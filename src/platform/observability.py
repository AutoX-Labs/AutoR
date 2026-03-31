from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class ObservabilityCollector:
    run_root: Path

    @property
    def observability_dir(self) -> Path:
        return self.run_root / "observability"

    @property
    def spans_path(self) -> Path:
        return self.observability_dir / "spans.jsonl"

    @property
    def metrics_path(self) -> Path:
        return self.observability_dir / "metrics.jsonl"

    def emit_span(self, name: str, **payload: object) -> None:
        self._append(
            self.spans_path,
            {
                "timestamp": _now(),
                "name": name,
                **payload,
            },
        )

    def emit_metric(self, name: str, value: float, **tags: object) -> None:
        self._append(
            self.metrics_path,
            {
                "timestamp": _now(),
                "name": name,
                "value": value,
                "tags": tags,
            },
        )

    def _append(self, path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")

