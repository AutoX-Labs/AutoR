from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .platform.semantic import SemanticIndexer
from .utils import RunPaths, StageSpec, truncate_text


TOKEN_PATTERN = re.compile(r"[a-z0-9_]{2,}")


@dataclass(frozen=True)
class KBEntry:
    entry_id: str
    created_at: str
    run_id: str
    entry_type: str
    title: str
    summary: str
    content: str
    stage_slug: str | None = None
    tags: list[str] = field(default_factory=list)
    file_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "entry_id": self.entry_id,
            "created_at": self.created_at,
            "run_id": self.run_id,
            "entry_type": self.entry_type,
            "title": self.title,
            "summary": self.summary,
            "content": self.content,
            "stage_slug": self.stage_slug,
            "tags": list(self.tags),
            "file_paths": list(self.file_paths),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "KBEntry":
        return cls(
            entry_id=str(payload.get("entry_id") or uuid.uuid4()),
            created_at=str(payload.get("created_at") or _now()),
            run_id=str(payload.get("run_id") or ""),
            entry_type=str(payload.get("entry_type") or "note"),
            title=str(payload.get("title") or "Untitled entry"),
            summary=str(payload.get("summary") or ""),
            content=str(payload.get("content") or ""),
            stage_slug=str(payload["stage_slug"]) if payload.get("stage_slug") is not None else None,
            tags=[str(item) for item in payload.get("tags", []) if str(item).strip()],
            file_paths=[str(item) for item in payload.get("file_paths", []) if str(item).strip()],
        )


@dataclass(frozen=True)
class KBSearchResult:
    entry: KBEntry
    score: float


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _tokenize(text: str) -> set[str]:
    return set(TOKEN_PATTERN.findall(text.lower()))


def initialize_knowledge_base(paths: RunPaths, user_goal: str) -> None:
    if paths.knowledge_base_entries.exists() and paths.knowledge_base_entries.read_text(encoding="utf-8").strip():
        return

    write_kb_entry(
        paths,
        entry_type="user_goal",
        title="Original user goal",
        summary=truncate_text(user_goal, max_chars=240),
        content=user_goal,
        tags=["goal", "run"],
    )


def load_kb_entries(entries_path: Path) -> list[KBEntry]:
    if not entries_path.exists():
        return []

    entries: list[KBEntry] = []
    for line in entries_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        entries.append(KBEntry.from_dict(json.loads(stripped)))
    return entries


def append_kb_entry(entries_path: Path, entry: KBEntry) -> None:
    entries_path.parent.mkdir(parents=True, exist_ok=True)
    with entries_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry.to_dict(), ensure_ascii=True) + "\n")


def write_kb_entry(
    paths: RunPaths,
    *,
    entry_type: str,
    title: str,
    summary: str,
    content: str,
    stage: StageSpec | None = None,
    tags: list[str] | None = None,
    file_paths: list[str] | None = None,
) -> KBEntry:
    entry = KBEntry(
        entry_id=str(uuid.uuid4()),
        created_at=_now(),
        run_id=paths.run_root.name,
        entry_type=entry_type,
        title=title.strip(),
        summary=summary.strip(),
        content=content.strip(),
        stage_slug=stage.slug if stage else None,
        tags=[tag.strip() for tag in (tags or []) if tag.strip()],
        file_paths=[path.strip() for path in (file_paths or []) if path.strip()],
    )
    append_kb_entry(paths.knowledge_base_entries, entry)
    return entry


def search_knowledge_base(
    entries_path: Path,
    query: str,
    limit: int = 5,
    stage: StageSpec | None = None,
) -> list[KBSearchResult]:
    entries = load_kb_entries(entries_path)
    if not entries:
        return []

    query_text = query.strip().lower()
    query_tokens = _tokenize(query_text)
    semantic_matches = SemanticIndexer().rank(
        query_text,
        [
            " ".join(
                [
                    entry.title,
                    entry.summary,
                    entry.content,
                    entry.entry_type,
                    entry.stage_slug or "",
                    " ".join(entry.tags),
                    " ".join(entry.file_paths),
                ]
            )
            for entry in entries
        ],
        limit=max(limit * 3, 12),
    )
    semantic_scores = {match.index: match.score for match in semantic_matches}
    scored: list[KBSearchResult] = []

    for index, entry in enumerate(entries):
        haystack = " ".join(
            [
                entry.title,
                entry.summary,
                entry.content,
                entry.entry_type,
                entry.stage_slug or "",
                " ".join(entry.tags),
                " ".join(entry.file_paths),
            ]
        ).lower()
        haystack_tokens = _tokenize(haystack)

        score = 0.0
        if query_text and query_text in haystack:
            score += 4.0

        overlap = query_tokens & haystack_tokens
        if query_tokens:
            score += 2.0 * len(overlap)
            score += len(overlap) / len(query_tokens)

        score += semantic_scores.get(index, 0.0) * 6.0

        if stage and entry.stage_slug == stage.slug:
            score += 1.5
        elif stage and entry.stage_slug is None:
            score += 0.2

        if entry.entry_type in {"stage_approved", "stage_validated"}:
            score += 0.5

        if score <= 0:
            continue

        scored.append(KBSearchResult(entry=entry, score=score))

    scored.sort(key=lambda result: (result.score, result.entry.created_at), reverse=True)
    return scored[:limit]


def format_kb_context(results: list[KBSearchResult]) -> str:
    if not results:
        return "No relevant knowledge-base entries yet."

    blocks: list[str] = []
    for index, result in enumerate(results, start=1):
        entry = result.entry
        stage_label = entry.stage_slug or "global"
        lines = [
            f"{index}. [{entry.entry_type}] {entry.title}",
            f"   Stage: {stage_label}",
            f"   Summary: {truncate_text(entry.summary or entry.content, max_chars=280)}",
        ]
        if entry.file_paths:
            lines.append("   Files: " + ", ".join(f"`{path}`" for path in entry.file_paths[:6]))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def format_kb_search_results(results: list[KBSearchResult]) -> str:
    if not results:
        return "No matching knowledge-base entries."

    lines: list[str] = []
    for result in results:
        entry = result.entry
        lines.append(
            (
                f"- [{entry.entry_type}] {entry.title} | stage={entry.stage_slug or 'global'} "
                f"| score={result.score:.2f} | created_at={entry.created_at}\n"
                f"  {truncate_text(entry.summary or entry.content, max_chars=280)}"
            )
        )
    return "\n".join(lines)
