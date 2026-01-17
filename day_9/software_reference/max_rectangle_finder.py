#!/usr/bin/env python3
"""
Software Reference Implementation of MaxRectangleFinder Algorithm

This is a Python reference implementation that mirrors the RTL algorithm.
It finds the maximum area axis-aligned rectangle that is completely
contained within a rectilinear polygon.

Algorithm:
1. Input polygon vertices (x,y coordinates)
2. Scale coordinates by 4 (to match RTL fixed-point math)
3. Generate all vertex pair combinations as rectangle candidates
4. For each candidate rectangle:
   a. Compute axis-aligned bounding rectangle from vertex pair
   b. Validate using 4 checks (vertex inside, edge intersection, ray casting, boundary)
   c. Track maximum valid rectangle area
5. Return area (with formula: (width+4)*(height+4)/16 to match RTL)
"""

import sys
from typing import List, Tuple, Optional


class MaxRectangleFinder:
    """Software reference for MaxRectangleFinder RTL module."""

    # Coordinate scaling factor (matches RTL SCALE_SHIFT=2)
    SCALE_FACTOR = 4

    def __init__(self):
        self.vertices = []
        self.max_area = 0
        self.rectangles_tested = 0
        self.rectangles_pruned = 0
        self.valid_rectangles_found = 0

    def add_vertex(self, x: int, y: int):
        """Add a vertex to the polygon (coordinates will be scaled internally)."""
        scaled_x = x * self.SCALE_FACTOR
        scaled_y = y * self.SCALE_FACTOR
        self.vertices.append((scaled_x, scaled_y))

    def find_max_rectangle(self) -> int:
        """
        Find the maximum rectangle area within the polygon.

        Returns:
            Maximum rectangle area (scaled and divided by 16 to match RTL output)
        """
        if len(self.vertices) < 3:
            return 0

        self.max_area = 0
        self.rectangles_tested = 0
        self.rectangles_pruned = 0
        self.valid_rectangles_found = 0

        num_vertices = len(self.vertices)

        # Generate all vertex pair combinations (i, j) where i < j
        for i in range(num_vertices):
            for j in range(i + 1, num_vertices):
                # Get the two vertices
                vi_x, vi_y = self.vertices[i]
                vj_x, vj_y = self.vertices[j]

                # Compute axis-aligned rectangle from vertex pair
                min_x = min(vi_x, vj_x)
                max_x = max(vi_x, vj_x)
                min_y = min(vi_y, vj_y)
                max_y = max(vi_y, vj_y)

                width = max_x - min_x
                height = max_y - min_y

                # Skip degenerate rectangles (zero width or height)
                if width == 0 or height == 0:
                    continue

                # Compute area with RTL formula: (width+4)*(height+4)
                candidate_area = (width + 4) * (height + 4)

                # Area pruning: skip if can't beat current max
                if candidate_area <= self.max_area:
                    self.rectangles_pruned += 1
                    continue

                # Validate rectangle
                if self._validate_rectangle(min_x, min_y, width, height):
                    if candidate_area > self.max_area:
                        self.max_area = candidate_area
                    self.valid_rectangles_found += 1

                self.rectangles_tested += 1

        # Return area divided by 16 (to match RTL output scaling)
        return self.max_area >> 4

    def _validate_rectangle(self, rect_x: int, rect_y: int,
                           rect_width: int, rect_height: int) -> bool:
        """
        Validate if rectangle is completely contained within polygon.

        Uses 4 checks that mirror the RTL ValidateRectangle module:
        - CHECK 1: No polygon vertex strictly inside rectangle
        - CHECK 2: No polygon edge intersects shrunken rectangle boundary
        - CHECK 3: All 4 corners have odd ray-casting crossing count
        - CHECK 4: No corner lies on polygon boundary

        Args:
            rect_x, rect_y: Rectangle bottom-left corner
            rect_width, rect_height: Rectangle dimensions

        Returns:
            True if rectangle is valid (completely inside polygon)
        """
        # Rectangle bounds
        rect_x2 = rect_x + rect_width
        rect_y2 = rect_y + rect_height

        # Shrunken rectangle for CHECK 2 (shrink by 4 units)
        shrink_x1 = rect_x + 4
        shrink_x2 = rect_x2 - 4
        shrink_y1 = rect_y + 4
        shrink_y2 = rect_y2 - 4

        num_vertices = len(self.vertices)

        # Iterate through all polygon edges
        for edge_idx in range(num_vertices):
            # Current and next vertex (wrapping around)
            curr_x, curr_y = self.vertices[edge_idx]
            next_x, next_y = self.vertices[(edge_idx + 1) % num_vertices]

            # CHECK 1: Vertex strictly inside rectangle
            # A vertex is strictly inside if:
            # rect_x < vx < rect_x2 AND rect_y < vy < rect_y2
            if (rect_x < curr_x < rect_x2) and (rect_y < curr_y < rect_y2):
                return False  # Vertex inside - rectangle invalid

            # CHECK 2: Edge intersects shrunken rectangle boundary
            # Check if edge (curr -> next) intersects the shrunken rectangle
            if self._edge_intersects_rect(curr_x, curr_y, next_x, next_y,
                                         shrink_x1, shrink_y1, shrink_x2, shrink_y2):
                return False  # Edge intersects - rectangle invalid

        # CHECK 3 & 4: Validate all 4 corners
        # A corner is valid if: on_boundary OR odd_crossings
        corners = [
            (rect_x, rect_y),           # Bottom-left
            (rect_x2, rect_y),          # Bottom-right
            (rect_x, rect_y2),          # Top-left
            (rect_x2, rect_y2),         # Top-right
        ]

        for corner_x, corner_y in corners:
            # CHECK 4: Corner on polygon boundary
            on_boundary = self._point_on_polygon_boundary(corner_x, corner_y)

            # CHECK 3: Ray casting - count crossings
            crossings = self._ray_cast_crossings(corner_x, corner_y)
            odd_crossings = (crossings % 2 == 1)

            # Corner is valid if on boundary OR odd crossings
            if not (on_boundary or odd_crossings):
                return False  # Corner invalid - rectangle invalid

        # All checks passed - rectangle is valid
        return True

    def _edge_intersects_rect(self, x1: int, y1: int, x2: int, y2: int,
                              rect_x1: int, rect_y1: int,
                              rect_x2: int, rect_y2: int) -> bool:
        """
        Check if edge (x1,y1)->(x2,y2) intersects axis-aligned rectangle.

        For rectilinear polygons, edges are either horizontal or vertical,
        which simplifies the intersection test.
        """
        # Ensure edge endpoints are ordered
        if x1 > x2:
            x1, x2 = x2, x1
        if y1 > y2:
            y1, y2 = y2, y1

        # Horizontal edge
        if y1 == y2:
            edge_y = y1
            # Check if horizontal edge crosses any vertical rectangle boundary
            if rect_y1 < edge_y < rect_y2:
                # Check if edge overlaps horizontally with rectangle
                if not (x2 <= rect_x1 or x1 >= rect_x2):
                    return True

        # Vertical edge
        if x1 == x2:
            edge_x = x1
            # Check if vertical edge crosses any horizontal rectangle boundary
            if rect_x1 < edge_x < rect_x2:
                # Check if edge overlaps vertically with rectangle
                if not (y2 <= rect_y1 or y1 >= rect_y2):
                    return True

        return False

    def _point_on_polygon_boundary(self, px: int, py: int) -> bool:
        """
        Check if point (px, py) lies on any polygon edge.

        For rectilinear polygons, a point is on an edge if:
        - For horizontal edge: py == edge_y and min_x <= px <= max_x
        - For vertical edge: px == edge_x and min_y <= py <= max_y
        """
        num_vertices = len(self.vertices)

        for i in range(num_vertices):
            x1, y1 = self.vertices[i]
            x2, y2 = self.vertices[(i + 1) % num_vertices]

            # Horizontal edge
            if y1 == y2:
                if py == y1 and min(x1, x2) <= px <= max(x1, x2):
                    return True

            # Vertical edge
            if x1 == x2:
                if px == x1 and min(y1, y2) <= py <= max(y1, y2):
                    return True

        return False

    def _ray_cast_crossings(self, px: int, py: int) -> int:
        """
        Ray casting algorithm: count edge crossings from point to infinity.

        Matches RTL logic: ray from (px, py) to the right counts crossings
        with non-horizontal edges where edge_p1_x <= px and py in [ymin, ymax).

        Returns:
            Number of edge crossings
        """
        crossings = 0
        num_vertices = len(self.vertices)

        for i in range(num_vertices):
            x1, y1 = self.vertices[i]
            x2, y2 = self.vertices[(i + 1) % num_vertices]

            # Skip horizontal edges
            if y1 == y2:
                continue

            # Get y range [ymin, ymax]
            ymin = min(y1, y2)
            ymax = max(y1, y2)

            # Count crossing if: edge_p1_x <= px AND py in [ymin, ymax)
            if x1 <= px and ymin <= py < ymax:
                crossings += 1

        return crossings

    def get_statistics(self) -> dict:
        """Return algorithm statistics."""
        return {
            'vertices': len(self.vertices),
            'rectangles_tested': self.rectangles_tested,
            'rectangles_pruned': self.rectangles_pruned,
            'valid_rectangles': self.valid_rectangles_found,
            'max_area': self.max_area >> 4,  # Scaled output
        }


