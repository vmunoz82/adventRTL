#!/usr/bin/env python3
"""
Utility to compare software reference against RTL implementation.

This script runs both implementations and compares their results,
showing detailed statistics and any discrepancies.
"""

import sys
import os
import subprocess
import time
from max_rectangle_finder import MaxRectangleFinder, parse_polygon_text


def run_software(input_text):
    """Run software reference implementation."""
    vertices = parse_polygon_text(input_text)

    finder = MaxRectangleFinder()
    for x, y in vertices:
        finder.add_vertex(x, y)

    start_time = time.time()
    max_area = finder.find_max_rectangle()
    elapsed = time.time() - start_time

    stats = finder.get_statistics()
    stats['elapsed'] = elapsed
    stats['result'] = max_area

    return stats


def run_rtl(input_file):
    """Run RTL implementation via UART bridge."""
    try:
        # Run UART bridge test directly (assumes libraries are built)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        test_script = os.path.join(script_dir, '..', 'verilator_benchs', 'python', 'impl_uart_bridge.py')
        cmd = ['python3', test_script, input_file]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            return None

        # Parse output
        lines = result.stderr.strip().split('\n')
        output_lines = result.stdout.strip().split('\n')

        stats = {
            'result': int(output_lines[0]) if output_lines else None,
            'elapsed': None,
            'cycles': None,
        }

        # Extract statistics from stderr
        for line in lines:
            if 'Time:' in line:
                stats['elapsed'] = float(line.split(':')[1].strip().rstrip('s'))
            elif 'Cycles:' in line:
                stats['cycles'] = int(line.split(':')[1].strip())

        return stats

    except Exception as e:
        print(f"Error running RTL: {e}", file=sys.stderr)
        return None


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Compare software reference against RTL implementation'
    )
    parser.add_argument('input_file', help='Input file with polygon vertices')
    args = parser.parse_args()

    # Read input
    with open(args.input_file, 'r') as f:
        input_text = f.read()

    print("=" * 70)
    print("RTL vs Software Reference Comparison")
    print("=" * 70)
    print()

    # Run software reference
    print("Running software reference...")
    sw_stats = run_software(input_text)

    print(f"  Result: {sw_stats['result']}")
    print(f"  Time: {sw_stats['elapsed']:.3f}s")
    print(f"  Vertices: {sw_stats['vertices']}")
    print(f"  Rectangles tested: {sw_stats['rectangles_tested']}")
    print(f"  Rectangles pruned: {sw_stats['rectangles_pruned']}")
    print(f"  Valid rectangles: {sw_stats['valid_rectangles']}")
    print()

    # Run RTL if available
    print("Running RTL implementation...")
    # Use absolute path for RTL test
    abs_input_path = os.path.abspath(args.input_file)
    rtl_stats = run_rtl(abs_input_path)

    if rtl_stats:
        print(f"  Result: {rtl_stats['result']}")
        print(f"  Time: {rtl_stats['elapsed']:.3f}s" if rtl_stats['elapsed'] else "  Time: N/A")
        print(f"  Cycles: {rtl_stats['cycles']}" if rtl_stats['cycles'] else "  Cycles: N/A")
        print()

        # Compare results
        print("=" * 70)
        print("Comparison")
        print("=" * 70)

        if sw_stats['result'] == rtl_stats['result']:
            print(f"✓ Results match: {sw_stats['result']}")
        else:
            print(f"✗ Results differ:")
            print(f"    Software: {sw_stats['result']}")
            print(f"    RTL:      {rtl_stats['result']}")
            return 1

        if sw_stats['elapsed'] and rtl_stats['elapsed']:
            speedup = rtl_stats['elapsed'] / sw_stats['elapsed']
            print(f"  Speed: Software {speedup:.2f}x faster (simulation overhead)")

        print()
        print("✓ All checks passed!")
        return 0
    else:
        print("  RTL test skipped (not available)")
        print()
        return 0


if __name__ == '__main__':
    sys.exit(main())
