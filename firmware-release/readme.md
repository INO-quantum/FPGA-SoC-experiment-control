# firmware-release

The folders contain the firmware files needed to be saved on the SD card of each FPGA board.

The folders are named by FPGA-boad version ("Cora-Z7-10" or "Cora-Z7-07S"), buffer board version ("v1.2", "v1.3", "v1.4"), and "primary" and "secondary" board and firmware release date. 

Choose the latest firmware for your FPGA board (sticker on FPGA chip indicates "10" or "07S") and buffer board version (written on PCB). 

If you are using a single board choose "primary", otherwise you have to define one board as "primary" and all other boards as "secondary". In the default configuration the primary board provides the clock ("clock out") to the secondary boards ("clock in") and a start trigger signal ("trig out" or "sync cout") to the secondary boards ("trig in" or "sync in"). Note that the secondary board "clock in" resistor network has to be adjusted for "LVPECL" input in order to use the clock of the primary board. The primary board "clock in" can be configured to your needs as "LVPECL" or "sine-wave" input (see board schematics).

Each folder contains 3-4 files: BOOT.BIN is the bootloader and contains the logic description file for the FPGA. image.ub is the Linux image which the bootloader loads. server.config is a custom text file used to configure the the server and timings of the board. Edit this file in order to change the IP address and if you need to fine-tune the synchronization of the boards. For Vivado/Petalinux 2020.1 and newer there is a fourth file boot.scr which is the boot script of the second-stage bootloader (U-boot).

The default IP addresses of the primary boards for buffer board version v1.2, v1.3 and v1.4 are: 192.168.1.120, 192.168.1.130 and 192.168.140. The IP address of the secondary boards is just incrementing the last digit, i.e. 1 for the first secondary, 2 for the second, etc. If you have connection problems verify that "ping <IP address>" does not report loss of data for any of your boards. Note that you cannot use the same firmware for different boards! This gives random connection problems since two boards have the same MAC address. If you need more than one secondary board please contact me or recompile the firmware with Petalinux where with "petalinux -config" you can configure the MAC address.

I am currently in the process of regenerating all versions with Vivado/Petalinux 2020.1. If you do not find your version in the list or you need more help please contact me.


