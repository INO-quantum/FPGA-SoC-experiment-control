#!/usr/bin/python

########################################################################################################################
# imports

import numpy as np
from labscript import start, stop, add_time_marker, Trigger
from user_devices.FPGA_device.labscript_device import (
    FPGA_board, DigitalChannels, AnalogChannels, DDSChannels,
    DigitalOutput, DDS_generic,
    PRIMARY_IP, SECONDARY_IP, DEFAULT_PORT
)
from user_devices.FPGA_device.shared import use_prelim_version
if use_prelim_version:
    from user_devices.FPGA_device.DAC import DAC712, DAC715, DAC7744
    from user_devices.FPGA_device.generic_conversion import generic_conversion

########################################################################################################################
# FPGA boards

# examples for worker_args:
# these can can be overwritten in experiment script and in GUI.
# 'inputs' : {'start trigger': ('input 1', 'rising edge')} # needed for secondary board
# 'outputs': {'output 0': ('sync out', 'low level')}, # needed for primary board
# 'ext_clock' : True,  # True = use external clock
# 'ignore_clock_loss' : True # True = ignore when external clock is lost. Message Box is displayed but board keeps running.

if False:
    # DummyPseudoClock test
    from labscript_devices.DummyPseudoclock.labscript_devices import DummyPseudoclock
    from labscript_devices.DummyIntermediateDevice import DummyIntermediateDevice
    dummy = DummyPseudoclock()
    DummyIntermediateDevice('AO0', dummy.clockline)
    DummyIntermediateDevice('AO1', dummy.clockline)
    DummyIntermediateDevice('DO0', dummy.clockline)
    DummyIntermediateDevice('DO1', dummy.clockline)

if False:
    # test with/without PulseBlaster from Andrea
    from labscript_devices.PulseBlaster import PulseBlaster
    p = False
    if p:
        # dont do this!
        #from user_devices.FPGA_device_Andrea import FPGA_board, DigitalChannels, AnalogChannels, DEFAULT_PORT

        pb0 = PulseBlaster(name='PulseBlaster_0', board_number=-1)
        pb0_trg = Trigger(name='pb0_trg', parent_device=pb0.direct_outputs, connection='flag 0',
                          trigger_edge_type='rising')
        pb0_ch1 = DigitalOutput(name='pb0_ch1', parent_device=pb0.direct_outputs, connection='flag 1')
        parent = pb0_trg
    else:
        # dont do this!
        #from user_devices.FPGA_device_Alone import FPGA_board, DigitalChannels, AnalogChannels, DEFAULT_PORT
        parent = None

    primary = FPGA_board(name='main_board', ip_address='192.168.1.10', ip_port=DEFAULT_PORT, bus_rate=1.0,
                         num_racks=1,
                         trigger_device=parent,
                         worker_args={#'inputs': {'start trigger': ('input 0', 'low level')},
                                      'outputs': {'output 0': ('sync out', 'low level')},
                                      'simulate': True # simulate device
                                      },
                        )

    if False:  # use secondary board
        if p:
            parent = pb0_trg
        else:
            parent = primary
        secondary = FPGA_board(name='test_board', ip_address='192.168.1.11', ip_port=DEFAULT_PORT, bus_rate=1.0,
                               num_racks=1,
                               trigger_device=parent,
                               worker_args={'inputs': {'start trigger': ('input 0', 'low level')}})
    else:
        secondary = None

