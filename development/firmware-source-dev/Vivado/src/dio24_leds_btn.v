`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////
// LEDs and button I/O module, created 23/01/2020 by Andi
// implements button debouncing and LEDs dimming/blinking
// control bits for blinking:
// leds_ctrl_0: 0 = blink*, 1 = constant
// leds_ctrl_1: 0 = slow/dim, 1 = fast/bright
// leds_ctrl_2: 0 = normal signal, 1 = inverted signal**
// *blinking is done with bright level
// **when LED contstant on, input signal is inverted,
//   when LED is blinking, input signal is not inverted but blinks out of phase
//   with LED_BLINK_ON ratio inverted, i.e. with LED_BLINK_ON = 2 is 3:1 ON/OFF
// note:
// - when control bits change the blink counter is not reset, 
//   so it might look first that nothing has changed.
//   e.g. from OFF to blink it might start with a dark phase.
// TODO: LED_BRIGHT_HIGH = 0 gives errors in lines 160,163,171,174 because of negative indices.
// last change 4/11/2024 by Andi
//////////////////////////////////////////////////////////////////////////////////

module dio24_leds_btn # (
  parameter NUM_BUTTONS = 2,            // number of buttons
  parameter NUM_LEDS = 2,               // number of LEDs
  parameter BTN_SYNC = 2,               // button clock sychronization. 0 = none.  
  parameter BTN_DEB_BITS = 10,          // button debounce counter bits
  parameter LED_BLINK_ON = 3,           // bits used for blinking leds ON-time: 1=50%, 2=25%, 3=12.5%, 4=6.25%
  // bits used for blinking leds
  parameter LED_SLOW = 26,              // blink slow
  parameter LED_FAST = 24,              // blink fast (1 <= LED_FAST < LED_SLOW)
  // bits used for PWM dimming of leds. 0 = no dimming.
  parameter LED_DIM_LOW = 8,            // dim level low (< LED_SLOW)
  parameter LED_DIM_HIGH = 6,           // dim level high (< LED_SLOW)
  parameter LED_BRIGHT_LOW = 1,         // bright level low (< LED_SLOW)
  parameter LED_BRIGHT_HIGH = 1         // bright level high (1 <= LED_BRIGHT_HIGH < LED_SLOW)
)(
    // clock and reset
    input clk,
    input reset_n,
    // buttons
    input [NUM_BUTTONS-1:0] btn_in,     // button input
    output [NUM_BUTTONS-1:0] btn_status, // button status after debouncing
    // LEDs
    input [NUM_LEDS-1:0] leds_in,        // LEDs ON/OFF state
    output [NUM_LEDS-1:0] leds_out,      // dimmed/blinking signal to LEDs
    input [NUM_LEDS-1:0] leds_bright,    // 0 = dim, 1 = bright
    input [NUM_LEDS-1:0] leds_blink,     // 0 = constant, 1 = blink
    input [NUM_LEDS-1:0] leds_high,      // 0 = normal, 1 = faster/brighter
    input [NUM_LEDS-1:0] leds_inv        // 0 = normal signal, 1 = inverted signal
  );
  
// blink counter used also for dimming
reg [LED_SLOW - 1 : 0] blink = 0;
always @ (posedge clk) begin
  blink <= blink + 1;
end    

// buttons
// if BTN_SYNC > 0 we synchronize button with clock to avoid metastability.
// when button pressed and btn_cnt = 0 then btn_pulse is pulsing one cycle
// and btn_cnt is starting to count down from BTN_DEBOUNCE_COUNT
// when button is pressed and btn_cnt > 0 then nothing happens until btn_cnt = 0 again.
// btn_sts is set while btn_cnt > 0
reg [NUM_BUTTONS - 1 : 0] btn_pulse;
generate
for (genvar i = 0; i < NUM_BUTTONS; i = i + 1) 
begin : GEN_BTN
  
  wire btn_sig;
  if ( BTN_SYNC > 0 ) begin
    reg [BTN_SYNC : 0] btn_sync;
    always @ (posedge clk) begin
      if ( reset_n == 1'b0 ) btn_sync <= 0;
      else btn_sync <= {btn_sync[BTN_SYNC-1:0],btn_in[i]};
    end
    assign btn_sig = btn_sync[BTN_SYNC];
  end
  else begin
    assign btn_sig = btn_in[i];
  end

  reg [BTN_DEB_BITS - 1 : 0] btn_cnt;
  reg btn_sts;
  always @ (posedge clk) begin
    if ( reset_n == 1'b0 ) begin
      btn_pulse[i] <= 1'b0;
      btn_cnt <= 0;
      btn_sts <= 1'b0;
    end
    else if ( btn_sig == 1'b1 ) begin // button pressed
      btn_cnt <= {BTN_DEB_BITS{1'b1}};
      btn_sts <= 1'b1;
      if ( btn_cnt == 0 ) begin // button pressed and cnt = 0
        btn_pulse[i] <= 1'b1;
      end
      else begin
        btn_pulse[i] <= 1'b0;
      end
    end
    else begin // button not pressed
      btn_pulse[i] <= 1'b0;
      if ( btn_cnt > 0 ) begin
        btn_cnt <= btn_cnt - 1;
        btn_sts <= 1'b1;
      end
      else begin
        btn_cnt <= 0;
        btn_sts <= 1'b0;
      end
    end
  end
  assign btn_status[i] = btn_sts;
end
endgenerate

// LEDs input latch
reg [NUM_LEDS - 1 : 0] leds_ff;
always @ (posedge clk) begin
    leds_ff <= leds_in;
end    

// LEDs blinking and dimming depending on control bits
generate
for (genvar i = 0; i < NUM_LEDS; i = i + 1) 
begin : GEN_LED

    reg led_out_ff = 1'b0;
    always @ ( posedge clk ) begin
        case ({leds_bright[i],leds_blink[i],leds_high[i],leds_inv[i]})
            4'b0000: // DIM LOW LEVEL
                if (LED_DIM_LOW > 0) led_out_ff <= ( blink[LED_DIM_LOW-1 : 0] == 0 ) ? leds_ff[i] : 1'b0; 
                else led_out_ff <= leds_ff[i];
            4'b0001: // DIM LOW LEVEL INVERTED
                if (LED_DIM_LOW  > 0) led_out_ff <= ( blink[LED_DIM_LOW-1 : 0] == 0 ) ? ~leds_ff[i] : 1'b1;
                else led_out_ff <= ~leds_ff[i];
            4'b0010: // DIM HIGH LEVEL
                if (LED_DIM_HIGH > 0) led_out_ff <= ( blink[LED_DIM_HIGH-1 : 0] == 0 ) ? leds_ff[i] : 1'b0; 
                else led_out_ff <= leds_ff[i];
            4'b0011: // DIM HIGH LEVEL INVERTED
                if (LED_DIM_HIGH > 0) led_out_ff <= ( blink[LED_DIM_HIGH-1 : 0] == 0 ) ? ~leds_ff[i] : 1'b1;
                else led_out_ff <= ~leds_ff[i];
            4'b0100: // DIM BLINK SLOW/LOW LEVEL
                if (LED_DIM_LOW > 0) led_out_ff <= (( blink[(LED_SLOW-1)-:LED_BLINK_ON] == 0 ) && ( blink[LED_DIM_LOW-1 : 0] == 0 )) ? leds_ff[i] : 1'b0;
                else led_out_ff <= ( blink[(LED_SLOW-1)-:LED_BLINK_ON] == 0 ) ? leds_ff[i] : 1'b0;
            4'b0101: // DIM BLINK SLOW/LOW LEVEL INVERTED
                if (LED_DIM_LOW > 0) led_out_ff <= (( blink[(LED_SLOW-1)-:LED_BLINK_ON] != 0 ) && ( blink[LED_DIM_LOW-1 : 0] == 0 )) ? leds_ff[i] : 1'b0;
                else led_out_ff <= ( blink[(LED_SLOW-1)-:LED_BLINK_ON] != 0 ) ? leds_ff[i] : 1'b0;
            4'b0110: // DIM BLINK FAST/HIGH LEVEL
                if (LED_DIM_HIGH > 0) led_out_ff <= (( blink[(LED_FAST-1)-:LED_BLINK_ON] == 0 ) && ( blink[LED_DIM_HIGH-1 : 0] == 0 )) ? leds_ff[i] : 1'b0;
                else led_out_ff <= ( blink[(LED_FAST-1)-:LED_BLINK_ON] == 0 ) ? leds_ff[i] : 1'b0;
            4'b0111: // DIM BLINK FAST/HIG LEVEL INVERTED
                if (LED_DIM_HIGH > 0) led_out_ff <= (( blink[(LED_FAST-1)-:LED_BLINK_ON] != 0 ) && ( blink[LED_DIM_HIGH-1 : 0] == 0 )) ? leds_ff[i] : 1'b0;
                else led_out_ff <= ( blink[(LED_FAST-1)-:LED_BLINK_ON] != 0 ) ? leds_ff[i] : 1'b0;
            4'b1000: // BRIGHT LOW LEVEL
                if (LED_BRIGHT_LOW > 0) led_out_ff <= ( blink[LED_BRIGHT_LOW-1 : 0] == 0 ) ? leds_ff[i] : 1'b0; 
                else led_out_ff <= leds_ff[i];
            4'b1001: // BRIGHT LOW LEVEL INVERTED
                if (LED_BRIGHT_LOW) led_out_ff <= ( blink[LED_BRIGHT_LOW-1 : 0] == 0 ) ? ~leds_ff[i] : 1'b1;
                else led_out_ff <= ~leds_ff[i];
            4'b1010: // BRIGHT HIGH LEVEL
                if (LED_BRIGHT_HIGH > 0) led_out_ff <= ( blink[LED_BRIGHT_HIGH-1 : 0] == 0 ) ? leds_ff[i] : 1'b0;
                else led_out_ff <= leds_ff[i];
            4'b1011: // BRIGHT HIGH LEVEL INVERTED
                if (LED_BRIGHT_HIGH > 0) led_out_ff <= ( blink[LED_BRIGHT_HIGH-1 : 0] == 0 ) ? ~leds_ff[i] : 1'b1;
                else led_out_ff <= ~leds_ff[i];
            4'b1100: // BRIGHT BLINK SLOW/LOW LEVEL
                if (LED_BRIGHT_LOW > 0) led_out_ff <= (( blink[(LED_SLOW-1)-:LED_BLINK_ON] == 0 ) && ( blink[LED_BRIGHT_LOW-1 : 0] == 0 )) ? leds_ff[i] : 1'b0;
                else led_out_ff <= ( blink[(LED_SLOW-1)-:LED_BLINK_ON] == 0 ) ? leds_ff[i] : 1'b0;
            4'b1101: // BRIGHT BLINK SLOW/LOW LEVEL INVERTED
                led_out_ff <= (( blink[(LED_SLOW-1)-:LED_BLINK_ON] != 0 ) && ( blink[LED_BRIGHT_LOW-1 : 0] == 0 )) ? leds_ff[i] : 1'b0;
            4'b1110: // BRIGHT BLINK FAST/HIGH LEVEL
                if (LED_BRIGHT_HIGH > 0) led_out_ff <= (( blink[(LED_FAST-1)-:LED_BLINK_ON] == 0 ) && ( blink[LED_BRIGHT_HIGH-1 : 0] == 0 )) ? leds_ff[i] : 1'b0;
                else led_out_ff <= ( blink[(LED_FAST-1)-:LED_BLINK_ON] == 0 ) ? leds_ff[i] : 1'b0;
            4'b1111: // BRIGHT BLINK FAST/HIGH LEVEL INVERTED
                if (LED_BRIGHT_HIGH > 0) led_out_ff <= (( blink[(LED_FAST-1)-:LED_BLINK_ON] != 0 ) && ( blink[LED_BRIGHT_HIGH-1 : 0] == 0 )) ? leds_ff[i] : 1'b0;
                else led_out_ff <= ( blink[(LED_FAST-1)-:LED_BLINK_ON] != 0 ) ? leds_ff[i] : 1'b0;
        endcase
    end
    assign leds_out[i] = led_out_ff;
  
end
endgenerate 

endmodule
