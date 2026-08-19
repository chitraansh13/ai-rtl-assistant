# AI-Driven RTL Design and Verification Assistant — Project Development Log

## Project Goal

Build an AI-assisted RTL development workflow that starts from natural-language hardware intent, moves through a structured specification layer, generates SystemVerilog RTL, and then relies on deterministic hardware tools to decide whether the result is valid and functionally correct.

The long-term intended flow is:

```text
Natural-language requirement
→ structured HardwareSpec
→ AI-generated SystemVerilog RTL
→ deterministic verification
→ later repair/improvement loops
```

The core engineering principle from the beginning has been simple:

```text
LLM output is never the source of truth.
Deterministic hardware tools are the source of truth.
```

## Current Architecture Summary

Current implemented architecture:

```text
Natural-language requirement
→ ambiguity analysis
→ clarification if needed
→ validated HardwareSpec
→ local LLM RTL generation
→ local sanity checks

Validated HardwareSpec
→ local LLM verification-plan generation
→ deterministic expected-value resolver
→ typed VerificationPlan

Validated HardwareSpec + VerificationPlan
→ structured TestbenchPlan / IR
→ deterministic SystemVerilog renderer
→ lightweight deterministic validation

Manually written RTL or future AI-generated RTL
→ Verilator lint
→ Icarus Verilog compile/simulate
→ Yosys synthesis
→ typed VerificationReport
→ PASS / FAIL / UNKNOWN
```

Important architectural layers in the current repository:

- `src/rtl_assistant/models/`
  - typed Pydantic contracts for simulation, lint, synthesis, verification, LLM parsing, HardwareSpec, and RTL generation
- `src/rtl_assistant/hardware_tools/`
  - deterministic adapters for Verilator, Icarus Verilog, and Yosys
- `src/rtl_assistant/llm/`
  - provider-neutral LLM interface and Ollama implementation
- `src/rtl_assistant/spec/`
  - natural-language requirement parsing, ambiguity analysis, clarification handling, and prompt construction
- `src/rtl_assistant/rtl/`
  - HardwareSpec-to-RTL generation prompt and generator logic
- `src/rtl_assistant/verification_plan/`
  - HardwareSpec-to-verification-plan prompt and generator logic
- `src/rtl_assistant/reference/`
  - deterministic expected-value resolution for machine-computable verification semantics
- `src/rtl_assistant/testbench/`
  - HardwareSpec-plus-VerificationPlan to testbench prompt and generator logic
- `src/rtl_assistant/pipeline/`
  - unified deterministic verification orchestration
- `scripts/`
  - thin CLI entry points for validation, parsing, generation, lint, simulation, synthesis, and full verification

## Current Status

- Deterministic verification foundation is implemented.
- Structured HardwareSpec layer is implemented.
- Local Ollama-based requirement parsing is implemented.
- Ambiguity and clarification handling is implemented.
- AI RTL generation is implemented.
- AI verification-plan generation is implemented.
- Deterministic testbench rendering from validated plans is implemented.
- Deterministic verification is intentionally not yet wired into the RTL generation loop.

## Last Documented Step

Step 14 — testbench generation is currently in progress.

## Step Status

| Step | Milestone                            | Status      |
| ---- | ------------------------------------ | ----------- |
| 0    | Project setup and scope              | Complete    |
| 1    | Manual RTL and simulation            | Complete    |
| 2    | Waveform inspection                  | Complete    |
| 3    | Python simulation automation         | Complete    |
| 4    | Structured simulation reports        | Complete    |
| 5    | Verilator linting                    | Complete    |
| 6    | Yosys synthesis                      | Complete    |
| 7    | Unified verification pipeline        | Complete    |
| 8    | Structured HardwareSpec              | Complete    |
| 9    | Local LLM environment                | Complete    |
| 10   | AI requirement parsing               | Complete    |
| 11   | Ambiguity and clarification handling | Complete    |
| 12   | AI RTL generation                    | Complete    |
| 13   | Verification plan generation         | Complete    |
| 14   | Testbench generation                 | In Progress |

---

## Step 0 — Project Setup and Scope

### Goal

Define the project boundary, target workflow, technology stack, and architectural principles before writing automation code.

### Why This Step Was Needed

Without a clear scope, it would have been easy to build a demo that looked intelligent but had no reliable correctness boundary. This project needed a firm distinction between:

- probabilistic AI assistance
- deterministic hardware validation

That distinction influenced every later design decision.

### What We Implemented

This phase established the project as a Python-based RTL assistant centered on:

- SystemVerilog examples
- Pydantic v2 typed contracts
- Icarus Verilog and `vvp` for functional simulation
- Verilator for linting
- Yosys for synthesis
- Ollama with `qwen2.5-coder:7b` for local LLM work

It also established two non-negotiable design goals:

- provider-neutral AI architecture
- cross-platform tool execution, especially Windows support

### Files Created

`PROJECT_SCOPE_V1.md`

- early scope definition for the first meaningful version of the project
- captures the project boundary before later AI features
- useful for explaining what was intentionally deferred

`PROJECT_ROADMAP.md`

- milestone-oriented plan for how the project should evolve
- separates foundational deterministic work from later AI layers
- helped keep later feature additions staged instead of monolithic

`requirements.txt`

- Python dependency list for the repository
- anchors the environment around the chosen Python and Pydantic tooling

### Files Modified

`README.md`

- became the public-facing summary of the project direction
- later updated as deterministic verification and structured specification work were completed

### Architecture / Flow

```text
Project scope
→ deterministic verification first
→ AI layers later
→ provider-neutral, cross-platform architecture
```

### Manual Validation Performed

At this stage the validation was architectural rather than executable:

- confirmed the project would center on real SystemVerilog examples
- confirmed the verification backbone would precede AI generation
- confirmed Windows, macOS, and Linux needed to remain viable targets

### Problems Encountered

The biggest early risk was conceptual rather than code-level:

- an AI-first prototype could easily produce impressive-looking but unverifiable results
- Windows support for hardware tools was known in advance to be a likely friction point

### Fixes / Improvements

The answer was to lock the architecture around deterministic tools first and treat AI as a front-end that feeds validated contracts into that backbone.

### Key Engineering Decisions

- Deterministic hardware tools, not the LLM, would be the correctness oracle.
- Structured typed models would be used early to avoid loosely formatted tool output.
- The architecture would stay modular so later AI steps would not collapse into one giant script.

### What We Learned

The most important project decision was not a code detail. It was deciding what the system should trust.

### Final Outcome

A clearly scoped project plan existed:

```text
natural language
→ structured spec
→ RTL
→ deterministic verification
→ later repair
```

### Limitations / Deferred Work

- no automation yet
- no typed report models yet
- no AI parsing or generation yet
- no verification orchestration yet

---

## Step 1 — Manual RTL and Simulation

### Goal

Create a small set of hand-written reference RTL modules and self-checking testbenches that could serve as known-good baselines for all later automation.

### Why This Step Was Needed

Before automating simulation, lint, or synthesis, the project needed trusted reference designs. Without them, later failures could be caused by either the automation or the hardware itself, making debugging much harder.

### What We Implemented

Three reference examples were created:

- 2-to-1 multiplexer
- 4-bit ALU
- 4-bit synchronous counter

Each example included:

- SystemVerilog RTL
- a self-checking SystemVerilog testbench

Important reference behavior established here:

- MUX:
  - `select = 0` selects `a`
  - `select = 1` selects `b`
- ALU:
  - opcode `00` = ADD
  - opcode `01` = SUB
  - opcode `10` = AND
  - opcode `11` = OR
  - visible outputs include result, carry, and zero
- Counter:
  - synchronous sequential behavior
  - reset support
  - enable-controlled update
  - wraparound counting behavior

These examples later became the benchmark set used across simulation, lint, synthesis, HardwareSpec, and AI parsing tests.

### Files Created

`examples/mux_2to1/mux_2to1.sv`

- reference combinational RTL for the 2-to-1 multiplexer
- establishes the simplest supported design family

`examples/mux_2to1/mux_2to1_tb.sv`

- self-checking testbench for the MUX
- verifies select-to-output behavior without manual waveform inspection

`examples/alu_4bit/alu_4bit.sv`

- reference combinational ALU RTL
- provides arithmetic and logic operations plus carry/zero outputs
- later became the most important example for showing that simulation and synthesis answer different questions

`examples/alu_4bit/alu_4bit_tb.sv`

- self-checking ALU testbench
- verifies opcode mapping and visible outputs

`examples/4bit_counter/counter_4bit.sv`

- reference sequential counter RTL
- captures clocked behavior, reset, enable, and natural wraparound

`examples/4bit_counter/counter_4bit_tb.sv`

- self-checking testbench for the counter
- verifies reset, increment, hold, and wrap behavior

### Files Modified

No later automation files were required yet. This step mainly established the hardware examples themselves.

### Architecture / Flow

```text
Manual RTL
→ self-checking testbench
→ trusted reference behavior
```

### Manual Validation Performed

Manual simulation and inspection confirmed:

- MUX output changed correctly with select
- ALU operations matched the intended opcode mapping
- counter reset, enable, and wraparound behavior were correct

