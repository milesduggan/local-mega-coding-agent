"""
Unit tests for the executor module.

Tests security features:
- Input validation (task length, file count, file size)
- Path traversal prevention in _parse_file_blocks()

Note: Tests that require actual model inference are in test_agent_real_models.py
"""
import pytest
from scripts.executor.executor import (
    _parse_file_blocks,
    ExecutionError,
    MAX_TASK_LENGTH,
    MAX_FILES,
    MAX_TOTAL_FILE_SIZE,
)


class TestInputValidation:
    """Test input validation limits in execute()."""

    def test_imports_work(self):
        """Verify executor module imports correctly."""
        from scripts.executor.executor import execute
        assert callable(execute)

    def test_constants_defined(self):
        """Verify security constants are defined with reasonable values."""
        assert MAX_TASK_LENGTH == 10_000
        assert MAX_FILES == 100
        assert MAX_TOTAL_FILE_SIZE == 50_000_000


class TestParseFileBlocks:
    """Test _parse_file_blocks() function."""

    def test_valid_single_file(self):
        """Parse a valid single file block."""
        raw = """FILE: test.py
def hello():
    print("hello")
"""
        result = _parse_file_blocks(raw, {"test.py"})
        assert "test.py" in result
        assert "def hello" in result["test.py"]
        assert 'print("hello")' in result["test.py"]

    def test_valid_multiple_files(self):
        """Parse multiple valid file blocks."""
        raw = """FILE: a.py
def a():
    pass

FILE: b.py
def b():
    pass
"""
        result = _parse_file_blocks(raw, {"a.py", "b.py"})
        assert len(result) == 2
        assert "a.py" in result
        assert "b.py" in result
        assert "def a" in result["a.py"]
        assert "def b" in result["b.py"]

    def test_rejects_unknown_file(self):
        """Reject file not in allowed set (hallucination guard)."""
        raw = "FILE: unknown.py\ncode here"
        with pytest.raises(ExecutionError, match="unknown file"):
            _parse_file_blocks(raw, {"allowed.py"})

    def test_rejects_absolute_path_unix(self):
        """Reject Unix-style absolute paths.

        Note: On Windows, PurePath("/etc/passwd").is_absolute() returns False.
        We use PurePosixPath to ensure Unix-style paths are detected as absolute
        on all platforms. But pathlib.PurePath in the executor uses the current
        OS conventions. This test verifies the behavior on the current platform.
        """
        import sys
        raw = "FILE: /etc/passwd\nmalicious content"
        if sys.platform != "win32":
            # On Unix, this should be rejected as absolute
            with pytest.raises(ExecutionError, match="Absolute paths not allowed"):
                _parse_file_blocks(raw, {"/etc/passwd"})
        else:
            # On Windows, /etc/passwd is treated as relative (no drive letter)
            # This is arguably a gap, but the hallucination guard will still
            # block it if /etc/passwd isn't in allowed_files
            with pytest.raises(ExecutionError, match="unknown file"):
                _parse_file_blocks(raw, {"allowed.py"})

    def test_rejects_absolute_path_windows(self):
        """Reject Windows-style absolute paths."""
        raw = "FILE: C:\\Windows\\System32\\config\nmalicious content"
        with pytest.raises(ExecutionError, match="Absolute paths not allowed"):
            _parse_file_blocks(raw, {"C:\\Windows\\System32\\config"})

    def test_rejects_path_traversal_simple(self):
        """Reject simple path traversal."""
        raw = "FILE: ../secret.py\nmalicious"
        with pytest.raises(ExecutionError, match="Path traversal not allowed"):
            _parse_file_blocks(raw, {"../secret.py"})

    def test_rejects_path_traversal_deep(self):
        """Reject deep path traversal."""
        raw = "FILE: ../../../etc/passwd\nmalicious"
        with pytest.raises(ExecutionError, match="Path traversal not allowed"):
            _parse_file_blocks(raw, {"../../../etc/passwd"})

    def test_rejects_path_traversal_mixed(self):
        """Reject path traversal mixed with valid components."""
        raw = "FILE: src/../../../etc/passwd\nmalicious"
        with pytest.raises(ExecutionError, match="Path traversal not allowed"):
            _parse_file_blocks(raw, {"src/../../../etc/passwd"})

    def test_allows_nested_paths(self):
        """Allow valid nested relative paths."""
        raw = "FILE: src/utils/helper.py\ndef helper(): pass"
        result = _parse_file_blocks(raw, {"src/utils/helper.py"})
        assert "src/utils/helper.py" in result

    def test_empty_output_returns_empty_dict(self):
        """Empty output returns empty dict."""
        result = _parse_file_blocks("", {"test.py"})
        assert result == {}

    def test_no_file_markers_returns_empty_dict(self):
        """Output without FILE: markers returns empty dict."""
        result = _parse_file_blocks("just some random text\nno markers", {"test.py"})
        assert result == {}

    def test_duplicate_files_takes_first(self):
        """When file appears twice, take first occurrence only."""
        raw = """FILE: test.py
first version

FILE: test.py
second version
"""
        result = _parse_file_blocks(raw, {"test.py"})
        assert "first version" in result["test.py"]
        assert "second version" not in result["test.py"]

    def test_handles_markdown_code_blocks(self):
        """Extract code from markdown code blocks."""
        raw = """FILE: test.py
```python
def hello():
    pass
```
"""
        result = _parse_file_blocks(raw, {"test.py"})
        assert "def hello" in result["test.py"]
        # Should not contain markdown artifacts
        assert "```" not in result["test.py"]


