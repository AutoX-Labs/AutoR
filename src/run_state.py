from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .utils import RunPaths, StageSpec


RUN_STATUS_PENDING = "PENDING"
RUN_STATUS_RUNNING = "RUNNING"
RUN_STATUS_HUMAN_REVIEW = "HUMAN_REVIEW"
RUN_STATUS_COMPLETED = "COMPLETED"
RUN_STATUS_FAILED = "FAILED"
RUN_STATUS_CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class RunState:
    run_id: str
    status: str
    created_at: str
    updated_at: str
    last_event: str
    current_stage_slug: str | None = None
    current_stage_title: str | None = None
    current_pattern: str | None = None
    current_attempt: int | None = None
    human_review_required: bool = True
    waiting_for_human_review: bool = False
    approved_stages: list[dict[str, str]] = field(default_factory=list)
    last_error: str | None = None
    completed_at: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_event": self.last_event,
            "current_stage_slug": self.current_stage_slug,
            "current_stage_title": self.current_stage_title,
            "current_pattern": self.current_pattern,
            "current_attempt": self.current_attempt,
            "human_review_required": self.human_review_required,
            "waiting_for_human_review": self.waiting_for_human_review,
            "approved_stages": list(self.approved_stages),
            "last_error": self.last_error,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "RunState":
        approved_stages = payload.get("approved_stages", [])
        if not isinstance(approved_stages, list):
            approved_stages = []

        return cls(
            run_id=str(payload.get("run_id") or ""),
            status=str(payload.get("status") or RUN_STATUS_PENDING),
            created_at=str(payload.get("created_at") or _now()),
            updated_at=str(payload.get("updated_at") or _now()),
            last_event=str(payload.get("last_event") or "run.created"),
            current_stage_slug=str(payload["current_stage_slug"]) if payload.get("current_stage_slug") is not None else None,
            current_stage_title=str(payload["current_stage_title"]) if payload.get("current_stage_title") is not None else None,
            current_pattern=str(payload["current_pattern"]) if payload.get("current_pattern") is not None else None,
            current_attempt=int(payload["current_attempt"]) if payload.get("current_attempt") is not None else None,
            human_review_required=bool(payload.get("human_review_required", True)),
            waiting_for_human_review=bool(payload.get("waiting_for_human_review", False)),
            approved_stages=[dict(item) for item in approved_stages if isinstance(item, dict)],
            last_error=str(payload["last_error"]) if payload.get("last_error") is not None else None,
            completed_at=str(payload["completed_at"]) if payload.get("completed_at") is not None else None,
        )


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _write_run_state(path: Path, state: RunState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict(), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def load_run_state(path: Path) -> RunState | None:
    if not path.exists():
        return None

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    return RunState.from_dict(json.loads(text))


def initialize_run_state(paths: RunPaths) -> RunState:
    timestamp = _now()
    state = RunState(
        run_id=paths.run_root.name,
        status=RUN_STATUS_PENDING,
        created_at=timestamp,
        updated_at=timestamp,
        last_event="run.created",
    )
    _write_run_state(paths.run_state, state)
    return state


def ensure_run_state(paths: RunPaths) -> RunState:
    state = load_run_state(paths.run_state)
    if state is not None:
        return state
    return initialize_run_state(paths)


def _update_run_state(paths: RunPaths, **changes: object) -> RunState:
    state = ensure_run_state(paths)
    payload = state.to_dict()
    payload.update(changes)
    payload["updated_at"] = _now()
    next_state = RunState.from_dict(payload)
    _write_run_state(paths.run_state, next_state)
    return next_state


def mark_stage_running(paths: RunPaths, stage: StageSpec, attempt_no: int) -> RunState:
    return _update_run_state(
        paths,
        status=RUN_STATUS_RUNNING,
        current_stage_slug=stage.slug,
        current_stage_title=stage.stage_title,
        current_pattern=stage.orchestration_pattern,
        current_attempt=attempt_no,
        waiting_for_human_review=False,
        last_event="stage.started",
        last_error=None,
    )


def mark_stage_human_review(paths: RunPaths, stage: StageSpec, attempt_no: int) -> RunState:
    return _update_run_state(
        paths,
        status=RUN_STATUS_HUMAN_REVIEW,
        current_stage_slug=stage.slug,
        current_stage_title=stage.stage_title,
        current_pattern=stage.orchestration_pattern,
        current_attempt=attempt_no,
        waiting_for_human_review=True,
        last_event="stage.awaiting_human_review",
        last_error=None,
    )


def mark_stage_approved(paths: RunPaths, stage: StageSpec) -> RunState:
    state = ensure_run_state(paths)
    approved_stages = list(state.approved_stages)
    if not any(item.get("slug") == stage.slug for item in approved_stages):
        approved_stages.append(
            {
                "slug": stage.slug,
                "title": stage.stage_title,
                "approved_at": _now(),
            }
        )

    return _update_run_state(
        paths,
        status=RUN_STATUS_PENDING,
        current_stage_slug=None,
        current_stage_title=None,
        current_pattern=None,
        current_attempt=None,
        waiting_for_human_review=False,
        approved_stages=approved_stages,
        last_event="stage.approved",
        last_error=None,
    )


def mark_run_completed(paths: RunPaths) -> RunState:
    completed_at = _now()
    return _update_run_state(
        paths,
        status=RUN_STATUS_COMPLETED,
        current_stage_slug=None,
        current_stage_title=None,
        current_pattern=None,
        current_attempt=None,
        waiting_for_human_review=False,
        completed_at=completed_at,
        last_event="run.completed",
        last_error=None,
    )


def mark_run_cancelled(paths: RunPaths, stage: StageSpec | None = None) -> RunState:
    return _update_run_state(
        paths,
        status=RUN_STATUS_CANCELLED,
        current_stage_slug=stage.slug if stage else None,
        current_stage_title=stage.stage_title if stage else None,
        current_pattern=stage.orchestration_pattern if stage else None,
        waiting_for_human_review=False,
        last_event="run.cancelled",
    )


def mark_run_failed(paths: RunPaths, error: str, stage: StageSpec | None = None) -> RunState:
    return _update_run_state(
        paths,
        status=RUN_STATUS_FAILED,
        current_stage_slug=stage.slug if stage else None,
        current_stage_title=stage.stage_title if stage else None,
        current_pattern=stage.orchestration_pattern if stage else None,
        waiting_for_human_review=False,
        last_event="run.failed",
        last_error=error.strip(),
    )


def format_run_state(state: RunState) -> str:
    lines = [
        f"Run: {state.run_id}",
        f"Status: {state.status}",
        f"Last Event: {state.last_event}",
        f"Updated At: {state.updated_at}",
    ]

    if state.current_stage_title:
        lines.append(f"Current Stage: {state.current_stage_title}")
    if state.current_pattern:
        lines.append(f"Stage Pattern: {state.current_pattern}")
    if state.current_attempt is not None:
        lines.append(f"Current Attempt: {state.current_attempt}")

    lines.append(f"Waiting For Human Review: {state.waiting_for_human_review}")
    lines.append(f"Approved Stages: {len(state.approved_stages)}")

    if state.last_error:
        lines.append(f"Last Error: {state.last_error}")
    if state.completed_at:
        lines.append(f"Completed At: {state.completed_at}")

    return "\n".join(lines)
