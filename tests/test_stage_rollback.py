from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.manifest import (
    initialize_run_manifest,
    load_run_manifest,
    mark_stage_approved_manifest,
    rollback_to_stage,
)
from src.utils import STAGES, build_run_paths, ensure_run_config, ensure_run_layout, initialize_memory, write_text


class StageRollbackTests(unittest.TestCase):
    def test_rollback_marks_downstream_stale_and_rebuilds_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            runs_dir = Path(tmp_dir) / "runs"
            run_root = runs_dir / "run"
            paths = build_run_paths(run_root)
            ensure_run_layout(paths)
            write_text(paths.user_input, "Rollback validation workflow.")
            initialize_memory(paths, "Rollback validation workflow.")
            ensure_run_config(paths, model="sonnet", venue="neurips_2025")

            initialize_run_manifest(paths)
            for stage in STAGES[:5]:
                write_text(
                    paths.stage_file(stage),
                    (
                        f"# Stage {stage.number:02d}: {stage.display_name}\n\n"
                        "## Objective\nDone.\n\n"
                        "## Previously Approved Stage Summaries\n_None yet._\n\n"
                        "## What I Did\nDid work.\n\n"
                        "## Key Results\nKey result.\n\n"
                        "## Files Produced\n- `stages/example.md`\n\n"
                        "## Suggestions for Refinement\n"
                        "1. Refine one.\n2. Refine two.\n3. Refine three.\n\n"
                        "## Your Options\n"
                        "1. Use suggestion 1\n2. Use suggestion 2\n3. Use suggestion 3\n4. Refine with your own feedback\n5. Approve and continue\n6. Abort\n"
                    ),
                )
                mark_stage_approved_manifest(paths, stage, attempt_no=1, artifact_paths=[str(paths.stage_file(stage))])

            rollback_to_stage(paths, STAGES[2], reason="Redo study design")
            manifest = load_run_manifest(paths.run_manifest)
            assert manifest is not None

            by_slug = {entry.slug: entry for entry in manifest.stages}
            self.assertEqual(by_slug["03_study_design"].status, "pending")
            self.assertTrue(by_slug["03_study_design"].dirty)
            self.assertEqual(by_slug["04_implementation"].status, "stale")
            self.assertTrue(by_slug["04_implementation"].stale)
            self.assertEqual(by_slug["05_experimentation"].status, "stale")


if __name__ == "__main__":
    unittest.main()
