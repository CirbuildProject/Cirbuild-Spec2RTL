# 🛠️ SYSTEM DIRECTIVE: Comprehensive Spec2RTL Pipeline & Synthesis Fixes

**Objective:** Resolve compilation mismatch, linking (ODR) violations, asymmetric reflection loops, interface flattening, and logic translation errors to harden the pipeline for rigorous benchmarking.

## DIRECTIVE 1: Synchronize C++ Implementation Filename

**Context:** The testbench generation prompt instructs the LLM that the target module is named `[module]_hls.cpp`. However, the pipeline writes the implementation file as `[module]_check.cpp`, causing fatal `#include` errors during compilation.

* **Target File:** `spec2rtl/pipeline.py`
* **Target Method:** `Spec2RTLPipeline._verify_with_reflection`

**Required Changes:**

1. Locate the first instance of `tmp_path = write_to_build_dir(...)` (around line 235).
2. Change the filename argument from `f"{result.name}_check.cpp"` to `f"{result.name}_hls.cpp"`.
3. Locate the reflection loop block handling `ReflectionPath.RETRY_CURRENT` (around line 280) and apply the exact same filename change to the `tmp_path` variable inside the loop.

## DIRECTIVE 2: Prevent ODR (Multiple Definition) Violations

**Context:** The LLM-generated testbench natively `#includes` the C++ implementation file. Passing both the implementation file and the testbench file to `g++` causes the compiler to process the implementation logic twice, resulting in a linker failure.

* **Target File:** `spec2rtl/agents/module2_coding.py`
* **Target Method:** `ProgressiveCodingModule.logical_verify`

**Required Changes:**

1. Locate the `subprocess.run` command that invokes `g++` (around line 273).
2. Remove `str(cpp_path)` from the command list.
3. The updated command array must be:
   ```python
   ["g++", str(tb_path), "-o", str(binary_path)]
   ```

## DIRECTIVE 3: Implement Symmetrical Reflection Routing

**Context:** Currently, when compilation fails due to a testbench error, the reflection loop only requests a fix for the `cpp_code` and re-runs the verification using the original, broken `testbench_code`. The agent must be able to view and fix both files simultaneously.

### Target 3A: Data Models (`spec2rtl/core/data_models.py`)

1. Locate the `CppCorrection` Pydantic model.
2. Add an optional string field: `fixed_testbench_code: Optional[str] = None`.

### Target 3B: Module 2 Error Handler (`spec2rtl/agents/module2_coding.py`)

1. Locate method: `ProgressiveCodingModule.fix_compilation_error`.
2. Add `bad_testbench: Optional[str] = None` to the method signature.
3. Update `user_prompt` to dynamically include the testbench code if it is provided:
   `"Here is the Testbench code that was used:\n[TESTBENCH]\n{bad_testbench}"`.
4. Update `system_prompt` to explicitly state: `"If the compiler error originates from the testbench logic, provide the corrected testbench code in the fixed_testbench_code JSON field."`

### Target 3C: Pipeline Integration (`spec2rtl/pipeline.py`)

1. Locate method: `Spec2RTLPipeline._verify_with_reflection`.
2. Inside the `ReflectionPath.RETRY_CURRENT` block, extract the current testbench code: `current_tb = result.testbench.testbench_code if result.testbench else None`.
3. Update the call to `self._module2.fix_compilation_error(cpp_code, status, compiler, current_tb)`.
4. After receiving the correction object, conditionally update the testbench result:

   ```python
   if correction.fixed_testbench_code and result.testbench:
       result.testbench.testbench_code = clean_llm_code_output(correction.fixed_testbench_code)
   ```

## DIRECTIVE 4: Enforce Output Unpacking (Pointer/Reference Passing)

**Context:** HLS compilers flatten structs returned by value, destroying the intended multi-port interface of the hardware module.

* **Target Files:** `spec2rtl/prompts/module2_cpp_coder.jinja2` & `spec2rtl/agents/module2_coding.py` (`_COMPILER_RULES`)

**Required Changes:**

1. Update both the `google_xls` and `vitis` rules in `_COMPILER_RULES` to include this strict directive:
   > "OUTPUT INTERFACE RULE: DO NOT return a struct by value. If a module has multiple outputs, pass them as pointers or references in the function signature (e.g., void TopModule(..., bool* flush, uint32_t* new_pc))."

## DIRECTIVE 5: Dynamic Reset and Interface Mapping

**Context:** The LLM is overriding textually specified active-high resets (e.g., `rst`) with hardcoded active-low defaults (`rst_n`) injected by the system prompts.

* **Target File:** `spec2rtl/agents/module2_coding.py`

**Required Changes:**

1. Delete the line: `Only add rst_n (active-low reset) for SEQUENTIAL designs with registers.` from `_COMPILER_RULES`.
2. Inject a dynamic rule into the prompt generation that states: `"Use EXACTLY the port names and reset polarities defined in the JSON plan. Do not invent signal names like rst_n if rst is requested in the inputs."`

## DIRECTIVE 6: Literal Value Translation Enforcement

**Context:** The underlying LLM is failing to translate Verilog bit-literals (like `6'b011111`) into explicit numerical equivalents in C++, instead inventing arbitrary state integers which breaks hardware logic.

* **Target Files:** `spec2rtl/prompts/module2_python_coder.jinja2` & `spec2rtl/prompts/module2_cpp_coder.jinja2`

**Required Changes:**

1. Add the following system directive to both templates:
   > "BIT-VECTOR LITERALS: You must explicitly convert Verilog bit-literals (e.g., 6'b011111) into their exact C++/Python hexadecimal or decimal equivalents (e.g., 0x1F or 31). Never replace explicit bit patterns with arbitrary integer states."

## DIRECTIVE 7: Post-Synthesis Port Verification

**Context:** `g++` compilation does not guarantee the correct hardware interface was generated. The pipeline must verify the final Verilog ports against the original specification.

* **Target File:** `spec2rtl/pipeline.py`

**Required Changes:**

1. Add a validation step after Module 4 synthesis completes.
2. Parse the generated `.v` file's module declaration to extract the actual generated port list.
3. Compare these ports against `DecompositionPlan.inputs_outputs`.
4. If a severe mismatch is detected (e.g., detecting a collapsed output bus like `out [71:0]`), trigger a `ReflectionPath.RETRY_CURRENT` cycle with the explicit error payload: `"HLS collapsed the ports. Rewrite the C++ to use pass-by-reference/pointers for all outputs instead of returning a struct."`