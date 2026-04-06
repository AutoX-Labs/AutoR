"""Tests for A2A agent card, server factory, and integration."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.a2a.agent_card import build_agent_card
from src.a2a.server import create_app
from src.operator_base import OperatorBase
from src.utils import OperatorResult


class FakeOperator(OperatorBase):
    def __init__(self, model: str = "fake-model"):
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def run_stage(self, stage, prompt, paths, attempt_no, continue_session=False):
        return OperatorResult(
            success=True, exit_code=0, stdout="fake", stderr="",
            stage_file_path=Path("/tmp/f.md"),
        )

    def repair_stage_summary(self, stage, original_prompt, original_result, paths, attempt_no):
        return self.run_stage(stage, original_prompt, paths, attempt_no)


class TestAgentCard:
    def test_card_name_includes_operator_type(self):
        op = FakeOperator()
        card = build_agent_card("http://localhost:50002", op)
        assert "fake" in card.name

    def test_card_description_includes_model(self):
        op = FakeOperator(model="haiku")
        card = build_agent_card("http://localhost:50002", op)
        assert "haiku" in card.description

    def test_card_has_8_skills(self):
        op = FakeOperator()
        card = build_agent_card("http://localhost:50002", op)
        assert len(card.skills) == 8

    def test_card_has_streaming_capability(self):
        op = FakeOperator()
        card = build_agent_card("http://localhost:50002", op)
        assert card.capabilities.streaming is True

    def test_card_has_provider(self):
        op = FakeOperator()
        card = build_agent_card("http://localhost:50002", op)
        assert card.provider.organization == "AutoX-AI-Labs"


class TestCreateApp:
    def test_create_app_returns_starlette_application(self):
        from a2a.server.apps import A2AStarletteApplication
        op = FakeOperator()
        app = create_app(operator=op, host="127.0.0.1", port=50099)
        assert isinstance(app, A2AStarletteApplication)

    def test_create_app_builds_asgi(self):
        op = FakeOperator()
        app = create_app(operator=op, host="127.0.0.1", port=50099)
        asgi = app.build()
        assert callable(asgi)
