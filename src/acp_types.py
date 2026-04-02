"""ACP (Agent Communication Protocol) message types.

These dataclasses define the structured messages exchanged between the
ACPOperator (client) and the ACP agent server via JSON-RPC 2.0.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TaskState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# --- Request params ---


@dataclass(frozen=True)
class TaskCreateParams:
    prompt: str
    model: str
    workspace: str
    stage_slug: str
    stage_output_path: str
    timeout_seconds: int | None = None
    tools: list[str] | None = None
    session_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "prompt": self.prompt,
            "model": self.model,
            "workspace": self.workspace,
            "stage_slug": self.stage_slug,
            "stage_output_path": self.stage_output_path,
        }
        if self.timeout_seconds is not None:
            d["timeout_seconds"] = self.timeout_seconds
        if self.tools is not None:
            d["tools"] = self.tools
        if self.session_id is not None:
            d["session_id"] = self.session_id
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TaskCreateParams:
        return cls(
            prompt=d["prompt"],
            model=d["model"],
            workspace=d["workspace"],
            stage_slug=d["stage_slug"],
            stage_output_path=d["stage_output_path"],
            timeout_seconds=d.get("timeout_seconds"),
            tools=d.get("tools"),
            session_id=d.get("session_id"),
        )


@dataclass(frozen=True)
class TaskCancelParams:
    task_id: str
    reason: str = "user_request"

    def to_dict(self) -> dict[str, Any]:
        return {"task_id": self.task_id, "reason": self.reason}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TaskCancelParams:
        return cls(task_id=d["task_id"], reason=d.get("reason", "user_request"))


@dataclass(frozen=True)
class TaskResumeParams:
    task_id: str
    feedback: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"task_id": self.task_id}
        if self.feedback is not None:
            d["feedback"] = self.feedback
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TaskResumeParams:
        return cls(task_id=d["task_id"], feedback=d.get("feedback"))


# --- Response results ---


@dataclass(frozen=True)
class TaskCreateResult:
    task_id: str
    session_id: str

    def to_dict(self) -> dict[str, Any]:
        return {"task_id": self.task_id, "session_id": self.session_id}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TaskCreateResult:
        return cls(task_id=d["task_id"], session_id=d["session_id"])


@dataclass(frozen=True)
class TaskQueryResult:
    task_id: str
    state: TaskState
    tokens_used: int = 0
    stage_output: str | None = None
    session_id: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "task_id": self.task_id,
            "state": self.state.value,
            "tokens_used": self.tokens_used,
        }
        if self.stage_output is not None:
            d["stage_output"] = self.stage_output
        if self.session_id is not None:
            d["session_id"] = self.session_id
        if self.error_message is not None:
            d["error_message"] = self.error_message
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TaskQueryResult:
        return cls(
            task_id=d["task_id"],
            state=TaskState(d["state"]),
            tokens_used=d.get("tokens_used", 0),
            stage_output=d.get("stage_output"),
            session_id=d.get("session_id"),
            error_message=d.get("error_message"),
        )


# --- Streaming events (sent as JSON-RPC notifications) ---


@dataclass(frozen=True)
class ProgressEvent:
    task_id: str
    tokens_used: int
    elapsed_seconds: float
    files_modified: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "tokens_used": self.tokens_used,
            "elapsed_seconds": self.elapsed_seconds,
            "files_modified": self.files_modified,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProgressEvent:
        return cls(
            task_id=d["task_id"],
            tokens_used=d["tokens_used"],
            elapsed_seconds=d["elapsed_seconds"],
            files_modified=d.get("files_modified", []),
        )


@dataclass(frozen=True)
class ToolCallEvent:
    task_id: str
    tool_name: str
    tool_input: dict[str, Any]
    status: str  # "running", "completed", "failed"
    tool_output: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "task_id": self.task_id,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "status": self.status,
        }
        if self.tool_output is not None:
            d["tool_output"] = self.tool_output
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ToolCallEvent:
        return cls(
            task_id=d["task_id"],
            tool_name=d["tool_name"],
            tool_input=d["tool_input"],
            status=d["status"],
            tool_output=d.get("tool_output"),
        )


@dataclass(frozen=True)
class ErrorEvent:
    task_id: str
    code: str
    message: str
    recoverable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "code": self.code,
            "message": self.message,
            "recoverable": self.recoverable,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ErrorEvent:
        return cls(
            task_id=d["task_id"],
            code=d["code"],
            message=d["message"],
            recoverable=d.get("recoverable", False),
        )


@dataclass(frozen=True)
class CompletionEvent:
    task_id: str
    state: TaskState
    tokens_used: int
    session_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "task_id": self.task_id,
            "state": self.state.value,
            "tokens_used": self.tokens_used,
        }
        if self.session_id is not None:
            d["session_id"] = self.session_id
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CompletionEvent:
        return cls(
            task_id=d["task_id"],
            state=TaskState(d["state"]),
            tokens_used=d["tokens_used"],
            session_id=d.get("session_id"),
        )
