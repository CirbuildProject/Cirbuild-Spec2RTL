"""Module 4.5: HLS Reflection & Prompt Adaptation.

This module acts as a recovery loop for Module 4. If HLS synthesis fails,
this module analyzes the compiler stderr, fixes the C++ code, and extracts
new rules to append to the active HLS constraints.

Now includes integration with Agentic Memory for persistent learning.
"""

import logging
from pathlib import Path

from autogen_agentchat.agents import AssistantAgent

from spec2rtl.config.settings import Spec2RTLSettings
from spec2rtl.core.data_models import HLSConstraints, HLSRecoveryPlan
from spec2rtl.llm.llm_client import LLMClient
from spec2rtl.memory.long_term_memory import LongTermMemory, ErrorFixPair

logger = logging.getLogger(__name__)


class HLSReflectionModule:
    """Analyzes HLS synthesis failures and fixes code/constraints.
    
    Now with Agentic Memory integration:
    - Before recovery: Searches for similar past errors and their fixes
    - After successful recovery: Stores error-fix pairs for future learning
    """

    def __init__(self, config: Spec2RTLSettings):
        self.config = config
        self.llm_client = LLMClient(config)
        self._prompt_dir = Path(__file__).parent.parent / "prompts"
        
        # Initialize long-term memory for error-fix learning
        self._long_term_memory = LongTermMemory(
            persist_dir="memory/hls_fixes",
            similarity_threshold=0.7,
        )
        
        logger.info(
            "HLS Reflection Module initialized. Memory stats: %s",
            self._long_term_memory.get_statistics(),
        )

    def _load_prompt(self, template_name: str, **kwargs) -> str:
        """Load and render a Jinja2 prompt template."""
        from jinja2 import Environment, FileSystemLoader

        env = Environment(loader=FileSystemLoader(self._prompt_dir))
        template = env.get_template(template_name)
        return template.render(**kwargs)
    
    def _classify_error(self, error_log: str) -> tuple[str, str]:
        """Classify the error type from the error log.
        
        Args:
            error_log: The compiler error output.
            
        Returns:
            Tuple of (error_type, compiler_key).
        """
        error_log_lower = error_log.lower()
        
        # Classify error type
        if "schedul" in error_log_lower:
            error_type = "scheduling_failure"
        elif "syntax" in error_log_lower:
            error_type = "syntax_error"
        elif "type" in error_log_lower or "mismatch" in error_log_lower:
            error_type = "type_error"
        elif "pragma" in error_log_lower:
            error_type = "pragma_error"
        elif "resource" in error_log_lower or "area" in error_log_lower:
            error_type = "resource_limit"
        elif "timing" in error_log_lower:
            error_type = "timing_violation"
        else:
            error_type = "unknown_error"
        
        # Determine compiler key
        if "xls" in error_log_lower:
            compiler_key = "google_xls"
        elif "bambu" in error_log_lower:
            compiler_key = "bambu"
        elif "vitis" in error_log_lower or "hls" in error_log_lower:
            compiler_key = "vitis"
        else:
            compiler_key = "unknown"
            
        return error_type, compiler_key

    def recover(
        self, 
        cpp_code: str, 
        error_log: str, 
        target_compiler: str, 
        current_constraints: HLSConstraints
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
        
        # Classify the error type
        error_type, compiler_key = self._classify_error(error_log)
        logger.info(f"📊 Error classified as: {error_type} on {compiler_key}")
        
        # Search for similar past errors in long-term memory
        similar_fixes = self._long_term_memory.find_similar_fixes(
            error_message=error_log,
            error_type=error_type,
            compiler=compiler_key,
            n_results=2,
        )
        
        # Build context from similar fixes if found
        historical_context = ""
        if similar_fixes:
            logger.info(f"🧠 Found {len(similar_fixes)} similar past fixes!")
            historical_context = "\n\n## Historical Fixes (from memory):\n"
            for i, fix in enumerate(similar_fixes, 1):
                historical_context += f"""
### Fix {i} (recorded {fix.timestamp}):
- **Error**: {fix.error_message[:300]}
- **Fix Strategy**: {fix.fix_strategy}
- **Code Change**: {fix.fixed_code_snippet[:500]}
"""
        
        # Load the reflection prompt with historical context
        sys_prompt = self._load_prompt(
            "hls_reflector.jinja2",
            target_compiler=target_compiler,
            cpp_code=cpp_code,
            error_log=error_log,
            historical_fixes=historical_context,
        )

        # Use the LLM to generate a recovery plan
        # Note: Using generate() method which was fixed earlier
        response = self.llm_client.generate(
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": "Analyze the error and provide the recovery plan."},
            ],
            response_format=HLSRecoveryPlan,
        )

        assert isinstance(response, HLSRecoveryPlan)

        logger.info("✅ HLS error analyzed. C++ code patched.")

        # Store successful fix in long-term memory
        if response.fixed_cpp_code:
            error_fix = ErrorFixPair(
                error_type=error_type,
                compiler=compiler_key,
                error_message=error_log[:2000],  # Limit length
                fix_strategy=response.reasoning or "Generated fix",
                fixed_code_snippet=response.fixed_cpp_code[:1000],  # Store snippet
                success=True,
            )
            self._long_term_memory.store_fix(error_fix)
            logger.info("💾 Stored fix in long-term memory for future learning")

        if response.learned_rule:
            logger.info(f"🧠 Learned new constraint: {response.learned_rule}")
            # Add to forbidden constructs if it's a new rule
            if response.learned_rule not in current_constraints.forbidden_constructs:
               current_constraints.forbidden_constructs.append(response.learned_rule)
            else:
               logger.debug("Constraint already exists in memory, skipping append.")

        return response.fixed_cpp_code, current_constraints

    def get_learned_rules_summary(self, compiler_name: str) -> str:
        """Get a summary of learned rules from long-term memory.
        
        Args:
            compiler_name: The HLS compiler name (e.g., "google_xls", "bambu").
            
        Returns:
            A formatted string of learned rules, or a default message if none found.
        """
        # Map display name to storage key
        compiler_key = compiler_name.lower().replace(" ", "_")
        if "google" in compiler_key or "xls" in compiler_key:
            compiler_key = "google_xls"
        
        # Search for successful fixes
        fixes = self._long_term_memory.find_similar_fixes(
            error_message="",
            error_type=None,
            compiler=compiler_key,
            n_results=5,
        )
        
        if not fixes:
            return "No previous rules learned yet."
        
        # Build summary from learned fixes
        rules = []
        for fix in fixes:
            if fix.fix_strategy and fix.success:
                rules.append(f"- {fix.fix_strategy}")
        
        if not rules:
            return "No previous rules learned yet."
        
        return "## Previously Learned Rules:\n" + "\n".join(rules[:5])
