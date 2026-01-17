#!/usr/bin/env python3
"""
UART Bridge for MaxRectangleAsciiWrapper.

Bridges the ASCII wrapper's 8-bit streaming interface to UART TX/RX.
Optionally adds FIFOs on both sides with configurable depth.
"""

import sys
import os

# Add project root to sys.path for imports
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
sys.path.insert(0, _script_dir)

from amaranth import *
from amaranth.lib import fifo
from uart import TX, RX, PARITY_NONE


class UartBridge(Elaboratable):
    """
    Bridge between ASCII wrapper and UART.

    Features:
    - Streaming to UART conversion
    - Optional TX/RX FIFOs (depth configurable, default 128)
    - Flow control signals for external control
    - Overflow detection for error handling
    """

    def __init__(self, baud_div, data_bits=8, parity=PARITY_NONE, stop=1,
                 tx_fifo_depth=128, rx_fifo_depth=128, use_fifos=True):
        """
        Parameters:
            baud_div: Baud rate divisor (clock_freq / baud_rate)
            data_bits: UART data bits (default 8)
            parity: UART parity (default PARITY_NONE)
            stop: UART stop bits (default 1)
            tx_fifo_depth: TX FIFO depth (default 128, 0 to disable)
            rx_fifo_depth: RX FIFO depth (default 128, 0 to disable)
            use_fifos: Enable/disable FIFOs (default True)
        """
        self.baud_div = baud_div
        self.data_bits = data_bits
        self.parity = parity
        self.stop = stop
        self.tx_fifo_depth = tx_fifo_depth if use_fifos else 0
        self.rx_fifo_depth = rx_fifo_depth if use_fifos else 0

        # =====================================================================
        # Clock and Reset
        # =====================================================================
        self.clk = ClockSignal()
        self.rst = ResetSignal()

        # =====================================================================
        # ASCII Wrapper Interface
        # =====================================================================
        # Input side (from UART to ASCII wrapper)
        self.ascii_in = Signal(8)          # Input ASCII character
        self.ascii_in_valid = Signal()     # Data valid
        self.ascii_in_ready = Signal()     # Ready for data

        # Output side (from ASCII wrapper to UART)
        self.ascii_out = Signal(8)         # Output ASCII character
        self.ascii_out_valid = Signal()    # Data valid
        self.ascii_out_ready = Signal()    # Ready for data

        # =====================================================================
        # UART Interface
        # =====================================================================
        self.uart_tx = Signal(1)           # UART TX output
        self.uart_rx = Signal(1)           # UART RX input

        # =====================================================================
        # Flow Control Signals (for external UART control)
        # =====================================================================
        # TX path: external -> UART
        self.tx_ready = Signal()           # TX FIFO can accept data
        self.tx_overflow = Signal()        # TX FIFO overflow detected (data lost)

        # RX path: UART -> external
        self.rx_valid = Signal()           # RX FIFO has data available
        self.rx_overflow = Signal()        # RX FIFO overflow detected (data lost)

    def elaborate(self, platform):
        m = Module()

        # =========================================================================
        # Instantiate UART TX and RX
        # =========================================================================
        uart_tx = TX(self.baud_div, self.data_bits, self.parity, self.stop)
        uart_rx = RX(self.baud_div, self.data_bits, self.parity, self.stop)
        m.submodules.uart_tx = uart_tx
        m.submodules.uart_rx = uart_rx

        # Connect UART signals
        m.d.comb += [
            self.uart_tx.eq(uart_tx.tx),
            uart_rx.rx.eq(self.uart_rx),
        ]

        # =========================================================================
        # TX Path: ASCII wrapper -> UART
        # =========================================================================
        if self.tx_fifo_depth > 0:
            # =====================================================================
            # TX FIFO path (with FIFO)
            # =====================================================================
            tx_fifo = fifo.SyncFIFOBuffered(width=8, depth=self.tx_fifo_depth)
            m.submodules.tx_fifo = tx_fifo

            # Connect ASCII wrapper to TX FIFO
            m.d.comb += [
                tx_fifo.w_data.eq(self.ascii_out),
                tx_fifo.w_en.eq(self.ascii_out_valid),
                self.ascii_out_ready.eq(tx_fifo.w_rdy),
                self.tx_ready.eq(tx_fifo.w_rdy),  # Flow control: ready when not full
            ]

            # Overflow detection: sticky bit set on any overflow
            overflow_pending = Signal()
            m.d.sync += [
                self.tx_overflow.eq((self.ascii_out_valid & ~tx_fifo.w_rdy) | overflow_pending)
            ]
            with m.If(self.ascii_out_valid & ~tx_fifo.w_rdy):
                m.d.sync += overflow_pending.eq(1)
            with m.Elif(tx_fifo.w_rdy):
                m.d.sync += overflow_pending.eq(0)

            # Connect TX FIFO to UART TX
            can_transmit = Signal()
            m.d.comb += can_transmit.eq(tx_fifo.r_rdy & ~uart_tx.busy)

            with m.FSM():
                with m.State("IDLE"):
                    with m.If(can_transmit):
                        m.d.comb += [
                            uart_tx.data.eq(tx_fifo.r_data),
                            uart_tx.tx_enable.eq(1),
                            tx_fifo.r_en.eq(1),
                        ]
                        m.next = "TRANSMIT"
                    with m.Else():
                        m.d.comb += uart_tx.tx_enable.eq(0)

                with m.State("TRANSMIT"):
                    m.d.comb += uart_tx.tx_enable.eq(0)
                    with m.If(~can_transmit):
                        m.next = "IDLE"

        else:
            # =====================================================================
            # TX direct path (no FIFO)
            # =====================================================================
            with m.FSM():
                with m.State("IDLE"):
                    with m.If(self.ascii_out_valid & ~uart_tx.busy):
                        m.d.comb += [
                            uart_tx.data.eq(self.ascii_out),
                            uart_tx.tx_enable.eq(1),
                            self.ascii_out_ready.eq(1),
                            self.tx_ready.eq(~uart_tx.busy),  # Ready when not busy
                        ]
                        m.next = "TRANSMIT"
                    with m.Else():
                        m.d.comb += [
                            uart_tx.tx_enable.eq(0),
                            self.ascii_out_ready.eq(0),
                            self.tx_ready.eq(~uart_tx.busy),
                        ]

                with m.State("TRANSMIT"):
                    m.d.comb += [
                        uart_tx.tx_enable.eq(0),
                        self.ascii_out_ready.eq(0),
                        self.tx_ready.eq(0),  # Not ready while transmitting
                    ]
                    with m.If(~uart_tx.busy):
                        m.next = "IDLE"

            # No overflow detection for direct path
            m.d.comb += self.tx_overflow.eq(0)

        # =========================================================================
        # RX Path: UART -> ASCII wrapper
        # =========================================================================
        if self.rx_fifo_depth > 0:
            # =====================================================================
            # RX FIFO path (with FIFO)
            # =====================================================================
            rx_fifo = fifo.SyncFIFOBuffered(width=8, depth=self.rx_fifo_depth)
            m.submodules.rx_fifo = rx_fifo

            # Connect UART RX to RX FIFO
            rx_state = Signal(2, reset=0)

            with m.FSM():
                with m.State("IDLE"):
                    m.d.sync += rx_state.eq(0)
                    m.d.comb += self.rx_valid.eq(rx_fifo.r_rdy)  # Data available
                    with m.If(uart_rx.valid & rx_fifo.w_rdy):
                        m.d.comb += [
                            rx_fifo.w_data.eq(uart_rx.data),
                            rx_fifo.w_en.eq(1),
                        ]
                        m.next = "RECEIVE"
                    with m.Elif(~rx_fifo.w_rdy):
                        # RX FIFO full - data will be lost, set overflow flag
                        m.d.comb += self.rx_overflow.eq(1)
                    with m.Else():
                        m.d.comb += rx_fifo.w_en.eq(0)

                with m.State("RECEIVE"):
                    m.d.sync += rx_state.eq(1)
                    m.d.comb += [
                        rx_fifo.w_en.eq(0),
                        self.rx_overflow.eq(0),
                    ]
                    m.next = "IDLE"

            # Connect RX FIFO to ASCII wrapper
            m.d.comb += [
                self.ascii_in.eq(rx_fifo.r_data),
                self.ascii_in_valid.eq(rx_fifo.r_rdy),
                rx_fifo.r_en.eq(self.ascii_in_ready),
            ]

        else:
            # =====================================================================
            # RX direct path (no FIFO)
            # =====================================================================
            data_latch = Signal(8)
            data_valid_latch = Signal()

            with m.FSM():
                with m.State("IDLE"):
                    m.d.comb += self.ascii_in_valid.eq(data_valid_latch)
                    m.d.comb += self.rx_valid.eq(data_valid_latch)  # Data available
                    with m.If(uart_rx.valid & ~data_valid_latch):
                        m.d.sync += [
                            data_latch.eq(uart_rx.data),
                            data_valid_latch.eq(1),
                        ]
                    with m.Elif(self.ascii_in_ready & data_valid_latch):
                        m.d.sync += data_valid_latch.eq(0)

            m.d.comb += [
                self.ascii_in.eq(Mux(data_valid_latch, data_latch, 0)),
                self.rx_overflow.eq(uart_rx.valid & data_valid_latch),  # Data lost
            ]

        return m


