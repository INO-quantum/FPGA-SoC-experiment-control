////////////////////////////////////////////////////////////////////////////
//-- (c) Copyright 2012 - 2013 Xilinx, Inc. All rights reserved.
//--
//-- This file contains confidential and proprietary information
//-- of Xilinx, Inc. and is protected under U.S. and
//-- international copyright and other intellectual property
//-- laws.
//--
//-- DISCLAIMER
//-- This disclaimer is not a license and does not grant any
//-- rights to the materials distributed herewith. Except as
//-- otherwise provided in a valid license issued to you by
//-- Xilinx, and to the maximum extent permitted by applicable
//-- law: (1) THESE MATERIALS ARE MADE AVAILABLE "AS IS" AND
//-- WITH ALL FAULTS, AND XILINX HEREBY DISCLAIMS ALL WARRANTIES
//-- AND CONDITIONS, EXPRESS, IMPLIED, OR STATUTORY, INCLUDING
//-- BUT NOT LIMITED TO WARRANTIES OF MERCHANTABILITY, NON-
//-- INFRINGEMENT, OR FITNESS FOR ANY PARTICULAR PURPOSE; and
//-- (2) Xilinx shall not be liable (whether in contract or tort,
//-- including negligence, or under any other theory of
//-- liability) for any loss or damage of any kind or nature
//-- related to, arising under or in connection with these
//-- materials, including for any direct, or any indirect,
//-- special, incidental, or consequential loss or damage
//-- (including loss of data, profits, goodwill, or any type of
//-- loss or damage suffered as a result of any action brought
//-- by a third party) even if such damage or loss was
//-- reasonably foreseeable or Xilinx had been advised of the
//-- possibility of the same.
//--
//-- CRITICAL APPLICATIONS
//-- Xilinx products are not designed or intended to be fail-
//-- safe, or for use in any application requiring fail-safe
//-- performance, such as life-support or safety devices or
//-- systems, Class III medical devices, nuclear facilities,
//-- applications related to the deployment of airbags, or any
//-- other applications that could lead to death, personal
//-- injury, or severe property or environmental damage
//-- (individually and collectively, "Critical
//-- Applications"). Customer assumes the sole risk and
//-- liability of any use of Xilinx products in Critical
//-- Applications, subject only to applicable laws and
//-- regulations governing limitations on product liability.
//--
//-- THIS COPYRIGHT NOTICE AND DISCLAIMER MUST BE RETAINED AS
//-- PART OF THIS FILE AT ALL TIMES.
////////////////////////////////////////////////////////////////////////////
// AXI4-Lite Master Example
//
// The purpose of this design is to provide a simple AXI4-Lite example.
//
// The distinguishing characteristics of AXI4-Lite are the single-beat transfers,
// limited data width, and limited other transaction qualifiers. These make it
// best suited for low-throughput control functions.
//
// The example user application will perform a set of writes, then after completing all the writes,
// the example design will perform reads and attempt to verify the values.
//
////////////////////////////////////////////////////////////////////////////
// modified by Andi:
// if wr_ready & wr_valid writes data to given register address. 
//   wr_ready is reset until write is finished
// if rd_ready & rd_valid reads data to given register address
//   rd_valid is reset until read is finished and new rd_data is available
// note: this module is only intended for simulation!
// created 15/4/2021
// last change 15/4/2021
////////////////////////////////////////////////////////////////////////////

`timescale 1ns/1ps

////////////////////////////////////////////////////////////////////////////
// Width of M_AXI address bus. The master generates the read and write addresses
// of width specified as C_M_AXI_ADDR_WIDTH.
//`define C_M_AXI_ADDR_WIDTH 32
////////////////////////////////////////////////////////////////////////////
// Width of M_AXI data bus. The master issues write data and accept read data
// where the width of the data bus is C_M_AXI_DATA_WIDTH
//`define C_M_AXI_DATA_WIDTH 32

