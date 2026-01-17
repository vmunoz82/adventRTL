# =============================================================================
# Modular Verilator Testbench Build System
# =============================================================================
#
# This Makefile builds Python ctypes-based testbenches for RTL modules.
# To add a new module, just add an entry to the MODULES list below.
#
# Flow: Amaranth (.py) -> Verilog (.v) -> Verilator -> Shared Lib (.so) -> Python
#
# =============================================================================

#==============================================================================
# CONFIGURATION
#==============================================================================

# Directories (relative to this Makefile)
ROOT        := ..
RTL_DIR     := $(ROOT)/rtl
IMPL_DIR    := $(ROOT)/impl
VERILOG_DIR := $(ROOT)/generated/verilog
LIB_DIR     := lib
OBJ_DIR     := obj_dir
WRAPPER_DIR := wrappers
PYTHON_DIR  := python

# Tools
PYTHON      := python3
VERILATOR   := verilator
CXX         := g++

# Verilator flags
VERILATOR_FLAGS := --cc -O3 -Wno-lint -Wno-style
VERILATOR_FLAGS += --trace-fst  # Enable FST tracing (optional, controlled at runtime)

# Verilator runtime library path (check multiple locations)
VERILATOR_ROOT := $(shell \
    if [ -d "/usr/local/share/verilator" ]; then echo "/usr/local/share/verilator"; \
    elif [ -d "/usr/share/verilator" ]; then echo "/usr/share/verilator"; \
    else pkg-config --variable=datadir verilator 2>/dev/null || echo "/usr/share/verilator"; fi)

# C++ compiler flags for shared library
CXX_FLAGS := -shared -fPIC -O3 -std=c++17
CXX_FLAGS += -I$(VERILATOR_ROOT)/include

#==============================================================================
# MODULE DEFINITIONS
# Format: <name>:<layer>:<python_module_path>
#
# - name: Short name for the module (used in target names)
# - layer: rtl or impl (determines source directory)
# - python_module_path: Path to Python module (without .py)
#==============================================================================

MODULES := \
    max-rect:rtl:rtl/max_rectangle_finder \
    ascii:impl:impl/ascii_wrapper \
    uart:impl:impl/uart \
    uart-bridge:impl:impl/uart_bridge

#==============================================================================
# HELPER FUNCTIONS
#==============================================================================

# Extract parts from module definition
module_name  = $(word 1,$(subst :, ,$1))
module_layer = $(word 2,$(subst :, ,$1))
module_path  = $(word 3,$(subst :, ,$1))

# Generate full name: layer_name (e.g., rtl_max-rect)
full_name = $(call module_layer,$1)_$(call module_name,$1)

# Convert dashes to underscores for file names
file_name = $(subst -,_,$(call full_name,$1))

#==============================================================================
# AUTO-GENERATED TARGET LISTS
#==============================================================================

ALL_VERILOG := $(foreach m,$(MODULES),$(VERILOG_DIR)/$(call file_name,$m).v)
ALL_LIBS    := $(foreach m,$(MODULES),$(LIB_DIR)/lib$(call file_name,$m).so)
ALL_TESTS   := $(foreach m,$(MODULES),test-$(call full_name,$m))

#==============================================================================
# MAIN TARGETS
#==============================================================================

.PHONY: all verilog libs test clean clean-all help

all: libs

verilog: $(ALL_VERILOG)
	@echo "All Verilog files generated"

libs: $(ALL_LIBS)
	@echo "All shared libraries built"

test: $(ALL_TESTS)
	@echo "All tests completed"

