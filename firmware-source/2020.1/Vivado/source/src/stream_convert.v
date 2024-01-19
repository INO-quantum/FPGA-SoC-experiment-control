`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// stream_convert.v
// stream data width converter
// created 29/5/2020 by Andi 
// parameters:
// - IN_BYTES = input data bytes, max. 16*
// - OUT_BYTES = output data bytes, max. 16*
// for test bench see stream_convert_tb.v
// notes:
// *limit is given by size of lookup tables. you can increase if needed. 
// - the case that we simultaneously load and unload data (4'b1111) does not occur!
//   if in_valid and out_ready would be high at the same time we would require: 
//   OUT_WIDTH <= count <= N_MAX - IN_WIDTH 
//   and we get condition N_MAX >= IN_WIDTH + OUT_WIDTH
//   which never occurs since n_max returns always <= IN_WIDTH + OUT_WIDTH - 1.
//   this is "lucky" since the case 4'b1111 would require load and shift-right
//   of remainder which cannot be done in one cycle!? maybe would work with already shifted copy register?
// TODO:
// - contiguous out_last = 1 is not working but gives one cycle 1 other cycle 0!
// - maybe there is an issue with IN_BYTES=5, OUT_BYTES=7 with random in_last (but could be related to previous issue).
// - test in_keep != all 1's with in_last = 0 (should work but not tested)   
// - output has regular single-cycle gaps which might be a problem for high performance.
//   I think this is because module never loads and unloads at the same time.
// last change 10/02/2022 by Andi
//////////////////////////////////////////////////////////////////////////////////

module stream_convert # (
        parameter IN_BYTES = 16,        // TX: 16, RX: 8 or 12
        parameter OUT_BYTES = 8         // TX: 8 or 12, RX: 16
    )
    (
    // clock and reset
    input clock,
    input reset_n,
    // tkeep error if 0s are not only on MSB side
    output error_keep,
    // data input
    input [(IN_BYTES*8)-1:0] in_data,
    input in_last,
    input [IN_BYTES-1:0] in_keep,
    input in_valid,
    output in_ready,
    // data output
    output [(OUT_BYTES*8)-1:0] out_data,
    output out_last,
    output [OUT_BYTES-1:0] out_keep,
    output out_valid,
    input out_ready
    );
    
    // returns ceiling of the log base 2 of bd.
    // see axi_stream_master.v example from Xilinx
    function integer clogb2 (input integer bd);
        integer bit_depth;
        begin
            bit_depth = bd;
            for(clogb2=0; bit_depth>0; clogb2=clogb2+1)
                bit_depth = bit_depth >> 1;
        end
    endfunction
    
    localparam integer IN_WIDTH = IN_BYTES*8;
    localparam integer OUT_WIDTH = OUT_BYTES*8;
    localparam integer N_MAX = IN_BYTES + OUT_BYTES - 1;    // 23 or 27 bytes
    localparam integer N_COUNT = clogb2(N_MAX);             // always 8 bits
    
    // input buffer
    // allows to delay in_data for counting in_bits
    // and buffers input data for contiguous input stream
    wire [IN_BYTES*8 - 1 : 0] in_buf_data;
    wire in_buf_last;
    wire in_buf_valid;          // data in input buffer
    reg in_buf_ready = 1'b0;    // reload input buffer
    stream_IO # (
        .DATA_WIDTH(IN_BYTES*8+1),
        .IN_READY_PULSE("YES"),        // "NO","YES","OSC"
        .OUT_BUF("FALSE"),             // "TRUE", "FALSE"
        .IN_READY_LOW_CYCLES(0),       // >=0
        .OUT_ZERO("FALSE")             // "TRUE", "FALSE"
        )
    in_buf
        (
        // clock and reset
        .clock(clock),
        .reset_n(reset_n),
        // input interface
        .in_data({in_last,in_data}),
        .in_valid(in_valid),
        .in_ready(in_ready),
        // output interface
        .out_data({in_buf_last,in_buf_data}),
        .out_valid(in_buf_valid),
        .out_ready(in_buf_ready)
        );
    
    // count number of bits in in_keep which corresponds to used bytes in in_data
    // in_keep bits must be LSB aligned and there is no gap allowed, 
    // otherwise we assert error_keep
    // lookup table is valid for 1 <= IN_BYTES <= 16 (DEFAULT)
    reg in_bytes_sel = 1'b0;
    reg [N_COUNT-1:0] in_bytes_ff [0:1];
    wire [N_COUNT-1:0] in_bytes = (in_bytes_sel) ? in_bytes_ff[1] : in_bytes_ff[0];
    reg error_keep_ff = 1'b0;
    always @ ( posedge clock ) begin
        if ( reset_n == 1'b0 ) begin
            in_bytes_ff[0] <= 0;
            in_bytes_ff[1] <= 0;
        end
        else begin
            if ( in_valid & in_ready ) begin
                case ( in_keep )
                    'h0001:      begin in_bytes_ff[0] <= 01; error_keep_ff <= 1'b0; end
                    'h0003:      begin in_bytes_ff[0] <= 02; error_keep_ff <= 1'b0; end
                    'h0007:      begin in_bytes_ff[0] <= 03; error_keep_ff <= 1'b0; end
                    'h000f:      begin in_bytes_ff[0] <= 04; error_keep_ff <= 1'b0; end
                    'h001f:      begin in_bytes_ff[0] <= 05; error_keep_ff <= 1'b0; end
                    'h003f:      begin in_bytes_ff[0] <= 06; error_keep_ff <= 1'b0; end
                    'h007f:      begin in_bytes_ff[0] <= 07; error_keep_ff <= 1'b0; end
                    'h00ff:      begin in_bytes_ff[0] <= 08; error_keep_ff <= 1'b0; end
                    'h01ff:      begin in_bytes_ff[0] <= 09; error_keep_ff <= 1'b0; end
                    'h03ff:      begin in_bytes_ff[0] <= 10; error_keep_ff <= 1'b0; end
                    'h07ff:      begin in_bytes_ff[0] <= 11; error_keep_ff <= 1'b0; end
                    'h0fff:      begin in_bytes_ff[0] <= 12; error_keep_ff <= 1'b0; end
                    'h1fff:      begin in_bytes_ff[0] <= 13; error_keep_ff <= 1'b0; end
                    'h3fff:      begin in_bytes_ff[0] <= 14; error_keep_ff <= 1'b0; end
                    'h7fff:      begin in_bytes_ff[0] <= 15; error_keep_ff <= 1'b0; end
                    'hffff:      begin in_bytes_ff[0] <= 16; error_keep_ff <= 1'b0; end
                    default:     begin in_bytes_ff[0] <= 00; error_keep_ff <= 1'b1; end
                endcase
            end
            else begin
                in_bytes_ff[0] <= in_bytes_ff[0];
                error_keep_ff <= error_keep_ff;
            end
            // buffer in_bytes in case output is not read
            if (in_buf_valid & ~in_buf_ready) begin
                in_bytes_sel <=  1'b1;
                in_bytes_ff[1] <= (in_bytes_sel) ? in_bytes_ff[1] : in_bytes_ff[0];
            end
            else begin
                in_bytes_sel <= 1'b0;
                in_bytes_ff[1] <= in_bytes_ff[1];
            end
        end
    end
    assign error_keep = error_keep_ff;    
    
    // shift register, byte counter, state detection & control 
    reg [N_MAX*8 - 1 : 0] in_out = 0;
    reg in_out_last = 1'b0;
    reg [N_COUNT - 1 : 0] count = 0;    
    reg out_buf_valid = 1'b0; 
    wire out_buf_ready;   
    reg out_buf_last = 1'b0;
    always @ ( posedge clock ) begin
        if ( reset_n == 1'b0 ) begin
            in_buf_ready  <= 1'b0;
            in_out        <= 0;
            in_out_last   <= 0;
            count         <= 0;
            out_buf_valid <= 1'b0;
            out_buf_last  <= 1'b0;
        end
        else begin
            case ({in_buf_valid & in_buf_ready,out_buf_valid & out_buf_ready})
                2'b10: begin    // load data
                    in_out[(count<<3) + IN_WIDTH - 1 -: IN_WIDTH] <= in_buf_data;
                    in_out_last <= in_buf_last;
                    out_buf_last <= (in_buf_last && ((count + in_bytes) <= OUT_BYTES)) ? 1'b1 : 1'b0;
                    count <= count + in_bytes;
                    in_buf_ready <= ( (count + in_bytes) <= (N_MAX-IN_BYTES) ) && (~in_out_last);
                    out_buf_valid <= ( (count + in_bytes) >= OUT_BYTES ) || in_out_last;
                end
                2'b01: begin    // unload data and shift-right remainder
                    in_out <= in_out >> OUT_WIDTH;
                    in_out_last <= (in_out_last && (count > OUT_BYTES)) ? 1'b1 : 1'b0;
                    out_buf_last <= (in_out_last && (count <= 2*OUT_BYTES)) ? 1'b1 : 1'b0;
                    count <= (count >= OUT_BYTES) ? count - OUT_BYTES : ( in_out_last ? 0 : count);
                    in_buf_ready <= ( count <= (N_MAX+OUT_BYTES-IN_BYTES) ) && ((in_out_last && (count > OUT_BYTES)) ? 1'b0 : 1'b1);
                    out_buf_valid <= ( count >= 2*OUT_BYTES ) || ((in_out_last && (count > OUT_BYTES)) ? 1'b1 : 1'b0);
                end
                default: begin  // no change: for first loading in_ready is high initially
                    in_out <= in_out;
                    in_out_last <= in_out_last;
                    out_buf_last <= out_buf_last;
                    count <= count;
                    in_buf_ready <= ( count <= (N_MAX-IN_BYTES) ) && (~in_out_last);
                    out_buf_valid <= out_buf_valid || in_out_last;
                end
            endcase
        end
    end
    
    // output buffer
    // allows to delay out_data for out_keep 
    // and buffers output for contiguous output stream
    wire [OUT_BYTES*8-1 : 0] out_buf_data = in_out[OUT_BYTES*8-1 : 0];
    stream_IO # (
        .DATA_WIDTH(OUT_BYTES*8+1),
        .IN_READY_PULSE("YES"),        // "NO","YES","OSC"
        .OUT_BUF("FALSE"),             // "TRUE", "FALSE"
        .IN_READY_LOW_CYCLES(0),       // >=0
        .OUT_ZERO("FALSE")             // "TRUE", "FALSE"
        )
    out_buf
        (
        // clock and reset
        .clock(clock),
        .reset_n(reset_n),
        // input interface
        .in_data({out_buf_last,out_buf_data}),
        .in_valid(out_buf_valid),
        .in_ready(out_buf_ready),
        // output interface
        .out_data({out_last,out_data}),
        .out_valid(out_valid),
        .out_ready(out_ready)
        );    

    // output used bits lookup table
    // lookup table is valid for 1 <= OUT_BYTES <= 16
    reg [OUT_BYTES-1:0] out_keep_ff [0:1];
    reg out_keep_sel = 1'b0;
    always @ ( posedge clock ) begin
        if ( reset_n == 1'b0 ) begin
            out_keep_ff[0] <= 0;
            out_keep_ff[1] <= 0;
        end
        else begin
            if ( out_buf_valid & out_buf_ready ) begin
                // count can be maximum: IN_BYTES + OUT_BYTES - 1
                // so we have to cover BYTES_MAX*2 cases
                case ( count )
                    1:       out_keep_ff[0] <= 'h0001;
                    2:       out_keep_ff[0] <= 'h0003;
                    3:       out_keep_ff[0] <= 'h0007;
                    4:       out_keep_ff[0] <= 'h000f;
                    5:       out_keep_ff[0] <= 'h001f;
                    6:       out_keep_ff[0] <= 'h003f;
                    7:       out_keep_ff[0] <= 'h007f;
                    8:       out_keep_ff[0] <= 'h00ff;
                    9:       out_keep_ff[0] <= 'h01ff;
                    10:      out_keep_ff[0] <= 'h03ff;
                    11:      out_keep_ff[0] <= 'h07ff;
                    12:      out_keep_ff[0] <= 'h0fff;
                    13:      out_keep_ff[0] <= 'h1fff;
                    14:      out_keep_ff[0] <= 'h3fff;
                    15:      out_keep_ff[0] <= 'h7fff;
                    16:      out_keep_ff[0] <= 'hffff;
                    17:      out_keep_ff[0] <= 'hffff;
                    18:      out_keep_ff[0] <= 'hffff;
                    19:      out_keep_ff[0] <= 'hffff;
                    20:      out_keep_ff[0] <= 'hffff;
                    21:      out_keep_ff[0] <= 'hffff;
                    22:      out_keep_ff[0] <= 'hffff;
                    23:      out_keep_ff[0] <= 'hffff;
                    24:      out_keep_ff[0] <= 'hffff;
                    25:      out_keep_ff[0] <= 'hffff;
                    26:      out_keep_ff[0] <= 'hffff;
                    27:      out_keep_ff[0] <= 'hffff;
                    28:      out_keep_ff[0] <= 'hffff;
                    29:      out_keep_ff[0] <= 'hffff;
                    30:      out_keep_ff[0] <= 'hffff;
                    31:      out_keep_ff[0] <= 'hffff;
                    32:      out_keep_ff[0] <= 'hffff;
                    default: out_keep_ff[0] <= 'h0000;
                endcase
            end
            else begin
                out_keep_ff[0] <= out_keep_ff[0];
            end
            // buffer out_keep in case output is not read
            if ( out_valid & ~out_ready ) begin
                out_keep_sel <=  1'b1;
                out_keep_ff[1] <= (out_keep_sel) ? out_keep_ff[1] : out_keep_ff[0];
            end
            else begin
                out_keep_sel <= 1'b0;
                out_keep_ff[1] <= out_keep_ff[1];
            end            
        end
    end
    assign out_keep = (out_keep_sel) ? out_keep_ff[1] : out_keep_ff[0];

endmodule
