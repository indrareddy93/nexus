"""Role-Based Access Control (RBAC) — roles, permissions, and route guards."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from nexus.core.request import Request
from nexus.core.response import ErrorResponse
from nexus.di.dependencies import Depends


@dataclass(frozen=True)
class Permission:
    """A single named permission (e.g. ``articles:write``)."""
    name: str

    def __str__(self) -> str:
        return self.name


@dataclass
class Role:
    """
    A named role that grants a set of permissions.

    Usage::

        admin = Role("admin", permissions={"users:read", "users:write", "articles:*"})
        editor = Role("editor", permissions={"articles:read", "articles:write"})
    """
    name: str
    permissions: set[str] = field(default_factory=set)
    inherits: list[str] = field(default_factory=list)  # role names this role inherits from

    def can(self, permission: str) -> bool:
        """Check if this role grants *permission* (supports wildcard ``resource:*``)."""
        if permission in self.permissions:
            return True
        # Wildcard check: "articles:*" matches "articles:read", "articles:write", etc.
        resource = permission.split(":")[0]
        return f"{resource}:*" in self.permissions or "*" in self.permissions


class RBACPolicy:
    """
    Policy store — manages roles and permission checks.

    Usage::

        policy = RBACPolicy()
        policy.define_role("admin", permissions={"*"})
        policy.define_role("editor", permissions={"articles:read", "articles:write"})
        policy.define_role("viewer", permissions={"articles:read", "users:read"})

        assert policy.has_permission("admin", "anything")
        assert policy.has_permission("editor", "articles:write")
        assert not policy.has_permission("viewer", "articles:write")
    """

    def __init__(self) -> None:
        self._roles: dict[str, Role] = {}

    def define_role(
        self,
        name: str,
        *,
        permissions: set[str] | None = None,
        inherits: list[str] | None = None,
    ) -> Role:
        role = Role(name=name, permissions=permissions or set(), inherits=inherits or [])
        self._roles[name] = role
        return role

    def get_role(self, name: str) -> Role | None:
        return self._roles.get(name)

    def has_permission(self, role_name: str, permission: str) -> bool:
        role = self._roles.get(role_name)
        if role is None:
            return False
        if role.can(permission):
            return True
        # Check inherited roles
        for parent_name in role.inherits:
            if self.has_permission(parent_name, permission):
                return True
        return False

    def all_permissions(self, role_name: str) -> set[str]:
        role = self._roles.get(role_name)
        if role is None:
            return set()
        perms = set(role.permissions)
        for parent_name in role.inherits:
            perms |= self.all_permissions(parent_name)
        return perms


# ------------------------------------------------------------------
# Dependency-injection guards
# ------------------------------------------------------------------

def requires_role(*allowed_roles: str, claims_key: str = "role") -> Callable:
    """
    DI dependency factory: requires that the JWT claim ``role`` is in *allowed_roles*.

    Usage::

        @app.delete("/users/{id}")
        async def delete_user(id: int, _=requires_role("admin")):
            ...
    """
    async def _check(request: Request) -> dict[str, Any]:
        claims: dict = getattr(request, "state", {}).get("claims", {})
        role = claims.get(claims_key, "")
        if role not in allowed_roles:
            raise PermissionError(
                f"Role {role!r} is not authorised. Requires one of: {allowed_roles}"
            )
        return claims

    return Depends(_check)


def requires_permission(
    permission: str,
    *,
    policy: RBACPolicy,
    claims_key: str = "role",
) -> Callable:
    """
    DI dependency factory: checks that the user's role has *permission*.

    Usage::

        rbac = RBACPolicy()
        rbac.define_role("editor", permissions={"articles:write"})

        @app.post("/articles")
        async def create_article(body=Body(), _=requires_permission("articles:write", policy=rbac)):
            ...
    """
    async def _check(request: Request) -> dict[str, Any]:
        claims: dict = getattr(request, "state", {}).get("claims", {})
        role = claims.get(claims_key, "")
        if not policy.has_permission(role, permission):
            raise PermissionError(
                f"Role {role!r} does not have permission {permission!r}"
            )
        return claims

    return Depends(_check)
