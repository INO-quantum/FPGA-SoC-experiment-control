`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// cross_IO module for transferring slow data across clock demains
// created 31/3/2020 by Andi
// parameters: 
// - DATA_WIDTH = data bits to be sent
// - SYNC = # of synchronization registers, 2-4, 2 for single bits, 3-4 for coherent data
// - OUTPUT_READER = if "TRUE" adds a reader to output and out_data is valid contiguously.
//  i.e. out_valid = 1 after first data is loaded and cannot be reset anymore.
//  out_valid also does not anymore indicate when out_data is updated.
//  however, this is useful for contiguous variables, like control or status bits.
// input data:
// - in_clock = input clock
// - in_data = DATA_WIDTH input data bits
// - in_valid = if 1 in_data is valid, can be constant 1'b1.
// - in_ready = if 1 last input data was sent and received by output. initially 1.
// output data:
// - out_clock = output clock
// - out_data = DATA_WIDTH output data bits, undefined when out_valid is not 1
// - out_valid = if 1 output_data is valid
// - out_ready = if 1 new data can be send. can be constant 1'b1.
// notes:
// - the module works very simple and allows to send data over a clock domain
//   irrespective which side runs at the slower or the faster clock.
//   data transfer is only from input to output, but there is feedback when data is sent.
//   when new data is available on the input (can be contiguously) and in_ready is 1
//   and input sets in_valid bit, data is sent and in_ready bit becomes 0. 
//   after ca. SYNC+1 out cycles out_data receives data and out_valid is 1.
//   after new data is read the output sets out_ready 1 (can be contiguously)
//   then another ca. SYNC+1 in cycles in_ready bit becomes 1 again.
// - for simple applications the feedback signal (out_ready -> in_ready) might be
//   usable as a single bit "ok","done", etc. signal when in-between no data needs to be sent.
//   see the dio24_reset module for an (slightly more involved) example.
//   if you need to send data both ways use two cross_IO modules.
//   one could here easily send more data back than the one bit feedback signal,
//   but the output side would never get feedback that data was sent -
//   maybe by using an additional bit in the forward data. but data streams would be linked.
// - the module is NOT intended for high-speed data transmission. use a FIFO for this!
// - the module does not need a reset since it is used inside the dio24_reset module.
//   the output is not defined as long as out_valid is not 1.
// last changed 8/4/2020 by andi 
// TODO: 
// - at the moment the constraint is using clock_roups, would be nice to use max_delay instad
// - also one could include the constraint here?
//////////////////////////////////////////////////////////////////////////////////

module cross_IO # (
        parameter integer DATA_WIDTH = 32,
        parameter integer SYNC = 3,             // 2-4
        parameter OUTPUT_READER = "FALSE"
    )
    (
        // input data
        input in_clock,
        input [DATA_WIDTH-1:0] in_data,
        input in_valid,
        output in_ready,
        // output data
        input out_clock,
        output [DATA_WIDTH-1:0] out_data,
        output out_valid,
        input out_ready
    );
    
    (* ASYNC_REG = "TRUE" *)
    reg [DATA_WIDTH - 1 : 0] in_sync [0 : SYNC-1];  // data
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1 : 0] in_to_out = 0;                 // toggle bit
    (* ASYNC_REG = "TRUE" *)
    reg [SYNC-1 : 0] out_to_in = 0;                 // toggle bit feedback

    // latch input data and toggle bit
    reg [DATA_WIDTH - 1 : 0] in_data_ff;
    reg in_tgl = 1'b0;
    always @ ( posedge in_clock ) begin
        if ( in_valid & in_ready ) begin
            in_data_ff <= in_data;
            in_tgl <= ~in_tgl;
        end
        else begin
            in_data_ff <= in_data_ff;
            in_tgl <= in_tgl;
        end
    end
    
    // input data ready when toggle bit has travelled from input to output and back
    assign in_ready = ( out_to_in[SYNC-1] == in_tgl );
    // unbufferd output valid signal
    wire out_valid_ub;
    
    // sync input data with output clock
    integer i;
    always @ ( posedge out_clock ) begin
        if ( ~out_valid_ub ) begin
            in_sync[0] <= in_data_ff;
            for (i = 1; i < SYNC; i = i + 1) begin
                in_sync[i] <= in_sync[i-1];
            end
            in_to_out <= {in_to_out[SYNC-2:0],in_tgl};
        end 
        else begin
            in_sync[0] <= in_sync[0];
            for (i = 1; i < SYNC; i = i + 1) begin
                in_sync[i] <= in_sync[i];
            end
            in_to_out <= in_to_out;
        end
    end

    // sync feedback toggle bit with input clock
    reg out_tgl = 1'b0;
    always @ ( posedge in_clock ) begin
        if ( ~in_ready ) begin
            out_to_in <= {out_to_in[SYNC-2:0],out_tgl};
        end 
        else begin
            out_to_in <= out_to_in;
        end
    end
    assign out_valid_ub = ( in_to_out[SYNC-1] != out_tgl );
    
    // load feedback toggle bit
    always @ ( posedge out_clock ) begin
        if ( out_valid_ub & out_ready ) begin
            out_tgl <= in_to_out[SYNC-1];
        end
        else begin
            out_tgl <= out_tgl;
        end
    end

    if ( OUTPUT_READER == "TRUE" ) begin
        
        // output reader
        reg [DATA_WIDTH-1:0] out_data_ff = 0;
        reg out_valid_ff = 1'b0;
        always @ ( posedge out_clock ) begin
            if ( out_valid_ub & out_ready ) begin
                out_data_ff <= in_sync[SYNC-1];
                out_valid_ff <= 1'b1;
            end
            else begin
                out_data_ff <= out_data_ff;
                out_valid_ff <= out_valid_ff;
            end
        end
        assign out_valid = out_valid_ff;
        assign out_data = out_data_ff;
        
    end
    else begin
    
        // output data valid when toggle bit has travelled from input to output
        assign out_valid = out_valid_ub;
        // output data
        assign out_data = in_sync[SYNC-1];
        
    end
    
endmodule
