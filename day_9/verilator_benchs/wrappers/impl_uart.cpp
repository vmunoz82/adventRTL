/**
 * C wrapper for impl_uart (UART Loopback) Verilator module.
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
    dut->tx_enable = 0;
    dut->data = 0;
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
// TX Signals (Testbench -> DUT)
//==============================================================================

void set_tx_enable(uint8_t v) { dut->tx_enable = v; }
void set_data(uint8_t v) { dut->data = v; }
uint8_t get_busy() { return dut->busy; }
uint8_t get_tx() { return dut->tx; }

//==============================================================================
// RX Signals (DUT -> Testbench)
//==============================================================================

// Note: set_rx removed - rx is internally connected in LoopbackDevice
uint8_t get_rx_busy() { return dut->busy__0241; }  // RX busy signal
uint8_t get_rx_data() { return dut->data__0242; }  // RX data output
uint8_t get_valid() { return dut->valid; }
uint8_t get_frame_error() { return dut->frame_error; }
// get_parity_ok removed - not available when parity is disabled
uint8_t get_break_detected() { return dut->break_detected; }

//==============================================================================
// Convenience Functions
//==============================================================================

// Send a byte via TX (blocking)
// Returns cycles taken
uint32_t send_byte(uint8_t byte) {
    dut->data = byte;
    dut->tx_enable = 1;
    clock_cycle();
    dut->tx_enable = 0;

    uint32_t cycles = 1;
    while (dut->busy) {
        clock_cycle();
        cycles++;
    }
    return cycles;
}

// Wait for RX valid and return received byte
// Returns byte in lower 8 bits, bit 8 set if valid, 0 if timeout
uint16_t receive_byte(uint32_t max_cycles) {
    for (uint32_t i = 0; i < max_cycles; i++) {
        if (dut->valid) {
            return dut->data__0242 | 0x100;
        }
        clock_cycle();
    }
    return 0;
}

} // extern "C"
