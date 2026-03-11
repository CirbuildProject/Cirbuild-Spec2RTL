"""Librelane RTL-to-GDSII integration interface (stub).

This module provides the interface for passing generated, verified RTL
directly into the Librelane open-source physical design flow. The actual
CLI integration is deferred to a future phase — this stub defines the
complete interface contract so Module 5 consumers can program against it.

Datapath: Synthesized RTL → Config Generation → Flow Execution → GDSII
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from spec2rtl.core.exceptions import PhysicalDesignRoutingError

logger = logging.getLogger("spec2rtl.librelane.librelane_runner")


class LibrelaneRunner:
    """Interface for the Librelane RTL-to-GDSII physical design flow.

    This is a stub implementation that defines the full interface
    contract. All methods raise NotImplementedError until the
    Librelane toolchain is integrated in a future phase.

    Args:
        rtl_dir: Directory containing the RTL source files.
        config_dir: Directory for generated configuration files.
        librelane_path: Path to the Librelane binary/script.
    """

    def __init__(
        self,
        rtl_dir: Path,
        config_dir: Path | None = None,
        librelane_path: str = "librelane",
    ) -> None:
        self.rtl_dir = rtl_dir
        self.config_dir = config_dir or rtl_dir / "librelane_config"
        self.librelane_path = librelane_path

    def generate_config(
        self,
        module_name: str,
        clock_period_ns: float = 10.0,
        pin_constraints: Dict[str, str] | None = None,
    ) -> Path:
        """Generate Librelane configuration files (TCL/JSON).

        Per spec: write the necessary .tcl or .json configuration files
        required by Librelane, including pin and timing constraints.

        Args:
            module_name: Top-level module name.
            clock_period_ns: Target clock period in nanoseconds.
            pin_constraints: Optional mapping of signal names to pin locations.

        Returns:
            Path to the generated configuration file.

        Raises:
            NotImplementedError: Always (deferred to next phase).
        """
        raise NotImplementedError(
            "Librelane config generation is deferred to the integration phase. "
            "See Module 5 in Spec2RTL_implementation.md for the full design."
        )

    def run_flow(
        self,
        config_path: Path,
        stages: list[str] | None = None,
    ) -> Dict[str, Any]:
        """Execute the Librelane physical design flow as a subprocess.

        Per spec: invoke the toolchain as a subprocess and parse the
        physical design logs for PPA metrics.

        Args:
            config_path: Path to the Librelane configuration file.
            stages: Optional list of flow stages to run (e.g.,
                ['synthesis', 'placement', 'routing']). Runs all if None.

        Returns:
            Dictionary of PPA (Power, Performance, Area) metrics.

        Raises:
            NotImplementedError: Always (deferred to next phase).
        """
        raise NotImplementedError(
            "Librelane flow execution is deferred to the integration phase."
        )

    def parse_results(
        self,
        log_dir: Path,
    ) -> Dict[str, Any]:
        """Parse Librelane physical design logs for PPA metrics.

        Args:
            log_dir: Directory containing Librelane output logs.

        Returns:
            Dictionary with parsed PPA metrics (area, timing, power).

        Raises:
            NotImplementedError: Always (deferred to next phase).
        """
        raise NotImplementedError(
            "Librelane log parsing is deferred to the integration phase."
        )
