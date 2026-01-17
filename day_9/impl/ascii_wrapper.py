#!/usr/bin/env python3
"""
ASCII Streaming Wrapper for MaxRectangleFinder.

Receives ASCII character stream (x,y per line),
parses coordinates, and streams to MaxRectangleFinder.
Outputs result as ASCII string.
"""

import sys
import os

# Add project root to sys.path for imports
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
sys.path.insert(0, os.path.join(_project_root, 'rtl'))
sys.path.insert(0, os.path.join(_project_root, 'impl'))

from amaranth import *
from amaranth.lib import fifo

# Import the real MaxRectangleFinder, or use stub for testing
USE_STUB = os.environ.get('ASCII_WRAPPER_USE_STUB', '0') == '1'

if USE_STUB:
    # Use stub for testing
    class MaxRectangleFinder(Elaboratable):
        """Stub for MaxRectangleFinder when main module not available."""

        def __init__(self, coord_width=20, max_vertices=1024):
            self.coord_width = coord_width
            self.max_vertices = max_vertices
            self.area_width = 2 * coord_width

            # Control
            self.clk = ClockSignal()
            self.rst = ResetSignal()
            self.start_search = Signal()

            # Vertex input (streaming)
            self.vertex_x = Signal(coord_width)
            self.vertex_y = Signal(coord_width)
            self.vertex_valid = Signal()
            self.vertex_last = Signal()

            # Status
            self.busy = Signal()
            self.done = Signal()

            # Output interface
            self.valid = Signal()
            self.max_area = Signal(self.area_width)

            # Debug outputs
            self.rectangles_tested = Signal(64)
            self.rectangles_pruned = Signal(64)
            self.vertices_loaded = Signal(32)
            self.validation_cycles = Signal(32)
            self.debug_state = Signal(4)
            self.debug_num_vertices = Signal(32)
            self.debug_rect_count = Signal(64)
            self.debug_max_area = Signal(self.area_width)

        def elaborate(self, platform):
            m = Module()

            # Stub: Simulates processing with a counter
            cycle_count = Signal(16)
            done_delay = Signal(16, reset=100)

            with m.If(self.start_search):
                m.d.sync += cycle_count.eq(1)
            with m.Else():
                with m.If(cycle_count != 0):
                    m.d.sync += cycle_count.eq(cycle_count + 1)

            m.d.comb += [
                self.busy.eq(cycle_count != 0),
                self.done.eq(cycle_count == done_delay),
                self.valid.eq(cycle_count == done_delay),
                self.max_area.eq(1562459680 * 16),  # Scaled value (wrapper divides by 16)
            ]

            return m
else:
    # Use real MaxRectangleFinder
    from max_rectangle_finder import MaxRectangleFinder


