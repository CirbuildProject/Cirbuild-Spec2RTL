"""Unit tests for the LiteLLM API-agnostic client."""

import unittest
from unittest.mock import MagicMock, patch

from pydantic import BaseModel

from spec2rtl.core.exceptions import LLMFormattingError, LLMRateLimitError
from spec2rtl.llm.llm_client import LLMClient


class PointModel(BaseModel):
    x: int
    y: int


class TestLLMClient(unittest.TestCase):
    """Tests for dual-loop robustness inside LLMClient."""

    @patch("spec2rtl.llm.llm_client.completion")
    def test_successful_structured_creation(self, mock_completion: MagicMock) -> None:
        """The client should correctly map API responses to Pydantic models."""
        mock_msg = MagicMock()
        mock_msg.content = '{"x": 10, "y": 20}'
        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_completion.return_value = mock_response

        client = LLMClient(settings=MagicMock(default_model="test/model", fallback_models=[]))
        
        result = client.generate(messages=[{"role": "user", "content": "hello"}], response_format=PointModel)

        self.assertIsInstance(result, PointModel)
        self.assertEqual(result.x, 10)
        self.assertEqual(result.y, 20)

    @patch("spec2rtl.llm.llm_client.completion")
    def test_fallback_routing_on_rate_limit(self, mock_completion: MagicMock) -> None:
        """The client should try a fallback model if the primary throws a service error."""
        from litellm.exceptions import ServiceUnavailableError

        mock_msg = MagicMock()
        mock_msg.content = '{"x": 1, "y": 1}'
        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_completion.side_effect = [
            ServiceUnavailableError(message="503 Down", llm_provider="test", model="test/fail"),
            mock_response
        ]

        client = LLMClient(settings=MagicMock(default_model="test/fail", fallback_models=["test/success"]))
        result = client.generate(messages=[{"role": "user", "content": "hi"}], response_format=PointModel)

        self.assertEqual(mock_completion.call_count, 2)
        self.assertIsInstance(result, PointModel)

    @patch("spec2rtl.llm.llm_client.completion")
    def test_formatting_retry_on_bad_json(self, mock_completion: MagicMock) -> None:
        """If the LLM returns bad JSON, the client should retry the SAME model."""
        mock_msg_bad = MagicMock()
        mock_msg_bad.content = '{"x": 10, "y": "twenty"}'
        mock_choice_bad = MagicMock()
        mock_choice_bad.message = mock_msg_bad
        mock_bad = MagicMock()
        mock_bad.choices = [mock_choice_bad]

        mock_msg_good = MagicMock()
        mock_msg_good.content = '{"x": 10, "y": 20}'
        mock_choice_good = MagicMock()
        mock_choice_good.message = mock_msg_good
        mock_good = MagicMock()
        mock_good.choices = [mock_choice_good]

        mock_completion.side_effect = [mock_bad, mock_good]

        settings = MagicMock(default_model="test/model", fallback_models=[], max_llm_retries=3)
        client = LLMClient(settings=settings)
        result = client.generate(messages=[{"role": "user", "content": "hi"}], response_format=PointModel)

        self.assertEqual(mock_completion.call_count, 2)
        self.assertIsInstance(result, PointModel)


if __name__ == "__main__":
    unittest.main()
