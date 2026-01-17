"""
Property-based tests for range merger algorithm using Hypothesis.

This module formally verifies the correctness of the merge_all_ranges algorithm
by testing invariant properties that must hold for all valid inputs.
"""

import pytest
from hypothesis import given, strategies as st, assume, settings, HealthCheck
from hypothesis.strategies import lists, tuples, integers
import sys

# Import the functions to test
from software_reference.range_merger import merge_all_ranges, calculate_total_coverage


# Strategy for generating valid ranges (start <= end)
@st.composite
def valid_range(draw):
    """Generate a valid range where start <= end."""
    start = draw(integers(min_value=-1000000, max_value=1000000))
    end = draw(integers(min_value=start, max_value=1000000))
    return (start, end)


# Strategy for generating lists of valid ranges
ranges_strategy = lists(valid_range(), min_size=0, max_size=100)


def ranges_to_set(ranges):
    """Convert a list of ranges to a set of all integers covered."""
    result = set()
    for start, end in ranges:
        result.update(range(start, end + 1))
    return result


def is_sorted_by_start(ranges):
    """Check if ranges are sorted by start position."""
    for i in range(len(ranges) - 1):
        if ranges[i][0] > ranges[i + 1][0]:
            return False
    return True


def has_no_overlaps(ranges):
    """Check if ranges have no overlaps or adjacencies."""
    for i in range(len(ranges) - 1):
        if ranges[i][1] >= ranges[i + 1][0]:
            return False
    return True


# Property 1: Merged ranges cover the same integers as original ranges
@given(ranges_strategy)
@settings(max_examples=1000)
def test_coverage_preservation(ranges):
    """
    Property: The set of integers covered by merged ranges must equal
    the set of integers covered by original ranges.
    """
    # Skip if total coverage would be too large to compute
    total_span = sum(end - start + 1 for start, end in ranges)
    assume(total_span < 100000)  # Limit for performance

    original_coverage = ranges_to_set(ranges)
    merged = merge_all_ranges(ranges)
    merged_coverage = ranges_to_set(merged)

    assert original_coverage == merged_coverage, \
        f"Coverage mismatch: original={len(original_coverage)}, merged={len(merged_coverage)}"


# Property 2: Result must be sorted by start position
@given(ranges_strategy)
def test_output_is_sorted(ranges):
    """
    Property: Merged ranges must be sorted by start position.
    """
    merged = merge_all_ranges(ranges)
    assert is_sorted_by_start(merged), \
        f"Output not sorted: {merged}"


# Property 3: No overlapping or adjacent ranges in result
@given(ranges_strategy)
def test_no_overlaps_in_output(ranges):
    """
    Property: Merged ranges must not overlap or be adjacent.
    """
    merged = merge_all_ranges(ranges)
    assert has_no_overlaps(merged), \
        f"Output has overlaps: {merged}"


# Property 4: Idempotence - merging already merged ranges has no effect
@given(ranges_strategy)
def test_idempotence(ranges):
    """
    Property: merge_all_ranges(merge_all_ranges(x)) == merge_all_ranges(x)
    """
    merged_once = merge_all_ranges(ranges)
    merged_twice = merge_all_ranges(merged_once)

    assert merged_once == merged_twice, \
        f"Not idempotent: first={merged_once}, second={merged_twice}"


# Property 5: Empty input produces empty output
def test_empty_input():
    """
    Property: Merging empty list returns empty list.
    """
    assert merge_all_ranges([]) == []


# Property 6: Single range remains unchanged
@given(valid_range())
def test_single_range(r):
    """
    Property: A single range should remain unchanged.
    """
    assert merge_all_ranges([r]) == [r]


# Property 7: Calculate coverage matches expected count
@given(ranges_strategy)
@settings(max_examples=500, suppress_health_check=[HealthCheck.filter_too_much])
def test_coverage_calculation(ranges):
    """
    Property: calculate_total_coverage should return the count of unique integers.
    """
    # Skip if total coverage would be too large to compute
    total_span = sum(end - start + 1 for start, end in ranges)
    assume(total_span < 100000)

    merged = merge_all_ranges(ranges)
    coverage_count = calculate_total_coverage(merged)
    actual_coverage = ranges_to_set(ranges)

    assert coverage_count == len(actual_coverage), \
        f"Coverage count mismatch: calculated={coverage_count}, actual={len(actual_coverage)}"


