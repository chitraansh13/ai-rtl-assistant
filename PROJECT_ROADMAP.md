# AI-Driven RTL Design and Verification Assistant

## Step-by-Step Project Roadmap

---

# Step 0 — Project Setup and Scope Definition

## What we will do

* Create the GitHub repository.
* Add both team members as collaborators.
* Define the first supported hardware modules.
* Create the initial folder structure.
* Write the project scope document.
* Define basic responsibilities for the CSE and ECE developers.
* Configure `.gitignore`.
* Establish basic Git and commit conventions.

## Initial supported modules

* 2-to-1 Multiplexer
* 4-bit ALU
* 4-bit synchronous counter

## What we will achieve

* A clean shared project repository
* Clear responsibilities
* A fixed first version of the project
* A controlled scope that prevents the project from becoming too large
* A common place for all code and documentation

## Completion condition

Both developers can clone the repository, make changes, commit, and push successfully.

---

# Step 1 — Manual RTL Design and Simulation

## What we will do

* Learn the basic RTL development workflow.
* Write SystemVerilog modules manually.
* Write self-checking testbenches.
* Compile designs using Icarus Verilog.
* Run simulations using `vvp`.
* Understand inputs, outputs, modules, DUTs, and testbenches.
* Learn how simulation time and delays work.

## Modules

1. 2-to-1 Multiplexer
2. 4-bit ALU
3. 4-bit synchronous counter

## Tools

* SystemVerilog
* Icarus Verilog
* `vvp`
* Git

## What we will achieve

* A basic understanding of hardware design
* Working RTL examples
* Working self-checking testbenches
* Verified simulation results
* A foundation for automation

## Completion condition

All three modules compile successfully and their testbenches print correct pass or fail results.

---

# Step 2 — Waveform Generation and Debugging

## What we will do

* Add waveform generation to the testbenches.
* Generate `.vcd` files.
* Open waveforms using GTKWave.
* Inspect signal changes over time.
* Understand clocks, resets, inputs, outputs, and internal states.
* Intentionally introduce small RTL mistakes and identify them through waveforms.

## Tools

* GTKWave
* VCD waveform files
* Icarus Verilog

## What we will achieve

* Ability to visually debug hardware behavior
* Understanding of sequential timing
* Better confidence when diagnosing simulation failures
* A method for inspecting generated RTL later

## Completion condition

Both developers can open a waveform and explain why the output is correct or incorrect.

---

# Step 3 — Python Simulation Automation

## What we will do

Create a Python program that automatically:

1. Accepts an RTL file.
2. Accepts a testbench file.
3. Runs Icarus Verilog.
4. Checks the compilation exit code.
5. Captures compiler output.
6. Runs the generated simulation.
7. Captures simulation output.
8. Reports pass or fail.
9. Handles missing files and timeouts.

## Example command

```bash
python scripts/run_simulation.py \
  --rtl examples/mux_2to1/mux_2to1.sv \
  --testbench examples/mux_2to1/mux_2to1_tb.sv
```

## Tools

* Python
* `subprocess`
* `pathlib`
* Icarus Verilog
* `vvp`

## What we will achieve

* The first real software automation component
* Automatic RTL compilation and simulation
* Structured error handling
* A reusable simulation runner
* The foundation for connecting AI-generated files to hardware tools

## Completion condition

One Python command can compile and simulate any supported example.

---

# Step 4 — Structured Simulation Results

## What we will do

* Create Python result models.
* Store compilation and simulation results in a structured format.
* Record:

  * Exit code
  * Standard output
  * Standard error
  * Duration
  * Pass or fail status
  * Generated artifacts
  * Timeout status
* Export results as JSON.

## Example output

```json
{
  "compile_passed": true,
  "simulation_passed": true,
  "exit_code": 0,
  "duration_ms": 145,
  "stdout": "PASS: Test 1",
  "stderr": "",
  "timed_out": false
}
```

## Tools

* Python
* Pydantic
* JSON

## What we will achieve

