`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// sync_timer module
// clock = all in/out ports are at this clock, except sync_in is not synchronized
// clock_PS = phase shifted clock
// sync_in is sampled at clock and clock_PS simultaneously
// created 11/02/2021 by Andi
// last change 15/03/2021
//////////////////////////////////////////////////////////////////////////////////

module sync_timer # (
    parameter integer PULSE_LENGTH  = 3,
    parameter integer PULSE_WAIT    = 5,
    parameter integer PULSE_NUM_MAX = 2,
    parameter integer TIME_BITS = 8,
    parameter integer DELAY_BITS = 12  
)(
    input wire clock_det,
    input wire reset_n_det,
    
    input wire as_en,
    input wire as_prim,
    input wire sync_in_bus,                     // sync_in sampled at clk_bus and CDC to clk_det
    input wire sync_in_det,                     // sync_in sampled at clk_det
    output wire sync_mon,
    output wire as_timeout,
    output wire [4*TIME_BITS-1:0] sync_time,
    output wire as_done
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

    localparam integer TIME_MAX = {(TIME_BITS){1'b1}};
    localparam integer COUNT_BITS = clogb2(PULSE_NUM_MAX);
    localparam integer WAIT_TIME = PULSE_LENGTH + PULSE_WAIT; 

    // sync_in_bus edge detector
    reg sync_in_bus_ff;
    always @ ( posedge clock_det ) begin
        sync_in_bus_ff <= sync_in_bus;
    end
    wire [1:0] sync_in_bus_edge = {sync_in_bus_ff,sync_in_bus};

    // sync_in_det edge detector
    reg sync_in_det_ff;
    always @ ( posedge clock_det ) begin
        sync_in_det_ff <= sync_in_det;
    end
    wire [1:0] sync_in_det_edge = {sync_in_det_ff,sync_in_det};

    // enable edge detector
    reg as_en_ff;
    always @ ( posedge clock_det ) begin
        as_en_ff <= as_en;
    end
    wire [1:0] as_en_edge = {as_en_ff, as_en};
    
    localparam integer STATE_IDLE       = 0;
    localparam integer STATE_PRIM_WAIT  = 1;
    localparam integer STATE_SEC_WAIT   = 2;
    localparam integer STATE_TIMER      = 3;
    localparam integer STATE_OUTPUT     = 4;
    localparam integer STATE_BITS = clogb2(STATE_OUTPUT);

    // sync count timer states delayed to fix a hold time violation
    reg [TIME_BITS-1:0] sync_count;
    reg sc_wait_end = 1'b0;
    reg sc_timeout = 1'b0;
    always @ ( posedge clock_det ) begin
        sc_wait_end <= (sync_count >= WAIT_TIME);
        sc_timeout <= (sync_count == (TIME_MAX-1));
    end
    
    // timer
    reg [COUNT_BITS-1:0] pulse_count;
    reg [TIME_BITS-1:0] sync_time0_ff;
    reg [TIME_BITS-1:0] sync_time1_ff;
    reg [TIME_BITS-1:0] sync_time0_PS_ff;
    reg [TIME_BITS-1:0] sync_time1_PS_ff;
    reg [STATE_BITS-1:0] state;
    reg as_timeout_ff;
    reg as_detect_ff;               // monitor detection
    reg as_done_ff;
    always @ ( posedge clock_det ) begin
        if ( reset_n_det == 1'b0 ) begin
            state <= STATE_IDLE;
            sync_count <= 1;
            pulse_count <= 0;
            sync_time0_ff <= 0;
            sync_time1_ff <= 0;
            sync_time0_PS_ff <= 0;
            sync_time1_PS_ff <= 0;
            as_timeout_ff <= 1'b0;
            as_detect_ff <= 1'b0;
            as_done_ff <= 1'b0;
        end
        else if ( state == STATE_PRIM_WAIT ) begin
            state <= sc_timeout ? STATE_OUTPUT : sc_wait_end ? STATE_TIMER : state;
            sync_count <= sync_count + 1;
            pulse_count <= 0; 
            sync_time0_ff <= 0;
            sync_time1_ff <= 0;
            sync_time0_PS_ff <= 0;
            sync_time1_PS_ff <= 0;
            as_detect_ff <= sc_wait_end ? sync_in_det : 1'b0;
            as_timeout_ff <= sc_timeout ? 1'b1 : 1'b0;
            as_done_ff <= 1'b0;
        end
        else if ( state == STATE_SEC_WAIT ) begin
            state <= ( sync_in_det_edge == 2'b10 ) ? STATE_TIMER : state;
            sync_count <= 1;
            pulse_count <= 0; 
            sync_time0_ff <= 0;
            sync_time1_ff <= 0;
            sync_time0_PS_ff <= 0;
            sync_time1_PS_ff <= 0;
            as_detect_ff <= sync_in_det;
            as_timeout_ff <= 1'b0;
            as_done_ff <= 1'b0;
        end
        else if ( state == STATE_TIMER ) begin
            state <= sc_timeout || ( pulse_count >= PULSE_NUM_MAX ) ? STATE_OUTPUT : state;
            sync_count <= sync_count + 1;
            pulse_count <= ( sync_in_bus_edge == 2'b01 ) ? pulse_count + 1 : pulse_count; // pulse finished on positive edge @ clock
            sync_time0_ff <= ( sync_in_bus_edge == 2'b10 ) ? sync_count : sync_time0_ff; // negative edge @ clock
            sync_time1_ff <= ( sync_in_bus_edge == 2'b01 ) ? sync_count : sync_time1_ff; // positive edge @ clock
            sync_time0_PS_ff <= ( sync_in_det_edge == 2'b10 ) ? sync_count : sync_time0_PS_ff; // negative edge @ clock_det
            sync_time1_PS_ff <= ( sync_in_det_edge == 2'b01 ) ? sync_count : sync_time1_PS_ff; // positive edge @ clock_det
            as_detect_ff <= sync_in_det;
            as_timeout_ff <= 1'b0;
            as_done_ff <= 1'b0;
        end
        else if ( state == STATE_OUTPUT ) begin
            state <= STATE_IDLE;
            sync_count <= 1;
            pulse_count <= pulse_count;
            sync_time0_ff <= sync_time0_ff;
            sync_time1_ff <= sync_time1_ff;
            sync_time0_PS_ff <= sync_time0_PS_ff;
            sync_time1_PS_ff <= sync_time1_PS_ff;
            as_timeout_ff <= ((sync_time0_ff==0)||(sync_time1_ff==0)||(sync_time1_PS_ff==0));
            as_detect_ff <= 1'b0;
            as_done_ff <= 1'b1;
        end
        else begin // idle state
            if ( as_en_edge == 2'b01 ) begin
                state <= as_prim ? STATE_PRIM_WAIT : STATE_SEC_WAIT;
                pulse_count <= 0;
                sync_time0_ff <= 0;
                sync_time1_ff <= 0;
                sync_time0_PS_ff <= 0;
                sync_time1_PS_ff <= 0;
                as_timeout_ff <= 1'b0;
                as_detect_ff <= 1'b1;
            end
            else begin
                state <= STATE_IDLE;
                pulse_count <= pulse_count;
                sync_time0_ff <= sync_time0_ff;
                sync_time1_ff <= sync_time1_ff;
                sync_time0_PS_ff <= sync_time0_PS_ff;
                sync_time1_PS_ff <= sync_time1_PS_ff;
                as_timeout_ff <= as_timeout_ff;
                as_detect_ff <= 1'b0;
            end
            sync_count <= 1;
            as_done_ff <= 1'b0;
        end
    end

    // assign outputs
    assign as_timeout = as_timeout_ff;
    assign sync_time = {sync_time1_PS_ff,sync_time0_PS_ff,sync_time1_ff,sync_time0_ff};
    assign as_done = as_done_ff;
    assign sync_mon = as_detect_ff;
    
endmodule
