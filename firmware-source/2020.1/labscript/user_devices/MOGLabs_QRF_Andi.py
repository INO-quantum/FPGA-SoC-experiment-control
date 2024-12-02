#####################################################################
#                                                                   #
# /NovaTechDDS9M.py                                                 #
#                                                                   #
# Copyright 2013, Monash University                                 #
#                                                                   #
# This file is part of the module labscript_devices, in the         #
# labscript suite (see http://labscriptsuite.org), and is           #
# licensed under the Simplified BSD License. See the license.txt    #
# file in the root of the project for the full license.             #
#                                                                   #
#####################################################################

# MOGLabs QRF module for use with FPGA board by Andi
# depdnds on labscript-suite, PyQt5, numpy, scipy, FPGA_device and mogdevice
# modified from: https://github.com/specialforcea/labscript_suite/blob/a4ad5255207cced671990fff94647b1625aa0049/labscript_devices/MOGLabs_XRF021.py
# copy this file into user_devices and ensure register_classes.py contains the lines:
#register_classes(
#    'MOGLabs_QRF',
#    BLACS_tab='user_devices.MOGLabs_QRF.MOGLabs_QRF_Tab'
#)
# copy also mogdevice.py file downloadable from MOGlabs (link?) into user_devices folder.
# Authors:
# - original ?
# - Andi
# - Ale

import numpy as np
import time
import socket
import select
import struct
import collections
import logging
import time

from labscript_devices import runviewer_parser, labscript_device, BLACS_tab, BLACS_worker
from labscript_utils.qtwidgets.toolpalette import ToolPaletteGroup
from labscript import Device, PseudoclockDevice, Pseudoclock, ClockLine, IntermediateDevice, DDSQuantity, config, LabscriptError, set_passed_properties
import labscript_utils.h5_lock, h5py
import labscript_utils.properties
from blacs.tab_base_classes import Worker, define_state
from blacs.tab_base_classes import MODE_MANUAL, MODE_TRANSITION_TO_BUFFERED, MODE_TRANSITION_TO_MANUAL, MODE_BUFFERED
from blacs.device_base_class import DeviceTab

from PyQt5.QtWidgets import QWidget, QGridLayout, QCheckBox

from user_devices.mogdevice import MOGDevice

# note: if needed importing FPGA_board should work but in case of an error 'cannot load FPGA_board'
#       ensure that MOGLabs_QRF is not loaded in FPGA_device which causes this error!
#       it seems Python cannot handle circular references!
#       the error occurred during compilation of connection table with BLACS.
# from user_devices.FPGA_device import FPGA_board

# reduce number of log entries in logfile (labscript-suite/logs/BLACS.log)
log_level = [logging.CRITICAL, logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG, logging.NOTSET][2]

# set number of channels
MAX_NUM_CHANNELS = 4

# min/max RF frequency in MHz
MIN_RF_FREQ     = 20.0
MAX_RF_FREQ     = 200.0
DEFAULT_RF_FREQ = MIN_RF_FREQ

# min/max RF amplitudes in dBm
MIN_RF_AMP      = -50.0
MAX_RF_AMP      = 33.0

# min/max RF phase in degree
MIN_RF_PHASE    = 0
MAX_RF_PHASE    = 360

# measured trigger delay in table in seconds. there is a jitter of 5us.
TABLE_MIN_TRIGGER_DELAY = 3.5e-6
TABLE_MAX_TRIGGER_DELAY = 8.5e-6

# trigger delay for switching RF on/off when not in table mode.
# this maximum value given is the specified value. the minimum value was measured.
# no jitter seen but could be different from device to device.
NO_TABLE_MIN_TRIGGER_DELAY = 25e-9
NO_TABLE_MAX_TRIGGER_DELAY = 40e-9

# this applies only for Table mode
# clock resolution and limit calculated from MAX_BUS_RATE.
# MAX_BUS_RATE is the maximum data output rate in Hz on the bus. individual devices can give a lower rate but not higher.
# times are rounded to nearest integer multiple of clock_resolution in quantise_to_pseudoclock in labscript.py.
# time deltas dt are checked vs. dt < 1/clock_line.clock_limit in collect_change_times in labscript.py.
# we add epsilon(MAX_TIME) to clock_limit to avoid that small numberical errors cause problems.
def epsilon(number):
    """
    returns smallest epsilon for which number + epsilon != number.
    sys.float_info.epsilon = epsilon(1.0)
    """
    e = number
    while(number + e != number):
        e /= 2
    return 2*e
# limits in TABLE mode
TABLE_CLOCK_RESOLUTION = 5e-6
TABLE_MAX_BUS_RATE     = 1/TABLE_CLOCK_RESOLUTION
TABLE_MAX_TIME         = ((2**32)-1)*TABLE_CLOCK_RESOLUTION # TODO: not clear what is largest time? maybe only 16bits?
TABLE_CLOCK_LIMIT      = 1.0/(TABLE_CLOCK_RESOLUTION - 2*epsilon(TABLE_MAX_TIME))
# limits when not in TABLE mode depends on actual FPGA board clock resolution
NO_TABLE_CLOCK_RESOLUTION = NO_TABLE_MAX_TRIGGER_DELAY
NO_TABLE_MAX_BUS_RATE     = 1/NO_TABLE_CLOCK_RESOLUTION
def get_clock_limit(clock_resolution):
    return 1.0/(NO_TABLE_CLOCK_RESOLUTION - 2*epsilon(((2**32)-1)*clock_resolution))
