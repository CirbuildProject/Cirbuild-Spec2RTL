# Implementation Plan v0.2: Spec2RTL/py Future Enhancements

This document outlines the technical design, chosen dependencies, and implementation strategy for adding stateful memory modules, a human-in-the-loop advisor agent, and a native web GUI to the Spec2RTL/py framework.

## 1. Agentic Memory Modules (DONE)

### Objective
Enhance the pipeline with statefulness to overcome context window limitations, particularly enabling the HLS Reflection Engine to learn from past compilation errors and fixes without relying on Reinforcement Learning.

### Dependencies
- **Vector Database**: `chromadb` - Easily embeddable, lightweight, and Python-native.
- **Data Schemas**: `pydantic` - To enforce strict schema validation for the "Error -> Fix" pairs.

### Implementation Steps
1.  **Short-Term Memory Manager:**
    -   *Design*: Introduce a context-pruning utility within the agent orchestration layer.
    -   *Action*: Clear non-essential conversational history at the start of each new synthesis loop. Only retain the original hardware specification and the context of the current module iteration to save tokens and prevent LLM confusion.
2.  **Long-Term Memory (HLS Fix Database):**
    -   *Design*: Instantiate a ChromaDB persistent client pointing to a local `memory/` directory.
    -   *Action*: When the HLS Reflection Engine successfully resolves a compilation error (e.g., Google XLS scheduling error or Bambu syntax failure), it serializes the error stack trace and the code diff of the fix into a JSON format.
    -   *Retrieval*: On subsequent HLS failures, the Reflection Engine will perform a similarity search in ChromaDB. If an embedding matches with high cosine similarity, the agent will inject the historical fix strategy into its prompt context.

## 2. Advisor / Supervisor Agent (Human-in-the-Loop)

### Objective
Provide a pipeline intercept module allowing users to pause the automated flow and interrogate the generated logic. This feature adds immense educational value for students learning IC design.

### Dependencies
- **Agent Framework**: `autogen` - Leveraging the native `UserProxyAgent` class.
- **CLI Interaction**: `rich` - For rendering formatted terminal-based Q&A and code snippets during the pause.

### Implementation Steps
1.  **Pipeline Intercept Module:**
    -   *Design*: Create an `AdvisorProxy` class inheriting from AutoGen's `UserProxyAgent`.
    -   *Action*: Configure the proxy to trigger during specifically defined breakpoints (e.g., after initial C++ generation, or if the HLS loop fails more than 3 consecutive times).
2.  **Interactive Q&A Mode:**
    -   *Design*: When intercepted, the standard pipeline execution suspends.
    -   *Action*: The user can ask questions like "Why did you generate this specific Error Correction Code module?" The agent will use the intermediate generated code as context to explain its architectural decisions. Once satisfied, the user can manually resume the execution.

## 3. GUI and Natural Language Translator

### Objective
Make the toolchain accessible to non-CLI users through a clean web interface while avoiding over-engineered JS setups ("GUI Trap"). Additionally, implement a fast, cost-effective interpreter for simple commands.

### Dependencies
- **Web UI**: `streamlit` - A Python-native framework ideal for spinning up reactive data and automation tool UIs quickly.
- **Parsing Math/Logic**: Python standard libraries `re` (Regex) and `ast` (Abstract Syntax Tree).

### Implementation Steps
1.  **Streamlit Control Panel:**
    -   *Design*: Create an entry point `gui_app.py`.
    -   *Action*: Map Spec2RTL pipeline parameters directly to Streamlit widgets. This includes a file upload widget for the PDF specifications, dropdowns for HLS backends, and a live-updating terminal output console to stream the generation logs natively in the browser.
2.  **NL Scripting Translator:**
    -   *Design*: Implement a lightweight `LocalParser` module for simple intent classification.
    -   *Action*: Use `re` and/or `ast` to map simple string inputs (e.g., "build memory controller") into CLI execution arguments or Python function calls cleanly, circumventing the need to hit LLM APIs for basic routing.
    -   *Fallback*: If the input complexity exceeds static parsing rules, the prompt will fallback smoothly to an LLM for interpretation.
