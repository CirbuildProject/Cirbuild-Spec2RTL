<div align="center">

# Cirbuild-Spec2RTL/py

![Version](https://img.shields.io/badge/spec2rtl%2Fpy_ver.-V0.1-007EC6?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-4CAF50?style=for-the-badge)
![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)

**An API-Agnostic, Multi-Agent Framework for Hardware Synthesis**
</div>

## 📖 Overview
Spec2RTL/py is a fully automated, agentic toolchain that accelerates hardware design by translating natural language specifications and PDF documents directly into Register Transfer Level (RTL) code. Leveraging Large Language Models (LLMs) via the AutoGen framework, this tool systematically decomposes complex specifications, generates intermediate C++ implementations, verifies functional correctness, and synthesizes the code into optimized RTL using High-Level Synthesis (HLS) constraints.

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
This software toolchain owes its foundational concepts to the original **Spec2RTL** research paper. We extend our deepest gratitude and full credit to the original authors of Spec2RTL for their pioneering contributions to LLM-driven hardware generation and automated RTL synthesis loops.

## 🚀 Installation Guide

### Prerequisites
*   OS: Linux (Recommended)
*   Python: `>= 3.12`
*   Docker (if using the Google XLS HLS backend container)
*   HLS Compilers (e.g., Google XLS, Bambu)

### 1. Clone & Setup Environment
```bash
# Clone the repository
git clone https://github.com/your-repo/spec2rtl.git
cd spec2rtl

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
python -m spec2rtl.pipeline --spec /path/to/spec.pdf --module my_hardware_module
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
