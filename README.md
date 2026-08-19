# AI-Driven RTL Design and Verification Assistant

An AI-assisted RTL workflow that turns natural-language hardware intent into structured specifications, AI-generated design artifacts, deterministic testbench structure, and tool-backed verification.

The project is built around one core idea:

```text
LLM outputs are untrusted.
Deterministic tools and reference logic are authoritative.
```

## Why This Project

LLMs are useful for:

- extracting structure from hardware requirements
- proposing RTL
- proposing verification intent

But they are not trusted as correctness oracles. This repository combines local AI assistance with deterministic EDA tools and deterministic reference logic so that unsupported or invalid outputs fail safely instead of being guessed through.

## Current Architecture

```text
Natural Language Requirement
        ↓
AI Requirement Parser
        ↓
Clarification / HardwareSpec
        ↓
AI RTL Generator
        ↓
AI Verification Planning
        ↓
Deterministic Expected-Value / Reference Layer
        ↓
Deterministic Testbench IR + Renderer
        ↓
Icarus / Verilator / Yosys
        ↓
Verification Report
```

Current trust boundary:

```text
AI may reason about what to build and what to test.
Deterministic code decides how those structured results are validated and executed.
```

Practical stage split:

```text
AI-dependent:
Requirement → HardwareSpec
HardwareSpec → RTL
HardwareSpec → VerificationPlan

Deterministic:
VerificationPlan → Testbench IR → SystemVerilog testbench
RTL + testbench → lint / simulation / synthesis
```

Future work will add richer failure classification and repair loops, but those are not complete yet.

## Current Progress

Completed:

- project setup and modular architecture
- manual SystemVerilog RTL examples and self-checking testbenches
- VCD waveform generation and GTKWave-friendly debugging
- Python simulation automation
- typed simulation, lint, synthesis, and unified verification reports
- Verilator lint integration
- Yosys synthesis integration
- unified deterministic verification pipeline
- structured `HardwareSpec`
- local Ollama provider integration
- AI requirement parsing
- ambiguity clarification handling
- AI RTL generation
- AI verification-plan generation
- deterministic expected-value/reference correction for supported semantics

In progress:

- Step 14 deterministic testbench rendering generalization and regression hardening

Upcoming:

- richer independent reference models
- failure classification
- AI repair loop
- storage / API / frontend work
- benchmarking and evaluation
- optional formal / FPGA extensions later

## Trust Model

This repository intentionally separates:

- AI-generated intent
- deterministic execution and validation

Practical implications:

- `HardwareSpec` validation is authoritative for specification structure.
- deterministic reference logic is authoritative for supported expected-value semantics.
- deterministic testbench rendering is authoritative for final SystemVerilog testbench structure.
- Verilator, Icarus Verilog, and Yosys remain authoritative for tool-backed verification.
- unsupported semantics fail explicitly instead of being approximated confidently.

## Supported Examples

Current example set includes:

- 2:1 mux
- 4-bit ALU
- 4-bit synchronous counter
- 3-to-8 decoder
- 4-bit shift register

Today, manually written RTL/testbenches are present for the mux, ALU, and counter examples. Structured `HardwareSpec` examples are also present for decoder and shift register work used by the newer AI/deterministic generation layers.

## Repository Structure

```text
src/rtl_assistant/
  hardware_tools/
  llm/
  models/
  pipeline/
  reference/
  rtl/
  spec/
  testbench/
  verification_plan/

scripts/
  check_environment.py
  generate_rtl.py
  generate_testbench.py
  generate_verification_plan.py
  parse_requirement.py
  run_lint.py
  run_simulation.py
  run_synthesis.py
  test_llm.py
  validate_spec.py
  verify_rtl.py

examples/
  mux_2to1/
  alu_4bit/
  4bit_counter/
  specs/

reports/
generated/
docs/
```

## Installation

### Python

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Windows Git Bash:

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### macOS

Install the local tools with Homebrew:

```bash
brew install icarus-verilog verilator yosys ollama
```

### Windows

Current Windows strategy is:

- Python runs natively on Windows
- Icarus Verilog / `vvp` run natively on Windows
- Verilator runs through WSL
- Yosys runs through WSL

That means a Windows setup should have:

- Python 3.10+
- native `iverilog` and `vvp`
- WSL installed and working
- `verilator` installed inside WSL
- `yosys` installed inside WSL
- `ollama` installed locally if AI features are needed

### Linux

Install Python 3 plus:

- Icarus Verilog
- Verilator
- Yosys
- Ollama if AI features are needed

Package names vary by distribution, so use your distro’s package manager where appropriate.

## Ollama

