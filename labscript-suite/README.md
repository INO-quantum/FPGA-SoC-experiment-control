# labscript_FPGA-SoC_device
python code to implement FPGA-SoC board in labscript-suite

The FPGA-SoC board:
The board is used as a low-cost experimental control hardware for controlling cold and ultracold atoms experiments. It is designed to work together with existing hardware placed in a 19" rack and replaces the outdated DIO64 (probably also DIO128) boards from Viewpoint Systems. In each rack several plug-in modules can be inserted, like digital or analog outputs which are programmed via a ribbon cable "bus" on the backplane of the rack. A custom buffer card was designed to buffer and level-shift the signal from the FPGA-SoC board (3.3V) from the rack (5V) and which hosts clock input and output buffers for an external clock reference and additional buffers for external triggers and to synchronize several boards. The FPGA-SoC board is connected with the Arduino style headers to the buffer card which is directly inserted into the rack and connects to the backplane bus. The setup might be also compatible with similar racks used with other digital I/O cards like the ones from National Instruments. The board is a commercial low-cost board from Digilent Inc. called Cora-Z7-10. The cheaper Cora-Z7-07S board is suiteable as well, but has only a single-core CPU which could limit certain applications. The board has a FPGA-SoC chip from Xilinx (Zynq-7010 or 7007S), Gigabit Ethernet, USB (device and host) ports and plenty of external pins in an extended Arduino style layout. On the FPGA-SoC (system-on-a-chip) a simple Linux operating system (petalinux 2017) is running on the CPU which faciliates proptyping and tests where one can execute C/C++ applications or even Python code (if Python is installed). The second half of the chip is the FPGA (field-programmable gate array) part which contains custom hardware design (programmed in Verilog) which generates the signals which communicate with the devices on the bus. 

Each FPGA-SoC board can drive 2 racks but they should be nearby. This was implemented since the old DIO card was able to drive two racks. If the two racks are far (> 1m) apart consider to use two FPGA-SoC boards instead to keep the timing tight.

The channels (or plug-in modules) are distinguished with a 7-bit address which must be unique for each rack. The same addresses are allowed on different racks since these are independent. The device-dependent data word is 16-bits long which allows to address 16 digital channels or one 16-bit DAC. The FPGA-SoC puts the address and data word on the bus at the programmed time and after about 300ns (for 1MHz bus update rate) another bit on the bus (used as the pseudeclock which is also called 'strobe') goes high and after about 300ns goes low. This triggers the addressed channel to update the output.

Implementation as a labscript-suite device:
The present software implements the FPGA-SoC board as a labscript-suite device. Labscript-suite (https://docs.labscriptsuite.org/) is a free software package written in Python which allows to control ion, cold- or ultracold atoms experiments. It consists of 'runmanager' which generates the experimental sequence data, 'runviewer' which allows to visualize the data like oscilloscope traces and 'BLACS' which interacts with the hardware. The additional program 'Lyse' allows to gather data (like images) and analyze it. The experimental sequence, i.e. the list of actions as a function of time, is saved as an easy-to-read Python file (see example FPGA_test.py) which the user edits. The top of the file contains the so-called "connection table" where the used hardware is declared. A separate file "connection_table.py" must contain the same hardware declaration, but could contain more hardware than used in the actual experimental sequence file. 

The FPGA-SoC board is implemented as a "pseudoclock device" (i.e. it gives the timing), the insert-modules are implemented as "intermediate device". They are internally connected via a single "clockline" to a single "pseudoclock" and then to the FPGA board. The two possible racks are not implemented as separate "clocklines" since they must share the same times (since a common data structure is generated). The generated pseudoclock signal ('strobe') on the two buses is independent however.

I have not implemented several boards. Probably additional boards can be just directly connected to the primary board and have then their individual devices attached. There is also an auto-synchronization feature which can synchronize several boards with a few ns relative error. This is not fully implemented but will be done in the future. The intermediate plan is to measure the delay times between the boards and give as an argument to the secondary boards.

Steps to get started:
1. install labscript-suite on your computer as described here: https://docs.labscriptsuite.org/en/stable/installation/
2. into the folder labscript-suite/userlib/user_devices copy the two files: FPGA_device.py and register_classes.py
3. into the folder labscript-suite/userlib/labscriptlib/<your apparatus name> copy conncetion_table.py and FPGA_test.py
4. edit 'FPGA_test.py' and accordingly connection_table.py for your experimental setup (see comments in files and below)
5. in linux from a terminal window (other OS see labscript doc)
  a) cd <labscript installation folder>
  b) source .venv/bin/activate
  c) runmanager
  d) runviewer [optional in another terminal after steps a-b]
  e) blacs [optional in another terminal after steps a-b]

