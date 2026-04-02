"""ACP Agent Server wrapping the Anthropic Python SDK.

Receives structured JSON-RPC requests, translates them to Claude API calls,
and emits typed events. Runs in-process (no network needed).
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from .acp_types import (
    CompletionEvent,
    ErrorEvent,
    TaskCancelParams,
    TaskCreateParams,
    TaskCreateResult,
    TaskQueryResult,
    TaskResumeParams,
    TaskState,
)
from .jsonrpc import ErrorCode, JsonRpcException


@dataclass
class _TaskRecord:
    task_id: str
    session_id: str
    params: TaskCreateParams
    state: TaskState = TaskState.PENDING
    tokens_used: int = 0
    error_message: str | None = None


class ACPServer:
    """In-process ACP server. Manages task lifecycle and delegates to Claude API."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key
        self._tasks: dict[str, _TaskRecord] = {}

    def handle_request(self, method: str, params: Any) -> Any:
        if method == "acp.task.create":
            return self._create_task(params)
        if method == "acp.task.query":
            return self._query_task(params)
        if method == "acp.task.cancel":
            return self._cancel_task(params)
        if method == "acp.task.resume":
            return self._resume_task(params)
        raise JsonRpcException(
            ErrorCode.METHOD_NOT_FOUND,
            f"Unknown method: {method}",
        )

    def stream_events(self, task_id: str) -> Iterator[Any]:
        record = self._tasks.get(task_id)
        if record is None:
            raise JsonRpcException(
                ErrorCode.SESSION_NOT_FOUND,
                f"Task not found: {task_id}",
            )

        if record.state == TaskState.CANCELLED:
            return

        # Execute the task (call Claude API)
        record.state = TaskState.RUNNING
        try:
            yield from self._execute_task(record)
        except Exception as exc:
            record.state = TaskState.FAILED
            record.error_message = str(exc)
            yield ErrorEvent(
                task_id=task_id,
                code="EXECUTION_ERROR",
                message=str(exc),
                recoverable=False,
            )

    def _create_task(self, params: TaskCreateParams) -> TaskCreateResult:
        task_id = str(uuid.uuid4())
        session_id = params.session_id or str(uuid.uuid4())
        record = _TaskRecord(
            task_id=task_id,
            session_id=session_id,
            params=params,
        )
        self._tasks[task_id] = record
        return TaskCreateResult(task_id=task_id, session_id=session_id)

    def _query_task(self, task_id: str) -> TaskQueryResult:
        record = self._tasks.get(task_id)
        if record is None:
            raise JsonRpcException(
                ErrorCode.SESSION_NOT_FOUND,
                f"Task not found: {task_id}",
            )
        return TaskQueryResult(
            task_id=record.task_id,
            state=record.state,
            tokens_used=record.tokens_used,
            session_id=record.session_id,
            error_message=record.error_message,
        )

    def _cancel_task(self, params: TaskCancelParams) -> None:
        record = self._tasks.get(params.task_id)
        if record is None:
            raise JsonRpcException(
                ErrorCode.SESSION_NOT_FOUND,
                f"Task not found: {params.task_id}",
            )
        record.state = TaskState.CANCELLED

    def _resume_task(self, params: TaskResumeParams) -> TaskCreateResult:
        record = self._tasks.get(params.task_id)
        if record is None:
            raise JsonRpcException(
                ErrorCode.SESSION_NOT_FOUND,
                f"Task not found: {params.task_id}",
            )
        record.state = TaskState.PENDING
        return TaskCreateResult(task_id=record.task_id, session_id=record.session_id)

    def _execute_task(self, record: _TaskRecord) -> Iterator[Any]:
        """Execute a task by calling the Claude API.

        This is the integration point with the Anthropic SDK.
        Currently a stub that completes immediately.

        The real implementation (future PR) will:
        1. Call anthropic.messages.create() with streaming
        2. Parse tool_use blocks and execute tools locally
        3. Yield ProgressEvent, ToolCallEvent as they happen
        4. Write stage output file when Claude produces it
        5. Yield CompletionEvent when done
        """
        record.state = TaskState.COMPLETED
        yield CompletionEvent(
            task_id=record.task_id,
            state=TaskState.COMPLETED,
            tokens_used=record.tokens_used,
            session_id=record.session_id,
        )
