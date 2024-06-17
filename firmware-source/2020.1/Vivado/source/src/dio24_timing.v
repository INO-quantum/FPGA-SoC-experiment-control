`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// dio24 timing module
// created 12/03/2020
// see dio24_timing_tb for simulation test bench
// parameters:
// - STREAM_DATA_BITS = number of bits of in_data and out_data
// - TIME_BITS = first number of bits of in_data are used for time (typicall)
// - BUS_DATA_BITS = number of bits for bus_data (typically 16)
// - BUS_ADDR_BITS = number of bits for bus_addr (typically 7 or 8)
// - BUS_ADDR_1_USE = "ZERO" / "ADDR0" / "DATA_HIGH" = all low (default) / same as bus_addr_0 = data[23:16], data[31:24] 
// - NUM_STRB = number of strobe bits (1 or 2)
// - NUM_BITS  = number of bits for num_samples
// - NUM_CTRL = numer of control bits 
// - NUM_STATUS = number of status bits
// - BIT_NOP = 0-based index of bit signalling no-operation in data bits (after TIME_BITS)
// - BIT_TRESET = 0-based index of bit signalling relative time from last command.
// - BIT_IRQ = 0-based index of bit signalling irq_FPGA (after TIME_BITS)
// - CLK_DIV_BITS = number of bits used for clock divider in reg_div
// - SYNC = number of synchronization stages. use 2-3.
// - TRG_DELAY_IN = cycles after run & strg_start until execution starts with trg_start_en. must be >=0.
// - TRG_DELAY_OUT = cycles after run bit until trg_out asserted. must be 0 - (CLK_DIV-1).
//      master is sending trg_out with MAX_CYCLES - TRG_DELAY_OUT before execution starts
//      slave waits TRG_DELAY_IN after trg_start before execution starts
// - IRQ_BITS = irq status bit toggle frequency in 2^IRQ_BITS of bus_cycles
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
// - bus_strb_0 = bus strobe outut 0
// - bus_strb_1 = bus strobe outut 1  
// - bus_enable_n = bus enable output, active low [removed]
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
// last change 2024/05/15 by Andi
//////////////////////////////////////////////////////////////////////////////////

module dio24_timing # (
    // AXI stream data input
    parameter integer STREAM_DATA_BITS  = 65,       // 64 + 1 {in_last,in_data}
    
    // data bits
    parameter integer BUS_DATA_BITS     = 16,       // 16
    parameter integer BUS_ADDR_BITS     =  8,       // 8
    parameter         BUS_ADDR_1_USE    = "ZERO",   // "ZERO"/"ADDR0"/"DATA_HIGH" = low / same as bus_addr_0 = data[23:16], data[31:24] 
    parameter integer NUM_STRB          = 1,        // number of bits for bus_strb (1 or 2)
    parameter integer REG_BITS          = 32,       // must be 32
    parameter integer CTRL_BITS         = 4,        // 4
    parameter integer STATUS_BITS       = 10,       // 10
    parameter integer CLK_DIV_BITS      = 8,        // 8: clock divider = 1-255
    parameter integer TRG_DIV_BITS      = 8,        // 8: trigger window divider = 0-255
    parameter integer STRB_DELAY_BITS   = 8,        // 8
    
    // special data bits
    parameter integer BIT_NOP           = 31,       // 31
    parameter integer BIT_TRST          = 30,       // 30
    parameter integer BIT_IRQ           = 29,       // 29
    
    // strobe bit in address data
    parameter integer BIT_STROBE        = 23,       // strobe bit = last address bit
    parameter         USE_STROBE        = "NO",     // "NO" = do not use strobe bit, "YES" = data output only when BIT_STROBE toggles

    // synchronization
    parameter integer SYNC              = 2,        // number of synchronization stages: 2-3
        
    // status irq toggle frequency
    parameter integer IRQ_FREQ_BITS     = 20       // 20. 2^20 ~ 10^6, gives 10Hz at clk_bus = 10MHz.
)
(
    // clocks and reset
    input clk_bus,
    input reset_bus_n,
    // control registers @ clk_bus
    input [CTRL_BITS-1:0] ctrl_bits,
    input [REG_BITS-1:0] num_samples,
    input [CLK_DIV_BITS-1:0] clk_div_bus,
    input [TRG_DIV_BITS-1:0] trg_div_bus,
    input [STRB_DELAY_BITS*NUM_STRB*2-1:0] strb_delay_bus,
    //input as_start,
    input ctrl_regs_reload,                         // pulses when num_samples or clk_div is updated
    input strb_delay_reload,                        // pulses when strb_delay_bus is updated
    // status registers time @ clc_bus
    output [STATUS_BITS-1:0] status_bits,
    output [REG_BITS-1:0] board_time,
    output [REG_BITS-1:0] board_samples,
    output [REG_BITS-1:0] board_time_ext,
    output [REG_BITS-1:0] board_samples_ext,
    output status_update,
    // TX stream data input
    input [STREAM_DATA_BITS-1:0] in_data,
    output in_ready,
    input in_valid,
    // RX stream data output
    output [STREAM_DATA_BITS-1:0] out_data,
    input out_ready,
    output out_valid,
    // bus output
    output [BUS_DATA_BITS-1:0] bus_data,
    output [BUS_ADDR_BITS-1:0] bus_addr_0,
    output [BUS_ADDR_BITS-1:0] bus_addr_1,
    output [NUM_STRB-1:0] bus_strb
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
    
    // settings
    localparam STREAM_IO_OUT_BUF = "TRUE";      // stream_IO output buffer ("TRUE")
    localparam IN_READY_PULSE = "YES";          // stream_IO in_ready loads data also when one buffer empty ("YES")
    localparam IN_READY_LOW_CYCLES = 0;         // cycles+2 after reset in_ready goes high
        
    // shared signals
    reg [REG_BITS-1:0] timer = 0;
    reg [REG_BITS-1:0] samples = 0;
        
    wire run          = ctrl_bits[0];
    wire restart_en   = ctrl_bits[1];
    wire irq_freq_en  = ctrl_bits[2];
    wire irq_data_en  = ctrl_bits[3];
    //wire test_run     = ctrl_bits[4];
    //wire test_update  = ctrl_bits[5];
    
    // registered status bits
    reg state_ready       = 1'b0;     // high when first data received and no error.
    reg state_run         = 1'b0;     // high while running. stays high during waiting.
    reg state_wait        = 1'b0;     // wait for restart trigger.
    reg state_end         = 1'b0;     // all data transmitted. not set when state_restart is high.
    reg state_restart     = 1'b0;     // restart after all data transmitted. error_in if no data available.
    reg [1:0] state_irq   = 2'b00;    // {irq_data,irq_freq} bits
    reg end_next_cycle    = 1'b0;     // high one cycle before state_end. not set when state_restart is high.
    reg end_pulse         = 1'b0;     // same as end_next_cycle but is set even with state_restart.
    reg reset_done        = 1'b0;     // high during & after reset. 
    
    // error bits
    reg error_in_ff = 1'b0;    // input error
    reg error_out_ff = 1'b0;   // output error
    reg error_time_ff = 1'b0;  // timing error
        
    //////////////////////////////////////////////////////////////////////////////////
    // input ready signal. this controls loading of in_data.
    // set with timeout_next_cycle
    // reset with in_valid & not timeout_next_cycle 
    // initially set even without run bit set
    // with timeout_next_cycle we anticipate timeout signal which permits maximum speed if needed.
    
    // TODO: with 1-2 samples next_valid is never assigned! since 3 input buffers do not fall-through!
    //       this might make problems not only at start but also when TX FIFO is becoming empty during run!
    //       changing this is very dangerous to make a mess and might require some time to fix and careful testing! 
    //       since I have no time to do this, for the moment I leave it untouched but 
    //       instead I request the driver to send always multiple of 4 samples (with NOP padded if needed).
    
    // number of input data buffers
    localparam integer IN_DATA_BUF = 3;

    reg in_ready_ff;
    reg [IN_DATA_BUF-1:0] in_valid_ff = {IN_DATA_BUF{1'b0}};
    wire next_valid = in_valid_ff[IN_DATA_BUF-1];
    wire timeout;
    wire timeout_next_cycle;
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) in_ready_ff <= 1'b0;
        else if ( (~in_valid_ff[IN_DATA_BUF-2]) | timeout_next_cycle ) in_ready_ff <= 1'b1;
        //else if ( (~next_valid) | timeout_next_cycle ) in_ready_ff <= 1'b1;
        else if ( in_valid ) in_ready_ff <= 1'b0;
        else in_ready_ff <= in_ready_ff;
    end
    assign in_ready = in_ready_ff;

    // input error detection
    // error if timeout_next_cycle but input not valid
    // requires reset to reset
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) error_in_ff <= 1'b0;
        else error_in_ff <= ( state_run & timeout & (~in_valid_ff[IN_DATA_BUF-1]) & (~end_next_cycle) ) ? 1'b1 : error_in_ff;
    end

    //////////////////////////////////////////////////////////////////////////////////
    // load data from input stream

    // input data buffer
    // for efficiency we use buffer cycles to register BIT_NOP and BIT_STROBE if used
    // if USE_STROBE == "YES":
    //    the first data is ALWAYS output regardless of BIT_STROBE unless BIT_NOP is set.
    //    further data is output only if BIT_STROBE toggles and BIT_NOP is not set.
    //    if BIT_NOP is set data is not output but BIT_STROBE is used to detect next toggle.
    // if USE_STROBE != "YES":
    //    data is output if BIT_NOP is not set. BIT_STROBE is ignored.
    // note: bus_strb_0/1 are NOT the same as BIT_STROBE!
    reg [STREAM_DATA_BITS-1:0] in_data_ff [0 : IN_DATA_BUF - 1];
    reg next_NOP_ff [0 : IN_DATA_BUF - 1];
    reg first_sample;
    reg last_strobe;
    integer i;
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) begin
            for (i=0; i<IN_DATA_BUF; i=i+1) begin
                in_data_ff[i] <= 0;
                next_NOP_ff[i] <= 1'b0;
            end
            in_valid_ff <= {IN_DATA_BUF{1'b0}};
            first_sample <= 1'b1;
            last_strobe <= 1'b0;
        end
        else if ( (in_valid | timeout) & in_ready ) begin
            in_data_ff[0] <= in_data;
            if ( USE_STROBE == "YES" )
                next_NOP_ff[0] <=     in_data[BIT_NOP+REG_BITS] |
                                  (~((in_data[BIT_STROBE+REG_BITS] ^ last_strobe) | first_sample));
            else
                next_NOP_ff[0] <= in_data[BIT_NOP+REG_BITS];        
            for (i=1; i<IN_DATA_BUF; i=i+1) begin
                in_data_ff[i] <= in_data_ff[i-1];
                next_NOP_ff[i] <= next_NOP_ff[i-1];
            end
            in_valid_ff <= {in_valid_ff[IN_DATA_BUF-2:0],1'b1};
            first_sample <= 1'b0;
            last_strobe <= in_data[BIT_STROBE+REG_BITS]; 
        end
        else begin
            for (i=0; i<IN_DATA_BUF; i=i+1) begin
                in_data_ff[i] <= in_data_ff[i];
                next_NOP_ff[i] <= next_NOP_ff[i];
            end
            in_valid_ff <= in_valid_ff;
            first_sample <= first_sample;
            last_strobe <= last_strobe;
        end
    end
    
    // assign time from input data buffer
    wire [REG_BITS-1:0] in_time_ff [0 : IN_DATA_BUF-1];
    for (genvar i=0; i<IN_DATA_BUF; i=i+1) begin
        assign in_time_ff[i] = in_data_ff[i][REG_BITS-1:0];
    end

    // data and time at timeout
    wire [STREAM_DATA_BITS-1:0] next_data = in_data_ff[IN_DATA_BUF-1];
    wire [REG_BITS-1:0] next_time  = in_time_ff[IN_DATA_BUF-1];
    wire [REG_BITS-1:0] next_time2 = in_time_ff[IN_DATA_BUF-2];
    wire next_IRQ                  = next_data[BIT_IRQ+REG_BITS];
    wire next_TRST                 = next_data[BIT_TRST+REG_BITS];
    wire next_NOP;
    if ( USE_STROBE == "YES" ) begin
        assign next_NOP = next_NOP_ff[IN_DATA_BUF-1];
    end
    else begin
        assign next_NOP = next_data[BIT_NOP+REG_BITS];
    end

    // timer error detection
    // error if next time is smaller or equal actual time
    // requires reset to reset
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) error_time_ff <= 1'b0;
        else error_time_ff <= ( run && in_valid && in_ready && ( next_time2 <= next_time ) ) ? 1'b1 : error_time_ff;
    end

    //////////////////////////////////////////////////////////////////////////////////
    // clock division of clk_bus, clk_strb_0 and clk_strb_1
    // we need these dividers to reach 1MHz ourput since the PLL give only 6.25MHz as the lowest outputs.
    // we could use a BUFR with fixed division (1-8) but then we cannot program it anymore if we want higher frequencies. 
    
    // clock divider counter
    // for clk_div == 0 remains at 0
    reg [CLK_DIV_BITS-1:0] clk_div_count = 0;
    wire timer_tick = ( clk_div_count == (clk_div_bus-1) );
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) clk_div_count <= 0;
        else clk_div_count <= ( state_run & (~state_wait) ) ?  ( timer_tick ) ? 0 : clk_div_count + 1 : clk_div_count;
    end
    
    // stop trigger window divider
    // when stop trigger is active then run bit is reset. 
    // stop trigger window divider delays stopping until trg_tick is high.
    // this allows to stop several boards synchroneously even when there is jitter and propagation delay.
    // trg_tick is high every trg_div cycle but might be delayed until trg_tick_delay is not active anymore.
    // this enaures that stop trigger does not interfer with strobe generation, i.e. strobe timing is preserved.
    // when trg_div_bus = 0 then trg_tick = 1'b1 all the time and stop trigger immediately stops run.
    reg [TRG_DIV_BITS-1:0] trg_div_count = 0;
    wire trg_tick_delay = (clk_div_count >= (clk_div_bus-3));
    wire trg_tick = (trg_div_bus == 0) | ( ( trg_div_count == (trg_div_bus - 1) ) & (~trg_tick_delay) );
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) trg_div_count <= 0;
        else trg_div_count <= ( state_run & (~state_wait) ) ? (( trg_tick | timer_tick ) ? 0 : 
                                              ((( trg_div_count == (trg_div_bus - 1)) & trg_tick_delay) ? trg_div_count : trg_div_count + 1)) : 
                                              trg_div_count;
    end
    

    //////////////////////////////////////////////////////////////////////////////////
    // timer and timeout

    // timer counter update on each timer_tick
    // reset with reset_bus_n, running while run bit is set
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) timer <= 0;
        else timer <= ( state_run & timer_tick ) ? timer + 1 : timer;
    end

    // data counter incremented on timeout
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) samples <= 0;
        else samples <= ( timeout ) ? samples + 1 : samples;
    end
    
    // timeout detection
    // we have to compensate for 2 cycles latency and have 3 scenarios:
    // TODO: these hish-speed = small clk_div scenarios need to be simulated again carefully! disabled for the moment. 
    // time_check[2]: bus divider > 2
    // time_check[1]: bus divider = 2
    // time_check[0]: bus divider = 1
    reg [2:0] time_check;
    reg [1:0] timeout_ff;
    //wire state_run_w = state_ready & run & (~state_end);
    //wire state_run_w = state_ready & (~state_end) & ( run | (state_run & (clk_div_count >= (clk_div_bus-3))) );
    /* wire state_run_w;
    localparam integer TRG_STOP_MASK = (1<<(TRG_STOP_WINDOW+1))-1;
    if ( TRG_STOP_WINDOW == 0 ) begin
        assign state_run_w = state_ready & (~state_end) & ( run | (state_run & (clk_div_count >= (clk_div_bus-3))) );
    end
    else begin
        assign state_run_w = state_ready & (~state_end) & ( run | (state_run & ((clk_div_count >= (clk_div_bus-3)) | ((clk_div_count & TRG_STOP_MASK) != 0))) );
        //assign state_run_w = state_ready & (~state_end) & ( run | (state_run & (clk_div_count >= (clk_div_bus>>1))) );
    end*/
    // run when ready, not end and stop at next trg_tick
    wire state_run_w = state_ready & (~state_end) & ( run | state_run );    
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) begin
            time_check <= 3'b000;
            timeout_ff <= 2'b00;
        end
        else if ( state_run ) begin
        //else if ( state_run_or_wait ) begin
            time_check[2] <= ( (in_valid_ff[IN_DATA_BUF-1] && (timer == in_time_ff[IN_DATA_BUF-1] )) ) && 
                               ( clk_div_count == (clk_div_bus-3) );
            time_check[1] <= ( (in_valid_ff[IN_DATA_BUF-1] && ((timer+1) == in_time_ff[IN_DATA_BUF-1] )) || 
                               (in_valid_ff[IN_DATA_BUF-2] && ((timer+1) == in_time_ff[IN_DATA_BUF-2] )) ) && 
                               ( clk_div_count == (clk_div_bus-1) ) && ( clk_div_bus == 2 );
            time_check[0] <= ( (in_valid_ff[IN_DATA_BUF-1] && ((timer+2) == in_time_ff[IN_DATA_BUF-1] )) || 
                               (in_valid_ff[IN_DATA_BUF-2] && ((timer+2) == in_time_ff[IN_DATA_BUF-2] )) || 
                               (in_valid_ff[IN_DATA_BUF-3] && ((timer+2) == in_time_ff[IN_DATA_BUF-3] )) ) && 
                               ( clk_div_bus == 1 );
            timeout_ff[0] <= |time_check;
            //timeout_ff[1] <= timeout_ff[0];
        end
        else if ( state_run_w ) begin // special case for next_time == 1 and bus divider = 1 we have to check 1 cycle earlier 
            time_check[2] <= 1'b0;
            time_check[1] <= 1'b0;
            time_check[0] <= in_valid_ff[IN_DATA_BUF-1] && ( in_time_ff[IN_DATA_BUF-1] == 1 ) && ( clk_div_bus == 1 );
        end
        else begin
            time_check <= 3'b000;
            timeout_ff <= timeout_ff;
        end
    end 
    assign timeout_next_cycle  = |time_check;
    assign timeout             = timeout_ff[0];
    
    //////////////////////////////////////////////////////////////////////////////////
    // RX stream data output

    // output valid signal. this controls unloading of out_data.
    // set with timeout
    // reset with out_ready & not timeout 
    reg out_valid_ff;
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) out_valid_ff <= 1'b0;
        else if ( timeout ) out_valid_ff <= 1'b1;
        else if ( out_ready ) out_valid_ff <= 1'b0;
        else out_valid_ff <= out_valid_ff;
    end
    assign out_valid = out_valid_ff;

    // RX data
    reg [STREAM_DATA_BITS-1:0] out_data_ff;
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) out_data_ff <= 0;
        else if ( timeout ) out_data_ff <= next_data;
        else out_data_ff <= out_data_ff;
    end
    assign out_data = out_data_ff;
    
    // output error detection
    // error if timeout but output not ready
    // requires reset to reset
    // TODO: enable with a bit. sometimes we might not care.
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) error_out_ff <= 1'b0;
        else error_out_ff <= ( timeout & (~out_ready) ) ? 1'b1 : error_out_ff;
    end

    //////////////////////////////////////////////////////////////////////////////////
    // bus data output on timeout pulse
    
    // bus data pipeline to match strobe generation
    // the enable bits are transmitted the same as data to ensure same timing
    // we add for bus one cycle so strobe can be set close to 0 delay (and negative). 
    localparam integer STRB_SYNC = 1;
    localparam integer BUS_SYNC  = 1; 
    reg [BUS_DATA_BITS-1:0] bus_data_buf [0 : BUS_SYNC - 1];
    reg [BUS_ADDR_BITS*2-1:0] bus_addr_buf [0 : BUS_SYNC - 1];
    //integer i;
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) begin
            for (i = 0; i < BUS_SYNC; i = i + 1) begin
                bus_data_buf[i] <= 0;
                bus_addr_buf[i] <= 0;
            end
        end
        else if ( state_run ) begin
            if ( timeout & (~next_NOP) ) begin
                bus_data_buf[0] <= next_data[REG_BITS+BUS_DATA_BITS-1 -: BUS_DATA_BITS];
                bus_addr_buf[0] <= next_data[REG_BITS+BUS_DATA_BITS+BUS_ADDR_BITS*2-1 -: BUS_ADDR_BITS*2];
                for (i = 1; i < BUS_SYNC; i = i + 1) begin
                    bus_data_buf[i] <= bus_data_buf[i-1];
                    bus_addr_buf[i] <= bus_addr_buf[i-1];
                end
            end
            else begin
                bus_data_buf[0]  <= bus_data_buf[0];
                bus_addr_buf[0]  <= bus_addr_buf[0];
                for (i = 1; i < BUS_SYNC; i = i + 1) begin
                    bus_data_buf[i] <= bus_data_buf[i-1];
                    bus_addr_buf[i] <= bus_addr_buf[i-1];
                end
            end
        end
        else begin
            for (i = 0; i < BUS_SYNC; i = i + 1) begin
                bus_data_buf[i] <= 0;
                bus_addr_buf[i] <= 0;
            end
        end
    end

    // on timeout toggle strobe bit
    // this triggers strobe output
    reg out_strb_tgl = 1'b0;
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) out_strb_tgl <= 1'b0;
        else out_strb_tgl <= ( state_run & timeout & (~next_NOP) ) ? ~out_strb_tgl : out_strb_tgl;
    end     
    
    //////////////////////////////////////////////////////////////////////////////////
    // strobe generation @ clk_strb_0 and clk_strb_1 (have put back to clk_bus since did not work)
        
    // assign strb_delay
    wire [STRB_DELAY_BITS-1 : 0] strb_start [0 : NUM_STRB-1];
    wire [STRB_DELAY_BITS-1 : 0] strb_end [0 : NUM_STRB-1];
    if (NUM_STRB == 1) begin
        assign {strb_end[0],strb_start[0]} = strb_delay_bus;
    end
    else begin
        assign {strb_end[1],strb_start[1],strb_end[0],strb_start[0]} = strb_delay_bus;
    end
        
    // when strobe is a toggle bit (i.e. strb_end == 0) then reset_bus_n does not reset strobe
    // this value is updated only after strb_end has been updated
    reg [NUM_STRB-1:0] strb_reset = {(NUM_STRB){1'b0}};
    for (genvar i = 0; i < NUM_STRB; i = i + 1)
    begin : GEN_STRB_TGL
        always @ ( posedge clk_bus ) begin
            strb_reset[i] <= ( strb_delay_reload ) ? (strb_end[i] == 0) : strb_reset[i];
        end
    end

    // init memory with zeros
    reg strb_out [0 : NUM_STRB-1];
    initial begin
        for (i = 0; i < NUM_STRB; i = i + 1) begin
            strb_out[i] <= 0;
        end
    end

    for (genvar i = 0; i < NUM_STRB; i = i + 1)
    begin : GEN_STRB
        // strobe generation
        // start strobe when out_strb_tgl received out of cdc
        // keep high for clk_div_strb cycles (1 cycle for clk_div_strb[i] == 0)
        reg strb_tgl = 1'b0;
        reg [CLK_DIV_BITS-1:0] strb_cnt = 0;
        wire strb_active = ( strb_tgl ^ out_strb_tgl );
        always @ ( posedge clk_bus ) begin
            if ( reset_bus_n == 1'b0 ) begin
                strb_tgl <= 1'b0;
                strb_cnt <= {CLK_DIV_BITS{1'b0}};
                strb_out[i] <= strb_reset[i] ? strb_out[i] : 1'b0; // reset only if not toggling strobe, otherwise keep old value
            end
            else if ( strb_end[i] == 0 ) begin // toggle strobe at start
                if ( strb_active ) begin
                    strb_tgl <= ( strb_cnt == strb_start[i] ) ? out_strb_tgl : strb_tgl;
                    strb_cnt <= strb_cnt + 1;
                    strb_out[i] <= ( strb_cnt == strb_start[i] ) ? ~strb_out[i] : strb_out[i];
                end
                else begin
                    strb_tgl <= strb_tgl;
                    strb_cnt <= {CLK_DIV_BITS{1'b0}};
                    strb_out[i] <= strb_out[i]; // TODO: cannot disable output & maintain state over reset
                end
            end
            else begin // pulse strobe from start to end
                if ( strb_active ) begin
                    strb_tgl <= ( strb_cnt == strb_end[i] ) ? out_strb_tgl : strb_tgl;
                    strb_cnt <= strb_cnt + 1;
                    strb_out[i] <= ( strb_cnt == strb_start[i] ) ? 1'b1 : strb_out[i];
                end
                else begin
                    strb_tgl <= strb_tgl;
                    strb_cnt <= {CLK_DIV_BITS{1'b0}};
                    strb_out[i] <= 1'b0;
                end
            end
        end

    end
    
    //////////////////////////////////////////////////////////////////////////////////
    // bus output buffer to minimize skew @ clk_bus
    
    // bus data
    (* IOB = "TRUE" *)
    reg [BUS_DATA_BITS-1:0] bus_data_ff;
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) bus_data_ff <= 0;
        else bus_data_ff <= bus_data_buf[BUS_SYNC-1];
    end
    assign bus_data = bus_data_ff;

    // bus address
    (* IOB = "TRUE" *)
    reg [BUS_ADDR_BITS*2-1:0] bus_addr_ff;
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) bus_addr_ff <= 0;
        else bus_addr_ff <= bus_addr_buf[BUS_SYNC-1];
    end
    assign bus_addr_0 = bus_addr_ff[BUS_ADDR_BITS-1:0]; // data bits [23:16]
    if ( BUS_ADDR_1_USE == "ADDR0" ) begin              // "ADDR0" = same as bus_addr_0 = data bits [23:16]
        assign bus_addr_1 = bus_addr_ff[BUS_ADDR_BITS-1:0];
    end
    else if ( BUS_ADDR_1_USE == "DATA_HIGH" ) begin     // "DATA_HIGH" = use data bits [31:24]
        assign bus_addr_1 = bus_addr_ff[BUS_ADDR_BITS*2-1 -: BUS_ADDR_BITS];
    end
    else begin                                          // default: "ZERO" = set all to 0
        assign bus_addr_1 = {BUS_ADDR_BITS{1'b0}};
    end
    
    //////////////////////////////////////////////////////////////////////////////////
    // bus strobe output buffer @ clk_strb_0 and clk_strb_1

    (* IOB = "TRUE" *)
    reg bus_strb_ff [0 : NUM_STRB-1];
    for (genvar i = 0; i < NUM_STRB; i = i + 1)
    begin : GEN_STRB_BUF

        always @ ( posedge clk_bus ) begin
            bus_strb_ff[i] = strb_out[i];
        end
        assign bus_strb[i] = bus_strb_ff[i];
        
    end

    //////////////////////////////////////////////////////////////////////////////////
    // assign status bits

    // end_pulse pulses right after last timeout.
    // end_state is reached at next timer_tick to ensure bus data and strobe is output completely
    //           end is not reached when restart is enabled
    // end_next cycle pulses before end_state is reached. is not active when restart is enabled..
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) begin
            reset_done        <= 1'b1;
            state_restart     <= 1'b0;
            state_ready       <= 1'b0;
            state_run         <= 1'b0;
            state_wait        <= 1'b0;
            end_next_cycle    <= 1'b0;
            end_pulse         <= 1'b0;
            state_end         <= 1'b0;
        end
        else begin
            reset_done        <= reset_done; 
            state_restart     <= (restart_en & state_run & state_wait & run) ? ~state_restart : state_restart; // toggle restart bit
            state_ready       <= reset_done & (~error_time_ff) & (~error_out_ff) & (~error_in_ff) & ( next_valid | state_ready );
            state_run         <= state_run_w;
            //state_run         <= state_ready & (~state_end) & ( run | (state_run_or_wait & (clk_div_count >= (clk_div_bus-3))) );
            state_wait        <= state_ready & (~state_end) & state_run & (~run) & ( trg_tick | state_wait );
            end_next_cycle    <= state_run & (~state_wait) & ( samples == num_samples ) & timer_tick & (~state_restart);
            end_pulse         <= state_run & (~state_wait) & ( samples == (num_samples-1) ) & timeout;
            state_end         <= end_next_cycle | state_end;
        end
    end
    
    assign status_bits = {state_irq,error_time_ff,error_out_ff,error_in_ff,state_restart,state_wait,state_end,state_run,state_ready};    
    assign status_update = 1'b0;
    
    //////////////////////////////////////////////////////////////////////////////////
    // irq toogle bits @ clk_bus
    
    reg irq_bit_old = 1'b0;
    wire irq_timer;
    if ( IRQ_FREQ_BITS == 0 ) assign irq_timer = 1'b0; // disabled
    else assign irq_timer = irq_freq_en & (timer[IRQ_FREQ_BITS-1] ^ irq_bit_old);
    wire irq_data  = irq_data_en & (timeout_next_cycle & next_IRQ & next_valid); 
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) begin
            state_irq <= 2'b00;
            irq_bit_old <= 1'b0; 
        end
        else begin
            state_irq[0] <= irq_timer ? ~state_irq[0] : state_irq[0];
            state_irq[1] <= irq_data ? ~state_irq[1] : state_irq[1];
            irq_bit_old <= irq_timer ? timer[IRQ_FREQ_BITS-1] : irq_bit_old;
        end
    end
    
    //////////////////////////////////////////////////////////////////////////////////
    // board time and samples
    // update on irq or end
    
    reg [REG_BITS-1:0] board_time_ff = 0;
    reg [REG_BITS-1:0] board_samples_ff = 0;
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) begin
            board_time_ff    <= 0;
            board_samples_ff <= 0;
        end
        else begin
            board_time_ff    <= ( irq_timer | end_pulse ) ? timer - 1 : board_time_ff;
            board_samples_ff <= ( irq_timer | end_pulse ) ? samples : board_samples_ff;      
        end
    end
    assign board_time    = board_time_ff;
    assign board_samples = board_samples_ff;

    //////////////////////////////////////////////////////////////////////////////////
    // test timer for arbitrary tests controlled by test bits
    // TODO: disabled now, maybe enable again?
    
    // test bits
    //wire test_run    = test_bits[0];
    //wire test_update = test_bits[1];
    
    /* run bit edge detector
    reg test_run_ff = 0;
    always @ ( posedge clk_bus ) begin
        test_run_ff <= test_run;
    end
    wire [1:0] test_run_edge = {test_run_ff,test_run};

    // update bit edge detector
    reg test_update_ff = 0;
    always @ ( posedge clk_bus ) begin
        test_update_ff <= test_update;
    end
    wire [1:0] test_update_edge = {test_update_ff,test_update};
    
    // test timer is running while test_run is high
    // the timer value is saved into board_time_ext on rising edge edge of test_update or falling edge of test_run
    // timer is reset only by external reset signal
    // since board_samples_ext is not used we save last value of board_time_ext. free for other purpose in the future.
    reg [REG_BITS-1:0] test_timer = 0;
    reg [REG_BITS-1:0] test_time_0 = 0;
    reg [REG_BITS-1:0] test_time_1 = 0;
    wire test_reg_update = (( test_run_edge == 2'b10 ) || ( test_update_edge == 2'b01));
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) begin
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
    */

    // TODO: might be useful for something?
    assign board_time_ext    = 0;
    assign board_samples_ext = 1;
    
endmodule
