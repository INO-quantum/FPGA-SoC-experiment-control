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
#import_or_reload('labscriptlib.BaLi_experiment.test pseudoclock.23012024.connection_table')
import_or_reload('labscriptlib.NI_DAQmx_test.connection_table')

########################################################################################################################

def chirp(t, duration, f_initial, f_final, f_rate):
    """
    chirp
    """
    if isinstance(t, list):
        t = np.array(t)
    return np.sin(2 * np.pi * f_initial * t + (f_final - f_initial) * f_rate / duration * t ** 2)

# experimental sequence

if __name__ == '__main__':

    t = 0.0
    dt = 1e-6

    # start sequence
    start()

    # define smallest time steps
    #TODO: without factor 2 I get random errors!
    #      definition of labscript clock_limit is unclear?
    #      maybe one has to init board with clock_limit = 2x max. sample rate?
    #dt      = 2.0/NI_board0.clock_limit # fast

    if True: # if not defined as global variable
        offset_voltage = 0
    
    if True:
        dt_slow = 2.0/NI_board_1.clock_limit # slow

        # define some times in seconds
        wait_between_digital = True
        experiment_time = 5   # for >30s we run out of memory!

        # switch all digital outputs on
        # this can be done all together or one by one

        if True:
            t += 2*dt
            digital_out_0.go_high(t)
            for i in range(3):
                digital_out_1.go_high(t)
                t += dt
                digital_out_1.go_low(t)
                t += dt
            t -= dt
            digital_out_0.go_low(t)
            t += dt

            for i in range(3):
                analog_out_0.constant(t, 1.0 + i*1.0)
                t += dt_slow

        if True:
            #do a ramps
            #t += analog_out_3.ramp(t, 5.0, 0, 5, samplerate=1000) 
            t+= analog_out_0.ramp(t, 1.0, offset_voltage, offset_voltage+5, samplerate=1000)
            t += 1
            t+= analog_out_1.ramp(t, 1.0, 0, 5, samplerate=1000) 

        if False: # TODO: this should give an error but does does not?
            t +=1
            a=0
            azioni=[]
            for tt in range(0,10):
                a += 1
                azioni.append((tt, a%2))

            t += static_digital_out_2.repeat_pulse_sequence(t, 4, azioni, period=float(6.5), samplerate=10)
        #t += dt_slow

        # switch all digital outputs off
        # this can be done all together or one by one

    if True:
        t += analog_out_0.customramp(t, function=chirp, f_initial=100, f_final=1000, duration=1.0, f_rate=100, samplerate=100e3)

    if False:
        # test final values by enabling or disabling this
        t += dt
        # board_0
        digital_out_0.go_high(t)
        digital_out_1.go_low(t)
        digital_out_30.go_high(t)
        digital_out_31.go_low(t)
        # board_1
        digital_out_32.go_high(t)
        digital_out_33.go_high(t)
        analog_out_0.constant(t, 1)
        analog_out_7.constant(t, 2)
        # board_2
        digital_out_34.go_high(t)
        digital_out_35.go_high(t)
        analog_out_8.constant(t, 3)
        analog_out_12.constant(t, 4)
        t += dt

        if True:
            # set some static channels
            static_digital_out_0.go_high()
            static_digital_out_5.go_high()
            static_digital_out_6.go_high()
            static_digital_out_21.go_high()

            static_analog_out_0.constant(1.0)
            static_analog_out_1.constant(2.0)
            static_analog_out_2.constant(3.0)
    else:
        t += dt
        # board_0
        digital_out_0.go_low(t)
        digital_out_1.go_high(t)
        digital_out_30.go_low(t)
        digital_out_31.go_high(t)
        # board_1
        digital_out_32.go_low(t)
        digital_out_33.go_low(t)
        analog_out_0.constant(t, -1)
        analog_out_7.constant(t, -2)
        # board_2
        digital_out_34.go_low(t)
        digital_out_35.go_low(t)
        analog_out_8.constant(t, -3)
        analog_out_12.constant(t, -4)
        t += dt

        if True:
            # set some static channels
            static_digital_out_0.go_low()
            static_digital_out_5.go_low()
            static_digital_out_6.go_low()
            static_digital_out_21.go_low()

            static_analog_out_0.constant(-1.0)
            static_analog_out_1.constant(-2.0)
            static_analog_out_2.constant(-3.0)

    #t += 1.0

    print(f"experiment time: {t}")
    # stop sequence
    stop(t)


