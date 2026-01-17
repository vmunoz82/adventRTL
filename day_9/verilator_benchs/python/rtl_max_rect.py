#!/usr/bin/env python3
"""
Python ctypes wrapper for rtl_max_rect (MaxRectangleFinder) Verilator module.

Usage:
    from rtl_max_rect import MaxRectangleFinder

    finder = MaxRectangleFinder()
    finder.load_polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    finder.start_search()
    finder.wait_done()
    print(f"Max area: {finder.max_area}")
"""

import ctypes
import os
import sys


class MaxRectangleFinder:
    """Python wrapper for MaxRectangleFinder RTL simulation via Verilator."""

    def __init__(self, lib_path=None):
        """Initialize the Verilator module wrapper.

        Args:
            lib_path: Path to shared library. If None, uses default location.
        """
        if lib_path is None:
            lib_path = os.path.join(
                os.path.dirname(__file__),
                "../lib/librtl_max_rect.so"
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
        self.lib.get_cycle_count.argtypes = []
        self.lib.get_cycle_count.restype = ctypes.c_uint64

        # Input signals
        self.lib.set_vertex_x.argtypes = [ctypes.c_uint32]
        self.lib.set_vertex_x.restype = None
        self.lib.set_vertex_y.argtypes = [ctypes.c_uint32]
        self.lib.set_vertex_y.restype = None
        self.lib.set_vertex_valid.argtypes = [ctypes.c_uint8]
        self.lib.set_vertex_valid.restype = None
        self.lib.set_vertex_last.argtypes = [ctypes.c_uint8]
        self.lib.set_vertex_last.restype = None
        self.lib.set_start_search.argtypes = [ctypes.c_uint8]
        self.lib.set_start_search.restype = None

        # Output signals
        self.lib.get_busy.argtypes = []
        self.lib.get_busy.restype = ctypes.c_uint8
        self.lib.get_done.argtypes = []
        self.lib.get_done.restype = ctypes.c_uint8
        self.lib.get_valid.argtypes = []
        self.lib.get_valid.restype = ctypes.c_uint8
        self.lib.get_max_area.argtypes = []
        self.lib.get_max_area.restype = ctypes.c_uint64
        self.lib.get_rectangles_tested.argtypes = []
        self.lib.get_rectangles_tested.restype = ctypes.c_uint32
        self.lib.get_rectangles_pruned.argtypes = []
        self.lib.get_rectangles_pruned.restype = ctypes.c_uint32
        self.lib.get_vertices_loaded.argtypes = []
        self.lib.get_vertices_loaded.restype = ctypes.c_uint32
        self.lib.get_validation_cycles.argtypes = []
        self.lib.get_validation_cycles.restype = ctypes.c_uint32
        self.lib.get_debug_state.argtypes = []
        self.lib.get_debug_state.restype = ctypes.c_uint8
        self.lib.get_debug_num_vertices.argtypes = []
        self.lib.get_debug_num_vertices.restype = ctypes.c_uint32
        self.lib.get_debug_rect_count.argtypes = []
        self.lib.get_debug_rect_count.restype = ctypes.c_uint32
        self.lib.get_debug_max_area.argtypes = []
        self.lib.get_debug_max_area.restype = ctypes.c_uint64

        # Convenience functions
        self.lib.load_vertex.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint8]
        self.lib.load_vertex.restype = None
        self.lib.start_search.argtypes = []
        self.lib.start_search.restype = None
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

    @property
    def cycle_count(self):
        """Current simulation cycle count."""
        return self.lib.get_cycle_count()

    # =========================================================================
    # Vertex loading
    # =========================================================================

    def load_vertex(self, x, y, last=False):
        """Load a single vertex."""
        self.lib.load_vertex(x, y, 1 if last else 0)

    def load_polygon(self, vertices):
        """Load a complete polygon.

        Args:
            vertices: List of (x, y) tuples
        """
        for i, (x, y) in enumerate(vertices):
            is_last = (i == len(vertices) - 1)
            self.load_vertex(x, y, last=is_last)

    # =========================================================================
    # Search control
    # =========================================================================

    def start_search(self):
        """Start the rectangle search."""
        self.lib.start_search()

    def wait_done(self, max_cycles=10_000_000_000):
        """Wait for search to complete.

        Args:
            max_cycles: Maximum cycles to wait (default 10B)

        Returns:
            Number of cycles taken
        """
        return self.lib.run_until_done(max_cycles)

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def busy(self):
        """True if module is busy."""
        return bool(self.lib.get_busy())

    @property
    def done(self):
        """True if search is complete."""
        return bool(self.lib.get_done())

    @property
    def valid(self):
        """True if a valid rectangle was found."""
        return bool(self.lib.get_valid())

    @property
    def max_area(self):
        """Maximum rectangle area found."""
        return self.lib.get_max_area()

    @property
    def rectangles_tested(self):
        """Number of rectangles tested."""
        return self.lib.get_rectangles_tested()

    @property
    def rectangles_pruned(self):
        """Number of rectangles pruned."""
        return self.lib.get_rectangles_pruned()

    @property
    def vertices_loaded(self):
        """Number of vertices loaded."""
        return self.lib.get_vertices_loaded()

    @property
    def validation_cycles(self):
        """Total cycles spent in validation."""
        return self.lib.get_validation_cycles()


