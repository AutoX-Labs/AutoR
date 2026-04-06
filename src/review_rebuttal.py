"""Simulated peer review and rebuttal generation for AutoR.

Post-hook that runs after Stage 07 (Writing) to simulate multi-reviewer
peer review, produce a meta-review, and generate an author rebuttal.
All artifacts are written to workspace/reviews/.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

from .utils import RunPaths, append_log_entry

# ---------------------------------------------------------------------------
# Review JSON schema (aligned with NeurIPS / AI-Scientist-v2 format)
# ---------------------------------------------------------------------------

REVIEW_FIELDS = [
    "Summary",
    "Strengths",
    "Weaknesses",
    "Originality",
    "Quality",
    "Clarity",
    "Significance",
    "Questions",
    "Limitations",
    "Soundness",
    "Presentation",
    "Contribution",
    "Overall",
    "Confidence",
    "Decision",
]

REVIEW_FORM = """\
## Review Form (NeurIPS Style)

Provide your review in **JSON** format with exactly these fields:

- "Summary": A 3-5 sentence summary of the paper and its contributions.
- "Strengths": A list of specific strengths (at least 3 items).
- "Weaknesses": A list of specific weaknesses (at least 3 items).
- "Originality": Integer 1-4 (1=low, 4=very high).
- "Quality": Integer 1-4 (1=low, 4=very high).
- "Clarity": Integer 1-4 (1=low, 4=very high).
- "Significance": Integer 1-4 (1=low, 4=very high).
- "Questions": A list of clarifying questions for the authors.
- "Limitations": A list of limitations and potential negative societal impacts.
- "Soundness": Integer 1-4 (1=poor, 4=excellent).
- "Presentation": Integer 1-4 (1=poor, 4=excellent).
- "Contribution": Integer 1-4 (1=poor, 4=excellent).
- "Overall": Integer 1-10 (1=very strong reject, 10=award quality).
- "Confidence": Integer 1-5 (1=low, 5=absolute).
- "Decision": Exactly one of "Accept" or "Reject".

Output ONLY the JSON object. No extra text before or after.
"""

# ---------------------------------------------------------------------------
# Three reviewer personas with different biases
# ---------------------------------------------------------------------------

REVIEWER_CONFIGS = [
    {
        "id": "R1",
        "name": "Reviewer 1 (Rigorous Theorist)",
        "system": (
            "You are a senior ML researcher reviewing a paper submitted to a top venue. "
            "You are rigorous and critical. You focus on theoretical soundness, novelty "
            "of contributions, and whether claims are well-supported by evidence. "
            "If you are uncertain about the quality, lean toward rejection. "
            "Be specific — cite exact sections, equations, or claims when pointing out issues."
        ),
    },
    {
        "id": "R2",
        "name": "Reviewer 2 (Empirical Methodologist)",
        "system": (
            "You are an experienced ML researcher reviewing a paper submitted to a top venue. "
            "You focus on experimental methodology: baseline comparisons, ablation studies, "
            "statistical significance, reproducibility, and dataset choices. "
            "You are fair but demanding about empirical rigor. "
            "Point out missing experiments or unfair comparisons specifically."
        ),
    },
    {
        "id": "R3",
        "name": "Reviewer 3 (Balanced Generalist)",
        "system": (
            "You are a well-rounded ML researcher reviewing a paper submitted to a top venue. "
            "You provide balanced, constructive feedback covering clarity, presentation, "
            "significance, and overall contribution to the field. "
            "Acknowledge genuine strengths while identifying concrete areas for improvement. "
            "Be constructive — suggest how weaknesses could be addressed."
        ),
    },
]

META_REVIEW_SYSTEM = (
    "You are an Area Chair at a top ML conference. You are responsible for "
    "synthesizing multiple reviewer opinions into a coherent meta-review "
    "and making a final recommendation."
)

REBUTTAL_SYSTEM = (
    "You are the author of the reviewed paper. You are writing a professional, "
    "point-by-point rebuttal to address reviewer concerns. Be respectful, "
    "precise, and evidence-based. Acknowledge valid criticisms honestly."
)


# ---------------------------------------------------------------------------
# Paper text collection
# ---------------------------------------------------------------------------

def _collect_paper_text(paths: RunPaths) -> str:
    """Read LaTeX source files from workspace/writing/ and combine."""
    writing_dir = paths.writing_dir
    parts: list[str] = []

    main_tex = writing_dir / "main.tex"
    if main_tex.exists():
        parts.append(f"% === main.tex ===\n{main_tex.read_text(encoding='utf-8')}")

    sections_dir = writing_dir / "sections"
    if sections_dir.is_dir():
        for tex_file in sorted(sections_dir.glob("*.tex")):
            parts.append(f"% === sections/{tex_file.name} ===\n{tex_file.read_text(encoding='utf-8')}")

    bib_file = writing_dir / "references.bib"
    if bib_file.exists():
        bib_text = bib_file.read_text(encoding="utf-8")
        # Truncate bibliography to avoid overwhelming the reviewer
        if len(bib_text) > 3000:
            bib_text = bib_text[:3000] + "\n% ... (bibliography truncated) ...\n"
        parts.append(f"% === references.bib ===\n{bib_text}")

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Claude CLI invocation
# ---------------------------------------------------------------------------

def _call_claude(prompt: str, model: str = "sonnet", timeout: int = 600) -> str:
    """Call Claude CLI in print mode and return stdout."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8",
    ) as f:
        f.write(prompt)
        prompt_path = f.name

    try:
        result = subprocess.run(
            [
                "claude",
                "--model", model,
                "-p", f"@{prompt_path}",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Claude CLI failed (exit {result.returncode}): "
                f"{(result.stderr or result.stdout or '(no output)')[:500]}"
            )
        return result.stdout.strip()
    finally:
        Path(prompt_path).unlink(missing_ok=True)


def _extract_json(text: str) -> dict:
    """Extract JSON object from Claude's response, handling markdown fences."""
    # Try to find JSON in code fences first
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)

    # Find the first { ... } block
    brace_start = text.find("{")
    if brace_start < 0:
        raise ValueError("No JSON object found in response")

    depth = 0
    for i in range(brace_start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[brace_start : i + 1])

    raise ValueError("Unterminated JSON object in response")