Editing connection table and experimental sequence files:
You have to edit your experimental control sequence (as for example FPGA_test.py) and connection_table.py to adapt to your setup. These are simple Python files located in the folder labscript-suite/userlib/labscriptlib/<your apparatus name>. The top of your experimental sequence file must be using the same names and arguments as used in the connection_table.py. The experimental sequence file must contain a subset of connection_table.py. It is important that in connection_table.py you still call start() and stop(1.0) functions. There can be commands between the start() and stop(1.0) but it does not make a difference. The time given to stop must be nonzero but otherwise does not matter. 
  
  The FPGA-SoC device is declared with:
  FPGA_board(name='board0', ip_address=PRIMARY_IP, ip_port=DEFAULT_PORT, bus_rate=1.0, num_racks=2)
    name = name string of device. can be anything, but must be a valid Python symbol name.
    ip_address = IP address of board (default PRIMARY_IP, can be modified in server.config file on micro SD card of each board)
    ip_port = port number string. use DEFAULT_PORT if not sure.
    bus_rate = maximum bus output rate in MHz. typically 1.0 (1MHz) but depends on your devices. Maximum 10MHz (but 30-40MHz should be possible).
    num_racks = number of connected racks. must be 1 or 2. keep cable as short as possible, otherwise use several boards!
  
  At the moment 2 plug-in modules can be declared: (DDS will be added later)
  Each of these modules host several channels (see further below).
  DigitalChannels(name='DO0'  , parent_device=board0, connection='0x01', rack=0, max_channels = 16)
    name = name string of device. can be anything, but must be a valid Python symbol name.
    parent_device = FPGA_board name to which device is connected. this is name given to FPGA_board(name=...) but without quotes.
    connection = device address string. shared by all channels. can be hex (with '0x') or decimal.
    rack = rack number must be 0 or 1
    max_channels = maximum number of allowed channels (typically 16)
  AnalogChannels(name='AO0'   , parent_device=board0, rack=0, max_channels = 2)
    name = name string of device. can be anything, but must be a valid Python symbol name.
    parent_device = FPGA_board name to which device is connected. this is name given to FPGA_board(name=...) but without quotes.
    rack = rack number must be 0 or 1
    max_channels = maximum number of allowed channels (typically 2 or 4)
    
  The actual channels are declared depending on the type of plug-in module they have as parent_device:
  DigitalOut(name='test0', parent_device=DO0, connection='0')
    name = name of channel.
    parent_device = DigitalChannels name to which channel is connected. this is name given to DigitalChannels(name=...) but without quotes.
    connection = unique channel number string. can be hex (with '0x') or decimal.
    note: the address is given to the DigitalChannels declaration since all channels have same address!
  AnalogOut(name='coil_x', parent_device=AO0, connection='0x02')
    name = name of channel.
    parent_device = AnalogChannels name to which channel is connected. this is name given to AnalogChannels(name=...) but without quotes.
    connection = device address string. can be hex (with '0x') or decimal.
  
=======
# FPGA-SoC_experiment_control

This project contains hopefully everything to generate your own FPGA-SoC experimental control system designed for cold or ultracold atoms experiments. But any other use is welcome!

The heart of the exerpimental control system is the Cora-Z7 board from Digilent Inc. https://store.digilentinc.com/cora-z7-zynq-7000-single-core-and-dual-core-options-for-arm-fpga-soc-development/. There are two boards available: Cora-Z7-10 and Cora-Z7-07S where the former has a dual-core CPU and the later a single-core CPU and a slightly smaller FPGA. The only measured difference between the performance of the two boards is that the uploading rate of the single-core CPU board was about 80% smaller than that of the dual-core CPU. The FPGA and DMA performance is exactly the same. The single-core board is slightly cheaper and the difference in FPGA size is not much. If you do not plan big additions in the FPGA part (we use about 60-80%) and you never upload many many samples, then this board is perfectly fine.

This is a low-cost FPGA-SoC development board. The SoC (system-on-a-chip) has a dual or single-core CPU (ARM Cortex A9) and on the same chip a FPGA (field-programmable gate array). The CPU allows to run a simple Linux operating system (Petalinux 2017.4) on the CPU which allows you to run your custom code or applications and facilitates using system services to access external hardware (Ethernet, DDR memory, USB keyboard/mouse, SD card, etc.). The FPGA allows to implement custom hardware (logic, PLLs, SERDES, etc.) which you can configure as you please. The tight connection between the CPU and FPGA allows to control the hardware by software and to efficiently transfer data between the two parts. 

