#this locks the location of the PL clock global clock buffer to the lower half
#this ensures that the clock pins U18 or N18 in clock region X0Y0, close to the MMCME2_ADV_X0Y0 can be used toghther with BUFGCTRL of ClockMUX
#otherwise get errors about "sub-optimal placement for and MMCM-BUFG component pair" (not always)
#to find the proper cell name: Open Syntesized design and Tools - Reports - Report Clock Networks
#in a working design with Cora-Z7-10 it uses BUFGCTRL_X0Y0
#When I have got error was placing it on BUFGCTRL_X0Y17 in upper half instead
#set_property LOC BUFGCTRL_X0Y16 [get_cells design_1_i/processing_system7_0/inst/buffer_fclk_clk_0.FCLK_CLK_0_BUFG]
#set_property LOC BUFGCTRL_X0Y15 [get_cells design_1_i/ClockMUX_0/inst/BUFGCTRL_inst]
#set_property LOC BUFGCTRL_X0Y14 [get_cells design_1_i/clk_wiz_0/inst/clkout1_buf]

#set_clock_groups -physically_exclusive -group [get_clocks -include_generated_clocks clkfbout_design_1_clk_wiz_1_0] -group [get_clocks -include_generated_clocks clkfbout_design_1_clk_wiz_1_0_2]
#set_clock_groups -physically_exclusive -group [get_clocks -include_generated_clocks clk_8_design_1_clk_wiz_1_0] -group [get_clocks -include_generated_clocks clk_8_design_1_clk_wiz_1_0_2]

#set_clock_groups -logically_exclusive -group [get_clocks -include_generated_clocks clk_wiz_1_clk_out1] -group [get_clocks -include_generated_clocks clk_wiz_0_clk_out1]

#(A)
#clk_in1 - (10MHz, pin) clk_wiz_0 (100MHz, no buffer) - ClockMUX - (100MHz, BUFG) clk_wiz_1 (16MHz, BUFG)
#timing fails with WNS=-9.1 TNS=-572.9 in 83 endpoints
#set_clock_groups -physically_exclusive -group [get_clocks -include_generated_clocks clkfbout_design_1_clk_wiz_1_0] -group [get_clocks -include_generated_clocks clkfbout_design_1_clk_wiz_1_0_1]
#set_clock_groups -physically_exclusive -group [get_clocks -include_generated_clocks clk_out1_design_1_clk_wiz_1_0] -group [get_clocks -include_generated_clocks clk_out1_design_1_clk_wiz_1_0_1]
#set_clock_groups -logically_exclusive -group [get_clocks -include_generated_clocks {clk_out1_design_1_clk_wiz_1_0 clkfbout_design_1_clk_wiz_1_0}] -group [get_clocks -include_generated_clocks {clk_out1_design_1_clk_wiz_1_0_1 clkfbout_design_1_clk_wiz_1_0_1}]
#create_generated_clock -name clk_fpga_0_Gen -source [get_pins design_1_i/ClockMUX_0/inst/BUFGCTRL_inst/I0] -divide_by 1 -add -master_clock clk_fpga_0 [get_pins design_1_i/ClockMUX_0/inst/BUFGCTRL_inst/O]
#create_generated_clock -name clk_wiz_0_clk_out1_Gen -source [get_pins design_1_i/ClockMUX_0/inst/BUFGCTRL_inst/I1] -divide_by 1 -add -master_clock clk_wiz_0_clk_out1 [get_pins design_1_i/ClockMUX_0/inst/BUFGCTRL_inst/O]
#set_clock_groups -logically_exclusive -group [get_clocks -include_generated_clocks clk_fpga_0_Gen] -group [get_clocks -include_generated_clocks clk_wiz_0_clk_out1_Gen]

