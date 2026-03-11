"""Module 4.5: HLS Reflection & Prompt Adaptation.

This module acts as a recovery loop for Module 4. If HLS synthesis fails,
this module analyzes the compiler stderr, fixes the C++ code, and extracts
new rules to append to the active HLS constraints.
"""

import logging
from pathlib import Path

from autogen_agentchat.agents import AssistantAgent

from spec2rtl.config.settings import Spec2RTLSettings
from spec2rtl.core.data_models import HLSConstraints, HLSRecoveryPlan
from spec2rtl.llm.llm_client import LLMClient

logger = logging.getLogger(__name__)


class HLSReflectionModule:
    """Analyzes HLS synthesis failures and fixes code/constraints."""

    def __init__(self, config: Spec2RTLSettings):
        self.config = config
        self.llm_client = LLMClient(config.default_model, config.fallback_models)
        self._prompt_dir = Path(__file__).parent.parent / "prompts"

    def _load_prompt(self, template_name: str, **kwargs) -> str:
        """Load and render a Jinja2 prompt template."""
        from jinja2 import Environment, FileSystemLoader

        env = Environment(loader=FileSystemLoader(self._prompt_dir))
        template = env.get_template(template_name)
        return template.render(**kwargs)

    def recover(
        self, cpp_code: str, error_log: str, target_compiler: str, current_constraints: HLSConstraints
    ) -> tuple[str, HLSConstraints]:
        """Analyze a synthesis failure, fix the code, and update constraints.

        Args:
            cpp_code: The C++ code that failed synthesis.
            error_log: The stderr output from the HLS compiler.
            target_compiler: The name of the compiler (e.g., "Google XLS").
            current_constraints: The active constraints for this compiler.

        Returns:
            A tuple containing:
                - The fixed C++ code string.
                - The updated HLSConstraints object (with any new rules).
        """
        logger.info("🔍 Analyzing HLS compiler error...")

        sys_prompt = self._load_prompt(
            "hls_reflector.jinja2",
            target_compiler=target_compiler,
            cpp_code=cpp_code,
            error_log=error_log,
        )

        agent = AssistantAgent(
            name="hls_reflector",
            model_client=self.llm_client,
            system_message=sys_prompt,
            response_format=HLSRecoveryPlan,
        )

        # We trigger the agent with a dummy user message since the system
        # prompt contains all the context (code and error log).
        response = self.llm_client.create(
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": "Analyze the error and provide the recovery plan."},
            ],
            response_format=HLSRecoveryPlan,
        )

        assert isinstance(response, HLSRecoveryPlan)

        logger.info("✅ HLS error analyzed. C++ code patched.")

        if response.learned_rule:
            logger.info(f"🧠 Learned new constraint: {response.learned_rule}")
            current_constraints.forbidden_patterns.append(response.learned_rule)

        return response.fixed_cpp_code, current_constraints
