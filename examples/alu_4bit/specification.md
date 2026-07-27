# 4-Bit ALU Specification

## Description

The module is a combinational 4-bit arithmetic and logic unit.

## Inputs

- `a`: 4-bit unsigned input
- `b`: 4-bit unsigned input
- `opcode`: 2-bit operation selector

## Outputs

- `result`: 4-bit result
- `carry`: carry-out for addition
- `zero`: high when result is zero

## Operations

| Opcode | Operation |
|--------|-----------|
| 00 | a + b |
| 01 | a - b |
| 10 | a AND b |
| 11 | a OR b |

## Behaviour

- Arithmetic is unsigned.
- Results wrap around to 4 bits.
- `carry` is meaningful only for addition.
- For all other operations, `carry` must be zero.
- `zero` must be one whenever `result` equals `0000`.
- The ALU is combinational and has no clock or reset.****
