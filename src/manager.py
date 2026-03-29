from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import TextIO

from .knowledge_base import (
    format_kb_context,
    format_kb_search_results,
    initialize_knowledge_base,
    search_knowledge_base,
    write_kb_entry,
)
from .operator import ClaudeOperator
from .platform.fault_tolerance import CheckpointManager
from .platform.observability import ObservabilityCollector
from .platform.orchestration import HierarchicalPattern, ParallelPattern, SequentialPattern, SwarmPattern
from .platform.types import PipelineStage, ProvenanceRecord, ResearchTask, TaskResult
from .run_state import (
    ensure_run_state,
    format_run_state,
    initialize_run_state,
    load_run_state,
    mark_run_cancelled,
    mark_run_completed,
    mark_run_failed,
    mark_stage_approved,
    mark_stage_human_review,
    mark_stage_running,
)
from .utils import (
    STAGES,
    RunPaths,
    StageSpec,
    append_approved_stage_summary,
    append_log_entry,
    build_continuation_prompt,
    build_prompt,
    build_run_paths,
    canonicalize_stage_markdown,
    create_run_root,
    ensure_run_layout,
    extract_markdown_section,
    extract_path_references,
    format_stage_template,
    initialize_memory,
    load_prompt_template,
    parse_refinement_suggestions,
    read_text,
    truncate_text,
    validate_stage_artifacts,
    validate_stage_markdown,
    write_text,
)


