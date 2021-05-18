`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// dynamic phase shift module
// note: all inputs and outputs are assumed to be synchronized with clock! 
// created 22/2/2021 by Andi
// last change 27/2/2021 by Andi
//////////////////////////////////////////////////////////////////////////////////

module dynamic_phase # (
    parameter integer PHASE_BITS = 12
    )
    (
    // clock and reset
    input wire clock,
    input wire reset_n,
    // control and status @ clock
    input wire ps_start,
    output wire ps_active,
    // clock is locked signal @ clock
    input wire clock_locked,
    // ps control @ clock
    output wire ps_en,
    output wire ps_inc, 
    input wire ps_done,
    // phase shift @ clock
    input wire [PHASE_BITS-1:0] ps_phase
    );
    
    // dynamic phase shifting TODO 
    // becomes active when trg_delay was changed and phase bits > 0 in trg_delay and not already active
    // performs specified number of steps in trg_delay TRG_DELAY_PHASE_BITS
    // direction of step is given by sign bit [MSB] -> disabled! now only increases!
    // each step consists of settings ps_en for 1 fast cycle and waiting for ps_done bit
    // if clock is lost during phase shift remains active to indicate error. needs reset.
    reg [PHASE_BITS - 1 :0] phase;
    reg ps_en_ff;
    reg ps_inc_ff;
    reg ps_active_ff;
    reg ps_error_ff;
    always @ (posedge clock) begin
        if ( reset_n == 1'b0 ) begin
            phase <= 0;
            ps_active_ff <= 1'b0;
            ps_en_ff <= 1'b0;
            ps_inc_ff <= 1'b0;
            ps_error_ff <= 1'b0;
        end
        else if ( ps_error_ff ) begin // error until reset
            phase <= 0;
            ps_active_ff <= 1'b1;
            ps_en_ff <= 1'b0;
            ps_inc_ff <= 1'b0;
            ps_error_ff <= ps_error_ff;
        end
        else if ( ps_start & (~ps_active_ff) & (ps_phase != 0) ) begin
            if ( clock_locked ) begin
                ps_active_ff <= 1'b1;
                ps_en_ff <= 1'b1;
                //if ( phase[TRG_DELAY_PHASE_BITS-1] == 1'b0 ) begin // positive
                    ps_inc_ff <= 1'b1;
                    phase <= ps_phase - 1;
                /*end
                else begin // negative
                    ps_inc_ff <= 1'b0;
                    ps_phase <= phase + 1;
                end*/
                ps_error_ff <= 1'b0;
            end
            else begin // error
                phase <= 0;
                ps_active_ff <= 1'b1;
                ps_en_ff <= 1'b0;
                ps_inc_ff <= 1'b0;
                ps_error_ff <= 1'b1;
            end
        end
        else if ( ps_active_ff ) begin
            if ( clock_locked ) begin
                if ( ps_done ) begin
                    ps_active_ff <= ( phase != 0 );
                    ps_en_ff <= ( phase != 0 );
                    phase <= ( ps_inc == 1'b1 ) ? phase - 1 : phase + 1;
                end
                else begin
                    ps_active_ff <= 1'b1;
                    ps_en_ff <= 1'b0;
                end
                ps_inc_ff <= ps_inc_ff;
                ps_error_ff <= 1'b0;
            end
            else begin // error
                phase <= 0;
                ps_active_ff <= 1'b1;
                ps_en_ff <= 1'b0;
                ps_inc_ff <= 1'b0;
                ps_error_ff <= 1'b1;
            end
        end
        else begin
            phase <= 0;
            ps_active_ff <= 1'b0;
            ps_en_ff <= 1'b0;
            ps_inc_ff <= 1'b0;
            ps_error_ff <= ps_error_ff;      
        end
    end
    assign ps_en = ps_en_ff;
    assign ps_inc = ps_inc_ff;
    assign ps_active = ps_active_ff;    
    
endmodule
