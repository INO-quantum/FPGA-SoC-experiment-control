// ctrl_out_params.vh
// output source and destinations for ctrl_out_mux.v module
// created 5/10/2024 by Andi
// last change 3/12/2024 by Andi

    // output control register
    parameter integer CTRL_OUT_SRC_BITS             = 6;

    // output destinations offsets (max. floor(32/CTRL_OUT_SRC_BITS) = 5 possible per register)
    // register 0
    parameter integer CTRL_OUT0_DST_OUT0            = 0;    // out[0]
    parameter integer CTRL_OUT0_DST_OUT1            = 1;    // out[1]
    parameter integer CTRL_OUT0_DST_OUT2            = 2;    // out[2]
    parameter integer CTRL_OUT0_DST_BUS_EN_0        = 3;    // bus_en[0]
    parameter integer CTRL_OUT0_DST_BUS_EN_1        = 4;    // bus_en[1]
    // register 1
    parameter integer CTRL_OUT1_DST_LED_R           = 0;    // buffer board red   = led[0]
    parameter integer CTRL_OUT1_DST_LED_G           = 1;    // buffer board green = led[1]
    parameter integer CTRL_OUT1_DST_LED_B           = 2;    // buffer board blue  = led[2]
    parameter integer CTRL_OUT1_DST_NONE_3          = 3;    // unused
    parameter integer CTRL_OUT1_DST_NONE_4          = 4;    // unused

    // output sources (max. 2^CTRL_OUT_SRC_BITS = 64 possible)
    parameter integer CTRL_OUT_SRC_FIXED_LOW        = 0;    // fixed output low level
    parameter integer CTRL_OUT_SRC_FIXED_HIGH       = 1;    // fixed output high level
    parameter integer CTRL_OUT_SRC_SYNC_OUT         = 2;    // sync_out
    parameter integer CTRL_OUT_SRC_SYNC_OUT_INV     = 3;    // sync_out inverted
    parameter integer CTRL_OUT_SRC_SYNC_EN          = 4;    // sync_en (used for debugging)
    parameter integer CTRL_OUT_SRC_SYNC_EN_INV      = 5;    // sync_en inverted (used for debugging)
    parameter integer CTRL_OUT_SRC_SYNC_MON         = 6;    // sync_mon (used for debugging)
    parameter integer CTRL_OUT_SRC_SYNC_MON_INV     = 7;    // sync_mon inverted (used for debugging)
    parameter integer CTRL_OUT_SRC_CLK_LOCKED       = 8;    // external clock locked
    parameter integer CTRL_OUT_SRC_CLK_LOCKED_INV   = 9;    // external clock locked inverted
    parameter integer CTRL_OUT_SRC_CLK_SEL          = 10;   // external clock selected
    parameter integer CTRL_OUT_SRC_CLK_SEL_INV      = 11;   // external clock selected inverted
    parameter integer CTRL_OUT_SRC_CLK_LOST         = 12;   // external clock lost
    parameter integer CTRL_OUT_SRC_CLK_LOST_INV     = 13;   // external clock lost inverted
    parameter integer CTRL_OUT_SRC_ERROR            = 14;   // error
    parameter integer CTRL_OUT_SRC_ERROR_INV        = 15;   // error inverted
    parameter integer CTRL_OUT_SRC_READY            = 16;   // ready (data in FIFO)
    parameter integer CTRL_OUT_SRC_READY_INV        = 17;   // ready (data in FIFO) inverted
    parameter integer CTRL_OUT_SRC_RUN              = 18;   // run (or wait)
    parameter integer CTRL_OUT_SRC_RUN_INV          = 19;   // run (or wait) inverted
    parameter integer CTRL_OUT_SRC_WAIT             = 20;   // wait
    parameter integer CTRL_OUT_SRC_WAIT_INV         = 21;   // wait inverted
    parameter integer CTRL_OUT_SRC_END              = 22;   // end
    parameter integer CTRL_OUT_SRC_END_INV          = 23;   // end inverted
    parameter integer CTRL_OUT_SRC_RESTART          = 24;   // restart (toggle bit)
    parameter integer CTRL_OUT_SRC_RESTART_INV      = 25;   // restart (toogle bit) inverted
    parameter integer CTRL_OUT_SRC_TRG_START        = 26;   // start trigger (toggle bit)
    parameter integer CTRL_OUT_SRC_TRG_START_INV    = 27;   // start trigger (toggle bit) inverted
    parameter integer CTRL_OUT_SRC_TRG_STOP         = 28;   // stop trigger (toggle bit)
    parameter integer CTRL_OUT_SRC_TRG_STOP_INV     = 29;   // stop trigger (toggle bit) inverted
    parameter integer CTRL_OUT_SRC_TRG_RESTART      = 30;   // restart trigger (toggle bit)
    parameter integer CTRL_OUT_SRC_TRG_RESTART_INV  = 31;   // restart trigger (toggle bit) inverted
    parameter integer CTRL_OUT_SRC_STRB0            = 32;   // strobe0 
    parameter integer CTRL_OUT_SRC_STRB0_INV        = 33;   // strobe0 inverted
    parameter integer CTRL_OUT_SRC_STRB0_CONT       = 34;   // strobe0 contiguous 
    parameter integer CTRL_OUT_SRC_STRB0_CONT_INV   = 35;   // strobe0 contiguous inverted
    parameter integer CTRL_OUT_SRC_STRB1            = 36;   // strobe1 
    parameter integer CTRL_OUT_SRC_STRB1_INV        = 37;   // strobe1 inverted
    parameter integer CTRL_OUT_SRC_STRB1_CONT       = 38;   // strobe1 contiguous 
    parameter integer CTRL_OUT_SRC_STRB1_CONT_INV   = 39;   // strobe1 contiguous inverted
    parameter integer CTRL_OUT_SRC_IRQ_TX           = 40;   // TX irq
    parameter integer CTRL_OUT_SRC_IRQ_TX_INV       = 41;   // TX irq inverted
    parameter integer CTRL_OUT_SRC_IRQ_RX           = 42;   // RX irq
    parameter integer CTRL_OUT_SRC_IRQ_RX_INV       = 43;   // RX irq inverted
    parameter integer CTRL_OUT_SRC_IRQ_FPGA         = 44;   // FPGA irq
    parameter integer CTRL_OUT_SRC_IRQ_FPGA_INV     = 45;   // FPGA irq inverted
    parameter integer CTRL_OUT_SRC_TX_FULL          = 46;   // TX FIFO full
    parameter integer CTRL_OUT_SRC_TX_FULL_INV      = 47;   // TX FIFO full inverted
    parameter integer CTRL_OUT_SRC_TX_EMPTY         = 48;   // TX FIFO empty
    parameter integer CTRL_OUT_SRC_TX_EMPTY_INV     = 49;   // TX FIFO empty inverted
    parameter integer CTRL_OUT_SRC_RX_FULL          = 50;   // RX FIFO full
    parameter integer CTRL_OUT_SRC_RX_FULL_INV      = 51;   // RX FIFO full inverted
    parameter integer CTRL_OUT_SRC_RX_EMPTY         = 52;   // RX FIFO empty
    parameter integer CTRL_OUT_SRC_RX_EMPTY_INV     = 53;   // RX FIFO empty inverted

    // unused    
    parameter integer CTRL_OUT_SRC_UNUSED_54        = 54;
    parameter integer CTRL_OUT_SRC_UNUSED_55        = 55;
    parameter integer CTRL_OUT_SRC_UNUSED_56        = 56;
    parameter integer CTRL_OUT_SRC_UNUSED_57        = 57;
    parameter integer CTRL_OUT_SRC_UNUSED_58        = 58;
    parameter integer CTRL_OUT_SRC_UNUSED_59        = 59;
    parameter integer CTRL_OUT_SRC_UNUSED_60        = 60;
    parameter integer CTRL_OUT_SRC_UNUSED_61        = 61;
    parameter integer CTRL_OUT_SRC_UNUSED_62        = 62;
    parameter integer CTRL_OUT_SRC_UNUSED_63        = 63;
    

