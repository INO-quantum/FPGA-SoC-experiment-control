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


#                                       holdtime
# stopvalue                         ---------------                       
#                                  /               \
#                        ramptime /                 \ ramptime
#                                /                   \
#                 holdtime      /                     \       
# startvalue  -----------------/                       \

#creates a sequence of N trapezoid pulse like that described above with the parameters
def AC_MOD_E11_E12_triangle(channelE12, channelE11, durat):
    
    global t
    global ramp_samplerate
    i = 0

    #t+=0.01
    #DOBoard0CH["DO1"].go_high(t) #Dig 02: the second digital start at t=1.26s (duration 3.74)

    phaseE12 = 0.83
    amptargetE12=1.20
    phaseE11 = 0.74
    amptargetE11=1.34
    max_AO_rate = 1e6

    factor = 4 #ext1
    factor2 = 3 #ext2
    factor3 = 0.3 #ext3
    
    rampspeed = factor3*ramp_samplerate
    ramptime =  100*ms#np.abs(factor2-factor)/rampspeed
    holdtime = 100*ms

    startvalueE12 = 1#amptargetE12*np.sin(phaseE12)*factor
    stopvalueE12 = 2#amptargetE12*np.sin(phaseE12)*factor2
    startvalueE11 = 1#amptargetE11*np.sin(phaseE11)*factor
    stopvalueE11 = 2#amptargetE11*np.sin(phaseE11)*factor2
    
    N = durat/(2*holdtime + 2*ramptime)#number of triangles given the duration
    #relativetime = t%(2*ramptime + 2*holdtime)     if the method with the while lopp that ends until we reach the N sequences doesn't work we can try with this 


    while i < N:
        channelE12.constant(t, startvalueE12)
        channelE11.constant(t, startvalueE11)
        t+=holdtime
        t+=channelE12.ramp(t, ramptime, startvalueE12, stopvalueE12, samplerate=ramp_samplerate)
        channelE12.constant(t, stopvalueE12)
        t+=channelE11.ramp(t, ramptime, startvalueE11, stopvalueE11, samplerate=ramp_samplerate)
        channelE11.constant(t, stopvalueE11)
        t+=holdtime
        t+=channelE12.ramp(t, ramptime, stopvalueE12, startvalueE12, samplerate=ramp_samplerate)
        t+=channelE11.ramp(t, ramptime, stopvalueE11, startvalueE11, samplerate=ramp_samplerate)
        
        i+=1
    

    


# The following script program the old sequence used for the experiments refering to the old control software.

if __name__ == '__main__':

    t = 0.0
    dt = 10e-6
    us = 1e-6
    ns = 1e-9
    ms = 1e-3
    max_AO_rate = 1e6
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
        ao = [g['ao%i'%i] for i in range(16)] # board1,2 = slow

        
        #Voltages and time durations
        DC_E11_1D = -(7.0)/2
        DC_E12_1D = -(7.03)/2
        DC_E11_2D = -(13.9)/2
        DC_E12_2D = -(13.72)/2
        AC_MOD_E12 = 2
        AC_MOD_E11 = 2
       
        ramp_up_time = 0.25
        ramp_down_time = 0.25
        ramp_samplerate = 10e3

        #start of the sequence!         
        DOBoard1CH["P0.0"].go_high(t) #Dig 01: do0 is the channel reserved to the photon counter 
        t+=10*us
        DOBoard1CH["P0.0"].go_low(t)

        #DOBoard0CH["DO8"].go_high(t) #Dig 10_1: high (duration = 5s)
        if False:
            DOBoard0CH["DO5"].go_high(t) #Dig 5: high (duration = 5s)
            DOBoard0CH["DO4"].go_high(t) #Dig 4: high (duration = 5s)
            DOBoard0CH["DO6"].go_high(t) #Dig 6: high (duration = 5s)
        AOBoard1CH["AO2"].constant(t, AC_MOD_E12) #AC_MOD_E12 start (duration = 1.25s)
        AOBoard1CH["AO3"].constant(t, AC_MOD_E11) #AC_MOD_E12 start (duration = 1.25s)
        t+=10*us       

        if False:
            AOBoard1CH["AO1"].constant(t, DC_E12_1D)
            AOBoard1CH["AO2"].constant(t, DC_E12_1D)
            t+=1
            
            t+=AOBoard1CH["AO1"].ramp(t, ramp_up_time, DC_E12_1D, DC_E12_2D, samplerate=ramp_samplerate) #250ms of ramp up to DC_E12_ramp_up 
            t+=AOBoard1CH["AO2"].ramp(t, ramp_up_time, DC_E11_1D, DC_E11_2D, samplerate=ramp_samplerate) #250ms of ramp up to DC_E11_ramp_up 

            AOBoard1CH["AO1"].constant(t, DC_E12_2D)
            AOBoard1CH["AO2"].constant(t, DC_E12_2D)
            t+=3

        AC_MOD_E11_E12_triangle(AOBoard1CH["AO5"], AOBoard1CH["AO6"], 3) #duration 3s, in this function are created the triangle with the parameters initialized within

        AOBoard1CH["AO5"].constant(t, AC_MOD_E12) #AC_MOD_E12 start (duration = 750ms)  
        AOBoard1CH["AO6"].constant(t, AC_MOD_E11) #AC_MOD_E12 start (duration = 750ms)  

        if False:
            t+=AOBoard1CH["AO1"].ramp(t, ramp_down_time, DC_E12_2D, DC_E12_1D, samplerate=ramp_samplerate) #250ms of ramp down to DC_E12_1D         
            t+=AOBoard1CH["AO2"].ramp(t, ramp_down_time, DC_E11_2D, DC_E11_1D, samplerate=ramp_samplerate) #250ms of ramp down to DC_E11_1D 

            AOBoard1CH["AO1"].constant(t, DC_E12_1D)
            AOBoard1CH["AO2"].constant(t, DC_E11_1D)
            t+=500*ms

            AOBoard1CH["AO1"].constant(t, 0)
            AOBoard1CH["AO2"].constant(t, 0)
            t+=250*ms
        t+=500*ms
        AOBoard1CH["AO5"].constant(t, 0)
        AOBoard1CH["AO6"].constant(t, 0)


        
        
        #stop of the sequence
        if False:
            DOBoard1CH["P0.0"].go_high(t)
            t+=10*us
            DOBoard1CH["P0.0"].go_low(t)
            t+=10*us
            DOBoard1CH["P0.0"].go_high(t)
            t+=10*us
            DOBoard1CH["P0.0"].go_low(t)
        
            
    else:
        t+=1
                
   
    
    print(f"Total time: {t}")
    # stop sequence
    stop(t + dt)


