"""
RangeChecker RTL testbench.

Tests hardware binary search implementation for checking query IDs
against merged ranges. Compares with software reference.
"""

import sys
from amaranth import *
from amaranth.sim import Simulator, Tick
from rtl.range_checker import RangeChecker, RangeCheckerSystem
from software_reference.range_checker import read_input, merge_all_ranges, is_in_ranges


def rtl_test_range_checker_basic(test_file="testcases/default_input.txt"):
    """
    Test RangeChecker module with actual data.
    Loads pre-merged ranges and checks query IDs using binary search.
    """

    print("=" * 80)
    print("RangeChecker RTL Test - Binary Search on Merged Ranges")
    print("=" * 80)

    # Read test data
    ranges, checks = read_input(test_file)

    # Use smaller subset for faster testing
    ranges = ranges[:20]
    checks = checks[:50]

    print(f"    Using {len(ranges)} ranges and {len(checks)} checks")

    # Software reference
    merged = merge_all_ranges(ranges)
    valid_count_sw = sum(1 for check in checks if is_in_ranges(check, merged))
    print(f"    Software: {len(merged)} merged ranges, {valid_count_sw} valid IDs")

    # Hardware test
    dut = RangeChecker(max_ranges=256, max_checks=1024, width=64)
    result = [False]

    def testbench():
        # Load merged ranges
        for start, end in merged:
            yield dut.range_start_in.eq(start)
            yield dut.range_end_in.eq(end)
            yield dut.range_valid_in.eq(1)
            yield Tick()

        yield dut.range_valid_in.eq(0)
        yield dut.range_count_in.eq(len(merged))
        yield dut.check_count_in.eq(len(checks))
        yield Tick()

        # Start checking
        yield dut.start.eq(1)
        yield Tick()
        yield dut.start.eq(0)

        # Feed check IDs - only when check_idx changes (one-cycle pulse)
        last_check_idx = -1
        for cycle in range(20000):
            # Get current check_idx to know which check to present
            current_check_idx = yield dut.check_idx_out

            # Present check ID only when idx changes (one-cycle pulse)
            if current_check_idx != last_check_idx and current_check_idx < len(checks):
                yield dut.check_id_in.eq(checks[current_check_idx])
                yield dut.check_valid_in.eq(1)
                last_check_idx = current_check_idx
            else:
                yield dut.check_valid_in.eq(0)

            yield Tick()

            if (yield dut.done):
                valid_count_hw = yield dut.valid_count_out
                print(f"    Done at cycle {cycle}")
                print(f"    Hardware: {valid_count_hw} valid IDs")

                if valid_count_hw == valid_count_sw:
                    print("\n    [OK] PERFECT MATCH! Hardware and software agree!")
                    result[0] = True
                    return
                else:
                    print(f"\n    [BAD] Mismatch! HW={valid_count_hw}, SW={valid_count_sw}")
                    return

            if cycle % 1000 == 0 and cycle > 0:
                print(f"    Cycle {cycle}, check_idx: {current_check_idx}")

        print("    [BAD] Timeout - did not finish!")

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_process(testbench)

    with sim.write_vcd("generated/range_checker.vcd"):
        sim.run()

    return result[0]


def rtl_test_range_checker_system(test_file="testcases/default_input.txt"):
    """
    Test complete RangeCheckerSystem (sort+merge + binary search).
    """

    print("\n" + "=" * 80)
    print("RangeCheckerSystem RTL Test - Full Part One Pipeline")
    print("=" * 80)

    # Read test data
    ranges, checks = read_input(test_file)

    # Use smaller subset for faster testing
    ranges = ranges[:20]
    checks = checks[:40]

    print(f"    Using {len(ranges)} ranges and {len(checks)} checks")

    # Software reference
    merged = merge_all_ranges(ranges)
    valid_count_sw = sum(1 for check in checks if is_in_ranges(check, merged))
    print(f"    Software: {len(merged)} merged ranges, {valid_count_sw} valid IDs")

    # Hardware test - full system
    dut = RangeCheckerSystem(max_ranges=256, max_checks=1024, width=64)
    result = [False]

    def testbench():
        # Load ranges
        for start, end in ranges:
            yield dut.range_start_in.eq(start)
            yield dut.range_end_in.eq(end)
            yield dut.range_valid_in.eq(1)
            yield Tick()

        yield dut.range_valid_in.eq(0)
        yield dut.range_count_in.eq(len(ranges))
        yield dut.check_count_in.eq(len(checks))
        yield Tick()

        # Start processing
        yield dut.start.eq(1)
        yield Tick()
        yield dut.start.eq(0)
        
        print("    Waiting for IntervalCoverage to finish...")
        
        # Wait for checker to start (which implies coverage is done)
        while not (yield dut.checker.busy):
            yield Tick()
            
        print("    Checker started! Feeding check IDs...")
        
        # Check range load count
        ranges_loaded = yield dut.checker_range_idx
        print(f"    Checker loaded {ranges_loaded} ranges")
        
        if ranges_loaded != len(merged):
             print(f"    WARNING: Loaded count mismatch! Expected {len(merged)}")

        # Feed check IDs - pulse when checker's internal idx changes
        last_check_idx = -1
        for cycle in range(50000):
            # Present check ID only when internal idx changes (one-cycle pulse)
            current_check_idx = yield dut.checker_check_idx
            if current_check_idx != last_check_idx and current_check_idx < len(checks):
                yield dut.check_id_in.eq(checks[current_check_idx])
                yield dut.check_valid_in.eq(1)
                last_check_idx = current_check_idx
            else:
                yield dut.check_valid_in.eq(0)

            yield Tick()

            if (yield dut.done):
                valid_count_hw = yield dut.valid_count_out
                print(f"    Done at cycle {cycle}")
                print(f"    Hardware: {valid_count_hw} valid IDs")

                if valid_count_hw == valid_count_sw:
                    print("\n    [OK] PERFECT MATCH! Full system works correctly!")
                    result[0] = True
                    return
                else:
                    print(f"\n    [BAD] Mismatch! HW={valid_count_hw}, SW={valid_count_sw}")
                    return

            if cycle % 2000 == 0 and cycle > 0:
                print(f"    Cycle {cycle}, check_idx: {current_check_idx}")

        print("    [BAD] Timeout - did not finish!")

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_process(testbench)

    with sim.write_vcd("generated/range_checker_system.vcd"):
        sim.run()

    return result[0]


if __name__ == "__main__":
    # Parse CLI arguments
    test_file = "testcases/default_input.txt"
    if len(sys.argv) > 1:
        test_file = sys.argv[1]

    print("\n" + "=" * 80)
    print("Amaranth HDL RangeChecker Verification Suite")
    print("=" * 80)

    # Run tests
    test1_passed = rtl_test_range_checker_basic(test_file)
    test2_passed = rtl_test_range_checker_system(test_file)

    print("\n" + "=" * 80)
    print("Final Results")
    print("=" * 80)
    print(f"  RangeChecker (binary search): {'[OK] PASS' if test1_passed else '[BAD] FAIL'}")
    print(f"  RangeCheckerSystem (full):    {'[OK] PASS' if test2_passed else '[BAD] FAIL'}")

    if test1_passed and test2_passed:
        print("\n  [OK] ALL TESTS PASSED! Part One hardware verified!")
        sys.exit(0)
    else:
        print("\n  [BAD] SOME TESTS FAILED!")
        sys.exit(1)