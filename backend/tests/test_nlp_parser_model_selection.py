from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.services.nlp_parser import call_llm_for_intent


@pytest.mark.asyncio
async def test_call_llm_for_intent_uses_extraction_model():
    with patch(
        "app.services.nlp_parser.call_llm_api",
        new=AsyncMock(return_value='{"intent":"general_chat","entities":{}}'),
    ) as mock_call:
        result = await call_llm_for_intent("帮我看看今天学什么", history=[])

    assert result["intent"] == "general_chat"
    assert mock_call.await_count == 1
    assert mock_call.await_args.kwargs["model"] == settings.LLM_EXTRACTION_MODEL
