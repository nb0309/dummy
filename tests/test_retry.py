"""Retry policy for LLM calls — no Azure credentials, no tokens."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.retry import invoke_with_retry, is_retryable  # noqa: E402


class _AuthError(Exception):
    status_code = 401


class _RateLimit(Exception):
    status_code = 429


class _ServerError(Exception):
    status_code = 502


class _FakeLLM:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        self.messages = messages
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def test_timeout_and_connection_errors_are_retryable():
    assert is_retryable(TimeoutError("timed out"))
    assert is_retryable(ConnectionError("network hiccup"))
    assert is_retryable(_RateLimit("Too Many Requests"))
    assert is_retryable(_ServerError("bad gateway"))
    wrapped = RuntimeError("invoke failed")
    wrapped.__cause__ = ConnectionError("reset by peer")
    assert is_retryable(wrapped)


def test_auth_and_bad_request_are_not_retryable():
    assert not is_retryable(_AuthError("invalid api key"))
    bad = Exception("bad request")
    bad.status_code = 400  # type: ignore[attr-defined]
    assert not is_retryable(bad)
    assert not is_retryable(ValueError("model returned an unexpected field"))


def test_retries_then_succeeds():
    llm = _FakeLLM(
        [ConnectionError("hiccup"), TimeoutError("again"), {"ok": True}]
    )
    sleeps: list[float] = []
    logs: list[str] = []
    result = invoke_with_retry(
        llm,
        ["msg"],
        attempts=4,
        base_delay=1.0,
        sleep=sleeps.append,
        log=logs.append,
    )
    assert result == {"ok": True}
    assert llm.calls == 3
    assert sleeps == [1.0, 2.0]
    assert len(logs) == 2
    assert "retry 1/3" in logs[0]


def test_non_retryable_raises_immediately():
    llm = _FakeLLM([_AuthError("nope")])
    with pytest.raises(_AuthError):
        invoke_with_retry(llm, ["msg"], sleep=lambda _d: None)
    assert llm.calls == 1


def test_exhausted_retries_reraise():
    llm = _FakeLLM(
        [ConnectionError("a"), ConnectionError("b"), ConnectionError("c")]
    )
    with pytest.raises(ConnectionError, match="c"):
        invoke_with_retry(
            llm, ["msg"], attempts=3, base_delay=0.5, sleep=lambda _d: None
        )
    assert llm.calls == 3
