# Local AI Agent - Architecture

## Overview

Local AI Agent is a VS Code extension backed by a Python JSON-RPC service and a single locally-running LLM:
- **Qwen3-14B-Instruct** (Q4_K_M) handles chat, code generation, review, normalization, and agent-turn decisions

All inference runs locally. No data leaves your machine.

## Architecture Framing

### Current Integrated Runtime

The current shipped runtime is:

1. A VS Code extension that manages the UI, command surface, diff application, and Python backend lifecycle
2. A Python backend that exposes JSON-RPC methods over stdin/stdout
3. A single main model managed through `ModelManager`
4. An agentic turn loop that can use tools before generating changes
5. A review-and-apply flow before writing code to disk

This is the current integrated path a user is actually running today.

Startup boundary:

- extension activation registers commands, views, and providers
- activation does not spawn the Python backend
- activation does not warm the main model
- backend startup and model loading happen on first intentional agent use or explicit model-management command

### Internal Module Structure

Some folders in the repo reflect implementation organization rather than separate live runtime boundaries:

- `scripts/critic/` contains internal chat and review codepaths
- `scripts/executor/` contains internal code generation codepaths
- `scripts/memory/` contains local context and memory utilities

These modules are useful implementation boundaries, but they should not be read as separate models or as separate product surfaces.

### Planned or Partial Context and Persistence Work

The codebase includes context and memory support code, and the docs/specs describe richer persistence and codebase-awareness patterns. Those ideas are directionally important, but they are **not yet fully integrated** into the current `agent_turn` orchestration path.

In particular:

- the current runtime uses `SessionContext` and `HistoryLog` inside the turn loop
- richer session persistence and codebase-awareness work remains planned or partial
- `scripts/memory/context_manager.py` should be read as supporting infrastructure, not as proof that full session persistence is already live in the shipped agent loop

## Component Flow

The current runtime flow is:

1. **VS Code extension**
   - `SidebarProvider.ts` handles chat UI, diff UI, apply/reject flow, and command-triggered actions
   - `pythonBackend.ts` is the TypeScript JSON-RPC client
   - `extension.ts` wires commands and extension activation
2. **Python backend**
   - `wrapper.py` exposes JSON-RPC methods such as `chat`, `normalize_task`, `execute`, `review`, and `agent_turn`
3. **Agent orchestration**
   - `TurnRunner` manages multi-turn tool use
   - `Router` scores tools against the user task
   - `SessionContext` and `HistoryLog` provide turn-level context and transcript state
4. **Model-backed execution**
   - the single main model is used across chat, normalization, turn decisions, generation, and review
5. **Review and apply**
   - generated diffs are reviewed
   - files are validated before write
   - changes are applied only after explicit user approval

## User Flow

1. **Select files** - The user adds files through the sidebar or command palette
2. **Chat** - The user describes the task and can clarify intent
3. **Proceed** - The extension gathers selected files and enters the execution flow
4. **Agent loop** - `agent_turn` can inspect files, search the workspace, and gather context through tools
5. **Execute** - The code generation stage produces file updates and synthesizes a diff locally
6. **Review** - The diff is checked before apply
7. **Apply / Reject** - The user decides whether to write the changes

## Key Design Decisions

### Why Single Model?

Using one model for all tasks offers significant advantages:

| Benefit | Detail |
|---------|--------|
| Simpler architecture | No coordination between multiple model runtimes |
| Lower RAM usage | One model is loaded and managed |
| Consistent reasoning | The same model that understands the task also writes and reviews the code |
| Easier configuration | A single `MODEL_*` configuration surface |

Qwen3-14B-Instruct currently handles conversation, code generation, review, normalization, and turn decisions.

### Agentic Loop

The agentic loop is a first-class runtime component.

Core pieces:

- `turn_runner.py` owns the multi-turn loop
- `router.py` ranks relevant tools from the task description
- `context.py` builds `SessionContext` for the prompt
- `history.py` records transcript events for the UI

The loop can:

- call read-only tools without pausing
- stop for approval when a write or shell tool requires it
- return explicit stop reasons such as `done`, `max_turns_reached`, `approval_required`, or `error`

### Chunk-Based Execution (Token Optimization)

For Python files, code generation uses AST-based chunking to reduce token usage.

How it works:

1. `python_chunker.py` parses the file with Python's `ast` module
2. `selector.py` chooses relevant chunks for the task
3. only relevant chunks are sent to the model
4. `reconstructor.py` rebuilds the full file from the modified chunks

Fallback:

- non-Python files use full-file mode

### Diff Generation is Local

