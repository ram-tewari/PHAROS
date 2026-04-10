"""
Quality domain objects for Neo Alexandria.

This module contains domain value objects for quality assessment,
with validation and business logic for multi-dimensional quality scoring.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict, fields
from typing import Any, Dict, Type, TypeVar
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

    @classmethod
    def from_json(cls: Type[T], json_str: str) -> T:
        """Create from JSON string."""
        return cls.from_dict(json.loads(json_str))

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


# Quality dimension weights for overall score calculation
ACCURACY_WEIGHT = 0.3
COMPLETENESS_WEIGHT = 0.2
CONSISTENCY_WEIGHT = 0.2
TIMELINESS_WEIGHT = 0.15
RELEVANCE_WEIGHT = 0.15

# Quality thresholds
HIGH_QUALITY_THRESHOLD = 0.7
MEDIUM_QUALITY_THRESHOLD = 0.5


@dataclass
class QualityScore(ValueObject):
    """
    Multi-dimensional quality score value object.

    Represents quality assessment across five dimensions: accuracy,
    completeness, consistency, timeliness, and relevance.
    """

    accuracy: float
    completeness: float
    consistency: float
    timeliness: float
    relevance: float

    def validate(self) -> None:
        """Validate all quality dimension scores."""
        validate_range(self.accuracy, 0.0, 1.0, "accuracy")
        validate_range(self.completeness, 0.0, 1.0, "completeness")
        validate_range(self.consistency, 0.0, 1.0, "consistency")
        validate_range(self.timeliness, 0.0, 1.0, "timeliness")
        validate_range(self.relevance, 0.0, 1.0, "relevance")

    def overall_score(self) -> float:
        """Compute weighted overall quality score."""
        return (
            ACCURACY_WEIGHT * self.accuracy
            + COMPLETENESS_WEIGHT * self.completeness
            + CONSISTENCY_WEIGHT * self.consistency
            + TIMELINESS_WEIGHT * self.timeliness
            + RELEVANCE_WEIGHT * self.relevance
        )

    def is_high_quality(self, threshold: float = HIGH_QUALITY_THRESHOLD) -> bool:
        """Check if overall quality meets high quality threshold."""
        return self.overall_score() >= threshold

    def is_low_quality(self, threshold: float = MEDIUM_QUALITY_THRESHOLD) -> bool:
        """Check if overall quality is below medium threshold."""
        return self.overall_score() < threshold

    def get_quality_level(self) -> str:
        """Get quality level as string classification."""
        if self.is_high_quality():
            return "high"
        elif self.is_low_quality():
            return "low"
        return "medium"

    def get_weakest_dimension(self) -> str:
        """Identify the dimension with the lowest score."""
        dimensions = {
            "accuracy": self.accuracy,
            "completeness": self.completeness,
            "consistency": self.consistency,
            "timeliness": self.timeliness,
            "relevance": self.relevance,
        }
        return min(dimensions, key=dimensions.get)

    def get_dimension_scores(self) -> Dict[str, float]:
        """Get all dimension scores as a dictionary."""
        return {
            "accuracy": self.accuracy,
            "completeness": self.completeness,
            "consistency": self.consistency,
            "timeliness": self.timeliness,
            "relevance": self.relevance,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert quality score to dictionary for API compatibility."""
        return {
            "accuracy": self.accuracy,
            "completeness": self.completeness,
            "consistency": self.consistency,
            "timeliness": self.timeliness,
            "relevance": self.relevance,
            "overall_score": self.overall_score(),
            "quality_level": self.get_quality_level(),
        }

    def get(self, key: str, default: Any = None) -> Any:
        """Get dimension score by key (dict-like interface)."""
        if key == "overall_score":
            return self.overall_score()
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:
        """Get dimension score by key (dict-like interface)."""
        if key == "overall_score":
            return self.overall_score()
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(f"'{key}' is not a valid quality dimension")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QualityScore":
        """Create quality score from dictionary."""
        return cls(
            accuracy=data["accuracy"],
            completeness=data["completeness"],
            consistency=data["consistency"],
            timeliness=data["timeliness"],
            relevance=data["relevance"],
        )