* Machine-readable simulation results
* Consistent result handling
* Data that can later be used by the AI repair system
* A result format suitable for a backend and web interface

## Completion condition

Every simulation produces a validated JSON result.

---

# Step 5 — RTL Linting with Verilator

## What we will do

* Install Verilator.
* Run lint checks on RTL.
* Detect:

  * Width mismatches
  * Unused signals
  * Incomplete assignments
  * Possible latch inference
  * Invalid constructs
* Capture and classify warnings.
* Add linting to the Python pipeline.

## Pipeline

```text
RTL
→ Verilator lint
→ Icarus compilation
→ Simulation
```

## Tools

* Verilator
* Python

## What we will achieve

* Detection of problems before simulation
* Better RTL quality
* More detailed diagnostics
* Cleaner generated hardware code

## Completion condition

The Python pipeline can run Verilator and return structured warnings.

---

# Step 6 — RTL Synthesis with Yosys

## What we will do

* Install Yosys.
* Create basic synthesis scripts.
* Synthesize supported RTL modules.
* Collect:

  * Cell counts
  * Register counts
  * Latch inference
  * Warnings
  * Top-module errors
  * Synthesizability status
* Add synthesis to the Python pipeline.

## Pipeline

```text
RTL
→ Lint
→ Compile
→ Simulate
→ Synthesize
→ Generate report
```

## Tools

* Yosys
* Python
* SystemVerilog

## What we will achieve

* Confirmation that the RTL can become hardware
* Basic hardware complexity reports
* Synthesis-aware verification
* A stronger engineering tool rather than only a simulator

## Completion condition

The pipeline produces a synthesis report for each verified module.

---

# Step 7 — Complete Deterministic Verification Pipeline

## What we will do

Combine all current components into one command.

The pipeline will:

1. Validate input files.
2. Run Verilator lint.
3. Compile with Icarus.
4. Simulate with `vvp`.
5. Run synthesis with Yosys.
6. Capture all logs.
7. Save all artifacts.
8. Produce one final JSON report.

## What we will achieve

* A complete non-AI RTL verification system
* A reliable foundation for future AI generation
* A reproducible hardware workflow
* A reusable engine for benchmarks and web APIs

## Completion condition

A manually written design can move through the complete pipeline using one command.

---

# Step 8 — Structured Hardware Specification

## What we will do

Create a formal Python schema called `HardwareSpec`.

It will describe:

* Module name
* Design category
* Inputs
* Outputs
* Signal widths
* Clock
* Reset
* Operations
* Parameters
* Arithmetic behavior
* Assumptions
* Verification strategy

## Example

```json
{
  "module_name": "counter_4bit",
  "design_type": "sequential",
  "width": 4,
  "clock_edge": "positive",
  "reset_type": "synchronous",
  "reset_polarity": "active_high",
  "has_enable": true,
  "overflow_behavior": "wrap"
}
```

## Tools

* Python
* Pydantic
* JSON Schema

## What we will achieve

* A precise machine-readable hardware requirement
* Reduced ambiguity
* Better AI generation
* Stable interfaces between AI, verification, and the frontend

## Completion condition

The three starter modules can each be represented completely using `HardwareSpec`.

---

# Step 9 — Local AI Setup with Ollama

## What we will do

* Install Ollama.
* Download one coding-focused local model.
* Test the model manually.
* Call Ollama using its local API.
* Create a Python `LLMProvider` interface.
* Implement an `OllamaProvider`.
* Record model name, response time, and output.

## Initial use of AI

The first AI task will be:

```text
Natural-language requirement
→ Structured HardwareSpec JSON
```

The first AI task will not be direct RTL generation.

## Tools

* Ollama
* Local coding model
* Python
* HTTP API

## What we will achieve

* A free local AI system
* No per-request API charges
* Offline AI execution
* A model-independent AI architecture

## Completion condition

Python can send a requirement to Ollama and receive a response.

---

# Step 10 — AI Requirement Parser

## What we will do

* Ask the local model to convert user text into `HardwareSpec`.
* Validate the returned JSON using Pydantic.
* Detect:

  * Missing fields
  * Invalid values
  * Unsupported features
  * Ambiguous behavior
