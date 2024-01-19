`timescale 1 ns / 1 ps

//////////////////////////////////////////////////////////////////////////////////
// AXI LITE interface
// created 2/9/2023 by Andi
// last change 2/9/2023 by Andi
// see UG1037 for signals
//////////////////////////////////////////////////////////////////////////////////

interface AXI_LITE # (
    parameter ADDR_WIDTH = 10,
    parameter DATA_WIDTH = 32                   // must be 32 bits
)(
    input logic                     ACLK,
    input logic                     ARESETN
);
    // write address channel
    logic [ADDR_WIDTH-1 : 0]        AWADDR;
    logic [2 : 0]                   AWPROT;     // protection bits ignored
    logic                           AWVALID;
    logic                           AWREADY;
    // write data channel
    logic [DATA_WIDTH-1 : 0]        WDATA;
    logic [(DATA_WIDTH/8)-1 : 0]    WSTRB;
    logic                           WVALID;
    logic                           WREADY;
    // write responds channel
    logic [1 : 0]                   BRESP;
    logic                           BVALID;
    logic                           BREADY;
    // read address channel
    logic [ADDR_WIDTH-1 : 0]        ARADDR;
    logic [2 : 0]                   ARPROT;     // protection bits ignored
    logic                           ARVALID;
    logic                           ARREADY;
    // read data channel
    logic [DATA_WIDTH-1 : 0]        RDATA;
    logic [1 : 0]                   RRESP;
    logic                           RVALID;
    logic                           RREADY;

modport source (
    input   ACLK,
    input   ARESETN,
    // write address channel
    output  AWADDR,
    output  AWPROT,
    output  AWVALID,
    input   AWREADY,
    // write data channel
    output  WDATA,
    output  WSTRB,
    output  WVALID,
    input   WREADY,
    // write responds channel
    input   BRESP,
    input   BVALID,
    output  BREADY,
    // read address channel
    output  ARADDR,
    output  ARPROT,
    output  ARVALID,
    input   ARREADY,
    // read data channel
    input   RDATA,
    input   RRESP,
    input   RVALID,
    output  RREADY
);

modport sink (
    input   ACLK,
    input   ARESETN,
    // write address channel
    input   AWADDR,
    input   AWPROT,
    input   AWVALID,
    output  AWREADY,
    // write data channel
    input   WDATA,
    input   WSTRB,
    input   WVALID,
    output  WREADY,
    // write responds channel
    output  BRESP,
    output  BVALID,
    input   BREADY,
    // read address channel
    input   ARADDR,
    input   ARPROT,
    input   ARVALID,
    output  ARREADY,
    // read data channel
    output  RDATA,
    output  RRESP,
    output  RVALID,
    input   RREADY
);

endinterface
