from llama_cpp import Llama

model = Llama(
    model_path="models/deepseek/deepseek-coder-6.7b-instruct.Q2_K.gguf",
    n_ctx=2048,
)

output = model("Write a Python function that adds two numbers.")

print(output["choices"][0]["text"])
