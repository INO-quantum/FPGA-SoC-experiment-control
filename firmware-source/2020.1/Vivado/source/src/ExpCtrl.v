`timescale 1 ns / 1 ps

//////////////////////////////////////////////////////////////////////////////////
// ExpCtrl_top module
// created 2023/09/03 by Andi
// intended as RTL top module for ExpCtrl project without Block diagram
// at the moment only instantiates dio24.v and is part of the block diagram 
// last change 2023/09/07 by Andi
// notes:
// - Vivado does not accept SystemVerilog modules as top module, only VHDL or Verilog are allowed.
// - in order that Vivado recognizes the interfaces the official names have to be appended to the port names.
// TODO: insert all external block diagram modules here (maybe with a .sv wrapper):
//       Zynq, Cpu Reset, DMA, 2x Clock Wizard, Concat, interconnect and Smart connect
//////////////////////////////////////////////////////////////////////////////////

module ExpCtrl_top #
(
    // fixed data widths needed for port definitions. do not change.
    parameter integer AXI_ADDR_WIDTH        = 7,            // 7: 2^7/4 = 32 registers
    parameter integer AXI_DATA_WIDTH        = 32,           // must be 32
    parameter integer STREAM_DATA_WIDTH     = 128,          // 128
    parameter integer BUS_ADDR_BITS         = 7,            // 7
    parameter integer BUS_DATA_BITS         = 16,           // 16

    // user-provided version and info register content
    parameter integer VERSION               = 32'h0103_0000, // version register 0xMM.mm_(year-2000)??9+month??5+day 
    parameter integer INFO                  = 32'h0000_0000, // info  register, 0xc1 = Cora-Z7-10
        
    // I/O bits
    parameter integer NUM_IN_BITS           = 3,            // number of external inputs
    parameter integer NUM_OUT_BITS          = 3,            // number of external outputs
            
    // LEDs and buttons 
    parameter integer NUM_BUTTONS           = 2,            // must be 2
    parameter integer NUM_LED_RED           = 2,            // must be 2
    parameter integer NUM_LED_GREEN         = 3,            // must be 3
    parameter integer NUM_LED_BLUE          = 2,            // must be 2
    // bits used for blinking leds ON-time: 1=50%, 2=25%, 3=12.5%, 4=6.25%
    parameter integer LED_BLINK_ON          = 3,
    // bits used for blinking leds
    parameter LED_SLOW                      = 26,           // blink slow
    parameter LED_FAST                      = 24,           // blink fast (1 <= LED_FAST < LED_SLOW)
    // bits used for PWM dimming of leds. 0 = no dimming.
    parameter LED_DIM_LOW                   = 8,            // dim level low (< LED_SLOW)
    parameter LED_DIM_HIGH                  = 6,            // dim level high (< LED_SLOW)
    parameter LED_BRIGHT_LOW                = 1,            // bright level low (< LED_SLOW)
    parameter LED_BRIGHT_HIGH               = 1,            // bright level high (1 <= LED_BRIGHT_HIGH < LED_SLOW)
        
    // auto-sync
    parameter integer AUTO_SYNC_PULSE_LENGTH = 3,           // 2 = 40ns @ 50MHz 
    parameter integer AUTO_SYNC_PULSE_WAIT   = 5,           // 3 = 60ns @ 50MHz, wait time after pulse
                                                            // this does not affect bus_strb_0/1 output.
    // irq_FPGA frequency
    parameter integer IRQ_FREQ_BITS         = 20,           // 20 = 10Hz at 10MHz bus clock, 23 = 12Hz @ 100MHz
            
    // minimum number of contiguous cycles until lock lost error is raised. 
    parameter integer ERROR_LOCK_DELAY      = 5,

    // TX and RX FIFO
    parameter integer TX_FIFO_DEPTH         = 8192,
    parameter integer RX_FIFO_DEPTH         = 8192
)
(
    // AXI LITE Bus Interface
    input wire                              AXI_LITE_ACLK,
    input wire                              AXI_LITE_ARESETN,
    input wire [AXI_ADDR_WIDTH-1 : 0]       AXI_LITE_AWADDR,
    input wire [2 : 0]                      AXI_LITE_AWPROT,
    input wire                              AXI_LITE_AWVALID,
    output wire                             AXI_LITE_AWREADY,
    input wire [AXI_DATA_WIDTH-1 : 0]       AXI_LITE_WDATA,
    input wire [(AXI_DATA_WIDTH/8)-1 : 0]   AXI_LITE_WSTRB,
    input wire                              AXI_LITE_WVALID,
    output wire                             AXI_LITE_WREADY,
    output wire [1 : 0]                     AXI_LITE_BRESP,
    output wire                             AXI_LITE_BVALID,
    input wire                              AXI_LITE_BREADY,
    input wire [AXI_ADDR_WIDTH-1 : 0]       AXI_LITE_ARADDR,
    input wire [2 : 0]                      AXI_LITE_ARPROT,
    input wire                              AXI_LITE_ARVALID,
    output wire                             AXI_LITE_ARREADY,
    output wire [AXI_DATA_WIDTH-1 : 0]      AXI_LITE_RDATA,
    output wire [1 : 0]                     AXI_LITE_RRESP,
    output wire                             AXI_LITE_RVALID,
    input wire                              AXI_LITE_RREADY,

    // AXI stream data input (from DMA stream master @ clk_fast)
    input wire                              AXIS_in_ACLK,   // PL clock with AXI stream data from PS [100MHz]
    input wire                              AXIS_in_ARESETN,
    input wire [STREAM_DATA_WIDTH-1 : 0]    AXIS_in_TDATA,
    input wire [(STREAM_DATA_WIDTH/8)-1:0]  AXIS_in_TKEEP,
    input wire                              AXIS_in_TLAST,
    input wire                              AXIS_in_TVALID,
    output wire                             AXIS_in_TREADY,

    // AXI stream data output (to DMA stream slave @ clk_fast)
    input wire                              AXIS_out_ACLK,  // PL clock with AXI stream data from PS [100MHz]
    input wire                              AXIS_out_ARESETN,
    output wire [STREAM_DATA_WIDTH-1 : 0]   AXIS_out_TDATA,
    output wire [(STREAM_DATA_WIDTH/8)-1:0] AXIS_out_TKEEP,
    output wire                             AXIS_out_TLAST,
    output wire                             AXIS_out_TVALID,
    input wire                              AXIS_out_TREADY,

    // clocks and reset
    input wire                              clk_bus,        // main clock, typically PL clock, can be locked to external clock [100MHz]
    input wire                              clk_det,        // clk_bus + phase shift phi_det [100MHz]
    input wire                              clk_pwm,        // slow clock for PWM of LEDs [10MHz]
    //input wire                              ext_clk_in,       // 10MHz external input clock
    //output wire                             ext_clk_out,      // 10MHz external output clock

    // AXI Lite interface
    output wire                             reset_AXI_sw_n, // @ clk_AXI, hardware + software reset output for clock Wizards
    
    // FPGA board buttons and RGB LEDs
    input wire [NUM_BUTTONS-1:0]            buttons_in,     // async
    output wire [NUM_LED_RED-1:0]           led_red,        // @ clk_AXI
    output wire [NUM_LED_GREEN-1:0]         led_green,      // @ clk_AXI
    output wire [NUM_LED_BLUE-1:0]          led_blue,       // @ clk_AXI
    
    // buffer board external clock control
    input wire                              clk_ext_locked, // assumed not synchronized to any clock
    input wire                              clk_mux_locked, // assumed not synchronized to any clock
    output wire                             clk_ext_sel,    // @ clk_AXI

    // rack data bus output @ clk_bus
    output wire [1:0]                       bus_en,
    output wire [BUS_DATA_BITS-1:0]         bus_data,
    output wire [BUS_ADDR_BITS-1:0]         bus_addr_0,
    output wire [BUS_ADDR_BITS-1:0]         bus_addr_1,
    // strobe output at phase shifted clk_bus x2
    output wire                             bus_strb_0,
    output wire                             bus_strb_1,
    
    // irq I/O @ clk_fast
    input wire                              irq_TX,
    input wire                              irq_RX,
    output wire                             irq_FPGA,
    
    // external inputs
    input wire [NUM_IN_BITS-1:0]            ext_in,
    
    // external outputs
    output wire [NUM_OUT_BITS-1:0]          ext_out,
    
    // dynamic phase shift of external clock input and detector clock @ clk_AXI 
    input wire                              ps_done_ext,
    output wire                             ps_en_ext,
    output wire                             ps_inc_ext,
    input wire                              ps_done_det,
    output wire                             ps_en_det,
    output wire                             ps_inc_det
);

    // clock control and status signals
    //wire reset_AXI_sw_n;   // @ clk_AXI, hardware + software reset output for clock Wizards 
    //wire clk_ext_locked; // assumed not synchronized to any clock
    //wire clk_mux_locked; // assumed not synchronized to any clock
    //wire clk_ext_sel;    // @ clk_AXI

    // dynamic phase shift of external clock input and detector clock @ clk_AXI 
    //wire ps_clk = AXI_LITE_ACLK;
    //wire ps_done_ext;
    //wire ps_en_ext;
    //wire ps_inc_ext;
    //wire ps_done_det;
    //wire ps_en_det;
    //wire ps_inc_det;

    /* external input clock buffer
    wire ext_clk_in_buf;
    BUFG BUFG_in (
      .O(ext_clk_in_buf), // 1-bit output: Clock output
      .I(ext_clk_in)  // 1-bit input: Clock input
   );*/

    /* input clock MMCM
    // in = 10MHz + BUFG, out = 100MHz with dynamic phase shift @ clk_AXI
    wire ext_clk_in_100;
    MMCME2_ADV #(
        .BANDWIDTH("OPTIMIZED"),        // Jitter programming (OPTIMIZED, HIGH, LOW)
        .CLKFBOUT_MULT_F(60.0),          // Multiply value for all CLKOUT (2.000-64.000).
        .CLKFBOUT_PHASE(0.0),           // Phase offset in degrees of CLKFB (-360.000-360.000).
        // CLKIN_PERIOD: Input clock period in ns to ps resolution (i.e. 33.333 is 30 MHz).
        .CLKIN1_PERIOD(100.0),
        .CLKIN2_PERIOD(10.0),
        // CLKOUT0_DIVIDE - CLKOUT6_DIVIDE: Divide amount for CLKOUT (1-128)
        .CLKOUT1_DIVIDE(1),
        .CLKOUT2_DIVIDE(1),
        .CLKOUT3_DIVIDE(1),
        .CLKOUT4_DIVIDE(1),
        .CLKOUT5_DIVIDE(1),
        .CLKOUT6_DIVIDE(1),
        .CLKOUT0_DIVIDE_F(6.0),         // Divide amount for CLKOUT0 (1.000-128.000).
        // CLKOUT0_DUTY_CYCLE - CLKOUT6_DUTY_CYCLE: Duty cycle for CLKOUT outputs (0.01-0.99).
        .CLKOUT0_DUTY_CYCLE(0.5),
        .CLKOUT1_DUTY_CYCLE(0.5),
        .CLKOUT2_DUTY_CYCLE(0.5),
        .CLKOUT3_DUTY_CYCLE(0.5),
        .CLKOUT4_DUTY_CYCLE(0.5),
        .CLKOUT5_DUTY_CYCLE(0.5),
        .CLKOUT6_DUTY_CYCLE(0.5),
        // CLKOUT0_PHASE - CLKOUT6_PHASE: Phase offset for CLKOUT outputs (-360.000-360.000).
        .CLKOUT0_PHASE(0.0),
        .CLKOUT1_PHASE(0.0),
        .CLKOUT2_PHASE(0.0),
        .CLKOUT3_PHASE(0.0),
        .CLKOUT4_PHASE(0.0),
        .CLKOUT5_PHASE(0.0),
        .CLKOUT6_PHASE(0.0),
        .CLKOUT4_CASCADE("FALSE"),      // Cascade CLKOUT4 counter with CLKOUT6 (FALSE, TRUE)
        .COMPENSATION("ZHOLD"),         // ZHOLD, BUF_IN, EXTERNAL, INTERNAL
        .DIVCLK_DIVIDE(1),              // Master division value (1-106)
        // REF_JITTER: Reference input jitter in UI (0.000-0.999).
        .REF_JITTER1(0.5),
        .REF_JITTER2(0.2),
        .STARTUP_WAIT("FALSE"),         // Delays DONE until MMCM is locked (FALSE, TRUE)
        // Spread Spectrum: Spread Spectrum Attributes
        .SS_EN("FALSE"),                // Enables spread spectrum (FALSE, TRUE)
        .SS_MODE("CENTER_HIGH"),        // CENTER_HIGH, CENTER_LOW, DOWN_HIGH, DOWN_LOW
        .SS_MOD_PERIOD(10000),          // Spread spectrum modulation period (ns) (VALUES)
        // USE_FINE_PS: Fine phase shift enable (TRUE/FALSE)
        .CLKFBOUT_USE_FINE_PS("FALSE"),
        .CLKOUT0_USE_FINE_PS("TRUE"),
        .CLKOUT1_USE_FINE_PS("FALSE"),
        .CLKOUT2_USE_FINE_PS("FALSE"),
        .CLKOUT3_USE_FINE_PS("FALSE"),
        .CLKOUT4_USE_FINE_PS("FALSE"),
        .CLKOUT5_USE_FINE_PS("FALSE"),
        .CLKOUT6_USE_FINE_PS("FALSE")
    )
    MMCME2_ADV_inst (
        // Clock Outputs: 1-bit (each) output: User configurable clock outputs
        .CLKOUT0(ext_clk_in_100),   // 1-bit output: CLKOUT0
        .CLKOUT0B(),                // 1-bit output: Inverted CLKOUT0
        .CLKOUT1(),                 // 1-bit output: CLKOUT1
        .CLKOUT1B(),                // 1-bit output: Inverted CLKOUT1
        .CLKOUT2(),                 // 1-bit output: CLKOUT2
        .CLKOUT2B(),                // 1-bit output: Inverted CLKOUT2
        .CLKOUT3(),                 // 1-bit output: CLKOUT3
        .CLKOUT3B(),                // 1-bit output: Inverted CLKOUT3
        .CLKOUT4(),                 // 1-bit output: CLKOUT4
        .CLKOUT5(),                 // 1-bit output: CLKOUT5
        .CLKOUT6(),                 // 1-bit output: CLKOUT6
        // DRP Ports: 16-bit (each) output: Dynamic reconfiguration ports
        .DO(),                      // 16-bit output: DRP data
        .DRDY( ),                   // 1-bit output: DRP ready
        // Dynamic Phase Shift Ports: 1-bit (each) output: Ports used for dynamic phase shifting of the outputs
        .PSDONE(ps_done_ext),       // 1-bit output: Phase shift done
        // Feedback Clocks: 1-bit (each) output: Clock feedback ports
        .CLKFBOUT(CLKFBOUT),         // 1-bit output: Feedback clock
        .CLKFBOUTB(CLKFBOUTB),       // 1-bit output: Inverted CLKFBOUT
        // Status Ports: 1-bit (each) output: MMCM status ports
        .CLKFBSTOPPED(CLKFBSTOPPED), // 1-bit output: Feedback clock stopped
        .CLKINSTOPPED(CLKINSTOPPED), // 1-bit output: Input clock stopped
        .LOCKED(clk_ext_locked),     // 1-bit output: LOCK
        // Clock Inputs: 1-bit (each) input: Clock inputs
        .CLKIN1(ext_clk_in_buf),     // 1-bit input: Primary clock
        .CLKIN2(),                   // 1-bit input: Secondary clock
        // Control Ports: 1-bit (each) input: MMCM control ports
        .CLKINSEL(1'b1),             // 1-bit input: Clock select, High=CLKIN1 Low=CLKIN2
        .PWRDWN(1'b0),               // 1-bit input: Power-down
        .RST(reset_AXI_sw),          // 1-bit input: Reset
        // DRP Ports: 7-bit (each) input: Dynamic reconfiguration ports
        .DADDR(),                    // 7-bit input: DRP address
        .DCLK( ),                    // 1-bit input: DRP clock
        .DEN(1'b0),                  // 1-bit input: DRP enable
        .DI(),                       // 16-bit input: DRP data
        .DWE(),                      // 1-bit input: DRP write enable
        // Dynamic Phase Shift Ports: 1-bit (each) input: Ports used for dynamic phase shifting of the outputs
        .PSCLK(ps_clk),               // 1-bit input: Phase shift clock
        .PSEN(ps_en_ext),             // 1-bit input: Phase shift enable
        .PSINCDEC(ps_incdec_ext),     // 1-bit input: Phase shift increment/decrement
        // Feedback Clocks: 1-bit (each) input: Clock feedback ports
        .CLKFBIN()                    // 1-bit input: Feedback clock
    );
    */

    dio24 #
    (
        .AXI_ADDR_WIDTH(AXI_ADDR_WIDTH),
        .AXI_DATA_WIDTH(AXI_DATA_WIDTH),
        .STREAM_DATA_WIDTH(STREAM_DATA_WIDTH),
        .BUS_ADDR_BITS(BUS_ADDR_BITS),
        .BUS_DATA_BITS(BUS_DATA_BITS),

        .VERSION(VERSION),
        .INFO(INFO),

        .BITS_PER_SAMPLE(64),               // 64 (2 ports) or 96 (4 ports)
        
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
        
        .TIME_BITS(32),                     // must be 32
        .TIME_START(0),                     // first time
        .DATA_BITS(32),                     // must be 32
        .DATA_START_64(32),                 // 32
        .DATA_START_96_0(32),               // 32
        .DATA_START_96_1(64),               // 64
        .CLK_DIV_BITS(8),                   // 8: clock divider = 1-255
        .TRG_DIV_BITS(8),                   // 8: trigger window divider = 0-255
        .STRB_DELAY_BITS(8),                // 8
        
        .AUTO_SYNC_PULSE_LENGTH(AUTO_SYNC_PULSE_LENGTH),
        .AUTO_SYNC_PULSE_WAIT(AUTO_SYNC_PULSE_WAIT),
        .AUTO_SYNC_MAX_PULSES(2),           // 2 
        .AUTO_SYNC_TIME_BITS(8),            // 8
        .AUTO_SYNC_DELAY_BITS(10),          // 10
        .AUTO_SYNC_PHASE_BITS(12),          // 12     

        .BUS_ADDR_1_USE("ADDR0"),           // "ADDR0" = same as bus_addr_0, otherwise set to 0.
        
        .BIT_NOP(31),                       // must be 31. when set then data is not output on bus, but time is still running,
        .BIT_TRST(30),                      // 30. when set time is reset to 0 [not implemented]
        .BIT_IRQ(29),                       // 29. when set FPGA_irq is generated.
        .BIT_STOP(28),                      // 28, when set board waits for next start trigger
        
        .BIT_STROBE(23),                    // strobe bit = highest address bit in input data.
        .USE_STROBE("NO"),                  // "YES" = data output when BIT_STROBE toggles, otherwise BIT_STROBE is ignored.

        .SYNC(2),                           // 2-3

        .IRQ_FREQ_BITS(IRQ_FREQ_BITS),
                
        .ERROR_LOCK_DELAY(ERROR_LOCK_DELAY),

        .TX_FIFO_DEPTH(TX_FIFO_DEPTH),
        .RX_FIFO_DEPTH(RX_FIFO_DEPTH)
    )
    dio24_inst
    (
	    .s00_axi_aclk(AXI_LITE_ACLK),
        .s00_axi_aresetn(AXI_LITE_ARESETN),
	    .s00_axi_awaddr(AXI_LITE_AWADDR),
	    .s00_axi_awprot(AXI_LITE_AWPROT),
	    .s00_axi_awvalid(AXI_LITE_AWVALID),
	    .s00_axi_awready(AXI_LITE_AWREADY),
	    .s00_axi_wdata(AXI_LITE_WDATA),
	    .s00_axi_wstrb(AXI_LITE_WSTRB),
	    .s00_axi_wvalid(AXI_LITE_WVALID),
	    .s00_axi_wready(AXI_LITE_WREADY),
	    .s00_axi_bresp(AXI_LITE_BRESP),
	    .s00_axi_bvalid(AXI_LITE_BVALID),
	    .s00_axi_bready(AXI_LITE_BREADY),
	    .s00_axi_araddr(AXI_LITE_ARADDR),
	    .s00_axi_arprot(AXI_LITE_ARPROT),
	    .s00_axi_arvalid(AXI_LITE_ARVALID),
	    .s00_axi_arready(AXI_LITE_ARREADY),
	    .s00_axi_rdata(AXI_LITE_RDATA),
	    .s00_axi_rresp(AXI_LITE_RRESP),
	    .s00_axi_rvalid(AXI_LITE_RVALID),
	    .s00_axi_rready(AXI_LITE_RREADY),

        .AXIS_in_aclk(AXIS_IN_ACLK),
        .AXIS_in_aresetn(AXIS_IN_ARESETN),
	    .AXIS_in_tdata(AXIS_IN_TDATA),
	    .AXIS_in_tkeep(AXIS_IN_TKEEP),
        .AXIS_in_tlast(AXIS_IN_TLAST),
	    .AXIS_in_tvalid(AXIS_IN_TVALID),
	    .AXIS_in_tready(AXIS_IN_TREADY),

        .AXIS_out_aclk(AXIS_OUT_ACLK),
        .AXIS_out_aresetn(AXIS_OUT_ARESETN),
	    .AXIS_out_tdata(AXIS_OUT_TDATA),
	    .AXIS_out_tkeep(AXIS_OUT_TKEEP),
	    .AXIS_out_tlast(AXIS_OUT_TLAST),
	    .AXIS_out_tvalid(AXIS_OUT_TVALID),
	    .AXIS_out_tready(AXIS_OUT_TREADY),

        .clk_bus(clk_bus),
        .clk_det(clk_det),
        .clk_pwm(clk_pwm),

        .reset_AXI_sw_n(reset_AXI_sw_n),
        
        .buttons_in(buttons_in),
        .led_red(led_red),
        .led_green(led_green),
        .led_blue(led_blue),
        
        .clk_ext_locked(clk_ext_locked),
        .clk_mux_locked(clk_mux_locked),
        .clk_ext_sel(clk_ext_sel),

        .bus_en(bus_en),
        .bus_data(bus_data),
        .bus_addr_0(bus_addr_0),
        .bus_addr_1(bus_addr_1),
        .bus_strb_0(bus_strb_0),
        .bus_strb_1(bus_strb_1),
        
        .irq_TX(irq_TX),
        .irq_RX(irq_RX),
        .irq_FPGA(irq_FPGA),
        
        .ext_in(ext_in),
        .ext_out(ext_out),
        
        .ps_done_ext(ps_done_ext),
        .ps_en_ext(ps_en_ext),
        .ps_inc_ext(ps_inc_ext),
        .ps_done_det(pd_done_det),
        .ps_en_det(ps_en_det),
        .ps_inc_det(ps_inc_det)
    );

endmodule
