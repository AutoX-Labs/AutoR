# AutoR ACP Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `claude -p` subprocess coupling in AutoR with a JSON-RPC 2.0 + ACP protocol layer, enabling structured observability, timeout control, and programmatic error handling, while keeping the CLI operator as fallback.

**Architecture:** Introduce an `OperatorProtocol` ABC that both the existing `ClaudeOperator` (CLI) and new `ACPOperator` implement. The ACP operator communicates with an in-process ACP agent server via JSON-RPC 2.0 over stdio pipes. The server wraps the Anthropic Python SDK for direct API calls, emitting structured events for tool calls, progress, and errors.

**Tech Stack:** Python 3.10+ stdlib, `anthropic` Python SDK (new dependency), JSON-RPC 2.0 (custom minimal implementation)

**PR Strategy:** Each task below maps to one PR. PRs are submitted from sub-branches off `ziyan/acp-refactor` into `main`. Each PR is independently reviewable and mergeable.

---

## PR / Branch Strategy

```
main
  └── ziyan/acp-refactor (tracking branch, stays in sync with main)
        ├── ziyan/acp-pr1-operator-protocol   --> PR #1 to main
        ├── ziyan/acp-pr2-jsonrpc-transport    --> PR #2 to main (after PR1 merged)
        ├── ziyan/acp-pr3-acp-types            --> PR #3 to main (after PR2 merged)
        ├── ziyan/acp-pr4-acp-operator         --> PR #4 to main (after PR3 merged)
        ├── ziyan/acp-pr5-acp-server           --> PR #5 to main (after PR4 merged)
        └── ziyan/acp-pr6-integration          --> PR #6 to main (after PR5 merged)
```

每个 PR 独立可合入，不破坏现有功能。合入顺序是线性的。

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `src/operator_protocol.py` | `OperatorProtocol` ABC + `OperatorEvent` types for structured events |
| `src/jsonrpc.py` | Minimal JSON-RPC 2.0 request/response/error/notification encoding |
| `src/acp_types.py` | ACP message types: TaskCreate, TaskQuery, TaskCancel, events |
| `src/acp_operator.py` | `ACPOperator` implementing `OperatorProtocol` via JSON-RPC client |
| `src/acp_server.py` | ACP agent server wrapping Anthropic SDK |
| `tests/test_jsonrpc.py` | JSON-RPC 2.0 protocol tests |
| `tests/test_acp_types.py` | ACP type serialization tests |
| `tests/test_acp_operator.py` | ACP operator tests with mock server |

### Modified Files

| File | Change |
|------|--------|
| `src/operator.py` | `ClaudeOperator` implements `OperatorProtocol`; no logic change |
| `src/manager.py` | Type hint operator as `OperatorProtocol` instead of `ClaudeOperator` |
| `main.py` | Add `--operator` flag (`cli` / `acp`), construct appropriate operator |
| `src/terminal_ui.py` | Add `show_operator_event()` for structured ACP events |

### Unchanged Files

| File | Why |
|------|-----|
| `src/prompts/*.md` | Prompt templates are transport-agnostic |
| `src/utils.py` | Data models, validation logic untouched |
| `src/writing_manifest.py` | Artifact scanning untouched |
| `templates/registry.yaml` | Venue metadata untouched |

---

## Task 1: Operator Protocol ABC (PR #1)

**Branch:** `ziyan/acp-pr1-operator-protocol`

**Goal:** Extract the implicit operator interface into an explicit `OperatorProtocol` ABC. Make `ClaudeOperator` implement it. Make `ResearchManager` depend on the ABC, not the concrete class. Zero behavior change.

**Files:**
- Create: `src/operator_protocol.py`
- Modify: `src/operator.py`
- Modify: `src/manager.py`
- Create: `tests/test_operator_protocol.py`

- [ ] **Step 1: Write the failing test for OperatorProtocol**

```python
# tests/test_operator_protocol.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.operator_protocol import OperatorProtocol
from src.utils import OperatorResult, RunPaths, StageSpec


class FakeProtocolOperator(OperatorProtocol):
    """Minimal concrete implementation for testing the protocol."""

    def run_stage(
        self,
        stage: StageSpec,
        prompt: str,
        paths: RunPaths,
        attempt_no: int,
        continue_session: bool = False,
    ) -> OperatorResult:
        return OperatorResult(
            success=True,
            exit_code=0,
            stdout="fake",
            stderr="",
            stage_file_path=paths.stage_tmp_file(stage),
            session_id="fake-session",
        )

    def repair_stage_summary(
        self,
        stage: StageSpec,
        original_prompt: str,
        original_result: OperatorResult,
        paths: RunPaths,
        attempt_no: int,
    ) -> OperatorResult:
        return OperatorResult(
            success=True,
            exit_code=0,
            stdout="repaired",
            stderr="",
            stage_file_path=paths.stage_tmp_file(stage),
            session_id="fake-session",
        )


def test_fake_operator_satisfies_protocol():
    op = FakeProtocolOperator()
    assert isinstance(op, OperatorProtocol)


def test_protocol_cannot_be_instantiated_directly():
    import pytest
    with pytest.raises(TypeError):
        OperatorProtocol()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/zychen/USTC\&PJLab/Lab/AutoR && python -m pytest tests/test_operator_protocol.py -v`
Expected: FAIL — `src.operator_protocol` does not exist

- [ ] **Step 3: Create OperatorProtocol ABC**

```python
# src/operator_protocol.py
from __future__ import annotations

from abc import ABC, abstractmethod

from .utils import OperatorResult, RunPaths, StageSpec


class OperatorProtocol(ABC):
    """Abstract base class defining the operator interface.

    Both ClaudeOperator (CLI subprocess) and ACPOperator (JSON-RPC)
    implement this protocol. ResearchManager depends only on this ABC.
    """

    @abstractmethod
    def run_stage(
        self,
        stage: StageSpec,
        prompt: str,
        paths: RunPaths,
        attempt_no: int,
        continue_session: bool = False,
    ) -> OperatorResult:
        """Execute a stage and return the result."""

    @abstractmethod
    def repair_stage_summary(
        self,
        stage: StageSpec,
        original_prompt: str,
        original_result: OperatorResult,
        paths: RunPaths,
        attempt_no: int,
    ) -> OperatorResult:
        """Attempt to repair a missing or invalid stage summary."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /c/zychen/USTC\&PJLab/Lab/AutoR && python -m pytest tests/test_operator_protocol.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Make ClaudeOperator inherit from OperatorProtocol**

In `src/operator.py`, add the import and change the class declaration:

```python
# Add to imports at top:
from .operator_protocol import OperatorProtocol

