# Agentic Turn Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-pass agent pipeline with a multi-turn TurnRunner that calls tools autonomously, builds a session transcript, and migrates to a single Qwen2.5-Coder 7B model.

**Architecture:** A new `TurnRunner` class owns a loop (up to `MAX_AGENT_TURNS=10`) where the model issues structured tool calls, read-only tools execute silently, and write/bash tools pause for user approval. After the loop, the existing executor and reviewer run as before. A new `agent_turn` JSON-RPC endpoint in `wrapper.py` exposes this to the VS Code extension, which renders a collapsible transcript and an approval UI.

**Tech Stack:** Python 3.10+, llama-cpp-python, Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf, TypeScript/VS Code WebviewAPI

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `scripts/config.py` | Replace DEEPSEEK_*/LLAMA_* with MODEL_*, add MAX_AGENT_TURNS |
| Modify | `scripts/backend/model_manager.py` | Single ModelType.MAIN enum value |
| Modify | `scripts/critic/critic.py` | Use MODEL_* config + ModelType.MAIN |
| Modify | `scripts/executor/executor.py` | Use MODEL_* config + ModelType.MAIN |
| Modify | `setup_models.py` | Download Qwen2.5-Coder 7B only |
| Create | `scripts/agent/history.py` | HistoryLog event accumulator |
| Create | `scripts/agent/router.py` | Token-scoring tool router |
| Create | `scripts/agent/context.py` | SessionContext builder |
| Create | `scripts/agent/turn_runner.py` | Multi-turn loop with approval gate |
| Modify | `scripts/agent/main.py` | Delegate agent_loop to TurnRunner |
| Modify | `scripts/backend/wrapper.py` | Add agent_turn RPC handler |
| Modify | `vscode-ai-agent/src/SidebarProvider.ts` | Transcript + approval UI |
| Create | `tests/test_history.py` | HistoryLog unit tests |
| Create | `tests/test_router.py` | Router unit tests |
| Create | `tests/test_context.py` | SessionContext unit tests |
| Create | `tests/test_turn_runner.py` | TurnRunner unit tests (all stop reasons) |
| Create | `tests/test_tool_registry_parity.py` | Registry completeness check |

---

## Task 1: Migrate config.py to single model block

**Files:**
- Modify: `scripts/config.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_config_migration.py`:

```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_model_config_exists():
    from scripts import config
    assert hasattr(config, "MODEL_PATH")
    assert hasattr(config, "MODEL_N_CTX")
    assert hasattr(config, "MODEL_N_THREADS")
    assert hasattr(config, "MODEL_CHAT_MAX_TOKENS")
    assert hasattr(config, "MODEL_CHAT_TEMPERATURE")
    assert hasattr(config, "MODEL_CODE_MAX_TOKENS")
    assert hasattr(config, "MODEL_CODE_TEMPERATURE")
    assert hasattr(config, "MODEL_REVIEW_MAX_TOKENS")
    assert hasattr(config, "MODEL_REVIEW_TEMPERATURE")
    assert hasattr(config, "MODEL_NORMALIZE_MAX_TOKENS")
    assert hasattr(config, "MODEL_NORMALIZE_TEMPERATURE")
    assert hasattr(config, "MAX_AGENT_TURNS")

def test_old_config_gone():
    from scripts import config
    assert not hasattr(config, "DEEPSEEK_N_CTX")
    assert not hasattr(config, "LLAMA_N_CTX")
    assert not hasattr(config, "DEEPSEEK_MODEL_PATH")
    assert not hasattr(config, "LLAMA_MODEL_PATH")

def test_max_agent_turns_default():
    from scripts import config
    assert config.MAX_AGENT_TURNS == 10
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_config_migration.py -v
```
Expected: FAIL — `MODEL_PATH` not found, `DEEPSEEK_N_CTX` still exists

- [ ] **Step 3: Replace scripts/config.py**

Replace the entire file with:

```python
"""
Central configuration for model parameters.

All values can be overridden via environment variables prefixed with AI_AGENT_.
"""

import os


def _get_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


# =============================================================================
# Model Settings (Qwen2.5-Coder 7B-Instruct)
# =============================================================================

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MODEL_PATH = os.environ.get(
    "AI_AGENT_MODEL_PATH",
    os.path.join(_PROJECT_ROOT, "models", "qwen", "qwen2.5-coder-7b-instruct-q4_k_m.gguf")
)

# Context window — larger allows more file content but uses more RAM
MODEL_N_CTX = _get_int("AI_AGENT_MODEL_N_CTX", 8192)

# CPU threads for inference
MODEL_N_THREADS = _get_int("AI_AGENT_MODEL_N_THREADS", 4)

# Chat role — moderate creativity for conversation
MODEL_CHAT_MAX_TOKENS = _get_int("AI_AGENT_MODEL_CHAT_MAX_TOKENS", 512)
MODEL_CHAT_TEMPERATURE = _get_float("AI_AGENT_MODEL_CHAT_TEMPERATURE", 0.7)

# Code generation role — low temperature for determinism
MODEL_CODE_MAX_TOKENS = _get_int("AI_AGENT_MODEL_CODE_MAX_TOKENS", 1024)
MODEL_CODE_TEMPERATURE = _get_float("AI_AGENT_MODEL_CODE_TEMPERATURE", 0.2)

# Review role — conservative for correctness judgments
MODEL_REVIEW_MAX_TOKENS = _get_int("AI_AGENT_MODEL_REVIEW_MAX_TOKENS", 256)
MODEL_REVIEW_TEMPERATURE = _get_float("AI_AGENT_MODEL_REVIEW_TEMPERATURE", 0.3)

# Task normalization role — low temp for consistent format
MODEL_NORMALIZE_MAX_TOKENS = _get_int("AI_AGENT_MODEL_NORMALIZE_MAX_TOKENS", 300)
MODEL_NORMALIZE_TEMPERATURE = _get_float("AI_AGENT_MODEL_NORMALIZE_TEMPERATURE", 0.2)

# Turn loop role — moderate for tool call decisions
MODEL_TURN_MAX_TOKENS = _get_int("AI_AGENT_MODEL_TURN_MAX_TOKENS", 512)
MODEL_TURN_TEMPERATURE = _get_float("AI_AGENT_MODEL_TURN_TEMPERATURE", 0.4)

# =============================================================================
# Agentic Loop Settings
# =============================================================================

# Maximum turns before giving up and returning max_turns_reached
MAX_AGENT_TURNS = _get_int("AI_AGENT_MAX_TURNS", 10)

# =============================================================================
# Chunker Settings
# =============================================================================

CHUNK_MAX_TOKENS = _get_int("AI_AGENT_CHUNK_MAX_TOKENS", 3000)

# =============================================================================
# Timeout Settings (milliseconds)
# =============================================================================

TIMEOUT_CHAT_MS = _get_int("AI_AGENT_TIMEOUT_CHAT_MS", 60000)
TIMEOUT_NORMALIZE_MS = _get_int("AI_AGENT_TIMEOUT_NORMALIZE_MS", 60000)
TIMEOUT_EXECUTE_MS = _get_int("AI_AGENT_TIMEOUT_EXECUTE_MS", 180000)
TIMEOUT_REVIEW_MS = _get_int("AI_AGENT_TIMEOUT_REVIEW_MS", 60000)
TIMEOUT_WARMUP_MS = _get_int("AI_AGENT_TIMEOUT_WARMUP_MS", 120000)

# =============================================================================
# Model Lifecycle Settings
# =============================================================================

MODEL_IDLE_TIMEOUT_MINUTES = _get_int("AI_AGENT_MODEL_IDLE_TIMEOUT_MINUTES", 15)
AUTO_UNLOAD_ENABLED = os.environ.get(
    "AI_AGENT_AUTO_UNLOAD_ENABLED", "true"
).lower() in ("1", "true", "yes")

# =============================================================================
# Debug Settings
# =============================================================================

DEBUG_LOG_LLM_IO = os.environ.get("AI_AGENT_DEBUG_LOG_LLM_IO", "").lower() in ("1", "true", "yes")
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_config_migration.py -v
```
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/config.py tests/test_config_migration.py
git commit -m "refactor: migrate config to single MODEL_* block, add MAX_AGENT_TURNS"
```

---

## Task 2: Migrate model_manager.py to single ModelType

**Files:**
- Modify: `scripts/backend/model_manager.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config_migration.py`:

```python
def test_model_type_single():
    from scripts.backend.model_manager import ModelType
    assert hasattr(ModelType, "MAIN")
    assert not hasattr(ModelType, "CRITIC")
    assert not hasattr(ModelType, "EXECUTOR")
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_config_migration.py::test_model_type_single -v
```
Expected: FAIL — `ModelType` has no `MAIN` attribute

- [ ] **Step 3: Update model_manager.py**

Replace the `ModelType` enum and its docstring at the top of the file:

```python
class ModelType(Enum):
    """Single model type — Qwen2.5-Coder handles all roles."""
    MAIN = "main"
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_config_migration.py -v
```
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/backend/model_manager.py tests/test_config_migration.py
git commit -m "refactor: collapse ModelType to single MAIN value"
```

