#!/usr/bin/python
# experiment script to test iPCdev devices with labscript

########################################################################################################################
# general imports

import numpy as np
from labscript import start, stop, add_time_marker, LabscriptError, AnalogOut, DigitalOut

########################################################################################################################
# import connection table.
# TODO: update the experiment name <iPCdev_text> with your actual name

from labscript_utils import import_or_reload
import_or_reload('labscriptlib.iPCdev_test.connection_table')

########################################################################################################################

# experimental sequence

if __name__ == '__main__':

    t = 0.0
    dt = 1e-6

    # start sequence
    start()

    if True:
        dt_slow = 2.0/device_0.clock_limit # slow

        # define some times in seconds
        wait_between_digital = True
        experiment_time = 5   # for >30s we run out of memory!

        offset_voltage = 2.0

        # switch all digital outputs on
        # this can be done all together or one by one

        t += 2*dt
        digital_out_0.go_high(t)
        for i in range(3):        
            digital_out_16.go_high(t)
            t += dt
            digital_out_16.go_low(t)
            t += dt
        t -= dt
        digital_out_0.go_low(t)
        t += dt

        for i in range(3):
            analog_out_8.constant(t, offset_voltage + i*1.0)
            t += dt_slow    

        if True:
            #do a ramps
            #t += analog_out_3.ramp(t, 5.0, 0, 5, samplerate=1000) 
            t+= analog_out_0.ramp(t, 0.5, offset_voltage, offset_voltage+5, samplerate=1000)
            t += 0.5
            t+= analog_out_1.ramp(t, 0.5, 0, 5, samplerate=1000)

        if True:
            t += 0.1
            a=0
            azioni=[]
            for tt in range(0,10):
                a+=1
                azioni.append((tt, a%2))

            t+=digital_out_2.repeat_pulse_sequence(t, 1, azioni, period=float(6.5), samplerate=100)
        #t += dt_slo

    if False:
        # test DDS. TODO: fix problem with unit conversion
        for dds in [dds_0,dds_3]:
            for i in range(11):
                dds.setfreq(t, 100.0+i*10, 'MHz')
                dds.setamp(t, -30+i*2)
                dds.setphase(t, i*10)
                t += 0.1

    if False: #True/False to test final values
        digital_out_0.go_high(t)
        digital_out_63.go_high(t)
        static_digital_out_0.go_high()
        static_digital_out_4.go_high()
        t += dt
        analog_out_0.constant(t, 1.0)
        analog_out_4.constant(t, 2.0)
        static_analog_out_0.constant(3.0)
        static_analog_out_3.constant(2.0)
        t += dt
        dds_0.setfreq(t, 101e6)
        dds_0.setamp(t, 11)
        dds_0.setphase(t, 21)
        dds_4.setfreq(t, 102e6)
        dds_4.setamp(t, 12)
        dds_4.setphase(t, 22)
        t += dt
        dds_0.setfreq(t, 101e6)
        dds_0.setamp(t, 11)
        dds_0.setphase(t, 25)
        dds_4.setfreq(t, 101e6)
        dds_4.setamp(t, 11)
        dds_4.setphase(t, 25)
        t += dt

    print(f"experiment time: {t} s")
    # stop sequence
    stop(t)

