`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// stream_IO module
// created 17/03/2020 by Andi
// input/ouput module for AXIS stream interface
// allows to easily interface a user IP with an AXI stream IP
// without worrying about timing and buffering
// an optional additional output buffer can be added (OUT_BUF=1)
// which increases latency but might help to improve timing
// simulation/test bench: stream_IO_tb.v
// usage:
// each interface has a valid and ready signal, 
// one of these signals is controlled by user IP, the other by AXI stream IP
// for example when user IP receives data from AXI stream IP,
// AXI stream IP sets in_valid signal high when in_data is valid
// and user IP sets in_ready signal high when it has read in_data
// the key is:
// when valid and ready signals are both high data is updated in next cycle
// internally:
// - the module uses 2 data buffers to ensure operation under all circumstances.
//   the module can handle a contiguous stream of data, where only one buffer is used,
//   which introduces one cycle of latency. when the stream stops the 2nd buffer is used,
//   if OUT_BUF="TRUE" another buffer is added introducing another cycle of latency,
//   but which might improve performance depending on application.
//   such that the latency after restart might be 2 cycles (depending how it stopped).
// - if out_ready=0 then loading of data is allowed only when both data_buf are empty! 
//   this is because setting in_ready=1, then checking in next cycle if in_valid==1 
//   and resetting in_ready=0 will always require 2 cycles where 2 data samples might
//   have been loaded! to allow loading of a single sample of data set
//   IN_READY_PULSE="YES" which will set in_ready=1 only for a single cycle after in_valid=1. 
//   if you set IN_READY_PULSE="OSC" then will oscillate in_ready regardless of in_valid
//   and checks if data was loaded in the cycle with in_ready=0, if not repeats. 
//   both options allow to load data when out_ready=0 and one buffer empty.
//   for IN_READY_PULSE="NO" both buffers must be empty to load data.
// ATTENTION: simulate behaviour for EVERY change you do!
// notes: 
// - for applications where the out_data is used for more than one cycle 
//   it is recommended to copy the data into a local buffer.
//   this allows stream_IO to pre-load the next data while the first is used.
//   for convenience you can use OUT_BUF="TRUE" to achieve this buffering,
//   however, it might be advantageous to access next_valid and next_ready directly
//   before this output buffer, thus a local buffer with OUT_BUF="FALSE" might be better. 
// - use IN_READY_PULSE="YES" or "OSC" for applications with long waiting time between 
//   short out_ready pulses or/and when on the next ready pulse valid data is 
//   absolutely needed. this way data could be loaded earlier and not only when 
//   needed and both buffers empty. adding output buffer with OUT_BUF="TRUE"
//   is increasing the buffered data and can also help to bridge gaps with in_valid=0.
//   recommended settings is "YES" for most applications. 
// - the IP sets in_ready high after reset to signal data transmission is ready.
//   after first 2 data reading cycles in_ready will go low if out_ready is low.
//   this should be not a problem but allows faster starting of transmission.
// - OUT_ZERO = "TRUE" sets out_data = 0 when out_valid = 0
//   OUT_ZERO = "FALSE" old value is kept.
//   setting out_data=0 is consistent in all cases and errors might be easier to detect.
//   however, more switching activiy might slightly increase current consumption.
// - some IP's require long reset time, like the FIFO requires 7 read cycles!
// - this IP was first designed for usage together with FIFO_DUALCLOCK_MACRO,
//   for input stream data into FIFO assign out_valid = WREN and out_ready = ~FULL  
//   for output FIFO data to stream assign in_ready = RDEN and in_valid = ~EMPTY
//   this works but WREN/RDEN signals are high even when FIFO is full/empty,
//   which causes that the error bits WRERR/RDERR become high in this condition.
//   the errors are reset whenever the FIFO is not full/empty again
//   and the IP takes care that no data is lost. 
//   to avoid these errors one could alternatively assign WREN = out_valid & out_ready
//   and similar for the reading case, but one needs to add one cycle delay
//   whenever WREN/RDEN changes from 0 to 1 to allow data transmission.
//   but I think these errors are not bad and we save one delay cycle when recovering from full/empty.
//   additionally, the IP can be used as is without modifications and additional complexities.
// - the accompanying test bench stream_IO_tb.v is heavily testing as many behaviour patterns as possible,
//   especially test #6 was designed for this. however, I cannot fully exclude that there might be
//   pattern which are not tested. this is unlikely, but maybe a pattern which depends on what happened 
//   more than 2 cycles before? in case the application stalls or gives errors due to no obvious reason 
//   consider this possibility. In the case-structure below I do not check the state of data_valid[0],
//   since it seems not to be needed for the state detection, but maybe it is for very special cases?
// - output valid = often in_valid delayed by one cycle, but not always!
// parameters:
//  DATA_WIDTH = width in bits of input and output data
//  IN_READY_PULSE = "NO" load data ony when out_ready=1 or both buffers empty.
//                  "YES" load data also when out_ready=0 if one buffer empty (recommended).
//                  "OSC" as "YES" but tries to load data even if in_valid=0. 
//                        oscillates in_ready until in_valid=1. 
//  OUT_BUF = if "TRUE"/"FALSE" additional output buffer is/is_not used
//  IN_READY_LOW_CYCLES = cycles+2 after reset in_ready goes high.
//                        if 0 in_ready goes high 1 cycle after reset.
//  OUT_ZERO = allows to zero output when invalid ("TRUE") or keep old value ("FALSE")
// clock and reset:
//  clock = common clock for all data I/O
//  reset_n = active low reset
// input interface:
//  in_data = input data of DATA_WIDTH bits (controlled by sender)
//  in_valid = high when in_data is valid (controlled by sender)
//  in_ready = high when in_data can be updated (controlled by IP)
// output interface:
//  out_data = output data of DATA_WIDTH bits (controlled by IP)
//  out_valid = high when out_data is valid (controlled by IP)
//  out_ready = high when in_data can be updated (controlled by receiver)
// last change 22/4/2020 by Andi
//////////////////////////////////////////////////////////////////////////////////

module stream_IO # (
    parameter integer DATA_WIDTH = 32,
    parameter IN_READY_PULSE = "YES",        // "NO","YES","OSC"
    parameter OUT_BUF = "FALSE",             // "TRUE", "FALSE"
    parameter integer IN_READY_LOW_CYCLES = 0, // >=0
    parameter OUT_ZERO = "FALSE"             // "TRUE", "FALSE"
    )
    (
    // clock and reset
    input clock,
    input reset_n,
    // input interface
    input [DATA_WIDTH-1:0] in_data,
    input in_valid,
    output in_ready,
    // output interface
    output [DATA_WIDTH-1:0] out_data,
    output out_valid,
    input out_ready
    );
    
    // keep output data or set to zero if output invalid
    reg [DATA_WIDTH - 1 : 0] data_buf [0 : 1];
    wire [DATA_WIDTH - 1 : 0] data_keep [0 : 1];
    if ( OUT_ZERO == "TRUE" ) begin
        assign data_keep[0] = 0;
        assign data_keep[1] = 0;
    end
    else begin
        assign data_keep[0] = data_buf[0];
        assign data_keep[1] = data_buf[1];
    end
    
    // input/output data buffer
    // note: all 2'b11 states on input and output need action
    reg [1:0] data_valid = 2'b00;
    wire data_ready;
    always @ ( posedge clock ) begin
        if ( reset_n == 1'b0 ) begin
            data_buf[0] <= 0;
            data_buf[1] <= 0;
            data_valid <= 2'b00;
        end
        else begin
            case ( {in_valid,in_ready,data_valid[1],data_ready} )
                4'b11_11: begin // normal active state = contiguously streaming
                    data_buf[0] <= data_keep[0];
                    data_buf[1] <= in_data;
                    data_valid <= 2'b10;
                end
                4'b11_00: begin // loading of first data 1st cycle with data_ready=0
                    data_buf[0] <= data_keep[0];
                    data_buf[1] <= in_data;
                    data_valid <= 2'b10;
                end
                4'b11_10: begin // loading of first data 2nd cycle with data_ready=0
                    data_buf[0] <= in_data;
                    data_buf[1] <= data_buf[1];
                    data_valid <= 2'b11;
                end
                4'b11_01: begin
                    data_buf[0] <= data_keep[0];
                    data_buf[1] <= in_data;
                    data_valid <= 2'b10;
                end
                4'b10_11: begin
                    data_buf[0] <= data_keep[0];
                    data_buf[1] <= data_valid[0] ? data_buf[0] : data_keep[1];
                    data_valid <= {data_valid[0],1'b0};
                end
                4'b01_11: begin
                    data_buf[0] <= data_keep[0];
                    data_buf[1] <= data_keep[1];
                    data_valid <= 2'b00;
                end
                4'b00_11: begin
                    data_buf[0] <= data_keep[0];
                    data_buf[1] <= data_valid[0] ? data_buf[0] : data_keep[1];
                    data_valid <= {data_valid[0],1'b0};
                end
                default: begin
                    data_buf[0] <= data_buf[0];
                    data_buf[1] <= data_buf[1];
                    data_valid <= data_valid;
                end
            endcase
        end
    end
    
    // input ready = data_ready delayed by one cycle
    // except when buffers empty then high to ensure loading of first data
    // and with IN_READY_PULSE in other than "NO" settings when one buffer is empty.
    // the (~in_ready_ff) ensures that only one data sample can be loaded
    reg in_ready_ff = 1'b0;
    wire in_test;
    if ( IN_READY_PULSE == "OSC" ) // oscillate in_ready when in_valid=0 and out_ready=0
        assign in_test = data_ready | (~data_valid[1]) | ((~data_valid[0]) & (~in_ready_ff));
    else if ( IN_READY_PULSE == "YES" ) // set in_ready=1 only when in_valid=1 and out_ready=0
        assign in_test = data_ready | (~data_valid[1]) | (in_valid & (~data_valid[0]) & (~in_ready_ff));
    else // "NO" = set in_ready=1 only when in_valid=1 and out_ready=1 or both buffer empty
        assign in_test = data_ready | (~data_valid[1]);
    // if IN_READY_LOW_CYCLES > 0 in_ready goes high IN_READY_LOW_CYCLES+2 cycles after reset goes high
    // if IN_READY_LOW_CYCLES == 0 in_ready goes high 1 cycle after reset goes high
    reg reset_done = 1'b0;
    if ( IN_READY_LOW_CYCLES == 0 ) begin
        always @ ( posedge clock ) begin
            if ((reset_n == 1'b0) || (~reset_done)) begin
                in_ready_ff <= 1'b0;
                reset_done <= ~reset_n;
            end
            else if ( in_test ) begin
                in_ready_ff <= 1'b1;
                reset_done <= reset_done;
            end
            else begin
                in_ready_ff <= 1'b0;
                reset_done <= reset_done;
            end
        end
    end
    else begin
        // note: GSR init with all bits set to ensure in_ready = 0 initially 
        reg [IN_READY_LOW_CYCLES:0] reset_ff = {IN_READY_LOW_CYCLES{1'b1}};
        always @ ( posedge clock ) begin
            if ( (reset_n == 1'b0) || (reset_ff != 0) || (~reset_done)) begin
                reset_ff <= {reset_ff[IN_READY_LOW_CYCLES-1:0],~reset_n};
                reset_done <= ~reset_n;
                in_ready_ff <= 1'b0;
            end
            else if ( in_test ) begin
                in_ready_ff <= 1'b1;
                reset_done <= reset_done;
            end
            else begin
                in_ready_ff <= 1'b0;
                reset_done <= reset_done;
            end
        end
    end
    assign in_ready = in_ready_ff;
    
    if ( OUT_BUF == "TRUE" ) begin  // use output buffer
        reg [DATA_WIDTH - 1 : 0] out_buf;
        reg out_buf_valid = 1'b0;
        always @ ( posedge clock ) begin
            if ( reset_n == 1'b0 ) begin
                out_buf <= 0;
                out_buf_valid <= 1'b0;
            end
            else if ( data_ready & data_valid[1] ) begin
                out_buf <= data_buf[1];
                out_buf_valid <= 1'b1;
            end
            else if ( out_valid & out_ready ) begin
                out_buf <= 0;
                out_buf_valid <= 1'b0;
            end
            else begin
                out_buf <= out_buf;
                out_buf_valid <= out_buf_valid;
            end
        end
        assign data_ready = out_ready | (~out_buf_valid);
        assign out_data = out_buf;
        assign out_valid = out_buf_valid;
    end
    else begin  // do not use output buffer
        assign data_ready = out_ready;
        assign out_data = data_buf[1];
        assign out_valid = data_valid[1];
    end
    
endmodule
