from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.utils import STAGES, build_continuation_prompt, build_handoff_context, build_run_paths, ensure_run_layout, write_stage_handoff


class StageHandoffTests(unittest.TestCase):
    def test_write_stage_handoff_and_prompt_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_root = Path(tmp_dir) / "run"
            paths = build_run_paths(run_root)
            ensure_run_layout(paths)
            stage = STAGES[0]
            stage_markdown = (
                "# Stage 01: Literature Survey\n\n"
                "## Objective\nObjective.\n\n"
                "## Previously Approved Stage Summaries\n_None yet._\n\n"
                "## What I Did\nDid work.\n\n"
                "## Key Results\nKey result.\n\n"
                "## Files Produced\n- `workspace/literature/evidence.md`\n\n"
                "## Suggestions for Refinement\n"
                "1. Refine one.\n2. Refine two.\n3. Refine three.\n\n"
                "## Your Options\n"
                "1. Use suggestion 1\n2. Use suggestion 2\n3. Use suggestion 3\n4. Refine with your own feedback\n5. Approve and continue\n6. Abort\n"
            )
            write_stage_handoff(paths, stage, stage_markdown)
            handoff_context = build_handoff_context(paths, upto_stage=STAGES[1])
            prompt = build_continuation_prompt(
                stage=STAGES[1],
                stage_template="Stage template body",
                paths=paths,
                handoff_context=handoff_context,
                revision_feedback=None,
            )

            self.assertIn("Handoff: Stage 01: Literature Survey", handoff_context)
            self.assertIn("# Stage Handoff Context", prompt)
            self.assertIn("Handoff: Stage 01: Literature Survey", prompt)

    def test_build_handoff_context_collects_multiple_stage_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_root = Path(tmp_dir) / "run"
            paths = build_run_paths(run_root)
            ensure_run_layout(paths)
            write_stage_handoff(
                paths,
                STAGES[0],
                (
                    "# Stage 01: Literature Survey\n\n"
                    "## Objective\nObjective A.\n\n"
                    "## Previously Approved Stage Summaries\n_None yet._\n\n"
                    "## What I Did\nDid work.\n\n"
                    "## Key Results\nKey A.\n\n"
                    "## Files Produced\n- `workspace/literature/a.md`\n\n"
                    "## Suggestions for Refinement\n"
                    "1. Refine one.\n2. Refine two.\n3. Refine three.\n\n"
                    "## Your Options\n"
                    "1. Use suggestion 1\n2. Use suggestion 2\n3. Use suggestion 3\n4. Refine with your own feedback\n5. Approve and continue\n6. Abort\n"
                ),
            )
            write_stage_handoff(
                paths,
                STAGES[1],
                (
                    "# Stage 02: Hypothesis Generation\n\n"
                    "## Objective\nObjective B.\n\n"
                    "## Previously Approved Stage Summaries\n_None yet._\n\n"
                    "## What I Did\nDid work.\n\n"
                    "## Key Results\nKey B.\n\n"
                    "## Files Produced\n- `workspace/notes/b.md`\n\n"
                    "## Suggestions for Refinement\n"
                    "1. Refine one.\n2. Refine two.\n3. Refine three.\n\n"
                    "## Your Options\n"
                    "1. Use suggestion 1\n2. Use suggestion 2\n3. Use suggestion 3\n4. Refine with your own feedback\n5. Approve and continue\n6. Abort\n"
                ),
            )

            handoff_context = build_handoff_context(paths, upto_stage=STAGES[2])
            self.assertIn("Handoff: Stage 01: Literature Survey", handoff_context)
            self.assertIn("Handoff: Stage 02: Hypothesis Generation", handoff_context)


if __name__ == "__main__":
    unittest.main()