* Add limited retries for invalid JSON.
* Display assumptions clearly.

## Example

```text
Input:
Create a 4-bit counter with enable and active-high synchronous reset.
```

```json
{
  "module_name": "counter_4bit",
  "design_type": "sequential",
  "width": 4,
  "reset_type": "synchronous",
  "reset_polarity": "active_high",
  "has_enable": true
}
```

## What we will achieve

* Reliable natural-language specification parsing
* Validated hardware requirements
* Separation between user language and RTL generation
* A safe entry point for AI

## Completion condition

The local model correctly parses supported specifications into valid `HardwareSpec` objects.

---

# Step 11 — Ambiguity and Clarification System

## What we will do

The system will identify important missing information.

Examples:

* Reset polarity not specified
* Signedness not specified
* Clock edge not specified
* Overflow behavior not specified
* Opcode mapping not specified

The system will either:

* Ask the user for clarification, or
* Display a low-risk assumption for approval

## What we will achieve

* Fewer incorrect RTL designs
* Better user control
* More reliable AI generation
* Clear documentation of assumptions

## Completion condition

The system does not silently invent important hardware behavior.

---

# Step 12 — AI RTL Generation

## What we will do

* Pass the approved `HardwareSpec` to the local model.
* Request synthesizable SystemVerilog.
* Enforce coding rules:

  * `always_comb`
  * `always_ff`
  * Explicit widths
  * No simulation-only code in the DUT
  * No inferred latches
  * Stable module interface
* Save generated RTL as an artifact.
* Send it through the deterministic verification pipeline.

## Flow

```text
Approved HardwareSpec
→ Ollama
→ Generated RTL
→ Lint
→ Compile
→ Simulate
→ Synthesize
```

## What we will achieve

* The first real AI-generated hardware design
* Tool-verified local RTL generation
* A system where AI proposes code but tools validate it

## Completion condition

The local model can generate at least one verified supported RTL design.

---

# Step 13 — Verification Plan Generation

## What we will do

Before generating a testbench, create a verification plan.

The plan will define:

* Important input cases
* Edge cases
* Reset cases
* Boundary values
* Exhaustive or randomized testing
* Expected outputs
* Assertions
* Timeout behavior

## What we will achieve

* Better testbench quality
* Clear verification intent
* Less dependence on random AI-generated testing
* A reusable verification strategy

## Completion condition

Every supported design receives a structured verification plan.

---

# Step 14 — AI Testbench Generation

## What we will do

* Generate self-checking SystemVerilog testbenches.
* Include:

  * Input stimulus
  * Expected results
  * Pass/fail counters
  * Clear error messages
  * Timeout protection
  * Optional waveform generation
* Compile the testbench with the generated RTL.
* Capture all failures.

## What we will achieve

* Automatic testbench creation
* Automatic simulation
* Better end-to-end hardware generation
* Verification artifacts available for download

## Completion condition

The system can generate and run a testbench for a supported RTL module.

---

# Step 15 — Independent Reference Models

## What we will do

Create Python reference models for supported module families.

Examples:

* MUX reference function
* ALU arithmetic and logic model
* Counter state-transition model

Simulation results will be compared against these independent models.

## What we will achieve

* Stronger correctness checks
* Reduced risk of RTL and testbench sharing the same AI mistake
* Deterministic expected outputs
* Better benchmark reliability

## Completion condition

Generated RTL is tested against an independent expected-behavior model.

---

# Step 16 — Failure Classification

## What we will do

Convert raw tool logs into structured failure categories.

Examples:

* Syntax error
* Port mismatch
* Width mismatch
* Functional mismatch
* Reset failure
* Timeout
* Latch inference
* Unsynthesizable construct
* Missing top module

## Example

```json
{
  "failure_type": "functional_mismatch",
  "expected": 1,
  "actual": 0,
  "inputs": {
    "a": 1,
    "b": 0,
    "select": 0
  }
}
```

## What we will achieve

