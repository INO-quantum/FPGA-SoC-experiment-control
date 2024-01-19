`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// mux.v 
// simple multiplexer
// created 06/05/2023 by Andi
// last change 08/05/2023
//////////////////////////////////////////////////////////////////////////////////

module mux # (
    parameter integer CTRL_BITS = 2,   // control bits
    parameter integer NUM_IN    = 4    // number of inputs. max. 2^CTRL_BITS
)
(
    // clock and reset
    input wire clock,
    input wire reset_n,
    // control input
    input wire [CTRL_BITS-1:0] ctrl,
    // inputs
    input wire [NUM_IN-1:0] in,
    // outputs
    output out
);
        
    integer i;
    reg out_ff = 1'b0;
    always @ ( posedge clock ) begin
        if ( reset_n == 1'b0 ) begin
            out_ff <= 1'b0;
        end
        else begin
            for (i = 0; i < NUM_IN; i = i + 1) begin
                if ( ctrl == i ) begin
                    out_ff <= in[i];
                end
            end
        end
    end
    assign out = out_ff;

endmodule
