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

########################################################################################################################
#aoBoard1CH = { "ao0": 0, "ao1": 4, "ao2": 8, "a3": 12, "ao4": 16, "ao5": 20, "ao6": 24, "ao7": 28}
AOBoard1CH = { "AO0": ao0, "AO1": ao1, "AO2": ao2, "AO3": ao3, "AO4": ao4, "AO5": ao5, "AO6": ao6, "AO7": ao7}
#aoBoard2CH = { "ao0": 32, "ao1": 36, "ao2": 40, "a3": 44, "ao4": 48, "ao5": 52, "ao6": 56, "ao7": 60}
DOBoard1CH = { "P0.0": do32, "P0.1": do33}
#DOBoard0CH = { "DO0": do0, "DO1": do1,"DO2": do2, "DO3": do3, "DO4": do4, "DO5": do5, "DO6": do6, "DO7": do7, "DO8": do8, "DO9": do9, "DO10": do10, "DO11": do11, "DO12": do12, "DO13": do13,  "DO14": do14, "DO15": do15, "DO16": do16, "DO17": do17, "DO18": do18, "DO19": do19,  "DO20": do20, "DO21": do21, "DO22": do22, "DO23": do23, "DO24": do24, "DO25": do25, "DO26": do26, "DO27": do27, "DO28": do28, "DO29": do29, "DO30": do30, "DO31": do31 }

# experimental sequence

if __name__ == '__main__':

    t = 0.0
    dt = 10e-6
    us = 1e-6
    ns = 1e-9
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
        ao = [g['ao%i'%i] for i in range(8)] # board1,2 = slow

        if False:
            t+= ao28.ramp(t, 30*us, offset_voltage, offset_voltage + max_voltage_second_ramp, samplerate=1e6) 
            ao28.constant(t,5)
            t += 1
            t+= ao28.ramp(t, 30*us, 5, 0, samplerate=1e6) 

            t+= ao36.ramp(t, 30*us, offset_voltage, offset_voltage + max_voltage_second_ramp, samplerate=1e6) 
            ao36.constant(t,5)
            t += 2
            t+= ao36.ramp(t, 30*us, 5, 0, samplerate=1e6) 
       

        DOBoard1CH["P0.0"].go_high(t) #Dig 01: do0 is the channel reserved to the photon counter 
        t+=1000*us
        DOBoard1CH["P0.0"].go_low(t)
        
        t += 1*us
    
        if True:
            pulseSeq_duration = 0.50
            DO_rate = 2.5e6

            pulse_time = 1 / DO_rate  # total time of DO pulse, high_time + low_time
            if True:
                # repeat a simple pulse sequence for a given duration
                # this needs much less compilation time than individual pulses

                # list with (time,state)
                pulses = [(0.0,0),(pulse_time/2,1)]
                # length of pulses + hold time of last pulse
                pulses_period = pulses[-1][0]+pulse_time/2
                t += do1.repeat_pulse_sequence(t=t,
                                          duration=pulseSeq_duration,
                                          pulse_sequence=pulses,
                                          period=pulses_period,
                                          samplerate=DO_rate)

            else:
                # this takes very long for compilation
                n_DO_pulses = pulseSeq_duration / pulse_time

                for i in range(int(n_DO_pulses)):
                    DOBoard1CH["P0.0"].go_high(t)
                    t+=pulse_time/2
                    DOBoard1CH["P0.0"].go_low(t)
                    t+=pulse_time/2

    
        if False:
            high = 128*ns
            low = 138*ns
            n_pulses = 2
            for i in range(n_pulses):
                do0.go_high(t)
                t+=high
                do0.go_low(t)
                t+=low
        
        
                
        if False:                
            do4.go_high(t)
            t+=high_time*ns
            do4.go_low(t)
            t+=low_time*ns

        
       
            
    else:
        t+=1
                
   
    
    print(f"Total time: {t}")
    # stop sequence
    stop(t + dt)


