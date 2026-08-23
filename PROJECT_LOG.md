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
→ final enriched requirement
→ AI HardwareIntent
→ deterministic semantic compiler
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
- `src/rtl_assistant/hardware_intent/`
  - deterministic lowering from high-level HardwareIntent into executable semantic AST / HardwareSpec
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

Another ambiguity-layer bug appeared later in normalization:

- the local ambiguity policy could preserve `ready = false`
- but canonicalization could drop every surviving `missing_critical`, `ambiguous`, and `clarification_questions` item
- that produced an impossible intermediate state and triggered a raw `RequirementAnalysis` validation crash

Another routing issue then appeared for unseen families:

- unknown/new hardware families could be normalized through an unrelated known family ambiguity template
- this produced internally valid but semantically nonsensical clarification output
- for example, a priority encoder could surface MUX-style ids such as `mux_select_mapping`

Another question-quality issue appeared once unseen families started reaching generic fallback handling:

- clarification could still ask for facts already explicit in the requirement
- it could also ask for facts that were safely derivable from explicit structured facts
- for example, `Create an 8-bit priority encoder.` could still ask for input width, output width, or binary-versus-one-hot input representation even though those dimensions were already explicit or mathematically derivable

Another semantic-identity leak then appeared in the same pipeline:

- unknown-family sanitization could replace family-specific clarification ids with opaque placeholders such as `generic_clarification_2`
- once that happened, deterministic derivation could no longer tell what unresolved concept the question was actually about
- the result was that already resolved topics such as encoder input width could survive only because their machine-readable meaning had been discarded

One more structured-filtering issue then appeared even after semantic keys were preserved:

- derivation could resolve `encoded_output_width`
- but a clarification question could still survive under the neighboring semantic key `output_width`
- in encoder-like contexts those two labels referred to the same deterministically derivable property, so the remaining clarification was still unnecessary

Another state-management issue then appeared at the end of the same normalization pipeline:

- deterministic derivation could successfully resolve every remaining ambiguity
- but the final normalized analysis could still preserve the model's old `ready = false`
- that created a false internal inconsistency even though the last clarification topic had been intentionally resolved

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

6. Structural preservation of not-ready evidence

If ambiguity normalization or local policy leaves a requirement as not-ready, the analysis must retain an explicit reason:

- missing critical field ids
- ambiguous field ids
- clarification questions

If canonicalization cannot safely preserve any of that evidence, the parser now fails structurally with an internal ambiguity-policy inconsistency error instead of constructing an invalid `RequirementAnalysis`.

7. Safe family-specific policy routing

Family-specific ambiguity policy is now applied only to compatible recognized families.

For unknown or unsupported families:

- preserve generic model uncertainty when possible
- avoid remapping to unrelated family-specific canonical ids
- strip or genericize incompatible family-template artifacts instead of surfacing misleading MUX/ALU/counter questions

8. Deterministic derive-before-asking

Before final clarification is emitted, the ambiguity layer now derives narrow safe facts from explicit requirement cues and simple mathematical relationships.

Examples:

- explicit bit widths are retained as resolved facts
- encoder-like requests can derive encoded output width as `ceil(log2(N))` when the input choice count is explicit
- redundant clarification about already-known widths, counts, or encodings is filtered out before the user is interrupted

9. Resolved-question filtering

Clarification questions are now checked against:

- explicit requirement facts
- deterministic derived facts
- the remaining unresolved machine-readable ambiguity ids

If a question asks about something the system already knows safely, it is dropped instead of being shown to the user.

10. Structured clarification semantic keys

Clarification questions now retain a separate machine-readable semantic topic independently of their presentation id.

That means a question can safely become:

- `id = generic_clarification_2`

while still preserving:

- `semantic_key = input_width`

Deterministic filtering now operates on the semantic key rather than depending on English wording or opaque placeholder ids.

11. Unknown-family semantic grounding

Unknown-family fallback now preserves uncertainty without preserving clearly incompatible structured concepts.

For example:

- an encoder-like requirement may still surface unresolved semantic choices
- but an invented `select_mapping` clarification is dropped because that structural concept is not grounded in the detected requirement shape

12. Context-aware semantic-key canonicalization

The ambiguity layer now uses one shared semantic-identity function across:

- derived facts
- clarification-question normalization
- resolved-question filtering
- unresolved-field filtering

This allows nearby machine-readable labels to collapse when structured context proves they represent the same fact.

Example:

- in encoder-like contexts, `output_width` canonicalizes to `encoded_output_width`
- that lets deterministic derivation remove redundant output-width clarification once `ceil(log2(N))` has already been resolved

13. Final readiness recomputation

The final ambiguity result now recomputes readiness after all deterministic processing has finished:

- family routing
- generic fallback normalization
- semantic-key normalization
- contextual canonicalization
- derive-before-asking
- grounding
- question deduplication
- resolved-question filtering
- unresolved-field filtering

If no unresolved evidence remains at the end of that process, the requirement is promoted back to `READY`.

The old LLM-provided `ready` value is now treated as advisory input rather than the final authority.

14. Clarification answers now become explicit requirement facts

The clarification flow previously carried accepted answers as side-channel parser state between ambiguity handling and HardwareSpec generation.

That created too many opportunities for resolved answers to be:

- normalized differently from the original requirement
- lost between stages
- represented differently from the original requirement contract
- contradicted later by HardwareSpec generation because the model did not see the clarified facts in the same text context

The parser now uses a simpler canonical flow:

```text
original requirement
→ ambiguity analysis
→ clarification questions
→ validated answers
→ deterministic enriched requirement
→ fresh parse/generation pass
```

Accepted clarification answers are now injected into a structured enriched-requirement block such as:

```text
Clarified requirements:
- Priority direction: Highest to lowest
- Valid output presence: Yes
```

The original requirement text is still preserved for provenance, but the enriched requirement becomes the authoritative post-clarification contract for the next parse/generation pass.

This also keeps clarification iterative: after one answered round, the parser reruns ambiguity analysis on the enriched requirement and only asks again if genuine unresolved uncertainty still remains.

One CLI orchestration regression appeared immediately after this refactor:

- the post-clarification enriched-requirement path could construct and run the second pass
- but its result did not always flow back through the normal final parser renderer
- the command could therefore terminate after printing only a separator line instead of a real READY / NEEDS_CLARIFICATION / FAIL summary

That CLI path now converges back onto the same final result-rendering and output-writing boundary used by the normal single-pass flow.

Another post-clarification orchestration bug then appeared inside the enriched-requirement path itself:

- the parser could accept a clarification answers file
- but rebuild the accepted-answer list through normalized question ordering
- and then construct an enriched requirement identical to the original requirement text

That meant the second pass could silently rerun the original vague prompt even after answers had already been validated.

The flow now carries the canonical accepted-answer payload directly into the single authoritative `enriched_requirement` string used both for debug display and for the second parse pass.

It also now fails structurally if accepted clarification answers exist but the enriched requirement remains identical to the original requirement.

The clarification CLI has now been upgraded from a batch-style handoff into the canonical interactive architecture:

```text
original requirement
→ ambiguity analysis
→ NEEDS_CLARIFICATION
→ interactive user answers
→ deterministic requirement enrichment
→ ambiguity analysis again
→ repeat until READY or structured FAIL
```

The program now stays alive across clarification rounds instead of requiring a new process plus a JSON answer file between each round.

Accepted answers are validated, accumulated by semantic identity, and then used to deterministically rebuild the authoritative enriched requirement from:

- the immutable original requirement
- every accepted clarification fact so far

That keeps clarification state inside one continuous dialogue and prevents answer/enrichment drift across process boundaries.

The final enriched requirement becomes the exact contract passed into HardwareSpec generation once ambiguity has been resolved.

One more regression appeared when the clarification loop was split from the generation step:

- the new `analyze_requirement(...)` orchestration boundary could allow a vague requirement to proceed directly to HardwareSpec generation
- this happened because the clarification architecture no longer had one explicit authoritative ambiguity-resolution function shared by every path
- the result was that an underspecified prompt could appear to jump straight to `Generating HardwareSpec...` instead of asking clarification questions first

The parser now routes interactive mode, `--answers` mode, `--no-interactive`, and the legacy one-shot `parse(...)` call through the same authoritative full ambiguity-analysis pipeline before any generation step is allowed.

That shared pipeline still treats the raw LLM `ready` field as advisory input rather than final authority, and it preserves the deterministic policy layer that decides whether unresolved requirement intent still remains.

The next major architecture milestone then moved the same trust-boundary idea into hardware semantics themselves.

