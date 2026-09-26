from datetime import UTC, datetime

import pytest

from tropos.core.application.ingestion.raw_record import RawKnowledgeRecord
from tropos.core.application.ports.sources import (
    SourceCapture,
    SourceRateLimitedError,
    SourceRecordNotFoundError,
    SourceUnavailableError,
)
from tropos.core.application.sources.reliability import (
    RetryingSourceConnector,
    SourceRetryPolicy,
)
from tropos.core.domain.access import AccessPolicy, AccessScope


class SequencedConnector:
    def __init__(self, outcomes: list[SourceCapture | Exception]) -> None:
        self._outcomes = outcomes
        self.calls = 0

    @property
    def source_namespace(self) -> str:
        return "fake:test"

    def capture(self, source_record_id: str) -> SourceCapture:
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _capture() -> SourceCapture:
    raw = RawKnowledgeRecord(
        source_system="fake:test",
        source_record_id="article-1",
        source_version="1",
        content_type="text/plain",
        payload=b"hello",
        access_policy=AccessPolicy(tenant_id="tenant-a", scope=AccessScope.TENANT),
        captured_at=datetime(2026, 9, 26, tzinfo=UTC),
    )
    return SourceCapture(raw_record=raw)


def test_retries_transient_failures_with_exponential_backoff() -> None:
    connector = SequencedConnector(
        [
            SourceUnavailableError("timeout"),
            SourceUnavailableError("temporary 503"),
            _capture(),
        ]
    )
    sleeps: list[float] = []
    reliable = RetryingSourceConnector(connector=connector, sleeper=sleeps.append)

    result = reliable.capture("article-1")

    assert result == _capture()
    assert connector.calls == 3
    assert sleeps == [1.0, 2.0]


def test_rate_limit_honors_source_retry_after_hint() -> None:
    connector = SequencedConnector(
        [SourceRateLimitedError("429", retry_after_seconds=7.5), _capture()]
    )
    sleeps: list[float] = []
    reliable = RetryingSourceConnector(connector=connector, sleeper=sleeps.append)

    reliable.capture("article-1")

    assert connector.calls == 2
    assert sleeps == [7.5]


def test_terminal_failure_is_not_retried() -> None:
    connector = SequencedConnector([SourceRecordNotFoundError("missing")])
    sleeps: list[float] = []
    reliable = RetryingSourceConnector(connector=connector, sleeper=sleeps.append)

    with pytest.raises(SourceRecordNotFoundError):
        reliable.capture("missing")

    assert connector.calls == 1
    assert sleeps == []


def test_retry_exhaustion_raises_last_transient_failure() -> None:
    connector = SequencedConnector(
        [
            SourceUnavailableError("first"),
            SourceUnavailableError("second"),
            SourceUnavailableError("third"),
        ]
    )
    sleeps: list[float] = []
    reliable = RetryingSourceConnector(
        connector=connector,
        policy=SourceRetryPolicy(max_attempts=3),
        sleeper=sleeps.append,
    )

    with pytest.raises(SourceUnavailableError, match="third"):
        reliable.capture("article-1")

    assert connector.calls == 3
    assert sleeps == [1.0, 2.0]


def test_retry_policy_validates_bounds_and_caps_delay() -> None:
    policy = SourceRetryPolicy(
        max_attempts=5,
        initial_backoff_seconds=2.0,
        backoff_multiplier=3.0,
        max_backoff_seconds=10.0,
    )

    assert policy.delay_after_failure(1) == 2.0
    assert policy.delay_after_failure(2) == 6.0
    assert policy.delay_after_failure(3) == 10.0

    with pytest.raises(ValueError):
        SourceRetryPolicy(max_attempts=0)
