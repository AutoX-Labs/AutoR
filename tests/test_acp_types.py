from __future__ import annotations

import pytest

from src.acp_types import (
    CompletionEvent,
    ErrorEvent,
    ProgressEvent,
    TaskCancelParams,
    TaskCreateParams,
    TaskCreateResult,
    TaskQueryResult,
    TaskResumeParams,
    TaskState,
    ToolCallEvent,
)


class TestTaskState:
    def test_valid_states(self):
        assert TaskState.PENDING == "pending"
        assert TaskState.RUNNING == "running"
        assert TaskState.COMPLETED == "completed"
        assert TaskState.FAILED == "failed"
        assert TaskState.CANCELLED == "cancelled"


class TestTaskCreateParams:
    def test_to_dict_required_fields(self):
        params = TaskCreateParams(
            prompt="do research",
            model="sonnet",
            workspace="/tmp/workspace",
            stage_slug="05_experimentation",
            stage_output_path="/tmp/stages/05.tmp.md",
        )
        d = params.to_dict()
        assert d["prompt"] == "do research"
        assert d["model"] == "sonnet"
        assert d["workspace"] == "/tmp/workspace"
        assert d["stage_slug"] == "05_experimentation"
        assert d["stage_output_path"] == "/tmp/stages/05.tmp.md"
        assert "timeout_seconds" not in d
        assert "tools" not in d
        assert "session_id" not in d

    def test_to_dict_with_optional_fields(self):
        params = TaskCreateParams(
            prompt="do research",
            model="sonnet",
            workspace="/tmp/workspace",
            stage_slug="05_experimentation",
            stage_output_path="/tmp/stages/05.tmp.md",
            timeout_seconds=1800,
            tools=["Read", "Write", "Bash"],
            session_id="sess-123",
        )
        d = params.to_dict()
        assert d["timeout_seconds"] == 1800
        assert d["tools"] == ["Read", "Write", "Bash"]
        assert d["session_id"] == "sess-123"

    def test_from_dict_required_only(self):
        d = {
            "prompt": "hello",
            "model": "opus",
            "workspace": "/w",
            "stage_slug": "01_literature_survey",
            "stage_output_path": "/s/01.tmp.md",
        }
        params = TaskCreateParams.from_dict(d)
        assert params.prompt == "hello"
        assert params.model == "opus"
        assert params.timeout_seconds is None
        assert params.tools is None
        assert params.session_id is None

    def test_from_dict_missing_required_raises(self):
        with pytest.raises(KeyError):
            TaskCreateParams.from_dict({"prompt": "hello"})

    def test_roundtrip(self):
        original = TaskCreateParams(
            prompt="test",
            model="sonnet",
            workspace="/w",
            stage_slug="02_hypothesis_generation",
            stage_output_path="/s/02.tmp.md",
            timeout_seconds=600,
            tools=["Read"],
        )
        restored = TaskCreateParams.from_dict(original.to_dict())
        assert restored == original


class TestTaskCancelParams:
    def test_to_dict(self):
        params = TaskCancelParams(task_id="t1", reason="timeout")
        d = params.to_dict()
        assert d == {"task_id": "t1", "reason": "timeout"}

    def test_from_dict_default_reason(self):
        params = TaskCancelParams.from_dict({"task_id": "t1"})
        assert params.reason == "user_request"


class TestTaskResumeParams:
    def test_to_dict_without_feedback(self):
        params = TaskResumeParams(task_id="t1")
        d = params.to_dict()
        assert d == {"task_id": "t1"}
        assert "feedback" not in d

    def test_to_dict_with_feedback(self):
        params = TaskResumeParams(task_id="t1", feedback="try harder")
        d = params.to_dict()
        assert d["feedback"] == "try harder"


class TestTaskCreateResult:
    def test_roundtrip(self):
        original = TaskCreateResult(task_id="t1", session_id="s1")
        restored = TaskCreateResult.from_dict(original.to_dict())
        assert restored == original


class TestTaskQueryResult:
    def test_from_dict_running(self):
        d = {"task_id": "t1", "state": "running", "tokens_used": 5000}
        r = TaskQueryResult.from_dict(d)
        assert r.task_id == "t1"
        assert r.state == TaskState.RUNNING
        assert r.tokens_used == 5000
        assert r.stage_output is None

    def test_from_dict_completed(self):
        d = {
            "task_id": "t1",
            "state": "completed",
            "tokens_used": 25000,
            "stage_output": "# Stage 05\n...",
            "session_id": "sess-abc",
        }
        r = TaskQueryResult.from_dict(d)
        assert r.state == TaskState.COMPLETED
        assert r.stage_output is not None
        assert r.session_id == "sess-abc"

    def test_roundtrip(self):
        original = TaskQueryResult(
            task_id="t1",
            state=TaskState.FAILED,
            tokens_used=100,
            error_message="boom",
        )
        restored = TaskQueryResult.from_dict(original.to_dict())
        assert restored == original


class TestProgressEvent:
    def test_to_dict(self):
        e = ProgressEvent(task_id="t1", tokens_used=1200, elapsed_seconds=45.0)
        d = e.to_dict()
        assert d["task_id"] == "t1"
        assert d["tokens_used"] == 1200
        assert d["elapsed_seconds"] == 45.0
        assert d["files_modified"] == []

    def test_from_dict(self):
        d = {"task_id": "t1", "tokens_used": 500, "elapsed_seconds": 10.0}
        e = ProgressEvent.from_dict(d)
        assert e.tokens_used == 500
        assert e.files_modified == []

    def test_roundtrip_with_files(self):
        original = ProgressEvent(
            task_id="t1",
            tokens_used=3000,
            elapsed_seconds=120.0,
            files_modified=["code/model.py", "data/config.json"],
        )
        restored = ProgressEvent.from_dict(original.to_dict())
        assert restored == original


class TestToolCallEvent:
    def test_to_dict(self):
        e = ToolCallEvent(
            task_id="t1",
            tool_name="Bash",
            tool_input={"command": "python train.py"},
            status="running",
        )
        d = e.to_dict()
        assert d["tool_name"] == "Bash"
        assert d["status"] == "running"
        assert "tool_output" not in d

    def test_to_dict_with_output(self):
        e = ToolCallEvent(
            task_id="t1",
            tool_name="Read",
            tool_input={"file_path": "/tmp/f.py"},
            status="completed",
            tool_output="file contents",
        )
        d = e.to_dict()
        assert d["tool_output"] == "file contents"


class TestErrorEvent:
    def test_to_dict(self):
        e = ErrorEvent(
            task_id="t1",
            code="SESSION_NOT_FOUND",
            message="No session",
            recoverable=True,
        )
        d = e.to_dict()
        assert d["recoverable"] is True

    def test_from_dict_default_recoverable(self):
        d = {"task_id": "t1", "code": "TIMEOUT", "message": "timed out"}
        e = ErrorEvent.from_dict(d)
        assert e.recoverable is False


class TestCompletionEvent:
    def test_to_dict(self):
        e = CompletionEvent(
            task_id="t1",
            state=TaskState.COMPLETED,
            tokens_used=30000,
            session_id="sess-123",
        )
        d = e.to_dict()
        assert d["state"] == "completed"
        assert d["session_id"] == "sess-123"

    def test_roundtrip(self):
        original = CompletionEvent(
            task_id="t1",
            state=TaskState.FAILED,
            tokens_used=500,
        )
        restored = CompletionEvent.from_dict(original.to_dict())
        assert restored == original
