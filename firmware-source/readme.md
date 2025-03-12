# FPGA firmware

This folder contains the source files needed for building the firmware for the Cora-Z7 board. The building process can be divided into two main steps: 

1. Generate the hardware logic on the FPGA part using Vivado (2020.1)
2. Generate the Linux image and software running on the CPU with Petalinux (2020.1)

The used software tools are heavy, not user-friendly and buggy. First time compilation for each of the tools can take 10-15 minutes and for Petalinux several additional resources need to be downloaded from the internet. After the first successful compilation the compile time is reduced but 5-10 minutes per iteration makes debugging still very tedious.

Ready-to-use firmware files can be found in the [firmware-release folder](/firmware-release): select the folder corresponding to your FPGA-SoC board and the version of your buffer card and choose primary or secondary board.

## Hardware implementation

The Hardware logic is generated with Vivado 2020.1 from Xilinx running on Windows or Ubuntu[^1]. Vivado WebPACK can be downloaded free of charge (after registering) and supports the Zynq-7000 series SoC devices from Xilinx which are used in this project. For instructions on how to install Vivado 2020.1 [see UG973 from Xilinx](https://docs.xilinx.com/v/u/2020.1-English/ug973-vivado-release-notes-install-license). See also the very good [tutorial from Digilent](https://digilent.com/reference/programmable-logic/guides/installing-vivado-and-vitis). The installation file size is huge which is a problem when you need to install several versions of Vivado or running Linux in a virtual environment. For this project `Vitis` is not needed but for debugging it can be useful. During the installation ensure that support for the Zynq-7000 series devices is enabled. I have tested Vivado on Windows and Linux and have not seen a big difference.

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

1. Copy the content of the [source file folder including the tcl script](/firmware-source/2020.1/Vivado/source/) to the location where you want the project to be created

2. Open Vivado (or close any open project) and on the bottom in the `Tcl Console` execute the following commands selecting the tcl script file according to your FPGA board (xx = `10` or `07S`), the buffer board (yy = `v1.2`, `v1.3` or `v1.4`), and zzzz is the release date of the firmware (select the latest for your board):
```
cd <path to copied folder>
source ./ExpCtrl_Cora-Z7-xx_yy_zzzz.tcl  
```

3. Wait until the new project is created in the folder. Vivado asks to select the top module: automatic selection should work, or select `design_1_wrapper.v` manually. Check on the bottom that in the `Tcl Console` there are no red entries. You can `Open Block Design` to get a graphical representation of the design blocks, the used I/O ports and the connections.

4. On the bottom of `Flow Navigator` select `Program and Debug` and click `Generate Bitstream`. This will generate the .bit file to describe the hardware logic. The first time this can takes some minutes (8'30s on my laptop) and after it finished you can check that in the `Messages` tab on the bottom there are no Critical Warnings. There will be about 190 Warnings which can be ignored in this case - but not always!

5. Vivado is asking to `Open the Implemented Design` which you can `Abort` or click `Open` in case you want to see the utilized regions of the FPGA. It's quite packed: the project uses 68% of the lookup tables (logic cells), 53% of the flip flops (single-bit memory) and 76% of the block RAM. When the chip utilization gets too high the generation can take much longer since Vivado has to find routes for all signals and place cells without having many options to choose from. In this case it will be very difficult for Vivado to fulfill the timing constraints. The timing result you can see in the `Design Runs` tab on the bottom where nothing should be red: the most critical is WNS (worst negative slack) which should be positive and is usually around 1.8ns. All other times should be close to 0. In case of timing problems you can check the failed routes in the `Implemented Design`. There is also the `Constraint Wizard` which is sometimes useful to automatically fix unconstraint clock domain crossings which most of the time cause failed routes.

6. If all is ok, select `File` - `Export` - `Export Hardware` and leave the selection `Fixed` and click on `Next`, then change the selection to `Include Bitstream` and click `Next`, leave everything on default and click `Next` and `Finish`

7. After a few seconds Vivado has exported the file `design_1_wrapper.xsa` into the project folder. This is the file we need to give to Petalinux in the next step. I usually rename it to match the project name. The .xsa files for the different boards you find [here](/firmware-source/2020.1/Vivado/xsa/). Now you can close the project.

> [!NOTE]
> I could simplify the steps for creating the project with respect to the first release of this project with Vivado 2017.4. There I have "packaged" the main IP (dio24.v) which, apart of complicating the compilation steps, caused also that Vivado crashing randomly (on Windows and on Ubuntu) and several times even messed up the entire project rendering it unusable. Now I include the IP as RTL module (in the Block Diagram context menu select `Add Module` instead of `Add IP`) which makes the definition of interfaces less controllable but is easier to maintain and so far Vivado (2020.1) crashed significantly less often (during simulation still happens).
  
### Modify the Vivado project

In the open project click `Open Block Design`. Here you can add existing IP blocks, rearrange connections and customize blocks by double-clicking them. Most likely, you want to modify the [Verilog source files](/firmware-source/Vivado/source). You can open them from the `Sources` tab or with an external text editor. Vivado will recognize when a source has changed. If you want to add new files you have to add them in the `Sources` tab, otherwise Vivado will not find them. To regenerate the design click on `Generate Bitstream`. Check that the timing (WNS and others) are not red and that in the `Messages` tab there are no Critical Warnings or Errors. Normal Warnings can be often ignored but one still has to check them since they can be an indicator of problems. When you are finished click `File` - `Export` - `Export Hardware` to export the .xsa file as described in the section before. 

If you want to generate the firmware for another buffer board, you have to enable the corresponding .xdc file in the `Sources` tab, constraints section, and for/to buffer board version v1.4 you have to change differential/single-ended clock input:

1. The project contains the constraints files (port layout and timing) for all three buffer board versions. You will find two of the files gray, i.e. disabled. Right-click the file for the board you want to enable and select `Enable File` and for the previously enabled file select `Disable File`. 

2. The buffer board version v1.4 uses a differential input clock while the older version v1.2 and v1.3 use a single-ended clock input. Therefore, to switch from or to board version v1.4 you need to setup or remove the differential clock input. In the Block Design find the Clock Wizard "clk_wiz_0" and double-click on it and select "Clocking Options" and on the right bottom (you might need to scroll horizontally) you can choose between "Differential clock capable pin" (v1.4) and "Single ended clock capable pin" (v1.2 and v1.3). After you have changed this, check that "Input Frequency (MHz)" is still set to 10.0, i.e. 10MHz and click "OK". 

* For the new board version v1.2 or v1.3 select the port `clk_in1` of the Clock Wizard block and right-click and select `Make External`. Delete the two ports `clk_in1_n_0` and `clk_in1_p_0`. Click on the new external input `clk_in1_0` and check that in the `External Port Properties` the frequency is set to 10MHz, otherwise set it to this frequency.
 
* For the new board version v1.4 click the `+` symbol near the `CLK_IN1_D` port (vertical two lines `||`) of the Clock Wizard block and select one of the two pins and `Make External`. Do the same for the other pin. Delete the remaining `clk_in1_0` port from the previous design. Click on the new external input `clk_in1_n_0` or `clk_in1_p_0` and check that in the `External Port Properties` the frequency is set to 10MHz, otherwise set it to this frequency.

3. This step is optional but when you change the buffer board version you should also change the content of the `Version` register: In the Block Design double-click on the `dio24_0` module and scroll down to the `Version` entry. This is a hexadecimal number where the first four digits represent the board version: `0x0102` is v1.2, `0x0103` is v1.3 and `0x0104` is v1.4. Change this entry accordingly leaving the remaining 4 digits as they were - they represent the date of the firmware. Click "OK" when finished.

4. Now you can regenerate the .xsa file as described above. If it gives an error look in the `Messages` tab what is the reason. Most likely the name of one of the ports is wrong. Open the selected constraint .xdc file and search for `clk_in` and give the ports on the Block Diagram the exact same name as in the .xdc (or vice versa). The port name can be changed by changing the `Name` entry in `External Port Properties`. 


> [!Note]
> If you have created the project using the tcl scripts, then modifying the top design might create an error that design_1_wrapper.v uses external ports which should have been deleted. This is a known bug in Vivado 2020.1 where modifications in design_1.bd are not automatically updated in design_1_wrapper.v. In this case you need (1) to create a new HDL wrapper and afterwards (2) disable and then (3) delete the old design_1_wrapper.v. The reason is that design_1_wrapper.v is copied by the tcl script into the wrong folder (`<project>/sources_1/imports/hdl/` instead of `<project>/sources_1/bd/design_1/hdl/`). My latest tcl's should not have this problem, but the older ones might require this manual fix. In case of problems let me know.


## Software implementation

Petalinux is a simple Linux distribution which allows to run an embedded Linux operating system on the CPU part of the FPGA-SoC chip. The original board support package (.bsp) and demos are from [Digilent](https://reference.digilentinc.com/reference/software/petalinux/start) and require Petalinux 2017.4 installed on a Linux operating system (can be a virtual environment). The present project works with Vivado and Petalinux 2020.1 on Ubuntu 20.04 LTS[^1]. For the installation of Petalinux 2020.1 please consult the [Petalinux Tools guide from Xilinx](https://docs.xilinx.com/v/u/2020.1-English/ug1144-petalinux-tools-reference-guide). More condensed information (maybe not fully up-to-date) can be obtained from [Cora-Z7-07S Petalinux BSP Project from Digilent](https://github.com/Digilent/Petalinux-Cora-Z7-07S/blob/master/README.md). The guides use the recommended installation folder /opt/pkg/petalinux[^2].

The generated [.xsa files from Vivado](/firmware-source/2020.1/Vivado/xsa/) contain the bitstream (.bit) which the bootloader is uploading on the FPGA part and the device tree used by Petalinux to define external devices which can then be accessed by user-defined application software. 

Below you find how to create and compile the Petalinux project and generate the firmware files. Already compiled files you find in the [firmware release folder](/firmware-release/) for the different FPGA boards, buffer board versions and for primary and secondary boards.

### Generate the Petalinux Project

1. From the [Petalinux directory](/firmware-source/2020.1/Petalinux) copy the file ExpCtrl-Cora-Z7-yy-v1.4_zzzz.bsp for your board (yy="10" or "07S" and zzzz=release date), open a console and `cd` to a folder where you want the project to be located and create the project:

        cd <path-to-folder-where-new-project-should-be-created>
        source <path-to-petalinux-installation-folder>/settings.sh
        petalinux-create -t project -s <path to bsp file>/ExpCtrl-Cora-Z7-yy-v1.4_zzzz.bsp

This creates the project folder ExpCtrl-Cora-Z7-yy-v1.4_zzzz in the current directy. When this does not give an error, you can skip steps 2-4, and proceed directly to [Compiling the Petalinux project](/firmware-source#Compiling-the-Petalinux-project).

> [!NOTE]
> After the project is created you cannot move or rename the project folder! Any attempt of compilation will break the project in a non-revertible way.

2. The project generation from the bsp file might fail when the petalinux version is different from the version with which the bsp was created. In this case one can create a new project using the `zynq` template but additional configuration steps are required:

        petalinux-create -t project -n ExpCtrl-Cora-Z7-yy-v1.4_zzzz --template zynq
        petalinux-config --get-hw-description=./
        petalinux-config -c kernel
        petalinux-config -c rootfs
        petalinix-config -c u-boot
    
The first `petalinux-config` is to select the .xsa file (see [next section 4](/firmware-source#Compiling-the-Petalinux-project)) and in the menu one should first set the Ethernet MAC address (see [next section 2](/firmware-source#Compiling-the-Petalinux-project)) and one can optionally set the location of the kernel source (see [next section 3](/firmware-source#Compiling-the-Petalinux-project)). 

In the kernel configuration one has to disable the Xilinx DMA driver: Navigate to `Device Drivers` and disable `Multimedia support` by pressing the space key (this disables `Xilinx Video IP`) and go inside `Graphics support` and disable `Xilinx DRM KMS Driver`. Finally, disable the entire `DMA Engine support` (disables `DMA API driver Driver for PL330`, `Xilinx AXI DMAS engine`, `Xilinx DMA engines`, `Xilinx Framebuffer`). Optionally, you can also disable: `PCI support`, `Sound card support`, `Real Time clock`, and `Xilinx AXI Performance Monitor driver` within `Userspace I/O driver`.

The rootfs (root file system) configuration allows to remove further unneccessary components from the image file: In `Filesystem Packages` one can disable everything not needed and in `Petalinux Package Groups` and `Image Features` and `user packages` nothing should be selected. In `apps` only `fpga-init`, `fpga-server` and `fpga-test`, and in `modules` only `dio24` should be selected (they will appear here only after they have been created; see [4. Create device driver and applications](/firmware-source#Generate-the-Petalinux-Project)) and disable eventual selected default applications (`gpio-demo` and `peekpoke`).

The configuration of u-boot is optional. I do not change anything there, but it fails when the next step ([3. Update the device tree](/firmware-source#Generate-the-Petalinux-Project)) is not done.

3. Update the device-tree:

Replace the file `<project folder>/project-spec/meta-user/recipes-bsp/device-tree/files/system-user.dtsi` with the one [provided here](/firmware-source/2020.1/Petalinux/project-spec/meta-user/recipes-bsp/device-tree/files/system-user.dtsi). Ensure that in the replaced file the second CPU is removed (present) for the Cora-Z7-07S (Cora-Z7-10) board (see comments in system-user.dtsi and [Change FPGA board version below](/firmware-source#Change-FPGA-board-version)). After this step `petalinux-config -c u-boot` should execute without error.

4. Create device driver and applications:

Now you can proceed to create the device driver (`dio24`) and the three applications (`fpga-server`, `fpga-test` and `fpga-init`) - see [sections 1-3. in Modifying the project](/firmware-source#Modifying-the-project) below. After this, check that with `petalinux-config -c rootfs` the applications are enabled.

Now you have the new project ready for [Compiling the Petalinux project](/firmware-source#Compiling-the-Petalinux-project).

### Compiling the Petalinux project

1. For compiling the Petalinux project `cd` into the project folder and source petalinux (if not already done):

        cd <path-to-project-folder>
        source <petalinux-folder>/settings.sh
    
2. For a new project you must set the Ethernet MAC address to the one given on the sticker of the board:

If several boards in the experiment have the same Ethernet MAC address the communication will not work properly. In the provided firmware folder I use standard distinct MAC addresses for different boards. This is the reason for having different firmware files for each primary and secondary boards.

        petalinux-config
        navigate to "Subsystem AUTO Hardware Settings" - "Ethernet Settings" - "Ethernet MAC address"
        edit MAC address to the one given on sticker of the board
        exit from all sub-menus and from configuration menu and select to save new configuration
       
In the next menu "Obtain IP address automatically" one can disable automatic IP address assignment by a DHCP server and set a static IP. But keep it selected, since this can be changed easier in the server.config file without recompiling.
  
3. Set Linux Kernel Source (optional):

This is useful if you have several projects, otherwise Petalinux will download it automatically for each project. 
    
        petalinux-config
        select "Linux Component Selection"
        in "linux-kernel" select "ext-local-src"
        in "External linux-kernel local source settings" enter folder as "/home/<user name>/<path-to-folder>"
        leave "External linux-kernel license checksum" empty
        download Kernel source into the selected folder and extract it

It should be possible using a relative path, but I could not get it working. The project currently uses the [5.4 Linux kernel for petalinux 2020.1](https://github.com/Xilinx/linux-xlnx/releases/tag/xlnx_rebase_v5.4_2020.1). In the same way you can also select a local source for the first-stage-bootloader (FSB) and the linux bootloader (u-boot) but since they are small they can be downloaded automatically when building the project the first time.

<!-- 
https://github.com/Xilinx/linux-xlnx/releases/tag/xilinx-v2020.1
https://github.com/Xilinx/linux-xlnx/releases/tag/xilinx-v2017.4 
-->

4. To select a new .xsa file generated with Vivado:

Copy the .xsa file generated by Vivado [see above](/firmware-source#generate-the-vivado-project) into the Petalinux project folder and type:

        petalinux-config --get-hw-description=./
        exit from configuration menu

This assumes that only one .xsa file is in the project folder. Alternatively, you can also give the file name and path after the '='.

5. Compile the project:

        petalinux-build
    
For the first time this will download the linux kernel (if not selected from local folder) and FSBL (first-stage bootloader) source and u-boot (linux bootloader source) and compilation will need some time (9 minutes on my laptop[^3]). The warnings related to the non-official Ubuntu version can be ignored. In the "Tasks Summary" output it should say "all succeeded" and no red messages should appear. Sometimes compilation fails, which is either a timeout (first-stage booloader config after 3 minutes waiting for other tasks to finish) or low memory (are you running in a virual environment?) when many tasks run in parallel. Just compile again and it should work.

[^3]: Recently, downloading of `qemu-xilinx-native` is extremely slow and can prolong the first compile time significantly (40 minutes!). This might even fail and one has to retry compilation, maybe at a later time, since disabling `qemu-xilinx-native` is not working according to online resources (I have not tried).

6. Package files for booting from SD card:

        petalinux-package --boot --force --fsbl images/linux/zynq_fsbl.elf --fpga images/linux/system.bit --u-boot

Copy the files image.ub, BOOT.BIN and boot.scr from <project folder>/images/linux to the micro-SD card. You need also the server.config file with the proper IP address and other settings. See the folder with the [compiled firmware files](/firmware-release) for your board.

### Change buffer board version

In order to change the buffer board version you just need to give a proper .xsa file to Petalinux and recompile:

        petalinux-config --get-hw-description=<path to xsa file>        // or './' instead of path
        petalinux-build
        petalinux-package --boot --force --fsbl images/linux/zynq_fsbl.elf --fpga images/linux/system.bit --u-boot
        
The same steps are needed after creating a new .xsa file with Vivado.

### Change FPGA board version

In the [Petalinux folder](/firmware-source/2020.1/Petalinux) I provide already the `bsp` to create the project for the different FPGA boards. It is however easy to switch between the boards also in the project. First you have to edit the `system-user.dtsi` file in the folder `<project folder>/projet-spec/meta-user/recipes-bsp/device-tree/files` in order to tell Petalinux if the second CPU core is present or not. For the `Cora-Z7-10` comment (using `/**/` and not `//`) the following entry, or uncomment it for the `Cora-Z7-07S` board:
        
        &amba {
	        ptm@f889d000 {
		        cpu = <&cpu0>;
	        };
        };

After this change, select the .xsa file for the proper board and recompile and package as described in [sections 4-6 in Compiling the Petalinux project](/firmware-source#Compiling-the-Petalinux-project).

### Modifying the project

These are the steps if you want to add new functionality or when you have to [create the device driver and applications without bsp file](/firmware-source#Generate-the-Petalinux-Project). Execute these commands inside the project folder (except of packaging) and after sourcing petalinux. To re-create the device driver and applications from the project without bsp file, just replace the folders generated here with the ones provided in the [firmware source](/firmware-source/2020.1/Petalinux/project-spec/meta-user). The exact location is indicated below.

1. Add a new driver module (we use `dio24`):

        petalinux-create -t modules -n dio24 --enable    // use lowercase letters and do not use '_'
        petalinux-config -c rootfs                       // check if module is in list and enable module if not --enable

This will add a driver template module to the project in the folder `/project-spec/meta-user/recipes-modules` which you can modify. 

The project uses the `dio24` kernel module driver which manages three devices in the FPGA part: the experiment control logic, the DMA module (direct-memory-access which transmits data from and to external memory) and the analog-to-digital conversion used to read the temperature of the FPGA-SoC. To re-create the driver replace the `dio24` folder with the [dio24 source](/firmware-source/2020.1/Petalinux/project-spec/meta-user/recipes-modules/dio24). 

2. Add a new C++ application (we use `fpga-server` and the same for `fpga-test`):

        petalinux-create -t apps --template c++ -n fpga-server --enable  // use lowercase letters and do not use '_'
        petalinux-config -c rootfs                       // check if app is in list and enable if not --enable
 
This will add a hello-world application in the folder /project-spec/meta-user/recipes-apps which you can modify. 

The project uses two C++ applications: fpga-server which communicates via Ethernet with the control computer and fpga-test which is used for testing (optional; requires console access, see [In case of problems](/firmware-source#In-case-of-problems)). To re-create the server replace the `fpga-server` folder with the [server source](/firmware-source/2020.1/Petalinux/project-spec/meta-user/recipes-apps/fpga-server). The `fpga-test` folder can be found [here](/firmware-source/2020.1/Petalinux/project-spec/meta-user/recipes-apps/fpga-test). 
       
3. Add a startup script (here `fpga-init`):
        
        petalinux-create -t apps --template install -n fpga-init --enable   // use lowercase letters and do not use '_'
        petalinux-config -c rootfs                      // check if is in list of apps and enable if not --enable

This will add a demo startup script in the folder /project-spec/meta-user/recipes-apps which you can modify.

The project uses the startup script `fpga-init` which reads the `server.config` file from the SD card and launches the `fpga-server` application giving it all configuration options. To re-create the startup script replace the `fpga-init` folder with the [startup script source](/firmware-source/2020.1/Petalinux/project-spec/meta-user/recipes-apps/fpga-init).

4. Configure kernel, root file system (rootfs) and boot loader (u-boot):

        petalinux-config -c kernel
        petalinux-config -c rootfs
        petalinux-config -c u-boot
        
Each of these commands opens a configuration menu where you can change the settings of each of the components. See also notes in section [Generate the Petalinux Project](/firmware-source#Generate-the-Petalinux-Project). 

5. Package a project as bsp:

        petalinux-build -x distclean        // clean project
        peatlinux-build -x mrproper         // optional: delete entire workspace. attention: you have to recompile everything! 
        cd <location where bsp should be generated>
        petalinux-package --bsp -p <project folder> --hwsource <path to and name of xsa> --exclude-workspace --output <file name of .bsp>
        
### In case of problems

- Don't panic! This is normal for such an involved project which depends on many components. You will for sure encounter problems when you try to use different versions of Vivado/Petalinux or when you try on a different operation system - especially on a not recommonded one. Vivado and Petalinux in general must have the same version. At present I use Vivado/Petalinux 2020.1, the original project was with 2017.4. Newer versions would be preferred but fixing all the problems after migrating to newer versions takes some time. Additionally, I have serveral projects using the RedPitaya board which requires Vivado 2020.1.
- Check the board is powered (red LED is on) and power is stable - especially during booting. If using a wall-plug be absolutely sure it gives 5V DC. Steady-state current is 0.3A but during booting it might be higher. A supply with 1A is recommended.
- There are two jumpers on the board, one for the power supply (near the jack) needs to be set to EXT or USB depending if you power from the jack (2.1-2.5mm center-positive) or via the USB plug. The second jumper should be shortened in order to boot from SD card.
- About 1s after switching on the power a yellow or green LED should switch on in addtion to the red power LED. This indicates the bitstream was written to the FPGA part. If this is not the case then either the SD card is not properly inserted or corrupt, or the bitstream is for a different board. Check that the sticker on the FPGA-SoC chip reads "10" for the Cora-Z7-10 board or "7S" for the Cora-Z7-07S board and choose the proper firmware for the board. I had problems with low-quality SD cards which broke after only one month of usage although the board only reads the SD card and does not write (user software can also write to it when needed).
- For debugging one can connect a micro-USB cable on the board and monitor in the console the boot process and navigate in the file system: I use `minicom` (any other terminal program should work) with 115200/8/N/1 settings and Hardware flow control disabled. The board appears usally as `ttyUSB1` (and `ttyUSB3` when a second board should be monitored on the same computer). When a terminal program is connected, sometimes the board boots accidently into the `Zynq>` console, then enter: `boot` or push the `SRST` button and the board should boot again. After booting is completed enter as user `root` and password `root` to navigate in the linux file system. 
- In the console you should see an output as below during booting. You can use also `dmesg` to output the kernel log file which can be very valuable, but it contains only the driver entries, i.e. the `fpga-init`, `FPGA-master` and `FPGA-server` entries are missing. In case the board is booting but the `dma24` driver is not associated as DMA driver, then you should see in the boot log that a `Xilinx DMA/DMAS/PL330` device driver was loaded instead. In order to deactivate them use `petalinux-config -c kernel`, see [Generate the Petalinux Project, section 2](/firmware-source#Generate-the-Petalinux-Project) for details what to disable. Ensure also that in `petalinux-config -c rootfs`, section `apps` has `fpga-init`, `fpga-server` and `fpga-test` enabled, and section `modules` has `dio24` enabled. After rebooting (you can type `reboot` in the console) check that none of the Xilinx DMA drivers appear in the boot log and that the `dio24` driver is mapped on 3 devices (dma24, dio24, xadc_wiz) and 3 irq's (2x for dma24, 1x for dio24 and none for xadc_wiz) as in the following output:

```
dio24: loading out-of-tree module taints kernel.
DIOdrv Linux kernel module for Cora-Z7-10 FPGA by Andi
DIOdrv registering dio24dev char device (246) ok
DIOdrv registering dma24dev char device (245) ok
DIOdrv pid 83 (udevd) device probing ... (matched)
DIOdrv get 2 irqs dma24 device...
dio24 40400000.dma: @ 0x40400000 mapped 0xE0A70000, irq=45/46
DIOdrv ok dma24 device probing
DIOdrv pid 83 (udevd) device probing ... (matched)
DIOdrv get 1 irqs dio24 device...
dio24 43c00000.dio24: @ 0x43C00000 mapped 0xE0A90000, irq=47
DIOdrv ok dio24 device probing
DIOdrv pid 83 (udevd) device probing ... (matched)
DIOdrv get 0 irqs XADC device...
dio24 43c10000.xadc_wiz: @ 0x43C10000 mapped 0xE0AB0000, irq=<none>
DIOdrv reading reg ...
DIOdrv update status ...
DIOdrv update status ok
DIOdrv ok XADC device probing
DIOdrv registering driver dio24 ok
DIOdrv char-device dio24dev (246) registered ok
DIOdrv char-device dma24dev (245) registered ok
DIOhlp pid 146 (dio24helper) waiting for IRQ ...

...

fpga-init v1.1 by Andi
fpga-init: mounting SD card on /mnt/sd/
fpga-init: info     = Cora-Z7-07S v1.3 prim. 192.168.1.130 (IBK)
fpga-init: IP       = 192.168.1.130 (static)
fpga-init: netmask  = 255.255.255.0 (set by server)
fpga-init: port     = <default>
fpga-init: clk_div  = 100
fpga-init: ctrl_in  = [0x0,0x0]
fpga-init: ctrl_out = [0x26482,0x848e]
fpga-init: strobe 0 = 30:40:30:1
fpga-init: strobe 1 = 29:40:31:1
fpga-init: primary  = 1
fpga-init: CPUs     = 1
fpga-init: wait     = 0
fpga-init: phase    = <default>
fpga-init: unmounting SD card
fpga-init: create dio24dev device node (247)
fpga-init: create dma24dev device node (246)
fpga-init: starting fpga-server ...
fpga-init: done

...

FPGA server v1.0 by Andi
FPGA-master: ctrl_in = [0x0,0x0]
FPGA-master: ctrl_out = [0x26482,0x848e]
FPGA-master: number CPU 1
FPGA-master: sync wait time 0
FPGA-master: sync phase 0x0
FPGA-master: strobe delay 0x441d451e
actual flags 0x1002 (need 0x1)
FPGA-master:  'eth0' not ready ...
get IP (1) failed. flags = 0x1003, errno = 99 (ok with DHCP)
new    flags 0x1003 (ok), IP '192.168.1.130'
FPGA-master: 'eth0' ready and IP '192.168.1.130' set ok.
FPGA-master: start server ...
FPGA-master: server is starting ...
FPGA-server: listening at localhost:49701
FPGA-server: set_div 100 ok
FPGA-server: set strobe delay 0x441d451e ok
FPGA-server: set wait time 0 ok
FPGA-server: OUT_CONFIG actual config f08070 (0)
FPGA-server: set ctrl_in/out 0x0/0/26482/848e (ok)
FPGA-server: startup ok.
FPGA-master: server start succeeded
FPGA-master: connection to localhost:49701 ok (port 41048)

master: hit <ESC> or 'X' to shutdown server ...

FPGA-server: 127.0.0.1:41048 connected (local)

```


