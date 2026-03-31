import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_model_config_exists():
    from scripts import config
    assert hasattr(config, "MODEL_PATH")
    assert hasattr(config, "MODEL_N_CTX")
    assert hasattr(config, "MODEL_N_THREADS")
    assert hasattr(config, "MODEL_CHAT_MAX_TOKENS")
    assert hasattr(config, "MODEL_CHAT_TEMPERATURE")
    assert hasattr(config, "MODEL_CODE_MAX_TOKENS")
    assert hasattr(config, "MODEL_CODE_TEMPERATURE")
    assert hasattr(config, "MODEL_REVIEW_MAX_TOKENS")
    assert hasattr(config, "MODEL_REVIEW_TEMPERATURE")
    assert hasattr(config, "MODEL_NORMALIZE_MAX_TOKENS")
    assert hasattr(config, "MODEL_NORMALIZE_TEMPERATURE")
    assert hasattr(config, "MAX_AGENT_TURNS")

def test_old_config_gone():
    from scripts import config
    old_names = [
        "DEEPSEEK_N_CTX", "DEEPSEEK_MAX_TOKENS", "DEEPSEEK_TEMPERATURE",
        "DEEPSEEK_TOP_P", "DEEPSEEK_REPEAT_PENALTY", "DEEPSEEK_N_THREADS",
        "DEEPSEEK_MODEL_PATH",
        "LLAMA_N_CTX", "LLAMA_N_THREADS", "LLAMA_CHAT_MAX_TOKENS",
        "LLAMA_CHAT_TEMPERATURE", "LLAMA_REVIEW_MAX_TOKENS",
        "LLAMA_REVIEW_TEMPERATURE", "LLAMA_NORMALIZE_MAX_TOKENS",
        "LLAMA_NORMALIZE_TEMPERATURE", "LLAMA_MODEL_PATH",
    ]
    for name in old_names:
        assert not hasattr(config, name), f"Old config name still present: {name}"

def test_max_agent_turns_default():
    from scripts import config
    assert config.MAX_AGENT_TURNS == 10

def test_code_tuning_params_present():
    from scripts import config
    assert hasattr(config, "MODEL_CODE_TOP_P")
    assert hasattr(config, "MODEL_CODE_REPEAT_PENALTY")
    assert config.MODEL_CODE_TOP_P == 0.9
    assert config.MODEL_CODE_REPEAT_PENALTY == 1.1

def test_model_type_single():
    from scripts.backend.model_manager import ModelType
    assert hasattr(ModelType, "MAIN")
    assert not hasattr(ModelType, "CRITIC")
    assert not hasattr(ModelType, "EXECUTOR")
