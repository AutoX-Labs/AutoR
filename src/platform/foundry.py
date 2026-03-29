from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..inspection import build_run_snapshot, list_run_artifacts
from ..utils import build_run_paths, read_text, write_text


class FoundryOutputFormat(str, Enum):
    PAPER = "paper"
    POSTER = "poster"
    SLIDES = "slides"
    SOCIAL = "social"


@dataclass(frozen=True)
class FoundryOutput:
    output_format: FoundryOutputFormat
    output_path: Path
    summary: str


def generate_foundry_output(run_root: Path, output_format: FoundryOutputFormat) -> FoundryOutput:
    paths = build_run_paths(run_root)
    foundry_dir = paths.artifacts_dir / "foundry"
    foundry_dir.mkdir(parents=True, exist_ok=True)
    output_path = foundry_dir / f"{output_format.value}.md"

    snapshot = build_run_snapshot(run_root)
    memory_text = read_text(paths.memory) if paths.memory.exists() else ""
    artifacts = list_run_artifacts(run_root)
    summary = (
        f"# Foundry Output: {output_format.value.title()}\n\n"
        f"Run: {run_root.name}\n"
        f"Status: {snapshot['status']}\n"
        f"Approved stages: {snapshot['approved_stage_count']}\n"
        f"Artifacts: {artifacts['total_files']}\n\n"
        "## Approved Memory\n\n"
        f"{memory_text.strip() or 'No memory recorded.'}\n\n"
        "## Artifact Groups\n\n"
        + "\n".join(
            f"- {group}: {len(files)} file(s)"
            for group, files in artifacts["groups"].items()
            if files
        )
        + "\n"
    )
    write_text(output_path, summary)
    return FoundryOutput(output_format=output_format, output_path=output_path, summary=summary)
