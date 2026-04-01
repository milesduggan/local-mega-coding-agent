# Local AI Agent - Architecture

## Overview

A VSCode extension that provides a local AI coding assistant using a single locally-running LLM:
- **Qwen3-14B-Instruct** (Q4_K_M) - Chat, code generation, and code review

All inference runs locally. No data leaves your machine.

## Component Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│  VSCode Extension (TypeScript)                                       │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐      │
│  │ SidebarProvider │  │  extension.ts   │  │ pythonBackend.ts│      │
│  │   (UI + Flow)   │  │   (Commands)    │  │  (IPC Client)   │      │
│  └────────┬────────┘  └─────────────────┘  └────────┬────────┘      │
│           │                                          │               │
│           └──────────────────────────────────────────┘               │
│                              │                                       │
│                    JSON-RPC 2.0 over stdin/stdout                    │
└──────────────────────────────┼───────────────────────────────────────┘
                               │
┌──────────────────────────────┼───────────────────────────────────────┐
│  Python Backend              │                                       │
│  ┌───────────────────────────┴───────────────────────────────────┐  │
│  │                       wrapper.py                               │  │
│  │                   (JSON-RPC Router)                            │  │
│  └───────────┬───────────────────────────────────────────────────┘  │
│              │                                                       │
│  ┌───────────┴───────────────────────────────────────────────────┐  │
│  │                   scripts/agent/                               │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────┐   │  │
│  │  │ TurnRunner  │  │   Router    │  │   SessionContext /    │   │  │
│  │  │ (agentic    │  │ (tool call  │  │   HistoryLog         │   │  │
│  │  │  loop)      │  │  dispatch)  │  │   (session state)    │   │  │
│  │  └──────┬──────┘  └──────┬──────┘  └──────────────────────┘   │  │
│  │         │                │                                      │  │
│  │         └────────────────┘                                      │  │
│  │                  │                                               │  │
│  │         ┌────────┴────────┐                                      │  │
│  │         │  Qwen3-14B      │                                      │  │
│  │         │  (Chat / Code   │                                      │  │
│  │         │   Gen / Review) │                                      │  │
│  │         └─────────────────┘                                      │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                  scripts/critic/ + executor/                   │  │
│  │  - critic.py    → Chat and diff review (PASS/FAIL)            │  │
│  │  - executor.py  → Code generation, diff synthesis             │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                    chunker/ (Token Optimizer)                  │  │
│  │  - python_chunker.py  → Parse Python into chunks (AST)        │  │
│  │  - selector.py        → Select relevant chunks for task       │  │
│  │  - reconstructor.py   → Rebuild file from modified chunks     │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

## User Flow

```
1. SELECT FILES     →  User adds files via context menu or command palette
2. CHAT             →  User describes task, Qwen3 clarifies intent
3. PROCEED          →  normalize_task() creates clean spec
4. AGENTIC LOOP     →  TurnRunner dispatches tool calls (read, write, bash, etc.)
                        each turn produces a diff; Router routes tool requests
5. REVIEW           →  Qwen3 reviews diff for correctness (PASS/FAIL)
6. APPLY/REJECT     →  User decides, changes applied to files
```

## Key Design Decisions

### Why Single Model?

Using one model for all tasks (chat, code generation, review) offers significant advantages:

| Benefit | Detail |
|---------|--------|
| Simpler architecture | No coordination between two separate models |
| Lower RAM usage | One 14B model loaded instead of two smaller models |
| Consistent reasoning | Same model that understands the task also writes and reviews the code |
| Easier configuration | Single MODEL_* parameter block |

Qwen3-14B-Instruct handles conversation, code generation, and diff review with high quality across all three tasks.

### Chunk-Based Execution (Token Optimization)

For Python files, the executor uses AST-based chunking to reduce token usage:

```
┌─────────────────────────────────────────────────────────────────┐
│  Full File (300 lines)                                          │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌──────────┐  │
│  │ imports │ │ func_a  │ │ func_b  │ │ Class_C │ │ func_d   │  │
│  │ 20 lines│ │ 50 lines│ │ 80 lines│ │ 100 line│ │ 50 lines │  │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └──────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
        Task: "Add logging to func_b"
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Selected Chunks (100 lines = 67% savings)                      │
│  ┌─────────┐ ┌─────────┐                                        │
│  │ imports │ │ func_b  │  → Sent to Qwen3                       │
│  │ 20 lines│ │ 80 lines│                                        │
│  └─────────┘ └─────────┘                                        │
└─────────────────────────────────────────────────────────────────┘
```