# Property 8: Order independence - result should be same regardless of input order
@given(ranges_strategy)
def test_order_independence(ranges):
    """
    Property: The result should be the same regardless of input order.
    """
    if len(ranges) < 2:
        return  # Skip for trivial cases

    merged1 = merge_all_ranges(ranges)

    # Shuffle the ranges (use reverse as a simple permutation)
    reversed_ranges = list(reversed(ranges))
    merged2 = merge_all_ranges(reversed_ranges)

    assert merged1 == merged2, \
        f"Order dependent: forward={merged1}, reversed={merged2}"


# Property 9: Non-overlapping ranges remain separate
@given(lists(integers(min_value=0, max_value=100), min_size=2, max_size=10, unique=True))
def test_non_overlapping_ranges_separate(positions):
    """
    Property: Non-overlapping ranges with gaps should remain separate.
    """
    if len(positions) < 2:
        return

    # Create ranges with guaranteed gaps
    positions.sort()
    ranges = []
    for i, pos in enumerate(positions):
        start = pos * 10
        end = pos * 10 + 1  # Small range
        ranges.append((start, end))

    merged = merge_all_ranges(ranges)

    # Should have same number of ranges since they don't overlap
    assert len(merged) == len(ranges), \
        f"Non-overlapping ranges were merged: input={ranges}, output={merged}"


# Property 10: Complete overlap collapses to single range
@given(integers(min_value=-1000, max_value=1000), integers(min_value=1, max_value=100))
def test_complete_overlap_single_range(start, length):
    """
    Property: Multiple ranges that completely overlap should merge to one range.
    """
    end = start + length
    # Create multiple identical or subset ranges
    ranges = [
        (start, end),
        (start, end),
        (start + 1, end - 1),
        (start, start + 1)
    ]

    merged = merge_all_ranges(ranges)

    assert len(merged) == 1, \
        f"Completely overlapping ranges not merged to one: {merged}"
    assert merged[0] == (start, end), \
        f"Merged range incorrect: expected ({start}, {end}), got {merged[0]}"


# Concrete test cases for edge cases
def test_adjacent_ranges():
    """Test that adjacent ranges are merged correctly."""
    ranges = [(1, 5), (6, 10), (11, 15)]
    merged = merge_all_ranges(ranges)
    # Adjacent ranges should NOT be merged (5 and 6 are separate)
    assert merged == [(1, 5), (6, 10), (11, 15)]


def test_touching_ranges():
    """Test that touching ranges are merged."""
    ranges = [(1, 5), (5, 10)]
    merged = merge_all_ranges(ranges)
    # Touching at 5 should merge
    assert merged == [(1, 10)]


def test_overlapping_chains():
    """Test complex overlapping chains."""
    ranges = [(1, 3), (5, 7), (2, 6), (10, 15), (12, 20)]
    merged = merge_all_ranges(ranges)
    # (1,3), (2,6), (5,7) should merge to (1,7)
    # (10,15), (12,20) should merge to (10,20)
    assert merged == [(1, 7), (10, 20)]


def test_duplicate_ranges():
    """Test that duplicate ranges are handled correctly."""
    ranges = [(1, 5), (1, 5), (1, 5)]
    merged = merge_all_ranges(ranges)
    assert merged == [(1, 5)]


def test_negative_ranges():
    """Test ranges with negative numbers."""
    ranges = [(-10, -5), (-7, -3), (0, 5)]
    merged = merge_all_ranges(ranges)
    assert merged == [(-10, -3), (0, 5)]


def test_single_point_ranges():
    """Test ranges that are single points."""
    ranges = [(1, 1), (2, 2), (3, 3), (5, 5)]
    merged = merge_all_ranges(ranges)
    # Single points (1,1) and (2,2): 2 > 1, so they're separate (no overlap)
    # Consecutive integers but not overlapping ranges
    assert merged == [(1, 1), (2, 2), (3, 3), (5, 5)]


def test_consecutive_integers_as_ranges():
    """Test that consecutive integers represented as overlapping ranges merge."""
    # To merge 1,2,3 into (1,3), ranges must overlap
    ranges = [(1, 2), (2, 3), (3, 4)]
    merged = merge_all_ranges(ranges)
    # These overlap at their boundaries, so they merge
    assert merged == [(1, 4)]


if __name__ == "__main__":
    # Run pytest
    pytest.main([__file__, "-v", "--tb=short"])
