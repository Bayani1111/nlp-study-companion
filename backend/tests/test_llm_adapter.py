"""Tests for the LLM adapter module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm_adapter import (
    _MAX_RETRIES,
    FALLBACK_REPLY,
    _TokenBucket,
    call_llm_api,
)

# ---------------------------------------------------------------------------
# TokenBucket unit tests
# ---------------------------------------------------------------------------


class TestTokenBucket:
    def test_acquire_within_capacity(self):
        bucket = _TokenBucket(rate=1.0, capacity=3)
        assert bucket.acquire() is True
        assert bucket.acquire() is True
        assert bucket.acquire() is True

    def test_acquire_exhausted(self):
        bucket = _TokenBucket(rate=0.0, capacity=2)
        assert bucket.acquire() is True
        assert bucket.acquire() is True
        assert bucket.acquire() is False

    def test_refill_over_time(self):
        bucket = _TokenBucket(rate=100.0, capacity=5)
        # Drain all tokens
        for _ in range(5):
            bucket.acquire()
        # Manually advance the internal clock
        bucket._last_refill -= 1  # simulate 1 second passing
        assert bucket.acquire() is True


# ---------------------------------------------------------------------------
# call_llm_api tests
# ---------------------------------------------------------------------------


def _make_completion(content: str):
    """Helper to build a mock completion response."""
    choice = MagicMock()
    choice.message.content = content
    completion = MagicMock()
    completion.choices = [choice]
    return completion


@pytest.mark.asyncio
async def test_call_llm_api_success():
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=_make_completion("Hello!"))

    with (
        patch("app.services.llm_adapter._get_client", return_value=mock_client),
        patch("app.services.llm_adapter._rate_limiter") as mock_limiter,
    ):
        mock_limiter.acquire.return_value = True
        result = await call_llm_api([{"role": "user", "content": "Hi"}])

    assert result == "Hello!"


@pytest.mark.asyncio
async def test_call_llm_api_json_format():
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_completion('{"intent": "general_chat"}')
    )

    with (
        patch("app.services.llm_adapter._get_client", return_value=mock_client),
        patch("app.services.llm_adapter._rate_limiter") as mock_limiter,
    ):
        mock_limiter.acquire.return_value = True
        result = await call_llm_api(
            [{"role": "user", "content": "Hi"}],
            response_format="json",
        )

    assert result == '{"intent": "general_chat"}'
    # Verify response_format was passed
    call_kwargs = mock_client.chat.completions.create.call_args
    assert call_kwargs.kwargs.get("response_format") == {"type": "json_object"}


@pytest.mark.asyncio
async def test_call_llm_api_supports_model_override():
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=_make_completion("Hello!"))

    with (
        patch("app.services.llm_adapter._get_client", return_value=mock_client),
        patch("app.services.llm_adapter._rate_limiter") as mock_limiter,
    ):
        mock_limiter.acquire.return_value = True
        await call_llm_api(
            [{"role": "user", "content": "Hi"}],
            model="qwen-plus-2025-07-28",
        )

    call_kwargs = mock_client.chat.completions.create.call_args
    assert call_kwargs.kwargs.get("model") == "qwen-plus-2025-07-28"


@pytest.mark.asyncio
async def test_call_llm_api_rate_limited():
    with patch("app.services.llm_adapter._rate_limiter") as mock_limiter:
        mock_limiter.acquire.return_value = False
        result = await call_llm_api([{"role": "user", "content": "Hi"}])

    assert result == FALLBACK_REPLY


@pytest.mark.asyncio
async def test_call_llm_api_retries_on_api_error():
    from openai import APIError

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=APIError(
            message="server error",
            request=MagicMock(),
            body=None,
        )
    )

    with (
        patch("app.services.llm_adapter._get_client", return_value=mock_client),
        patch("app.services.llm_adapter._rate_limiter") as mock_limiter,
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        mock_limiter.acquire.return_value = True
        result = await call_llm_api([{"role": "user", "content": "Hi"}])

    assert result == FALLBACK_REPLY
    assert mock_client.chat.completions.create.call_count == _MAX_RETRIES
    # Verify exponential backoff sleep calls (1s, 2s — no sleep after last attempt)
    assert mock_sleep.call_count == _MAX_RETRIES - 1
    mock_sleep.assert_any_call(1)
    mock_sleep.assert_any_call(2)


@pytest.mark.asyncio
async def test_call_llm_api_succeeds_after_retry():
    from openai import APITimeoutError

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=[
            APITimeoutError(request=MagicMock()),
            _make_completion("Recovered!"),
        ]
    )

    with (
        patch("app.services.llm_adapter._get_client", return_value=mock_client),
        patch("app.services.llm_adapter._rate_limiter") as mock_limiter,
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        mock_limiter.acquire.return_value = True
        result = await call_llm_api([{"role": "user", "content": "Hi"}])

    assert result == "Recovered!"
    assert mock_client.chat.completions.create.call_count == 2


@pytest.mark.asyncio
async def test_call_llm_api_unknown_error_no_retry():
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("unexpected"))

    with (
        patch("app.services.llm_adapter._get_client", return_value=mock_client),
        patch("app.services.llm_adapter._rate_limiter") as mock_limiter,
    ):
        mock_limiter.acquire.return_value = True
        result = await call_llm_api([{"role": "user", "content": "Hi"}])

    assert result == FALLBACK_REPLY
    # Unknown errors should NOT retry
    assert mock_client.chat.completions.create.call_count == 1


@pytest.mark.asyncio
async def test_call_llm_api_empty_content_returns_empty_string():
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=_make_completion(None))

    with (
        patch("app.services.llm_adapter._get_client", return_value=mock_client),
        patch("app.services.llm_adapter._rate_limiter") as mock_limiter,
    ):
        mock_limiter.acquire.return_value = True
        result = await call_llm_api([{"role": "user", "content": "Hi"}])

    assert result == ""