**How it works:**
1. `python_chunker.py` parses file using Python's `ast` module
2. `selector.py` matches task keywords to chunk names
3. Only relevant chunks sent to Qwen3 (CHUNK: format)
4. `reconstructor.py` splices modified chunks back into full file

**Fallback:** Non-Python files use full-file mode.

### Diff Generation is Local

The model outputs **full file contents** (or chunks), not diffs. The executor:
1. Parses `FILE:` or `CHUNK:` blocks from output
2. Reconstructs full file if using chunks
3. Uses Python's `difflib` to generate unified diffs
4. Returns diff to frontend for review

This is deterministic and avoids the model hallucinating diff syntax.

### Model Lifecycle Management

The model is managed by a centralized `ModelManager` singleton that handles:
- Lazy loading on first access
- Access timestamp tracking
- Automatic unloading after idle timeout
- Manual unload via commands

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

**Key features:**
- **Thread-safe singleton**: Safe for concurrent access
- **Lazy loading**: Model only loads when first accessed
- **Access tracking**: Timestamps updated on each `get_model()` call
- **Auto-unload**: Background thread unloads model idle > 15 minutes (configurable)
- **Memory cleanup**: Uses `gc.collect()` twice after deletion

**Warm-up**: On extension activation, `warm_up()` pre-loads the model to eliminate first-request latency (10-20s).

**Unloading**: Use `AI Agent: Unload Models` command or wait for auto-unload to free ~8-10GB RAM.

### Tool System

The agent includes a pluggable tool system for executing actions like running commands, reading/writing files, and searching the codebase.

```
┌─────────────────────────────────────────────────────────────────┐
│  Tool Registry (Singleton)                                       │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐               │
│  │  BashTool   │ │ ReadFile    │ │  GlobTool   │  ...          │
│  └─────────────┘ └─────────────┘ └─────────────┘               │
│                                                                  │
│  registry.execute("bash", {"command": "npm test"})              │
│         ↓                                                        │
│  ToolResult(success=True, output="...", metadata={...})         │
└─────────────────────────────────────────────────────────────────┘
```

**Available Tools:**

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

**Tool Security:**

- All file operations validate paths stay within workspace
- Dangerous bash commands are blocked (rm -rf /, fork bombs, curl|sh, etc.)
- Destructive commands are flagged for caution
- Tools can only operate within the workspace directory

See [TOOLS.md](TOOLS.md) for detailed tool documentation and usage examples.

## Model Parameters

All parameters are configurable via environment variables. See [CONFIGURATION.md](CONFIGURATION.md) for full reference.

### Qwen3-14B-Instruct (Single Model)
```python
MODEL_PATH     = "models/qwen3/Qwen3-14B-Instruct-Q4_K_M.gguf"
MODEL_N_CTX    = 8192       # Context window (chat + file contents)
MODEL_N_THREADS = 4         # CPU threads
MODEL_MAX_TOKENS = 1024     # Response length
MODEL_TEMPERATURE = 0.2     # Low for deterministic code generation
MODEL_TOP_P    = 0.9
MODEL_REPEAT_PENALTY = 1.1  # Prevents repetition
```

### Configuration

Parameters are centralized in `scripts/config.py` and can be overridden via environment variables:

```bash
# Increase output tokens
export AI_AGENT_MODEL_MAX_TOKENS=2048

# Disable auto-unload
export AI_AGENT_AUTO_UNLOAD_ENABLED=false
```

## JSON-RPC Protocol

Communication between TypeScript and Python uses JSON-RPC 2.0 over stdin/stdout.

### Methods

| Method | Description | Timeout |
|--------|-------------|---------|
| `ping` | Health check | - |
| `warm_up` | Pre-load model | 120s |
| `chat` | Conversation with agent | 60s |
| `normalize_task` | Convert conversation to spec | 60s |
| `execute` | Generate code changes | 180s |
| `agent_turn` | Run one agentic loop turn (tools → diff) | 180s |
| `review` | Review diff for correctness | 60s |
| `validate` | Validate Python syntax before writing | 10s |
| `unload` | Unload model to free RAM | 10s |
| `model_status` | Get model load state and idle time | 5s |
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

