"""Abstract base class for HLS compiler backends.

Follows the Dependency Inversion Principle: all pipeline code depends
on this abstraction rather than any concrete compiler. New compilers
are added by subclassing AbstractHLSTool without touching existing code.
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List

from spec2rtl.core.data_models import HLSConstraints, HLSSynthesisResult

logger = logging.getLogger("spec2rtl.hls.base")


class AbstractHLSTool(ABC):
    """Abstract interface for High-Level Synthesis compiler backends.

    Each subclass encapsulates the constraints, invocation method, and
    log parsing logic for a specific HLS compiler. The Code Optimizer
    Agent dynamically queries get_constraints() to format C++ code for
    the active compiler.

    Args:
        tool_name: Human-readable name for this compiler backend.
    """

    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name

    @abstractmethod
    def get_constraints(self) -> HLSConstraints:
        """Return compiler-specific constraints for code formatting.

        The Code Optimizer Agent uses these constraints to format C++
        code appropriately before synthesis.

        Returns:
            An HLSConstraints model with type mappings, forbidden
            constructs, required pragmas, and header rules.
        """

    @abstractmethod
    def synthesize(self, cpp_path: Path, output_dir: Path) -> HLSSynthesisResult:
        """Run HLS synthesis on a C++ source file.

        Args:
            cpp_path: Path to the input C++ source file.
            output_dir: Directory for synthesis outputs (RTL, logs).

        Returns:
            An HLSSynthesisResult with success status, output paths,
            and any error details.

        Raises:
            HLSSynthesisFailedError: If the synthesis process fails
                in an unrecoverable way.
        """

    @abstractmethod
    def parse_logs(self, log_path: Path) -> Dict[str, str]:
        """Parse synthesis logs for key metrics and error information.

        Args:
            log_path: Path to the synthesis log file.

        Returns:
            Dictionary of parsed metrics (e.g., latency, resource usage)
            or error details.
        """

    def get_supported_types(self) -> List[str]:
        """Return the list of C++ type names this compiler supports.

        Returns:
            List of type name strings (e.g., ['unsigned char', 'ap_uint']).
        """
        constraints = self.get_constraints()
        return list(constraints.type_mappings.values())
