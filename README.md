<div align="center">

# Cirbuild-Spec2RTL/py

![Version](https://img.shields.io/badge/Cirbuild--Spec2RTL%2Fpy_ver.-V0.1-007EC6?style=for-the-badge)
[![License](https://img.shields.io/badge/License-MIT-4CAF50?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/downloads/)

**An API-Agnostic, Multi-Agent Framework for Hardware Synthesis**

</div>

## 💡 Acknowledgments
This software toolchain owes its foundational concepts to the original 
**Spec2RTL-Agent: Automated Hardware Code Generation from Complex Specifications Using LLM Agent Systems** (https://arxiv.org/abs/2506.13905) research paper. We extend our deepest gratitude and full credit to the original authors of Spec2RTL for their pioneering contributions to LLM-driven hardware generation and automated RTL synthesis loops.

## 📖 Overview
Spec2RTL/py is a fully automated, agentic toolchain that accelerates hardware design by translating natural language specifications and PDF documents directly into Register Transfer Level (RTL) code. Leveraging Large Language Models (LLMs) via the AutoGen framework, this tool systematically decomposes complex specifications, generates intermediate C++ implementations, verifies functional correctness, and synthesizes the code into optimized RTL using High-Level Synthesis (HLS) constraints. Additionally, this project will be integrated into CirbuildSTG as a subsystem module. The /py marker is a suffix to indicate that this is a Python implementation of the Spec2RTL toolchain.

### What is Spec2RTL/py?

Spec2RTL/py is a **dual-agnostic** hardware synthesis framework:

1. **LLM Provider Agnostic**: Through [`litellm`](spec2rtl/llm/llm_client.py), the framework transparently supports over 100+ LLM providers (OpenAI, Google Gemini, Anthropic, OpenRouter, Azure OpenAI, local Ollama models, etc.) without code changes. Users configure their preferred model in a simple YAML file or environment variables.

2. **HLS Compiler Agnostic**: The framework abstracts HLS backend implementation through a unified [`HLSBackend`](spec2rtl/hls/base.py) interface, currently supporting:
   - **Google XLS**: High-performance HLS for cloud deployments
   - **Bambu**: Open-source HLS from the PandA framework
   - Extensible architecture for future compiler backends (Vitis HLS, Catapult, etc.)

3. **Agentic Memory**: Built upon the original framework, this implementation adds persistent learning to enhance cross-design abilities through:
   - **Long-Term Memory**: ChromaDB vector database storing error-fix pairs for cross-session learning
   - **Short-Term Memory**: Structured `GenerationTrajectory` objects capturing complete generation history

## 🚀 Innovations Beyond the Original Paper

This implementation extends the original Spec2RTL-Agent architecture with several key enhancements:

### 1. Hardware Classification Engine
Added automatic **combinational vs. sequential** hardware classification in Module 1, enabling:
- Optimized HLS constraint application
- Automatic pipeline stage detection
- Appropriate testbench generation

### 2. Agentic Memory Integration
- **ChromaDB-backed long-term memory** for persistent error-fix learning
- **Vector similarity search** to recall solutions to similar errors
- **Learned constraints extraction** to prevent recurring issues

### 3. Fault-Tolerant LLM Client
Built a **dual-loop, fault-tolerant API client** with:
- Automatic retry with exponential backoff
- Rate limiting handling
- Token usage tracking
- Unified response formatting across providers

## 🏛️ Architecture
The toolchain is divided into an intelligent, multi-stage pipeline:

*   **Module 1: Specification Understanding** 
    Extracts, summarises, and structures requirements from PDFs (including text and visual data like diagrams) into logical sub-functions.
*   **Module 2: Code Generation** 
    Utilizes a chain-of-thought approach (Pseudocode `->` Python `->` C++) alongside testbench generation to lay the groundwork for HLS.
*   **Module 3: Verification**
    Rigorously analyzes and tests the generated code, iteratively reflecting and fixing issues until the behavioral representation is flawless.
*   **Module 4: HLS Code Optimization & Conversion**
    Dynamically adheres to specific HLS compiler constraints (Google XLS, Bambu) to prepare the C++ code for synthesis.
*   **Module 4.5: HLS Reflection Engine**
    An advanced recovery loop that intercepts synthesis compilation failures, patches C++ code syntax or pragmas, and learns new constraints to prevent subsequent errors.

## 🚀 Installation Guide

### Prerequisites
*   OS: Linux (Recommended)
*   Python: `>= 3.12`
*   Docker (if using the Google XLS HLS backend container)
*   HLS Compilers (e.g., Google XLS, Bambu)

### Option 1: Install via pip (Recommended)
```bash
# Install directly from GitHub
pip install git+https://github.com/CirbuildProject/Cirbuild-Spec2RTL.git

# Or install in editable mode for development
pip install -e git+https://github.com/CirbuildProject/Cirbuild-Spec2RTL.git
```

### Option 2: Manual Setup
```bash
# Clone the repository
git clone https://github.com/CirbuildProject/Cirbuild-Spec2RTL.git
cd Cirbuild-Spec2RTL

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies (ensure pip is updated)
pip install --upgrade pip
pip install -e .

# Install dev dependencies for running tests
pip install -e ".[dev]"
```

### 2. Configuration & API Keys
Spec2RTL/py relies on [`litellm`](https://docs.litellm.ai/docs/) to remain completely API-agnostic. You can define your default target models inside `spec2rtl/config/default_config.yaml` or via environment variables(.env).

### 3. Set up the Google XLS Docker Environment

CirbuildSTG uses a containerized Google XLS toolchain for High-Level Synthesis (HLS) to save you from compiling the tools from source. You **must** have Docker installed and running before starting the pipeline. 

Choose **one** of the following methods to get the required `cirbuild-xls:v1` image:

#### Option A: Pull the Pre-built Image (Fastest)
If you just want to run the pipeline immediately, you can download the pre-compiled image directly from Docker Hub and tag it for local use:
```bash
# Pull the image from Docker Hub 
docker cirbuildproject/cirbuild-xls:v1

# Tag it so the CirbuildSTG backend can find it automatically
docker tag cirbuildproject/cirbuild-xls:v1 cirbuild-xls:v1
```
#### Option B: Build Directly from Source (For Developers)
If you prefer complete transparency or want to modify the XLS environment, you can build the image directly using the Dockerfile included in this repository. (Note: This process takes about 15-20 minutes upto a few hours as it compiles Google XLS via Bazel, depending on the hardware you are working on).
```bash
# Run this from the root of the CirbuildSTG directory
docker build -t cirbuild-xls:v1 .
```

---

### Using .env File for Configuration

For convenience, you can configure Spec2RTL using a `.env` file. When Spec2RTL is used as a dependency (e.g., within CirbuildSTG), it will automatically load the `.env` from the current working directory.

Spec2RTL uses **provider-specific API keys** so that primary and fallback models can use different providers without rate-limit conflicts. The correct key is selected automatically based on the model string prefix before each API call.

#### How Key Selection Works

| Model prefix | Key used |
|---|---|
| `openrouter/...` | `SPEC2RTL_OPENROUTER_KEY` |
| `gemini/...` | `SPEC2RTL_GEMINI_KEY` |
| `anthropic/...` | `SPEC2RTL_ANTHROPIC_KEY` |

This means if your primary model is `openrouter/minimax/minimax-m2.5` and your fallback is `gemini/gemini-2.5-flash`, the pipeline will automatically use `SPEC2RTL_OPENROUTER_KEY` for the primary call and `SPEC2RTL_GEMINI_KEY` for the fallback — no extra configuration needed.

#### Quick Setup (for standalone usage)

```bash
# Create a .env file in your project root
cat > .env << 'EOF'
# Provider API Keys — set only the ones you need
SPEC2RTL_OPENROUTER_KEY="sk-or-v1-your-openrouter-key-here"
SPEC2RTL_GEMINI_KEY="AIza-your-gemini-key-here"       # optional: only if using gemini/ fallback
SPEC2RTL_ANTHROPIC_KEY="sk-ant-your-anthropic-key-here" # optional: only if using anthropic/ fallback

# Model Selection (optional)
SPEC2RTL_DEFAULT_MODEL="openrouter/minimax/minimax-m2.5"

# HLS Compiler (optional)
SPEC2RTL_HLS_COMPILER="google_xls"
EOF
```

#### Configuration Priority

Configuration is resolved in this priority order:
1. **Environment variables** (`.env` file) ← Use this for API keys
2. **YAML config file** (`spec2rtl/config/default_config.yaml`)
3. **Code defaults**

#### All Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SPEC2RTL_OPENROUTER_KEY` | Yes* | — | API key for `openrouter/` models |
| `SPEC2RTL_GEMINI_KEY` | Yes* | — | API key for `gemini/` models (Google AI Studio) |
| `SPEC2RTL_ANTHROPIC_KEY` | Yes* | — | API key for `anthropic/` models |
| `SPEC2RTL_DEFAULT_MODEL` | No | `openrouter/minimax/minimax-m2.5` | Primary LLM model |
| `SPEC2RTL_HLS_COMPILER` | No | `google_xls` | HLS compiler |
| `SPEC2RTL_BUILD_DIR` | No | `builds` | Output directory |
| `SPEC2RTL_LOG_LEVEL` | No | `INFO` | Logging level |

> * At minimum, set the key for your primary model's provider. Set additional keys only if you configure fallback models from other providers.

> **Note:** For advanced customization (fallback models, retry counts, etc.), edit `spec2rtl/config/default_config.yaml` directly.

## 📂 Repository Guide

Understanding the project structure:

```text
spec2rtl/
├── agents/             # AutoGen orchestrators (Modules 1-4)
├── config/            # Pydantic-based configuration and default YAMLs
├── core/              # Custom exceptions, logging config, and shared Data Models
├── hls/               # Abstract HLS interfaces and compiler backends (XLS, Bambu, Reflection)
├── llm/               # Dual-loop fault-tolerant API-agnostic LiteLLM client
├── memory/            # ChromaDB-backed long-term memory for error-fix learning
├── prompts/           # Jinja2 prompt templates utilized by the agents
├── tests/             # Pytest battery assuring system integrity
├── utils/             # File handling, code extraction, multimodal PDF parsers
├── pipeline.py        # Main entry point and end-to-end execution script
└── ...
```

### Usage

Execute the pipeline via the CLI:
```bash
# Using the spec2rtl command (after pip install)
spec2rtl --spec /path/to/spec.pdf

# Or using Python module syntax
python -m spec2rtl --spec /path/to/spec.pdf

# Analyze a raw text specification
python -m spec2rtl --spec /path/to/spec.txt --text
```

### Scripting Guide

You can also integrate Cirbuild-Spec2RTL/py into your Python scripts for customized workflows:

```python
from spec2rtl.pipeline import Spec2RTLPipeline
from pathlib import Path

# Initialize the pipeline
pipeline = Spec2RTLPipeline()

# Run the hardware synthesis pipeline
result = pipeline.run(Path("/path/to/spec.pdf"))

if result.success:
    print(f"RTL generated successfully at: {result.rtl_output_path}")
else:
    print("Pipeline failed. Check the logs for details.")
```

## 🔍 Interpreting Error Logs

The toolchain generates detailed logs in the `logs/` directory. When an error occurs during synthesis or generation:
*   **Module 1-3 Errors**: Typically relate to LLM misinterpretations or code extraction failures. Check `generation.log` and ensure your PDF specification is clearly formatted.
*   **Module 4 (HLS) Errors**: These are handled by the Reflection Engine. If the system fails to recover, check `hls_synthesis.log` for the specific C++ pragma or syntax failure reported by the Google XLS or Bambu compilers.

## 🐛 Bug Reports

If you encounter persistent issues, unexpected crashes, or have feature requests, please report them to our development team. 

📧 Email bug reports to: **cirbuild_dev@proton.me**

Please include the relevant `.log` files, the configuration used, and the target hardware specification in your report.

## 🔮 Future Work

Future development will focus on the integration of Spec2RTL/py into **CirbuildSTG** as a subsystem module. This integration will allow the toolchain to operate directly within the broader CirbuildSTG ecosystem as a dedicated hardware synthesis component.

Additionally, the following enhancements are planned to improve the robustness and usability of the toolchain:

*   **Advisor / Supervisor Agent (Human-in-the-Loop)**: Introducing an interactive pipeline intercept module. This User Proxy agent will be triggered during high-complexity outputs or unresolvable HLS errors, allowing users to pause the flow and interrogate the generated logic. This feature aims to transform the toolchain into a hands-on learning platform for IC design students.
*   **GUI and Natural Language Translator**: 
    *   *Web Interface*: Transitioning to a Python-native framework like Streamlit or Gradio to spin up a reactive GUI without falling into the "GUI Trap" of over-engineering heavy frontend web frameworks.
    *   *NL Scripting Translator*: Developing an internal Python execution script translator using standard `re` libraries or AST parsing to map simple natural language commands to local execution scripts, serving as a low-latency alternative to expensive LLM API calls.

## ⚠️ Disclaimer

This project is completely written, debugged, and verified via the use of the **Antigravity** agentic IDE and Kilo Code Extension in VS Code IDE, utilizing models of Claude Opus 4.6, Gemini 3.1 Pro, and Minimax M2.5. Any generated code through this pipeline should be manually verified before mission-critical use (e.g., research literature, commercial usage, etc.). The architectural considerations and progressive refinements are genuine human intent.
