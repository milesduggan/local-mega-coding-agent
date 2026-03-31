"""
Parity audit tests for the tool registry.

Verifies that every tool registered in the tool registry is properly configured
with required fields and satisfies safety invariants.
"""

import os
import sys

import pytest

# Add project root to path
_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TEST_DIR)
sys.path.insert(0, _PROJECT_ROOT)

# Import tool modules to trigger @register_tool decorators
import scripts.tools.bash  # noqa: F401
import scripts.tools.file_ops  # noqa: F401
import scripts.tools.search  # noqa: F401

from scripts.tools.registry import get_registry


def get_all_tool_instances():
    """Return a list of instantiated Tool objects for all registered tools."""
    registry = get_registry()
    return [registry.get(name) for name in registry.list_tool_names()]


# =============================================================================
# Schema tests
# =============================================================================


def test_all_tools_have_schema():
    """Every registered tool must expose a non-empty schema dict with at least 'name'."""
    tools = get_all_tool_instances()
    assert len(tools) > 0, "Registry is empty — no tools registered"

    for tool in tools:
        schema = tool.get_schema()
        assert isinstance(schema, dict), (
            f"Tool {tool.name}: get_schema() must return a dict, got {type(schema)}"
        )
        assert "name" in schema, f"Tool {tool.name}: schema missing 'name' key"
        assert schema["name"], f"Tool {tool.name}: schema 'name' must be non-empty"


# =============================================================================
# Description tests
# =============================================================================


def test_all_tools_have_description():
    """Every registered tool must have a non-empty string description."""
    tools = get_all_tool_instances()
    assert len(tools) > 0, "Registry is empty — no tools registered"

    for tool in tools:
        assert isinstance(tool.description, str), (
            f"Tool {tool.name}: description must be a str, got {type(tool.description)}"
        )
        assert tool.description.strip(), (
            f"Tool {tool.name}: description must not be empty or whitespace-only"
        )


# =============================================================================
# Safety flag tests
# =============================================================================


def test_all_tools_have_is_read_only_set():
    """Every registered tool must have is_read_only explicitly set as a bool (not None)."""
    tools = get_all_tool_instances()
    assert len(tools) > 0, "Registry is empty — no tools registered"

    for tool in tools:
        assert tool.is_read_only is not None, (
            f"Tool {tool.name}: is_read_only must not be None"
        )
        assert isinstance(tool.is_read_only, bool), (
            f"Tool {tool.name}: is_read_only must be a bool, got {type(tool.is_read_only)}"
        )


def test_all_tools_have_requires_approval_set():
    """Every registered tool must have requires_approval explicitly set as a bool (not None)."""
    tools = get_all_tool_instances()
    assert len(tools) > 0, "Registry is empty — no tools registered"

    for tool in tools:
        assert tool.requires_approval is not None, (
            f"Tool {tool.name}: requires_approval must not be None"
        )
        assert isinstance(tool.requires_approval, bool), (
            f"Tool {tool.name}: requires_approval must be a bool, got {type(tool.requires_approval)}"
        )


# =============================================================================
# Safety invariant
# =============================================================================


def test_non_read_only_tools_require_approval():
    """
    Safety invariant: any tool that is NOT read-only MUST require approval.

    A tool that can write/execute but doesn't require approval is a security hole.
    """
    tools = get_all_tool_instances()
    assert len(tools) > 0, "Registry is empty — no tools registered"

    for tool in tools:
        if not tool.is_read_only:
            assert tool.requires_approval, (
                f"Tool {tool.name} is not read-only but does not require approval — "
                "this is a security violation"
            )


# =============================================================================
# Sanity checks
# =============================================================================


def test_at_least_one_read_only_tool_exists():
    """Sanity check: at least one read-only tool must exist in the registry."""
    tools = get_all_tool_instances()
    read_only_tools = [t for t in tools if t.is_read_only]
    assert len(read_only_tools) > 0, (
        "No read-only tools found in registry — registry is likely misconfigured"
    )


def test_at_least_one_approval_required_tool_exists():
    """Sanity check: at least one tool requiring approval must exist (bash should require approval)."""
    tools = get_all_tool_instances()
    approval_tools = [t for t in tools if t.requires_approval]
    assert len(approval_tools) > 0, (
        "No tools require approval — expected at least bash to require approval"
    )
