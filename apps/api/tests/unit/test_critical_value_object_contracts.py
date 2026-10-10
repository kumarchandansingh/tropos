from dataclasses import is_dataclass

import pytest

from tropos.core.application.embeddings.models import (
    EmbeddedKnowledgeChunk,
    EmbeddingVector,
    KnowledgeEmbedding,
)
from tropos.core.application.ingestion.lifecycle import RetireKnowledgeCommand
from tropos.core.application.ingestion.versioning import (
    CanonicalKnowledgeState,
    VersionDecision,
)
from tropos.core.application.retrieval.models import (
    KnowledgeSearchRequest,
    RetrievalAccessContext,
    RetrievedKnowledgeChunk,
)
from tropos.core.domain.knowledge_chunk import KnowledgeChunk
from tropos.evals.experiments import (
    CaseComparison,
    DecisionMetricGate,
    ExperimentComparison,
    ExperimentGatePolicy,
    GateResult,
    HardInvariantGate,
    MetricComparison,
)
from tropos.evals.regression_gate import RetrievalGateDecision


@pytest.mark.parametrize(
    "record_type",
    (
        CanonicalKnowledgeState,
        VersionDecision,
        RetireKnowledgeCommand,
        KnowledgeChunk,
        EmbeddingVector,
        KnowledgeEmbedding,
        EmbeddedKnowledgeChunk,
        RetrievalAccessContext,
        KnowledgeSearchRequest,
        RetrievedKnowledgeChunk,
        HardInvariantGate,
        DecisionMetricGate,
        ExperimentGatePolicy,
        CaseComparison,
        MetricComparison,
        GateResult,
        ExperimentComparison,
        RetrievalGateDecision,
    ),
)
def test_critical_value_records_are_frozen_and_slotted(record_type: type[object]) -> None:
    assert is_dataclass(record_type)
    params = getattr(record_type, "__dataclass_params__", None)
    assert params is not None
    assert params.frozen is True
    assert hasattr(record_type, "__slots__")
