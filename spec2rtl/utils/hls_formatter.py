"""Deterministic HLS formatting utilities for the Spec2RTL pipeline.

Implements Phase 2 (Task 2.1) of the architecture hardening plan:
replace LLM-driven formatting of basic HLS directives with deterministic
Python scripts that cannot hallucinate or destroy logic.

Compiler-gating policy (A1):
  - Vitis:      swap_standard_types() inserts ap_uint/ap_int types.
  - Google XLS: type mapping is handled by patch_xls_headers() in
                code_utils.py. Do NOT call swap_standard_types() for XLS.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger("spec2rtl.utils.hls_formatter")

# ──────────────────────────────────────────────────────────────
# Pre-compiled regex patterns (compiled once at import time)
# ──────────────────────────────────────────────────────────────

# Matches a 'for' loop header line (handles optional leading whitespace).
# Used to insert #pragma HLS pipeline / #pragma hls_unroll directly above.
_FOR_LOOP_PATTERN = re.compile(
    r"^(?P<indent>[ \t]*)for\s*\(",
    re.MULTILINE,
)

# Matches a C++ function definition line that could be the top-level entry.
# Captures: optional return type + function name.
# Deliberately broad — we match by name after extraction.
_FUNC_DEF_PATTERN = re.compile(
    r"^(?P<indent>[ \t]*)(?:[\w:\*&<> ]+\s+)?(?P<name>\w+)\s*\([^;{]*\)\s*(?:const\s*)?\{",
    re.MULTILINE,
)

# Vitis HLS type mapping: C99 stdint → Xilinx ap_uint/ap_int
# Word-boundary anchored to avoid partial substitutions.
_VITIS_TYPE_MAP: dict[str, str] = {
    r"\buint8_t\b":  "ap_uint<8>",
    r"\buint16_t\b": "ap_uint<16>",
    r"\buint32_t\b": "ap_uint<32>",
    r"\buint64_t\b": "ap_uint<64>",
    r"\bint8_t\b":   "ap_int<8>",
    r"\bint16_t\b":  "ap_int<16>",
    r"\bint32_t\b":  "ap_int<32>",
    r"\bint64_t\b":  "ap_int<64>",
    r"\bbool\b":     "ap_uint<1>",
}

# Pre-compile Vitis type patterns for performance
_COMPILED_VITIS_TYPES = {
    re.compile(pattern): replacement
    for pattern, replacement in _VITIS_TYPE_MAP.items()
}

# Pragma strings per compiler
_VITIS_LOOP_PRAGMA = "#pragma HLS pipeline"
_XLS_LOOP_PRAGMA = "#pragma hls_unroll yes"
_XLS_TOP_PRAGMA = "#pragma hls_top"


def insert_pipeline_pragmas(code: str, compiler_key: str) -> str:
    """Insert loop-unrolling/pipeline pragmas above every 'for' loop.

    For Vitis HLS: inserts `#pragma HLS pipeline` above each for-loop.
    For Google XLS: inserts `#pragma hls_unroll yes` above each for-loop.

    This is a deterministic operation — the LLM is not involved.

    Args:
        code: C++ source code string.
        compiler_key: Normalized compiler key ('vitis' or 'google_xls').

    Returns:
        C++ source code with loop pragmas inserted.
    """
    if "vitis" in compiler_key:
        pragma = _VITIS_LOOP_PRAGMA
    else:
        pragma = _XLS_LOOP_PRAGMA

    lines = code.split("\n")
    result_lines: list[str] = []

    for line in lines:
        # Check if this line is a for-loop header
        m = _FOR_LOOP_PATTERN.match(line)
        if m:
            indent = m.group("indent")
            pragma_line = f"{indent}{pragma}"
            # Only insert if not already present on the immediately preceding line
            if not result_lines or result_lines[-1].strip() != pragma.strip():
                result_lines.append(pragma_line)
                logger.debug("Inserted '%s' before: %s", pragma, line.strip())
        result_lines.append(line)

    return "\n".join(result_lines)


def inject_hls_top(code: str, top_func_name: str, compiler_key: str) -> str:
    """Inject the top-level pragma directly above the named function using robust regex."""
    if "vitis" in compiler_key:
        return code

    pragma = "#pragma hls_top\n"

    # Matches the return type (Group 1), function name, and opening parenthesis (Group 2)
    # \s* safely handles spaces or newlines between the name and the parenthesis
    pattern = r"((?:\w[\w:\*&<> ]*\s+))" + re.escape(top_func_name) + r"(\s*\()"
    replacement = rf"{pragma}\1{top_func_name}\2"

    new_code, count = re.subn(pattern, replacement, code, count=1)

    if count == 0:
        logger.warning(f"inject_hls_top: function '{top_func_name}' not found — pragma not inserted.")
    else:
        logger.info(f"✅ Top-level pragma injection applied (func: '{top_func_name}')")

    return new_code


def swap_standard_types(code: str) -> str:
    """Swap C99 stdint types to Xilinx ap_uint/ap_int for Vitis HLS.

    IMPORTANT: Call this ONLY for the 'vitis' compiler key.
    For Google XLS, use patch_xls_headers() from code_utils.py instead.

    Operates on word boundaries to avoid partial matches (e.g., does not
    mangle 'uint32_t_array'). Does not touch comments or string literals —
    simple regex is intentionally chosen over a full AST parser to keep
    this dependency-free and auditable.

    Args:
        code: C++ source code with C99 stdint types.

    Returns:
        C++ source code with Xilinx ap_uint/ap_int types substituted.
    """
    # Ensure the ap_int header is present
    if "#include" not in code or "ap_int.h" not in code:
        code = '#include "ap_int.h"\n' + code
        logger.debug("Injected '#include \"ap_int.h\"' for Vitis type mapping")

    for compiled_pattern, ap_type in _COMPILED_VITIS_TYPES.items():
        original = code
        code = compiled_pattern.sub(ap_type, code)
        if code != original:
            logger.debug("swap_standard_types: substituted → %s", ap_type)

    return code


def apply_deterministic_formatting(
    code: str,
    compiler_key: str,
    top_func_name: Optional[str] = None,
    enable_loop_pragmas: bool = True,
    enable_type_swap: bool = True,
) -> str:
    """Apply all deterministic HLS formatting passes in the correct order.

    Orchestrates the three sub-transforms. This is the single entry point
    called by Module 4 before (optionally) invoking the LLM optimizer.

    Transform order:
      1. Type substitution (must come before pragma insertion to avoid
         pragma lines being matched as 'for' loops).
      2. Loop pragma insertion.
      3. Top-level pragma injection.

    Args:
        code: Input C++ source code.
        compiler_key: Normalized compiler key ('vitis' or 'google_xls').
        top_func_name: Name of the top-level function, if known.
        enable_loop_pragmas: Feature flag — set False to skip pragma insertion.
        enable_type_swap: Feature flag — Vitis: swap types; XLS: no-op here.

    Returns:
        Deterministically formatted C++ source code.
    """
    logger.info(
        "🔧 HLS Formatter: applying deterministic passes for '%s'", compiler_key
    )
    result = code

    # Pass 1: Type mapping (compiler-gated per A1 directive)
    if enable_type_swap:
        if "vitis" in compiler_key:
            result = swap_standard_types(result)
            logger.info("  ✅ Vitis type substitution applied (stdint → ap_uint/ap_int)")
        else:
            # XLS types are handled by patch_xls_headers() in code_utils.py
            logger.debug(
                "  ⏭️  Type swap skipped for '%s' — handled upstream by patch_xls_headers()",
                compiler_key,
            )

    # Pass 2: Loop pragma insertion
    if enable_loop_pragmas:
        result = insert_pipeline_pragmas(result, compiler_key)
        logger.info("  ✅ Loop pragma insertion applied")

    # Pass 3: Top pragma injection (XLS only, Vitis is no-op)
    if top_func_name:
        result = inject_hls_top(result, top_func_name, compiler_key)
        logger.info("  ✅ Top-level pragma injection applied (func: '%s')", top_func_name)

    return result
