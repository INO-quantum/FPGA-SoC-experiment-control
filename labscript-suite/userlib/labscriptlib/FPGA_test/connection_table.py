#!/usr/bin/python

########################################################################################################################
# imports

import numpy as np
from labscript import start, stop, add_time_marker, AnalogOut, DigitalOut, DDS, Trigger
from user_devices.FPGA_device import FPGA_board, DigitalChannels, AnalogChannels, PRIMARY_IP, SECONDARY_IP, DEFAULT_PORT
from user_devices.generic_conversion import generic_conversion

########################################################################################################################
# FPGA boards

# examples for worker_args:
# these can can be overwritten in experiment script and in GUI.
# 'inputs' : {'start trigger': ('input 1', 'rising edge')} # needed for secondary board
# 'outputs': {'output 0': ('sync out', 'low level')}, # needed for primary board
# 'ext_clock' : True,  # True = use external clock
# 'ignore_clock_loss' : True # True = ignore when external clock is lost. Message Box is displayed but board keeps running.

# primary board:
# note: importing 'primary' from connection_table does not work with 'FPGA_device(name='primary',...)' but requres to assign primary!
primary = FPGA_board(
    name           = 'primary',         # give board name displayed in GUI. must be valid Python variable name.
    ip_address     = "192.168.1.140",   # IP address of board
    ip_port        =   DEFAULT_PORT,    # port of the board. can be skipped, None, DEFAULT_PORT
    bus_rate       = 1e6,               # bus output rate in Hz. typically 1MHz
    num_racks      = 1,                 # number of sub-racks the board is connected to. 1 or 2.
    trigger_device = None,              # None for the primary board, primary board for secondary board.
    worker_args    = {                  # optional settings
        'outputs': {'output 0': ('sync out', 'low level')}, # trigger secondary board on experiment start.
        'ext_clock': False,             # if True use external clock reference
        }
    )

# secondary board: (enable with True)
if False:
    secondary = FPGA_board(
        name            = 'secondary',      # give board name displayed in GUI. must be valid Python variable name.
        ip_address      = "192.168.1.141",  # IP address of board
        ip_port         = DEFAULT_PORT,     # port of the board. can be skipped, None, DEFAULT_PORT
        bus_rate        = 1e6,              # bus output rate in Hz. typically 1MHz
        num_racks       = 1,                # number of sub-racks the board is connected to. 1 or 2.
        trigger_device  = primary,          # must be primary board name
        worker_args     = {                 # optional settings
            'inputs' : {'start trigger' : ('input 0', 'falling edge')}, # use start trigger from primary board on input 0
            'ext_clock': True,              # use external clock from primary board.
        })
else: secondary = None

########################################################################################################################
# analog outputs
# in a real experiment you would give a name like 'MOT_current' to each channel.
# connection = address set on sub-rack. can be decimal or hex - as you prefer.

AnalogChannels(name='AO0', parent_device=primary, rack=0, max_channels=2)
AnalogOut     (name='ao0', parent_device=AO0, connection='0x03')
AnalogOut     (name='ao1', parent_device=AO0, connection='0x04')

# example with generic_conversion class.
# use variable 'x' to convert from 'unit' to volts in 'equation'.
# 'min' and 'max' give the limits in the chosen 'unit'.
AnalogChannels(name='AO1', parent_device=primary, rack=0, max_channels=2)
AnalogOut     (name='ao2', parent_device=AO1, connection='0x05', unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit':'A', 'equation':'x/10.0', 'min':-0.01, 'max':100.0})
AnalogOut     (name='ao3', parent_device=AO1, connection='0x06', unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit':'MHz', 'equation':'(x-142.31036)/31.31786', 'min':0.0, 'max':455.48896})

if secondary is not None:
    AnalogChannels(name='AO2', parent_device=secondary, rack=0, max_channels=4)
    AnalogOut     (name='ao4', parent_device=AO0, connection='0x07')
    AnalogOut     (name='ao5', parent_device=AO0, connection='0x08')
    AnalogOut     (name='ao6', parent_device=AO0, connection='0x09')
    AnalogOut     (name='ao7', parent_device=AO0, connection='0x0a')

########################################################################################################################
# digital outputs
# in a real experiment you would give a name like 'MOT_IGBT' to each channel.
# connection on DigitalChannels = address set on the sub-rack. can be decimal or hex - as you prefer.
# connection on DigitalOut      = channel number 0..max_channels-1

DigitalChannels(name='DO0', parent_device=primary, connection='0x0', rack=0, max_channels=16)
for i in range(16):
    DigitalOut(name='do%i'%i, parent_device=DO0, connection=i)

if secondary is not None:
    DigitalChannels(name='DO1', parent_device=secondary, connection='0x01', rack=0, max_channels=16)
    for i in range(16):
        DigitalOut(name='do%i'%i+16, parent_device=DO1, connection=i)

########################################################################################################################
# experimental sequence

if __name__ == '__main__':

    #t = primary.start_time #note: t is not used here
    #dt = primary.time_step

    # start sequence
    start()

    # stop sequence
    stop(1.0)


