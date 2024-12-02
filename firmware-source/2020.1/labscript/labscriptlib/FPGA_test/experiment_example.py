#!/usr/bin/python

# 2022/02/16, 08:37:18
# automatically generated labscript experimental sequence from 'Andi_test.prg'
# command line: 'LVparser.py -p ./20220216_labview_prg -f Andi_test.prg -a ListOfActionAnalog.txt -d ListOfActionTTL.txt -o connection_table.py -l {'IR laser #3 (W)':[7.1,200.0],'Crossed Green #19 (W)':[0.1,100.0]}'

########################################################################################################################
# imports

import numpy as np
from labscript import start, stop, add_time_marker, LabscriptError, AnalogOut, DigitalOut
from user_devices.FPGA_device import FPGA_board, DigitalChannels, AnalogChannels, PRIMARY_IP, SECONDARY_IP, DEFAULT_PORT, AO_MIN, AO_MAX
from user_devices.generic_conversion import generic_conversion

########################################################################################################################
# in experimental sequcnce file uncomment this section and remove board and channel definitions below
from labscript_utils import import_or_reload
import_or_reload('labscriptlib.FPGA_test.connection_table')

from labscriptlib.FPGA_test.connection_table import primary #, secondary

########################################################################################################################
# experimental sequence

def precise_ramp(t, duration, initial, final, rate, name):
    """
    linear ramp with fixed sample rate.
    intermediate points are kept constant.
    this allows interleaved ramps without time collisions.
    """
    print(name, t)
    if initial   > AO_MAX: initial = AO_MAX
    elif initial < AO_MIN: initial = AO_MIN
    if final     > AO_MAX: final   = AO_MAX
    elif final   < AO_MIN: final   = AO_MIN
    if isinstance(t, np.ndarray):
        return np.where(t < duration, initial + np.floor(t*rate)/rate*(final-initial)/duration, [final]*len(t))
    else:
        if t < duration: return initial + np.floor(t*rate)/rate*(final-initial)/duration
        else:            return final

