"""Bambu HLS compiler backend (stub).

Provides the interface for the open-source Bambu HLS compiler.
Actual CLI integration will be implemented when the Bambu toolchain
is configured in the development environment.
"""

import logging
from pathlib import Path
from typing import Dict

from spec2rtl.core.data_models import HLSConstraints, HLSSynthesisResult
from spec2rtl.hls.base import AbstractHLSTool

logger = logging.getLogger("spec2rtl.hls.bambu")


class BambuHLSTool(AbstractHLSTool):
    """Bambu open-source HLS compiler backend.

    This is a stub implementation providing the correct interface
    and constraint definitions. The synthesize() method will be
    implemented when Bambu is available in the build environment.

    Args:
        bambu_path: Path to the Bambu binary. Defaults to 'bambu'
            (assumes it is on the system PATH).
        timeout: Maximum seconds for synthesis.
    """

    def __init__(
        self,
        bambu_path: str = "bambu",
        timeout: int = 300,
    ) -> None:
        super().__init__(tool_name="Bambu HLS")
        self.bambu_path = bambu_path
        self.timeout = timeout

    def get_constraints(self) -> HLSConstraints:
        """Return Bambu-specific constraints.

        Returns:
            HLSConstraints with Bambu-specific type mappings and rules.
        """
        return HLSConstraints(
            compiler_name="Bambu HLS",
            type_mappings={
                "uint8_t": "unsigned char",
                "uint16_t": "unsigned short",
                "uint32_t": "unsigned int",
                "uint64_t": "unsigned long long",
                "int8_t": "signed char",
                "int16_t": "short",
                "int32_t": "int",
                "int64_t": "long long",
            },
            forbidden_constructs=[
                "dynamic_memory",
                "xilinx_pragmas",
                "ap_int_types",
            ],
            required_pragmas=[],
            header_rules=(
                "Standard C/C++ headers are permitted. Use <cstdint> "
                "types for portability."
            ),
        )

    def synthesize(self, cpp_path: Path, output_dir: Path) -> HLSSynthesisResult:
        """Run Bambu HLS synthesis (not yet implemented).

        Args:
            cpp_path: Path to the input C++ source file.
            output_dir: Directory for synthesis outputs.

        Returns:
            HLSSynthesisResult indicating the stub status.

        Raises:
            NotImplementedError: Always, until Bambu is integrated.
        """
        raise NotImplementedError(
            "Bambu HLS synthesis is not yet integrated. "
            "Please install Bambu and update this backend."
        )

    def parse_logs(self, log_path: Path) -> Dict[str, str]:
        """Parse Bambu synthesis logs (not yet implemented).

        Args:
            log_path: Path to the synthesis log.

        Returns:
            Dictionary indicating stub status.
        """
        return {
            "compiler": self.tool_name,
            "status": "not_implemented",
            "message": "Bambu log parsing is not yet integrated.",
        }
