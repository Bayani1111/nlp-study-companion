"""大模型 API 适配器 — 封装 OpenAI 异步客户端调用。

功能：
- 使用 openai 异步客户端调用大模型 API
- 指数退避重试（最多 3 次，间隔 1s, 2s, 4s）
- 调用失败时返回友好降级回复
- 简单的令牌桶速率限制
"""

import asyncio
import logging
import time

from openai import APIError, APITimeoutError, AsyncOpenAI, RateLimitError

from app.config import settings

logger = logging.getLogger(__name__)

FALLBACK_REPLY = "抱歉，我暂时无法回复，请稍后再试"

# ---------------------------------------------------------------------------
# 速率限制 — 简单令牌桶
# ---------------------------------------------------------------------------


class _TokenBucket:
    """简单的令牌桶速率限制器。

    每秒补充 *rate* 个令牌，桶容量上限为 *capacity*。
    调用 :meth:`acquire` 消耗一个令牌，令牌不足时返回 ``False``。
    """

    def __init__(self, rate: float = 1.0, capacity: int = 10) -> None:
        self.rate = rate
        self.capacity = capacity
        self._tokens: float = float(capacity)
        self._last_refill: float = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last_refill = now

    def acquire(self) -> bool:
        """尝试获取一个令牌，成功返回 True，否则 False。"""
        self._refill()
        if self._tokens >= 1:
            self._tokens -= 1
            return True
        return False


# 模块级别的速率限制器实例（每秒 1 次请求，桶容量 10）
_rate_limiter = _TokenBucket(rate=1.0, capacity=10)

# ---------------------------------------------------------------------------
# 异步 OpenAI 客户端（延迟初始化）
# ---------------------------------------------------------------------------

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    """获取或创建 AsyncOpenAI 客户端单例。"""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_API_BASE_URL,
        )
    return _client


# ---------------------------------------------------------------------------
# 核心 API 调用
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3
_BACKOFF_INTERVALS = [1, 2, 4]  # 秒


async def call_llm_api(
    messages: list[dict],
    response_format: str | None = None,
    model: str | None = None,
) -> str:
    """调用大模型 API 并返回回复文本。

    Parameters
    ----------
    messages:
        OpenAI chat messages 格式的消息列表。
    response_format:
        若为 ``"json"``，则在请求中添加 ``response_format`` 参数
        以要求模型返回 JSON。

    Returns
    -------
    str
        模型回复文本；若所有重试均失败则返回降级回复。
    """
    # 速率限制检查
    if not _rate_limiter.acquire():
        logger.warning("LLM API 速率限制触发，返回降级回复")
        return FALLBACK_REPLY

    client = _get_client()

    kwargs: dict = {
        "model": model or settings.LLM_CHAT_MODEL,
        "messages": messages,
    }
    if response_format == "json":
        kwargs["response_format"] = {"type": "json_object"}

    last_exception: Exception | None = None

    for attempt in range(_MAX_RETRIES):
        try:
            completion = await client.chat.completions.create(**kwargs)
            content = completion.choices[0].message.content
            return content or ""
        except (APIError, APITimeoutError, RateLimitError) as exc:
            last_exception = exc
            logger.warning(
                "LLM API 调用失败 (第 %d/%d 次): %s",
                attempt + 1,
                _MAX_RETRIES,
                exc,
            )
            if attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(_BACKOFF_INTERVALS[attempt])
        except Exception as exc:
            last_exception = exc
            logger.error("LLM API 调用发生未知错误: %s", exc)
            break

    # 所有重试均失败 — 返回降级回复
    logger.error("LLM API 调用最终失败，返回降级回复。最后异常: %s", last_exception)
    return FALLBACK_REPLY
