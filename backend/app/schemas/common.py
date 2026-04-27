def strip_text(value: str) -> str:
    return value.strip()


def strip_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def validate_non_empty_text(value: str) -> str:
    if not value:
        raise ValueError("该字段不能为空")
    return value


def validate_positive_optional_int(value: int | None, field_name: str) -> int | None:
    if value is not None and value < 0:
        raise ValueError(f"{field_name} 不能小于 0")
    return value
