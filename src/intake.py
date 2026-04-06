from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .terminal_ui import TerminalUI
    from .utils import RunPaths

# ---------------------------------------------------------------------------
# Suffix sets (reuse from utils where possible, add code-oriented ones)
# ---------------------------------------------------------------------------

PDF_SUFFIXES = {".pdf"}
BIB_SUFFIXES = {".bib", ".bibtex"}
CODE_SUFFIXES = {".py", ".ipynb", ".r", ".jl", ".sh", ".js", ".ts", ".cpp", ".c", ".h", ".java", ".go", ".rs"}
DATA_SUFFIXES = {".json", ".jsonl", ".csv", ".tsv", ".parquet", ".yaml", ".yml", ".npz", ".npy"}
NOTES_SUFFIXES = {".md", ".txt", ".rst", ".org"}
TEX_SUFFIXES = {".tex"}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QATurn:
    question: str
    answer: str


@dataclass(frozen=True)
class ResourceEntry:
    source_path: str
    resource_type: str  # "pdf", "bib", "code", "dataset", "notes", "other"
    dest_dir: str  # workspace subdirectory name: "literature", "code", "data", "notes", "artifacts"
    dest_relative: str  # relative path within workspace after copy
    description: str


@dataclass(frozen=True)
class IntakeContext:
    goal: str
    original_goal: str
    resources: list[ResourceEntry] = field(default_factory=list)
    qa_transcript: list[QATurn] = field(default_factory=list)
    notes: str = ""


# ---------------------------------------------------------------------------
# Resource classification
# ---------------------------------------------------------------------------


def classify_resource(path: Path) -> tuple[str, str]:
    """Return (resource_type, dest_dir) based on file suffix or directory heuristic."""
    if path.is_dir():
        # Heuristic: if directory contains code-like files, treat as code
        code_files = list(path.rglob("*.py")) + list(path.rglob("*.ipynb"))
        if code_files:
            return "code", "code"
        return "other", "artifacts"

    suffix = path.suffix.lower()
    if suffix in PDF_SUFFIXES:
        return "pdf", "literature"
    if suffix in BIB_SUFFIXES:
        return "bib", "literature"
    if suffix in CODE_SUFFIXES:
        return "code", "code"
    if suffix in DATA_SUFFIXES:
        return "dataset", "data"
    if suffix in NOTES_SUFFIXES:
        return "notes", "notes"
    if suffix in TEX_SUFFIXES:
        return "tex", "writing"
    return "other", "artifacts"


# ---------------------------------------------------------------------------
# Resource ingestion
# ---------------------------------------------------------------------------

_DEST_DIR_MAP = {
    "literature": "literature_dir",
    "code": "code_dir",
    "data": "data_dir",
    "notes": "notes_dir",
    "writing": "writing_dir",
    "artifacts": "artifacts_dir",
}


