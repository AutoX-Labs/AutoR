"""Tests for the review_rebuttal module.

Unit tests cover text collection, JSON extraction, and file output.
Claude CLI calls are mocked to avoid real API calls.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.utils import (
    DEFAULT_VENUE,
    build_run_paths,
    ensure_run_config,
    ensure_run_layout,
    write_text,
)
from src.review_rebuttal import (
    REVIEWER_CONFIGS,
    REVIEW_FIELDS,
    _collect_paper_text,
    _extract_json,
    run_review_rebuttal_hook,
)


class TestExtractJson(unittest.TestCase):
    def test_plain_json(self):
        text = '{"Summary": "A paper", "Decision": "Accept"}'
        result = _extract_json(text)
        self.assertEqual(result["Summary"], "A paper")

    def test_json_in_code_fence(self):
        text = 'Here is the review:\n```json\n{"Summary": "Test", "Overall": 7}\n```\n'
        result = _extract_json(text)
        self.assertEqual(result["Summary"], "Test")
        self.assertEqual(result["Overall"], 7)

    def test_json_with_surrounding_text(self):
        text = 'THOUGHT: looks good\n\n{"Decision": "Reject", "Overall": 3}\n\nDone.'
        result = _extract_json(text)
        self.assertEqual(result["Decision"], "Reject")

    def test_nested_json(self):
        text = '{"outer": {"inner": 1}, "list": [1, 2]}'
        result = _extract_json(text)
        self.assertEqual(result["outer"]["inner"], 1)

    def test_no_json_raises(self):
        with self.assertRaises(ValueError):
            _extract_json("no json here")


class TestCollectPaperText(unittest.TestCase):
    def _make_run(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        run_root = Path(tmp_dir.name) / "run"
        paths = build_run_paths(run_root)
        ensure_run_layout(paths)
        write_text(paths.user_input, "Test")
        write_text(
            paths.memory,
            "# Approved Run Memory\n\n## Original User Goal\nTest\n\n"
            "## Approved Stage Summaries\n\n_None yet._\n",
        )
        ensure_run_config(paths, model="sonnet", venue=DEFAULT_VENUE)
        return paths

    def test_collects_main_and_sections(self):
        paths = self._make_run()
        write_text(paths.writing_dir / "main.tex", "\\documentclass{article}")
        sections = paths.writing_dir / "sections"
        sections.mkdir(parents=True, exist_ok=True)
        write_text(sections / "introduction.tex", "\\section{Introduction}\nHello.")
        write_text(sections / "method.tex", "\\section{Method}\nWe propose...")

        text = _collect_paper_text(paths)
        self.assertIn("\\documentclass{article}", text)
        self.assertIn("\\section{Introduction}", text)
        self.assertIn("\\section{Method}", text)

    def test_empty_writing_dir(self):
        paths = self._make_run()
        text = _collect_paper_text(paths)
        self.assertEqual(text, "")

    def test_truncates_long_bib(self):
        paths = self._make_run()
        write_text(paths.writing_dir / "main.tex", "\\documentclass{article}")
        write_text(paths.writing_dir / "references.bib", "x" * 5000)

        text = _collect_paper_text(paths)
        self.assertIn("bibliography truncated", text)


SAMPLE_REVIEW = {
    "Summary": "This paper proposes a novel method.",
    "Strengths": ["Good writing", "Novel approach", "Strong results"],
    "Weaknesses": ["Limited baselines", "No ablation", "Small dataset"],
    "Originality": 3,
    "Quality": 3,
    "Clarity": 3,
    "Significance": 2,
    "Questions": ["Why not compare with X?"],
    "Limitations": ["Only tested on one dataset"],
    "Soundness": 3,
    "Presentation": 3,
    "Contribution": 3,
    "Overall": 6,
    "Confidence": 4,
    "Decision": "Accept",
}

SAMPLE_META = {
    "consensus_strengths": ["Novel approach"],
    "consensus_weaknesses": ["Limited baselines"],
    "disagreements": [],
    "critical_issues": ["Need more baselines"],
    "recommendation": "Minor Revision",
    "meta_review_text": "The paper shows promise but needs more experiments.",
    "average_overall": 6.0,
}


class TestReviewRebuttalHook(unittest.TestCase):
    def _make_run_with_paper(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        run_root = Path(tmp_dir.name) / "run"
        paths = build_run_paths(run_root)
        ensure_run_layout(paths)
        write_text(paths.user_input, "Test review")
        write_text(
            paths.memory,
            "# Approved Run Memory\n\n## Original User Goal\nTest\n\n"
            "## Approved Stage Summaries\n\n_None yet._\n",
        )
        ensure_run_config(paths, model="sonnet", venue=DEFAULT_VENUE)

        # Create a minimal paper
        write_text(
            paths.writing_dir / "main.tex",
            (
                "\\documentclass{article}\n"
                "\\begin{document}\n"
                "\\title{Test Paper}\n"
                "\\input{sections/introduction}\n"
                "\\input{sections/method}\n"
                "\\end{document}\n"
            ),
        )
        sections = paths.writing_dir / "sections"
        sections.mkdir(parents=True, exist_ok=True)
        write_text(
            sections / "introduction.tex",
            "\\section{Introduction}\nWe study an important problem in ML. " * 10,
        )
        write_text(
            sections / "method.tex",
            "\\section{Method}\nWe propose a novel architecture. " * 10,
        )
        return paths

    @patch("src.review_rebuttal._call_claude")
    def test_full_pipeline_produces_artifacts(self, mock_claude):
        """Full pipeline with mocked Claude calls produces expected files."""
        paths = self._make_run_with_paper()

        # Mock responses for: 3 reviewers + 1 meta-review + 1 rebuttal
        call_count = [0]
        def mock_response(prompt, model="sonnet", timeout=600):
            call_count[0] += 1
            if call_count[0] <= 3:
                review = dict(SAMPLE_REVIEW)
                review["Overall"] = 5 + call_count[0]
                return json.dumps(review)
            elif call_count[0] == 4:
                return json.dumps(SAMPLE_META)
            else:
                return "# Rebuttal\n\n> Limited baselines\n\nWe will add more baselines.\n"

        mock_claude.side_effect = mock_response

        result = run_review_rebuttal_hook(paths, model="sonnet")

        self.assertIsNotNone(result)
        self.assertEqual(result["num_reviews"], 3)
        self.assertEqual(result["recommendation"], "Minor Revision")
        self.assertTrue(result["rebuttal_generated"])

        # Check files created
        reviews_dir = paths.reviews_dir
        self.assertTrue((reviews_dir / "review_r1.json").exists())
        self.assertTrue((reviews_dir / "review_r2.json").exists())
        self.assertTrue((reviews_dir / "review_r3.json").exists())
        self.assertTrue((reviews_dir / "meta_review.json").exists())
        self.assertTrue((reviews_dir / "rebuttal.md").exists())
        self.assertTrue((reviews_dir / "review_summary.json").exists())

        # Verify review content
        r1 = json.loads((reviews_dir / "review_r1.json").read_text())
        self.assertEqual(r1["Overall"], 6)
        self.assertEqual(r1["_reviewer_id"], "R1")

    @patch("src.review_rebuttal._call_claude")
    def test_skips_if_paper_too_short(self, mock_claude):
        """Should return None if paper text is too short."""
        paths = self._make_run_with_paper()
        write_text(paths.writing_dir / "main.tex", "short")
        # Remove sections
        for f in (paths.writing_dir / "sections").glob("*.tex"):
            f.unlink()

        result = run_review_rebuttal_hook(paths, model="sonnet")
        self.assertIsNone(result)
        mock_claude.assert_not_called()

    @patch("src.review_rebuttal._call_claude")
    def test_handles_reviewer_failure(self, mock_claude):
        """Should handle individual reviewer failures gracefully."""
        paths = self._make_run_with_paper()

        call_count = [0]
        def mock_response(prompt, model="sonnet", timeout=600):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("API error")
            elif call_count[0] <= 3:
                return json.dumps(SAMPLE_REVIEW)
            elif call_count[0] == 4:
                return json.dumps(SAMPLE_META)
            else:
                return "# Rebuttal\n\nAddressed."

        mock_claude.side_effect = mock_response

        result = run_review_rebuttal_hook(paths, model="sonnet")
        # Should still succeed with 2 out of 3 reviewers
        self.assertIsNotNone(result)
        self.assertEqual(result["num_reviews"], 2)

    @patch("src.review_rebuttal._call_claude")
    def test_returns_none_if_too_few_reviews(self, mock_claude):
        """Should return None if fewer than 2 reviews succeed."""
        paths = self._make_run_with_paper()

        call_count = [0]
        def mock_response(prompt, model="sonnet", timeout=600):
            call_count[0] += 1
            if call_count[0] <= 2:
                raise RuntimeError("API error")
            return json.dumps(SAMPLE_REVIEW)

        mock_claude.side_effect = mock_response

        result = run_review_rebuttal_hook(paths, model="sonnet")
        self.assertIsNone(result)


class TestReviewerConfigs(unittest.TestCase):
    def test_three_reviewers_configured(self):
        self.assertEqual(len(REVIEWER_CONFIGS), 3)

    def test_unique_ids(self):
        ids = [c["id"] for c in REVIEWER_CONFIGS]
        self.assertEqual(len(set(ids)), 3)

    def test_all_have_required_keys(self):
        for config in REVIEWER_CONFIGS:
            self.assertIn("id", config)
            self.assertIn("name", config)
            self.assertIn("system", config)


if __name__ == "__main__":
    unittest.main()