---

## Task 3: Update critic.py for single model

**Files:**
- Modify: `scripts/critic/critic.py`

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_config_migration.py — add:
def test_critic_uses_model_config():
    import inspect, scripts.critic.critic as c
    src = inspect.getsource(c)
    assert "MODEL_PATH" in src
    assert "MODEL_N_CTX" in src
    assert "ModelType.MAIN" in src
    assert "LLAMA_" not in src
    assert "ModelType.CRITIC" not in src
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_config_migration.py::test_critic_uses_model_config -v
```
Expected: FAIL

- [ ] **Step 3: Update the imports and model registration in critic.py**

Replace the import block (lines starting with `from scripts.config import` through `_manager.register_model(...)`):

```python
from scripts.config import (
    MODEL_N_CTX, MODEL_N_THREADS,
    MODEL_CHAT_MAX_TOKENS, MODEL_CHAT_TEMPERATURE,
    MODEL_REVIEW_MAX_TOKENS, MODEL_REVIEW_TEMPERATURE,
    MODEL_NORMALIZE_MAX_TOKENS, MODEL_NORMALIZE_TEMPERATURE,
    MODEL_PATH,
)
from scripts.backend.model_manager import get_manager, ModelType

log = logging.getLogger(__name__)

STORAGE_DIR = os.path.join(_PROJECT_ROOT, ".ai-agent-memory")
HANDOFF_PHRASE = "Proceed with implementation."

Message = Dict[str, str]
History = List[Message]

_context_manager = None
_manager = get_manager()


def _create_llm() -> Llama:
    return Llama(
        model_path=MODEL_PATH,
        n_ctx=MODEL_N_CTX,
        n_threads=MODEL_N_THREADS,
        verbose=False,
    )


_manager.register_model(
    ModelType.MAIN,
    MODEL_PATH,
    {"n_ctx": MODEL_N_CTX, "n_threads": MODEL_N_THREADS},
    _create_llm
)
```

Replace `_get_llm()`:

```python
def _get_llm() -> Llama:
    return _manager.get_model(ModelType.MAIN)
```

Replace `unload()`:

```python
def unload() -> bool:
    return _manager.unload_model(ModelType.MAIN)
```

Replace `is_loaded()`:

```python
def is_loaded() -> bool:
    return _manager.is_loaded(ModelType.MAIN)
```

In `chat()`, replace `top_p=0.9` block with updated config names — the function body stays the same, just the imported constants change (already imported above).

In `review_diff()`, the function body is unchanged.

In `normalize_task()`, the function body is unchanged.

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_config_migration.py -v
```
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/critic/critic.py tests/test_config_migration.py
git commit -m "refactor: update critic to use single MODEL_* config and ModelType.MAIN"
```

---

## Task 4: Update executor.py for single model

**Files:**
- Modify: `scripts/executor/executor.py`

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_config_migration.py — add:
def test_executor_uses_model_config():
    import inspect, scripts.executor.executor as e
    src = inspect.getsource(e)
    assert "MODEL_PATH" in src
    assert "ModelType.MAIN" in src
    assert "DEEPSEEK_" not in src
    assert "ModelType.EXECUTOR" not in src
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_config_migration.py::test_executor_uses_model_config -v
```
Expected: FAIL

- [ ] **Step 3: Update the imports and model registration in executor.py**

Replace the import block (from `from scripts.config import` through `_manager.register_model(...)`):

```python
from scripts.config import (
    MODEL_N_CTX, MODEL_N_THREADS, MODEL_CODE_MAX_TOKENS,
    MODEL_CODE_TEMPERATURE, MODEL_PATH,
)
from scripts.backend.model_manager import get_manager, ModelType

log = logging.getLogger(__name__)

MAX_TASK_LENGTH = 10_000
MAX_TOTAL_FILE_SIZE = 50_000_000
MAX_FILES = 100


class ExecutionError(Exception):
    pass


_manager = get_manager()


def _create_model() -> Llama:
    return Llama(
        model_path=MODEL_PATH,
        n_ctx=MODEL_N_CTX,
        n_threads=MODEL_N_THREADS,
        verbose=False,
    )


# Register only if not already registered by critic.py
try:
    _manager.register_model(
        ModelType.MAIN,
        MODEL_PATH,
        {"n_ctx": MODEL_N_CTX, "n_threads": MODEL_N_THREADS},
        _create_model
    )
except Exception:
    pass  # Already registered by critic.py — same singleton
```

Replace `_get_deepseek()`:

```python
def _get_deepseek() -> Llama:
    return _manager.get_model(ModelType.MAIN)
```

Replace `unload_executor` / `warm_up` to use `ModelType.MAIN`:

```python
def warm_up() -> bool:
    try:
        _manager.get_model(ModelType.MAIN)
        return True
    except FileNotFoundError as e:
        log.error(f"Model file not found: {e}")
        return False
    except Exception as e:
        log.error(f"Failed to load model: {type(e).__name__}: {e}")
        return False


def unload() -> bool:
    return _manager.unload_model(ModelType.MAIN)
```

Inside the `execute()` function, replace `DEEPSEEK_MAX_TOKENS` and `DEEPSEEK_TEMPERATURE` references with `MODEL_CODE_MAX_TOKENS` and `MODEL_CODE_TEMPERATURE`.

- [ ] **Step 4: Run all existing tests to verify nothing broke**

```
pytest tests/ -v
```
Expected: All existing tests PASS (executor security + tool tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/executor/executor.py tests/test_config_migration.py
git commit -m "refactor: update executor to use single MODEL_* config and ModelType.MAIN"
```

---

## Task 5: Update setup_models.py and README

**Files:**
- Modify: `setup_models.py`
- Modify: `README.md`

- [ ] **Step 1: Replace setup_models.py**

```python
"""
Download Qwen2.5-Coder 7B-Instruct GGUF model for local inference.

Model: Qwen2.5-Coder-7B-Instruct-Q4_K_M (~4.5GB)
Source: Qwen/Qwen2.5-Coder-7B-Instruct-GGUF on Hugging Face
"""

import os
from huggingface_hub import hf_hub_download

MODEL_DIR = os.path.join(os.path.dirname(__file__), "models", "qwen")
os.makedirs(MODEL_DIR, exist_ok=True)

print("Downloading Qwen2.5-Coder-7B-Instruct-Q4_K_M (~4.5GB)...")

hf_hub_download(
    repo_id="Qwen/Qwen2.5-Coder-7B-Instruct-GGUF",
    filename="qwen2.5-coder-7b-instruct-q4_k_m.gguf",
    local_dir=MODEL_DIR,
)

print(f"Model saved to: {MODEL_DIR}")
print("Setup complete.")
```

- [ ] **Step 2: Update README.md hardware requirements table**

Find and replace the Requirements table:

```markdown
## Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| RAM | 8GB | 16GB |
| Disk | 5GB (model) | 6GB |
| Python | 3.10 | 3.11+ |
| VS Code | 1.85 | Latest |
| Node.js | 18+ | 20+ |
```

Update the Features section — replace:
```
- **Dual-Model Architecture** - LLaMA 3.1 8B for chat/review + DeepSeek Coder 6.7B for code generation
```
with:
```
- **Single-Model Architecture** - Qwen2.5-Coder 7B-Instruct for all roles (chat, code, review)
```

Update the How It Works section to remove LLaMA/DeepSeek references:
```
The dual-model approach uses each model's strengths:
- **LLaMA 3.1 8B** excels at conversation and reasoning
- **DeepSeek Coder 6.7B** excels at code generation with predictable output format
```
Replace with:
```
Qwen2.5-Coder 7B-Instruct runs all three roles with different temperature settings:
- **Chat/clarify** — temperature 0.7 for natural conversation
- **Code generation** — temperature 0.2 for deterministic output
- **Review** — temperature 0.3 for conservative correctness judgments
```

- [ ] **Step 3: Update setup instructions in README**

Replace `~8GB total` with `~4.5GB` in the installation steps.

- [ ] **Step 4: Commit**

```bash
git add setup_models.py README.md
git commit -m "feat: switch to Qwen2.5-Coder 7B single-model architecture"
```

---

## Task 6: Create scripts/agent/history.py (TDD)

**Files:**
- Create: `scripts/agent/history.py`
- Create: `tests/test_history.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_history.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.agent.history import HistoryLog


def test_empty_log_returns_empty_list():
    log = HistoryLog()
    assert log.to_list() == []


def test_add_single_event():
    log = HistoryLog()
    log.add("Read file", "auth.py (120 lines)")
    result = log.to_list()
    assert len(result) == 1
    assert result[0]["title"] == "Read file"
    assert result[0]["detail"] == "auth.py (120 lines)"


def test_add_preserves_order():
    log = HistoryLog()
    log.add("First", "a")
    log.add("Second", "b")
    log.add("Third", "c")
    result = log.to_list()
    assert [e["title"] for e in result] == ["First", "Second", "Third"]


def test_to_list_returns_dicts():
    log = HistoryLog()
    log.add("Tool used", "detail here")
    result = log.to_list()
    assert isinstance(result[0], dict)
    assert set(result[0].keys()) == {"title", "detail"}


def test_multiple_logs_are_independent():
    log1 = HistoryLog()
    log2 = HistoryLog()
    log1.add("In log1", "x")
    assert log2.to_list() == []
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_history.py -v
```
Expected: FAIL — `ModuleNotFoundError: scripts.agent.history`

- [ ] **Step 3: Implement scripts/agent/history.py**

```python
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class HistoryEvent:
    title: str
    detail: str


class HistoryLog:
    def __init__(self) -> None:
        self._events: List[HistoryEvent] = []

    def add(self, title: str, detail: str) -> None:
        self._events.append(HistoryEvent(title=title, detail=detail))

    def to_list(self) -> List[Dict[str, str]]:
        return [{"title": e.title, "detail": e.detail} for e in self._events]
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_history.py -v
```
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/agent/history.py tests/test_history.py
git commit -m "feat: add HistoryLog for session transcript"
```

---

## Task 7: Create scripts/agent/router.py (TDD)

**Files:**
- Create: `scripts/agent/router.py`
- Create: `tests/test_router.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_router.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.agent.router import Router, ToolMatch
from scripts.tools.registry import ToolRegistry
from scripts.tools.base import Tool, ToolResult, ToolParameter


class FakeTool(Tool):
    name = "search_files"
    description = "Search files with glob pattern"
    parameters = []
    is_read_only = True
    requires_approval = False

    def execute(self, **params) -> ToolResult:
        return ToolResult.ok("ok")


class FakeBashTool(Tool):
    name = "bash"
    description = "Run a bash shell command"
    parameters = []
    is_read_only = False
    requires_approval = True

    def execute(self, **params) -> ToolResult:
        return ToolResult.ok("ok")


def _make_registry():
    r = ToolRegistry()
    r._tools = {}  # Reset singleton for test isolation
    r.register(FakeTool)
    r.register(FakeBashTool)
    return r


def test_scores_relevant_tool_higher(monkeypatch):
    router = Router()
    registry = _make_registry()
    monkeypatch.setattr("scripts.agent.router.get_registry", lambda: registry)

    matches = router.score("search for login files")
    names = [m.name for m in matches]
    assert "search_files" in names
    # search_files should score higher than bash for this input
    assert matches[0].name == "search_files"


def test_returns_empty_on_no_match(monkeypatch):
    router = Router()
    registry = _make_registry()
    monkeypatch.setattr("scripts.agent.router.get_registry", lambda: registry)

    matches = router.score("xyzzy frobnotz quux")
    assert matches == []


def test_returns_empty_on_empty_input(monkeypatch):
    router = Router()
    registry = _make_registry()
    monkeypatch.setattr("scripts.agent.router.get_registry", lambda: registry)

    assert router.score("") == []
    assert router.score("   ") == []


def test_returns_empty_on_none_input(monkeypatch):
    router = Router()
    registry = _make_registry()
    monkeypatch.setattr("scripts.agent.router.get_registry", lambda: registry)

    assert router.score(None) == []


def test_match_has_required_fields(monkeypatch):
    router = Router()
    registry = _make_registry()
    monkeypatch.setattr("scripts.agent.router.get_registry", lambda: registry)

    matches = router.score("run a bash command")
    assert len(matches) > 0
    m = matches[0]
    assert isinstance(m, ToolMatch)
    assert m.name
    assert isinstance(m.score, float)
    assert 0.0 < m.score <= 1.0
    assert m.description
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_router.py -v
```
Expected: FAIL — `ModuleNotFoundError: scripts.agent.router`

- [ ] **Step 3: Implement scripts/agent/router.py**

```python
import re
from dataclasses import dataclass
from typing import List, Optional

from scripts.tools.registry import get_registry


@dataclass
class ToolMatch:
    name: str
    score: float
    description: str


class Router:
    def score(self, user_input: Optional[str]) -> List[ToolMatch]:
        if not user_input or not str(user_input).strip():
            return []

        tokens = set(re.findall(r'\w+', user_input.lower()))
        if not tokens:
            return []

        registry = get_registry()
        tools = registry.list_tools()

        matches: List[ToolMatch] = []
        for tool in tools:
            name = tool.get("name", "")
            desc = tool.get("description", "")
            tool_tokens = set(re.findall(r'\w+', (name + " " + desc).lower()))
            overlap = len(tokens & tool_tokens)
            if overlap > 0:
                score = overlap / max(len(tokens), 1)
                matches.append(ToolMatch(name=name, score=score, description=desc))

        return sorted(matches, key=lambda m: m.score, reverse=True)
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_router.py -v
```
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/agent/router.py tests/test_router.py
git commit -m "feat: add Router for tool relevance scoring"
```

---

## Task 8: Create scripts/agent/context.py (TDD)

**Files:**
- Create: `scripts/agent/context.py`
- Create: `tests/test_context.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_context.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.agent.context import SessionContext, build_session_context, context_to_prompt
from scripts.agent.router import ToolMatch


def _make_routing():
    return [
        ToolMatch(name="search_files", score=0.8, description="Search files"),
        ToolMatch(name="read_file", score=0.5, description="Read a file"),
    ]


def test_build_session_context_sets_tool_count(monkeypatch):
    from scripts.tools.registry import ToolRegistry
    fake_registry = ToolRegistry()
    fake_registry._tools = {"a": None, "b": None, "c": None}
    monkeypatch.setattr("scripts.agent.context.get_registry", lambda: fake_registry)

    ctx = build_session_context("snapshot text", _make_routing())
    assert ctx.tool_count == 3


def test_build_session_context_sets_matched_tools(monkeypatch):
    from scripts.tools.registry import ToolRegistry
    fake_registry = ToolRegistry()
    fake_registry._tools = {}
    monkeypatch.setattr("scripts.agent.context.get_registry", lambda: fake_registry)

    ctx = build_session_context("snapshot text", _make_routing())
    assert ctx.matched_tools == ["search_files", "read_file"]


def test_build_session_context_empty_routing(monkeypatch):
    from scripts.tools.registry import ToolRegistry
    fake_registry = ToolRegistry()
    fake_registry._tools = {}
    monkeypatch.setattr("scripts.agent.context.get_registry", lambda: fake_registry)

    ctx = build_session_context("snapshot", [])
    assert ctx.matched_tools == []


def test_context_to_prompt_contains_tool_count(monkeypatch):
    from scripts.tools.registry import ToolRegistry
    fake_registry = ToolRegistry()
    fake_registry._tools = {"x": None}
    monkeypatch.setattr("scripts.agent.context.get_registry", lambda: fake_registry)

    ctx = build_session_context("", _make_routing())
    prompt = context_to_prompt(ctx)
    assert "1" in prompt  # tool_count
    assert "search_files" in prompt


def test_context_to_prompt_no_matches(monkeypatch):
    from scripts.tools.registry import ToolRegistry
    fake_registry = ToolRegistry()
    fake_registry._tools = {}
    monkeypatch.setattr("scripts.agent.context.get_registry", lambda: fake_registry)

    ctx = build_session_context("", [])
    prompt = context_to_prompt(ctx)
    assert "none" in prompt.lower()
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_context.py -v
```
Expected: FAIL — `ModuleNotFoundError: scripts.agent.context`

- [ ] **Step 3: Implement scripts/agent/context.py**

```python
from dataclasses import dataclass, field
from typing import Dict, List

from scripts.agent.router import ToolMatch
from scripts.tools.registry import get_registry


@dataclass
class SessionContext:
    tool_count: int
    matched_tools: List[str]
    workspace_root: str
    model_info: str = "Qwen2.5-Coder-7B-Instruct"


def build_session_context(snapshot_text: str, routing_result: List[ToolMatch]) -> SessionContext:
    registry = get_registry()
    tool_count = len(registry.list_tool_names())
    matched_tools = [m.name for m in routing_result]
    workspace_root = registry._workspace_root or "unknown"

    return SessionContext(
        tool_count=tool_count,
        matched_tools=matched_tools,
        workspace_root=workspace_root,
    )


def context_to_prompt(ctx: SessionContext) -> str:
    if ctx.matched_tools:
        tools_str = ", ".join(ctx.matched_tools)
    else:
        tools_str = "none matched"

    return (
        f"[Session Context]\n"
        f"Available tools: {ctx.tool_count}\n"
        f"Relevant tools for this task: {tools_str}\n"
        f"Model: {ctx.model_info}\n"
        f"Workspace: {ctx.workspace_root}\n"
    )
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_context.py -v
```
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/agent/context.py tests/test_context.py
git commit -m "feat: add SessionContext for turn loop bootstrapping"
```

---

## Task 9: Create scripts/agent/turn_runner.py (TDD)

**Files:**
- Create: `scripts/agent/turn_runner.py`
- Create: `tests/test_turn_runner.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_turn_runner.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.agent.turn_runner import TurnRunner, TurnResult, STOP_DONE, STOP_MAX_TURNS, STOP_APPROVAL, STOP_ERROR
from scripts.tools.registry import ToolRegistry
from scripts.tools.base import Tool, ToolResult, ToolParameter


# --- Fake tools for testing ---

class FakeReadTool(Tool):
    name = "read_file"
    description = "Read a file"
    parameters = [ToolParameter(name="path", type="string", description="File path")]
    is_read_only = True
    requires_approval = False

    def execute(self, **params) -> ToolResult:
        return ToolResult.ok(f"contents of {params.get('path', 'unknown')}")


class FakeBashTool(Tool):
    name = "bash"
    description = "Run bash command"
    parameters = [ToolParameter(name="command", type="string", description="Command")]
    is_read_only = False
    requires_approval = True

    def execute(self, **params) -> ToolResult:
        return ToolResult.ok("bash output")


class FakeFailTool(Tool):
    name = "fail_tool"
    description = "Always fails"
    parameters = []
    is_read_only = True
    requires_approval = False

    def execute(self, **params) -> ToolResult:
        return ToolResult.fail(error="tool exploded")


def _make_registry():
    r = ToolRegistry()
    r._tools = {}
    r.register(FakeReadTool)
    r.register(FakeBashTool)
    r.register(FakeFailTool)
    return r


# --- Model call helpers ---

def _model_ready(_messages):
    """Model immediately signals ready to implement."""
    return "READY_TO_IMPLEMENT"


def _model_uses_read_tool(_messages):
    """Model calls a read-only tool then signals ready."""
    # After first call, just say ready
    if not hasattr(_model_uses_read_tool, "called"):
        _model_uses_read_tool.called = True
        return 'TOOL_CALL: read_file\nPARAMS: {"path": "auth.py"}'
    del _model_uses_read_tool.called
    return "READY_TO_IMPLEMENT"


def _model_uses_bash(_messages):
    """Model calls a write/bash tool."""
    return 'TOOL_CALL: bash\nPARAMS: {"command": "ls src/"}'


def _model_always_loops(_messages):
    """Model never signals done — forces max_turns."""
    return 'TOOL_CALL: read_file\nPARAMS: {"path": "file.py"}'


def _model_returns_garbage(_messages):
    """Model returns unparseable output with no tool call or ready signal."""
    return "I am confused and cannot help you today."


def _model_errors(_messages):
    raise RuntimeError("model crashed")


# --- Tests ---

def test_stop_reason_done_when_ready(monkeypatch):
    monkeypatch.setattr("scripts.agent.turn_runner.get_registry", lambda: _make_registry())
    runner = TurnRunner(model_call=_model_ready)
    result = runner.run("fix the auth bug", {})
    assert result.stop_reason == STOP_DONE
    assert result.mode == "execute"


def test_stop_reason_max_turns_reached(monkeypatch):
    monkeypatch.setattr("scripts.agent.turn_runner.get_registry", lambda: _make_registry())
    runner = TurnRunner(model_call=_model_always_loops, max_turns=3)
    result = runner.run("fix everything", {})
    assert result.stop_reason == STOP_MAX_TURNS
    assert result.mode == "max_turns_reached"
    assert len(result.transcript) > 0


def test_read_only_tool_executes_without_approval(monkeypatch):
    call_count = {"n": 0}

    def model_call(messages):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return 'TOOL_CALL: read_file\nPARAMS: {"path": "main.py"}'
        return "READY_TO_IMPLEMENT"

    monkeypatch.setattr("scripts.agent.turn_runner.get_registry", lambda: _make_registry())
    runner = TurnRunner(model_call=model_call)
    result = runner.run("read main.py", {})
    assert result.stop_reason == STOP_DONE
    assert any("read_file" in e["title"].lower() for e in result.transcript)


def test_bash_tool_returns_approval_required(monkeypatch):
    monkeypatch.setattr("scripts.agent.turn_runner.get_registry", lambda: _make_registry())
    runner = TurnRunner(model_call=_model_uses_bash)
    result = runner.run("run ls", {})
    assert result.stop_reason == STOP_APPROVAL
    assert result.mode == "approval_required"
    assert result.pending_tool is not None
    assert result.pending_tool["name"] == "bash"


def test_error_stop_reason_on_model_crash(monkeypatch):
    monkeypatch.setattr("scripts.agent.turn_runner.get_registry", lambda: _make_registry())
    runner = TurnRunner(model_call=_model_errors)
    result = runner.run("anything", {})
    assert result.stop_reason == STOP_ERROR
    assert result.error is not None


def test_clarify_mode_on_unparseable_output(monkeypatch):
    monkeypatch.setattr("scripts.agent.turn_runner.get_registry", lambda: _make_registry())
    runner = TurnRunner(model_call=_model_returns_garbage)
    result = runner.run("do something", {})
    assert result.mode == "clarify"


def test_transcript_is_list_of_dicts(monkeypatch):
    monkeypatch.setattr("scripts.agent.turn_runner.get_registry", lambda: _make_registry())
    runner = TurnRunner(model_call=_model_ready)
    result = runner.run("task", {})
    assert isinstance(result.transcript, list)


def test_all_stop_reasons_reachable(monkeypatch):
    """Verify every stop reason constant maps to a reachable code path."""
    monkeypatch.setattr("scripts.agent.turn_runner.get_registry", lambda: _make_registry())

    # STOP_DONE
    r = TurnRunner(_model_ready)
    assert r.run("t", {}).stop_reason == STOP_DONE

    # STOP_MAX_TURNS
    r = TurnRunner(_model_always_loops, max_turns=1)
    assert r.run("t", {}).stop_reason == STOP_MAX_TURNS

    # STOP_APPROVAL
    r = TurnRunner(_model_uses_bash)
    assert r.run("t", {}).stop_reason == STOP_APPROVAL

    # STOP_ERROR
    r = TurnRunner(_model_errors)
    assert r.run("t", {}).stop_reason == STOP_ERROR
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_turn_runner.py -v
```
Expected: FAIL — `ModuleNotFoundError: scripts.agent.turn_runner`

- [ ] **Step 3: Implement scripts/agent/turn_runner.py**

```python
import json
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from scripts.agent.history import HistoryLog
from scripts.agent.context import build_session_context, context_to_prompt
from scripts.agent.router import Router
from scripts.tools.registry import get_registry
from scripts.config import MAX_AGENT_TURNS, TIMEOUT_EXECUTE_MS

STOP_DONE = "done"
STOP_MAX_TURNS = "max_turns_reached"
STOP_APPROVAL = "approval_required"
STOP_ERROR = "error"

_TOOL_CALL_RE = re.compile(
    r'TOOL_CALL:\s*(\w+)\s*\nPARAMS:\s*(\{[^}]*\})',
    re.DOTALL
)


@dataclass
class TurnResult:
    stop_reason: str
    mode: str
    transcript: List[Dict[str, str]]
    context_summary: str
    pending_tool: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class TurnRunner:
    def __init__(
        self,
        model_call: Callable[[List[Dict]], str],
        snapshot_text: str = "",
        max_turns: Optional[int] = None,
    ) -> None:
        self.model_call = model_call
        self.snapshot_text = snapshot_text
        self.max_turns = max_turns if max_turns is not None else MAX_AGENT_TURNS
        self._history = HistoryLog()
        self._router = Router()

    def run(self, user_input: str, files: Dict[str, str]) -> TurnResult:
        routing = self._router.score(user_input)
        ctx = build_session_context(self.snapshot_text, routing)
        conversation = self._build_messages(user_input, files, ctx)

        for _turn in range(self.max_turns):
            response, err = self._call_model_with_timeout(conversation)

            if err:
                return TurnResult(
                    stop_reason=STOP_ERROR,
                    mode="error",
                    transcript=self._history.to_list(),
                    context_summary="",
                    error=err,
                )

            response = response or ""

            if "READY_TO_IMPLEMENT" in response:
                return TurnResult(
                    stop_reason=STOP_DONE,
                    mode="execute",
                    transcript=self._history.to_list(),
                    context_summary=self._summarize(conversation),
                )

            tool_calls = _TOOL_CALL_RE.findall(response)

            if not tool_calls:
                # No tool call and no ready signal — treat as clarification
                return TurnResult(
                    stop_reason=STOP_DONE,
                    mode="clarify",
                    transcript=self._history.to_list(),
                    context_summary=response,
                )

            for tool_name, params_str in tool_calls:
                try:
                    params = json.loads(params_str)
                except json.JSONDecodeError:
                    params = {}

                registry = get_registry()
                tool = registry.get(tool_name)

                if tool is None:
                    self._history.add(
                        f"Unknown tool: {tool_name}",
                        f"Available: {registry.list_tool_names()}"
                    )
                    conversation.append({
                        "role": "user",
                        "content": f"Tool '{tool_name}' not found. "
                                   f"Available: {registry.list_tool_names()}",
                    })
                    continue

                if tool.requires_approval:
                    self._history.add(f"Approval required: {tool_name}", str(params))
                    return TurnResult(
                        stop_reason=STOP_APPROVAL,
                        mode="approval_required",
                        transcript=self._history.to_list(),
                        context_summary="",
                        pending_tool={"name": tool_name, "params": params},
                    )

                # Execute read-only tool immediately
                result = registry.execute(tool_name, params)
                detail = (result.output or result.error or "")[:200]
                self._history.add(f"Used {tool_name}", detail)
                conversation.append({
                    "role": "user",
                    "content": f"Tool result ({tool_name}):\n{result.output or result.error}",
                })

        # Exhausted max_turns
        return TurnResult(
            stop_reason=STOP_MAX_TURNS,
            mode="max_turns_reached",
            transcript=self._history.to_list(),
            context_summary=self._summarize(conversation),
        )

    def _call_model_with_timeout(self, conversation: List[Dict]) -> tuple:
        result_holder: List[Optional[str]] = [None]
        error_holder: List[Optional[str]] = [None]

        def call() -> None:
            try:
                result_holder[0] = self.model_call(conversation)
            except Exception as exc:
                error_holder[0] = f"{type(exc).__name__}: {exc}"

        thread = threading.Thread(target=call, daemon=True)
        thread.start()
        timeout_s = TIMEOUT_EXECUTE_MS / 1000
        thread.join(timeout=timeout_s)

        if thread.is_alive():
            # Timeout — log and return empty (caller continues loop)
            self._history.add("Turn timeout", "Model call exceeded timeout")
            return "", None

        return result_holder[0], error_holder[0]

    def _build_messages(
        self,
        user_input: str,
        files: Dict[str, str],
        ctx: Any,
    ) -> List[Dict[str, str]]:
        context_header = context_to_prompt(ctx)

        files_section = ""
        for name, content in files.items():
            files_section += f"FILE: {name}\n{content[:2000]}\n\n"

        system = (
            "You are a coding agent. Gather context using tools before implementing.\n\n"
            "To call a tool, output EXACTLY:\n"
            "TOOL_CALL: <tool_name>\n"
            'PARAMS: {"key": "value"}\n\n'
            "When you have enough context, output:\n"
            "READY_TO_IMPLEMENT\n\n"
            f"{context_header}"
        )

        user_content = f"TASK: {user_input}"
        if files_section:
            user_content += f"\n\nFILES:\n{files_section}"

        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]

    def _summarize(self, conversation: List[Dict]) -> str:
        non_system = [m for m in conversation if m.get("role") != "system"]
        return "\n".join(m["content"][:300] for m in non_system[-4:])
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_turn_runner.py -v
```
Expected: PASS (8 tests)

- [ ] **Step 5: Run full test suite**

```
pytest tests/ -v
```
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/agent/turn_runner.py tests/test_turn_runner.py
git commit -m "feat: add TurnRunner with multi-turn agentic loop and approval gate"
```

---

## Task 10: Add agent_turn to wrapper.py

**Files:**
- Modify: `scripts/backend/wrapper.py`

- [ ] **Step 1: Add the import at the top of wrapper.py**

After the existing imports, add:

```python
from scripts.agent.turn_runner import TurnRunner
from scripts.critic.critic import chat_for_turn  # added in next step
```

- [ ] **Step 2: Add chat_for_turn helper to critic.py**

In `scripts/critic/critic.py`, add this function after `_get_llm()`:

```python
def chat_for_turn(messages: list) -> str:
    """
    Chat completion for TurnRunner — takes a messages list, returns response string.
    Uses turn temperature for tool-call decision making.
    """
    from scripts.config import MODEL_TURN_MAX_TOKENS, MODEL_TURN_TEMPERATURE
    llm = _get_llm()
    response = llm.create_chat_completion(
        messages=messages,
        max_tokens=MODEL_TURN_MAX_TOKENS,
        temperature=MODEL_TURN_TEMPERATURE,
    )
    return _extract_response_text(response)
```

- [ ] **Step 3: Add handle_agent_turn to wrapper.py**

Add this function before `handle_message()`:

```python
def handle_agent_turn(params: dict) -> dict:
    """
    Run the multi-turn agentic loop.

    Params:
        user_input: str — the task description
        files: dict[str, str] — filename -> content
        snapshot: str — optional decision state snapshot text
        resume_tool: dict — optional {"name": str, "params": dict, "approved": bool}
            Pass when resuming after an approval_required response

    Returns:
        {
            "stop_reason": str,   — done | max_turns_reached | approval_required | error
            "mode": str,          — execute | clarify | approval_required | max_turns_reached | error
            "transcript": list,   — [{title, detail}, ...]
            "context_summary": str,
            "pending_tool": dict | null,
            "error": str | null
        }
    """
    user_input = params.get("user_input", "")
    files = params.get("files", {})
    snapshot = params.get("snapshot", "")

    if not user_input:
        raise ValueError("Missing 'user_input' parameter")

    from scripts.critic.critic import chat_for_turn
    runner = TurnRunner(
        model_call=chat_for_turn,
        snapshot_text=snapshot,
    )

    # Handle resume after approval
    resume_tool = params.get("resume_tool")
    if resume_tool:
        tool_name = resume_tool.get("name", "")
        tool_params = resume_tool.get("params", {})
        approved = resume_tool.get("approved", False)

        if approved and tool_name:
            result = _tool_registry.execute(tool_name, tool_params)
            runner._history.add(
                f"Approved: {tool_name}",
                (result.output or result.error or "")[:200]
            )

    result = runner.run(user_input, files)
    return {
        "stop_reason": result.stop_reason,
        "mode": result.mode,
        "transcript": result.transcript,
        "context_summary": result.context_summary,
        "pending_tool": result.pending_tool,
        "error": result.error,
    }
```

- [ ] **Step 4: Register the handler in handle_message()**

In the `handle_message()` function, add before the `else` clause:

```python
        elif method == "agent_turn":
            result = handle_agent_turn(params)
            send_response(msg_id, result=result)
```

- [ ] **Step 5: Test the handler manually**

```
cd /c/local-ai-agent
python -c "
from scripts.backend.wrapper import handle_agent_turn
# Dry run without a real model — should fail gracefully
try:
    handle_agent_turn({'user_input': 'test', 'files': {}})
except FileNotFoundError as e:
    print('Expected: model not found -', e)
except Exception as e:
    print('Got:', type(e).__name__, e)
"
```
Expected: `Expected: model not found — Model not found: .../qwen/...`

- [ ] **Step 6: Commit**

```bash
git add scripts/backend/wrapper.py scripts/critic/critic.py
git commit -m "feat: add agent_turn RPC handler to wrapper"
```

---

## Task 11: Update SidebarProvider.ts for transcript and approval UI

**Files:**
- Modify: `vscode-ai-agent/src/SidebarProvider.ts`

- [ ] **Step 1: Add agentTurn method to PythonBackend (pythonBackend.ts)**

Open `vscode-ai-agent/src/pythonBackend.ts`. Add after the existing method definitions:

```typescript
async agentTurn(params: {
  user_input: string;
  files: Record<string, string>;
  snapshot?: string;
  resume_tool?: { name: string; params: Record<string, unknown>; approved: boolean } | null;
}): Promise<{
  stop_reason: string;
  mode: string;
  transcript: Array<{ title: string; detail: string }>;
  context_summary: string;
  pending_tool: { name: string; params: Record<string, unknown> } | null;
  error: string | null;
}> {
  return this.sendRequest("agent_turn", params) as Promise<any>;
}
```

- [ ] **Step 2: Add FlowState for the new modes**

In `SidebarProvider.ts`, find:

```typescript
type FlowState = "chatting" | "executing" | "reviewing" | "applying";
```

Replace with:

```typescript
type FlowState = "chatting" | "agent_running" | "approval_pending" | "executing" | "reviewing" | "applying";
```

- [ ] **Step 3: Add state fields for transcript and pending tool**

In the `SidebarProvider` class body, after `private reviewVerdict: string = "";`, add:

```typescript
private agentTranscript: Array<{ title: string; detail: string }> = [];
private pendingTool: { name: string; params: Record<string, unknown> } | null = null;
```

- [ ] **Step 4: Add handleAgentProceed method**

Add this method to `SidebarProvider` after `warmUpModels()`:

```typescript
private async handleAgentProceed(
  userInput: string,
  resumeTool?: { name: string; params: Record<string, unknown>; approved: boolean } | null
): Promise<void> {
  this.currentState = "agent_running";
  this.agentTranscript = [];
  this.pendingTool = null;
  this.updateWebview();

  const filesObj: Record<string, string> = {};
  this.selectedFiles.forEach((content, path) => { filesObj[path] = content; });

  try {
    const result = await this.backend.agentTurn({
      user_input: userInput,
      files: filesObj,
      resume_tool: resumeTool ?? null,
    });

    this.agentTranscript = result.transcript;

    if (result.stop_reason === "approval_required" && result.pending_tool) {
      this.pendingTool = result.pending_tool;
      this.currentState = "approval_pending";
      this.updateWebview();
      return;
    }

    if (result.stop_reason === "error") {
      vscode.window.showErrorMessage(`Agent error: ${result.error}`);
      this.currentState = "chatting";
      this.updateWebview();
      return;
    }

    if (result.mode === "clarify") {
      // Agent wants more info — show context_summary as assistant message
      this.conversationHistory.push({
        role: "assistant",
        content: result.context_summary,
      });
      this.currentState = "chatting";
      this.updateWebview();
      return;
    }

    if (result.stop_reason === "max_turns_reached") {
      vscode.window.showWarningMessage(
        "Agent reached turn limit — try narrowing your task."
      );
      this.currentState = "chatting";
      this.updateWebview();
      return;
    }

    // mode === "execute" — proceed to code generation
    this.currentTask = result.context_summary || userInput;
    this.currentState = "executing";
    this.updateWebview();

    const diff = await this.backend.execute({
      task: this.currentTask,
      files: filesObj,
    });

    this.currentDiff = diff;
    this.currentState = "reviewing";
    this.updateWebview();

  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    vscode.window.showErrorMessage(`Agent failed: ${msg}`);
    this.currentState = "chatting";
    this.updateWebview();
  }
}
```

- [ ] **Step 5: Add transcript and approval HTML to getHtmlForWebview**

Find the `getHtmlForWebview` method. Locate the section that renders the diff/review UI and add the transcript section before it. Find the `<div id="diff-section"` and add before it:

```typescript
// After the existing chat section, add transcript + approval sections
const transcriptHtml = this.agentTranscript.length > 0 ? `
  <details id="transcript-section" ${this.agentTranscript.length > 0 ? 'open' : ''}>
    <summary style="cursor:pointer;font-weight:bold;margin:8px 0;">
      Agent Actions (${this.agentTranscript.length})
    </summary>
    <div id="transcript-list" style="font-size:12px;padding:4px 0;">
      ${this.agentTranscript.map(e => `
        <div style="padding:2px 0;border-bottom:1px solid var(--vscode-widget-border)">
          <strong>${e.title}</strong><br/>
          <span style="color:var(--vscode-descriptionForeground)">${e.detail}</span>
        </div>
      `).join('')}
    </div>
  </details>
` : '';

const approvalHtml = this.currentState === 'approval_pending' && this.pendingTool ? `
  <div id="approval-section" style="border:1px solid var(--vscode-inputValidation-warningBorder);padding:8px;margin:8px 0;">
    <strong>Approval Required</strong><br/>
    Tool: <code>${this.pendingTool.name}</code><br/>
    Params: <code>${JSON.stringify(this.pendingTool.params)}</code><br/>
    <button id="btn-approve">Approve</button>
    <button id="btn-reject">Reject</button>
  </div>
` : '';
```

Include `${transcriptHtml}${approvalHtml}` in the returned HTML string at the appropriate location in the body.

- [ ] **Step 6: Wire up approve/reject in the message handler**

In the `resolveWebviewView` method, find the `webview.onDidReceiveMessage` handler. Add cases:

```typescript
case 'approve_tool':
  if (this.pendingTool && this.currentTask) {
    this.handleAgentProceed(this.currentTask, {
      ...this.pendingTool,
      approved: true,
    });
  }
  break;

case 'reject_tool':
  if (this.pendingTool && this.currentTask) {
    this.handleAgentProceed(this.currentTask, {
      ...this.pendingTool,
      approved: false,
    });
  }
  this.pendingTool = null;
  this.currentState = "chatting";
  this.updateWebview();
  break;
```

Add button click handlers in the webview JavaScript:

```javascript
document.getElementById('btn-approve')?.addEventListener('click', () => {
  vscode.postMessage({ command: 'approve_tool' });
});
document.getElementById('btn-reject')?.addEventListener('click', () => {
  vscode.postMessage({ command: 'reject_tool' });
});
```

- [ ] **Step 7: Wire "Proceed" to handleAgentProceed instead of old flow**

Find the case that handles the `proceed` command in `onDidReceiveMessage`. Replace the body with:

```typescript
case 'proceed':
  const userInput = message.input || this.currentTask;
  this.currentTask = userInput;
  this.handleAgentProceed(userInput);
  break;
```

- [ ] **Step 8: Compile TypeScript**

```
cd /c/local-ai-agent/vscode-ai-agent
npm run compile
```
Expected: No TypeScript errors

- [ ] **Step 9: Commit**

```bash
git add vscode-ai-agent/src/SidebarProvider.ts vscode-ai-agent/src/pythonBackend.ts
git commit -m "feat: add transcript and approval UI to VS Code sidebar"
```

---

## Task 12: Add test_tool_registry_parity.py

**Files:**
- Create: `tests/test_tool_registry_parity.py`

- [ ] **Step 1: Write and run the test**

```python
# tests/test_tool_registry_parity.py
"""
Parity audit: verifies all registered tools are fully configured.
Catches tools added to the registry without required fields.
Inspired by Claude Code's parity_audit pattern.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.tools.registry import get_registry
from scripts.tools.bash import BashTool
from scripts.tools.file_ops import ReadFileTool, WriteFileTool, EditFileTool, DeleteFileTool, MoveFileTool, ListDirectoryTool
from scripts.tools.search import GlobTool, GrepTool, FindDefinitionTool
from scripts.tools.base import Tool

# Register all tools before checking
registry = get_registry()
for cls in [BashTool, ReadFileTool, WriteFileTool, EditFileTool, DeleteFileTool, MoveFileTool, ListDirectoryTool, GlobTool, GrepTool, FindDefinitionTool]:
    try:
        registry.register(cls)
    except Exception:
        pass


def _all_tools():
    return [get_registry().get(name) for name in get_registry().list_tool_names()]


def test_all_tools_have_name():
    for tool in _all_tools():
        assert tool.name, f"Tool {type(tool).__name__} missing name"
        assert isinstance(tool.name, str)


def test_all_tools_have_description():
    for tool in _all_tools():
        assert tool.description, f"Tool '{tool.name}' missing description"
        assert len(tool.description) > 5, f"Tool '{tool.name}' description too short"


def test_all_tools_have_is_read_only_set():
    for tool in _all_tools():
        assert isinstance(tool.is_read_only, bool), \
            f"Tool '{tool.name}' is_read_only must be bool, got {type(tool.is_read_only)}"


def test_all_tools_have_requires_approval_set():
    for tool in _all_tools():
        assert isinstance(tool.requires_approval, bool), \
            f"Tool '{tool.name}' requires_approval must be bool, got {type(tool.requires_approval)}"


def test_write_tools_require_approval():
    """Non-read-only tools must require approval — safety invariant."""
    for tool in _all_tools():
        if not tool.is_read_only:
            assert tool.requires_approval, \
                f"Tool '{tool.name}' is not read-only but requires_approval=False — this is unsafe"


def test_all_tools_have_valid_schema():
    for tool in _all_tools():
        schema = tool.get_schema()
        assert "name" in schema
        assert "description" in schema
        assert "parameters" in schema
        assert "properties" in schema["parameters"]
```

- [ ] **Step 2: Run test**

```
pytest tests/test_tool_registry_parity.py -v
```
Expected: PASS (6 tests)

If any test fails, fix the tool's missing field before continuing.

- [ ] **Step 3: Run full test suite**

```
pytest tests/ -v
```
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_tool_registry_parity.py
git commit -m "test: add tool registry parity audit"
```

---

## Task 13: Update CHANGELOG.md and push

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add new entry to CHANGELOG.md**

Prepend before the existing `## [0.1.0]` entry:

```markdown
## [0.2.0] - 2026-03-31

### Added
- Multi-turn agentic loop (TurnRunner) — agent calls tools autonomously up to 10 turns before generating a diff
- Prompt routing — user input scored against tool registry to pre-load relevant tools
- Session context bootstrapping — model sees tool counts and routing decisions from turn 1
- Session transcript — collapsible log of all tool calls shown in VS Code sidebar
- Approval gate — write/bash tools pause for user approval; read-only tools execute silently
- Explicit stop reasons: `done`, `max_turns_reached`, `approval_required`, `error`
- Tool registry parity audit test

### Changed
- Migrated from dual-model (LLaMA 3.1 8B + DeepSeek Coder 6.7B) to single Qwen2.5-Coder 7B-Instruct
- RAM minimum requirement reduced from 16GB to 8GB
- Disk requirement reduced from ~8GB to ~4.5GB

### Removed
- LLaMA and DeepSeek model downloads (replaced by Qwen2.5-Coder)
```

- [ ] **Step 2: Commit and push**

```bash
git add CHANGELOG.md
git commit -m "docs: update CHANGELOG for v0.2.0 agentic loop release"
git push origin main
```

---

## Self-Review Notes

**Spec coverage check:**
- ✅ Multi-turn loop with max_turns (Task 9)
- ✅ Hybrid permission model (Task 9 — `requires_approval` gate)
- ✅ Session transcript (Task 6 + Task 11)
- ✅ Single Qwen2.5-Coder model (Tasks 1–5)
- ✅ Prompt routing (Task 7)
- ✅ Stop reasons: done/max_turns/approval/error (Task 9)
- ✅ Session context bootstrap (Task 8)
- ✅ Per-turn timeout (Task 9 — `_call_model_with_timeout`)
- ✅ Tool registry parity test (Task 12)
- ✅ All stop reasons reachable via explicit tests (Task 9)
- ✅ VS Code transcript + approval UI (Task 11)

**Type consistency:**
- `TurnResult` defined in Task 9, used in Task 10 (wrapper) — consistent
- `HistoryLog.to_list()` returns `List[Dict[str, str]]` — used in Task 11 (transcript render) — consistent
- `ToolMatch` defined in Task 7, imported by Task 8 (context) — consistent
- `chat_for_turn()` added to critic.py in Task 10, imported in wrapper — consistent

**Deferred (not in this plan):**
- `simple_mode` config flag
- Decision-State Snapshot validation improvements
- Async/streaming loop (Option C)