#print('Moglabs QFR: maximum bus rate %.3f MHz gives resolution %.3f ns and max time %.3f s (clock limit = bus rate + %.3f Hz)' % (MAX_BUS_RATE/1e6, CLOCK_RESOLUTION*1e9, MAX_TIME, CLOCK_LIMIT - MAX_BUS_RATE))

# table options passed to worker
FLAG_TABLE_MODE         = 1
FLAG_TRIGGER_EACH_STEP  = 2

class QRF_DDS(IntermediateDevice):
    """
    wrapper class for DDS with table mode and trigger options.
    name = name of channel, must be a valid Python name
    parent_device = must be a MOGLabs_QRF device
    connection = must be 'channel %i' with %i = 0..3
    digital_gate = must contain 'device' = DigitalChannels intermediate device with free channel number given as 'connection'
    table_mode = if False: use enable/disable to switch RF on/off very fast.
                           channel frequency, amplitude, phase cannot change during the experiment.
                           set them once in experimental script, otherwise manual parameters are used.
                 if True: use table mode to program channel with every trigger (trigger_each_Step=True) or at the programmed time ((trigger_each_Step=False)
                          this mode has up to 5us delay with jitter but allows the frequency, amplitude and phase to be changed during the experiment.
    trigger_each_step = used only with table_mode=True. if True for each change of the state of the channel a TTL signal is generated.
                 if False, a single trigger for the first change of the state of the channel is generated and the QRF executes the table at the programmed time.
                 if True the QRF will stay in sync with the experiment, but many triggers might be generated.
                 if False the QRF might get out of sync when the reference clock is not used.
    """

    def __init__(self, name, parent_device, connection, digital_gate, table_mode=True, trigger_each_step=False, freq_limits=None, freq_conv_class=None, freq_conv_params={},
                 amp_limits=None, amp_conv_class=None, amp_conv_params={}, phase_limits=None, phase_conv_class=None, phase_conv_params = {},
                 call_parents_add_device = True, **kwargs):

        # parent device must be MOGLabs_QRF device
        if not isinstance(parent_device, MOGLabs_QRF):
            raise LabscriptError("Device '%s' parent class is '%s' but must be 'MOGLabs_QRF'!" % (name, type(parent_device).__name__))

        # find parent FPGA board and check that this is correct
        # note: importing FPGA_board makes troubles, so have to check type instead of isinstance!
        #parent_board = parent_device.parent_board
        #if type(parent_board).__name__ != 'FPGA_board':
        #    raise LabscriptError("Device '%s' parent device is '%s' but must be 'FPGA_board'!" % (name, type(parent_board).__name__))

        # trigger device must be DigitalChannels intermediate device
        # note: importing FPGA_board makes troubles, so have to check type instead of isinstance!
        if not 'device' in digital_gate or not 'connection' in digital_gate:
            raise LabscriptError("Device '%s' give digital_gate={'device':DigitalChannels, 'connection':free channel number}!" % (self.name))
        if type(digital_gate['device']).__name__ != 'DigitalChannels':
            raise LabscriptError("Device '%s' trigger device is '%s' but must be 'DigitalChannels'!" % (name, type(digital_gate['device']).__name__))

        self.table_mode = table_mode
        self.trigger_each_step = trigger_each_step

        # trigger delay and resolution depend if we are in table mode or not
        # in non-table mode we take limits of parent board
        if self.table_mode:
            self.trigger_delay = TABLE_MAX_TRIGGER_DELAY
            self.bus_rate      = TABLE_MAX_BUS_RATE
            self.clock_limit   = TABLE_CLOCK_LIMIT
            self.clock_resolution = TABLE_CLOCK_RESOLUTION
        else:
            self.trigger_delay = NO_TABLE_MAX_TRIGGER_DELAY
            self.bus_rate      = NO_TABLE_MAX_BUS_RATE
            #self.clock_limit   = get_clock_limit(parent_board.clock_resolution)
            #self.clock_resolution = parent_board.clock_resolution
            self.clock_limit   = get_clock_limit(1e-6)
            self.clock_resolution = 1e-6

        # create pseudoclock
        # Pseudoclock is initialized with the parent_device clock limit/resolution which is NOT what we want.
        # we want limit/resolution of this device. the paren_device will set its limit/resolution to the fastest clock.
        # we call add_device later when chain of devices is created othwise lists of child_devices are empty
        self.pseudoclock = Pseudoclock(name=name+'_ps', pseudoclock_device=parent_device, connection='ps%i'%digital_gate['connection'], call_parents_add_device=False)
        self.pseudoclock.clock_limit = self.clock_limit
        self.pseudoclock.clock_resolution = self.clock_resolution

        # create clockline
        self.clockline = ClockLine(name=name+'_cl', pseudoclock=self.pseudoclock, connection='cl%i'%digital_gate['connection'])

        # init class. this will call parent_device.add_device
        IntermediateDevice.__init__(self, 'QRF_%s'%name, parent_device=self.clockline)

        # create new DDS. self.DDS.gate contains new DigitalOutput used as trigger
        self.DDS = DDSQuantity(name, parent_device=self, connection=connection, digital_gate=digital_gate)

        # set default frequency in MHz
        self.DDS.frequency.default_value = DEFAULT_RF_FREQ

        # notify MOGLabs_QRF of new pseudoclock. this will adapt the clock_limt and clock_resolution to fastest clock
        parent_device.add_device(self.pseudoclock)

