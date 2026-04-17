"""
Quality Module - Service

Combined implementation with QualityService and ContentQualityAnalyzer.
Extracted from app/services/quality_service.py as part of vertical slice refactoring.
"""

from typing import Dict, List, Optional, Any, Mapping
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
import json
import logging

from app.utils import text_processor as tp
from .domain import QualityScore
from app.shared.cache import cache

logger = logging.getLogger(__name__)


# Quality thresholds for classification
HIGH_QUALITY_THRESHOLD = 0.8
MEDIUM_QUALITY_THRESHOLD = 0.5

# Default quality dimension weights
# These weights represent the relative importance of each quality dimension
# in computing the overall quality score. They must sum to 1.0.
# Rationale:
# - Accuracy (0.25): Critical for ensuring data correctness and validation
# - Completeness (0.25): Essential for comprehensive resource information
# - Consistency (0.20): Important for maintaining data integrity
# - Timeliness (0.15): Relevant for keeping information current
# - Relevance (0.15): Useful for context-specific quality assessment
DEFAULT_QUALITY_WEIGHTS = {
    "accuracy": 0.25,
    "completeness": 0.25,
    "consistency": 0.20,
    "timeliness": 0.15,
    "relevance": 0.15,
}

# ContentQualityAnalyzer weights for overall quality computation
# Rationale:
# - Metadata (0.6): Primary indicator of resource quality and completeness
# - Readability (0.4): Secondary indicator for text-based content assessment
METADATA_WEIGHT = 0.6
READABILITY_WEIGHT = 0.4

# Reading ease normalization constants
# Flesch Reading Ease typically ranges from 0-100
READING_EASE_MIN = 0.0
READING_EASE_MAX = 100.0
READING_EASE_OFFSET = 30.0  # Offset for normalization adjustment
READING_EASE_RANGE = (
    150.0  # Total range for normalization to get 0.5 for reading_ease of 75
)

# Source credibility scores
# Rationale: Different source types have different inherent credibility levels
CREDIBILITY_HIGH = 0.9  # Academic/government sources (.edu, .gov, arxiv, doi, pubmed)
CREDIBILITY_MEDIUM = 0.7  # Organizational/community sources (.org, wikipedia, github)
CREDIBILITY_DEFAULT = 0.6  # General web sources
CREDIBILITY_UNKNOWN = 0.5  # No source information available

# Content depth thresholds (word count)
# Rationale: Longer content generally indicates more comprehensive coverage
DEPTH_THRESHOLD_MINIMAL = 50  # Below this: shallow content (score: 0.2)
DEPTH_THRESHOLD_SHORT = 200  # Below this: short content (score: 0.4)
DEPTH_THRESHOLD_MEDIUM = 1000  # Below this: medium content (score: 0.7)
# Above DEPTH_THRESHOLD_MEDIUM: comprehensive content (score: 0.9)

DEPTH_SCORE_MINIMAL = 0.2
DEPTH_SCORE_SHORT = 0.4
DEPTH_SCORE_MEDIUM = 0.7
DEPTH_SCORE_COMPREHENSIVE = 0.9

# Completeness dimension weights per metadata field
# Each required field contributes equally to the completeness score
COMPLETENESS_FIELD_WEIGHT = 0.2  # 5 fields × 0.2 = 1.0

# Quality degradation monitoring
DEGRADATION_THRESHOLD = 0.2  # 20% drop in quality triggers review
DEGRADATION_DEFAULT_WINDOW_DAYS = 30  # Default time window for monitoring

# Outlier detection parameters
OUTLIER_MIN_RESOURCES = 10  # Minimum resources required for statistical validity
OUTLIER_CONTAMINATION = 0.1  # Expected proportion of outliers (10%)
OUTLIER_N_ESTIMATORS = 100  # Number of trees in Isolation Forest
OUTLIER_RANDOM_STATE = 42  # Random seed for reproducibility
OUTLIER_DEFAULT_BATCH_SIZE = 1000  # Default batch size for processing
OUTLIER_THRESHOLD_LOW = 0.3  # Threshold for identifying low dimension scores

# Default feature values for missing data
FEATURE_DEFAULT_VALUE = 0.5  # Neutral baseline for missing quality dimensions

# Weight validation tolerance
WEIGHT_SUM_TOLERANCE = 0.001  # Acceptable deviation from 1.0 for weight sum


