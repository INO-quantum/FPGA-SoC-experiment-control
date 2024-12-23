// ctrl_in_params.vh
// input source and destinations for ctrl_in_mux.v module
// created 5/10/2024 by Andi
// last change 3/12/2024 by Andi

    // input control register
    parameter integer CTRL_IN_SRC_BITS          = 6;

    // input destinations offsets (max. floor(32/CTRL_IN_SRC_BITS) = 5 possible per register)
    // register 0
    parameter integer CTRL_IN0_DST_TRG_START    = 0;    // start trigger
    parameter integer CTRL_IN0_DST_TRG_STOP     = 1;    // stop trigger
    parameter integer CTRL_IN0_DST_TRG_RESTART  = 2;    // restart trigger
    parameter integer CTRL_IN0_DST_LOGIC_A0     = 3;    // logic module A input 0
    parameter integer CTRL_IN0_DST_LOGIC_A1     = 4;    // logic module A input 1
    // register 1
    parameter integer CTRL_IN1_DST_DATA_NOP     = 0;    // no operation bit
    parameter integer CTRL_IN1_DST_DATA_IRQ     = 1;    // IRQ bit
    parameter integer CTRL_IN1_DST_DATA_STRB    = 2;    // strobe bit 
    parameter integer CTRL_IN0_DST_LOGIC_B0     = 3;    // logic module B input 0
    parameter integer CTRL_IN0_DST_LOGIC_B1     = 4;    // logic module B input 1

    // input sources (max. 2^CTRL_IN_SRC_BITS = 64 possible)
    parameter integer CTRL_IN_SRC_NONE          = 0;    // source disabled
    parameter integer CTRL_IN_SRC_IN0           = 1;    // ext_in[0]
    parameter integer CTRL_IN_SRC_IN0_INV       = 2;    // ext_in[0] inverted
    parameter integer CTRL_IN_SRC_IN0_EDGE_POS  = 3;    // ext_in[0] positive edge
    parameter integer CTRL_IN_SRC_IN0_EDGE_NEG  = 4;    // ext_in[0] negative edge
    parameter integer CTRL_IN_SRC_IN1           = 5;    // ext_in[1]
    parameter integer CTRL_IN_SRC_IN1_INV       = 6;    // ext_in[1] inverted
    parameter integer CTRL_IN_SRC_IN1_EDGE_POS  = 7;    // ext_in[1] positive edge
    parameter integer CTRL_IN_SRC_IN1_EDGE_NEG  = 8;    // ext_in[1] negative edge
    parameter integer CTRL_IN_SRC_IN2           = 9;    // ext_in[2]
    parameter integer CTRL_IN_SRC_IN2_INV       = 10;   // ext_in[2] inverted
    parameter integer CTRL_IN_SRC_IN2_EDGE_POS  = 11;   // ext_in[2] positive edge
    parameter integer CTRL_IN_SRC_IN2_EDGE_NEG  = 12;   // ext_in[2] negative edge

    parameter integer CTRL_IN_SRC_UNUSED_13     = 13;
    parameter integer CTRL_IN_SRC_UNUSED_14     = 14;
    parameter integer CTRL_IN_SRC_UNUSED_15     = 15;
    parameter integer CTRL_IN_SRC_UNUSED_16     = 16;
    parameter integer CTRL_IN_SRC_UNUSED_17     = 17;
    parameter integer CTRL_IN_SRC_UNUSED_18     = 18;
    parameter integer CTRL_IN_SRC_UNUSED_19     = 19;
    parameter integer CTRL_IN_SRC_UNUSED_20     = 20;
    parameter integer CTRL_IN_SRC_UNUSED_21     = 21;
    parameter integer CTRL_IN_SRC_UNUSED_22     = 22;
    parameter integer CTRL_IN_SRC_UNUSED_23     = 23;
    parameter integer CTRL_IN_SRC_UNUSED_24     = 24;

