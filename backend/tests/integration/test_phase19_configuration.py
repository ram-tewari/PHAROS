"""
Unit tests for Phase 19 configuration management.

Tests MODE-aware configuration, environment variable validation,
and requirements file inheritance strategy.

Requirements tested:
- 7.1: MODE environment variable support
- 7.2: CLOUD mode excludes torch
- 7.3: EDGE mode verifies CUDA
- 7.6: Environment variable validation
- 7.7: Requirements file validation
- 7.8: Base + extension strategy
"""

import os
import re

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


@pytest.fixture(autouse=True)
def setup_phase19_env(monkeypatch):
    """Setup Phase 19 environment for all tests."""
    # Enable Phase 19 validation
    monkeypatch.setenv("PHASE19_ENABLED", "true")

    # Set minimal required env vars
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://test.upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token")
    monkeypatch.setenv("PHAROS_ADMIN_TOKEN", "test-admin-token")

    # These tests exercise the real, cached get_settings() and its validation;
    # the suite-wide conftest replaces it with a fixed test Settings.
    import app.config.settings as settings_module

    real = settings_module._real_get_settings
    monkeypatch.setattr(settings_module, "get_settings", real)
    real.cache_clear()

    yield

    real.cache_clear()


class TestModeConfiguration:
    """Test MODE environment variable and mode-specific behavior."""

    def test_cloud_mode_does_not_import_torch(self, monkeypatch):
        """
        Test that MODE=CLOUD doesn't import torch modules.

        Validates: Requirement 7.2
        """
        # Set MODE to CLOUD
        monkeypatch.setenv("MODE", "CLOUD")

        from app.config.settings import get_settings

        # In CLOUD mode, settings should initialize without importing torch
        settings = get_settings()
        assert settings.MODE == "CLOUD"

        # Verify torch is not in sys.modules (wasn't imported)
        import sys

        assert "torch" not in sys.modules, "CLOUD mode should not import torch"

    def test_edge_mode_verifies_cuda(self, monkeypatch):
        """
        Test that MODE=EDGE verifies CUDA and logs GPU info.

        Validates: Requirement 7.3
        """
        # Set MODE to EDGE
        monkeypatch.setenv("MODE", "EDGE")

        # Set required EDGE credentials
        monkeypatch.setenv("QDRANT_URL", "https://test.qdrant.io")
        monkeypatch.setenv("QDRANT_API_KEY", "test-api-key")

        from app.config.settings import get_settings

        # Mock torch module
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.get_device_name.return_value = "NVIDIA RTX 4070"
        mock_torch.cuda.get_device_properties.return_value.total_memory = 16e9
        mock_torch.version.cuda = "12.1"

        with patch.dict("sys.modules", {"torch": mock_torch}):
            settings = get_settings()
            assert settings.MODE == "EDGE"
            assert settings.DEVICE == "cuda"

            # Verify CUDA detection was called
            mock_torch.cuda.is_available.assert_called_once()

    def test_edge_mode_cpu_fallback(self, monkeypatch):
        """
        Test that MODE=EDGE falls back to CPU when CUDA unavailable.

        Validates: Requirement 7.3
        """
        # Set MODE to EDGE
        monkeypatch.setenv("MODE", "EDGE")

        # Set required EDGE credentials
        monkeypatch.setenv("QDRANT_URL", "https://test.qdrant.io")
        monkeypatch.setenv("QDRANT_API_KEY", "test-api-key")

        from app.config.settings import get_settings

        # Mock torch module with no CUDA
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False

        with patch.dict("sys.modules", {"torch": mock_torch}):
            settings = get_settings()
            assert settings.MODE == "EDGE"
            assert settings.DEVICE == "cpu"

    def test_edge_mode_without_torch_raises_error(self, monkeypatch):
        """
        MODE=EDGE without torch installed fails at settings load with an install hint.

        Validates: Requirement 7.3
        """
        import importlib.util

        if importlib.util.find_spec("torch") is not None:
            pytest.skip("needs an environment without torch")
        monkeypatch.setenv("MODE", "EDGE")

        from app.config.settings import get_settings

        with pytest.raises(ImportError, match="MODE=EDGE requires torch"):
            get_settings()


