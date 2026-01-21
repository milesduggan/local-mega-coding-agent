"""
Search tools for finding files and searching content.

Provides glob-based file finding and grep-like content search.
"""

import fnmatch
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from scripts.tools.base import Tool, ToolResult, ToolParameter, ToolError
from scripts.tools.registry import register_tool

log = logging.getLogger(__name__)

# Maximum number of results to return
MAX_RESULTS = 500

# Maximum file size for content search (5MB)
MAX_SEARCH_FILE_SIZE = 5_000_000

# Directories to skip during search
SKIP_DIRS: Set[str] = {
    ".git", ".svn", ".hg",
    "node_modules", "__pycache__", ".pytest_cache",
    ".venv", "venv", "env",
    "dist", "build", ".next", ".nuxt",
    ".idea", ".vscode",
    "coverage", ".nyc_output",
}

# Binary file extensions to skip
BINARY_EXTENSIONS: Set[str] = {
    ".pyc", ".pyo", ".so", ".dll", ".dylib", ".exe",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp",
    ".mp3", ".mp4", ".wav", ".avi", ".mkv", ".mov",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".lock",  # package-lock.json etc can be huge
}


def should_skip_dir(dirname: str) -> bool:
    """Check if a directory should be skipped during search."""
    return dirname in SKIP_DIRS or dirname.startswith(".")


def should_skip_file(filename: str) -> bool:
    """Check if a file should be skipped (binary, etc.)."""
    ext = os.path.splitext(filename)[1].lower()
    return ext in BINARY_EXTENSIONS


def validate_path_in_workspace(file_path: str, workspace_root: str) -> str:
    """Validate that a path stays within the workspace."""
    if os.path.isabs(file_path):
        resolved = os.path.normpath(file_path)
    else:
        resolved = os.path.normpath(os.path.join(workspace_root, file_path))

    normalized_root = os.path.normpath(workspace_root)

    if not resolved.startswith(normalized_root + os.sep) and resolved != normalized_root:
        raise ToolError(f"Path escapes workspace: {file_path}", recoverable=False)

    return resolved


@register_tool
class GlobTool(Tool):
    """Find files matching a glob pattern."""

    name = "glob"
    description = (
        "Find files matching a glob pattern (e.g., '**/*.py' for all Python files). "
        "Useful for discovering files in a project. Returns list of matching paths."
    )
    parameters = [
        ToolParameter(
            name="pattern",
            type="string",
            description="Glob pattern (e.g., '*.py', '**/*.ts', 'src/**/*.js')",
            required=True,
        ),
        ToolParameter(
            name="path",
            type="string",
            description="Directory to search in (relative to workspace). Default: workspace root",
            required=False,
            default=".",
        ),
        ToolParameter(
            name="include_hidden",
            type="boolean",
            description="Include hidden files/directories. Default: false",
            required=False,
            default=False,
        ),
    ]

    requires_approval = False
    is_read_only = True

    def execute(
        self,
        pattern: str,
        path: str = ".",
        include_hidden: bool = False,
    ) -> ToolResult:
        """Find files matching glob pattern."""
        if not self.workspace_root:
            return ToolResult.fail(error="Workspace root not set")

        try:
            search_path = validate_path_in_workspace(path, self.workspace_root)
        except ToolError as e:
            return ToolResult.fail(error=str(e))

        if not os.path.exists(search_path):
            return ToolResult.fail(error=f"Path not found: {path}")

        if not os.path.isdir(search_path):
            return ToolResult.fail(error=f"Not a directory: {path}")

        try:
            matches = []
            count = 0

            # Use pathlib for glob matching
            search_pathlib = Path(search_path)

            # Handle recursive (**) patterns
            if "**" in pattern:
                # pathlib.glob handles ** correctly
                for match in search_pathlib.glob(pattern):
                    # Skip hidden if not included
                    if not include_hidden:
                        parts = match.relative_to(search_pathlib).parts
                        if any(p.startswith(".") for p in parts):
                            continue

                    # Skip ignored directories
                    if any(should_skip_dir(p) for p in match.parts):
                        continue

                    # Get relative path from workspace
                    rel_path = os.path.relpath(str(match), self.workspace_root)
                    matches.append(rel_path)
                    count += 1

                    if count >= MAX_RESULTS:
                        break
            else:
                # Non-recursive glob
                for match in search_pathlib.glob(pattern):
                    if not include_hidden and match.name.startswith("."):
                        continue

                    rel_path = os.path.relpath(str(match), self.workspace_root)
                    matches.append(rel_path)
                    count += 1

                    if count >= MAX_RESULTS:
                        break

            # Sort for consistent output
            matches.sort()

            output = "\n".join(matches)
            if count >= MAX_RESULTS:
                output += f"\n\n[Truncated at {MAX_RESULTS} results]"

            return ToolResult.ok(
                output=output or "(no matches)",
                match_count=len(matches),
                truncated=count >= MAX_RESULTS,
            )

        except Exception as e:
            return ToolResult.fail(error=f"Glob error: {type(e).__name__}: {e}")


