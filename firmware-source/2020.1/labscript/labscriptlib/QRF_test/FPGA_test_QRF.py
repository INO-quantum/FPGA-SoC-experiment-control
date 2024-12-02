#!/usr/bin/python

########################################################################################################################
# imports

import numpy as np
from labscript import (
    start, stop,
    Trigger, AnalogOut, StaticAnalogOut, DigitalOut, StaticDigitalOut, DDS, StaticDDS,
    LabscriptError
)
#from user_devices.FPGA_device import FPGA_board, DigitalChannels, AnalogChannels, PRIMARY_IP, SECONDARY_IP, DEFAULT_PORT, AO_MIN, AO_MAX
#from user_devices.generic_conversion import generic_conversion

########################################################################################################################
# import connection table. give your actual experiment name instead of "QRF_test"
from labscript_utils import import_or_reload
import_or_reload('labscriptlib.QRF_test.connection_table')
from labscriptlib.QRF_test.connection_table import primary

from user_devices.Moglabs_QRF.labscript_devices import (
    QRF, QRF_DDS, MODES,
    MODE_BASIC, MODE_TABLE_TIMED, MODE_TABLE_TIMED_SW, MODE_TABLE_TRIGGERED,
)

########################################################################################################################
# helper functions

from user_devices.mogdevice import MOGDevice

def MOG_test():
    """
    tests direct programming of QRF.
    """
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
        dev.cmd('TABLE,EDGE,%i,RISING' % channel)  # set trigger edge rising or falling (works with firmware 0.5.3 but not with 0.5.1)
        dev.cmd('TABLE,REARM,%i,on' % channel)  # enable rearming of the table as soon as the table is finished
        if True:
            # restart table after was re-armed. this way needs same number of triggers as table entries.
            dev.cmd('TABLE,RESTART,%i,on' % channel)

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

########################################################################################################################
# get all channels in the system and assign into lists of different types

DO                  = []
DO_static           = []
AO                  = []
AO_static           = []
DDS_classic         = []
DDS_basic           = []
DDS_table_timed     = []
DDS_table_timed_sw  = []
DDS_table_triggered = []
for name, channel in globals()['__builtins__'].items():
    if   isinstance(channel, Trigger): # do not program trigger directly!
        print('skip trigger device', channel.name)
    elif isinstance(channel, AnalogOut):            AO                 .append(channel)
    elif isinstance(channel, StaticAnalogOut):      AO_static          .append(channel)
    elif isinstance(channel, DigitalOut):
        if channel.name.endswith('_gate'): # do not program gates directly!
            print('skip gate device', channel.name)
        else:                                       DO                 .append(channel)
    elif isinstance(channel, StaticDigitalOut):     DO_static          .append(channel)
    elif isinstance(channel, QRF_DDS):
        mode_value = MODES[channel.mode_name]
        print("DDS '%s' mode '%s' (%i)" % (channel.name, channel.mode_name, mode_value))
        if   mode_value == MODE_BASIC:              DDS_basic          .append(channel)
        elif mode_value == MODE_TABLE_TIMED:        DDS_table_timed    .append(channel)
        elif mode_value == MODE_TABLE_TIMED_SW:     DDS_table_timed_sw .append(channel)
        elif mode_value == MODE_TABLE_TRIGGERED:    DDS_table_triggered.append(channel)
        else: raise LabscriptError('%s mode %s (%i) unknown!' % (channel.name, channel.mode, mode_value))
    elif isinstance(channel, DDS):
        if hasattr(channel, 'mode_name'): # skip channels of QRF_DDS
            mode_value = MODES[channel.mode_name]
            print("DDS '%s' mode '%s' (%i) - skip" % (channel.name, channel.mode_name, mode_value))
        else:
            print("DDS '%s' classic" % (channel.name))
            DDS_classic.append(channel)
print('%3i AO  total: %2i normal , %2i static' % (len(AO)+len(AO_static), len(AO), len(AO_static)))
print('%3i DO  total: %2i normal , %2i static' % (len(DO)+len(DO_static), len(DO), len(DO_static)))
print('%3i DDS total: %2i classic, %2i basic (fast), %i timed, %i timed (sw), %i triggered' % (
    len(DDS_classic)+len(DDS_basic)+len(DDS_table_timed_sw)+len(DDS_table_timed)+len(DDS_table_triggered),
    len(DDS_classic), len(DDS_basic), len(DDS_table_timed), len(DDS_table_timed_sw), len(DDS_table_triggered)))

########################################################################################################################
# experimental sequence

