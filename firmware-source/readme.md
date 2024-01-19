# FPGA firmware

This folder contains the source files needed for building the firmware for the Cora-Z7 board. The building process can be divided into two main steps: 

1. generate the hardware logic on the FPGA part using Vivado (2020.1)
2. generate the Linux image and software running on the CPU with Petalinux (2020.1)

These software tools are very heavy and not easy to use and Vivado randomly crashes. First time compilation can take easily 15 minutes and for Petalinux several additional resources need to be downloaded from the internet. After the first successful compilation the compile time is reduced but at least 5 minutes per iteration makes debugging still very tedious.

If you are looking for ready-to-use firmware files please have a look at the [firmware-release folder](/firmware-release), select the folder corresponding to your FPGA-SoC board and the version of your buffer card and choose primary or secondary board.

## Hardware implementation:

The Hardware logic is generated with Vivado 2020.1 from Xilinx running on Ubuntu 20.04 LTS (Vivado is available also for Windows). Vivado WebPACK can be downloaded for free and supports the Zynq 7000 series SoC devices from Xilinx which are used in this project. For instructions on how to install Vivado 2020.1 [see UG973 from Xilinx](https://docs.xilinx.com/v/u/2020.1-English/ug973-vivado-release-notes-install-license). See also the very good [tutorial from Digilent](https://digilent.com/reference/programmable-logic/guides/installing-vivado-and-vitis). For this project Vitis is not needed but for debugging it can be useful and if you want to test `baremetal` projects you will need it. During the installation ensure support for the Zynq-7000 series is enabled. I have tested the Windows and Linux versions and have not seen a big difference. Officially, Ubuntu 18.04 LTS is required but installation on 20.04 LTS is working.

<!--check my notes!-->

On Windows you should have a shortcut on the desctop or enter `vivado` in the search box of the task bar. On Ubuntu you need to launch Vivado from the terminal like this:

    cd <working folder>
    source /opt/Xilinx/Vivado/2020.1/settings64.sh
    export LC_ALL=C
    vivado
    
This assumes Vivado was installed in the standard location[^1]. Do not execute `vivado` in your home folder since it will contaminate it with temporary files. It is best to create a `work` folder for this purpose. The important `export` command you can also add to `settings64.sh`, so you do not forget it. The `cd` command I do not recommend to add to the file since some scripts execute `settings64.sh` automatically and will end up in an unexpected folder. 

[^1]: I prefer to install Vivado in the home directory `~/Xilinx/Vivado/`.

> [!Note]
> By sourcing `settings64.sh` manually you can easily switch between different versions of Vivado. This might be needed since projects generated with one version usually make troubles when trying to use with another version.

After Vivado is installed you need to download and copy the [board files from Digilent](https://reference.digilentinc.com/vivado/installing-vivado/start#installing_digilent_board_files).


> [!NOTE]
> I am in the process of updating this page. The information below is not anymore up-to-date ...


### Generate the Vivado project:

- copy the content of the sub-folder Vivado_2017.4/release_202x.x-x (take the latest) into the folder where you want the project to be located
- open Vivado and on the bottom "Tcl console" type: (tested on ubuntu 18.04 LTS, should be similar on other OS)
        
      cd /home/path to your folder with tcl scripts
      source ./ExpCtrl_dio24_project_script.tcl

- wait until the dio24 project is created. check that a new folder dio24 was created in the script folder.
- do not close the project but type in the "Tcl console" on the bottom:
    
      source ./ExpCtrl_dio24_package_script.tcl
       
- this will open the IP packager to package the dio24 project into a custom IP in the sub-folder /ip_repo/dio24/. this is the custom module which we use for the project. The Verilog source is in the /hdl folder. wait until the packager has closed and you are back in the dio24 project. 
- check if there are errors in the Tcl console.
- check that in the "IP Catalog" (in the Project Manager on the left) there is now a new entry "User Repository" - "UserIP" - "dio24_v1_0". Otherwise, click in Project Manager on "Settings" - "IP" - "Repository". remove any red repository there (select and click the "-") and click "+" and select the new /ip_repo folder.
- close the project
- now you can create the main project for the Cora-Z7-10 or Cora-Z7-07S board (or both) and type again in the "Tcl console" of Vivado for either board:

      source ./ExpCtrl_Cora_Z7_10_project_script.tcl
      source ./ExpCtrl_Cora_Z7_07S_project_script.tcl
      
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
Unfortunately, Vivado on Ubuntu 18.04 LTS tends to crash frequently during the execution of the tcl scripts and rarely otherwise
- before packaging of the IP (the second script mentioned above), ensure, that in "Settings" - "IP" - "Repository" there is no red entry, otherwise remove it. If a project entry is there, remove it as well. 
- all crashes happen randomly, often immediately or a few seconds after tcl script, IP packager or generating output products started. just retry and most likely it will work the next time.
- ensure that Ubuntu is not using Wayland but Xorg as display server in Ubuntu. Ensure your Os is up-to-date. avoid clicking anything during execution of the tcl script. maybe move the mouse outside of the Vivado window. For Vivado there is a known bug from 2016-2018 versions (maybe even 2020?), but nothing has helped for me. However, it crashes only rarely and 2017 is maybe more stable than 2018 (there the SDK was unusable, but is not needed here).
- wait until all background activity of Vivado has stopped or close and re-open before going to the next step.
- especially for upgrading an IP on Vivado 2018 it required to close the project and re-open it before upgrading. Maybe "Rerun" the IP status report might also help.

## Software implementation:

Petalinux is a simple Linux distribution which allows you to run an embedded Linux operating system on the CPU. The original board support package (bsp) I used for this project is from Digilent (see https://reference.digilentinc.com/reference/software/petalinux/start) and requires Petalinux 2017.4, which needs to be installed on Ubuntu or a few other Linux OS. Please follow this guide to install Petalinux: https://github.com/Digilent/Petalinux-Cora-Z7-10. The guide uses the recommended installation folder /opt/pkg/petalinux.


### Generate Project:

We are still following the guide from before, but instead of using the Digilent bsp (which was the original bsp of my project), we use our project bsp (Petalinux-Cora-Z7-yy-20xx.x-0.bsp for your board with yy="10" or "07S") which you copy onto your computer, open a console and cd to a folder where you want the project to be located and create the project:

    cd path-to-folder-where-new-project-should-be-created
    source path-to-petalinux-installation-folder/settings.sh
    petalinux-create -t project -s path/Petalinux-Cora-Z7-yy-20xx.x-x.bsp

### Using the pre-built images:

In the sub-folder "pre-built" of the project you find the prebuilt images with which you can immediately run the board. 
- copy the files BOOT.BIN (bootloader), image.ub (Linux image), uEnv.txt (Ethernet MAC address) and server.config (server IP address) on a micro-SD card. 
- edit uEnv.txt and insert the MAC address given on the sticker of your board. 
- edit server.config and insert the IP address which you want to use for your board.
- insert the micro SD card into the board
- short the "Mode" jumper on the board to boot from SD card
- set the power jumper to "USB" or "EXT" depending on which power source you want to use (board needs less than 0.3A, so USB 2.0 should be fine)
- ATTENTION: external supply must be 4.5-5.5V DC center positive! Power jack has inner diameter 2.1-2.5mm. There is no input protection or regulator on the input and with higher input voltage you can damage the board! Recommended supply current is >= 1A but my measurements show that with the current design the board draws slightly less than 0.3A.
- power up the board
- you should see the red power LED near the power jack and the yellow LED near the USB-A plug should be on, indicating that the bitstream has been programmed. The 3-color LEDs near the two pushbuttons should be green and red with low intensity. 
- open minicom (or other terminal program) with 115200/8/N/1 settings (and no Hardware flow control). Connect your computer with a USB cable and the micro-USB connector on the board (used also for USB power if selected). The board appears usally as ttyUSB1 or ttyUSB3 (if a second board is already connected).
- pressing Enter in the terminal program you should see the TX and RX LEDs blinking near the micro-USB connector and you should see the console of the board root@Cora-Z7-yy.
- if you push the SRST button (or type "reboot") the board reboots and you can observe the booting process of the Linux. At the end you will see when the dio24 module is loaded and the server is started

In case of problems:
- check the board is powered (red LED is on) and power is stable - especially during booting. If using a wall-plug be absolutely sure it gives 5V DC with more than 0.3A (1A recommended)! 
- if the yellow LED is not on, then the bitstream was not written. either the SD card is not properly inserted or the bitstream is corrupt or for a different board. check that the SD card is properly inserted: remove and insert again. check that the sticker on the FPGA-SoC chip reads "10" for the Cora-Z7-10 board or "7S" for the Cora-Z7-07S board. Choose the proper images for the board. try to copy the images again or try a different micro SD card.
- sometimes the board boots accidently into the "Zynq>" console or you have entered something on the terminal during boot. Enter: "boot" or push the SRST button and the board should boot again.

### Compiling the Petalinux project:

1. For compiling the Petalinux project cd into project folder and source petalinux if not already done:

       cd path-to-project-folder
       source <petalinux-folder>/settings.sh
    
2. For a new project you should set the MAC address to the one given on the sticker of the board:

       petalinux-config
       navigate to "Subsystem AUTO Hardware Settings" - "Ethernet Settings" - "Ethernet MAC address"
       edit MAC address to the one given on sticker of the board 
       exit from all sub-menus and from configuration menu and select to save new configuration
  
3. Set Linux Kernel Source (optional):
This is useful if you have several projects, otherwise Petalinux will download it automatically for each project. 
    
       petalinux-config
       select "Linux Component Selection"
       in "linux-kernel" select "ext-local-src"
       in "External linux-kernel local source settings" enter folder as "/home/<user name>/<path-to-folder>"
       download Kernel source into the selected folder 

As kernel source I use this from Xilinx: https://github.com/Xilinx/linux-xlnx/releases/tag/xilinx-v2017.4

4. When you have changed the bitstream with Vivado:
copy the design_1_wrapper.hdf file generated by Vivado from the "sdk" folder (see above) into the Petalinux project folder and type

       petalinux-config --get-hw-description=./
       exit from configuration menu

5. Compile project:

       petalinux-build
    
For the first time this will download the linux kernel (if not selected from local folder) and u-boot (bootloader source) and compiling will need some time (9 Minutes on my system including downloading). There will be 3 warnings but which can be savely ignored: the RDEPENDS warnings sometimes change.

    WARNING: Host distribution "Ubuntu-18.04" has not been validated with this version of the build system; you may possibly experience unexpected failures. It is recommended that you use a tested distribution.
    WARNING: FPGA-server-1.0-r0 do_package_qa: QA Issue: /usr/bin/FPGA-server contained in package FPGA-server requires libc.so.6(GLIBC_2.4), but no providers found in RDEPENDS_FPGA-server? [file-rdeps]
    WARNING: FPGA-test-1.0-r0 do_package_qa: QA Issue: /usr/bin/FPGA-test contained in package FPGA-test requires libstdc++.so.6(CXXABI_1.3.8), but no providers found in RDEPENDS_FPGA-test? [file-rdeps]

Sometimes building will fail when configuring of the fsbl (first stage bootloader) takes too long. I think it needs to wait until all other sources are compiled. Petalinux gives an error which looks like it was running out of memory, but I believe its rather a timeout during configuring. When you build it a second time it will work without problems since the dependent sources are already compiled and the fsbl should configure and compile immediately. 

6. Package files for booting from SD card:

       petalinux-package --boot --force --fsbl images/linux/zynq_fsbl.elf --fpga images/linux/design_1_wrapper.bit --u-boot

Copy image.ub and BOOT.BIN from the /images/linux folder (not the pre-built folder) to the micro-SD card, ensure the server.config file with the proper IP address is as well on the SD card and if you have set the MAC address in petalinux-config you can remove the uEnv.txt file from the SD card.


### Using Petalinux:

These are the first steps if you want to add new functionality.

1. Add a new driver module (here dio24):

       petalinux-create -t modules -n dio24 --enable    // use lowercase only!
       petalinux-config -c rootfs                       // check if module is in list and enable module if not --enable
       petalinux-config -c kernel                       // exit without modifications. this might be needed for 1st module but not clear?

This will add a demonstration driver module to the project in the folder /project-spec/meta-user/recipes-modules.

2. Add a new C++ application (here FPGA-server):

       petalinux-create -t apps --template c++ -n FPGA-server --enable  // do not use '_' in names!
       petalinux-config -c rootfs                       // check if app is in list and enable if not --enable
 
This will add a hello-world demo application in the folder /project-spec/meta-user/recipes-apps. 
       
3. Add a startup script:
        
        petalinux-create -t apps --template install -n FPGA-init --enable
        petalinux-config -c rootfs                      // check if is in list of apps and enable if not --enable

This will add a demo install script in the folder /project-spec/meta-user/recipes-apps.