def ingest_resources(
    resources: list[ResourceEntry],
    paths: RunPaths,
) -> list[ResourceEntry]:
    """Copy each resource into the appropriate workspace directory.

    Returns a new list of ResourceEntry with ``dest_relative`` filled in.
    Missing source files are skipped with a warning printed to stderr.
    """
    import sys

    updated: list[ResourceEntry] = []
    for entry in resources:
        src = Path(entry.source_path).expanduser().resolve()
        if not src.exists():
            print(f"Warning: resource not found, skipping: {src}", file=sys.stderr)
            continue

        attr = _DEST_DIR_MAP.get(entry.dest_dir, "artifacts_dir")
        dest_parent: Path = getattr(paths, attr)
        dest_parent.mkdir(parents=True, exist_ok=True)

        if src.is_dir():
            dest = dest_parent / src.name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
        else:
            dest = dest_parent / src.name
            shutil.copy2(src, dest)

        rel = dest.relative_to(paths.workspace_root)
        updated.append(
            ResourceEntry(
                source_path=entry.source_path,
                resource_type=entry.resource_type,
                dest_dir=entry.dest_dir,
                dest_relative=str(rel),
                description=entry.description,
            )
        )
    return updated


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def save_intake_context(paths: RunPaths, context: IntakeContext) -> Path:
    """Write *context* to ``intake_context.json`` under the run root."""
    dest = paths.intake_context
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(asdict(context), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return dest


def load_intake_context(paths: RunPaths) -> IntakeContext | None:
    """Load an IntakeContext from disk. Returns ``None`` for legacy runs."""
    if not paths.intake_context.exists():
        return None
    raw = json.loads(paths.intake_context.read_text(encoding="utf-8"))
    return IntakeContext(
        goal=raw["goal"],
        original_goal=raw["original_goal"],
        resources=[ResourceEntry(**r) for r in raw.get("resources", [])],
        qa_transcript=[QATurn(**t) for t in raw.get("qa_transcript", [])],
        notes=raw.get("notes", ""),
    )


# ---------------------------------------------------------------------------
# Prompt formatting
# ---------------------------------------------------------------------------

_MAX_RESOURCES_IN_PROMPT = 20


def format_intake_for_prompt(context: IntakeContext) -> str:
    """Format the intake context as a markdown section for stage prompts."""
    parts: list[str] = []

    if context.resources:
        lines = ["## User-Provided Resources", ""]
        shown = context.resources[:_MAX_RESOURCES_IN_PROMPT]
        for r in shown:
            desc = f" - {r.description}" if r.description else ""
            lines.append(f"- `workspace/{r.dest_relative}` ({r.resource_type}){desc}")
        remaining = len(context.resources) - len(shown)
        if remaining > 0:
            lines.append(f"- ... and {remaining} more resource(s) (see intake_context.json)")
        parts.append("\n".join(lines))

    if context.qa_transcript:
        qa_lines = ["## User Clarifications", ""]
        for turn in context.qa_transcript:
            qa_lines.append(f"**Q: {turn.question}**")
            qa_lines.append(f"A: {turn.answer}")
            qa_lines.append("")
        parts.append("\n".join(qa_lines).rstrip())

    if context.notes:
        parts.append(f"## Additional Notes\n\n{context.notes}")

    return "\n\n".join(parts).strip() if parts else ""


def format_resources_for_intake_prompt(resources: list[ResourceEntry]) -> str:
    """Format pre-loaded resources as a section for the intake stage prompt."""
    if not resources:
        return "_No resources pre-loaded._"
    lines = []
    for r in resources:
        rel = r.dest_relative or r.source_path
        desc = f" - {r.description}" if r.description else ""
        lines.append(f"- `{rel}` ({r.resource_type}){desc}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Convenience builders (non-interactive, for --skip-intake backward compat)
# ---------------------------------------------------------------------------


def build_intake_from_goal(goal: str) -> IntakeContext:
    """Build a minimal IntakeContext from a plain goal string (backward compat)."""
    return IntakeContext(goal=goal, original_goal=goal)


def build_intake_from_resources(
    goal: str,
    resource_paths: list[str],
) -> IntakeContext:
    """Build an IntakeContext from a goal and a list of file/dir paths.

    Used when ``--resources`` is provided without the interactive session.
    """
    entries: list[ResourceEntry] = []
    for p in resource_paths:
        path = Path(p).expanduser().resolve()
        rtype, ddir = classify_resource(path)
        entries.append(
            ResourceEntry(
                source_path=str(path),
                resource_type=rtype,
                dest_dir=ddir,
                dest_relative="",  # filled in during ingest
                description="",
            )
        )
    return IntakeContext(
        goal=goal,
        original_goal=goal,
        resources=entries,
    )


# ---------------------------------------------------------------------------
# Collect resource paths from UI (used before Claude-driven intake stage)
# ---------------------------------------------------------------------------


def collect_resource_paths_from_ui(
    ui: TerminalUI,
    initial_resources: list[str] | None = None,
) -> list[ResourceEntry]:
    """Prompt the user for resource file paths via the terminal UI.

    Returns a list of :class:`ResourceEntry` objects ready for ingestion.
    This runs *before* the Claude-driven intake stage so that resources
    are already in the workspace when the operator executes.
    """
    entries: list[ResourceEntry] = []

    # Seed from --resources if provided
    if initial_resources:
        for p in initial_resources:
            path = Path(p).expanduser().resolve()
            rtype, ddir = classify_resource(path)
            entries.append(
                ResourceEntry(
                    source_path=str(path),
                    resource_type=rtype,
                    dest_dir=ddir,
                    dest_relative="",
                    description="",
                )
            )
        ui.show_status(f"Pre-loaded {len(entries)} resource(s) from --resources.", level="info")

    if ui.ask_yes_no(
        "Do you have existing resources to include? (PDFs, code, datasets, .bib files, notes)",
        default=bool(entries),
    ):
        new_entries = ui.ask_resource_paths()
        for src_path, desc in new_entries:
            path = Path(src_path).expanduser().resolve()
            rtype, ddir = classify_resource(path)
            entries.append(
                ResourceEntry(
                    source_path=str(path),
                    resource_type=rtype,
                    dest_dir=ddir,
                    dest_relative="",
                    description=desc,
                )
            )

    return entries
