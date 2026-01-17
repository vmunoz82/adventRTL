/**
 * C wrapper for impl_uart_bridge (UartBridgeTop) Verilator module.
 * Exposes module signals as C functions for Python ctypes.
 */

#include "Vtop.h"
#include "verilated.h"
#include "verilated_fst_c.h"
#include <cstdint>

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
    dut->uart_rx = 1;  // Idle high
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
    dut->trace(tfp, 99);
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
// UART Signals
//==============================================================================

void set_uart_rx(uint8_t v) { dut->uart_rx = v; }
uint8_t get_uart_tx() { return dut->uart_tx; }

//==============================================================================
// Flow Control Signals
//==============================================================================

uint8_t get_tx_ready() { return dut->tx_ready; }
uint8_t get_tx_overflow() { return dut->tx_overflow; }
uint8_t get_rx_valid() { return dut->rx_valid; }
uint8_t get_rx_overflow() { return dut->rx_overflow; }

//==============================================================================
// Status Signals
//==============================================================================

uint8_t get_processing() { return dut->processing; }
uint8_t get_done() { return dut->done; }

//==============================================================================
// Convenience Functions
//==============================================================================

// Run until done, returns cycles taken
uint64_t run_until_done(uint64_t max_cycles) {
    uint64_t cycles = 0;
    while (!dut->done && cycles < max_cycles) {
        clock_cycle();
        cycles++;
    }
    return cycles;
}

} // extern "C"
