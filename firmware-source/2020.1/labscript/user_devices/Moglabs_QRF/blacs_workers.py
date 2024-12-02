# Moglabs QRF 
# created 29/5/2024 by Andi
# modified from:
# https://github.com/specialforcea/labscript_suite/blob/a4ad5255207cced671990fff94647b1625aa0049/labscript_devices/MOGLabs_XRF021.py
# requires mogdevice.py, see: https://pypi.org/project/mogdevice/
# last change 29/5/2024 by Andi 

import numpy as np
from time import sleep

import labscript_utils.h5_lock
import h5py
from labscript import LabscriptError

from user_devices.iPCdev.labscript_devices import (
    iPCdev,
    DEVICE_HARDWARE_INFO, DEVICE_INFO_TYPE, DEVICE_INFO_ADDRESS, DEVICE_INFO_CHANNEL, DEVICE_INFO_PATH,
    DEVICE_DATA_DDS, DEVICE_TIME,
    HARDWARE_TYPE, HARDWARE_TYPE_DDS,
)
from user_devices.iPCdev.blacs_tabs import (
    DDS_CHANNEL_PROP_FREQ, DDS_CHANNEL_PROP_AMP, DDS_CHANNEL_PROP_PHASE,
)
from user_devices.iPCdev.blacs_workers import (
    iPCdev_worker, SYNC_RESULT_OK, SYNC_RESULT_TIMEOUT, SYNC_RESULT_TIMEOUT_OTHER, SYNC_RESET_EACH_RUN,
)

from .labscript_devices import (
    MAX_NUM_CHANNELS, DDS_CHANNEL_PROP_MODE,
    MODES, MODE_BASIC, MODE_TABLE_TRIGGERED, MODE_TABLE_TIMED, MODE_TABLE_TIMED_SW,
    RESOLUTION_TABLE_MODE
)

# scale DDS channel analog values from hd5 file to displayed values of channels
DDS_CHANNEL_SCALING = {DDS_CHANNEL_PROP_FREQ: 1e-6, DDS_CHANNEL_PROP_AMP: 1.0, DDS_CHANNEL_PROP_PHASE: 1.0}

# display status information only every UPDATE_TIME seconds
UPDATE_TIME         = 1.0

# Moglabs commands and responds
MOGCMD_OK                   = 'OK'
MOGCMD_ERR                  = 'ERR'
MOGCMD_MODE_BASIC           = 'MODE,%i,NSB'
MOGCMD_MODE_TABLE           = 'MODE,%i,TSB'
MOGCMD_GET_FREQ             = 'FREQ,%i'
MOGCMD_SET_FREQ             = 'FREQ,%i,%fMHz'
MOGCMD_GET_AMP              = 'POW,%i'
MOGCMD_SET_AMP              = 'POW,%i,%fdBm'
MOGCMD_GET_PHASE            = 'PHASE,%i'
MOGCMD_SET_PHASE            = 'PHASE,%i,%fdeg'
MOGCMD_ALL_ON               = 'ON,%i,ALL'
MOGCMD_ALL_OFF              = 'OFF,%i,ALL'
MOGCMD_SIG_ON               = 'ON,%i,SIG'
MOGCMD_SIG_OFF              = 'OFF,%i,SIG'
MOGCMD_PWR_ON               = 'ON,%i,POW'
MOGCMD_PWR_OFF              = 'OFF,%i,POW'
MOGCMD_TABLE_CLEAR          = 'TABLE,CLEAR,%i'
MOGCMD_TABLE_EDGE_RISING    = 'TABLE,EDGE,%i,RISING'
MOGCMD_TABLE_APPEND         = 'TABLE,APPEND,%i,%i,%.3f,%.3f,%i'
MOGCMD_TABLE_APPEND_OFF     = 'TABLE,APPEND,%i,10,0x0,0,%i'
MOGCMD_TABLE_ENTRIES        = 'TABLE,ENTRIES,%i,%i'
MOGCMD_TABLE_ARM            = 'TABLE,ARM,%i'
MOGCMD_TABLE_STOP           = 'TABLE,STOP,%i'

