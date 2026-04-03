from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.platform.foundry import generate_release_package
from src.utils import build_run_paths, ensure_run_config, ensure_run_layout, initialize_memory, write_text


class ReleasePackageTests(unittest.TestCase):
    def test_generate_release_package_writes_expected_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_root = Path(tmp_dir) / "run"
            paths = build_run_paths(run_root)
            ensure_run_layout(paths)
            write_text(paths.user_input, "Release package title")
            initialize_memory(paths, "Release package title")
            ensure_run_config(paths, model="sonnet", venue="neurips_2025")

            package = generate_release_package(run_root)

            names = {path.name for path in package.artifact_paths}
            self.assertIn("readiness_checklist.md", names)
            self.assertIn("threats_to_validity.md", names)
            self.assertIn("artifact_bundle_manifest.json", names)
            self.assertIn("release_notes.md", names)
            self.assertIn("poster.md", names)
            self.assertIn("slides.md", names)
            self.assertIn("social.md", names)
            self.assertIn("external_summary.md", names)
            self.assertTrue(all(path.exists() for path in package.artifact_paths))


if __name__ == "__main__":
    unittest.main()
