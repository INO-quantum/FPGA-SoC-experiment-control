# timing.xdc
# define general timing constraints
# disable for Synthesis, enable for Implementation to avoid Critical Warnings.

## all active clocks before going to Vivado 2020.2
#set_clock_groups -asynchronous -group clk_fpga_0 -group [get_clocks -of_objects [get_pins design_1_i/clk_wiz_1/inst/mmcm_adv_inst/CLKOUT0]]
#set_clock_groups -physically_exclusive -group [get_clocks -include_generated_clocks clkfbout_design_1_clk_wiz_1_0] -group [get_clocks -include_generated_clocks clkfbout_design_1_clk_wiz_1_0_1]
#set_clock_groups -physically_exclusive -group [get_clocks -include_generated_clocks clk_bus_design_1_clk_wiz_1_0] -group [get_clocks -include_generated_clocks clk_bus_design_1_clk_wiz_1_0_1]
#set_clock_groups -physically_exclusive -group [get_clocks -include_generated_clocks clk_det_design_1_clk_wiz_1_0] -group [get_clocks -include_generated_clocks clk_det_design_1_clk_wiz_1_0_1]
#set_clock_groups -asynchronous -group [get_clocks clk_fpga_0] -group [get_clocks clk_det_design_1_clk_wiz_1_0_1]
#set_clock_groups -asynchronous -group [get_clocks clk_det_design_1_clk_wiz_1_0_1] -group [get_clocks clk_fpga_0]
## automatically included by constraint wizard:
#set_clock_groups -physically_exclusive -group [get_clocks -include_generated_clocks clk_out_design_1_clk_wiz_1_0] -group [get_clocks -include_generated_clocks clk_out_design_1_clk_wiz_1_0_1]
#set_clock_groups -asynchronous -group [get_clocks clk_bus_design_1_clk_wiz_1_0_1] -group [get_clocks clk_det_design_1_clk_wiz_1_0]
#set_clock_groups -asynchronous -group [get_clocks clk_bus_design_1_clk_wiz_1_0] -group [get_clocks clk_det_design_1_clk_wiz_1_0_1]
## automatically included by constraint wizard:
#set_clock_groups -physically_exclusive -group [get_clocks -include_generated_clocks clk_pwm_design_1_clk_wiz_1_0] -group [get_clocks -include_generated_clocks clk_pwm_design_1_clk_wiz_1_0_1]
#set_false_path -from [get_clocks clk_pwm_design_1_clk_wiz_1_0_1] -to [get_clocks clk_fpga_0]

# auto-created by Vivado 2020.2 Constraints Wizard:
#set_clock_groups -physically_exclusive -group [get_clocks -include_generated_clocks clkfbout_design_1_clk_wiz_1_0] -group [get_clocks -include_generated_clocks clkfbout_design_1_clk_wiz_1_0_1]
#set_clock_groups -physically_exclusive -group [get_clocks -include_generated_clocks clk_100_design_1_clk_wiz_1_0] -group [get_clocks -include_generated_clocks clk_100_design_1_clk_wiz_1_0_1]
#set_clock_groups -physically_exclusive -group [get_clocks -include_generated_clocks clk_100_PS_design_1_clk_wiz_1_0] -group [get_clocks -include_generated_clocks clk_100_PS_design_1_clk_wiz_1_0_1]
#set_clock_groups -physically_exclusive -group [get_clocks -include_generated_clocks clk_10_design_1_clk_wiz_1_0] -group [get_clocks -include_generated_clocks clk_10_design_1_clk_wiz_1_0_1]
#set_clock_groups -asynchronous -group [get_clocks clk_100_design_1_clk_wiz_1_0_1] -group [get_clocks clk_100_PS_design_1_clk_wiz_1_0]
#set_clock_groups -asynchronous -group [get_clocks clk_100_design_1_clk_wiz_1_0] -group [get_clocks clk_100_PS_design_1_clk_wiz_1_0_1]
#set_clock_groups -asynchronous -group [get_clocks clk_fpga_0] -group [get_clocks clk_100_PS_design_1_clk_wiz_1_0_1]
#set_clock_groups -asynchronous -group [get_clocks clk_100_PS_design_1_clk_wiz_1_0_1] -group [get_clocks clk_100_design_1_clk_wiz_1_0]
#set_clock_groups -asynchronous -group [get_clocks clk_100_PS_design_1_clk_wiz_1_0] -group [get_clocks clk_100_design_1_clk_wiz_1_0_1]
#set_clock_groups -asynchronous -group [get_clocks clk_100_PS_design_1_clk_wiz_1_0_1] -group [get_clocks clk_fpga_0]
#set_false_path -from [get_clocks clk_10_design_1_clk_wiz_1_0_1] -to [get_clocks clk_fpga_0]
# manually added
#set_false_path -from [get_clocks clk_fpga_0] -to [get_clocks clk_100_design_1_clk_wiz_1_0]
#set_false_path -from [get_clocks clk_fpga_0] -to [get_clocks clk_100_design_1_clk_wiz_1_0_1]
#set_false_path -from [get_clocks clk_fpga_0] -to [get_clocks clk_10_design_1_clk_wiz_1_0]
#set_false_path -from [get_clocks clk_fpga_0] -to [get_clocks clk_10_design_1_clk_wiz_1_0_1]
#set_false_path -from [get_clocks clk_100_design_1_clk_wiz_1_0_1] -to [get_clocks clk_fpga_0]

