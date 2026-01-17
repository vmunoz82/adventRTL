"""
Comprehensive testbench for MergeSortBRAM RTL implementation.

Tests the BRAM-based merge sort that sorts ranges by (start, end) tuples.
Part of the complete range processing pipeline.

Usage:
    python3 -m amaranth_benchs.rtl_merge_sort_tests [test_file]

Default test file: testcases/default_input.txt
"""

import sys
from amaranth import *
from amaranth.sim import Simulator, Tick
from rtl.merge_sort import MergeSortBRAM
from software_reference.range_merger import read_input


def test_merge_sort_with_actual_data(test_file="testcases/default_input.txt", num_ranges=173):
    """
    Test the hardware RTL implementation with actual input data.

    Args:
        test_file: Path to test data file
        num_ranges: Number of ranges to test (default: 173)
    """

    print("=" * 80)
    print("MergeSortBRAM RTL Verification")
    print("=" * 80)

    # Read input data
    print("\n[1] Loading input data...")
    print(f"    File: {test_file}")
    ranges, _ = read_input(test_file)
    test_data = ranges[:num_ranges]
    print(f"    Loaded {len(test_data)} ranges for testing")

    # Get expected result (software reference)
    print("\n[2] Computing software reference...")
    expected = sorted(test_data)
    print(f"    Software sorted: {len(expected)} ranges")

    # Run hardware simulation
    print("\n[3] Running hardware RTL simulation...")

    dut = MergeSortBRAM(max_ranges=256, width=64)
    sorted_output = []

    def testbench():
        # Load input data
        for start, end in test_data:
            yield dut.start_in.eq(start)
            yield dut.end_in.eq(end)
            yield dut.valid_in.eq(1)
            yield Tick()

        yield dut.valid_in.eq(0)
        yield dut.count_in.eq(len(test_data))
        yield Tick()

        # Start sorting
        yield dut.start.eq(1)
        yield Tick()
        yield dut.start.eq(0)

        # Collect sorted outputs
        for cycle in range(10000):
            yield Tick()

            if (yield dut.valid_out):
                out = ((yield dut.start_out), (yield dut.end_out))
                sorted_output.append(out)
                idx = yield dut.output_idx
                if len(sorted_output) <= 5 or len(sorted_output) > len(test_data) - 3:
                    print(f"    Output[{len(sorted_output)-1}]: {out}, output_idx={idx}")

            if (yield dut.done):
                print(f"    Done at cycle {cycle}")
                break

            if cycle % 1000 == 0 and cycle > 0:
                print(f"  Cycle {cycle}, outputs: {len(sorted_output)}")

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_process(testbench)

    with sim.write_vcd("generated/merge_sort_bram.vcd"):
        sim.run()

    # Verify results
    print(f"\n[4] Verifying results...")
    print(f"    Hardware output: {len(sorted_output)} ranges")
    print(f"    Expected:        {len(expected)} ranges")

    if len(sorted_output) != len(expected):
        print(f"\n    [BAD] MISMATCH: Different number of outputs!")
        return False

    if sorted_output == expected:
        print("\n    [OK] SUCCESS: All outputs match perfectly!")
        print(f"    [OK] Sorted {len(expected)} ranges correctly")
        return True
    else:
        # Check if at least sorted
        is_sorted = all(sorted_output[i] <= sorted_output[i+1]
                        for i in range(len(sorted_output)-1))
        print(f"    Is sorted: {is_sorted}")

        # Find first mismatch
        for i in range(min(len(sorted_output), len(expected))):
            if sorted_output[i] != expected[i]:
                print(f"\n    First mismatch at {i}:")
                print(f"      Got:      {sorted_output[i]}")
                print(f"      Expected: {expected[i]}")
                break
        return False


def test_small_examples():
    """Test with small hand-crafted examples."""

    print("\n" + "=" * 80)
    print("Small Example Tests")
    print("=" * 80)

    test_cases = [
        {
            "name": "Already sorted",
            "input": [(1, 5), (10, 15), (20, 25)],
            "expected": [(1, 5), (10, 15), (20, 25)],
        },
        {
            "name": "Reverse sorted",
            "input": [(20, 25), (10, 15), (1, 5)],
            "expected": [(1, 5), (10, 15), (20, 25)],
        },
        {
            "name": "Random order",
            "input": [(15, 20), (1, 5), (3, 10)],
            "expected": [(1, 5), (3, 10), (15, 20)],
        },
        {
            "name": "Single element",
            "input": [(100, 200)],
            "expected": [(100, 200)],
        },
        {
            "name": "Two elements",
            "input": [(10, 20), (1, 5)],
            "expected": [(1, 5), (10, 20)],
        },
    ]

    all_passed = True

    for test in test_cases:
        print(f"\n  Test: {test['name']}")
        print(f"    Input: {test['input']}")
        print(f"    Expected: {test['expected']}")

        dut = MergeSortBRAM(max_ranges=256, width=64)
        hw_results = []

        def testbench():
            # Load input
            for start, end in test['input']:
                yield dut.start_in.eq(start)
                yield dut.end_in.eq(end)
                yield dut.valid_in.eq(1)
                yield Tick()

            yield dut.valid_in.eq(0)
            yield dut.count_in.eq(len(test['input']))
            yield Tick()

            # Start
            yield dut.start.eq(1)
            yield Tick()
            yield dut.start.eq(0)

            # Collect outputs
            for _ in range(1000):
                yield Tick()
                if (yield dut.valid_out):
                    hw_results.append(((yield dut.start_out), (yield dut.end_out)))
                if (yield dut.done):
                    break

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
    print("Amaranth HDL MergeSortBRAM Verification Suite")
    print("=" * 80)

    # Run small tests first
    small_tests_passed = test_small_examples()

    # Run full test with actual data
    full_test_passed = test_merge_sort_with_actual_data(test_file)

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
