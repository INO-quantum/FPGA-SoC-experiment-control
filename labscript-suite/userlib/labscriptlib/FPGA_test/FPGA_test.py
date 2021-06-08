##############################################################################################################
# import hardware_setup.py in folder labscript-suite/userlib/pythonlib
# this ensures consistent connection_table.py with all experimental scripts
##############################################################################################################
#import hardware_setup
# TODO: there is some problem with importing hardware_setup. so temporarily copy content here.
#       this needs to be consistent with connection_table.py! so you have to edit always 2 files!

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



from labscript import start, stop, add_time_marker
from user_devices.FPGA_device import FPGA_board, DigitalChannels, AnalogChannels, PRIMARY_IP, SECONDARY_IP, DEFAULT_PORT

t = 0
#add_time_marker(t, "Start", verbose=True)
start()

# toggle some bits as fast as possible.
# no initial waiting time needed but there will be always a sample at 0 time (can be empty).
# digital channels on the same DigitalChannels device can change at the same time!
# coil_z and test0 can be set at the same time since they are on different racks!
# for more than 1e4 repetitions this will make runmanager unresponsive for seconds!
dt = 1e-6
coil_z.constant(t,5.0)
t+=dt
coil_z.constant(t,1.0)
t+=dt
if True:
    for i in range(160): # 160, 128, 64,...
        test1.go_high(t)
        test16.go_high(t)
        t+=dt
        out3.go_high(t)
        out4.go_high(t)
        t+=dt
        out4.go_low(t)
        out3.go_low(t)
        t+=dt
        test16.go_low(t)
        test1.go_low(t)
        t+=dt
    coil_z.constant(t,2.0)
    t+=dt
    coil_z.constant(t, 3.0)
    t += dt
    test16.go_high(t)
    test1.go_high(t)

# generate a repeated triangular signal
# for  1 repetitions we get ca. 130k samples, uploading time 0.03s
# for  8 repetitions we get ca.   1M samples, uploading time 0.3s
# for 80 repetitions we get ca.  10M samples, uploading time 2.3s (2.8s for Cora-Z7-07S)
#        10M samples is the maximum possible! for more you get an error (NACK) from FPGA.
#        -> press "Restart tab and reinitialize device" (blue circular arrow) and it should be ok.
if True:
    for i in range(1):
        # this creates an analog ramp from -10V to +10V and back with maximum sample rate of 1MHz.
        # for 16bits the voltage resolution is 20V/2^16 = 0.3mV.
        # if you increase the duration the true samplerate will go down. this is not a problem with labscript or ramp,
        # but is a concequence that FPGA_device generates output only when the channel is changing.
        # for 16 bits voltage resolution and more than 2^16 samples not every sample can change the voltage.
        t += dt
        t += coil_x.ramp(t=t, initial=-10.0, final= 10.0, duration=(2**16)*1e-6, samplerate=1e6)
        t += coil_x.ramp(t=t, initial= 10.0, final=-10.0, duration=(2**16)*1e-6, samplerate=1e6)

t += dt
test16.go_low(t)
test1.go_low(t)

# Stop the experiment shot with stop()
# no waiting time needed
t += 100.0e-6
stop(t)
