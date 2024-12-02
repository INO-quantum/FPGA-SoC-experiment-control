#!/usr/bin/python

# experiment script to test NI_DAQmx devices with labscript
# using internal clock of devices / chassis
# use NI_DAQmx_internal_clock which simulates pseudoclock device

# TODO: use modified version of <python-path>/labscript-devices/NI_DAQmx/blacs_workers.py
#       you should find this in the present project folder

########################################################################################################################
# general imports

import numpy as np
from labscript import start, stop, add_time_marker, LabscriptError, AnalogOut, DigitalOut

########################################################################################################################
# import connection table.
# TODO: update the experiment name <NI_DAQmx_text> with your actual name

from labscript_utils import import_or_reload
import_or_reload('labscriptlib.BaLi_experiment.test pseudoclock.connection_table')

########################################################################################################################


# experimental sequence

if __name__ == '__main__':

    t = 0.0
    dt = 10e-6
    us = 1e-6
    ms = 1e-3
    # start sequence
    start()

    # define smallest time steps
    #TODO: without factor 2 I get random errors!
    #      definition of labscript clock_limit is unclear?
    #      maybe one has to init board with clock_limit = 2x max. sample rate?
    #dt      = 2.0/NI_board0.clock_limit # fast
    
    if True:
        dt_slow = 2.0/NI_board1.clock_limit # slow

        # load do and ao from globals.
        # in a typical experiment you give a proper name of you channel in connection_table.
        g = globals()['__builtins__'] # somehow labscript stores these as builtins?
        do = [g['do%i'%i] for i in range(32)] # board0 = fast
        #do_slow = [g['do%i'%i] for i in range(32,34)] # board1 = slow
        ao = [g['ao%i'%i] for i in range(32)] # board1,2 = slow

        # define some times in seconds
        wait_between_digital = True

       
        #experiment_time = 5   # for >30s we run out of memory!
        
       
        t+=50*ms
        
        do2.go_high(t)
        t+=500*ms
        do2.go_low(t)
        t+=1.3
        ao28.constant(t,3)
        t+=1.5
        ao28.constant(t,0)
        t+=1               
    
        #do a ramps
        #t += ao60.ramp(t, 5.0, 0, 5, samplerate=1000) 
        
        #t+= ao28.ramp(t, 5.0, offset_voltage, offset_voltage+5, samplerate=10) 
        #t += 1
        #t+= ao24.ramp(t, 5.0, 0, 5, samplerate=1000) 
        
        DO_pulseSeq_duration = 5
        n_DO_pulses = 20

        totDO = DO_pulseSeq_duration/n_DO_pulses #total time of DO pulse, high_time + low_time
        t += 1
        i=0
        print(totDO)
        for i in range(n_DO_pulses):
            do2.go_high(t)
            t+=totDO/2
            do2.go_low(t)
            t+=totDO/2
            
        t +=1.5
        do2.go_high(t)
        t+=50*ms
        do2.go_low(t)


        ao28.constant(t,0)
        
            
    else:
        t+=1
                
   
    
    print(f"Total time: {t}")
    # stop sequence
    stop(t + dt)


