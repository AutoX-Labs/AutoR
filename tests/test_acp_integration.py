"""End-to-end integration tests: ACPOperator + ACPServer wired together."""
from __future__ import annotations

from pathlib import Path

from src.acp_operator import ACPOperator
from src.acp_server import ACPServer
from src.operator_protocol import OperatorProtocol
from src.utils import STAGES, build_run_paths, ensure_run_layout, write_text


def _make_run(tmp_path: Path) -> Path:
    run_root = tmp_path / "integration_run"
    paths = build_run_paths(run_root)
    ensure_run_layout(paths)
    write_text(paths.user_input, "integration test goal")
    write_text(
        paths.memory,
        "# Approved Run Memory\n\n## Original User Goal\nintegration test\n\n## Approved Stage Summaries\n\n_None yet._\n",
    )
    return run_root


class TestACPIntegration:
    def test_operator_with_real_server_success(self, tmp_path):
        """ACPOperator + ACPServer can complete a task lifecycle (stub mode)."""
        run_root = _make_run(tmp_path)
        paths = build_run_paths(run_root)
        stage = STAGES[0]

        server = ACPServer(api_key="test-key")
        op = ACPOperator(model="sonnet", server_factory=lambda: server)
        assert isinstance(op, OperatorProtocol)

        # Pre-create stage file (in real usage, server writes it via Claude)
        stage_tmp = paths.stage_tmp_file(stage)
        write_text(stage_tmp, "# Stage 01: Literature Survey\n\n## Objective\nTest\n")
        write_text(paths.notes_dir / "fake.md", "placeholder")

        result = op.run_stage(stage, "test prompt", paths, attempt_no=1)

        assert result.success is True
        assert result.session_id is not None

    def test_operator_with_real_server_missing_file(self, tmp_path):
        """ACPOperator reports failure when stage file is not produced."""
        run_root = _make_run(tmp_path)
        paths = build_run_paths(run_root)
        stage = STAGES[0]

        server = ACPServer(api_key="test-key")
        op = ACPOperator(model="sonnet", server_factory=lambda: server)

        # Don't create the stage file
        result = op.run_stage(stage, "test prompt", paths, attempt_no=1)

        assert result.success is False

    def test_logs_contain_acp_events(self, tmp_path):
        """Verify that ACP events are logged to logs_raw.jsonl."""
        run_root = _make_run(tmp_path)
        paths = build_run_paths(run_root)
        stage = STAGES[0]

        server = ACPServer(api_key="test-key")
        op = ACPOperator(model="sonnet", server_factory=lambda: server)
        write_text(paths.stage_tmp_file(stage), "# Stage 01\n")

        op.run_stage(stage, "test prompt", paths, attempt_no=1)

        logs = paths.logs_raw.read_text(encoding="utf-8")
        assert "acp_start" in logs
        assert "acp_result" in logs
        assert "completion" in logs

    def test_session_id_persists_across_attempts(self, tmp_path):
        """Verify session continuity across multiple run_stage calls."""
        run_root = _make_run(tmp_path)
        paths = build_run_paths(run_root)
        stage = STAGES[0]

        server = ACPServer(api_key="test-key")
        op = ACPOperator(model="sonnet", server_factory=lambda: server)
        write_text(paths.stage_tmp_file(stage), "# Stage 01\n")

        # First attempt
        result1 = op.run_stage(stage, "first prompt", paths, attempt_no=1)
        session_id_1 = result1.session_id

        # Second attempt with continue_session=True
        result2 = op.run_stage(stage, "second prompt", paths, attempt_no=2, continue_session=True)
        session_id_2 = result2.session_id

        # Session ID from first attempt should be reused
        assert session_id_1 == session_id_2

    def test_repair_delegates_to_run_stage(self, tmp_path):
        """Verify repair_stage_summary works through the ACP path."""
        run_root = _make_run(tmp_path)
        paths = build_run_paths(run_root)
        stage = STAGES[0]

        server = ACPServer(api_key="test-key")
        op = ACPOperator(model="sonnet", server_factory=lambda: server)

        from src.utils import OperatorResult
        original_result = OperatorResult(
            success=False, exit_code=1, stdout="", stderr="",
            stage_file_path=paths.stage_tmp_file(stage),
        )

        # Pre-create to make result.success possible
        write_text(paths.stage_tmp_file(stage), "# Stage 01: Literature Survey\n")

        repair_result = op.repair_stage_summary(
            stage=stage,
            original_prompt="original prompt",
            original_result=original_result,
            paths=paths,
            attempt_no=1,
        )

        # Repair delegates to run_stage, which should succeed (file exists + server completes)
        assert repair_result.success is True

    def test_multiple_stages_independent(self, tmp_path):
        """Different stages get different session IDs."""
        run_root = _make_run(tmp_path)
        paths = build_run_paths(run_root)

        server = ACPServer(api_key="test-key")
        op = ACPOperator(model="sonnet", server_factory=lambda: server)

        for stage in STAGES[:3]:
            write_text(paths.stage_tmp_file(stage), f"# {stage.stage_title}\n")

        r1 = op.run_stage(STAGES[0], "prompt 1", paths, attempt_no=1)
        r2 = op.run_stage(STAGES[1], "prompt 2", paths, attempt_no=1)
        r3 = op.run_stage(STAGES[2], "prompt 3", paths, attempt_no=1)

        # Each stage should get its own session
        assert r1.session_id != r2.session_id
        assert r2.session_id != r3.session_id
