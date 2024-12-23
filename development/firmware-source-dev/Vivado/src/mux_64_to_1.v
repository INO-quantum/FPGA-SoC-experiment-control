`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// mux_64_to_1.v 
// 64:1 multiplexer: out <= in[ctrl]
// on 7-series device this should use 4x CLB slices + 1x LUT6 of another CLB slice
// out is buffered when BUFFERED_OUT != 0.
// output of 16:1 MUX is buffered when BUFFER_MUX16 != 0.
// latency = 2 cycles when both buffers are activated, 1 cycle for one activated.
// created 30/11/2024 by Andi
// last change 2/12/2024 by Andi (reviewed 4/12/2024 by Andi)
//////////////////////////////////////////////////////////////////////////////////

module mux_64_to_1 # (
    parameter integer BUFFER_OUT = 1,
    parameter integer BUFFER_MUX16 = 1
)
(
    // clock
    input wire clk,
    // control input
    input wire [6-1:0] ctrl,
    // inputs
    input wire [64-1:0] in,
    // output
    output wire out
);

    // 4x 16:1 MUX 
    // this should synthesize into 4x CLB slices
    wire [4-1:0] mux16_out;
    generate 
    for (genvar i = 0; i < 4; i = i + 1) begin : MUX16
        mux_16_to_1 # (
            .BUFFERED (BUFFER_MUX16)
        )
        mux (
            .clk    (clk),
            .ctrl   (ctrl[3:0]),
            .in     (in  [16*(i+1)-1 -: 16]),
            .out    (mux16_out[i])
        );
    end
    endgenerate
    
    // combine 16:1 MUX with 4:1 MUX into 64:1 MUX
    // this should synthesize a single LUT6 of another slice
    wire mux64_out;
    mux_4_to_1 MUX64 (
        .ctrl   (ctrl[5:4]),
        .in     (mux16_out),
        .out    (mux64_out)
    );

    // output buffer if enabled
    if (BUFFER_OUT == 0) begin
        assign out = mux64_out;
    end
    else begin
        reg out_ff = 1'b0; 
        always @ ( posedge clk ) begin
            out_ff <= mux64_out;
        end
        assign out = out_ff;
    end

endmodule
