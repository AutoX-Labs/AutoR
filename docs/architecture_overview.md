# AutoR Architecture Overview

> Generated 2026-04-02. Based on origin/main (commit 4efc3f2).

## What is AutoR

AutoR is a terminal-first, file-based, human-in-the-loop research workflow runner. It executes a fixed 8-stage research pipeline (literature survey -> hypothesis -> study design -> implementation -> experimentation -> analysis -> writing -> dissemination), producing auditable, publication-grade artifacts on disk.

## Technology Stack

- Python 3.10+ (pure stdlib, no external dependencies)
- Claude CLI (`claude`) via `subprocess.Popen` for AI invocation
- File-based state management (no database)
- YAML venue registry, JSON configs, Markdown stage summaries
- ANSI terminal UI

## Source Layout

```
AutoR/
  main.py                   # CLI entry point (argparse)
  src/
    manager.py              # ResearchManager: 8-stage orchestration loop
    operator.py             # ClaudeOperator: subprocess invocation of `claude` CLI
    terminal_ui.py          # TerminalUI: ANSI rendering, menus, streaming display
    utils.py                # Data models, validation, prompt assembly, venue resolution
    writing_manifest.py     # Artifact scanning for Stage 07
    prompts/                # One .md template per stage (01-08)
  templates/
    registry.yaml           # Venue metadata (NeurIPS, ICLR, Nature, etc.)
  tests/                    # Unit tests (pytest)
  docs/                     # Design docs, specs, analysis
  examples/                 # Example run artifacts
```

## Core Components

### 1. main.py (Entry Point)

- Parses CLI args: `--goal`, `--model`, `--venue`, `--resume-run`, `--redo-stage`, `--fake-operator`
- Creates `ClaudeOperator` and `ResearchManager`
- Routes to new run or resume existing run

### 2. ResearchManager (src/manager.py)

The central orchestrator. Owns the 8-stage loop.

**Key methods:**
- `run(user_goal, venue)` -> creates run dir, starts pipeline
- `resume_run(run_root, start_stage, venue)` -> resumes from pending stages
- `_run_stage(paths, stage)` -> single stage execution + approval loop
- `_build_stage_prompt(...)` -> assembles prompt from template + memory + feedback

**Stage execution flow:**
```
_run_stage():
  while True:
    1. Build prompt (initial or continuation)
    2. Call operator.run_stage()
    3. If stage file missing -> operator.repair_stage_summary()
    4. If still missing -> _materialize_missing_stage_draft() (local fallback)
    5. Validate markdown (required sections) + artifacts (files on disk)
    6. If invalid -> repair -> normalize locally if still invalid
    7. Show output to human, ask choice (1-6)
    8. Choice 1-3: use suggestion -> continue_session=True, loop
    9. Choice 4: custom feedback -> continue_session=True, loop
    10. Choice 5: approve -> promote tmp to final, append to memory.md
    11. Choice 6: abort
```

### 3. ClaudeOperator (src/operator.py)

Invokes `claude` CLI as subprocess. Key responsibilities:

- **Session management**: Each stage gets a UUID session ID stored in `operator_state/<stage>.session_id.txt`
- **Streaming**: Uses `--output-format stream-json` to get real-time output
- **Resume/fallback**: If `--resume` fails, falls back to new session
- **Repair**: `repair_stage_summary()` sends a targeted recovery prompt to fix missing/invalid output
- **Fake mode**: Returns synthetic markdown for testing without Claude

**CLI command construction** (`_build_cli_command`):
```
claude --model <model> --permission-mode bypassPermissions --dangerously-skip-permissions
  [--resume <session_id> | --session-id <session_id>]
  -p @<prompt_file>
  --output-format stream-json --verbose
```

### 4. Utils (src/utils.py)

Contains all data models and utility logic:

**Data models:**
- `StageSpec(number, slug, display_name)` - stage metadata
- `RunPaths` - all paths within a run directory
- `OperatorResult` - operator invocation result
- `STAGES` - the fixed list of 8 StageSpec instances

**Prompt assembly:**
- `build_prompt()` - initial prompt: instructions + template + user goal + memory + feedback
- `build_continuation_prompt()` - continuation prompt: references existing files, preserves work
- `format_stage_template()` - fills {{PLACEHOLDER}} tokens in stage templates

**Validation:**
- `validate_stage_markdown()` - checks required headings, placeholder text, file references
- `validate_stage_artifacts()` - checks for required files by stage (data, results, figures, LaTeX, PDF)
- `canonicalize_stage_markdown()` - local repair of invalid markdown structure

