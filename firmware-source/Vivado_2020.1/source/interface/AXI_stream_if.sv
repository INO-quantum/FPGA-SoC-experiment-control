`timescale 1 ns / 1 ps

//////////////////////////////////////////////////////////////////////////////////
// AXI stream interface
// created 2/9/2023 by Andi
// last change 2/9/2023 by Andi
// notes: 
// - TKEEP is 1 for used bytes in TDATA. see PG085.
// - TLAST is 1 for last TDATA of packet.
// - TSTRB, TID, TDEST and TUSER are not used.
//////////////////////////////////////////////////////////////////////////////////

interface AXI_stream # (
    parameter DATA_WIDTH = 32
    //parameter ID_WIDTH   = 0,
    //parameter DEST_WIDTH = 0,
    //parameter USER_WIDYH = 0
)(
    input logic                     ACLK,
    input logic                     ARESETN
);
    logic [DATA_WIDTH-1 : 0]        TDATA;
    //logic [(DATA_WIDTH/8)-1 : 0]    TSTRB;
    logic [(DATA_WIDTH/8)-1 : 0]    TKEEP;
    logic                           TLAST;
    logic                           TVALID;
    logic                           TREADY;
    //logic [ID_WIDTH-1 : 0]          TID;
    //logic [DEST_WIDTH-1 : 0]        TDEST;
    //logic [USER_WIDTH-1 : 0]        TUSER;

modport source (
    input   ACLK,
    input   ARESETN,
    output  TDATA,
    //output  TSTRB,
    output  TKEEP,
    output  TLAST,
    output  TVALID,
    input   TREADY
    //output  TID,
    //output  TDEST,
    //output  TUSER
);

modport sink (
    input   ACLK,
    input   ARESETN,
    input   TDATA,
    //input   TSTRB,
    input   TKEEP,
    input   TLAST,
    input   TVALID,
    output  TREADY
    //input   TID,
    //input   TDEST,
    //input   TUSER
);

endinterface
