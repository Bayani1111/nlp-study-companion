import importlib
import sys
import types
from datetime import datetime

import pytest


def import_chat_time_parser(
    monkeypatch: pytest.MonkeyPatch,
    *,
    parse_result=None,
    search_result=None,
    parse_exception: Exception | None = None,
    search_exception: Exception | None = None,
):
    fake_dateparser = types.ModuleType("dateparser")

    def fake_parse(*args, **kwargs):
        if parse_exception is not None:
            raise parse_exception
        return parse_result

    fake_dateparser.parse = fake_parse

    fake_search_module = types.ModuleType("dateparser.search")

    def fake_search_dates(*args, **kwargs):
        if search_exception is not None:
            raise search_exception
        return search_result

    fake_search_module.search_dates = fake_search_dates

    monkeypatch.setitem(sys.modules, "dateparser", fake_dateparser)
    monkeypatch.setitem(sys.modules, "dateparser.search", fake_search_module)
    sys.modules.pop("app.services.chat_time_parser", None)
    return importlib.import_module("app.services.chat_time_parser")


@pytest.mark.asyncio
async def test_parse_chinese_relative_time_handles_tomorrow_afternoon_half_past(
    monkeypatch: pytest.MonkeyPatch,
):
    module = import_chat_time_parser(monkeypatch)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 4, 24, 9, 0, 0)

    monkeypatch.setattr(module, "datetime", FrozenDateTime)

    parsed = module.parse_chinese_relative_time("明天下午3点半")

    assert parsed == datetime(2026, 4, 25, 15, 30)


@pytest.mark.asyncio
async def test_parse_natural_due_date_prefers_manual_relative_time_in_raw_due_date(
    monkeypatch: pytest.MonkeyPatch,
):
    fallback_date = datetime(2030, 1, 1, 9, 0)
    module = import_chat_time_parser(monkeypatch, parse_result=fallback_date)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 4, 24, 9, 0, 0)

    monkeypatch.setattr(module, "datetime", FrozenDateTime)

    parsed = module.parse_natural_due_date("明天晚上8点", "帮我记个任务")

    assert parsed == datetime(2026, 4, 25, 20, 0)


@pytest.mark.asyncio
async def test_parse_natural_due_date_falls_back_to_dateparser_parse(
    monkeypatch: pytest.MonkeyPatch,
):
    parsed_date = datetime(2026, 4, 28, 18, 0)
    module = import_chat_time_parser(monkeypatch, parse_result=parsed_date)

    result = module.parse_natural_due_date("4月28日晚上6点", "帮我安排一下")

    assert result == parsed_date


@pytest.mark.asyncio
async def test_parse_natural_due_date_falls_back_to_search_dates_from_message(
    monkeypatch: pytest.MonkeyPatch,
):
    searched_date = datetime(2026, 4, 26, 14, 0)
    module = import_chat_time_parser(
        monkeypatch,
        parse_result=None,
        search_result=[("下午两点", searched_date)],
    )

    result = module.parse_natural_due_date(None, "下午两点提醒我复习")

    assert result == searched_date


@pytest.mark.asyncio
async def test_parse_natural_due_date_returns_none_when_all_strategies_fail(
    monkeypatch: pytest.MonkeyPatch,
):
    module = import_chat_time_parser(
        monkeypatch,
        parse_result=None,
        search_result=None,
        parse_exception=ValueError("bad parse"),
        search_exception=ValueError("bad search"),
    )

    result = module.parse_natural_due_date("没有时间", "也没有时间")

    assert result is None


@pytest.mark.asyncio
async def test_parse_chinese_relative_time_handles_weekday_expression(
    monkeypatch: pytest.MonkeyPatch,
):
    module = import_chat_time_parser(monkeypatch)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            # Friday
            return cls(2026, 4, 24, 9, 0, 0)

    monkeypatch.setattr(module, "datetime", FrozenDateTime)

    parsed = module.parse_chinese_relative_time("周三下午4点提醒我参加算法讨论课")

    assert parsed == datetime(2026, 4, 29, 16, 0)


@pytest.mark.asyncio
async def test_parse_chinese_relative_time_returns_none_for_weekday_without_explicit_hour(
    monkeypatch: pytest.MonkeyPatch,
):
    module = import_chat_time_parser(monkeypatch)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 4, 24, 9, 0, 0)

    monkeypatch.setattr(module, "datetime", FrozenDateTime)

    parsed = module.parse_chinese_relative_time("下周二下午安排一次组内代码评审")
    assert parsed is None


@pytest.mark.asyncio
async def test_parse_chinese_relative_time_handles_weekday_evening_without_explicit_hour(
    monkeypatch: pytest.MonkeyPatch,
):
    module = import_chat_time_parser(monkeypatch)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 4, 24, 9, 0, 0)

    monkeypatch.setattr(module, "datetime", FrozenDateTime)

    parsed = module.parse_chinese_relative_time("周五晚上复盘本周学习")
    assert parsed == datetime(2026, 4, 24, 20, 0)


@pytest.mark.asyncio
async def test_parse_chinese_relative_time_handles_period_only_expression_as_today(
    monkeypatch: pytest.MonkeyPatch,
):
    module = import_chat_time_parser(monkeypatch)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 4, 24, 9, 0, 0)

    monkeypatch.setattr(module, "datetime", FrozenDateTime)

    parsed = module.parse_chinese_relative_time("晚上把项目需求文档补齐", allow_period_only=True)
    assert parsed == datetime(2026, 4, 24, 20, 0)


@pytest.mark.asyncio
async def test_parse_chinese_relative_time_handles_tonight_and_tomorrow_night_aliases(
    monkeypatch: pytest.MonkeyPatch,
):
    module = import_chat_time_parser(monkeypatch)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 4, 24, 9, 0, 0)

    monkeypatch.setattr(module, "datetime", FrozenDateTime)

    tonight = module.parse_chinese_relative_time("今晚10点前完成任务")
    tomorrow_night = module.parse_chinese_relative_time("明晚8点复习概率论")

    assert tonight == datetime(2026, 4, 24, 22, 0)
    assert tomorrow_night == datetime(2026, 4, 25, 20, 0)


@pytest.mark.asyncio
async def test_parse_chinese_relative_time_handles_weekend_expression(
    monkeypatch: pytest.MonkeyPatch,
):
    module = import_chat_time_parser(monkeypatch)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            # Friday
            return cls(2026, 4, 24, 9, 0, 0)

    monkeypatch.setattr(module, "datetime", FrozenDateTime)

    parsed = module.parse_chinese_relative_time("周末下午复习计算机网络")
    assert parsed == datetime(2026, 4, 25, 15, 0)
