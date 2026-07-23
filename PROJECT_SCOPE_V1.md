# AI-Driven RTL Design and Verification Assistant

## Version 1 Goal

Build a local system that accepts a natural-language description of a supported
digital circuit, generates SystemVerilog RTL and a testbench, runs simulation,
and reports whether the design passed or failed.

## Initially Supported Circuits

1. 2:1 Multiplexer
2. 4-bit ALU
3. 4-bit synchronous counter

## Version 1 Pipeline

Natural-language specification
→ Structured hardware specification
→ SystemVerilog RTL
→ Testbench
→ Icarus Verilog compilation
→ Simulation
→ Pass/fail report

## Tools

- Python
- SystemVerilog
- Icarus Verilog
- GTKWave
- Verilator
- Yosys
- Git
- GitHub
- Docker later

## Not Included in Version 1

- Web frontend
- Database
- RAG
- LangGraph
- FPGA deployment
- ASIC physical design
- Complex processors
- Multiple clock domains

## Team Responsibilities

### CSE Developer

- Python automation
- LLM integration
- Pipeline orchestration
- Tool execution
- Result parsing
- Software testing

### ECE Developer

- Hardware specifications
- Golden RTL designs
- Testbenches
- Expected output definitions
- Waveform validation
- Synthesis validation

## First Success Condition

The project reaches its first success when a manually written 2:1 multiplexer
and testbench can be compiled and simulated automatically through a Python
command.