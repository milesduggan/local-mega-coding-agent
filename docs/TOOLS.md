# Tool System Reference

The AI agent includes a pluggable tool system that allows execution of actions like running commands, file operations, and codebase searches.

## Overview

Tools are managed by a `ToolRegistry` singleton. Each tool:
- Has a unique name
- Declares its parameters via JSON schema
- Returns a `ToolResult` with success status, output, and metadata
- Can be marked as read-only or requiring user approval

## Available Tools

### bash

Execute shell commands with security checks.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `command` | string | Yes | - | Shell command to execute |
| `timeout` | integer | No | 120 | Timeout in seconds (max: 600) |
| `working_dir` | string | No | workspace root | Working directory (relative to workspace) |

**Security:**

Blocked commands (always rejected):
- `rm -rf /`, `rm -rf /*`, `rm -rf ~`
- `mkfs.*` (filesystem formatting)
- `dd if=... of=/dev/...`
- Fork bombs
- `curl|sh`, `wget|bash` (remote code execution)

Cautioned commands (allowed but logged):
- `rm -rf` (on non-root paths)
- `git push --force`
- `git reset --hard`
- `npm publish`

**Example:**

```json
{
  "tool": "bash",
  "params": {
    "command": "npm test",
    "timeout": 60
  }
}
```

---

### read_file

Read the contents of a file.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `path` | string | Yes | - | Path to file (relative to workspace) |
| `start_line` | integer | No | 1 | Start reading from this line (1-indexed) |
| `end_line` | integer | No | all | Stop at this line (inclusive) |

**Limits:**
- Max file size: 10MB

**Example:**

```json
{
  "tool": "read_file",
  "params": {
    "path": "src/main.py",
    "start_line": 10,
    "end_line": 50
  }
}
```

---

### write_file

Create or overwrite a file.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `path` | string | Yes | - | Path to file (relative to workspace) |
| `content` | string | Yes | - | Content to write |
| `create_dirs` | boolean | No | true | Create parent directories if needed |

**Example:**

```json
{
  "tool": "write_file",
  "params": {
    "path": "src/utils/helper.py",
    "content": "def helper():\n    return 42\n"
  }
}
```

---

### edit_file

Edit a file by replacing specific text.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `path` | string | Yes | - | Path to file (relative to workspace) |
| `old_text` | string | Yes | - | Text to find (must match exactly) |
| `new_text` | string | Yes | - | Replacement text |
| `replace_all` | boolean | No | false | Replace all occurrences |

**Example:**

```json
{
  "tool": "edit_file",
  "params": {
    "path": "src/config.py",
    "old_text": "DEBUG = False",
    "new_text": "DEBUG = True"
  }
}
```

---

### delete_file

Delete a file or directory.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `path` | string | Yes | - | Path to delete (relative to workspace) |
| `recursive` | boolean | No | false | Delete non-empty directories recursively |

**Example:**

```json
{
  "tool": "delete_file",
  "params": {
    "path": "temp/cache",
    "recursive": true
  }
}
```

---

### move_file

Move or rename a file or directory.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `source` | string | Yes | - | Source path |
| `destination` | string | Yes | - | Destination path |
| `overwrite` | boolean | No | false | Overwrite if destination exists |

**Example:**

```json
{
  "tool": "move_file",
  "params": {
    "source": "old_name.py",
    "destination": "new_name.py"
  }
}
```

---

### list_directory

List contents of a directory.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `path` | string | No | "." | Directory path (relative to workspace) |
| `recursive` | boolean | No | false | List recursively |
| `include_hidden` | boolean | No | false | Include hidden files (starting with .) |

**Limits:**
- Max entries: 1000

**Example:**

```json
{
  "tool": "list_directory",
  "params": {
    "path": "src",
    "recursive": true
  }
}
```

---

### glob

Find files matching a glob pattern.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `pattern` | string | Yes | - | Glob pattern (e.g., `**/*.py`) |
| `path` | string | No | "." | Directory to search in |
| `include_hidden` | boolean | No | false | Include hidden files |

**Pattern Examples:**
- `*.py` - Python files in current directory
- `**/*.py` - All Python files recursively
- `src/**/*.ts` - TypeScript files under src/
- `test_*.py` - Test files starting with test_

**Limits:**
- Max results: 500

**Example:**

```json
{
  "tool": "glob",
  "params": {
    "pattern": "**/*.py",
    "path": "src"
  }
}
```

---

### grep

Search file contents for a pattern.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `pattern` | string | Yes | - | Search pattern (regex supported) |
| `path` | string | No | "." | File or directory to search |
| `file_pattern` | string | No | all | Only search files matching this glob |
| `case_insensitive` | boolean | No | false | Case-insensitive search |
| `context_lines` | integer | No | 0 | Lines of context before/after match |

**Limits:**
- Max results: 500
- Max file size for search: 5MB
- Skips binary files and common ignored directories (node_modules, .git, etc.)

**Example:**

```json
{
  "tool": "grep",
  "params": {
    "pattern": "def.*execute",
    "file_pattern": "*.py",
    "context_lines": 2
  }
}
```

---

### find_definition

Find function, class, or variable definitions.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `symbol` | string | Yes | - | Name to find |
| `path` | string | No | "." | Directory to search |
| `language` | string | No | auto | Language hint: python, javascript, typescript, go, rust |

**Example:**

```json
{
  "tool": "find_definition",
  "params": {
    "symbol": "execute",
    "language": "python"
  }
}
```

---

## Security

### Path Validation

All file operations validate that paths stay within the workspace:

```python
def validate_path_in_workspace(file_path: str, workspace_root: str) -> str:
    resolved = os.path.normpath(os.path.join(workspace_root, file_path))
    if not resolved.startswith(workspace_root):
        raise ToolError("Path escapes workspace")
    return resolved
```

### Tool Approval

Tools are categorized by risk level:

| Category | Examples | Requires Approval |
|----------|----------|-------------------|
| Read-only | read_file, glob, grep | No |
| Write | write_file, edit_file | Yes |
| Destructive | delete_file, bash | Yes |

---

## JSON-RPC Interface

### set_workspace

Set the workspace root before using tools.

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "set_workspace",
  "params": {
    "workspace_root": "/path/to/project"
  }
}
```

### list_tools

List all available tools with their schemas.

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "list_tools",
  "params": {}
}
```

### execute_tool

Execute a tool by name.

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "execute_tool",
  "params": {
    "tool": "grep",
    "params": {
      "pattern": "TODO",
      "file_pattern": "*.py"
    }
  }
}
```

**Response:**

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "success": true,
    "output": "src/main.py:42: # TODO: implement this\n...",
    "error": null,
    "metadata": {
      "match_count": 5,
      "files_searched": 12
    }
  }
}
```

---

## Adding Custom Tools

1. Create a new file in `scripts/tools/`:

```python
from scripts.tools.base import Tool, ToolResult, ToolParameter
from scripts.tools.registry import register_tool

@register_tool
class MyCustomTool(Tool):
    name = "my_tool"
    description = "Does something useful"
    parameters = [
        ToolParameter(
            name="input",
            type="string",
            description="Input value",
            required=True,
        ),
    ]

    requires_approval = False
    is_read_only = True

    def execute(self, input: str) -> ToolResult:
        # Your logic here
        return ToolResult.ok(output=f"Processed: {input}")
```

2. Import the tool in `scripts/tools/__init__.py` to auto-register it.

3. The tool is now available via `execute_tool` RPC.
