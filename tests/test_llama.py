from llama_cpp import Llama

model = Llama(
    model_path="models/llama/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
    n_ctx=2048,
)

response = model("Say hello in one short sentence.")

print(response["choices"][0]["text"])
