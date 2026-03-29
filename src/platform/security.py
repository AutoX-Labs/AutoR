from __future__ import annotations

from dataclasses import dataclass


ROLE_SCOPES: dict[str, set[str]] = {
    "admin": {"*"},
    "researcher": {
        "task.create",
        "task.read",
        "task.approve",
        "kb.read",
        "kb.write",
        "foundry.create",
        "usage.read",
        "system.read",
    },
    "reviewer": {
        "task.read",
        "task.approve",
        "kb.read",
        "system.read",
    },
    "node": {
        "node.invoke",
        "node.read",
        "system.read",
    },
    "orchestrator": {
        "task.create",
        "task.read",
        "task.approve",
        "kb.read",
        "kb.write",
        "agent.read",
        "node.invoke",
        "foundry.create",
        "system.read",
    },
}


@dataclass(frozen=True)
class AccessContext:
    role: str = "researcher"


def authorize_scope(role: str, scope: str) -> None:
    granted = ROLE_SCOPES.get(role)
    if granted is None:
        raise PermissionError(f"Unknown role: {role}")
    if "*" in granted or scope in granted:
        return
    raise PermissionError(f"Role '{role}' is not allowed to use scope '{scope}'.")

