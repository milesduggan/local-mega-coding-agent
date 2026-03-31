# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
