"""
Tests for Summarization Evaluator Service

Tests the implementation of:
- SummarizationEvaluator class initialization
- G-Eval metrics with Flan-T5-Large (with mocked pipeline)
- FineSurE metrics
- BERTScore metric
- evaluate_summary method
- Fallback behavior when models unavailable
"""

import pytest
from unittest.mock import Mock, patch
from sqlalchemy.orm import Session

from app.modules.quality.evaluator import SummarizationEvaluator
from app.database.models import Resource

# Check if transformers is available for mocking
try:
    import transformers

    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False


class TestSummarizationEvaluatorInit:
    """Test SummarizationEvaluator initialization."""

    def test_init_without_api_key(self, db_session: Session):
        """Test initialization without any special configuration."""
        evaluator = SummarizationEvaluator(db=db_session)

        assert evaluator.db == db_session
        assert evaluator.model_name == "google/flan-t5-large"
        assert evaluator.openai_available is False

    def test_init_with_custom_model(self, db_session: Session):
        """Test initialization with custom model name."""
        evaluator = SummarizationEvaluator(
            db=db_session, model_name="google/flan-t5-xl"
        )

        assert evaluator.db == db_session
        assert evaluator.model_name == "google/flan-t5-xl"

    def test_summary_weights_sum_to_one(self, db_session: Session):
        """Test that summary weights sum to 1.0."""
        evaluator = SummarizationEvaluator(db=db_session)

        total_weight = sum(evaluator.SUMMARY_WEIGHTS.values())
        assert abs(total_weight - 1.0) < 0.001


class TestGEvalMetrics:
    """Test G-Eval metrics with mocked Flan-T5 pipeline."""

    @pytest.mark.skipif(
        not TRANSFORMERS_AVAILABLE, reason="transformers package not installed"
    )
    def test_g_eval_coherence_with_model(self, db_session: Session):
        """Test G-Eval coherence with mocked HuggingFace pipeline."""
        evaluator = SummarizationEvaluator(db=db_session)
        evaluator.hf_available = True

        # Mock the pipeline
        mock_pipeline = Mock()
        mock_pipeline.return_value = [{"generated_text": "4"}]
        evaluator._hf_pipeline = mock_pipeline

        summary = "This is a coherent summary."
        score = evaluator.g_eval_coherence(summary)

        # Score should be normalized: (4 - 1) / 4 = 0.75
        assert score == 0.75
        assert 0.0 <= score <= 1.0

    def test_g_eval_coherence_fallback(self, db_session: Session):
        """Test G-Eval coherence fallback when model unavailable."""
        evaluator = SummarizationEvaluator(db=db_session)
        evaluator.hf_available = False

        summary = "This is a test summary."
        score = evaluator.g_eval_coherence(summary)

        # Should return fallback score
        assert score == 0.7

    @pytest.mark.skipif(
        not TRANSFORMERS_AVAILABLE, reason="transformers package not installed"
    )
    def test_g_eval_consistency_with_model(self, db_session: Session):
        """Test G-Eval consistency with mocked HuggingFace pipeline."""
        evaluator = SummarizationEvaluator(db=db_session)
        evaluator.hf_available = True

        # Mock the pipeline
        mock_pipeline = Mock()
        mock_pipeline.return_value = [{"generated_text": "5"}]
        evaluator._hf_pipeline = mock_pipeline

        summary = "Machine learning is AI."
        reference = "Machine learning is a field of artificial intelligence."
        score = evaluator.g_eval_consistency(summary, reference)

        # Score should be normalized: (5 - 1) / 4 = 1.0
        assert score == 1.0

    def test_g_eval_consistency_fallback(self, db_session: Session):
        """Test G-Eval consistency fallback."""
        evaluator = SummarizationEvaluator(db=db_session)
        evaluator.hf_available = False

        summary = "Test summary."
        reference = "Test reference."
        score = evaluator.g_eval_consistency(summary, reference)

        assert score == 0.7

    @pytest.mark.skipif(
        not TRANSFORMERS_AVAILABLE, reason="transformers package not installed"
    )
    def test_g_eval_fluency_with_model(self, db_session: Session):
        """Test G-Eval fluency with mocked HuggingFace pipeline."""
        evaluator = SummarizationEvaluator(db=db_session)
        evaluator.hf_available = True

        # Mock the pipeline
        mock_pipeline = Mock()
        mock_pipeline.return_value = [{"generated_text": "3"}]
        evaluator._hf_pipeline = mock_pipeline

        summary = "This summary has good fluency."
        score = evaluator.g_eval_fluency(summary)

        # Score should be normalized: (3 - 1) / 4 = 0.5
        assert score == 0.5

    def test_g_eval_fluency_fallback(self, db_session: Session):
        """Test G-Eval fluency fallback."""
        evaluator = SummarizationEvaluator(db=db_session)
        evaluator.hf_available = False

        summary = "Test summary."
        score = evaluator.g_eval_fluency(summary)

        assert score == 0.7

    @pytest.mark.skipif(
        not TRANSFORMERS_AVAILABLE, reason="transformers package not installed"
    )
    def test_g_eval_relevance_with_model(self, db_session: Session):
        """Test G-Eval relevance with mocked HuggingFace pipeline."""
        evaluator = SummarizationEvaluator(db=db_session)
        evaluator.hf_available = True

        # Mock the pipeline
        mock_pipeline = Mock()
        mock_pipeline.return_value = [{"generated_text": "4"}]
        evaluator._hf_pipeline = mock_pipeline

        summary = "Key information captured."
        reference = "This document contains key information about the topic."
        score = evaluator.g_eval_relevance(summary, reference)

        # Score should be normalized: (4 - 1) / 4 = 0.75
        assert score == 0.75

    def test_g_eval_relevance_fallback(self, db_session: Session):
        """Test G-Eval relevance fallback."""
        evaluator = SummarizationEvaluator(db=db_session)
        evaluator.hf_available = False

        summary = "Test summary."
        reference = "Test reference."
        score = evaluator.g_eval_relevance(summary, reference)

        assert score == 0.7

    @pytest.mark.skipif(
        not TRANSFORMERS_AVAILABLE, reason="transformers package not installed"
    )
    def test_g_eval_error_handling(self, db_session: Session):
        """Test G-Eval error handling when pipeline fails."""
        evaluator = SummarizationEvaluator(db=db_session)
        evaluator.hf_available = True

        # Mock the pipeline to raise an error
        mock_pipeline = Mock()
        mock_pipeline.side_effect = Exception("Pipeline error")
        evaluator._hf_pipeline = mock_pipeline

        summary = "Test summary."
        score = evaluator.g_eval_coherence(summary)

        # Should return fallback score on error
        assert score == 0.7