### Problems Encountered

At this stage the main problem was simply making sure the testbenches were truly self-checking rather than only producing waveforms.

### Fixes / Improvements

The testbenches were written to report pass/fail conditions directly, which later made CLI-based automation far easier.

### Key Engineering Decisions

- start with small designs that cover both combinational and sequential logic
- use self-checking testbenches instead of relying only on visual inspection
- keep the examples simple enough to explain in a capstone presentation

### What We Learned

Good automation starts with small, trusted reference cases. The examples chosen here later shaped nearly every other project decision.

### Final Outcome

The project had baseline RTL and testbenches for three design families:

- mux
- ALU
- counter

### Limitations / Deferred Work

- verification still depended on manual tool invocation
- no typed reports yet
- no cross-platform abstraction yet

---

## Step 2 — Waveform Inspection

### Goal

Add VCD waveform generation and inspect the designs with GTKWave to confirm timing and signal behavior visually.

### Why This Step Was Needed

Self-checking testbenches provide pass/fail answers, but they do not always explain why something failed. Waveforms are essential when learning the hardware behavior of a design or debugging unexpected sequential timing.

### What We Implemented

The testbench flow was extended to dump VCD traces so that designs could be inspected in GTKWave. This was used for:

- the MUX
- the ALU
- the counter

This phase made the project easier to debug and easier to explain to others, especially when sequential timing behavior needed to be shown visually.

### Files Created

Generated VCD outputs were produced during manual testing rather than becoming core source files. A representative example visible at the repository root is:

`counter_4bit.vcd`

- waveform dump from counter simulation work
- demonstrates the project’s early debug workflow before deterministic automation became the default interface

### Files Modified

`examples/*/*_tb.sv`

- testbenches were used in a waveform-producing mode for manual inspection
- this debug capability later remained useful even after typed automation was added

### Architecture / Flow

```text
RTL
→ testbench
→ VCD dump
→ GTKWave inspection
```

### Manual Validation Performed

Waveforms were inspected to confirm:

- MUX select-driven output switching
- ALU output transitions under different opcodes
- counter clocked updates, reset behavior, and hold behavior

### Problems Encountered

The main limitation of this phase was that waveform review does not scale. It is very useful for understanding behavior, but it is not a good primary automation interface.

### Fixes / Improvements

This insight directly motivated the next phase: use Python to automate compile and simulation steps while keeping waveforms available as a debugging aid.

### Key Engineering Decisions

- keep waveform generation available, but do not make it the main verification result
- preserve GTKWave as an optional debug path, not a mandatory pipeline dependency

### What We Learned

Waveforms are excellent for diagnosis and explanation, but they are not enough by themselves for a reproducible engineering pipeline.

### Final Outcome

The project gained a practical debug layer:

```text
simulation
→ VCD
→ waveform inspection
```

### Limitations / Deferred Work

- still manual and not strongly typed
- no machine-readable simulation summary yet

---

## Step 3 — Python Simulation Automation

### Goal

Automate Icarus Verilog compilation and `vvp` simulation through Python so the project no longer depended on manual tool invocation.

### Why This Step Was Needed

Once the examples were trusted, the next bottleneck was repeatability. Manually invoking `iverilog` and `vvp` is fine for a quick experiment, but not for a system that eventually needs to orchestrate multiple tools and AI outputs.

### What We Implemented

The simulation flow was wrapped in reusable Python logic that:

- resolves input paths safely
- compiles with `iverilog`
- runs the output with `vvp`
- captures stdout and stderr
- tracks durations
- handles tool-not-found and timeout cases

A CLI wrapper was then placed on top so the project could be used both:

- as reusable Python code
- from the command line

### Files Created

`src/rtl_assistant/hardware_tools/iverilog.py`

- reusable Icarus Verilog adapter
- contains subprocess-based compile and simulation execution
- handles path resolution, timeout behavior, and output capture
- later became the reusable core used by the standalone simulation CLI and unified verification pipeline

`scripts/run_simulation.py`

- thin command-line wrapper around the reusable simulation adapter
- keeps automation accessible without duplicating core logic

### Files Modified

`src/rtl_assistant/hardware_tools/__init__.py`

- later exports the Icarus adapter alongside the other hardware-tool modules
- helps keep tool orchestration modular rather than CLI-driven

### Architecture / Flow

```text
RTL + testbench
→ Python Icarus adapter
→ compile
→ simulate
→ reusable simulation result
```

### Manual Validation Performed

The automated simulation path was manually exercised on the existing examples to confirm:

- compile commands were formed correctly
- simulation launched correctly
- stdout and stderr were captured
- missing-file and missing-tool conditions did not crash the program

### Problems Encountered

Several practical concerns had to be handled early:

- spaces in paths
- subprocess safety
- tool failures
- timeout behavior

### Fixes / Improvements

The automation used:

- argument lists instead of shell command strings
- `shell=False`
- explicit timeout handling
- typed error fields in the returned report data structure

### Key Engineering Decisions

- keep simulation logic separate from CLI code
- avoid calling one Python script from another through subprocess
- build the reusable function first, then let the CLI be a wrapper

### What We Learned

A hardware tool adapter should behave like an API boundary, not like a script that only humans can run manually.

### Final Outcome

The project could now launch simulation reproducibly from Python and from the command line.

### Limitations / Deferred Work

- results were not yet strongly typed enough to express nuanced simulation outcomes
- PASS/FAIL classification still needed care

---

## Step 4 — Structured Simulation Reports

### Goal

Convert raw simulation output into a typed Pydantic report with reliable PASS / FAIL / UNKNOWN semantics.

### Why This Step Was Needed

A compile exit code and a block of stdout are not enough to represent verification meaningfully. Functional simulation has subtleties:

- compilation can pass while simulation fails
- simulation can exit cleanly but still not prove functional success
- raw text matching can misclassify results

### What We Implemented

The simulation layer was upgraded to return a typed `SimulationReport` with fields covering:

- compile stage status
- simulation stage status
- final PASS / FAIL / UNKNOWN classification
- exit codes
- stdout and stderr
- timeout flags
- durations
- infrastructure error metadata

This phase also established an important classification rule:

```text
vvp exit code 0 does not automatically mean functional PASS
```

### Files Created

`src/rtl_assistant/models/simulation.py`

- typed Pydantic simulation model definitions
- establishes the project’s simulation status vocabulary
- validates the internal consistency of simulation outcomes

### Files Modified

`src/rtl_assistant/hardware_tools/iverilog.py`

- evolved from simple automation into typed report generation
- now classifies output lines instead of exposing only raw process results

`src/rtl_assistant/models/__init__.py`

- exports simulation types for clean reuse by CLIs and later orchestration layers

### Architecture / Flow

```text
compile + simulation output
→ classification logic
→ typed SimulationReport
→ PASS / FAIL / UNKNOWN
```

### Manual Validation Performed

Manual testing included cases where:

- compilation failed
- simulation failed functionally
- simulation succeeded
- output contained ambiguous text

The most important observed issue was a classifier bug where naive string matching looked for `"FAIL"` anywhere in the output.

### Problems Encountered

A previous classifier incorrectly treated text like:

```text
Failed tests: 0
```

as a functional failure, even though it was actually reporting zero failures.

### Fixes / Improvements

The classifier was refined to distinguish real failure indicators from benign summary text. This was one of the first places where small text-processing mistakes clearly affected verification correctness.

### Key Engineering Decisions

- represent uncertainty explicitly with `UNKNOWN`
- separate compile success from functional simulation success
- use Pydantic invariants so impossible combinations are harder to create accidentally

### What We Learned

Even deterministic tools often communicate through human-oriented text. Turning that text into reliable structured meaning takes careful classification logic.

### Final Outcome

Simulation results became typed, more trustworthy, and much easier to integrate into later pipeline stages.

### Limitations / Deferred Work

- no linting yet
- no synthesis yet
- still only one verification stage

---

## Step 5 — Verilator Linting

### Goal

Integrate Verilator as a deterministic lint and structural-quality check for RTL before or alongside simulation.

### Why This Step Was Needed

Simulation answers functional questions only for the cases exercised by the testbench. Linting catches a different class of issues:

- structural problems
- questionable coding style
- warnings that may indicate real mistakes

It also helped strengthen the idea that multiple deterministic tools are complementary, not interchangeable.

### What We Implemented

A reusable Verilator adapter and typed lint report were added. The implementation had to be cross-platform:

- Windows:
  - run Verilator through WSL
- macOS/Linux:
  - run Verilator natively

This phase also introduced shared platform adaptation helpers so Windows-to-WSL path conversion did not remain buried inside one tool adapter.

### Files Created

`src/rtl_assistant/models/lint.py`

- typed Pydantic lint report model
- expresses PASS / FAIL / UNKNOWN with warnings, errors, timeout state, and infrastructure failures

`src/rtl_assistant/hardware_tools/verilator.py`

- reusable Verilator adapter
- builds the correct command for Windows WSL or native Unix-like hosts
- parses Verilator warning and error lines into a structured report

`src/rtl_assistant/hardware_tools/platform.py`