The old semantics path asked the LLM to directly generate the final low-level semantic AST inside HardwareSpec.

That repeatedly failed on unseen combinational designs even when the model clearly understood the requested circuit.

Observed failure patterns included:

- malformed AST field names
- invented expression shapes
- vector indexing embedded inside signal identifiers
- self-referential combinational expressions
- structurally valid but functionally wrong semantics
- precedence logic contorted into unrelated arithmetic operators

The priority-encoder regression made the problem decisive:

- the model understood widths
- it understood the clarified priority direction
- it understood the valid-output requirement
- but it still emitted a schema-valid AST that behaved like exact one-hot decoding rather than true priority selection

That exposed the same architectural issue already solved on the verification side:

```text
the LLM was being asked to author both the meaning and the executable semantic truth
```

The default combinational requirement-to-spec flow is now:

```text
final enriched requirement
→ AI HardwareIntent
→ deterministic HardwareIntent compiler
→ low-level semantic AST
→ validated HardwareSpec
```

The new HardwareIntent layer captures high-level combinational meaning without forcing the model to spell out recursive low-level semantic AST implementation trees.

Initial composable intent primitives now cover:

- signal/literal references
- arithmetic operations
- bitwise operations
- comparisons
- conditional selection
- priority-based selection
- status derivation such as NONZERO

Priority-based selection is now lowered deterministically into nested `BitSelectExpr` + `SelectExpr` structure, and status derivation such as:

```text
valid = NONZERO(data_in)
```

is deterministically lowered into a zero-comparison semantic expression instead of being authored directly by the model.

The low-level semantic AST remains authoritative and still feeds the deterministic validator and evaluator. The difference is that the model now proposes high-level meaning, while deterministic code owns the executable semantic representation.

Sequential HardwareIntent lowering is explicitly deferred in this phase. Existing sequential requirement-to-spec behavior remains on the clearly transitional legacy direct-HardwareSpec path.

Two follow-on robustness regressions then appeared during the first interactive HardwareIntent runs.

The first was a clarification applicability regression:

- the LLM surfaced `carry_behavior` / carry-overflow uncertainty while clarifying a priority encoder
- that question was semantically irrelevant to the current requirement
- once answered, it polluted the enriched requirement contract even though it never should have been asked

The fix was to tighten semantic applicability grounding for clarification questions.

A semantic clarification key must now be grounded as applicable to the current structured requirement context before it can reach the user.

The system now distinguishes:

- unresolved and applicable
- already resolved
- unsupported or irrelevant

Only unresolved and applicable clarification concepts may be surfaced or accepted into the enriched requirement contract.

That means the LLM may still identify uncertainty, but it cannot invent new required hardware concepts through clarification.

The second regression appeared in HardwareIntent descriptive metadata:

- the model emitted slightly different JSON shapes inside `behavior.operations` and `behavior.assumptions`
- those fields are descriptive prose metadata rather than authoritative executable intent
- but strict list-of-string validation caused HardwareIntent rejection before deterministic lowering could even begin

The fix was to normalize descriptive HardwareIntent metadata conservatively before strict typed validation.

Descriptive fields such as:

- `behavior.operations`
- `behavior.rules`
- `behavior.assumptions`
- `tags`
- `notes`

are now treated as non-authoritative prose metadata.

They are normalized into plain strings where safe, while authoritative fields such as:

- module name
- ports
- intent assignments
- operators
- targets
- signal references
- widths
- priority direction
- output modes

remain strictly validated.

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

Another important lesson was:

```text
A not-ready decision must carry an explanation; ambiguity policy should never emit an impossible intermediate state.
```

Two related lessons followed:

```text
Clarification must be semantically grounded in the detected hardware family; an unrelated deterministic template is worse than preserving generic model uncertainty.
```

And the derive-before-asking pass made three more lessons concrete:

```text
Clarification should be reserved for genuine design choices, not facts the system can safely derive.
```

```text
Explicit requirement facts and deterministic mathematical relationships should be resolved before the user is interrupted.
```

```text
Question quality is part of correctness: an unnecessary clarification can be as harmful as an incorrect assumption.
```

```text
Unknown families should fall back safely, not be coerced into the nearest known family.
```

And one more clarification-flow lesson became explicit:

```text
Clarification answers should become part of the requirement contract.
```

Keep the original requirement for provenance, but use the enriched requirement as the authoritative post-clarification input.

Do not rely on hidden LLM side-channel context when explicit deterministic text can carry the same contract.

Another implementation lesson from the CLI regression was:

```text
Multi-pass CLI flows should converge on one result boundary; intermediate success must not bypass final status reporting.
```

And the enrichment-path bug made three more lessons explicit:

```text
Accepted clarification answers must be materialized into the requirement contract before any second-pass LLM call.
```

```text
The debug view of an enriched requirement must show exactly what the model receives.
```

```text
Never silently rerun the original vague requirement after successfully validating answers.
```

The new canonical clarification-loop lessons are:

```text
Clarification is a dialogue, not a batch file transformation.
```

```text
The parser should remain alive while requirement intent is being resolved.
```

```text
Every accepted answer becomes part of the accumulated requirement contract.
```

```text
Ambiguity resolution and HardwareSpec repair are separate loops and must remain separate.
```

And the boundary regression made two more lessons explicit:

```text
Splitting orchestration boundaries must not duplicate or bypass policy logic.
```

```text
There should be exactly one authoritative function that decides whether a requirement is sufficiently specified.
```

The new semantic-intent compiler milestone added four more core lessons:

```text
Do not ask the LLM to author both the meaning and the executable semantic truth.
```

```text
High-level intent and low-level semantic execution should be separate representations.
```

```text
Generalization should come from composable hardware primitives, not one handler per module family.
```

```text
The verification architecture already proved this pattern: AI intent plus deterministic compilation is more robust than direct low-level generation.
```

And these early HardwareIntent regressions added two more trust-boundary lessons:

```text
The LLM may identify uncertainty, but it cannot invent new required hardware concepts through clarification.
```

```text
Strictness belongs on executable intent; descriptive prose should not be part of the semantic trust boundary.
```

And one more trust-boundary lesson emerged from the semantic-key fix:

```text
Question IDs are presentation identifiers, not semantic meaning.
```

```text
Machine-readable clarification semantics must survive normalization.
```

```text
Deterministic filtering should operate on structured concepts, not English wording.
```

```text
Structured semantics still need canonical identity; two machine-readable labels can represent the same fact.
```

```text
Semantic equivalence must be contextual, not a global string alias.
```

```text
`ready` is derived from final unresolved evidence, not an immutable LLM judgment.
```

```text
Resolving the last clarification should promote the requirement back to READY.
```

```text
Policy inconsistency must distinguish accidental evidence loss from intentional deterministic resolution.
```

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

4. AI-generated RTL could omit the final POSIX newline at end-of-file. This did not affect simulation or synthesis semantics, but Verilator reported `%Warning-EOFNEWLINE`, which is fatal under the current lint configuration.

### Fixes / Improvements

The prompt was tightened to prefer modern, conservative SystemVerilog:

- `logic` instead of legacy `reg`
- `output logic` for procedurally assigned outputs
- scalar syntax for width-1 ports
- no unnecessary self-assignment such as `count <= count;`

A lightweight sanity check was also added for obvious procedural-output declaration issues.

Generated RTL file output was also normalized to end with exactly one trailing newline so deterministic linting does not fail on formatting-only EOF issues.

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

