from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from tropos.core.application.ingestion.raw_record import RawKnowledgeRecord
from tropos.core.application.ports.sources import (
    SourceCapture,
    SourceCaptureError,
    SourceRecordNotFoundError,
    UnsupportedSourceArtifactError,
)
from tropos.core.domain.access import AccessPolicy

_CONTENT_TYPES = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".html": "text/html",
    ".htm": "text/html",
    ".xhtml": "application/xhtml+xml",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class LocalFileSourceConnector:
    """Capture supported files below one configured root as immutable source records."""

    def __init__(
        self,
        *,
        root: str | Path,
        source_namespace: str,
        access_policy: AccessPolicy,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        namespace = source_namespace.strip()
        if not namespace:
            raise ValueError("source_namespace must not be blank")
        if not isinstance(access_policy, AccessPolicy):
            raise TypeError("access_policy must be an AccessPolicy")

        resolved_root = Path(root).resolve()
        if not resolved_root.is_dir():
            raise ValueError("root must be an existing directory")

        self._root = resolved_root
        self._source_namespace = namespace
        self._access_policy = access_policy
        self._clock = clock or (lambda: datetime.now(UTC))

    @property
    def source_namespace(self) -> str:
        return self._source_namespace

    def capture(self, source_record_id: str) -> SourceCapture:
        record_id = source_record_id.strip()
        if not record_id:
            raise ValueError("source_record_id must not be blank")

        candidate = (self._root / record_id).resolve()
        try:
            relative = candidate.relative_to(self._root)
        except ValueError as exc:
            raise SourceCaptureError("source_record_id must remain below connector root") from exc

        if not candidate.is_file():
            raise SourceRecordNotFoundError(f"source record not found: {relative.as_posix()}")

        content_type = _CONTENT_TYPES.get(candidate.suffix.lower())
        if content_type is None:
            raise UnsupportedSourceArtifactError(
                f"unsupported local source artifact: {candidate.suffix.lower() or '<no extension>'}"
            )

        payload = candidate.read_bytes()
        if not payload:
            raise SourceCaptureError("source artifact must not be empty")

        captured_at = self._clock()
        if captured_at.tzinfo is None or captured_at.utcoffset() is None:
            raise ValueError("connector clock must return a timezone-aware datetime")

        source_updated_at = datetime.fromtimestamp(candidate.stat().st_mtime, tz=UTC)
        canonical_record_id = relative.as_posix()
        source_version = sha256(payload).hexdigest()

        return SourceCapture(
            raw_record=RawKnowledgeRecord(
                source_system=self._source_namespace,
                source_record_id=canonical_record_id,
                source_version=source_version,
                content_type=content_type,
                payload=payload,
                access_policy=self._access_policy,
                captured_at=captured_at,
            ),
            source_uri=candidate.as_uri(),
            source_updated_at=source_updated_at,
        )
