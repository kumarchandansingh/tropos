from dataclasses import replace
from datetime import UTC, datetime

from tropos.core.adapters.normalization.deterministic import DeterministicKnowledgeNormalizer
from tropos.core.application.ingestion.normalization import (
    ExtractedKnowledgeText,
    NormalizedKnowledge,
    TextFormat,
)
from tropos.core.application.ingestion.raw_record import RawKnowledgeRecord
from tropos.core.application.ingestion.versioning import (
    VersionAction,
    VersionReason,
    access_policy_fingerprint,
    resolve_canonical_version,
    state_from_candidate,
)
from tropos.core.domain.access import AccessPolicy, AccessScope


def build_candidate(
    text: str = "# Reset\n\nUse the portal.",
    *,
    access_policy: AccessPolicy | None = None,
    strategy_version: str = "canonical-text-v1",
) -> NormalizedKnowledge:
    raw = RawKnowledgeRecord(
        source_system="test-knowledge-base",
        source_record_id="ARTICLE-001",
        source_version="1",
        content_type="text/markdown",
        payload=text.encode("utf-8"),
        access_policy=access_policy
        or AccessPolicy(
            tenant_id="acme",
            scope=AccessScope.TENANT,
        ),
        captured_at=datetime(2026, 9, 21, tzinfo=UTC),
    )
    source = ExtractedKnowledgeText(
        raw_record=raw,
        title="Credential reset",
        text=text,
        text_format=TextFormat.MARKDOWN,
    )
    return DeterministicKnowledgeNormalizer(strategy_version=strategy_version).normalize(source)


def restricted_access() -> AccessPolicy:
    return AccessPolicy(
        tenant_id="acme",
        scope=AccessScope.RESTRICTED,
        allowed_groups=("knowledge-manager",),
    )


def test_first_seen_content_creates_version() -> None:
    decision = resolve_canonical_version(previous=None, candidate=build_candidate())

    assert decision.action is VersionAction.CREATE_VERSION
    assert decision.reason is VersionReason.FIRST_SEEN
    assert decision.requires_governance_refresh is False


def test_formatting_only_change_does_not_create_content_version() -> None:
    first = build_candidate("# Reset\n\nUse the portal.\n\n- Verify login")
    formatting_change = build_candidate(
        "\ufeff# Reset\r\n\r\nUse the portal.   \r\n\r\n* Verify login\r\n"
    )
    previous = state_from_candidate(first)

    decision = resolve_canonical_version(
        previous=previous,
        candidate=formatting_change,
    )

    assert decision.action is VersionAction.NO_CONTENT_VERSION
    assert decision.reason is VersionReason.CONTENT_UNCHANGED
    assert decision.requires_governance_refresh is False


def test_meaningful_change_creates_new_content_version() -> None:
    previous = state_from_candidate(
        build_candidate("# Password policy\n\nPasswords expire after 90 days.")
    )

    decision = resolve_canonical_version(
        previous=previous,
        candidate=build_candidate("# Password policy\n\nPasswords expire after 60 days."),
    )

    assert decision.action is VersionAction.CREATE_VERSION
    assert decision.reason is VersionReason.CONTENT_CHANGED
    assert decision.requires_governance_refresh is False


def test_access_change_refreshes_governance_without_content_version() -> None:
    first = build_candidate()
    previous = state_from_candidate(first)
    restricted = restricted_access()
    candidate = build_candidate(access_policy=restricted)

    decision = resolve_canonical_version(previous=previous, candidate=candidate)

    assert previous.access_fingerprint != access_policy_fingerprint(restricted)
    assert decision.action is VersionAction.REFRESH_GOVERNANCE
    assert decision.reason is VersionReason.ACCESS_CHANGED
    assert decision.requires_governance_refresh is True


def test_content_and_access_change_signal_both_workstreams() -> None:
    previous = state_from_candidate(
        build_candidate("# Password policy\n\nPasswords expire after 90 days.")
    )
    candidate = build_candidate(
        "# Password policy\n\nPasswords expire after 60 days.",
        access_policy=restricted_access(),
    )

    decision = resolve_canonical_version(previous=previous, candidate=candidate)

    assert decision.action is VersionAction.CREATE_VERSION
    assert decision.reason is VersionReason.CONTENT_CHANGED
    assert decision.requires_governance_refresh is True


def test_normalization_strategy_change_requires_rebaseline() -> None:
    first = build_candidate(strategy_version="canonical-text-v1")
    previous = state_from_candidate(first)
    candidate = build_candidate(strategy_version="canonical-text-v2")

    decision = resolve_canonical_version(previous=previous, candidate=candidate)

    assert decision.action is VersionAction.REBASELINE_REQUIRED
    assert decision.reason is VersionReason.NORMALIZATION_STRATEGY_CHANGED
    assert decision.requires_governance_refresh is False


def test_strategy_and_access_change_do_not_hide_governance_refresh() -> None:
    previous = state_from_candidate(build_candidate(strategy_version="canonical-text-v1"))
    candidate = build_candidate(
        strategy_version="canonical-text-v2",
        access_policy=restricted_access(),
    )

    decision = resolve_canonical_version(previous=previous, candidate=candidate)

    assert decision.action is VersionAction.REBASELINE_REQUIRED
    assert decision.reason is VersionReason.NORMALIZATION_STRATEGY_CHANGED
    assert decision.requires_governance_refresh is True


def test_source_version_churn_does_not_participate_in_content_decision() -> None:
    candidate = build_candidate()
    previous = state_from_candidate(candidate)

    changed_source_version = replace(
        candidate,
        source=replace(
            candidate.source,
            raw_record=replace(candidate.source.raw_record, source_version="2"),
        ),
    )

    decision = resolve_canonical_version(
        previous=previous,
        candidate=changed_source_version,
    )

    assert decision.action is VersionAction.NO_CONTENT_VERSION
    assert decision.requires_governance_refresh is False
