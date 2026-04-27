import logging
import re
from datetime import datetime, timedelta
from typing import cast

try:
    import dateparser
    from dateparser.search import search_dates
except ModuleNotFoundError:  # pragma: no cover - exercised via monkeypatch in tests
    dateparser = None
    search_dates = None

logger = logging.getLogger(__name__)

_WEEKDAY_MAP = {
    "一": 0,
    "二": 1,
    "三": 2,
    "四": 3,
    "五": 4,
    "六": 5,
    "日": 6,
    "天": 6,
}


def parse_chinese_relative_time(text: str, *, allow_period_only: bool = False) -> datetime | None:
    if not text:
        return None

    now = datetime.now()
    base_date = now.date()

    is_weekday_expression = False

    if "后天" in text:
        base_date = (now + timedelta(days=2)).date()
    elif "明天" in text or "明晚" in text or "明早" in text:
        base_date = (now + timedelta(days=1)).date()
    elif "今天" in text or "今晚" in text or "今早" in text:
        base_date = now.date()
    elif "下周末" in text or "周末" in text:
        has_time_hint = bool(
            re.search(r"\d{1,2}\s*点", text)
            or any(
                word in text for word in ("上午", "早上", "中午", "下午", "晚上", "今晚", "明晚")
            )
        )
        if not has_time_hint:
            return None
        if "下周末" in text:
            # 下周末默认落在下周六
            days_until_next_monday = (7 - now.weekday()) % 7
            days_until_next_monday = 7 if days_until_next_monday == 0 else days_until_next_monday
            next_monday = now + timedelta(days=days_until_next_monday)
            base_date = (next_monday + timedelta(days=5)).date()
        else:
            # 周末默认落在最近的周六（当天是周末则用当天）
            day_delta = (5 - now.weekday()) % 7
            base_date = (now + timedelta(days=day_delta)).date()
    else:
        weekday_match = re.search(r"(?:下周|本周|这周)?(?:周|星期)([一二三四五六日天])", text)
        if weekday_match:
            target_weekday = _WEEKDAY_MAP[weekday_match.group(1)]
            day_delta = (target_weekday - now.weekday()) % 7
            has_next_week_hint = "下周" in text
            has_current_week_hint = "本周" in text or "这周" in text
            if has_next_week_hint:
                day_delta = day_delta + 7 if day_delta != 0 else 7
            elif not has_current_week_hint and day_delta == 0:
                day_delta = 7
            base_date = (now + timedelta(days=day_delta)).date()
            is_weekday_expression = True
        else:
            # 仅有“晚上/下午”等日内时段时，可按 today 解析（用于兜底场景）。
            if allow_period_only and any(
                word in text for word in ("今晚", "今早", "晚上", "下午", "上午", "早上", "中午")
            ):
                base_date = now.date()
            else:
                return None

    hour = 9
    minute = 0

    if any(word in text for word in ["上午", "早上", "清晨"]):
        hour = 9
    elif "中午" in text:
        hour = 12
    elif "下午" in text:
        hour = 15
    elif any(word in text for word in ["晚上", "今晚"]):
        hour = 20

    match = re.search(r"(\d{1,2})\s*点(?:\s*([0-5]?\d)\s*分?)?(半)?(?:前)?", text)
    if match:
        parsed_hour = int(match.group(1))
        explicit_minute = match.group(2)
        parsed_half = match.group(3)

        if (
            "下午" in text or "晚上" in text or "今晚" in text or "明晚" in text
        ) and parsed_hour < 12:
            parsed_hour += 12
        elif "中午" in text and parsed_hour < 11:
            parsed_hour += 12

        hour = parsed_hour
        if explicit_minute is not None:
            minute = int(explicit_minute)
        else:
            minute = 30 if parsed_half else 0
    elif is_weekday_expression:
        # “周几+晚上”可落在默认 20:00，其余时段无点钟时不直接落截止。
        if any(word in text for word in ("晚上", "今晚")):
            hour = 20
        else:
            return None

    return datetime(
        year=base_date.year,
        month=base_date.month,
        day=base_date.day,
        hour=hour,
        minute=minute,
    )


def parse_natural_due_date(raw_due_date: str | None, message: str) -> datetime | None:
    settings: dict[str, object] = {
        "PREFER_DATES_FROM": "future",
        "RELATIVE_BASE": datetime.now(),
    }

    if raw_due_date:
        manual_parsed = parse_chinese_relative_time(raw_due_date)
        if manual_parsed:
            return manual_parsed

        if dateparser is not None:
            try:
                parsed_date = cast(
                    datetime | None,
                    dateparser.parse(
                        raw_due_date,
                        languages=["zh"],
                        settings=settings,
                    ),
                )
                if parsed_date:
                    return parsed_date
            except Exception as exc:
                logger.debug("Failed to parse due date with dateparser: %s", exc)

        if search_dates is not None:
            try:
                searched = cast(
                    list[tuple[str, datetime]] | None,
                    search_dates(
                        raw_due_date,
                        languages=["zh"],
                        settings=settings,
                    ),
                )
                if searched:
                    return searched[0][1]
            except Exception as exc:
                logger.debug("Failed to search due date in entity text: %s", exc)

    manual_from_message = parse_chinese_relative_time(message)
    if manual_from_message:
        return manual_from_message

    if search_dates is not None:
        try:
            searched_from_message = cast(
                list[tuple[str, datetime]] | None,
                search_dates(
                    message,
                    languages=["zh"],
                    settings=settings,
                ),
            )
            if searched_from_message:
                return searched_from_message[0][1]
        except Exception as exc:
            logger.debug("Failed to search due date in message: %s", exc)

    manual_period_only = parse_chinese_relative_time(message, allow_period_only=True)
    if manual_period_only:
        return manual_period_only

    return None
