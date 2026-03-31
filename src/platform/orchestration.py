from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

from .types import ResearchTask, TaskResult


TaskRunner = Callable[[ResearchTask], TaskResult]


@dataclass(frozen=True)
class SequentialPattern:
    name: str = "sequential"

    def execute(self, tasks: list[ResearchTask], runner: TaskRunner) -> list[TaskResult]:
        return [runner(task) for task in tasks]


@dataclass(frozen=True)
class ParallelPattern:
    name: str = "parallel"
    max_workers: int = 4

    def execute(self, tasks: list[ResearchTask], runner: TaskRunner) -> list[TaskResult]:
        with ThreadPoolExecutor(max_workers=max(self.max_workers, 1)) as pool:
            futures = [pool.submit(runner, task) for task in tasks]
            return [future.result() for future in futures]


@dataclass(frozen=True)
class HierarchicalPattern:
    name: str = "hierarchical"

    def execute(
        self,
        root_task: ResearchTask,
        planner: Callable[[ResearchTask], list[ResearchTask]],
        runner: TaskRunner,
    ) -> list[TaskResult]:
        subtasks = planner(root_task)
        return [runner(task) for task in subtasks]


@dataclass(frozen=True)
class SwarmPattern:
    name: str = "swarm"
    rounds: int = 2

    def execute(self, tasks: list[ResearchTask], runner: TaskRunner) -> list[TaskResult]:
        results: list[TaskResult] = []
        for _ in range(max(self.rounds, 1)):
            results = [runner(task) for task in tasks]
        return results