class MOGDevice_sim(object):
    """
    simulated MOGdevice.
    TODO: not sure on responds and implemented only functions used here.
    """
    def __init__(self):
        pass
    def cmd(self, cmd):
        return MOGCMD_OK
    def ask(self, cmd):
        if cmd == 'info': return 'MOGdevice (simulated)'
        else: raise LabscriptError('MOGdevice ask %s not implemented in simulation!' % (cmd))
    def flush(self):
        return MOGCMD_OK
    def close(self):
        pass

class QRF_worker(iPCdev_worker):
    def init(self):
        global zTimeoutError; from zprocess.utils import TimeoutError as zTimeoutError
        global get_ticks; from time import perf_counter as get_ticks

        # if address is None simulate device
        if self.addr is None:
            self.properties['worker_args'].update({'simulate':True})

        super(QRF_worker, self).init()

        # remove virtual channel from self.channels.
        # this is only existing when there is no other master pseudoclock device in the system.
        channels = {}
        self.final_values   = {}
        for connection, channel in self.channels.items():
            hardware_info = channel.properties[DEVICE_HARDWARE_INFO]
            if (hardware_info[DEVICE_INFO_TYPE][HARDWARE_TYPE] == HARDWARE_TYPE_DDS): # and (channel.device_class == 'QRF_DDS'):
                # get mode of channel
                mode_name = channel.properties[DDS_CHANNEL_PROP_MODE]
                mode = MODES[mode_name]
                print('%s: %s (%s)' % (channel.name, connection, mode_name))
                channels[connection] = channel
                # get actual output value for each sub-channel
                act = {}
                for con, sub in channel.child_list.items():
                    act[con] = 0 #sub.output_value
                self.final_values[connection] = act
        self.channels = channels

        # synchronization


        # last experiment data
        self.file_id        = id
        self.exp_time       = 0.0
        self.table_basic    = {}
        self.table_timed    = {}
        self.table_trig     = {}

        # board status after experiment
        self.board_status   = {}

        # open device
        if self.connect('init'):
            info = self.dev.ask('info')
            print('MOGlabs info:', info)

            # flush any junk from the buffer
            self.dev.flush()

            # switch all outputs off
            for channel in range(1, MAX_NUM_CHANNELS + 1):
                self.dev.cmd(MOGCMD_ALL_OFF % channel)

            # get actual output values
            #self.check_remote_values()

    def connect(self, name):
        # connect to device. returns True on success, otherwise False.
        # check if self.dev is None if device is connected or not and call this again.
        if self.simulate:
            # use simulated device
            self.dev = MOGDevice_sim()
            return True
        else:
            # TODO: not tested so far
            try:
                from mogdevice import MOGDevice
                self.dev = MOGDevice(self.addr, self.port)
            except Exception: # on Linux gives OSError, on Windows dont know
                self.dev = None
                #print('%s: no connection.' % (name))
                return False
            self.dev.flush()
            return True

    # switch RF signal on/off. returns True if ok, False on error.
    # note: if state = False we switch signal AND RF amplifier off!
    def onSignal(self, channel, state):
        cmd = 'ON' if state else 'OFF'
        info = "'%s' channel %i: RF signal %s" % (self.device_name, channel, cmd)
        if self.dev is not None:
            if state: self.dev.cmd(MOGCMD_SIG_ON % channel)
            else:     self.dev.cmd(MOGCMD_ALL_OFF % channel) # see note
            print(info)
            return True
        print(info + ' failed!')
        return False

    # switch RF amplifier on/off. returns True if ok, False on error.
    # note: if state = True we switch signal AND RF amplifier on!
    def onAmp(self, channel, state):
        cmd = 'ON' if state else 'OFF'
        info = "'%s' channel %i: RF amplifier %s" % (self.device_name, channel, cmd)
        if self.dev is not None:
            if state: self.dev.cmd(MOGCMD_ALL_ON % channel) # see note
            else:     self.dev.cmd(MOGCMD_PWR_OFF % channel)
            print(info)
            return True
        print(info + ' failed!')
        return False

    # switch RF signal & amplifier on/off. returns True if ok, False on error.
    def onBoth(self, channel, state):
        cmd = 'ON' if state else 'OFF'
        info = "'%s' channel %i: RF signal & amplifier %s" % (self.device_name, channel, cmd)
        if self.dev is not None:
            if state: 
                result = self.dev.cmd(MOGCMD_ALL_ON % channel)
            else:     
                result = self.dev.cmd(MOGCMD_ALL_OFF % channel)
            return (result == MOGCMD_OK)
        print(info + ' failed!')
        return False

    def check_remote_values(self):
        # called by labscript when supports_remote_value_check(True)
        # return dictionary of actual value for each channel (connection, not name)
        # for DDS we must give for each connection a dictionary of sub-channels with keys = DDS_CHANNEL_PROP_...

        if self.simulate:
            # return actual front panel values
            return self.final_values
        
        # if not connected try to connect. return None on failure.
        if (self.dev is None) and not self.connect('check_remote_values'):
            return None # TODO: test this
        
        # get the current output values and save as last values:
        self.final_values = {}
        for i in range(1, MAX_NUM_CHANNELS + 1):
            freq  = float(self.dev.ask(MOGCMD_GET_FREQ  % i).split()[0])
            amp   = float(self.dev.ask(MOGCMD_GET_AMP   % i).split()[0])
            phase = float(self.dev.ask(MOGCMD_GET_PHASE % i).split()[0])
            self.final_values['channel %d' % i] = {DDS_CHANNEL_PROP_FREQ : freq,
                                                   DDS_CHANNEL_PROP_AMP  : amp,
                                                   DDS_CHANNEL_PROP_PHASE: phase}
        # print(self.final_values)
        return self.final_values

    def program_manual(self, front_panel_values):
        # user changed a front panel value
        print(self.device_name, 'program manual:', front_panel_values)

        # if not connected try to connect. return on failure.
        if (not self.simulate) and (self.dev is None) and (not self.connect('program_manual')):
            return

        for connection, new_values in self.final_values.items():
            old_values = self.final_values[connection]
            for channel, new_value in new_values.items():
                if new_value != old_values[channel]:
                    if channel == DDS_CHANNEL_PROP_FREQ:
                        self.dev.cmd(MOGCMD_SET_FREQ % (i, new_value))
                    elif channel == DDS_CHANNEL_PROP_AMP:
                        self.dev.cmd(MOGCMD_SET_AMP % (i, new_value))
                    elif channel == DDS_CHANNEL_PROP_PHASE:
                        self.dev.cmd(MOGCMD_SET_PHASE % (i, new_value))
                    else:
                        raise LabscriptError("DDS '%s' has no channel '%s'!" % (connection, channel))

        # save new front panel values and return them
        self.final_values = front_panel_values

        return front_panel_values

    def transition_to_buffered(self, device_name, h5file, initial_values, fresh):

        # load data from h5 file when needed
        # file id is used to check if file has been changed (update = True) or not (update = False)
        update = fresh
        with h5py.File(h5file,'r') as f:
            id = f.attrs['sequence_id'] + ('_%i' % f.attrs['sequence_index']) + ('_%i' % f.attrs['run number'])
            if update or (self.file_id is None) or (self.file_id != id):
                # new file
                update              = True
                self.file_id        = id
                self.exp_time       = 0.0
                self.final_values   = {}
                self.table_basic    = {}
                self.table_timed    = {}
                self.table_trig     = {}

                # load data tables for all DDS channels
                for connection, device in self.channels.items():
                    hardware_info = device.properties[DEVICE_HARDWARE_INFO]
                    channel_index = hardware_info[DEVICE_INFO_CHANNEL]
                    mode_name = device.properties[DDS_CHANNEL_PROP_MODE]
                    mode = MODES[mode_name]
                    group = f[hardware_info[DEVICE_INFO_PATH]]
                    times = group[DEVICE_TIME][()]
                    if times[-1] > self.exp_time: self.exp_time = times[-1]
                    print('%s (%s): %i times' % (device.name, mode_name, len(times)))
                    final = {}
                    dds_data  = {}
                    for channel in device.child_list.values():
                        dataset = DEVICE_DATA_DDS % (device.name, hardware_info[DEVICE_INFO_ADDRESS], channel.parent_port)
                        data = group[dataset][()]
                        if data is None:
                            raise LabscriptError("device %s: dataset %s not existing!" % (channel.name, dataset))
                        if mode == MODE_BASIC:
                            if (len(times) > 2) or (len(data) > 2): # basic mode allows only programming once!
                                raise LabscriptError('%s in mode %s cannot be programmed during runtime!' % (device.name, mode_name))
                        elif (len(times) != len(data)):
                            raise LabscriptError("device %s: %i times but %i data!" % (channel.name, len(times), len(data)))
                        channel_data = iPCdev.extract_channel_data(hardware_info, data)
                        scaling = DDS_CHANNEL_SCALING[channel.parent_port]
                        dds_data[channel.parent_port] = channel_data * scaling
                        final[channel.parent_port]    = channel_data[-1] * scaling
                    self.final_values[connection] = final
                    # save data and times for each channel
                    # the channels indices are 1..4
                    if mode == MODE_BASIC:
                        self.table_basic[channel_index] = dds_data
                    elif mode == MODE_TABLE_TIMED:
                        self.table_timed[channel_index] = (times, dds_data)
                    elif mode == MODE_TABLE_TIMED_SW:
                        self.table_timed[channel_index] = (times, dds_data)
                    elif mode == MODE_TABLE_TRIGGERED:
                        self.table_trig[channel_index] = dds_data
                    else:
                        raise LabscriptError("dds '%s' channel %i mode '%s' unknown!" % (device_name, channel_index, mode_name))

                print('final values:', self.final_values)

        # experiment time
        if   self.exp_time >= 1.0:  tm = '%.3f s'  % (self.exp_time)
        elif self.exp_time > 1e-3:  tm = '%.3f ms' % (self.exp_time * 1e3)
        elif self.exp_time > 1e-6:  tm = '%.3f us' % (self.exp_time * 1e6)
        else:                       tm = '%.1f ns' % (self.exp_time * 1e9)

        # channel information
        tmp = []
        if len(self.table_basic) > 0: tmp += ['%i basic'                  % len(self.table_basic)]
        if len(self.table_timed) > 0: tmp += ['%i table mode (timed)'     % len(self.table_timed)]
        if len(self.table_trig ) > 0: tmp += ['%i table mode (triggered)' % len(self.table_trig)]
        num_channels = len(self.table_basic) + len(self.table_timed) + len(self.table_trig)
        ch_info = ('%i channels: ' % (num_channels)) + ', '.join(tmp)

        if self.simulate:
            print('\n%s start experiment. %s, duration %s %s' % (self.device_name, ch_info, tm, '(old file - simulate)' if not update else '(new file - simulate)'))
        else:
            print('\n%s start experiment. %s, duration %s %s' % (self.device_name, ch_info, tm, '(old file)' if not update else '(new file)'))

        # if we are not connected try to connect. return on failure.
        if (not self.simulate) and (self.dev is None) and (not self.connect('check_remote_values')):
            return None # error

        # program basic mode channels immediately and switch RF on
        for channel_index, data in self.table_basic.items():
            self.dev.cmd(MOGCMD_MODE_BASIC % channel_index)
            self.dev.cmd(MOGCMD_SET_FREQ  % (channel_index, data[DDS_CHANNEL_PROP_FREQ][0]))
            self.dev.cmd(MOGCMD_SET_AMP   % (channel_index, data[DDS_CHANNEL_PROP_AMP][0]))
            self.dev.cmd(MOGCMD_SET_PHASE % (channel_index, data[DDS_CHANNEL_PROP_PHASE][0]))
            self.dev.cmd(MOGCMD_ALL_ON % channel_index)

        # table mode with internal timing
        for channel_index, (times, data) in self.table_timed.items():
            self.dev.cmd(MOGCMD_MODE_TABLE % channel_index)
            self.dev.cmd(MOGCMD_TABLE_CLEAR % channel_index)
            self.dev.cmd(MOGCMD_TABLE_EDGE_RISING % channel_index)  # set trigger edge rising
            freq  = data[DDS_CHANNEL_PROP_FREQ]
            amp   = data[DDS_CHANNEL_PROP_AMP]
            phase = data[DDS_CHANNEL_PROP_PHASE]
            for i in range(len(times)-1):
                self.dev.cmd(MOGCMD_TABLE_APPEND % (channel_index, freq[i], amp[i], phase[i], int(times[i]/RESOLUTION_TABLE_MODE)))
            # switch off at end of table
            self.dev.cmd(MOGCMD_TABLE_APPEND_OFF % (channel_index, int(times[-1]/RESOLUTION_TABLE_MODE)+1))
            # set number of entries and arm table
            self.dev.cmd(MOGCMD_TABLE_ENTRIES % (channel_index,len(times)))
            self.dev.cmd(MOGCMD_TABLE_ARM % channel_index)
            self.dev.cmd(MOGCMD_ALL_ON % channel_index)

        # table mode with external trigger
        for channel, data in self.table_trig.items():
            self.dev.cmd(MOGCMD_MODE_TABLE)
            self.dev.cmd(MOGCMD_TABLE_CLEAR % channel_index)
            self.dev.cmd(MOGCMD_TABLE_EDGE_RISING % channel_index)  # set trigger edge rising
            freq  = data[DDS_CHANNEL_PROP_FREQ]
            amp   = data[DDS_CHANNEL_PROP_AMP]
            phase = data[DDS_CHANNEL_PROP_PHASE]
            for i in range(len(times)-1):
                self.dev.cmd(MOGCMD_TABLE_APPEND % (channel_index, freq[i], amp[i], phase[i], 0))
            # switch off at end of table
            self.dev.cmd(MOGCMD_TABLE_APPEND_OFF % (channel_index, 0))
            # set number of entries and arm table
            self.dev.cmd(MOGCMD_TABLE_ENTRIES % (channel_index, len(data)))
            self.dev.cmd(MOGCMD_TABLE_ARM % channel_index)
            self.dev.cmd(MOGCMD_ALL_ON % channel_index)

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
                if not SYNC_RESET_EACH_RUN and (count < 1):
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

        # save starting time and last update time such that first status_monitor prints status immediately
        self.t_start = get_ticks()
        self.t_last  = -2*self.update_time

        return self.final_values

    def transition_to_manual(self, abort=False):
        # this is called for all QRF devices

        # TODO: can we get some status from QRF, if table is executed?
        self.board_status = error = 0

        if abort:
            # on abort manually program final values
            print('transition to manual (abort)')
            self.program_manual(self.final_values)
        else:
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

        # return True to indicate we successfully transitioned back to manual mode
        # we do this even on error to avoid ugly error in GUI and force user to restart board.
        # the error code is transmitted with status_monitor status_end=True after this function returns.
        return True

    def status_monitor(self, status_end):
        """
        this is called from DeviceTab::status_monitor during run to update status - but of primary board only!
        i.e. if none of the boards is primary this is never called!
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
            # TODO: can we read out status in timed mode?
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

    def shutdown(self):
        # execute only when we are connected
        if self.dev is not None:
            # turn all channels off
            for i in range(1, MAX_NUM_CHANNELS + 1):
                self.dev.cmd(MOGCMD_ALL_OFF % i)
            self.dev.close()
        print(self.device_name,'shutdown')
        sleep(1.0)
