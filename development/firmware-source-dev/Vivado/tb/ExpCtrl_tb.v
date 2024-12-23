`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// test bench for ExpCtrl_top module
// created 24/03/2020 by Andi
// last change 2024/12/04 by Andi
//////////////////////////////////////////////////////////////////////////////////

module ExpCtrl_tb ();

    //////////////////////////////////////////////////////////////////////////////////    
    // parameters

    `include "reg_params.vh"
    `include "ctrl_in_params.vh"
    `include "ctrl_out_params.vh"

    // user-provided version and info register content
    parameter integer VERSION               = 32'h0104_3184;    // version register (24<<9+12<<5+4=0x3184)
    parameter integer INFO                  = 32'h0000_00c0;    // info  register; 0xc0/c1 = Cora-Z7-07S/-10

    // fixed data widths needed for port definitions. do not change.
    parameter integer AXI_ADDR_WIDTH        = 8;        // 8: 2^8/4 = 64 registers
    parameter integer AXI_DATA_WIDTH        = 32;       // must be 32
    parameter integer STREAM_DATA_WIDTH     = 64;       // fixed 64
    parameter integer BUS_ADDR_BITS         = 8;        // 7 (Florence) or 8 (Innsbruck)
    parameter integer BUS_DATA_BITS         = 16;       // 16 fixed
    parameter integer BUS_RESET             = 0;        // 0 = keep bus after end at last state; otherwise reset to zero.
    parameter integer NUM_STRB              = 2;        // number of bits for bus_strb (1 or 2)
    parameter integer NUM_BUS_EN            = 2;        // number of bits for bus_en (1 or 2)
        
    // I/O bits
    parameter integer NUM_IN                = 3;       // number of external inputs
    parameter integer NUM_OUT               = 3;       // number of external outputs

    // LEDs and buttons 
    parameter integer NUM_BUTTONS   = 2;        // must be 2
    parameter integer NUM_LED_RED   = 2;        // must be 2
    parameter integer NUM_LED_GREEN = 2;        // must be 2
    parameter integer NUM_LED_BLUE  = 2;        // must be 2
    parameter         INV_RED       = 2'b00;    // bit for each LED
    parameter         INV_GREEN     = 2'b00;    // bit for each LED
    parameter         INV_BLUE      = 2'b00;    // bit for each LED
    // bits used for blinking leds ON-time: 1=50%; 2=25%; 3=12.5%; 4=6.25%
    parameter integer LED_BLINK_ON          = 3;
    // bits used for blinking leds
    parameter integer LED_SLOW              = 26;       // blink slow
    parameter integer LED_FAST              = 24;       // blink fast (1.. < LED_SLOW)
    // bits used for PWM dimming of leds. 0 = no dimming.
    parameter integer LED_DIM_LOW           = 8;        // dim level low (< LED_SLOW)
    parameter integer LED_DIM_HIGH          = 6;        // dim level high (< LED_SLOW)
    parameter integer LED_BRIGHT_LOW        = 1;        // bright level low (< LED_SLOW)
    parameter integer LED_BRIGHT_HIGH       = 1;        // bright level high (1 .. < LED_SLOW)
    
    // data and time bits
    parameter integer TIME_BITS             = AXI_DATA_WIDTH;   // must be 32
    parameter integer TIME_START            = 0;                // typically 0
    parameter integer DATA_BITS             = AXI_DATA_WIDTH;   // must be 32
    parameter integer DATA_START_64         = 32;               // typically 32
    parameter integer DATA_START_96_0       = 32;               // typically 32
    parameter integer DATA_START_96_1       = 64;               // typically 64    
    parameter integer CLK_DIV_BITS          = 8;                // 8
    parameter integer SYNC_DELAY_BITS       = 10;               // 10

    // auto-sync
    parameter integer AUTO_SYNC_PULSE_LENGTH = 3;               // 2 = 40ns @ 50MHz 
    parameter integer AUTO_SYNC_PULSE_WAIT   = 5;               // 3 = 60ns @ 50MHz; wait time after pulse
    parameter integer AUTO_SYNC_MAX_PULSES   = 2;               // 2 
    parameter integer AUTO_SYNC_TIME_BITS    = 8;               // 8
    parameter integer AUTO_SYNC_PHASE_BITS   = 12;               // 12     
    
    // bus data and address bits without strobe bit
    parameter         BUS_ADDR_1_USE = "DATA_HIGH";    // "ZERO"/"ADDR0"/"DATA_HIGH" = low / same as bus_addr_0; data[31:24] 

    // special data bits. <0 or outside given range to disable. 
    // absolute value is taken to generate data with these bits.
    parameter integer BIT_NOP  = 31;                               // 28-31
    parameter integer BIT_STOP = 30;                               // 28-31
    //parameter integer BIT_IRQ  = -29;                              // 28-31 TODO: this is not tested!
    parameter integer BIT_STRB = (BUS_DATA_BITS+BUS_ADDR_BITS);    // 23-24
    
    // synchronization stages
    parameter integer SYNC     = 2;             // 2-3 (2)
    parameter integer SYNC_EXT = 3;             // 2-3 (3)
    
    // irq_FPGA frequency bits
    parameter integer IRQ_FREQ_BITS = 6;        // set to 6 if want to see this
    
    parameter integer ERROR_LOCK_DELAY = 8;     // 5/6/8 = 1/2/3 clk_AXI cycles of clk_ext_clock loss is acceptable 
    
    // TX and RX FIFO
    parameter integer TX_FIFO_DEPTH = 8192;
    parameter integer RX_FIFO_DEPTH = 8192;
        
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
    
    // return absolute value
    function integer abs(input integer value);
    begin
        abs = (value<0) ? -value : value;
    end
    endfunction

    //////////////////////////////////////////////////////////////////////////////////    

    // number of generated samples   
    // TODO: with 1 check_end gives fake errors.
    //       for small samples (ca. <10) is already in end state when waits for trigger.
    localparam integer GEN_NUM_SAMPLES = 19;
    
    // number of runs
    // after each run performs a software reset.
    // for details of each run see CTRL_BITS_ definitions below
    localparam integer RUNS = 14;
    
    // abort data ouput in given run
    localparam integer RUN_ABORT_SAMPLES = GEN_NUM_SAMPLES - 5;
    
    // experimental run and samples where clock is lost
    localparam integer RUN_CLOCK_LOSS_SAMPLES = 6;
    
    // every # of samples stop trigger bit is set
    localparam integer STOP_TRG_DATA_SAMPLE = 10;

    // clock divider for bus
    localparam integer CLK_DIV          = 20;   // clock divider (normally 5-100, TODO: at 4 strobe does not work)
    
    // strobe delay {strb_end_1,strb_start_1,strb_end_0,strb_start_0}
    // strb_end = 0x00 = toggle strobe at given strb_start
    localparam integer STRB_DELAY = 32'h0005_0b01;
    
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
    localparam integer PERIOD_LINE      = 900;          // line trigger period used as tart trigger
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
    
    // if != 0 invert line trigger
    // useful for testing trigger levels and edges
    localparam integer LINE_TRG_INVERTED = 0;
    
    // data generator settings
    localparam integer GEN_DATA_WIDTH    = 32;
    localparam integer GEN_TIME_WIDTH    = 32;
    localparam         GEN_DATA_START    = 32'h0003_0201;   // initial data + address
    localparam         GEN_DATA_STEP     = 32'h0001_0101;   // added in every step
    localparam         GEN_TIME_START    = 32'h0000_0000;   // initial time >= 0
    localparam integer GEN_SAMPLE_WIDTH  = GEN_DATA_WIDTH+GEN_TIME_WIDTH+1; // time+data+last
    
    // control and status bits
    localparam integer CTRL_64          = (1<<CTRL_READY) | CTRL_IRQ_ALL; 
    localparam integer CTRL_96          = CTRL_64 | (1<<CTRL_BPS96); 
    localparam integer CTRL_AS_PRIM     = (1<<CTRL_AUTO_SYNC_EN) | (1<<CTRL_AUTO_SYNC_PRIM);
    localparam integer CTRL_AS_SEC      = (1<<CTRL_AUTO_SYNC_EN);
    localparam integer CTRL_CLK_EXT_EN  = (1<<CTRL_CLK_EXT) | (1<<CTRL_ERR_LOCK_EN);
    localparam integer CTRL_CLK_EXT_IGNORE = (1<<CTRL_CLK_EXT);
    localparam integer STATUS_RST_END   = 'h0000_0000;    // status after reset
            
    // NOP data bit 31
    localparam integer CTRL_IN1_DATA_NOP = (BIT_NOP == 31) ? (CTRL_IN_SRC_DATA_31 << (CTRL_IN1_DST_DATA_NOP*CTRL_IN_SRC_BITS)) : 
                                           (BIT_NOP == 30) ? (CTRL_IN_SRC_DATA_30 << (CTRL_IN1_DST_DATA_NOP*CTRL_IN_SRC_BITS)) :
                                           (BIT_NOP == 29) ? (CTRL_IN_SRC_DATA_30 << (CTRL_IN1_DST_DATA_NOP*CTRL_IN_SRC_BITS)) :
                                           (BIT_NOP == 28) ? (CTRL_IN_SRC_DATA_30 << (CTRL_IN1_DST_DATA_NOP*CTRL_IN_SRC_BITS)) : 0;

    // STRB data bit 23 or 24
    // note: this is for historic reasons. use NOP bit instead.
    //       only used by Yb lab and even there not fully (as far as I understand). 
    //       support might be stopped in the near future.
    localparam integer CTRL_IN1_DATA_STRB = (BIT_STRB == 24) ? (CTRL_IN_SRC_DATA_24 << (CTRL_IN1_DST_DATA_STRB*CTRL_IN_SRC_BITS)) :
                                            (BIT_STRB == 23) ? (CTRL_IN_SRC_DATA_23 << (CTRL_IN1_DST_DATA_STRB*CTRL_IN_SRC_BITS)) : 0; 

    // start trigger configuration. 
    // you can use LINE_TRG_INVERTED to test different levels and edges.
    localparam integer CTRL_TRG_START_SRC       = CTRL_IN_SRC_IN2;
    localparam integer CTRL_TRG_START_EDGE_POS  = (CTRL_TRG_START_SRC == CTRL_IN_SRC_IN0_EDGE_POS) ||
                                                  (CTRL_TRG_START_SRC == CTRL_IN_SRC_IN1_EDGE_POS) ||
                                                  (CTRL_TRG_START_SRC == CTRL_IN_SRC_IN2_EDGE_POS);
    localparam integer CTRL_TRG_START_EDGE_NEG  = (CTRL_TRG_START_SRC == CTRL_IN_SRC_IN0_EDGE_NEG) ||
                                                  (CTRL_TRG_START_SRC == CTRL_IN_SRC_IN1_EDGE_NEG) ||
                                                  (CTRL_TRG_START_SRC == CTRL_IN_SRC_IN2_EDGE_NEG);
    localparam integer CTRL_TRG_START_HIGH      = (CTRL_TRG_START_SRC == CTRL_IN_SRC_IN0) ||
                                                  (CTRL_TRG_START_SRC == CTRL_IN_SRC_IN1) ||
                                                  (CTRL_TRG_START_SRC == CTRL_IN_SRC_IN2);
    localparam integer CTRL_TRG_START_LOW       = (CTRL_TRG_START_SRC == CTRL_IN_SRC_IN0_INV) ||
                                                  (CTRL_TRG_START_SRC == CTRL_IN_SRC_IN1_INV) ||
                                                  (CTRL_TRG_START_SRC == CTRL_IN_SRC_IN2_INV);
    localparam integer CTRL_TRG_START           = CTRL_TRG_START_SRC << (CTRL_IN0_DST_TRG_START*CTRL_IN_SRC_BITS);  

    // stop trigger configuration
    localparam integer CTRL_TRG_STOP        = CTRL_IN_SRC_IN1_EDGE_POS << (CTRL_IN0_DST_TRG_STOP*CTRL_IN_SRC_BITS);  
  
    // data stop trigger with stop bit 28-31
    // sample with stop bit = STOP_TRG_DATA_SAMPLE
    localparam integer CTRL_TRG_DATA_STOP   = (BIT_STOP == 31) ? (CTRL_IN_SRC_DATA_31 << (CTRL_IN0_DST_TRG_STOP*CTRL_IN_SRC_BITS)) : 
                                              (BIT_STOP == 30) ? (CTRL_IN_SRC_DATA_30 << (CTRL_IN0_DST_TRG_STOP*CTRL_IN_SRC_BITS)) :
                                              (BIT_STOP == 29) ? (CTRL_IN_SRC_DATA_29 << (CTRL_IN0_DST_TRG_STOP*CTRL_IN_SRC_BITS)) :
                                              (BIT_STOP == 28) ? (CTRL_IN_SRC_DATA_28 << (CTRL_IN0_DST_TRG_STOP*CTRL_IN_SRC_BITS)) : 0;  
    
    // restart trigger
    localparam integer CTRL_TRG_RESTART     = CTRL_IN_SRC_IN2_EDGE_POS << (CTRL_IN0_DST_TRG_RESTART*CTRL_IN_SRC_BITS);
    // output configuration bits
    // sync_out configuration
    localparam integer SYNC_OUT_DST = CTRL_OUT0_DST_OUT0;
    localparam SYNC_OUT_INVERTED = "YES";

    // bus enable 0 configuration
    localparam BUS_EN_0_INVERTED = "YES";
    localparam integer BUS_0_ENABLED = (BUS_EN_0_INVERTED == "YES") ? 1'b0 : 1'b1;

    // bus enable 1 configuration
    localparam BUS_EN_1_INVERTED = "NO";
    localparam integer BUS_1_ENABLED = (BUS_EN_1_INVERTED == "YES") ? 1'b0 : 1'b1;

    // sync out on external out 0
    localparam integer CTRL_SYNC_OUT     = ((SYNC_OUT_INVERTED == "YES") ? CTRL_OUT_SRC_SYNC_OUT_INV : CTRL_OUT_SRC_SYNC_OUT) << (SYNC_OUT_DST*CTRL_OUT_SRC_BITS);
                             
    // external output 1 and 2       
    localparam integer CTRL_OUT12 = ( CTRL_OUT_SRC_STRB0_CONT << (CTRL_OUT0_DST_OUT1*CTRL_OUT_SRC_BITS)) |
                                    ( CTRL_OUT_SRC_STRB1_CONT << (CTRL_OUT0_DST_OUT2*CTRL_OUT_SRC_BITS)) ;

    // bus endable signals
    localparam integer CTRL_BUS_OUT_EN_0 = ((BUS_EN_0_INVERTED == "YES") ? CTRL_OUT_SRC_FIXED_LOW : CTRL_OUT_SRC_FIXED_HIGH) << (CTRL_OUT0_DST_BUS_EN_0*CTRL_OUT_SRC_BITS);  
    localparam integer CTRL_BUS_OUT_EN_1 = ((BUS_EN_1_INVERTED == "YES") ? CTRL_OUT_SRC_FIXED_LOW : CTRL_OUT_SRC_FIXED_HIGH) << (CTRL_OUT0_DST_BUS_EN_1*CTRL_OUT_SRC_BITS);

    // leds outputs
    localparam integer CTRL_LEDS = (CTRL_OUT_SRC_ERROR      << (CTRL_OUT1_DST_LED_R*CTRL_OUT_SRC_BITS)) |
                                   (CTRL_OUT_SRC_RUN        << (CTRL_OUT1_DST_LED_G*CTRL_OUT_SRC_BITS)) |
                                   (CTRL_OUT_SRC_CLK_LOCKED << (CTRL_OUT1_DST_LED_B*CTRL_OUT_SRC_BITS));


    // control bits to be configured for each run
    // check RUNS, RUN_ABORT_#, RUN_CLOCK_LOSS_# and if (run == #) cases when changing these!
    // run 0: start as single board and run normal until end
    localparam integer CTRL_BITS_0     = CTRL_64 | (1<<CTRL_RESTART_EN);
    localparam integer CTRL_IN0_0      = 0; 
    localparam integer CTRL_IN1_0      = CTRL_IN1_DATA_NOP | CTRL_IN1_DATA_STRB; 
    localparam integer CTRL_OUT0_0     = CTRL_OUT12 | CTRL_BUS_OUT_EN_0 | CTRL_BUS_OUT_EN_1;
    localparam integer CTRL_OUT1_0     = CTRL_LEDS;
    localparam integer CTRL_REP_0      = 1;    
    localparam integer CTRL_CYCLES_0   = 3;    
    // run 1: start as single board with external start/stop/restart trigger until end
    localparam integer CTRL_BITS_1     = CTRL_64;
    localparam integer CTRL_IN0_1      = CTRL_TRG_START | CTRL_TRG_STOP | CTRL_TRG_RESTART;
    localparam integer CTRL_IN1_1      = CTRL_IN1_DATA_NOP | CTRL_IN1_DATA_STRB;
    localparam integer CTRL_OUT0_1     = CTRL_SYNC_OUT | CTRL_OUT12 | CTRL_BUS_OUT_EN_0 | CTRL_BUS_OUT_EN_1; 
    localparam integer CTRL_OUT1_1     = CTRL_LEDS;
    localparam integer CTRL_REP_1      = 1;    
    localparam integer CTRL_CYCLES_1   = 1;    
    // run 2: start as single board with external start/data stop/restart trigger until end
    localparam integer CTRL_BITS_2     = CTRL_64;
    localparam integer CTRL_IN0_2      = CTRL_TRG_START | CTRL_TRG_DATA_STOP | CTRL_TRG_RESTART;
    localparam integer CTRL_IN1_2      = CTRL_IN1_DATA_NOP | CTRL_IN1_DATA_STRB;
    localparam integer CTRL_OUT0_2     = CTRL_SYNC_OUT | CTRL_OUT12 | CTRL_BUS_OUT_EN_0 | CTRL_BUS_OUT_EN_1; 
    localparam integer CTRL_OUT1_2     = CTRL_LEDS;
    localparam integer CTRL_REP_2      = 1;    
    localparam integer CTRL_CYCLES_2   = 1;    
    // run 3: start as primary board without trigger, until end
    localparam integer CTRL_BITS_3     = CTRL_64 | CTRL_AS_PRIM;
    localparam integer CTRL_IN0_3      = 0;
    localparam integer CTRL_IN1_3      = CTRL_IN1_DATA_NOP | CTRL_IN1_DATA_STRB;
    localparam integer CTRL_OUT0_3     = CTRL_SYNC_OUT | CTRL_OUT12 | CTRL_BUS_OUT_EN_0 | CTRL_BUS_OUT_EN_1; 
    localparam integer CTRL_OUT1_3     = CTRL_LEDS;
    localparam integer CTRL_REP_3      = 1;    
    localparam integer CTRL_CYCLES_3   = 1;    
    // run 4: start as primary board with start/stop/restart trigger and external clock, until end
    localparam integer CTRL_BITS_4     = CTRL_64 | CTRL_AS_PRIM;
    localparam integer CTRL_IN0_4      = CTRL_TRG_START | CTRL_TRG_STOP | CTRL_TRG_RESTART;
    localparam integer CTRL_IN1_4      = CTRL_IN1_DATA_NOP | CTRL_IN1_DATA_STRB;
    localparam integer CTRL_OUT0_4     = CTRL_SYNC_OUT | CTRL_OUT12 | CTRL_BUS_OUT_EN_0 | CTRL_BUS_OUT_EN_1;
    localparam integer CTRL_OUT1_4     = CTRL_LEDS;
    localparam integer CTRL_REP_4      = 1;    
    localparam integer CTRL_CYCLES_4   = 1;    
    // run 5: start as primary board with start/stop/restart trigger, abort with software reset
    localparam integer CTRL_BITS_5     = CTRL_64 | CTRL_AS_PRIM;
    localparam integer CTRL_IN0_5      = CTRL_TRG_START | CTRL_TRG_STOP | CTRL_TRG_RESTART;
    localparam integer CTRL_IN1_5      = CTRL_IN1_DATA_NOP | CTRL_IN1_DATA_STRB;
    localparam integer CTRL_OUT0_5     = CTRL_SYNC_OUT | CTRL_OUT12 | CTRL_BUS_OUT_EN_0 | CTRL_BUS_OUT_EN_1; 
    localparam integer CTRL_OUT1_5     = CTRL_LEDS;
    localparam integer CTRL_REP_5      = 1;    
    localparam integer CTRL_CYCLES_5   = 1;    
    localparam integer RUN_ABORT_0     = 5;
    // run 6: start as primary board with start/stop trigger but without restart. abort with software reset
    localparam integer CTRL_BITS_6     = CTRL_64 | CTRL_AS_PRIM;
    localparam integer CTRL_IN0_6      = CTRL_TRG_START | CTRL_TRG_STOP;
    localparam integer CTRL_IN1_6      = CTRL_IN1_DATA_NOP | CTRL_IN1_DATA_STRB;
    localparam integer CTRL_OUT0_6     = CTRL_SYNC_OUT | CTRL_OUT12 | CTRL_BUS_OUT_EN_0 | CTRL_BUS_OUT_EN_1; 
    localparam integer CTRL_OUT1_6     = CTRL_LEDS;
    localparam integer CTRL_REP_6      = 1;        
    localparam integer CTRL_CYCLES_6   = 1;    
    localparam integer HOLD_LINE_TRG_0 = 6; // hold line trigger
    localparam integer RUN_ABORT_1     = 6; 
    // run 7: start as primary board with start/stop/restart trigger and external clock, run until end
    localparam integer CTRL_BITS_7     = CTRL_64 | CTRL_AS_PRIM | CTRL_CLK_EXT_EN;
    localparam integer CTRL_IN0_7      = CTRL_TRG_START | CTRL_TRG_STOP | CTRL_TRG_RESTART;
    localparam integer CTRL_IN1_7      = CTRL_IN1_DATA_NOP | CTRL_IN1_DATA_STRB;
    localparam integer CTRL_OUT0_7     = CTRL_SYNC_OUT | CTRL_OUT12 | CTRL_BUS_OUT_EN_0 | CTRL_BUS_OUT_EN_1; 
    localparam integer CTRL_OUT1_7     = CTRL_LEDS;
    localparam integer CTRL_REP_7      = 1;
    localparam integer CTRL_CYCLES_7   = 1;    
    localparam integer HOLD_LINE_TRG_1 = 7; // hold line trigger            
    // run 8: start as secondary board with start trigger and run until end
    localparam integer CTRL_BITS_8     = CTRL_64 | CTRL_AS_SEC | CTRL_CLK_EXT_EN;
    localparam integer CTRL_IN0_8      = CTRL_TRG_START;
    localparam integer CTRL_IN1_8      = 0; // for testing do not enable strb
    localparam integer CTRL_OUT0_8     = CTRL_SYNC_OUT | CTRL_OUT12 | CTRL_BUS_OUT_EN_0 | CTRL_BUS_OUT_EN_1; 
    localparam integer CTRL_OUT1_8     = CTRL_LEDS;
    localparam integer CTRL_REP_8      = 1;    
    localparam integer CTRL_CYCLES_8   = 1;    
    // run 9: start as secondary board with start trigger, short clock loss should still run until end. expect clock loss in status but no error.
    localparam integer CTRL_BITS_9     = CTRL_64 | CTRL_AS_SEC | CTRL_CLK_EXT_EN;
    localparam integer CTRL_IN0_9      = CTRL_TRG_START;
    localparam integer CTRL_IN1_9      = CTRL_IN1_DATA_NOP | CTRL_IN1_DATA_STRB;
    localparam integer CTRL_OUT0_9     = CTRL_SYNC_OUT | CTRL_OUT12 | CTRL_BUS_OUT_EN_0 | CTRL_BUS_OUT_EN_1; 
    localparam integer CTRL_OUT1_9     = CTRL_LEDS;
    localparam integer CTRL_REP_9      = 1;    
    localparam integer CTRL_CYCLES_9   = 1;    
    localparam integer RUN_CLOCK_LOSS_SHORT = 9;
    // run 10: start as secondary board with start trigger and run until external clock lost. expect error.
    localparam integer CTRL_BITS_10    = CTRL_64 | CTRL_AS_SEC | CTRL_CLK_EXT_EN;
    localparam integer CTRL_IN0_10     = CTRL_TRG_START;
    localparam integer CTRL_IN1_10     = CTRL_IN1_DATA_NOP | CTRL_IN1_DATA_STRB;
    localparam integer CTRL_OUT0_10    = CTRL_SYNC_OUT | CTRL_OUT12 | CTRL_BUS_OUT_EN_0 | CTRL_BUS_OUT_EN_1;
    localparam integer CTRL_OUT1_10    = CTRL_LEDS;     
    localparam integer CTRL_REP_10     = 1;    
    localparam integer CTRL_CYCLES_10  = 1;    
    localparam integer RUN_CLOCK_LOSS = 10;
    // run 11: start as secondary board with start trigger and run until end despite of external clock lost.
    localparam integer CTRL_BITS_11    = CTRL_64 | CTRL_AS_SEC | CTRL_CLK_EXT_IGNORE;
    localparam integer CTRL_IN0_11     = CTRL_TRG_START;
    localparam integer CTRL_IN1_11     = CTRL_IN1_DATA_NOP | CTRL_IN1_DATA_STRB;
    localparam integer CTRL_OUT0_11    = CTRL_SYNC_OUT | CTRL_OUT12 | CTRL_BUS_OUT_EN_0 | CTRL_BUS_OUT_EN_1;
    localparam integer CTRL_OUT1_11    = CTRL_LEDS;     
    localparam integer CTRL_REP_11     = 1;
    localparam integer CTRL_CYCLES_11  = 1;    
    localparam integer RUN_CLOCK_LOSS_IGNORE = 11;
    // run 12: start as secondary board with start/stop trigger but without restart. abort with software reset.
    localparam integer CTRL_BITS_12    = CTRL_64 | CTRL_AS_SEC | CTRL_CLK_EXT_IGNORE;
    localparam integer CTRL_IN0_12     = CTRL_TRG_START | CTRL_TRG_STOP;
    localparam integer CTRL_IN1_12     = CTRL_IN1_DATA_NOP | CTRL_IN1_DATA_STRB;
    localparam integer CTRL_OUT0_12    = CTRL_SYNC_OUT | CTRL_OUT12 | CTRL_BUS_OUT_EN_0 | CTRL_BUS_OUT_EN_1;
    localparam integer CTRL_OUT1_12    = CTRL_LEDS;     
    localparam integer CTRL_REP_12     = 1;
    localparam integer CTRL_CYCLES_12  = 1; 
    localparam integer RUN_ABORT_2     = 12;
    // run 13: start as secondary board with start/stop/restart trigger and run until end.
    localparam integer CTRL_BITS_13    = CTRL_64 | CTRL_AS_SEC | CTRL_CLK_EXT_IGNORE;
    localparam integer CTRL_IN0_13     = CTRL_TRG_START | CTRL_TRG_STOP | CTRL_TRG_RESTART;
    localparam integer CTRL_IN1_13     = CTRL_IN1_DATA_NOP | CTRL_IN1_DATA_STRB;
    localparam integer CTRL_OUT0_13    = CTRL_SYNC_OUT | CTRL_OUT12 | CTRL_BUS_OUT_EN_0 | CTRL_BUS_OUT_EN_1;
    localparam integer CTRL_OUT1_13    = CTRL_LEDS;
    localparam integer CTRL_REP_13     = 25;
    localparam integer CTRL_CYCLES_13  = 1;
    localparam integer HOLD_LINE_TRG_2 = 13; // hold line trigger such that each loop we test different clk_bus_div value for stop trigger.
    
    // end check
    localparam integer END_CTRL_MASK   = (1<<CTRL_READY) | (1<<CTRL_RUN);
    localparam integer END_CTRL_SET    = (1<<CTRL_READY) | (1<<CTRL_RUN);
    localparam integer END_STATUS_MASK = (1<<STATUS_RESET)|(1<<STATUS_READY)|(1<<STATUS_RUN)|(1<<STATUS_END)|STATUS_ERR_ALL|(1<<STATUS_IRQ_ERROR)|(1<<STATUS_IRQ_END);
    localparam integer END_STATUS_SET  = (1<<STATUS_READY)|(1<<STATUS_END)|(1<<STATUS_IRQ_END);
            
    // masks for tests
    // data bits without special data bits
    localparam [GEN_DATA_WIDTH  -1:0] DATA_MASK = (BUS_ADDR_BITS == 8) ? 32'h00ffffff : 
                                                                         32'h007fffff;
    // bus output mask without 'last' bit
    localparam [GEN_SAMPLE_WIDTH-1:0] BUS_MASK  = 65'h0_ffff_ffff_ffff_ffff;

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
    reg line_trg_hold  = 1'b0; // hold line trigger low while this is high.
    reg line_trg_reset = 1'b0; // hold and reset line trigger.
    integer line_trg_loop = 0;
    integer line_trg_count = PERIOD_LINE;
    localparam integer LINE_TRG_LOW  = (LINE_TRG_INVERTED == 0) ? 1'b0: 1'b1;
    localparam integer LINE_TRG_HIGH = (LINE_TRG_INVERTED == 0) ? 1'b1: 1'b0;
    initial begin
        line_trg = LINE_TRG_LOW;
        forever begin
            #(PERIOD_BUS/4);
            if (line_trg_reset == 1'b1) begin
                line_trg       = LINE_TRG_LOW;
                line_trg_loop  = 0;
                line_trg_count = PERIOD_LINE;
            end
            else if (line_trg_hold == 1'b1) begin
                line_trg = LINE_TRG_LOW;
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
    wire [AXI_ADDR_WIDTH-1 : 0]     AXI_awaddr;
    wire [2 : 0]                    AXI_awprot;
    wire                            AXI_awvalid;
    wire                            AXI_awready;
    wire [AXI_DATA_WIDTH-1 : 0]     AXI_wdata;
    wire [(AXI_DATA_WIDTH/8)-1 : 0] AXI_wstrb;
    wire                            AXI_wvalid;
    wire                            AXI_wready;
    wire [1 : 0]                    AXI_bresp;
    wire                            AXI_bvalid;
    wire                            AXI_bready;
    wire [AXI_ADDR_WIDTH-1 : 0]     AXI_araddr;
    wire [2 : 0]                    AXI_arprot;
    wire                            AXI_arvalid;
    wire                            AXI_arready;
    wire [AXI_DATA_WIDTH-1 : 0]     AXI_rdata;
    wire [1 : 0]                    AXI_rresp;
    wire                            AXI_rvalid;
    wire                            AXI_rready;
    axi_lite_master # (
            //.C_TRANSACTIONS_NUM(4)
            .DATA_WIDTH(AXI_DATA_WIDTH),
            .ADDR_WIDTH(AXI_ADDR_WIDTH)
        ) AXI_master (
            .M_AXI_ACLK(clk_AXI),
            .M_AXI_ARESETN(reset_AXI_n),
            
            // write data to specified register address
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
            .M_AXI_AWADDR(AXI_awaddr),
            .M_AXI_AWPROT(AXI_awprot),
            .M_AXI_AWVALID(AXI_awvalid),
            .M_AXI_AWREADY(AXI_awready),
            .M_AXI_WDATA(AXI_wdata),
            .M_AXI_WSTRB(AXI_wstrb),
            .M_AXI_WVALID(AXI_wvalid),
            .M_AXI_WREADY(AXI_wready),
            .M_AXI_BRESP(AXI_bresp),
            .M_AXI_BVALID(AXI_bvalid),
            .M_AXI_BREADY(AXI_bready),
            .M_AXI_ARADDR(AXI_araddr),
            .M_AXI_ARPROT(AXI_arprot),
            .M_AXI_ARVALID(AXI_arvalid),
            .M_AXI_ARREADY(AXI_arready),
            .M_AXI_RDATA(AXI_rdata),
            .M_AXI_RRESP(AXI_rresp),
            .M_AXI_RVALID(AXI_rvalid),
            .M_AXI_RREADY(AXI_rready)
        );

    // define time steps in units of 1/bus_rate. will be repeated for more data.
    // seq_time[0] is relative to last sample
    // for steps <= 0 expect timing error.
    localparam integer SEQ_TIME = 17;
    reg [GEN_TIME_WIDTH-1:0] seq_time [0 : SEQ_TIME-1];
    initial begin
        seq_time[ 0] = 2;   // first absolute time is GEN_TIME_START, this is after restart
        seq_time[ 1] = 1;
        seq_time[ 2] = 5;
        seq_time[ 3] = 1;
        seq_time[ 4] = 3;
        seq_time[ 5] = 1;
        seq_time[ 6] = 1;
        seq_time[ 7] = 1;
        seq_time[ 8] = 2;
        seq_time[ 9] = 1;
        seq_time[10] = 1;
        seq_time[11] = 6;
        seq_time[12] = 4;
        seq_time[13] = 1;
        seq_time[14] = 1;
        seq_time[15] = 1;
        seq_time[16] = 7;
    end 
        
    // sequence of NOP, STROBE, STOP bits. will be repeated for more data.
    localparam integer SEQ_NOP  = 7;
    localparam integer SEQ_STRB = 16;
    localparam integer SEQ_STOP = STOP_TRG_DATA_SAMPLE;
    reg [SEQ_NOP -1 : 0] seq_nop  = 7'b1000000;
    reg [SEQ_STRB-1 : 0] seq_strb = 16'b1010110101001010;
    //reg [SEQ_NOP -1 : 0] seq_nop  = 7'b0000000;
    //reg [SEQ_STRB-1 : 0] seq_strb = 18'b101010101010101010;
    reg [SEQ_STOP-1 : 0] seq_stop = {1'b1,{(STOP_TRG_DATA_SAMPLE-1){1'b0}}};

    // generate TX data memory
    // this includes 32bit time + 32bit data (16bit data + address + special bits) + last 
    reg [GEN_SAMPLE_WIDTH-1 : 0] gen_data [0 : GEN_NUM_SAMPLES - 1];
    reg [GEN_TIME_WIDTH  -1 : 0] gen_t;
    reg [GEN_DATA_WIDTH  -1 : 0] gen_d;
    reg [GEN_DATA_WIDTH  -1 : 0] gen_a;
    reg                        gen_l;
    integer num_skip_nop;       // number of skipped samples by nop bit
    integer num_skip_strb;      // number of skipped samples by strobe bit
    integer gen_last_good_nop;  // index of last sample to be output regarding only NOP bit
    integer gen_last_good_strb; // index or last sample to be output regarding NOP and STRB bits
    integer i;
    initial begin
        num_skip_nop = 0;
        num_skip_strb = 0;
        gen_t = GEN_TIME_START;
        gen_d = GEN_DATA_START;
        gen_a = (seq_nop[0] << abs(BIT_NOP)) | (seq_strb[0] << abs(BIT_STRB));
        gen_last_good_nop  = (seq_nop[0] == 1'b0) ? 0 : -1;
        gen_last_good_strb = (seq_nop[0] == 1'b0) ? 0 : -1;
        gen_l = 1'b0;
        gen_data[0] = {gen_l, gen_a | gen_d, gen_t};
        for (i = 1; i < GEN_NUM_SAMPLES; i = i + 1) begin
            if (seq_nop[i % SEQ_NOP]) begin
                num_skip_nop = num_skip_nop + 1;
            end
            else begin
                gen_last_good_nop = i;
                if ( ((BIT_STRB == 23)||(BIT_STRB==24)) &&
                      (seq_strb[i % SEQ_STRB] == seq_strb[(i-1) % SEQ_STRB]) ) begin
                    num_skip_strb = num_skip_strb + 1;
                end
                else begin
                    gen_last_good_strb = i;
                end
            end
            gen_t = gen_t + seq_time[i % SEQ_TIME];
            gen_d = gen_d + GEN_DATA_STEP; 
            gen_a = (seq_nop [i % SEQ_NOP] << abs(BIT_NOP)) | (seq_strb[i % SEQ_STRB] << abs(BIT_STRB)) | (seq_stop[i % SEQ_STOP] << abs(BIT_STOP));
            gen_l = (i == GEN_NUM_SAMPLES-1) ? 1'b1 : 1'b0;
            gen_data[i] = {gen_l, gen_a | gen_d, gen_t};
        end
    end
    
    // input data stream
    reg gen_ctrl;               // output enable. controlled by simulation
    reg gen_ctrl_reset;         // reset generator. controlled by simulation
    reg gen_en = 1'b1;
    reg [31:0] gen_count  = 0;  // actual samples
    reg [31:0] gen_cycles = 0;  // actual cycles
    reg [31:0] run_cycles;      // number of cycles. controlled by simulation.
    wire gen_ready;
    wire gen_valid = gen_en & gen_ctrl;
    reg [(STREAM_DATA_WIDTH/8)-1:0] gen_keep = {(STREAM_DATA_WIDTH/8){1'b1}};
    always @ ( posedge clk_stream ) begin
        if ( ( reset_stream_n == 1'b0) || (gen_ctrl_reset == 1'b1) ) begin
            gen_count  <= 0;
            gen_cycles <= 0;
            gen_en     <= 1'b1;
        end
        else if ( gen_ready & gen_valid ) begin
            gen_count  <= (gen_count == (GEN_NUM_SAMPLES-1)) ? 0 : gen_count + 1;
            gen_cycles <= (gen_count == (GEN_NUM_SAMPLES-1)) ? gen_cycles + 1 : gen_cycles;
            gen_en     <= (gen_count == (GEN_NUM_SAMPLES-1)) && (gen_cycles == (run_cycles-1)) ? 1'b0 : 1'b1;
        end
        else begin
            gen_count  <= gen_count;
            gen_cycles <= gen_cycles;
            gen_en     <= gen_en;
        end
    end
    
    // expand input data to 12 bytes/sample if needed
    // TODO: implement the Yb data with dynamic switching
    wire [STREAM_DATA_WIDTH - 1 : 0] gen_data_full;
    wire gen_last = gen_data[gen_count][GEN_SAMPLE_WIDTH-1];
    if (STREAM_DATA_WIDTH == 64) begin
        assign gen_data_full = gen_data[gen_count][STREAM_DATA_WIDTH-1:0];
    end
    else begin
        assign gen_data_full = {~gen_data[gen_count][GEN_SAMPLE_WIDTH-1 -: GEN_DATA_WIDTH], gen_data[gen_count][STREAM_DATA_WIDTH-1:0]};
    end
    
    /* combine samples from BITS_PER_SAMPLE to STREAM_DATA_WIDTH
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
   */
   
   // TODO: expand data for BIT_PER_SAMPLE = 96
    wire [STREAM_DATA_WIDTH-1:0] TX_data = gen_data_full;
    wire TX_last = gen_last;
    wire [(STREAM_DATA_WIDTH/8)-1:0] TX_keep = gen_keep;
    wire TX_valid = gen_valid;
    wire TX_ready;
    assign gen_ready = TX_ready;
   
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
    reg  [NUM_IN -1:0] ext_in;
    wire [NUM_OUT-1:0] ext_out;

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
        .VERSION(VERSION),
        .INFO(INFO),

        .STREAM_DATA_WIDTH(STREAM_DATA_WIDTH),

        .AXI_DATA_WIDTH(AXI_DATA_WIDTH),
        .AXI_ADDR_WIDTH(AXI_ADDR_WIDTH),

        .NUM_IN(NUM_IN),
        .NUM_OUT(NUM_OUT),

        .BUS_ADDR_BITS(BUS_ADDR_BITS),
        .BUS_DATA_BITS(BUS_DATA_BITS),
        .NUM_STRB(NUM_STRB),
        .NUM_BUS_EN(NUM_BUS_EN),
                        
        .BUS_ADDR_1_USE(BUS_ADDR_1_USE),
        .BUS_RESET(BUS_RESET),

        .NUM_BUTTONS(NUM_BUTTONS),
        .NUM_LED_RED(NUM_LED_RED),
        .NUM_LED_GREEN(NUM_LED_GREEN),
        .NUM_LED_BLUE(NUM_LED_BLUE),
        .INV_RED(INV_RED),
        .INV_GREEN(INV_GREEN),
        .INV_BLUE(INV_BLUE),

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
        .SYNC_DELAY_BITS(SYNC_DELAY_BITS),

        .AUTO_SYNC_PULSE_LENGTH(AUTO_SYNC_PULSE_LENGTH),
        .AUTO_SYNC_PULSE_WAIT(AUTO_SYNC_PULSE_WAIT),
        .AUTO_SYNC_MAX_PULSES(AUTO_SYNC_MAX_PULSES),
        .AUTO_SYNC_TIME_BITS(AUTO_SYNC_TIME_BITS),
        .AUTO_SYNC_PHASE_BITS(AUTO_SYNC_PHASE_BITS),
                
        .SYNC(SYNC),
        .SYNC_EXT(SYNC_EXT),
                
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
        
        // external I/O
        .ext_in(ext_in),
        .ext_out(ext_out),
        
        // dynamic phase shift of external clock input and detector clock 
        .ps_done_ext(ps_done_ext),
        .ps_en_ext(ps_en_ext),
        .ps_inc_ext(ps_inc_ext),
        .ps_done_det(ps_done_det),
        .ps_en_det(ps_en_det),
        .ps_inc_det(ps_inc_det),
        
        // AXI Lite Slave Bus Interface S00_AXI
        .AXI_aclk(clk_AXI),
        .AXI_aresetn(reset_AXI_n),
        .AXI_awaddr(AXI_awaddr),
        .AXI_awprot(AXI_awprot),
        .AXI_awvalid(AXI_awvalid),
        .AXI_awready(AXI_awready),
        .AXI_wdata(AXI_wdata),
        .AXI_wstrb(AXI_wstrb),
        .AXI_wvalid(AXI_wvalid),
        .AXI_wready(AXI_wready),
        .AXI_bresp(AXI_bresp),
        .AXI_bvalid(AXI_bvalid),
        .AXI_bready(AXI_bready),
        .AXI_araddr(AXI_araddr),
        .AXI_arprot(AXI_arprot),
        .AXI_arvalid(AXI_arvalid),
        .AXI_arready(AXI_arready),
        .AXI_rdata(AXI_rdata),
        .AXI_rresp(AXI_rresp),
        .AXI_rvalid(AXI_rvalid),
        .AXI_rready(AXI_rready),
        
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
    
    wire [STREAM_DATA_WIDTH - 1 : 0] out_data;
    wire [(STREAM_DATA_WIDTH/8) - 1 : 0] out_keep;
    wire out_last;
    wire out_valid;
    reg out_ready = 1'b0;

    assign out_data  = RX_data;
    assign out_last  = RX_last;
    assign out_valid = RX_valid;
    assign out_keep  = RX_keep;
    assign RX_ready  = out_ready;

    /* split samples from STREAM_DATA_WIDTH to BITS_PER_SAMPLE for comparison with gen_datatime
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
    */
    
    reg out_error_keep = 1'b0;
    always @ ( posedge clk_stream ) begin
        if ( reset_stream_n == 1'b0 ) begin
            out_error_keep <= 1'b0;
        end
        else begin
            out_error_keep <= (out_valid) ? ((RX_keep != {(STREAM_DATA_WIDTH/8){1'b1}}) ? 1'b1 : 1'b0) : out_error_keep;
        end
    end

    // bus out counter / timer to compare actual bus output time with programmed time
    // TODO: this code tends to make troubles because it is sensitive to small offsets in time!
    //       when you change timing you might experience fake bus_out_error. 
    //       ensure that clk_div_count == bus_act_time_cnt
    //       adjust initial value of bus_act_time_cnt accordingly.
    reg [clogb2(CLK_DIV):0] bus_act_time_cnt = -1; // counter @ clk_bus to generate CLK_DIV
    reg [GEN_TIME_WIDTH-1:0] bus_act_time    = 0; // actual bus time = bus_out_time_cnt / CLK_DIV
    reg [AXI_DATA_WIDTH-1:0] bus_out_count   = 0;
    reg [AXI_DATA_WIDTH-1:0] bus_out_cycles  = 0;
    wire bus_out_last_cycle  = (bus_out_cycles >= (run_cycles-1));
    wire bus_out_tick  = ( bus_act_time_cnt == CLK_DIV );
    wire bus_out_reset = ( bus_act_time == gen_data[GEN_NUM_SAMPLES-1][TIME_BITS-1:0]);
    always @ ( posedge clk_bus ) begin
        if ( reset_AXI_sw_n == 1'b0 ) begin
            bus_act_time     <= GEN_TIME_START - 1;
        end
        else if ( DUT.timing.state_run ) begin
            bus_act_time     <= bus_out_tick & (~DUT.timing.state_wait) ? 
                                    ( bus_out_reset ? GEN_TIME_START :
                                      bus_act_time + 1 ) : bus_act_time;
        end
        // counter is running always. must be in sync with timing module.
        bus_act_time_cnt <= bus_out_tick ? 1 : bus_act_time_cnt + 1;
    end

    // monitor bus output @ clk_bus
    // we check output at correct time and data and address is same as generated
    reg bus_strb_0_ff;
    reg bus_strb_0_toggle = 1'b0; // toggles for each bus_strb_0 change. bus_strb_1 must be in same state
    reg [STREAM_DATA_WIDTH-1:0] bus_out_datatime;
    reg [AXI_DATA_WIDTH-1:0] bus_out_skipped;
    reg bus_out_error;
    wire [GEN_SAMPLE_WIDTH -1 : 0] gen_data_act = ( bus_out_count >= GEN_NUM_SAMPLES ) ? 0 : gen_data[bus_out_count];
    reg bus_gen_strb = 1'b0;
    wire skip_NOP;
    reg [31:0] conf_in0 = 0;
    reg [31:0] conf_in1 = 0;
    wire nop_en  = ( conf_in1[(CTRL_IN1_DST_DATA_NOP +1)*CTRL_IN_SRC_BITS -1 -: CTRL_IN_SRC_BITS] != CTRL_IN_SRC_NONE );
    wire strb_en = ( conf_in1[(CTRL_IN1_DST_DATA_STRB+1)*CTRL_IN_SRC_BITS -1 -: CTRL_IN_SRC_BITS] != CTRL_IN_SRC_NONE );
    wire skip_NOP_w  = nop_en  &   gen_data_act[abs(BIT_NOP)+GEN_TIME_WIDTH];
    wire skip_STRB_w = strb_en & ( gen_data_act[abs(BIT_STRB)+GEN_TIME_WIDTH] == bus_gen_strb );
    assign skip_NOP = ( bus_out_count < GEN_NUM_SAMPLES ) & ( skip_NOP_w | skip_STRB_w );
    
    always @ ( posedge clk_bus or negedge reset_AXI_sw_n ) begin
        if ( reset_AXI_sw_n == 1'b0 ) begin
            bus_strb_0_ff           <= 1'b0;
            bus_strb_0_toggle       <= bus_strb_0_toggle;
            bus_out_datatime        <= 0;
            bus_out_count           <= 0;
            bus_out_cycles          <= 0;
            bus_out_skipped         <= 0;
            bus_out_error           <= 1'b0;
            bus_gen_strb            <= ~seq_strb[0];
        end
        else if ( bus_out_reset & bus_out_tick ) begin
            if (~bus_out_last_cycle) begin
                bus_out_count       <= 0;
                bus_out_datatime    <= 0;
            end
            bus_out_cycles          <= (bus_out_cycles != run_cycles) ? bus_out_cycles + 1 : bus_out_cycles;
            bus_strb_0_ff           <= 1'b0;
            bus_strb_0_toggle       <= bus_strb_0_toggle;
            bus_out_skipped         <= bus_out_skipped; // do not reset this
            bus_out_error           <= 1'b0;
            bus_gen_strb            <= ~seq_strb[0];
        end
        else if ( bus_en[0] == BUS_0_ENABLED ) begin
            if ( {bus_strb_0_ff,bus_strb[0]} == 2'b01 ) begin
                bus_strb_0_ff       <= bus_strb[0];
                bus_strb_0_toggle   <= ~bus_strb_0_toggle;
                bus_out_datatime    <= {bus_addr_1,bus_addr_0,bus_data,bus_act_time};
                bus_out_count       <= bus_out_count + 1;
                bus_out_cycles      <= bus_out_cycles;
                bus_out_skipped     <= bus_out_skipped; 
                bus_gen_strb        <= gen_data_act[abs(BIT_STRB)+GEN_TIME_WIDTH];
                if ( (gen_data_act & BUS_MASK) != {bus_addr_1,bus_addr_0,bus_data,bus_act_time} )
                    bus_out_error   <= 1'b1;
                else 
                    bus_out_error   <= bus_out_error;
            end
            else if ( skip_NOP & bus_out_tick ) begin // skip data with NOP bit set
                bus_out_count       <= bus_out_count + 1;
                bus_out_skipped     <= bus_out_skipped + 1;
                bus_gen_strb        <= gen_data_act[abs(BIT_STRB)+GEN_TIME_WIDTH];
            end
            bus_strb_0_ff <= bus_strb;
        end
    end
    
    // monitor RX data output @ clk_stream
    // here the time does not matter, we only check the correct data
    reg  [AXI_DATA_WIDTH-1:0] out_count = 0;
    reg  [AXI_DATA_WIDTH-1:0] out_cycles = 0;
    reg  [GEN_SAMPLE_WIDTH -1 : 0] out_datatime;
    wire [GEN_SAMPLE_WIDTH -1 : 0] out_gen_data = gen_data[out_count];
    reg out_error = 1'b0;
    always @ ( posedge clk_stream or negedge reset_AXI_sw_n ) begin
        if ( reset_AXI_sw_n == 1'b0 ) begin
            out_datatime <= 0;
            out_count    <= 0;
            out_cycles   <= 0;
            out_error    <= 1'b0;
        end
        else if ( out_valid & out_ready ) begin
            out_datatime <= {out_last,out_data[STREAM_DATA_WIDTH-1:0]};
            out_count    <= out_last && (out_cycles != (run_cycles-1)) ? 0 : out_count + 1;
            out_cycles   <= out_last ? out_cycles + 1 : out_cycles;
            out_error    <= ( out_gen_data != {out_last,out_data[STREAM_DATA_WIDTH-1:0]} ) ? 1'b1 : out_error;
        end
        else begin
            out_datatime <= out_datatime;
            out_count    <= out_count;
            out_cycles   <= out_cycles;
            out_error    <= out_error;
        end
    end    

    // connect line trigger with external inputs as configured
    // this ensures that only the selected inputs are used and not by chance a different one. 
    task set_ext_in;
    begin
        ext_in[0] = ( conf_in0[(CTRL_IN0_DST_TRG_START  +1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN0          ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_START  +1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN0_INV      ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_START  +1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN0_EDGE_POS ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_START  +1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN0_EDGE_NEG ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_STOP   +1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN0          ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_STOP   +1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN0_INV      ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_STOP   +1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN0_EDGE_POS ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_STOP   +1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN0_EDGE_NEG ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_RESTART+1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN0          ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_RESTART+1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN0_INV      ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_RESTART+1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN0_EDGE_POS ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_RESTART+1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN0_EDGE_NEG ) ? line_trg : 1'b0;
        ext_in[1] = ( conf_in0[(CTRL_IN0_DST_TRG_START  +1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN1          ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_START  +1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN1_INV      ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_START  +1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN1_EDGE_POS ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_START  +1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN1_EDGE_NEG ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_STOP   +1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN1          ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_STOP   +1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN1_INV      ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_STOP   +1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN1_EDGE_POS ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_STOP   +1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN1_EDGE_NEG ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_RESTART+1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN1          ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_RESTART+1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN1_INV      ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_RESTART+1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN1_EDGE_POS ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_RESTART+1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN1_EDGE_NEG ) ? line_trg : 1'b0;
        ext_in[2] = ( conf_in0[(CTRL_IN0_DST_TRG_START  +1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN2          ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_START  +1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN2_INV      ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_START  +1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN2_EDGE_POS ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_START  +1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN2_EDGE_NEG ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_STOP   +1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN2          ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_STOP   +1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN2_INV      ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_STOP   +1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN2_EDGE_POS ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_STOP   +1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN2_EDGE_NEG ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_RESTART+1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN2          ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_RESTART+1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN2_INV      ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_RESTART+1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN2_EDGE_POS ) ? line_trg :
                    ( conf_in0[(CTRL_IN0_DST_TRG_RESTART+1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] == CTRL_IN_SRC_IN2_EDGE_NEG ) ? line_trg : 1'b0;
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
    integer expect_error = 0;
    integer bus_out_error_ignore = 0;
    reg error_ignore = 1'b0;
    task check_DUT;
    begin
        if ( DUT.error_axi ) begin
            if (~error_ignore) begin
                $display("%d: DUT is in error state!", $time);
                $display("%d: DUT ctrl 0x%x status 0x%x", $time, DUT.control_axi, DUT.status_axi);
                if ((DUT.status_axi & STATUS_ERR_ALL) == expect_error) begin
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
            if ( DUT.timing.timeout_next_cycle && (DUT.timing.timer != DUT.timing.next_time) ) begin
                $display("%d: timeout does not agree with timer == next_time!", $time);
                $display(DUT.timing.timer);
                $display(DUT.timing.next_time);
                $finish;
            end 
            if ( bus_out_error && (!bus_out_error_ignore)) begin
                $display("%d: error bus data! (only displayed one time)", $time);
                $display("this error might be caused when bus_act_time_cnt %d != clk_div_count %d", bus_act_time_cnt, DUT.timing.clk_div_count);
                $display("in this case add to initial value of bus_act_time_cnt difference %d", (bus_act_time_cnt - DUT.timing.clk_div_count)%CLK_DIV);
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
    integer conf = 0;
    task wait_end;
    begin
        while ( DUT.status_end_axi != 1'b1 ) begin 
          @(posedge clk_AXI);
          
          if ( DUT.irq_FPGA ) begin //&& ((DUT.status & STATUS_IRQ_ERR) == 0) ) begin
              $display("%d RESET FPGA_IRQ ...", $time);
              // AXI Lite interface: reset IRQ_EN bit
              repeat(5) @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b1;
              AXI_wr_addr = REG_CTRL*REG_NUM_BYTES;
              AXI_wr_data = ((1<<CTRL_RUN) | conf) & (~(1<<CTRL_IRQ_EN));
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
              AXI_wr_addr = REG_CTRL*REG_NUM_BYTES;
              AXI_wr_data = (1<<CTRL_RUN) | conf | (1<<CTRL_IRQ_EN);
              @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b0;
              @(posedge clk_AXI);
          end
        end
    end
    endtask
    
    task software_reset;
    begin
      // AXI Lite interface: activate software reset
      repeat(25) @(posedge clk_AXI);
      #1
      AXI_wr_valid = 1'b1;
      AXI_wr_addr = REG_CTRL*REG_NUM_BYTES;
      AXI_wr_data = (1<<CTRL_RESET);
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
      while ( DUT.status_axi & (1<<STATUS_RESET) != (1<<STATUS_RESET) ) begin 
        @(posedge clk_AXI);
      end
      $display("%d *** software RESET active! *** ", $time);
    
      // wait until reset is done
      while ( ( (DUT.status_axi & (~(1<<STATUS_CLK_EXT_LOCKED))) != STATUS_RST_END ) || 
              ( DUT.control_axi != 0 ) || 
              ( reset_AXI_sw_n != 1'b1 ) ||
              ( DUT.reset_AXI_active_n != 1'b1 ) ) begin 
        @(posedge clk_AXI);
      end
      $display("%d *** software RESET done! *** ", $time);
    end
    endtask
    
    // check final state
    integer run = 0;
    integer last_good = 0;
    task check_end;
    begin
        if ( (DUT.control_axi & END_CTRL_MASK) != END_CTRL_SET ) begin
            $display("%d: check final state!", $time);
            $finish;
        end
        if ( (DUT.status_axi & (~expect_error) & END_STATUS_MASK) != END_STATUS_SET ) begin
            $display("%d: check final state!", $time);
            $display("status 0x%x & 0x%x = 0x%x != 0x%x (expect error 0x%x)", DUT.status_axi, END_STATUS_MASK, DUT.status_axi & END_STATUS_MASK, END_STATUS_SET, expect_error);
            $finish;
        end
        if ( DUT.error_axi ) begin
            if ((DUT.status_axi & STATUS_ERR_ALL) == expect_error) begin
                $display("%d: final state 0x%x with expected error 0x%x! (ok)", $time, DUT.status_axi, expect_error);
            end
            else begin
                $display("%d: check final state!", $time);
                $finish;
            end
        end
        if ( DUT.num_samples_axi != GEN_NUM_SAMPLES ) begin
            $display("%d: check final state!", $time);
            $finish;
        end
        if ( DUT.board_samples_axi != GEN_NUM_SAMPLES ) begin
            $display("%d: check final state!", $time);
            $display("board samples %d != %d", DUT.board_samples_axi, GEN_NUM_SAMPLES);
            $finish;
        end
        if ( DUT.board_time_axi != (gen_data[GEN_NUM_SAMPLES-1][GEN_TIME_WIDTH-1:0] + 1) ) begin
            $display("%d: check final state!", $time);
            $display("%d != %d + 1", DUT.board_time_axi, gen_data[GEN_NUM_SAMPLES-1][GEN_TIME_WIDTH-1:0]);
            $finish;
        end
        if ( bus_out_datatime != (gen_data[last_good] & BUS_MASK)) begin
            $display("%d: check final state!", $time);
            $display("last bus output 0x%x", bus_out_datatime);
            $display("last expected   0x%x", gen_data[last_good]& BUS_MASK);
            $finish;
        end
        if ( bus_out_count != GEN_NUM_SAMPLES ) begin
            $display("%d: check final state!", $time);
            $finish;
        end         
        if ( bus_out_cycles != run_cycles ) begin
            $display("%d: check final state!", $time);
            $finish;
        end         
        if ( strb_en ) begin
            if ( nop_en ) begin
                if (bus_out_skipped != (num_skip_nop+num_skip_strb)*run_cycles) begin
                    $display("%d: check final state!", $time);
                    $finish;
                end
            end
            else begin
                if (bus_out_skipped != (num_skip_strb)*run_cycles) begin
                    $display("%d: check final state!", $time);
                    $finish;
                end
            end
        end
        else if ( nop_en ) begin
            if ( bus_out_skipped != num_skip_nop*run_cycles ) begin
               $display("%d: check final state!", $time);
               $finish;
            end
        end
        else if ( bus_out_skipped != 0 )begin
            $display("%d: check final state!", $time);
            $finish;
        end
        if ( out_count != GEN_NUM_SAMPLES ) begin
            $display("%d: check final state!", $time);
            $finish;
        end
        if ( out_cycles != run_cycles ) begin
            $display("%d: check final state!", $time);
            $finish;
        end
        if ( out_datatime != gen_data[GEN_NUM_SAMPLES-1]) begin
            $display("%d: check final state!", $time);
            $finish;
        end
        if (out_datatime[STREAM_DATA_WIDTH] != 1'b1) begin
            $display("%d: check final state!", $time);
            $finish;
        end
        if ( BUS_RESET != 0 ) begin
            if (( bus_data != 0 ) || ( bus_addr_0 != 0 ) || ( bus_addr_1 != 0 )) begin
                $display("%d: check final state!", $time);
                $finish;
            end
        end 
        else begin
            if (( bus_data   != bus_out_datatime[TIME_BITS + BUS_DATA_BITS                   -1 -: BUS_DATA_BITS] ) || 
                ( bus_addr_0 != bus_out_datatime[TIME_BITS + BUS_DATA_BITS + 1*BUS_ADDR_BITS -1 -: BUS_ADDR_BITS] ) || 
                ( bus_addr_1 != bus_out_datatime[TIME_BITS + BUS_DATA_BITS + 2*BUS_ADDR_BITS -1 -: BUS_ADDR_BITS] )) begin
                $display("0x%x vs 0x%x", bus_data  , bus_out_datatime[TIME_BITS + BUS_DATA_BITS                   -1 -: BUS_DATA_BITS]);
                $display("0x%x vs 0x%x", bus_addr_0, bus_out_datatime[TIME_BITS + BUS_DATA_BITS + 1*BUS_ADDR_BITS -1 -: BUS_ADDR_BITS]);
                $display("0x%x vs 0x%x", bus_addr_1, bus_out_datatime[TIME_BITS + BUS_DATA_BITS + 2*BUS_ADDR_BITS -1 -: BUS_ADDR_BITS]);
                $display("%d: check final state!", $time);
                $finish;
            end
        end
        if ( bus_strb[0] != 1'b0 ) begin  // strb_0 should not be toggling!
            $display("%d: check final state!", $time);
            $finish;
        end         
        if ( bus_strb[1] != bus_strb_0_toggle ) begin // strb_1 should be toggling! 
            $display("%d: check final state!", $time);
            $finish;
        end   
        if ( ( bus_en[0] != BUS_0_ENABLED ) || ( bus_en[1] != BUS_1_ENABLED ) ) begin // TODO: might give an error when one changes output configuration of bus_en bits.
            $display("%d: check final state!", $time);
            $finish;
        end        

        $display("%d: final state 0x%x control 0x%x! (ok)", $time, DUT.status_axi, DUT.control_axi);
        $display("%d *** final state ok! ***", $time);
    end
    endtask
       
    // simulation
    integer conf_out0     = 0;
    integer conf_out1     = 0;
    integer run_rep       = 1;
    integer run_rep_count = 0;
    integer tmp = 0;
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
      line_trg_reset = 1'b0;
      
      // init AXI Lite interface
      AXI_wr_data = 0;
      AXI_wr_addr = REG_CTRL*REG_NUM_BYTES;
      AXI_wr_valid = 1'b0;
      AXI_rd_addr = REG_STATUS*REG_NUM_BYTES;
      AXI_rd_ready = 1'b0;

      // wait for hardware reset to finish
      @(posedge reset_AXI_n);
      
      // wait for clock mux reset to finish
      while ( reset_AXI_sw_n == 1'b0 ) begin 
        @(posedge clk_AXI);
      end
      
      // wait for board reset to finish
      while ( DUT.reset_AXI_active_n == 1'b0 ) begin 
        @(posedge clk_AXI);
      end

      // force out test
      repeat(10) @(posedge clk_bus);
      #1
      AXI_wr_valid = 1'b1;
      AXI_wr_addr = REG_FORCE_OUT*REG_NUM_BYTES;
      AXI_wr_data = $urandom();
      @(posedge clk_AXI);
      #1
      AXI_wr_valid = 1'b0;
      // wait until data written
      while ( AXI_wr_ready == 1'b0 ) begin 
        @(posedge clk_AXI);
      end
      repeat(10) @(posedge clk_bus);
      if ( DUT.timing.force_out != AXI_wr_data ) begin
        $display("%d FORCE OUT register is not written!?", $time);
        $finish;
      end
      else begin
        if ( ( DUT.bus_data    != AXI_wr_data[BUS_DATA_BITS-1:0] ) ||
             ( DUT.bus_addr_0  != AXI_wr_data[BUS_DATA_BITS+BUS_ADDR_BITS-1   -: BUS_ADDR_BITS] ) ||
             ( DUT.bus_addr_1  != AXI_wr_data[BUS_DATA_BITS+BUS_ADDR_BITS*2-1 -: BUS_ADDR_BITS] ) // assumes ADDR_1_USE = DATA_HIGH
             ) begin
          $display("0x%x vs. 0x%x", DUT.bus_data   , AXI_wr_data[BUS_DATA_BITS-1:0]);
          $display("0x%x vs. 0x%x", DUT.bus_addr_0 , AXI_wr_data[BUS_DATA_BITS+BUS_ADDR_BITS-1   -: BUS_ADDR_BITS]);
          $display("0x%x vs. 0x%x", DUT.bus_addr_1 , AXI_wr_data[BUS_DATA_BITS+BUS_ADDR_BITS*2-1 -: BUS_ADDR_BITS]);
          $display("%d FORCE OUT bus output unexpected!?", $time);
          $finish;
        end
        else begin
          $display("%d *** FORCE OUT 0x%x OK! *** ", $time, AXI_wr_data);
          $finish;
        end

        // perform software reset
        software_reset;

      end

      for (run=0; run < RUNS; run = run + 1) begin
          $display("%d run %d / %d", $time, run, RUNS);
          
          for (run_rep_count=0; run_rep_count<run_rep; run_rep_count=run_rep_count+1) begin
              $display("%d loop %d / %d", $time, run_rep_count, run_rep);
    
              // control bits for current run        
              if ( run == 0 ) begin
                conf        = CTRL_BITS_0;
                conf_in0    = CTRL_IN0_0;
                conf_in1    = CTRL_IN1_0;
                conf_out0   = CTRL_OUT0_0;
                conf_out1   = CTRL_OUT1_0;
                run_rep     = CTRL_REP_0;
                run_cycles  = CTRL_CYCLES_0;
              end
              else if ( run == 1 ) begin
                conf        = CTRL_BITS_1;
                conf_in0    = CTRL_IN0_1;
                conf_in1    = CTRL_IN1_1;
                conf_out0   = CTRL_OUT0_1;
                conf_out1   = CTRL_OUT1_1;
                run_rep     = CTRL_REP_1;
                run_cycles  = CTRL_CYCLES_1;
              end
              else if ( run == 2 ) begin
                conf        = CTRL_BITS_2;
                conf_in0    = CTRL_IN0_2;
                conf_in1    = CTRL_IN1_2;  
                conf_out0   = CTRL_OUT0_2;
                conf_out1   = CTRL_OUT1_2;
                run_rep     = CTRL_REP_2;
                run_cycles  = CTRL_CYCLES_2;
              end          
              else if ( run == 3 ) begin
                conf        = CTRL_BITS_3;
                conf_in0    = CTRL_IN0_3;
                conf_in1    = CTRL_IN1_3;
                conf_out0   = CTRL_OUT0_3;
                conf_out1   = CTRL_OUT1_3;
                run_rep     = CTRL_REP_3;
                run_cycles  = CTRL_CYCLES_3;
              end
              else if ( run == 4 ) begin
                conf        = CTRL_BITS_4;
                conf_in0    = CTRL_IN0_4;
                conf_in1    = CTRL_IN1_4;
                conf_out0   = CTRL_OUT0_4;
                conf_out1   = CTRL_OUT1_4;
                run_rep     = CTRL_REP_4;
                run_cycles  = CTRL_CYCLES_4;                
              end
              else if ( run == 5 ) begin
                conf        = CTRL_BITS_5;
                conf_in0    = CTRL_IN0_5;
                conf_in1    = CTRL_IN1_5;
                conf_out0   = CTRL_OUT0_5;
                conf_out1   = CTRL_OUT1_5;
                run_rep     = CTRL_REP_5;
                run_cycles  = CTRL_CYCLES_5;
              end
              else if ( run == 6 ) begin
                conf        = CTRL_BITS_6;
                conf_in0    = CTRL_IN0_6;
                conf_in1    = CTRL_IN1_6;
                conf_out0   = CTRL_OUT0_6;
                conf_out1   = CTRL_OUT1_6;
                run_rep     = CTRL_REP_6;
                run_cycles  = CTRL_CYCLES_6;
              end
              else if ( run == 7 ) begin
                conf        = CTRL_BITS_7;
                conf_in0    = CTRL_IN0_7;
                conf_in1    = CTRL_IN1_7;
                conf_out0   = CTRL_OUT0_7;
                conf_out1   = CTRL_OUT1_7;
                run_rep     = CTRL_REP_7;
                run_cycles  = CTRL_CYCLES_7;
              end
              else if ( run == 8 ) begin
                conf        = CTRL_BITS_8;
                conf_in0    = CTRL_IN0_8;
                conf_in1    = CTRL_IN1_8;
                conf_out0   = CTRL_OUT0_8;
                conf_out1   = CTRL_OUT1_8;
                run_rep     = CTRL_REP_8;
                run_cycles  = CTRL_CYCLES_8;
              end
              else if ( run == 9 ) begin
                conf        = CTRL_BITS_9;
                conf_in0    = CTRL_IN0_9;
                conf_in1    = CTRL_IN1_9;
                conf_out0   = CTRL_OUT0_9;
                conf_out1   = CTRL_OUT1_9;
                run_rep     = CTRL_REP_9;
                run_cycles  = CTRL_CYCLES_9;
              end
              else if ( run == 10 ) begin
                conf        = CTRL_BITS_10;
                conf_in0    = CTRL_IN0_10;
                conf_in1    = CTRL_IN1_10;
                conf_out0   = CTRL_OUT0_10;
                conf_out1   = CTRL_OUT1_10;
                run_rep     = CTRL_REP_10;
                run_cycles  = CTRL_CYCLES_10;
              end
              else if ( run == 11 ) begin
                conf        = CTRL_BITS_11;
                conf_in0    = CTRL_IN0_11;
                conf_in1    = CTRL_IN1_11;
                conf_out0   = CTRL_OUT0_11;
                conf_out1   = CTRL_OUT1_11;
                run_rep     = CTRL_REP_11;
                run_cycles  = CTRL_CYCLES_11;
              end
              else if ( run == 12 ) begin
                conf        = CTRL_BITS_12;
                conf_in0    = CTRL_IN0_12;
                conf_in1    = CTRL_IN1_12;
                conf_out0   = CTRL_OUT0_12;
                conf_out1   = CTRL_OUT1_12;
                run_rep     = CTRL_REP_12;
                run_cycles  = CTRL_CYCLES_12;
              end
              else if ( run == 13 ) begin
                conf        = CTRL_BITS_13;
                conf_in0    = CTRL_IN0_13;
                conf_in1    = CTRL_IN1_13;
                conf_out0   = CTRL_OUT0_13;
                conf_out1   = CTRL_OUT1_13;
                run_rep     = CTRL_REP_13;
                run_cycles  = CTRL_CYCLES_13;
              end
              else begin
                $display("%d run %d is not properly setup!?", $time, run);
                $finish;
              end
              
              if ((run_rep_count==0) && (run_rep > 1)) begin
                $display("note: run %d with %d repetitions might be slow. please be patient!", run, run_rep);
                $finish;
              end
    
              // get index of last good sample depending on strobe settings
              if (conf_in1[(CTRL_IN1_DST_DATA_STRB+1)*CTRL_IN_SRC_BITS-1 -: CTRL_IN_SRC_BITS] != 0) begin
                last_good = gen_last_good_strb;
              end
              else begin
                last_good = gen_last_good_nop;
              end
                            
              if (( run == RUN_ABORT_0 ) || ( run == RUN_ABORT_1 ) || ( run == RUN_ABORT_2 )) begin
                // reset line trigger period to ensure board goes into run_wait state
                @(posedge clk_bus);
                line_trg_reset = 1'b1;
                //@(posedge clk_bus);
                //line_trg_reset = 1'b0;
              end
              else begin
                @(posedge clk_bus);
                line_trg_hold = 1'b1;
              end
              
              // AXI Lite interface: set control bits: SERVER READY
              if ( DUT.control_axi != 0 ) begin
                $display("%d control is not 0!?", $time);
                $finish;
              end
              repeat(50) @(posedge clk_AXI); // ensure conf_out is updated
              #1
              AXI_wr_valid = 1'b1;
              AXI_wr_addr = REG_CTRL*REG_NUM_BYTES;
              AXI_wr_data = (1<<CTRL_READY);
              @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b0;
              // wait until data written
              while ( AXI_wr_ready == 1'b0 ) begin 
                @(posedge clk_AXI);
              end
              repeat(1) @(posedge clk_AXI);
              if ( DUT.control_axi != (1<<STATUS_READY) ) begin
                $display("%d SERVER READY bit is not set!?", $time);
                $finish;
              end
              else begin
                $display("%d *** SERVER READY! *** ", $time);
              end
        
              // lock external clock if selected
              if ( conf & (1<<CTRL_CLK_EXT) ) begin
                clk_ext_locked = 1'b1;
              end
              else begin
                clk_ext_locked = 1'b0;
              end
    
              // AXI Lite interface: write configuration bits
              #1
              AXI_wr_valid = 1'b1;
              AXI_wr_addr = REG_CTRL*REG_NUM_BYTES;
              AXI_wr_data = conf;
              @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b0;
              // wait until data written
              while ( AXI_wr_ready == 1'b0 ) begin 
                @(posedge clk_AXI);
              end
              repeat(1) @(posedge clk_AXI);
              if ( DUT.control_axi != conf ) begin
                $display("%d CONFIG bit are not set!?", $time);
                $finish;
              end
              else begin
                $display("%d *** CONFIG OK (0x%x) *** ", $time, conf);
              end
              
              // AXI Lite interface: write input configuration bits 0     
              #1
              AXI_wr_valid = 1'b1;
              AXI_wr_addr = REG_CTRL_IN0*REG_NUM_BYTES;
              AXI_wr_data = conf_in0;
              @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b0;
              // wait until data written
              while ( AXI_wr_ready == 1'b0 ) begin 
                @(posedge clk_AXI);
              end
              repeat(1) @(posedge clk_AXI);
              if ( DUT.ctrl_in0_axi != conf_in0 ) begin
                $display("%d CTRL IN0 bits are not set!?", $time);
                $finish;
              end
              else begin
                $display("%d *** CTRL IN0 OK (0x%x) *** ", $time, conf_in0);
              end
    
              // AXI Lite interface: write input configuration bits 1     
              #1
              AXI_wr_valid = 1'b1;
              AXI_wr_addr = REG_CTRL_IN1*REG_NUM_BYTES;
              AXI_wr_data = conf_in1;
              @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b0;
              // wait until data written
              while ( AXI_wr_ready == 1'b0 ) begin 
                @(posedge clk_AXI);
              end
              repeat(1) @(posedge clk_AXI);
              if ( DUT.ctrl_in1_axi != conf_in1 ) begin
                $display("%d CTRL IN1 not set!?", $time);
                $finish;
              end
              else begin
                $display("%d *** CTRL IN1 OK (0x%x) *** ", $time, conf_in1);
              end

              // AXI Lite interface: write output configuration bits 0    
              #1
              AXI_wr_valid = 1'b1;
              AXI_wr_addr = REG_CTRL_OUT0*REG_NUM_BYTES;
              AXI_wr_data = conf_out0;
              @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b0;
              // wait until data written
              while ( AXI_wr_ready == 1'b0 ) begin 
                @(posedge clk_AXI);
              end
              repeat(1) @(posedge clk_AXI);
              if ( DUT.ctrl_out0_axi != conf_out0 ) begin
                $display("%d CTRL OUT0 not set!?", $time);
                $finish;
              end
              else begin
                $display("%d *** CTRL OUT0 OK (0x%x) *** ", $time, conf_out0);
              end
    
              // AXI Lite interface: write output configuration bits 1    
              #1
              AXI_wr_valid = 1'b1;
              AXI_wr_addr = REG_CTRL_OUT1*REG_NUM_BYTES;
              AXI_wr_data = conf_out1;
              @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b0;
              // wait until data written
              while ( AXI_wr_ready == 1'b0 ) begin 
                @(posedge clk_AXI);
              end
              repeat(1) @(posedge clk_AXI);
              if ( DUT.ctrl_out1_axi != conf_out1 ) begin
                $display("%d CTRL OUT1 not set!?", $time);
                $finish;
              end
              else begin
                $display("%d *** CTRL OUT1 OK (0x%x) *** ", $time, conf_out1);
              end
            
              if (( run == 0 ) && (run_rep_count == 0)) begin 
                  // clock_div and strb_delay must be written only once!
                  // otherwise we get a glitch in contigous output strobe
                  // and toggle strobe is reset

                  // AXI Lite interface write clock divider
                  #1
                  AXI_wr_valid = 1'b1;
                  AXI_wr_addr = REG_CLK_DIV*REG_NUM_BYTES;
                  AXI_wr_data = CLK_DIV;
                  @(posedge clk_AXI);
                  #1
                  AXI_wr_valid = 1'b0;
                  // wait until data written
                  while ( AXI_wr_ready == 1'b0 ) begin 
                    @(posedge clk_AXI);
                  end
                  repeat(1) @(posedge clk_AXI);
                  if ( DUT.clk_div_axi != CLK_DIV ) begin
                    $display("%d CLK_DIV not set!?", $time);
                    $finish;
                  end
                  else begin
                    $display("%d *** CLK_DIV set OK (only 1x) *** ", $time);
                  end
            
                  // AXI Lite interface write strobe delay
                  #1
                  AXI_wr_valid = 1'b1;
                  AXI_wr_addr = REG_STRB_DELAY*REG_NUM_BYTES;
                  AXI_wr_data = STRB_DELAY;
                  @(posedge clk_AXI);
                  #1
                  AXI_wr_valid = 1'b0;
                  // wait until data written
                  while ( AXI_wr_ready == 1'b0 ) begin 
                    @(posedge clk_AXI);
                  end
                  repeat(1) @(posedge clk_AXI);
                  if ( DUT.strb_delay_axi != STRB_DELAY ) begin
                    $display("%d STRB_DELAY not set!?", $time);
                    $finish;
                  end
                  else begin
                    $display("%d *** STRB_DELAY set OK (only 1x) *** ", $time);
                  end
              end
            
              // AXI Lite interface write sync delay
              #1
              AXI_wr_valid = 1'b1;
              AXI_wr_addr = REG_SYNC_DELAY*REG_NUM_BYTES;
              if ( conf & CTRL_AUTO_SYNC_PRIM ) 
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
              if ( DUT.sync_delay_axi != AXI_wr_data ) begin
                $display("%d SYNC_DELAY not set!?", $time);
                $finish;
              end
              else begin
                $display("%d *** SYNC_DELAY set OK *** ", $time);
              end
        
              // AXI Lite interface write sync phase
              #1
              AXI_wr_valid = 1'b1;
              AXI_wr_addr = REG_SYNC_PHASE*REG_NUM_BYTES;
              AXI_wr_data = SYNC_PHASE;
              @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b0;
              // wait until data written
              while ( AXI_wr_ready == 1'b0 ) begin 
                @(posedge clk_AXI);
              end
              repeat(1) @(posedge clk_AXI);
              if ( DUT.sync_phase_axi != SYNC_PHASE ) begin
                $display("%d SYNC_PHASE not set!?", $time);
                $finish;
              end
              else begin
                $display("%d *** SYNC_PHASE set OK *** ", $time);
              end
        
              // AXI Lite interface: write NUM_SAMPLES
              if ((run == 0) && ( DUT.num_samples_axi != 0 )) begin
                $display("%d NUM_SAMPLES %d not 0!?", $time, DUT.num_samples_axi);
                $finish;
              end
              if ( AXI_wr_ready != 1'b1 ) begin
                $display("%d AXI write not ready!?", $time);
                $finish;
              end
              #1
              AXI_wr_data = GEN_NUM_SAMPLES;
              AXI_wr_addr = REG_NUM_SAMPLES*REG_NUM_BYTES;
              AXI_wr_valid = 1'b1;
              @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b0;
              // wait until data written
              while ( AXI_wr_ready == 1'b0 ) begin 
                @(posedge clk_AXI);
              end
              repeat(2) @(posedge clk_AXI);
              if ( DUT.num_samples_axi == GEN_NUM_SAMPLES ) begin
                $display("%d *** NUM_SAMPLES written (ok) *** ", $time);
              end
              else begin
                $display("%d NUM_SAMPLES writing error!", $time);
                $finish;
              end
              
              // AXI Lite interface: write NUM_CYCLES
              if ((run == 0) && ( DUT.num_cycles_axi != 1 )) begin
                $display("%d NUM_CYCLES %d not 1!?", $time, DUT.num_cycles_axi);
                $finish;
              end
              if ( AXI_wr_ready != 1'b1 ) begin
                $display("%d AXI write not ready!?", $time);
                $finish;
              end
              #1
              AXI_wr_data = run_cycles;
              AXI_wr_addr = REG_NUM_CYCLES*REG_NUM_BYTES;
              AXI_wr_valid = 1'b1;
              @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b0;
              // wait until data written
              while ( AXI_wr_ready == 1'b0 ) begin 
                @(posedge clk_AXI);
              end
              repeat(2) @(posedge clk_AXI);
              if ( DUT.num_cycles_axi == run_cycles ) begin
                $display("%d *** NUM_CYCLES written (ok) *** ", $time);
              end
              else begin
                $display("%d NUM_CYCLES writing error!", $time);
                $display("%d != %d", DUT.num_cycles_axi, run_cycles);
                $finish;
              end

              // after num_samples written we can generate TX data
              repeat(5) @(posedge clk_stream);
              #1; gen_ctrl = 1'b1;
              
              // AXI Lite interface: read NUM_SAMPLES
              #1
              AXI_rd_addr = REG_NUM_SAMPLES*REG_NUM_BYTES;
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
              while ( DUT.status_ready_axi == 1'b0 ) begin 
                @(posedge clk_AXI);
              end
              $display("%d *** READY! *** ", $time);
        
              // AXI Lite interface: set RUN bit
              repeat(125) @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b1;
              AXI_wr_addr = REG_CTRL*REG_NUM_BYTES;
              AXI_wr_data = (1<<CTRL_RUN) | conf;
              @(posedge clk_AXI);
              #1
              AXI_wr_valid = 1'b0;
              
              // wait until run_en bit is set
              while ( DUT.run_en_axi == 1'b0 ) begin 
                @(posedge clk_bus);
              end
              if ( ( DUT.run_en_axi != 1'b1 ) || ( DUT.control_axi != ((1<<CTRL_RUN)|conf) ) ) begin
                $display("%d RUN bit is not set!?", $time);
                $finish;
              end
              else begin
                $display("%d *** RUN! *** ", $time);
              end
              
              // check if ext clock is selected or not as configured
              if ( conf & (1<<CTRL_CLK_EXT) ) begin
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
                                          
              // release line trigger after run_en bit is set
              // for some configs the simulation might not detect the line_trg properly
              // and give false error below when checking the start trigger
              // maybe this solves this problem? 
              @(posedge clk_bus);
              line_trg_hold  = 1'b0;
              line_trg_reset = 1'b0;
              
              if (conf_in0[(CTRL_IN0_DST_TRG_START+1)*CTRL_IN_SRC_BITS -1 -: CTRL_IN_SRC_BITS] != 0) begin
                  // if external start trigger enabled, we check that boad is waiting
                  // note: we use line_trg signal for all trigger signals
                  // wait for start trigger and ensure run bit is not set in status
                  if ( CTRL_TRG_START_EDGE_POS ) begin // rising edge
                    if ( line_trg == 1'b1 ) begin
                        $display("%d *** EXT_TRIG waiting for rising edge (high) ... *** ", $time);
                        while( line_trg == 1'b1 ) begin
                            if ( DUT.status_run_axi ) begin
                                $display("%d *** EXT_TRIG error: not waiting for rising edge! *** ", $time);
                                $finish;
                            end
                            @(posedge clk_bus);
                        end
                    end
                    $display("%d *** EXT_TRIG waiting for rising edge (low) ... *** ", $time);
                    while( line_trg == 1'b0 ) begin
                        if ( DUT.status_run_axi ) begin
                            $display("%d *** EXT_TRIG error: not waiting for rising edge! *** ", $time);
                            $finish;
                        end
                        @(posedge clk_bus);
                    end
                    $display("%d *** EXT_TRIG rising edge now! *** ", $time);            
                    while( DUT.status_run_axi == 1'b0 ) begin
                        @(posedge clk_bus);
                    end
                    $display("%d *** EXT_TRIG rising edge ok! *** ", $time);            
                  end
                  else if ( CTRL_TRG_START_EDGE_NEG ) begin // falling edge
                    while( line_trg == 1'b0 ) begin
                        if ( DUT.status_run_axi ) begin
                            $display("%d *** EXT_TRIG error: not waiting for falling edge! *** ", $time);
                            $finish;
                        end
                        @(posedge clk_bus);
                    end
                    while( line_trg == 1'b1 ) begin
                        if ( DUT.status_run_axi ) begin
                            $display("%d *** EXT_TRIG error: not waiting for falling edge! *** ", $time);
                            $finish;
                        end
                        @(posedge clk_bus);
                    end
                    $display("%d *** EXT_TRIG falling edge now! *** ", $time);            
                    while( DUT.status_run_axi == 1'b0 ) begin
                        @(posedge clk_bus);
                    end
                    $display("%d *** EXT_TRIG falling edge ok! *** ", $time);            
                  end
                  else if ( CTRL_TRG_START_HIGH ) begin // high level
                    while( line_trg == 1'b0 ) begin
                        if ( DUT.status_run_axi ) begin
                            $display("%d *** EXT_TRIG error: not waiting for high level! *** ", $time);
                            $finish;
                        end
                        @(posedge clk_bus);
                    end
                    $display("%d *** EXT_TRIG level high now! *** ", $time);            
                    while( DUT.status_run_axi == 1'b0 ) begin
                        @(posedge clk_bus);
                    end
                    $display("%d *** EXT_TRIG level high ok! *** ", $time);            
                  end
                  else if ( CTRL_TRG_START_LOW ) begin // low level
                    while( line_trg == 1'b1 ) begin
                        if ( DUT.status_run_axi ) begin
                            $display("%d *** EXT_TRIG error: not waiting for low level! *** ", $time);
                            $finish;
                        end
                        @(posedge clk_bus);
                    end
                    $display("%d *** EXT_TRIG level low now! *** ", $time);            
                    while( DUT.status_run_axi == 1'b0 ) begin
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
                // reset line trigger for loop clk_bus cycles
                @(posedge clk_bus2);
                line_trg_reset = 1'b1;
                repeat(run_rep_count+1) @(posedge clk_bus2);
                line_trg_reset = 1'b0;
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
                    while( DUT.status_wait_axi == 1'b0 ) begin
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
                    if (DUT.status_wait_axi == 1'b0) begin
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
                    AXI_wr_addr = REG_CTRL*REG_NUM_BYTES;
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
                    if ( ( DUT.run_en_axi != 1'b0 ) || ( DUT.status_run_axi != 1'b1 ) || ( DUT.status_wait_axi != 1'b1 ) || ( DUT.control_axi != (conf) ) ) begin
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
                    if ( ( DUT.run_en_axi != 1'b0 ) || ( DUT.status_run_axi != 1'b1 ) || ( DUT.status_wait_axi != 1'b1 ) || ( DUT.control_axi != (conf) ) ) begin
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
                expect_error = (1<<STATUS_ERR_LOCK);
                
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
                while( (DUT.status_axi & STATUS_ERR_ALL) != expect_error) begin
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
                    while ( (DUT.error_lock_axi != 1'b1) || (DUT.error_axi != 1'b1) ) begin 
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
              repeat(5) @(posedge clk_stream);
              #1; 
              gen_ctrl       = 1'b0;
              gen_ctrl_reset = 1'b1;
              repeat(2) @(posedge clk_stream);
              #1
              gen_ctrl_reset = 1'b0;
    
              // perform software reset
              software_reset;
                            
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
