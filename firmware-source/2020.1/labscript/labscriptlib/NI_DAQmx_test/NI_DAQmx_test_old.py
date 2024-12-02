#!/usr/bin/python

# experiment script to test NI_DAQmx devices with labscript
# using internal clock of devices / chassis
# use NI_DAQmx_internal_clock which simulates pseudoclock device
# needs update of <python-path>/labscript-devices/NI_DAQmx/blacs_workers.py
# in order to send a contiguous stream of data to the device

########################################################################################################################
# general imports

import numpy as np
from labscript import start, stop, add_time_marker, LabscriptError, AnalogOut, DigitalOut

########################################################################################################################
# import connection table.
# TODO: update the experiment name with your actual name

from labscript_utils import import_or_reload
import_or_reload('labscriptlib.NI_DAQmx_test.connection_table')

########################################################################################################################
# experimental sequence

if __name__ == '__main__':

    t = 0.0
    dt = 1e-6;

    # start sequence
    start()

    # define smallest time steps
    #TODO: without factor 2 I get random errors!
    #      definition of labscript clock_limit is unclear?
    #      maybe one has to init board with clock_limit = 2x max. sample rate?
    dt      = 2.0/NI_board0.clock_limit # fast
    dt_slow = 2.0/NI_board1.clock_limit # slow

    # load do and ao from globals.
    # in a typical experiment you give a proper name of you channel in connection_table.
    g = globals()['__builtins__'] # somehow labscript stores these as builtins?
    do = [g['do%i'%i] for i in range(32)] # board0 = fast
    do_slow = [g['do%i'%i] for i in range(32,34)] # board1 = slow
    ao = [g['ao%i'%i] for i in range(32)] # board1 = slow

    # define some times in seconds
    wait_between_digital = True
    experiment_time = 3.0   # for >30s we run out of memory!

    # switch all digital outputs on
    # this can be done all together or one by one
    if True:
        for doi in do:
            doi.go_high(t)
            if wait_between_digital:
                t += dt
        for doi in do_slow:
            doi.go_high(t)
            if wait_between_digital:
                t += dt_slow

    # switch all analog outputs to constant values
    if True:
        t = experiment_time/4
        for i,aoi in enumerate(ao):
            aoi.constant(t,(i+1)*0.1)
            t += dt_slow

    # switch all analog outputs to constant values
    if True:
        t = experiment_time/2
        for i,aoi in enumerate(ao):
            aoi.constant(t,(i+1)*(-5.0)/len(ao))
            t += dt_slow

    # switch all analog outputs to constant values
    if True:
        t = experiment_time*3/4
        for i,aoi in enumerate(ao):
            aoi.constant(t, 0.0)
            t += dt_slow

    # switch all digital outputs off
    # this can be done all together or one by one
    if True:
        t = experiment_time
        for doi in do:
            doi.go_low(t)
            if wait_between_digital:
                t += dt
        for doi in do_slow:
            doi.go_low(t)
            if wait_between_digital:
                t += dt_slow

    # stop sequence
    stop(t + dt)