#same as (A) but clk_wiz_1 removed and directly input into dio24 module with 100MHz (but need 8,16,32MHz)
#timing ok with WNS = 2.2, TNS = 0
#3 critical warnings that clk_wiz_0_clk_out1_Gen might not be needed since has only disabled paths?
#create_generated_clock -name clk_fpga_0_Gen -source [get_pins design_1_i/ClockMUX_0/inst/BUFGCTRL_inst/I0] -divide_by 1 -add -master_clock clk_fpga_0 [get_pins design_1_i/ClockMUX_0/inst/BUFGCTRL_inst/O]
#create_generated_clock -name clk_wiz_0_clk_out1_Gen -source [get_pins design_1_i/ClockMUX_0/inst/BUFGCTRL_inst/I1] -divide_by 1 -add -master_clock clk_wiz_0_clk_out1 [get_pins design_1_i/ClockMUX_0/inst/BUFGCTRL_inst/O]
#set_clock_groups -logically_exclusive -group [get_clocks -include_generated_clocks clk_fpga_0_Gen] -group [get_clocks -include_generated_clocks clk_wiz_0_clk_out1_Gen]

#this should be a working config without external clock but one clocking wizard with 8MHz into dio24 module
#timing fails now on 75 endpoints with WNS = -5.5, TNS = -178.6 but yesterday it was working!
#2nd run fails on 58 endpoints with WNS = -1.8, TNS = -33.0, have just made a new wizard without input buffer


#create_clock -period 10.000 -name clk_in1_0 -waveform {0.000 5.000} [get_ports clk_in1_0]

#added by Andi on 27/3/2020 to disable timing checking for asynchroneous reset of dual clock FIFOs
#about reset see UG473, v1.14, p.9. the suggestion on the false path was here:
#forums.xilinx.com/t5/Timing-Analysis/Helping-to-Meet-Timing-on-the-Reset-of-a-FIFO-With-Two-Clocks/td-p/726019
#todo: do inside dio24_FIFO module
#set_false_path -to [get_pins {design_1_i/dio24_0/inst/TX_FIFO/GEN_FIFO[*].FIFO/genblk5_0.genblk5_0.fifo_36_bl.fifo_36_bl/RST}]
#set_false_path -to [get_pins {design_1_i/dio24_0/inst/RX_FIFO/GEN_FIFO[*].FIFO/genblk5_0.genblk5_0.fifo_36_bl.fifo_36_bl/RST}]
#set_false_path -to [get_pins {design_1_i/dio24_0/inst/TX_ctrl_FIFO/FIFO/genblk5_0.genblk5_0.fifo_18_bl_1.fifo_18_bl_1/RST}]
#set_false_path -to [get_pins {design_1_i/dio24_0/inst/RX_ctrl_FIFO/FIFO/genblk5_0.genblk5_0.fifo_18_bl_1.fifo_18_bl_1/RST}]

#set_false_path -from [get_pins design_1_i/dio24_0/inst/reset/reset_fast_reg/C] -to [get_pins {design_1_i/dio24_0/inst/reset/reset_slow_reg[0]/D}]
#set_false_path -from [get_pins {design_1_i/dio24_0/inst/reset/reset_count_reg[*]/C}] -to [get_pins {design_1_i/dio24_0/inst/reset/reset_n_fast_ff_reg[0]/D}]

##this is for clock_wizard 1 to be used as PLL/MMCM and clock multiplexer
set_clock_groups -physically_exclusive -group [get_clocks -include_generated_clocks clkfbout_design_1_clk_wiz_1_0] -group [get_clocks -include_generated_clocks clkfbout_design_1_clk_wiz_1_0_1]
set_clock_groups -physically_exclusive -group [get_clocks -include_generated_clocks clk_out_design_1_clk_wiz_1_0] -group [get_clocks -include_generated_clocks clk_out_design_1_clk_wiz_1_0_1]
set_clock_groups -physically_exclusive -group [get_clocks -include_generated_clocks clk_out_PS_design_1_clk_wiz_1_0] -group [get_clocks -include_generated_clocks clk_out_PS_design_1_clk_wiz_1_0_1]
##disable tests on asynchronous clocks (the 3rd line is the same as the other two)
##set_clock_groups -asynchronous -group {clk_fpga_0} -group {clk_out1_design_1_clk_wiz_0_1}
##set_clock_groups -asynchronous -group {clk_fpga_0} -group {clk_out1_design_1_clk_wiz_0_1_1}
set_clock_groups -asynchronous -group clk_fpga_0 -group [get_clocks -of_objects [get_pins design_1_i/clk_wiz_1/inst/mmcm_adv_inst/CLKOUT0]]
## same for clock_out_PS
##todo: do inside cross_IO module and use set_max_delay (set_bus_scew and set_false_delay) instead for CDC!
# auto-generated on 28/2/2021
set_clock_groups -asynchronous -group [get_clocks clk_out_PS_design_1_clk_wiz_1_0_1] -group [get_clocks clk_fpga_0]
set_clock_groups -asynchronous -group [get_clocks clk_out_design_1_clk_wiz_1_0_1] -group [get_clocks clk_out_PS_design_1_clk_wiz_1_0]
set_clock_groups -asynchronous -group [get_clocks clk_fpga_0] -group [get_clocks clk_out_PS_design_1_clk_wiz_1_0_1]
set_clock_groups -asynchronous -group [get_clocks clk_out_design_1_clk_wiz_1_0] -group [get_clocks clk_out_PS_design_1_clk_wiz_1_0_1]