class TestFineSurEMetrics:
    """Test FineSurE metrics."""

    def test_completeness_good_overlap(self, db_session: Session):
        """Test completeness with good term overlap."""
        evaluator = SummarizationEvaluator(db=db_session)

        summary = "machine learning artificial intelligence statistical techniques"
        reference = "Machine learning is a field of artificial intelligence that uses statistical techniques."

        score = evaluator.finesure_completeness(summary, reference)

        assert 0.0 <= score <= 1.0
        assert score > 0.5  # Should have decent overlap

    def test_completeness_no_overlap(self, db_session: Session):
        """Test completeness with no term overlap."""
        evaluator = SummarizationEvaluator(db=db_session)

        summary = "xyz abc def"
        reference = "completely different words here"

        score = evaluator.finesure_completeness(summary, reference)

        assert score == 0.0

    def test_completeness_empty_inputs(self, db_session: Session):
        """Test completeness with empty inputs."""
        evaluator = SummarizationEvaluator(db=db_session)

        assert evaluator.finesure_completeness("", "reference") == 0.0
        assert evaluator.finesure_completeness("summary", "") == 0.0
        assert evaluator.finesure_completeness("", "") == 0.0

    def test_completeness_stopwords_removed(self, db_session: Session):
        """Test that stopwords are removed from completeness calculation."""
        evaluator = SummarizationEvaluator(db=db_session)

        # Summary with only stopwords
        summary = "the a an and or but is are"
        reference = "the machine learning field uses statistical techniques"

        score = evaluator.finesure_completeness(summary, reference)

        # Should be 0 since all summary words are stopwords
        assert score == 0.0

    def test_conciseness_optimal_range(self, db_session: Session):
        """Test conciseness with optimal compression ratio (5-15%)."""
        evaluator = SummarizationEvaluator(db=db_session)

        # 10% compression (optimal)
        summary = "A" * 100
        reference = "B" * 1000

        score = evaluator.finesure_conciseness(summary, reference)

        assert score == 1.0

    def test_conciseness_too_short(self, db_session: Session):
        """Test conciseness with too short summary (< 5%)."""
        evaluator = SummarizationEvaluator(db=db_session)

        # 2% compression (too short)
        summary = "A" * 20
        reference = "B" * 1000

        score = evaluator.finesure_conciseness(summary, reference)

        assert 0.0 < score < 1.0
        assert abs(score - 0.4) < 0.01  # Should be 0.02 / 0.05 = 0.4

    def test_conciseness_too_long(self, db_session: Session):
        """Test conciseness with too long summary (> 15%)."""
        evaluator = SummarizationEvaluator(db=db_session)

        # 50% compression (too long)
        summary = "A" * 500
        reference = "B" * 1000

        score = evaluator.finesure_conciseness(summary, reference)

        assert score == 0.0

    def test_conciseness_empty_inputs(self, db_session: Session):
        """Test conciseness with empty inputs."""
        evaluator = SummarizationEvaluator(db=db_session)

        assert evaluator.finesure_conciseness("", "reference") == 0.0
        assert evaluator.finesure_conciseness("summary", "") == 0.0


