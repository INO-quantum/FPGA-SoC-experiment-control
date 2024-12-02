#!/usr/bin/python

# connection table to test NI_DAQmx devices with labscript
# using internal clock of devices / chassis
# use NI_DAQmx_internal_clock which simulates pseudoclock device
# needs update of <python-path>/labscript-devices/NI_DAQmx/blacs_workers.py
# in order to send a contiguous stream of data to the device

# TODO: import connection_table.py into your experiment script using:
#       from labscript_utils import import_or_reload
#       import_or_reload('labscriptlib.<experiment name>.connection_table')

########################################################################################################################
# general imports

import numpy as np
from labscript import start, stop, add_time_marker, AnalogOut, DigitalOut, StaticDigitalOut, DDS, Trigger

########################################################################################################################
# NI DAQmx devices
# use NI_DAQmx_internal_clock to simulate a pseudoclock device
# for each NI_DAQms device give the return value of get_clockline() as parent device.
# for each device give name as displayed by NI MAX.
# I can test only simulated devices. clock_terminal and other settings might need to be adjusted.

from labscript_devices.NI_DAQmx.labscript_devices import NI_PXIe_6535, NI_PXIe_6738
from user_devices.NI_DAQmx_internal_clock import NI_DAQmx_internal_clock

NI_DAQmx_internal_clock('NI_internal_clock')
NI_PXIe_6535('NI_board0', NI_internal_clock.get_clockline(), clock_terminal='PFI4', MAX_name='PXI1Slot2')
NI_PXIe_6738('NI_board1', NI_internal_clock.get_clockline(), clock_terminal='PFI0', MAX_name='PXI1Slot3', max_AO_sample_rate=400e3)
#NI_PXIe_6738('NI_board2', NI_internal_clock.get_clockline(), clock_terminal='PFI0', MAX_name='PXI1Slot4', max_AO_sample_rate=400e3)

########################################################################################################################
# NI DAQmx channels
# we name here the channels as 'ao#' and 'do#' with # an integer.
# in a real experiment you can give each channel a meaningful name
# such that in the experiment script it is easy to understand what actions are done.
# the name must be valid to represent python variable (no spaces, no mathematical symbols)

do_count = 0
ao_count = 0
#for board in [NI_board0, NI_board1, NI_board2]:
for board in [NI_board0, NI_board1]:
    #print(board.name)
    # digital outputs. we take only buffered ones.
    for port,value in board.ports.items():
        for channel in range(value['num_lines']):
            if value['supports_buffered']:
                name = 'do%i'%do_count
                #print(name, '%s/line%i'%(port,channel))
                DigitalOut(name, board, '%s/line%i'%(port,channel))
                do_count += 1
            else: # labscript does not allow dynamic and static I/Os at the same time. we skip this.
                name = 'do%i'%do_count
                #print(name, '%s/line%i (static skipped)'%(port,channel))
                #StaticDigitalOut(name, board, '%s/line%i'%(port,channel))
                #do_count += 1
    # analog outputs
    for channel in range(board.num_AO):
        #print('ao%i'%(ao_count), 'ao%i'%(channel))
        AnalogOut(name='ao%i'%(ao_count), parent_device=board, connection='ao%i'%(channel))
        ao_count += 1

########################################################################################################################
# connection table must contain an empty experimental sequence
# do not modify this.

if __name__ == '__main__':

    # start sequence
    start()

    # stop sequence
    stop(1.0)