1. **LLM Response Validation**: All model responses are validated before accessing nested fields
2. **Syntax Validation**: Python files validated with `ast.parse()` before writing to disk
3. **Exception Wrapping**: `handle_message()` catches all exceptions and returns JSON-RPC errors
4. **Logging**: All operations logged to stderr for debugging
5. **Graceful Degradation**: Warm-up failures don't block usage (model loads on first use)

### Security Hardening

The codebase includes defense-in-depth security measures:

**Path Traversal Protection (TypeScript)**

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

Applied to: `addFile()`, `applyDiff()`, `handleApply()`

**Input Validation (Python)**

The executor enforces limits to prevent resource exhaustion:

| Limit | Value | Purpose |
|-------|-------|---------|
| `MAX_TASK_LENGTH` | 10KB | Prevent prompt injection |
| `MAX_FILES` | 100 | Limit batch size |
| `MAX_TOTAL_FILE_SIZE` | 50MB | Prevent memory exhaustion |

**LLM Output Validation**

`_parse_file_blocks()` validates model output to prevent the model from referencing files outside the allowed set:
- Rejects absolute paths (`/etc/passwd`)
- Rejects path traversal (`../../../etc/passwd`)
- Only allows files from the original input set

### Defense-in-Depth Validation

Generated code is validated at multiple points:

```
Qwen3 Output
    ↓
[Chunk-based?] → reconstruct_file() → ast.parse() ✓
    ↓
[Full-file?] → _parse_file_blocks() → ast.parse() ✓
    ↓
User clicks "Apply"
    ↓
validateFiles() RPC → ast.parse() ✓  (TypeScript-side)
    ↓
fs.writeFileSync()
```

## File Structure

```
local-mega-coding-agent/
├── models/
│   └── qwen3/
│       └── Qwen3-14B-Instruct-Q4_K_M.gguf
├── scripts/
│   ├── backend/
│   │   ├── wrapper.py          # JSON-RPC router
│   │   └── model_manager.py    # Model lifecycle management
│   ├── agent/
│   │   ├── turn_runner.py      # Agentic loop execution
│   │   ├── router.py           # Tool call dispatch
│   │   ├── context.py          # SessionContext (per-session state)
│   │   └── history.py          # HistoryLog (turn history)
│   ├── chunker/
│   │   ├── __init__.py         # Package exports
│   │   ├── python_chunker.py   # AST-based Python parsing
│   │   ├── selector.py         # Chunk relevance selection
│   │   └── reconstructor.py    # File reconstruction
│   ├── critic/
│   │   └── critic.py           # Chat and diff review interface
│   ├── executor/
│   │   └── executor.py         # Code generation and diff synthesis
│   ├── memory/
│   │   └── context_manager.py  # Session persistence
│   ├── tools/
│   │   ├── __init__.py         # Package exports
│   │   ├── base.py             # Tool, ToolResult, ToolParameter
│   │   ├── registry.py         # ToolRegistry singleton
│   │   ├── bash.py             # Shell command execution
│   │   ├── file_ops.py         # File operations (read, write, edit, etc.)
│   │   └── search.py           # Glob, grep, find_definition
│   └── config.py               # Central configuration
├── vscode-ai-agent/
│   ├── src/
│   │   ├── extension.ts        # Entry point
│   │   ├── SidebarProvider.ts  # UI + flow logic
│   │   └── pythonBackend.ts    # IPC client
│   └── package.json
├── docs/
│   ├── ARCHITECTURE.md         # This file
│   ├── CONFIGURATION.md        # Configuration reference
│   └── TOOLS.md                # Tool system documentation
├── tests/
│   ├── test_executor.py        # Unit tests for executor security
│   └── test_tools.py           # Unit tests for tool system (52 tests)
├── setup_models.py             # Model download script
├── README.md                   # Project overview
├── CONTRIBUTING.md             # Contribution guidelines
└── LICENSE                     # MIT license
```

## Troubleshooting

### Model Loading Fails
- Check model file exists in `models/qwen3/` directory
- Run `python setup_models.py` to download
- Check disk space (~9GB needed for the model)

### Slow First Response
- Model should warm up on activation
- Check Output panel for "Warming up AI models..."
- If warm-up fails, model loads on first use (10-20s delay)

### Diff Application Fails
- Ensure file hasn't changed since selection
- Check diff parsing handles both `--- path` and `--- a/path` formats
