# firmware-release

The folders contain the firmware files needed to be saved on the SD card of each FPGA board.

The folders are named by FPGA-boad version ("Cora-Z7-10" or "Cora-Z7-07S"), buffer board version ("v1.2", "v1.3", "v1.4"), "prim" and "sec" for primary and secondary board and firmware release date. 

Choose the latest firmware for your FPGA board (sticker on FPGA chip indicates "10" or "7S") and buffer board version (written on PCB). 

If you are using a single board choose "primary", otherwise you have to define one board as "primary" and all other boards as "secondary". In the default configuration the primary board provides the clock ("clock out") to the secondary boards ("clock in") and a start trigger signal ("trig out" or "sync cout") to the secondary boards ("trig in" or "sync in"). Note, that the secondary board "clock in" resistor network has to be adjusted for "LVPECL" input in order to use the clock of the primary board. The primary board "clock in" can be configured to your needs as "LVPECL" or "sine-wave" input. [See buffer board schematics](https://github.com/INO-quantum/FPGA-SoC-experiment-control/tree/main/buffer-card).

Each folder contains 4 files: BOOT.BIN is the bootloader and includes the logic description file for the FPGA. boot.scr is the script for the second stage bootloader (u-boot). image.ub is the Linux image which the second stage bootloader loads. server.config is a custom text file used to configure the server and timings of the board. Edit this file in order to use a static IP address (default uses DHCP) and if you need to fine-tune the synchronization of the boards.

>[!NOTE]
> You cannot use the same firmware for different boards since each board must have its unique Ethernet MAC address. This is hard-coded in the firmware. You might experience random connection problems when two boards have the same MAC address. If you need more than one secondary board, or if you experience problems please contact me.


## Florence

This folder contains the releases for the Florence and Trieste designs.

## Innsbruck

This folder contains the releases for the Innsbruck design which is similar but not identical to the Florence design. The [development folder](https://github.com/INO-quantum/FPGA-SoC-experiment-control/tree/main/development) contains the newer version but which is still not completely tested and has some issues with synchronization of several boards.