##this is for ClockMUX input clocks from clock wizard 0 and clk_fpga_0 (system clock)
#set_clock_groups -physically_exclusive -group [get_clocks clk_fpga_0] -group [get_clocks -of_objects [get_pins design_1_i/clk_wiz_0/clk_out1]]
#set_clock_groups -asynchronous -group clk_fpga_0 -group [get_clocks -of_objects [get_pins design_1_i/clk_wiz_0/clk_out1]]
##set_property CLOCK_DEDICATED_ROUTE FALSE [get_nets design_1_i/clk_wiz_0/inst/clk_out1_design_1_clk_wiz_0_0]

#adjusted phase shift of virtual clock to -10ns to compensate for a big hold time violation when using IOB as output flip-flops.
#alternatively one could shift delays by +10ns, i.e. set min=0 and max=23 which has the same effect.
#here the phase with the real clock does not matter since we do not output. othwerwise, adjust its phase in MMCM directly!
#output delay parameters @ 8MHz: setup=5ns, hold=15ns, trc_min=5ns, trc_max=8ns. min=trc_min-hold=-10ns, max=trc_max+setup=13ns
#output delay parameters @32MHz: setup=3ns, hold= 7ns, trc_min=5ns, trc_max=8ns. min=trc_min-hold= -2ns, max=trc_max+setup=11ns
#output delay parameters @50MHz: setup=3ns, hold= 3ns, trc_min=3ns, trc_max=5ns. min=trc_min-hold= 0ns, max=trc_max+setup=8ns
#create_clock -period 125.000 -name VIRTUAL_clk_out1_design_1_clk_wiz_0_1 -waveform {115.000 177.500}
#create_clock -period 125.000 -name VIRTUAL_clk_out1_design_1_clk_wiz_0_1 -waveform {0.000 62.500}
##create_clock -period 20.000 -name VIRTUAL_clock_out -waveform {0.000 10.000}
##set_output_delay -clock [get_clocks VIRTUAL_clock_out] -min 0.000 [get_ports {bus_addr_0[*]}]
##set_output_delay -clock [get_clocks VIRTUAL_clock_out] -max 8.000 [get_ports {bus_addr_0[*]}]
##set_output_delay -clock [get_clocks VIRTUAL_clock_out] -min 0.000 [get_ports {bus_data_0[*]}]
##set_output_delay -clock [get_clocks VIRTUAL_clock_out] -max 8.000 [get_ports {bus_data_0[*]}]
##set_output_delay -clock [get_clocks VIRTUAL_clock_out] -min 0.000 [get_ports bus_enable_n_0]
##set_output_delay -clock [get_clocks VIRTUAL_clock_out] -max 8.000 [get_ports bus_enable_n_0]
##set_output_delay -clock [get_clocks VIRTUAL_clock_out] -min 0.000 [get_ports bus_strb_0]
##set_output_delay -clock [get_clocks VIRTUAL_clock_out] -max 8.000 [get_ports bus_strb_0]

#this impacts significantly setup time and fails for 100MHz clock!?
#set_output_delay -clock [get_clocks clk_fpga_0] -min -add_delay -0.500 [get_ports {leds_out_0[*]}]
#set_output_delay -clock [get_clocks clk_fpga_0] -max -add_delay 2.000 [get_ports {leds_out_0[*]}]
