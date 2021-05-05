`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// sync_pulse module
// created 11/03/2021 by Andi
//////////////////////////////////////////////////////////////////////////////////

module sync_pulse # (
    parameter integer PULSE_LENGTH = 2
)(
    input wire clock,
    input wire reset_n,
    
    input wire start,
    output wire sync_out
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
    
    // start edge detector
    reg start_edge_ff;
    always @ ( posedge clock ) begin
        start_edge_ff <= start;
    end
    wire [1:0] start_edge = {start_edge_ff,start};
    
    // pulse generation @ clock_bus
    localparam integer COUNT_BITS = clogb2(PULSE_LENGTH);
    reg [COUNT_BITS-1 : 0] count = 0;
    reg sync_out_n_ff;
    wire as_done;
    always @ ( posedge clock ) begin
        if ( reset_n == 1'b0 ) begin
            count <= 0;
            sync_out_n_ff <= 1'b1;
        end
        else if ( count > 0 ) begin
            count <= count - 1;
            sync_out_n_ff <= 1'b0;
        end
        else if ( start_edge == 2'b01 ) begin // start at positive edge
            count <= PULSE_LENGTH - 1;
            sync_out_n_ff <= 1'b0;
        end
        else begin
            count <= 0;
            sync_out_n_ff <= 1'b1;
        end
    end
    assign sync_out = sync_out_n_ff;
    
endmodule
