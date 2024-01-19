`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// performs reset of dio24 module with fast and slow clocks
// and generates the appropriate reset signal for the FIFOs which is critical.
// reset condition is any of these inputs, they are all sync to clock_fast:
// - reset_n = hardware reset, active low
// - reset_sw = software reset, active high
// - PLL_locked = reset is active while this is 0
// reset is prolonged to have at least FIFO_RESET_CYCLES + 2*FIFO_RESET_DELAY slow cycles in total
// - reset_n_fast/slow outputs are active low and synchronized with fast/slow clocks
// - reset_FIFO is active high and synchronized to slow clock (for FIFO does not matter).
//   it is delayed FIFO_RESET_CYLES slow clock cycles after reset_n_slow becomes low and
//   it is reset FIFO_RESET_CYLES slow clock cycles before reset_n_slow becomes high.
// parameters:
// - FIFO_RESET_DELAY = slow cycles before/after FIFO is reset. must be >= 4
//      this ensures that WREN/RDEN signals into the FIFO are low before after reset of FIFO
//      the actual FIFO requirement would be >=4 cycles before and >=2 after,
//      but for simplicity we keep this symmetric and stick with larger requirement.
// - FIFO_RESET_CYCLES = minimum slow cycles the FIFO is held in reset. must be >=5.
// - SYNC = number of synchronization registers to go from fast to slow clock. must be 2-4.
// notes:
// - the total minimum reset slow cycles for anything else than the FIFO is:
//   FIFO_RESET_CYCLES + 2*FIFO_RESET_DELAY (-1 if FIFO_RESET_CYCLES is odd).
// - the FIFOs need stable fast and slow clocks for proper reset,
//   therefore, reset_FIFO is NOT active until PLL_locked signal is high.
//   if the PLL_locked signal and clocks become instable during FIFO reset,
//   the FIFOs might go into an invalid state and need to be power-cycled.
//   the module does not detect this situation.
// - single-cycle pulses on any of the reset inputs will start a full reset!
//   so ensure this does not happen.
// - the module uses the cross_IO module for synchronizing fast and slow resets.   
// - test benches for dio24_reset: cross_IO_tb.v and dio24_FIFO_tb.v
// created 27/3/2020 by Andi
// last change 7/4/2020 by Andi
//////////////////////////////////////////////////////////////////////////////////

module dio24_reset # (
        parameter integer FIFO_RESET_DELAY = 10,    // >= 4
        parameter integer FIFO_RESET_CYCLES = 10,   // >= 5
        parameter integer SYNC = 3                  // 2-4
    )
    (
        // clock and reset sources: hardware, software, PLL_locked
        input wire clock_fast,
        input wire clock_slow,
        input wire reset_n,         // active low
        input wire reset_sw,
        input wire PLL_locked,
        // reset outputs
        output wire reset_n_fast,  // active low
        output wire reset_n_slow, // active low
        output wire reset_FIFO
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
    
    localparam integer RESET_CYCLES = (FIFO_RESET_CYCLES/2) + FIFO_RESET_DELAY;
    localparam integer NUM_RESET = clogb2(RESET_CYCLES);
    reg [NUM_RESET - 1 : 0] reset_count = 0;

    // fast reset set when reset condition detected (one cycle after), 
    // reset when ok condition sent from fast -> slow and finished
    localparam integer STATE_OK = 2'b11; // see actual_state
    wire xover_in_ready;
    reg xover_in_valid = 1'b0;
    reg [1:0] last_state = STATE_OK;   // last sent status
    reg reset_fast = 1'b0;
    always @ ( posedge clock_fast ) begin
        if ( xover_in_valid ) begin
            reset_fast <= 1'b1;
        end
        else if ( (last_state == STATE_OK) && (xover_in_ready) ) begin
            reset_fast <= 1'b0;
        end
        else begin
            reset_fast <= reset_fast;
        end
    end
    assign reset_n_fast = ~reset_fast;  // = xover_ready

    // detect reset condition
    // send from fast -> slow when condition changes
    wire [1:0] actual_state = {reset_n & (~reset_sw),PLL_locked};
    always @ ( posedge clock_fast ) begin
        if ( xover_in_ready & (~xover_in_valid)) begin // update state only when ready and >1 cycle after valid
            if ( actual_state != STATE_OK ) begin // reset is active
                if ( last_state != actual_state ) begin  // state changed
                    xover_in_valid <= 1'b1;
                    last_state <= actual_state;
                end
                else begin  // no change
                    xover_in_valid <= 1'b0;
                    last_state <= last_state;
                end
            end
            else if ( last_state != STATE_OK ) begin // status ok not sent
                xover_in_valid <= 1'b1;
                last_state <= STATE_OK;
            end
            else begin // no reset
                xover_in_valid <= 1'b0;
                last_state <= last_state;
            end
        end
        else begin // wait until ready, then check state
            xover_in_valid <= 1'b0;
            last_state <= last_state;
        end
    end

    // sync reset and PLL_locked to slow clock
    wire [1:0] xover_out_data;
    wire xover_out_valid;
    reg xover_out_ready = 1'b0;
    cross_IO # (
        .DATA_WIDTH(2),
        .SYNC(SYNC),
        .OUTPUT_READER("FALSE")
    )
    xover
    (
        .in_clock(clock_fast),
        .in_data(last_state),
        .in_valid(xover_in_valid),
        .in_ready(xover_in_ready),
        .out_clock(clock_slow),
        .out_data(xover_out_data),
        .out_valid(xover_out_valid),
        .out_ready(xover_out_ready)
    );

    // memorize state and control xover_out_ready bit
    reg PLL_locked_slow;
    reg state_ok_slow;
    reg reset_dir = 1'b0;
    always @ ( posedge clock_slow ) begin
        if ( xover_out_valid ) begin    // valid data (remains 1 until xover_ready = 1)
            PLL_locked_slow <= xover_out_data[0];
            if ( xover_out_data == STATE_OK ) begin // reset gone: wait until counter finished
                state_ok_slow <= 1'b1;
                xover_out_ready <= ( ( reset_count == 2 ) && ( reset_dir == 1'b0 ) );
            end
            else begin
                state_ok_slow <= 1'b0;
                xover_out_ready <= 1'b1; // reset active: get next status update
            end
        end
        else begin
            PLL_locked_slow <= PLL_locked_slow;
            state_ok_slow <= state_ok_slow;
            xover_out_ready <= 1'b0; // wait for valid data
        end
    end

    // set counting direction
    // this starts counting up when set to 1
    // reverts direction when maximum counter reached
    always @ ( posedge clock_slow ) begin
        if ( (reset_count == 0) && xover_out_valid ) begin
            reset_dir <= 1'b1;  // start counting
        end        
        else if ( reset_count == RESET_CYCLES ) begin
            reset_dir <= 1'b0;  // reverse direction
        end
        else begin
            reset_dir <= reset_dir;
        end
    end

    // counter running at slow clock
    // while reset_dir is 1 we count up until FIFO_RESET_DELAY reached
    // there we wait until PLL_locked_slow is 1 and count up until RESET_CYCLES is reached
    // there we wait until reset is finished and count down to 0
    always @ ( posedge clock_slow ) begin
        if ( reset_dir ) begin
            if ( reset_count <  FIFO_RESET_DELAY ) reset_count <= reset_count + 1;
            else if ( PLL_locked_slow ) begin // PLL_locked
                if ( reset_count <  RESET_CYCLES ) reset_count <= reset_count + 1;
                else reset_count <= reset_count;
            end
            else begin
                reset_count <= reset_count;
            end
        end
        else begin
            if ( state_ok_slow ) begin
                if ( reset_count > 0) reset_count <= reset_count - 1;
                else reset_count <= 0;
            end
            else begin
                reset_count <= reset_count;
            end
        end
    end
    
    // reset outputs sync'ed to slow clock
    reg reset_n_slow_ff = 1'b1;
    reg reset_FIFO_ff = 1'b0;
    always @ ( posedge clock_slow ) begin
        reset_n_slow_ff <= ( reset_count == 0 );
        reset_FIFO_ff <= ( reset_count > FIFO_RESET_DELAY );
    end
    assign reset_n_slow = reset_n_slow_ff;
    assign reset_FIFO = reset_FIFO_ff;

endmodule
