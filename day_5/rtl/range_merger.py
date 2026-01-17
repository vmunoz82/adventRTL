"""
Range Merger Hardware Implementation using Amaranth HDL

This module implements the range merging algorithm in hardware RTL.
The design uses a streaming architecture that processes pre-sorted ranges
and merges overlapping ones.

Architecture:
- Input: Stream of (start, end) range pairs (must be pre-sorted)
- Output: Stream of merged (start, end) range pairs
- Processing: Single-pass merge using a register to hold the last range
"""

from amaranth import *
from amaranth.sim import Simulator


class RangeMerger(Elaboratable):
    """
    Hardware module that merges overlapping ranges.

    Assumes input ranges are sorted by start position.

    Ports:
        Input:
            - start_in: Current range start value (64-bit)
            - end_in: Current range end value (64-bit)
            - valid_in: Input data valid signal
            - ready_out: Module ready to accept data

        Output:
            - start_out: Merged range start value (64-bit)
            - end_out: Merged range end value (64-bit)
            - valid_out: Output data valid signal
            - ready_in: Downstream ready to accept data
    """

    def __init__(self, width=64, compute_coverage=False):
        """
        Initialize the Range Merger module.

        Args:
            width: Bit width for range values (default: 64)
            compute_coverage: If True, accumulate total coverage (default: False)
        """
        self.width = width
        self.compute_coverage = compute_coverage

        # Input interface
        self.start_in = Signal(width)
        self.end_in = Signal(width)
        self.valid_in = Signal()
        self.last_in = Signal()  # Indicates last input range

        # Output interface
        self.start_out = Signal(width)
        self.end_out = Signal(width)
        self.valid_out = Signal()
        self.last_out = Signal()  # Indicates last output range

        # Coverage output (optional, only when compute_coverage=True)
        # 128-bit to handle large sums (max ~10^38)
        self.total_coverage = Signal(128)

        # Control
        self.ready = Signal()  # Ready to accept input

    def elaborate(self, platform):
        m = Module()

        # Internal registers to hold the current accumulated range
        accum_start = Signal(self.width)
        accum_end = Signal(self.width)
        have_accum = Signal()  # We have a range being accumulated

        # Combinational logic for merge decision
        new_end = Signal(self.width)
        m.d.comb += new_end.eq(Mux(self.end_in > accum_end, self.end_in, accum_end))

        # Coverage accumulation (when enabled)
        if self.compute_coverage:
            coverage_accum = Signal(128)
            range_size = Signal(128)
            m.d.comb += self.total_coverage.eq(coverage_accum)

        # State machine states
        with m.FSM() as fsm:

            with m.State("IDLE"):
                m.d.comb += self.ready.eq(1)
                m.d.sync += [
                    self.valid_out.eq(0),
                    self.last_out.eq(0),
                ]

                # When we receive the first valid input
                with m.If(self.valid_in):
                    m.d.sync += [
                        accum_start.eq(self.start_in),
                        accum_end.eq(self.end_in),
                        have_accum.eq(1),
                    ]
                    # Check if this is also the last input
                    with m.If(self.last_in):
                        m.next = "OUTPUT_LAST"
                    with m.Else():
                        m.next = "PROCESS"

            with m.State("PROCESS"):
                m.d.comb += self.ready.eq(1)
                m.d.sync += [
                    self.valid_out.eq(0),
                    self.last_out.eq(0),
                ]

                with m.If(self.valid_in):
                    # Check if current input overlaps with accumulated range
                    # Overlap condition: start_in <= accum_end
                    with m.If(self.start_in <= accum_end):
                        # Merge: extend the end to maximum of both
                        m.d.sync += accum_end.eq(new_end)

                        # If this is the last input, output the merged range
                        with m.If(self.last_in):
                            m.next = "OUTPUT_LAST"

                    with m.Else():
                        # No overlap: output the accumulated range and start new one
                        m.d.sync += [
                            self.start_out.eq(accum_start),
                            self.end_out.eq(accum_end),
                            self.valid_out.eq(1),
                            self.last_out.eq(0),
                            accum_start.eq(self.start_in),
                            accum_end.eq(self.end_in),
                        ]

                        # Accumulate coverage if enabled
                        if self.compute_coverage:
                            m.d.comb += range_size.eq(accum_end - accum_start + 1)
                            m.d.sync += coverage_accum.eq(coverage_accum + range_size)

                        # If this is the last input, we need to output it next
                        with m.If(self.last_in):
                            m.next = "OUTPUT_LAST"
                        with m.Else():
                            m.next = "PROCESS"

            with m.State("OUTPUT_LAST"):
                # Output the final accumulated range
                m.d.sync += [
                    self.start_out.eq(accum_start),
                    self.end_out.eq(accum_end),
                    self.valid_out.eq(1),
                    self.last_out.eq(1),
                    have_accum.eq(0),
                ]

                # Accumulate coverage for the final range if enabled
                if self.compute_coverage:
                    m.d.comb += range_size.eq(accum_end - accum_start + 1)
                    m.d.sync += coverage_accum.eq(coverage_accum + range_size)

                m.next = "DONE"

            with m.State("DONE"):
                # Processing complete, hold output valid for one more cycle
                m.d.sync += [
                    self.valid_out.eq(0),
                ]
                m.d.comb += self.ready.eq(0)

        return m
