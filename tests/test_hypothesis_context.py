"""Tests for typed hypothesis context (Issue #33).

Validates that:
- Stage 02 prompt requires typed subsections in Key Results.
- extract_hypothesis_context extracts the three subsections.
- build_hypothesis_context reads from Stage 02 handoff.
- Downstream stage prompts inject hypothesis context for stage 3+.
- Stage 1-2 prompts do not include hypothesis context.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from src.utils import (
    STAGES,
    build_hypothesis_context,
    build_run_paths,
    create_run_root,
    ensure_run_layout,
    extract_hypothesis_context,
    initialize_memory,
    initialize_run_config,
    read_text,
    write_stage_handoff,
    write_text,
)


STAGE_02_WITH_TYPED_HYPOTHESES = """\
# Stage 02: Hypothesis Generation

## Objective
Generate testable hypotheses from the literature survey.

## Previously Approved Stage Summaries
_None yet._

## What I Did
Analyzed gaps from Stage 01 and derived typed claims.

## Key Results

### Theoretical Propositions
- **T1**: Attention mechanisms implicitly perform variable binding in compositional tasks.
  - Derived from: evidence in literature survey (papers A, B, C)

### Empirical Hypotheses
- **H1**: Adding a sparse gating layer will improve compositional generalization by at least 15%.
  - Depends on: T1 (attention as variable binding)
  - Verification: compare gated vs ungated models on SCAN and COGS benchmarks
- **H2**: The improvement will be larger on longer sequences (>20 tokens).
  - Depends on: H1
  - Verification: stratified evaluation by sequence length

### Paper Claims (Provisional)
- **C1**: Sparse gating is a lightweight, general-purpose enhancement for compositional reasoning.
  - Status: proposed

## Files Produced
- `workspace/notes/hypotheses.md` - detailed hypothesis derivation

## Decision Ledger
- **Open Questions**: Does the gating mechanism add significant inference latency?
- **Locked Decisions**: Focus on compositional generalization benchmarks
- **Assumptions**: Pre-trained transformer backbone is frozen
- **Rejected Alternatives**: Dense mixture-of-experts (too expensive)

## Suggestions for Refinement
1. Add a third benchmark (CFQ) for broader coverage.
2. Tighten the 15% threshold with a power analysis.
3. Consider an ablation on gating sparsity levels.

## Your Options
1. Use suggestion 1
2. Use suggestion 2
3. Use suggestion 3
4. Refine with your own feedback
5. Approve and continue
6. Abort
"""

STAGE_02_WITHOUT_TYPED_HYPOTHESES = """\
# Stage 02: Hypothesis Generation

## Objective
Generate hypotheses.

## Previously Approved Stage Summaries
_None yet._

## What I Did
Brainstormed ideas.

## Key Results
We hypothesize that method X will outperform baseline Y on benchmark Z.

## Files Produced
- `workspace/notes/hypotheses.md` - hypothesis list

## Decision Ledger
- **Open Questions**: None
- **Locked Decisions**: None
- **Assumptions**: None
- **Rejected Alternatives**: None

## Suggestions for Refinement
1. Refine hypothesis 1.
2. Add baseline comparison.
3. Strengthen theoretical motivation.

