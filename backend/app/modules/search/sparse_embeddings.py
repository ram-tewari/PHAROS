"""
Sparse Embedding Service

Provides sparse vector embedding generation for learned keyword search.
Uses BGE-M3 model for generating sparse representations.
"""

from typing import Dict, List, Optional
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)

# Try to import FlagEmbedding for BGE-M3 model
try:
    from FlagEmbedding import BGEM3FlagModel

    BGEM3_AVAILABLE = True
except ImportError:
    BGEM3_AVAILABLE = False
    logger.info(
        "FlagEmbedding not available, using TF-IDF fallback for sparse embeddings"
    )


class SparseEmbeddingService:
    """
    Sparse embedding service for learned keyword search.

    Generates sparse vector representations for text using BGE-M3 model.
    Sparse vectors capture learned keyword importance for better retrieval.
    """

    def __init__(self, db: Session, model_name: str = "BAAI/bge-m3"):
        """
        Initialize sparse embedding service.

        Args:
            db: Database session
            model_name: Sparse embedding model name (default: BAAI/bge-m3)
        """
        self.db = db
        self.model_name = model_name
        self.model: Optional["BGEM3FlagModel"] = None
        self._model_loaded = False

    def _load_model(self):
        """Lazy load the sparse embedding model on first use."""
        if self._model_loaded:
            return

        self._model_loaded = True

        if not BGEM3_AVAILABLE:
            logger.warning("BGE-M3 model not available, using TF-IDF fallback")
            return

        try:
            logger.info(f"Loading BGE-M3 model: {self.model_name}")
            self.model = BGEM3FlagModel(
                self.model_name,
                use_fp16=True,  # Memory efficient
                device="cpu",  # Start with CPU, can be changed to "cuda" if available
            )
            logger.info("BGE-M3 model loaded successfully")
        except Exception as e:
            logger.warning(f"Could not load BGE-M3 model, using fallback: {e}")
            self.model = None

    def generate_embedding(self, text: str) -> Dict[int, float]:
        """
        Generate sparse embedding for text.

        Args:
            text: Input text

        Returns:
            Dictionary mapping token IDs to weights (sparse vector)
        """
        if not text or not text.strip():
            return {}

        # Lazy load model on first use
        self._load_model()

        try:
            if self.model is None:
                # Fallback: simple TF-IDF-like sparse representation
                return self._generate_fallback_sparse(text)

            # Use BGE-M3 model to generate sparse embedding
            output = self.model.encode(
                [text],
                return_sparse=True,
                return_dense=False,
                return_colbert_vecs=False,
            )
            sparse_vec = output.get("lexical_weights", [{}])[0]
            return {int(k): float(v) for k, v in sparse_vec.items()}

        except Exception as e:
            logger.error(f"Error generating sparse embedding: {e}")
            # Fallback on error
            return self._generate_fallback_sparse(text)

    def _generate_fallback_sparse(self, text: str) -> Dict[int, float]:
        """
        Generate simple sparse representation as fallback.

        Uses basic term frequency with simple normalization.

        Args:
            text: Input text

        Returns:
            Dictionary mapping token hashes to weights
        """
        from collections import Counter

        # Tokenize (simple whitespace + lowercase)
        tokens = text.lower().split()

        # Count term frequencies
        term_freq = Counter(tokens)

        # Normalize by document length
        doc_length = len(tokens)
        if doc_length == 0:
            return {}

        # Create sparse vector using hash of terms as IDs
        sparse_vec = {}
        for term, freq in term_freq.items():
            term_id = hash(term) % (2**31)  # Use hash as token ID
            weight = freq / doc_length  # Simple TF normalization
            sparse_vec[term_id] = weight

        return sparse_vec

    def batch_generate_embeddings(self, texts: List[str]) -> List[Dict[int, float]]:
        """
        Generate sparse embeddings for multiple texts.

        Args:
            texts: List of input texts

        Returns:
            List of sparse embeddings
        """
        return [self.generate_embedding(text) for text in texts]

    def batch_update_sparse_embeddings(
        self, resource_ids: List[str] = None, batch_size: int = 32
    ):
        """
        Batch update sparse embeddings for resources.

        Args:
            resource_ids: Optional list of specific resource IDs to process
            batch_size: Batch size for processing
        """
        from ...database.models import Resource
        from sqlalchemy import or_
        import json
        from datetime import datetime

        try:
            # Query resources to process
            if resource_ids:
                query = self.db.query(Resource).filter(Resource.id.in_(resource_ids))
            else:
                query = self.db.query(Resource).filter(
                    or_(
                        Resource.sparse_embedding.is_(None),
                        Resource.sparse_embedding == "",
                    )
                )

            resources = query.all()
            total = len(resources)

            logger.info(f"Processing {total} resources for sparse embeddings")

            # Process in batches
            for i in range(0, total, batch_size):
                batch = resources[i : i + batch_size]

                for resource in batch:
                    # Generate sparse embedding
                    text = resource.description or resource.title or ""
                    sparse_vec = self.generate_embedding(text)

                    # Store as JSON
                    resource.sparse_embedding = json.dumps(sparse_vec)
                    resource.sparse_embedding_model = self.model_name
                    resource.sparse_embedding_updated_at = datetime.utcnow()

                # Commit batch
                self.db.commit()
                logger.info(f"Processed {min(i + batch_size, total)}/{total} resources")

            logger.info(f"Completed sparse embedding generation for {total} resources")

        except Exception as e:
            logger.error(f"Error in batch sparse embedding generation: {e}")
            self.db.rollback()
            raise