class UartBridgeTop(Elaboratable):
    """
    Top-level module combining ASCII wrapper and UART bridge.
    Provides complete UART interface with flow control for external systems.
    """

    def __init__(self, coord_width=20, max_vertices=1024,
                 baud_div=25000000 // 115200,  # Default for 25MHz clock, 115200 baud
                 data_bits=8, parity=PARITY_NONE, stop=1,
                 tx_fifo_depth=128, rx_fifo_depth=128, use_fifos=True):
        """
        Parameters:
            coord_width: Coordinate width for MaxRectangleFinder
            max_vertices: Maximum vertices for MaxRectangleFinder
            baud_div: UART baud rate divisor
            data_bits: UART data bits
            parity: UART parity
            stop: UART stop bits
            tx_fifo_depth: TX FIFO depth
            rx_fifo_depth: RX FIFO depth
            use_fifos: Enable/disable FIFOs
        """
        # Import here to avoid circular dependency
        from ascii_wrapper import MaxRectangleAsciiWrapper

        self.wrapper = MaxRectangleAsciiWrapper(coord_width, max_vertices)
        self.bridge = UartBridge(baud_div, data_bits, parity, stop,
                                 tx_fifo_depth, rx_fifo_depth, use_fifos)

        # =====================================================================
        # Clock and Reset
        # =====================================================================
        self.clk = ClockSignal()
        self.rst = ResetSignal()

        # =====================================================================
        # UART Interface
        # =====================================================================
        self.uart_tx = Signal(1)
        self.uart_rx = Signal(1)

        # =====================================================================
        # Flow Control Signals (for external control)
        # =====================================================================
        self.tx_ready = Signal()      # TX can accept data
        self.tx_overflow = Signal()   # TX overflow detected
        self.rx_valid = Signal()      # RX has data available
        self.rx_overflow = Signal()   # RX overflow detected

        # =====================================================================
        # Status Outputs
        # =====================================================================
        self.processing = Signal()
        self.done = Signal()

    def elaborate(self, platform):
        m = Module()

        m.submodules.wrapper = self.wrapper
        m.submodules.bridge = self.bridge

        # Connect ASCII wrapper to UART bridge
        m.d.comb += [
            # ASCII out -> UART TX path
            self.bridge.ascii_out.eq(self.wrapper.ascii_out),
            self.bridge.ascii_out_valid.eq(self.wrapper.ascii_out_valid),
            self.wrapper.ascii_out_ready.eq(self.bridge.ascii_out_ready),

            # UART RX -> ASCII in path
            self.wrapper.ascii_in.eq(self.bridge.ascii_in),
            self.wrapper.ascii_in_valid.eq(self.bridge.ascii_in_valid),
            self.bridge.ascii_in_ready.eq(self.wrapper.ascii_in_ready),

            # UART signals
            self.uart_tx.eq(self.bridge.uart_tx),  # bridge TX output -> top TX output
            self.bridge.uart_rx.eq(self.uart_rx),  # top RX input -> bridge RX input

            # Flow control signals
            self.tx_ready.eq(self.bridge.tx_ready),
            self.tx_overflow.eq(self.bridge.tx_overflow),
            self.rx_valid.eq(self.bridge.rx_valid),
            self.rx_overflow.eq(self.bridge.rx_overflow),

            # Status
            self.processing.eq(self.wrapper.processing),
            self.done.eq(self.wrapper.done),
        ]

        return m


if __name__ == "__main__":
    import sys
    from amaranth.back import verilog

    output_path = sys.argv[1] if len(sys.argv) > 1 else "uart_bridge.v"
    baud_div = int(sys.argv[2]) if len(sys.argv) > 2 else 234  # 27MHz @ 115200

    dut = UartBridgeTop(
        baud_div=baud_div,
        use_fifos=True,
        tx_fifo_depth=256,
        rx_fifo_depth=256
    )

    v = verilog.convert(dut, name="top", ports=[
        dut.uart_tx, dut.uart_rx,
        dut.tx_ready, dut.tx_overflow,
        dut.rx_valid, dut.rx_overflow,
        dut.processing, dut.done,
    ])

    with open(output_path, "w") as f:
        f.write(v)
    print(f"Generated {output_path}")
