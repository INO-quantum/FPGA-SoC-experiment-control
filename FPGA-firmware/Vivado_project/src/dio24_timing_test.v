`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// timing test module
// use to measure data transmission rates
// created 23/9/2020 by Andi
// same parameters and ports as dio24_timing for easy switching
// functionality:
// - timer starts depending on {CTRL_TEST_START_1,CTRL_TEST_START_0}:
//   2'b00 = run bit rising edge, 2'b01 = first data, 2'b10 = IRQ rising edge, 2'b11 = IRQ falling edge
// - timer stops always with run bit falling edge
// - board time is updated depending on {CTRL_TEST_UPD_1,CTRL_TEST_UPD_0}:
//   2'b00 = run falling edge, 2'b01 = data, 2'b10 = IRQ rising edge, 2'b11 = IRQ falling edge 
// - board samples are updated depending on {CTRL_TEST_RX,CTRL_TEST_TX}:
//   2'b00 = none, 2'b01 = TX data read, 2'b01 = RX data write, 2'b11 = TX data read
// - the IRQ source for start/update depends on {CTRL_TEST_IRQ_1,CTRL_TEST_IRQ_0}:
//   2'b00 = none, 2'b01 = irq_TX, 2'b10 = irq_RX, 2'b11 = irq FPGA toggle bit
// - out_data depends on {CTRL_TEST_RX,CTRL_TEST_TX}:
//   2'b00 = none, 2'b01 = TX data, 2'b01 = RX data, 2'b11 = TX data
//   with RX_data = {last,samples,timer} where timer = time of sample, samples = # samples
//   and last is high for every full buffer and for last sample = num_samples.
//   when num_samples reached no further data is output to RX channel.
// last change 12/04/2021 by Andi
//////////////////////////////////////////////////////////////////////////////////

module dio24_timing_test # (
    // AXI stream data input
    parameter integer STREAM_DATA_BITS = 65,    // 64 + 1 {in_last,in_data}
    
    // data bits
    parameter integer BUS_DATA_BITS = 16,       // 16
    parameter integer BUS_ADDR_BITS = 7,        // 7    
    parameter integer REG_BITS    = 32,         // 32
    parameter integer CTRL_BITS   = 7,          // 7
    parameter integer TEST_BITS   = 10,         // 10
    parameter integer STATUS_BITS = 9,          // 9
    
    // trigger delay register bits = {0s,phase_bits,out_bits,in_bits}
    parameter integer TRG_DELAY_IN_BITS     = 10,               // 10
    parameter integer TRG_DELAY_OUT_BITS    = 10,               // 10
    //parameter integer TRG_DELAY_PHASE_BITS  = 11,               // 11     
    
    // special data bits
    parameter integer BIT_NOP = 31,             // 31
    parameter integer BIT_IRQ = 30,             // 30
    //parameter integer BIT_NUM = 29,             // 29
    
    // timing
    parameter integer CLK_DIV    = 50,             // must be >= 4
    parameter integer STRB_DELAY = 12,
    parameter integer STRB_LEN   = 25, 
    parameter integer SYNC       = 2,                 // number of synchronization stages: 2-3
        
    // status irq toggle frequency in Hz @ clock/CLK_DIV = 1MHz
    parameter integer IRQ_FREQ = 25,
    
    // TX and RX FIFO
    parameter integer TX_FIFO_DEPTH = 8192,     // 8192
    parameter integer RX_FIFO_DEPTH = 8192,     // 4096, 8192
    
    // DMA buffer size in samples
    parameter integer DMA_BUF_SIZE = 4032/12

)
(
    // FIFO reset input
    input reset_FIFO,
    // fast clock and reset
    input clock_fast,
    input reset_n_fast,
    // slow clock and reset
    input clock_slow,
    input reset_n_slow,
    // control bits @ clock_fast
    input [CTRL_BITS-1:0] ctrl_bits,
    input [TEST_BITS-1:0] test_bits,
    input [REG_BITS-1:0] num_samples,
    input [REG_BITS-1:0] trg_delay,
    input ctrl_regs_reload,
    // status bits and board time @ clock_fast
    output [STATUS_BITS-1:0] status_bits,
    output [REG_BITS-1:0] board_time, // = time of last sample
    output [REG_BITS-1:0] board_samples, // = number of samples received
    output [REG_BITS-1:0] board_time_ext, // = first update time
    output [REG_BITS-1:0] board_samples_ext, // = first update sample
    output status_update,
    // data input
    input [STREAM_DATA_BITS-1:0] in_data,
    output in_ready,
    input in_valid,
    // data output
    output [STREAM_DATA_BITS-1:0] out_data,
    input out_ready,
    output out_valid,
    // bus output
    output [BUS_DATA_BITS-1:0] bus_data,
    output [BUS_ADDR_BITS-1:0] bus_addr,
    output bus_strb,
    output bus_enable_n,
    // trigger input and output
    input trg_start,
    input trg_stop,
    output trg_out,
    // DMA irq inputs
    input irq_TX,
    input irq_RX
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
        
    // assign control bits @ clock_fast
    wire f_run                  = ctrl_bits[0];
    wire f_restart_en           = ctrl_bits[1];
    //wire f_ctrl_num_reload      = ctrl_bits[2];   // pulses after ctrl_bits, test_bits, num_samples or trg_delay have changed
    wire f_error_ext            = ctrl_bits[2];
    wire f_irq_freq_en          = ctrl_bits[3];
    wire f_irq_data_en          = ctrl_bits[4];
    wire f_trg_start_en         = ctrl_bits[5];
    wire f_trg_stop_en          = ctrl_bits[6];
    
    // assign test bits @ clock_fast
    wire f_test_TX              = test_bits[0];
    wire f_test_RX              = test_bits[1];
    wire [2:0] f_test_start     = test_bits[4:2];
    wire [2:0] f_test_update    = test_bits[7:5];
    wire [1:0] f_test_irq       = test_bits[9:8];
    
    // actual time, sample time and number of samples @ clock_slow
    reg [REG_BITS-1:0] timer_s;
    reg [REG_BITS-1:0] sample_time_s;
    reg [REG_BITS-1:0] sample_count_s;
    reg [REG_BITS-1:0] sample_time_ext_s;
    reg [REG_BITS-1:0] sample_count_ext_s;

    // update time and sample (and RX data valid)
    wire update_t;
    wire update_s;

    // enabled run bit and TX/RX channels
    wire [1:0] s_run;
    wire s_TX;
    wire s_RX;

    // state bits @ clock_slow
    reg run_s;
    reg ready_s;
    reg start_s;
    reg end_s;
    
    // ignore run_s when starting with IRQ
    wire ignore_run;
    
    // FPGA irq update signal 
    wire irq_timer;    

    // last sample total and for actual buffer
    wire [1:0] last_s;
    wire [1:0] buf_last;
    
    // data bits @ clock_slow
    wire [STREAM_DATA_BITS-1:0] s_data; // out of TX
    //reg [STREAM_DATA_BITS-1:0] data_s;  // into RX

    // TX FIFO
    wire f_ready;
    wire s_ready;
    wire s_valid;
    dio24_FIFO # (
        .STREAM_DATA_WIDTH(STREAM_DATA_BITS),
        .FIFO_DEPTH(TX_FIFO_DEPTH),
        .OUT_ZERO("FALSE")
    )
    TX_FIFO
    (
        // input TX stream (AXI Stream Slave Bus S00_AXIS)
        .in_clock(clock_fast),
        .in_reset_n(reset_n_fast),
        .in_data(in_data),
        .in_ready(f_ready),
        .in_valid(in_valid & f_test_TX),
        // output RX stream (AXI Stream Master Bus M00_AXIS)
        .out_clock(clock_slow),
        .out_reset_n(reset_n_slow),
        .out_data(s_data),
        .out_valid(s_valid),
        .out_ready(s_ready & (run_s | ignore_run))
    );    
    assign in_ready = f_ready & f_test_TX;
    
    // multiplex TX data or generated data
    wire [STREAM_DATA_BITS-1:0] mux_data_s;
    wire mux_valid_s;
    wire mux_ready_s;
    wire mux_in_valid_s = (~last_s[1]) & s_RX;
    wire mux_in_ready_s;
    stream_MUX # (
        .DATA_WIDTH(STREAM_DATA_BITS),
        .OUT_BUF("FALSE")
    )
    MUX 
    (
        // clock and reset
        .clock(clock_slow),
        .reset_n(reset_n_slow),
        // input selection
        .in_select(s_TX),
        // stream data input 0 = generated data
        .in_data_0({last_s[0]|buf_last[0],sample_count_s+1,timer_s+1}),
        .in_valid_0(mux_in_valid_s & (run_s|ignore_run)),
        .in_ready_0(mux_in_ready_s),
        // stream data input 1 = TX
        //.in_data_1(s_data),
        .in_data_1({s_data[64],s_data[63:32],timer_s+1}),
        .in_valid_1(s_valid & s_RX & (run_s|ignore_run)),
        .in_ready_1(s_ready),
        // stream data output
        .out_data(mux_data_s),
        .out_valid(mux_valid_s),
        .out_ready(mux_ready_s)
    );
    
    // RX FIFO
    dio24_FIFO # (
        .STREAM_DATA_WIDTH(STREAM_DATA_BITS),
        .FIFO_DEPTH(RX_FIFO_DEPTH),
        .OUT_ZERO("FALSE")
    )
    RX_FIFO
    (
        // input stream (AXI Stream Slave Bus S00_AXIS)
        .in_clock(clock_slow),
        .in_reset_n(reset_n_slow),
        .in_data(mux_data_s),
        .in_ready(mux_ready_s),
        .in_valid(mux_valid_s),
        // output stream (AXI Stream Master Bus M00_AXIS)
        .out_clock(clock_fast),
        .out_reset_n(reset_n_fast),
        .out_data(out_data),
        .out_valid(out_valid),
        .out_ready(out_ready)
    );
        
    // sync control bits @ clock_slow 
    // note: these bits are NOT synced with respect to each other! but transmits faster than CDC.
    localparam integer NUM_IN_SYNC = 6;
    wire [NUM_IN_SYNC-1:0] in_w = {trg_stop & f_trg_stop_en,trg_start & f_trg_start_en,irq_RX,irq_TX,f_irq_freq_en,f_run};
    wire [NUM_IN_SYNC-1:0] in_s;
    wire s_run_w;
    wire s_irq_TX;
    wire s_irq_RX;
    wire s_irq_freq_en;
    wire s_trg_start_w;
    wire s_trg_stop_w;
    generate
    for (genvar i = 0; i < NUM_IN_SYNC; i = i + 1)
    begin : I_SYNC
        (* ASYNC_REG = "TRUE" *)
        reg [SYNC-1:0] sync = 0;
        always @ ( posedge clock_slow ) begin
            sync <= {sync[SYNC-2:0],in_w[i]};
        end
        assign in_s[i] = sync[SYNC-1];
    end
    endgenerate
    assign {s_trg_stop_w,s_trg_start_w,s_irq_RX,s_irq_TX,s_irq_freq_en,s_run_w} = in_s;    
    
    // memorize if control registers need to be updated if cdc_ctrl is not ready
    reg cdc_ctrl_valid;
    wire cdc_ctrl_ready;
    always @ ( posedge clock_fast ) begin
        if ( reset_n_fast == 1'b0 ) cdc_ctrl_valid <= 1'b0;
        else if ( ctrl_regs_reload & (~cdc_ctrl_ready)) cdc_ctrl_valid <= 1'b1;
        else if ( cdc_ctrl_ready ) cdc_ctrl_valid <= 1'b0;
        else cdc_ctrl_valid <= cdc_ctrl_valid; 
    end
    
    // sync _test_ control bits and number of samples @ clock_slow
    // CDC ensures consistency between bits which is needed for num_samples and _test_ bits
    wire [REG_BITS-1:0] s_num_samples;
    wire [TRG_DELAY_IN_BITS-1:0] s_trg_delay_in;
    wire [TRG_DELAY_OUT_BITS-1:0] s_trg_delay_out;
    wire [2:0] s_test_start;
    wire [2:0] s_test_update;
    wire [1:0] s_test_irq;
    wire s_ctrl_reload;
    cdc # ( 
        .SYNC(SYNC), 
        .DATA_WIDTH(REG_BITS+TRG_DELAY_OUT_BITS+TRG_DELAY_IN_BITS+TEST_BITS), 
        .USE_OUT_READY("NO")
    )
    cdc_ctrl (
        .in_clock(clock_fast),
        .in_reset_n(reset_n_fast),
        .in_data({num_samples,trg_delay[TRG_DELAY_IN_BITS+TRG_DELAY_OUT_BITS-1-:TRG_DELAY_OUT_BITS],trg_delay[TRG_DELAY_IN_BITS-1:0],f_test_irq,f_test_update,f_test_start,f_test_RX,f_test_TX}),
        .in_valid(cdc_ctrl_valid | ctrl_regs_reload),
        .in_ready(cdc_ctrl_ready),
        .out_clock(clock_slow),
        .out_reset_n(reset_n_slow),
        .out_data({s_num_samples,s_trg_delay_out,s_trg_delay_in,s_test_irq,s_test_update,s_test_start,s_RX,s_TX}),// register output
        .out_valid(s_ctrl_reload),// pulses when bits have been reloaded
        .out_ready(1'b1) // always ready
    );
    
    // s_run bit edge detector
    reg s_run_ff;
    always @ ( posedge clock_slow ) begin
        if ( reset_n_slow == 1'b0 ) s_run_ff <= 1'b0;
        else s_run_ff <= s_run_w;
    end
    //assign s_run[0] = s_run_w & cdc_ctrl_ready;
    assign s_run[0] = s_run_w;
    assign s_run[1] = s_run_ff;
        
    // start trigger edge detector
    reg s_trg_start_ff;
    wire [1:0] s_trg_start;
    always @ ( posedge clock_slow ) begin
        if ( reset_n_slow == 1'b0 ) s_trg_start_ff <= 1'b0;
        else s_trg_start_ff <= s_trg_start_w;
    end
    assign s_trg_start[0] = s_trg_start_w;
    assign s_trg_start[1] = s_trg_start_ff;

    // stop trigger edge detector
    reg s_trg_stop_ff;
    wire [1:0] s_trg_stop;
    always @ ( posedge clock_slow ) begin
        if ( reset_n_slow == 1'b0 ) s_trg_stop_ff <= 1'b0;
        else s_trg_stop_ff <= s_trg_stop_w;
    end
    assign s_trg_stop[0] = s_trg_stop_w;
    assign s_trg_stop[1] = s_trg_stop_ff;

    // first sample
    always @ ( posedge clock_slow ) begin
        if ( reset_n_slow == 1'b0 ) ready_s <= 1'b0;
        else ready_s <= s_valid | ready_s;
    end
    
    // last sample total
    reg last_s_ff;
    always @ ( posedge clock_slow ) begin
        if ( reset_n_slow == 1'b0 ) last_s_ff <= 1'b0;
        else last_s_ff <= (mux_in_ready_s) ? last_s[0] : last_s[1];
    end    
    assign last_s[0] = ((sample_count_s+1) >= s_num_samples);
    assign last_s[1] = last_s_ff;
    
    // MUX IRQ source
    reg [1:0] irq_FPGA_s = 2'b00;
    reg [2:0] s_irq;
    always @ ( posedge clock_slow ) begin
        if ( reset_n_slow == 1'b0 ) s_irq <= 3'b000;
        else s_irq <= (s_test_irq == 2'b11) ? {s_irq[1:0],irq_FPGA_s[0]} :
                      (s_test_irq == 2'b01) ? {s_irq[1:0],s_irq_TX} :
                      (s_test_irq == 2'b10) ? {s_irq[1:0],s_irq_RX} : 3'b000;
    end

    // MUX start timer pulse
    always @ ( posedge clock_slow ) begin
        if ( reset_n_slow == 1'b0 ) start_s <= 1'b0;
        else start_s <= (s_test_start == 3'd0) ? (s_run == 2'b01) :
                        (s_test_start == 3'd1) ? ({ready_s,s_valid} == 2'b01) :
                        (s_test_start == 3'd2) ? (s_irq[1:0]==2'b01) : 
                        (s_test_start == 3'd3) ? (s_irq[2:1]==2'b10) :
                        (s_test_start == 3'd4) ? (s_trg_start[1:0]==2'b01) :
                        (s_test_start == 3'd5) ? (s_trg_start[1:0]==2'b10) :
                        (s_test_start == 3'd6) ? (s_trg_stop[1:0]==2'b01) : (s_trg_stop[1:0]==2'b10);
    end
    
    // when we start with IRQ_UP then run_s is not assigned and no RX data would be transmitted.
    // with this bit enabled run_s is ignored for RX data. but data might not be valid and data might be duplicate.
    assign ignore_run = (s_test_start == 3'd2);

    // sample counter
    assign update_s = (s_TX == 1'b1) ? (run_s|ignore_run) & s_valid & s_ready : // count TX samples
                      (s_RX == 1'b1) ? (run_s|ignore_run) & mux_in_ready_s & mux_in_valid_s // count RX samples 
                       : irq_timer ; // neither RX nor TX channel: count FPGA irqs
    // MUX update time pulse
    assign update_t = (s_test_update == 3'd0) ? ((s_run == 2'b10) | irq_timer) :
                      (s_test_update == 3'd1) ? update_s :
                      (s_test_update == 3'd2) ? (s_irq[1:0] == 2'b01) : 
                      (s_test_update == 3'd3) ? (s_irq[2:1] == 2'b10) :
                      (s_test_update == 3'd4) ? (s_trg_start[1:0]==2'b01) :
                      (s_test_update == 3'd5) ? (s_trg_start[1:0]==2'b10) :
                      (s_test_update == 3'd6) ? (s_trg_stop[1:0]==2'b01) : (s_trg_stop[1:0]==2'b10);

    // timer run bit: set = timer start pulse, reset = run bit negative edge
    always @ ( posedge clock_slow ) begin
        if ( reset_n_slow == 1'b0 ) run_s <= 1'b0;
        else if (start_s) run_s <= 1'b1;
        else if (s_run == 2'b10) run_s <= 1'b0;
        else run_s <= run_s; 
    end

    // end = falling edge of run_s bit = falling edge of s_run bit delayed
    // or if number of samples reached
    always @ ( posedge clock_slow ) begin
        if ( reset_n_slow == 1'b0 ) end_s <= 1'b0;
        else end_s <= ((s_run == 2'b10) || ((sample_count_s == s_num_samples) && (s_num_samples > 0))) ? 1'b1 : end_s;
    end

    // timer
    always @ ( posedge clock_slow ) begin
        if ( reset_n_slow == 1'b0 ) timer_s <= 0;
        else if ( run_s ) timer_s <= timer_s + 1;
        else timer_s <= timer_s;
    end
    /* used for IRQ test to be sure its working
    always @ ( posedge clock_slow ) begin
        if ( reset_n_slow == 1'b0 ) timer_s <= 0;
        else if ( s_irq_TX ) timer_s <= timer_s + 1;
        else timer_s <= timer_s;
    end */

    // board time and samples
    reg first_t;
    reg first_s;
    always @ ( posedge clock_slow ) begin
        if ( reset_n_slow == 1'b0 ) begin
            sample_time_s <= 0;
            sample_count_s <= 0;
            sample_time_ext_s <= 0;
            sample_count_ext_s <= 0;
            first_t <= 1'b1;
            first_s <= 1'b1;
        end
        else begin
            sample_time_s  <= ( update_t ) ? timer_s        + 1 : sample_time_s;
            sample_count_s <= ( update_s ) ? sample_count_s + 1 : sample_count_s;
            sample_time_ext_s  <= ( update_t & first_t ) ? timer_s        + 1 : sample_time_ext_s;
            sample_count_ext_s <= ( update_s & first_s ) ? sample_count_s + 1 : sample_count_ext_s;
            first_t <= ( update_t & first_t ) ? 1'b0 : first_t;
            first_s <= ( update_s & first_s ) ? 1'b0 : first_s;
        end
    end

    // last sample of buffer
    localparam integer BUF_NUM_BITS = clogb2(DMA_BUF_SIZE);
    reg [BUF_NUM_BITS-1:0] buf_count;
    reg buf_last_ff;
    always @ ( posedge clock_slow ) begin
        if ( reset_n_slow == 1'b0 ) begin
            buf_count <= 0;
            buf_last_ff <= 1'b0;
        end
        else begin
            buf_count <= ( update_s ) ? (buf_last_ff ? 0 : buf_count + 1) : buf_count;
            buf_last_ff <= buf_last[0];
        end
    end
    assign buf_last[0] = (buf_count == (DMA_BUF_SIZE-2));
    assign buf_last[1] = buf_last_ff;
    
    // irq toogle bit @ clock_slow
    // 0 at beginning of sequence. toggle with timer if enabled. keep state during pause.
    // IRQ_FREQ = 100Hz -> IRQ_BIT = 19 -> 50x10^6/2^19 = 95Hz @ clock_slow = 50MHz 
    // todo: measure actual frequency
    localparam integer IRQ_BIT = 26-clogb2(IRQ_FREQ);
    if ( IRQ_FREQ == 0 ) assign irq_timer = 1'b0; // disabled
    else assign irq_timer = s_irq_freq_en & (timer_s[IRQ_BIT] ^ irq_FPGA_s[1]); // pulses when enabled and IRQ_BIT changed state
    always @ (posedge clock_slow) begin
        if ( reset_n_slow == 1'b0 ) begin
            irq_FPGA_s <= 2'b00;
        end
        else begin
            irq_FPGA_s[0] <= irq_timer ? ~irq_FPGA_s[0] : irq_FPGA_s[0]; // toggle state
            irq_FPGA_s[1] <= timer_s[IRQ_BIT]; // memorize last state
        end
    end

    // CDC slow -> fast for timer, samples and status bits
    // latency = 4 fast clock cycles
    // updated for each sample
    wire ready_f;
    wire run_f;
    wire end_f;
    wire irq_f;
    wire cdc_ready_s; // not used
    wire cdc_ready_f = 1'b1; // not used
    cdc # ( 
        .SYNC(SYNC), 
        .DATA_WIDTH((4*REG_BITS) + 4), 
        .USE_OUT_READY("NO")
    )
    cdc_status (
        .in_clock(clock_slow),
        .in_reset_n(reset_n_slow),
        .in_data({sample_count_ext_s,sample_time_ext_s,sample_count_s,sample_time_s,irq_FPGA_s[0],end_s,run_s,ready_s}),
        .in_valid(1'b1),
        .in_ready(cdc_ready_s),
        .out_clock(clock_fast),
        .out_reset_n(reset_n_fast),
        .out_data({board_samples_ext,board_time_ext,board_samples,board_time,irq_f,end_f,run_f,ready_f}),
        .out_valid(status_update),
        .out_ready(cdc_ready_f)
    );     
    
    assign status_bits = {1'b0,irq_f,{(STATUS_BITS-5){1'b0}},end_f,run_f,ready_f};
    
    // not used outputs:
    assign bus_data = 0;
    assign bus_addr = 0;
    assign bus_strb = 1'b0;
    assign bus_enable_n = 1'b1;
    
    // trigger output = running state @ clock_slow
    // set after s_trg_delay_in, reset after s_trg_delay_out if not 0 otherwise with run_s
    localparam integer TRG_DELAY_SUM_BITS = (TRG_DELAY_IN_BITS >= TRG_DELAY_OUT_BITS) ? TRG_DELAY_IN_BITS + 1 : TRG_DELAY_OUT_BITS + 1;
    wire [TRG_DELAY_SUM_BITS-1 : 0] s_trg_delay_sum = s_trg_delay_in + s_trg_delay_out;
    reg trg_out_ff = 1'b0;
    always @ ( posedge clock_slow ) begin
        if ( run_s ) begin
            if ( timer_s == {{(REG_BITS-TRG_DELAY_IN_BITS){1'b0}},s_trg_delay_in} ) trg_out_ff <= 1'b1;
            else if ( timer_s == {{(REG_BITS-TRG_DELAY_SUM_BITS){1'b0}},s_trg_delay_sum} ) trg_out_ff <= 1'b0;
            else trg_out_ff <= trg_out_ff;
        end
        else begin
            trg_out_ff <= 1'b0;
        end
    end
    assign trg_out = trg_out_ff;
    

endmodule