The implementation of the FPGA-SoC for "experimental control" was born out of the need to replace an old DIO64 card (from Viewpoint Systems) which is not anymore supported/sold and uses old Hardware (PCI slot) and old operating systems (Windows XP/7/8). This card was preferrably programmed with NI Labview/LabwindowsCVI usser application programms which create a table of time and instructions (32bit time and 32bit instruction/data in the simplest case) which is sent to the driver and is then executed on the card. This card outputs the instructions at the programmed time (typically in units of us) on a 50-way ribbon cable of 2-3m length. This cable is connected to a 19" rack with our custom hardware. After buffering and electrical isolation (in a buffer card) the instructions/data are on the backplane of the rack on a bus. Several plug-in modules of different type and size can be inserted into the rack and connect to this bus. Typical devices are digital and analog outpus and DDS (direct digital synthesizers, i.e. RF generators). Some experiments might use also input devices, but we do not have. Each device has an address decoder and 7 bits of the data are reserved for the address of the device. 16 data bits are reserved for device specific data. One bit called "Strobe" is used as a pseudo-clock, which is simply a clock which pulses only when something on the bus should be updated. This signal is originally recovered from a bit generated by the software and sent with the data by the DIO64 card. This bit must change state for every instruction and in the buffer card a simple electronic cirquit generates the pulses out of this signal. The pulses must be shorter than the update rate of the bus (essentially, it has twice the frequency than the bus) and must be delayed in time with the bus update. This way delays between different bits on the bus and noise is cancelled.

The FPGA-SoC replaces the DIO64 card but also improves the old system in many ways:
1. the data is uploaded via Gigabit Ethernet:
  * even for long sequences the uploading time is small (2.3s for 10M samples)
  * electrical isolation given by Ethernet
  * much longer cables are possible. this even allows remote-control over network.
  * no driver is needed on the experimental control computer 
    * no restrictions on operating system
    * no restriction on used software
  * experimental control computer is free to do other things during the execution of the sequence since there is no busy driver running in background
2. 10M samples can be stored directly on the board
  * this size (128MB) is more than sufficient for most of our experiments
  * repetitions of the same experiment can be done directly by the board without uploading again the data
  * in a future possible extension only parts of the data could be updated in memory
3. contiguous bus output rate of 30-40MHz
  * the data from the memory into the FPGA part is transmitted via direct memory access (DMA) which gives the limitation of contiguous data output rate
  * write to the bus and read from the bus (not in our experiment) can be done simultaneously without affecting the other channel
  * using more of the unused DMA ports can increase the rate (factor 2 should be possible, maybe 100MHz?)
4. the internal FIFOs hold 8192 samples which allows short "burst" of output/input at higher rates
  * for short time and ensuring the FIFO is not getting empty/full output/input can be done at higher rates
5. the internal clock of the FPGA part is running at the moment with 50MHz
  * increasing to 100MHz is "easy" but you most likely, the FPGA design has to be adapted.
  * going to 200MHz might be possible but will be come more difficult. 250MHz is the limit.
  * using the "strobe" the output rate is limited to half of the FPGA clock frequency (current design even 1/3) but this could be changed
  * additional considerations are voltage levels (at the moment 5V) and proper termination of the bus (at the moment unterminated). 
  * to use differential lines the FPGA would support this but the given board design strongly constrains on usable pairs. Additionally, levels cannot be easily mixed (should work but nobody will warrant for this). 
6. the FPGA-SoC allows to customize for our application. We have the freedom to implement new ideas, features, use new devices, implement protocols, etc. here a list what could be done or is partially already done or tested:
  * we tested to synchronize several boards by using a common clock signal and to trigger the boards from one board and measure and correct for the propagation delay of the trigger signal. This way we could synchronize 2 boards with about 1ns. This is not fully implemented but should become a standard feature.
  * you could run additional software on the CPU. for example some python analysis/feedback program, which changes the state of the experiment depending on measured values. note however, this cannot be "very" fast (the CPU runs at 650MHz). Very fast things could be done on the hardware, but also this is limited to 100-200MHz, but things can be done in parallel (on many bits).
  * the board features an USB port which can be configured as device (passive, like a flash drive) or host (active, like your computer). Many modern laboratory equipments allow to remote control via USB (using the USBTMC protocol) or older devices use the GPIB port for which USB-to-GPIB adapters exist. You could directly control such a device from the FPGA-SoC using a simple application running on the CPU or with data which you send via Ethernet.
  * one could implement ramps directly on the board and update only parts of the sequence

The project has several folders. Look at the readme.md files there for specific instructions.

1. FPGA-SoC-Cora-Z7-10: this is the firmware to be uploaded on the Cora-Z7-10 board
  a. Vivado: this contains the Vivado Project on which you generate the logic part of the board
  b. Petalinux: this contains the Petalinux-Project on which you generate the linux boot image and boot loader 
2. FPGA-SoC-Cora-Z7-07S: this is the firmware to be uploaded on the Cora-Z7-07S board
  a. Vivado: this contains the Vivado Project on which you generate the logic part of the board
  b. Petalinux: this contains the Petalinux-Project on which you generate the linux boot image and boot loader 
3. buffer-card: schematics, Gerber files and bill of materials needed for the buffer card
4. auto-synchronization: schematics of the auto-synchronization electronics
5. labscript: labscript device implementation
>>>>>>> a496bf7fa26cf9b30f595ec0146819c345dc1b0d