class TestEnvironmentVariableValidation:
    """Test environment variable validation on startup."""

    def test_missing_upstash_url_raises_error(self, monkeypatch):
        """
        Test that missing UPSTASH_REDIS_REST_URL raises validation error.

        Validates: Requirement 7.6
        """
        # Clear required env vars
        monkeypatch.delenv("UPSTASH_REDIS_REST_URL")

        from app.config.settings import get_settings

        with pytest.raises(ValueError, match="UPSTASH_REDIS_REST_URL must be set"):
            get_settings()

    def test_missing_upstash_token_raises_error(self, monkeypatch):
        """
        Test that missing UPSTASH_REDIS_REST_TOKEN raises validation error.

        Validates: Requirement 7.6
        """
        # Clear token
        monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN")

        from app.config.settings import get_settings

        with pytest.raises(ValueError, match="UPSTASH_REDIS_REST_TOKEN must be set"):
            get_settings()

    def test_missing_pharos_admin_token_raises_error(self, monkeypatch):
        """
        Test that missing PHAROS_ADMIN_TOKEN raises validation error.

        Validates: Requirement 7.6, 2.8
        """
        # Clear admin token
        monkeypatch.delenv("PHAROS_ADMIN_TOKEN")

        from app.config.settings import get_settings

        with pytest.raises(ValueError, match="PHAROS_ADMIN_TOKEN must be set"):
            get_settings()

    def test_invalid_mode_raises_error(self, monkeypatch):
        """
        Test that invalid MODE value raises validation error.

        Validates: Requirement 7.1
        """
        # Set invalid MODE
        monkeypatch.setenv("MODE", "INVALID")

        from app.config.settings import get_settings

        # The error happens during Settings initialization, not validation
        # Pydantic will raise a validation error for invalid Literal value
        with pytest.raises(
            (ValueError, Exception)
        ):  # Accept either ValueError or pydantic ValidationError
            get_settings()

    def test_invalid_queue_size_raises_error(self, monkeypatch):
        """
        Test that invalid MAX_QUEUE_SIZE raises validation error.

        Validates: Requirement 7.6
        """
        # Set invalid queue size
        monkeypatch.setenv("MAX_QUEUE_SIZE", "0")

        from app.config.settings import get_settings

        with pytest.raises(ValueError, match="MAX_QUEUE_SIZE must be positive"):
            get_settings()

    def test_cloud_mode_https_validation(self, monkeypatch):
        """
        Test that CLOUD mode validates HTTPS URLs.

        Validates: Requirement 11.3
        """
        # Set MODE to CLOUD with non-HTTPS URL
        monkeypatch.setenv("MODE", "CLOUD")
        monkeypatch.setenv("QDRANT_URL", "http://insecure.qdrant.io")  # HTTP not HTTPS

        from app.config.settings import get_settings

        with pytest.raises(ValueError, match="QDRANT_URL must use HTTPS"):
            get_settings()

    def test_edge_mode_requires_qdrant_credentials(self, monkeypatch):
        """
        Test that EDGE mode requires Qdrant credentials.

        Validates: Requirement 7.6
        """
        # Set MODE to EDGE without Qdrant credentials
        monkeypatch.setenv("MODE", "EDGE")
        monkeypatch.delenv("QDRANT_URL", raising=False)

        from app.config.settings import get_settings

        # Mock torch to avoid import issues
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False

        with patch.dict("sys.modules", {"torch": mock_torch}):
            with pytest.raises(ValueError, match="QDRANT_URL must be set in EDGE mode"):
                get_settings()


