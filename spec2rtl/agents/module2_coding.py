"""Module 2: Progressive Coding and Prompt Optimization.

Sequentially implements each sub-function from the Module 1 plan
using a progressive refinement chain: Pseudocode → Python → C++.
Includes verification via testbench generation and prompt optimization.

Datapath: Structured Dict → Pseudocode → Python → Synthesizable C++

Each level's output is used as reference context for the next level,
enabling cross-level code referencing as specified in the architecture.
"""

import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from jinja2 import Environment, FileSystemLoader

from spec2rtl.config.settings import Spec2RTLSettings
from spec2rtl.core.data_models import (
    CppCorrection,
    CppHlsTarget,
    CppTestbench,
    PseudocodePlan,
    PythonReference,
    StructuredInfoDict,
)
from spec2rtl.core.exceptions import CompilationError, PipelineStageError
from spec2rtl.llm.llm_client import LLMClient
from spec2rtl.utils.code_utils import clean_llm_code_output, patch_xls_headers

logger = logging.getLogger("spec2rtl.agents.module2")

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    keep_trailing_newline=True,
)

# Feature flag: if True, pass full function bodies in cross-function context.
# Set to False (default) to only pass signatures and prevent context ballooning.
INCLUDE_FULL_BODY_IN_CONTEXT: bool = False

# Compiler-specific rule sets for C++ code generation
# Note: rst_n should only be added for sequential designs, not combinational
_COMPILER_RULES: Dict[str, str] = {
    "google_xls": """
[GOOGLE XLS SPECIFIC RULES]
1. DO NOT use Xilinx Vitis HLS libraries. NO #include "ap_int.h". NO ap_uint.
2. DO NOT use Xilinx pragmas. NO #pragma HLS INTERFACE.
3. Use exactly one `#pragma hls_top` before the top-level evaluation function.
4. NO SYSTEM HEADERS: DO NOT use ANY #include directives (NO #include <cstdint>).
5. Use native C++ built-in types: unsigned char (8-bit), unsigned short (16-bit), unsigned int (32-bit), bool.
6. Only add rst_n (active-low reset) for SEQUENTIAL designs with registers.
7. For COMBINATIONAL designs: NO clock, NO reset, NO rst_n.
8. LOOP PRAGMAS: Precede combinational `for` loops with `#pragma hls_unroll yes`.
""",
    "vitis": """
[VITIS HLS SPECIFIC RULES]
1. Use standard Xilinx Vitis HLS libraries. #include "ap_int.h" and use ap_uint/ap_int types.
2. Apply appropriate #pragma HLS INTERFACE and #pragma HLS PIPELINE directives.
3. Use standard C++ libraries like <cstdint> (uint8_t, uint16_t, bool).
""",
}