- shared platform helper module
- contains host-mode detection, WSL command prefixing, and path adaptation
- avoids duplicating Windows-to-WSL logic across tool adapters

`scripts/run_lint.py`

- standalone CLI for lint-only execution
- exposes typed linting without requiring the full verification pipeline

### Files Modified

`src/rtl_assistant/hardware_tools/__init__.py`

- exports lint-related tool functions

`src/rtl_assistant/models/__init__.py`

- exports lint report types for clean reuse

`examples/*/*.sv`

- starter RTL examples were adjusted to satisfy strict lint expectations

### Architecture / Flow

```text
RTL
→ platform adapter
→ Verilator
→ typed LintReport
```

### Manual Validation Performed

The reference examples were linted manually to confirm:

- command construction worked across platforms
- warnings and errors were captured
- missing-tool and WSL-not-found conditions produced typed failures

An important observed warning was:

```text
%Warning-EOFNEWLINE
```

### Problems Encountered

Verilator warnings could affect overall lint result classification. A simple formatting issue, missing trailing newlines in source files, caused Verilator to emit `%Warning-EOFNEWLINE`.

### Fixes / Improvements

The example RTL files were updated to include proper trailing newlines so the baseline examples linted cleanly.

### Key Engineering Decisions

- treat Windows as a first-class target by routing Verilator through WSL
- keep raw stdout/stderr while also parsing warnings and errors
- distinguish tool availability failures from genuine lint findings

### What We Learned

Lint can fail for surprisingly small reasons, and those details matter when trying to build a clean baseline for later AI-generated code.

### Final Outcome

The project gained a second deterministic verification stage and a reusable cross-platform lint adapter.

### Limitations / Deferred Work

- no synthesis yet
- no unified overall verification result yet

---

## Step 6 — Yosys Synthesis

### Goal

Add deterministic synthesis checking and extract a useful subset of hardware-structure statistics from Yosys.

### Why This Step Was Needed

Passing simulation does not prove that RTL is synthesizable, and passing lint does not describe the inferred hardware structure. Yosys adds another complementary answer:

- can the design synthesize?
- what sort of structure is inferred?

This was important both for verification and for later AI-generated RTL evaluation.

### What We Implemented

A cross-platform Yosys adapter and typed synthesis report were added. The deterministic synthesis flow was intentionally simple:

```text
read_verilog -sv
→ hierarchy -check -top
→ proc
→ opt
→ memory
→ opt
→ stat
```

The adapter:

- uses the same shared Windows-to-WSL platform logic as Verilator
- handles missing files, missing tools, timeout, invalid top module, and startup failures
- preserves full raw stdout/stderr
- parses conservative warning/error information
- extracts a small stable subset of `stat` data

### Files Created

`src/rtl_assistant/models/synthesis.py`

- typed Pydantic synthesis report
- captures synthesis status, exit code, diagnostics, duration, timeout, infrastructure failures, and parsed statistics

`src/rtl_assistant/hardware_tools/yosys.py`

- reusable Yosys synthesis adapter
- builds the deterministic non-interactive synthesis command
- parses diagnostics and stable statistics from the `stat` section

`scripts/run_synthesis.py`

- standalone synthesis CLI
- prints a readable summary and optionally saves the validated report as JSON

### Files Modified

`src/rtl_assistant/hardware_tools/platform.py`

- reused for Yosys host adaptation in the same pattern as Verilator

`src/rtl_assistant/models/__init__.py`

- exports synthesis types

`src/rtl_assistant/hardware_tools/__init__.py`

- exports Yosys synthesis entry points

### Architecture / Flow

```text
RTL
→ platform adapter
→ Yosys deterministic flow
→ typed SynthesisReport
→ optional stat parsing
```

### Manual Validation Performed

Manual synthesis runs were performed on the reference examples. Notable observed results included:

ALU synthesis:

- PASS
- number of wires: 15
- number of wire bits: 38
- number of cells: 12
- inferred cell types included:
  - `$add`
  - `$sub`
  - `$and`
  - `$or`
  - `$pmux`

Counter synthesis:

- PASS
- inferred cells included:
  - `$add`
  - `$sdffe`

The `$sdffe` result was important because it reflected sequential storage with enable/reset-style behavior in a recognizably meaningful way.

### Problems Encountered

The main design challenge was deciding how much of Yosys output to parse. Over-parsing would make the feature brittle; under-parsing would make the report less useful.

### Fixes / Improvements

Only a conservative, stable subset of `stat` information was parsed:

- wire count
- wire-bit count
- cell count
- cell-type distribution

Everything else remained available in raw stdout/stderr for diagnosis.

### Key Engineering Decisions

- prioritize reliable synthesis success/failure detection over aggressive parsing
- reuse platform helpers instead of duplicating Windows/WSL logic
- keep synthesis independent from CLI and verification orchestration

### What We Learned

Synthesis statistics are useful, but only if they are parsed conservatively enough to remain trustworthy.

### Final Outcome

The project now had three complementary deterministic views of RTL:

- lint
- simulation
- synthesis

### Limitations / Deferred Work

- no unified verification model yet
- no single command to run all stages together yet

---

## Step 7 — Unified Deterministic Verification Pipeline

### Goal

Combine lint, simulation, and synthesis into one deterministic verification pipeline with a single typed overall result.

### Why This Step Was Needed

Once the three tool adapters existed, users still had to think about them separately. A real workflow needed:

- one orchestration layer
- one summary status
- one nested machine-readable report

This step was also the strongest proof of the project’s central thesis: one tool is not enough.

### What We Implemented

A `VerificationReport` model and a reusable orchestration module were added. The orchestration runs:

1. Verilator lint
2. Icarus compile/simulate
3. Yosys synthesis

and then derives:

- overall PASS if all three pass
- overall FAIL if any stage fails
- otherwise UNKNOWN

The pipeline was exposed both:

- as reusable Python logic
- through a standalone CLI

### Files Created

`src/rtl_assistant/models/verification.py`

- typed top-level verification report
- nests the lint, simulation, and synthesis reports
- validates the relationship between stage outcomes and overall status

`src/rtl_assistant/pipeline/verification.py`

- reusable orchestration layer
- calls existing tool adapters rather than duplicating execution logic
- computes final overall status from stage results

`src/rtl_assistant/pipeline/__init__.py`

- package initializer for the pipeline layer

`scripts/verify_rtl.py`

- unified CLI for end-to-end deterministic verification
- prints concise stage summaries and optionally writes nested JSON output

### Files Modified

`src/rtl_assistant/models/__init__.py`

- exports verification types

`src/rtl_assistant/hardware_tools/iverilog.py`

- simulation logic was kept reusable so the pipeline could call Python functions directly instead of launching CLI scripts through subprocess

### Architecture / Flow

```text
RTL
→ Verilator lint
→ Icarus compile/simulate
→ Yosys synthesis
→ VerificationReport
→ PASS / FAIL / UNKNOWN
```

### Manual Validation Performed

The most important manual experiment in the entire deterministic foundation was performed here:

The ALU OR behavior was deliberately broken by replacing:

```text
result = a | b;
```

with an incorrect AND-style implementation.

Observed result:

- Lint: PASS
- Simulation: FAIL
- Synthesis: PASS
- Overall: FAIL

### Problems Encountered

Without this experiment, it would have been easy to treat simulation, lint, or synthesis as redundant checks. They are not redundant.

### Fixes / Improvements

The pipeline semantics were intentionally kept strict:

- any FAIL forces overall FAIL
- UNKNOWN never overrides an explicit FAIL

### Key Engineering Decisions

- continue later stages where possible even if an earlier stage fails, because combined diagnostics are useful
- keep the orchestration thin and reuse the existing adapters
- preserve exact nested report field names rather than renaming data for cosmetic JSON output

### What We Learned

This step provided the clearest architectural proof in the project:

```text
syntactically valid and synthesizable hardware can still be functionally wrong
```

### Final Outcome

The repository gained a deterministic verification engine with one combined result and one nested typed report.

### Limitations / Deferred Work

- no AI integration yet
- verification still consumed manually written RTL

---

## Step 8 — Structured HardwareSpec

### Goal

Introduce a validated, machine-readable hardware specification that could serve as the contract between natural-language requirements and later AI-generated RTL.

### Why This Step Was Needed

Jumping directly from natural language to RTL would make later AI steps hard to validate and hard to debug. A structured intermediary was needed so that:

- requirements could be validated independently of generation
- future LLM output could be checked against a known schema
- deterministic tools and AI layers would share the same contract

### What We Implemented

A Pydantic v2 `HardwareSpec` schema was implemented along with supporting models and enums:

- `HardwareSpec`
- `PortSpec`
- `ParameterSpec`
- `ClockSpec`
- `ResetSpec`
- `BehaviorSpec`

Important enums added:

- combinational / sequential design type
- port direction
- port role
- positive / negative clock edge
- synchronous / asynchronous reset
- active-high / active-low reset

Cross-field validation was added for:

- valid simple SystemVerilog identifiers
- duplicate port rejection
- duplicate parameter rejection
- `width >= 1`
- sequential designs requiring a clock
- combinational designs rejecting clock/reset metadata in this version
- clock/reset signals matching valid input ports
- first-version single-bit clock/reset expectations

