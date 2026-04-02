from __future__ import annotations

from abc import ABC, abstractmethod

from .utils import OperatorResult, RunPaths, StageSpec


class OperatorProtocol(ABC):
    """Abstract base class defining the operator interface.

    Both ClaudeOperator (CLI subprocess) and ACPOperator (JSON-RPC)
    implement this protocol. ResearchManager depends only on this ABC.
    """

    @abstractmethod
    def run_stage(
        self,
        stage: StageSpec,
        prompt: str,
        paths: RunPaths,
        attempt_no: int,
        continue_session: bool = False,
    ) -> OperatorResult:
        """Execute a stage and return the result."""

    @abstractmethod
    def repair_stage_summary(
        self,
        stage: StageSpec,
        original_prompt: str,
        original_result: OperatorResult,
        paths: RunPaths,
        attempt_no: int,
    ) -> OperatorResult:
        """Attempt to repair a missing or invalid stage summary."""
