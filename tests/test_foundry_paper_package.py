from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.platform.foundry import generate_paper_package
from src.utils import build_run_paths, ensure_run_config, ensure_run_layout, initialize_memory, write_text


class FoundryPaperPackageTests(unittest.TestCase):
    def test_generate_paper_package_writes_expected_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_root = Path(tmp_dir) / "run"
            paths = build_run_paths(run_root)
            ensure_run_layout(paths)
            write_text(paths.user_input, "Paper package title")
            initialize_memory(paths, "Paper package title")
            ensure_run_config(paths, model="sonnet", venue="neurips_2025")
            write_text(paths.results_dir / "metrics.json", '{"accuracy": 0.9}')
            (paths.figures_dir / "accuracy.png").write_bytes(b"\x89PNG fake")

            package = generate_paper_package(run_root)

            names = {path.name for path in package.artifact_paths}
            self.assertIn("abstract.md", names)
            self.assertIn("manuscript.tex", names)
            self.assertIn("references.bib", names)
            self.assertIn("build.sh", names)
            self.assertIn("submission_checklist.md", names)
            self.assertIn("paper.pdf", names)
            self.assertTrue(all(path.exists() for path in package.artifact_paths))


if __name__ == "__main__":
    unittest.main()
