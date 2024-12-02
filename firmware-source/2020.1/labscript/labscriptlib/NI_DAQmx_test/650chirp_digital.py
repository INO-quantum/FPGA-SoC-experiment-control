#!/usr/bin/python

# experiment script to test NI_DAQmx devices with labscript
# using internal clock of devices / chassis
# use NI_DAQmx_internal_clock which simulates pseudoclock device

# TODO: use modified version of <python-path>/labscript-devices/NI_DAQmx/blacs_workers.py
#       you should find this in the present project folder

########################################################################################################################
# general imports

import numpy as np
#import AC_Mod_E12_triangle as tr
from labscript import start, stop, add_time_marker, LabscriptError, AnalogOut, DigitalOut

########################################################################################################################
# import connection table.
# TODO: update the experiment name <NI_DAQmx_text> with your actual name

from labscript_utils import import_or_reload
import_or_reload('labscriptlib.NI_DAQmx_test.connection_table')

def generate_pulses(channel, t_start, sample_rate, times, values=[1,0]):
    """
    create digital pulses on the channel from t_start for t_duration with sample_rate.
    returns last used time in seconds.
    channel     = digital output channel
    t_start     = start time in seconds. the first sample is always created at this time.
                  following samples at t_start + integer multiple of 1/sample_rate.
    sample_rate = maximum sample rate in samples/s.
    times       = if single time in seconds given:
                    a sample for each t = t_start + N*1/sample_rate time is generated
                    for N integer and t <= times.
                  if a list is given:
                    time in seconds for each corresponding entry in values.
                    times must start at 0.
                    samples are created for each value/time pair rounded to nearest
                    t_start + N*1/sample_rate for N integer and t <= times[-1] + 1/sample_rate.
                    gives an error if several samples are at the same time.
    values      = values (0 or 1) corresponding to times.
                  if times is None:
                    give [starting_value, end_value] with
                    starting_value = first output state (1 by default).
                    ending_value   = last ouput state (0 by default).
                    if needed, the duration is shortened by 1/sample_rate to ensure ending_value is the given state.
    this is much more efficient than to call channel.go_high() and channel.g_low() in a loop.
    this is similar to labscript.repeat_pulse_sequence and functions.pulse_sequence,
    but without resampling at fixed sampling rate, i.e. the number of samples is not changed here!
    """
    if isinstance(times, (float,int)):
        # duration given
        duration = float(times)
        if len(values) != 2:
            print(values)
            raise LabscriptError("generate_pulses called with times=%f which requires values to be a list of 2 values but %i values given!" % (duration, len(values)))
        first,last = values
        samples = int(np.floor(duration * sample_rate))
        if ( first != last ) and (samples & 1) == 1: samples -= 1 # want even samples
        if ( first == last ) and (samples & 1) == 0: samples -= 1 # want odd samples
        t_end = t_start + samples/sample_rate
        times = np.linspace(t_start, t_end, samples)
        values = np.array([1, 0] if first != 0 else [0, 1], dtype=np.int8)
        values = np.tile(states, 1 + samples // 2)[:samples]
    else:
        # time, value pairs given
        if len(times) != len(values):
            raise LabscriptError("generate_pulses called with %i times and %i values but they must have equal length!" % (len(times), len(values)))
        elif times[0] != 0:
            raise LabscriptError("generate_pulses called with first time %f != 0!" % (times[0]))
        samples = len(times)
        t_end = t_start + np.round(times[-1]*sample_rate)/sample_rate
    print('generate_pulses t =',t_start, ', t_end =', t_end, ', rate =', sample_rate, ', # times =', len(times), ', # values =', len(values))
    print('%i samples:' % (samples))
    #print(np.transpose([times, values]))
    # fake rate to force labscript generating only given number of samples
    # t_end is included by labscript, so we must ensure largest index = samples-1
    pseudo_rate = (samples-1)/(t_end-t_start)
    def gen_pulses(t):
        # function is called once with scalar t_end-t_start and once with a numpy array
        if isinstance(t, (int,float)):
            print('times =', t, '(last time delta)' if t == (t_end-t_start) else '')
            t = np.array([t])
        else:
            print('%i times =' % len(t), t, type(t))
        indices = np.round(t * pseudo_rate).astype(int)
        print('indices =', indices)
        print('values =', values[indices])
        return values[indices]
    # note: we give a fake sample rate here to force labscript to generate only samples times
    #       the time given to gen_pulses is then just the index into the list
    if False:
        channel.add_instruction(t_start,
            {'function': gen_pulses, 'description': 'generate pulses',
            'initial time': t_start, 'end time': t_end,
            'clock rate': pseudo_rate, 'units': None}
            )
    else:
        d = dict(zip(times, values))
        d['raw_data'] = (times,values)
        d['initial time'] = t_start
        d['end time'] = t_end
        d['clock rate'] = pseudo_rate
        d['function'] = (lambda x: 0)
        d['units'] = None
        #print(d)
        channel.instructions[t_start] = d
        #channel.go_low(t_end)

    return times[-1]


# Endcap voltages
DC_E11_1D = -(7.0)/2
DC_E12_1D = -(7.03)/2
DC_E11_2D = -(13.9)/2
DC_E12_2D = -(13.72)/2

       
#Chirp parameters
try:
    f_initial = ext1
    f_final = ext2
    ratio_on_off = ext3  # ratio of the time in the cycle when the laser is off. if this is 0.1 it means that 650 is turned off for 10% in each cycle.
except NameError:
    # 100 samples
    f_initial = 7
    f_final   = 10
    # 1M samples
    #f_initial = 70e3
    #f_final   = 100e3
    # 10M samples
    #f_initial = 700e3
    #f_final   = 1000e3
    # test
    f_initial = 10
    f_final   = 100
    ratio_on_off = 0.5

t = 0.0
micro = 1e-6
nano = 1e-9
milli = 1e-3
mega = 1e6
max_AO_rate = 1e6
chirp_digital_samplerate = 10e6
duration_sequence = 10
ramp_samplerate = 200e3
sign_DIG10 = False#Flip the signal for DIG10 since it is on when ttl is 0.

turnOn650 = 0
turnOff650 = 1

DIG0  = digital_out_0
DIG1  = digital_out_1
DIG2  = digital_out_2
DIG3  = digital_out_3
DIG4  = digital_out_4
DIG5  = digital_out_5
DIG6  = digital_out_6
DIG7  = digital_out_7
DIG8  = digital_out_8
DIG9  = digital_out_9
DIG10 = digital_out_10

ao1_0  = analog_out_0
ao1_4  = analog_out_1
ao1_8  = analog_out_2
ao1_12 = analog_out_3
ao1_16 = analog_out_4
ao1_20 = analog_out_5
ao1_24 = analog_out_6
ao1_28 = analog_out_7

def initialize_outputs():
    DIG3.go_high(0)
    DIG4.go_high(0)
    DIG5.go_high(0)
    DIG6.go_low(0)
    DIG7.go_low(0)
    DIG8.go_high(0)
    DIG9.go_low(0)
    DIG10.go_low(0)

    ao1_0.constant(0, DC_E11_1D)#Endcap2.1
    ao1_4.constant(0, DC_E12_1D)#Endcap1.2
    ao1_8.constant(0, DC_E11_1D)#Endcap1.1
    ao1_12.constant(0, DC_E12_1D)#Endcap2.2
    ao1_16.constant(0, 0)
    ao1_20.constant(0, 0)
    ao1_24.constant(0, 0)
    ao1_28.constant(0, 0)

def make_start_signal():#Starting signal for the photon counter
    DIG0.go_high(0)
    #DIG0.go_low(1*micro)

def make_end_signal():#Starting signal for the photon counter
    DIG0.go_high(duration_sequence - 4*micro)
    DIG0.go_low(duration_sequence - 3*micro)
    DIG0.go_high(duration_sequence - 2*micro)
    DIG0.go_low(duration_sequence - 1*micro)


def ramp_from_1d_to_2d(ramp_start_time, ramp_time):
    ao1_0.ramp(ramp_start_time, ramp_time, DC_E11_1D, DC_E11_2D, samplerate=ramp_samplerate) 
    ao1_4.ramp(ramp_start_time, ramp_time, DC_E12_1D, DC_E12_2D, samplerate=ramp_samplerate)

def ramp_from_2d_to_1d(ramp_start_time, ramp_time):
    ao1_0.ramp(ramp_start_time, ramp_time, DC_E11_2D, DC_E11_1D, samplerate=ramp_samplerate) 
    ao1_4.ramp(ramp_start_time, ramp_time, DC_E12_2D, DC_E12_1D, samplerate=ramp_samplerate) 

def chirp(t, duration, f_initial, f_final):
    """
    creates a chirp from f_initial to f_final with changing rate r_rate. all units in Hz.
    amplitude 1V around zero.
    here you can give any mathematical expression as a function of time
    """
    if isinstance(t, list):
        t+=np.array(t)
    return np.sin(2*np.pi*f_initial*t + np.pi*(f_final-f_initial)/duration*t*t)

# This one we cannot set the ratio of on and off time
def chirp_digital_0_crossing(start_time, chirp_duration):
    ramptime = np.arange(0.0, chirp_duration, 1.0/chirp_digital_samplerate)
    chirpvalues=chirp(ramptime, chirp_duration, f_initial, f_final)
    mask = np.sign(chirpvalues) 
    diff = mask[1:] - mask[:-1]
    ind = np.argwhere(diff!=0)
    ind = ind.reshape((len(ind),))
    tau = np.concatenate(([0.0],ramptime[ind[:-1]+1]))#zero crossing of chirp
    values_dig = np.tile([1,0], int((len(tau)+1)//2))[:len(tau)-1]#with odd tau we finish with 1
    values_dig = np.concatenate(([1],values_dig))
    if values_dig[-1] == 0:
        tau = np.concatenate((tau, [chirp_duration]))
        values_dig = np.concatenate((values_dig, [1]))
    if not sign_DIG10:# Flip 0 and 1 since on 650 switch 0 is on and 1 is idling frequency
        values_dig = 1 - values_dig
    print(np.transpose([tau,values_dig]).shape)
    print(np.transpose([tau,values_dig]))
    DIG10.repeat_pulse_sequence(start_time, chirp_duration,np.transpose([tau,values_dig]), period = chirp_duration, samplerate=chirp_digital_samplerate)

def chirp_digital_old(start_time, ramp_time):
    time_now = 0
    timeState = []
    while time_now < start_time + ramp_time:
        freqNow = f_initial + (f_initial - f_initial)*(time_now - start_time)/ramp_time
        cycle_time = 1/freqNow
        off_time = cycle_time*ratio_on_off
        on_time = cycle_time - off_time
        timeState.append([round(time_now, 6), turnOn650])#Time to switch on
        timeState.append([round(time_now+on_time, 6), turnOff650])#Time to switch off
        time_now = time_now + cycle_time
    if timeState[1,-1] == turnOff650: # Make sure to turn on the repumper at the end
        if timeState[0,-1] != round(start_time + ramp_time, 6):
            timeState.append([round(start_time + ramp_time, 6), turnOn650])
        else:
            timeState[1,-1] = turnOn650
#    DIG10.repeat_pulse_sequence(start_time, ramp_time, timeState, ramp_time, 1*mega)
    DIG10.repeat_pulse_sequence(start_time, ramp_time,np.array(timeState), period = ramp_time, samplerate=chirp_digital_samplerate)

def chirp_digital_2(channel, start_time, chirp_duration, f_initial, f_final, ratio_on_off, chirp_digital_samplerate):
    # version from 26/8/2024 which made many troubles
    ramptime = np.arange(0.0, chirp_duration, 1.0/chirp_digital_samplerate)
    chirpvalues=chirp(ramptime, chirp_duration, f_initial, f_final)
    mask = np.sign(chirpvalues)
    diff = mask[1:] - mask[:-1]
    off_index = np.argwhere(diff>0)
    off_index = off_index.reshape((len(off_index),))
    off_time = ramptime[off_index+1]#positive crossing of chirp
    on_time = off_time + 1/(f_initial + (f_final - f_initial)*(off_time - start_time)/chirp_duration)*ratio_on_off
    switch_time_all = np.c_[off_time, on_time].flat[:]
    if on_time[-1] > start_time + chirp_duration:
        switch_time_all = switch_time_all[:-1]
        switch_time_all = np.append(switch_time_all, start_time + chirp_duration)
    on_off = np.tile([1,0],on_time.size)
    # First time has to be 0
    if False:
        if switch_time_all[0] != 0:
            switch_time_all = np.insert(switch_time_all, 0, 0)
            on_off = np.insert(on_off, 0, 0)
        channel.repeat_pulse_sequence(start_time, chirp_duration,np.transpose([switch_time_all,on_off]), period = chirp_duration, samplerate=chirp_digital_samplerate)
    #Andreas fixing on 26_08_24
    #channel = DIG10
    print(switch_time_all[0])
    index = np.argsort(switch_time_all)
    print(np.count_nonzero((switch_time_all[1:]-switch_time_all[:-1])<=0))
    switch_time_all = switch_time_all[index]
    print(np.count_nonzero((switch_time_all[1:]-switch_time_all[:-1])<=0))
    print([switch_time_all[0], switch_time_all[-1]])
    switch_time_all[0] = 0
    print(np.count_nonzero(switch_time_all < 0))
    switch_time_all += start_time
    print('smallest dt', np.min(switch_time_all[1:]-switch_time_all[:-1]))
    mask = np.concatenate(([True],((switch_time_all[1:]-switch_time_all[:-1]) > 200e-9))) & (switch_time_all < (5.0+start_time))
    switch_time_all = switch_time_all[mask]
    print('smallest dt', np.min(switch_time_all[1:]-switch_time_all[:-1]))
    print('chirp_digital add_instruction @ %f - %f (time,value) shape = 2 x %i' % (start_time, switch_time_all[-1], len(switch_time_all)))
    #print('addr %x %x' % (switch_time_all.ctypes.data, on_off.ctypes.data))
    if False:
        for t, value in zip(switch_time_all, on_off):
            if value:
                channel.go_high(t)
            else:
                channel.go_low(t)
    elif False:
        channel.repeat_pulse_sequence(start_time, switch_time_all[-1] - start_time, np.transpose([switch_time_all-start_time, on_off[index][mask]]),
                                      period=chirp_duration,
                                      samplerate=1e6 #(len(switch_time_all)-1)/chirp_duration
        )
    else:
        # insert directly pair of [time,value]. requires labscript to be changed.
        #if len(switch_time_all) < 260:
        #    print(np.transpose([switch_time_all, on_off]))
        channel.add_instruction(start_time, [switch_time_all, on_off[index][mask]], units=None)


# def chirp_digital_0_crossing(start_time, chirp_duration):
#     ramptime = np.arange(0.0, chirp_duration, 1.0/chirp_digital_samplerate)
#     chirpvalues=chirp(ramptime, chirp_duration, f_initial, f_final)
#     mask = np.sign(chirpvalues) 
#     diff = mask[1:] - mask[:-1]
#     on_time = np.argwhere(diff>0)
#     on_time = on_time.reshape((len(ind),))
#     off_time = on_time + 

#     tau = np.concatenate(([0.0],ramptime[ind[:-1]+1]))#zero crossing of chirp
#     values_dig = np.tile([1,0], int((len(tau)+1)//2))[:len(tau)-1]#with odd tau we finish with 1
#     values_dig = np.concatenate(([1],values_dig))
#     if values_dig[-1] == 0:
#         tau = np.concatenate((tau, [chirp_duration]))
#         values_dig = np.concatenate((values_dig, [1]))
#     if not sign_DIG10:# Flip 0 and 1 since on 650 switch 0 is on and 1 is idling frequency
#         values_dig = 1 - values_dig
#     DIG10.repeat_pulse_sequence(start_time, chirp_duration,np.transpose([tau,values_dig]), period = chirp_duration, samplerate=chirp_digital_samplerate)

def chirp_digital(analog, digital, start_time, chirp_duration, f_initial, f_final, ratio_on_off, chirp_digital_samplerate, function='add_instruction'):
    ramptime = np.arange(0.0, chirp_duration, 1.0/chirp_digital_samplerate)
    chirpvalues=chirp(ramptime, chirp_duration, f_initial, f_final)
    mask = np.sign(chirpvalues) 
    diff = mask[1:] - mask[:-1]
    off_index = np.argwhere(diff>0)
    off_index = off_index.reshape((len(off_index),))
    off_time = ramptime[off_index+1]#positive crossing of chirp
    on_time = off_time + 1/(f_initial + (f_initial - f_initial)*(off_time - start_time)/chirp_duration)*ratio_on_off
    switch_time_all = np.c_[off_time, on_time].flat[:]
    if on_time[-1] > start_time + chirp_duration:
        switch_time_all = switch_time_all[:-1]
        switch_time_all = np.append(switch_time_all, start_time + chirp_duration)
    on_off = np.tile([1,0],on_time.size)
    #print('chirp_digital: (value,time).shape = ', np.transpose([switch_time_all,on_off]).shape)
    #print(np.transpose([switch_time_all,on_off]))
    switch_time_all[0] = 0
    if False:
        channel.repeat_pulse_sequence(start_time, chirp_duration,np.transpose([switch_time_all,on_off]), period = chirp_duration, samplerate=chirp_digital_samplerate)
    if False:
        print(start_time + switch_time_all)
        print(on_off)
        generate_pulses(channel, start_time, chirp_digital_samplerate, switch_time_all, on_off)

    print('chirp_digital add_instruction @ %f - %f (time,value) shape = 2 x %i' % (start_time, start_time + switch_time_all[-1], len(switch_time_all)))
    print('addr 0x%x 0x%x' % (switch_time_all.ctypes.data, on_off.ctypes.data))
    if function == 'loop':
        # loop over time and values
        # this is very slow for many instructions but does not use a lot of memory
        if analog is not None:
            for t, value in zip(start_time + ramptime, chirpvalues):
                analog.constant(t, value)
        if digital is not None:
            for t, value in zip(start_time + switch_time_all, on_off):
                if value:
                    digital.go_high(t)
                else:
                    digital.go_low(t)
    elif function == 'pulse_sequence':
        # use repeat pulse sequence
        # sample rate has to be increased to fulfill the timing requirements
        # this increases memory a lot
        digital.repeat_pulse_sequence(start_time, switch_time_all[-1],
                                      np.transpose([switch_time_all, on_off]),
                                      period=chirp_duration,
                                      #samplerate=(len(switch_time_all)-1)/chirp_duration
                                      samplerate=10e6
                                      )
    elif function == 'add_instruction':
        ramptime += start_time
        switch_time_all += start_time
        # insert directly pair of (time,value). requires labscript to be changed.
        if True and (len(switch_time_all) <= 150):
            print(np.transpose([switch_time_all, on_off]))
        if analog is not None:
            analog.add_instruction(start_time, [ramptime, chirpvalues], units=None)
        if digital is not None:
            digital.add_instruction(start_time, [switch_time_all, on_off], units=None)

if __name__ == '__main__':
    # start sequence
    start()

    # define smallest time steps
    #TODO: without factor 2 I get random errors!
    #      definition of labscript clock_limit is unclear?
    #      maybe one has to init board with clock_limit = 2x max. sample rate?
    #dt      = 2.0/NI_board0.clock_limit # fast
    

    initialize_outputs()
    make_start_signal()
    ramp_from_1d_to_2d(1.75, 0.5)

    #chirp_digital_0_crossing(3.25, 6)
    chirp_digital(analog            = None, #analog_out_4,
                  digital           = digital_out_4,
                  start_time        = 2.5,
                  chirp_duration    = 6.0,
                  f_initial         = 250e3,
                  f_final           = 500e3,
                  ratio_on_off      = 0.5,
                  chirp_digital_samplerate=10e6,
                  function = ['loop','pulse_sequence','add_instruction'][1]
                  )
    if False:
        chirp_digital(analog            = None, #analog_out_8,
                      digital           = digital_out_8,
                      start_time        = 3.5,
                      chirp_duration    = 1.0,
                      f_initial         = 100e3,
                      f_final           = 70e3,
                      ratio_on_off      = 0.5,
                      chirp_digital_samplerate=10e6,
                      function = ['loop','pulse_sequence','add_instruction'][2]
                      )

    #analog_out_8.ramp(2.5, 3.9, -10, 10, 1e6)

    DIG9.go_high(5.5)
    DIG9.go_low(6.0)
    DIG9.go_high(0.28)
    DIG0.go_low(5.0)
    DIG0.go_high(5.2)
    #chirp_digital(DIG9, 6, 6)

    ramp_from_2d_to_1d(9.25, 0.5)
    make_end_signal()

    # stop sequence
    #stop(duration_sequence)
    stop(10)


