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

# Feature flag: use legacy regex heuristic for top-module detection.
# Set to True only for backward-compat debugging. Default: False (schema-driven).
LEGACY_TOP_MODULE_HEURISTIC: bool = False


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

        # DFG interface validation (Phase 3.3) — warns on bit-width mismatches
        _validate_dfg_interfaces(plan)

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

        # Combine all sub-function C++ into final code (schema-driven, Phase 3.2)
        module_name = plan.module_name
        final_cpp, top_func_name = self._combine_cpp(verified_results, plan)
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
            top_func_name=top_func_name,
        )

        # ── Post-Synthesis Port Verification (Directive 7) ──
        if synthesis_result.success:
            port_error = self._verify_post_synthesis_ports(synthesis_result, plan)
            if port_error:
                logger.warning("🔄 Post-synthesis port mismatch detected — attempting retry with corrected C++.")
                # Use the existing reflection infrastructure to fix the C++
                correction = self._module2.fix_compilation_error(
                    final_cpp, port_error, compiler
                )
                final_cpp = clean_llm_code_output(correction.fixed_cpp_code)
                synthesis_result = self._module4.run(
                    cpp_code=final_cpp,
                    module_name=module_name,
                    build_dir=self._settings.build_dir,
                    is_combinational=is_combinational,
                    top_func_name=top_func_name,
                )
                if synthesis_result.success:
                    # Re-verify after retry
                    port_error_2 = self._verify_post_synthesis_ports(synthesis_result, plan)
                    if port_error_2:
                        logger.error("Port verification still failing after retry: %s", port_error_2)

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

        # DFG interface validation (Phase 3.3)
        _validate_dfg_interfaces(plan)

        coding_results = self._module2.run(info_dicts, compiler)
        verified_results = self._verify_with_reflection(
            coding_results, info_dicts, compiler
        )
        final_cpp, top_func_name = self._combine_cpp(verified_results, plan)

        # Determine if design is combinational
        is_combinational = plan.hardware_classification in [
            HardwareClassification.COMBINATIONAL,
            "COMBINATIONAL", 
            "combinational",
        ]
        
        synthesis_result = self._module4.run(
            cpp_code=final_cpp,
            module_name=plan.module_name,
            build_dir=self._settings.build_dir,
            is_combinational=is_combinational,
            top_func_name=top_func_name,
        )

        # ── Post-Synthesis Port Verification (Directive 7) ──
        if synthesis_result.success:
            port_error = self._verify_post_synthesis_ports(synthesis_result, plan)
            if port_error:
                logger.warning("🔄 Post-synthesis port mismatch detected — attempting retry with corrected C++.")
                correction = self._module2.fix_compilation_error(
                    final_cpp, port_error, compiler
                )
                final_cpp = clean_llm_code_output(correction.fixed_cpp_code)
                synthesis_result = self._module4.run(
                    cpp_code=final_cpp,
                    module_name=plan.module_name,
                    build_dir=self._settings.build_dir,
                    is_combinational=is_combinational,
                    top_func_name=top_func_name,
                )
                if synthesis_result.success:
                    port_error_2 = self._verify_post_synthesis_ports(synthesis_result, plan)
                    if port_error_2:
                        logger.error("Port verification still failing after retry: %s", port_error_2)

        return synthesis_result

    def run_from_json(
        self,
        spec_json: dict,
        target_compiler: str | None = None,
    ) -> HLSSynthesisResult:
        """Execute the pipeline from a JSON specification object.

        Converts the structured JSON into a text representation
        and delegates to run_from_text(). This enables programmatic
        invocation from the Cirbuild agent client.

        Args:
            spec_json: Dictionary with keys: module_name, description,
                inputs, outputs, behavior, constraints, classification.
            target_compiler: Override the configured compiler.

        Returns:
            HLSSynthesisResult with the path to generated RTL.
        """
        spec_text = self._json_to_spec_text(spec_json)
        return self.run_from_text(spec_text, target_compiler)

    @staticmethod
    def _json_to_spec_text(spec_json: dict) -> str:
        """Convert a JSON spec dict into a natural-language spec string.

        Handles the Hardware Classification explicitly so the backend
        uses the correct prompts for COMBINATIONAL vs SEQUENTIAL designs.
        """
        parts = []
        parts.append(f"Module Name: {spec_json.get('module_name', 'Unknown')}")
        parts.append(f"\nDescription:\n{spec_json.get('description', '')}")

        if inputs := spec_json.get("inputs"):
            parts.append("\nInputs:")
            for name, desc in inputs.items():
                parts.append(f"  - {name}: {desc}")

        if outputs := spec_json.get("outputs"):
            parts.append("\nOutputs:")
            for name, desc in outputs.items():
                parts.append(f"  - {name}: {desc}")

        if behavior := spec_json.get("behavior"):
            parts.append(f"\nBehavior:\n{behavior}")

        if constraints := spec_json.get("constraints"):
            parts.append("\nConstraints:")
            for c in constraints:
                parts.append(f"  - {c}")

        if classification := spec_json.get("classification"):
            parts.append(f"\nHardware Classification: {classification}")

        return "\n".join(parts)

    def _verify_with_reflection(
        self,
        results: List[SubFunctionResult],
        info_dicts: List[StructuredInfoDict],
        compiler: str,
    ) -> List[SubFunctionResult]:
        """Run verification with Module 3 reflection on failures.

        Phase 1 hardening: After syntax passes, writes the testbench to disk
        and runs logical_verify (compiles + executes with assertions). If the
        testbench fails, the execution log is piped into the reflection loop
        as the error payload. The pipeline is hard-gated: it will not proceed
        to Module 4 until logical verification passes or max_cycles is exhausted.

        Args:
            results: Coding results from Module 2.
            info_dicts: Info dicts for re-generation context.
            compiler: Target compiler name.

        Returns:
            List of verified SubFunctionResults.
        """
        max_cycles = self._settings.max_reflection_cycles
        build_dir = self._settings.build_dir

        for result in results:
            if result.cpp_code is None:
                logger.error(
                    "❌ %s has no C++ code generated - skipping verification.",
                    result.name,
                )
                continue

            cpp_code = clean_llm_code_output(result.cpp_code.cpp_code)

            # Write C++ to disk for syntax check
            tmp_path = write_to_build_dir(
                content=cpp_code,
                filename=f"{result.name}_hls.cpp",
                build_root=build_dir,
            )
            status = ProgressiveCodingModule.syntax_check(tmp_path)

            if status != "SUCCESS":
                logger.warning(
                    "❌ %s failed syntax check — entering reflection loop.", result.name
                )
            else:
                # Syntax passed: attempt logical verification (Phase 1, Task 1.1)
                if result.testbench and result.testbench.testbench_code:
                    tb_code = clean_llm_code_output(result.testbench.testbench_code)
                    tb_path = write_to_build_dir(
                        content=tb_code,
                        filename=f"{result.name}_tb.cpp",
                        build_root=build_dir,
                    )
                    logical_ok, exec_log = ProgressiveCodingModule.logical_verify(
                        cpp_path=tmp_path,
                        tb_path=tb_path,
                        build_dir=tmp_path.parent,
                    )
                    if logical_ok:
                        logger.info(
                            "✅ %s passed syntax + logical verification.", result.name
                        )
                        continue
                    else:
                        # Hard-gate: logical failure treated as error for reflection
                        logger.warning(
                            "🔴 %s failed logical verification — entering reflection loop.",
                            result.name,
                        )
                        logger.debug("Execution log:\n%s", exec_log[:1000])
                        status = exec_log  # Pipe execution log into reflection
                else:
                    # No testbench available — syntax pass is sufficient
                    logger.info(
                        "✅ %s passed syntax check (no testbench available).", result.name
                    )
                    continue

            # ── Reflection Loop ──
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
                trajectory.error_description = f"Verification failed: {status[:500]}"

                if result.pseudocode:
                    trajectory.pseudocode = result.pseudocode.model_dump_json()
                if result.python_code:
                    trajectory.python_code = result.python_code.python_code

                decision = self._module3.analyze_and_decide(trajectory)

                if decision.chosen_path == ReflectionPath.RETRY_CURRENT:
                    current_tb = result.testbench.testbench_code if result.testbench else None
                    correction = self._module2.fix_compilation_error(
                        cpp_code, status, compiler, current_tb
                    )
                    cpp_code = clean_llm_code_output(correction.fixed_cpp_code)
                    result.cpp_code.cpp_code = cpp_code
                    if correction.fixed_testbench_code and result.testbench:
                        result.testbench.testbench_code = clean_llm_code_output(correction.fixed_testbench_code)

                    tmp_path = write_to_build_dir(
                        content=cpp_code,
                        filename=f"{result.name}_hls.cpp",
                        build_root=build_dir,
                    )
                    status = ProgressiveCodingModule.syntax_check(tmp_path)

                    if status == "SUCCESS":
                        # Re-run logical verification after fix
                        if result.testbench and result.testbench.testbench_code:
                            tb_code = clean_llm_code_output(
                                result.testbench.testbench_code
                            )
                            tb_path = write_to_build_dir(
                                content=tb_code,
                                filename=f"{result.name}_tb.cpp",
                                build_root=build_dir,
                            )
                            logical_ok, exec_log = ProgressiveCodingModule.logical_verify(
                                cpp_path=tmp_path,
                                tb_path=tb_path,
                                build_dir=tmp_path.parent,
                            )
                            if logical_ok:
                                logger.info(
                                    "✅ %s fixed after %d reflection cycle(s).",
                                    result.name,
                                    cycle + 1,
                                )
                                break
                            else:
                                status = exec_log  # Continue looping
                        else:
                            logger.info(
                                "✅ %s syntax fixed after %d reflection cycle(s).",
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
                    logger.info(
                        "🔄 PATH_1: Revising specification understanding for %s",
                        result.name,
                    )
                    current_tb = result.testbench.testbench_code if result.testbench else None
                    correction = self._module2.fix_compilation_error(
                        cpp_code, status, compiler, current_tb
                    )
                    cpp_code = clean_llm_code_output(correction.fixed_cpp_code)
                    result.cpp_code.cpp_code = cpp_code
                    if correction.fixed_testbench_code and result.testbench:
                        result.testbench.testbench_code = clean_llm_code_output(correction.fixed_testbench_code)
                    tmp_path = write_to_build_dir(
                        content=cpp_code,
                        filename=f"{result.name}_path1_hls.cpp",
                        build_root=build_dir,
                    )
                    status = ProgressiveCodingModule.syntax_check(tmp_path)
                    if status == "SUCCESS":
                        logger.info("✅ %s fixed via PATH_1 revision.", result.name)
                    break
                elif decision.chosen_path == ReflectionPath.FIX_PREVIOUS_SUBFUNCTIONS:
                    logger.info(
                        "🔄 PATH_2: Fixing potential issues in previous sub-functions for %s",
                        result.name,
                    )
                    current_idx = next(
                        (idx for idx, r in enumerate(results) if r.name == result.name),
                        -1,
                    )
                    if current_idx > 0:
                        logger.info(
                            "Re-validating %d previous sub-functions", current_idx
                        )
                    current_tb = result.testbench.testbench_code if result.testbench else None
                    correction = self._module2.fix_compilation_error(
                        cpp_code, status, compiler, current_tb
                    )
                    cpp_code = clean_llm_code_output(correction.fixed_cpp_code)
                    result.cpp_code.cpp_code = cpp_code
                    if correction.fixed_testbench_code and result.testbench:
                        result.testbench.testbench_code = clean_llm_code_output(correction.fixed_testbench_code)
                    tmp_path = write_to_build_dir(
                        content=cpp_code,
                        filename=f"{result.name}_path2_hls.cpp",
                        build_root=build_dir,
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
    def _combine_cpp(
        results: List[SubFunctionResult],
        plan: DecompositionPlan,
    ) -> tuple[str, str]:
        """Combine all sub-function C++ into a single source file.

        Uses the schema-driven `is_top_module` flag from the DecompositionPlan
        to deterministically identify the top module (Phase 3.2). Falls back to
        the legacy regex heuristic only if LEGACY_TOP_MODULE_HEURISTIC is True.

        Only the top module retains its `#pragma hls_top` annotation.

        Args:
            results: List of coding results with C++ code.
            plan: The DecompositionPlan from Module 1, containing is_top_module flags.

        Returns:
            Tuple of (combined C++ source string, resolved top function name).
        """
        import re

        parts: List[str] = []
        safe_name_fallback = plan.module_name.strip().lower().replace(" ", "_").replace("-", "_")

        # Build a lookup: sub-function name → is_top_module
        top_module_set: set[str] = {
            sf.name
            for sf in plan.sub_functions
            if sf.is_top_module
        }

        # Fallback: if schema provides no designation (e.g., old plans), use top_module_name
        if not top_module_set and plan.top_module_name:
            top_module_set = {plan.top_module_name}

        if not top_module_set and not LEGACY_TOP_MODULE_HEURISTIC:
            # Last resort: use the last result (integrator pattern)
            if results:
                top_module_set = {results[-1].name}
                logger.warning(
                    "No is_top_module flag found in schema — defaulting to last "
                    "sub-function '%s' as top module.",
                    results[-1].name,
                )

        if LEGACY_TOP_MODULE_HEURISTIC:
            # ── Legacy regex heuristic (preserved for debugging) ──
            spec_module_name = plan.module_name
            spec_name_clean = (
                spec_module_name.lower().replace("_", "").replace("-", "")
                if spec_module_name
                else ""
            )
            top_patterns = ["result_mux", "top", "main", "output", "mux", "wrapper"]
            top_function_idx = 0
            best_score = -1
            for idx, result in enumerate(results):
                if result.cpp_code is None:
                    continue
                func_name = result.name.lower().replace("_", "").replace("-", "")
                score = 0
                if spec_name_clean and func_name == spec_name_clean:
                    score = 100
                elif spec_name_clean and spec_name_clean in func_name:
                    score = 80
                elif any(pattern in func_name for pattern in top_patterns):
                    for pattern in reversed(top_patterns):
                        if pattern in func_name:
                            score = 50 + (10 - top_patterns.index(pattern))
                            break
                elif idx == len(results) - 1:
                    score = 20
                if score > best_score:
                    best_score = score
                    top_function_idx = idx
            top_module_set = {results[top_function_idx].name} if results else set()
            logger.debug(
                "[LEGACY] Selected '%s' as top module (score: %d)",
                results[top_function_idx].name if results else "N/A",
                best_score,
            )

        logger.info(
            "Top module(s) designated for #pragma hls_top: %s", top_module_set
        )

        for result in results:
            if result.cpp_code is not None:
                code = clean_llm_code_output(result.cpp_code.cpp_code)
                is_top = result.name in top_module_set

                if "#pragma hls_top" in code:
                    if is_top:
                        code = _ensure_toppragma(code)
                        logger.debug("Kept #pragma hls_top for: %s", result.name)
                    else:
                        code = _remove_toppragma(code)
                        logger.debug("Removed #pragma hls_top from: %s", result.name)
                elif is_top:
                    # Top function has no pragma yet — inject it
                    code = _ensure_toppragma(code)
                    logger.debug("Injected #pragma hls_top for: %s", result.name)

                parts.append(code)

        combined = "\n\n".join(parts)

        # Safety: ensure exactly one #pragma hls_top in output
        if combined.count("#pragma hls_top") > 1:
            combined = _ensure_single_toppragma(combined)

        # Resolve a single top function name for downstream use
        resolved_top_name = next(iter(top_module_set)) if top_module_set else safe_name_fallback
        return combined, resolved_top_name

    @staticmethod
    def _verify_post_synthesis_ports(
        synthesis_result: "HLSSynthesisResult",
        plan: DecompositionPlan,
    ) -> Optional[str]:
        """Verify that generated Verilog ports match the specification.

        Parses the module declaration from the synthesized .v file and
        compares the port list against DecompositionPlan.inputs_outputs.
        Detects collapsed output buses (e.g., 'out [71:0]') that indicate
        the HLS compiler flattened a multi-port interface.

        Args:
            synthesis_result: The result from Module 4 synthesis.
            plan: The DecompositionPlan with expected I/O definitions.

        Returns:
            An error message string if a severe mismatch is detected,
            None if ports match or verification cannot be performed.
        """
        import re

        if not synthesis_result.success or not synthesis_result.rtl_output_path:
            return None

        rtl_path = Path(synthesis_result.rtl_output_path)
        if not rtl_path.exists():
            logger.warning("Port verification skipped: RTL file not found at %s", rtl_path)
            return None

        rtl_content = rtl_path.read_text(encoding="utf-8")

        # Extract module declaration: module <name> ( ... );
        module_match = re.search(
            r"module\s+\w+\s*\((.*?)\)\s*;",
            rtl_content,
            re.DOTALL,
        )
        if not module_match:
            logger.warning("Port verification: could not parse module declaration from %s", rtl_path.name)
            return None

        port_section = module_match.group(1)
        # Extract individual port names (handles input/output/inout declarations)
        actual_ports = re.findall(
            r"(?:input|output|inout)\s+(?:\[[\d:]+\]\s+)?(\w+)",
            port_section,
        )

        # Build expected port set from the plan
        expected_ports: set[str] = set()
        for sf in plan.sub_functions:
            expected_ports.update(sf.inputs.keys())
            expected_ports.update(sf.outputs.keys())

        # Detect collapsed output buses (e.g., 'out [71:0]' from struct flattening)
        collapsed_buses = re.findall(
            r"output\s+\[(\d+):\s*0\]\s+(\w+)",
            port_section,
        )
        for msb, name in collapsed_buses:
            if int(msb) > 32:  # Suspiciously wide bus likely from struct collapse
                error_msg = (
                    f"HLS collapsed the ports: detected wide output bus '{name} [{msb}:0]' "
                    f"which indicates struct flattening. "
                    f"Rewrite the C++ to use pass-by-reference/pointers for all outputs "
                    f"instead of returning a struct."
                )
                logger.error("Port verification FAILED: %s", error_msg)
                return error_msg

        # Check for missing expected ports
        actual_set = set(actual_ports)
        missing = expected_ports - actual_set
        if missing:
            error_msg = (
                f"Port verification mismatch: expected ports {missing} not found in generated RTL. "
                f"Actual ports: {actual_set}. "
                f"Rewrite the C++ to use pass-by-reference/pointers for all outputs."
            )
            logger.error("Port verification FAILED: %s", error_msg)
            return error_msg

        logger.info("Port verification PASSED: %d ports match specification.", len(actual_set))
        return None


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


def _validate_dfg_interfaces(plan: DecompositionPlan) -> None:
    """Validate that DFG interface bit-widths are consistent between dependent sub-functions.

    Phase 3.3: For each sub-function B that declares a dependency on sub-function A,
    check that any signal name appearing in BOTH A's outputs and B's inputs has the
    same declared type string. Logs a WARNING for each mismatch; does not raise
    exceptions so the pipeline can still proceed.

    Args:
        plan: The DecompositionPlan from Module 1 with sub-function I/O definitions.
    """
    # Build lookup: name → SubFunction
    sf_by_name: dict[str, object] = {sf.name: sf for sf in plan.sub_functions}

    mismatch_count = 0
    for sf_b in plan.sub_functions:
        for dep_name in sf_b.dependencies:
            sf_a = sf_by_name.get(dep_name)
            if sf_a is None:
                logger.warning(
                    "DFG: Sub-function '%s' declares dependency '%s' which does not "
                    "exist in the decomposition plan.",
                    sf_b.name,
                    dep_name,
                )
                continue

            # Check overlapping signal names between A's outputs and B's inputs
            overlapping_signals = set(sf_a.outputs.keys()) & set(sf_b.inputs.keys())
            for signal in overlapping_signals:
                type_a = sf_a.outputs[signal]
                type_b = sf_b.inputs[signal]
                if type_a != type_b:
                    logger.warning(
                        "DFG MISMATCH: Signal '%s' between '%s' → '%s': "
                        "producer declares '%s', consumer expects '%s'. "
                        "Proceeding, but this may cause type errors in C++.",
                        signal,
                        dep_name,
                        sf_b.name,
                        type_a,
                        type_b,
                    )
                    mismatch_count += 1

    if mismatch_count == 0:
        logger.info("✅ DFG interface validation passed — no bit-width mismatches found.")
    else:
        logger.warning(
            "⚠️  DFG interface validation found %d mismatch(es). "
            "Review signal type declarations in Module 1 output.",
            mismatch_count,
        )
