"""
Neo Alexandria 2.0 - Shared Embedding Service

This module provides embedding generation and caching functionality for the shared kernel.
It consolidates embedding operations used across all domain modules.

Features:
- Vector embedding generation using sentence-transformers
- Sparse embedding generation for hybrid search
- Batch embedding generation for efficiency
- Redis caching with intelligent TTL
- Thread-safe model loading

Related files:
- app/shared/ai_core.py: Core AI operations
- app/shared/cache.py: Caching layer
- app/shared/database.py: Database access
"""

import logging
import threading
from typing import List, Optional
from sqlalchemy.orm import Session

# Lazy import sentence-transformers for embeddings
try:
    from sentence_transformers import SentenceTransformer  # type: ignore
except Exception:  # pragma: no cover
    SentenceTransformer = None  # type: ignore

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """Abstraction around a sentence embedding model.

    Uses sentence-transformers with a configurable model for generating
    vector embeddings from text content.
    """

    def __init__(self, model_name: str = "nomic-ai/nomic-embed-text-v1") -> None:
        self.model_name = model_name
        self._model = None
        self._model_lock = threading.Lock()
        self._warmed_up = False
        
        # Detect best device for acceleration
        try:
            import torch
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            self.device = "cpu"
        logger.info(f"Embedding device: {self.device}")

    def _ensure_loaded(self):
        """Lazy load the embedding model in a thread-safe manner."""
        if self._model is None:
            with self._model_lock:
                if self._model is None:  # Double-check locking pattern
                    import os
                    deployment_mode = os.getenv("MODE", "EDGE")
                    if deployment_mode == "CLOUD":
                        logger.info("Cloud mode detected - skipping embedding model load (query embeddings via Tailscale Funnel)")
                        return
                    
                    if SentenceTransformer is None:  # pragma: no cover
                        # Leave model as None; caller will use fallback
                        return
                    # Arm faulthandler so a native crash inside torch / nomic
                    # custom code dumps a stack instead of dying silently.
                    try:
                        import faulthandler
                        if not faulthandler.is_enabled():
                            faulthandler.enable()
                    except Exception:
                        pass

                    try:
                        logger.info(
                            f"Loading SentenceTransformer model={self.model_name!r} "
                            f"device={self.device} (use_safetensors=True)"
                        )
                        # use_safetensors avoids the pytorch_model.bin load path,
                        # which has been observed to crash silently on Windows +
                        # Python 3.13 + nomic-bert custom remote code.
                        self._model = SentenceTransformer(
                            self.model_name,
                            trust_remote_code=True,
                            device=self.device,
                            model_kwargs={"use_safetensors": True},
                        )
                        logger.info(
                            f"Loaded embedding model on {self.device}: {self.model_name}"
                        )
                    except TypeError:
                        # Older sentence-transformers (<3) doesn't accept
                        # model_kwargs. Fall back to the plain constructor.
                        logger.warning(
                            "sentence-transformers does not accept model_kwargs; "
                            "retrying without use_safetensors hint"
                        )
                        try:
                            self._model = SentenceTransformer(
                                self.model_name,
                                trust_remote_code=True,
                                device=self.device,
                            )
                            logger.info(
                                f"Loaded embedding model on {self.device}: {self.model_name}"
                            )
                        except Exception as e:
                            logger.exception(f"Failed to load embedding model: {e}")
                    except Exception as e:
                        # Use .exception so the traceback reaches the log, not
                        # just the message. The previous handler swallowed the
                        # stack and made silent crashes look like clean exits.
                        logger.exception(f"Failed to load embedding model: {e}")

    def warmup(self) -> bool:
        """Warmup the model with a dummy encoding to avoid cold start latency.

        This should be called once during application startup to ensure
        the first real encoding is fast.

        Returns:
            True if warmup successful, False otherwise
        """
        if self._warmed_up:
            logger.debug("Model already warmed up, skipping")
            return True

        self._ensure_loaded()
        if self._model is not None:
            try:
                # Perform a dummy encoding to warm up the model
                _ = self._model.encode("warmup", convert_to_tensor=False)
                self._warmed_up = True
                logger.info(f"Embedding model warmed up: {self.model_name}")
                return True
            except Exception as e:  # pragma: no cover
                logger.error(f"Model warmup failed: {e}")
                return False
        return False

    def generate_embedding(self, text: str) -> List[float]:
        """Generate vector embedding for the given text.

        Returns:
            List of float values representing the embedding vector.
            Returns empty list if model unavailable or text is empty.
        """
        text = (text or "").strip()
        if not text:
            return []

        self._ensure_loaded()
        if self._model is not None:
            try:
                # sentence-transformers returns numpy array, convert to list
                embedding = self._model.encode(text, convert_to_tensor=False)
                return embedding.tolist()
            except Exception:  # pragma: no cover - encoding failures
                pass

        # Fallback: return empty embedding
        return []