@register_tool
class GrepTool(Tool):
    """Search file contents for a pattern."""

    name = "grep"
    description = (
        "Search file contents for a pattern (regex supported). "
        "Returns matching lines with file paths and line numbers. "
        "Useful for finding code patterns, function definitions, etc."
    )
    parameters = [
        ToolParameter(
            name="pattern",
            type="string",
            description="Search pattern (regex supported)",
            required=True,
        ),
        ToolParameter(
            name="path",
            type="string",
            description="File or directory to search (relative to workspace). Default: workspace root",
            required=False,
            default=".",
        ),
        ToolParameter(
            name="file_pattern",
            type="string",
            description="Only search files matching this glob (e.g., '*.py'). Default: all files",
            required=False,
            default=None,
        ),
        ToolParameter(
            name="case_insensitive",
            type="boolean",
            description="Case-insensitive search. Default: false",
            required=False,
            default=False,
        ),
        ToolParameter(
            name="context_lines",
            type="integer",
            description="Number of context lines before/after match. Default: 0",
            required=False,
            default=0,
        ),
    ]

    requires_approval = False
    is_read_only = True

    def execute(
        self,
        pattern: str,
        path: str = ".",
        file_pattern: Optional[str] = None,
        case_insensitive: bool = False,
        context_lines: int = 0,
    ) -> ToolResult:
        """Search file contents for a pattern."""
        if not self.workspace_root:
            return ToolResult.fail(error="Workspace root not set")

        try:
            search_path = validate_path_in_workspace(path, self.workspace_root)
        except ToolError as e:
            return ToolResult.fail(error=str(e))

        if not os.path.exists(search_path):
            return ToolResult.fail(error=f"Path not found: {path}")

        # Compile regex
        try:
            flags = re.IGNORECASE if case_insensitive else 0
            regex = re.compile(pattern, flags)
        except re.error as e:
            return ToolResult.fail(error=f"Invalid regex pattern: {e}")

        results = []
        files_searched = 0
        matches_found = 0

        def search_file(file_path: str) -> List[str]:
            """Search a single file and return matching lines."""
            nonlocal files_searched, matches_found

            # Skip binary files
            if should_skip_file(os.path.basename(file_path)):
                return []

            # Check file size
            try:
                if os.path.getsize(file_path) > MAX_SEARCH_FILE_SIZE:
                    return []
            except OSError:
                return []

            files_searched += 1
            file_results = []

            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()

                rel_path = os.path.relpath(file_path, self.workspace_root)

                for i, line in enumerate(lines):
                    if regex.search(line):
                        matches_found += 1

                        if matches_found > MAX_RESULTS:
                            return file_results

                        # Get context lines
                        start = max(0, i - context_lines)
                        end = min(len(lines), i + context_lines + 1)

                        if context_lines > 0:
                            context = []
                            for j in range(start, end):
                                prefix = ">" if j == i else " "
                                context.append(f"{prefix} {j + 1}: {lines[j].rstrip()}")
                            file_results.append(f"{rel_path}:\n" + "\n".join(context))
                        else:
                            file_results.append(f"{rel_path}:{i + 1}: {line.rstrip()}")

            except (UnicodeDecodeError, IOError):
                pass

            return file_results

        try:
            if os.path.isfile(search_path):
                # Search single file
                results.extend(search_file(search_path))
            else:
                # Search directory
                for root, dirs, files in os.walk(search_path):
                    # Skip ignored directories
                    dirs[:] = [d for d in dirs if not should_skip_dir(d)]

                    for filename in files:
                        # Apply file pattern filter
                        if file_pattern and not fnmatch.fnmatch(filename, file_pattern):
                            continue

                        file_path = os.path.join(root, filename)
                        results.extend(search_file(file_path))

                        if matches_found > MAX_RESULTS:
                            break

                    if matches_found > MAX_RESULTS:
                        break

            output = "\n".join(results)
            if matches_found > MAX_RESULTS:
                output += f"\n\n[Truncated at {MAX_RESULTS} matches]"

            return ToolResult.ok(
                output=output or "(no matches)",
                match_count=min(matches_found, MAX_RESULTS),
                files_searched=files_searched,
                truncated=matches_found > MAX_RESULTS,
            )

        except Exception as e:
            return ToolResult.fail(error=f"Search error: {type(e).__name__}: {e}")


