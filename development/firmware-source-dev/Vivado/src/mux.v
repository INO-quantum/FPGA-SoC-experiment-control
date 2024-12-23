`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// mux.v 
// simple multiplexer: out <= in[ctrl]
// out is buffered with 1 cycle latency
// created 06/05/2023 by Andi
// last change 17/10/2024 by Andi
//////////////////////////////////////////////////////////////////////////////////

module mux # (
    parameter integer CTRL_BITS  = 2,       // control bits
    parameter integer NUM_IN     = 4,       // number of inputs. max. 2^CTRL_BITS
    parameter integer BUFFERED   = 1        // 1 = use register, otherwise use assign
)
(
    // clock and reset
    input wire clock,
    input wire reset_n,
    // control input
    input wire [CTRL_BITS-1:0] ctrl,
    // inputs
    input wire [NUM_IN-1:0] in,
    // valid when high for each input
    input wire [NUM_IN-1:0] in_valid,
    // output
    output wire out,
    // output valid
    output wire out_valid
);

    //localparam integer MAX_IN = (1<<CTRL_BITS);
    if (BUFFERED) begin       
        integer i;
        reg out_ff       = 1'b0;
        reg out_valid_ff = 1'b0;
        always @ ( posedge clock ) begin
            if ( reset_n == 1'b0 ) begin
                out_ff <= 1'b0;
            end
            else begin
                for (i = 0; i < NUM_IN; i = i + 1) begin
                    if ( ctrl == i ) begin
                        out_ff       <= in_valid[i] ? in[i] : 1'b0;
                        out_valid_ff <= in_valid[i];
                    end
                end
                // TODO: not sure if below simpler code synthesizes?
                //       out_ff <= (ctrl < NUM_IN) ? in[ctrl] & valid[ctrl] : 1'b0;
            end
        end
        assign out       = out_ff;
        assign out_valid = out_valid_ff;
    end 
    else begin
       assign out       = (ctrl < NUM_IN) ? in_valid[ctrl] & in[ctrl] : 1'b0;
       assign out_valid = (ctrl < NUM_IN) ? in_valid[ctrl]            : 1'b0;
    end

endmodule