The model outputs full file contents or chunk contents, not diffs.

The generation path:

1. parses `FILE:` or `CHUNK:` blocks from model output
2. reconstructs the full file if chunking was used
3. synthesizes unified diffs locally with Python's `difflib`
4. returns the diff to the frontend for review

This keeps diff generation deterministic and avoids relying on the model to emit valid diff syntax.

### Model Lifecycle Management

The model is managed by a centralized `ModelManager` singleton that handles:

- lazy loading on first access
- access timestamp tracking
- automatic unloading after idle timeout
- manual unload through the extension command surface

```python
from scripts.backend.model_manager import get_manager, ModelType

manager = get_manager()
manager.register_model(ModelType.MAIN, path, config, loader_fn)

# Lazy load and track access
model = manager.get_model(ModelType.MAIN)

# Check status
status = manager.get_status()  # {main: {loaded, idle_seconds}}

# Manual unload to free RAM
manager.unload_model(ModelType.MAIN)
```

Key features:

- **Thread-safe singleton** - safe for concurrent access
- **Lazy loading** - model loads only when first accessed
- **Access tracking** - timestamps update on each `get_model()` call
- **Auto-unload** - background thread unloads the model after idle timeout
- **Memory cleanup** - uses `gc.collect()` after deletion

Warm-up:

- the runtime supports explicit `warm_up()` calls, but the extension no longer performs eager warm-up on activation
- in the current shipped behavior, the backend and main model are started lazily on first real use

Unload:

- use the unload command to unload the main model and free RAM

### Tool System

The agent includes a pluggable tool system for actions like running commands, reading and writing files, and searching the codebase.

Available tools:

| Tool | Description | Read-Only | Approval Required |
|------|-------------|-----------|-------------------|
| `bash` | Execute shell commands | No | Yes |
| `read_file` | Read file contents | Yes | No |
| `write_file` | Create/overwrite files | No | Yes |
| `edit_file` | String replacement edits | No | Yes |
| `delete_file` | Delete files/directories | No | Yes |
| `move_file` | Move/rename files | No | Yes |
| `list_directory` | List directory contents | Yes | No |
| `glob` | Find files by pattern | Yes | No |
| `grep` | Search file contents | Yes | No |
| `find_definition` | Find function/class definitions | Yes | No |

Security properties:

- file operations validate paths stay within workspace
- dangerous shell commands are blocked
- destructive actions require approval
- tools are scoped to the workspace directory

See [TOOLS.md](TOOLS.md) for detailed tool documentation and usage examples.

## Model Parameters

All parameters are configurable via environment variables. See [CONFIGURATION.md](CONFIGURATION.md) for the full reference.

### Qwen3-14B-Instruct (Single Model)

```python
MODEL_PATH = "models/qwen3/Qwen3-14B-Instruct-Q4_K_M.gguf"
MODEL_N_CTX = 8192
MODEL_N_THREADS = 4
MODEL_CODE_MAX_TOKENS = 1024
MODEL_CODE_TEMPERATURE = 0.2
MODEL_CODE_TOP_P = 0.9
MODEL_CODE_REPEAT_PENALTY = 1.1
```

### Configuration

Parameters are centralized in `scripts/config.py` and can be overridden via environment variables:

```bash
# Increase output tokens
export AI_AGENT_MODEL_CODE_MAX_TOKENS=2048

# Disable auto-unload
export AI_AGENT_AUTO_UNLOAD_ENABLED=false
```

## JSON-RPC Protocol

Communication between TypeScript and Python uses JSON-RPC 2.0 over stdin/stdout.

### Methods

| Method | Description | Timeout |
|--------|-------------|---------|
| `ping` | Health check | - |
| `warm_up` | Pre-load the main model | 120s |
| `chat` | Conversation with the agent | 60s |
| `normalize_task` | Convert conversation to a task spec | 60s |
| `execute` | Generate code changes | 180s |
| `agent_turn` | Run one agentic turn with tools and transcript state | 180s |
| `review` | Review diff for correctness | 60s |
| `validate` | Validate Python syntax before writing | 10s |
| `unload` | Unload the main model to free RAM | 10s |
| `model_status` | Get main model load state and idle time | 5s |
| `set_workspace` | Set workspace root for tools | 5s |
| `list_tools` | List available tools with schemas | 5s |
| `execute_tool` | Execute a tool by name | varies |

### Example Request

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "chat",
  "params": {
    "message": "Add a logging statement",
    "history": []
  }
}
```

### Example Response

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": "I understand you want to add logging. Which function should I add it to?",
  "error": null
}
```

