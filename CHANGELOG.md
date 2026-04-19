# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Changed
- VS Code extension startup is now strict-lazy for development use: activation no longer warms the main model and no longer spawns the Python backend by default
- The Python backend and Qwen model now start only on intentional agent use or explicit model-management actions

## [0.3.0] - 2026-03-31

### Changed
- Upgraded from Qwen2.5-Coder 7B to Qwen3-14B-Instruct (~9GB, better reasoning)
- `setup_models.py` now supports `--model 30b` flag to download Qwen3-Coder-30B-A3B (~19GB)
- Added `<think>` token stripping in `_extract_response_text` for Qwen3 compatibility
- To swap to 30B: set `AI_AGENT_MODEL_PATH` env var and run `python setup_models.py --model 30b`

## [0.2.0] - 2026-03-31

### Added
- Multi-turn agentic loop: TurnRunner runs up to MAX_AGENT_TURNS before generating a diff
- Router: scores user input against tool registry to pre-load relevant tools into context
- SessionContext: injects tool counts, routing decisions, and workspace metadata into turn 1 system prompt
- HistoryLog: per-turn transcript of tool calls shown in VS Code sidebar (collapsible)
- Approval gate: write/bash tools pause the loop and surface Approve/Reject UI in sidebar
- `agent_turn` JSON-RPC method in wrapper.py for VS Code extension to drive the loop
- Tool registry parity tests: audit that all tools have schema, description, is_read_only, requires_approval set
- Safety invariant test: non-read-only tools must require approval

### Changed
- Migrated from dual-model (LLaMA 3.1 8B + DeepSeek Coder 6.7B) to single Qwen2.5-Coder 7B-Instruct
- RAM requirement reduced from ~8GB to ~4.5GB loaded (minimum from 16GB to 8GB)
- Disk requirement reduced from ~8GB to ~4.5GB
- config.py: removed DEEPSEEK_* and LLAMA_* blocks, added unified MODEL_* block
- model_manager.py: ModelType.MAIN replaces ModelType.CRITIC and ModelType.EXECUTOR
- setup_models.py: downloads Qwen2.5-Coder-7B-Instruct-Q4_K_M only

### Removed
- `scripts/executor/deepseek_executor.py` — stale DeepSeek-specific executor
- `scripts/agent/llama_wrapper.py` — stale LLaMA wrapper
- `tests/test_deepseek.py`, `tests/test_llama.py` — model-specific tests no longer applicable

### Stop Reasons
- `done`: agent completed successfully
- `max_turns_reached`: hit MAX_AGENT_TURNS (default: 10) without finishing
- `approval_required`: write/bash tool needs user approval before executing
- `error`: tool failure or unparseable model output

## [0.1.0] - 2026-03-31

### Added
- Dual-model architecture: LLaMA 3.1 8B for chat/review, DeepSeek Coder 6.7B for code generation
- Critic-Executor-Review workflow with built-in diff validation
- AST-based Python chunking with 50-75% token savings
- Extensible tool system: bash, file operations, glob/grep/find_definition search
- Auto memory management with configurable idle timeout
- Path traversal protection and input validation
- VS Code sidebar extension with Apply/Reject diff UX
- JSON-RPC backend with model lifecycle management
- Decision-State Snapshot system for deterministic agent behavior
- Token monitor with soft (70%) and hard (85%) context limits
- Full configuration via environment variables
- CI/CD with GitHub Actions