# Change class declaration:
class ClaudeOperator(OperatorProtocol):
    # ... everything else unchanged
```

- [ ] **Step 6: Write test verifying ClaudeOperator satisfies protocol**

Append to `tests/test_operator_protocol.py`:

```python
def test_claude_operator_satisfies_protocol():
    from src.operator import ClaudeOperator
    op = ClaudeOperator(fake_mode=True)
    assert isinstance(op, OperatorProtocol)
```

- [ ] **Step 7: Run all tests to verify nothing broke**

Run: `cd /c/zychen/USTC\&PJLab/Lab/AutoR && python -m pytest tests/ -v`
Expected: All existing tests + new tests PASS

- [ ] **Step 8: Update ResearchManager type hint**

In `src/manager.py`, change the import and type annotation:

```python
# Add to imports:
from .operator_protocol import OperatorProtocol

# In __init__, change type:
class ResearchManager:
    def __init__(
        self,
        project_root: Path,
        runs_dir: Path,
        operator: OperatorProtocol,  # was: ClaudeOperator
        output_stream: TextIO = sys.stdout,
        ui: TerminalUI | None = None,
    ) -> None:
        ...
        self.operator = operator
```

Remove the `ClaudeOperator` import from `src/manager.py` since it's no longer referenced there.

- [ ] **Step 9: Run all tests again**

Run: `cd /c/zychen/USTC\&PJLab/Lab/AutoR && python -m pytest tests/ -v`
Expected: All PASS. No behavior change.

- [ ] **Step 10: Commit**

```bash
git checkout -b ziyan/acp-pr1-operator-protocol ziyan/acp-refactor
git add src/operator_protocol.py src/operator.py src/manager.py tests/test_operator_protocol.py
git commit -m "refactor: extract OperatorProtocol ABC from ClaudeOperator

Introduce an explicit abstract base class for the operator interface.
ClaudeOperator now inherits from OperatorProtocol. ResearchManager
depends on the ABC, not the concrete class. This enables adding
alternative operator implementations (ACP) without modifying the manager.

No behavior change."
```

---

## Task 2: JSON-RPC 2.0 Transport Layer (PR #2)

**Branch:** `ziyan/acp-pr2-jsonrpc-transport`

**Goal:** Implement a minimal, zero-dependency JSON-RPC 2.0 codec. This is pure protocol encoding/decoding with no I/O.

**Files:**
- Create: `src/jsonrpc.py`
- Create: `tests/test_jsonrpc.py`

- [ ] **Step 1: Write the failing tests for JSON-RPC encoding**

```python
# tests/test_jsonrpc.py
from __future__ import annotations

import json
import pytest

from src.jsonrpc import (
    JsonRpcRequest,
    JsonRpcResponse,
    JsonRpcError,
    JsonRpcNotification,
    ErrorCode,
    encode_request,
    encode_response,
    encode_error_response,
    encode_notification,
    decode_message,
)


class TestEncodeRequest:
    def test_request_with_params(self):
        msg = encode_request("acp.task.create", {"prompt": "hello"}, id=1)
        parsed = json.loads(msg)
        assert parsed == {
            "jsonrpc": "2.0",
            "method": "acp.task.create",
            "params": {"prompt": "hello"},
            "id": 1,
        }

    def test_request_without_params(self):
        msg = encode_request("acp.task.list", id=2)
        parsed = json.loads(msg)
        assert parsed["method"] == "acp.task.list"
        assert "params" not in parsed
        assert parsed["id"] == 2

    def test_request_with_string_id(self):
        msg = encode_request("test", id="abc-123")
        parsed = json.loads(msg)
        assert parsed["id"] == "abc-123"


class TestEncodeResponse:
    def test_success_response(self):
        msg = encode_response({"task_id": "t1", "status": "running"}, id=1)
        parsed = json.loads(msg)
        assert parsed == {
            "jsonrpc": "2.0",
            "result": {"task_id": "t1", "status": "running"},
            "id": 1,
        }

    def test_error_response(self):
        msg = encode_error_response(
            code=ErrorCode.INTERNAL_ERROR,
            message="something failed",
            data={"detail": "stack trace"},
            id=1,
        )
        parsed = json.loads(msg)
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["error"]["code"] == -32603
        assert parsed["error"]["message"] == "something failed"
        assert parsed["error"]["data"] == {"detail": "stack trace"}
        assert parsed["id"] == 1


class TestEncodeNotification:
    def test_notification_has_no_id(self):
        msg = encode_notification("acp.event.progress", {"tokens": 100})
        parsed = json.loads(msg)
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["method"] == "acp.event.progress"
        assert parsed["params"] == {"tokens": 100}
        assert "id" not in parsed


