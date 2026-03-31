# tests/test_turn_runner.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.agent.turn_runner import TurnRunner, TurnResult, STOP_DONE, STOP_MAX_TURNS, STOP_APPROVAL, STOP_ERROR
from scripts.tools.registry import ToolRegistry
from scripts.tools.base import Tool, ToolResult, ToolParameter


class FakeReadTool(Tool):
    name = "read_file"
    description = "Read a file"
    parameters = [ToolParameter(name="path", type="string", description="File path")]
    is_read_only = True
    requires_approval = False

    def execute(self, **params) -> ToolResult:
        return ToolResult.ok(f"contents of {params.get('path', 'unknown')}")


class FakeBashTool(Tool):
    name = "bash"
    description = "Run bash command"
    parameters = [ToolParameter(name="command", type="string", description="Command")]
    is_read_only = False
    requires_approval = True

    def execute(self, **params) -> ToolResult:
        return ToolResult.ok("bash output")


def _make_registry():
    r = ToolRegistry()
    r._tools = {}
    r.register(FakeReadTool)
    r.register(FakeBashTool)
    return r


def _model_ready(_messages):
    return "READY_TO_IMPLEMENT"


def _model_uses_bash(_messages):
    return 'TOOL_CALL: bash\nPARAMS: {"command": "ls src/"}'


def _model_always_loops(_messages):
    return 'TOOL_CALL: read_file\nPARAMS: {"path": "file.py"}'


def _model_returns_garbage(_messages):
    return "I am confused and cannot help you today."


def _model_errors(_messages):
    raise RuntimeError("model crashed")


def test_stop_reason_done_when_ready(monkeypatch):
    monkeypatch.setattr("scripts.agent.turn_runner.get_registry", lambda: _make_registry())
    runner = TurnRunner(model_call=_model_ready)
    result = runner.run("fix the auth bug", {})
    assert result.stop_reason == STOP_DONE
    assert result.mode == "execute"


def test_stop_reason_max_turns_reached(monkeypatch):
    monkeypatch.setattr("scripts.agent.turn_runner.get_registry", lambda: _make_registry())
    runner = TurnRunner(model_call=_model_always_loops, max_turns=3)
    result = runner.run("fix everything", {})
    assert result.stop_reason == STOP_MAX_TURNS
    assert result.mode == "max_turns_reached"
    assert len(result.transcript) > 0


def test_read_only_tool_executes_without_approval(monkeypatch):
    call_count = {"n": 0}

    def model_call(messages):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return 'TOOL_CALL: read_file\nPARAMS: {"path": "main.py"}'
        return "READY_TO_IMPLEMENT"

    monkeypatch.setattr("scripts.agent.turn_runner.get_registry", lambda: _make_registry())
    runner = TurnRunner(model_call=model_call)
    result = runner.run("read main.py", {})
    assert result.stop_reason == STOP_DONE
    assert any("read_file" in e["title"].lower() for e in result.transcript)


def test_bash_tool_returns_approval_required(monkeypatch):
    monkeypatch.setattr("scripts.agent.turn_runner.get_registry", lambda: _make_registry())
    runner = TurnRunner(model_call=_model_uses_bash)
    result = runner.run("run ls", {})
    assert result.stop_reason == STOP_APPROVAL
    assert result.mode == "approval_required"
    assert result.pending_tool is not None
    assert result.pending_tool["name"] == "bash"


def test_error_stop_reason_on_model_crash(monkeypatch):
    monkeypatch.setattr("scripts.agent.turn_runner.get_registry", lambda: _make_registry())
    runner = TurnRunner(model_call=_model_errors)
    result = runner.run("anything", {})
    assert result.stop_reason == STOP_ERROR
    assert result.error is not None


def test_clarify_mode_on_unparseable_output(monkeypatch):
    monkeypatch.setattr("scripts.agent.turn_runner.get_registry", lambda: _make_registry())
    runner = TurnRunner(model_call=_model_returns_garbage)
    result = runner.run("do something", {})
    assert result.mode == "clarify"


def test_transcript_is_list_of_dicts(monkeypatch):
    monkeypatch.setattr("scripts.agent.turn_runner.get_registry", lambda: _make_registry())
    runner = TurnRunner(model_call=_model_ready)
    result = runner.run("task", {})
    assert isinstance(result.transcript, list)


def test_all_stop_reasons_reachable(monkeypatch):
    monkeypatch.setattr("scripts.agent.turn_runner.get_registry", lambda: _make_registry())

    r = TurnRunner(_model_ready)
    assert r.run("t", {}).stop_reason == STOP_DONE

    r = TurnRunner(_model_always_loops, max_turns=1)
    assert r.run("t", {}).stop_reason == STOP_MAX_TURNS

    r = TurnRunner(_model_uses_bash)
    assert r.run("t", {}).stop_reason == STOP_APPROVAL

    r = TurnRunner(_model_errors)
    assert r.run("t", {}).stop_reason == STOP_ERROR
