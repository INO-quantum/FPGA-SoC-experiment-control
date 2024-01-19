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
// last change 2023/01/20 by Andi
//////////////////////////////////////////////////////////////////////////////////

	module dio24 #
	(
	    // user-provided version and info register content
        parameter integer VERSION               = 32'h0000_0000, // version register 
        parameter integer INFO                  = 32'h0000_0000,  // info  register

	    // AXI stream bus
        parameter integer STREAM_DATA_WIDTH  = 128,      // no limits
        parameter integer BITS_PER_SAMPLE  = 64,        // 64 (2 ports) or 96 (4 ports)
	
		// AXI Lite slave bus
        parameter integer AXI_DATA_WIDTH = 32,      // must be 32
        parameter integer AXI_ADDR_WIDTH = 7,       // 7: 2^7/4 = 32 registers
        
        // I/O bits
        parameter integer NUM_IN_BITS = 3,          // number of external inputs
        parameter integer NUM_OUT_BITS = 3,         // number of external outputs
                
        // LEDs and buttons 
        parameter integer NUM_BUTTONS = 2,              // must be 2
        parameter integer NUM_LED_RED = 2,              // must be 2
        parameter integer NUM_LED_GREEN = 3,            // must be 3
        parameter integer NUM_LED_BLUE = 2,             // must be 2
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

        // bus data and address bits without strobe bit
        parameter integer BUS_DATA_BITS = 16,       // 16
        parameter integer BUS_ADDR_BITS = 7,        // 7
        parameter         BUS_ADDR_1_USE = "ADDR0", // "ADDR0" = same as bus_addr_0, otherwise set to 0.
        //parameter         BUS_EN_0       = "LOW",   // "LOW", "HIGH" or "ACTIVE" = always low, high or changing state when running
        //parameter         BUS_EN_1       = "LOW",   // "LOW", "HIGH" or "ACTIVE" = always low, high or changing state when running
        
        // special data bits. they are not output on bus.
        parameter integer BIT_NOP = 31,             // 31. when set data is not output on bus, but time is still running,
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
        input wire  clk_bus,                        // main clock, typically PL clock, can be locked to external clock [100MHz]
        input wire  clk_det,                        // clk_bus + phase shift phi_det [100MHz]
        input wire  clk_pwm,                        // slow clock for PWM of LEDs [10MHz]

        // FPGA board buttons and RGB LEDs
        input wire [NUM_BUTTONS-1:0] buttons_in,    // async
        output wire [NUM_LED_RED-1:0]   led_red,    // @ clk_AXI
        output wire [NUM_LED_GREEN-1:0] led_green,  // @ clk_AXI
        output wire [NUM_LED_BLUE-1:0]  led_blue,   // @ clk_AXI
        
        // buffer board external clock control
        input wire clk_ext_locked,                  // assumed not synchronized to any clock
        input wire clk_mux_locked,                  // assumed not synchronized to any clock
        output wire clk_ext_sel,                    // @ clk_AXI

        // rack data bus output @ clk_bus
        output wire [1:0] bus_en,
        output wire [BUS_DATA_BITS-1:0] bus_data,
        output wire [BUS_ADDR_BITS-1:0] bus_addr_0,
        output wire [BUS_ADDR_BITS-1:0] bus_addr_1,
        // strobe output at phase shifted clk_bus x2
        output wire bus_strb_0,
        output wire bus_strb_1,
        
        // irq I/O @ clk_fast
        input wire irq_TX,
        input wire irq_RX,
        output wire irq_FPGA,
        
        // external inputs
        input wire [NUM_IN_BITS-1:0] ext_in,
        
        // external outputs
        output wire [NUM_OUT_BITS-1:0] ext_out,
        
        // dynamic phase shift of external clock input and detector clock @ clk_AXI 
        input wire ps_done_ext,
        output wire ps_en_ext,
        output wire ps_inc_ext,
        input wire ps_done_det,
        output wire ps_en_det,
        output wire ps_inc_det,

        output wire reset_AXI_sw_n,                 // @ clk_AXI, hardware + software reset output for clock Wizards

		// AXI Lite Slave Bus Interface S00_AXI @ clk_AXI
        AXI_LITE_if.sink axi_in,

		// AXI stream data input (from DMA stream master @ clk_fast)
        AXI_stream.sink     axis_in,

		// AXI stream data output (to DMA stream slave @ clk_fast)
        AXI_stream.source   axis_out

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

    assign axis_out.TDATA  = axis_in.TDATA;
    assign axis_out.TKEEP  = axis_in.TKEEP;
    assign axis_out.TLAST  = axis_in.TLAST;
    assign axis_out.TVALID = axis_in.TVALID;
    assign axis_out.TREADY = axis_in.TREADY;


    assign led_red   = {NUM_LED_RED{1'b0}};
    assign led_green = {NUM_LED_GREEN{1'b0}};
    assign led_blue  = {NUM_LED_BLUE{1'b0}};
    
    assign clk_ext_sel = 1'b0;

    assign bus_en = 2'b0;
    assign bus_data = {BUS_DATA_BITS{1'b0}};
    assign bus_addr_0 = {BUS_ADDR_BITS{1'b0}};
    assign bys_addr_1 = {BUS_ADDR_BITS{1'b0}};
    assign bus_strb_0 = 1'b0;
    assign bus_strb_1 = 1'b0;
    
    assign irq_FPGA = 1'b0;
    
    assign ext_out = {NUM_OUT_BITS{1'b0}};
    
    assign ps_en_ext = 1'b0;
    assign ps_inc_ext = 1'b0;
    assign ps_en_det = 1'b0;
    assign ps_inc_det = 1'b0;

    assign reset_AXI_sw_n = 1'b1;
    
endmodule