Generated source formatting is also part of deterministic tool compatibility even when it does not affect HDL semantics.

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
→ JSON-only verification-intent generation
→ Pydantic validation of intent
→ deterministic verification compiler
→ deterministic expected-value/reference semantics
→ compiled executable verification plan
→ typed VerificationPlanGenerationResult
```

The output is now split across two layers:

- AI-facing `VerificationIntentPlan`
- deterministic `CompiledVerificationPlan`

This fixed an architectural overload in the earlier design where one free-form VerificationPlan had to serve as both:

1. AI intent
2. executable verification semantics

### Files Created

`src/rtl_assistant/models/verification_plan.py`

- typed Pydantic models for the verification-plan schema and generation result
- separates the plan itself from the AI execution metadata

`src/rtl_assistant/verification_plan/prompts.py`

- versioned prompt builder for plan generation and repair
- feeds the full validated `HardwareSpec` JSON to the model

`src/rtl_assistant/verification_plan/generator.py`

- provider-neutral verification-plan generator
- now generates typed verification intent instead of executable prose
- performs JSON extraction, Pydantic validation of intent, deterministic compilation, and one repair attempt

`src/rtl_assistant/models/verification_intent.py`

- new AI-facing verification-intent schema
- captures behavior, scenario, vector hints, and optional precondition intent without executable timing prose

`src/rtl_assistant/models/compiled_verification_plan.py`

- new deterministic compiled-plan schema
- stores typed actions, typed checks, state provenance, and compilation notes

`src/rtl_assistant/verification_plan/compiler.py`

- deterministic bridge from `HardwareSpec + VerificationIntentPlan` to executable compiled verification semantics
- owns legal state setup, reset semantics, action ordering, expected-value derivation, and safe failure on unsupported intent

`src/rtl_assistant/verification_plan/semantics.py`

- centralized behavior/scenario normalization and grounding helpers
- reduces duplicated semantic interpretation across generation, reference resolution, and testbench translation

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
- now also exports the new verification-intent and compiled-plan models

`src/rtl_assistant/models/reference.py`

- adds typed deterministic-resolution and correction-trail models
- preserves structured visibility when AI-proposed expected values are canonicalized

`PROJECT_LOG.md`

- updated with the new Step 13 entry and project-status tracking

### Architecture / Flow

```text
HardwareSpec
→ verification-intent prompt
→ LLMProvider
→ JSON extraction
→ VerificationIntentPlan validation
→ deterministic verification compiler
→ deterministic expected-value/reference semantics
→ CompiledVerificationPlan
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
- operation-coverage normalization was initially too literal for terms such as `SHIFT_LEFT`
- expected fields could repeat input stimulus such as `rst_n=1`, `en=1`, or `serial_in=1` instead of describing observations
- sequential precondition checking initially leaned too heavily on counter-style patterns and needed to generalize to other sequential state machines
- asynchronous reset behavior must not inherit synchronous clock-edge requirements
- AI verification plans can invent plausible but unsupported behavior, such as shift-register wraparound, even when the HardwareSpec does not define it
- a syntactically valid VerificationPlan could still pass existing guardrails even though multiple sequential tests depended on an unestablished initial state
- deasserted reset could appear in accepted plans as though it established the reset value, even though reset deassertion is not initialization
- repeated sequential transitions needed deterministic state propagation across every edge rather than one-step reasoning
- the same free-form `setup`, `stimulus`, `expected`, and `covers` strings were being parsed repeatedly by:
  - the Step 13 generator
  - the deterministic reference layer
  - the Step 14 translator
- this meant the repository kept patching natural-language variants instead of fixing the trust boundary itself
- optional AI vector suggestions were still crossing the deterministic trust boundary too strongly
- invalid optional hints such as out-of-range ALU operands or output-signal hints could still block compilation of an otherwise valid semantic intent

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

```text
Verification intent must remain grounded in HardwareSpec semantics, not merely sound plausible.
```

```text
Sequential state cannot be assumed; it must be established, constrained, or explicitly stated as a legal precondition.
```

```text
Asynchronous reset is a state transition independent of the active clock edge.
```

```text
Reset deassertion is not initialization.
```

```text
Sequential verification requires explicit known-state provenance.
```

```text
Each test case must be independently executable unless the IR explicitly defines shared state.
```

```text
Reference models should propagate state across repeated transitions, not merely validate individual expected literals.
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
- operation-coverage and unsupported-behavior checks now use canonical behavior concepts so phrases like `shift left by one bit` normalize cleanly to structured semantics such as `SHIFT_LEFT`
- expected-output sanitization now removes plain DUT-input echoes from `expected` when they merely restate stimulus instead of observable behavior
- sequential precondition checks are now generic across sequential designs rather than only counter-oriented
- asynchronous reset semantics are validated separately from synchronous reset semantics, so an async reset test does not require an active clock edge
- unsupported behavior claims such as wraparound on a pure shift-register spec are now rejected as ungrounded plan semantics
- the deterministic reference layer now includes a generic simple shift-register handler for explicitly defined shift semantics with known prior state, serial input, enable/reset conditions, and active-edge information
- generic sequential known-state reasoning now distinguishes reset assertion from reset deassertion and rejects tests that claim known output state without legal provenance
- repeated shift-register transitions are now propagated deterministically across every referenced active edge when the starting state and legal stimulus are known
- expected engineering benefits of this layer are:
  - fewer arithmetic hallucinations
  - fewer unnecessary LLM retries
  - higher repeatability across runs
  - stronger portability across future LLM providers
  - a natural foundation for richer Step 15 reference models
- unsupported semantics degrade safely instead of being guessed
- final architectural cleanup split the overloaded VerificationPlan boundary into:
  - `VerificationIntentPlan`
  - deterministic compiler
  - `CompiledVerificationPlan`
- machine-critical semantics such as state provenance, legal reset behavior, clocked action ordering, and expected values now become typed exactly once during deterministic compilation
- AI vector hints are now sanitized as advisory metadata only
- invalid, out-of-range, output-side, unknown-signal, or clock-signal hints are ignored and replaced by deterministic legal vector selection
- deterministic compilation now owns legal vector selection even when the model offers poor optional hints
- family-specific deterministic handlers do not scale across unseen combinational hardware families
- a typed combinational hardware-semantics AST plus generic deterministic evaluator now provides a scalable path for unseen combinational designs without requiring a new module-family handler for every case
- introducing the semantics layer also exposed a circular import between foundational models and semantics services
- this was fixed by keeping `semantics/__init__.py` lightweight, lazy-importing semantic validation from `HardwareSpec`, and using type-only `HardwareSpec` references inside semantics services
- unseen combinational regression exposed malformed verification-intent JSON wrapped in extra prose/formatting even though the underlying content was recoverable
- the same regression also showed that a typed semantic AST can still be wrong if its structured branches contradict a safely cross-checkable canonical behavior equation
- structured semantic AST support had become generic, but VerificationIntent grounding still depended too heavily on a parallel manually maintained behavior vocabulary
- that allowed new primitive capabilities such as `BIT_XOR` to be represented and evaluated but still rejected before deterministic compilation
- combinational composed behavior also required path reasoning through the AST so a targeted capability could imply deterministic control assignments such as a select branch choice
- select-branch consistency also needed to cover narrow `target = expr when control is 0/1` forms, not only canonical ternary strings
- human-readable behavior text was still being used as a weak secondary source for checking semantic branch direction, but equivalent phrasing made that cross-check fragile
- explicit conditional requirement meaning therefore needed to be preserved structurally at parse time instead of being reconstructed later from prose

### Key Engineering Decisions

- keep verification-plan generation separate from deterministic verification execution
- keep the generator provider-neutral
- validate the plan as data before later generating any testbench code
- do not treat the plan as executable or authoritative until validated
- avoid module-name-specific fixes; derive deterministic expectations from `HardwareSpec`, explicit literals, and structured behavior where possible
- keep foundational models independent from eager service imports that depend back on those same models
- keep typed semantic ASTs authoritative long-term, but validate them against human-readable behavior when a narrow safe consistency check exists
- derive semantic capability vocabulary from the typed AST instead of maintaining a separate parallel list for the same machine-computable concepts
- preserve explicit conditional branch meaning as structured semantic constraints and validate the AST against those constraints before accepting a HardwareSpec as READY

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

A typed semantic AST is only useful if it is internally validated for consistency where a safe cross-check is available.

Semantic capability vocabulary should come from the typed semantic representation, not a parallel manually maintained list.

Composed hardware behavior requires reasoning about paths through the semantic AST, not module families.

Once structured semantics are validated, downstream deterministic execution should use them as the source of truth.

Machine-critical requirement relationships should be preserved structurally at the point of interpretation, not reconstructed later from prose.

Structured semantic constraints validate the AST; downstream execution uses the validated AST.

LLM interpretation may be retried, but deterministic consistency validation decides acceptance.

```text
LLM output should describe intent, not executable timing semantics.
```

```text
Free-form prose should not survive across the deterministic trust boundary.
```

```text
Advisory AI hints should never determine whether a semantically valid verification case is executable.
```

```text
Deterministic compilation owns legal vector selection; AI hints can improve coverage but cannot define correctness.
```

```text
Generalization comes from modeling primitive hardware semantics, not enumerating every module family.
```

```text
Hardware families are compositions of a much smaller set of deterministic operations.
```

### Final Outcome

The repository now contains a completed structured verification-intent generation layer plus deterministic compilation into executable verification semantics.

The architectural goal of Step 13 is not to guarantee that an untrusted LLM always generates a valid verification plan. The goal is to:

- produce a typed `VerificationIntentPlan`
- compile that intent into a deterministic executable verification plan when the semantics are supported
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
CompiledVerificationPlan
```

