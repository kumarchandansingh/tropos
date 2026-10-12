from __future__ import annotations

# ruff: noqa: E501

from pathlib import Path

from tropos.cli import ingest_local_file
from tropos.core.adapters.retrieval.sqlite_fts import SQLiteFtsKnowledgeRetriever
from tropos.core.application.ingestion.run_state import IngestionOutcome
from tropos.core.application.retrieval.models import (
    KnowledgeSearchRequest,
    RetrievalAccessContext,
)


def test_ingest_file_creates_searchable_current_knowledge(tmp_path: Path) -> None:
    source = tmp_path / "runbook.md"
    source.write_text(
        "# Certificate rotation\n\nRestart the device after certificate rotation.",
        encoding="utf-8",
    )
    database = tmp_path / "tropos.db"

    result = ingest_local_file(
        file_path=source,
        database_path=database,
        tenant_id="tenant-a",
    )

    assert result.outcome is IngestionOutcome.VERSION_CREATED
    assert result.chunks_written > 0

    retrieved = SQLiteFtsKnowledgeRetriever(database).search(
        KnowledgeSearchRequest(
            query="certificate rotation",
            access=RetrievalAccessContext(tenant_id="tenant-a"),
        )
    )
    assert retrieved
    assert retrieved[0].chunk.knowledge_id == result.knowledge_id


def test_reingest_formatting_only_change_does_not_create_content_version(tmp_path: Path) -> None:
    source = tmp_path / "procedure.md"
    source.write_text("# Reset\n\nRestart the service.", encoding="utf-8")
    database = tmp_path / "tropos.db"

    first = ingest_local_file(
        file_path=source,
        database_path=database,
        tenant_id="tenant-a",
    )

    source.write_text("# Reset  \n\n\nRestart the service.   \n", encoding="utf-8")
    second = ingest_local_file(
        file_path=source,
        database_path=database,
        tenant_id="tenant-a",
        knowledge_id=first.knowledge_id,
    )

    assert first.outcome is IngestionOutcome.VERSION_CREATED
    assert second.outcome is IngestionOutcome.NO_CHANGE
    assert second.chunks_written == 0


def test_restricted_file_is_not_retrieved_without_matching_group(tmp_path: Path) -> None:
    source = tmp_path / "restricted.txt"
    source.write_text("Escalation token recovery procedure", encoding="utf-8")
    database = tmp_path / "tropos.db"

    ingest_local_file(
        file_path=source,
        database_path=database,
        tenant_id="tenant-a",
        groups=("support-l3",),
    )

    retriever = SQLiteFtsKnowledgeRetriever(database)
    denied = retriever.search(
        KnowledgeSearchRequest(
            query="escalation recovery",
            access=RetrievalAccessContext(tenant_id="tenant-a", groups=("support-l2",)),
        )
    )
    allowed = retriever.search(
        KnowledgeSearchRequest(
            query="escalation recovery",
            access=RetrievalAccessContext(tenant_id="tenant-a", groups=("support-l3",)),
        )
    )

    assert denied == ()
    assert allowed



def test_dynamic_html_embedded_data_becomes_searchable(tmp_path: Path) -> None:
    source = tmp_path / "retail-map.html"
    source.write_text(
        """
<html>
  <head><title>Retail Analytics</title></head>
  <body>
    <h1>Retail solution map</h1>
    <div id="cards"></div>
    <script>
    const CARDS=[
      {title:'Falling traffic / footfall',
       problem:'Footfall is declining while marketing spend rises and visits do not respond.',
       analytics:'Marketing mix modelling and geo-lift testing isolate which channels drive incremental store visits.',
       steps:[
         {title:'Baseline footfall',desc:'Segment by store, day-part, and week to identify the decline pattern.'},
         {title:'Attribution audit',desc:'Identify which media spend drives store visits instead of online sessions only.'}
       ]},
      {title:'Low conversion rate',
       problem:'High footfall but low purchase rate and checkout abandonment indicate funnel friction.',
       analytics:'Funnel analytics maps entry, browse, add-to-cart, checkout, and purchase drop-off.',
       steps:[
         {title:'Funnel diagnosis',desc:'Find the largest conversion drop-off before choosing an intervention.'},
         {title:'Root cause analysis',desc:'Test product, price, experience, and trust hypotheses separately.'}
       ]},
      {title:'Declining basket size / AOV',
       problem:'Average order value shrinks when customers buy one item and leave.',
       analytics:'Market basket analysis finds products bought together and recommendation engines suggest next-best products.',
       steps:[
         {title:'Association mining',desc:'Identify product pairs and triples with the highest co-purchase lift.'},
         {title:'Bundle creation',desc:'Create curated bundles and measure attach rate against standalone sales.'}
       ]}
    ];
    </script>
  </body>
</html>
""",
        encoding="utf-8",
    )
    database = tmp_path / "tropos.db"

    result = ingest_local_file(
        file_path=source,
        database_path=database,
        tenant_id="tenant-a",
    )

    assert result.outcome is IngestionOutcome.VERSION_CREATED
    assert result.chunks_written > 1

    retriever = SQLiteFtsKnowledgeRetriever(database)
    footfall = retriever.search(
        KnowledgeSearchRequest(
            query="falling footfall",
            access=RetrievalAccessContext(tenant_id="tenant-a"),
        )
    )
    conversion = retriever.search(
        KnowledgeSearchRequest(
            query="low conversion funnel",
            access=RetrievalAccessContext(tenant_id="tenant-a"),
        )
    )
    basket = retriever.search(
        KnowledgeSearchRequest(
            query="basket size average order value",
            access=RetrievalAccessContext(tenant_id="tenant-a"),
        )
    )

    assert footfall
    assert "Falling traffic / footfall" in footfall[0].chunk.text
    assert conversion
    assert "Low conversion rate" in conversion[0].chunk.text
    assert basket
    assert "Declining basket size / AOV" in basket[0].chunk.text
