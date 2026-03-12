"""Short-Term Memory Manager for context pruning.

This module provides utilities to prune non-essential conversational history
to save tokens and prevent LLM confusion during long synthesis loops.
"""

import logging
from typing import Any

logger = logging.getLogger("spec2rtl.memory.short_term")


class ShortTermMemoryManager:
    """Manages short-term memory by pruning non-essential conversation history.
    
    This manager helps reduce token usage by:
    - Removing redundant system prompts
    - Trimming long assistant responses
    - Keeping only the original spec and current module context
    
    Args:
        max_messages: Maximum number of messages to retain (default: 20)
        preserve_system: Whether to always keep the first system prompt (default: True)
    """
    
    def __init__(
        self,
        max_messages: int = 20,
        preserve_system: bool = True,
    ) -> None:
        self.max_messages = max_messages
        self.preserve_system = preserve_system
    
    def prune(
        self,
        messages: list[dict[str, Any]],
        keep_original_spec: str | None = None,
    ) -> list[dict[str, Any]]:
        """Prune messages to reduce token count while preserving essential context.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content' keys.
            keep_original_spec: Optional original specification text to always preserve.
        
        Returns:
            Pruned list of messages.
        """
        if not messages:
            return []
        
        pruned: list[dict[str, Any]] = []
        
        # Always keep the first system message if configured
        if self.preserve_system and messages:
            for msg in messages:
                if msg.get("role") == "system":
                    pruned.append(msg)
                    break
        
        # Add original spec if provided
        if keep_original_spec:
            pruned.append({
                "role": "user",
                "content": f"[ORIGINAL SPEC]\n{keep_original_spec[:5000]}",
            })
        
        # Keep recent messages up to max_messages
        # Filter out very long assistant messages that are mostly context
        recent = [
            msg for msg in messages[-self.max_messages:]
            if msg.get("role") != "system"  # Skip system (already handled)
        ]
        
        # Truncate long assistant messages
        for msg in recent:
            content = msg.get("content", "")
            if msg.get("role") == "assistant" and len(content) > 2000:
                # Keep first 500 and last 1500 chars
                truncated = content[:500] + f"\n...[truncated {len(content)-2000} chars]...\n" + content[-1500:]
                pruned.append({**msg, "content": truncated})
            else:
                pruned.append(msg)
        
        logger.debug(
            "Short-term memory pruned: %d original messages -> %d retained",
            len(messages),
            len(pruned),
        )
        
        return pruned
    
    def extract_module_context(
        self,
        messages: list[dict[str, Any]],
        module_name: str,
    ) -> list[dict[str, Any]]:
        """Extract only messages relevant to a specific module.
        
        Args:
            messages: Full message history.
            module_name: Target module (e.g., 'Module 2', 'Module 3').
        
        Returns:
            Filtered messages relevant to the module.
        """
        context: list[dict[str, Any]] = []
        
        # Find messages containing the module name or recent messages
        found_module = False
        for msg in reversed(messages):
            content = msg.get("content", "")
            if module_name.lower() in content.lower():
                found_module = True
            
            if found_module:
                context.insert(0, msg)
                
                # Stop at previous module boundary
                prev_modules = ["module 1", "module 2", "module 3", "module 4"]
                for pm in prev_modules:
                    if pm != module_name.lower() and pm in content.lower():
                        break
        
        return context if context else messages[-5:]  # Fallback to last 5 messages
