"""Unit tests for long-term memory with ChromaDB."""

import shutil
import tempfile
import unittest
from pathlib import Path

# Import the module under test
from spec2rtl.memory.long_term_memory import ErrorFixPair, LongTermMemory


class TestLongTermMemory(unittest.TestCase):
    """Tests for the ChromaDB-backed long-term memory."""

    def setUp(self) -> None:
        """Create a temporary directory for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.memory = LongTermMemory(persist_dir=self.temp_dir)

    def tearDown(self) -> None:
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_store_and_retrieve_fix(self) -> None:
        """Should store and retrieve a successful error-fix pair."""
        if self.memory._collection is None:
            self.skipTest("ChromaDB not available")

        fix = ErrorFixPair(
            error_type="pointer_parameter",
            compiler="google_xls",
            error_message="UNIMPLEMENTED: Pointer function parameters unsupported",
            fix_strategy="Use return values instead of pointer outputs",
            fixed_code_snippet="unsigned int select_alu_result(...)",
            success=True,
        )

        # Store the fix
        stored = self.memory.store_fix(fix)
        self.assertTrue(stored)

        # Retrieve similar fixes - this tests the $and syntax we fixed
        results = self.memory.find_similar_fixes(
            error_message="Pointer function parameters unsupported",
            error_type="pointer_parameter",
            compiler="google_xls",
        )

        # Should find the fix we just stored
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].error_type, "pointer_parameter")

    def test_find_similar_fixes_with_multiple_filters(self) -> None:
        """Test that multiple filter conditions work with $and operator."""
        if self.memory._collection is None:
            self.skipTest("ChromaDB not available")

        # Store a fix
        fix = ErrorFixPair(
            error_type="duplicate_top",
            compiler="google_xls",
            error_message="ALREADY_EXISTS: Two top functions defined",
            fix_strategy="Remove pragma from non-top functions",
            fixed_code_snippet="#pragma hls_top only on one function",
            success=True,
        )
        self.memory.store_fix(fix)

        # Search with multiple filters - this is what was failing before
        results = self.memory.find_similar_fixes(
            error_message="Two top functions defined",
            error_type="duplicate_top",
            compiler="google_xls",
        )

        # Should work without ChromaDB errors
        self.assertIsInstance(results, list)

    def test_get_statistics(self) -> None:
        """Should return statistics about the memory."""
        stats = self.memory.get_statistics()
        self.assertIn("available", stats)
        self.assertIn("total_fixes", stats)

    def test_store_duplicate_returns_false(self) -> None:
        """Storing the same fix twice should return False."""
        if self.memory._collection is None:
            self.skipTest("ChromaDB not available")

        fix = ErrorFixPair(
            error_type="test_error",
            compiler="test_compiler",
            error_message="Test error message",
            fix_strategy="Test fix",
            fixed_code="test code",
            success=True,
        )

        first = self.memory.store_fix(fix)
        second = self.memory.store_fix(fix)

        self.assertTrue(first)
        self.assertFalse(second)


if __name__ == "__main__":
    unittest.main()
