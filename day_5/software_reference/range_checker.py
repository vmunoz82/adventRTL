"""
Range Checker - Part One: Count Valid Query IDs

Checks which query IDs fall within any of the specified inclusion ranges.
Uses binary search for efficient lookup after merging ranges.
"""

import sys


def read_input(filename):
    """
    Read input file containing ranges and check values.

    Args:
        filename: Path to input file

    Returns:
        tuple: (ranges, checks) where ranges is list of (start, end) tuples
               and checks is list of integers to verify
    """
    with open(filename) as f:
        ranges = []
        checks = []
        state = 0

        for line in f:
            line = line.strip()

            if state == 0:
                parts = line.split("-")
                if len(parts) == 2:
                    start, end = int(parts[0]), int(parts[1])
                    ranges.append((start, end))
                else:
                    state = 1

            elif state == 1:
                state = 2
                continue

            elif state == 2:
                checks.append(int(line))

    return ranges, checks


def merge_all_ranges(ranges):
    """
    Merge all overlapping or adjacent ranges in a single pass.

    Args:
        ranges: List of (start, end) tuples

    Returns:
        list: Fully merged list of non-overlapping ranges, sorted by start position

    Algorithm:
        1. Sort ranges by start position
        2. Iterate through sorted ranges
        3. For each range, try to merge with the last merged range
        4. If overlap exists (current.start <= last.end), extend the last range
        5. Otherwise, add current range as a new separate range

    Time Complexity: O(n log n) where n is the number of ranges
    Space Complexity: O(n) for the output list
    """
    if not ranges:
        return []

    # Sort ranges by start position (and by end position as tiebreaker)
    sorted_ranges = sorted(ranges)
    merged = [sorted_ranges[0]]

    for current_start, current_end in sorted_ranges[1:]:
        last_start, last_end = merged[-1]

        # Check if current range overlaps with or is adjacent to the last merged range
        if current_start <= last_end:
            # Merge: extend the last range to include the current one
            merged[-1] = (last_start, max(last_end, current_end))
        else:
            # No overlap: add current range as a new separate range
            merged.append((current_start, current_end))

    return merged


def is_in_ranges(value, ranges):
    """
    Check if a value falls within any of the merged ranges using binary search.

    Args:
        value: Integer to check
        ranges: List of (start, end) tuples, sorted by start, non-overlapping

    Returns:
        bool: True if value is in any range, False otherwise

    Algorithm:
        Binary search on range start positions to find potential match,
        then verify the value is within that range's end boundary.
    """
    if not ranges:
        return False

    left, right = 0, len(ranges) - 1

    while left <= right:
        mid = (left + right) // 2
        start, end = ranges[mid]

        if value < start:
            # Value is before this range, search left half
            right = mid - 1
        elif value > end:
            # Value is after this range, search right half
            # Note: since ranges are non-overlapping and sorted,
            # if value > end, it cannot be in current range or any previous range
            left = mid + 1
        else:
            # value >= start and value <= end: found it!
            return True

    return False


def count_valid_ids(ranges, checks):
    """
    Count how many check IDs fall within any of the ranges.

    Args:
        ranges: List of (start, end) tuples (will be merged)
        checks: List of integer IDs to check

    Returns:
        int: Count of check IDs that are valid (fall within at least one range)

    Time Complexity: O(n log n + m log n) where:
        - n = number of ranges (for sorting and merging)
        - m = number of checks (for binary search on each)
    Space Complexity: O(n) for merged ranges
    """
    # First merge ranges for efficient lookup
    merged = merge_all_ranges(ranges)

    # Count valid IDs using binary search
    valid_count = 0
    for check_id in checks:
        if is_in_ranges(check_id, merged):
            valid_count += 1

    return valid_count


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python range_checker.py <input_file>")
        sys.exit(1)

    input_file = sys.argv[1]
    ranges, checks = read_input(input_file)

    # Count how many check IDs are valid
    valid_count = count_valid_ids(ranges, checks)

    print(f"Valid IDs count: {valid_count}")
