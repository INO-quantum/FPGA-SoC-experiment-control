`timescale 1 ns / 1 ps

//////////////////////////////////////////////////////////////////////////////////
// Verilog module cdc_no_bus.v, created 8/8/2023 by Andi
// simple cdc with non-synchronized bits
// use constraint file: cdc_no_bus.xdc with SCOPED_TO_REF = cdc_no_bus.v
// creates simple clock-domain-crossing of WIDTH unrelated bits (no bus).
// for related (bus) bits use cdc module. 
// latency = in -> out:
//   SYNC_STAGES   clk_out cycles with USE_INPUT_BUFFER="NO"
//   SYNC_STAGES+1 clk_out cycles with USE_INPUT_BUFFER="YES"
// parameters:
// - BITS_WIDTH = number of unrelated bits
// - SYNC_STAGES = number of synchronization stages. use 2 or 3 (1 or 2 metastable bits)
// - USE_INPUT_BUFFER = "YES" or "NO" if an additional input buffer should be used or not.
//                      use "YES" if input signal is coming from logic, "NO" if comes from register.
// inputs:
// - clk_out = output clock
// - in      = input bits at input clock
// outputs:
// - out     = output bits at clk_out 
//////////////////////////////////////////////////////////////////////////////////

module cdc_no_bus #
(
    parameter integer BITS_WIDTH = 1,
    parameter integer SYNC_STAGES = 2,
    parameter USE_INPUT_BUFFER = "YES"
)
(
    // input and output clock
    input wire clk_in,
    input wire clk_out,

    // input and output bits (unrelated)
    input  wire [BITS_WIDTH-1:0] in,
    output wire [BITS_WIDTH-1:0] out
);

    // input buffer @ clk_in
    wire [BITS_WIDTH-1:0] in_w;
    if ( USE_INPUT_BUFFER == "YES" ) begin
        reg [BITS_WIDTH-1:0] in_buf = 0;
        always @ ( posedge clk_in ) begin
            in_buf <= in;
        end
        assign in_w = in_buf;
    end
    else begin
        assign in_w = in;
    end

    // synchronize output bits @ clk_out
    generate
    for (genvar i = 0; i < BITS_WIDTH; i = i + 1)
    begin : SNB
        // ASYNC_REG = ensures sync bits are close to each other
        (* ASYNC_REG = "TRUE" *)
        reg [SYNC_STAGES-1:0] sync = 0;
        always @ ( posedge clk_out ) begin
            sync <= {sync[SYNC_STAGES-2:0],in_w[i]};
        end
        assign out[i] = sync[SYNC_STAGES-1];
    end
    endgenerate

endmodule