def create_composite_text(resource) -> str:
    """Create composite text from resource for embedding generation.

    Combines title, description, and subjects into a single text string
    optimized for semantic embedding.

    Args:
        resource: Resource object with title, description, and subject fields

    Returns:
        Composite text string suitable for embedding generation
    """
    parts = []

    # Add title (most important)
    if hasattr(resource, "title") and resource.title:
        parts.append(resource.title)

    # Add description
    if hasattr(resource, "description") and resource.description:
        parts.append(resource.description)

    # Add subjects as keywords
    if hasattr(resource, "subject") and resource.subject:
        try:
            if isinstance(resource.subject, list):
                subjects_text = " ".join(resource.subject)
                if subjects_text.strip():
                    parts.append(f"Keywords: {subjects_text}")
        except Exception:
            pass

    return " ".join(parts)


class EmbeddingService:
    """Service for generating and caching embeddings.

    This service provides embedding generation with Redis caching
    to reduce expensive computation. Embeddings are cached with a 1-hour TTL.

    Attributes:
        db: Database session
        embedding_generator: EmbeddingGenerator instance
        cache: Optional cache service for caching embeddings
    """

    def __init__(
        self,
        db: Optional[Session] = None,
        embedding_generator: Optional[EmbeddingGenerator] = None,
        cache_service=None,
    ):
        """Initialize embedding service.

        Args:
            db: Optional database session
            embedding_generator: Optional EmbeddingGenerator instance
            cache_service: Optional cache service for caching
        """
        self.db = db
        self.embedding_generator = embedding_generator or EmbeddingGenerator()
        self.cache = cache_service

    def warmup(self) -> bool:
        """Warmup the embedding model to avoid cold start latency.

        This should be called once during application startup.

        Returns:
            True if warmup successful, False otherwise
        """
        return self.embedding_generator.warmup()

    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text.

        Returns:
            Embedding vector as list of floats
        """
        return self.embedding_generator.generate_embedding(text)

    def generate_sparse_embedding(self, text: str) -> dict:
        """Generate sparse embedding for hybrid search.

        This is a placeholder for sparse embedding generation.
        In a full implementation, this would use BM25 or similar.

        Args:
            text: Input text

        Returns:
            Dictionary with sparse embedding data
        """
        # Placeholder implementation
        # In production, this would use BM25 or similar sparse representation
        words = text.lower().split()
        word_freq = {}
        for word in words:
            word_freq[word] = word_freq.get(word, 0) + 1
        return word_freq

    def encode(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """Convenience alias for batch_generate — accepts a list and returns embeddings.

        Maintains backwards-compatible single-string support: if a bare string is
        passed it is wrapped in a list and the first result is returned.

        Args:
            texts: List of texts (or a single string for backwards compatibility)
            batch_size: Batch size passed to the underlying encoder

        Returns:
            List of embedding vectors, or a single vector if input was a string
        """
        if isinstance(texts, str):
            result = self.batch_generate([texts], batch_size=batch_size)
            return result[0] if result else []
        return self.batch_generate(texts, batch_size=batch_size)

    def batch_generate(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """Generate embeddings for multiple texts efficiently using TRUE batch processing.

        This uses the model's native batch encoding which is 6-7x faster than
        processing texts one at a time.

        Args:
            texts: List of input texts
            batch_size: Batch size for encoding (default: 32)

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        # Filter empty texts and track indices
        valid_texts = [(i, text.strip()) for i, text in enumerate(texts) if text and text.strip()]
        if not valid_texts:
            return [[] for _ in texts]

        # Delegate to the generator which owns the model instance
        gen = self.embedding_generator
        gen._ensure_loaded()
        if gen._model is not None:
            try:
                texts_to_encode = [text for _, text in valid_texts]

                # Use model's native batch encoding (6-7x faster than loop)
                embeddings = gen._model.encode(
                    texts_to_encode,
                    convert_to_tensor=False,
                    batch_size=batch_size,
                    show_progress_bar=len(texts_to_encode) > 10,
                )

                # Map back to original indices
                result = [[] for _ in texts]
                for (original_idx, _), embedding in zip(valid_texts, embeddings):
                    result[original_idx] = embedding.tolist()

                logger.info(f"Batch generated {len(valid_texts)} embeddings")
                return result
            except Exception as e:
                logger.error(f"Batch encoding failed: {e}")

        # Fallback to individual encoding
        logger.warning("Falling back to individual encoding (slower)")
        return [self.generate_embedding(text) for text in texts]

    def get_embedding(self, resource_id: str) -> Optional[List[float]]:
        """Get embedding for a resource with caching.

        First checks cache, then generates if not found and stores in cache.

        Args:
            resource_id: Resource ID

        Returns:
            Embedding vector as list of floats, or None if generation fails
        """
        if not self.db:
            logger.warning("No database session provided to EmbeddingService")
            return None

        cache_key = f"embedding:{resource_id}"

        # Try cache first if available
        if self.cache:
            cached_embedding = self.cache.get(cache_key)
            if cached_embedding is not None:
                logger.debug(f"Cache hit for embedding: {resource_id}")
                return cached_embedding
            logger.debug(f"Cache miss for embedding: {resource_id}")

        # Cache miss - generate embedding
        embedding = self._generate_embedding_from_db(resource_id)

        # Store in cache if generation succeeded and cache available
        if embedding and self.cache:
            self.cache.set(cache_key, embedding, ttl=3600)  # 1 hour TTL

        return embedding

    def _generate_embedding_from_db(self, resource_id: str) -> Optional[List[float]]:
        """Generate embedding for a resource from database.

        Args:
            resource_id: Resource ID

        Returns:
            Embedding vector as list of floats, or None if generation fails
        """
        if not self.db:
            return None

        try:
            # Import here to avoid circular dependency
            from ..database import models as db_models

            # Fetch resource from database
            resource = (
                self.db.query(db_models.Resource)
                .filter(db_models.Resource.id == resource_id)
                .first()
            )

            if not resource:
                logger.warning(f"Resource not found: {resource_id}")
                return None

            # Create composite text from resource
            composite_text = create_composite_text(resource)

            if not composite_text.strip():
                logger.warning(f"Empty composite text for resource: {resource_id}")
                return None

            # Generate embedding
            embedding = self.generate_embedding(composite_text)

            if not embedding:
                logger.warning(
                    f"Embedding generation failed for resource: {resource_id}"
                )
                return None

            logger.info(f"Generated embedding for resource: {resource_id}")
            return embedding

        except Exception as e:
            logger.error(f"Error generating embedding for resource {resource_id}: {e}")
            return None

    def generate_and_store_embedding(self, resource_id: str) -> bool:
        """Generate embedding and store in both database and cache.

        This method is used by background tasks to regenerate embeddings
        after resource updates.

        Args:
            resource_id: Resource ID

        Returns:
            True if successful, False otherwise
        """
        if not self.db:
            logger.warning("No database session provided to EmbeddingService")
            return False

        try:
            # Import here to avoid circular dependency
            from ..database import models as db_models

            # Generate embedding
            embedding = self._generate_embedding_from_db(resource_id)

            if not embedding:
                return False

            # Store in database
            resource = (
                self.db.query(db_models.Resource)
                .filter(db_models.Resource.id == resource_id)
                .first()
            )

            if not resource:
                logger.warning(f"Resource not found: {resource_id}")
                return False

            resource.embedding = embedding
            self.db.commit()

            # Store in cache if available
            if self.cache:
                cache_key = f"embedding:{resource_id}"
                self.cache.set(cache_key, embedding, ttl=3600)  # 1 hour TTL

            logger.info(f"Stored embedding for resource: {resource_id}")
            return True

        except Exception as e:
            logger.error(f"Error storing embedding for resource {resource_id}: {e}")
            if self.db:
                self.db.rollback()
            return False

    def invalidate_cache(self, resource_id: str):
        """Invalidate cached embedding for a resource.

        Args:
            resource_id: Resource ID
        """
        if self.cache:
            cache_key = f"embedding:{resource_id}"
            self.cache.delete(cache_key)
            logger.info(f"Invalidated embedding cache for resource: {resource_id}")
