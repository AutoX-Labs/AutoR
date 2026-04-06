# src/operator_base.py
from __future__ import annotations

from abc import ABC, abstractmethod

from .utils import OperatorResult, RunPaths, StageSpec


class OperatorBase(ABC):
    """Abstract base class for all operator backends.

    ResearchManager depends only on this interface.
    Each CLI agent (claude, codex, gemini, ...) implements a concrete subclass.
    """

    @property
    @abstractmethod
    def model(self) -> str:
        """Model name or alias used by this operator."""

    @abstractmethod
    def run_stage(
        self,
        stage: StageSpec,
        prompt: str,
        paths: RunPaths,
        attempt_no: int,
        continue_session: bool = False,
    ) -> OperatorResult:
        """Execute a research stage and return the result."""

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
