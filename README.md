# AI-Driven RTL Design and Verification Assistant

A Python-based project for deterministic verification of small SystemVerilog designs, with a structured hardware specification layer that is intended to support future AI-assisted RTL generation.

The current repository does **not** yet implement natural-language parsing or AI RTL generation. Today, RTL and testbenches are written manually, then checked by a reproducible verification pipeline.

---

## Overview

### What is implemented now

- SystemVerilog RTL examples
- Self-checking SystemVerilog testbenches
- Example designs:
  - 2-to-1 MUX
  - 4-bit ALU
  - 4-bit synchronous counter
- VCD waveform generation
- GTKWave-based waveform inspection for debugging
- Icarus Verilog compilation
- `vvp` functional simulation
- PASS / FAIL / UNKNOWN result classification
- Typed Pydantic simulation reports
- Verilator linting
- Typed lint reports
- Yosys synthesis
- Parsed synthesis statistics:
  - wire count
  - wire-bit count
  - cell count
  - cell types
- Cross-platform hardware-tool execution:
  - Windows: Verilator and Yosys through WSL, Icarus native
  - macOS/Linux: native tools
- Unified deterministic verification pipeline
- Nested typed JSON `VerificationReport`
- Structured Pydantic `HardwareSpec`
- Hardware specifications for:
  - MUX
  - ALU
  - counter
- HardwareSpec validation CLI

### Current verification flow

```text
Structured HardwareSpec
        ↓
Manually written SystemVerilog RTL
        ↓
┌──────────────────────────┐
│ Verilator lint           │
│ Icarus compile/simulate  │
│ Yosys synthesis          │
└──────────────────────────┘
        ↓
Typed VerificationReport
        ↓
PASS / FAIL / UNKNOWN
```

### Planned future AI flow

```text
Natural-language requirement
        ↓
HardwareSpec
        ↓
AI RTL generation
        ↓
Deterministic verification engine
```

That future AI layer is planned work, not current functionality.

---

## Why Multiple Tools Are Used

The project intentionally combines different deterministic hardware tools because they answer different questions:

- Verilator checks lint, structural issues, and common RTL quality problems.
- Icarus Verilog plus a self-checking testbench checks functional behavior.
- Yosys checks that the RTL is synthesizable and reports inferred hardware structure.

These tools are complementary. A design can legitimately produce:

```text
Lint       PASS
Simulation FAIL
Synthesis  PASS
```

This project has already validated that case using an intentionally incorrect ALU operation: syntactically valid and synthesizable RTL can still implement the wrong functionality.

---

## Current Example Designs

- `examples/mux_2to1/`
- `examples/alu_4bit/`
- `examples/4bit_counter/`

The repository also contains some additional experimental material, but the designs above are the current documented examples for the deterministic pipeline and HardwareSpec layer.

---

## Platform Requirements

### Windows

- Python 3.10+
- Icarus Verilog / `vvp` available natively
- WSL
- Verilator installed inside WSL
- Yosys installed inside WSL

### macOS

- Python 3
- Icarus Verilog
- Verilator
- Yosys
- Homebrew is a practical installation path for the hardware tools

### Linux

- Python 3
- Icarus Verilog
- Verilator
- Yosys

GTKWave is useful for waveform inspection and debugging, but it is not required to run the core verification pipeline.

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/chitraansh13/ai-rtl-assistant.git
cd ai-rtl-assistant
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
```

Git Bash on Windows:

```bash
source .venv/Scripts/activate
```

PowerShell on Windows:

```powershell
.venv\Scripts\Activate.ps1
```

Linux or macOS:

```bash
source .venv/bin/activate
```

### 3. Install Python dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

---

## Usage

### Validate a HardwareSpec

```bash
python scripts/validate_spec.py examples/specs/alu_4bit.json
```

### Run lint only

```bash
python scripts/run_lint.py \
  --rtl examples/alu_4bit/alu_4bit.sv
```

### Run simulation only

```bash
python scripts/run_simulation.py \
  --rtl examples/alu_4bit/alu_4bit.sv \
  --testbench examples/alu_4bit/alu_4bit_tb.sv \
  --report reports/alu_result.json
```

### Run synthesis only

```bash
python scripts/run_synthesis.py \
  --rtl examples/alu_4bit/alu_4bit.sv \
  --top alu_4bit \
  --report reports/alu_synthesis.json
```

### Run complete verification

```bash
python scripts/verify_rtl.py \
  --rtl examples/alu_4bit/alu_4bit.sv \
  --testbench examples/alu_4bit/alu_4bit_tb.sv \
  --top alu_4bit \
  --report reports/alu_verification.json
```

A successful full verification run prints a concise stage summary like:

```text
Lint:       PASS
Simulation: PASS
Synthesis:  PASS

Overall:    PASS
```

The unified JSON output nests the typed lint, simulation, and synthesis reports inside a typed `VerificationReport`.

---

## HardwareSpec Layer

The repository now includes a structured `HardwareSpec` model that represents a hardware design independently from any future AI system.

It currently supports:

- module name
- design type (`combinational` or `sequential`)
- parameters
- ports with direction, width, signedness, and role
- optional clock metadata
- optional reset metadata
- structured behavioral descriptions
- tags

Current cross-field validation includes:

- port widths must be at least 1
- duplicate ports are rejected
- duplicate parameters are rejected
- clock signals must be valid declared input ports
- reset signals must be valid declared input ports
- sequential designs must define a clock
- combinational designs reject clock/reset metadata in this first version

Example specs live in:

- `examples/specs/mux_2to1.json`
- `examples/specs/alu_4bit.json`
- `examples/specs/counter_4bit.json`

---

## Waveforms and Debugging

The self-checking testbenches generate VCD waveforms, which can be inspected in GTKWave when debugging behavior.

Examples:

```bash
gtkwave examples/mux_2to1/mux_2to1.vcd
```

```bash
gtkwave examples/alu_4bit/alu_4bit.vcd
```

Waveform viewing is optional, but helpful when a design fails functional simulation.

---

## Repository Structure

```text
scripts/
  run_lint.py
  run_simulation.py
  run_synthesis.py
  verify_rtl.py
  validate_spec.py

src/rtl_assistant/
  models/
    lint.py
    simulation.py
    synthesis.py
    verification.py
    hardware_spec.py

  hardware_tools/
    platform.py
    verilator.py
    iverilog.py
    yosys.py

  pipeline/
    verification.py

examples/
  mux_2to1/
  alu_4bit/
  4bit_counter/
  specs/
  fifo_sync/
```

---

## Progress

Completed:

- Project setup
- Manual RTL + testbenches
- Waveform generation/debugging
- Python simulation automation
- Structured simulation results
- Verilator linting
- Yosys synthesis
- Unified deterministic verification pipeline
- Structured HardwareSpec

Planned next:

- Ollama / local LLM provider integration
- natural-language to HardwareSpec parsing
- ambiguity and clarification handling
- AI RTL generation
- verification-plan and testbench generation
- failure classification
- automatic RTL repair
- storage / backend / frontend
- benchmarks and evaluation
- optional RAG / formal / FPGA extensions

---

## License

A project license has not yet been selected. Until a license is added, all rights remain with the repository owners.