class SubFunctionResult:
    """Container for the progressive coding output of a single sub-function.

    Attributes:
        name: Sub-function name.
        pseudocode: The architectural plan.
        python_code: The Python reference model.
        cpp_code: The synthesizable C++ code.
        testbench: The generated testbench (if any).
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.pseudocode: Optional[PseudocodePlan] = None
        self.python_code: Optional[PythonReference] = None
        self.cpp_code: Optional[CppHlsTarget] = None
        self.testbench: Optional[CppTestbench] = None


class ProgressiveCodingModule:
    """Module 2 orchestrator: progressive code generation.

    For each sub-function, runs the three-level coding chain
    (pseudo → Python → C++) with cross-level referencing, then
    generates and optionally runs a C++ testbench.

    Args:
        settings: Application settings.
        llm_client: Pre-configured LLM client.
    """

    def __init__(
        self,
        settings: Spec2RTLSettings | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self._settings = settings or Spec2RTLSettings.from_yaml()
        self._llm = llm_client or LLMClient(self._settings)
        self._compiler_key = self._settings.hls_compiler

    def run(
        self,
        info_dicts: List[StructuredInfoDict],
        target_compiler: str = "Google XLS",
    ) -> List[SubFunctionResult]:
        """Execute progressive coding for all sub-functions.

        Args:
            info_dicts: Structured info dicts from Module 1.
            target_compiler: Target HLS compiler name.

        Returns:
            List of SubFunctionResult with generated code at each level.
        """
        results: List[SubFunctionResult] = []
        previous_python: str = ""
        previous_cpp: str = ""

        for i, info_dict in enumerate(info_dicts):
            logger.info(
                "🔨 Module 2 — Sub-function %d/%d: %s",
                i + 1,
                len(info_dicts),
                info_dict.sub_function_name,
            )
            result = SubFunctionResult(name=info_dict.sub_function_name)

            # Step 1: Pseudocode
            result.pseudocode = self._generate_pseudocode(info_dict)

            # Step 2: Python reference model (with cross-level context)
            result.python_code = self._generate_python(
                result.pseudocode, previous_python
            )
            # Append only function signatures to avoid context ballooning (Phase 3.1)
            if INCLUDE_FULL_BODY_IN_CONTEXT:
                previous_python += f"\n# --- {info_dict.sub_function_name} ---\n"
                previous_python += result.python_code.python_code
            else:
                sigs = _extract_python_signatures(result.python_code.python_code)
                previous_python += f"\n# --- {info_dict.sub_function_name} (interface) ---\n"
                previous_python += sigs

            # Step 3: C++ HLS code (with cross-level context)
            result.cpp_code = self._generate_cpp(
                result.python_code, target_compiler, previous_cpp
            )

            # Apply XLS header patching if needed
            if "xls" in target_compiler.lower():
                result.cpp_code.cpp_code = patch_xls_headers(
                    result.cpp_code.cpp_code
                )

            # Append only C++ function signatures (Phase 3.1)
            if INCLUDE_FULL_BODY_IN_CONTEXT:
                previous_cpp += f"\n// --- {info_dict.sub_function_name} ---\n"
                previous_cpp += result.cpp_code.cpp_code
            else:
                sigs = _extract_cpp_signatures(result.cpp_code.cpp_code)
                previous_cpp += f"\n// --- {info_dict.sub_function_name} (interface) ---\n"
                previous_cpp += sigs

            # Step 4: Testbench generation
            result.testbench = self._generate_testbench(
                result.pseudocode, target_compiler, result.cpp_code.cpp_code
            )

            results.append(result)

        logger.info("Module 2 complete: %d sub-functions coded.", len(results))
        return results

    def _generate_pseudocode(
        self,
        info_dict: StructuredInfoDict,
    ) -> PseudocodePlan:
        """Generate architectural pseudocode from the info dictionary.

        Args:
            info_dict: Structured information for this sub-function.

        Returns:
            A PseudocodePlan with classified hardware and logic steps.
        """
        template = _jinja_env.get_template("module2_pseudocoder.jinja2")
        prompt = template.render(
            sub_function_info_json=info_dict.model_dump_json(indent=2),
        )
        messages = [
            {"role": "system", "content": "You are a Senior Hardware Architect."},
            {"role": "user", "content": prompt},
        ]
        return self._llm.generate(messages, PseudocodePlan)

    def _generate_python(
        self,
        plan: PseudocodePlan,
        previous_code: str,
    ) -> PythonReference:
        """Generate a Python reference model from pseudocode.

        Args:
            plan: The pseudocode plan.
            previous_code: Accumulated Python from prior sub-functions.

        Returns:
            A PythonReference with bit-accurate Python code.
        """
        template = _jinja_env.get_template("module2_python_coder.jinja2")
        prompt = template.render(
            plan_module_name=plan.module_name,
            plan_inputs_outputs_json=json.dumps(plan.inputs_outputs),
            plan_logic_steps=plan.logic_steps,
            previous_code=previous_code if previous_code.strip() else None,
        )
        messages = [
            {"role": "system", "content": "You are a bit-accurate Python hardware modeling expert."},
            {"role": "user", "content": prompt},
        ]
        return self._llm.generate(messages, PythonReference)

    def _generate_cpp(
        self,
        py_model: PythonReference,
        target_compiler: str,
        previous_cpp: str,
    ) -> CppHlsTarget:
        """Translate Python to synthesizable C++ for the target compiler.

        Args:
            py_model: The Python reference model.
            target_compiler: Target HLS compiler name.
            previous_cpp: Accumulated C++ from prior sub-functions.

        Returns:
            A CppHlsTarget with compiler-compliant C++ code.
        """
        template = _jinja_env.get_template("module2_cpp_coder.jinja2")

        # Select compiler-specific rules
        if "vitis" in target_compiler.lower():
            rules = _COMPILER_RULES["vitis"]
        else:
            rules = _COMPILER_RULES["google_xls"]

        prompt = template.render(
            target_compiler=target_compiler,
            compiler_specific_rules=rules,
            python_code=py_model.python_code,
            previous_cpp=previous_cpp if previous_cpp.strip() else None,
        )
        messages = [
            {
                "role": "system",
                "content": f"You are an expert hardware compiler engineer targeting {target_compiler}.",
            },
            {"role": "user", "content": prompt},
        ]
        return self._llm.generate(messages, CppHlsTarget)

    def _generate_testbench(
        self,
        plan: PseudocodePlan,
        target_compiler: str,
        generated_cpp: str,
    ) -> CppTestbench:
        """Generate a C++ testbench for the sub-function.

        Args:
            plan: The pseudocode plan with I/O definitions.
            target_compiler: Target HLS compiler name.
            generated_cpp: The C++ code to test.

        Returns:
            A CppTestbench with algorithmic verification code.
        """
        template = _jinja_env.get_template("module2_verifier.jinja2")

        if "vitis" in target_compiler.lower():
            rules = _COMPILER_RULES["vitis"]
        else:
            rules = _COMPILER_RULES["google_xls"]

        safe_name = (
            plan.module_name.strip().lower().replace(" ", "_").replace("-", "_")
        )
        module_filename = f"{safe_name}_hls.cpp"

        prompt = template.render(
            target_compiler=target_compiler,
            compiler_specific_rules=rules,
            module_filename=module_filename,
            plan_module_name=plan.module_name,
            plan_inputs_outputs_json=json.dumps(plan.inputs_outputs),
            plan_logic_steps=plan.logic_steps,
            generated_cpp=generated_cpp,
        )
        messages = [
            {
                "role": "system",
                "content": f"You are an expert hardware verification engineer targeting {target_compiler}.",
            },
            {"role": "user", "content": prompt},
        ]
        return self._llm.generate(messages, CppTestbench)

    @staticmethod
    def syntax_check(filepath: Path) -> str:
        """Run a g++ syntax check on a C++ file.

        Args:
            filepath: Path to the C++ source file.

        Returns:
            'SUCCESS' if syntax is valid, otherwise the compiler error.
        """
        try:
            subprocess.run(
                ["g++", "-fsyntax-only", str(filepath)],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            return "SUCCESS"
        except subprocess.CalledProcessError as exc:
            return exc.stderr
        except subprocess.TimeoutExpired:
            return "ERROR: Syntax check timed out after 30s"

    @staticmethod
    def logical_verify(cpp_path: Path, tb_path: Path, build_dir: Path) -> tuple[bool, str]:
        """
        Compile the C++ code with its testbench and execute it to verify logical correctness.
        Returns a tuple of (Success Boolean, Output/Error Log).
        """
        binary_path = build_dir / f"{cpp_path.stem}_tb_bin"
        
        try:
            # 1. Compile C++ and Testbench together
            subprocess.run(
                ["g++", str(cpp_path), str(tb_path), "-o", str(binary_path)],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            
            # 2. Execute the compiled testbench
            exec_proc = subprocess.run(
                [str(binary_path)],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            return True, exec_proc.stdout

        except subprocess.CalledProcessError as exc:
            # Captures compilation errors, linking errors, or assertion failures during execution
            error_msg = exc.stderr if exc.stderr else exc.stdout
            return False, f"Logical Verification Failed:\n{error_msg}"
        except subprocess.TimeoutExpired:
            return False, "Logical Verification Failed: Execution timed out after 30s."

    def fix_compilation_error(
        self,
        bad_code: str,
        error_log: str,
        target_compiler: str,
    ) -> CppCorrection:
        """Use the reflection loop to fix a compilation error.

        Args:
            bad_code: The C++ code that failed compilation.
            error_log: The compiler error output.
            target_compiler: Target HLS compiler name.

        Returns:
            A CppCorrection with the fixed code and explanation.
        """
        if "vitis" in target_compiler.lower():
            rules = _COMPILER_RULES["vitis"]
        else:
            rules = _COMPILER_RULES["google_xls"]

        system_prompt = (
            f"You are an expert {target_compiler} C++ debugging agent.\n\n"
            f"CRITICAL STRICT RULES:\n{rules}\n"
            "- DO NOT include ANY comments. Provide ONLY the raw logic.\n"
            "- Output as a JSON string. Escape newlines as \\\\n."
        )
        user_prompt = (
            f"The following C++ HLS code failed to compile.\n\n"
            f"[CODE]\n{bad_code}\n\n"
            f"[COMPILER ERROR LOG]\n{error_log}\n\n"
            "Fix the errors and provide the corrected C++ code."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self._llm.generate(messages, CppCorrection)


# ──────────────────────────────────────────────────────────────
# Signature extraction helpers (Phase 3.1)
# ──────────────────────────────────────────────────────────────

# Matches C++ function signatures: optional return type + name + params
# Intentionally does NOT match bodies — stops at '{' or ';'
_CPP_SIG_PATTERN = re.compile(
    r"^[ \t]*(?:(?:inline|static|extern|virtual|constexpr)\s+)?"
    r"(?:[\w:<>*& ]+\s+)?(?P<name>\w+)\s*\([^)]*\)\s*(?:const\s*)?\s*(?=[{;])",
    re.MULTILINE,
)

# Matches Python 'def' lines only (no body)
_PY_SIG_PATTERN = re.compile(
    r"^[ \t]*(?:async\s+)?def\s+\w+\s*\([^)]*\).*?:",
    re.MULTILINE,
)


def _extract_cpp_signatures(code: str) -> str:
    """Extract C++ function prototype lines (no bodies) from a code block.

    Used to pass only the interface of previously generated sub-functions
    into the LLM context, preventing context window saturation.

    Args:
        code: Full C++ source code string.

    Returns:
        Newline-joined string of function signature lines.
    """
    matches = _CPP_SIG_PATTERN.findall(code)
    # Re-extract the full matching lines (findall returns only named groups)
    sigs: list[str] = []
    for m in _CPP_SIG_PATTERN.finditer(code):
        line = m.group(0).rstrip(" {;")
        sigs.append(line.strip() + ";")
    result = "\n".join(sigs) if sigs else "// (no signatures found)"
    logger.debug("Extracted %d C++ signatures for context", len(sigs))
    return result


def _extract_python_signatures(code: str) -> str:
    """Extract Python function 'def' header lines (no bodies) from a code block.

    Args:
        code: Python source code string.

    Returns:
        Newline-joined string of def header lines (ending with '...').
    """
    sigs: list[str] = []
    for m in _PY_SIG_PATTERN.finditer(code):
        sigs.append(m.group(0).strip() + " ...")
    result = "\n".join(sigs) if sigs else "# (no signatures found)"
    logger.debug("Extracted %d Python signatures for context", len(sigs))
    return result
