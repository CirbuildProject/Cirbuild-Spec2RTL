"""Dual-level logging configuration for the Spec2RTL toolchain.

Console output is kept clean at INFO level for the user, while file
logs capture full DEBUG-level detail including raw LLM prompts, tool
CLI arguments, and execution timings for post-mortem analysis by the
ReflectionAgent.
"""

import logging
import sys
from pathlib import Path


def setup_logging(
    log_level: str = "INFO",
    log_dir: Path | None = None,
    log_filename: str = "spec2rtl.log",
) -> logging.Logger:
    """Configure and return the root logger for the Spec2RTL package.

    Args:
        log_level: Minimum level for console output (e.g. 'INFO', 'DEBUG').
        log_dir: Directory for the rotating file log. If None, file logging
            is disabled and only console output is produced.
        log_filename: Name of the log file within log_dir.

    Returns:
        The configured root logger for the 'spec2rtl' namespace.
    """
    logger = logging.getLogger("spec2rtl")
    logger.setLevel(logging.DEBUG)

    # Prevent duplicate handlers on repeated calls
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # --- Console handler (user-facing, clean) ---
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # --- File handler (debug-level, for reflection / post-mortem) ---
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(
            log_dir / log_filename,
            mode="a",
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
