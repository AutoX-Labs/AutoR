"""A2A executor that delegates to an OperatorBase implementation."""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    Artifact,
    DataPart,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)

from ..operator_base import OperatorBase
from ..utils import STAGES, build_run_paths, ensure_run_layout


class AutoRExecutor(AgentExecutor):
    """Bridges OperatorBase to the A2A protocol."""

    def __init__(self, operator: OperatorBase) -> None:
        self._operator = operator

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        task_id = context.task_id or str(uuid.uuid4())
        context_id = context.context_id or str(uuid.uuid4())
        prompt = self._extract_prompt(context)

        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                taskId=task_id,
                contextId=context_id,
                final=False,
                status=TaskStatus(
                    state=TaskState.working,
                    message=Message(
                        messageId=str(uuid.uuid4()),
                        role=Role.agent,
                        parts=[Part(root=TextPart(text="Processing..."))],
                    ),
                ),
            )
        )

        stage = STAGES[0]
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = build_run_paths(Path(tmp_dir) / "run")
            ensure_run_layout(paths)
            result = self._operator.run_stage(
                stage=stage, prompt=prompt, paths=paths, attempt_no=1,
            )

        await event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                taskId=task_id,
                contextId=context_id,
                artifact=Artifact(
                    artifactId=str(uuid.uuid4()),
                    parts=[
                        Part(root=TextPart(text=result.stdout or "")),
                        Part(root=DataPart(data={
                            "success": result.success,
                            "exit_code": result.exit_code,
                            "session_id": result.session_id,
                            "stage_file_path": str(result.stage_file_path),
                            "operator": type(self._operator).__name__,
                            "model": self._operator.model,
                        })),
                    ],
                    name="operator-result",
                ),
            )
        )

        final_state = TaskState.completed if result.success else TaskState.failed
        status_text = f"Task {final_state}" + (
            f": {result.stderr}" if result.stderr and not result.success else ""
        )
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                taskId=task_id,
                contextId=context_id,
                final=True,
                status=TaskStatus(
                    state=final_state,
                    message=Message(
                        messageId=str(uuid.uuid4()),
                        role=Role.agent,
                        parts=[Part(root=TextPart(text=status_text))],
                    ),
                ),
            )
        )

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                taskId=context.task_id or "",
                contextId=context.context_id or "",
                final=True,
                status=TaskStatus(state=TaskState.canceled),
            )
        )

    def _extract_prompt(self, context: RequestContext) -> str:
        if context.message:
            for part in context.message.parts:
                inner = part.root
                if hasattr(inner, "text"):
                    return inner.text
        return ""
