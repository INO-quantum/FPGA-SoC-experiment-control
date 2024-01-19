`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// cdc.v 
// clock domain crossing module for multi-bit signals.
// adapted from CummingsSNUG2008Boston_CDC_clock_domain_crossings.pdf figures 21 and 22.
// out_ready signal can be asserted before out_valid. out_valid asserted with out_data.
// created 25/06/2020 by Andi
// last change 26/06/2020
// notes:
// - latency = 4 out_clock cycles
// - if USE_OUT_READY == "YES" out_ready signal is used (fig. 22), 
//   otherwise not (fig. 21) and out_valid pulses when out_data has changed.
//   second case behaves as first case with out_ready = 1'b1.
// - for contiguous stream of data one can set in_valid = 1'b1 permanently.
//////////////////////////////////////////////////////////////////////////////////

module cdc # (
        parameter integer DATA_WIDTH = 2,       // data bits
        parameter integer SYNC = 2,             // synchronization stages 2-3
        parameter USE_OUT_READY = "YES"         // YES or NO 
    )
    (
        // input
        input in_clock,
        input in_reset_n,
        input [DATA_WIDTH-1:0] in_data,
        input in_valid,
        output in_ready,
        // output
        input out_clock,
        input out_reset_n,
        output [DATA_WIDTH-1:0] out_data,
        output out_valid,
        input out_ready
    );
    
    //////////////////////////////////////////////////////////////////////////////////
    // signals between clock domains
    //////////////////////////////////////////////////////////////////////////////////
    
    reg [DATA_WIDTH-1:0] in_data_ff = {DATA_WIDTH{1'b0}};   // in -> out data
    reg in_en = 1'b0;                                       // in -> out data ready toggle
    wire out_ack;                                           // out -> in ready toggle
    
    //////////////////////////////////////////////////////////////////////////////////
    // input clock domain
    //////////////////////////////////////////////////////////////////////////////////
    
    // input ready state machine
    // set with ack signal, reset when valid signal
    // additional RESET state is needed if in_valid = 1'b1 permanently,
    // which allows to set in_ready = 1'b1 before loading of first data.
    localparam integer RESET = 2'b00;
    localparam integer READY = 2'b01;
    localparam integer NOT_READY = 2'b11; 
    reg [1:0] in_state = RESET;
    reg in_ready_ff = 1'b0;
    wire in_ack;
    always @ ( posedge in_clock ) begin
        if ( in_reset_n == 1'b0 ) begin
            in_state <= RESET;
            in_ready_ff <= 1'b0;
        end
        else begin
            case ( in_state )
                READY:      
                    if ( in_valid ) begin
                        in_state <= NOT_READY;
                        in_ready_ff <= 1'b0;
                    end
                    else begin
                        in_state <= READY;
                        in_ready_ff <= 1'b1;
                    end
                NOT_READY:
                    if ( in_ack ) begin
                        in_state <= READY;
                        in_ready_ff <= 1'b1;
                    end
                    else begin
                        in_state <= NOT_READY;
                        in_ready_ff <= 1'b0;
                    end
                default: // reset state
                    begin
                        in_state <= READY;
                        in_ready_ff <= 1'b1;
                    end
            endcase
        end
    end
    assign in_ready = in_ready_ff;
    
    // transmit data register
    wire in_load = in_valid & in_ready;
    always @ ( posedge in_clock ) begin
        if ( in_reset_n == 1'b0 ) in_data_ff <= 0;
        else in_data_ff <= in_load ? in_data : in_data_ff; 
    end
    
    // enable toggle signal
    always @ ( posedge in_clock ) begin
        if ( in_reset_n == 1'b0 ) in_en <= 1'b0;
        else in_en <= in_load ^ in_en;  
    end
    
    // in_ack feedback pulse
    sync_pgen # (.SYNC(SYNC))
    out_to_in_ack (
        .out_clock(in_clock),
        .out_reset_n(in_reset_n),
        .in_signal(out_ack),
        .out_signal(), // not used
        .out_pulse(in_ack)
    );

    //////////////////////////////////////////////////////////////////////////////////
    // output clock domain
    //////////////////////////////////////////////////////////////////////////////////
    
    // out enable pulse
    wire out_toggle;
    wire out_load;
    sync_pgen # (.SYNC(SYNC))
    in_to_out_enable (
        .out_clock(out_clock),
        .out_reset_n(out_reset_n),
        .in_signal(in_en),
        .out_signal(out_toggle),
        .out_pulse(out_load)
    );
    
    // receive data register
    reg [DATA_WIDTH-1:0] out_data_ff = 0;
    always @ ( posedge out_clock ) begin
        if ( out_reset_n == 1'b0 ) out_data_ff <= 0;
        else out_data_ff <= out_load ? in_data_ff : out_data_ff; 
    end
    assign out_data = out_data_ff;
    
    if ( USE_OUT_READY == "YES" ) begin : RDY_ACK
    
        // output valid state machine
        // set with out_en signal, reset with out_ready signal
        localparam integer VALID = 1'b1;
        localparam integer NOT_VALID = 1'b0;     
        reg out_state = 1'b0;
        reg out_valid_ff = 1'b0;
        always @ ( posedge out_clock ) begin
            if ( out_reset_n == 1'b0 ) begin
                out_state <= NOT_VALID;
                out_valid_ff <= 1'b0;
            end
            else begin
                case ( out_state )
                    NOT_VALID:      
                        if ( out_load ) begin
                            out_state <= VALID;
                            out_valid_ff <= 1'b1;
                        end
                        else begin
                            out_state <= NOT_VALID;
                            out_valid_ff <= 1'b0;
                        end
                    VALID:
                        if ( out_ready ) begin
                            out_state <= NOT_VALID;
                            out_valid_ff <= 1'b0;
                        end
                        else begin
                            out_state <= VALID;
                            out_valid_ff <= 1'b1;
                        end
                    default: // never reached
                        begin
                            out_state <= NOT_VALID;
                            out_valid_ff <= 1'b0;
                        end
                endcase
            end
        end
        assign out_valid = out_valid_ff;    
        
        // out_ack toggle bit
        reg out_ack_ff = 1'b0;
        always @ ( posedge out_clock ) begin
            if ( out_reset_n == 1'b0 ) out_ack_ff <= 1'b0;
            else out_ack_ff <= ( out_valid_ff & out_ready ) ^ out_ack_ff;  
        end
        assign out_ack = out_ack_ff;
    
    end
    else begin // USE_OUT_READY == "NO"
    
        // delay out load pulse for one cycle = out_valid pulse
        reg out_load_delay;
        always @ ( posedge out_clock ) begin
            out_load_delay <= out_load;
        end
        assign out_valid = out_load_delay;
        assign out_ack = out_toggle;
        
    end
    
    
endmodule
