# Teammate Setup

This guide is the quickest way to get the current repository running on a new machine, especially macOS.

## macOS Quick Start

1. Clone the repository.

```bash
git clone https://github.com/chitraansh13/ai-rtl-assistant.git
cd ai-rtl-assistant
```

2. Install hardware and local-LLM tools with Homebrew.

```bash
brew install icarus-verilog verilator yosys ollama
```

3. Create and activate a Python virtual environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

4. Start Ollama and pull the default model.

```bash
ollama serve
```

In another terminal:

```bash
ollama pull qwen2.5-coder:7b
```

5. Run the environment doctor.

```bash
python scripts/check_environment.py
```

6. Validate one known spec.

```bash
python scripts/validate_spec.py examples/specs/alu_4bit.json
```

7. Generate a verification plan.

```bash
python scripts/generate_verification_plan.py \
  examples/specs/alu_4bit.json \
  --output reports/alu_4bit_verification_plan.json
```

8. Generate a deterministic testbench.

```bash
python scripts/generate_testbench.py \
  examples/specs/alu_4bit.json \
  reports/alu_4bit_verification_plan.json \
  --output generated/alu_4bit_tb.sv
```

9. Run one known-good deterministic verification example using the checked-in manual RTL and testbench.

```bash
python scripts/verify_rtl.py \
  --rtl examples/alu_4bit/alu_4bit.sv \
  --testbench examples/alu_4bit/alu_4bit_tb.sv \
  --top alu_4bit \
  --report reports/alu_verification.json
```

## Notes

- If `scripts/check_environment.py` says the deterministic pipeline is ready but AI features are not, the usual missing piece is either:
  - Ollama is not running
  - `qwen2.5-coder:7b` has not been pulled yet
- Deterministic Step 14 testbench rendering does not require Ollama once a valid `VerificationPlan` already exists.
- Windows currently uses WSL for Verilator and Yosys; macOS and Linux use native tool binaries.
