"""End-to-end pipeline orchestrator for the Spec2RTL toolchain.

Connects Modules 1 through 4 into a single coherent pipeline that
takes a PDF specification and produces synthesized RTL code. Module 3's
adaptive reflection is invoked automatically on verification failures.
"""

import logging
from pathlib import Path
from typing import List, Optional

from spec2rtl.agents.module1_understanding import UnderstandingModule
from spec2rtl.agents.module2_coding import (
    ProgressiveCodingModule,
    SubFunctionResult,
)
from spec2rtl.agents.module3_reflection import (
    GenerationTrajectory,
    ReflectionModule,
)
from spec2rtl.agents.module4_optimization import OptimizationModule
from spec2rtl.config.settings import Spec2RTLSettings
from spec2rtl.core.data_models import (
    DecompositionPlan,
    HLSSynthesisResult,
    ReflectionPath,
    StructuredInfoDict,
)
from spec2rtl.core.exceptions import PipelineStageError, Spec2RTLError
from spec2rtl.core.logging_config import setup_logging
from spec2rtl.llm.llm_client import LLMClient
from spec2rtl.utils.code_utils import clean_llm_code_output, write_to_build_dir
from spec2rtl.utils.pdf_parser import PDFParser

logger = logging.getLogger("spec2rtl.pipeline")