# =============================================================================
# Test
# =============================================================================

def load_polygon_from_file(filepath):
    """Load polygon vertices from file."""
    vertices = []
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                break  # Empty line ends polygon
            parts = line.split(',')
            if len(parts) >= 2:
                x, y = int(parts[0]), int(parts[1])
                vertices.append((x, y))
    return vertices


def main():
    """Run test with optional input file."""
    import time
    import argparse

    parser = argparse.ArgumentParser(description='MaxRectangleFinder Verilator test')
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

    print(f"Loading polygon from: {input_filepath}", file=sys.stderr)
    vertices = load_polygon_from_file(input_filepath)

    print(f"Vertices loaded: {len(vertices)}", file=sys.stderr)

    # Create finder and run
    finder = MaxRectangleFinder()

    # Enable waveform if requested
    if args.waveform:
        print(f"Waveform output: {args.waveform}", file=sys.stderr)
        if args.waveform_from_cycle or args.waveform_to_cycle:
            print(f"  Cycle range: {args.waveform_from_cycle} - "
                  f"{args.waveform_to_cycle if args.waveform_to_cycle else 'end'}", file=sys.stderr)
        finder.enable_waveform(args.waveform, args.waveform_from_cycle, args.waveform_to_cycle)

    start_time = time.time()

    # Load polygon
    finder.load_polygon(vertices)
    print(f"Polygon loaded, vertices_loaded={finder.vertices_loaded}", file=sys.stderr)

    # Run search
    finder.start_search()
    cycles = finder.wait_done()

    elapsed = time.time() - start_time

    # Print results
    print(f"\nResults:", file=sys.stderr)
    print(f"  Done: {finder.done}", file=sys.stderr)
    print(f"  Valid: {finder.valid}", file=sys.stderr)
    print(f"  Max area: {finder.max_area}", file=sys.stderr)
    print(f"  Rectangles tested: {finder.rectangles_tested}", file=sys.stderr)
    print(f"  Rectangles pruned: {finder.rectangles_pruned}", file=sys.stderr)
    print(f"  Cycles: {cycles}", file=sys.stderr)
    print(f"  Time: {elapsed:.3f}s", file=sys.stderr)
    if elapsed > 0:
        print(f"  Rate: {cycles / elapsed / 1e6:.2f}M cycles/sec", file=sys.stderr)

    # Output just the area for scripting
    print(finder.max_area)

    return 0 if finder.done else 1


if __name__ == "__main__":
    sys.exit(main())
