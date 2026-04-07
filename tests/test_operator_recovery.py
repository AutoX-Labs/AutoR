from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


class OperatorRecoveryTests(unittest.TestCase):
    def test_resume_failure_falls_back_to_new_session_and_records_attempt_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_root = Path(tmp_dir) / "run"
            paths = build_run_paths(run_root)
            ensure_run_layout(paths)
            write_text(paths.user_input, "Operator recovery goal")
            initialize_memory(paths, "Operator recovery goal")

            operator = ClaudeOperator(fake_mode=False, output_stream=io.StringIO())
            stage = STAGES[0]
            old_session_id = "old-session-id"
            operator._persist_stage_session_id(paths, stage, old_session_id)

            call_count = {"value": 0}

            def fake_stream(*args, **kwargs):
                call_count["value"] += 1
                if call_count["value"] == 1:
                    return (
                        1,
                        "No conversation found with session id old-session-id",
                        "",
                        None,
                        {"raw_line_count": 1, "non_json_line_count": 1, "malformed_json_count": 1},
                    )

                stage_tmp_path = paths.stage_tmp_file(stage)
                write_text(
                    stage_tmp_path,
                    (
                        "# Stage 01: Literature Survey\n\n"
                        "## Objective\nRecovered.\n\n"
                        "## Previously Approved Stage Summaries\n_None yet._\n\n"
                        "## What I Did\nRecovered session.\n\n"
                        "## Key Results\nRecovered stage summary.\n\n"
                        "## Files Produced\n- `stages/01_literature_survey.tmp.md`\n\n"
                        "## Suggestions for Refinement\n"
                        "1. Refine one.\n2. Refine two.\n3. Refine three.\n\n"
                        "## Your Options\n"
                        "1. Use suggestion 1\n2. Use suggestion 2\n3. Use suggestion 3\n4. Refine with your own feedback\n5. Approve and continue\n6. Abort\n"
                    ),
                )
                return (
                    0,
                    "Recovered successfully.",
                    "",
                    "new-session-id",
                    {"raw_line_count": 2, "non_json_line_count": 0, "malformed_json_count": 0},
                )

            with patch("src.operator.shutil.which", return_value="/usr/bin/claude"), patch.object(
                operator,
                "_run_streaming_command",
                side_effect=fake_stream,
            ):
                result = operator._run_real(
                    stage=stage,
                    prompt="prompt",
                    paths=paths,
                    attempt_no=1,
                    continue_session=True,
                )

            self.assertTrue(result.success)
            self.assertEqual(result.session_id, "new-session-id")
            self.assertEqual(call_count["value"], 2)
            self.assertEqual(paths.stage_session_file(stage).read_text(encoding="utf-8").strip(), "new-session-id")

            attempt_state = json.loads(paths.stage_attempt_state_file(stage, 1).read_text(encoding="utf-8"))
            self.assertEqual(attempt_state["status"], "completed")
            self.assertEqual(attempt_state["mode"], "resume")
            self.assertEqual(attempt_state["session_id"], "new-session-id")

    def test_broken_session_is_not_reused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_root = Path(tmp_dir) / "run"
            paths = build_run_paths(run_root)
            ensure_run_layout(paths)
            write_text(paths.user_input, "Broken session test")
            initialize_memory(paths, "Broken session test")

            operator = ClaudeOperator(fake_mode=False, output_stream=io.StringIO())
            stage = STAGES[0]
            write_text(
                paths.stage_session_state_file(stage),
                json.dumps(
                    {
                        "session_id": "broken-session-id",
                        "broken": True,
                    },
                    indent=2,
                ),
            )

            resolved = operator._resolve_stage_session_id(paths, stage, continue_session=False)
            self.assertIsNotNone(resolved)
            self.assertNotEqual(resolved, "broken-session-id")


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
        """Simulate: run stage 01 (attempt 1) -> abort -> resume -> attempt should be 2."""
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
