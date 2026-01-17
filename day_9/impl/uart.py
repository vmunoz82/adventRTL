"""UART TX/RX implementation in Amaranth HDL."""

from amaranth import *
from amaranth.sim import *
from amaranth.asserts import *

import functools


# =============================================================================
# Parity Configuration
# =============================================================================

PARITY_NONE, PARITY_ODD, PARITY_EVEN, PARITY_MARK, PARITY_SPACE = range(5)
PARITY_LIST = (PARITY_NONE, PARITY_ODD, PARITY_EVEN, PARITY_MARK, PARITY_SPACE)


# =============================================================================
# Utility Functions
# =============================================================================

def util_parity_function(parity, data):
    """Calculate parity bit for given data."""
    return {
        PARITY_NONE: None,
        PARITY_ODD: ~functools.reduce(lambda x, y: x ^ y, data),
        PARITY_EVEN: functools.reduce(lambda x, y: x ^ y, data),
        PARITY_MARK: 1,
        PARITY_SPACE: 0
    }[parity]


def util_bitcount(data_bits, parity, stop):
    """Return total bits in one UART frame (start + data + parity + stop)."""
    return 1 + data_bits + (1 if parity != PARITY_NONE else 0) + stop


def formal_check(m, div, sample_offset, data_bits, parity, stop, uart_signal, data):
    """Formal verification: check UART bit timing and correctness."""
    bit_pos = 0

    # Check stop bits (all 1s)
    for i in range(stop):
        m.d.comb += Assert(Past(uart_signal, div * bit_pos + sample_offset) == 1)
        bit_pos += 1

    # Check parity bit if present
    if parity != PARITY_NONE:
        parity_bit = util_parity_function(parity, data)
        m.d.comb += Assert(Past(uart_signal, div * bit_pos + sample_offset) == parity_bit)
        bit_pos += 1

    # Check data bits (LSB first)
    for i in range(data_bits):
        m.d.comb += Assert(Past(uart_signal, div * bit_pos + sample_offset) == data[data_bits - i - 1])
        bit_pos += 1

    # Check start bit (0)
    m.d.comb += Assert(Past(uart_signal, div * bit_pos + sample_offset) == 0)


# =============================================================================
# UART Transmitter
# =============================================================================

class TX(Elaboratable):
    """UART Transmitter."""

    def __init__(self, div, data_bits=8, parity=PARITY_NONE, stop=1):
        self.data_bits, self.parity, self.stop = data_bits, parity, stop
        self.baud_div = int(div - 1)

        # Inputs
        self.tx_enable = Signal(1)   # Enable transmission
        self.data = Signal(data_bits)  # Data to transmit

        # Outputs
        self.busy = Signal(1)        # Transmitter busy
        self.tx = Signal(1)          # TX output

    def _add_formal_verification(self, m):
        """Add formal verification assertions."""
        print("formal TX baby")
        div_period = self.baud_div + 1
        data_snapshot = Signal(self.data_bits)
        tx_start = self.tx_enable & (~self.busy)

        with m.If(tx_start):
            m.d.sync += data_snapshot.eq(self.data)

        with m.If(~self.busy):
            m.d.comb += Assert(self.tx)
            with m.If(self._shift_reg != 1):
                m.d.comb += Assert(~self._tick)

        with m.If(self._tick):
            m.d.comb += Assert(Past(self._tick, div_period) | Past(self.tx_enable, div_period))

        with m.If((self._shift_reg == 1) & self._tick):
            bit_count = div_period * util_bitcount(self.data_bits, self.parity, self.stop)
            for i in range(bit_count):
                m.d.comb += Assume(Past(self.tx_enable, i) == 0)
                m.d.comb += Assume(Stable(self.data, i))

        formal_check(m, div_period, 0, self.data_bits, self.parity, self.stop, self.tx, data_snapshot)

    def elaborate(self, platform):
        m = Module()

        # Internal signals
        self._tick = Signal()
        self._shift_reg = Signal(util_bitcount(self.data_bits, self.parity, self.stop), reset=0)
        cycle_counter = Signal(range(self.baud_div + 1), reset=self.baud_div)

        tx_start = self.tx_enable & (~self.busy)

        # Tick when counter reaches zero
        m.d.comb += self._tick.eq(cycle_counter == 0)
        # Busy when shift register not empty or last bit with tick
        m.d.comb += self.busy.eq((self._shift_reg[1:] != 0) | (self._shift_reg[0] ^ self._tick))
        # TX output: shift bit or high when idle
        m.d.comb += self.tx.eq(self._shift_reg[0] | (~self.busy))
        # Counter: reset on tick, new data, or idle
        m.d.sync += cycle_counter.eq(Mux(self._tick | tx_start | (~self.busy), self.baud_div, cycle_counter - 1))

        # Load shift register: [stop][parity][data][start=0]
        with m.If(tx_start):
            parity = util_parity_function(self.parity, self.data)
            checksumed = Cat(self.data, parity) if self.parity != PARITY_NONE else self.data
            stop_bits = Const((1 << self.stop) - 1, unsigned(self.stop))
            m.d.sync += self._shift_reg.eq(Cat(0, checksumed, stop_bits))
        with m.Elif(self._tick):
            m.d.sync += self._shift_reg.eq(Cat(self._shift_reg[1:], 0))

        if platform == "formal":
            self._add_formal_verification(m)

        return m


