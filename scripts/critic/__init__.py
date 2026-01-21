"""
Critic module for LLaMA-based chat and review functionality.

This module provides the interface to the LLaMA 3.1 8B model for:
- Chat: Clarifying user intent and answering questions
- Review: Validating generated code changes
- Normalize: Converting conversation to task specification
"""

from .critic import chat, review_diff, normalize_task, HANDOFF_PHRASE

__all__ = [
    "chat",
    "review_diff",
    "normalize_task",
    "HANDOFF_PHRASE",
]
