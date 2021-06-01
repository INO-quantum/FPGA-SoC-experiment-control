`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// dio24_FIFO_TX module, created 15/03/2020 by Andi
// implements block RAM FIFO with clock domain crossing
// parameters:
// - STREAM_DATA_WIDTH = bits for input stream*
// - FIFO_DEPTH = number of samples of STREAM_DATA_WIDTH bits in FIFO (must be power of two)
// - OUT_ZERO = allows to zero output when invalid ("TRUE") or keep old value ("FALSE")
// input TX stream:
// - in_clock = input stream data clock
// - in_reset_n = input reset, active low, sync to in_clock (also used to reset FIFO)
// - in_data = STREAM_DATA_WIDTH input data bits
// - in_ready = output ready for new data (= FIFO not full)
// - in_valid = input stream data is valid
// output data:
// - out_clock = output stream data clock
// - out_reset_n = output reset, active low, sync to out_clock
// - out_data = STREAM_DATA_WIDTH output data bits
// - out_ready = input downstream IP is ready for new data
// - out_valid = output stream data is valid (= FIFO not empty)
// - FIFO_DUALCLOCK_MACRO works in simulation but when FIFO is empty/full get sometimes dropped/repeated samples!
//   changed on 10/5/2020 to xpm_fifo_async macro which works and is more flexible and easier with reset
// ATTENTION: 
// - FIFO is reset with in_reset_n sync to in_clock. there seems to be no special requirements.
//   we do not need reset_FIFO from dio24_reset module since Fifo reset must be synced to in_clock.
//   still its best to use dio24_reset module to generate proper in_reset_n and out_reset_n signals.
// - to be sure reset is ok I keep wr_en = rd_en = 0 during reset (and when full/empty). 
//   this might introduce combinatorial delay which might require another ff-stage for fast applications.
// last change 10/5/2020 by Andi
//////////////////////////////////////////////////////////////////////////////////

module dio24_FIFO # (
    parameter integer STREAM_DATA_WIDTH = 64,
    parameter integer FIFO_DEPTH = 4096,        // powers of 2
    parameter OUT_ZERO = "FALSE"                // "TRUE", "FALSE"
)
(
    // input TX stream (AXI Stream Slave Bus S00_AXIS)
    input in_clock,
    input in_reset_n,
    input [STREAM_DATA_WIDTH - 1 : 0] in_data,
    output in_ready,
    input in_valid,
    
    // output RX stream (AXI Stream Master Bus M00_AXIS)
    input out_clock,
    input out_reset_n,
    output [STREAM_DATA_WIDTH - 1 : 0] out_data,
    input out_ready,
    output out_valid
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
    
    // stream_IO settings
    localparam IO_DATA_WIDTH = STREAM_DATA_WIDTH;
    localparam IO_IN_READY_PULSE = "YES";
    localparam IO_OUT_BUF = "FALSE";
    localparam IO_IN_READY_LOW_CYCLES = 0;
    localparam IO_IN_ZERO = "FALSE";

    // number of read and write counter bits
    localparam integer FIFO_NCOUNT = clogb2(FIFO_DEPTH);
    
    // input and output data latch to FIFO
    wire [STREAM_DATA_WIDTH - 1 : 0] fifo_in;
    wire [STREAM_DATA_WIDTH - 1 : 0] fifo_out;

    // write and read enable signals common for all FIFOs
    wire wr_en;
    wire rd_en;
    
    // full and empty flags
    wire full;
    wire empty;
    
    // busy flags high until reset is finished: do not write or read data
    wire rd_busy;
    wire wr_busy;

    // interface AXI stream slave input with FIFO write side (WREN)
    wire TX_out_valid;
    stream_IO # (
        .DATA_WIDTH(IO_DATA_WIDTH),
        .IN_READY_PULSE(IO_IN_READY_PULSE),
        .OUT_BUF(IO_OUT_BUF),
        .IN_READY_LOW_CYCLES(IO_IN_READY_LOW_CYCLES),
        .OUT_ZERO(IO_IN_ZERO)
    )
    TX_IO
    (
        .clock(in_clock),
        .reset_n(in_reset_n),
        .in_data(in_data),
        .in_ready(in_ready),
        .in_valid(in_valid),
        .out_data(fifo_in),
        .out_valid(TX_out_valid),
        .out_ready((~full) & (~wr_busy))
    );
    assign wr_en = TX_out_valid & (~full) & (~wr_busy);
    
    // xpm_fifo_async: Asynchronous FIFO
    // Xilinx Parameterized Macro, version 2019.2
    // see ug953-vivado-7-series-libraries.pdf p. 32ff
    wire a_empty;
    wire a_full; 
    wire p_empty;
    wire p_full;
    wire rd_valid;
    wire wr_ack;
    wire wr_err;
    wire rd_err;
    wire [FIFO_NCOUNT - 1 : 0] wr_cnt;
    wire [FIFO_NCOUNT - 1 : 0] rd_cnt;    
    wire dbiterr;
    wire sbiterr;
    
    xpm_fifo_async #(   
    .CDC_SYNC_STAGES(2),       // DECIMAL   
    .DOUT_RESET_VALUE("0"),    // String   
    .ECC_MODE("no_ecc"),       // String   
    .FIFO_MEMORY_TYPE("block"),// String   
    .FIFO_READ_LATENCY(0),     // DECIMAL   
    .FIFO_WRITE_DEPTH(FIFO_DEPTH),   // DECIMAL   
    .FULL_RESET_VALUE(0),      // DECIMAL   
    .PROG_EMPTY_THRESH(10),    // DECIMAL   
    .PROG_FULL_THRESH(10),     // DECIMAL   
    .RD_DATA_COUNT_WIDTH(FIFO_NCOUNT),   // DECIMAL   
    .READ_DATA_WIDTH(STREAM_DATA_WIDTH),      // DECIMAL   
    .READ_MODE("fwft"),        // String   
    .RELATED_CLOCKS(0),        // DECIMAL   
    //.SIM_ASSERT_CHK(1),      // DECIMAL; // Andi: gives error in synthesis   
    .USE_ADV_FEATURES("0000"), // String // Andi: HEX (use "1515" for debugging)
    .WAKEUP_TIME(0),           // DECIMAL   
    .WRITE_DATA_WIDTH(STREAM_DATA_WIDTH),     // DECIMAL   
    .WR_DATA_COUNT_WIDTH(FIFO_NCOUNT)    // DECIMAL
    ) xpm_fifo_async_inst (   
    .almost_empty(a_empty),     // 1-bit output: Almost Empty : When asserted, this signal indicates that                                  
                                // only one more read can be performed before the FIFO goes to empty.   
    .almost_full(a_full),       // 1-bit output: Almost Full: When asserted, this signal indicates that                                  
                                // only one more write can be performed before the FIFO is full.   
    .data_valid(rd_valid),      // 1-bit output: Read Data Valid: When asserted, this signal indicates                                  
                                // that valid data is available on the output bus (dout).   
    .dbiterr(dbiterr),          // 1-bit output: Double Bit Error: Indicates that the ECC decoder detected                                  
                                // a double-bit error and data in the FIFO core is corrupted.   
    .dout(fifo_out),            // READ_DATA_WIDTH-bit output: Read Data: The output data bus is driven                                  
                                // when reading the FIFO.   
    .empty(empty),              // 1-bit output: Empty Flag: When asserted, this signal indicates that the                                  
                                // FIFO is empty. Read requests are ignored when the FIFO is empty,                                  
                                // initiating a read while empty is not destructive to the FIFO.   
    .full(full),                // 1-bit output: Full Flag: When asserted, this signal indicates that the                                  
                                // FIFO is full. Write requests are ignored when the FIFO is full,                                  
                                // initiating a write when the FIFO is full is not destructive to the                                  
                                // contents of the FIFO.   
    .overflow(wr_err),          // 1-bit output: Overflow: This signal indicates that a write request                                  
                                // (wren) during the prior clock cycle was rejected, because the FIFO is                                  
                                // full. Overflowing the FIFO is not destructive to the contents of the                                  
                                // FIFO.   
    .prog_empty(p_empty),       // 1-bit output: Programmable Empty: This signal is asserted when the                                  
                                // number of words in the FIFO is less than or equal to the programmable                                  
                                // empty threshold value. It is de-asserted when the number of words in                                  
                                // the FIFO exceeds the programmable empty threshold value.   
    .prog_full(p_full),         // 1-bit output: Programmable Full: This signal is asserted when the                                  
                                // number of words in the FIFO is greater than or equal to the                                  
                                // programmable full threshold value. It is de-asserted when the number of                                  
                                // words in the FIFO is less than the programmable full threshold value.   
    .rd_data_count(rd_cnt),     // RD_DATA_COUNT_WIDTH-bit output: Read Data Count: This bus indicates the                                  
                                // number of words read from the FIFO.   
    .rd_rst_busy(rd_busy),      // 1-bit output: Read Reset Busy: Active-High indicator that the FIFO read                                  
                                // domain is currently in a reset state.
    .sbiterr(sbiterr),          // 1-bit output: Single Bit Error: Indicates that the ECC decoder detected                                  
                                // and fixed a single-bit error.   
    .underflow(rd_err),         // 1-bit output: Underflow: Indicates that the read request (rd_en) during                                  
                                // the previous clock cycle was rejected because the FIFO is empty. Under                                  
                                // flowing the FIFO is not destructive to the FIFO.   
    .wr_ack(wr_ack),            // 1-bit output: Write Acknowledge: This signal indicates that a write                                  
                                // request (wr_en) during the prior clock cycle is succeeded.   
    .wr_data_count(wr_cnt),     // WR_DATA_COUNT_WIDTH-bit output: Write Data Count: This bus indicates                                  
                                // the number of words written into the FIFO.   
    .wr_rst_busy(wr_busy),      // 1-bit output: Write Reset Busy: Active-High indicator that the FIFO                                  
                                // write domain is currently in a reset state.   
    .din(fifo_in),              // WRITE_DATA_WIDTH-bit input: Write Data: The input data bus used when                                  
                                // writing the FIFO.   
    .injectdbiterr(1'b0),       // 1-bit input: Double Bit Error Injection: Injects a double bit error if                                  
                                // the ECC feature is used on block RAMs or UltraRAM macros.   
    .injectsbiterr(1'b0),       // 1-bit input: Single Bit Error Injection: Injects a single bit error if                                  
                                // the ECC feature is used on block RAMs or UltraRAM macros.   
    .rd_clk(out_clock),         // 1-bit input: Read clock: Used for read operation. rd_clk must be a free                                  
                                // running clock.   
    .rd_en(rd_en),              // 1-bit input: Read Enable: If the FIFO is not empty, asserting this                                  
                                // signal causes data (on dout) to be read from the FIFO. Must be held                                  
                                // active-low when rd_rst_busy is active high.   
    .rst(~in_reset_n),          // 1-bit input: Reset: Must be synchronous to wr_clk. The clock(s) can be                                  
                                // unstable at the time of applying reset, but reset must be released only                                  
                                // after the clock(s) is/are stable.   
    .sleep(1'b0),               // 1-bit input: Dynamic power saving: If sleep is High, the memory/fifo                                  
                                // block is in power saving mode.   
    .wr_clk(in_clock),          // 1-bit input: Write clock: Used for write operation. wr_clk must be a                                  
                                // free running clock.   
    .wr_en(wr_en)               // 1-bit input: Write Enable: If the FIFO is not full, asserting this                                  
                                // signal causes data (on din) to be written to the FIFO. Must be held                                  
                                // active-low when rst or wr_rst_busy is active high.
    );
    
    // End of xpm_fifo_async_inst instantiation
    
    // interface FIFO read side (RDEN) with AXI stream master output
    // we keep this in reset mode for RESET_COUNT + RESET_WAIT slow_clock cycles after reset
    wire RX_in_ready;
    stream_IO # (
        .DATA_WIDTH(IO_DATA_WIDTH),
        .IN_READY_PULSE(IO_IN_READY_PULSE),
        .OUT_BUF(IO_OUT_BUF),
        .IN_READY_LOW_CYCLES(IO_IN_READY_LOW_CYCLES),
        .OUT_ZERO(OUT_ZERO)
    )
    RX_IO
    (
        .clock(out_clock),
        .reset_n(out_reset_n),
        .in_data(fifo_out),
        .in_ready(RX_in_ready),
        .in_valid((~empty) & (~rd_busy)),
        .out_data(out_data),
        .out_valid(out_valid),
        .out_ready(out_ready)
    );
    assign rd_en = RX_in_ready & (~empty) & (~rd_busy);
    
endmodule
