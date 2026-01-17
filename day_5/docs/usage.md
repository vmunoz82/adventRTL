# Usage Guide

This document covers how to run tests, generate Verilog, and perform formal verification for the Range Merger hardware project.

**Important:** All commands should be run from the **project root directory**.

## Running Python Tests

### Amaranth RTL Tests

Run the Amaranth simulation-based tests:

```bash
# Test merge sort RTL
python3 -m amaranth_benchs.rtl_merge_sort_tests [test_file]

# Test range merger RTL
python3 -m amaranth_benchs.rtl_range_merger_tests [test_file]

# Test range checker RTL
python3 -m amaranth_benchs.rtl_range_checker_tests [test_file]

# Test interval coverage RTL
python3 -m amaranth_benchs.rtl_interval_coverage_tests [test_file]
```

Default test file is `testcases/default_input.txt` if not specified.

## Generating Verilog Files

Generate Verilog from RTL modules using Python module invocation:

```bash
# Generate range checker system Verilog
python3 -m rtl.range_checker generated/range_checker_system.v

# For other modules, you can generate Verilog programmatically:
python3 -c "from rtl.range_merger import RangeMerger; from amaranth.back import verilog; top = RangeMerger(); v = verilog.convert(top, ports=[top.start_in, top.end_in, top.valid_in, top.last_in, top.start_out, top.end_out, top.valid_out, top.last_out, top.ready]); print(v)" > generated/range_merger.v
```

## Formal Verification

### Hypothesis Property-Based Testing

Run property-based tests using Hypothesis:

```bash
# Run all hypothesis tests
python3 -m pytest formal/tests_hypothesis.py -v

# Run with specific settings
python3 -m pytest formal/tests_hypothesis.py -v --tb=short

# Run with increased examples
python3 -m pytest formal/tests_hypothesis.py -v --hypothesis-seed=0
```

### SymbiYosys Formal Verification

Run formal verification with SBY (requires SymbiYosys and Yosys):

```bash
# Generate RTLIL for merge sort formal verification
python3 -m formal.merge_sort

# Generate RTLIL for range merger formal verification
python3 -m formal.range_merger

# Run merge sort formal verification (bmc mode)
sby -f formal/merge_sort.sby bmc

# Run merge sort formal verification (prove mode)
sby -f formal/merge_sort.sby prove

# Run range merger formal verification (bmc mode)
sby -f formal/range_merger.sby bmc

# Run range merger formal verification (prove mode)
sby -f formal/range_merger.sby prove
```

## Module Reference

| Module | Layer | Purpose | Test Command |
|--------|-------|---------|--------------|
| `range_merger` | rtl | Merges overlapping ranges | `python3 -m amaranth_benchs.rtl_range_merger_tests` |
| `merge_sort` | rtl | BRAM-based merge sort | `python3 -m amaranth_benchs.rtl_merge_sort_tests` |
| `range_checker` | rtl | Polygon validation checks | `python3 -m amaranth_benchs.rtl_range_checker_tests` |
| `interval_coverage` | rtl | Calculates total coverage | `python3 -m amaranth_benchs.rtl_interval_coverage_tests` |
