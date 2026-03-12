<div align="center">

# Cirbuild-Spec2RTL/py

![Version](https://img.shields.io/badge/Cirbuild--Spec2RTL%2Fpy_ver.-V0.1-007EC6?style=for-the-badge)
[![License](https://img.shields.io/badge/License-MIT-4CAF50?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/downloads/)

**An API-Agnostic, Multi-Agent Framework for Hardware Synthesis**
</div>

## 📖 Overview
Spec2RTL/py is a fully automated, agentic toolchain that accelerates hardware design by translating natural language specifications and PDF documents directly into Register Transfer Level (RTL) code. Leveraging Large Language Models (LLMs) via the AutoGen framework, this tool systematically decomposes complex specifications, generates intermediate C++ implementations, verifies functional correctness, and synthesizes the code into optimized RTL using High-Level Synthesis (HLS) constraints. Additionally, this project will be integrated into CirbuildSTG as a subsystem module. The /py marker is a suffix to indicate that this is a Python implementation of the Spec2RTL toolchain.

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

## 💡 Acknowledgments
This software toolchain owes its foundational concepts to the original 
**Spec2RTL-Agent: Automated Hardware Code Generation from Complex Specifications Using LLM Agent Systems** (https://arxiv.org/abs/2506.13905) research paper. We extend our deepest gratitude and full credit to the original authors of Spec2RTL for their pioneering contributions to LLM-driven hardware generation and automated RTL synthesis loops.

## 🚀 Installation Guide

### Prerequisites
*   OS: Linux (Recommended)
*   Python: `>= 3.12`
*   Docker (if using the Google XLS HLS backend container)
*   HLS Compilers (e.g., Google XLS, Bambu)

### 1. Clone & Setup Environment
```bash
# Clone the repository
git clone https://github.com/CirbuildProject/Cirbuild-Spec2RTL.git
cd Cirbuild-Spec2RTL

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies (ensure pip is updated)
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Configuration & API Keys
Spec2RTL/py relies on [`litellm`](https://docs.litellm.ai/docs/) to remain completely API-agnostic. You can define your default target models inside `spec2rtl/config/default_config.yaml` or via environment variables.

Export your provider API keys directly to your environment:
```bash
export GEMINI_API_KEY="your_api_key_here"
export OPENAI_API_KEY="your_api_key_here"
export OPENROUTER_API_KEY="your_api_key_here"
```

## 📂 Repository Guide

Understanding the project structure:

```text
spec2rtl/
├── agents/             # AutoGen orchestrators (Modules 1-4)
├── config/             # Pydantic-based configuration and default YAMLs
├── core/               # Custom exceptions, logging config, and shared Data Models
├── hls/                # Abstract HLS interfaces and compiler backends (XLS, Bambu, Reflection)
├── llm/                # Dual-loop fault-tolerant API-agnostic LiteLLM client
├── prompts/            # Jinja2 prompt templates utilized by the agents
├── tests/              # Pytest battery assuring system integrity
├── utils/              # File handling, code extraction, multimodal PDF parsers
├── pipeline.py         # Main entry point and end-to-end execution script
└── ...
```

### Usage

Execute the pipeline via the CLI:
```bash
# Analyze a PDF specification
python -m spec2rtl --spec /path/to/spec.pdf

# Analyze a raw text specification
python -m spec2rtl --spec /path/to/spec.txt --text
```

### Scripting Guide

You can also integrate Cirbuild-Spec2RTL/py into your Python scripts for customized workflows:

```python
from spec2rtl.pipeline import run_pipeline
from spec2rtl.config import load_config

# Load configuration
config = load_config("spec2rtl/config/default_config.yaml")

# Run the hardware synthesis pipeline
result = run_pipeline(
    spec_path="/path/to/spec.pdf",
    module_name="my_hardware_module",
    config=config
)

if result.success:
    print(f"RTL generated successfully at {result.output_dir}")
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

*   **Agentic Memory Modules**: 
    *   *Short-Term Memory*: Explicitly structuring conversational history to retain only the current synthesis loop's context, saving tokens and reducing iterative confusion.
    *   *Long-Term Memory*: Implementing a lightweight, local Vector Database (e.g., ChromaDB or FAISS) to embed "Error -> Fix" generation pairs. This stateful learning capability will allow the HLS Reflection Engine to recall and apply past solutions to similar errors.
*   **Advisor / Supervisor Agent (Human-in-the-Loop)**: Introducing an interactive pipeline intercept module. This User Proxy agent will be triggered during high-complexity outputs or unresolvable HLS errors, allowing users to pause the flow and interrogate the generated logic. This feature aims to transform the toolchain into a hands-on learning platform for IC design students.
*   **GUI and Natural Language Translator**: 
    *   *Web Interface*: Transitioning to a Python-native framework like Streamlit or Gradio to spin up a reactive GUI without falling into the "GUI Trap" of over-engineering heavy frontend web frameworks.
    *   *NL Scripting Translator*: Developing an internal Python execution script translator using standard `re` libraries or AST parsing to map simple natural language commands to local execution scripts, serving as a low-latency alternative to expensive LLM API calls.

## ⚠️ Disclaimer

This project is completely written, debugged, and verified via the use of the **Antigravity** agentic IDE, utilizing models of Claude Opus 4.6 and Gemini 3.1 Pro. Any generated code through this pipeline should be manually verified before mission-critical use (e.g., research literature, commercial usage, etc.). The architectural considerations and progressive refinements are genuine human intent.
