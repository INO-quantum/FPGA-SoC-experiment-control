#####################################################################
#                                                                   #
# /NI_DAQmx/blacs_workers.py                                        #
#                                                                   #
# Copyright 2018, Monash University, JQI, Christopher Billington    #
#                                                                   #
# This file is part of the module labscript_devices, in the         #
# labscript suite (see http://labscriptsuite.org), and is           #
# licensed under the Simplified BSD License. See the license.txt    #
# file in the root of the project for the full license.             #
#                                                                   #
#####################################################################

# Jan-May 2024, modified by Andi to generate pseudoclock with NIDAQmx counter.
# last change 14/6/2024 by Andi

import sys
import time
import threading
import logging
try:
    from PyDAQmx import *
    from PyDAQmx.DAQmxConstants import *
    from PyDAQmx.DAQmxTypes import *
    from PyDAQmx.DAQmxCallBack import *
except Exception:
    # simulate everything
    from ctypes import c_uint as uInt32
    from ctypes import c_int as int32
    from ctypes import c_ulonglong as uInt64
    from ctypes import create_string_buffer, POINTER, c_uint32
    from user_devices.NI_DAQmx_iPCdev.NI_DAQmx_simulate import (
        DAQmxResetDevice,
        Task,
        DAQmx_Val_GroupByChannel, DAQmx_Val_GroupByScanNumber,
        DAQmx_Val_ChanPerLine, DAQmx_Val_ChanForAllLines,
        DAQmx_Val_Volts,
        DAQmx_Val_Rising, DAQmx_Val_Falling,
        DAQmx_Val_FiniteSamps,
        DAQmx_Val_Low, DAQmx_Val_High,
        DAQmxGetDevCOPhysicalChans,
    )

import numpy as np
from numpy.lib.recfunctions import structured_to_unstructured
import labscript_utils.h5_lock
import h5py
from zprocess import Event
from zprocess.utils import _reraise
from labscript import LabscriptError

import labscript_utils.properties as properties
from labscript_utils import dedent
from labscript_utils.connections import _ensure_str

from user_devices.iPCdev.labscript_devices import (
    DEVICE_HARDWARE_INFO, DEVICE_DEVICES, DEVICE_SEP,
    DEVICE_TIME, DEVICE_DATA_DO, DEVICE_DATA_AO,
    DEVICE_INFO_TYPE, DEVICE_INFO_PATH, DEVICE_INFO_ADDRESS, DEVICE_INFO_CHANNEL, DEVICE_INFO_BOARD,
    HARDWARE_TYPE, HARDWARE_TYPE_AO, HARDWARE_TYPE_DO,
    HARDWARE_SUBTYPE, HARDWARE_SUBTYPE_STATIC, HARDWARE_SUBTYPE_TRIGGER,
)
from user_devices.iPCdev.blacs_workers import iPCdev_worker, SYNC_RESULT_OK, SYNC_RESULT_TIMEOUT, SYNC_RESULT_TIMEOUT_OTHER
from user_devices.NI_DAQmx_iPCdev.labscript_devices import START_TRIGGER_EDGE_RISING, START_TRIGGER_EDGE_FALLING, DAQMX_INTERNAL_CLOCKRATE

from labscript_devices.NI_DAQmx.utils import split_conn_port, split_conn_DO
from .labscript_devices import NI_DAQmx_iPCdev

# for testing
from user_devices.h5_file_parser import read_group

# display status information only every UPDATE_TIME seconds
UPDATE_TIME         = 1.0

# if True reset sync counter each run.
# TODO: False case is tested quite a lot and seems to work (although maybe in very rare cases could still cause timeout).
#       True case is not much tested. this was original approach but did not worked due to subtle timing problems.
#       these problems were debugged and hopefully all fixed and now also this case should work again.
#       the problems mainly occur when restarting boards, after compilation or start of blacs, but only in rare cases.
#       so its not so easy to detect if it is working now or not.
SYNC_RESET_EACH_RUN = False

# bytes to allocate for counter port
COUNTER_BUFSIZE     = 128

# maximum number of samples for static output
STATIC_MAX_SAMPLES  = 2

# timeouts in seconds
TIMEOUT_WRITE       = 20.0
TIMEOUT_READ_FILE   = 20.0
TIMEOUT_WAIT_STATIC = 2.0
TIMEOUT_DONE        = 1.0

# options
WAIT_STATIC_AO_TASK_DONE    = False     # enabling gives timeout error while for DO it is fine?
WAIT_STATIC_DO_TASK_DONE    = False     # not required but better to to do. might timeout?
LOCK_REFCLOCK_AO_DO         = True      # required, otherwise get an error

# output channel info for each run for CO/AO/DO channels. set to None if should not print this
# device name, number and type of channels, counter port name, number of samples, additional info
CHANNEL_INFO = '%-16s %-26s %26s %16s %10i samples%s'

# minimum low and high time in seconds and ticks. for ticks depends on the clock rate.
MIN_TIME            = 60e-9
MIN_TICKS_10MHz     = 2
MIN_TICKS_100MHz    = 3

