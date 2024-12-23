`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// control_in_mux.v 
// multiplexer for control in registers
// created 06/05/2023 by Andi
// last change 4/12/2024 by Andi
// TODO: this needs to be simulated carefully again!
//////////////////////////////////////////////////////////////////////////////////

module ctrl_in_mux 
(
    clock_bus,
    clock_det,
    reset_bus_n,
    reset_det_n,

    ctrl_in0_det,
    ctrl_in0_bus,
    ctrl_in1_bus,

    ext_in,

    run_en,

    data_reload,
    data_reload_ff,
    in_valid,
    first_sample,
    state_run,
    state_wait,
    state_restart,  
    data,

    trg_start_en,
    trg_start_pulse,
    trg_start_tgl,
    trg_start_tgl_det,
    trg_stop_en,
    trg_stop_pulse,
    trg_stop_tgl,
    trg_restart_en,
    trg_restart_pulse,
    trg_restart_tgl,

    data_stop,
    data_nop,
    data_irq
);

    //////////////////////////////////////////////////////////////////////////////////
    // parameters
    
    `include "ctrl_in_params.vh"

    // regiser data width must be 32
    parameter integer REG_WIDTH                 = 32;
    // number of external inputs
    parameter integer NUM_IN                    = 3;
    // synchronization stages
    parameter integer SYNC                      = 2;
    // size of input data pipeline 0 or 2
    parameter integer IN_DATA_BUF               = 2;
    
    //////////////////////////////////////////////////////////////////////////////////
    // ports

    // clock and reset
    input wire clock_bus;
    input wire clock_det;
    input wire reset_bus_n;
    input wire reset_det_n;
    // control register
    input wire [REG_WIDTH-1:0] ctrl_in0_det; // @ clock_det
    input wire [REG_WIDTH-1:0] ctrl_in0_bus;
    input wire [REG_WIDTH-1:0] ctrl_in1_bus;
    // I/O @ clk_bus
    input wire [NUM_IN-1:0] ext_in;
    // run enable bit
    input wire run_en;
    // input data
    input wire data_reload;     // reload buffer
    input wire data_reload_ff;  // data_reload delayed by one cycle
    input wire in_valid;        // data valid one cycle after data_reload
    input wire first_sample;    // for first sample strobe is ignored
    input wire state_run;       // running or waiting state
    input wire state_wait;      // waiting state
    input wire state_restart;   // restart state at end of cycle 
    input wire [REG_WIDTH-1:0] data;
    // multiplexed trigger outputs
    output wire trg_start_en;
    output wire trg_start_pulse;
    output wire trg_start_tgl;
    output wire trg_start_tgl_det; // @ clock_det
    output wire trg_stop_en;
    output wire trg_stop_pulse;
    output wire trg_stop_tgl;
    output wire trg_restart_en;
    output wire trg_restart_pulse;
    output wire trg_restart_tgl;
    // registered data bit outputs
    output wire data_stop;
    output wire data_nop;
    output wire data_irq;
    
    //////////////////////////////////////////////////////////////////////////////////
    // bus clock domain @ clock_bus

    // latency of DATA multiplexer
    localparam integer DATA_MUX_LATENCY = 1;

    localparam integer CTRL_16_BITS     = 4;                    // ctrl bits of 16:1
    localparam integer CTRL_32_BITS     = 5;                    // ctrl bits of 32:1
    localparam integer CTRL_64_BITS     = 6;                    // ctrl bits of 32:1
    localparam integer NUM_SRC_16       = (1<<CTRL_16_BITS);    // 16
    localparam integer NUM_SRC_32       = (1<<CTRL_32_BITS);    // 32
    localparam integer NUM_SRC_64       = (1<<CTRL_64_BITS);    // 64
        
    // assign control_trg register @ clk_bus
    wire [CTRL_16_BITS -1:0] ctrl_in_start   = ctrl_in0_bus[CTRL_IN0_DST_TRG_START  *CTRL_IN_SRC_BITS +: CTRL_16_BITS    ];
    wire [CTRL_64_BITS -1:0] ctrl_in_stop    = ctrl_in0_bus[CTRL_IN0_DST_TRG_STOP   *CTRL_IN_SRC_BITS +: CTRL_64_BITS    ];
    wire [CTRL_16_BITS -1:0] ctrl_in_restart = ctrl_in0_bus[CTRL_IN0_DST_TRG_RESTART*CTRL_IN_SRC_BITS +: CTRL_16_BITS    ];
    wire [CTRL_32_BITS   :0] ctrl_in_nop     = ctrl_in1_bus[CTRL_IN1_DST_DATA_NOP   *CTRL_IN_SRC_BITS +: CTRL_32_BITS + 1];
    wire [CTRL_32_BITS   :0] ctrl_in_irq     = ctrl_in1_bus[CTRL_IN1_DST_DATA_IRQ   *CTRL_IN_SRC_BITS +: CTRL_32_BITS + 1];
    wire [CTRL_32_BITS   :0] ctrl_in_strb    = ctrl_in1_bus[CTRL_IN1_DST_DATA_STRB  *CTRL_IN_SRC_BITS +: CTRL_32_BITS + 1];
    
    wire [NUM_SRC_64-1:0] src;
    assign src  [CTRL_IN_SRC_NONE               ] = 1'b0;
    if (NUM_IN >= 1) begin
        reg ext_in0_ff;
        always @ ( posedge clock_bus ) begin
            ext_in0_ff <= ext_in[0]; 
        end
        assign src  [CTRL_IN_SRC_IN0            ] =  ext_in[0];
        assign src  [CTRL_IN_SRC_IN0_INV        ] = ~ext_in[0];
        assign src  [CTRL_IN_SRC_IN0_EDGE_POS   ] = ({ext_in0_ff, ext_in[0]} == 2'b01);
        assign src  [CTRL_IN_SRC_IN0_EDGE_NEG   ] = ({ext_in0_ff, ext_in[0]} == 2'b10);
    end
    else begin
        assign src  [CTRL_IN_SRC_IN0            ] = 1'b0;
        assign src  [CTRL_IN_SRC_IN0_INV        ] = 1'b0;
        assign src  [CTRL_IN_SRC_IN0_EDGE_POS   ] = 1'b0;
        assign src  [CTRL_IN_SRC_IN0_EDGE_NEG   ] = 1'b0;
    end
    
    if (NUM_IN >= 2) begin
        reg ext_in1_ff;
        always @ ( posedge clock_bus ) begin
            ext_in1_ff <= ext_in[1]; 
        end
        assign src  [CTRL_IN_SRC_IN1            ] =  ext_in[1];
        assign src  [CTRL_IN_SRC_IN1_INV        ] = ~ext_in[1];
        assign src  [CTRL_IN_SRC_IN1_EDGE_POS   ] = ({ext_in1_ff, ext_in[1]} == 2'b01);
        assign src  [CTRL_IN_SRC_IN1_EDGE_NEG   ] = ({ext_in1_ff, ext_in[1]} == 2'b10);
    end
    else begin
        assign src  [CTRL_IN_SRC_IN1            ] = 1'b0;
        assign src  [CTRL_IN_SRC_IN1_INV        ] = 1'b0;
        assign src  [CTRL_IN_SRC_IN1_EDGE_POS   ] = 1'b0;
        assign src  [CTRL_IN_SRC_IN1_EDGE_NEG   ] = 1'b0;
    end
    
    if (NUM_IN >= 3) begin
        reg ext_in2_ff;
        always @ ( posedge clock_bus ) begin
            ext_in2_ff <= ext_in[2]; 
        end    
        assign src  [CTRL_IN_SRC_IN2            ] =  ext_in[2];
        assign src  [CTRL_IN_SRC_IN2_INV        ] = ~ext_in[2];
        assign src  [CTRL_IN_SRC_IN2_EDGE_POS   ] = ({ext_in2_ff, ext_in[2]} == 2'b01);
        assign src  [CTRL_IN_SRC_IN2_EDGE_NEG   ] = ({ext_in2_ff, ext_in[2]} == 2'b10);
    end
    else begin
        assign src  [CTRL_IN_SRC_IN2            ] = 1'b0;
        assign src  [CTRL_IN_SRC_IN2_INV        ] = 1'b0;
        assign src  [CTRL_IN_SRC_IN2_EDGE_POS   ] = 1'b0;
        assign src  [CTRL_IN_SRC_IN2_EDGE_NEG   ] = 1'b0;
    end
    
    assign src [CTRL_IN_SRC_UNUSED_13           ] = 1'b0;
    assign src [CTRL_IN_SRC_UNUSED_14           ] = 1'b0;
    assign src [CTRL_IN_SRC_UNUSED_15           ] = 1'b0;
    assign src [CTRL_IN_SRC_UNUSED_16           ] = 1'b0;
    assign src [CTRL_IN_SRC_UNUSED_17           ] = 1'b0;
    assign src [CTRL_IN_SRC_UNUSED_18           ] = 1'b0;
    assign src [CTRL_IN_SRC_UNUSED_19           ] = 1'b0;
    assign src [CTRL_IN_SRC_UNUSED_20           ] = 1'b0;
    assign src [CTRL_IN_SRC_UNUSED_21           ] = 1'b0;
    assign src [CTRL_IN_SRC_UNUSED_22           ] = 1'b0;
    assign src [CTRL_IN_SRC_UNUSED_23           ] = 1'b0;
    assign src [CTRL_IN_SRC_UNUSED_24           ] = 1'b0;
    assign src [CTRL_IN_SRC_UNUSED_25           ] = 1'b0;
    assign src [CTRL_IN_SRC_UNUSED_26           ] = 1'b0;
    assign src [CTRL_IN_SRC_UNUSED_27           ] = 1'b0;
    assign src [CTRL_IN_SRC_UNUSED_28           ] = 1'b0;
    assign src [CTRL_IN_SRC_UNUSED_29           ] = 1'b0;
    assign src [CTRL_IN_SRC_UNUSED_30           ] = 1'b0;
    assign src [CTRL_IN_SRC_UNUSED_31           ] = 1'b0;
    
    assign src  [CTRL_IN_SRC_DATA_0             ] = data[0];
    assign src  [CTRL_IN_SRC_DATA_1             ] = data[1];
    assign src  [CTRL_IN_SRC_DATA_2             ] = data[2];
    assign src  [CTRL_IN_SRC_DATA_3             ] = data[3];
    assign src  [CTRL_IN_SRC_DATA_4             ] = data[4];
    assign src  [CTRL_IN_SRC_DATA_5             ] = data[5];
    assign src  [CTRL_IN_SRC_DATA_6             ] = data[6];
    assign src  [CTRL_IN_SRC_DATA_7             ] = data[7];    
    assign src  [CTRL_IN_SRC_DATA_8             ] = data[8];
    assign src  [CTRL_IN_SRC_DATA_9             ] = data[9];
    assign src  [CTRL_IN_SRC_DATA_10            ] = data[10];
    assign src  [CTRL_IN_SRC_DATA_11            ] = data[11];
    assign src  [CTRL_IN_SRC_DATA_12            ] = data[12];
    assign src  [CTRL_IN_SRC_DATA_13            ] = data[13];
    assign src  [CTRL_IN_SRC_DATA_14            ] = data[14];
    assign src  [CTRL_IN_SRC_DATA_15            ] = data[15];
    assign src  [CTRL_IN_SRC_DATA_16            ] = data[16];
    assign src  [CTRL_IN_SRC_DATA_17            ] = data[17];
    assign src  [CTRL_IN_SRC_DATA_18            ] = data[18];
    assign src  [CTRL_IN_SRC_DATA_19            ] = data[19];
    assign src  [CTRL_IN_SRC_DATA_20            ] = data[20];
    assign src  [CTRL_IN_SRC_DATA_21            ] = data[21];
    assign src  [CTRL_IN_SRC_DATA_22            ] = data[22];
    assign src  [CTRL_IN_SRC_DATA_23            ] = data[23];
    assign src  [CTRL_IN_SRC_DATA_24            ] = data[24];
    assign src  [CTRL_IN_SRC_DATA_25            ] = data[25];
    assign src  [CTRL_IN_SRC_DATA_26            ] = data[26];
    assign src  [CTRL_IN_SRC_DATA_27            ] = data[27];
    assign src  [CTRL_IN_SRC_DATA_28            ] = data[28];
    assign src  [CTRL_IN_SRC_DATA_29            ] = data[29];
    assign src  [CTRL_IN_SRC_DATA_30            ] = data[30];
    assign src  [CTRL_IN_SRC_DATA_31            ] = data[31];
    
    // MUX start trigger @ clk_bus
    wire start_trg_en = (ctrl_in_start[CTRL_16_BITS-1:0] != 0);
    wire start_trg;
    mux_16_to_1 # (
        .BUFFERED   (1)
        )
    mux_trg_start (
        .clk        (clock_bus),
        .ctrl       (ctrl_in_start[CTRL_16_BITS-1:0]),
        .in         (src          [NUM_SRC_16  -1:0]),
        .out        (start_trg)
    );
          
    // generate start trigger positive edge pulse
    // set when enabled and run bit enabled and mux_trg_start output is high and not already generated
    // not already generated (start_trg_ff) is reset with ~run_en or restart state at end of cycle
    reg start_trg_ff    = 1'b0;
    reg start_trg_tgl   = 1'b0;
    wire start_trg_pulse_w = ({start_trg,start_trg_ff} == 2'b10);
    always @ ( posedge clock_bus ) begin
        if (reset_bus_n == 1'b0) begin
            start_trg_ff    <= 1'b0;
            start_trg_tgl   <= 1'b0;
        end
        else if ( run_en & start_trg_en ) begin
            start_trg_ff    <= start_trg_pulse_w ? 1'b1 : state_restart ? 1'b0 : start_trg_ff;
            start_trg_tgl   <= start_trg_pulse_w ? ~start_trg_tgl : start_trg_tgl;
        end
        else begin
            start_trg_ff    <= 1'b0;
            start_trg_tgl   <= start_trg_tgl;
        end
    end
    assign trg_start_en    = start_trg_en;
    assign trg_start_pulse = start_trg_pulse_w; // latency from ext_in: 3 clock_bus cycles and is only used in state machine.
    assign trg_start_tgl   = start_trg_tgl;

    // MUX stop trigger @ clk_bus
    // trigger enabled when lowest 4 bits != 0 and higher 2 bits are 0
    // when higest bit is enabled then data stop trigger enabled (see below).
    wire stop_trg_en  = (ctrl_in_stop[CTRL_16_BITS-1:0] != 0) & (ctrl_in_stop[CTRL_32_BITS:CTRL_16_BITS] == 2'b00);
    wire stop_trg;
    mux_16_to_1 # (
        .BUFFERED       (1)
        )
    mux_trg_stop (
        .clk        (clock_bus),
        .ctrl       (ctrl_in_stop[CTRL_16_BITS-1:0]),
        .in         (src         [NUM_SRC_16  -1:0]),
        .out        (stop_trg)
    );
     
    // generate stop trigger positive edge pulse
    // set when enabled and in running state and mux_trg_stop output is high and not already generated
    // not already generated (stop_trg_ff) is reset with ~state_run or state_wait
    reg stop_trg_ff    = 1'b0;
    reg stop_trg_tgl   = 1'b0;
    wire stop_trg_pulse_w = ({stop_trg,stop_trg_ff} == 2'b10);
    wire restart_trg_pulse_w;
    always @ ( posedge clock_bus ) begin
        if (reset_bus_n == 1'b0) begin
            stop_trg_ff    <= 1'b0;
            stop_trg_tgl   <= 1'b0;
        end
        else if ( state_run & (~state_wait) & stop_trg_en ) begin
            stop_trg_ff    <= stop_trg_pulse_w ? 1'b1 : stop_trg_ff;
            stop_trg_tgl   <= stop_trg_pulse_w ? ~stop_trg_tgl : stop_trg_tgl;
        end
        else begin
            stop_trg_ff    <= 1'b0;
            stop_trg_tgl   <= stop_trg_tgl;
        end
    end
    assign trg_stop_en    = stop_trg_en;
    assign trg_stop_pulse = stop_trg_pulse_w; // latency from ext_in: 3 clock_bus cycles and is only used in state machine.
    assign trg_stop_tgl   = stop_trg_tgl;

    // MUX restart trigger @ clk_bus
    wire restart_trg_en = (ctrl_in_restart[CTRL_16_BITS-1:0] != 0);
    wire restart_trg;
    mux_16_to_1 # (
        .BUFFERED      (1)
        )
    mux_trg_restart (
        .clk        (clock_bus),
        .ctrl       (ctrl_in_restart[CTRL_16_BITS-1:0]),
        .in         (src            [NUM_SRC_16  -1:0]),
        .out        (restart_trg)
    );
          
    // generate restart trigger positive edge pulse
    // set when enabled and in waiting state and mux_trg_restart output is high and not already generated
    // not already generated (restart_trg_ff) is reset with ~state_wait
    reg restart_trg_ff    = 1'b0;
    reg restart_trg_tgl   = 1'b0;
    assign restart_trg_pulse_w = ({restart_trg,restart_trg_ff} == 2'b10);
    always @ ( posedge clock_bus ) begin
        if (reset_bus_n == 1'b0) begin
            restart_trg_ff    <= 1'b0;
            restart_trg_tgl   <= 1'b0;
        end
        else if ( state_wait & restart_trg_en ) begin
            restart_trg_ff    <= restart_trg_pulse_w ? 1'b1 : restart_trg_ff;
            restart_trg_tgl   <= restart_trg_pulse_w ? ~restart_trg_tgl : restart_trg_tgl;
        end
        else begin
            restart_trg_ff    <= 1'b0;
            restart_trg_tgl   <= restart_trg_tgl;
        end
    end
    assign trg_restart_en    = restart_trg_en;
    assign trg_restart_pulse = restart_trg_pulse_w; // latency from ext_in: 3 clock_bus cycles and is only used in state machine.
    assign trg_restart_tgl   = restart_trg_tgl;    
    
	//////////////////////////////////////////////////////////////////////////////////
    // detection clock domain @ clock_det

    // trg_start_tgl CDC from clock_bus to clock_det
    // note: this has at least SYNC cycles delay vs. trg_start_tgl
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1:0] cdc_det;    
    always @ ( posedge clock_det ) begin
        cdc_det <= {cdc_det[SYNC-2:0],trg_start_tgl};
    end
    assign trg_start_tgl_det = cdc_det[SYNC-1];    
    
	//////////////////////////////////////////////////////////////////////////////////
    // special data bits @ clk_bus
    // TODO: in original code mux was not buffered and was fine but now its larger.
    //       when buffered we get a 1 cycle delay,
    //       which means we have to delay data_reload_ff by another cycle!
    // TODO: mux_32_to_1 is even 2x buffered in standard config. 
    //       to match timing set BUFFER_MUX16 = 0.

    // MUX data NOP bit @ clk_bus
    wire data_nop_en = ctrl_in_nop[CTRL_32_BITS];
    wire data_nop_w;
    mux_32_to_1 # (
        .BUFFER_OUT     (1),
        .BUFFER_MUX16   (0)
        )
    mux_nop (
        .clk        (clock_bus),
        .ctrl       (ctrl_in_nop[CTRL_32_BITS-1  : 0]),
        .in         (src        [NUM_SRC_64  -1 -: NUM_SRC_32]),
        .en         (data_nop_en), 
        .out        (data_nop_w)
    );
    
    // MUX data STOP bit @ clk_bus
    // data stop enabled when highest bit is set
    wire data_stop_en = ctrl_in_stop[CTRL_32_BITS];
    wire data_stop_w;
    mux_32_to_1 # (
        .BUFFER_OUT     (1),
        .BUFFER_MUX16   (0)
        )
    mux_stop (
        .clk        (clock_bus),
        .ctrl       (ctrl_in_stop[CTRL_32_BITS-1  : 0]),
        .in         (src         [NUM_SRC_64  -1 -: NUM_SRC_32]),
        .en         (data_stop_en), 
        .out        (data_stop_w)
    );
    
    // MUX data IRQ bit @ clk_bus
    wire data_irq_en = ctrl_in_irq[CTRL_32_BITS];
    wire data_irq_w;
    mux_32_to_1 # (
        .BUFFER_OUT     (1),
        .BUFFER_MUX16   (0)
        )
    mux_irq (
        .clk        (clock_bus),
        .ctrl       (ctrl_in_irq[CTRL_32_BITS-1  : 0]),
        .in         (src        [NUM_SRC_64  -1 -: NUM_SRC_32]),
        .en         (data_irq_en), 
        .out        (data_irq_w)
    );
    
    // MUX data STRB bit @ clk_bus
    wire data_strb_en = ctrl_in_strb[CTRL_32_BITS];
    wire data_strb_w;
    mux_32_to_1 # (
        .BUFFER_OUT     (1),
        .BUFFER_MUX16   (0)
        )
    mux_strb (
        .clk        (clock_bus),
        .ctrl       (ctrl_in_strb[CTRL_32_BITS-1  : 0]),
        .in         (src         [NUM_SRC_64  -1 -: NUM_SRC_32]),
        .en         (data_strb_en), 
        .out        (data_strb_w)
    );

    if (IN_DATA_BUF >= 2) begin
    
        // input data multiplexer and pipeline
        reg [IN_DATA_BUF-1:0] data_nop_ff  = {(IN_DATA_BUF){1'b0}};
        reg [IN_DATA_BUF-1:0] data_stop_ff = {(IN_DATA_BUF){1'b0}};
        reg [IN_DATA_BUF-1:0] data_irq_ff  = {(IN_DATA_BUF){1'b0}};
        reg data_strb_ff;
        integer i;
        always @ ( posedge clock_bus ) begin
            if ( reset_bus_n == 1'b0 ) begin
                data_nop_ff   <= {(IN_DATA_BUF){1'b0}};
                data_stop_ff  <= {(IN_DATA_BUF){1'b0}};
                data_irq_ff   <= {(IN_DATA_BUF){1'b0}};
                data_strb_ff  <= 1'b0;
            end
            else if ( data_reload ) begin
                // note: in_valid is only valid at data_reload_ff
                data_nop_ff [DATA_MUX_LATENCY] <= ((data_nop_en  & data_nop_w) |
                                                   (data_strb_en & (~first_sample) & (~(data_strb_w ^ data_strb_ff))));
                data_stop_ff[DATA_MUX_LATENCY] <=  (data_stop_en & data_stop_w);                            
                data_irq_ff [DATA_MUX_LATENCY] <=  (data_irq_ff  & data_irq_w);
                for (i=DATA_MUX_LATENCY+1; i < IN_DATA_BUF; i=i+1) begin
                    data_nop_ff [i] <= data_nop_ff [i-1] & in_valid;
                    data_stop_ff[i] <= data_stop_ff[i-1] & in_valid;
                    data_irq_ff [i] <= data_irq_ff [i-1] & in_valid;
                end
                data_strb_ff <= data_strb_w;
            end
        end
        
        // assign output data bits
        assign data_stop = data_stop_ff[IN_DATA_BUF-1];
        assign data_nop  = data_nop_ff [IN_DATA_BUF-1];
        assign data_irq  = data_irq_ff [IN_DATA_BUF-1];
    
    end
    else begin
        // no input data buffer

        // combine data bits when enabled
        reg data_nop_ff    = 1'b0;
        reg data_stop_ff   = 1'b0;
        reg data_irq_ff    = 1'b0;
        reg data_strb_ff   = 1'b0;
        wire data_ready;
        always @ ( posedge clock_bus ) begin
            if ( reset_bus_n == 1'b0 ) begin
                data_nop_ff    <= 1'b0;
                data_stop_ff   <= 1'b0;
                data_irq_ff    <= 1'b0;
                data_strb_ff   <= 1'b0;
            end
            else begin
                if ( data_ready & in_valid ) begin
                    data_nop_ff   <= (data_nop_en  & data_nop_w) |
                                     (data_strb_en & (~first_sample) & (~(data_strb_w ^ data_strb_ff)));
                    data_stop_ff  <= data_stop_en & data_stop_w;                    
                    data_irq_ff   <= data_irq_ff  & data_irq_w;
                    data_strb_ff  <= data_strb_w;
                end
            end
        end
    
       if ( DATA_MUX_LATENCY == 0 ) begin
            // no delay of multiplexer
            assign data_ready = data_reload_ff;
       end
       else if ( DATA_MUX_LATENCY == 1 ) begin
            // 1 cycle delay of multiplexer 
            reg data_reload2_ff = 1'b0;
            always @ ( posedge clock_bus ) begin
                data_reload2_ff <= data_reload_ff;
            end
            assign data_ready = data_reload2_ff; 
       end
       else begin
            // >=2 cycles delay of multiplexer 
            reg [DATA_MUX_LATENCY-1 : 0] data_reload2_ff = {DATA_MUX_LATENCY{1'b0}};
            always @ ( posedge clock_bus ) begin
                data_reload2_ff <= {data_reload2_ff[DATA_MUX_LATENCY-2:0],data_reload_ff};
            end
            assign data_ready = data_reload2_ff; 
       end

        // assign output data bits
        assign data_nop  = data_nop_ff;
        assign data_stop = data_stop_ff;
        assign data_irq  = data_irq_ff;
        
    end
                
endmodule
