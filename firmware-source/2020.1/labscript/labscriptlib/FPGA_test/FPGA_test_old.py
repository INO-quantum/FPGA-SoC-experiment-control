#!/usr/bin/env python

from labscript import start, stop
from generate_samples import generate_digital_samples, generate_analog_samples, test_word
from labscript_utils import import_or_reload
import_or_reload('labscriptlib.FPGA_test.connection_table')

from labscriptlib.FPGA_test.connection_table import primary, secondary

# # self test
# #test_word()
#
# # define initial time and smallest time steps which the device allows
t = board0.start_time
dt = board0.time_step
#
# # start experiment
# #add_time_marker(t, "Start", verbose=True)
start()

# we can set all digital channels on the same device at the same time
# additionally, on different boards it can be also at the same time!
for i in range(2):
    test0.go_high(t)
    test15.go_high(t)
    t += dt
    test0.go_low(t)
    test15.go_low(t)
    t += dt
test0.go_high(t)
test15.go_high(t)
if not secondary: t += dt
out0.go_high(t)
out15.go_high(t)

t += dt
#coil_z.constant(t, 5)
#t += dt

if True:
    # toggle some bits as fast as possible.
    # no initial waiting time needed
    # digital channels on the same DigitalChannels device can change at the same time!
    # NOTE: for more than 1e4 samples this will make runmanager unresponsive for seconds!
    # ATTENTION: all channels of device are used! ensure no real device is attached!!!
    t = generate_digital_samples(DigitalChannels_device=DO0, start_time=t, time_step=0.1, end_time=None, num_samples=31)
    #t += dt
    if secondary:
        t = generate_digital_samples(DigitalChannels_device=DO1, start_time=t, time_step=0.1, end_time=None, num_samples=31)
    t += dt

if True:
    # generate triangular ramps on given analog channel
    samples = int(1e5)
    t_start = t
    t = generate_analog_samples(AnalogOut_device=coil_x, start_time=t, time_step=dt, end_time=None, num_samples=samples, Umin=-10, Umax=+10, dU=1)
    if secondary:
        t = generate_analog_samples(AnalogOut_device=test_x, start_time=t_start, time_step=dt, end_time=None, num_samples=samples, Umin=-10, Umax=+10, dU=1)
    t += dt

# generate a repeated triangular signal
# for  1 repetitions we get ca. 130k samples, uploading time 0.03s
# for  8 repetitions we get ca.   1M samples, uploading time 0.3s
# for 80 repetitions we get ca.  10M samples, uploading time 2.3s (2.8s for Cora-Z7-07S)
#        10M samples is the maximum possible! for more you get an error (NACK) from FPGA.
#        -> press "Restart tab and reinitialize device" (blue circular arrow) and it should be ok.
if False:
    if True: # fastest ramp possible with 1 sample per us
        duration = 4*(2**16)*1e-6
    else: # 5s in total
        duration = 10.0
    for i in range(10):
        # this creates an analog ramp from -10V to +10V and back with maximum sample rate of 1MHz.
        # for 16bits the voltage resolution is 20V/2^16 = 0.3mV.
        # if you increase the duration the true samplerate will go down. this is not a problem with labscript or ramp,
        # but is a concequence that FPGA_device generates output only when the channel is changing.
        # for 16 bits voltage resolution and more than 2^16 samples not every sample can change the voltage.
        t += dt
        #t += coil_x.ramp(t=t, initial=-10.0, final= 10.0, duration=(2**16)*1e-6, samplerate=1e6)
        #t += coil_x.ramp(t=t, initial= 10.0, final=-10.0, duration=(2**16)*1e-6, samplerate=1e6)
        t_start = t
        t += coil_x.ramp(t=t, initial= 0.0, final= 9.0, duration=duration/4, samplerate=1e6)
        t += coil_x.ramp(t=t, initial= 9.3, final=-9.0, duration=duration/2, samplerate=1e6)
        t += coil_x.ramp(t=t, initial=-9.3, final= 0.0, duration=duration/4, samplerate=1e6)
        if secondary is not None: # parallel ramp on secondary board
            t = t_start
            t += test_x.ramp(t=t, initial=0.0, final=9.0, duration=duration/4, samplerate=1e6)
            t += test_x.ramp(t=t, initial=9.3, final=-9.0, duration=duration/2, samplerate=1e6)
            t += test_x.ramp(t=t, initial=-9.3, final=0.0, duration=duration/4, samplerate=1e6)
#
t += dt
test15.go_low(t)
test0.go_low(t)
if not secondary: t += dt
out15.go_low(t)
out0.go_low(t)
#
# # Stop the experiment shot with stop()
# # no waiting time needed
# #t += 100 * dt
stop(t)