class MOGLabs_QRF(PseudoclockDevice):
    """
    MOGLabs QRF device.
    init with:
    name = allowed python name
    trigger_device = must be FPGA_board
    addr = address for MOGDevice.__init__
    port = prot for MOGDevice.__init__
    worker_args = arguments passed to MOGLabs_QRF_Worker
    """

    description = 'QRF'
    allowed_children = [Pseudoclock]

    # these values will be updated in add_device for fastest channels
    # TODO: inserted temporarily - should be updated later by fastest DDS channel.
    #       the problem here is that the channels can have different clock rates and limits which is not intended here.
    #       a solution would be to create one QRF device for each channel but only one worker can talk to the real device. possible but not practical.
    clock_limit = get_clock_limit(1e-6)
    clock_resolution = 1e-6
    trigger_delay = 1e-6
    trigger_minimum_duration = 5e-6

    @set_passed_properties(
        property_names={'connection_table_properties': ['addr', 'port', 'worker_args']}
    )
    def __init__(self, name, parent_device, addr=None, port=7802, worker_args=None):
        self.BLACS_connection = '%s,%s' % (addr, str(port))

        self.name = name
        self.parent_device = parent_device # will be replaced with digital channel of fastest QRF_DDS
        self.parent_board  = parent_device

        # parent device must be FPGA_board
        # note: importing FPGA_board makes troubles, so have to check type instead of isinstance!
        #if type(parent_device).__name__ != 'FPGA_board':
        #    raise LabscriptError("Device '%s' trigger class is '%s' but must be 'FPGA_board'!" % (self.name, type(parent_device).__name__))

        # init parent class. we must give a trigger_device and trigger_connection (name seems not to matter)
        # this will create a Trigger device which needs to have parent_device = DigitalOut
        # we will fill this in as soon as QRF_DDS channels are created and clockline is added in add_device
        PseudoclockDevice.__init__(self, name, trigger_device=parent_device, trigger_connection=15)

        # add QRF to list of secondary boards. this is needed, otherwise generate_code is not called.
        #self.parent_board.add_device(self)

    def add_device(self, device):
        # called with device = Pseudoclock from child channel QRF_DDS
        print('QRF add_device called for device',device.name)
        Device.add_device(self, device)

        if False:
            # we need to provide a valid DigitalChannel as trigger_device also for the MOGLabs_QRF, otherwise start() will give an error.
            # we choose the fastest channel for this.
            # TODO: I cannot say at the moment if this has negative side-effects.
            #       its also strange that for the Secondary boards this is NOT needed!?
            IM = device.child_devices[0].child_devices[0]
            clock_limit = IM.clock_limit
            if self.clock_limit is None or clock_limit > self.clock_limit:
                self.clock_limit = clock_limit
                self.clock_resolution = IM.clock_resolution
                self.trigger_device.parent_device = IM.DDS.gate

    def generate_code(self, hdf5_file):

        print(f"'{self.name}' generating code")

        # create list of times and raw_data for each device
        PseudoclockDevice.generate_code(self, hdf5_file)

        grp = self.init_device_group(hdf5_file)
        dtypes = [('time', np.uint32), ('freq', np.uint32), ('amp', np.uint16), ('phase', np.uint16)]

        # get values of all channels. channels might have different numbers of entries.
        for pseudoclock in self.child_devices:
            #print(pseudoclock)
            for clockline in pseudoclock.child_devices:
                #print(clockline)
                for IM in clockline.child_devices:
                    print(IM)
                    for dds in IM.child_devices:
                        #print(dds.name)
                        try:
                            prefix, channel = dds.connection.split()
                            channel = int(channel)
                        except:
                            raise LabscriptError('%s has invalid connection string: \'%s\'. ' % (dds.name, str(dds.connection)) + 'Format must be \'channel n\' with n from 0 to 4.')

                        gate = dds.gate
                        print(gate.name)
                        gate_cl = gate.parent_device.parent_device
                        gate_ps = gate_cl.parent_device
                        print(gate_ps.times[gate_cl])
                        print(gate.raw_output)
                        print(gate.child_devices)



                        # for connection in DDSs:
                        #     if connection in range(2):
                        #         # Dynamic DDS
                        #         dds = DDSs[connection]
                        #         print(dds.frequency.scale_factor)
                        #     else:
                        #         raise LabscriptError('%s %s has invalid connection string: \'%s\'. '%(dds.description,dds.name,str(dds.connection)) +
                        #                              'Format must be \'channel n\' with n from 0 to 4.')

                        times = pseudoclock.times[clockline]
                        print(f"'{dds.name}' times: {times}")
                        #print(f"'{self.name}' DDSs: {DDSs}")

                        # TODO: enable/disable act on the TTL. in table mode we need to know the RF level and set amp to minimum / last level.
                        #       if level is never set use manual values

                        out_table = np.zeros(len(times), dtype=dtypes)
                        out_table['freq'].fill(DEFAULT_RF_FREQ)

                        #print(f"Channel {connection} output: {[dds.frequency.raw_output,dds.amplitude.raw_output,dds.phase.raw_output]}")
                        # The last two instructions are left blank, for BLACS
                        # to fill in at program time.
                        out_table['time'][:]  = times
                        out_table['freq'][:]  = dds.frequency.raw_output
                        out_table['amp'][:]   = dds.amplitude.raw_output
                        out_table['phase'][:] = dds.phase.raw_output

                        grp.create_dataset('TABLE_DATA%i'%channel, compression=config.compression, data=out_table)
                        flags = (FLAG_TABLE_MODE if IM.table_mode else 0) | (FLAG_TRIGGER_EACH_STEP if IM.trigger_each_step else 0)
                        grp.create_dataset('TABLE_OPT%i' % channel, compression=config.compression, data=np.array([flags], dtype=np.uint8))

                        print(f"'{dds.name}' generate_code, out_table:\n time/freq/amp/phase\n", out_table)


