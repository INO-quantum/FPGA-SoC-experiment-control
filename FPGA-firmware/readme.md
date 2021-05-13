This folder contains the firmware running on the board. 

It is divided into the hardware (FPGA logic) and the software part (running on the CPU/Linux)

1. Hardware implementation:

The Hardware is generated with the Vivado 2017.4 software from Xilinx running on Ubuntu 18.04 LTS (Vivado is available also for Windows, but Petalinux - see below - requires a Linux OS). Vivado WebPACK can be downloaded for free and supports the 7-Series devices from Xilinx which are used here. For instructions on how to install Vivado 2017.4 see here: https://www.xilinx.com/support/documentation/sw_manuals/xilinx2017_4/ug973-vivado-release-notes-install-license.pdf. See also this tutorial: https://reference.digilentinc.com/vivado/installing-vivado/start. I have tested the Windows and Linux versions. Officially, Ubuntu 16.04.2 LTS is required but installation on 18.04 LTS was working. There are a few dependencies and the installer will tell you what is missing. 

I had only one bigger issue with Python - I think 3.5 is required - which I had installed but the installer did not recognize it. When I did this the first time, installing Python 2.7 was resolving the issue, the second time this did not help but somehow I have got it working without knowing how. I tried to install Vivado on Ubuntu 20.04 LTS but I did not managed to solve the Python issue. I worked initially with Vivado 2018.1 and then 2018.3 but I had many issues (see below) and finally downgraded to 2017.4 which seems to be more stable. Also, the board support package for the Cora-Z7 board from Digilent require Petalinux 2017.4, which is designed to work with Vivado 2017.4.

After Vivado is installed you need to download and copy the board files from Digilent: https://reference.digilentinc.com/vivado/installing-vivado/start#installing_digilent_board_files.

Now you can generate the project from the provided TCL script: Extract the ExpCtrl_project_script_Cora_Z7_10.zip (ExpCtrl_project_script_Cora_Z7_07S.zip) file in the folder where you would like to have the project be located. Open Vivado - Tools - Run Tcl Script... and select the ExpCtrl_project_script_Cora_Z7_10.tcl (or ExpCtrl_project_script_Cora_Z7_07S.tcl) script and click ok. Vivado will regenerate the project. After this is done you can "Open Block Design" in the Flow Navigator to get an overview of the project. The block "dio24_0" is the main module of the experiment control. Double-click you can change parameters of this module. Right-click and select "Edit in IP packager" you can modifiy the verilog source files. After you are happy with the modifications select the tab "Package IP - dio24", click on all icons which are not marked with a green check mark and select "merge changes .." and finally on the "Review and Package" tab click "Re-Package IP". Back in the main project you should get a notification on the top indicating that you should "Report IP Status" (or click Tools - Report - Report IP status) and on the bottom you will se the panel "IP status" with dio24_0 indicated with revision changed. Click on "Upgrade Selected" and you are asked to generate output products which you confirm by clicking the "generate" button. If your changes were fine it will finish without errors after a minute. Click on "Generate Bitstream" and wait for several minutes (depends on how many changes were done) until the bitstream is created. Vivado will ask you if you want to "Open Implemented Design" which you can choose to open or just Cancel (since it takes some seconds). Click File - Export - Export Hardware. In the dialog box select "Include Bitstream" and click ok. Now you have generated the bistream which is loaded to the FPGA during the booting. The file design_1_.warpper.hdf is located in your project directory/project_name.sdk folder and you will need to copy it into the Petalinux project folder since the hdf contains also information about the "device tree" used by Petalinux (see below). 

In Vivado 2018.1 and 2018.3 the upgrading was often not working or crashed Vivado and few times messed up the entire project such that it was not usable anymore. First try to "rerun" in the "IP Status" panel if it will work. Otherwise, close the project, reopen the project and then upgrading was usually working. Also the SDK (not used here) in the 2018 versions was always (100%) crashing and could not be used anymore after the project was changed. In 2017.4 I think I never had these problems.

2. Software implementation:

In the future I will provide my own project BSP files to make this easier.

Petalinux is a simple Linux distribution which allows you to run an embedded Linux operating system on the CPU. The board support package from Digilent uses Petalinux 2017.4 which needs to be installed on Ubuntu or a few other Linux OS. Please follow this guide here from Digilent to create the Petalinux project: https://github.com/Digilent/Petalinux-Cora-Z7-10. 

Now you should have your Petalinux project folder and it should compile without errors and you can run the demo design. To update the bitstream with the one generated by Vivado: copy the design_i_wrapper.hdf file into your Petalinux folder and input on the console: 
cd into project folder
*source <petalinux-folder>/settings.sh
*petalinux-config --get-hw-description=./           // you have to do this every time you change the bitstream
*exit from the configuration menu or set MAC address if the first time (see below)

Add the driver module:
*petalinux-create -t modules -n dio24 --enable		  // use lowercase only!
*petalinux-config -c rootfs		                      // check if module is in list and enable module if not --enable
*petalinux-config -c kernel	      	                // exit without modifications or disable DMA driver (see below). this might be needed for 1st module?
this will add a demonstration driver module to the project in the folder <project>/project-spec/meta-user/recipes-modules
replace the dio24 folder with the one here on github
  
Add the server C++ application:
*petalinux-create -t apps --template c++ -n FPGA-server --enable	// do not use '_' in names!
*petalinux-config -c rootfs		                      // check if app is in list and enable if not --enable
this will add a hello-world demo application in the folder <project>/project-spec/meta-user/recipes-apps
replace the FPGA-server folder with the one here on github
You can do the same with the C++ applicaton FPGA-test which can be run manually on the console of the SoC and is used to display register content and to run some tests.
  
Add the startup script:
*petalinux-create -t apps --template install -n FPGA-init --enable
*petalinux-config -c rootfs		                      // check if is in list of apps and enable if not --enable
this will add a demo install script in the folder <project>/project-spec/meta-user/recipes-apps
replace the FPGA-init folder with the one here on github
You can do the same with FPGA-exit, which can be run manually on the console of the SoC and unmounts the SD card and flash USB devices.
  
Set MAC address:
*petalinux-config
  *go to Subsystem AUTO Hardware Settings - Ethernet Settings - Ethernet MAC address
  *set mac address to the one given on sticker of the board 
  
Set Linux Kernel Source (optional):
this is useful if you have several projects. 
*petalinux-config:
  *select Linux Component Selection
  *in "linux Kernel" select ext-local-src
  *in External linux-kernel local source settings select folder (I have /home/.../linux-xlnx-xilinx-v2017.4)
  *download Kernel source into the selected folder. I use this from Xilinx: linux-xlnx-xilinx-v2017.4

You have to disable the DMA driver from Xilinx:
*petalinux-config -c kernel
*in device drivers: disable DMA Engine Support -> this ensures that my driver is used and not the one from Xilinx
*in device drivers: disable multimedia support (otherwise get errors about missing DMA driver)
*in device drivers: disable sound card support
*in device drivers: graphics support: disable Xilinx DRM (otherwise get errors about missing DMA driver)

To compile the project:
*petalinux-build      // for the first time this will download the linux kernel (if not selected from local folder) and u-boot
*petalinux-package --boot --force --fsbl images/linux/zynq_fsbl.elf --fpga images/linux/design_1_wrapper.bit --u-boot
*copy image.ub and BOOT.BIN in the <project>/images/linux folder on the SD card. 
*copy the server.config file (see <github folder>/FPGA-firmware/images/) and modify the IP address as you like
*power on the board with jumper set for SD card (see https://reference.digilentinc.com/reference/programmable-logic/cora-z7/reference-manual)
