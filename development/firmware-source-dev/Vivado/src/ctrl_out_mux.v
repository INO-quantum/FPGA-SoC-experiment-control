`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// control_out_mux.v 
// multiplexer for control out registers
// created 06/05/2023 by Andi
// last change 3/12/2024 by Andi
//////////////////////////////////////////////////////////////////////////////////

module ctrl_out_mux (
    // clock and reset
    clock,
    reset_n,
    // control register
    ctrl_out0,
    ctrl_out1,
    // input sources
    sync_out,
    sync_en,
    sync_mon,
    clk_ext_locked,
    clk_ext_sel,
    clk_ext_lost,
    error,
    status_ready,
    status_run,
    status_wait,
    status_end,
    status_restart,
    trg_start,
    trg_stop,
    trg_restart,
    strb,
    strb_cont,
    irq_TX,
    irq_RX,
    irq_FPGA,
    TX_full,
    TX_empty,
    RX_full,
    RX_empty,
    // input data
    //input wire [REG_WIDTH-1:0] data,
    // multiplexed outputs
    out,
    bus_en,
    led
);

    //////////////////////////////////////////////////////////////////////////////////
    // parameters

    `include "ctrl_out_params.vh"
    
    // regiser data width must be 32
    parameter integer REG_WIDTH                 = 32;
    // number of outputs. max. 3
    parameter integer NUM_OUT                   = 3;
    // number of LEDS. max. 3
    parameter integer NUM_LED                   = 3;
    // number of bus_en. max 2
    parameter integer NUM_BUS_EN                = 2;
    // number of strobe inputs. max. 2
    parameter integer NUM_STRB                  = 2;

    //////////////////////////////////////////////////////////////////////////////////
    // ports

    // clock and reset
    input wire clock;
    input wire reset_n;
    // control register
    input wire [REG_WIDTH-1:0] ctrl_out0;
    input wire [REG_WIDTH-1:0] ctrl_out1;
    // input sources
    input wire sync_out;
    input wire sync_en;
    input wire sync_mon;
    input wire clk_ext_locked;
    input wire clk_ext_sel;
    input wire clk_ext_lost;
    input wire error;
    input wire status_ready;
    input wire status_run;
    input wire status_wait;
    input wire status_end;
    input wire status_restart;
    input wire trg_start;
    input wire trg_stop;
    input wire trg_restart;
    input wire [NUM_STRB-1:0] strb;
    input wire [NUM_STRB-1:0] strb_cont;
    input wire irq_TX;
    input wire irq_RX;
    input wire irq_FPGA;
    input wire TX_full;
    input wire TX_empty;
    input wire RX_full;
    input wire RX_empty;    
    // input data
    //input wire [REG_WIDTH-1:0] data;
    // multiplexed outputs
    output wire [NUM_OUT-1   :0] out;
    output wire [NUM_BUS_EN-1:0] bus_en;
    output wire [NUM_LED-1   :0] led;
    
    //////////////////////////////////////////////////////////////////////////////////
    
    wire [CTRL_OUT_SRC_BITS-1:0] ctrl_out_0   = ctrl_out0[CTRL_OUT0_DST_OUT0    *CTRL_OUT_SRC_BITS +: CTRL_OUT_SRC_BITS];
    wire [CTRL_OUT_SRC_BITS-1:0] ctrl_out_1   = ctrl_out0[CTRL_OUT0_DST_OUT1    *CTRL_OUT_SRC_BITS +: CTRL_OUT_SRC_BITS];
    wire [CTRL_OUT_SRC_BITS-1:0] ctrl_out_2   = ctrl_out0[CTRL_OUT0_DST_OUT2    *CTRL_OUT_SRC_BITS +: CTRL_OUT_SRC_BITS];
    wire [CTRL_OUT_SRC_BITS-1:0] ctrl_bus_en0 = ctrl_out0[CTRL_OUT0_DST_BUS_EN_0*CTRL_OUT_SRC_BITS +: CTRL_OUT_SRC_BITS];
    wire [CTRL_OUT_SRC_BITS-1:0] ctrl_bus_en1 = ctrl_out0[CTRL_OUT0_DST_BUS_EN_1*CTRL_OUT_SRC_BITS +: CTRL_OUT_SRC_BITS];
    wire [CTRL_OUT_SRC_BITS-1:0] ctrl_led_r   = ctrl_out1[CTRL_OUT1_DST_LED_R   *CTRL_OUT_SRC_BITS +: CTRL_OUT_SRC_BITS];
    wire [CTRL_OUT_SRC_BITS-1:0] ctrl_led_g   = ctrl_out1[CTRL_OUT1_DST_LED_G   *CTRL_OUT_SRC_BITS +: CTRL_OUT_SRC_BITS];
    wire [CTRL_OUT_SRC_BITS-1:0] ctrl_led_b   = ctrl_out1[CTRL_OUT1_DST_LED_B   *CTRL_OUT_SRC_BITS +: CTRL_OUT_SRC_BITS];

    // source bits for each source and level
    localparam integer NUM_SRC = (1<<CTRL_OUT_SRC_BITS);    // number of input sources
    wire [NUM_SRC-1:0] src;
    assign src  [CTRL_OUT_SRC_FIXED_LOW        ] = 1'b0;
    assign src  [CTRL_OUT_SRC_FIXED_HIGH       ] = 1'b1;
    assign src  [CTRL_OUT_SRC_SYNC_OUT         ] =  sync_out;
    assign src  [CTRL_OUT_SRC_SYNC_OUT_INV     ] = ~sync_out;
    assign src  [CTRL_OUT_SRC_SYNC_EN          ] =  sync_en;
    assign src  [CTRL_OUT_SRC_SYNC_EN_INV      ] = ~sync_en;
    assign src  [CTRL_OUT_SRC_SYNC_MON         ] =  sync_mon;
    assign src  [CTRL_OUT_SRC_SYNC_MON_INV     ] = ~sync_mon;
    assign src  [CTRL_OUT_SRC_CLK_LOCKED       ] =  clk_ext_locked;
    assign src  [CTRL_OUT_SRC_CLK_LOCKED_INV   ] = ~clk_ext_locked;
    assign src  [CTRL_OUT_SRC_CLK_SEL          ] =  clk_ext_sel;
    assign src  [CTRL_OUT_SRC_CLK_SEL_INV      ] = ~clk_ext_sel;
    assign src  [CTRL_OUT_SRC_CLK_LOST         ] =  clk_ext_lost;
    assign src  [CTRL_OUT_SRC_CLK_LOST_INV     ] = ~clk_ext_lost;
    assign src  [CTRL_OUT_SRC_ERROR            ] =  error;
    assign src  [CTRL_OUT_SRC_ERROR_INV        ] = ~error;
    assign src  [CTRL_OUT_SRC_RUN              ] =  status_run;
    assign src  [CTRL_OUT_SRC_RUN_INV          ] = ~status_run;
    assign src  [CTRL_OUT_SRC_WAIT             ] =  status_wait;
    assign src  [CTRL_OUT_SRC_WAIT_INV         ] = ~status_wait;
    assign src  [CTRL_OUT_SRC_END              ] =  status_end;
    assign src  [CTRL_OUT_SRC_END_INV          ] = ~status_end;
    assign src  [CTRL_OUT_SRC_READY            ] =  status_ready;
    assign src  [CTRL_OUT_SRC_READY_INV        ] = ~status_ready;
    assign src  [CTRL_OUT_SRC_RESTART          ] =  status_restart;
    assign src  [CTRL_OUT_SRC_RESTART_INV      ] = ~status_restart;
    assign src  [CTRL_OUT_SRC_TRG_START        ] =  trg_start;
    assign src  [CTRL_OUT_SRC_TRG_START_INV    ] = ~trg_start;
    assign src  [CTRL_OUT_SRC_TRG_STOP         ] =  trg_stop;
    assign src  [CTRL_OUT_SRC_TRG_STOP_INV     ] = ~trg_stop;
    assign src  [CTRL_OUT_SRC_TRG_RESTART      ] =  trg_restart;
    assign src  [CTRL_OUT_SRC_TRG_RESTART_INV  ] = ~trg_restart;

    // irq's
    assign src  [CTRL_OUT_SRC_IRQ_TX           ] = irq_TX;
    assign src  [CTRL_OUT_SRC_IRQ_TX_INV       ] = ~irq_TX;
    assign src  [CTRL_OUT_SRC_IRQ_RX           ] = irq_RX;
    assign src  [CTRL_OUT_SRC_IRQ_RX_INV       ] = ~irq_RX;
    assign src  [CTRL_OUT_SRC_IRQ_FPGA         ] = irq_FPGA;
    assign src  [CTRL_OUT_SRC_IRQ_FPGA_INV     ] = ~irq_FPGA;

    // TX/RX FIFO full/empty 
    assign src  [CTRL_OUT_SRC_TX_FULL          ] = TX_full;
    assign src  [CTRL_OUT_SRC_TX_FULL_INV      ] = ~TX_full;
    assign src  [CTRL_OUT_SRC_TX_EMPTY         ] = TX_empty;
    assign src  [CTRL_OUT_SRC_TX_EMPTY_INV     ] = ~TX_empty;
    assign src  [CTRL_OUT_SRC_RX_FULL          ] = RX_full;
    assign src  [CTRL_OUT_SRC_RX_FULL_INV      ] = ~RX_full;
    assign src  [CTRL_OUT_SRC_RX_EMPTY         ] = RX_empty;
    assign src  [CTRL_OUT_SRC_RX_EMPTY_INV     ] = ~RX_empty;

    if (NUM_STRB >= 1) begin
        assign src  [CTRL_OUT_SRC_STRB0            ] =  strb[0];
        assign src  [CTRL_OUT_SRC_STRB0_INV        ] = ~strb[0];
        assign src  [CTRL_OUT_SRC_STRB0_CONT       ] =  strb_cont[0];
        assign src  [CTRL_OUT_SRC_STRB0_CONT_INV   ] = ~strb_cont[0];
    end
    else begin
        assign src  [CTRL_OUT_SRC_STRB0            ] = 1'b0;
        assign src  [CTRL_OUT_SRC_STRB0_INV        ] = 1'b0;
        assign src  [CTRL_OUT_SRC_STRB0_CONT       ] = 1'b0;
        assign src  [CTRL_OUT_SRC_STRB0_CONT_INV   ] = 1'b0;
    end
    if (NUM_STRB >= 2) begin
        assign src  [CTRL_OUT_SRC_STRB1            ] =  strb[1];
        assign src  [CTRL_OUT_SRC_STRB1_INV        ] = ~strb[1];
        assign src  [CTRL_OUT_SRC_STRB1_CONT       ] =  strb_cont[1];
        assign src  [CTRL_OUT_SRC_STRB1_CONT_INV   ] = ~strb_cont[1];
    end
    else begin
        assign src  [CTRL_OUT_SRC_STRB1            ] = 1'b0;
        assign src  [CTRL_OUT_SRC_STRB1_INV        ] = 1'b0;
        assign src  [CTRL_OUT_SRC_STRB1_CONT       ] = 1'b0;
        assign src  [CTRL_OUT_SRC_STRB1_CONT_INV   ] = 1'b0;
    end
    
    // unused
    assign src [CTRL_OUT_SRC_UNUSED_54] = 1'b0;
    assign src [CTRL_OUT_SRC_UNUSED_55] = 1'b0;
    assign src [CTRL_OUT_SRC_UNUSED_56] = 1'b0;
    assign src [CTRL_OUT_SRC_UNUSED_57] = 1'b0;
    assign src [CTRL_OUT_SRC_UNUSED_58] = 1'b0;
    assign src [CTRL_OUT_SRC_UNUSED_59] = 1'b0;
    assign src [CTRL_OUT_SRC_UNUSED_60] = 1'b0;
    assign src [CTRL_OUT_SRC_UNUSED_61] = 1'b0;
    assign src [CTRL_OUT_SRC_UNUSED_62] = 1'b0;
    assign src [CTRL_OUT_SRC_UNUSED_63] = 1'b0;
    
    if (NUM_OUT >= 1) begin
        mux_64_to_1 # (
            .BUFFER_OUT     (1),
            .BUFFER_MUX16   (1)
            )
        mux_out0 (
            .clk        (clock),
            .ctrl       (ctrl_out_0),
            .in         (src),
            .out        (out[0])
        );
    end

    if (NUM_OUT >= 2) begin
        mux_64_to_1 # (
            .BUFFER_OUT     (1),
            .BUFFER_MUX16   (1)
            )
        mux_out1 (
            .clk        (clock),
            .ctrl       (ctrl_out_1),
            .in         (src),
            .out        (out[1])
        );
    end

    if (NUM_OUT >= 3) begin
        mux_64_to_1 # (
            .BUFFER_OUT     (1),
            .BUFFER_MUX16   (1)
            )
        mux_out2 (
            .clk        (clock),
            .ctrl       (ctrl_out_2),        
            .in         (src),
            .out        (out[2])
        );
    end
    
    if (NUM_BUS_EN >= 1) begin
        wire bus_en_0_w;
        mux_2_to_1 
        mux_bus_en_0 (
            .ctrl       (ctrl_bus_en0[0]),
            .in         (src[2-1:0]),
            .en         (ctrl_bus_en0[CTRL_OUT_SRC_BITS-1:1]=={(CTRL_OUT_SRC_BITS-1){1'b0}}),
            .out        (bus_en0_w)
        );
        // mux output register
        reg bus_en0_ff = 1'b0;
        always @ (posedge clock) begin
            bus_en0_ff <= bus_en0_w;
        end
        assign bus_en[0] = bus_en0_ff;
    end
    
    if (NUM_BUS_EN >= 2) begin
        wire bus_en1_w;
        mux_2_to_1 
        mux_bus_en_1 (
            .ctrl       (ctrl_bus_en1[0]),
            .in         (src[2-1:0]),
            .en         (ctrl_bus_en1[CTRL_OUT_SRC_BITS-1:1]=={(CTRL_OUT_SRC_BITS-1){1'b0}}),
            .out        (bus_en1_w)
        );
        // mux output register
        reg bus_en1_ff = 1'b0;
        always @ (posedge clock) begin
            bus_en1_ff <= bus_en1_w;
        end
        assign bus_en[1] = bus_en1_ff;
    end

    if (NUM_LED >= 1) begin
        mux_64_to_1 # (
            .BUFFER_OUT     (1),
            .BUFFER_MUX16   (1)
            )
        mux_led_r (
            .clk        (clock),
            .ctrl       (ctrl_led_r),
            .in         (src),
            .out        (led[0])
        );
    end
    
    if (NUM_LED >= 2) begin
        mux_64_to_1 # (
            .BUFFER_OUT     (1),
            .BUFFER_MUX16   (1)
            )
        mux_led_g (
            .clk        (clock),
            .ctrl       (ctrl_led_g),
            .in         (src),
            .out        (led[1])
        );
    end

    if (NUM_LED >= 3) begin
        mux_64_to_1 # (
            .BUFFER_OUT     (1),
            .BUFFER_MUX16   (1)
            )
        mux_led_b (
            .clk        (clock),
            .ctrl       (ctrl_led_b),
            .in         (src),
            .out        (led[2])
        );
    end

endmodule
