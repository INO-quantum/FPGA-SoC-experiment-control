#!/usr/bin/python

########################################################################################################################
# imports

import numpy as np
from labscript import start, stop, add_time_marker, LabscriptError, AnalogOut, DigitalOut
from user_devices.FPGA_device import FPGA_board, DigitalChannels, AnalogChannels, PRIMARY_IP, SECONDARY_IP, DEFAULT_PORT, AO_MIN, AO_MAX
from user_devices.generic_conversion import generic_conversion

from labscript_utils import import_or_reload
import_or_reload('labscriptlib.FPGA_test.connection_table')

from labscriptlib.FPGA_test.connection_table import primary, secondary

########################################################################################################################
# experimental sequence

if True:
    # load do and ao channesl from globals.
    # in a typical experiment you give a proper name of your channel in connection_table. so this is not needed.
    g = globals()['__builtins__'] # somehow labscript stores these as builtins?
    num_analog = 4 if secondary is None else 8
    num_digital = 16 if secondary is None else 32
    do = [g['do%i'%i] for i in range(num_digital)]
    ao = [g['ao%i'%i] for i in range(num_analog)]

if __name__ == '__main__':

    t = primary.start_time
    dt = primary.time_step

    # start sequence
    start()

    if False:
        # these are some examples of options which can be set for each experiment.
        # this is convenient for debugging but permanent settings should be done in connection table worker_args.

        # set start, data stop and restart trigger
        # this is an example for a re-triggerable line-trigger at the start and during experiment
        # you can also use another input as start trigger and set in first data bit 30 (see WAIT command below).
        # this way you can wait for MOT loaded and start with next line trigger.
        primary.set_start_trigger('input 2', 'rising edge')          # start experiment with rising edge at input 2.
        primary.set_stop_trigger('data bits 28-31','offset bit 2')   # stop experiment when data bit 30 is set.
        primary.set_restart_trigger('input 2', 'rising edge')        # restart experiment with next rising edge on input 2.

        # this sets stop bit 30 in data at the given time.
        # digital or analog channels can be still programmed at the same time.
        primary.WAIT(t)

        # for debugging its nice to have a signal when board is running or waiting
        # 'run' = high while running and restart trigger, low while waiting for start trigger
        # 'wait' = high while waiting for start or restart trigger
        # note: depending on board version output buffer is inverting
        primary.set_ctrl_out({'output 1': ('wait', 'low level')})

        # set synchronization primary wait time and secondary phase
        # for primary board use wait time >0 in units of 10ns and phase = 0
        # for secondary board use wait time = 0 and phase_ext can be used to fine-tune on the ns level.
        # phase_det is normally 0 but if you see random jumps of +/-10ns you can adjust this.
        # units of phase = 0..560 in steps of 1 = 0..360° in steps of 360/560°. 360° = 10ns.
        primary.set_sync_params(wait = 0, phase_ext = 0, phase_det = 0)

    # define some experiment parameters
    do_ramp              = True     # perform triangular ramp on all analog channels
    ramp_rate            = 100e3    # sample rate in Hz
    wait_between_digital = False    # wait for each channel when switching digital channels on/off
    experiment_time      = 3.0      # experiment time in seconds

    # switch all digital outputs on
    # this can be done all together or one by one
    if True:
        for doi in do:
            doi.go_high(t)
            if wait_between_digital:
                t += dt
                
    if do_ramp:
        # do a triangular ramp on one analog channel
        channel = ao0
        t += dt
        duration = experiment_time - t - 2*dt - 2/ramp_rate
        t += channel.ramp(t=t, initial=  0, final= 10, duration=duration/4, samplerate=ramp_rate) + 1/ramp_rate
        t += channel.ramp(t=t, initial= 10, final=-10, duration=duration/2, samplerate=ramp_rate) + 1/ramp_rate
        t += channel.ramp(t=t, initial=-10, final=  0, duration=duration/4, samplerate=ramp_rate) + dt
    else:

        # switch all analog outputs to constant values
        # this has to be done one-by-one
        if True:
            t = experiment_time/4
            for i,aoi in enumerate(ao):
                aoi.constant(t,(i+1)*0.1)
                t += dt

        # switch all analog outputs to constant values
        # this has to be done one-by-one
        if True:
            t = experiment_time/2
            for i,aoi in enumerate(ao):
                aoi.constant(t,(i+1)*(-5.0)/len(ao))
                t += dt

        # switch all analog outputs to constant values
        # this has to be done one-by-one
        if True:
            t = experiment_time*3/4
            for i,aoi in enumerate(ao):
                aoi.constant(t, 0.0)
                t += dt

    # switch all digital outputs off
    # this can be done all together or one by one
    if True:
        t = experiment_time - ((len(do)+1)*dt if wait_between_digital else dt)
        for doi in do:
            doi.go_low(t)
            if wait_between_digital:
                t += dt

    # stop sequence
    stop(t + dt)


