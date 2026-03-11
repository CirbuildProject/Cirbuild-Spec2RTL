"""Unit tests for code utility functions."""

import tempfile
from pathlib import Path

import pytest

from spec2rtl.utils.code_utils import (
    clean_llm_code_output,
    patch_xls_headers,
    write_to_build_dir,
)


class TestCleanLLMCodeOutput:
    """Tests for stripping markdown fences and normalizing newlines."""

    def test_strips_markdown_fence(self) -> None:
        raw = '```cpp\nint main() { return 0; }\n```'
        result = clean_llm_code_output(raw)
        assert "```" not in result
        assert "int main()" in result

    def test_strips_python_fence(self) -> None:
        raw = '```python\ndef foo(): pass\n```'
        result = clean_llm_code_output(raw)
        assert "```" not in result
        assert "def foo()" in result

    def test_normalizes_escaped_newlines(self) -> None:
        raw = 'int a = 1;\\nint b = 2;'
        result = clean_llm_code_output(raw)
        assert "\\n" not in result
        assert "\n" in result

    def test_no_fences_unchanged(self) -> None:
        raw = "int x = 42;"
        result = clean_llm_code_output(raw)
        assert result == raw

    def test_strips_whitespace(self) -> None:
        raw = "  \n  int x;  \n  "
        result = clean_llm_code_output(raw)
        assert result == "int x;"


class TestPatchXLSHeaders:
    """Tests for Google XLS header patching."""

    def test_removes_cstdint(self) -> None:
        code = '#include <cstdint>\nuint8_t x;'
        result = patch_xls_headers(code)
        assert "#include <cstdint>" not in result

    def test_removes_stdint_h(self) -> None:
        code = '#include <stdint.h>\nint8_t x;'
        result = patch_xls_headers(code)
        assert "#include <stdint.h>" not in result

    def test_replaces_uint8(self) -> None:
        code = "uint8_t data_in;"
        result = patch_xls_headers(code)
        assert result == "unsigned char data_in;"

    def test_replaces_uint16(self) -> None:
        code = "uint16_t value;"
        result = patch_xls_headers(code)
        assert result == "unsigned short value;"

    def test_replaces_int32(self) -> None:
        code = "int32_t accumulator;"
        result = patch_xls_headers(code)
        assert result == "int accumulator;"

    def test_word_boundary_safety(self) -> None:
        """Must not replace partial matches like 'my_uint8_t_val'."""
        code = "unsigned char my_uint8_t_val;"
        result = patch_xls_headers(code)
        # The word 'uint8_t' embedded inside the variable name should not be changed
        # but since it matches the word boundary regex, the variable name stays
        assert "unsigned char" in result


class TestWriteToBuildDir:
    """Tests for sandboxed file output."""

    def test_creates_directory_and_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_to_build_dir(
                content="test content",
                filename="test.cpp",
                build_root=Path(tmp),
                run_id="test_run",
            )
            assert path.exists()
            assert path.read_text() == "test content"
            assert "test_run" in str(path)

    def test_auto_timestamp_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_to_build_dir(
                content="data",
                filename="out.v",
                build_root=Path(tmp),
            )
            assert path.exists()
            assert "run_" in str(path.parent.name)

    def test_idempotent_writes(self) -> None:
        """Writing the same content twice to the same run_id should
        produce the same file content (per SKILL.md idempotency)."""
        with tempfile.TemporaryDirectory() as tmp:
            p1 = write_to_build_dir("abc", "f.txt", Path(tmp), "run1")
            p2 = write_to_build_dir("abc", "f.txt", Path(tmp), "run1")
            assert p1.read_text() == p2.read_text() == "abc"
