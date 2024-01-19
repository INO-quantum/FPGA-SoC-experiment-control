`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// control_out_mux.v 
// multiplexer for control out registers
// created 06/05/2023 by Andi
// last change 06/05/2023
//////////////////////////////////////////////////////////////////////////////////

module ctrl_out_mux # (
    // regiser data width must be 32
    parameter integer REG_WIDTH                 = 32,
    // output control register
    parameter integer CTRL_OUT_SRC_BITS         = 5,
    parameter integer CTRL_OUT_LEVEL_BITS       = 2,

    // output destinations offsets (max. floor(32/CTRL_OUT_DST_BITS) = 4 possible per register)
    // register 0
    parameter integer CTRL_OUT0_DST_OUT0        = 0,    // out[0]
    parameter integer CTRL_OUT0_DST_OUT1        = 1,    // out[1]
    parameter integer CTRL_OUT0_DST_OUT2        = 2,    // out[2]
    parameter integer CTRL_OUT0_DST_LED_R       = 3,    // led[0]
    // register 1
    parameter integer CTRL_OUT1_DST_LED_G       = 0,    // led[1]
    parameter integer CTRL_OUT1_DST_LED_B       = 1,    // led[2]
    parameter integer CTRL_OUT1_DST_BUS_EN_0    = 2,    // bus_en[0]
    parameter integer CTRL_OUT1_DST_BUS_EN_1    = 3,    // bus_en[1]

    // output sources (max. 2^CTRL_OUT_SRC_BITS = 32 possible)
    // note: these numbers are hard-coded below with incremental step. parameter is for documentation only.
    parameter integer CTRL_OUT_SRC_FIXED        = 0,    // fixed output with given level
    parameter integer CTRL_OUT_SRC_SYNC_OUT     = 1,    // sync_out
    parameter integer CTRL_OUT_SRC_SYNC_EN      = 2,    // sync_en (used for debugging)
    parameter integer CTRL_OUT_SRC_SYNC_MON     = 3,    // sync_mon (used for debugging)
    parameter integer CTRL_OUT_SRC_CLK_LOST     = 4,    // clock lost
    parameter integer CTRL_OUT_SRC_ERROR        = 5,    // error
    parameter integer CTRL_OUT_SRC_RUN          = 6,    // run (or wait)
    parameter integer CTRL_OUT_SRC_WAIT         = 7,    // wait
    parameter integer CTRL_OUT_SRC_READY        = 8,    // ready (data in FIFO)
    parameter integer CTRL_OUT_SRC_RESTART      = 9,    // restart (toogle bit in cycling mode, could also indicate restart trigger)
    parameter integer CTRL_OUT_SRC_TRG_START    = 10,   // start trigger (toggle bit)
    parameter integer CTRL_OUT_SRC_TRG_STOP     = 11,   // stop trigger (toggle bit)
    parameter integer CTRL_OUT_SRC_TRG_RESTART  = 12,   // restart trigger (toggle bit)
    parameter integer CTRL_OUT_SRC_DATA_0       = 13,   // data bit 0-3 
    parameter integer CTRL_OUT_SRC_DATA_4       = 14,   // data bit 4-7
    parameter integer CTRL_OUT_SRC_DATA_8       = 15,   // data bit 8-11
    parameter integer CTRL_OUT_SRC_DATA_12      = 16,   // data bit 12-15 
    parameter integer CTRL_OUT_SRC_DATA_16      = 17,   // data bit 16-19
    parameter integer CTRL_OUT_SRC_DATA_20      = 18,   // data bit 20-23 
    parameter integer CTRL_OUT_SRC_DATA_24      = 19,   // data bit 24-27
    parameter integer CTRL_OUT_SRC_DATA_28      = 20,   // data bit 28-31
        
    // output levels (max. 2^CTRL_OUT_LEVEL_BITS = 4 possible)
    // note: these numbers are hard-coded below with incremental step. parameter is for documentation only.
    parameter integer CTRL_OUT_LEVEL_LOW        = 0,    // level active low  = inverted
    parameter integer CTRL_OUT_LEVEL_HIGH       = 1,    // level active high = normal
    // output data offset (max. 2^CTRL_OUT_LEVEL_BITS = 4 possible)
    // note: these numbers are hard-coded below with incremental step. parameter is for documentation only.
    parameter integer CTRL_OUT_DATA_0           = 0,    // offset bit 0
    parameter integer CTRL_OUT_DATA_1           = 1,    // offset bit 1
    parameter integer CTRL_OUT_DATA_2           = 2,    // offset bit 2
    parameter integer CTRL_OUT_DATA_3           = 3     // offset bit 3
)
(
    // clock and reset
    input wire clock,
    input wire reset_n,
    // control register
    input wire [REG_WIDTH-1:0] ctrl_out0,
    input wire [REG_WIDTH-1:0] ctrl_out1,
    // input sources
    input wire sync_out,
    input wire sync_en,
    input wire sync_mon,
    input wire clk_ext_lost,
    input wire error,
    input wire status_run,
    input wire status_wait,
    input wire status_ready,
    input wire status_restart,
    input wire trg_start,
    input wire trg_stop,
    input wire trg_restart,
    // input data
    //input wire [REG_WIDTH-1:0] data,
    // multiplexed outputs
    output wire [2:0] out,
    //output wire [2:0] led,
    output wire [1:0] bus_en
);
    
    //////////////////////////////////////////////////////////////////////////////////
    
    localparam integer CTRL_OUT_DST_BITS = CTRL_OUT_SRC_BITS + CTRL_OUT_LEVEL_BITS;
    localparam integer NUM_SRC = 12;        // number of input sources
    //localparam integer NUM_SRC_PACKED = REG_WIDTH + (NUM_SRC+1)*4;
    localparam integer NUM_SRC_PACKED = (NUM_SRC+1)*4;

    wire [CTRL_OUT_DST_BITS-1:0] ctrl_out_0   = ctrl_out0[(CTRL_OUT0_DST_OUT0+1)*CTRL_OUT_DST_BITS-1 -: CTRL_OUT_DST_BITS];
    wire [CTRL_OUT_DST_BITS-1:0] ctrl_out_1   = ctrl_out0[(CTRL_OUT0_DST_OUT1+1)*CTRL_OUT_DST_BITS-1 -: CTRL_OUT_DST_BITS];
    wire [CTRL_OUT_DST_BITS-1:0] ctrl_out_2   = ctrl_out0[(CTRL_OUT0_DST_OUT2+1)*CTRL_OUT_DST_BITS-1 -: CTRL_OUT_DST_BITS];
    wire [CTRL_OUT_DST_BITS-1:0] ctrl_bus_en0 = ctrl_out1[(CTRL_OUT1_DST_BUS_EN_0+1)*CTRL_OUT_DST_BITS-1 -: CTRL_OUT_DST_BITS];
    wire [CTRL_OUT_DST_BITS-1:0] ctrl_bus_en1 = ctrl_out1[(CTRL_OUT1_DST_BUS_EN_1+1)*CTRL_OUT_DST_BITS-1 -: CTRL_OUT_DST_BITS];

    wire [NUM_SRC_PACKED-1:0] src_packed = {//data,
                                            2'b00,  trg_restart,    ~trg_restart,
                                            2'b00,  trg_stop,       ~trg_stop,
                                            2'b00,  trg_start,      ~trg_start,
                                            2'b00,  status_restart, ~status_restart,
                                            2'b00,  status_ready,   ~status_ready,
                                            2'b00,  status_wait,    ~status_wait,
                                            2'b00,  status_run,     ~status_run,
                                            2'b00,  error,          ~error,
                                            2'b00,  clk_ext_lost,   ~clk_ext_lost,
                                            2'b00,  sync_mon,       ~sync_mon,
                                            2'b00,  sync_en,        ~sync_en,
                                            2'b00,  sync_out,       ~sync_out,
                                            4'b0010 // fixed low/high
                                            }; 

    mux # (
        .CTRL_BITS(CTRL_OUT_DST_BITS),
        .NUM_IN(NUM_SRC_PACKED))
    mux_out0 (
        .clock(clock),
        .reset_n(reset_n),
        .ctrl({ctrl_out_0[CTRL_OUT_SRC_BITS-1:0],ctrl_out_0[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS]}),
        .in(src_packed),
        .out(out[0])
    );

    mux # (
        .CTRL_BITS(CTRL_OUT_DST_BITS),
        .NUM_IN(NUM_SRC_PACKED))
    mux_out1 (
        .clock(clock),
        .reset_n(reset_n),
        .ctrl({ctrl_out_1[CTRL_OUT_SRC_BITS-1:0],ctrl_out_1[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS]}),
        .in(src_packed),
        .out(out[1])
    );

    mux # (
        .CTRL_BITS(CTRL_OUT_DST_BITS),
        .NUM_IN(NUM_SRC_PACKED))
    mux_out2 (
        .clock(clock),
        .reset_n(reset_n),
        .ctrl({ctrl_out_2[CTRL_OUT_SRC_BITS-1:0],ctrl_out_2[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS]}),        
        .in(src_packed),
        .out(out[2])
    );

    /*
    mux # (
        .CTRL_BITS(CTRL_OUT_DST_BITS),
        .NUM_IN(NUM_SRC_PACKED))
    mux_led_r (
        .clock(clock),
        .reset_n(reset_n),
        .ctrl(ctrl_out0[(CTRL_OUT0_DST_LED_R+1)*CTRL_OUT_DST_BITS-1 -: CTRL_OUT_DST_BITS]),
        .in(src_packed),
        .out(led[0])
    );

    mux # (
        .CTRL_BITS(CTRL_OUT_DST_BITS),
        .NUM_IN(NUM_SRC_PACKED))
    mux_led_g (
        .clock(clock),
        .reset_n(reset_n),
        .ctrl(ctrl_out1[(CTRL_OUT1_DST_LED_G+1)*CTRL_OUT_DST_BITS-1 -: CTRL_OUT_DST_BITS]),
        .in(src_packed),
        .out(led[1])
    );

    mux # (
        .CTRL_BITS(CTRL_OUT_DST_BITS),
        .NUM_IN(NUM_SRC_PACKED))
    mux_led_b (
        .clock(clock),
        .reset_n(reset_n),
        .ctrl(ctrl_out1[(CTRL_OUT1_DST_LED_B+1)*CTRL_OUT_DST_BITS-1 -: CTRL_OUT_DST_BITS]),
        .in(src_packed),
        .out(led[2])
    );
    */

    mux # (
        .CTRL_BITS(CTRL_OUT_DST_BITS),
        .NUM_IN(NUM_SRC_PACKED))
    mux_bus_en_0 (
        .clock(clock),
        .reset_n(reset_n),
        .ctrl({ctrl_bus_en0[CTRL_OUT_SRC_BITS-1:0],ctrl_bus_en0[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS]}),
        .in(src_packed),
        .out(bus_en[0])
    );

    mux # (
        .CTRL_BITS(CTRL_OUT_DST_BITS),
        .NUM_IN(NUM_SRC_PACKED))
    mux_bus_en_1 (
        .clock(clock),
        .reset_n(reset_n),
        .ctrl({ctrl_bus_en1[CTRL_OUT_SRC_BITS-1:0],ctrl_bus_en1[CTRL_OUT_DST_BITS-1 -: CTRL_OUT_LEVEL_BITS]}),
        .in(src_packed),
        .out(bus_en[1])
    );

endmodule
