# development version

This folder contains the development version which is used for testing future updated or other things. 

> [!WARNING]
> Not everything might be working in this version! If you need the latest stable version see [firmware-release](https://github.com/INO-quantum/FPGA-SoC-experiment-control/tree/main/firmware-release).

The actual version is for testing in Innsbruck.

this version includes:
1. contiguous strobe on any output: 
  This can be programmed by software, labscript connection table or directly by setting register or server command. To maintain the phase of the strobe the start and restart trigger will start the board at the next contiguous strobe output. This causes that synchronization of several boards is making problems. See warning below.
2. force out:
  a special register can be programmed by software or GUI (see labscript BLACS) to output any bit pattern directly on the bus. Use this for testing the bus connection and for debugging. 
3. DHCP:
  the board is now configured by default to get its IP address from a DHCP server. If you need a static IP address enable the corresponding entry in the server.config file, otherwise leave it commented.
4. extended server.config file:
  The server.config file has been extended to include clock divider and input and output control registers. This way the contiguous strobe can be enabled automatically at startup of the board. To use the proper settings for your experiment you have to set clk_div, strobe_0 or strobe_1 and ctrl_out. Additionally, the IP address can be programmed with "DHCP" or left commented for DHCP.
5. manual:
  I have extended the manual to include most of the features of the board including new sections about the server commands and registers.
6. labscript + DAC:
  different types of DAC can now be selected in the connection table
7. labscript + DDS:
  different types of DDS can now be selected in the connection table. This includes all DDS from Innsbruck.
8. bus output frequency up to 20MHz:
  The previous version had bugs in the server and in labscript which did not allowed to change the bus output frequency. This is fixed now and 20MHz output frequency (clock divider = 5) is possible without restrictions.

> [!WARNING]
> This version has problems with synchronization of serveral boards! For each start or restart trigger the boards have a jitter in timing of maximum ±1/bus output frequency. This is an unintended side-effect of the contiguous strobe and that the boards are reset and unlocked from the external clock in each run. To fix this one has to synchronize the contiguous strobe at the first start trigger (or send a trigger after all boards are started) and then keep the boards always locked to the external clock, i.e. do not reset between each run. I did not realized this initially, but can be fixed with some effort. 


