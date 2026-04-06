from __future__ import annotations

from pathlib import Path

import pytest

from src.operator_codex import CodexOperator
from src.operator_base import OperatorBase
from src.utils import OperatorResult, StageSpec


class TestCodexOperator:
    def test_is_operator_base(self):
        op = CodexOperator()
        assert isinstance(op, OperatorBase)

    def test_default_model(self):
        op = CodexOperator()
        assert op.model == "codex-mini"

    def test_custom_model(self):
        op = CodexOperator(model="o3")
        assert op.model == "o3"

    def test_run_stage_raises_not_implemented(self):
        op = CodexOperator()
        stage = StageSpec(number=1, slug="01_literature_survey", display_name="Literature Survey")
        with pytest.raises(NotImplementedError, match="CodexOperator"):
            op.run_stage(stage, "test", None, 1)

    def test_repair_stage_summary_raises_not_implemented(self):
        op = CodexOperator()
        stage = StageSpec(number=1, slug="01_literature_survey", display_name="Literature Survey")
        dummy_result = OperatorResult(
            success=False, exit_code=1, stdout="", stderr="",
            stage_file_path=Path("/tmp/x.md"),
        )
        with pytest.raises(NotImplementedError, match="CodexOperator"):
            op.repair_stage_summary(stage, "test", dummy_result, None, 1)
