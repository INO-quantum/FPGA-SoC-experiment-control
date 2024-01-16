#!/usr/bin/python

########################################################################################################################
# imports

import numpy as np
from labscript import start, stop, add_time_marker, AnalogOut, DigitalOut, DDS, Trigger
from user_devices.FPGA_device import FPGA_board, DigitalChannels, AnalogChannels, PRIMARY_IP, SECONDARY_IP, DEFAULT_PORT
from user_devices.generic_conversion import generic_conversion

########################################################################################################################
# FPGA boards

# primary board:
# note: importing 'primary' from connection_table does not work with 'FPGA_device(name='primary',...)' but requres to assign primary!
primary = FPGA_board(name='primary', ip_address="192.168.1.120", ip_port=DEFAULT_PORT, bus_rate=1e6, num_racks=1,trigger_device=pb0_trg,
    worker_args={ # optional arguments. can be changed in GUI. if defined here used at startup, otherwise last settings in GUI are used.
        #'inputs':{'start trigger': ('input 1', 'rising edge')},
        #'outputs': {'output 0': ('sync out', 'low level')}, # required: start trigger for sec. board (default, keep here). other outputs can be added.
        #'ext_clock':True,  # True = use external clock
        #'ignore_clock_loss':True # True = ignore when external clock is lost. Message Box is displayed but board keeps running.
        #'trigger':{}, # no trigger (default)
        #'trigger':{'start trigger':('input 0', 'rising edge')}, # start trigger
        #'trigger':{'start trigger':('input 0', 'rising edge'),'stop trigger':('input 1', 'falling edge'),'restart trigger':('input 0', 'rising edge')}, # start+stop+restart trigger
    }
    )

# secondary board: (enable with True)
if False:
    secondary = FPGA_board(name='secondary', ip_address="192.168.1.131", ip_port=DEFAULT_PORT, bus_rate=1e6, num_racks=1, trigger_device=primary,
        worker_args={ # optional arguments. can be changed in GUI. if defined here used at startup, otherwise last settings in GUI are used.
            #'inputs':{'start trigger':('input 0', 'falling edge')},
                      #'NOP bit':('data bits 20-23','offset bit 0'),
                      #'STRB bit' : ('data bits 20-23','offset bit 3')}, # required: start trigger from primary board (default, keep here)
            #'ext_clock': True,  # True = required: use external clock from primary board (default, keep here)
            #'ignore_clock_loss': True # True = ignore when external clock is lost. Message Box is displayed but board keeps running.
            # 'trigger':{'start trigger':('input 0', 'falling edge'),'stop trigger':('input 1', 'falling edge'),'restart trigger':('input 1', 'rising edge')}, # start+stop+restart trigger. must be input 1 or 2
            #'outputs':{'output 0': ('sync out', 'low level'),'output 0': ('lock lost', 'high level')}, example outputs can be added when needed.
        })

########################################################################################################################
# analog outputs

AnalogChannels(name='AO0', parent_device=primary, rack=0, max_channels=2)
AnalogOut     (name='ao0', parent_device=AO0, connection='0x00')
AnalogOut     (name='ao1', parent_device=AO0, connection='0x01')

AnalogChannels(name='AO1', parent_device=primary, rack=0, max_channels=2)
AnalogOut     (name='ao2', parent_device=AO1, connection='0x02', unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit':'A', 'equation':'x', 'min':-10.0, 'max':10.0})
AnalogOut     (name='ao3', parent_device=AO1, connection='0x03', unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit':'MHz', 'equation':'(x-142.31036)/31.31786', 'min':0.0, 'max':455.48896})

if secondary is not None:
    AnalogChannels(name='AO2', parent_device=primary, rack=0, max_channels=4)
    AnalogOut     (name='ao4', parent_device=AO0, connection='0x04')
    AnalogOut     (name='ao5', parent_device=AO0, connection='0x05')
    AnalogOut     (name='ao6', parent_device=AO0, connection='0x06')
    AnalogOut     (name='ao7', parent_device=AO0, connection='0x07')

########################################################################################################################
# digital outputs

DigitalChannels(name='DO0', parent_device=primary, connection='0x0', rack=0, max_channels=16)
for i in range(16):
    DigitalOut(name='do%i'%i, parent_device=DO0, connection=0)

if secondary is not None:
    for i in range(16):
        DigitalOut(name='do%i'%i+16, parent_device=DO0, connection='0x%02x'%i)

########################################################################################################################
# experimental sequence

if __name__ == '__main__':

    #t = primary.start_time #note: t is not used here
    #dt = primary.time_step

    # start sequence
    start()

    # stop sequence
    stop(1.0)


