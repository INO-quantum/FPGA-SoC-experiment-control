`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// control_in_mux.v 
// multiplexer for control in registers
// created 06/05/2023 by Andi
// last change 06/05/2023
//////////////////////////////////////////////////////////////////////////////////

module ctrl_in_mux # (

    // global input parameters
    // when changing any of these code below must be reviewed!
    
    // regiser data width must be 32
    parameter integer REG_WIDTH                 = 32,
    // number of external inputs
    parameter integer NUM_EXT_IN                = 3,
    // number of strobe signals
    parameter integer NUM_STROBE                = 2,
    // synchronization stages
    parameter integer SYNC                      = 2,
    // size of input data pipeline
    parameter integer IN_DATA_BUF               = 2,
    
    // following parameters do not need to be defined outside of this module
    
    // input control register
    parameter integer CTRL_IN_SRC_BITS          = 4,
    parameter integer CTRL_IN_LEVEL_BITS        = 2,

    // input destinations offsets (max. floor(32/CTRL_IN_DST_BITS) = 5 possible per register)
    // register 0
    parameter integer CTRL_IN0_DST_START        = 0,    // start trigger (= sync_in with DIO_CTRL_AUTO_SYNC_EN)
    parameter integer CTRL_IN0_DST_STOP         = 1,    // stop trigger
    parameter integer CTRL_IN0_DST_RESTART      = 2,    // restart trigger
    parameter integer CTRL_IN0_DST_DATA_STRB0   = 3,    // strobe_0 bit 
    parameter integer CTRL_IN0_DST_DATA_STRB1   = 4,    // strobe_1 bit 
    // register 1
    parameter integer CTRL_IN1_DST_DATA_NOP     = 0,    // no operation bit (selection is ignored, always data bit 31)
    parameter integer CTRL_IN1_DST_DATA_IRQ     = 1,    // IRQ bit

    // input sources (max. 2^CTRL_IN_SRC_BITS = 16 possible)
    // note: these numbers are hard-coded below with incremental step. parameter is for documentation only.
    parameter integer CTRL_IN_SRC_NONE          = 0,    // source disabled
    parameter integer CTRL_IN_SRC_IN0           = 1,    // ext_in[0]
    parameter integer CTRL_IN_SRC_IN1           = 2,    // ext_in[1]
    parameter integer CTRL_IN_SRC_IN2           = 3,    // ext_in[2]
    parameter integer CTRL_IN_SRC_DATA_0        = 4,    // data bit 0-3 
    parameter integer CTRL_IN_SRC_DATA_4        = 5,    // data bit 4-7
    parameter integer CTRL_IN_SRC_DATA_8        = 6,    // data bit 8-11
    parameter integer CTRL_IN_SRC_DATA_12       = 7,    // data bit 12-15 
    parameter integer CTRL_IN_SRC_DATA_16       = 8,    // data bit 16-19
    parameter integer CTRL_IN_SRC_DATA_20       = 9,    // data bit 20-23 
    parameter integer CTRL_IN_SRC_DATA_24       = 10,   // data bit 24-27
    parameter integer CTRL_IN_SRC_DATA_28       = 11,   // data bit 28-31

    // input levels (max. 2^CTRL_IN_LEVEL_BITS = 4 possible)
    // note: these numbers are hard-coded below with incremental step. parameter is for documentation only.
    parameter integer CTRL_IN_LEVEL_LOW         = 0,    // level low
    parameter integer CTRL_IN_LEVEL_HIGH        = 1,    // level high
    parameter integer CTRL_IN_EDGE_FALLING      = 2,    // edge falling
    parameter integer CTRL_IN_EDGE_RISING       = 3,    // edge rising
    // optional data bit indices added to CTRL_IN_SRC_DATA_#
    // note: these numbers are hard-coded below with incremental step. parameter is for documentation only.
    parameter integer CTRL_IN_DATA_0            = 0,    // offset bit 0
    parameter integer CTRL_IN_DATA_1            = 1,    // offset bit 1
    parameter integer CTRL_IN_DATA_2            = 2,    // offset bit 2
    parameter integer CTRL_IN_DATA_3            = 3     // offset bit 3
)
(
    // clock and reset
    input wire clock_bus,
    input wire clock_det,
    input wire reset_bus_n,
    input wire reset_det_n,
    // control register
    input wire [REG_WIDTH-1:0] ctrl_in0_det, // @ clock_det
    input wire [REG_WIDTH-1:0] ctrl_in0_bus,
    input wire [REG_WIDTH-1:0] ctrl_in1_bus,
    // external inputs
    input wire [NUM_EXT_IN-1:0] ext_in_none, // not synchronized
    // run enable bit
    input wire run_en,
    // input data
    input wire data_reload,
    input wire in_valid,
    input wire [REG_WIDTH-1:0] data,
    // multiplexed trigger outputs
    output wire trg_start_en,
    output wire trg_start_pulse,
    output wire trg_start_tgl,
    output wire trg_start_tgl_det, // @ clock_det
    output wire trg_stop_en,
    output wire trg_stop_pulse,
    output wire trg_stop_tgl,
    output wire trg_restart_en,
    output wire trg_restart_pulse,
    output wire trg_restart_tgl,
    // data bit outputs
    output wire data_stop_en,
    output wire data_stop,
    output wire data_nop_en,
    output wire data_nop,
    output wire data_irq_en,
    output wire data_irq,
    output wire [NUM_STROBE-1:0] data_strb_en,
    output wire [NUM_STROBE-1:0] data_strb_nop
);
    
    //////////////////////////////////////////////////////////////////////////////////
    // bus clock domain @ clock_bus
    
    localparam integer CTRL_IN_DST_BITS = CTRL_IN_SRC_BITS + CTRL_IN_LEVEL_BITS;

    // assign control_trg register @ clk_bus
    wire [CTRL_IN_DST_BITS-1:0] ctrl_in_start_bus   = ctrl_in0_bus[CTRL_IN0_DST_START      +CTRL_IN_DST_BITS-1 -: CTRL_IN_DST_BITS];
    wire [CTRL_IN_DST_BITS-1:0] ctrl_in_stop_bus    = ctrl_in0_bus[CTRL_IN0_DST_STOP       +CTRL_IN_DST_BITS-1 -: CTRL_IN_DST_BITS];
    wire [CTRL_IN_DST_BITS-1:0] ctrl_in_restart_bus = ctrl_in0_bus[CTRL_IN0_DST_RESTART    +CTRL_IN_DST_BITS-1 -: CTRL_IN_DST_BITS];
    wire [CTRL_IN_DST_BITS-1:0] ctrl_in_strb0_bus   = ctrl_in0_bus[CTRL_IN0_DST_DATA_STRB0 +CTRL_IN_DST_BITS-1 -: CTRL_IN_DST_BITS];
    wire [CTRL_IN_DST_BITS-1:0] ctrl_in_strb1_bus   = ctrl_in0_bus[CTRL_IN0_DST_DATA_STRB1 +CTRL_IN_DST_BITS-1 -: CTRL_IN_DST_BITS];
    wire [CTRL_IN_DST_BITS-1:0] ctrl_in_nop_bus     = ctrl_in1_bus[CTRL_IN1_DST_DATA_NOP   +CTRL_IN_DST_BITS-1 -: CTRL_IN_DST_BITS];
    wire [CTRL_IN_DST_BITS-1:0] ctrl_in_irq_bus     = ctrl_in1_bus[CTRL_IN1_DST_DATA_IRQ   +CTRL_IN_DST_BITS-1 -: CTRL_IN_DST_BITS];
  
    // synchronize external inputs for triggers @ clk_bus
    // note: there is no way to ensure that these bits are synchronized with each other!
    //       when different inputs are used and might change state at the same time,
    //       ensure that STOP and RESTART trigger are sampled at opposite edges.
    //       for START trigger use auto-sync module (with as_en bit) which introduces a delay 
    //       which should avoid this problem.
    wire [NUM_EXT_IN - 1 : 0] ext_in_bus;
    generate
    for (genvar i = 0; i < NUM_EXT_IN; i = i + 1) begin : GEN_EXT
        (* ASYNC_REG = "TRUE" *)
        reg [SYNC-1:0] ext_in_bus_cdc;
        always @ ( posedge clock_bus ) begin
            ext_in_bus_cdc <= {ext_in_bus_cdc[SYNC-2:0],ext_in_none[i]};
        end
        assign ext_in_bus[i] = ext_in_bus_cdc[SYNC-1];
    end
    endgenerate

    // MUX start trigger @ clk_bus
    reg start_trg_bus = 1'b0;
    reg [1:0] start_trg_en_ff_bus = 2'b00;
    always @ ( posedge clock_bus ) begin
        if ( reset_bus_n == 1'b0 ) begin
            start_trg_bus       <= 1'b0;
            start_trg_en_ff_bus <= 2'b00;
        end
        else begin
            start_trg_bus          <= ( ctrl_in_start_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_IN0 ) ? ext_in_bus[0] :
                                      ( ctrl_in_start_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_IN1 ) ? ext_in_bus[1] :
                                      ( ctrl_in_start_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_IN2 ) ? ext_in_bus[2] : 1'b0;
            start_trg_en_ff_bus[0] <= ( ctrl_in_start_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_IN0 ) ? 1'b1 :
                                      ( ctrl_in_start_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_IN1 ) ? 1'b1 :
                                      ( ctrl_in_start_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_IN2 ) ? 1'b1 : 1'b0;
            start_trg_en_ff_bus[1] <= start_trg_en_ff_bus[0];
        end
    end
    wire start_trg_en_bus = & start_trg_en_ff_bus; // delayed enable singal to avoid spike right after programming 
          
    // generate start trigger positive edge pulse @ clk_det
    reg start_trg_ff_bus    = 1'b0;
    reg start_trg_pulse_bus = 1'b0;
    reg start_trg_tgl_bus   = 1'b0;
    always @ ( posedge clock_bus ) begin
            if (reset_bus_n == 1'b0) begin
            start_trg_ff_bus    <= 1'b0;
            start_trg_pulse_bus <= 1'b0;
            start_trg_tgl_bus   <= 1'b0;
        end
        else begin
        start_trg_ff_bus    <= (ctrl_in_start_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_LEVEL_HIGH  ) ? run_en & start_trg_en_bus & start_trg_bus : 
                               (ctrl_in_start_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_LEVEL_LOW   ) ? run_en & start_trg_en_bus & ~start_trg_bus :
                               (ctrl_in_start_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_EDGE_FALLING) ? start_trg_bus :
                               (ctrl_in_start_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_EDGE_RISING ) ? start_trg_bus : 1'b0;
        start_trg_pulse_bus <= run_en & start_trg_en_bus & (
                               (ctrl_in_start_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_LEVEL_HIGH  ) ? ({start_trg_ff_bus,start_trg_bus} == 2'b01) : 
                               (ctrl_in_start_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_LEVEL_LOW   ) ? ({start_trg_ff_bus,start_trg_bus} == 2'b00) :
                               (ctrl_in_start_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_EDGE_FALLING) ? ({start_trg_ff_bus,start_trg_bus} == 2'b10) :
                               (ctrl_in_start_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_EDGE_RISING ) ? ({start_trg_ff_bus,start_trg_bus} == 2'b01) : 1'b0 );
        start_trg_tgl_bus   <= run_en & start_trg_en_bus & (
                               (ctrl_in_start_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_LEVEL_HIGH  ) ? ({start_trg_ff_bus,start_trg_bus} == 2'b01) ? ~start_trg_tgl_bus : start_trg_tgl_bus : 
                               (ctrl_in_start_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_LEVEL_LOW   ) ? ({start_trg_ff_bus,start_trg_bus} == 2'b00) ? ~start_trg_tgl_bus : start_trg_tgl_bus :
                               (ctrl_in_start_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_EDGE_FALLING) ? ({start_trg_ff_bus,start_trg_bus} == 2'b10) ? ~start_trg_tgl_bus : start_trg_tgl_bus :
                               (ctrl_in_start_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_EDGE_RISING ) ? ({start_trg_ff_bus,start_trg_bus} == 2'b01) ? ~start_trg_tgl_bus : start_trg_tgl_bus : 1'b0 );
        end
    end
    assign trg_start_en    = start_trg_en_bus;
    assign trg_start_pulse = start_trg_pulse_bus;
    assign trg_start_tgl   = start_trg_tgl_bus;

    // MUX stop trigger @ clk_bus
    reg stop_trg_bus = 1'b0;
    reg [1:0] stop_trg_en_ff_bus = 2'b00;
    always @ ( posedge clock_bus ) begin
        if ( reset_bus_n == 1'b0 ) begin
            stop_trg_bus       <= 1'b0;
            stop_trg_en_ff_bus <= 2'b00;
        end
        else begin
            stop_trg_bus          <= ( ctrl_in_stop_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_IN0     ) ? ext_in_bus[0] :
                                     ( ctrl_in_stop_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_IN1     ) ? ext_in_bus[1] :
                                     ( ctrl_in_stop_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_IN2     ) ? ext_in_bus[2] : 1'b0;
            stop_trg_en_ff_bus[0] <= ( ctrl_in_stop_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_IN0     ) ? 1'b1 :
                                     ( ctrl_in_stop_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_IN1     ) ? 1'b1 :
                                     ( ctrl_in_stop_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_IN2     ) ? 1'b1 : 1'b0;
            stop_trg_en_ff_bus[1] <= stop_trg_en_ff_bus[0];
        end
    end
    wire stop_trg_en_bus = & stop_trg_en_ff_bus; // delayed enable singal to avoid spike right after programming 
     
    // generate stop trigger positive edge pulse @ clk_bus
    reg stop_trg_ff_bus    = 1'b0;
    reg stop_trg_pulse_bus = 1'b0;
    reg stop_trg_tgl_bus   = 1'b0;
    always @ ( posedge clock_bus ) begin
        if (reset_bus_n == 1'b0) begin
            stop_trg_ff_bus    <= 1'b0;
            stop_trg_pulse_bus <= 1'b0;
            stop_trg_tgl_bus   <= 1'b0;
        end
        else begin
        stop_trg_ff_bus    <= (ctrl_in_stop_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_LEVEL_HIGH  ) ? run_en & stop_trg_en_bus & stop_trg_bus : 
                              (ctrl_in_stop_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_LEVEL_LOW   ) ? run_en & stop_trg_en_bus & ~stop_trg_bus :
                              (ctrl_in_stop_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_EDGE_FALLING) ? stop_trg_bus :
                              (ctrl_in_stop_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_EDGE_RISING ) ? stop_trg_bus : 1'b0;
        stop_trg_pulse_bus <= run_en & stop_trg_en_bus & (
                                (ctrl_in_stop_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_LEVEL_HIGH  ) ? ({stop_trg_ff_bus,stop_trg_bus} == 2'b01) : 
                                (ctrl_in_stop_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_LEVEL_LOW   ) ? ({stop_trg_ff_bus,stop_trg_bus} == 2'b00) :
                                (ctrl_in_stop_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_EDGE_FALLING) ? ({stop_trg_ff_bus,stop_trg_bus} == 2'b10) :
                                (ctrl_in_stop_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_EDGE_RISING ) ? ({stop_trg_ff_bus,stop_trg_bus} == 2'b01) : 1'b0 
                              ); 
        stop_trg_tgl_bus <= run_en & stop_trg_en_bus & (
                              (ctrl_in_stop_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_LEVEL_HIGH  ) ? ({stop_trg_ff_bus,stop_trg_bus} == 2'b01) ? ~stop_trg_tgl_bus : stop_trg_tgl_bus :  
                              (ctrl_in_stop_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_LEVEL_LOW   ) ? ({stop_trg_ff_bus,stop_trg_bus} == 2'b00) ? ~stop_trg_tgl_bus : stop_trg_tgl_bus :
                              (ctrl_in_stop_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_EDGE_FALLING) ? ({stop_trg_ff_bus,stop_trg_bus} == 2'b10) ? ~stop_trg_tgl_bus : stop_trg_tgl_bus :
                              (ctrl_in_stop_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_EDGE_RISING ) ? ({stop_trg_ff_bus,stop_trg_bus} == 2'b01) ? ~stop_trg_tgl_bus : stop_trg_tgl_bus : 1'b0 
                            ); 
        end
    end
    assign trg_stop_en    = stop_trg_en_bus;
    assign trg_stop_pulse = stop_trg_pulse_bus;
    assign trg_stop_tgl   = stop_trg_tgl_bus;

    // MUX restart trigger @ clk_bus
    reg restart_trg_bus = 1'b0;
    reg [1:0] restart_trg_en_ff_bus = 2'b00;
    always @ ( posedge clock_bus ) begin
        if ( reset_bus_n == 1'b0 ) begin
            restart_trg_bus       <= 1'b0;
            restart_trg_en_ff_bus <= 2'b00;
        end
        else begin
            restart_trg_bus          <= ( ctrl_in_restart_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_IN0 ) ? ext_in_bus[0] :
                                        ( ctrl_in_restart_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_IN1 ) ? ext_in_bus[1] :
                                        ( ctrl_in_restart_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_IN2 ) ? ext_in_bus[2] : 1'b0;
            restart_trg_en_ff_bus[0] <= ( ctrl_in_restart_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_IN0 ) ? 1'b1 :
                                        ( ctrl_in_restart_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_IN1 ) ? 1'b1 :
                                        ( ctrl_in_restart_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_IN2 ) ? 1'b1 : 1'b0;
            restart_trg_en_ff_bus[1] <= restart_trg_en_ff_bus[0];
        end
    end
    wire restart_trg_en_bus = & restart_trg_en_ff_bus; // delayed enable singal to avoid spike right after programming 
     
    // generate restart trigger positive edge pulse @ clk_bus
    reg restart_trg_ff_bus    = 1'b0;
    reg restart_trg_pulse_bus = 1'b0;
    reg restart_trg_tgl_bus   = 1'b0;
    always @ ( posedge clock_bus ) begin
        if (reset_bus_n == 1'b0) begin
            restart_trg_ff_bus    <= 1'b0;
            restart_trg_pulse_bus <= 1'b0;
            restart_trg_tgl_bus   <= 1'b0;
        end
        else begin
        restart_trg_ff_bus    <= (ctrl_in_restart_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_LEVEL_HIGH  ) ? run_en & restart_trg_en_bus & restart_trg_bus : 
                                 (ctrl_in_restart_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_LEVEL_LOW   ) ? run_en & restart_trg_en_bus & ~restart_trg_bus :
                                 (ctrl_in_restart_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_EDGE_FALLING) ? restart_trg_bus :
                                 (ctrl_in_restart_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_EDGE_RISING ) ? restart_trg_bus : 1'b0;
        restart_trg_pulse_bus <= run_en & restart_trg_en_bus & (
                                 (ctrl_in_restart_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_LEVEL_HIGH  ) ? ({restart_trg_ff_bus,restart_trg_bus} == 2'b01) : 
                                 (ctrl_in_restart_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_LEVEL_LOW   ) ? ({restart_trg_ff_bus,restart_trg_bus} == 2'b00) :
                                 (ctrl_in_restart_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_EDGE_FALLING) ? ({restart_trg_ff_bus,restart_trg_bus} == 2'b10) :
                                 (ctrl_in_restart_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_EDGE_RISING ) ? ({restart_trg_ff_bus,restart_trg_bus} == 2'b01) : 1'b0 
                                 );
        restart_trg_tgl_bus   <= run_en & restart_trg_en_bus & (
                                  (ctrl_in_restart_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_LEVEL_HIGH  ) ? ({restart_trg_ff_bus,restart_trg_bus} == 2'b01) ? ~restart_trg_tgl_bus : restart_trg_tgl_bus : 
                                  (ctrl_in_restart_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_LEVEL_LOW   ) ? ({restart_trg_ff_bus,restart_trg_bus} == 2'b00) ? ~restart_trg_tgl_bus : restart_trg_tgl_bus :
                                  (ctrl_in_restart_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_EDGE_FALLING) ? ({restart_trg_ff_bus,restart_trg_bus} == 2'b10) ? ~restart_trg_tgl_bus : restart_trg_tgl_bus :
                                  (ctrl_in_restart_bus[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_EDGE_RISING ) ? ({restart_trg_ff_bus,restart_trg_bus} == 2'b01) ? ~restart_trg_tgl_bus : restart_trg_tgl_bus : 1'b0 
                               );
        end
    end
    assign trg_restart_en    = restart_trg_en_bus;
    assign trg_restart_pulse = restart_trg_pulse_bus;
    assign trg_restart_tgl   = restart_trg_tgl_bus;    
    
	//////////////////////////////////////////////////////////////////////////////////
    // detection clock domain @ clock_det

    // assign control_trg register @ clk_bus
    wire [CTRL_IN_DST_BITS-1:0] ctrl_in_start_det   = ctrl_in0_det[CTRL_IN0_DST_START      +CTRL_IN_DST_BITS-1 -: CTRL_IN_DST_BITS];

    // synchronize external inputs @ clk_bus
    // note: there is no way to ensure that these bits are synchronized with each other!
    // so if they are even coming from the same source they might have 1 cycle difference!
    // this means that same sources must have alternate trigger edges to work properly.
    wire [NUM_EXT_IN - 1 : 0] ext_in_det;
    generate
    for (genvar i = 0; i < NUM_EXT_IN; i = i + 1) begin : GEN_EXT_DET
        (* ASYNC_REG = "TRUE" *)
        reg [SYNC-1:0] ext_in_det_cdc;
        always @ ( posedge clock_det ) begin
            ext_in_det_cdc <= {ext_in_det_cdc[SYNC-2:0],ext_in_none[i]};
        end
        assign ext_in_det[i] = ext_in_det_cdc[SYNC-1];
    end
    endgenerate

    // run_en CDC from clock_bus to clock_det
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] run_en_cdc_det;    
    always @ ( posedge clock_det ) begin
        run_en_cdc_det <= {run_en_cdc_det[SYNC-2:0],run_en};
    end
    wire run_en_det = run_en_cdc_det[SYNC-1];    

    // MUX start_in trigger @ clk_det
    reg start_trg_det = 1'b0;
    reg [1:0] start_trg_en_ff_det = 2'b00;
    always @ ( posedge clock_det ) begin
        if ( reset_det_n == 1'b0 ) begin
            start_trg_det       <= 1'b0;
            start_trg_en_ff_det <= 2'b00;
        end
        else begin
            start_trg_det          <= ( ctrl_in_start_det[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_IN0 ) ? ext_in_det[0] :
                                      ( ctrl_in_start_det[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_IN1 ) ? ext_in_det[1] :
                                      ( ctrl_in_start_det[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_IN2 ) ? ext_in_det[2] : 1'b0;
            start_trg_en_ff_det[0] <= ( ctrl_in_start_det[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_IN0 ) ? 1'b1 :
                                      ( ctrl_in_start_det[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_IN1 ) ? 1'b1 :
                                      ( ctrl_in_start_det[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_IN2 ) ? 1'b1 : 1'b0;
            start_trg_en_ff_det[1] <= start_trg_en_ff_det[0];
        end
    end
    wire start_trg_en_det = & start_trg_en_ff_det; // delayed enable singal to avoid spike right after programming 

         
    // generate start_trg positive edge pulse @ clk_det
    reg start_trg_ff_det = 1'b0;
    //reg start_trg_pulse_det = 1'b0;
    reg start_trg_tgl_det = 1'b0;
    always @ ( posedge clock_det ) begin
        if (reset_det_n == 1'b0) begin
            start_trg_ff_det    <= 1'b0;
            //start_trg_pulse_det <= 1'b0;
            start_trg_tgl_det   <= 1'b0;
        end
        else begin
        start_trg_ff_det    <= (ctrl_in_start_det[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_LEVEL_HIGH  ) ? run_en_det & start_trg_en_det & start_trg_det : 
                               (ctrl_in_start_det[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_LEVEL_LOW   ) ? run_en_det & start_trg_en_det & ~start_trg_det :
                               (ctrl_in_start_det[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_EDGE_FALLING) ? start_trg_det :
                               (ctrl_in_start_det[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_EDGE_RISING ) ? start_trg_det : 1'b0;
        /*start_trg_pulse_det <= run_en_det & start_trg_en_det & (
                               (ctrl_in_start_det[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_LEVEL_HIGH  ) ? ({start_trg_ff_det,start_trg_det} == 2'b01) : 
                               (ctrl_in_start_det[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_LEVEL_LOW   ) ? ({start_trg_ff_det,start_trg_det} == 2'b00) :
                               (ctrl_in_start_det[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_EDGE_FALLING) ? ({start_trg_ff_det,start_trg_det} == 2'b10) :
                               (ctrl_in_start_det[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_EDGE_RISING ) ? ({start_trg_ff_det,start_trg_det} == 2'b01) : 1'b0 );
        */
        start_trg_tgl_det   <= run_en_det & start_trg_en_det & (
                               (ctrl_in_start_det[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_LEVEL_HIGH  ) ? ({start_trg_ff_det,start_trg_det} == 2'b01) ? ~start_trg_tgl_det : start_trg_tgl_det : 
                               (ctrl_in_start_det[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_LEVEL_LOW   ) ? ({start_trg_ff_det,start_trg_det} == 2'b00) ? ~start_trg_tgl_det : start_trg_tgl_det :
                               (ctrl_in_start_det[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_EDGE_FALLING) ? ({start_trg_ff_det,start_trg_det} == 2'b10) ? ~start_trg_tgl_det : start_trg_tgl_det :
                               (ctrl_in_start_det[CTRL_IN_DST_BITS-1 -: CTRL_IN_LEVEL_BITS] == CTRL_IN_EDGE_RISING ) ? ({start_trg_ff_det,start_trg_det} == 2'b01) ? ~start_trg_tgl_det : start_trg_tgl_det : 1'b0 );
        end
    end
    //assign trg_restart_en_det    = start_trg_en_det;
    //assign trg_restart_pulse_det = start_trg_pulse_det;
    assign trg_start_tgl_det     = start_trg_tgl_det;
    
	//////////////////////////////////////////////////////////////////////////////////
    // special data bits @ clk_bus

    // input control enable bits
    reg data_stop_en_ff  = 1'b0;
    reg data_nop_en_ff   = 1'b0;
    reg data_strb0_en_ff = 1'b0;
    reg data_strb1_en_ff = 1'b0;
    reg data_irq_en_ff   = 1'b0;
    always @ ( posedge clock_bus ) begin
        if ( reset_bus_n == 1'b0 ) begin
            data_stop_en_ff  <= 1'b0;
            data_nop_en_ff   <= 1'b0;
            data_strb0_en_ff <= 1'b0;
            data_strb1_en_ff <= 1'b0;
            data_irq_en_ff   <= 1'b0;
        end
        else begin
            data_stop_en_ff  <= (ctrl_in_stop_bus [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_20) ? 1'b1 :
                                (ctrl_in_stop_bus [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_24) ? 1'b1 :
                                (ctrl_in_stop_bus [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_28) ? 1'b1 : 1'b0;
            data_nop_en_ff   <= (ctrl_in_nop_bus  [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_20) ? 1'b1 :
                                (ctrl_in_nop_bus  [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_24) ? 1'b1 :
                                (ctrl_in_nop_bus  [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_28) ? 1'b1 : 1'b0;
            data_strb0_en_ff <= (ctrl_in_strb0_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_20) ? 1'b1 :
                                (ctrl_in_strb0_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_24) ? 1'b1 :
                                (ctrl_in_strb0_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_28) ? 1'b1 : 1'b0;
            data_strb1_en_ff <= (ctrl_in_strb1_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_20) ? 1'b1 :
                                (ctrl_in_strb1_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_24) ? 1'b1 :
                                (ctrl_in_strb1_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_28) ? 1'b1 : 1'b0;
            data_irq_en_ff   <= (ctrl_in_irq_bus  [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_20) ? 1'b1 :
                                (ctrl_in_irq_bus  [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_24) ? 1'b1 :
                                (ctrl_in_irq_bus  [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_28) ? 1'b1 : 1'b0;
        end
    end
    
    // input data multiplexer and pipeline
    reg [IN_DATA_BUF-1:0] data_stop_ff = {(IN_DATA_BUF){1'b0}};
    reg [IN_DATA_BUF-1:0] data_nop_ff  = {(IN_DATA_BUF){1'b0}};
    reg [IN_DATA_BUF-1:0] data_irq_ff  = {(IN_DATA_BUF){1'b0}};
    reg [1:0] data_strb0_ff = 2'b00;
    reg [1:0] data_strb1_ff = 2'b00;
    reg [IN_DATA_BUF-1:1] data_strb0_nop_ff = {(IN_DATA_BUF-1){1'b0}};
    reg [IN_DATA_BUF-1:1] data_strb1_nop_ff = {(IN_DATA_BUF-1){1'b0}};
    integer i;
    always @ ( posedge clock_bus ) begin
        if ( reset_bus_n == 1'b0 ) begin
            data_nop_ff   <= {(IN_DATA_BUF){1'b0}};
            data_stop_ff  <= {(IN_DATA_BUF){1'b0}};
            data_irq_ff   <= {(IN_DATA_BUF){1'b0}};
            data_strb0_ff <= 1'b0;
            data_strb1_ff <= 1'b0;
        end
        else begin
            data_nop_ff[0]  <= data_reload ? (
                            (ctrl_in_nop_bus [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_20) & (ctrl_in_nop_bus [CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_0) ? data[20] :
                            (ctrl_in_nop_bus [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_20) & (ctrl_in_nop_bus [CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_1) ? data[21] :
                            (ctrl_in_nop_bus [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_20) & (ctrl_in_nop_bus [CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_2) ? data[22] :
                            (ctrl_in_nop_bus [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_20) & (ctrl_in_nop_bus [CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_3) ? data[23] :
                            (ctrl_in_nop_bus [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_24) & (ctrl_in_nop_bus [CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_0) ? data[24] :
                            (ctrl_in_nop_bus [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_24) & (ctrl_in_nop_bus [CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_1) ? data[25] :
                            (ctrl_in_nop_bus [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_24) & (ctrl_in_nop_bus [CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_2) ? data[26] :
                            (ctrl_in_nop_bus [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_24) & (ctrl_in_nop_bus [CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_3) ? data[27] :
                            (ctrl_in_nop_bus [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_28) & (ctrl_in_nop_bus [CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_0) ? data[28] :
                            (ctrl_in_nop_bus [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_28) & (ctrl_in_nop_bus [CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_1) ? data[29] :
                            (ctrl_in_nop_bus [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_28) & (ctrl_in_nop_bus [CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_2) ? data[30] :
                            (ctrl_in_nop_bus [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_28) & (ctrl_in_nop_bus [CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_3) ? data[31] : 1'b0 )
                            : data_nop_ff[0];
            data_stop_ff[0] <= data_reload ? (
                            (ctrl_in_stop_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_20) & (ctrl_in_stop_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_0) ? data[20] :
                            (ctrl_in_stop_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_20) & (ctrl_in_stop_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_1) ? data[21] :
                            (ctrl_in_stop_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_20) & (ctrl_in_stop_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_2) ? data[22] :
                            (ctrl_in_stop_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_20) & (ctrl_in_stop_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_3) ? data[23] :
                            (ctrl_in_stop_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_24) & (ctrl_in_stop_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_0) ? data[24] :
                            (ctrl_in_stop_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_24) & (ctrl_in_stop_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_1) ? data[25] :
                            (ctrl_in_stop_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_24) & (ctrl_in_stop_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_2) ? data[26] :
                            (ctrl_in_stop_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_24) & (ctrl_in_stop_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_3) ? data[27] :
                            (ctrl_in_stop_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_28) & (ctrl_in_stop_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_0) ? data[28] :
                            (ctrl_in_stop_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_28) & (ctrl_in_stop_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_1) ? data[29] :
                            (ctrl_in_stop_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_28) & (ctrl_in_stop_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_2) ? data[30] :
                            (ctrl_in_stop_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_28) & (ctrl_in_stop_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_3) ? data[31] : 1'b0 ) 
                            : data_stop_ff[0];                            
            data_irq_ff[0]  <= data_reload ? (
                            (ctrl_in_irq_bus [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_20) & (ctrl_in_irq_bus [CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_0) ? data[20] :
                            (ctrl_in_irq_bus [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_20) & (ctrl_in_irq_bus [CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_1) ? data[21] :
                            (ctrl_in_irq_bus [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_20) & (ctrl_in_irq_bus [CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_2) ? data[22] :
                            (ctrl_in_irq_bus [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_20) & (ctrl_in_irq_bus [CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_3) ? data[23] :
                            (ctrl_in_irq_bus [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_24) & (ctrl_in_irq_bus [CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_0) ? data[24] :
                            (ctrl_in_irq_bus [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_24) & (ctrl_in_irq_bus [CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_1) ? data[25] :
                            (ctrl_in_irq_bus [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_24) & (ctrl_in_irq_bus [CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_2) ? data[26] :
                            (ctrl_in_irq_bus [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_24) & (ctrl_in_irq_bus [CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_3) ? data[27] :
                            (ctrl_in_irq_bus [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_28) & (ctrl_in_irq_bus [CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_0) ? data[28] :
                            (ctrl_in_irq_bus [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_28) & (ctrl_in_irq_bus [CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_1) ? data[29] :
                            (ctrl_in_irq_bus [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_28) & (ctrl_in_irq_bus [CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_2) ? data[30] :
                            (ctrl_in_irq_bus [CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_28) & (ctrl_in_irq_bus [CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_3) ? data[31] : 1'b0 )
                            : data_irq_ff[0];
            data_strb0_ff[0] <= data_reload ? (
                            (ctrl_in_strb0_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_20) & (ctrl_in_strb0_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_0) ? data[20] :
                            (ctrl_in_strb0_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_20) & (ctrl_in_strb0_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_1) ? data[21] :
                            (ctrl_in_strb0_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_20) & (ctrl_in_strb0_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_2) ? data[22] :
                            (ctrl_in_strb0_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_20) & (ctrl_in_strb0_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_3) ? data[23] :
                            (ctrl_in_strb0_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_24) & (ctrl_in_strb0_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_0) ? data[24] :
                            (ctrl_in_strb0_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_24) & (ctrl_in_strb0_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_1) ? data[25] :
                            (ctrl_in_strb0_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_24) & (ctrl_in_strb0_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_2) ? data[26] :
                            (ctrl_in_strb0_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_24) & (ctrl_in_strb0_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_3) ? data[27] :
                            (ctrl_in_strb0_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_28) & (ctrl_in_strb0_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_0) ? data[28] :
                            (ctrl_in_strb0_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_28) & (ctrl_in_strb0_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_1) ? data[29] :
                            (ctrl_in_strb0_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_28) & (ctrl_in_strb0_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_2) ? data[30] :
                            (ctrl_in_strb0_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_28) & (ctrl_in_strb0_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_3) ? data[31] : 1'b0 )
                            : data_strb0_ff[0];
            data_strb1_ff[0] <= data_reload ? (
                            (ctrl_in_strb1_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_20) & (ctrl_in_strb1_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_0) ? data[20] :
                            (ctrl_in_strb1_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_20) & (ctrl_in_strb1_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_1) ? data[21] :
                            (ctrl_in_strb1_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_20) & (ctrl_in_strb1_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_2) ? data[22] :
                            (ctrl_in_strb1_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_20) & (ctrl_in_strb1_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_3) ? data[23] :
                            (ctrl_in_strb1_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_24) & (ctrl_in_strb1_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_0) ? data[24] :
                            (ctrl_in_strb1_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_24) & (ctrl_in_strb1_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_1) ? data[25] :
                            (ctrl_in_strb1_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_24) & (ctrl_in_strb1_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_2) ? data[26] :
                            (ctrl_in_strb1_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_24) & (ctrl_in_strb1_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_3) ? data[27] :
                            (ctrl_in_strb1_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_28) & (ctrl_in_strb1_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_0) ? data[28] :
                            (ctrl_in_strb1_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_28) & (ctrl_in_strb1_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_1) ? data[29] :
                            (ctrl_in_strb1_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_28) & (ctrl_in_strb1_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_2) ? data[30] :
                            (ctrl_in_strb1_bus[CTRL_IN_SRC_BITS-1:0] == CTRL_IN_SRC_DATA_28) & (ctrl_in_strb1_bus[CTRL_IN_DST_BITS-1-:CTRL_IN_LEVEL_BITS] == CTRL_IN_DATA_3) ? data[31] : 1'b0 )
                            : data_strb1_ff[0];
            for (i=1; i < IN_DATA_BUF; i=i+1) begin
                data_nop_ff [i] <= data_reload ? data_nop_ff [i-1] : data_nop_ff [i];
                data_stop_ff[i] <= data_reload ? data_stop_ff[i-1] : data_stop_ff[i];
                data_irq_ff [i] <= data_reload ? data_irq_ff [i-1] : data_irq_ff [i];
            end
            // data_strb_nop is high when strobe bit is not toggling
            data_strb0_ff[1]     <= data_reload ? data_strb0_ff[0] : data_strb0_ff[1];
            data_strb1_ff[1]     <= data_reload ? data_strb1_ff[0] : data_strb1_ff[1];
            data_strb0_nop_ff[1] <= data_reload ? in_valid & ~(data_strb0_ff[0] ^ data_strb0_ff[1]) : data_strb0_nop_ff[1];
            data_strb1_nop_ff[1] <= data_reload ? in_valid & ~(data_strb1_ff[0] ^ data_strb1_ff[1]) : data_strb1_nop_ff[1];
            if ( IN_DATA_BUF > 2 ) begin
                for (i=2; i<IN_DATA_BUF; i=i+1) begin
                    data_strb0_nop_ff[i] <= data_reload ? data_strb0_nop_ff[i-1] : data_strb0_nop_ff[i];
                    data_strb1_nop_ff[i] <= data_reload ? data_strb1_nop_ff[i-1] : data_strb1_nop_ff[i];
                end
            end
        end
    end
    
    // assign output data bits
    assign data_stop_en     = data_stop_en_ff;
    assign data_nop_en      = data_nop_en_ff;
    assign data_irq_en      = data_irq_en_ff;
    assign data_strb_en[0]  = data_strb0_en_ff;
    assign data_strb_en[1]  = data_strb1_en_ff;
    assign data_stop        = data_stop_ff[IN_DATA_BUF-1];
    assign data_nop         = data_nop_ff[IN_DATA_BUF-1];
    assign data_irq         = data_irq_ff[IN_DATA_BUF-1];
    assign data_strb_nop[0] = data_strb0_nop_ff[IN_DATA_BUF-1];
    assign data_strb_nop[1] = data_strb1_nop_ff[IN_DATA_BUF-1];
            

endmodule