## Your Options
1. Use suggestion 1
2. Use suggestion 2
3. Use suggestion 3
4. Refine with your own feedback
5. Approve and continue
6. Abort
"""


class TestExtractHypothesisContext(unittest.TestCase):
    def test_extracts_all_three_subsections(self):
        result = extract_hypothesis_context(STAGE_02_WITH_TYPED_HYPOTHESES)
        self.assertIsNotNone(result)
        self.assertIn("### Theoretical Propositions", result)
        self.assertIn("### Empirical Hypotheses", result)
        self.assertIn("### Paper Claims (Provisional)", result)
        self.assertIn("T1", result)
        self.assertIn("H1", result)
        self.assertIn("C1", result)

    def test_extracts_hypothesis_details(self):
        result = extract_hypothesis_context(STAGE_02_WITH_TYPED_HYPOTHESES)
        self.assertIn("sparse gating layer", result)
        self.assertIn("Depends on", result)
        self.assertIn("Verification", result)
        self.assertIn("SCAN and COGS", result)

    def test_returns_none_without_subsections(self):
        result = extract_hypothesis_context(STAGE_02_WITHOUT_TYPED_HYPOTHESES)
        self.assertIsNone(result)

    def test_returns_none_without_key_results(self):
        no_results = "# Stage 02\n\n## Objective\nTest.\n"
        result = extract_hypothesis_context(no_results)
        self.assertIsNone(result)


class TestBuildHypothesisContext(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.runs_dir = Path(self.tmp) / "runs"
        self.runs_dir.mkdir()
        self.run_root = create_run_root(self.runs_dir)
        self.paths = build_run_paths(self.run_root)
        ensure_run_layout(self.paths)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_returns_none_when_no_stage_02_handoff(self):
        result = build_hypothesis_context(self.paths)
        self.assertIsNone(result)

    def test_returns_none_when_handoff_has_no_subsections(self):
        write_stage_handoff(self.paths, STAGES[1], STAGE_02_WITHOUT_TYPED_HYPOTHESES)
        result = build_hypothesis_context(self.paths)
        self.assertIsNone(result)

    def test_extracts_from_stage_02_handoff(self):
        write_stage_handoff(self.paths, STAGES[1], STAGE_02_WITH_TYPED_HYPOTHESES)
        result = build_hypothesis_context(self.paths)
        self.assertIsNotNone(result)
        self.assertIn("Theoretical Propositions", result)
        self.assertIn("Empirical Hypotheses", result)
        self.assertIn("Paper Claims (Provisional)", result)
        self.assertIn("sparse gating layer", result)


class TestStagePromptIncludesHypothesisContext(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.runs_dir = Path(self.tmp) / "runs"
        self.runs_dir.mkdir()
        self.run_root = create_run_root(self.runs_dir)
        self.paths = build_run_paths(self.run_root)
        ensure_run_layout(self.paths)
        initialize_run_config(self.paths, model="sonnet", venue="neurips_2025")
        initialize_memory(self.paths, "Test goal")
        write_text(self.paths.user_input, "Test goal")
        # Write Stage 01 handoff (needed for stage 02+)
        write_stage_handoff(self.paths, STAGES[0], (
            "# Stage 01: Literature Survey\n\n"
            "## Objective\nSurvey.\n\n"
            "## Key Results\nFound gaps.\n\n"
            "## Files Produced\n- `workspace/notes/survey.md`\n"
        ))
        # Write Stage 02 handoff with typed hypotheses
        write_stage_handoff(self.paths, STAGES[1], STAGE_02_WITH_TYPED_HYPOTHESES)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_hypothesis_context_injected_for_stage_03(self):
        from src.manager import ResearchManager
        from src.operator import ClaudeOperator
        from src.terminal_ui import TerminalUI

        repo_root = Path(__file__).resolve().parent.parent
        ui = TerminalUI()
        operator = ClaudeOperator(model="sonnet", fake_mode=True, ui=ui)
        manager = ResearchManager(
            project_root=repo_root, runs_dir=self.runs_dir,
            operator=operator, ui=ui,
        )
        # Stage 03 = STAGES[2]
        prompt = manager._build_stage_prompt(self.paths, STAGES[2], None, False)
        self.assertIn("Hypothesis Context (from Stage 02)", prompt)
        self.assertIn("Empirical Hypotheses", prompt)
        self.assertIn("sparse gating layer", prompt)
        self.assertIn("do not design experiments to test these", prompt)

    def test_hypothesis_context_not_injected_for_stage_02(self):
        from src.manager import ResearchManager
        from src.operator import ClaudeOperator
        from src.terminal_ui import TerminalUI

        repo_root = Path(__file__).resolve().parent.parent
        ui = TerminalUI()
        operator = ClaudeOperator(model="sonnet", fake_mode=True, ui=ui)
        manager = ResearchManager(
            project_root=repo_root, runs_dir=self.runs_dir,
            operator=operator, ui=ui,
        )
        prompt = manager._build_stage_prompt(self.paths, STAGES[1], None, False)
        self.assertNotIn("Hypothesis Context (from Stage 02)", prompt)


class TestStage02PromptRequiresTypedHypotheses(unittest.TestCase):
    def test_prompt_mentions_theoretical_propositions(self):
        prompt_path = Path(__file__).resolve().parent.parent / "src" / "prompts" / "02_hypothesis_generation.md"
        content = prompt_path.read_text()
        self.assertIn("Theoretical Propositions", content)
        self.assertIn("Empirical Hypotheses", content)
        self.assertIn("Paper Claims (Provisional)", content)

    def test_prompt_requires_identifiers(self):
        prompt_path = Path(__file__).resolve().parent.parent / "src" / "prompts" / "02_hypothesis_generation.md"
        content = prompt_path.read_text()
        self.assertIn("T1, T2", content)
        self.assertIn("H1, H2", content)
        self.assertIn("C1, C2", content)


class TestDownstreamPromptsReferenceHypotheses(unittest.TestCase):
    def test_stage_03_mentions_empirical_hypotheses(self):
        path = Path(__file__).resolve().parent.parent / "src" / "prompts" / "03_study_design.md"
        content = path.read_text()
        self.assertIn("Empirical Hypotheses", content)
        self.assertIn("Theoretical Propositions", content)

    def test_stage_05_mentions_empirical_hypotheses(self):
        path = Path(__file__).resolve().parent.parent / "src" / "prompts" / "05_experimentation.md"
        content = path.read_text()
        self.assertIn("Empirical Hypotheses", content)

    def test_stage_07_mentions_provisional_claims(self):
        path = Path(__file__).resolve().parent.parent / "src" / "prompts" / "07_writing.md"
        content = path.read_text()
        self.assertIn("provisional", content.lower())
        self.assertIn("verified", content.lower())


if __name__ == "__main__":
    unittest.main()
