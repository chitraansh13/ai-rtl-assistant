# Yosys Synthesis Notes

## Tool

Yosys Version:

0.68+post

---

# Objective

The objective of synthesis is to convert synthesizable RTL into a hardware representation consisting of logic gates, multiplexers, flip-flops, arithmetic units, and memories.

Unlike simulation, synthesis determines what hardware can actually be implemented.

---

# Synthesis Flow Used

```text
read_verilog -sv
↓

hierarchy

↓

proc

↓

opt

↓

memory

↓

opt

↓

stat

↓

write_json

↓

write_verilog
```

---

# Explanation of Commands

### read_verilog -sv

Reads the SystemVerilog RTL source.

---

### hierarchy

Finds the top module and checks the module hierarchy.

---

### proc

Converts procedural always_ff blocks into hardware structures.

---

### opt

Performs logic optimization and removes redundant hardware.

---

### memory

Infers memories from register arrays and optimizes memory implementation.

---

### stat

Prints synthesis statistics.

---

### write_json

Generates a machine-readable synthesized netlist.

---

### write_verilog

Generates synthesized Verilog RTL.

---

# Synthesis Statistics

Number of wires:
119

Number of wire bits:
453

Public wires:
29

Public wire bits:
165

Ports:
9

Port bits:
27

Total cells:
114

---

# Cell Breakdown

| Cell | Count |
|------|------:|
| $add | 3 |
| $sub | 1 |
| $and | 40 |
| $or | 1 |
| $not | 4 |
| $mux | 28 |
| $pmux | 1 |
| $eq | 6 |
| $logic_and | 2 |
| $logic_not | 3 |
| $reduce_bool | 3 |
| $reduce_or | 2 |
| $dffe | 16 |
| $sdffe | 4 |

---

# Observations

The FIFO synthesized successfully without errors.

Yosys inferred sequential storage from the always_ff blocks.

The FIFO memory array was recognized during the memory optimization passes and converted into synthesizable storage elements.

Conditional statements were synthesized into multiplexers.

Arithmetic operations such as incrementing and decrementing the FIFO count were synthesized into adders and subtractors.

Optimization passes removed redundant logic and unused wires while preserving functionality.

---

# Conclusion

The parameterized synchronous FIFO is fully synthesizable.

The generated hardware contains arithmetic logic, multiplexers, flip-flops, comparison logic, and synthesized memory required to implement FIFO functionality.

The generated JSON and synthesized Verilog netlists can be used by later stages of the AI-Driven RTL Design and Verification Assistant.