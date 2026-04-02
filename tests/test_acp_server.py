from __future__ import annotations

import pytest

from src.acp_server import ACPServer
from src.acp_types import (
    CompletionEvent,
    ErrorEvent,
    TaskCancelParams,
    TaskCreateParams,
    TaskCreateResult,
    TaskQueryResult,
    TaskResumeParams,
    TaskState,
)
from src.jsonrpc import ErrorCode, JsonRpcException


def _make_params(**overrides) -> TaskCreateParams:
    defaults = {
        "prompt": "test prompt",
        "model": "sonnet",
        "workspace": "/tmp/w",
        "stage_slug": "01_literature_survey",
        "stage_output_path": "/tmp/s/01.tmp.md",
    }
    defaults.update(overrides)
    return TaskCreateParams(**defaults)


class TestACPServerCreateTask:
    def test_create_returns_task_and_session_id(self):
        server = ACPServer(api_key="test-key")
        result = server.handle_request("acp.task.create", _make_params())
        assert isinstance(result, TaskCreateResult)
        assert result.task_id
        assert result.session_id

    def test_create_preserves_session_id_if_provided(self):
        server = ACPServer(api_key="test-key")
        params = _make_params(session_id="my-session")
        result = server.handle_request("acp.task.create", params)
        assert result.session_id == "my-session"

    def test_create_generates_session_id_if_not_provided(self):
        server = ACPServer(api_key="test-key")
        params = _make_params()
        result = server.handle_request("acp.task.create", params)
        assert result.session_id  # non-empty

    def test_multiple_creates_get_different_task_ids(self):
        server = ACPServer(api_key="test-key")
        r1 = server.handle_request("acp.task.create", _make_params())
        r2 = server.handle_request("acp.task.create", _make_params())
        assert r1.task_id != r2.task_id


class TestACPServerQueryTask:
    def test_query_pending_task(self):
        server = ACPServer(api_key="test-key")
        create_result = server.handle_request("acp.task.create", _make_params())
        query_result = server.handle_request("acp.task.query", create_result.task_id)
        assert isinstance(query_result, TaskQueryResult)
        assert query_result.state == TaskState.PENDING

    def test_query_nonexistent_task_raises_with_error_code(self):
        server = ACPServer(api_key="test-key")
        with pytest.raises(JsonRpcException) as exc_info:
            server.handle_request("acp.task.query", "nonexistent")
        assert exc_info.value.code == ErrorCode.SESSION_NOT_FOUND

    def test_query_after_stream_shows_completed(self):
        server = ACPServer(api_key="test-key")
        create_result = server.handle_request("acp.task.create", _make_params())
        # Consume stream to execute
        list(server.stream_events(create_result.task_id))
        query_result = server.handle_request("acp.task.query", create_result.task_id)
        assert query_result.state == TaskState.COMPLETED


class TestACPServerCancelTask:
    def test_cancel_task(self):
        server = ACPServer(api_key="test-key")
        create_result = server.handle_request("acp.task.create", _make_params())
        cancel_params = TaskCancelParams(task_id=create_result.task_id)
        server.handle_request("acp.task.cancel", cancel_params)
        query_result = server.handle_request("acp.task.query", create_result.task_id)
        assert query_result.state == TaskState.CANCELLED

    def test_cancel_nonexistent_raises_with_error_code(self):
        server = ACPServer(api_key="test-key")
        with pytest.raises(JsonRpcException) as exc_info:
            server.handle_request("acp.task.cancel", TaskCancelParams(task_id="nope"))
        assert exc_info.value.code == ErrorCode.SESSION_NOT_FOUND

    def test_cancelled_task_stream_is_empty(self):
        server = ACPServer(api_key="test-key")
        create_result = server.handle_request("acp.task.create", _make_params())
        server.handle_request("acp.task.cancel", TaskCancelParams(task_id=create_result.task_id))
        events = list(server.stream_events(create_result.task_id))
        assert events == []


class TestACPServerResumeTask:
    def test_resume_resets_to_pending(self):
        server = ACPServer(api_key="test-key")
        create_result = server.handle_request("acp.task.create", _make_params())
        # Execute to completed
        list(server.stream_events(create_result.task_id))
        # Resume
        resume_params = TaskResumeParams(task_id=create_result.task_id)
        resume_result = server.handle_request("acp.task.resume", resume_params)
        assert resume_result.task_id == create_result.task_id
        query_result = server.handle_request("acp.task.query", create_result.task_id)
        assert query_result.state == TaskState.PENDING

    def test_resume_nonexistent_raises_with_error_code(self):
        server = ACPServer(api_key="test-key")
        with pytest.raises(JsonRpcException) as exc_info:
            server.handle_request("acp.task.resume", TaskResumeParams(task_id="nope"))
        assert exc_info.value.code == ErrorCode.SESSION_NOT_FOUND


class TestACPServerStreamEvents:
    def test_stream_yields_completion_event(self):
        server = ACPServer(api_key="test-key")
        create_result = server.handle_request("acp.task.create", _make_params())
        events = list(server.stream_events(create_result.task_id))
        assert len(events) == 1
        assert isinstance(events[0], CompletionEvent)
        assert events[0].state == TaskState.COMPLETED

    def test_stream_nonexistent_raises_with_error_code(self):
        server = ACPServer(api_key="test-key")
        with pytest.raises(JsonRpcException) as exc_info:
            list(server.stream_events("nonexistent"))
        assert exc_info.value.code == ErrorCode.SESSION_NOT_FOUND

    def test_stream_transitions_through_running(self):
        server = ACPServer(api_key="test-key")
        create_result = server.handle_request("acp.task.create", _make_params())
        # Before stream: pending
        assert server.handle_request("acp.task.query", create_result.task_id).state == TaskState.PENDING
        # During/after stream: completed
        list(server.stream_events(create_result.task_id))
        assert server.handle_request("acp.task.query", create_result.task_id).state == TaskState.COMPLETED


class TestACPServerUnknownMethod:
    def test_unknown_method_raises_with_error_code(self):
        server = ACPServer(api_key="test-key")
        with pytest.raises(JsonRpcException) as exc_info:
            server.handle_request("acp.unknown", {})
        assert exc_info.value.code == ErrorCode.METHOD_NOT_FOUND
        assert "Unknown method" in str(exc_info.value)
