# Local AI Agent

> A fully offline AI coding assistant for VS Code, powered by local LLMs.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![VS Code](https://img.shields.io/badge/VS%20Code-1.85+-blue.svg)](https://code.visualstudio.com/)
[![Python](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org/)

## Features

- **100% Offline** - No API keys, no cloud services, your code never leaves your machine
- **Single-Model Architecture** - Qwen3-14B-Instruct handles chat, code generation, review, and agent-turn decisions
- **Review Gate Before Apply** - Generated changes are reviewed before you accept them
- **Agentic Loop** - The agent can inspect files, search the codebase, and gather context with tools before generating a diff
- **Smart Chunking** - AST-based Python chunking reduces token usage on larger files
- **Tool System** - Extensible tools for shell commands, file operations, and codebase search
- **Auto Memory Management** - Automatically unloads the main model when idle to free RAM
- **Security Hardened** - Path traversal protection and input validation
- **Configurable** - Tune timeouts, model parameters, and behavior via settings

## Quick Start

### Prerequisites

- Python 3.10+
- VS Code 1.85+
- 16GB RAM minimum (32GB recommended)
- ~10GB disk space for model

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/milesduggan/local-mega-coding-agent.git
   cd local-mega-coding-agent
   ```

2. **Download models**
   ```bash
   python setup_models.py
   ```
   This downloads Qwen3-14B-Instruct Q4_K_M (~9GB).

   For the larger Qwen3-Coder 30B model (better for agentic tasks, needs ~20GB free RAM):
   ```bash
   python setup_models.py --model 30b
   ```

3. **Install Python dependencies**
   ```bash
   pip install llama-cpp-python
   ```

4. **Install and compile the VS Code extension**
   ```bash
   cd vscode-ai-agent
   npm install
   npm run compile
   ```

5. **Launch the extension**
   - Open the `local-mega-coding-agent` folder in VS Code
   - Press `F5` to launch the Extension Development Host
   - The AI Agent icon appears in the sidebar

### Usage

1. Click the **AI Agent** icon in the VS Code sidebar
2. Add files via right-click context menu or the "+" button
3. Describe your task in the chat
4. Click **Proceed** to let the agent gather context and generate changes
5. Review the diff and click **Apply** or **Reject**

## How It Works

1. **Chat** - The agent clarifies intent if needed.
2. **Agent Loop** - Tools inspect files, search the codebase, and gather context.
3. **Execute** - The model generates code changes.
4. **Review** - Generated changes are checked before apply.
5. **Apply** - Changes are written after validation.

Qwen3-14B-Instruct handles all stages with different temperature settings:
- **Chat/clarify** - temperature 0.7 for natural conversation
- **Code generation** - temperature 0.2 for deterministic output
- **Review** - temperature 0.3 for conservative correctness judgments

## Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| RAM | 8GB | 16GB |
| Disk | 5GB (model) | 6GB |
| Python | 3.10 | 3.11+ |
| VS Code | 1.85 | Latest |
| Node.js | 18+ | 20+ |

## Configuration

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for all available settings.

### Quick Examples

**Increase timeout for slow hardware:**
```json
// VS Code settings.json
{
  "ai-agent.timeouts.execute": 300000
}
```

**Disable auto-unload (keep models in RAM):**
```bash
export AI_AGENT_AUTO_UNLOAD_ENABLED=false
```

**Increase max output tokens:**
```bash
export AI_AGENT_MODEL_CODE_MAX_TOKENS=2048
```

## Commands

| Command | Description |
|---------|-------------|
| `AI Agent: Open Sidebar` | Open the agent panel |
| `AI Agent: Add File` | Add file to context |
| `AI Agent: Remove File` | Remove file from context |
| `AI Agent: Clear All Files` | Clear all files from context |
| `AI Agent: Unload Models` | Free RAM by unloading the main model |
| `AI Agent: Show Model Status` | View main model status and idle time |

## Project Structure

```text
local-mega-coding-agent/
|-- models/                     # GGUF model files (gitignored)
|   `-- qwen/
|-- scripts/
|   |-- backend/
|   |   |-- wrapper.py          # JSON-RPC router
|   |   `-- model_manager.py    # Model lifecycle management
|   |-- chunker/                # AST-based Python chunking
|   |-- agent/                  # Agentic loop
|   |   |-- turn_runner.py      # Multi-turn loop with tool dispatch
|   |   |-- router.py           # Scores tools against user input
|   |   |-- context.py          # Session context for system prompt
|   |   `-- history.py          # Per-turn transcript log
|   |-- critic/                 # Internal chat and review codepaths
|   |-- executor/               # Internal code generation codepaths
|   |-- memory/                 # Local context and memory utilities
|   |-- tools/                  # Extensible tool system
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
|   |-- ARCHITECTURE.md         # Technical architecture
|   |-- CONFIGURATION.md        # Configuration reference
|   `-- TOOLS.md                # Tool system reference
|-- tests/
|   |-- test_executor.py        # Executor security tests
|   |-- test_tools.py           # Tool system tests
|   |-- test_turn_runner.py     # Agentic loop tests
|   `-- test_tool_registry_parity.py  # Tool registry audit
|-- setup_models.py             # Model download script
`-- README.md
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## Troubleshooting

### Models fail to load

- Ensure models exist in `models/` directory
- Run `python setup_models.py` to download
- Check you have ~5GB free disk space

### Slow first response

- The extension now uses strict lazy startup
- Opening the repo, activating the extension, or opening the sidebar does not load the main model
- The Python backend and main model start on first intentional agent use
- The first real agent action may take a cold-start hit while the model loads

### Out of memory

- Use `AI Agent: Unload Models` command to unload the main model and free RAM
- Enable auto-unload in settings (default: 15 min idle)
- Consider using a machine with 32GB RAM

### Code generation returns garbage

- Ensure the model is the correct version
- Check Python backend logs in Output panel
- Try simplifying your task description

## License

MIT - see [LICENSE](LICENSE)

## Acknowledgments

- [llama.cpp](https://github.com/ggerganov/llama.cpp) - Fast inference engine
- [llama-cpp-python](https://github.com/abetlen/llama-cpp-python) - Python bindings
- [Qwen](https://qwenlm.github.io/) - Qwen3 language models