module axi_lite_master #   (
  ////////////////////////////////////////////////////////////////////////////
  // Transaction number is the number of write and read transactions the master
  // will perform as a part of this example memory test.
  //parameter integer C_TRANSACTIONS_NUM = 1, // single read/write
  parameter integer DATA_WIDTH = 32,
  parameter integer ADDR_WIDTH = 7
) (
  ////////////////////////////////////////////////////////////////////////////
  // Asserts when write transactions are complete
  //output wire WCOMPLETE,
  ////////////////////////////////////////////////////////////////////////////
  // Asserts when read transactions are complete
  //output wire RCOMPLETE,
  ////////////////////////////////////////////////////////////////////////////
  // System Signals
  input wire M_AXI_ACLK,
  input wire M_AXI_ARESETN,
  
  // added by Andi, simple AXI stream slave interface to write data to given address
  input [ADDR_WIDTH-1:0] wr_addr,
  input [DATA_WIDTH-1:0] wr_data,
  input wr_valid,
  output wr_ready,
  
  // added by Andi, simple AXI stream master interface to read data from given address
  input [ADDR_WIDTH-1:0] rd_addr,
  output [DATA_WIDTH-1:0] rd_data,
  output rd_valid,
  input rd_ready,

  ////////////////////////////////////////////////////////////////////////////
  // Master Interface Write Address Channel ports
  // Write address (issued by master)
  //output wire [`C_M_AXI_ADDR_WIDTH-1:0] M_AXI_AWADDR,
  output wire [ADDR_WIDTH-1:0] M_AXI_AWADDR,

  ////////////////////////////////////////////////////////////////////////////
  // Write channel Protection type. This signal indicates the
  // privilege and security level of the transaction, and whether
  // the transaction is a data access or an instruction access.
  output wire [2:0] M_AXI_AWPROT,

  ////////////////////////////////////////////////////////////////////////////
  //Write address valid. This signal indicates that the master signaling
  // valid write address and control information.
  output wire M_AXI_AWVALID,

  ////////////////////////////////////////////////////////////////////////////
  // Write address ready. This signal indicates that the slave is ready
  // to accept an address and associated control signals.
  input wire M_AXI_AWREADY,

  ////////////////////////////////////////////////////////////////////////////
  // Master Interface Write Data Channel ports

  ////////////////////////////////////////////////////////////////////////////
  // Write data (issued by master)
  //output wire [`C_M_AXI_DATA_WIDTH-1:0] M_AXI_WDATA,
  output wire [DATA_WIDTH-1:0] M_AXI_WDATA,

  ////////////////////////////////////////////////////////////////////////////
  // Write strobes. This signal indicates which byte lanes hold
  // valid data. There is one write strobe bit for each eight
  // bits of the write data bus.
  //output wire [`C_M_AXI_DATA_WIDTH/8-1:0] M_AXI_WSTRB,
  output wire [DATA_WIDTH/8-1:0] M_AXI_WSTRB,

  ////////////////////////////////////////////////////////////////////////////
  //Write valid. This signal indicates that valid write
  // data and strobes are available.
  output wire M_AXI_WVALID,

  ////////////////////////////////////////////////////////////////////////////
  // Write ready. This signal indicates that the slave
  // can accept the write data.
  input wire M_AXI_WREADY,

  ////////////////////////////////////////////////////////////////////////////
  // Master Interface Write Response Channel ports

  ////////////////////////////////////////////////////////////////////////////
  // Write response. This signal indicates the status
  // of the write transaction.
  input wire [1:0] M_AXI_BRESP,

  ////////////////////////////////////////////////////////////////////////////
  // Write response valid. This signal indicates that the channel
  // is signaling a valid write response.
  input wire M_AXI_BVALID,

  ////////////////////////////////////////////////////////////////////////////
  // Response ready. This signal indicates that the master
  // can accept a write response.
  output wire M_AXI_BREADY,

  ////////////////////////////////////////////////////////////////////////////
  // Master Interface Read Address Channel ports

  ////////////////////////////////////////////////////////////////////////////
  // Read address (issued by master)
  //output wire [`C_M_AXI_ADDR_WIDTH-1:0] M_AXI_ARADDR,
  output wire [ADDR_WIDTH-1:0] M_AXI_ARADDR,

  ////////////////////////////////////////////////////////////////////////////
  // Protection type. This signal indicates the privilege
  // and security level of the transaction, and whether the
  // transaction is a data access or an instruction access.
  output wire [2:0] M_AXI_ARPROT,

  ////////////////////////////////////////////////////////////////////////////
  // Read address valid. This signal indicates that the channel
  // is signaling valid read address and control information.
  output wire M_AXI_ARVALID,

  ////////////////////////////////////////////////////////////////////////////
  // Read address ready. This signal indicates that the slave is
  // ready to accept an address and associated control signals.
  input wire M_AXI_ARREADY,

  ////////////////////////////////////////////////////////////////////////////
  // Master Interface Read Data Channel ports

  ////////////////////////////////////////////////////////////////////////////
  // Read data (issued by slave)
  //input wire [`C_M_AXI_DATA_WIDTH-1:0]  M_AXI_RDATA,
  input wire [DATA_WIDTH-1:0]  M_AXI_RDATA,

  ////////////////////////////////////////////////////////////////////////////
  // Read response. This signal indicates the status of the
  // read transfer.
  input wire [1:0] M_AXI_RRESP,

  ////////////////////////////////////////////////////////////////////////////
  // Read valid. This signal indicates that the channel is
  // signaling the required read data.
  input wire M_AXI_RVALID,

  ////////////////////////////////////////////////////////////////////////////
  // Read ready. This signal indicates that the master can
  // accept the read data and response information.
  output wire M_AXI_RREADY
);