# =============================================================================
# Helper: Set-Reset Latch
# =============================================================================

def logic(m, set, clear, signal):
    """Set-reset latch: signal=1 if set, 0 if clear, else holds previous value."""
    _signal = Signal()

    with m.If(set):
        m.d.sync += _signal.eq(1)
    with m.If(clear):
        m.d.sync += _signal.eq(0)

    m.d.comb += signal.eq(Mux(clear, 0, Mux(set, 1, _signal)))

    return _signal


# =============================================================================
# UART Receiver
# =============================================================================

class RX(Elaboratable):
    """UART Receiver with frame error, parity error, and break detection."""

    def __init__(self, div, data_bits=8, parity=PARITY_NONE, stop=1):
        self.data_bits, self.parity, self.stop = data_bits, parity, stop

        # Register bit offsets: [idle][stop bits][parity][data bits][start bit]
        self._off_start = 0
        self._off_data = 1
        self._off_parity = self._off_data + self.data_bits
        self._off_stop = self._off_parity + (0 if self.parity == PARITY_NONE else 1)
        self._off_end = self._off_stop + self.stop

        # Timing
        self.baud_div = int(div - 1)
        self.sample_offset = int(div / 2)  # Sample at bit midpoint

        # Input
        self.rx = Signal(1)

        # Outputs
        self.busy = Signal(1)
        self.data = Signal(data_bits)
        self.valid = Signal(1)
        self.frame_error = Signal(1)
        self.parity_ok = Signal(1)
        self.break_detected = Signal(1)
        self.sample = Signal(1)

    def _add_formal_verification(self, m):
        """Add formal verification assertions."""
        print("formal RX baby")
        with m.If(self.valid):
            formal_check(m, self.baud_div + 1, self.sample_offset, self.data_bits,
                        self.parity, self.stop, self.rx, self.data)

    def elaborate(self, platform):
        m = Module()

        # Internal signals
        initialized = Signal()
        rx_shift_reg = Signal(self._off_end + 1, reset=1 << self._off_end)
        cycle_counter = Signal(range(self.baud_div + 1), reset=self.baud_div)
        data_latch = Signal(self.data_bits)

        # Busy state management: start on falling edge, clear at end
        _unused = Signal()
        transfer_complete = (cycle_counter == 0) & rx_shift_reg[self._off_start]
        start_detected = initialized & (~self.rx) & (~self.busy)
        busy = logic(m, start_detected, transfer_complete, _unused)
        m.d.comb += self.busy.eq(busy)
        receiving = busy | start_detected

        # Counter reset
        m.d.sync += cycle_counter.eq(Mux((cycle_counter == 0) | (~receiving), self.baud_div, cycle_counter - 1))

        # Data output latching
        m.d.comb += self.data.eq(Mux(transfer_complete, rx_shift_reg[self._off_data+1:self._off_parity+1], data_latch))

        with m.If(transfer_complete):
            # Frame error: start bit not 0 OR stop bits not all 1
            m.d.comb += self.frame_error.eq(rx_shift_reg[self._off_start + 1] | (rx_shift_reg[self._off_stop+1:self._off_end+1] != ((1 << self.stop) - 1)))
            if self.parity != PARITY_NONE:
                parity = util_parity_function(self.parity, rx_shift_reg[self._off_data+1:self._off_parity+1])
                m.d.comb += self.parity_ok.eq(parity == rx_shift_reg[self._off_parity + 1])
            m.d.comb += self.valid.eq((~self.frame_error) & (self.parity_ok if self.parity != PARITY_NONE else 1))
            m.d.comb += self.break_detected.eq(rx_shift_reg[1:] == 0)

        # Sample at midpoint of bit period
        m.d.comb += self.sample.eq(receiving & (cycle_counter == self.sample_offset))

        with m.If(transfer_complete):
            m.d.sync += data_latch.eq(rx_shift_reg[self._off_data+1:self._off_parity+1])
            m.d.sync += rx_shift_reg.eq(1 << self._off_end)
        with m.Elif(self.sample):
            m.d.sync += rx_shift_reg.eq(Cat(rx_shift_reg[1:], self.rx))

        m.d.sync += initialized.eq(1)

        if platform == "formal":
            self._add_formal_verification(m)

        return m


