import json
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from scripts.agent.history import HistoryLog
from scripts.agent.context import build_session_context, context_to_prompt
from scripts.agent.router import Router
from scripts.tools.registry import get_registry
from scripts.config import MAX_AGENT_TURNS, TIMEOUT_EXECUTE_MS

STOP_DONE = "done"
STOP_MAX_TURNS = "max_turns_reached"
STOP_APPROVAL = "approval_required"
STOP_ERROR = "error"

_TOOL_CALL_RE = re.compile(
    r'TOOL_CALL:\s*(\w+)\s*\nPARAMS:\s*(\{[^}]*\})',
    re.DOTALL
)

# Sentinel returned by _call_model_with_timeout when the model call timed out.
_TIMEOUT_SENTINEL = None


@dataclass
class TurnResult:
    stop_reason: str
    mode: str
    transcript: List[Dict[str, str]]
    context_summary: str
    pending_tool: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class TurnRunner:
    def __init__(
        self,
        model_call: Callable[[List[Dict]], str],
        snapshot_text: str = "",
        max_turns: Optional[int] = None,
    ) -> None:
        self.model_call = model_call
        self.snapshot_text = snapshot_text
        self.max_turns = max_turns if max_turns is not None else MAX_AGENT_TURNS
        self._history = HistoryLog()
        self._router = Router()
        self._pending_tool: Optional[Dict[str, Any]] = None
        self._pending_conversation: Optional[List[Dict]] = None

    def run(self, user_input: str, files: Dict[str, str]) -> TurnResult:
        routing = self._router.score(user_input)
        ctx = build_session_context(self.snapshot_text, routing)
        conversation = self._build_messages(user_input, files, ctx)
        return self._run_loop(conversation)

    def _run_loop(self, conversation: List[Dict]) -> TurnResult:
        for _turn in range(self.max_turns):
            response, err = self._call_model_with_timeout(conversation)

            if err:
                return TurnResult(
                    stop_reason=STOP_ERROR,
                    mode="error",
                    transcript=self._history.to_list(),
                    context_summary="",
                    error=err,
                )

            # Timeout: response is None (sentinel). Log and continue to next turn.
            if response is _TIMEOUT_SENTINEL:
                self._history.add("Turn timeout", "Model call exceeded timeout; retrying")
                conversation.append({
                    "role": "user",
                    "content": "[System: model call timed out, please retry]",
                })
                continue

            response = response or ""

            if "READY_TO_IMPLEMENT" in response:
                return TurnResult(
                    stop_reason=STOP_DONE,
                    mode="execute",
                    transcript=self._history.to_list(),
                    context_summary=self._summarize(conversation),
                )

            tool_calls = _TOOL_CALL_RE.findall(response)

            if not tool_calls:
                return TurnResult(
                    stop_reason=STOP_DONE,
                    mode="clarify",
                    transcript=self._history.to_list(),
                    context_summary=response,
                )

            for tool_name, params_str in tool_calls:
                try:
                    params = json.loads(params_str)
                except json.JSONDecodeError:
                    params = {}

                registry = get_registry()
                tool = registry.get(tool_name)

                if tool is None:
                    self._history.add(
                        f"Unknown tool: {tool_name}",
                        f"Available: {registry.list_tool_names()}"
                    )
                    conversation.append({
                        "role": "user",
                        "content": f"Tool '{tool_name}' not found. "
                                   f"Available: {registry.list_tool_names()}",
                    })
                    continue

                if tool.requires_approval:
                    self._history.add(f"Approval required: {tool_name}", str(params))
                    self._pending_tool = {"name": tool_name, "params": params}
                    self._pending_conversation = conversation
                    return TurnResult(
                        stop_reason=STOP_APPROVAL,
                        mode="approval_required",
                        transcript=self._history.to_list(),
                        context_summary="",
                        pending_tool={"name": tool_name, "params": params},
                    )

                result = registry.execute(tool_name, params)
                detail = (result.output or result.error or "")[:200]

                if not result.success:
                    self._history.add(f"Tool failed: {tool_name}", result.error or detail)
                else:
                    self._history.add(f"Used {tool_name}", detail)

                conversation.append({
                    "role": "user",
                    "content": f"Tool result ({tool_name}):\n{result.output or result.error}",
                })

        return TurnResult(
            stop_reason=STOP_MAX_TURNS,
            mode="max_turns_reached",
            transcript=self._history.to_list(),
            context_summary=self._summarize(conversation),
        )

    def resume(
        self,
        tool_name: str,
        tool_params: Dict[str, Any],
        approved: bool,
    ) -> TurnResult:
        """
        Resume the loop after a tool-approval pause.

        If approved=False, log rejection and return stop_reason='done'.
        If approved=True, execute the tool; on error return stop_reason='error';
        on success continue the loop from where it paused.
        """
        conversation = self._pending_conversation or []

        if not approved:
            self._history.add(f"Tool rejected: {tool_name}", str(tool_params))
            self._pending_tool = None
            self._pending_conversation = None
            return TurnResult(
                stop_reason=STOP_DONE,
                mode="rejected",
                transcript=self._history.to_list(),
                context_summary="",
            )

        registry = get_registry()
        result = registry.execute(tool_name, tool_params)

        if not result.success:
            error_msg = result.error or "Tool execution failed"
            self._history.add(f"Tool failed: {tool_name}", error_msg)
            self._pending_tool = None
            self._pending_conversation = None
            return TurnResult(
                stop_reason=STOP_ERROR,
                mode="error",
                transcript=self._history.to_list(),
                context_summary="",
                error=error_msg,
            )

        detail = (result.output or "")[:200]
        self._history.add(f"Used {tool_name}", detail)
        conversation.append({
            "role": "user",
            "content": f"Tool result ({tool_name}):\n{result.output}",
        })

        self._pending_tool = None
        self._pending_conversation = None
        return self._run_loop(conversation)

    def _call_model_with_timeout(self, conversation: List[Dict]) -> tuple:
        result_holder: List[Optional[str]] = [None]
        error_holder: List[Optional[str]] = [None]
        # Use a distinct marker so we can distinguish "timed out" from
        # "model returned None/empty string".
        _not_set = object()
        result_holder = [_not_set]

        def call() -> None:
            try:
                result_holder[0] = self.model_call(conversation)
            except Exception as exc:
                error_holder[0] = f"{type(exc).__name__}: {exc}"

        thread = threading.Thread(target=call, daemon=True)
        thread.start()
        timeout_s = TIMEOUT_EXECUTE_MS / 1000
        thread.join(timeout=timeout_s)

        if thread.is_alive():
            # Return the sentinel (None) to signal a timeout to the caller.
            return _TIMEOUT_SENTINEL, None

        if error_holder[0] is not None:
            return None, error_holder[0]

        value = result_holder[0]
        if value is _not_set:
            # Thread finished but set neither result nor error — treat as empty.
            return "", None
        return value, None

    def _build_messages(
        self,
        user_input: str,
        files: Dict[str, str],
        ctx: Any,
    ) -> List[Dict[str, str]]:
        context_header = context_to_prompt(ctx)

        files_section = ""
        for name, content in files.items():
            files_section += f"FILE: {name}\n{content[:2000]}\n\n"

        system = (
            "You are a coding agent. Gather context using tools before implementing.\n\n"
            "To call a tool, output EXACTLY:\n"
            "TOOL_CALL: <tool_name>\n"
            'PARAMS: {"key": "value"}\n\n'
            "When you have enough context, output:\n"
            "READY_TO_IMPLEMENT\n\n"
            f"{context_header}"
        )

        user_content = f"TASK: {user_input}"
        if files_section:
            user_content += f"\n\nFILES:\n{files_section}"

        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]

    def _summarize(self, conversation: List[Dict]) -> str:
        non_system = [m for m in conversation if m.get("role") != "system"]
        return "\n".join(m["content"][:300] for m in non_system[-4:])
