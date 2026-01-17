/**
 * C wrapper for rtl_max_rect (MaxRectangleFinder) Verilator module.
 * Exposes module signals as C functions for Python ctypes.
 */

#include "Vtop.h"
#include "verilated.h"
#include "verilated_fst_c.h"
#include <cstdint>
#include <cstring>

static Vtop* dut = nullptr;
static VerilatedContext* ctx = nullptr;
static VerilatedFstC* tfp = nullptr;
static uint64_t sim_time = 0;
static uint64_t trace_from_cycle = 0;
static uint64_t trace_to_cycle = UINT64_MAX;
static bool tracing_enabled = false;

extern "C" {

//==============================================================================
// Lifecycle
//==============================================================================

void init_module() {
    ctx = new VerilatedContext;
    dut = new Vtop(ctx);
    sim_time = 0;
    // Reset sequence
    dut->rst = 1;
    for (int i = 0; i < 5; i++) {
        dut->clk = 0; dut->eval();
        dut->clk = 1; dut->eval();
    }
    dut->rst = 0;
    // Initialize inputs
    dut->vertex_x = 0;
    dut->vertex_y = 0;
    dut->vertex_valid = 0;
    dut->vertex_last = 0;
    dut->start_search = 0;
}

void cleanup_module() {
    if (tfp) {
        tfp->close();
        delete tfp;
        tfp = nullptr;
    }
    if (dut) {
        dut->final();
        delete dut;
        dut = nullptr;
    }
    if (ctx) {
        delete ctx;
        ctx = nullptr;
    }
    tracing_enabled = false;
}

//==============================================================================
// Waveform Control
//==============================================================================

void enable_waveform(const char* filename, uint64_t from_cycle, uint64_t to_cycle) {
    if (tfp) {
        tfp->close();
        delete tfp;
    }
    tfp = new VerilatedFstC;
    ctx->traceEverOn(true);
    dut->trace(tfp, 99);  // Trace 99 levels of hierarchy
    tfp->open(filename);
    trace_from_cycle = from_cycle;
    trace_to_cycle = to_cycle;
    tracing_enabled = true;
}

void disable_waveform() {
    if (tfp) {
        tfp->close();
        delete tfp;
        tfp = nullptr;
    }
    tracing_enabled = false;
}

//==============================================================================
// Clock
//==============================================================================

void clock_cycle() {
    uint64_t cycle = sim_time / 2;

    dut->clk = 0;
    dut->eval();
    if (tracing_enabled && tfp && cycle >= trace_from_cycle && cycle <= trace_to_cycle) {
        tfp->dump(sim_time);
    }
    sim_time++;

    dut->clk = 1;
    dut->eval();
    if (tracing_enabled && tfp && cycle >= trace_from_cycle && cycle <= trace_to_cycle) {
        tfp->dump(sim_time);
    }
    sim_time++;
}

void clock_n(uint32_t n) {
    for (uint32_t i = 0; i < n; i++) {
        clock_cycle();
    }
}

uint64_t get_cycle_count() {
    return sim_time / 2;
}

//==============================================================================
// Input Signals
//==============================================================================

void set_vertex_x(uint32_t v) { dut->vertex_x = v; }
void set_vertex_y(uint32_t v) { dut->vertex_y = v; }
void set_vertex_valid(uint8_t v) { dut->vertex_valid = v; }
void set_vertex_last(uint8_t v) { dut->vertex_last = v; }
void set_start_search(uint8_t v) { dut->start_search = v; }

//==============================================================================
// Output Signals
//==============================================================================

uint8_t get_busy() { return dut->busy; }
uint8_t get_done() { return dut->done; }
uint8_t get_valid() { return dut->valid; }
uint64_t get_max_area() { return dut->max_area; }
uint32_t get_rectangles_tested() { return dut->rectangles_tested; }
uint32_t get_rectangles_pruned() { return dut->rectangles_pruned; }
uint32_t get_vertices_loaded() { return dut->vertices_loaded; }
uint32_t get_validation_cycles() { return dut->validation_cycles; }
uint8_t get_debug_state() { return dut->debug_state; }
uint32_t get_debug_num_vertices() { return dut->debug_num_vertices; }
uint32_t get_debug_rect_count() { return dut->debug_rect_count; }
uint64_t get_debug_max_area() { return dut->debug_max_area; }

//==============================================================================
// Convenience Functions
//==============================================================================

void load_vertex(uint32_t x, uint32_t y, uint8_t last) {
    dut->vertex_x = x;
    dut->vertex_y = y;
    dut->vertex_valid = 1;
    dut->vertex_last = last;
    clock_cycle();
    dut->vertex_valid = 0;
    dut->vertex_last = 0;
}

void start_search() {
    dut->start_search = 1;
    clock_cycle();
    dut->start_search = 0;
}

uint64_t run_until_done(uint64_t max_cycles) {
    uint64_t cycles = 0;
    while (!dut->done && cycles < max_cycles) {
        clock_cycle();
        cycles++;
    }
    return cycles;
}

} // extern "C"
