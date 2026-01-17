#!/usr/bin/env python3
"""
Maximum Rectangle Finder - Wrapper for ValidateRectangle

Processes a stream of polygon vertices and finds the maximum area
rectangle that is completely contained within the polygon.

Architecture:
- Streams in polygon vertices
- Generates all vertex pair combinations as candidate rectangles
- Validates each using ValidateRectangle module
- Tracks and outputs maximum valid rectangle area

Optimizations:
- Single polygon load at search start
- Area pruning (skip candidates that can't beat current max)
- Pipelined vertex prefetch during validation
- Merged FSM states for reduced latency

Parameters
----------
coord_width : int
    Coordinate width in bits (16-32, default 20).
max_vertices : int
    Maximum polygon vertices (3-8192, default 1024).

Interface
---------
Inputs:
    vertex_x, vertex_y : Vertex coordinates (streaming)
    vertex_valid : Vertex data valid strobe
    vertex_last : Marks final vertex in polygon
    start_search : Begin rectangle search

Outputs:
    busy, done : Status signals
    valid : At least one valid rectangle found
    max_area : Maximum area of valid rectangles
    rectangles_tested : Debug counter
    vertices_loaded : Debug counter
"""

import sys
import os

# Add project root to sys.path for imports
_script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _script_dir)

from amaranth import *
from validate_rectangle import ValidateRectangle


