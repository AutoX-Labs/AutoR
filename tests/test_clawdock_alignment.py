from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.knowledge_base import initialize_knowledge_base, load_kb_entries, search_knowledge_base, write_kb_entry
from src.manager import ResearchManager
from src.operator import ClaudeOperator
from src.run_state import RUN_STATUS_COMPLETED, load_run_state
from src.utils import STAGES, build_prompt, build_run_paths, ensure_run_layout


class ClawDockAlignmentTests(unittest.TestCase):
    def test_build_prompt_includes_pattern_and_kb_context(self) -> None:
        stage = STAGES[0]
        prompt = build_prompt(
            stage=stage,
            stage_template="Stage template body",
            user_request="Survey recent work on retrieval.",
            approved_memory="Approved memory body",
            kb_context="1. [user_goal] Original user goal",
            revision_feedback=None,
        )

        self.assertIn("# Research Pipeline Mapping", prompt)
        self.assertIn(stage.orchestration_pattern, prompt)
        self.assertIn("# Knowledge Base Context", prompt)
        self.assertIn("Original user goal", prompt)

    def test_kb_search_prioritizes_matching_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_root = Path(tmp_dir) / "run"
            paths = build_run_paths(run_root)
            ensure_run_layout(paths)
            initialize_knowledge_base(paths, "Research goal")

            write_kb_entry(
                paths,
                entry_type="stage_approved",
                title="Literature survey approved",
                summary="Protein folding literature synthesis",
                content="Discussed literature evidence for protein folding.",
                stage=STAGES[0],
                tags=["literature"],
            )
            write_kb_entry(
                paths,
                entry_type="stage_approved",
                title="Hypothesis approved",
                summary="Hypothesis for protein folding experiments",
                content="Outlined a protein folding hypothesis.",
                stage=STAGES[1],
                tags=["hypothesis"],
            )

            results = search_knowledge_base(
                paths.knowledge_base_entries,
                query="protein folding literature",
                limit=3,
                stage=STAGES[0],
            )

            self.assertGreaterEqual(len(results), 1)
            self.assertEqual(results[0].entry.stage_slug, STAGES[0].slug)

    def test_fake_run_completes_with_state_and_kb(self) -> None:
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
                completed = manager.run("Build a reproducible research workflow.")

            self.assertTrue(completed)

            run_roots = sorted(path for path in runs_dir.iterdir() if path.is_dir())
            self.assertEqual(len(run_roots), 1)
            paths = build_run_paths(run_roots[0])

            state = load_run_state(paths.run_state)
            self.assertIsNotNone(state)
            assert state is not None
            self.assertEqual(state.status, RUN_STATUS_COMPLETED)
            self.assertEqual(len(state.approved_stages), len(STAGES))

            entries = load_kb_entries(paths.knowledge_base_entries)
            entry_types = [entry.entry_type for entry in entries]
            self.assertIn("run_completed", entry_types)
            self.assertEqual(entry_types.count("stage_approved"), len(STAGES))


if __name__ == "__main__":
    unittest.main()