@register_tool
class FindDefinitionTool(Tool):
    """Find function, class, or variable definitions."""

    name = "find_definition"
    description = (
        "Find where a function, class, or variable is defined. "
        "Searches for common definition patterns (def, class, const, let, var, function). "
        "More targeted than grep for finding code definitions."
    )
    parameters = [
        ToolParameter(
            name="symbol",
            type="string",
            description="Name of the function, class, or variable to find",
            required=True,
        ),
        ToolParameter(
            name="path",
            type="string",
            description="Directory to search (relative to workspace). Default: workspace root",
            required=False,
            default=".",
        ),
        ToolParameter(
            name="language",
            type="string",
            description="Language hint (python, javascript, typescript, go, rust). Default: auto-detect",
            required=False,
            default=None,
            enum=["python", "javascript", "typescript", "go", "rust", None],
        ),
    ]

    requires_approval = False
    is_read_only = True

    def execute(
        self,
        symbol: str,
        path: str = ".",
        language: Optional[str] = None,
    ) -> ToolResult:
        """Find definition of a symbol."""
        if not self.workspace_root:
            return ToolResult.fail(error="Workspace root not set")

        # Build regex patterns for common definition syntaxes
        # Escape symbol for regex
        escaped = re.escape(symbol)

        patterns = []

        if language in (None, "python"):
            patterns.append((r"^[ \t]*def\s+" + escaped + r"\s*\(", "*.py"))
            patterns.append((r"^[ \t]*class\s+" + escaped + r"[\s:(]", "*.py"))
            patterns.append((r"^" + escaped + r"\s*=", "*.py"))

        if language in (None, "javascript", "typescript"):
            exts = ["*.js", "*.jsx", "*.ts", "*.tsx"] if language is None else [f"*.{language[:2]}*"]
            for ext in exts:
                patterns.append((r"^[ \t]*(export\s+)?(async\s+)?function\s+" + escaped + r"\s*[(<]", ext))
                patterns.append((r"^[ \t]*(export\s+)?class\s+" + escaped + r"[\s{<]", ext))
                patterns.append((r"^[ \t]*(export\s+)?(const|let|var)\s+" + escaped + r"\s*=", ext))
                patterns.append((r"^[ \t]*" + escaped + r"\s*[=:].*(?:function|=>)", ext))

        if language in (None, "go"):
            patterns.append((r"^func\s+(\([^)]+\)\s*)?" + escaped + r"\s*\(", "*.go"))
            patterns.append((r"^type\s+" + escaped + r"\s+(struct|interface)", "*.go"))

        if language in (None, "rust"):
            patterns.append((r"^[ \t]*(pub\s+)?fn\s+" + escaped + r"\s*[(<]", "*.rs"))
            patterns.append((r"^[ \t]*(pub\s+)?struct\s+" + escaped + r"[\s{<]", "*.rs"))
            patterns.append((r"^[ \t]*(pub\s+)?enum\s+" + escaped + r"[\s{<]", "*.rs"))

        if not patterns:
            return ToolResult.fail(error=f"Unknown language: {language}")

        # Search using grep tool logic
        try:
            search_path = validate_path_in_workspace(path, self.workspace_root)
        except ToolError as e:
            return ToolResult.fail(error=str(e))

        results = []

        for pattern_str, file_glob in patterns:
            try:
                regex = re.compile(pattern_str, re.MULTILINE)
            except re.error:
                continue

            for root, dirs, files in os.walk(search_path):
                dirs[:] = [d for d in dirs if not should_skip_dir(d)]

                for filename in files:
                    if not fnmatch.fnmatch(filename, file_glob):
                        continue

                    file_path = os.path.join(root, filename)

                    if should_skip_file(filename):
                        continue

                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()

                        for match in regex.finditer(content):
                            # Get line number
                            line_num = content[:match.start()].count("\n") + 1
                            line = content.split("\n")[line_num - 1].strip()

                            rel_path = os.path.relpath(file_path, self.workspace_root)
                            results.append(f"{rel_path}:{line_num}: {line}")

                            if len(results) >= MAX_RESULTS:
                                break

                    except (IOError, UnicodeDecodeError):
                        continue

                    if len(results) >= MAX_RESULTS:
                        break

                if len(results) >= MAX_RESULTS:
                    break

        # Deduplicate (same file:line might match multiple patterns)
        seen = set()
        unique_results = []
        for r in results:
            key = r.split(":")[0:2]  # file:line
            if tuple(key) not in seen:
                seen.add(tuple(key))
                unique_results.append(r)

        output = "\n".join(unique_results)
        if len(results) >= MAX_RESULTS:
            output += f"\n\n[Truncated at {MAX_RESULTS} results]"

        return ToolResult.ok(
            output=output or f"No definition found for '{symbol}'",
            match_count=len(unique_results),
        )
