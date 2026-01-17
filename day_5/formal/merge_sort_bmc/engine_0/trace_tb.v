`ifndef VERILATOR
module testbench;
  reg [4095:0] vcdfile;
  reg clock;
`else
module testbench(input clock, output reg genclock);
  initial genclock = 1;
`endif
  reg genclock = 1;
  reg [31:0] cycle = 0;
  reg [0:0] PI_start;
  reg [0:0] PI_valid_in;
  reg [7:0] PI_start_in;
  reg [7:0] PI_end_in;
  reg [2:0] PI_count_in;
  wire [0:0] PI_clk = clock;
  reg [0:0] PI_rst;
  top UUT (
    .start(PI_start),
    .valid_in(PI_valid_in),
    .start_in(PI_start_in),
    .end_in(PI_end_in),
    .count_in(PI_count_in),
    .clk(PI_clk),
    .rst(PI_rst)
  );
`ifndef VERILATOR
  initial begin
    if ($value$plusargs("vcd=%s", vcdfile)) begin
      $dumpfile(vcdfile);
      $dumpvars(0, testbench);
    end
    #5 clock = 0;
    while (genclock) begin
      #5 clock = 0;
      #5 clock = 1;
    end
  end
`endif
  initial begin
`ifndef VERILATOR
    #1;
`endif
    // UUT.$sample$s$done$sync$1 = 1'b0;
    UUT.completed = 1'b0;
    // UUT.dut.\$/ends_a_mem$rdreg[0]$q  = 2'b00;
    // UUT.dut.\$/ends_b_mem$rdreg[0]$q  = 2'b00;
    // UUT.dut.\$/starts_a_mem$rdreg[0]$q  = 2'b00;
    // UUT.dut.\$/starts_b_mem$rdreg[0]$q  = 2'b00;
    UUT.dut.block_start = 3'b000;
    UUT.dut.busy = 1'b0;
    UUT.dut.done = 1'b0;
    UUT.dut.end_out = 8'b00000000;
    UUT.dut.fsm_state = 4'b0000;
    UUT.dut.input_idx = 3'b000;
    UUT.dut.left_end = 8'b00000000;
    UUT.dut.left_idx = 3'b000;
    UUT.dut.left_limit = 3'b000;
    UUT.dut.left_start = 8'b00000000;
    UUT.dut.merge_width = 3'b000;
    UUT.dut.num_ranges = 3'b000;
    UUT.dut.out_idx = 3'b000;
    UUT.dut.output_idx = 3'b000;
    UUT.dut.right_end = 8'b00000000;
    UUT.dut.right_idx = 3'b000;
    UUT.dut.right_limit = 3'b000;
    UUT.dut.right_start = 8'b00000000;
    UUT.dut.start_out = 8'b00000000;
    UUT.dut.use_a_as_source = 1'b0;
    UUT.dut.valid_out = 1'b0;
    UUT.input_count = 3'b000;
    UUT.output_count = 3'b000;
    UUT.output_end_0 = 8'b00000000;
    UUT.output_end_1 = 8'b00000000;
    UUT.output_end_2 = 8'b00000000;
    UUT.output_end_3 = 8'b00000000;
    UUT.output_start_0 = 8'b00000000;
    UUT.output_start_1 = 8'b00000000;
    UUT.output_start_2 = 8'b00000000;
    UUT.output_start_3 = 8'b00000000;
    UUT.sort_started = 1'b0;
    UUT.dut.ends_a_mem[2'b00] = 8'b00000000;
    UUT.dut.ends_b_mem[2'b00] = 8'b00000000;
    UUT.dut.starts_a_mem[2'b00] = 8'b00000000;
    UUT.dut.starts_b_mem[2'b00] = 8'b00000000;

    // state 0
    PI_start = 1'b1;
    PI_valid_in = 1'b1;
    PI_start_in = 8'b00000000;
    PI_end_in = 8'b01000001;
    PI_count_in = 3'b001;
    PI_rst = 1'b0;
  end
  always @(posedge clock) begin
    // state 1
    if (cycle == 0) begin
      PI_start <= 1'b0;
      PI_valid_in <= 1'b0;
      PI_start_in <= 8'b00000001;
      PI_end_in <= 8'b00100000;
      PI_count_in <= 3'b010;
      PI_rst <= 1'b0;
    end

    // state 2
    if (cycle == 1) begin
      PI_start <= 1'b0;
      PI_valid_in <= 1'b0;
      PI_start_in <= 8'b00000000;
      PI_end_in <= 8'b01110000;
      PI_count_in <= 3'b010;
      PI_rst <= 1'b0;
    end

    // state 3
    if (cycle == 2) begin
      PI_start <= 1'b0;
      PI_valid_in <= 1'b0;
      PI_start_in <= 8'b00000000;
      PI_end_in <= 8'b00000000;
      PI_count_in <= 3'b100;
      PI_rst <= 1'b0;
    end

    // state 4
    if (cycle == 3) begin
      PI_start <= 1'b0;
      PI_valid_in <= 1'b0;
      PI_start_in <= 8'b10000011;
      PI_end_in <= 8'b01110000;
      PI_count_in <= 3'b100;
      PI_rst <= 1'b0;
    end

    // state 5
    if (cycle == 4) begin
      PI_start <= 1'b0;
      PI_valid_in <= 1'b0;
      PI_start_in <= 8'b00000000;
      PI_end_in <= 8'b01100000;
      PI_count_in <= 3'b001;
      PI_rst <= 1'b0;
    end

    // state 6
    if (cycle == 5) begin
      PI_start <= 1'b0;
      PI_valid_in <= 1'b0;
      PI_start_in <= 8'b00000110;
      PI_end_in <= 8'b01110000;
      PI_count_in <= 3'b010;
      PI_rst <= 1'b0;
    end

    // state 7
    if (cycle == 6) begin
      PI_start <= 1'b0;
      PI_valid_in <= 1'b0;
      PI_start_in <= 8'b00000000;
      PI_end_in <= 8'b01000001;
      PI_count_in <= 3'b100;
      PI_rst <= 1'b0;
    end

    // state 8
    if (cycle == 7) begin
      PI_start <= 1'b0;
      PI_valid_in <= 1'b0;
      PI_start_in <= 8'b01000000;
      PI_end_in <= 8'b00000000;
      PI_count_in <= 3'b010;
      PI_rst <= 1'b0;
    end

    // state 9
    if (cycle == 8) begin
      PI_start <= 1'b0;
      PI_valid_in <= 1'b0;
      PI_start_in <= 8'b01000000;
      PI_end_in <= 8'b00100000;
      PI_count_in <= 3'b010;
      PI_rst <= 1'b0;
    end

    // state 10
    if (cycle == 9) begin
      PI_start <= 1'b0;
      PI_valid_in <= 1'b0;
      PI_start_in <= 8'b00000000;
      PI_end_in <= 8'b00101010;
      PI_count_in <= 3'b010;
      PI_rst <= 1'b0;
    end

    // state 11
    if (cycle == 10) begin
      PI_start <= 1'b0;
      PI_valid_in <= 1'b0;
      PI_start_in <= 8'b00000000;
      PI_end_in <= 8'b00000000;
      PI_count_in <= 3'b100;
      PI_rst <= 1'b0;
    end

    genclock <= cycle < 11;
    cycle <= cycle + 1;
  end
endmodule
