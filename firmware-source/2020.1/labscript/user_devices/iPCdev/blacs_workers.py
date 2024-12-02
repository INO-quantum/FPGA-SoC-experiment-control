# internal pseudoclock device
# created April 2024 by Andi
# last change 14/6/2024 by Andi

import numpy as np
import labscript_utils.h5_lock
import h5py
from zprocess import Event
from zprocess.utils import _reraise

from labscript import LabscriptError
from labscript_utils import import_or_reload
from blacs.tab_base_classes import Worker

import logging
from .labscript_devices import (
    log_level,
    DEVICE_INFO_PATH, DEVICE_TIME, DEVICE_HARDWARE_INFO, DEVICE_INFO_ADDRESS, DEVICE_INFO_TYPE, DEVICE_INFO_BOARD,
    DEVICE_DATA_AO, DEVICE_DATA_DO, DEVICE_DATA_DDS,
    HARDWARE_TYPE, HARDWARE_SUBTYPE,
    HARDWARE_TYPE_AO, HARDWARE_TYPE_DO, HARDWARE_TYPE_DDS,
    HARDWARE_SUBTYPE_STATIC, HARDWARE_SUBTYPE_TRIGGER,
)
from .blacs_tabs import DDS_CHANNEL_PROP_FREQ, DDS_CHANNEL_PROP_AMP, DDS_CHANNEL_PROP_PHASE

from time import sleep

# for testing
#from user_devices.h5_file_parser import read_group

# optional worker_args
ARG_SIM  = 'simulate'
ARG_SYNC = 'sync_boards'

# default update time interval in seconds when status monitor shows actual status
UPDATE_TIME                     = 1.0

# default timeout in seconds for sync_boards
SYNC_TIMEOUT                    = 1.0

# if True reset sync counter each run.
# TODO: False case is tested quite a lot and seems to work (although maybe in very rare cases could still cause timeout).
#       True case is not much tested. this was original approach but did not worked due to subtle timing problems.
#       these problems were debugged and hopefully all fixed and now also this case should work again.
#       the problems mainly occur when restarting boards, after compilation or start of blacs, but only in rare cases.
#       so its not so easy to detect if it is working now or not.
SYNC_RESET_EACH_RUN             = True

# time margin for sync_boards with reset_event_counter=True
# this is not used with SYNC_RESET_EACH_RUN
SYNC_TIME_MARGIN                = 0.2

# events
EVENT_TO_PRIMARY                = '%s_to_prim'
EVENT_FROM_PRIMARY              = '%s_from_prim'
EVENT_TIMEOUT                   = 'timeout!'
EVENT_COUNT_INITIAL             = 0

# return code from sync_boards
SYNC_RESULT_OK                  = 0     # ok
SYNC_RESULT_TIMEOUT             = 1     # connection timeout
SYNC_RESULT_TIMEOUT_OTHER       = 2     # timeout on another board

# scale DDS channel analog values from hd5 file to displayed values of channels
DDS_CHANNEL_SCALING = {DDS_CHANNEL_PROP_FREQ: 1e-6, DDS_CHANNEL_PROP_AMP: 1.0, DDS_CHANNEL_PROP_PHASE: 1.0}

