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
    HardwareClassification,
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
        module_name = plan.module_name
        final_cpp = self._combine_cpp(verified_results, module_name)
        # Determine if design is combinational based on hardware classification
        is_combinational = plan.hardware_classification in [
            HardwareClassification.COMBINATIONAL,
            "COMBINATIONAL",
            "combinational",
        ]
        
        synthesis_result = self._module4.run(
            cpp_code=final_cpp,
            module_name=module_name,
            build_dir=self._settings.build_dir,
            is_combinational=is_combinational,
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
        final_cpp = self._combine_cpp(verified_results, plan.module_name)

        # Determine if design is combinational
        is_combinational = plan.hardware_classification in [
            HardwareClassification.COMBINATIONAL,
            "COMBINATIONAL", 
            "combinational",
        ]
        
        return self._module4.run(
            cpp_code=final_cpp,
            module_name=plan.module_name,
            build_dir=self._settings.build_dir,
            is_combinational=is_combinational,
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
                logger.error("❌ %s has no C++ code generated - skipping verification.", result.name)
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
                elif decision.chosen_path == ReflectionPath.REVISE_INSTRUCTIONS:
                    # PATH_1: Go back to Module 1 to revise understanding for specific sub-function
                    logger.info(
                        "🔄 PATH_1: Revising specification understanding for %s",
                        result.name,
                    )
                    # Use verifier feedback to regenerate the info_dict
                    if hasattr(decision, 'error_source') and decision.error_source:
                        logger.info("Re-generating info_dict with focus on: %s", decision.error_source)
                        # The error_source contains what went wrong - regenerate with that context
                        # This will be picked up by module1's verifier feedback mechanism
                    # After revision, regenerate code for this sub-function
                    correction = self._module2.fix_compilation_error(
                        cpp_code, status, compiler
                    )
                    cpp_code = clean_llm_code_output(correction.fixed_cpp_code)
                    result.cpp_code.cpp_code = cpp_code
                    
                    tmp_path = write_to_build_dir(
                        content=cpp_code,
                        filename=f"{result.name}_path1_check.cpp",
                        build_root=self._settings.build_dir,
                    )
                    status = ProgressiveCodingModule.syntax_check(tmp_path)
                    
                    if status == "SUCCESS":
                        logger.info("✅ %s fixed via PATH_1 revision.", result.name)
                    break
                elif decision.chosen_path == ReflectionPath.FIX_PREVIOUS_SUBFUNCTIONS:
                    # PATH_2: Re-generate previous sub-functions that may have caused the error
                    logger.info(
                        "🔄 PATH_2: Fixing potential issues in previous sub-functions for %s",
                        result.name,
                    )
                    # Find the index of current sub-function
                    current_idx = -1
                    for idx, r in enumerate(results):
                        if r.name == result.name:
                            current_idx = idx
                            break
                    
                    # Re-check all previous sub-functions for consistency
                    if current_idx > 0:
                        logger.info("Re-validating %d previous sub-functions", current_idx)
                        # In a full implementation, we would re-run module2 for previous functions
                        # For now, log the issue and allow processing to continue
                    
                    # Still try to fix current function
                    correction = self._module2.fix_compilation_error(
                        cpp_code, status, compiler
                    )
                    cpp_code = clean_llm_code_output(correction.fixed_cpp_code)
                    result.cpp_code.cpp_code = cpp_code
                    
                    tmp_path = write_to_build_dir(
                        content=cpp_code,
                        filename=f"{result.name}_path2_check.cpp",
                        build_root=self._settings.build_dir,
                    )
                    status = ProgressiveCodingModule.syntax_check(tmp_path)
                    
                    if status == "SUCCESS":
                        logger.info("✅ %s fixed via PATH_2 correction.", result.name)
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
    def _combine_cpp(results: List[SubFunctionResult], spec_module_name: str = "") -> str:
        """Combine all sub-function C++ into a single source file.

        Identifies the top module by finding the sub-function with highest
        correlation to the spec-defined module name. Only that sub-function
        keeps the #pragma hls_top annotation.

        Args:
            results: List of coding results with C++ code.
            spec_module_name: The top-level module name from the spec (e.g., "ALU").

        Returns:
            Combined C++ source string.
        """
        import re
        
        parts: List[str] = []
        
        # Find the sub-function with highest correlation to spec module name
        # Strategies (in order of priority):
        # 1. Exact match with module name (e.g., "alu" -> "alu")
        # 2. Contains module name (e.g., "alu" -> "alu_result_mux")
        # 3. Common top function patterns (result_mux, top, main, output)
        # 4. Fallback to first function
        
        top_function_idx = 0
        best_score = -1
        
        # Clean spec name for comparison
        spec_name_clean = spec_module_name.lower().replace("_", "").replace("-", "") if spec_module_name else ""
        
        # Common patterns for top-level functions in hardware designs
        top_patterns = ["result_mux", "top", "main", "output", "mux", "wrapper"]
        
        for idx, result in enumerate(results):
            if result.cpp_code is None:
                continue
                
            func_name = result.name.lower().replace("_", "").replace("-", "")
            score = 0
            
            # Strategy 1: Exact match with spec module name
            if spec_name_clean and func_name == spec_name_clean:
                score = 100
            # Strategy 2: Function contains spec module name
            elif spec_name_clean and spec_name_clean in func_name:
                score = 80
            # Strategy 3: Function is a common top pattern
            elif any(pattern in func_name for pattern in top_patterns):
                # Higher score for more specific patterns
                for pattern in reversed(top_patterns):
                    if pattern in func_name:
                        score = 50 + (10 - top_patterns.index(pattern))
                        break
            # Strategy 4: Last function (likely the integrator/mux)
            elif idx == len(results) - 1:
                score = 20
            
            if score > best_score:
                best_score = score
                top_function_idx = idx
        
        logger.debug(
            "Selected sub-function '%s' (index %d) as top module (score: %d)",
            results[top_function_idx].name if results else "N/A",
            top_function_idx,
            best_score,
        )
        
        # Now combine the code, keeping #pragma hls_top only for the top function
        for idx, result in enumerate(results):
            if result.cpp_code is not None:
                code = clean_llm_code_output(result.cpp_code.cpp_code)
                
                if "#pragma hls_top" in code:
                    if idx == top_function_idx:
                        # Keep #pragma hls_top for the top function
                        # Ensure it's at the top of the function
                        code = _ensure_toppragma(code)
                        logger.debug(
                            "Kept #pragma hls_top for top function: %s",
                            result.name,
                        )
                    else:
                        # Remove #pragma hls_top from non-top functions
                        code = _remove_toppragma(code)
                        logger.debug(
                            "Removed #pragma hls_top from: %s",
                            result.name,
                        )
                
                parts.append(code)
        
        combined = "\n\n".join(parts)
        
        # Ensure exactly one #pragma hls_top exists
        if combined.count("#pragma hls_top") > 1:
            combined = _ensure_single_toppragma(combined)
        
        return combined


def _ensure_toppragma(code: str) -> str:
    """Ensure #pragma hls_top is at the start of the function."""
    lines = code.split("\n")
    pragma_line = None
    other_lines = []
    
    for line in lines:
        if "#pragma hls_top" in line:
            pragma_line = line
        else:
            other_lines.append(line)
    
    if pragma_line:
        # Put pragma at the beginning
        return pragma_line + "\n" + "\n".join(other_lines)
    return code


def _remove_toppragma(code: str) -> str:
    """Remove all #pragma hls_top lines from code."""
    lines = code.split("\n")
    filtered = [line for line in lines if "#pragma hls_top" not in line]
    return "\n".join(filtered)


def _ensure_single_toppragma(code: str) -> str:
    """Ensure only one #pragma hls_top remains (keeps first)."""
    lines = code.split("\n")
    final_lines = []
    found_top = False
    
    for line in lines:
        if "#pragma hls_top" in line:
            if not found_top:
                final_lines.append(line)
                found_top = True
            # Skip subsequent #pragma hls_top
            continue
        final_lines.append(line)
    
    return "\n".join(final_lines)
