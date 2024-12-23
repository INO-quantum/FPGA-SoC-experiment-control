`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// AXI stream data generator
// created 03/10/2020 by Andi
// last change 04/10/2020 by Andi
// renamed 17/6/2024 from data_gen to AXI_stream_generator
//////////////////////////////////////////////////////////////////////////////////

module AXI_stream_generator # (
    parameter integer DATA_WIDTH            = 32,
    parameter integer SAMPLES_WIDTH         = 32,
    parameter [DATA_WIDTH-1:0] DATA_START   = 32'h04030201,
    parameter [DATA_WIDTH-1:0] DATA_STEP    = 32'h01010101,
    parameter integer NUM_SAMPLES           = 10
)
(
    // clock and reset
    input clock,
    input reset_n,
    // enable signal blocks output when 1'b0
    input out_enable,
    // number of generated samples
    output [SAMPLES_WIDTH-1:0] num_samples,
    // stream data output
    output [DATA_WIDTH-1:0] out_data,
    output out_last,
    output out_valid,
    input  out_ready
);
    
    reg [DATA_WIDTH-1:0] data;
    reg [SAMPLES_WIDTH-1:0] samples;
    reg [1:0] last;
    always @ ( posedge clock ) begin
        if ( reset_n == 1'b0 ) begin
            data    <= DATA_START;
            samples <= 0;
            last    <= (NUM_SAMPLES == 1) ? 2'b01 : 2'b00;
        end
        else if ( out_valid & out_ready ) begin
            data    <= data + DATA_STEP;
            samples <= samples + 1;
            last[0] <= ((samples+2) >= NUM_SAMPLES) ? 1'b1 : 1'b0;
            last[1] <= last[0];
        end
        else begin
            data    <= data;
            samples <= samples;
            last    <= last;
        end
    end
    assign out_data = data;
    assign out_last = last[0];
    assign out_valid = out_enable & (~last[1]);
    assign num_samples = samples; 

endmodule
