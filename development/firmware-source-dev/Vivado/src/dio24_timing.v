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
// - BIT_STOP = 0-based index of bit signalling run stop when enabled
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
// last change 2024/12/2 by Andi
//////////////////////////////////////////////////////////////////////////////////

module dio24_timing # (
    // AXI stream data input
    parameter integer STREAM_DATA_BITS  = 65,       // 64 + 1 {in_last,in_data}
    
    // data bits
    parameter integer BUS_DATA_BITS     = 16,       // 16
    parameter integer BUS_ADDR_BITS     =  8,       // 8
    parameter         BUS_ADDR_1_USE    = "ZERO",   // "ZERO"/"ADDR0"/"DATA_HIGH" = low / same as bus_addr_0 = data[23:16], data[31:24]
    parameter integer BUS_RESET         = 1,        // 0 = keep bus after end at last state, otherwise reset to zero. 
    parameter integer NUM_STRB          = 1,        // number of bits for bus_strb (1 or 2)
    parameter integer NUM_STRB_CONT     = 2,        // number of bits for strb and strb_cont (2)
    parameter integer NUM_BUS_EN        = 2,        // number of bits for bus_en (1 or 2)
    parameter integer REG_BITS          = 32,       // must be 32
    parameter integer CTRL_BITS         = 7,        // 7
    parameter integer STATUS_BITS       = 10,       // 10
    parameter integer CLK_DIV_BITS      = 8,        // 8: clock divider = 1-255
    parameter integer SYNC_DELAY_BITS   = 10,       // 10
    
    // I/O bits
    parameter integer NUM_IN            = 3,        // number of external inputs (3)
    parameter integer NUM_OUT           = 3,        // number of external outputs (3)
    parameter integer NUM_LED           = 3,        // types of led = red,green,blue (3)

    // synchronization
    parameter integer SYNC              = 2,        // number of synchronization stages: 2-3
        
    // status irq toggle frequency
    parameter integer IRQ_FREQ_BITS     = 21       // 21 = 12-24Hz for 100MHz clk_bus
)
(
    // clocks and reset
    input clk_bus,
    input clk_det,
    input reset_bus_n,
    input reset_hw_bus_n,                           // no software reset
    input reset_det_n,
    // control registers @ clk_bus
    input [CTRL_BITS-1:0] ctrl_bits,
    input [REG_BITS-1:0] num_samples,
    input [REG_BITS-1:0] num_cycles,
    input num_reload,                               // pulses when num_samples/cycles are updated
    input [CLK_DIV_BITS-1:0] clk_div,
    input [CLK_DIV_BITS*NUM_STRB_CONT*2-1:0] strb_delay,
    input timing_reload,                            // pulses when clk_div and strb_delay are updated
    input [SYNC_DELAY_BITS-1:0] sync_delay,         // for future use
    input sync_delay_reload,                        // pulses when sync_delay is updated
    input [REG_BITS-1:0] ctrl_in0_det,
    input [REG_BITS-1:0] ctrl_in0,
    input [REG_BITS-1:0] ctrl_in1, 
    input ctrl_in_reload,                           // pulses when ctrl_in0/1 are updated   
    input [REG_BITS-1:0] ctrl_out0,
    input [REG_BITS-1:0] ctrl_out1, 
    input ctrl_out_reload,                          // pulses when ctrl_out0/1 are updated   
    input [REG_BITS-1:0] force_out,
    input force_reload,                             // pulses when force_out is updated
    // TS/RX status @ clk_bus
    input TX_full,
    input TX_empty,
    input RX_full,
    input RX_empty,
    // external I/O @ clk_bus
    input  [NUM_IN    -1:0] ext_in,
    output [NUM_OUT   -1:0] ext_out,
    output [NUM_LED   -1:0] led_out,
    input                   irq_TX,
    input                   irq_RX,
    input                   irq_FPGA,
    // auto-sync control/status bits
    //input  as_en,
    output as_run,
    input  as_start,
    input  sync_out,
    input  sync_mon,
    input  sync_en,
    // status registers time @ clk_bus
    output [STATUS_BITS-1:0] status_bits,
    output [REG_BITS-1:0] board_time,
    output [REG_BITS-1:0] board_samples,
    output [REG_BITS-1:0] board_time_ext,
    output [REG_BITS-1:0] board_samples_ext,
    output [REG_BITS-1:0] board_cycles,    
    output status_update,
    // TX stream data input
    input [STREAM_DATA_BITS-1:0] in_data,
    input  in_valid,
    output in_ready,
    // RX stream data output
    output [STREAM_DATA_BITS-1:0] out_data,
    output out_valid,
    input  out_ready,
    // bus output
    output [BUS_DATA_BITS-1:0] bus_data,
    output [BUS_ADDR_BITS-1:0] bus_addr_0,
    output [BUS_ADDR_BITS-1:0] bus_addr_1,
    output [NUM_STRB     -1:0] bus_strb,
    output [NUM_BUS_EN   -1:0] bus_en,                 
    // trigger signals
    output start_trg_en,
    output start_trg_tgl,
    output start_trg_tgl_det,
    output stop_trg_tgl,
    output restart_trg_tgl
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
    reg [REG_BITS-1:0] timer   = 0;
    reg [REG_BITS-1:0] samples = 0;
    reg [REG_BITS-1:0] cycles  = 0;
    
    wire svr_ready      = ctrl_bits[0];       // server/driver ready
    wire error_ext      = ctrl_bits[1];       // error condition outside module: requires reset    
    wire run_en         = ctrl_bits[2];       // run bit from control register, might reset temporarily.
    wire restart_en     = ctrl_bits[3];       // allow restart at end of cycle
    wire irq_freq_en    = ctrl_bits[4];       // generate irq's at fixed rate (20Hz typically)
    wire irq_data_en    = ctrl_bits[5];       // allow irq from data bit
    wire clk_ext_locked = ctrl_bits[6];       // external clock locked
    wire clk_ext_sel    = ctrl_bits[7];       // external clock selected
    wire clk_ext_lost   = ctrl_bits[8];       // external clock lost
    wire as_en          = ctrl_bits[9];
    //wire test_update  = ctrl_bits[5];
    
    // registered status bits
    reg state_ready       = 1'b0;     // high when first data received and no error.
    reg state_run         = 1'b0;     // high while running. stays high during waiting.
    reg state_end         = 1'b0;     // all data transmitted. not set when state_restart is high.
    reg state_wait        = 1'b0;     // wait for restart trigger.
    reg state_restart     = 1'b0;     // restart after all data transmitted. error_in if no data available.
    reg [1:0] state_irq   = 2'b00;    // {irq_data,irq_freq} bits
    //reg end_next_cycle    = 1'b0;     // high one cycle before state_end. not set when state_restart is high.
    //reg end_pulse         = 1'b0;     // same as end_next_cycle but is set even with state_restart.
    reg reset_done        = 1'b0;     // high during & after reset. 
    
    // error bits
    reg error_in_ff     = 1'b0; // input error
    reg error_out_ff    = 1'b0; // output error
    reg error_time_ff   = 1'b0; // timing error
    wire state_error_w = error_ext | error_in_ff | error_out_ff | error_time_ff;
    
    // timeout signals
    wire timeout;
    wire timeout_next_cycle;

    // end signals can be used together with timeout or timeout_next_cycle of last sample
    wire end_of_cycle_w = state_run & (~state_wait) & ( samples == (num_samples-1) );
    wire last_cycle     = (num_cycles != 0) && (cycles == (num_cycles-1));
    wire end_w          = end_of_cycle_w & ~( restart_en & ~last_cycle );
    wire restart_w      = end_of_cycle_w &    restart_en & ~last_cycle;
    wire first_sample   = samples == 0;
        
    //////////////////////////////////////////////////////////////////////////////////
    // input data buffer
    // used to buffer gaps in input data stream and as a pipeline to combine special data bits.

    // number of input data buffers. must be 0 or >= 2.
    // TODO: for >= 2 must be simulated again since lose 2nd sample!
    localparam integer IN_DATA_BUF = 0;
    
    wire [STREAM_DATA_BITS-1:0] next_data;
    wire                        next_reload;
    wire [REG_BITS-1:0]         next_time;
    wire                        next_valid;
        
    if (IN_DATA_BUF >= 2) begin

        reg next_valid = 1'b0;
        reg [IN_DATA_BUF-1:0] in_valid_ff = {IN_DATA_BUF{1'b0}};
        reg [STREAM_DATA_BITS-1:0] in_data_ff [0 : IN_DATA_BUF - 1];
        reg in_ready_ff = 1'b0;
        //wire in_load = in_ready & (in_valid | timeout);
        wire in_load = in_ready | timeout;
        integer i;
        always @ ( posedge clk_bus ) begin
            if ( reset_bus_n == 1'b0 ) begin
                for (i=0; i<IN_DATA_BUF; i=i+1) begin
                    in_data_ff[i] <= 0;
                end
                in_valid_ff <= {IN_DATA_BUF{1'b0}};
                in_ready_ff <= 1'b0;
            end
            else begin
                in_ready_ff    <= timeout_next_cycle | (in_ready & in_valid ? ~in_valid_ff[IN_DATA_BUF-2] : ~in_valid_ff[IN_DATA_BUF-1]);
                in_data_ff [0] <= in_load ? in_data  : in_data_ff [0];
                in_valid_ff[0] <= in_load ? in_ready & in_valid : in_valid_ff[0];
                if ( IN_DATA_BUF > 2 ) begin
                    for (i=1; i<IN_DATA_BUF-1; i=i+1) begin
                        in_data_ff [i] <= in_load ? in_data_ff [i-1] : in_data_ff [i];
                        in_valid_ff[i] <= in_load ? in_valid_ff[i-1] : in_valid_ff[i];
                    end
                end
                in_data_ff [IN_DATA_BUF-1] <= in_load ? in_data_ff [IN_DATA_BUF-2] : in_data_ff[IN_DATA_BUF-1];
                in_valid_ff[IN_DATA_BUF-1] <= in_load ? in_valid_ff[IN_DATA_BUF-2] : ~next_valid ? 1'b0 : in_valid_ff[IN_DATA_BUF-1];
            end
        end
        assign in_ready = in_ready_ff;
        
        //////////////////////////////////////////////////////////////////////////////////
        // next data, time and special bits.
        // next_time gives timeout when next_data is output on bus.
        // error_in when next_valid is low after timeout and not end! i.e. when no data available when needed.
        // error_time when next_time <= following time in input data buffer. 
    
        // update: register next_ variables and decouple from input buffer/pipeline
        // next time and data and valid bit @ clk_bus
        reg [STREAM_DATA_BITS-1:0] next_data_ff = 0;
        
        if (IN_DATA_BUF >= 2) begin
            always @ ( posedge clk_bus ) begin
                if ( reset_bus_n == 1'b0 ) begin
                    next_data_ff <= 0;
                    next_valid   <= 1'b0;
                end
                else if ( next_reload ) begin
                    next_data_ff <= in_data_ff [IN_DATA_BUF-1];
                    next_valid   <= in_valid_ff[IN_DATA_BUF-1];
                end
                else begin
                    next_data_ff <= next_data_ff;
                    next_valid   <= next_valid;
                end
            end
        end
        else begin
            always @ ( posedge clk_bus ) begin
                if ( reset_bus_n == 1'b0 ) begin
                    next_data_ff <= 0;
                    next_valid   <= 1'b0;
                end
                else if ( next_reload ) begin
                    next_data_ff <= in_data;
                    next_valid   <= in_valid;
                end
                else begin
                    next_data_ff <= next_data_ff;
                    next_valid   <= next_valid;
                end
            end
        end
        assign next_time  = next_data_ff[REG_BITS-1:0];
        assign next_data   = next_data_ff;
        assign next_reload = timeout | ~next_valid; // same as in_ready
    
        // next_time and next_valid signals after timeout
        //assign next_next_time  = in_data_ff [IN_DATA_BUF-1];
        //assign next_next_valid = in_valid_ff[IN_DATA_BUF-1];
    
    end
    else begin
    
        // bypass input buffer 
        // next_reload = in_ready = (timeout | ~next_valid)
        assign in_ready    = next_reload;
        assign next_data   = in_data;
        assign next_time   = in_data[REG_BITS-1:0];
        assign next_reload = timeout | ~next_valid; // same as in_ready
        assign next_valid  = in_valid;
        
    end
    
    // last time for time error checking
    reg next_reload_ff = 1'b0;
    reg [REG_BITS-1:0] last_time  = {REG_BITS{1'b0}};
    reg                last_valid = 1'b0;
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) begin
            last_time  <= {REG_BITS{1'b0}};
            last_valid <= 1'b0;
        end
        else begin
            last_time  <= (next_reload_ff) ? next_time  : last_time;
            last_valid <= (next_reload_ff) ? next_valid : last_valid;
        end
        next_reload_ff <= next_reload;
    end
    
    //////////////////////////////////////////////////////////////////////////////////
    // input multiplexer for trigger and special data bits

    // trigger inputs
    //wire start_trg_en;
    wire stop_trg_en;
    wire restart_trg_en;
    wire start_trg_pulse;
    wire stop_trg_pulse;
    wire restart_trg_pulse;
    //assign {restart_trg_pulse,restart_trg_en,stop_trg_pulse,stop_trg_en,start_trg_pulse,start_trg_en} = ctrl_trg;
    // registered special data bits
    wire next_STOP;
    wire next_NOP;
    wire next_IRQ;
    ctrl_in_mux # (
        .REG_WIDTH          (REG_BITS),
        .NUM_IN             (NUM_IN),
        .SYNC               (SYNC),
        .IN_DATA_BUF        (IN_DATA_BUF)         
    )
    ctrl_in_mux_inst (
        .clock_bus          (clk_bus),
        .clock_det          (clk_det),
        .reset_bus_n        (reset_bus_n),
        .reset_det_n        (reset_det_n),
        .ctrl_in0_det       (ctrl_in0_det),
        .ctrl_in0_bus       (ctrl_in0),
        .ctrl_in1_bus       (ctrl_in1),
        .ext_in             (ext_in),
        .run_en             (run_en),
        .data_reload        (next_reload),
        .data_reload_ff     (next_reload_ff),
        .first_sample       (first_sample),
        .state_run          (state_run),
        .state_wait         (state_wait),
        .state_restart      (state_restart),
        .in_valid           (in_valid),
        .data               (in_data[2*REG_BITS-1 -: REG_BITS]),
        .trg_start_en       (start_trg_en),
        .trg_start_pulse    (start_trg_pulse),
        .trg_start_tgl      (start_trg_tgl),
        .trg_start_tgl_det  (start_trg_tgl_det),
        .trg_stop_en        (stop_trg_en),
        .trg_stop_pulse     (stop_trg_pulse),
        .trg_stop_tgl       (stop_trg_tgl),
        .trg_restart_en     (restart_trg_en),
        .trg_restart_pulse  (restart_trg_pulse),
        .trg_restart_tgl    (restart_trg_tgl),
        .data_nop           (next_NOP),
        .data_stop          (next_STOP),
        .data_irq           (next_IRQ)
    );
    
    //////////////////////////////////////////////////////////////////////////////////
    // output multiplexer for external outputs
    // TODO: we reset only with hardware reset in order to keep contiguous strobe output
    //       if this has unwanted side-effects give hw & sw reset into mux module 
    //       and reset registers as needed.

    wire [NUM_STRB_CONT-1:0] strb;
    wire [NUM_STRB_CONT-1:0] strb_cont;
    ctrl_out_mux # (
        .REG_WIDTH(REG_BITS),
        .NUM_OUT(NUM_OUT),
        .NUM_LED(NUM_LED),
        .NUM_BUS_EN(NUM_BUS_EN),
        .NUM_STRB(NUM_STRB_CONT)                
    )
    ctrl_out_mux_inst (
        .clock          (clk_bus),
        .reset_n        (reset_hw_bus_n),       // no software reset
        .ctrl_out0      (ctrl_out0),
        .ctrl_out1      (ctrl_out1),
        .sync_out       (sync_out),
        .sync_en        (sync_en),
        .sync_mon       (sync_mon),
        .clk_ext_locked (clk_ext_locked),
        .clk_ext_sel    (clk_ext_sel),
        .clk_ext_lost   (clk_ext_lost),
        .error          (state_error_w),
        .status_ready   (state_ready),
        .status_run     (state_run),
        .status_wait    (state_wait),
        .status_end     (state_end),
        .status_restart (state_restart),
        .trg_start      (start_trg_tgl),
        .trg_stop       (stop_trg_tgl),
        .trg_restart    (restart_trg_tgl),
        .strb           (strb),
        .strb_cont      (strb_cont),
        .irq_TX         (irq_TX),
        .irq_RX         (irq_RX),
        .irq_FPGA       (irq_FPGA),
        .TX_full        (TX_full),
        .TX_empty       (TX_empty),
        .RX_full        (RX_full),
        .RX_empty       (RX_empty),        
        .out            (ext_out),
        .bus_en         (bus_en),
        .led            (led_out)
    );

    //////////////////////////////////////////////////////////////////////////////////
    // clock division of clk_bus, clk_strb_0 and clk_strb_1
    // we need these dividers to reach 1MHz output since the PLL give only 6.25MHz as the lowest outputs.
    // we could use a BUFR with fixed division (1-8) but then we cannot program it anymore if we want higher frequencies.
    // note: one can switch BUFR on/off with paramters depending on bus clock range
    
    // clock divider counter
    // note: for clk_div == 0 remains at 0, so do not use this!
    // update on 2024/09/20: 
    // - keep clk_div_count counting even in state_wait but do not generate timer_tick
    //   - strobe output remains synchroneous to the bus_clock even across stop/restart
    //     this allows to output contiguous strobe even during wait which was requested by ibk team.
    //   - strobe generation can use the same counter since last strobe can be finished
    //     even when going into wait state.
    //   - the stop window can be deleted since we get automatic a window of the bus output period.
    // update on 2024/10/05:
    // - keep clk_div_count counting always and do not reset
    // - this allows contiguous strobe output as requested by IBK
    // - exception: clk_div register is updated, i.e. timing_reload, then reset 
    //   this ensures that count is not > clk_div
    // - note to avoid glitches in contiguous strobe output:
    //   write clk_div and strb_delay only once at startup and not between each runs!
    reg [CLK_DIV_BITS-1:0] clk_div_count = 0;
    wire timer_tick_cont = ( clk_div_count == clk_div );
    wire timer_tick      = timer_tick_cont & state_run & (~state_wait);
    always @ ( posedge clk_bus ) begin
        clk_div_count <= ( timer_tick_cont | timing_reload ) ? 1 : clk_div_count + 1;
    end

    //////////////////////////////////////////////////////////////////////////////////
    // timer and timeout

    // timer counter update on each timer_tick
    // reset with reset_bus_n, running while run bit is set
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) timer <= 0;
        else timer <= ( state_run & timer_tick ) ? restart_w & timeout_next_cycle ? 0 : timer + 1 : timer;
    end

    // data counter incremented on timeout
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) samples <= 0;
        else samples <= ( timeout ) ? restart_w ? 0 : samples + 1 : samples;
    end
    
    // timeout detection
    // we have to compensate for 2 cycles latency and have 3 scenarios:
    // TODO: these hish-speed = small clk_div scenarios need to be simulated again carefully! disabled for the moment. 
    // time_check[2]: bus divider > 2
    // time_check[1]: bus divider = 2
    // time_check[0]: bus divider = 1
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
    // update 2024/09/20: 
    // - removed time_check[1] and [0] since need to be checked from clk_div_bus = 2 and 1
    //   and renamed time_check[2] -> time_check
    // - (~state_wait) added to time_check
    // - trg_tick not needed anymore
    //reg [2:0]time_check;
    //reg [1:0] timeout_ff;
    reg timeout_ff;
    //wire state_run_w = state_ready & (~state_end) & ( run | state_run );
    //assign timeout_next_cycle = ( (in_valid_ff[IN_DATA_BUF-1] && (timer == in_time_ff[IN_DATA_BUF-1] )) ) && timer_tick;
    assign timeout_next_cycle = ( (next_valid && (timer == next_time)) ) & timer_tick;
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) begin
            //time_check <= 3'b000;
            timeout_ff <= 2'b00;
        end
        else if ( state_run ) begin
        //else if ( state_run_or_wait ) begin
        /*
            time_check[1] <= ( (in_valid_ff[IN_DATA_BUF-1] && ((timer+1) == in_time_ff[IN_DATA_BUF-1] )) || 
                               (in_valid_ff[IN_DATA_BUF-2] && ((timer+1) == in_time_ff[IN_DATA_BUF-2] )) ) && 
                               ( clk_div_count == (clk_div_bus-1) ) && (~state_wait) && ( clk_div_bus == 2 );
            time_check[0] <= ( (in_valid_ff[IN_DATA_BUF-1] && ((timer+2) == in_time_ff[IN_DATA_BUF-1] )) || 
                               (in_valid_ff[IN_DATA_BUF-2] && ((timer+2) == in_time_ff[IN_DATA_BUF-2] )) || 
                               (in_valid_ff[IN_DATA_BUF-3] && ((timer+2) == in_time_ff[IN_DATA_BUF-3] )) ) && 
                               ( clk_div_bus == 1 );
            timeout_ff[0] <= |time_check;
            //timeout_ff[1] <= timeout_ff[0];
        */
            timeout_ff <= timeout_next_cycle;
        end
        /*
        disabled on 2024/09/20
        else if ( state_run_w ) begin // special case for next_time == 1 and bus divider = 1 we have to check 1 cycle earlier 
            time_check[2] <= 1'b0;
            time_check[1] <= 1'b0;
            time_check[0] <= in_valid_ff[IN_DATA_BUF-1] && ( in_time_ff[IN_DATA_BUF-1] == 1 ) && ( clk_div_bus == 1 );
        end
        */
        else begin
            //time_check <= 3'b000;
            timeout_ff <= timeout_ff;
        end
    end 
    //assign timeout_next_cycle  = |time_check;
    //assign timeout             = timeout_ff[0];
    assign timeout             = timeout_ff;
    
    //////////////////////////////////////////////////////////////////////////////////
    // RX stream data output

    // output valid signal. this controls unloading of out_data.
    // set with timeout
    // reset with out_ready & not timeout 
    reg out_valid_ff;
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) out_valid_ff <= 1'b0;
        else if ( timeout )        out_valid_ff <= 1'b1;
        else if ( out_ready )      out_valid_ff <= 1'b0;
        else                       out_valid_ff <= out_valid_ff;
    end
    assign out_valid = out_valid_ff;

    // RX data
    reg [STREAM_DATA_BITS-1:0] out_data_ff;
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) out_data_ff <= 0;
        else if ( timeout )        out_data_ff <= next_data;
        else                       out_data_ff <= out_data_ff;
    end
    assign out_data = out_data_ff;
    
    //////////////////////////////////////////////////////////////////////////////////
    // bus data output on timeout pulse
    
    // bus data buffer and pipeline to match strobe generation
    // the enable bits are transmitted the same as data to ensure same timing
    // minimum BUS_SYNC = 1 need to buffer bus output.
    localparam integer BUS_SYNC = 1;
    
    reg [BUS_DATA_BITS  -1:0] bus_data_buf [0 : BUS_SYNC - 1];
    reg [BUS_ADDR_BITS*2-1:0] bus_addr_buf [0 : BUS_SYNC - 1];
    reg force_active = 1'b0;
    integer i;
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) begin
            for (i = 0; i < BUS_SYNC; i = i + 1) begin
                bus_data_buf[i] <= 0;
                bus_addr_buf[i] <= 0;
                force_active    <= 1'b0;
            end
        end
        else if ( state_run ) begin // run state
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
            force_active <= 1'b0;
        end
        else if ( force_reload | force_active ) begin // force output until next reset or run state
            bus_data_buf[BUS_SYNC-1] <= force_out[BUS_DATA_BITS-1 -: BUS_DATA_BITS];
            bus_addr_buf[BUS_SYNC-1] <= force_out[BUS_DATA_BITS+BUS_ADDR_BITS*2-1 -: BUS_ADDR_BITS*2];
            force_active <= 1'b1;
        end
        else if ( BUS_RESET != 0 ) begin // not in run state: reset bus
            for (i = 0; i < BUS_SYNC; i = i + 1) begin
                bus_data_buf[i] <= 0;
                bus_addr_buf[i] <= 0;
            end
        end
    end
        
    //////////////////////////////////////////////////////////////////////////////////
    // strobe generation @ clk_bus
    // minimum strobe start = 1: bus output is aligned with strobe pulse rising edge.
    // note: strb start = 0 does not work since clk_div_count = 1 at bus output.
                            
    wire [CLK_DIV_BITS-1 : 0] strb_start [0 : NUM_STRB_CONT-1];
    wire [CLK_DIV_BITS-1 : 0] strb_end   [0 : NUM_STRB_CONT-1];
    reg [NUM_STRB_CONT-1 : 0] strb_toggle  = {NUM_STRB_CONT{1'b0}};
    reg [NUM_STRB_CONT-1 : 0] strb_cont_ff = {NUM_STRB_CONT{1'b1}};
    reg [NUM_STRB_CONT-1 : 0] strb_bus_ff  = {NUM_STRB_CONT{1'b1}};
    reg strb_en_ff = 1'b0;
    reg strb_valid = 1'b0;  // do not output strobe before timing data is written
    for (genvar i = 0; i < NUM_STRB_CONT; i = i + 1)
    begin : GEN_STRB_CONT
        // contiguous strobe generation
        always @ ( posedge clk_bus ) begin
            if ( reset_hw_bus_n == 1'b0 ) begin
                strb_toggle[i]  <= 1'b0;
                strb_cont_ff[i] <= 1'b0;
                strb_bus_ff [i] <= 1'b0;
                strb_valid      <= 1'b0;
            end
            else if ( timing_reload ) begin // reset strobe
                strb_toggle[i]  <= (strb_end[i] == 0);
                strb_cont_ff[i] <= 1'b0;
                strb_bus_ff [i] <= 1'b0;
                strb_valid      <= 1'b1;
            end
            else if ( strb_valid ) begin
                if (strb_toggle[i]) begin // toggle strobe
                    strb_cont_ff[i] <= ( clk_div_count == strb_start[i] ) ? ~strb_cont_ff[i] : strb_cont_ff[i];
                    strb_bus_ff [i] <= ( force_reload | force_active    ) ? force_out[BUS_DATA_BITS+BUS_ADDR_BITS+i] :
                                       ( strb_en_ff ) & 
                                       ( clk_div_count == strb_start[i] ) ? ~strb_bus_ff[i]  : strb_bus_ff[i];
                end
                else begin // pulse strobe
                    strb_cont_ff[i] <= ( clk_div_count == strb_start[i] ) ? 1'b1 : 
                                       ( clk_div_count == strb_end  [i] ) ? 1'b0 : strb_cont_ff[i];
                    strb_bus_ff [i] <= ( force_reload | force_active    ) ? force_out[BUS_DATA_BITS+BUS_ADDR_BITS+i] :  
                                       ( ~strb_en_ff                    ) ? 1'b0 :
                                       ( clk_div_count == strb_start[i] ) ? 1'b1 : 
                                       ( clk_div_count == strb_end  [i] ) ? 1'b0 : strb_bus_ff[i];
                end
                strb_en_ff <= ( ~state_run )                     ? 1'b0 :
                              ( timeout_next_cycle & ~next_NOP ) ? 1'b1 : 
                              ( timer_tick_cont                ) ? 1'b0 : strb_en_ff;
            end
            else begin
                strb_bus_ff[i] <= ( force_reload | force_active ) ? force_out[BUS_DATA_BITS+BUS_ADDR_BITS+i] : 1'b0; 
            end
        end
        assign strb_start[i] = strb_delay[CLK_DIV_BITS*(2*i+1)-1 -: CLK_DIV_BITS];
        assign strb_end  [i] = strb_delay[CLK_DIV_BITS*(2*i+2)-1 -: CLK_DIV_BITS];
        assign strb_cont [i] = strb_cont_ff[i];
        assign strb      [i] = strb_bus_ff [i];
                
    end

    //////////////////////////////////////////////////////////////////////////////////
    // bus output buffer to minimize skew @ clk_bus
    // deleted since not really needed, not sure if IOB works and saves one cycle same on strb
    
    assign bus_data   = bus_data_buf[BUS_SYNC-1];
    assign bus_addr_0 = bus_addr_buf[BUS_SYNC-1][BUS_ADDR_BITS-1:0]; 
    if ( BUS_ADDR_1_USE == "ADDR0" ) begin              // "ADDR0" = same as bus_addr_0 = data bits [23:16]
        assign bus_addr_1 = bus_addr_buf[BUS_SYNC-1][BUS_ADDR_BITS-1:0];
    end
    else if ( BUS_ADDR_1_USE == "DATA_HIGH" ) begin     // "DATA_HIGH" = use data bits [31:24]
        assign bus_addr_1 = bus_addr_buf[BUS_SYNC-1][BUS_ADDR_BITS*2-1 -: BUS_ADDR_BITS];
    end
    else begin                                          // default: "ZERO" = set all to 0
        assign bus_addr_1 = {BUS_ADDR_BITS{1'b0}};
    end
    
    /* bus data
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
    // bus strobe output buffer @ clk_bus

    (* IOB = "TRUE" *)
    reg bus_strb_ff [0 : NUM_STRB-1];
    for (genvar i = 0; i < NUM_STRB; i = i + 1)
    begin : GEN_STRB_BUF

        always @ ( posedge clk_bus ) begin
            bus_strb_ff[i] = strb_bus_ff[i];
        end
        assign bus_strb[i] = bus_strb_ff[i];
        
    end
    */

    for (genvar i = 0; i < NUM_STRB; i = i + 1)
    begin : GEN_STRB_BUF
        assign bus_strb[i] = strb_bus_ff[i];
    end
        
    //////////////////////////////////////////////////////////////////////////////////
    // irq toogle bits @ clk_bus
    
    reg irq_bit_old = 1'b0;
    wire irq_timer_bit;
    wire irq_timer;
    reg end_delayed     = 1'b0; // end_w delayed until end state
    if ( IRQ_FREQ_BITS == 0 ) begin
        // disabled
        assign irq_timer_bit = 1'b0;
        assign irq_timer     = 1'b0; 
    end
    else begin 
        // enabled
        // for IRQ_FREQ_BITS = 21 this should give irq frequency of 12-24Hz for all clk_div > 1.
        // note: this assumes CLK_DIV_BITS = 8. will give > frequencies for wider clk_div and error for smaller.
        assign irq_timer_bit = clk_div[7] ? timer[IRQ_FREQ_BITS-6] : // clk_div = 128-255: 24-12Hz
                               clk_div[6] ? timer[IRQ_FREQ_BITS-5] : // clk_div =  64-127: 24-12Hz
                               clk_div[5] ? timer[IRQ_FREQ_BITS-4] : // clk_div =  32- 63: 24-12Hz
                               clk_div[4] ? timer[IRQ_FREQ_BITS-3] : // clk_div =  16- 31: 24-12Hz
                               clk_div[3] ? timer[IRQ_FREQ_BITS-2] : // clk_div =   8- 15: 24-13Hz 
                               clk_div[2] ? timer[IRQ_FREQ_BITS-1] : // clk_div =   4-  7: 24-14Hz
                                            timer[IRQ_FREQ_BITS-0] ; // clk_div =   2-  3: 24-16Hz
        assign irq_timer = irq_freq_en & (irq_timer_bit ^ irq_bit_old) & (~(end_w | end_delayed | state_end));
    end        
    wire irq_data  = irq_data_en & (timeout_next_cycle & next_IRQ & next_valid); 
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) begin
            state_irq   <= 2'b00;
            irq_bit_old <= 1'b0; 
        end
        else begin
            state_irq[0] <= irq_timer ? ~state_irq[0] : state_irq[0];
            state_irq[1] <= irq_data  ? ~state_irq[1] : state_irq[1];
            irq_bit_old  <= irq_timer ? irq_timer_bit : irq_bit_old;
        end
    end
    
    //////////////////////////////////////////////////////////////////////////////////
    // board time, samples and cycles
    // update on irq or end
    // timer and samples update fast, so we map them on board_... registers fewer time.
    // cycle can be mapped directly.
    
    reg [REG_BITS-1:0] board_time_ff    = 0;
    reg [REG_BITS-1:0] board_samples_ff = 0;
    //reg [REG_BITS-1:0] board_cycles_ff = 0;
    reg end_pulse = 1'b0;
    // timeout_next_cycle = ( (next_valid && (timer == next_time)) ) & timer_tick;
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) begin
            board_time_ff    <= 0;
            board_samples_ff <= 0;
            cycles           <= 0;
            end_pulse        <= 1'b0;
        end
        else begin
            board_time_ff    <= ( irq_timer | end_pulse ) ? timer      : board_time_ff;
            board_samples_ff <= ( irq_timer | end_pulse ) ? samples    : board_samples_ff;
            cycles           <=               end_pulse   ? cycles + 1 : cycles;
            end_pulse        <= end_of_cycle_w & timeout;      
        end
    end
    assign board_time    = board_time_ff;
    assign board_samples = board_samples_ff;
    assign board_cycles  = cycles;

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
    
    //////////////////////////////////////////////////////////////////////////////////
    // error detection
    
    // input error detection
    // error if timeout but input not valid unless at end state
    // requires reset to reset
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) error_in_ff <= 1'b0;
        else error_in_ff <= ( state_run & timeout & (~in_valid) & (~end_w) ) ? 1'b1 : error_in_ff;
    end
    
    // timer error detection
    // error if next time is smaller or equal actual time
    // requires reset
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) error_time_ff <= 1'b0;
        //else error_time_ff <= ( run & in_valid & in_ready & (~restart_w) & ( next_time2 <= next_time ) ) ? 1'b1 : error_time_ff;
        //else error_time_ff <= ( state_run & next_valid & next_valid2 & (~end_of_cycle_w) & ( next_time2 <= next_time ) ) | error_time_ff;
        //else error_time_ff <= 1'b0;
        else error_time_ff <= ( next_reload_ff & last_valid & (~first_sample) & (~end_delayed) & ( next_time <= last_time ) ) | error_time_ff;
    end
    
    // output error detection
    // error if timeout but output not ready
    // requires reset to reset
    // TODO: enable with a bit. sometimes we might not care.
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) error_out_ff <= 1'b0;
        else error_out_ff <= ( timeout & (~out_ready) ) ? 1'b1 : error_out_ff;
    end
    
    //////////////////////////////////////////////////////////////////////////////////
    // finite state machine @ clk_bus
    
    // run_en positive edge detector
    reg run_en_ff;
    always @ (posedge clk_bus) begin
        run_en_ff <= run_en;
    end
    wire run_en_edge = ({run_en_ff,run_en} == 2'b01);
    
    // stop trigger detector. set by stop_trg_pulse, reset by trg_tick.
    // update: reset by timer_tick
    reg stop_trg_ff;
    always @ (posedge clk_bus) begin
        stop_trg_ff <= state_run & (~state_wait) & (stop_trg_pulse | stop_trg_ff) & ~timer_tick; //~trg_tick;
    end
    wire stop_trg_detected = stop_trg_ff | stop_trg_pulse;

    // end state is delayed from last timeout until end state after next timer_tick
    // this is needed that last data is properly output on bus before going into end state.
    // when restarting this delay is not needed since its the 0 time delay.
    always @ (posedge clk_bus) begin
        //end_delayed <= timer_tick ? end_w : end_delayed;
        if ( timeout_next_cycle & end_w ) end_delayed <= 1'b1;
        else if ( state_end )             end_delayed <= 1'b0;
        else                              end_delayed <= end_delayed;
    end

    // TODO: add auto-sync here, i.e. generate sync_in & wait time or wait for sync_in
    // TODO: state and state_ bits have same information. remove one of them!
    //       individual bits would be more efficient I think but state is more comprehensive.
    //       state_run might have a higher fan-out and could be registered but assigned directly here to save one cycle.
    localparam integer STATE_BITS  = 3;
    localparam integer STATE_RESET = 0;
    localparam integer STATE_READY = 1;
    localparam integer STATE_START = 2;
    localparam integer STATE_RUN   = 3;
    localparam integer STATE_WAIT  = 4;
    localparam integer STATE_END   = 5;
    localparam integer STATE_ERROR = 6;
    reg [STATE_BITS-1:0] state = STATE_RESET;    
    always @ (posedge clk_bus) begin
        if ( reset_bus_n == 1'b0 ) begin // hardware or software reset
            state <= STATE_RESET;
            state_ready   <= 1'b0;
            state_run     <= 1'b0;
            state_end     <= 1'b0;
            state_wait    <= 1'b0;
            state_restart <= 1'b0;
        end
        else begin
            case ( state )
                STATE_RESET: begin // wait for svr_ready & first data
                    state <= (state_error_w         ) ? STATE_ERROR : 
                             (svr_ready & next_valid) ? STATE_READY : STATE_RESET;
                    state_ready   <= 1'b0;
                    state_run     <= 1'b0;
                    state_end     <= 1'b0;
                    state_wait    <= 1'b0;
                    state_restart <= 1'b0;
                end
                STATE_READY: begin // wait for run_en bit
                    state <= (state_error_w                     ) ? STATE_ERROR : 
                             (run_en &  ( as_en | start_trg_en )) ? STATE_START : 
                             (run_en & ~( as_en | start_trg_en )) ? STATE_RUN   : 
                                                                    STATE_READY ;
                    state_ready   <= 1'b1;
                    state_run     <= 1'b0;
                    state_end     <= 1'b0;
                    state_wait    <= 1'b0;
                    state_restart <= state_restart;
                end
                STATE_START: begin // wait for start trigger or as_start signal
                    state <= ( state_error_w                                                       ) ? STATE_ERROR :
                             ( run_en & (( as_en & as_start ) | ( start_trg_en & start_trg_pulse ))) ? STATE_RUN   :
                                                                                                       STATE_START ;
                    state_ready <= 1'b1;
                    state_run   <= 1'b0; // TODO: would be good to have this active already for irq_FREQ
                    state_end   <= 1'b0;
                    state_wait  <= 1'b1;
                    state_restart <= state_restart;
                end
                STATE_WAIT: begin // wait for restart trigger or run_en positive edge
                    state <= (state_error_w                                              ) ? STATE_ERROR :
                             ((run_en & restart_trg_en & restart_trg_pulse) | run_en_edge) ? STATE_RUN   :
                                                                                             STATE_WAIT  ;
                    state_ready <= 1'b1;
                    state_run   <= 1'b1;
                    state_end   <= 1'b0;
                    state_wait  <= 1'b1;
                    state_restart <= state_restart;
                end
                STATE_RUN: begin 
                    // running state: wait until end, stop trigger or stop data bit or ~run_en
                    //                STATE_WAIT is entered only at next trg_tick or timer_tick
                    state <= ( state_error_w                                                                      ) ? STATE_ERROR :
                             ( (~run_en) | (stop_trg_en & stop_trg_detected & timer_tick) | (next_STOP & timeout) ) ? STATE_WAIT  :
                             ( restart_w & timeout & ( as_en | start_trg_en )                                     ) ? STATE_START : 
                             ( end_delayed & timer_tick                                                           ) ? STATE_END   : 
                                                                                                                      STATE_RUN   ;
                    state_ready   <= 1'b1;
                    state_run     <= 1'b1;
                    state_end     <= 1'b0;
                    state_wait    <= 1'b0;
                    state_restart <= ((~state_error_w) & run_en & restart_w & timeout) ? ~state_restart : state_restart;
                end
                STATE_END: begin // end state: requires software reset
                    state <= STATE_END;
                    state_ready   <= 1'b1;
                    state_run     <= 1'b0;
                    state_end     <= 1'b1;
                    state_wait    <= 1'b0;
                    state_restart <= state_restart;
                end
                default: begin // = STATE_ERROR: an error occurred: requires reset
                    state         <= STATE_ERROR;
                    state_ready   <= 1'b0;
                    state_run     <= 1'b0;
                    state_end     <= 1'b0;    
                    state_wait    <= 1'b0;
                    state_restart <= state_restart;
                end
            endcase
        end
    end 

    assign status_bits = {state_irq,error_time_ff,error_out_ff,error_in_ff,state_restart,state_wait,state_end,state_run,state_ready};    
    assign status_update = 1'b0;
    assign as_run = as_en && ( state == STATE_START );    

    //////////////////////////////////////////////////////////////////////////////////
    // assign status bits

    /* end_pulse pulses right after last timeout.
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
            //state_wait        <= state_ready & (~state_end) & state_run & (~run) & ( timer_tick | state_wait );
            state_wait        <= state_ready & (~state_end) & state_run & (~run);
            end_next_cycle    <= state_run & (~state_wait) & ( samples == num_samples ) & timer_tick & (~restart_w);
            //state_restart     <= state_run & (~state_wait) & ( samples == num_samples ) & timer_tick & restart_en;
            end_pulse         <= state_run & (~state_wait) & ( samples == (num_samples-1) ) & timeout;
            state_end         <= end_next_cycle | state_end;
        end
    end

    assign status_bits = {state_irq,error_time_ff,error_out_ff,error_in_ff,state_restart,state_wait,state_end,state_run,state_ready};    
    assign status_update = 1'b0;
    */
    
endmodule