if True:
    # primary board:
    # note: importing 'primary' from connection_table does not work with 'FPGA_device(name='primary',...)' but requires to assign primary!

    if use_prelim_version:
        primary = FPGA_board(
            name           = 'primary',         # give board name displayed in GUI. must be valid Python variable name.
            ip_address     = "192.168.1.130",   # IP address of board
            ip_port        = DEFAULT_PORT,      # port of the board. can be skipped, None, DEFAULT_PORT
            bus_rate       = 1e6,               # bus output rate in Hz. typically 1MHz, max. FPGA_device.shared.MAX_FPGA_RATE.
            num_racks      = 1,                 # number of sub-racks the board is connected to. 1 or 2.
            trigger_device = None,              # None for the primary board, primary board for secondary board.
            worker_args    = {                  # optional settings
                # optional inputs configuration with external start/stop/restart trigger.
                # note: boards v1.3 and v1.4 have input buffer inverted and on board v1.3 labels of input 1 and 2 are inverted.
                'inputs' : {
                    # 'trigger start'   : 'input 0 falling', # start trigger.
                    # 'trigger stop'    : 'data bit 28', # stops when stop bit 28 in data is set
                    # 'trigger restart' : 'input 0 rising', # restart board (can be the same or different to start trigger)
                    'bit NOP': 'data bit 31',  # note: labscript might insert data with this bit set. should be fixed in next version.
                },
                'outputs': {'output 0' : 'sync out', # trigger secondary board on experiment start.
                            'output 1' : 'run',
                            'output 2' : 'strobe 1 contiguous',
                            'LED red'  : 'error',
                            'LED green': 'run',
                            'LED blue' : 'ext clock locked'},
                'strb_delay': 0x001e461e,       # optional strobe 0 and strobe 1 timings
                                                # bits  0-3  = strobe 0 start time when strobe goes high in units of 10ns
                                                # bits  4-7  = strobe 0 end time when strobe goes low in units of 10ns. when 0 toggles.
                                                # bits  8-11 = strobe 1 start time when strobe goes high in units of 10ns
                                                # bits 12-15 = strobe 1 end time when strobe goes low in units of 10ns. when 0 toggles.
                'ext_clock': False,             # optional: if True use external clock reference
                'simulate' : False              # if True simulate hardware
            },
            )
    else:
        primary = FPGA_board(name='primary', ip_address="192.168.1.130", ip_port=DEFAULT_PORT, bus_rate=1e6,
                             num_racks=1, trigger_device=None,
                             worker_args={
                                 # optional arguments. can be changed in GUI. if defined here used at startup, otherwise last settings in GUI are used.
                                 # 'inputs':{'start trigger': ('input 1', 'rising edge')},
                                 # 'outputs': {'output 0': ('sync out', 'low level')}, # required: start trigger for sec. board (default, keep here). other outputs can be added.
                                 # 'ext_clock':True,  # True = use external clock
                                 # 'ignore_clock_loss':True # True = ignore when external clock is lost. Message Box is displayed but board keeps running.
                                 # 'trigger':{}, # no trigger (default)
                                 # 'trigger':{'start trigger':('input 0', 'rising edge')}, # start trigger
                                 # 'trigger':{'start trigger':('input 0', 'rising edge'),'stop trigger':('input 1', 'falling edge'),'restart trigger':('input 0', 'rising edge')}, # start+stop+restart trigger
                             }
                             )

# secondary board: (enable with True)
if True:
    if use_prelim_version:
        secondary = FPGA_board(
            name            = 'secondary',      # give board name displayed in GUI. must be valid Python variable name.
            ip_address      = "192.168.1.131",  # IP address of board
            ip_port         = DEFAULT_PORT,     # port of the board. can be skipped, None, DEFAULT_PORT
            bus_rate        = 1e6,              # bus output rate in Hz. typically 1MHz. max. FPGA_device.shared.MAX_FPGA_RATE
            num_racks       = 1,                # number of sub-racks the board is connected to. 1 or 2.
            trigger_device  = primary,          # must be primary board name
            worker_args     = {                 # optional settings
                # required input configuration: use start trigger from primary board on input 0
                # note: boards v1.3 and v1.4 have input buffer inverted and on board v1.3 labels of input 1 and 2 are inverted.
                'inputs'  : {'trigger start' : 'input 0 falling',
                             'bit NOP'       : 'data bit 31',   # note: labscript might insert data with this bit set. should be fixed in next version.
                            },
                # optional outputs configuration for debugging/monitoring.
                'outputs' : {'output 0': 'sync out', # pulses when board starts
                             'output 1': 'run inverted',  # high while running
                             'output 2': 'wait inverted'}, # high while waiting (I think only in 'pause' mode with run bit reset)
                'strb_delay': 0x001e461e,       # optional strobe 0 and strobe 1 timings
                                                # bits  0-3  = strobe 0 start time when strobe goes high in units of 10ns
                                                # bits  4-7  = strobe 0 end time when strobe goes low in units of 10ns. when 0 toggles.
                                                # bits  8-11 = strobe 1 start time when strobe goes high in units of 10ns
                                                # bits 12-15 = strobe 1 end time when strobe goes low in units of 10ns. when 0 toggles.
                'ext_clock': True,              # required: use external clock from primary board (LVPECL signal).
                'simulate' : False              # if True simulate hardware
            })
    else:
        secondary = FPGA_board(name='secondary', ip_address="192.168.1.131", ip_port=DEFAULT_PORT, bus_rate=1e6,
                               num_racks=1, trigger_device=primary,
                               worker_args={
                                   # optional arguments. can be changed in GUI. if defined here used at startup, otherwise last settings in GUI are used.
                                   # 'inputs':{'start trigger':('input 0', 'falling edge')},
                                   # 'NOP bit':('data bits 20-23','offset bit 0'),
                                   # 'STRB bit' : ('data bits 20-23','offset bit 3')}, # required: start trigger from primary board (default, keep here)
                                   # 'ext_clock': True,  # True = required: use external clock from primary board (default, keep here)
                                   # 'ignore_clock_loss': True # True = ignore when external clock is lost. Message Box is displayed but board keeps running.
                                   # 'trigger':{'start trigger':('input 0', 'falling edge'),'stop trigger':('input 1', 'falling edge'),'restart trigger':('input 1', 'rising edge')}, # start+stop+restart trigger. must be input 1 or 2
                                   # 'outputs':{'output 0': ('sync out', 'low level'),'output 0': ('lock lost', 'high level')}, example outputs can be added when needed.
                               })

else: secondary = None

########################################################################################################################
# digital outputs
# in a real experiment you would give a name like 'MOT_IGBT' to each channel.
# connection on DigitalChannels = address set on the sub-rack. can be decimal or hex - as you prefer.
# connection on DigitalOutput   = channel number 0..max_channels-1

