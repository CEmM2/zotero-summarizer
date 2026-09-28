"""Tests for Retry error classification.

Ensures that LLM errors are correctly classified as transient (timeout, 429, 503)
or fatal (auth, invalid model) and handled appropriately in complete_with_retry().
Transient errors should be retried up to max_retries attempts; fatal errors should
raise immediately without retry.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from zsum.config import Config
from zsum.llm import LLMResponse, _is_transient, complete_with_retry


def _make_status_error(status_code: int, message: str = "error"):
    """Create a generic APIStatusError-like exception with a status_code attribute."""
    exc = Exception(message)
    exc.status_code = status_code  # type: ignore[attr-defined]
    return exc


class TestIsTransient:
    """Unit tests for the _is_transient() helper directly."""

    def test_generic_runtime_error_is_transient(self):
        """Unknown exceptions default to transient for backward compatibility."""
        assert _is_transient(RuntimeError("boom")) is True

    def test_connection_error_is_transient(self):
        assert _is_transient(ConnectionError("network down")) is True

    def test_timeout_error_is_transient(self):
        assert _is_transient(TimeoutError("timed out")) is True

    def test_os_error_is_fatal(self):
        # OSError is reclassified as fatal (non-transient) so that
        # filesystem errors (e.g. missing cache files) fail fast instead of retrying.
        # ConnectionError and TimeoutError remain transient because they are explicit
        # members of _TRANSIENT_BUILTIN; a bare OSError is not a network error.
        assert _is_transient(OSError("socket error")) is False

    def test_value_error_is_fatal(self):
        # Config / validation errors are fatal
        assert _is_transient(ValueError("bad value")) is False

    def test_unknown_exception_default_transient(self):
        """Any unrecognised exception should default to transient."""

        class WeirdError(Exception):
            pass

        assert _is_transient(WeirdError("weird")) is True


class TestRetryClassification:
    """
    Tests for Retry error classification
    Covers: Auth/invalid model errors surface immediately;
    timeouts/429 retry with exponential backoff
    """

    @pytest.mark.unit
    @patch("zsum.llm.complete")
    def test_auth_error_no_retry(self, mock_complete):
        """
        Verifies: Authentication errors (401, invalid API key) are fatal.
        Covers: auth error no retry.
        Passes when: AuthenticationError (or 401 from API) is raised immediately
        without consuming any retry attempts.

        The real _is_transient classifies status_code=401 as fatal (returns False),
        so no mocking is needed.
        """
        # Create an auth-like error with status_code=401
        auth_error = Exception("Invalid API key")
        auth_error.status_code = 401  # type: ignore[attr-defined]

        mock_complete.side_effect = auth_error
        config = Config()

        with pytest.raises(Exception, match="Invalid API key"):
            complete_with_retry("sys", "user", config, max_retries=3, base_delay=0.01)

        # Must NOT have retried — only one call to complete()
        assert mock_complete.call_count == 1

    @pytest.mark.unit
    @patch("zsum.llm.complete")
    def test_timeout_retries(self, mock_complete):
        """
        Verifies: Timeout errors are transient and retried.
        Covers: timeout retries.
        Passes when: TimeoutError is caught, retried up to max_retries times,
        finally raises RuntimeError after exhaustion.
        """
        mock_complete.side_effect = TimeoutError("request timed out")
        config = Config()

        with pytest.raises(RuntimeError, match="failed after 2 attempts"):
            complete_with_retry("sys", "user", config, max_retries=2, base_delay=0.0)

        # Should have been called exactly max_retries times
        assert mock_complete.call_count == 2

    @pytest.mark.unit
    @patch("zsum.llm.complete")
    def test_rate_limit_429_retries(self, mock_complete):
        """
        Verifies: HTTP 429 (rate limit) errors are transient and retried.
        Covers: 429 retries.
        Passes when: Exception with status_code=429 is retried and succeeds on retry.
        """
        rate_limit_error = Exception("Rate limit exceeded")
        rate_limit_error.status_code = 429  # type: ignore[attr-defined]

        success_response = LLMResponse(text="ok", model="test", input_tokens=10, output_tokens=5)
        mock_complete.side_effect = [rate_limit_error, success_response]
        config = Config()

        result = complete_with_retry("sys", "user", config, max_retries=3, base_delay=0.0)

        assert result.text == "ok"
        assert mock_complete.call_count == 2

    @pytest.mark.unit
    @patch("zsum.llm.complete")
    def test_invalid_model_no_retry(self, mock_complete):
        """
        Verifies: Invalid model errors are fatal.
        Covers: invalid model no retry.
        Passes when: A 404/not-found model error is raised immediately
        without consuming any retry attempts.

        The real _is_transient classifies status_code=404 as fatal (returns False),
        so no mocking is needed.
        """
        not_found_error = Exception("model not found")
        not_found_error.status_code = 404  # type: ignore[attr-defined]

        mock_complete.side_effect = not_found_error
        config = Config()

        with pytest.raises(Exception, match="model not found"):
            complete_with_retry("sys", "user", config, max_retries=3, base_delay=0.01)

        # Must NOT have retried
        assert mock_complete.call_count == 1

    @pytest.mark.unit
    @patch("zsum.llm.complete")
    def test_503_retries(self, mock_complete):
        """
        Verifies: HTTP 503 (service unavailable) errors are transient and retried.
        """
        server_error = Exception("Service unavailable")
        server_error.status_code = 503  # type: ignore[attr-defined]

        success_response = LLMResponse(
            text="recovered", model="test", input_tokens=5, output_tokens=3
        )
        mock_complete.side_effect = [server_error, success_response]
        config = Config()

        result = complete_with_retry("sys", "user", config, max_retries=3, base_delay=0.0)

        assert result.text == "recovered"
        assert mock_complete.call_count == 2

    @pytest.mark.unit
    @patch("zsum.llm.complete")
    def test_400_fatal_no_retry(self, mock_complete):
        """
        Verifies: HTTP 400 (bad request / config error) is fatal.
        """
        bad_request = Exception("bad request")
        bad_request.status_code = 400  # type: ignore[attr-defined]

        mock_complete.side_effect = bad_request
        config = Config()

        with pytest.raises(Exception, match="bad request"):
            complete_with_retry("sys", "user", config, max_retries=3, base_delay=0.01)

        assert mock_complete.call_count == 1