////////////////////////////////////////////////////////////////////////////
// The master will start generating data from the LP_START_DATA_VALUE value
//localparam LP_START_DATA_VALUE  = {`C_M_AXI_DATA_WIDTH/8{8'hAA}};

////////////////////////////////////////////////////////////////////////////
// The master requires a target slave base address. The master will initiate
// read and write transactions on the slave with base address specified
// here as a parameter.
//localparam LP_TARGET_SLAVE_BASE_ADDR  = `C_M_AXI_ADDR_WIDTH'h4000;

////////////////////////////////////////////////////////////////////////////
// Start count is the numeber of clock cycles the master will wait
// before initiating/issuing any transaction.
//localparam integer LP_START_COUNT    = 32;

////////////////////////////////////////////////////////////////////////////
// AXI4 Lite internal signals

////////////////////////////////////////////////////////////////////////////
// write address valid
reg axi_awvalid;
////////////////////////////////////////////////////////////////////////////
// write data valid
reg axi_wvalid;
////////////////////////////////////////////////////////////////////////////
// read address valid
reg axi_arvalid;
////////////////////////////////////////////////////////////////////////////
// read data acceptance
reg axi_rready;
////////////////////////////////////////////////////////////////////////////
// write response acceptance
reg axi_bready;
////////////////////////////////////////////////////////////////////////////
// write address
//reg [`C_M_AXI_ADDR_WIDTH-1:0] axi_awaddr;
reg [ADDR_WIDTH-1:0] axi_awaddr;
////////////////////////////////////////////////////////////////////////////
// write data
//reg [`C_M_AXI_DATA_WIDTH-1:0] axi_wdata;
reg [DATA_WIDTH-1:0] axi_wdata;
////////////////////////////////////////////////////////////////////////////
// read addresss
//reg [`C_M_AXI_ADDR_WIDTH-1:0] axi_araddr;
reg [ADDR_WIDTH-1:0] axi_araddr;

////////////////////////////////////////////////////////////////////////////
//Example-specific design signals
// All the following wire/reg are used in the current example.
// for demonstation.

// function called clogb2 that returns an integer which has the
// value of the ceiling of the log base 2.
function integer clogb2 (input integer bd);
integer bit_depth;
begin
  bit_depth = bd;
  for(clogb2=0; bit_depth>0; clogb2=clogb2+1)
    bit_depth = bit_depth >> 1;
  end
endfunction

////////////////////////////////////////////////////////////////////////////
// Example user application signals

// LP_WAIT_COUNT_BITS is the width of the wait counter.
//localparam integer LP_WAIT_COUNT_BITS = clogb2(LP_START_COUNT-1);
////////////////////////////////////////////////////////////////////////////
// wait counter. The master waits for the user defined number of
// clock cycles before initiating a transfer.
//reg [LP_WAIT_COUNT_BITS-1:0] count;

////////////////////////////////////////////////////////////////////////////
// LP_TRANS_NUM_BITS is the width of the index counter for
// number of write or read transaction.
//localparam integer LP_TRANS_NUM_BITS = clogb2(C_TRANSACTIONS_NUM-1);

////////////////////////////////////////////////////////////////////////////
// Asserts when there is a write response error
wire write_resp_error;
////////////////////////////////////////////////////////////////////////////
// Asserts when there is a read response error
wire read_resp_error;
////////////////////////////////////////////////////////////////////////////
// A pulse to initiate a write transaction
reg start_single_write;
////////////////////////////////////////////////////////////////////////////
// A pulse to initiate a read transaction
reg start_single_read;

////////////////////////////////////////////////////////////////////////////
// Asserts when a single beat write transaction is issued and
// remains asserted till the completion of write trasaction.
reg write_issued;

////////////////////////////////////////////////////////////////////////////
// Asserts when a single beat read transaction is issued and
// remains asserted till the completion of read trasaction.
reg read_issued;

////////////////////////////////////////////////////////////////////////////
// flag that marks the completion of write trasactions. The number of
// write transaction is user selected by the parameter C_TRANSACTIONS_NUM
(* mark_debug = "true" *) reg writes_done;

////////////////////////////////////////////////////////////////////////////
// flag that marks the completion of read trasactions. The number of read
// transaction is user selected by the parameter C_TRANSACTIONS_NUM
(* mark_debug = "true" *) reg reads_done;

////////////////////////////////////////////////////////////////////////////
// The error register is asserted when any of the write response
// error, read response error or the data mismatch flags are asserted.
(* mark_debug = "true" *) reg error_reg;

