"""
Local model wrappers for LLaMA and DeepSeek.
These are utility classes for direct model access if needed.
The executor module now handles DeepSeek directly with appropriate context size.
"""

from llama_cpp import Llama


class LocalLlama:
    """Wrapper for local LLaMA model."""

    def __init__(self, model_path: str, n_ctx: int = 4096):
        self.llm = Llama(
            model_path=model_path,
            n_ctx=n_ctx,
            verbose=False,
        )

    def __call__(self, prompt: str) -> str:
        result = self.llm(prompt, max_tokens=512)
        return result["choices"][0]["text"].strip()


class LocalDeepSeek:
    """
    Wrapper for local DeepSeek model.
    Configured for full file output (not diffs).
    """

    def __init__(self, model_path: str, n_ctx: int = 16384):
        self.llm = Llama(
            model_path=model_path,
            n_ctx=n_ctx,
            verbose=False,
        )

    def __call__(self, prompt: str) -> str:
        result = self.llm(
            prompt,
            max_tokens=4096,
            temperature=0.2,
            stop=["</s>", "<|EOT|>"],
        )
        text = result["choices"][0]["text"].strip()
        return text.encode("utf-8", errors="replace").decode("utf-8")
