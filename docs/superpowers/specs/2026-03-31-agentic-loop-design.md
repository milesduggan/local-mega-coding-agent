# Agentic Turn Loop — Design Spec

**Date:** 2026-03-31
**Status:** Approved

---

## Overview

Replace the current single-pass `agent_loop` with a multi-turn `TurnRunner` that autonomously calls tools, gathers context, and builds a session transcript before generating a diff. Simultaneously migrate from dual-model architecture (LLaMA + DeepSeek) to a single Qwen2.5-Coder 7B-Instruct model.

Inspired by architectural patterns revealed in the Claude Code source leak (March 2026), adapted to this project's dual-model-to-single-model transition and local-first constraints.

---

## Goals

- Agent can autonomously call tools across multiple turns before generating a diff
- User sees a live transcript of what the agent did
- Read-only tools run silently; write/bash tools require user approval
- Loop always terminates with a meaningful stop reason
- Single model replaces dual-model setup — better results, lower RAM, simpler architecture
- No async rewrite (deferred — requires async inference layer first)

## Non-Goals

- Real-time streaming / async event loop (future: requires swapping llama-cpp-python for a server-based inference layer)
- Session persistence across restarts
- `simple_mode` tool restriction flag (deferred)
- Decision-State Snapshot validation improvements (deferred)

---

## Architecture

```
User input
    ↓
Router — scores user input against tool registry, ranks relevant tools
    ↓
SessionContext — builds structured context: tool counts, routing decisions, workspace metadata
    ↓
TurnRunner.run() — loop up to MAX_AGENT_TURNS
    ┌─────────────────────────────────────────────────┐
    │  Each turn:                                      │
    │  1. Model response (Qwen2.5-Coder)              │
    │  2. Extract tool calls from response            │
    │  3. Read-only tools → execute immediately       │
    │  4. Write/bash tools → return approval_required │
    │  5. Tool results → appended to context          │
    │  6. History event logged                        │
    │  7. Check stop_reason → break if terminal       │
    └─────────────────────────────────────────────────┘
    ↓
Executor prompt → diff generated (same Qwen2.5-Coder instance, low temp)
    ↓
Reviewer prompt → PASS/FAIL (same model, conservative temp)
    ↓
TurnResult { diff, transcript, stop_reason, mode }
    ↓
VS Code sidebar — renders transcript (collapsible) + diff + stop reason message
```

---

## Components

### New Files

**`scripts/agent/turn_runner.py`**
- `TurnRunner` class with `run(user_input, files) → TurnResult`
- Owns the turn loop, tool dispatch, approval gating, history building
- Per-turn timeout using existing `TIMEOUT_EXECUTE_MS`
- Returns explicit `stop_reason`: `done`, `max_turns_reached`, `approval_required`, `error`

**`scripts/agent/router.py`**
- `Router` class with `score(user_input, tools) → List[ToolMatch]`
- Tokenizes user input, scores against tool registry
- Pre-loads relevant tools into turn 1 context
- Returns empty list gracefully on no match or malformed input

**`scripts/agent/context.py`**
- `SessionContext` dataclass: tool counts, routing decisions, workspace metadata, model info
- `build_session_context(snapshot, routing_result) → SessionContext`
- Injected into system prompt so model knows what's available from turn 1

**`scripts/agent/history.py`**
- `HistoryLog` with `add(title: str, detail: str)` and `to_list() → List[Dict]`
- One event per tool call: `"Read file"`, `"Searched files"`, `"Ran bash: ls src/"`

### Modified Files

**`scripts/agent/main.py`**
- `agent_loop` replaced, delegates entirely to `TurnRunner`
- Signature unchanged for backward compatibility with `backend/wrapper.py`

**`scripts/config.py`**
- Remove `DEEPSEEK_*` and `LLAMA_*` config blocks
- Add single `MODEL_*` block (path, context size, temperatures per role, threads)
- Add `MAX_AGENT_TURNS = _get_int("AI_AGENT_MAX_TURNS", 10)`

**`scripts/backend/model_manager.py`**
- Manage single Qwen2.5-Coder model instance instead of two
- RAM requirement drops from ~8GB to ~4.5GB loaded