Example JSON specs were then created for the project’s core benchmark designs.

### Files Created

`src/rtl_assistant/models/hardware_spec.py`

- main typed hardware specification schema
- validates structure and cross-field consistency
- became the key contract between requirement parsing and later RTL generation

`examples/specs/mux_2to1.json`

- structured specification matching the reference MUX RTL

`examples/specs/alu_4bit.json`

- structured specification matching the reference ALU RTL and opcode behavior

`examples/specs/counter_4bit.json`

- structured specification matching the reference counter clock, reset, enable, and wrap behavior

`scripts/validate_spec.py`

- standalone CLI that validates a JSON file as a `HardwareSpec`
- prints concise human-readable summaries and returns a clean exit code

### Files Modified

`src/rtl_assistant/models/__init__.py`

- exports the HardwareSpec-related types

### Architecture / Flow

```text
natural-language intent or manual design description
→ HardwareSpec
→ validated structured contract
```

### Manual Validation Performed

The example JSON specs were checked against the schema. Important invalid-case testing was also done. One notable manual test changed an ALU input width to `0`, and Pydantic correctly rejected the spec with a width validation error.

### Problems Encountered

The main challenge was keeping the schema strict enough to be useful without making it so rigid that common design families would no longer fit.

### Fixes / Improvements

Validation focused on stable structural rules rather than over-modeling every possible hardware family.

### Key Engineering Decisions

- use one generic `ports` list instead of splitting inputs/outputs into separate top-level arrays
- keep behavior structured but still flexible through descriptions, operations, rules, and assumptions
- let Pydantic be the source of truth for schema validity

### What We Learned

The HardwareSpec layer is what makes later AI steps auditable. It gives the project a place to say, “the model produced something structured, but is it actually valid?”

### Final Outcome

The project gained a reusable structured hardware contract with example JSON specs and a validation CLI.

### Limitations / Deferred Work

- no natural-language parsing yet
- no RTL generation yet
- no testbench generation yet

---

## Step 9 — Local LLM Environment

### Goal

Set up a local LLM environment that could support requirement parsing and later RTL generation without depending on a cloud API.

### Why This Step Was Needed

The project roadmap required AI assistance, but using a local model had several benefits:

- privacy
- low-cost experimentation
- offline or near-offline development
- easier capstone demonstration without external API dependencies

### What We Implemented

Ollama was installed locally on Windows and configured so the project could use the local HTTP API at `http://localhost:11434`.

Important available models included:

- `qwen2.5-coder:7b`
- `llama3.1:8b` also being present in the local environment

`qwen2.5-coder:7b` was chosen as the main local coding model for the project.

### Files Created

No permanent repository source files were strictly required for the environment setup itself. This phase mostly established the external local runtime that later source code would target.

### Files Modified

Repository code changes came in the next step. This step mainly prepared the environment and validated the chosen local model setup.

### Architecture / Flow

```text
Local Ollama runtime
→ HTTP API
→ future provider-neutral project integration
```

### Manual Validation Performed

Manual checks confirmed:

- `ollama run` worked
- the Ollama HTTP API was reachable
- `/api/tags` returned local model availability

### Problems Encountered

A notable model-quality observation appeared early: the model incorrectly described a 4-bit counter as having four states instead of sixteen.

### Fixes / Improvements

This did not produce a code fix yet, but it strongly reinforced an architectural decision that had already been planned:

```text
LLM output must be treated as untrusted input
```

### Key Engineering Decisions

- prefer a local provider for the first AI layer
- keep later code provider-neutral so Ollama is not hardwired into the rest of the architecture

### What We Learned

Even when a model sounds confident, basic digital-design reasoning can still be wrong. That observation justified the entire deterministic validation strategy.

### Final Outcome

The project had a working local LLM environment ready to be integrated through a provider abstraction.

### Limitations / Deferred Work

- no provider-neutral code yet
- no requirement parser yet
- no RTL generation yet

---

## Step 10 — AI Requirement Parsing

### Goal

Convert natural-language hardware requirements into validated `HardwareSpec` objects using a provider-neutral local LLM architecture.

### Why This Step Was Needed

HardwareSpec was useful, but still had to be written by hand. To move toward the intended workflow, the project needed its first real AI layer:

```text
natural-language requirement
→ structured spec
```

### What We Implemented

A provider-neutral LLM layer and requirement parser were created. Key behavior:

```text
natural-language requirement
→ LLMProvider
→ OllamaProvider
→ JSON
→ HardwareSpec validation
→ RequirementParseResult
```

The parser included:

- JSON-only prompting
- fence-tolerant extraction
- Pydantic validation as the source of truth
- at most two attempts
- a repair prompt when initial JSON or schema output was malformed

Provider errors were also turned into typed results rather than uncaught exceptions.

### Files Created

`src/rtl_assistant/models/llm.py`

- typed models for provider responses and requirement parsing results
- defines structured failure and success data for the AI parsing layer

`src/rtl_assistant/llm/base.py`

- provider-neutral abstract LLM interface
- keeps the parser independent from any one provider

`src/rtl_assistant/llm/ollama.py`

- local Ollama implementation of the provider interface
- handles local HTTP requests, response capture, and typed provider errors

`src/rtl_assistant/llm/__init__.py`

- package export surface for the LLM layer

`src/rtl_assistant/spec/prompts.py`

- versioned prompt builder for requirement parsing
- centralizes JSON schema instructions instead of scattering prompt text

`src/rtl_assistant/spec/ai_parser.py`

- reusable requirement parser
- combines prompt generation, provider calls, JSON extraction, and HardwareSpec validation

`src/rtl_assistant/spec/__init__.py`

- package initializer for the specification/AI parsing layer

`scripts/parse_requirement.py`

- CLI for turning a requirement string into a validated `HardwareSpec`

`scripts/test_llm.py`

- small connectivity script that isolates provider/API testing from HardwareSpec parsing logic

### Files Modified

`src/rtl_assistant/models/__init__.py`

- exports LLM- and parser-related types

### Architecture / Flow

```text
Requirement text
→ versioned parsing prompt
→ LLMProvider
→ JSON extraction
→ HardwareSpec validation
→ RequirementParseResult
```

### Manual Validation Performed

Detailed prompts were manually tested and successfully produced valid HardwareSpecs for:

- MUX
- 4-bit ALU
- detailed synchronous counter

### Problems Encountered

Even when the parser succeeded, quality issues appeared. One observed example was a valid but awkward generated module name for the mux:

```text
mux_1to2_1bit
```

This was not structurally invalid, but it showed that style and naming consistency would matter in later refinement steps.

### Fixes / Improvements

Robustness was built around:

- JSON-only instructions
- code-fence stripping
- maximum two attempts
- repair prompts for malformed JSON or schema mismatch
- typed error categories for provider failures

### Key Engineering Decisions

- keep the parser dependent only on `LLMProvider`
- do not trust valid JSON unless `HardwareSpec` also validates
- version prompts from the first AI step onward

### What We Learned

Structured generation becomes much more manageable when the output target is a schema, not free-form text.

### Final Outcome

The project could now turn sufficiently detailed natural-language requests into validated `HardwareSpec` objects.

### Limitations / Deferred Work

- no ambiguity handling yet
- vague prompts could still be unsafe
- no RTL generation yet

---

## Step 11 — Ambiguity and Clarification Handling

### Goal

Prevent the requirement parser from silently inventing important hardware semantics when the user request is underspecified.

### Why This Step Was Needed

Step 10 proved that a detailed prompt could produce a valid `HardwareSpec`, but it also exposed a dangerous failure mode:

```text
valid HardwareSpec does not mean the user actually specified the behavior
```

Schema validation alone could not distinguish:

- explicitly requested behavior
- model-invented behavior

### What We Implemented

This step evolved through several iterations. The final architecture became:

```text
requirement
→ requirement analysis
→ if critical ambiguities remain:
   → NEEDS_CLARIFICATION
   → structured clarification questions
→ otherwise:
   → HardwareSpec generation
   → HardwareSpec validation
   → READY
```

Important additions included:

- `RequirementStatus`
  - `READY`
  - `NEEDS_CLARIFICATION`
  - `FAIL`
- `RequirementAnalysis`
- `ClarificationQuestion`
- updated `RequirementParseResult`
- ambiguity-analysis prompts
- clarification-answer composition support
- local ambiguity safety policy
- canonical ambiguity IDs
- explicit-detail detection
- deduplication between LLM analysis and local policy

### Files Created

No major brand-new package was required beyond the Step 10 parsing layer, but the existing parsing models and logic were significantly expanded.

### Files Modified

`src/rtl_assistant/models/llm.py`

- expanded from basic provider and parse-result typing into a richer ambiguity-aware result model
- now carries clarification questions, unresolved fields, assumptions, and status distinctions

`src/rtl_assistant/spec/prompts.py`

- gained dedicated versioned prompts for ambiguity analysis and repair
- encodes the distinction between “analyze what is missing” and “generate final JSON”

`src/rtl_assistant/spec/ai_parser.py`

