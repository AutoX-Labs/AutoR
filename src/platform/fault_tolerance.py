from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 4
    delays_s: tuple[float, ...] = (1.0, 2.0, 4.0, 8.0)

    def run(self, fn: Callable[[], T]) -> T:
        last_error: Exception | None = None
        for index in range(self.attempts):
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if index < len(self.delays_s):
                    time.sleep(self.delays_s[index])
        assert last_error is not None
        raise last_error


@dataclass(frozen=True)
class FallbackChain:
    providers: tuple[str, ...]

    def next_after(self, provider: str) -> str | None:
        try:
            index = self.providers.index(provider)
        except ValueError:
            return self.providers[0] if self.providers else None
        if index + 1 >= len(self.providers):
            return None
        return self.providers[index + 1]


class ErrorClassifier:
    def classify(self, error_text: str) -> str:
        lowered = error_text.lower()
        if any(token in lowered for token in ("429", "timeout", "temporarily", "connection reset")):
            return "transient"
        if any(token in lowered for token in ("permission", "auth", "forbidden")):
            return "human_required"
        return "non_recoverable"


@dataclass(frozen=True)
class CheckpointManager:
    checkpoint_path: Path

    def save(self, payload: dict[str, object]) -> None:
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    def load(self) -> dict[str, object] | None:
        if not self.checkpoint_path.exists():
            return None
        return json.loads(self.checkpoint_path.read_text(encoding="utf-8"))

