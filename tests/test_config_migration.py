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
    assert not hasattr(config, "DEEPSEEK_N_CTX")
    assert not hasattr(config, "LLAMA_N_CTX")
    assert not hasattr(config, "DEEPSEEK_MODEL_PATH")
    assert not hasattr(config, "LLAMA_MODEL_PATH")

def test_max_agent_turns_default():
    from scripts import config
    assert config.MAX_AGENT_TURNS == 10
