import logging
import os
import sys
from typing import List, Dict, Optional
from llama_cpp import Llama

# Add parent directory to path for imports
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_MODULE_DIR))
sys.path.insert(0, _PROJECT_ROOT)

from scripts.memory.context_manager import ContextManager
from scripts.backend.model_manager import get_manager, ModelType
from scripts.config import (
    LLAMA_N_CTX, LLAMA_N_THREADS,
    LLAMA_CHAT_MAX_TOKENS, LLAMA_CHAT_TEMPERATURE,
    LLAMA_REVIEW_MAX_TOKENS, LLAMA_REVIEW_TEMPERATURE,
    LLAMA_NORMALIZE_MAX_TOKENS, LLAMA_NORMALIZE_TEMPERATURE,
    LLAMA_MODEL_PATH,
)

log = logging.getLogger(__name__)

MODEL_PATH = LLAMA_MODEL_PATH  # Use centralized config
STORAGE_DIR = os.path.join(_PROJECT_ROOT, ".ai-agent-memory")

HANDOFF_PHRASE = "Proceed with implementation."

# Type aliases for conversation history
Message = Dict[str, str]
History = List[Message]

_context_manager = None

# Register model with the ModelManager
_manager = get_manager()


def _create_llm() -> Llama:
    """Factory function to create LLaMA model instance."""
    return Llama(
        model_path=MODEL_PATH,
        n_ctx=LLAMA_N_CTX,
        n_threads=LLAMA_N_THREADS,
        verbose=False,
    )


_manager.register_model(
    ModelType.CRITIC,
    MODEL_PATH,
    {"n_ctx": LLAMA_N_CTX, "n_threads": LLAMA_N_THREADS},
    _create_llm
)


class CriticError(Exception):
    """Raised when critic encounters an error."""
    pass


def _extract_response_text(response: dict) -> str:
    """
    Safely extract text from LLM chat completion response.
    Validates structure before accessing nested fields.
    """
    if not response or not isinstance(response, dict):
        raise CriticError("LLM returned invalid response structure")

    choices = response.get("choices")
    if not choices or not isinstance(choices, list) or len(choices) == 0:
        raise CriticError("LLM returned no choices in response")

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise CriticError("LLM response choice is not a dict")

    message = first_choice.get("message")
    if not isinstance(message, dict) or "content" not in message:
        raise CriticError("LLM response missing 'message.content' field")

    content = message["content"]
    if content is None:
        raise CriticError("LLM returned null content")

    text = str(content).strip()
    return text.encode("utf-8", errors="replace").decode("utf-8")


def _get_llm() -> Llama:
    """Get the critic model via ModelManager (lazy loading, access tracking)."""
    return _manager.get_model(ModelType.CRITIC)


def _get_context_manager() -> ContextManager:
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager(STORAGE_DIR)
    return _context_manager


def warm_up() -> bool:
    """
    Pre-load the LLaMA model into memory.
    Called during extension activation to eliminate first-request latency.
    Returns True if model loaded successfully.
    """
    try:
        _get_llm()
        return True
    except FileNotFoundError as e:
        log.error(f"Critic model file not found: {e}")
        return False
    except Exception as e:
        log.error(f"Failed to load critic model: {type(e).__name__}: {e}")
        return False


def unload() -> bool:
    """
    Unload the critic model to free memory.
    Returns True if model was unloaded, False if not loaded.
    """
    return _manager.unload_model(ModelType.CRITIC)


def is_loaded() -> bool:
    """Check if critic model is currently loaded."""
    return _manager.is_loaded(ModelType.CRITIC)


