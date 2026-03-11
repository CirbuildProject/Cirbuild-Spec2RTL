# Spec2RTL-Agent: Backend Architecture & Implementation Guidelines

## 1. System Overview
The backend software implements the Spec2RTL-Agent framework, an automated multi-agent system designed to directly process complex, unstructured hardware specification documents and generate fully functional Register Transfer Level (RTL) code. To meet custom requirements, the software is fully modular, written in Python, API/compiler agnostic, and features a direct integration interface for the Librelane open-source RTL-to-GDSII EDA tool.

## 2. Core Architecture & Datapaths
The system is divided into four primary modules as outlined in the literature, plus a fifth module for physical design integration.

### Module 1: Iterative Understanding and Reasoning
* **Objective**: Transform unstructured, lengthy specification documents (PDFs with text, figures, equations) into a structured, step-by-step implementation plan.
* **Datapath**: Raw Spec Document $\rightarrow$ Summaries $\rightarrow$ Decomposed Sub-Functions $\rightarrow$ Structured Information Dictionary.
* **Agents Involved**:
  * **Understanding/Summarization Agent**: Generates concise summaries for each section of the original document to reduce complexity.
  * **Decomposer Agent**: Takes summaries and the original document to organize the target implementation into a sequence of sub-functions.
  * **Description Agent**: Collates necessary info (inputs, outputs, functionality, references) into a structured dictionary.
  * **Verifier**: Reviews the dictionary and provides feedback to ensure complete and precise details.

### Module 2: Progressive Coding and Prompt Optimization
* **Objective**: Sequentially implement each sub-function based on the decomposition plan, using cross-level code referencing.
* **Datapath**: Structured Dictionary $\rightarrow$ Pseudocode $\rightarrow$ Python $\rightarrow$ Synthesizable C++.
* **Agents Involved**:
  * **Progressive Coders (Pseudo Coder, Python Coder, C++ Coder)**: Sequentially draft implementations, using higher-level code as a reference for lower-level generation.
  * **Verifier**: Assesses accuracy using derived test cases or self-validation against specs, suggesting revisions or complete regenerations.
  * **Prompt Optimizer Agent**: Analyzes the implementation log for the current sub-function and refines the prompts used by the Coder to enhance accuracy and efficiency.

### Module 3: Adaptive Reflection Module
* **Objective**: Dynamically identify and trace the sources of errors across all generated sub-functions to ensure robustness.
* **Datapath**: Failed Verification Logs $\rightarrow$ Error Source Analysis $\rightarrow$ Strategic Routing Action.
* **Agents Involved**:
  * **Analysis Agent**: Reviews the entire generation trajectory to propose potential error locations.
  * **Reflection Agent**: Determines the next action based on four routing paths:
    * **Path 1**: Return to Module 1 to revise instructions if the error originates from incorrect instructions.
    * **Path 2**: Return to previous sub-functions if they are the source of the error.
    * **Path 3**: Restart generation within Module 2 if the error is confined to the current sub-function.
    * **Path 4**: Escalate to human intervention if the error source is unclear.

### Module 4: Code Optimization and Conversion (Agnostic HLS)
* **Objective**: Reformat the C++ implementation to comply with HLS constraints, then synthesize to RTL.
* **Datapath**: Final C++ Code $\rightarrow$ Optimized C++ $\rightarrow$ Synthesized RTL.
* **Agents & Components Involved**:
  * **Code Optimizer Agent**: Adapts the C++ code to meet HLS constraints (e.g., data format restrictions, static memory usage).
  * **Agnostic HLS Wrapper**: An abstracted interface that compiles the optimized C++ into Verilog/SystemVerilog, supporting both open-source (e.g., Bambu) and proprietary tools (e.g., Stratus HLS, Vitis HLS).

### Module 5: Librelane Integration (Custom Requirement)
* **Objective**: Pass the generated, verified RTL directly into a physical design flow.
* **Datapath**: Synthesized RTL $\rightarrow$ Librelane Configuration Generation $\rightarrow$ Librelane Flow Execution $\rightarrow$ GDSII Layout.
* **Components Involved**:
  * **Librelane Interface Manager**: A dedicated Python class that writes the necessary `.tcl` or `.json` configuration files required by Librelane, invokes the toolchain as a subprocess, and parses the physical design logs (PPA metrics).

## 3. Software Requirements & System Constraints
To fulfill the specific engineering guidelines, the backend must be constructed under the following parameters:

### Language & Modularity:
* The entire backend must be written in Python to ensure AI compatibility.
* Agent interactions and tool usage should be managed using a multi-agent framework, mimicking the AutoGen implementation referenced in the architecture.
* Partial code replacement logic must be implemented using a rule-based approach (e.g., locating sub-functions marked with 20 asterisks) to bypass LLM output length limits.

### LLM API Agnosticism:
* Implementation must utilize an abstraction layer (such as LiteLLM or an internal wrapper) so the underlying model can be swapped seamlessly between cloud models (GPT-4o, Claude 3.5, Gemini) and local models (Llama 3, Qwen) via a single configuration file.

### PDF Extraction Interface:
* A multimodal parsing utility must be implemented using PyPDF for text extraction and a screenshot utility for capturing multi-modal tables and figures.

### HLS Compiler Agnosticism:
* Design an `AbstractHLSTool` base class containing methods like `synthesize()`, `get_constraints()`, and `parse_logs()`.
* Subclass this for specific tools (e.g., `StratusHLSTool`, `BambuHLSTool`). The Code Optimizer Agent will dynamically query `get_constraints()` to format the C++ accurately for the active compiler.

### Librelane RTL-to-GDSII Interface:
* A dedicated module `librelane_runner.py` must be written to accept the RTL output directory, automatically generate pin constraints and timing constraints, and execute the physical design steps.