class TestRequirementsFileStructure:
    """Direct dependencies live in requirements-*.in; requirements-*.txt are hash-pinned locks."""

    BACKEND = Path(__file__).resolve().parents[2]
    ML_FRAMEWORKS = ("torch", "torchvision", "torchaudio", "transformers", "sentence-transformers",
                     "torch-geometric", "accelerate", "bitsandbytes")

    @staticmethod
    def _norm(name: str) -> str:
        return re.sub(r"[-_.]+", "-", name).lower()

    def _lock(self, name: str) -> dict[str, str]:
        """{package: version} from a uv-compiled lock, asserting every pin carries hashes."""
        text = (self.BACKEND / name).read_text()
        pins = {}
        for block in re.split(r"\n(?=[A-Za-z0-9])", text):
            first = block.split("\n", 1)[0]
            m = re.match(r"([A-Za-z0-9_.\-]+)(?:\[[^\]]*\])?==([^\s;\\]+)", first)
            if not m:
                continue
            assert "--hash=sha256:" in block, f"{name}: {m.group(1)} is pinned without a hash"
            pins[self._norm(m.group(1))] = m.group(2)
        assert pins, f"{name} has no pins"
        return pins

    def _direct(self, name: str) -> set[str]:
        out = set()
        for line in (self.BACKEND / name).read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if line and not line.startswith("-"):
                out.add(self._norm(re.split(r"[\[<>=!~ ;]", line, 1)[0]))
        return out

    def test_cloud_lock_is_hash_pinned_and_covers_every_direct_dependency(self):
        lock = self._lock("requirements-cloud.txt")
        missing = self._direct("requirements-cloud.in") - set(lock)
        assert not missing, f"requirements-cloud.txt is stale (run `make lock`): missing {sorted(missing)}"

    def test_cloud_lock_has_no_ml_frameworks(self):
        """The cloud API must stay light: no torch or transformers in its lock (Requirement 7.2)."""
        lock = self._lock("requirements-cloud.txt")
        assert not set(self.ML_FRAMEWORKS) & set(lock)

    def test_dev_lock_pins_the_same_versions_as_cloud(self):
        cloud, dev = self._lock("requirements-cloud.txt"), self._lock("requirements-dev.txt")
        drift = {p: (v, dev.get(p)) for p, v in cloud.items() if dev.get(p) != v}
        assert not drift, f"dev and cloud locks disagree: {drift}"
        assert "-r requirements-cloud.in" in (self.BACKEND / "requirements-dev.in").read_text()

    def test_onnx_lock_is_constrained_by_cloud(self):
        cloud, onnx = self._lock("requirements-cloud.txt"), self._lock("requirements-onnx.txt")
        assert {"onnxruntime", "tokenizers"} <= set(onnx)
        assert all(cloud[p] == v for p, v in onnx.items() if p in cloud)

    def test_edge_extends_cloud_and_adds_torch(self):
        edge = (self.BACKEND / "requirements-edge.txt").read_text()
        assert "-r requirements-cloud.in" in edge
        assert re.search(r"^torch==", edge, re.M), "requirements-edge.txt must pin torch"
        assert "sentence-transformers" in edge


class TestConfigurationDefaults:
    """Test default configuration values."""

    def test_default_queue_size(self):
        """
        Test default MAX_QUEUE_SIZE value.

        Validates: Requirement 2.6
        """
        from app.config.settings import get_settings

        settings = get_settings()
        assert settings.QUEUE_SIZE == 10, "Default queue size should be 10"  # env: MAX_QUEUE_SIZE

    def test_default_task_ttl(self):
        """
        Test default TASK_TTL_SECONDS value.

        Validates: Requirement 2.7
        """
        from app.config.settings import get_settings

        settings = get_settings()
        assert settings.TASK_TTL == 86400, (  # env: TASK_TTL_SECONDS
            "Default TTL should be 24 hours (86400 seconds)"
        )

    def test_default_worker_poll_interval(self):
        """
        Test default WORKER_POLL_INTERVAL value.

        Validates: Requirement 3.3
        """
        from app.config.settings import get_settings

        settings = get_settings()
        assert settings.WORKER_POLL_INTERVAL == 2, (
            "Default poll interval should be 2 seconds"
        )
