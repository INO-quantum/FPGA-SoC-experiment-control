`timescale 1 ns / 1 ps

//////////////////////////////////////////////////////////////////////////////////
// dio24 module, created 2019, revised 02-03/2020 by Andi
// main module for dio24 experiment control
// parameters:
// - STREAM_DATA_WIDTH = AXI stream data width (any width allowed)
// - BITS_PER_SAMPLE = bits per sample within AXI stream. must be 64 or 96.
// - AXI_DATA_WIDTH = AXI Lite slave bus width (must be 32)
// - AXI_ADDR_WIDTH = AXI Lite address width. see dio24_AXI_slave.v
// - FIFO_RESET_DELAY = delay for FIFO reset. >= 4 see dio24_reset.v
// - FIFO_RESET_CYCLES = reset cycles for FIFO reset. >=5 see dio24_reset.v
// - NUM_BUTTONS = number of buttons (must be 2)
// - NUM_LEDS = number of LEDs (must be 2)
// - TIME_BITS = number of bits for time (must be 32)
// - TIME_START = LSB index of first time bit (typically 0)
// - DATA_BITS = number of bits for data without time (must be 32)
// - DATA_START_64 = LSB index of first data bit with 64bits/sample (typically 32, i.e. right after time)
// - DATA_START_96_0 = LSB index of first data bit, 96bits/sample, board 0 (typically 32, i.e. right after time)
// - DATA_START_96_1 = LSB index of first data bit, 96bits/sample, board 0 (typically 64, i.e. right after board 0 data)
// - BUS_DATA_BITS = number of data bits (typically 16)
// - BUS_ADDR_BITS = number of address bits (typically 7)
// - BIT_NOP = 0-based index of bit signalling no-operation in data bits (starting at DATA_START)
// - BIT_IRQ = 0-based index of bit signalling irq_FPGA (after TIME_BITS)
// - BIT_NUM = 0-based index of bit signalling num_samples in data (starting at DATA_START)
// - CLK_DIV = clock divider applied to generate output frequency. must be >=4.
// - STRB_DELAY = slow clock cycles until bus_strb is set to high after timeout. >=0
// - STRB_LEN = slow clock cycles with bus_strb high after timeout and STRB_DELAY. 
//              1 <= STRB_LEN <= (CLK_DIV - STRB_DELAY - 2) 
// - SYNC = number of synchronization stages. use 2-3
// - TRG_DELAY_IN = cycles after run & strg_start until execution starts with trg_start_en. must be >=0.
// - TRG_DELAY_OUT = cycles after run bit until trg_out asserted. must be 0 - (CLK_DIV-1).
//      master is sending trg_out with MAX_CYCLES - TRG_DELAY_OUT before execution starts
//      slave waits TRG_DELAY_IN after trg_start before execution starts
// - IRQ_FREQ = irq_FPGA frequency in Hz (approx) assuming clk_slow/CLK_DIV = 1MHz
// - TX/RX_FIFO_DEPTH = number of samples of TX/RX STREAM_DATA_WIDTH bits in FIFO, power of 2
// common clock and reset:
// - clk_slow = slow data/sample clock for dio24_timing module
// - clk_fast = fast system clock for all AXI interfaces
// - reset_n = common active-low reset
// FPGA board buttons and RGB LEDs
// - buttons_in = buttons input signal
// - rgb_led0_out = first RGB LED signal 
// - rgb_led1_out = second RGB LED signal
// buffer board control and status LEDs
// - bus_enable_n = bus enable signal
// - LED_ready = status LED green "Ready"
// - LED_error = status LED red "Error" 
// buffer board start/stop/out trigger
// - trg_start = start trigger input
// - trg_stop = stop trigger input
// - trg_out = trigger output
// buffer board external clock control
// - clk_int_locked = internal clock PLL is locked  
// - clk_ext_locked = external clock PLL is locked  
// - clk_ext_sel = switch between internal (0) and external clock (1)
// rack data bus output
// - bus_data = data output of DATA_OUT_WIDTH bits
// - bus_addr = address output of ADDR_OUT_WIDTH bits
// - bus_strobe = strobe output 
// irq I/O
// - irq_TX/RX = input of DMA TX/RX irqs. only used by timing_test module.
// - irq_FPGA = high when error or num_samples reached, requires reset
// AXI Lite Slave Bus Interface S00_AXI
// ... see dio24_AXI_slave
// AXI stream data input (from DMA stream master)
// - in_data = stream data of STREAM_DATA_WIDTH bits
// - in_last = stream data tlast signal
// - in_ready = module is ready for new data
// - in_valid = input data is valid
// - in_keep = input tkeep signal of STREAM_DATA_WIDTH/8 bits (all must be 1)
// AXI stream data output (to DMA stream slave)
// - out_data = stream data of STREAM_DATA_WIDTH bits
// - out_last = stream data tlast signal
// - out_ready = external IP is ready for new data
// - out_valid = output data is valid
// - out_keep = output tkeep signal of STREAM_DATA_WIDTH/8 bits (all set to 1)
// last change 14/04/2021 by Andi
//////////////////////////////////////////////////////////////////////////////////

	module dio24 #
	(
	    // AXI stream bus
        parameter integer STREAM_DATA_WIDTH  = 128,      // no limits
        parameter integer BITS_PER_SAMPLE  = 96,        // 64 (2 ports) or 96 (4 ports)
	
		// AXI Lite slave bus
        parameter integer AXI_DATA_WIDTH = 32,      // must be 32
        parameter integer AXI_ADDR_WIDTH = 7,       // 7: 2^7/4 = 32 registers
        
        // DMA buffer size in samples
        parameter integer DMA_BUF_SIZE = 4032/12,

        // reset settings        
        parameter integer FIFO_RESET_DELAY = 10,    // >= 4
        parameter integer FIFO_RESET_CYCLES = 10,   // >= 5
        
        // LEDs and buttons 
        parameter integer NUM_BUTTONS = 2,          // must be 2
        parameter integer NUM_LEDS = 4,             // must be 4
        // bits used for blinking leds ON-time: 1=50%, 2=25%, 3=12.5%, 4=6.25%
        parameter integer LED_BLINK_ON = 3,
        // bits used for blinking leds
        parameter LED_SLOW = 26,              // blink slow
        parameter LED_FAST = 24,              // blink fast (1 <= LED_FAST < LED_SLOW)
        // bits used for PWM dimming of leds. 0 = no dimming.
        parameter LED_DIM_LOW = 8,            // dim level low (< LED_SLOW)
        parameter LED_DIM_HIGH = 6,           // dim level high (< LED_SLOW)
        parameter LED_BRIGHT_LOW = 1,         // bright level low (< LED_SLOW)
        parameter LED_BRIGHT_HIGH = 1,        // bright level high (1 <= LED_BRIGHT_HIGH < LED_SLOW)
        
        // data and time bits
        parameter integer TIME_BITS             = AXI_DATA_WIDTH,   // must be 32
        parameter integer TIME_START            = 0,                // typically 0
        parameter integer DATA_BITS             = AXI_DATA_WIDTH,   // must be 32
        parameter integer DATA_START_64         = 32,               // typically 32
        parameter integer DATA_START_96_0       = 32,               // typically 32
        parameter integer DATA_START_96_1       = 64,               // typically 64
        
        // auto-sync
        parameter integer AUTO_SYNC_PULSE_LENGTH = 3,               // 2 = 40ns @ 50MHz 
        parameter integer AUTO_SYNC_PULSE_WAIT   = 5,               // 3 = 60ns @ 50MHz, wait time after pulse
        parameter integer AUTO_SYNC_MAX_PULSES   = 2,               // 2 
        parameter integer AUTO_SYNC_TIME_BITS    = 8,               // 8
        parameter integer AUTO_SYNC_DELAY_BITS   = 10,               // 10
        parameter integer AUTO_SYNC_PHASE_BITS   = 12,               // 12     

        // bus data and address bits without strobe bit
        parameter integer BUS_DATA_BITS = 16,       // 16
        parameter integer BUS_ADDR_BITS = 7,        // 7
        
        // special data bits
        parameter integer BIT_NOP = 31,             // 31
        parameter integer BIT_IRQ = 30,             // 30
        //parameter integer BIT_NUM = 29,             // 29
 
        // dio24_timing parameters
        parameter integer CLK_DIV = 50,             // must be >= 4
        parameter integer STRB_DELAY = 12,
        parameter integer STRB_LEN = 25, 
        parameter integer SYNC = 2,                 // 2-3

        // irq_FPGA frequency in Hz @ clock/CLK_DIV = 1MHz
        parameter integer IRQ_FREQ = 16,

        // TX and RX FIFO
        parameter integer TX_FIFO_DEPTH = 8192,
        parameter integer RX_FIFO_DEPTH = 8192
	)
	(
        // common clock and reset
        input wire  clock_slow,
        input wire  clock_slow_PS,
        input wire  clock_fast,
        input wire  reset_n,                        // @ clk_fast
        output wire reset_active_n,                 // reset output @ clk_fast
        
        // FPGA board buttons and RGB LEDs
        input wire [NUM_BUTTONS-1:0] buttons_in,    // async
        output wire [NUM_LEDS-1:0] leds_out,        // @ clk_fast
        output wire [1:0] led_blue,                 // external clock {used,locked}
        
        // buffer board start/stop/out trigger
        input wire trg_start,                       // async
        input wire trg_stop,                        // async
        output wire trg_out,                        // @ clk_slow

        // buffer board external clock control @ clk_fast
        input wire clk_int_locked,  
        input wire clk_ext_locked,
        output wire clk_ext_sel,

        // rack data bus output @ clk_slow
        output wire bus_enable_n,
        output wire [BUS_DATA_BITS-1:0] bus_data,
        output wire [BUS_ADDR_BITS-1:0] bus_addr,
        output wire bus_strb,
        
        // irq I/O @ clk_fast
        input wire irq_TX,
        input wire irq_RX,
        output wire irq_FPGA,
        
        // auto-sync
        output wire sync_out,       // trigger pulse
        output wire sync_en,        // FET
        output wire sync_mon,       // monitor for debugging
        input wire sync_in,         // detector input
        
        // dynamic phase shift of external clock input and detector clock 
        input wire ps_done_ext,
        output wire ps_en_ext,
        output wire ps_inc_ext,
        input wire ps_done_det,
        output wire ps_en_det,
        output wire ps_inc_det,

		// AXI Lite Slave Bus Interface S00_AXI @ clk_fast
		//input wire  s00_axi_aclk,
        //input wire  s00_axi_aresetn,
		input wire [AXI_ADDR_WIDTH-1 : 0] s00_axi_awaddr,
		input wire [2 : 0] s00_axi_awprot,
		input wire  s00_axi_awvalid,
		output wire  s00_axi_awready,
		input wire [AXI_DATA_WIDTH-1 : 0] s00_axi_wdata,
		input wire [(AXI_DATA_WIDTH/8)-1 : 0] s00_axi_wstrb,
		input wire  s00_axi_wvalid,
		output wire  s00_axi_wready,
		output wire [1 : 0] s00_axi_bresp,
		output wire  s00_axi_bvalid,
		input wire  s00_axi_bready,
		input wire [AXI_ADDR_WIDTH-1 : 0] s00_axi_araddr,
		input wire [2 : 0] s00_axi_arprot,
		input wire  s00_axi_arvalid,
		output wire  s00_axi_arready,
		output wire [AXI_DATA_WIDTH-1 : 0] s00_axi_rdata,
		output wire [1 : 0] s00_axi_rresp,
		output wire  s00_axi_rvalid,
		input wire  s00_axi_rready,

		// AXI stream data input (from DMA stream master @ clk_fast)
		input wire [STREAM_DATA_WIDTH-1 : 0] in_data,
        input wire  in_last,
		output wire  in_ready,
		input wire  in_valid,
		input wire [(STREAM_DATA_WIDTH/8)-1 : 0] in_keep, // disabled if USE_TKEEP != "TRUE"

		// AXI stream data output (to DMA stream slave @ clk_fast)
		output wire [STREAM_DATA_WIDTH-1 : 0] out_data,
		output wire  out_last,
		input wire  out_ready,
		output wire  out_valid,
		output wire [(STREAM_DATA_WIDTH/8)-1 : 0] out_keep

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

    // buttons and LEDs settings
    localparam integer BTN_SYNC = 2;                // button clock sychronization. 0 = none.  
    localparam integer BTN_DEB_BITS = 10;           // button debounce counter bits
    
    // number of control and status registers 
    localparam integer NUM_CTRL = 5;                // number of control registers (must match AXI slave)
    localparam integer NUM_STATUS = 6;              // number of status registers (must match AXI slave)
    
    // auto-reset register and bit
    localparam integer REG_CTRL = 0;                // index of control register 
    localparam integer REG_CTRL_RESET = 0;          // index of reset bit in control register  
    
    // index of ctrl_test register
    localparam integer REG_TEST = 1;

    // index of num_samples register
    localparam integer REG_NUM_SAMPLES = 2;
    
    // index of sync_delay and sync phase register
    localparam integer REG_SYNC_DELAY = 3;
    localparam integer REG_SYNC_PHASE = 4;
    
    // trigger settings
    localparam integer TRG_SYNC = 2;                  // number of trigger synchronization cycles (>=2)
    
    // control register bits
    localparam integer CTRL_RESET           = 0;       // manual reset (active high), auto-reset after 1 cycle
    localparam integer CTRL_READY           = 1;       // ready bit set by device open/close to indicate server startup
    localparam integer CTRL_RUN             = 2;       // run bit
    // 3 = end bit in status
    localparam integer CTRL_RESTART_EN      = 4;       // restart enable bit
    localparam integer CTRL_AUTO_SYNC_EN    = 5;       // auto-sync enable bit
    localparam integer CTRL_AUTO_SYNC_PRIM  = 6;       // auto-sync primary board = generate pulse & start timer, if false wait only for pulse
    localparam integer CTRL_AUTO_SYNC_FET   = 7;       // auto-sync reflect pulse
    // 7 = phase shift active
    localparam integer CTRL_BPS96           = 8;       // if 1 data format = 96bits per samples
    localparam integer CTRL_BPS96_BRD_1     = 9;       // if CTRL_BPS96: 0 = board 0, 1=board 1 i.e. use DATA_START_0/1
    localparam integer CTRL_CLK_EXT         = 10;       // 0 = internal clock, 1 = external clock
    // 11 = external clock locked
    // 12-18 = error bits in status
    // 19 = free 
    localparam integer CTRL_IRQ_EN          = 20;      // 1 = enable all irq output
    localparam integer CTRL_IRQ_END_EN      = 21;      // 1 = enable irq output when in end state
    localparam integer CTRL_IRQ_RESTART_EN  = 22;      // 1 = enable irq output for each restart
    localparam integer CTRL_IRQ_FREQ_EN     = 23;      // 1 = enable irq with IRQ_FREQ frequency
    localparam integer CTRL_IRQ_DATA_EN     = 24;      // 1 = enable irq with BIT_IRQ
    // 27 = free
    localparam integer CTRL_TRG_START_EN    = 28;      // 1 = enable start trigger (positive edge)
    localparam integer CTRL_TRG_STOP_EN     = 29;      // 1 = enable stop trigger (not implemented)
    // 30-31 = buttons in status
        
    // control register assignments
    localparam integer CTRL_BITS            = 7;       // number of control bits for timing module
    wire [AXI_DATA_WIDTH-1:0] control;
    wire reset_sw       = control[CTRL_RESET];
    wire svr_ready      = control[CTRL_READY];
    wire run_en         = control[CTRL_RUN];
    wire restart_en     = control[CTRL_RESTART_EN];
    wire [4:0] irq_en   = {control[CTRL_IRQ_DATA_EN],control[CTRL_IRQ_FREQ_EN],control[CTRL_IRQ_RESTART_EN],control[CTRL_IRQ_END_EN],control[CTRL_IRQ_EN]};
    wire trg_start_en   = control[CTRL_TRG_START_EN];
    wire trg_stop_en    = control[CTRL_TRG_STOP_EN];
    wire [CTRL_BITS-1:0] ctrl_bits;

    // control bits for timing_test module
    localparam integer TEST_BITS            = 10;      // number of control bits for timing_test module
    localparam integer TEST_TX              = 0;       // TX enabled
    localparam integer TEST_RX              = 1;       // RX enabled
    localparam integer TEST_START_0         = 4;       // start timer:
    localparam integer TEST_START_1         = 5;       // 0 = run rising edge, 1 = first data, 2 = IRQ rising edge, 3 = IRQ falling edge
    localparam integer TEST_START_2         = 6;       // 4 = trg_start rising edge, 5 = trg_start falling edge, 6 = trg_stop rising edge, 7 = trg_stop falling edge
    localparam integer TEST_UPD_0           = 8;       // update board_time source:
    localparam integer TEST_UPD_1           = 9;       // 0 = run falling edge, 1 = data, 2 = IRQ rising edge, 3 = IRQ falling edge
    localparam integer TEST_UPD_2           = 10;      // 4 = trg_start rising edge, 5 = trg_start falling edge, 6 = trg_stop rising edge, 7 = trg_stop falling edge
    localparam integer TEST_IRQ_0           = 12;      // IRQ source: 
    localparam integer TEST_IRQ_1           = 13;      // 0 = none, 1 = irq_TX, 2 = irq_RX, 3 = irq FPGA toggle bit
    wire [AXI_DATA_WIDTH-1:0] ctrl_test;
    wire [TEST_BITS-1:0] test_bits;
    
    // status bits out of timing module
    localparam integer STATUS_BITS = 9;
    wire [STATUS_BITS-1:0] status_bits;
    
    // pulses bit corresponding to control register when was updated
    wire [NUM_CTRL-1:0] ctrl_update;
    
    // status register bits
    // general
    localparam integer STATUS_RESET      =  0;      // 1 = reset is active
    localparam integer STATUS_READY      =  1;      // 1 = ready = first data received and not finished
    localparam integer STATUS_RUN        =  2;      // 1 = running = status_run bit
    localparam integer STATUS_END        =  3;      // 1 = finished = num_samples generated without error
    localparam integer STATUS_RESTART    =  4;      // toggle bit on every restart
    // phase shift
    localparam integer STATUS_AUTO_SYNC  = 5;       // 1 = auto sync active
    localparam integer STATUS_AS_TIMEOUT = 6;       // 1 = auto sync timeout
    localparam integer STATUS_PS_ACTIVE  = 7;       // 1 = phase shift active
    // clock
    localparam integer STATUS_CLK_EXT        = 10;  // actual 0 = internal clock, 1 = external clock
    localparam integer STATUS_CLK_EXT_LOCKED = 11;  // external clock locked
    // error
    localparam integer STATUS_ERR_IN        = 12;   // input error
    localparam integer STATUS_ERR_OUT       = 13;   // output error
    localparam integer STATUS_ERR_TIME      = 14;   // time error
    localparam integer STATUS_ERR_LOCK      = 15;   // external lock lost
    localparam integer STATUS_ERR_TKEEP     = 16;   // in_keep signal error
    localparam integer STATUS_ERR_TKEEP2    = 17;   // in_keep_smpl signal error
    localparam integer STATUS_ERR_TKEEP3    = 18;   // out_keep_smpl signal error
    // irq
    localparam integer STATUS_IRQ_ERROR     = 20;  // irq error active
    localparam integer STATUS_IRQ_END       = 21;  // irq end active
    localparam integer STATUS_IRQ_RESTART   = 22;  // irq restart active
    localparam integer STATUS_IRQ_FREQ      = 23;  // irq from IRQ_FREQ or IRQ_DATA
    localparam integer STATUS_IRQ_DATA      = 24;  // irq from IRQ_FREQ or IRQ_DATA
    // trigger state
    localparam integer STATUS_TRG_START     = 28;   // start trigger input
    localparam integer STATUS_TRG_STOP      = 29;   // stop trigger input
    // buttons state
    localparam integer STATUS_BTN_0         = 30;   // button 0
    localparam integer STATUS_BTN_1         = 31;   // button 1
    
    // status bit assignments
    wire reset_n_fast;
    wire reset_n_slow;
    wire reset_FIFO;
    reg reset_active_ff;
    wire status_ready;
    wire status_run;
    wire status_end;
    wire status_restart;
    wire status_irq_freq;
    wire status_irq_data;
    wire error_in;
    wire error_out;
    wire error_time;
    wire error_lock;
    wire [2:0] error_keep; // in - smpl - out
    wire error = error_in | error_out | error_time | error_lock | error_keep[0] | error_keep[1] | error_keep[2];
    reg [4:0] irq_out_ff;
    wire [NUM_BUTTONS-1:0] btn_status;
    wire trg_start_f;
    wire trg_stop_f;
    wire as_active;
    wire as_timeout;
    //wire sync_in_s;
    wire ps_active;
    wire [AXI_DATA_WIDTH-1:0] status; // status register
    generate
      for (genvar i = 0; i < AXI_DATA_WIDTH; i = i + 1)
      begin:REG_STATUS
        case ( i )
          STATUS_RESET:             assign status[i] = reset_active_ff;
          STATUS_READY:             assign status[i] = status_ready;
          STATUS_RUN:               assign status[i] = status_run;
          STATUS_END:               assign status[i] = status_end;
          STATUS_RESTART:           assign status[i] = status_restart;
          //
          STATUS_AUTO_SYNC:         assign status[i] = as_active;
          STATUS_AS_TIMEOUT:        assign status[i] = as_timeout;
          STATUS_PS_ACTIVE:         assign status[i] = ps_active;
          // 
          STATUS_CLK_EXT:           assign status[i] = clk_ext_sel;
          STATUS_CLK_EXT_LOCKED:    assign status[i] = clk_ext_locked;
          //STATUS_CLK_INT_LOCKED:    assign status[i] = clk_int_locked;
          //
          STATUS_ERR_IN:            assign status[i] = error_in;
          STATUS_ERR_OUT:           assign status[i] = error_out;
          STATUS_ERR_TIME:          assign status[i] = error_time;
          STATUS_ERR_LOCK:          assign status[i] = error_lock;
          STATUS_ERR_TKEEP:         assign status[i] = error_keep[0];
          STATUS_ERR_TKEEP2:        assign status[i] = error_keep[1];
          STATUS_ERR_TKEEP3:        assign status[i] = error_keep[2];
          //
          STATUS_IRQ_ERROR:         assign status[i] = irq_out_ff[0];
          STATUS_IRQ_END:           assign status[i] = irq_out_ff[1];
          STATUS_IRQ_RESTART:       assign status[i] = irq_out_ff[2];
          STATUS_IRQ_FREQ:          assign status[i] = irq_out_ff[3];
          STATUS_IRQ_DATA:          assign status[i] = irq_out_ff[4];
          // 
          STATUS_TRG_START:         assign status[i] = trg_start_f;
          STATUS_TRG_STOP:          assign status[i] = trg_stop_f;
          //
          STATUS_BTN_0:             assign status[i] = btn_status[0];
          STATUS_BTN_1:             assign status[i] = btn_status[1];
          //
          default:                  assign status[i] = 1'b0;
        endcase
      end
    endgenerate

    /* positive edge detector for reset_n_fast
    reg reset_ff;
    wire reset_done = ( {reset_ff,reset_n_fast} == 1'b01 );
    always @ (posedge clock_fast) begin
        if ( (reset_n == 1'b0) || (reset_n_fast == 1'b0) ) begin
            reset_ff <= 1'b0;
            reset_active_ff <= 1'b1;
        end
        else begin
            reset_ff <= reset_n_fast;
            if ( reset_sw ) begin
                reset_active_ff <= 1'b1;
            end
            else if ( reset_done ) begin
                reset_active_ff <= 1'b0;
            end
            else begin
                reset_active_ff <= reset_active_ff;
            end
        end
    end
    assign reset_active_n = ~reset_active_ff;*/
    
    // reset_active_n is used for clock wizard 1 which generates slow clock
    // to reset the phase to 0 by software we use this to generate RESET_CYCLES of reset signal
    // but which is not depending on slow clock. 
    // this is different than using reset_done above which uses reset module.
    localparam integer RESET_CYCLES = 25;
    localparam RESET_BITS = clogb2(RESET_CYCLES);
    reg [RESET_BITS-1:0] reset_cnt;
    always @ ( posedge clock_fast ) begin
        if ( ( reset_n == 1'b0 ) || ( reset_sw ) ) begin
            reset_active_ff <= 1'b1;
            reset_cnt <= FIFO_RESET_CYCLES;
        end
        else if ( reset_active_ff ) begin
            reset_active_ff <= ( reset_cnt != 1 );
            reset_cnt <= reset_cnt - 1;
        end
        else begin
            reset_active_ff <= 1'b0;
            reset_cnt <= 0;
        end
    end
    assign reset_active_n = ~reset_active_ff;
    
    // combine reset sources and ensure reset is long enough for FIFOs
    // reset condition = hardware (active low), software (active high) and 
    // while internal PLL is not locked
    // note: reset_FIFO is not used for XPM FIFO but fast and slow resets. 
    dio24_reset # (
        .FIFO_RESET_DELAY(FIFO_RESET_DELAY),
        .FIFO_RESET_CYCLES(FIFO_RESET_CYCLES),
        .SYNC(SYNC)
    )
    reset
    (
        // clock and reset sources: hardware, software, PLL_locked
        .clock_fast(clock_fast),
        .clock_slow(clock_slow),
        .reset_n(reset_n),
        .reset_sw(reset_sw),
        .PLL_locked(1'b1),      // TODO: use clk_int_locked but should not cause reset, but only required for recovery!
        // reset output
        .reset_n_fast(reset_n_fast),
        .reset_n_slow(reset_n_slow),
        .reset_FIFO(reset_FIFO)
    );
    
    // AXI lite slave = register control
    wire [AXI_DATA_WIDTH-1:0] num_samples;
    wire [AXI_DATA_WIDTH-1:0] sync_delay;
    wire [AXI_DATA_WIDTH-1:0] sync_phase;
    wire [AXI_DATA_WIDTH-1:0] board_time;
    wire [AXI_DATA_WIDTH-1:0] board_samples;
    wire [AXI_DATA_WIDTH-1:0] board_time_ext;
    wire [AXI_DATA_WIDTH-1:0] board_samples_ext;
    wire [AXI_DATA_WIDTH - 1 : 0] sync_time;
	dio24_AXI_slave # (
		.C_S_AXI_DATA_WIDTH(AXI_DATA_WIDTH),
		.C_S_AXI_ADDR_WIDTH(AXI_ADDR_WIDTH),
		.NUM_CTRL(NUM_CTRL),
		.NUM_STATUS(NUM_STATUS),
		.REG_CTRL(REG_CTRL),
		.REG_CTRL_RESET(REG_CTRL_RESET)
	) dio24_AXI_inst (
		.S_AXI_ACLK(clock_fast),
		.S_AXI_ARESETN(reset_n),
		.S_AXI_AWADDR(s00_axi_awaddr),
		.S_AXI_AWPROT(s00_axi_awprot),
		.S_AXI_AWVALID(s00_axi_awvalid),
		.S_AXI_AWREADY(s00_axi_awready),
		.S_AXI_WDATA(s00_axi_wdata),
		.S_AXI_WSTRB(s00_axi_wstrb),
		.S_AXI_WVALID(s00_axi_wvalid),
		.S_AXI_WREADY(s00_axi_wready),
		.S_AXI_BRESP(s00_axi_bresp),
		.S_AXI_BVALID(s00_axi_bvalid),
		.S_AXI_BREADY(s00_axi_bready),
		.S_AXI_ARADDR(s00_axi_araddr),
		.S_AXI_ARPROT(s00_axi_arprot),
		.S_AXI_ARVALID(s00_axi_arvalid),
		.S_AXI_ARREADY(s00_axi_arready),
		.S_AXI_RDATA(s00_axi_rdata),
		.S_AXI_RRESP(s00_axi_rresp),
		.S_AXI_RVALID(s00_axi_rvalid),
		.S_AXI_RREADY(s00_axi_rready),
		.control(control),
		.ctrl_test(ctrl_test),
		.num_samples(num_samples),
		.sync_delay(sync_delay),
		.sync_phase(sync_phase),
		.status(status),
		.board_time(board_time),
        .board_samples(board_samples),
		.board_time_ext(board_time_ext),
        .board_samples_ext(board_samples_ext),
        .sync_time(sync_time),
		.ctrl_update(ctrl_update)
	);
	
	// convert DMA input data stream to 64/96bits per sample
	// TODO: dynamic switching control[CTRL_BPS96] and selection of board data control[CTRL_BPS96_BRD_1]
	wire [BITS_PER_SAMPLE - 1 : 0] in_data_smpl;
	wire [(BITS_PER_SAMPLE/8) - 1 : 0] in_keep_smpl;
	wire in_last_smpl;
	wire in_valid_smpl;
	wire in_ready_smpl;
	if (STREAM_DATA_WIDTH != BITS_PER_SAMPLE) begin : IN_CONV
	   stream_convert # (
	       .IN_BYTES(STREAM_DATA_WIDTH/8), // always 16 bytes
	       .OUT_BYTES(BITS_PER_SAMPLE/8) // 12 or 8 bytes
	   )
	   in_conv (
	       // clock and reset
	       .clock(clock_fast),
	       .reset_n(reset_active_n),
	       // tkeep error
	       .error_keep(error_keep[0]),
	       // data input
	       .in_data(in_data),
	       .in_last(in_last),
	       .in_keep(in_keep),
	       .in_valid(in_valid),
	       .in_ready(in_ready),
	       // data output
	       .out_data(in_data_smpl),
           .out_last(in_last_smpl),	 
           .out_keep(in_keep_smpl),
           .out_valid(in_valid_smpl),
           .out_ready(in_ready_smpl)
	   );
	end
	else begin
	   assign error_keep[0] = 1'b0;
	   assign in_data_smpl = in_data;
	   assign in_last_smpl = in_last;
	   assign in_keep_smpl = in_keep;
	   assign in_valid_smpl = in_valid;
	   assign in_ready = in_ready_smpl;
	end
	
	// in_keep_smpl must have all bits high
	reg error_keep_smpl = 1'b0;
	always @ ( posedge clock_fast ) begin
	   if ( reset_active_n == 1'b0 ) error_keep_smpl <= 1'b0;
	   else if ( in_valid_smpl & in_ready_smpl ) begin
	       error_keep_smpl <= ( in_keep_smpl != {(BITS_PER_SAMPLE/8){1'b1}}) ? 1'b1 : error_keep_smpl;
	   end
	   else begin
	       error_keep_smpl <= error_keep_smpl;
	   end
	end
	assign error_keep[1] = error_keep_smpl;

    // TX data stream: select time and data from samples
    wire [TIME_BITS + DATA_BITS - 1 : 0] in_data_TX;
    wire in_last_TX;
    wire in_valid_TX;
    wire in_ready_TX;
    wire [clogb2(BITS_PER_SAMPLE-DATA_BITS)-1:0] data_offset = control[CTRL_BPS96] ? (control[CTRL_BPS96_BRD_1] ? DATA_START_96_1 : DATA_START_96_0) : DATA_START_64;
   	if (BITS_PER_SAMPLE != (TIME_BITS + DATA_BITS)) begin
        assign in_data_TX = {in_data_smpl[data_offset + DATA_BITS -1 -: DATA_BITS],in_data_smpl[TIME_START + TIME_BITS -1 -: TIME_BITS]};
        assign in_last_TX = in_last_smpl;
        assign in_valid_TX = in_valid_smpl;
        assign in_ready_smpl = in_ready_TX;
    end
    else begin
        assign in_data_TX = in_data_smpl;
        assign in_last_TX = in_last_smpl;
        assign in_valid_TX = in_valid_smpl;
        assign in_ready_smpl = in_ready_TX;
    end
    
    // run bit at fast clock. used in status bits and as input to slow clock synchronizer
    // note: start trigger is done in timing module to accomodate TRG_DELAY_IN/OUT
    //       start/stop trigger was tested here modifying run signal into timing module.
    reg run_en_ff;
    //reg [1:0] trg_start_ff;
    always @ ( posedge clock_fast ) begin
        if ( reset_active_ff ) begin
            run_en_ff <= 1'b0;
            //trg_start_ff <= 2'b00;
        end
        /*else if ( trg_start_en ) begin
            run_en_ff <= (run_en & svr_ready) && (run_en_ff ? trg_start : (trg_start_ff == 1'b01));
            trg_start_ff <= {trg_start_ff[0],trg_start};
        end*/
        else begin
            run_en_ff <= run_en & svr_ready;
            //trg_start_ff <= 2'b00;
        end
    end
    
    // timing module = bus data generation and RX stream output
    wire [TIME_BITS + DATA_BITS - 1 : 0] out_data_RX;
    wire out_last_RX;
    wire out_valid_RX;
    wire out_ready_RX;
    wire ctrl_regs_reload = |ctrl_update;// timing_test module
    //wire ctrl_regs_reload = ctrl_update[REG_NUM_SAMPLES]|ctrl_update[REG_TRG_DELAY];// timing module    
    dio24_timing # (
        .STREAM_DATA_BITS(TIME_BITS + DATA_BITS + 1),
        .BUS_DATA_BITS(BUS_DATA_BITS),
        .BUS_ADDR_BITS(BUS_ADDR_BITS),
        .REG_BITS(AXI_DATA_WIDTH),
        .CTRL_BITS(CTRL_BITS),
        .TEST_BITS(TEST_BITS),
        .STATUS_BITS(STATUS_BITS),
        .TRG_DELAY_IN_BITS(AUTO_SYNC_DELAY_BITS),
        .TRG_DELAY_OUT_BITS(AUTO_SYNC_DELAY_BITS),
        //.TRG_DELAY_PHASE_BITS(AUTO_SYNC_PHASE_BITS),
        .BIT_NOP(BIT_NOP),
        .BIT_IRQ(BIT_IRQ),
        //.BIT_NUM(BIT_NUM),
        .CLK_DIV(CLK_DIV),
        .STRB_DELAY(STRB_DELAY),
        .STRB_LEN(STRB_LEN),
        .SYNC(SYNC),
        .IRQ_FREQ(IRQ_FREQ),
        .TX_FIFO_DEPTH(TX_FIFO_DEPTH),
        .RX_FIFO_DEPTH(RX_FIFO_DEPTH),
        .DMA_BUF_SIZE(DMA_BUF_SIZE)          // DMA buffer size in samples (only timing test)
    )
    timing (
        // FIFO reset
        .reset_FIFO(reset_FIFO),
        // fast clock and reset
        .clock_fast(clock_fast),
        .reset_n_fast(reset_active_n),
        // slow clock and reset
        .clock_slow(clock_slow),
        .reset_n_slow(reset_n_slow),
        // control bits @ clock_fast
        .ctrl_bits(ctrl_bits),
        .test_bits(test_bits),
        .num_samples(num_samples),
        .trg_delay(sync_delay),
        .ctrl_regs_reload(ctrl_regs_reload),
        // status bits and board time & samples @ clock_fast
        .status_bits(status_bits),
        .board_time(board_time),
        .board_samples(board_samples),
        .board_time_ext(board_time_ext),
        .board_samples_ext(board_samples_ext),
        .status_update(),   // not used
        // TX stream data input
        .in_data({in_last_TX,in_data_TX}),
        .in_valid(in_valid_TX),
        .in_ready(in_ready_TX),
        // RX stream data output
        .out_data({out_last_RX,out_data_RX}),
        .out_valid(out_valid_RX),
        .out_ready(out_ready_RX),
        // bus output
        .bus_data(bus_data),
        .bus_addr(bus_addr),
        .bus_strb(bus_strb),
        .bus_enable_n(bus_enable_n),
        // trigger out and input
        .trg_start(trg_start),
        .trg_stop(trg_stop), 
        .trg_out(trg_out),
        // IRQ inputs (used by timing_test)
        .irq_TX(irq_TX),
        .irq_RX(irq_RX)
    );
    assign ctrl_bits = {trg_stop_en,trg_start_en,irq_en[4:3],error_lock|error_keep[0]|error_keep[1]|error_keep[2],restart_en,run_en_ff};
    assign test_bits = {ctrl_test[TEST_IRQ_1],ctrl_test[TEST_IRQ_0],ctrl_test[TEST_UPD_2],ctrl_test[TEST_UPD_1],ctrl_test[TEST_UPD_0],ctrl_test[TEST_START_2],ctrl_test[TEST_START_1],ctrl_test[TEST_START_0],ctrl_test[TEST_RX],ctrl_test[TEST_TX]};
    assign {status_irq_data,status_irq_freq,error_time,error_out,error_in,status_restart,status_end,status_run,status_ready} = status_bits;
   
    // expand RX stream data output to 64/96bits per sample
    // TODO: either switch dynamically or directly send data without expanding?
    //       another idea would be to send data back into TX FIFO for fast in-buffer repeated waveforms.
    //       this way both buffers could be used for storage and we would have 16k samples.
	wire [BITS_PER_SAMPLE - 1 : 0] out_data_smpl;
    wire out_last_smpl;
    wire out_valid_smpl;
    wire out_ready_smpl;    
    if (BITS_PER_SAMPLE != (TIME_BITS + DATA_BITS)) begin
        assign out_data_smpl[DATA_START_96_0 + DATA_BITS -1 -: DATA_BITS] = out_data_RX[DATA_START_64 + DATA_BITS -1 -: DATA_BITS];
        assign out_data_smpl[TIME_START + TIME_BITS -1 -: TIME_BITS] = out_data_RX[TIME_START + TIME_BITS -1 -: TIME_BITS];
        // assign gaps in output stream with zeros
        localparam integer SEL_LS = ( DATA_START_96_0 > TIME_START ) ? TIME_START : DATA_START_96_0;
        localparam integer SEL_LE = ( DATA_START_96_0 > TIME_START ) ? TIME_START+TIME_BITS : DATA_START_96_0+DATA_BITS;
        localparam integer SEL_HS = ( DATA_START_96_0 > TIME_START ) ? DATA_START_96_0 : TIME_START;
        localparam integer SEL_HE = ( DATA_START_96_0 > TIME_START ) ? DATA_START_96_0+DATA_BITS : TIME_START+TIME_BITS;
        if ( SEL_LS > 0 ) begin
           assign out_data_smpl[SEL_LS - 1 : 0] = {SEL_LS{1'b0}};
        end
        if ( SEL_HS > SEL_LE ) begin
           assign out_data_smpl[SEL_HS - 1 : SEL_LE] = {(SEL_HS - SEL_LE){1'b0}};
        end
        if ( BITS_PER_SAMPLE > SEL_HE ) begin
           assign out_data_smpl[BITS_PER_SAMPLE - 1 : SEL_HE] = {(BITS_PER_SAMPLE - SEL_HE){1'b0}};
        end
        assign out_last_smpl = out_last_RX;
        assign out_valid_smpl = out_valid_RX;
        assign out_ready_RX = out_ready_smpl;
    end
    else begin
        assign out_data_smpl = out_data_RX;
        assign out_last_smpl = out_last_RX;
        assign out_valid_smpl = out_valid_RX;
        assign out_ready_RX = out_ready_smpl;
    end
    
	// convert 64/96bits per sample back into DMA output data stream
    if (STREAM_DATA_WIDTH != BITS_PER_SAMPLE) begin : OUT_CONV
       stream_convert # (
           .IN_BYTES(BITS_PER_SAMPLE/8),
           .OUT_BYTES(STREAM_DATA_WIDTH/8)
       )
       out_conv (
           // clock and reset
           .clock(clock_fast),
           .reset_n(reset_active_n),
           // error keep
           .error_keep(error_keep[2]),
           // data input
           .in_data(out_data_smpl),
           .in_last(out_last_smpl),
           .in_keep({(BITS_PER_SAMPLE/8){1'b1}}), // all BYTES are used
           .in_valid(out_valid_smpl),
           .in_ready(out_ready_smpl),
           // data output
           .out_data(out_data),
           .out_last(out_last),
           .out_keep(out_keep),
           .out_valid(out_valid),
           .out_ready(out_ready)
       );
    end
    else begin
       assign error_keep[2] = 1'b0;
       assign out_data = out_data_smpl;
       assign out_last = out_last_smpl;
       assign out_keep = {(BITS_PER_SAMPLE/8){1'b1}};
       assign out_valid = out_valid_smpl;
       assign out_ready_smpl = out_ready;
    end
    
    // button and LEDs
    localparam ON = 1'b1;
    localparam OFF = 1'b0;
    localparam BLINK = 1'b1;
    localparam CONT = 1'b0;
    localparam FAST = 1'b1;
    localparam SLOW = 1'b0;
    localparam BRIGHT = 1'b1;
    localparam DIM = 1'b0;
    localparam NORM = 1'b0;
    localparam INV = 1'b1;
    localparam LEDS_TEST_DEFAULT = 0;
    // {ext green ready,ext red error,board green ready,board red error} LEDs
    reg [NUM_LEDS - 1 : 0] leds_in;
    reg [NUM_LEDS - 1 : 0] leds_bright = {BRIGHT,BRIGHT,DIM,DIM}; // overall brightness level
    reg [NUM_LEDS - 1 : 0] leds_blink;
    reg [NUM_LEDS - 1 : 0] leds_high;
    reg [NUM_LEDS - 1 : 0] leds_inv;
    reg [3:0] leds_test = LEDS_TEST_DEFAULT;
    always @ ( posedge clock_fast ) begin
        if ( reset_active_ff ) begin // reset: red and green on
            leds_in <= {ON,ON,ON,ON};
            leds_blink <= {CONT,CONT,CONT,CONT};     
            leds_high <= {BRIGHT,BRIGHT,BRIGHT,BRIGHT};     
            leds_inv <= {btn_status,btn_status};     
        end
        else if ( svr_ready ) begin
            if ( status_ready ) begin
                if ( status_run ) begin // run: green LED bright/dim toggled after each restart
                    leds_in <= {ON,OFF,ON, OFF};
                    leds_blink <= {CONT,CONT,CONT,CONT};     
                    leds_high <= {~status_restart,DIM,~status_restart,DIM};     
                    leds_inv<= {btn_status,btn_status};     
                end
                else begin // ready: green blink fast
                    leds_in <= {ON,OFF,ON,OFF};
                    leds_blink <= {BLINK,CONT,BLINK,CONT};     
                    leds_high <= {FAST,BRIGHT,FAST,BRIGHT};     
                    leds_inv <= {btn_status,btn_status};     
                end
            end
            else if ( status_end ) begin // end: green blink slow
                leds_in <= {ON,OFF,ON,OFF};
                leds_blink <= {BLINK,CONT,BLINK,CONT};     
                leds_high <= {SLOW,DIM,SLOW,DIM};     
                leds_inv <= {btn_status,btn_status};     
            end
            else if ( error ) begin // error: red and green blink fast with 3:1 ratio out of phase 
                leds_in <= {ON,ON,ON,ON};
                leds_blink <= {BLINK,BLINK,BLINK,BLINK};     
                leds_high <= {FAST,FAST,FAST,FAST};     
                leds_inv <= {btn_status[1],~btn_status[0],btn_status[1],~btn_status[0]};     
            end
            else begin // waiting for first data: red and green
                leds_in <= {ON,ON,ON,ON};
                leds_blink <= {CONT,CONT,CONT,CONT};     
                leds_high <= {DIM,DIM,DIM,DIM};     
                leds_inv <= {btn_status,btn_status};     
            end
            leds_test <= LEDS_TEST_DEFAULT; // reset LEDs test to default
        end
        else begin // server not ready: LEDs test with buttons. initially LEDS_TEST_DEFAULT.
            case ( leds_test )
                0: begin // default
                    leds_test <= (btn_status == 2'b01) ? leds_test+1 : ( (btn_status == 2'b10) ? 9 : leds_test ); 
                    leds_in <= {ON,ON,ON,ON};
                    leds_blink <= {CONT,CONT,CONT,CONT};     
                    leds_high <= {DIM,DIM,DIM,DIM};     
                    leds_inv <= {NORM,NORM,NORM,NORM};
                end
                1: begin
                    leds_test <= (btn_status == 2'b01) ? leds_test+1 : ( (btn_status == 2'b10) ? leds_test-1 : leds_test ); 
                    leds_in <= {ON,ON,ON,ON};
                    leds_blink <= {CONT,CONT,CONT,CONT};     
                    leds_high <= {BRIGHT,BRIGHT,BRIGHT,BRIGHT};     
                    leds_inv <= {INV,INV,NORM,NORM};
                end
                2: begin
                    leds_test <= (btn_status == 2'b01) ? leds_test+1 : ( (btn_status == 2'b10) ? leds_test-1 : leds_test ); 
                    leds_in <= {ON,ON,ON,ON};
                    leds_blink <= {CONT,CONT,CONT,CONT};     
                    leds_high <= {BRIGHT,BRIGHT,BRIGHT,BRIGHT};     
                    leds_inv <= {NORM,NORM,INV,INV};
                end
                3: begin
                    leds_test <= (btn_status == 2'b01) ? leds_test+1 : ( (btn_status == 2'b10) ? leds_test-1 : leds_test ); 
                    leds_in <= {ON,ON,ON,ON};
                    leds_blink <= {CONT,CONT,CONT,CONT};     
                    leds_high <= {DIM,DIM,DIM,DIM};     
                    leds_inv <= {INV,INV,NORM,NORM};
                end
                4: begin
                    leds_test <= (btn_status == 2'b01) ? leds_test+1 : ( (btn_status == 2'b10) ? leds_test-1 : leds_test ); 
                    leds_in <= {ON,ON,ON,ON};
                    leds_blink <= {CONT,CONT,CONT,CONT};     
                    leds_high <= {DIM,DIM,DIM,DIM};     
                    leds_inv <= {NORM,NORM,INV,INV};
                end
                5: begin
                    leds_test <= (btn_status == 2'b01) ? leds_test+1 : ( (btn_status == 2'b10) ? leds_test-1 : leds_test ); 
                    leds_in <= {ON,ON,ON,ON};
                    leds_blink <= {BLINK,BLINK,BLINK,BLINK};     
                    leds_high <= {FAST,FAST,FAST,FAST};     
                    leds_inv <= {INV,INV,NORM,NORM};
                end
                6: begin
                    leds_test <= (btn_status == 2'b01) ? leds_test+1 : ( (btn_status == 2'b10) ? leds_test-1 : leds_test ); 
                    leds_in <= {ON,ON,ON,ON};
                    leds_blink <= {BLINK,BLINK,BLINK,BLINK};     
                    leds_high <= {FAST,FAST,FAST,FAST};     
                    leds_inv <= {NORM,NORM,INV,INV};
                end
                7: begin
                    leds_test <= (btn_status == 2'b01) ? leds_test+1 : ( (btn_status == 2'b10) ? leds_test-1 : leds_test ); 
                    leds_in <= {ON,ON,ON,ON};
                    leds_blink <= {BLINK,BLINK,BLINK,BLINK};     
                    leds_high <= {SLOW,SLOW,SLOW,SLOW};     
                    leds_inv <= {INV,INV,NORM,NORM};
                end
                8: begin
                    leds_test <= (btn_status == 2'b01) ? leds_test+1 : ( (btn_status == 2'b10) ? leds_test-1 : leds_test ); 
                    leds_in <= {ON,ON,ON,ON};
                    leds_blink <= {BLINK,BLINK,BLINK,BLINK};     
                    leds_high <= {SLOW,SLOW,SLOW,SLOW};     
                    leds_inv <= {NORM,NORM,INV,INV};
                end
                default: begin // all off
                    leds_test <= (btn_status == 2'b01) ? 0 : ( (btn_status == 2'b10) ? leds_test-1 : leds_test );
                    leds_in <= {OFF,OFF,OFF,OFF};
                    leds_blink <= {CONT,CONT,CONT,CONT};     
                    leds_high <= {BRIGHT,BRIGHT,BRIGHT,BRIGHT};     
                    leds_inv <= {NORM,NORM,NORM,NORM};
                end     
            endcase               
        end
    end
    
    dio24_leds_btn # (
      .NUM_BUTTONS(NUM_BUTTONS),
      .NUM_LEDS(NUM_LEDS),
      .BTN_SYNC(BTN_SYNC),  
      .BTN_DEB_BITS(BTN_DEB_BITS),
      .LED_BLINK_ON(LED_BLINK_ON),
      .LED_SLOW(LED_SLOW),
      .LED_FAST(LED_FAST),
      .LED_DIM_LOW(LED_DIM_LOW),
      .LED_DIM_HIGH(LED_DIM_HIGH),
      .LED_BRIGHT_LOW(LED_BRIGHT_LOW),
      .LED_BRIGHT_HIGH(LED_BRIGHT_HIGH)
    )
    leds_btn
    (
        // clock and reset
        .clk(clock_fast),
        .reset_n(reset_n_fast),
        // buttons
        .btn_in(buttons_in),
        .btn_status(btn_status),
        // LEDs
        .leds_in(leds_in),
        .leds_out(leds_out),
        .leds_bright(leds_bright),
        .leds_blink(leds_blink),
        .leds_high(leds_high),
        .leds_inv(leds_inv)
        );
        
    // IRQ on error, restart (toggle), end (positive edge) state or update (toggle)
    // reset with reset_n_fast or set irq_en = 0
    // note: even if disabled maintain edge detector of end state!
    //       otherwise on enabling will trigger irq when already in end state.
    reg [1:0] status_err_ff;    // positive edge detector of error
    reg [1:0] status_end_ff;    // positive edge detector of end state
    reg status_restart_ff;      // status_restart change detector
    reg status_irq_freq_ff;     // status_irq_freq change detector
    reg status_irq_data_ff;     // status_irq_data change detector
    always @ ( posedge clock_fast ) begin
        if ( reset_n_fast == 1'b0 ) begin
            irq_out_ff <= 0;
            status_err_ff <= 2'b00;
            status_end_ff <= 2'b00;
            status_restart_ff <= 1'b0;
            status_irq_freq_ff <= 1'b0;
            status_irq_data_ff <= 1'b0;
        end
        else begin
            irq_out_ff[0] <= irq_en[0]             & ( ( status_err_ff == 2'b01 )                | irq_out_ff[0] );
            irq_out_ff[1] <= irq_en[0] & irq_en[1] & ( ( status_end_ff == 2'b01 )                | irq_out_ff[1] );
            irq_out_ff[2] <= irq_en[0] & irq_en[2] & ( ( status_restart_ff != status_restart )   | irq_out_ff[2] );
            irq_out_ff[3] <= irq_en[0] & irq_en[3] & ( ( status_irq_freq_ff != status_irq_freq ) | irq_out_ff[3] );
            irq_out_ff[4] <= irq_en[0] & irq_en[4] & ( ( status_irq_data_ff != status_irq_data ) | irq_out_ff[4] );
            status_err_ff <= {status_err_ff[0],error};
            status_end_ff <= {status_end_ff[0],status_end};
            status_restart_ff <= status_restart;
            status_irq_freq_ff <= status_irq_freq;
            status_irq_data_ff <= status_irq_data;
        end
    end
    assign irq_FPGA = |irq_out_ff;
    
    // external trigger input synchronization to fast clock (for status bits)
    if ( TRG_SYNC > 0 ) begin
        (* ASYNC_REG = "TRUE" *)
        reg [TRG_SYNC-1 : 0] trg_start_sync;
        (* ASYNC_REG = "TRUE" *)
        reg [TRG_SYNC-1 : 0] trg_stop_sync;
        always @ ( posedge clock_fast ) begin
            if ( reset_n_fast == 1'b0 ) begin
                trg_start_sync <= 0;
                trg_stop_sync <= 0;
            end
            else begin
                trg_start_sync <= {trg_start_sync[TRG_SYNC-2:0],trg_start};
                trg_stop_sync <= {trg_stop_sync[TRG_SYNC-2:0],trg_stop};
            end
        end
        assign trg_start_f = trg_start_sync[TRG_SYNC-1];
        assign trg_stop_f = trg_stop_sync[TRG_SYNC-1];
    end
    else begin
        assign trg_start_f = trg_start;
        assign trg_stop_f = trg_stop;
    end
    
    // external clock selection
    // external clock is enabled only if internal end external clocks are locked and no error
    // and the clk_ext_sel bit is set
    // note: for clocking wizard sel=0: clk_in2, sel=1: clk_in1, ClockMUX is the other way round
    reg clk_ext_sel_ff = 1'b0;
    always @ (posedge clock_fast ) begin
        if ( reset_n_fast == 1'b0 ) begin
            clk_ext_sel_ff <= 1'b0;
        end
        else begin
            clk_ext_sel_ff <= clk_int_locked & clk_ext_locked & control[CTRL_CLK_EXT] & (~error);
        end
    end
    assign clk_ext_sel = clk_ext_sel_ff;
    
    // detect error_lock @ clock_fast
    // set when external clock selected and lock lost
    // reset by reset_n_fast
    reg error_lock_ff = 1'b0;
    always @ ( posedge clock_fast ) begin
        if ( reset_n_fast == 1'b0 ) begin
            error_lock_ff <= 1'b0;
        end 
        else begin
            error_lock_ff <= ( clk_ext_sel & (~clk_ext_locked) ) | error_lock_ff;
        end
    end
    assign error_lock = error_lock_ff;
        
    localparam integer LED_BLINK_BITS = 4;
    reg [LED_BLINK_BITS-1:0] led_blink = 0;
    always @ (posedge clock_fast) begin
        led_blink <= led_blink + 1;
    end 
    
    assign led_blue[0] = clk_ext_locked & (led_blink == 0);
    assign led_blue[1] = clk_ext_sel & (led_blink == 0);
    
    auto_sync # (
        // pulse length + wait time
        .PULSE_LENGTH(AUTO_SYNC_PULSE_LENGTH),
        .PULSE_WAIT(AUTO_SYNC_PULSE_WAIT),
        .PULSE_NUM_MAX(AUTO_SYNC_MAX_PULSES),
        // auto-sync time bits
        .TIME_BITS(AUTO_SYNC_TIME_BITS),     
        // phase shift bits
        .PHASE_BITS(AUTO_SYNC_PHASE_BITS),
        // delay bits
        .DELAY_BITS(AUTO_SYNC_DELAY_BITS)
    )
    as
    (
        // clock and reset
        .clock_IO(clock_fast),
        .clock_bus(clock_slow),
        .clock_det(clock_slow_PS),
        .reset_n_IO(reset_active_n),
        .reset_n_bus(reset_n_slow),
        
        // dynamic phase shift of external clock input and detector clock @ clock_fast
        .ps_done_ext(ps_done_ext),
        .ps_en_ext(ps_en_ext),
        .ps_inc_ext(ps_inc_ext),
        .ps_done_det(ps_done_det),
        .ps_en_det(ps_en_det),
        .ps_inc_det(ps_inc_det),
        
        // auto-sync input and outputs
        .sync_out(sync_out),        // @ clock_slow
        .sync_mon(sync_mon),        // @ clock_det
        .sync_in(sync_in),          // not synchronized
        
        // control bits @ clock_fast
        .clk_ext_locked(clk_ext_locked),
        .clk_int_locked(clk_int_locked),
        .as_en(control[CTRL_AUTO_SYNC_EN]),
        .as_prim(control[CTRL_AUTO_SYNC_PRIM]),
        .ps_start(ctrl_update[REG_SYNC_PHASE]),
        
        // status bits @ clock_fast
        .as_active(as_active),
        .as_timeout(as_timeout),
        .ps_active(ps_active),
        
        // measured round-trip time {t1_PS,,t0_PS,t1,t0} @ clock_fast
        .sync_time(sync_time),        

        // trigger delay
        .sync_delay(sync_delay[AUTO_SYNC_DELAY_BITS-1 : 0]),    // @ clock_fast
        .trg_out(), //trg_out),                                      // @ clock_det. TODO: @ clock

        // phase shift @ clock_fast
        .ps_phase(sync_phase[2*AUTO_SYNC_PHASE_BITS-1 : 0])
        );

    // auto-sync enable FET output. high = reflect pulse
    reg sync_en_ff;
    always @ ( posedge clock_fast ) begin
        sync_en_ff <= control[CTRL_AUTO_SYNC_EN] & control[CTRL_AUTO_SYNC_FET];
    end
    assign sync_en = sync_en_ff;
    
endmodule
