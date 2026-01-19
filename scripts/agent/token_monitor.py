class TokenMonitor:
    def __init__(self, max_tokens: int):
        self.max_tokens = max_tokens
        self.used_tokens = 0

    def estimate(self, text: str) -> int:
        if not text:
            return 0
        return max(1, len(text) // 4)

    def add(self, text: str):
        self.used_tokens += self.estimate(text)

    @property
    def usage_ratio(self) -> float:
        return self.used_tokens / self.max_tokens

    @property
    def soft_limit_reached(self) -> bool:
        return self.usage_ratio >= 0.7

    @property
    def hard_limit_reached(self) -> bool:
        return self.usage_ratio >= 0.85
