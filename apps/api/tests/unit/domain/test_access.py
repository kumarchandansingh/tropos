import pytest

from tropos.domain.access import AccessPolicy, AccessScope


def test_tenant_access_is_indexable() -> None:
    policy = AccessPolicy(
        tenant_id="acme",
        scope=AccessScope.TENANT,
    )

    assert policy.is_indexable is True
    assert policy.allowed_groups == ()


def test_unresolved_access_is_not_indexable() -> None:
    policy = AccessPolicy(
        tenant_id="acme",
        scope=AccessScope.UNRESOLVED,
    )

    assert policy.is_indexable is False


def test_restricted_access_requires_groups() -> None:
    with pytest.raises(
        ValueError,
        match="requires at least one group",
    ):
        AccessPolicy(
            tenant_id="acme",
            scope=AccessScope.RESTRICTED,
        )


def test_non_restricted_access_rejects_groups() -> None:
    with pytest.raises(
        ValueError,
        match="only for restricted access",
    ):
        AccessPolicy(
            tenant_id="acme",
            scope=AccessScope.TENANT,
            allowed_groups=("support-agent",),
        )


def test_groups_are_canonicalized() -> None:
    policy = AccessPolicy(
        tenant_id=" acme ",
        scope=AccessScope.RESTRICTED,
        allowed_groups=(" tier-two ", "tier-one"),
    )

    assert policy.tenant_id == "acme"
    assert policy.allowed_groups == ("tier-one", "tier-two")


def test_duplicate_groups_are_rejected_after_normalization() -> None:
    with pytest.raises(
        ValueError,
        match="must not contain duplicates",
    ):
        AccessPolicy(
            tenant_id="acme",
            scope=AccessScope.RESTRICTED,
            allowed_groups=("tier-one", " tier-one "),
        )


def test_blank_tenant_is_rejected() -> None:
    with pytest.raises(ValueError, match="tenant_id must not be blank"):
        AccessPolicy(
            tenant_id=" ",
            scope=AccessScope.TENANT,
        )
