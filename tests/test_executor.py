from scripts.executor.executor import execute

files = {
    "example.py": "def add(a, b):\n    return a + b\n"
}

task = "Add basic input validation to ensure both arguments are numbers."

diff = execute(task, files)

print(diff)