**`setup_models.py`**
- Download Qwen2.5-Coder 7B-Instruct Q4_K_M only (~4.5GB)
- Remove LLaMA and DeepSeek download logic

**`vscode-ai-agent/src/SidebarProvider.ts`**
- Render collapsible transcript section above diff
- Display stop reason message: e.g. "Agent reached turn limit — try narrowing your task"
- Handle `approval_required` mode: show tool + args with Approve/Reject buttons

### Unchanged

- `scripts/tools/` — tool system untouched
- `scripts/chunker/` — AST chunking untouched
- `scripts/critic/`, `scripts/executor/`, `scripts/review/` — same prompts/logic, just called against single model
- `backend/wrapper.py` — JSON-RPC routing untouched

---

## Stop Reasons

| stop_reason | Meaning | UI Message |
|---|---|---|
| `done` | Agent completed successfully | (none, show diff) |
| `max_turns_reached` | Hit MAX_AGENT_TURNS without finishing | "Agent reached turn limit — try narrowing your task" |
| `approval_required` | Write/bash tool needs user approval | Show tool + args with Approve/Reject |
| `error` | Tool failure or unparseable model output | Surface error message, no diff |

---

## Permission Model

| Tool type | Behavior |
|---|---|
| Read-only (`is_read_only=True`) | Execute silently, log to transcript |
| Write/bash (`requires_approval=True`) | Pause loop, return `approval_required` to VS Code |

On approval: resume loop with tool result in context.
On rejection: log rejection to transcript, continue loop without tool result.

---

## Error Handling

- **Max turns reached:** Return partial transcript + `max_turns_reached` stop reason
- **Read-only tool fails:** Log to transcript, continue loop, let model decide next step
- **Write/bash tool fails after approval:** `stop_reason: "error"`, surface error, no diff
- **Unparseable model output:** Treat as clarification, return `mode: "clarify"` to user
- **Per-turn timeout:** Cancel turn, log timeout event to transcript, continue to next turn

---

## Model Migration

| | Before | After |
|---|---|---|
| Models | LLaMA 3.1 8B + DeepSeek Coder 6.7B | Qwen2.5-Coder 7B-Instruct |
| RAM (loaded) | ~8GB | ~4.5GB |
| RAM (minimum) | 16GB | 8GB |
| Disk | ~8GB | ~4.5GB |
| Chat temp | 0.7 (LLaMA) | 0.7 |
| Code gen temp | 0.2 (DeepSeek) | 0.2 |
| Review temp | 0.3 (LLaMA) | 0.3 |

Critic-Executor-Review workflow is preserved — same three roles, different system prompts, same single model instance.

---

## Testing

**`tests/test_turn_runner.py`**
- Loop breaks on `done` before max_turns
- Loop breaks on `max_turns_reached` at turn limit (explicit reachability test)
- Read-only tools execute without approval gate
- Write/bash tools return `approval_required` (explicit reachability test)
- Per-turn timeout triggers correctly
- `error` stop reason reachable via tool failure (explicit reachability test)

**`tests/test_router.py`**
- Scores correct tools higher for known input patterns
- Returns empty list on no match
- Handles empty/malformed input without crashing

**`tests/test_history.py`**
- Events append in order
- `to_list()` returns correct structure for VS Code serialization

**`tests/test_context.py`**
- `SessionContext` builds correctly with tool counts and routing decisions
- System prompt contains expected metadata

**`tests/test_tool_registry_parity.py`**
- All registered tools have: schema, description, `is_read_only` set, `requires_approval` set
- Catches tools added without proper configuration

**Unchanged:** `test_executor.py`, `test_tools.py`

---

## Deferred

- **Async/streaming loop (Option C):** Right architecture, wrong time. Prerequisite is async model inference (llama.cpp server or ollama). Revisit when inference layer is ready.
- **`simple_mode`:** Config flag to limit tools to bash + file ops. Low effort, low priority.
- **Decision-State Snapshot validation improvements:** Already implemented in `snapshot.py`, improvements deferred.
- **Session persistence across restarts:** Not in scope for this iteration.
