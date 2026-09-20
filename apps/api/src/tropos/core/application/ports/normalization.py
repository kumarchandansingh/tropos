from typing import Protocol

from tropos.core.application.ingestion.normalization import (
    ExtractedKnowledgeText,
    NormalizedKnowledge,
)


class KnowledgeNormalizer(Protocol):
    """Create a deterministic canonical representation for version comparison."""

    def normalize(self, source: ExtractedKnowledgeText) -> NormalizedKnowledge: ...
