"""
Agent loop — delegates to TurnRunner for multi-turn agentic execution.
"""
from scripts.agent.turn_runner import TurnRunner
from scripts.critic.critic import chat_for_turn


def agent_loop(user_input: str, files: dict) -> dict:
    """
    Run the agentic loop for a user request.

    Returns a TurnResult dict with keys:
        stop_reason, mode, transcript, context_summary, pending_tool, error
    """
    runner = TurnRunner(model_call=chat_for_turn)
    result = runner.run(user_input, files)
    return {
        "stop_reason": result.stop_reason,
        "mode": result.mode,
        "transcript": result.transcript,
        "context_summary": result.context_summary,
        "pending_tool": result.pending_tool,
        "error": result.error,
    }
