#!/usr/bin/env python3
"""
Python ctypes wrapper for impl_uart_bridge (UartBridgeTop) Verilator module.

This module bridges the ASCII wrapper to UART, providing a complete
serial interface for the MaxRectangleFinder.

Usage:
    from impl_uart_bridge import UartBridge

    bridge = UartBridge()
    result = bridge.process_polygon("0,0\n100,0\n100,100\n0,100\n\n")
    print(f"Result: {result}")
"""

import ctypes
import os
import sys


class UartBridge:
    """Python wrapper for UartBridgeTop RTL simulation via Verilator."""

    BAUD_DIV = 234  # 27MHz @ 115200 baud

    def __init__(self, lib_path=None):
        """Initialize the Verilator module wrapper.

        Args:
            lib_path: Path to shared library. If None, uses default location.
        """
        if lib_path is None:
            lib_path = os.path.join(
                os.path.dirname(__file__),
                "../lib/libimpl_uart_bridge.so"
            )

        if not os.path.exists(lib_path):
            raise FileNotFoundError(f"Shared library not found: {lib_path}")

        self.lib = ctypes.CDLL(lib_path)
        self._setup_functions()
        self.lib.init_module()

        # TX state machine for sending bytes
        self._tx_shift_reg = 0xFFFF  # Idle high
        self._tx_bit_counter = 0
        self._tx_cycle_counter = 0
        self._tx_transmitting = False
        self._tx_queue = []

        # RX state machine for receiving bytes
        self._rx_state = 0  # 0=idle, 1=start, 2=data, 3=stop
        self._rx_bit_counter = 0
        self._rx_cycle_counter = 0
        self._rx_shift_reg = 0
        self._rx_received = []

    def _setup_functions(self):
        """Define C function signatures."""
        # Lifecycle
        self.lib.init_module.argtypes = []
        self.lib.init_module.restype = None
        self.lib.cleanup_module.argtypes = []
        self.lib.cleanup_module.restype = None

        # Waveform control
        self.lib.enable_waveform.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64]
        self.lib.enable_waveform.restype = None
        self.lib.disable_waveform.argtypes = []
        self.lib.disable_waveform.restype = None

        # Clock
        self.lib.clock_cycle.argtypes = []
        self.lib.clock_cycle.restype = None
        self.lib.clock_n.argtypes = [ctypes.c_uint32]
        self.lib.clock_n.restype = None

        # UART signals
        self.lib.set_uart_rx.argtypes = [ctypes.c_uint8]
        self.lib.set_uart_rx.restype = None
        self.lib.get_uart_tx.argtypes = []
        self.lib.get_uart_tx.restype = ctypes.c_uint8

        # Flow control
        self.lib.get_tx_ready.argtypes = []
        self.lib.get_tx_ready.restype = ctypes.c_uint8
        self.lib.get_tx_overflow.argtypes = []
        self.lib.get_tx_overflow.restype = ctypes.c_uint8
        self.lib.get_rx_valid.argtypes = []
        self.lib.get_rx_valid.restype = ctypes.c_uint8
        self.lib.get_rx_overflow.argtypes = []
        self.lib.get_rx_overflow.restype = ctypes.c_uint8

        # Status
        self.lib.get_processing.argtypes = []
        self.lib.get_processing.restype = ctypes.c_uint8
        self.lib.get_done.argtypes = []
        self.lib.get_done.restype = ctypes.c_uint8

        # Convenience
        self.lib.run_until_done.argtypes = [ctypes.c_uint64]
        self.lib.run_until_done.restype = ctypes.c_uint64

    def __del__(self):
        """Cleanup on destruction."""
        if hasattr(self, 'lib'):
            self.lib.cleanup_module()

    # =========================================================================
    # Waveform control
    # =========================================================================

    def enable_waveform(self, filename, from_cycle=0, to_cycle=None):
        """Enable waveform capture to FST file.

        Args:
            filename: Output FST filename
            from_cycle: Start capturing from this cycle (default 0)
            to_cycle: Stop capturing at this cycle (default: unlimited)
        """
        if to_cycle is None:
            to_cycle = 0xFFFFFFFFFFFFFFFF  # UINT64_MAX
        self.lib.enable_waveform(filename.encode(), from_cycle, to_cycle)

    def disable_waveform(self):
        """Disable waveform capture and close the file."""
        self.lib.disable_waveform()

    # =========================================================================
    # UART TX State Machine (Testbench -> DUT)
    # =========================================================================

    def _tx_enqueue(self, byte):
        """Queue a byte for transmission."""
        self._tx_queue.append(byte)

    def _tx_tick(self):
        """Process one clock cycle of TX state machine.

        Returns:
            Current TX line value (0 or 1)
        """
        # Start new transmission if idle and have data
        if not self._tx_transmitting and self._tx_queue:
            byte = self._tx_queue.pop(0)
            # Build frame: [stop=1][data][start=0]
            self._tx_shift_reg = (1 << 9) | (byte << 1) | 0
            self._tx_bit_counter = 10  # 1 start + 8 data + 1 stop
            self._tx_cycle_counter = self.BAUD_DIV
            self._tx_transmitting = True

        output = 1  # Idle high

        if self._tx_transmitting:
            output = self._tx_shift_reg & 1
            self._tx_cycle_counter -= 1
            if self._tx_cycle_counter == 0:
                self._tx_shift_reg >>= 1
                self._tx_shift_reg |= (1 << 15)  # Shift in 1s
                self._tx_bit_counter -= 1
                self._tx_cycle_counter = self.BAUD_DIV
                if self._tx_bit_counter == 0:
                    self._tx_transmitting = False

        return output

    # =========================================================================
    # UART RX State Machine (DUT -> Testbench)
    # =========================================================================

    def _rx_tick(self, rx_bit):
        """Process one clock cycle of RX state machine.

        Args:
            rx_bit: Current RX line value

        Returns:
            Received byte if complete, None otherwise
        """
        result = None

        if self._rx_state == 0:  # Idle - wait for start bit
            if rx_bit == 0:
                self._rx_state = 1
                self._rx_cycle_counter = self.BAUD_DIV // 2  # Sample at midpoint

        elif self._rx_state == 1:  # Start bit verification
            self._rx_cycle_counter -= 1
            if self._rx_cycle_counter == 0:
                if rx_bit == 0:
                    self._rx_state = 2
                    self._rx_bit_counter = 0
                    self._rx_cycle_counter = self.BAUD_DIV
                    self._rx_shift_reg = 0
                else:
                    self._rx_state = 0  # False start

        elif self._rx_state == 2:  # Data bits
            self._rx_cycle_counter -= 1
            if self._rx_cycle_counter == 0:
                self._rx_shift_reg = (self._rx_shift_reg >> 1) | (rx_bit << 7)
                self._rx_bit_counter += 1
                self._rx_cycle_counter = self.BAUD_DIV
                if self._rx_bit_counter == 8:
                    self._rx_state = 3

        elif self._rx_state == 3:  # Stop bit
            self._rx_cycle_counter -= 1
            if self._rx_cycle_counter == 0:
                if rx_bit == 1:
                    result = self._rx_shift_reg
                self._rx_state = 0

        return result

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def processing(self):
        """True if module is processing."""
        return bool(self.lib.get_processing())

    @property
    def done(self):
        """True if processing is complete."""
        return bool(self.lib.get_done())

    @property
    def tx_ready(self):
        """True if TX FIFO can accept data."""
        return bool(self.lib.get_tx_ready())

    @property
    def rx_valid(self):
        """True if RX FIFO has data."""
        return bool(self.lib.get_rx_valid())

    # =========================================================================
    # High-level API
    # =========================================================================

    def process_polygon(self, input_data, max_cycles=50_000_000_000, verbose=False):
        """Process a polygon via UART and return the result.

        Args:
            input_data: String of polygon vertices (x,y per line)
            max_cycles: Maximum simulation cycles
            verbose: Print progress updates

        Returns:
            Tuple of (result_string, cycles_taken)
        """
        # Queue all input data
        for c in input_data:
            self._tx_enqueue(ord(c))
        # Add null terminator
        self._tx_enqueue(0)

        # Run simulation
        output = []
        cycles = 0
        last_progress = 0

        while cycles < max_cycles:
            # Drive RX input from TX state machine
            tx_bit = self._tx_tick()
            self.lib.set_uart_rx(tx_bit)

            # Clock the DUT
            self.lib.clock_cycle()

            # Sample TX output and process through RX state machine
            rx_bit = self.lib.get_uart_tx()
            received = self._rx_tick(rx_bit)
            if received is not None:
                c = chr(received)
                if c not in '\r\n':
                    output.append(c)

            cycles += 1

            # Check for done
            if self.done and not self._tx_transmitting and not self._tx_queue:
                # Wait for all remaining output (max 14 bytes: 13 digits + newline)
                # Each byte takes BAUD_DIV * 10 cycles, so wait BAUD_DIV * 150
                for _ in range(self.BAUD_DIV * 150):
                    self.lib.set_uart_rx(1)  # Idle
                    self.lib.clock_cycle()
                    rx_bit = self.lib.get_uart_tx()
                    received = self._rx_tick(rx_bit)
                    if received is not None:
                        c = chr(received)
                        if c not in '\r\n':
                            output.append(c)
                    cycles += 1
                break

            # Progress update
            if verbose and cycles - last_progress >= 10_000_000:
                print(f"Cycle {cycles // 1_000_000}M, TX pending: {len(self._tx_queue)}, "
                      f"output len: {len(output)}", file=sys.stderr)
                last_progress = cycles

        return ''.join(output), cycles