class Spec2RTLPipeline:
    """Top-level orchestrator connecting Modules 1-4.

    Usage:
        pipeline = Spec2RTLPipeline()
        result = pipeline.run(Path("my_spec.pdf"))
        print(result.rtl_output_path)

    Args:
        config_path: Path to a YAML config file. Uses defaults if None.
        settings: Pre-built settings. Overrides config_path if provided.
    """

    def __init__(
        self,
        config_path: Path | None = None,
        settings: Spec2RTLSettings | None = None,
    ) -> None:
        self._settings = settings or Spec2RTLSettings.from_yaml(config_path)

        # Setup logging
        setup_logging(
            log_level=self._settings.log_level,
            log_dir=self._settings.log_dir,
        )

        # Shared LLM client
        self._llm = LLMClient(self._settings)

        # Initialize modules
        self._module1 = UnderstandingModule(self._settings, self._llm)
        self._module2 = ProgressiveCodingModule(self._settings, self._llm)
        self._module3 = ReflectionModule(self._settings, self._llm)
        self._module4 = OptimizationModule(self._settings, self._llm)

    def run(
        self,
        spec_path: Path,
        target_compiler: str | None = None,
    ) -> HLSSynthesisResult:
        """Execute the full Spec2RTL pipeline.

        Args:
            spec_path: Path to the specification PDF document.
            target_compiler: Override the configured compiler. If None,
                uses the config default.

        Returns:
            HLSSynthesisResult with the path to generated RTL.

        Raises:
            Spec2RTLError: On any pipeline failure.
        """
        compiler = target_compiler or "Google XLS"
        logger.info("🚀 Spec2RTL Pipeline starting for: %s", spec_path.name)
        logger.info("   Target compiler: %s", compiler)

        # ── Module 1: Understanding ──
        logger.info("=" * 60)
        logger.info("MODULE 1: Iterative Understanding & Reasoning")
        logger.info("=" * 60)

        pages = PDFParser.extract_text(spec_path)
        plan, info_dicts = self._module1.run(pages)

        # ── Module 2: Progressive Coding ──
        logger.info("=" * 60)
        logger.info("MODULE 2: Progressive Coding & Prompt Optimization")
        logger.info("=" * 60)

        coding_results = self._module2.run(info_dicts, compiler)

        # ── Module 2.5: Verification + Module 3 Reflection Loop ──
        verified_results = self._verify_with_reflection(
            coding_results, info_dicts, compiler
        )

        # ── Module 4: Optimization & Synthesis ──
        logger.info("=" * 60)
        logger.info("MODULE 4: Code Optimization & HLS Synthesis")
        logger.info("=" * 60)

        # Combine all sub-function C++ into final code
        final_cpp = self._combine_cpp(verified_results)

        module_name = plan.module_name
        synthesis_result = self._module4.run(
            cpp_code=final_cpp,
            module_name=module_name,
            build_dir=self._settings.build_dir,
        )

        if synthesis_result.success:
            logger.info("🎉 Pipeline complete! RTL: %s", synthesis_result.rtl_output_path)
        else:
            logger.error("❌ Pipeline failed at synthesis stage.")

        return synthesis_result

    def run_from_text(
        self,
        spec_text: str,
        target_compiler: str | None = None,
    ) -> HLSSynthesisResult:
        """Execute the pipeline from raw specification text.

        Convenience method for cases where the spec is already in text
        form (e.g., from the existing cirbuild_source_code.py workflow).

        Args:
            spec_text: The hardware specification as a string.
            target_compiler: Override the configured compiler.

        Returns:
            HLSSynthesisResult with the path to generated RTL.
        """
        compiler = target_compiler or "Google XLS"
        logger.info("🚀 Spec2RTL Pipeline starting from text input")

        pages = [spec_text]
        plan, info_dicts = self._module1.run(pages, spec_text)
        coding_results = self._module2.run(info_dicts, compiler)
        verified_results = self._verify_with_reflection(
            coding_results, info_dicts, compiler
        )
        final_cpp = self._combine_cpp(verified_results)

        return self._module4.run(
            cpp_code=final_cpp,
            module_name=plan.module_name,
            build_dir=self._settings.build_dir,
        )

    def _verify_with_reflection(
        self,
        results: List[SubFunctionResult],
        info_dicts: List[StructuredInfoDict],
        compiler: str,
    ) -> List[SubFunctionResult]:
        """Run verification with Module 3 reflection on failures.

        For each sub-function, checks compilation and routes failures
        through the reflection module for up to max_reflection_cycles.

        Args:
            results: Coding results from Module 2.
            info_dicts: Info dicts for re-generation context.
            compiler: Target compiler name.

        Returns:
            List of verified SubFunctionResults.
        """
        max_cycles = self._settings.max_reflection_cycles

        for result in results:
            if result.cpp_code is None:
                continue

            cpp_code = clean_llm_code_output(result.cpp_code.cpp_code)

            # Write to temp for syntax check
            tmp_path = write_to_build_dir(
                content=cpp_code,
                filename=f"{result.name}_check.cpp",
                build_root=self._settings.build_dir,
            )
            status = ProgressiveCodingModule.syntax_check(tmp_path)

            if status == "SUCCESS":
                logger.info("✅ %s passed syntax check.", result.name)
                continue

            # Enter reflection loop
            for cycle in range(max_cycles):
                logger.warning(
                    "🔄 Reflection cycle %d/%d for %s",
                    cycle + 1,
                    max_cycles,
                    result.name,
                )

                trajectory = GenerationTrajectory(result.name)
                trajectory.cpp_code = cpp_code
                trajectory.compilation_log = status
                trajectory.error_description = f"Compilation failed: {status[:500]}"

                if result.pseudocode:
                    trajectory.pseudocode = result.pseudocode.model_dump_json()
                if result.python_code:
                    trajectory.python_code = result.python_code.python_code

                decision = self._module3.analyze_and_decide(trajectory)

                if decision.chosen_path == ReflectionPath.RETRY_CURRENT:
                    correction = self._module2.fix_compilation_error(
                        cpp_code, status, compiler
                    )
                    cpp_code = clean_llm_code_output(correction.fixed_cpp_code)
                    result.cpp_code.cpp_code = cpp_code

                    tmp_path = write_to_build_dir(
                        content=cpp_code,
                        filename=f"{result.name}_check.cpp",
                        build_root=self._settings.build_dir,
                    )
                    status = ProgressiveCodingModule.syntax_check(tmp_path)

                    if status == "SUCCESS":
                        logger.info(
                            "✅ %s fixed after %d reflection cycles.",
                            result.name,
                            cycle + 1,
                        )
                        break
                elif decision.chosen_path == ReflectionPath.HUMAN_INTERVENTION:
                    logger.error(
                        "🛑 Human intervention requested for %s: %s",
                        result.name,
                        decision.reasoning,
                    )
                    break
                else:
                    logger.warning(
                        "Reflection path %s not yet automated. "
                        "Continuing with best-effort code.",
                        decision.chosen_path.value,
                    )
                    break

        return results

    @staticmethod
    def _combine_cpp(results: List[SubFunctionResult]) -> str:
        """Combine all sub-function C++ into a single source file.

        Args:
            results: List of coding results with C++ code.

        Returns:
            Combined C++ source string.
        """
        parts: List[str] = []
        for result in results:
            if result.cpp_code is not None:
                code = clean_llm_code_output(result.cpp_code.cpp_code)
                parts.append(code)
        return "\n\n".join(parts)
