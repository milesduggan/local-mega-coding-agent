"""
File operation tools for reading, writing, and manipulating files.

All operations are scoped to the workspace directory for security.
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.tools.base import Tool, ToolResult, ToolParameter, ToolError
from scripts.tools.registry import register_tool

log = logging.getLogger(__name__)

# Maximum file size for reading (10MB)
MAX_READ_SIZE = 10_000_000

# Maximum number of files to list
MAX_LIST_FILES = 1000


def validate_path_in_workspace(file_path: str, workspace_root: str) -> str:
    """
    Validate that a path stays within the workspace.

    Args:
        file_path: Path to validate (relative or absolute)
        workspace_root: Workspace root directory

    Returns:
        Resolved absolute path

    Raises:
        ToolError: If path escapes workspace
    """
    # Handle both relative and absolute paths
    if os.path.isabs(file_path):
        resolved = os.path.normpath(file_path)
    else:
        resolved = os.path.normpath(os.path.join(workspace_root, file_path))

    normalized_root = os.path.normpath(workspace_root)

    # Check path is within workspace
    if not resolved.startswith(normalized_root + os.sep) and resolved != normalized_root:
        raise ToolError(
            f"Path escapes workspace: {file_path}",
            recoverable=False,
        )

    return resolved


@register_tool
class ReadFileTool(Tool):
    """Read the contents of a file."""

    name = "read_file"
    description = (
        "Read the contents of a file. Returns the file content as text. "
        "Use for examining source code, configuration files, etc."
    )
    parameters = [
        ToolParameter(
            name="path",
            type="string",
            description="Path to the file (relative to workspace)",
            required=True,
        ),
        ToolParameter(
            name="start_line",
            type="integer",
            description="Start reading from this line (1-indexed). Default: 1",
            required=False,
            default=1,
        ),
        ToolParameter(
            name="end_line",
            type="integer",
            description="Stop reading at this line (inclusive). Default: read all",
            required=False,
            default=None,
        ),
    ]

    requires_approval = False
    is_read_only = True

    def execute(
        self,
        path: str,
        start_line: int = 1,
        end_line: Optional[int] = None,
    ) -> ToolResult:
        """Read file contents."""
        if not self.workspace_root:
            return ToolResult.fail(error="Workspace root not set")

        try:
            full_path = validate_path_in_workspace(path, self.workspace_root)
        except ToolError as e:
            return ToolResult.fail(error=str(e))

        if not os.path.exists(full_path):
            return ToolResult.fail(error=f"File not found: {path}")

        if not os.path.isfile(full_path):
            return ToolResult.fail(error=f"Not a file: {path}")

        # Check file size
        file_size = os.path.getsize(full_path)
        if file_size > MAX_READ_SIZE:
            return ToolResult.fail(
                error=f"File too large: {file_size / 1_000_000:.1f}MB (max {MAX_READ_SIZE / 1_000_000:.0f}MB)"
            )

        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            total_lines = len(lines)

            # Apply line range
            start_idx = max(0, start_line - 1)
            end_idx = total_lines if end_line is None else min(end_line, total_lines)

            selected_lines = lines[start_idx:end_idx]
            content = "".join(selected_lines)

            return ToolResult.ok(
                output=content,
                total_lines=total_lines,
                lines_returned=len(selected_lines),
                start_line=start_idx + 1,
                end_line=end_idx,
            )

        except UnicodeDecodeError:
            return ToolResult.fail(error=f"Cannot read file as text: {path}")
        except Exception as e:
            return ToolResult.fail(error=f"Error reading file: {type(e).__name__}: {e}")


@register_tool
class WriteFileTool(Tool):
    """Write content to a file (create or overwrite)."""

    name = "write_file"
    description = (
        "Write content to a file, creating it if it doesn't exist or "
        "overwriting if it does. Use for creating new files or completely "
        "replacing file contents."
    )
    parameters = [
        ToolParameter(
            name="path",
            type="string",
            description="Path to the file (relative to workspace)",
            required=True,
        ),
        ToolParameter(
            name="content",
            type="string",
            description="Content to write to the file",
            required=True,
        ),
        ToolParameter(
            name="create_dirs",
            type="boolean",
            description="Create parent directories if they don't exist. Default: true",
            required=False,
            default=True,
        ),
    ]

    requires_approval = True
    is_read_only = False

    def execute(
        self,
        path: str,
        content: str,
        create_dirs: bool = True,
    ) -> ToolResult:
        """Write content to a file."""
        if not self.workspace_root:
            return ToolResult.fail(error="Workspace root not set")

        try:
            full_path = validate_path_in_workspace(path, self.workspace_root)
        except ToolError as e:
            return ToolResult.fail(error=str(e))

        try:
            # Create parent directories if needed
            parent = os.path.dirname(full_path)
            if create_dirs and parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)

            # Check if file exists (for metadata)
            existed = os.path.exists(full_path)

            # Write the file
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)

            return ToolResult.ok(
                output=f"{'Overwrote' if existed else 'Created'} {path} ({len(content)} bytes)",
                created=not existed,
                bytes_written=len(content),
            )

        except PermissionError:
            return ToolResult.fail(error=f"Permission denied: {path}")
        except Exception as e:
            return ToolResult.fail(error=f"Error writing file: {type(e).__name__}: {e}")


@register_tool
class EditFileTool(Tool):
    """Edit a file by replacing specific text."""

    name = "edit_file"
    description = (
        "Edit a file by replacing specific text with new text. "
        "The old_text must match exactly (including whitespace). "
        "Use for making targeted changes to existing files."
    )
    parameters = [
        ToolParameter(
            name="path",
            type="string",
            description="Path to the file (relative to workspace)",
            required=True,
        ),
        ToolParameter(
            name="old_text",
            type="string",
            description="Text to find and replace (must match exactly)",
            required=True,
        ),
        ToolParameter(
            name="new_text",
            type="string",
            description="Text to replace with",
            required=True,
        ),
        ToolParameter(
            name="replace_all",
            type="boolean",
            description="Replace all occurrences (default: false, replace first only)",
            required=False,
            default=False,
        ),
    ]

    requires_approval = True
    is_read_only = False

    def execute(
        self,
        path: str,
        old_text: str,
        new_text: str,
        replace_all: bool = False,
    ) -> ToolResult:
        """Edit a file by text replacement."""
        if not self.workspace_root:
            return ToolResult.fail(error="Workspace root not set")

        try:
            full_path = validate_path_in_workspace(path, self.workspace_root)
        except ToolError as e:
            return ToolResult.fail(error=str(e))

        if not os.path.exists(full_path):
            return ToolResult.fail(error=f"File not found: {path}")

        if not os.path.isfile(full_path):
            return ToolResult.fail(error=f"Not a file: {path}")

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Check if old_text exists
            if old_text not in content:
                return ToolResult.fail(
                    error=f"Text not found in file. The old_text must match exactly."
                )

            # Count occurrences
            count = content.count(old_text)

            # Perform replacement
            if replace_all:
                new_content = content.replace(old_text, new_text)
                replacements = count
            else:
                new_content = content.replace(old_text, new_text, 1)
                replacements = 1

            # Write back
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            return ToolResult.ok(
                output=f"Replaced {replacements} occurrence(s) in {path}",
                replacements=replacements,
                total_occurrences=count,
            )

        except Exception as e:
            return ToolResult.fail(error=f"Error editing file: {type(e).__name__}: {e}")


@register_tool
class DeleteFileTool(Tool):
    """Delete a file or directory."""

    name = "delete_file"
    description = (
        "Delete a file or directory. For directories, use recursive=true "
        "to delete non-empty directories. Be careful with this operation."
    )
    parameters = [
        ToolParameter(
            name="path",
            type="string",
            description="Path to delete (relative to workspace)",
            required=True,
        ),
        ToolParameter(
            name="recursive",
            type="boolean",
            description="For directories: delete recursively. Default: false",
            required=False,
            default=False,
        ),
    ]

    requires_approval = True
    is_read_only = False

    def execute(self, path: str, recursive: bool = False) -> ToolResult:
        """Delete a file or directory."""
        if not self.workspace_root:
            return ToolResult.fail(error="Workspace root not set")

        try:
            full_path = validate_path_in_workspace(path, self.workspace_root)
        except ToolError as e:
            return ToolResult.fail(error=str(e))

        if not os.path.exists(full_path):
            return ToolResult.fail(error=f"Path not found: {path}")

        try:
            if os.path.isfile(full_path):
                os.remove(full_path)
                return ToolResult.ok(output=f"Deleted file: {path}")

            elif os.path.isdir(full_path):
                if recursive:
                    shutil.rmtree(full_path)
                    return ToolResult.ok(output=f"Deleted directory recursively: {path}")
                else:
                    # Only delete empty directories
                    if os.listdir(full_path):
                        return ToolResult.fail(
                            error=f"Directory not empty: {path}. Use recursive=true to delete."
                        )
                    os.rmdir(full_path)
                    return ToolResult.ok(output=f"Deleted empty directory: {path}")

            else:
                return ToolResult.fail(error=f"Unknown path type: {path}")

        except PermissionError:
            return ToolResult.fail(error=f"Permission denied: {path}")
        except Exception as e:
            return ToolResult.fail(error=f"Error deleting: {type(e).__name__}: {e}")


@register_tool
class MoveFileTool(Tool):
    """Move or rename a file or directory."""

    name = "move_file"
    description = (
        "Move or rename a file or directory. Both source and destination "
        "must be within the workspace."
    )
    parameters = [
        ToolParameter(
            name="source",
            type="string",
            description="Source path (relative to workspace)",
            required=True,
        ),
        ToolParameter(
            name="destination",
            type="string",
            description="Destination path (relative to workspace)",
            required=True,
        ),
        ToolParameter(
            name="overwrite",
            type="boolean",
            description="Overwrite destination if it exists. Default: false",
            required=False,
            default=False,
        ),
    ]

    requires_approval = True
    is_read_only = False

    def execute(
        self,
        source: str,
        destination: str,
        overwrite: bool = False,
    ) -> ToolResult:
        """Move or rename a file or directory."""
        if not self.workspace_root:
            return ToolResult.fail(error="Workspace root not set")

        try:
            src_path = validate_path_in_workspace(source, self.workspace_root)
            dst_path = validate_path_in_workspace(destination, self.workspace_root)
        except ToolError as e:
            return ToolResult.fail(error=str(e))

        if not os.path.exists(src_path):
            return ToolResult.fail(error=f"Source not found: {source}")

        if os.path.exists(dst_path) and not overwrite:
            return ToolResult.fail(
                error=f"Destination exists: {destination}. Use overwrite=true to replace."
            )

        try:
            # Create parent directory if needed
            dst_parent = os.path.dirname(dst_path)
            if dst_parent and not os.path.exists(dst_parent):
                os.makedirs(dst_parent, exist_ok=True)

            # If destination exists and overwrite is True, remove it first
            if os.path.exists(dst_path) and overwrite:
                if os.path.isdir(dst_path):
                    shutil.rmtree(dst_path)
                else:
                    os.remove(dst_path)

            shutil.move(src_path, dst_path)
            return ToolResult.ok(output=f"Moved {source} -> {destination}")

        except PermissionError:
            return ToolResult.fail(error=f"Permission denied")
        except Exception as e:
            return ToolResult.fail(error=f"Error moving: {type(e).__name__}: {e}")


@register_tool
class ListDirectoryTool(Tool):
    """List contents of a directory."""

    name = "list_directory"
    description = (
        "List files and directories in a path. Returns names with "
        "type indicators (/ for directories). Use for exploring "
        "project structure."
    )
    parameters = [
        ToolParameter(
            name="path",
            type="string",
            description="Path to list (relative to workspace). Default: workspace root",
            required=False,
            default=".",
        ),
        ToolParameter(
            name="recursive",
            type="boolean",
            description="List recursively. Default: false",
            required=False,
            default=False,
        ),
        ToolParameter(
            name="include_hidden",
            type="boolean",
            description="Include hidden files (starting with .). Default: false",
            required=False,
            default=False,
        ),
    ]

    requires_approval = False
    is_read_only = True

    def execute(
        self,
        path: str = ".",
        recursive: bool = False,
        include_hidden: bool = False,
    ) -> ToolResult:
        """List directory contents."""
        if not self.workspace_root:
            return ToolResult.fail(error="Workspace root not set")

        try:
            full_path = validate_path_in_workspace(path, self.workspace_root)
        except ToolError as e:
            return ToolResult.fail(error=str(e))

        if not os.path.exists(full_path):
            return ToolResult.fail(error=f"Path not found: {path}")

        if not os.path.isdir(full_path):
            return ToolResult.fail(error=f"Not a directory: {path}")

        try:
            entries = []
            count = 0

            if recursive:
                for root, dirs, files in os.walk(full_path):
                    # Skip hidden directories if not included
                    if not include_hidden:
                        dirs[:] = [d for d in dirs if not d.startswith(".")]

                    rel_root = os.path.relpath(root, full_path)
                    if rel_root == ".":
                        rel_root = ""
                    else:
                        rel_root += os.sep

                    for d in sorted(dirs):
                        if include_hidden or not d.startswith("."):
                            entries.append(f"{rel_root}{d}/")
                            count += 1
                            if count >= MAX_LIST_FILES:
                                break

                    for f in sorted(files):
                        if include_hidden or not f.startswith("."):
                            entries.append(f"{rel_root}{f}")
                            count += 1
                            if count >= MAX_LIST_FILES:
                                break

                    if count >= MAX_LIST_FILES:
                        break
            else:
                items = sorted(os.listdir(full_path))
                for item in items:
                    if not include_hidden and item.startswith("."):
                        continue

                    item_path = os.path.join(full_path, item)
                    if os.path.isdir(item_path):
                        entries.append(f"{item}/")
                    else:
                        entries.append(item)

                    count += 1
                    if count >= MAX_LIST_FILES:
                        break

            output = "\n".join(entries)
            if count >= MAX_LIST_FILES:
                output += f"\n\n[Truncated at {MAX_LIST_FILES} entries]"

            return ToolResult.ok(
                output=output or "(empty directory)",
                entry_count=len(entries),
                truncated=count >= MAX_LIST_FILES,
            )

        except PermissionError:
            return ToolResult.fail(error=f"Permission denied: {path}")
        except Exception as e:
            return ToolResult.fail(error=f"Error listing directory: {type(e).__name__}: {e}")