if __name__ == '__main__':

    t = board0.start_time #note: t is not used here
    dt = board0.time_step

    # start sequence
    start()

    if True:
        # precise ramp test
        # this allows to generate interleaved ramps with constant sample rate without generating time confilcts.
        # the problem with labscript 'ramp' is that labscript generates for all outputs (on the same clockline)
        # values for all times used in any channel. But since our board can execute only one command per time,
        # generate_code above takes only the data where a channel is changing and ensures that no channels change at the same time.
        # this works well for static channels, but with labscript 'ramp' whenever any command is executed in parallel,
        # or a second ramp is executed in parallel we would get time confilcts since labscript recalculates the ramp values
        # also for these intermediate points outside of the set samplerate.
        # the solution with precise_ramp is simply to enforce the set samplerate (called 'rate') even when intermediate values are calculated.
        # you have to give two rates:
        # 'rate' = the true output rate, i.e. the rate of change of the output.
        #          1/rate must be integer multiple of samplerate*num_actions.
        #          with num_actions = number of parallel actions. typically 2 for 2 parallel ramps or for one ramp and a parallel digital I/O
        #          each parallel action i must start at a different 'time slot' with time offset = i*1/samplerate
        # 'samplerate' = the time resolution of the ramp. labview rounds all output times to this resolution!
        #                therefore, this must correspond to time_offset between the ramps as given in the example below.
        # note: conversion from float to integer might cause still time conflicts for high-resolution ramps.
        #       in this case try vary some parameters or reduce the resolution to half the maximum.
        ao0 = Analog_no24_V
        ao1 = Analog_no25_V
        do0 = test_no3per10_on
        do1 = test_no3per11_on
        ramp_offset = 5*dt # offset between ramps. minimum dt.
        ramp_duration = 1.0
        ramp_rate = [1/(ramp_offset*3)]*2 # max rate = 1/(ramp_res*parallel actions)
        # parallel action 0: ramp ao0
        ao0.customramp(t + 0*ramp_offset, function=precise_ramp, initial=0.0, final=10.0, duration=ramp_duration, samplerate=1/ramp_offset, rate=ramp_rate[0], name='ao0')
        # parallel action 1: ramp ao1
        ao1.customramp(t + 2*ramp_offset, function=precise_ramp, initial=10.0, final=0.0, duration=ramp_duration, samplerate=1/ramp_offset, rate=ramp_rate[1], name='ao1')
        # parallel action 2: do0 and do1 (they are in same device and can therefore change simultaneously)
        do0.go_high(t + 0.5 + 1*ramp_offset)
        do0.go_low(t + 0.6 + 1*ramp_offset)
        do1.go_high(t + 0.5 + 1*ramp_offset)
        do1.go_low(t + 0.7 + 1*ramp_offset)
        t += ramp_duration + 3*ramp_offset + dt

    if False: # analog ramp test
        check_ramp = True  # compare generated ramps after stop()
        samples = 2**10  # the true number of samples can be larger (typically by 1-2, but depends on number of samples)
        t_step = dt * 50
        duration = samples * t_step
        t = 0.0
        # ramp all channels
        do = [Stingray_no1per1_on, Li_ZS_AOM_no1per2_on, CrRepumpers_AOMshutter_no1per3_on, Li_oven_shutter_no1per4_on]
        for i,ao in enumerate([test_ao_0,test_ao_1,test_ao_2,test_ao_3]):
            do[i].go_high(t)
            t += dt
            t += ao.ramp(t=t, initial=  0.0, final= 10.0, duration=1*duration, samplerate=1 / t_step) + dt
            t += ao.ramp(t=t, initial= 10.0, final=-10.0, duration=2*duration, samplerate=1 / t_step) + dt
            t += ao.ramp(t=t, initial=-10.0, final=  0.0, duration=1*duration, samplerate=1 / t_step) + dt
            do[i].go_low(t)
            t += dt

    if False: # Andi_test.prg
        Li_oven_shutter_no1per4_on.go_high(0.000001)
        Cr_img_shutter_no1per8_on.go_low(0.000005)
        CrRepumpers_AOMshutter_no1per3_on.go_high(0.000009)
        Li_D1_no0per12_on.go_low(0.000010)
        Cr_AOM_MOT_60to127MHz_no4_MHz.constant(0.000011, 115.3, 'MHz')
        Li_Rep_no1per10_on.go_high(0.000012)
        Cr_AOM_TC_70to115MHz_no5_MHz.constant(0.000013, 122.0, 'MHz')
        Li_MOT_shutter_no0per13_on.go_high(0.000014)
        Li_Cooler_no1per5_on.go_high(0.000016)
        Li_cool_int_no7_percent.constant(0.000018, 100.0, 'percent')
        Li_rep_int_no13_percent.constant(0.000020, 100.0, 'percent')
        Cr_AOM_MOT_int_no16_percent.constant(0.000021, 50.0, 'percent')
        Cr_MOT_AOM_no0per5_on.go_high(0.000023)
        Li_cooling_no10_MHz.constant(0.000024, 83.0, 'MHz')
        Cr_TC_AOM_no0per6_on.go_high(0.000025)
        Li_repumper_no11_MHz.constant(0.000026, 200.0, 'MHz')
        Cr_ZS_AOM_no0per7_on.go_high(0.000027)
        Li_ZS_AOM_no1per2_on.go_high(0.000028)
        Cr_R2_no1per7_on.go_high(0.000029)
        Cr_R1_no1per6_on.go_high(0.000031)
        Li_ZS_AOM_74to140MHz_no12_MHz.constant(0.000032, 85.0, 'MHz')
        Li_D2_no0per11_on.go_high(0.000038)
        Cr_AOM_R1_int_no17_percent.constant(0.000047, 100.0, 'percent')
        CrRepumpers_Servoshutter_no1per13_on.go_high(0.000054)
        CrBlueRep_shutter_no3per4_on.go_high(0.000106)
        Blue_shutter_no0per15_on.go_high(0.000108)
        Comp_coils_Z_ON_no3per3_on.go_high(0.000109)
        Comp_coils_Y_ON_no3per5_on.go_high(0.000111)
        CompCoil_z_no20_A.constant(0.000113, 0.7, 'A')
        Li_oven_shutter_no1per4_on.go_low(0.000313)
        Li_oven_shutter_no1per4_on.go_high(0.000521)
        Li_oven_shutter_no1per4_on.go_low(0.000729)
        Li_oven_shutter_no1per4_on.go_high(0.000833)
        Li_oven_shutter_no1per4_on.go_low(0.000937)
        Osci_trigger_no1per16_on.go_high(1.000000)
        t = 1.0

    # stop sequence
    stop(t + dt)


