"""A2A HTTP server for the AutoR research agent."""
from __future__ import annotations

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore

from .agent_card import build_agent_card
from .executor import AutoRExecutor
from ..operator_base import OperatorBase


def create_app(
    operator: OperatorBase,
    host: str = "0.0.0.0",
    port: int = 50002,
) -> A2AStarletteApplication:
    url = f"http://{host}:{port}"
    agent_card = build_agent_card(url, operator)
    executor = AutoRExecutor(operator)
    task_store = InMemoryTaskStore()
    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=task_store,
    )
    return A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=handler,
    )


def run_server(
    operator: OperatorBase,
    host: str = "0.0.0.0",
    port: int = 50002,
) -> None:
    import uvicorn
    app = create_app(operator=operator, host=host, port=port)
    uvicorn.run(app.build(), host=host, port=port)
