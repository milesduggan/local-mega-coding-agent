"""
JSON-RPC wrapper for VSCode extension communication.

This module provides a stdin/stdout interface for the VSCode extension
to communicate with the critic and executor components.

Protocol: JSON-RPC 2.0 over stdin/stdout (one JSON object per line)
"""

import json
import sys
from typing import Any

# Add parent directory to path for imports
sys.path.insert(0, str(__file__).rsplit("scripts", 1)[0])

from scripts.critic.critic import chat, review, normalize_task, History
from scripts.executor.executor import execute


def send_response(id: int | None, result: Any = None, error: str | None = None) -> None:
    """Send a JSON-RPC response to stdout."""
    response = {
        "jsonrpc": "2.0",
        "id": id,
        "result": result,
        "error": error,
    }
    print(json.dumps(response), flush=True)


def send_error(id: int | None, message: str) -> None:
    """Send an error response."""
    send_response(id, result=None, error=message)


def handle_chat(params: dict) -> str:
    """Handle a chat request."""
    message = params.get("message", "")
    history = params.get("history", [])

    if not message:
        raise ValueError("Missing 'message' parameter")

    # Convert history to proper format if needed
    formatted_history: History = []
    for msg in history:
        if isinstance(msg, dict) and "role" in msg and "content" in msg:
            formatted_history.append({"role": msg["role"], "content": msg["content"]})

    return chat(message, formatted_history)


def handle_execute(params: dict) -> str:
    """Handle an execute request."""
    task = params.get("task", "")
    files = params.get("files", {})

    if not task:
        raise ValueError("Missing 'task' parameter")
    if not files:
        raise ValueError("Missing 'files' parameter")

    return execute(task, files)


def handle_review(params: dict) -> str:
    """Handle a review request."""
    task = params.get("task", "")
    diff = params.get("diff", "")

    if not task:
        raise ValueError("Missing 'task' parameter")
    if not diff:
        raise ValueError("Missing 'diff' parameter")

    return review(task, diff)


def handle_normalize_task(params: dict) -> str:
    """Generate a condensed task specification from conversation history."""
    history = params.get("history", [])

    if not history:
        raise ValueError("No conversation history to normalize")

    # Convert history to proper format
    formatted_history: History = []
    for msg in history:
        if isinstance(msg, dict) and "role" in msg and "content" in msg:
            formatted_history.append({"role": msg["role"], "content": msg["content"]})

    return normalize_task(formatted_history)


def handle_message(msg: dict) -> None:
    """Route a JSON-RPC message to the appropriate handler."""
    msg_id = msg.get("id")
    method = msg.get("method", "")
    params = msg.get("params", {})

    try:
        if method == "chat":
            result = handle_chat(params)
            send_response(msg_id, result=result)

        elif method == "execute":
            result = handle_execute(params)
            send_response(msg_id, result=result)

        elif method == "review":
            result = handle_review(params)
            send_response(msg_id, result=result)

        elif method == "normalize_task":
            result = handle_normalize_task(params)
            send_response(msg_id, result=result)

        elif method == "ping":
            # Health check
            send_response(msg_id, result="pong")

        else:
            send_error(msg_id, f"Unknown method: {method}")

    except Exception as e:
        send_error(msg_id, str(e))


def main() -> None:
    """Main loop: read JSON-RPC messages from stdin, process, respond on stdout."""
    # Signal ready
    send_response(None, result="ready")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError as e:
            send_error(None, f"Invalid JSON: {e}")
            continue

        # Validate JSON-RPC format
        if not isinstance(msg, dict):
            send_error(None, "Message must be a JSON object")
            continue

        if msg.get("jsonrpc") != "2.0":
            send_error(msg.get("id"), "Invalid JSON-RPC version (expected 2.0)")
            continue

        handle_message(msg)


if __name__ == "__main__":
    main()
