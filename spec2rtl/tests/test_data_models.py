"""Unit tests for Pydantic data models."""

import unittest

from spec2rtl.core.data_models import (
    CppHlsTarget,
    DecompositionPlan,
    HardwareClassification,
    HLSConstraints,
    PseudocodePlan,
    PythonReference,
    ReflectionDecision,
    ReflectionPath,
    SpecSummary,
    StructuredInfoDict,
    SubFunction,
)


class TestSpecSummary(unittest.TestCase):
    """Tests for the SpecSummary model."""

    def test_valid_summary(self) -> None:
        summary = SpecSummary(
            section_title="I/O Interface",
            summary="8-bit unsigned input, 8-bit unsigned output",
            key_parameters=["data_in: 8-bit", "data_out: 8-bit"],
        )
        self.assertEqual(summary.section_title, "I/O Interface")
        self.assertEqual(len(summary.key_parameters), 2)

    def test_default_key_parameters(self) -> None:
        summary = SpecSummary(section_title="Test", summary="Test summary")
        self.assertEqual(summary.key_parameters, [])


class TestDecompositionPlan(unittest.TestCase):
    """Tests for the DecompositionPlan model."""

    def test_valid_plan(self) -> None:
        plan = DecompositionPlan(
            module_name="FIR Filter",
            sub_functions=[
                SubFunction(
                    name="shift_register",
                    description="Shifts data through taps",
                    inputs={"data_in": "8-bit unsigned"},
                    outputs={"tap_values": "array of 4x 8-bit"},
                ),
            ],
            hardware_classification=HardwareClassification.SEQUENTIAL_PIPELINE,
        )
        self.assertEqual(plan.module_name, "FIR Filter")
        self.assertEqual(len(plan.sub_functions), 1)
        self.assertEqual(plan.hardware_classification, HardwareClassification.SEQUENTIAL_PIPELINE)

    def test_serialization_roundtrip(self) -> None:
        plan = DecompositionPlan(
            module_name="ALU",
            sub_functions=[],
            hardware_classification=HardwareClassification.COMBINATIONAL,
        )
        json_str = plan.model_dump_json()
        restored = DecompositionPlan.model_validate_json(json_str)
        self.assertEqual(restored.module_name, plan.module_name)


class TestReflectionDecision(unittest.TestCase):
    """Tests for the ReflectionDecision model."""

    def test_valid_decision(self) -> None:
        decision = ReflectionDecision(
            chosen_path=ReflectionPath.RETRY_CURRENT,
            reasoning="Error is a simple type mismatch in current sub-function",
            error_source="C++ type casting",
            target_sub_function="accumulator",
        )
        self.assertEqual(decision.chosen_path, ReflectionPath.RETRY_CURRENT)
        self.assertEqual(decision.target_sub_function, "accumulator")

    def test_human_intervention_no_target(self) -> None:
        decision = ReflectionDecision(
            chosen_path=ReflectionPath.HUMAN_INTERVENTION,
            reasoning="Cannot determine error source",
            error_source="Unknown",
        )
        self.assertIsNone(decision.target_sub_function)


class TestPseudocodePlan(unittest.TestCase):
    """Tests for the PseudocodePlan model."""

    def test_with_state_elements(self) -> None:
        plan = PseudocodePlan(
            module_name="Moving Average",
            target_compiler="Google XLS",
            hardware_classification="SEQUENTIAL_PIPELINE",
            inputs_outputs={"data_in": "8-bit", "data_out": "8-bit"},
            state_elements=["history[4]: 8-bit unsigned array"],
            logic_steps="1. Shift data\n2. Sum\n3. Divide by 4",
        )
        self.assertEqual(len(plan.state_elements), 1)

    def test_combinational_no_state(self) -> None:
        plan = PseudocodePlan(
            module_name="Adder",
            target_compiler="Google XLS",
            hardware_classification="COMBINATIONAL",
            inputs_outputs={"a": "8-bit", "b": "8-bit", "sum": "9-bit"},
            logic_steps="sum = a + b",
        )
        self.assertEqual(plan.state_elements, [])


if __name__ == "__main__":
    unittest.main()