# ---------------------------------------------------------------------------
# Individual review
# ---------------------------------------------------------------------------

def _run_single_review(
    paper_text: str,
    reviewer_config: dict,
    model: str,
) -> dict:
    """Run one reviewer and return structured review dict."""
    prompt = (
        f"{reviewer_config['system']}\n\n"
        f"{REVIEW_FORM}\n\n"
        f"## Paper to Review\n\n"
        f"{paper_text}\n"
    )

    raw = _call_claude(prompt, model=model)
    review = _extract_json(raw)

    # Validate required fields exist
    for field in REVIEW_FIELDS:
        if field not in review:
            review[field] = "N/A" if isinstance(review.get(field), str) else []

    review["_reviewer_id"] = reviewer_config["id"]
    review["_reviewer_name"] = reviewer_config["name"]
    return review


# ---------------------------------------------------------------------------
# Meta-review
# ---------------------------------------------------------------------------

def _run_meta_review(reviews: list[dict], model: str) -> dict:
    """Aggregate individual reviews into a meta-review."""
    reviews_text = ""
    for r in reviews:
        reviews_text += (
            f"### {r.get('_reviewer_name', 'Reviewer')}\n"
            f"- Overall: {r.get('Overall', 'N/A')}/10\n"
            f"- Decision: {r.get('Decision', 'N/A')}\n"
            f"- Confidence: {r.get('Confidence', 'N/A')}/5\n"
            f"- Summary: {r.get('Summary', 'N/A')}\n"
            f"- Strengths: {json.dumps(r.get('Strengths', []))}\n"
            f"- Weaknesses: {json.dumps(r.get('Weaknesses', []))}\n"
            f"- Questions: {json.dumps(r.get('Questions', []))}\n\n"
        )

    prompt = (
        f"{META_REVIEW_SYSTEM}\n\n"
        f"## Individual Reviews\n\n{reviews_text}\n"
        f"## Task\n\n"
        f"Write a meta-review that:\n"
        f"1. Summarizes the consensus view across reviewers.\n"
        f"2. Identifies the most critical weaknesses that authors must address.\n"
        f"3. Notes any significant disagreements between reviewers.\n"
        f"4. Makes a final recommendation.\n\n"
        f"Output JSON with these fields:\n"
        f'- "consensus_strengths": list of agreed-upon strengths\n'
        f'- "consensus_weaknesses": list of agreed-upon weaknesses\n'
        f'- "disagreements": list of points where reviewers disagree\n'
        f'- "critical_issues": list of issues that must be addressed\n'
        f'- "recommendation": one of "Accept", "Minor Revision", "Major Revision", "Reject"\n'
        f'- "meta_review_text": 2-3 paragraph narrative summary\n'
        f'- "average_overall": average of reviewer Overall scores (float)\n\n'
        f"Output ONLY the JSON object."
    )

    raw = _call_claude(prompt, model=model)
    meta = _extract_json(raw)

    # Compute average score
    scores = [r.get("Overall", 5) for r in reviews if isinstance(r.get("Overall"), (int, float))]
    if scores:
        meta["average_overall"] = round(sum(scores) / len(scores), 1)

    return meta


# ---------------------------------------------------------------------------
# Rebuttal generation
# ---------------------------------------------------------------------------

