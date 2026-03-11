"""Centralized configuration management using pydantic-settings.

All tunable parameters (LLM models, HLS paths, build directories, etc.)
are loaded from a YAML config file and can be overridden by environment
variables. No hardcoded values exist in functional logic.
"""

from pathlib import Path
from typing import List

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings


_DEFAULT_CONFIG_PATH = Path(__file__).parent / "default_config.yaml"


def _load_yaml_config(path: Path) -> dict:
    """Load a YAML configuration file and return its contents as a dict.

    Args:
        path: Absolute or relative path to the YAML file.

    Returns:
        Parsed dictionary from the YAML file, or empty dict if not found.
    """
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


class Spec2RTLSettings(BaseSettings):
    """Application-wide settings for the Spec2RTL toolchain.

    Values are resolved in this priority order (highest wins):
    1. Environment variables (prefixed with SPEC2RTL_)
    2. Values passed directly to the constructor
    3. Defaults defined below (which match default_config.yaml)
    """

    # --- LLM Configuration (API-Agnostic) ---
    default_model: str = Field(
        default="gemini/gemini-3-flash-preview",
        description="Primary LLM model identifier in LiteLLM format.",
    )
    fallback_models: List[str] = Field(
        default_factory=lambda: [
            "gemini/gemini-2.5-flash",
            "gemini/gemini-2.5-flash-lite",
            "gemini/gemini-2.5-pro",
        ],
        description="Ordered list of fallback model identifiers.",
    )
    max_llm_retries: int = Field(
        default=3,
        description="Max formatting retry attempts per model before fallback.",
    )
    llm_temperature: float = Field(
        default=0.0,
        description="Temperature for LLM completions.",
    )
    llm_max_tokens: int = Field(
        default=4096,
        description="Maximum output tokens for LLM completions.",
    )

    # --- Build & Output ---
    build_dir: Path = Field(
        default=Path("builds"),
        description="Root directory for timestamped build outputs.",
    )

    # --- HLS Compiler ---
    hls_compiler: str = Field(
        default="google_xls",
        description="Active HLS compiler backend (google_xls, bambu, vitis).",
    )
    xls_docker_image: str = Field(
        default="cirbuild-xls:v1",
        description="Docker image tag for the Google XLS toolchain.",
    )

    # --- Logging ---
    log_level: str = Field(
        default="INFO",
        description="Console log level (DEBUG, INFO, WARNING, ERROR).",
    )
    log_dir: Path = Field(
        default=Path("logs"),
        description="Directory for detailed debug log files.",
    )

    # --- Agent Orchestration ---
    max_agent_rounds: int = Field(
        default=20,
        description="Maximum message rounds in an AutoGen group chat.",
    )
    max_reflection_cycles: int = Field(
        default=3,
        description="Maximum Module 3 reflection retry cycles.",
    )

    model_config = {
        "env_prefix": "SPEC2RTL_",
        "env_nested_delimiter": "__",
    }

    @classmethod
    def from_yaml(cls, config_path: Path | None = None) -> "Spec2RTLSettings":
        """Load settings from a YAML file, with env var overrides.

        Priority order (highest wins):
        1. Environment variables (SPEC2RTL_*)
        2. YAML config file values
        3. Field defaults

        Args:
            config_path: Path to a YAML config file. Falls back to the
                built-in default_config.yaml if not provided.

        Returns:
            A fully resolved Spec2RTLSettings instance.
        """
        import os

        path = config_path or _DEFAULT_CONFIG_PATH
        yaml_values = _load_yaml_config(path)

        # Let env vars take precedence: remove YAML keys that have
        # a corresponding SPEC2RTL_ environment variable set.
        env_prefix = cls.model_config.get("env_prefix", "SPEC2RTL_")
        filtered: dict = {}
        for key, value in yaml_values.items():
            env_key = f"{env_prefix}{key.upper()}"
            if env_key not in os.environ:
                filtered[key] = value

        return cls(**filtered)
