# Local AI Agent - Architecture

## Overview

A VSCode extension that provides a local AI coding assistant using two locally-running LLMs:
- **LLaMA 3.1 8B** (Instruct, Q4_K_M) - Chat and code review
- **DeepSeek Coder 6.7B** (Instruct, Q4_K_M) - Code generation

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
│  └───────────┬────────────────────────────────────┬──────────────┘  │
│              │                                    │                  │
│  ┌───────────┴───────────┐          ┌─────────────┴─────────────┐   │
│  │     critic.py         │          │      executor.py          │   │
│  │  ┌─────────────────┐  │          │  ┌─────────────────────┐  │   │
│  │  │  LLaMA 3.1 8B   │  │          │  │  DeepSeek 6.7B      │  │   │
│  │  │  (Chat/Review)  │  │          │  │  (Code Generation)  │  │   │
│  │  └─────────────────┘  │          │  └─────────────────────┘  │   │
│  │                       │          │                           │   │
│  │  - chat()             │          │  - execute()              │   │
│  │  - review_diff()      │          │  - _execute_chunked()     │   │
│  │  - normalize_task()   │          │  - _build_prompt()        │   │
│  └───────────────────────┘          │  - _synthesize_diffs()    │   │
│                                     └───────────────────────────┘   │
│                                                                     │
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
2. CHAT             →  User describes task, LLaMA clarifies intent
3. PROCEED          →  normalize_task() creates clean spec
4. EXECUTE          →  DeepSeek generates code, executor creates diff
5. REVIEW           →  LLaMA reviews diff for correctness (PASS/FAIL)
6. APPLY/REJECT     →  User decides, changes applied to files
```

## Key Design Decisions

### Why Two Models?

| Task | Model | Why |
|------|-------|-----|
| Chat | LLaMA 3.1 8B | Better at conversation, clarifying questions |
| Code Gen | DeepSeek 6.7B | Trained specifically for code, follows output format |
| Review | LLaMA 3.1 8B | General reasoning about correctness |

### Prompt Format for DeepSeek

DeepSeek Coder Instruct uses **Alpaca-style format**:

```
### Instruction:
Apply the following task to the provided files. Output ONLY the complete modified file contents.
Use this exact format for each file you modify:

FILE: <path>
<complete file contents>

Do not include explanations, markdown, or any other text.

### Task:
{task description}

### Input Files:
FILE: path/to/file.py
{file contents}

### Response:
```

**Why Alpaca format?**
- DeepSeek follows it reliably
- Clear separation of instruction vs input vs output
- Stop tokens (`### Instruction`, `### Explanation`) prevent rambling

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
│  │ imports │ │ func_b  │  → Sent to DeepSeek                    │
│  │ 20 lines│ │ 80 lines│                                        │
│  └─────────┘ └─────────┘                                        │
└─────────────────────────────────────────────────────────────────┘
```

**How it works:**
1. `python_chunker.py` parses file using Python's `ast` module
2. `selector.py` matches task keywords to chunk names
3. Only relevant chunks sent to DeepSeek (CHUNK: format)
4. `reconstructor.py` splices modified chunks back into full file

**Fallback:** Non-Python files use full-file mode.

### Diff Generation is Local

DeepSeek outputs **full file contents** (or chunks), not diffs. The executor:
1. Parses `FILE:` or `CHUNK:` blocks from output
2. Reconstructs full file if using chunks
3. Uses Python's `difflib` to generate unified diffs
4. Returns diff to frontend for review

This is deterministic and avoids LLM hallucinating diff syntax.

### Model Lifecycle Management

Models are managed by a centralized `ModelManager` singleton that handles:
- Lazy loading on first access
- Access timestamp tracking
- Automatic unloading after idle timeout
- Manual unload via commands

```python
from scripts.backend.model_manager import get_manager, ModelType

manager = get_manager()
manager.register_model(ModelType.CRITIC, path, config, loader_fn)

# Lazy load and track access
model = manager.get_model(ModelType.CRITIC)

# Check status
status = manager.get_status()  # {critic: {loaded, idle_seconds}, ...}

