"""Retry transient LLM/API failures so a network hiccup does not drop a row.

``run.py`` used to catch any ``invoke`` exception, record ``Prediction="error"``,
and move on. One blip (timeout, 429, 502) then cost the whole sample. This
module retries those faults with exponential backoff; auth and bad-request
errors still fail immediately.
"""

from __future__ import annotations

import time
from typing import Any, Callable

RETRY_ATTEMPTS = 4
RETRY_BASE_DELAY_S = 2.0
RETRY_MAX_DELAY_S = 20.0

_NON_RETRYABLE_STATUS = frozenset({400, 401, 403, 404, 409, 422})
_RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504, 529})

_RETRYABLE_TYPES = (
    ConnectionError,
    TimeoutError,
    BrokenPipeError,
)

_RETRYABLE_NAME_FRAGMENTS = (
    "apiconnectionerror",
    "apitimeouterror",
    "ratelimiterror",
    "internalservererror",
    "apiservererror",
    "serviceunavailable",
    "timeout",
    "connecterror",
    "connecttimeout",
    "readtimeout",
    "remoteprotocolerror",
    "outputparserexception",
)

_RETRYABLE_TEXT = (
    "connection",
    "timeout",
    "timed out",
    "temporarily unavailable",
    "rate limit",
    "too many requests",
    "server error",
    "bad gateway",
    "gateway timeout",
    "service unavailable",
    "reset by peer",
    "connection reset",
    "broken pipe",
    "temporarily overloading",
    "please retry",
    "try again",
)


def _status_code(exc: BaseException) -> int | None:
    for attr in ("status_code", "http_status", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    response = getattr(exc, "response", None)
    if response is not None:
        value = getattr(response, "status_code", None)
        if isinstance(value, int):
            return value
    return None


def _is_retryable_one(exc: BaseException) -> bool:
    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
        return False
    status = _status_code(exc)
    if status in _NON_RETRYABLE_STATUS:
        return False
    if status in _RETRYABLE_STATUS or (status is not None and status >= 500):
        return True
    if isinstance(exc, _RETRYABLE_TYPES):
        return True
    name = type(exc).__name__.lower()
    if any(fragment in name for fragment in _RETRYABLE_NAME_FRAGMENTS):
        return True
    message = str(exc).lower()
    return any(fragment in message for fragment in _RETRYABLE_TEXT)


def is_retryable(exc: BaseException) -> bool:
    """True when another attempt at the same call is likely to succeed."""
    seen: set[int] = set()
    stack: list[BaseException] = [exc]
    while stack:
        current = stack.pop()
        marker = id(current)
        if marker in seen:
            continue
        seen.add(marker)
        if _is_retryable_one(current):
            return True
        if current.__cause__ is not None:
            stack.append(current.__cause__)
        if current.__context__ is not None:
            stack.append(current.__context__)
    return False


def _delay_s(attempt: int, base_delay: float) -> float:
    return min(RETRY_MAX_DELAY_S, base_delay * (2 ** (attempt - 1)))


def invoke_with_retry(
    llm: Any,
    messages: Any,
    *,
    attempts: int = RETRY_ATTEMPTS,
    base_delay: float = RETRY_BASE_DELAY_S,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = print,
) -> Any:
    """Call ``llm.invoke(messages)``, retrying transient failures.

    After ``attempts`` failures the last exception is re-raised so the caller
    can still record the row as an error rather than aborting the run.
    """
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    last: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return llm.invoke(messages)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            last = exc
            retries_left = attempts - attempt
            if retries_left <= 0 or not is_retryable(exc):
                raise
            delay = _delay_s(attempt, base_delay)
            log(
                f"   ! transient error ({type(exc).__name__}): {exc} "
                f"-- retry {attempt}/{attempts - 1} in {delay:g}s"
            )
            sleep(delay)
    assert last is not None
    raise last
