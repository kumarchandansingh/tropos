import json
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256

from tropos.core.application.ingestion.normalization import NormalizedKnowledge
from tropos.core.domain.access import AccessPolicy

_HEXADECIMAL_CHARACTERS = frozenset("0123456789abcdefABCDEF")


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in _HEXADECIMAL_CHARACTERS for character in value)


def access_policy_fingerprint(policy: AccessPolicy) -> str:
    """Fingerprint retrieval-governance state independently from content identity."""

    payload = {
        "allowed_groups": policy.allowed_groups,
        "scope": policy.scope.value,
        "tenant_id": policy.tenant_id,
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


class VersionAction(StrEnum):
    """Action required after comparing a normalized candidate with current state."""

    CREATE_VERSION = "CREATE_VERSION"
    NO_CONTENT_VERSION = "NO_CONTENT_VERSION"
    REFRESH_GOVERNANCE = "REFRESH_GOVERNANCE"
    REBASELINE_REQUIRED = "REBASELINE_REQUIRED"


class VersionReason(StrEnum):
    """Stable explanation for a canonical-version decision."""

    FIRST_SEEN = "FIRST_SEEN"
    CONTENT_CHANGED = "CONTENT_CHANGED"
    CONTENT_UNCHANGED = "CONTENT_UNCHANGED"
    ACCESS_CHANGED = "ACCESS_CHANGED"
    NORMALIZATION_STRATEGY_CHANGED = "NORMALIZATION_STRATEGY_CHANGED"


@dataclass(frozen=True, slots=True)
class CanonicalKnowledgeState:
    """Persisted comparison state for the current canonical knowledge version."""

    content_fingerprint: str
    normalization_strategy_version: str
    access_fingerprint: str

    def __post_init__(self) -> None:
        if not _is_sha256(self.content_fingerprint):
            raise ValueError("content_fingerprint must be a SHA-256 digest")
        if not self.normalization_strategy_version.strip():
            raise ValueError("normalization_strategy_version must not be blank")
        if not _is_sha256(self.access_fingerprint):
            raise ValueError("access_fingerprint must be a SHA-256 digest")


@dataclass(frozen=True, slots=True)
class VersionDecision:
    """Auditable result of comparing a candidate with the current canonical state."""

    action: VersionAction
    reason: VersionReason


def state_from_candidate(normalized: NormalizedKnowledge) -> CanonicalKnowledgeState:
    """Build comparison state from one normalized candidate."""

    return CanonicalKnowledgeState(
        content_fingerprint=normalized.content_fingerprint,
        normalization_strategy_version=normalized.strategy_version,
        access_fingerprint=access_policy_fingerprint(normalized.source.raw_record.access_policy),
    )


def resolve_canonical_version(
    *,
    previous: CanonicalKnowledgeState | None,
    candidate: NormalizedKnowledge,
) -> VersionDecision:
    """Choose content-version or governance action without trusting source-version churn."""

    if previous is None:
        return VersionDecision(
            action=VersionAction.CREATE_VERSION,
            reason=VersionReason.FIRST_SEEN,
        )

    if previous.normalization_strategy_version != candidate.strategy_version:
        return VersionDecision(
            action=VersionAction.REBASELINE_REQUIRED,
            reason=VersionReason.NORMALIZATION_STRATEGY_CHANGED,
        )

    if previous.content_fingerprint != candidate.content_fingerprint:
        return VersionDecision(
            action=VersionAction.CREATE_VERSION,
            reason=VersionReason.CONTENT_CHANGED,
        )

    candidate_access = access_policy_fingerprint(candidate.source.raw_record.access_policy)
    if previous.access_fingerprint != candidate_access:
        return VersionDecision(
            action=VersionAction.REFRESH_GOVERNANCE,
            reason=VersionReason.ACCESS_CHANGED,
        )

    return VersionDecision(
        action=VersionAction.NO_CONTENT_VERSION,
        reason=VersionReason.CONTENT_UNCHANGED,
    )