# Andi: power check boxes for each DDS
class power_check_boxes(QWidget):
    labels = ['signal', 'amplifier', 'both']  # labels for check boxes

    def __init__(self, parent, name, channel, signal=False, amplifier=False, align_horizontal=False):
        super(power_check_boxes, self).__init__(parent._ui)

        # init class
        self.parent    = parent                 # parent (DeviceTab instance)
        self.name      = name                   # channel name in connection table (string)
        self.channel   = channel                # channel number (integer)
        self.signal    = signal                 # initial state of signal check box (bool)
        self.amplifier = amplifier              # initial state of amplifier check box (bool)
        self.both      = signal and amplifier   # initial state of both check box (bool)

        # create layout
        grid = QGridLayout(self)
        self.setLayout(grid)

        # create check boxes
        states  = [signal, amplifier, signal and amplifier]
        connect = [self.onSignal, self.onAmp, self.onBoth]
        self.cb = []
        for i,name in enumerate(self.labels):
            cb = QCheckBox(name)
            cb.setChecked(states[i])
            cb.clicked.connect(connect[i])
            self.cb.append(cb)
            if align_horizontal: grid.addWidget(cb, 0, i)
            else:                grid.addWidget(cb, i, 0)

    def onSignal(self, state):
        # 'signal' clicked: manually insert event into parent event queue. see tab_base_classes.py @define_state(MODE_MANUAL, True)
        self.parent.event_queue.put(allowed_states=MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=False,
                                    data=[self._onSignal, [[self.channel, state], {}]])

    def onAmp(self, state, both=False):
        # 'amplifier' clicked: manually insert event into parent event queue. see tab_base_classes.py @define_state(MODE_MANUAL, True)
        self.parent.event_queue.put(allowed_states=MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=False,
                                    data=[self._onAmp, [[self.channel, state], {}]])

    def onBoth(self, state):
        # 'both' clicked: manually insert event into parent event queue. see tab_base_classes.py @define_state(MODE_MANUAL, True)
        self.parent.event_queue.put(allowed_states=MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=False,
                                    data=[self._onBoth, [[self.channel, state], {}]])

    def _onSignal(self, parent, channel, state):
        # executed by QT main thread (tab_base_classes.py Tab::mainloop). must be generator (with yield).
        info = "'%s' %s signal" % (self.name, 'enable' if state else 'disable')
        result = yield (self.parent.queue_work(self.parent.primary_worker, 'onSignal', channel, state))
        if (result is not None) and result:
            self.signal = state
            print(info)
            self.cb[0].setChecked(self.signal)
            self.set_both()
        else:
            print(info + ' failed!')
            self.cb[0].setChecked(self.signal)

    def _onAmp(self, parent, channel, state):
        # executed by QT main thread (tab_base_classes.py Tab::mainloop). must be generator (with yield).
        info = "'%s' %s amplifier" % (self.name, 'enable' if state else 'disable')
        result = yield (self.parent.queue_work(self.parent.primary_worker, 'onAmp', channel, state))
        if (result is not None) and result:
            self.amplifier = state
            print(info)
            self.cb[1].setChecked(self.amplifier)
            self.set_both()
        else:
            print(info + ' failed!')
            self.cb[1].setChecked(self.amplifier)

    def _onBoth(self, parent, channel, state):
        # executed by QT main thread (tab_base_classes.py Tab::mainloop). must be generator (with yield).
        info = "'%s' %s signal & amplifier" % (self.name, 'enable' if state else 'disable')
        result = yield (self.parent.queue_work(self.parent.primary_worker, 'onBoth', channel, state))
        if (result is not None) and result:
            self.signal    = state
            self.amplifier = state
            print(info)
            self.cb[0].setChecked(self.signal)
            self.cb[1].setChecked(self.amplifier)
            self.set_both()
        else:
            print(info + ' failed!')
            self.cb[2].setChecked(self.both)

    def set_both(self):
        # returns new checked state of 'both' checkbox
        # changes state only when signal and amplifier are both on or both off
        # this allows to click on 'both' to perform the last selection for both.
        if self.both: # both is checked: if only signal or amplifier unchecked keep old state checked, uncheck if both are unchecked.
            self.both = self.signal or self.amplifier
        else: # both is not checked: if only signal or amplifier checked keep old state unchecked, check if both are checked.
            self.both = self.signal and self.amplifier
        self.cb[2].setChecked(self.both)

    def get_save_data(self, data):
        "save current settings to data dictionary"
        state = (4 if self.both else 0)|(2 if self.amplifier else 0)|(1 if self.signal else 0)
        #print('get_save_data state =',state)
        data[self.name] = state

    def restore_save_data(self, data):
        "restore saved settings from data dictionary"
        if self.name in data:
            state = data[self.name]
            #print('restore_save_data state =', state)
            signal = (state & 1) == 1
            amp    = (state & 2) == 2
            both   = (state & 4) == 4
            if (signal == amp) and ((self.signal != signal) or (self.amplifier != amp)):
                self.onBoth(signal)
            else:
                if self.signal != signal: self.onSignal(signal)
                if self.amplifier != amp: self.onAmp(amp)
                self.both = both
                self.cb[2].setChecked(both)

