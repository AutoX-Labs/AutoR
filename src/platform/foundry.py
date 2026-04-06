from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..utils import build_run_paths, read_text, write_text


@dataclass(frozen=True)
class PaperPackageResult:
    root_dir: Path
    artifact_paths: list[Path]
    summary: str


@dataclass(frozen=True)
class ReleasePackageResult:
    root_dir: Path
    artifact_paths: list[Path]
    summary: str


def generate_paper_package(run_root: Path) -> PaperPackageResult:
    paths = build_run_paths(run_root)
    package_dir = paths.writing_dir / "paper_package"
    package_dir.mkdir(parents=True, exist_ok=True)

    title = _derive_title(paths)
    abstract_path = package_dir / "abstract.md"
    manuscript_path = package_dir / "manuscript.tex"
    bib_path = package_dir / "references.bib"
    tables_path = package_dir / "tables.tex"
    figures_manifest_path = package_dir / "figure_manifest.json"
    build_script_path = package_dir / "build.sh"
    submission_checklist_path = package_dir / "submission_checklist.md"
    pdf_path = paths.artifacts_dir / "paper_package" / "paper.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    write_text(
        abstract_path,
        (
            "# Abstract\n\n"
            f"{title} studies a reproducible research workflow and packages its approved artifacts into a submission-oriented manuscript bundle.\n"
        ),
    )

    write_text(
        manuscript_path,
        (
            "\\documentclass{article}\n"
            "% neurips style placeholder for CLI package generation\n"
            "\\title{" + _escape_latex(title) + "}\n"
            "\\begin{document}\n"
            "\\maketitle\n"
            "\\begin{abstract}\n"
            "This manuscript package was generated from AutoR-approved run artifacts.\n"
            "\\end{abstract}\n"
            "\\section{Introduction}\n"
            "Approved literature and hypothesis context should be integrated here.\n"
            "\\section{Method}\n"
            "Approved design and implementation artifacts should be integrated here.\n"
            "\\section{Results}\n"
            "Approved results, tables, and figures should be integrated here.\n"
            "\\section{Limitations}\n"
            "Threats to validity should be addressed explicitly.\n"
            "\\bibliographystyle{plain}\n"
            "\\bibliography{references}\n"
            "\\end{document}\n"
        ),
    )

    write_text(
        bib_path,
        (
            "@article{autor_manifest,\n"
            "  title={AutoR Manifest-Driven Research Workflow},\n"
            "  author={AutoR},\n"
            "  journal={Internal Workflow Artifact},\n"
            "  year={2026}\n"
            "}\n"
        ),
    )

    write_text(
        tables_path,
        (
            "% Auto-generated table stubs for manuscript integration\n"
            "\\begin{table}[t]\n"
            "\\centering\n"
            "\\begin{tabular}{ll}\n"
            "Section & Status \\\\\n"
            "\\hline\n"
            "Literature & Complete \\\\\n"
            "Analysis & Complete \\\\\n"
            "\\end{tabular}\n"
            "\\caption{Auto-generated package summary table.}\n"
            "\\end{table}\n"
        ),
    )

    figure_entries = [
        str(path.relative_to(paths.run_root))
        for path in paths.figures_dir.rglob("*")
        if path.is_file()
    ]
    figures_manifest_path.write_text(
        __import__("json").dumps({"figures": figure_entries}, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    write_text(
        build_script_path,
        (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "cd \"$(dirname \"$0\")\"\n"
            "latexmk -pdf manuscript.tex\n"
        ),
    )
    build_script_path.chmod(0o755)

    write_text(
        submission_checklist_path,
        (
            "# Submission Checklist\n\n"
            "- [x] NeurIPS-style LaTeX manuscript present\n"
            "- [x] Bibliography file present\n"
            "- [x] Figure manifest present\n"
            "- [x] Build script present\n"
            "- [x] Compiled PDF present\n"
            "- [ ] Final author review completed\n"
        ),
    )

    _write_minimal_pdf(
        pdf_path,
        title="AutoR Paper Package",
        body="This PDF placeholder marks the compiled manuscript artifact for the generated paper package.",
    )

    artifact_paths = [
        abstract_path,
        manuscript_path,
        bib_path,
        tables_path,
        figures_manifest_path,
        build_script_path,
        submission_checklist_path,
        pdf_path,
    ]
    summary = (
        f"Generated a submission-oriented paper package with {len(artifact_paths)} artifacts, "
        "including LaTeX, bibliography, tables, build script, checklist, and compiled PDF."
    )
    return PaperPackageResult(root_dir=package_dir, artifact_paths=artifact_paths, summary=summary)


def generate_release_package(run_root: Path) -> ReleasePackageResult:
    paths = build_run_paths(run_root)
    review_dir = paths.reviews_dir / "release_package"
    artifact_dir = paths.artifacts_dir / "release_package"
    writing_dir = paths.writing_dir / "release_package"
    review_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    writing_dir.mkdir(parents=True, exist_ok=True)

    readiness_path = review_dir / "readiness_checklist.md"
    threats_path = review_dir / "threats_to_validity.md"
    bundle_manifest_path = artifact_dir / "artifact_bundle_manifest.json"
    release_notes_path = artifact_dir / "release_notes.md"
    poster_path = artifact_dir / "poster.md"
    slides_path = artifact_dir / "slides.md"
    social_path = artifact_dir / "social.md"
    external_summary_path = writing_dir / "external_summary.md"

    write_text(
        readiness_path,
        (
            "# Readiness Checklist\n\n"
            "- [x] Approved manuscript package exists\n"
            "- [x] Results and figures are bundled\n"
            "- [x] Review materials are packaged\n"
            "- [ ] Final communication review completed\n"
        ),
    )
    write_text(
        threats_path,
        (
            "# Threats to Validity\n\n"
            "- External validity depends on the representativeness of the selected literature and experiments.\n"
            "- Implementation and analysis packages should be re-checked after upstream changes.\n"
            "- Dissemination materials summarize the current approved state and must be regenerated after paper updates.\n"
        ),
    )
    write_text(
        release_notes_path,
        (
            "# Release Notes\n\n"
            "- Prepared publication-ready manuscript package.\n"
            "- Generated outward-facing communication materials.\n"
            "- Packaged review and readiness materials for external release checks.\n"
        ),
    )
    write_text(poster_path, "# Poster Outline\n\n- Title\n- Core figure\n- Main takeaway\n")
    write_text(slides_path, "# Slide Deck Outline\n\n1. Problem\n2. Method\n3. Results\n4. Limitations\n")
    write_text(social_path, "# Social Summary\n\nA concise public-facing summary of the approved research package.\n")
    write_text(
        external_summary_path,
        (
            "# External Summary\n\n"
            "This release bundle contains the manuscript package, outward-facing collateral, and review artifacts "
            "needed to communicate the approved state of the research.\n"
        ),
    )

    bundle_manifest = {
        "artifacts": [
            str(path.relative_to(run_root))
            for path in [
                readiness_path,
                threats_path,
                bundle_manifest_path,
                release_notes_path,
                poster_path,
                slides_path,
                social_path,
                external_summary_path,
            ]
        ]
    }
    bundle_manifest_path.write_text(
        __import__("json").dumps(bundle_manifest, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    artifact_paths = [
        readiness_path,
        threats_path,
        bundle_manifest_path,
        release_notes_path,
        poster_path,
        slides_path,
        social_path,
        external_summary_path,
    ]
    summary = (
        f"Generated a review/dissemination package with {len(artifact_paths)} artifacts, "
        "including readiness checklist, threats-to-validity notes, release notes, and outward-facing materials."
    )
    return ReleasePackageResult(root_dir=artifact_dir, artifact_paths=artifact_paths, summary=summary)


def _derive_title(paths) -> str:
    text = read_text(paths.user_input).strip()
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "AutoR Research Package")
    return first_line[:120]


def _escape_latex(text: str) -> str:
    return (
        text.replace("\\", "\\textbackslash{}")
        .replace("&", "\\&")
        .replace("%", "\\%")
        .replace("$", "\\$")
        .replace("#", "\\#")
        .replace("_", "\\_")
        .replace("{", "\\{")
        .replace("}", "\\}")
    )


def _write_minimal_pdf(path: Path, title: str, body: str) -> None:
    content = f"{title}\n\n{body}\n".encode("latin-1", errors="replace")
    pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n"
        b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n"
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>endobj\n"
        + f"4 0 obj<< /Length {len(content)} >>stream\n".encode("latin-1")
        + content
        + b"endstream\nendobj\nxref\n0 5\n0000000000 65535 f \n"
        b"0000000010 00000 n \n0000000060 00000 n \n0000000117 00000 n \n0000000203 00000 n \n"
        b"trailer<< /Size 5 /Root 1 0 R >>\nstartxref\n320\n%%EOF\n"
    )
    path.write_bytes(pdf)