class TestBERTScore:
    """Test BERTScore metric."""

    def test_bertscore_calculation(self, db_session: Session):
        """Test BERTScore calculation with mocked library."""
        pytest.importorskip(
            "bert_score", reason="bert_score library not installed"
        )
        evaluator = SummarizationEvaluator(db=db_session)

        with patch("bert_score.score") as mock_bert_score:
            # Mock BERTScore return values
            mock_f1 = Mock()
            mock_f1.item.return_value = 0.85
            mock_bert_score.return_value = (Mock(), Mock(), [mock_f1])

            summary = "Machine learning is AI."
            reference = "Machine learning is artificial intelligence."

            score = evaluator.bertscore_f1(summary, reference)

            assert score == 0.85
            assert 0.0 <= score <= 1.0

    def test_bertscore_fallback_on_import_error(self, db_session: Session):
        """Test BERTScore fallback when library not available."""
        evaluator = SummarizationEvaluator(db=db_session)

        with patch("builtins.__import__", side_effect=ImportError):
            summary = "Test summary."
            reference = "Test reference."

            score = evaluator.bertscore_f1(summary, reference)

            # Should return fallback score
            assert score == 0.5

    def test_bertscore_empty_inputs(self, db_session: Session):
        """Test BERTScore with empty inputs."""
        evaluator = SummarizationEvaluator(db=db_session)

        assert evaluator.bertscore_f1("", "reference") == 0.5
        assert evaluator.bertscore_f1("summary", "") == 0.5

    def test_bertscore_error_handling(self, db_session: Session):
        """Test BERTScore error handling."""
        pytest.importorskip(
            "bert_score", reason="bert_score library not installed"
        )
        evaluator = SummarizationEvaluator(db=db_session)

        with patch("bert_score.score", side_effect=Exception("BERTScore error")):
            summary = "Test summary."
            reference = "Test reference."

            score = evaluator.bertscore_f1(summary, reference)

            # Should return fallback score on error
            assert score == 0.5