class iPCdev_worker(Worker):

    # synchronization options. overwrite in derived class
    sync_reset_each_run = SYNC_RESET_EACH_RUN
    sync_time_margin    = SYNC_TIME_MARGIN

    def init(self):
        global zTimeoutError; from zprocess.utils import TimeoutError as zTimeoutError
        global get_ticks; from time import perf_counter as get_ticks
        global get_ticks; from time import sleep

        # reduce number of log entries in logfile (labscript-suite/logs/BLACS.log)
        self.logger.setLevel(log_level)
        #self.logger.setLevel(logging.INFO)

        # check worker arguments for options
        options = []
        self.worker_args = self.properties['worker_args']
        if self.worker_args is not None:
            # simulate device
            try:
                self.simulate = self.worker_args[ARG_SIM]
                if self.simulate: options.append('simulate')
            except KeyError:
                self.simulate = False
            # synchronize boards
            try:
                self.sync = self.worker_args[ARG_SYNC]
                if self.sync: options.append('synchronize boards')
            except KeyError:
                self.sync = False
        if len(options) > 0: options = '(%s)'%(', '.join(options))
        else:                options = ''

        if self.is_primary:
            print(self.device_name, '(primary) init %s' % options)
            print('%i secondary boards:' % (len(self.boards)), self.boards)
        else:
            print(self.device_name, '(secondary) init %s' % options)
            print('primary board:', self.boards[0])

        if False: # print worker args
            print(self.device_name, 'worker args:', self.worker_args)

        # below we call static method extract_channel_data in a possibly derived class of iPCdev
        # dynamically load module and get the class object.
        # TODO: not sure if this will work under all conditions? esp. importing modules in python is not robust.
        self.derived_module = self.properties['derived_module']
        device_module = import_or_reload(self.derived_module)
        self.device_class_object = getattr(device_module, self.device_class)
        if False: # print module and class information
            print('derived module:', self.derived_module)
            print('device class:', self.device_class)

        if self.properties['shared_clocklines']:
            # when shared_clocklines = True then self.clocklines contains the clockline names of this board.
            print('%s has %i channels, %i clocklines (shared)' % (self.device_name, len(self.channels), len(self.clocklines)))
        else:
            print('%s has %i channels' % (self.device_name, len(self.channels)))

        if not hasattr(self, 'update_time'):
            self.update_time = UPDATE_TIME

        # file id used to determine if file has changed or not
        self.file_id = None

        # experiment time in seconds and number of channels for different output types
        self.exp_time = 0
        self.num_channels = {}

        # prepare zprocess events for communication between primary and secondary boards
        # primary board: boards/events = list of all secondary board names/events
        # secondary board: boards/events = list containing only primary board name/event
        self.create_events()

    def create_events(self):
        if self.is_primary:
            self.events_wait = [self.process_tree.event(EVENT_TO_PRIMARY % self.device_name, role='wait')]
            self.events_post = [self.process_tree.event(EVENT_FROM_PRIMARY % s, role='post') for s in self.boards]
        else:
            self.events_post = [self.process_tree.event(EVENT_TO_PRIMARY % self.boards[0], role='post')]
            self.events_wait = [self.process_tree.event(EVENT_FROM_PRIMARY % self.device_name, role='wait')]
        self.event_count = EVENT_COUNT_INITIAL

    def sync_boards(self, payload=None, timeout=SYNC_TIMEOUT, reset_event_counter=False):
        # synchronize multiple boards
        # payload = data to be distributed to all boards.
        # timeout = timeout time in seconds
        # reset_event_counter = if True resets event counter before waiting.
        # 1. primary board waits for events of all secondary boards and then sends event back.
        # 2. each secondary board sends event to primary board and waits for primary event.
        # primary collects dictionary {board_name:payload} for all boards and sends back to all boards.
        # this allows to share data among boards.
        # returns (status, result, duration)
        # status   = SYNC_RESULT_OK if all ok
        #            SYNC_RESULT_TIMEOUT if connection timeout
        #            SYNC_RESULT_TIMEOUT_OTHER if connection to any other board timeout
        # result   = if not None dictionary with key = board name, value = payload
        # duration = total time in ms the worker spent in sync_boards function
        # timeout behaviour:
        # since each board can be reset by user self.event_count might get out of sync with other boards.
        # this will cause timeout on all boards - event the ones which are still synchronized!
        # this is by purpose to ensure all boards have the same waiting times.
        # on timeout each worker should call sync_boards again with reset_event_counter=True
        # this allows to re-synchronize all boards and continue without restarting of blacs.
        # notes:
        # - in rare cases this was not working since the primary can by chance still wait for timeout,
        #   while any secondary is already timeout and calls sync_boards again but with reset self.event_count.
        #   in this case the primary might discard the new event since it still waits for the old event.
        #   when it then resets it will timeout because the new event was already discarded.
        #   to avoid this issue on reset_event_counter the secondary boards wait SYNC_TIME_MARGIN time
        #   before sending the reset events and the primary should be reset and waiting for the new event.
        # TODO:
        # - test this option again: use reset_event_counter=True in each loop and set SYNC_TIME_MARGIN=0
        #   this was essentially the first configuration I tested but due to further bugs was not working.
        #   possibly this works now again and does not need the retry option.
        t_start = get_ticks()
        if reset_event_counter: self.event_count = EVENT_COUNT_INITIAL
        sync_result = SYNC_RESULT_OK
        if self.is_primary:
            # 1. primary board: first wait then send
            if not iPCdev_worker.sync_reset_each_run and reset_event_counter:
                # compensate the additional waiting time of secondary boards
                timeout += iPCdev_worker.sync_time_margin
            result = {} if payload is None else {self.device_name:payload}
            event = self.events_wait[0]
            #sleep(0.1) # this triggers 100% the timeout event! when restarting both secondary boards!
            for i in range(len(self.boards)):
                is_timeout = False
                try:
                    _t_start = get_ticks()
                    #self.logger.log(logging.INFO, "%s (pri) wait evt %i (#%i) ..." % (self.device_name, self.event_count, i))
                    _result = event.wait(self.event_count, timeout=timeout/len(self.boards))
                    if _result is not None: result.update(_result)
                except zTimeoutError:
                    is_timeout = True
                    sync_result = SYNC_RESULT_TIMEOUT
                    result[self.boards[i]] = EVENT_TIMEOUT
                #self.logger.log(logging.WARNING if is_timeout else logging.INFO, "%s (pri) wait evt %i (#%i) %.3fms: %s" % (self.device_name, self.event_count, i, (get_ticks() - _t_start) * 1e3, 'timeout!' if is_timeout else str(_result)))
            if sync_result == SYNC_RESULT_OK:
                for event in self.events_post:
                    event.post(self.event_count, data=None if len(result) == 0 else result)
            else:
                # on timeout we have to ensure that primary board waits the same time as secondary boards,
                # otherwise primary board resets and starts waiting too early while other boards are still waiting for first event.
                remaining = timeout - (get_ticks() - t_start)
                if remaining > 0:
                    #self.logger.log(logging.INFO,"%s (pri) wait remaining %.3fms ..." % (self.device_name, remaining * 1e3))
                    sleep(remaining)
            # return total duration in ms
            duration = (get_ticks() - t_start) * 1e3
        else:
            # 2. secondary board: first send then wait
            if not iPCdev_worker.sync_reset_each_run and reset_event_counter:
                # ensure primary is reset before sending the reset event id
                sleep(iPCdev_worker.sync_time_margin)
            self.events_post[0].post(self.event_count, data={self.device_name:payload})
            is_timeout = False
            try:
                #self.logger.log(logging.INFO, "%s (sec) wait evt %i ..." % (self.device_name, self.event_count))
                result = self.events_wait[0].wait(self.event_count, timeout=timeout)
                if (result is not None) and (sync_result == SYNC_RESULT_OK):
                    for board, _result in result.items():
                        if isinstance(_result, str) and _result == EVENT_TIMEOUT:
                            sync_result = SYNC_RESULT_TIMEOUT_OTHER
                            break
            except zTimeoutError:
                is_timeout = True
                sync_result = SYNC_RESULT_TIMEOUT
                result = None
            duration = (get_ticks() - t_start) * 1e3
            #self.logger.log(logging.WARNING if is_timeout else logging.INFO, "%s (sec) wait evt %i %.3fms: %s" % (self.device_name, self.event_count, duration, 'timeout!' if is_timeout else 'ok'))
        self.event_count += 1

        return (sync_result, result, duration)

    def program_manual(self, front_panel_values):
        print(self.device_name, 'program manual')
        return {}

    def transition_to_buffered(self, device_name, h5file, initial_values, fresh):
        # this is called for all iPCdev devices
        # return None on error, dictionary of final values for each channel otherwise
        print(self.device_name, 'transition to buffered')
        #print('initial values:', initial_values)
        final_values = {}
        update = fresh # requires supports_smart_programming=True and fresh=True when 'clear smart-programming cache' symbol clicked

        with h5py.File(h5file,'r') as f:
            # file id used to check if file has been changed
            id = f.attrs['sequence_id'] + ('_%i' % f.attrs['sequence_index']) + ('_%i' % f.attrs['run number'])
            if update or (self.file_id is None) or (self.file_id != id):
                # new file
                self.file_id = id
                self.exp_time = 0
                self.num_channels = {}
                update = True

                # load data tables for all output channels
                for connection, device in self.channels.items():
                    hardware_info    = device.properties[DEVICE_HARDWARE_INFO]
                    hardware_type    = hardware_info[DEVICE_INFO_TYPE][HARDWARE_TYPE]
                    hardware_subtype = hardware_info[DEVICE_INFO_TYPE][HARDWARE_SUBTYPE]
                    group = f[hardware_info[DEVICE_INFO_PATH]]
                    times = group[DEVICE_TIME][()]
                    static = False
                    if hardware_type == HARDWARE_TYPE_AO:
                        devices = [(device.name, DEVICE_DATA_AO % (device.name, hardware_info[DEVICE_INFO_ADDRESS]),device.parent_port, 'AO', None)]
                        if hardware_subtype == HARDWARE_SUBTYPE_STATIC:
                            static = True
                    elif (hardware_type == HARDWARE_TYPE_DO): # note: this includes trigger devices as well
                        devices = [(device.name, DEVICE_DATA_DO % (hardware_info[DEVICE_INFO_BOARD], hardware_info[DEVICE_INFO_ADDRESS]), device.parent_port, 'DO', None)]
                        if hardware_subtype == HARDWARE_SUBTYPE_STATIC:
                            static = True
                    elif hardware_type == HARDWARE_TYPE_DDS:
                        if hardware_subtype == HARDWARE_SUBTYPE_STATIC:
                            static = True
                        devices = [(channel.name, DEVICE_DATA_DDS % (device.name, hardware_info[DEVICE_INFO_ADDRESS], channel.parent_port), channel.parent_port, None, DDS_CHANNEL_SCALING[channel.parent_port]) for channel in device.child_list.values()]
                    else:
                        print("warning: device %s unknown type %s (skip)" % (device.name, hardware_type))
                        continue
                    final = {}
                    for (name, dataset, port, type, scaling) in devices:
                        data = group[dataset][()]
                        if data is None:
                            raise LabscriptError("device %s: dataset %s not existing!" % (name, dataset))
                        elif static and ((len(times) != 2) or (len(data) != 1)):
                            raise LabscriptError("static device %s: %i/%i times/data instead of 2/1!" % (name, len(times), len(data)))
                        elif not static and (len(times) != len(data)):
                            raise LabscriptError("device %s: %i times but %i data!" % (name, len(times), len(data)))
                        if times[-1] > self.exp_time: self.exp_time = times[-1]
                        channel_data = self.device_class_object.extract_channel_data(hardware_info, data)
                        if scaling is not None:
                            final[port] = channel_data[-1]*scaling
                        else:
                            final[port] = channel_data[-1]
                        # save number of used channels per type of port.
                        if (type is not None) and (len(channel_data) > 2):
                            changes = ((channel_data[1:].astype(int) - channel_data[:-1].astype(int)) != 0)
                            if np.any(changes):
                                try:
                                    self.num_channels[type] += 1
                                except KeyError:
                                    self.num_channels[type] = 1

                    if len(devices) == 1: final_values[connection] = final[device.parent_port]
                    else:                 final_values[connection] = final

                print('final values:', final_values)

        if   self.exp_time >= 1.0: tmp = '%.3f s'  % (self.exp_time)
        elif self.exp_time > 1e-3: tmp = '%.3f ms' % (self.exp_time*1e3)
        elif self.exp_time > 1e-6: tmp = '%.3f us' % (self.exp_time*1e6)
        else:                      tmp = '%.1f ns' % (self.exp_time*1e9)
        print('\n%s start experiment: duration %s %s' % (self.device_name, tmp, '(old file)' if not update else '(new file)'))

        #print('final values:', final_values)

        if self.sync:
            # synchronize boards and get experiment time for all of them
            # note: this option is for demonstration and not needed for functionality.
            #       but some boards, like NI-DAQmx, require synchronization when hardware is shared.
            #       if a board is restarted we will get timeout but we can restart all boards and try again.
            count = 0
            payload = np.round(self.exp_time,6)
            (timeout, board_times, duration) = self.sync_boards(payload=payload, reset_event_counter=SYNC_RESET_EACH_RUN)
            while timeout != SYNC_RESULT_OK:
                if timeout == SYNC_RESULT_TIMEOUT:         tmp = ''
                elif timeout == SYNC_RESULT_TIMEOUT_OTHER: tmp = '(other) '
                else:                                      tmp = '(unknown) '
                if not iPCdev_worker.sync_reset_each_run and (count < 1):
                    print("\ntimeout %ssync with all boards! (%.3fms, reset & retry)\n" % (tmp, duration))
                    (timeout, board_times, duration) = self.sync_boards(payload=payload, reset_event_counter=True)
                else:
                    print("\ntimeout %ssync with all boards! (%.3fms, abort)\n" % (tmp, duration))
                    return None
                count += 1
            print('board times (%.3fms):'%duration, board_times)

            if True:
                # we set experiment time to largest of all boards
                for board, exp_time in board_times.items():
                    if exp_time > self.exp_time:
                        print('%s update duration from board %s to %.3e s' % (self.device_name, board,exp_time))
                        self.exp_time = exp_time

        # manually call start_run from here
        self.start_run()

        return final_values

    def transition_to_manual(self, abort=False):
        # this is called for all iPCdev devices
        print(self.device_name, 'transition to manual')

        error = 0

        if abort:
            self.board_status = {}
            print('board status: ABORTED!')
        else:
            # get number of samples
            tmp = []
            for name, samples in self.num_channels.items():
                tmp += ['%s: %i' % (name, samples)]
            if len(tmp) > 0: print("%s done, active channels: %s (ok)" % (self.device_name, ', '.join(tmp)))
            else:            print("%s done, no active channels (ok)" % (self.device_name))

            if self.sync:
                # get status (error) of all boards
                (timeout, self.board_status, duration) = self.sync_boards(payload=error)
                if timeout == SYNC_RESULT_OK:
                    print('board status (%.3fms):'%duration, self.board_status)
                else:
                    if   timeout == SYNC_RESULT_TIMEOUT:       tmp = ''
                    elif timeout == SYNC_RESULT_TIMEOUT_OTHER: tmp = '(other) '
                    else:                                      tmp = '(unknown) '
                    print("\ntimeout %sget status of all boards! (%.3fms)\n" % (tmp, duration))
                    return True
                print('board status (%.3fms):'%duration, self.board_status)
            else:
                self.board_status = {self.device_name: error}

        # return True = all ok
        return (error == 0)

    def abort_transition_to_buffered(self):
        print(self.device_name, 'transition to buffered abort')
        return self.transition_to_manual(abort=True)

    def abort_buffered(self):
        print(self.device_name, 'buffered abort')
        return self.transition_to_manual(abort=True)

    def start_run(self):
        # note: this is called manually from transition_to_buffered for all iPCdev devices
        #       since iPCdev_tab::start_run is called only for primary pseudoclock device!
        #print(self.device_name, 'start run')
        self.t_start = get_ticks()
        self.t_last  = -2*self.update_time

        # return True = ok
        return True

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
        end = False
        run_time = get_ticks() - self.t_start
        if self.simulate:
            end = (run_time >= self.exp_time)
        else:
            # TODO: implement for your device!
            end = (run_time >= self.exp_time)

        if end:
            if status_end:
                print(self.device_name, 'status monitor %.1f s (end - manual)' % run_time)
                end = self.board_status
            else:
                print(self.device_name, 'status monitor %.1f s (end)' % run_time)
        elif (run_time - self.t_last) >= self.update_time:
            self.t_last = run_time
            if status_end:
                print(self.device_name, 'status monitor %.1f s (aborted)' % run_time)
                end = self.board_status
            else:
                print(self.device_name, 'status monitor %.1f s (running)' % run_time)
        return end

    def restart(self):
        # restart tab only. return True = restart, False = do not restart.
        print(self.device_name, 'restart')
        # TODO: cleanup resources here
        # short sleep to allow user to read that we have cleaned up.
        sleep(0.5)
        return True

    def shutdown(self):
        # shutdown blacs
        print(self.device_name, 'shutdown')
        # TODO: cleanup resources here...
        # short sleep to allow user to read that we have cleaned up.
        sleep(0.5)
        pass
    
