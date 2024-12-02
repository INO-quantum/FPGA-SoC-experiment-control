#!/usr/bin/env python

from labscript import start, stop
from labscript_utils import import_or_reload
import_or_reload('labscriptlib.FPGA_test.connection_table')
from labscriptlib.FPGA_test.connection_table import primary, secondary
from user_devices.generate_samples import generate_digital_samples, generate_analog_samples, test_word
from user_devices.FPGA_device import AO_RESOLUTION

import numpy as np

# # self test
# #test_word()
#
# define initial time and smallest time steps which the device allows
t = primary.start_time
dt = primary.time_step
# analog output resolution in V
dU = AO_RESOLUTION

# assign analog outputs
#test_ao_0 = IR_laser_no3_W
#test_ao_1 = Cr_AOM_spectr_60to137MHz_no26_MHz
#test_ao_2 = 
#test_ao_3 =
ch_ao = [test_ao_0, test_ao_1, test_ao_2, test_ao_3]
test_do_0 = Stingray_no1per1_on
test_do_1 = Li_ZS_AOM_no1per2_on
test_do_2 = CrRepumpers_AOMshutter_no1per3_on
test_do_3 = Li_oven_shutter_no1per4_on
ch_do = [test_do_0, test_do_1, test_do_2, test_do_3]

if secondary:
    ch2_ao = [test_ao_4, test_ao_5, test_ao_4, test_ao_5]
    test_do_4 = Crossed_AOM_no3per1_on
    test_do_5 = test_no3per2_on
    test_do_6 = test_no3per3_on
    test_do_7 = test_no3per4_on
    ch2_do = [test_do_4, test_do_5, test_do_6, test_do_7]

#
# # start experiment
# #add_time_marker(t, "Start", verbose=True)
start()

if False:
    # we can set all digital channels on the same device at the same time
    # additionally, on different boards it can be also at the same time!
    for do in ch_do:
        do.go_high(t)
    t += dt
    #for do in ch_do:
    #    do.go_low(t)
    #t += dt

if False:
    test_do_0.go_high(t)
    test_do_3.go_high(t)
    t += dt
    test_do_4.go_high(t)
    test_do_5.go_high(t)
    t += dt
    test_do_4.go_low(t)
    test_do_5.go_low(t)
    t += dt
    test_do_0.go_low(t)
    test_do_3.go_low(t)
    t += dt

    test_ao_1.constant(3*dt, 5.0) # error

if False:
    # toggle some bits as fast as possible.
    # no initial waiting time needed
    # digital channels on the same DigitalChannels device can change at the same time!
    # NOTE: for more than 1e4 samples this will make runmanager unresponsive for seconds!
    # ATTENTION: all channels of device are used! ensure no real device is attached!!!
    t = generate_digital_samples(DigitalChannels_device=DO1, start_time=t, time_step=0.1, end_time=None, num_samples=31)
    #t += dt
    if secondary:
        t = generate_digital_samples(DigitalChannels_device=DO1, start_time=t, time_step=0.1, end_time=None, num_samples=31)
    t += dt

#test_ao_5.constant(0.5, 0.0)
#test_ao_5.constant(0.5, 1.0)
#t += 10*dt

if False: # analog ramp test
    check_ramp = True # compare generated ramps after stop()
    samples = 2**5 # the true number of samples can be larger (typically by 1-2, but depends on number of samples)
    t_step = dt*50
    t0 = 100.0 + dt # note: the error is small but increase with t0!
    t1 = t0 + samples*t_step
    duration = t1 - t0
    U0 = -5.0
    U1 = 5.0
    # using ramp
    test_ao_1.ramp(t=t0+25*dt, initial=U0, final=U1, duration=duration, samplerate=1 / t_step)
    t_ramp = test_ao_0.ramp(t=t0, initial=U0, final=U1, duration=duration, samplerate=1/t_step)
    if True:# using manual steps to reproduce what ramp is doing
        #t0 = round(t0 + 0*dt, 10)
        #duration = round(duration, 10)
        slope = (U1 - U0)/duration
        times = np.arange(0, duration, t_step, dtype=np.float64)
        #times = np.linspace(0, duration, samples + 1, dtype=np.float64)
        U_ramp = U0 + np.around(times + t_step/2,10) * slope  # the initial value is not in list, all times are shifted by t_step/2
        times += t0
        for i,t in enumerate(times):
            test_ao_4.constant(round(t,10), U_ramp[i])
        if U_ramp[-1] != U1: # the exact final value is always in list. this randomly changes number of samples
            test_ao_4.constant(times[-1]+t_step, U1)
        print('final time %f and U %f' % (times[-1], U_ramp[-1]))
    t = t0 + t_ramp + t_step
else:
    check_ramp = False # compare generated ramps after stop()

