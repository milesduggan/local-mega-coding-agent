import os
import sys
from typing import List, Dict, Optional
from llama_cpp import Llama

# Add parent directory to path for memory module import
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_MODULE_DIR))
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "scripts"))

from memory.context_manager import ContextManager

MODEL_PATH = os.path.join(_PROJECT_ROOT, "models", "llama", "Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf")
STORAGE_DIR = os.path.join(_PROJECT_ROOT, ".ai-agent-memory")

HANDOFF_PHRASE = "Proceed with implementation."

# Type aliases for conversation history
Message = Dict[str, str]
History = List[Message]

_llm = None
_context_manager = None


def _get_llm() -> Llama:
    global _llm
    if _llm is None:
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(
                f"Model not found: {MODEL_PATH}\n"
                f"Run setup_models.py to download the model."
            )
        _llm = Llama(
            model_path=MODEL_PATH,
            n_ctx=16384,
            n_threads=8,
            verbose=False,
        )
    return _llm


def _get_context_manager() -> ContextManager:
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager(STORAGE_DIR)
    return _context_manager


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
        max_tokens=512,
        temperature=0.7,
        top_p=0.9,
    )

    text = response["choices"][0]["message"]["content"].strip()
    return text.encode("utf-8", errors="replace").decode("utf-8")


def review(task: str, diff: str) -> str:
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
        max_tokens=256,
        temperature=0.3,
    )

    text = response["choices"][0]["message"]["content"].strip()
    return text.encode("utf-8", errors="replace").decode("utf-8")


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
        max_tokens=300,
        temperature=0.2,
    )

    text = response["choices"][0]["message"]["content"].strip()
    return text.encode("utf-8", errors="replace").decode("utf-8")
