from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .types import PipelineStage, ResearchTask, TaskResult


@dataclass
class CommandResearchAgent:
    name: str
    domain: str
    pipeline_stages: list[PipelineStage]
    handler: Callable[[ResearchTask], TaskResult]
    citations: list[str] = field(default_factory=list)

    def run(self, task: ResearchTask) -> TaskResult:
        return self.handler(task)


class AgentRuntimeManager:
    def __init__(self) -> None:
        self._agents: dict[str, CommandResearchAgent] = {}

    def register(self, agent: CommandResearchAgent) -> None:
        self._agents[agent.name] = agent

    def list_agents(self) -> list[CommandResearchAgent]:
        return list(self._agents.values())

    def get(self, name: str) -> CommandResearchAgent:
        return self._agents[name]

