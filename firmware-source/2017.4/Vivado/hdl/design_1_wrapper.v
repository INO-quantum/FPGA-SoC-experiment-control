//Copyright 1986-2017 Xilinx, Inc. All Rights Reserved.
//--------------------------------------------------------------------------------
//Tool Version: Vivado v.2017.4 (lin64) Build 2086221 Fri Dec 15 20:54:30 MST 2017
//Date        : Thu May 13 14:09:42 2021
//Host        : andi-ThinkPad-E14 running 64-bit Ubuntu 18.04.5 LTS
//Command     : generate_target design_1_wrapper.bd
//Design      : design_1_wrapper
//Purpose     : IP block netlist
//--------------------------------------------------------------------------------
`timescale 1 ps / 1 ps

module design_1_wrapper
   (DDR_addr,
    DDR_ba,
    DDR_cas_n,
    DDR_ck_n,
    DDR_ck_p,
    DDR_cke,
    DDR_cs_n,
    DDR_dm,
    DDR_dq,
    DDR_dqs_n,
    DDR_dqs_p,
    DDR_odt,
    DDR_ras_n,
    DDR_reset_n,
    DDR_we_n,
    FIXED_IO_ddr_vrn,
    FIXED_IO_ddr_vrp,
    FIXED_IO_mio,
    FIXED_IO_ps_clk,
    FIXED_IO_ps_porb,
    FIXED_IO_ps_srstb,
    bus_addr_0,
    bus_data_0,
    bus_enable_n_0,
    bus_strb_0,
    buttons_in_0,
    clk_in1_0,
    clk_out_0,
    led_blue_0,
    leds_out_0,
    sync_en_0,
    sync_in_0,
    sync_mon_0,
    sync_out_0,
    trg_out_0,
    trg_start_0,
    trg_stop_0);
  inout [14:0]DDR_addr;
  inout [2:0]DDR_ba;
  inout DDR_cas_n;
  inout DDR_ck_n;
  inout DDR_ck_p;
  inout DDR_cke;
  inout DDR_cs_n;
  inout [3:0]DDR_dm;
  inout [31:0]DDR_dq;
  inout [3:0]DDR_dqs_n;
  inout [3:0]DDR_dqs_p;
  inout DDR_odt;
  inout DDR_ras_n;
  inout DDR_reset_n;
  inout DDR_we_n;
  inout FIXED_IO_ddr_vrn;
  inout FIXED_IO_ddr_vrp;
  inout [53:0]FIXED_IO_mio;
  inout FIXED_IO_ps_clk;
  inout FIXED_IO_ps_porb;
  inout FIXED_IO_ps_srstb;
  output [6:0]bus_addr_0;
  output [15:0]bus_data_0;
  output bus_enable_n_0;
  output bus_strb_0;
  input [1:0]buttons_in_0;
  input clk_in1_0;
  output clk_out_0;
  output [1:0]led_blue_0;
  output [3:0]leds_out_0;
  output sync_en_0;
  input sync_in_0;
  output sync_mon_0;
  output sync_out_0;
  output trg_out_0;
  input trg_start_0;
  input trg_stop_0;

  wire [14:0]DDR_addr;
  wire [2:0]DDR_ba;
  wire DDR_cas_n;
  wire DDR_ck_n;
  wire DDR_ck_p;
  wire DDR_cke;
  wire DDR_cs_n;
  wire [3:0]DDR_dm;
  wire [31:0]DDR_dq;
  wire [3:0]DDR_dqs_n;
  wire [3:0]DDR_dqs_p;
  wire DDR_odt;
  wire DDR_ras_n;
  wire DDR_reset_n;
  wire DDR_we_n;
  wire FIXED_IO_ddr_vrn;
  wire FIXED_IO_ddr_vrp;
  wire [53:0]FIXED_IO_mio;
  wire FIXED_IO_ps_clk;
  wire FIXED_IO_ps_porb;
  wire FIXED_IO_ps_srstb;
  wire [6:0]bus_addr_0;
  wire [15:0]bus_data_0;
  wire bus_enable_n_0;
  wire bus_strb_0;
  wire [1:0]buttons_in_0;
  wire clk_in1_0;
  wire clk_out_0;
  wire [1:0]led_blue_0;
  wire [3:0]leds_out_0;
  wire sync_en_0;
  wire sync_in_0;
  wire sync_mon_0;
  wire sync_out_0;
  wire trg_out_0;
  wire trg_start_0;
  wire trg_stop_0;

  design_1 design_1_i
       (.DDR_addr(DDR_addr),
        .DDR_ba(DDR_ba),
        .DDR_cas_n(DDR_cas_n),
        .DDR_ck_n(DDR_ck_n),
        .DDR_ck_p(DDR_ck_p),
        .DDR_cke(DDR_cke),
        .DDR_cs_n(DDR_cs_n),
        .DDR_dm(DDR_dm),
        .DDR_dq(DDR_dq),
        .DDR_dqs_n(DDR_dqs_n),
        .DDR_dqs_p(DDR_dqs_p),
        .DDR_odt(DDR_odt),
        .DDR_ras_n(DDR_ras_n),
        .DDR_reset_n(DDR_reset_n),
        .DDR_we_n(DDR_we_n),
        .FIXED_IO_ddr_vrn(FIXED_IO_ddr_vrn),
        .FIXED_IO_ddr_vrp(FIXED_IO_ddr_vrp),
        .FIXED_IO_mio(FIXED_IO_mio),
        .FIXED_IO_ps_clk(FIXED_IO_ps_clk),
        .FIXED_IO_ps_porb(FIXED_IO_ps_porb),
        .FIXED_IO_ps_srstb(FIXED_IO_ps_srstb),
        .bus_addr_0(bus_addr_0),
        .bus_data_0(bus_data_0),
        .bus_enable_n_0(bus_enable_n_0),
        .bus_strb_0(bus_strb_0),
        .buttons_in_0(buttons_in_0),
        .clk_in1_0(clk_in1_0),
        .clk_out_0(clk_out_0),
        .led_blue_0(led_blue_0),
        .leds_out_0(leds_out_0),
        .sync_en_0(sync_en_0),
        .sync_in_0(sync_in_0),
        .sync_mon_0(sync_mon_0),
        .sync_out_0(sync_out_0),
        .trg_out_0(trg_out_0),
        .trg_start_0(trg_start_0),
        .trg_stop_0(trg_stop_0));
endmodule
