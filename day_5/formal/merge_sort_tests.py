"""
Property-based testing for hardware merge sort using Hypothesis.

This complements formal verification by testing the hardware implementation
with thousands of randomly generated test cases of varying sizes.
"""

from hypothesis import given, strategies as st, settings, Phase
from amaranth.sim import Simulator, Tick
from rtl.merge_sort import MergeSortBRAM


def simulate_merge_sort(test_data, max_ranges=256):
    """Simulate the merge sort hardware and return sorted output."""
    dut = MergeSortBRAM(max_ranges=max_ranges, width=64)
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

        # Collect outputs (with timeout)
        for cycle in range(50000):
            yield Tick()

            if (yield dut.valid_out):
                out = ((yield dut.start_out), (yield dut.end_out))
                sorted_output.append(out)

            if (yield dut.done):
                break

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_process(testbench)
    sim.run()

    return sorted_output


# Strategy: generate lists of (start, end) tuples
range_tuple = st.tuples(
    st.integers(min_value=0, max_value=1000),  # start
    st.integers(min_value=0, max_value=1000)   # end
).filter(lambda t: t[0] <= t[1])  # ensure start <= end


@given(st.lists(range_tuple, min_size=1, max_size=8))
@settings(max_examples=100, phases=[Phase.generate, Phase.target])
def test_merge_sort_property_small(test_data):
    """
    Property: Hardware merge sort produces same result as Python sorted()
    Test with small inputs (1-8 elements)
    """
    expected = sorted(test_data)
    actual = simulate_merge_sort(test_data, max_ranges=16)

    assert len(actual) == len(expected), f"Length mismatch: {len(actual)} vs {len(expected)}"
    assert actual == expected, f"Sort mismatch"


@given(st.lists(range_tuple, min_size=9, max_size=32))
@settings(max_examples=50)
def test_merge_sort_property_medium(test_data):
    """
    Property: Hardware merge sort produces same result as Python sorted()
    Test with medium inputs (9-32 elements)
    """
    expected = sorted(test_data)
    actual = simulate_merge_sort(test_data, max_ranges=64)

    assert len(actual) == len(expected), f"Length mismatch: {len(actual)} vs {len(expected)}"
    assert actual == expected, f"Sort mismatch"


@given(st.lists(range_tuple, min_size=33, max_size=100))
@settings(max_examples=20, deadline=2000)  # 2 second deadline for large tests
def test_merge_sort_property_large(test_data):
    """
    Property: Hardware merge sort produces same result as Python sorted()
    Test with large inputs (33-100 elements)
    """
    expected = sorted(test_data)
    actual = simulate_merge_sort(test_data, max_ranges=128)

    assert len(actual) == len(expected), f"Length mismatch: {len(actual)} vs {len(expected)}"
    assert actual == expected, f"Sort mismatch"


@given(st.lists(range_tuple, min_size=1, max_size=200))
@settings(max_examples=10, deadline=5000)  # 5 second deadline for extra large tests
def test_merge_sort_property_xlarge(test_data):
    """
    Property: Hardware merge sort produces same result as Python sorted()
    Test with extra large inputs (1-200 elements)
    """
    expected = sorted(test_data)
    actual = simulate_merge_sort(test_data, max_ranges=256)

    assert len(actual) == len(expected), f"Length mismatch: {len(actual)} vs {len(expected)}"
    assert actual == expected, f"Sort mismatch"


# Edge cases
@given(st.lists(range_tuple, min_size=1, max_size=20))
def test_all_identical(test_data):
    """Property: Sorting identical elements works correctly"""
    # Make all elements the same
    if test_data:
        test_data = [test_data[0]] * len(test_data)

    expected = sorted(test_data)
    actual = simulate_merge_sort(test_data, max_ranges=32)
    assert actual == expected


@given(st.lists(range_tuple, min_size=2, max_size=20))
def test_already_sorted(test_data):
    """Property: Sorting already-sorted data works correctly"""
    test_data = sorted(test_data)

    expected = test_data  # Already sorted
    actual = simulate_merge_sort(test_data, max_ranges=32)
    assert actual == expected


@given(st.lists(range_tuple, min_size=2, max_size=20))
def test_reverse_sorted(test_data):
    """Property: Sorting reverse-sorted data works correctly"""
    test_data = sorted(test_data, reverse=True)

    expected = sorted(test_data)
    actual = simulate_merge_sort(test_data, max_ranges=32)
    assert actual == expected


if __name__ == "__main__":
    import pytest
    import sys

    print("=" * 70)
    print("Property-Based Testing: Hardware Merge Sort")
    print("=" * 70)
    print("\nRunning Hypothesis-based property tests...")
    print("This will generate hundreds of random test cases.\n")

    # Run with pytest
    exit_code = pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "--hypothesis-show-statistics"
    ])

    sys.exit(exit_code)
