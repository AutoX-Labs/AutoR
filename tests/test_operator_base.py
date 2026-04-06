# tests/test_operator_base.py
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.operator_base import OperatorBase
from src.utils import OperatorResult, RunPaths, StageSpec, build_run_paths


class TestOperatorBaseABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError, match="abstract"):
            OperatorBase()

    def test_subclass_must_implement_model(self):
        class Incomplete(OperatorBase):
            def run_stage(self, stage, prompt, paths, attempt_no, continue_session=False):
                pass
            def repair_stage_summary(self, stage, original_prompt, original_result, paths, attempt_no):
                pass

        with pytest.raises(TypeError, match="abstract"):
            Incomplete()

    def test_subclass_must_implement_run_stage(self):
        class Incomplete(OperatorBase):
            @property
            def model(self) -> str:
                return "test"
            def repair_stage_summary(self, stage, original_prompt, original_result, paths, attempt_no):
                pass

        with pytest.raises(TypeError, match="abstract"):
            Incomplete()

    def test_subclass_must_implement_repair_stage_summary(self):
        class Incomplete(OperatorBase):
            @property
            def model(self) -> str:
                return "test"
            def run_stage(self, stage, prompt, paths, attempt_no, continue_session=False):
                pass

        with pytest.raises(TypeError, match="abstract"):
            Incomplete()

    def test_complete_subclass_can_be_instantiated(self):
        class Complete(OperatorBase):
            @property
            def model(self) -> str:
                return "test-model"
            def run_stage(self, stage, prompt, paths, attempt_no, continue_session=False):
                return OperatorResult(
                    success=True, exit_code=0, stdout="", stderr="",
                    stage_file_path=Path("/tmp/test.md"),
                )
            def repair_stage_summary(self, stage, original_prompt, original_result, paths, attempt_no):
                return OperatorResult(
                    success=True, exit_code=0, stdout="", stderr="",
                    stage_file_path=Path("/tmp/test.md"),
                )

        op = Complete()
        assert op.model == "test-model"
