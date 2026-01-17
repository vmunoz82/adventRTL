#!/usr/bin/env python3
"""
Validation check modules for ValidateRectangle.

Contains 3 validation checks:
- CHECK 1: VRC (Vertex-in-Rectangle Checker)
- CHECK 2: EIC (Edge Intersection Checker)
- CHECK 3+4: CornerValidationCheck (CV Ray-Casting + Boundary combined)
"""

from amaranth import *


class VertexInRectangleCheck(Elaboratable):
    """
    CHECK 1: Vertex-in-Rectangle Checker (VRC)

    Detects if polygon vertex P1 is strictly inside rectangle (not on boundary).
    Violation triggers early termination.

    Inputs: edge_p1_x/y, rect_x/y/x2/y2
    Outputs: violation (1-bit)
    """

    def __init__(self, coord_width: int = 20):
        self.coord_width = coord_width

        # Inputs
        self.edge_p1_x = Signal(coord_width)
        self.edge_p1_y = Signal(coord_width)
        self.rect_x = Signal(coord_width)
        self.rect_y = Signal(coord_width)
        self.rect_x2 = Signal(coord_width)
        self.rect_y2 = Signal(coord_width)

        # Outputs
        self.violation = Signal()

    def elaborate(self, platform):
        m = Module()

        # Vertex is strictly inside if: inside bounds AND not on any edge
        not_on_boundary = (
            (self.edge_p1_x != self.rect_x) &
            (self.edge_p1_x != self.rect_x2) &
            (self.edge_p1_y != self.rect_y) &
            (self.edge_p1_y != self.rect_y2)
        )

        inside = (
            (self.edge_p1_x > self.rect_x) &
            (self.edge_p1_x < self.rect_x2) &
            (self.edge_p1_y > self.rect_y) &
            (self.edge_p1_y < self.rect_y2)
        )

        m.d.comb += self.violation.eq(not_on_boundary & inside)

        return m


class EdgeIntersectionCheck(Elaboratable):
    """
    CHECK 2: Edge Intersection Checker (EIC)

    Checks if polygon edge intersects shrunken rectangle.
    Only checks vertical/horizontal edges (rectilinear polygon).

    Inputs: edge_p1/p2 x/y, shrunk rectangle coordinates
    Outputs: violation (1-bit)
    """

    def __init__(self, coord_width: int = 20):
        self.coord_width = coord_width

        # Inputs
        self.edge_p1_x = Signal(coord_width)
        self.edge_p1_y = Signal(coord_width)
        self.edge_p2_x = Signal(coord_width)
        self.edge_p2_y = Signal(coord_width)
        # Pre-computed shrunk rectangle values (for better timing)
        self.shrunk_x1 = Signal(coord_width)
        self.shrunk_x2 = Signal(coord_width)
        self.shrunk_y1 = Signal(coord_width)
        self.shrunk_y2 = Signal(coord_width)

        # Outputs
        self.violation = Signal()

    def elaborate(self, platform):
        m = Module()

        # Edge orientation
        is_vertical = Signal()
        is_horizontal = Signal()
        m.d.comb += [
            is_vertical.eq(self.edge_p1_x == self.edge_p2_x),
            is_horizontal.eq(self.edge_p1_y == self.edge_p2_y),
        ]

        # Edge Y range (for vertical edges)
        eymin = Mux(self.edge_p1_y < self.edge_p2_y, self.edge_p1_y, self.edge_p2_y)
        eymax = Mux(self.edge_p1_y > self.edge_p2_y, self.edge_p1_y, self.edge_p2_y)

        # Edge X range (for horizontal edges)
        exmin = Mux(self.edge_p1_x < self.edge_p2_x, self.edge_p1_x, self.edge_p2_x)
        exmax = Mux(self.edge_p1_x > self.edge_p2_x, self.edge_p1_x, self.edge_p2_x)

        # Vertical edge crosses horizontal rectangle side
        v_intersects = (
            is_vertical &
            (eymin < self.shrunk_y1) & (self.shrunk_y1 < eymax) &
            (self.shrunk_x1 < self.edge_p1_x) & (self.edge_p1_x < self.shrunk_x2)
        )

        # Horizontal edge crosses vertical rectangle side
        h_intersects = (
            is_horizontal &
            (exmin < self.shrunk_x1) & (self.shrunk_x1 < exmax) &
            (self.shrunk_y1 < self.edge_p1_y) & (self.edge_p1_y < self.shrunk_y2)
        )

        m.d.comb += self.violation.eq(v_intersects | h_intersects)

        return m


