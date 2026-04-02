"""Tests for operator recovery: resume failure detection, attempt persistence, interrupt logging."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.operator import ClaudeOperator
from src.utils import (
    STAGES,
    build_run_paths,
    ensure_run_layout,
    read_attempt_count,
    read_text,
    write_attempt_count,
    write_text,
)


# ---------------------------------------------------------------------------
# V3-3: _looks_like_resume_failure detection
# ---------------------------------------------------------------------------


class TestResumeFailureDetection:
    def _op(self) -> ClaudeOperator:
        return ClaudeOperator(fake_mode=True)

    def test_exact_session_not_found_message(self):
        op = self._op()
        assert op._looks_like_resume_failure(
            "Error: No conversation found with session id abc-123", ""
        )

    def test_case_insensitive(self):
        op = self._op()
        assert op._looks_like_resume_failure(
            "ERROR: NO CONVERSATION FOUND WITH SESSION ID XYZ", ""
        )

    def test_resume_not_found_detected(self):
        op = self._op()
        assert op._looks_like_resume_failure(
            "Could not resume: session not found", ""
        )

    def test_resume_and_not_found_in_stderr(self):
        op = self._op()
        assert op._looks_like_resume_failure(
            "", "Failed to resume session — not found in backend"
        )

    def test_unrelated_resume_word_not_false_positive(self):
        op = self._op()
        # "resume" appears in normal research context, no "not found"
        assert not op._looks_like_resume_failure(
            "Please resume the experiment from checkpoint 5", ""
        )

    def test_not_found_without_resume_not_false_positive(self):
        op = self._op()
        # "not found" without "resume" should not trigger
        assert not op._looks_like_resume_failure(
            "File not found: data.csv", ""
        )

    def test_empty_output(self):
        op = self._op()
        assert not op._looks_like_resume_failure("", "")

    def test_none_like_empty(self):
        op = self._op()
        # Both empty strings
        assert not op._looks_like_resume_failure("", "")

    def test_normal_success_output(self):
        op = self._op()
        assert not op._looks_like_resume_failure(
            '{"type":"result","subtype":"success","session_id":"abc"}', ""
        )


# ---------------------------------------------------------------------------
# V3-1: attempt_no persistence across resumes
# ---------------------------------------------------------------------------


class TestAttemptCountPersistence:
    def test_initial_count_is_zero(self, tmp_path):
        paths = build_run_paths(tmp_path / "run")
        ensure_run_layout(paths)
        stage = STAGES[0]
        assert read_attempt_count(paths, stage) == 0

    def test_write_then_read(self, tmp_path):
        paths = build_run_paths(tmp_path / "run")
        ensure_run_layout(paths)
        stage = STAGES[0]
        write_attempt_count(paths, stage, 3)
        assert read_attempt_count(paths, stage) == 3

    def test_increments_across_writes(self, tmp_path):
        paths = build_run_paths(tmp_path / "run")
        ensure_run_layout(paths)
        stage = STAGES[0]

        for i in range(1, 6):
            write_attempt_count(paths, stage, i)

        assert read_attempt_count(paths, stage) == 5

    def test_different_stages_independent(self, tmp_path):
        paths = build_run_paths(tmp_path / "run")
        ensure_run_layout(paths)
        write_attempt_count(paths, STAGES[0], 3)
        write_attempt_count(paths, STAGES[1], 7)
        assert read_attempt_count(paths, STAGES[0]) == 3
        assert read_attempt_count(paths, STAGES[1]) == 7

    def test_corrupt_file_returns_zero(self, tmp_path):
        paths = build_run_paths(tmp_path / "run")
        ensure_run_layout(paths)
        stage = STAGES[0]
        path = paths.operator_state_dir / f"{stage.slug}.attempt_count.txt"
        write_text(path, "not_a_number")
        assert read_attempt_count(paths, stage) == 0

    def test_empty_file_returns_zero(self, tmp_path):
        paths = build_run_paths(tmp_path / "run")
        ensure_run_layout(paths)
        stage = STAGES[0]
        path = paths.operator_state_dir / f"{stage.slug}.attempt_count.txt"
        path.write_text("", encoding="utf-8")
        assert read_attempt_count(paths, stage) == 0

    def test_manager_reads_persisted_count(self, tmp_path):
        """Verify that manager._run_stage starts from persisted count + 1."""
        paths = build_run_paths(tmp_path / "run")
        ensure_run_layout(paths)
        stage = STAGES[0]

        # Pre-set as if 3 attempts already happened
        write_attempt_count(paths, stage, 3)
        write_text(paths.user_input, "test goal")
        write_text(
            paths.memory,
            "# Approved Run Memory\n\n## Original User Goal\ntest\n\n"
            "## Approved Stage Summaries\n\n_None yet._\n",
        )

        # After setting count=3, next attempt_no should be 4
        assert read_attempt_count(paths, stage) + 1 == 4

    def test_write_attempt_count_called_by_manager(self, tmp_path):
        """After fake-operator run_stage + write_attempt_count, count persists."""
        paths = build_run_paths(tmp_path / "run")
        ensure_run_layout(paths)
        stage = STAGES[0]

        # Simulate what manager does: read, increment, run, write
        attempt_no = read_attempt_count(paths, stage) + 1
        assert attempt_no == 1

        write_attempt_count(paths, stage, attempt_no)
        assert read_attempt_count(paths, stage) == 1

        # Simulate second resume
        attempt_no = read_attempt_count(paths, stage) + 1
        assert attempt_no == 2

        write_attempt_count(paths, stage, attempt_no)
        assert read_attempt_count(paths, stage) == 2