so that later deterministic simulation can execute the proposed verification strategy against the DUT.

### Why This Step Was Needed

A generated RTL design cannot be trusted without executable verification. Even a good verification plan is still only intent until it becomes a runnable self-checking testbench.

### What We Implemented

The current Step 14 architecture is:

```text
HardwareSpec + compiled executable verification plan
→ structured TestbenchPlan / IR
→ deterministic renderer
→ lightweight deterministic structural validation
→ SUCCESS / FAIL
```

The public/default generator no longer depends on Ollama once a valid compiled verification plan already exists.

The current implementation treats the compiled verification plan as the authoritative executable description of what must be tested. This replaced the earlier direct:

```text
HardwareSpec + free-form verification prose
→ repeated parsing / interpretation
→ fragile executable semantics
```

path as the default production flow.

The deterministic path now provides:

- typed result model
- typed Testbench IR
- deterministic translator from compiled typed actions/checks to structured Testbench IR
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
HardwareSpec + CompiledVerificationPlan
→ deterministic translation
→ Testbench IR
→ deterministic SystemVerilog rendering
→ lightweight deterministic validation
→ TestbenchGenerationResult
```

### Trust Boundary

The trust boundary changed significantly during this step:

```text
AI may help produce verification intent.
Deterministic code decides how that intent becomes executable SystemVerilog.
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
- simple expected forms such as `signal equals literal` were not normalized even though literal assignments and signal-to-signal equality were both already supported elsewhere
- binary-looking expected bit vectors such as `y=00001000` could be misread as decimal text instead of width-matched binary output values
- harmless clock phrase variants such as `clk rising edge` were not normalized into the existing active-edge IR action
- AI verification plans could place an active clock edge before the input assignments intended for that edge
- deterministic translation needed to recognize that, for edge-triggered hardware, assignments such as enable or serial-input setup belong before the consuming edge rather than after it
- the old Step 14 translator still had to interpret prose because Step 13 output mixed AI intent and executable semantics in one schema

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
- simple signal-to-literal expectations such as `q equals 0` or `result equals 5` now normalize into the same typed literal-check representation as `q=0` and `result=5`
- expected-value parsing now shares the same signal-aware literal rules as stimulus parsing so width- and signal-semantics cannot drift apart
- width-matched output bit vectors such as `00001000` can now be interpreted safely as binary when the target signal semantics make that unambiguous
- common active-edge phrases such as `clk rising edge`, `rising edge of clk`, `posedge clk`, and repeated-edge variants are now normalized into typed clock actions before rendering
- recognized sequential stimulus is now canonicalized so input and control setup precedes the relevant active edge
- ambiguous sequential ordering fails safely instead of being guessed, especially when async-reset semantics would make reordering unsafe

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

```text
Equivalent verification intent should normalize to the same typed representation before rendering.
```

```text
For edge-triggered hardware, stimulus timing is part of correctness: inputs must be established before the edge that consumes them.
```

### Final Outcome

The repository now contains a deterministic testbench-rendering pipeline that translates structured verification intent into reproducible SystemVerilog without requiring Ollama in the default path. Step 14 is intentionally still open until manual generation and downstream deterministic validation are performed.

### Limitations / Deferred Work

- the translator only supports VerificationPlan actions it can safely understand
- the new compiled-plan path is now the default, but legacy prose-oriented code still exists in the repository for transitional compatibility and can be removed later after regression confidence improves
- unsupported actions fail explicitly instead of being guessed
- structural checks do not guarantee behavioral correctness
- generated testbenches are not yet automatically executed by the generator
- the legacy direct-AI generator remains in the repository but is no longer the default production path
- Step 15 will later address richer reference-model behavior more directly

---

## Architecture Milestone — First Fully Unseen End-to-End Design Regression

This was a major architecture milestone because it demonstrated end-to-end success on a genuinely unseen design family without adding a family-specific deterministic reference handler.

### Design

2-bit unsigned comparator

### Original Natural-Language Requirement

```text
Create a 2-bit unsigned comparator with inputs a and b. It should have three outputs: eq, gt, and lt, indicating whether a is equal to, greater than, or less than b.
```

### Successful Pipeline

```text
Natural language
→ AI requirement parser
→ HardwareSpec
→ structured combinational semantic AST
→ AI VerificationIntentPlan
→ deterministic verification compiler
→ generic semantic evaluator
→ CompiledVerificationPlan
→ deterministic testbench
→ AI-generated SystemVerilog RTL
→ Verilator lint
→ Icarus simulation
→ Yosys synthesis
→ Overall PASS
```

### Important Result

- no comparator-specific deterministic handler was added
- `EQ` / `GT` / `LT` behavior was represented through the generic semantic AST
- deterministic evaluation produced all expected outputs
- AI-generated RTL passed lint, functional simulation, and synthesis

### First Verification Attempt Issue

The first full regression exposed one generic output-formatting problem rather than a hardware-semantics problem:

- simulation: PASS
- synthesis: PASS
- lint: initially FAIL

The only lint issue was Verilator `%Warning-EOFNEWLINE` because the AI-generated RTL lacked a trailing POSIX newline even though the HDL itself was otherwise correct.

That was fixed generically by normalizing saved AI-generated RTL files to end with exactly one newline. After that output-normalization fix, the comparator rerun produced a full end-to-end PASS.

### Why This Was Important

This result showed that an unseen hardware family could be supported through primitive semantic composition rather than by introducing a new deterministic family-specific handler. The comparator behavior was grounded in generic structured semantics and then carried through deterministic compilation, deterministic expected-value evaluation, deterministic testbench generation, and downstream hardware-tool validation.

It also reinforced a stricter success criterion for the project:

- successful AI code generation alone is not enough
- successful simulation alone is not enough
- successful synthesis alone is not enough
- end-to-end success must include lint, functional simulation, and synthesis

### Engineering Lessons

```text
An unseen hardware family can be supported through primitive semantic composition without introducing a family-specific reference handler.
```

```text
Generated-source formatting is part of tool compatibility even when HDL semantics are correct.
```

```text
End-to-end success must include lint, functional simulation, and synthesis rather than merely successful code generation.
```

This milestone does not mean arbitrary RTL is now supported. It means the current architecture successfully generalized to at least one previously unseen combinational design family when the behavior could be represented safely through the structured semantic layer.

Another harder unseen composed combinational design then exercised:

- structured conditional constraints
- `SELECT`
- `ADD`
- `BIT_XOR`
- AST-derived capabilities
- AST-path control inference
- deterministic semantic evaluation
- AI RTL generation
- deterministic TB generation
- Verilator
- Icarus
- Yosys

That design passed functional simulation and synthesis immediately, but the first lint result failed only because the generated RTL filename did not match the validated module name. Saving the same RTL using the module-aligned filename produced:

- Lint: PASS
- Simulation: PASS
- Synthesis: PASS
- Overall: PASS

Engineering lesson:

`Generated artifact naming is part of toolchain compatibility; module names and RTL filenames should align by default.`

Another unseen regression then exposed a more important semantics-layer limitation:

- the requirement/clarification pipeline correctly handled an unseen 8-bit priority encoder
- but HardwareSpec generation failed because the semantic AST could not represent vector bit selection directly
- the model responded by emitting invalid `SignalExpr` identifiers such as `data_in[7]`
- it also tried to contort priority behavior through malformed nested `SUB` expressions and contradictory prose about MSB-versus-LSB priority

The architectural fix was to extend the generic semantic DSL itself rather than add a priority-encoder-specific handler.

The structured semantics layer now supports typed `BitSelectExpr`, which lets vector-bit conditions be represented directly as AST nodes instead of being smuggled inside identifier strings. That in turn makes ordinary nested `SelectExpr` composition expressive enough to model priority/precedence behavior generically:

- check one bit
- if asserted, return its encoded value
- otherwise continue to the next branch

The semantic-constraint layer was also generalized so preserved requirement meaning can use a typed condition expression rather than only a scalar `control_signal` / `control_value` pair. That keeps resolved clarification answers structurally enforceable when precedence depends on vector bits rather than a single top-level select signal.

This did not solve every semantic-completeness question. In particular, the encoded output value when no priority-encoder input is asserted may still remain underspecified unless the requirement or clarification makes it observable. The current project intentionally does not guess that kind of don't-care behavior.

One prompt-construction bug then appeared immediately after adding the `BitSelectExpr` guidance:

- a literal JSON `BitSelectExpr` example was inserted directly into an f-string
- Python interpreted the JSON braces as formatting syntax
- the parser crashed before the LLM call instead of reaching semantic validation

