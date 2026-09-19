from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    """Canonical knowledge content independent of its source system."""

    knowledge_id: str
    source_system: str
    source_record_id: str
    version: str
    title: str
    content: str

    def __post_init__(self) -> None:
        if not self.knowledge_id.strip():
            raise ValueError("knowledge_id must not be blank")

        if not self.source_system.strip():
            raise ValueError("source_system must not be blank")

        if not self.source_record_id.strip():
            raise ValueError("source_record_id must not be blank")

        if not self.version.strip():
            raise ValueError("version must not be blank")

        if not self.content.strip():
            raise ValueError("content must not be blank")


@dataclass(frozen=True, slots=True)
class RetrievedKnowledge:
    """One retrieved document and its normalized relevance score."""

    document: KnowledgeDocument
    score: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("score must be between 0.0 and 1.0")
