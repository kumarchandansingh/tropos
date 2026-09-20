from hashlib import sha256

from tropos.core.domain.knowledge import KnowledgeDocument
from tropos.core.domain.knowledge_chunk import (
    KnowledgeChunk,
    text_fingerprint,
    validate_chunk_set,
)


class DeterministicKnowledgeChunker:
    """Split canonical text while preferring human-readable boundaries."""

    def __init__(
        self,
        *,
        max_characters: int = 1_200,
        minimum_break_ratio: float = 0.5,
        strategy_version: str = "structural-character-v1",
    ) -> None:
        if max_characters < 32:
            raise ValueError("max_characters must be at least 32")
        if not 0.0 < minimum_break_ratio <= 1.0:
            raise ValueError("minimum_break_ratio must be between 0 and 1")
        if not strategy_version.strip():
            raise ValueError("strategy_version must not be blank")

        self._max_characters = max_characters
        self._minimum_break_ratio = minimum_break_ratio
        self._strategy_version = strategy_version

    def chunk(self, document: KnowledgeDocument) -> tuple[KnowledgeChunk, ...]:
        spans = self._find_spans(document.content)
        chunks = tuple(
            self._build_chunk(document, sequence_number, start, end)
            for sequence_number, (start, end) in enumerate(spans)
        )
        validate_chunk_set(document=document, chunks=chunks)
        return chunks

    def _find_spans(self, text: str) -> tuple[tuple[int, int], ...]:
        spans: list[tuple[int, int]] = []
        start = 0

        while start < len(text):
            hard_end = min(start + self._max_characters, len(text))
            end = hard_end if hard_end == len(text) else self._preferred_end(text, start, hard_end)
            spans.append((start, end))
            start = end

        return tuple(spans)

    def _preferred_end(self, text: str, start: int, hard_end: int) -> int:
        window = text[start:hard_end]
        minimum = int(self._max_characters * self._minimum_break_ratio)

        for separator in ("\n\n", "\n", ". ", " "):
            position = window.rfind(separator, minimum)
            if position >= 0:
                return start + position + len(separator)

        return hard_end

    def _build_chunk(
        self,
        document: KnowledgeDocument,
        sequence_number: int,
        start: int,
        end: int,
    ) -> KnowledgeChunk:
        text = document.content[start:end]
        fingerprint = text_fingerprint(text)
        identity = "\0".join(
            (
                document.knowledge_id,
                document.normalized_content_fingerprint,
                document.normalization_strategy_version,
                self._strategy_version,
                str(start),
                str(end),
                fingerprint,
            )
        )
        chunk_id = f"chunk_{sha256(identity.encode('utf-8')).hexdigest()}"

        return KnowledgeChunk(
            chunk_id=chunk_id,
            knowledge_id=document.knowledge_id,
            source_system=document.source_system,
            source_record_id=document.source_record_id,
            source_version=document.source_version,
            document_title=document.title,
            sequence_number=sequence_number,
            text=text,
            start_offset=start,
            end_offset=end,
            content_fingerprint=fingerprint,
            ingestion_fingerprint=document.ingestion_fingerprint,
            normalized_content_fingerprint=document.normalized_content_fingerprint,
            normalization_strategy_version=document.normalization_strategy_version,
            access_policy=document.access_policy,
            strategy_version=self._strategy_version,
        )
