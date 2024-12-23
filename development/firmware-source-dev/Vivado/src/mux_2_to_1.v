`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// mux_2_to_1.v 
// simple 2:1 multiplexer: out <= in[ctrl]
// on 7-series device for fixed en = 1'b1 this should synthesize into F7AMUX, F7BMUX or F8MUX
// for variable en this should synthesize into one LUT6
// 4x mux_4_to_1 and 3x mux_2_to_1 can be combined into 1x 16:1 mux 
// out is not buffered
// created 30/11/2024 by Andi
// last change 2/12/2024 by Andi (reviewed 4/12/2024 by Andi)
//////////////////////////////////////////////////////////////////////////////////

module mux_2_to_1 (
    // control input
    input wire [1-1:0] ctrl,
    // inputs
    input wire [2-1:0] in,
    // enable input
    input wire en,
    // output
    output wire out
);

    reg out2;
    always @ ( in or ctrl or en ) begin
        case ({ctrl,en}) 
            2'b00  : out2 <= 1'b0;
            2'b01  : out2 <= in[0];
            2'b10  : out2 <= 1'b0;
            2'b11  : out2 <= in[1];
            default: out2 <= 1'bx;
        endcase
    end
    assign out = out2;
    
endmodule

