from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.operator import ClaudeOperator
from src.utils import (
    STAGES,
    build_run_paths,
    ensure_run_layout,
    initialize_memory,
    read_attempt_count,
    write_attempt_count,
    write_text,
)


STAGE_01 = next(stage for stage in STAGES if stage.slug == "01_literature_survey")
STAGE_05 = next(stage for stage in STAGES if stage.slug == "05_experimentation")


class TestResumeFailureDetection(unittest.TestCase):
    def setUp(self) -> None:
        self.op = ClaudeOperator(fake_mode=True)

    def test_exact_message_detected(self) -> None:
        self.assertTrue(
            self.op._looks_like_resume_failure(
                "Error: No conversation found with session id abc-123", ""
            )
        )

    def test_resume_not_found_detected(self) -> None:
        self.assertTrue(
            self.op._looks_like_resume_failure(
                "Could not resume: session not found", ""
            )
        )

    def test_unrelated_resume_word_not_false_positive(self) -> None:
        self.assertFalse(
            self.op._looks_like_resume_failure(
                "Please resume the experiment from checkpoint 5", ""
            )
        )

    def test_empty_output(self) -> None:
        self.assertFalse(self.op._looks_like_resume_failure("", ""))

    def test_stderr_detected(self) -> None:
        self.assertTrue(
            self.op._looks_like_resume_failure(
                "", "No conversation found with session id xyz"
            )
        )

    def test_operator_precedence_fix(self) -> None:
        # Before the fix, this would incorrectly return True because
        # `"resume" in combined and "not found" in combined` was evaluated
        # before `or`, and both words appear in the text.
        # After the fix, "resume" + "not found" together should still match.
        self.assertTrue(
            self.op._looks_like_resume_failure(
                "Failed to resume session: not found in store", ""
            )
        )
        # But "resume" alone without "not found" should NOT match.
        self.assertFalse(
            self.op._looks_like_resume_failure(
                "Will resume processing after delay", ""
            )
        )


class TestAttemptCountPersistence(unittest.TestCase):
    def test_read_returns_zero_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_run_paths(Path(tmp) / "run")
            ensure_run_layout(paths)
            self.assertEqual(read_attempt_count(paths, STAGE_01), 0)

    def test_write_and_read_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_run_paths(Path(tmp) / "run")
            ensure_run_layout(paths)
            write_attempt_count(paths, STAGE_05, 3)
            self.assertEqual(read_attempt_count(paths, STAGE_05), 3)

    def test_increments_across_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_run_paths(Path(tmp) / "run")
            ensure_run_layout(paths)
            for i in range(1, 6):
                write_attempt_count(paths, STAGE_01, i)
            self.assertEqual(read_attempt_count(paths, STAGE_01), 5)

    def test_different_stages_independent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_run_paths(Path(tmp) / "run")
            ensure_run_layout(paths)
            write_attempt_count(paths, STAGE_01, 3)
            write_attempt_count(paths, STAGE_05, 7)
            self.assertEqual(read_attempt_count(paths, STAGE_01), 3)
            self.assertEqual(read_attempt_count(paths, STAGE_05), 7)


class TestStageTimeout(unittest.TestCase):
    def test_default_timeout_is_4_hours(self) -> None:
        op = ClaudeOperator(fake_mode=True)
        self.assertEqual(op.stage_timeout, 14400)

    def test_custom_timeout(self) -> None:
        op = ClaudeOperator(fake_mode=True, stage_timeout=7200)
        self.assertEqual(op.stage_timeout, 7200)


class TestFakeOperatorAttemptContinuity(unittest.TestCase):
    def test_attempt_no_continues_after_resume(self) -> None:
        """Simulate: run stage 01 (attempt 1) → abort → resume → attempt should be 2."""
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_run_paths(Path(tmp) / "run")
            ensure_run_layout(paths)
            write_text(paths.user_input, "test goal")
            initialize_memory(paths, "test goal")

            # First attempt
            attempt_no = read_attempt_count(paths, STAGE_01) + 1
            self.assertEqual(attempt_no, 1)
            write_attempt_count(paths, STAGE_01, attempt_no)

            # Simulate abort and resume
            attempt_no = read_attempt_count(paths, STAGE_01) + 1
            self.assertEqual(attempt_no, 2)
            write_attempt_count(paths, STAGE_01, attempt_no)

            # Another resume
            attempt_no = read_attempt_count(paths, STAGE_01) + 1
            self.assertEqual(attempt_no, 3)


if __name__ == "__main__":
    unittest.main()
