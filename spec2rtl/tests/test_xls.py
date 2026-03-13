"""Unit tests for Google XLS HLS compiler."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from spec2rtl.hls.xls import XLSHLSTool
from spec2rtl.core.data_models import HLSConstraints


class TestXLSHLSTool(unittest.TestCase):
    """Tests for the XLS HLS compiler backend."""

    def test_default_timeout_is_none(self) -> None:
        """Default timeout should be None (no limit) after our fix."""
        tool = XLSHLSTool()
        self.assertIsNone(tool.timeout)

    def test_custom_timeout(self) -> None:
        """Should accept custom timeout values."""
        tool = XLSHLSTool(timeout=300)
        self.assertEqual(tool.timeout, 300)

    def test_timeout_can_be_zero(self) -> None:
        """Should allow timeout of 0 (immediate timeout)."""
        tool = XLSHLSTool(timeout=0)
        self.assertEqual(tool.timeout, 0)

    def test_get_constraints(self) -> None:
        """Should return XLS-specific constraints."""
        tool = XLSHLSTool()
        constraints = tool.get_constraints()

        self.assertIsInstance(constraints, HLSConstraints)
        self.assertEqual(constraints.compiler_name, "Google XLS")
        self.assertIn("uint8_t", constraints.type_mappings)
        self.assertIn("#pragma hls_top", constraints.required_pragmas)

    def test_type_mappings(self) -> None:
        """Should have correct type mappings for XLS."""
        tool = XLSHLSTool()
        constraints = tool.get_constraints()

        # Verify type mappings
        self.assertEqual(constraints.type_mappings["uint8_t"], "unsigned char")
        self.assertEqual(constraints.type_mappings["uint32_t"], "unsigned int")
        self.assertEqual(constraints.type_mappings["int32_t"], "int")

    def test_forbidden_constructs(self) -> None:
        """Should list forbidden constructs for XLS."""
        tool = XLSHLSTool()
        constraints = tool.get_constraints()

        self.assertIn("dynamic_memory", constraints.forbidden_constructs)
        self.assertIn("xilinx_pragmas", constraints.forbidden_constructs)


if __name__ == "__main__":
    unittest.main()