Current default local model configuration:

- URL: `http://localhost:11434`
- model: `qwen2.5-coder:7b`

These defaults can be overridden with environment variables:

- `RTL_ASSISTANT_OLLAMA_URL`
- `RTL_ASSISTANT_MODEL`

Example setup:

```bash
ollama pull qwen2.5-coder:7b
ollama serve
```

`ollama serve` must be running for AI-powered stages such as:

- natural-language requirement parsing
- AI RTL generation
- AI VerificationPlan generation

The configured model, currently `qwen2.5-coder:7b`, must already be downloaded for those stages.

Once the model is downloaded, normal Ollama inference is local. Internet access is not required for ordinary local model execution.

Important: deterministic Step 14 testbench rendering does **not** require Ollama once a valid `VerificationPlan` already exists.

Deterministic verification tools such as:

- Icarus / `vvp`
- Verilator
- Yosys

do not depend on Ollama.

## Verify Setup

Run the non-installing environment doctor:

```bash
python scripts/check_environment.py
```

It checks:

- Python version
- required Python imports
- repo structure
- `iverilog`
- `vvp`
- `verilator`
- `yosys`
- Ollama executable
- Ollama server reachability
- default model availability

It distinguishes deterministic readiness from AI-feature readiness so missing Ollama does not hide the rest of the environment state.

For example, this is a legitimate result:

```text
Deterministic pipeline: READY
AI features: NOT READY
```

That can happen when Ollama is installed but `ollama serve` is not currently running. In that case, start:

```bash
ollama serve
```

and then rerun:

```bash
python scripts/check_environment.py
```

Ollama does not need to remain running for deterministic testbench rendering or deterministic RTL verification.

## Quick Start

### 1. Validate a HardwareSpec

```bash
python scripts/validate_spec.py examples/specs/alu_4bit.json
```

### 2. Generate a verification plan

```bash
python scripts/generate_verification_plan.py \
  examples/specs/alu_4bit.json \
  --output reports/alu_4bit_verification_plan.json
```

This step is AI-dependent and requires:

- `ollama serve` running
- the configured model already downloaded locally

### 3. Generate a deterministic testbench

```bash
python scripts/generate_testbench.py \
  examples/specs/alu_4bit.json \
  reports/alu_4bit_verification_plan.json \
  --output generated/alu_4bit_tb.sv
```

This step is deterministic and does **not** require Ollama once a valid `HardwareSpec` and `VerificationPlan` already exist.

### 4. Run a known-good deterministic verification example

This uses the checked-in manual ALU RTL and testbench:

```bash
python scripts/verify_rtl.py \
  --rtl examples/alu_4bit/alu_4bit.sv \
  --testbench examples/alu_4bit/alu_4bit_tb.sv \
  --top alu_4bit \
  --report reports/alu_verification.json
```

This verification flow is deterministic and does not depend on Ollama.

### 5. Optional: run the standalone stages

Lint:

```bash
python scripts/run_lint.py \
  --rtl examples/alu_4bit/alu_4bit.sv
```

Simulation:

```bash
python scripts/run_simulation.py \
  --rtl examples/alu_4bit/alu_4bit.sv \
  --testbench examples/alu_4bit/alu_4bit_tb.sv \
  --report reports/alu_result.json
```

Synthesis:

```bash
python scripts/run_synthesis.py \
  --rtl examples/alu_4bit/alu_4bit.sv \
  --top alu_4bit \
  --report reports/alu_synthesis.json
```

## Cross-Platform Notes

- The Python pipeline is shared across Windows, macOS, and Linux.
- Generated SystemVerilog artifacts are platform-independent text outputs.
- Ollama usage is local on every platform when AI steps are enabled.
- Hardware-tool adapters isolate OS-specific invocation behavior.
- Windows currently relies on WSL for Verilator and Yosys.
- macOS and Linux use native Verilator and Yosys binaries.
- The deterministic Step 14 renderer is offline once `HardwareSpec` and `VerificationPlan` are available.

## Teammate Quick Start

If you just want the fastest onboarding path, use:

- [docs/TEAMMATE_SETUP.md](docs/TEAMMATE_SETUP.md)

That guide is intentionally practical and macOS-friendly.

## Known Limitations

- the local 7B model can still produce invalid plans or invalid RTL
- deterministic reference support is still expanding
- unsupported VerificationPlan language is rejected rather than guessed
- Step 14 sequential generalization is still being validated
- deterministic testbench rendering depends on structured plan language it can safely translate
- full failure classification and repair loops are not implemented yet

## License

A project license has not yet been selected. Until a license is added, all rights remain with the repository owners.
