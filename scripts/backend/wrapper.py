"""
JSON-RPC wrapper for VSCode extension communication.

This module provides a stdin/stdout interface for the VSCode extension
to communicate with the critic and executor components.

Protocol: JSON-RPC 2.0 over stdin/stdout (one JSON object per line)
"""

import ast
import json
import logging
import os
import sys
import traceback
from typing import Any

# Configure logging to stderr (stdout is reserved for JSON-RPC)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger(__name__)

# Add project root to path for imports
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_MODULE_DIR))
sys.path.insert(0, _PROJECT_ROOT)

from scripts.critic.critic import chat, review_diff, normalize_task, History
from scripts.critic.critic import warm_up as warm_up_critic
from scripts.critic.critic import unload as unload_critic
from scripts.executor.executor import execute
from scripts.executor.executor import warm_up as warm_up_executor
from scripts.executor.executor import unload as unload_executor
from scripts.backend.model_manager import get_manager


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

    return review_diff(task, diff)


def handle_normalize_task(params: dict) -> str:
    """Generate a normalized execution brief from conversation history."""
    history = params.get("history", [])
    selected_files = params.get("files", [])

    if not history:
        raise ValueError("No conversation history to normalize")

    # Convert history to proper format
    formatted_history: History = []
    for msg in history:
        if isinstance(msg, dict) and "role" in msg and "content" in msg:
            formatted_history.append({"role": msg["role"], "content": msg["content"]})

    # Convert files dict keys to list if dict provided
    if isinstance(selected_files, dict):
        selected_files = list(selected_files.keys())

    return normalize_task(formatted_history, selected_files)


def handle_warm_up(params: dict) -> dict:
    """
    Pre-load models into memory to eliminate first-request latency.
    Can specify which models to load: 'critic', 'executor', or 'all' (default).
    """
    models = params.get("models", "all")

    results = {}

    if models in ("all", "critic"):
        log.info("Warming up critic model (LLaMA)...")
        results["critic"] = warm_up_critic()
        log.info(f"Critic warm-up: {'success' if results['critic'] else 'failed'}")

    if models in ("all", "executor"):
        log.info("Warming up executor model (DeepSeek)...")
        results["executor"] = warm_up_executor()
        log.info(f"Executor warm-up: {'success' if results['executor'] else 'failed'}")

    return results


def handle_validate(params: dict) -> dict:
    """
    Validate file content syntax before writing to disk.
    Defense-in-depth: catches any syntax errors that escaped earlier validation.

    Params:
        files: dict[str, str] - filename -> content mapping

    Returns:
        {
            "valid": bool,
            "errors": dict[str, str]  # filename -> error message (only for failures)
        }
    """
    files = params.get("files", {})
    errors = {}

    for filename, content in files.items():
        if filename.endswith('.py'):
            try:
                ast.parse(content)
            except SyntaxError as e:
                errors[filename] = f"Line {e.lineno}: {e.msg}"

    return {"valid": len(errors) == 0, "errors": errors}


def handle_unload(params: dict) -> dict:
    """
    Unload models to free memory.

    Params:
        models: "all" | "critic" | "executor" (default: "all")

    Returns:
        {"critic": bool, "executor": bool} - True if model was unloaded
    """
    models = params.get("models", "all")
    results = {}

    if models in ("all", "critic"):
        results["critic"] = unload_critic()
        log.info(f"Critic unload: {'success' if results['critic'] else 'not loaded'}")

    if models in ("all", "executor"):
        results["executor"] = unload_executor()
        log.info(f"Executor unload: {'success' if results['executor'] else 'not loaded'}")

    return results


def handle_model_status(params: dict) -> dict:
    """
    Get status of loaded models.

    Returns:
        {
            "critic": {"loaded": bool, "idle_seconds": int|null, ...},
            "executor": {"loaded": bool, "idle_seconds": int|null, ...},
            "config": {"idle_timeout_minutes": int, "auto_unload_enabled": bool}
        }
    """
    manager = get_manager()
    return manager.get_status()


def handle_message(msg: dict) -> None:
    """Route a JSON-RPC message to the appropriate handler."""
    msg_id = msg.get("id")
    method = msg.get("method", "")
    params = msg.get("params", {})

    log.info(f"Handling method: {method} (id={msg_id})")

    try:
        if method == "chat":
            result = handle_chat(params)
            send_response(msg_id, result=result)

        elif method == "execute":
            log.info(f"Executing task on {len(params.get('files', {}))} file(s)")
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

        elif method == "warm_up":
            result = handle_warm_up(params)
            send_response(msg_id, result=result)

        elif method == "validate":
            result = handle_validate(params)
            send_response(msg_id, result=result)

        elif method == "unload":
            result = handle_unload(params)
            send_response(msg_id, result=result)

        elif method == "model_status":
            result = handle_model_status(params)
            send_response(msg_id, result=result)

        else:
            log.warning(f"Unknown method: {method}")
            send_error(msg_id, f"Unknown method: {method}")

    except Exception as e:
        log.error(f"Error in {method}: {e}\n{traceback.format_exc()}")
        send_error(msg_id, str(e))


def main() -> None:
    """Main loop: read JSON-RPC messages from stdin, process, respond on stdout."""
    log.info("Backend starting...")

    # Signal ready
    send_response(None, result="ready")
    log.info("Backend ready, waiting for requests")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError as e:
            log.error(f"Invalid JSON received: {e}")
            send_error(None, f"Invalid JSON: {e}")
            continue

        # Validate JSON-RPC format
        if not isinstance(msg, dict):
            send_error(None, "Message must be a JSON object")
            continue

        if msg.get("jsonrpc") != "2.0":
            send_error(msg.get("id"), "Invalid JSON-RPC version (expected 2.0)")
            continue

        # Wrap handle_message to catch any unexpected crashes
        try:
            handle_message(msg)
        except Exception as e:
            # This should never happen (handle_message has its own try/except)
            # but if it does, we don't want to crash the backend
            log.critical(f"Unhandled exception in message handler: {e}\n{traceback.format_exc()}")
            send_error(msg.get("id"), f"Internal error: {e}")

    log.info("Backend shutting down (stdin closed)")


if __name__ == "__main__":
    main()
