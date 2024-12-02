#!/usr/bin/env python
##############################################################################################################
# connection_table.py
# import global hardware_setup.py file from lbascript-suite/userlib/pythonlib directory
# importing connection_table.py into individual experimental sequence file does not work!?
# but importing hardware_setup.py from connection_table.py works.
# this is much more convenient than to have connection_table defined in EVERY experimental sequence and
# moreover one needs to change only a single file!
##############################################################################################################

from labscript import AnalogOut, DigitalOut
from user_devices.FPGA_device import FPGA_board, DigitalChannels, AnalogChannels, PRIMARY_IP, SECONDARY_IP, DEFAULT_PORT #, generic_conversion
#from generic_conversion import generic_conversion
from labscript_utils.unitconversions import generic_conversion

#from pythonlib import generic_conversion
#from labscript_utils import import_or_reload
#import_or_reload('pythonlib.generic_conversion')

# FPGA device (pseudoclock device)
#       name = name string.
#       ip_address = IP address of board
#       ip_port = port number string
#       bus_rate = maximum bus output rate in MHz
#       num_racks = number of connected racks. must be 1 or 2. keep cable as short as possible, otherwise use several boards!
# each board can drive max. 2 nearby racks with independent device addresses and strobe (96bits per sample).
# if need more racks or more than few Meter distance use several boards with one as primary board, others are connected as secondary boards.
primary   = FPGA_board(name='board0', ip_address='192.168.0.12', ip_port=DEFAULT_PORT, bus_rate=1.0, num_racks=1)
if False: # use secondary board
    secondary = FPGA_board(name='board1', ip_address='192.168.1.11', ip_port=DEFAULT_PORT, bus_rate=1.0, num_racks=1, trigger_device=board0, trigger_connection='secondary')
else:
    secondary = None

# digital outputs
# DigitalChannels: (intermediate device)
#       name = name of device. give as parent_device to DigitalOut.
#       parent_device = FPGA_board object. this is name given to FPGA_board(name=...) but without quotes.
#       connection = device address string. shared by all channels. can be hex (with '0x') or decimal.
#       rack = 0 or 1
#       max_channels = maximum number of allowed channels (typically 16)
# DigitalOut: (individual output channel)
#       name = name of channel.
#       parent_device = DigitalChannels object. this is name given to DigitalChannels(name=...) but without quotes.
#       connection = unique channel number string. can be hex (with '0x') or decimal.
DigitalChannels(name='DO0'  , parent_device=board0, connection='0x01', rack=0, max_channels = 16)
for i in range(16):
    DigitalOut(name='test'+str(i), parent_device=DO0, connection=str(i))
if secondary:
    DigitalChannels(name='DO1'  , parent_device=board1, connection='0x01', rack=0, max_channels = 16)
    for i in range(16):
        DigitalOut(name='out'+str(i), parent_device=DO1, connection=str(i))
else:
    DigitalChannels(name='DO1', parent_device=board0, connection='0x02', rack=0, max_channels=16)
    for i in range(16):
        DigitalOut(name='out' + str(i), parent_device=DO1, connection=str(i))

# analog outputs
# AnalogChannels: (intermediate device)
#       name = name of device. give as parent_device to AnalogOut.
#       parent_device = FPGA_board object. this is name given to FPGA_board(name=...) but without quotes.
#       rack = 0 or 1
#       max_channels = maximum number of allowed channels (typically 2 or 4)
# AnalogOut: (individual output channel)
#       name = name of channel.
#       parent_device = AnalogChannels object. this is name given to AnalogChannels(name=...) but without quotes.
#       connection = device address string. can be hex (with '0x') or decimal.
AnalogChannels(name='AO0'   , parent_device=board0, rack=0, max_channels = 2)
AnalogOut     (name='coil_x', parent_device=AO0, connection='0x03' )
AnalogOut     (name='coil_y', parent_device=AO0, connection='0x04')

AnalogChannels(name='AO1'   , parent_device=board0, rack=0, max_channels = 2)
AnalogOut     (name='coil_z', parent_device=AO1, connection='0x15')

AnalogChannels(name='AO2'   , parent_device=board0, rack=0, max_channels = 4)
AnalogOut     (name='Amp_out', parent_device=AO2, connection='0x06',
               unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit':'A', 'equation':'Amp*10.0/100.0', 'user_param':'Amp', 'min':0.0, 'max':100.0, 'step': 10, 'decimals':3})

if secondary:
    AnalogChannels(name='AO3'   , parent_device=board1, rack=0, max_channels = 2)
    AnalogOut     (name='test_x', parent_device=AO3, connection='0x03')
    AnalogOut     (name='test_y', parent_device=AO3, connection='0x04')

##############################################################################################################

##############################################################################################################
# ATTENTION: start() and stop(1) cannot be missing! time for stop must be >0. 
##############################################################################################################
from labscript import start, stop
if __name__ == '__main__':
    start()
    stop(1)
