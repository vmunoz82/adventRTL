# Advent of Code 2025 - RTL Implementations

Hardware implementations of selected Advent of Code 2025 puzzles in Amaranth HDL.

## Overview

This project implements solutions for Advent of Code 2025 puzzles using RTL (Register Transfer Level) design. The implementations target FPGA devices and include simulation, formal verification, and hardware testing.

### Implemented Puzzles

| Day | Problem | Algorithm | Status |
|-----|---------|-----------|--------|
| 5 | Range sort/merge/traversal | BRAM merge sort, range merge, binary search | Complete - formal verification with SymbiYosys |
| 9 | Maximum Rectangle in Polygon | Rectangle finding, O(N³) with pruning | Complete - deployed to TangNano 9K FPGA |

## Requirements

- Amaranth HDL 0.4.dev19+
- Verilator 4.223+
- SymbiYosys with Yosys 0.17+

## Quick Start

### Day 5 - Range Merger

```bash
cd day_5

# Run range merger tests
python3 -m amaranth_benchs.rtl_range_merger_tests [test_file]

# Generate formal verification files
python3 -m formal.merge_sort
```

**Example output:**
```
================================================================================
Amaranth HDL Range Merger Verification Suite
================================================================================

[OK] ALL TESTS PASSED! Hardware RTL verified against software!
  Software: 48 ranges, coverage = 432675568113956
  Hardware: 48 ranges, coverage = 432675568113956
```

### Day 9 - Maximum Rectangle

```bash
cd day_9

# Run ASCII wrapper simulation
python3 verilator_benchs/python/impl_ascii.py [input.txt] [--waveform output.fst]
```

**Example output:**
```
2151361240
Loading input from: testcase/default_input.txt
Input bytes: 3116

Results:
  Done: True
  Result: 2151361240
  Cycles: 1313686
  Time: 1.625s
  Rate: 0.81M cycles/sec
```

## Project Structure

```
adventRTL/
├── day_5/              # Day 5: Range Merger with Merge Sort
│   ├── rtl/            # Core RTL modules
│   ├── formal/         # SymbiYosys formal verification
│   ├── amaranth_benchs/  # Amaranth simulation tests
│   └── docs/           # Detailed documentation
│
└── day_9/              # Day 9: Maximum Rectangle Finder
    ├── rtl/            # Core RTL modules
    ├── impl/           # I/O wrappers (ASCII, UART)
    ├── docs/           # Detailed documentation
    └── verilator_benchs/  # Verilator simulation tests
```

### Documentation

- [Day 5 Usage Guide](day_5/docs/usage.md)
- [Day 9 Usage Guide](day_9/docs/usage.md)

## Implementation Notes

**Day 5:** Range merger using BRAM-based merge sort with streaming output. Formal verification passed for N≤4 with 471 property-based tests. Performance: 5,865 cycles for 173 ranges at 100 MHz.

**Day 9:** Maximum area axis-aligned rectangle within a rectilinear polygon. Optimizations include area pruning, single polygon load, and Double Dabble BCD conversion. Deployed on TangNano 9K FPGA with UART communication.

## License

MIT License - Copyright (c) 2026 Victor Muñoz

All problem statements and test cases included in this repository are original work. No third-party copyright material is included.

## TODO

- Add documentation
- Improve FMAX
- Implement Day 5 in FPGA
- Implement Day 9 on a larger FPGA
- Improve pipeline usage of Day 9
- Try interfaces beyond UART
- Make a generic harness
- Make Day 9 parallel/multicore
- Measure and benchmark Joules/Ops vs software
- Write a detailed writeup
