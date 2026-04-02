# ACP Refactor Analysis: From `claude -p` to JSON-RPC 2.0 + ACP

> Generated 2026-04-02. Proposal for the `ziyan/acp-refactor` branch.

## Problem Statement

AutoR's current architecture is tightly coupled to the Claude CLI (`claude -p`) via subprocess invocation. This creates fundamental observability and reliability problems:

### Current Architecture

```
ResearchManager
  -> ClaudeOperator.run_stage()
    -> subprocess.Popen(["claude", "--model", model, "-p", "@prompt", ...])
    -> parse stdout line-by-line (stream-json)
    -> string-match stderr for failure detection
    -> file-based session ID management
```

### Root Problems

| Problem | Cause | Impact |
|---------|-------|--------|
| **No observability** | Claude is a black box subprocess | Can't inspect token usage, tool calls, reasoning, progress |
| **No timeout control** | `subprocess.Popen` with no timeout | Stage 05 hung for hours in example run |
| **Fragile failure detection** | String matching on stderr (`"no conversation found"`) | Silent failures, resume loops (V3-1) |
| **No structured errors** | CLI exit codes + text messages | Can't distinguish between error types programmatically |
| **Opaque session resume** | `--resume <uuid>` with no health check | Resume hits stale sessions, causes loops |
| **Prompt explosion** | Memory.md grows unbounded, no token budget | 8KB -> 75KB prompt growth (V4-1) |
| **No progress tracking** | Can only stream text output | Can't show "tool X called", "Y% complete" |
| **No cancellation** | Only `process.terminate()` | Unclean state on interrupt (V3-4) |

## Proposed Architecture: JSON-RPC 2.0 + ACP

### What is ACP

ACP (Agent Communication Protocol) is a standardized protocol for agent-to-agent communication built on JSON-RPC 2.0. It provides:

- **Structured request/response**: Typed methods, parameters, and results
- **Streaming**: Server-Sent Events (SSE) for real-time progress
- **Task lifecycle**: Create, query, cancel, resume tasks with explicit states
- **Observable**: Token usage, tool calls, intermediate results all visible
- **Transport-agnostic**: HTTP, WebSocket, stdio all supported

### Target Architecture

```
ResearchManager
  -> ACPOperator (replaces ClaudeOperator)
    -> JSON-RPC 2.0 client
      -> ACP-compatible agent server (wrapping Claude API)
        -> Claude API (direct, not CLI)
```

### Key Components to Build

#### 1. ACP Agent Server (`src/acp_server.py`)

A lightweight ACP-compatible server that wraps the Claude API (Anthropic SDK):

```
ACP Server
  Exposes methods:
    - acp.task.create    -> start a stage execution
    - acp.task.query     -> check status, get progress
    - acp.task.cancel    -> graceful cancellation
    - acp.task.resume    -> resume with context
    - acp.tools.list     -> available tools
    - acp.tools.call     -> delegate tool execution
```

This server manages:
- Direct Claude API calls (not CLI subprocess)
- Tool execution routing (file read/write, search, etc.)
- Token tracking and budget enforcement
- Structured error reporting
- Task lifecycle state machine

#### 2. ACP Client / ACPOperator (`src/acp_operator.py`)

Replaces `ClaudeOperator`. Communicates with the ACP server via JSON-RPC 2.0:

```python
class ACPOperator:
    def run_stage(self, stage, prompt, paths, attempt_no, continue_session=False):
        # Create task via JSON-RPC
        task_id = self.client.request("acp.task.create", {
            "prompt": prompt,
            "model": self.model,
            "tools": [...],
            "workspace": str(paths.workspace_root),
            "token_budget": self._token_budget_for_stage(stage),
        })

        # Stream progress via SSE
        for event in self.client.stream(task_id):
            self._handle_event(event, paths, stage)  # structured events!

        # Query final result
        result = self.client.request("acp.task.query", {"task_id": task_id})
        return self._to_operator_result(result)
```

