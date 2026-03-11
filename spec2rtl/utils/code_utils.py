"""Code post-processing utilities for the Spec2RTL pipeline.

Handles LLM output sanitization, XLS header patching, markdown fence
stripping, and sandboxed file output. These utilities sit between the
raw LLM output and the downstream HLS compiler.
"""

import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("spec2rtl.utils.code_utils")

# Pre-compiled regex patterns (per SKILL.md: compile globally, comment)
# Matches markdown code fences like ```python ... ``` or ```cpp ... ```
_MARKDOWN_FENCE_PATTERN = re.compile(
    r"^```\w*\s*\n?(.*?)```\s*$",
    re.DOTALL | re.MULTILINE,
)

# Word-boundary replacements for stdint types → native C++ types
_STDINT_REPLACEMENTS: dict[str, str] = {
    r"\buint8_t\b": "unsigned char",
    r"\buint16_t\b": "unsigned short",
    r"\buint32_t\b": "unsigned int",
    r"\buint64_t\b": "unsigned long long",
    r"\bint8_t\b": "signed char",
    r"\bint16_t\b": "short",
    r"\bint32_t\b": "int",
    r"\bint64_t\b": "long long",
}

# Pre-compile the stdint patterns for performance
_COMPILED_STDINT = {
    re.compile(pattern): replacement
    for pattern, replacement in _STDINT_REPLACEMENTS.items()
}


def clean_llm_code_output(raw_output: str) -> str:
    """Strip markdown fences and normalize escaped newlines from LLM output.

    LLM responses frequently wrap code in markdown ``` fences and use
    literal '\\n' instead of actual newlines. This function handles both.

    Args:
        raw_output: Raw code string from an LLM response.

    Returns:
        Cleaned code string ready for file writing or compilation.
    """
    cleaned = raw_output.strip()

    # Strip markdown code fences
    fence_match = _MARKDOWN_FENCE_PATTERN.search(cleaned)
    if fence_match:
        cleaned = fence_match.group(1)

    # Normalize escaped newlines to actual newlines
    cleaned = cleaned.replace("\\n", "\n")

    return cleaned.strip()


def patch_xls_headers(cpp_code: str) -> str:
    """Remove standard headers and replace stdint types for Google XLS.

    Google XLS has a stripped compiler environment that forbids
    standard C library headers. This function deterministically
    patches the code to use native C++ built-in types.

    Args:
        cpp_code: C++ source code that may contain stdint types.

    Returns:
        Patched C++ code safe for Google XLS compilation.
    """
    # Remove problematic standard headers
    cpp_code = cpp_code.replace("#include <cstdint>", "")
    cpp_code = cpp_code.replace("#include <stdint.h>", "")

    # Replace stdint types with native equivalents using word boundaries
    for compiled_pattern, native_type in _COMPILED_STDINT.items():
        cpp_code = compiled_pattern.sub(native_type, cpp_code)

    logger.debug("Patched XLS headers: removed stdint, replaced types")
    return cpp_code.strip()


def write_to_build_dir(
    content: str,
    filename: str,
    build_root: Path,
    run_id: str | None = None,
) -> Path:
    """Write generated content to a sandboxed, timestamped build directory.

    Per SKILL.md: never overwrite original files. Always write to a
    timestamped subdirectory to preserve reproducibility.

    Args:
        content: File content to write.
        filename: Target filename (e.g., 'module_hls.cpp').
        build_root: Root build directory (e.g., Path('builds')).
        run_id: Optional run identifier. If None, a timestamp is generated.

    Returns:
        Absolute path to the written file.
    """
    if run_id is None:
        run_id = datetime.now().strftime("run_%Y%m%d_%H%M%S")

    run_dir = build_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    output_path = run_dir / filename
    output_path.write_text(content, encoding="utf-8")

    logger.info("Wrote %s to %s", filename, run_dir)
    return output_path