class CornerValidationCheck(Elaboratable):
    """
    CHECK 3+4: Combined Corner Validation (Ray-Casting + Boundary)

    For a single rectangle corner, determines:
    - crossing_inc: Does this edge contribute a ray-casting crossing?
    - boundary_set: Is corner exactly on this edge?

    Combines CHECK 3 (ray-casting) and CHECK 4 (boundary) to share
    common ymin/ymax computation.

    Inputs: edge_p1/p2 x/y, edge_ymin/ymax/xmin/xmax (pre-registered for timing),
            corner_x/y, on_boundary
    Outputs: crossing_inc, boundary_set
    """

    def __init__(self, coord_width: int = 20):
        self.coord_width = coord_width

        # Inputs
        self.edge_p1_x = Signal(coord_width)
        self.edge_p1_y = Signal(coord_width)
        self.edge_p2_x = Signal(coord_width)
        self.edge_p2_y = Signal(coord_width)
        # Pre-registered edge min/max values (for better timing)
        self.edge_ymin = Signal(coord_width)
        self.edge_ymax = Signal(coord_width)
        self.edge_xmin = Signal(coord_width)
        self.edge_xmax = Signal(coord_width)
        self.corner_x = Signal(coord_width)
        self.corner_y = Signal(coord_width)
        self.on_boundary = Signal()

        # Outputs
        self.crossing_inc = Signal()
        self.boundary_set = Signal()

    def elaborate(self, platform):
        m = Module()

        # Skip computation if already on boundary
        active = ~self.on_boundary

        # Compute edge min/max values combinatorially from edge_p1/p2
        # (Pre-registered values were causing 1-cycle offset bug)
        ymin = Mux(self.edge_p1_y < self.edge_p2_y, self.edge_p1_y, self.edge_p2_y)
        ymax = Mux(self.edge_p1_y > self.edge_p2_y, self.edge_p1_y, self.edge_p2_y)
        xmin = Mux(self.edge_p1_x < self.edge_p2_x, self.edge_p1_x, self.edge_p2_x)
        xmax = Mux(self.edge_p1_x > self.edge_p2_x, self.edge_p1_x, self.edge_p2_x)

        # Edge orientation
        is_vertical = self.edge_p1_x == self.edge_p2_x
        is_horizontal = self.edge_p1_y == self.edge_p2_y

        # === CHECK 3: Ray-Casting ===
        # Count crossing if: non-horizontal, p1.x <= corner.x, corner.y in [ymin, ymax)
        ray_cast_hit = (
            ~is_horizontal &
            (self.edge_p1_x <= self.corner_x) &
            (self.corner_y >= ymin) &
            (self.corner_y < ymax)
        )
        m.d.comb += self.crossing_inc.eq(active & ray_cast_hit)

        # === CHECK 4: Boundary ===
        # Vertical edge: corner.x == edge.x AND corner.y in [ymin, ymax]
        on_v_edge = (
            is_vertical &
            (self.corner_x == self.edge_p1_x) &
            (self.corner_y >= ymin) &
            (self.corner_y <= ymax)
        )

        # Horizontal edge: corner.y == edge.y AND corner.x in [xmin, xmax]
        on_h_edge = (
            is_horizontal &
            (self.corner_y == self.edge_p1_y) &
            (self.corner_x >= xmin) &
            (self.corner_x <= xmax)
        )

        m.d.comb += self.boundary_set.eq(active & (on_v_edge | on_h_edge))

        return m
