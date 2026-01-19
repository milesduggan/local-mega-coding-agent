class GateDecision:
    CLARIFY = "clarify"
    EXECUTE = "execute"
    FORCE_EXECUTE = "force_execute"


def decide(user_input: str) -> str:
    if not user_input:
        return GateDecision.CLARIFY

    lines = [l.strip().lower() for l in user_input.splitlines() if l.strip()]
    if not lines:
        return GateDecision.CLARIFY

    first = lines[0]

    if first == "proceed with implementation":
        return GateDecision.EXECUTE

    if first == "force implement":
        return GateDecision.FORCE_EXECUTE

    return GateDecision.CLARIFY