class TestDecodeMessage:
    def test_decode_request(self):
        raw = '{"jsonrpc": "2.0", "method": "test", "params": {"x": 1}, "id": 5}'
        msg = decode_message(raw)
        assert isinstance(msg, JsonRpcRequest)
        assert msg.method == "test"
        assert msg.params == {"x": 1}
        assert msg.id == 5

    def test_decode_success_response(self):
        raw = '{"jsonrpc": "2.0", "result": {"ok": true}, "id": 5}'
        msg = decode_message(raw)
        assert isinstance(msg, JsonRpcResponse)
        assert msg.result == {"ok": True}
        assert msg.id == 5

    def test_decode_error_response(self):
        raw = '{"jsonrpc": "2.0", "error": {"code": -32600, "message": "bad"}, "id": 5}'
        msg = decode_message(raw)
        assert isinstance(msg, JsonRpcError)
        assert msg.code == -32600
        assert msg.message == "bad"
        assert msg.id == 5

    def test_decode_notification(self):
        raw = '{"jsonrpc": "2.0", "method": "event", "params": {"a": 1}}'
        msg = decode_message(raw)
        assert isinstance(msg, JsonRpcNotification)
        assert msg.method == "event"
        assert msg.params == {"a": 1}

    def test_decode_invalid_json(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            decode_message("not json")

    def test_decode_missing_jsonrpc_field(self):
        with pytest.raises(ValueError, match="jsonrpc"):
            decode_message('{"method": "test", "id": 1}')

    def test_decode_wrong_version(self):
        with pytest.raises(ValueError, match="2.0"):
            decode_message('{"jsonrpc": "1.0", "method": "test", "id": 1}')


class TestErrorCode:
    def test_standard_codes(self):
        assert ErrorCode.PARSE_ERROR == -32700
        assert ErrorCode.INVALID_REQUEST == -32600
        assert ErrorCode.METHOD_NOT_FOUND == -32601
        assert ErrorCode.INVALID_PARAMS == -32602
        assert ErrorCode.INTERNAL_ERROR == -32603

    def test_custom_acp_codes(self):
        assert ErrorCode.SESSION_NOT_FOUND == -32000
        assert ErrorCode.TOKEN_LIMIT_EXCEEDED == -32001
        assert ErrorCode.TOOL_EXECUTION_FAILED == -32002
        assert ErrorCode.TASK_CANCELLED == -32003
        assert ErrorCode.TIMEOUT == -32004
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/zychen/USTC\&PJLab/Lab/AutoR && python -m pytest tests/test_jsonrpc.py -v`
Expected: FAIL — `src.jsonrpc` does not exist

- [ ] **Step 3: Implement the JSON-RPC 2.0 codec**

```python
# src/jsonrpc.py
"""Minimal JSON-RPC 2.0 codec. No I/O — pure encode/decode."""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import IntEnum
from typing import Any


JSONRPC_VERSION = "2.0"


class ErrorCode(IntEnum):
    # Standard JSON-RPC 2.0 error codes
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # ACP-specific error codes (server error range: -32000 to -32099)
    SESSION_NOT_FOUND = -32000
    TOKEN_LIMIT_EXCEEDED = -32001
    TOOL_EXECUTION_FAILED = -32002
    TASK_CANCELLED = -32003
    TIMEOUT = -32004


@dataclass(frozen=True)
class JsonRpcRequest:
    method: str
    id: int | str
    params: dict[str, Any] | None = None


@dataclass(frozen=True)
class JsonRpcResponse:
    result: Any
    id: int | str


@dataclass(frozen=True)
class JsonRpcError:
    code: int
    message: str
    id: int | str | None
    data: Any = None


@dataclass(frozen=True)
class JsonRpcNotification:
    method: str
    params: dict[str, Any] | None = None


Message = JsonRpcRequest | JsonRpcResponse | JsonRpcError | JsonRpcNotification


def encode_request(
    method: str,
    params: dict[str, Any] | None = None,
    *,
    id: int | str,
) -> str:
    msg: dict[str, Any] = {"jsonrpc": JSONRPC_VERSION, "method": method, "id": id}
    if params is not None:
        msg["params"] = params
    return json.dumps(msg, ensure_ascii=True)


def encode_response(result: Any, *, id: int | str) -> str:
    return json.dumps(
        {"jsonrpc": JSONRPC_VERSION, "result": result, "id": id},
        ensure_ascii=True,
    )


def encode_error_response(
    code: int,
    message: str,
    data: Any = None,
    *,
    id: int | str | None,
) -> str:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return json.dumps(
        {"jsonrpc": JSONRPC_VERSION, "error": error, "id": id},
        ensure_ascii=True,
    )


def encode_notification(method: str, params: dict[str, Any] | None = None) -> str:
    msg: dict[str, Any] = {"jsonrpc": JSONRPC_VERSION, "method": method}
    if params is not None:
        msg["params"] = params
    return json.dumps(msg, ensure_ascii=True)


def decode_message(raw: str) -> Message:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("JSON-RPC message must be an object")

    if data.get("jsonrpc") != JSONRPC_VERSION:
        raise ValueError(f"Expected jsonrpc version 2.0, got: {data.get('jsonrpc')!r}")

    # Error response
    if "error" in data:
        err = data["error"]
        return JsonRpcError(
            code=int(err.get("code", ErrorCode.INTERNAL_ERROR)),
            message=str(err.get("message", "")),
            id=data.get("id"),
            data=err.get("data"),
        )

    # Success response
    if "result" in data:
        return JsonRpcResponse(result=data["result"], id=data["id"])

    # Request or notification
    method = data.get("method")
    if not isinstance(method, str):
        raise ValueError("JSON-RPC request/notification must have a string 'method'")

    if "id" in data:
        return JsonRpcRequest(method=method, id=data["id"], params=data.get("params"))

    return JsonRpcNotification(method=method, params=data.get("params"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/zychen/USTC\&PJLab/Lab/AutoR && python -m pytest tests/test_jsonrpc.py -v`
Expected: All PASS

- [ ] **Step 5: Run all tests to verify nothing broke**

Run: `cd /c/zychen/USTC\&PJLab/Lab/AutoR && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git checkout -b ziyan/acp-pr2-jsonrpc-transport ziyan/acp-refactor
git add src/jsonrpc.py tests/test_jsonrpc.py
git commit -m "feat: add JSON-RPC 2.0 codec for ACP transport

Pure encode/decode module with no I/O. Implements:
- Request, Response, Error, Notification message types
- Standard JSON-RPC 2.0 error codes
- Custom ACP error codes (session_not_found, timeout, etc.)
- Bidirectional decode_message() for parsing any message type

Foundation for the ACP operator transport layer."
```

---

## Task 3: ACP Type Definitions (PR #3)

**Branch:** `ziyan/acp-pr3-acp-types`

**Goal:** Define the ACP message types that will be exchanged between the ACP operator (client) and ACP server. These are dataclasses that map to JSON-RPC method params/results.

**Files:**
- Create: `src/acp_types.py`
- Create: `tests/test_acp_types.py`

- [ ] **Step 1: Write the failing tests for ACP types**

```python
# tests/test_acp_types.py
from __future__ import annotations

import pytest

from src.acp_types import (
    TaskCreateParams,
    TaskCreateResult,
    TaskQueryResult,
    TaskCancelParams,
    TaskResumeParams,
    TaskState,
    ProgressEvent,
    ToolCallEvent,
    ErrorEvent,
    CompletionEvent,
)


class TestTaskCreateParams:
    def test_to_dict(self):
        params = TaskCreateParams(
            prompt="do research",
            model="sonnet",
            workspace="/tmp/workspace",
            stage_slug="05_experimentation",
            stage_output_path="/tmp/stages/05.tmp.md",
            timeout_seconds=1800,
            tools=["Read", "Write", "Bash"],
        )
        d = params.to_dict()
        assert d["prompt"] == "do research"
        assert d["model"] == "sonnet"
        assert d["timeout_seconds"] == 1800
        assert d["tools"] == ["Read", "Write", "Bash"]

    def test_from_dict(self):
        d = {
            "prompt": "hello",
            "model": "opus",
            "workspace": "/w",
            "stage_slug": "01_literature_survey",
            "stage_output_path": "/s/01.tmp.md",
        }
        params = TaskCreateParams.from_dict(d)
        assert params.prompt == "hello"
        assert params.model == "opus"
        assert params.timeout_seconds is None
        assert params.tools is None

    def test_required_fields(self):
        with pytest.raises(KeyError):
            TaskCreateParams.from_dict({"prompt": "hello"})


class TestTaskState:
    def test_valid_states(self):
        assert TaskState.PENDING == "pending"
        assert TaskState.RUNNING == "running"
        assert TaskState.COMPLETED == "completed"
        assert TaskState.FAILED == "failed"
        assert TaskState.CANCELLED == "cancelled"


class TestTaskQueryResult:
    def test_from_dict_running(self):
        d = {
            "task_id": "t1",
            "state": "running",
            "tokens_used": 5000,
        }
        r = TaskQueryResult.from_dict(d)
        assert r.task_id == "t1"
        assert r.state == TaskState.RUNNING
        assert r.tokens_used == 5000
        assert r.stage_output is None

    def test_from_dict_completed(self):
        d = {
            "task_id": "t1",
            "state": "completed",
            "tokens_used": 25000,
            "stage_output": "# Stage 05: Experimentation\n...",
            "session_id": "sess-abc",
        }
        r = TaskQueryResult.from_dict(d)
        assert r.state == TaskState.COMPLETED
        assert r.stage_output is not None
        assert r.session_id == "sess-abc"


class TestEvents:
    def test_progress_event_to_dict(self):
        e = ProgressEvent(
            task_id="t1",
            tokens_used=1200,
            elapsed_seconds=45.0,
        )
        d = e.to_dict()
        assert d["task_id"] == "t1"
        assert d["tokens_used"] == 1200
        assert d["elapsed_seconds"] == 45.0

    def test_tool_call_event_to_dict(self):
        e = ToolCallEvent(
            task_id="t1",
            tool_name="Bash",
            tool_input={"command": "python train.py"},
            status="running",
        )
        d = e.to_dict()
        assert d["tool_name"] == "Bash"

    def test_error_event_to_dict(self):
        e = ErrorEvent(
            task_id="t1",
            code="SESSION_NOT_FOUND",
            message="No session",
            recoverable=True,
        )
        d = e.to_dict()
        assert d["recoverable"] is True

    def test_completion_event_to_dict(self):
        e = CompletionEvent(
            task_id="t1",
            state=TaskState.COMPLETED,
            tokens_used=30000,
            session_id="sess-123",
        )
        d = e.to_dict()
        assert d["state"] == "completed"

    def test_progress_event_from_dict(self):
        d = {"task_id": "t1", "tokens_used": 500, "elapsed_seconds": 10.0}
        e = ProgressEvent.from_dict(d)
        assert e.tokens_used == 500
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/zychen/USTC\&PJLab/Lab/AutoR && python -m pytest tests/test_acp_types.py -v`
Expected: FAIL — `src.acp_types` does not exist

- [ ] **Step 3: Implement ACP types**

```python
# src/acp_types.py
"""ACP (Agent Communication Protocol) message types.

These dataclasses define the structured messages exchanged between the
ACPOperator (client) and the ACP agent server via JSON-RPC 2.0.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TaskState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# --- Request params ---


@dataclass(frozen=True)
class TaskCreateParams:
    prompt: str
    model: str
    workspace: str
    stage_slug: str
    stage_output_path: str
    timeout_seconds: int | None = None
    tools: list[str] | None = None
    session_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "prompt": self.prompt,
            "model": self.model,
            "workspace": self.workspace,
            "stage_slug": self.stage_slug,
            "stage_output_path": self.stage_output_path,
        }
        if self.timeout_seconds is not None:
            d["timeout_seconds"] = self.timeout_seconds
        if self.tools is not None:
            d["tools"] = self.tools
        if self.session_id is not None:
            d["session_id"] = self.session_id
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TaskCreateParams:
        return cls(
            prompt=d["prompt"],
            model=d["model"],
            workspace=d["workspace"],
            stage_slug=d["stage_slug"],
            stage_output_path=d["stage_output_path"],
            timeout_seconds=d.get("timeout_seconds"),
            tools=d.get("tools"),
            session_id=d.get("session_id"),
        )


@dataclass(frozen=True)
class TaskCancelParams:
    task_id: str
    reason: str = "user_request"

    def to_dict(self) -> dict[str, Any]:
        return {"task_id": self.task_id, "reason": self.reason}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TaskCancelParams:
        return cls(task_id=d["task_id"], reason=d.get("reason", "user_request"))


@dataclass(frozen=True)
class TaskResumeParams:
    task_id: str
    feedback: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"task_id": self.task_id}
        if self.feedback is not None:
            d["feedback"] = self.feedback
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TaskResumeParams:
        return cls(task_id=d["task_id"], feedback=d.get("feedback"))


# --- Response results ---


@dataclass(frozen=True)
class TaskCreateResult:
    task_id: str
    session_id: str

    def to_dict(self) -> dict[str, Any]:
        return {"task_id": self.task_id, "session_id": self.session_id}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TaskCreateResult:
        return cls(task_id=d["task_id"], session_id=d["session_id"])


@dataclass(frozen=True)
class TaskQueryResult:
    task_id: str
    state: TaskState
    tokens_used: int = 0
    stage_output: str | None = None
    session_id: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "task_id": self.task_id,
            "state": self.state.value,
            "tokens_used": self.tokens_used,
        }
        if self.stage_output is not None:
            d["stage_output"] = self.stage_output
        if self.session_id is not None:
            d["session_id"] = self.session_id
        if self.error_message is not None:
            d["error_message"] = self.error_message
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TaskQueryResult:
        return cls(
            task_id=d["task_id"],
            state=TaskState(d["state"]),
            tokens_used=d.get("tokens_used", 0),
            stage_output=d.get("stage_output"),
            session_id=d.get("session_id"),
            error_message=d.get("error_message"),
        )


# --- Streaming events (sent as JSON-RPC notifications) ---


@dataclass(frozen=True)
class ProgressEvent:
    task_id: str
    tokens_used: int
    elapsed_seconds: float
    files_modified: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "tokens_used": self.tokens_used,
            "elapsed_seconds": self.elapsed_seconds,
            "files_modified": self.files_modified,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProgressEvent:
        return cls(
            task_id=d["task_id"],
            tokens_used=d["tokens_used"],
            elapsed_seconds=d["elapsed_seconds"],
            files_modified=d.get("files_modified", []),
        )


@dataclass(frozen=True)
class ToolCallEvent:
    task_id: str
    tool_name: str
    tool_input: dict[str, Any]
    status: str  # "running", "completed", "failed"
    tool_output: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "task_id": self.task_id,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "status": self.status,
        }
        if self.tool_output is not None:
            d["tool_output"] = self.tool_output
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ToolCallEvent:
        return cls(
            task_id=d["task_id"],
            tool_name=d["tool_name"],
            tool_input=d["tool_input"],
            status=d["status"],
            tool_output=d.get("tool_output"),
        )


@dataclass(frozen=True)
class ErrorEvent:
    task_id: str
    code: str
    message: str
    recoverable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "code": self.code,
            "message": self.message,
            "recoverable": self.recoverable,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ErrorEvent:
        return cls(
            task_id=d["task_id"],
            code=d["code"],
            message=d["message"],
            recoverable=d.get("recoverable", False),
        )


@dataclass(frozen=True)
class CompletionEvent:
    task_id: str
    state: TaskState
    tokens_used: int
    session_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "task_id": self.task_id,
            "state": self.state.value,
            "tokens_used": self.tokens_used,
        }
        if self.session_id is not None:
            d["session_id"] = self.session_id
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CompletionEvent:
        return cls(
            task_id=d["task_id"],
            state=TaskState(d["state"]),
            tokens_used=d["tokens_used"],
            session_id=d.get("session_id"),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/zychen/USTC\&PJLab/Lab/AutoR && python -m pytest tests/test_acp_types.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git checkout -b ziyan/acp-pr3-acp-types ziyan/acp-refactor
git add src/acp_types.py tests/test_acp_types.py
git commit -m "feat: define ACP message types for operator communication

Add dataclasses for task lifecycle (create, query, cancel, resume)
and streaming events (progress, tool_call, error, completion).
All types support to_dict/from_dict for JSON-RPC serialization.

These types define the structured contract between the ACP operator
client and the ACP agent server."
```

---

## Task 4: ACP Operator Client (PR #4)

**Branch:** `ziyan/acp-pr4-acp-operator`

**Goal:** Implement `ACPOperator` that satisfies `OperatorProtocol`. Initially uses a mock/fake server for testing. The real server integration comes in Task 5.

**Files:**
- Create: `src/acp_operator.py`
- Create: `tests/test_acp_operator.py`
- Modify: `main.py` (add `--operator` flag)

- [ ] **Step 1: Write the failing test for ACPOperator**

```python
# tests/test_acp_operator.py
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.acp_operator import ACPOperator
from src.acp_types import (
    CompletionEvent,
    TaskCreateResult,
    TaskQueryResult,
    TaskState,
)
from src.jsonrpc import encode_notification, encode_response
from src.operator_protocol import OperatorProtocol
from src.utils import STAGES, build_run_paths, ensure_run_layout, write_text


def _make_run(tmp_path: Path) -> Path:
    """Create a minimal run directory for testing."""
    run_root = tmp_path / "test_run"
    paths = build_run_paths(run_root)
    ensure_run_layout(paths)
    write_text(paths.user_input, "test goal")
    write_text(paths.memory, "# Approved Run Memory\n\n## Original User Goal\ntest\n\n## Approved Stage Summaries\n\n_None yet._\n")
    return run_root


class TestACPOperatorSatisfiesProtocol:
    def test_is_operator_protocol(self):
        op = ACPOperator(model="sonnet", server_factory=lambda: MagicMock())
        assert isinstance(op, OperatorProtocol)


class TestACPOperatorRunStage:
    def test_run_stage_success(self, tmp_path):
        run_root = _make_run(tmp_path)
        paths = build_run_paths(run_root)
        stage = STAGES[0]  # 01_literature_survey

        # Create fake stage output file (simulating what the server would produce)
        stage_tmp = paths.stage_tmp_file(stage)
        fake_markdown = (
            f"# Stage 01: Literature Survey\n\n"
            "## Objective\nTest\n\n"
            "## Previously Approved Stage Summaries\n_None yet._\n\n"
            "## What I Did\nFake work\n\n"
            "## Key Results\nFake results\n\n"
            "## Files Produced\n- `workspace/notes/fake.md`\n\n"
            "## Suggestions for Refinement\n"
            "1. Suggestion A\n2. Suggestion B\n3. Suggestion C\n\n"
            "## Your Options\n"
            "1. Use suggestion 1\n2. Use suggestion 2\n3. Use suggestion 3\n"
            "4. Refine with your own feedback\n5. Approve and continue\n6. Abort\n"
        )

        # Mock server that returns success
        mock_server = MagicMock()
        mock_server.handle_request.side_effect = [
            # task.create response
            TaskCreateResult(task_id="t1", session_id="s1"),
            # task.query response (completed)
            TaskQueryResult(
                task_id="t1",
                state=TaskState.COMPLETED,
                tokens_used=5000,
                session_id="s1",
            ),
        ]
        mock_server.stream_events.return_value = iter([
            CompletionEvent(task_id="t1", state=TaskState.COMPLETED, tokens_used=5000, session_id="s1"),
        ])

        op = ACPOperator(model="sonnet", server_factory=lambda: mock_server)

        # Write the fake stage file before calling run_stage
        # (in real usage, the server writes it; here we simulate)
        write_text(stage_tmp, fake_markdown)
        write_text(paths.notes_dir / "fake.md", "fake")

        result = op.run_stage(stage, "test prompt", paths, attempt_no=1)

        assert result.success is True
        assert result.exit_code == 0
        assert result.session_id == "s1"
        assert result.stage_file_path == stage_tmp
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/zychen/USTC\&PJLab/Lab/AutoR && python -m pytest tests/test_acp_operator.py::TestACPOperatorSatisfiesProtocol -v`
Expected: FAIL — `src.acp_operator` does not exist

- [ ] **Step 3: Implement ACPOperator**

```python
# src/acp_operator.py
"""ACP-based operator that communicates via JSON-RPC 2.0.

Replaces subprocess invocation of `claude -p` with structured
JSON-RPC requests to an ACP agent server.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any, Callable, TextIO

from .acp_types import (
    CompletionEvent,
    ErrorEvent,
    ProgressEvent,
    TaskCancelParams,
    TaskCreateParams,
    TaskCreateResult,
    TaskQueryResult,
    TaskState,
    ToolCallEvent,
)
from .jsonrpc import ErrorCode
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

        server = self._get_server()

        try:
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
            stdout_fragments.append(f"Task completed: {event.state.value}, tokens: {event.tokens_used}")

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/zychen/USTC\&PJLab/Lab/AutoR && python -m pytest tests/test_acp_operator.py -v`
Expected: All PASS

- [ ] **Step 5: Add --operator flag to main.py**

In `main.py`, add the argument and routing logic:

```python
# In parse_args(), add:
parser.add_argument(
    "--operator",
    choices=["cli", "acp"],
    default="cli",
    help="Operator backend: 'cli' uses Claude CLI subprocess (default), 'acp' uses ACP JSON-RPC protocol.",
)

# In main(), replace the operator construction with:
def _create_operator(args, model, ui):
    if args.operator == "acp":
        from src.acp_operator import ACPOperator
        return ACPOperator(model=model, ui=ui)
    return ClaudeOperator(model=model, fake_mode=args.fake_operator, ui=ui)
```

Update both the resume and new-run paths to use `_create_operator(args, model, ui)`.

- [ ] **Step 6: Run all tests**

Run: `cd /c/zychen/USTC\&PJLab/Lab/AutoR && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git checkout -b ziyan/acp-pr4-acp-operator ziyan/acp-refactor
git add src/acp_operator.py tests/test_acp_operator.py main.py
git commit -m "feat: add ACPOperator implementing OperatorProtocol

ACPOperator communicates with an ACP server via structured JSON-RPC
messages instead of subprocess calls. Emits typed events (progress,
tool_call, error, completion) to logs_raw.jsonl.

Add --operator cli|acp flag to main.py for backend selection.
Default remains 'cli' for backward compatibility."
```

---

## Task 5: ACP Agent Server (PR #5)

**Branch:** `ziyan/acp-pr5-acp-server`

**Goal:** Implement the ACP agent server that wraps the Anthropic Python SDK. This is the server-side component that receives JSON-RPC requests from `ACPOperator` and translates them to Claude API calls.

**Files:**
- Create: `src/acp_server.py`
- Create: `tests/test_acp_server.py`

- [ ] **Step 1: Write the failing test for ACPServer**

```python
# tests/test_acp_server.py
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.acp_server import ACPServer
from src.acp_types import (
    TaskCreateParams,
    TaskCreateResult,
    TaskQueryResult,
    TaskState,
)


class TestACPServerTaskLifecycle:
    def test_create_task_returns_task_id(self):
        server = ACPServer(api_key="test-key")
        params = TaskCreateParams(
            prompt="hello",
            model="sonnet",
            workspace="/tmp/w",
            stage_slug="01_literature_survey",
            stage_output_path="/tmp/s/01.tmp.md",
        )
        result = server.handle_request("acp.task.create", params)
        assert isinstance(result, TaskCreateResult)
        assert result.task_id
        assert result.session_id

    def test_query_pending_task(self):
        server = ACPServer(api_key="test-key")
        params = TaskCreateParams(
            prompt="hello",
            model="sonnet",
            workspace="/tmp/w",
            stage_slug="01_literature_survey",
            stage_output_path="/tmp/s/01.tmp.md",
        )
        create_result = server.handle_request("acp.task.create", params)
        query_result = server.handle_request("acp.task.query", create_result.task_id)
        assert isinstance(query_result, TaskQueryResult)
        assert query_result.state in {TaskState.PENDING, TaskState.RUNNING, TaskState.COMPLETED}

    def test_unknown_method_raises(self):
        server = ACPServer(api_key="test-key")
        with pytest.raises(ValueError, match="Unknown method"):
            server.handle_request("acp.unknown", {})

    def test_query_nonexistent_task_raises(self):
        server = ACPServer(api_key="test-key")
        with pytest.raises(KeyError):
            server.handle_request("acp.task.query", "nonexistent")


class TestACPServerCancel:
    def test_cancel_task(self):
        server = ACPServer(api_key="test-key")
        params = TaskCreateParams(
            prompt="hello",
            model="sonnet",
            workspace="/tmp/w",
            stage_slug="01_literature_survey",
            stage_output_path="/tmp/s/01.tmp.md",
        )
        create_result = server.handle_request("acp.task.create", params)
        from src.acp_types import TaskCancelParams
        cancel_params = TaskCancelParams(task_id=create_result.task_id)
        server.handle_request("acp.task.cancel", cancel_params)
        query_result = server.handle_request("acp.task.query", create_result.task_id)
        assert query_result.state == TaskState.CANCELLED
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/zychen/USTC\&PJLab/Lab/AutoR && python -m pytest tests/test_acp_server.py -v`
Expected: FAIL — `src.acp_server` does not exist

- [ ] **Step 3: Implement ACPServer**

```python
# src/acp_server.py
"""ACP Agent Server wrapping the Anthropic Python SDK.

Receives structured JSON-RPC requests, translates them to Claude API calls,
and emits typed events. Runs in-process (no network needed).
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from .acp_types import (
    CompletionEvent,
    ErrorEvent,
    ProgressEvent,
    TaskCancelParams,
    TaskCreateParams,
    TaskCreateResult,
    TaskQueryResult,
    TaskResumeParams,
    TaskState,
    ToolCallEvent,
)


@dataclass
class _TaskRecord:
    task_id: str
    session_id: str
    params: TaskCreateParams
    state: TaskState = TaskState.PENDING
    tokens_used: int = 0
    error_message: str | None = None
    events: list[Any] = field(default_factory=list)


class ACPServer:
    """In-process ACP server. Manages task lifecycle and delegates to Claude API."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key
        self._tasks: dict[str, _TaskRecord] = {}

    def handle_request(self, method: str, params: Any) -> Any:
        if method == "acp.task.create":
            return self._create_task(params)
        if method == "acp.task.query":
            return self._query_task(params)
        if method == "acp.task.cancel":
            return self._cancel_task(params)
        if method == "acp.task.resume":
            return self._resume_task(params)
        raise ValueError(f"Unknown method: {method}")

    def stream_events(self, task_id: str) -> Iterator[Any]:
        record = self._tasks.get(task_id)
        if record is None:
            raise KeyError(f"Task not found: {task_id}")

        if record.state == TaskState.CANCELLED:
            return

        # Execute the task (call Claude API)
        record.state = TaskState.RUNNING
        try:
            yield from self._execute_task(record)
        except Exception as exc:
            record.state = TaskState.FAILED
            record.error_message = str(exc)
            yield ErrorEvent(
                task_id=task_id,
                code="EXECUTION_ERROR",
                message=str(exc),
                recoverable=False,
            )

    def _create_task(self, params: TaskCreateParams) -> TaskCreateResult:
        task_id = str(uuid.uuid4())
        session_id = params.session_id or str(uuid.uuid4())
        record = _TaskRecord(
            task_id=task_id,
            session_id=session_id,
            params=params,
        )
        self._tasks[task_id] = record
        return TaskCreateResult(task_id=task_id, session_id=session_id)

    def _query_task(self, task_id: str) -> TaskQueryResult:
        record = self._tasks.get(task_id)
        if record is None:
            raise KeyError(f"Task not found: {task_id}")
        return TaskQueryResult(
            task_id=record.task_id,
            state=record.state,
            tokens_used=record.tokens_used,
            session_id=record.session_id,
            error_message=record.error_message,
        )

    def _cancel_task(self, params: TaskCancelParams) -> None:
        record = self._tasks.get(params.task_id)
        if record is None:
            raise KeyError(f"Task not found: {params.task_id}")
        record.state = TaskState.CANCELLED

    def _resume_task(self, params: TaskResumeParams) -> TaskCreateResult:
        record = self._tasks.get(params.task_id)
        if record is None:
            raise KeyError(f"Task not found: {params.task_id}")
        record.state = TaskState.PENDING
        return TaskCreateResult(task_id=record.task_id, session_id=record.session_id)

    def _execute_task(self, record: _TaskRecord) -> Iterator[Any]:
        """Execute a task by calling the Claude API.

        This is the integration point with the Anthropic SDK.
        For now, this is a stub that yields a completion event.
        The real implementation will:
        1. Call anthropic.messages.create() with streaming
        2. Parse tool_use blocks and execute tools locally
        3. Yield ProgressEvent, ToolCallEvent as they happen
        4. Write stage output file when Claude produces it
        5. Yield CompletionEvent when done
        """
        # TODO(PR #6): Replace with real Anthropic SDK integration
        record.state = TaskState.COMPLETED
        yield CompletionEvent(
            task_id=record.task_id,
            state=TaskState.COMPLETED,
            tokens_used=record.tokens_used,
            session_id=record.session_id,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/zychen/USTC\&PJLab/Lab/AutoR && python -m pytest tests/test_acp_server.py -v`
Expected: All PASS

- [ ] **Step 5: Run all tests**

Run: `cd /c/zychen/USTC\&PJLab/Lab/AutoR && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git checkout -b ziyan/acp-pr5-acp-server ziyan/acp-refactor
git add src/acp_server.py tests/test_acp_server.py
git commit -m "feat: add ACP server with task lifecycle management

ACPServer manages task creation, querying, cancellation, and resumption.
Task execution currently stubs the Claude API call — real Anthropic SDK
integration will follow in the next PR.

Server runs in-process (no network). Emits typed events (progress,
tool_call, error, completion) via stream_events() iterator."
```

---

## Task 6: End-to-End Integration (PR #6)

**Branch:** `ziyan/acp-pr6-integration`

**Goal:** Wire ACPOperator + ACPServer together in `main.py`. Add Anthropic SDK integration in the server. Add `--operator acp` smoke test. Add structured event display in terminal UI.

**Files:**
- Modify: `main.py` (wire server_factory for ACP operator)
- Modify: `src/acp_server.py` (add Anthropic SDK call in `_execute_task`)
- Modify: `src/terminal_ui.py` (add `show_acp_event` method)
- Modify: `src/acp_operator.py` (call UI for events)
- Create: `tests/test_acp_integration.py`

- [ ] **Step 1: Write the integration test**

```python
# tests/test_acp_integration.py
from __future__ import annotations

import tempfile
from pathlib import Path

from src.acp_operator import ACPOperator
from src.acp_server import ACPServer
from src.acp_types import CompletionEvent, TaskState
from src.operator_protocol import OperatorProtocol
from src.utils import STAGES, build_run_paths, ensure_run_layout, write_text


def _make_run(tmp_path: Path) -> Path:
    run_root = tmp_path / "integration_run"
    paths = build_run_paths(run_root)
    ensure_run_layout(paths)
    write_text(paths.user_input, "integration test goal")
    write_text(
        paths.memory,
        "# Approved Run Memory\n\n## Original User Goal\nintegration test\n\n## Approved Stage Summaries\n\n_None yet._\n",
    )
    return run_root


def test_acp_operator_with_real_server(tmp_path):
    """ACPOperator + ACPServer can complete a task lifecycle (stub mode)."""
    run_root = _make_run(tmp_path)
    paths = build_run_paths(run_root)
    stage = STAGES[0]

    server = ACPServer(api_key="test-key")
    op = ACPOperator(model="sonnet", server_factory=lambda: server)
    assert isinstance(op, OperatorProtocol)

    # Since server is in stub mode, it will complete immediately
    # but won't write the stage file. We pre-create it.
    stage_tmp = paths.stage_tmp_file(stage)
    write_text(stage_tmp, "# Stage 01: Literature Survey\n\n## Objective\nTest\n")
    write_text(paths.notes_dir / "fake.md", "placeholder")

    result = op.run_stage(stage, "test prompt", paths, attempt_no=1)

    # Stub server completes, file exists -> success
    assert result.success is True
    assert result.session_id is not None

    # Verify logs were written
    logs_raw = paths.logs_raw.read_text(encoding="utf-8")
    assert "acp_start" in logs_raw or "acp_result" in logs_raw


def test_acp_operator_handles_missing_stage_file(tmp_path):
    """ACPOperator reports failure when stage file is not produced."""
    run_root = _make_run(tmp_path)
    paths = build_run_paths(run_root)
    stage = STAGES[0]

    server = ACPServer(api_key="test-key")
    op = ACPOperator(model="sonnet", server_factory=lambda: server)

    # Don't create the stage file — server stub doesn't write it
    result = op.run_stage(stage, "test prompt", paths, attempt_no=1)

    # No stage file -> success=False
    assert result.success is False
```

- [ ] **Step 2: Run test to verify it fails (or passes if wiring is correct)**

Run: `cd /c/zychen/USTC\&PJLab/Lab/AutoR && python -m pytest tests/test_acp_integration.py -v`
Expected: Should pass if Tasks 4+5 are correct

- [ ] **Step 3: Wire server_factory in main.py**

Update the `_create_operator` function in `main.py`:

```python
def _create_operator(args, model, ui):
    if args.operator == "acp":
        from src.acp_operator import ACPOperator
        from src.acp_server import ACPServer
        import os

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        server = ACPServer(api_key=api_key)
        return ACPOperator(model=model, ui=ui, server_factory=lambda: server)
    return ClaudeOperator(model=model, fake_mode=args.fake_operator, ui=ui)
```

- [ ] **Step 4: Add show_acp_event to TerminalUI**

In `src/terminal_ui.py`, add:

```python
def show_acp_progress(self, tokens_used: int, elapsed: float) -> None:
    self.show_status(
        f"Tokens: {tokens_used:,} | Elapsed: {elapsed:.1f}s",
        level="info",
    )

def show_acp_tool_call(self, tool_name: str, status: str) -> None:
    level = "warn" if status == "failed" else "info"
    self.show_status(f"[{tool_name}] {status}", level=level)

def show_acp_completion(self, state: str, tokens_used: int, session_id: str) -> None:
    level = "success" if state == "completed" else "error"
    self.show_status(
        f"Task {state} | Tokens: {tokens_used:,} | Session: {session_id}",
        level=level,
    )
```

- [ ] **Step 5: Update ACPOperator._handle_event to use new UI methods**

In `src/acp_operator.py`, update `_handle_event`:

```python
def _handle_event(self, event, paths, stage, attempt_no, stdout_fragments):
    if isinstance(event, ProgressEvent):
        append_jsonl(paths.logs_raw, {
            "_meta": {"stage": stage.slug, "attempt": attempt_no, "event": "progress"},
            **event.to_dict(),
        })
        self.ui.show_acp_progress(event.tokens_used, event.elapsed_seconds)
    elif isinstance(event, ToolCallEvent):
        append_jsonl(paths.logs_raw, {
            "_meta": {"stage": stage.slug, "attempt": attempt_no, "event": "tool_call"},
            **event.to_dict(),
        })
        self.ui.show_acp_tool_call(event.tool_name, event.status)
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
        self.ui.show_acp_completion(
            event.state.value, event.tokens_used, event.session_id or "unknown"
        )
        stdout_fragments.append(
            f"Task completed: {event.state.value}, tokens: {event.tokens_used}"
        )
```

- [ ] **Step 6: Run all tests**

Run: `cd /c/zychen/USTC\&PJLab/Lab/AutoR && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git checkout -b ziyan/acp-pr6-integration ziyan/acp-refactor
git add main.py src/acp_operator.py src/acp_server.py src/terminal_ui.py tests/test_acp_integration.py
git commit -m "feat: wire ACP operator + server end-to-end

- main.py: --operator acp creates ACPServer with ANTHROPIC_API_KEY
  and passes it to ACPOperator via server_factory
- terminal_ui.py: add show_acp_progress/tool_call/completion methods
  for structured event display
- ACPOperator: use new UI methods for event rendering
- Integration test: verify operator + server lifecycle works"
```

---

## Post-PR6: Future Work (Not in Current Plan)

这些不在当前计划范围内，但记录下来作为后续方向：

1. **Anthropic SDK 真实集成**: 在 `ACPServer._execute_task()` 中替换 stub，使用 `anthropic.messages.create(stream=True)` 进行真实 API 调用，解析 tool_use blocks，本地执行工具（文件读写、Bash 等），将结果回传给 Claude。

2. **Token Budget**: 根据 `ProgressEvent.tokens_used` 实现 token 预算控制，在接近上下文窗口限制时压缩 memory.md。

3. **超时控制**: 在 `ACPServer._execute_task()` 中加入 `timeout_seconds` 支持，超时后优雅终止并 yield `ErrorEvent(code="TIMEOUT")`。

4. **HTTP 传输**: 当需要分布式部署时，在 JSON-RPC 层之上加 HTTP/SSE 传输。

5. **可观测性 Dashboard**: 利用结构化的 `logs_raw.jsonl` 事件构建实时 run dashboard。

---

## Summary

| PR | Branch | 改动范围 | 核心产出 |
|----|--------|---------|---------|
| #1 | `ziyan/acp-pr1-operator-protocol` | 接口提取 | `OperatorProtocol` ABC |
| #2 | `ziyan/acp-pr2-jsonrpc-transport` | 协议层 | JSON-RPC 2.0 codec |
| #3 | `ziyan/acp-pr3-acp-types` | 类型定义 | ACP 消息类型 |
| #4 | `ziyan/acp-pr4-acp-operator` | 客户端 | `ACPOperator` + `--operator` flag |
| #5 | `ziyan/acp-pr5-acp-server` | 服务端 | `ACPServer` 任务生命周期 |
| #6 | `ziyan/acp-pr6-integration` | 集成 | 端到端接线 + UI + 测试 |

每个 PR 独立可审查、可合入、不破坏现有功能。
