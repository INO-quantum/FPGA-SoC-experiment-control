`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// mux_4_to_1.v 
// simple 4:1 multiplexer: out <= in[ctrl]
// on 7-series device this should synthesize into one LUT6 with 4 inputs + 2 address bits
// 4x mux_4_to_1 and 3x mux_2_to_1 can be combined into 1x 16:1 mux
// out is not buffered
// created 30/11/2024 by Andi
// last change 30/11/2024 by Andi (reviewed 4/12/2024 by Andi)
//////////////////////////////////////////////////////////////////////////////////

module mux_4_to_1
(
    // control input
    input wire [2-1:0] ctrl,
    // inputs
    input wire [4-1:0] in,
    // output
    output wire out
);

    reg out4;
    always @ ( in or ctrl ) begin
        case ( ctrl ) 
            2'b00  : out4 <= in[0];
            2'b01  : out4 <= in[1];
            2'b10  : out4 <= in[2];
            2'b11  : out4 <= in[3];
            default: out4 <= 1'bx;
        endcase
    end
    assign out = out4;

endmodule

