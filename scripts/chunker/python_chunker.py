"""
Parse Python files into logical chunks using AST.

Chunks are logical units of code (functions, classes, imports, module-level code)
that can be processed independently by the LLM.
"""

import ast
from dataclasses import dataclass, field
from typing import List, Set


@dataclass
class CodeChunk:
    """A logical chunk of code from a source file."""
    name: str           # "execute", "MyClass", "imports", "module_level_0"
    chunk_type: str     # "function", "class", "imports", "module_level"
    start_line: int     # 1-indexed, inclusive
    end_line: int       # 1-indexed, inclusive
    content: str        # Exact source code
    dependencies: List[str] = field(default_factory=list)  # Names referenced in this chunk


def _get_node_end_line(node: ast.AST, lines: List[str]) -> int:
    """
    Get the actual end line of a node, handling decorators and docstrings.
    AST end_lineno can be unreliable for some constructs.
    """
    if hasattr(node, 'end_lineno') and node.end_lineno is not None:
        return node.end_lineno
    # Fallback: return start line
    return node.lineno


def _extract_dependencies(node: ast.AST) -> Set[str]:
    """
    Extract names referenced in a node (potential dependencies on other chunks).
    """
    deps = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            deps.add(child.id)
        elif isinstance(child, ast.Attribute):
            # Get the root name (e.g., 'os' from 'os.path.join')
            root = child
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name):
                deps.add(root.id)
        elif isinstance(child, ast.Call):
            # Function calls
            if isinstance(child.func, ast.Name):
                deps.add(child.func.id)
            elif isinstance(child.func, ast.Attribute) and isinstance(child.func.value, ast.Name):
                deps.add(child.func.value.id)
    return deps


def _get_decorator_start(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> int:
    """Get the start line including decorators."""
    if node.decorator_list:
        return node.decorator_list[0].lineno
    return node.lineno


def parse_python_file(content: str, filename: str = "<unknown>") -> List[CodeChunk]:
    """
    Parse Python source into logical chunks.

    Args:
        content: Python source code
        filename: Filename for error messages

    Returns:
        List of CodeChunk objects representing logical units

    Raises:
        SyntaxError: If the Python code cannot be parsed
    """
    tree = ast.parse(content, filename=filename)
    lines = content.splitlines(keepends=True)
    total_lines = len(lines)

    # If file is empty or nearly empty, return single chunk
    if total_lines == 0:
        return []

    chunks: List[CodeChunk] = []
    covered_lines: Set[int] = set()

    # Collect imports (group consecutive imports into one chunk)
    import_nodes = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            import_nodes.append(node)

    if import_nodes:
        start = import_nodes[0].lineno
        end = _get_node_end_line(import_nodes[-1], lines)
        import_content = ''.join(lines[start - 1:end])
        chunks.append(CodeChunk(
            name="imports",
            chunk_type="imports",
            start_line=start,
            end_line=end,
            content=import_content,
            dependencies=[]
        ))
        for line_num in range(start, end + 1):
            covered_lines.add(line_num)

    # Collect functions and classes
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = _get_decorator_start(node)
            end = _get_node_end_line(node, lines)
            func_content = ''.join(lines[start - 1:end])
            deps = list(_extract_dependencies(node) - {node.name})

            chunks.append(CodeChunk(
                name=node.name,
                chunk_type="function",
                start_line=start,
                end_line=end,
                content=func_content,
                dependencies=deps
            ))
            for line_num in range(start, end + 1):
                covered_lines.add(line_num)

        elif isinstance(node, ast.ClassDef):
            start = _get_decorator_start(node)
            end = _get_node_end_line(node, lines)
            class_content = ''.join(lines[start - 1:end])
            deps = list(_extract_dependencies(node) - {node.name})

            chunks.append(CodeChunk(
                name=node.name,
                chunk_type="class",
                start_line=start,
                end_line=end,
                content=class_content,
                dependencies=deps
            ))
            for line_num in range(start, end + 1):
                covered_lines.add(line_num)

    # Collect module-level code (constants, assignments, etc.)
    module_level_idx = 0
    current_block_start = None
    current_block_nodes = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef,
                            ast.AsyncFunctionDef, ast.ClassDef)):
            # Save any pending module-level block
            if current_block_nodes:
                start = current_block_nodes[0].lineno
                end = _get_node_end_line(current_block_nodes[-1], lines)
                block_content = ''.join(lines[start - 1:end])
                deps = set()
                for n in current_block_nodes:
                    deps.update(_extract_dependencies(n))

                chunks.append(CodeChunk(
                    name=f"module_level_{module_level_idx}",
                    chunk_type="module_level",
                    start_line=start,
                    end_line=end,
                    content=block_content,
                    dependencies=list(deps)
                ))
                for line_num in range(start, end + 1):
                    covered_lines.add(line_num)
                module_level_idx += 1
                current_block_nodes = []
            continue

        # It's a module-level statement
        current_block_nodes.append(node)

    # Don't forget last block
    if current_block_nodes:
        start = current_block_nodes[0].lineno
        end = _get_node_end_line(current_block_nodes[-1], lines)
        block_content = ''.join(lines[start - 1:end])
        deps = set()
        for n in current_block_nodes:
            deps.update(_extract_dependencies(n))

        chunks.append(CodeChunk(
            name=f"module_level_{module_level_idx}",
            chunk_type="module_level",
            start_line=start,
            end_line=end,
            content=block_content,
            dependencies=list(deps)
        ))

    # Sort chunks by start line
    chunks.sort(key=lambda c: c.start_line)

    return chunks


if __name__ == "__main__":
    # Quick test with a sample file
    import sys

    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r') as f:
            content = f.read()
        chunks = parse_python_file(content, sys.argv[1])
        for chunk in chunks:
            print(f"\n{'='*60}")
            print(f"CHUNK: {chunk.name} ({chunk.chunk_type})")
            print(f"Lines: {chunk.start_line}-{chunk.end_line}")
            print(f"Dependencies: {chunk.dependencies}")
            print(f"Content preview: {chunk.content[:100]}...")
    else:
        print("Usage: python python_chunker.py <file.py>")
