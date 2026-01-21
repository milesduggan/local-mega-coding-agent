"""
Tools package for the AI agent.

Provides a pluggable tool system that allows the LLM to execute actions
like running commands, reading/writing files, and searching the codebase.
"""

from scripts.tools.base import Tool, ToolResult, ToolError
from scripts.tools.registry import ToolRegistry, get_registry

__all__ = [
    "Tool",
    "ToolResult",
    "ToolError",
    "ToolRegistry",
    "get_registry",
]
