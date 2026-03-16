"""API-agnostic LLM client wrapping LiteLLM with dual-loop fault tolerance.

This client provides a single interface for all LLM interactions in the
Spec2RTL pipeline. It implements:
- Inner loop: JSON formatting retries for a given model
- Outer loop: Automatic fallback to alternative models on rate limits

The underlying model can be any provider supported by LiteLLM (OpenAI,
Anthropic, Google, local Ollama, etc.) — controlled purely by config.
"""

import logging
import os
from typing import List, Type, TypeVar

import litellm
from litellm import completion
from litellm.exceptions import (
    APIConnectionError,
    ContextWindowExceededError,
    NotFoundError,
    RateLimitError,
    ServiceUnavailableError,
)
from pydantic import BaseModel

from spec2rtl.config.settings import Spec2RTLSettings
from spec2rtl.core.exceptions import LLMFormattingError, LLMRateLimitError

logger = logging.getLogger("spec2rtl.llm.llm_client")

# Enable client-side schema validation for structured outputs
litellm.enable_json_schema_validation = True

T = TypeVar("T", bound=BaseModel)


class LLMClient:
    """API-agnostic LLM client with automatic fallback routing.

    Wraps LiteLLM's completion API to provide structured Pydantic output
    with dual-loop error handling: retry formatting errors locally, and
    fall back to alternative models on rate limits or service outages.

    Args:
        settings: Application settings containing model config.
            If None, defaults are loaded from default_config.yaml.

    Example:
        client = LLMClient()
        result = client.generate(
            messages=[{"role": "user", "content": "Hello"}],
            response_format=MyPydanticModel,
        )
    """

    def __init__(self, settings: Spec2RTLSettings | None = None) -> None:
        self._settings = settings or Spec2RTLSettings.from_yaml()
        self._active_model: str | None = None

    @staticmethod
    def _resolve_api_key(model: str) -> str | None:
        """Resolve the correct API key for a given model string.

        Inspects the model prefix to select the appropriate provider key
        from the environment. This allows the pipeline to use different
        providers for primary and fallback models without coupling to a
        single API key, preventing rate-limit conflicts between providers.

        Key environment variables (set in .env):
            SPEC2RTL_OPENROUTER_KEY  — for ``openrouter/`` models
            SPEC2RTL_GEMINI_KEY      — for ``gemini/`` models
            SPEC2RTL_ANTHROPIC_KEY   — for ``anthropic/`` models

        Args:
            model: LiteLLM model string (e.g. ``openrouter/minimax/minimax-m2.5``).

        Returns:
            The resolved API key string, or None if no matching key is set.
        """
        if model.startswith("gemini/"):
            return os.environ.get("SPEC2RTL_GEMINI_KEY")
        if model.startswith("anthropic/"):
            return os.environ.get("SPEC2RTL_ANTHROPIC_KEY")
        if model.startswith("openrouter/"):
            return os.environ.get("SPEC2RTL_OPENROUTER_KEY")
        # Unknown provider prefix — let LiteLLM fall back to its own env detection
        return None

    @property
    def default_model(self) -> str:
        """The primary model identifier."""
        return self._settings.default_model

    @property
    def fallback_models(self) -> List[str]:
        """Ordered fallback model identifiers."""
        return self._settings.fallback_models

    def generate(
        self,
        messages: List[dict],
        response_format: Type[T],
        model_override: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> T:
        """Generate a structured LLM response with fault-tolerant routing.

        Args:
            messages: Chat-format message list (system + user messages).
            response_format: Pydantic model class for structured output.
            model_override: Use a specific model instead of the default.
            temperature: Override the configured temperature.
            max_tokens: Override the configured max tokens.

        Returns:
            A validated instance of the response_format Pydantic model.

        Raises:
            LLMRateLimitError: If all models are rate-limited or unavailable.
            LLMFormattingError: If the response cannot be parsed after retries.
        """
        primary = model_override or self._settings.default_model
        models_to_try = [primary] + [
            m for m in self._settings.fallback_models if m != primary
        ]
        temp = temperature if temperature is not None else self._settings.llm_temperature
        tokens = max_tokens if max_tokens is not None else self._settings.llm_max_tokens
        max_retries = self._settings.max_llm_retries

        last_error: Exception | None = None

        # Base messages (shallow copy of dicts) to avoid mutating caller's list
        base_messages = [dict(m) for m in messages]

        # Level 1 Defensive Programming: Aggressive System Prompt Injection
        aggressive_prompt = (
            "Output ONLY valid JSON. Do not include markdown formatting. "
            "Do not include any conversational text before or after the JSON."
        )
        
        prompt_injected = False
        for msg in base_messages:
            if msg.get("role") == "system":
                msg["content"] = str(msg.get("content", "")) + "\n\n" + aggressive_prompt
                prompt_injected = True
                break
                
        if not prompt_injected:
            base_messages.insert(0, {"role": "system", "content": aggressive_prompt})

        # --- OUTER LOOP: Model Fallback Routing ---
        for current_model in models_to_try:
            if current_model != self._active_model:
                logger.info("🤖 [Model Active] %s", current_model)
                self._active_model = current_model

            # State for the inner loop
            current_messages = list(base_messages)

            # --- INNER LOOP: JSON Formatting Retries ---
            for attempt in range(max_retries):
                content = None
                try:
                    response = completion(
                        model=current_model,
                        api_key=self._resolve_api_key(current_model),
                        max_tokens=tokens,
                        temperature=temp,
                        messages=current_messages,
                        response_format=response_format,
                    )
                    content = response.choices[0].message.content
                    result = response_format.model_validate_json(content)

                    logger.debug(
                        "LLM response validated: model=%s, schema=%s",
                        current_model,
                        response_format.__name__,
                    )
                    return result

                except (
                    RateLimitError,
                    ContextWindowExceededError,
                    APIConnectionError,
                    litellm.exceptions.BadRequestError,
                ) as exc:
                    logger.warning(
                        "⚠️ [API Limit / Bad Request] %s on %s. Routing to fallback...",
                        type(exc).__name__,
                        current_model,
                    )
                    last_error = exc
                    break  # Move to next model

                except ServiceUnavailableError as exc:
                    logger.warning(
                        "⚠️ [Server Down] %s on %s. Routing to fallback...",
                        type(exc).__name__,
                        current_model,
                    )
                    last_error = exc
                    break

                except NotFoundError as exc:
                    logger.warning(
                        "Model %s not found on LiteLLM. Routing to fallback...",
                        current_model,
                    )
                    last_error = exc
                    break

                except Exception as exc:
                    last_error = exc
                    logger.warning(
                        "⚠️ [Attempt %d/%d] Formatting error on %s: %s",
                        attempt + 1,
                        max_retries,
                        current_model,
                        str(exc)[:200],
                    )
                    if attempt == max_retries - 1:
                        logger.error(
                            "❌ Max formatting retries reached on %s.",
                            current_model,
                        )
                        # Do NOT fallback on formatting errors — the model
                        # understands the task but can't format properly
                        raise LLMFormattingError(
                            f"Failed to parse {response_format.__name__} "
                            f"after {max_retries} attempts on {current_model}: "
                            f"{exc}"
                        ) from exc
                        
                    # Feedback loop: Append error so model can correct itself
                    raw_content = getattr(exc, "raw_response", content)
                    if raw_content:
                        # Append the malformed response so the model has context
                        current_messages.append({"role": "assistant", "content": str(raw_content)})
                    else:
                        current_messages.append({"role": "assistant", "content": "Failed to generate valid output."})
                        
                    error_msg = (
                        f"Your previous response failed validation with the following error:\n"
                        f"{str(exc)}\n\n"
                        f"Please fix the formatting, assure JSON correctness, and ensure "
                        f"you strictly follow the complete {response_format.__name__} schema."
                    )
                    current_messages.append({"role": "user", "content": error_msg})

        # All models exhausted
        raise LLMRateLimitError(
            f"All models exhausted. Last error: {last_error}"
        )
