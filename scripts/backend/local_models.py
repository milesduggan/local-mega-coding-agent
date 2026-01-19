from llama_cpp import Llama


class LocalLlama:
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
    def __init__(self, model_path: str, n_ctx: int = 4096):
        self.llm = Llama(
            model_path=model_path,
            n_ctx=n_ctx,
            verbose=False,
        )

    def __call__(self, prompt: str) -> str:
        result = self.llm(prompt, max_tokens=1024)
        return result["choices"][0]["text"].strip()
