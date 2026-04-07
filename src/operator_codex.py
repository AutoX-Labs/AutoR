"""Codex CLI operator skeleton.

This is a placeholder for future Codex CLI integration.
It implements the OperatorBase interface but raises NotImplementedError
for all operations.
"""
from __future__ import annotations

from .operator_base import OperatorBase
from .utils import OperatorResult, RunPaths, StageSpec


class CodexOperator(OperatorBase):
    """Operator backed by the Codex CLI (placeholder).

    To implement a real Codex operator, override run_stage() and
    repair_stage_summary() with subprocess calls to the codex CLI.
    """

    def __init__(self, model: str = "codex-mini") -> None:
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def run_stage(
        self,
        stage: StageSpec,
        prompt: str,
        paths: RunPaths,
        attempt_no: int,
        continue_session: bool = False,
    ) -> OperatorResult:
        raise NotImplementedError(
            "CodexOperator is a placeholder. "
            "Implement run_stage() to call the Codex CLI."
        )

    def repair_stage_summary(
        self,
        stage: StageSpec,
        original_prompt: str,
        original_result: OperatorResult,
        paths: RunPaths,
        attempt_no: int,
    ) -> OperatorResult:
        raise NotImplementedError(
            "CodexOperator is a placeholder. "
            "Implement repair_stage_summary() to call the Codex CLI."
        )
