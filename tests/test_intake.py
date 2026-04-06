from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.intake import (
    IntakeContext,
    QATurn,
    ResourceEntry,
    build_intake_from_goal,
    build_intake_from_resources,
    classify_resource,
    format_intake_for_prompt,
    ingest_resources,
    load_intake_context,
    save_intake_context,
)
from src.utils import (
    STAGES,
    build_prompt,
    build_run_paths,
    ensure_run_layout,
    initialize_memory,
    write_text,
)


class ClassifyResourceTests(unittest.TestCase):
    def test_pdf(self) -> None:
        rtype, ddir = classify_resource(Path("paper.pdf"))
        self.assertEqual(rtype, "pdf")
        self.assertEqual(ddir, "literature")

    def test_bib(self) -> None:
        rtype, ddir = classify_resource(Path("refs.bib"))
        self.assertEqual(rtype, "bib")
        self.assertEqual(ddir, "literature")

    def test_bibtex_suffix(self) -> None:
        rtype, ddir = classify_resource(Path("refs.bibtex"))
        self.assertEqual(rtype, "bib")
        self.assertEqual(ddir, "literature")

    def test_python_code(self) -> None:
        rtype, ddir = classify_resource(Path("model.py"))
        self.assertEqual(rtype, "code")
        self.assertEqual(ddir, "code")

    def test_csv_dataset(self) -> None:
        rtype, ddir = classify_resource(Path("data.csv"))
        self.assertEqual(rtype, "dataset")
        self.assertEqual(ddir, "data")

    def test_markdown_notes(self) -> None:
        rtype, ddir = classify_resource(Path("notes.md"))
        self.assertEqual(rtype, "notes")
        self.assertEqual(ddir, "notes")

    def test_tex(self) -> None:
        rtype, ddir = classify_resource(Path("main.tex"))
        self.assertEqual(rtype, "tex")
        self.assertEqual(ddir, "writing")

    def test_unknown_suffix(self) -> None:
        rtype, ddir = classify_resource(Path("mystery.xyz"))
        self.assertEqual(rtype, "other")
        self.assertEqual(ddir, "artifacts")

    def test_directory_with_code(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name) / "repo"
        d.mkdir()
        (d / "train.py").write_text("pass")
        rtype, ddir = classify_resource(d)
        self.assertEqual(rtype, "code")
        self.assertEqual(ddir, "code")

    def test_directory_without_code(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name) / "stuff"
        d.mkdir()
        (d / "readme.txt").write_text("hi")
        rtype, ddir = classify_resource(d)
        self.assertEqual(rtype, "other")
        self.assertEqual(ddir, "artifacts")


class IngestResourcesTests(unittest.TestCase):
    def _build_paths(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        run_root = Path(tmp_dir.name) / "run"
        paths = build_run_paths(run_root)
        ensure_run_layout(paths)
        return paths, tmp_dir.name

    def test_copies_file_to_workspace(self) -> None:
        paths, base = self._build_paths()
        src = Path(base) / "paper.pdf"
        src.write_bytes(b"%PDF-1.4 fake")

        entries = [
            ResourceEntry(
                source_path=str(src),
                resource_type="pdf",
                dest_dir="literature",
                dest_relative="",
                description="A test paper",
            )
        ]
        updated = ingest_resources(entries, paths)

        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0].dest_relative, "literature/paper.pdf")
        self.assertTrue((paths.literature_dir / "paper.pdf").exists())

    def test_copies_directory_to_workspace(self) -> None:
        paths, base = self._build_paths()
        src_dir = Path(base) / "my_repo"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("print('hi')")

        entries = [
            ResourceEntry(
                source_path=str(src_dir),
                resource_type="code",
                dest_dir="code",
                dest_relative="",
                description="Code repo",
            )
        ]
        updated = ingest_resources(entries, paths)

        self.assertEqual(len(updated), 1)
        self.assertTrue((paths.code_dir / "my_repo" / "main.py").exists())

    def test_skips_missing_source(self) -> None:
        paths, _ = self._build_paths()
        entries = [
            ResourceEntry(
                source_path="/nonexistent/file.pdf",
                resource_type="pdf",
                dest_dir="literature",
                dest_relative="",
                description="missing",
            )
        ]
        updated = ingest_resources(entries, paths)
        self.assertEqual(len(updated), 0)