That was fixed by rendering prompt JSON examples safely instead of embedding raw brace-heavy JSON directly inside f-strings.

Another HardwareSpec-generation regression appeared immediately afterward:

- the model could emit `semantic_constraints` while leaving `semantics` null
- that produced a validator failure because structured constraints require compatible structured semantic assignments
- the raw failure was correct, but the repair loop initially only saw a broad schema-validation error instead of a concise actionable cause

That was fixed by adding an early HardwareSpec-generation guard:

- if `semantic_constraints` are present but compatible `semantics.combinational.assignments` are missing
- return a targeted validation/repair message
- tell the model to either emit matching structured semantics or omit `semantic_constraints`

Engineering lessons:

```text
Do not encode HDL syntax inside semantic signal identifiers.
```

```text
When an LLM contorts valid behavior into unrelated operators, the semantic DSL may be missing a primitive.
```

```text
Generalize the semantic vocabulary at the operation level, not by adding module-family handlers.
```

```text
Resolved clarification answers must remain authoritative through HardwareSpec validation.
```

```text
Prompt examples are code too; literal JSON inside f-strings must be escaped or serialized.
```

```text
Structured semantic constraints are only meaningful when the corresponding structured semantics also exist.
```

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

---

## HardwareIntent Priority-Select Milestone

### Milestone

The first priority-encoder run through the new `HardwareIntent -> deterministic semantic compiler` path successfully produced a correct nested priority-selection semantic AST.

### Observed Success

For the clarified requirement:

- `Priority direction: Highest to lowest`
- `Valid output presence: Yes`

the deterministic compiler lowered the priority-selection behavior into the expected ordered chain:

- `data_in[7] -> 7`
- `data_in[6] -> 6`
- ...
- `data_in[0] -> 0`

This correctly handles multiple asserted bits and is the first strong evidence that the new trust boundary is working as intended for precedence-based combinational logic.

### Remaining Regression

The compiled `valid` semantic was still wrong:

- produced: `valid = (encoded_out != 0)`
- required: `valid = (data_in != 0)`

This fails for cases such as `data_in = 00000001`, where `encoded_out = 0` but `valid` must still be `1`.

### Architectural Value

The important result is that the remaining bug is now localized to one of two places:

- the validated high-level `HardwareIntent`
- its deterministic lowering

rather than being buried inside an opaque malformed low-level AST emitted directly by the LLM.

### Debugging Support Added

The requirement-parser CLI now supports a `--show-intent` view so the exact validated `HardwareIntent` object passed into deterministic compilation can be inspected independently of the compiled semantic AST.

### Engineering Lessons

```text
Inspect intent and compiled semantics independently at the trust boundary.
```

```text
A deterministic compiler can only be as semantically correct as the validated high-level intent it receives.
```

---

## Semantic Provenance for Verification Planning

### Milestone

`HardwareIntent` successfully lowered priority-selection behavior into correct executable nested `BitSelectExpr` / `SelectExpr` semantics.

### Regression

Verification-intent generation then lost that high-level meaning after lowering.

The verification layer saw only the low-level `SelectExpr` implementation tree and treated the design like generic routing or mux behavior. That produced weak intent such as:

- `mux_select_zero`
- `mux_select_one`
- `mux_select_max`

and missed the critical multi-active priority cases that distinguish true precedence logic from one-hot-only behavior.

### Architecture Fix

High-level semantic provenance is now preserved from `HardwareIntent` through deterministic lowering into `HardwareSpec` via typed `semantic_features`.

Examples now include preserved feature identity such as:

- `PRIORITY_SELECT`
- `NONZERO`

These features do not replace the executable semantic AST. Instead:

- low-level semantics remain authoritative for deterministic evaluation
- semantic features preserve the higher-level behavioral identity needed by downstream verification planning

### Verification Planning Impact

Verification planning and deterministic compilation now prefer preserved semantic features when available instead of relying only on AST-derived operator capabilities.

This allows deterministic minimum-coverage obligations to be enforced for semantic primitives.

For `PRIORITY_SELECT`, the compiler now synthesizes mandatory coverage cases such as:

- no active source bits
- low-boundary one-hot
- high-boundary one-hot
- multi-active competing bits

For `NONZERO`, the compiler now guarantees:

- source equals zero
- source is nonzero

AI vector hints remain advisory. Deterministic semantic-feature coverage owns the minimum correctness obligations.

### Documentation Impact

The project architecture documentation now distinguishes:

- executable semantics
- semantic provenance / features

inside `HardwareSpec`, and shows that verification planning can use both representations for different purposes.

### Engineering Lessons

```text
Lowering must not erase the semantic identity needed by downstream verification.
```

```text
Executable semantics and coverage semantics are related but not identical representations.
```

```text
Mandatory coverage for semantic primitives should be deterministic; AI scenario suggestions remain advisory.
```

---

## Verification-Intent Vocabulary Separation

### Problem

After semantic provenance was added to `HardwareSpec`, the verification-intent model could copy a semantic feature kind directly into the `scenario` field.

Observed regression:

- `scenario = NONZERO`

This was wrong because:

- semantic feature kinds describe what behavior exists
- scenario tokens describe what testing situation is being exercised

Those are different dimensions.

### Fix

The verification-intent prompt now separates the two vocabularies explicitly:

- `target_behavior` may align to grounded semantic feature kinds such as `NONZERO` or `PRIORITY_SELECT`
- `scenario` must use only the verification-scenario vocabulary such as `BASIC`, `BOUNDARY`, `MAPPING`, `RESET_ASSERT`, or `LOGIC`

The deterministic compiler now also detects this collision structurally. If a case places a semantic behavior token into `scenario`, it returns a targeted structured failure instead of a generic unsupported-scenario message.

### Important Preservation

This change does not weaken the deterministic semantic-feature obligations:

- `PRIORITY_SELECT` still gets mandatory priority-competition and boundary coverage
- `NONZERO` still gets zero and nonzero deterministic coverage

AI scenario wording remains advisory; deterministic coverage remains authoritative.

### Engineering Lessons

```text
Behavior taxonomy and test-scenario taxonomy are different dimensions and must not share tokens accidentally.
```

```text
Semantic provenance should guide target behavior, not overwrite the scenario field.
```

---

## VerificationIntent Envelope Hardening

### Problem

VerificationIntent retry could return a partial or alternate JSON shape instead of the complete `VerificationIntentPlan` envelope.

That caused top-level required fields such as:

- `module_name`
- `design_type`
- `strategy`
- `cases`

to disappear, even though the model was still returning JSON.

### Debugging Regression

The CLI flag `--show-raw-intent` did not expose the final raw model response on this schema-validation failure path, which made it harder to inspect whether the model had returned:

- only a `cases` array
- a partial object
- explanatory prose
- or some other alternate envelope

### Fix

VerificationIntent generation now performs a lightweight structural envelope check immediately after JSON extraction.

Every retry is required to return the full top-level `VerificationIntentPlan` object containing:

- `schema_version`
- `module_name`
- `design_type`
- `strategy`
- `cases`
- `coverage_targets`
- `assumptions`
- `notes`

If that envelope is missing, generation now produces a targeted `INVALID_VERIFICATION_INTENT_ENVELOPE` failure and feeds that reason into repair.

The prompt and repair prompt now also state explicitly that repair must replace the full object, not return a fragment or patch.

### Debugging Improvement

`--show-raw-intent` now consistently exposes the final raw model response on AI-generation failures as well as showing the validated intent on success.

This preserves the exact model output that failed validation instead of requiring reconstruction from partial parsed data.

### Engineering Lessons

```text
Repair responses must replace the full typed object, not return partial patches.
```

```text
Structured-output debugging must preserve the exact model response that failed validation.
```

---

## Typed TestbenchAction Consumption Fix

### Problem

Mandatory semantic-feature coverage synthesis assumed an outdated `TestbenchAction` field shape and accessed `action.value` directly while trying to reuse existing compiled vectors.

That caused a raw `AttributeError` before verification-plan compilation completed.

### Fix

Coverage vector extraction now uses the current typed `TestbenchAction` schema.

For `SET_INPUT`, the deterministic IR stores the assigned signal and literal value inside:

- `action.assignment.signal`
- `action.assignment.value`

The compiler now reads that typed payload directly and rejects an impossible malformed `SET_INPUT` action through a structured compiler error instead of crashing with a raw attribute access failure.

### Important Preservation

This fix does not change the intended mandatory semantic coverage policy:

- `PRIORITY_SELECT` still requires zero-active, low-boundary, high-boundary, and competing multi-active coverage
- `NONZERO` still requires zero and nonzero coverage

