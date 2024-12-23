# development version

This folder contains the development version which is used for testing future updated or other things. 

> [!WARNING]
> Not everything might be working in this version! If you need the latest stable version see [firmware-release](https://github.com/INO-quantum/FPGA-SoC-experiment-control/tree/main/firmware-release).

The actual version is for testing in Innsbruck.

this version includes:
1. contiguous strobe on any output: 
  This can be programmed by software, labscript connection table or directly by setting register (DIO_REG_CTRL_OUT0 and DIO_REG_CTRL_OUT1) with server command (SERVER_SET_REG). You can test this simply in BLACS `FPGA-board` section `output configuration` where you can select the output and one of the congiguous signals. The register values are displayed below the selection and can be copied directly into the connection table (prepending `0x` for each value). To maintain the phase of the strobe the start and restart trigger will start the board at the next contiguous strobe output. This causes that synchronization of several boards is making problems. See warning below.
2. force out:
  A special register (DIO_REG_FORCE_OUT) can be programmed by server command (SERVER_SET_REG) to output an arbitrary bit pattern directly on the bus. This includes all data and address bits and both strobe bits (when available in the firmware version). Some higher bits are output on `JB` of the FPGA board. Use this for testing the bus connection and for debugging in manual mode. As soon as the board is reset or is going into the run state, the pattern is reset and the register has to be written again for renewed output. 
3. DHCP:
  The board is now configured by default to get its IP address from a DHCP server. If you need a static IP address enable the corresponding entry in the server.config file, otherwise leave it commented, i.e. the sharp symbol `#` as the first character. I could test DHCP only briefly since I do not have a rooter in the lab. Let me know if there is a problem.
4. extended server.config file:
  The server.config file has been extended to include clock divider (`clk_div`) and input (`ctrl_in`) and output (`ctrl_out`) control registers. The clock divider allows to configure the bus output rate f_bus = 100MHz / clk_div with minimum clk_div = 5 giving 20MHz. The output control register allows to enable the contiguous strobe output automatically immediately at startup of the board. To use the proper settings for your experiment you have to set in the server.config file: clk_div, strobe_0 or strobe_1 and ctrl_out. Additionally, the IP address can be programmed with "DHCP" or left commented for DHCP.
5. manual:
  I have extended the manual to include most of the features of the board including new sections about the server commands and registers.
6. labscript + DAC:
  Different types of DAC can now be selected in the connection table
7. labscript + DDS:
  Different types of DDS can now be selected in the connection table. This includes all DDS used in Innsbruck.
8. bus output frequency up to 20MHz:
  The previous version had bugs in the server and in labscript which did not allowed to change the bus output frequency. This is fixed now and 20MHz output frequency (clock divider = 5) is possible without restrictions.
9. The reset of the board (SERVER_RESET) does now not anymore reset most of the configuration registers. This means that after the board has been configured one time (SERVER_CMD_OUT_CONFIG) it does not need to be configured again, unless some of the configuration should be changed. The reset is still needed in each cycle, mainly in order to properly reset the DMA channel, which otherwise gives an error. After the reset you have to program the FPGA control register (DIO_REG_CTRL) with the server command SERVER_SET_REG. The data is also needed to be uploaded (SERVER_CMD_OUT_WRITE) since this is reset as well. Afterwards you can start the board (SERVER_CMD_OUT_START), monitor execution progress (SERVER_GET_STATUS_IRQ) and stop (SERVER_CMD_OUT_STOP) the board when the returned status register (DIO_REG_STATUS) is in the end (DIO_STATUS_END) or error (bits 12-16) state. After this a new cycle can begin. In the next version the reset between the cycles should not be needed anymore which should allow to simply call SERVER_CMD_OUT_START and SERVER_CMD_OUT_STOP in order to repeat the last experiment without configuration and uploading of data. There will be also the possibility to automatically repeat the last experiment a programmable number of times with the minimum time step (1/f_bus) between the cycles. This so-called `cycling` mode is already implemented and simulated in the FPGA but the DMA driver has to be adapted for this. To remove the requirement of the reset between the cycles is a precondition to get the cycling mode working.


> [!WARNING]
> This version has problems with synchronization of serveral boards! For each start or restart trigger the boards have a jitter in timing of maximum ±1/bus output frequency. This is an unintended side-effect of the contiguous strobe and that the boards are reset and unlocked from the external clock in each run. To fix this one has to synchronize the contiguous strobe at the first start trigger (or send a trigger after all boards are started) and then keep the boards always locked to the external clock, i.e. do not reset between each run. I did not realized this initially, but can be fixed with some effort. 