# Manual unload to free RAM
manager.unload_model(ModelType.CRITIC)
```

**Key features:**
- **Thread-safe singleton**: Safe for concurrent access
- **Lazy loading**: Models only load when first accessed
- **Access tracking**: Timestamps updated on each `get_model()` call
- **Auto-unload**: Background thread unloads models idle > 15 minutes (configurable)
- **Memory cleanup**: Uses `gc.collect()` twice after deletion

**Warm-up**: On extension activation, `warm_up()` pre-loads both models to eliminate first-request latency (10-20s).

**Unloading**: Use `AI Agent: Unload Models` command or wait for auto-unload to free ~8-10GB RAM.

## Model Parameters

All parameters are configurable via environment variables. See [CONFIGURATION.md](CONFIGURATION.md) for full reference.

### LLaMA (Critic)
```python
n_ctx=4096      # Context window (sufficient for chat)
n_threads=4     # CPU threads
max_tokens=512  # Response length (chat)
temperature=0.7 # Moderate creativity for conversation
```

### DeepSeek (Executor)
```python
n_ctx=8192      # Larger context for file contents
n_threads=4     # CPU threads
max_tokens=1024 # Longer for full file output
temperature=0.2 # Low - we want deterministic code
top_p=0.9
repeat_penalty=1.1  # Prevents code repetition
stop=["</s>", "<|EOT|>", "### Instruction", "### Explanation"]
```

### Configuration

Parameters are centralized in `scripts/config.py` and can be overridden via environment variables:

```bash
# Increase output tokens
export AI_AGENT_DEEPSEEK_MAX_TOKENS=2048

# Disable auto-unload
export AI_AGENT_AUTO_UNLOAD_ENABLED=false
```

## JSON-RPC Protocol

Communication between TypeScript and Python uses JSON-RPC 2.0 over stdin/stdout.

### Methods

| Method | Description | Timeout |
|--------|-------------|---------|
| `ping` | Health check | - |
| `warm_up` | Pre-load models | 120s |
| `chat` | Conversation with critic | 60s |
| `normalize_task` | Convert conversation to spec | 60s |
| `execute` | Generate code changes | 180s |
| `review` | Review diff for correctness | 60s |
| `validate` | Validate Python syntax before writing | 10s |
| `unload` | Unload models to free RAM | 10s |
| `model_status` | Get model load state and idle time | 5s |

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
5. **Graceful Degradation**: Warm-up failures don't block usage (models load on first use)

### Defense-in-Depth Validation

Generated code is validated at multiple points:

```
DeepSeek Output
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
local-ai-agent/
├── models/
│   ├── llama/
│   │   └── Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf
│   └── deepseek/
│       └── deepseek-coder-6.7b-instruct.Q4_K_M.gguf
├── scripts/
│   ├── backend/
│   │   ├── wrapper.py          # JSON-RPC router
│   │   └── model_manager.py    # Model lifecycle management
│   ├── chunker/
│   │   ├── __init__.py         # Package exports
│   │   ├── python_chunker.py   # AST-based Python parsing
│   │   ├── selector.py         # Chunk relevance selection
│   │   └── reconstructor.py    # File reconstruction
│   ├── critic/
│   │   └── critic.py           # LLaMA interface
│   ├── executor/
│   │   └── executor.py         # DeepSeek interface
│   ├── memory/
│   │   └── context_manager.py  # Session persistence
│   └── config.py               # Central configuration
├── vscode-ai-agent/
│   ├── src/
│   │   ├── extension.ts        # Entry point
│   │   ├── SidebarProvider.ts  # UI + flow logic
│   │   └── pythonBackend.ts    # IPC client
│   └── package.json
├── docs/
│   ├── ARCHITECTURE.md         # This file
│   └── CONFIGURATION.md        # Configuration reference
├── tests/                      # Test files
├── setup_models.py             # Model download script
├── README.md                   # Project overview
├── CONTRIBUTING.md             # Contribution guidelines
└── LICENSE                     # MIT license
```

## Troubleshooting

### Model Loading Fails
- Check model files exist in `models/` directory
- Run `python scripts/setup_models.py` to download
- Check disk space (~8GB needed for both models)

### Slow First Response
- Models should warm up on activation
- Check Output panel for "Warming up AI models..."
- If warm-up fails, models load on first use (10-20s delay)

### Code Generation Returns Garbage
- Check DeepSeek is using Alpaca format (not chat completion)
- Temperature should be low (0.2)
- Check stop tokens include `### Instruction`

### Diff Application Fails
- Ensure file hasn't changed since selection
- Check diff parsing handles both `--- path` and `--- a/path` formats
