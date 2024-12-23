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
// - clk_slow = slow data/sample clock for timing module
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
// last change 2024/12/4 by Andi (24<<9+12<<5+4=0x3184)
//////////////////////////////////////////////////////////////////////////////////

    module dio24 (
        clk_bus,
        clk_det,
        clk_pwm,
        reset_AXI_sw_n,

        buttons_in,

        led_red,
        led_green,
        led_blue,

        clk_ext_locked,
        clk_mux_locked,
        clk_ext_sel,

        bus_en,
        bus_data,
        bus_addr_0,
        bus_addr_1,
        bus_strb,       
        
        irq_TX,
        irq_RX,
        irq_FPGA,
        
        ext_in,
        ext_out,
        
        ps_done_ext,
        ps_en_ext,
        ps_inc_ext,
        ps_done_det,
        ps_en_det,
        ps_inc_det,
        
        AXI_aclk,
        AXI_aresetn,
        AXI_awaddr,
        AXI_awprot,
        AXI_awvalid,
        AXI_awready,
        AXI_wdata,
        AXI_wstrb,
        AXI_wvalid,
        AXI_wready,
        AXI_bresp,
        AXI_bvalid,
        AXI_bready,
        AXI_araddr,
        AXI_arprot,
        AXI_arvalid,
        AXI_arready,
        AXI_rdata,
        AXI_rresp,
        AXI_rvalid,
        AXI_rready,

        AXIS_in_aclk,
        AXIS_in_aresetn,
        AXIS_in_tdata,
        AXIS_in_tlast,
        AXIS_in_tready,
        AXIS_in_tvalid,
        AXIS_in_tkeep,

        AXIS_out_aclk,
        AXIS_out_aresetn,
        AXIS_out_tdata,
        AXIS_out_tlast,
        AXIS_out_tready,
        AXIS_out_tvalid,
        AXIS_out_tkeep
    
    );
    
    //////////////////////////////////////////////////////////////////////////////////    
    // parameters
    
    // register definitions
    `include "reg_params.vh"
    
    // user-provided version and info register content
    parameter integer VERSION               = 32'h0104_3183; // version register 0xMM.mm_(year-2000)<<9+month<<5+day 
    parameter integer INFO                  = 32'h0000_00c0; // info  register, 0xc0 = Cora-Z7-07s

    // AXI stream bus
    parameter integer STREAM_DATA_WIDTH     = 64;       // must be 64

    // AXI Lite slave bus
    parameter integer AXI_DATA_WIDTH        = 32;       // must be 32
    parameter integer AXI_ADDR_WIDTH        = 8;        // 8: 2^8/4 = 64 registers

    // I/O bits
    parameter integer NUM_IN                = 3;        // number of external inputs
    parameter integer NUM_OUT               = 3;        // number of external outputs

    // bus data and address bits without strobe bit
    parameter integer BUS_DATA_BITS         = 16;       // 16
    parameter integer BUS_ADDR_BITS         = 7;        // 7 (Florence) or 8 (Innsbruck)
    parameter integer NUM_STRB              = 2;        // number of bits for bus_strb (1 or 2)
    parameter integer NUM_BUS_EN            = 2;        // number of bits for bus_en (1 or 2)
    parameter integer BUS_RESET             = 0;        // 0 = keep bus after end at last state, otherwise reset to zero.
                        
    // second address bits selection. TODO: select by in_ctrl register
    parameter         BUS_ADDR_1_USE = "ZERO";    // "ZERO"/"ADDR0"/"DATA_HIGH" = low / same as bus_addr_0, data[31:24] 

    // LEDs and buttons 
    parameter integer NUM_BUTTONS           = 2;        // must be 2
    parameter integer NUM_LED_RED           = 2;        // must be 2
    parameter integer NUM_LED_GREEN         = 2;        // must be 2
    parameter integer NUM_LED_BLUE          = 2;        // must be 2
    parameter         INV_RED               = 2'b00;    // bit for each LED
    parameter         INV_GREEN             = 2'b00;    // bit for each LED
    parameter         INV_BLUE              = 2'b00;    // bit for each LED
    // bits used for blinking leds ON-time: 1=50%, 2=25%, 3=12.5%, 4=6.25%
    parameter integer LED_BLINK_ON          = 3;
    // bits used for blinking leds
    parameter integer LED_SLOW              = 26;       // blink slow
    parameter integer LED_FAST              = 24;       // blink fast (1 <= LED_FAST < LED_SLOW)
    // bits used for PWM dimming of leds. 0 = no dimming.
    parameter integer LED_DIM_LOW           = 8;        // dim level low (< LED_SLOW)
    parameter integer LED_DIM_HIGH          = 6;        // dim level high (< LED_SLOW)
    parameter integer LED_BRIGHT_LOW        = 1;        // bright level low (< LED_SLOW)
    parameter integer LED_BRIGHT_HIGH       = 1;        // bright level high (1 <= LED_BRIGHT_HIGH < LED_SLOW)
    
    // data and time bits
    parameter integer TIME_BITS             = 32;       // must be 32
    parameter integer TIME_START            = 0;        // 0
    parameter integer DATA_BITS             = 32;       // must be 32
    parameter integer DATA_START_64         = 32;       // 32
    parameter integer DATA_START_96_0       = 32;       // 32
    parameter integer DATA_START_96_1       = 64;       // 64
    parameter integer CLK_DIV_BITS          = 8;        // 8: clock divider = 1-255

    // bits for waiting time for secondary boards        
    parameter integer SYNC_DELAY_BITS       = 10;       // 10
    
    // auto-sync. TODO: not used anymore
    parameter integer AUTO_SYNC_PULSE_LENGTH = 3;               // 2 = 40ns @ 50MHz 
    parameter integer AUTO_SYNC_PULSE_WAIT   = 5;               // 3 = 60ns @ 50MHz, wait time after pulse
    parameter integer AUTO_SYNC_MAX_PULSES   = 2;               // 2 
    parameter integer AUTO_SYNC_TIME_BITS    = 8;               // 8
    parameter integer AUTO_SYNC_PHASE_BITS   = 12;              // 12     

    // synchronization stages
    parameter integer SYNC = 2;                 // internal 2-3 (2)
    parameter integer SYNC_EXT = 3;             // ext_in   2-3 (3)

    // irq_FPGA frequency
    parameter integer IRQ_FREQ_BITS = 21;       // 21 = 12-24Hz for 100MHz clk_bus
            
    // minimum number of contiguous cycles until lock lost error is raised. 
    parameter integer ERROR_LOCK_DELAY      = 5;

    // TX and RX FIFO
    parameter integer TX_FIFO_DEPTH         = 8192;
    parameter integer RX_FIFO_DEPTH         = 8192;

    //////////////////////////////////////////////////////////////////////////////////
    // ports

    // clocks and reset
    //input wire  clk_stream,                   // PL clock with AXI stream data from PS [100MHz]
    input wire  clk_bus;                        // main clock, typically PL clock, can be locked to external clock [100MHz]
    input wire  clk_det;                        // clk_bus + phase shift phi_det [100MHz]
    input wire  clk_pwm;                        // slow clock for PWM of LEDs [10MHz]

    // AXI Lite interface hardware + software reset output for clock Wizards
    output wire reset_AXI_sw_n;                 // @ AXI_aclk
    
    // FPGA board buttons and RGB LEDs
    input  wire [NUM_BUTTONS-1:0]   buttons_in; // async
    output wire [NUM_LED_RED-1:0]   led_red;    // @ AXI_aclk
    output wire [NUM_LED_GREEN-1:0] led_green;  // @ AXI_aclk
    output wire [NUM_LED_BLUE-1:0]  led_blue;   // @ AXI_aclk
    
    // buffer board external clock control
    input  wire clk_ext_locked;                 // assumed not synchronized to any clock
    input  wire clk_mux_locked;                 // assumed not synchronized to any clock
    output wire clk_ext_sel;                    // @ AXI_aclk

    // rack data bus output @ clk_bus
    output wire [NUM_BUS_EN   -1:0] bus_en;
    output wire [BUS_DATA_BITS-1:0] bus_data;
    output wire [BUS_ADDR_BITS-1:0] bus_addr_0;
    output wire [BUS_ADDR_BITS-1:0] bus_addr_1;
    output wire [NUM_STRB     -1:0] bus_strb;       
    
    // irq I/O @ AXI_aclk
    input  wire irq_TX;
    input  wire irq_RX;
    output wire irq_FPGA;
    
    // external I/O
    input  wire [NUM_IN -1:0] ext_in;
    output wire [NUM_OUT-1:0] ext_out;
    
    // dynamic phase shift of external clock input and detector clock @ AXI_aclk 
    input  wire ps_done_ext;
    output wire ps_en_ext;
    output wire ps_inc_ext;
    input  wire ps_done_det;
    output wire ps_en_det;
    output wire ps_inc_det;

    // AXI Lite Slave Bus Interface @ AXI_aclk
    input  wire                            AXI_aclk;
    input  wire                            AXI_aresetn;
    input  wire [AXI_ADDR_WIDTH-1 : 0]     AXI_awaddr;
    input  wire [2 : 0]                    AXI_awprot;
    input  wire                            AXI_awvalid;
    output wire                            AXI_awready;
    input  wire [AXI_DATA_WIDTH-1 : 0]     AXI_wdata;
    input  wire [(AXI_DATA_WIDTH/8)-1 : 0] AXI_wstrb;
    input  wire                            AXI_wvalid;
    output wire                            AXI_wready;
    output wire [1 : 0]                    AXI_bresp;
    output wire                            AXI_bvalid;
    input  wire                            AXI_bready;
    input  wire [AXI_ADDR_WIDTH-1 : 0]     AXI_araddr;
    input  wire [2 : 0]                    AXI_arprot;
    input  wire                            AXI_arvalid;
    output wire                            AXI_arready;
    output wire [AXI_DATA_WIDTH-1 : 0]     AXI_rdata;
    output wire [1 : 0]                    AXI_rresp;
    output wire                            AXI_rvalid;
    input  wire                            AXI_rready;

    // AXI stream data input (from DMA stream master @ AXIS_in_aclk)
    input  wire                            AXIS_in_aclk;
    input  wire                            AXIS_in_aresetn;
    input  wire [STREAM_DATA_WIDTH-1 : 0]  AXIS_in_tdata;
    input  wire                            AXIS_in_tlast;
    output wire                            AXIS_in_tready;
    input  wire                            AXIS_in_tvalid;
    input  wire [(STREAM_DATA_WIDTH/8)-1 : 0] AXIS_in_tkeep;

    // AXI stream data output (to DMA stream slave @ AXIS_out_aclk)
    input  wire                            AXIS_out_aclk;
    input  wire                            AXIS_out_aresetn;
    output wire [STREAM_DATA_WIDTH-1 : 0]  AXIS_out_tdata;
    output wire                            AXIS_out_tlast;
    input  wire                            AXIS_out_tready;
    output wire                            AXIS_out_tvalid;
    output wire [(STREAM_DATA_WIDTH/8)-1 : 0] AXIS_out_tkeep;

    //////////////////////////////////////////////////////////////////////////////////    
    // helper functions
    
    // returns ceiling of the log base 2 of bd.
    // see axi_stream_master.v example from Xilinx
    // equivalent to $clog2 in SystemVerilog
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
    
    // fixed number of selectable strobes in ctrl_out_mux
    localparam integer NUM_STRB_CONT = 2;   // must be >= NUM_STRB

    //////////////////////////////////////////////////////////////////////////////////    
    // global reset @ AXI_aclk
    
    // generate reset_AXI_sw_n signal @ AXI_aclk
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
    // UPDATE: clock locked are not anymore used for reset condition. electrical spikes which unlocked clock caused reset! 
    localparam integer RESET_BITS = 7; // set long enough such that slowest clock is reset! 
    localparam integer RESET_FULL = {RESET_BITS{1'b1}};
    localparam integer RESET_HALF = {1'b0,{(RESET_BITS-1){1'b1}}};
    reg [RESET_BITS-1:0] reset_cnt = 0;
    reg reset_AXI_sw_n_ff = 1'b1;
    reg reset_AXI_active_n = 1'b1;
    wire reset_sw_axi;
    wire clk_mux_locked_axi;
    always @ ( posedge AXI_aclk ) begin
        if ( ( AXI_aresetn == 1'b0 ) || ( reset_sw_axi == 1'b1 ) )  begin //|| ( (ext_clk_en & reset_AXI_sw_n_ff & (~clk_ext_sel)) == 1'b1 )) begin // reset condition
            reset_cnt <= RESET_FULL;
            reset_AXI_sw_n_ff <= 1'b0;
            reset_AXI_active_n <= 1'b0;
        end
        else if ( reset_cnt > RESET_HALF ) begin // reset condition released but keep clock wizards in reset
            reset_cnt <= reset_cnt - 1;
            reset_AXI_sw_n_ff <= 1'b0;
            reset_AXI_active_n <= 1'b0;
        end
        else if ( (reset_cnt > 0) && (clk_mux_locked_axi == 1'b0) ) begin // release clock wizards and wait for locked
            reset_cnt <= reset_cnt;
            reset_AXI_sw_n_ff <= 1'b1;
            reset_AXI_active_n <= 1'b0;
        end
        else if ( reset_cnt > 0 ) begin // locked, wait until counter is zero
            reset_cnt <= reset_cnt - 1;
            reset_AXI_sw_n_ff <= 1'b1;
            reset_AXI_active_n <= 1'b0;
        end
        else begin // reset finished
            reset_cnt <= 0;
            reset_AXI_sw_n_ff <= 1'b1;
            reset_AXI_active_n <= 1'b1;
        end
    end
    assign reset_AXI_sw_n = reset_AXI_sw_n_ff;

    // synchronize hardware and software reset @ clk_bus
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] reset_bus_cdc = {SYNC{1'b1}};
    always @ ( posedge clk_bus ) begin
        reset_bus_cdc <= {reset_bus_cdc[SYNC-2:0],reset_AXI_active_n};
    end
    wire reset_bus_n = reset_bus_cdc[SYNC-1];

    // synchronize hardware and software reset @ AXIS_in_aclk
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] reset_in_stream_cdc = {SYNC{1'b1}};
    always @ ( posedge AXIS_in_aclk ) begin
        reset_in_stream_cdc <= {reset_in_stream_cdc[SYNC-2:0],reset_AXI_active_n};
    end
    wire reset_in_stream_n = reset_in_stream_cdc[SYNC-1];
    
    // synchronize hardware and software reset @ AXIS_out_aclk
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] reset_out_stream_cdc = {SYNC{1'b1}};
    always @ ( posedge AXIS_out_aclk ) begin
        reset_out_stream_cdc <= {reset_out_stream_cdc[SYNC-2:0],reset_AXI_active_n};
    end
    wire reset_out_stream_n = reset_out_stream_cdc[SYNC-1];

    //////////////////////////////////////////////////////////////////////////////////
    // external clock selection @ AXI_aclk
    // clock Wizards are all @ AXI_aclk and are reset by reset_AXI_sw_n during switching of clock source

    // synchronize external lock signals @ AXI_aclk (note: most likely already synced?)    
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] clk_ext_locked_cdc = 0;
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] clk_mux_locked_cdc = 0;
    always @ ( posedge AXI_aclk ) begin
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
    wire error_axi;                 // status register bit
    wire ctrl_ext_clk_axi;          // control register bit
    reg [1:0] clk_ext_sel_ff = 2'b00;
    reg clk_ext_lost_axi;               // set immediately when external clock is selected and lock is lost
    wire ext_clk_en = clk_ext_locked_axi & clk_mux_locked_axi & ctrl_ext_clk_axi & (~error_axi);
    always @ ( posedge AXI_aclk ) begin
        if ( ( AXI_aresetn == 1'b0 ) || ( reset_sw_axi == 1'b1 ) ) begin
            clk_ext_sel_ff[0] <= 1'b0;
            clk_ext_sel_ff[1] <= 1'b0;
        end
        else begin 
            clk_ext_sel_ff[0] <= ext_clk_en;
            clk_ext_sel_ff[1] <= ext_clk_en & clk_ext_sel_ff[0]; // must be at least 2 cycles enabled. disable immediately.
        end
    end
    assign clk_ext_sel = clk_ext_sel_ff[1];
    
    // detect error_lock @ AXI_aclk
    // clk_ext_lost = set when external clock selected and lock lost. set until reset.
    // error_lock_count = is counting cycles while clk_ext_lost and CTRL_ERR_LOCK_EN is enabled
    // error_lock = is set when error_lock_count == ERROR_LOCK_DELAY
    // reset by reset_AXI_sw_n (software reset)
    reg error_lock_axi = 1'b0;
    wire ctrl_error_lock_en_axi;
    //wire lock_lost = clk_ext_sel & ((~clk_ext_locked_axi) | (~clk_mux_locked_axi) );
    wire lock_lost = ctrl_ext_clk_axi & ((~clk_ext_locked_axi) | (~clk_mux_locked_axi) );
    wire error_lock_active;
    if ( ERROR_LOCK_DELAY > 0 ) begin
        localparam integer ERROR_LOCK_BITS = clogb2(ERROR_LOCK_DELAY);
        reg [ERROR_LOCK_BITS-1:0] error_lock_count = 0;
        always @ ( posedge AXI_aclk ) begin
            if ( reset_AXI_sw_n == 1'b0 ) begin
                error_lock_count <= 0;
            end
            else begin
                error_lock_count <= ( ctrl_error_lock_en_axi & lock_lost ) ? error_lock_count + 1 : 0;
            end
        end
        assign error_lock_active = ( error_lock_count == ERROR_LOCK_DELAY );
    end
    else begin
        assign error_lock_active = ctrl_error_lock_en_axi & lock_lost;
    end
    // error_lock and clk_ext_lost signals @ AXI_aclk
    always @ ( posedge AXI_aclk ) begin
        if ( reset_AXI_sw_n == 1'b0 ) begin
            clk_ext_lost_axi <= 1'b0;
            error_lock_axi   <= 1'b0;
        end
        else begin
            clk_ext_lost_axi <= lock_lost | clk_ext_lost_axi;
            error_lock_axi   <= error_lock_active | error_lock_axi;
        end
    end

    //////////////////////////////////////////////////////////////////////////////////    
    // CDC status registers @ clk_bus -> AXI_aclk

    // latency = 4 fast clock cycles
    wire [AXI_DATA_WIDTH-1:0] board_time_bus;
    wire [AXI_DATA_WIDTH-1:0] board_samples_bus;
    wire [AXI_DATA_WIDTH-1:0] board_time_ext_bus;
    wire [AXI_DATA_WIDTH-1:0] board_samples_ext_bus;    
    wire [AXI_DATA_WIDTH-1:0] board_cycles_bus;
    wire [AXI_DATA_WIDTH-1:0] board_time_axi;
    wire [AXI_DATA_WIDTH-1:0] board_samples_axi;
    wire [AXI_DATA_WIDTH-1:0] board_time_ext_axi;
    wire [AXI_DATA_WIDTH-1:0] board_samples_ext_axi;
    wire [AXI_DATA_WIDTH-1:0] board_cycles_axi;
    wire [AXI_DATA_WIDTH-1:0] sync_time_axi;        // sync'ed from sync_time_det
    //wire status_update_axi;
    cdc # ( 
        .SYNC(SYNC), 
        .DATA_WIDTH(5*AXI_DATA_WIDTH), 
        .USE_OUT_READY("NO")
    )
    cdc_status (
        .in_clock(clk_bus),
        .in_reset_n(reset_bus_n),
        .in_data({board_cycles_bus,board_samples_ext_bus,board_time_ext_bus,board_samples_bus,board_time_bus}),
        .in_valid(1'b1),
        .in_ready(),                        // not used
        .out_clock(AXI_aclk),
        .out_reset_n(reset_AXI_sw_n),
        .out_data({board_cycles_axi,board_samples_ext_axi,board_time_ext_axi,board_samples_axi,board_time_axi}),
        .out_valid(),                       // not used (status_update_axi)
        .out_ready()                        // not used
    ); 

    //////////////////////////////////////////////////////////////////////////////////    
    // synchronize status bits and trg inputs @ AXI_aclk

    // assign status bits from timing module
    localparam integer TIMING_STATUS_BITS = 10;
    wire [TIMING_STATUS_BITS-1:0] timing_status_bus;
    wire [TIMING_STATUS_BITS-1:0] timing_status_axi;
    wire status_ready_axi       = timing_status_axi[0];
    wire status_run_axi         = timing_status_axi[1];
    wire status_end_axi         = timing_status_axi[2];
    wire status_wait_axi        = timing_status_axi[3];
    wire status_restart_axi     = timing_status_axi[4];
    wire error_in_axi           = timing_status_axi[5];
    wire error_out_axi          = timing_status_axi[6];
    wire error_time_axi         = timing_status_axi[7];
    wire status_irq_freq_axi    = timing_status_axi[8];
    wire status_irq_data_axi    = timing_status_axi[9];
    
    // TX/RX FIFO full
    wire TX_full_axi;
    wire RX_full_axi;

    // assign status bits from auto-sync module
    wire as_active_bus;
    wire as_active_axi;
    wire as_timeout_axi;
    wire as_done_axi;
    
    // phase shift status bit
    wire ps_active_axi;
    
    // trigger inputs (only for use in status register)
    //wire trg_start_axi;
    //wire trg_stop_axi;
        
    // other status bits
    wire error_keep_stream;
    wire error_keep_axi;

    // buttons    
    wire [NUM_BUTTONS-1:0] buttons_axi;
    wire [NUM_BUTTONS-1:0] buttons_pwm;

    // synchronize control bits and trigger inputs with clk_bus (no reset needed)
    // note: these bits are NOT synced with respect to each other! but transmits faster than CDC above.
    localparam integer NUM_OUT_SYNC = NUM_BUTTONS + 2 + TIMING_STATUS_BITS;    
    wire [NUM_OUT_SYNC-1:0] out_w = {buttons_pwm,error_keep_stream,as_active_bus,timing_status_bus};
    wire [NUM_OUT_SYNC-1:0] out_s;
    generate
    for (genvar i = 0; i < NUM_OUT_SYNC; i = i + 1)
    begin : O_SYNC
        (* ASYNC_REG = "TRUE" *)
        reg [SYNC-1:0] sync = 0;
        always @ ( posedge AXI_aclk ) begin
            sync <= {sync[SYNC-2:0],out_w[i]};
        end
        assign out_s[i] = sync[SYNC-1];
    end
    endgenerate
    assign {buttons_axi,error_keep_axi,as_active_axi,timing_status_axi} = out_s;
    
    //////////////////////////////////////////////////////////////////////////////////
    // IRQ status @ AXI_aclk
    // TODO: maybe its easier @ clk_bus and then sync to AXI_aclk?
        
    // IRQ on error, external clock lost, restart (toggle), end (positive edge) state or update (toggle)
    // reset with reset_n_fast or set irq_en = 0
    // note: even if disabled maintain edge detector of end state!
    //       otherwise on enabling will trigger irq when already in end state.
    localparam integer NUM_IRQ = 5;
    reg  [NUM_IRQ-1:0] irq_out_axi; // irq status bits
    wire [NUM_IRQ-1:0] irq_en_axi;  // irq enable control bits
    reg  [1:0] status_err_ff;       // positive edge detector of error
    reg  [1:0] status_end_ff;       // positive edge detector of end state
    reg  status_restart_ff;         // status_restart change detector
    reg  status_irq_freq_ff;        // status_irq_freq change detector
    reg  status_irq_data_ff;        // status_irq_data change detector
    always @ ( posedge AXI_aclk ) begin
        if ( reset_AXI_sw_n == 1'b0 ) begin
            irq_out_axi        <= 0;
            status_err_ff      <= 2'b00;
            status_end_ff      <= 2'b00;
            status_restart_ff  <= 1'b0;
            status_irq_freq_ff <= 1'b0;
            status_irq_data_ff <= 1'b0;
        end
        else begin
            irq_out_axi[0]     <= irq_en_axi[0]                 & ( ( status_err_ff == 2'b01 )                    | irq_out_axi[0] );
            irq_out_axi[1]     <= irq_en_axi[0] & irq_en_axi[1] & ( ( status_end_ff == 2'b01 )                    | irq_out_axi[1] );
            irq_out_axi[2]     <= irq_en_axi[0] & irq_en_axi[2] & ( ( status_restart_ff  != status_restart_axi  ) | irq_out_axi[2] );
            irq_out_axi[3]     <= irq_en_axi[0] & irq_en_axi[3] & ( ( status_irq_freq_ff != status_irq_freq_axi ) | irq_out_axi[3] );
            irq_out_axi[4]     <= irq_en_axi[0] & irq_en_axi[4] & ( ( status_irq_data_ff != status_irq_data_axi ) | irq_out_axi[4] );
            status_err_ff      <= {status_err_ff[0],error_axi};
            status_end_ff      <= {status_end_ff[0],status_end_axi};
            status_restart_ff  <= status_restart_axi;
            status_irq_freq_ff <= status_irq_freq_axi;
            status_irq_data_ff <= status_irq_data_axi;
        end
    end
    assign irq_FPGA = |irq_out_axi;

    //////////////////////////////////////////////////////////////////////////////////
    // buttons and LEDs (status) @ clk_pwm
    
    wire svr_ready_axi;                     // control bit
    wire reset_sw_n_pwm;
    wire run_pwm;
    wire error_pwm;
    wire restart_pwm;
    wire clk_ext_locked_pwm;
    
    // synchronize bits used for LEDs with clk_pwm
    //localparam integer NUM_PWM_SYNC = 8;    
    //wire [NUM_PWM_SYNC-1:0] pwm_w = {status_restart_axi,status_end_axi,error_axi,status_run_axi,ready_axi,clk_ext_sel,clk_ext_locked_axi,reset_AXI_sw_n};
    localparam integer NUM_LED = 3; // types of led = red,green,blue
    localparam integer NUM_PWM_SYNC = NUM_LED + 5;
    wire [NUM_LED-1:0] led_bus;
    wire [NUM_LED-1:0] led_pwm;
    wire [NUM_PWM_SYNC-1:0] pwm_w = {status_restart_axi,clk_ext_locked,error_axi,status_run_axi,led_bus,reset_AXI_sw_n};
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
    //assign {restart_pwm,end_pwm,error_pwm,run_pwm,ready_pwm,clk_ext_sel_pwm,clk_ext_locked_pwm,reset_sw_n_pwm} = pwm_s;
    assign {restart_pwm,clk_ext_locked_pwm,error_pwm,run_pwm,led_pwm,reset_sw_n_pwm} = pwm_s;
    
    /* test
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] reset_n_pwm_sync = 0;
    always @ ( posedge clk_pwm ) begin
        reset_n_pwm_sync <= {reset_n_pwm_sync[SYNC-2:0],AXI_aresetn};
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
        .clk_in(AXI_aclk),
        .clk_out(clk_pwm),
        .in(AXI_aresetn),
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
    wire [NUM_LEDS-1:0] leds_in_sel;
    assign leds_in_sel[0] = error_pwm;          // Cora red (error)
    assign leds_in_sel[1] = led_bus[0];         // buffer board red (programmable)
    assign leds_in_sel[2] = run_pwm;            // Cora green (ok)
    assign leds_in_sel[3] = led_bus[1];         // buffer board green (programmable)
    assign leds_in_sel[4] = clk_ext_locked_pwm; // Cora blue (ext clock locked)
    assign leds_in_sel[5] = led_bus[2];         // buffer board green or blue (programmable)
    reg  [NUM_LEDS - 1 : 0] leds_in;
    reg  [NUM_LEDS - 1 : 0] leds_bright = {DIM,BRIGHT,DIM,BRIGHT,DIM,BRIGHT}; // overall brightness level
    reg  [NUM_LEDS - 1 : 0] leds_blink;
    reg  [NUM_LEDS - 1 : 0] leds_high;
    wire [NUM_LEDS - 1 : 0] leds_inv    = {INV_BLUE,INV_GREEN,INV_RED};
    wire any_btn = |buttons_pwm;
    always @ ( posedge clk_pwm ) begin
        if ( (reset_sw_n_pwm == 1'b0) || (any_btn == 1'b1) ) begin // reset or any button pressed: all LEDs ON bright.
            leds_in    <= {ON,ON,ON,ON,ON,ON};
            leds_blink <= {CONT,CONT,CONT,CONT,CONT,CONT};     
            leds_high  <= {BRIGHT,BRIGHT,BRIGHT,BRIGHT,BRIGHT,BRIGHT};
            //leds_inv <= {NUM_LEDS{1'b0}};
        end
        else if ( error_pwm ) begin // error: red on
            //leds_in <= {clk_ext_locked_pwm, clk_ext_locked_pwm, OFF,OFF,ON,ON};
            leds_in    <= leds_in_sel;
            leds_blink <= {CONT,CONT,CONT,CONT,CONT,CONT};     
            leds_high  <= {BRIGHT,BRIGHT,BRIGHT,BRIGHT,BRIGHT,BRIGHT};     
            //leds_inv <= {NUM_LEDS{1'b0}};
        end
        else if ( run_pwm ) begin // run: green LED bright/dim toggled after each restart
            //leds_in <= {clk_ext_locked_pwm,clk_ext_locked_pwm,ON,ON,OFF,OFF};
            leds_in    <= leds_in_sel;
            leds_blink <= {CONT,CONT,CONT,CONT,CONT,CONT};     
            leds_high  <= {BRIGHT,BRIGHT,~restart_pwm,~restart_pwm,DIM,DIM};
            //leds_inv <= {NUM_LEDS{1'b0}};
        end
        else if ( svr_ready_axi | status_ready_axi | status_end_axi ) begin // server connected, ready for data, or end: all off
            //leds_in <= {clk_ext_locked_pwm,clk_ext_locked_pwm,OFF,OFF,OFF,OFF};
            leds_in    <= leds_in_sel;
            leds_blink <= {CONT,CONT,CONT,CONT,CONT,CONT};     
            leds_high  <= {BRIGHT,BRIGHT,BRIGHT,BRIGHT,BRIGHT,BRIGHT};     
            //leds_inv <= {NUM_LEDS{1'b0}};
        end
        else begin // waiting for server to connect: all on
            //leds_in <= {clk_ext_locked_pwm,clk_ext_locked_pwm,ON,ON,ON,ON};
            leds_in    <= leds_in_sel;
            leds_blink <= {CONT,CONT,CONT,CONT,CONT,CONT};     
            leds_high  <= {BRIGHT,BRIGHT,BRIGHT,BRIGHT,DIM,DIM};     
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
    assign led_red   = leds_out[1:0];
    assign led_green = leds_out[3:2];
    assign led_blue  = leds_out[5:4];

    //////////////////////////////////////////////////////////////////////////////////    
    // AXI Lite bus @ AXI_aclk

    reg ps_done_ext_ff;
    reg ps_done_det_ff;

    // status bit assignments @ AXI_aclk
    wire [AXI_DATA_WIDTH-1:0] status_axi; // status register
    assign error_axi = error_in_axi | error_out_axi | error_time_axi | error_lock_axi | error_keep_axi;
    generate
      for (genvar i = 0; i < AXI_DATA_WIDTH; i = i + 1)
      begin: GEN_REG_STATUS
        case ( i )
          STATUS_RESET:             assign status_axi[i] = ~reset_AXI_sw_n;
          STATUS_READY:             assign status_axi[i] = status_ready_axi;
          STATUS_RUN:               assign status_axi[i] = status_run_axi;
          STATUS_END:               assign status_axi[i] = status_end_axi;
          STATUS_WAIT:              assign status_axi[i] = status_wait_axi;
          //
          STATUS_AUTO_SYNC:         assign status_axi[i] = as_active_axi;
          STATUS_AS_TIMEOUT:        assign status_axi[i] = as_timeout_axi;
          STATUS_PS_ACTIVE:         assign status_axi[i] = ps_active_axi;
          //
          STATUS_TX_FULL:           assign status_axi[i] = TX_full_axi;
          STATUS_RX_FULL:           assign status_axi[i] = RX_full_axi;
          // 
          STATUS_CLK_EXT:           assign status_axi[i] = clk_ext_sel;
          STATUS_CLK_EXT_LOCKED:    assign status_axi[i] = clk_ext_locked_axi;
          //
          STATUS_ERR_IN:            assign status_axi[i] = error_in_axi;
          STATUS_ERR_OUT:           assign status_axi[i] = error_out_axi;
          STATUS_ERR_TIME:          assign status_axi[i] = error_time_axi;
          STATUS_ERR_LOCK:          assign status_axi[i] = clk_ext_lost_axi; 
          STATUS_ERR_TKEEP:         assign status_axi[i] = error_keep_axi;
          //
          STATUS_IRQ_ERROR:         assign status_axi[i] = irq_out_axi[0];
          STATUS_IRQ_END:           assign status_axi[i] = irq_out_axi[1];
          STATUS_IRQ_RESTART:       assign status_axi[i] = irq_out_axi[2];
          STATUS_IRQ_FREQ:          assign status_axi[i] = irq_out_axi[3];
          STATUS_IRQ_DATA:          assign status_axi[i] = irq_out_axi[4];
          // 
          //STATUS_TRG_START:         assign status_axi[i] = trg_start_axi;
          //STATUS_TRG_STOP:          assign status_axi[i] = trg_stop_axi;
          //
          STATUS_BTN_0:             assign status_axi[i] = buttons_axi[0];
          STATUS_BTN_1:             assign status_axi[i] = buttons_axi[1];
          //
          default:                  assign status_axi[i] = 1'b0;
        endcase
      end
    endgenerate
                    
    wire [NUM_CTRL-1:0] ctrl_update_axi;          // pulses bit corresponding to control register when was updated
    wire [AXI_DATA_WIDTH-1:0] control_axi;
    wire [AXI_DATA_WIDTH-1:0] ctrl_in0_axi;
    wire [AXI_DATA_WIDTH-1:0] ctrl_in1_axi;
    wire [AXI_DATA_WIDTH-1:0] ctrl_out0_axi;
    wire [AXI_DATA_WIDTH-1:0] ctrl_out1_axi;
    wire [AXI_DATA_WIDTH-1:0] num_samples_axi;
    wire [AXI_DATA_WIDTH-1:0] num_cycles_axi;
    wire [AXI_DATA_WIDTH-1:0] clk_div_axi;
    wire [AXI_DATA_WIDTH-1:0] strb_delay_axi;
    wire [AXI_DATA_WIDTH-1:0] sync_delay_axi;
    wire [AXI_DATA_WIDTH-1:0] sync_phase_axi;
    wire [AXI_DATA_WIDTH-1:0] force_out_axi;
    // packed settings
    wire [7:0] bus_data_bits    = BUS_DATA_BITS;
    wire [7:0] bus_addr_bits    = BUS_ADDR_BITS;
    wire [7:0] bus_num_strb     = NUM_STRB;
    wire [7:0] bus_num_en       = NUM_BUS_EN;
    wire [7:0] bus_addr_high    = (BUS_ADDR_1_USE == "ZERO"     ) ? 8'd0 :
                                  (BUS_ADDR_1_USE == "ADDR0"    ) ? 8'd1 :
                                  (BUS_ADDR_1_USE == "DATA_HIGH") ? 8'd2 : 8'd3; 
    wire [7:0] irq_freq_bits    = IRQ_FREQ_BITS;
    wire [7:0] clk_div_bits     = CLK_DIV_BITS;
    wire [7:0] strb_delay_bits  = CLK_DIV_BITS;
    wire [7:0] sync_delay_bits  = SYNC_DELAY_BITS;
    wire [7:0] error_lock_delay = ERROR_LOCK_DELAY;
    wire [7:0] led_blink_on     = LED_BLINK_ON;
    wire [7:0] led_slow         = LED_SLOW;
    wire [7:0] led_fast         = LED_FAST;
    wire [7:0] led_dim_low      = LED_DIM_LOW;
    wire [7:0] led_dim_high     = LED_DIM_HIGH;
    wire [7:0] led_bright_low   = LED_BRIGHT_LOW;
    wire [7:0] led_bright_high  = LED_BRIGHT_HIGH;

    dio24_AXI_slave # (
        .C_S_AXI_DATA_WIDTH(AXI_DATA_WIDTH),
        .C_S_AXI_ADDR_WIDTH(AXI_ADDR_WIDTH),
        .REG_CTRL(REG_CTRL),
        .REG_CTRL_RESET(CTRL_RESET),
        .REG_0_CTRL_INIT(32'd0),
        .REG_1_CTRL_INIT(32'd0),
        .REG_2_CTRL_INIT(32'd0),
        .REG_3_CTRL_INIT(32'd0),
        .REG_4_CTRL_INIT(32'd0), 
        .REG_5_CTRL_INIT(32'd0),
        .REG_6_CTRL_INIT(32'd0),
        .REG_7_CTRL_INIT(32'd0),
        .REG_8_CTRL_INIT(32'd0),
        .REG_9_CTRL_INIT(32'd0),
        .REG_10_CTRL_INIT(32'd0),
        .REG_11_CTRL_INIT(32'd0),
        .REG_12_CTRL_INIT(32'd100),         // clk_div = 100 = 1MHz
        .REG_13_CTRL_INIT(32'h461e461e),    // strb_delay = 300:400:300 ns @ 1MHz
        .REG_14_CTRL_INIT(32'd0),
        .REG_15_CTRL_INIT(32'd0),
        .REG_16_CTRL_INIT(32'd0),
        .REG_17_CTRL_INIT(32'd1),           // num_cycles = 1
        .REG_18_CTRL_INIT(32'd0),
        .REG_19_CTRL_INIT(32'd0),
        .REG_20_CTRL_INIT(32'd0), 
        .REG_21_CTRL_INIT(32'd0),
        .REG_22_CTRL_INIT(32'd0),
        .REG_23_CTRL_INIT(32'd0),
        .REG_24_CTRL_INIT(32'd0),
        .REG_25_CTRL_INIT(32'd0),
        .REG_26_CTRL_INIT(32'd0),
        .REG_27_CTRL_INIT(32'd0),
        .REG_28_CTRL_INIT(32'd0),
        .REG_29_CTRL_INIT(32'd0),
        .REG_30_CTRL_INIT(32'd0),
        .REG_31_CTRL_INIT(32'd0)
    ) dio24_AXI_inst (
        .S_AXI_ACLK(AXI_aclk),
        .S_AXI_ARESETN(AXI_aresetn),          // note: dont reset with reset_sw
        .S_AXI_AWADDR(AXI_awaddr),
        .S_AXI_AWPROT(AXI_awprot),
        .S_AXI_AWVALID(AXI_awvalid),
        .S_AXI_AWREADY(AXI_awready),
        .S_AXI_WDATA(AXI_wdata),
        .S_AXI_WSTRB(AXI_wstrb),
        .S_AXI_WVALID(AXI_wvalid),
        .S_AXI_WREADY(AXI_wready),
        .S_AXI_BRESP(AXI_bresp),
        .S_AXI_BVALID(AXI_bvalid),
        .S_AXI_BREADY(AXI_bready),
        .S_AXI_ARADDR(AXI_araddr),
        .S_AXI_ARPROT(AXI_arprot),
        .S_AXI_ARVALID(AXI_arvalid),
        .S_AXI_ARREADY(AXI_arready),
        .S_AXI_RDATA(AXI_rdata),
        .S_AXI_RRESP(AXI_rresp),
        .S_AXI_RVALID(AXI_rvalid),
        .S_AXI_RREADY(AXI_rready),
        // control registers
        .reg_0_ctrl(control_axi),
        .reg_1_ctrl(),
        .reg_2_ctrl(),
        .reg_3_ctrl(),
        .reg_4_ctrl(ctrl_in0_axi),
        .reg_5_ctrl(ctrl_in1_axi),
        .reg_6_ctrl(),
        .reg_7_ctrl(),
        .reg_8_ctrl(ctrl_out0_axi),
        .reg_9_ctrl(ctrl_out1_axi),
        .reg_10_ctrl(),
        .reg_11_ctrl(),
        .reg_12_ctrl(clk_div_axi),
        .reg_13_ctrl(strb_delay_axi),
        .reg_14_ctrl(),
        .reg_15_ctrl(),
        .reg_16_ctrl(num_samples_axi),
        .reg_17_ctrl(num_cycles_axi),
        .reg_18_ctrl(),
        .reg_19_ctrl(),
        .reg_20_ctrl(),
        .reg_21_ctrl(),
        .reg_22_ctrl(),
        .reg_23_ctrl(),
        .reg_24_ctrl(sync_delay_axi),
        .reg_25_ctrl(sync_phase_axi),
        .reg_26_ctrl(),
        .reg_27_ctrl(),
        .reg_28_ctrl(),
        .reg_29_ctrl(),
        .reg_30_ctrl(force_out_axi),
        .reg_31_ctrl(),
        // pulses bit corresponding to control register when was updated
        .reg_ctrl_update(ctrl_update_axi),
        // status registers
        .reg_32_sts(status_axi),
        .reg_33_sts(32'h0),
        .reg_34_sts(32'h0),
        .reg_35_sts(32'h0),
        .reg_36_sts(board_time_axi),
        .reg_37_sts(board_time_ext_axi),
        .reg_38_sts(sync_time_axi),
        .reg_39_sts(32'h0),
        .reg_40_sts(board_samples_axi),
        .reg_41_sts(board_samples_ext_axi),
        .reg_42_sts(32'h0),
        .reg_43_sts(32'h0),
        .reg_44_sts(board_cycles_axi),
        .reg_45_sts(32'h0),
        .reg_46_sts(32'h0),
        .reg_47_sts(32'h0),
        .reg_48_sts({bus_num_en,bus_num_strb,bus_addr_bits,bus_data_bits}),
        .reg_49_sts({24'h0,bus_addr_high}),
        .reg_50_sts({16'h0,strb_delay_bits,clk_div_bits}),
        .reg_51_sts({24'h0,irq_freq_bits}),
        .reg_52_sts({24'h0,sync_delay_bits}),
        .reg_53_sts({24'h0,error_lock_delay}),
        .reg_54_sts({ 8'h0,led_blink_on,led_fast,led_slow}),
        .reg_55_sts({led_bright_high,led_bright_low,led_dim_high,led_dim_low}),
        .reg_56_sts(32'b0),
        .reg_57_sts(32'h0),
        .reg_58_sts(32'h0),
        .reg_59_sts(32'h0),
        .reg_60_sts(VERSION),
        .reg_61_sts(INFO),
        .reg_62_sts(32'h0),
        .reg_63_sts(32'h0)
    );
            
    //////////////////////////////////////////////////////////////////////////////////
    // dynamic phase shift @ AXI_aclk

    // start phase shift when sync_phase register was written
    wire ps_start_axi = ctrl_update_axi[REG_SYNC_PHASE];

    // external clock dynamic phase shift @ clock_pclk
    wire ps_ext_active_axi;
    dynamic_phase # (
        .PHASE_BITS(AUTO_SYNC_PHASE_BITS)
    )
    ps_ext
    (
        // clock and reset
        .clock(AXI_aclk),                    // if pclk = AXI_aclk then all wizards can be reset with same reset signal
        .reset_n(reset_AXI_sw_n),           // same reset as for clock wizard. triggered by HW, SW and switching of clock.
        // control and status
        .ps_start(ps_start_axi),
        .ps_active(ps_ext_active_axi),
        // clock is locked signal
        .clock_locked(clk_ext_locked_axi),      // external clock must be locked and stay locked during phase shift
        // ps control
        .ps_en(ps_en_ext),
        .ps_inc(ps_inc_ext), 
        .ps_done(ps_done_ext),
        // phase shift @ AXI_aclk
        .ps_phase(sync_phase_axi[2*AUTO_SYNC_PHASE_BITS-1:AUTO_SYNC_PHASE_BITS])
        //.ps_phase(sync_phase[AUTO_SYNC_PHASE_BITS-1:0])
    );

    // temporary test    
    always @ (posedge AXI_aclk) begin
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
    wire ps_det_active_axi;
    dynamic_phase # (
        .PHASE_BITS(AUTO_SYNC_PHASE_BITS)
    )
    ps_det
    (
        // clock and reset
        .clock(AXI_aclk),                    // if pclk = AXI_aclk then all wizards can be reset with same reset signal
        .reset_n(reset_AXI_sw_n),           // same reset as for clock wizard. triggered by HW, SW and switching of clock.
        // control and status
        .ps_start(ps_start_axi),
        .ps_active(ps_det_active_axi),
        // clock is locked signal
        .clock_locked(clk_mux_locked_axi & clk_ext_locked_axi), // ensure all clocks are locked. 
        // ps control
        .ps_en(ps_en_det),
        .ps_inc(ps_inc_det), 
        .ps_done(ps_done_det),
        // phase shift @ AXI_aclk
        .ps_phase(sync_phase_axi[AUTO_SYNC_PHASE_BITS-1:0])
    );
    
    assign ps_active_axi = ps_ext_active_axi | ps_det_active_axi;

    //////////////////////////////////////////////////////////////////////////////////
    // CDC control bits & trigger and locked inputs @ clk_bus 

    // control register assignments @ AXI_aclk
    assign reset_sw_axi             = control_axi[CTRL_RESET];  // this is auto-reset by dio24_AXI_slave
    assign svr_ready_axi            = control_axi[CTRL_READY];
    wire run_en_axi                 = control_axi[CTRL_RUN];
    wire restart_en_axi             = control_axi[CTRL_RESTART_EN];
    wire as_en_axi                  = control_axi[CTRL_AUTO_SYNC_EN];
    //wire as_prim_axi                = control_axi[CTRL_AUTO_SYNC_PRIM];
    wire str_96_axi                 = control_axi[CTRL_BPS96];
    wire str_96_b1_axi              = control_axi[CTRL_BPS96_BRD_1];
    assign ctrl_ext_clk_axi         = control_axi[CTRL_CLK_EXT];
    assign ctrl_error_lock_en_axi   = control_axi[CTRL_ERR_LOCK_EN]; 
    wire irq_freq_en_axi            = control_axi[CTRL_IRQ_FREQ_EN];
    wire irq_data_en_axi            = control_axi[CTRL_IRQ_DATA_EN];
    assign irq_en_axi[NUM_IRQ-1:0]  = {irq_data_en_axi,irq_freq_en_axi,control_axi[CTRL_IRQ_RESTART_EN],control_axi[CTRL_IRQ_END_EN],control_axi[CTRL_IRQ_EN]};
    
    // control bits into timing module
    localparam integer TIMING_CTRL_BITS = 10;       // number of control bits for timing module
    wire [TIMING_CTRL_BITS - 1 : 0] timing_ctrl_axi = {as_en_axi,clk_ext_lost_axi,clk_ext_sel,clk_ext_locked,irq_data_en_axi,irq_freq_en_axi,restart_en_axi,run_en_axi,error_axi,svr_ready_axi};
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
    localparam integer NUM_IN_SYNC = TIMING_CTRL_BITS; //+ AS_CTRL_BITS; //+ LOCKED_BITS; // + TRG_BITS;
    //wire svr_ready_bus;
    //wire error_bus;
    //wire ctrl_ext_clk_bus;
    //wire as_en_bus; // if 1'b1 start trigger is detected @ clk_det in as module, otherwise directly here (see run_bus)
    //wire trg_start_en_bus;
    //wire [NUM_IN_SYNC-1:0] in_w = {ctrl_ext_clk,error,svr_ready,as_ctrl,timing_ctrl};
    wire [NUM_IN_SYNC-1:0] in_w = timing_ctrl_axi;
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
    assign timing_ctrl_bus = in_s;
        
    //////////////////////////////////////////////////////////////////////////////////
    // input AXI stream @ AXIS_in_aclk
    
    // synchronize stream selection bits @ AXIS_in_aclk
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] str_96_cdc = 0;
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] str_96_b1_cdc = 0;
    always @ ( posedge AXIS_in_aclk ) begin
        str_96_cdc    <= {str_96_cdc   [SYNC-2:0],str_96_axi};
        str_96_b1_cdc <= {str_96_b1_cdc[SYNC-2:0],str_96_b1_axi};
    end
    wire str_96_stream    = str_96_cdc   [SYNC-1];
    wire str_96_b1_stream = str_96_b1_cdc[SYNC-1];
    
    // tkeep must have all bits high
    reg error_keep_in = 1'b0;
    always @ ( posedge AXIS_in_aclk ) begin
        if ( (reset_in_stream_n == 1'b0) || (AXIS_in_aresetn == 1'b0)) begin
            error_keep_in <= 1'b0;
        end
        else if ( AXIS_in_tvalid & AXIS_in_tready ) begin
            error_keep_in <= ( AXIS_in_tkeep != {(STREAM_DATA_WIDTH/8){1'b1}}) ? 1'b1 : error_keep_in;
        end
        else begin
            error_keep_in <= error_keep_in;
        end
    end
    assign error_keep_stream = error_keep_in;

    /* convert DMA input data stream to 64/96bits per sample
    // TODO: dynamic switching str_96_stream and selection of board data str_96_b1_stream
    wire [STREAM_DATA_WIDTH - 1 : 0] in_data_smpl;
    wire [(STREAM_DATA_WIDTH/8) - 1 : 0] in_keep_smpl;
    wire in_last_smpl;
    wire in_valid_smpl;
    wire in_ready_smpl;
    if (STREAM_DATA_WIDTH != STREAM_DATA_WIDTH) begin : IN_CONV
       stream_convert # (
           .IN_BYTES(STREAM_DATA_WIDTH/8), // always 16 bytes
           .OUT_BYTES(STREAM_DATA_WIDTH/8) // 12 or 8 bytes
       )
       in_conv (
           // clock and reset
           .clock(AXIS_in_aclk),
           .reset_n(reset_in_stream_n & AXIS_in_aresetn),
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
        if ( (reset_in_stream_n == 1'b0) || (AXIS_in_aresetn == 1'b0)) begin
            error_keep_smpl <= 1'b0;
        end
        else if ( in_valid_smpl & in_ready_smpl ) begin
            error_keep_smpl <= ( in_keep_smpl != {(STREAM_DATA_WIDTH/8){1'b1}}) ? 1'b1 : error_keep_smpl;
        end
        else begin
            error_keep_smpl <= error_keep_smpl;
        end
    end
    assign error_keep_stream[1] = error_keep_smpl;

    // TX data stream: select time and data from samples
    wire [STREAM_DATA_WIDTH - 1 : 0] in_data_TX;
    wire in_last_TX;
    wire in_valid_TX;
    wire in_ready_TX;
    wire [clogb2(STREAM_DATA_WIDTH-DATA_BITS)-1:0] data_offset = str_96_stream ? (str_96_b1_stream ? DATA_START_96_1 : DATA_START_96_0) : DATA_START_64;
    if (STREAM_DATA_WIDTH != TIMEDATA_BITS) begin
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
    */
        
    // TODO: dynamic switching str_96_stream and selection of board data str_96_b1_stream
    wire [STREAM_DATA_WIDTH-1:0] in_data_TX = AXIS_in_tdata;
    wire in_last_TX = AXIS_in_tlast;
    wire in_valid_TX = AXIS_in_tvalid;
    wire in_ready_TX;
    assign AXIS_in_tready = in_ready_TX;

    //////////////////////////////////////////////////////////////////////////////////
    // TX FIFO @ AXIS_in_aclk -> clk_bus 

    wire [STREAM_DATA_WIDTH - 1 : 0] in_data_bus;    
    wire in_last_bus;
    wire in_ready_bus;
    wire in_valid_bus;
    wire TX_full_axis;
    wire TX_empty_bus;
    dio24_FIFO # (
        .STREAM_DATA_WIDTH(STREAM_DATA_WIDTH + 1),
        .FIFO_DEPTH(TX_FIFO_DEPTH),
        .OUT_ZERO("FALSE")
    )
    TX_FIFO
    (
        .in_clock(AXIS_in_aclk),
        .in_reset_n(reset_in_stream_n & AXIS_in_aresetn),
        .in_data({in_last_TX,in_data_TX}),
        .in_ready(in_ready_TX),
        .in_valid(in_valid_TX),
        .in_full(TX_full_axis),
        .out_clock(clk_bus),
        .out_reset_n(reset_bus_n),
        .out_data({in_last_bus,in_data_bus}),
        .out_valid(in_valid_bus),
        .out_ready(in_ready_bus),
        .out_empty(TX_empty_bus)
    );

    //////////////////////////////////////////////////////////////////////////////////
    // CDC control registers @ AXI_aclk -> clk_bus 
    // CDC ensures consistency between bits
    
    // reset CDC from clock_AXI to clock_bus without software reset
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] reset_hw_ff;    
    always @ ( posedge clk_bus ) begin
        reset_hw_ff <= {reset_hw_ff[SYNC-2:0], AXI_aresetn};
    end
    wire reset_hw_bus_n = reset_hw_ff[SYNC-1];    

    // num_samples and num_cycles
    wire num_reload_bus;
    wire [AXI_DATA_WIDTH-1 : 0] num_samples_bus;
    wire [AXI_DATA_WIDTH-1 : 0] num_cycles_bus;
    reg  num_valid = 1'b0;
    wire num_ready;
    // cdc valid signal 
    // set when register is updated @ AXI_aclk
    // reset when ready @ clk_bus transmitted back to AXI_aclk
    always @ ( posedge AXI_aclk ) begin
        if      ( AXI_aresetn == 1'b0 ) num_valid <= 1'b0;
        else if ( ctrl_update_axi[REG_NUM_SAMPLES] | 
                  ctrl_update_axi[REG_NUM_CYCLES] ) 
                                        num_valid <= 1'b1;
        else if ( num_ready )           num_valid <= 1'b0;
        else                            num_valid <= num_valid;
    end
    cdc # ( 
        .SYNC(SYNC), 
        .DATA_WIDTH(AXI_DATA_WIDTH*2), 
        .USE_OUT_READY("NO")
    )
    cdc_num (
        .in_clock(AXI_aclk),
        .in_reset_n(AXI_aresetn),               // no software reset
        .in_data({num_cycles_axi, num_samples_axi}),
        .in_valid(num_valid),
        .in_ready(num_ready),
        .out_clock(clk_bus),
        .out_reset_n(reset_hw_bus_n),           // no software reset
        .out_data({num_cycles_bus, num_samples_bus}),
        .out_valid(num_reload_bus),             // pulses when registers are updated
        .out_ready(1'b1)                        // always ready
    ); 
    
    // timing registers: clk_div and strb_delay
    // note: these registers affect the strobe output - contiguous and on bus
    //       in order to avoid glitches or unintended reset of toggle bus write only once!
    wire timing_reload_bus; // pulses when registers are updated @ clk_bus
    wire [CLK_DIV_BITS                -1 : 0] clk_div_bus;
    wire [CLK_DIV_BITS*NUM_STRB_CONT*2-1 : 0] strb_delay_bus;    
    reg  timing_valid = 1'b0;
    wire timing_ready;
    always @ ( posedge AXI_aclk ) begin
        if      ( AXI_aresetn == 1'b0 ) timing_valid <= 1'b0;
        else if ( ctrl_update_axi[REG_CLK_DIV   ] |
                  ctrl_update_axi[REG_STRB_DELAY] ) 
                                        timing_valid <= 1'b1;
        else if ( timing_ready )        timing_valid <= 1'b0;
        else                            timing_valid <= timing_valid;
    end
    cdc # ( 
        .SYNC(SYNC), 
        .DATA_WIDTH(CLK_DIV_BITS + 2*NUM_STRB_CONT*CLK_DIV_BITS), 
        .USE_OUT_READY("NO")
    )
    cdc_timing (
        .in_clock(AXI_aclk),
        .in_reset_n(AXI_aresetn),               // no software reset
        .in_data({strb_delay_axi[2*NUM_STRB_CONT*CLK_DIV_BITS-1 : 0],
                  clk_div_axi[CLK_DIV_BITS-1:0]}),
        .in_valid(timing_valid),
        .in_ready(timing_ready),
        .out_clock(clk_bus),
        .out_reset_n(reset_hw_bus_n),           // no software reset
        .out_data({strb_delay_bus, clk_div_bus}),
        .out_valid(timing_reload_bus),
        .out_ready(1'b1)                        // always ready
    );    
    
    // sync_delay register
    // note: do not combine with timing registers above to avoid unintended glitches. 
    //       however, could be combined with other registers.
    wire sync_delay_reload_bus; // pulses when register is updated @ clk_bus
    wire [SYNC_DELAY_BITS             -1 : 0] sync_delay_bus;
    reg  sync_delay_valid = 1'b0;
    wire sync_delay_ready;
    always @ ( posedge AXI_aclk ) begin
        if      ( AXI_aresetn == 1'b0 ) sync_delay_valid <= 1'b0;
        else if ( ctrl_update_axi[REG_SYNC_DELAY] ) 
                                        sync_delay_valid <= 1'b1;
        else if ( sync_delay_ready )    sync_delay_valid <= 1'b0;
        else                            sync_delay_valid <= sync_delay_valid;
    end
    cdc # ( 
        .SYNC(SYNC), 
        .DATA_WIDTH(SYNC_DELAY_BITS), 
        .USE_OUT_READY("NO")
    )
    cdc_sync_delay (
        .in_clock(AXI_aclk),
        .in_reset_n(AXI_aresetn),               // no software reset
        .in_data(sync_delay_axi[SYNC_DELAY_BITS-1:0]),
        .in_valid(sync_delay_valid),
        .in_ready(sync_delay_ready),
        .out_clock(clk_bus),
        .out_reset_n(reset_hw_bus_n),           // no software reset
        .out_data(sync_delay_bus),
        .out_valid(sync_delay_reload_bus),
        .out_ready(1'b1)                        // always ready
    );    

    // ctrl_in0 and ctrl_in1
    wire ctrl_in_reload_bus;
    wire [AXI_DATA_WIDTH-1 : 0] ctrl_in0_bus;
    wire [AXI_DATA_WIDTH-1 : 0] ctrl_in1_bus;
    reg  ctrl_in_valid = 1'b0;
    wire ctrl_in_ready;
    always @ ( posedge AXI_aclk ) begin
        if      ( AXI_aresetn == 1'b0 ) ctrl_in_valid <= 1'b0;
        else if ( ctrl_update_axi[REG_CTRL_IN0] | 
                  ctrl_update_axi[REG_CTRL_IN1] ) 
                                        ctrl_in_valid <= 1'b1;
        else if ( ctrl_in_ready )       ctrl_in_valid <= 1'b0;
        else                            ctrl_in_valid <= ctrl_in_valid;
    end
    cdc # ( 
        .SYNC(SYNC), 
        .DATA_WIDTH(AXI_DATA_WIDTH*2), 
        .USE_OUT_READY("NO")
    )
    cdc_ctrl_in (
        .in_clock(AXI_aclk),
        .in_reset_n(AXI_aresetn),               // no software reset
        .in_data({ctrl_in1_axi, ctrl_in0_axi}),
        .in_valid(ctrl_in_valid),
        .in_ready(ctrl_in_ready),
        .out_clock(clk_bus),
        .out_reset_n(reset_hw_bus_n),           // no software reset
        .out_data({ctrl_in1_bus,ctrl_in0_bus}),
        .out_valid(ctrl_in_reload_bus),         // pulses when registers are updated
        .out_ready(1'b1)                        // always ready
    ); 

    // ctrl_out0 and ctrl_out1
    wire ctrl_out_reload_bus;
    wire [AXI_DATA_WIDTH-1 : 0] ctrl_out0_bus;
    wire [AXI_DATA_WIDTH-1 : 0] ctrl_out1_bus;
    reg  ctrl_out_valid = 1'b0;
    wire ctrl_out_ready;
    always @ ( posedge AXI_aclk ) begin
        if      ( AXI_aresetn == 1'b0 ) ctrl_out_valid <= 1'b0;
        else if ( ctrl_update_axi[REG_CTRL_OUT0] | 
                  ctrl_update_axi[REG_CTRL_OUT1] ) 
                                        ctrl_out_valid <= 1'b1;
        else if ( ctrl_out_ready )      ctrl_out_valid <= 1'b0;
        else                            ctrl_out_valid <= ctrl_out_valid;
    end
    cdc # ( 
        .SYNC(SYNC), 
        .DATA_WIDTH(AXI_DATA_WIDTH*2), 
        .USE_OUT_READY("NO")
    )
    cdc_ctrl_out (
        .in_clock(AXI_aclk),
        .in_reset_n(AXI_aresetn),               // no software reset
        .in_data({ctrl_out1_axi, ctrl_out0_axi}),
        .in_valid(ctrl_out_valid),
        .in_ready(ctrl_out_ready),
        .out_clock(clk_bus),
        .out_reset_n(reset_hw_bus_n),           // no software reset
        .out_data({ctrl_out1_bus,ctrl_out0_bus}),
        .out_valid(ctrl_out_reload_bus),        // pulses when registers are updated
        .out_ready(1'b1)                        // always ready
    ); 

    wire force_reload_bus;
    wire [AXI_DATA_WIDTH - 1 : 0] force_out_bus;
    reg  force_valid = 1'b0;
    wire force_ready;
    always @ ( posedge AXI_aclk ) begin
        if      ( AXI_aresetn == 1'b0 ) force_valid <= 1'b0;
        else if ( ctrl_update_axi[REG_FORCE_OUT] ) 
                                        force_valid <= 1'b1;
        else if ( force_ready )         force_valid <= 1'b0;
        else                            force_valid <= force_valid;
    end
    cdc # ( 
        .SYNC(SYNC), 
        .DATA_WIDTH(AXI_DATA_WIDTH), 
        .USE_OUT_READY("NO")
    )
    cdc_force_out (
        .in_clock(AXI_aclk),
        .in_reset_n(AXI_aresetn),               // no software reset
        .in_data(force_out_axi),
        .in_valid(force_valid),
        .in_ready(force_ready),
        .out_clock(clk_bus),
        .out_reset_n(reset_hw_bus_n),           // no software reset
        .out_data(force_out_bus),
        .out_valid(force_reload_bus),           // pulses when register is updated
        .out_ready(1'b1)                        // always ready
    ); 

    //////////////////////////////////////////////////////////////////////////////////
    // synchronize external input @ clk_bus
    
    // synchronize external inputs for triggers @ clk_bus
    // note: there is no way to ensure that these bits are synchronized with each other!
    //       when different inputs are used and might change state at the same time,
    //       ensure that STOP and RESTART trigger are sampled at opposite edges.
    //       for START trigger use auto-sync module (with as_en bit) which introduces a delay 
    //       which should avoid this problem.
    // note: ext_in_bus signal goes directly into 16:1 multiplexer which is a LUT6 on input
    //       SYNC_EXT = 3 is recommended since has 2 synchronization stages (but 2 cycles delay).
    wire [NUM_IN - 1 : 0] ext_in_bus;
    generate
    for (genvar i = 0; i < NUM_IN; i = i + 1) begin : GEN_EXT
        (* ASYNC_REG = "TRUE" *)
        reg [SYNC_EXT-1:0] ext_in_cdc;
        always @ ( posedge clk_bus ) begin
            ext_in_cdc <= {ext_in_cdc[SYNC_EXT-2:0], ext_in[i]};
        end
        assign ext_in_bus[i] = ext_in_cdc[SYNC_EXT-1];
    end
    endgenerate

    // synchronize irq's at clk_bus
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] irq_TX_ff;    
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] irq_RX_ff;    
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] irq_FPGA_ff;    
    always @ ( posedge clk_bus ) begin
        irq_TX_ff   <= {irq_TX_ff  [SYNC-2:0], irq_TX};
        irq_RX_ff   <= {irq_RX_ff  [SYNC-2:0], irq_RX};
        irq_FPGA_ff <= {irq_FPGA_ff[SYNC-2:0], irq_FPGA};
    end
    wire irq_TX_bus   = irq_TX_ff[SYNC-1];    
    wire irq_RX_bus   = irq_RX_ff[SYNC-1];    
    wire irq_FPGA_bus = irq_FPGA_ff[SYNC-1];

    //////////////////////////////////////////////////////////////////////////////////
    // synchronize start trigger (sync_in) @ clk_det
    // TODO: not needed after auto-sync module is removed in the near future.

    // reset CDC from clock_bus to clock_det
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] reset_n_det_ff;    
    always @ ( posedge clk_det ) begin
        reset_n_det_ff <= {reset_n_det_ff[SYNC-2:0],reset_bus_n};
    end
    wire reset_det_n = reset_n_det_ff[SYNC-1];    

    // ctrl_in0 @ clk_det
    wire [AXI_DATA_WIDTH - 1: 0] ctrl_in0_det;
    reg  in_det_valid = 1'b0;
    wire in_det_ready;
    always @ ( posedge AXI_aclk ) begin
        if      ( AXI_aresetn == 1'b0 ) in_det_valid <= 1'b0;
        else if ( ctrl_update_axi[REG_CTRL_IN0] ) 
                                        in_det_valid <= 1'b1;
        else if ( in_det_ready )        in_det_valid <= 1'b0;
        else                            in_det_valid <= in_det_valid;
    end
    cdc # ( 
        .SYNC(SYNC), 
        .DATA_WIDTH(AXI_DATA_WIDTH), 
        .USE_OUT_READY("NO")
    )
    cdc_det (
        .in_clock(AXI_aclk),
        .in_reset_n(AXI_aresetn),
        .in_data(ctrl_in0_axi),
        .in_valid(in_det_valid),
        .in_ready(in_det_ready),
        .out_clock(clk_det),
        .out_reset_n(reset_det_n),
        .out_data(ctrl_in0_det),
        .out_valid(),                           // pulses when register is updated
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
    
    // timing module = bus data generation
    wire [STREAM_DATA_WIDTH - 1 : 0] out_data_bus;
    wire out_last_bus;
    wire out_valid_bus;
    wire out_ready_bus;
    wire as_run;                // enable as module
    wire as_start;              // as start signal recieved
    wire start_trg_en_bus;
    wire start_trg_tgl_bus;
    wire start_trg_tgl_det;
    wire stop_trg_tgl_bus;
    wire restart_trg_tgl_bus;
    wire sync_out_bus;
    wire sync_mon_bus;
    wire timing_status_update;
    wire TX_full_bus;
    wire RX_full_bus;
    wire RX_empty_bus;
    dio24_timing # (
        .STREAM_DATA_BITS(STREAM_DATA_WIDTH + 1),
        .BUS_DATA_BITS(BUS_DATA_BITS),
        .BUS_ADDR_BITS(BUS_ADDR_BITS),
        .BUS_ADDR_1_USE(BUS_ADDR_1_USE),
        .BUS_RESET(BUS_RESET),
        .NUM_STRB(NUM_STRB),
        .NUM_STRB_CONT(NUM_STRB_CONT),
        .REG_BITS(AXI_DATA_WIDTH),
        .CTRL_BITS(TIMING_CTRL_BITS),
        .STATUS_BITS(TIMING_STATUS_BITS),
        .CLK_DIV_BITS(CLK_DIV_BITS),
        .SYNC_DELAY_BITS(SYNC_DELAY_BITS),
        .NUM_IN(NUM_IN),
        .NUM_OUT(NUM_OUT),
        .NUM_LED(NUM_LED),
        .NUM_BUS_EN(NUM_BUS_EN),
        .SYNC(SYNC),
        .IRQ_FREQ_BITS(IRQ_FREQ_BITS)
    )
    timing (
        // clocks and reset
        .clk_bus            (clk_bus),
        .clk_det            (clk_det),
        .reset_bus_n        (reset_bus_n),
        .reset_hw_bus_n     (reset_hw_bus_n),
        .reset_det_n        (reset_det_n),
        // control bits
        .ctrl_bits          (timing_ctrl_bus),
        .num_samples        (num_samples_bus),
        .num_cycles         (num_cycles_bus),
        .num_reload         (num_reload_bus),           // pulses when num_samples/cycles are updated
        .clk_div            (clk_div_bus),
        .strb_delay         (strb_delay_bus),
        .timing_reload      (timing_reload_bus),        // pulses when clk_div and strb_delay are updated
        .sync_delay         (sync_delay_bus),
        .sync_delay_reload  (sync_delay_reload_bus),    // pulses when sync_delay is updated
        .ctrl_in0_det       (ctrl_in0_det),
        .ctrl_in0           (ctrl_in0_bus),
        .ctrl_in1           (ctrl_in1_bus),
        .ctrl_in_reload     (ctrl_in_reload_bus),       // pulses when ctrl_in0/1 are updated
        .ctrl_out0          (ctrl_out0_bus),
        .ctrl_out1          (ctrl_out1_bus),
        .ctrl_out_reload    (ctrl_out_reload_bus),      // pulses when ctrl_out0/1 are updated
        .force_out          (force_out_bus),
        .force_reload       (force_reload_bus),         // pulses when force_out is updated
        // external I/O @ clk_bus
        .ext_in             (ext_in_bus),
        .ext_out            (ext_out),
        .led_out            (led_bus),
        .irq_TX             (irq_TX_bus),
        .irq_RX             (irq_RX_bus),
        .irq_FPGA           (irq_FPGA_bus),
        .TX_full            (TX_full_bus),
        .TX_empty           (TX_empty_bus),
        .RX_full            (RX_full_bus),
        .RX_empty           (RX_empty_bus),
        //.trg_start(trg_start_bus),
        // auto-sync control/status bits
        //.as_en              (as_en_bus),
        .as_run             (as_run),
        .as_start           (as_start),
        .sync_out           (sync_out_bus),
        .sync_mon           (sync_mon_bus),
        .sync_en            (as_active_bus),        
        // status bits and board time & samples
        .status_bits        (timing_status_bus),
        .board_time         (board_time_bus),
        .board_samples      (board_samples_bus),
        .board_time_ext     (board_time_ext_bus),
        .board_samples_ext  (board_samples_ext_bus),
        .board_cycles       (board_cycles_bus),
        .status_update      (timing_status_update),     // not used
        // TX stream data input
        .in_data            ({in_last_bus,in_data_bus}),
        .in_valid           (in_valid_bus),
        .in_ready           (in_ready_bus),
        // RX stream data output
        .out_data           ({out_last_bus,out_data_bus}),
        .out_valid          (out_valid_bus),
        .out_ready          (out_ready_bus),
        // bus output
        .bus_data           (bus_data),
        .bus_addr_0         (bus_addr_0),
        .bus_addr_1         (bus_addr_1),
        .bus_strb           (bus_strb),
        .bus_en             (bus_en),
        // trigger signals
        .start_trg_en       (start_trg_en_bus),
        .start_trg_tgl      (start_trg_tgl_bus),
        .start_trg_tgl_det  (start_trg_tgl_det),        // @ clk_det
        .stop_trg_tgl       (stop_trg_tgl_bus),
        .restart_trg_tgl    (restart_trg_tgl_bus)
    );
        
    wire [4*AUTO_SYNC_TIME_BITS-1:0] sync_time_det;
    wire as_timeout_det;
    wire as_done_det;
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
        .DELAY_BITS(SYNC_DELAY_BITS)
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
        .as_run_start(as_run),
        
        // status bits
        .as_active(as_active_bus),          // @ clk_bus
        .as_timeout(as_timeout_det),        // @ clk_det
        .as_done(as_done_det),              // @ clk_det
                
        // external auto-sync input and outputs
        .sync_out(sync_out_bus),                        // @ clk_bus
        //.sync_en(sync_en_bus),                        // @ clk_bus
        .sync_mon(sync_mon_det),                        // @ clk_det
        .sync_in_tgl_bus(start_trg_tgl_bus),            // @ clk_bus
        .sync_in_tgl_det(start_trg_tgl_det),            // @ clk_det
                        
        // measured round-trip time {t1_PS,,t0_PS,t1,t0} and timeout @ clk_det
        .sync_time(sync_time_det),

        // sync delay time at clk_bus
        .sync_delay(sync_delay_bus),
        
        // auto-sync start signal. pulses for 1 clk_bus cycle.
        .as_start(as_start)
        );
                
    // sync_time, timeout and done CDC from clock_det to clock_pclk = AXI_aclk
    wire [4*AUTO_SYNC_TIME_BITS-1:0] sync_time_axi_w;
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
        .out_clock(AXI_aclk),
        .out_reset_n(reset_AXI_sw_n),
        .out_data({as_timeout_axi,sync_time_axi_w}),
        .out_valid(as_done_axi),// pulses when bits have been reloaded
        .out_ready(1'b1) // always ready
    );
    if (AXI_DATA_WIDTH > 4*AUTO_SYNC_TIME_BITS) begin
        assign sync_time_axi = {{(AXI_DATA_WIDTH-4*AUTO_SYNC_TIME_BITS){1'b0}},sync_time_axi_w};
    end
    else begin
        assign sync_time_axi = sync_time_axi_w[AXI_DATA_WIDTH-1:0];
    end

    //////////////////////////////////////////////////////////////////////////////////
    // multiplex and sync outputs @ AXI_aclk 

    /* synchronize sync_out at AXI_aclk
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] sync_out_axi_cdc;
    always @ ( posedge AXI_aclk ) begin
        sync_out_axi_cdc <= {sync_out_axi_cdc[SYNC-2:0],sync_out_bus};
    end
    wire sync_out_axi = sync_out_axi_cdc[SYNC-1];

    // synchronize sync_mon at AXI_aclk
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] sync_mon_axi_cdc;
    always @ ( posedge AXI_aclk ) begin
        sync_mon_axi_cdc <= {sync_mon_axi_cdc[SYNC-2:0],sync_mon_det};
    end
    wire sync_mon_axi = sync_mon_axi_cdc[SYNC-1];*/

    // synchronize sync_mon at clk_bus
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] sync_mon_bus_cdc;
    always @ ( posedge clk_bus ) begin
        sync_mon_bus_cdc <= {sync_mon_bus_cdc[SYNC-2:0],sync_mon_det};
    end
    assign sync_mon_bus = sync_mon_bus_cdc[SYNC-1];

    // synchronize trg_start at AXI_aclk
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] trg_start_axi_cdc;
    always @ ( posedge AXI_aclk ) begin
        //trg_start_AXI_cdc <= {trg_start_AXI_cdc[SYNC-2:0],trg_start_bus};
        trg_start_axi_cdc <= {trg_start_axi_cdc[SYNC-2:0], start_trg_tgl_bus};
    end
    wire trg_start_axi = trg_start_axi_cdc[SYNC-1];

    // synchronize trg_stop at AXI_aclk
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] trg_stop_axi_cdc;
    always @ ( posedge AXI_aclk ) begin
        //trg_stop_AXI_cdc <= {trg_stop_AXI_cdc[SYNC-2:0],trg_stop_bus};
        trg_stop_axi_cdc <= {trg_stop_axi_cdc[SYNC-2:0], stop_trg_tgl_bus};
    end
    wire trg_stop_axi = trg_stop_axi_cdc[SYNC-1];

    // synchronize trg_restart at AXI_aclk
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] trg_restart_axi_cdc;
    always @ ( posedge AXI_aclk ) begin
        //trg_restart_AXI_cdc <= {trg_restart_AXI_cdc[SYNC-2:0],trg_restart_bus};
        trg_restart_axi_cdc <= {trg_restart_axi_cdc[SYNC-2:0], restart_trg_tgl_bus};
    end
    wire trg_restart_axi = trg_restart_axi_cdc[SYNC-1];
    
    // synchronize TX/RX_full signals at AXI_aclk
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] TX_full_cdc;
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] RX_full_cdc;
    always @ ( posedge AXI_aclk ) begin
        TX_full_cdc <= {TX_full_cdc[SYNC-2:0], TX_full_axis};
        RX_full_cdc <= {RX_full_cdc[SYNC-2:0], RX_full_bus };
    end
    assign TX_full_axi = TX_full_cdc[SYNC-1];
    assign RX_full_axi = RX_full_cdc[SYNC-1];

    // synchronize TX_full/RX_empty signals at clk_bus
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] TX_full_cdc_bus;
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] RX_empty_cdc_bus;
    always @ ( posedge clk_bus ) begin
        TX_full_cdc_bus  <= {TX_full_cdc_bus [SYNC-2:0], TX_full_axis};
        RX_empty_cdc_bus <= {RX_empty_cdc_bus[SYNC-2:0], RX_empty_axis};
    end
    assign TX_full_bus  = TX_full_cdc_bus [SYNC-1];
    assign RX_empty_bus = RX_empty_cdc_bus[SYNC-1];

    //////////////////////////////////////////////////////////////////////////////////
    // RX FIFO @ clk_bus -> AXIS_out_aclk 
    
    wire [STREAM_DATA_WIDTH - 1 : 0] out_data_RX;        
    wire out_last_RX;
    wire out_ready_RX;
    wire out_valid_RX;
    dio24_FIFO # (
        .STREAM_DATA_WIDTH(STREAM_DATA_WIDTH + 1),
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
        .in_full(RX_full_bus),
        .out_clock(AXIS_out_aclk),
        .out_reset_n(reset_out_stream_n & AXIS_out_aresetn),
        .out_data({out_last_RX,out_data_RX}),
        .out_valid(out_valid_RX),
        .out_ready(out_ready_RX),
        .out_empty(RX_empty_axis)
    );
   
    //////////////////////////////////////////////////////////////////////////////////
    // output AXI stream @ AXIS_out_clk

    /* expand RX stream data output to 64/96bits per sample
    // TODO: either switch dynamically or directly send data without expanding?
    //       another idea would be to send data back into TX FIFO for fast in-buffer repeated waveforms.
    //       this way both buffers could be used for storage and we would have 16k samples.
    wire [STREAM_DATA_WIDTH - 1 : 0] out_data_smpl;
    wire out_last_smpl;
    wire out_valid_smpl;
    wire out_ready_smpl;    
    if (STREAM_DATA_WIDTH != (TIME_BITS + DATA_BITS)) begin
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
        if ( STREAM_DATA_WIDTH > SEL_HE ) begin
           assign out_data_smpl[STREAM_DATA_WIDTH - 1 : SEL_HE] = {(STREAM_DATA_WIDTH - SEL_HE){1'b0}};
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
    if (STREAM_DATA_WIDTH != STREAM_DATA_WIDTH) begin : OUT_CONV
       stream_convert # (
           .IN_BYTES(STREAM_DATA_WIDTH/8),
           .OUT_BYTES(STREAM_DATA_WIDTH/8)
       )
       out_conv (
           // clock and reset
           .clock(AXIS_out_aclk),
           .reset_n(reset_out_stream_n & AXIS_out_aresetn),
           // error keep
           .error_keep(error_keep_stream[2]),
           // data input
           .in_data(out_data_smpl),
           .in_last(out_last_smpl),
           .in_keep({(STREAM_DATA_WIDTH/8){1'b1}}), // all BYTES are used
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
       assign out_keep = {(STREAM_DATA_WIDTH/8){1'b1}};
       assign out_valid = out_valid_smpl;
       assign out_ready_smpl = AXIS_out_tready;
    end
    */
    
    // TODO: either switch dynamically or directly send data without expanding?
    assign AXIS_out_tdata  = out_data_RX;
    assign AXIS_out_tlast  = out_last_RX;
    assign AXIS_out_tkeep  = {(STREAM_DATA_WIDTH/8){1'b1}};
    assign AXIS_out_tvalid = out_valid_RX;
    assign out_ready_RX    = AXIS_out_tready;
        
endmodule
