"""Pydantic data models defining the contracts between Spec2RTL agents.

These schemas act as rigid interfaces ensuring that data flowing between
pipeline stages is validated, typed, and serializable. Each model
corresponds to the output of a specific agent or pipeline stage.
"""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────
# Enumerations
# ──────────────────────────────────────────────────────────────

class HardwareClassification(str, Enum):
    """Classification of hardware module type."""

    COMBINATIONAL = "COMBINATIONAL"
    SEQUENTIAL_PIPELINE = "SEQUENTIAL_PIPELINE"
    STATE_MACHINE = "STATE_MACHINE"


class ReflectionPath(str, Enum):
    """Routing paths for the Module 3 Adaptive Reflection Agent."""

    REVISE_INSTRUCTIONS = "PATH_1_REVISE_INSTRUCTIONS"
    FIX_PREVIOUS_SUBFUNCTIONS = "PATH_2_FIX_PREVIOUS"
    RETRY_CURRENT = "PATH_3_RETRY_CURRENT"
    HUMAN_INTERVENTION = "PATH_4_HUMAN_INTERVENTION"


# ──────────────────────────────────────────────────────────────
# Module 1: Understanding & Reasoning
# ──────────────────────────────────────────────────────────────

class SpecSection(BaseModel):
    """A single section extracted from the specification document."""

    section_title: str = Field(
        description="Title or heading of the specification section.",
    )
    content: str = Field(
        description="Raw text content of this section.",
    )
    page_numbers: List[int] = Field(
        default_factory=list,
        description="Source page numbers in the original PDF.",
    )


class SpecSummary(BaseModel):
    """Condensed summary of one specification section."""

    section_title: str = Field(
        description="Original section title.",
    )
    summary: str = Field(
        description="Concise summary retaining key technical details.",
    )
    key_parameters: List[str] = Field(
        default_factory=list,
        description="Important numerical values, signal names, or constraints.",
    )


class VerifierResult(BaseModel):
    """Result of the verification agent for structured info dictionaries."""

    status: str = Field(
        description="Verification status: must be exactly 'APPROVED' or 'REJECTED'",
    )
    feedback: str = Field(
        default="",
        description="Detailed feedback if REJECTED, empty string if APPROVED.",
    )


class SubFunction(BaseModel):
    """A single decomposed sub-function in the implementation plan."""

    name: str = Field(
        description="Descriptive name for this sub-function.",
    )
    description: str = Field(
        description="What this sub-function computes or implements.",
    )
    inputs: Dict[str, str] = Field(
        default_factory=dict,
        description="Input signal names mapped to their bit-widths/types.",
    )
    outputs: Dict[str, str] = Field(
        default_factory=dict,
        description="Output signal names mapped to their bit-widths/types.",
    )
    dependencies: List[str] = Field(
        default_factory=list,
        description="Names of other sub-functions this depends on.",
    )


class DecompositionPlan(BaseModel):
    """Ordered list of sub-functions forming the implementation plan."""

    module_name: str = Field(
        description="Top-level hardware module name.",
    )
    sub_functions: List[SubFunction] = Field(
        description="Sequential list of sub-functions to implement.",
    )
    hardware_classification: HardwareClassification = Field(
        description="Classification of the overall hardware type.",
    )


class StructuredInfoDict(BaseModel):
    """Comprehensive structured dictionary for a single sub-function.

    Produced by the Description Agent and validated by the Verifier.
    """

    sub_function_name: str = Field(
        description="Name of the sub-function.",
    )
    functionality: str = Field(
        description="Detailed description of the expected behavior.",
    )
    inputs: Dict[str, str] = Field(
        description="Input signals with types and bit-widths.",
    )
    outputs: Dict[str, str] = Field(
        description="Output signals with types and bit-widths.",
    )
    state_elements: List[str] = Field(
        default_factory=list,
        description="Registers, memories, or history arrays required.",
    )
    constraints: List[str] = Field(
        default_factory=list,
        description="Timing, area, or synthesis constraints.",
    )
    spec_references: List[str] = Field(
        default_factory=list,
        description="References to original spec sections or page numbers.",
    )


# ──────────────────────────────────────────────────────────────
# Module 2: Progressive Coding
# ──────────────────────────────────────────────────────────────

