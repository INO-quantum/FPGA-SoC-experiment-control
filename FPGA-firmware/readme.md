# FPGA firmware

This folder contains the firmware running on the board. 

It is divided into the hardware logic implementation (Vivado) and the software part running on the CPU/Linux (Petalinux)

## Hardware implementation:

  The Hardware is generated with the Vivado 2017.4 software from Xilinx running on Ubuntu 18.04 LTS (Vivado is available also for Windows). Vivado WebPACK can be downloaded for free and supports the 7-Series SoC devices from Xilinx which are used here. For instructions on how to install Vivado 2017.4 see here: https://www.xilinx.com/support/documentation/sw_manuals/xilinx2017_4/ug973-vivado-release-notes-install-license.pdf. See also this tutorial: https://reference.digilentinc.com/vivado/installing-vivado/start. I have tested the Windows and Linux versions. Officially, Ubuntu 16.04.2 LTS is required but installation on 18.04 LTS was working. There are a few dependencies and the installer will tell you what is missing. 

  I had only one bigger issue with Python - I think 3.5 is required - which I had installed but the installer did not recognize it. When I did this the first time, installing Python 2.7 was resolving the issue, the second time this did not help but somehow I have got it working without knowing how. I tried to install Vivado on Ubuntu 20.04 LTS but I did not managed to solve the Python issue. I worked initially with Vivado 2018.1 and then 2018.3 but I had many issues (see below) and finally downgraded to 2017.4 which seems to be more stable. Also, the board support package for the Cora-Z7 board from Digilent require Petalinux 2017.4, which is designed to work with Vivado 2017.4.

  After Vivado is installed you need to download and copy the board files from Digilent: https://reference.digilentinc.com/vivado/installing-vivado/start#installing_digilent_board_files.

### Generate the Vivado project:

- copy the content of the sub-folder Vivado_2017.4/release_202x.x-x (take the latest) into the folder where you want the project to be located
- open Vivado and on the bottom "Tcl console" type: (tested on ubuntu 18.04 LTS, should be similar on other OS)
  - cd /home/path to your folder with tcl scripts
  - source ./ExpCtrl_dio24_project_script.tcl
- wait until the dio24 project is created. check that a new folder dio24 was created in the script folder.
- do not close the project but type in the "Tcl console" on the bottom:
  - source ./ExpCtrl_dio24_package_script.tcl
- this will open the IP packager to package the dio24 project into a custom IP in the sub-folder /ip_repo/dio24/. this is the custom module which we use for the project. The Verilog source is in the /hdl folder. wait until the packager has closed and you are back in the dio24 project. 
- check if there are errors in the Tcl console.
- check that in the "IP Catalog" (in the Project Manager on the left) there is now a new entry "User Repository" - "UserIP" - "dio24_v1_0". Otherwise, click in Project Manager on "Settings" - "IP" - "Repository". remove any red repository there (select and click the "-") and click "+" and select the new /ip_repo folder.
- close the project
- now you can create the main project for the Cora-Z7-10 or Cora-Z7-07S board (or both) and type again in the "Tcl console" of Vivado for either board:
  - source ./ExpCtrl_Cora_Z7_10_project_script.tcl
  - source ./ExpCtrl_Cora_Z7_07S_project_script.tcl
- this will create the main project in a new sub-folder "Cora-Z7-10" or "Cora-Z7-07S". The last output on the console should read "INFO: Project created:Cora-Z7-xx" with xx="10" or "07S" depending on the board. There will be 12 critical warnings which can be ignored. Four of them are: "PCW_UIPARAM_DDR_DQS_TO_CLK_DELAY_* has negative value...". They are about DDR timings. See here (for a different board): https://github.com/Digilent/SDSoC-Zybo-Z7-20
- in the Project Manager - IP Integrator "Open Block Design" and press the Round-Circle-Arrow symbol to regenerate the Layout. You should see something similar as in the screenshot file in the script folder.
- click the Square-Check-Mark symbol to validate design: you should get only the 4 Critical Warnings from above.
  - click in Project Manager "Program and Debug" - "Generate Bitstream"
  - this will generate the bitstream which will be uploaded on the FPGA. Depending on your computer this can take several minutes (the first time). On mine it takes 10 Minutes. You can observe the progress in the "Design Run" Tab on the Bottom.
- When Vivado is finished it will ask you to "Open Implemented Design" which you can "cancel" or click "ok" to see the placement on the chip and other information.
- click File - Export - Export Hardware - ensure "Include Bitstream" is selected and click ok. This saves the file design_1_warpper.hdf in your project directory/project_name.sdk folder. You will need to copy this file into the Petalinux project folder since the hdf contains not only the "bit stream" but also information about the "device tree" used by Petalinux (see below).
  
### Modify the project: 
- in the Block design right-click on the dio24 module block and select "Edit in IP-packager". 
- In the packager you can modify the source Verilog files. 
- After Modification ensure that in the "Package IP" tab all items have a green checkmark, otherwise click the item and on the top "Merge changes...". 
- On the last entry on the bottom click "Re-package IP". 
- After this you have to "Upgrade IP". Usually, you will get a notification that this has to be done, otherwise select "Tools" - "Reports" - "Report IP Status". and a new pane opens on the bottom. if there is a blue "Rerun" text, click on it to run it again and it will tell you which module needs to be upgraded. Click on the bottom on "Upgrade Selected". 
- It will ask to "Regenerate Output Products" which you can click "OK" or "Cancel" and go to next point immediately (which will generate output products if not done). 
- Generate Bitstream
- Watch out the "Messages" window on the bottom. There are many warnings (1331 for first run of tcl) but most can be ignored. However, if something does not work, you will most likely find hints there. Critical Warnings should not be ignored except a few standard ones (like the 4 PCW_UIPARAM_DDR_DQS_TO_CLK_DELAY_ from above or when the upgrading has detected port changes). Note that Vivado 2017.4 still displays old messages (especially errors) even when you have fixed them (not the case anymore in 2018 versions). 

### In case of troubles:
on my system it is likely that Vivado crashes during the execution of the tcl scripts
- ensure that before packaging of the IP (the second script mentioned above) in "Settings" - "IP" - "Repository" there is no red entry, otherwise remove it. If the project entry is there remove it as well. 
- all crashes which I experienced on Ubuntu 18.04 happen randomly, often immediately or a few seconds after tcl script, IP packager or generating output products started. just retrying can help.
- ensure that Ubuntu is not running with Wayland but with Xorg and ensure that its up-to-date. avoid clicking anything during execution of the tcl script. maybe move the mouse outside of the Vivado window. there is a known bug from 2016-2018 (maybe even 2020?) versions of Vivado, but nothing has helped for me.
- wait until all background activity of Vivado has stopped or close and re-open before going to the next step.
- especially for upgrading an IP on Vivado 2018 it required to close the project and re-open it before upgrading. Maybe "Rerun" the IP status report might also help.
- Vivado 2017.4 seems more stable than 2018.1 and 2018.3 versions (the SDK was quasi unusable there but is not used here in this project).

## Software implementation:

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
