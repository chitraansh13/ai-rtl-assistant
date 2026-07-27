from pathlib import Path
import subprocess
import sys


def main() -> int:
    repository_root = Path(__file__).resolve().parent.parent

    rtl_file = repository_root / "examples" / "alu_4bit" / "alu_4bit.sv"
    testbench_file = repository_root / "examples" / "alu_4bit" / "alu_4bit_tb.sv"
    simulation_file = repository_root / "examples" / "alu_4bit" / "alu_sim"

    if not rtl_file.exists():
        print(f"ERROR: RTL file not found: {rtl_file}")
        return 1

    if not testbench_file.exists():
        print(f"ERROR: Testbench file not found: {testbench_file}")
        return 1

    compile_command = [
        "iverilog",
        "-g2012",
        "-o",
        str(simulation_file),
        str(rtl_file),
        str(testbench_file),
    ]

    print("Compiling ALU...")

    compile_result = subprocess.run(
        compile_command,
        capture_output=True,
        text=True,
    )

    if compile_result.returncode != 0:
        print("COMPILATION FAILED")
        print(compile_result.stderr)
        return 1

    print("Compilation successful")
    print("Running simulation...")

    simulation_result = subprocess.run(
        ["vvp", str(simulation_file)],
        capture_output=True,
        text=True,
    )

    print(simulation_result.stdout)

    if simulation_result.returncode != 0:
        print("SIMULATION FAILED")
        print(simulation_result.stderr)
        return 1

    if "ALL ALU TESTS PASSED" in simulation_result.stdout:
        print("FINAL RESULT: PASS")
        return 0

    print("FINAL RESULT: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())