def _generate_rebuttal(
    paper_text: str,
    reviews: list[dict],
    meta_review: dict,
    model: str,
) -> str:
    """Generate a point-by-point author rebuttal in markdown."""
    reviews_text = ""
    for r in reviews:
        rid = r.get("_reviewer_id", "R?")
        reviews_text += f"### {r.get('_reviewer_name', rid)}\n"
        reviews_text += f"**Weaknesses:**\n"
        for i, w in enumerate(r.get("Weaknesses", []), 1):
            reviews_text += f"  {rid}-W{i}: {w}\n"
        reviews_text += f"**Questions:**\n"
        for i, q in enumerate(r.get("Questions", []), 1):
            reviews_text += f"  {rid}-Q{i}: {q}\n"
        reviews_text += "\n"

    critical = meta_review.get("critical_issues", [])
    critical_text = "\n".join(f"- {issue}" for issue in critical) if critical else "(none)"

    prompt = (
        f"{REBUTTAL_SYSTEM}\n\n"
        f"## Meta-Review Summary\n"
        f"Recommendation: {meta_review.get('recommendation', 'N/A')}\n"
        f"Average Score: {meta_review.get('average_overall', 'N/A')}/10\n\n"
        f"Critical issues to address:\n{critical_text}\n\n"
        f"## Reviewer Comments\n\n{reviews_text}\n"
        f"## Paper (for reference)\n\n{paper_text[:8000]}\n\n"
        f"## Task\n\n"
        f"Write a point-by-point rebuttal in markdown. For each weakness and question:\n"
        f"1. Quote the reviewer concern (use > blockquote).\n"
        f"2. Provide a specific response.\n"
        f"3. If a paper revision is warranted, note what would change.\n\n"
        f"Organize by reviewer. Be professional, concise, and evidence-based.\n"
        f"Start critical issues first, then address remaining points.\n"
        f"Output the rebuttal in markdown format."
    )

    return _call_claude(prompt, model=model)


# ---------------------------------------------------------------------------
# Main hook entry point
# ---------------------------------------------------------------------------

def run_review_rebuttal_hook(
    paths: RunPaths,
    model: str = "sonnet",
) -> dict | None:
    """Run the full review-rebuttal pipeline after Stage 07.

    Returns a summary dict or None on failure.
    """
    reviews_dir = paths.reviews_dir
    reviews_dir.mkdir(parents=True, exist_ok=True)

    # 1. Collect paper text
    paper_text = _collect_paper_text(paths)
    if len(paper_text.strip()) < 200:
        print("[review_rebuttal] Paper text too short, skipping review.")
        return None

    # 2. Run 3 independent reviewers
    reviews: list[dict] = []
    for config in REVIEWER_CONFIGS:
        print(f"[review_rebuttal] Running {config['name']}...")
        try:
            review = _run_single_review(paper_text, config, model)
            reviews.append(review)

            review_path = reviews_dir / f"review_{config['id'].lower()}.json"
            review_path.write_text(
                json.dumps(review, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(
                f"[review_rebuttal] {config['name']}: "
                f"Overall={review.get('Overall', '?')}/10, "
                f"Decision={review.get('Decision', '?')}"
            )
        except Exception as exc:
            print(f"[review_rebuttal] {config['name']} failed: {exc}")
            append_log_entry(
                paths.logs,
                f"review_rebuttal_{config['id']}_error",
                str(exc),
            )

    if len(reviews) < 2:
        print("[review_rebuttal] Fewer than 2 reviews succeeded, skipping meta-review.")
        return None

    # 3. Meta-review
    print("[review_rebuttal] Generating meta-review...")
    try:
        meta_review = _run_meta_review(reviews, model)
        meta_path = reviews_dir / "meta_review.json"
        meta_path.write_text(
            json.dumps(meta_review, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(
            f"[review_rebuttal] Meta-review: "
            f"Recommendation={meta_review.get('recommendation', '?')}, "
            f"Avg={meta_review.get('average_overall', '?')}/10"
        )
    except Exception as exc:
        print(f"[review_rebuttal] Meta-review failed: {exc}")
        append_log_entry(paths.logs, "review_rebuttal_meta_error", str(exc))
        meta_review = {
            "recommendation": "N/A",
            "critical_issues": [],
            "meta_review_text": "Meta-review generation failed.",
        }

    # 4. Author rebuttal
    print("[review_rebuttal] Generating author rebuttal...")
    try:
        rebuttal_md = _generate_rebuttal(paper_text, reviews, meta_review, model)
        rebuttal_path = reviews_dir / "rebuttal.md"
        rebuttal_path.write_text(rebuttal_md, encoding="utf-8")
        print(f"[review_rebuttal] Rebuttal saved to {rebuttal_path}")
    except Exception as exc:
        print(f"[review_rebuttal] Rebuttal generation failed: {exc}")
        append_log_entry(paths.logs, "review_rebuttal_rebuttal_error", str(exc))
        rebuttal_md = ""

    # 5. Summary
    summary = {
        "num_reviews": len(reviews),
        "reviewer_scores": [
            {"id": r.get("_reviewer_id"), "overall": r.get("Overall"), "decision": r.get("Decision")}
            for r in reviews
        ],
        "recommendation": meta_review.get("recommendation", "N/A"),
        "average_overall": meta_review.get("average_overall"),
        "critical_issues": meta_review.get("critical_issues", []),
        "rebuttal_generated": bool(rebuttal_md),
    }

    summary_path = reviews_dir / "review_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    append_log_entry(
        paths.logs,
        "review_rebuttal_complete",
        json.dumps(summary, indent=2),
    )

    return summary
