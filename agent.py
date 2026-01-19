import os
from pathlib import Path

from scripts.critic.critic import chat, review, HANDOFF_PHRASE
from scripts.executor.executor import execute


HELP_TEXT = """
Available commands:
  /files add <path>...  - Add files for the executor
  /files remove <path>  - Remove a file
  /files list           - Show selected files
  /files clear          - Clear all files
  /help                 - Show this help
  Ctrl+C                - Exit

Workflow:
  1. Describe your task
  2. Answer the critic's questions
  3. Use /files add to specify files
  4. Type "Proceed with implementation." to execute
"""


def looks_like_question(text: str) -> bool:
    """Check if the critic's response appears to be asking for clarification."""
    question_markers = [
        "?",
        "clarify",
        "confirm",
        "could you",
        "can you",
        "what about",
        "how about",
        "tell me",
        "please explain",
        "more details",
        "which",
        "when",
        "where",
        "why",
        "how",
    ]
    text_lower = text.lower()
    return any(marker in text_lower for marker in question_markers)


def read_file_safely(file_path: str) -> tuple[str, str | None]:
    """
    Read a file from disk.

    Returns:
        Tuple of (content, error_message). If successful, error_message is None.
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return "", f"File not found: {file_path}"
        if not path.is_file():
            return "", f"Not a file: {file_path}"
        if path.stat().st_size > 100_000:  # 100KB limit
            return "", f"File too large (>100KB): {file_path}"

        content = path.read_text(encoding="utf-8")
        return content, None
    except PermissionError:
        return "", f"Permission denied: {file_path}"
    except UnicodeDecodeError:
        return "", f"Cannot read file (not UTF-8): {file_path}"
    except Exception as e:
        return "", f"Error reading {file_path}: {e}"


def handle_files_command(args: list[str], file_paths: set[str]) -> str:
    """
    Handle /files commands.

    Args:
        args: Command arguments (e.g., ["add", "foo.py"])
        file_paths: Current set of file paths (modified in place)

    Returns:
        Status message to display
    """
    if not args:
        return "Usage: /files add|remove|list|clear [paths...]"

    cmd = args[0].lower()

    if cmd == "add":
        if len(args) < 2:
            return "Usage: /files add <path> [path...]"
        added = []
        errors = []
        for path in args[1:]:
            # Normalize the path
            normalized = os.path.abspath(path)
            if os.path.exists(normalized):
                file_paths.add(normalized)
                added.append(path)
            else:
                errors.append(f"  Not found: {path}")

        result = []
        if added:
            result.append(f"Added: {', '.join(added)}")
        if errors:
            result.append("Errors:\n" + "\n".join(errors))
        return "\n".join(result) if result else "No files added"

    elif cmd == "remove":
        if len(args) < 2:
            return "Usage: /files remove <path> [path...]"
        removed = []
        for path in args[1:]:
            normalized = os.path.abspath(path)
            if normalized in file_paths:
                file_paths.remove(normalized)
                removed.append(path)
        return f"Removed: {', '.join(removed)}" if removed else "No files removed"

    elif cmd == "list":
        if not file_paths:
            return "No files selected"
        return "Selected files:\n" + "\n".join(f"  - {p}" for p in sorted(file_paths))

    elif cmd == "clear":
        count = len(file_paths)
        file_paths.clear()
        return f"Cleared {count} file(s)"

    else:
        return f"Unknown command: {cmd}. Use add|remove|list|clear"


def main():
    print("Critic ready. Talk freely. Type Ctrl+C to exit.")
    print("Use /files add <path> to specify files for the executor.")
    print("Type /help for more commands.\n")

    normalized_task = None
    conversation_history: list[dict[str, str]] = []
    file_paths: set[str] = set()

    while True:
        try:
            user_input = input("You: ").strip()
        except KeyboardInterrupt:
            print("\nExiting.")
            break

        # Skip empty input
        if not user_input:
            continue

        # Handle /help command
        if user_input == "/help":
            print(HELP_TEXT)
            continue

        # Handle /files command
        if user_input.startswith("/files"):
            args = user_input.split()[1:]  # Split and remove "/files"
            result = handle_files_command(args, file_paths)
            print(f"\n{result}\n")
            continue

        if user_input == HANDOFF_PHRASE:
            if not normalized_task:
                print("No confirmed task to execute.")
                continue

            if not file_paths:
                print("No files specified. Use /files add <path> first.")
                continue

            print("\n--- EXECUTING TASK ---\n")

            # Read files from disk
            files = {}
            for path in file_paths:
                content, error = read_file_safely(path)
                if error:
                    print(f"Warning: {error}")
                else:
                    # Use relative path as key for cleaner diffs
                    rel_path = os.path.relpath(path)
                    files[rel_path] = content

            if not files:
                print("No valid files to process.")
                continue

            diff = execute(normalized_task, files)

            print("\n--- DIFF ---\n")
            print(diff)

            confirm = input("\nRun critic review? (y/n): ").strip().lower()
            if confirm != "y":
                print("Review skipped.")
                # Clear state for next task
                normalized_task = None
                conversation_history.clear()
                continue

            verdict = review(normalized_task, diff)

            print("\n--- REVIEW ---\n")
            print(verdict)

            # Clear state for next task
            normalized_task = None
            conversation_history.clear()
            continue

        response = chat(user_input, conversation_history)
        print(f"\nCritic: {response}\n")

        # Update history with both user message and response
        conversation_history.append({"role": "user", "content": user_input})
        conversation_history.append({"role": "assistant", "content": response})

        # Only freeze intent if the critic is NOT asking questions
        if not looks_like_question(response):
            normalized_task = response


if __name__ == "__main__":
    main()
