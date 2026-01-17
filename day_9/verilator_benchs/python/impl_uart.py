#!/usr/bin/env python3
"""
Python ctypes wrapper for impl_uart (UART Loopback) Verilator module.

Usage:
    from impl_uart import UartLoopback

    uart = UartLoopback()
    uart.send_byte(0x55)
    received = uart.receive_byte()
"""

import ctypes
import os
import sys


class UartLoopback:
    """Python wrapper for UART Loopback RTL simulation via Verilator."""

    BAUD_DIV = 234  # 27MHz @ 115200 baud

    def __init__(self, lib_path=None):
        """Initialize the Verilator module wrapper.

        Args:
            lib_path: Path to shared library. If None, uses default location.
        """
        if lib_path is None:
            lib_path = os.path.join(
                os.path.dirname(__file__),
                "../lib/libimpl_uart.so"
            )

        if not os.path.exists(lib_path):
            raise FileNotFoundError(f"Shared library not found: {lib_path}")

        self.lib = ctypes.CDLL(lib_path)
        self._setup_functions()
        self.lib.init_module()

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

        # TX signals
        self.lib.set_tx_enable.argtypes = [ctypes.c_uint8]
        self.lib.set_tx_enable.restype = None
        self.lib.set_data.argtypes = [ctypes.c_uint8]
        self.lib.set_data.restype = None
        self.lib.get_busy.argtypes = []
        self.lib.get_busy.restype = ctypes.c_uint8
        self.lib.get_tx.argtypes = []
        self.lib.get_tx.restype = ctypes.c_uint8

        # RX signals (set_rx removed - internal loopback)
        self.lib.get_valid.argtypes = []
        self.lib.get_valid.restype = ctypes.c_uint8
        self.lib.get_frame_error.argtypes = []
        self.lib.get_frame_error.restype = ctypes.c_uint8
        # get_parity_ok removed - not available when parity is disabled
        self.lib.get_break_detected.argtypes = []
        self.lib.get_break_detected.restype = ctypes.c_uint8

        # Convenience functions
        self.lib.send_byte.argtypes = [ctypes.c_uint8]
        self.lib.send_byte.restype = ctypes.c_uint32
        self.lib.receive_byte.argtypes = [ctypes.c_uint32]
        self.lib.receive_byte.restype = ctypes.c_uint16

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
    # Clock control
    # =========================================================================

    def clock(self, n=1):
        """Advance simulation by n clock cycles."""
        if n == 1:
            self.lib.clock_cycle()
        else:
            self.lib.clock_n(n)

    # =========================================================================
    # TX API
    # =========================================================================

    def send_byte(self, byte):
        """Send a byte via TX (blocking).

        Args:
            byte: Byte to send

        Returns:
            Cycles taken
        """
        return self.lib.send_byte(byte)

    def send_bytes(self, data):
        """Send multiple bytes via TX.

        Args:
            data: Bytes to send

        Returns:
            Total cycles taken
        """
        total_cycles = 0
        for b in data:
            total_cycles += self.send_byte(b)
        return total_cycles

    # =========================================================================
    # RX API
    # =========================================================================

    def receive_byte(self, max_cycles=None):
        """Receive a byte via RX.

        Args:
            max_cycles: Maximum cycles to wait (default: BAUD_DIV * 15)

        Returns:
            Received byte, or None if timeout
        """
        if max_cycles is None:
            max_cycles = self.BAUD_DIV * 15

        result = self.lib.receive_byte(max_cycles)
        if result & 0x100:
            return result & 0xFF
        return None

    def receive_bytes(self, count, max_cycles_per_byte=None):
        """Receive multiple bytes via RX.

        Args:
            count: Number of bytes to receive
            max_cycles_per_byte: Max cycles per byte

        Returns:
            List of received bytes (may be shorter than count on timeout)
        """
        data = []
        for _ in range(count):
            b = self.receive_byte(max_cycles_per_byte)
            if b is None:
                break
            data.append(b)
        return data

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def busy(self):
        """True if TX is busy."""
        return bool(self.lib.get_busy())

    @property
    def valid(self):
        """True if RX has valid data."""
        return bool(self.lib.get_valid())

    @property
    def frame_error(self):
        """True if RX frame error detected."""
        return bool(self.lib.get_frame_error())

    # parity_ok property removed - not available when parity is disabled

    @property
    def break_detected(self):
        """True if RX break detected."""
        return bool(self.lib.get_break_detected())


# =============================================================================
# Test
# =============================================================================

def main():
    """Run loopback test."""
    import time
    import argparse

    parser = argparse.ArgumentParser(description='UART Loopback Verilator test')
    parser.add_argument('input_file', nargs='?', help='Input file with test data')
    parser.add_argument('--waveform', '-w', metavar='FILE', help='Output FST waveform file')
    parser.add_argument('--waveform-from-cycle', type=int, default=0,
                        help='Start waveform capture at this cycle (default: 0)')
    parser.add_argument('--waveform-to-cycle', type=int, default=None,
                        help='Stop waveform capture at this cycle (default: unlimited)')
    args = parser.parse_args()

    print("UART Loopback Test", file=sys.stderr)

    # Create UART instance
    uart = UartLoopback()

    # Enable waveform if requested
    if args.waveform:
        print(f"Waveform output: {args.waveform}", file=sys.stderr)
        if args.waveform_from_cycle or args.waveform_to_cycle:
            print(f"  Cycle range: {args.waveform_from_cycle} - "
                  f"{args.waveform_to_cycle if args.waveform_to_cycle else 'end'}", file=sys.stderr)
        uart.enable_waveform(args.waveform, args.waveform_from_cycle, args.waveform_to_cycle)

    # Test data
    test_data = b"Hello, UART!"
    if args.input_file:
        with open(args.input_file, 'rb') as f:
            test_data = f.read()

    print(f"Sending {len(test_data)} bytes...", file=sys.stderr)

    start_time = time.time()

    # The loopback device should echo back each byte
    received = []
    for byte in test_data:
        cycles = uart.send_byte(byte)
        # In loopback mode, we should receive the byte back
        rx_byte = uart.receive_byte()
        if rx_byte is not None:
            received.append(rx_byte)
            sys.stdout.buffer.write(bytes([rx_byte]))
            sys.stdout.buffer.flush()

    elapsed = time.time() - start_time

    print(f"\nResults:", file=sys.stderr)
    print(f"  Sent: {len(test_data)} bytes", file=sys.stderr)
    print(f"  Received: {len(received)} bytes", file=sys.stderr)
    print(f"  Time: {elapsed:.3f}s", file=sys.stderr)

    # Verify
    if bytes(received) == test_data:
        print("  PASS: Data matches", file=sys.stderr)
        return 0
    else:
        print("  FAIL: Data mismatch", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
