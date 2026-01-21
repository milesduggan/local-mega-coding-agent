# Configuration Reference

All settings can be configured via environment variables (Python backend) or VS Code settings (extension).

## Environment Variables

Set these before starting VS Code or in your shell profile.

### DeepSeek (Executor) Model

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_AGENT_DEEPSEEK_N_CTX` | 8192 | Context window size (tokens) |
| `AI_AGENT_DEEPSEEK_MAX_TOKENS` | 1024 | Maximum output tokens |
| `AI_AGENT_DEEPSEEK_TEMPERATURE` | 0.2 | Creativity (0.0-1.0, lower = more deterministic) |
| `AI_AGENT_DEEPSEEK_TOP_P` | 0.9 | Nucleus sampling threshold |
| `AI_AGENT_DEEPSEEK_REPEAT_PENALTY` | 1.1 | Penalty for repeating tokens |
| `AI_AGENT_DEEPSEEK_N_THREADS` | 4 | CPU threads for inference |

### LLaMA (Critic) Model

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_AGENT_LLAMA_N_CTX` | 4096 | Context window size (tokens) |
| `AI_AGENT_LLAMA_CHAT_MAX_TOKENS` | 512 | Max tokens for chat responses |
| `AI_AGENT_LLAMA_REVIEW_MAX_TOKENS` | 256 | Max tokens for diff review |
| `AI_AGENT_LLAMA_NORMALIZE_MAX_TOKENS` | 300 | Max tokens for task normalization |
| `AI_AGENT_LLAMA_CHAT_TEMPERATURE` | 0.7 | Chat creativity (higher = more creative) |
| `AI_AGENT_LLAMA_REVIEW_TEMPERATURE` | 0.3 | Review creativity (lower = more conservative) |
| `AI_AGENT_LLAMA_NORMALIZE_TEMPERATURE` | 0.2 | Normalization creativity |
| `AI_AGENT_LLAMA_N_THREADS` | 4 | CPU threads for inference |

### Model Lifecycle

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_AGENT_MODEL_IDLE_TIMEOUT_MINUTES` | 15 | Minutes of inactivity before auto-unload (0 = disable) |
| `AI_AGENT_AUTO_UNLOAD_ENABLED` | true | Enable automatic model unloading |

### Chunker

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_AGENT_CHUNK_MAX_TOKENS` | 3000 | Max tokens for chunk selection budget |

### Timeouts

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_AGENT_TIMEOUT_CHAT_MS` | 60000 | Chat response timeout (ms) |
| `AI_AGENT_TIMEOUT_NORMALIZE_MS` | 60000 | Task normalization timeout (ms) |
| `AI_AGENT_TIMEOUT_EXECUTE_MS` | 180000 | Code generation timeout (ms) |
| `AI_AGENT_TIMEOUT_REVIEW_MS` | 60000 | Diff review timeout (ms) |
| `AI_AGENT_TIMEOUT_WARMUP_MS` | 120000 | Model warm-up timeout (ms) |

### Debug

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_AGENT_DEBUG_LOG_LLM_IO` | false | Log all LLM inputs/outputs to stderr |

---

## VS Code Settings

Configure in VS Code settings (UI or `settings.json`).

### Timeouts

| Setting | Default | Description |
|---------|---------|-------------|
| `ai-agent.timeouts.chat` | 60000 | Chat response timeout (ms) |
| `ai-agent.timeouts.normalize` | 60000 | Task normalization timeout (ms) |
| `ai-agent.timeouts.execute` | 180000 | Code generation timeout (ms) |
| `ai-agent.timeouts.review` | 60000 | Diff review timeout (ms) |
| `ai-agent.timeouts.warmup` | 120000 | Model warm-up timeout (ms) |

### Model Management

| Setting | Default | Description |
|---------|---------|-------------|
| `ai-agent.modelIdleTimeoutMinutes` | 15 | Minutes before auto-unload |
| `ai-agent.autoUnloadEnabled` | true | Enable auto-unload when idle |
| `ai-agent.pythonPath` | `python` | Path to Python executable |

---

## Configuration Priority

Settings are resolved in this order (highest priority first):

1. **Environment variables** - Override everything
2. **VS Code settings** - User and workspace settings
3. **Default values** - Built into the code

---

## Example Configurations

### Slower Hardware (Increase Timeouts)

```bash
# Shell
export AI_AGENT_TIMEOUT_EXECUTE_MS=300000
export AI_AGENT_TIMEOUT_WARMUP_MS=180000
```

```json
// VS Code settings.json
{
  "ai-agent.timeouts.execute": 300000,
  "ai-agent.timeouts.warmup": 180000
}
```

### More Creative Code Generation

```bash
export AI_AGENT_DEEPSEEK_TEMPERATURE=0.4
export AI_AGENT_DEEPSEEK_MAX_TOKENS=2048
```

### Keep Models in RAM (Disable Auto-Unload)

```bash
export AI_AGENT_AUTO_UNLOAD_ENABLED=false
```

```json
// VS Code settings.json
{
  "ai-agent.autoUnloadEnabled": false
}
```

### Aggressive Auto-Unload (Save RAM)

```bash
export AI_AGENT_MODEL_IDLE_TIMEOUT_MINUTES=5
```

```json
// VS Code settings.json
{
  "ai-agent.modelIdleTimeoutMinutes": 5
}
```

### Debug Mode (Log All LLM I/O)

```bash
export AI_AGENT_DEBUG_LOG_LLM_IO=true
```

Check the Output panel in VS Code (select "AI Agent" from dropdown).

### Custom Python Path

```json
// VS Code settings.json
{
  "ai-agent.pythonPath": "/usr/local/bin/python3.11"
}
```

---

## Model Parameters Explained

### Context Window (`n_ctx`)
The maximum number of tokens the model can process at once. Larger values allow more context but use more memory.

- **DeepSeek default (8192)**: Handles files up to ~6000 lines
- **LLaMA default (4096)**: Sufficient for chat and review tasks

### Temperature
Controls randomness in output. Range: 0.0 to 1.0

- **0.0**: Completely deterministic (same input = same output)
- **0.2**: Low creativity (good for code generation)
- **0.7**: Moderate creativity (good for chat)
- **1.0**: Maximum creativity (often incoherent)

### Top-P (Nucleus Sampling)
Only consider tokens whose cumulative probability exceeds this threshold.

- **0.9 (default)**: Consider top 90% probability mass
- **Lower values**: More focused/deterministic
- **Higher values**: More diverse outputs

### Repeat Penalty
Penalizes the model for repeating tokens. Helps prevent infinite loops in code.

- **1.0**: No penalty
- **1.1 (default)**: Slight penalty
- **Higher values**: Strongly discourage repetition

---

## Troubleshooting Configuration

### Settings Not Taking Effect

1. **Environment variables**: Restart VS Code after setting
2. **VS Code settings**: May require extension reload (`Ctrl+Shift+P` > "Reload Window")
3. **Check priority**: Environment variables override VS Code settings

### Finding Current Values

Run this Python snippet to see active configuration:

```python
from scripts.config import *
print(f"DeepSeek n_ctx: {DEEPSEEK_N_CTX}")
print(f"LLaMA n_ctx: {LLAMA_N_CTX}")
print(f"Auto-unload: {AUTO_UNLOAD_ENABLED}")
print(f"Idle timeout: {MODEL_IDLE_TIMEOUT_MINUTES} min")
```

### Model Status Command

Use `AI Agent: Show Model Status` command to see:
- Which models are loaded
- Idle time for each model
- Current auto-unload settings
