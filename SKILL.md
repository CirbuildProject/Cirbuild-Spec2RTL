---
name: coding_skill
description: Python Coding Standards & Best Practices for Spec2RTL-Agent & EDA Development
---

# Python Coding Standards & Best Practices for Spec2RTL-Agent & EDA Development

This document outlines the mandatory coding standards, architectural principles, and EDA-specific development practices for the Antigravity AI agent. Adherence to these guidelines is non-negotiable to ensure maximum modularity, readability, and maintainability of the hardware generation pipeline.

## 1. General Python Conventions
* **PEP 8 Compliance**: All code must strictly adhere to PEP 8 standards. Use formatters like `black` (with an 88-character line limit) and `ruff` for linting.
* **Strict Type Hinting**: Every function signature, class attribute, and complex variable must have Python type hints (`typing` module). This is critical for EDA tools where data types (e.g., AST nodes, binary strings, file paths) frequently cross boundaries.
  * *Good*: `def parse_verilog_ast(filepath: Path) -> Dict[str, Any]:`
  * *Bad*: `def parse_verilog(filepath):`
* **Docstrings (Google Style)**: Every module, class, and public function requires a Google-style docstring. Docstrings must explain the *why* and the edge cases, not just the *what*. Include `Args:`, `Returns:`, and `Raises:` sections explicitly.
* **Pathlib over OS**: Always use `pathlib.Path` for file system operations instead of `os.path`. EDA tools involve heavy file manipulation (RTL files, GDSII, logs, TCL scripts); `pathlib` ensures cross-platform reliability.

## 2. Modularity & Software Architecture
* **SOLID Principles**:
  * *Single Responsibility*: An agent should only do one thing (e.g., `ProgressiveCoder` writes code; `Verifier` tests code; `LibrelaneRunner` executes CLI).
  * *Dependency Inversion*: Depend on abstractions, not concretions. For LLMs and HLS tools, rely on Abstract Base Classes (ABCs).
* **Abstract Base Classes (ABCs)**: Use the `abc` module to define interfaces for swappable components.
  * *Example*: `class BaseLLM(ABC):` must define abstract methods like `generate()`. `OpenAILLM` and `LocalOllamaLLM` will inherit and implement this.
  * *Example*: `class BaseHLSCompiler(ABC):` must define `synthesize()`.
* **State Management**: AI agents maintain complex states (chat histories, implementation plans). Encapsulate agent state within isolated context objects (e.g., using `pydantic` models) rather than using global variables or deeply nested dictionaries.
* **Configuration Management**: Hardcoding is strictly prohibited. All model parameters, LLM API keys, HLS tool paths, and Librelane constraints must be loaded from a configuration file (YAML or TOML) parsed via a centralized settings manager (e.g., `pydantic-settings`).

## 3. EDA-Specific Development Practices
* **Subprocess Execution & Tool Wrapping**:
  * EDA workflows require calling external binaries (Stratus HLS, Yosys, OpenROAD via Librelane). Always use the `subprocess` module with explicit `timeout` arguments to prevent hanging processes.
  * Capture `stdout` and `stderr` streams independently.
  * Always check return codes (`process.returncode == 0`). If a tool fails, wrap the standard error in a custom Python exception.
* **Non-Destructive File Generation**:
  * When an agent generates RTL, C++, or TCL scripts, always write to a sandboxed, timestamped build directory (e.g., `builds/run_YYYYMMDD_HHMMSS/`).
  * Never overwrite original user specifications or base constraints.
* **Regex and Abstract Syntax Trees (AST)**:
  * When modifying large C++ or Verilog files (like the 20-asterisk replacement rule for sub-functions), prefer dedicated AST parsers (like `pycparser` or `tree-sitter`) over complex Regex if possible. If Regex must be used, compile the patterns globally and comment them extensively.
* **Idempotency**: EDA scripts (like TCL generators) must be idempotent. Running the `LibrelaneManager.generate_tcl()` method twice with the same inputs must yield the exact same file hash.

## 4. AI & Agent Integration Best Practices
* **LLM API Agnosticism**: The core system must never import `openai` or `anthropic` directly into functional logic. Use an intermediary wrapper layer (like `litellm` or a custom proxy class) so the backend can route to local or cloud models interchangeably.
* **Prompt Separation**: Do not hardcode large system prompts inside Python execution files. Store prompts as template files (e.g., `.jinja2` or `.txt`) in a dedicated `prompts/` directory. Load and inject variables at runtime.
* **Defensive Parsing**: LLM outputs are inherently unpredictable. When expecting JSON or specific code blocks from an agent:
  * Use robust stripping algorithms (e.g., removing markdown ````python` wrappers).
  * Validate the output structure using `pydantic` before passing it to the next EDA stage.

## 5. Error Handling & Reflection Logging
* **Custom Exception Hierarchy**: Define specific exceptions for the hardware flow:
  * `Spec2RTLError(Exception)` (Base)
  * `LLMRateLimitError(Spec2RTLError)`
  * `HLSSynthesisFailedError(Spec2RTLError)`
  * `PhysicalDesignRoutingError(Spec2RTLError)`
* **Structured Logging**: Use the `logging` module. Console logs should be readable for the user (`INFO` level), but file logs must be highly detailed (`DEBUG` level), including raw LLM prompts, tool CLI arguments, and execution times.
* **Reflection Payload**: When an HLS or RTL tool fails, the error handler must format the stack trace and stdout into a clean, truncated payload designed specifically to be fed back into the `ReflectionAgent` for debugging.

## 6. Testing & Validation
* **Unit Testing (Pytest)**: All utility functions and text parsers must have 100% test coverage using `pytest`.
* **Mocking External Tools**: Do not run actual LLM API calls or heavy HLS synthesis during basic unit tests. Use `unittest.mock` to mock tool return codes, API responses, and file outputs.
* **Integration Tests**: Maintain a separate suite of integration tests that perform a dry-run of the end-to-end pipeline using a tiny, dummy specification document.