"""
Recommendation domain objects for Neo Alexandria.

This module contains domain value objects for recommendation systems,
with validation and business logic for scoring and ranking.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict, fields
from typing import Any, Dict, Optional, Type, TypeVar
import json


T = TypeVar("T", bound="BaseDomainObject")


class BaseDomainObject(ABC):
    """Abstract base class for domain objects."""

    def to_dict(self) -> Dict[str, Any]:
        """Convert domain object to dictionary."""
        if hasattr(self, "__dataclass_fields__"):
            return asdict(self)
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    @classmethod
    def from_dict(cls: Type[T], data: Dict[str, Any]) -> T:
        """Create domain object from dictionary."""
        if hasattr(cls, "__dataclass_fields__"):
            field_names = {f.name for f in fields(cls)}
            filtered_data = {k: v for k, v in data.items() if k in field_names}
            return cls(**filtered_data)
        return cls(**data)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)

    @abstractmethod
    def validate(self) -> None:
        """Validate domain object state."""
        pass


@dataclass
class ValueObject(BaseDomainObject):
    """Base class for immutable value objects."""

    def __post_init__(self):
        """Validate after initialization."""
        self.validate()

    def validate(self) -> None:
        """Default validation - override in subclasses."""
        pass


def validate_range(
    value: float, min_value: float, max_value: float, field_name: str
) -> None:
    """Validate value is within range."""
    if not min_value <= value <= max_value:
        raise ValueError(
            f"{field_name} must be between {min_value} and {max_value}, got {value}"
        )


def validate_non_empty(value: str, field_name: str) -> None:
    """Validate string is not empty."""
    if not value or not value.strip():
        raise ValueError(f"{field_name} cannot be empty")


@dataclass
class RecommendationScore(ValueObject):
    """
    Recommendation score with confidence and ranking metadata.

    Attributes:
        score: Relevance score (0.0-1.0, higher is better)
        confidence: Confidence in the recommendation (0.0-1.0)
        rank: Ranking position (1-based, lower is better)
    """

    score: float
    confidence: float
    rank: int

    def validate(self) -> None:
        """Validate recommendation score attributes."""
        validate_range(self.score, 0.0, 1.0, "score")
        validate_range(self.confidence, 0.0, 1.0, "confidence")
        if self.rank < 1:
            raise ValueError(f"rank must be positive (1-based), got {self.rank}")

    def is_high_confidence(self, threshold: float = 0.8) -> bool:
        """Check if recommendation has high confidence."""
        return self.confidence >= threshold

    def is_high_score(self, threshold: float = 0.7) -> bool:
        """Check if recommendation has high relevance score."""
        return self.score >= threshold

    def is_top_ranked(self, top_k: int = 5) -> bool:
        """Check if recommendation is in top K positions."""
        return self.rank <= top_k

    def combined_quality(self) -> float:
        """Calculate combined quality metric (70% score, 30% confidence)."""
        return 0.7 * self.score + 0.3 * self.confidence

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API compatibility."""
        return {
            "score": self.score,
            "confidence": self.confidence,
            "rank": self.rank,
            "combined_quality": self.combined_quality(),
        }


@dataclass
class Recommendation(ValueObject):
    """
    Recommendation value object with resource and scoring information.

    Attributes:
        resource_id: Unique identifier of the recommended resource
        user_id: Unique identifier of the user receiving the recommendation
        recommendation_score: Scoring information for this recommendation
        strategy: Strategy used to generate this recommendation
        reason: Optional explanation for why this was recommended
        metadata: Additional metadata about the recommendation
    """

    resource_id: str
    user_id: str
    recommendation_score: RecommendationScore
    strategy: str = "unknown"
    reason: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Initialize metadata dict if None and validate."""
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})
        super().__post_init__()

    def validate(self) -> None:
        """Validate recommendation attributes."""
        validate_non_empty(self.resource_id, "resource_id")
        validate_non_empty(self.user_id, "user_id")
        self.recommendation_score.validate()

    def get_score(self) -> float:
        """Get the relevance score."""
        return self.recommendation_score.score

    def get_confidence(self) -> float:
        """Get the confidence score."""
        return self.recommendation_score.confidence

    def get_rank(self) -> int:
        """Get the ranking position."""
        return self.recommendation_score.rank

    def is_high_quality(
        self, score_threshold: float = 0.7, confidence_threshold: float = 0.8
    ) -> bool:
        """Check if recommendation meets high quality criteria."""
        return self.recommendation_score.is_high_score(
            score_threshold
        ) and self.recommendation_score.is_high_confidence(confidence_threshold)

    def is_top_recommendation(self, top_k: int = 5) -> bool:
        """Check if this is a top-ranked recommendation."""
        return self.recommendation_score.is_top_ranked(top_k)

    def __lt__(self, other: "Recommendation") -> bool:
        """Compare recommendations for sorting (lower rank is better)."""
        if not isinstance(other, Recommendation):
            return NotImplemented
        return self.get_rank() < other.get_rank()

    def get(self, key: str, default: Any = None) -> Any:
        """Get attribute value by key (dict-like interface)."""
        key_mapping = {
            "score": "get_score",
            "confidence": "get_confidence",
            "rank": "get_rank",
        }
        if key in key_mapping:
            return getattr(self, key_mapping[key])()
        return getattr(self, key, default)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API compatibility."""
        return {
            "resource_id": self.resource_id,
            "user_id": self.user_id,
            "score": self.get_score(),
            "confidence": self.get_confidence(),
            "rank": self.get_rank(),
            "strategy": self.strategy,
            "reason": self.reason,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Recommendation":
        """Create recommendation from dictionary."""
        if "recommendation_score" in data:
            score_data = data["recommendation_score"]
            rec_score = RecommendationScore(
                score=score_data["score"],
                confidence=score_data["confidence"],
                rank=score_data["rank"],
            )
        else:
            rec_score = RecommendationScore(
                score=data["score"], confidence=data["confidence"], rank=data["rank"]
            )
        return cls(
            resource_id=data["resource_id"],
            user_id=data["user_id"],
            recommendation_score=rec_score,
            strategy=data.get("strategy", "unknown"),
            reason=data.get("reason"),
            metadata=data.get("metadata"),
        )
