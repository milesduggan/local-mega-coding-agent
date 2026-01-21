"""
Bash tool for executing shell commands.

Security considerations:
- Commands run in workspace directory by default
- Dangerous commands are blocked
- Timeout prevents runaway processes
- Output is truncated to prevent memory issues
"""

import logging
import os
import re
import shlex
import subprocess
import sys
from typing import Any, Dict, List, Optional, Set

from scripts.tools.base import Tool, ToolResult, ToolParameter, ToolError
from scripts.tools.registry import register_tool

log = logging.getLogger(__name__)

# Maximum output size (characters)
MAX_OUTPUT_SIZE = 100_000

# Default timeout in seconds
DEFAULT_TIMEOUT = 120

# Commands that are always blocked (case-insensitive patterns)
BLOCKED_COMMANDS: List[str] = [
    r"rm\s+-rf\s+/",  # rm -rf /
    r"rm\s+-rf\s+/\*",  # rm -rf /*
    r"rm\s+-rf\s+~",  # rm -rf ~
    r"rm\s+-fr\s+/",  # rm -fr /
    r"mkfs\.",  # mkfs.* (format filesystem)
    r"dd\s+if=.+of=/dev/",  # dd to device
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:",  # Fork bomb
    r">\s*/dev/sd",  # Write to disk device
    r"chmod\s+-R\s+777\s+/",  # chmod 777 /
    r"chown\s+-R\s+.+\s+/\s*$",  # chown / (root)
    r"curl.+\|\s*sh",  # curl | sh
    r"wget.+\|\s*sh",  # wget | sh
    r"curl.+\|\s*bash",  # curl | bash
    r"wget.+\|\s*bash",  # wget | bash
]

# Commands that require extra caution (warning but allowed)
CAUTION_COMMANDS: List[str] = [
    r"rm\s+-rf",  # rm -rf (but not /)
    r"rm\s+-r",  # rm -r
    r"git\s+push\s+.*--force",  # git push --force
    r"git\s+reset\s+--hard",  # git reset --hard
    r"npm\s+publish",  # npm publish
    r"pip\s+install",  # pip install (could install malware)
]

# Safe read-only commands (can be auto-approved)
SAFE_COMMANDS: Set[str] = {
    "ls", "cat", "head", "tail", "grep", "find", "wc", "diff",
    "pwd", "echo", "date", "whoami", "hostname", "uname",
    "git status", "git log", "git diff", "git branch", "git show",
    "npm list", "npm outdated", "pip list", "pip show",
    "python --version", "node --version", "npm --version",
    "which", "where", "type", "file",
}


def is_command_blocked(command: str) -> Optional[str]:
    """
    Check if a command matches a blocked pattern.

    Returns:
        Reason string if blocked, None if allowed
    """
    command_lower = command.lower()

    for pattern in BLOCKED_COMMANDS:
        if re.search(pattern, command_lower):
            return f"Command matches blocked pattern: {pattern}"

    return None


def is_command_caution(command: str) -> Optional[str]:
    """
    Check if a command requires caution.

    Returns:
        Warning message if caution needed, None if safe
    """
    command_lower = command.lower()

    for pattern in CAUTION_COMMANDS:
        if re.search(pattern, command_lower):
            return f"This command may have destructive effects: {pattern}"

    return None


def is_command_safe(command: str) -> bool:
    """Check if a command is in the safe list (read-only)."""
    # Get the base command (first word)
    parts = command.strip().split()
    if not parts:
        return False

    base_cmd = parts[0].lower()

    # Check exact match
    if base_cmd in SAFE_COMMANDS:
        return True

    # Check command with first arg (e.g., "git status")
    if len(parts) >= 2:
        cmd_with_arg = f"{base_cmd} {parts[1].lower()}"
        if cmd_with_arg in SAFE_COMMANDS:
            return True

    return False