////////////////////////////////////////////////////////////////////////////
// index counter to track the number of write transaction issued
//reg [7:0] write_index;
////////////////////////////////////////////////////////////////////////////
// index counter to track the number of read transaction issued
//reg [7:0] read_index;

////////////////////////////////////////////////////////////////////////////
// Flag marks the completion of comparison of the read
// data with the expected read data
//(* mark_debug = "true" *) reg compare_done;

////////////////////////////////////////////////////////////////////////////
// This flag is asserted when there is a mismatch of
// the read data with the expected read data.
//(* mark_debug = "true" *) reg read_mismatch;

////////////////////////////////////////////////////////////////////////////
// Flag is asserted when the write index reaches the last write transction number
//reg last_write;
////////////////////////////////////////////////////////////////////////////
// Flag is asserted when the read index reaches the last read transction number
//reg last_read;

////////////////////////////////////////////////////////////////////////////
 // Example State machine to initialize counter, initialize write transactions,
 // initialize read transactions and comparison of read data with the
 // written data words.
/*localparam [1:0] INIT_COUNTER = 2'b00, // This state initializes the counter, ones
                                       // the counter reaches LP_START_COUNT count,
                                       // the state machine changes state to INIT_WRITE
                 INIT_WRITE   = 2'b01, // This state initializes write transaction,
                                       // once writes are done, the state machine
                                       // changes state to INIT_READ
                 INIT_READ = 2'b10,    // This state initializes read transaction
                                       // once reads are done, the state machine
                                       // changes state to INIT_COMPARE
                 INIT_COMPARE = 2'b11; // This state issues the status of comparison
                                       // of the written data with the read data
                                       */
  localparam [1:0]  STATE_WAIT    = 2'b00,    // wait for input
                    STATE_WRITE   = 2'b01,    // This state initializes write transaction,
                    STATE_READ    = 2'b10;    // This state initializes read transaction

reg [1:0] mst_exec_state;

////////////////////////////////////////////////////////////////////////////
// I/O Connections //

////////////////////////////////////////////////////////////////////////////
// Write Address (AW)

////////////////////////////////////////////////////////////////////////////
// Adding the offset address to the base addr of the slave
//assign M_AXI_AWADDR  = LP_TARGET_SLAVE_BASE_ADDR | axi_awaddr;
assign M_AXI_AWADDR  = axi_awaddr;
////////////////////////////////////////////////////////////////////////////
// AXI 4 write data
assign M_AXI_WDATA   = axi_wdata;
assign M_AXI_AWPROT  = 3'h0;
assign M_AXI_AWVALID = axi_awvalid;

////////////////////////////////////////////////////////////////////////////
//Write Data(W)
assign M_AXI_WVALID = axi_wvalid;

