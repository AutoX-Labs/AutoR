from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.a2a.executor import AutoRExecutor
from src.operator_base import OperatorBase
from src.utils import OperatorResult, StageSpec


class StubOperator(OperatorBase):
    def __init__(self, model: str = "stub-model", result: OperatorResult | None = None):
        self._model = model
        self._result = result or OperatorResult(
            success=True, exit_code=0, stdout="stub output", stderr="",
            stage_file_path=Path("/tmp/stub.md"), session_id="stub-session-123",
        )

    @property
    def model(self) -> str:
        return self._model

    def run_stage(self, stage, prompt, paths, attempt_no, continue_session=False):
        return self._result

    def repair_stage_summary(self, stage, original_prompt, original_result, paths, attempt_no):
        return self._result


def _make_context(prompt: str = "Test prompt", task_id: str = "t1", context_id: str = "c1"):
    from a2a.server.agent_execution import RequestContext
    from a2a.types import Message, MessageSendParams, Part, Role, TextPart
    return RequestContext(
        request=MessageSendParams(
            message=Message(
                messageId=str(uuid.uuid4()),
                role=Role.user,
                parts=[Part(root=TextPart(text=prompt))],
            ),
        ),
        task_id=task_id,
        context_id=context_id,
    )


class TestAutoRExecutor:
    def test_execute_emits_working_then_artifact_then_completed(self):
        from a2a.types import TaskState, TaskStatusUpdateEvent, TaskArtifactUpdateEvent
        op = StubOperator()
        executor = AutoRExecutor(operator=op)
        queue = MagicMock()
        queue.enqueue_event = AsyncMock()
        context = _make_context("Run literature survey")
        asyncio.run(executor.execute(context, queue))
        assert queue.enqueue_event.call_count == 3
        events = [c.args[0] for c in queue.enqueue_event.call_args_list]
        assert isinstance(events[0], TaskStatusUpdateEvent)
        assert events[0].status.state == TaskState.working
        assert isinstance(events[1], TaskArtifactUpdateEvent)
        assert isinstance(events[2], TaskStatusUpdateEvent)
        assert events[2].status.state == TaskState.completed

    def test_execute_artifact_contains_operator_result_data(self):
        from a2a.types import TaskArtifactUpdateEvent, DataPart
        op = StubOperator()
        executor = AutoRExecutor(operator=op)
        queue = MagicMock()
        queue.enqueue_event = AsyncMock()
        context = _make_context("Run analysis")
        asyncio.run(executor.execute(context, queue))
        events = [c.args[0] for c in queue.enqueue_event.call_args_list]
        artifact_event = [e for e in events if isinstance(e, TaskArtifactUpdateEvent)][0]
        parts = artifact_event.artifact.parts
        assert parts[0].root.text == "stub output"
        data_part = parts[1].root
        assert isinstance(data_part, DataPart)
        assert data_part.data["exit_code"] == 0
        assert data_part.data["session_id"] == "stub-session-123"
        assert data_part.data["success"] is True

    def test_execute_failed_result_emits_failed_state(self):
        from a2a.types import TaskState, TaskStatusUpdateEvent
        failed_result = OperatorResult(
            success=False, exit_code=1, stdout="", stderr="something broke",
            stage_file_path=Path("/tmp/fail.md"),
        )
        op = StubOperator(result=failed_result)
        executor = AutoRExecutor(operator=op)
        queue = MagicMock()
        queue.enqueue_event = AsyncMock()
        context = _make_context("Failing task")
        asyncio.run(executor.execute(context, queue))
        events = [c.args[0] for c in queue.enqueue_event.call_args_list]
        final_event = events[-1]
        assert isinstance(final_event, TaskStatusUpdateEvent)
        assert final_event.status.state == TaskState.failed

    def test_cancel_emits_canceled(self):
        from a2a.types import TaskState, TaskStatusUpdateEvent
        from a2a.server.agent_execution import RequestContext
        op = StubOperator()
        executor = AutoRExecutor(operator=op)
        queue = MagicMock()
        queue.enqueue_event = AsyncMock()
        context = RequestContext(task_id="cancel-1", context_id="ctx-1")
        asyncio.run(executor.cancel(context, queue))
        assert queue.enqueue_event.call_count == 1
        event = queue.enqueue_event.call_args_list[0].args[0]
        assert isinstance(event, TaskStatusUpdateEvent)
        assert event.status.state == TaskState.canceled

    def test_execute_with_empty_message(self):
        from a2a.server.agent_execution import RequestContext
        op = StubOperator()
        executor = AutoRExecutor(operator=op)
        queue = MagicMock()
        queue.enqueue_event = AsyncMock()
        context = RequestContext(task_id="t1", context_id="c1")
        asyncio.run(executor.execute(context, queue))
        assert queue.enqueue_event.call_count == 3
