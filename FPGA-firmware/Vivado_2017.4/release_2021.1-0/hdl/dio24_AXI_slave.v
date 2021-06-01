`timescale 1 ns / 1 ps
//////////////////////////////////////////////////////////////////////////////////
// dio24_AXI_slave module, created 2019, revised 02-03/2020 by Andi
// implements AXI Lite bus for register input and output
// this is a modified version of the Xilinx AXI slave module XXXX_v1_0_S00_AXI
// automatically created with Tools - Create and Package new IP - 
// - Create a new AXI Peripheral - and select AXI Lite slave
// parameters:
// - C_S_AXI_DATA_WIDTH = AXI Lite bus data width, should be 32
// - C_S_AXI_ADDR_WIDTH = AXI Lite address width. this defines max. number 
//                        of registers = 2^(C_S_AXI_ADDR_WIDTH-2)
// - NUM_CTR = number of control registers (= output register)
// - NUM_STATUS = number of status registers (= input register)
// control registers:
// - control = bitwise application control
// - num_samples = total number of samples
// status registers:
// - status = bitwise application status
// - board_time = actual time
// - board_samples = actual number of received samples
// - board_time_ext = extra/additional board_time for tests
// - board_samples_ext = extra/additional board samples for tests
// AXI Lite ports:
//   ...copied form Xilinx sample, do not modify
// notes:
// - to add more control/status register just define them as additional output/input
//   and ensure C_S_AXI_ADDR_WIDTH is large enough to address all registers.
//   increase NUM_CTRL/NUM_STATUS accordingly and assign registers at the end of this code.
//   the register address is the index in the assignment * 4 (4 bytes per register).
// - at the moment when reading back the "value" of a control register it gives the last
//   written value, but sometimes one would like to read status information like this.
//   this could be implemented but is not done here. instead use a separate status register. 
// last change 23/2/2020 by Andi
//////////////////////////////////////////////////////////////////////////////////

  module dio24_AXI_slave #
  (
    // Width of S_AXI data bus
    parameter integer C_S_AXI_DATA_WIDTH  = 32,
    // Width of S_AXI address bus
    parameter integer C_S_AXI_ADDR_WIDTH  = 7, // 7: 2^7/4 = 32 registers

    // Users to add parameters here
    
    parameter integer NUM_CTRL = 5,     // number of control registers (must match user outputs)
    parameter integer NUM_STATUS = 6,   // number of status registers (must match user inputs)
    parameter integer REG_CTRL = 0,     // index of control register
    parameter integer REG_CTRL_RESET = 0    // index of reset bit in control register - used for auto-reset  
    
    // User parameters ends
    // Do not modify the parameters beyond this line
  )
  (
    // Users to add ports here

    // register 0 = control register
    output wire [C_S_AXI_DATA_WIDTH-1:0] control,
    // register 1 = test control bits
    output wire [C_S_AXI_DATA_WIDTH-1:0] ctrl_test,
    // register 2 = number of samples
    output wire [C_S_AXI_DATA_WIDTH-1:0] num_samples,
    // register 3 = sync delay
    output wire [C_S_AXI_DATA_WIDTH-1:0] sync_delay,    
    // register 4 = synd phase shift
    output wire [C_S_AXI_DATA_WIDTH-1:0] sync_phase,    
    // register 5 = status register
    input wire [C_S_AXI_DATA_WIDTH-1:0] status,
    // register 6 = board time
    input wire [C_S_AXI_DATA_WIDTH-1:0] board_time,
    // register 7 = board samples
    input wire [C_S_AXI_DATA_WIDTH-1:0] board_samples,
    // register 8 = extra board time
    input wire [C_S_AXI_DATA_WIDTH-1:0] board_time_ext,
    // register 9 = extra board samples
    input wire [C_S_AXI_DATA_WIDTH-1:0] board_samples_ext,
    // register 10 = auto-sync round trip time
    input wire [C_S_AXI_DATA_WIDTH-1:0] sync_time,
    // pulses bit corresponding to control register when was updated
    output wire [NUM_CTRL-1:0] ctrl_update,

    // User ports ends
    // Do not modify the ports beyond this line

    // Global Clock Signal
    input wire  S_AXI_ACLK,
    // Global Reset Signal. This Signal is Active LOW
    input wire  S_AXI_ARESETN,
    // Write address (issued by master, acceped by Slave)
    input wire [C_S_AXI_ADDR_WIDTH-1 : 0] S_AXI_AWADDR,
    // Write channel Protection type. This signal indicates the
    // privilege and security level of the transaction, and whether
    // the transaction is a data access or an instruction access.
    input wire [2 : 0] S_AXI_AWPROT,
    // Write address valid. This signal indicates that the master signaling
    // valid write address and control information.
    input wire  S_AXI_AWVALID,
    // Write address ready. This signal indicates that the slave is ready
    // to accept an address and associated control signals.
    output wire  S_AXI_AWREADY,
    // Write data (issued by master, acceped by Slave) 
    input wire [C_S_AXI_DATA_WIDTH-1 : 0] S_AXI_WDATA,
    // Write strobes. This signal indicates which byte lanes hold
    // valid data. There is one write strobe bit for each eight
    // bits of the write data bus.    
    input wire [(C_S_AXI_DATA_WIDTH/8)-1 : 0] S_AXI_WSTRB,
    // Write valid. This signal indicates that valid write
    // data and strobes are available.
    input wire  S_AXI_WVALID,
    // Write ready. This signal indicates that the slave
    // can accept the write data.
    output wire  S_AXI_WREADY,
    // Write response. This signal indicates the status
    // of the write transaction.
    output wire [1 : 0] S_AXI_BRESP,
    // Write response valid. This signal indicates that the channel
    // is signaling a valid write response.
    output wire  S_AXI_BVALID,
    // Response ready. This signal indicates that the master
    // can accept a write response.
    input wire  S_AXI_BREADY,
    // Read address (issued by master, acceped by Slave)
    input wire [C_S_AXI_ADDR_WIDTH-1 : 0] S_AXI_ARADDR,
    // Protection type. This signal indicates the privilege
    // and security level of the transaction, and whether the
    // transaction is a data access or an instruction access.
    input wire [2 : 0] S_AXI_ARPROT,
    // Read address valid. This signal indicates that the channel
    // is signaling valid read address and control information.
    input wire  S_AXI_ARVALID,
    // Read address ready. This signal indicates that the slave is
    // ready to accept an address and associated control signals.
    output wire  S_AXI_ARREADY,
    // Read data (issued by slave)
    output wire [C_S_AXI_DATA_WIDTH-1 : 0] S_AXI_RDATA,
    // Read response. This signal indicates the status of the
    // read transfer.
    output wire [1 : 0] S_AXI_RRESP,
    // Read valid. This signal indicates that the channel is
    // signaling the required read data.
    output wire  S_AXI_RVALID,
    // Read ready. This signal indicates that the master can
    // accept the read data and response information.
    input wire  S_AXI_RREADY
  );

  // AXI4LITE signals
  reg [C_S_AXI_ADDR_WIDTH-1 : 0]   axi_awaddr;
  reg    axi_awready;
  reg    axi_wready;
  reg [1 : 0]   axi_bresp;
  reg    axi_bvalid;
  reg [C_S_AXI_ADDR_WIDTH-1 : 0]   axi_araddr;
  reg    axi_arready;
  reg [C_S_AXI_DATA_WIDTH-1 : 0]   axi_rdata;
  reg [1 : 0]   axi_rresp;
  reg    axi_rvalid;

  // Example-specific design signals
  // local parameter for addressing 32 bit / 64 bit C_S_AXI_DATA_WIDTH
  // ADDR_LSB is used for addressing 32/64 bit registers/memories
  // ADDR_LSB = 2 for 32 bits (n downto 2)
  // ADDR_LSB = 3 for 64 bits (n downto 3)
  localparam integer ADDR_LSB = (C_S_AXI_DATA_WIDTH/32) + 1;
  localparam integer OPT_MEM_ADDR_BITS = C_S_AXI_ADDR_WIDTH - ADDR_LSB -1;
  //----------------------------------------------
  //-- Signals for user logic register space example
  //------------------------------------------------
  wire   slv_reg_rden;
  wire   slv_reg_wren;
  reg [C_S_AXI_DATA_WIDTH-1:0]   reg_data_out;
  integer   byte_index;
  reg   aw_en;

  // I/O Connections assignments

  assign S_AXI_AWREADY  = axi_awready;
  assign S_AXI_WREADY  = axi_wready;
  assign S_AXI_BRESP  = axi_bresp;
  assign S_AXI_BVALID  = axi_bvalid;
  assign S_AXI_ARREADY  = axi_arready;
  assign S_AXI_RDATA  = axi_rdata;
  assign S_AXI_RRESP  = axi_rresp;
  assign S_AXI_RVALID  = axi_rvalid;
  // Implement axi_awready generation
  // axi_awready is asserted for one S_AXI_ACLK clock cycle when both
  // S_AXI_AWVALID and S_AXI_WVALID are asserted. axi_awready is
  // de-asserted when reset is low.

  always @( posedge S_AXI_ACLK )
  begin
    if ( S_AXI_ARESETN == 1'b0 )
      begin
        axi_awready <= 1'b0;
        aw_en <= 1'b1;
      end 
    else
      begin    
        if (~axi_awready && S_AXI_AWVALID && S_AXI_WVALID && aw_en)
          begin
            // slave is ready to accept write address when 
            // there is a valid write address and write data
            // on the write address and data bus. This design 
            // expects no outstanding transactions. 
            axi_awready <= 1'b1;
            aw_en <= 1'b0;
          end
          else if (S_AXI_BREADY && axi_bvalid)
              begin
                aw_en <= 1'b1;
                axi_awready <= 1'b0;
              end
        else           
          begin
            axi_awready <= 1'b0;
          end
      end 
  end       

  // Implement axi_awaddr latching
  // This process is used to latch the address when both 
  // S_AXI_AWVALID and S_AXI_WVALID are valid. 

  always @( posedge S_AXI_ACLK )
  begin
    if ( S_AXI_ARESETN == 1'b0 )
      begin
        axi_awaddr <= 0;
      end 
    else
      begin    
        if (~axi_awready && S_AXI_AWVALID && S_AXI_WVALID && aw_en)
          begin
            // Write Address latching 
            axi_awaddr <= S_AXI_AWADDR;
          end
      end 
  end       

  // Implement axi_wready generation
  // axi_wready is asserted for one S_AXI_ACLK clock cycle when both
  // S_AXI_AWVALID and S_AXI_WVALID are asserted. axi_wready is 
  // de-asserted when reset is low. 

  always @( posedge S_AXI_ACLK )
  begin
    if ( S_AXI_ARESETN == 1'b0 )
      begin
        axi_wready <= 1'b0;
      end 
    else
      begin    
        if (~axi_wready && S_AXI_WVALID && S_AXI_AWVALID && aw_en )
          begin
            // slave is ready to accept write data when 
            // there is a valid write address and write data
            // on the write address and data bus. This design 
            // expects no outstanding transactions. 
            axi_wready <= 1'b1;
          end
        else
          begin
            axi_wready <= 1'b0;
          end
      end 
  end       

  // Implement memory mapped register select and write logic generation
  // The write data is accepted and written to memory mapped registers when
  // axi_awready, S_AXI_WVALID, axi_wready and S_AXI_WVALID are asserted. Write strobes are used to
  // select byte enables of slave registers while writing.
  // These registers are cleared when reset (active low) is applied.
  // Slave register write enable is asserted when valid address and data are available
  // and the slave is ready to accept the write address and write data.
  assign slv_reg_wren = axi_wready && S_AXI_WVALID && axi_awready && S_AXI_AWVALID;

  // Implement write response logic generation
  // The write response and response valid signals are asserted by the slave 
  // when axi_wready, S_AXI_WVALID, axi_wready and S_AXI_WVALID are asserted.  
  // This marks the acceptance of address and indicates the status of 
  // write transaction.

  always @( posedge S_AXI_ACLK )
  begin
    if ( S_AXI_ARESETN == 1'b0 )
      begin
        axi_bvalid  <= 0;
        axi_bresp   <= 2'b0;
      end 
    else
      begin    
        if (axi_awready && S_AXI_AWVALID && ~axi_bvalid && axi_wready && S_AXI_WVALID)
          begin
            // indicates a valid write response is available
            axi_bvalid <= 1'b1;
            axi_bresp  <= 2'b0; // 'OKAY' response 
          end                   // work error responses in future
        else
          begin
            if (S_AXI_BREADY && axi_bvalid) 
              //check if bready is asserted while bvalid is high) 
              //(there is a possibility that bready is always asserted high)   
              begin
                axi_bvalid <= 1'b0; 
              end  
          end
      end
  end   

  // Implement axi_arready generation
  // axi_arready is asserted for one S_AXI_ACLK clock cycle when
  // S_AXI_ARVALID is asserted. axi_awready is 
  // de-asserted when reset (active low) is asserted. 
  // The read address is also latched when S_AXI_ARVALID is 
  // asserted. axi_araddr is reset to zero on reset assertion.

  always @( posedge S_AXI_ACLK )
  begin
    if ( S_AXI_ARESETN == 1'b0 )
      begin
        axi_arready <= 1'b0;
        axi_araddr  <= 32'b0;
      end 
    else
      begin    
        if (~axi_arready && S_AXI_ARVALID)
          begin
            // indicates that the slave has acceped the valid read address
            axi_arready <= 1'b1;
            // Read address latching
            axi_araddr  <= S_AXI_ARADDR;
          end
        else
          begin
            axi_arready <= 1'b0;
          end
      end 
  end       

  // Implement axi_arvalid generation
  // axi_rvalid is asserted for one S_AXI_ACLK clock cycle when both 
  // S_AXI_ARVALID and axi_arready are asserted. The slave registers 
  // data are available on the axi_rdata bus at this instance. The 
  // assertion of axi_rvalid marks the validity of read data on the 
  // bus and axi_rresp indicates the status of read transaction.axi_rvalid 
  // is deasserted on reset (active low). axi_rresp and axi_rdata are 
  // cleared to zero on reset (active low).  
  always @( posedge S_AXI_ACLK )
  begin
    if ( S_AXI_ARESETN == 1'b0 )
      begin
        axi_rvalid <= 0;
        axi_rresp  <= 0;
      end 
    else
      begin    
        if (axi_arready && S_AXI_ARVALID && ~axi_rvalid)
          begin
            // Valid read data is available at the read data bus
            axi_rvalid <= 1'b1;
            axi_rresp  <= 2'b0; // 'OKAY' response
          end   
        else if (axi_rvalid && S_AXI_RREADY)
          begin
            // Read data is accepted by the master
            axi_rvalid <= 1'b0;
          end                
      end
  end    

  // Output register or memory read data
  always @( posedge S_AXI_ACLK )
  begin
    if ( S_AXI_ARESETN == 1'b0 )
      begin
        axi_rdata  <= 0;
      end 
    else
      begin    
        // When there is a valid read address (S_AXI_ARVALID) with 
        // acceptance of read address by the slave (axi_arready), 
        // output the read dada 
        if (slv_reg_rden)
          begin
            axi_rdata <= reg_data_out;     // register read data
          end   
      end
  end    

  // Implement memory mapped register select and read logic generation
  // Slave register read enable is asserted when valid address is available
  // and the slave is ready to accept the read address.
  assign slv_reg_rden = axi_arready & S_AXI_ARVALID & ~axi_rvalid;

    // Add user logic here

    // Andi: write control registers (no modification needed)
    reg [C_S_AXI_DATA_WIDTH-1:0] ctrl_reg[0 : NUM_CTRL - 1];
    generate
    for (genvar i = 0; i < NUM_CTRL; i = i + 1)
    begin: GEN_CTRL

        reg ctrl_update_ff;
        always @ (posedge S_AXI_ACLK) begin
            if ( S_AXI_ARESETN == 1'b0 ) begin
                ctrl_reg[i] <= 0;
                ctrl_update_ff <= 1'b0;
            end
            else begin
                if ((slv_reg_wren) && ( i == axi_awaddr[ADDR_LSB+OPT_MEM_ADDR_BITS:ADDR_LSB] )) begin
                    for ( byte_index = 0; byte_index <= (C_S_AXI_DATA_WIDTH/8)-1; byte_index = byte_index+1 ) begin
                        if ( S_AXI_WSTRB[byte_index] == 1 ) begin
                            ctrl_reg[i][(byte_index*8) +: 8] <= S_AXI_WDATA[(byte_index*8) +: 8];
                        end
                    end
                    ctrl_update_ff <= 1'b1;
                end 
                else begin
                    if ( i == REG_CTRL ) begin // auto-reset of reset bit after 1 cycle
                        ctrl_reg[i] <= ctrl_reg[i] & (~(1<<REG_CTRL_RESET));
                    end
                    ctrl_update_ff <= 1'b0;
                end 
            end
        end
        assign ctrl_update[i] = ctrl_update_ff;
    end
    endgenerate
    
    // Andi: read control and status registers (no modification needed)
    //       control registers return last written value 
    wire [OPT_MEM_ADDR_BITS : 0] r_index = axi_araddr[ADDR_LSB+OPT_MEM_ADDR_BITS:ADDR_LSB];
    wire [C_S_AXI_DATA_WIDTH-1:0] status_reg[NUM_CTRL : NUM_CTRL + NUM_STATUS - 1];
    always @(*) begin
        if ( r_index < NUM_CTRL ) begin
            reg_data_out <= ctrl_reg[r_index];
        end
        else if ( r_index < ( NUM_CTRL + NUM_STATUS ) ) begin
            reg_data_out <= status_reg[r_index];
        end
        else begin
            reg_data_out <= {C_S_AXI_DATA_WIDTH{1'b1}}; // invalid register
        end
    end
    
    // Andi: assign control and status registers with increasing index
    // control register start with index 0
    // status register start with index NUM_CTRL
    // index = register number as seen from software
    assign control        = ctrl_reg[0];
    assign ctrl_test      = ctrl_reg[1];
    assign num_samples    = ctrl_reg[2];
    assign sync_delay     = ctrl_reg[3];
    assign sync_phase     = ctrl_reg[4];
    assign status_reg[ 5] = status;
    assign status_reg[ 6] = board_time;
    assign status_reg[ 7] = board_samples;
    assign status_reg[ 8] = board_time_ext;
    assign status_reg[ 9] = board_samples_ext;
    assign status_reg[10] = sync_time;

    // User logic ends
    
endmodule
