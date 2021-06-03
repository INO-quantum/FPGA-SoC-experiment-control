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
You have to edit your experimental control sequence (as for example FPGA_test.py) and hardware_setup.py to adapt to your setup. These are simple Python files located in the folders labscript-suite/userlib/labscriptlib/<your apparatus name> and labscript-suite/userlib/pythonlib/. The top of your experimental sequence file must import the hardware_setup.py file. The file connection_table.py is also importing the same file and does not need to be modified.
  
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
  
