"""
Backend module for VSCode extension communication.

This module provides the JSON-RPC interface that the TypeScript
extension uses to communicate with the Python LLM backend.
"""

from .model_manager import get_manager, ModelType

__all__ = [
    "get_manager",
    "ModelType",
]
