`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// auto_sync created 18/12/2020 by Andi
// last change 15/03/2021 by Andi
// note:
// - if received pulses < PULSE_NUM_MAX waits until timeout (TIME_BITS cycles) to finish.
//   as long as time0, time1, and time1_PS are nonzero does not give as_timeout error though.
//   time0_PS can be 0 for both boards (for secondary always the case for single pulse).
//   its not clear how this could be avoided. 
// TODO:
// - measured times might be wrong when pulses are very close, at wait end or near timeout.
//////////////////////////////////////////////////////////////////////////////////

module auto_sync # (
	// auto-sync pulse time + blank time
    parameter integer PULSE_LENGTH  = 3,            // 2 = 40ns @ 50MHz
    parameter integer PULSE_WAIT    = 5,            // 3 = 60ns @ 50MHz, wait time after pulse
    parameter integer PULSE_NUM_MAX = 2,            // 2 = primary board, 1 = secondary board
	// auto-sync time bits
    parameter integer TIME_BITS = 8,                // 4x8
    // phase shift bits
    parameter integer PHASE_BITS  = 12,             // 12     
    // delay bits
    parameter integer DELAY_BITS = 10               // 10
)
(
    // clock and reset
    input wire clock_IO,        // clock for register I/O and dynamic phase shift
    input wire clock_bus,       // bus output clock
    input wire clock_det,       // phase shifted detector clock with respect to clock_bus
    input wire reset_n_IO, 
    input wire reset_n_bus,
    
    // dynamic phase shift of external clock input and detector clock @ clock_IO
    input wire ps_done_ext,
    output wire ps_en_ext,
    output wire ps_inc_ext,
    input wire ps_done_det,
    output wire ps_en_det,
    output wire ps_inc_det,
    
    // auto-sync outputs and input
    output wire sync_out,       // @ clock_bus
    output wire sync_mon,       // @ clock_det
    input wire sync_in,         // not synchronized
    
    // control bits @ clock_IO
    input wire clk_ext_locked, // external clock is locked. used by phase shift
    input wire clk_int_locked, // internal clock is locked. used by phase shift
    input wire as_en,
    input wire as_prim,
    input wire ps_start,
    
    // status bits @ clock_IO
    output wire as_active,
    output wire as_timeout,
    output wire ps_active,
    
    // measured round-trip time {t1_PS,t0_PS,t1,t0} @ clock_IO
    output wire [(4*TIME_BITS)-1:0] sync_time,

    // trigger delay
    input wire [DELAY_BITS-1:0] sync_delay,     // @ clock_IO
    output wire trg_out,                        // @ clock_bus

    // phase shift @ clock_IO
    input wire [2*PHASE_BITS-1:0] ps_phase
    
    );
    
    // number of synchronization stages
    localparam integer SYNC = 2;
                
    // pulse start CDC from clock_IO to clock_bus
    wire pulse_start = as_en & as_prim;
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] pulse_start_cdc_bus;
    always @ ( posedge clock_bus ) begin
        pulse_start_cdc_bus <= {pulse_start_cdc_bus[SYNC-2:0],pulse_start};
    end
    wire pulse_start_bus = pulse_start_cdc_bus[SYNC-1];
                
    // pulse generation @ clock_bus
    sync_pulse # (
        .PULSE_LENGTH(PULSE_LENGTH)
        )
    pulse (    
        .clock(clock_bus),
        .reset_n(reset_n_bus),
        .start(pulse_start_bus),                // @ clock_bus 
        .sync_out(sync_out)                     // @ clock_bus
        );

    // reset CDC from clock_bus to clock_det
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] reset_n_det_ff;    
    always @ ( posedge clock_det ) begin
        reset_n_det_ff <= {reset_n_det_ff[SYNC-2:0],reset_n_bus};
    end
    wire reset_n_det = reset_n_det_ff[SYNC-1];
    
    // auto-sync enable CDC from clock_IO to clock_det
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] as_en_det_cdc;
    always @ ( posedge clock_det ) begin
        as_en_det_cdc <= {as_en_det_cdc[SYNC-2:0],as_en};
    end
    wire as_en_det = as_en_det_cdc[SYNC-1];    
    
    // auto-sync primary board CDC from clock_IO to clock_det
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] as_prim_det_cdc;
    always @ ( posedge clock_det ) begin
        as_prim_det_cdc <= {as_prim_det_cdc[SYNC-2:0],as_prim};
    end
    wire as_prim_det = as_prim_det_cdc[SYNC-1];
    
    // sync_in synchronization / detection @ clock_bus
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] sync_in_cdc_bus;
    always @ ( posedge clock_bus ) begin
        sync_in_cdc_bus <= {sync_in_cdc_bus[SYNC-2:0],sync_in};
    end
    wire sync_in_bus = sync_in_cdc_bus[SYNC-1];

    // sync_in detection at clock_bus and CDC to clock_det
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] sync_in_bus_cdc_det;
    always @ ( posedge clock_det ) begin
        sync_in_bus_cdc_det <= {sync_in_bus_cdc_det[SYNC-2:0],sync_in_bus};
    end
    wire sync_in_bus_det = sync_in_bus_cdc_det[SYNC-1];
    
    // sync_in synchronization / detection @ clock_det 
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] sync_in_cdc_det;
    always @ ( posedge clock_det ) begin
        sync_in_cdc_det <= {sync_in_cdc_det[SYNC-2:0],sync_in};
    end
    wire sync_in_det = sync_in_cdc_det[SYNC-1];

    wire as_timeout_det;
    wire [(4*TIME_BITS)-1:0] sync_time_det;
    wire as_done_det;
    sync_timer # (
        .PULSE_LENGTH(PULSE_LENGTH),
        .PULSE_WAIT(PULSE_WAIT),
        .PULSE_NUM_MAX(PULSE_NUM_MAX),
        .TIME_BITS(TIME_BITS),
        .DELAY_BITS(DELAY_BITS)
        )
    timer (  
        .clock_det(clock_det),
        .reset_n_det(reset_n_det),
        .as_en(as_en_det),              // @ clock_det
        .as_prim(as_prim_det),          // @ clock_det
        .sync_in_bus(sync_in_bus_det),  // sync_in sampled at clk_bus and CDC to clk_det
        .sync_in_det(sync_in_det),      // sync_in sampled at clk_det
        .sync_mon(sync_mon),            // @ clock_det
        .as_timeout(as_timeout_det),    // @ clock_det
        .sync_time(sync_time_det),      // @ clock_det
        .as_done(as_done_det)           // @ clock_det
        );
        
    // sync_time, timeout and done CDC from clock_det to clock_IO
    wire as_done;
    cdc # ( 
        .SYNC(SYNC), 
        .DATA_WIDTH(4*TIME_BITS + 1), 
        .USE_OUT_READY("NO")
    )
    cdc_out (
        .in_clock(clock_det),
        .in_reset_n(reset_n_det),
        .in_data({as_timeout_det,sync_time_det}),
        .in_valid(as_done_det),
        .in_ready(),
        .out_clock(clock_IO),
        .out_reset_n(reset_n_IO),
        .out_data({as_timeout,sync_time}),
        .out_valid(as_done),// pulses when bits have been reloaded
        .out_ready(1'b1) // always ready
    );
        
    // start edge detector
    reg as_en_ff;
    always @ ( posedge clock_IO ) begin
        as_en_ff <= as_en;
    end
    wire as_en_edge = ({as_en_ff,as_en} == 2'b01) ? 1'b1 : 1'b0;

    // active from positive edge of as_en until as_done
    reg as_active_ff;
    always @ (posedge clock_IO ) begin
        if ( reset_n_IO == 1'b0 ) as_active_ff <= 1'b0;
        else if ( as_en_edge ) as_active_ff <= 1'b1;
        else if ( as_done ) as_active_ff <= 1'b0;
        else as_active_ff <= as_active_ff;
    end
    assign as_active = as_active_ff;
    
    // sync_delay, as_en and as_prim input CDC from clock_IO to clock_bus
    wire [DELAY_BITS-1:0] sync_delay_bus;
    wire as_en_bus;
    wire as_prim_bus;
    wire as_start_bus;
    cdc # ( 
        .SYNC(SYNC), 
        .DATA_WIDTH(DELAY_BITS+2), 
        .USE_OUT_READY("NO")
    )
    cdc_in (
        .in_clock(clock_IO),
        .in_reset_n(reset_n_IO),
        .in_data({as_prim,as_en,sync_delay}),
        .in_valid(as_en_edge),
        .in_ready(),
        .out_clock(clock_bus),
        .out_reset_n(reset_n_bus),
        .out_data({as_prim_bus,as_en_bus,sync_delay_bus}),
        .out_valid(as_start_bus),   // pulses when bits have been reloaded
        .out_ready(1'b1)            // always ready
    );
    
    // as_done CDC from clock_det to clock_bus
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] as_done_cdc_bus;
    always @ ( posedge clock_bus ) begin
        as_done_cdc_bus <= {as_done_cdc_bus[SYNC-2:0],as_done_det};
    end
    wire as_done_bus = as_done_cdc_bus[SYNC-1];

    // trigger output to demonstrate synchronization of primary and secondary boards.
    // primary board:   single pulse after trg_delay cycles after pulse generation. 
    //                  no pulse if sync_delay = 0 
    // secondary board: single pulse with as_done independent of sync_delay.
    reg [DELAY_BITS-1:0] trg_count;
    reg trg_out_ff;
    reg as_active_bus;
    always @ ( posedge clock_bus ) begin
        if ( reset_n_bus == 1'b0 ) begin 
            trg_count <= 0;
            trg_out_ff <= 1'b0;
            as_active_bus <= 1'b0;
        end
        else if ( as_prim_bus ) begin // primary board
            if ( as_start_bus ) begin
                trg_count <= sync_delay_bus;
                trg_out_ff <= 1'b0;
            end
            else if ( trg_count > 0 ) begin
                trg_count <= trg_count - 1;
                trg_out_ff <= ( trg_count == 1 ) ? 1'b1 : 1'b0;
            end
            else begin
                trg_count <= 0;
                trg_out_ff <= 1'b0;
            end
            as_active_bus <= 1'b0;
        end
        else if ( as_start_bus ) begin // secondary board
            trg_count <= 0;
            trg_out_ff <= 1'b0;
            as_active_bus <= 1'b1;
        end
        else if ( as_active_bus ) begin
            trg_count <= 0;
            trg_out_ff <= as_done_bus;        
            as_active_bus <= ~as_done_bus;            
        end
        else begin
            trg_count <= 0;
            trg_out_ff <= 1'b0;
            as_active_bus <= 1'b0;
        end
    end
    assign trg_out = trg_out_ff;

    // external clock dynamic phase shift @ clock_fast
    wire ps_ext_active;
    dynamic_phase # (
        .PHASE_BITS(PHASE_BITS)
    )
    ps_ext
    (
        // clock and reset
        .clock(clock_IO),
        .reset_n(reset_n_IO),
        // control and status
        .ps_start(ps_start),
        .ps_active(ps_ext_active),
        // clock is locked signal
        .clock_locked(clk_ext_locked),
        // ps control
        .ps_en(ps_en_ext),
        .ps_inc(ps_inc_ext), 
        .ps_done(ps_done_ext),
        // phase shift
        .ps_phase(ps_phase[2*PHASE_BITS-1:PHASE_BITS])
    );

    // detector clock dynamic phase shift @ clock_fast
    wire ps_det_active;
    dynamic_phase # (
        .PHASE_BITS(PHASE_BITS)
    )
    ps_det
    (
        // clock and reset
        .clock(clock_IO),
        .reset_n(reset_n_IO),
        // control and status
        .ps_start(ps_start),
        .ps_active(ps_det_active),
        // clock is locked signal
        .clock_locked(clk_int_locked),
        // ps control
        .ps_en(ps_en_det),
        .ps_inc(ps_inc_det), 
        .ps_done(ps_done_det),
        // phase shift
        .ps_phase(ps_phase[PHASE_BITS-1:0])
    );
    
    assign ps_active = ps_ext_active | ps_det_active;
        
endmodule