DigitalChannels(name='DO0', parent_device=primary, connection='0x0', rack=0, max_channels=16, bus_rate=20e6)
for i in range(16):
    DigitalOutput(name='do%i'%i, parent_device=DO0, connection=i)

if secondary is not None:
    DigitalChannels(name='DO1', parent_device=secondary, connection='0x01', rack=0, max_channels=16)
    for i in range(16):
        DigitalOutput(name='do%i'%(i+16), parent_device=DO1, connection=i)

########################################################################################################################
# analog outputs
# in a real experiment you would give a name like 'MOT_current' to each channel.
# connection = address set on sub-rack. can be decimal or hex - as you prefer.

if use_prelim_version:
    AnalogChannels(name='AO0', parent_device=primary, rack=0, max_channels=4)
    DAC712 (name='ao0', parent_device=AO0, connection='0x02')
    DAC715 (name='ao1', parent_device=AO0, connection='0x03')
    DAC7744(name='ao2', parent_device=AO0, connection='0x04')
    # example with generic_conversion class.
    # use variable 'x' to convert from 'unit' to volts in 'equation'.
    # 'min' and 'max' give the limits in the chosen 'unit'.
    AnalogChannels(name='AO1', parent_device=primary, rack=0, max_channels=4)
    DAC712 (name='ao3', parent_device=AO1, connection='0x05', unit_conversion_class=generic_conversion,
                   unit_conversion_parameters={'unit':'A', 'equation':'x/10.0', 'min':-0.01, 'max':100.0})
    DAC715 (name='ao4', parent_device=AO1, connection='0x06', unit_conversion_class=generic_conversion,
                   unit_conversion_parameters={'unit':'MHz', 'equation':'(x-142.31036)/31.31786', 'min':0.0, 'max':455.48896})
    DAC7744(name='ao5', parent_device=AO1, connection='0x07', unit_conversion_class=generic_conversion,
                   unit_conversion_parameters={'unit':'MHz', 'equation':'(x-142.31036)/31.31786', 'min':0.0, 'max':455.48896})

    if secondary is not None:
        AnalogChannels(name='AO2', parent_device=secondary, rack=0, max_channels=4)
        DAC712 (name='ao6', parent_device=AO2, connection='0x08')
        DAC715 (name='ao7', parent_device=AO2, connection='0x09')
        DAC7744(name='ao8', parent_device=AO2, connection='0x0a')
else:
    from labscript import AnalogOut
    AnalogChannels(name='AO0', parent_device=primary, rack=0, max_channels=6)
    for i in range(6):
        AnalogOut (name='ao%i'%i, parent_device=AO0, connection='0x%i'%(2+i))
    if secondary is not None:
        AnalogChannels(name='AO2', parent_device=primary, rack=0, max_channels=4)
        for i in range(6,9):
            AnalogOut(name='ao%i' % i, parent_device=AO2, connection='0x%i' % (2 + i))

########################################################################################################################
# DDS
if False:
    # import custom DDS implementations
    from user_devices.FPGA_device.AnalogDevices_DDS import AD9854, AD9858, AD9915

    # we need to define at least one intermediate device for DDSChannels.
    # here we define FPGA board and rack (= strobe line)
    # and one can limit bus output rate of DDS in case needed.
    DDSChannels(name='DDS0', parent_device=primary, rack=0, max_channels=None, bus_rate=1e6)

    # create DDS. address must be multiple of 4 and no in-between address must be used elsewhere.
    AD9854(name='dds_0', parent_device=DDS0, connection='0x10') #, freq_limits=(70e6,80e6))
    AD9858(name='dds_1', parent_device=DDS0, connection='0x14', amp_limits=(-30,0))
    AD9915(name='dds_2', parent_device=DDS0, connection='0x18', phase_limits=(0,90))

    if secondary is not None:
        DDSChannels(name='DDS1', parent_device=secondary, rack=0, max_channels=None)
        DDS_generic(name='dds_3', parent_device=DDS1, connection='0x20', freq_limits=(100e6,120e6))
        DDS_generic(name='dds_4', parent_device=DDS1, connection='0x24')
        DDS_generic(name='dds_5', parent_device=DDS1, connection='0x28')

########################################################################################################################
if False:
    # test triggerable device:
    # connect one intermediate device as parent_device
    # and give connection = channel number of the digital channel to be used to trigger the device
    # in runviewer the channel will be visible as triggerable device name + '_trigger'
    from labscript_devices.IMAQdxCamera.labscript_devices import IMAQdxCamera

    DigitalChannels(name='DO_cam', parent_device=primary, connection='0x27', rack=0, max_channels=16)

    IMAQdxCamera('test_camera', parent_device=DO_cam, connection=0, mock=True, serial_number=10)

########################################################################################################################
# experimental sequence

if __name__ == '__main__':

    #t = primary.start_time #note: t is not used here
    #dt = primary.time_step

    # start sequence
    start()

    # stop sequence
    stop(1.0)