def get_clock_ticks(times, clock_rate=None, values=None, safe_state=None, min_time_or_ticks=None):
    """
    convert times to low and high times.
    returns (low,high) times if values is not None
    returns (clock,values) if values == True
    returns values if values is np.ndarray.
    times      = numpy array of times in seconds
    clock_rate = if None returned times are in seconds
                 otherwise clock rate in Hz to convert times into ticks
    values     = if not None and values == True:
                 returns (clock,values) for runviewer to show clock ticks.
                 with clock = absolute time of clock changing state.
                 and values = clock high/low states.
                 if not None and values is numpy.ndarray:
                 returns expanded values for runviewer to show data for clock.
                 expanded values have same length as given clock times.
    min_time_or_ticks = minimum time or ticks the hardware allows, see MIN_TIME or MIN_TICKS_ constants.
                 for None MIN_TIME or MIN_TICKS_100MHz is taken.
    safe_state = if not None and values is not None:
                 expanded values start and end in this state.
    notes:
    - the returned low and high times are used to program the counter.
      there will be in total 2x len(times) transitions of the counter output PFI terminal.
      the initial state of the PFI is assumed low and on each rising edge of the PFI
      the connected (output) devices will change to the next programmed state.
      the final state of the PFI is high but will go back to low after the task ended.
      this way the initial and final state of the PFI is always the same (low).
      TODO: I do not know when the PFI goes low after the task is ended.
    - after the start of the task (software or hardware trigger) the counter ouput PFI goes high
      after the first low time. we cannot set this to 0 but we set it to MIN_TIME or MIN_TICKS_.
      these values are given by hardware and might be different for different hardware.
      so there is always a small fixed delay between the start and the first action.
      this is also taken into account for displaying purpose when values is not None
    - labscript always generates len(times) >= 2 and times[-1] == times[-2].
      this is needed for some devices.
      at the moment we keep the last sample although it could be skipped.
      this is also displayed if values is not None.
      TODO: a safe_state might be defined for all channels and instead of repeating the last data sample,
            the last programmed value might be set (external to this function) to the safe state.
            for displaying with values is not None safe_state can be given already here.
    - if values is not None the function returns data to be displayed in runviewer and not to be programmed!
      if values = True then returned (clock,values) represent the time and values of the PFI output
      if values is numpy.ndarray then the returned expanded values can be used to display the channel values
      together with the clock times given as input.
    """
    if values is not None and isinstance(values, (np.ndarray, list, tuple)):
        # expand values to match clock times
        # first time = 0 with value = 0 assumed initial state
        # next entries: 2x repeated values
        # labscript gives always value[-1] = value[-2]
        expanded = np.empty(shape=(len(times),), dtype=values.dtype)
        if safe_state is None:
            expanded[0] = 0
            expanded[1::2] = values
            expanded[2::2] = values
        else:
            expanded[0] = expanded[-1] = safe_state
            expanded[1::2] = values
            expanded[2:-1:2] = values[-1]
        return expanded

    # get half of time differences
    dtime = ((times[1:] - times[:-1]) / 2).astype(np.float64)
    if clock_rate is None:
        # allocate arrays
        if min_time_or_ticks is None: min_time_or_ticks = MIN_TIME
        dtime_low = np.empty(shape=(len(times),), dtype=np.float64, order='C')
        dtime_high = np.empty(shape=(len(times),), dtype=np.float64, order='C')
        dtime_low[0] = min_time_or_ticks
        dtime_low[1:] = dtime
        dtime_high[:-1] = dtime
        dtime_high[-1] = min_time_or_ticks
    else:
        # allocate arrays
        # convert to ticks. minimum is min_time_or_ticks.
        if min_time_or_ticks is None: min_time_or_ticks = MIN_TICKS_100MHz
        ticks = np.round(dtime * clock_rate).astype(np.uint32)
        ticks = np.where(ticks < min_time_or_ticks, min_time_or_ticks, ticks)
        dtime_low = np.empty(shape=(len(times),), dtype=np.uint32, order='C')
        dtime_high = np.empty(shape=(len(times),), dtype=np.uint32, order='C')
        dtime_low[0] = min_time_or_ticks
        dtime_low[1:] = ticks
        dtime_high[:-1] = ticks
        dtime_high[-1] = min_time_or_ticks

    if values is not None:
        if isinstance(values, bool):
            if values:
                # get absolute time from low and high time
                # we insert first time = 0 to indicate the initial state
                # last time is
                clock = np.empty(shape=(2 * len(times) + 1,), dtype=dtime_low.dtype)
                clock[0] = 0.0
                clock[1::2] = dtime_low
                clock[2::2] = dtime_high
                clock = np.cumsum(clock)
                # create clock high/low values
                if safe_state is None:
                    low = 0
                    high = 1
                else:
                    low = safe_state
                    high = 1 if safe_state == 0 else 0
                values = np.tile(np.array([low, high], dtype=np.uint8), int((len(clock) + 1) // 2))[:len(clock)]
                return (clock, values)

    # return low and high times
    return [dtime_low, dtime_high]

class NI_DAQmx_OutputWorker(iPCdev_worker):

    iPCdev_worker.sync_reset_each_run = SYNC_RESET_EACH_RUN

    def init(self):
        global zTimeoutError; from zprocess.utils import TimeoutError as zTimeoutError
        global get_ticks; from time import perf_counter as get_ticks

        super(NI_DAQmx_OutputWorker, self).init()
        #print('worker', self.device_name, 'simulate', self.simulate)

        # set log level
        self.logger.setLevel(logging.INFO)

        #print('channels:', [(ch.name, con)for con, ch in self.channels.items()])
        #print('%i channels', len(self.channels))
        print('clocklines:', [cl.name for cl in self.clocklines]) # TODO: is this needed?
        print('%i AO, counter:' % self.num_AO, self.counter_AO)
        print('%i DO, counter:' % len(self.ports), self.counter_DO)

        # get parameters given to NI_DAQmx_iPCdev.__init__

        # MAX name of device
        self.MAX_name               = self.properties['MAX_name']

        # external terminals (clock and trigger)
        self.clock_terminal         = self.properties['clock_terminal']
        self.clock_rate             = self.properties['clock_rate']
        self.clock_mirror_terminal  = self.properties['clock_mirror_terminal']
        #self.clock_limit            = self.properties['clock_limit']
        self.internal_clock_rate    = self.properties['internal_clock_rate']
        self.start_trigger_terminal = self.properties['start_trigger_terminal']
        self.start_trigger_edge     = self.properties['start_trigger_edge']
        self.connected_terminals    = self.properties['connected_terminals']

        # counter (half used as output, input not possible)
        self.num_CI                 = self.properties['num_CI']

        # analog out
        self.counter_AO             = self.properties['counter_AO']
        self.num_AO                 = self.properties['num_AO']
        self.supports_buffered_AO   = self.properties['supports_buffered_AO']
        self.static_AO              = self.properties['static_AO']
        self.AO_range               = self.properties["AO_range"],
        self.max_AO_sample_rate     = self.properties["max_AO_sample_rate"]

        #  digital out
        self.counter_DO             = self.properties['counter_DO']
        self.ports                  = self.properties['ports']
        self.supports_buffered_DO   = self.properties['supports_buffered_DO']
        self.static_DO              = self.properties['static_DO']
        self.max_DO_sample_rate     = self.properties["max_DO_sample_rate"]

        if False:
            # analog in (not implemented)
            self.num_AI                 = self.properties['num_AI']
            self.acquisition_rate       = self.properties['acquisition_rate']
            self.AI_range               = self.properties['AI_range']
            self.AI_range_Diff          = self.properties['AI_range_Diff']
            self.AI_start_delay         = self.properties['AI_start_delay']
            self.AI_start_delay_ticks   = self.properties['AI_start_delay_ticks']
            self.AI_term                = self.properties['AI_term']
            self.AI_term_cfg            = self.properties['AI_term_cfg']
            self.AI_chans               = self.properties['AI_chans']
            self.max_AI_multi_chan_rate = self.properties['max_AI_multi_chan_rate'],
            self.max_AI_single_chan_rate = self.properties['max_AI_single_chan_rate']
            self.min_semiperiod_measurement = self.properties['min_semiperiod_measurement']
            self.supports_semiperiod_measurement = self.properties['supports_semiperiod_measurement']
            self.supports_simultaneous_AI_sampling = self.properties['supports_simultaneous_AI_sampling']
            # wait monitor (not implemented)
            self.wait_monitor_minimum_pulse_width = self.properties['wait_monitor_minimum_pulse_width']
            self.wait_monitor_supports_wait_completed_events = self.properties['wait_monitor_supports_wait_completed_events']

        # Reset Device: clears previously added routes etc. Note: is insufficient for
        # some devices, which require power cycling to truly reset.
        DAQmxResetDevice(self.MAX_name)

        print("primary               :", self.is_primary)
        print("boards                :", self.boards)
        print("clock terminal        :", self.clock_terminal)
        print("clock mirror terminal :", self.clock_mirror_terminal)
        print("connected terminals   :", self.connected_terminals)
        print("start trigger terminal:", self.start_trigger_terminal)
        print("start trigger edge    :", self.start_trigger_edge)

        # experimental run counter
        self.run_count = 0

        # update time
        self.update_time = UPDATE_TIME

        # tasks
        self.AO_task = None
        self.DO_task = None
        self.CO_tasks = {}

        # dictionary for counter output ports for each used counter.
        # key = counter name self.counter_DO/AO, value = (port name (bytes), board name)
        self.counter_ports = {}
        self.counters_used = 0
        if self.counter_AO is not None: self.counters_used += 1
        if self.counter_DO is not None: self.counters_used += 1

        # last file id used to detect if file has been changed
        self.file_id = None

        # experiment time in seconds and number of samples
        self.exp_time               = 0
        self.exp_samples_CO         = []
        self.exp_samples_AO         = 0
        self.exp_samples_DO         = 0

        # status of all boards in transition_to_manual
        # obtained by primary board and returned to status_monitor with status_end=True
        self.board_status = {}

        # event test:
        if False and self.is_primary:
            events = [self.process_tree.event('prim_test_event_0', role='both'),self.process_tree.event('prim_test_event_1', role='both')]
            num = 10
            for i in range(num):
                events[0].post(i, data=i)
                events[1].post(i, data=i + num)
            time.sleep(1.0)
            for i in range(num):
                try:
                    data = [0,0]
                    data[1] = events[1].wait(i, timeout = 1.0)
                    data[0] = events[0].wait(i, timeout=1.0)
                except zTimeoutError:
                    print('event test %i timeout!' % (i))
                    break
                if (data[0] == i) and (data[1] == i+num):
                    print('event test ok', i)
                else:
                    print('event test ', i, "!=", data)
            del events


        # start in manual mode. program_manual is called after this returns.
        self.initial_values = {}
        self.tasks_manual = True
        self.start_manual_mode_tasks()

    def check_version(self):
        """Check the version of PyDAQmx is high enough to avoid a known bug"""
        major = uInt32()
        minor = uInt32()
        patch = uInt32()
        DAQmxGetSysNIDAQMajorVersion(major)
        DAQmxGetSysNIDAQMinorVersion(minor)
        DAQmxGetSysNIDAQUpdateVersion(patch)

        if major.value == 14 and minor.value < 2:
            msg = """There is a known bug with buffered shots using NI DAQmx v14.0.0.
                This bug does not exist on v14.2.0. You are currently using v%d.%d.%d.
                Please ensure you upgrade to v14.2.0 or higher."""
            raise Exception(dedent(msg) % (major.value, minor.value, patch.value))

    def stop_tasks(self):
        print("stop tasks")
        if self.AO_task is not None:
            self.AO_task.StopTask()
            self.AO_task.ClearTask()
            self.AO_task = None
        if self.DO_task is not None:
            self.DO_task.StopTask()
            self.DO_task.ClearTask()
            self.DO_task = None
        for counter, task in self.CO_tasks.items():
            print('delete counter',counter)
            task.StopTask()
            task.ClearTask()
        self.CO_tasks = {}
        # force reloading of file
        self.file_id = None
        # Remove the mirroring of the clock terminal, if applicable:
        self.set_mirror_clock_terminal_connected(False)
        # Remove connections between other terminals, if applicable:
        self.set_connected_terminals_connected(False)

    def start_manual_mode_tasks(self):
        # Create tasks:
        if self.num_AO > 0:
            self.AO_task = Task(self.device_name + "AOman")
        else:
            self.AO_task = None

        if self.ports:
            self.DO_task = Task(self.device_name + "DOman")
        else:
            self.DO_task = None

        # Setup AO channels
        for i in range(self.num_AO):
            con = self.MAX_name + "/ao%d" % i
            self.AO_task.CreateAOVoltageChan(
                con, "", self.Vmin, self.Vmax, DAQmx_Val_Volts, None
            )

        # Setup DO channels
        for port_str in sorted(self.ports, key=split_conn_port):
            if not self.ports[port_str]['num_lines']:
                continue
            # Add each port to the task:
            con = '%s/%s' % (self.MAX_name, port_str)
            self.DO_task.CreateDOChan(con, "", DAQmx_Val_ChanForAllLines)

        # Start tasks:
        if self.AO_task is not None:
            #print("'%s' start manual mode task 'AO' %i" % (self.device_name, self.run_count))
            self.AO_task.StartTask()
        if self.DO_task is not None:
            #print("'%s' start manual mode task 'DO' %i" % (self.device_name, self.run_count))
            self.DO_task.StartTask()

        self.tasks_manual = True

    def program_manual(self, front_panel_values):
        if front_panel_values == self.initial_values:
            print('program manual (init values)')
        else:
            print('program manual (new values)')
        if not self.tasks_manual:
            self.stop_tasks()
            self.start_manual_mode_tasks()
        #print(front_panel_values)
        written = int32()
        if self.AO_task is not None:
            AO_data = np.zeros(self.num_AO, dtype=np.float64)
            if False: # old code
                for i in range(self.num_AO):
                    AO_data[i] = front_panel_values['ao%d' % i]
            else:
                count = 0
                for connection, device in self.channels.items():
                    hardware_info    = device.properties[DEVICE_HARDWARE_INFO]
                    board            = hardware_info[DEVICE_INFO_BOARD]
                    hardware_type    = hardware_info[DEVICE_INFO_TYPE][HARDWARE_TYPE]
                    #hardware_subtype = hardware_info[DEVICE_INFO_TYPE][HARDWARE_SUBTYPE]
                    if board == self.device_name and (hardware_type == HARDWARE_TYPE_AO):
                        AO_data[count] = front_panel_values[connection]
                        count += 1
                if count != self.num_AO: # sanity check
                    raise LabscriptError("number of AO channels %i != expected %i?" % (count, self.num_AO))
            self.AO_task.WriteAnalogF64(
                1, True, 1, DAQmx_Val_GroupByChannel, AO_data, written, None
            )
            if WAIT_STATIC_AO_TASK_DONE:
                self.AO_task.WaitUntilTaskDone(TIMEOUT_WAIT_STATIC)
            
        if self.DO_task is not None:
            # Due to two bugs in DAQmx, we will always pack our data into a uint32 and
            # write using WriteDigitalU32. The first bug is some kind of use of
            # uninitialised memory when using WriteDigitalLines, discussed here:
            # https://bitbucket.org/labscript_suite
            #     /labscript_devices/pull-requests/56/#comment-83671312
            # The second is that using a smaller int dtype sometimes fails even though
            # it is the correct int size for the size of the port. Using a 32 bit int
            # always works, the additional bits are ignored. This is discussed here:
            # https://forums.ni.com/t5/Multifunction-DAQ
            #     /problem-with-correlated-DIO-on-USB-6341/td-p/3344066
            DO_data = np.zeros(len(self.ports), dtype=np.uint32)
            # new code
            ports_channels = np.zeros(shape=(len(self.ports),), dtype=np.uint8)
            for connection, device in self.channels.items():
                hardware_info    = device.properties[DEVICE_HARDWARE_INFO]
                board            = hardware_info[DEVICE_INFO_BOARD]
                hardware_type    = hardware_info[DEVICE_INFO_TYPE][HARDWARE_TYPE]
                hardware_subtype = hardware_info[DEVICE_INFO_TYPE][HARDWARE_SUBTYPE]
                port             = hardware_info[DEVICE_INFO_ADDRESS]
                line             = hardware_info[DEVICE_INFO_CHANNEL]
                if (board == self.device_name) and (hardware_type == HARDWARE_TYPE_DO) and (hardware_subtype != HARDWARE_SUBTYPE_TRIGGER):
                    DO_data[port] |= front_panel_values[connection] << line
                    ports_channels[port] += 1
            # TODO: static ports not tested
            if np.count_nonzero(ports_channels) > len(self.ports): # sanity check
                raise LabscriptError("number of DO ports %i > maximum %i?" % (np.count_nonzero(ports_channels), len(self.ports)))
            self.DO_task.WriteDigitalU32(
                1, True, 10.0, DAQmx_Val_GroupByChannel, DO_data, written, None
            )
            if WAIT_STATIC_DO_TASK_DONE:
                self.DO_task.WaitUntilTaskDone(TIMEOUT_WAIT_STATIC)

        return {}

    def set_mirror_clock_terminal_connected(self, connected):
        """Mirror the clock terminal on another terminal to allow daisy chaining of the
        clock line to other devices, if applicable"""
        if self.clock_mirror_terminal is None:
            return
        if connected:
            DAQmxConnectTerms(
                self.clock_terminal,
                self.clock_mirror_terminal,
                DAQmx_Val_DoNotInvertPolarity,
            )
        else:
            DAQmxDisconnectTerms(self.clock_terminal, self.clock_mirror_terminal)

    def set_connected_terminals_connected(self, connected):
        """Connect the terminals in the connected terminals list.
        Allows on daisy chaining of the clock line to/from other devices
        that do not have a direct route (see Device Routes in NI MAX)."""
        if self.connected_terminals is None:
            return
        if connected:
            for terminal_pair in self.connected_terminals:
                DAQmxConnectTerms(
                    terminal_pair[0],
                    terminal_pair[1],
                    DAQmx_Val_DoNotInvertPolarity,
                )
        else:
            for terminal_pair in self.connected_terminals:
                DAQmxDisconnectTerms(terminal_pair[0], terminal_pair[1])

    def get_output_tables(self, f, device_name):
        """returns CO, AO and DO tables from open h5file f"""

        CO_table                    = {}
        AO_table                    = {}
        AO_table_static             = {}
        DO_table                    = {}
        DO_table_static             = {}

        self.exp_time = 0
        self.exp_samples_CO = {}
        self.exp_samples_AO = 0
        self.exp_samples_DO = 0

        #read_group(f)

        # load times of board counters connected with AO/DO channels
        # they can be shared between boards and might be different from the AO/DO channels below.
        group = f[DEVICE_DEVICES]
        for device in self.clocklines:
            hardware_info    = device.properties[DEVICE_HARDWARE_INFO]
            board            = hardware_info[DEVICE_INFO_BOARD]
            hardware_type    = hardware_info[DEVICE_INFO_TYPE][HARDWARE_TYPE]
            hardware_subtype = hardware_info[DEVICE_INFO_TYPE][HARDWARE_SUBTYPE]
            if board == self.device_name:
                if (hardware_type == HARDWARE_TYPE_AO) or (hardware_type == HARDWARE_TYPE_DO):
                    if hardware_subtype == HARDWARE_SUBTYPE_TRIGGER:
                        # skip trigger (DO) channel
                        continue
                    static = (hardware_subtype == HARDWARE_SUBTYPE_STATIC)
                    if static:
                        counter = [self.counter_AO, self.counter_DO]
                        if device.parent_port in counter:
                            raise LabscriptError("static device '%s': cannot use counter '%s'!" % (device.name, device.parent_port))
                    else:
                        counter = self.counter_AO if (hardware_type == HARDWARE_TYPE_AO) else self.counter_DO
                        if counter != device.parent_port:
                            print(device.device_class)
                            raise LabscriptError("device '%s': counter '%s' given but '%s' expected!" % (device.name, device.parent_port, counter))
                    g_IM = group[self.device_name + DEVICE_SEP + device.name]
                    times = g_IM[DEVICE_TIME][()]
                    if times is None:
                        raise LabscriptError("device %s: dataset %s not existing!" % (device.name, dataset))
                    elif static and len(times) != 2:
                        raise LabscriptError("device %s: 2 times expected but have got %i!" % (device.name, len(times)))
                    if not static:
                        CO_table[device.parent_port] = times
                    self.exp_samples_CO[device.parent_port] = len(times)
                    #print('loading counter', device.parent_port, '%i times' % len(times))
                    if times[-1] > self.exp_time: self.exp_time = times[-1]
            else:
                # clocklines of other boards should have been already filtered by blacs_tabs
                print("info: clockline %s of other board %s (skip)" % (device.name, hardware_type))
                continue

        # load data tables for analog and digital outputs
        # we load only data for different addresses
        for connection, device in self.channels.items():
            hardware_info    = device.properties[DEVICE_HARDWARE_INFO]
            hardware_type    = hardware_info[DEVICE_INFO_TYPE][HARDWARE_TYPE]
            hardware_subtype = hardware_info[DEVICE_INFO_TYPE][HARDWARE_SUBTYPE]
            board            = hardware_info[DEVICE_INFO_BOARD]
            address          = hardware_info[DEVICE_INFO_ADDRESS]
            if board == self.device_name:
                if (hardware_type == HARDWARE_TYPE_AO):
                    dataset = DEVICE_DATA_AO % (device.name, address)
                elif (hardware_type == HARDWARE_TYPE_DO) and (hardware_subtype != HARDWARE_SUBTYPE_TRIGGER):
                    connection = connection.split(DEVICE_SEP)[0]
                    if connection in DO_table: continue # address already loaded
                    dataset = DEVICE_DATA_DO % (board, address)
                else:
                    continue
            else:
                # devices of other boards should have been already filtered by blacs_tabs
                print("info: device %s of other board %s (skip)" % (device.name, board))
                continue
            group = f[hardware_info[DEVICE_INFO_PATH]]
            times = group[DEVICE_TIME][()]
            data  = group[dataset][()]
            if data is None:
                raise LabscriptError("device %s: dataset %s not existing!" % (device.name, dataset))
            elif hardware_type == HARDWARE_TYPE_AO:
                if hardware_subtype == HARDWARE_SUBTYPE_STATIC:
                    if (len(times) != STATIC_MAX_SAMPLES) or (len(data) != 1):
                        raise LabscriptError("static AO device %s: 2/1 times/data expected but got %i/%i!" % (device.name, len(times), len(data)))
                    AO_table_static[connection] = data
                else:
                    if (len(times) != len(data)):
                        raise LabscriptError("AO device %s: %i times but %i data!" % (device.name, len(times), len(data)))
                    AO_table[connection] = data
                    if self.exp_samples_AO == 0:
                        self.exp_samples_AO = len(data)
                    elif self.exp_samples_AO != len(data):
                        raise LabscriptError("AO device %s: %i samples different than before %i!\neach AO channel must use the same clockline!" % (device.name, self.exp_samples_AO, len(data)))
            elif hardware_type == HARDWARE_TYPE_DO:
                if hardware_subtype == HARDWARE_SUBTYPE_STATIC:
                    if (len(times) != STATIC_MAX_SAMPLES) or (len(data) != 1):
                        raise LabscriptError("static DO device %s: 2/1 times/data expected but got %i/%i!" % (device.name, len(times), len(data)))
                    DO_table_static[connection] = data
                elif hardware_subtype != HARDWARE_SUBTYPE_TRIGGER:
                    if (len(times) != len(data)):
                        raise LabscriptError("DO device %s: %i times but %i data!" % (device.name, len(times), len(data)))
                    DO_table[connection] = data
                    if self.exp_samples_DO == 0:
                        self.exp_samples_DO = len(data)
                    elif self.exp_samples_DO != len(data):
                        raise LabscriptError("DO device %s: %i samples different than before %i!\neach AO channel must use the same clockline!" % (device.name, self.exp_samples_DO, len(data)))
            if times[-1] > self.exp_time: self.exp_time = times[-1]

        return CO_table, AO_table, AO_table_static, DO_table, DO_table_static

    def program_buffered_CO(self, CO_table):
        """
        program counters.
        CO_table = dictionary with key = counter name, value = np.array of times in seconds.
        """
        written = int32()
        info = ''
        for counter, times in CO_table.items():
            if counter in self.CO_tasks:
                task = self.CO_tasks[counter]
                task.ClearTask()
            task = self.CO_tasks[counter] = Task(self.device_name + "CObuf_" + counter.replace('/',''))
            num_samples = len(times)

            # create counter. this implicitly assigns PFI output
            # sourceTerminal = None uses always the internal 100MHz clock
            # if needed this clock can be locked with PLL to external source
            # minimum ticks = min_ticks_100MHz
            task.CreateCOPulseChanTicks(counter                 = counter,
                                        nameToAssignToChannel   = '',
                                        sourceTerminal          = None,
                                        idleState               = DAQmx_Val_Low,
                                        initialDelay            = 0,
                                        lowTicks                = MIN_TICKS_100MHz,
                                        highTicks               = MIN_TICKS_100MHz)

            # lock internal 100MHz clock to external clock at given rate
            # this must be set for all tasks, othwerwise get an error thar resources are already in use
            # we have seen a similar behaviour with C code.
            if self.clock_terminal is not None:
                task.SetRefClkSrc(self.clock_terminal)
                task.SetRefClkRate(self.clock_rate)

            if self.start_trigger_terminal is not None:
                # set external start trigger channel
                if self.start_trigger_edge is None:
                    edge = DAQmx_Val_Rising
                else:
                    edge = DAQmx_Val_Rising if self.start_trigger_edge == START_TRIGGER_EDGE_RISING else DAQmx_Val_Falling
                task.CfgDigEdgeStartTrig(self.start_trigger_terminal, edge)

            # setup implicit timing with finite samples
            task.CfgImplicitTiming(sampleMode=DAQmx_Val_FiniteSamps, sampsPerChan=num_samples)

            # write times to counter. times are given as pointer to a continuous array of uint32.
            # get difference of times (as numpy.ndarray) and divide evenly between high and low time
            # the first low time we want to be as short as possible.
            ticks_low, ticks_high = get_clock_ticks(times, clock_rate=self.internal_clock_rate, min_time_or_ticks=MIN_TICKS_100MHz)
            ptr_low  = ticks_low.ctypes.data_as(POINTER(c_uint32))
            ptr_high = ticks_high.ctypes.data_as(POINTER(c_uint32))
            result = task.WriteCtrTicks(
                               numSampsPerChan          = num_samples,
                               autoStart                = 0,
                               timeout                  = TIMEOUT_WRITE,
                               dataLayout               = DAQmx_Val_GroupByChannel,
                               highTicks                = ptr_high,
                               lowTicks                 = ptr_low,
                               numSampsPerChanWritten   = written,
                               reserved                 = None
                               )
            if (result != 0) or (written.value != len(times)):
                raise LabscriptError("counter write result %i (%i/%i written)!" % (result, written.value, num_samples))

            if counter not in self.counter_ports:
                # get the counter output port
                # note: if this is called too early gives strange error -200216:
                #       DAQmx Error: Buffered operations cannot use a Data Transfer Mechanism of Programmed I/O for this device and Channel Type.
                name = create_string_buffer(COUNTER_BUFSIZE)
                error = task.GetCOPulseTerm(counter, name, COUNTER_BUFSIZE)
                if error != 0:
                    raise LabscriptError("DAQmxGetCOPulseTerm returned error %i" % (error))

                # save port and board
                self.counter_ports[counter] = (name.value.decode('utf-8'), self.device_name)

                info = ' (shared)'

            if CHANNEL_INFO is not None:
                print(CHANNEL_INFO % (self.device_name, '1 counter %s' % counter,
                                      self.counter_ports[counter][0], self.counter_ports[counter][1],
                                      num_samples, info))


    def program_static_AO(self, AO_table_static):
        """
        set all static analog ouput channels.
        returns dictionary of the final values of each channel.
        """

        final_values    = {}

        if (AO_table_static is not None) and (len(AO_table_static) > 0):
            task     = Task(self.device_name + "AOstat")
            array_static    = np.empty(shape=(len(AO_table_static),), dtype=np.float64)
            num_static      = 0
            num_samples     = 1
            written         = int32()

            for name, data in AO_table_static.items():
                con = self.MAX_name + '/' + name
                array_static[num_static] = data[0]
                task.CreateAOVoltageChan(con, "", self.Vmin, self.Vmax, DAQmx_Val_Volts, None)
                final_values[name] = data[-1]
                num_static += 1

            # Static AO. Start the task and write data, no timing configuration.
            task.StartTask()
            result = task.WriteAnalogF64(
                num_samples,
                True,
                TIMEOUT_WRITE,
                DAQmx_Val_GroupByChannel,
                np.ascontiguousarray(array_static),
                #array_static,
                written,
                None
            )
            if (result != 0) or (written.value != num_samples):
                raise LabscriptError("static AO write result %i (%i/%i written)!" % (result, written.value, num_samples))

            if WAIT_STATIC_AO_TASK_DONE:
                task.WaitUntilTaskDone(TIMEOUT_WAIT_STATIC)
            task.StopTask()
            task.ClearTask()

            if CHANNEL_INFO is not None:
                print(CHANNEL_INFO % (self.device_name, '%i static AO channels'%len(AO_table_static), '', '', num_samples, ''))

        return final_values

    def program_buffered_AO(self, AO_table):

        final_values    = {}
        num_buffered    = 0
        num_samples     = None
        matrix_buffered = None
        written         = int32()
        info            = ''

        if (AO_table is not None) and (len(AO_table) > 0):

            for name, data in AO_table.items():
                if num_samples is None:
                    num_samples = len(data)

                    if self.AO_task is not None:
                        self.AO_task.ClearTask()
                    self.AO_task = Task(self.device_name + "AObuf")

                    matrix_buffered = np.empty(shape=(len(AO_table), num_samples), dtype=np.float64)
                elif len(data) != num_samples:
                    raise LabscriptError("channel '%s' number of samples %i != %i! different clocklines for different channels is not supported at the moment." % (name, len(data), num_samples))
                final_values[name] = data[-1]

                con = self.MAX_name + '/' + name
                matrix_buffered[num_buffered] = data
                self.AO_task.CreateAOVoltageChan(con, "", self.Vmin, self.Vmax, DAQmx_Val_Volts, None)

                num_buffered += 1

            # lock internal 100MHz clock to external clock at given rate.
            # this must be set also for DO/AO tasks as for the counters, otherwise get an error that resources are already in use.
            # however, for the PXIe-6535 board without counters we cannot set this, otherwise we get another error.
            # we have seen a similar behaviour with C code.
            if (self.clock_terminal is not None) and LOCK_REFCLOCK_AO_DO:
                length = DAQmxGetDevCOPhysicalChans(self.MAX_name, None, 0);
                if length == 0:
                    info = ' (no internal counter)'
                else:
                    self.AO_task.SetRefClkSrc(self.clock_terminal)
                    self.AO_task.SetRefClkRate(self.clock_rate)

            # get counter port
            try:
                counter_port, counter_board = self.counter_ports[self.counter_AO]
            except KeyError:
                raise LabscriptError("AO counter '%s' port not found!" % (self.counter_DO))

            # Set up timing:
            self.AO_task.CfgSampClkTiming(
                counter_port.encode('utf-8'),
                self.max_AO_sample_rate,
                DAQmx_Val_Rising,
                DAQmx_Val_FiniteSamps,
                num_samples,
            )

            # Write data:
            result = self.AO_task.WriteAnalogF64(
                num_samples,
                False,
                TIMEOUT_WRITE,
                DAQmx_Val_GroupByChannel, #DAQmx_Val_GroupByScanNumber,
                np.ascontiguousarray(matrix_buffered),
                written,
                None,
            )

            if (result != 0) or (written.value != num_samples):
                raise LabscriptError("AO write result %i (%i/%i written)!" % (result, written.value, num_samples))

            if CHANNEL_INFO is not None:
                print(CHANNEL_INFO % (self.device_name, '%i buffered AO channels'%len(AO_table),
                                      counter_port, counter_board,
                                      num_samples, info))

        return final_values

    def program_static_DO(self, DO_table_static):
        """
        set all static digital ouput channels.
        returns dictionary of the final values of each channel.
        """
        final_values = {}

        if (DO_table_static is not None) and (len(DO_table_static) > 0):
            task         = Task(self.device_name + "DOstat")
            array_static = np.empty(shape=(len(DO_table_static),), dtype=np.uint32)
            num_static   = 0
            num_samples  = 1
            written      = int32()

            for port_str, data in DO_table_static.items():
                # Add each port to the static task
                if data[0] != data[-1]:
                    print(data)
                    raise LabscriptError("channel '%s': %i data not the same!" % (port_str, len(data)))

                #print('port', port_str, 'data', data)
                # Collect the final values of the lines on this port:
                port_final_value = data[-1]
                for line in range(self.ports[port_str]["num_lines"]):
                    # Extract each digital value from the packed bits:
                    line_final_value = bool((1 << line) & port_final_value)
                    final_values['%s/line%d' % (port_str, line)] = int(line_final_value)

                con = '%s/%s' % (self.MAX_name, port_str)
                array_static[num_static] = data[0]
                task.CreateDOChan(con, "", DAQmx_Val_ChanForAllLines)
                num_static += 1

            # Static DO. Start the task and write data, no timing configuration.
            task.StartTask()
            # Write data. See the comment in self.program_manual as to why we are using
            # uint32 instead of the native size of each port
            result = task.WriteDigitalU32(
                num_samples,
                False,
                TIMEOUT_WRITE,
                DAQmx_Val_GroupByScanNumber,
                np.ascontiguousarray(array_static),
                written,
                None,
            )
            if (result != 0) or (written.value != num_samples):
                raise LabscriptError("static DO write result %i (%i/%i written)!" % (result, written.value, num_samples))

            if WAIT_STATIC_DO_TASK_DONE:
                task.WaitUntilTaskDone(TIMEOUT_WAIT_STATIC)
            task.StopTask()
            task.ClearTask()

            if CHANNEL_INFO is not None:
                print(CHANNEL_INFO % (self.device_name, '%i static DO ports'%len(DO_table_static), '', '', num_samples, ''))

        return final_values

    def program_buffered_DO(self, DO_table):
        """
        Create the DO task and program in the DO table for a shot.
        Return a dictionary of the final values of each channel.
        """
        written         = int32()
        final_values    = {}
        num_buffered    = 0
        num_samples     = None
        matrix_buffered = None
        info            = ''

        if len(DO_table) > 0:

            for port_str, data in DO_table.items():
                # create port, save data into matrix_buffered and get final values of each channel
                if num_samples is None:
                    num_samples = len(data)

                    if self.DO_task is not None:
                        self.DO_task.ClearTask()
                    self.DO_task = Task(self.device_name + "DObuf")

                    matrix_buffered = np.empty(shape=(len(DO_table), num_samples), dtype=np.uint32)
                elif len(data) != num_samples:
                    raise LabscriptError("channel '%s' number of samples %i != %i! different clocklines for different channels is not supported at the moment." % (port_str, len(data), num_samples))

                #print('port', port_str, 'data', data)
                # Collect the final values of the lines on this port:
                port_final_value = data[-1]
                for line in range(self.ports[port_str]["num_lines"]):
                    # Extract each digital value from the packed bits:
                    line_final_value = bool((1 << line) & port_final_value)
                    final_values['%s/line%d' % (port_str, line)] = int(line_final_value)

                con = '%s/%s' % (self.MAX_name, port_str)
                matrix_buffered[num_buffered] = data
                self.DO_task.CreateDOChan(con, "", DAQmx_Val_ChanForAllLines)

                num_buffered += 1

            # lock internal 100MHz clock to external clock at given rate.
            # this must be set also for DO/AO tasks as for the counters, otherwise get an error that resources are already in use.
            # however, for the PXIe-6535 board without counters we cannot set this, otherwise we get another error.
            # we have seen a similar behaviour with C code.
            if (self.clock_terminal is not None) and LOCK_REFCLOCK_AO_DO:
                length = DAQmxGetDevCOPhysicalChans(self.MAX_name, None, 0);
                if length == 0:
                    info = ' (no internal counter)'
                else:
                    self.DO_task.SetRefClkSrc(self.clock_terminal)
                    self.DO_task.SetRefClkRate(self.clock_rate)

            # get counter port
            try:
                counter_port, counter_board = self.counter_ports[self.counter_DO]
            except KeyError:
                raise LabscriptError("DO counter '%s' port found!" % (self.counter_DO))

            # Set up timing:
            self.DO_task.CfgSampClkTiming(
                counter_port.encode('utf-8'),
                self.max_DO_sample_rate,
                DAQmx_Val_Rising,
                DAQmx_Val_FiniteSamps,
                num_samples,
            )

            # Write data. See the comment in self.program_manual as to why we are using
            # uint32 instead of the native size of each port.
            result = self.DO_task.WriteDigitalU32(
                num_samples,
                False,
                TIMEOUT_WRITE,
                DAQmx_Val_GroupByChannel, #DAQmx_Val_GroupByScanNumber,
                np.ascontiguousarray(matrix_buffered), #DO_table,
                written,
                None,
            )
            if (result != 0) or (written.value != num_samples):
                raise LabscriptError("DO write result %i (%i/%i written)!" % (result, num_samples, written.value))

            if CHANNEL_INFO is not None:
                print(CHANNEL_INFO % (self.device_name, '%i buffered DO port'%len(DO_table),
                                      counter_port, counter_board,
                                      num_samples, info))

        return final_values

    def transition_to_buffered(self, device_name, h5file, initial_values, fresh):
        # Store the initial values in case we have to abort and restore them:
        self.initial_values = initial_values
        final_values = {}
        # 'fresh' is True on startup and when user pushes the button 'clear smart-programming cache' but is unrelated to new file.
        update = fresh

        if self.tasks_manual:
            # force update to stop the manual mode tasks
            self.tasks_manual = False
            update = True

        with h5py.File(h5file, 'r') as f:
            # file id used to check if file has been changed
            id = f.attrs['sequence_id'] + ('_%i'%f.attrs['sequence_index']) + ('_%i'%f.attrs['run number'])
            if self.file_id is None or self.file_id != id:
                # new file
                update = True

            # transmit to all boards if need to update.
            # this is needed when one worker was restarted otherwise get PyDAQmx.DAQmxFunctions.RuntimeAborted_RoutingError (-88709).
            # this happens since boards share counters. NIDAQmx gives this error when taskHandle changes although the activity is the same.
            # surprisingly, when programming manual this does not happen although ClearTask is called as well
            # but in this case the new created buffered tasks have the SAME handles as the old and NIDAQmx does not recognize this (looks like a bug?).
            # to be sure we force all boards to update in any case here.
            # on fresh start we sometimes get timeout here. with retry=1 the events are re-created and function tries one more time.
            reset_event_counter = SYNC_RESET_EACH_RUN
            for i in range(2):
                (timeout, board_update, duration) = self.sync_boards(payload=update, reset_event_counter=reset_event_counter)
                if timeout == SYNC_RESULT_OK: break
                elif not SYNC_RESET_EACH_RUN and (i == 0):
                    # first timeout: most likely worker has been restarted.
                    # reset event counter and force update of all boards.
                    print("\ntimeout: restarted board? reset & retry ...\n")
                    reset_event_counter = True
                    update = True
                else:
                    # second timeout: something more serious happenend?
                    print("\ntimeout waiting for board status update!\n")
                    return None # this causes abort_transition_to_buffered which does not require user to restart worker.

            # update if any board needs to update
            print('board update:', board_update)
            for board, _update in board_update.items():
                if _update: update = True
                elif reset_event_counter: # ensure that all boards update after restart
                    print("\n%s %s is not updating after successful restart!?\n" % (self.device_name, board))
                    return None

            if update:
                # clear all old tasks (manual or buffered) otherwise get errors of already used resources.
                self.stop_tasks()
                # get data tables from h5 file.
                # note: this might take several seconds!
                CO_table, AO_table, AO_table_static, DO_table, DO_table_static = self.get_output_tables(f, device_name)
                # save new file id (after stop_tasks which resets id)
                self.file_id = id

        if update:
            print('\n%s reprogram channels:' % device_name)
            # Program static tasks and retrieve the final values
            # note: when programming counters before this get unexpected errors!
            final_values.update(self.program_static_AO(AO_table_static))
            final_values.update(self.program_static_DO(DO_table_static))

            # wait until all static channels are programmed.
            # note: this might timeout when one boards has many data in h5 file to read.
            #       fast boards will timeout here and slow board in next call to sync_board below.
            #       for debugging enable logging.INFO below which prints time
            #       when board starts to wait. increase TIMEOUT_READ_FILE in this case.
            #self.logger.log(logging.INFO, "%s wait evt %i ..." % (self.device_name, self.event_count))
            result = self.sync_boards(payload=device_name, timeout=TIMEOUT_READ_FILE)
            if result[0] != SYNC_RESULT_OK:
                print("\ntimeout waiting to read file & static channels programmed!\n")
                return None
            print(device_name, result)

            # Mirror the clock terminal, if applicable:
            self.set_mirror_clock_terminal_connected(True)

            # Mirror other terminals, if applicable
            self.set_connected_terminals_connected(True)

            # program counter
            self.program_buffered_CO(CO_table)

            # wait until all boards have programmed counters and share counters output ports among boards
            (timeout, board_counters, duration) = self.sync_boards(payload={c:p[0] for c,p in self.counter_ports.items()} if len(self.counter_ports) > 0 else None, timeout=TIMEOUT_WRITE)
            if timeout:
                print("\ntimeout waiting for counter PFI ports or reading file took me too long!\n")
                return None # TODO should cause abort transition to buffered?
            if len(self.counter_ports) < self.counters_used:
                #print('shared couner ports:', board_counters)
                counters = {}
                for board, ctr in board_counters.items():
                    for c,port in ctr.items():
                        if c in counters:
                            print(board_counters)
                            raise LabscriptError("counter '%s' assigned twice!?\nthis is a bug." % (c))
                        counters[c] = (port, board)
                #print(counters)
                for ctr in [self.counter_AO, self.counter_DO]:
                    if ctr is not None:
                        if ctr not in self.counter_ports:
                            self.counter_ports[ctr] = counters[ctr]
                            #print("note: counter '%s' output port '%s' shared from board '%s'" % (ctr, counters[ctr][0], counters[ctr][1]))
                        elif self.counter_ports[ctr][0] != counters[ctr][0]:
                            raise LabscriptError("counter '%s' port has changed from '%s' to '%s'!\nthis should not happen!?" % (ctr, self.counter_ports[ctr], counters[ctrs][0]))

            # Program buffered tasks and retrieve the final values of each output
            final_values.update(self.program_buffered_DO(DO_table))
            final_values.update(self.program_buffered_AO(AO_table))

            #print('final values:', final_values)

            # wait until all boards have programmed output channels
            if self.sync_boards(timeout=TIMEOUT_WRITE)[0] != SYNC_RESULT_OK:
                print("\ntimeout program channels!\n")
                return None
        
        if   self.exp_time >= 1.0: tmp = '%.3f s'  % (self.exp_time)
        elif self.exp_time > 1e-3: tmp = '%.3f ms' % (self.exp_time*1e3)
        elif self.exp_time > 1e-6: tmp = '%.3f us' % (self.exp_time*1e6)
        else:                      tmp = '%.1f ns' % (self.exp_time*1e9)
        print('\nstart experiment: duration', tmp, '(new file)' if update else '(old file)')

        if self.AO_task is not None: self.AO_task.StartTask()
        if self.DO_task is not None: self.DO_task.StartTask()

        self.t_start = get_ticks()
        self.t_last = -2*self.update_time

        # increment run counter
        self.run_count += 1

        # start counters
        # note: if several counters are used an external trigger is needed to synchronize them!
        for task in self.CO_tasks.values():
            task.StartTask()

        return final_values

    def transition_to_manual(self, abort=False):
        # Stop output tasks.
        # Only call StopTask if not aborting.
        # Otherwise results in an error if output was incomplete. If aborting, call
        # ClearTask only.

        # notes:
        # - the order of stopping the tasks is irrelevant.
        # - we do not clear tasks here since with old file can reuse without uploading data
        #   TODO: this is essentially the 'smart programming' feature which could be activated.
        
        npts = uInt64()
        samples = uInt64()
        tasks = []
        for counter, task in self.CO_tasks.items():
            tasks.append([task, False, counter, self.exp_samples_CO[counter]])
        if self.AO_task is not None:
            tasks.append([self.AO_task, False, 'AO', self.exp_samples_AO])
        if self.DO_task is not None:
            tasks.append([self.DO_task, False, 'DO', self.exp_samples_DO])

        # board status error = 0: all is ok, otherwise error code
        error = 0
        for task, static, name, num_samples in tasks:
            if not abort:
                if not static:
                    try:
                        # Wait for task completion
                        task.WaitUntilTaskDone(TIMEOUT_DONE)
                        timeout = False
                    except Exception as e:
                        timeout = True
                    finally:
                        # Log where we were up to in sample generation, regardless of
                        # whether the above succeeded:
                        if self.simulate:
                            current = total = num_samples
                        else:
                            task.GetWriteCurrWritePos(npts)
                            task.GetWriteTotalSampPerChanGenerated(samples)
                            # Detect -1 even though they're supposed to be unsigned ints, -1
                            # seems to indicate the task was not started:
                            current = samples.value if samples.value != 2 ** 64 - 1 else -1
                            total = npts.value if npts.value != 2 ** 64 - 1 else -1
                        ok = (not timeout) and (current == total) and (total == num_samples)
                        if ok:
                            print("run %4i: %s done %i/%i samples (ok)" % (self.run_count, name, current, num_samples))
                        else:
                            if timeout:              error = -1
                            elif (current != total): error = -2
                            else:                    error = -3
                            print("run %4i: %s done %i/%i/%i samples (error %i)" % (self.run_count, name, current, total, num_samples, error))
                task.StopTask()
            #task.ClearTask()

        if len(tasks) == 0:
            print("run %4i: nothing to do" % (self.run_count))

        # Remove the mirroring of the clock terminal, if applicable:
        #self.set_mirror_clock_terminal_connected(False)

        # Remove connections between other terminals, if applicable:
        #self.set_connected_terminals_connected(False)

        if abort:
            self.board_status = {}
        else:
            # wait until all boards have stopped tasks before programming manual tasks
            # return status all_ok to primary board
            (timeout, self.board_status, duration) = self.sync_boards(payload=error)
            if timeout:
                print("\ntimeout stop tasks!\n")
                return False # user has to restart all tabs which is not so nice.

        #if abort:
            # Reprogram the initial states when aborted
            #self.program_manual(self.initial_values) # seems to be called automatically by labscript

        # primary board checks status of secondary boards
        if self.is_primary:
            #print(self.board_status)
            for board, board_error in self.board_status.items():
                if board_error != 0: print('%s status error (%i)' % (board, board_error))
                #else:                print('%s ok' % (board))

        # return True = all ok
        return (error == 0)

    def status_monitor(self, status_end):
        """
        this is called from DeviceTab::status_monitor during run to update status - but of primary board only!
        if status_end = True then this is called from DeviceTab::status_end.
        return True = end or error. False = running.
        when returns True:
        1. transition_to_manual is called for ALL boards where we get self.board_status of all boards.
        2. status_monitor is called again with status_end=True for primary board only
           and worker should return self.board_status with key = board name. value = error code. 0 = ok.
        """
        run_time = get_ticks() - self.t_start
        if self.simulate:
            # simulate end with computer clock
            end = (run_time >= self.exp_time)
        elif len(self.CO_tasks) == 0:
            # primary board has no counters: just wait exp_time
            end = (run_time >= self.exp_time)
        else:
            # wait until all counter tasks are done
            end = True
            for task in self.CO_tasks.values():
                is_done = np.array((1,),dtype=int)
                task.IsTaskDone(is_done.ctypes.data_as(POINTER(c_ulong)))
                if not is_done:
                    end = False
        if end:
            # all tasks finished
            if status_end:
                # called after transition_to_manual for status check
                # return error code of all boards. 0 = ok, {} = aborted
                print(self.device_name, 'status monitor %.1f s (end - manual)' % run_time)
                if len(self.board_status) == 0:
                    print('board status: ABORTED!')
                else:
                    print('board status:', self.board_status)
                end = self.board_status
            else:
                # called during buffered modue and end detected
                # return True = end
                print(self.device_name, 'status monitor %.1f s (end)' % run_time)
        elif (run_time - self.t_last) >= self.update_time:
            # running: return False
            self.t_last = run_time
            if status_end: # not sure if this can happen?
                end = self.board_status
                print(self.device_name, 'status monitor %.1f s (aborted)' % run_time)
            else:
                print(self.device_name, 'status monitor %.1f s (running)' % run_time)
        return end

    def restart(self):
        # restart tab only. return True = restart, False = do not restart.
        print(self.device_name, 'restart')
        self.stop_tasks()
        time.sleep(0.5)
        return True

    def shutdown(self):
        # shutdown blacs
        print(self.device_name, 'shutdown')
        self.stop_tasks()
        time.sleep(0.5)
