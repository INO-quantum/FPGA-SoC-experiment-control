# FPGA firmware

This folder contains the source files needed for building the firmware for the Cora-Z7 board. The building process can be divided into two main steps: 

1. generate the hardware logic on the FPGA part using Vivado (2020.1)
2. generate the Linux image and software running on the CPU with Petalinux (2020.1)

These software tools are very heavy and not easy to use. First time compilation for each of the tools can take easily 10-15 minutes and for Petalinux several additional resources need to be downloaded from the internet. After the first successful compilation the compile time is reduced but at least 5 minutes per iteration makes debugging still very tedious.

Ready-to-use firmware files can be found in the [firmware-release folder](/firmware-release), select the folder corresponding to your FPGA-SoC board and the version of your buffer card and choose primary or secondary board.

## Hardware implementation

The Hardware logic is generated with Vivado 2020.1 from Xilinx running on Windows or Ubuntu[^1]. Vivado WebPACK can be downloaded for free and supports the Zynq 7000 series SoC devices from Xilinx which are used in this project. For instructions on how to install Vivado 2020.1 [see UG973 from Xilinx](https://docs.xilinx.com/v/u/2020.1-English/ug973-vivado-release-notes-install-license). See also the very good [tutorial from Digilent](https://digilent.com/reference/programmable-logic/guides/installing-vivado-and-vitis). For this project Vitis is not needed but for debugging it can be useful. During the installation ensure that support for the Zynq-7000 series devices is enabled since we will need this. I have tested Vivado on Windows and Linux and have not seen a big difference.

[^1]: Vivado and Petalinux 2020.1 officially support Ubuntu 18.04 LTS but I use Ubuntu 20.04 LTS without big problems.

> [!NOTE]
> Note that this project uses Petalinx 2020.1 which requires a Linux operating system. So even if Vivado is available on Windows you will need some Linux distribution to (cross-)compile this project.

On Windows you should have a shortcut on the desctop or enter `vivado` in the search box of the task bar. On Linux you need to launch Vivado from the terminal like this:

    cd <working folder>
    source /opt/Xilinx/Vivado/2020.1/settings64.sh
    export LC_ALL=C
    vivado

This assumes Vivado was installed in the standard location[^2]. Do not execute `vivado` in your home folder since it will contaminate it with temporary files. It is best to create a `work` folder for this purpose. The `export` command you can also add to `settings64.sh`, so you do not forget it. The `cd` command I do not recommend to add to the file since some scripts execute `settings64.sh` automatically and will end up in an unexpected folder. 

[^2]: I prefer to install Vivado and Petalinux in the home directory `~/Xilinx/Vivado/<version>` and `~/Xilinx/petalinux/<version>`. This way installation does not need `sudo` privilege.

> [!Note]
> By manually selecting the location of `settings64.sh` you can easily switch between different versions of Vivado. This might be needed since projects generated with one version usually make troubles when trying to use with another version.

After Vivado is installed you need to download and copy the [board files from Digilent](https://reference.digilentinc.com/vivado/installing-vivado/start#installing_digilent_board_files). Choose the Cora-Z7-07S or Cora-Z7-10 board, depending on which you have.


### Generate the Vivado project

This describes how to generate the .xsa file which Petalinux needs and contains the .bit file with the logic definition of the FPGA and the linux device tree. You find already generated .xsa files in the [xsa file folder](/firmware-source/2020.1/Vivado/xsa/) for your board.

1. copy the content of the [source file folder including the tcl script](/firmware-source/2020.1/Vivado/source/) to the location where you want the project to be created

2. open Vivado (or close any open project) and on the bottom in the `Tcl Console` execute the following commands selecting the tcl script file according to your FPGA board (xx = `10` or `07S`), the buffer board (yy = `v1.2`, `v1.3` or `v1.4`), and zzzz is the release date of the firmware (select the latest for your board):
```
cd <path to copied folder>
source ./ExpCtrl_Cora-Z7-xx_yy_zzzz.tcl  
```

3. wait until the new project is created in the folder. Vivado asks to select the top module: you can let it do it automatically, or select `design_1_wrapper.v` manually. Check on the bottom that in the `Tcl Console` there are no red entries. You can `Open Block Design` to get a graphical representation of the design blocks, the used I/O ports and the connections.

4. on the bottom of `Flow Navigator` select `Program and Debug` and click `Generate Bitstream`. This will generate the .bit file to describe the hardware logic. This takes some time (8'30s on my laptop) and after it finished you can check that in the `Messages` tab on the bottom there are no Critical Warnings. There will be about 190 Warnings which can be ignored in this case - but not always!

5. after the generation is finished Vivado is asking to `Open the Implemented Design` which you can `Abort` or click `Open` in case you want to see the utilized regions of the FPGA. It's quite packed: the projects use 68% of the lookup tables (logic cells), 53% of the flip flops (single-bit memory) and 76% of the block RAM. When the chip utilization gets too high the generation can take much longer since Vivado has to find routes for all signals and place cells without having many options to choose from. In this case it will be very difficult for Vivado to fulfill the timing constraints. The timing result you can see in the `Design Runs` tab on the bottom where nothing should be red: the most critical is WNS (worst negative slack) which should be positive and is usually around 1.8ns. All other times should be close to 0. In case of timing problems you can check the failed routes in the `Implemented Design`. There is also the `Constraint Wizard` which is sometimes useful to automatically fix unconstraint clock domain crossings which most of the time cause failed routes.

6. if all is ok, select `File` - `Export` - `Export Hardware` and leave the selection `Fixed` and click on `Next`, then change the selection to `Include Bitstream` and click `Next`, leave everything on default and click `Next` and `Finish`

7. after a few seconds Vivado has exported the file `design_1_wrapper.xsa` into the project folder. This is the file we need to give to Petalinux in the next step. I usually rename it to match the project name. Now you can close the project.

> [!NOTE]
> I could simplify the steps for creating the project with respect to the first release of this project with Vivado 2017.4. There I have "packaged" the main IP (dio24.v) which, apart of complicating the compilation steps, caused also that Vivado crashing randomly (on Windows and on Ubuntu) and several times even messed up the entire project rendering it unusable. Now I include the IP as RTL module (in the Block Diagram context menu select `Add Module` instead of `Add IP`) which makes the definition of interfaces less controllable but is easier to maintain and so far Vivado (2020.1) crashed only once.
  
### Modify the Vivado project

In the open project click `Open Block Design`. Here you can add existing IP blocks, rearrange connections and customize blocks by double-clicking them. Most likely, you want to modify the [Verilog source files](/firmware-source/Vivado/source). You can open them from the `Sources` tab or with an external text editor. Vivado will recognize when a source has changed. If you want to add new files you have to add them in the `Sources` tab, otherwise Vivado will not find them. To regenerate the design click on `Generate Bitstream`. Check that the timing (WNS and others) are not red and that in the `Messages` tab there are no Critical Warnings or Errors. Normal Warnings can be often ignored but one still has to check them since they can be an indicator of problems. When you are finished click `File` - `Export` - `Export Hardware` to export the .xsa file as described in the section before. 

If you want to generate the firmware for another buffer board, you have to enable the corresponding .xdc file in the `Sources` tab, constraints section, and change differential vs. single-ended clock:

1. The project contains the constraints files (port layout and timing) for all three buffer board versions. You will find two of the files gray, i.e. disabled. Right-click the file for the board you want to enable and select `Enable File` and ensure to `Disable File` the previously enabled file. 

2. Buffer board version v1.4 uses a differential input clock while the older version v1.2 and v1.3 use a single-ended clock input. Therefore, to switch from or to board version v1.4 you need to setup or remove the differential clock input. In the Block Design find the Clock Wizard "clk_wiz_0" and double-click on it and select "Clocking Options" and on the right bottom (you might need to scroll horizontally) you can choose between "Differential clock capable pin" (v1.4) and "Single ended clock capable pin" (v1.2 and v1.3). After you have changed this, check that "Input Frequency (MHz)" is still set to 10.0, i.e. 10MHz and click "OK". 

* For the new board version v1.2 or v1.3 select `clk_in_1` and right-click and select `Make External` and delete the two ports `clk_in1_n_0` and `clk_in1_p_0`.
 
* For the new board version v1.4 click the `+` symbol near the `CLK_IN1_D` port (vertical two lines `||`) and select one of the two pins and `Make External`. Do the same for the other pin. Delete the remaining `clk_in1_0` port from the previous design.

3. This step is optional but when you change the buffer board version you should also change the content of the `Version` register: In the Block Design double-click on the `dio24_0` module and scroll down to the `Version` entry. This is a hexadecimal number where the upper four digits represent the board version: `0x0102` is v1.2, `0x0103` is v1.3 and `0x0104` is v1.4. Change this entry accordingly leaving the remaining 4 digits as they were - they represent the date of the firmware. Click "OK" when finished.

4. Now you can regenerate the .xsa file as described above. If it gives an error look in the `Messages` tab what is the reason. Most likely the name of one of the ports is wrong. Open the selected constraint .xdc file and search for `clk_in` and give the ports on the Block Diagram the exact same name as in the .xdc (or vice versa). The port name can be changed by changing the `Name` entry in `External Port Properties`. 

> [!NOTE]
> I am in the process of updating this page. The information below is not anymore up-to-date ...

## Software implementation

Petalinux is a simple Linux distribution which allows to run an embedded Linux operating system on the CPU. The original board support package (.bsp) and demos are from [Digilent](https://reference.digilentinc.com/reference/software/petalinux/start) and require Petalinux 2017.4 installed on a Linux operating system. The present project works with Vivado and Petalinux 2020.1 on Ubuntu 20.04 LTS[^1]. For the installation of Petalinux 2020.1 please consult the [Petalinux Tools guide from Xilinx](https://docs.xilinx.com/v/u/2020.1-English/ug1144-petalinux-tools-reference-guide). More condensed information (probably not anymore fully up-to-date) can be obtained also from the [Cora-Z7-07S Petalinux BSP Project from Digilent](https://github.com/Digilent/Petalinux-Cora-Z7-07S/blob/master/README.md). The guides use the recommended installation folder /opt/pkg/petalinux[^2].

### Generate Project

We are still following the guide from before, but instead of using the Digilent bsp (which was the original bsp of my project), we use our project bsp (Petalinux-Cora-Z7-yy-20xx.x-0.bsp for your board with yy="10" or "07S") which you copy onto your computer, open a console and cd to a folder where you want the project to be located and create the project:

    cd path-to-folder-where-new-project-should-be-created
    source path-to-petalinux-installation-folder/settings.sh
    petalinux-create -t project -s path/Petalinux-Cora-Z7-yy-20xx.x-x.bsp

### Using the pre-built images

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

### Compiling the Petalinux project

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

Sometimes building will fail when configuring of the fsbl (first stage bootloader) takes too long. I think it needs to wait until all other sources are compiled. Petalinux gives an error which looks like it was running out of memory, but I believe its rather a timeout during configuring? When you build it a second time it will work without problems since the dependent sources are already compiled and the fsbl should configure and compile immediately. 

6. Package files for booting from SD card:

       petalinux-package --boot --force --fsbl images/linux/zynq_fsbl.elf --fpga images/linux/design_1_wrapper.bit --u-boot

Copy image.ub and BOOT.BIN from the /images/linux folder (not the pre-built folder) to the micro-SD card, ensure the server.config file with the proper IP address is as well on the SD card and if you have set the MAC address in petalinux-config you can remove the uEnv.txt file from the SD card.


### Using Petalinux

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