class ContentQualityAnalyzer:
    """Compute content quality metrics for a resource and its text."""

    REQUIRED_KEYS = [
        "title",
        "description",
        "subject",
        "creator",
        "language",
        "type",
        "identifier",
    ]

    def metadata_completeness(self, resource_in: Mapping[str, Any] | Any) -> float:
        """Return ratio of required fields that are present and non-empty."""
        present = 0
        total = len(self.REQUIRED_KEYS)
        for key in self.REQUIRED_KEYS:
            value = None
            if isinstance(resource_in, Mapping):
                value = resource_in.get(key)
            else:
                value = getattr(resource_in, key, None)
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            if isinstance(value, list) and len(value) == 0:
                continue
            present += 1
        return present / total if total else 0.0

    def text_readability(self, text: str) -> Dict[str, float]:
        return tp.readability_scores(text)

    def content_readability(self, text: str) -> Dict[str, float]:
        """
        Compute comprehensive readability metrics for text content.

        Returns dictionary with:
        - reading_ease: Flesch Reading Ease score
        - fk_grade: Flesch-Kincaid Grade Level
        - word_count: Total number of words
        - sentence_count: Number of sentences
        - avg_words_per_sentence: Average words per sentence
        - unique_word_ratio: Ratio of unique words to total words
        - long_word_ratio: Ratio of words with >6 characters
        - paragraph_count: Number of paragraphs

        Args:
            text: Text content to analyze

        Returns:
            Dictionary with readability metrics
        """
        if not text or not text.strip():
            return {
                "reading_ease": 0.0,
                "fk_grade": 0.0,
                "word_count": 0.0,
                "sentence_count": 0.0,
                "avg_words_per_sentence": 0.0,
                "unique_word_ratio": 0.0,
                "long_word_ratio": 0.0,
                "paragraph_count": 0.0,
            }

        # Get base readability scores from text_processor
        base_scores = tp.readability_scores(text)

        # Calculate additional metrics
        words = text.split()
        word_count = len(words)

        # Count sentences (simple heuristic: split by . ! ?)
        import re

        sentences = re.split(r"[.!?]+", text)
        sentences = [s.strip() for s in sentences if s.strip()]
        sentence_count = len(sentences)

        # Average words per sentence
        avg_words_per_sentence = (
            word_count / sentence_count if sentence_count > 0 else 0.0
        )

        # Unique word ratio (vocabulary diversity)
        unique_words = set(word.lower() for word in words)
        unique_word_ratio = len(unique_words) / word_count if word_count > 0 else 0.0

        # Long word ratio (words with more than 6 characters)
        long_words = [word for word in words if len(word) > 6]
        long_word_ratio = len(long_words) / word_count if word_count > 0 else 0.0

        # Paragraph count (split by double newlines or single newlines)
        paragraphs = re.split(r"\n\s*\n|\n", text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        paragraph_count = len(paragraphs)

        return {
            "reading_ease": base_scores.get("reading_ease", 0.0),
            "fk_grade": base_scores.get("fk_grade", 0.0),
            "word_count": float(word_count),
            "sentence_count": float(sentence_count),
            "avg_words_per_sentence": avg_words_per_sentence,
            "unique_word_ratio": unique_word_ratio,
            "long_word_ratio": long_word_ratio,
            "paragraph_count": float(paragraph_count),
        }

    def overall_quality(self, resource_in: Dict[str, Any], text: str | None) -> float:
        meta_score = self.metadata_completeness(resource_in)
        if not text:
            return meta_score
        scores = self.text_readability(text)
        # Normalize reading ease: 75 should give 0.5, so divide by 150
        norm_read = max(0.0, min(1.0, scores.get("reading_ease", 0.0) / 150.0))
        return METADATA_WEIGHT * meta_score + READABILITY_WEIGHT * norm_read

    def quality_level(self, score: float) -> str:
        if score >= HIGH_QUALITY_THRESHOLD:
            return "HIGH"
        if score >= MEDIUM_QUALITY_THRESHOLD:
            return "MEDIUM"
        return "LOW"

    def source_credibility(self, source: Optional[str]) -> float:
        """Assess source credibility based on URL/identifier.

        Args:
            source: Source URL or identifier

        Returns:
            Credibility score between 0.0 and 1.0
        """
        if not source or not source.strip():
            return 0.0

        # Simple heuristics for credibility
        source_lower = source.lower()

        # Start with base score
        score = 0.5

        # High credibility domains (+0.4)
        high_cred_domains = [
            ".edu",
            ".gov",
            "arxiv.org",
            "doi.org",
            "pubmed",
            "scholar.google",
        ]
        if any(domain in source_lower for domain in high_cred_domains):
            score += 0.4

        # Medium credibility domains (+0.2)
        elif any(domain in source_lower for domain in [".org", "wikipedia", "github"]):
            score += 0.2

        # Standard domains (+0.1)
        elif any(domain in source_lower for domain in [".com", ".net"]):
            score += 0.1

        # HTTPS bonus (+0.05)
        if source_lower.startswith("https://"):
            score += 0.05

        # Penalties

        # IP address penalty (-0.3)
        import re

        if re.match(r"https?://\d+\.\d+\.\d+\.\d+", source_lower):
            score -= 0.3

        # Suspicious TLD penalty (-0.05)
        suspicious_tlds = [".xyz", ".top", ".click", ".loan", ".win"]
        if any(tld in source_lower for tld in suspicious_tlds):
            score -= 0.05

        # Blog platform penalty (-0.1)
        blog_platforms = ["blog.wordpress", "blogspot", "tumblr", "medium.com/@"]
        if any(platform in source_lower for platform in blog_platforms):
            score -= 0.1

        # Clamp to valid range
        return max(0.0, min(1.0, score))

    def content_depth(self, text: Optional[str]) -> float:
        """Assess content depth based on text length and complexity."""
        if not text:
            return 0.0

        word_count = len(text.split())

        # Score based on word count
        if word_count < DEPTH_THRESHOLD_MINIMAL:
            return DEPTH_SCORE_MINIMAL
        elif word_count < DEPTH_THRESHOLD_SHORT:
            return DEPTH_SCORE_SHORT
        elif word_count < DEPTH_THRESHOLD_MEDIUM:
            return DEPTH_SCORE_MEDIUM
        else:
            return DEPTH_SCORE_COMPREHENSIVE

    def _normalize_reading_ease(self, reading_ease: float) -> float:
        """Normalize Flesch Reading Ease score to 0-1 range.

        Flesch Reading Ease typically ranges from -30 to 100:
        - 90-100: Very easy (normalized to ~0.92-1.0)
        - 60-70: Standard (normalized to ~0.69-0.77)
        - 0-30: Difficult (normalized to ~0.23-0.46)
        - Below 0: Very difficult (normalized to 0.0-0.23)

        We normalize to 0-1 where higher is better.
        Formula: (reading_ease - (-30)) / (100 - (-30)) = (reading_ease + 30) / 130
        """
        # Extended range for Flesch Reading Ease: -30 to 100
        MIN_READING_EASE = -30.0
        MAX_READING_EASE = 100.0

        # Clamp to reasonable range
        clamped = max(MIN_READING_EASE, min(MAX_READING_EASE, reading_ease))
        # Normalize to 0-1
        return (clamped - MIN_READING_EASE) / (MAX_READING_EASE - MIN_READING_EASE)

    def overall_quality_score(
        self, resource: Dict[str, Any], content: Optional[str]
    ) -> float:
        """
        Compute comprehensive overall quality score combining multiple factors.

        This method integrates:
        - Metadata completeness (40%)
        - Source credibility (30%)
        - Content depth (20%)
        - Content readability (10%)

        Args:
            resource: Resource metadata dictionary or object
            content: Text content to analyze (optional)

        Returns:
            Overall quality score between 0.0 and 1.0
        """
        # Weight distribution for overall score
        METADATA_WEIGHT = 0.4
        CREDIBILITY_WEIGHT = 0.3
        DEPTH_WEIGHT = 0.2
        READABILITY_WEIGHT = 0.1

        # 1. Metadata completeness
        metadata_score = self.metadata_completeness(resource)

        # 2. Source credibility
        source = None
        if isinstance(resource, dict):
            source = resource.get("source")
        else:
            source = getattr(resource, "source", None)
        credibility_score = self.source_credibility(source)

        # 3. Content depth
        depth_score = self.content_depth(content)

        # 4. Content readability (normalized)
        readability_score = 0.0
        if content and content.strip():
            readability_metrics = self.content_readability(content)
            # Normalize reading ease to 0-1 range
            reading_ease = readability_metrics.get("reading_ease", 0.0)
            readability_score = self._normalize_reading_ease(reading_ease)

        # Compute weighted overall score
        overall = (
            METADATA_WEIGHT * metadata_score
            + CREDIBILITY_WEIGHT * credibility_score
            + DEPTH_WEIGHT * depth_score
            + READABILITY_WEIGHT * readability_score
        )

        return overall


class QualityService:
    """Quality service for computing and monitoring resource quality."""

    def __init__(self, db: Session, quality_version: str = "v2.0"):
        self.db = db
        self.quality_version = quality_version

    def get_quality_scores(
        self, resource_id: str, weights: Optional[Dict[str, float]] = None
    ) -> Optional[QualityScore]:
        """Get quality scores for a resource with caching.

        First checks cache, then computes if not found and stores in cache.

        Args:
            resource_id: ID of the resource to evaluate
            weights: Optional custom weights for dimensions (must sum to 1.0)

        Returns:
            QualityScore domain object with all dimension scores, or None if computation fails
        """
        cache_key = f"quality:{resource_id}"

        # Try cache first
        cached_scores = cache.get(cache_key)
        if cached_scores is not None:
            logger.debug(f"Cache hit for quality scores: {resource_id}")
            # Reconstruct QualityScore from cached dict
            return QualityScore(
                accuracy=cached_scores["accuracy"],
                completeness=cached_scores["completeness"],
                consistency=cached_scores["consistency"],
                timeliness=cached_scores["timeliness"],
                relevance=cached_scores["relevance"],
            )

        # Cache miss - compute quality
        logger.debug(f"Cache miss for quality scores: {resource_id}")
        quality_score = self.compute_quality(resource_id, weights)

        # Store in cache if computation succeeded
        if quality_score:
            cache_data = {
                "accuracy": quality_score.accuracy,
                "completeness": quality_score.completeness,
                "consistency": quality_score.consistency,
                "timeliness": quality_score.timeliness,
                "relevance": quality_score.relevance,
            }
            cache.set(cache_key, cache_data, ttl=1800)  # 30 minutes TTL

        return quality_score

    def compute_quality(
        self, resource_id: str, weights: Optional[Dict[str, float]] = None
    ) -> QualityScore:
        """Compute quality scores for a resource.

        Args:
            resource_id: ID of the resource to evaluate
            weights: Optional custom weights for dimensions (must sum to 1.0)

        Returns:
            QualityScore domain object with all dimension scores

        Raises:
            ValueError: If resource not found or weights are invalid
        """
        from app.database.models import Resource

        # Default weights
        if weights is None:
            weights = DEFAULT_QUALITY_WEIGHTS.copy()

        # Validate weights
        if set(weights.keys()) != {
            "accuracy",
            "completeness",
            "consistency",
            "timeliness",
            "relevance",
        }:
            raise ValueError("Weights must include all five dimensions")

        if abs(sum(weights.values()) - 1.0) > WEIGHT_SUM_TOLERANCE:
            raise ValueError("Weights must sum to 1.0")

        # Get resource
        resource = self.db.query(Resource).filter(Resource.id == resource_id).first()
        if not resource:
            raise ValueError(f"Resource {resource_id} not found")

        # Compute dimension scores using extracted methods
        accuracy = self._compute_accuracy_dimension(resource)
        completeness = self._compute_completeness_dimension(resource)
        consistency = self._compute_consistency_dimension(resource)
        timeliness = self._compute_timeliness_dimension(resource)
        relevance = self._compute_relevance_dimension(resource)

        # Create QualityScore domain object
        quality_score = QualityScore(
            accuracy=accuracy,
            completeness=completeness,
            consistency=consistency,
            timeliness=timeliness,
            relevance=relevance,
        )

        # Compute overall score using domain object
        overall = quality_score.overall_score()

        # Update resource
        self._update_resource_quality_fields(
            resource,
            accuracy,
            completeness,
            consistency,
            timeliness,
            relevance,
            overall,
            weights,
        )

        self.db.commit()

        # Emit quality.computed event
        from .handlers import emit_quality_computed

        emit_quality_computed(
            resource_id=resource_id,
            quality_score=overall,
            dimensions={
                "accuracy": accuracy,
                "completeness": completeness,
                "consistency": consistency,
                "timeliness": timeliness,
                "relevance": relevance,
            },
            computation_version=self.quality_version,
        )

        return quality_score

    def invalidate_cache(self, resource_id: str):
        """Invalidate cached quality scores for a resource.

        Args:
            resource_id: Resource ID
        """
        cache_key = f"quality:{resource_id}"
        cache.delete(cache_key)
        logger.info(f"Invalidated quality cache for resource: {resource_id}")

    def _compute_accuracy_dimension(self, resource) -> float:
        """Compute accuracy dimension score for a resource.

        Args:
            resource: Resource object to evaluate

        Returns:
            Accuracy score between 0.0 and 1.0
        """
        # Simplified accuracy calculation
        # In a real implementation, this would check data validation,
        # cross-references, citation accuracy, etc.
        return 0.7

    def _compute_completeness_dimension(self, resource) -> float:
        """Compute completeness dimension score for a resource.

        Args:
            resource: Resource object to evaluate

        Returns:
            Completeness score between 0.0 and 1.0
        """
        completeness = 0.0

        # Check presence of key metadata fields
        if resource.title:
            completeness += COMPLETENESS_FIELD_WEIGHT
        if resource.description:
            completeness += COMPLETENESS_FIELD_WEIGHT
        if resource.creator:
            completeness += COMPLETENESS_FIELD_WEIGHT
        if resource.publication_year:
            completeness += COMPLETENESS_FIELD_WEIGHT
        if resource.doi:
            completeness += COMPLETENESS_FIELD_WEIGHT

        return completeness

    def _compute_consistency_dimension(self, resource) -> float:
        """Compute consistency dimension score for a resource.

        Args:
            resource: Resource object to evaluate

        Returns:
            Consistency score between 0.0 and 1.0
        """
        # Simplified consistency calculation
        # In a real implementation, this would check for contradictions,
        # format consistency, naming consistency, etc.
        return 0.75

    def _compute_timeliness_dimension(self, resource) -> float:
        """Compute timeliness dimension score for a resource.

        Args:
            resource: Resource object to evaluate

        Returns:
            Timeliness score between 0.0 and 1.0
        """
        # Simplified timeliness calculation
        # In a real implementation, this would check publication date,
        # last update time, relevance to current date, etc.
        return 0.7

    def _compute_relevance_dimension(self, resource) -> float:
        """Compute relevance dimension score for a resource.

        Args:
            resource: Resource object to evaluate

        Returns:
            Relevance score between 0.0 and 1.0
        """
        # Simplified relevance calculation
        # In a real implementation, this would check topic relevance,
        # user context, search query matching, etc.
        return 0.7

    def _compute_weighted_overall_score(
        self,
        accuracy: float,
        completeness: float,
        consistency: float,
        timeliness: float,
        relevance: float,
        weights: Dict[str, float],
    ) -> float:
        """Compute weighted overall quality score.

        Args:
            accuracy: Accuracy dimension score
            completeness: Completeness dimension score
            consistency: Consistency dimension score
            timeliness: Timeliness dimension score
            relevance: Relevance dimension score
            weights: Weight dictionary for each dimension

        Returns:
            Weighted overall score between 0.0 and 1.0
        """
        return (
            weights["accuracy"] * accuracy
            + weights["completeness"] * completeness
            + weights["consistency"] * consistency
            + weights["timeliness"] * timeliness
            + weights["relevance"] * relevance
        )

    def _update_resource_quality_fields(
        self,
        resource,
        accuracy: float,
        completeness: float,
        consistency: float,
        timeliness: float,
        relevance: float,
        overall: float,
        weights: Dict[str, float],
    ) -> None:
        """Update resource quality fields with computed scores.

        Args:
            resource: Resource object to update
            accuracy: Accuracy dimension score
            completeness: Completeness dimension score
            consistency: Consistency dimension score
            timeliness: Timeliness dimension score
            relevance: Relevance dimension score
            overall: Overall quality score
            weights: Weight dictionary used for computation
        """
        resource.quality_accuracy = accuracy
        resource.quality_completeness = completeness
        resource.quality_consistency = consistency
        resource.quality_timeliness = timeliness
        resource.quality_relevance = relevance
        resource.quality_overall = overall
        resource.quality_score = overall
        resource.quality_weights = json.dumps(weights)
        resource.quality_computation_version = self.quality_version
        resource.quality_last_computed = datetime.now(timezone.utc)

    def monitor_quality_degradation(
        self, time_window_days: int = DEGRADATION_DEFAULT_WINDOW_DAYS
    ) -> List[Dict[str, Any]]:
        """Monitor quality degradation over time.

        Args:
            time_window_days: Number of days to look back for old quality scores

        Returns:
            List of dictionaries with degradation information for each degraded resource
        """
        from app.database.models import Resource

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=time_window_days)

        # Find resources with old quality scores
        resources = (
            self.db.query(Resource)
            .filter(
                Resource.quality_last_computed.isnot(None),
                Resource.quality_last_computed < cutoff_date,
                Resource.quality_overall.isnot(None),
            )
            .all()
        )

        degraded = []

        for resource in resources:
            old_quality = resource.quality_overall

            # Recompute quality - returns QualityScore object
            quality_score = self.compute_quality(str(resource.id))
            new_quality = quality_score.overall_score()

            # Check for degradation (>20% drop)
            quality_drop = old_quality - new_quality
            if quality_drop > DEGRADATION_THRESHOLD:
                degradation_pct = (quality_drop / old_quality) * 100.0

                # Flag for review
                resource.needs_quality_review = True
                self.db.commit()

                degraded.append(
                    {
                        "resource_id": str(resource.id),
                        "title": resource.title,
                        "old_quality": old_quality,
                        "new_quality": new_quality,
                        "degradation_pct": degradation_pct,
                    }
                )

        return degraded

    def detect_quality_outliers(
        self, batch_size: int = OUTLIER_DEFAULT_BATCH_SIZE
    ) -> int:
        """Detect quality outliers using Isolation Forest.

        Args:
            batch_size: Number of resources to process (default: 1000)

        Returns:
            Count of detected outliers

        Raises:
            ValueError: If fewer than 10 resources with quality scores exist
        """
        from app.database.models import Resource
        from sklearn.ensemble import IsolationForest
        import numpy as np

        # Query resources with quality scores in configurable batches
        resources = (
            self.db.query(Resource)
            .filter(Resource.quality_overall.isnot(None))
            .limit(batch_size)
            .all()
        )

        # Validate minimum resources for statistical validity
        if len(resources) < OUTLIER_MIN_RESOURCES:
            raise ValueError(
                f"Outlier detection requires minimum {OUTLIER_MIN_RESOURCES} resources with quality scores"
            )

        # Build feature matrix from 5 quality dimensions plus 4 summary dimensions when available
        feature_matrix = []
        resource_list = []

        for resource in resources:
            features = []

            # Add 5 quality dimensions
            features.append(
                resource.quality_accuracy
                if resource.quality_accuracy is not None
                else FEATURE_DEFAULT_VALUE
            )
            features.append(
                resource.quality_completeness
                if resource.quality_completeness is not None
                else FEATURE_DEFAULT_VALUE
            )
            features.append(
                resource.quality_consistency
                if resource.quality_consistency is not None
                else FEATURE_DEFAULT_VALUE
            )
            features.append(
                resource.quality_timeliness
                if resource.quality_timeliness is not None
                else FEATURE_DEFAULT_VALUE
            )
            features.append(
                resource.quality_relevance
                if resource.quality_relevance is not None
                else FEATURE_DEFAULT_VALUE
            )

            # Add 4 summary quality dimensions when available
            if (
                hasattr(resource, "summary_coherence")
                and resource.summary_coherence is not None
            ):
                features.append(resource.summary_coherence)
            else:
                features.append(FEATURE_DEFAULT_VALUE)  # Neutral baseline

            if (
                hasattr(resource, "summary_consistency")
                and resource.summary_consistency is not None
            ):
                features.append(resource.summary_consistency)
            else:
                features.append(FEATURE_DEFAULT_VALUE)

            if (
                hasattr(resource, "summary_fluency")
                and resource.summary_fluency is not None
            ):
                features.append(resource.summary_fluency)
            else:
                features.append(FEATURE_DEFAULT_VALUE)

            if (
                hasattr(resource, "summary_relevance")
                and resource.summary_relevance is not None
            ):
                features.append(resource.summary_relevance)
            else:
                features.append(FEATURE_DEFAULT_VALUE)

            feature_matrix.append(features)
            resource_list.append(resource)

        # Convert to numpy array
        X = np.array(feature_matrix)

        # Train Isolation Forest with configured parameters
        iso_forest = IsolationForest(
            contamination=OUTLIER_CONTAMINATION,
            n_estimators=OUTLIER_N_ESTIMATORS,
            random_state=OUTLIER_RANDOM_STATE,
        )

        # Fit and predict
        predictions = iso_forest.fit_predict(X)

        # Predict anomaly scores for all resources (lower scores = more anomalous)
        anomaly_scores = iso_forest.score_samples(X)

        # Identify outliers where prediction equals -1
        outlier_count = 0

        for i, (resource, prediction, anomaly_score) in enumerate(
            zip(resource_list, predictions, anomaly_scores)
        ):
            if prediction == -1:
                # Call _identify_outlier_reasons for each outlier
                reasons = self._identify_outlier_reasons(resource)

                # Update resources with is_quality_outlier flag, outlier_score, outlier_reasons JSON, and needs_quality_review flag
                resource.is_quality_outlier = True
                resource.outlier_score = float(anomaly_score)
                resource.outlier_reasons = json.dumps(reasons)
                resource.needs_quality_review = True

                # Emit quality.outlier_detected event
                from .handlers import emit_quality_outlier_detected

                emit_quality_outlier_detected(
                    resource_id=str(resource.id),
                    quality_score=resource.quality_overall or 0.0,
                    outlier_score=float(anomaly_score),
                    dimensions={
                        "accuracy": resource.quality_accuracy or 0.0,
                        "completeness": resource.quality_completeness or 0.0,
                        "consistency": resource.quality_consistency or 0.0,
                        "timeliness": resource.quality_timeliness or 0.0,
                        "relevance": resource.quality_relevance or 0.0,
                    },
                    reason=", ".join(reasons) if reasons else "anomalous_pattern",
                )

                outlier_count += 1
            else:
                # Clear outlier flags for non-outliers
                resource.is_quality_outlier = False
                resource.outlier_score = float(anomaly_score)
                resource.outlier_reasons = None

        # Commit updates to database
        self.db.commit()

        # Return count of detected outliers
        return outlier_count

    def _identify_outlier_reasons(self, resource) -> List[str]:
        """Identify reasons why a resource is an outlier."""
        reasons = []

        # Check quality dimensions
        if (
            hasattr(resource, "quality_accuracy")
            and resource.quality_accuracy
            and resource.quality_accuracy < OUTLIER_THRESHOLD_LOW
        ):
            reasons.append("low_accuracy")
        if (
            hasattr(resource, "quality_completeness")
            and resource.quality_completeness
            and resource.quality_completeness < OUTLIER_THRESHOLD_LOW
        ):
            reasons.append("low_completeness")
        if (
            hasattr(resource, "quality_consistency")
            and resource.quality_consistency
            and resource.quality_consistency < OUTLIER_THRESHOLD_LOW
        ):
            reasons.append("low_consistency")
        if (
            hasattr(resource, "quality_timeliness")
            and resource.quality_timeliness
            and resource.quality_timeliness < OUTLIER_THRESHOLD_LOW
        ):
            reasons.append("low_timeliness")
        if (
            hasattr(resource, "quality_relevance")
            and resource.quality_relevance
            and resource.quality_relevance < OUTLIER_THRESHOLD_LOW
        ):
            reasons.append("low_relevance")

        # Check summary quality dimensions
        if (
            hasattr(resource, "summary_coherence")
            and resource.summary_coherence
            and resource.summary_coherence < OUTLIER_THRESHOLD_LOW
        ):
            reasons.append("low_summary_coherence")
        if (
            hasattr(resource, "summary_consistency")
            and resource.summary_consistency
            and resource.summary_consistency < OUTLIER_THRESHOLD_LOW
        ):
            reasons.append("low_summary_consistency")
        if (
            hasattr(resource, "summary_fluency")
            and resource.summary_fluency
            and resource.summary_fluency < OUTLIER_THRESHOLD_LOW
        ):
            reasons.append("low_summary_fluency")
        if (
            hasattr(resource, "summary_relevance")
            and resource.summary_relevance
            and resource.summary_relevance < OUTLIER_THRESHOLD_LOW
        ):
            reasons.append("low_summary_relevance")

        return reasons
