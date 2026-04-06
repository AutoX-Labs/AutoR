from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.manager import ResearchManager
from src.manifest import load_run_manifest
from src.utils import (
    DEFAULT_REFINEMENT_SUGGESTIONS,
    STAGES,
    OperatorResult,
    approved_stage_summaries,
    build_run_paths,
    read_text,
    relative_to_run,
    write_text,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
STAGE_01 = next(stage for stage in STAGES if stage.slug == "01_literature_survey")
STAGE_05 = next(stage for stage in STAGES if stage.slug == "05_experimentation")
STAGE_06 = next(stage for stage in STAGES if stage.slug == "06_analysis")


class ScriptedSmokeOperator:
    def __init__(self) -> None:
        self.model = "smoke-test-model"
        self.invocations: dict[str, int] = {}
        self.continue_modes: dict[str, list[bool]] = {}

    def run_stage(
        self,
        stage,
        prompt: str,
        paths,
        attempt_no: int,
        continue_session: bool = False,
    ) -> OperatorResult:
        invocation = self.invocations.get(stage.slug, 0) + 1
        self.invocations[stage.slug] = invocation
        self.continue_modes.setdefault(stage.slug, []).append(continue_session)
        produced = self._materialize_artifacts(stage, paths, invocation)
        stage_file = paths.stage_tmp_file(stage)
        write_text(
            stage_file,
            self._build_stage_markdown(
                stage,
                paths,
                invocation,
                produced,
                continue_session,
                len(prompt.split()),
            ),
        )
        return OperatorResult(
            success=True,
            exit_code=0,
            stdout=f"scripted invocation {invocation}",
            stderr="",
            stage_file_path=stage_file,
            session_id=f"{stage.slug}-session-{invocation}",
        )

    def repair_stage_summary(
        self,
        stage,
        original_prompt: str,
        original_result: OperatorResult,
        paths,
        attempt_no: int,
    ) -> OperatorResult:
        return self.run_stage(stage, original_prompt, paths, attempt_no, continue_session=False)

    def _materialize_artifacts(self, stage, paths, invocation: int) -> list[str]:
        produced: list[str] = []

        note_path = paths.notes_dir / f"{stage.slug}_smoke_note.md"
        write_text(note_path, f"# Smoke Note\n\nStage: {stage.slug}\nInvocation: {invocation}\n")
        produced.append(relative_to_run(note_path, paths.run_root))

        if stage.number >= 3:
            data_path = paths.data_dir / "study_design.json"
            write_text(
                data_path,
                json.dumps({"stage": stage.slug, "invocation": invocation, "dataset": "smoke"}),
            )
            produced.append(relative_to_run(data_path, paths.run_root))

        if stage.number >= 4:
            code_path = paths.code_dir / "train.py"
            write_text(code_path, "print('smoke experiment entrypoint')\n")
            produced.append(relative_to_run(code_path, paths.run_root))

        if stage.number >= 5:
            result_path = paths.results_dir / "metrics.json"
            write_text(
                result_path,
                json.dumps({"stage": stage.slug, "invocation": invocation, "accuracy": 0.9}),
            )
            produced.append(relative_to_run(result_path, paths.run_root))

        if stage.number >= 6:
            figure_path = paths.figures_dir / "accuracy.png"
            figure_path.write_bytes(b"\x89PNG smoke image data")
            produced.append(relative_to_run(figure_path, paths.run_root))

        if stage.number >= 7:
            sections_dir = paths.writing_dir / "sections"
            sections_dir.mkdir(parents=True, exist_ok=True)
            write_text(
                paths.writing_dir / "main.tex",
                (
                    "% AutoR venue: neurips_2025\n"
                    "\\documentclass{article}\n"
                    "\\usepackage{neurips_2023}\n"
                    "\\begin{document}\n"
                    "\\input{sections/introduction}\n"
                    "\\end{document}\n"
                ),
            )
            write_text(paths.writing_dir / "references.bib", "@article{smoke2026, title={Smoke}, year={2026}}\n")
            write_text(sections_dir / "introduction.tex", "\\section{Introduction}\nSmoke content.\n")
            write_text(sections_dir / "method.tex", "\\section{Method}\nSmoke content.\n")
            (paths.artifacts_dir / "paper.pdf").write_bytes(b"%PDF-1.4 smoke paper")
            write_text(paths.artifacts_dir / "build_log.txt", "Final status: SUCCESS\n")
            write_text(
                paths.artifacts_dir / "citation_verification.json",
                json.dumps({"overall_status": "pass", "total_citations": 1}),
            )
            write_text(
                paths.artifacts_dir / "self_review.json",
                json.dumps({"overall_score": 8.5, "final_verdict": "ready", "rounds": 1}),
            )
            produced.extend(
                [
                    relative_to_run(paths.writing_dir / "main.tex", paths.run_root),
                    relative_to_run(paths.artifacts_dir / "paper.pdf", paths.run_root),
                ]
            )

        if stage.number >= 8:
            review_path = paths.reviews_dir / "readiness.md"
            write_text(review_path, "# Readiness\n\n- Ready for smoke release.\n")
            produced.append(relative_to_run(review_path, paths.run_root))

        return produced

    def _build_stage_markdown(
        self,
        stage,
        paths,
        invocation: int,
        produced: list[str],
        continue_session: bool,
        prompt_word_count: int,
    ) -> str:
        prior = approved_stage_summaries(read_text(paths.memory))
        mode = "continuation" if continue_session else "fresh"
        files = "\n".join(f"- `{path}`" for path in produced)
        suggestions = "\n".join(
            f"{index}. {text}"
            for index, text in enumerate(DEFAULT_REFINEMENT_SUGGESTIONS, start=1)
        )

        return (
            f"# Stage {stage.number:02d}: {stage.display_name}\n\n"
            "## Objective\n"
            f"Produce a valid smoke-test stage summary for {stage.display_name}.\n\n"
            "## Previously Approved Stage Summaries\n"
            f"{prior}\n\n"
            "## What I Did\n"
            f"- Executed the scripted smoke operator in {mode} mode.\n"
            f"- Materialized the required artifacts for {stage.slug}.\n\n"
            "## Key Results\n"
            f"- Invocation marker: {invocation}\n"
            f"- Prompt words observed: {prompt_word_count}\n"
            "- The CLI workflow, validation, and approval loop all executed.\n\n"
            "## Files Produced\n"
            f"{files}\n\n"
            "## Suggestions for Refinement\n"
            f"{suggestions}\n\n"
            "## Your Options\n"
            "1. Use suggestion 1\n"
            "2. Use suggestion 2\n"
            "3. Use suggestion 3\n"
            "4. Refine with your own feedback\n"
            "5. Approve and continue\n"
            "6. Abort\n"
        )


class ManagerSmokeTests(unittest.TestCase):
    def _run_roots(self, runs_dir: Path) -> list[Path]:
        return sorted(path for path in runs_dir.iterdir() if path.is_dir())

    def _build_manager(self, tmp_dir: str) -> tuple[Path, ScriptedSmokeOperator, ResearchManager]:
        runs_dir = Path(tmp_dir) / "runs"
        operator = ScriptedSmokeOperator()
        manager = ResearchManager(
            project_root=REPO_ROOT,
            runs_dir=runs_dir,
            operator=operator,
            output_stream=io.StringIO(),
        )
        return runs_dir, operator, manager

    def test_manager_run_completes_full_eight_stage_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            runs_dir, operator, manager = self._build_manager(tmp_dir)

            with patch.object(manager, "_ask_choice", return_value="5"):
                success = manager.run("Smoke-test the end-to-end AutoR flow.", venue="neurips_2025")

            self.assertTrue(success)
            run_root = self._run_roots(runs_dir)[0]
            paths = build_run_paths(run_root)
            self.assertTrue(paths.run_manifest.exists())
            self.assertTrue((paths.artifacts_dir / "paper_package" / "paper.pdf").exists())
            self.assertTrue((paths.artifacts_dir / "release_package" / "artifact_bundle_manifest.json").exists())
            self.assertTrue(paths.stage_file(STAGE_06).exists())

    def test_resume_run_from_redo_stage_reruns_downstream_stages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            runs_dir, operator, manager = self._build_manager(tmp_dir)

            with patch.object(manager, "_ask_choice", return_value="5"):
                self.assertTrue(manager.run("Smoke-test redo-stage handling.", venue="neurips_2025"))

            run_root = self._run_roots(runs_dir)[0]
            paths = build_run_paths(run_root)
            initial_stage06 = read_text(paths.stage_file(STAGE_06))
            self.assertIn("Invocation marker: 1", initial_stage06)

            with patch.object(manager, "_ask_choice", return_value="5"):
                resumed = manager.resume_run(run_root, start_stage=STAGE_06, venue="neurips_2025")

            self.assertTrue(resumed)
            rerun_stage06 = read_text(paths.stage_file(STAGE_06))
            self.assertIn("Invocation marker: 2", rerun_stage06)
            self.assertIn("Invocation marker: 1", read_text(paths.stage_file(STAGES[4])))

    def test_stage_refinement_reuses_same_stage_before_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            _, operator, manager = self._build_manager(tmp_dir)
            paths = manager._create_run("Smoke-test stage refinement handling.", venue="neurips_2025")

            with patch.object(manager, "_ask_choice", side_effect=["1", "5"]):
                approved = manager._run_stage(paths, STAGE_01)

            self.assertTrue(approved)
            self.assertEqual(operator.continue_modes[STAGE_01.slug], [False, True])
            self.assertIn("Invocation marker: 2", read_text(paths.stage_file(STAGE_01)))

            manifest = load_run_manifest(paths.run_manifest)
            self.assertIsNotNone(manifest)
            assert manifest is not None
            entry = next(item for item in manifest.stages if item.slug == STAGE_01.slug)
            self.assertTrue(entry.approved)
            self.assertEqual(entry.attempt_count, 2)

    def test_resume_run_with_rollback_reruns_invalidated_downstream_stages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            runs_dir, operator, manager = self._build_manager(tmp_dir)

            with patch.object(manager, "_ask_choice", return_value="5"):
                self.assertTrue(manager.run("Smoke-test rollback resume handling.", venue="neurips_2025"))

            run_root = self._run_roots(runs_dir)[0]
            paths = build_run_paths(run_root)
            self.assertIn("Invocation marker: 1", read_text(paths.stage_file(STAGE_05)))
            self.assertIn("Invocation marker: 1", read_text(paths.stage_file(STAGE_06)))

            with patch.object(manager, "_ask_choice", return_value="5"):
                resumed = manager.resume_run(run_root, rollback_stage=STAGE_05, venue="neurips_2025")

            self.assertTrue(resumed)
            self.assertIn("Invocation marker: 2", read_text(paths.stage_file(STAGE_05)))
            self.assertIn("Invocation marker: 2", read_text(paths.stage_file(STAGE_06)))
            self.assertEqual(operator.invocations[STAGE_05.slug], 2)
            self.assertEqual(operator.invocations[STAGE_06.slug], 2)
            self.assertIn("Invocation marker: 1", read_text(paths.stage_file(STAGES[3])))

    def test_manager_abort_marks_run_cancelled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            runs_dir, _, manager = self._build_manager(tmp_dir)

            with patch.object(manager, "_ask_choice", return_value="6"):
                success = manager.run("Smoke-test abort handling.", venue="neurips_2025")

            self.assertFalse(success)
            run_root = self._run_roots(runs_dir)[0]
            paths = build_run_paths(run_root)
            manifest = load_run_manifest(paths.run_manifest)
            self.assertIsNotNone(manifest)
            assert manifest is not None
            self.assertEqual(manifest.run_status, "cancelled")
            self.assertEqual(manifest.current_stage_slug, STAGE_01.slug)
            self.assertIsNone(manifest.completed_at)


if __name__ == "__main__":
    unittest.main()
