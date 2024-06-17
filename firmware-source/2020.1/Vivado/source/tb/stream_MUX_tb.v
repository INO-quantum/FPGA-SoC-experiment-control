`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// test bench for stream_MUX module
// created 03/10/2020 by Andi
// last change 03/10/2020 by Andi
//////////////////////////////////////////////////////////////////////////////////

module stream_MUX_tb # (
    parameter integer DATA_WIDTH  = 32,
    parameter OUT_BUF = "FALSE"             // "TRUE" or "FALSE" (default)
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
    localparam integer PERIOD               = 10;
    localparam integer RESET_CYCLES         = 5;
    
    // number of input ports (fixed)
    localparam integer NUM_INPUT            = 2;
    
    // samples
    localparam [32*NUM_INPUT-1 : 0] NUM_SAMPLES = { 32'd11132, 32'd25 };
    localparam [32*NUM_INPUT-1 : 0] DATA_START  = { 32'hf2f10000, 32'h00000201 };
    localparam [32*NUM_INPUT-1 : 0] DATA_STEP   = { 32'h01010000, 32'h00000101 };    
    
    // clock generator
    reg clock;
    initial begin
        clock = 1'b0;
        forever begin
        clock = #(PERIOD/2) ~clock;
        end
    end
    
    // reset for RESET_CYCLES cycles
    reg reset_n;
    initial begin
        reset_n = 1'b0;
        repeat (RESET_CYCLES) @(posedge clock);
        reset_n = 1'b1;
    end
    
    // select input stream
    reg sim_in_select;
    reg rnd_in_en;
    
    // data generator 0 and 1
    reg [1:0] sim_in_en;
    wire [DATA_WIDTH-1 : 0] in_data [0:1];
    wire [1:0] in_last;
    wire [1:0] in_valid;
    wire [1:0] in_ready;
    generate 
    for (genvar i = 0; i < NUM_INPUT; i = i + 1) begin : TX
        AXI_stream_generator # (
            .DATA_WIDTH(DATA_WIDTH),
            .SAMPLES_WIDTH(clogb2(NUM_SAMPLES[32*i +: 32])),
            .DATA_START(DATA_START[32*i +: 32]),
            .DATA_STEP(DATA_STEP[32*i +: 32]),
            .NUM_SAMPLES(NUM_SAMPLES[32*i +: 32])
        )
        gen
        (
            // clock and reset
            .clock(clock),
            .reset_n(reset_n),
            // output enable
            .out_enable(sim_in_en[i] & rnd_in_en),
            // stream data output
            .out_data(in_data[i]),
            .out_last(in_last[i]),
            .out_valid(in_valid[i]),
            .out_ready(in_ready[i])
        );
    end
    endgenerate

    // output stream
    wire [DATA_WIDTH-1 : 0] out_data;
    wire out_last;
    wire out_valid;
    reg sim_out_ready;
    reg rnd_out_ready;
    wire out_ready = sim_out_ready & rnd_out_ready;

    // DUT
    stream_MUX # (
        .DATA_WIDTH(DATA_WIDTH+1),
        .OUT_BUF(OUT_BUF)
    )
    DUT (
        // clock and reset
        .clock(clock),
        .reset_n(reset_n),
        // input selection
        .in_select(sim_in_select),
        // stream data input 0
        .in_data_0({in_last[0],in_data[0]}),
        .in_valid_0(in_valid[0]),
        .in_ready_0(in_ready[0]),
        // stream data input 1
        .in_data_1({in_last[1],in_data[1]}),
        .in_valid_1(in_valid[1]),
        .in_ready_1(in_ready[1]),
        // stream data output
        .out_data({out_last,out_data}),
        .out_valid(out_valid),
        .out_ready(out_ready)
    );
    
    // RX reader
    localparam integer NUM_BITS = clogb2(NUM_SAMPLES[63:32] + NUM_SAMPLES[31:0]);
    reg [NUM_BITS-1:0] RX_samples = 0;
    reg [DATA_WIDTH-1:0] RX_data = 0;
    reg RX_last =  1'b0;
    always @ ( posedge clock ) begin
        if ( out_valid & out_ready ) begin
            RX_samples <= RX_samples + 1;
            RX_data <= out_data;
            RX_last <= out_last;
        end
    end
    
    // check RX data consistency
    reg [DATA_WIDTH-1:0] test;
    initial begin
        forever begin
            @(posedge clock)
            if ( out_valid & out_ready ) begin
                test = ( sim_in_select ) ? (DATA_START[32*1 +: 32] + RX_samples * DATA_STEP[32*1 +: 32]) :
                                           (DATA_START[32*0 +: 32] + RX_samples * DATA_STEP[32*0 +: 32]);
                if ( out_data != test ) begin
                    $display("%d *** error out_data! *** ", $time);
                    $display("%d *** %x != %x *** ", $time/PERIOD, out_data, test);
                    $finish;
                end
                #1
                test = ( sim_in_select ) ? (DATA_START[32*1 +: 32] + (RX_samples-1) * DATA_STEP[32*1 +: 32]) :
                                           (DATA_START[32*0 +: 32] + (RX_samples-1) * DATA_STEP[32*0 +: 32]);
                if ( RX_data != test ) begin
                    $display("%d *** error RX_data! *** ", $time);
                    $display("%d *** %x != %x *** ", $time/PERIOD, RX_data, test);
                    $finish;
                end
            end
        end
    end
    
    // randomly stop TX channel
    integer delay_TX;
    reg sim_rnd_TX_en;
    initial begin
        $srandom(32'h98a4);
        rnd_in_en = 1'b1;
        forever begin
            if (sim_rnd_TX_en) begin
                delay_TX = $urandom_range(1,5);
                //$display("%d: %d - %d", $time/PERIOD, rnd_out_ready, delay);
                repeat(delay_TX) @(posedge clock); 
                #1 rnd_in_en = 1'b0;
                delay_TX = $urandom_range(1,5);
                //$display("%d: %d - %d", $time/PERIOD, rnd_out_ready, delay);
                repeat(delay_TX) @(posedge clock);
                #1 rnd_in_en = 1'b1;
            end
            else begin
                @(posedge clock);
                #1 rnd_in_en = 1'b1;
            end
        end
    end
    
    // randomly stop RX channel
    integer delay_RX;
    reg sim_rnd_RX_en;
    initial begin
        $srandom(32'h1a03);
        rnd_out_ready = 1'b1;
        forever begin
            if (sim_rnd_RX_en) begin
                delay_RX = $urandom_range(1,5);
                //$display("%d: %d - %d", $time/PERIOD, rnd_out_ready, delay);
                repeat(delay_RX) @(posedge clock); 
                #1 rnd_out_ready = 1'b0;
                delay_RX = $urandom_range(1,5);
                //$display("%d: %d - %d", $time/PERIOD, rnd_out_ready, delay);
                repeat(delay_RX) @(posedge clock);
                #1 rnd_out_ready = 1'b1;
            end
            else begin
                @(posedge clock);
                #1 rnd_out_ready = 1'b1;
            end
        end
    end
    
    // simulation
    initial begin
        $display("%d *** start simulation *** ", $time/PERIOD);
      
        // init registers
        sim_in_select = 1'b1;   // input selection
        sim_in_en     = 2'b00;  // enable TX 0/1
        sim_out_ready = 1'b0;   // enable RX ready
        sim_rnd_TX_en = 1'b0;   // random TX enable
        sim_rnd_RX_en = 1'b0;   // random RX ready enable
        
        // wait for reset to finish
        while( reset_n == 1'b0 ) begin
            #1 @(posedge clock);
        end
        
        // enable TX channels
        repeat(5) @(posedge clock);
        #1 sim_in_en = 2'b11;
        
        if(1) begin // set RX ready
            repeat(10) @(posedge clock);
            #1 sim_out_ready = 1'b1;
        end
        
        if(1) begin // enable random TX/RX valid/ready signal
            repeat(10) @(posedge clock);
            #1 
            sim_rnd_TX_en = 1'b1;
            sim_rnd_RX_en = 1'b1;
        end
        else begin
            repeat(10) @(posedge clock);
            #1;
        end
                
        // wait until all samples transmitted
        while ( (RX_samples != ((sim_in_select) ? NUM_SAMPLES[63:32] : NUM_SAMPLES[31:0])) || (RX_last != 1'b1)) begin
            @(posedge clock);
            #1;
        end

        repeat(2) @(posedge clock);
        #1 
        sim_rnd_TX_en = 1'b0;
        sim_rnd_RX_en = 1'b0;
    
        repeat(20) @(posedge clock);

        $display("%d *** finished *** ", $time/PERIOD);
        $finish;
    end    
endmodule