The change only corrects how existing compiled input vectors are read for duplicate detection and reuse.

### Engineering Lesson

```text
New deterministic compiler stages must consume the typed IR as it exists today, not assumptions from an older action representation.
```

---

## Additive Semantic-Coverage Completion

### Problem

Mandatory semantic-feature synthesis was effectively assigning generated obligation vectors to existing AI cases.

The visible result was that case ids and names survived while their compiled stimuli changed, producing semantically false cases such as an `encode_highest_priority` case that no longer tested the AI-selected highest-priority input vector.

### Root Cause

The mutation happened in two layers:

- generic combinational compilation applied valid AI vector hints first
- the later `PRIORITY_SELECT` / `NONZERO` input strategies then overwrote those same source-signal assignments using deterministic case-index-driven feature vectors

At the same time, mandatory-coverage reuse was too literal. It matched only exact vector values instead of checking whether an existing typed vector already satisfied obligations such as:

- zero-active
- low-boundary one-hot
- high-boundary one-hot
- multi-active competition
- nonzero

### Fix

Existing compiled AI intent cases are now treated as immutable during mandatory semantic coverage completion.

Concretely:

- feature-specific input strategies no longer overwrite an already selected source-signal value
- mandatory obligations are checked against the actual extracted typed input vector semantics
- if an existing case already satisfies an obligation, that coverage is reused without mutation
- only genuinely missing obligations append new deterministic cases

### Obligation Matching

For `PRIORITY_SELECT`, the compiler now checks existing vectors structurally for:

- `source == 0`
- exact lowest-index one-hot
- exact highest-index one-hot
- any vector with at least two asserted source bits

For `NONZERO`, it checks:

- `source == 0`
- `source != 0`

This means one real test vector may legitimately satisfy multiple semantic obligations without requiring duplicate or rewritten cases.

### Important Preservation

This change does not alter deterministic expected-value authority:

- expected outputs still come from deterministic semantic evaluation
- RTL generation was not changed

### Engineering Lessons

```text
Coverage completion must not rewrite the behavior of an existing test case.
```

```text
Case identity and stimulus must remain semantically aligned.
```

```text
Mandatory obligations should be matched against actual typed vectors, not list positions, names, or prose.
```

```text
One physical test vector may satisfy multiple semantic coverage obligations without requiring duplicate cases.
```

---

## VerificationIntent Envelope Misclassification Fix

### Problem

The new `INVALID_VERIFICATION_INTENT_ENVELOPE` guard was too eager to classify some failures as missing-envelope problems even when the final raw model response visibly contained the full top-level `VerificationIntentPlan` object.

That created a misleading failure diagnosis at the verification-intent boundary.

### Fix

VerificationIntent generation now normalizes top-level JSON keys before applying the envelope check, and envelope validation runs against that normalized object.

This keeps `INVALID_VERIFICATION_INTENT_ENVELOPE` reserved for genuinely missing structural envelopes.

If the full envelope is present, the response now falls through to the normal typed schema-validation path or later deterministic compilation checks instead of being misclassified early.

Envelope diagnostics were also improved to report which top-level keys were actually present when the structural check fails.

### Engineering Lesson

```text
A structural guard should diagnose only the specific structure it actually proves is missing.
```

---

## HardwareIntent Descriptive-Metadata Tolerance

### Problem

HardwareIntent generation could fail after retries because the schema required a descriptive `behavior` field even when the authoritative combinational intent was otherwise valid.

That meant missing prose metadata could trigger `HARDWARE_INTENT_INVALID` and consume expensive LLM repair attempts even though deterministic compilation only needed:

- module and design identity
- ports
- combinational intent assignments
- valid typed operators and signal references

### Fix

`HardwareIntent` now distinguishes authoritative compilation fields from descriptive metadata more cleanly.

Descriptive `behavior` metadata now uses a typed default and descriptive normalization:

- missing `behavior` becomes a default typed descriptive structure
- string or other simple descriptive shapes normalize into valid metadata
- tags and notes remain optional descriptive lists

Authoritative semantic and structural fields remain strict.

### Important Preservation

This change does not relax failures for actual executable-intent problems such as:

- missing or malformed `combinational_intent`
- unknown signals
- invalid operators
- width mismatches
- unsupported sequential lowering
- malformed `priority_select` direction or output mode

### Debugging Improvement

`parse_requirement.py --show-intent` now remains useful on HardwareIntent failure:

- if a validated HardwareIntent exists, it is shown
- otherwise the final raw HardwareIntent model response is shown for debugging

### Engineering Lessons

```text
Typed boundaries should be strict about executable meaning, not incidental prose.
```

```text
Missing descriptive metadata should not consume expensive LLM repair retries.
```

```text
LLM robustness improves when authoritative intent and advisory metadata are modeled separately.
```

---

## Final Clarification-State Recompute

### Problem

The ambiguity-resolution pipeline could finish deterministic filtering with zero clarification questions while still carrying a stale `NEEDS_CLARIFICATION`/`ready=False` state.

When that stale state was forwarded directly into `RequirementParseResult`, Pydantic correctly rejected the impossible combination:

- `status = NEEDS_CLARIFICATION`
- `clarification_questions = []`

### Root Cause

`RequirementAnalysis` can still represent a not-ready state with unresolved labels but no questions.

That is acceptable as an intermediate ambiguity-analysis structure, but `RequirementParseResult` is stricter:

- `NEEDS_CLARIFICATION` must have at least one question

The parser boundary was trusting the post-policy `ready` flag directly instead of making one final deterministic decision from the fully filtered state.

### Fix

The parser now performs one authoritative final readiness recomputation immediately before constructing a typed result:

- if clarification questions remain, emit `NEEDS_CLARIFICATION`
- if no unresolved ambiguity remains, promote the requirement to `READY`
- if unresolved ambiguity labels remain but no clarification questions exist, return structured `AMBIGUITY_POLICY_INCONSISTENCY`

This prevents raw Pydantic invariant failures from leaking to the CLI for a normal ambiguity-analysis outcome.

### Engineering Lessons

```text
Typed result invariants must be enforced before model construction, not discovered by Pydantic at runtime.
```

```text
Clarification readiness is a property of the final normalized state, not the original LLM response.
```

```text
Filtering questions and computing status must share one authoritative final decision point.
```

---

## Ambiguity Applicability by Executable Semantics

### Problem

A well-specified combinational add/sub datapath was still blocked by broad ambiguity labels for:

- signedness
- supported arithmetic operations

Even though the requirement already stated:

- `mode = 0` performs addition
- `mode = 1` performs subtraction

deterministic filtering could remove the surviving clarification question while leaving unresolved ambiguity labels behind, which then escalated into `AMBIGUITY_POLICY_INCONSISTENCY`.

### Fix

Ambiguity applicability is now tied more closely to executable semantic relevance instead of broad family convention.

- Explicitly enumerated operation mappings now derive a machine-readable `operations` fact, so broad operation-set ambiguity is resolved when the requirement already names the operations.
- Signedness is now treated as clarification-critical only when the explicitly requested operations can change behavior under signed versus unsigned interpretation.
- When a structured clarification concept is filtered out as inapplicable or already resolved, the matching unresolved ambiguity label is cleared in the same semantic-key space.

For same-width modulo bit-vector operations such as:

- `ADD`
- `SUB`
- `BIT_AND`
- `BIT_OR`
- `BIT_XOR`
- `EQ`
- `NE`
- conditional selection

signedness no longer blocks progress by itself.

For semantically sign-sensitive behavior such as:

- `LT / LE / GT / GE`
- arithmetic right shift
- sign extension
- explicitly signed/unsigned comparison semantics
- saturation or range-sensitive arithmetic semantics

signedness remains clarification-relevant.

### Engineering Lessons

```text
Not every unspecified property is a semantic ambiguity.
```

```text
Clarification should be driven by executable consequence, not domain convention alone.
```

```text
Question filtering and unresolved-evidence cleanup must stay synchronized.
```

---

## Combinational Pipeline Stabilization

### Why

Repeated end-to-end runs were exposing different hidden boundary assumptions one command at a time, including:

- impossible clarification states
- stale ambiguity evidence after filtering
- advisory metadata blocking authoritative intent
- partial structured-output envelopes
- vocabulary collisions between behavior and scenario
- stale typed-IR assumptions
- deterministic coverage rewriting existing AI-authored stimuli

The architecture itself was moving in the right direction, but the supported combinational path still needed explicit invariant coverage at each typed trust boundary.

### Action

