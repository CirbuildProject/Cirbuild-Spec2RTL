"""Unit tests for the config system."""

from pathlib import Path

import pytest

from spec2rtl.config.settings import Spec2RTLSettings


class TestSpec2RTLSettings:
    """Test the Pydantic-settings configuration loader."""

    def test_default_settings_load(self) -> None:
        """Settings should load with defaults from default_config.yaml."""
        settings = Spec2RTLSettings.from_yaml()
        assert settings.default_model == "gemini/gemini-3.1-pro-preview"
        assert len(settings.fallback_models) >= 1
        assert settings.max_llm_retries == 3
        assert settings.llm_temperature == 0.0

    def test_default_model_is_litellm_format(self) -> None:
        """Model identifiers should use 'provider/model' LiteLLM format."""
        settings = Spec2RTLSettings.from_yaml()
        assert "/" in settings.default_model, (
            "Model ID must be in LiteLLM format: 'provider/model-name'"
        )

    def test_build_dir_is_path(self) -> None:
        """Build dir should be a Path object."""
        settings = Spec2RTLSettings.from_yaml()
        assert isinstance(settings.build_dir, Path)

    def test_from_yaml_nonexistent_file(self) -> None:
        """Loading from a nonexistent file should fallback to defaults."""
        settings = Spec2RTLSettings.from_yaml(Path("/nonexistent/config.yaml"))
        assert settings.default_model == "gemini/gemini-3-flash-preview"

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Environment variables should override config values."""
        monkeypatch.setenv("SPEC2RTL_DEFAULT_MODEL", "openai/gpt-4o")
        settings = Spec2RTLSettings.from_yaml()
        assert settings.default_model == "openai/gpt-4o"

    def test_hls_compiler_default(self) -> None:
        """Default HLS compiler should be google_xls."""
        settings = Spec2RTLSettings.from_yaml()
        assert settings.hls_compiler == "google_xls"
