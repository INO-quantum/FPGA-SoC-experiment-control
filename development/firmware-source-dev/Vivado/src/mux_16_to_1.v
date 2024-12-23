`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// mux_16_to_1.v 
// 16:1 multiplexer: out <= in[ctrl]
// for 7-series device this should synthesize into 16:1 multiplexer of a single CLB slice 
// out is buffered when BUFFERED != 0 
// latency = 1 cycle when buffer is activated.
// created 30/11/2024 by Andi
// last change 4/12/2024 by Andi
//////////////////////////////////////////////////////////////////////////////////

module mux_16_to_1 # (
    parameter integer BUFFERED = 1
)
(
    // clock
    input wire clk,
    // control input
    input wire [4-1:0] ctrl,
    // inputs
    input wire [16-1:0] in,
    // output
    output wire out
);

    // 4x 4:1 MUX 
    // this should synthesize into 4x LUT6 of CLB slice
    wire [4-1:0] mux4_out;
    generate 
    for (genvar i = 0; i < 4; i = i + 1) begin : MUX4
        mux_4_to_1 MUX (
            .ctrl   (ctrl    [1:0]),
            .in     (in      [4*(i+1)-1 -: 4]),
            .out    (mux4_out[i])
        );
    end
    endgenerate
    
    // combine 4:1 MUX with 2:1 MUX into 8:1 MUX
    // this should synthesize into F7AMUX and F7BMUX of CLB slice
    wire [2-1:0] mux8_out;    
    generate 
    for (genvar i = 0; i < 2; i = i + 1) begin : F7
        mux_2_to_1 MUX (
            .ctrl   (ctrl[2]),
            .in     (mux4_out[2*(i+1)-1 -: 2]),
            .out    (mux8_out[i]),
            .en     (1'b1)
        );
    end
    endgenerate

    // combine 8:1 MUX with 2:1 MUX into 16:1 MUX
    // this should synthesize into F8MUX of CLB slice
    wire mux16_out;
    mux_2_to_1 F8MUX (
        .ctrl   (ctrl[3]),
        .in     (mux8_out),
        .out    (mux16_out),
        .en     (1'b1)
    );

    // output buffer if enabled
    // this should use register output B of CLB slice
    if (BUFFERED == 0) begin
        assign out = mux16_out;
    end
    else begin
        reg out_ff = 1'b0; 
        always @ ( posedge clk ) begin
            out_ff <= mux16_out;
        end
        assign out = out_ff;
    end

endmodule

