from __future__ import annotations

import pytest

from src.operator_protocol import OperatorProtocol
from src.utils import OperatorResult, RunPaths, StageSpec


class FakeProtocolOperator(OperatorProtocol):
    """Minimal concrete implementation for testing the protocol."""

    def run_stage(
        self,
        stage: StageSpec,
        prompt: str,
        paths: RunPaths,
        attempt_no: int,
        continue_session: bool = False,
    ) -> OperatorResult:
        return OperatorResult(
            success=True,
            exit_code=0,
            stdout="fake",
            stderr="",
            stage_file_path=paths.stage_tmp_file(stage),
            session_id="fake-session",
        )

    def repair_stage_summary(
        self,
        stage: StageSpec,
        original_prompt: str,
        original_result: OperatorResult,
        paths: RunPaths,
        attempt_no: int,
    ) -> OperatorResult:
        return OperatorResult(
            success=True,
            exit_code=0,
            stdout="repaired",
            stderr="",
            stage_file_path=paths.stage_tmp_file(stage),
            session_id="fake-session",
        )


class TestOperatorProtocol:
    def test_fake_operator_satisfies_protocol(self):
        op = FakeProtocolOperator()
        assert isinstance(op, OperatorProtocol)

    def test_protocol_cannot_be_instantiated_directly(self):
        with pytest.raises(TypeError):
            OperatorProtocol()

    def test_claude_operator_satisfies_protocol(self):
        from src.operator import ClaudeOperator
        op = ClaudeOperator(fake_mode=True)
        assert isinstance(op, OperatorProtocol)
