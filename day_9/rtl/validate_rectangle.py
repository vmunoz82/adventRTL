import sys
import os

# Add project root to sys.path for imports
_script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _script_dir)

from amaranth import *
from amaranth.sim import Simulator
from amaranth.hdl.mem import Memory
from checks import VertexInRectangleCheck, EdgeIntersectionCheck, CornerValidationCheck


class ValidateRectangle(Elaboratable):
    """
    Polygon-rectangle validation unit with BRAM-based polygon storage.

    Validates whether an axis-aligned rectangle is completely contained
    within a rectilinear polygon using single-pass edge traversal.

    Architecture:
    - 5-state FSM with BRAM vertex storage
    - 4 parallel checks per edge (VRC, EIC, CV Ray-Cast, CV Boundary)
    - Early termination for CHECK 1/2 violations
    - Latency: num_vertices + 3 cycles

    Checks:
    - CHECK 1 (VRC): Polygon vertex strictly inside rectangle
    - CHECK 2 (EIC): Edge intersects shrunken rectangle
    - CHECK 3 (CV Ray-Cast): Ray-casting crossing count per corner
    - CHECK 4 (CV Boundary): Corner on polygon edge detection

    Parameters
    ----------
    coord_width : int
        Coordinate width in bits (16-32, default 20).
    max_vertices : int
        Maximum polygon vertices (3-8192, default 512).

    Interface
    ---------
    Inputs:
        rect_x, rect_y, rect_width, rect_height : Rectangle parameters
        num_vertices : Polygon vertex count
        load_mode, load_addr, load_data_x, load_data_y, load_wr : BRAM load
        start : Begin validation

    Outputs:
        busy, done : Status
        is_valid : Result (valid when done=1)
        check1_fail, check2_fail, check3_fail : Debug outputs
        debug_edges_processed : Edge counter for benchmarking
    """

    def __init__(self, coord_width: int = 20, max_vertices: int = 512):
        if coord_width < 16 or coord_width > 32:
            raise ValueError(f"coord_width must be 16-32 bits, got {coord_width}")
        if max_vertices < 3 or max_vertices > 8192:
            raise ValueError(f"max_vertices must be 3-8192, got {max_vertices}")

        self.coord_width = coord_width
        self.max_vertices = max_vertices
        self.addr_width = (max_vertices - 1).bit_length()

        # Rectangle parameters
        self.rect_x = Signal(coord_width)
        self.rect_y = Signal(coord_width)
        self.rect_width = Signal(coord_width)
        self.rect_height = Signal(coord_width)

        # Polygon parameters
        self.num_vertices = Signal(self.addr_width + 1)
        self.start_vertex = Signal(self.addr_width)  # Starting vertex for circular iteration

        # Memory load interface
        self.load_mode = Signal()
        self.load_addr = Signal(self.addr_width)
        self.load_data_x = Signal(coord_width)
        self.load_data_y = Signal(coord_width)
        self.load_wr = Signal()

        # Control interface
        self.start = Signal()
        self.busy = Signal()
        self.done = Signal()

        # Output interface
        self.is_valid = Signal()
        self.check1_fail = Signal()
        self.check2_fail = Signal()
        self.check3_fail = Signal()
        self.debug_edges_processed = Signal(self.addr_width + 1)
        self.validation_cycles = Signal(16)  # Cycles from start to done
        self.fail_edge_index = Signal(self.addr_width)  # Edge where CHECK1/2 failed

    def elaborate(self, platform):
        m = Module()

        # ===== BRAM for Polygon Vertices =====
        vertex_mem = Memory(width=2 * self.coord_width, depth=self.max_vertices, init=[])
        read_port = vertex_mem.read_port(domain="sync", transparent=False)
        write_port = vertex_mem.write_port(domain="sync")
        m.submodules.mem_read = read_port
        m.submodules.mem_write = write_port

        # ===== Memory Control =====
        current_vertex = Signal(self.addr_width)
        edge_counter = Signal(self.addr_width + 1)

        mem_data_x = Signal(self.coord_width)
        mem_data_y = Signal(self.coord_width)
        m.d.comb += [
            mem_data_x.eq(read_port.data[:self.coord_width]),
            mem_data_y.eq(read_port.data[self.coord_width:]),
        ]

        # Memory write
        m.d.comb += [
            write_port.addr.eq(self.load_addr),
            write_port.data.eq(Cat(self.load_data_x, self.load_data_y)),
            write_port.en.eq(self.load_wr & self.load_mode),
        ]

        # ===== Edge Registers =====
        edge_p1_x = Signal(self.coord_width)
        edge_p1_y = Signal(self.coord_width)
        edge_p2_x = Signal(self.coord_width)
        edge_p2_y = Signal(self.coord_width)

        # ===== Validation State =====
        crossings = [Signal(16, name=f'crossings_{i}') for i in range(4)]
        on_boundary = [Signal(name=f'on_boundary_{i}') for i in range(4)]
        check1_failed = Signal()
        check2_failed = Signal()
        cycle_counter = Signal(16)  # Count cycles from start to done

        # ===== Registered Rectangle Boundaries (pipelined for timing) =====
        rect_x2_reg = Signal(self.coord_width)
        rect_y2_reg = Signal(self.coord_width)

        # ===== Registered Rectangle Input Parameters (OPTIMIZATION #7) =====
        # Register rect inputs to break combinatorial path from finder's max_y_reg
        rect_x_reg = Signal(self.coord_width)
        rect_y_reg = Signal(self.coord_width)
        rect_width_reg = Signal(self.coord_width)
        rect_height_reg = Signal(self.coord_width)

        # ===== Registered Shrunk Rectangle Values (pipelined for timing) =====
        shrunk_x1_reg = Signal(self.coord_width)
        shrunk_x2_reg = Signal(self.coord_width)
        shrunk_y1_reg = Signal(self.coord_width)
        shrunk_y2_reg = Signal(self.coord_width)

        # ===== Registered Corner Coordinates (pipelined for timing) =====
        corner_x_reg = Array([Signal(self.coord_width) for _ in range(4)])
        corner_y_reg = Array([Signal(self.coord_width) for _ in range(4)])

        # ===== Registered Edge Min/Max Values (pipelined for timing) =====
        edge_ymin_reg = Signal(self.coord_width)
        edge_ymax_reg = Signal(self.coord_width)
        edge_xmin_reg = Signal(self.coord_width)
        edge_xmax_reg = Signal(self.coord_width)

        # ===== Check Violation Signals =====
        check1_violation = Signal()
        check2_violation = Signal()
        cv_crossing_inc = [Signal(name=f'cv_crossing_inc_{i}') for i in range(4)]
        cv_boundary_set = [Signal(name=f'cv_boundary_set_{i}') for i in range(4)]

        # ===== CHECK 1: VRC Module =====
        check1 = VertexInRectangleCheck(coord_width=self.coord_width)
        m.submodules.check1 = check1
        m.d.comb += [
            check1.edge_p1_x.eq(edge_p1_x),
            check1.edge_p1_y.eq(edge_p1_y),
            check1.rect_x.eq(rect_x_reg),  # Use registered value (OPTIMIZATION #7)
            check1.rect_y.eq(rect_y_reg),  # Use registered value (OPTIMIZATION #7)
            check1.rect_x2.eq(rect_x2_reg),  # Use registered value
            check1.rect_y2.eq(rect_y2_reg),  # Use registered value
            check1_violation.eq(check1.violation),
        ]

        # ===== CHECK 2: EIC Module =====
        check2 = EdgeIntersectionCheck(coord_width=self.coord_width)
        m.submodules.check2 = check2
        m.d.comb += [
            check2.edge_p1_x.eq(edge_p1_x),
            check2.edge_p1_y.eq(edge_p1_y),
            check2.edge_p2_x.eq(edge_p2_x),
            check2.edge_p2_y.eq(edge_p2_y),
            # Pass pre-computed shrunk rectangle values
            check2.shrunk_x1.eq(shrunk_x1_reg),
            check2.shrunk_x2.eq(shrunk_x2_reg),
            check2.shrunk_y1.eq(shrunk_y1_reg),
            check2.shrunk_y2.eq(shrunk_y2_reg),
            check2_violation.eq(check2.violation),
        ]

        # ===== CHECK 3+4: Corner Validation Modules =====
        for c in range(4):
            cv = CornerValidationCheck(coord_width=self.coord_width)
            m.submodules[f'cv_{c}'] = cv
            m.d.comb += [
                cv.edge_p1_x.eq(edge_p1_x),
                cv.edge_p1_y.eq(edge_p1_y),
                cv.edge_p2_x.eq(edge_p2_x),
                cv.edge_p2_y.eq(edge_p2_y),
                # Use pre-registered edge min/max values (timing optimization)
                cv.edge_ymin.eq(edge_ymin_reg),
                cv.edge_ymax.eq(edge_ymax_reg),
                cv.edge_xmin.eq(edge_xmin_reg),
                cv.edge_xmax.eq(edge_xmax_reg),
                # Use pre-registered corner coordinates (timing optimization)
                cv.corner_x.eq(corner_x_reg[c]),
                cv.corner_y.eq(corner_y_reg[c]),
                cv.on_boundary.eq(on_boundary[c]),
                cv_crossing_inc[c].eq(cv.crossing_inc),
                cv_boundary_set[c].eq(cv.boundary_set),
            ]

        # ===== Final Validation =====
        # Corner valid if on_boundary OR odd crossing count (LSB=1)
        all_corners_valid = Signal()
        m.d.comb += all_corners_valid.eq(
            (on_boundary[0] | crossings[0][0]) &
            (on_boundary[1] | crossings[1][0]) &
            (on_boundary[2] | crossings[2][0]) &
            (on_boundary[3] | crossings[3][0])
        )

        # Debug output
        m.d.comb += self.debug_edges_processed.eq(edge_counter)

        # ===== Next Address Computation (registered for timing) =====
        # Pre-compute next vertex one cycle early to reduce BRAM address setup path
        next_vertex = Signal(self.addr_width)
        next_vertex_reg = Signal(self.addr_width)  # Registered version for BRAM addressing
        m.d.comb += [
            next_vertex.eq(Mux(current_vertex + 1 < self.num_vertices, current_vertex + 1, 0)),
            # Use registered version for BRAM address (timing optimization)
            read_port.addr.eq(next_vertex_reg),
        ]

        # ===== FSM =====
        with m.FSM(domain="sync"):
            with m.State("IDLE"):
                m.d.comb += self.busy.eq(0)

                # Reset state
                for c in range(4):
                    m.d.sync += [crossings[c].eq(0), on_boundary[c].eq(0)]
                m.d.sync += [
                    check1_failed.eq(0),
                    check2_failed.eq(0),
                    self.done.eq(0),
                    self.check1_fail.eq(0),
                    self.check2_fail.eq(0),
                    self.check3_fail.eq(0),
                    self.is_valid.eq(0),
                    edge_counter.eq(0),
                    current_vertex.eq(0),
                    cycle_counter.eq(0),
                    self.fail_edge_index.eq(0),
                ]

                with m.If(self.start & ~self.load_mode):
                    # Start from specified vertex (circular iteration)
                    # Pre-compute next vertex for timing (wrap-around handled in computation)
                    next_v = Signal(self.addr_width)
                    m.d.comb += next_v.eq(Mux(self.start_vertex + 1 < self.num_vertices, self.start_vertex + 1, 0))
                    m.d.sync += [
                        current_vertex.eq(self.start_vertex),
                        cycle_counter.eq(1),
                        next_vertex_reg.eq(next_v),  # Register for BRAM address (timing optimization)
                        # OPTIMIZATION #7: Register rectangle inputs to break combinatorial path
                        rect_x_reg.eq(self.rect_x),
                        rect_y_reg.eq(self.rect_y),
                        rect_width_reg.eq(self.rect_width),
                        rect_height_reg.eq(self.rect_height),
                    ]
                    m.d.comb += read_port.addr.eq(self.start_vertex)
                    m.next = "INIT_FETCH_V1"

            with m.State("INIT_FETCH_V1"):
                m.d.comb += self.busy.eq(1)
                m.d.sync += [
                    edge_p1_x.eq(mem_data_x),
                    edge_p1_y.eq(mem_data_y),
                    current_vertex.eq(next_vertex),
                    next_vertex_reg.eq(next_vertex),  # Register for BRAM address (timing optimization)
                    cycle_counter.eq(cycle_counter + 1),
                ]
                m.d.comb += read_port.addr.eq(next_vertex)
                m.next = "INIT_FETCH_V2"

            with m.State("INIT_FETCH_V2"):
                m.d.comb += self.busy.eq(1)
                m.d.sync += [
                    edge_p2_x.eq(mem_data_x),
                    edge_p2_y.eq(mem_data_y),
                    current_vertex.eq(next_vertex),
                    next_vertex_reg.eq(next_vertex),  # Register for BRAM address (timing optimization)
                    edge_counter.eq(0),
                    cycle_counter.eq(cycle_counter + 1),
                    # Pre-compute and register rectangle boundaries (using registered rect inputs)
                    rect_x2_reg.eq(rect_x_reg + rect_width_reg),
                    rect_y2_reg.eq(rect_y_reg + rect_height_reg),
                    # Pre-compute and register shrunk rectangle values (using registered rect inputs)
                    shrunk_x1_reg.eq(rect_x_reg + 1),
                    shrunk_x2_reg.eq(rect_x_reg + rect_width_reg - 1),
                    shrunk_y1_reg.eq(rect_y_reg + 1),
                    shrunk_y2_reg.eq(rect_y_reg + rect_height_reg - 1),
                    # Pre-compute and register corner coordinates (using registered rect inputs)
                    corner_x_reg[0].eq(rect_x_reg),
                    corner_y_reg[0].eq(rect_y_reg),
                    corner_x_reg[1].eq(rect_x_reg + rect_width_reg),
                    corner_y_reg[1].eq(rect_y_reg),
                    corner_x_reg[2].eq(rect_x_reg + rect_width_reg),
                    corner_y_reg[2].eq(rect_y_reg + rect_height_reg),
                    corner_x_reg[3].eq(rect_x_reg),
                    corner_y_reg[3].eq(rect_y_reg + rect_height_reg),
                    # Initialize edge min/max for first edge (timing optimization)
                    # Use edge_p1 (set in INIT_FETCH_V1) and edge_p2 (just loaded)
                    edge_ymin_reg.eq(Mux(edge_p1_y < mem_data_y, edge_p1_y, mem_data_y)),
                    edge_ymax_reg.eq(Mux(edge_p1_y > mem_data_y, edge_p1_y, mem_data_y)),
                    edge_xmin_reg.eq(Mux(edge_p1_x < mem_data_x, edge_p1_x, mem_data_x)),
                    edge_xmax_reg.eq(Mux(edge_p1_x > mem_data_x, edge_p1_x, mem_data_x)),
                ]
                m.d.comb += read_port.addr.eq(next_vertex)
                m.next = "PROCESS_PIPELINE"

            with m.State("PROCESS_PIPELINE"):
                m.d.comb += self.busy.eq(1)

                # Count cycles in this state
                m.d.sync += cycle_counter.eq(cycle_counter + 1)

                with m.If(check1_violation | check2_violation):
                    # Early termination: capture which edge failed
                    # fail_vertex is the start of the failing edge (P1's index)
                    # Since current_vertex points ahead, we go back
                    fail_vertex = Signal(self.addr_width)
                    m.d.comb += fail_vertex.eq(
                        Mux(current_vertex < 2,
                            self.num_vertices + current_vertex - 2,
                            current_vertex - 2)
                    )
                    m.d.sync += [
                        check1_failed.eq(check1_violation),
                        check2_failed.eq(check2_violation),
                        self.fail_edge_index.eq(fail_vertex),
                    ]
                    m.next = "FINALIZE"
                with m.Else():
                    # Update crossing counters and boundary flags
                    for c in range(4):
                        with m.If(cv_crossing_inc[c]):
                            m.d.sync += crossings[c].eq(crossings[c] + 1)
                        with m.If(cv_boundary_set[c]):
                            m.d.sync += on_boundary[c].eq(1)

                    m.d.sync += edge_counter.eq(edge_counter + 1)

                    with m.If(edge_counter >= self.num_vertices):
                        m.next = "FINALIZE"
                    with m.Else():
                        # Slide edge window and register min/max for next iteration
                        m.d.sync += [
                            edge_p1_x.eq(edge_p2_x),
                            edge_p1_y.eq(edge_p2_y),
                            edge_p2_x.eq(mem_data_x),
                            edge_p2_y.eq(mem_data_y),
                            current_vertex.eq(next_vertex),
                            next_vertex_reg.eq(next_vertex),  # Register for BRAM address (timing optimization)
                            # Register edge min/max (timing optimization - use CURRENT edge_p1/edge_p2)
                            edge_ymin_reg.eq(Mux(edge_p1_y < edge_p2_y, edge_p1_y, edge_p2_y)),
                            edge_ymax_reg.eq(Mux(edge_p1_y > edge_p2_y, edge_p1_y, edge_p2_y)),
                            edge_xmin_reg.eq(Mux(edge_p1_x < edge_p2_x, edge_p1_x, edge_p2_x)),
                            edge_xmax_reg.eq(Mux(edge_p1_x > edge_p2_x, edge_p1_x, edge_p2_x)),
                        ]
                        m.d.comb += read_port.addr.eq(next_vertex)

            with m.State("FINALIZE"):
                m.d.comb += self.busy.eq(0)

                # Reset next_vertex_reg to ensure clean start for next validation
                m.d.sync += next_vertex_reg.eq(0)

                with m.If(check1_failed | check2_failed):
                    m.d.sync += [
                        self.is_valid.eq(0),
                        self.check1_fail.eq(check1_failed),
                        self.check2_fail.eq(check2_failed),
                        self.check3_fail.eq(0),
                    ]
                with m.Else():
                    m.d.sync += [
                        self.is_valid.eq(all_corners_valid),
                        self.check1_fail.eq(0),
                        self.check2_fail.eq(0),
                        self.check3_fail.eq(~all_corners_valid),
                    ]

                m.d.sync += [
                    self.done.eq(1),
                    self.validation_cycles.eq(cycle_counter + 1),  # +1 for FINALIZE cycle
                ]
                m.next = "IDLE"

        return m
