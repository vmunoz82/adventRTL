#!/usr/bin/env python3
"""
Python ctypes wrapper for impl_ascii (MaxRectangleAsciiWrapper) Verilator module.

Usage:
    from impl_ascii import AsciiWrapper

    wrapper = AsciiWrapper()
    result = wrapper.process_polygon("0,0\n100,0\n100,100\n0,100\n\n")
    print(f"Result: {result}")
"""

import ctypes
import os
import sys


class AsciiWrapper:
    """Python wrapper for MaxRectangleAsciiWrapper RTL simulation via Verilator."""

    def __init__(self, lib_path=None):
        """Initialize the Verilator module wrapper.

        Args:
            lib_path: Path to shared library. If None, uses default location.
        """
        if lib_path is None:
            lib_path = os.path.join(
                os.path.dirname(__file__),
                "../lib/libimpl_ascii.so"
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

        # Input signals
        self.lib.set_ascii_in.argtypes = [ctypes.c_uint8]
        self.lib.set_ascii_in.restype = None
        self.lib.set_ascii_in_valid.argtypes = [ctypes.c_uint8]
        self.lib.set_ascii_in_valid.restype = None
        self.lib.set_ascii_out_ready.argtypes = [ctypes.c_uint8]
        self.lib.set_ascii_out_ready.restype = None

        # Output signals
        self.lib.get_ascii_in_ready.argtypes = []
        self.lib.get_ascii_in_ready.restype = ctypes.c_uint8
        self.lib.get_ascii_out.argtypes = []
        self.lib.get_ascii_out.restype = ctypes.c_uint8
        self.lib.get_ascii_out_valid.argtypes = []
        self.lib.get_ascii_out_valid.restype = ctypes.c_uint8
        self.lib.get_processing.argtypes = []
        self.lib.get_processing.restype = ctypes.c_uint8
        self.lib.get_done.argtypes = []
        self.lib.get_done.restype = ctypes.c_uint8

        # Convenience functions
        self.lib.send_char.argtypes = [ctypes.c_uint8, ctypes.c_uint32]
        self.lib.send_char.restype = ctypes.c_uint8
        self.lib.receive_char.argtypes = []
        self.lib.receive_char.restype = ctypes.c_uint16
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
    # Clock control
    # =========================================================================

    def clock(self, n=1):
        """Advance simulation by n clock cycles."""
        if n == 1:
            self.lib.clock_cycle()
        else:
            self.lib.clock_n(n)

    # =========================================================================
    # Input/Output
    # =========================================================================

    def send_char(self, c, max_wait=1000):
        """Send a single character with handshaking.

        Args:
            c: Character to send (int or single-char string)
            max_wait: Maximum cycles to wait for ready

        Returns:
            True if accepted, False if timeout
        """
        if isinstance(c, str):
            c = ord(c)
        return bool(self.lib.send_char(c, max_wait))

    def send_string(self, s):
        """Send a string of characters.

        Args:
            s: String to send

        Returns:
            Number of characters successfully sent
        """
        count = 0
        for c in s:
            if self.send_char(c):
                count += 1
            else:
                break
        return count

    def receive_output(self, max_cycles=1000):
        """Receive output characters.

        Args:
            max_cycles: Maximum cycles to wait

        Returns:
            String of received characters
        """
        output = []
        for _ in range(max_cycles):
            result = self.lib.receive_char()
            if result & 0x100:  # Valid flag set
                char = chr(result & 0xFF)
                if char not in '\r\n':
                    output.append(char)
            self.clock()
        return ''.join(output)

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
    def ascii_in_ready(self):
        """True if ready to accept input."""
        return bool(self.lib.get_ascii_in_ready())

    @property
    def ascii_out_valid(self):
        """True if output is valid."""
        return bool(self.lib.get_ascii_out_valid())

    # =========================================================================
    # High-level API
    # =========================================================================

    def process_polygon(self, input_data, max_cycles=50_000_000_000):
        """Process a polygon and return the result.

        Args:
            input_data: String of polygon vertices (x,y per line)
            max_cycles: Maximum simulation cycles

        Returns:
            Result string (the max area as decimal)
        """
        # Send input data
        for c in input_data:
            self.lib.set_ascii_in(ord(c))
            self.lib.set_ascii_in_valid(1)
            while not self.lib.get_ascii_in_ready():
                self.clock()
            self.clock()

        # Send null to signal end of polygon
        self.lib.set_ascii_in(0)
        self.lib.set_ascii_in_valid(1)
        while not self.lib.get_ascii_in_ready():
            self.clock()
        self.clock()
        self.lib.set_ascii_in_valid(0)

        # Wait for done and collect output
        output = []
        cycles = 0
        while not self.done and cycles < max_cycles:
            self.clock()
            if self.lib.get_ascii_out_valid():
                c = chr(self.lib.get_ascii_out())
                if c not in '\r\n':
                    output.append(c)
            cycles += 1

        return ''.join(output), cycles


# =============================================================================
# Test
# =============================================================================

def main():
    """Run test with optional input file."""
    import time
    import argparse

    parser = argparse.ArgumentParser(description='MaxRectangleAsciiWrapper Verilator test')
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

    # Create wrapper and run
    wrapper = AsciiWrapper()

    # Enable waveform if requested
    if args.waveform:
        print(f"Waveform output: {args.waveform}", file=sys.stderr)
        if args.waveform_from_cycle or args.waveform_to_cycle:
            print(f"  Cycle range: {args.waveform_from_cycle} - "
                  f"{args.waveform_to_cycle if args.waveform_to_cycle else 'end'}", file=sys.stderr)
        wrapper.enable_waveform(args.waveform, args.waveform_from_cycle, args.waveform_to_cycle)

    start_time = time.time()
    result, cycles = wrapper.process_polygon(input_data)
    elapsed = time.time() - start_time

    # Print results
    print(f"\nResults:", file=sys.stderr)
    print(f"  Done: {wrapper.done}", file=sys.stderr)
    print(f"  Result: {result}", file=sys.stderr)
    print(f"  Cycles: {cycles}", file=sys.stderr)
    print(f"  Time: {elapsed:.3f}s", file=sys.stderr)
    print(f"  Rate: {cycles / elapsed / 1e6:.2f}M cycles/sec", file=sys.stderr)

    # Output just the result for scripting
    print(result)

    return 0 if wrapper.done else 1


if __name__ == "__main__":
    sys.exit(main())