@BLACS_tab
class MOGLabs_QRF_Tab(DeviceTab):
    def initialise_GUI(self):
        # Andi: reduce number of log entries in logfile (labscript-suite/logs/BLACS.log)
        self.logger.setLevel(log_level)

        # Capabilities
        self.base_units = {'freq': 'MHz', 'amp': 'dBm', 'phase': 'Degrees'}
        self.base_min = {'freq': MIN_RF_FREQ, 'amp': MIN_RF_AMP, 'phase': MIN_RF_PHASE}
        self.base_max = {'freq': MAX_RF_FREQ, 'amp': MAX_RF_AMP, 'phase': MAX_RF_PHASE}
        self.base_step = {'freq': 1.0, 'amp': 1.0, 'phase': 1.0}
        self.base_decimals = {'freq': 6, 'amp': 2, 'phase': 3}  # TODO: find out what the phase precision is!
        self.num_DDS = MAX_NUM_CHANNELS

        # Create DDS Output objects
        dds_prop = {}
        for i in range(self.num_DDS):  # 4 is the number of DDS outputs on this device
            dds_prop['channel %d' % i] = {}
            for subchnl in ['freq', 'amp', 'phase']:
                dds_prop['channel %d' % i][subchnl] = {'base_unit': self.base_units[subchnl],
                                                       'min': self.base_min[subchnl],
                                                       'max': self.base_max[subchnl],
                                                       'step': self.base_step[subchnl],
                                                       'decimals': self.base_decimals[subchnl]
                                                       }
        # Create the output objects
        self.create_dds_outputs(dds_prop)
        # Create widgets for output objects
        dds_widgets, ao_widgets, do_widgets = self.auto_create_widgets()
        # and auto place the widgets in the UI
        self.auto_place_widgets(("DDS Outputs", dds_widgets))

        connection_object = self.settings['connection_table'].find_by_name(self.device_name)
        connection_table_properties = connection_object.properties

        self.addr = connection_table_properties['addr']
        self.port = connection_table_properties['port']
        self.worker_args = connection_table_properties['worker_args']

        # Create and set the primary worker
        self.create_worker("main_worker", MOGLabs_QRF_Worker, {'addr': self.addr, 'port': self.port, 'worker_args': self.worker_args})
        self.primary_worker = "main_worker"

        # Set the capabilities of this device
        self.supports_remote_value_check(True)
        self.supports_smart_programming(True)

        # get dictionary of channels with names in connection table
        channels = {}
        for pseudoclock in connection_object.child_list.values():
            #print(pseudoclock.name)
            for clockline in pseudoclock.child_list.values():
                #print(clockline.name)
                for IM in clockline.child_list.values():
                    #print(IM.name)
                    for name, child in IM.child_list.items():
                        channels[child.parent_port] = name
        #print(channels)

        # add check boxes to enable signal/power/both:
        place_below = False # True = below DDS frame, False = right of DDS frame
        layout = self.get_tab_layout()
        index = layout.count()
        self.power_cb = [None for _ in range(MAX_NUM_CHANNELS)]
        for i in range(index):
            widget = layout.itemAt(i).widget()
            if widget is not None:
                children = widget.findChildren(ToolPaletteGroup)
                for child in children:
                    if 'DDS Outputs' in child._widget_groups:
                        index, toolpalette, button = child._widget_groups['DDS Outputs']
                        for j,dds in enumerate(toolpalette._widget_list):
                            layout = dds._layout
                            channel = dds._hardware_name
                            try:
                                channel_index = int(channel.split(' ')[-1])
                            except ValueError:
                                print("unexpected channel name '%s'?")
                                break
                            cb = power_check_boxes(parent=self, name=channels[channel], channel=channel_index, align_horizontal=place_below)
                            if place_below: layout.addWidget(cb)
                            else:           layout.addWidget(cb,1,1)
                            if j < MAX_NUM_CHANNELS:
                                self.power_cb[j] = cb
                            else:
                                print('error: maximum channels %i specified but %i existing!?' % (MAX_NUM_CHANNELS, len(toolpalette._widget_list)))
                                exit()

    def get_save_data(self):
        # Andi: save user selection on shutdown
        data = {}
        for cb in self.power_cb:
            cb.get_save_data(data)
        #print("'%s' get_save_data:" % self.device_name, data)
        return data

    def restore_save_data(self, data):
        # Andi: resore user selection on restart
        #print("'%s' restore_save_data:" % self.device_name, data)
        for cb in self.power_cb:
            cb.restore_save_data(data)