class ResearchManager:
    def __init__(
        self,
        project_root: Path,
        runs_dir: Path,
        operator: ClaudeOperator,
        output_stream: TextIO = sys.stdout,
    ) -> None:
        self.project_root = project_root
        self.runs_dir = runs_dir
        self.operator = operator
        self.prompt_dir = self.project_root / "src" / "prompts"
        self.output_stream = output_stream

    def run(self, user_goal: str) -> bool:
        paths = self.create_run_paths(user_goal)
        self._print(f"Run created at: {paths.run_root}")
        return self.execute_run_paths(paths)

    def resume_run(self, run_root: Path, start_stage: StageSpec | None = None) -> bool:
        paths = build_run_paths(run_root)
        ensure_run_layout(paths)
        if not paths.user_input.exists():
            raise FileNotFoundError(f"Missing user_input.txt in run: {run_root}")
        if not paths.memory.exists():
            raise FileNotFoundError(f"Missing memory.md in run: {run_root}")

        initialize_knowledge_base(paths, read_text(paths.user_input))
        ensure_run_state(paths)

        append_log_entry(
            paths.logs,
            "run_resume",
            f"Resumed run at: {paths.run_root}"
            + (f"\nRequested start stage: {start_stage.stage_title}" if start_stage else ""),
        )
        self._print(f"Resuming run at: {paths.run_root}")
        if start_stage:
            self._print(f"Restarting from: {start_stage.stage_title}")
        return self.execute_run_paths(paths, start_stage=start_stage, failure_title="Run failed during resume", failure_tags=["failure", "run", "resume"])

    def create_run_paths(self, user_goal: str) -> RunPaths:
        return self._create_run(user_goal)

    def execute_run_paths(
        self,
        paths: RunPaths,
        start_stage: StageSpec | None = None,
        failure_title: str = "Run failed",
        failure_tags: list[str] | None = None,
    ) -> bool:
        try:
            return self._run_from_paths(paths, start_stage=start_stage)
        except Exception as exc:
            mark_run_failed(paths, error=str(exc), stage=start_stage)
            write_kb_entry(
                paths,
                entry_type="run_failed",
                title=failure_title,
                summary=str(exc),
                content=f"{failure_title} with error:\n{exc}",
                stage=start_stage,
                tags=failure_tags or ["failure", "run"],
            )
            raise

    def _run_from_paths(self, paths: RunPaths, start_stage: StageSpec | None = None) -> bool:
        stages_to_run = self._select_stages_for_run(paths, start_stage)

        for stage in stages_to_run:
            approved = self._run_stage(paths, stage)
            if not approved:
                append_log_entry(
                    paths.logs,
                    "run_aborted",
                    f"Run aborted during {stage.stage_title}.",
                )
                mark_run_cancelled(paths, stage=stage)
                write_kb_entry(
                    paths,
                    entry_type="run_cancelled",
                    title="Run aborted by user",
                    summary=f"Run aborted during {stage.stage_title}.",
                    content=f"The run was aborted while working in {stage.stage_title}.",
                    stage=stage,
                    tags=["run", "cancelled"],
                )
                self._print("Run aborted.")
                return False

        append_log_entry(paths.logs, "run_complete", "All stages approved.")
        mark_run_completed(paths)
        write_kb_entry(
            paths,
            entry_type="run_completed",
            title="Run completed",
            summary="All stages were approved.",
            content="The run completed successfully after approval of all eight stages.",
            tags=["run", "completed"],
        )
        self._print("All stages approved. Run complete.")
        return True

    def _create_run(self, user_goal: str) -> RunPaths:
        run_root = create_run_root(self.runs_dir)
        paths = build_run_paths(run_root)
        ensure_run_layout(paths)
        write_text(paths.user_input, user_goal)
        initialize_memory(paths, user_goal)
        initialize_knowledge_base(paths, user_goal)
        initialize_run_state(paths)
        append_log_entry(paths.logs, "run_start", f"Run root: {paths.run_root}")
        return paths

    def _select_stages_for_run(
        self,
        paths: RunPaths,
        start_stage: StageSpec | None,
    ) -> list[StageSpec]:
        if start_stage is not None:
            return [stage for stage in STAGES if stage.number >= start_stage.number]

        approved_memory = read_text(paths.memory)
        pending: list[StageSpec] = []
        for stage in STAGES:
            final_stage_path = paths.stage_file(stage)
            if final_stage_path.exists() and stage.stage_title in approved_memory:
                continue
            pending.append(stage)

        return pending

    def _run_stage(self, paths: RunPaths, stage: StageSpec) -> bool:
        attempt_no = 1
        revision_feedback: str | None = None
        continue_session = False

        while True:
            orchestration_summary = self._execute_stage_orchestration(paths, stage, attempt_no)
            mark_stage_running(paths, stage, attempt_no)
            write_kb_entry(
                paths,
                entry_type="stage_attempt_started",
                title=f"{stage.stage_title} attempt {attempt_no} started",
                summary=(
                    f"Started {stage.stage_title} attempt {attempt_no} using the "
                    f"{stage.orchestration_pattern} stage pattern."
                ),
                content=(
                    f"Attempt {attempt_no} for {stage.stage_title} started.\n\n"
                    f"{stage.pattern_summary}\n\n"
                    f"Planned subtasks: {orchestration_summary['subtask_count']}"
                ),
                stage=stage,
                tags=["stage", "attempt", "running", stage.slug],
            )
            self._print(f"\nRunning {stage.stage_title} (attempt {attempt_no})...")
            prompt = self._build_stage_prompt(paths, stage, revision_feedback, continue_session)
            append_log_entry(
                paths.logs,
                f"{stage.slug} attempt {attempt_no} prompt",
                prompt,
            )

            result = self.operator.run_stage(
                stage,
                prompt,
                paths,
                attempt_no,
                continue_session=continue_session,
            )
            append_log_entry(
                paths.logs,
                f"{stage.slug} attempt {attempt_no} result",
                (
                    f"success: {result.success}\n"
                    f"exit_code: {result.exit_code}\n"
                    f"session_id: {result.session_id or '(unknown)'}\n"
                    f"stage_file_path: {result.stage_file_path}\n"
                    f"final_stage_file_path: {paths.stage_file(stage)}\n\n"
                    "stdout:\n"
                    f"{result.stdout or '(empty)'}\n\n"
                    "stderr:\n"
                    f"{result.stderr or '(empty)'}"
                ),
            )

            if not result.stage_file_path.exists():
                self._print(
                    f"Stage summary draft missing for {stage.stage_title}. Running repair attempt..."
                )
                append_log_entry(
                    paths.logs,
                    f"{stage.slug} attempt {attempt_no} repair_triggered",
                    "Primary attempt did not produce stage summary draft. Triggering repair pass.",
                )
                repair_result = self.operator.repair_stage_summary(
                    stage=stage,
                    original_prompt=prompt,
                    original_result=result,
                    paths=paths,
                    attempt_no=attempt_no,
                )
                append_log_entry(
                    paths.logs,
                    f"{stage.slug} attempt {attempt_no} repair_result",
                    (
                        f"success: {repair_result.success}\n"
                        f"exit_code: {repair_result.exit_code}\n"
                        f"stage_file_path: {repair_result.stage_file_path}\n\n"
                        "stdout:\n"
                        f"{repair_result.stdout or '(empty)'}\n\n"
                        "stderr:\n"
                        f"{repair_result.stderr or '(empty)'}"
                    ),
                )
                result = repair_result

            if not result.stage_file_path.exists():
                raise RuntimeError(
                    f"Stage summary draft was not generated for {stage.slug}: {result.stage_file_path}"
                )

            stage_markdown = read_text(result.stage_file_path)
            validation_errors = validate_stage_markdown(stage_markdown) + validate_stage_artifacts(stage, paths)
            if validation_errors:
                self._print(
                    f"Stage summary for {stage.stage_title} was incomplete. Running repair attempt..."
                )
                append_log_entry(
                    paths.logs,
                    f"{stage.slug} attempt {attempt_no} validation_failed",
                    "\n".join(validation_errors),
                )
                write_kb_entry(
                    paths,
                    entry_type="stage_validation_failed",
                    title=f"{stage.stage_title} validation failed",
                    summary=validation_errors[0],
                    content="\n".join(validation_errors),
                    stage=stage,
                    tags=["stage", "validation_failed", stage.slug],
                )
                repair_result = self.operator.repair_stage_summary(
                    stage=stage,
                    original_prompt=prompt,
                    original_result=result,
                    paths=paths,
                    attempt_no=attempt_no,
                )
                append_log_entry(
                    paths.logs,
                    f"{stage.slug} attempt {attempt_no} repair_result",
                    (
                        f"success: {repair_result.success}\n"
                        f"exit_code: {repair_result.exit_code}\n"
                        f"stage_file_path: {repair_result.stage_file_path}\n\n"
                        "stdout:\n"
                        f"{repair_result.stdout or '(empty)'}\n\n"
                        "stderr:\n"
                        f"{repair_result.stderr or '(empty)'}"
                    ),
                )

                if not repair_result.stage_file_path.exists():
                    raise RuntimeError(
                        f"Stage summary repair failed for {stage.slug}: {repair_result.stage_file_path}"
                    )

                stage_markdown = read_text(repair_result.stage_file_path)
                validation_errors = validate_stage_markdown(stage_markdown) + validate_stage_artifacts(stage, paths)
                if validation_errors:
                    self._print(
                        f"Repair output for {stage.stage_title} is still incomplete. Normalizing locally..."
                    )
                    normalized_markdown = canonicalize_stage_markdown(
                        stage=stage,
                        memory_text=read_text(paths.memory),
                        markdown=stage_markdown,
                        fallback_text="\n\n".join(
                            part for part in [result.stdout, result.stderr, repair_result.stdout, repair_result.stderr] if part
                        ),
                    )
                    write_text(repair_result.stage_file_path, normalized_markdown)
                    append_log_entry(
                        paths.logs,
                        f"{stage.slug} attempt {attempt_no} local_normalization",
                        (
                            "Applied local stage markdown normalization after repair remained invalid.\n\n"
                            "Previous validation errors:\n"
                            + "\n".join(f"- {problem}" for problem in validation_errors)
                            + "\n\nNormalized markdown preview:\n"
                            + truncate_text(normalized_markdown, max_chars=6000)
                        ),
                    )
                    write_kb_entry(
                        paths,
                        entry_type="stage_local_normalization",
                        title=f"{stage.stage_title} normalized locally",
                        summary="Applied local stage summary normalization after repair remained invalid.",
                        content=truncate_text(normalized_markdown, max_chars=6000),
                        stage=stage,
                        file_paths=[str(repair_result.stage_file_path.relative_to(paths.run_root))],
                        tags=["stage", "normalization", stage.slug],
                    )

                    stage_markdown = read_text(repair_result.stage_file_path)
                    validation_errors = validate_stage_markdown(stage_markdown) + validate_stage_artifacts(stage, paths)
                    if validation_errors:
                        append_log_entry(
                            paths.logs,
                            f"{stage.slug} attempt {attempt_no} local_normalization_failed",
                            (
                                "Local normalization remained invalid. Re-running current stage from scratch.\n\n"
                                + "\n".join(f"- {problem}" for problem in validation_errors)
                            ),
                        )
                        self._print(
                            f"Local normalization for {stage.stage_title} is still incomplete. Re-running the stage..."
                        )
                        revision_feedback = (
                            "Continue the current stage conversation and fix the invalid stage summary. "
                            "Keep all correct work already completed, but produce a fully complete stage summary "
                            "with no placeholder markers and ensure every required section is substantively filled."
                        )
                        continue_session = True
                        attempt_no += 1
                        continue

                result = repair_result

            final_stage_path = paths.stage_file(stage)
            shutil.copyfile(result.stage_file_path, final_stage_path)
            append_log_entry(
                paths.logs,
                f"{stage.slug} attempt {attempt_no} promoted",
                (
                    "Promoted validated stage summary draft to final stage file.\n"
                    f"draft: {result.stage_file_path}\n"
                    f"final: {final_stage_path}"
                ),
            )
            stage_markdown = read_text(final_stage_path)
            mark_stage_human_review(paths, stage, attempt_no)
            write_kb_entry(
                paths,
                entry_type="stage_validated",
                title=f"{stage.stage_title} ready for human review",
                summary=(extract_markdown_section(stage_markdown, "Key Results") or "Validated stage summary.").strip(),
                content=truncate_text(stage_markdown, max_chars=8000),
                stage=stage,
                file_paths=self._stage_file_paths(paths, stage, stage_markdown),
                tags=["stage", "validated", "human_review", stage.slug],
            )

            self._display_stage_output(stage, stage_markdown)
            choice = self._ask_choice()
            custom_feedback: str | None = None
            append_log_entry(
                paths.logs,
                f"{stage.slug} attempt {attempt_no} user_choice",
                f"choice: {choice}",
            )

            if choice in {"1", "2", "3"}:
                suggestions = parse_refinement_suggestions(stage_markdown)
                selected = suggestions[int(choice) - 1]
                revision_feedback = (
                    "Continue the current stage conversation and improve the existing work. "
                    "Do not discard correct completed parts. Address this refinement request:\n"
                    f"{selected}"
                )
                write_kb_entry(
                    paths,
                    entry_type="stage_revision_requested",
                    title=f"{stage.stage_title} revision requested",
                    summary=selected,
                    content=f"Revision requested via built-in suggestion {choice}.\n\n{selected}",
                    stage=stage,
                    tags=["stage", "revision", "human_feedback", stage.slug],
                )
                continue_session = True
                attempt_no += 1
                continue

            if choice == "4":
                custom_feedback = self._read_multiline_feedback()
                revision_feedback = (
                    "Continue the current stage conversation and improve the existing work. "
                    "Preserve correct completed parts unless the feedback requires changing them. "
                    "Address this user feedback:\n"
                    f"{custom_feedback}"
                )
                append_log_entry(
                    paths.logs,
                    f"{stage.slug} attempt {attempt_no} custom_feedback",
                    custom_feedback,
                )
                write_kb_entry(
                    paths,
                    entry_type="stage_revision_requested",
                    title=f"{stage.stage_title} custom feedback",
                    summary=truncate_text(custom_feedback, max_chars=240),
                    content=custom_feedback,
                    stage=stage,
                    tags=["stage", "revision", "human_feedback", stage.slug],
                )
                continue_session = True
                attempt_no += 1
                continue

            if choice == "5":
                append_approved_stage_summary(paths.memory, stage, stage_markdown)
                mark_stage_approved(paths, stage)
                append_log_entry(
                    paths.logs,
                    f"{stage.slug} approved",
                    "Stage approved and appended to memory.",
                )
                write_kb_entry(
                    paths,
                    entry_type="stage_approved",
                    title=f"{stage.stage_title} approved",
                    summary=(extract_markdown_section(stage_markdown, "Key Results") or "Stage approved.").strip(),
                    content=truncate_text(stage_markdown, max_chars=8000),
                    stage=stage,
                    file_paths=self._stage_file_paths(paths, stage, stage_markdown),
                    tags=["stage", "approved", stage.slug],
                )
                self._print(f"Approved {stage.stage_title}.")
                return True

            if choice == "6":
                mark_run_cancelled(paths, stage=stage)
                write_kb_entry(
                    paths,
                    entry_type="stage_aborted",
                    title=f"{stage.stage_title} aborted by user",
                    summary=f"User aborted during {stage.stage_title}.",
                    content=truncate_text(stage_markdown, max_chars=4000),
                    stage=stage,
                    file_paths=self._stage_file_paths(paths, stage, stage_markdown),
                    tags=["stage", "aborted", stage.slug],
                )
                return False

    def _build_stage_prompt(
        self,
        paths: RunPaths,
        stage: StageSpec,
        revision_feedback: str | None,
        continue_session: bool,
    ) -> str:
        template = load_prompt_template(self.prompt_dir, stage)
        stage_template = format_stage_template(template, stage, paths)
        kb_context = self._build_kb_context(paths, stage)
        if continue_session:
            return build_continuation_prompt(stage, stage_template, paths, kb_context, revision_feedback)

        user_request = read_text(paths.user_input)
        approved_memory = read_text(paths.memory)
        return build_prompt(stage, stage_template, user_request, approved_memory, kb_context, revision_feedback)

    def _display_stage_output(self, stage: StageSpec, markdown: str) -> None:
        divider = "=" * 80
        self._print(f"\n{divider}")
        self._print(stage.stage_title)
        self._print(divider)
        self._print(markdown.rstrip())
        self._print(divider)

    def _ask_choice(self) -> str:
        valid = {"1", "2", "3", "4", "5", "6"}
        while True:
            choice = input("Enter your choice:\n> ").strip()
            if choice in valid:
                return choice
            self._print("Invalid choice. Enter one of: 1, 2, 3, 4, 5, 6.")

    def _read_multiline_feedback(self) -> str:
        self._print("Enter custom feedback. Finish with an empty line:")
        lines: list[str] = []

        while True:
            prompt = "> " if not lines else ""
            line = input(prompt)
            if not line.strip():
                if lines:
                    break
                self._print("Feedback cannot be empty.")
                continue
            lines.append(line.rstrip())

        return "\n".join(lines).strip()

    def _print(self, text: str) -> None:
        print(text, file=self.output_stream)

    def _execute_stage_orchestration(self, paths: RunPaths, stage: StageSpec, attempt_no: int) -> dict[str, object]:
        subtasks = self._build_stage_subtasks(paths, stage, attempt_no)
        runner = self._orchestration_runner()
        pattern_name = stage.orchestration_pattern.lower()
        if "parallel" in pattern_name and "+" in pattern_name:
            pattern = SequentialPattern()
            results = pattern.execute(subtasks, runner)
        elif "parallel" in pattern_name:
            results = ParallelPattern(max_workers=min(len(subtasks), 4)).execute(subtasks, runner)
        elif "hierarchical" in pattern_name:
            results = HierarchicalPattern().execute(subtasks[0], planner=lambda _root: subtasks, runner=runner)
        elif "swarm" in pattern_name:
            results = SwarmPattern(rounds=2).execute(subtasks, runner)
        else:
            results = SequentialPattern().execute(subtasks, runner)

        summary = {
            "stage_slug": stage.slug,
            "attempt_no": attempt_no,
            "pattern": stage.orchestration_pattern,
            "subtask_count": len(subtasks),
            "subtasks": [
                {
                    "task_id": task.task_id,
                    "title": task.title,
                    "goal": task.goal,
                }
                for task in subtasks
            ],
            "results": [
                {
                    "task_id": result.task_id,
                    "output": result.output,
                    "provenance": [record.action for record in result.provenance],
                }
                for result in results
            ],
        }

        plan_path = paths.notes_dir / f"{stage.slug}_attempt_{attempt_no:02d}_orchestration.json"
        write_text(plan_path, json.dumps(summary, indent=2, ensure_ascii=True))
        CheckpointManager(paths.control_dir / f"{stage.slug}_attempt_{attempt_no:02d}_checkpoint.json").save(summary)
        collector = ObservabilityCollector(paths.run_root)
        collector.emit_span(
            "stage.orchestration.executed",
            run_id=paths.run_root.name,
            stage_slug=stage.slug,
            attempt_no=attempt_no,
            pattern=stage.orchestration_pattern,
        )
        collector.emit_metric(
            "autor.orchestration.subtask_count",
            float(len(subtasks)),
            run_id=paths.run_root.name,
            stage_slug=stage.slug,
        )
        return summary

    def _build_stage_subtasks(self, paths: RunPaths, stage: StageSpec, attempt_no: int) -> list[ResearchTask]:
        stage_key: PipelineStage = stage.slug[3:]
        project_id = paths.run_root.name
        goal = read_text(paths.user_input).strip()

        subtask_titles: dict[str, list[str]] = {
            "01_literature_survey": ["Search sources", "Extract evidence", "Merge survey map"],
            "02_hypothesis_generation": ["Propose hypotheses", "Critique hypotheses", "Synthesize direction"],
            "03_study_design": ["Plan protocol", "Define variables", "Set evaluation criteria"],
            "04_implementation": ["Prepare environment", "Implement pipeline", "Validate execution"],
            "05_experimentation": ["Set experiment plan", "Run experiments", "Aggregate checkpoints"],
            "06_analysis": ["Compute statistics", "Generate visuals", "Interpret findings"],
            "07_writing": ["Outline manuscript", "Draft sections", "Check consistency"],
            "08_dissemination": ["Draft poster", "Draft slides", "Draft social summary"],
        }

        tasks: list[ResearchTask] = []
        for index, title in enumerate(subtask_titles.get(stage.slug, [stage.display_name]), start=1):
            tasks.append(
                ResearchTask(
                    task_id=f"{stage.slug}-attempt-{attempt_no:02d}-task-{index:02d}",
                    title=title,
                    goal=f"{goal}\n\nStage focus: {stage.stage_title}\nSubtask: {title}",
                    pipeline_stage=stage_key,
                    project_id=project_id,
                    kb_context=[paths.run_root.name, stage.slug],
                    human_gate_required=False,
                    reproducibility_notes=[f"Attempt {attempt_no}", stage.orchestration_pattern],
                )
            )
        return tasks

    def _orchestration_runner(self) -> callable:
        def _run(task: ResearchTask) -> TaskResult:
            return TaskResult(
                task_id=task.task_id,
                output=f"Completed orchestration subtask: {task.title}",
                provenance=[
                    ProvenanceRecord(
                        agent_name="AutoROrchestrator",
                        action=f"planned:{task.title}",
                        evidence=[task.pipeline_stage, task.project_id],
                    )
                ],
            )

        return _run

    def _build_kb_context(self, paths: RunPaths, stage: StageSpec) -> str:
        user_request = read_text(paths.user_input)
        query = f"{stage.display_name} {stage.slug} {user_request}"
        results = search_knowledge_base(
            paths.knowledge_base_entries,
            query=query,
            limit=6,
            stage=stage,
        )
        return format_kb_context(results)

    def _stage_file_paths(self, paths: RunPaths, stage: StageSpec, stage_markdown: str) -> list[str]:
        file_paths = extract_path_references(stage_markdown)
        final_stage_path = str(paths.stage_file(stage).relative_to(paths.run_root))
        if final_stage_path not in file_paths:
            file_paths.insert(0, final_stage_path)
        return file_paths[:16]

    def describe_run_status(self, run_root: Path) -> str:
        paths = build_run_paths(run_root)
        ensure_run_layout(paths)
        ensure_run_state(paths)
        state = load_run_state(paths.run_state)
        if state is None:
            raise RuntimeError(f"Could not load run state from {paths.run_state}")
        return format_run_state(state)

    def search_run_knowledge_base(self, run_root: Path, query: str, limit: int = 5) -> str:
        paths = build_run_paths(run_root)
        ensure_run_layout(paths)
        initialize_knowledge_base(paths, read_text(paths.user_input))
        results = search_knowledge_base(paths.knowledge_base_entries, query=query, limit=limit)
        return format_kb_search_results(results)