////////////////////////////////////////////////////////////////////////////
//Set all byte strobes in this example
//assign M_AXI_WSTRB  = {`C_M_AXI_DATA_WIDTH/8{1'b1}};
assign M_AXI_WSTRB  = {DATA_WIDTH/8{1'b1}};

////////////////////////////////////////////////////////////////////////////
//Write Response (B)
assign M_AXI_BREADY = axi_bready;

////////////////////////////////////////////////////////////////////////////
//Read Address (AR)
//assign M_AXI_ARADDR = LP_TARGET_SLAVE_BASE_ADDR | axi_araddr;
assign M_AXI_ARADDR = rd_addr; // unbuffered, so dont change during transaction!
assign M_AXI_ARVALID = axi_arvalid;
assign M_AXI_ARPROT = 3'h0;

////////////////////////////////////////////////////////////////////////////
//Read and Read Response (R)
assign M_AXI_RREADY = axi_rready;

////////////////////////////////////////////////////////////////////////////
//Example design I/O

//assign WCOMPLETE  = writes_done;
//assign RCOMPLETE  = reads_done;


////////////////////////////////////////////////////////////////////////////
//Write Address Channel
// The purpose of the write address channel is to request the address and
// command information for the entire transaction.  It is a single beat
// of information.
//
// Note for this example the axi_awvalid/axi_wvalid are asserted at the same
// time, and then each is deasserted independent from each other.
// This is a lower-performance, but simplier control scheme.
//
// AXI VALID signals must be held active until accepted by the partner.
//
// A data transfer is accepted by the slave when a master has
// VALID data and the slave acknoledges it is also READY. While the master
// is allowed to generated multiple, back-to-back requests by not
// deasserting VALID, this design will add rest cycle for
// simplicity.
//
// Since only one outstanding transaction is issued by the user design,
// there will not be a collision between a new request and an accepted
// request on the same clock cycle.

always @(posedge M_AXI_ACLK) begin
  ////////////////////////////////////////////////////////////////////////////
  //Only VALID signals must be deasserted during reset per AXI spec
  //Consider inverting then registering active-low reset for higher fmax
  if (M_AXI_ARESETN == 0 ) begin
    axi_awvalid <= 1'b0;
  end else begin
    ////////////////////////////////////////////////////////////////////////////
    //Signal a new address/data command is available by user logic
    if (start_single_write) begin
      axi_awvalid <= 1'b1;
    end else if (M_AXI_AWREADY && axi_awvalid) begin
    ////////////////////////////////////////////////////////////////////////////
    //Address accepted by interconnect/slave (issue of M_AXI_AWREADY by slave)
      axi_awvalid <= 1'b0;
    end
  end
end

////////////////////////////////////////////////////////////////////////////
// start_single_write triggers a new write
// transaction. write_index is a counter to
// keep track with number of write transaction
/* issued/initiated
always @(posedge M_AXI_ACLK) begin
  if (M_AXI_ARESETN == 0 ) begin
    write_index <= 8'h00;
  end else if (start_single_write) begin
    ////////////////////////////////////////////////////////////////////////////
    // Signals a new write address/ write data is
    // available by user logic
    write_index <= write_index + 1;
  end
end*/

////////////////////////////////////////////////////////////////////////////
//Write Data Channel
//
// The write data channel is for transfering the actual data.
//
// The data generation is speific to the example design, and
// so only the WVALID/WREADY handshake is shown here
always @(posedge M_AXI_ACLK) begin
  if (M_AXI_ARESETN == 0 ) begin
    axi_wvalid <= 1'b0;
  end else if (start_single_write) begin
    ////////////////////////////////////////////////////////////////////////////
    //Signal a new address/data command is available by user logic
    axi_wvalid <= 1'b1;
  end else if (M_AXI_WREADY && axi_wvalid) begin
    ////////////////////////////////////////////////////////////////////////////
    //Data accepted by interconnect/slave (issue of M_AXI_WREADY by slave)
     axi_wvalid <= 1'b0;
   end
end

////////////////////////////////////////////////////////////////////////////
//Write Response (B) Channel
//
// The write response channel provides feedback that the write has committed
// to memory. BREADY will occur after both the data and the write address
// has arrived and been accepted by the slave, and can guarantee that no
// other accesses launched afterwards will be able to be reordered before it.
//
// The BRESP bit [1] is used indicate any errors from the interconnect or
// slave for the entire write burst. This example will capture the error.
//
// While not necessary per spec, it is advisable to reset READY signals in
// case of differing reset latencies between master/slave.
always @(posedge M_AXI_ACLK) begin
  if (M_AXI_ARESETN == 0 ) begin
    axi_bready <= 1'b0;
  end else if (M_AXI_BVALID && ~axi_bready) begin
  ////////////////////////////////////////////////////////////////////////////
  // accept/acknowledge bresp with axi_bready by the master
  // when M_AXI_BVALID is asserted by slave
    axi_bready <= 1'b1;
  end else if (axi_bready) begin
    ////////////////////////////////////////////////////////////////////////////
    // deassert after one clock cycle
    axi_bready <= 1'b0;
  end else begin
    ////////////////////////////////////////////////////////////////////////////
    // retain the previous value
    axi_bready <= axi_bready;
  end
end

////////////////////////////////////////////////////////////////////////////
//Flag write errors
assign write_resp_error = (axi_bready & M_AXI_BVALID & M_AXI_BRESP[1]);

////////////////////////////////////////////////////////////////////////////
//Read Address Channel
//
// start_single_read triggers a new read
// transaction. read_index is a counter to
// keep track with number of read transaction
/* issued/initiated
always @(posedge M_AXI_ACLK) begin
  if (M_AXI_ARESETN == 0 ) begin
    read_index <= 8'h00;
  end else if (start_single_read) begin
    // Signals a new read address is
    // available by user logic
    read_index <= read_index + 1;
  end
end*/

////////////////////////////////////////////////////////////////////////////
// A new axi_arvalid is asserted when there is a valid read address
// available by the master. start_single_read triggers a new read
// transaction
always @(posedge M_AXI_ACLK) begin
  if (M_AXI_ARESETN == 0 ) begin
    axi_arvalid <= 1'b0;
  end else if (start_single_read) begin
  ////////////////////////////////////////////////////////////////////////////
  //Signal a new read address command is available by user logic
    axi_arvalid <= 1'b1;
  end else if (M_AXI_ARREADY && axi_arvalid) begin
  ////////////////////////////////////////////////////////////////////////////
  //RAddress accepted by interconnect/slave (issue of M_AXI_ARREADY by slave)
    axi_arvalid <= 1'b0;
  end
end

////////////////////////////////////////////////////////////////////////////
//Read Data (and Response) Channel
//
// The Read Data channel returns the results of the read request
// The master will accept the read data by asserting axi_rready
// when there is a valid read data available.
// While not necessary per spec, it is advisable to reset READY signals in
// case of differing reset latencies between master/slave.
always @(posedge M_AXI_ACLK) begin
  if (M_AXI_ARESETN == 0 ) begin
    axi_rready <= 1'b0;
  end else if (M_AXI_RVALID && ~axi_rready) begin
  ////////////////////////////////////////////////////////////////////////////
  // accept/acknowledge rdata/rresp with axi_rready by the master
  // when M_AXI_RVALID is asserted by slave
    axi_rready <= 1'b1;
  end else if (axi_rready) begin
  ////////////////////////////////////////////////////////////////////////////
  // deassert after one clock cycle
    axi_rready <= 1'b0;
  end
end

////////////////////////////////////////////////////////////////////////////
//Flag write errors
assign read_resp_error = (axi_rready & M_AXI_RVALID & M_AXI_RRESP[1]);

////////////////////////////////////////////////////////////////////////////
//Address/Data Stimulus
//
// Address/data pairs for this example. The read and write values should
// match.
//
// Modify these as desired for different address patterns.

////////////////////////////////////////////////////////////////////////////
/*Write Addresses
always @(posedge M_AXI_ACLK) begin
  if (M_AXI_ARESETN == 0) begin
    axi_awaddr <= {`C_M_AXI_ADDR_WIDTH{1'b0}};
  end else if (M_AXI_AWREADY && axi_awvalid) begin
    axi_awaddr <= axi_awaddr + (`C_M_AXI_DATA_WIDTH/8);
  end else begin
    axi_awaddr <= axi_awaddr;
  end
end*/
always @(posedge M_AXI_ACLK) begin
  if (M_AXI_ARESETN == 0) begin
    axi_awaddr <= {ADDR_WIDTH{1'b0}};
  end else if ( wr_ready & wr_valid ) begin
    axi_awaddr <= wr_addr;
  end else begin
    axi_awaddr <= axi_awaddr;
  end
end

////////////////////////////////////////////////////////////////////////////
//Read Addresses
/*
always @(posedge M_AXI_ACLK) begin
  if (M_AXI_ARESETN == 0) begin
    axi_araddr <= {`C_M_AXI_ADDR_WIDTH{1'b0}};
  end else if (M_AXI_ARREADY && axi_arvalid) begin
    axi_araddr <= axi_araddr + (`C_M_AXI_DATA_WIDTH/8);
  end else begin
    axi_araddr <= axi_araddr;
  end
end 
always @(posedge M_AXI_ACLK) begin
  if (M_AXI_ARESETN == 0) begin
    //axi_wdata <= LP_START_DATA_VALUE;
    axi_wdata <= {`C_M_AXI_DATA_WIDTH{1'b0}};
  end else if (M_AXI_WREADY && axi_wvalid) begin
    //axi_wdata <= LP_START_DATA_VALUE + {(`C_M_AXI_DATA_WIDTH/8){write_index}};
    axi_wdata <= wr_data;
  end else begin
    axi_wdata <= axi_wdata;
  end
end
*/

always @(posedge M_AXI_ACLK) begin
  if (M_AXI_ARESETN == 0) begin
    axi_araddr <= {ADDR_WIDTH{1'b0}};
  end else if ( rd_ready & rd_valid ) begin
    axi_araddr <= rd_addr;
  end else begin
    axi_araddr <= axi_araddr;
  end
end

always @(posedge M_AXI_ACLK) begin
  if (M_AXI_ARESETN == 0) begin
    axi_wdata <= {DATA_WIDTH{1'b0}};
  end else if ( wr_ready & wr_valid ) begin
    axi_wdata <= wr_data;
  end else begin
    axi_wdata <= axi_wdata;
  end
end

/*
////////////////////////////////////////////////////////////////////////////
//implement master command interface state machine
always @ ( posedge M_AXI_ACLK) begin
  if (M_AXI_ARESETN == 1'b0 ) begin
    ////////////////////////////////////////////////////////////////////////////
    // reset condition
    // All the signals are assigned default values under reset condition
    mst_exec_state  <= INIT_COUNTER;
    count    <= 0;
    start_single_write <= 1'b0;
    write_issued  <= 1'b0;
    start_single_read  <= 1'b0;
    read_issued   <= 1'b0;
    compare_done  <= 1'b0;
  end else begin
  ////////////////////////////////////////////////////////////////////////////
  // state transition
    case (mst_exec_state)
      INIT_COUNTER: begin
        ////////////////////////////////////////////////////////////////////////////
        // This state is responsible to wait for user defined LP_START_COUNT
        // number of clock cycles.
          if ( count == LP_START_COUNT - 1 ) begin
            mst_exec_state  <= INIT_WRITE;
          end else begin
            count <= count + 1;
            mst_exec_state  <= INIT_COUNTER;
          end
        end

      INIT_WRITE: begin
        ////////////////////////////////////////////////////////////////////////////
        // This state is responsible to issue start_single_write pulse to
        // initiate a write transaction. Write transactions will be
        // issued until last_write signal is asserted.
        // write controller
        if (writes_done) begin
          mst_exec_state <= INIT_READ;
        end else begin
          mst_exec_state  <= INIT_WRITE;

          if (~axi_awvalid && ~axi_wvalid && ~M_AXI_BVALID && ~last_write && ~start_single_write && ~write_issued) begin
            start_single_write <= 1'b1;
            write_issued  <= 1'b1;
          end else if (axi_bready) begin
            write_issued  <= 1'b0;
          end else begin
            start_single_write <= 1'b0; //Negate to generate a pulse
          end
        end
      end

      INIT_READ: begin
        ////////////////////////////////////////////////////////////////////////////
        // This state is responsible to issue start_single_read pulse to
        // initiate a read transaction. Read transactions will be
        // issued until last_read signal is asserted.
        // read controller
        if (reads_done) begin
          mst_exec_state <= INIT_COMPARE;
        end else begin
          mst_exec_state <= INIT_READ;
        
          if (~axi_arvalid && ~M_AXI_RVALID && ~last_read && ~start_single_read && ~read_issued) begin
            start_single_read <= 1'b1;
            read_issued  <= 1'b1;
          end else if (axi_rready) begin
            read_issued  <= 1'b0;
          end else begin
            start_single_read <= 1'b0; //Negate to generate a pulse
          end
        end
      end

      INIT_COMPARE: begin
        ////////////////////////////////////////////////////////////////////////////
        // This state is responsible to issue the state of comparison
        // of written data with the read data. If no error flags are set,
        // compare_done signal will be asseted to indicate success.
        if (~error_reg) begin
          mst_exec_state <= INIT_COMPARE;
          compare_done <= 1'b1;
        end
      end
//      default : begin
//        mst_exec_state  <= INIT_COUNTER;
//      end
    endcase
  end
end //MASTER_EXECUTION_PROC
*/

////////////////////////////////////////////////////////////////////////////
//implement master command interface state machine
reg wr_ready_ff;
reg rd_valid_ff;
reg [DATA_WIDTH-1:0] rd_data_ff;
always @ ( posedge M_AXI_ACLK) begin
  if (M_AXI_ARESETN == 1'b0 ) begin
    mst_exec_state  <= STATE_WAIT;
    start_single_write <= 1'b0;
    write_issued  <= 1'b0;
    start_single_read  <= 1'b0;
    read_issued   <= 1'b0;
    wr_ready_ff <= 1'b1;
    rd_valid_ff <= 1'b1; // for simplicity so do not need to distingiush first time
    rd_data_ff <= 0;
  end else begin
    case (mst_exec_state)
      STATE_WAIT: begin
        if ( wr_ready & wr_valid ) begin
            mst_exec_state <= STATE_WRITE;
            wr_ready_ff <= 1'b0;
        end
        else if ( rd_ready & rd_valid ) begin
            mst_exec_state <= STATE_READ;
            rd_valid_ff <= 1'b0;
        end
        else begin 
            mst_exec_state <= STATE_WAIT;
        end
      end
      STATE_WRITE: begin
        if (writes_done) begin
          mst_exec_state <= STATE_WAIT;
          wr_ready_ff <= 1'b1;
        end else begin
          mst_exec_state  <= STATE_WRITE;
          wr_ready_ff <= 1'b0;

          if (~axi_awvalid && ~axi_wvalid && ~M_AXI_BVALID && ~start_single_write && ~write_issued) begin
            start_single_write <= 1'b1;
            write_issued  <= 1'b1;
          end else if (axi_bready) begin
            write_issued  <= 1'b0;
          end else begin
            start_single_write <= 1'b0; //Negate to generate a pulse
          end
        end
      end
      STATE_READ: begin
        if (reads_done) begin
          mst_exec_state <= STATE_WAIT;
          rd_valid_ff <= 1'b1;
          rd_data_ff <= M_AXI_RDATA;
        end else begin
          mst_exec_state <= STATE_READ;
          rd_valid_ff <= 1'b0;
          
          //if (~axi_arvalid && ~M_AXI_RVALID && ~last_read && ~start_single_read && ~read_issued) begin
          if (~axi_arvalid && ~M_AXI_RVALID  && ~start_single_read && ~read_issued) begin
            start_single_read <= 1'b1;
            read_issued  <= 1'b1;
          end else if (axi_rready) begin
            read_issued  <= 1'b0;
          end else begin
            start_single_read <= 1'b0; //Negate to generate a pulse
          end
        end
      end
      default : begin
        mst_exec_state  <= STATE_WAIT;
      end
    endcase
  end
end //MASTER_EXECUTION_PROC

// assig axi slave ready/valid signals
assign wr_ready = wr_ready_ff;
assign rd_valid = rd_valid_ff;
assign rd_data = rd_data_ff;

////////////////////////////////////////////////////////////////////////////
//Terminal write count
/*
always @(posedge M_AXI_ACLK) begin
  if (M_AXI_ARESETN == 0) begin
    last_write <= 1'b0;
  end else if ((write_index == C_TRANSACTIONS_NUM) && M_AXI_AWREADY) begin
    ////////////////////////////////////////////////////////////////////////////
    //The last write should be associated with a write address ready response
    last_write <= 1'b1;
  end else begin
    last_write <= last_write;
  end
end*/

////////////////////////////////////////////////////////////////////////////
//  Check for last write completion.
//
//  This logic is to qualify the last write count with the final write
//  response. This demonstrates how to confirm that a write has been
//  committed.

always @(posedge M_AXI_ACLK) begin
  if (M_AXI_ARESETN == 0) begin
    writes_done <= 1'b0;
  //end else if (last_write && M_AXI_BVALID && axi_bready) begin
  end else if (M_AXI_BVALID && axi_bready) begin
    //The writes_done should be associated with a bready response
    writes_done <= 1'b1;
  end else begin
    //writes_done <= writes_done;
    writes_done <= 1'b0;
  end
end

////////////////////////////////////////////////////////////////////////////
//Read example
/*Terminal Read Count
always @(posedge M_AXI_ACLK) begin
  if (M_AXI_ARESETN == 0) begin
    last_read <= 1'b0;
  end else if ((read_index == C_TRANSACTIONS_NUM) && (M_AXI_ARREADY) ) begin
    ////////////////////////////////////////////////////////////////////////////
    //The last read should be associated with a read address ready response
    last_read <= 1'b1;
  end else begin
    last_read <= last_read;
  end
end
*/
////////////////////////////////////////////////////////////////////////////
// Check for last read completion.
//
// This logic is to qualify the last read count with the final read
// response/data.
always @(posedge M_AXI_ACLK) begin
  if (M_AXI_ARESETN == 0) begin
    reads_done <= 1'b0;
  //end else if (last_read && M_AXI_RVALID && axi_rready) begin
  end else if (M_AXI_RVALID && axi_rready) begin
    ////////////////////////////////////////////////////////////////////////////
    //The reads_done should be associated with a read ready response
    reads_done <= 1'b1;
  end else begin
    //reads_done <= reads_done;
    reads_done <= 1'b0;
  end
end

////////////////////////////////////////////////////////////////////////////
//Example design error register

/*
////////////////////////////////////////////////////////////////////////////
//Data Comparison
always @(posedge M_AXI_ACLK) begin
  if (M_AXI_ARESETN == 0) begin
    read_mismatch <= 1'b0;
  end else if (M_AXI_RVALID && axi_rready) begin
    ////////////////////////////////////////////////////////////////////////////
    //The read data when available (on axi_rready) is compared with the expected data
    case (read_index)
      1: read_mismatch <= (LP_START_DATA_VALUE + {(`C_M_AXI_DATA_WIDTH/8){8'h00}}) != M_AXI_RDATA;
      2: read_mismatch <= (LP_START_DATA_VALUE + {(`C_M_AXI_DATA_WIDTH/8){8'h01}}) != M_AXI_RDATA;
      3: read_mismatch <= (LP_START_DATA_VALUE + {(`C_M_AXI_DATA_WIDTH/8){8'h02}}) != M_AXI_RDATA;
      4: read_mismatch <= (LP_START_DATA_VALUE + {(`C_M_AXI_DATA_WIDTH/8){8'h03}}) != M_AXI_RDATA;
      default: read_mismatch <= {`C_M_AXI_DATA_WIDTH{1'b0}} != M_AXI_RDATA;
    endcase
  end else begin
    read_mismatch <= read_mismatch;
  end
end
*/

////////////////////////////////////////////////////////////////////////////
// Register and hold any data mismatches, or read/write interface errors
always @(posedge M_AXI_ACLK)  begin
  if (M_AXI_ARESETN == 0) begin
      error_reg <= 1'b0;
  //end else if (read_mismatch || write_resp_error || read_resp_error) begin
  end else if (write_resp_error || read_resp_error) begin
    ////////////////////////////////////////////////////////////////////////////
    //Capture any error types
      error_reg <= 1'b1;
  end else begin
    error_reg <= error_reg;
  end
end

endmodule