#### 3. JSON-RPC 2.0 Transport (`src/jsonrpc.py`)

Minimal JSON-RPC 2.0 client/server implementation:

```python
# Request
{"jsonrpc": "2.0", "method": "acp.task.create", "params": {...}, "id": 1}

# Response (success)
{"jsonrpc": "2.0", "result": {"task_id": "...", "status": "running"}, "id": 1}

# Response (error)
{"jsonrpc": "2.0", "error": {"code": -32000, "message": "...", "data": {...}}, "id": 1}

# Notification (no id, no response expected)
{"jsonrpc": "2.0", "method": "acp.event.progress", "params": {"task_id": "...", "tokens_used": 1234}}
```

## What This Fixes

### 1. Observability (V3-*, V4-*)

**Before**: Parse stdout line-by-line, hope for useful text.
**After**: Structured events with typed fields:

```json
// Progress event
{"method": "acp.event.progress", "params": {
  "task_id": "abc123",
  "stage": "05_experimentation",
  "tokens_used": 15000,
  "tokens_budget": 50000,
  "tools_called": ["Write", "Bash", "Read"],
  "files_modified": ["workspace/code/model.py"],
  "elapsed_seconds": 120
}}

// Tool call event
{"method": "acp.event.tool_call", "params": {
  "task_id": "abc123",
  "tool": "Bash",
  "input": {"command": "python train.py"},
  "status": "running"
}}

// Error event (structured, not string matching)
{"method": "acp.event.error", "params": {
  "task_id": "abc123",
  "code": "SESSION_NOT_FOUND",
  "message": "No conversation found with session id abc123",
  "recoverable": true
}}
```

### 2. Timeout & Cancellation (V3-2, V3-4)

**Before**: No timeout. `process.terminate()` leaves dirty state.
**After**: Task-level timeout and graceful cancellation:

```python
# Create with timeout
task = client.request("acp.task.create", {
    "timeout_seconds": 1800,  # 30 min max
    ...
})

# Cancel gracefully
client.request("acp.task.cancel", {
    "task_id": task["task_id"],
    "reason": "user_interrupt",
    "save_progress": True  # persist partial work
})
```

### 3. Session Health (V3-1, V3-3)

**Before**: `_looks_like_resume_failure()` with fragile string matching.
**After**: Explicit session state query:

```python
# Query session health before attempting resume
status = client.request("acp.task.query", {"task_id": task_id})
if status["state"] == "completed":
    # Don't resume a completed task
elif status["state"] == "failed":
    # Start fresh, don't resume
elif status["state"] == "suspended":
    # Safe to resume
    client.request("acp.task.resume", {"task_id": task_id, "context": {...}})
```

### 4. Token Budget & Context Compression (V4-1, V4-2)

**Before**: Prompt grows to 75KB with no awareness of token limits.
**After**: Token-aware prompt construction:

```python
# Server reports token usage
result = client.request("acp.task.query", {"task_id": task_id})
# result["tokens_used"] = 45000
# result["context_window_remaining"] = 155000

# Client can make informed decisions about prompt size
if stage.number >= 6:
    # Late stages: compress memory, keep only recent + critical
    memory = compress_memory(full_memory, token_budget=20000)
```

### 5. Structured Error Handling (all V-*)

**Before**: Parse text for error patterns.
**After**: Typed error codes:

```python
try:
    result = client.request("acp.task.create", params)
except JsonRpcError as e:
    if e.code == ErrorCode.SESSION_NOT_FOUND:
        # Explicit: create new session
    elif e.code == ErrorCode.TOKEN_LIMIT_EXCEEDED:
        # Explicit: compress and retry
    elif e.code == ErrorCode.TOOL_EXECUTION_FAILED:
        # Explicit: handle tool failure
    elif e.code == ErrorCode.MODEL_OVERLOADED:
        # Explicit: backoff and retry
```

## Migration Strategy

### Phase 1: JSON-RPC 2.0 Transport Layer

