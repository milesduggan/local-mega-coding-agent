"""
Tool registry for managing available tools.

The registry is a singleton that holds all registered tools and provides
methods to execute them by name.
"""

import logging
from typing import Any, Dict, List, Optional, Type

from scripts.tools.base import Tool, ToolResult, ToolError

log = logging.getLogger(__name__)


class ToolRegistry:
    """
    Singleton registry for all available tools.

    Usage:
        registry = get_registry()
        registry.register(BashTool)
        result = registry.execute("bash", command="ls -la")
    """

    _instance: Optional["ToolRegistry"] = None

    def __new__(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._tools: Dict[str, Type[Tool]] = {}
        self._workspace_root: Optional[str] = None
        self._initialized = True

    def set_workspace_root(self, path: str) -> None:
        """Set the workspace root for all tools."""
        self._workspace_root = path
        log.debug(f"Tool registry workspace root set to: {path}")

    def register(self, tool_class: Type[Tool]) -> None:
        """
        Register a tool class.

        Args:
            tool_class: A Tool subclass to register
        """
        # Instantiate temporarily to get the name
        temp = tool_class()
        name = temp.name

        if name in self._tools:
            log.warning(f"Overwriting existing tool: {name}")

        self._tools[name] = tool_class
        log.debug(f"Registered tool: {name}")

    def unregister(self, name: str) -> bool:
        """
        Unregister a tool by name.

        Returns:
            True if tool was unregistered, False if not found
        """
        if name in self._tools:
            del self._tools[name]
            log.debug(f"Unregistered tool: {name}")
            return True
        return False

    def get(self, name: str) -> Optional[Tool]:
        """
        Get an instantiated tool by name.

        Returns:
            Tool instance or None if not found
        """
        tool_class = self._tools.get(name)
        if tool_class is None:
            return None
        return tool_class(workspace_root=self._workspace_root)

    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def list_tools(self) -> List[Dict[str, Any]]:
        """
        List all registered tools with their schemas.

        Returns:
            List of tool schemas suitable for LLM prompts
        """
        result = []
        for tool_class in self._tools.values():
            tool = tool_class(workspace_root=self._workspace_root)
            result.append(tool.get_schema())
        return result

    def list_tool_names(self) -> List[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def execute(self, name: str, params: Dict[str, Any]) -> ToolResult:
        """
        Execute a tool by name with given parameters.

        Args:
            name: Tool name
            params: Parameters to pass to the tool

        Returns:
            ToolResult with execution outcome
        """
        tool = self.get(name)
        if tool is None:
            return ToolResult.fail(
                error=f"Unknown tool: {name}. Available: {self.list_tool_names()}"
            )

        try:
            # Validate parameters
            validated_params = tool.validate_params(params)

            # Execute
            log.info(f"Executing tool: {name} with params: {validated_params}")
            result = tool.execute(**validated_params)
            log.info(f"Tool {name} completed: success={result.success}")

            return result

        except ToolError as e:
            log.warning(f"Tool {name} failed: {e}")
            return ToolResult.fail(error=str(e))

        except Exception as e:
            log.error(f"Tool {name} unexpected error: {type(e).__name__}: {e}")
            return ToolResult.fail(
                error=f"Internal error in tool {name}: {type(e).__name__}: {e}"
            )

    def get_tool_for_approval(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get tool info for approval prompt.

        Returns:
            Dict with tool name, description, and requires_approval flag
        """
        tool = self.get(name)
        if tool is None:
            return None
        return {
            "name": tool.name,
            "description": tool.description,
            "requires_approval": tool.requires_approval,
            "is_read_only": tool.is_read_only,
        }


# Module-level singleton accessor
_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """Get the global tool registry singleton."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def register_tool(tool_class: Type[Tool]) -> Type[Tool]:
    """
    Decorator to register a tool class.

    Usage:
        @register_tool
        class MyTool(Tool):
            ...
    """
    get_registry().register(tool_class)
    return tool_class