class MaxRectangleFinder(Elaboratable):
    def __init__(self, coord_width: int = 20, max_vertices: int = 1024):
        if coord_width < 16 or coord_width > 32:
            raise ValueError(f"coord_width must be 16-32 bits, got {coord_width}")
        if max_vertices < 3 or max_vertices > 8192:
            raise ValueError(f"max_vertices must be 3-8192, got {max_vertices}")

        self.coord_width = coord_width
        self.max_vertices = max_vertices
        self.addr_width = (max_vertices - 1).bit_length()

        # Vertex streaming interface
        self.vertex_x = Signal(coord_width)
        self.vertex_y = Signal(coord_width)
        self.vertex_valid = Signal()
        self.vertex_last = Signal()

        # Control interface
        self.start_search = Signal()
        self.busy = Signal()
        self.done = Signal()

        # Output interface
        self.valid = Signal()
        self.max_area = Signal(2 * coord_width)

        # Debug outputs (directly connected, not just at COMPLETE)
        self.rectangles_tested = Signal(2 * self.addr_width)
        self.rectangles_pruned = Signal(2 * self.addr_width)
        self.vertices_loaded = Signal(self.addr_width + 1)
        self.validation_cycles = Signal(32)  # Total cycles spent in validation
        self.debug_state = Signal(4)
        self.debug_num_vertices = Signal(self.addr_width + 1)
        self.debug_rect_count = Signal(2 * self.addr_width)
        self.debug_max_area = Signal(2 * self.coord_width)

    def elaborate(self, platform):
        m = Module()

        # ===== Vertex Storage BRAM =====
        from amaranth.hdl.mem import Memory
        vertex_mem = Memory(width=2 * self.coord_width, depth=self.max_vertices, init=[])
        read_port = vertex_mem.read_port(domain="sync", transparent=False)
        write_port = vertex_mem.write_port(domain="sync")
        m.submodules.vertex_mem_read = read_port
        m.submodules.vertex_mem_write = write_port

        # ===== ValidateRectangle Instance =====
        validator = ValidateRectangle(coord_width=self.coord_width, max_vertices=self.max_vertices)
        m.submodules.validator = validator

        # ===== State Registers =====
        num_vertices = Signal(self.addr_width + 1)
        write_addr = Signal(self.addr_width)

        # Rectangle generation counters
        rect_i = Signal(self.addr_width + 1)
        rect_j = Signal(self.addr_width + 1)

        # Polygon loading counter
        poly_load_addr = Signal(self.addr_width)

        # Pruning counter
        pruned_count = Signal(2 * self.addr_width)

        # Rectangle candidate registers
        cand_x = Signal(self.coord_width)
        cand_y = Signal(self.coord_width)
        cand_width = Signal(self.coord_width)
        cand_height = Signal(self.coord_width)
        cand_area = Signal(2 * self.coord_width)  # OPTIMIZATION #8: Pre-compute area

        # Vertex pair values
        vertex_i_x = Signal(self.coord_width)
        vertex_i_y = Signal(self.coord_width)
        vertex_j_x = Signal(self.coord_width)
        vertex_j_y = Signal(self.coord_width)

        # Registered min/max values (pipelined for timing)
        min_x_reg = Signal(self.coord_width)
        max_x_reg = Signal(self.coord_width)
        min_y_reg = Signal(self.coord_width)
        max_y_reg = Signal(self.coord_width)

        # Registered width/height for timing (OPTIMIZATION #9)
        width_reg = Signal(self.coord_width)
        height_reg = Signal(self.coord_width)

        # Results tracking
        max_area_reg = Signal(2 * self.coord_width)
        valid_found = Signal()
        rect_count = Signal(2 * self.addr_width)
        validation_cycles_reg = Signal(32)
        start_vertex_reg = Signal(self.addr_width)  # For circular edge iteration optimization

        # Pipeline registers for prefetching
        # prefetch_state: 0=idle, 1=addr_set (waiting for data), 2=captured
        prefetch_state = Signal(2)
        prefetched_x = Signal(self.coord_width)
        prefetched_y = Signal(self.coord_width)

        # Memory read helpers
        mem_x = Signal(self.coord_width)
        mem_y = Signal(self.coord_width)
        m.d.comb += [
            mem_x.eq(read_port.data[:self.coord_width]),
            mem_y.eq(read_port.data[self.coord_width:]),
        ]

        # Default validator inputs (can be overridden in states)
        m.d.comb += [
            validator.load_mode.eq(0),
            validator.load_wr.eq(0),
            validator.start.eq(0),
            validator.rect_x.eq(cand_x),
            validator.rect_y.eq(cand_y),
            validator.rect_width.eq(cand_width),
            validator.rect_height.eq(cand_height),
            validator.num_vertices.eq(num_vertices),
            validator.start_vertex.eq(start_vertex_reg),  # Circular iteration optimization
            validator.load_addr.eq(0),
            validator.load_data_x.eq(0),
            validator.load_data_y.eq(0),
        ]

        # ===== FSM =====
        with m.FSM(domain="sync") as fsm:
            m.d.comb += [
                self.debug_state.eq(fsm.state),
                self.debug_num_vertices.eq(num_vertices),
                self.debug_rect_count.eq(rect_count),
                self.debug_max_area.eq(max_area_reg),
            ]

            # ===== VERTEX LOADING PHASE =====
            with m.State("IDLE"):
                m.d.comb += self.busy.eq(0)

                with m.If(self.vertex_valid):
                    m.d.sync += [
                        self.done.eq(0),
                        write_port.addr.eq(0),
                        write_port.data.eq(Cat(self.vertex_x, self.vertex_y)),
                        write_port.en.eq(1),
                        write_addr.eq(1),
                        num_vertices.eq(1),
                    ]
                    m.next = "LOAD_VERTICES"
                with m.Else():
                    m.d.sync += [
                        self.done.eq(0),
                        write_port.en.eq(0),
                        write_addr.eq(0),
                        num_vertices.eq(0),
                    ]

            with m.State("LOAD_VERTICES"):
                m.d.comb += self.busy.eq(0)

                with m.If(self.vertex_valid):
                    m.d.sync += [
                        write_port.addr.eq(write_addr),
                        write_port.data.eq(Cat(self.vertex_x, self.vertex_y)),
                        write_port.en.eq(1),
                        write_addr.eq(write_addr + 1),
                        num_vertices.eq(write_addr + 1),
                    ]

                    with m.If(self.vertex_last):
                        m.d.sync += write_port.en.eq(0)
                        m.next = "WAIT_START"
                with m.Else():
                    m.d.sync += write_port.en.eq(0)

            with m.State("WAIT_START"):
                m.d.comb += self.busy.eq(0)
                m.d.sync += write_port.en.eq(0)

                with m.If(self.start_search):
                    m.d.sync += [
                        rect_i.eq(0),
                        rect_j.eq(1),
                        rect_count.eq(0),
                        pruned_count.eq(0),
                        max_area_reg.eq(0),
                        valid_found.eq(0),
                        poly_load_addr.eq(0),
                        validation_cycles_reg.eq(0),
                        start_vertex_reg.eq(0),
                    ]
                    m.d.comb += read_port.addr.eq(0)
                    m.next = "LOAD_POLY_ONCE"

            # ===== POLYGON LOADING (ONCE) =====
            with m.State("LOAD_POLY_ONCE"):
                m.d.comb += self.busy.eq(1)

                # Write vertex to ValidateRectangle memory
                m.d.comb += [
                    validator.load_mode.eq(1),
                    validator.load_addr.eq(poly_load_addr),
                    validator.load_data_x.eq(mem_x),
                    validator.load_data_y.eq(mem_y),
                    validator.load_wr.eq(1),
                ]

                m.d.sync += poly_load_addr.eq(poly_load_addr + 1)

                with m.If(poly_load_addr == num_vertices - 1):
                    m.d.comb += read_port.addr.eq(0)
                    m.next = "INIT_SEARCH"
                with m.Else():
                    m.d.comb += read_port.addr.eq(poly_load_addr + 1)

            # ===== SEARCH PHASE =====
            with m.State("INIT_SEARCH"):
                m.d.comb += self.busy.eq(1)
                m.d.sync += [
                    vertex_i_x.eq(mem_x),
                    vertex_i_y.eq(mem_y),
                ]
                m.d.comb += read_port.addr.eq(1)
                m.next = "FETCH_J"

            with m.State("FETCH_J"):
                m.d.comb += self.busy.eq(1)
                m.d.sync += [
                    vertex_j_x.eq(mem_x),
                    vertex_j_y.eq(mem_y),
                ]
                m.next = "REGISTER_PAIR"

            # REGISTER_PAIR: Register min/max values and compute width/height for timing
            # OPTIMIZATION #9: Pre-register width/height to eliminate subtractor from validator path
            with m.State("REGISTER_PAIR"):
                m.d.comb += self.busy.eq(1)
                # Compute min/max values combinationall
                min_x = Mux(vertex_i_x < vertex_j_x, vertex_i_x, vertex_j_x)
                max_x = Mux(vertex_i_x > vertex_j_x, vertex_i_x, vertex_j_x)
                min_y = Mux(vertex_i_y < vertex_j_y, vertex_i_y, vertex_j_y)
                max_y = Mux(vertex_i_y > vertex_j_y, vertex_i_y, vertex_j_y)
                # Compute width/height from min/max (combinatorial, same cycle)
                width = max_x - min_x
                height = max_y - min_y
                # Register everything
                m.d.sync += [
                    min_x_reg.eq(min_x),
                    max_x_reg.eq(max_x),
                    min_y_reg.eq(min_y),
                    max_y_reg.eq(max_y),
                    width_reg.eq(width),  # Register width (OPTIMIZATION #9)
                    height_reg.eq(height),  # Register height (OPTIMIZATION #9)
                    prefetch_state.eq(0),  # Reset prefetch state
                ]
                m.next = "GENERATE_RECT"

            with m.State("GENERATE_RECT"):
                m.d.comb += self.busy.eq(1)

                # OPTIMIZATION #9: Use registered width/height (no combinatorial subtractor)
                width = width_reg
                height = height_reg

                # Area formula: (width+4)*(height+4) for inclusive bounds with SCALE_FACTOR=4
                candidate_area = (width + 4) * (height + 4)

                m.d.sync += [
                    cand_x.eq(min_x_reg),
                    cand_y.eq(min_y_reg),
                    cand_width.eq(width),
                    cand_height.eq(height),
                    cand_area.eq(candidate_area),  # Register area
                ]

                with m.If((width == 0) | (height == 0)):
                    m.next = "NEXT_RECT"
                with m.Elif(candidate_area <= max_area_reg):
                    m.d.sync += pruned_count.eq(pruned_count + 1)
                    m.next = "NEXT_RECT"
                with m.Else():
                    # Start validation immediately using registered values
                    m.d.comb += [
                        validator.rect_x.eq(min_x_reg),
                        validator.rect_y.eq(min_y_reg),
                        validator.rect_width.eq(width_reg),  # Use registered width (OPTIMIZATION #9)
                        validator.rect_height.eq(height_reg),  # Use registered height (OPTIMIZATION #9)
                        validator.start.eq(1),
                    ]
                    m.next = "VALIDATE_WAIT"

            with m.State("VALIDATE_WAIT"):
                m.d.comb += self.busy.eq(1)

                # Compute next indices combinationally
                will_need_new_i = (rect_j + 1 >= num_vertices)
                next_j_val = rect_j + 1
                next_i_val = rect_i + 1

                # Prefetch next vertex while waiting (PIPELINE OPTIMIZATION)
                # State machine: 0=idle, 1=addr_set, 2=captured
                with m.If(prefetch_state == 0):
                    with m.If(will_need_new_i):
                        # Need to fetch new i vertex
                        with m.If(next_i_val >= num_vertices - 1):
                            # Will complete after this validation - skip prefetch
                            m.d.sync += prefetch_state.eq(2)
                        with m.Else():
                            m.d.comb += read_port.addr.eq(next_i_val)
                            m.d.sync += prefetch_state.eq(1)
                    with m.Else():
                        # Just fetch next j
                        m.d.comb += read_port.addr.eq(next_j_val)
                        m.d.sync += prefetch_state.eq(1)

                with m.Elif(prefetch_state == 1):
                    # Capture data (one cycle after addr was set)
                    m.d.sync += [
                        prefetched_x.eq(mem_x),
                        prefetched_y.eq(mem_y),
                        prefetch_state.eq(2),
                    ]

                # State 2: captured, just wait for validator

                with m.If(validator.done):
                    m.d.sync += [
                        rect_count.eq(rect_count + 1),
                        # Accumulate validator's cycle count
                        validation_cycles_reg.eq(validation_cycles_reg + validator.validation_cycles),
                    ]

                    # Merged UPDATE_MAX: Update max in same cycle if valid
                    with m.If(validator.is_valid):
                        # OPTIMIZATION #8: Use pre-registered area instead of combinatorial computation
                        with m.If(cand_area > max_area_reg):
                            m.d.sync += max_area_reg.eq(cand_area)
                        m.d.sync += [
                            valid_found.eq(1),
                            start_vertex_reg.eq(0),  # Reset after valid rectangle
                        ]
                    with m.Elif(validator.check1_fail | validator.check2_fail):
                        # Early termination: use fail_edge for next validation
                        m.d.sync += start_vertex_reg.eq(validator.fail_edge_index)
                    with m.Else():
                        # CHECK3 failed (tested all edges): reset to beginning
                        m.d.sync += start_vertex_reg.eq(0)

                    m.next = "NEXT_RECT"

            with m.State("NEXT_RECT"):
                m.d.comb += self.busy.eq(1)

                # Compute next indices combinationally
                will_need_new_i = (rect_j + 1 >= num_vertices)
                next_j_val = rect_j + 1
                next_i_val = rect_i + 1

                with m.If(will_need_new_i):
                    # Moving to next i
                    with m.If(next_i_val >= num_vertices - 1):
                        m.next = "COMPLETE"
                    with m.Else():
                        m.d.sync += [
                            rect_i.eq(next_i_val),
                            rect_j.eq(next_i_val + 1),
                        ]
                        # Use prefetched i if available, otherwise fetch
                        with m.If(prefetch_state == 2):
                            m.d.sync += [
                                vertex_i_x.eq(prefetched_x),
                                vertex_i_y.eq(prefetched_y),
                            ]
                            m.d.comb += read_port.addr.eq(next_i_val + 1)
                            m.next = "FETCH_J"
                        with m.Else():
                            m.d.comb += read_port.addr.eq(next_i_val)
                            m.next = "FETCH_I"
                with m.Else():
                    # Same i, next j
                    m.d.sync += rect_j.eq(next_j_val)
                    with m.If(prefetch_state == 2):
                        # Use prefetched j vertex
                        m.d.sync += [
                            vertex_j_x.eq(prefetched_x),
                            vertex_j_y.eq(prefetched_y),
                        ]
                        m.next = "REGISTER_PAIR"  # Go through REGISTER_PAIR to update min/max
                    with m.Else():
                        # Need to fetch j
                        m.d.comb += read_port.addr.eq(next_j_val)
                        m.next = "FETCH_J"

            with m.State("FETCH_I"):
                m.d.comb += self.busy.eq(1)
                m.d.sync += [
                    vertex_i_x.eq(mem_x),
                    vertex_i_y.eq(mem_y),
                ]
                m.d.comb += read_port.addr.eq(rect_j)
                m.next = "FETCH_J"

            with m.State("COMPLETE"):
                m.d.comb += self.busy.eq(0)
                m.d.sync += [
                    self.done.eq(1),
                    self.valid.eq(valid_found),
                    self.max_area.eq(max_area_reg),
                    self.rectangles_tested.eq(rect_count),
                    self.rectangles_pruned.eq(pruned_count),
                    self.vertices_loaded.eq(num_vertices),
                    self.validation_cycles.eq(validation_cycles_reg),
                ]
                m.next = "IDLE"

        return m


if __name__ == "__main__":
    import sys
    from amaranth.back import verilog

    output_path = sys.argv[1] if len(sys.argv) > 1 else "max_rectangle_finder.v"

    top = MaxRectangleFinder(coord_width=20, max_vertices=1024)
    v = verilog.convert(top, name="top", ports=[
        top.vertex_x, top.vertex_y, top.vertex_valid, top.vertex_last,
        top.start_search, top.busy, top.done, top.valid, top.max_area,
        top.rectangles_tested, top.rectangles_pruned, top.vertices_loaded,
        top.validation_cycles, top.debug_state, top.debug_num_vertices,
        top.debug_rect_count, top.debug_max_area
    ])

    with open(output_path, "w") as f:
        f.write(v)
    print(f"Generated {output_path}")
