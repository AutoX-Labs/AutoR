from __future__ import annotations

from dataclasses import dataclass, field


PIPELINE_STAGES = (
    "literature_survey",
    "hypothesis_generation",
    "study_design",
    "implementation",
    "experimentation",
    "analysis",
    "writing",
    "dissemination",
)

PipelineStage = str


@dataclass(frozen=True)
class Citation:
    title: str
    source: str
    identifier: str = ""


@dataclass(frozen=True)
class ProvenanceRecord:
    agent_name: str
    action: str
    evidence: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass(frozen=True)
class ResearchTask:
    task_id: str
    title: str
    goal: str
    pipeline_stage: PipelineStage
    project_id: str
    kb_context: list[str] = field(default_factory=list)
    human_gate_required: bool = True
    citations: list[Citation] = field(default_factory=list)
    reproducibility_notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TaskResult:
    task_id: str
    output: str
    artifacts: list[str] = field(default_factory=list)
    provenance: list[ProvenanceRecord] = field(default_factory=list)