- became the main implementation site for:
  - ambiguity analysis
  - local policy merging
  - canonical ambiguity mapping
  - explicit-detail detection
  - question deduplication
  - safe normalization before strict validation

`scripts/parse_requirement.py`

- updated to print clarification questions when the result is `NEEDS_CLARIFICATION`
- now uses exit codes:
  - `0` for `READY`
  - `1` for `FAIL`
  - `2` for `NEEDS_CLARIFICATION`

### Architecture / Flow

```text
Requirement
→ ambiguity analysis
→ merge with local safety policy
→ deduplicate canonical ambiguities
→ READY or NEEDS_CLARIFICATION
→ only READY proceeds to final HardwareSpec generation
```

### Manual Validation Performed

This step was tested heavily with both detailed and vague prompts.

Initial unsafe case:

```text
Create a counter.
```

The earlier parser silently invented:

- clock signal
- positive clock edge
- reset
- asynchronous reset
- active-low reset
- other unspecified behavior

After the clarification system matured, the observed behavior became:

- detailed counter: `READY`
- detailed one-bit MUX: `READY`
- vague ALU: `NEEDS_CLARIFICATION`
- partial ALU:
  - `Create an unsigned 8-bit ALU supporting ADD, SUB, AND and OR.`
  - unresolved critical item correctly reduced to `opcode_mapping`
- vague counter:
  - `Create a counter.`
  - `NEEDS_CLARIFICATION` with deduplicated questions and exit code `2`

### Problems Encountered

This step had the richest sequence of discovered bugs.

Initial problems:

- a fully specified counter incorrectly asked about signedness
- a fully specified one-bit MUX incorrectly asked about width
- vague counter and ALU prompts produced duplicate questions because the LLM and local policy named the same concept differently

Examples of duplicated semantics included:

- `state width`
- `counter_width`
- `width`

and:

- `operand width`
- `alu_width`
- `behavior.operations`
- `supported operations`

Another failure appeared when the LLM returned:

```text
choices: "yes / no"
```

instead of a JSON list, which caused strict Pydantic validation to fail even though the semantic intent was obvious.

### Fixes / Improvements

Several important improvements were added:

1. Family-specific ambiguity policies

- counter
- ALU
- mux

2. Canonical ambiguity IDs

Examples:

- `counter_width`
- `clock_edge`
- `reset_presence`
- `count_direction`
- `alu_width`
- `alu_signedness`
- `alu_operations`
- `opcode_mapping`
- `mux_data_width`
- `mux_select_mapping`

3. Explicit-detail detection in natural language

Examples that now resolve ambiguities automatically:

- `one-bit`
- `4-bit counter`
- `positive-edge`
- `active-high synchronous reset`
- `up-counter`
- `wraps from 15 to 0`
- `unsigned 8-bit ALU`
- `ADD, SUB, AND and OR`

4. Deduplication and normalization

The system now maps semantically similar LLM-produced fields into canonical concepts and emits at most one final clarification question per concept.

5. Safe pre-validation normalization for `choices`

Accepted examples include:

- `null` → `[]`
- `"yes / no"` → `["yes", "no"]`
- `"positive / negative"` → `["positive", "negative"]`
- comma-, slash-, or pipe-separated strings
- single strings → one-item list

This repair is intentionally narrow. It fixes obvious representation mismatches without inventing missing hardware decisions.

### Key Engineering Decisions

- Pydantic validation alone is not enough to detect invented semantics
- ambiguity analysis must happen before final spec generation
- clock/reset signal naming can be treated as lower-risk assumptions than behavioral semantics
- explicit FAIL, READY, and NEEDS_CLARIFICATION states are more honest than a single “success/failure” result

### What We Learned

This step clarified a deep lesson:

```text
internal consistency is not the same thing as user intent fidelity
```

The project needed both schema validation and ambiguity detection.

### Final Outcome

The parser no longer silently invents critical behavior for vague requirements. Ambiguous input now produces structured clarification questions instead of an unjustified “valid” HardwareSpec.

### Limitations / Deferred Work

- clarification is not yet interactive
- the system still relies on LLM analysis, so prompt quality remains important
- no RTL generation from HardwareSpec yet in the completed pipeline

---

## Step 12 — AI RTL Generation

**Status: Complete**

### Goal

Generate synthesizable SystemVerilog RTL from a validated `HardwareSpec` using the local LLM, while keeping the output typed and subject to local sanity checks.

### Why This Step Was Needed

After Step 10 and Step 11, the project could turn natural language into a validated structured specification. The next logical step was:

```text
validated HardwareSpec
→ SystemVerilog RTL
```

This is the first phase where the LLM starts producing actual HDL rather than only structured JSON.

### What We Implemented

The current Step 12 flow is:

```text
HardwareSpec
→ versioned RTL prompt
→ LLMProvider
→ raw model text
→ safe RTL extraction
→ lightweight sanity checks
→ RTLGenerationResult
```

The LLM receives the structured `HardwareSpec`, not the original vague user requirement. That is an important architectural improvement because generation now starts from a validated contract.

### Files Created

`src/rtl_assistant/models/rtl_generation.py`

- typed generation result model for RTL generation
- represents success/failure, provider/model metadata, attempts, duration, raw output, and error information

`src/rtl_assistant/rtl/prompts.py`

- versioned prompt builder for HardwareSpec-to-RTL generation
- centralizes rules for interface fidelity, synthesizability, and output format

`src/rtl_assistant/rtl/generator.py`

- provider-neutral RTL generator implementation
- performs prompt construction, provider calls, RTL extraction, sanity checks, and limited retry behavior

`src/rtl_assistant/rtl/__init__.py`

- package initializer for the RTL generation layer

`scripts/generate_rtl.py`

- CLI that reads a validated HardwareSpec JSON file, invokes the generator, prints status, and optionally saves the generated `.sv` file

### Files Modified

`src/rtl_assistant/models/__init__.py`

- exports RTL generation result types

### Architecture / Flow

```text
Validated HardwareSpec
→ RTL generation prompt
→ LLMProvider
→ extract module ... endmodule
→ sanity checks
→ RTLGenerationResult
```

### Manual Validation Performed

Manual generation was performed for the project’s three benchmark specs:

- MUX generation: SUCCESS
- ALU generation: SUCCESS
- counter generation: SUCCESS

The refinement history is worth preserving because it explains the final prompt rules:

Initial MUX result:

- one-bit signals were emitted using `[0:0]` syntax

Initial ALU result:

- procedurally assigned outputs were not consistently declared as `logic`

Initial counter result:

- generated RTL included a redundant hold assignment such as `count <= count;`

After prompt and sanity refinements, the final manual results were:

- MUX:
  - clean scalar `logic` interface for one-bit ports
  - correct combinational behavior
- ALU:
  - clean `output logic` declarations for procedurally assigned outputs
  - correct opcode behavior
- Counter:
  - correct `posedge` clocking
  - synchronous active-high reset
  - enable-controlled update
  - wraparound behavior

### Problems Encountered

The main issues found during manual source inspection were quality issues rather than total generation failures:

1. One-bit ports were sometimes emitted as:

```text
[0:0]
```

which is legal but unnecessarily noisy.

2. Procedurally assigned outputs were not always emitted as explicit `logic`, which is undesirable in modern SystemVerilog and can become confusing when assigned inside `always_comb` or `always_ff`.

3. Sequential hold behavior could be expressed with redundant self-assignment such as:

```text
count <= count;
```

which is not functionally wrong, but is less clean than simply omitting the assignment in the hold case.

### Fixes / Improvements

The prompt was tightened to prefer modern, conservative SystemVerilog:

- `logic` instead of legacy `reg`
- `output logic` for procedurally assigned outputs
- scalar syntax for width-1 ports
- no unnecessary self-assignment such as `count <= count;`

A lightweight sanity check was also added for obvious procedural-output declaration issues.

Lightweight local sanity checks now exist for:

- missing module
- multiple modules
- module-name mismatch
- missing required ports
- obvious simulation/testbench constructs

### Key Engineering Decisions

- keep RTL generation separate from requirement parsing
- keep the generator provider-neutral
- do not yet connect generation directly to lint/simulation/synthesis
- treat generated RTL as untrusted text, not executable logic

### What We Learned

A valid-looking HDL block can still have quality issues that matter for readability and style. Prompting and light sanity checks help, but they are not replacements for deterministic verification.

### Final Outcome

The project can now take a validated `HardwareSpec` and generate a single synthesizable SystemVerilog module through the local LLM, with exact module/interface constraints, conservative extraction, lightweight sanity checks, and at most one repair attempt. Manual MUX, ALU, and counter generations produced clean RTL after prompt-quality refinements.

### Limitations / Deferred Work

- not yet connected to deterministic verification
- no testbench generation
- no automatic repair loop based on Verilator/Icarus/Yosys feedback
- later steps still need verification-loop integration and broader evaluation

---

## Step 13 — Verification Plan Generation

**Status: Complete**

### Goal

Generate a structured verification plan from a validated `HardwareSpec` so the project can explicitly represent what should be tested before generating any SystemVerilog testbench code.

### Why This Step Was Needed