* Clear diagnostics
* Better AI repair prompts
* Better user explanations
* Searchable failure statistics

## Completion condition

Common compiler, simulation, and synthesis failures are converted into structured diagnostics.

---

# Step 17 — Automatic RTL Repair Loop

## What we will do

When verification fails:

1. Collect RTL.
2. Collect approved specification.
3. Collect structured diagnostics.
4. Send them to the local AI model.
5. Generate corrected RTL.
6. Rerun all verification stages.
7. Preserve each attempt.
8. Stop after a fixed retry limit.

## Retry policy

Initially:

* Maximum three repair attempts
* Interface cannot change
* All previous tests must rerun
* Every attempt must be saved

## What we will achieve

* Automatic debugging
* Iterative RTL improvement
* A central feature of the project
* Measurable repair success rates

## Completion condition

The system repairs selected intentionally broken RTL examples.

---

# Step 18 — Project and Artifact Storage

## What we will do

Store:

* Projects
* Specifications
* Runs
* Attempts
* Generated RTL
* Testbenches
* Logs
* Waveforms
* Synthesis reports
* AI model metadata

Start with:

* Local folders
* SQLite

Move later to:

* PostgreSQL
* Object storage

## What we will achieve

* Persistent project history
* Comparison between attempts
* Reproducible runs
* Data for the frontend and evaluation system

## Completion condition

A completed run can be reopened with all its artifacts and results.

---

# Step 19 — FastAPI Backend

## What we will do

Create backend endpoints for:

* Projects
* Specifications
* AI parsing
* Run creation
* Run status
* Artifacts
* Reports
* Downloads

## Example endpoints

```text
POST /api/v1/projects
POST /api/v1/specifications/parse
POST /api/v1/runs
GET /api/v1/runs/{run_id}
GET /api/v1/runs/{run_id}/artifacts
```

## What we will achieve

* A proper backend application
* Separation between frontend and the RTL engine
* Persistent project APIs
* A professional software architecture

## Completion condition

The complete RTL pipeline can be triggered through an API.

---

# Step 20 — Background Worker System

## What we will do

Move long-running verification tasks out of API requests.

Initially:

* Local worker

Later:

* Redis
* Dramatiq, RQ, or Celery

## What we will achieve

* Non-blocking API requests
* Better reliability
* Run cancellation
* Progress updates
* Support for multiple queued designs

## Completion condition

The backend can start a job and return its status while verification continues separately.

---

# Step 21 — Web Dashboard

## What we will do

Build a professional frontend with:

* Project creation
* Natural-language specification input
* Structured specification review
* Clarification questions
* RTL viewer
* Testbench viewer
* Pipeline progress
* Simulation logs
* Error explanations
* Repair attempt comparison
* Synthesis report
* Artifact downloads

## Tools

* Next.js
* React
* TypeScript
* Tailwind CSS
* Monaco Editor

## What we will achieve

* A complete user-facing engineering application
* A professional capstone demonstration
* A usable interface for non-programmatic users

## Completion condition

A user can complete the entire generation and verification workflow from the browser.

---

# Step 22 — Benchmark Suite

## What we will do

Create a fixed benchmark collection.

Suggested modules:

* Multiplexer
* Decoder
* Encoder
* Comparator
* Adder
* ALU
* Counter
* Shift register
* Sequence detector
* Traffic-light controller
* Register file
* Synchronous FIFO

Each benchmark will contain:

* Natural-language prompt
* Structured specification
* Golden RTL
* Golden testbench
* Reference model
* Expected behavior
* Difficulty level

## What we will achieve

* A fair evaluation set
* Repeatable experiments
* Reliable comparison between models and prompts
* A basis for research claims

## Completion condition

The benchmark suite runs automatically and produces consistent results.

---

# Step 23 — Evaluation Framework

## What we will do

Measure:

* Valid JSON generation rate
* RTL compilation success rate
* Simulation pass rate
* Synthesis success rate
* End-to-end verified design rate
* Repair success rate
* Average repair attempts
* Generation time
* Memory usage
* Model response time
* Local model quality

