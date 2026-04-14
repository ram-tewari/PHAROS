"""
Real SPLADE Sparse Embedding Service

Implements true SPLADE (Sparse Lexical and Expansion) model for learned keyword search.
Uses naver/splade-cocondenser-ensembledistil for production-grade sparse embeddings.

This replaces the TF-IDF fallback with actual transformer-based sparse representations.
"""

from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
import logging
from datetime import datetime
import importlib.util

logger = logging.getLogger(__name__)

# Defer heavy imports (torch/transformers/numpy) until first real model use.
SPLADE_AVAILABLE = all(
    importlib.util.find_spec(pkg) is not None
    for pkg in ("torch", "transformers", "numpy")
)

if not SPLADE_AVAILABLE:
    logger.warning(
        "transformers or torch not available. Install with: pip install transformers torch"
    )


class RealSPLADEService:
    """
    Real SPLADE sparse embedding service using transformer models.
    
    SPLADE generates sparse token-weight dictionaries where:
    - Keys are vocabulary token IDs
    - Values are learned importance weights
    - Sparse representation enables efficient inverted index search
    
    Model: naver/splade-cocondenser-ensembledistil
    - Lightweight (33M parameters)
    - Fast inference (~50ms per query on CPU)
    - Production-ready quality
    """
    
    def __init__(
        self, 
        db: Session, 
        model_name: str = "naver/splade-cocondenser-ensembledistil",
        device: str = "cpu"
    ):
        """
        Initialize SPLADE service.
        
        Args:
            db: Database session
            model_name: HuggingFace model identifier
            device: Device for inference ("cpu" or "cuda")
        """
        self.db = db
        self.model_name = model_name
        self.device = device
        self.model: Optional[Any] = None
        self.tokenizer: Optional[Any] = None
        self._model_loaded = False
        
    def _load_model(self):
        """Lazy load SPLADE model on first use."""
        if self._model_loaded:
            return
            
        self._model_loaded = True
        
        if not SPLADE_AVAILABLE:
            logger.error(
                "SPLADE dependencies not available. "
                "Install with: pip install transformers torch"
            )
            return
            
        try:
            global torch, AutoModelForMaskedLM, AutoTokenizer, np

            import numpy as np
            import torch
            from transformers import AutoModelForMaskedLM, AutoTokenizer

            logger.info(f"Loading SPLADE model: {self.model_name}")
            
            # Load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            
            # Load model
            self.model = AutoModelForMaskedLM.from_pretrained(self.model_name)
            self.model.to(self.device)
            self.model.eval()  # Set to evaluation mode
            
            logger.info(f"SPLADE model loaded successfully on {self.device}")
            
        except Exception as e:
            logger.error(f"Failed to load SPLADE model: {e}")
            self.model = None
            self.tokenizer = None
    
    def generate_embedding(self, text: str, max_length: int = 256) -> Dict[int, float]:
        """
        Generate SPLADE sparse embedding for text.
        
        Args:
            text: Input text
            max_length: Maximum token length (default: 256)
            
        Returns:
            Dictionary mapping token IDs to weights (sparse vector)
            Format: {token_id: weight, ...}
            
        Example:
            {
                2054: 0.847,  # "authentication"
                3029: 0.623,  # "oauth"
                1998: 0.512,  # "security"
                ...
            }
        """
        if not text or not text.strip():
            return {}
            
        # Lazy load model
        self._load_model()
        
        if self.model is None or self.tokenizer is None:
            logger.error("SPLADE model not available, cannot generate embedding")
            return self._generate_fallback_sparse(text)
            
        try:
            # Tokenize input
            inputs = self.tokenizer(
                text,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=max_length
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            # Forward pass through SPLADE model
            with torch.no_grad():
                outputs = self.model(**inputs)
                logits = outputs.logits  # Shape: (batch_size, seq_len, vocab_size)
            
            # Apply log(1 + ReLU(logits)) activation (SPLADE paper)
            # This creates sparse representations with learned importance
            activated = torch.log(1 + torch.relu(logits))
            
            # Max pooling over sequence dimension
            # Shape: (batch_size, vocab_size)
            pooled = torch.max(activated, dim=1).values
            
            # Convert to sparse dictionary
            # Only keep non-zero weights to maintain sparsity
            sparse_vec = {}
            pooled_np = pooled.cpu().numpy()[0]  # Get first (only) batch item
            
            # Find non-zero indices
            non_zero_indices = np.where(pooled_np > 0)[0]
            
            for idx in non_zero_indices:
                token_id = int(idx)
                weight = float(pooled_np[idx])
                sparse_vec[token_id] = weight
            
            logger.debug(
                f"Generated SPLADE embedding with {len(sparse_vec)} non-zero tokens"
            )
            
            return sparse_vec
            
        except Exception as e:
            logger.error(f"Error generating SPLADE embedding: {e}")
            return self._generate_fallback_sparse(text)
    
    def _generate_fallback_sparse(self, text: str) -> Dict[int, float]:
        """
        Generate simple TF-IDF-like sparse representation as fallback.
        
        This is used when SPLADE model is unavailable.
        
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
    
    def batch_generate_embeddings(
        self, 
        texts: List[str], 
        batch_size: int = 8
    ) -> List[Dict[int, float]]:
        """
        Generate SPLADE embeddings for multiple texts in batches.
        
        Args:
            texts: List of input texts
            batch_size: Batch size for processing
            
        Returns:
            List of sparse embeddings
        """
        embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_embeddings = [self.generate_embedding(text) for text in batch]
            embeddings.extend(batch_embeddings)
            
        return embeddings
    
    def batch_update_sparse_embeddings(
        self,
        resource_ids: List[str] = None,
        batch_size: int = 16,
        force_update: bool = False
    ):
        """
        Batch update sparse embeddings for resources in database.
        
        Args:
            resource_ids: Optional list of specific resource IDs to process
            batch_size: Batch size for processing
            force_update: If True, regenerate even if embedding exists
        """
        from ...database.models import Resource
        from sqlalchemy import or_
        
        try:
            # Query resources to process
            if resource_ids:
                query = self.db.query(Resource).filter(Resource.id.in_(resource_ids))
            else:
                if force_update:
                    query = self.db.query(Resource)
                else:
                    query = self.db.query(Resource).filter(
                        or_(
                            Resource.sparse_embedding.is_(None),
                            Resource.sparse_embedding == {},
                        )
                    )
            
            resources = query.all()
            total = len(resources)
            
            logger.info(f"Processing {total} resources for SPLADE embeddings")
            
            # Process in batches
            for i in range(0, total, batch_size):
                batch = resources[i:i + batch_size]
                
                for resource in batch:
                    # Generate sparse embedding
                    text = resource.description or resource.title or ""
                    sparse_vec = self.generate_embedding(text)
                    
                    # Store as JSONB (PostgreSQL will handle this natively)
                    resource.sparse_embedding = sparse_vec
                    resource.sparse_embedding_model = self.model_name
                    resource.sparse_embedding_updated_at = datetime.utcnow()
                
                # Commit batch
                self.db.commit()
                logger.info(
                    f"Processed {min(i + batch_size, total)}/{total} resources"
                )
            
            logger.info(
                f"Completed SPLADE embedding generation for {total} resources"
            )
            
        except Exception as e:
            logger.error(f"Error in batch SPLADE embedding generation: {e}")
            self.db.rollback()
            raise
    
    def decode_tokens(self, sparse_vec: Dict[int, float], top_k: int = 10) -> List[tuple]:
        """
        Decode token IDs to human-readable tokens for debugging.
        
        Args:
            sparse_vec: Sparse embedding dictionary
            top_k: Number of top tokens to return
            
        Returns:
            List of (token, weight) tuples sorted by weight
        """
        if self.tokenizer is None:
            self._load_model()
            
        if self.tokenizer is None:
            return []
        
        # Sort by weight descending
        sorted_items = sorted(sparse_vec.items(), key=lambda x: x[1], reverse=True)
        
        # Decode top-k tokens
        decoded = []
        for token_id, weight in sorted_items[:top_k]:
            token = self.tokenizer.decode([token_id])
            decoded.append((token, weight))
        
        return decoded


# Backward compatibility: alias to new implementation
SparseEmbeddingService = RealSPLADEService
