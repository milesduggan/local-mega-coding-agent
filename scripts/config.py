"""
Central configuration for model parameters.

All values can be overridden via environment variables prefixed with AI_AGENT_.
This allows tuning model behavior without code changes.

Example:
    export AI_AGENT_DEEPSEEK_MAX_TOKENS=2048
    export AI_AGENT_LLAMA_CHAT_TEMPERATURE=0.5
"""

import os
from typing import Union


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
# DeepSeek (Executor) Settings
# =============================================================================

# Context window size - larger allows more file content but uses more memory
DEEPSEEK_N_CTX = _get_int("AI_AGENT_DEEPSEEK_N_CTX", 8192)

# Maximum tokens in model output - increase if output is being truncated
DEEPSEEK_MAX_TOKENS = _get_int("AI_AGENT_DEEPSEEK_MAX_TOKENS", 1024)

# Temperature for code generation - lower = more deterministic
DEEPSEEK_TEMPERATURE = _get_float("AI_AGENT_DEEPSEEK_TEMPERATURE", 0.2)

# Nucleus sampling threshold
DEEPSEEK_TOP_P = _get_float("AI_AGENT_DEEPSEEK_TOP_P", 0.9)

# Penalty for repeating tokens - helps prevent code repetition loops
DEEPSEEK_REPEAT_PENALTY = _get_float("AI_AGENT_DEEPSEEK_REPEAT_PENALTY", 1.1)

# Number of CPU threads for inference
DEEPSEEK_N_THREADS = _get_int("AI_AGENT_DEEPSEEK_N_THREADS", 4)


# =============================================================================
# LLaMA (Critic) Settings
# =============================================================================

# Context window size - 4096 is sufficient for chat/review tasks
LLAMA_N_CTX = _get_int("AI_AGENT_LLAMA_N_CTX", 4096)

# Max tokens for chat responses
LLAMA_CHAT_MAX_TOKENS = _get_int("AI_AGENT_LLAMA_CHAT_MAX_TOKENS", 512)

# Max tokens for review verdicts (PASS/FAIL with reason)
LLAMA_REVIEW_MAX_TOKENS = _get_int("AI_AGENT_LLAMA_REVIEW_MAX_TOKENS", 256)

# Max tokens for task normalization output
LLAMA_NORMALIZE_MAX_TOKENS = _get_int("AI_AGENT_LLAMA_NORMALIZE_MAX_TOKENS", 300)

# Temperature for chat - moderate creativity for conversation
LLAMA_CHAT_TEMPERATURE = _get_float("AI_AGENT_LLAMA_CHAT_TEMPERATURE", 0.7)

# Temperature for review - conservative for correctness judgments
LLAMA_REVIEW_TEMPERATURE = _get_float("AI_AGENT_LLAMA_REVIEW_TEMPERATURE", 0.3)

# Temperature for task normalization - low for consistent output format
LLAMA_NORMALIZE_TEMPERATURE = _get_float("AI_AGENT_LLAMA_NORMALIZE_TEMPERATURE", 0.2)

# Number of CPU threads for inference
LLAMA_N_THREADS = _get_int("AI_AGENT_LLAMA_N_THREADS", 4)


# =============================================================================
# Chunker Settings
# =============================================================================

# Maximum tokens to include in chunk selection (approximate)
# Larger values include more context but increase latency
CHUNK_MAX_TOKENS = _get_int("AI_AGENT_CHUNK_MAX_TOKENS", 3000)


# =============================================================================
# Timeout Settings (milliseconds)
# These are defaults - TypeScript side reads from VSCode settings
# =============================================================================

TIMEOUT_CHAT_MS = _get_int("AI_AGENT_TIMEOUT_CHAT_MS", 60000)
TIMEOUT_NORMALIZE_MS = _get_int("AI_AGENT_TIMEOUT_NORMALIZE_MS", 60000)
TIMEOUT_EXECUTE_MS = _get_int("AI_AGENT_TIMEOUT_EXECUTE_MS", 180000)
TIMEOUT_REVIEW_MS = _get_int("AI_AGENT_TIMEOUT_REVIEW_MS", 60000)
TIMEOUT_WARMUP_MS = _get_int("AI_AGENT_TIMEOUT_WARMUP_MS", 120000)


# =============================================================================
# Model Lifecycle Settings
# =============================================================================

# Minutes of inactivity before auto-unloading a model (0 = disable auto-unload)
MODEL_IDLE_TIMEOUT_MINUTES = _get_int("AI_AGENT_MODEL_IDLE_TIMEOUT_MINUTES", 15)

# Enable automatic model unloading after idle timeout
AUTO_UNLOAD_ENABLED = os.environ.get(
    "AI_AGENT_AUTO_UNLOAD_ENABLED", "true"
).lower() in ("1", "true", "yes")


# =============================================================================
# Debug Settings
# =============================================================================

# Enable verbose logging of LLM inputs/outputs
DEBUG_LOG_LLM_IO = os.environ.get("AI_AGENT_DEBUG_LOG_LLM_IO", "").lower() in ("1", "true", "yes")