# added by constraint wizard
set_clock_groups -physically_exclusive -group [get_clocks -include_generated_clocks clkfbout_design_1_clk_wiz_1_0] -group [get_clocks -include_generated_clocks clkfbout_design_1_clk_wiz_1_0_1]
set_clock_groups -physically_exclusive -group [get_clocks -include_generated_clocks clk_bus_design_1_clk_wiz_1_0] -group [get_clocks -include_generated_clocks clk_bus_design_1_clk_wiz_1_0_1]
set_clock_groups -physically_exclusive -group [get_clocks -include_generated_clocks clk_det_design_1_clk_wiz_1_0] -group [get_clocks -include_generated_clocks clk_det_design_1_clk_wiz_1_0_1]
set_clock_groups -physically_exclusive -group [get_clocks -include_generated_clocks clk_pwm_design_1_clk_wiz_1_0] -group [get_clocks -include_generated_clocks clk_pwm_design_1_clk_wiz_1_0_1]
set_clock_groups -physically_exclusive -group [get_clocks -include_generated_clocks clk_out_design_1_clk_wiz_1_0] -group [get_clocks -include_generated_clocks clk_out_design_1_clk_wiz_1_0_1]
set_clock_groups -asynchronous -group [get_clocks clk_fpga_0] -group [get_clocks clk_det_design_1_clk_wiz_1_0_1]
set_clock_groups -asynchronous -group [get_clocks clk_det_design_1_clk_wiz_1_0_1] -group [get_clocks clk_fpga_0]
#set_false_path -from [get_clocks clk_pwm_design_1_clk_wiz_1_0_1] -to [get_clocks clk_fpga_0]

# manually added
set_false_path -from [get_clocks clk_fpga_0] -to [get_clocks clk_bus_design_1_clk_wiz_1_0]
set_false_path -from [get_clocks clk_fpga_0] -to [get_clocks clk_bus_design_1_clk_wiz_1_0_1]
set_false_path -from [get_clocks clk_bus_design_1_clk_wiz_1_0] -to [get_clocks clk_fpga_0]
set_false_path -from [get_clocks clk_bus_design_1_clk_wiz_1_0_1] -to [get_clocks clk_fpga_0]

set_false_path -from [get_clocks clk_fpga_0] -to [get_clocks clk_det_design_1_clk_wiz_1_0]
set_false_path -from [get_clocks clk_fpga_0] -to [get_clocks clk_det_design_1_clk_wiz_1_0_1]
set_false_path -from [get_clocks clk_det_design_1_clk_wiz_1_0] -to [get_clocks clk_fpga_0]
set_false_path -from [get_clocks clk_det_design_1_clk_wiz_1_0_1] -to [get_clocks clk_fpga_0]

set_false_path -from [get_clocks clk_fpga_0] -to [get_clocks clk_pwm_design_1_clk_wiz_1_0]
set_false_path -from [get_clocks clk_fpga_0] -to [get_clocks clk_pwm_design_1_clk_wiz_1_0_1]
set_false_path -from [get_clocks clk_pwm_design_1_clk_wiz_1_0] -to [get_clocks clk_fpga_0]
set_false_path -from [get_clocks clk_pwm_design_1_clk_wiz_1_0_1] -to [get_clocks clk_fpga_0]

set_false_path -from [get_clocks clk_bus_design_1_clk_wiz_1_0_1] -to [get_clocks clk_det_design_1_clk_wiz_1_0]

# added by Constraints Wizard for ExpCtrl_top module
set_clock_groups -asynchronous -group [get_clocks clk_det_design_1_clk_wiz_1_0_1] -group [get_clocks clk_bus_design_1_clk_wiz_1_0]
set_clock_groups -asynchronous -group [get_clocks clk_det_design_1_clk_wiz_1_0] -group [get_clocks clk_bus_design_1_clk_wiz_1_0_1]
set_clock_groups -asynchronous -group [get_clocks clk_bus_design_1_clk_wiz_1_0] -group [get_clocks clk_det_design_1_clk_wiz_1_0_1]
