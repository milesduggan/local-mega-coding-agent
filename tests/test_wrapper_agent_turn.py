# tests/test_wrapper_agent_turn.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch, MagicMock
from scripts.agent.turn_runner import TurnResult, STOP_DONE


def _make_turn_result(**kwargs):
    defaults = dict(
        stop_reason=STOP_DONE,
        mode="execute",
        transcript=[],
        context_summary="summary text",
        pending_tool=None,
        error=None,
    )
    defaults.update(kwargs)
    return TurnResult(**defaults)


def _handle_message_dispatch(msg: dict) -> dict:
    """
    Helper that calls handle_message and captures what was sent to stdout
    by intercepting send_response.
    """
    import json
    import io
    from unittest.mock import patch as _patch

    captured = {}

    def fake_send_response(id_, result=None, error=None):
        captured["id"] = id_
        captured["result"] = result
        captured["error"] = error

    import scripts.backend.wrapper as wrapper
    original_send = wrapper.send_response
    wrapper.send_response = fake_send_response
    try:
        wrapper.handle_message(msg)
    finally:
        wrapper.send_response = original_send

    return captured


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHandleAgentTurnRouting:
    """Test that handle_message routes 'agent_turn' correctly."""

    def test_agent_turn_returns_expected_keys(self):
        """handle_message with method='agent_turn' should return a dict with correct shape."""
        mock_result = _make_turn_result()

        with patch("scripts.backend.wrapper.TurnRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.run.return_value = mock_result

            response = _handle_message_dispatch({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "agent_turn",
                "params": {
                    "user_input": "Add a hello world function",
                    "files": {"main.py": "# empty"},
                },
            })

        assert response["error"] is None, f"Unexpected error: {response['error']}"
        result = response["result"]
        assert isinstance(result, dict)
        for key in ("stop_reason", "mode", "transcript", "context_summary", "pending_tool", "error"):
            assert key in result, f"Missing key: {key}"

    def test_agent_turn_stop_reason_and_mode(self):
        """Result dict values should reflect TurnResult fields."""
        mock_result = _make_turn_result(
            stop_reason=STOP_DONE,
            mode="execute",
            transcript=[{"role": "user", "content": "hi"}],
            context_summary="some summary",
        )

        with patch("scripts.backend.wrapper.TurnRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.run.return_value = mock_result

            response = _handle_message_dispatch({
                "jsonrpc": "2.0",
                "id": 2,
                "method": "agent_turn",
                "params": {
                    "user_input": "task",
                    "files": {},
                },
            })

        result = response["result"]
        assert result["stop_reason"] == STOP_DONE
        assert result["mode"] == "execute"
        assert result["transcript"] == [{"role": "user", "content": "hi"}]
        assert result["context_summary"] == "some summary"
        assert result["pending_tool"] is None
        assert result["error"] is None

    def test_agent_turn_uses_chat_for_turn_as_model_call(self):
        """TurnRunner should be constructed with chat_for_turn as model_call."""
        mock_result = _make_turn_result()

        with patch("scripts.backend.wrapper.TurnRunner") as MockRunner, \
             patch("scripts.backend.wrapper.chat_for_turn") as mock_chat_for_turn:
            instance = MockRunner.return_value
            instance.run.return_value = mock_result

            _handle_message_dispatch({
                "jsonrpc": "2.0",
                "id": 3,
                "method": "agent_turn",
                "params": {"user_input": "task", "files": {}},
            })

            MockRunner.assert_called_once_with(model_call=mock_chat_for_turn)

    def test_agent_turn_resume_path(self):
        """When resume=True, runner.resume() should be called instead of runner.run()."""
        mock_result = _make_turn_result(mode="rejected")

        with patch("scripts.backend.wrapper.TurnRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.resume.return_value = mock_result

            response = _handle_message_dispatch({
                "jsonrpc": "2.0",
                "id": 4,
                "method": "agent_turn",
                "params": {
                    "user_input": "",
                    "files": {},
                    "resume": True,
                    "tool_name": "bash",
                    "tool_params": {"command": "ls"},
                    "approved": False,
                },
            })

        instance.resume.assert_called_once_with("bash", {"command": "ls"}, False)
        instance.run.assert_not_called()
        assert response["result"]["mode"] == "rejected"

    def test_agent_turn_chat_for_turn_mock_returns_ready(self):
        """Integration-style: mock chat_for_turn to return READY_TO_IMPLEMENT."""
        from scripts.agent.turn_runner import TurnRunner as RealTurnRunner

        def fake_chat(messages):
            return "READY_TO_IMPLEMENT"

        with patch("scripts.backend.wrapper.chat_for_turn", side_effect=fake_chat), \
             patch("scripts.backend.wrapper.TurnRunner", wraps=RealTurnRunner):

            response = _handle_message_dispatch({
                "jsonrpc": "2.0",
                "id": 5,
                "method": "agent_turn",
                "params": {
                    "user_input": "Write a hello world function",
                    "files": {"hello.py": ""},
                },
            })

        assert response["error"] is None
        result = response["result"]
        assert result["stop_reason"] == STOP_DONE
        assert result["mode"] == "execute"


class TestUnknownMethodStillErrors:
    """Confirm that unknown methods still return an error (routing not broken)."""

    def test_unknown_method_returns_error(self):
        response = _handle_message_dispatch({
            "jsonrpc": "2.0",
            "id": 99,
            "method": "nonexistent_method_xyz",
            "params": {},
        })
        assert response["result"] is None
        assert response["error"] is not None
        assert "Unknown method" in response["error"]
