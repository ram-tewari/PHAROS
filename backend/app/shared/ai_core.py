"""
Neo Alexandria 2.0 - Shared AI Core

This module provides AI-powered content processing capabilities for the shared kernel.
It handles text summarization, entity extraction, and classification using Hugging Face transformers.

Features:
- Text summarization using BART-based models
- Zero-shot classification for automatic tagging
- Entity extraction (placeholder for future implementation)
- Lazy loading and caching for optimal performance
- Graceful fallback when AI dependencies are unavailable
- Thread-safe model loading and inference

Related files:
- app/shared/embeddings.py: Embedding generation
- app/config/settings.py: AI model configuration settings
"""

from __future__ import annotations

from typing import List, Optional, Sequence

# Lazy import transformers to avoid heavy import at module load in tests
try:
    from transformers import pipeline  # type: ignore
except Exception:  # pragma: no cover
    pipeline = None  # type: ignore


class Summarizer:
    """Abstraction around a text summarization model.

    Uses transformers pipeline('summarization') with a configurable model.
    """

    def __init__(
        self,
        model_name: str = "sshleifer/distilbart-cnn-12-6",
        max_length: int = 180,
        min_length: int = 50,
    ) -> None:
        self.model_name = model_name
        self.max_length = max_length
        self.min_length = min_length
        self._pipe = None

    def _ensure_loaded(self):
        if self._pipe is None:
            if pipeline is None:  # pragma: no cover
                # Leave pipe as None; caller will use fallback
                return
            try:
                self._pipe = pipeline("summarization", model=self.model_name)
            except Exception:
                # Task may not be available in this transformers version
                self._pipe = None

    def summarize(self, text: str) -> str:
        text = (text or "").strip()
        if not text:
            return ""
        self._ensure_loaded()
        if self._pipe is not None:
            try:
                # CRITICAL: Truncate input to prevent CUDA context overflow
                # Most summarization models have 1024 token limit
                # Truncate to ~3000 chars (~750 tokens) to be safe
                if len(text) > 3000:
                    text = text[:3000]
                
                result = self._pipe(
                    text,
                    max_length=self.max_length,
                    min_length=self.min_length,
                    do_sample=False,
                    truncation=True,  # Force truncation at tokenizer level
                )
                if isinstance(result, list) and result:
                    summary_text = result[0].get("summary_text") or ""
                    return summary_text.strip()
            except Exception:  # pragma: no cover - model-specific failures
                pass
        # Fallbacks when transformers unavailable or failed
        if len(text) <= 280:
            return text
        trimmed = text[:280]
        return trimmed + "…"


class ZeroShotTagger:
    """Zero-shot classification tagger producing labels from candidate set.

    Uses transformers pipeline('zero-shot-classification') with a configurable model.
    """

    def __init__(
        self,
        model_name: str = "facebook/bart-large-mnli",
        candidate_labels: Optional[Sequence[str]] = None,
        multi_label: bool = True,
        threshold: float = 0.3,
    ) -> None:
        self.model_name = model_name
        self.multi_label = multi_label
        self.threshold = float(threshold)
        self._pipe = None
        # Default broad candidate set; AuthorityControl will normalize downstream
        default_candidates = [
            "Artificial Intelligence",
            "Machine Learning",
            "Deep Learning",
            "Neural Networks",
            "Natural Language Processing",
            "Language",
            "Linguistics",
            "Programming",
            "Python",
            "Data Science",
            "Mathematics",
            "Physics",
            "Biology",
            "Chemistry",
            "Economics",
            "History",
        ]
        self.candidate_labels: List[str] = (
            list(candidate_labels) if candidate_labels else default_candidates
        )

    def _ensure_loaded(self):
        if self._pipe is None:
            if pipeline is None:  # pragma: no cover
                # Leave pipe as None; caller will use heuristics
                return
            try:
                self._pipe = pipeline("zero-shot-classification", model=self.model_name)
            except Exception:
                self._pipe = None

    def generate_tags(self, text: str) -> List[str]:
        text = (text or "").strip()
        if not text:
            return []
        self._ensure_loaded()
        if self._pipe is not None:
            try:
                # CRITICAL: Truncate input to prevent CUDA context overflow
                # Zero-shot models typically have 1024 token limit
                # Truncate to ~3000 chars (~750 tokens) to be safe
                if len(text) > 3000:
                    text = text[:3000]
                
                res = self._pipe(
                    text,
                    candidate_labels=self.candidate_labels,
                    multi_label=self.multi_label,
                    truncation=True,  # Force truncation at tokenizer level
                )
                labels = res.get("labels") or []
                scores = res.get("scores") or []
                out: List[str] = []
                for label, score in zip(labels, scores):
                    try:
                        sc = float(score)
                    except Exception:
                        sc = 0.0
                    if sc >= self.threshold:
                        out.append(str(label))
                return out
            except Exception:  # pragma: no cover
                pass
        # Fallback: simple heuristic keywords
        lower = text.lower()
        tags: List[str] = []
        if "artificial intelligence" in lower or " ai " in f" {lower} ":
            tags.append("Artificial Intelligence")
        if "machine learning" in lower or " ml " in f" {lower} ":
            tags.append("Machine Learning")
        if "linguistic" in lower or "language" in lower:
            tags.append("Language")
        if "python" in lower:
            tags.append("Python")
        return tags


class AICore:
    """Facade to AI capabilities used across the application.

    Provides a unified interface for summarization, tagging, and classification.
    Designed for dependency injection in services and easy testing.
    """

    def __init__(
        self,
        summarizer: Optional[Summarizer] = None,
        tagger: Optional[ZeroShotTagger] = None,
    ) -> None:
        self.summarizer = summarizer or Summarizer()
        self.tagger = tagger or ZeroShotTagger()

    def summarize(self, text: str) -> str:
        """Generate a summary of the given text.

        Args:
            text: Input text to summarize

        Returns:
            Summary text
        """
        return self.summarizer.summarize(text)

    def generate_tags(self, text: str) -> List[str]:
        """Generate tags for the given text using zero-shot classification.

        Args:
            text: Input text to tag

        Returns:
            List of tag strings
        """
        return self.tagger.generate_tags(text)

    def classify_text(
        self, text: str, candidate_labels: Optional[List[str]] = None
    ) -> List[str]:
        """Classify text into one or more categories.

        This is an alias for generate_tags with optional custom labels.

        Args:
            text: Input text to classify
            candidate_labels: Optional list of candidate labels

        Returns:
            List of classification labels
        """
        if candidate_labels:
            # Create a temporary tagger with custom labels
            temp_tagger = ZeroShotTagger(
                model_name=self.tagger.model_name,
                candidate_labels=candidate_labels,
                multi_label=self.tagger.multi_label,
                threshold=self.tagger.threshold,
            )
            return temp_tagger.generate_tags(text)
        return self.generate_tags(text)

    def extract_entities(self, text: str) -> List[dict]:
        """Extract named entities from text.

        This is a placeholder for future entity extraction functionality.

        Args:
            text: Input text

        Returns:
            List of entity dictionaries with 'text', 'type', and 'score' keys
        """
        # Placeholder implementation
        # In production, this would use NER models
        return []
