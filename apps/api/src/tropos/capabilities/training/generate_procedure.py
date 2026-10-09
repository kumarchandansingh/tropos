"""Application service connecting governed Tropos retrieval to procedure extraction."""

from dataclasses import dataclass

from tropos.capabilities.training.procedure import (
    EvidenceExcerpt,
    ProcedureDraft,
    ProcedureExtractor,
)
from tropos.core.application.ports.retrieval import KnowledgeChunkRetriever
from tropos.core.application.retrieval.models import KnowledgeSearchRequest, RetrievalAccessContext


@dataclass(frozen=True, slots=True)
class GenerateProcedureRequest:
    query: str
    tenant_id: str
    groups: tuple[str, ...] = ()
    retrieval_limit: int = 8

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError("query must not be blank")
        if not self.tenant_id.strip():
            raise ValueError("tenant_id must not be blank")
        if not 1 <= self.retrieval_limit <= 100:
            raise ValueError("retrieval_limit must be between 1 and 100")


class GenerateProcedure:
    """Retrieve authorized evidence, preserve provenance, then invoke an extractor."""

    def __init__(
        self,
        retriever: KnowledgeChunkRetriever,
        extractor: ProcedureExtractor,
    ) -> None:
        self._retriever = retriever
        self._extractor = extractor

    def execute(self, request: GenerateProcedureRequest) -> ProcedureDraft:
        search = KnowledgeSearchRequest(
            query=request.query,
            access=RetrievalAccessContext(
                tenant_id=request.tenant_id,
                groups=request.groups,
            ),
            limit=request.retrieval_limit,
        )
        results = self._retriever.search(search)
        if not results:
            raise LookupError("No authorized evidence found for procedure generation")

        evidence = tuple(
            EvidenceExcerpt(
                source_id=result.chunk.chunk_id,
                locator=(
                    f"{result.chunk.source_system}:{result.chunk.source_record_id}"
                    f"@v{result.chunk.source_version}"
                    f"#chars={result.chunk.start_offset}-{result.chunk.end_offset}"
                ),
                text=result.chunk.text,
            )
            for result in results
        )
        return self._extractor.extract(evidence)
