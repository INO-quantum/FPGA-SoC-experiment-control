##############################################################################################################
# import hardware_setup.py in folder labscript-suite/userlib/pythonlib
# this ensures consistent connection_table.py with all experimental scripts
##############################################################################################################
import hardware_setup

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
