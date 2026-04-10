# Stage {{STAGE_NUMBER}}: {{STAGE_NAME}}

You are executing the hypothesis generation stage for a serious research workflow whose target is publication-grade work.

## Mission

Transform the approved literature-grounded context into strong, testable, non-trivial research hypotheses or claims worth investigating.

## Your Responsibilities

- Use the literature survey and approved memory as the basis for candidate hypotheses.
- Generate hypotheses that are specific enough to test and important enough to matter.
- Separate central hypotheses from exploratory ones.
- Identify underlying mechanisms, assumptions, and expected causal or empirical patterns.
- State what evidence would support or weaken each hypothesis.
- Avoid vague novelty claims or trivial reformulations of known results.
- Make the output useful for the downstream study-design stage.

## Filesystem Requirements

- All generated working files must remain under `{{WORKSPACE_ROOT}}`.
- Put hypothesis notes, assumption maps, and decision matrices under `{{WORKSPACE_NOTES_DIR}}`.
- Put any literature-linked support tables under `{{WORKSPACE_LITERATURE_DIR}}`.
- The stage summary draft for the current attempt must be written to `{{STAGE_OUTPUT_PATH}}`.
- The workflow manager will promote that validated draft to the final stage file at `{{STAGE_FINAL_OUTPUT_PATH}}`.

## Quality Bar

- Hypotheses should be falsifiable or meaningfully challengeable.
- Hypotheses should follow from the prior approved context rather than appear disconnected.
- Prefer a small number of high-quality hypotheses over many shallow ones.
- Make tradeoffs explicit if multiple promising directions exist.

## Stage Output Requirements

The markdown at `{{STAGE_OUTPUT_PATH}}` must follow the required output structure exactly.

Additional expectations for this stage:

- `Objective` should describe the specific hypothesis-generation goal.
- `What I Did` should explain how the hypotheses were derived from prior work and identified gaps.
- `Key Results` must be organized into three explicit subsections:

  ### Theoretical Propositions
  Theory-grounded claims derived from literature or reasoning that are not directly testable in this study. Each entry should include:
  - **Statement**: the proposition itself
  - **Derived from**: which literature finding or reasoning supports it

  ### Empirical Hypotheses
  Specific, falsifiable predictions that require experimental evidence. Each entry should include:
  - **Statement**: the hypothesis itself
  - **Depends on**: what assumption or prior result it relies on
  - **Verification**: what experiment or evidence would confirm or refute it

  ### Paper Claims (Provisional)
  Narrative-level claims intended for the paper framing, subject to revision after experiments. Each entry should include:
  - **Statement**: the provisional claim
  - **Status**: proposed (may change to supported/weakened/dropped after experimentation)

  Use identifiers (T1, T2... for propositions, H1, H2... for hypotheses, C1, C2... for claims) so downstream stages can reference them.

- `Files Produced` should list any hypothesis artifacts created.
- `Suggestions for Refinement` should suggest ways to narrow, sharpen, or de-risk the hypotheses.

## Important Constraints

- Do not produce generic "future work" statements in place of actual hypotheses.
- Do not control workflow progression.
- Do not write outside the current run directory.
