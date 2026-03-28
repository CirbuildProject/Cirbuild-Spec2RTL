"""Module 1: Iterative Understanding and Reasoning.

Transforms unstructured specification documents into structured,
step-by-step implementation plans using a multi-agent workflow.

Datapath: Raw Spec → Summaries → Decomposed Sub-Functions → Structured Info Dict

Uses Custom, sequential, schema-driven, deterministic agentic pipeline.
Prompts are loaded from Jinja2 templates in the prompts/ directory.
"""

import json
import logging
from pathlib import Path
from typing import List

from jinja2 import Environment, FileSystemLoader

from spec2rtl.config.settings import Spec2RTLSettings
from spec2rtl.core.data_models import (
    DecompositionPlan,
    SpecSummary,
    StructuredInfoDict,
)
from spec2rtl.core.exceptions import PipelineStageError
from spec2rtl.llm.llm_client import LLMClient
from spec2rtl.utils.pdf_parser import PDFParser
# Use the structured LLM generate method with VerifierResult schema
from spec2rtl.core.data_models import VerifierResult


logger = logging.getLogger("spec2rtl.agents.module1")

# Jinja2 template loader
_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    keep_trailing_newline=True,
)


class UnderstandingModule:
    """Module 1 orchestrator: specification understanding and reasoning.

    Runs a sequential pipeline of LLM-powered agents to transform
    raw specification text into a validated, structured implementation
    plan ready for Module 2's progressive coding stage.

    Args:
        settings: Application settings. Loaded from defaults if None.
        llm_client: Pre-configured LLM client. Created from settings if None.
    """

    def __init__(
        self,
        settings: Spec2RTLSettings | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self._settings = settings or Spec2RTLSettings.from_yaml()
        self._llm = llm_client or LLMClient(self._settings)

    def run(
        self,
        spec_pages: List[str],
        original_text: str | None = None,
    ) -> tuple[DecompositionPlan, List[StructuredInfoDict]]:
        """Execute the full Module 1 pipeline.

        Args:
            spec_pages: List of text strings, one per PDF page.
            original_text: Full concatenated spec text. If None,
                pages are joined automatically.

        Returns:
            A tuple of (DecompositionPlan, list of StructuredInfoDicts).

        Raises:
            PipelineStageError: If any agent stage fails critically.
        """
        full_text = original_text or "\n\n".join(spec_pages)

        # Stage 1: Summarize each page/section
        logger.info("📄 Module 1 — Stage 1: Summarizing specification sections...")
        summaries = self._summarize_sections(spec_pages)

        # Stage 2: Decompose into sub-functions
        logger.info("🔧 Module 1 — Stage 2: Decomposing into sub-functions...")
        plan = self._decompose(summaries, full_text)

        # Stage 3: Build structured info dictionaries
        logger.info("📋 Module 1 — Stage 3: Building structured info dicts...")
        info_dicts = self._describe_sub_functions(plan, full_text, summaries)

        # Stage 4: Verify each info dict
        logger.info("✅ Module 1 — Stage 4: Verifying structured info dicts...")
        verified_dicts = self._verify_info_dicts(plan, info_dicts, full_text, summaries)

        logger.info(
            "Module 1 complete: %d sub-functions planned.",
            len(plan.sub_functions),
        )
        return plan, verified_dicts

    def _summarize_sections(self, pages: List[str]) -> List[SpecSummary]:
        """Run the Summarization Agent on each specification page.

        Args:
            pages: List of per-page text strings.

        Returns:
            List of SpecSummary models, one per non-empty page.
        """
        template = _jinja_env.get_template("module1_summarizer.jinja2")
        summaries: List[SpecSummary] = []

        for i, page_text in enumerate(pages):
            if not page_text.strip():
                continue

            prompt = template.render(section_content=page_text)
            messages = [
                {"role": "system", "content": "You are a Senior Hardware Specification Analyst."},
                {"role": "user", "content": prompt},
            ]
            try:
                summary = self._llm.generate(messages, SpecSummary)
                summaries.append(summary)
                logger.debug("Summarized page %d: %s", i + 1, summary.section_title)
            except Exception as exc:
                logger.warning("Failed to summarize page %d: %s", i + 1, exc)

        return summaries

    def _decompose(
        self,
        summaries: List[SpecSummary],
        original_text: str,
    ) -> DecompositionPlan:
        """Run the Decomposer Agent to break the spec into sub-functions.

        Args:
            summaries: List of section summaries from Stage 1.
            original_text: Full specification text for reference.

        Returns:
            A DecompositionPlan with ordered sub-functions.
        """
        template = _jinja_env.get_template("module1_decomposer.jinja2")
        summaries_json = json.dumps(
            [s.model_dump() for s in summaries], indent=2
        )
        prompt = template.render(
            summaries_json=summaries_json,
            original_spec_text=original_text[:8000],
        )
        messages = [
            {"role": "system", "content": "You are a Hardware Design Decomposition Expert."},
            {"role": "user", "content": prompt},
        ]
        return self._llm.generate(messages, DecompositionPlan)

    def _describe_sub_functions(
        self,
        plan: DecompositionPlan,
        original_text: str,
        summaries: List[SpecSummary], 
    ) -> List[StructuredInfoDict]:
        """Run the Description Agent on each sub-function.

        Args:
            plan: The decomposition plan from Stage 2.
            original_text: Full specification text.

        Returns:
            List of StructuredInfoDicts, one per sub-function.
        """
        template = _jinja_env.get_template("module1_descriptor.jinja2")
        info_dicts: List[StructuredInfoDict] = []
        summaries_json = json.dumps([s.model_dump() for s in summaries], indent=2)

        for sub_func in plan.sub_functions:
            prompt = template.render(
                decomposition_plan_json=plan.model_dump_json(indent=2),
                target_sub_function_name=sub_func.name,
                original_spec_text=original_text[:8000],
                summaries_json=summaries_json,
            )
            messages = [
                {"role": "system", "content": "You are a Hardware Description Engineer."},
                {"role": "user", "content": prompt},
            ]
            info_dict = self._llm.generate(messages, StructuredInfoDict)
            info_dicts.append(info_dict)
            logger.debug("Described sub-function: %s", sub_func.name)

        return info_dicts

    def _verify_info_dicts(
        self,
        plan: DecompositionPlan,
        info_dicts: List[StructuredInfoDict],
        original_text: str,
        summaries: List[SpecSummary],
    ) -> List[StructuredInfoDict]:
        """Run the Verifier Agent to validate each info dictionary.

        If the verifier rejects a dict, it is regenerated with the feedback
        and re-verified up to max_verifier_retries times.

        Args:
            info_dicts: List of StructuredInfoDicts from Stage 3.
            original_text: Full specification text.

        Returns:
            List of verified StructuredInfoDicts.
        """
        template = _jinja_env.get_template("module1_verifier.jinja2")
        max_retries = self._settings.max_verifier_retries
        verified: List[StructuredInfoDict] = []

        for info_dict in info_dicts:
            current_dict = info_dict
            
            for attempt in range(1, max_retries + 1):
                prompt = template.render(
                    info_dict_json=current_dict.model_dump_json(indent=2),
                    decomposition_plan_json=plan.model_dump_json(indent=2),
                    original_spec_text=original_text[:8000],
                )
                messages = [
                    {"role": "system", "content": "You are a Hardware Verification Engineer."},
                    {"role": "user", "content": prompt},
                ]
                try:
                    response = self._llm.generate(messages, response_format=VerifierResult)
                    verdict = response.status.upper() if response.status else ""

                    if "APPROVED" in verdict:
                        logger.debug(
                            "Verified: %s — APPROVED (attempt %d)",
                            current_dict.sub_function_name,
                            attempt,
                        )
                        verified.append(current_dict)
                        break
                    else:
                        logger.warning(
                            "Verifier rejected %s (attempt %d/%d): %s",
                            current_dict.sub_function_name,
                            attempt,
                            max_retries,
                            response.feedback[:200] if response.feedback else "No feedback provided",
                        )
                        
                        # Regenerate the info_dict with feedback for next attempt
                        if attempt < max_retries:
                            logger.info(
                                "Regenerating info_dict for '%s' with verifier feedback...",
                                current_dict.sub_function_name,
                            )
                            current_dict = self._regenerate_info_dict(
                                current_dict,
                                response.feedback,
                                original_text,
                                plan,
                                summaries,
                            )
                        else:
                            logger.warning(
                                "Max verifier retries reached for '%s'. Keeping last version.",
                                current_dict.sub_function_name,
                            )
                            verified.append(current_dict)

                except Exception as exc:
                    logger.warning(
                        "Verification failed for %s: %s",
                        current_dict.sub_function_name,
                        exc,
                    )
                    verified.append(current_dict)
                    break

        return verified

    def _regenerate_info_dict(
        self,
        info_dict: StructuredInfoDict,
        verifier_feedback: str,
        original_text: str,
        plan: DecompositionPlan,
        summaries: List[SpecSummary],
    ) -> StructuredInfoDict:
        """Regenerate an info_dict based on verifier feedback.

        Args:
            info_dict: The original info_dict that was rejected.
            verifier_feedback: The feedback from the verifier explaining what needs fixing.
            original_text: Full specification text.

        Returns:
            A new StructuredInfoDict with corrections applied.
        """
        template = _jinja_env.get_template("module1_descriptor.jinja2")
        summaries_json = json.dumps([s.model_dump() for s in summaries], indent=2)
        
        prompt = template.render(
            decomposition_plan_json=plan.model_dump_json(indent=2),
            info_dict_json=info_dict.model_dump_json(indent=2),
            target_sub_function_name=info_dict.sub_function_name,
            original_spec_text=original_text[:8000],
            summaries_json=summaries_json,
            verifier_feedback=verifier_feedback,
        )
        messages = [
            {"role": "system", "content": "You are a Hardware Description Engineer."},
            {"role": "user", "content": prompt},
        ]
        return self._llm.generate(messages, StructuredInfoDict)

