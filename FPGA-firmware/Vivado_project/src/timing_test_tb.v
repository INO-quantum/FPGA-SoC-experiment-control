`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// test bench for timing_test module
// created 30/09/2020 by Andi
// last change 01/10/2020 by Andi
//////////////////////////////////////////////////////////////////////////////////

module timing_test_tb # (
    // AXI stream bus
    parameter integer STREAM_DATA_WIDTH  = 128,
    
    // AXI Lite slave bus
    parameter integer AXI_DATA_WIDTH = 32,
    parameter integer AXI_ADDR_WIDTH = 5,
    
    // data and time bits
    parameter integer TIME_BITS = 32,       // must be 32
    parameter integer TIME_START = 0,       // typically 0
    parameter integer DATA_BITS = 32,       // must be 32
    parameter integer DATA_START_64 = 32,   // typically 32
    parameter integer DATA_START_96_0 = 32, // typically 32
    parameter integer DATA_START_96_1 = 64, // typically 64
    
    // bus data and address bits
    parameter integer BUS_DATA_BITS = 16,
    parameter integer BUS_ADDR_BITS = 7,
    
    // special data bits
    parameter integer BIT_NOP = 31,             // 31
    parameter integer BIT_IRQ = 30,             // 30
    parameter integer BIT_NUM = 29,             // 29
    
        // dio24_timing parameters
    parameter integer CLK_DIV = 50,             // must be >= 4
    parameter integer STRB_DELAY = 12,
    parameter integer STRB_LEN = 25, 
    parameter integer SYNC = 2,                 // 2-3

    // trigger delay
    parameter integer TRG_DELAY_IN = 41,        // >= 0
    parameter integer TRG_DELAY_OUT = 0,        // 0 - (CLK_DIV-1)

    // irq_FPGA frequency in Hz @ clock/CLK_DIV = 1MHz, power of 2
    parameter integer IRQ_FREQ = 2000000,

    // TX and RX FIFO settings
    parameter integer TX_FIFO_DEPTH = 4096,     // power of 2
    parameter integer RX_FIFO_DEPTH = 16,     // power of 2, >= 16
    
    parameter integer DMA_BUF_SIZE = 8         // DMA buffer size in samples
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
    
    // clock and reset settings
    localparam integer PERIOD_FAST          = 10;
    localparam integer PERIOD_SLOW          = 22;
    localparam integer RESET_CYCLES_SLOW    = 5;
    localparam integer RESET_CYCLES_FAST    = RESET_CYCLES_SLOW*PERIOD_SLOW/PERIOD_FAST;
    
    // samples
    localparam integer NUM_SAMPLES          = 52;
    localparam [31:0] DTIME_START           = 32'd1;
    localparam [31:0] DTIME_STEP            = 32'd1;
    localparam [31:0] DATA_START            = 32'h04030201;
    localparam [31:0] DATA_STEP             = 32'h01010101;
    
    // start timer options
    localparam integer PERF_START_RUN_UP    = 2'b00;
    localparam integer PERF_START_DATA      = 2'b01;
    localparam integer PERF_START_IRQ_UP    = 2'b10;
    localparam integer PERF_START_IRQ_DN    = 2'b11;

    // update sample time options
    localparam integer PERF_UPD_RUN_DN      = 2'b00;
    localparam integer PERF_UPD_DATA        = 2'b01;
    localparam integer PERF_UPD_IRQ_UP      = 2'b10;
    localparam integer PERF_UPD_IRQ_DN      = 2'b11;
    
    // IRQ settings
    localparam integer PERF_IRQ_NONE        = 2'b00;
    localparam integer PERF_IRQ_TX          = 2'b01;
    localparam integer PERF_IRQ_RX          = 2'b10;
    localparam integer PERF_IRQ_FPGA_TGL    = 2'b11;
    
    
    // fast clock generator
    reg clock_fast;
    initial begin
        clock_fast = 1'b0;
        forever begin
        clock_fast = #(PERIOD_FAST/2) ~clock_fast;
        end
    end
    
    // slow clock generator
    reg clock_slow;
    initial begin
        clock_slow = 1'b0;
        forever begin
        clock_slow = #(PERIOD_SLOW/2) ~clock_slow;
        end
    end

    // reset for RESET_CYCLES_FAST/SLOW cycles
    reg reset_n_fast;
    initial begin
        reset_n_fast = 1'b0;
        repeat (RESET_CYCLES_FAST) @(posedge clock_fast);
        reset_n_fast = 1'b1;
    end
    reg reset_n_slow;
    initial begin
        reset_n_slow = 1'b0;
        repeat (RESET_CYCLES_SLOW) @(posedge clock_slow);
        reset_n_slow = 1'b1;
    end
    
    // dio24_timing parameters
    localparam integer NUM_BITS  = DATA_BITS;
    
    // simulation control bits
    localparam integer NUM_CTRL = 13;
    wire [NUM_CTRL-1:0] ctrl;
    reg sim_test_RX;
    reg sim_test_TX;
    reg [1:0] ctrl_irq_en = 2'b11;
    reg ctrl_error_ext = 1'b0;
    reg sim_ctrl_num_reload;
    reg sim_ctrl_run;
    reg [1:0] sim_test_start;
    reg [1:0] sim_test_update;
    reg [1:0] sim_test_irq;
    assign ctrl = {sim_test_irq,sim_test_update,sim_test_start[1],sim_test_RX,sim_test_TX,ctrl_irq_en,ctrl_error_ext,sim_ctrl_num_reload,sim_test_start[0],sim_ctrl_run}; 
    
    localparam integer NUM_STATUS = 9;
    wire [NUM_STATUS-1:0] status;

    // number of samples    
    reg [NUM_BITS-1:0] num_samples = NUM_SAMPLES;

    // board time and samples
    wire [TIME_BITS-1:0] board_time;
    wire [NUM_BITS-1:0] board_samples;
    
    // irq bits
    reg sim_irq_TX;
    reg sim_irq_RX;
    
    // output stream
    wire [TIME_BITS + DATA_BITS - 1 : 0] out_data;
    wire out_last;
    wire out_valid;
    reg sim_out_ready;  // direct simulation controlled
    reg rnd_out_ready;  // allows random control
    wire out_ready = sim_out_ready & rnd_out_ready;
    
    // TX data generator
    wire [NUM_BITS-1:0] TX_samples;
    wire [DATA_BITS+TIME_BITS-1:0] TX_data;
    wire TX_last;
    reg sim_in_valid;
    reg rnd_in_en;
    wire TX_en = sim_in_valid & rnd_in_en;
    wire in_valid;
    wire in_ready;
    localparam [TIME_BITS+DATA_BITS-1:0] DDATA_START = {DATA_START,DTIME_START};
    localparam [TIME_BITS+DATA_BITS-1:0] DDATA_STEP  = {DATA_STEP ,DTIME_STEP};
    data_gen # (
        .DATA_WIDTH(TIME_BITS + DATA_BITS),
        .SAMPLES_WIDTH(NUM_BITS),
        .DATA_START(DDATA_START),
        .DATA_STEP(DDATA_STEP),
        .NUM_SAMPLES(NUM_SAMPLES)
    )
    gen
    (
        // clock and reset
        .clock(clock_fast),
        .reset_n(reset_n_fast),
        // output enable
        .out_enable(TX_en),
        // stream data output
        .out_data(TX_data),
        .out_last(TX_last),
        .out_valid(in_valid),
        .out_ready(in_ready),
        // number of generated samples
        .num_samples(TX_samples)
    );

    // DUT
    dio24_timing_test # (
        .STREAM_DATA_BITS(TIME_BITS + DATA_BITS + 1),
        .TIME_BITS(TIME_BITS),
        .BUS_DATA_BITS(BUS_DATA_BITS),
        .BUS_ADDR_BITS(BUS_ADDR_BITS),
        .NUM_BITS(NUM_BITS),
        .NUM_CTRL(NUM_CTRL),       // number of control bits
        .NUM_STATUS(NUM_STATUS),     // number of status bits
        .BIT_NOP(BIT_NOP),
        .BIT_IRQ(BIT_IRQ),
        .BIT_NUM(BIT_NUM),
        .CLK_DIV(CLK_DIV),
        .STRB_DELAY(STRB_DELAY),
        .STRB_LEN(STRB_LEN),
        .SYNC(SYNC),
        .TRG_DELAY_IN(TRG_DELAY_IN),
        .TRG_DELAY_OUT(TRG_DELAY_OUT),
        .IRQ_FREQ(IRQ_FREQ),
        .TX_FIFO_DEPTH(TX_FIFO_DEPTH),
        .RX_FIFO_DEPTH(RX_FIFO_DEPTH),
        .DMA_BUF_SIZE(DMA_BUF_SIZE)
    )
    timing (
        // FIFO reset
        .reset_FIFO(),
        // fast clock and reset
        .clock_fast(clock_fast),
        .reset_n_fast(reset_n_fast),
        // slow clock and reset
        .clock_slow(clock_slow),
        .reset_n_slow(reset_n_slow),
        // control bits @ clock_fast
        .control(ctrl),
        .num_samples(num_samples),
        // status bits and board time & samples @ clock_fast
        .status(status),
        .board_time(board_time),
        .board_samples(board_samples),
        .status_update(),   // not used
        // TX stream data input
        .in_data({TX_last,TX_data}),
        .in_valid(in_valid),
        .in_ready(in_ready),
        // RX stream data output
        .out_data({out_last,out_data}),
        .out_valid(out_valid),
        .out_ready(out_ready),
        // bus output
        .bus_data(),
        .bus_addr(),
        .bus_strb(),
        .bus_enable_n(),
        // trigger out and input
        .trg_start_en(1'b0),
        .trg_start(1'b0), 
        .trg_out(),
        // trigger inputs (used by timing_test)
        .irq_TX(sim_irq_TX),
        .irq_RX(sim_irq_RX)
    );
    
    // RX reader
    reg [NUM_BITS-1:0] RX_samples = 0;
    reg [TIME_BITS-1:0] RX_time = 0;
    reg [DATA_BITS-1:0] RX_data = 0;
    reg RX_last =  1'b0;
    always @ ( posedge clock_fast ) begin
        if ( out_valid & out_ready ) begin
            RX_samples <= RX_samples + 1;
            RX_time <= out_data[TIME_BITS-1 : 0];
            RX_data <= out_data[DATA_BITS+TIME_BITS-1 -: DATA_BITS];
            RX_last <= out_last;
        end
    end
    
    // check RX data consistency
    reg [TIME_BITS+DATA_BITS-1:0] test;
    reg [TIME_BITS+DATA_BITS-1:0] mask;
    initial begin
        forever begin
            @(posedge clock_fast)
            if ( out_valid & out_ready ) begin // check output
                test = ( sim_test_TX ) ? (DDATA_START + RX_samples * DDATA_STEP) : {RX_samples+1,32'd0};
                mask = ( sim_test_TX ) ? 64'hffff_ffff_ffff_ffff : 64'hffff_ffff_0000_0000;
                if ( (out_data & mask) != test ) begin
                    $display("%d *** error out_data! *** ", $time);
                    $display("%d *** %x != %x *** ", $time, out_data & mask, test);
                    $finish;
                end
                #1 // check RX data/time
                test = ( sim_test_TX ) ? (DDATA_START + (RX_samples-1) * DDATA_STEP) : {RX_samples,32'd0};
                mask = ( sim_test_TX ) ? 64'hffff_ffff_ffff_ffff : 64'hffff_ffff_0000_0000;
                if ( ({RX_data,RX_time} & mask) != test ) begin
                    $display("%d *** error RX_data! *** ", $time);
                    $display("%d *** %x != %x *** ", $time, ({RX_data,RX_time} & mask), test);
                    $finish;
                end
            end
        end
    end

    // randomly stop TX channel
    integer delay_TX;
    reg sim_rnd_TX_en;
    initial begin
        $srandom(32'h98a5);
        rnd_in_en = 1'b1;
        forever begin
            if (sim_rnd_TX_en) begin
                delay_TX = $urandom_range(1,5);
                //$display("%d: %d - %d", $time/PERIOD, rnd_out_ready, delay);
                repeat(delay_TX) @(posedge clock_fast); 
                #1 rnd_in_en = 1'b0;
                delay_TX = $urandom_range(1,10);
                //$display("%d: %d - %d", $time/PERIOD, rnd_out_ready, delay);
                repeat(delay_TX) @(posedge clock_fast);
                #1 rnd_in_en = 1'b1;
            end
            else begin
                @(posedge clock_fast);
                #1 rnd_in_en = 1'b1;
            end
        end
    end
    
    // randomly stop RX channel
    integer delay_RX;
    reg sim_rnd_RX_en;
    initial begin
        $srandom(32'h1a06);
        rnd_out_ready = 1'b1;
        forever begin
            if (sim_rnd_RX_en) begin
                delay_RX = $urandom_range(1,5);
                //$display("%d: %d - %d", $time/PERIOD, rnd_out_ready, delay);
                repeat(delay_RX) @(posedge clock_fast); 
                #1 rnd_out_ready = 1'b0;
                delay_RX = $urandom_range(1,12);
                //$display("%d: %d - %d", $time/PERIOD, rnd_out_ready, delay);
                repeat(delay_RX) @(posedge clock_fast);
                #1 rnd_out_ready = 1'b1;
            end
            else begin
                @(posedge clock_fast);
                #1 rnd_out_ready = 1'b1;
            end
        end
    end
    
    
    // simulation
    initial begin
        $display("%d *** start simulation *** ", $time);
      
        // init registers
        // TX / RX / TX & RX test set manually
        sim_test_TX = 1'b0;         // enable TX channel
        sim_test_RX = 1'b0;         // enable RX channel: if TX not enabled use PERF_START_RUN_UP
        sim_test_start      = PERF_START_RUN_UP;
        sim_test_update     = PERF_UPD_IRQ_UP;
        sim_test_irq        = PERF_IRQ_FPGA_TGL;
        // other control bits
        sim_ctrl_run = 1'b0;        // run bit
        sim_irq_TX = 1'b0;          // TX irq bit
        sim_irq_RX = 1'b0;          // RX irq bit
        sim_rnd_TX_en = 1'b1;       // random TX valid
        sim_rnd_RX_en = 1'b1;       // random RX ready
        sim_in_valid = 1'b0;        // enable TX data valid
        sim_out_ready = 1'b0;       // enable RX data ready
        sim_ctrl_num_reload = 1'b0;
        
        // wait for reset to finish
        while( (reset_n_fast == 1'b0) || (reset_n_slow == 1'b0)) begin
            @(posedge clock_fast);
        end
        
        // load control registers and number of samples
        repeat(5) @(posedge clock_fast);
        #1
        sim_ctrl_num_reload = 1'b1;
        @(posedge clock_fast);
        #1
        sim_ctrl_num_reload = 1'b0;
        
        // set run bit
        repeat(10) @(posedge clock_fast);
        sim_ctrl_run = 1'b1;
        
        if(1) begin // set RX ready
            repeat(10) @(posedge clock_fast);
            #1 sim_out_ready = 1'b1;
        end
        
        if(1) begin // set TX valid
            repeat(10) @(posedge clock_fast);
            #1 sim_in_valid = 1'b1;
        end
        
        if(1) begin
            if(sim_test_TX) begin // reset TX valid for some time
                repeat(10) @(posedge clock_fast);
                #1 sim_in_valid = 1'b0;
                repeat(20) @(posedge clock_fast);
                #1 sim_in_valid = 1'b1;
                repeat(3) @(posedge clock_fast);
                #1 sim_in_valid = 1'b0;
                repeat(7) @(posedge clock_fast);
                #1 sim_in_valid = 1'b1;
            end
            else begin
                //repeat(30) @(posedge clock_fast);
                #1;
            end
        end
                
        if(1) begin // reset RX ready for some time to produce backpressure when RX FIFO is full
            repeat(25) @(posedge clock_fast);
            #1 sim_out_ready = 1'b0;
            repeat(25) @(posedge clock_fast);
            #1 sim_out_ready = 1'b1;
        end
        else begin
            repeat(50) @(posedge clock_fast);
            #1;
        end
        
        // wait until TX/RX samples transmitted
        if (sim_test_RX) begin
            while ( (RX_samples != NUM_SAMPLES) && (RX_last!=1'b1) ) begin
                @(posedge clock_fast);
                #1;
            end
            repeat(5) @(posedge clock_fast);
            #1 
            sim_rnd_TX_en = 1'b0;
            sim_rnd_RX_en = 1'b0;
        end
        else if ( sim_test_TX ) begin
            while ( TX_samples != NUM_SAMPLES ) begin
                @(posedge clock_fast);
                #1;
            end
            // for TX only stops too early, so give some more time
            if (sim_test_RX == 1'b0) begin 
                repeat(50) @(posedge clock_fast);
            end
            repeat(5) @(posedge clock_fast);
            #1
            sim_rnd_TX_en = 1'b0;
            sim_rnd_RX_en = 1'b0;
        end
        else begin // both channels disabled: just wait some time then stop
            repeat(2000) @(posedge clock_fast);
        end
        
        if (1) begin // pulse TX irq
            repeat(5) @(posedge clock_fast);
            #1 sim_irq_TX = 1'b1;
            repeat(15) @(posedge clock_fast);
            #1 sim_irq_TX = 1'b0;
        end

        if (1) begin // pulse RX irq
            repeat(5) @(posedge clock_fast);
            #1 sim_irq_RX = 1'b1;
            repeat(10) @(posedge clock_fast); // IRQ of 5 slow cycles
            #1 sim_irq_RX = 1'b0;
        end

        // reset run
        repeat(5) @(posedge clock_fast);
        sim_ctrl_run = 1'b0;

        repeat(20) @(posedge clock_fast);

        $display("%d *** finished *** ", $time);
        $finish;
    end    
endmodule