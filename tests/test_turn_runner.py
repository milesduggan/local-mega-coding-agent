# tests/test_turn_runner.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time

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


class FakeBashToolFails(Tool):
    """Bash-like tool that requires approval but always errors on execute."""
    name = "bash"
    description = "Run bash command"
    parameters = [ToolParameter(name="command", type="string", description="Command")]
    is_read_only = False
    requires_approval = True

    def execute(self, **params) -> ToolResult:
        return ToolResult.fail(error="Error: permission denied")


def _make_registry():
    r = ToolRegistry()
    r._tools = {}
    r.register(FakeReadTool)
    r.register(FakeBashTool)
    return r


def _make_registry_with_failing_bash():
    r = ToolRegistry()
    r._tools = {}
    r.register(FakeReadTool)
    r.register(FakeBashToolFails)
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


def test_timeout_continues_loop(monkeypatch):
    """
    When the model call exceeds the per-turn timeout the loop must NOT exit
    immediately with stop_reason='clarify'. Instead it should log a timeout
    event, append a retry note to the conversation, and continue to the next
    turn. The run ultimately ends with max_turns_reached (not 'clarify').
    """
    # Patch the timeout to 10 ms so the sleep below reliably exceeds it.
    monkeypatch.setattr("scripts.agent.turn_runner.TIMEOUT_EXECUTE_MS", 10)

    call_count = {"n": 0}

    def slow_model(_messages):
        call_count["n"] += 1
        # Sleep long enough to exceed the 10 ms timeout on every call.
        time.sleep(0.5)
        return "READY_TO_IMPLEMENT"

    monkeypatch.setattr("scripts.agent.turn_runner.get_registry", lambda: _make_registry())

    # max_turns=3 so the loop terminates even if every call times out.
    runner = TurnRunner(model_call=slow_model, max_turns=3)
    result = runner.run("do work", {})

    # Must NOT be 'clarify' — that would mean the loop exited on the first turn.
    assert result.stop_reason != STOP_DONE or result.mode != "clarify", (
        "Loop exited with clarify immediately, meaning timeout did not continue"
    )
    # The final stop reason should be max_turns_reached (all turns timed out).
    assert result.stop_reason == STOP_MAX_TURNS

    # At least one timeout event must appear in the transcript.
    timeout_events = [e for e in result.transcript if "timeout" in e["title"].lower()]
    assert len(timeout_events) > 0, "Expected at least one timeout event in transcript"


def test_read_only_tool_failure_logged_distinctly(monkeypatch):
    """
    When a read-only tool execution returns a failure result the history entry
    title must contain 'failed', not just 'Used <tool>'.
    """
    class FakeReadToolFails(Tool):
        name = "read_file"
        description = "Read a file"
        parameters = [ToolParameter(name="path", type="string", description="File path")]
        is_read_only = True
        requires_approval = False

        def execute(self, **params) -> ToolResult:
            return ToolResult.fail(error="Error: file not found")

    def make_failing_registry():
        r = ToolRegistry()
        r._tools = {}
        r.register(FakeReadToolFails)
        return r

    call_count = {"n": 0}

    def model_call(messages):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return 'TOOL_CALL: read_file\nPARAMS: {"path": "missing.py"}'
        return "READY_TO_IMPLEMENT"

    monkeypatch.setattr("scripts.agent.turn_runner.get_registry", make_failing_registry)
    runner = TurnRunner(model_call=model_call)
    result = runner.run("read missing.py", {})

    # The tool failure must appear as a 'Tool failed' entry, not 'Used read_file'.
    failed_events = [e for e in result.transcript if "failed" in e["title"].lower()]
    assert len(failed_events) > 0, (
        f"Expected 'Tool failed' entry in transcript. Got: {[e['title'] for e in result.transcript]}"
    )


def test_error_on_tool_failure_after_approval(monkeypatch):
    """
    When the user approves a write/bash tool and its execution fails, the loop
    must return stop_reason='error' with a populated error message.
    """
    monkeypatch.setattr(
        "scripts.agent.turn_runner.get_registry",
        lambda: _make_registry_with_failing_bash(),
    )

    runner = TurnRunner(model_call=_model_uses_bash)

    # run() should pause and request approval.
    run_result = runner.run("run ls", {})
    assert run_result.stop_reason == STOP_APPROVAL, (
        f"Expected approval_required, got {run_result.stop_reason}"
    )
    assert run_result.pending_tool is not None

    tool_name = run_result.pending_tool["name"]
    tool_params = run_result.pending_tool["params"]

    # User approves, but the tool fails internally.
    resume_result = runner.resume(tool_name, tool_params, approved=True)

    assert resume_result.stop_reason == STOP_ERROR, (
        f"Expected stop_reason='error' after tool failure, got '{resume_result.stop_reason}'"
    )
    assert resume_result.error is not None, "Expected error message to be populated"
