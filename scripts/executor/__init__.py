"""
Executor module for DeepSeek-based code generation.

This module provides the interface to the DeepSeek Coder 6.7B model
for generating code changes based on task specifications.
"""

from .executor import execute

__all__ = [
    "execute",
]
