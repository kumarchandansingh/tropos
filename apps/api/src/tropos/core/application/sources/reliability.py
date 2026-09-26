from collections.abc import Callable
from dataclasses import dataclass
from time import sleep as _sleep

from tropos.core.application.ports.sources import (
    KnowledgeSourceConnector,
    RetryableSourceError,
    SourceCapture,
    SourceRateLimitedError,
)


@dataclass(frozen=True, slots=True)
class SourceRetryPolicy:
    """Bounded retry policy for transient source-capture failures."""

    max_attempts: int = 3
    initial_backoff_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    max_backoff_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.initial_backoff_seconds < 0:
            raise ValueError("initial_backoff_seconds must be non-negative")
        if self.backoff_multiplier < 1:
            raise ValueError("backoff_multiplier must be at least 1")
        if self.max_backoff_seconds < 0:
            raise ValueError("max_backoff_seconds must be non-negative")
        if self.max_backoff_seconds < self.initial_backoff_seconds:
            raise ValueError("max_backoff_seconds must be >= initial_backoff_seconds")

    def delay_after_failure(self, failed_attempt: int) -> float:
        """Return the bounded exponential delay after a failed attempt."""

        if failed_attempt < 1:
            raise ValueError("failed_attempt must be at least 1")
        delay = self.initial_backoff_seconds * (self.backoff_multiplier ** (failed_attempt - 1))
        return min(delay, self.max_backoff_seconds)


class RetryingSourceConnector:
    """Decorate a connector with bounded retries for explicitly transient failures."""

    def __init__(
        self,
        *,
        connector: KnowledgeSourceConnector,
        policy: SourceRetryPolicy | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self._connector = connector
        self._policy = policy or SourceRetryPolicy()
        self._sleeper = sleeper or _sleep

    @property
    def source_namespace(self) -> str:
        return self._connector.source_namespace

    def capture(self, source_record_id: str) -> SourceCapture:
        attempt = 1
        while True:
            try:
                return self._connector.capture(source_record_id)
            except SourceRateLimitedError as exc:
                if attempt >= self._policy.max_attempts:
                    raise
                delay = (
                    exc.retry_after_seconds
                    if exc.retry_after_seconds is not None
                    else self._policy.delay_after_failure(attempt)
                )
                self._sleeper(delay)
                attempt += 1
            except RetryableSourceError:
                if attempt >= self._policy.max_attempts:
                    raise
                self._sleeper(self._policy.delay_after_failure(attempt))
                attempt += 1
