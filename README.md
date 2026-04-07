<div align="center">

# Cirbuild-Spec2RTL/py

![Version](https://img.shields.io/badge/Cirbuild--Spec2RTL%2Fpy_ver.-V0.1.1-007EC6?style=for-the-badge)
[![License](https://img.shields.io/badge/License-MIT-4CAF50?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/downloads/)

**An API-Agnostic, Multi-Agent Pipeline for Automated Hardware Synthesis**

*Translates natural language hardware specifications into synthesizable RTL (Verilog) via LLM-driven HLS — without hardcoding any LLM provider or HLS compiler.*

</div>

---

## 📌 Overview & Motivation

Hardware description is a high-skill bottleneck that forces RTL engineers to manually translate behavioral intent into synthesizable code. Spec2RTL/py automates this translation by running a structured, multi-agent LLM pipeline: a specification is read in plain text or PDF, decomposed into sub-functions, progressively coded through Pseudocode → Python → C++, verified with a g++ testbench, and finally passed through a High-Level Synthesis compiler to produce RTL.

The pipeline is designed to be a **subsystem module for [CirbuildSTG](https://github.com/CirbuildProject/CirbuildSTG)** — the broader Spec-to-GDSII design assistant — but is fully usable as a standalone library or CLI tool.

**Pipeline at a glance:**

```
PDF / Text Spec
      │
      ▼
  Module 1: Understanding
  (Summarize → Decompose → Describe → Verify)
      │
      ▼
  Module 2: Progressive Coding
  (Pseudocode → Python → C++ → Testbench)
      │
      ▼
  Module 2.5: Logical Verification  ───► Module 3: Reflection (on failure)
  (g++ compile + execute testbench)       (Analyze → Decide → Re-route)
      │
      ▼
  Module 4: HLS Optimization & Synthesis
  (Deterministic formatting → LLM optimizer → HLS compiler)
      │
      ▼
  Module 4.5: HLS Reflection (on synthesis failure)
  (Patch C++ → Learn new constraint → Retry)
      │
      ▼
      RTL (Verilog)
```

> **Acknowledgment:** This implementation is based on the original [Spec2RTL-Agent paper](https://arxiv.org/abs/2506.13905). Full credit to the original authors for pioneering LLM-driven RTL generation pipelines.

---

## 🏗️ Key Design Decisions & Trade-offs

**1. Dual agnosticism: LLM provider and HLS compiler are fully swappable.**
Rather than coupling to a single model API (e.g., OpenAI) or a single synthesis backend (e.g., Vivado), the entire pipeline routes through [`litellm`](https://docs.litellm.ai/) and a unified `AbstractHLSTool` interface. Switching from Google XLS to Bambu, or from Minimax to Gemini, requires only a one-line YAML change. The trade-off is a thin abstraction layer on top of each backend, but this cost is trivial against the flexibility gained.

**2. Deterministic HLS formatting before the LLM optimizer.**
HLS pragmas (`#pragma hls_top`, `#pragma hls_unroll yes`) and type mappings (`uint8_t` → `ap_uint<8>` for Vitis) are injected by a pure Python/regex pass (Module 4, Stage 0) *before* the LLM optimizer sees the code. This eliminates hallucination risk for mechanical formatting. The alternative — asking the LLM to manage pragmas — was observed to cause Dead Code Elimination (DCE) in Google XLS when the top-function pragma was misplaced or absent.

**3. Schema-driven top-module resolution.**
The `DecompositionPlan` Pydantic schema carries an `is_top_module: bool` flag on each `SubFunction`. This is resolved in Module 1 and propagated through to the HLS formatter deterministically. The legacy heuristic (regex pattern-matching on function names) is preserved behind a feature flag (`LEGACY_TOP_MODULE_HEURISTIC = False`) for debugging.

---

## 🚦 Project Status

- [x] **Completed:** Core 4+1 module pipeline (Understanding → Coding → Reflection → HLS → HLS Reflection)
- [x] **Completed:** Dual-loop fault-tolerant LLM client with provider fallback and retry backoff
- [x] **Completed:** Deterministic HLS formatting pass (pragma injection, type mapping, loop pragmas)
- [x] **Completed:** Schema-driven top-module detection (Phase 3.2 hardening)
- [x] **Completed:** Logical verification harness (g++ compile + testbench execution hard-gate)
- [x] **Completed:** ChromaDB-backed long-term memory for cross-session error-fix learning
- [x] **Completed:** DFG interface bit-width validation (warns on signal type mismatches)
- [x] **Completed:** `clean_llm_json` JSON sanitizer (strips markdown fences before Pydantic validation)
- [x] **Completed:** Pytest battery — 41/43 tests pass (2 pre-existing config test stubs)
- [ ] **In Progress:** CirbuildSTG integration as live subsystem module
- [ ] **Planned:** Vitis HLS backend (type mapping complete; synthesis runner pending)
- [ ] **Planned:** Advisor/Supervisor human-in-the-loop intercept agent
- [ ] **Planned:** Streamlit/Gradio GUI front-end

---

## 🛠️ Tech Stack

| Layer | Library / Tool | Version | Role |
|---|---|---|---|
| **LLM Interface** | [LiteLLM](https://docs.litellm.ai/) | `>=1.0.0` | Unified API for 100+ providers (OpenRouter, Gemini, Anthropic, Ollama, …) |
| **Data Validation** | [Pydantic](https://docs.pydantic.dev/) v2 | `>=2.0.0` | Schema enforcement for all inter-module data contracts |
| **Settings** | [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) | `>=2.0.0` | YAML + env-var configuration with `SPEC2RTL_` prefix override |
| **Prompt Templating** | [Jinja2](https://jinja.palletsprojects.com/) | `>=3.0.0` | All LLM prompts rendered from version-controlled `.jinja2` templates |
| **PDF Parsing** | [pypdfium2](https://pypdfium2.readthedocs.io/) | `>=4.0.0` | Spec extraction from PDF documents |
| **Configuration** | [PyYAML](https://pyyaml.org/) | `>=6.0` | Human-readable YAML config files |
| **Long-Term Memory** | [ChromaDB](https://www.trychroma.com/) | optional | Embedding-based vector store for persistent HLS error-fix learning |
| **HLS Backend (default)** | [Google XLS](https://google.github.io/xls/) via Docker | `cirbuild-xls:v1` | C++ → Verilog HLS synthesis |
| **HLS Backend (alt)** | [Bambu](https://bambu-hls.com/) | PandA framework | Open-source GCC-based HLS |
| **Verification** | g++ (system) | any | C++ testbench compilation and execution |
| **Testing** | [pytest](https://pytest.org/) | `>=7.0.0` | 43-test battery |
| **Dev IDE** | Antigravity agentic IDE / Kilo Code (VS Code) | — | Claude Sonnet 4.6, Minimax M2.5 |

**Primary LLM (default config):** `openrouter/minimax/minimax-m2.5`
**Fallback chain:** `gemini-3.1-flash-lite-preview` → `gemini-3-flash-preview` → `deepseek-v3.2` → `kimi-k2.5`

---

## 🏛️ Architecture

```text
spec2rtl/
├── agents/          # Module 1–4 orchestrators (understanding → coding → reflection → HLS)
├── config/          # Pydantic-settings config + default_config.yaml
├── core/            # Shared data models (Pydantic), exceptions, logging
├── hls/             # AbstractHLSTool interface + XLS / Bambu backends + HLS Reflection (4.5)
├── llm/             # Fault-tolerant LiteLLM client (retry, fallback, JSON sanitization)
├── memory/          # ChromaDB long-term memory for error-fix pairs
├── prompts/         # Jinja2 prompt templates for all agents
├── tests/           # Pytest battery
├── utils/           # PDF parser, code_utils (clean_llm_json, patch_xls_headers), hls_formatter
└── pipeline.py      # End-to-end orchestrator (Modules 1–4)
```

### Module Responsibilities

| Module | Input | Output | Key Mechanism |
|---|---|---|---|
| **1: Understanding** | Raw spec text / PDF pages | `DecompositionPlan` + `StructuredInfoDict[]` | 4-stage agent chain: Summarize → Decompose → Describe → Verify |
| **2: Coding** | `StructuredInfoDict[]` | `SubFunctionResult[]` (pseudocode + Python + C++) | Progressive 3-level chain; signature-only context to prevent ballooning |
| **2.5: Verification** | C++ + testbench | Pass/fail + exec log | `g++ -fsyntax-only` → g++ compile + execute; hard-gates Module 4 |
| **3: Reflection** | `GenerationTrajectory` | `ReflectionDecision` (4 paths) | LLM error analysis → route to re-generate / retry / human escalation |
| **4: HLS Optimization** | Combined C++ | `HLSSynthesisResult` | Stage 0: deterministic format → Stage 1: LLM optimizer → Stage 2: synthesis |
| **4.5: HLS Reflection** | C++ + synthesis error log | Fixed C++ + updated constraints | LLM recovery + ChromaDB memory store |

---

## 🚀 Installation Guide

### Prerequisites

- OS: Linux (recommended) / macOS
- Python: `>= 3.12`
- Docker (required for Google XLS HLS backend)
- g++ (for testbench verification — usually pre-installed on Linux)

### Option 1: Install via pip

```bash
# Install directly from GitHub
pip install git+https://github.com/CirbuildProject/Cirbuild-Spec2RTL.git@main

# Or editable for development
git clone https://github.com/CirbuildProject/Cirbuild-Spec2RTL.git
cd Cirbuild-Spec2RTL
pip install -e .
pip install -e ".[dev]"   # + pytest
```

### Option 2: Quickstart with automatic launch script

For a one-click setup that always pulls the latest version:

**Linux/macOS — `start.sh`:**
```bash
#!/bin/bash
echo "🚀 Initializing Spec2RTL Environment..."

if [ ! -d "venv" ]; then
    echo "📦 Creating a fresh virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate
pip install --upgrade pip setuptools wheel

echo "🔄 Fetching the latest Spec2RTL from remote..."
pip install --upgrade --force-reinstall --no-cache-dir \
    git+https://github.com/CirbuildProject/Cirbuild-Spec2RTL.git@main

echo "✨ Ready. Run: spec2rtl --spec /path/to/spec.pdf"
```

*Run `chmod +x start.sh` first, then `./start.sh`.*

---

### Configuration & API Keys

Spec2RTL uses **provider-specific API keys** so that primary and fallback models can use different providers without rate-limit conflicts.

#### How Key Selection Works

| Model prefix | Key used |
|---|---|
| `openrouter/...` | `SPEC2RTL_OPENROUTER_KEY` |
| `gemini/...` | `SPEC2RTL_GEMINI_KEY` |
| `anthropic/...` | `SPEC2RTL_ANTHROPIC_KEY` |

#### Quick `.env` Setup

```bash
cat > .env << 'EOF'
# At minimum, set the key for your primary model's provider
SPEC2RTL_OPENROUTER_KEY="sk-or-v1-your-openrouter-key-here"
SPEC2RTL_GEMINI_KEY="AIza-your-gemini-key-here"         # optional fallback
SPEC2RTL_ANTHROPIC_KEY="sk-ant-your-anthropic-key-here" # optional fallback

# Optional overrides (defaults shown)
SPEC2RTL_DEFAULT_MODEL="openrouter/minimax/minimax-m2.5"
SPEC2RTL_HLS_COMPILER="google_xls"
SPEC2RTL_BUILD_DIR="builds"
SPEC2RTL_LOG_LEVEL="INFO"
EOF
```

**Configuration priority:** env vars → `default_config.yaml` → code defaults.

#### All Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SPEC2RTL_OPENROUTER_KEY` | Yes* | — | API key for `openrouter/` models |
| `SPEC2RTL_GEMINI_KEY` | Yes* | — | API key for `gemini/` models |
| `SPEC2RTL_ANTHROPIC_KEY` | Yes* | — | API key for `anthropic/` models |
| `SPEC2RTL_DEFAULT_MODEL` | No | `openrouter/minimax/minimax-m2.5` | Primary LLM |
| `SPEC2RTL_HLS_COMPILER` | No | `google_xls` | HLS backend |
| `SPEC2RTL_BUILD_DIR` | No | `builds` | Output directory |
| `SPEC2RTL_LOG_LEVEL` | No | `INFO` | Logging verbosity |
| `SPEC2RTL_MAX_REFLECTION_CYCLES` | No | `3` | Max reflection retries per sub-function |

> *Set at minimum the key for your primary model's provider.

---

### Set up the Google XLS Docker Environment

The default HLS backend runs inside a Docker container so you don't need to compile XLS from source.

#### Option A: Pull the Pre-built Image (Fastest)
```bash
docker pull cirbuildproject/cirbuild-xls:v1
docker tag cirbuildproject/cirbuild-xls:v1 cirbuild-xls:v1
```

#### Option B: Build from Source (Developers)
```bash
# From the CirbuildSTG root (contains the Dockerfile)
docker build -t cirbuild-xls:v1 .
# ⚠ Takes 15 min – several hours depending on hardware (Bazel build)
```

---

## 💻 Usage

### CLI

```bash
# From a PDF spec
spec2rtl --spec /path/to/spec.pdf

# From raw text
python -m spec2rtl --spec /path/to/spec.txt --text
```

### Python API

```python
from spec2rtl.pipeline import Spec2RTLPipeline
from pathlib import Path

pipeline = Spec2RTLPipeline()

# From PDF
result = pipeline.run(Path("my_spec.pdf"))

# From text (e.g., embedded in another application)
result = pipeline.run_from_text("Design a 32-bit ALU that supports ADD, SUB, AND, OR, XOR...")

# From structured JSON (used by CirbuildSTG)
result = pipeline.run_from_json({
    "module_name": "ALU32",
    "description": "32-bit ALU ...",
    "inputs": {"a": "uint32_t", "b": "uint32_t", "op": "uint3_t"},
    "outputs": {"result": "uint32_t", "zero": "bool"},
    "behavior": "...",
    "constraints": [],
    "classification": "COMBINATIONAL"
})

if result.success:
    print(f"RTL at: {result.rtl_output_path}")
```

### Scripting Guide

The pipeline is designed for programmatic integration. Key attributes of `HLSSynthesisResult`:

| Field | Type | Description |
|---|---|---|
| `success` | `bool` | Whether synthesis completed |
| `rtl_output_path` | `str \| None` | Path to generated Verilog |
| `module_name` | `str` | Name of the generated module |
| `log_summary` | `str` | Summary of synthesis log |
| `error_log` | `str \| None` | Error details if failed |

---

## 🔍 Interpreting Error Logs

Logs are written to the `logs/` directory. When errors occur:

- **Module 1–3 Errors:** Usually LLM JSON formatting failures or schema mismatches. Check the log for `JSONSchemaValidationError` — the pipeline retries up to 3× with fallback models automatically.
- **Module 4 (HLS) Errors:** Handled by the HLS Reflection engine (Module 4.5). If max retries are exhausted, `hls_synthesis.log` will contain the raw C++ pragma or type error reported by Google XLS or Bambu.
- **Syntax/Logical Verification Failures:** Written to `builds/<run_id>/<func>_check.cpp` and `<func>_tb.cpp`. Re-run with `g++ -fsyntax-only` locally to reproduce.

---

## 🐛 Bug Reports

Report persistent issues, crashes, or feature requests to:
📧 **cirbuild_dev@proton.me**

Please include: relevant `.log` files, your `.env` configuration (redact API keys), your hardware spec, and Python/OS version.

---

## 🔮 Future Work & Architectural Pivots

- **Direct SystemVerilog Generation (HLS Deprecation Track):** Pivoting the primary educational pipeline away from High-Level Synthesis (e.g., Google XLS/Vitis) to direct SystemVerilog generation. HLS produces highly optimized but unreadable gate-level netlists, which violates the core product definition of providing human-readable, deterministic baselines for students. 
- **Concentric "Fast-Fail" Verification Loops:** Replacing monolithic verification passes with escalating computational loops to save LLM context windows and drastically reduce latency:
  - *Inner Loop (Milliseconds):* Syntax and semantic checks using ultra-fast linters (**Verible** or **Slang**).
  - *Middle Loop (Seconds):* Functional verification via Hardware Test-Driven Development (TDD) using **Cocotb** and **Verilator/Icarus**.
  - *Outer Loop (Minutes):* Physical design and timing constraints pushed to **Librelane** (Yosys/OpenROAD) only after logical verification passes.
- **Deterministic Testbench Harness (Echo-Chamber Prevention):** Engineer a strict, multi-stage prompt harness for the `cocotb` testbench agent. To prevent the LLM from generating flawed RTL and a flawed testbench that agrees with it, the pipeline will strictly separate intent extraction (JSON I/O mapping -> English logical invariants) from the final Python assertion generation.
- **CirbuildSTG Integration:** Full operation as a live subsystem module within the CirbuildSTG ecosystem.
- **Advisor / Supervisor Agent:** Human-in-the-loop intercept for high-complexity or unresolvable errors — intended as a learning platform for IC design students to manually unblock the agent.

---

## ⚠️ Disclaimer

This project is developed with the assistance of the **Antigravity** agentic IDE and Kilo Code extension (VS Code), utilizing Claude Sonnet 4.6, Minimax M2.5, and Gemini 3.1 Pro. All generated RTL should be manually verified before use in research publications or commercial applications. Architectural decisions, design intent, and progressive refinements reflect genuine human engineering judgment.
