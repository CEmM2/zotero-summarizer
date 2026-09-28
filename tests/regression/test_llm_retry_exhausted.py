"""Tests for Create LLMRetryExhausted exception type

Introduces a typed LLMRetryExhausted exception that extends RuntimeError
with last_error and attempts attributes, replacing the bare RuntimeError raised
when retry exhaustion occurs in complete_with_retry().

These tests verify:
1. LLMRetryExhausted stores both last_error and attempts attributes
2. isinstance(LLMRetryExhausted(), RuntimeError) is True for backward compatibility
3. The retry exhaustion point raises LLMRetryExhausted (not bare RuntimeError)
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from zsum.config import Config
from zsum.llm import LLMRetryExhausted, complete_with_retry


class TestLlmRetryExhausted:
    """
    Tests for Create LLMRetryExhausted exception type
    Covers: AC-1, AC-2, AC-3
    """

    @pytest.mark.unit
    def test_llmretryexhausted_stores_last_error_and_attempts(self):
        """
        Verifies: LLMRetryExhausted exception stores last_error and attempts as attributes
        Covers: LLMRetryExhausted has last_error and attempts attributes
        Passes when: Exception instance has both attributes set to expected values
        """
        original = ValueError("something went wrong")
        exc = LLMRetryExhausted(last_error=original, attempts=3)
        assert exc.last_error is original
        assert exc.attempts == 3
        assert "3" in str(exc)
        assert "something went wrong" in str(exc)

    @pytest.mark.unit
    def test_llmretryexhausted_is_runtimeerror_subclass(self):
        """
        Verifies: LLMRetryExhausted is a subclass of RuntimeError for backward compatibility
        Covers: isinstance(LLMRetryExhausted(), RuntimeError) is True
        Passes when: An LLMRetryExhausted instance is recognized as a RuntimeError
        """
        exc = LLMRetryExhausted(last_error=ValueError("x"), attempts=1)
        assert isinstance(exc, RuntimeError)
        assert issubclass(LLMRetryExhausted, RuntimeError)

    @pytest.mark.unit
    def test_retry_exhaustion_raises_llmretryexhausted(self):
        """
        Verifies: complete_with_retry() raises LLMRetryExhausted when max_retries is exhausted
        Covers: Retry exhaustion test catches LLMRetryExhausted
        Passes when: LLMRetryExhausted is raised with correct last_error and attempts count
        """
        root_error = ConnectionError("network down")
        config = Config()
        with (
            patch("zsum.llm.complete", side_effect=root_error),
            pytest.raises(LLMRetryExhausted) as exc_info,
        ):
            complete_with_retry("sys", "user", config, max_retries=3, base_delay=0.0)
        assert exc_info.value.attempts == 3
        assert exc_info.value.last_error is root_error
        assert isinstance(exc_info.value, RuntimeError)