Feature work paused to consolidate stage invariants and add deterministic regression coverage across the supported combinational path:

```text
natural-language requirement
→ ambiguity analysis
→ clarification resolution
→ HardwareIntent generation
→ deterministic HardwareIntent compiler
→ HardwareSpec / semantics / semantic_features
→ VerificationIntent generation
→ deterministic verification compiler
→ deterministic testbench IR / rendering
```

The stabilization work focuses on:

- one authoritative invariant decision point per stage boundary where practical
- explicit distinction between authoritative executable fields and advisory/descriptive metadata
- structured deterministic failures instead of raw boundary exceptions for expected invalid inputs
- regression fixtures after the LLM trust boundary so tests remain stable even when model wording changes

### Architectural Principle

```text
LLM outputs may be variable; behavior after the typed trust boundary must be deterministic, invariant-driven, and regression-tested.
```

```text
100% success for arbitrary prompts is not the requirement. Supported requests must either succeed or fail/clarify safely and structurally.
```

### Regression-Suite Follow-Up

The new deterministic regression suite immediately exposed one remaining ambiguity-state bug:

- 13 of 14 tests passed
- the add/sub ambiguity regression still failed

The root cause was not the final readiness checker. The primary canonical ambiguity pass correctly resolved the add/sub case, but a legacy fallback path could still re-introduce sanitized prose ambiguity evidence after all real unresolved semantic keys had already been cleared.

In the failing case, the stale survivor was the prose-derived semantic label equivalent to:

- `signedness_of_inputs_and_output`

That happened because clarification-question filtering and unresolved-evidence cleanup were synchronized in the main canonical pass, but the fallback branch was still allowed to repopulate ambiguity evidence even after deterministic resolution had already succeeded.

### Fix

Resolved or inapplicable semantic keys are now allowed to end the normalization pass cleanly once deterministic resolution has already been applied.

The fallback ambiguity reconstruction path now runs only when ambiguity evidence disappeared **without** any deterministic resolution/filtering step that explains the change.

This keeps the architecture strict:

- deterministic resolution may promote the requirement to `READY`
- unexplained evidence loss still becomes structured inconsistency

### Lesson

```text
A clarification question disappearing is not sufficient; the normalized ambiguity evidence that justified it must be resolved at the same boundary.
```

---

## Deterministic Verification Stimulus Diversity

### Problem

Case-local invalid or missing AI vector hints could cause generic combinational fallback strategies to overwrite too much of the candidate stimulus.

That preserved deterministic correctness, but it collapsed distinct AI intent cases onto identical full input vectors. In the observed add/sub datapath regression, several apparently different cases all converged to the same:

- `ADD`: `a=63, b=1, mode=0`
- `SUB`: `a=0, b=63, mode=1`

This weakened coverage diversity and made case names less representative of their actual stimuli.

### Fix

Generic combinational stimulus selection now repairs cases locally instead of replacing the whole vector:

- valid AI hint fields are preserved
- invalid or missing fields are filled individually
- deterministic behavior-specific defaults populate only unresolved fields
- required semantic control-path values are filled only when missing
- if the resulting full vector still duplicates a previously compiled sibling case, deterministic duplicate-avoidance searches for a legal alternative using only non-protected fields

Negative or out-of-range hints are still rejected conservatively:

- they are recorded in compilation notes
- they are not silently wrapped or reinterpreted
- only the invalid field is replaced

### Lesson

```text
Fallback stimulus generation should repair the smallest invalid portion of a case, not replace the whole case.
```

```text
Deterministic correctness and coverage diversity are separate requirements.
```

---

## Ordered-Comparison Signedness Clarification

### Problem

A complex unseen combinational smoke prompt exposed an upstream ambiguity-policy regression.

The requirement included an ordered comparison:

```text
output a if a is greater than b, otherwise output b
```

but the ambiguity layer still treated the prompt as effectively sign-insensitive and allowed HardwareIntent generation to begin. The downstream HardwareIntent model then invented:

- `a.signed = true`
- `b.signed = true`
- `y.signed = true`

That should never have happened before clarification, because `GT` semantics can change under signed versus unsigned interpretation.

### Root Cause

The signedness applicability rule already treated `LT / LE / GT / GE` as sign-sensitive, but natural-language ordered-comparison phrasing was not reliably entering the structured operation-evidence path that drives local ambiguity policy for non-family-specific combinational prompts.

That left the pipeline without one deterministic reason to inject a signedness clarification when the LLM ambiguity pass missed it.

### Fix

Natural-language ordered comparisons now contribute canonical comparison-operation evidence before signedness applicability is evaluated.

The ambiguity layer now:

- recognizes clear identifier-to-identifier comparison phrases such as `greater than`, `less than`, `greater than or equal to`, `less than or equal to`, `equal to`, and `not equal to`
- marks signedness as clarification-critical when sign-sensitive comparison semantics are present and no explicit signed/unsigned interpretation is given
- emits a deterministic signedness clarification question before HardwareIntent generation

Explicit signedness still resolves the ambiguity cleanly, and same-width raw bit-vector `ADD / SUB / XOR` style prompts still avoid unnecessary signedness questions.

### Engineering Lessons

```text
Semantic applicability is only as reliable as the structured operation evidence feeding it.
```

```text
Sign-sensitive intent must be clarified before crossing the HardwareIntent trust boundary.
```
## 2026-08-19 - HardwareIntent Expressiveness for Complex Combinational Datapaths

Problem:
Complex combinational smoke testing exposed that nested binary conditionals are a fragile LLM representation for opcode dispatch, and that carry-out cannot be represented safely without explicit width-growth semantics. The same run also showed that derived outputs such as zero flags must not depend implicitly on assignment ordering.

Architecture fix:
- Added a high-level `case_select` HardwareIntent primitive for selector-driven multi-way combinational dispatch.
- Kept `priority_select` narrowly scoped to source-bit priority resolution and separated it from generic opcode/mode selection.
- Added explicit semantic width extension so carry-out can be represented by deterministic lowering rather than an invented `CARRY` operator.
- Preserved derived-output safety by validating acyclic output dependencies and allowing deterministic output-to-output references only through the validated semantic graph.

Engineering lessons:
- High-level intent primitives should match common specification structure while still lowering into a small deterministic semantic core.
- Width growth must be explicit; fixed-width arithmetic must not silently change semantics.
- Priority selection and generic multi-way selection are different semantic operations.
- Derived outputs must not depend implicitly on assignment ordering.
## 2026-08-19 - Import Graph Regression After CASE_SELECT Refactor

Problem:
The CASE_SELECT and width-extension refactor left a stale `SignalSpec` import in the HardwareIntent model path, and a related stale validator symbol reference in `hardware_spec.py`. That prevented the deterministic regression suite from importing the production combinational model/compiler path.

Fix:
Model imports now use the current canonical `PortSpec` type from `hardware_spec.py`, and semantic validation calls the current `validate_hardware_semantics(...)` entrypoint. The model export surface was updated consistently for the newly added intent, semantic, and feature types.

Lesson:
Large typed-model refactors must keep the import/export graph regression-tested before semantic behavior can be evaluated.
## 2026-08-19 - Semantic Capabilities Public API Audit

Problem:
The capabilities refactor preserved recursive capability derivation for new semantic expressions but accidentally dropped public helpers still required by verification-plan semantics, including `derive_combinational_semantic_capabilities(...)`. That caused import-time failure before deterministic regressions could run.

Fix:
Audited the full public import surface of `rtl_assistant.semantics.capabilities` and restored the canonical helper set used by verification: combinational capability derivation, hardware-spec capability derivation, token normalization, path matching, and the typed path-match result.

Lesson:
Refactors of shared typed utility modules must preserve or deliberately migrate their public API as a unit.
Import-surface regression is part of architecture stability, not a downstream test concern.
## 2026-08-19 - Shared Contract Restoration After Semantic Expressiveness Refactor

Regression suite result:
The CASE_SELECT / explicit width-extension refactor imported cleanly but exposed two shared contract regressions across many deterministic tests:
1. `evaluate_combinational_semantics(...)` confused the outer `HardwareSemantics` wrapper with the already-extracted `CombinationalSemantics` object used by current callers.
2. `BehaviorSpec` became strict again even though behavior metadata is advisory and must remain default-constructible.

Fix:
Restored the canonical evaluator contract to consume `CombinationalSemantics` directly, audited all evaluator call sites to align with that API, and restored a typed neutral default for `BehaviorSpec.description` so descriptive behavior metadata can remain optional without weakening authoritative HardwareIntent fields.