## What we will achieve

* Quantitative evidence
* Research-ready results
* Honest measurement of system performance
* Data for reports, charts, and presentations

## Completion condition

One command can evaluate the full benchmark suite and produce a result report.

---

# Step 24 — RAG Knowledge System

## What we will do

Create a curated knowledge base containing:

* Synthesizable SystemVerilog rules
* RTL coding patterns
* Verification patterns
* Common errors
* Tool documentation
* Assertion examples
* Trusted module templates

Use:

* ChromaDB or FAISS
* Embeddings
* Metadata filters

## What we will achieve

* Better generation quality
* Better debugging suggestions
* Reduced repeated model mistakes
* A measurable RAG versus non-RAG comparison

## Completion condition

RAG shows measurable improvement on at least part of the benchmark suite.

---

# Step 25 — Formal Verification

## What we will do

Add formal checks for selected modules using:

* SystemVerilog Assertions
* SymbiYosys
* Yosys formal flow
* SMT solvers

Potential properties:

* Counter never exceeds its defined width
* Reset always clears state
* MUX output always matches selected input
* FSM never enters illegal states
* FIFO does not read when empty

## What we will achieve

* Stronger correctness guarantees
* A valuable research feature
* Verification beyond simulation
* Better support for safety properties

## Completion condition

Selected benchmark properties are automatically proven or produce clear counterexamples.

---

# Step 26 — FPGA Demonstration

## What we will do

Choose an FPGA board and deploy selected verified designs.

Possible designs:

* ALU
* Counter
* Sequence detector
* UART transmitter

Tasks:

* Create board constraints
* Add clock and I/O wrappers
* Run FPGA synthesis
* Generate bitstream
* Program the board
* Verify physical output

## What we will achieve

* Proof that generated RTL works on real hardware
* A stronger project demonstration
* Practical FPGA experience
* A valuable portfolio feature

## Completion condition

At least one AI-generated and verified module runs successfully on an FPGA board.

---

# Step 27 — Optional Open-Source ASIC Flow

## What we will do

For selected designs, explore:

* SKY130
* OpenSTA
* OpenROAD
* OpenLane

Possible flow:

```text
RTL
→ Synthesis
→ Floorplanning
→ Placement
→ Clock-tree synthesis
→ Routing
→ Timing report
```

## What we will achieve

* ASIC-oriented design analysis
* Timing and area experiments
* Exposure to physical design
* An impressive future extension

## Completion condition

At least one small verified design completes a documented open-source ASIC flow.

---

# Step 28 — Final Documentation and Presentation

## What we will do

Create:

* Professional README
* Architecture diagrams
* API documentation
* User guide
* Developer guide
* Hardware verification guide
* Benchmark documentation
* Research abstract
* Final report
* Presentation
* Demo video
* Resume description
* Reproduction instructions

## What we will achieve

* A polished final-year project
* A professional GitHub portfolio
* Research-ready documentation
* A strong project presentation
* A reproducible project for evaluators

## Completion condition

A new person can understand, install, run, evaluate, and demonstrate the project using the documentation.

---

# Recommended Implementation Order

```text
Step 0–2:
Project setup and manual hardware learning

Step 3–7:
Python-based deterministic verification pipeline

Step 8:
Structured hardware specification

Step 9–12:
Local AI parsing and RTL generation

Step 13–17:
Verification generation, diagnostics, and repair

Step 18–21:
Storage, backend, workers, and frontend

Step 22–24:
Benchmarks, evaluation, and RAG

Step 25–27:
Formal verification, FPGA, and ASIC extensions

Step 28:
Final documentation and presentation
```

---

# Current Progress

Completed:

* GitHub repository created
* First SystemVerilog module created
* First testbench created
* Icarus Verilog compilation completed
* MUX simulation completed
* All MUX tests passed

Current position:

```text
Step 1 — Manual RTL Design and Simulation
```

Immediate next task:

```text
Clean and commit the MUX example
→ Generate and inspect its waveform
→ Create the first Python simulation runner
```