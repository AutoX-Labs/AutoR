from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.manager import ResearchManager
from src.operator import ClaudeOperator
from src.platform.foundry import FoundryOutputFormat, generate_foundry_output
from src.platform.orchestration import HierarchicalPattern, ParallelPattern, SequentialPattern, SwarmPattern
from src.platform.security import ROLE_SCOPES, authorize_scope
from src.platform.semantic import SemanticIndexer
from src.platform.types import ResearchTask, TaskResult
from src.utils import STAGES


class PlatformAlignmentTests(unittest.TestCase):
    def test_semantic_indexer_ranks_relevant_document_first(self) -> None:
        matches = SemanticIndexer().rank(
            "protein folding literature evidence",
            [
                "agent orchestration and task routing",
                "protein folding literature survey and evidence extraction",
                "deployment and docker compose instructions",
            ],
            limit=3,
        )

        self.assertGreaterEqual(len(matches), 1)
        self.assertEqual(matches[0].index, 1)

    def test_orchestration_patterns_execute_tasks(self) -> None:
        tasks = [
            ResearchTask(task_id="1", title="A", goal="a", pipeline_stage="analysis", project_id="run"),
            ResearchTask(task_id="2", title="B", goal="b", pipeline_stage="analysis", project_id="run"),
        ]

        def runner(task: ResearchTask) -> TaskResult:
            return TaskResult(task_id=task.task_id, output=f"done:{task.title}")

        sequential_results = SequentialPattern().execute(tasks, runner)
        parallel_results = ParallelPattern(max_workers=2).execute(tasks, runner)
        swarm_results = SwarmPattern(rounds=2).execute(tasks, runner)
        hierarchical_results = HierarchicalPattern().execute(
            tasks[0],
            planner=lambda root: tasks,
            runner=runner,
        )

        self.assertEqual([item.output for item in sequential_results], ["done:A", "done:B"])
        self.assertEqual(sorted(item.output for item in parallel_results), ["done:A", "done:B"])
        self.assertEqual(len(swarm_results), 2)
        self.assertEqual(len(hierarchical_results), 2)

    def test_foundry_generation_writes_output(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with tempfile.TemporaryDirectory() as tmp_dir:
            runs_dir = Path(tmp_dir) / "runs"
            manager = ResearchManager(
                project_root=repo_root,
                runs_dir=runs_dir,
                operator=ClaudeOperator(fake_mode=True, output_stream=io.StringIO()),
                output_stream=io.StringIO(),
            )

            with patch("builtins.input", side_effect=["5"] * len(STAGES)):
                self.assertTrue(manager.run("Generate a foundry-ready package."))

            run_root = next(path for path in runs_dir.iterdir() if path.is_dir())
            output = generate_foundry_output(run_root, FoundryOutputFormat.PAPER)
            self.assertEqual(output.output_format, FoundryOutputFormat.PAPER)
            self.assertIn("paper.md", str(output.output_path))
            self.assertIn("Foundry Output: Paper", output.summary)

    def test_security_role_map_and_authorization(self) -> None:
        self.assertIn("researcher", ROLE_SCOPES)
        authorize_scope("researcher", "task.read")
        with self.assertRaises(PermissionError):
            authorize_scope("unknown-role", "task.read")


if __name__ == "__main__":
    unittest.main()
