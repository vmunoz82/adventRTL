"""
Comprehensive testbench for Range Merger RTL implementation.

Loads actual input data from test file and compares hardware results
with software reference implementation.

Usage:
    python3 -m amaranth_benchs.range_merger_tests [test_file]

Default test file: testcases/default_input.txt
"""

import sys
from amaranth import *
from amaranth.sim import Simulator, Tick
from rtl.range_merger import RangeMerger
from software_reference.range_merger import merge_all_ranges, calculate_total_coverage, read_input


def test_range_merger_with_actual_data(test_file="testcases/default_input.txt"):
    """
    Test the hardware RTL implementation with actual input data
    and compare with software reference.

    Args:
        test_file: Path to test data file (default: testcases/default_input.txt)
    """

    print("=" * 80)
    print("Range Merger RTL Verification")
    print("=" * 80)

    # Read input data
    print("\n[1] Loading input data...")
    print(f"    File: {test_file}")
    ranges, checks = read_input(test_file)
    print(f"    Loaded {len(ranges)} ranges")

    # Sort ranges (hardware expects pre-sorted input)
    print("\n[2] Sorting ranges for hardware input...")
    sorted_ranges = sorted(ranges)

    # Get software reference result
    print("\n[3] Computing software reference...")
    sw_merged = merge_all_ranges(ranges)
    sw_coverage = calculate_total_coverage(sw_merged)
    print(f"    Software merged ranges: {len(sw_merged)}")
    print(f"    Software total coverage: {sw_coverage}")

    # Run hardware simulation
    print("\n[4] Running hardware RTL simulation...")

    dut = RangeMerger(width=64)
    hw_results = []

    def testbench():
        # Reset
        yield dut.valid_in.eq(0)
        yield dut.last_in.eq(0)
        yield Tick()
        yield Tick()

        # Feed sorted ranges to hardware
        for i, (start, end) in enumerate(sorted_ranges):
            # Wait for ready
            while not (yield dut.ready):
                yield Tick()

            # Apply input
            yield dut.start_in.eq(start)
            yield dut.end_in.eq(end)
            yield dut.valid_in.eq(1)
            yield dut.last_in.eq(1 if i == len(sorted_ranges) - 1 else 0)
            yield Tick()

            # Capture output if valid
            if (yield dut.valid_out):
                out_start = yield dut.start_out
                out_end = yield dut.end_out
                out_last = yield dut.last_out
                hw_results.append((out_start, out_end))
                if out_last:
                    print(f"    Hardware output last range at cycle {i+3}")

        # Clear inputs
        yield dut.valid_in.eq(0)
        yield dut.last_in.eq(0)

        # Continue clocking to capture remaining outputs
        for cycle in range(20):
            yield Tick()
            if (yield dut.valid_out):
                out_start = yield dut.start_out
                out_end = yield dut.end_out
                out_last = yield dut.last_out
                hw_results.append((out_start, out_end))
                if out_last:
                    print(f"    Hardware output completed at cleanup cycle {cycle}")
                    break

    sim = Simulator(dut)
    sim.add_clock(1e-6)  # 1 MHz clock
    sim.add_process(testbench)

    # Run simulation
    with sim.write_vcd("generated/range_merger_tests.vcd"):
        sim.run()

    print(f"    Hardware merged ranges: {len(hw_results)}")

    # Calculate hardware coverage
    hw_coverage = calculate_total_coverage(hw_results)
    print(f"    Hardware total coverage: {hw_coverage}")

    # Compare results
    print("\n[5] Comparing results...")
    print(f"    Software: {len(sw_merged)} ranges, coverage = {sw_coverage}")
    print(f"    Hardware: {len(hw_results)} ranges, coverage = {hw_coverage}")

    # Check if results match
    if len(sw_merged) != len(hw_results):
        print(f"\n    [BAD] MISMATCH: Different number of merged ranges!")
        print(f"       Software: {len(sw_merged)}, Hardware: {len(hw_results)}")

        # Show first few differences
        print("\n    First 10 software ranges:")
        for i, (s, e) in enumerate(sw_merged[:10]):
            print(f"      [{i}] ({s}, {e})")

        print("\n    First 10 hardware ranges:")
        for i, (s, e) in enumerate(hw_results[:10]):
            print(f"      [{i}] ({s}, {e})")

        return False

    # Compare each range
    all_match = True
    mismatches = []

    for i, (sw_range, hw_range) in enumerate(zip(sw_merged, hw_results)):
        if sw_range != hw_range:
            all_match = False
            mismatches.append((i, sw_range, hw_range))

    if not all_match:
        print(f"\n    [BAD] MISMATCH: Found {len(mismatches)} differing ranges!")
        for i, sw_range, hw_range in mismatches[:5]:  # Show first 5
            print(f"       Range {i}: SW={sw_range}, HW={hw_range}")
        return False

    # Check coverage
    if sw_coverage != hw_coverage:
        print(f"\n    [BAD] MISMATCH: Coverage differs!")
        print(f"       Software: {sw_coverage}")
        print(f"       Hardware: {hw_coverage}")
        return False

    print("\n    [OK] SUCCESS: Hardware and software results match perfectly!")
    print(f"    [OK] Both produce {len(sw_merged)} merged ranges")
    print(f"    [OK] Total coverage: {sw_coverage}")

    return True