class TestEvaluateSummary:
    """Test evaluate_summary method."""

    def test_evaluate_summary_without_g_eval(
        self, db_session: Session, sample_resource: Resource
    ):
        """Test evaluate_summary without G-Eval (fallback scores)."""
        evaluator = SummarizationEvaluator(db=db_session)
        evaluator.hf_available = False  # Force fallback

        result = evaluator.evaluate_summary(
            resource_id=str(sample_resource.id), use_g_eval=False
        )

        # Check all metrics are present
        assert "coherence" in result
        assert "consistency" in result
        assert "fluency" in result
        assert "relevance" in result
        assert "completeness" in result
        assert "conciseness" in result
        assert "bertscore" in result
        assert "overall" in result

        # Check all scores are in valid range
        for metric, score in result.items():
            if metric != "error":
                assert 0.0 <= score <= 1.0, f"{metric} score out of range: {score}"

        # Check G-Eval metrics use fallback
        assert result["coherence"] == 0.7
        assert result["consistency"] == 0.7
        assert result["fluency"] == 0.7
        assert result["relevance"] == 0.7

    @pytest.mark.skipif(
        not TRANSFORMERS_AVAILABLE, reason="transformers package not installed"
    )
    def test_evaluate_summary_with_g_eval(
        self, db_session: Session, sample_resource: Resource
    ):
        """Test evaluate_summary with G-Eval enabled."""
        evaluator = SummarizationEvaluator(db=db_session)
        evaluator.hf_available = True

        # Mock the pipeline
        mock_pipeline = Mock()
        mock_pipeline.return_value = [{"generated_text": "4"}]
        evaluator._hf_pipeline = mock_pipeline

        result = evaluator.evaluate_summary(
            resource_id=str(sample_resource.id), use_g_eval=True
        )

        # Check G-Eval metrics are not fallback values
        assert result["coherence"] == 0.75  # (4-1)/4
        assert result["consistency"] == 0.75
        assert result["fluency"] == 0.75
        assert result["relevance"] == 0.75

    def test_evaluate_summary_updates_resource(
        self, db_session: Session, sample_resource: Resource
    ):
        """Test that evaluate_summary updates resource fields."""
        evaluator = SummarizationEvaluator(db=db_session)

        result = evaluator.evaluate_summary(
            resource_id=str(sample_resource.id), use_g_eval=False
        )

        # Refresh resource from database
        db_session.refresh(sample_resource)

        # Check all fields are updated
        assert sample_resource.summary_coherence == result["coherence"]
        assert sample_resource.summary_consistency == result["consistency"]
        assert sample_resource.summary_fluency == result["fluency"]
        assert sample_resource.summary_relevance == result["relevance"]
        assert sample_resource.summary_completeness == result["completeness"]
        assert sample_resource.summary_conciseness == result["conciseness"]
        assert sample_resource.summary_bertscore == result["bertscore"]
        assert sample_resource.summary_quality_overall == result["overall"]

    def test_evaluate_summary_composite_score(
        self, db_session: Session, sample_resource: Resource
    ):
        """Test that composite score is calculated correctly."""
        evaluator = SummarizationEvaluator(db=db_session)

        result = evaluator.evaluate_summary(
            resource_id=str(sample_resource.id), use_g_eval=False
        )

        # Calculate expected composite score
        expected_overall = (
            evaluator.SUMMARY_WEIGHTS["coherence"] * result["coherence"]
            + evaluator.SUMMARY_WEIGHTS["consistency"] * result["consistency"]
            + evaluator.SUMMARY_WEIGHTS["fluency"] * result["fluency"]
            + evaluator.SUMMARY_WEIGHTS["relevance"] * result["relevance"]
            + evaluator.SUMMARY_WEIGHTS["completeness"] * result["completeness"]
            + evaluator.SUMMARY_WEIGHTS["conciseness"] * result["conciseness"]
            + evaluator.SUMMARY_WEIGHTS["bertscore"] * result["bertscore"]
        )

        assert abs(result["overall"] - expected_overall) < 0.001

    def test_evaluate_summary_resource_not_found(self, db_session: Session):
        """Test evaluate_summary with non-existent resource."""
        evaluator = SummarizationEvaluator(db=db_session)

        with pytest.raises(ValueError, match="not found"):
            evaluator.evaluate_summary(
                resource_id="00000000-0000-0000-0000-000000000000", use_g_eval=False
            )

    def test_evaluate_summary_no_summary(self, db_session: Session):
        """Test evaluate_summary with resource that has no summary."""
        from app.database.models import Resource
        import uuid

        # Create resource without description (summary)
        resource = Resource(id=uuid.uuid4(), title="Test Resource", description=None)
        db_session.add(resource)
        db_session.commit()

        evaluator = SummarizationEvaluator(db=db_session)

        result = evaluator.evaluate_summary(
            resource_id=str(resource.id), use_g_eval=False
        )

        assert "error" in result
        assert "no summary" in result["error"].lower()


# Fixtures


@pytest.fixture
def sample_resource(db_session: Session) -> Resource:
    """Create a sample resource for testing."""
    import uuid
    from app.database.models import Resource

    resource = Resource(
        id=uuid.uuid4(),
        title="Machine Learning Overview",
        description="Machine learning is a field of artificial intelligence that uses statistical techniques to enable computers to learn from data.",
    )
    db_session.add(resource)
    db_session.commit()

    return resource
