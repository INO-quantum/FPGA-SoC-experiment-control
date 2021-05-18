`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// AXI stream multiplexer
// out_select selects which of the two inputs is connected to output
// OUT_BUF = "FALSE": no additional buffer (default, recommended). latency = 1.
// OUT_BUF = "TRUE" : additional output buffered. latency = 2. 
//                    better preformance for stop-and-go applications.
// all outputs are directly registered without logic: out_data, out_valid and in_ready
// created 03/10/2020 by Andi
// last change 03/10/2020 by Andi
// TODO: 
// - switching while streaming is not tested.
// - the faster recovery with output buffer not tested.
//////////////////////////////////////////////////////////////////////////////////

module stream_MUX # (
    parameter integer DATA_WIDTH = 32,
    parameter OUT_BUF = "FALSE"             // "TRUE" or "FALSE"
)
(
    // clock and reset
    input clock,
    input reset_n,
    // input selection
    input in_select,
    // stream data input 0
    input [DATA_WIDTH-1:0] in_data_0,
    input in_valid_0,
    output in_ready_0,
    // stream data input 1
    input [DATA_WIDTH-1:0] in_data_1,
    input in_valid_1,
    output in_ready_1,
    // stream data output
    output [DATA_WIDTH-1:0] out_data,
    output out_valid,
    input out_ready
);

    wire in_ready;
    stream_IO # (
        .DATA_WIDTH(DATA_WIDTH),
        .IN_READY_PULSE("YES"),         // "NO","YES","OSC"
        .OUT_BUF(OUT_BUF),              // "TRUE", "FALSE"
        .IN_READY_LOW_CYCLES(0),        // >=0
        .OUT_ZERO("FALSE")              // "TRUE", "FALSE"
        )
        IO
        (
        // clock and reset
        .clock(clock),
        .reset_n(reset_n),
        // input interface
        .in_data((in_select) ? in_data_1 : in_data_0),
        .in_valid((in_select) ? in_valid_1 : in_valid_0),
        .in_ready(in_ready),
        // output interface
        .out_data(out_data),
        .out_valid(out_valid),
        .out_ready(out_ready)
        );
            
    assign in_ready_0 = (in_select) ? 1'b0 : in_ready;
    assign in_ready_1 = (in_select) ? in_ready : 1'b0;

endmodule