if True:
    # generate triangular ramps on given analog channel
    # TODO: more than 2 channels with 32k samples each takes too long to compile and get 'lock not held' error!
    samples = 2**16 # samples per ramp from -10V to +10V
    t_step = 1*dt
    if True: # test with ramp function. more efficient but does not create precise steps
        # TODO: it is impossible to do interleaved ramps with ao.ramp function? this is strange since one would think that each ramp is done the same?
        # print('ramp time %f for %i samples' % (tramp, samples))
        t_start = t
        for i,ao in enumerate(ch_ao):
            #t = t_start + i*dt*2
            ch_do[i].go_high(t)
            if secondary:
                ch2_do[i].go_high(t)
            t += t_step
            #print([i,t*1e6])
            t_ramp_0 = ao.ramp(t=t, initial=0.0, final=samples*dU/2, duration=samples*t_step/2, samplerate=1/t_step)
            if secondary:
                ch2_ao[i].ramp(t=t, initial=0.0, final=samples * dU / 2, duration=samples * t_step / 2, samplerate=1 / t_step)
            t += t_ramp_0 + t_step
            #print([i,t*1e6])
            t_ramp_1 = ao.ramp(t=t, initial=10.0, final=-10, duration=samples*t_step, samplerate=1/t_step)
            if secondary:
                ch2_ao[i].ramp(t=t, initial=10.0, final=-10, duration=samples*t_step, samplerate=1/t_step)
            t += t_ramp_1 + t_step
            t_ramp_2 = ao.ramp(t=t, initial=-10.0, final=0, duration=samples*t_step/2, samplerate=1/t_step)
            if secondary:
                ch2_ao[i].ramp(t=t, initial=-10.0, final=0, duration=samples*t_step/2, samplerate=1/t_step)
            t += t_ramp_2 + t_step
            ch_do[i].go_low(t)
            if secondary:
                ch2_do[i].go_low(t)
            t += t_step
    else:
        t = generate_analog_samples(AnalogOut_device=test_ao_0, start_time=t_start, time_step=t_step, end_time=None, num_samples=samples, Umin=-10, Umax=+10, dU=dU)
        if not secondary: t_start += dt
        t = generate_analog_samples(AnalogOut_device=test_ao_1, start_time=t_start, time_step=t_step, end_time=None,num_samples=samples, Umin=-10, Umax=+10, dU=dU)
    #t += dt
    test_do_0.go_low(t)
    t += dt

#test_ao_1.constant(10*dt, 10) Generates time conflict. TODO: why initial value is 1? and not 0?

#test_do_4.go_high(t)
#test_do_4.go_low(t)

if False:
    # adjust max/min voltage. at +/-6.5V DVM has 3 digits while at 10V has only 2 digits
    U_test = 6.5
    for i in range(len(ch_ao)):
        ch_do[i].go_high(t)
        ch_ao[i].constant(t + dt, U_test)
        t += 0.5
    for i in range(len(ch_ao)):
        ch_do[i].go_low(t)
        ch_ao[i].constant(t + dt, -U_test)
        t += 0.5
    for i in range(len(ch_ao)):
        ch_ao[i].constant(t + dt, 0)
        t += 0.5

if False: # resolution test
    U = -0.010
    for i in range(51):
        test_ao_0.constant(t, U)
        t += 10*dt
        U -= dU

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
        #t += test_ao_0.ramp(t=t, initial=-10.0, final= 10.0, duration=(2**16)*1e-6, samplerate=1e6)
        #t += test_ao_0.ramp(t=t, initial= 10.0, final=-10.0, duration=(2**16)*1e-6, samplerate=1e6)
        t_start = t
        t += test_ao_0.ramp(t=t, initial= 0.0, final= 9.0, duration=duration/4, samplerate=1e6)
        t += test_ao_0.ramp(t=t, initial= 9.3, final=-9.0, duration=duration/2, samplerate=1e6)
        t += test_ao_0.ramp(t=t, initial=-9.3, final= 0.0, duration=duration/4, samplerate=1e6)
        if secondary is not None: # parallel ramp on secondary board
            t = t_start
            t += test_ao_1.ramp(t=t, initial=0.0, final=9.0, duration=duration/4, samplerate=1e6)
            t += test_ao_1.ramp(t=t, initial=9.3, final=-9.0, duration=duration/2, samplerate=1e6)
            t += test_ao_1.ramp(t=t, initial=-9.3, final=0.0, duration=duration/4, samplerate=1e6)

if False: # reset all test channels
    t += dt
    for ao in ch_ao:
        ao.constant(t, 0)
        t+=dt
    for do in ch_do:
        do.go_low(t)
        t+=dt
#
# # Stop the experiment shot with stop()
# # no waiting time needed
stop(t)

if check_ramp: # compare generated ramps
    times0 = np.array(primary._pseudoclock.times[primary._clockline])
    times1 = np.array(secondary._pseudoclock.times[secondary._clockline])
    data0 = test_ao_0.raw_output
    data1 = test_ao_4.raw_output
    if (len(data0) != len(times0)) or (len(data1) != len(times1)) or (len(times0) != len(times1)):
        print('unequal length data0/times0 %i/%i != data1/times1 %i/%i' % (len(data0),len(times0),len(data1),len(times1)))
    else:
        print('data and time length equal %i' % (len(times0)))
        data_non_equal = (data0 != data1)
        time_non_equal = (times0 != times1)
        non_equal = data_non_equal | time_non_equal
        if any(non_equal):
            index = np.arange(len(times0))[time_non_equal]
            if any(time_non_equal): print('%i/%i time different! max difference %e' % (len(index), len(times0), np.max(np.abs(times0-times1))))
            index = np.arange(len(times0))[data_non_equal]
            if any(data_non_equal): print('%i/%i data different! max difference %e' % (len(index), len(times0), np.max(np.abs(data0-data1))))
            index = np.arange(len(times0))[non_equal]
            print('total %i/%i differences' % (len(index), len(times0)))
            if len(index) < 20: irange = [index]
            else: irange = [index[0:10],index[-10:]]
            print('sample:        time0        data0        time1        data1        t1-t0        d1-d0')
            for irng in irange:
                for j,i in enumerate(irng):
                    print('%6i: %12.6f %12.6f %12.6f %12.6f %12.6e %12.6e' % (i, times0[i], data0[i], times1[i], data1[i], times1[i]-times0[i], data1[i]-data0[i]))
        else:
            print('data equal!')
    print('done')