class MaxRectangleAsciiWrapper(Elaboratable):
    """
    ASCII streaming wrapper for MaxRectangleFinder.

    Input:  ASCII stream "x,y\\nx,y\\n..."
    Output: ASCII string of max_area result

    Flow control: valid/ready handshaking
    """

    def __init__(self, coord_width=20, max_vertices=1024):
        """
        Parameters:
            coord_width: Width of vertex coordinates (default 20 bits)
            max_vertices: Maximum number of vertices
        """
        # Parameters
        self.coord_width = coord_width
        self.max_vertices = max_vertices
        self.area_width = 2 * coord_width

        # Scale factor for coordinates (multiply by 4)
        self.SCALE_SHIFT = 2  # 2^2 = 4

        # =========================================================================
        # Clock and Reset
        # =========================================================================
        self.clk = ClockSignal()
        self.rst = ResetSignal()

        # =========================================================================
        # ASCII Input Interface
        # =========================================================================
        self.ascii_in = Signal(8)          # Input ASCII character
        self.ascii_in_valid = Signal()     # Data valid
        self.ascii_in_ready = Signal()     # Ready for data

        # =========================================================================
        # ASCII Output Interface
        # =========================================================================
        self.ascii_out = Signal(8)         # Output ASCII character
        self.ascii_out_valid = Signal()    # Data valid
        self.ascii_out_ready = Signal()    # Ready for data

        # =========================================================================
        # Status Outputs
        # =========================================================================
        self.processing = Signal()         # Currently processing
        self.done = Signal()               # Computation complete

        # Debug outputs
        self.debug_state = Signal(4)       # Current state
        self.debug_idle_count = Signal(8)  # Idle counter

    def elaborate(self, platform):
        m = Module()

        # =========================================================================
        # Instantiate MaxRectangleFinder
        # =========================================================================
        finder = MaxRectangleFinder(coord_width=self.coord_width,
                                   max_vertices=self.max_vertices)
        m.submodules.finder = finder

        # =========================================================================
        # State Machine
        # =========================================================================
        IDLE = 0
        PARSE_X = 1
        PARSE_Y = 2
        SEND_VERTEX = 3
        START_SEARCH = 4       # Wait for input to end, send vertex with last=1
        WAIT_COMPLETE = 5      # Wait one cycle for vertex_last to be processed
        ASSERT_START = 6       # Assert start_search signal
        WAIT_RESULT = 7
        BCD_CONVERT = 8        # OPTIMIZATION #11: Double Dabble BCD conversion
        SEND_RESULT = 9
        DONE_STATE = 10

        state = Signal(4, reset=IDLE)  # Need 4 bits for 11 states

        # =========================================================================
        # Parser State
        # =========================================================================
        # Accumulators for parsed coordinates
        accum_x = Signal(self.coord_width)
        accum_y = Signal(self.coord_width)

        # Vertex counter
        vertex_count = Signal(16)

        # Debug counter (kept for debugging visibility)
        idle_count = Signal(16)

        # =========================================================================
        # Output Conversion State (OPTIMIZATION #11: Double Dabble Algorithm)
        # =========================================================================
        # Buffer for result digits (max 13 digits for 40-bit number)
        result_buffer = Array([Signal(8) for _ in range(16)])
        result_len = Signal(6)      # Number of digits
        result_idx = Signal(6)      # Current output index

        # Binary value to convert (40 bits for area)
        binary_value = Signal(self.area_width)

        # BCD digits (13 digits for 40-bit number, max 999999999999)
        # bcd_digits[0] = LSB, bcd_digits[12] = MSB
        bcd_digits = Array([Signal(4, name=f"bcd_{i}") for i in range(13)])

        # Carry bits for shift step (one for each BCD digit boundary)
        # carry[0] = incoming bit from binary_value MSB
        # carry[i] = carry from bcd_digits[i-1] to bcd_digits[i]
        carry_bits = Array([Signal(name=f"carry_{i}") for i in range(13)])

        # Dabbled values (after adding 3 if >= 5)
        dabbled_values = Array([Signal(4, name=f"dabbled_{i}") for i in range(13)])

        # Shift counter (7 bits for 0-63)
        shift_count = Signal(7)

        # All zero detection
        all_zero = Signal()

        # =========================================================================
        # Default assignments
        # =========================================================================
        m.d.comb += [
            self.processing.eq((state != IDLE) & (state != DONE_STATE)),
            self.done.eq(state == DONE_STATE),
            self.debug_state.eq(state),
            self.debug_idle_count.eq(idle_count),
            finder.vertex_last.eq(0),
            finder.start_search.eq(0),
        ]

        # =========================================================================
        # ASCII Parser Logic
        # =========================================================================
        # ASCII character classifications
        is_digit = Signal()
        is_comma = Signal()
        is_newline = Signal()
        is_carriage_return = Signal()
        is_null = Signal()  # Null character (0x00) signals end-of-polygon

        m.d.comb += [
            is_digit.eq((self.ascii_in >= ord('0')) & (self.ascii_in <= ord('9'))),
            is_comma.eq(self.ascii_in == ord(',')),
            is_newline.eq(self.ascii_in == ord('\n')),
            is_carriage_return.eq(self.ascii_in == ord('\r')),
            is_null.eq(self.ascii_in == 0),
        ]

        # =========================================================================
        # Vertex output to MaxRectangleFinder
        # =========================================================================
        # Apply scaling (multiply by 4)
        scaled_x = Signal(self.coord_width)
        scaled_y = Signal(self.coord_width)

        m.d.comb += [
            scaled_x.eq(accum_x << self.SCALE_SHIFT),
            scaled_y.eq(accum_y << self.SCALE_SHIFT),
        ]

        # =========================================================================
        # Backpressure: ready when parsing or in START_SEARCH (to accept more vertices)
        # =========================================================================
        m.d.comb += self.ascii_in_ready.eq(
            (state == PARSE_X) | (state == PARSE_Y) | (state == IDLE) | (state == START_SEARCH)
        )

        # =========================================================================
        # State Machine
        # =========================================================================

        with m.Switch(state):
            # =====================================================================
            # IDLE: Wait for first digit (skip leading empty lines)
            # =====================================================================
            with m.Case(IDLE):
                m.d.sync += [
                    vertex_count.eq(0),
                    idle_count.eq(0),
                ]
                with m.If(self.ascii_in_valid):
                    with m.If(is_digit):
                        m.d.sync += [
                            accum_x.eq(self.ascii_in - ord('0')),
                            state.eq(PARSE_X),
                        ]
                    # Skip newlines and carriage returns at start
                    with m.Elif(is_newline | is_carriage_return):
                        pass  # Stay in IDLE

            # =====================================================================
            # PARSE_X: Accumulate X coordinate
            # =====================================================================
            with m.Case(PARSE_X):
                with m.If(self.ascii_in_valid):
                    with m.If(is_digit):
                        # accum_x = accum_x * 10 + digit
                        m.d.sync += accum_x.eq(accum_x * 10 + (self.ascii_in - ord('0')))
                    with m.Elif(is_comma):
                        m.d.sync += [
                            accum_y.eq(0),
                            state.eq(PARSE_Y),
                        ]

            # =====================================================================
            # PARSE_Y: Accumulate Y coordinate
            # =====================================================================
            with m.Case(PARSE_Y):
                with m.If(self.ascii_in_valid):
                    with m.If(is_digit):
                        # accum_y = accum_y * 10 + digit
                        m.d.sync += accum_y.eq(accum_y * 10 + (self.ascii_in - ord('0')))
                    with m.Elif(is_carriage_return):
                        # Ignore CR, wait for LF
                        pass
                    with m.Elif(is_newline):
                        # Vertex complete, prepare to send
                        m.d.sync += [
                            vertex_count.eq(vertex_count + 1),
                            state.eq(SEND_VERTEX),
                            idle_count.eq(0),  # Reset idle counter
                        ]

            # =====================================================================
            # SEND_VERTEX: Send vertex to MaxRectangleFinder
            # =====================================================================
            with m.Case(SEND_VERTEX):
                m.d.comb += [
                    finder.vertex_x.eq(scaled_x),
                    finder.vertex_y.eq(scaled_y),
                    finder.vertex_valid.eq(1),
                ]
                # Always go to START_SEARCH to decide what to do next
                m.d.sync += state.eq(START_SEARCH)

            # =====================================================================
            # START_SEARCH: Wait for next vertex or end-of-polygon signal
            # End-of-polygon signaled by:
            #   - Empty line (newline without preceding digits)
            #   - Null character (byte 0)
            # =====================================================================
            with m.Case(START_SEARCH):
                m.d.comb += finder.vertex_valid.eq(0)

                # Debug counter
                m.d.sync += idle_count.eq(idle_count + 1)

                # If we get a digit, more vertices coming - go back to parsing
                with m.If(self.ascii_in_valid & is_digit):
                    m.d.comb += [
                        finder.vertex_x.eq(scaled_x),
                        finder.vertex_y.eq(scaled_y),
                        finder.vertex_valid.eq(1),
                    ]
                    m.d.sync += [
                        accum_x.eq(self.ascii_in - ord('0')),
                        state.eq(PARSE_X),
                        idle_count.eq(0),
                    ]
                # If we get a newline (empty line) or null char, end of polygon - send last vertex
                with m.Elif(self.ascii_in_valid & (is_newline | is_null)):
                    m.d.comb += [
                        finder.vertex_x.eq(scaled_x),
                        finder.vertex_y.eq(scaled_y),
                        finder.vertex_valid.eq(1),
                        finder.vertex_last.eq(1),
                    ]
                    m.d.sync += state.eq(WAIT_COMPLETE)
                # Ignore carriage return (for \r\n line endings)
                with m.Elif(self.ascii_in_valid & is_carriage_return):
                    pass  # Stay in START_SEARCH, wait for \n

            # =====================================================================
            # WAIT_COMPLETE: Wait one cycle for vertex_last to be processed
            # =====================================================================
            with m.Case(WAIT_COMPLETE):
                # Just wait one cycle, don't drive any signals
                m.d.sync += state.eq(ASSERT_START)

            # =====================================================================
            # ASSERT_START: Assert start_search signal
            # =====================================================================
            with m.Case(ASSERT_START):
                m.d.comb += finder.start_search.eq(1)
                m.d.sync += state.eq(WAIT_RESULT)

            # =====================================================================
            # WAIT_RESULT: Wait for MaxRectangleFinder to finish
            # =====================================================================
            with m.Case(WAIT_RESULT):
                with m.If(finder.done):
                    # Initialize BCD conversion
                    # Divide by 16 (4*4 for x and y scaling) to get original area
                    m.d.sync += [
                        binary_value.eq(finder.max_area >> 4),  # Divide by 16
                        shift_count.eq(0),
                        result_len.eq(0),
                        result_idx.eq(0),
                    ]
                    # Initialize all BCD digits to 0
                    for i in range(13):
                        m.d.sync += bcd_digits[i].eq(0)
                    m.d.sync += state.eq(BCD_CONVERT)

            # =====================================================================
            # BCD_CONVERT: Double Dabble Algorithm (OPTIMIZATION #11)
            # =====================================================================
            # Converts binary to BCD using only shifts and additions.
            # This eliminates the slow 40-bit division/modulo from the critical path.
            with m.Case(BCD_CONVERT):
                # We need 40 iterations (one per bit of the 40-bit binary value)
                with m.If(shift_count < 40):
                    # ============ DABBLE STEP ============
                    # If any BCD digit is >= 5, add 3 to it
                    for i in range(13):
                        with m.If(bcd_digits[i] >= 5):
                            m.d.comb += dabbled_values[i].eq(bcd_digits[i] + 3)
                        with m.Else():
                            m.d.comb += dabbled_values[i].eq(bcd_digits[i])

                    # ============ COMPUTE CARRY BITS ============
                    # carry[0] is the MSB of binary_value
                    m.d.comb += carry_bits[0].eq(binary_value.bit_select(39, 1))

                    # carry[i] is the MSB of dabbled_values[i-1]
                    for i in range(1, 13):
                        m.d.comb += carry_bits[i].eq(dabbled_values[i-1].bit_select(3, 1))

                    # ============ SHIFT AND REGISTER UPDATE ============
                    # Shift each BCD digit left by 1, bringing in the carry
                    for i in range(13):
                        m.d.sync += bcd_digits[i].eq((dabbled_values[i] << 1) | carry_bits[i])

                    # Shift binary_value left by 1
                    m.d.sync += binary_value.eq(binary_value << 1)
                    m.d.sync += shift_count.eq(shift_count + 1)

                with m.Else():
                    # ============ CONVERSION COMPLETE ============
                    # Convert BCD digits to ASCII and store in result_buffer
                    # Check if value is zero (all BCD digits are 0)
                    m.d.comb += all_zero.eq(1)
                    for i in range(13):
                        with m.If(bcd_digits[i] != 0):
                            m.d.comb += all_zero.eq(0)

                    with m.If(all_zero):
                        # Special case: output "0"
                        m.d.sync += [
                            result_buffer[0].eq(ord('0')),
                            result_len.eq(1),
                        ]
                    with m.Else():
                        # Convert each BCD digit to ASCII
                        for i in range(13):
                            m.d.sync += result_buffer[i].eq(bcd_digits[i] + ord('0'))

                        # Find the length (first non-zero from MSB)
                        # In Amaranth, later assignments in a loop have higher priority
                        # So we iterate from LSB to MSB, and the highest non-zero wins
                        m.d.sync += result_len.eq(0)
                        for i in range(13):
                            with m.If(bcd_digits[i] != 0):
                                m.d.sync += result_len.eq(i + 1)

                    m.d.sync += state.eq(SEND_RESULT)

            # =====================================================================
            # SEND_RESULT: Output ASCII string
            # =====================================================================
            with m.Case(SEND_RESULT):
                with m.If(result_idx < result_len):
                    m.d.comb += [
                        self.ascii_out.eq(result_buffer[result_len - 1 - result_idx]),
                        self.ascii_out_valid.eq(1),
                    ]
                    with m.If(self.ascii_out_ready):
                        m.d.sync += result_idx.eq(result_idx + 1)
                with m.Else():
                    # Send newline after result
                    m.d.comb += [
                        self.ascii_out.eq(ord('\n')),
                        self.ascii_out_valid.eq(1),
                    ]
                    with m.If(self.ascii_out_ready):
                        m.d.sync += state.eq(DONE_STATE)

            # =====================================================================
            # DONE_STATE: Finished
            # =====================================================================
            with m.Case(DONE_STATE):
                m.d.comb += self.ascii_out_valid.eq(0)

        return m


if __name__ == "__main__":
    import sys
    from amaranth.back import verilog

    output_path = sys.argv[1] if len(sys.argv) > 1 else "ascii_wrapper.v"

    dut = MaxRectangleAsciiWrapper()
    v = verilog.convert(dut, name="top", ports=[
        dut.ascii_in, dut.ascii_in_valid, dut.ascii_in_ready,
        dut.ascii_out, dut.ascii_out_valid, dut.ascii_out_ready,
        dut.processing, dut.done,
    ])

    with open(output_path, "w") as f:
        f.write(v)
    print(f"Generated {output_path}")