class PseudocodePlan(BaseModel):
    """Architectural pseudocode plan extracted from the specification."""

    module_name: str = Field(
        description="The name of the hardware module.",
    )
    target_compiler: str = Field(
        description=(
            "The target HLS compiler (e.g., 'Google XLS', 'Vitis HLS'). "
            "Defaults to 'Google XLS' if not specified."
        ),
    )
    hardware_classification: str = Field(
        description=(
            "Classify as exactly one: 'COMBINATIONAL', "
            "'SEQUENTIAL_PIPELINE', or 'STATE_MACHINE'."
        ),
    )
    inputs_outputs: Dict[str, str] = Field(
        description="Dictionary of signal names and their widths.",
    )
    state_elements: List[str] = Field(
        default_factory=list,
        description=(
            "List any required memory elements, registers, or history "
            "arrays. Return empty list if purely combinational."
        ),
    )
    logic_steps: str = Field(
        description="Step-by-step pseudocode logic.",
    )


class PythonReference(BaseModel):
    """Executable Python reference model of the hardware logic."""

    python_code: str = Field(
        description="Executable Python code representing the hardware logic.",
    )


class CppHlsTarget(BaseModel):
    """Synthesizable C++ code ready for HLS compilation."""

    cpp_code: str = Field(
        description="Synthesizable C++ code ready for HLS.",
    )
    compiler_directives: str = Field(
        default="None",
        description=(
            "Comma-separated list of compiler-specific directives used, "
            "or 'None'."
        ),
    )


class CppCorrection(BaseModel):
    """Output of the Reflection Agent's code fix attempt."""

    fixed_cpp_code: str = Field(
        description="The corrected C++ code.",
    )
    explanation: str = Field(
        description="Brief explanation of what was fixed.",
    )


class CppTestbench(BaseModel):
    """C++ testbench for validating the generated hardware module."""

    testbench_code: str = Field(
        description=(
            "C++ testbench code containing a main() function to validate "
            "the module."
        ),
    )
    test_cases_covered: str = Field(
        description="Brief comma-separated list of the test scenarios covered.",
    )


# ──────────────────────────────────────────────────────────────
# Module 3: Adaptive Reflection
# ──────────────────────────────────────────────────────────────

class ReflectionDecision(BaseModel):
    """Decision output of the Reflection Agent's error analysis."""

    chosen_path: ReflectionPath = Field(
        description="The routing path selected for error recovery.",
    )
    reasoning: str = Field(
        description="Explanation of why this path was chosen.",
    )
    error_source: str = Field(
        description="Identified source of the error (sub-function, stage, etc.).",
    )
    target_sub_function: Optional[str] = Field(
        default=None,
        description=(
            "Name of the sub-function to re-generate, if applicable "
            "(for paths 2 and 3)."
        ),
    )

class HLSRecoveryPlan(BaseModel):
    """Output from the HLS Reflection Agent (Module 4.5)."""

    fixed_cpp_code: str = Field(
        description="The fully corrected C++ code that addresses the synthesis error."
    )
    learned_rule: str | None = Field(
        default=None,
        description="A concise rule to add to the compiler constraints to prevent this error in the future."
    )
    reasoning: str = Field(
        description="Explanation of the error cause and why this fix works."
    )

# ──────────────────────────────────────────────────────────────
# Module 4: HLS Optimization
# ──────────────────────────────────────────────────────────────

class HLSConstraints(BaseModel):
    """Compiler-specific constraints queried from the HLS backend."""

    compiler_name: str = Field(
        description="Name of the HLS compiler.",
    )
    type_mappings: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping from generic types to compiler-specific types.",
    )
    forbidden_constructs: List[str] = Field(
        default_factory=list,
        description="C++ constructs not allowed (e.g., 'dynamic_memory').",
    )
    required_pragmas: List[str] = Field(
        default_factory=list,
        description="Required pragma directives for this compiler.",
    )
    header_rules: str = Field(
        default="",
        description="Rules about which headers can/cannot be included.",
    )


class HLSSynthesisResult(BaseModel):
    """Result of an HLS synthesis run."""

    success: bool = Field(
        description="Whether the synthesis completed successfully.",
    )
    rtl_output_path: Optional[str] = Field(
        default=None,
        description="Path to the generated RTL file, if successful.",
    )
    log_summary: str = Field(
        default="",
        description="Summary of the synthesis log.",
    )
    error_log: Optional[str] = Field(
        default=None,
        description="Error details if synthesis failed.",
    )