def parse_polygon_text(text: str) -> List[Tuple[int, int]]:
    """
    Parse polygon from text format.

    Format: "x,y\\nx,y\\n...\\n\\n" (empty line terminates)

    Args:
        text: Text with x,y coordinates per line

    Returns:
        List of (x, y) vertex tuples
    """
    vertices = []
    for line in text.strip().split('\n'):
        line = line.strip()
        if not line:
            break  # Empty line terminates polygon
        if ',' in line:
            x, y = line.split(',')
            vertices.append((int(x), int(y)))
    return vertices


def main():
    """Command-line interface for MaxRectangleFinder."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Find maximum rectangle within rectilinear polygon'
    )
    parser.add_argument('input_file', nargs='?', type=argparse.FileType('r'),
                       default=sys.stdin,
                       help='Input file with polygon vertices (default: stdin)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Print algorithm statistics')
    args = parser.parse_args()

    # Read input
    input_text = args.input_file.read()
    vertices = parse_polygon_text(input_text)

    if len(vertices) < 3:
        print("Error: Need at least 3 vertices", file=sys.stderr)
        return 1

    if args.verbose:
        print(f"Processing polygon with {len(vertices)} vertices", file=sys.stderr)

    # Find maximum rectangle
    finder = MaxRectangleFinder()
    for x, y in vertices:
        finder.add_vertex(x, y)

    max_area = finder.find_max_rectangle()

    # Output result
    print(max_area)

    if args.verbose:
        stats = finder.get_statistics()
        print(f"\nStatistics:", file=sys.stderr)
        print(f"  Vertices: {stats['vertices']}", file=sys.stderr)
        print(f"  Rectangles tested: {stats['rectangles_tested']}", file=sys.stderr)
        print(f"  Rectangles pruned: {stats['rectangles_pruned']}", file=sys.stderr)
        print(f"  Valid rectangles: {stats['valid_rectangles']}", file=sys.stderr)
        print(f"  Max area: {stats['max_area']}", file=sys.stderr)

    return 0


if __name__ == '__main__':
    sys.exit(main())