@register_tool
class BashTool(Tool):
    """
    Execute shell commands.

    Security:
    - Dangerous commands are blocked
    - Commands run in workspace directory
    - Output is truncated to prevent memory issues
    - Timeout prevents runaway processes
    """

    name = "bash"
    description = (
        "Execute a shell command. Use for running build commands, "
        "git operations, tests, and other CLI tasks. Commands run "
        "in the workspace directory."
    )
    parameters = [
        ToolParameter(
            name="command",
            type="string",
            description="The shell command to execute",
            required=True,
        ),
        ToolParameter(
            name="timeout",
            type="integer",
            description="Timeout in seconds (default: 120, max: 600)",
            required=False,
            default=DEFAULT_TIMEOUT,
        ),
        ToolParameter(
            name="working_dir",
            type="string",
            description="Working directory (relative to workspace). Default: workspace root",
            required=False,
            default=None,
        ),
    ]

    requires_approval = True  # Most bash commands should be approved
    is_read_only = False

    def execute(
        self,
        command: str,
        timeout: int = DEFAULT_TIMEOUT,
        working_dir: Optional[str] = None,
    ) -> ToolResult:
        """Execute a shell command."""
        # Validate command
        if not command or not command.strip():
            return ToolResult.fail(error="Empty command")

        # Security check: blocked commands
        blocked_reason = is_command_blocked(command)
        if blocked_reason:
            return ToolResult.fail(
                error=f"Command blocked for security: {blocked_reason}"
            )

        # Determine working directory
        cwd = self.workspace_root
        if working_dir:
            if self.workspace_root:
                # Resolve relative to workspace
                cwd = os.path.normpath(os.path.join(self.workspace_root, working_dir))
                # Security: ensure we stay within workspace
                if not cwd.startswith(os.path.normpath(self.workspace_root)):
                    return ToolResult.fail(
                        error=f"Working directory escapes workspace: {working_dir}"
                    )
            else:
                cwd = working_dir

        if cwd and not os.path.isdir(cwd):
            return ToolResult.fail(error=f"Working directory does not exist: {cwd}")

        # Clamp timeout
        timeout = min(max(timeout, 1), 600)

        # Check for caution commands
        caution_msg = is_command_caution(command)
        if caution_msg:
            log.warning(f"Executing cautioned command: {caution_msg}")

        # Determine if this is a safe command (for metadata)
        is_safe = is_command_safe(command)

        try:
            log.info(f"Executing bash: {command[:100]}{'...' if len(command) > 100 else ''}")

            # Use shell=True for proper command parsing
            # On Windows, use cmd.exe; on Unix, use sh
            if sys.platform == "win32":
                shell_cmd = command
            else:
                shell_cmd = command

            result = subprocess.run(
                shell_cmd,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "TERM": "dumb"},  # Disable colors
            )

            # Combine stdout and stderr
            output = ""
            if result.stdout:
                output += result.stdout
            if result.stderr:
                if output:
                    output += "\n--- stderr ---\n"
                output += result.stderr

            # Truncate if needed
            if len(output) > MAX_OUTPUT_SIZE:
                output = output[:MAX_OUTPUT_SIZE] + f"\n\n[Output truncated at {MAX_OUTPUT_SIZE} characters]"

            # Determine success
            success = result.returncode == 0

            return ToolResult(
                success=success,
                output=output or "(no output)",
                error=None if success else f"Exit code: {result.returncode}",
                metadata={
                    "exit_code": result.returncode,
                    "is_safe_command": is_safe,
                    "working_dir": cwd,
                },
            )

        except subprocess.TimeoutExpired:
            return ToolResult.fail(
                error=f"Command timed out after {timeout} seconds",
                output="",
                timeout=True,
            )

        except FileNotFoundError as e:
            return ToolResult.fail(error=f"Command not found: {e}")

        except PermissionError as e:
            return ToolResult.fail(error=f"Permission denied: {e}")

        except Exception as e:
            log.error(f"Bash execution error: {type(e).__name__}: {e}")
            return ToolResult.fail(error=f"Execution error: {type(e).__name__}: {e}")
