`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// dio24 timing module
// created 12/03/2020
// see dio24_timing_tb for simulation test bench
// parameters:
// - STREAM_DATA_BITS = number of bits of in_data and out_data
// - TIME_BITS = first number of bits of in_data are used for time
// - BUS_DATA_BITS = number of bits for bus_data
// - BUS_ADDR_BITS = number of bits for bus_addr
// - NUM_BITS  = number of bits for num_samples
// - NUM_CTRL = numer of control bits 
// - NUM_STATUS = number of status bits
// - BIT_NOP = 0-based index of bit signalling no-operation in data bits (after TIME_BITS)
// - BIT_IRQ = 0-based index of bit signalling irq_FPGA (after TIME_BITS)
// - BIT_NUM = 0-based index of bit signalling num_samples in data bits (after TIME_BITS)
//      if this bit is set the data is not interpreted as {data,time} bits
//      but as {(NUM_SAMPLES_BIT<<1) | num_samples}  
//      must be data bit < STREAM_DATA_BITS!
// - CLK_DIV = clock divider applied to generate output frequency. must be >=4.
//      cycle goes from 0..CLK_DIV-1, then resets to 0. does not need to be a power of 2.
// - STRB_DELAY = slow clock cycles until bus_strb is set to high after timeout. >=0
// - STRB_LEN = slow clock cycles with bus_strb high after timeout and STRB_DELAY. 
//              1 <= STRB_LEN <= (CLK_DIV - STRB_DELAY - 2) 
// - SYNC = number of synchronization stages. use 2-3.
// - TRG_DELAY_IN = cycles after run & strg_start until execution starts with trg_start_en. must be >=0.
// - TRG_DELAY_OUT = cycles after run bit until trg_out asserted. must be 0 - (CLK_DIV-1).
//      master is sending trg_out with MAX_CYCLES - TRG_DELAY_OUT before execution starts
//      slave waits TRG_DELAY_IN after trg_start before execution starts
// - IRQ_FREQ = irq status bit toggle frequency in Hz (next higher power of 2) assuming clk_slow/CLK_DIV = 1MHz. disabled if 0.
// - TX/RX_FIFO_DEPTH = FIFO depth, see dio24_FIFO.v
// clock and reset:
// - clk_slow = slow clock for timer with frequency = output frequency * CLK_DIV
// - clk_fast = fast clock to synchronize status outputs
// - reset_n_slow = active low reset input @ clock_slow (generate with dio24_reset)  
// - reset_n_fast = active low reset input  @ clock_fast (generate with dio24_reset)
// - reset_n_FIFO = active high FIFO reset (generate with dio24_reset, not used with XPM FIFO)  
// control bits:
// - control[0] = run = if 1 timer is running, otherwise it is suspended,
//   setting run bit to 0 does not reset timer, thus it can be used to pause and resume output.
//   run can be set to 1 before first data is ready without creating an error.
//   first data is latched into registers independently of run bit.
// - control[1] = restart_en = if 1 module will auto-restart when num_samples reached (see 1st note)
// - control[3] = error_ext = external error brings module into error state and stopps further output
// - control[4] = irq_freq_en = timer irq enabled with IRQ_FREQ frequency
// - control[5] = irq_data_en = data irq enabled when BIT_IRQ is set
// - control[12:6] = testing bits. use for timing_test
// - num_samples = number of output data samples. updated when num_reload is high.
// - trg_delay = 16 + 16 bit trigger {trg_delay_out,trg_delay_in}
// - ctrl_regs_reload = pulse high for 1 fast cycle to reload all control registers
// status: 
// - status[0] = ready = first data ready and num_samples not generated and no error
// - status[1] = run = running state = status_ready and run bit set
// - status[2] = end = num_samples generated without error
// - status[3] = restart = toggles state on every restart, initially 0
// - status[4] = error_in = input data not valid on timeout
// - status[5] = error_out = output not ready
// - status[6] = error_time = time not incremental (except auto-restart)
// - status[7] = irq_freq = toggles with about IRQ_FREQ Hz
// - status[8] = irq_data = toggles when irq_en[1] is enabled and BIT_IRQ in in_data is set
// - board_time = actual board time
// - board_samples = actual number of samples
// - board_time_ext = extra board time for tests
// - board_samples_ext = extra number of samples for tests
// - status_update = pulses when status has update 
// data input:
// - in_data = data input of DATA_BITS width
// - in_ready = if 1 data can be updated.
// - in_valid = if 1 data is valid
// data output:
// - out_data = output data of DATA_BITS width
// - out_ready = output of next data is allowed. can be set to 1 if not needed.
// - out_valid = output data is valid. reset after out_ready is set.
// bus output: assign directly to external pins!
// - bus_data = bus data output
// - bus_addr = bus address output
// - bus_strb = bus strobe outut
// - bus_enable_n = bus enable output, active low
// trigger output and input:
// - trg_start_en = enable start trigger
// - trg_start = if run and trg_start_en and positive edge on trg_start starts with execution.
// - trg_out = 1 when execution has started. can be used together with trg_start and trg_start_en
//   to synchronize several boards. TRG_DELAY_IN/OUT parameters are used to fine-tune timing.
// irq inputs:
// - irq_TX/RX = DMA irq TX/RX inputs used only by timing_test module 
// implements:
// - input and output FIFO
// - synchronization of control and status bits
// - timer and cycle counter
// - data output at correct time
// - strobe generation
// - error detection
// - auto restart
// - synchronization of boards via trigger output and start input
// notes:
// - if num_samples were output and there are more samples available (i.e. not in end state, see below)
//   and restart_en=1 then module will auto-restart: counter and timer will be reset and
//   a new sequence is started with time = 0 at 1us* after the previous sequence last sample,
//   assuming 1us time step (e.g. CLK_DIV=8 with clk_slow=8MHz) and data immediately available.
//   this allows to have a controlled time between old an new sequence. 
//   if num_samples were otuput and no more samples available the module goes into end state,
//   indicated by status_end bit and stops output: bus_enable_n goes high and status_ready goes low. 
//   if new samples become available in end state and run and restart_en bits are set,
//   the module will auto-restart as before, but with time = 0 at the moment the new data has arrived. 
//   in this case there will be an unpredictaple time gap for restarting.
// - num_samples must be loaded by pulsing num_reload or by inserting num_samples into stream
//   with NUM_SAMPLES_BIT = 1. when num_reload is pulsed a sample is inserted into the stream
//   with num_samples and NUM_SAMPLES_BIT = 1. neither inserted nor already in the stream existing
//   num_sample are sent to output. loading of num_samples is only allowed 
//   before or after run state but not during run state, otherwise error_in.
//   for auto-restart num_samples can be sent between the last sample of the old sequence
//   and the first sample of the new sequence. for the first sequence send num_sample as the first data.
//   for auto-restart during running state send num_samples only one time.
//   if num_sample = 0 (initial state) dio24_timing will output data as soon as run=1 and data available,
//   but it will never go into end state or auto-restart (streaming mode).
//   it will expect a contiguous stream of data, otherwise error_in. stop with setting run=0.
//   in streaming mode num_samples cannot be loaded. this means, to go from streaming into normal state
//   reset run bit or just do not send more data and allow module to finish - or go into error mode
//   and then initialize software reset. after this you can send num_samples and run module as normal.
//   in case a PAUSE bit would be defined one could send after or together with the num_samples.
//   this would allow to stop streaming mode without software reset. 
// - reset should also empty the FIFO (actually they are not cleared but the counters).
// - except for auto-restart next time > last time, otherwise error_time is generated. 
// - out_data is the same as in_data, only delayed at time specified in first TIME_BITS of data.
//   all data with NUM_SAMPLES_BIT = 1 are not output.
// - when run = 0 during running state the module goes into the READY state and waits until run = 1
//   this allows to halt the output for an arbitrary amount of time.
//   during this time bus_enable_n=0 (active) and status_run=0 and status_ready=1.
// - when num_samples of data output and no data is valid module goes into end state
//   after all strobe bits of the last sample have been generated. 
//   in the end state bus_enable_n = 1 and the status_end=1 and status_run=status_ready=0. 
//   also when run=0 the module waits until last strobe bits are generated before going into READY state.
//   only when there is an error, the module does not wait for the last strobe to be finished
//   and sets in addition to error bit: bus_enable_n=1, status_end=status_run=status_ready=0
// - putting IOB options on bus output FF's causes large hold time violation = signal before clock.
//   to fix this use virtual clock and set output delay max/min with appropriate phase.
// - CLK_DIV=3 could be made working with some effort (needs stream_IO).
// TODO: 
// - used CDC module to load number of samples [I fear the way its done now is not good]
// - trig_out/trg_start work only after reset. they are not tested for auto-restart or start after end
// - send num_samples to output maybe as an option or insert num_samples with bit out of data
//   and use a second bit inside data for num_samples within stream.
// - on error wait for strobe to finish. check consistency between status_ready/end/run and error bits.
// - test if sending num_samples in READY state is allowed? this would allow to terminate streaming mode.
// - define a PAUSE bit in stream data which brings module into READY state until run bit is cycled.
//   this might also allow to stop streaming mode without software reset.
// - another option to stop streaming mode would be to allow in this case to send num_samples.
//   however, this could be done in stream data or if we accept error_in after no data is sent.
//   but last case needs a reset anyway, so not really useful.
// last change 24/04/2021 by Andi
//////////////////////////////////////////////////////////////////////////////////

module dio24_timing # (
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
    parameter integer CLK_DIV    = 50,              // must be >= 4
    parameter integer STRB_DELAY = 12,
    parameter integer STRB_LEN   = 25, 
    parameter integer SYNC       = 2,                 // number of synchronization stages: 2-3
        
    // status irq toggle frequency in Hz @ clock/CLK_DIV = 1MHz
    parameter integer IRQ_FREQ = 25,
    
    // TX and RX FIFO
    parameter integer TX_FIFO_DEPTH = 8192,        // 8192
    parameter integer RX_FIFO_DEPTH = 8192,         // 4096
    
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
    output [REG_BITS-1:0] board_time,
    output [REG_BITS-1:0] board_samples,
    output [REG_BITS-1:0] board_time_ext,
    output [REG_BITS-1:0] board_samples_ext,
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
    // DMA irq inputs (used by timing_test module)
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
    
    // states
    localparam integer STATE_INIT    = 0; // reset state
    localparam integer STATE_READY   = 1; // first data read
    localparam integer STATE_START   = 3; // start after TRG_DELAY_INT/EXT
    localparam integer STATE_RSTRB   = 4;
    localparam integer STATE_RUN     = 5; // normal running state
    localparam integer STATE_ESTRB   = 6;
    localparam integer STATE_END     = 7; // num_samples executed
    localparam integer STATE_RESTART = 8;
    localparam integer STATE_ERROR   = 9; // error state (must be highest number)
    localparam integer STATE_BITS = clogb2(STATE_ERROR);
    reg [STATE_BITS-1:0] state = STATE_ERROR;   // needs reset to come out of this state
    
    // timer and cycle running state
    wire state_timer = (state==STATE_RUN) || (state==STATE_RESTART);
    // cycle running state
    wire state_cycle = (state==STATE_START) || (state==STATE_RSTRB) || (state==STATE_ESTRB);
    // running = output active state = timer and cycles running
    wire state_run = state_timer || state_cycle;
    // ready = output enabled state = data ready = all states except INIT, END and ERROR
    wire state_ready = (state == STATE_READY) || state_run;
    // end = num_samples reached and no new data
    wire state_end = ( state == STATE_END );
    // restart toggle bit (not reset)
    reg state_restart = 1'b0;

    // cycle bits
    localparam integer CYCLE_BITS = clogb2(CLK_DIV-1);
    localparam integer CYCLE_MAX = CLK_DIV-1; //{CYCLE_BITS{1'b1}};
    
    // settings
    localparam STREAM_IO_OUT_BUF = "TRUE";      // stream_IO output buffer ("TRUE")
    localparam IN_READY_PULSE = "YES";          // stream_IO in_ready loads data also when one buffer empty ("YES")
    localparam IN_READY_LOW_CYCLES = 0;         // cycles+2 after reset in_ready goes high
    
    // local control bits     
    reg error_in_ff = 1'b0;    // input error
    reg error_out_ff = 1'b0;   // output error
    reg error_time_ff = 1'b0;  // timing error
    reg timeout = 1'b0;        // data output on timeout
    
    // synchronized inputs @ slow clock
    wire s_run;
    wire s_restart_en;
    wire s_error_ext;
    wire s_irq_freq_en;
    wire s_irq_data_en; 
    wire s_trg_start;
    wire s_trg_start_en;
    wire [REG_BITS-1:0] s_num_samples;
    
    // shared signals
    wire [STREAM_DATA_BITS-1:0] next_data;
    wire [REG_BITS-1:0] next_time = next_data[REG_BITS-1:0];
    reg [REG_BITS-1:0] timer = 0;
    reg [REG_BITS-1:0] counter = 0;
    reg [CYCLE_BITS-1:0] cycle = 0;
    reg out_valid_s = 1'b0;
    //wire in_NOP = in_data[BIT_NOP+REG_BITS] & (~in_data[BIT_NOP+REG_BITS]); // @clock_fast: skip sample entirely
    wire next_NOP = next_data[BIT_NOP+REG_BITS];   // @clock_slow: do not generate strobe signal
    wire next_IRQ = next_data[BIT_IRQ+REG_BITS];   // @clock_slow: toggle state_irq, time valid, data valid only if BIT_NOP not set
    //wire next_NUM = next_data[BIT_NUM+REG_BITS];   // @clock_slow: data = number of samples
    wire next_valid;                                // @clock_slow: data valid out of TX FIFO

    // end detection
    wire check_end;
    // timeout check at cycle = 0 
    wire timeout_0 = ( ( state == STATE_RUN ) && ( timer == next_time ) && ( cycle == 0 ) );
    
    // irq toogle bits @ clock_slow
    // 0 at beginning of sequence. toggle with timer and IRQ_BIT if enabled. keep state during pause.
    // IRQ_BIT = 13/14/15/16/17: real IRQ_FREQ = 122/61/31/15/8Hz
    // todo: measure actual frequency
    localparam integer IRQ_BIT = 20-clogb2(IRQ_FREQ);
    reg [1:0] state_irq = 2'b00;
    reg irq_bit_old = 1'b0;
    wire irq_timer;
    if ( IRQ_FREQ == 0 ) assign irq_timer = 1'b0; // disabled
    else assign irq_timer = s_irq_freq_en & (timer[IRQ_BIT] ^ irq_bit_old);
    wire irq_data  = s_irq_data_en & (timeout_0 & next_IRQ & next_valid); 
    always @ (posedge clock_slow) begin
        if ( reset_n_slow == 1'b0 ) begin
            state_irq <= 2'b00;
            irq_bit_old <= 1'b0; 
        end
        else begin
            state_irq[0] <= irq_timer ? ~state_irq[0] : state_irq[0];
            state_irq[1] <= irq_data ? ~state_irq[1] : state_irq[1];
            irq_bit_old <= irq_timer ? timer[IRQ_BIT] : irq_bit_old;
        end
    end

    // synchronize control bits and trigger inputs with clock_slow (no reset needed)
    // note: these bits are NOT synced with respect to each other! but transmits faster than CDC.    
    wire f_run          = ctrl_bits[0];
    wire f_restart_en   = ctrl_bits[1];
    //wire f_ctrl_num_reload = ctrl_bits[2]; // pulses after ctrl_bits, test_bits, num_samples or trg_delay have changed
    wire f_error_ext    = ctrl_bits[2];
    wire f_irq_freq_en  = ctrl_bits[3];
    wire f_irq_data_en  = ctrl_bits[4];
    wire f_trg_start_en = ctrl_bits[5];
    //wire f_trg_stop_en  = ctrl_bits[6];    
    localparam integer NUM_IN_SYNC = 7;
    wire [NUM_IN_SYNC-1:0] in_w = {f_trg_start_en,trg_start,f_irq_data_en,f_irq_freq_en,f_error_ext,f_restart_en,f_run};
    wire [NUM_IN_SYNC-1:0] in_s;
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
    assign {s_trg_start_en,s_trg_start,s_irq_data_en,s_irq_freq_en,s_error_ext,s_restart_en,s_run} = in_s;
    
    // memorize if control bits or num_samples need to be updated if cdc_ctrl is not ready
    reg cdc_ctrl_valid;
    wire cdc_ctrl_ready;
    always @ ( posedge clock_fast ) begin
        if ( reset_n_fast == 1'b0 ) cdc_ctrl_valid <= 1'b0;
        else if ( ctrl_regs_reload & (~cdc_ctrl_ready)) cdc_ctrl_valid <= 1'b1;
        else if ( cdc_ctrl_ready ) cdc_ctrl_valid <= 1'b0;
        else cdc_ctrl_valid <= cdc_ctrl_valid; 
    end

    // start copied from timing_test module    
    // TODO: simulate!    
    // sync number of samples and trg_delay bits @ clock_slow
    // CDC ensures consistency between bits
    wire [TRG_DELAY_IN_BITS-1:0] s_trg_delay_in;
    wire [TRG_DELAY_IN_BITS-1:0] s_trg_delay_out;
    wire s_num_reload;
    cdc # ( 
        .SYNC(SYNC), 
        .DATA_WIDTH(REG_BITS+TRG_DELAY_OUT_BITS+TRG_DELAY_IN_BITS), 
        .USE_OUT_READY("NO")
    )
    cdc_ctrl (
        .in_clock(clock_fast),
        .in_reset_n(reset_n_fast),
        .in_data({num_samples,trg_delay[TRG_DELAY_IN_BITS+TRG_DELAY_OUT_BITS-1-:TRG_DELAY_OUT_BITS],trg_delay[TRG_DELAY_IN_BITS-1:0]}),
        .in_valid(cdc_ctrl_valid | ctrl_regs_reload),
        .in_ready(cdc_ctrl_ready),
        .out_clock(clock_slow),
        .out_reset_n(reset_n_slow),
        .out_data({s_num_samples,s_trg_delay_out,s_trg_delay_in}),// register output
        .out_valid(s_num_reload),// pulses when bits have been reloaded
        .out_ready(1'b1) // always ready
    );
    // end copied from timing_test module    
    
    // cdc module transmits board time and status bits from slow clock to fast clock
    // latency = 4 fast clock cycles
    wire [STATUS_BITS-1:0] status_slow = {state_irq,error_time_ff,error_out_ff,error_in_ff,state_restart,state_end,state_run,state_ready};
    cdc # ( 
        .SYNC(SYNC), 
        .DATA_WIDTH(STATUS_BITS + REG_BITS + REG_BITS), 
        .USE_OUT_READY("NO")
    )
    cdc_status (
        .in_clock(clock_slow),
        .in_reset_n(reset_n_slow),
        .in_data({status_slow,counter,timer}),
        .in_valid(1'b1),
        .in_ready(), // not used
        .out_clock(clock_fast),
        .out_reset_n(reset_n_fast),
        .out_data({status_bits,board_samples,board_time}),
        .out_valid(status_update),
        .out_ready() // not used
    ); 
    
    // use CDC to transmit num_samples    
    wire in_num_valid = in_valid; // & (~in_NOP); // input valid, no NOP bit or load num_samples.
    wire [STREAM_DATA_BITS-1:0] in_num_data = in_data;
    wire in_num_ready;
    wire next_ready = timeout;        // get next data from FIFO on timeout
    assign in_ready = in_num_ready;

    /* insert num_samples into stream data @ clock_fast
    // TODO: use CDC module for this!
    reg num_reload_ff = 1'b0;
    wire in_num_valid = (in_valid & (~in_NOP)) | f_ctrl_num_reload; // input valid, no NOP bit or load num_samples
    wire in_num_ready;
    wire in_num_reload = f_ctrl_num_reload || num_reload_ff;
    wire [STREAM_DATA_BITS-1:0] in_num = {{(STREAM_DATA_BITS-(BIT_NUM+REG_BITS)-1){1'b0}},1'b1,{(BIT_NUM){1'b0}},num_samples};
    wire [STREAM_DATA_BITS-1:0] in_num_data = in_num_reload ? in_num : in_data;
    always @ ( posedge clock_fast ) begin
        if ( reset_n_fast == 1'b0 ) begin
            num_reload_ff <= 1'b0;
        end
        else if ( f_ctrl_num_reload ) begin
            num_reload_ff <= in_num_ready ? 1'b0 : 1'b1;
        end
        else if ( in_num_ready ) begin
            num_reload_ff <= 1'b0;
        end
        else begin
            num_reload_ff <= num_reload_ff;
        end
    end
    // block stream while loading num_samples
    assign in_ready = in_num_ready & ~(f_ctrl_num_reload || num_reload_ff);
    
	// TX FIFO = data input buffer and clock boundary crossing fast -> slow
    // stream_IO module for data input timing and buffering
    //wire next_ready = (next_valid & next_NUM) | timeout;        // get next data from FIFO on timeout or num_samples read
    */
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
        .in_data(in_num_data),
        .in_ready(in_num_ready),
        .in_valid(in_num_valid),
        // output RX stream (AXI Stream Master Bus M00_AXIS)
        .out_clock(clock_slow),
        .out_reset_n(reset_n_slow),
        .out_data(next_data),
        .out_valid(next_valid),
        .out_ready(next_ready)
    );
    
    /* load num_samples_s at CYCLE_MAX
    // next_num_ff ensures immediate loading of data in state_run, otherwise error_in 
    always @ ( posedge clock_slow ) begin
        if ( reset_n_slow == 1'b0 ) begin
            s_num_samples <= 0;
        end
        else if ( next_valid & next_NUM ) begin
            s_num_samples <= next_data[REG_BITS-1:0];
        end
        else begin
            s_num_samples <= s_num_samples;
        end
    end  */
    
    // end state detection
    // set when num_samples reached, reset when STATE_END or STATE_RESTART
    // STATE_RESTART is included for case when valid data arrives after check_end_w=1
    reg check_end_ff = 1'b0;
    wire check_end_w = (( s_num_samples > 0 ) && ( counter == s_num_samples ));    
    always @ ( posedge clock_slow ) begin
        if ( reset_n_slow == 1'b0 ) begin
           check_end_ff <= 1'b0;
        end
        else if ( check_end_w ) begin
           check_end_ff <= 1'b1;
        end
        else if ( ( state == STATE_END ) || ( state == STATE_RESTART ) ) begin
            check_end_ff <= 1'b0;
        end
        else begin
           check_end_ff <= check_end_ff;
        end
    end
    assign check_end = check_end_w | check_end_ff;

    // timer and cycle 
    // reset with reset_ns, running while run bit is set and no error
    // cycle is incremented every clock_slow cycle but rolls over to zero at CLK_DIV
    // timer is incremented when cycle rolls over, thus runs at clock_slow/CLK_DIV frequency
    always @ ( posedge clock_slow ) begin
        if ( reset_n_slow == 1'b0 ) begin
            cycle <= 0;
            timer <= 0;
        end
        else if ( state_timer ) begin
            if ( cycle == CYCLE_MAX ) begin
                cycle <= 0;
                timer <= ( state == STATE_RESTART ) ? 0 : timer + 1;
            end
            else begin
                cycle <= cycle + 1;
                timer <= timer;
            end
        end
        else if ( state_cycle ) begin
            cycle <= ( cycle == CYCLE_MAX ) ? 0 : cycle + 1;
            timer <= timer;
        end
        else begin
            cycle <= cycle;
            timer <= timer;
        end
    end

    // data counter incremented on timeout
    // reset only by reset_ns
    always @ ( posedge clock_slow ) begin
        if ( ( reset_n_slow == 1'b0 ) || ( state == STATE_RESTART) ) begin
            counter <= 0;
        end
        else if ( timeout ) begin
            counter <= counter + 1;
        end
        else begin
            counter <= counter;
        end
    end
    
    // timeout detection when active, last output read and timer == next latched time
    // timeout is high only for one cycle
    // we check here ~out_valid instead of out_ready since new output can be written
    // while out_ready might be still low. out_valid is set by timeout and reset by out_ready.
    always @ ( posedge clock_slow ) begin
        if ( reset_n_slow == 1'b0 ) begin
            timeout <= 1'b0;
        end
        else if ( timeout_0 & (~out_valid_s) ) begin
            timeout <= 1'b1;
        end
        else begin
            timeout <= 1'b0; 
        end
    end 

    // RX FIFO data on timeout pulse
    reg [STREAM_DATA_BITS-1:0] out_data_s;
    always @ ( posedge clock_slow ) begin
        if ( reset_n_slow == 1'b0 ) begin
            out_data_s <= 0;
        end
        else if ( timeout ) begin // & (~next_NOP)) begin
            out_data_s <= next_data;
        end
        else begin
            out_data_s <= out_data_s;
        end
    end 
    
    // bus data output on timeout pulse if not NOP bit is set
    // note: we split bus data and RX data because NOP bit should block bus data but not RX data
    //       and bus-data is pipelined into output buffer to ensure small output skew on bus
    reg [BUS_DATA_BITS-1:0] bus_data_buf;
    reg [BUS_ADDR_BITS-1:0] bus_addr_buf;
    always @ ( posedge clock_slow ) begin
        if ( reset_n_slow == 1'b0 ) begin
            bus_data_buf <= 0;
            bus_addr_buf <= 0;
        end
        else if ( timeout & (~next_NOP)) begin
            bus_data_buf <= next_data[REG_BITS+BUS_DATA_BITS-1 -: BUS_DATA_BITS];
            bus_addr_buf <= next_data[REG_BITS+BUS_DATA_BITS+BUS_ADDR_BITS-1 -: BUS_ADDR_BITS];
        end
        else begin
            bus_data_buf <= bus_data_buf;
            bus_addr_buf <= bus_addr_buf;
        end
    end 
    
    // strobe generation after timeout pulse
    // set STRB_DELAY cycles after timeout (and not BIT_NOP)
    // reset STRB_DELAY+STRB_LEN cycles after timeout
    localparam integer STRB_END = (1+STRB_DELAY+STRB_LEN) <= (CLK_DIV-1) ? (1+STRB_DELAY+STRB_LEN) : (CLK_DIV-1);
    reg out_strb_active = 1'b0;
    wire out_strb;
    always @ (posedge clock_slow) begin
        if ( reset_n_slow == 1'b0 ) begin
            out_strb_active <= 1'b0;
        end
        else if ( timeout & (~next_NOP)) begin
            out_strb_active <= 1'b1;
        end
        else begin
            out_strb_active <= ( cycle < STRB_END ) ? out_strb_active : 1'b0; 
        end
    end 
    assign out_strb = out_strb_active && ( cycle > (1+STRB_DELAY) );
    
    // output valid
    // set by timeout, reset by out_ready
    wire out_ready_s;
    always @ (posedge clock_slow) begin
        if ( reset_n_slow == 1'b0 ) begin
            out_valid_s <= 1'b0;
        end
        else if ( timeout ) begin
            out_valid_s <= 1'b1;
        end
        else if ( out_ready_s ) begin
            out_valid_s <= 1'b0; 
        end
        else begin
            out_valid_s <= out_valid_s; 
        end
    end 

    // TODO: disabled any checking. should re-enable.
    /* input error detection one cycle after data loading
    // requires reset to reset
    // notes: 
    // - at cycle=2 we might receive num_samples (next_num_bit=1)
    //   and at cycle=2-3 we get next data which must be always valid.
    // - if next_num_bit=1 without check_end=1 we get also error.
    //   would happen when sending num_samples during run_state,
    //   or if repeated num_samples are sent at RESTART.
    always @ ( posedge clock_slow ) begin
        if ( reset_n_slow == 1'b0 ) begin
            error_in_ff <= 1'b0;
        end
        else if ( state_timer ) begin // timer running state
            if (( state == STATE_RESTART ) && ( next_NUM )) begin // num_samples sent twice?
                error_in_ff <= 1'b1;
            end  
            else if ( (~check_end) && (cycle >= 2) ) begin // not end: data must be loaded but no num_samples allowed
                error_in_ff <= ( ( ~next_valid ) | next_NUM ) ? 1'b1 : error_in_ff;
            end
            else begin
                error_in_ff <= error_in_ff;
            end
        end
        else begin // not in running state
            error_in_ff <= error_in_ff;
        end
    end
    */
    
    // output error detection
    // error if timeout but output not ready
    // requires reset to reset
    always @ ( posedge clock_slow ) begin
        if ( reset_n_slow == 1'b0 ) begin
            error_out_ff <= 1'b0;
        end
        else if ( timeout_0 & out_valid_s ) begin
            error_out_ff <= 1'b1;
        end
        else begin
            error_out_ff <= error_out_ff;
        end
    end
    
    // timer error detection
    // error if next time is smaller or equal actual time
    // requires reset to reset
    always @ ( posedge clock_slow ) begin
        if ( reset_n_slow == 1'b0 ) begin
            error_time_ff <= 1'b0;
        end
        else if ( (state == STATE_RUN) && (cycle == 2) && (~check_end) ) begin
            error_time_ff <= ( next_valid && ( next_time <= timer ) ) ? 1'b1 : error_time_ff;
        end
        else begin
            error_time_ff <= error_time_ff;
        end
    end
    
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
        .in_data(out_data_s),
        .in_ready(out_ready_s),
        .in_valid(out_valid_s),
        // output stream (AXI Stream Master Bus M00_AXIS)
        .out_clock(clock_fast),
        .out_reset_n(reset_n_fast),
        .out_data(out_data),
        .out_valid(out_valid),
        .out_ready(out_ready)
    );

    // bus data output buffer
    (* IOB = "TRUE" *)
    reg [BUS_DATA_BITS-1:0] bus_data_ff;
    always @ ( posedge clock_slow ) begin
        if ( reset_n_slow == 1'b0 ) begin
            bus_data_ff <= 0;
        end
        else begin
            //bus_data_ff = out_data_s[REG_BITS+BUS_DATA_BITS-1 -: BUS_DATA_BITS];
            bus_data_ff <= bus_data_buf;
        end
    end
    assign bus_data = bus_data_ff;

    // bus address output buffer
    (* IOB = "TRUE" *)
    reg [BUS_ADDR_BITS-1:0] bus_addr_ff;
    always @ ( posedge clock_slow ) begin
        if ( reset_n_slow == 1'b0 ) begin
            bus_addr_ff <= 0;
        end
        else begin
            //bus_addr_ff = out_data_s[REG_BITS+BUS_DATA_BITS+BUS_ADDR_BITS-1 -: BUS_ADDR_BITS];
            bus_addr_ff <= bus_addr_buf;
        end
    end
    assign bus_addr = bus_addr_ff;

    // bus strobe output buffer
    // last possible output goes low together with ready. 
    (* IOB = "TRUE" *)
    reg bus_strb_ff;
    always @ ( posedge clock_slow ) begin
        if ( reset_n_slow == 1'b0 ) begin
            bus_strb_ff <= 1'b0;
        end
        else begin
            bus_strb_ff = out_strb;
        end
    end
    assign bus_strb = bus_strb_ff;

    // bus output enable buffer, active low.
    // goes high one cycle after last possible strobe goes low.
    (* IOB = "TRUE" *)
    reg bus_enable_n_ff;
    always @ ( posedge clock_slow ) begin
        if ( reset_n_slow == 1'b0 ) begin
            bus_enable_n_ff <= 1'b1;
        end
        else begin
            bus_enable_n_ff = ~state_ready;
        end
    end
    assign bus_enable_n = bus_enable_n_ff;
    
    // restart toggle bit when going from RESTART to RUN state
    // note: does not change on reset. initially 0
    wire check_restart = ( s_run && (cycle == CYCLE_MAX) );
    always @ ( posedge clock_slow ) begin
        if ( ( state == STATE_RESTART ) && next_valid && check_restart ) begin
            state_restart <= ~state_restart;
        end
        else begin
            state_restart <= state_restart;
        end
    end

    // start trigger 
    // if enabled set when run and positive edge on trg_start
    // trigger is delayed by TRG_DELAY_IN slow clock cycles to allow fine-adjustment of slave timing
    // TODO: this needs to be updated!
    reg [TRG_DELAY_IN_BITS+1:0] trg_start_ff = 1;
    always @ ( posedge clock_slow ) begin
        if ( s_trg_start_en ) begin
            trg_start_ff <= {trg_start_ff[TRG_DELAY_IN_BITS:0],s_trg_start & s_run};
        end
        else begin
            trg_start_ff <= 1;
        end
    end
    wire trigger = s_run && (trg_start_ff[(TRG_DELAY_IN_BITS+1) -: 2] == 2'b01);
    
    // state machine @ slow clock
    always @ ( posedge clock_slow ) begin
        if ( reset_n_slow == 1'b0 ) begin
            state <= STATE_INIT;
        end
        else if ( error_in_ff | error_out_ff | error_time_ff | s_error_ext ) begin
            state <= STATE_ERROR;
        end
        else begin
            case (state)
                //STATE_INIT:     state <= (next_valid & (~next_NUM)) ? STATE_READY : STATE_INIT;
                STATE_INIT:     state <= (next_valid) ? STATE_READY : STATE_INIT;
                STATE_READY:    state <= s_trg_start_en ? ( trigger ? STATE_RUN : STATE_READY ) : ( s_run ? STATE_START : STATE_READY );
                STATE_START:    state <= ( cycle == CYCLE_MAX ) ? STATE_RUN : STATE_START;
                STATE_RSTRB:    state <= ( cycle == 2 ) ? STATE_READY : STATE_RSTRB;
                STATE_RUN:  
                    if ( cycle <= 1 ) begin // cycle = 0-2: no action
                        state <= STATE_RUN;
                    end
                    else if ( cycle == 2 ) begin
                        if ( check_end ) begin // end or restart (run bit ignored)
                            if ( next_valid && s_restart_en ) begin // restart
                                state <= STATE_RESTART;
                            end
                            else if ( cycle == CYCLE_MAX ) begin // end: cycle finished (run bit ignored)
                                state <= STATE_ESTRB;
                            end
                            else begin  // end: wait until cycle finished (run bit ignored)
                                state <= STATE_RUN;
                            end
                        end
                        else begin // not end (check run bit). TODO: need to check here also trigger bit when enabled.
                            state <= s_run ? STATE_RUN : STATE_RSTRB;
                        end
                    end
                    else if ( check_end ) begin // end: wait until cycle finished (run bit ignored)
                        if ( cycle == CYCLE_MAX ) begin
                            state <= STATE_ESTRB;
                        end 
                        else begin
                            state <= STATE_RUN;
                        end
                    end
                    else begin // cycle 4 - CYCLE_MAX: check run bit
                        state <= s_run ? STATE_RUN : STATE_RSTRB;
                    end
                STATE_ESTRB:    state <= ( cycle == (CYCLE_MAX-1) ) ? STATE_END : STATE_ESTRB;
                //STATE_END:      state <= ( next_valid & (~next_NUM) & s_restart_en ) ? STATE_RESTART : STATE_END;
                STATE_END:      state <= ( next_valid & s_restart_en ) ? STATE_RESTART : STATE_END;
                STATE_RESTART:  state <= next_valid ? ( check_restart ? STATE_RUN : STATE_RESTART) : STATE_ESTRB;
                default:        state <= STATE_ERROR;
            endcase            
        end
    end
    
    // trigger output = state_active @ clock_slow
    // trigger output is delayed by TRG_DELAY_OUT slow clock cycles to allow fine-adjustment of master timing
    reg trg_out_ff = 1'b0;
    always @ ( posedge clock_slow ) begin
        trg_out_ff <= ( trg_out_ff ) ? state_run : (state_run && ( cycle == s_trg_delay_out ));
    end
    assign trg_out = trg_out_ff;
    
    // test timer for arbitrary tests controlled by test bits
    
    // test bits
    wire test_run    = test_bits[0];
    wire test_update = test_bits[1];
    
    // run bit edge detector
    reg test_run_ff = 0;
    always @ ( posedge clock_fast ) begin
        test_run_ff <= test_run;
    end
    wire [1:0] test_run_edge = {test_run_ff,test_run};

    // update bit edge detector
    reg test_update_ff = 0;
    always @ ( posedge clock_fast ) begin
        test_update_ff <= test_update;
    end
    wire [1:0] test_update_edge = {test_update_ff,test_update};
    
    // timer
    // timer is running while test_run is high
    // the timer value is saved into board_time_ext on rising edge edge of test_update or falling edge of test_run
    // timer is reset only by external reset signal
    // since board_samples_ext is not used we save last value of board_time_ext. free for other purpose in the future.
    reg [REG_BITS-1:0] test_timer = 0;
    reg [REG_BITS-1:0] test_time_0 = 0;
    reg [REG_BITS-1:0] test_time_1 = 0;
    wire test_reg_update = (( test_run_edge == 2'b10 ) || ( test_update_edge == 2'b01));
    always @ ( posedge clock_fast ) begin
        if ( reset_n_fast == 1'b0 ) begin
            test_timer <= 0;
            test_time_0 <= 0;
            test_time_1 <= 0;
        end
        else if ( test_run_ff ) begin
            test_timer <= test_timer + 1;
            test_time_0 <= test_reg_update ? test_timer  : test_time_0;
            test_time_1 <= test_reg_update ? test_time_0 : test_time_1;
        end
        else begin
            test_timer <= test_timer;
            test_time_0 <= test_time_0;
            test_time_1 <= test_time_1;
        end
    end
    
    // assign extra board time and samples
    assign board_time_ext    = test_time_0;
    assign board_samples_ext = test_time_1;
    
endmodule