Add `src/jsonrpc.py` with minimal JSON-RPC 2.0 client/server:
- Request/response encoding
- Error codes
- Notification support
- Stdio transport (same process, no network dependency initially)

### Phase 2: ACP Operator (Parallel Implementation)

Add `src/acp_operator.py` alongside existing `src/operator.py`:
- Same interface (`run_stage`, `repair_stage_summary`)
- Uses JSON-RPC instead of subprocess
- Feature flag in `main.py`: `--operator acp` vs `--operator cli` (default)

### Phase 3: ACP Agent Server

Add `src/acp_server.py`:
- Wraps Anthropic Python SDK (direct API calls)
- Manages tool execution
- Reports structured events
- Handles session/task lifecycle

### Phase 4: Observability Dashboard

The structured events from ACP enable a real-time dashboard:
- Token usage per stage
- Tool call timeline
- Error rates and recovery patterns
- Progress tracking
- Run comparison

### Phase 5: Deprecate CLI Operator

Once ACP operator is stable:
- Make `--operator acp` the default
- Keep `--operator cli` as fallback
- Eventually remove CLI operator

## Impact on Existing Code

### Files that change:

| File | Change Type | Scope |
|------|-------------|-------|
| `main.py` | Modified | Add `--operator` flag, route to ACP or CLI operator |
| `src/manager.py` | Minimal | Operator interface is the same; add event handling |
| `src/operator.py` | Unchanged | Kept as CLI fallback |
| `src/utils.py` | Minor | Add token budget helpers |
| `src/terminal_ui.py` | Enhanced | Display structured events (tool calls, progress bars) |

### New files:

| File | Purpose |
|------|---------|
| `src/jsonrpc.py` | JSON-RPC 2.0 protocol implementation |
| `src/acp_operator.py` | ACP-based operator (replaces subprocess calls) |
| `src/acp_server.py` | ACP agent server (wraps Claude API) |
| `src/acp_types.py` | Type definitions for ACP messages |
| `src/token_budget.py` | Token tracking and budget enforcement |

### Files that DON'T change:

| File | Why |
|------|-----|
| `src/prompts/*.md` | Prompt templates are transport-agnostic |
| `templates/registry.yaml` | Venue metadata is independent |
| `src/writing_manifest.py` | Artifact scanning is independent |
| `tests/` | Add new tests; existing tests continue to use fake operator |

## Key Design Constraints

1. **No external dependencies for core**: JSON-RPC 2.0 is simple enough to implement in stdlib. ACP client/server use only `json`, `http.server`, `urllib`.

2. **Backward compatible**: CLI operator remains available. All existing run dirs work unchanged.

3. **Same operator interface**: `ACPOperator` exposes the same `run_stage()` / `repair_stage_summary()` interface. `ResearchManager` doesn't need to know which operator it's using.

4. **Incremental migration**: Each phase is independently valuable and testable.

5. **Local-first**: Default transport is stdio (same process). HTTP transport is optional for distributed setups.

## Open Questions

1. **Anthropic SDK vs Claude API directly?** The Anthropic Python SDK is a thin wrapper. Using it adds one dependency but handles auth, retries, and streaming. Recommend using it.

2. **Tool execution model?** In CLI mode, Claude has direct filesystem access. In ACP mode, should tools be:
   - (a) Executed by the ACP server (same access model)
   - (b) Routed back to the client for execution (more control, more complexity)
   - Recommend (a) for simplicity, with tool execution logging.

3. **Session persistence?** ACP tasks have explicit state. Should we:
   - (a) Store ACP task state in `operator_state/` (like session IDs today)
   - (b) Use the ACP server's built-in task persistence
   - Recommend (a) for consistency with existing run directory structure.

4. **Memory compression strategy?** With token visibility, we can implement real compression:
   - (a) LLM-based summarization of memory.md per stage
   - (b) Rule-based truncation (keep headings + key results, drop details)
   - (c) Sliding window (only last N stages in full)
   - Recommend (b) initially, upgrade to (a) when stable.
