"""
Range Checker - Part One: Count Valid Query IDs

Hardware RTL implementation of binary search on merged ranges.
Checks which query IDs fall within any of the merged inclusion ranges.
This version fixes integration issues found in the original implementation.

Architecture:
    1. Load merged ranges into BRAM (sorted, non-overlapping)
    2. For each query ID, perform binary search
    3. Count how many query IDs are valid

Components:
    - BRAM storage for merged ranges
    - Binary search FSM
    - Valid ID counter

"""

from amaranth import *
from rtl.interval_coverage import IntervalCoverage


class RangeChecker(Elaboratable):
    """
    Hardware module that checks query IDs against merged ranges using binary search.
    
    Ports:
        Input (range loading phase):
            - range_start_in: Merged range start value (64-bit)
            - range_end_in: Merged range end value (64-bit)
            - range_valid_in: Range input data valid signal
            - range_count_in: Total number of merged ranges

        Input (query checking phase):
            - check_id_in: Query ID to check (64-bit)
            - check_valid_in: Query ID input data valid signal
            - check_count_in: Total number of query IDs to check

        Output:
            - valid_count_out: Count of valid query IDs (32-bit)
            - done: Processing complete
            - check_idx_out: Current check index being processed (for debug/sync)
            - range_idx_out: Current range index being loaded (for debug/sync)

        Control:
            - start: Start checking after ranges are loaded
            - ready: Ready to accept input
    """

    def __init__(self, max_ranges=256, max_checks=1024, width=64):
        self.max_ranges = max_ranges
        self.max_checks = max_checks
        self.width = width

        # Range input interface
        self.range_start_in = Signal(width)
        self.range_end_in = Signal(width)
        self.range_valid_in = Signal()
        self.range_count_in = Signal(range(max_ranges + 1))

        # Check input interface
        self.check_id_in = Signal(width)
        self.check_valid_in = Signal()
        self.check_count_in = Signal(range(max_checks + 1))

        # Output interface
        self.valid_count_out = Signal(32)
        self.done = Signal()
        self.check_idx_out = Signal(range(max_checks + 1))
        self.range_idx_out = Signal(range(max_ranges + 1))

        # Control
        self.start = Signal()
        self.ready = Signal()
        self.busy = Signal()

    def elaborate(self, platform):
        m = Module()

        # BRAM storage for merged ranges
        starts_mem = Memory(width=self.width, depth=self.max_ranges)
        ends_mem = Memory(width=self.width, depth=self.max_ranges)

        starts_rd = starts_mem.read_port()
        starts_wr = starts_mem.write_port()
        ends_rd = ends_mem.read_port()
        ends_wr = ends_mem.write_port()

        m.submodules += [starts_rd, starts_wr, ends_rd, ends_wr]

        # State variables
        num_ranges = Signal(range(self.max_ranges + 1))
        num_checks = Signal(range(self.max_checks + 1))
        range_idx = Signal(range(self.max_ranges + 1))
        check_idx = Signal(range(self.max_checks + 1))

        # Connect check_idx and range_idx to output for monitoring
        m.d.comb += [
            self.check_idx_out.eq(check_idx),
            self.range_idx_out.eq(range_idx)
        ]

        # Binary search variables
        left = Signal(range(self.max_ranges + 1))
        right = Signal(range(self.max_ranges + 1))
        mid = Signal(range(self.max_ranges + 1))

        # Current check value
        current_check = Signal(self.width)

        # Latched range values from memory
        range_start = Signal(self.width)
        range_end = Signal(self.width)

        # Valid count accumulator
        valid_count = Signal(32)

        with m.FSM() as fsm:

            with m.State("IDLE"):
                m.d.comb += self.ready.eq(1)
                m.d.sync += [
                    self.busy.eq(0),
                    self.done.eq(0),
                    valid_count.eq(0),
                ]

                # Load merged ranges into BRAM
                with m.If(self.range_valid_in):
                    m.d.comb += [
                        starts_wr.addr.eq(range_idx),
                        starts_wr.data.eq(self.range_start_in),
                        starts_wr.en.eq(1),
                        ends_wr.addr.eq(range_idx),
                        ends_wr.data.eq(self.range_end_in),
                        ends_wr.en.eq(1),
                    ]
                    m.d.sync += range_idx.eq(range_idx + 1)

                # Start checking when commanded
                with m.If(self.start):
                    m.d.sync += [
                        num_ranges.eq(self.range_count_in),
                        num_checks.eq(self.check_count_in),
                        check_idx.eq(0),
                        self.busy.eq(1),
                        # Initialize search bounds for the first check (will be reset anyway)
                        left.eq(0),
                        right.eq(self.range_count_in - 1),
                    ]
                    m.next = "LOAD_CHECK"

            with m.State("LOAD_CHECK"):
                # Check if all IDs processed
                with m.If(check_idx >= num_checks):
                    m.d.sync += [
                        self.valid_count_out.eq(valid_count),
                        self.done.eq(1),
                    ]
                    m.next = "DONE"
                
                # Wait for valid check ID input
                with m.Elif(self.check_valid_in):
                    m.d.sync += [
                        current_check.eq(self.check_id_in),
                        left.eq(0),
                        right.eq(num_ranges - 1),
                    ]
                    m.next = "SEARCH_SETUP"

            with m.State("SEARCH_SETUP"):
                # 1. Handle empty ranges case
                # 2. Handle search completion (not found)
                # 3. Calculate mid for next step

                with m.If(num_ranges == 0):
                    # No ranges at all
                    m.d.sync += check_idx.eq(check_idx + 1)
                    m.next = "LOAD_CHECK"

                with m.Elif(left > right):
                    # Binary search finished, not found
                    m.d.sync += check_idx.eq(check_idx + 1)
                    m.next = "LOAD_CHECK"

                with m.Else():
                    # Calculate middle index
                    m.d.sync += mid.eq((left + right) >> 1)
                    m.next = "SEARCH_READ"

            with m.State("SEARCH_READ"):
                # Initiate read from memory
                m.d.comb += [
                    starts_rd.addr.eq(mid),
                    ends_rd.addr.eq(mid),
                ]
                m.next = "SEARCH_LATCH"

            with m.State("SEARCH_LATCH"):
                # Wait for memory read (1 cycle latency)
                m.d.sync += [
                    range_start.eq(starts_rd.data),
                    range_end.eq(ends_rd.data),
                ]
                m.next = "SEARCH_COMPARE"

            with m.State("SEARCH_COMPARE"):
                # Check where current_check lies relative to [range_start, range_end]
                
                with m.If(current_check < range_start):
                    # Go Left
                    with m.If(mid == 0):
                        # Cannot go left anymore, not found
                        m.d.sync += check_idx.eq(check_idx + 1)
                        m.next = "LOAD_CHECK"
                    with m.Else():
                        m.d.sync += right.eq(mid - 1)
                        m.next = "SEARCH_SETUP"

                with m.Elif(current_check > range_end):
                    # Go Right
                    m.d.sync += left.eq(mid + 1)
                    m.next = "SEARCH_SETUP"

                with m.Else():
                    # Found! (range_start <= current_check <= range_end)
                    m.d.sync += [
                        valid_count.eq(valid_count + 1),
                        check_idx.eq(check_idx + 1),
                    ]
                    m.next = "LOAD_CHECK"

            with m.State("DONE"):
                m.d.sync += [
                    self.done.eq(1),
                    self.busy.eq(0),
                ]
                # Hold done state

        return m


