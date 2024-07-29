`timescale 1 ns / 1 ps

//////////////////////////////////////////////////////////////////////////////////
// dio24 module, created 2019, revised 02-03/2020 by Andi
// main module for dio24 experiment control
// parameters:
// - STREAM_DATA_WIDTH = AXI stream data width (any width allowed)
// - BITS_PER_SAMPLE = bits per sample within AXI stream. must be 64 or 96.
// - AXI_DATA_WIDTH = AXI Lite slave bus width (must be 32)
// - AXI_ADDR_WIDTH = AXI Lite address width. see dio24_AXI_slave.v
// - NUM_STRB = number of strobe bits (1 or 2)
// - FIFO_RESET_DELAY = delay for FIFO reset. >= 4 see dio24_reset.v
// - FIFO_RESET_CYCLES = reset cycles for FIFO reset. >=5 see dio24_reset.v
// - NUM_BUTTONS = number of buttons (must be 2)
// - NUM_LED_RED   = number of red LEDs (must be 2)
// - NUM_LED_GREEN = number of green LEDs (must be 2)
// - NUM_LED_BLUE  = number of blue LEDs (must be 2)
// - INV_RED       = bit pattern for each red LED, 0 = normal, 1 = inverted.
// - INV_GREEN     = bit pattern for each green LED, 0 = normal, 1 = inverted.
// - INV_BLUE      = bit pattern for each blue LED, 0 = normal, 1 = inverted.
// - TIME_BITS = number of bits for time (must be 32)
// - TIME_START = LSB index of first time bit (typically 0)
// - DATA_BITS = number of bits for data without time (must be 32)
// - DATA_START_64 = LSB index of first data bit with 64bits/sample (typically 32, i.e. right after time)
// - DATA_START_96_0 = LSB index of first data bit, 96bits/sample, board 0 (typically 32, i.e. right after time)
// - DATA_START_96_1 = LSB index of first data bit, 96bits/sample, board 0 (typically 64, i.e. right after board 0 data)
// - BUS_DATA_BITS = number of data bits (typically 16)
// - BUS_ADDR_BITS = number of address bits (typically 8)
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
// last change 2024/07/29 by Andi
//////////////////////////////////////////////////////////////////////////////////

	module dio24 #
	(
        // fixed data widths needed for port definitions. do not change.
        parameter integer AXI_ADDR_WIDTH        = 7,        // 7: 2^7/4 = 32 registers
        parameter integer AXI_DATA_WIDTH        = 32,       // must be 32
        parameter integer STREAM_DATA_WIDTH     = 128,      // 128
        parameter integer BUS_ADDR_BITS         = 8,        // 8
        parameter integer BUS_DATA_BITS         = 16,       // 16
        parameter integer NUM_STRB              = 1,        // number of bits for bus_strb (1 or 2)
        parameter integer NUM_BUS_EN            = 1,        // number of bits for bus_en (1 or 2)

	    // user-provided version and info register content
        parameter integer VERSION               = 32'h0103_2F2b, // version register 0xMM.mm_(year-2000)<<9+month<<5+day 
        parameter integer INFO                  = 32'h0000_0000,  // info  register, 0xc1 = Cora-Z7-10

	    // AXI stream bus
        parameter integer BITS_PER_SAMPLE  = 64,        // 64 (2 ports) or 96 (4 ports)
	        
        // I/O bits
        parameter integer NUM_IN_BITS = 3,          // number of external inputs
        parameter integer NUM_OUT_BITS = 3,         // number of external outputs
                
        // LEDs and buttons 
        parameter integer NUM_BUTTONS   = 2,        // must be 2
        parameter integer NUM_LED_RED   = 2,        // must be 2
        parameter integer NUM_LED_GREEN = 2,        // must be 2
        parameter integer NUM_LED_BLUE  = 2,        // must be 2
        parameter         INV_RED       = 2'b00,    // bit for each LED
        parameter         INV_GREEN     = 2'b00,    // bit for each LED
        parameter         INV_BLUE      = 2'b00,    // bit for each LED
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
        parameter integer TIME_BITS             = 32,               // must be 32
        parameter integer TIME_START            = 0,                // 0
        parameter integer DATA_BITS             = 32,               // must be 32
        parameter integer DATA_START_64         = 32,               // 32
        parameter integer DATA_START_96_0       = 32,               // 32
        parameter integer DATA_START_96_1       = 64,               // 64
        parameter integer CLK_DIV_BITS          = 8,                // 8: clock divider = 1-255
        parameter integer TRG_DIV_BITS          = 8,                // 8: trigger window divider = 0-255
        parameter integer STRB_DELAY_BITS       = 8,                // 8
        
        // auto-sync
        parameter integer AUTO_SYNC_PULSE_LENGTH = 3,               // 2 = 40ns @ 50MHz 
        parameter integer AUTO_SYNC_PULSE_WAIT   = 5,               // 3 = 60ns @ 50MHz, wait time after pulse
        parameter integer AUTO_SYNC_MAX_PULSES   = 2,               // 2 
        parameter integer AUTO_SYNC_TIME_BITS    = 8,               // 8
        parameter integer AUTO_SYNC_DELAY_BITS   = 10,               // 10
        parameter integer AUTO_SYNC_PHASE_BITS   = 12,               // 12     

        // second address bits selection
        parameter         BUS_ADDR_1_USE = "ZERO",    // "ZERO"/"ADDR0"/"DATA_HIGH" = low / same as bus_addr_0, data[31:24] 
        
        // special data bits. they are not output on bus.
        parameter integer BIT_NOP = 31,             // must be 31. when set then data is not output on bus, but time is still running,
        parameter integer BIT_TRST = 30,            // 30. when set time is reset to 0 [not implemented]
        parameter integer BIT_IRQ = 29,             // 29. when set FPGA_irq is generated.
        parameter integer BIT_STOP = 28,            // 28, when set board waits for next start trigger
        // strobe bit in address data
        parameter integer BIT_STROBE = 23,          // strobe bit = highest address bit in input data.
        parameter         USE_STROBE = "NO",        // "YES" = data output when BIT_STROBE toggles, otherwise BIT_STROBE is ignored.
                                                    // this does not affect bus_strb_0/1 output.
        // synchronization stages
        parameter integer SYNC = 2,                 // 2-3

        // irq_FPGA frequency
        parameter integer IRQ_FREQ_BITS = 20,       // 20 = 10Hz at 10MHz bus clock, 23 = 12Hz @ 100MHz
                
        // minimum number of contiguous cycles until lock lost error is raised. 
        parameter integer ERROR_LOCK_DELAY = 5,

        // TX and RX FIFO
        parameter integer TX_FIFO_DEPTH = 8192,
        parameter integer RX_FIFO_DEPTH = 8192
	)
	(
        // clocks and reset
        //input wire  clk_stream,                     // PL clock with AXI stream data from PS [100MHz]
        input wire  clk_bus,                        // main clock, typically PL clock, can be locked to external clock [100MHz]
        input wire  clk_det,                        // clk_bus + phase shift phi_det [100MHz]
        input wire  clk_pwm,                        // slow clock for PWM of LEDs [10MHz]

        // AXI Lite interface
        //input wire  clk_AXI,                        // AXI Lite clock and phase shift clock for clock wizards (PS clock) [100MHz]
        //input wire  reset_AXI_n,
        output wire reset_AXI_sw_n,                 // @ s00_axi_aclk, hardware + software reset output for clock Wizards
        
        // FPGA board buttons and RGB LEDs
        input wire [NUM_BUTTONS-1:0] buttons_in,    // async
        output wire [NUM_LED_RED-1:0]   led_red,    // @ s00_axi_aclk
        output wire [NUM_LED_GREEN-1:0] led_green,  // @ s00_axi_aclk
        output wire [NUM_LED_BLUE-1:0]  led_blue,   // @ s00_axi_aclk
        
        // buffer board external clock control
        input wire clk_ext_locked,                  // assumed not synchronized to any clock
        input wire clk_mux_locked,                  // assumed not synchronized to any clock
        output wire clk_ext_sel,                    // @ s00_axi_aclk

        // rack data bus output @ clk_bus
        output wire [NUM_BUS_EN-1:0] bus_en,
        output wire [BUS_DATA_BITS-1:0] bus_data,
        output wire [BUS_ADDR_BITS-1:0] bus_addr_0,
        output wire [BUS_ADDR_BITS-1:0] bus_addr_1,
        
        // strobe output at phase shifted clk_bus x2
        output [NUM_STRB-1:0] bus_strb,       
        
        // irq I/O @ s00_axi_aclk
        input wire irq_TX,  // not used
        input wire irq_RX,  // not used
        output wire irq_FPGA,
        
        // external I/O
        input wire [NUM_IN_BITS-1:0] ext_in,
        output wire [NUM_OUT_BITS-1:0] ext_out,
        
        // dynamic phase shift of external clock input and detector clock @ s00_axi_aclk 
        input wire ps_done_ext,
        output wire ps_en_ext,
        output wire ps_inc_ext,
        input wire ps_done_det,
        output wire ps_en_det,
        output wire ps_inc_det,

		// AXI Lite Slave Bus Interface S00_AXI @ s00_axi_aclk
		input wire                            s00_axi_aclk,
        input wire                            s00_axi_aresetn,
		input wire [AXI_ADDR_WIDTH-1 : 0]     s00_axi_awaddr,
		input wire [2 : 0]                    s00_axi_awprot,
		input wire                            s00_axi_awvalid,
		output wire                           s00_axi_awready,
		input wire [AXI_DATA_WIDTH-1 : 0]     s00_axi_wdata,
		input wire [(AXI_DATA_WIDTH/8)-1 : 0] s00_axi_wstrb,
		input wire                            s00_axi_wvalid,
		output wire                           s00_axi_wready,
		output wire [1 : 0]                   s00_axi_bresp,
		output wire                           s00_axi_bvalid,
		input wire                            s00_axi_bready,
		input wire [AXI_ADDR_WIDTH-1 : 0]     s00_axi_araddr,
		input wire [2 : 0]                    s00_axi_arprot,
		input wire                            s00_axi_arvalid,
		output wire                           s00_axi_arready,
		output wire [AXI_DATA_WIDTH-1 : 0]    s00_axi_rdata,
		output wire [1 : 0]                   s00_axi_rresp,
		output wire                           s00_axi_rvalid,
		input wire                            s00_axi_rready,

		// AXI stream data input (from DMA stream master @ AXIS_in_aclk)
		input wire                            AXIS_in_aclk,
        input wire                            AXIS_in_aresetn,
		input wire [STREAM_DATA_WIDTH-1 : 0]  AXIS_in_tdata,
        input wire                            AXIS_in_tlast,
		output wire                           AXIS_in_tready,
		input wire                            AXIS_in_tvalid,
		input wire [(STREAM_DATA_WIDTH/8)-1 : 0] AXIS_in_tkeep,

		// AXI stream data output (to DMA stream slave @ AXIS_out_aclk)
		input wire                            AXIS_out_aclk,
        input wire                            AXIS_out_aresetn,
		output wire [STREAM_DATA_WIDTH-1 : 0] AXIS_out_tdata,
		output wire                           AXIS_out_tlast,
		input wire                            AXIS_out_tready,
		output wire                           AXIS_out_tvalid,
		output wire [(STREAM_DATA_WIDTH/8)-1 : 0] AXIS_out_tkeep

	);

    //////////////////////////////////////////////////////////////////////////////////    
    // helper functions
    
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

    //////////////////////////////////////////////////////////////////////////////////    
    // local settings

    // buttons and LEDs settings
    localparam integer BTN_SYNC             = SYNC; // button clock sychronization. 0 = none.  
    localparam integer BTN_DEB_BITS         = 10;   // button debounce counter bits
    
    // number of control and status registers 
    localparam integer NUM_CTRL             = 8;    // number of control registers (must match AXI slave)
    localparam integer NUM_STATUS           = 8;    // number of status registers (must match AXI slave)
    
    // register indices
    localparam integer REG_CTRL             = 0;    // index of control register 
    localparam integer REG_CTRL_TRG         = 1;    // index of trigger control register
    localparam integer REG_CTRL_OUT         = 2;    // index of trigger control register
    localparam integer REG_NUM_SAMPLES      = 3;    // index of num_samples register
    localparam integer REG_CLK_DIV          = 4;    // index of clk_div register
    localparam integer REG_STRB_DELAY       = 5;    // index of strb_delay register
    localparam integer REG_SYNC_DELAY       = 6;    // index of sync_delay register      
    localparam integer REG_SYNC_PHASE       = 7;    // index of sync_phase register

    // trigger settings
    localparam integer TRG_SYNC             = SYNC; // number of trigger synchronization cycles (>=2)
    
    // control register bits
    localparam integer CTRL_RESET           = 0;       // manual reset (active high), auto-reset after 1 cycle
    localparam integer CTRL_READY           = 1;       // ready bit set by device open/close to indicate server startup
    localparam integer CTRL_RUN             = 2;       // run bit
    // 3 = end bit in status
    localparam integer CTRL_RESTART_EN      = 4;       // restart enable bit
    localparam integer CTRL_AUTO_SYNC_EN    = 5;       // auto-sync enable bit. if set detect start trigger @ clk_det and wait sync_delay, otherwise detect @ clk_bus and no wait.
    localparam integer CTRL_AUTO_SYNC_PRIM  = 6;       // auto-sync primary board. unused at the moment.
    // 7 = phase shift active
    localparam integer CTRL_BPS96           = 8;       // if 1 data format = 96bits per samples
    localparam integer CTRL_BPS96_BRD_1     = 9;       // if CTRL_BPS96: 0 = board 0, 1=board 1 i.e. use DATA_START_0/1
    localparam integer CTRL_CLK_EXT         = 10;      // 0 = internal clock, 1 = external clock
    // 11 = external clock locked
    // 12-18 = error bits in status
    localparam integer CTRL_ERR_LOCK_EN     = 15;      // if set enable error on external lock lost, otherwise continue with internal clock. IRQ_ERR will be still generated.
    // 19 = free 
    localparam integer CTRL_IRQ_EN          = 20;      // 1 = enable all irq output
    localparam integer CTRL_IRQ_END_EN      = 21;      // 1 = enable irq output when in end state
    localparam integer CTRL_IRQ_RESTART_EN  = 22;      // 1 = enable irq output for each restart
    localparam integer CTRL_IRQ_FREQ_EN     = 23;      // 1 = enable irq with IRQ_FREQ frequency
    localparam integer CTRL_IRQ_DATA_EN     = 24;      // 1 = enable irq with BIT_IRQ
    // 27-29 = free
    // 30-31 = buttons in status
    
    // trigger control register
    localparam integer CTRL_TRG_SRC_BITS        = 3;
    localparam integer CTRL_TRG_LEVEL_BITS      = 2;
    localparam integer CTRL_TRG_DST_BITS        = CTRL_TRG_SRC_BITS + CTRL_TRG_LEVEL_BITS;
    
    // trigger destinations offsets (max. floor(32/CTRL_TRG_DST_BITS) = 6 possible)
    localparam integer CTRL_TRG_DST_NUM         = 3;
    localparam integer CTRL_TRG_DST_START       = 0*CTRL_TRG_DST_BITS;  // start trigger (= sync_in with DIO_CTRL_AUTO_SYNC_EN)
    localparam integer CTRL_TRG_DST_STOP        = 1*CTRL_TRG_DST_BITS;  // stop trigger
    localparam integer CTRL_TRG_DST_RESTART     = 2*CTRL_TRG_DST_BITS;  // restart trigger
    
    // trigger sources (max. 2^CTRL_TRG_SRC_BITS = 8 possible)
    localparam integer CTRL_TRG_SRC_NONE        = 0;    // no trigger input
    localparam integer CTRL_TRG_SRC_IN0         = 1;    // ext_in[0]
    localparam integer CTRL_TRG_SRC_IN1         = 2;    // ext_in[1]
    localparam integer CTRL_TRG_SRC_IN2         = 3;    // ext_in[2]
    localparam integer CTRL_TRG_SRC_DATA        = 4;    // data BIT_STOP, used only for CTRL_TRG_SRC_STOP

    // trigger levels (max. 2^CTRL_TRG_LEVEL_BITS = 4 possible)
    localparam integer CTRL_TRG_LEVEL_LOW       = 0;    // level low
    localparam integer CTRL_TRG_LEVEL_HIGH      = 1;    // level higth
    localparam integer CTRL_TRG_EDGE_FALLING    = 2;    // edge falling
    localparam integer CTRL_TRG_EDGE_RISING     = 3;    // edge rising

    // output control register
    localparam integer CTRL_OUT_SRC_BITS        = 4;
    localparam integer CTRL_OUT_LEVEL_BITS      = 2;
    localparam integer CTRL_OUT_DST_BITS        = CTRL_OUT_SRC_BITS + CTRL_OUT_LEVEL_BITS;

    // output destinations offsets (max. floor(32/CTRL_OUT_DST_BITS) = 5 possible)
    localparam integer CTRL_OUT_DST_NUM         = 5;
    localparam integer CTRL_OUT_DST_OUT0        = 0*CTRL_OUT_DST_BITS;  // ext_out[0]
    localparam integer CTRL_OUT_DST_OUT1        = 1*CTRL_OUT_DST_BITS;  // ext_out[1]
    localparam integer CTRL_OUT_DST_OUT2        = 2*CTRL_OUT_DST_BITS;  // ext_out[2]
    localparam integer CTRL_OUT_DST_BUS_EN_0    = 3*CTRL_OUT_DST_BITS;  // bus_en[0]
    localparam integer CTRL_OUT_DST_BUS_EN_1    = 4*CTRL_OUT_DST_BITS;  // bus_en[1]

    // output sources (max. 2^CTRL_OUT_SRC_BITS = 16 possible)
    localparam integer CTRL_OUT_SRC_NONE        = 0;    // fixed output with given level
    localparam integer CTRL_OUT_SRC_SYNC_OUT    = 1;    // sync_out
    localparam integer CTRL_OUT_SRC_SYNC_EN     = 2;    // sync_en (= as_active, for testing is sync_out @ clk_det)
    localparam integer CTRL_OUT_SRC_SYNC_MON    = 3;    // sync_mon (= pulses when sync starts)
    localparam integer CTRL_OUT_SRC_CLK_LOST    = 4;    // clock lost
    localparam integer CTRL_OUT_SRC_ERROR       = 5;    // error
    localparam integer CTRL_OUT_SRC_RUN         = 6;    // run (or wait)
    localparam integer CTRL_OUT_SRC_WAIT        = 7;    // wait
    localparam integer CTRL_OUT_SRC_READY       = 8;    // ready (not really needed)
    localparam integer CTRL_OUT_SRC_RESTART     = 9;    // restart (toogle bit in cycling mode, could also indicate restart trigger)
    localparam integer CTRL_OUT_SRC_TRG_START   = 10;   // start trigger
    localparam integer CTRL_OUT_SRC_TRG_STOP    = 11;   // stop trigger
    localparam integer CTRL_OUT_SRC_TRG_RESTART = 12;   // restart trigger
        
    // output levels (max. 2^CTRL_OUT_LEVEL_BITS = 4 possible)
    localparam integer CTRL_OUT_LEVEL_LOW       = 0;    // level active low = inverted
    localparam integer CTRL_OUT_LEVEL_HIGH      = 1;    // level active high = normal

    // status register bits
    // general
    localparam integer STATUS_RESET      =  0;      // 1 = reset is active
    localparam integer STATUS_READY      =  1;      // 1 = ready = first data received and not finished
    localparam integer STATUS_RUN        =  2;      // 1 = running (or waiting)
    localparam integer STATUS_END        =  3;      // 1 = finished = num_samples generated without error
    localparam integer STATUS_WAIT       =  4;      // 1 = waiting for restart trigger
    // phase shift
    localparam integer STATUS_AUTO_SYNC  = 5;       // 1 = auto sync active
    localparam integer STATUS_AS_TIMEOUT = 6;       // 1 = auto sync timeout
    localparam integer STATUS_PS_ACTIVE  = 7;       // 1 = phase shift active
    // clock
    localparam integer STATUS_CLK_EXT        = 10;  // actual selected clock: 0 = internal clock, 1 = external clock
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

    //////////////////////////////////////////////////////////////////////////////////    
    // global reset @ s00_AXI_aclk
    
    // combine reset sources and ensure reset is long enough for FIFOs
    // reset condition = hardware (active low), software (active high) and 
    // while internal PLL is not locked
    // note: reset_FIFO is not used for XPM FIFO but fast and slow resets. 
    /*
    wire reset_sw;
    wire reset_bus_n;
    wire reset_FIFO;
    wire ext_clk_en;
    dio24_reset # (
        .FIFO_RESET_DELAY(20),
        .FIFO_RESET_CYCLES(20),
        .SYNC(SYNC)
    )
    reset
    (
        // clock and reset sources: hardware, software, PLL_locked
        .clock_fast(s00_axo_aclk),
        .clock_slow(clk_bus),
        .reset_n(s00_axi_aresetn),
        .reset_sw(reset_sw),
        .PLL_locked(1'b1),      // TODO: use clk_int_locked but should not cause reset, but only required for recovery!
        // reset output
        .reset_n_fast(reset_AXI_sw_n),
        .reset_n_slow(reset_bus_n),
        .reset_FIFO(reset_FIFO)
    );*/

    // generate reset_AXI_sw_n signal @ s00_axi_aclk
    // used as global reset and to reset phase shifts and to switch clock source
    // note:
    // - reset condition is hardware reset, sotware reset or switching clock source
    //   this sets reset_active to high and reset_AXI_sw_n to low which resets clock wizards and stops all generated clocks!
    // - after reset conditions are cleared timer starts to count down from RESET_FULL
    // - when it reaches RESET_HALF reset_AXI_sw_n is set high which restarts generated clocks.
    // - after all generated clocks are locked, counter continues to count down
    // - when counter reaches 0 reset_active is set low and reset is finished.   
    // - set RESET_BITS long enough such that slowest clock has enough time to reset.
    //   this is especially important for FIFOs which need quite some cycles on both ports to reset!
    localparam integer RESET_BITS = 7; // set long enough such that slowest clock is reset! 
    localparam integer RESET_FULL = {RESET_BITS{1'b1}};
    localparam integer RESET_HALF = {1'b0,{(RESET_BITS-1){1'b1}}};
    reg [RESET_BITS-1:0] reset_cnt = 0;
    reg reset_AXI_sw_n_ff = 1'b1;
    reg reset_active_n = 1'b1;
    wire reset_sw;
    wire clk_mux_locked_axi;
    always @ ( posedge s00_axi_aclk ) begin
        if ( ( s00_axi_aresetn == 1'b0 ) || ( reset_sw == 1'b1 ) )  begin //|| ( (ext_clk_en & reset_AXI_sw_n_ff & (~clk_ext_sel)) == 1'b1 )) begin // reset condition
            reset_cnt <= RESET_FULL;
            reset_AXI_sw_n_ff <= 1'b0;
            reset_active_n <= 1'b0;
        end
        else if ( reset_cnt > RESET_HALF ) begin // reset condition released but keep clock wizards in reset
            reset_cnt <= reset_cnt - 1;
            reset_AXI_sw_n_ff <= 1'b0;
            reset_active_n <= 1'b0;
        end
        else if ( (reset_cnt > 0) && (clk_mux_locked_axi == 1'b0) ) begin // release clock wizards and wait for locked
            reset_cnt <= reset_cnt;
            reset_AXI_sw_n_ff <= 1'b1;
            reset_active_n <= 1'b0;
        end
        else if ( reset_cnt > 0 ) begin // locked, wait until counter is zero
            reset_cnt <= reset_cnt - 1;
            reset_AXI_sw_n_ff <= 1'b1;
            reset_active_n <= 1'b0;
        end
        else begin // reset finished
            reset_cnt <= 0;
            reset_AXI_sw_n_ff <= 1'b1;
            reset_active_n <= 1'b1;
        end
    end
    assign reset_AXI_sw_n = reset_AXI_sw_n_ff;

    // synchronize hardware and software reset @ clk_bus
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] reset_bus_cdc = {SYNC{1'b1}};
    always @ ( posedge clk_bus ) begin
        reset_bus_cdc <= {reset_bus_cdc[SYNC-2:0],reset_active_n};
    end
    wire reset_bus_n = reset_bus_cdc[SYNC-1];

    // synchronize hardware and software reset @ AXIS_in_aclk
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] reset_in_stream_cdc = {SYNC{1'b1}};
    always @ ( posedge AXIS_in_aclk ) begin
        reset_in_stream_cdc <= {reset_in_stream_cdc[SYNC-2:0],reset_active_n};
    end
    wire reset_in_stream_n = reset_in_stream_cdc[SYNC-1];
    
    // synchronize hardware and software reset @ AXIS_out_aclk
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] reset_out_stream_cdc = {SYNC{1'b1}};
    always @ ( posedge AXIS_out_aclk ) begin
        reset_out_stream_cdc <= {reset_out_stream_cdc[SYNC-2:0],reset_active_n};
    end
    wire reset_out_stream_n = reset_out_stream_cdc[SYNC-1];

	//////////////////////////////////////////////////////////////////////////////////
    // external clock selection @ s00_axi_aclk
    // clock Wizards are all @ s00_axi_aclk and are reset by reset_AXI_sw_n during switching of clock source

    // synchronize external lock signals @ s00_axi_aclk (note: most likely already synced?)    
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] clk_ext_locked_cdc = 0;
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] clk_mux_locked_cdc = 0;
    always @ ( posedge s00_axi_aclk ) begin
        clk_ext_locked_cdc <= {clk_ext_locked_cdc[SYNC-2:0],clk_ext_locked};
        clk_mux_locked_cdc <= {clk_mux_locked_cdc[SYNC-2:0],clk_mux_locked};
        //clk_div_locked_cdc <= {clk_div_locked_cdc[SYNC-2:0],clk_div_locked};
    end
    wire clk_ext_locked_axi = clk_ext_locked_cdc[SYNC-1];
    assign clk_mux_locked_axi = clk_mux_locked_cdc[SYNC-1];

    // external clock is enabled only if internal and external clocks are locked and no error
    // and the clk_ext_sel bit is set
    // we delay selection by one cycle to avoid one cycle re-locking on error for short unlocking.
    // note: for clocking wizard sel=0: clk_in2, sel=1: clk_in1
    wire error;                     // status register bit
    wire ctrl_ext_clk;              // control register bit
    reg [1:0] clk_ext_sel_ff = 2'b00;
    reg clk_ext_lost;               // set immediately when external clock is selected and lock is lost
    wire ext_clk_en = clk_ext_locked_axi & clk_mux_locked_axi & ctrl_ext_clk & (~error);
    always @ ( posedge s00_axi_aclk ) begin
        if ( ( s00_axi_aresetn == 1'b0 ) || ( reset_sw == 1'b1 ) ) begin
            clk_ext_sel_ff[0] <= 1'b0;
            clk_ext_sel_ff[1] <= 1'b0;
        end
        else begin 
            clk_ext_sel_ff[0] <= ext_clk_en;
            clk_ext_sel_ff[1] <= ext_clk_en & clk_ext_sel_ff[0]; // must be at least 2 cycles enabled. disable immediately.
        end
    end
    assign clk_ext_sel = clk_ext_sel_ff[1];
    
    // detect error_lock @ s00_axi_aclk
    // clk_ext_lost = set when external clock selected and lock lost. set until reset.
    // error_lock_count = is counting cycles while clk_ext_lost and CTRL_ERR_LOCK_EN is enabled
    // error_lock = is set when error_lock_count == ERROR_LOCK_DELAY
    // reset by reset_AXI_sw_n (software reset)
    reg error_lock = 1'b0;
    wire ctrl_error_lock_en;
    //wire lock_lost = clk_ext_sel & ((~clk_ext_locked_axi) | (~clk_mux_locked_axi) );
    wire lock_lost = ctrl_ext_clk & ((~clk_ext_locked_axi) | (~clk_mux_locked_axi) );
    wire error_lock_active;
    if ( ERROR_LOCK_DELAY > 0 ) begin
        localparam integer ERROR_LOCK_BITS = clogb2(ERROR_LOCK_DELAY);
        reg [ERROR_LOCK_BITS-1:0] error_lock_count;
        always @ ( posedge s00_axi_aclk ) begin
            if ( reset_AXI_sw_n == 1'b0 ) begin
                error_lock_count <= 0;
            end
            else begin
                error_lock_count <= ( ctrl_error_lock_en & lock_lost ) ? error_lock_count + 1 : 0;
            end
        end
        assign error_lock_active = ( error_lock_count == ERROR_LOCK_DELAY );
    end
    else begin
        assign error_lock_active = ctrl_error_lock_en & lock_lost;
    end
    // error_lock and clk_ext_lost signals @ s00_axi_aclk
    always @ ( posedge s00_axi_aclk ) begin
        if ( reset_AXI_sw_n == 1'b0 ) begin
            clk_ext_lost     <= 1'b0;
            error_lock       <= 1'b0;
        end
        else begin
            clk_ext_lost     <= lock_lost | clk_ext_lost;
            error_lock       <= error_lock_active | error_lock;
        end
    end

    //////////////////////////////////////////////////////////////////////////////////    
    // CDC status registers @ clk_bus -> s00_axi_aclk

    // latency = 4 fast clock cycles
    wire [AXI_DATA_WIDTH-1:0] board_time_bus;
    wire [AXI_DATA_WIDTH-1:0] board_samples_bus;
    wire [AXI_DATA_WIDTH-1:0] board_time_ext_bus;
    wire [AXI_DATA_WIDTH-1:0] board_samples_ext_bus;    
    //wire [AXI_DATA_WIDTH-1:0] sync_time_bus;
    wire [AXI_DATA_WIDTH-1:0] board_time;
    wire [AXI_DATA_WIDTH-1:0] board_samples;
    wire [AXI_DATA_WIDTH-1:0] board_time_ext;
    wire [AXI_DATA_WIDTH-1:0] board_samples_ext;
    wire [AXI_DATA_WIDTH-1:0] sync_time;
    wire status_update;
    cdc # ( 
        .SYNC(SYNC), 
        .DATA_WIDTH(4*AXI_DATA_WIDTH), 
        .USE_OUT_READY("NO")
    )
    cdc_status (
        .in_clock(clk_bus),
        .in_reset_n(reset_bus_n),
        .in_data({board_samples_ext_bus,board_time_ext_bus,board_samples_bus,board_time_bus}),
        .in_valid(1'b1),
        .in_ready(),                        // not used
        .out_clock(s00_axi_aclk),
        .out_reset_n(reset_AXI_sw_n),
        .out_data({board_samples_ext,board_time_ext,board_samples,board_time}),
        .out_valid(status_update),
        .out_ready()                        // not used
    ); 

    //////////////////////////////////////////////////////////////////////////////////    
    // synchronize status bits and trg inputs @ s00_axi_aclk

    // assign status bits from timing module
    localparam integer TIMING_STATUS_BITS = 10;
    wire [TIMING_STATUS_BITS-1:0] timing_status_bus;
    wire [TIMING_STATUS_BITS-1:0] timing_status_axi;
    wire status_ready;
    wire status_run;
    wire status_end;
    wire status_wait;
    wire status_restart;
    wire status_irq_freq;
    wire status_irq_data;
    wire error_in;
    wire error_out;
    wire error_time;
    assign {status_irq_data,status_irq_freq,error_time,error_out,error_in,status_restart,status_wait,status_end,status_run,status_ready} = timing_status_axi;
    wire end_bus = timing_status_bus[2];

    // assign status bits from auto-sync module
    wire as_active_bus;
    wire as_active;
    wire as_timeout;
    wire as_done;
    
    // phase shift status bit
    wire ps_active;
    
    // trigger inputs (only for use in status register)
    //wire trg_start_axi;
    //wire trg_stop_axi;
    
    // other status bits
    localparam integer EKEEP_BITS = 3;
    wire [EKEEP_BITS-1:0] error_keep_stream;
    wire [EKEEP_BITS-1:0] error_keep; // in - smpl - out

    // buttons    
    wire [NUM_BUTTONS-1:0] buttons_AXI;
    wire [NUM_BUTTONS-1:0] buttons_pwm;

    // synchronize control bits and trigger inputs with clk_bus (no reset needed)
    // note: these bits are NOT synced with respect to each other! but transmits faster than CDC above.
    localparam integer NUM_OUT_SYNC = NUM_BUTTONS + EKEEP_BITS + 1 + TIMING_STATUS_BITS;    
    wire [NUM_OUT_SYNC-1:0] out_w = {buttons_pwm,error_keep_stream,as_active_bus,timing_status_bus};
    wire [NUM_OUT_SYNC-1:0] out_s;
    generate
    for (genvar i = 0; i < NUM_OUT_SYNC; i = i + 1)
    begin : O_SYNC
        (* ASYNC_REG = "TRUE" *)
        reg [SYNC-1:0] sync = 0;
        always @ ( posedge s00_axi_aclk ) begin
            sync <= {sync[SYNC-2:0],out_w[i]};
        end
        assign out_s[i] = sync[SYNC-1];
    end
    endgenerate
    assign {buttons_AXI,error_keep,as_active,timing_status_axi} = out_s;
    
	//////////////////////////////////////////////////////////////////////////////////
    // IRQ status @ s00_axi_aclk
        
    // IRQ on error, external clock lost, restart (toggle), end (positive edge) state or update (toggle)
    // reset with reset_n_fast or set irq_en = 0
    // note: even if disabled maintain edge detector of end state!
    //       otherwise on enabling will trigger irq when already in end state.
    reg [4:0] irq_out_ff;       // irq status bits
    wire [4:0] irq_en;          // irq enable control bits
    reg [1:0] status_err_ff;    // positive edge detector of error
    reg [1:0] status_end_ff;    // positive edge detector of end state
    reg status_restart_ff;      // status_restart change detector
    reg status_irq_freq_ff;     // status_irq_freq change detector
    reg status_irq_data_ff;     // status_irq_data change detector
    always @ ( posedge s00_axi_aclk ) begin
        if ( reset_AXI_sw_n == 1'b0 ) begin
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

	//////////////////////////////////////////////////////////////////////////////////
	// buttons and LEDs (status) @ clk_pwm
	
	wire clk_ext_locked_pwm;
	wire clk_ext_sel_pwm;
	wire run_pwm;
	wire error_pwm;
	wire end_pwm;
	wire restart_pwm;
    wire svr_ready;                     // control bit    
	wire ready_axi = svr_ready | status_ready | status_end;
	wire ready_pwm;
	wire reset_sw_n_pwm;
	
    // synchronize bits used for LEDs with clk_pwm
    localparam integer NUM_PWM_SYNC = 8;    
    wire [NUM_PWM_SYNC-1:0] pwm_w = {status_restart,status_end,error,status_run,ready_axi,clk_ext_sel,clk_ext_locked_axi,reset_AXI_sw_n};
    wire [NUM_PWM_SYNC-1:0] pwm_s;
    generate
    for (genvar i = 0; i < NUM_PWM_SYNC; i = i + 1)
    begin : PWM_SYNC
        (* ASYNC_REG = "TRUE" *)
        reg [SYNC-1:0] sync_pwm = 0;
        always @ ( posedge clk_pwm ) begin
            sync_pwm <= {sync_pwm[SYNC-2:0],pwm_w[i]};
        end
        assign pwm_s[i] = sync_pwm[SYNC-1];
    end
    endgenerate
    assign {restart_pwm,end_pwm,error_pwm,run_pwm,ready_pwm,clk_ext_sel_pwm,clk_ext_locked_pwm,reset_sw_n_pwm} = pwm_s;
    
    /* test
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] reset_n_pwm_sync = 0;
    always @ ( posedge clk_pwm ) begin
        reset_n_pwm_sync <= {reset_n_pwm_sync[SYNC-2:0],s00_axi_aresetn};
    end
    wire reset_n_pwm = reset_n_pwm_sync[SYNC-1];
    */
    
    wire reset_n_pwm;
    cdc_no_bus # (
        .BITS_WIDTH(1),
        .SYNC_STAGES(SYNC),
        .USE_INPUT_BUFFER("NO")
    )
    sync_clk_pwm_reset (
        .clk_in(s00_axi_aclk),
        .clk_out(clk_pwm),
        .in(s00_axi_aresetn),
        .out(reset_n_pwm)
    );

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
    localparam NUM_LEDS = NUM_LED_RED + NUM_LED_GREEN + NUM_LED_BLUE;
    wire [NUM_LEDS-1:0] leds_out;
    assign led_red  [0] = leds_out[0];  // Cora red (error)
    assign led_red  [1] = leds_out[1];  // buffer board red (error)
    assign led_green[0] = leds_out[2];  // Cora green (ok)
    assign led_green[1] = leds_out[3];  // buffer board green (ok)
    assign led_blue [0] = leds_out[4];  // Cora blue (ext clock locked)
    assign led_blue [1] = leds_out[5];  // buffer board green or blue (ext clock locked)
    reg  [NUM_LEDS - 1 : 0] leds_in;
    reg  [NUM_LEDS - 1 : 0] leds_bright = {DIM,BRIGHT,DIM,BRIGHT,DIM,BRIGHT}; // overall brightness level
    reg  [NUM_LEDS - 1 : 0] leds_blink;
    reg  [NUM_LEDS - 1 : 0] leds_high;
    wire [NUM_LEDS - 1 : 0] leds_inv    = {INV_BLUE,INV_GREEN,INV_RED};
    wire any_btn = |buttons_pwm;
    always @ ( posedge clk_pwm ) begin
        if ( (reset_sw_n_pwm == 1'b0) || (any_btn == 1'b1) ) begin // reset or any button pressed: all LEDs ON bright.
            leds_in <= {ON,ON,ON,ON,ON,ON};
            leds_blink <= {CONT,CONT,CONT,CONT,CONT,CONT};     
            leds_high <= {BRIGHT,BRIGHT,BRIGHT,BRIGHT,BRIGHT,BRIGHT};
            //leds_inv <= {NUM_LEDS{1'b0}};
        end
        else if ( error_pwm ) begin // error: red on
            leds_in <= {clk_ext_locked_pwm, clk_ext_locked_pwm, OFF,OFF,ON,ON};
            leds_blink <= {CONT,CONT,CONT,CONT,CONT,CONT};     
            leds_high <= {BRIGHT,BRIGHT,BRIGHT,BRIGHT,BRIGHT,BRIGHT};     
            //leds_inv <= {NUM_LEDS{1'b0}};
        end
        else if ( run_pwm ) begin // run: green LED bright/dim toggled after each restart
            leds_in <= {clk_ext_locked_pwm,clk_ext_locked_pwm,ON,ON,OFF,OFF};
            leds_blink <= {CONT,CONT,CONT,CONT,CONT,CONT};     
            leds_high <= {BRIGHT,BRIGHT,~restart_pwm,~restart_pwm,DIM,DIM};
            //leds_inv <= {NUM_LEDS{1'b0}};
        end
        else if ( svr_ready | status_ready | status_end ) begin // server connected, ready for data, or end: all off
            leds_in <= {clk_ext_locked_pwm,clk_ext_locked_pwm,OFF,OFF,OFF,OFF};
            leds_blink <= {CONT,CONT,CONT,CONT,CONT,CONT};     
            leds_high <= {BRIGHT,BRIGHT,BRIGHT,BRIGHT,BRIGHT,BRIGHT};     
            //leds_inv <= {NUM_LEDS{1'b0}};
        end
        else begin // waiting for server to connect: all on
            leds_in <= {clk_ext_locked_pwm,clk_ext_locked_pwm,ON,ON,ON,ON};
            leds_blink <= {CONT,CONT,CONT,CONT,CONT,CONT};     
            leds_high <= {BRIGHT,BRIGHT,BRIGHT,BRIGHT,DIM,DIM};     
            //leds_inv <= {NUM_LEDS{1'b0}};
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
        .clk(clk_pwm),
        .reset_n(reset_n_pwm),
        // buttons
        .btn_in(buttons_in), // unsynchronized buttons in
        .btn_status(buttons_pwm), // output synchronized buttons with clk_pwm
        // LEDs
        .leds_in(leds_in),
        .leds_out(leds_out),
        .leds_bright(leds_bright),
        .leds_blink(leds_blink),
        .leds_high(leds_high),
        .leds_inv(leds_inv)
        );

    /* TODO put together with other LEDs with PWM. might be very bright!
    localparam integer LED_BLINK_BITS = 5;
    reg [LED_BLINK_BITS-1:0] led_blink = 0;
    reg [1:0] led_blue_ff = 2'b0;
    always @ ( posedge s00_axi_aclk ) begin
        led_blink <= led_blink + 1;
        led_blue_ff[0] <= clk_ext_locked_axi & (led_blink == 0);        // indicates external clock locked
        led_blue_ff[1] <= clk_ext_sel        & (led_blink == 0);        // indicates external clock used
    end 
    assign led_blue = led_blue_ff;
    */

    //////////////////////////////////////////////////////////////////////////////////    
    // AXI Lite bus @ s00_axi_aclk

    reg ps_done_ext_ff;
    reg ps_done_det_ff;

    // status bit assignments @ s00_axi_aclk
    wire [AXI_DATA_WIDTH-1:0] status; // status register
    assign error = error_in | error_out | error_time | error_lock | error_keep[0] | error_keep[1] | error_keep[2];
    generate
      for (genvar i = 0; i < AXI_DATA_WIDTH; i = i + 1)
      begin:REG_STATUS
        case ( i )
          STATUS_RESET:             assign status[i] = ~reset_AXI_sw_n;
          STATUS_READY:             assign status[i] = status_ready;
          STATUS_RUN:               assign status[i] = status_run;
          STATUS_END:               assign status[i] = status_end;
          STATUS_WAIT:              assign status[i] = status_wait;
          //
          STATUS_AUTO_SYNC:         assign status[i] = as_active;
          STATUS_AS_TIMEOUT:        assign status[i] = as_timeout;
          STATUS_PS_ACTIVE:         assign status[i] = ps_active;
          // 
          STATUS_CLK_EXT:           assign status[i] = clk_ext_sel;
          STATUS_CLK_EXT_LOCKED:    assign status[i] = clk_ext_locked_axi;
          //
          STATUS_ERR_IN:            assign status[i] = error_in;
          STATUS_ERR_OUT:           assign status[i] = error_out;
          STATUS_ERR_TIME:          assign status[i] = error_time;
          STATUS_ERR_LOCK:          assign status[i] = clk_ext_lost;  // external clock lost 
          STATUS_ERR_TKEEP:         assign status[i] = error_keep[0]; //clk_mux_locked_axi; //error_keep[0];
          STATUS_ERR_TKEEP2:        assign status[i] = error_keep[1]; //clk_div_locked_axi; //error_keep[1];
          STATUS_ERR_TKEEP3:        assign status[i] = error_keep[2];
          //
          STATUS_IRQ_ERROR:         assign status[i] = irq_out_ff[0];
          STATUS_IRQ_END:           assign status[i] = irq_out_ff[1];
          STATUS_IRQ_RESTART:       assign status[i] = irq_out_ff[2];
          STATUS_IRQ_FREQ:          assign status[i] = irq_out_ff[3];
          STATUS_IRQ_DATA:          assign status[i] = irq_out_ff[4];
          // 
          //STATUS_TRG_START:         assign status[i] = trg_start_axi;
          //STATUS_TRG_STOP:          assign status[i] = trg_stop_axi;
          //
          STATUS_BTN_0:             assign status[i] = buttons_AXI[0];
          STATUS_BTN_1:             assign status[i] = buttons_AXI[1];
          //
          default:                  assign status[i] = 1'b0;
        endcase
      end
    endgenerate
                    
    wire [AXI_DATA_WIDTH-1:0] control;
    wire [NUM_CTRL-1:0] ctrl_update;          // pulses bit corresponding to control register when was updated
    wire [AXI_DATA_WIDTH-1:0] ctrl_trg;
    wire [AXI_DATA_WIDTH-1:0] ctrl_out;
    wire [AXI_DATA_WIDTH-1:0] num_samples;
    wire [AXI_DATA_WIDTH-1:0] clk_div;
    wire [AXI_DATA_WIDTH-1:0] strb_delay;
    wire [AXI_DATA_WIDTH-1:0] sync_delay;
    wire [AXI_DATA_WIDTH-1:0] sync_phase;
	dio24_AXI_slave # (
		.VERSION(VERSION),
        .INFO(INFO),
		.C_S_AXI_DATA_WIDTH(AXI_DATA_WIDTH),
		.C_S_AXI_ADDR_WIDTH(AXI_ADDR_WIDTH),
		.NUM_CTRL(NUM_CTRL),
		.NUM_STATUS(NUM_STATUS),
		.REG_CTRL(REG_CTRL),
		.REG_CTRL_RESET(CTRL_RESET)
	) dio24_AXI_inst (
		.S_AXI_ACLK(s00_axi_aclk),
		.S_AXI_ARESETN(s00_axi_aresetn),          // note: dont reset with reset_sw
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
		// control registers
		.control(control),
		.ctrl_trg(ctrl_trg),
		.ctrl_out(ctrl_out),
		.num_samples(num_samples),
		.clk_div(clk_div),
		.strb_delay(strb_delay),
		.sync_delay(sync_delay),
		.sync_phase(sync_phase),
		// status registers
		.status(status),
		.board_time(board_time),
        .board_samples(board_samples),
		.board_time_ext(board_time_ext),
        .board_samples_ext(board_samples_ext),
        .sync_time(sync_time),
        // pulses bit corresponding to control register when was updated
		.ctrl_update(ctrl_update)
	);
			
	//////////////////////////////////////////////////////////////////////////////////
    // dynamic phase shift @ s00_axi_aclk

    // start phase shift when sync_phase register was written
    wire ps_start       = ctrl_update[REG_SYNC_PHASE];

    // external clock dynamic phase shift @ clock_pclk
    wire ps_ext_active;
    dynamic_phase # (
        .PHASE_BITS(AUTO_SYNC_PHASE_BITS)
    )
    ps_ext
    (
        // clock and reset
        .clock(s00_axi_aclk),                    // if pclk = s00_axi_aclk then all wizards can be reset with same reset signal
        .reset_n(reset_AXI_sw_n),           // same reset as for clock wizard. triggered by HW, SW and switching of clock.
        // control and status
        .ps_start(ps_start),
        .ps_active(ps_ext_active),
        // clock is locked signal
        .clock_locked(clk_ext_locked_axi),      // external clock must be locked and stay locked during phase shift
        // ps control
        .ps_en(ps_en_ext),
        .ps_inc(ps_inc_ext), 
        .ps_done(ps_done_ext),
        // phase shift @ s00_axi_aclk
        .ps_phase(sync_phase[2*AUTO_SYNC_PHASE_BITS-1:AUTO_SYNC_PHASE_BITS])
        //.ps_phase(sync_phase[AUTO_SYNC_PHASE_BITS-1:0])
    );

    // temporary test    
    always @ (posedge s00_axi_aclk) begin
        if (reset_AXI_sw_n == 1'b0) begin
            ps_done_ext_ff <= 1'b0;
            ps_done_det_ff <= 1'b0;
        end
        else begin
            ps_done_ext_ff <= (ps_done_ext) ? 1'b1 : ps_done_ext_ff;
            ps_done_det_ff <= (ps_done_det) ? 1'b1 : ps_done_det_ff;
        end
    end

    // detector clock dynamic phase shift @ clock_pclk
    wire ps_det_active;
    dynamic_phase # (
        .PHASE_BITS(AUTO_SYNC_PHASE_BITS)
    )
    ps_det
    (
        // clock and reset
        .clock(s00_axi_aclk),                    // if pclk = s00_axi_aclk then all wizards can be reset with same reset signal
        .reset_n(reset_AXI_sw_n),           // same reset as for clock wizard. triggered by HW, SW and switching of clock.
        // control and status
        .ps_start(ps_start),
        .ps_active(ps_det_active),
        // clock is locked signal
        .clock_locked(clk_mux_locked_axi & clk_ext_locked_axi), // ensure all clocks are locked. 
        // ps control
        .ps_en(ps_en_det),
        .ps_inc(ps_inc_det), 
        .ps_done(ps_done_det),
        // phase shift @ s00_axi_aclk
        .ps_phase(sync_phase[AUTO_SYNC_PHASE_BITS-1:0])
    );
    
    assign ps_active = ps_ext_active | ps_det_active;

	//////////////////////////////////////////////////////////////////////////////////
    // CDC control bits & trigger and locked inputs @ clk_bus 

    // control register assignments @ s00_axi_aclk
    assign reset_sw             = control[CTRL_RESET];  // this is auto-reset by dio24_AXI_slave
    assign svr_ready            = control[CTRL_READY];
    wire run_en                 = control[CTRL_RUN];
    wire restart_en             = control[CTRL_RESTART_EN];
    wire as_en                  = control[CTRL_AUTO_SYNC_EN];
    wire as_prim                = control[CTRL_AUTO_SYNC_PRIM]; // note: keep defined but has no action.
    wire str_96                 = control[CTRL_BPS96];
    wire str_96_b1              = control[CTRL_BPS96_BRD_1];
    assign ctrl_ext_clk         = control[CTRL_CLK_EXT];
    assign ctrl_error_lock_en   = control[CTRL_ERR_LOCK_EN]; 
    wire irq_freq_en            = control[CTRL_IRQ_FREQ_EN];
    wire irq_data_en            = control[CTRL_IRQ_DATA_EN];
    assign irq_en               = {irq_data_en,irq_freq_en,control[CTRL_IRQ_RESTART_EN],control[CTRL_IRQ_END_EN],control[CTRL_IRQ_EN]};
    
    // control bits into timing module
    localparam integer TIMING_CTRL_BITS = 4;       // number of control bits for timing module
    wire [TIMING_CTRL_BITS - 1 : 0] timing_ctrl = {irq_data_en,irq_freq_en,restart_en,run_en};
    wire [TIMING_CTRL_BITS - 1 : 0] timing_ctrl_bus;
    wire run_en_bus = timing_ctrl_bus[0];
    
    // locked bits
    //localparam integer LOCKED_BITS = 2;
    //wire [LOCKED_BITS-1 : 0] locked = {clk_mux_locked,clk_ext_locked};
    //wire [LOCKED_BITS-1 : 0] locked_bus;
    
    // trigger bits
    //localparam integer TRG_BITS = 4;
    //wire [TRG_BITS-1 : 0] trig = {trg_stop,trg_start,trg_stop_en,trg_start_en};
    //wire [TRG_BITS-1 : 0] trig_bus;
    //wire trg_start_en_bus = trig_bus[0];
    //wire trg_stop_en_bus  = trig_bus[1];
    //wire trg_start_bus    = trig_bus[2];
    //wire trg_stop_bus     = trig_bus[3];

    // synchronize control bits with clk_bus (no reset needed)
    // note: these bits are NOT synced with respect to each other! but transmits faster than CDC above.    
    localparam integer NUM_IN_SYNC = 4 + TIMING_CTRL_BITS; //+ AS_CTRL_BITS; //+ LOCKED_BITS; // + TRG_BITS;
    wire svr_ready_bus;
    wire error_bus;
    wire ctrl_ext_clk_bus;
    wire as_en_bus; // if 1'b1 start trigger is detected @ clk_det in as module, otherwise directly here (see run_bus)
    //wire trg_start_en_bus;
    //wire [NUM_IN_SYNC-1:0] in_w = {ctrl_ext_clk,error,svr_ready,as_ctrl,timing_ctrl};
    wire [NUM_IN_SYNC-1:0] in_w = {ctrl_ext_clk,error,svr_ready,as_en,timing_ctrl};
    wire [NUM_IN_SYNC-1:0] in_s;
    generate
    for (genvar i = 0; i < NUM_IN_SYNC; i = i + 1)
    begin : I_SYNC
        (* ASYNC_REG = "TRUE" *)
        reg [SYNC-1:0] sync = 0;
        always @ ( posedge clk_bus ) begin
            sync <= {sync[SYNC-2:0],in_w[i]};
        end
        assign in_s[i] = sync[SYNC-1];
    end
    endgenerate
    //assign {ctrl_ext_clk_bus,error_bus,svr_ready_bus,as_ctrl_bus,timing_ctrl_bus} = in_s;
    assign {ctrl_ext_clk_bus,error_bus,svr_ready_bus,as_en_bus,timing_ctrl_bus} = in_s;
        
	//////////////////////////////////////////////////////////////////////////////////
    // input AXI stream @ AXIS_in_aclk
    
    // synchronize stream selection bits @ AXIS_in_aclk
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] str_96_cdc = 0;
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] str_96_b1_cdc = 0;
    always @ ( posedge AXIS_in_aclk ) begin
        str_96_cdc    <= {str_96_cdc   [SYNC-2:0],str_96};
        str_96_b1_cdc <= {str_96_b1_cdc[SYNC-2:0],str_96_b1};
    end
    wire str_96_stream    = str_96_cdc   [SYNC-1];
    wire str_96_b1_stream = str_96_b1_cdc[SYNC-1];
	
	// convert DMA input data stream to 64/96bits per sample
	// TODO: dynamic switching str_96_stream and selection of board data str_96_b1_stream
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
	       .clock(AXIS_in_aclk),
	       .reset_n(reset_in_stream_n),
	       // tkeep error
	       .error_keep(error_keep_stream[0]),
	       // data input
	       .in_data(AXIS_in_tdata),
	       .in_last(AXIS_in_tlast),
	       .in_keep(AXIS_in_tkeep),
	       .in_valid(AXIS_in_tvalid),
	       .in_ready(AXIS_in_tready),
	       // data output
	       .out_data(in_data_smpl),
           .out_last(in_last_smpl),	 
           .out_keep(in_keep_smpl),
           .out_valid(in_valid_smpl),
           .out_ready(in_ready_smpl)
	   );
	end
	else begin
	   assign error_keep_stream[0] = 1'b0;
	   assign in_data_smpl = AXIS_in_tdata;
	   assign in_last_smpl = AXIS_in_tlast;
	   assign in_keep_smpl = AXIS_in_tkeep;
	   assign in_valid_smpl = AXIS_in_tvalid;
	   assign AXIS_in_tready = in_ready_smpl;
	end
	
	// in_keep_smpl must have all bits high
	reg error_keep_smpl = 1'b0;
	always @ ( posedge AXIS_in_aclk ) begin
	   if ( reset_in_stream_n == 1'b0 ) error_keep_smpl <= 1'b0;
	   else if ( in_valid_smpl & in_ready_smpl ) begin
	       error_keep_smpl <= ( in_keep_smpl != {(BITS_PER_SAMPLE/8){1'b1}}) ? 1'b1 : error_keep_smpl;
	   end
	   else begin
	       error_keep_smpl <= error_keep_smpl;
	   end
	end
	assign error_keep_stream[1] = error_keep_smpl;

    // TX data stream: select time and data from samples
    localparam integer TIMEDATA_BITS = TIME_BITS + DATA_BITS;
    wire [TIMEDATA_BITS - 1 : 0] in_data_TX;
    wire in_last_TX;
    wire in_valid_TX;
    wire in_ready_TX;
    wire [clogb2(BITS_PER_SAMPLE-DATA_BITS)-1:0] data_offset = str_96_stream ? (str_96_b1_stream ? DATA_START_96_1 : DATA_START_96_0) : DATA_START_64;
   	if (BITS_PER_SAMPLE != TIMEDATA_BITS) begin
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
        
	//////////////////////////////////////////////////////////////////////////////////
    // TX FIFO @ AXIS_in_aclk -> clk_bus 

	wire [TIMEDATA_BITS - 1 : 0] in_data_bus;    
	wire in_last_bus;
	wire in_ready_bus;
	wire in_valid_bus;
    dio24_FIFO # (
        .STREAM_DATA_WIDTH(TIMEDATA_BITS + 1),
        .FIFO_DEPTH(TX_FIFO_DEPTH),
        .OUT_ZERO("FALSE")
    )
    TX_FIFO
    (
        .in_clock(AXIS_in_aclk),
        .in_reset_n(reset_in_stream_n),
        .in_data({in_last_TX,in_data_TX}),
        .in_ready(in_ready_TX),
        .in_valid(in_valid_TX),
        .out_clock(clk_bus),
        .out_reset_n(reset_bus_n),
        .out_data({in_last_bus,in_data_bus}),
        .out_valid(in_valid_bus),
        .out_ready(in_ready_bus)
    );

	//////////////////////////////////////////////////////////////////////////////////
    // CDC control registers @ s00_axi_aclk -> clk_bus 
    
    // cdc valid signal 
    // set when num_samples or clk_div or reg_trg is updated
    // reset when cdc is ready
    reg ctrl_regs_reload_axi;
    wire cdc_ctrl_ready;
    always @ ( posedge s00_axi_aclk ) begin
        if ( s00_axi_aresetn == 1'b0 ) ctrl_regs_reload_axi <= 1'b0;
        else if ( ctrl_update[REG_NUM_SAMPLES] | ctrl_update[REG_CLK_DIV] | ctrl_update[REG_CTRL_TRG] ) ctrl_regs_reload_axi <= 1'b1;
        else if ( cdc_ctrl_ready ) ctrl_regs_reload_axi <= 1'b0;
        else ctrl_regs_reload_axi <= ctrl_regs_reload_axi;
    end

    // sync registers @ clk_bus
    // CDC ensures consistency between bits
    wire ctrl_regs_reload_bus;
    wire [AXI_DATA_WIDTH-1:0] num_samples_bus;
    wire [CTRL_TRG_DST_NUM*CTRL_TRG_DST_BITS-1:0] ctrl_trg_bus;
    wire [CLK_DIV_BITS-1:0] clk_div_bus;
    wire [TRG_DIV_BITS-1:0] trg_div_bus;
    wire [AUTO_SYNC_DELAY_BITS-1 : 0] sync_delay_bus;
    //wire [AUTO_SYNC_PHASE_BITS*2-1 : 0] sync_phase_bus;
    cdc # ( 
        .SYNC(SYNC), 
        .DATA_WIDTH(AUTO_SYNC_DELAY_BITS + TRG_DIV_BITS + CLK_DIV_BITS + CTRL_TRG_DST_NUM*CTRL_TRG_DST_BITS + AXI_DATA_WIDTH), // + AUTO_SYNC_PHASE_BITS*2 
        .USE_OUT_READY("NO")
    )
    cdc_ctrl (
        .in_clock(s00_axi_aclk),
        .in_reset_n(s00_axi_aresetn),
        .in_data({sync_delay[AUTO_SYNC_DELAY_BITS-1:0],clk_div[CLK_DIV_BITS+TRG_DIV_BITS-1:0],ctrl_trg[CTRL_TRG_DST_NUM*CTRL_TRG_DST_BITS-1:0],num_samples}),
        .in_valid(ctrl_regs_reload_axi),
        .in_ready(cdc_ctrl_ready),
        .out_clock(clk_bus),
        .out_reset_n(reset_bus_n),
        .out_data({sync_delay_bus,trg_div_bus,clk_div_bus,ctrl_trg_bus,num_samples_bus}),
        .out_valid(ctrl_regs_reload_bus),       // pulses when num_samples or clk_div is updated
        .out_ready(1'b1)                        // always ready
    ); 
    
	//////////////////////////////////////////////////////////////////////////////////
    // multiplex and synchronize ctrl_trg register @ clk_bus 
    
    // synchronize external inputs for triggers @ clk_bus
    // note: there is no way to ensure that these bits are synchronized with each other!
    //       when different inputs are used and might change state at the same time,
    //       ensure that STOP and RESTART trigger are sampled at opposite edges.
    //       for START trigger use auto-sync module (with as_en bit) which introduces a delay 
    //       which should avoid this problem.
    wire [NUM_IN_BITS - 1 : 0] ext_in_bus;
    generate
    for (genvar i = 0; i < NUM_IN_BITS; i = i + 1) begin : GEN_EXT
        (* ASYNC_REG = "TRUE" *)
        reg [SYNC-1:0] ext_in_bus_cdc;
        always @ ( posedge clk_bus ) begin
            ext_in_bus_cdc <= {ext_in_bus_cdc[SYNC-2:0],ext_in[i]};
        end
        assign ext_in_bus[i] = ext_in_bus_cdc[SYNC-1];
    end
    endgenerate
    
    // assign control_trg register @ clk_bus
    wire [CTRL_TRG_DST_BITS-1:0] ctrl_trg_start_bus   = ctrl_trg_bus[CTRL_TRG_DST_START  +CTRL_TRG_DST_BITS-1 -: CTRL_TRG_DST_BITS];
    wire [CTRL_TRG_DST_BITS-1:0] ctrl_trg_stop_bus    = ctrl_trg_bus[CTRL_TRG_DST_STOP   +CTRL_TRG_DST_BITS-1 -: CTRL_TRG_DST_BITS];
    wire [CTRL_TRG_DST_BITS-1:0] ctrl_trg_restart_bus = ctrl_trg_bus[CTRL_TRG_DST_RESTART+CTRL_TRG_DST_BITS-1 -: CTRL_TRG_DST_BITS];
    
    // MUX start trigger @ clk_bus
    reg start_trg_bus = 1'b0;
    reg start_trg_en_bus = 1'b0;
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) begin
            start_trg_bus    <= 1'b0;
            start_trg_en_bus <= 1'b0;
        end
        else begin
            start_trg_bus    <= ( ctrl_trg_start_bus[CTRL_TRG_SRC_BITS-1:0] == CTRL_TRG_SRC_IN0 ) ? ext_in_bus[0] :
                                ( ctrl_trg_start_bus[CTRL_TRG_SRC_BITS-1:0] == CTRL_TRG_SRC_IN1 ) ? ext_in_bus[1] :
                                ( ctrl_trg_start_bus[CTRL_TRG_SRC_BITS-1:0] == CTRL_TRG_SRC_IN2 ) ? ext_in_bus[2] : 1'b0;
            start_trg_en_bus <= ( ctrl_trg_start_bus[CTRL_TRG_SRC_BITS-1:0] == CTRL_TRG_SRC_IN0 ) ? 1'b1 :
                                ( ctrl_trg_start_bus[CTRL_TRG_SRC_BITS-1:0] == CTRL_TRG_SRC_IN1 ) ? 1'b1 :
                                ( ctrl_trg_start_bus[CTRL_TRG_SRC_BITS-1:0] == CTRL_TRG_SRC_IN2 ) ? 1'b1 : 1'b0;
        end
    end
          
    // generate start trigger positive edge pulse @ clk_det
    reg start_trg_ff_bus    = 1'b0;
    reg start_trg_pulse_bus = 1'b0;
    reg start_trg_tgl_bus   = 1'b0;
    always @ ( posedge clk_bus ) begin
            if (reset_bus_n == 1'b0) begin
            start_trg_ff_bus    <= 1'b0;
            start_trg_pulse_bus <= 1'b0;
            start_trg_tgl_bus   <= 1'b0;
        end
        else begin
        start_trg_ff_bus    <= (ctrl_trg_start_bus[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_LEVEL_HIGH  ) ? run_en_bus & start_trg_en_bus & start_trg_bus : 
                               (ctrl_trg_start_bus[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_LEVEL_LOW   ) ? run_en_bus & start_trg_en_bus & ~start_trg_bus :
                               (ctrl_trg_start_bus[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_EDGE_FALLING) ? start_trg_bus :
                               (ctrl_trg_start_bus[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_EDGE_RISING ) ? start_trg_bus : 1'b0;
        start_trg_pulse_bus <= run_en_bus & start_trg_en_bus & (
                               (ctrl_trg_start_bus[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_LEVEL_HIGH  ) ? ({start_trg_ff_bus,start_trg_bus} == 2'b01) : 
                               (ctrl_trg_start_bus[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_LEVEL_LOW   ) ? ({start_trg_ff_bus,start_trg_bus} == 2'b00) :
                               (ctrl_trg_start_bus[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_EDGE_FALLING) ? ({start_trg_ff_bus,start_trg_bus} == 2'b10) :
                               (ctrl_trg_start_bus[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_EDGE_RISING ) ? ({start_trg_ff_bus,start_trg_bus} == 2'b01) : 1'b0 );
        start_trg_tgl_bus   <= run_en_bus & start_trg_en_bus & (
                               (ctrl_trg_start_bus[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_LEVEL_HIGH  ) ? ({start_trg_ff_bus,start_trg_bus} == 2'b01) ? ~start_trg_tgl_bus : start_trg_tgl_bus : 
                               (ctrl_trg_start_bus[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_LEVEL_LOW   ) ? ({start_trg_ff_bus,start_trg_bus} == 2'b00) ? ~start_trg_tgl_bus : start_trg_tgl_bus :
                               (ctrl_trg_start_bus[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_EDGE_FALLING) ? ({start_trg_ff_bus,start_trg_bus} == 2'b10) ? ~start_trg_tgl_bus : start_trg_tgl_bus :
                               (ctrl_trg_start_bus[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_EDGE_RISING ) ? ({start_trg_ff_bus,start_trg_bus} == 2'b01) ? ~start_trg_tgl_bus : start_trg_tgl_bus : 1'b0 );
        end
    end

    // MUX stop trigger @ clk_bus
    reg stop_trg_bus = 1'b0;
    reg stop_trg_en_bus = 1'b0;
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) begin
            stop_trg_bus    <= 1'b0;
            stop_trg_en_bus <= 1'b0;
        end
        else begin
            stop_trg_bus    <= ( ctrl_trg_stop_bus[CTRL_TRG_SRC_BITS-1:0] == CTRL_TRG_SRC_IN0  ) ? ext_in_bus[0] :
                               ( ctrl_trg_stop_bus[CTRL_TRG_SRC_BITS-1:0] == CTRL_TRG_SRC_IN1  ) ? ext_in_bus[1] :
                               ( ctrl_trg_stop_bus[CTRL_TRG_SRC_BITS-1:0] == CTRL_TRG_SRC_IN2  ) ? ext_in_bus[1] :
                               ( ctrl_trg_stop_bus[CTRL_TRG_SRC_BITS-1:0] == CTRL_TRG_SRC_DATA ) ? 1'b0 : 1'b0; // TODO: data stop not implemented
            stop_trg_en_bus <= ( ctrl_trg_stop_bus[CTRL_TRG_SRC_BITS-1:0] == CTRL_TRG_SRC_IN0  ) ? 1'b1 :
                               ( ctrl_trg_stop_bus[CTRL_TRG_SRC_BITS-1:0] == CTRL_TRG_SRC_IN1  ) ? 1'b1 :
                               ( ctrl_trg_stop_bus[CTRL_TRG_SRC_BITS-1:0] == CTRL_TRG_SRC_IN2  ) ? 1'b1 :
                               ( ctrl_trg_stop_bus[CTRL_TRG_SRC_BITS-1:0] == CTRL_TRG_SRC_DATA ) ? 1'b0 : 1'b0; // TODO: data stop not implemented
        end
    end
     
    // generate stop trigger positive edge pulse @ clk_bus
    reg stop_trg_ff_bus = 1'b0;
    reg stop_trg_pulse_bus = 1'b0;
    always @ ( posedge clk_bus ) begin
        if (reset_bus_n == 1'b0) begin
            stop_trg_ff_bus <= 1'b0;
            stop_trg_pulse_bus <= 1'b0;
        end
        else begin
        stop_trg_ff_bus    <= (ctrl_trg_stop_bus[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_LEVEL_HIGH  ) ? run_en_bus & stop_trg_en_bus & stop_trg_bus : 
                              (ctrl_trg_stop_bus[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_LEVEL_LOW   ) ? run_en_bus & stop_trg_en_bus & ~stop_trg_bus :
                              (ctrl_trg_stop_bus[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_EDGE_FALLING) ? stop_trg_bus :
                              (ctrl_trg_stop_bus[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_EDGE_RISING ) ? stop_trg_bus : 1'b0;
        stop_trg_pulse_bus <= run_en_bus & stop_trg_en_bus & (
                              (ctrl_trg_stop_bus[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_LEVEL_HIGH  ) ? ({stop_trg_ff_bus,stop_trg_bus} == 2'b01) : 
                              (ctrl_trg_stop_bus[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_LEVEL_LOW   ) ? ({stop_trg_ff_bus,stop_trg_bus} == 2'b00) :
                              (ctrl_trg_stop_bus[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_EDGE_FALLING) ? ({stop_trg_ff_bus,stop_trg_bus} == 2'b10) :
                              (ctrl_trg_stop_bus[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_EDGE_RISING ) ? ({stop_trg_ff_bus,stop_trg_bus} == 2'b01) : 1'b0 );
        end
    end

    // MUX restart trigger @ clk_bus
    reg restart_trg_bus = 1'b0;
    reg restart_trg_en_bus = 1'b0;
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) begin
            restart_trg_bus    <= 1'b0;
            restart_trg_en_bus <= 1'b0;
        end
        else begin
            restart_trg_bus    <= ( ctrl_trg_restart_bus[CTRL_TRG_SRC_BITS-1:0] == CTRL_TRG_SRC_IN0 ) ? ext_in_bus[0] :
                                  ( ctrl_trg_restart_bus[CTRL_TRG_SRC_BITS-1:0] == CTRL_TRG_SRC_IN1 ) ? ext_in_bus[1] :
                                  ( ctrl_trg_restart_bus[CTRL_TRG_SRC_BITS-1:0] == CTRL_TRG_SRC_IN2 ) ? ext_in_bus[2] : 1'b0;
            restart_trg_en_bus <= ( ctrl_trg_restart_bus[CTRL_TRG_SRC_BITS-1:0] == CTRL_TRG_SRC_IN0 ) ? 1'b1 :
                                  ( ctrl_trg_restart_bus[CTRL_TRG_SRC_BITS-1:0] == CTRL_TRG_SRC_IN1 ) ? 1'b1 :
                                  ( ctrl_trg_restart_bus[CTRL_TRG_SRC_BITS-1:0] == CTRL_TRG_SRC_IN2 ) ? 1'b1 : 1'b0;
        end
    end
     
    // generate restart trigger positive edge pulse @ clk_bus
    reg restart_trg_ff_bus = 1'b0;
    reg restart_trg_pulse_bus = 1'b0;
    always @ ( posedge clk_bus ) begin
        if (reset_bus_n == 1'b0) begin
            restart_trg_ff_bus <= 1'b0;
            restart_trg_pulse_bus <= 1'b0;
        end
        else begin
        restart_trg_ff_bus    <= (ctrl_trg_restart_bus[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_LEVEL_HIGH  ) ? run_en_bus & restart_trg_en_bus & restart_trg_bus : 
                                 (ctrl_trg_restart_bus[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_LEVEL_LOW   ) ? run_en_bus & restart_trg_en_bus & ~restart_trg_bus :
                                 (ctrl_trg_restart_bus[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_EDGE_FALLING) ? restart_trg_bus :
                                 (ctrl_trg_restart_bus[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_EDGE_RISING ) ? restart_trg_bus : 1'b0;
        restart_trg_pulse_bus <= run_en_bus & restart_trg_en_bus & (
                                 (ctrl_trg_restart_bus[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_LEVEL_HIGH  ) ? ({restart_trg_ff_bus,restart_trg_bus} == 2'b01) : 
                                 (ctrl_trg_restart_bus[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_LEVEL_LOW   ) ? ({restart_trg_ff_bus,restart_trg_bus} == 2'b00) :
                                 (ctrl_trg_restart_bus[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_EDGE_FALLING) ? ({restart_trg_ff_bus,restart_trg_bus} == 2'b10) :
                                 (ctrl_trg_restart_bus[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_EDGE_RISING ) ? ({restart_trg_ff_bus,restart_trg_bus} == 2'b01) : 1'b0 );
        end
    end

	//////////////////////////////////////////////////////////////////////////////////
    // synchronize start trigger (former sync_in) @ clk_det

    // synchronize external inputs @ clk_bus
    // note: there is no way to ensure that these bits are synchronized with each other!
    // so if they are even coming from the same source they might have 1 cycle difference!
    // this means that same sources must have alternate trigger edges to work properly.
    wire [NUM_IN_BITS - 1 : 0] ext_in_det;
    generate
    for (genvar i = 0; i < NUM_IN_BITS; i = i + 1) begin : GEN_EXT_DET
        (* ASYNC_REG = "TRUE" *)
        reg [SYNC-1:0] ext_in_det_cdc;
        always @ ( posedge clk_det ) begin
            ext_in_det_cdc <= {ext_in_det_cdc[SYNC-2:0],ext_in[i]};
        end
        assign ext_in_det[i] = ext_in_det_cdc[SYNC-1];
    end
    endgenerate

    // run_en CDC from clock_bus to clock_det
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] run_en_cdc_det;    
    always @ ( posedge clk_det ) begin
        run_en_cdc_det <= {run_en_cdc_det[SYNC-2:0],run_en_bus};
    end
    wire run_en_det = run_en_cdc_det[SYNC-1];    

    // reset CDC from clock_bus to clock_det
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] reset_n_det_ff;    
    always @ ( posedge clk_det ) begin
        reset_n_det_ff <= {reset_n_det_ff[SYNC-2:0],reset_bus_n};
    end
    wire reset_det_n = reset_n_det_ff[SYNC-1];    

    wire [CTRL_TRG_DST_BITS - 1: 0] ctrl_trg_start_det;
    cdc # ( 
        .SYNC(SYNC), 
        .DATA_WIDTH(CTRL_TRG_DST_BITS), 
        .USE_OUT_READY("NO")
    )
    cdc_det (
        .in_clock(s00_axi_aclk),
        .in_reset_n(s00_axi_aresetn),
        .in_data(ctrl_trg[CTRL_TRG_DST_START+CTRL_TRG_DST_BITS-1 -: CTRL_TRG_DST_BITS]),
        .in_valid(ctrl_update[REG_CTRL_TRG]),
        .in_ready(),
        .out_clock(clk_det),
        .out_reset_n(reset_det_n),
        .out_data(ctrl_trg_start_det),
        .out_valid(),       // pulses clk_div is updated
        .out_ready(1'b1)                        // always ready
    ); 

    // MUX start_in trigger @ clk_det
    reg start_trg_det = 1'b0;
    reg start_trg_en_det = 1'b0;
    always @ ( posedge clk_det ) begin
        if ( reset_det_n == 1'b0 ) begin
            start_trg_det <= 1'b0;
            start_trg_en_det <= 1'b0;
        end
        else begin
            start_trg_det    <= ( ctrl_trg_start_det[CTRL_TRG_SRC_BITS-1:0] == CTRL_TRG_SRC_IN0 ) ? ext_in_det[0] :
                                ( ctrl_trg_start_det[CTRL_TRG_SRC_BITS-1:0] == CTRL_TRG_SRC_IN1 ) ? ext_in_det[1] :
                                ( ctrl_trg_start_det[CTRL_TRG_SRC_BITS-1:0] == CTRL_TRG_SRC_IN2 ) ? ext_in_det[2] : 1'b0;
            start_trg_en_det <= ( ctrl_trg_start_det[CTRL_TRG_SRC_BITS-1:0] == CTRL_TRG_SRC_IN0 ) ? 1'b1 :
                                ( ctrl_trg_start_det[CTRL_TRG_SRC_BITS-1:0] == CTRL_TRG_SRC_IN1 ) ? 1'b1 :
                                ( ctrl_trg_start_det[CTRL_TRG_SRC_BITS-1:0] == CTRL_TRG_SRC_IN2 ) ? 1'b1 : 1'b0;
        end
    end
         
    // generate start_trg positive edge pulse @ clk_det
    reg start_trg_ff_det = 1'b0;
    reg start_trg_pulse_det = 1'b0;
    reg start_trg_tgl_det = 1'b0;
    always @ ( posedge clk_det ) begin
        if (reset_det_n == 1'b0) begin
            start_trg_ff_det    <= 1'b0;
            start_trg_pulse_det <= 1'b0;
            start_trg_tgl_det   <= 1'b0;
        end
        else begin
        start_trg_ff_det    <= (ctrl_trg_start_det[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_LEVEL_HIGH  ) ? run_en_det & start_trg_en_det & start_trg_det : 
                               (ctrl_trg_start_det[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_LEVEL_LOW   ) ? run_en_det & start_trg_en_det & ~start_trg_det :
                               (ctrl_trg_start_det[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_EDGE_FALLING) ? start_trg_det :
                               (ctrl_trg_start_det[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_EDGE_RISING ) ? start_trg_det : 1'b0;
        start_trg_pulse_det <= run_en_det & start_trg_en_det & (
                               (ctrl_trg_start_det[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_LEVEL_HIGH  ) ? ({start_trg_ff_det,start_trg_det} == 2'b01) : 
                               (ctrl_trg_start_det[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_LEVEL_LOW   ) ? ({start_trg_ff_det,start_trg_det} == 2'b00) :
                               (ctrl_trg_start_det[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_EDGE_FALLING) ? ({start_trg_ff_det,start_trg_det} == 2'b10) :
                               (ctrl_trg_start_det[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_EDGE_RISING ) ? ({start_trg_ff_det,start_trg_det} == 2'b01) : 1'b0 );
        start_trg_tgl_det   <= run_en_det & start_trg_en_det & (
                               (ctrl_trg_start_det[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_LEVEL_HIGH  ) ? ({start_trg_ff_det,start_trg_det} == 2'b01) ? ~start_trg_tgl_det : start_trg_tgl_det : 
                               (ctrl_trg_start_det[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_LEVEL_LOW   ) ? ({start_trg_ff_det,start_trg_det} == 2'b00) ? ~start_trg_tgl_det : start_trg_tgl_det :
                               (ctrl_trg_start_det[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_EDGE_FALLING) ? ({start_trg_ff_det,start_trg_det} == 2'b10) ? ~start_trg_tgl_det : start_trg_tgl_det :
                               (ctrl_trg_start_det[CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_EDGE_RISING ) ? ({start_trg_ff_det,start_trg_det} == 2'b01) ? ~start_trg_tgl_det : start_trg_tgl_det : 1'b0 );
        end
    end

	//////////////////////////////////////////////////////////////////////////////////
    // synchronize strobe clock division and delay @ clk_bus
        
    wire strb_delay_reload; // pulses when strobe_delay is updated @ clk_bus
    
    // synchronized outputs
    wire [STRB_DELAY_BITS*NUM_STRB*2-1:0] strb_delay_bus;
    
    reg valid = 1'b0;
    wire ready;
    always @ ( posedge s00_axi_aclk ) begin
        if ( s00_axi_aresetn == 1'b0 ) valid <= 1'b0;
        else if ( ctrl_update[REG_STRB_DELAY] ) valid <= 1'b1;
        else if ( ready ) valid <= 1'b0;
        else valid <= valid;
    end
    // cdc
    cdc # ( 
        .SYNC(SYNC), 
        .DATA_WIDTH(2*NUM_STRB*STRB_DELAY_BITS), 
        .USE_OUT_READY("NO")
    )
    cdc_strb_delay (
        .in_clock(s00_axi_aclk),
        .in_reset_n(s00_axi_aresetn),
        .in_data(strb_delay[2*NUM_STRB*STRB_DELAY_BITS-1 : 0]),
        .in_valid(valid),
        .in_ready(ready),
        .out_clock(clk_bus),
        .out_reset_n(reset_bus_n),
        .out_data(strb_delay_bus),
        .out_valid(strb_delay_reload),
        .out_ready(1'b1)                        // always ready
    );    
    
	//////////////////////////////////////////////////////////////////////////////////
    // timing and auto-sync modules @ clk_bus 
    
    //                                      +-----------+-----------+-----------+
    //                                      |              reset                |
    //                                      +-----------+-----------+-----------+
    //                                                  |           |
    //                                       first data |           | error
    //                                                  |           +-----------------------+
    //                                                  |                                   |
    //                                      +-----------+-----------+-----------+           |
    //                                      |           svr_ready_bus           |           |
    //                                      +-----------+-----------+-----------+           |
    //                                                  |           |                       |
    //                                           run_en |           | error                 |
    //                                                  |           +-----------------------+
    //                                                  |                                   |
    //            as_en_bus = 1'b0                      |                 1'b1              |
    //                          +-----------------------+-------------------+               |
    //  start_trg_en_bus = 1'b0 | 1'b1                        1'b1          |     1'b0      |
    //          +---------------+---+                           +-----------+-------+       |
    //          |                   |                           |                   |       |
    //          |   +---------------+-------+       +-----------+-----------+       |       |
    //          |   |     wait start_trg    |       |     wait as_start     |       |       |
    //          |   +---------------+-------+       +-----------+-----------+       |       |
    //          |                   |                           |                   |       |
    //          +-------------------+---------------+-----------+-------------------+       |
    //                                              |                                       |
    //                                  +-----------+-----------+-----------+               |
    //                      +---------->|              run_bus              |               |
    //                      |           +-----------+-----------+-----------+               |
    //                      |                       |           |                           |
    //                      |     stop_trg_en_bus & |           | error                     |
    //                      |    stop_trg_pulse_bus |           +---------------------------+
    //                      |                       |                                       |
    //                      |           +-----------+-----------+-----------+               |
    //                      |           |              run_wait             |               |
    //                      |           +-----------+-----------+-----------+               |
    //                      |                       |           |                           |
    //                      |  restart_trg_en_bus & |           | error                     | 
    //                      | restart_trg_pulse_bus |           |                           |
    //                      |                       |           |                           |
    //                      +-----------------------+           +---------------------------+
    //                                                          |
    //                                  +-----------+-----------+-----------+
    //                                  |               error               |
    //                                  +-----------+-----------+-----------+
    // 
    // notes: 
    // - as_start_bus pulses for 1 clk_bus cycle after start trigger and sync_delay count
    // - run_... bits are control bits and not status bits
    
    // TODO: 
    // - a state machine would be more comprehensive? 
    wire as_start_bus;      // auto-sync start signal. pulses for 1 clk_bus cycle.
    reg run_bus;            // timer running
    reg run_bus_pulse;      // timer start running pulse 1 cycle, does not pulse at restart.
    reg run_wait;           // stop trigger active, wait for restart trigger
    reg run_start;          // start trigger recieved: wait for as_start_bus
    reg trg_start_bus   = 1'b0; // trigger start toggle bit 
    reg trg_stop_bus    = 1'b0; // trigger stop toggle bit
    reg trg_restart_bus = 1'b0; // trigger restart toggle bit
    always @ ( posedge clk_bus ) begin
        if ( reset_bus_n == 1'b0 ) begin
            run_start     <= 1'b0;
            run_bus       <= 1'b0;
            run_bus_pulse <= 1'b0;
            //run_or_wait   <= 1'b0;
            run_wait      <= 1'b0;
        end 
        else if ( end_bus ) begin // end state. wait until reset
            run_start     <= 1'b0;
            run_bus       <= 1'b0;
            run_bus_pulse <= 1'b0;
            //run_or_wait   <= 1'b0;
            run_wait      <= 1'b0;
        end
        else if ( run_wait ) begin // restart
            run_start     <= 1'b0;
            run_bus       <= restart_trg_en_bus ? restart_trg_pulse_bus & run_en_bus & svr_ready_bus & (~error_bus) : 1'b0;
            run_bus_pulse <= 1'b0;
            //run_or_wait   <= 1'b1;
            run_wait      <= restart_trg_en_bus ? (~restart_trg_pulse_bus) : 1'b1;
            trg_restart_bus <= ( restart_trg_en_bus & restart_trg_pulse_bus & run_en_bus & svr_ready_bus & (~error_bus) ) ? ~trg_restart_bus : trg_restart_bus;
        end 
        else if ( run_bus ) begin // running: wait for stop.
            run_start     <= 1'b0;
            run_bus       <= stop_trg_en_bus ? (~stop_trg_pulse_bus) & run_en_bus & svr_ready_bus & (~error_bus):
                                                                       run_en_bus & svr_ready_bus & (~error_bus);
            run_bus_pulse <= 1'b0;
            //run_or_wait   <= 1'b1;
            run_wait      <= stop_trg_en_bus ? stop_trg_pulse_bus : 1'b0;
            trg_stop_bus  <= ( stop_trg_en_bus & stop_trg_pulse_bus & run_en_bus & svr_ready_bus & (~error_bus) ) ? ~trg_stop_bus : trg_stop_bus;
        end
        else if ( run_start ) begin // wait for start trigger or/and sync_delay
            run_start     <= run_en_bus & svr_ready_bus & (~error_bus);
            run_bus       <= (as_en_bus ? as_start_bus : start_trg_pulse_bus) & run_en_bus & svr_ready_bus & (~error_bus);
            run_bus_pulse <= (as_en_bus ? as_start_bus : start_trg_pulse_bus) & run_en_bus & svr_ready_bus & (~error_bus);
            //run_or_wait   <= (as_en_bus ? as_start_bus : start_trg_pulse_bus) & run_en_bus & svr_ready_bus & (~error_bus);
            run_wait      <= 1'b0;
            trg_start_bus <= ((as_en_bus ? as_start_bus : start_trg_pulse_bus) & run_en_bus & svr_ready_bus & (~error_bus)) ? ~trg_start_bus : trg_start_bus;
        end
        else begin // not running: wait for run_en
            run_start     <= run_en_bus & svr_ready_bus & (~error_bus); // activate as module as soon as run_en bit is set
            run_bus       <= (as_en_bus | start_trg_en_bus) ? 1'b0 : run_en_bus & svr_ready_bus & (~error_bus);
            run_bus_pulse <= (as_en_bus | start_trg_en_bus) ? 1'b0 : run_en_bus & svr_ready_bus & (~error_bus);
            //run_or_wait   <= (as_en_bus | start_trg_en_bus) ? 1'b0 : run_en_bus & svr_ready_bus & (~error_bus);
            run_wait      <= 1'b0;
            trg_start_bus <= ( ~(as_en_bus | start_trg_en_bus) & run_en_bus & svr_ready_bus & (~error_bus) ) ? ~trg_start_bus : trg_start_bus;
        end
    end    

    // timing module = bus data generation
    wire [TIMEDATA_BITS - 1 : 0] out_data_bus;
    wire out_last_bus;
    wire out_valid_bus;
    wire out_ready_bus;
    dio24_timing # (
        .STREAM_DATA_BITS(TIMEDATA_BITS + 1),
        .BUS_DATA_BITS(BUS_DATA_BITS),
        .BUS_ADDR_BITS(BUS_ADDR_BITS),
        .BUS_ADDR_1_USE(BUS_ADDR_1_USE),
        .NUM_STRB(NUM_STRB),
        .REG_BITS(AXI_DATA_WIDTH),
        .CTRL_BITS(TIMING_CTRL_BITS),
        .STATUS_BITS(TIMING_STATUS_BITS),
        .CLK_DIV_BITS(CLK_DIV_BITS),
        .TRG_DIV_BITS(TRG_DIV_BITS),
        .STRB_DELAY_BITS(STRB_DELAY_BITS),
        .BIT_NOP(BIT_NOP),
        .BIT_TRST(BIT_TRST),
        .BIT_IRQ(BIT_IRQ),
        .BIT_STROBE(BIT_STROBE),
        .USE_STROBE(USE_STROBE),
        .SYNC(SYNC),
        .IRQ_FREQ_BITS(IRQ_FREQ_BITS)
    )
    timing (
        // clocks and reset
        .clk_bus(clk_bus),
        .reset_bus_n(reset_bus_n),
        // control bits
        .ctrl_bits({timing_ctrl_bus[TIMING_CTRL_BITS-1:1],run_bus}),
        .num_samples(num_samples_bus),
        .clk_div_bus(clk_div_bus),
        .trg_div_bus(trg_div_bus),
        .strb_delay_bus(strb_delay_bus),
        .ctrl_regs_reload(ctrl_regs_reload_bus),        // pulses when num_samples or clk_div is updated
        .strb_delay_reload(strb_delay_reload),          // pulses when strb_delay_bus is updated
        //.trg_start(trg_start_bus),
        //.as_start(as_start_bus),
        // status bits and board time & samples
        .status_bits(timing_status_bus),
        .board_time(board_time_bus),
        .board_samples(board_samples_bus),
        .board_time_ext(board_time_ext_bus),
        .board_samples_ext(board_samples_ext_bus),
        .status_update(), // not used
        // next data out of input buffer (not used)
        .next_data(),
        .next_reload(),
        // TX stream data input
        .in_data({in_last_bus,in_data_bus}),
        .in_valid(in_valid_bus),
        .in_ready(in_ready_bus),
        // RX stream data output
        .out_data({out_last_bus,out_data_bus}),
        .out_valid(out_valid_bus),
        .out_ready(out_ready_bus),
        // bus output
        .bus_data(bus_data),
        .bus_addr_0(bus_addr_0),
        .bus_addr_1(bus_addr_1),
        .bus_strb(bus_strb)
    );
        
    wire [4*AUTO_SYNC_TIME_BITS-1:0] sync_time_det;
    wire as_timeout_det;
    wire as_done_det;
    wire sync_out_bus;
    wire sync_mon_det;
    //wire sync_en_bus;
    auto_sync # (
        // pulse length + wait time
        .PULSE_LENGTH(AUTO_SYNC_PULSE_LENGTH),
        .PULSE_WAIT(AUTO_SYNC_PULSE_WAIT),
        .PULSE_NUM_MAX(AUTO_SYNC_MAX_PULSES),
        // auto-sync time bits
        .TIME_BITS(AUTO_SYNC_TIME_BITS),     
        // delay bits
        .DELAY_BITS(AUTO_SYNC_DELAY_BITS)
    )
    as
    (
        // clock and reset
        .clk_bus(clk_bus),
        .clk_det(clk_det),
        .reset_bus_n(reset_bus_n),
        .reset_det_n(reset_det_n),
        
        // control bits @ clk_bus
        //.as_en(as_en_bus),
        .as_trg_en(start_trg_en_bus), // wait for trigger, otherwise just generate sync_out
        //.as_prim(as_prim_bus),
        //.as_sync_wait(trg_start_en_bus),
        //.as_sync_wait(1'b0), // TODO: remove
        //.as_FET(as_FET_bus),
        .as_run_start(run_start),
        
        // status bits
        .as_active(as_active_bus),          // @ clk_bus
        .as_timeout(as_timeout_det),        // @ clk_det
        .as_done(as_done_det),              // @ clk_det
                
        // external auto-sync input and outputs
        .sync_out(sync_out_bus),        // @ clk_bus
        //.sync_en(sync_en_bus),          // @ clk_bus
        .sync_mon(sync_mon_det),        // @ clk_det
        .sync_in_tgl_bus(start_trg_tgl_bus),          // @ clk_bus
        .sync_in_tgl_det(start_trg_tgl_det),          // @ clk_det
                        
        // measured round-trip time {t1_PS,,t0_PS,t1,t0} and timeout @ clk_det
        .sync_time(sync_time_det),

        // sync delay time at clk_bus
        .sync_delay(sync_delay_bus),
        
        // auto-sync start signal. pulses for 1 clk_bus cycle.
        .as_start(as_start_bus)
        );
                
    // sync_time, timeout and done CDC from clock_det to clock_pclk = s00_axi_aclk
    wire [4*AUTO_SYNC_TIME_BITS-1:0] sync_time_axi;
    cdc # ( 
        .SYNC(SYNC), 
        .DATA_WIDTH(4*AUTO_SYNC_TIME_BITS + 1), 
        .USE_OUT_READY("NO")
    )
    cdc_out (
        .in_clock(clk_det),
        .in_reset_n(reset_det_n),
        .in_data({as_timeout_det,sync_time_det}),
        .in_valid(as_done_det),
        .in_ready(),
        .out_clock(s00_axi_aclk),
        .out_reset_n(reset_AXI_sw_n),
        .out_data({as_timeout,sync_time_axi}),
        .out_valid(as_done),// pulses when bits have been reloaded
        .out_ready(1'b1) // always ready
    );
    if (AXI_DATA_WIDTH > 4*AUTO_SYNC_TIME_BITS) begin
        assign sync_time = {{(AXI_DATA_WIDTH-4*AUTO_SYNC_TIME_BITS){1'b0}},sync_time_axi};
    end
    else begin
        assign sync_time = sync_time_axi;
    end

	//////////////////////////////////////////////////////////////////////////////////
    // multiplex and sync outputs @ s00_axi_aclk 

    // synchronize sync_out at s00_axi_aclk
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] sync_out_AXI_cdc;
    always @ ( posedge s00_axi_aclk ) begin
        sync_out_AXI_cdc <= {sync_out_AXI_cdc[SYNC-2:0],sync_out_bus};
    end
    wire sync_out_AXI = sync_out_AXI_cdc[SYNC-1];

    // synchronize sync_mon at s00_axi_aclk
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] sync_mon_AXI_cdc;
    always @ ( posedge s00_axi_aclk ) begin
        sync_mon_AXI_cdc <= {sync_mon_AXI_cdc[SYNC-2:0],sync_mon_det};
    end
    wire sync_mon_AXI = sync_mon_AXI_cdc[SYNC-1];

    // synchronize trg_start at s00_axi_aclk
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] trg_start_AXI_cdc;
    always @ ( posedge s00_axi_aclk ) begin
        trg_start_AXI_cdc <= {trg_start_AXI_cdc[SYNC-2:0],trg_start_bus};
    end
    wire trg_start_AXI = trg_start_AXI_cdc[SYNC-1];

    // synchronize trg_stop at s00_axi_aclk
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] trg_stop_AXI_cdc;
    always @ ( posedge s00_axi_aclk ) begin
        trg_stop_AXI_cdc <= {trg_stop_AXI_cdc[SYNC-2:0],trg_stop_bus};
    end
    wire trg_stop_AXI = trg_stop_AXI_cdc[SYNC-1];

    // synchronize trg_restart at s00_axi_aclk
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] trg_restart_AXI_cdc;
    always @ ( posedge s00_axi_aclk ) begin
        trg_restart_AXI_cdc <= {trg_restart_AXI_cdc[SYNC-2:0],trg_restart_bus};
    end
    wire trg_restart_AXI = trg_restart_AXI_cdc[SYNC-1];

    /* synchronize sync_en at s00_axi_aclk. replaced by as_active_bus -> CDC as_active @ s00_axi_aclk
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] sync_en_AXI_cdc;
    always @ ( posedge s00_axi_aclk ) begin
        sync_en_AXI_cdc <= {sync_en_AXI_cdc[SYNC-2:0],sync_en_bus};
    end
    wire sync_en_AXI = sync_en_AXI_cdc[SYNC-1];*/
    wire sync_en_AXI = as_active;
        
    // assign control_out register @ s00_axi_aclk
    wire [CTRL_OUT_DST_BITS-1:0] ctrl_out0 = ctrl_out[CTRL_OUT_DST_OUT0    +CTRL_OUT_DST_BITS-1 -: CTRL_OUT_DST_BITS];
    wire [CTRL_OUT_DST_BITS-1:0] ctrl_out1 = ctrl_out[CTRL_OUT_DST_OUT1    +CTRL_OUT_DST_BITS-1 -: CTRL_OUT_DST_BITS];
    wire [CTRL_OUT_DST_BITS-1:0] ctrl_out2 = ctrl_out[CTRL_OUT_DST_OUT2    +CTRL_OUT_DST_BITS-1 -: CTRL_OUT_DST_BITS];
    wire [CTRL_OUT_DST_BITS-1:0] ctrl_out3 = ctrl_out[CTRL_OUT_DST_BUS_EN_0+CTRL_OUT_DST_BITS-1 -: CTRL_OUT_DST_BITS];
    wire [CTRL_OUT_DST_BITS-1:0] ctrl_out4 = ctrl_out[CTRL_OUT_DST_BUS_EN_1+CTRL_OUT_DST_BITS-1 -: CTRL_OUT_DST_BITS];

    // exteranl outputs @ s00_axi_aclk
    // at the moment these are not directly reset with software reset.
    // TODO: change to clk_bus?
    reg [2:0] ext_out_ff = 3'b000;
    reg [1:0] bus_en_ff = 2'b00;
    always @ ( posedge s00_axi_aclk ) begin
        if ( s00_axi_aresetn == 1'b0 ) begin
            ext_out_ff <= 3'b000;
            bus_en_ff  <= 2'b00;
        end
        else begin
            ext_out_ff[0] <= ( ctrl_out0[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_SYNC_OUT    ) ? (( ctrl_out0[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~sync_out_AXI       : sync_out_AXI       ) :
                             ( ctrl_out0[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_SYNC_EN     ) ? (( ctrl_out0[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~sync_en_AXI        : sync_en_AXI        ) : 
                             ( ctrl_out0[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_SYNC_MON    ) ? (( ctrl_out0[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~sync_mon_AXI       : sync_mon_AXI       ) :
                             ( ctrl_out0[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_CLK_LOST    ) ? (( ctrl_out0[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~clk_ext_lost       : clk_ext_lost       ) : 
                             ( ctrl_out0[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_ERROR       ) ? (( ctrl_out0[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~error              : error              ) :
                             ( ctrl_out0[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_RUN         ) ? (( ctrl_out0[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~status_run         : status_run         ) :
                             ( ctrl_out0[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_WAIT        ) ? (( ctrl_out0[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~status_wait        : status_wait        ) :
                             ( ctrl_out0[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_READY       ) ? (( ctrl_out0[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~status_ready       : status_ready       ) :
                             ( ctrl_out0[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_RESTART     ) ? (( ctrl_out0[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~status_restart     : status_restart     ) : 
                             ( ctrl_out0[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_TRG_START   ) ? (( ctrl_out0[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~trg_start_AXI      : trg_start_AXI      ) :
                             ( ctrl_out0[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_TRG_STOP    ) ? (( ctrl_out0[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~trg_stop_AXI       : trg_stop_AXI       ) :
                             ( ctrl_out0[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_TRG_RESTART ) ? (( ctrl_out0[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~trg_restart_AXI    : trg_restart_AXI    ) :
                                                                                                   ( ctrl_out0[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? 1'b0 : 1'b1;
            ext_out_ff[1] <= ( ctrl_out1[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_SYNC_OUT    ) ? (( ctrl_out1[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~sync_out_AXI       : sync_out_AXI       ) :
                             ( ctrl_out1[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_SYNC_EN     ) ? (( ctrl_out1[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~sync_en_AXI        : sync_en_AXI        ) : 
                             ( ctrl_out1[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_SYNC_MON    ) ? (( ctrl_out1[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~sync_mon_AXI       : sync_mon_AXI       ) :
                             ( ctrl_out1[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_CLK_LOST    ) ? (( ctrl_out1[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~clk_ext_lost       : clk_ext_lost       ) : 
                             ( ctrl_out1[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_ERROR       ) ? (( ctrl_out1[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~error              : error              ) :
                             ( ctrl_out1[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_RUN         ) ? (( ctrl_out1[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~status_run         : status_run         ) :
                             ( ctrl_out1[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_WAIT        ) ? (( ctrl_out1[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~status_wait        : status_wait        ) :
                             ( ctrl_out1[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_READY       ) ? (( ctrl_out1[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~status_ready       : status_ready       ) :
                             ( ctrl_out1[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_RESTART     ) ? (( ctrl_out1[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~status_restart     : status_restart     ) :
                             ( ctrl_out1[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_TRG_START   ) ? (( ctrl_out1[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~trg_start_AXI      : trg_start_AXI      ) :
                             ( ctrl_out1[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_TRG_STOP    ) ? (( ctrl_out1[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~trg_stop_AXI       : trg_stop_AXI       ) :
                             ( ctrl_out1[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_TRG_RESTART ) ? (( ctrl_out1[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~trg_restart_AXI    : trg_restart_AXI    ) :
                                                                                                   ( ctrl_out1[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? 1'b0 : 1'b1;
            ext_out_ff[2] <= ( ctrl_out2[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_SYNC_OUT    ) ? (( ctrl_out2[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~sync_out_AXI       : sync_out_AXI       ) :
                             ( ctrl_out2[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_SYNC_EN     ) ? (( ctrl_out2[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~sync_en_AXI        : sync_en_AXI        ) : 
                             ( ctrl_out2[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_SYNC_MON    ) ? (( ctrl_out2[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~sync_mon_AXI       : sync_mon_AXI       ) :
                             ( ctrl_out2[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_CLK_LOST    ) ? (( ctrl_out2[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~clk_ext_lost       : clk_ext_lost       ) : 
                             ( ctrl_out2[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_ERROR       ) ? (( ctrl_out2[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~error              : error              ) :
                             ( ctrl_out2[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_RUN         ) ? (( ctrl_out2[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~status_run         : status_run         ) :
                             ( ctrl_out2[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_WAIT        ) ? (( ctrl_out2[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~status_wait        : status_wait        ) :
                             ( ctrl_out2[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_READY       ) ? (( ctrl_out2[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~status_ready       : status_ready       ) :
                             ( ctrl_out2[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_RESTART     ) ? (( ctrl_out2[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~status_restart     : status_restart     ) :
                             ( ctrl_out2[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_TRG_START   ) ? (( ctrl_out2[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~trg_start_AXI      : trg_start_AXI      ) :
                             ( ctrl_out2[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_TRG_STOP    ) ? (( ctrl_out2[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~trg_stop_AXI       : trg_stop_AXI       ) :
                             ( ctrl_out2[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_TRG_RESTART ) ? (( ctrl_out2[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~trg_restart_AXI    : trg_restart_AXI    ) :
                                                                                                   ( ctrl_out2[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? 1'b0 : 1'b1;
            bus_en_ff[0]  <= ( ctrl_out3[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_SYNC_OUT    ) ? (( ctrl_out3[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~sync_out_AXI       : sync_out_AXI       ) :
                             ( ctrl_out3[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_SYNC_EN     ) ? (( ctrl_out3[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~sync_en_AXI        : sync_en_AXI        ) : 
                             ( ctrl_out3[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_SYNC_MON    ) ? (( ctrl_out3[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~sync_mon_AXI       : sync_mon_AXI       ) :
                             ( ctrl_out3[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_CLK_LOST    ) ? (( ctrl_out3[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~clk_ext_lost       : clk_ext_lost       ) : 
                             ( ctrl_out3[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_ERROR       ) ? (( ctrl_out3[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~error              : error              ) :
                             ( ctrl_out3[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_RUN         ) ? (( ctrl_out3[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~status_run         : status_run         ) :
                             ( ctrl_out3[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_WAIT        ) ? (( ctrl_out3[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~status_wait        : status_wait        ) :
                             ( ctrl_out3[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_READY       ) ? (( ctrl_out3[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~status_ready       : status_ready       ) :
                             ( ctrl_out3[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_RESTART     ) ? (( ctrl_out3[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~status_restart     : status_restart     ) :
                             ( ctrl_out3[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_TRG_START   ) ? (( ctrl_out3[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~trg_start_AXI      : trg_start_AXI      ) :
                             ( ctrl_out3[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_TRG_STOP    ) ? (( ctrl_out3[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~trg_stop_AXI       : trg_stop_AXI       ) :
                             ( ctrl_out3[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_TRG_RESTART ) ? (( ctrl_out3[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~trg_restart_AXI    : trg_restart_AXI    ) :
                                                                                                   ( ctrl_out3[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? 1'b0 : 1'b1;
            bus_en_ff[1]  <= ( ctrl_out4[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_SYNC_OUT    ) ? (( ctrl_out4[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~sync_out_AXI       : sync_out_AXI       ) :
                             ( ctrl_out4[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_SYNC_EN     ) ? (( ctrl_out4[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~sync_en_AXI        : sync_en_AXI        ) : 
                             ( ctrl_out4[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_SYNC_MON    ) ? (( ctrl_out4[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~sync_mon_AXI       : sync_mon_AXI       ) :
                             ( ctrl_out4[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_CLK_LOST    ) ? (( ctrl_out4[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~clk_ext_lost       : clk_ext_lost       ) : 
                             ( ctrl_out4[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_ERROR       ) ? (( ctrl_out4[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~error              : error              ) :
                             ( ctrl_out4[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_RUN         ) ? (( ctrl_out4[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~status_run         : status_run         ) :
                             ( ctrl_out4[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_WAIT        ) ? (( ctrl_out4[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~status_wait        : status_wait        ) :
                             ( ctrl_out4[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_READY       ) ? (( ctrl_out4[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~status_ready       : status_ready       ) :
                             ( ctrl_out4[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_RESTART     ) ? (( ctrl_out4[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~status_restart     : status_restart     ) :
                             ( ctrl_out4[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_TRG_START   ) ? (( ctrl_out4[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~trg_start_AXI      : trg_start_AXI      ) :
                             ( ctrl_out4[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_TRG_STOP    ) ? (( ctrl_out4[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~trg_stop_AXI       : trg_stop_AXI       ) :
                             ( ctrl_out4[CTRL_OUT_SRC_BITS-1 : 0] == CTRL_OUT_SRC_TRG_RESTART ) ? (( ctrl_out4[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? ~trg_restart_AXI    : trg_restart_AXI    ) :
                                                                                                   ( ctrl_out4[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS] == CTRL_OUT_LEVEL_LOW ) ? 1'b0 : 1'b1;
end
    end
    assign ext_out = ext_out_ff;
    
    if (NUM_BUS_EN == 1) begin
        assign bus_en[0]  = bus_en_ff[0];
    end
    else begin
        assign bus_en  = bus_en_ff;
    end
    
    
	//////////////////////////////////////////////////////////////////////////////////
    // RX FIFO @ clk_bus -> AXIS_out_aclk 
    
	wire [TIMEDATA_BITS - 1 : 0] out_data_RX;        
	wire out_last_RX;
    wire out_ready_RX;
    wire out_valid_RX;
    dio24_FIFO # (
        .STREAM_DATA_WIDTH(TIMEDATA_BITS + 1),
        .FIFO_DEPTH(RX_FIFO_DEPTH),
        .OUT_ZERO("FALSE")
    )
    RX_FIFO
    (
        .in_clock(clk_bus),
        .in_reset_n(reset_bus_n),
        .in_data({out_last_bus,out_data_bus}),
        .in_ready(out_ready_bus),
        .in_valid(out_valid_bus),
        .out_clock(AXIS_out_aclk),
        .out_reset_n(reset_out_stream_n),
        .out_data({out_last_RX,out_data_RX}),
        .out_valid(out_valid_RX),
        .out_ready(out_ready_RX)
    );
   
	//////////////////////////////////////////////////////////////////////////////////
	// output AXI stream @ AXIS_out_clk

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
           .clock(AXIS_out_aclk),
           .reset_n(reset_out_stream_n),
           // error keep
           .error_keep(error_keep_stream[2]),
           // data input
           .in_data(out_data_smpl),
           .in_last(out_last_smpl),
           .in_keep({(BITS_PER_SAMPLE/8){1'b1}}), // all BYTES are used
           .in_valid(out_valid_smpl),
           .in_ready(out_ready_smpl),
           // data output
           .out_data(AXIS_out_tdata),
           .out_last(AXIS_out_tlast),
           .out_keep(AXIS_out_tkeep),
           .out_valid(AXIS_out_tvalid),
           .out_ready(AXIS_out_tready)
       );
    end
    else begin
       assign error_keep_stream[2] = 1'b0;
       assign out_data = out_data_smpl;
       assign out_last = out_last_smpl;
       assign out_keep = {(BITS_PER_SAMPLE/8){1'b1}};
       assign out_valid = out_valid_smpl;
       assign out_ready_smpl = AXIS_out_tready;
    end
    
endmodule