## Error Handling

1. **LLM response validation** - all model responses are validated before accessing nested fields
2. **Syntax validation** - Python files are validated with `ast.parse()` before writing to disk
3. **Exception wrapping** - `handle_message()` catches exceptions and returns JSON-RPC errors
4. **Logging** - operations are logged to stderr for debugging
5. **Graceful degradation** - warm-up failure does not block usage

## Security Hardening

The codebase includes defense-in-depth protections.

### Path Traversal Protection (TypeScript)

All file operations in `SidebarProvider.ts` validate paths stay within the workspace:

```typescript
function validatePathInWorkspace(filePath: string, workspaceRoot: string): string {
  const resolved = path.resolve(workspaceRoot, filePath);
  const normalizedRoot = path.resolve(workspaceRoot);
  if (!resolved.startsWith(normalizedRoot + path.sep) && resolved !== normalizedRoot) {
    throw new Error(`Path traversal blocked: "${filePath}" escapes workspace`);
  }
  return resolved;
}
```

Applied to:

- `addFile()`
- `applyDiff()`
- `handleApply()`

### Input Validation (Python)

The code generation path enforces limits to prevent resource exhaustion:

| Limit | Value | Purpose |
|-------|-------|---------|
| `MAX_TASK_LENGTH` | 10KB | Prevent prompt injection |
| `MAX_FILES` | 100 | Limit batch size |
| `MAX_TOTAL_FILE_SIZE` | 50MB | Prevent memory exhaustion |

### LLM Output Validation

`_parse_file_blocks()` validates model output so the model cannot reference files outside the allowed set:

- rejects absolute paths such as `/etc/passwd`
- rejects path traversal such as `../../../etc/passwd`
- only allows files from the original input set

### Defense-in-Depth Validation

Generated code is validated at multiple points:

1. generation output is parsed and reconstructed
2. Python syntax is validated before returning changes
3. frontend validation runs before apply
4. files are only written after validation passes

## File Structure

```text
local-mega-coding-agent/
|-- models/
|   `-- qwen3/
|       `-- Qwen3-14B-Instruct-Q4_K_M.gguf
|-- scripts/
|   |-- backend/
|   |   |-- wrapper.py          # JSON-RPC router
|   |   `-- model_manager.py    # Model lifecycle management
|   |-- agent/
|   |   |-- turn_runner.py      # Agentic loop execution
|   |   |-- router.py           # Tool relevance scoring
|   |   |-- context.py          # SessionContext
|   |   `-- history.py          # HistoryLog
|   |-- chunker/
|   |   |-- __init__.py
|   |   |-- python_chunker.py   # AST-based Python parsing
|   |   |-- selector.py         # Chunk relevance selection
|   |   `-- reconstructor.py    # File reconstruction
|   |-- critic/
|   |   `-- critic.py           # Internal chat and review codepaths
|   |-- executor/
|   |   `-- executor.py         # Internal code generation codepaths
|   |-- memory/
|   |   `-- context_manager.py  # Local context and memory utilities
|   |-- tools/
|   |   |-- __init__.py
|   |   |-- base.py             # Tool, ToolResult, ToolParameter
|   |   |-- registry.py         # ToolRegistry singleton
|   |   |-- bash.py             # Shell command execution
|   |   |-- file_ops.py         # File operations
|   |   `-- search.py           # Glob, grep, find_definition
|   `-- config.py               # Central configuration
|-- vscode-ai-agent/
|   |-- src/
|   |   |-- extension.ts        # Entry point
|   |   |-- SidebarProvider.ts  # UI and flow logic
|   |   `-- pythonBackend.ts    # IPC client
|   `-- package.json
|-- docs/
|   |-- ARCHITECTURE.md         # This file
|   |-- CONFIGURATION.md        # Configuration reference
|   `-- TOOLS.md                # Tool system documentation
|-- tests/
|   |-- test_executor.py        # Executor security tests
|   `-- test_tools.py           # Tool system tests
|-- setup_models.py             # Model download script
|-- README.md                   # Project overview
|-- CONTRIBUTING.md             # Contribution guidelines
`-- LICENSE                     # MIT license
```

## Troubleshooting

### Model Loading Fails

- Check that the model file exists in `models/qwen3/`
- Run `python setup_models.py` to download it
- Check disk space (~9GB needed for the default model)

### Slow First Response

- The main model may warm up on activation
- Check Output panel for warm-up messages
- If warm-up fails, the model loads on first use

### Diff Application Fails

- Ensure the file has not changed since selection
- Check that diff parsing handles the returned patch format