# =============================================================================
# Test
# =============================================================================

def main():
    """Run test with optional input file."""
    import time
    import argparse

    parser = argparse.ArgumentParser(description='UartBridgeTop Verilator test')
    parser.add_argument('input_file', nargs='?', help='Input file with polygon vertices')
    parser.add_argument('--waveform', '-w', metavar='FILE', help='Output FST waveform file')
    parser.add_argument('--waveform-from-cycle', type=int, default=0,
                        help='Start waveform capture at this cycle (default: 0)')
    parser.add_argument('--waveform-to-cycle', type=int, default=None,
                        help='Stop waveform capture at this cycle (default: unlimited)')
    args = parser.parse_args()

    # Get input file or use default test
    if args.input_file:
        input_filepath = args.input_file
    else:
        # Use default test case
        input_filepath = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "testcase", "default_input.txt"
        )

    print(f"Loading input from: {input_filepath}", file=sys.stderr)
    with open(input_filepath, 'r') as f:
        input_data = f.read()

    print(f"Input bytes: {len(input_data)}", file=sys.stderr)

    # Create bridge and run
    bridge = UartBridge()

    # Enable waveform if requested
    if args.waveform:
        print(f"Waveform output: {args.waveform}", file=sys.stderr)
        if args.waveform_from_cycle or args.waveform_to_cycle:
            print(f"  Cycle range: {args.waveform_from_cycle} - "
                  f"{args.waveform_to_cycle if args.waveform_to_cycle else 'end'}", file=sys.stderr)
        bridge.enable_waveform(args.waveform, args.waveform_from_cycle, args.waveform_to_cycle)

    start_time = time.time()
    result, cycles = bridge.process_polygon(input_data, verbose=True)
    elapsed = time.time() - start_time

    # Print results
    print(f"\nResults:", file=sys.stderr)
    print(f"  Done: {bridge.done}", file=sys.stderr)
    print(f"  Result: {result}", file=sys.stderr)
    print(f"  Cycles: {cycles}", file=sys.stderr)
    print(f"  Time: {elapsed:.3f}s", file=sys.stderr)
    if elapsed > 0:
        print(f"  Rate: {cycles / elapsed / 1e6:.2f}M cycles/sec", file=sys.stderr)

    # Output just the result for scripting
    print(result)

    return 0 if bridge.done else 1


if __name__ == "__main__":
    sys.exit(main())