**Memory management:**
- `append_approved_stage_summary()` - appends approved summary to memory.md
- `approved_stage_entries()` / `approved_stage_numbers()` - parses memory.md
- `filtered_approved_memory()` - trims memory for redo scenarios

### 5. TerminalUI (src/terminal_ui.py)

ANSI-colored terminal interface:
- Banner, stage start/end notifications
- Live streaming of Claude output events
- Menu-driven approval choice (1-6)
- Multiline feedback input

### 6. Writing Manifest (src/writing_manifest.py)

Scans `figures/`, `results/`, `data/` to generate a manifest of available workspace artifacts for Stage 07 writing.

## Run Directory Structure

Each run is fully isolated:

```
runs/<timestamp>/
  user_input.txt            # Original research goal
  memory.md                 # Approved stage summaries (accumulates)
  run_config.json           # {model, venue, created_at}
  logs.txt                  # Human-readable timestamped log
  logs_raw.jsonl            # Raw Claude stream-json events
  prompt_cache/             # All prompts (audit trail)
  operator_state/           # Session IDs per stage
  stages/                   # Stage summaries (.md final, .tmp.md draft)
  workspace/
    literature/ code/ data/ results/ figures/
    writing/ artifacts/ notes/ reviews/
```

## Data Flow

```
User Goal
  |
  v
[memory.md: initially just goal]
  |
  v
For each stage 01-08:
  |
  +---> Stage template (prompts/<slug>.md)
  |       + {{PLACEHOLDER}} substitution
  |       + Venue profile
  |       + Writing manifest (stage 07)
  |
  +---> Approved memory (memory.md)
  |
  +---> Revision feedback (if continuing)
  |
  v
  Assembled prompt -> written to prompt_cache/
  |
  v
  ClaudeOperator.run_stage()
    -> subprocess: claude -p @prompt ...
    -> streams output to terminal + logs_raw.jsonl
    -> Claude writes stage summary to stages/<slug>.tmp.md
    -> Claude writes artifacts to workspace/
  |
  v
  Validation (markdown structure + artifact checks)
  |
  v
  Human approval loop (refine/approve/abort)
  |
  v
  If approved:
    stages/<slug>.tmp.md -> stages/<slug>.md  (promoted)
    Summary appended to memory.md
    Next stage
```

## Key Design Decisions

1. **Fixed 8-stage pipeline**: Not a generic agent framework. Research stages are hardcoded.
2. **File-based everything**: All state on disk. No database, no cloud state.
3. **Human gates**: Every stage requires explicit approval. Can't be skipped.
4. **Session-per-stage**: Each stage gets its own Claude session for continuation.
5. **Three-tier recovery**: primary attempt -> repair prompt -> local normalization.
6. **Prompt caching**: All prompts saved for auditability.
7. **Venue-aware writing**: Stage 07+ uses venue metadata for LaTeX formatting.

## Critical Coupling: `claude -p`

The entire system is tightly coupled to the Claude CLI (`claude -p`) subprocess model:

- **Invocation**: `operator.py` constructs CLI commands and calls `subprocess.Popen`
- **Session resume**: Uses `claude --resume <session_id>` for continuation
- **Output parsing**: Reads `stream-json` format line by line
- **Permission bypass**: Uses `--dangerously-skip-permissions` for autonomous operation
- **No API alternative**: There is no programmatic API path; everything goes through CLI

This coupling is the root cause of many observability and reliability issues:
- No structured error codes from Claude (only string matching for failure detection)
- No timeout control (subprocess hangs indefinitely)
- No way to inspect Claude's internal state
- Resume failure detection is fragile (string matching on stderr)
- Session IDs are opaque UUIDs with no health checking

## Known Vulnerability Categories

See `vulnerability_analysis.md` for detailed evidence from the example run.

| Category | Key Issues |
|----------|-----------|
| **Operator reliability** (V3-*) | Resume loops, no timeout, fragile failure detection, unclean interrupts |
| **Context management** (V4-*) | Prompt 8KB->75KB growth, memory.md redundancy, weak continuation prompts |
| **Writing quality** (V7-*) | No .bib file, no sections/ dir, compilation not reproducible |
| **Dissemination gates** (V8-*) | Blocking gaps don't block, checklist not machine-readable |
| **Cross-cutting** (S1-S3) | Resume storms, prompt bloat -> writing quality, checks != gates |
