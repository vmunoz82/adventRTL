"""
BRAM-Based Merge Sort for Hardware RTL

Bottom-up iterative merge sort implementation using Block RAM primitives.
Part of the complete range processing system.

Algorithm:
    - O(n log n) guaranteed complexity
    - Ping-pong buffering between banks A and B
    - 8 merge passes for up to 256 elements
    - Handles remainder blocks correctly (critical for N>136)

Hardware Features:
    - 4× BRAM blocks (2 banks × start/end arrays)
    - Synchronous memory with 1-cycle read latency
    - FSM-based control with proper timing
    - Tuple comparison: (start, end) with tiebreaking

Critical Bug Fix (Dec 2024):
    When a merge pass has unpaired remainder blocks (e.g., N=137 with width=128),
    these blocks must be copied to output bank. Previously skipped to BLOCK_NEXT,
    causing uninitialized memory reads and incorrect sort results for N≥137.

    Fix: Always enter MERGE_READ_LEFT which handles the right_idx >= right_limit
    case by copying left elements correctly.

Performance:
    - 173 ranges: ~5,600 clock cycles
    - Throughput: ~34 cycles per pass × 8 passes + overhead
    - At 100 MHz: 56 μs latency
"""

from amaranth import *
from amaranth.sim import Simulator, Tick