Lessons:
- Adding semantic expressiveness must not silently change established public function contracts.
- Advisory metadata defaults are part of the typed API and must survive refactors.
- Repeated test failures should be traced to shared boundaries before individual cases are patched.
## 2026-08-19 - Final Two Regressions After CASE_SELECT / ExtendExpr Refactor

After restoring the shared evaluator and capabilities APIs, the deterministic regression suite was down to two remaining failures.

1. Output-dependency cycle rejection was already happening correctly during `HardwareSpec` construction through the integrated semantic validator. The stale regression expectation was updated to assert rejection at that earlier authoritative typed boundary instead of weakening production validation.

2. Priority-selection evaluation for the `priority8` fixture was producing the wrong encoded index because `PRIORITY_SELECT` lowering wrapped nested `SelectExpr` nodes in the wrong order for `HIGHEST_INDEX_FIRST`. The fix was to preserve the existing evaluator and correct the lowering order itself.

Cleanup:
Removed an ignored `notes=intent.notes` argument from `HardwareIntent -> HardwareSpec` construction rather than relying on silent dropping of unknown fields.
## 2026-08-19 - HardwareIntent Prompt Reliability Pass for Local 7B

Goal:
Improve first-pass HardwareIntent quality for the current local 7B model without changing the typed semantic architecture.

Approach:
- Rewrote the HardwareIntent generation prompt into a shorter structured format: role, hard rules, primitive-selection guide, canonical mini-examples, and output contract.
- Added exact-schema mini-examples for CASE_SELECT, PRIORITY_SELECT, zero flags, carry-out via extend + ADD + bit_select, and max(a,b) via CONDITIONAL(GT(...)).
- Strengthened the strict JSON contract and explicitly forbade invented operators and pseudo-primitives.
- Reworked the HardwareIntent repair prompt to demand a complete corrected object, preserve valid portions, and apply targeted DSL correction hints for common structural mistakes.

Reason:
Recent smoke tests showed that remaining failures were often not missing compiler capability but model misuse of the existing DSL.

Important principle:
Prompt tuning should teach the model to cross the typed boundary correctly; deterministic validation remains authoritative.
## 2026-08-19 - HardwareIntent design_type Contract Audit

Problem:
The first complex smoke test after HardwareIntent prompt tuning reached intent generation but crashed before semantic evaluation because `ai_parser` assumed `HardwareIntent.design_type` exposed `.value`, while the current validated object exposed a plain string.

Fix:
Unified `HardwareIntent.design_type` with the existing shared `DesignType` enum used by `HardwareSpec`, so JSON `"combinational"` validates into one canonical in-memory representation and downstream consumers can rely on the enum contract consistently.

Lesson:
JSON representation and validated in-memory representation must have an explicit stable contract; downstream code must not assume Enum APIs unless the model guarantees them.
## 2026-08-19 - Nested Carry Lowering Symbol-Resolution Fix

Prompt-tuned complex smoke testing successfully produced the intended high-level DSL: CASE_SELECT for opcode dispatch, a correct max conditional, zero as EQ(y,0), and explicit carry width-extension semantics.

However deterministic HardwareIntent lowering rejected a declared input inside the nested carry expression with `INTENT_SIGNAL_NOT_FOUND`.

Root cause:
The carry expression itself used valid nested input references, but top-level `conditional` assignments also feed semantic-constraint synthesis. That helper was recursively lowering the condition and true branch with an empty signal environment instead of the canonical declared-port symbol table, so declared inputs such as `a` and `b` became invisible only on that path.

Fix:
Semantic-constraint synthesis now reuses the same canonical signal environment as the main HardwareIntent lowering path.

Why existing carry regression coverage missed it:
The earlier deterministic carry fixture used CASE_SELECT for carry gating, which never exercised the top-level CONDITIONAL constraint-building path reached by the prompt-tuned smoke test.

Lesson:
Once the LLM produces a valid typed intent, deterministic lowering must preserve one canonical symbol environment recursively through every expression primitive.
## 2026-08-19 - HardwareIntent Port Schema Completeness Prompt Hardening

The complex prompt-tuned smoke test now generated the correct semantic DSL but omitted required port directions on all ports across retries.

This was a schema-adherence problem, not a missing semantic capability.

Fix:
The HardwareIntent generation prompt now makes the required port structure explicit near the authoritative shape, includes compact input/output port examples, adds a short pre-output checklist, and the repair-hint layer now gives a targeted correction when Pydantic reports missing `ports -> ... -> direction` fields.

Lesson:
Prompt tuning should separately optimize semantic selection and schema completeness; success in one does not imply success in the other.
## 2026-08-19 - Post-Clarification Requirement Analysis Hardening

The complex smoke test passed the initial ambiguity stage and correctly asked only signedness, but post-clarification analysis regressed by:
1. emitting malformed analysis JSON;
2. forgetting an explicitly stated opcode mapping and asking for it again.

Fix:
Requirement-analysis JSON guidance and repair were tightened with an exact valid envelope example and explicit array-vs-object rules. Deterministic selector-mapping evidence preservation was also hardened so explicit selector/opcode behavior survives re-analysis and filters redundant opcode-mapping questions.

Lessons:
- Clarification must monotonically enrich requirements; it must not erase previously explicit facts.
- LLM-proposed ambiguity must be filtered against deterministic explicit evidence.
- Structured analysis JSON and HardwareIntent JSON are separate trust boundaries and require separate prompt/repair guarantees.
- August 19, 2026: After adding generic selector/opcode mapping evidence, normalization correctly removed a stale LLM-proposed `opcode_mapping` ambiguity but failed to mark that removal as deterministic resolution. Canonical explicit-evidence filtering now participates in the same deterministic-resolution bookkeeping used by final readiness validation. Lesson: removing stale ambiguity and proving why it was removed are both part of the deterministic contract; safety invariants must distinguish unexplained information loss from evidence-backed resolution.
- August 19, 2026: The selector-mapping bookkeeping fix introduced a stale duplicate-`family` argument when canonicalizing clarification-question semantic identities. The call now matches the canonical `canonical_semantic_identity(...)` signature again without changing ambiguity policy.
- August 19, 2026: The complex smoke test exposed two remaining front-end reliability issues: ambiguity analysis still proposed redundant explicit-behavior and inferred-implementation questions, and HardwareIntent semantics were correct but nested JSON structure was malformed after retries. Clarification filtering now treats explicit output/status rules as resolved semantic evidence and suppresses inferred internal implementation questions such as mux-structure prompts unless that primitive is explicitly requested. Lesson: behavioral clarification must not ask the user to reconfirm explicitly specified outputs; internal implementation choices must not leak into requirement clarification; semantic correctness and syntactic JSON correctness are separate model reliability dimensions.

## 2026-08-24 - HardwareIntent Generation and Repair Reliability

The complex combinational smoke test showed that primitive-selection prompt tuning was working, but HardwareIntent generation still failed along three general model-interface dimensions:
1. syntactically malformed nested HardwareIntent JSON;
2. unnecessary width growth in ordinary fixed-width assignments;
3. loss or inversion of explicit conditional derived-output behavior.

Fix:
JSON extraction failures now use a focused syntax-repair prompt containing the malformed response, parser error, complete-object contract, and exact compact nested-expression shapes. Generation and typed repair guidance now distinguish fixed-width result arithmetic from separate widened derived expressions, preserve explicit conditional output rules, and distinguish value-producing BIT_SELECT from boolean EQ comparisons.

The HardwareIntent schema, deterministic compiler, and semantic validation remain strict and unchanged.

Principle:
The model should be helped to express the intended semantics correctly; deterministic code should validate, not silently repair, invalid intent.

## 2026-08-24 - Resolved Behavioral Obligations Across the Intent Trust Boundary

Problem:
A HardwareIntent could be schema-valid and compiler-valid while still losing a resolved conditional behavior from the requirement. Representation validation alone could not detect that an explicitly specified condition or otherwise branch had disappeared before executable intent was established.

Architecture fix:
The requirement-analysis boundary now preserves confidently detected behavioral obligations as lightweight typed facts containing the target, condition, behavior under that condition, explicit otherwise behavior, completeness, and evidence source. Complete obligations are carried monotonically through clarification and handed to HardwareIntent generation and repair in a compact authoritative section. Partial conditional rules remain unresolved and may still require clarification because no default behavior was supplied.

This structure is not a second executable HardwareIntent or semantic AST. It preserves resolved user meaning at the trust boundary while the existing HardwareIntent compiler and semantic validator remain authoritative for executable representation.

Principle:
Validation of representation is not sufficient if resolved user semantics can disappear before the typed executable boundary.
