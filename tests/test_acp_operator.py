from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from src.acp_operator import ACPOperator
from src.acp_types import (
    CompletionEvent,
    TaskCreateResult,
    TaskQueryResult,
    TaskState,
)
from src.operator_protocol import OperatorProtocol
from src.utils import STAGES, build_run_paths, ensure_run_layout, write_text


def _make_run(tmp_path: Path) -> Path:
    """Create a minimal run directory for testing."""
    run_root = tmp_path / "test_run"
    paths = build_run_paths(run_root)
    ensure_run_layout(paths)
    write_text(paths.user_input, "test goal")
    write_text(
        paths.memory,
        "# Approved Run Memory\n\n## Original User Goal\ntest\n\n## Approved Stage Summaries\n\n_None yet._\n",
    )
    return run_root


class TestACPOperatorSatisfiesProtocol:
    def test_is_operator_protocol(self):
        op = ACPOperator(model="sonnet", server_factory=lambda: MagicMock())
        assert isinstance(op, OperatorProtocol)


class TestACPOperatorRunStage:
    def test_run_stage_success(self, tmp_path):
        run_root = _make_run(tmp_path)
        paths = build_run_paths(run_root)
        stage = STAGES[0]  # 01_literature_survey

        # Mock server
        mock_server = MagicMock()
        mock_server.handle_request.side_effect = [
            # task.create response
            TaskCreateResult(task_id="t1", session_id="s1"),
            # task.query response
            TaskQueryResult(
                task_id="t1",
                state=TaskState.COMPLETED,
                tokens_used=5000,
                session_id="s1",
            ),
        ]
        mock_server.stream_events.return_value = iter([
            CompletionEvent(
                task_id="t1",
                state=TaskState.COMPLETED,
                tokens_used=5000,
                session_id="s1",
            ),
        ])

        op = ACPOperator(model="sonnet", server_factory=lambda: mock_server)

        # Pre-create stage file (in real usage, server writes it)
        stage_tmp = paths.stage_tmp_file(stage)
        write_text(stage_tmp, "# Stage 01: Literature Survey\n\n## Objective\nTest\n")
        write_text(paths.notes_dir / "fake.md", "fake")

        result = op.run_stage(stage, "test prompt", paths, attempt_no=1)

        assert result.success is True
        assert result.exit_code == 0
        assert result.session_id == "s1"
        assert result.stage_file_path == stage_tmp

    def test_run_stage_failure_no_stage_file(self, tmp_path):
        run_root = _make_run(tmp_path)
        paths = build_run_paths(run_root)
        stage = STAGES[0]

        mock_server = MagicMock()
        mock_server.handle_request.side_effect = [
            TaskCreateResult(task_id="t1", session_id="s1"),
            TaskQueryResult(task_id="t1", state=TaskState.COMPLETED, tokens_used=1000, session_id="s1"),
        ]
        mock_server.stream_events.return_value = iter([
            CompletionEvent(task_id="t1", state=TaskState.COMPLETED, tokens_used=1000, session_id="s1"),
        ])

        op = ACPOperator(model="sonnet", server_factory=lambda: mock_server)

        # Don't create stage file
        result = op.run_stage(stage, "test prompt", paths, attempt_no=1)

        assert result.success is False  # server says completed but file missing

    def test_run_stage_server_error(self, tmp_path):
        run_root = _make_run(tmp_path)
        paths = build_run_paths(run_root)
        stage = STAGES[0]

        mock_server = MagicMock()
        mock_server.handle_request.side_effect = RuntimeError("server crashed")

        op = ACPOperator(model="sonnet", server_factory=lambda: mock_server)

        result = op.run_stage(stage, "test prompt", paths, attempt_no=1)

        assert result.success is False
        assert result.exit_code == 1
        assert "server crashed" in result.stderr

    def test_session_id_persisted(self, tmp_path):
        run_root = _make_run(tmp_path)
        paths = build_run_paths(run_root)
        stage = STAGES[0]

        mock_server = MagicMock()
        mock_server.handle_request.side_effect = [
            TaskCreateResult(task_id="t1", session_id="persisted-session"),
            TaskQueryResult(task_id="t1", state=TaskState.COMPLETED, tokens_used=0, session_id="persisted-session"),
        ]
        mock_server.stream_events.return_value = iter([])

        op = ACPOperator(model="sonnet", server_factory=lambda: mock_server)
        write_text(paths.stage_tmp_file(stage), "# Stage 01\n")
        op.run_stage(stage, "test", paths, attempt_no=1)

        session_file = paths.stage_session_file(stage)
        assert session_file.exists()
        assert "persisted-session" in session_file.read_text(encoding="utf-8")

    def test_continue_session_reuses_session_id(self, tmp_path):
        run_root = _make_run(tmp_path)
        paths = build_run_paths(run_root)
        stage = STAGES[0]

        # Pre-set session id
        write_text(paths.stage_session_file(stage), "existing-session-id")

        mock_server = MagicMock()
        mock_server.handle_request.side_effect = [
            TaskCreateResult(task_id="t1", session_id="existing-session-id"),
            TaskQueryResult(task_id="t1", state=TaskState.COMPLETED, tokens_used=0),
        ]
        mock_server.stream_events.return_value = iter([])

        op = ACPOperator(model="sonnet", server_factory=lambda: mock_server)
        write_text(paths.stage_tmp_file(stage), "# Stage 01\n")
        result = op.run_stage(stage, "test", paths, attempt_no=2, continue_session=True)

        # Verify create was called with the existing session_id
        create_call = mock_server.handle_request.call_args_list[0]
        params = create_call[0][1]  # second positional arg is params
        assert params.session_id == "existing-session-id"

    def test_logs_written_to_jsonl(self, tmp_path):
        run_root = _make_run(tmp_path)
        paths = build_run_paths(run_root)
        stage = STAGES[0]

        mock_server = MagicMock()
        mock_server.handle_request.side_effect = [
            TaskCreateResult(task_id="t1", session_id="s1"),
            TaskQueryResult(task_id="t1", state=TaskState.COMPLETED, tokens_used=0),
        ]
        mock_server.stream_events.return_value = iter([])

        op = ACPOperator(model="sonnet", server_factory=lambda: mock_server)
        write_text(paths.stage_tmp_file(stage), "# Stage 01\n")
        op.run_stage(stage, "test prompt", paths, attempt_no=1)

        logs = paths.logs_raw.read_text(encoding="utf-8")
        assert "acp_start" in logs
        assert "acp_result" in logs

    def test_no_server_factory_raises(self, tmp_path):
        run_root = _make_run(tmp_path)
        paths = build_run_paths(run_root)
        stage = STAGES[0]

        op = ACPOperator(model="sonnet")  # no server_factory

        result = op.run_stage(stage, "test", paths, attempt_no=1)
        assert result.success is False
        assert "No ACP server factory" in result.stderr
