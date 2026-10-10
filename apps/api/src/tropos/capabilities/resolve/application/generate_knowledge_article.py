"""Application service for grounded Knowledge Article generation."""

from dataclasses import dataclass

from tropos.capabilities.resolve.application.knowledge_article_request import (
    KnowledgeArticleGenerationRequest,
    KnowledgeArticleRetrievalIntent,
    PromptProfileRef,
    build_prompt_inputs,
    build_retrieval_intent,
)
from tropos.capabilities.resolve.application.ports.knowledge_article import (
    KnowledgeArticleEvidenceExcerpt,
    KnowledgeArticleGenerator,
)
from tropos.core.application.ports.retrieval import KnowledgeChunkRetriever
from tropos.core.application.retrieval.models import (
    KnowledgeSearchRequest,
    RetrievalAccessContext,
)
from tropos.core.domain.evidence import EvidenceRef
from tropos.core.domain.knowledge_article import KnowledgeArticleDraft


@dataclass(frozen=True, slots=True)
class GenerateKnowledgeArticleCommand:
    request: KnowledgeArticleGenerationRequest
    tenant_id: str
    prompt_profile: PromptProfileRef
    groups: tuple[str, ...] = ()
    retrieval_limit: int = 8

    def __post_init__(self) -> None:
        if not self.tenant_id.strip():
            raise ValueError("tenant_id must not be blank")
        if not 1 <= self.retrieval_limit <= 100:
            raise ValueError("retrieval_limit must be between 1 and 100")


def build_retrieval_query(intent: KnowledgeArticleRetrievalIntent) -> str:
    parts = [intent.subject, intent.product]
    if intent.module is not None:
        parts.append(intent.module)
    parts.extend(intent.keywords)
    return " ".join(part.strip() for part in parts if part.strip())


class GenerateKnowledgeArticle:
    """Retrieve authorized evidence and invoke a provider-neutral generator."""

    def __init__(
        self,
        retriever: KnowledgeChunkRetriever,
        generator: KnowledgeArticleGenerator,
    ) -> None:
        self._retriever = retriever
        self._generator = generator

    def execute(self, command: GenerateKnowledgeArticleCommand) -> KnowledgeArticleDraft:
        intent = build_retrieval_intent(command.request)
        query = build_retrieval_query(intent)
        search = KnowledgeSearchRequest(
            query=query,
            access=RetrievalAccessContext(
                tenant_id=command.tenant_id,
                groups=command.groups,
            ),
            limit=command.retrieval_limit,
        )
        results = self._retriever.search(search)
        if not results:
            raise LookupError("No authorized evidence found for Knowledge Article generation")

        evidence = tuple(
            KnowledgeArticleEvidenceExcerpt(
                reference=EvidenceRef(
                    chunk_id=result.chunk.chunk_id,
                    knowledge_id=result.chunk.knowledge_id,
                    source_system=result.chunk.source_system,
                    source_record_id=result.chunk.source_record_id,
                    source_version=result.chunk.source_version,
                    locator=(
                        f"{result.chunk.source_system}:{result.chunk.source_record_id}"
                        f"@v{result.chunk.source_version}"
                        f"#chars={result.chunk.start_offset}-{result.chunk.end_offset}"
                    ),
                    content_fingerprint=result.chunk.content_fingerprint,
                ),
                text=result.chunk.text,
            )
            for result in results
        )
        prompt_inputs = build_prompt_inputs(command.request, command.prompt_profile)
        return self._generator.generate(prompt_inputs, evidence)