Jumping directly from `HardwareSpec` to arbitrary testbench generation would hide an important intermediate decision:

```text
What behaviors are we actually planning to verify?
```

The verification plan exists so the project can:

- inspect whether critical behavior is covered
- compare AI-generated plans independently of testbench syntax
- reason about missing coverage later
- make future testbench generation more deterministic

### What We Implemented

The current Step 13 flow is:

```text
Validated HardwareSpec
→ local LLM
→ JSON-only verification-plan generation
→ Pydantic validation
→ deterministic expected-value resolution where semantics are machine-computable
→ lightweight sanity checks
→ typed VerificationPlanGenerationResult
```

The output is a structured verification intent, not SystemVerilog code. It describes:

- strategy
- test cases
- expected outcomes
- coverage targets
- assumptions

### Files Created

`src/rtl_assistant/models/verification_plan.py`

- typed Pydantic models for the verification-plan schema and generation result
- separates the plan itself from the AI execution metadata

`src/rtl_assistant/verification_plan/prompts.py`

- versioned prompt builder for plan generation and repair
- feeds the full validated `HardwareSpec` JSON to the model

`src/rtl_assistant/verification_plan/generator.py`

- provider-neutral verification-plan generator
- performs JSON extraction, Pydantic validation, deterministic expected-value canonicalization, lightweight sanity checks, and one repair attempt

`src/rtl_assistant/reference/base.py`

- abstract deterministic reference-resolution interface
- defines the provider-neutral contract for future richer reference-model work

`src/rtl_assistant/reference/resolver.py`

- handler-based deterministic expected-value resolver
- currently supports machine-computable verification semantics such as fixed-width ALU arithmetic/logic, simple routed combinational outputs, one-hot decoding, and simple counter transitions

`src/rtl_assistant/reference/__init__.py`

- export surface for the deterministic reference layer

`src/rtl_assistant/verification_plan/__init__.py`

- export surface for the verification-plan package

`scripts/generate_verification_plan.py`

- CLI for generating a verification plan from a HardwareSpec JSON file
- prints a concise summary and optionally writes the validated plan to disk

### Files Modified

`src/rtl_assistant/models/__init__.py`

- exports verification-plan-related types

`src/rtl_assistant/models/reference.py`

- adds typed deterministic-resolution and correction-trail models
- preserves structured visibility when AI-proposed expected values are canonicalized

`PROJECT_LOG.md`

- updated with the new Step 13 entry and project-status tracking

### Architecture / Flow

```text
HardwareSpec
→ verification-plan prompt
→ LLMProvider
→ JSON extraction
→ VerificationPlan validation
→ deterministic expected-value resolver
→ lightweight sanity checks
→ VerificationPlanGenerationResult
```

### Manual Validation Performed

Manual validation covered both the original benchmark designs and unseen generalization cases.

Observed successful cases:

- MUX verification-plan generation succeeded.
- ALU verification-plan generation succeeded after deterministic semantic validation improvements.
- unseen `decoder_3to8` succeeded and covered all 8 mappings.
- unseen `shift_register_4bit` succeeded, including sequential semantics such as asynchronous active-low reset and shifting behavior.

Important observed limitation:

- counter generation demonstrated nondeterminism from the local `qwen2.5-coder:7b` model
- some runs generated valid plans
- other runs attempted illegal direct state or output assignment
- other runs failed to establish required sequential preconditions

Those invalid plans were correctly rejected by deterministic validation rather than being passed downstream.

### Problems Encountered

This step is being designed to avoid a known future risk:

- if testbench generation starts directly from prose or loosely structured AI output, it becomes much harder to inspect whether important behaviors were omitted
- the local model returned scalar strings for list-typed verification-plan fields such as `setup`, `stimulus`, `expected`, and `covers`
- strict Pydantic validation rejected those scalar representations even when the underlying test intent was semantically useful
- after fixing scalar strings, raw inspection showed that the model could also emit dictionary-style `setup` and `expected` fields and object-style `coverage_targets`
- after the schema-shape issues were fixed, the ALU plan became structurally inspectable but still contained mathematically incorrect expected values
- examples included:
  - unsigned values incorrectly described as negative
  - `3 - 5` incorrectly expected as `2` instead of the fixed-width unsigned wrap result
  - `10 AND 6` incorrectly expected as `6`
  - a required carry-producing ADD case was absent
- after those issues were improved, manual inspection still found `0 - 15` incorrectly expected as `15` instead of `1`
- this proved that one-off arithmetic checks tied only to previously seen bad vectors were too narrow
- counter plan passed schema validation but attempted to drive output state directly
- it also contained mathematically incorrect clock-cycle expectations
- synchronous reset semantics were described too loosely
- this showed that structurally valid sequential plans can still violate legal hardware stimulus rules
- sequential plan used clock levels like `clk=1` instead of explicit active edges
- reset checker initially treated tests containing inactive `rst=0` as reset tests, which created false positives
- final counter issue: some tests could still implicitly depend on state established by a previous test instead of being independently reproducible
- after rejecting explicit `drive/set/force` on outputs, the model still used bare output assignments such as `count=15` as state setup
- the deterministic validator could correctly identify missing sequential preconditions, but the repair attempt could still rephrase the plan without actually fixing the semantic cause
- repeated testing showed that even after semantic repair prompts, the local model could still miscalculate deterministic hardware expectations such as fixed-width subtraction, bitwise results, and status flags
- the validator safely rejected those plans, but relying on repeated LLM regeneration reduced repeatability and made correct-plan production more model-quality dependent than necessary
- initial integration of the deterministic reference layer exposed an operation-resolution bug
- opcode literals were parsed, but strict opcode-to-operation resolution was not enforced correctly, and unsupported cases could fall through into unsafe operation guessing
- this caused several ALU vectors to be canonicalized incorrectly during early deterministic-reference integration

Engineering lesson:

```text
Schema validity does not imply verification-plan correctness.
```

```text
A semantic guardrail should validate the rule, not memorize one previously observed failure.
```

```text
A valid verification plan must respect both functional behavior and the legal way hardware state can be reached.
```

```text
A clock level is not a clock event, and an inactive reset assignment is not a reset test.
```

```text
Changing the wording of an illegal action does not make the hardware action legal.
```

```text
Verification tests should be independently reproducible rather than depending on execution order.
```

```text
A useful retry loop must repair the cause of an error, not merely regenerate different wording.
```

```text
Schema validity does not make the LLM a trustworthy arithmetic or logic oracle.
```

```text
Deterministic does not automatically mean correct. A reference model must itself be validated before it becomes a source of truth.
```

### Fixes / Improvements

The current implementation addresses that by making verification intent explicit through:

- typed test-case structures
- explicit coverage targets
- separation between plan content and generation metadata
- lightweight checks for obvious omissions such as reset or operation coverage
- narrow pre-validation normalization for obvious scalar-to-list representation mismatches before strict schema validation
- deterministic dict-to-readable-string normalization for dictionary-shaped setup, stimulus, expected, covers, assumptions, notes, and coverage target fields
- tighter prompt instructions that explicitly require JSON arrays of strings for the list-typed verification-plan fields
- category canonicalization so wording such as `LOGIC` or `ZERO_BEHAVIOR` maps into the existing enum vocabulary instead of failing purely on label choice
- stronger prompt instructions that emphasize unsigned semantics, mathematically correct expected values, and the requirement for an actual carry-producing ADD test when carry behavior exists
- lightweight sanity guardrails for signedness contradictions, missing carry-assert coverage, and a few obvious arithmetic inconsistencies
- replaced narrow special-case arithmetic checks with generic literal-vector consistency checking for simple explicit ADD, SUB, AND, and OR examples already present in generated ALU verification plans
- added output-direction safety checks so verification plans cannot directly drive DUT outputs
- added active-clock-event checks for sequential state-transition tests
- added synchronous-reset semantic guardrails that require an active clock edge for synchronous reset tests
- added small counter transition consistency checking for simple literal counter sequences
- strengthened the sequential verification-plan prompt guidance so state must be reached through legal inputs and clock transitions
- reset-test detection became polarity-aware and now triggers only on actual reset behavior
- active-clock detection now distinguishes clock edges from clock levels
- prompt guidance now asks for logical active-edge events rather than manual clock-level toggling
- counter setup guidance was tightened so state is reached legally and concisely
- prompt guidance now emphasizes independently reproducible sequential tests with legal state preparation or explicit legal preconditions
- a conservative `UNESTABLISHED_PRECONDITION` guardrail was added for counter-style hold and wrap tests that expect nontrivial state without establishing it
- two unseen generalization benchmarks were added:
  - `decoder_3to8`
  - `shift_register_4bit`
