# packages the dio24 project as user IP which can be included into the main project files
# tested with Vivado 2017.4 on Ubuntu 18.04 LTS
# created 16/5/2021 by Andi
# last update 18/5/2021 by Andi
#
# instructions:
# 1. ensure you have created the dio24 project with the ExpCtrl_dio24_project_script.tcl (see instructions there)
#    the folder dio24 contains the project and must be in the same folder as the script ExpCtrl_dio24_package_script.tcl
# 2. open Vivado and open the new dio24 project (if not already open) and in TCL console on bottom type:
#    cd /home/<path to ExpCtrl_dio24_package_script.tcl>
#    source ./ExpCtrl_dio24_package_script.tcl
#    this will open a temporary Package IP project, assign the interfaces and package it into the sub-folder ./ip_repo/dio24
# 3. check in the IP catalog (in the Project Manager pane on the left) that: 
#    there is a "User Repository" entry with "UserIP" sub-entry which should contain the new packaged IP "dio24_v1_0"
# 4. now you are done and can continue with creating the main projects Cora-Z7-10 and Cora-Z7-07S with the scrips:
#    ExpCtrl_Cora_Z7_10_project_script.tcl or ExpCtrl_Cora_Z7_07S_project_script.tcl
#
# in case of errors / crashes of Vivado:
# unfortunately, Vivado might crash during the execution of the script at random points!
# it happens most likely at the end when the IP catalog is updated.
# - first check if the packaged IP is in the IP catalog (point 3 above). if this is the case, you can contine since the IP is created.
# - if the IP is not in the catalog but the folder ip_repo/dio24/ contains a /src folder with verilog files, /xgui folder and component.xml folder,
#   the you can manually update the IP catalog. open any project (maybe the dio24 project), click "Settings" - "IP" - "Repository"
#   if there is a red entry select it and click the "-" to remove it from the list
#   click "+" and select the "/ip_repo" folder where the new packed IP is located and click "ok"
#   check point 3 above.
# - if the ip_repo/dio24 folder does not exist or is empty try to repeat steps 2-3 above. ensure that you run the script from the dio24 project.
# - if nothing works: 
#   - ensure that "Settings" - "IP" - "Repository" has no red entries and the current project is not in the list. maybe try emptying the list entirely.
#   - sometimes closing and re-opening Vivado can help
#   - delete the dio24 folder and start with point 1 above
#   - contact me. I can give you instructions on how to package the IP manually.

# open project and start packaging IP
# with this Vivado seems to crash more often. maybe since it does something in background?
#open_project ./dio24/dio24.xpr
#update_compile_order -fileset sources_1

# package project
ipx::package_project -root_dir ./ip_repo/dio24 -vendor user.org -library user -taxonomy /UserIP -import_files -set_current false
ipx::edit_ip_in_project -upgrade true -name tmp_edit_project -directory ./ip_repo/dio24 ./ip_repo/dio24/component.xml

# the AXI Light interface is automatically recognized but we have to associate clock
ipx::associate_bus_interfaces -busif s00_axi -clock clock_fast [ipx::current_core]

