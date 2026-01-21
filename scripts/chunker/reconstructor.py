"""
Reconstruct full file from modified chunks.

Takes original file content and modified chunks, splices them back
together to produce the complete updated file.
"""

import ast
import re
from typing import Dict, List, Optional

from .python_chunker import CodeChunk


class ReconstructionError(Exception):
    """Raised when file reconstruction fails."""
    pass


def _parse_chunk_output(output: str) -> Dict[str, str]:
    """
    Parse LLM output containing modified chunks.

    Expected format:
    CHUNK: chunk_name
    <chunk content>

    CHUNK: another_chunk
    <chunk content>

    Returns:
        Dict mapping chunk names to their new content
    """
    result = {}

    # Split on CHUNK: markers
    pattern = r'^CHUNK:\s*(\S+)'
    parts = re.split(pattern, output, flags=re.MULTILINE)

    # parts[0] is any text before first CHUNK:
    # then alternating: chunk_name, content, chunk_name, content, ...
    if len(parts) < 3:
        return result

    i = 1
    while i < len(parts) - 1:
        chunk_name = parts[i].strip()
        content = parts[i + 1]

        if not chunk_name:
            i += 2
            continue

        # Clean up content
        content = content.strip('\n')

        # Remove trailing markdown if present
        content = re.sub(r'\n*```$', '', content)

        # Remove leading markdown if present
        content = re.sub(r'^```(?:python)?\n', '', content)

        result[chunk_name] = content
        i += 2

    return result


def _validate_python_syntax(content: str) -> bool:
    """Check if content is valid Python."""
    try:
        ast.parse(content)
        return True
    except SyntaxError:
        return False


def reconstruct_file(
    original_content: str,
    original_chunks: List[CodeChunk],
    modified_chunks: Dict[str, str]
) -> str:
    """
    Replace original chunks with modified versions.

    Args:
        original_content: Full original file content
        original_chunks: Chunks extracted from original file
        modified_chunks: Dict of chunk_name -> new_content

    Returns:
        Reconstructed file content

    Raises:
        ReconstructionError: If reconstruction produces invalid Python
    """
    if not modified_chunks:
        return original_content

    lines = original_content.splitlines(keepends=True)

    # Build a map of chunk name to original chunk
    chunk_map = {chunk.name: chunk for chunk in original_chunks}

    # Sort chunks to replace by start_line descending
    # (replace from bottom to top to preserve line numbers)
    chunks_to_replace = []
    for name, new_content in modified_chunks.items():
        if name in chunk_map:
            chunks_to_replace.append((chunk_map[name], new_content))

    chunks_to_replace.sort(key=lambda x: -x[0].start_line)

    # Replace each chunk
    for original_chunk, new_content in chunks_to_replace:
        start_idx = original_chunk.start_line - 1  # 0-indexed
        end_idx = original_chunk.end_line  # exclusive

        # Ensure new content ends with newline
        if new_content and not new_content.endswith('\n'):
            new_content += '\n'

        # Split new content into lines
        new_lines = new_content.splitlines(keepends=True)

        # Replace the chunk's lines
        lines = lines[:start_idx] + new_lines + lines[end_idx:]

    result = ''.join(lines)

    # Validate the result is still valid Python
    if not _validate_python_syntax(result):
        raise ReconstructionError(
            "Reconstruction produced invalid Python syntax. "
            "This may indicate a chunk boundary mismatch."
        )

    return result


def reconstruct_from_llm_output(
    original_content: str,
    original_chunks: List[CodeChunk],
    llm_output: str
) -> str:
    """
    High-level function to reconstruct file from LLM output.

    Args:
        original_content: Full original file content
        original_chunks: Chunks extracted from original file
        llm_output: Raw LLM output containing CHUNK: blocks

    Returns:
        Reconstructed file content
    """
    modified_chunks = _parse_chunk_output(llm_output)

    if not modified_chunks:
        raise ReconstructionError(
            "No CHUNK: blocks found in LLM output. "
            "Expected format: CHUNK: chunk_name\\n<content>"
        )

    return reconstruct_file(original_content, original_chunks, modified_chunks)


if __name__ == "__main__":
    # Quick test
    from .python_chunker import parse_python_file

    original = '''import os

def hello():
    print("hello")

def goodbye():
    print("goodbye")
'''

    chunks = parse_python_file(original, "test.py")
    print("Original chunks:")
    for c in chunks:
        print(f"  {c.name}: lines {c.start_line}-{c.end_line}")

    # Simulate LLM modifying the hello function
    llm_output = '''CHUNK: hello
def hello():
    print("hello world!")
    print("with logging")
'''

    result = reconstruct_from_llm_output(original, chunks, llm_output)
    print("\nReconstructed file:")
    print(result)