/*  parameter integer CTRL_IN_SRC_LOGIC_A       = 13;   // logic module A output
    parameter integer CTRL_IN_SRC_LOGIC_B       = 14;   // logic module B output
    parameter integer CTRL_IN_SRC_LOGIC_A_INV   = 15;   // logic module A inverted output
    parameter integer CTRL_IN_SRC_LOGIC_A_XOR   = 15;   // logic module A in0 ^ in1
    parameter integer CTRL_IN_SRC_LOGIC_A_NAND  = 16;   // logic module A ~(in0 & in1)
    parameter integer CTRL_IN_SRC_LOGIC_A_NOR   = 17;   // logic module A ~(in0 | in1)
    parameter integer CTRL_IN_SRC_LOGIC_A_XNOR  = 18;   // logic module A ~(in0 ^ in1)
    parameter integer CTRL_IN_SRC_LOGIC_B_AND   = 19;   // logic module B in0 & in1
    parameter integer CTRL_IN_SRC_LOGIC_B_OR    = 20;   // logic module B in0 | in1
    parameter integer CTRL_IN_SRC_LOGIC_B_XOR   = 21;   // logic module B in0 ^ in1
    parameter integer CTRL_IN_SRC_LOGIC_B_NAND  = 22;   // logic module B ~(in0 & in1)
    parameter integer CTRL_IN_SRC_LOGIC_B_NOR   = 23;   // logic module B ~(in0 | in1)
    parameter integer CTRL_IN_SRC_LOGIC_B_XNOR  = 24;   // logic module B ~(in0 ^ in1)
*/
    parameter integer CTRL_IN_SRC_UNUSED_25     = 25;
    parameter integer CTRL_IN_SRC_UNUSED_26     = 26;
    parameter integer CTRL_IN_SRC_UNUSED_27     = 27;
    parameter integer CTRL_IN_SRC_UNUSED_28     = 28;
    parameter integer CTRL_IN_SRC_UNUSED_29     = 29;
    parameter integer CTRL_IN_SRC_UNUSED_30     = 30;
    parameter integer CTRL_IN_SRC_UNUSED_31     = 31;

    parameter integer CTRL_IN_SRC_DATA_0        = 32;   // data bit 0 
    parameter integer CTRL_IN_SRC_DATA_1        = 33;   // data bit 1
    parameter integer CTRL_IN_SRC_DATA_2        = 34;   // data bit 2
    parameter integer CTRL_IN_SRC_DATA_3        = 35;   // data bit 3 
    parameter integer CTRL_IN_SRC_DATA_4        = 36;   // data bit 4
    parameter integer CTRL_IN_SRC_DATA_5        = 37;   // data bit 5 
    parameter integer CTRL_IN_SRC_DATA_6        = 38;   // data bit 6
    parameter integer CTRL_IN_SRC_DATA_7        = 39;   // data bit 7
    parameter integer CTRL_IN_SRC_DATA_8        = 40;   // data bit 8
    parameter integer CTRL_IN_SRC_DATA_9        = 41;   // data bit 9 
    parameter integer CTRL_IN_SRC_DATA_10       = 42;   // data bit 10
    parameter integer CTRL_IN_SRC_DATA_11       = 43;   // data bit 11
    parameter integer CTRL_IN_SRC_DATA_12       = 44;   // data bit 12
    parameter integer CTRL_IN_SRC_DATA_13       = 45;   // data bit 13 
    parameter integer CTRL_IN_SRC_DATA_14       = 46;   // data bit 14
    parameter integer CTRL_IN_SRC_DATA_15       = 47;   // data bit 15
    parameter integer CTRL_IN_SRC_DATA_16       = 48;   // data bit 16
    parameter integer CTRL_IN_SRC_DATA_17       = 49;   // data bit 17 
    parameter integer CTRL_IN_SRC_DATA_18       = 50;   // data bit 18
    parameter integer CTRL_IN_SRC_DATA_19       = 51;   // data bit 19 
    parameter integer CTRL_IN_SRC_DATA_20       = 52;   // data bit 20
    parameter integer CTRL_IN_SRC_DATA_21       = 53;   // data bit 21
    parameter integer CTRL_IN_SRC_DATA_22       = 54;   // data bit 22
    parameter integer CTRL_IN_SRC_DATA_23       = 55;   // data bit 23 
    parameter integer CTRL_IN_SRC_DATA_24       = 56;   // data bit 24
    parameter integer CTRL_IN_SRC_DATA_25       = 57;   // data bit 25
    parameter integer CTRL_IN_SRC_DATA_26       = 58;   // data bit 26
    parameter integer CTRL_IN_SRC_DATA_27       = 59;   // data bit 27 
    parameter integer CTRL_IN_SRC_DATA_28       = 60;   // data bit 28
    parameter integer CTRL_IN_SRC_DATA_29       = 61;   // data bit 29 
    parameter integer CTRL_IN_SRC_DATA_30       = 62;   // data bit 30
    parameter integer CTRL_IN_SRC_DATA_31       = 63;   // data bit 31


