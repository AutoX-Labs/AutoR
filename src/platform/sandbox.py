from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Callable, TypeVar


T = TypeVar("T")


class SandboxLevel(str, Enum):
    NONE = "none"
    BASIC = "basic"
    STRICT = "strict"


@dataclass(frozen=True)
class ExecutionPolicy:
    level: SandboxLevel = SandboxLevel.NONE
    cwd: str | None = None


class SandboxRunner:
    def __init__(self, policy: ExecutionPolicy | None = None) -> None:
        self.policy = policy or ExecutionPolicy()

    def run_callable(self, fn: Callable[[], T]) -> T:
        return fn()

    def run_subprocess(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=self.policy.cwd,
            capture_output=True,
            text=True,
            check=False,
        )

