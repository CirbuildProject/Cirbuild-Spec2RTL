"""Module 4: Code Optimization and Conversion (Agnostic HLS).

Reformats the C++ implementation to comply with the active HLS
compiler's constraints, then triggers synthesis to RTL.

Datapath: Final C++ Code → Optimized C++ → Synthesized RTL

The Code Optimizer Agent dynamically queries get_constraints() from
the active AbstractHLSTool subclass to format the code accurately.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader

from spec2rtl.config.settings import Spec2RTLSettings
from spec2rtl.core.data_models import CppHlsTarget, HLSSynthesisResult, HLSConstraints
from spec2rtl.core.exceptions import HLSSynthesisFailedError, PipelineStageError
from spec2rtl.hls.bambu import BambuHLSTool
from spec2rtl.hls.base import AbstractHLSTool
from spec2rtl.hls.xls import XLSHLSTool
from spec2rtl.llm.llm_client import LLMClient
from spec2rtl.utils.code_utils import write_to_build_dir

logger = logging.getLogger("spec2rtl.agents.module4")

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    keep_trailing_newline=True,
)

# Registry of available HLS backends
_HLS_REGISTRY: dict[str, type[AbstractHLSTool]] = {
    "google_xls": XLSHLSTool,
    "bambu": BambuHLSTool,
}


def get_hls_tool(
    compiler_key: str,
    settings: Spec2RTLSettings,
) -> AbstractHLSTool:
    """Factory function to instantiate the configured HLS backend.

    Args:
        compiler_key: Key from config (e.g., 'google_xls', 'bambu').
        settings: Application settings for backend-specific config.

    Returns:
        An instantiated AbstractHLSTool subclass.

    Raises:
        PipelineStageError: If the compiler key is not registered.
    """
    tool_class = _HLS_REGISTRY.get(compiler_key)
    if tool_class is None:
        raise PipelineStageError(
            "Module 4",
            f"Unknown HLS compiler: '{compiler_key}'. "
            f"Available: {list(_HLS_REGISTRY.keys())}",
        )

    if compiler_key == "google_xls":
        return tool_class(
            docker_image=settings.xls_docker_image,
        )
    return tool_class()


class OptimizationModule:
    """Module 4 orchestrator: HLS code optimization and synthesis.

    Queries the active HLS compiler's constraints, asks the LLM to
    adapt the C++ code accordingly, then runs synthesis to produce RTL.

    Args:
        settings: Application settings.
        llm_client: Pre-configured LLM client.
        hls_tool: Pre-configured HLS tool. If None, created from settings.
    """

    def __init__(
        self,
        settings: Spec2RTLSettings | None = None,
        llm_client: LLMClient | None = None,
        hls_tool: AbstractHLSTool | None = None,
    ) -> None:
        self._settings = settings or Spec2RTLSettings.from_yaml()
        self._llm = llm_client or LLMClient(self._settings)
        self._hls_tool = hls_tool or get_hls_tool(
            self._settings.hls_compiler, self._settings
        )

    def run(
        self,
        cpp_code: str,
        module_name: str,
        build_dir: Path | None = None,
        is_combinational: bool = True,
    ) -> HLSSynthesisResult:
        """Execute the full Module 4 pipeline.

        Args:
            cpp_code: The C++ code to optimize and synthesize.
            module_name: Name for file naming purposes.
            build_dir: Output directory. Uses settings default if None.
            is_combinational: Whether the design is combinational (no clock/reset).

        Returns:
            HLSSynthesisResult with the path to generated RTL.

        Raises:
            HLSSynthesisFailedError: If synthesis fails after max retries.
        """
        output_dir = build_dir or self._settings.build_dir
        safe_name = module_name.strip().lower().replace(" ", "_").replace("-", "_")

        # We will keep track of the active constraints and code
        # They might change if we hit an error and learn a new rule
        current_constraints = self._hls_tool.get_constraints()
        current_cpp_code = cpp_code
        
        from spec2rtl.hls.reflection import HLSReflectionModule
        hls_reflector = HLSReflectionModule(self._settings)

        for attempt in range(1, self._settings.max_reflection_cycles + 1):
            
            # Stage 1: Optimize C++ for the active compiler (using current constraints)
            if attempt == 1:
                logger.info(
                    "⚡ Module 4 — Optimizing C++ for %s...",
                    self._hls_tool.tool_name,
                )
            else:
                logger.info(
                    "♻️ Module 4 — Re-optimizing C++ with learned rules (Attempt %d)...",
                    attempt
                )
            
            optimized = self._optimize_for_compiler(current_cpp_code, current_constraints, is_combinational)

            # Write optimized code to build directory
            cpp_path = write_to_build_dir(
                content=optimized.cpp_code,
                filename=f"{safe_name}_hls_att{attempt}.cpp",
                build_root=output_dir,
            )

            # Stage 2: Synthesize to RTL
            logger.info("🏗️ Module 4 — Running HLS synthesis (Attempt %d)...", attempt)
            
            result = self._hls_tool.synthesize(
                cpp_path=cpp_path,
                output_dir=cpp_path.parent,
            )

            if result.success:
                logger.info("✅ Module 4 complete: RTL at %s", result.rtl_output_path)
                return result
            
            # If we get here, synthesize() failed but didn't throw an exception 
            # (which means the tool returned success=False)
            logger.error("❌ Module 4 HLS synthesis failed: %s", result.error_log)
            
            if attempt == self._settings.max_reflection_cycles:
                logger.error("🛑 Max HLS reflection cycles reached. Aborting.")
                return result # Return the failed result
            
            # Invoke Module 4.5 to fix the code and learn a new rule
            logger.info("🔄 Passing error to Module 4.5 HLS Reflection...")
            fixed_cpp, updated_constraints = hls_reflector.recover(
                cpp_code=optimized.cpp_code,
                error_log=str(result.error_log),
                target_compiler=self._hls_tool.tool_name,
                current_constraints=current_constraints
            )
            
            # Update variables for next loop iteration
            current_cpp_code = fixed_cpp
            current_constraints = updated_constraints

    def _optimize_for_compiler(self, cpp_code: str, constraints: HLSConstraints, is_combinational: bool = True) -> CppHlsTarget:
        """Ask the LLM to adapt C++ code for the active compiler.

        Args:
            cpp_code: The input C++ code.
            constraints: The active compiler constraints (possibly updated by reflection).
            is_combinational: Whether the design is combinational (no clock/reset).

        Returns:
            A CppHlsTarget with the optimized code.
        """
        template = _jinja_env.get_template("module4_optimizer.jinja2")
        
        # Get learned rules from reflection module if available
        learned_rules = "No previous rules learned yet."
        try:
            from spec2rtl.hls.reflection import HLSReflectionModule
            reflector = HLSReflectionModule(self._settings)
            learned_rules = reflector.get_learned_rules_summary(constraints.compiler_name)
        except Exception:
            pass
        
        prompt = template.render(
            compiler_name=constraints.compiler_name,
            constraints_json=constraints.model_dump_json(indent=2),
            learned_rules=learned_rules,
            input_cpp_code=cpp_code,
            is_combinational=is_combinational,
        )
        messages = [
            {
                "role": "system",
                "content": (
                    f"You are an HLS Code Optimization Expert for "
                    f"{constraints.compiler_name}."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        
        # We use generate() with structured output via Pydantic schema
        result = self._llm.generate(messages, response_format=CppHlsTarget)
        assert isinstance(result, CppHlsTarget)
        return result
