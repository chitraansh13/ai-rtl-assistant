# AI-Driven RTL Design and Verification Assistant

An AI-assisted platform for generating, simulating, verifying, debugging, and eventually synthesizing Verilog/SystemVerilog RTL designs from natural-language hardware specifications.

> **Project status:** Early development. RTL simulation, waveform generation, automated result classification, and structured JSON reporting are currently available. AI-based RTL generation has not yet been integrated.

---

## Overview

The final system will accept a hardware requirement such as:

> Create a 4-bit ALU supporting ADD, SUB, AND, and OR.

It will eventually:

1. Convert the requirement into a structured hardware specification.
2. Generate synthesizable RTL.
3. Generate verification testbenches.
4. Compile and simulate the design.
5. Detect compilation and functional failures.
6. Attempt automatic RTL repair.
7. Run synthesis and generate hardware reports.
8. Present the workflow through a web dashboard.

The project follows one core principle:

> AI generates candidate hardware designs, while deterministic hardware tools verify whether they are correct.

---

## Current Features

- SystemVerilog RTL examples
- Self-checking SystemVerilog testbenches
- RTL compilation using Icarus Verilog
- Simulation using `vvp`
- Generic Python simulation runner
- PASS, FAIL, and UNKNOWN result classification
- Missing-file and timeout handling
- VCD waveform generation
- GTKWave waveform inspection
- Structured JSON simulation reports
- Typed report validation using Pydantic v2

---

## Current Example Modules

- 2-to-1 Multiplexer
- 4-bit ALU
- 4-bit synchronous counter — in progress

---

## Current Pipeline

```text
RTL file
    ↓
Testbench
    ↓
Python simulation runner
    ↓
Icarus Verilog compilation
    ↓
vvp simulation
    ↓
PASS / FAIL / UNKNOWN
    ↓
Validated JSON report
    ↓
VCD waveform
```

## Technologies

### Currently used
- Python
- Pydantic v2
- SystemVerilog
- Icarus Verilog
- `vvp`
- GTKWave
- Git
- GitHub

### Planned
- Verilator
- Yosys
- Ollama
- FastAPI
- PostgreSQL
- Next.js
- React
- TypeScript
- Tailwind CSS
- Docker

## Repository Structure

```text
ai-rtl-assistant/
├── README.md
├── requirements.txt
├── .gitignore
│
├── examples/
│   ├── mux_2to1/
│   │   ├── mux_2to1.sv
│   │   ├── mux_2to1_tb.sv
│   │   └── specification.md
│   │
│   └── alu_4bit/
│       ├── alu_4bit.sv
│       ├── alu_4bit_tb.sv
│       └── specification.md
│
├── scripts/
│   └── run_simulation.py
│
├── src/
│   └── rtl_assistant/
│       ├── __init__.py
│       └── models/
│           ├── __init__.py
│           └── simulation.py
│
└── docs/
```

Generated files such as `.vvp`, `.vcd`, simulation executables, and JSON reports are ignored by Git.

## Prerequisites

Install:
- Git
- Python 3.10 or newer
- Icarus Verilog
- GTKWave

Verify the installations:
```bash
python --version
iverilog -V
vvp -V
gtkwave --version
```

## Setup

### 1. Clone the repository
```bash
git clone https://github.com/chitraansh13/ai-rtl-assistant.git
cd ai-rtl-assistant
```

### 2. Create a virtual environment
```bash
python -m venv .venv
```

Activate it in Git Bash on Windows:
```bash
source .venv/Scripts/activate
```

On PowerShell:
```powershell
.venv\Scripts\Activate.ps1
```

On Linux or macOS:
```bash
source .venv/bin/activate
```

### 3. Install dependencies
```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Running a Simulation

The simulation runner accepts an RTL file and its testbench.

### Run the 2-to-1 MUX
```bash
python scripts/run_simulation.py \
  --rtl examples/mux_2to1/mux_2to1.sv \
  --testbench examples/mux_2to1/mux_2to1_tb.sv
```

### Run the 4-bit ALU
```bash
python scripts/run_simulation.py \
  --rtl examples/alu_4bit/alu_4bit.sv \
  --testbench examples/alu_4bit/alu_4bit_tb.sv
```

A successful execution ends with:
```text
FINAL RESULT: PASS
```

## Generate a JSON Report

Use the optional `--report` argument:
```bash
python scripts/run_simulation.py \
  --rtl examples/alu_4bit/alu_4bit.sv \
  --testbench examples/alu_4bit/alu_4bit_tb.sv \
  --report reports/alu_result.json
```

View the generated report:
```bash
cat reports/alu_result.json
```

Example:
```json
{
  "compile_passed": true,
  "simulation_passed": true,
  "final_status": "PASS",
  "compile_exit_code": 0,
  "simulation_exit_code": 0,
  "compile_timed_out": false,
  "simulation_timed_out": false,
  "compile_duration_ms": 52,
  "simulation_duration_ms": 14,
  "total_duration_ms": 69,
  "error_type": null,
  "error_message": null
}
```

The complete report also includes:
- RTL and testbench paths
- Compiler output
- Simulator output
- Exit codes
- Stage durations
- Timeout information
- Structured error information

## Result Statuses

### PASS
The RTL compiled, the simulation ran, and all functional tests passed.

Process exit code: `0`

### FAIL
Possible causes include:
- Missing RTL or testbench file
- Compilation error
- Simulator error
- Timeout
- Functional test failure

Process exit code: `1`

### UNKNOWN
The simulation completed, but the testbench did not print a recognizable PASS or FAIL result.

Process exit code: `2`

## Compilation Success vs Functional Correctness

A design can compile successfully and still be functionally wrong.

Example:
```json
{
  "compile_passed": true,
  "simulation_exit_code": 0,
  "simulation_passed": false,
  "final_status": "FAIL"
}
```

This means:
- The SystemVerilog syntax was valid.
- The simulator executed successfully.
- The testbench detected incorrect hardware behaviour.

## Viewing Waveforms

The current testbenches generate VCD waveform files.

### MUX waveform
Run the MUX simulation, then open:
```bash
gtkwave examples/mux_2to1/mux_2to1.vcd
```

Inspect:
- `a`
- `b`
- `select`
- `y`

Expected behaviour:
- `select = 0` → `y` follows `a`
- `select = 1` → `y` follows `b`

### ALU waveform
Run the ALU simulation, then open:
```bash
gtkwave examples/alu_4bit/alu_4bit.vcd
```

Inspect:
- `a`
- `b`
- `opcode`
- `result`
- `carry`
- `zero`

ALU opcode mapping:

| Opcode | Operation |
| :--- | :--- |
| `00` | ADD |
| `01` | SUB |
| `10` | AND |
| `11` | OR |

## Adding a New RTL Module

Create a folder inside `examples/`:
```text
examples/<module_name>/
├── <module_name>.sv
├── <module_name>_tb.sv
└── specification.md
```

The testbench should:
- Be self-checking
- Print clear `PASS` and `FAIL` messages
- Report expected and actual values
- End using `$finish`
- Optionally generate a VCD waveform

Run the module using:
```bash
python scripts/run_simulation.py \
  --rtl examples/<module_name>/<module_name>.sv \
  --testbench examples/<module_name>/<module_name>_tb.sv \
  --report reports/<module_name>_result.json
```

The Python runner is module-independent and does not need to be modified for each new design.

## License

A project license has not yet been selected. Until a license is added, all rights remain with the repository owners.
