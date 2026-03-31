"""
Central configuration for model parameters.

All values can be overridden via environment variables prefixed with AI_AGENT_.
"""

import os


def _get_int(name: str, default: int) -> int:
    """Get integer config value from environment or use default."""
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    """Get float config value from environment or use default."""
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


# =============================================================================
# Model Settings (Qwen2.5-Coder 7B-Instruct)
# =============================================================================

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MODEL_PATH = os.environ.get(
    "AI_AGENT_MODEL_PATH",
    os.path.join(_PROJECT_ROOT, "models", "qwen", "qwen2.5-coder-7b-instruct-q4_k_m.gguf")
)

# Context window — larger allows more file content but uses more RAM
MODEL_N_CTX = _get_int("AI_AGENT_MODEL_N_CTX", 8192)

# CPU threads for inference
MODEL_N_THREADS = _get_int("AI_AGENT_MODEL_N_THREADS", 4)

# Chat role — moderate creativity for conversation
MODEL_CHAT_MAX_TOKENS = _get_int("AI_AGENT_MODEL_CHAT_MAX_TOKENS", 512)
MODEL_CHAT_TEMPERATURE = _get_float("AI_AGENT_MODEL_CHAT_TEMPERATURE", 0.7)

# Code generation role — low temperature for determinism
MODEL_CODE_MAX_TOKENS = _get_int("AI_AGENT_MODEL_CODE_MAX_TOKENS", 1024)
MODEL_CODE_TEMPERATURE = _get_float("AI_AGENT_MODEL_CODE_TEMPERATURE", 0.2)

# Nucleus sampling for code generation
MODEL_CODE_TOP_P = _get_float("AI_AGENT_MODEL_CODE_TOP_P", 0.9)

# Penalize token repetition — prevents code repetition loops
MODEL_CODE_REPEAT_PENALTY = _get_float("AI_AGENT_MODEL_CODE_REPEAT_PENALTY", 1.1)

# Review role — conservative for correctness judgments
MODEL_REVIEW_MAX_TOKENS = _get_int("AI_AGENT_MODEL_REVIEW_MAX_TOKENS", 256)
MODEL_REVIEW_TEMPERATURE = _get_float("AI_AGENT_MODEL_REVIEW_TEMPERATURE", 0.3)

# Task normalization role — low temp for consistent format
MODEL_NORMALIZE_MAX_TOKENS = _get_int("AI_AGENT_MODEL_NORMALIZE_MAX_TOKENS", 300)
MODEL_NORMALIZE_TEMPERATURE = _get_float("AI_AGENT_MODEL_NORMALIZE_TEMPERATURE", 0.2)

# Turn loop role — moderate for tool call decisions
MODEL_TURN_MAX_TOKENS = _get_int("AI_AGENT_MODEL_TURN_MAX_TOKENS", 512)
MODEL_TURN_TEMPERATURE = _get_float("AI_AGENT_MODEL_TURN_TEMPERATURE", 0.4)

# =============================================================================
# Agentic Loop Settings
# =============================================================================

# Maximum turns before giving up and returning max_turns_reached
MAX_AGENT_TURNS = _get_int("AI_AGENT_MAX_TURNS", 10)

# =============================================================================
# Chunker Settings
# =============================================================================

CHUNK_MAX_TOKENS = _get_int("AI_AGENT_CHUNK_MAX_TOKENS", 3000)

# =============================================================================
# Timeout Settings (milliseconds)
# =============================================================================

TIMEOUT_CHAT_MS = _get_int("AI_AGENT_TIMEOUT_CHAT_MS", 60000)
TIMEOUT_NORMALIZE_MS = _get_int("AI_AGENT_TIMEOUT_NORMALIZE_MS", 60000)
TIMEOUT_EXECUTE_MS = _get_int("AI_AGENT_TIMEOUT_EXECUTE_MS", 180000)
TIMEOUT_REVIEW_MS = _get_int("AI_AGENT_TIMEOUT_REVIEW_MS", 60000)
TIMEOUT_WARMUP_MS = _get_int("AI_AGENT_TIMEOUT_WARMUP_MS", 120000)

# =============================================================================
# Model Lifecycle Settings
# =============================================================================

MODEL_IDLE_TIMEOUT_MINUTES = _get_int("AI_AGENT_MODEL_IDLE_TIMEOUT_MINUTES", 15)
AUTO_UNLOAD_ENABLED = os.environ.get(
    "AI_AGENT_AUTO_UNLOAD_ENABLED", "true"
).lower() in ("1", "true", "yes")

# =============================================================================
# Debug Settings
# =============================================================================

DEBUG_LOG_LLM_IO = os.environ.get("AI_AGENT_DEBUG_LOG_LLM_IO", "").lower() in ("1", "true", "yes")
