"""
Base classes for the tool system.

Tools are actions that the LLM can request to execute. Each tool has:
- A name (used in tool calls)
- A description (shown to LLM)
- A schema (JSON schema for parameters)
- An execute method (performs the action)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class ToolError(Exception):
    """Raised when a tool execution fails."""

    def __init__(self, message: str, tool_name: str = "", recoverable: bool = True):
        super().__init__(message)
        self.tool_name = tool_name
        self.recoverable = recoverable


@dataclass
class ToolResult:
    """Result of a tool execution."""

    success: bool
    output: str
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "metadata": self.metadata,
        }

    @classmethod
    def ok(cls, output: str, **metadata: Any) -> "ToolResult":
        """Create a successful result."""
        return cls(success=True, output=output, metadata=metadata)

    @classmethod
    def fail(cls, error: str, output: str = "", **metadata: Any) -> "ToolResult":
        """Create a failed result."""
        return cls(success=False, output=output, error=error, metadata=metadata)


@dataclass
class ToolParameter:
    """Definition of a tool parameter."""

    name: str
    type: str  # "string", "integer", "boolean", "array", "object"
    description: str
    required: bool = True
    default: Any = None
    enum: Optional[List[Any]] = None


class Tool(ABC):
    """
    Abstract base class for all tools.

    Subclasses must implement:
    - name: Tool identifier used in tool calls
    - description: Human-readable description for the LLM
    - parameters: List of ToolParameter definitions
    - execute(**params): The actual tool logic
    """

    name: str
    description: str
    parameters: List[ToolParameter] = []

    # Safety flags
    requires_approval: bool = False  # If True, requires user approval before execution
    is_read_only: bool = True  # If True, does not modify state

    def __init__(self, workspace_root: Optional[str] = None):
        """
        Initialize the tool.

        Args:
            workspace_root: Root directory for workspace-scoped operations.
                           If None, some tools may refuse to operate.
        """
        self.workspace_root = workspace_root

    @abstractmethod
    def execute(self, **params: Any) -> ToolResult:
        """
        Execute the tool with the given parameters.

        Args:
            **params: Tool-specific parameters

        Returns:
            ToolResult with success status and output

        Raises:
            ToolError: If execution fails in a way that should be reported to the LLM
        """
        pass

    def get_schema(self) -> Dict[str, Any]:
        """
        Get JSON schema for tool parameters.

        Returns a schema compatible with function calling conventions.
        """
        properties = {}
        required = []

        for param in self.parameters:
            prop: Dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default

            properties[param.name] = prop

            if param.required:
                required.append(param.name)

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and normalize parameters.

        Args:
            params: Raw parameters from tool call

        Returns:
            Validated parameters with defaults applied

        Raises:
            ToolError: If required parameters are missing or invalid
        """
        validated = {}
        param_defs = {p.name: p for p in self.parameters}

        # Check for required parameters
        for param in self.parameters:
            if param.required and param.name not in params:
                raise ToolError(
                    f"Missing required parameter: {param.name}",
                    tool_name=self.name,
                )

        # Validate and apply defaults
        for param in self.parameters:
            if param.name in params:
                value = params[param.name]
                # Type checking could be added here
                if param.enum and value not in param.enum:
                    raise ToolError(
                        f"Invalid value for {param.name}: {value}. "
                        f"Must be one of: {param.enum}",
                        tool_name=self.name,
                    )
                validated[param.name] = value
            elif param.default is not None:
                validated[param.name] = param.default

        return validated

    def __repr__(self) -> str:
        return f"<Tool {self.name}>"