#@BLACS_worker Andi: disabled due to warning
class MOGLabs_QRF_Worker(Worker):
    def init(self):
        global h5py
        import labscript_utils.h5_lock, h5py

        # Andi: reduce number of log entries in logfile (labscript-suite/logs/BLACS.log)
        self.logger.setLevel(log_level)

        self.smart_cache = {'TABLE_DATA': ''}

        # Get a device object
        # Andi: this will fail when there is no connection
        if self.reconnect('init'):
            # info = dev.ask('info')
            # raise(info)
            # TODO wrap ask cmnds with error checking

            # Flush any junk from the buffer
            #self.dev.flush()
            # and turn both channels on
            #for i in range(MAX_NUM_CHANNELS): # disabled by Andi
            #    self.dev.cmd('on,%d' % (i + 1))

            # return self.get_current_values()

            # Andi: switch off output and clear table
            for channel in range(MAX_NUM_CHANNELS):
                self.dev.cmd('OFF,%i' % (channel+1))
                # Added by Ale -> this initializes the QRF in table mode: don't konw if it is what we want
                self.dev.cmd('mode,%i,tsb' % (channel+1))
                #self.dev.cmd('TABLE,STOP,%i' % (channel + 1))
                self.dev.cmd('TABLE,CLEAR,%i' % (channel+1))
            print(f"MOGLabs worker is initialized off, in table mode with cleared table")

    def reconnect(self, name):
        # Andi: try to connect to device. returns True on success, otherwise False.
        #       check if self.dev is None if device is connected or not and call this again.
        try:
            self.dev = MOGDevice(self.addr, self.port)
        except Exception: # on Linux gives OSError, on Windows dont know
            self.dev = None
            #print('%s: no connection.' % (name))
            return False
        self.dev.flush()
        return True

    def check_remote_values(self):
        # Andi: try to reconnect. return 0's on failure.
        results = {}
        if (self.dev is None) and not self.reconnect('check_remote_values'):
            for i in range(MAX_NUM_CHANNELS):
                results['channel %d' % i] = {}
                results['channel %d' % i]['freq'] = 0.0
                results['channel %d' % i]['amp']  = 0.0
                results['channel %d' % i]['phase'] = 0.0
            return results
        # Get the currently output values:
        for i in range(MAX_NUM_CHANNELS):
            results['channel %d' % i] = {}
            freq = float(self.dev.ask('FREQ,%d' % (i + 1)).split()[0])
            amp = float(self.dev.ask('POW,%d' % (i + 1)).split()[0])
            phase = float(self.dev.ask('PHASE,%d' % (i + 1)).split()[0])

            results['channel %d' % i]['freq'] = freq
            results['channel %d' % i]['amp'] = amp
            results['channel %d' % i]['phase'] = phase
        # print(results)
        return results

    def program_manual(self, front_panel_values):
        # try to reconnect. return on failure.
        if (self.dev is None) and (not self.reconnect('program_manual')):
            return
        # TODO: Optimise this so that only items that have changed are reprogrammed by storing the last programmed values
        # For each DDS channel,
        for i in range(MAX_NUM_CHANNELS):
            # self.dev.cmd('FREQ,%d,20MHz'%(i+1))
            # self.dev.cmd('POW,%d,0 dBm'%(i+1))
            # self.dev.cmd('PHASE,%d,0deg'%(i+1))

            # and for each subchnl in the DDS,
            for subchnl in ['freq', 'amp', 'phase']:
                # print('f', front_panel_values['channel %d'%i][subchnl])
                self.program_static(i, subchnl, front_panel_values['channel %d' % i][subchnl])
        return self.check_remote_values()

    def program_static(self, channel, type, value):
        if type == 'freq':
            # print(value)
            command = 'FREQ,%d,%fMHz' % (channel + 1, value)
            self.dev.cmd(command)
        elif type == 'amp':
            # print(value)
            command = 'POW,%d,%f dBm' % (channel + 1, value)
            self.dev.cmd(command)
            # self.dev.cmd('POW,%d,0 dBm'%(channel+1))
        elif type == 'phase':
            # print(value)
            command = 'PHASE,%d,%fdeg' % (channel + 1, value)
            self.dev.cmd(command)
            # self.dev.cmd('PHASE,%d,0deg'%(channel+1))
        else:
            raise TypeError(type)
        # Now that a static update has been done, we'd better invalidate the saved STATIC_DATA:
        # self.smart_cache['STATIC_DATA'] = None

    def transition_to_buffered(self, device_name, h5file, initial_values, fresh):
        # try to reconnect. return on failure.
        if (self.dev is None) and (not self.reconnect('check_remote_values')):

            if True:
                # Andi test read table data for each channel
                # program device below in this way
                print('%s cannot connect. test reading hdf5 file....' % (device_name))
                with h5py.File(h5file, 'r') as hdf5_file:
                    group = hdf5_file['/devices/' + device_name]
                    # If there are values to set the unbuffered outputs to, set them now:
                    # if 'STATIC_DATA' in group:
                    #     static_data = group['STATIC_DATA'][:][0]
                    # Now program the buffered outputs:
                    for i in range(MAX_NUM_CHANNELS):
                        table_name = 'TABLE_OPT%i'%i
                        if table_name in group:
                            flags = group[table_name][:][0]
                            print('%s / channel %i options:' % (device_name, i), flags)
                            table_mode        = (flags & FLAG_TABLE_MODE       ) == FLAG_TABLE_MODE
                            trigger_each_step = (flags & FLAG_TRIGGER_EACH_STEP) == FLAG_TRIGGER_EACH_STEP
                            print('table mode %s, trigger each step %s' % (table_mode, trigger_each_step))
                        table_name = 'TABLE_DATA%i'%i
                        if table_name in group:
                            table_data = group[table_name][:]  # Skip last line?: ale
                            print('%s / channel %i data:' % (device_name, i), table_data)

                return True # avoid every time to restart during testing

            return False

        # Andi: TODO update code as in test case without connection above!
        # each channel can be in table mode or not and in table mode can be triggered one time or each step
        # these options are given in connection table.
        # the table_data contains time/frequency/amplitude/phase for all cases.
        # time is in seconds and needs to be divided by 5us and is needed only in table mode with single trigger.


        # Store the initial values in case we have to abort and restore them:
        self.initial_values = initial_values
        print(f"'{device_name}'Transition to buffered. Device info: {self.dev.ask('info')}  ")
        # Store the final values to for use during transition_to_static:
        self.final_values = {}
        # static_data = None
        table_data = None
        # Commented by Ale
        #with h5py.File(h5file) as hdf5_file: 
        # Added by Ale
        self.shot_file = h5file
        with h5py.File(self.shot_file, 'r') as hdf5_file:
            group = hdf5_file['/devices/' + device_name]
            # If there are values to set the unbuffered outputs to, set them now:
            # if 'STATIC_DATA' in group:
            #     static_data = group['STATIC_DATA'][:][0]
            # Now program the buffered outputs:
            if 'TABLE_DATA' in group:
                table_data = group['TABLE_DATA'] [:] # Skip last line?: ale

        # all channels go to table mode
        for channel in range(MAX_NUM_CHANNELS):
            self.dev.cmd(f'MODE,{channel+1},TSB')            
            # Added by Ale 
            #self.dev.cmd(f'TABLE,CLEAR,{channel+1}')            
            self.dev.cmd(F'TABLE,EDGE,{channel+1},FALLING') # set trigger edge rising

        print(f"'{device_name}'in table mode")
        # Now program the buffered outputs:
        if table_data is not None:
            data = table_data
            # Add switch off 
            #data.append(f'{data[-1,0]}, {data[-1,1]}, {data[-1,2]}, {data[-1,3]}, 0, 0, 0, 0, 0x0, 0x0, 0x0, 0x0')
            #print(f"Table data: {data}")
            for i, line in enumerate(data):
                st = time.time()
                oldtable = self.smart_cache['TABLE_DATA']
                for ddsno in range(MAX_NUM_CHANNELS):
                    if fresh or i >= len(oldtable) or (
                    line['freq%d' % ddsno], line['phase%d' % ddsno], line['amp%d' % ddsno]) != (
                    oldtable[i]['freq%d' % ddsno], oldtable[i]['phase%d' % ddsno], oldtable[i]['amp%d' % ddsno]):
                        #command = 'table,entry,%d,%d,%fMHz,%fdBm,%fdeg,1,trig' % ( # gives always invalid table enry!?
                        #ddsno + 1, i + 1, line['freq%d' % ddsno], line['amp%d' % ddsno], line['phase%d' % ddsno])
                        command = 'TABLE,APPEND,%d,%i,%.3f,%.3f,0' % (
                        ddsno + 1, line['freq%d' % ddsno], line['amp%d' % ddsno], line['phase%d' % ddsno])
                        print(f"A line in the table of Ch {ddsno+1} has changed: sending command", command)
                        self.dev.cmd(command)
                et = time.time()
                tt = et - st
                self.logger.debug('Time spent on line %s: %s' % (i, tt))
            # Added by Ale: set the power to 0 at the end of the ramp

            #print('Switch off channels')

            # Store the table for future smart programming comparisons:
            try:
                self.smart_cache['TABLE_DATA'][:len(data)] = data
                self.logger.debug('Stored new table as subset of old table')
            except:  # new table is longer than old table
                self.smart_cache['TABLE_DATA'] = data
                self.logger.debug('New table is longer than old table and has replaced it.')

            # Get the final values of table mode so that the GUI can
            # reflect them after the run:
            self.final_values['channel 0'] = {}
            self.final_values['channel 1'] = {}
            self.final_values['channel 2'] = {}
            self.final_values['channel 3'] = {}

            self.final_values['channel 0']['freq'] = data[-1]['freq0']
            self.final_values['channel 1']['freq'] = data[-1]['freq1']
            self.final_values['channel 2']['freq'] = data[-1]['freq2']
            self.final_values['channel 3']['freq'] = data[-1]['freq3']
            self.final_values['channel 0']['amp'] = data[-1]['amp0']
            self.final_values['channel 1']['amp'] = data[-1]['amp1']
            self.final_values['channel 2']['amp'] = data[-1]['amp2']
            self.final_values['channel 3']['amp'] = data[-1]['amp3']
            self.final_values['channel 0']['phase'] = data[-1]['phase0']
            self.final_values['channel 1']['phase'] = data[-1]['phase1']
            self.final_values['channel 2']['phase'] = data[-1]['phase2']
            self.final_values['channel 3']['phase'] = data[-1]['phase3']
            
            # Transition to table mode:
            # Set the number of entries for each channel

            for ch in range(MAX_NUM_CHANNELS):
                self.dev.cmd(f'TABLE,APPEND,{ch+1},10,0x0,0,0') # Switch off
                self.dev.cmd(f'TABLE,ENTRIES,{ch+1},{len(data)+1}')
                self.dev.cmd(f'TABLE,ARM,{ch+1}')
                print(f"Ch {ch+1}: armed with {len(data)+1} entries")



        # import time
        # time.sleep(1)
            #print(f"Table final values: {self.final_values}")
        return self.final_values

    def abort_transition_to_buffered(self):
        return self.transition_to_manual(True)

    def abort_buffered(self):
        # TODO: untested
        return self.transition_to_manual(True)

    def transition_to_manual(self, abort=False):
        print('Transition to manual')
        if self.dev is not None:
            for channel in range(MAX_NUM_CHANNELS):
                print(f"Stopping Ch {channel+1}")
                #self.dev.cmd('TABLE,STOP,%i' % (channel + 1))
                #self.dev.cmd('TABLE,CLEAR,%i' % (channel + 1))
                self.dev.cmd(f"OFF,{channel+1},SIG")
                self.dev.cmd('MODE,%i,NSB' % (channel+1))


            if abort:
                DDSs = [] # Andi to avoid problems
                #pass
                # If we're aborting the run, then we need to reset DDSs 2 and 3 to their initial values.
                # 0 and 1 will already be in their initial values. We also need to invalidate the smart
                # programming cache for them.
                # values = self.initial_values
                # DDSs = [2,3]
                # self.smart_cache['STATIC_DATA'] = None
            else:
                # If we're not aborting the run, then we need to set DDSs 0 and 1 to their final values.
                # 2 and 3 will already be in their final values.
                values = self.final_values
                DDSs = [0, 1, 2, 3]

            # only program the channels that we need to
            for ddsnumber in DDSs:
                channel_values = values['channel %d' % ddsnumber]
                for subchnl in ['freq', 'amp', 'phase']:
                    self.program_static(ddsnumber, subchnl, channel_values[subchnl])

        # return True to indicate we successfully transitioned back to manual mode
        return True

    def shutdown(self):
        # Andi: execute only when we are connected
        if self.dev is not None:
            # turn both channels off
            for i in range(MAX_NUM_CHANNELS):
                self.dev.cmd('off,%d,all' % (i + 1))
            self.dev.close()

    # Andi: switch RF signal on/off. returns True if ok, False on error.
    def onSignal(self, channel, state):
        cmd = 'ON' if state else 'OFF'
        info = "'%s' channel %i: RF signal %s" % (self.device_name, channel, cmd)
        if self.dev is not None:
            self.dev.cmd('%s,%i,SIG' % (cmd, channel + 1))
            print(info)
            return True
        print(info + ' failed!')
        return False

    # Andi: switch RF amplifier on/off. returns True if ok, False on error.
    def onAmp(self, channel, state):
        cmd = 'ON' if state else 'OFF'
        info = "'%s' channel %i: RF amplifier %s" % (self.device_name, channel, cmd)
        if self.dev is not None:
            self.dev.cmd('%s,%i,POW' % (cmd, channel + 1))
            print(info)
            return True
        print(info + ' failed!')
        return False

    # Andi: switch RF signal & amplifier on/off. returns True if ok, False on error.
    def onBoth(self, channel, state):
        cmd = 'ON' if state else 'OFF'
        info = "'%s' channel %i: RF signal & amplifier %s" % (self.device_name, channel, cmd)
        if self.dev is not None:
            self.dev.cmd('%s,%i,ALL' % (cmd, channel + 1))
            print(info)
            return True
        print(info + ' failed!')
        return False

