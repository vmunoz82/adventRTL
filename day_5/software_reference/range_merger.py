
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

def suma(n):
    """
    Calculate sum of integers from 1 to n using Gauss formula.

    Args:
        n: Upper bound integer

    Returns:
        int: Sum of 1 + 2 + ... + n
    """
    return (n * (n + 1)) // 2


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


def calculate_total_coverage(ranges):
    """
    Calculate total number of integers covered by all ranges.

    Args:
        ranges: List of (start, end) tuples

    Returns:
        int: Total count of unique integers in all ranges
    """
    total = 0
    for start, end in ranges:
        total += end - (start - 1)
    return total


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python range_merger.py <input_file>")
        sys.exit(1)

    input_file = sys.argv[1]
    ranges, checks = read_input(input_file)

    # Merge all overlapping ranges
    merged_ranges = merge_all_ranges(ranges)

    # Calculate total coverage
    total = calculate_total_coverage(merged_ranges)

    print(f"Total coverage: {total}")
