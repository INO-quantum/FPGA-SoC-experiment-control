#!/usr/bin/python

# experiment script using custom linear ramp to avoid time conflicts in labscript
# TODO: adapt for your experiment and control system. 
#       this is for experimen FPGA_test and for FPGA_device control system

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

from labscriptlib.FPGA_test.connection_table import primary, board_alt, pb0, pb0_trg, pb0_ch1

########################################################################################################################
# helper functions

def precise_ramp(t, duration, initial, final, rate, name):
    """
    linear ramp with fixed sample rate.
    intermediate points are kept constant.
    this allows 'interleaved ramps' without time collisions.
    """
    #print(name, t)
    if initial   > AO_MAX: initial = AO_MAX
    elif initial < AO_MIN: initial = AO_MIN
    if final     > AO_MAX: final   = AO_MAX
    elif final   < AO_MIN: final   = AO_MIN
    if isinstance(t, np.ndarray):
        return np.where(t < duration, initial + np.floor(t*rate)/rate*(final-initial)/duration, [final]*len(t))
    else:
        if t < duration: return initial + np.floor(t*rate)/rate*(final-initial)/duration
        else:            return final

def generate_pulses(channel, t_start, t_duration, rate, first = 1, last = 0):
    """
    create on/off pulses with given rate in samples/s on the given channel from t_start in seconds for t_duration time.
    this is much more efficient than to call channel.go_high() and channel.g_low() in a loop.
    the first and last sample level can be changed from default high and low respectively.
    t_duration is an upper limit and is t_start + samples/rate with samples = floor(t_duration*rate)
    and if first != last and samples is odd samples -= 1
    and if first == last and samples is even samples -= 1
    returns actual duration in seconds.
    this is similar as labscript.repeat_pulse_sequence and functions.pulse_sequence but without interpolation.
    """
    samples = int(np.floor(t_duration * rate))
    if ( first != last ) and (samples & 1) == 1: samples -= 1 # want even samples
    if ( first == last ) and (samples & 1) == 0: samples -= 1 # want odd samples
    t_end = t_start + samples/rate
    times = np.linspace(t_start, t_end, samples)
    states = np.array([1, 0] if first != 0 else [0, 1], dtype=np.int8)
    states = np.tile(states, 1 + samples // 2)[:samples]
    print([len(times),len(states)])
    #print(np.transpose([times, states]))
    #print(samples)
    if False: # try to do it manually (not finished)
        def pulses(t):
            print('time = ', t)
            # function is called once with a scalar and once with a list???
            try:
                len(t)
                print('indices', np.array(np.floor((t - t_start) * rate), dtype = int))
                print('states = ', states[np.array(np.floor((t - t_start) * rate), dtype = int)])
                #return states[np.array(np.floor((t - t_start) * rate), dtype = int)]
                return np.array(np.floor((t - t_start) * rate), dtype=int) & 1
            except TypeError:
                return 0
        channel.add_instruction(t_start,
                             {'function': pulses, 'description': 'pulses',
                              'initial time': t_start, 'end time': t_end, 'clock rate': rate, 'units': None})
    else:
        # use repeat_pulse_sequence. this interpolates data which is not really needed.
        # this might generate not exactly the number of samples and times intended?
        channel.repeat_pulse_sequence(t_start, samples / rate, np.transpose([times, states]), (samples + 1) / rate, rate)
    return samples/rate

def quantize(time, offset):
    "returns time as next lower integer multiple of offset"
    return (time//offset)*offset

from user_devices.mogdevice import MOGDevice

def MOG_test():
    import time

    # Connect to device
    dev = MOGDevice('192.168.1.190')
    print('Device info:', dev.ask('info'))

    channel = 1  # channel 1-4
    frequency = 10.0  # frequency in MHz
    amp = [-10.0, 0.0]  # [minimum,maximum,step] amplitude in dBm
    phase = 0.0  # phase in degrees
    duration = 0  # duration in 5us units, 0 = wait for trigger for each step
    steps = 4  # number of steps

    dev.cmd('OFF,%i' % channel)

    if True: # RF on/off mode
        dev.cmd('MODE,%i,NSB' % (channel)) # standard mode
        #dev.cmd('TABLE,STOP,%i' % channel)  # stop tablemode
        dev.cmd('FREQ,%i,%.3fMHz' % (channel, frequency))
        dev.cmd('POW,%i,%.3fdBm' % (channel, amp[-1]))
        dev.cmd('PHASE,%i,%.3fdeg' % (channel, phase))
        #dev.cmd('ON,%i,POW' % (channel))
        dev.cmd('ON,%i,ALL' % (channel)) # one has to switch RF on, while TTL is low is kept off however
    else:
        # construct the pulse
        ramp = np.linspace(amp[0], amp[1], steps)  # 0 to 10 dBm
        ramp = np.concatenate((ramp, [-50]))
        print(ramp)

        dev.cmd('MODE,%i,TSB' % channel)  # set channel into table mode
        dev.cmd('TABLE,CLEAR,%i' % channel)  # clear entries in existing table
        dev.cmd(
            'TABLE,EDGE,%i,RISING' % channel)  # set trigger edge rising or falling (works with firmware 0.5.3 but not with 0.5.1)
        dev.cmd('TABLE,REARM,%i,on' % channel)  # enable rearming of the table as soon as the table is finished
        if True:
            dev.cmd(
                'TABLE,RESTART,%i,on' % channel)  # restart table after was re-armed. this way needs same number of triggers as table entries.

        for i, amp in enumerate(ramp):
            print([i, amp])
            if True:
                cmd = 'TABLE,APPEND,%i,%.3fMHz,%.3fdBm,%.3fdeg,%i' % (channel, frequency, amp, phase, duration)
            else:
                cmd = 'TABLE,ENTRY,%i,%i,%.3fMHz,%.3fdBm,%.3fdeg,%i' % (channel, i+1, frequency, amp, phase, duration)
                #cmd = 'TABLE,ENTRY,%i,%i,%iHz,%i,%i,%i' % (channel,i+1,frequency,amp,phase,duration) # this returns always invalid table entry!? whatever I try
            print(cmd)
            ret = dev.cmd(cmd)
            print(ret)

        if True: # test change last entry
            i = len(ramp) - 1
            amp = -10
            cmd = 'TABLE,ENTRY,%i,%i,%.3fMHz,%.3fdBm,%.3fdeg,%i' % (channel, i + 1, frequency, amp, phase, duration)
            # cmd = 'TABLE,ENTRY,%i,%i,%iHz,%i,%i,%i' % (channel,i+1,frequency,amp,phase,duration) # this returns always invalid table entry!? whatever I try
            print(cmd)
            ret = dev.cmd(cmd)
            print(ret)

        if False:  # power off
            dev.cmd(f'TABLE,APPEND,%i,%iHz,0x0,0,0' % (channel, frequency))

        if False:
            dev.cmd('TABLE,ARM,%i' % channel)
        else:
            dev.cmd('TABLE,TIMESYNC,%i' % channel)  # the older manual says 'TABLE,TRIGSYNC' but which does not work!

        if False:
            dev.cmd('TABLE,STOP,%i' % channel)  # stop table at end

    dev.close()

if False:
    TTL0 = [MOT_IGBT_no0per1_on, FB_Helmholtz_no0per2_on,MOT_Helmholtz_no0per3_on,
            Cr_ZS_current_no0per4_on,Cr_MOT_AOM_no0per5_on,Cr_TC_AOM_no0per6_on,
            Cr_ZS_AOM_no0per7_on,Cr_mf_pump_no0per8_on,Li_ZS_current_no0per9_on,
            Cr_Andor_trigger_no0per10_on,Li_D2_no0per11_on,Li_D1_no0per12_on,
            Li_MOT_shutter_no0per13_on,img_shutter_no0per14_on,Blue_shutter_no0per15_on,
            FB_IGBT_no0per16_on
    ]
    TTL1 = [
        Stingray_no1per1_on, Li_ZS_AOM_no1per2_on, CrRepumpers_AOMshutter_no1per3_on,
        Li_oven_shutter_no1per4_on, Li_Cooler_no1per5_on, Cr_R1_no1per6_on, Cr_R2_no1per7_on,
        Cr_img_shutter_no1per8_on, Li_img_AOM_no1per9_on, Li_Rep_no1per10_on,
        Current_Green_no1per11_off, Li_img_HF_AOM_no1per12_on, CrRepumpers_Servoshutter_no1per13_on,
        Green_AOM_TTL_no1per14_on, IR_AOM_TTL_no1per15_on, Osci_trigger_no1per16_on]

if __name__ == '__main__':

    if primary is not None:
        t = primary.start_time
        dt = primary.time_step
    else:
        t = 0.0
        dt = 1e-6;

    # start sequence
    start()

    if True:
        # precise ramp test
        # this allows to generate 'interleaved ramps' with constant sample rate without generating time confilcts.

        # the problem with labscript 'ramp' is that labscript generates for all outputs (on the same clockline)
        # values for all times used in any channel. But since our board can execute only one command per time,
        # generate_code above takes only the data where a channel is changing and ensures that no channels change at the same time.
        # this works well for static channels, but with labscript 'ramp' whenever any command is executed in parallel,
        # or a second ramp is executed in parallel, we would get time confilcts since labscript recalculates the ramp values
        # also for these intermediate points outside of the set samplerate, i.e. the value then changing and
        # generate_code will not remove these points which will eventually lead to the time conflict.
        # the solution with precise_ramp is simply to enforce the set samplerate (called 'rate') even when intermediate values are calculated.
        # you have to give two rates to customramp:
        # 'rate' = the true output rate, i.e. the rate of change of the output.
        #   1/rate must be integer multiple of channels*t_ch_offset,
        #   with channels = number of channels which change in parallel,
        #   t_ch_offset = time slot per channel (integer multiple of dt, minimum dt)
        # 'samplerate' = the time resolution of the ramp.
        #   labscript rounds all output times to this resolution.
        #   therefore, this must be <= 1/t_ch_offset.
        # note: conversion from float to integer might still cause time conflicts for high-resolution ramps?
        #   increase t_ch_offset or try increasing samplerate (max. 1/dt).

        # example code with mixture of analog and digital channels operated in parallel.
        # note that 1/analog_ramp_rate and on_duration must be integer multiple of channels * t_ch_offset

        ao_list = [ao0, ao1, ao2, ao3]
        do_list = [do0, do1, do2, do3]
        channels = len(ao_list) + len(do_list)  # number of parallel channels
        # get time offset per channel.
        t_ch_offset = dt # time offset between channel
        t_offset = {}
        for i, channel in enumerate(ao_list + do_list):
            t_offset[channel.name] = i*t_ch_offset
            print("channel %i: '%-35s' time slot %i us" % (i, channel.name, t_offset[channel.name]*1e6))
        ramp_duration = 5.1 # fastest is (2^16us)/channels = (0.065536s)/channels
        analog_ramp_rate = 1/(channels*t_ch_offset) # we go at maximum sample rate
        digital_toggles = 10; # for digital we go slower and toggle state this times
        on_duration = quantize(ramp_duration / (2*digital_toggles), t_ch_offset*channels)
        # parallel analog ramps
        for i,ao in enumerate(ao_list):
            if (i & 1) == 0:
                start = -10
                end   = 10
            else:
                start = 10
                end  = -10
            ao.customramp(t + t_offset[ao.name], function=precise_ramp, initial=start, final=end, duration=ramp_duration, samplerate=1/t_ch_offset, rate=analog_ramp_rate, name='ananlog ramp %i'%i)
        # parallel digital outputs
        #t += 5.0
        for i,do in enumerate(do_list):
            for j in range(digital_toggles):
                do.go_high(t + t_offset[do.name] + 2*j*on_duration)
                do.go_low (t + t_offset[do.name] + (2*j+1)*on_duration)
        # shortest time after ramps finished
        t += (channels-1) * t_ch_offset + ramp_duration + dt

    if False: # analog ramp test
        check_ramp = True  # compare generated ramps after stop()
        samples = 2**10  # the true number of samples can be larger (typically by 1-2, but depends on number of samples)
        t_step = dt * 50
        duration = samples * t_step
        t = 0.0
        # ramp all channels
        do = [do0, do1, do2, do3]
        ao = [ao0, ao1, ao2, ao3]
        for i,ao in enumerate(ao):
            do[i].go_high(t)
            t += dt
            t += ao.ramp(t=t, initial=  0.0, final= 10.0, duration=1*duration, samplerate=1 / t_step) + dt
            t += ao.ramp(t=t, initial= 10.0, final=-10.0, duration=2*duration, samplerate=1 / t_step) + dt
            t += ao.ramp(t=t, initial=-10.0, final=  0.0, duration=1*duration, samplerate=1 / t_step) + dt
            do[i].go_low(t)
            t += dt

    # stop sequence
    stop(t + dt)


