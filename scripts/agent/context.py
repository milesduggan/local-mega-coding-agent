from dataclasses import dataclass, field
from typing import Dict, List

from scripts.agent.router import ToolMatch
from scripts.tools.registry import get_registry


@dataclass
class SessionContext:
    tool_count: int
    matched_tools: List[str]
    workspace_root: str
    model_info: str = "Qwen2.5-Coder-7B-Instruct"


def build_session_context(snapshot_text: str, routing_result: List[ToolMatch]) -> SessionContext:
    registry = get_registry()
    tool_count = len(registry.list_tool_names())
    matched_tools = [m.name for m in routing_result]
    workspace_root = registry._workspace_root or "unknown"

    return SessionContext(
        tool_count=tool_count,
        matched_tools=matched_tools,
        workspace_root=workspace_root,
    )


def context_to_prompt(ctx: SessionContext) -> str:
    if ctx.matched_tools:
        tools_str = ", ".join(ctx.matched_tools)
    else:
        tools_str = "none matched"

    return (
        f"[Session Context]\n"
        f"Available tools: {ctx.tool_count}\n"
        f"Relevant tools for this task: {tools_str}\n"
        f"Model: {ctx.model_info}\n"
        f"Workspace: {ctx.workspace_root}\n"
    )
