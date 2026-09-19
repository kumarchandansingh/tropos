from dataclasses import dataclass
from enum import StrEnum


class AccessScope(StrEnum):
    """How knowledge may be accessed within a tenant."""

    UNRESOLVED = "unresolved"
    TENANT = "tenant"
    RESTRICTED = "restricted"


@dataclass(frozen=True, slots=True)
class AccessPolicy:
    """Canonical access policy carried by documents and child chunks."""

    tenant_id: str
    scope: AccessScope
    allowed_groups: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        tenant_id = self.tenant_id.strip()
        if not tenant_id:
            raise ValueError("tenant_id must not be blank")

        if not isinstance(self.scope, AccessScope):
            raise TypeError("scope must be an AccessScope")

        groups = tuple(group.strip() for group in self.allowed_groups)

        if any(not group for group in groups):
            raise ValueError("allowed_groups must not contain blank values")

        if len(groups) != len(set(groups)):
            raise ValueError("allowed_groups must not contain duplicates")

        if self.scope is AccessScope.RESTRICTED and not groups:
            raise ValueError("restricted access requires at least one group")

        if self.scope is not AccessScope.RESTRICTED and groups:
            raise ValueError("allowed_groups are valid only for restricted access")

        object.__setattr__(self, "tenant_id", tenant_id)
        object.__setattr__(self, "allowed_groups", tuple(sorted(groups)))

    @property
    def is_indexable(self) -> bool:
        """Return whether content may enter a searchable index."""

        return self.scope is not AccessScope.UNRESOLVED