class TestExecuteValidation:
    """Test execute() input validation.

    Note: These tests use mocking to avoid requiring actual models.
    For full integration tests, see test_agent_real_models.py.
    """

    def test_empty_task_raises(self):
        """Empty task string should raise ExecutionError."""
        from scripts.executor.executor import execute
        with pytest.raises(ExecutionError, match="empty"):
            execute("", {"file.py": "code"})

    def test_whitespace_task_raises(self):
        """Whitespace-only task should raise ExecutionError."""
        from scripts.executor.executor import execute
        with pytest.raises(ExecutionError, match="empty"):
            execute("   \n\t  ", {"file.py": "code"})

    def test_empty_files_raises(self):
        """Empty files dict should raise ExecutionError."""
        from scripts.executor.executor import execute
        with pytest.raises(ExecutionError, match="No files"):
            execute("do something", {})

    def test_task_too_long_raises(self):
        """Task exceeding MAX_TASK_LENGTH should raise ExecutionError."""
        from scripts.executor.executor import execute
        long_task = "x" * (MAX_TASK_LENGTH + 1)
        with pytest.raises(ExecutionError, match="too long"):
            execute(long_task, {"file.py": "code"})

    def test_too_many_files_raises(self):
        """More than MAX_FILES should raise ExecutionError."""
        from scripts.executor.executor import execute
        many_files = {f"file{i}.py": "code" for i in range(MAX_FILES + 1)}
        with pytest.raises(ExecutionError, match="Too many files"):
            execute("task", many_files)

    def test_total_size_too_large_raises(self):
        """Total file size exceeding MAX_TOTAL_FILE_SIZE should raise."""
        from scripts.executor.executor import execute
        # Create a file just over the limit
        large_content = "x" * (MAX_TOTAL_FILE_SIZE + 1)
        with pytest.raises(ExecutionError, match="too large"):
            execute("task", {"large.py": large_content})


class TestGenerateUnifiedDiff:
    """Test _generate_unified_diff() function."""

    def test_generates_valid_diff(self):
        """Generate valid unified diff for simple change."""
        from scripts.executor.executor import _generate_unified_diff

        original = "def foo():\n    pass\n"
        modified = "def foo():\n    return 42\n"

        diff = _generate_unified_diff("test.py", original, modified)

        assert "--- test.py" in diff
        assert "+++ test.py" in diff
        assert "-    pass" in diff
        assert "+    return 42" in diff

    def test_no_changes_returns_empty(self):
        """Identical files produce empty diff."""
        from scripts.executor.executor import _generate_unified_diff

        content = "def foo():\n    pass\n"
        diff = _generate_unified_diff("test.py", content, content)

        assert diff == ""


class TestSynthesizeDiffs:
    """Test _synthesize_diffs() function."""

    def test_synthesizes_multiple_diffs(self):
        """Synthesize diffs for multiple changed files."""
        from scripts.executor.executor import _synthesize_diffs

        original = {
            "a.py": "def a(): pass\n",
            "b.py": "def b(): pass\n",
        }
        updated = {
            "a.py": "def a(): return 1\n",
            "b.py": "def b(): return 2\n",
        }

        diff = _synthesize_diffs(original, updated)

        assert "--- a.py" in diff
        assert "--- b.py" in diff
        assert "+def a(): return 1" in diff
        assert "+def b(): return 2" in diff

    def test_skips_unchanged_files(self):
        """Don't include unchanged files in diff."""
        from scripts.executor.executor import _synthesize_diffs

        original = {
            "changed.py": "def a(): pass\n",
            "unchanged.py": "def b(): pass\n",
        }
        updated = {
            "changed.py": "def a(): return 1\n",
            "unchanged.py": "def b(): pass\n",  # Same as original
        }

        diff = _synthesize_diffs(original, updated)

        assert "changed.py" in diff
        assert "unchanged.py" not in diff