if __name__ == '__main__':

    t            = 0.0
    dt_slow      = 5e-6
    dt_fast      = 1e-6
    dt_triggered = 10e-6
    dt_classic   = 1e-6

    # start sequence
    start()
    
    if False:
        # upload table to QRF. this needs to be done only 1x.
        MOG_test()

    if True: 
        # invert signals to test final values
        # this way we do not overwrite if 'invert_signals' is defined in globals
        try:
            invert_signals
        except NameError:
            invert_signals = False
        print('invert_signals =', invert_signals)

        if len(AO) > 0:
            # analog triangle ramp settings
            ramp_start_time  = 0.1
            ramp_duration    = 1.0
            ramp_limits      = [-10,10]
            ramp_num         = 3 # number of triangles
            ramp_start       = -10.0 # first channel offset
            ramp_offset      = (ramp_limits[1]-ramp_limits[0])/len(AO) # offset between channels
            ramp_rate        = (ramp_limits[1]-ramp_limits[0])*2*ramp_num/ramp_duration
            ramp_sample_rate = 10e3

        # times, frequency, power and phase used during experiment
        num = 10 # number of data points
        tstart          = 1.2
        times_slow      = tstart + np.linspace(0, num-1, num) * dt_slow
        times_fast      = tstart + np.linspace(0, num-1, num) * dt_fast
        times_classic   = tstart + np.linspace(0, num-1, num) * dt_classic
        times_triggered = tstart + np.linspace(0, num-1, num) * dt_triggered
        freq            = np.linspace(100e6, 200e6, num)
        pwr             = np.linspace(-30, 10, num)
        phase           = np.linspace(0, 360, num)

        if invert_signals:
            ramp_start  = -ramp_start
            ramp_offset = -ramp_offset
            ramp_rate   = -ramp_rate
            freq        = list(reversed(freq))
            pwr         = list(reversed(pwr))
            phase       = list(reversed(phase))

        # switch all digital out on
        # since not all might be on the same address we have to offset them by dt_fast
        for do in DO:
            if invert_signals: do.go_low(t)
            else:              do.go_high(t)
            t += dt_slow

        # triangular ramp on all analog channels for given duration
        # we could use ramp but customramp is more flexible here
        # TODO: on FPGA_board get error that ramps are at the same time!?
        #       looks like samples are taken not offset from start time!?
        def triangle(time, duration, initial, limits, ramp_rate):
            y = initial + np.array(time)*ramp_rate # linear ramp with given rate
            order = np.floor((y - limits[0])/(limits[1]-limits[0])).astype(int)
            if False and isinstance(time, np.ndarray):
                print('%i: %.6f .. %.6f' % (len(time), time[0], time[-1]))
            y = y-order*(limits[1]-limits[0]) # sawtooth signal within limits
            y = np.where(order & 1, limits[0] + limits[1]-y, y) # invert every even ramp
            return y

        for i, ao in enumerate(AO):
            if primary == 'FPGA': # ramps always conflict in time with FPGA although when offset in start time!?
                ao.constant(t, ramp_start+i*ramp_offset)
            else:
                ao.customramp(t=t, function=triangle, duration=ramp_duration,
                              initial=ramp_start+i*ramp_offset, limits=ramp_limits, ramp_rate=ramp_rate,
                              samplerate=ramp_sample_rate)
            t += dt_fast

        if False: # some additional tests
            #QRF_0.trigger(t, duration = 5*dt)
            t += dt_slow
            #QRF_trigger_0.go_high(t)
            t += dt_slow
            #QRF_trigger_0.go_low(t)
            t += dt_slow

        # program classic DDS
        for i, dds in enumerate(DDS_classic):
            for j,ti in enumerate(times_classic):
                dds.setfreq (ti, freq [(i+j) % num])
                dds.setamp  (ti, pwr  [(i+j) % num])
                dds.setphase(ti, phase[(i+j) % num])

        # program basic DDS.
        # frequency, amolitude, phase can only be programmed once per experiment otherwise gives an error!
        # use function without time since this acts as a static DDS.
        # use dds.enable/disable to switch on/off RF fast during experiment.
        # enable/disable signal is given to digital_gate of channel.
        for i, dds in enumerate(DDS_basic):
            dds.setfreq (freq [i % len(freq )])
            dds.setamp  (pwr  [i % len(pwr  )])
            dds.setphase(phase[i % len(phase)])
            print(dds.name, '(static)', '%.3f MHz, %.3f dBm, %.3f °' % (freq [i % len(freq )]/1e6, pwr  [i % len(pwr  )], phase[i % len(phase)]))
            for j,ti in enumerate(times_fast):
                if (i+j) & 1 == 0: dds.enable (ti)
                else:              dds.disable(ti)

        # program timed DDS in table mode.
        # this has 5us resolution.
        # if QRF clock input is not not locked to external clock might drift in time.
        # start trigger is generated on DO_QRF_start for entire QRF (I think must be on channel 1?).
        for i, dds in enumerate(DDS_table_timed):
            for j,ti in enumerate(times_slow):
                dds.setfreq (ti, freq [(i+j) % num])
                dds.setamp  (ti, pwr  [(i+j) % num])
                dds.setphase(ti, phase[(i+j) % num])

        # program timed software started DDS in table mode.
        # these are started by software in table mode.
        for i, dds in enumerate(DDS_table_timed_sw):
            for j,ti in enumerate(times_slow):
                dds.setfreq (ti, freq [(i+j) % num])
                dds.setamp  (ti, pwr  [(i+j) % num])
                dds.setphase(ti, phase[(i+j) % num])

        # program triggered DDS in table mode.
        # this has 5us resolution + jitter.
        # this generates trigger command on digital_gate for each DDS channel at the given time.
        for i, dds in enumerate(DDS_table_triggered):
            for j,ti in enumerate(times_triggered):
                dds.setfreq (ti, freq [(i+j) % num])
                dds.setamp  (ti, pwr  [(i+j) % num])
                dds.setphase(ti, phase[(i+j) % num])

        t += max(times_slow[-1]+dt_slow, times_fast[-1]+dt_fast, times_triggered[-1]+dt_triggered, times_classic[-1]+dt_classic)

        # switch all digital out off
        # since not all might be on the same address we have to offset them by dt_fast
        for do in DO:
            if invert_signals: do.go_high(t)
            else:              do.go_low(t)
            t += dt_fast

    # stop sequence
    t += dt_slow
    print('experiment duration: %.3e seconds' % (t))
    stop(t)


