`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// test bed for auto_sync module
// created 16/2/2021 by Andi
//////////////////////////////////////////////////////////////////////////////////

module auto_sync_tb # (
	// auto-sync pulse time + 
    parameter integer PULSE_LENGTH = 2,             // 2 = 40ns @ 50MHz
    parameter integer PULSE_WAIT = 1,               // 3 = 60ns @ 50MHz, wait time after pulse
    parameter integer PULSE_NUM_MAX = 2,            // 2 = primary board, 1 = secondary board
    // auto-sync time bits
    parameter integer TIME_BITS = 4,                // 4x8
    // phase shift bits
    parameter integer PHASE_BITS  = 12,             // 12    
    // delay bits
    parameter integer DELAY_BITS = 4               // 10     
)
(
    // no inputs or outputs for test bench    
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
    
    // phase shift detection clock in ns
    localparam integer PHASE                = 9; // ns
    
    // trigger delay time
    localparam integer SYNC_DELAY           = 10; // cycles
    
    // primary "TRUE" or secondary board "FALSE"
    localparam PRIMARY                      = "TRUE"; // "TRUE" or "FALSE"
    
    // clock and reset settings
    localparam integer PERIOD               = 20; // ns
    localparam integer PERIOD_FAST          = 15; // ns
    localparam integer RESET_CYCLES         = 5; // cycles
    
    // phase shift
    localparam integer PHASE_360            = 1120; // steps for 360 degree phase shift
    localparam integer EXT_PHASE            = 6;    // steps
    localparam integer DET_PHASE            = 4;    // steps
    localparam integer EXT_PHASE_CYCLES     = 2;    // cycles to complete one step
    localparam integer DET_PHASE_CYCLES     = 3;    // cycles to complete one step
    
    // pulse
    localparam integer PULSE_NUM            = 3;    // number of pulses
    localparam integer PULSE_DELAY_START    = 9;    // delay in ns before pulse starts
    localparam integer PULSE_DELAY_END      = 4;    // pulse prolongation in ns after PULS_LENGTH*PERIOD ns
    
    // clock generator clock for IO and phase shift
    reg clock_fast;
    initial begin
        clock_fast = 1'b0;
        forever begin
        clock_fast = #(PERIOD_FAST/2) ~clock_fast;
        end
    end
    
    // clock generator for auto-sync clock
    reg clock;
    initial begin
        clock = 1'b0;
        forever begin
        clock = #(PERIOD/2) ~clock;
        end
    end

    // clock generator for detector clock
    reg clock_det;
    initial begin
        clock_det = 1'b0;
        #(PHASE)                // phase shift
        forever begin
        clock_det = #(PERIOD/2) ~clock_det;
        end
    end

    // reset for RESET_CYCLES cycles phase shift clock
    reg reset_n_fast;
    initial begin
        reset_n_fast = 1'b0;
        repeat (RESET_CYCLES) @(posedge clock_fast);
        reset_n_fast = 1'b1;
    end
    
    // reset for RESET_CYCLES cycles auto-sync clock
    reg reset_n;
    initial begin
        reset_n = 1'b0;
        repeat (RESET_CYCLES) @(posedge clock);
        reset_n = 1'b1;
    end

    // DUT
    reg ps_done_ext_en_sim;
    reg ps_done_det_en_sim;
    reg ps_done_ext = 1'b0;
    reg ps_done_det = 1'b0;
    wire ps_inc_ext;
    wire ps_inc_det;
    wire ps_en_ext;
    wire ps_en_det;
    wire sync_out;
    wire sync_mon;
    reg sync_in_sim;
    reg clk_int_locked_sim;
    reg clk_ext_locked_sim;
    reg as_en_sim;
    reg as_prim_sim;
    reg ps_start_sim;
    wire as_active;
    wire as_timeout;
    wire ps_active;
    wire [(4*TIME_BITS)-1:0] sync_time;
    reg [PHASE_BITS-1:0] ps_phase_ext_sim;
    reg [PHASE_BITS-1:0] ps_phase_det_sim;
    reg [DELAY_BITS-1:0] sync_delay_sim;
    wire trg_out;
    auto_sync # (
        .PULSE_LENGTH(PULSE_LENGTH),
        .PULSE_WAIT(PULSE_WAIT),
        .PULSE_NUM_MAX(PULSE_NUM_MAX),
        .TIME_BITS(TIME_BITS),
        .PHASE_BITS(PHASE_BITS),
        .DELAY_BITS(DELAY_BITS)
        )
    DUT (
        // clock and reset
        .clock_IO(clock_fast),
        .clock_bus(clock),
        .clock_det(clock_det),    // phase shifted clock with respect to clock
        .reset_n_IO(reset_n_fast),
        .reset_n_bus(reset_n),
        
        // dynamic phase shifting @ clock_fast
        .ps_done_ext(ps_done_ext & ps_done_ext_en_sim),
        .ps_en_ext(ps_en_ext),
        .ps_inc_ext(ps_inc_ext),
        .ps_done_det(ps_done_det & ps_done_det_en_sim),
        .ps_en_det(ps_en_det),
        .ps_inc_det(ps_inc_det),
        
        // auto-sync inputs and outputs
        .sync_out(sync_out),
        .sync_mon(sync_mon),
        .sync_in(sync_in_sim),
        
        // control bits
        .clk_int_locked(clk_int_locked_sim),
        .clk_ext_locked(clk_ext_locked_sim),
        .as_en(as_en_sim),
        .as_prim(as_prim_sim),
        .ps_start(ps_start_sim),
        
        // status bits
        .as_active(as_active),
        .as_timeout(as_timeout),
        .ps_active(ps_active),
        
        // measured round-trip time {t1_PS,t0_PS,t1,t0}
        .sync_time(sync_time),
        
        // trigger delay
        .sync_delay(sync_delay_sim),
        .trg_out(trg_out),
    
        // phase shift
        .ps_phase({ps_phase_ext_sim,ps_phase_det_sim})
        
        );
        
    // auto-generation of ps_done signal @ clock_fast
    localparam integer EXT_COUNT_BITS = clogb2(EXT_PHASE_CYCLES-1);
    reg [EXT_COUNT_BITS-1:0] ps_ext_count = 0;
    reg [PHASE_BITS-1:0] ps_done_ext_count = 0;
    always @ ( posedge clock_fast ) begin 
        if ( ps_en_ext && ( ps_ext_count == 0) ) begin
            ps_ext_count <= EXT_PHASE_CYCLES-1;
            ps_done_ext <= 1'b0;
        end
        else if ( ps_ext_count > 0 ) begin
            ps_ext_count <= ps_ext_count - 1;
            ps_done_ext <= (ps_ext_count == 1) ? 1'b1 : 1'b0;
        end
        else begin
            ps_ext_count <= 0;
            ps_done_ext <= 0;
        end
        ps_done_ext_count <= (ps_done_ext) ? ps_done_ext_count + 1 : ps_done_ext_count;
    end

    localparam integer DET_COUNT_BITS = clogb2(DET_PHASE_CYCLES-1);
    reg [DET_COUNT_BITS-1:0] ps_det_count = 0;
    reg [PHASE_BITS-1:0] ps_done_det_count = 0;
    always @ ( posedge clock_fast ) begin 
        if ( ps_en_det && ( ps_det_count == 0) ) begin
            ps_det_count <= DET_PHASE_CYCLES-1;
            ps_done_det <= 1'b0;
        end
        else if ( ps_det_count > 0 ) begin
            ps_det_count <= ps_det_count - 1;
            ps_done_det <= (ps_det_count == 1) ? 1'b1 : 1'b0;
        end
        else begin
            ps_det_count <= 0;
            ps_done_det <= 0;
        end
        ps_done_det_count <= (ps_done_det) ? ps_done_det_count + 1 : ps_done_det_count;
    end

    // simulation
    integer i = 0;
    initial begin
        $display("%d *** start simulation *** ", $time);
      
        // init registers
        ps_done_ext_en_sim  = 1'b1;         // enable ps_done_ext
        ps_done_det_en_sim  = 1'b1;         // enable ps_done_det
        sync_in_sim         = 1'b1;         // simulates pulse
        clk_ext_locked_sim  = 1'b1;         // external clock is locked
        clk_int_locked_sim  = 1'b1;         // internal clock is locked
        as_en_sim           = 1'b0;         // auto-sync enable = start
        as_prim_sim         = 1'b0;         // auto-sync primary board = pulse generation
        ps_start_sim        = 1'b0;         // phase shift start
        sync_delay_sim      = SYNC_DELAY;   // delay time in clock cycles
        ps_phase_ext_sim    = EXT_PHASE;    // external clock phase shift in steps
        ps_phase_det_sim    = DET_PHASE;    // detection clock phase shift in steps
        
        // wait for reset to finish
        #1
        while( reset_n_fast == 1'b0 ) begin
            @(posedge clock_fast);
            #1;
        end
        while( reset_n == 1'b0 ) begin
            @(posedge clock);
            #1;
        end
        
        // start phase shift
        repeat(5) @(posedge clock_fast);
        #1
        ps_start_sim = 1'b1;
        @(posedge clock_fast);
        #1
        ps_start_sim = 1'b0;
        #1
        while( ps_active == 1'b0 ) begin
            @(posedge clock_fast);
            #1;
        end
        $display("%d phase shift ext/det %d/%d active", $time, EXT_PHASE, DET_PHASE);
        if (0) begin    // simulate clock loss during phase shift
            repeat(7) @ (posedge clock_fast);
            #1
            clk_int_locked_sim <= 1'b0; 
            repeat(10) @ (posedge clock_fast);
            #1
            clk_int_locked_sim <= 1'b1;
        end
        while( ps_active == 1'b1 ) begin
            @(posedge clock_fast);
            #1;
        end
        if ( (ps_done_ext_count == EXT_PHASE ) && ( ps_done_det_count == DET_PHASE ) ) begin
            $display("%d phase shift ext/det %d/%d done ok", $time, ps_done_ext_count, ps_done_det_count);
        end
        else begin
            $display("%d phase shift ext/det %d/%d done but wrong count!", $time, ps_done_ext_count, ps_done_det_count);
            $finish;
        end

        // start auto-sync
        repeat(5) @(posedge clock);
        #1
        as_en_sim = 1'b1;
        if ( PRIMARY == "TRUE" )
            as_prim_sim = 1'b1;
        else
            as_prim_sim = 1'b0;
        
        // generate pulses
        repeat(3) @( posedge clock );
        for (i = 0; i < PULSE_NUM; i=i+1) begin
            #(PULSE_DELAY_START)
            sync_in_sim = 1'b0;
            #(PULSE_LENGTH*PERIOD)
            #(PULSE_DELAY_END)
            sync_in_sim = 1'b1;
            repeat(6) @( posedge clock );
        end
        
        while(as_active) begin
            @ ( posedge clock );
            #1;
        end

        repeat(5) @(posedge clock);
        
        if ( as_timeout ) begin
            $display("%d timeout detected!", $time);
            $finish;
        end

        $display("%d phase %d ns sync_time 0x%x", $time, PHASE, sync_time);
        $display("%d *** finished *** ", $time);
        $finish;
    end    
endmodule