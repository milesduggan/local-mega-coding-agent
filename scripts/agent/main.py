import os
from scripts.agent.snapshot import DecisionSnapshot, SnapshotError
from scripts.agent.system_prompt import build_system_context
from scripts.agent.llama_wrapper import LlamaWrapper
from scripts.agent.brief_normalizer import normalize_brief
from scripts.agent.diff_normalizer import normalize_diff
from scripts.executor.deepseek_executor import DeepSeekExecutor
from scripts.review.review import review


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SNAPSHOT_PATH = os.path.join(BASE_DIR, "snapshot.txt")


def load_snapshot() -> DecisionSnapshot:
    try:
        with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            snapshot = DecisionSnapshot(f.read())
            snapshot.validate()
            return snapshot
    except FileNotFoundError:
        raise SnapshotError("Snapshot file not found.")
    except SnapshotError:
        raise
    except Exception as e:
        raise SnapshotError(str(e))


def agent_loop(user_input: str, files: dict, llama_call, deepseek_call):
    snapshot = load_snapshot()
    _ = build_system_context(snapshot.raw_text)

    llama = LlamaWrapper(llama_call)
    output = llama.handle(user_input)

    if "EXECUTION BRIEF" not in output:
        return {"mode": "clarify", "message": output}

    clean_brief = normalize_brief(output)

    executor = DeepSeekExecutor(deepseek_call)
    raw_diff = executor.execute(clean_brief, files)

    diff = normalize_diff(raw_diff)

    result = review(clean_brief, diff)

    if not result.passed:
        return {"mode": "rejected", "reasons": result.reasons, "diff": diff}

    return {"mode": "accepted", "diff": diff}
