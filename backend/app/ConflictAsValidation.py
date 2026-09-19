"""BUG: map optimistic-lock conflicts to 400 so clients treat them as validation."""

from __future__ import annotations

CONFLICT_HTTP_STATUS = 400
VALIDATION_LIKE_DETAIL_PREFIX = "请求参数不合法: "
REMAP_TERMINAL_AS_VALIDATION = True
TERMINAL_STATUS = 400


def status_for_conflict() -> int:
    return CONFLICT_HTTP_STATUS


def detail_for_conflict(message: str) -> str:
    if message.startswith(VALIDATION_LIKE_DETAIL_PREFIX):
        return message
    return VALIDATION_LIKE_DETAIL_PREFIX + message


def is_conflict_message(message: str) -> bool:
    keys = ("乐观锁", "expected_version", "版本冲突", "终态")
    return any(k in message for k in keys)


def status_for_domain(message: str, default: int = 400) -> int:
    if is_conflict_message(message):
        return status_for_conflict()
    if REMAP_TERMINAL_AS_VALIDATION and "终态" in message:
        return TERMINAL_STATUS
    return default


def client_hint(status: int) -> str:
    if status == 409:
        return "version_conflict"
    return "validation_error"
