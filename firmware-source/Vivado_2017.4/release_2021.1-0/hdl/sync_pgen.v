`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// sync_pgen.v synchronized pulse generator
// see CummingsSNUG2008Boston_CDC_clock_domain_crossings.pdf figure 19
// created 25/06/2020 by Andi
// last change 26/06/2020 by Andi
// ATTENTION: in_signal must come from a register and not from logic!
//////////////////////////////////////////////////////////////////////////////////


module sync_pgen # (
        parameter integer SYNC = 2      // synchronization stages 2-3 
    )
    (
        input out_clock,
        input out_reset_n,
        input in_signal,
        output out_pulse,
        output out_signal
    );
    
    // input synchronization
    wire in_sync;
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] sync = {SYNC{1'b0}};
    always @ ( posedge out_clock ) begin
        if ( out_reset_n == 1'b0 ) sync <= {SYNC{1'b0}};
        else sync <= {sync[SYNC-2:0],in_signal};
    end
    assign in_sync = sync[SYNC-1];
    
    // output signal flip-flop
    reg out_signal_ff = 1'b0;
    always @ ( posedge out_clock ) begin
        if ( out_reset_n == 1'b0 ) out_signal_ff <= 1'b0;
        else out_signal_ff <= in_sync;
    end
    assign out_signal = out_signal_ff;
    
    // pulse generation
    assign out_pulse = out_signal ^ in_sync;
    
endmodule