# @runviewer_parser
# class RunviewerClass(object):
#     def __init__(self, path, device):
#         self.path = path
#         self.name = device.name
#         self.device = device
#
#     def get_traces(self, add_trace, clock=None):
#         if clock is None:
#             # we're the master pseudoclock, software triggered. So we don't have to worry about trigger delays, etc
#             raise Exception('No clock passed to %s. The XRF021 must be clocked by another device.'%self.name)
#
#         times, clock_value = clock[0], clock[1]
#
#         clock_indices = np.where((clock_value[1:]-clock_value[:-1])==1)[0]+1
#         # If initial clock value is 1, then this counts as a rising edge (clock should be 0 before experiment)
#         # but this is not picked up by the above code. So we insert it!
#         if clock_value[0] == 1:
#             clock_indices = np.insert(clock_indices, 0, 0)
#         clock_ticks = times[clock_indices]
#
#         # get the data out of the H5 file
#         data = {}
#         with h5py.File(self.path, 'r') as f:
#             if 'TABLE_DATA' in f['devices/%s'%self.name]:
#                 table_data = f['devices/%s/TABLE_DATA'%self.name][:]
#                 for i in range(MAX_NUM_CHANNELS):
#                     for sub_chnl in ['freq', 'amp', 'phase']:
#                         data['channel %d_%s'%(i,sub_chnl)] = table_data['%s%d'%(sub_chnl,i)][:]
#
#             if 'STATIC_DATA' in f['devices/%s'%self.name]:
#                 static_data = f['devices/%s/STATIC_DATA'%self.name][:]
#                 for i in range(2,4):
#                     for sub_chnl in ['freq', 'amp', 'phase']:
#                         data['channel %d_%s'%(i,sub_chnl)] = np.empty((len(clock_ticks),))
#                         data['channel %d_%s'%(i,sub_chnl)].fill(static_data['%s%d'%(sub_chnl,i)][0])
#
#
#         for channel, channel_data in data.items():
#             data[channel] = (clock_ticks, channel_data)
#
#         for channel_name, channel in self.device.child_list.items():
#             for subchnl_name, subchnl in channel.child_list.items():
#                 connection = '%s_%s'%(channel.parent_port, subchnl.parent_port)
#                 if connection in data:
#                     add_trace(subchnl.name, data[connection], self.name, connection)
#
#         return {}
