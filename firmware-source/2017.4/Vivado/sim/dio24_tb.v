`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// test bench for dio24 module
// created 24/03/2020 by Andi
// last change 15/04/2021 by Andi
//////////////////////////////////////////////////////////////////////////////////

module dio24_tb # (
    // AXI stream bus
    parameter integer STREAM_DATA_WIDTH  = 128,      // no limits, typically power of 2 from FIFO like 64, 128, etc.
    parameter integer BITS_PER_SAMPLE  = 96,        // 64 (2 ports) or 96 (4 ports)
    
    // AXI Lite slave bus
    parameter integer AXI_DATA_WIDTH = 32,      // must be 32
    parameter integer AXI_ADDR_WIDTH = 7,       // 7: 2^7/4 = 32 registers
    
    // DMA buffer size in samples
    parameter integer DMA_BUF_SIZE = 4032/12,
    
    // reset settings        
    parameter integer FIFO_RESET_DELAY = 10,    // >= 4
    parameter integer FIFO_RESET_CYCLES = 10,   // >= 5
    
    // LEDs and buttons 
    parameter integer NUM_BUTTONS = 2,          // must be 2
    parameter integer NUM_LEDS = 4,             // must be 4
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
    
    // auto-sync
    parameter integer AUTO_SYNC_PULSE_LENGTH = 3,               // 2 = 40ns @ 50MHz 
    parameter integer AUTO_SYNC_PULSE_WAIT   = 5,               // 3 = 60ns @ 50MHz, wait time after pulse
    parameter integer AUTO_SYNC_MAX_PULSES   = 2,               // 2 
    parameter integer AUTO_SYNC_TIME_BITS    = 8,               // 8
    parameter integer AUTO_SYNC_DELAY_BITS   = 10,               // 10
    parameter integer AUTO_SYNC_PHASE_BITS   = 12,               // 12     
    
    // bus data and address bits without strobe bit
    parameter integer BUS_DATA_BITS = 16,       // 16
    parameter integer BUS_ADDR_BITS = 7,        // 7
    
    // special data bits
    parameter integer BIT_NOP = 31,             // 31
    parameter integer BIT_IRQ = 30,             // 30
    //parameter integer BIT_NUM = 29,             // 29
    
    // dio24_timing parameters
    parameter integer CLK_DIV = 5,              // must be >= 4
    parameter integer STRB_DELAY = 2,
    parameter integer STRB_LEN = 2, 
    parameter integer SYNC = 2,                 // 2-3
    
    // irq_FPGA frequency in Hz @ clock/CLK_DIV = 1MHz
    parameter integer IRQ_FREQ = 25,
    
    // TX and RX FIFO
    parameter integer TX_FIFO_DEPTH = 8192,
    parameter integer RX_FIFO_DEPTH = 4096
)
(
    // no inputs or outputs for test bench
    );
    
    // clock and reset settings
    localparam integer PERIOD_FAST = 10;
    localparam integer PERIOD_SLOW = 22;
    localparam integer PHASE_SLOW_PS = 7;            // phase in ns of phase shifted clock
    localparam integer RESET_CYCLES = 5;            // external reset (will be prolonged by dio24_reset module)
    
    localparam integer TIME_ERROR = -50;            // if > 0 sample to introduce time error
        
    // data generator settings
    localparam integer GEN_NUM_SAMPLES = 13;            // if odes not fit into STREAM_DATA_WIDTH will generate error_keep
    localparam integer GEN_DATA_WIDTH = 32;
    localparam integer GEN_TIME_WIDTH = 32;
    localparam integer GEN_DATA_START = 'h0003_0201;    // initial data + address
    localparam integer GEN_DATA_STEP  = 'h0001_0101;    // added in every step
    localparam integer GEN_TIME_START = 'h0000_0003;    // initial time
    localparam integer GEN_TIME_STEP  = 'h0000_0001;    // added in every step
    
    // control and status bits
    localparam integer CTRL_RESET     = 'h0001;         // software RESET bit
    localparam integer CTRL_READY     = 'h0002;         // READY bit
    localparam integer CTRL_RUN       = 'h0004;         // RUN bit
    localparam integer CTRL_64        = 'h01F0_0016;    // config IRQ_IRQ_ALL|RESTART|READY
    localparam integer CTRL_96        = 'h01F0_0116;    // config IRQ_IRQ_ALL|BPS96|RESTART|READY
    localparam integer STATUS_READY   = 'h0002;         // READY
    localparam integer STATUS_RUN     = 'h0206;         // PLL_LOCKED|RUN|READY
    localparam integer STATUS_END     = 'h2208;         // IRQ_END|PLL_LOCKED|END
    localparam integer STATUS_ERROR   = 'h41200;        // ERROR_TIME|IRQ_ERROR|PLL_LOCKED
    localparam integer STATUS_RESET_ACTIVE = 'h0201;    // PLL_LOCKED|RESET
    localparam integer STATUS_RESET_DONE   = 'h0200;    // PLL_LOCKED
    
    // fast clock generator
    reg clk_fast;
    initial begin
        clk_fast = 1'b0;
        forever begin
        clk_fast = #(PERIOD_FAST/2) ~clk_fast;
        end
    end
    
    // slow clock generator
    reg clk_slow;
    initial begin
        clk_slow = 1'b0;
        forever begin
        clk_slow = #(PERIOD_SLOW/2) ~clk_slow;
        end
    end

    // slow PS clock generator
    reg clk_slow_PS;
    initial begin
        clk_slow_PS = 1'b0;
        #PHASE_SLOW_PS;
        forever begin
        clk_slow_PS = #(PERIOD_SLOW/2) ~clk_slow_PS;
        end
    end

    // reset for RESET_CYCLES clk_fast cycles
    // this is the main system reset
    reg reset_n_fast;
    initial begin
        reset_n_fast = 1'b0;
        repeat (RESET_CYCLES) @(posedge clk_fast);
        reset_n_fast = 1'b1;
    end
    
    // reset for RESET_CYCLES clk_slow cycles
    // used only for simulation
    reg reset_n_slow;
    initial begin
        reset_n_slow = 1'b0;
        repeat (RESET_CYCLES) @(posedge clk_slow);
        reset_n_slow = 1'b1;
    end

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
            .M_AXI_ACLK(clk_fast),
            .M_AXI_ARESETN(reset_n_fast),
            
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
    reg [GEN_DATA_WIDTH-1:0] gen_data;
    reg [GEN_TIME_WIDTH-1:0] gen_time;
    reg [(BITS_PER_SAMPLE/8)-1:0] gen_keep = {(BITS_PER_SAMPLE/8){1'b1}};
    reg gen_last;
    reg gen_en;
    reg gen_ctrl;
    reg [31:0] gen_count;
    wire gen_ready;
    wire gen_valid = gen_en & gen_ctrl;
    always @ ( posedge clk_fast ) begin
        if ( reset_n_fast == 1'b0 ) begin
            gen_data <= GEN_DATA_START;
            gen_time <= GEN_TIME_START;
            gen_last <= 1'b0;
            gen_count <= 0;
            gen_en <= 1'b0;
        end
        else if ( gen_count < (GEN_NUM_SAMPLES-1) ) begin
            if ( gen_ready & gen_valid ) begin
                gen_data <= gen_data + GEN_DATA_STEP; 
                gen_time <= ( gen_count == TIME_ERROR ) ? gen_time : gen_time + GEN_TIME_STEP;
                gen_count <= gen_count + 1;
            end
            else begin
                gen_data <= gen_data;
                gen_time <= gen_time;
                gen_count <= gen_count;
            end
            if ( gen_count < (GEN_NUM_SAMPLES-2) ) gen_last <= 1'b0;
            else gen_last <= 1'b1;
            gen_en <= 1'b1;
        end
        else begin
            if ( gen_ready & gen_valid ) begin
                gen_count <= gen_count + 1;
                gen_en <= 1'b0;
            end
            else begin
                gen_count <= gen_count;
                gen_en <= gen_en;        
            end
            gen_data <= gen_data;
            gen_time <= gen_time;
            gen_last <= gen_last;
        end
    end
    
    wire [STREAM_DATA_WIDTH - 1 : 0] gen_data_full;
    if (BITS_PER_SAMPLE == 64) begin
        assign gen_data_full = {gen_data,gen_time};
    end
    else begin
        assign gen_data_full = {~gen_data,gen_data,gen_time};
    end
    
    // combine samples to STREAM_DATA_WIDTH
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
       .clock(clk_fast),
       .reset_n(reset_n_fast),
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
    
    // output data
    wire [STREAM_DATA_WIDTH-1:0] RX_data;
    wire RX_last;
    reg RX_ready;
    wire RX_valid;
    wire [(STREAM_DATA_WIDTH/8)-1:0] out_keep;

    // dio24 module instantiation
    wire reset_active_n;
    reg [NUM_BUTTONS-1:0] buttons_in;
    wire [NUM_LEDS-1:0] leds_out;
    wire [1:0] led_blue;
    reg [1:0] trg_in;
    wire trg_out;
    reg clk_int_locked;
    reg clk_ext_locked;
    wire clk_ext_sel;
    wire bus_enable_n;
    wire [BUS_DATA_BITS-1:0] bus_data;
    wire [BUS_ADDR_BITS-1:0] bus_addr;
    wire bus_strb;
    reg irq_TX = 0;
    reg irq_RX = 0;
    wire irq_FPGA;
    wire sync_out;
    wire sync_en;
    wire sync_mon;
    reg sync_in = 0;
    reg ps_done_ext = 0;
    wire ps_en_ext;
    wire ps_inc_ext;
    reg ps_done_det = 0;
    wire ps_en_det;
    wire ps_inc_det;
    dio24 # (
        .STREAM_DATA_WIDTH(STREAM_DATA_WIDTH),
        .BITS_PER_SAMPLE(BITS_PER_SAMPLE),
        .AXI_DATA_WIDTH(AXI_DATA_WIDTH),
        .AXI_ADDR_WIDTH(AXI_ADDR_WIDTH),
        .DMA_BUF_SIZE(DMA_BUF_SIZE),
        .FIFO_RESET_DELAY(FIFO_RESET_DELAY),
        .FIFO_RESET_CYCLES(FIFO_RESET_CYCLES),
        .NUM_BUTTONS(NUM_BUTTONS),
        .NUM_LEDS(NUM_LEDS),
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
        .AUTO_SYNC_PULSE_LENGTH(AUTO_SYNC_PULSE_LENGTH),
        .AUTO_SYNC_PULSE_WAIT(AUTO_SYNC_PULSE_WAIT),
        .AUTO_SYNC_MAX_PULSES(AUTO_SYNC_MAX_PULSES),
        .AUTO_SYNC_TIME_BITS(AUTO_SYNC_TIME_BITS),
        .AUTO_SYNC_DELAY_BITS(AUTO_SYNC_DELAY_BITS),
        .AUTO_SYNC_PHASE_BITS(AUTO_SYNC_PHASE_BITS),
        .BUS_DATA_BITS(BUS_DATA_BITS),
        .BUS_ADDR_BITS(BUS_ADDR_BITS),
        .BIT_NOP(BIT_NOP),
        .BIT_IRQ(BIT_IRQ),
        .CLK_DIV(CLK_DIV),
        .STRB_DELAY(STRB_DELAY),
        .STRB_LEN(STRB_LEN),
        .SYNC(SYNC),
        .IRQ_FREQ(IRQ_FREQ),
        .TX_FIFO_DEPTH(TX_FIFO_DEPTH),
        .RX_FIFO_DEPTH(RX_FIFO_DEPTH)
    )
    DUT
    (
        // common clock and reset
        .clock_slow(clk_slow),
        .clock_slow_PS(clk_slow_PS),
        .clock_fast(clk_fast),
        .reset_n(reset_n_fast),
        .reset_active_n(reset_active_n),
        
        // FPGA board buttons and RGB LEDs
        .buttons_in(buttons_in),
        .leds_out(leds_out),
        .led_blue(led_blue),
        
        // buffer board start/stop/out trigger
        .trg_start(trg_in[0]),
        .trg_stop(trg_in[1]),
        .trg_out(trg_out),
        
        // buffer board external clock control
        .clk_int_locked(clk_int_locked),  
        .clk_ext_locked(clk_ext_locked),
        .clk_ext_sel(clk_ext_sel),
        
        // rack data bus output
        .bus_enable_n(bus_enable_n),
        .bus_data(bus_data),
        .bus_addr(bus_addr),
        .bus_strb(bus_strb),
        
        // irq I/O
        .irq_TX(irq_TX),
        .irq_RX(irq_RX),
        .irq_FPGA(irq_FPGA),
        
        // auto-sync
        .sync_out(sync_out),
        .sync_en(sync_en),
        .sync_mon(sync_mon),
        .sync_in(sync_in),
        
        // dynamic phase shift of external clock input and detector clock 
        .ps_done_ext(ps_done_ext),
        .ps_en_ext(ps_en_ext),
        .ps_inc_ext(ps_inc_ext),
        .ps_done_det(ps_done_det),
        .ps_en_det(ps_en_det),
        .ps_inc_det(ps_inc_det),
        
        // AXI Lite Slave Bus Interface S00_AXI
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
        .in_data(TX_data),
        .in_last(TX_last),
        .in_ready(TX_ready),
        .in_valid(TX_valid),
        .in_keep(TX_keep),
        
        // AXI stream data output (to DMA stream slave)
        .out_data(RX_data),
        .out_last(RX_last),
        .out_ready(RX_ready),
        .out_valid(RX_valid),
        .out_keep(out_keep)
    );
    
    // timer counter to check output of DUT
    // triggered by bus_strobe
    reg [AXI_DATA_WIDTH-1:0] timer;
    reg [GEN_TIME_WIDTH-1:0] next_time;
    reg [GEN_DATA_WIDTH-1:0] next_data;
    reg [1:0] strb_edge;                  // strobe edge detector
    always @ ( posedge clk_slow ) begin
        if ( reset_n_slow == 1'b0 ) begin
            timer <= 0;
            next_time <= GEN_TIME_START;
            next_data <= GEN_DATA_START;
            strb_edge <= 2'b00;
        end
        else if ( ( bus_enable_n == 1'b0 ) && ( DUT.timing.s_run == 1'b1 ) ) begin // timer is running
            timer <= timer + 1;
            strb_edge <= {strb_edge[0],bus_strb};
            if ( strb_edge == 2'b10 ) begin // falling edge on strobe
                next_time <= next_time + GEN_TIME_STEP;
                next_data <= next_data + GEN_DATA_STEP;
            end
            else begin
                next_time <= next_time;
                next_data <= next_data;
            end
        end
        else begin
            timer <= timer;
            next_time <= next_time;
            next_data <= next_data;
            strb_edge <= strb_edge;
        end
    end    
    
    // check output of DUT
    // stops simulation when DUT gives error or incorrect output
    integer start_time = -1;
    integer e_count = 0;
    task check_DUT;
    begin
        /* start time offset = 2 (timeout @ DUT.timer.cycle = 1) + 2 (first 0's of STRB_BITS) + 1 (edge detection)
        // should be 5 but after some change is now 7. could depend a bit on clock frequency and phase.
        if ((start_time < 0) && (strb_edge == 2'b01) ) begin
            start_time = timer;
            if ( start_time != GEN_TIME_START*CLK_DIV + 7) begin
                $display("%d: start time = %d unexpected?", $time, start_time);
                $finish;
            end
            else begin
                $display("%d: start time = %d (assumed ok)", $time, start_time);
            end
        end
        if (e_count < 5) begin
            if ( ( ( bus_strb == 1'b1 ) && ( bus_data != next_data[BUS_DATA_BITS-1:0]) ) ||
               ( ( bus_strb == 1'b1 ) && ( bus_addr != next_data[(GEN_DATA_WIDTH-1)-:BUS_ADDR_BITS]) ) ||
               ( DUT.error_in != 0 ) || ( DUT.error_out != 0 ) || ( DUT.error_time != 0 )
            ) begin
            e_count = e_count + 1;
            $display("%d: check output!", $time);
            $finish;
            end
        end
        */
        if (DUT.error) begin
            $display("%d: error state!", $time);
            $finish;
        end
    end
    endtask

    // continuously check output state
    initial begin
        forever begin
            @(posedge clk_slow);
            #1
            check_DUT;
        end
    end

    // check final state
    task check_end;
    begin
        if ( 
            ( DUT.control != (CTRL_96 | CTRL_RUN )) ||
            ( DUT.status != STATUS_END ) ||
            ( DUT.num_samples != GEN_NUM_SAMPLES ) ||
            ( DUT.run_en != 1'b1 ) || ( DUT.status_ready != 1'b0 ) ||
            ( bus_data != gen_data[BUS_DATA_BITS-1:0] ) || 
            ( bus_addr != gen_data[(GEN_DATA_WIDTH-1)-:BUS_ADDR_BITS]) ||
            ( bus_strb != 1'b0 ) ||
            ( bus_enable_n != 1'b1 )
            
        ) begin
            $display("%d: check final state!", $time);
            $finish;
        end
        else begin
            $display("%d *** final state ok! ***", $time);
        end
    end
    endtask
    

    // simulation
    initial begin
      $display("%d *** start simulation *** ", $time);
      
      // init registers
      buttons_in = 2'b00;
      trg_in = 2'b00;
      clk_int_locked = 1'b0;
      clk_ext_locked = 1'b0;
      gen_ctrl = 1'b0;
      RX_ready = 1'b0;
      
      // init AXI Lite interface
      AXI_wr_data = 0;
      AXI_wr_addr = 0;
      AXI_wr_valid = 1'b0;
      AXI_rd_addr = 0;
      AXI_rd_ready = 1'b0;

      // wait for reset to finish
      @(posedge reset_n_fast);

      // internal reset waits for PLL to be locked
      repeat(10) @(posedge clk_slow);
      #1 
      clk_int_locked = 1'b1;      
      
      // wait for FIFO reset to finish
      while ( (DUT.reset_n_fast == 1'b0) || (DUT.reset_n_slow == 1'b0) ) begin 
        @(posedge clk_fast);
      end

      // AXI Lite interface: set control bits: SERVER READY
      if ( DUT.control != 0 ) begin
        $display("%d control is not 0!?", $time);
        $finish;
      end
      repeat(10) @(posedge clk_fast);
      #1
      AXI_wr_valid = 1'b1;
      AXI_wr_addr = 0*4;
      AXI_wr_data = CTRL_READY;
      @(posedge clk_fast);
      #1
      AXI_wr_valid = 1'b0;
      // wait until data written
      while ( AXI_wr_ready == 1'b0 ) begin 
        @(posedge clk_fast);
      end
      repeat(1) @(posedge clk_fast);
      if ( DUT.control != STATUS_READY ) begin
        $display("%d SERVER READY bit is not set!?", $time);
        $finish;
      end
      else begin
        $display("%d *** SERVER READY! *** ", $time);
      end

      // AXI Lite interface: write some test bits      
      #1
      AXI_wr_valid = 1'b1;
      AXI_wr_addr = 1*4;
      AXI_wr_data = 32'h1010_1111;
      @(posedge clk_fast);
      #1
      AXI_wr_valid = 1'b0;
      // wait until data written
      while ( AXI_wr_ready == 1'b0 ) begin 
        @(posedge clk_fast);
      end
      repeat(1) @(posedge clk_fast);
      if ( DUT.ctrl_test != 32'h1010_1111 ) begin
        $display("%d TEST bits are not set!?", $time);
        $finish;
      end
      else begin
        $display("%d *** TEST BITS OK *** ", $time);
      end

      // AXI Lite interface: write configuration bits
      #1
      AXI_wr_valid = 1'b1;
      AXI_wr_addr = 0*4;
      AXI_wr_data = CTRL_96;
      @(posedge clk_fast);
      #1
      AXI_wr_valid = 1'b0;
      // wait until data written
      while ( AXI_wr_ready == 1'b0 ) begin 
        @(posedge clk_fast);
      end
      repeat(1) @(posedge clk_fast);
      if ( DUT.control != CTRL_96 ) begin
        $display("%d CONFIG bit are not set!?", $time);
        $finish;
      end
      else begin
        $display("%d *** CONFIG OK *** ", $time);
      end

      // AXI Lite interface: write NUM_SAMPLES
      if ( DUT.num_samples != 0 ) begin
        $display("%d NUM_SAMPLES not 0!?", $time);
        $finish;
      end
      if ( AXI_wr_ready != 1'b1 ) begin
        $display("%d AXI write not ready!?", $time);
        $finish;
      end
      #1
      AXI_wr_data = GEN_NUM_SAMPLES;
      AXI_wr_addr = 2 * 4;
      AXI_wr_valid = 1'b1;
      @(posedge clk_fast);
      #1
      AXI_wr_valid = 1'b0;
      // wait until data written
      while ( AXI_wr_ready == 1'b0 ) begin 
        @(posedge clk_fast);
      end
      repeat(2) @(posedge clk_fast);
      if ( DUT.num_samples == GEN_NUM_SAMPLES ) begin
        $display("%d *** NUM_SAMPLES written (ok) *** ", $time);
      end
      else begin
        $display("%d NUM_SAMPLES writing error!", $time);
        $finish;
      end
      
      // after num_samples written we can generate TX data
      repeat(5) @(posedge clk_fast);
      gen_ctrl = 1'b1;
      
      // AXI Lite interface: read NUM_SAMPLES
      #1
      AXI_rd_addr = 2*4;
      AXI_rd_ready = 1'b1;
      @(posedge clk_fast);
      #1
      // wait until data read
      while ( AXI_rd_valid == 1'b0 ) begin 
        @(posedge clk_fast);
      end
      repeat(1) @(posedge clk_fast);
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
        @(posedge clk_fast);
      end
      $display("%d *** READY! *** ", $time);

      // AXI Lite interface: set RUNl
      repeat(125) @(posedge clk_fast);
      #1
      AXI_wr_valid = 1'b1;
      AXI_wr_addr = 0*4;
      AXI_wr_data = CTRL_RUN | CTRL_96;
      @(posedge clk_fast);
      #1
      AXI_wr_valid = 1'b0;
      // wait until data written
      while ( AXI_wr_ready == 1'b0 ) begin 
        @(posedge clk_fast);
      end
      repeat(1) @(posedge clk_fast);
      if ( ( DUT.run_en != 1'b1 ) || ( DUT.control != (CTRL_RUN|CTRL_96) ) ) begin
        $display("%d RUN bit is not set!?", $time);
        $finish;
      end
      else begin
        $display("%d *** RUN! *** ", $time);
      end

      // wait until all data output
      while ( DUT.status_end != 1'b1 ) begin 
        @(posedge clk_fast);
      end

      repeat(20) @(posedge clk_fast);
      check_end;
      
      // AXI Lite interface: activeate software reset
      repeat(125) @(posedge clk_fast);
      #1
      AXI_wr_valid = 1'b1;
      AXI_wr_addr = 0*4;
      AXI_wr_data = CTRL_RESET;
      @(posedge clk_fast);
      #1
      AXI_wr_valid = 1'b0;
      // wait until data written
      while ( AXI_wr_ready == 1'b0 ) begin 
        @(posedge clk_fast);
      end
      if ( DUT.control != CTRL_RESET ) begin    // only active for 1 fast cycle
        $display("%d not in RESET mode!?", $time);
        $finish;
      end
      else begin
        $display("%d *** software RESET! *** ", $time);
      end

      // wait until slow reset
      while ( DUT.status != STATUS_RESET_ACTIVE ) begin 
        @(posedge clk_fast);
      end
      $display("%d *** software RESET active! *** ", $time);

      // wait until reset is done
      while ( ( DUT.status != STATUS_RESET_DONE ) || ( DUT.control != 0 ) ) begin 
        @(posedge clk_fast);
      end
      $display("%d *** software RESET done! *** ", $time);

      repeat(20) @(posedge clk_fast);

      $display("%d *** finished *** ", $time);
      $finish;
    
    end    
endmodule
