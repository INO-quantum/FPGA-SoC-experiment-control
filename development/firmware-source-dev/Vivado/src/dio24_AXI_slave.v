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
// - NUM_CTR    = number of control registers (= output register)
// - NUM_STATUS = number of status registers (= input register)
// control registers:
// - reg_i_ctrl = written from CPU to FPGA
// status registers:
// - reg_i_sts = read from FPGA by CPA
// AXI Lite ports:
//   ...copied form Xilinx sample, do not modify
// notes:
// - the register address reg_i_.. by the CPU is i * 4 (4 bytes per register).
// - for simplicity we have equal number of control as status registers
// - for the register with i = REG_CTRL the bit REG_CTRL_RESET is auto-reset 
//   after one cycle. this is intended for software reset.
// - to add more control/status register ensure C_S_AXI_ADDR_WIDTH is large enough to address all registers.
//   increase NUM_CTRL/NUM_STATUS accordingly and assign control and status registers
// - at the moment when reading back the "value" of a control register it gives the last
//   written value, but sometimes one would like to read status information like this.
//   this could be implemented but is not done here. instead use a separate status register. 
// last change 2024/11/29 by Andi
//////////////////////////////////////////////////////////////////////////////////

  module dio24_AXI_slave #
  (
    // Width of S_AXI data bus
    parameter integer C_S_AXI_DATA_WIDTH    = 32,
    // Width of S_AXI address bus
    parameter integer C_S_AXI_ADDR_WIDTH    = 8,    // 8: 2^8/4 = 64 registers

    // Users to add parameters here
    
    // number of control and status registers. 
    // sum must be allowed by C_S_AXI_ADDR_WIDTH.  
    parameter integer NUM_CTRL              = 32,
    parameter integer NUM_STATUS            = 32,

    // control register with auto-reset bit 
    parameter integer REG_CTRL              = 0,
    parameter integer REG_CTRL_RESET        = 0,
        
    // initial values for each control register
    parameter integer REG_0_CTRL_INIT   = 0,
    parameter integer REG_1_CTRL_INIT   = 0,
    parameter integer REG_2_CTRL_INIT   = 0,
    parameter integer REG_3_CTRL_INIT   = 0,
    parameter integer REG_4_CTRL_INIT   = 0,
    parameter integer REG_5_CTRL_INIT   = 0,
    parameter integer REG_6_CTRL_INIT   = 0,
    parameter integer REG_7_CTRL_INIT   = 0,
    parameter integer REG_8_CTRL_INIT   = 0,
    parameter integer REG_9_CTRL_INIT   = 0,
    parameter integer REG_10_CTRL_INIT  = 0,
    parameter integer REG_11_CTRL_INIT  = 0,
    parameter integer REG_12_CTRL_INIT  = 0,
    parameter integer REG_13_CTRL_INIT  = 0,
    parameter integer REG_14_CTRL_INIT  = 0,
    parameter integer REG_15_CTRL_INIT  = 0,
    parameter integer REG_16_CTRL_INIT  = 0,
    parameter integer REG_17_CTRL_INIT  = 0,
    parameter integer REG_18_CTRL_INIT  = 0,
    parameter integer REG_19_CTRL_INIT  = 0,
    parameter integer REG_20_CTRL_INIT  = 0,
    parameter integer REG_21_CTRL_INIT  = 0,
    parameter integer REG_22_CTRL_INIT  = 0,
    parameter integer REG_23_CTRL_INIT  = 0,
    parameter integer REG_24_CTRL_INIT  = 0,
    parameter integer REG_25_CTRL_INIT  = 0,
    parameter integer REG_26_CTRL_INIT  = 0,
    parameter integer REG_27_CTRL_INIT  = 0,
    parameter integer REG_28_CTRL_INIT  = 0,
    parameter integer REG_29_CTRL_INIT  = 0,
    parameter integer REG_30_CTRL_INIT  = 0,
    parameter integer REG_31_CTRL_INIT  = 0

    // User parameters ends
    // Do not modify the parameters beyond this line
  )
  (
    // Users to add ports here

    // control register
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_0_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_1_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_2_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_3_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_4_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_5_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_6_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_7_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_8_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_9_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_10_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_11_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_12_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_13_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_14_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_15_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_16_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_17_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_18_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_19_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_20_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_21_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_22_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_23_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_24_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_25_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_26_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_27_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_28_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_29_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_30_ctrl,
    output wire [C_S_AXI_DATA_WIDTH-1:0] reg_31_ctrl,

    // pulses bit corresponding to control register when was updated
    output wire [NUM_CTRL-1:0] reg_ctrl_update,

    // status register
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_32_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_33_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_34_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_35_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_36_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_37_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_38_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_39_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_40_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_41_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_42_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_43_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_44_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_45_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_46_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_47_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_48_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_49_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_50_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_51_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_52_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_53_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_54_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_55_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_56_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_57_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_58_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_59_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_60_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_61_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_62_sts,
    input wire [C_S_AXI_DATA_WIDTH-1:0] reg_63_sts,

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
    //       we init control registers with 0's except NUM_CYCLES = 1
    reg [C_S_AXI_DATA_WIDTH-1:0] ctrl_reg[0 : NUM_CTRL - 1];
    initial begin
        ctrl_reg[0]  = REG_0_CTRL_INIT;
        ctrl_reg[1]  = REG_1_CTRL_INIT;
        ctrl_reg[2]  = REG_2_CTRL_INIT;
        ctrl_reg[3]  = REG_3_CTRL_INIT;
        ctrl_reg[4]  = REG_4_CTRL_INIT;
        ctrl_reg[5]  = REG_5_CTRL_INIT;
        ctrl_reg[6]  = REG_6_CTRL_INIT;
        ctrl_reg[7]  = REG_7_CTRL_INIT;
        ctrl_reg[8]  = REG_8_CTRL_INIT;
        ctrl_reg[9]  = REG_9_CTRL_INIT;
        ctrl_reg[10] = REG_10_CTRL_INIT;
        ctrl_reg[11] = REG_11_CTRL_INIT;
        ctrl_reg[12] = REG_12_CTRL_INIT;
        ctrl_reg[13] = REG_13_CTRL_INIT;
        ctrl_reg[14] = REG_14_CTRL_INIT;
        ctrl_reg[15] = REG_15_CTRL_INIT;
        ctrl_reg[16] = REG_16_CTRL_INIT;
        ctrl_reg[17] = REG_17_CTRL_INIT;
        ctrl_reg[18] = REG_18_CTRL_INIT;
        ctrl_reg[19] = REG_19_CTRL_INIT;
        ctrl_reg[20] = REG_20_CTRL_INIT;
        ctrl_reg[21] = REG_21_CTRL_INIT;
        ctrl_reg[22] = REG_22_CTRL_INIT;
        ctrl_reg[23] = REG_23_CTRL_INIT;
        ctrl_reg[24] = REG_24_CTRL_INIT;
        ctrl_reg[25] = REG_25_CTRL_INIT;
        ctrl_reg[26] = REG_26_CTRL_INIT;
        ctrl_reg[27] = REG_27_CTRL_INIT;
        ctrl_reg[28] = REG_28_CTRL_INIT;
        ctrl_reg[29] = REG_29_CTRL_INIT;
        ctrl_reg[30] = REG_30_CTRL_INIT;
        ctrl_reg[31] = REG_31_CTRL_INIT;
    end
    
    reg [NUM_CTRL-1:0] reg_ctrl_update_ff = {NUM_CTRL{1'b0}};
    integer i;
    always @ (posedge S_AXI_ACLK) begin
        if ( S_AXI_ARESETN == 1'b0 ) begin
            ctrl_reg[0]  = REG_0_CTRL_INIT;
            ctrl_reg[1]  = REG_1_CTRL_INIT;
            ctrl_reg[2]  = REG_2_CTRL_INIT;
            ctrl_reg[3]  = REG_3_CTRL_INIT;
            ctrl_reg[4]  = REG_4_CTRL_INIT;
            ctrl_reg[5]  = REG_5_CTRL_INIT;
            ctrl_reg[6]  = REG_6_CTRL_INIT;
            ctrl_reg[7]  = REG_7_CTRL_INIT;
            ctrl_reg[8]  = REG_8_CTRL_INIT;
            ctrl_reg[9]  = REG_9_CTRL_INIT;
            ctrl_reg[10] = REG_10_CTRL_INIT;
            ctrl_reg[11] = REG_11_CTRL_INIT;
            ctrl_reg[12] = REG_12_CTRL_INIT;
            ctrl_reg[13] = REG_13_CTRL_INIT;
            ctrl_reg[14] = REG_14_CTRL_INIT;
            ctrl_reg[15] = REG_15_CTRL_INIT;
            ctrl_reg[16] = REG_16_CTRL_INIT;
            ctrl_reg[17] = REG_17_CTRL_INIT;
            ctrl_reg[18] = REG_18_CTRL_INIT;
            ctrl_reg[19] = REG_19_CTRL_INIT;
            ctrl_reg[20] = REG_20_CTRL_INIT;
            ctrl_reg[21] = REG_21_CTRL_INIT;
            ctrl_reg[22] = REG_22_CTRL_INIT;
            ctrl_reg[23] = REG_23_CTRL_INIT;
            ctrl_reg[24] = REG_24_CTRL_INIT;
            ctrl_reg[25] = REG_25_CTRL_INIT;
            ctrl_reg[26] = REG_26_CTRL_INIT;
            ctrl_reg[27] = REG_27_CTRL_INIT;
            ctrl_reg[28] = REG_28_CTRL_INIT;
            ctrl_reg[29] = REG_29_CTRL_INIT;
            ctrl_reg[30] = REG_30_CTRL_INIT;
            ctrl_reg[31] = REG_31_CTRL_INIT;
            reg_ctrl_update_ff <= {NUM_CTRL{1'b0}};
        end
        else begin
            for (i = 0; i < NUM_CTRL; i = i + 1) begin
                if ((slv_reg_wren) && ( i == axi_awaddr[ADDR_LSB+OPT_MEM_ADDR_BITS:ADDR_LSB] )) begin
                    for ( byte_index = 0; byte_index <= (C_S_AXI_DATA_WIDTH/8)-1; byte_index = byte_index+1 ) begin
                        if ( S_AXI_WSTRB[byte_index] == 1 ) begin
                            ctrl_reg[i][(byte_index*8) +: 8] <= S_AXI_WDATA[(byte_index*8) +: 8];
                        end
                    end
                    reg_ctrl_update_ff[i] <= 1'b1;
                end 
                else begin
                    if ( i == REG_CTRL ) begin // auto-reset of reset bit after 1 cycle
                        ctrl_reg[i] <= ctrl_reg[i] & (~(1<<REG_CTRL_RESET));
                    end
                    reg_ctrl_update_ff[i] <= 1'b0;
                end
            end
        end
    end
    assign reg_ctrl_update = reg_ctrl_update_ff;
    
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
    assign reg_0_ctrl  = ctrl_reg[0];
    assign reg_1_ctrl  = ctrl_reg[1];
    assign reg_2_ctrl  = ctrl_reg[2];
    assign reg_3_ctrl  = ctrl_reg[3];
    assign reg_4_ctrl  = ctrl_reg[4];
    assign reg_5_ctrl  = ctrl_reg[5];
    assign reg_6_ctrl  = ctrl_reg[6];
    assign reg_7_ctrl  = ctrl_reg[7];
    assign reg_8_ctrl  = ctrl_reg[8];
    assign reg_9_ctrl  = ctrl_reg[9];
    assign reg_10_ctrl = ctrl_reg[10];
    assign reg_11_ctrl = ctrl_reg[11];
    assign reg_12_ctrl = ctrl_reg[12];
    assign reg_13_ctrl = ctrl_reg[13];
    assign reg_14_ctrl = ctrl_reg[14];
    assign reg_15_ctrl = ctrl_reg[15];
    assign reg_16_ctrl = ctrl_reg[16];
    assign reg_17_ctrl = ctrl_reg[17];
    assign reg_18_ctrl = ctrl_reg[18];
    assign reg_19_ctrl = ctrl_reg[19];
    assign reg_20_ctrl = ctrl_reg[20];
    assign reg_21_ctrl = ctrl_reg[21];
    assign reg_22_ctrl = ctrl_reg[22];
    assign reg_23_ctrl = ctrl_reg[23];
    assign reg_24_ctrl = ctrl_reg[24];
    assign reg_25_ctrl = ctrl_reg[25];
    assign reg_26_ctrl = ctrl_reg[26];
    assign reg_27_ctrl = ctrl_reg[27];
    assign reg_28_ctrl = ctrl_reg[28];
    assign reg_29_ctrl = ctrl_reg[29];
    assign reg_30_ctrl = ctrl_reg[30];
    assign reg_31_ctrl = ctrl_reg[31];
    assign status_reg[32] = reg_32_sts;
    assign status_reg[33] = reg_33_sts;
    assign status_reg[34] = reg_34_sts;
    assign status_reg[35] = reg_35_sts;
    assign status_reg[36] = reg_36_sts;
    assign status_reg[37] = reg_37_sts;
    assign status_reg[38] = reg_38_sts;
    assign status_reg[39] = reg_39_sts;
    assign status_reg[40] = reg_40_sts;
    assign status_reg[41] = reg_41_sts;
    assign status_reg[42] = reg_42_sts;
    assign status_reg[43] = reg_43_sts;
    assign status_reg[44] = reg_44_sts;
    assign status_reg[45] = reg_45_sts;
    assign status_reg[46] = reg_46_sts;
    assign status_reg[47] = reg_47_sts;
    assign status_reg[48] = reg_48_sts;
    assign status_reg[49] = reg_49_sts;
    assign status_reg[50] = reg_50_sts;
    assign status_reg[51] = reg_51_sts;
    assign status_reg[42] = reg_52_sts;
    assign status_reg[53] = reg_53_sts;
    assign status_reg[54] = reg_54_sts;
    assign status_reg[55] = reg_55_sts;
    assign status_reg[56] = reg_56_sts;
    assign status_reg[57] = reg_57_sts;
    assign status_reg[58] = reg_58_sts;
    assign status_reg[59] = reg_59_sts;
    assign status_reg[60] = reg_60_sts;
    assign status_reg[61] = reg_61_sts;
    assign status_reg[62] = reg_62_sts;
    assign status_reg[63] = reg_63_sts;

    // User logic ends
    
endmodule