# create AXI stream master interface
ipx::add_bus_interface AXI_stream_master [ipx::current_core]
set_property abstraction_type_vlnv xilinx.com:interface:axis_rtl:1.0 [ipx::get_bus_interfaces AXI_stream_master -of_objects [ipx::current_core]]
set_property bus_type_vlnv xilinx.com:interface:axis:1.0 [ipx::get_bus_interfaces AXI_stream_master -of_objects [ipx::current_core]]
set_property interface_mode master [ipx::get_bus_interfaces AXI_stream_master -of_objects [ipx::current_core]]
ipx::add_port_map TLAST [ipx::get_bus_interfaces AXI_stream_master -of_objects [ipx::current_core]]
set_property physical_name out_last [ipx::get_port_maps TLAST -of_objects [ipx::get_bus_interfaces AXI_stream_master -of_objects [ipx::current_core]]]
ipx::add_port_map TDATA [ipx::get_bus_interfaces AXI_stream_master -of_objects [ipx::current_core]]
set_property physical_name out_data [ipx::get_port_maps TDATA -of_objects [ipx::get_bus_interfaces AXI_stream_master -of_objects [ipx::current_core]]]
ipx::add_port_map TVALID [ipx::get_bus_interfaces AXI_stream_master -of_objects [ipx::current_core]]
set_property physical_name out_valid [ipx::get_port_maps TVALID -of_objects [ipx::get_bus_interfaces AXI_stream_master -of_objects [ipx::current_core]]]
ipx::add_port_map TKEEP [ipx::get_bus_interfaces AXI_stream_master -of_objects [ipx::current_core]]
set_property physical_name out_keep [ipx::get_port_maps TKEEP -of_objects [ipx::get_bus_interfaces AXI_stream_master -of_objects [ipx::current_core]]]
ipx::add_port_map TREADY [ipx::get_bus_interfaces AXI_stream_master -of_objects [ipx::current_core]]
set_property physical_name out_ready [ipx::get_port_maps TREADY -of_objects [ipx::get_bus_interfaces AXI_stream_master -of_objects [ipx::current_core]]]
ipx::associate_bus_interfaces -busif AXI_stream_master -clock clock_fast [ipx::current_core]

# create AXI stream slave interface
ipx::add_bus_interface AXI_stream_slave [ipx::current_core]
set_property abstraction_type_vlnv xilinx.com:interface:axis_rtl:1.0 [ipx::get_bus_interfaces AXI_stream_slave -of_objects [ipx::current_core]]
set_property bus_type_vlnv xilinx.com:interface:axis:1.0 [ipx::get_bus_interfaces AXI_stream_slave -of_objects [ipx::current_core]]
ipx::add_port_map TDATA [ipx::get_bus_interfaces AXI_stream_slave -of_objects [ipx::current_core]]
set_property physical_name in_data [ipx::get_port_maps TDATA -of_objects [ipx::get_bus_interfaces AXI_stream_slave -of_objects [ipx::current_core]]]
ipx::add_port_map TLAST [ipx::get_bus_interfaces AXI_stream_slave -of_objects [ipx::current_core]]
set_property physical_name in_last [ipx::get_port_maps TLAST -of_objects [ipx::get_bus_interfaces AXI_stream_slave -of_objects [ipx::current_core]]]
ipx::add_port_map TVALID [ipx::get_bus_interfaces AXI_stream_slave -of_objects [ipx::current_core]]
set_property physical_name in_valid [ipx::get_port_maps TVALID -of_objects [ipx::get_bus_interfaces AXI_stream_slave -of_objects [ipx::current_core]]]
ipx::add_port_map TKEEP [ipx::get_bus_interfaces AXI_stream_slave -of_objects [ipx::current_core]]
set_property physical_name in_keep [ipx::get_port_maps TKEEP -of_objects [ipx::get_bus_interfaces AXI_stream_slave -of_objects [ipx::current_core]]]
ipx::add_port_map TREADY [ipx::get_bus_interfaces AXI_stream_slave -of_objects [ipx::current_core]]
set_property physical_name in_ready [ipx::get_port_maps TREADY -of_objects [ipx::get_bus_interfaces AXI_stream_slave -of_objects [ipx::current_core]]]
ipx::associate_bus_interfaces -busif AXI_stream_slave -clock clock_fast [ipx::current_core]

# save package
update_compile_order -fileset sources_1
set_property core_revision 1 [ipx::current_core]
ipx::create_xgui_files [ipx::current_core]
ipx::update_checksums [ipx::current_core]
ipx::save_core [ipx::current_core]

# close edit_ip project and delete temporary files.
# you can keep it open to check for errors, but I am not sure if the update of IP catalog is working then.
close_project -delete

# update IP catalog
# when I give ip_repo/dio24 Vivado might crash?
set_property  ip_repo_paths  ./ip_repo [current_project]
update_ip_catalog

#close project 
#close_project



