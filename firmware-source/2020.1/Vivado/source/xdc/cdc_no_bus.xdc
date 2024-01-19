# constraint file cdc_no_bus.xdc, created 8/8/2023 by Andi
# constraints Verilog module: cdc_no_bus.v 

# either manually set for this file: SCOPED_TO_REF = cdc_no_bus.v
# or enable next line to automatically set this for cdc_no_bus module.
# ensure cdc_no_bus.xdc is in sources of project.
# BUT next line gives and error with get_files! so have to do it manually.
# set_property SCOPED_TO_REF cdc_no_bus [get_files cdc_no_bus.xdc]

# set max delay between input 'in' and ouput 'out' of cdc_no_bus module to the output clock period
#set_max_delay -datapath_only -from [get_ports in[*]] -to [get_ports out[*]] [get_property -min PERIOD [get_clocks -of_objects [get_ports clk_out]]]

# see https://support.xilinx.com/s/question/0D52E00006hpXG6SAM/apply-setfalsepath-to-registers-between-different-clocks-using-name-wildcard?language=en_US
set cdc_period_ratio 0.95
set dst_ff [get_cells *SNB[*].sync_reg[0]]
set src_ff [get_cells -of_objects [get_pins -filter {IS_LEAF && DIRECTION == OUT} -of_objects [get_nets -segments -of_objects [get_pins *SNB[*].sync_reg[0]/D]]]]
set min_period [get_property -min PERIOD [get_clocks -of_objects [list $src_ff $dst_ff]]]
set_max_delay -from $src_ff -to $dst_ff [expr {$min_period} * $cdc_period_ratio]