class SerializationTests(unittest.TestCase):
    def _build_paths(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        run_root = Path(tmp_dir.name) / "run"
        paths = build_run_paths(run_root)
        ensure_run_layout(paths)
        return paths

    def test_roundtrip(self) -> None:
        paths = self._build_paths()
        ctx = IntakeContext(
            goal="Study transformers",
            original_goal="transformers",
            resources=[
                ResourceEntry("a.pdf", "pdf", "literature", "literature/a.pdf", "Paper A"),
            ],
            qa_transcript=[
                QATurn("What type?", "Empirical study"),
            ],
            notes="some notes",
        )
        save_intake_context(paths, ctx)
        loaded = load_intake_context(paths)

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.goal, "Study transformers")
        self.assertEqual(loaded.original_goal, "transformers")
        self.assertEqual(len(loaded.resources), 1)
        self.assertEqual(loaded.resources[0].source_path, "a.pdf")
        self.assertEqual(len(loaded.qa_transcript), 1)
        self.assertEqual(loaded.qa_transcript[0].answer, "Empirical study")
        self.assertEqual(loaded.notes, "some notes")

    def test_load_missing_returns_none(self) -> None:
        paths = self._build_paths()
        self.assertIsNone(load_intake_context(paths))


class FormatIntakeForPromptTests(unittest.TestCase):
    def test_includes_resources_and_qa(self) -> None:
        ctx = IntakeContext(
            goal="Study X",
            original_goal="X",
            resources=[
                ResourceEntry("a.pdf", "pdf", "literature", "literature/a.pdf", "Paper A"),
            ],
            qa_transcript=[
                QATurn("What type?", "Survey"),
            ],
        )
        text = format_intake_for_prompt(ctx)
        self.assertIn("literature/a.pdf", text)
        self.assertIn("Paper A", text)
        self.assertIn("What type?", text)
        self.assertIn("Survey", text)

    def test_empty_context(self) -> None:
        ctx = IntakeContext(goal="X", original_goal="X")
        text = format_intake_for_prompt(ctx)
        self.assertEqual(text, "")


class BuildIntakeHelpersTests(unittest.TestCase):
    def test_build_from_goal(self) -> None:
        ctx = build_intake_from_goal("Test goal")
        self.assertEqual(ctx.goal, "Test goal")
        self.assertEqual(ctx.original_goal, "Test goal")
        self.assertEqual(ctx.resources, [])

    def test_build_from_resources(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        pdf = Path(tmp.name) / "test.pdf"
        pdf.write_bytes(b"%PDF")
        csv = Path(tmp.name) / "data.csv"
        csv.write_text("a,b\n1,2")

        ctx = build_intake_from_resources("Goal", [str(pdf), str(csv)])
        self.assertEqual(ctx.goal, "Goal")
        self.assertEqual(len(ctx.resources), 2)
        types = {r.resource_type for r in ctx.resources}
        self.assertIn("pdf", types)
        self.assertIn("dataset", types)


class PromptIntegrationTests(unittest.TestCase):
    def test_prompt_includes_intake_section_when_present(self) -> None:
        stage = STAGES[0]
        prompt = build_prompt(
            stage=stage,
            stage_template="template content",
            user_request="research goal",
            approved_memory="",
            revision_feedback=None,
            intake_context_text="## Resources\n- paper.pdf",
        )
        self.assertIn("# Intake Context", prompt)
        self.assertIn("paper.pdf", prompt)

    def test_prompt_excludes_intake_section_when_absent(self) -> None:
        stage = STAGES[0]
        prompt = build_prompt(
            stage=stage,
            stage_template="template content",
            user_request="research goal",
            approved_memory="",
            revision_feedback=None,
        )
        self.assertNotIn("Intake Context", prompt)


class MemoryIntakeTests(unittest.TestCase):
    def _build_paths(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        run_root = Path(tmp_dir.name) / "run"
        paths = build_run_paths(run_root)
        ensure_run_layout(paths)
        return paths

    def test_memory_includes_intake_summary(self) -> None:
        paths = self._build_paths()
        initialize_memory(paths, "my goal", intake_summary="Resources: paper.pdf")
        memory = paths.memory.read_text(encoding="utf-8")
        self.assertIn("Intake Resources", memory)
        self.assertIn("paper.pdf", memory)

    def test_memory_without_intake(self) -> None:
        paths = self._build_paths()
        initialize_memory(paths, "my goal")
        memory = paths.memory.read_text(encoding="utf-8")
        self.assertNotIn("Intake Resources", memory)


if __name__ == "__main__":
    unittest.main()