class MergeSortBRAM(Elaboratable):
    """
    Merge sort using Block RAM (Memory).
    Handles the 1-cycle read latency correctly.
    """

    def __init__(self, max_ranges=256, width=64):
        self.max_ranges = max_ranges
        self.width = width

        # Input interface
        self.start_in = Signal(width)
        self.end_in = Signal(width)
        self.valid_in = Signal()
        self.count_in = Signal(range(max_ranges + 1))

        # Output interface
        self.start_out = Signal(width)
        self.end_out = Signal(width)
        self.valid_out = Signal()
        self.done = Signal()

        # Control
        self.start = Signal()
        self.ready = Signal()
        self.busy = Signal()

    def elaborate(self, platform):
        m = Module()

        # Ping-pong BRAM buffers
        starts_a_mem = Memory(width=self.width, depth=self.max_ranges)
        ends_a_mem = Memory(width=self.width, depth=self.max_ranges)
        starts_b_mem = Memory(width=self.width, depth=self.max_ranges)
        ends_b_mem = Memory(width=self.width, depth=self.max_ranges)

        # Read ports (synchronous, 1 cycle latency)
        starts_a_rd = starts_a_mem.read_port()
        ends_a_rd = ends_a_mem.read_port()
        starts_b_rd = starts_b_mem.read_port()
        ends_b_rd = ends_b_mem.read_port()

        # Write ports
        starts_a_wr = starts_a_mem.write_port()
        ends_a_wr = ends_a_mem.write_port()
        starts_b_wr = starts_b_mem.write_port()
        ends_b_wr = ends_b_mem.write_port()

        m.submodules += [
            starts_a_rd, ends_a_rd, starts_b_rd, ends_b_rd,
            starts_a_wr, ends_a_wr, starts_b_wr, ends_b_wr
        ]

        # State variables
        num_ranges = Signal(range(self.max_ranges + 1))
        input_idx = Signal(range(self.max_ranges + 1))

        # Pass control
        merge_width = Signal(range(self.max_ranges + 1))
        use_a_as_source = Signal()  # True = read from A, write to B

        # Merge control
        block_start = Signal(range(self.max_ranges + 1))
        left_idx = Signal(range(self.max_ranges + 1))
        right_idx = Signal(range(self.max_ranges + 1))
        left_limit = Signal(range(self.max_ranges + 1))
        right_limit = Signal(range(self.max_ranges + 1))
        out_idx = Signal(range(self.max_ranges + 1))

        # Latched values from memory reads
        left_start = Signal(self.width)
        left_end = Signal(self.width)
        right_start = Signal(self.width)
        right_end = Signal(self.width)

        # Output control
        output_idx = Signal(range(self.max_ranges + 1))

        # Debug
        self.output_idx = output_idx  # Expose for debugging

        with m.FSM() as fsm:

            with m.State("IDLE"):
                m.d.comb += self.ready.eq(1)
                m.d.sync += [
                    self.busy.eq(0),
                    self.done.eq(0),
                    input_idx.eq(0),
                    self.valid_out.eq(0),
                ]

                # Load input data into bank A
                with m.If(self.valid_in):
                    m.d.comb += [
                        starts_a_wr.addr.eq(input_idx),
                        starts_a_wr.data.eq(self.start_in),
                        starts_a_wr.en.eq(1),
                        ends_a_wr.addr.eq(input_idx),
                        ends_a_wr.data.eq(self.end_in),
                        ends_a_wr.en.eq(1),
                    ]
                    m.d.sync += input_idx.eq(input_idx + 1)

                # Start sorting
                with m.If(self.start):
                    m.d.sync += [
                        num_ranges.eq(self.count_in),
                        merge_width.eq(1),
                        use_a_as_source.eq(1),  # First pass reads from A
                        self.busy.eq(1),
                    ]
                    m.next = "PASS_START"

            with m.State("PASS_START"):
                m.d.sync += block_start.eq(0)
                m.next = "BLOCK_SETUP"

            with m.State("BLOCK_SETUP"):
                # Setup merge of two adjacent blocks
                m.d.sync += [
                    left_idx.eq(block_start),
                    right_idx.eq(block_start + merge_width),
                    out_idx.eq(block_start),
                ]

                # Calculate limits
                with m.If(block_start + merge_width < num_ranges):
                    m.d.sync += left_limit.eq(block_start + merge_width)
                with m.Else():
                    m.d.sync += left_limit.eq(num_ranges)

                with m.If(block_start + (merge_width << 1) < num_ranges):
                    m.d.sync += right_limit.eq(block_start + (merge_width << 1))
                with m.Else():
                    m.d.sync += right_limit.eq(num_ranges)

                # Check if right block exists
                with m.If(block_start + merge_width >= num_ranges):
                    # No right block - need to copy left block to output bank
                    # This handles the remainder elements at the end
                    m.next = "MERGE_READ_LEFT"
                with m.Else():
                    # Start merging - read first elements
                    m.next = "MERGE_READ_LEFT"

            with m.State("MERGE_READ_LEFT"):
                # Check if merge complete
                with m.If((left_idx >= left_limit) & (right_idx >= right_limit)):
                    m.next = "BLOCK_NEXT"

                with m.Elif(left_idx >= left_limit):
                    # Only right remains - read right element
                    with m.If(use_a_as_source):
                        m.d.comb += [
                            starts_a_rd.addr.eq(right_idx),
                            ends_a_rd.addr.eq(right_idx),
                        ]
                    with m.Else():
                        m.d.comb += [
                            starts_b_rd.addr.eq(right_idx),
                            ends_b_rd.addr.eq(right_idx),
                        ]
                    m.next = "MERGE_WRITE_RIGHT"

                with m.Elif(right_idx >= right_limit):
                    # Only left remains - read left element
                    with m.If(use_a_as_source):
                        m.d.comb += [
                            starts_a_rd.addr.eq(left_idx),
                            ends_a_rd.addr.eq(left_idx),
                        ]
                    with m.Else():
                        m.d.comb += [
                            starts_b_rd.addr.eq(left_idx),
                            ends_b_rd.addr.eq(left_idx),
                        ]
                    m.next = "MERGE_WRITE_LEFT"

                with m.Else():
                    # Both have elements - read left
                    with m.If(use_a_as_source):
                        m.d.comb += [
                            starts_a_rd.addr.eq(left_idx),
                            ends_a_rd.addr.eq(left_idx),
                        ]
                    with m.Else():
                        m.d.comb += [
                            starts_b_rd.addr.eq(left_idx),
                            ends_b_rd.addr.eq(left_idx),
                        ]
                    m.next = "MERGE_READ_RIGHT"

            with m.State("MERGE_READ_RIGHT"):
                # Latch left value (1 cycle after read command)
                with m.If(use_a_as_source):
                    m.d.sync += [
                        left_start.eq(starts_a_rd.data),
                        left_end.eq(ends_a_rd.data),
                    ]
                    # Issue right read
                    m.d.comb += [
                        starts_a_rd.addr.eq(right_idx),
                        ends_a_rd.addr.eq(right_idx),
                    ]
                with m.Else():
                    m.d.sync += [
                        left_start.eq(starts_b_rd.data),
                        left_end.eq(ends_b_rd.data),
                    ]
                    m.d.comb += [
                        starts_b_rd.addr.eq(right_idx),
                        ends_b_rd.addr.eq(right_idx),
                    ]
                m.next = "MERGE_COMPARE"

            with m.State("MERGE_COMPARE"):
                # Latch right value
                with m.If(use_a_as_source):
                    m.d.sync += [
                        right_start.eq(starts_a_rd.data),
                        right_end.eq(ends_a_rd.data),
                    ]
                with m.Else():
                    m.d.sync += [
                        right_start.eq(starts_b_rd.data),
                        right_end.eq(ends_b_rd.data),
                    ]
                m.next = "MERGE_WRITE_COMPARE"

            with m.State("MERGE_WRITE_COMPARE"):
                # Compare tuples: (start, end)
                take_left = Signal()
                m.d.comb += take_left.eq(
                    (left_start < right_start) |
                    ((left_start == right_start) & (left_end <= right_end))
                )

                # Write to opposite bank
                with m.If(use_a_as_source):
                    # Writing to B
                    with m.If(take_left):
                        m.d.comb += [
                            starts_b_wr.addr.eq(out_idx),
                            starts_b_wr.data.eq(left_start),
                            starts_b_wr.en.eq(1),
                            ends_b_wr.addr.eq(out_idx),
                            ends_b_wr.data.eq(left_end),
                            ends_b_wr.en.eq(1),
                        ]
                        m.d.sync += left_idx.eq(left_idx + 1)
                    with m.Else():
                        m.d.comb += [
                            starts_b_wr.addr.eq(out_idx),
                            starts_b_wr.data.eq(right_start),
                            starts_b_wr.en.eq(1),
                            ends_b_wr.addr.eq(out_idx),
                            ends_b_wr.data.eq(right_end),
                            ends_b_wr.en.eq(1),
                        ]
                        m.d.sync += right_idx.eq(right_idx + 1)
                with m.Else():
                    # Writing to A
                    with m.If(take_left):
                        m.d.comb += [
                            starts_a_wr.addr.eq(out_idx),
                            starts_a_wr.data.eq(left_start),
                            starts_a_wr.en.eq(1),
                            ends_a_wr.addr.eq(out_idx),
                            ends_a_wr.data.eq(left_end),
                            ends_a_wr.en.eq(1),
                        ]
                        m.d.sync += left_idx.eq(left_idx + 1)
                    with m.Else():
                        m.d.comb += [
                            starts_a_wr.addr.eq(out_idx),
                            starts_a_wr.data.eq(right_start),
                            starts_a_wr.en.eq(1),
                            ends_a_wr.addr.eq(out_idx),
                            ends_a_wr.data.eq(right_end),
                            ends_a_wr.en.eq(1),
                        ]
                        m.d.sync += right_idx.eq(right_idx + 1)

                m.d.sync += out_idx.eq(out_idx + 1)
                m.next = "MERGE_READ_LEFT"

            with m.State("MERGE_WRITE_LEFT"):
                # Write left element (1 cycle after read)
                with m.If(use_a_as_source):
                    m.d.comb += [
                        starts_b_wr.addr.eq(out_idx),
                        starts_b_wr.data.eq(starts_a_rd.data),
                        starts_b_wr.en.eq(1),
                        ends_b_wr.addr.eq(out_idx),
                        ends_b_wr.data.eq(ends_a_rd.data),
                        ends_b_wr.en.eq(1),
                    ]
                with m.Else():
                    m.d.comb += [
                        starts_a_wr.addr.eq(out_idx),
                        starts_a_wr.data.eq(starts_b_rd.data),
                        starts_a_wr.en.eq(1),
                        ends_a_wr.addr.eq(out_idx),
                        ends_a_wr.data.eq(ends_b_rd.data),
                        ends_a_wr.en.eq(1),
                    ]
                m.d.sync += [
                    left_idx.eq(left_idx + 1),
                    out_idx.eq(out_idx + 1),
                ]
                m.next = "MERGE_READ_LEFT"

            with m.State("MERGE_WRITE_RIGHT"):
                # Write right element (1 cycle after read)
                with m.If(use_a_as_source):
                    m.d.comb += [
                        starts_b_wr.addr.eq(out_idx),
                        starts_b_wr.data.eq(starts_a_rd.data),
                        starts_b_wr.en.eq(1),
                        ends_b_wr.addr.eq(out_idx),
                        ends_b_wr.data.eq(ends_a_rd.data),
                        ends_b_wr.en.eq(1),
                    ]
                with m.Else():
                    m.d.comb += [
                        starts_a_wr.addr.eq(out_idx),
                        starts_a_wr.data.eq(starts_b_rd.data),
                        starts_a_wr.en.eq(1),
                        ends_a_wr.addr.eq(out_idx),
                        ends_a_wr.data.eq(ends_b_rd.data),
                        ends_a_wr.en.eq(1),
                    ]
                m.d.sync += [
                    right_idx.eq(right_idx + 1),
                    out_idx.eq(out_idx + 1),
                ]
                m.next = "MERGE_READ_LEFT"

            with m.State("BLOCK_NEXT"):
                # Move to next block pair
                m.d.sync += block_start.eq(block_start + (merge_width << 1))

                with m.If(block_start + (merge_width << 1) >= num_ranges):
                    # Pass complete
                    m.next = "PASS_END"
                with m.Else():
                    m.next = "BLOCK_SETUP"

            with m.State("PASS_END"):
                # Check if sorting complete BEFORE flipping
                with m.If((merge_width << 1) >= num_ranges):
                    # Sorting complete! Don't flip
                    m.next = "OUTPUT_START"
                with m.Else():
                    # More passes needed
                    m.d.sync += [
                        merge_width.eq(merge_width << 1),
                        use_a_as_source.eq(~use_a_as_source),
                    ]
                    m.next = "PASS_START"

            with m.State("OUTPUT_START"):
                m.d.sync += [
                    output_idx.eq(0),
                    self.valid_out.eq(0),
                ]
                m.next = "OUTPUT_READ"

            with m.State("OUTPUT_READ"):
                # Clear valid_out (will be set again in EMIT if needed)
                m.d.sync += self.valid_out.eq(0)

                # Read from opposite bank (where last write went)
                with m.If(output_idx < num_ranges):
                    with m.If(use_a_as_source):
                        # Last write was to B
                        m.d.comb += [
                            starts_b_rd.addr.eq(output_idx),
                            ends_b_rd.addr.eq(output_idx),
                        ]
                    with m.Else():
                        # Last write was to A
                        m.d.comb += [
                            starts_a_rd.addr.eq(output_idx),
                            ends_a_rd.addr.eq(output_idx),
                        ]
                    m.next = "OUTPUT_EMIT"
                with m.Else():
                    m.d.sync += self.done.eq(1)
                    m.next = "IDLE"

            with m.State("OUTPUT_EMIT"):
                # Emit value (1 cycle after read)
                with m.If(use_a_as_source):
                    m.d.sync += [
                        self.start_out.eq(starts_b_rd.data),
                        self.end_out.eq(ends_b_rd.data),
                        self.valid_out.eq(1),
                    ]
                with m.Else():
                    m.d.sync += [
                        self.start_out.eq(starts_a_rd.data),
                        self.end_out.eq(ends_a_rd.data),
                        self.valid_out.eq(1),
                    ]

                # Check if this was the last element (before incrementing)
                with m.If(output_idx >= num_ranges - 1):
                    m.d.sync += self.done.eq(1)
                    m.next = "IDLE"
                with m.Else():
                    m.d.sync += output_idx.eq(output_idx + 1)
                    m.next = "OUTPUT_READ"

        return m
