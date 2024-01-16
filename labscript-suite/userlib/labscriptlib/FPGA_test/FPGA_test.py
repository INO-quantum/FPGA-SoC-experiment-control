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

# load do and ao from globals.
# in a typical experiment you give a proper name of you channel in connection_table.
g = globals()['__builtins__'] # somehow labscript stores these as builtins?
num_analog = 4 if secondary is None else 8
num_digial = 16 if secondary is None else 32
do = [g['do%i'%i] for i in range(num_digital)] 
ao = [g['ao%i'%i] for i in range(num_analog)]

if __name__ == '__main__':

    t = primary.start_time
    dt = primary.time_step

    # start sequence
    start()

    # define some experiment parameters
    do_ramp              = True     # perform triangular ramp on all analog channels
    ramp_rate            = 100e3    # sample rate in Hz
    wait_between_digital = False    # wait for each channel when switching digital channels on/off
    experiment_time      = 3.0      # (approximate) experiment time in seconds

    # switch all digital outputs on
    # this can be done all together or one by one
    if True:
        for doi in do:
            doi.go_high(t)
            if wait_between_digital:
                t += dt
                
    if do_ramp:
        # do a triangular ramp on all channels separated by dt
        t_start = t
        duration = experiment_time - t - dt
        for i,aoi in enumerate(ao):
            t = t_start + i*dt
            t += aoi.ramp(t=t, initial=  0, final= 10, duration=duration/4, samplerate=ramp_rate) + 1/ramp_rate
            t += aoi.ramp(t=t, initial= 10, final=-10, duration=duration/2, samplerate=ramp_rate) + 1/ramp_rate
            t += aoi.ramp(t=t, initial=-10, final=  0, duration=duration/4, samplerate=ramp_rate) + dt
    
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
        t = experiment_time
        for doi in do:
            doi.go_low(t)
            if wait_between_digital:
                t += dt

    # stop sequence
    stop(t + dt)


