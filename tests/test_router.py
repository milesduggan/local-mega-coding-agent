# tests/test_router.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.agent.router import Router, ToolMatch
from scripts.tools.registry import ToolRegistry
from scripts.tools.base import Tool, ToolResult, ToolParameter


class FakeTool(Tool):
    name = "search_files"
    description = "Search files with glob pattern"
    parameters = []
    is_read_only = True
    requires_approval = False

    def execute(self, **params) -> ToolResult:
        return ToolResult.ok("ok")


class FakeBashTool(Tool):
    name = "bash"
    description = "Run a bash shell command"
    parameters = []
    is_read_only = False
    requires_approval = True

    def execute(self, **params) -> ToolResult:
        return ToolResult.ok("ok")


def _make_registry():
    r = ToolRegistry()
    r._tools = {}  # Reset singleton for test isolation
    r.register(FakeTool)
    r.register(FakeBashTool)
    return r


def test_scores_relevant_tool_higher(monkeypatch):
    router = Router()
    registry = _make_registry()
    monkeypatch.setattr("scripts.agent.router.get_registry", lambda: registry)

    matches = router.score("search for login files")
    names = [m.name for m in matches]
    assert "search_files" in names
    assert matches[0].name == "search_files"


def test_returns_empty_on_no_match(monkeypatch):
    router = Router()
    registry = _make_registry()
    monkeypatch.setattr("scripts.agent.router.get_registry", lambda: registry)

    matches = router.score("xyzzy frobnotz quux")
    assert matches == []


def test_returns_empty_on_empty_input(monkeypatch):
    router = Router()
    registry = _make_registry()
    monkeypatch.setattr("scripts.agent.router.get_registry", lambda: registry)

    assert router.score("") == []
    assert router.score("   ") == []


def test_returns_empty_on_none_input(monkeypatch):
    router = Router()
    registry = _make_registry()
    monkeypatch.setattr("scripts.agent.router.get_registry", lambda: registry)

    assert router.score(None) == []


def test_match_has_required_fields(monkeypatch):
    router = Router()
    registry = _make_registry()
    monkeypatch.setattr("scripts.agent.router.get_registry", lambda: registry)

    matches = router.score("run a bash command")
    assert len(matches) > 0
    m = matches[0]
    assert isinstance(m, ToolMatch)
    assert m.name
    assert isinstance(m.score, float)
    assert 0.0 < m.score <= 1.0
    assert m.description
