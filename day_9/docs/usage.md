# Usage Guide

This document covers how to run tests, generate Verilog, perform formal verification, and use Verilator simulation.

## Running Python Tests

**Important:** All Python test commands should be run from the **project root directory**.

### Verilator Python Wrapper Tests

Run the compiled Verilator simulations via Python ctypes wrappers:

```bash
# RTL max rectangle finder test
python3 verilator_benchs/python/rtl_max_rect.py [input.txt] [--waveform output.fst]

# ASCII wrapper test
python3 verilator_benchs/python/impl_ascii.py [input.txt] [--waveform output.fst]

# UART loopback test (outputs raw coordinate stream for visualization)
python3 verilator_benchs/python/impl_uart.py [input_file] [--waveform output.fst]

# UART bridge test (full ASCII -> UART -> MaxRectangle -> UART -> result flow)
python3 verilator_benchs/python/impl_uart_bridge.py [input.txt] [--waveform output.fst]
```

### Software Reference Tests

Run the pure Python reference implementation:

```bash
# From file
python3 software_reference/max_rectangle_finder.py [input.txt] [--verbose]

# From stdin
echo "0,0\n100,0\n100,100\n0,100\n" | python3 software_reference/max_rectangle_finder.py

# Compare software reference vs RTL
python3 software_reference/compare_rtl.py testcase/input.txt
```

## Generating Verilog Files

### Using Python Module Invocation

Generate Verilog directly from Amaranth modules:

```bash
# From rtl/ directory
python3 -m rtl.max_rectangle_finder generated/verilog/rtl_max_rect.v
python3 -m rtl.validate_rectangle generated/verilog/validate_rectangle.v
python3 -m rtl.checks generated/verilog/checks.v

# From impl/ directory
python3 -m impl.ascii_wrapper generated/verilog/impl_ascii.v
python3 -m impl.uart generated/verilog/impl_uart.v
python3 -m impl.uart_bridge generated/verilog/impl_uart_bridge.v
```

### Using the Makefile

Generate Verilog via the build system:

```bash
cd verilator_benchs

# Generate all Verilog files
make verilog

# Generate specific module Verilog
make rtl-max-rect-verilog    # RTL max rectangle finder
make impl-ascii-verilog      # ASCII wrapper
make impl-uart-verilog       # UART TX/RX
make impl-uart-bridge-verilog # UART bridge
```

## Formal Verification

The UART implementation includes formal verification using `amaranth.asserts`. To run formal verification:

```bash
# Formal verification requires the SBY (SymbiYosys) tool and Yosys
# The formal platform is enabled when platform="formal" is passed to elaborate()

# Example: Run formal verification on UART modules
sby -f formal/uart_tx.sby
sby -f formal/uart_rx.sby
```

Note: The `formal/` directory currently exists but is empty. Formal verification assertions are embedded in `impl/uart.py`:
- `TX._add_formal_verification()` - Transmitter formal checks
- `RX._add_formal_verification()` - Receiver formal checks
- `LoopbackDevice` formal verification - End-to-end verification

## Verilator Test Generation and Execution

### Build Flow

```
Amaranth HDL (.py) -> Verilog (.v) -> Verilator -> Shared Library (.so) -> Python ctypes
```

### Using the Makefile

```bash
cd verilator_benchs

# Build all shared libraries
make libs

# Build specific module library
make rtl-max-rect-lib      # Build librtl_max_rect.so
make impl-ascii-lib        # Build libimpl_ascii.so
make impl-uart-lib         # Build libimpl_uart.so
make impl-uart-bridge-lib  # Build libimpl_uart_bridge.so

# Run all tests (NOTE: test targets require absolute paths or run from project root)
make test

# Run specific test (NOTE: these targets look for testcase/default_input.txt from current dir)
make test-rtl-max-rect
make test-impl-ascii
make test-impl-uart
make test-impl-uart-bridge

# Alternative: Run tests directly
cd python && python3 rtl_max_rect.py testcase/default_input.txt

# Clean build artifacts
make clean
make clean-all  # Also removes generated Verilog
```

### Manual Build Steps

If you need to build manually without the Makefile:

```bash
# 1. Generate Verilog from Amaranth
python3 -m rtl.max_rectangle_finder generated/verilog/rtl_max_rect.v

# 2. Compile with Verilator
verilator --cc -O3 -Wno-lint -Wno-style --trace-fst \
  --Mdir verilator_benchs/obj_dir/rtl_max_rect \
  --top-module top \
  generated/verilog/rtl_max_rect.v

# 3. Build the Verilator C++ model
make -C verilator_benchs/obj_dir/rtl_max_rect -f Vtop.mk

# 4. Compile the shared library
g++ -shared -fPIC -O3 -std=c++17 \
  -I/usr/local/share/verilator/include \
  -o verilator_benchs/lib/librtl_max_rect.so \
  verilator_benchs/wrappers/rtl_max_rect.cpp \
  verilator_benchs/obj_dir/rtl_max_rect/Vtop__ALL.cpp \
  /usr/local/share/verilator/include/verilated.cpp \
  /usr/local/share/verilator/include/verilated_fst_c.cpp \
  -Iverilator_benchs/obj_dir/rtl_max_rect \
  -lz

# 5. Run the Python test
python3 verilator_benchs/python/rtl_max_rect.py
```

## Module Reference

| Module | Layer | Purpose | Test Command |
|--------|-------|---------|--------------|
| `max_rectangle_finder` | rtl | Core rectangle finding algorithm | `python3 verilator_benchs/python/rtl_max_rect.py` |
| `validate_rectangle` | rtl | Polygon validation checks | (used by max_rectangle_finder) |
| `checks` | rtl | Individual validation checks | (used by validate_rectangle) |
| `ascii_wrapper` | impl | ASCII I/O wrapper | `python3 verilator_benchs/python/impl_ascii.py` |
| `uart` | impl | UART TX/RX implementation | `python3 verilator_benchs/python/impl_uart.py` |
| `uart_bridge` | impl | UART bridge with finder backend | `python3 verilator_benchs/python/impl_uart_bridge.py` |
