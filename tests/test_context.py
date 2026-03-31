# tests/test_context.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.agent.context import SessionContext, build_session_context, context_to_prompt
from scripts.agent.router import ToolMatch


def _make_routing():
    return [
        ToolMatch(name="search_files", score=0.8, description="Search files"),
        ToolMatch(name="read_file", score=0.5, description="Read a file"),
    ]


def test_build_session_context_sets_tool_count(monkeypatch):
    from scripts.tools.registry import ToolRegistry
    fake_registry = ToolRegistry()
    fake_registry._tools = {"a": None, "b": None, "c": None}
    monkeypatch.setattr("scripts.agent.context.get_registry", lambda: fake_registry)

    ctx = build_session_context("snapshot text", _make_routing())
    assert ctx.tool_count == 3


def test_build_session_context_sets_matched_tools(monkeypatch):
    from scripts.tools.registry import ToolRegistry
    fake_registry = ToolRegistry()
    fake_registry._tools = {}
    monkeypatch.setattr("scripts.agent.context.get_registry", lambda: fake_registry)

    ctx = build_session_context("snapshot text", _make_routing())
    assert ctx.matched_tools == ["search_files", "read_file"]


def test_build_session_context_empty_routing(monkeypatch):
    from scripts.tools.registry import ToolRegistry
    fake_registry = ToolRegistry()
    fake_registry._tools = {}
    monkeypatch.setattr("scripts.agent.context.get_registry", lambda: fake_registry)

    ctx = build_session_context("snapshot", [])
    assert ctx.matched_tools == []


def test_context_to_prompt_contains_tool_count(monkeypatch):
    from scripts.tools.registry import ToolRegistry
    fake_registry = ToolRegistry()
    fake_registry._tools = {"x": None}
    monkeypatch.setattr("scripts.agent.context.get_registry", lambda: fake_registry)

    ctx = build_session_context("", _make_routing())
    prompt = context_to_prompt(ctx)
    assert "1" in prompt
    assert "search_files" in prompt


def test_context_to_prompt_no_matches(monkeypatch):
    from scripts.tools.registry import ToolRegistry
    fake_registry = ToolRegistry()
    fake_registry._tools = {}
    monkeypatch.setattr("scripts.agent.context.get_registry", lambda: fake_registry)

    ctx = build_session_context("", [])
    prompt = context_to_prompt(ctx)
    assert "none" in prompt.lower()
