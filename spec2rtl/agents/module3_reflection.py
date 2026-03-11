"""Module 3: Adaptive Reflection.

Dynamically identifies and traces error sources across all generated
sub-functions, then routes to the appropriate recovery action using
a 4-path decision framework.

Datapath: Failed Verification → Error Analysis → Strategic Routing

Path 1: Return to Module 1 to revise specification understanding
Path 2: Re-generate previous sub-functions that caused cascading errors
Path 3: Retry current sub-function in Module 2
Path 4: Escalate to human intervention
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from jinja2 import Environment, FileSystemLoader

from spec2rtl.config.settings import Spec2RTLSettings
from spec2rtl.core.data_models import ReflectionDecision, ReflectionPath
from spec2rtl.core.exceptions import PipelineStageError
from spec2rtl.llm.llm_client import LLMClient

logger = logging.getLogger("spec2rtl.agents.module3")

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    keep_trailing_newline=True,
)


class GenerationTrajectory:
    """Record of the complete generation history for a sub-function.

    Used by the Analysis Agent to trace errors back to their origin
    in the progressive coding pipeline.

    Attributes:
        sub_function_name: Name of the sub-function.
        pseudocode: The generated pseudocode plan (serialized).
        python_code: The generated Python reference model.
        cpp_code: The generated C++ code.
        compilation_log: Compiler output (stdout/stderr).
        testbench_result: Testbench execution output.
        error_description: Description of the verification failure.
    """

    def __init__(self, sub_function_name: str) -> None:
        self.sub_function_name = sub_function_name
        self.pseudocode: str = ""
        self.python_code: str = ""
        self.cpp_code: str = ""
        self.compilation_log: str = ""
        self.testbench_result: str = ""
        self.error_description: str = ""

    def to_dict(self) -> Dict[str, str]:
        """Serialize the trajectory for prompt injection.

        Returns:
            Dictionary with all trajectory stages.
        """
        return {
            "sub_function_name": self.sub_function_name,
            "pseudocode": self.pseudocode[:2000],
            "python_code": self.python_code[:2000],
            "cpp_code": self.cpp_code[:2000],
            "compilation_log": self.compilation_log[:1000],
            "testbench_result": self.testbench_result[:1000],
            "error_description": self.error_description,
        }


class ReflectionModule:
    """Module 3 orchestrator: adaptive reflection and error recovery.

    When a verification failure occurs, this module:
    1. Analyzes the full generation trajectory to find the error source
    2. Decides the optimal recovery path (1 of 4 routing options)
    3. Returns a ReflectionDecision that the pipeline uses to re-route

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

    def analyze_and_decide(
        self,
        trajectory: GenerationTrajectory,
    ) -> ReflectionDecision:
        """Run the full analysis → reflection pipeline.

        Args:
            trajectory: Complete generation history for the failed
                sub-function.

        Returns:
            A ReflectionDecision with the chosen recovery path.
        """
        logger.info(
            "🔍 Module 3 — Analyzing failure for: %s",
            trajectory.sub_function_name,
        )

        # Stage 1: Analysis — trace the error source
        analysis_result = self._run_analysis(trajectory)

        # Stage 2: Reflection — decide recovery path
        decision = self._run_reflection(
            analysis_result,
            trajectory.sub_function_name,
        )

        logger.info(
            "Module 3 decision: %s → %s (reason: %s)",
            trajectory.sub_function_name,
            decision.chosen_path.value,
            decision.reasoning[:100],
        )
        return decision

    def _run_analysis(self, trajectory: GenerationTrajectory) -> str:
        """Run the Analysis Agent to trace the error source.

        Args:
            trajectory: Generation history to analyze.

        Returns:
            Analysis text describing the likely error source.
        """
        template = _jinja_env.get_template("module3_analysis.jinja2")
        prompt = template.render(
            trajectory_json=json.dumps(trajectory.to_dict(), indent=2),
            error_description=trajectory.error_description,
        )
        messages = [
            {
                "role": "system",
                "content": "You are a Hardware Generation Trajectory Analyst.",
            },
            {"role": "user", "content": prompt},
        ]

        # Use raw completion for the analysis (free-form text output)
        from litellm import completion as raw_completion

        response = raw_completion(
            model=self._llm.default_model,
            messages=messages,
            max_tokens=2048,
            temperature=0.0,
        )
        return response.choices[0].message.content.strip()

    def _run_reflection(
        self,
        analysis_result: str,
        current_sub_function: str,
    ) -> ReflectionDecision:
        """Run the Reflection Agent to decide the recovery path.

        Args:
            analysis_result: Error analysis from the Analysis Agent.
            current_sub_function: Name of the failing sub-function.

        Returns:
            A ReflectionDecision with path selection and reasoning.
        """
        template = _jinja_env.get_template("module3_reflection.jinja2")
        prompt = template.render(
            analysis_result=analysis_result,
            current_sub_function_name=current_sub_function,
        )
        messages = [
            {
                "role": "system",
                "content": "You are a Hardware Pipeline Recovery Strategist.",
            },
            {"role": "user", "content": prompt},
        ]
        return self._llm.generate(messages, ReflectionDecision)

    @staticmethod
    def format_error_payload(
        error_log: str,
        stage: str,
        max_length: int = 2000,
    ) -> str:
        """Format an error log into a clean payload for reflection.

        Per SKILL.md: error handlers must format the stack trace and
        stdout into a clean, truncated payload for the ReflectionAgent.

        Args:
            error_log: Raw error text (stdout/stderr/traceback).
            stage: Pipeline stage where the error occurred.
            max_length: Maximum character length of the payload.

        Returns:
            A formatted, truncated error payload string.
        """
        header = f"[ERROR in {stage}]\n"
        available = max_length - len(header)

        if len(error_log) > available:
            truncated = error_log[:available - 50]
            truncated += f"\n... [TRUNCATED: {len(error_log)} total chars]"
            return header + truncated

        return header + error_log
