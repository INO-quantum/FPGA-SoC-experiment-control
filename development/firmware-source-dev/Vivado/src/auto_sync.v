`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// auto_sync created 18/12/2020 by Andi
// simplified scheme:
//                                  +-----------+-----------+
//                                  |         reset         |
//                                  +-----------+-----------+
//                                              |
//                                 as_run_start |
//                                              |
//    as_trg_en  = 1'b0 +-----------------------+ 1'b1
//                      |                       |
//                      |                       / cdc @ clk_det
//                      |                       |
//                      |           +-----------+-----------+
//                      |           | wait sync_in_tgl_det  | @ clk_det
//                      |           +-----------+-----------+
//                      |                       |
//                      |                       / cdc @ clk_bus
//                      |                       |
//                      +-----------------------+-----------------------------------+
//                                              |                                   |
//      sync_delay == 0 +-----------------------+ > 0                               |
//                      |                       |                                   |
//                      |           +-----------+-----------+           +-----------+-----------+
//                      |           | wait sync_delay cycles|           |generate sync_out pulse|
//                      |           +-----------+-----------+           +-----------+-----------+
//                      |                       |
//                      +-----------------------+
//                                              |
//                                  +-----------+-----------+
//                                  |        as_start       |
//                                  +-----------+-----------+
//
// note:
// this module has been heavily edited and has been simplified.
// at the moment timer is not anymore used but could be converted to a general-purpose timer/counter module.
// 
// last change 2023/01/07 by Andi
//////////////////////////////////////////////////////////////////////////////////

module auto_sync # (
	// auto-sync pulse time + blank time
	//parameter SYNC_IN_INVERTED = "NO",              // "YES" or "NO" if sync_in input is inverted
	//parameter SYNC_OUT_INVERTED = "NO",             // "YES" or "NO" if sync_out output is inverted
    parameter integer PULSE_LENGTH  = 3,            // 2 = 40ns @ 50MHz
    parameter integer PULSE_WAIT    = 5,            // 3 = 60ns @ 50MHz, wait time after pulse
    parameter integer PULSE_NUM_MAX = 2,            // 2 = primary board, 1 = secondary board. TODO: hardcode?
	// auto-sync time bits
    parameter integer TIME_BITS     = 8,            // 4x8
    // delay bits
    parameter integer DELAY_BITS    = 10            // 10
)
(
    // clock and reset
    input wire clk_bus,                 // bus output clock
    input wire clk_det,                 // phase shifted detector clock with respect to clock_bus
    input wire reset_bus_n,
    input wire reset_det_n,
        
    // control bits @ clk_bus
    input wire as_trg_en,       // wait for start trigger
    //input wire as_prim,       // primary board [not needed anymore]
    //input wire as_sync_wait,  // wait for sync_in [not needed anymore]
    //input wire as_FET,        // switch on FET for pulse reflection. [replaced by setting an ouput to high/low]
    input wire as_run_start,    // run start
    
    // status bits
    output wire as_active,      // @ clk_bus
    output wire as_timeout,     // @ clk_det
    output wire as_done,        // @ clk_det

    // auto-sync inputs
    input wire sync_in_tgl_bus, // @ clk_bus
    input wire sync_in_tgl_det, // @ clk_det
    
    // auto-sync outputs
    output wire sync_out,       // pulse @ clk_bus
    //output wire sync_en,        // as_active signal @ clk_bus
    output wire sync_mon,       // sync_in detection @ clk_det
        
    // measured round-trip time {t1_PS,t0_PS,t1,t0} @ clock_det
    output wire [(4*TIME_BITS)-1:0] sync_time,

    // sync delay time @ clk_bus
    input wire [DELAY_BITS-1:0] sync_delay,
    
    // auto-sync start signal. pulses for 1 clk_bus cycle.
    output wire as_start
    );
    
    // returns ceiling of the log base 2 of bd.
    // see axi_stream_master.v example from Xilinx
    function integer clogb2 (input integer bd);
    integer bit_depth;
      begin
        bit_depth = bd;
        for(clogb2=0; bit_depth>0; clogb2=clogb2+1)
          bit_depth = bit_depth >> 1;
      end
    endfunction

    // number of synchronization stages
    localparam integer SYNC = 2;
                        
    ///////////////////////////////////////////////////////////
    // bus clock
    
    // cdc of detected pulse @ clk_det to clk_bus  
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] sync_in_tgl_cdc_bus;
    reg  sync_in_tgl_det_bus_ff = 1'b0;
    wire sync_in_tgl_det_bus    = sync_in_tgl_cdc_bus[SYNC-1];
    always @ ( posedge clk_bus ) begin
        sync_in_tgl_cdc_bus    <= {sync_in_tgl_cdc_bus[SYNC-2:0],sync_in_tgl_det};
        sync_in_tgl_det_bus_ff <= sync_in_tgl_det_bus;
    end
    wire sync_in_pulse_det_bus = ( sync_in_tgl_det_bus_ff != sync_in_tgl_det_bus );
    
    // finite state machine states
    localparam integer STATE_RESET  = 0;
    localparam integer STATE_TRIG   = 1;
    localparam integer STATE_DELAY  = 2;
    localparam integer STATE_START  = 3;
    // number of states
    localparam integer STATES       = 4;
    
    // finite state machine
    localparam integer STATE_BITS = clogb2(STATES-1);
    reg [STATE_BITS-1:0] state = STATE_RESET;
    localparam integer SYNC_OUT_COUNT_BITS = clogb2(PULSE_LENGTH-1);
    reg as_active_ff = 1'b0;
    reg [SYNC_OUT_COUNT_BITS-1 : 0] sync_out_count = 0;
    reg [DELAY_BITS-1:0] delay_count;
    reg as_start_ff;
    reg sync_out_ff;
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) begin // reset
            state          <= STATE_RESET;
            as_active_ff   <= 1'b0;
            sync_out_count <= 0;
            sync_out_ff    <= 1'b0;
            delay_count    <= 0;
            as_start_ff    <= 1'b0;
        end
        else if ( state == STATE_TRIG ) begin // start with external trigger
            state          <= ( sync_in_pulse_det_bus ) ? STATE_DELAY : STATE_TRIG;
            as_active_ff   <= 1'b1;
            sync_out_count <= sync_out_count;
            sync_out_ff    <= ( sync_in_pulse_det_bus );
            delay_count    <= delay_count;
            as_start_ff    <= ( sync_in_pulse_det_bus ) ? ( ( delay_count == 0 ) ? 1'b1 : 1'b0 ) : 1'b0;
        end 
        else if ( state == STATE_DELAY ) begin // pulse and/or delay counter running
            state          <= ( ( sync_out_count == 0 ) && ( delay_count == 0 ) ) ? STATE_START : STATE_DELAY; 
            as_active_ff   <= 1'b1;
            sync_out_count <= ( sync_out_count != 0 ) ? sync_out_count - 1 : 0;
            sync_out_ff    <= ( sync_out_count != 0 );
            delay_count    <= ( delay_count    != 0 ) ? delay_count    - 1 : 0;
            as_start_ff    <= ( delay_count == 1 ) ? 1'b1 : 1'b0;
        end
        else if ( state == STATE_START ) begin // delay one cycle to allow as_run_start to reset
            state          <= STATE_RESET; 
            as_active_ff   <= 1'b1;
            sync_out_count <= 0;
            sync_out_ff    <= 1'b0;
            delay_count    <= 0;
            as_start_ff    <= 1'b0;
        end
        else begin // state == STATE_RESET: wait for as_run_start
            state          <= ( as_run_start ) ? ( as_trg_en ? STATE_TRIG : STATE_DELAY ) : STATE_RESET;
            as_active_ff   <= ( as_run_start );
            sync_out_count <= ( as_run_start ) ? PULSE_LENGTH - 1 : 0;
            sync_out_ff    <= ( as_run_start ) ? ( as_trg_en ? 1'b0 : 1'b1 ) : 1'b0;
            delay_count    <= ( as_run_start ) ? sync_delay : 0;
            as_start_ff    <= ( as_run_start ) ? ( as_trg_en ? 1'b0 : (( sync_delay == 0 ) ? 1'b1 : 1'b0) ) : 1'b0;
        end
    end
    assign as_active = as_active_ff;
    assign sync_out = sync_out_ff;
    assign as_start = as_start_ff;
            
    /* auto-sync enable FET output. high = reflect pulse. replaced by as_active signal or better by software programming of output.
    reg sync_en_ff;
    always @ ( posedge clk_bus ) begin
        //sync_en_ff <= as_en & as_FET;
        sync_en_ff <= as_FET;
    end
    assign sync_en = sync_en_ff;
    */

    ///////////////////////////////////////////////////////////
    // detection clock
    
    // sync_in detection at clock_bus and CDC to clock_det
    // note: this signal has been synchronized 2x while sync_in_pulse_bus and sync_in_pulse_det only 1x
    //       this is intended for proper working!
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] sync_in_tgl_cdc_det;
    always @ ( posedge clk_det ) begin
        sync_in_tgl_cdc_det <= {sync_in_tgl_cdc_det[SYNC-2:0],sync_in_tgl_bus};
    end
    wire sync_in_tgl_bus_det = sync_in_tgl_cdc_det[SYNC-1];
        
    // auto-sync enable CDC from clock_bus to clock_det
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] as_en_det_cdc;
    always @ ( posedge clk_det ) begin
        as_en_det_cdc <= {as_en_det_cdc[SYNC-2:0],as_active};
    end
    wire as_en_det = as_en_det_cdc[SYNC-1];    

    // TODO: convert into general purpose timer/counter module with multiplexed start/stop signals at clk_bus.
    //       we could use this to measure DMA and Ethernet transmission rates as in paper.
    //       auto-sync phase detection should also work at clk_bus. 
    // auto_sync timer/detector @ clock_det
    // measures the round-trip pulse time at detection phase
    sync_timer # (
        .PULSE_LENGTH(PULSE_LENGTH),
        .PULSE_WAIT(PULSE_WAIT),
        .PULSE_NUM_MAX(PULSE_NUM_MAX),
        .TIME_BITS(TIME_BITS),
        .DELAY_BITS(DELAY_BITS)
        )
    timer (  
        .clock_det(clk_det),
        .reset_n_det(reset_det_n),
        .as_en(as_en_det),                      // @ clock_det
        .as_prim(1'b0),                         // @ clock_det
        .sync_in_tgl_bus(sync_in_tgl_bus_det),  // sync_in sampled at clk_bus and CDC to clk_det
        .sync_in_tgl_det(sync_in_tgl_det),      // sync_in sampled at clk_det
        .sync_mon(sync_mon),                    // @ clock_det
        .as_timeout(as_timeout),                // @ clock_det
        .sync_time(sync_time),                  // @ clock_det
        .as_done(as_done)                       // @ clock_det
        );
          
    /* as_done CDC from clock_det to clock_bus
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] as_done_cdc_bus;
    always @ ( posedge clk_bus ) begin
        as_done_cdc_bus <= {as_done_cdc_bus[SYNC-2:0],as_done};
    end
    wire as_done_bus = as_done_cdc_bus[SYNC-1];
    */
    
        
endmodule