def chat(user_message: str, history: Optional[History] = None) -> str:
    """
    Chat with the critic, maintaining conversation context.

    Args:
        user_message: The current user message
        history: List of previous messages as {"role": ..., "content": ...} dicts

    Returns:
        The assistant's response
    """
    if history is None:
        history = []

    system_prompt = (
        "You are a conservative software engineering critic.\n"
        "Your job is to clarify intent BEFORE any code is written.\n\n"
        "Rules:\n"
        "- Do NOT write code.\n"
        "- Ask ONLY questions needed to clarify the current request.\n"
        "- If intent is clear, confirm it concisely and say: 'I think I understand.'"
    )

    ctx_manager = _get_context_manager()
    messages = ctx_manager.build_context(system_prompt, history, user_message)

    llm = _get_llm()
    response = llm.create_chat_completion(
        messages=messages,
        max_tokens=LLAMA_CHAT_MAX_TOKENS,
        temperature=LLAMA_CHAT_TEMPERATURE,
        top_p=0.9,
    )

    return _extract_response_text(response)


def review_diff(task: str, diff: str) -> str:
    """
    Review a task and diff for correctness.

    Args:
        task: The task description
        diff: The unified diff to review

    Returns:
        PASS or FAIL with a short reason
    """
    messages = [
        {
            "role": "system",
            "content": (
                "You are a strict software engineering reviewer.\n"
                "Respond ONLY with PASS or FAIL and a short reason.\n"
                "If uncertain, FAIL."
            )
        },
        {"role": "user", "content": f"TASK:\n{task}\n\nDIFF:\n{diff}"}
    ]

    llm = _get_llm()
    response = llm.create_chat_completion(
        messages=messages,
        max_tokens=LLAMA_REVIEW_MAX_TOKENS,
        temperature=LLAMA_REVIEW_TEMPERATURE,
    )

    return _extract_response_text(response)


def save_session_summary(summary: str) -> None:
    """Called when session ends to save summary for next time."""
    ctx_manager = _get_context_manager()
    ctx_manager.save_session_summary(summary)


def add_project_learning(learning: str) -> None:
    """Add a persistent learning about the project/user."""
    ctx_manager = _get_context_manager()
    ctx_manager.update_project_context(learning)


def normalize_task(conversation_history: History, selected_files: Optional[List[str]] = None) -> str:
    """
    Generate a normalized execution brief from conversation.
    Called when user clicks 'Proceed' to create a clean task spec for the executor.

    Output format (strict):
    TASK:
    <single sentence describing the requested change>

    FILES:
    - <relative/path/file1>
    - <relative/path/file2>

    CONSTRAINTS:
    - <optional constraints, only if explicitly stated by user>

    If the conversation cannot be normalized, returns a clarification question.
    """
    # Build file list for context
    files_context = ""
    if selected_files:
        files_context = "\n\nSELECTED FILES:\n" + "\n".join(f"- {f}" for f in selected_files)

    system_prompt = """You are a task normalization engine.

Your job is to convert a conversation into a normalized execution brief.

OUTPUT FORMAT (STRICT - follow exactly):

TASK:
<single sentence describing the requested change>

FILES:
- <relative/path/file1>
- <relative/path/file2>

CONSTRAINTS:
- <constraint if explicitly stated by user>

RULES:
- Output ONLY the normalized brief in the exact format above
- Exactly one TASK section with a single sentence
- Exactly one FILES section listing files to modify
- CONSTRAINTS section may be empty (just "CONSTRAINTS:" with nothing after)
- Do NOT include markdown
- Do NOT include code
- Do NOT include examples
- Do NOT include headers like "EXECUTION BRIEF"
- Do NOT include commentary or explanations
- Do NOT repeat yourself

If you cannot determine the task clearly, output ONLY a clarification question starting with "CLARIFY:"."""

    # Build conversation summary from recent messages
    convo_text = "\n".join(
        f"{msg['role'].upper()}: {msg['content'][:500]}"
        for msg in conversation_history[-6:]  # Last 6 messages only
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Conversation:\n{convo_text}{files_context}"}
    ]

    llm = _get_llm()
    response = llm.create_chat_completion(
        messages=messages,
        max_tokens=LLAMA_NORMALIZE_MAX_TOKENS,
        temperature=LLAMA_NORMALIZE_TEMPERATURE,
    )

    return _extract_response_text(response)