- their purpose is to check that Step 13 generalizes beyond MUX, ALU, and counter rather than being overfitted to the original examples
- output-direction safety now also rejects bare assignment-style writes to DUT outputs in setup/stimulus while still allowing descriptive legal preconditions
- repair prompting was strengthened so validation errors must be repaired semantically, including legally establishing or explicitly stating required sequential state
- introduced a deterministic expected-value/reference layer between AI-generated verification intent and final plan acceptance
- the LLM remains responsible for proposing test intent, vectors, and legal stimulus structure
- deterministic code is intended to become authoritative for expected outputs whenever semantics can be proven from structured information and the resolver itself has been validated
- deterministic corrections are tracked structurally so later evaluation can measure where AI-proposed expected values needed canonicalization
- current deterministic handlers safely support:
  - fixed-width unsigned ALU ADD, SUB, AND, OR, plus carry/zero where derivable
  - simple select-routing combinational behavior
  - one-hot decoder outputs
  - simple fixed-width counter transitions with explicit starting state and active-edge information
- expected engineering benefits of this layer are:
  - fewer arithmetic hallucinations
  - fewer unnecessary LLM retries
  - higher repeatability across runs
  - stronger portability across future LLM providers
  - a natural foundation for richer Step 15 reference models
- unsupported semantics degrade safely instead of being guessed

### Key Engineering Decisions

- keep verification-plan generation separate from deterministic verification execution
- keep the generator provider-neutral
- validate the plan as data before later generating any testbench code
- do not treat the plan as executable or authoritative until validated
- avoid module-name-specific fixes; derive deterministic expectations from `HardwareSpec`, explicit literals, and structured behavior where possible

### What We Learned

There is value in separating:

```text
what should be tested
```

from:

```text
how that testbench will eventually be written
```

This step also clarified an important architectural principle for later work:

```text
AI proposes the test.
Deterministic logic computes the answer.
```

### Final Outcome

The repository now contains a completed structured verification-plan generation layer.

The architectural goal of Step 13 is not to guarantee that an untrusted LLM always generates a valid verification plan. The goal is to:

- produce a typed `VerificationPlan` when the generated plan is valid
- safely reject the plan when structural or semantic checks fail
- deterministically canonicalize machine-computable expected values before final acceptance when the `HardwareSpec` semantics make that safe

This goal was achieved across both the original examples and unseen benchmark families.

### Limitations / Deferred Work

- no SystemVerilog testbench generation yet
- no deterministic execution of the plan yet
- no coverage scoring or coverage-gap analysis yet
- the current deterministic reference layer only handles semantics it can prove from structured information
- the deterministic reference layer itself still requires explicit validation because early integration exposed an ALU operation-resolution bug that produced incorrect canonicalized expectations
- unsupported reference semantics are intentionally not approximated or guessed
- the current local 7B model may fail to repair a semantically invalid verification plan within the two-attempt retry budget
- this is treated as a model-quality limitation rather than something to solve by continually adding more design-specific validator rules

```text
Unsupported reference semantics must degrade safely, not be approximated confidently.
```

### What We Learned

```text
Safe failure is preferable to confidently accepting an invalid AI-generated verification strategy.
```

Future evaluation can measure:

- first-attempt success rate
- repair success rate
- final valid-plan rate
- semantic rejection rate

across different hardware families and potentially different LLMs.

---

## Step 14 — Testbench Generation

**Status: In Progress**

### Goal

Generate a self-checking SystemVerilog testbench from:

```text
HardwareSpec
+
VerificationPlan
```

so that later deterministic simulation can execute the proposed verification strategy against the DUT.

### Why This Step Was Needed

A generated RTL design cannot be trusted without executable verification. Even a good verification plan is still only intent until it becomes a runnable self-checking testbench.

### What We Implemented

The current Step 14 architecture is:

```text
HardwareSpec + validated VerificationPlan
→ structured TestbenchPlan / IR
→ deterministic renderer
→ lightweight deterministic structural validation
→ SUCCESS / FAIL
```

The public/default generator no longer depends on Ollama once a valid `VerificationPlan` already exists.

The current implementation treats the VerificationPlan as the authoritative description of what must be tested, then deterministically translates that plan into executable SystemVerilog structure. This replaced the earlier direct:

```text
HardwareSpec + VerificationPlan
→ local LLM
→ arbitrary SystemVerilog formatting
```

path as the default production flow.

The deterministic path now provides:

- typed result model
- typed Testbench IR
- deterministic translator from plan text to structured actions/checks
- deterministic SystemVerilog renderer
- structural validation
- offline operation once the plan exists

The earlier direct-AI testbench generator was kept in the repository as legacy/internal code rather than being deleted immediately, but it is no longer the default Step 14 path.

### Files Created

`src/rtl_assistant/models/testbench_generation.py`

- typed status/result model for testbench generation
- now distinguishes deterministic generation from legacy AI generation
- captures provider/model metadata only when AI generation is actually used
- records test count and validation failures for deterministic rendering too

`src/rtl_assistant/testbench/ir.py`

- typed intermediate representation for executable testbench intent
- defines structured actions, checks, and per-test execution shape
- creates a safer boundary between verification intent and final SystemVerilog syntax

`src/rtl_assistant/testbench/translator.py`

- deterministic translator from `VerificationPlan` text into the structured Testbench IR
- parses legal input assignments, expected checks, settle steps, and supported sequential actions
- fails explicitly when a plan action cannot be translated safely

`src/rtl_assistant/testbench/renderer.py`

- deterministic SystemVerilog renderer
- derives DUT declarations and port mapping directly from `HardwareSpec`
- emits one main stimulus process, inline checks, final summary, and `$finish`

`src/rtl_assistant/testbench/deterministic.py`

- default Step 14 generator
- orchestrates translation, rendering, and lightweight structural validation
- returns typed `TestbenchGenerationResult` values in deterministic mode

`src/rtl_assistant/testbench/prompts.py`

- legacy prompt builder for the earlier direct-AI testbench path
- preserved for internal fallback/experimentation, but no longer the default rendering route

`src/rtl_assistant/testbench/generator.py`

- legacy direct-AI testbench generator
- kept during the refactor rather than removed immediately, but no longer used by the default CLI flow

`src/rtl_assistant/testbench/__init__.py`

- package export surface for both deterministic and legacy AI generator entry points

`scripts/generate_testbench.py`

- CLI entry point for deterministic translation/rendering and file output
- saves a `.sv` file only when generation succeeds
- does not require Ollama in the default path

### Files Modified

`src/rtl_assistant/models/__init__.py`

- exports testbench-generation result types
- exports deterministic/AI generation mode metadata for downstream reporting

`PROJECT_LOG.md`

- updated to add Step 14 and reflect the current architecture

### Architecture / Flow

```text
HardwareSpec + VerificationPlan
→ deterministic translation
→ Testbench IR
→ deterministic SystemVerilog rendering
→ lightweight deterministic validation
→ TestbenchGenerationResult
```

### Trust Boundary

The trust boundary changed significantly during this step:

```text
AI may help produce the VerificationPlan.
Deterministic code decides how that plan becomes executable SystemVerilog.
```

Step 14 does not execute the generated testbench inside the generator. Execution and correctness are still determined later by deterministic simulation and hardware-tool validation.

### Manual Validation Performed

Manual generation/execution results have not been recorded yet for the new deterministic rendering path. Step 14 remains in progress until manual MUX, ALU, decoder, counter, and shift-register generation is inspected and later exercised through the existing deterministic toolchain.

### Problems Encountered

Repeated direct AI generation exposed a pattern:

- the first combinational MUX testbench unnecessarily invented a clock signal and clock generator even though the HardwareSpec had no clock
- generated combinational tests could be placed in separate concurrent `initial` blocks, creating races on shared DUT inputs
- a generated testbench could silently omit VerificationPlan test cases instead of implementing the full plan
- the LLM could treat `#1` as a generic line prefix and place delays before structural SystemVerilog keywords such as `begin`, `end`, or `else`, producing invalid syntax
- generated self-checking expressions could use English `and`
- multiple output mismatch predicates could be combined with AND semantics, allowing a test to pass when only some checked outputs were wrong
- a shared helper task could incorrectly assume every test checked the same set of DUT outputs
- tests with partial expected-output sets could therefore produce invalid task calls
- inventing an expected value for an output absent from the VerificationPlan would also weaken verification semantics
- helper-task abstraction made planned checks difficult to validate structurally without interprocedural analysis
- fixed helper signatures also pressured the model to invent expectations for outputs absent from individual VerificationPlan tests
- deterministic translation initially treated every bare numeric token as decimal
- encoded control values such as a 2-bit `10` opcode could therefore be misinterpreted as decimal ten instead of a structured binary control token
- symbolic expected relationships such as `y equals a` were not representable in the first deterministic translator pass
- binary-looking expected bit vectors such as `y=00001000` could be misread as decimal text instead of width-matched binary output values
- harmless clock phrase variants such as `clk rising edge` were not normalized into the existing active-edge IR action

The architectural conclusion was that the LLM was being asked to do too much low-level deterministic formatting work.

### Fixes / Improvements

Step 14 was therefore refactored around a deterministic renderer.

The current deterministic path now:

- translates validated `VerificationPlan` entries into a typed executable Testbench IR
- renders DUT declarations directly from `HardwareSpec` using exact widths and `logic`
- renders named DUT port mappings directly from `HardwareSpec`
- renders one deterministic main stimulus sequence
- renders an optional separate clock process only for sequential DUTs with a clock
- renders inline checks that compare exactly the outputs listed in each VerificationPlan test
- renders a fixed final pass/fail summary and `$finish`

