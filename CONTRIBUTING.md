# Contributing to Local AI Agent

Thank you for your interest in contributing. This document provides guidelines for development setup and contribution workflow.

## Development Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- VS Code
- 16GB RAM minimum, 32GB recommended (for running models)
- ~9GB disk space (for model)

### Steps

1. **Fork and clone the repository**
   ```bash
   git clone https://github.com/milesduggan/local-mega-coding-agent.git
   cd local-mega-coding-agent
   ```

2. **Download models**
   ```bash
   python setup_models.py
   ```
   Downloads Qwen3-14B-Instruct (~9GB). Pass `--model 30b` to download the larger 30B variant instead.

3. **Install Python dependencies**
   ```bash
   pip install llama-cpp-python
   pip install pytest  # For running tests
   ```

4. **Install extension dependencies**
   ```bash
   cd vscode-ai-agent
   npm install
   npm run compile
   ```

5. **Launch development environment**
   - Open the `local-mega-coding-agent` folder in VS Code
   - Press `F5` to launch the Extension Development Host
   - The extension runs in a new VS Code window

## Project Structure

```text
local-mega-coding-agent/
|-- scripts/                    # Python backend
|   |-- backend/
|   |   |-- wrapper.py          # JSON-RPC router (entry point)
|   |   `-- model_manager.py    # Model lifecycle management
|   |-- agent/                  # Agentic loop components
|   |   |-- turn_runner.py      # Agentic loop execution
|   |   |-- router.py           # Tool call dispatch
|   |   |-- context.py          # SessionContext (per-session state)
|   |   `-- history.py          # HistoryLog (turn history)
|   |-- chunker/                # AST-based Python chunking
|   |   |-- python_chunker.py   # Parse Python into chunks
|   |   |-- selector.py         # Select relevant chunks
|   |   `-- reconstructor.py    # Rebuild file from chunks
|   |-- critic/
|   |   `-- critic.py           # Internal chat and review codepaths
|   |-- executor/
|   |   `-- executor.py         # Internal code generation codepaths
|   |-- memory/
|   |   `-- context_manager.py  # Local context and memory utilities
|   `-- config.py               # Central configuration
|-- vscode-ai-agent/            # TypeScript extension
|   |-- src/
|   |   |-- extension.ts        # Extension entry point
|   |   |-- SidebarProvider.ts  # UI and workflow logic
|   |   `-- pythonBackend.ts    # IPC client for Python
|   `-- package.json            # Extension manifest
|-- models/                     # GGUF model files (gitignored)
|-- tests/                      # Test files
`-- docs/                       # Documentation
```

## Code Style

### Python

- Follow [PEP 8](https://peps.python.org/pep-0008/)
- Use type hints for function signatures
- Write docstrings for public functions
- Maximum line length: 100 characters

```python
def my_function(param: str, count: int = 10) -> List[str]:
    """
    Brief description of the function.

    Args:
        param: Description of param
        count: Description of count

    Returns:
        Description of return value
    """
    pass
```

### TypeScript

- Follow the ESLint configuration in the repo
- Use `async/await` over callbacks
- Use TypeScript strict mode types

```typescript
async function myFunction(param: string): Promise<Result> {
  const result = await someAsyncOperation(param);
  return result;
}
```

## Testing

### Python Tests

```bash
# Run all Python tests
python -m pytest tests/

# Run specific test file
python -m pytest tests/test_chunker.py

# Run with verbose output
python -m pytest tests/ -v
```

### TypeScript Tests

```bash
cd vscode-ai-agent
npm test
```

### Manual Testing

1. Press `F5` in VS Code to launch Extension Development Host
2. Open a Python project in the new window
3. Test the full workflow: add files -> chat -> proceed -> review -> apply

## Pull Request Process

1. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Write clear, focused commits
   - Include tests for new functionality
   - Update documentation if needed

3. **Test locally**
   - Run Python tests
   - Run TypeScript tests
   - Manual test the extension

4. **Push and create PR**
   ```bash
   git push origin feature/your-feature-name
   ```
   - Create a Pull Request on GitHub
   - Fill in the PR template
   - Link any related issues

5. **Address review feedback**
   - Respond to comments
   - Make requested changes
   - Re-request review when ready

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```text
<type>: <description>

[optional body]

[optional footer]
```

### Types

| Type | Description |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `style` | Formatting, no code change |
| `refactor` | Code change without feature/fix |
| `test` | Adding or updating tests |
| `chore` | Build, tooling, dependencies |

### Examples

```text
feat: add retry logic to model loading

fix: handle empty file selection gracefully

docs: update configuration reference

refactor: extract chunk validation to separate function

test: add unit tests for reconstructor
```

## Reporting Issues

### Bug Reports

Please include:
- VS Code version
- Python version
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Error messages and logs

### Feature Requests

Please include:
- Use case description
- Proposed solution (if any)
- Alternatives considered

## Architecture Guidelines

### Adding a New JSON-RPC Method

1. **Add handler in `wrapper.py`**
   ```python
   def handle_my_method(params: dict) -> dict:
       """Handle my_method requests."""
       # Implementation
       return result
   ```

2. **Add route in `handle_message()`**
   ```python
   elif method == "my_method":
       result = handle_my_method(params)
       send_response(msg_id, result=result)
   ```

3. **Add TypeScript client method in `pythonBackend.ts`**
   ```typescript
   async myMethod(param: string): Promise<Result> {
     return this.call("my_method", { param }, this.getTimeout("chat"));
   }
   ```

### Adding Configuration

1. **Add to `config.py`**
   ```python
   MY_SETTING = _get_int("AI_AGENT_MY_SETTING", 100)
   ```

2. **Import where needed**
   ```python
   from scripts.config import MY_SETTING
   ```

3. **Document in `docs/CONFIGURATION.md`**

### Modifying Model Behavior

1. Changes to model parameters should use `config.py`
2. Document any behavior changes

## Questions?

- Open a GitHub Issue for bugs or features
- Check existing issues first
- Be respectful and constructive

Thank you for contributing!
