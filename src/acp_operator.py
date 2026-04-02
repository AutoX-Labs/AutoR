"""ACP-based operator that communicates via JSON-RPC 2.0.

Replaces subprocess invocation of ``claude -p`` with structured
JSON-RPC requests to an ACP agent server.
"""
from __future__ import annotations

import sys
import uuid
from typing import Any, Callable, TextIO

from .acp_types import (
    CompletionEvent,
    ErrorEvent,
    ProgressEvent,
    TaskCreateParams,
    TaskCreateResult,
    TaskQueryResult,
    TaskState,
    ToolCallEvent,
)
from .operator_protocol import OperatorProtocol
from .terminal_ui import TerminalUI
from .utils import (
    DEFAULT_REFINEMENT_SUGGESTIONS,
    FIXED_STAGE_OPTIONS,
    OperatorResult,
    RunPaths,
    StageSpec,
    append_jsonl,
    read_text,
    write_text,
)


class ACPOperator(OperatorProtocol):
    """Operator that uses ACP protocol for Claude API communication."""

    def __init__(
        self,
        model: str = "sonnet",
        output_stream: TextIO = sys.stdout,
        ui: TerminalUI | None = None,
        server_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.model = model
        self.output_stream = output_stream
        self.ui = ui or TerminalUI(output_stream=output_stream)
        self._server_factory = server_factory
        self._server: Any | None = None

    def _get_server(self) -> Any:
        if self._server is None:
            if self._server_factory is None:
                raise RuntimeError(
                    "No ACP server factory provided. "
                    "Pass server_factory to ACPOperator or use --operator cli."
                )
            self._server = self._server_factory()
        return self._server

    def run_stage(
        self,
        stage: StageSpec,
        prompt: str,
        paths: RunPaths,
        attempt_no: int,
        continue_session: bool = False,
    ) -> OperatorResult:
        prompt_path = paths.prompt_cache_dir / f"{stage.slug}_attempt_{attempt_no:02d}.prompt.md"
        write_text(prompt_path, prompt)

        session_id = self._resolve_session_id(paths, stage, continue_session)
        stage_file = paths.stage_tmp_file(stage)

        params = TaskCreateParams(
            prompt=prompt,
            model=self.model,
            workspace=str(paths.workspace_root.resolve()),
            stage_slug=stage.slug,
            stage_output_path=str(stage_file.resolve()),
            session_id=session_id,
        )

        append_jsonl(
            paths.logs_raw,
            {
                "_meta": {
                    "stage": stage.slug,
                    "attempt": attempt_no,
                    "mode": "acp_continue" if continue_session else "acp_start",
                    "params": params.to_dict(),
                }
            },
        )

        try:
            server = self._get_server()
            create_result: TaskCreateResult = server.handle_request(
                "acp.task.create", params
            )
        except Exception as exc:
            append_jsonl(
                paths.logs_raw,
                {"_meta": {"stage": stage.slug, "attempt": attempt_no, "error": str(exc)}},
            )
            return OperatorResult(
                success=False,
                exit_code=1,
                stdout="",
                stderr=str(exc),
                stage_file_path=stage_file,
                session_id=session_id,
            )

        effective_session_id = create_result.session_id
        self._persist_session_id(paths, stage, effective_session_id)

        # Stream events from server
        stdout_fragments: list[str] = []
        for event in server.stream_events(create_result.task_id):
            self._handle_event(event, paths, stage, attempt_no, stdout_fragments)

        # Query final state
        try:
            query_result: TaskQueryResult = server.handle_request(
                "acp.task.query", create_result.task_id
            )
        except Exception:
            query_result = TaskQueryResult(
                task_id=create_result.task_id,
                state=TaskState.FAILED,
            )

        success = query_result.state == TaskState.COMPLETED and stage_file.exists()
        stdout_text = "\n".join(stdout_fragments).strip()

        append_jsonl(
            paths.logs_raw,
            {
                "_meta": {
                    "stage": stage.slug,
                    "attempt": attempt_no,
                    "mode": "acp_result",
                    "state": query_result.state.value,
                    "tokens_used": query_result.tokens_used,
                    "session_id": effective_session_id,
                    "success": success,
                }
            },
        )

        return OperatorResult(
            success=success,
            exit_code=0 if success else 1,
            stdout=stdout_text,
            stderr=query_result.error_message or "",
            stage_file_path=stage_file,
            session_id=effective_session_id,
        )

    def repair_stage_summary(
        self,
        stage: StageSpec,
        original_prompt: str,
        original_result: OperatorResult,
        paths: RunPaths,
        attempt_no: int,
    ) -> OperatorResult:
        stage_file = paths.stage_tmp_file(stage)
        current_draft = read_text(stage_file) if stage_file.exists() else "(missing)"
        current_final_path = paths.stage_file(stage)
        current_final = read_text(current_final_path) if current_final_path.exists() else "(missing)"

        repair_prompt = (
            f"You are performing failure recovery for {stage.stage_title}.\n\n"
            f"Overwrite the stage summary file at: {stage_file}\n\n"
            "Rules:\n"
            "- Do not browse the web.\n"
            "- Use only the information already available.\n"
            "- Produce a valid markdown file in the required format.\n"
            "- Do not write placeholder or in-progress content.\n\n"
            "Required markdown structure:\n"
            f"# Stage {stage.number:02d}: {stage.display_name}\n"
            "## Objective\n## Previously Approved Stage Summaries\n"
            "## What I Did\n## Key Results\n## Files Produced\n"
            "## Suggestions for Refinement\n"
            f"1. {DEFAULT_REFINEMENT_SUGGESTIONS[0]}\n"
            f"2. {DEFAULT_REFINEMENT_SUGGESTIONS[1]}\n"
            f"3. {DEFAULT_REFINEMENT_SUGGESTIONS[2]}\n"
            "## Your Options\n"
            + "\n".join(FIXED_STAGE_OPTIONS)
            + f"\n\nCurrent draft:\n{current_draft}\n\n"
            f"Current final:\n{current_final}\n\n"
            f"Original prompt:\n{original_prompt}\n\n"
            f"Original stdout:\n{original_result.stdout or '(empty)'}\n"
        )

        return self.run_stage(
            stage=stage,
            prompt=repair_prompt,
            paths=paths,
            attempt_no=attempt_no,
            continue_session=True,
        )

    def _handle_event(
        self,
        event: Any,
        paths: RunPaths,
        stage: StageSpec,
        attempt_no: int,
        stdout_fragments: list[str],
    ) -> None:
        if isinstance(event, ProgressEvent):
            append_jsonl(paths.logs_raw, {
                "_meta": {"stage": stage.slug, "attempt": attempt_no, "event": "progress"},
                **event.to_dict(),
            })
            self.ui.show_status(
                f"Tokens: {event.tokens_used:,} | Elapsed: {event.elapsed_seconds:.1f}s",
                level="info",
            )
        elif isinstance(event, ToolCallEvent):
            append_jsonl(paths.logs_raw, {
                "_meta": {"stage": stage.slug, "attempt": attempt_no, "event": "tool_call"},
                **event.to_dict(),
            })
            self.ui.show_status(
                f"[{event.tool_name}] {event.status}",
                level="info" if event.status != "failed" else "warn",
            )
        elif isinstance(event, ErrorEvent):
            append_jsonl(paths.logs_raw, {
                "_meta": {"stage": stage.slug, "attempt": attempt_no, "event": "error"},
                **event.to_dict(),
            })
            self.ui.show_status(f"Error: {event.message}", level="error")
        elif isinstance(event, CompletionEvent):
            append_jsonl(paths.logs_raw, {
                "_meta": {"stage": stage.slug, "attempt": attempt_no, "event": "completion"},
                **event.to_dict(),
            })
            level = "success" if event.state == TaskState.COMPLETED else "error"
            self.ui.show_status(
                f"Task {event.state.value} | Tokens: {event.tokens_used:,} | Session: {event.session_id or 'unknown'}",
                level=level,
            )
            stdout_fragments.append(
                f"Task completed: {event.state.value}, tokens: {event.tokens_used}"
            )

    def _resolve_session_id(
        self,
        paths: RunPaths,
        stage: StageSpec,
        continue_session: bool,
    ) -> str:
        if continue_session:
            session_file = paths.stage_session_file(stage)
            if session_file.exists():
                existing = read_text(session_file).strip()
                if existing:
                    return existing
        return str(uuid.uuid4())

    def _persist_session_id(
        self,
        paths: RunPaths,
        stage: StageSpec,
        session_id: str,
    ) -> None:
        write_text(paths.stage_session_file(stage), session_id)