Lightweight post-render validation remains as defense in depth:

- exactly one testbench module
- DUT instantiation presence
- required port mapping
- no obvious DUT output driving
- no missing VerificationPlan test ids
- no missing expected-output checks
- no multiple concurrent DUT-driving stimulus processes
- clock/reset infrastructure present where required
- deterministic final summary and `$finish`

This refactor means the default Step 14 path no longer depends on the model to decide:

- how many `initial` blocks to use
- how to place delays
- how to structure mismatch predicates
- how to format helper-task signatures
- whether every test case is implemented
- whether extra DUT-facing infrastructure should be invented
- input literal interpretation is now signal/spec-aware
- ordinary data values remain decimal by default unless an explicit radix is present
- encoded control tokens now use explicit HardwareSpec mappings when available
- the renderer now receives canonical integer values and only performs width-aware SystemVerilog formatting
- safe signal-to-signal expected equality is now supported for simple known-port relationships such as `y equals a`
- expected-value parsing now shares the same signal-aware literal rules as stimulus parsing so width- and signal-semantics cannot drift apart
- width-matched output bit vectors such as `00001000` can now be interpreted safely as binary when the target signal semantics make that unambiguous
- common active-edge phrases such as `clk rising edge`, `rising edge of clk`, `posedge clk`, and repeated-edge variants are now normalized into typed clock actions before rendering

### Key Engineering Decisions

- keep testbench generation provider-neutral at the plan layer, but make final SystemVerilog rendering deterministic by default
- keep generated testbench text untrusted until later deterministic execution
- fail explicitly when a VerificationPlan action cannot be translated safely instead of guessing
- save generated files only on success to avoid stale-output confusion
- retain the older direct-AI generator only as legacy/internal code during the transition
- avoid prematurely building UVM-style infrastructure for an educational capstone

### What We Learned

Step 14 sharpened the project trust boundary:

```text
AI may reason about what to verify.
Deterministic code decides how that verification intent becomes executable SystemVerilog.
```

```text
Use AI for reasoning where uncertainty is useful; use deterministic code for syntax and execution structure where uncertainty is harmful.
```

```text
Testbench infrastructure should be derived from the DUT interface and semantics, not invented by the model.
```

```text
A self-checking testbench is not deterministic if its own stimulus processes race each other.
```

```text
A generated testbench must implement the verification plan completely, not selectively.
```

```text
Simulation delays express timing relationships; they cannot be sprinkled arbitrarily through procedural syntax.
```

```text
A testbench that compiles is still unsafe if its pass/fail predicate has the wrong boolean semantics.
```

```text
A verification plan defines what must be checked; testbench abstractions must adapt to the plan, not force the plan into a fixed signature.
```

```text
Generated verification code should favor explicitness when abstraction makes correctness harder to prove.
```

```text
The meaning of a hardware literal depends on both its syntax and the signal semantics; "10" is not universally decimal or binary.
```

```text
Not every expected value is a constant; some verification requirements are relationships between signals.
```

```text
Literal interpretation must be width- and signal-aware on both stimulus and expected-value paths.
```

```text
Natural-language normalization should map equivalent timing phrases into one typed action before rendering.
```

### Final Outcome

The repository now contains a deterministic testbench-rendering pipeline that translates structured verification intent into reproducible SystemVerilog without requiring Ollama in the default path. Step 14 is intentionally still open until manual generation and downstream deterministic validation are performed.

### Limitations / Deferred Work

- the translator only supports VerificationPlan actions it can safely understand
- unsupported actions fail explicitly instead of being guessed
- structural checks do not guarantee behavioral correctness
- generated testbenches are not yet automatically executed by the generator
- the legacy direct-AI generator remains in the repository but is no longer the default production path
- Step 15 will later address richer reference-model behavior more directly

---

## Cross-Platform and Teammate Onboarding Pass

### Goal

Make the repository easier for another developer to clone, configure, and run without needing private setup knowledge, especially on macOS while preserving the existing Windows and Linux strategy.

### Why This Work Was Needed

By this point the project had grown from a small deterministic verification prototype into a multi-layer workflow containing:

- hardware-tool adapters
- local Ollama integration
- structured specification models
- AI generation layers
- deterministic rendering and validation layers

That made teammate onboarding more important. A new developer needed to be able to answer practical questions quickly:

- which tools must be installed locally
- which parts run natively on each operating system
- which parts require Ollama
- which parts do not require Ollama
- which commands are the current known-good entry points

Without this pass, there was a real risk that the project would be understandable only to the original developer.

### What We Implemented

This pass focused on portability, configuration clarity, and onboarding rather than feature expansion.

It added:

- a non-installing environment doctor script
- clearer Ollama default configuration through shared environment-aware helpers
- a rewritten README that matches the real current architecture
- a short teammate setup guide with a practical macOS-first path
- a small `.gitignore` cleanup for generated artifacts and platform metadata

It also included an audit for machine-specific assumptions so that tracked application code would not depend on local absolute paths.

### Files Created

`src/rtl_assistant/llm/config.py`

- centralizes default Ollama configuration
- reads:
  - `RTL_ASSISTANT_OLLAMA_URL`
  - `RTL_ASSISTANT_MODEL`
- avoids scattering hardcoded defaults across multiple scripts

`scripts/check_environment.py`

- inspection-only environment doctor
- checks Python version, imports, repo structure, hardware tools, WSL-based tool expectations on Windows, Ollama executable presence, Ollama server reachability, and default-model availability
- reports deterministic readiness separately from AI-feature readiness

`docs/TEAMMATE_SETUP.md`

- practical onboarding instructions intended for a teammate or evaluator
- especially useful for a macOS setup path
- keeps the quickest working flow separate from the more architectural README

### Files Modified

`README.md`

- rewritten to reflect the current Steps 0–14 architecture
- now explains the trust model, installation flow, environment verification, quick start, cross-platform notes, and known limitations without overstating unfinished functionality

`src/rtl_assistant/llm/ollama.py`

- now uses shared configuration defaults rather than embedding local assumptions directly in the provider constructor

`src/rtl_assistant/llm/__init__.py`

- exports the shared Ollama default helpers for reuse

`src/rtl_assistant/hardware_tools/platform.py`

- simplified OS branching around `platform.system()`
- keeps platform-dependent behavior isolated in the tool-adapter layer

`scripts/parse_requirement.py`

- now uses shared Ollama default configuration

`scripts/generate_verification_plan.py`

- now uses shared Ollama default configuration

`scripts/generate_rtl.py`

- now uses shared Ollama default configuration

`scripts/test_llm.py`

- now uses shared Ollama default configuration

`.gitignore`

- updated to ignore generated output directories and common macOS metadata without hiding checked-in source assets

`PROJECT_LOG.md`

- updated to document this onboarding and portability pass

### Architecture / Flow

```text
clone repo
→ install Python dependencies
→ install local hardware tools
→ optionally install/start Ollama
→ run environment doctor
→ run known example commands
```

### Manual Validation Performed

No commands were executed during this documentation/setup pass.

The goal was to prepare a clean, explicit manual validation path for:

- the original Windows environment
- a teammate macOS setup
- future Linux users

### Problems Encountered

- the README no longer matched the current architecture or current roadmap state
- onboarding knowledge had become spread across code, commands, and previous development context instead of one practical guide
- Ollama defaults were repeated in multiple scripts
- the repository lacked a single environment doctor to show which missing pieces affect which features
- generated-output ignore rules were incomplete for current workflow directories

### Fixes / Improvements

- added a shared Ollama configuration helper with environment-variable overrides
- added `scripts/check_environment.py` for inspection-only setup validation
- rewrote the README around the current trust model and current Steps 0–14 architecture
- added a concise teammate setup guide
- ignored `generated/` and `.DS_Store`
- confirmed that application code was not tied to Chitraansh-specific absolute local paths

### Key Engineering Decisions

- treat environment readiness as part of developer experience, not as an afterthought
- distinguish deterministic readiness from AI readiness
- preserve the current Windows strategy rather than pretending all tools are fully native there
- keep machine-specific paths out of tracked configuration
- use environment variables for overridable local Ollama defaults instead of repository-specific path conventions

### What We Learned

An advanced architecture is much less useful if a teammate cannot tell which parts are required, optional, local, or platform-specific.

### Final Outcome

The repository is now substantially easier for another developer to clone and configure:

- setup instructions are aligned with the actual current architecture
- the local model configuration is clearer and less duplicated
- a teammate can check the environment before attempting example flows
- macOS onboarding is explicit
- Windows and Linux expectations are documented honestly

### Limitations / Deferred Work

- this pass does not replace actual cross-machine manual validation
- the environment doctor does not install anything; it only reports state
- Step 14 feature work remains in progress
- future teammates may still need hardware-tool troubleshooting specific to their OS package manager or WSL distribution

---

## Documentation Rule for Future Steps

For every future completed step, update this file with:

- goal
- implementation
- files
- tests
- failures
- fixes
- decisions
- outcome
- limitations

This file should remain the authoritative chronological engineering history of the project.