class RangeCheckerSystem(Elaboratable):
    """
    Complete system: IntervalCoverage -> RangeChecker
    """

    def __init__(self, max_ranges=256, max_checks=1024, width=64):
        self.max_ranges = max_ranges
        self.max_checks = max_checks
        self.width = width

        # Range input interface
        self.range_start_in = Signal(width)
        self.range_end_in = Signal(width)
        self.range_valid_in = Signal()
        self.range_count_in = Signal(range(max_ranges + 1))

        # Check input interface
        self.check_id_in = Signal(width)
        self.check_valid_in = Signal()
        self.check_count_in = Signal(range(max_checks + 1))

        # Output interface
        self.valid_count_out = Signal(32)
        self.done = Signal()
        
        # Debug access
        self.checker_check_idx = Signal(range(max_checks + 1))
        self.checker_range_idx = Signal(range(max_ranges + 1))

        # Control
        self.start = Signal()
        self.ready = Signal()

    def elaborate(self, platform):
        m = Module()

        # Instantiate submodules
        coverage = IntervalCoverage(max_ranges=self.max_ranges, width=self.width)
        checker = RangeChecker(
            max_ranges=self.max_ranges, 
            max_checks=self.max_checks, 
            width=self.width
        )

        m.submodules.coverage = coverage
        m.submodules.checker = checker
        
        # Expose submodules for testbench access
        self.coverage = coverage
        self.checker = checker
        
        # Expose checker index and range index for testbench
        m.d.comb += [
            self.checker_check_idx.eq(checker.check_idx_out),
            self.checker_range_idx.eq(checker.range_idx_out)
        ]

        # Connect input ranges to coverage system
        m.d.comb += [
            coverage.start_in.eq(self.range_start_in),
            coverage.end_in.eq(self.range_end_in),
            coverage.valid_in.eq(self.range_valid_in),
            coverage.count_in.eq(self.range_count_in),
        ]

        # Internal signals for bridging
        merged_count = Signal(range(self.max_ranges + 1))
        start_checker = Signal()
        
        # Connect checker inputs
        m.d.comb += [
            checker.check_id_in.eq(self.check_id_in),
            checker.check_valid_in.eq(self.check_valid_in),
            checker.check_count_in.eq(self.check_count_in),
            checker.start.eq(start_checker),
            
            # Connect coverage output to checker input
            # Only valid when coverage says so!
            checker.range_start_in.eq(coverage.start_out),
            checker.range_end_in.eq(coverage.end_out),
            checker.range_valid_in.eq(coverage.valid_out),
            checker.range_count_in.eq(merged_count),
        ]

        # Output connections
        m.d.comb += [
            self.valid_count_out.eq(checker.valid_count_out),
            self.done.eq(checker.done),
            # System is ready when coverage is ready (initial state)
            self.ready.eq(coverage.ready), 
        ]

        # FSM for system coordination
        with m.FSM() as fsm:
            
            with m.State("IDLE"):
                m.d.sync += [
                    merged_count.eq(0),
                    start_checker.eq(0),
                ]
                
                with m.If(self.start):
                    m.d.comb += coverage.start.eq(1)
                    m.next = "COVERAGE"

            with m.State("COVERAGE"):
                # Track number of merged ranges produced
                with m.If(coverage.valid_out):
                    m.d.sync += merged_count.eq(merged_count + 1)
                
                # Wait for coverage to finish sorting and merging
                with m.If(coverage.done):
                    m.next = "START_CHECKER"

            with m.State("START_CHECKER"):
                # Trigger checker start
                m.d.sync += start_checker.eq(1)
                m.next = "CHECKING"

            with m.State("CHECKING"):
                # Clear start signal once checker is busy
                with m.If(checker.busy):
                    m.d.sync += start_checker.eq(0)
                
                # Wait for checker to complete
                with m.If(checker.done):
                    m.next = "DONE"

            with m.State("DONE"):
                # Stay here
                pass

        return m


if __name__ == "__main__":
    import sys
    from amaranth.back import verilog

    output_path = sys.argv[1] if len(sys.argv) > 1 else "range_checker_system.v"

    top = RangeCheckerSystem(max_ranges=256, max_checks=1024, width=64)
    v = verilog.convert(top, name="top", ports=[
        # Range input interface
        top.range_start_in, top.range_end_in, top.range_valid_in, top.range_count_in,
        # Check input interface
        top.check_id_in, top.check_valid_in, top.check_count_in,
        # Output interface
        top.valid_count_out, top.done,
        # Debug access
        top.checker_check_idx, top.checker_range_idx,
        # Control
        top.start, top.ready,
    ])

    with open(output_path, "w") as f:
        f.write(v)
    print(f"Generated {output_path}")