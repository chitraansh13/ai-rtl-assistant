# Synchronous FIFO Specification

## Module Name

fifo_sync

---

## Description

A parameterized synchronous First-In First-Out (FIFO) memory.

The FIFO stores data in the same order that it is written.

The first value written into the FIFO is the first value read from the FIFO.

All operations occur on the rising edge of the clock.

---

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| DATA_WIDTH | 8 | Width of each data word |
| DEPTH | 16 | Number of storage locations |

---

## Inputs

- clk
- rst
- wr_en
- rd_en
- data_in

---

## Outputs

- data_out
- full
- empty
- count

---

## Functional Behavior

### Reset

When rst is asserted:

- Write pointer becomes 0
- Read pointer becomes 0
- Count becomes 0
- FIFO becomes empty

---

### Write

A write occurs when:

- wr_en = 1
- FIFO is not full

The input data is stored at the write pointer.

The write pointer increments.

Count increments.

---

### Read

A read occurs when:

- rd_en = 1
- FIFO is not empty

The data at the read pointer is returned.

The read pointer increments.

Count decrements.

---

### Full Condition

The FIFO is full when:

count == DEPTH

---

### Empty Condition

The FIFO is empty when:

count == 0

---

### Simultaneous Read and Write

If both wr_en and rd_en are asserted simultaneously:

- One value is written
- One value is read
- Count remains unchanged

---

### Pointer Wraparound

When a pointer reaches the final memory location, it wraps back to zero.

---

## Verification Goals

- Reset
- Single write
- Multiple writes
- Single read
- Multiple reads
- FIFO ordering
- Full detection
- Empty detection
- Pointer wraparound
- Simultaneous read/write
- Count correctness
- Parameterization