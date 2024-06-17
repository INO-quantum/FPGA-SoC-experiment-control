`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// test bench for ExpCtrl_top module
// created 24/03/2020 by Andi
// last change 2024/06/17 by Andi
//////////////////////////////////////////////////////////////////////////////////

module ExpCtrl_tb # (
    // fixed data widths needed for port definitions. do not change.
    parameter integer AXI_ADDR_WIDTH = 7,       // 7: 2^7/4 = 32 registers
    parameter integer AXI_DATA_WIDTH = 32,      // must be 32
    parameter integer STREAM_DATA_WIDTH  = 128,      // no limits, typically power of 2 from FIFO like 64, 128, etc.
    parameter integer BUS_ADDR_BITS = 8,        // 7 or 8
    parameter integer BUS_DATA_BITS = 16,       // 16
    parameter integer NUM_STRB              = 2,        // number of bits for bus_strb (1 or 2)
    parameter integer NUM_BUS_EN            = 2,        // number of bits for bus_en (1 or 2)
    
    // AXI stream bus
    parameter integer BITS_PER_SAMPLE  = 64,        // 64 (1 rack) or 96 (2 racks)
    
    // user-provided version and info register content
    parameter integer VERSION               = 32'h0103_2F2b, // version register 0xMM.mm_(year-2000)<<9+month<<5+day 
    parameter integer INFO                  = 32'h0000_0000,  // info  register, 0xc1 = Cora-Z7-10

    // I/O bits
    parameter integer NUM_IN_BITS = 3,          // number of external inputs
    parameter integer NUM_OUT_BITS = 3,         // number of external outputs

    // LEDs and buttons 
    parameter integer NUM_BUTTONS = 2,          // must be 2
    parameter integer NUM_LED_RED = 2,          // must be 2
    parameter integer NUM_LED_GREEN = 2,        // must be 2
    parameter integer NUM_LED_BLUE = 2,         // must be 2
    // bits used for blinking leds ON-time: 1=50%, 2=25%, 3=12.5%, 4=6.25%
    parameter integer LED_BLINK_ON = 3,
    // bits used for blinking leds
    parameter LED_SLOW = 26,              // blink slow
    parameter LED_FAST = 24,              // blink fast (1.. < LED_SLOW)
    // bits used for PWM dimming of leds. 0 = no dimming.
    parameter LED_DIM_LOW = 8,            // dim level low (< LED_SLOW)
    parameter LED_DIM_HIGH = 6,           // dim level high (< LED_SLOW)
    parameter LED_BRIGHT_LOW = 1,         // bright level low (< LED_SLOW)
    parameter LED_BRIGHT_HIGH = 1,        // bright level high (1 .. < LED_SLOW)
    
    // data and time bits
    parameter integer TIME_BITS             = AXI_DATA_WIDTH,   // must be 32
    parameter integer TIME_START            = 0,                // typically 0
    parameter integer DATA_BITS             = AXI_DATA_WIDTH,   // must be 32
    parameter integer DATA_START_64         = 32,               // typically 32
    parameter integer DATA_START_96_0       = 32,               // typically 32
    parameter integer DATA_START_96_1       = 64,               // typically 64    
    parameter integer CLK_DIV_BITS          = 8,                // 8
    parameter integer TRG_DIV_BITS          = 8,                // 8
    parameter integer STRB_DELAY_BITS       = 8,                // 8    
    
    // auto-sync
    parameter integer AUTO_SYNC_PULSE_LENGTH = 3,               // 2 = 40ns @ 50MHz 
    parameter integer AUTO_SYNC_PULSE_WAIT   = 5,               // 3 = 60ns @ 50MHz, wait time after pulse
    parameter integer AUTO_SYNC_MAX_PULSES   = 2,               // 2 
    parameter integer AUTO_SYNC_TIME_BITS    = 8,               // 8
    parameter integer AUTO_SYNC_DELAY_BITS   = 10,               // 10
    parameter integer AUTO_SYNC_PHASE_BITS   = 12,               // 12     
    
    // bus data and address bits without strobe bit
    parameter         BUS_ADDR_1_USE = "DATA_HIGH",    // "ZERO"/"ADDR0"/"DATA_HIGH" = low / same as bus_addr_0, data[31:24] 

    
    // special data bits
    parameter integer BIT_NOP  = 31,             // 31
    parameter integer BIT_TRST = 30,            // 30
    parameter integer BIT_IRQ  = 29,             // 29
    parameter integer BIT_STOP = 28,            // 28, when set board waits for next start trigger
    
    // strobe bit in address data
    parameter integer BIT_STROBE = BUS_DATA_BITS + BUS_ADDR_BITS, // strobe bit = last address bit
    parameter         USE_STROBE = "YES",       // "YES" = data output when BIT_STROBE toggles, otherwise BIT_STROBE is ignored.
             
    parameter integer SYNC = 2,                 // 2-3
    
    // irq_FPGA frequency bits
    parameter integer IRQ_FREQ_BITS = 4,        // set to 4 if want to see this
    
    parameter integer ERROR_LOCK_DELAY = 8,    // 5/6/8 = 1/2/3 clk_AXI cycles of clk_ext_clock loss is acceptable 
    
    // TX and RX FIFO
    parameter integer TX_FIFO_DEPTH = 8192,
    parameter integer RX_FIFO_DEPTH = 8192
)
(
    // no inputs or outputs for test bench
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

    // registers
    localparam integer REG_LEN          = 4;
    localparam integer REG_CTRL         = 0*REG_LEN;
    localparam integer REG_CTRL_TRG     = 1*REG_LEN;
    localparam integer REG_CTRL_OUT     = 2*REG_LEN;
    localparam integer REG_NUM_SAMPLES  = 3*REG_LEN;
    localparam integer REG_CLK_DIV      = 4*REG_LEN;
    localparam integer REG_STRB_DELAY   = 5*REG_LEN;
    localparam integer REG_SYNC_DELAY   = 6*REG_LEN;
    localparam integer REG_SYNC_PHASE   = 7*REG_LEN;

    // number of generated samples    
    // note: driver sends data in multiples of 16 bytes (128 bits)
    //       i.e.  2 samples a 8 bytes or 4/3 samples a 12 bytes with NOP data padded
    localparam integer GEN_NUM_SAMPLES = 17;
    
    // number of runs
    // after each run performs a software reset.
    // for details of each run see CTRL_BITS_ definitions below
    localparam integer RUNS = 13;
    
    // abort data ouput in given run
    localparam integer RUN_ABORT_0 = 4; // wait RUN_ABORT_SAMPLES samples, then reset run bit = STOP command before sw_reset
    localparam integer RUN_ABORT_1 = 5; // wait until wait state, then reset run_bit = STOP command before sw_reset
    localparam integer RUN_ABORT_2 = 11; // wait until wait state, then sw_reset without STOP.
    localparam integer RUN_ABORT_SAMPLES = GEN_NUM_SAMPLES - 5;
    
    // experimental run and samples where clock is lost
    localparam integer RUN_CLOCK_LOSS_SHORT = 8;
    localparam integer RUN_CLOCK_LOSS = 9;
    localparam integer RUN_CLOCK_LOSS_IGNORE = 10;
    localparam integer RUN_CLOCK_LOSS_SAMPLES = 6;

    // clock divider for bus
    localparam integer CLK_DIV          = 20;   // clock divider (normally 100)
    localparam integer TRG_DIV          = 10;   // stop trigger window divider. 0=immediate stop,  
    
    // strobe delay {strb_end_1,strb_start_1,strb_end_0,strb_start_0}
    // strb_end = 0x00 = toggle strobe at given strb_start
    localparam integer STRB_DELAY = 32'h0005_0b06;
    
    // sync delay in cycle for secondary board
    localparam integer SYNC_DELAY = 20;
    
    // sync phase {ext,det} in pulses 0 - AS_PHASE_MAX
    localparam integer AS_PHASE_MAX = 560;              // max @ 100MHz
    localparam integer AS_PHASE_EXT = (0*AS_PHASE_MAX)/360;
    localparam integer AS_PHASE_DET = (0*AS_PHASE_MAX)/360;
    localparam integer SYNC_PHASE   = ((AS_PHASE_EXT & AUTO_SYNC_PHASE_BITS) << AUTO_SYNC_PHASE_BITS) | 
                                      (AS_PHASE_DET & AUTO_SYNC_PHASE_BITS);
    
    // clock and reset settings in ns
    localparam integer PERIOD_AXI       = 13;           // AXI Lite clock (<= PL) [100MHz]
    localparam integer PERIOD_STREAM    = 9;            // stream data clock PL [100MHz]
    localparam integer PERIOD_BUS       = 10;           // main clock. typically PL but can be locked externally. [100MHz]
    localparam integer PERIOD_LINE      = 990;         // line trigger period used as tart trigger
    localparam integer PERIOD_LINE_NUM  = 40;           // in PERIOD_LINE_NUM loops we add to line period PERIOD_LINE_ADD
    localparam integer PERIOD_LINE_ADD  = 100;          // in PERIOD_LINE_NUM loops we add to line period PERIOD_LINE_ADD
    localparam integer PERIOD_PWM       = 20;           // slow clock for PWM of LEDs [10MHz]
    localparam integer PHASE_DET        = (PERIOD_BUS * 350)/360;        // detection clock phase shift
    localparam integer RESET_PS_CYCLES  = 5;            // hardware reset cycles PS clock
    localparam integer RESET_AXI_CYCLES = 5;            // hardware reset cycles AXI clock
    localparam integer RESET_BUS_CYCLES = 30;           // hardware reset cycles bus clock
    localparam integer RESET_STREAM_CYCLES = 30;        // hardware reset cycles stream clock
    // * the phase at 0 is the same as 360 degree, i.e. the maximum phase
    //   for demonstration we set PHASE_STRB_0 to minimum and PHASE_STRB_1 to maximum phase-1ns
    
    // inserts in generated data TIME_ERROR_TIME_i after TIME_ERROR_i.
    // disabled for TIME_ERROR_i < 0
    // you can make different time jumps and introduce time errors with time[k] <= time[k-1], or set time for TIME_TRST.
    // next time increments from this time
    localparam integer TIME_JUMP_0       = -4;
    localparam integer TIME_JUMP_TIME_0  = 8;
    localparam integer TIME_JUMP_1       = -8;
    localparam integer TIME_JUMP_TIME_1  = 11;
    localparam integer TIME_JUMP_2       = -12;
    localparam integer TIME_JUMP_TIME_2  = 14;
    localparam integer TIME_JUMP_3       = -12;
    localparam integer TIME_JUMP_TIME_3  = 17;
    localparam integer TIME_JUMP_4       = -12;
    localparam integer TIME_JUMP_TIME_4  = 23;

    // sets in generated data NOP bit at given time
    // disabled when < 0
    // TODO: does not work with time = 0
    localparam integer TIME_NOP_0       = 5;
    localparam integer TIME_NOP_1       = 12;
    localparam integer TIME_NOP_2       = -4;
    localparam integer TIME_NOP_3       = -5;
    localparam integer TIME_NOP_4       = -6;
    localparam integer NUM_NOP          = ((TIME_NOP_0 >= 0) ? 1 : 0) + 
                                          ((TIME_NOP_1 >= 0) ? 1 : 0) + 
                                          ((TIME_NOP_2 >= 0) ? 1 : 0) + 
                                          ((TIME_NOP_3 >= 0) ? 1 : 0) +
                                          ((TIME_NOP_4 >= 0) ? 1 : 0);
                                          
    // do not toggle BIT_STROBE for the given sample
    // if USE_STROBE = "YES" has the same effect as TIME_NOP, otherwise is ignored.
    // disabled when < 0
    // TODO: problem with simulation when set to 2.
    localparam integer SKIP_STRB_0      = 3;
    localparam integer SKIP_STRB_1      = 8;
    localparam integer SKIP_STRB_2      = -5;
    localparam integer SKIP_STRB_3      = -5;
    localparam integer SKIP_STRB_4      = -5;
    localparam integer NUM_SKIP_STRB    = (USE_STROBE != "YES") ? 0 :
                                          ((SKIP_STRB_0 >= 0) ? 1 : 0)+ 
                                          ((SKIP_STRB_1 >= 0) ? 1 : 0) +
                                          ((SKIP_STRB_2 >= 0) ? 1 : 0) +
                                          ((SKIP_STRB_3 >= 0) ? 1 : 0) +
                                          ((SKIP_STRB_4 >= 0) ? 1 : 0);

    // sets in generated data TRST bit at time = TIME_TRST_i
    // disabled for TIME_TRST_i < 0 
    // use TIME_JUMP_i to set time
    // next time increments from this time
    localparam integer TIME_TRST_0       = -10;
    localparam integer TIME_TRST_1       = -7;
    localparam integer TIME_TRST_2       = -7;
    localparam integer TIME_TRST_3       = -7;
    localparam integer TIME_TRST_4       = -7;

    // data generator settings
    localparam integer GEN_DATA_WIDTH    = 32;
    localparam integer GEN_TIME_WIDTH    = 32;
    localparam integer GEN_DATA_START    = 'h0003_0201;    // initial data + address
    localparam integer GEN_DATA_STEP     = 'h0001_0101;    // added in every step
    localparam integer GEN_TIME_START    = 'h0000_0000;    // initial time >= 0
    localparam integer GEN_TIME_STEP     = 'h0000_0001;    // added in every step >= 1
    localparam integer GEN_STRB_START    = 1'b0;           // starting strobe bit (should not matter)
    localparam integer GEN_STRB_TOGGLE   = "YES";          // "YES" = toggle strobe bit, otherwise not.
    localparam integer STROBE_SET        = (1 << BIT_STROBE); // strobe bit in data
    localparam integer GEN_DATA_START_STRB = ((USE_STROBE == "YES") && (GEN_STRB_START == 1'b1)) ? GEN_DATA_START | STROBE_SET : GEN_DATA_START; 

    // control and status bits
    localparam integer CTRL_RESET        = 'h0000_0001;    // software RESET bit
    localparam integer CTRL_READY        = 'h0000_0002;    // READY bit
    localparam integer CTRL_RUN          = 'h0000_0004;    // RUN bit
    localparam integer CTRL_RESTART      = 'h0000_0010;    // RESTART bit
    localparam integer CTRL_AS_EN        = 'h0000_0020;    // auto-sync enable
    localparam integer CTRL_AS_PRIM      = 'h0000_0040;    // auto-sync primary board: used only in simulation.
    localparam integer CTRL_CLK_EXT      = 'h0000_0400;    // external clock
    localparam integer CTRL_ERR_LOCK_EN  = 'h0000_8000;    // enable error when external clock lost
    localparam integer CTRL_IRQ_EN       = 'h0010_0000;    // enable IRQs
    localparam integer CTRL_64           = 'h01F0_0002;    // config IRQ_IRQ_ALL|READY
    localparam integer CTRL_96           = 'h01F0_0102;    // config IRQ_IRQ_ALL|BPS96|READY
    localparam integer STATUS_RESET      = 'h0000_0001;    // RESET bit
    localparam integer STATUS_READY      = 'h0000_0002;    // READY bit
    localparam integer STATUS_RUN        = 'h0000_0004;    // RUN bit
    localparam integer STATUS_END        = 'h0000_0008;    // END bit
    localparam integer STATUS_RESTART    = 'h0000_0010;    // RESTART bit
    localparam integer STATUS_EXT_CLK    = 'h0000_0400;    // external clock selected
    localparam integer STATUS_LOCKED     = 'h0000_0800;    // external clock locked
    localparam integer STATUS_ERR_LOCK   = 'h0000_8000;    // external clock lost
    localparam integer STATUS_ERR_ALL    = 'h0007_f000;    // all error bits
    localparam integer STATUS_IRQ_ALL    = 'h01f0_0000;    // all IRQ bits
    localparam integer STATUS_IRQ_ERR    = 'h0010_0000;    // IRQ_ERROR bit
    localparam integer STATUS_IRQ_END    = 'h0020_0000;    // IRQ_END bit
    localparam integer STATUS_IRQ_RESTART= 'h0040_0000;    // IRQ_RESTART bit
    localparam integer STATUS_IRQ_FREQ   = 'h0080_0000;    // IRQ_FREQ bit
    localparam integer STATUS_RST_END    = 'h0000_0000;    // status after reset
    
    // trigger control register
    localparam integer CTRL_TRG_SRC_BITS        = 3;
    localparam integer CTRL_TRG_LEVEL_BITS      = 2;
    localparam integer CTRL_TRG_DST_BITS        = CTRL_TRG_SRC_BITS + CTRL_TRG_LEVEL_BITS;
    
    // trigger destinations offsets (max. 6 possible)
    localparam integer CTRL_TRG_DST_NUM         = 3;
    localparam integer CTRL_TRG_DST_START       = 0*CTRL_TRG_DST_BITS;  // start trigger
    localparam integer CTRL_TRG_DST_STOP        = 1*CTRL_TRG_DST_BITS;  // stop trigger
    localparam integer CTRL_TRG_DST_RESTART     = 2*CTRL_TRG_DST_BITS;  // restart trigger
    
    // trigger sources (max. 7 possible)
    localparam integer CTRL_TRG_SRC_NONE        = 0;    // no trigger input
    localparam integer CTRL_TRG_SRC_IN0         = 1;    // ext_in[0]
    localparam integer CTRL_TRG_SRC_IN1         = 2;    // ext_in[1]
    localparam integer CTRL_TRG_SRC_IN2         = 3;    // ext_in[2]
    localparam integer CTRL_TRG_SRC_DATA        = 4;    // data BIT_STOP, used only for CTRL_TRG_DST_STOP

    // trigger levels (all 4 possible used)
    localparam integer CTRL_TRG_LEVEL_LOW       = 0;    // level low
    localparam integer CTRL_TRG_LEVEL_HIGH      = 1;    // level higth
    localparam integer CTRL_TRG_EDGE_FALLING    = 2;    // edge falling
    localparam integer CTRL_TRG_EDGE_RISING     = 3;    // edge rising

    // output control register
    localparam integer CTRL_OUT_SRC_BITS        = 4;
    localparam integer CTRL_OUT_LEVEL_BITS      = 2;
    localparam integer CTRL_OUT_DST_BITS        = CTRL_OUT_SRC_BITS + CTRL_OUT_LEVEL_BITS;

    // output destinations offsets (max. 5 possible)
    localparam integer CTRL_OUT_DST_NUM         = 5;
    localparam integer CTRL_OUT_DST_OUT0        = 0*CTRL_OUT_DST_BITS;  // ext_out[0]
    localparam integer CTRL_OUT_DST_OUT1        = 1*CTRL_OUT_DST_BITS;  // ext_out[1]
    localparam integer CTRL_OUT_DST_OUT2        = 2*CTRL_OUT_DST_BITS;  // ext_out[2]
    localparam integer CTRL_OUT_DST_BUS_EN_0    = 3*CTRL_OUT_DST_BITS;  // ext_out[0]
    localparam integer CTRL_OUT_DST_BUS_EN_1    = 4*CTRL_OUT_DST_BITS;  // ext_out[1]

    // output sources (max. 16 possible)
    localparam integer CTRL_OUT_SRC_NONE        = 0;    // fixed output with given level
    localparam integer CTRL_OUT_SRC_SYNC_OUT    = 1;    // sync_out
    localparam integer CTRL_OUT_SRC_SYNC_EN     = 2;    // sync_en (this is sync_FET signal)
    localparam integer CTRL_OUT_SRC_SYNC_MON    = 3;    // sync_mon (used for debugging)
    localparam integer CTRL_OUT_SRC_CLK_LOST    = 4;    // clock lost
    localparam integer CTRL_OUT_SRC_ERROR       = 5;    // error
    localparam integer CTRL_OUT_SRC_RUN         = 6;    // run
    localparam integer CTRL_OUT_SRC_WAIT        = 7;    // run, also high during run_wait state.
    localparam integer CTRL_OUT_SRC_READY       = 8;    // ready (not really needed)
    localparam integer CTRL_OUT_SRC_RESTART     = 9;    // restart (toogle bit in cycling mode, could also indicate restart trigger)
    localparam integer CTRL_OUT_SRC_TRG_START   = 10;   // start trigger toggle signal
    localparam integer CTRL_OUT_SRC_TRG_STOP    = 11;   // stop trigger toggle signal
    localparam integer CTRL_OUT_SRC_TRG_RESTART = 12;   // restart trigger toggle signal
        
    // output levels (max. 4 possible)
    localparam integer CTRL_OUT_LEVEL_LOW       = 0;    // level low = inverted
    localparam integer CTRL_OUT_LEVEL_HIGH      = 1;    // level high = normal

    // start trigger    
    localparam integer START_TRG_SRC = CTRL_TRG_SRC_IN0;
    localparam START_TRG_EDGE = "YES";
    localparam START_TRG_INVERTED = "NO";
    
    // stop trigger    
    localparam integer STOP_TRG_SRC = CTRL_TRG_SRC_IN1;
    localparam STOP_TRG_EDGE = "YES";
    localparam STOP_TRG_INVERTED = "NO";

    // restart trigger    
    localparam integer RESTART_TRG_SRC = CTRL_TRG_SRC_IN0;
    localparam RESTART_TRG_EDGE = "YES";
    localparam RESTART_TRG_INVERTED = "NO";
    
    // sync_out
    localparam integer SYNC_OUT_DST = CTRL_OUT_DST_OUT0;
    localparam SYNC_OUT_INVERTED = "YES";

    // bus enable 0
    localparam integer BUS_EN_0_DST = CTRL_OUT_DST_BUS_EN_0;
    localparam BUS_EN_0_INVERTED = "YES";
    localparam BUS_EN_0_SRC = CTRL_OUT_SRC_NONE;

    // bus enable 1
    localparam integer BUS_EN_1_DST = CTRL_OUT_DST_BUS_EN_1;
    localparam BUS_EN_1_INVERTED = "NO";
    localparam BUS_EN_1_SRC = CTRL_OUT_SRC_NONE;

    localparam integer CTRL_TRG_START    = ( START_TRG_SRC | 
                                           (((START_TRG_EDGE == "YES") ? (( START_TRG_INVERTED == "NO") ? CTRL_TRG_EDGE_RISING : CTRL_TRG_EDGE_FALLING) :
                                                                         (( START_TRG_INVERTED == "NO") ? CTRL_TRG_LEVEL_HIGH  : CTRL_TRG_LEVEL_LOW)     ) << CTRL_TRG_SRC_BITS)) << CTRL_TRG_DST_START;  

    localparam integer CTRL_TRG_STOP     = ( STOP_TRG_SRC | 
                                           (((STOP_TRG_EDGE  == "YES") ? (( STOP_TRG_INVERTED  == "NO") ? CTRL_TRG_EDGE_RISING : CTRL_TRG_EDGE_FALLING) :
                                                                         (( STOP_TRG_INVERTED  == "NO") ? CTRL_TRG_LEVEL_HIGH  : CTRL_TRG_LEVEL_LOW)     ) << CTRL_TRG_SRC_BITS)) << CTRL_TRG_DST_STOP;  

    localparam integer CTRL_TRG_RESTART  = ( RESTART_TRG_SRC | 
                                           (((RESTART_TRG_EDGE  == "YES") ? (( RESTART_TRG_INVERTED  == "NO") ? CTRL_TRG_EDGE_RISING : CTRL_TRG_EDGE_FALLING) :
                                                                            (( RESTART_TRG_INVERTED  == "NO") ? CTRL_TRG_LEVEL_HIGH  : CTRL_TRG_LEVEL_LOW)     ) << CTRL_TRG_SRC_BITS)) << CTRL_TRG_DST_RESTART;  
    
    localparam integer CTRL_SYNC_OUT     = ( CTRL_OUT_SRC_SYNC_OUT | 
                                           (((SYNC_OUT_INVERTED == "NO") ? CTRL_OUT_LEVEL_HIGH  : CTRL_OUT_LEVEL_LOW) << CTRL_OUT_SRC_BITS)) << SYNC_OUT_DST;
                                           
    localparam integer CTRL_START_OUT1   = ( CTRL_OUT_SRC_TRG_START   | ( CTRL_OUT_LEVEL_HIGH  << CTRL_OUT_SRC_BITS ) ) << CTRL_OUT_DST_OUT1;
    localparam integer CTRL_STOP_OUT1    = ( CTRL_OUT_SRC_TRG_STOP    | ( CTRL_OUT_LEVEL_HIGH  << CTRL_OUT_SRC_BITS ) ) << CTRL_OUT_DST_OUT1;
    localparam integer CTRL_RESTART_OUT2 = ( CTRL_OUT_SRC_TRG_RESTART | ( CTRL_OUT_LEVEL_HIGH  << CTRL_OUT_SRC_BITS ) ) << CTRL_OUT_DST_OUT2;
    localparam integer CTRL_OUT12         = CTRL_STOP_OUT1 | CTRL_RESTART_OUT2;                                              

    localparam integer CTRL_BUS_OUT_EN_0 = ( BUS_EN_0_SRC | 
                                           (((BUS_EN_0_INVERTED  == "NO") ? CTRL_OUT_LEVEL_HIGH  : CTRL_OUT_LEVEL_LOW) << CTRL_OUT_SRC_BITS)) << BUS_EN_0_DST;  

    localparam integer CTRL_BUS_OUT_EN_1 = ( BUS_EN_1_SRC | 
                                           (((BUS_EN_1_INVERTED  == "NO") ? CTRL_OUT_LEVEL_HIGH  : CTRL_OUT_LEVEL_LOW) << CTRL_OUT_SRC_BITS)) << BUS_EN_1_DST;  

    // control bits to be configured for each run
    // check RUNS, RUN_ABORT_#, RUN_CLOCK_LOSS_# and if (run == #) cases when changing these!
    // run 0: start as single board and run normal until end
    localparam integer CTRL_BITS_0     = CTRL_64;
    localparam integer CTRL_TRG_0      = 0; 
    localparam integer CTRL_OUT_0      = CTRL_BUS_OUT_EN_0 | CTRL_BUS_OUT_EN_1;
    localparam integer CTRL_REP_0      = 1;    
    // run 1: start as single board with external start/stop/restart trigger until end
    localparam integer CTRL_BITS_1     = CTRL_64;
    localparam integer CTRL_TRG_1      = CTRL_TRG_START | CTRL_TRG_STOP | CTRL_TRG_RESTART; 
    localparam integer CTRL_OUT_1      = CTRL_BUS_OUT_EN_0 | CTRL_BUS_OUT_EN_1 | CTRL_SYNC_OUT | CTRL_OUT12;
    localparam integer CTRL_REP_1      = 1;    
    // run 2: start as primary board without trigger, until end
    localparam integer CTRL_BITS_2     = CTRL_64 | CTRL_AS_EN | CTRL_AS_PRIM;
    localparam integer CTRL_TRG_2      = 0; 
    localparam integer CTRL_OUT_2      = CTRL_BUS_OUT_EN_0 | CTRL_BUS_OUT_EN_1 | CTRL_SYNC_OUT | CTRL_OUT12;
    localparam integer CTRL_REP_2      = 1;    
    // run 3: start as primary board with start/stop/restart trigger and external clock, until end
    localparam integer CTRL_BITS_3     = CTRL_64 | CTRL_AS_EN | CTRL_AS_PRIM;
    localparam integer CTRL_TRG_3      = CTRL_TRG_START | CTRL_TRG_STOP | CTRL_TRG_RESTART;
    localparam integer CTRL_OUT_3      = CTRL_BUS_OUT_EN_0 | CTRL_BUS_OUT_EN_1 | CTRL_SYNC_OUT | CTRL_OUT12;
    localparam integer CTRL_REP_3      = 1;    
    // run 4: start as primary board with start/stop/restart trigger, abort with software reset
    localparam integer CTRL_BITS_4     = CTRL_64 | CTRL_AS_EN | CTRL_AS_PRIM;
    localparam integer CTRL_TRG_4      = CTRL_TRG_START | CTRL_TRG_STOP | CTRL_TRG_RESTART; 
    localparam integer CTRL_OUT_4      = CTRL_BUS_OUT_EN_0 | CTRL_BUS_OUT_EN_1 | CTRL_SYNC_OUT | CTRL_OUT12;
    localparam integer CTRL_REP_4      = 1;    
    // run 5: start as primary board with start/stop trigger but without restart. abort with software reset
    localparam integer CTRL_BITS_5     = CTRL_64 | CTRL_AS_EN | CTRL_AS_PRIM;
    localparam integer CTRL_TRG_5      = CTRL_TRG_START | CTRL_TRG_STOP; 
    localparam integer CTRL_OUT_5      = CTRL_BUS_OUT_EN_0 | CTRL_BUS_OUT_EN_1 | CTRL_SYNC_OUT | CTRL_OUT12;
    localparam integer CTRL_REP_5      = 1;        
    localparam integer HOLD_LINE_TRG_0 = 5; // hold line trigger
    // run 6: start as primary board with start/stop/restart trigger and external clock, run until end
    localparam integer CTRL_BITS_6     = CTRL_64 | CTRL_AS_EN | CTRL_AS_PRIM | CTRL_CLK_EXT | CTRL_ERR_LOCK_EN;
    localparam integer CTRL_TRG_6      = CTRL_TRG_START | CTRL_TRG_STOP | CTRL_TRG_RESTART; 
    localparam integer CTRL_OUT_6      = CTRL_BUS_OUT_EN_0 | CTRL_BUS_OUT_EN_1 | CTRL_SYNC_OUT | CTRL_OUT12;
    localparam integer CTRL_REP_6      = 1;
    localparam integer HOLD_LINE_TRG_1 = 6; // hold line trigger            
    // run 6: start as secondary board with start trigger and run until end
    localparam integer CTRL_BITS_7     = CTRL_64 | CTRL_AS_EN | CTRL_CLK_EXT | CTRL_ERR_LOCK_EN;
    localparam integer CTRL_TRG_7      = CTRL_TRG_START; 
    localparam integer CTRL_OUT_7      = CTRL_BUS_OUT_EN_0 | CTRL_BUS_OUT_EN_1 | CTRL_SYNC_OUT | CTRL_OUT12;
    localparam integer CTRL_REP_7      = 1;    
    // run 7: start as secondary board with start trigger, short clock loss should still run until end. expect clock loss in status but no error.
    localparam integer CTRL_BITS_8     = CTRL_64 | CTRL_AS_EN | CTRL_CLK_EXT | CTRL_ERR_LOCK_EN;
    localparam integer CTRL_TRG_8      = CTRL_TRG_START; 
    localparam integer CTRL_OUT_8      = CTRL_BUS_OUT_EN_0 | CTRL_BUS_OUT_EN_1 | CTRL_SYNC_OUT | CTRL_OUT12;
    localparam integer CTRL_REP_8      = 1;    
    // run 8: start as secondary board with start trigger and run until external clock lost. expect error.
    localparam integer CTRL_BITS_9     = CTRL_64 | CTRL_AS_EN | CTRL_CLK_EXT | CTRL_ERR_LOCK_EN;
    localparam integer CTRL_TRG_9      = CTRL_TRG_START;
    localparam integer CTRL_OUT_9      = CTRL_BUS_OUT_EN_0 | CTRL_BUS_OUT_EN_1 | CTRL_SYNC_OUT | CTRL_OUT12;     
    localparam integer CTRL_REP_9      = 1;    
    // run 9: start as secondary board with start trigger and run until end despite of external clock lost.
    localparam integer CTRL_BITS_10    = CTRL_64 | CTRL_AS_EN | CTRL_CLK_EXT;
    localparam integer CTRL_TRG_10     = CTRL_TRG_START;
    localparam integer CTRL_OUT_10     = CTRL_BUS_OUT_EN_0 | CTRL_BUS_OUT_EN_1 | CTRL_SYNC_OUT | CTRL_OUT12;     
    localparam integer CTRL_REP_10     = 1;    
    // run 10: start as secondary board with start/stop trigger but without restart. abort with software reset.
    localparam integer CTRL_BITS_11    = CTRL_64 | CTRL_AS_EN | CTRL_CLK_EXT;
    localparam integer CTRL_TRG_11     = CTRL_TRG_START | CTRL_TRG_STOP;
    localparam integer CTRL_OUT_11     = CTRL_BUS_OUT_EN_0 | CTRL_BUS_OUT_EN_1 | CTRL_SYNC_OUT | CTRL_OUT12;     
    localparam integer CTRL_REP_11     = 1; 
    // run 11: start as secondary board with start/stop/restart trigger and run until end.
    localparam integer CTRL_BITS_12    = CTRL_64 | CTRL_AS_EN | CTRL_CLK_EXT;
    localparam integer CTRL_TRG_12     = CTRL_TRG_START | CTRL_TRG_STOP | CTRL_TRG_RESTART;
    localparam integer CTRL_OUT_12     = CTRL_BUS_OUT_EN_0 | CTRL_BUS_OUT_EN_1 | CTRL_SYNC_OUT | CTRL_OUT12;
    localparam integer CTRL_REP_12     = 25;
    localparam integer HOLD_LINE_TRG_2 = 12; // hold line trigger such that each loop we test different clk_bus_div value for stop trigger.
    
    // end check
    localparam integer END_CTRL_MASK   = CTRL_READY | CTRL_RUN;
    localparam integer END_CTRL_SET    = CTRL_READY | CTRL_RUN;
    localparam integer END_STATUS_MASK = STATUS_RESET|STATUS_READY|STATUS_RUN|STATUS_END|STATUS_ERR_ALL|STATUS_IRQ_ERR|STATUS_IRQ_END;
    localparam integer END_STATUS_SET  = STATUS_READY|STATUS_END|STATUS_IRQ_END;
            
    // masks for tests
    localparam [GEN_DATA_WIDTH-1:0]                DATA_MASK = 32'h00ffffff;             // data bits without BIT_STROBE|BIT_NOP|BIT_IRQ|BIT_TRST
    localparam [GEN_DATA_WIDTH+GEN_TIME_WIDTH-1:0] BUS_MASK  = 'h7f_ffff_ffff_ffff;      // bus output mask without BIT_STROBE|BIT_NOP|BIT_IRQ|BIT_TRST

    // AXI clock
    reg clk_AXI;
    initial begin
        clk_AXI = 1'b0;
        forever begin
            #(PERIOD_AXI/2);
            clk_AXI = ~clk_AXI;
        end
    end

    // reset AXI
    reg reset_AXI_n;
    initial begin
        reset_AXI_n = 1'b0;
        repeat (RESET_AXI_CYCLES) @(posedge clk_AXI);
        reset_AXI_n = 1'b1;
    end

    // stream clock
    wire clk_stream = clk_AXI;
    wire reset_stream_n = reset_AXI_n;

    // bus clock
    // if connected to external clock this might get lost
    reg clk_bus;
    wire clk_ext_sel;
    reg clk_mux_en;
    initial begin
        clk_bus = 1'b0;
        forever begin
            #(PERIOD_BUS/2);
            clk_bus = (clk_ext_sel == 1'b0) ? ~clk_bus : 
                      (clk_mux_en  == 1'b1) ? ~clk_bus : 1'b0;
        end
    end

    // 2x bus clock for simulation
    reg clk_bus2;
    initial begin
        clk_bus2 = 1'b0;
        forever begin
            #(PERIOD_BUS/4);
            clk_bus2 = ~clk_bus2;
        end
    end

    // reset bus (used only in test bench)
    reg reset_bus_n;
    initial begin
        reset_bus_n = 1'b0;
        repeat (RESET_BUS_CYCLES) @(posedge clk_bus);
        reset_bus_n = 1'b1;
    end

    // detection clock phase shifted bus clock
    // if connected to external clock this might get lost
    reg clk_det;
    initial begin
        clk_det = 1'b0;
        #(PHASE_DET);
        forever begin
            #(PERIOD_BUS/2);
            //clk_det = ~clk_det;
            clk_det = (clk_ext_sel == 1'b0) ? ~clk_det : 
                      (clk_mux_en  == 1'b1) ? ~clk_det : 1'b0;
        end
    end
    
    // slow pwm clock
    // if connected to external clock this might get lost
    reg clk_pwm;
    initial begin
        clk_pwm = 1'b0;
        #(PHASE_DET);
        forever begin
            #(PERIOD_PWM/2);
            clk_pwm = (clk_ext_sel == 1'b0) ? ~clk_pwm : 
                      (clk_mux_en  == 1'b1) ? ~clk_pwm : 1'b0;
        end
    end

    // line trigger used for all triggering tasks
    reg line_trg;
    reg line_trg_hold = 1'b0; // keep line trigger low when this is high.
    integer line_trg_loop = 0;
    integer line_trg_count = PERIOD_LINE;
    initial begin
        line_trg = 1'b0;
        forever begin
            #(PERIOD_BUS/4);
            if (line_trg_hold == 1'b1) begin
                line_trg_loop = 0;
                line_trg_count = PERIOD_LINE;
            end
            else begin
                if ( line_trg_loop == PERIOD_LINE_NUM ) begin
                    line_trg_loop = 0;
                    line_trg_count = PERIOD_LINE;
                end
                else if ( line_trg_count <= 0 ) begin
                    line_trg = ~line_trg;
                    line_trg_loop = line_trg_loop + 1;
                    line_trg_count = PERIOD_LINE + PERIOD_LINE_ADD*line_trg_loop;
                end
                else begin
                    line_trg_count = line_trg_count - PERIOD_BUS/4;
                end
            end
        end
    end

    /* strobe 0 clock = phase shifted 2x bus clock
    reg clk_strb_0;
    initial begin
        clk_strb_0 = 1'b0;
        #(PERIOD_BUS/2 - PERIOD_STRB_0/2 + PHASE_STRB_0);
        forever begin
            #(PERIOD_STRB_0/2);
            clk_strb_0 = ~clk_strb_0;
        end
    end

    // strobe 1 clock = phase shifted 2x bus clock
    reg clk_strb_1;
    initial begin
        clk_strb_1 = 1'b0;
        #(PERIOD_BUS/2 - PERIOD_STRB_1/2 + PHASE_STRB_1);
        forever begin
            #(PERIOD_STRB_1/2);
            clk_strb_1 = ~clk_strb_1;
        end
    end
    */

    // AXI Light data interface for reading/writing registers
    // write register
    reg [AXI_DATA_WIDTH-1 : 0] AXI_wr_data;
    reg [AXI_ADDR_WIDTH-1 : 0] AXI_wr_addr;
    reg AXI_wr_valid;
    wire AXI_wr_ready;
    // read register
    wire [AXI_DATA_WIDTH-1 : 0] AXI_rd_data;
    reg [AXI_ADDR_WIDTH-1 : 0] AXI_rd_addr;
    wire AXI_rd_valid;
    reg AXI_rd_ready;
    // interface
    wire [AXI_ADDR_WIDTH-1 : 0] s00_axi_awaddr;
    wire [2 : 0] s00_axi_awprot;
    wire s00_axi_awvalid;
    wire s00_axi_awready;
    wire [AXI_DATA_WIDTH-1 : 0] s00_axi_wdata;
    wire [(AXI_DATA_WIDTH/8)-1 : 0] s00_axi_wstrb;
    wire s00_axi_wvalid;
    wire s00_axi_wready;
    wire [1 : 0] s00_axi_bresp;
    wire s00_axi_bvalid;
    wire s00_axi_bready;
    wire [AXI_ADDR_WIDTH-1 : 0] s00_axi_araddr;
    wire [2 : 0] s00_axi_arprot;
    wire s00_axi_arvalid;
    wire s00_axi_arready;
    wire [AXI_DATA_WIDTH-1 : 0] s00_axi_rdata;
    wire [1 : 0] s00_axi_rresp;
    wire s00_axi_rvalid;
    wire s00_axi_rready;
    axi_lite_master # (
            //.C_TRANSACTIONS_NUM(4)
            .DATA_WIDTH(AXI_DATA_WIDTH),
            .ADDR_WIDTH(AXI_ADDR_WIDTH)
        ) AXI_master (
            .M_AXI_ACLK(clk_AXI),
            .M_AXI_ARESETN(reset_AXI_n),
            
            // ware data to specified register address
            .wr_addr(AXI_wr_addr),
            .wr_data(AXI_wr_data),
            .wr_valid(AXI_wr_valid),
            .wr_ready(AXI_wr_ready),
            
            // read data at specified register address
            .rd_addr(AXI_rd_addr),
            .rd_data(AXI_rd_data),
            .rd_valid(AXI_rd_valid),
            .rd_ready(AXI_rd_ready),
            
            // AXI Lite interface
            .M_AXI_AWADDR(s00_axi_awaddr),
            .M_AXI_AWPROT(s00_axi_awprot),
            .M_AXI_AWVALID(s00_axi_awvalid),
            .M_AXI_AWREADY(s00_axi_awready),
            .M_AXI_WDATA(s00_axi_wdata),
            .M_AXI_WSTRB(s00_axi_wstrb),
            .M_AXI_WVALID(s00_axi_wvalid),
            .M_AXI_WREADY(s00_axi_wready),
            .M_AXI_BRESP(s00_axi_bresp),
            .M_AXI_BVALID(s00_axi_bvalid),
            .M_AXI_BREADY(s00_axi_bready),
            .M_AXI_ARADDR(s00_axi_araddr),
            .M_AXI_ARPROT(s00_axi_arprot),
            .M_AXI_ARVALID(s00_axi_arvalid),
            .M_AXI_ARREADY(s00_axi_arready),
            .M_AXI_RDATA(s00_axi_rdata),
            .M_AXI_RRESP(s00_axi_rresp),
            .M_AXI_RVALID(s00_axi_rvalid),
            .M_AXI_RREADY(s00_axi_rready)
        );
    
    // generate input data
    // when in_ready & in_valid increment data with fixed step size
    // in_count counts number of transmitted data
    localparam [GEN_DATA_WIDTH-1:0] TRST_SET = {1'b1,{BIT_TRST{1'b0}}};
    localparam [GEN_DATA_WIDTH-1:0] NOP_SET = {1'b1,{BIT_NOP{1'b0}}};
    reg [GEN_DATA_WIDTH-1:0] gen_data = 0;
    reg [GEN_DATA_WIDTH-1:0] gen_data_plus = 0;
    reg [GEN_TIME_WIDTH-1:0] gen_time = 0;
    reg [(BITS_PER_SAMPLE/8)-1:0] gen_keep = {(BITS_PER_SAMPLE/8){1'b1}};
    reg gen_last;
    reg gen_en;
    reg gen_ctrl;
    reg gen_ctrl_reset;
    reg [31:0] gen_count;
    wire gen_ready;
    wire gen_valid = gen_en & gen_ctrl;
    wire [GEN_TIME_WIDTH-1:0] gen_next_time = ( gen_time == TIME_JUMP_0 ) ? TIME_JUMP_TIME_0 : 
                                              ( gen_time == TIME_JUMP_1 ) ? TIME_JUMP_TIME_1 :
                                              ( gen_time == TIME_JUMP_2 ) ? TIME_JUMP_TIME_2 :
                                              ( gen_time == TIME_JUMP_3 ) ? TIME_JUMP_TIME_3 :
                                              ( gen_time == TIME_JUMP_4 ) ? TIME_JUMP_TIME_4 : gen_time + GEN_TIME_STEP;
    wire [GEN_DATA_WIDTH-1:0] gen_trst = (gen_next_time == TIME_TRST_0) ? TRST_SET : 
                                         (gen_next_time == TIME_TRST_1) ? TRST_SET :
                                         (gen_next_time == TIME_TRST_2) ? TRST_SET :
                                         (gen_next_time == TIME_TRST_3) ? TRST_SET :
                                         (gen_next_time == TIME_TRST_4) ? TRST_SET : 'd0;
    wire [GEN_DATA_WIDTH-1:0] gen_nop  = (gen_next_time == TIME_NOP_0) ? NOP_SET : 
                                         (gen_next_time == TIME_NOP_1) ? NOP_SET :
                                         (gen_next_time == TIME_NOP_2) ? NOP_SET :
                                         (gen_next_time == TIME_NOP_3) ? NOP_SET :
                                         (gen_next_time == TIME_NOP_4) ? NOP_SET : 'd0;
    reg gen_strb_toggle = 1'b0;
    wire [GEN_DATA_WIDTH-1:0] gen_strb = gen_strb_toggle ? STROBE_SET : 0; 
    wire gen_strb_w = (gen_count == (SKIP_STRB_0-3)) ? gen_strb_toggle: 
                      (gen_count == (SKIP_STRB_1-3)) ? gen_strb_toggle :
                      (gen_count == (SKIP_STRB_2-3)) ? gen_strb_toggle :
                      (gen_count == (SKIP_STRB_3-3)) ? gen_strb_toggle :
                      (gen_count == (SKIP_STRB_4-3)) ? gen_strb_toggle : ~gen_strb_toggle;
    reg [GEN_DATA_WIDTH+GEN_TIME_WIDTH:0] gen_datatime [0 : GEN_NUM_SAMPLES - 1]; // {last,data,time}
    reg [GEN_DATA_WIDTH+GEN_TIME_WIDTH:0] gen_datatime_last; // last gen_datatime without NOP bit
    always @ ( posedge clk_stream ) begin
        if ( ( reset_stream_n == 1'b0) || (gen_ctrl_reset == 1'b1) ) begin
            gen_data <= GEN_DATA_START_STRB;
            gen_data_plus <= (GEN_DATA_START & DATA_MASK) + GEN_DATA_STEP;
            gen_time <= GEN_TIME_START;
            gen_last <= 1'b0;
            gen_count <= 0;
            gen_datatime_last <= 0;
            gen_en <= 1'b0;
            if (GEN_STRB_TOGGLE == "YES")
                gen_strb_toggle <= ~GEN_STRB_START;
            else
                gen_strb_toggle <= 1'b0;
        end
        else if ( gen_count < (GEN_NUM_SAMPLES-1) ) begin
            if ( gen_ready & gen_valid ) begin
                gen_data <= gen_data_plus | gen_trst | gen_nop | gen_strb;
                gen_data_plus <= gen_data_plus + GEN_DATA_STEP;
                gen_time <= gen_next_time;
                gen_count <= gen_count + 1;
                gen_datatime[gen_count] <= {gen_last,gen_data,gen_time};
                gen_datatime_last <= (gen_data[BIT_NOP] == 1'b0) ? {gen_last,gen_data,gen_time} : gen_datatime_last;
                gen_last <= ( gen_count < (GEN_NUM_SAMPLES-2) ) ? 1'b0 : 1'b1;
                if ( GEN_STRB_TOGGLE == "YES" ) begin
                    gen_strb_toggle <= gen_strb_w;
                end
                else begin
                    gen_strb_toggle <= gen_strb_toggle;
                end
            end
            else begin
                gen_data <= gen_data;
                gen_data_plus <= gen_data_plus;
                gen_time <= gen_time;
                gen_count <= gen_count;
                gen_datatime_last <= gen_datatime_last;
                gen_last <= gen_last;
                gen_strb_toggle <= gen_strb_toggle;
            end
            gen_en <= 1'b1;
        end
        else begin
            if ( gen_ready & gen_valid ) begin
                gen_count <= gen_count + 1;
                gen_en <= 1'b0;
                // save last generated data to memory
                gen_datatime[gen_count] <= {gen_last,gen_data,gen_time};
                gen_datatime_last <= (gen_data[BIT_NOP] == 1'b0) ? {gen_last,gen_data,gen_time} : gen_datatime_last;
            end
            else begin
                gen_count <= gen_count;
                gen_en <= gen_en;        
            end
            gen_data <= gen_data;
            gen_data_plus <= gen_data_plus;
            gen_time <= gen_time;
            gen_last <= gen_last;
            gen_strb_toggle <= gen_strb_toggle;
        end
    end
    
    wire [BITS_PER_SAMPLE - 1 : 0] gen_data_full;
    if (BITS_PER_SAMPLE == 64) begin
        assign gen_data_full = {gen_data,gen_time};
    end
    else begin
        assign gen_data_full = {~gen_data,gen_data,gen_time};
    end
    
    // combine samples from BITS_PER_SAMPLE to STREAM_DATA_WIDTH
    wire [STREAM_DATA_WIDTH - 1 : 0] TX_data;
    wire [(STREAM_DATA_WIDTH/8) - 1 : 0] TX_keep;
    wire TX_last;
    wire TX_valid;
    wire TX_ready;
    wire TX_error_keep;
   stream_convert # (
       .IN_BYTES(BITS_PER_SAMPLE/8),
       .OUT_BYTES(STREAM_DATA_WIDTH/8)
   )
   gen_TX (
       // clock and reset
       .clock(clk_stream),
       .reset_n(reset_stream_n),
       // tkeep error
       .error_keep(TX_error_keep),
       // data input
       .in_data(gen_data_full),
       .in_last(gen_last),
       .in_keep(gen_keep),
       .in_valid(gen_valid),
       .in_ready(gen_ready),
       // data output
       .out_data(TX_data),
       .out_last(TX_last),     
       .out_keep(TX_keep),
       .out_valid(TX_valid),
       .out_ready(TX_ready)
   );
   
    // MUX clock locked signal
    // reset after each change of clk_ext_sel and when clock lost
    // select after CLK_MUX_DELAY ok clk_AXI cycles
    localparam integer CLK_MUX_DELAY = 15;
    reg clk_mux_locked = 1'b0;
    reg [CLK_MUX_DELAY-1:0] clk_mux_count = {(CLK_MUX_DELAY){1'b0}};
    reg clk_ext_locked;
    wire reset_AXI_sw_n;
    always @ (posedge clk_AXI) begin
        if ( reset_AXI_sw_n == 1'b0 ) begin // reset of clock Wizards
            clk_mux_count <= {(CLK_MUX_DELAY){1'b0}};
            clk_mux_locked <= 1'b0;
        end
        else if ( clk_ext_sel == 1'b0 ) begin // internal clock selected. this goes fast unless was unlocked before.
            clk_mux_count <= {clk_mux_count[CLK_MUX_DELAY-2:0],1'b1};
            clk_mux_locked <= clk_mux_count[CLK_MUX_DELAY-1];
        end
        else if ( clk_ext_locked ) begin // external clock selected and locked
            clk_mux_count <= {clk_mux_count[CLK_MUX_DELAY-2:0],1'b1};
            clk_mux_locked <= clk_mux_count[CLK_MUX_DELAY-1];
        end  
        else begin // external clock selected but not locked
            // to simulate short clock loss with clk_mux_en == 1'b1 we count down counter
            // to simulate complete clock loss with clk_mux_en == 1'b0 we completely reset counter
            clk_mux_count <= clk_mux_en ? {1'b0,clk_mux_count[CLK_MUX_DELAY-1:1]} : {(CLK_MUX_DELAY){1'b0}};
            clk_mux_locked <= 1'b0;
        end
    end 

    // external I/O
    reg [2:0] ext_in;
    wire [2:0] ext_out;

    // output data
    wire [STREAM_DATA_WIDTH-1:0] RX_data;
    wire RX_last;
    wire RX_ready;
    wire RX_valid;
    wire [(STREAM_DATA_WIDTH/8)-1:0] RX_keep;

    // dio24 module instantiation
    reg [NUM_BUTTONS-1:0] buttons_in;
    wire [NUM_LED_RED-1:0] led_red;
    wire [NUM_LED_GREEN-1:0] led_green;
    wire [NUM_LED_BLUE-1:0] led_blue;
    wire [NUM_BUS_EN-1:0] bus_en;
    wire [BUS_DATA_BITS-1:0] bus_data;
    wire [BUS_ADDR_BITS-1:0] bus_addr_0;
    wire [BUS_ADDR_BITS-1:0] bus_addr_1;
    wire [NUM_STRB-1:0] bus_strb;
    reg irq_TX = 0;
    reg irq_RX = 0;
    wire irq_FPGA;
    reg ps_done_ext = 0;
    wire ps_en_ext;
    wire ps_inc_ext;
    reg ps_done_det = 0;
    wire ps_en_det;
    wire ps_inc_det;
    dio24 # (
        .AXI_ADDR_WIDTH(AXI_ADDR_WIDTH),
        .AXI_DATA_WIDTH(AXI_DATA_WIDTH),
        .STREAM_DATA_WIDTH(STREAM_DATA_WIDTH),
        .BUS_ADDR_BITS(BUS_ADDR_BITS),
        .BUS_DATA_BITS(BUS_DATA_BITS),
        .NUM_STRB(NUM_STRB),
        .NUM_BUS_EN(NUM_BUS_EN),
        
        .VERSION(VERSION),
        .INFO(INFO),

        .BITS_PER_SAMPLE(BITS_PER_SAMPLE),
        
        .NUM_IN_BITS(NUM_IN_BITS),
        .NUM_OUT_BITS(NUM_OUT_BITS),
        
        .NUM_BUTTONS(NUM_BUTTONS),
        .NUM_LED_RED(NUM_LED_RED),
        .NUM_LED_GREEN(NUM_LED_GREEN),
        .NUM_LED_BLUE(NUM_LED_BLUE),
        .LED_BLINK_ON(LED_BLINK_ON),
        .LED_SLOW(LED_SLOW),
        .LED_FAST(LED_FAST),
        .LED_DIM_LOW(LED_DIM_LOW),
        .LED_DIM_HIGH(LED_DIM_HIGH),
        .LED_BRIGHT_LOW(LED_BRIGHT_LOW),
        .LED_BRIGHT_HIGH(LED_BRIGHT_HIGH),
        
        .TIME_BITS(TIME_BITS),
        .TIME_START(TIME_START),
        .DATA_BITS(DATA_BITS),
        .DATA_START_64(DATA_START_64),
        .DATA_START_96_0(DATA_START_96_0),
        .DATA_START_96_1(DATA_START_96_1),
        .CLK_DIV_BITS(CLK_DIV_BITS),
        .TRG_DIV_BITS(TRG_DIV_BITS),
        .STRB_DELAY_BITS(STRB_DELAY_BITS),
        
        .AUTO_SYNC_PULSE_LENGTH(AUTO_SYNC_PULSE_LENGTH),
        .AUTO_SYNC_PULSE_WAIT(AUTO_SYNC_PULSE_WAIT),
        .AUTO_SYNC_MAX_PULSES(AUTO_SYNC_MAX_PULSES),
        .AUTO_SYNC_TIME_BITS(AUTO_SYNC_TIME_BITS),
        .AUTO_SYNC_DELAY_BITS(AUTO_SYNC_DELAY_BITS),
        .AUTO_SYNC_PHASE_BITS(AUTO_SYNC_PHASE_BITS),
        
        .BUS_ADDR_1_USE(BUS_ADDR_1_USE),

        .BIT_NOP(BIT_NOP),
        .BIT_TRST(BIT_TRST),
        .BIT_IRQ(BIT_IRQ),
        .BIT_STOP(BIT_STOP),
        .BIT_STROBE(BIT_STROBE),
        .USE_STROBE(USE_STROBE),
        
        .SYNC(SYNC),
        
        .IRQ_FREQ_BITS(IRQ_FREQ_BITS),

        .ERROR_LOCK_DELAY(ERROR_LOCK_DELAY),

        .TX_FIFO_DEPTH(TX_FIFO_DEPTH),
        .RX_FIFO_DEPTH(RX_FIFO_DEPTH)
    )
    DUT
    (
        // clocks and reset
        //.clk_stream(clk_stream),
        .clk_bus(clk_bus),
        .clk_det(clk_det),
        .clk_pwm(clk_pwm),
        //.clk_AXI(clk_AXI),
        //.reset_AXI_n(reset_AXI_n),
        .reset_AXI_sw_n(reset_AXI_sw_n),
        
        // FPGA board buttons and RGB LEDs
        .buttons_in(buttons_in),
        .led_red(led_red),
        .led_green(led_green),
        .led_blue(led_blue),
                
        // buffer board external clock control
        .clk_ext_locked(clk_ext_locked),  
        .clk_mux_locked(clk_mux_locked),
        .clk_ext_sel(clk_ext_sel),
        
        // rack data bus output
        .bus_en(bus_en),
        .bus_data(bus_data),
        .bus_addr_0(bus_addr_0),
        .bus_addr_1(bus_addr_1),
        .bus_strb(bus_strb),
        
        // irq I/O
        .irq_TX(irq_TX),
        .irq_RX(irq_RX),
        .irq_FPGA(irq_FPGA),
        
        // inputs
        .ext_in(ext_in),
        
        // outputs
        .ext_out(ext_out),
        
        // dynamic phase shift of external clock input and detector clock 
        .ps_done_ext(ps_done_ext),
        .ps_en_ext(ps_en_ext),
        .ps_inc_ext(ps_inc_ext),
        .ps_done_det(ps_done_det),
        .ps_en_det(ps_en_det),
        .ps_inc_det(ps_inc_det),
        
        // AXI Lite Slave Bus Interface S00_AXI
        .s00_axi_aclk(clk_AXI),
        .s00_axi_aresetn(reset_AXI_n),
        .s00_axi_awaddr(s00_axi_awaddr),
        .s00_axi_awprot(s00_axi_awprot),
        .s00_axi_awvalid(s00_axi_awvalid),
        .s00_axi_awready(s00_axi_awready),
        .s00_axi_wdata(s00_axi_wdata),
        .s00_axi_wstrb(s00_axi_wstrb),
        .s00_axi_wvalid(s00_axi_wvalid),
        .s00_axi_wready(s00_axi_wready),
        .s00_axi_bresp(s00_axi_bresp),
        .s00_axi_bvalid(s00_axi_bvalid),
        .s00_axi_bready(s00_axi_bready),
        .s00_axi_araddr(s00_axi_araddr),
        .s00_axi_arprot(s00_axi_arprot),
        .s00_axi_arvalid(s00_axi_arvalid),
        .s00_axi_arready(s00_axi_arready),
        .s00_axi_rdata(s00_axi_rdata),
        .s00_axi_rresp(s00_axi_rresp),
        .s00_axi_rvalid(s00_axi_rvalid),
        .s00_axi_rready(s00_axi_rready),
        
        // AXI stream data input (from DMA stream master)
        .AXIS_in_aclk(clk_AXI),
        .AXIS_in_aresetn(reset_AXI_n),
        .AXIS_in_tdata(TX_data),
        .AXIS_in_tlast(TX_last),
        .AXIS_in_tready(TX_ready),
        .AXIS_in_tvalid(TX_valid),
        .AXIS_in_tkeep(TX_keep),
        
        // AXI stream data output (to DMA stream slave)
        .AXIS_out_aclk(clk_AXI),
        .AXIS_out_aresetn(reset_AXI_n),
        .AXIS_out_tdata(RX_data),
        .AXIS_out_tlast(RX_last),
        .AXIS_out_tready(RX_ready),
        .AXIS_out_tvalid(RX_valid),
        .AXIS_out_tkeep(RX_keep)
    );
    
    // split samples from STREAM_DATA_WIDTH to BITS_PER_SAMPLE for comparison with gen_datatime
    wire [BITS_PER_SAMPLE - 1 : 0] out_data;
    wire [(BITS_PER_SAMPLE/8) - 1 : 0] out_keep;
    wire out_last;
    wire out_valid;
    reg out_ready;
    wire out_error_keep;
    stream_convert # (
       .IN_BYTES(STREAM_DATA_WIDTH/8),
       .OUT_BYTES(BITS_PER_SAMPLE/8)
    )
    gen_RX (
       // clock and reset
       .clock(clk_stream),
       .reset_n(reset_stream_n),
       // tkeep error
       .error_keep(out_error_keep),
       // data input
       .in_data(RX_data),
       .in_last(RX_last),
       .in_keep(RX_keep),
       .in_valid(RX_valid),
       .in_ready(RX_ready),
       // data output
       .out_data(out_data),
       .out_last(out_last),     
       .out_keep(out_keep),
       .out_valid(out_valid),
       .out_ready(out_ready)
    );

    // bus out counter / timer to compare actual bus output time with programmed time
    // TODO: this code is a bit tricky with stop trigger!
    reg [clogb2(CLK_DIV):0] bus_act_time_cnt; // counter @ clk_bus to generate CLK_DIV
    reg [GEN_TIME_WIDTH-1:0] bus_act_time; // actual bus time = bus_out_time_cnt / CLK_DIV
    always @ ( posedge clk_bus or negedge reset_AXI_sw_n ) begin
        if ( reset_AXI_sw_n == 1'b0 ) begin
            bus_act_time_cnt <= -1;
            bus_act_time     <= GEN_TIME_START - 1;
        end
        //else if ( DUT.run_bus | (DUT.run_or_wait & (bus_act_time_cnt >= (CLK_DIV-3))) ) begin
        else if ( DUT.timing.state_run & (~DUT.timing.state_wait) ) begin
            bus_act_time_cnt <= ( bus_act_time_cnt == (CLK_DIV-1) ) ? 0 : bus_act_time_cnt + 1;
            bus_act_time     <= ( bus_act_time_cnt == (CLK_DIV-1) ) ? bus_act_time + 1 : bus_act_time;
        end
        else begin    
            bus_act_time_cnt <= bus_act_time_cnt;
            bus_act_time     <= bus_act_time;
        end
    end

    // monitor bus output @ clk_bus
    // we check output at correct relative time and data and address is same as generated
    reg bus_strb_0_ff;
    reg bus_strb_0_toggle = 1'b0; // toggles for each bus_strb_0 change. bus_strb_1 must be in same state
    //reg [GEN_TIME_WIDTH-1:0] bus_time;
    reg [GEN_DATA_WIDTH+GEN_TIME_WIDTH-1:0] bus_out_datatime;
    reg [AXI_DATA_WIDTH-1:0] bus_out_count = 0;
    reg [AXI_DATA_WIDTH-1:0] bus_out_skipped;
    reg bus_out_error;
    //wire [GEN_TIME_WIDTH-1:0] bus_out_time_w = ( bus_out_count == 0 ) ? GEN_TIME_START : (GEN_TIME_START + (bus_time * PERIOD_BUS) / (PERIOD_BUS * CLK_DIV));
    wire [GEN_TIME_WIDTH+GEN_DATA_WIDTH -1 : 0] gen_data_act = ( bus_out_count >= GEN_NUM_SAMPLES ) ? 0 : BUS_MASK & gen_datatime[bus_out_count][GEN_TIME_WIDTH+GEN_DATA_WIDTH-1 : 0];
    reg bus_gen_strb = 1'b0;
    wire skip_NOP;
    if ( USE_STROBE == "YES" )
        assign skip_NOP = ( bus_out_count >= GEN_NUM_SAMPLES ) ? 1'b0 : 
                          ( gen_datatime[bus_out_count][BIT_NOP+GEN_TIME_WIDTH] == 1'b1 ) ? 1'b1 :
                          ( gen_datatime[bus_out_count][BIT_STROBE+GEN_TIME_WIDTH] == bus_gen_strb ) ? 1'b1 : 1'b0;
    else
        assign skip_NOP = ( bus_out_count >= GEN_NUM_SAMPLES ) ? 1'b0 : 
                          ( gen_datatime[bus_out_count][BIT_NOP+GEN_TIME_WIDTH] == 1'b1 ) ? 1'b1 : 1'b0;
    
    always @ ( posedge clk_bus or negedge reset_AXI_sw_n ) begin
        if ( reset_AXI_sw_n == 1'b0 ) begin
            bus_strb_0_ff <= 1'b0;
            bus_strb_0_toggle <= bus_strb_0_toggle;
            //bus_time <= 0;
            //bus_out_time <= 0;
            bus_out_datatime  <= 0;
            bus_out_count <= 0;
            bus_out_skipped <= 0;
            bus_out_error <= 1'b0;
            bus_gen_strb <= ~GEN_STRB_START;
        end
        else if ( bus_en[0] == 1'b0 ) begin
            if ( {bus_strb_0_ff,bus_strb[0]} == 2'b01 ) begin
                bus_strb_0_ff <= bus_strb[0];
                bus_strb_0_toggle <= ~bus_strb_0_toggle;
                //bus_time <= ( bus_out_count == 0 ) ? 1 : bus_time + 1;
                //bus_out_time <= ( bus_out_count == 0 ) ? GEN_TIME_START : bus_out_time_w;
                bus_out_datatime  <= {bus_addr_0,bus_data,bus_act_time};
                bus_out_count <= bus_out_count + 1;
                bus_out_skipped <= bus_out_skipped; 
                bus_gen_strb <= gen_datatime[bus_out_count][BIT_STROBE+GEN_TIME_WIDTH];
                if ( gen_data_act != {bus_addr_0,bus_data,bus_act_time} )
                    bus_out_error <= 1'b1;
                else bus_out_error <= bus_out_error;
            end
            else if ( skip_NOP ) begin // skip data with NOP bit set
                bus_strb_0_ff <= bus_strb[0];
                bus_strb_0_toggle <= bus_strb_0_toggle;
                //bus_time <= DUT.run_bus ? bus_time + 1 : bus_time;
                //bus_out_time <= bus_out_time;
                bus_out_datatime  <= bus_out_datatime;
                bus_out_count <= bus_out_count + 1;
                bus_out_skipped <= bus_out_skipped + 1;
                bus_out_error <= bus_out_error;
                bus_gen_strb <= gen_datatime[bus_out_count][BIT_STROBE+GEN_TIME_WIDTH];
            end
            else begin
                bus_strb_0_ff <= bus_strb[0];
                bus_strb_0_toggle <= bus_strb_0_toggle;
                //bus_time <= DUT.run_bus ? bus_time + 1 : bus_time;
                //bus_out_time <= bus_out_time;
                bus_out_datatime  <= bus_out_datatime;
                bus_out_count <= bus_out_count;
                bus_out_skipped <= bus_out_skipped;
                bus_out_error <= bus_out_error;
                bus_gen_strb <= bus_gen_strb;
            end
        end
        else begin
            bus_strb_0_ff <= 1'b0;
            bus_strb_0_toggle <= bus_strb_0_toggle;
            //bus_time <= bus_time;
            //bus_out_time <= bus_out_time;
            bus_out_datatime  <= bus_out_datatime;
            bus_out_count <= bus_out_count;
            bus_out_skipped <= bus_out_skipped;
            bus_out_error <= bus_out_error;
            bus_gen_strb <= bus_gen_strb;
        end
    end    
    
    // monitor RX data output @ clk_stream
    // here the time does not matter, we only check the correct data
    reg [GEN_DATA_WIDTH+GEN_TIME_WIDTH : 0] out_datatime;
    reg [AXI_DATA_WIDTH-1:0] out_count;
    reg out_error = 1'b0;
    always @ ( posedge clk_stream or negedge reset_AXI_sw_n ) begin
        if ( reset_AXI_sw_n == 1'b0 ) begin
            out_datatime <= 0;
            out_count <= 0;
            out_error <= 1'b0;
        end
        else if ( out_valid & out_ready ) begin
            out_datatime <= {out_last,out_data[GEN_DATA_WIDTH+GEN_TIME_WIDTH-1:0]};
            out_count <= out_count + 1;
            out_error <= ( gen_datatime[out_count] != {out_last,out_data[GEN_DATA_WIDTH+GEN_TIME_WIDTH-1:0]} ) ? 1'b1 : out_error;
        end
        else begin
            out_datatime <= out_datatime;
            out_count <= out_count;
            out_error <= out_error;
        end
    end    

    // connect line trigger with external inputs as configured 
    integer conf_trg;
    task set_ext_in;
    begin
        ext_in[0] = ( conf_trg[CTRL_TRG_DST_START   + CTRL_TRG_SRC_BITS-1 -: CTRL_TRG_SRC_BITS] == CTRL_TRG_SRC_IN0 ) ? line_trg :
                    ( conf_trg[CTRL_TRG_DST_STOP    + CTRL_TRG_SRC_BITS-1 -: CTRL_TRG_SRC_BITS] == CTRL_TRG_SRC_IN0 ) ? line_trg :
                    ( conf_trg[CTRL_TRG_DST_RESTART + CTRL_TRG_SRC_BITS-1 -: CTRL_TRG_SRC_BITS] == CTRL_TRG_SRC_IN0 ) ? line_trg : 1'b0;
        ext_in[1] = ( conf_trg[CTRL_TRG_DST_START   + CTRL_TRG_SRC_BITS-1 -: CTRL_TRG_SRC_BITS] == CTRL_TRG_SRC_IN1 ) ? line_trg :
                    ( conf_trg[CTRL_TRG_DST_STOP    + CTRL_TRG_SRC_BITS-1 -: CTRL_TRG_SRC_BITS] == CTRL_TRG_SRC_IN1 ) ? line_trg :
                    ( conf_trg[CTRL_TRG_DST_RESTART + CTRL_TRG_SRC_BITS-1 -: CTRL_TRG_SRC_BITS] == CTRL_TRG_SRC_IN1 ) ? line_trg : 1'b0;
        ext_in[2] = ( conf_trg[CTRL_TRG_DST_START   + CTRL_TRG_SRC_BITS-1 -: CTRL_TRG_SRC_BITS] == CTRL_TRG_SRC_IN2 ) ? line_trg :
                    ( conf_trg[CTRL_TRG_DST_STOP    + CTRL_TRG_SRC_BITS-1 -: CTRL_TRG_SRC_BITS] == CTRL_TRG_SRC_IN2 ) ? line_trg :
                    ( conf_trg[CTRL_TRG_DST_RESTART + CTRL_TRG_SRC_BITS-1 -: CTRL_TRG_SRC_BITS] == CTRL_TRG_SRC_IN2 ) ? line_trg : 1'b0;
    end 
    endtask

    // continuously set external input as configured
    initial begin
        forever begin
            @(posedge clk_bus);
            set_ext_in;
        end
    end

    // check output of DUT @ bus clock
    // stops simulation when DUT gives error or incorrect output
    //integer start_time = -1;
    //integer e_count = 0;
    integer expect_error = 0;
    integer bus_out_error_ignore = 0;
    reg error_ignore = 1'b0;
    task check_DUT;
    begin
        if ( DUT.error ) begin
            if (~error_ignore) begin
                $display("%d: DUT is in error state!", $time);
                $display("%d: DUT ctrl 0x%x status 0x%x", $time, DUT.control, DUT.status);
                if ((DUT.status & STATUS_ERR_ALL) == expect_error) begin
                    $display("%d: DUT error %x expected (continue)", $time, expect_error);
                    error_ignore = 1'b1;
                end
                else begin
                    $finish;
                end
            end
        end
        else if ((reset_bus_n == 1'b1) && (reset_AXI_sw_n == 1'b1))  begin
            error_ignore = 1'b0;
            // check timeout at correct time. during run_wait state this might be incorrect.
            if ( DUT.timing.timeout && (DUT.timing.timer != DUT.timing.next_time) ) begin
                $display("%d: timeout does not agree with timer == next_time!", $time);
                $display(DUT.timing.timer);
                $display(DUT.timing.next_time);
                $finish;
            end 
            if ( bus_out_error && (!bus_out_error_ignore)) begin
                $display("%d: error bus data! (only displayed one time)", $time);
                $finish;
                bus_out_error_ignore = 1;
            end
            if ( out_error | out_error_keep ) begin
                $display("%d: RX data output error!", $time);
                $finish;
            end
        end
    end
    endtask

    // continuously check output state
    initial begin
        forever begin
            @(posedge clk_bus);
            check_DUT;
        end
    end
    
    // wait until all data output
    integer conf;
    task wait_end;
    begin
        while ( DUT.status_end != 1'b1 ) begin 
          @(posedge clk_AXI);
          
          if ( DUT.irq_FPGA ) begin //&& ((DUT.status & STATUS_IRQ_ERR) == 0) ) begin
              $display("%d RESET FPGA_IRQ ...", $time);
              // AXI Lite interface: reset IRQ_EN bit
              repeat(5) @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b1;
              AXI_wr_addr = 0*4;
              AXI_wr_data = (CTRL_RUN | conf) & (~CTRL_IRQ_EN);
              @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b0;
              //repeat(5) @(posedge clk_AXI);
              while ( DUT.irq_FPGA ) begin 
                  @(posedge clk_AXI);
              end
              $display("%d RESET FPGA_IRQ DONE", $time);
              // AXI Lite interface: set IRQ_EN bit
              repeat(5) @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b1;
              AXI_wr_addr = 0*4;
              AXI_wr_data = CTRL_RUN | conf | CTRL_IRQ_EN;
              @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b0;
              @(posedge clk_AXI);
          end
        end
    end
    endtask

    // check final state
    integer run = 0;
    task check_end;
    begin
        if ( (DUT.control & END_CTRL_MASK) != END_CTRL_SET ) begin
            $display("%d: check final state!", $time);
            $finish;
        end
        if ( (DUT.status & (~expect_error) & END_STATUS_MASK) != END_STATUS_SET ) begin
            $display("%d: check final state!", $time);
            $finish;
        end
        if ( DUT.error ) begin
            if ((DUT.status & STATUS_ERR_ALL) == expect_error) begin
                $display("%d: final state 0x%x with expected error 0x%x! (ok)", $time, DUT.status, expect_error);
            end
            else begin
                $display("%d: check final state!", $time);
                $finish;
            end
        end
        if ( DUT.num_samples != GEN_NUM_SAMPLES ) begin
            $display("%d: check final state!", $time);
            $finish;
        end
        if ( DUT.board_samples != GEN_NUM_SAMPLES ) begin
            $display("%d: check final state!", $time);
            $finish;
        end
        if ( DUT.board_time != gen_time) begin
            $display("%d: check final state!", $time);
            $finish;
        end
        if ( bus_out_datatime != (gen_datatime_last[GEN_DATA_WIDTH+GEN_TIME_WIDTH-1:0] & BUS_MASK)) begin
            $display("%d: check final state!", $time);
            $display("%x", bus_out_datatime);
            $display("%x", gen_datatime_last[GEN_DATA_WIDTH+GEN_TIME_WIDTH-1:0] & BUS_MASK);
            $finish;
        end
        if ( bus_out_count != GEN_NUM_SAMPLES ) begin
            $display("%d: check final state!", $time);
            $finish;
        end         
        if ( bus_out_skipped != (NUM_NOP + NUM_SKIP_STRB)) begin
            $display("%d: check final state!", $time);
            $finish;
        end
        if ( out_count != GEN_NUM_SAMPLES ) begin
            $display("%d: check final state!", $time);
            $finish;
        end
        if ( out_datatime != gen_datatime[GEN_NUM_SAMPLES-1]) begin
            $display("%d: check final state!", $time);
            $finish;
        end
        if (out_datatime[BITS_PER_SAMPLE] != 1'b1) begin
            $display("%d: check final state!", $time);
            $finish;
        end
        if (( bus_data != 0 ) || ( bus_addr_0 != 0 ) || ( bus_addr_1 != 0 )) begin
            $display("%d: check final state!", $time);
            $finish;
        end
        if ( bus_strb[0] != 1'b0 ) begin  // strb_0 is not toggling!
            $display("%d: check final state!", $time);
            $finish;
        end         
        if ( bus_strb[1] != bus_strb_0_toggle ) begin // strb_1 is toggling! 
            $display("%d: check final state!", $time);
            $finish;
        end        
        if ( ( bus_en[0] != 1'b0 ) || ( bus_en[1] != 1'b1 ) ) begin // TODO: might give an error when one changes output configuration of bus_en bits.
            $display("%d: check final state!", $time);
            $finish;
        end         

        $display("%d: final state 0x%x control 0x%x! (ok)", $time, DUT.status, DUT.control);
        $display("%d *** final state ok! ***", $time);
    end
    endtask
       
    // simulation
    integer conf_out = 0;
    integer tmp = 0;
    integer run_rep = 1;
    integer run_rep_count = 0;
    initial begin
      $display("%d *** start simulation *** ", $time);
      
      // init registers
      buttons_in = 2'b00;
      clk_ext_locked = 1'b0;
      //clk_mux_locked = 1'b0;
      clk_mux_en = 1'b1;
      gen_ctrl = 1'b0;
      gen_ctrl_reset = 1'b0;
      out_ready = 1'b1; // RX stream data ready
      ext_in = 3'b000;
      line_trg_hold = 1'b0;
      
      // init AXI Lite interface
      AXI_wr_data = 0;
      AXI_wr_addr = 0;
      AXI_wr_valid = 1'b0;
      AXI_rd_addr = 0;
      AXI_rd_ready = 1'b0;

      // wait for reset to finish
      @(posedge reset_AXI_n);

      // internal reset waits for PLL to be locked
      repeat(10) @(posedge clk_bus);
      #1 
      //clk_mux_locked = 1'b1;        
      
      // wait for FIFO reset to finish
      while ( reset_AXI_sw_n == 1'b0 ) begin 
        @(posedge clk_AXI);
      end
      
      for (run=0; run < RUNS; run = run + 1) begin
          $display("%d run %d / %d", $time, run, RUNS);
          for (run_rep_count=0; run_rep_count<run_rep; run_rep_count=run_rep_count+1) begin
              $display("%d loop %d / %d", $time, run_rep_count, run_rep);
    
              // control bits for current run        
              if ( run == 0 ) begin
                conf = CTRL_BITS_0;
                conf_trg = CTRL_TRG_0;
                conf_out = CTRL_OUT_0;
                run_rep  = CTRL_REP_0;
              end
              else if ( run == 1 ) begin
                conf = CTRL_BITS_1;
                conf_trg = CTRL_TRG_1;
                conf_out = CTRL_OUT_1;
                run_rep  = CTRL_REP_1;
              end
              else if ( run == 2 ) begin
                conf = CTRL_BITS_2;
                conf_trg = CTRL_TRG_2;  
                conf_out = CTRL_OUT_2;
                run_rep  = CTRL_REP_2;
              end          
              else if ( run == 3 ) begin
                conf = CTRL_BITS_3;
                conf_trg = CTRL_TRG_3;
                conf_out = CTRL_OUT_3;
                run_rep  = CTRL_REP_3;
              end
              else if ( run == 4 ) begin
                conf = CTRL_BITS_4;
                conf_trg = CTRL_TRG_4;
                conf_out = CTRL_OUT_4;
                run_rep  = CTRL_REP_4;
              end
              else if ( run == 5 ) begin
                conf = CTRL_BITS_5;
                conf_trg = CTRL_TRG_5;
                conf_out = CTRL_OUT_5;
                run_rep  = CTRL_REP_5;
              end
              else if ( run == 6 ) begin
                conf = CTRL_BITS_6;
                conf_trg = CTRL_TRG_6;
                conf_out = CTRL_OUT_6;
                run_rep  = CTRL_REP_6;
              end
              else if ( run == 7 ) begin
                conf = CTRL_BITS_7;
                conf_trg = CTRL_TRG_7;
                conf_out = CTRL_OUT_7;
                run_rep  = CTRL_REP_7;
              end
              else if ( run == 8 ) begin
                conf = CTRL_BITS_8;
                conf_trg = CTRL_TRG_8;
                conf_out = CTRL_OUT_8;
                run_rep  = CTRL_REP_8;
              end
              else if ( run == 9 ) begin
                conf = CTRL_BITS_9;
                conf_trg = CTRL_TRG_9;
                conf_out = CTRL_OUT_9;
                run_rep  = CTRL_REP_9;
              end
              else if ( run == 10 ) begin
                conf = CTRL_BITS_10;
                conf_trg = CTRL_TRG_10;
                conf_out = CTRL_OUT_10;
                run_rep  = CTRL_REP_10;
              end
              else if ( run == 11 ) begin
                conf = CTRL_BITS_11;
                conf_trg = CTRL_TRG_11;
                conf_out = CTRL_OUT_11;
                run_rep  = CTRL_REP_11;
              end
              else if ( run == 12 ) begin
                conf = CTRL_BITS_12;
                conf_trg = CTRL_TRG_12;
                conf_out = CTRL_OUT_12;
                run_rep  = CTRL_REP_12;
              end
              else begin
                $display("%d run %d is not properly setup!?", $time, run);
                $finish;
              end
                            
              if (( run == RUN_ABORT_0 ) || ( run == RUN_ABORT_1 ) || ( run == RUN_ABORT_2 )) begin
                // reset line trigger period to ensure board goes into run_wait state
                @(posedge clk_bus);
                line_trg_hold = 1'b1;
                @(posedge clk_bus);
                line_trg_hold = 1'b0;
              end
              // AXI Lite interface: set control bits: SERVER READY
              if ( DUT.control != 0 ) begin
                $display("%d control is not 0!?", $time);
                $finish;
              end
              repeat(50) @(posedge clk_AXI); // ensure conf_out is updated
              #1
              AXI_wr_valid = 1'b1;
              AXI_wr_addr = REG_CTRL;
              AXI_wr_data = CTRL_READY;
              @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b0;
              // wait until data written
              while ( AXI_wr_ready == 1'b0 ) begin 
                @(posedge clk_AXI);
              end
              repeat(1) @(posedge clk_AXI);
              if ( DUT.control != STATUS_READY ) begin
                $display("%d SERVER READY bit is not set!?", $time);
                $finish;
              end
              else begin
                $display("%d *** SERVER READY! *** ", $time);
              end
        
              // lock external clock if selected
              if ( conf & CTRL_CLK_EXT ) begin
                clk_ext_locked = 1'b1;
              end
              else begin
                clk_ext_locked = 1'b0;
              end
    
              // AXI Lite interface: write configuration bits
              #1
              AXI_wr_valid = 1'b1;
              AXI_wr_addr = REG_CTRL;
              AXI_wr_data = conf;
              @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b0;
              // wait until data written
              while ( AXI_wr_ready == 1'b0 ) begin 
                @(posedge clk_AXI);
              end
              repeat(1) @(posedge clk_AXI);
              if ( DUT.control != conf ) begin
                $display("%d CONFIG bit are not set!?", $time);
                $finish;
              end
              else begin
                $display("%d *** CONFIG OK *** ", $time);
              end
              
              // AXI Lite interface: write trigger configuration bits      
              #1
              AXI_wr_valid = 1'b1;
              AXI_wr_addr = REG_CTRL_TRG;
              AXI_wr_data = conf_trg;
              @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b0;
              // wait until data written
              while ( AXI_wr_ready == 1'b0 ) begin 
                @(posedge clk_AXI);
              end
              repeat(1) @(posedge clk_AXI);
              if ( DUT.ctrl_trg != conf_trg ) begin
                $display("%d CTRL TRIG bits are not set!?", $time);
                $finish;
              end
              else begin
                $display("%d *** CTRL TRIG BITS OK *** ", $time);
              end
    
              // AXI Lite interface: write output configuration bits      
              #1
              AXI_wr_valid = 1'b1;
              AXI_wr_addr = REG_CTRL_OUT;
              AXI_wr_data = conf_out;
              @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b0;
              // wait until data written
              while ( AXI_wr_ready == 1'b0 ) begin 
                @(posedge clk_AXI);
              end
              repeat(1) @(posedge clk_AXI);
              if ( DUT.ctrl_out != conf_out ) begin
                $display("%d CTRL OUT bits are not set!?", $time);
                $finish;
              end
              else begin
                $display("%d *** CTRL OUT BITS OK *** ", $time);
              end
    
              // AXI Lite interface write clock divider
              #1
              AXI_wr_valid = 1'b1;
              AXI_wr_addr = REG_CLK_DIV;
              AXI_wr_data = CLK_DIV | (TRG_DIV << CLK_DIV_BITS);
              @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b0;
              // wait until data written
              while ( AXI_wr_ready == 1'b0 ) begin 
                @(posedge clk_AXI);
              end
              repeat(1) @(posedge clk_AXI);
              if ( DUT.clk_div != (CLK_DIV | (TRG_DIV << CLK_DIV_BITS)) ) begin
                $display("%d CLK_DIV not set!?", $time);
                $finish;
              end
              else begin
                $display("%d *** CLK_DIV set OK *** ", $time);
              end
        
              // AXI Lite interface write strobe delay
              #1
              AXI_wr_valid = 1'b1;
              AXI_wr_addr = REG_STRB_DELAY;
              AXI_wr_data = STRB_DELAY;
              @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b0;
              // wait until data written
              while ( AXI_wr_ready == 1'b0 ) begin 
                @(posedge clk_AXI);
              end
              repeat(1) @(posedge clk_AXI);
              if ( DUT.strb_delay != STRB_DELAY ) begin
                $display("%d STRB_DELAY not set!?", $time);
                $finish;
              end
              else begin
                $display("%d *** STRB_DELAY set OK *** ", $time);
              end
        
              // AXI Lite interface write sync delay
              #1
              AXI_wr_valid = 1'b1;
              AXI_wr_addr = REG_SYNC_DELAY;
              if ( conf & CTRL_AS_PRIM ) 
                AXI_wr_data = SYNC_DELAY;
              else
                AXI_wr_data = 0;
              @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b0;
              // wait until data written
              while ( AXI_wr_ready == 1'b0 ) begin 
                @(posedge clk_AXI);
              end
              repeat(1) @(posedge clk_AXI);
              if ( DUT.sync_delay != AXI_wr_data ) begin
                $display("%d SYNC_DELAY not set!?", $time);
                $finish;
              end
              else begin
                $display("%d *** SYNC_DELAY set OK *** ", $time);
              end
        
              // AXI Lite interface write sync phase
              #1
              AXI_wr_valid = 1'b1;
              AXI_wr_addr = REG_SYNC_PHASE;
              AXI_wr_data = SYNC_PHASE;
              @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b0;
              // wait until data written
              while ( AXI_wr_ready == 1'b0 ) begin 
                @(posedge clk_AXI);
              end
              repeat(1) @(posedge clk_AXI);
              if ( DUT.sync_phase != SYNC_PHASE ) begin
                $display("%d SYNC_PHASE not set!?", $time);
                $finish;
              end
              else begin
                $display("%d *** SYNC_PHASE set OK *** ", $time);
              end
        
              // AXI Lite interface: write NUM_SAMPLES
              if ((run == 0) && ( DUT.num_samples != 0 )) begin
                $display("%d NUM_SAMPLES %d not 0!?", $time, DUT.num_samples);
                $finish;
              end
              if ( AXI_wr_ready != 1'b1 ) begin
                $display("%d AXI write not ready!?", $time);
                $finish;
              end
              #1
              AXI_wr_data = GEN_NUM_SAMPLES;
              AXI_wr_addr = REG_NUM_SAMPLES;
              AXI_wr_valid = 1'b1;
              @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b0;
              // wait until data written
              while ( AXI_wr_ready == 1'b0 ) begin 
                @(posedge clk_AXI);
              end
              repeat(2) @(posedge clk_AXI);
              if ( DUT.num_samples == GEN_NUM_SAMPLES ) begin
                $display("%d *** NUM_SAMPLES written (ok) *** ", $time);
              end
              else begin
                $display("%d NUM_SAMPLES writing error!", $time);
                $finish;
              end
              
              // after num_samples written we can generate TX data
              repeat(5) @(posedge clk_AXI);
              gen_ctrl = 1'b1;
              
              // AXI Lite interface: read NUM_SAMPLES
              #1
              AXI_rd_addr = REG_NUM_SAMPLES;
              AXI_rd_ready = 1'b1;
              @(posedge clk_AXI);
              #1
              // wait until data read
              while ( AXI_rd_valid == 1'b0 ) begin 
                @(posedge clk_AXI);
              end
              repeat(1) @(posedge clk_AXI);
              if ( AXI_rd_data == GEN_NUM_SAMPLES ) begin
                $display("%d *** NUM_SAMPLES read (ok) *** ", $time);
              end
              else begin
                $display("%d NUM_SAMPLES reading error!", $time);
                $finish;
              end
              #1
              AXI_rd_ready = 1'b0;
        
              // wait for ready bit = first data arrived      
              while ( DUT.status_ready == 1'b0 ) begin 
                @(posedge clk_AXI);
              end
              $display("%d *** READY! *** ", $time);
        
              // AXI Lite interface: set RUN bit
              repeat(125) @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b1;
              AXI_wr_addr = REG_CTRL;
              AXI_wr_data = CTRL_RUN | conf;
              @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b0;
              
              // wait until run bit is set
              while ( DUT.run_en == 1'b0 ) begin 
                @(posedge clk_bus);
              end
              if ( ( DUT.run_en != 1'b1 ) || ( DUT.control != (CTRL_RUN|conf) ) ) begin
                $display("%d RUN bit is not set!?", $time);
                $finish;
              end
              else begin
                $display("%d *** RUN! *** ", $time);
              end
              
              // check if ext clock is selected or not as configured
              if ( conf & CTRL_CLK_EXT ) begin
                if ( clk_ext_sel == 1'b1 ) begin
                    $display("%d ext. clock selected (ok)", $time);
                end
                else begin
                    $display("%d ext. clock not selected!?", $time);
                    $finish;
                end
              end
              else begin
                if ( clk_ext_sel == 1'b1 ) begin
                  $display("%d ext. clock selected but should be free running!?", $time);
                  $finish;
                end
                else begin
                  $display("%d ext. clock not selected (ok)", $time);
                end
              end
                            
              // if external start trigger enabled check that boad is waiting
              // note: we use line_trg signal for all trigger signals
              if ( conf_trg[CTRL_TRG_DST_START + CTRL_TRG_SRC_BITS-1 -: CTRL_TRG_SRC_BITS] != CTRL_TRG_SRC_NONE ) begin
                // wait for start trigger and ensure run bit is not set in status
                if ( conf_trg[CTRL_TRG_DST_START + CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_EDGE_RISING ) begin // rising edge
                    if ( line_trg == 1'b1 ) begin
                        $display("%d *** EXT_TRIG waiting for rising edge (high) ... *** ", $time);
                        while( line_trg == 1'b1 ) begin
                            if ( DUT.status_run ) begin
                                $display("%d *** EXT_TRIG error: not waiting for rising edge! *** ", $time);
                                $finish;
                            end
                            @(posedge clk_bus);
                        end
                    end
                    $display("%d *** EXT_TRIG waiting for rising edge (low) ... *** ", $time);
                    while( line_trg == 1'b0 ) begin
                        if ( DUT.status_run ) begin
                            $display("%d *** EXT_TRIG error: not waiting for rising edge! *** ", $time);
                            $finish;
                        end
                        @(posedge clk_bus);
                    end
                    $display("%d *** EXT_TRIG rising edge now! *** ", $time);            
                    while( DUT.status_run == 1'b0 ) begin
                        @(posedge clk_bus);
                    end
                    $display("%d *** EXT_TRIG rising edge ok! *** ", $time);            
                end
                else if ( conf_trg[CTRL_TRG_DST_START + CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_EDGE_FALLING ) begin // falling edge
                    while( line_trg == 1'b0 ) begin
                        if ( DUT.status_run ) begin
                            $display("%d *** EXT_TRIG error: not waiting for falling edge! *** ", $time);
                            $finish;
                        end
                        @(posedge clk_bus);
                    end
                    while( line_trg == 1'b1 ) begin
                        if ( DUT.status_run ) begin
                            $display("%d *** EXT_TRIG error: not waiting for falling edge! *** ", $time);
                            $finish;
                        end
                        @(posedge clk_bus);
                    end
                    $display("%d *** EXT_TRIG falling edge now! *** ", $time);            
                    while( DUT.status_run == 1'b0 ) begin
                        @(posedge clk_bus);
                    end
                    $display("%d *** EXT_TRIG falling edge ok! *** ", $time);            
                end
                else if ( conf_trg[CTRL_TRG_DST_START + CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_LEVEL_HIGH ) begin // high level
                    while( line_trg == 1'b0 ) begin
                        if ( DUT.status_run ) begin
                            $display("%d *** EXT_TRIG error: not waiting for high level! *** ", $time);
                            $finish;
                        end
                        @(posedge clk_bus);
                    end
                    $display("%d *** EXT_TRIG level high now! *** ", $time);            
                    while( DUT.status_run == 1'b0 ) begin
                        @(posedge clk_bus);
                    end
                    $display("%d *** EXT_TRIG level high ok! *** ", $time);            
                end
                else if ( conf_trg[CTRL_TRG_DST_START + CTRL_TRG_DST_BITS-1 -: CTRL_TRG_LEVEL_BITS] == CTRL_TRG_LEVEL_LOW ) begin // low level
                    while( line_trg == 1'b1 ) begin
                        if ( DUT.status_run ) begin
                            $display("%d *** EXT_TRIG error: not waiting for low level! *** ", $time);
                            $finish;
                        end
                        @(posedge clk_bus);
                    end
                    $display("%d *** EXT_TRIG level low now! *** ", $time);            
                    while( DUT.status_run == 1'b0 ) begin
                        @(posedge clk_bus);
                    end
                    $display("%d *** EXT_TRIG level low ok! *** ", $time);            
                end
                else begin
                    $display("%d *** EXT_TRIG error: unknown level! *** ", $time);
                    $finish;
                end
              end
              
              if ( ( run == HOLD_LINE_TRG_0 ) || ( run == HOLD_LINE_TRG_1 ) || ( run == HOLD_LINE_TRG_2 ) ) begin
                // hold line trigger for loop clk_bus cycles
                @(posedge clk_bus2);
                line_trg_hold = 1'b1;
                repeat(run_rep_count+1) @(posedge clk_bus2);
                line_trg_hold = 1'b0;
              end
            
              if (( run == RUN_ABORT_0 ) || ( run == RUN_ABORT_1 ) || ( run == RUN_ABORT_2 )) begin
                // for testing abort data output and reset after ABORT_RUN samples
                
                if (run == RUN_ABORT_0) begin
                    // wait for RUN_ABORT_SAMPLES
                    while( bus_out_count < RUN_ABORT_SAMPLES ) begin
                        @(posedge clk_AXI);
                        #1;
                    end
                end
                else begin
                    // wait until board is in wait state (requires stop trigger to be active and restart inactive!)
                    // reset line trigger
                    $display("%d waiting until board is in wait state ...", $time);
                    while( DUT.status_wait == 1'b0 ) begin
                        @(posedge clk_AXI);
                        #1;
                    end
                    $display("%d WAIT state (should not restart)", $time);
                    tmp = line_trg;
                    while( line_trg == tmp ) begin
                        @(posedge clk_AXI);
                        #1;
                    end
                    while( line_trg != tmp ) begin
                        @(posedge clk_AXI);
                        #1;
                    end
                    while( line_trg == tmp ) begin
                        @(posedge clk_AXI);
                        #1;
                    end
                    repeat(50) @(posedge clk_AXI);
                    #1
                    if (DUT.status_wait == 1'b0) begin
                        $display("%d error: WAIT state restarted!", $time);
                        $finish;
                    end
                    else begin
                        $display("%d WAIT state (ok)", $time);
                    end
                end
    
                if ( ( run == RUN_ABORT_0 ) || ( run == RUN_ABORT_1 ) ) begin
                    // reset run bit and wait until board is stopped
                    // AXI Lite interface: reset RUN bit
                    AXI_wr_valid = 1'b1;
                    AXI_wr_addr = REG_CTRL;
                    AXI_wr_data = conf;
                    @(posedge clk_AXI);
                    #1
                    AXI_wr_valid = 1'b0;
                    // wait until data is written
                    while ( AXI_wr_ready == 1'b0 ) begin 
                      @(posedge clk_AXI);
                    end
                    repeat(CLK_DIV*2) @(posedge clk_bus);
                    // this has been changed. now the run | wait bits should be set when run_en is reset during run.
                    //if ( ( DUT.run_en != 1'b0 ) || ( DUT.status_run != 1'b0 ) || ( DUT.status_wait != 1'b0 ) || ( DUT.control != (conf) ) ) begin
                    //$display("%d RUN bit is not reset or board not stopped!?", $time);
                    if ( ( DUT.run_en != 1'b0 ) || ( DUT.status_run != 1'b1 ) || ( DUT.status_wait != 1'b1 ) || ( DUT.control != (conf) ) ) begin
                      $display("%d RUN | WAIT should be set!?", $time);
                      $finish;
                    end
                    else begin
                      $display("%d *** RUN bit reset and board STOPPED! *** ", $time);
                    end
                    
                    // ensure board is not restarted by restart trigger
                    tmp = line_trg;
                    while( line_trg == tmp ) begin
                        @(posedge clk_AXI);
                        #1;
                    end
                    while( line_trg != tmp ) begin
                        @(posedge clk_AXI);
                        #1;
                    end
                    while( line_trg == tmp ) begin
                        @(posedge clk_AXI);
                        #1;
                    end
                    repeat(50) @(posedge clk_AXI);
                    //if ( ( DUT.run_en != 1'b0 ) || ( DUT.status_run != 1'b0 ) || ( DUT.status_wait != 1'b0 ) || ( DUT.control != (conf) ) ) begin
                    //  $display("%d board is not stopped after trigger!?", $time);
                    if ( ( DUT.run_en != 1'b0 ) || ( DUT.status_run != 1'b1 ) || ( DUT.status_wait != 1'b1 ) || ( DUT.control != (conf) ) ) begin
                      $display("%d board is not stopped after trigger!?", $time);
                      $finish;
                    end
                    else begin
                      $display("%d *** board remains STOPPED! *** ", $time);
                    end
                end
    
              end
              else if ( (run == RUN_CLOCK_LOSS_SHORT) || (run == RUN_CLOCK_LOSS) || (run == RUN_CLOCK_LOSS_IGNORE) ) begin
                // simulate clock loss
                
                // wait for some samples
                while( bus_out_count < RUN_CLOCK_LOSS_SAMPLES ) begin
                  @(posedge clk_AXI);
                  #1;
                end
                
                // after this we expect external clock lost in status
                $display("%d *** EXT CLOCK LOSS! ***", $time);
                expect_error = STATUS_ERR_LOCK;
                
                if ( run == RUN_CLOCK_LOSS_SHORT ) begin
                    // simulate short clock loss. do not expect error.
                    #1;
                    clk_ext_locked = 1'b0;
                    repeat(ERROR_LOCK_DELAY/2-1) @(posedge clk_AXI);
                    #1;
                    clk_ext_locked = 1'b1;
                end
                else if ( run == RUN_CLOCK_LOSS ) begin
                    // simulate not so short clock loss. expect error.
                    #3;
                    clk_mux_en = 1'b0;
                    repeat(50) @(posedge clk_AXI);
                    #1;
                    clk_ext_locked = 1'b0;
                    //clk_mux_locked = 1'b0;
                    repeat(ERROR_LOCK_DELAY) @(posedge clk_AXI);
                    #1;
                    clk_mux_en = 1'b1;
                    repeat(50) @(posedge clk_AXI);
                    #1;
                    clk_ext_locked = 1'b1;
                    //clk_mux_locked = 1'b1;
                end
                else begin
                    // simulate permanent clock loss.
                    #3;
                    clk_mux_en = 1'b0;
                    repeat(50) @(posedge clk_AXI);
                    #1;
                    clk_ext_locked = 1'b0;
                    //clk_mux_locked = 1'b0;
                end
                
                // wait until clock loss detected. status should reflect clock loss always.
                while( (DUT.status & STATUS_ERR_ALL) != expect_error) begin
                    @(posedge clk_AXI);
                end
    
                if ( run == RUN_CLOCK_LOSS_SHORT ) begin
                    $display("%d *** SHORT EXT CLOCK LOSS DETECTED! CONT. RUN ***", $time);
                    // wait until all data output
                    wait_end;
                    repeat(20) @(posedge clk_AXI);
                    check_end;
                end
                else if ( run == RUN_CLOCK_LOSS ) begin
                    $display("%d *** EXT CLOCK LOSS! WAIT ERROR ***", $time);
                    // wait until in error state
                    while ( (DUT.error_lock != 1'b1) || (DUT.error != 1'b1) ) begin 
                      @(posedge clk_AXI);
                    end
                    $display("%d *** ERROR STATE. OK ***", $time);
                end
                else begin
                    $display("%d *** EXT CLOCK LOSS! CONT. RUN ***", $time);
                    // wait until all data output
                    wait_end;
                    repeat(20) @(posedge clk_AXI);
                    check_end;
                end
                // reset external clock
                repeat(5) @(posedge clk_AXI);
                #1;
                clk_mux_en = 1'b1;
                //clk_mux_locked = 1'b1;
              end
              else begin
                  // wait until all data output
                  wait_end;
                  repeat(20) @(posedge clk_AXI);
                  check_end;
              end
              
              // stop and reset TX data generation
              repeat(5) @(posedge clk_AXI);
              gen_ctrl = 1'b0;
              gen_ctrl_reset = 1'b1;
              @(posedge clk_AXI);
              #1
              gen_ctrl_reset = 1'b0;
    
              // AXI Lite interface: activate software reset
              repeat(25) @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b1;
              AXI_wr_addr = REG_CTRL;
              AXI_wr_data = CTRL_RESET;
              @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b0;
              // wait until data written
              while ( AXI_wr_ready == 1'b0 ) begin 
                @(posedge clk_AXI);
              end
              
              if ( reset_AXI_sw_n != 1'b0 ) begin
                $display("%d not in RESET mode!?", $time);
                $finish;
              end
              else begin
                $display("%d *** software RESET! *** ", $time);
              end
    
              // wait until slow reset
              while ( DUT.status & STATUS_RESET != STATUS_RESET ) begin 
                @(posedge clk_AXI);
              end
              $display("%d *** software RESET active! *** ", $time);
        
              // wait until reset is done
              while ( ( (DUT.status & (~STATUS_LOCKED)) != STATUS_RST_END ) || 
                      ( DUT.control != 0 ) || 
                      ( reset_AXI_sw_n != 1'b1 ) ||
                      ( DUT.reset_active_n != 1'b1 ) ) begin 
                @(posedge clk_AXI);
              end
              $display("%d *** software RESET done! *** ", $time);
              
              // now all errors should be reset
              expect_error = 0;
        
              repeat(20) @(posedge clk_AXI);
              $display("%d loop %d/%d finished", $time, run_rep_count, run_rep_count);
          end
          $display("%d run %d/%d finished", $time, run, RUNS);
          $finish;
      end

      $display("%d *** all %d reps. finished *** ", $time, run);
      $finish;
    
    end    
endmodule
