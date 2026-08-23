# Combinational Smoke Manifest

These manual prompts exercise the current supported combinational pipeline end to end.

They are intentionally separate from the deterministic regression suite:

- deterministic regressions validate typed behavior after the LLM trust boundary
- these smoke runs validate live ambiguity handling, HardwareIntent generation, RTL generation, and tool orchestration

## Suggested Manual Prompts

### A. Straightforward Arithmetic Datapath

```text
Create a 6-bit combinational module with 6-bit inputs a and b, a 1-bit input mode, and a 6-bit output y. When mode is 0, y should equal a plus b. When mode is 1, y should equal a minus b.
```

### B. Composed Conditional Datapath

```text
Create a 4-bit combinational module with inputs a, b and sel. When sel is 0 output a+b, otherwise output a XOR b.
```

### C. Priority Selection

```text
Create an 8-bit priority encoder with highest-index-first priority, an encoded output, and a valid output.
```

### D. Vague Clarification Path

```text
Create an 8-bit ALU with arithmetic and logic operations.
```

### E. Unsupported or Deferred Sequential Behavior

Use one clearly sequential prompt that should still clarify, fail safely, or route through the current legacy/sequential architecture according to the current implementation boundary.
