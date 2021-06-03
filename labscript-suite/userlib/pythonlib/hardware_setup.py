#!/usr/bin/env python

##############################################################################################################
# hardware_setup.py
# import from connection_table.py and your script of the experimental sequence
# contains all devices in the system and unit conversion classes
# must be placed in folder labscript-suite/userlib/pythonlib
##############################################################################################################

from labscript import AnalogOut, DigitalOut, UnitConversion
from user_devices.FPGA_device import FPGA_board, DigitalChannels, AnalogChannels, PRIMARY_IP, SECONDARY_IP, DEFAULT_PORT

# define unit conversion class
class BidirectionalCoilDriver(UnitConversion):
    base_unit = 'V'
    derived_units = ['A']
    def __init__ (self, calibration_parameters = None):
        if calibration_parameters is None:
            calibration_parameters = {}
        self.parameters = calibration_parameters
        # I [ A ] = slope * V [ V ] + shift
        # Saturates at " saturation " Volts
        self.parameters.setdefault('slope', 1) # A / V
        self.parameters.setdefault('shift', 0 ) # A
        self.parameters.setdefault('saturation', 10 ) # V
        UnitConversion. __init__(self, self.parameters)

    def A_to_base(self, amps):
        shift = self.parameters['shift']
        slope = self.parameters['slope']
        volts = ( amps - shift ) / slope
        return volts

    def A_from_base(self, volts) :
        volts = numpy.minimum(volts, self.parameters['saturation'])
        shift = self.parameters['shift']
        slope = self.parameters['slope']
        amps = slope * volts + shift
        return amps

# FPGA device (pseudoclock device)
#       name = name string.
#       ip_address = IP address of board
#       ip_port = port number string
#       bus_rate = maximum bus output rate in MHz
#       num_racks = number of connected racks. must be 1 or 2. keep cable as short as possible, otherwise use several boards!
# each board can drive max. 2 nearby racks with independent device addresses and strobe (96bits per sample).
# if need more racks or more than few Meter distance use several boards with one as primary board, others are connected as secondary boards.
FPGA_board(name='board0', ip_address=PRIMARY_IP, ip_port=DEFAULT_PORT, bus_rate=1.0, num_racks=2)
#TODO: how to implement secondary boards?
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
    DigitalOut(name='test'+str(i+1), parent_device=DO0, connection=str(i))
DigitalChannels(name='DO1'  , parent_device=board0, connection='0x02', rack=0, max_channels = 16)
for i in range(16):
    DigitalOut(name='out'+str(i+1), parent_device=DO1, connection=str(i))
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
AnalogOut     (name='coil_x', parent_device=AO0, connection='0x03', unit_conversion_class = BidirectionalCoilDriver,
                    unit_conversion_parameters = {
                        'slope' : 10 , # A/V
                        'shift' : 0 , # A at 0V
                        'saturation' : 10 # V
                    })
AnalogOut     (name='coil_y', parent_device=AO0, connection='0x04')
AnalogChannels(name='AO1'   , parent_device=board0, rack=1, max_channels = 2)
AnalogOut     (name='coil_z', parent_device=AO1, connection='0x01')
AnalogChannels(name='AO2'   , parent_device=board0, rack=1, max_channels = 4)
AnalogOut     (name='PID_x' , parent_device=AO2, connection='0x02')
##############################################################################################################