clean:
	@echo "Cleaning build artifacts..."
	rm -rf $(OBJ_DIR)/*
	rm -rf $(LIB_DIR)/*.so
	@echo "Clean complete"

clean-all: clean
	@echo "Cleaning generated Verilog..."
	rm -rf $(VERILOG_DIR)/*.v
	@echo "Clean-all complete"

help:
	@echo "=============================================================="
	@echo "Modular Verilator Testbench Build System"
	@echo "=============================================================="
	@echo ""
	@echo "Main targets:"
	@echo "  make verilog     - Generate all Verilog files"
	@echo "  make libs        - Build all shared libraries"
	@echo "  make test        - Run all Python tests"
	@echo "  make clean       - Clean build artifacts"
	@echo "  make clean-all   - Clean everything including Verilog"
	@echo ""
	@echo "Per-module targets (replace <m> with module name):"
	@echo "  make <layer>-<name>-verilog  - Generate Verilog"
	@echo "  make <layer>-<name>-lib      - Build shared library"
	@echo "  make test-<layer>-<name>     - Run Python test"
	@echo ""
	@echo "Available modules:"
	@$(foreach m,$(MODULES),echo "  - $(call full_name,$m)";)
	@echo ""
	@echo "Examples:"
	@echo "  make rtl-max-rect-verilog"
	@echo "  make rtl-max-rect-lib"
	@echo "  make test-rtl-max-rect"

#==============================================================================
# VERILOG GENERATION RULES
#==============================================================================

# rtl_max_rect
$(VERILOG_DIR)/rtl_max_rect.v: $(RTL_DIR)/max_rectangle_finder.py $(RTL_DIR)/validate_rectangle.py $(RTL_DIR)/checks.py
	@mkdir -p $(VERILOG_DIR)
	@echo "Generating $@..."
	cd $(ROOT) && $(PYTHON) -m rtl.max_rectangle_finder generated/verilog/rtl_max_rect.v

# impl_ascii
$(VERILOG_DIR)/impl_ascii.v: $(IMPL_DIR)/ascii_wrapper.py $(RTL_DIR)/max_rectangle_finder.py
	@mkdir -p $(VERILOG_DIR)
	@echo "Generating $@..."
	cd $(ROOT) && $(PYTHON) -m impl.ascii_wrapper generated/verilog/impl_ascii.v

# impl_uart
$(VERILOG_DIR)/impl_uart.v: $(IMPL_DIR)/uart.py
	@mkdir -p $(VERILOG_DIR)
	@echo "Generating $@..."
	cd $(ROOT) && $(PYTHON) -m impl.uart generated/verilog/impl_uart.v

# impl_uart_bridge
$(VERILOG_DIR)/impl_uart_bridge.v: $(IMPL_DIR)/uart_bridge.py $(IMPL_DIR)/uart.py $(IMPL_DIR)/ascii_wrapper.py
	@mkdir -p $(VERILOG_DIR)
	@echo "Generating $@..."
	cd $(ROOT) && $(PYTHON) -m impl.uart_bridge generated/verilog/impl_uart_bridge.v

#==============================================================================
# VERILATOR COMPILATION RULES
#==============================================================================

# Generic rule: compile Verilog to C++ with Verilator
$(OBJ_DIR)/%/Vtop.h: $(VERILOG_DIR)/%.v
	@mkdir -p $(OBJ_DIR)/$*
	@echo "Compiling $< with Verilator..."
	$(VERILATOR) $(VERILATOR_FLAGS) --Mdir $(OBJ_DIR)/$* --top-module top $<
	$(MAKE) -C $(OBJ_DIR)/$* -f Vtop.mk

#==============================================================================
# SHARED LIBRARY BUILD RULES
#==============================================================================

# Generic rule: build shared library from wrapper and Verilator output
$(LIB_DIR)/lib%.so: $(OBJ_DIR)/%/Vtop.h $(WRAPPER_DIR)/%.cpp
	@mkdir -p $(LIB_DIR)
	@echo "Building $@..."
	$(CXX) $(CXX_FLAGS) -o $@ \
		$(WRAPPER_DIR)/$*.cpp \
		$(OBJ_DIR)/$*/Vtop__ALL.cpp \
		$(VERILATOR_ROOT)/include/verilated.cpp \
		$(VERILATOR_ROOT)/include/verilated_fst_c.cpp \
		-I$(OBJ_DIR)/$* \
		-I$(VERILATOR_ROOT)/include \
		-lz

#==============================================================================
# PER-MODULE CONVENIENCE TARGETS
#==============================================================================

# RTL Max Rectangle Finder
.PHONY: rtl-max-rect-verilog rtl-max-rect-lib test-rtl-max-rect

rtl-max-rect-verilog: $(VERILOG_DIR)/rtl_max_rect.v

rtl-max-rect-lib: $(LIB_DIR)/librtl_max_rect.so

test-rtl-max-rect: $(LIB_DIR)/librtl_max_rect.so
	@echo "Running rtl_max_rect tests..."
	cd $(PYTHON_DIR) && $(PYTHON) rtl_max_rect.py

# Impl ASCII Wrapper
.PHONY: impl-ascii-verilog impl-ascii-lib test-impl-ascii

impl-ascii-verilog: $(VERILOG_DIR)/impl_ascii.v

impl-ascii-lib: $(LIB_DIR)/libimpl_ascii.so

test-impl-ascii: $(LIB_DIR)/libimpl_ascii.so
	@echo "Running impl_ascii tests..."
	cd $(PYTHON_DIR) && $(PYTHON) impl_ascii.py

# Impl UART
.PHONY: impl-uart-verilog impl-uart-lib test-impl-uart

impl-uart-verilog: $(VERILOG_DIR)/impl_uart.v

impl-uart-lib: $(LIB_DIR)/libimpl_uart.so

test-impl-uart: $(LIB_DIR)/libimpl_uart.so
	@echo "Running impl_uart tests..."
	cd $(PYTHON_DIR) && $(PYTHON) impl_uart.py

# Impl UART Bridge
.PHONY: impl-uart-bridge-verilog impl-uart-bridge-lib test-impl-uart-bridge

impl-uart-bridge-verilog: $(VERILOG_DIR)/impl_uart_bridge.v

impl-uart-bridge-lib: $(LIB_DIR)/libimpl_uart_bridge.so

test-impl-uart-bridge: $(LIB_DIR)/libimpl_uart_bridge.so
	@echo "Running impl_uart_bridge tests..."
	cd $(PYTHON_DIR) && $(PYTHON) impl_uart_bridge.py