def test_small_examples():
    """Test with small hand-crafted examples."""

    print("\n" + "=" * 80)
    print("Small Example Tests")
    print("=" * 80)

    test_cases = [
        {
            "name": "Basic overlap",
            "input": [(1, 5), (3, 10)],
            "expected": [(1, 10)],
        },
        {
            "name": "Multiple overlaps",
            "input": [(1, 5), (3, 10), (15, 20), (18, 25)],
            "expected": [(1, 10), (15, 25)],
        },
        {
            "name": "No overlaps",
            "input": [(1, 5), (10, 15), (20, 25)],
            "expected": [(1, 5), (10, 15), (20, 25)],
        },
        {
            "name": "Touching ranges",
            "input": [(1, 5), (5, 10)],
            "expected": [(1, 10)],
        },
        {
            "name": "Single range",
            "input": [(100, 200)],
            "expected": [(100, 200)],
        },
    ]

    all_passed = True

    for test in test_cases:
        print(f"\n  Test: {test['name']}")
        print(f"    Input: {test['input']}")

        # Software reference
        sw_result = merge_all_ranges(test['input'])
        print(f"    Software: {sw_result}")
        print(f"    Expected: {test['expected']}")

        if sw_result != test['expected']:
            print(f"    [BAD] Software reference doesn't match expected!")
            all_passed = False
            continue

        # Hardware simulation
        dut = RangeMerger(width=64)
        hw_results = []

        def testbench():
            yield dut.valid_in.eq(0)
            yield Tick()

            sorted_input = sorted(test['input'])

            for i, (start, end) in enumerate(sorted_input):
                while not (yield dut.ready):
                    yield Tick()

                yield dut.start_in.eq(start)
                yield dut.end_in.eq(end)
                yield dut.valid_in.eq(1)
                yield dut.last_in.eq(1 if i == len(sorted_input) - 1 else 0)
                yield Tick()

                if (yield dut.valid_out):
                    hw_results.append((
                        (yield dut.start_out),
                        (yield dut.end_out)
                    ))

            yield dut.valid_in.eq(0)
            yield dut.last_in.eq(0)

            for _ in range(10):
                yield Tick()
                if (yield dut.valid_out):
                    hw_results.append((
                        (yield dut.start_out),
                        (yield dut.end_out)
                    ))

        sim = Simulator(dut)
        sim.add_clock(1e-6)
        sim.add_process(testbench)
        sim.run()

        print(f"    Hardware: {hw_results}")

        if hw_results == test['expected']:
            print(f"    [OK] PASS")
        else:
            print(f"    [BAD] FAIL: Hardware output doesn't match!")
            all_passed = False

    return all_passed


if __name__ == "__main__":
    # Parse CLI arguments
    test_file = "testcases/default_input.txt"
    if len(sys.argv) > 1:
        test_file = sys.argv[1]

    print("\n" + "=" * 80)
    print("Amaranth HDL Range Merger Verification Suite")
    print("=" * 80)

    # Run small tests first
    small_tests_passed = test_small_examples()

    # Run full test with actual data
    full_test_passed = test_range_merger_with_actual_data(test_file)

    print("\n" + "=" * 80)
    print("Final Results")
    print("=" * 80)
    print(f"  Small examples: {'[OK] PASS' if small_tests_passed else '[BAD] FAIL'}")
    print(f"  Full data test: {'[OK] PASS' if full_test_passed else '[BAD] FAIL'}")

    if small_tests_passed and full_test_passed:
        print("\n  [OK] ALL TESTS PASSED! Hardware RTL verified against software!")
        sys.exit(0)
    else:
        print("\n  [BAD] SOME TESTS FAILED!")
        sys.exit(1)