# =============================================================================
# Test Devices
# =============================================================================

class LoopbackDevice(Elaboratable):
    """Test device that internally connects TX to RX for verification."""

    def __init__(self, div, data_bits=8, parity=PARITY_NONE, stop=1):
        self.uart_tx = TX(div, data_bits, parity, stop)
        self.uart_rx = RX(div, data_bits, parity, stop)
        self.bitcount = util_bitcount(data_bits, parity, stop)
        self.div = div

    def elaborate(self, platform):
        m = Module()

        m.submodules.uart_tx = self.uart_tx
        m.submodules.uart_rx = self.uart_rx

        m.d.comb += self.uart_rx.rx.eq(self.uart_tx.tx)

        if platform == "formal":
            print("formal LoopbackDevice baby")
            with m.If(self.uart_rx.valid):
                m.d.comb += Assert(Past(self.uart_tx.data, self.div * self.bitcount) == self.uart_rx.data)
                m.d.comb += Assert(Past(self.uart_tx.tx_enable, self.div * self.bitcount) == 1)

        return m


class EchoDevice(Elaboratable):
    """Echo received data back on UART, with LED indicators."""

    def __init__(self, div, data_bits=8, parity=PARITY_NONE, stop=1):
        self.data_bits = data_bits
        self.uart_tx = TX(div, data_bits, parity, stop)
        self.uart_rx = RX(div, data_bits, parity, stop)

    def elaborate(self, platform):
        m = Module()

        initialized = Signal()
        data_pending = Signal()
        data_reg = Signal(self.data_bits, reset=0)

        m.submodules.uart_tx = self.uart_tx
        m.submodules.uart_rx = self.uart_rx

        platform_uart = platform.request("uart", 1)

        m.d.comb += [
            platform_uart.tx.o.eq(self.uart_tx.tx),
            self.uart_rx.rx.eq(platform_uart.rx.i),
            platform.request("led", 0).o.eq(data_reg[0]),
            platform.request("led", 1).o.eq(data_reg[1])
        ]

        with m.If(initialized):
            with m.If(self.uart_rx.valid):
                m.d.sync += [data_reg.eq(self.uart_rx.data), data_pending.eq(1)]
            with m.Elif((~self.uart_tx.busy) & data_pending):
                m.d.comb += [self.uart_tx.data.eq(data_reg), self.uart_tx.tx_enable.eq(1)]
                m.d.sync += data_pending.eq(0)

        m.d.sync += initialized.eq(1)

        return m


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    import sys
    from amaranth.back import verilog

    output_path = sys.argv[1] if len(sys.argv) > 1 else "uart.v"
    baud_div = int(sys.argv[2]) if len(sys.argv) > 2 else 234  # 27MHz @ 115200

    # Generate LoopbackDevice for testing (contains both TX and RX)
    dut = LoopbackDevice(div=baud_div)
    v = verilog.convert(dut, name="top", ports=[
        dut.uart_tx.tx_enable, dut.uart_tx.data, dut.uart_tx.busy, dut.uart_tx.tx,
        dut.uart_rx.busy, dut.uart_rx.data, dut.uart_rx.valid,
        dut.uart_rx.frame_error, dut.uart_rx.break_detected,
    ])

    with open(output_path, "w") as f:
        f.write(v)
    print(f"Generated {output_path}")
