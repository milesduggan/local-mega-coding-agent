def normalize_diff(text: str) -> str:
    lines = [l for l in text.splitlines() if l.strip() != ""]
    diff_lines = []

    for i in range(len(lines) - 1):
        if lines[i].startswith("--- ") and lines[i + 1].startswith("+++ "):
            # Found real diff start
            diff_lines.append(lines[i])
            diff_lines.append(lines[i + 1])

            # Capture remaining diff body
            for line in lines[i + 2:]:
                if line.startswith(("@@ ", "+", "-", " ")):
                    diff_lines.append(line)
                else:
                    br