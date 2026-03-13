"""Google XLS HLS compiler backend.

Wraps the Docker-based Google XLS toolchain (xlscc → opt_main → codegen_main)
migrated from the existing cirbuild_source_code.py. The synthesis pipeline
runs inside a pre-built Docker container for reproducibility.
"""

import logging
import subprocess
from pathlib import Path
from typing import Dict

from spec2rtl.core.data_models import HLSConstraints, HLSSynthesisResult
from spec2rtl.core.exceptions import HLSSynthesisFailedError
from spec2rtl.hls.base import AbstractHLSTool

logger = logging.getLogger("spec2rtl.hls.xls")

# Docker paths to XLS binaries inside the container
_XLS_BAZEL_PREFIX = (
    "/home/xls-developer/.cache/bazel/_bazel_xls-developer/"
    "970c5c2433bb6038ab152477a024c421/execroot/_main/"
    "bazel-out/k8-opt/bin/xls"
)
_XLSCC_BIN = f"{_XLS_BAZEL_PREFIX}/contrib/xlscc/xlscc"
_OPT_BIN = f"{_XLS_BAZEL_PREFIX}/tools/opt_main"
_CODEGEN_BIN = f"{_XLS_BAZEL_PREFIX}/tools/codegen_main"


class XLSHLSTool(AbstractHLSTool):
    """Google XLS HLS compiler backend using Docker.

    Executes the three-stage XLS pipeline:
    1. xlscc: C++ → XLS IR
    2. opt_main: XLS IR → Optimized IR
    3. codegen_main: Optimized IR → Verilog

    Args:
        docker_image: Tag of the pre-built XLS Docker image.
        timeout: Maximum seconds for each synthesis step.
    """

    def __init__(
        self,
        docker_image: str = "cirbuild-xls:v1",
        timeout: int | None = None,
    ) -> None:
        super().__init__(tool_name="Google XLS")
        self.docker_image = docker_image
        self.timeout = timeout

    def get_constraints(self) -> HLSConstraints:
        """Return Google XLS-specific constraints.

        Returns:
            HLSConstraints with XLS-specific type mappings, forbidden
            constructs, and required pragmas.
        """
        return HLSConstraints(
            compiler_name="Google XLS",
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
                "std_headers",
                "xilinx_pragmas",
                "ap_int_types",
            ],
            required_pragmas=["#pragma hls_top"],
            header_rules=(
                "NO #include directives allowed. The compiler environment "
                "is stripped. Use native C++ built-in types only."
            ),
        )

    def synthesize(self, cpp_path: Path, output_dir: Path) -> HLSSynthesisResult:
        """Run the full XLS C++ → Verilog pipeline via Docker.

        Args:
            cpp_path: Path to the input C++ source file.
            output_dir: Directory for intermediate and final outputs.

        Returns:
            HLSSynthesisResult with the path to generated Verilog.

        Raises:
            HLSSynthesisFailedError: If any pipeline step fails.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        ir_file = output_dir / cpp_path.with_suffix(".ir").name
        opt_ir_file = output_dir / f"{cpp_path.stem}_opt.ir"
        v_file = output_dir / cpp_path.with_suffix(".v").name

        # Resolve absolute paths for Docker volume mount
        local_dir = cpp_path.parent.resolve()
        base_docker_cmd = [
            "docker", "run", "--rm",
            "-v", f"{local_dir}:/workspace",
            "-w", "/workspace",
            self.docker_image,
        ]

        try:
            # Step 1: C++ → XLS IR
            logger.info("XLS Step 1: Converting C++ to XLS IR...")
            xlscc_result = subprocess.run(
                base_docker_cmd + [_XLSCC_BIN, cpp_path.name],
                check=True,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            ir_file.write_text(xlscc_result.stdout, encoding="utf-8")

            # Step 2: Optimize IR
            logger.info("XLS Step 2: Optimizing IR...")
            opt_result = subprocess.run(
                base_docker_cmd + [_OPT_BIN, ir_file.name],
                check=True,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            opt_ir_file.write_text(opt_result.stdout, encoding="utf-8")

            # Step 3: Generate Verilog
            logger.info("XLS Step 3: Generating Verilog...")
            codegen_result = subprocess.run(
                base_docker_cmd + [
                    _CODEGEN_BIN,
                    opt_ir_file.name,
                    "--generator", "combinational",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            v_file.write_text(codegen_result.stdout, encoding="utf-8")

            logger.info("✅ XLS Pipeline complete: %s", v_file)
            return HLSSynthesisResult(
                success=True,
                rtl_output_path=str(v_file),
                log_summary="XLS pipeline completed successfully.",
            )

        except subprocess.CalledProcessError as exc:
            error_msg = (
                f"XLS synthesis failed at: {' '.join(exc.cmd)}\n"
                f"stderr: {exc.stderr}"
            )
            logger.error("❌ %s", error_msg)
            # Return failed result instead of throwing to enable Module 4.5 reflection loop
            return HLSSynthesisResult(
                success=False,
                rtl_output_path="",
                log_summary="XLS synthesis failed.",
                error_log=error_msg,
            )

        except subprocess.TimeoutExpired as exc:
            error_msg = f"XLS synthesis timed out after {self.timeout}s"
            logger.error("❌ %s", error_msg)
            # Return failed result instead of throwing to enable Module 4.5 reflection loop
            return HLSSynthesisResult(
                success=False,
                rtl_output_path="",
                log_summary="XLS synthesis timed out.",
                error_log=error_msg,
            )

    def parse_logs(self, log_path: Path) -> Dict[str, str]:
        """Parse XLS synthesis logs for error context.

        Args:
            log_path: Path to the synthesis log or stderr output.

        Returns:
            Dictionary with keys like 'stage', 'error', 'context'.
        """
        if not log_path.exists():
            return {"error": f"Log file not found: {log_path}"}

        content = log_path.read_text(encoding="utf-8")
        return {
            "compiler": self.tool_name,
            "log_content": content[:2000],
            "truncated": str(len(content) > 2000),
        }
