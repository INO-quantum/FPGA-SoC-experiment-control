#####################################################################
# blacs_worker for FPGA-SoC device by Andreas Trenkwalder
# works as PseudoClockDevice
# created 6/4/2021
# last change 01/07/2024 by Andi
#####################################################################

import sys
import numpy as np
from time import sleep

import logging
from blacs.tab_base_classes import Worker

from labscript import (
    LabscriptError,
    StaticDigitalOut, StaticDigitalQuantity,
    StaticAnalogOut, StaticAnalogQuantity
)
from labscript_utils import import_or_reload

from .labscript_device import (
    log_level, save_print,
    SOCK_TIMEOUT_SHORT, SOCK_TIMEOUT,
    SERVER_ACK, SERVER_NACK, SERVER_STOP, SERVER_CMD_NUM_BYTES,
    SERVER_OPEN, SERVER_RESET, SERVER_CONFIG, SERVER_CLOSE, SERVER_START, SERVER_WRITE,
    SERVER_STATUS, SERVER_STATUS_FULL, SERVER_STATUS_RSP, SERVER_STATUS_IRQ_RSP, SERVER_STATUS_IRQ,
    SERVER_GET_REG, SERVER_SET_REG, SERVER_SET_EXT_CLOCK,
    FPGA_REG_CTRL, FPGA_REG_CTRL_IN0, FPGA_REG_CTRL_IN1, FPGA_REG_CTRL_OUT0, FPGA_REG_CTRL_OUT1,
    FPGA_REG_STRB_DELAY, FPGA_REG_SYNC_DELAY, FPGA_REG_SYNC_PHASE, FPGA_REG_FORCE_OUT,
    CONFIG_RUN_64, CONFIG_RUN_96, CONFIG_TRANS, CONFIG_CLOCK, CONFIG_CYCLES,
    CONFIG_NUM_BYTES, SYNC_WAIT_AUTO, SYNC_WAIT_PRIM, SYNC_WAIT_SINGLE, SYNC_WAIT_SEC,
    SYNC_PHASE_NONE, SYNC_PHASE_AUTO, SYNC_PHASE_SEC,
    CTRL_AUTO_SYNC_EN, CTRL_AUTO_SYNC_PRIM, CTRL_EXT_CLK, CTRL_ERR_LOCK_EN,
    default_in_prim, default_out_prim, default_in_sec, default_out_sec,
    STR_CONFIG, STR_INPUTS, STR_OUTPUTS, STR_SIMULATE, STR_CYCLES,
    STR_IGNORE_CLOCK_LOSS, STR_SYNC_PHASE, STR_SYNC_WAIT, STR_EXT_CLOCK,
    CONFIG_MANUAL_MASK,
    MSG_ENABLED, MSG_DISABLED, MSG_EXT_CLOCK, MSG_IO_SETTINGS,
    MSG_IGNORE_CLOCK_LOSS,
    START_TIME, BIT_NOP_SH,
    from_string, get_board_samples,
    get_rack, get_address, get_channel,
    to_client_status, from_client_status,
    to_client_sr32, from_client_sr32, STRUCT_CLIENT_SR32_NUM_BYTES,
    TIME_STEP, EVT_TIMEOUT,
    STATUS_EXT_LOCKED, STATUS_RUN, STATUS_END, STATUS_WAIT, STATUS_ERROR, STATUS_ERR_LOCK, STATUS_SECONDARY_READY,
    to_config, from_config, stop_primary_on_secondary_error,
    STRB_DELAY, STR_STRB_DELAY,
    AnalogChannels, DigitalChannels, DDSChannels,
    AnalogOutput, DigitalOutput,
    to_client_data32, get_bytes,
    FPGA_STATUS_NUM_BYTES_8, FPGA_status, FPGA_STATUS_OK, FPGA_STATUS_ENACK,
)
from .in_out import (
    get_ctrl_io, get_io_selection, get_io_info, is_enabled,
    STR_TRIG_START, STR_TRIG_STOP, STR_TRIG_RESTART,
)
from .shared import (
    use_prelim_version,
    DDS_CHANNEL_FREQ, DDS_CHANNEL_AMP, DDS_CHANNEL_PHASE,
    ALWAYS_SHOW, MAX_SHOW, show_data,
    CONFIG_EACH_RUN,
    CRC_CHECK, CRC,
    ADDR_SHIFT, ADDR_MASK_SH,
)

#connect to server
#timeout = time in seconds (float) after which function returns with error
#returns connected socket if connected, None on error
def connect(timeout, con):
    ip, port = con.split(':')
    port = int(port)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    save_print("connecting to %s:%i (max %.3fs) ..." % (ip, port, timeout))
    try:
        sock.connect((ip,port))
        #sock.setblocking(0)
        sock.settimeout(None)
        save_print("connection ok")
        return sock
    except socket.timeout:
        save_print("timeout!")
    except Exception as e:
        save_print("exception: \"%s\" (ignore)" % (str(e)))
    sock.close()
    return None

#receive data from server while sending data (can be None)
#function returns when recv_bytes received or timeout (None=Infinite)
#returns received bytes from server or None if nothing received (timeout)
#        if recv_bytes = 0 returns True if data was sent, otherwise None
#if output is not None:
#   if recv_bytes == 0 prints output + number of sent bytes
#   if recv_bytes == 2 prints output + information if ACK/NACK received
#   if recv_bytes > 2  prints output + number of received bytes
def send_recv_data(sock, data, timeout, recv_bytes=2, output=None):
    size = None
    if (data is None) and (recv_bytes > 0):
        #wait for new data
        (rd, wr, err) = select.select([sock], [], [], timeout)
    else:
        #send data
        try:
            sock.send(data)
        except (BrokenPipeError, OSError):
            # this happens when server closed connection
            save_print('%s error: server disconnected (send)!' % ('send_recv_data' if output is None else output))
            return None
        if recv_bytes > 0: #wait until data received
            (rd, wr, err) = select.select([sock], [], [], timeout)
        else: # only send data
            # here we wait until sending finished. if this fails we get timeout warning below.
            (rd, wr, err) = select.select([], [sock], [], timeout)
            if len(wr) == 1: # data sent (at least is in output buffer).
                if output is not None:
                    save_print('%s %d bytes sent' % (output,len(data)))
                return True
    if len(rd) == 1: #data available for receive
        if True:
            try:
                data = sock.recv(recv_bytes)
            except (ConnectionResetError, OSError):
                # this happens when server closed connection
                save_print('%s error: server disconnected (recv)!' % ('send_recv_data' if output is None else output))
                return None
        else: # test if server sends more data than expected
            data = sock.recv(recv_bytes+10)
            save_print("received %s (%d/%d bytes)" % (str(data), len(data), recv_bytes))
            data = data[:recv_bytes]
        if output is not None: # output what we received
            if recv_bytes == 2: # expect ACK or NACK
                if data == SERVER_ACK: save_print('%s ACK' % (output))
                elif data == SERVER_NACK: save_print('%s NACK' % (output))
                elif len(data) == 0: save_print('%s closed connection!' % (output))
                else: save_print('%s unknown bytes %s' % (output, data))
            else: # expect other data
                save_print('%s received %d bytes' % (output, len(data)))
        return data
    if output is not None: save_print('%s failed (timeout)!' % (output))
    return None

if use_prelim_version:
    ctrl_in_def = [0,0]
    ctrl_out_def = [0,0]
else:
    ctrl_in_def = 0
    ctrl_out_def = 0

def init_connection(info, con, reset):
    "connect - open - reset board. returns socket or None on error"
    sock = connect(SOCK_TIMEOUT_SHORT, con)
    if sock is None:
        print("%s: connection %s failed!" % (info, con))
    else:
        print("%s: connected at %s ok" % (info, con))
        # open board
        result = send_recv_data(sock, SERVER_OPEN, SOCK_TIMEOUT_SHORT, output='OPEN')
        if result == SERVER_ACK:
            if reset: # reset board
                result = send_recv_data(sock, SERVER_RESET, SOCK_TIMEOUT_SHORT, output='RESET')
                if result == SERVER_ACK:
                    return sock
            else: return sock
        #something went wrong. close socket after short timeout
        send_recv_data(sock, SERVER_CLOSE, 0.1, output='close')
        sock.close()
    return None

def send_config(info, sock, reset, bus_rate, config, ctrl_in, ctrl_out, strb_delay, sync_wait, sync_phase):
    """
    send configuration to board.
    returns True if ok, False on error.
    on error sends SERVER_CLOSE and closes socked.
    """
    if sock is None:
        print("%s: not connected!" % (info))
    else:
        if reset:
            # reset board
            result = send_recv_data(sock, SERVER_RESET, SOCK_TIMEOUT_SHORT, output='RESET')

        if (not reset) or (result == SERVER_ACK):
            # select sync_wait time and sync_phase depending if primary or secondary board
            if config & CTRL_AUTO_SYNC_EN:
                if config & CTRL_AUTO_SYNC_PRIM:
                    if sync_wait is None:  sync_wait  = SYNC_WAIT_PRIM
                    if sync_phase is None: sync_phase = SYNC_PHASE_NONE
                else:
                    if sync_wait is None:  sync_wait  = SYNC_WAIT_SEC
                    if sync_phase is None: sync_phase = SYNC_PHASE_SEC
            else:
                if sync_wait is None:  sync_wait  = SYNC_WAIT_SINGLE
                if sync_phase is None: sync_phase = SYNC_PHASE_NONE
            # send configuration. server will return new configuration (no ACK)
            data = to_config(SERVER_CONFIG, CONFIG_CLOCK, bus_rate, config, ctrl_in, ctrl_out,
                             CONFIG_CYCLES, CONFIG_TRANS, strb_delay, sync_wait, sync_phase)
            result = send_recv_data(sock, data, SOCK_TIMEOUT_SHORT, recv_bytes=len(data), output='CONFIG')
            if result is None:
                print("%s: timeout!" % (info))
            elif (len(result) == SERVER_CMD_NUM_BYTES):
                if result == SERVER_NACK:
                    print("%s: NACK received!" % (info))
                else:
                    print("%s: unexpected data received:" % (info), result)
            elif len(result) != CONFIG_NUM_BYTES:
                print("%s: unexpected data received:" % (info), result)
            else:
                if use_prelim_version:
                    [cmd, clock, scan, config, ctrl_in[0], ctrl_in[1], ctrl_out[0], ctrl_out[1], reps, trans, strb_delay, sync_wait, sync_phase] = from_config(result)
                else:
                    [cmd, clock, scan, config, ctrl_in, ctrl_out, reps, trans, strb_delay, sync_wait, sync_phase] = from_config(result)
                if cmd != SERVER_CONFIG:
                    print('%s: config received %s instead of %s!' % (info, str(cmd), str(SERVER_CONFIG)))
                else:
                    print("%s: ok" % (info))
                    return True

        # something went wrong:
        # close socket after short timeout and return None
        send_recv_data(sock, SERVER_CLOSE, 0.1, output='close')
        sock.close()
        sock = None
    return False

def send_data(info, sock, data, reset):
    """
    send data to socket.
        sock = socket
        data = 2d numpy array of data with time and one or two data columns
        reset = if True reset board before sending any data
    returns True if ok, False on error.
    on error sends SERVER_CLOSE and closes socked.
    """
    # check input
    if sock is None:
        print("%s: not connected!" % (info))
    else:
        # display data for debugging
        if ALWAYS_SHOW or len(data) <= MAX_SHOW:
            show_data(data)
        else:
            print('%i samples' % (len(data)))

        # reset board
        if reset == True:
            result = send_recv_data(sock, SERVER_RESET, SOCK_TIMEOUT, output='RESET')

        if (not reset) or (result == SERVER_ACK):
            # write data to board
            num_bytes = len(data)*len(data[0])*4
            result = send_recv_data(sock, to_client_data32(SERVER_WRITE, num_bytes), SOCK_TIMEOUT, output='SEND %d bytes?'%(num_bytes))
            if result == SERVER_ACK:
                result = send_recv_data(sock, data.tobytes(order='C'), None, output='SEND %d bytes'%(num_bytes))
                if result == SERVER_ACK:
                    print('%d bytes sent to server (ok)' % (num_bytes))
                    return True

        # something went wrong:
        # close socket after short timeout and return None
        send_recv_data(sock, SERVER_CLOSE, 0.1, output='close')
        sock.close()
        sock = None
    return False

#BLACS worker thread
class FPGA_worker(Worker):
    def init(self):
        exec('from numpy import *', globals())
        global h5py; import labscript_utils.h5_lock, h5py
        global re; import re
        global socket; import socket
        global select; import select
        global struct; import struct
        global get_ticks; from time import perf_counter as get_ticks

        # these functions allow to send events between the board worker processes
        # the minimum propagation time is however ca. 0.7(1)ms, which is not super fast.
        global zprocess; from zprocess import ProcessTree
        global zTimeoutError; from zprocess.utils import TimeoutError as zTimeoutError
        global process_tree; process_tree = ProcessTree.instance()

        # last board status. None on error
        self.board_status  = None
        self.board_time    = 0
        self.board_samples = 0
        self.board_cycles  = 0
        self.abort = False
        self.t_start = [0,0]; # start time from transition_to_manual and start_run
        self.final_values = {}
        self.front_panel_values = {}

        # default configuration
        self.config     = CONFIG_RUN_96 if (self.num_racks == 2) else CONFIG_RUN_64
        self.error_mask = 0xffff_ffff
        self.ext_clock  = False
        self.ignore_clock_loss = False
        self.sync_wait  = SYNC_WAIT_AUTO
        self.sync_phase = SYNC_PHASE_AUTO
        self.num_cycles = CONFIG_CYCLES
        self.strb_delay = STRB_DELAY
        self.simulate   = False

        if self.is_primary:
            # primary board
            self.config |= CTRL_AUTO_SYNC_EN | CTRL_AUTO_SYNC_PRIM
            self.ctrl_in  = get_ctrl_io(default_in_prim, input=True)
            self.ctrl_out = get_ctrl_io(default_out_prim, input=False)
            if len(self.boards) > 0:
                # secondary boards available
                save_print("init primary board '%s' with %i secondary boards" % (self.device_name, len(self.boards)))
            else:
                # single board
                save_print("init primary board '%s' without secondary boards" % (self.device_name))
        else:
            # secondary board: lock to external clock and wait for trigger
            self.ext_clock = True # external clock is always used
            self.config |= CTRL_AUTO_SYNC_EN | CTRL_EXT_CLK
            self.ctrl_in  = get_ctrl_io(default_in_sec, input=True)
            self.ctrl_out = get_ctrl_io(default_out_sec, input=False)
            save_print("init secondary board '%s'" % (self.device_name))

        # True if start trigger is enabled
        self.start_trg = is_enabled([STR_TRIG_START], self.ctrl_in, input=True)
        # True if external clock is used
        self.ext_clock = ((self.config & CTRL_EXT_CLK) != 0)
        # True if clock loss for short time should be ignored
        self.ignore_clock_loss = ((self.config & CTRL_ERR_LOCK_EN) == 0)

        # use settings given in worker arguments
        # they might be updated by worker_args_ex in hd5 file
        # returns worker args with None removed
        self.worker_args_ex = {}
        self.sock = None    # socket is not yet open. we write to registers below.
        self.worker_args = self.parse_worker_args(self.worker_args, init=True)

        # ensure external clock is set in config
        self.onChangeExtClock(self.ext_clock)

        if False: # print selected options
            self.onChangeInputs(self.ctrl_in)
            self.onChangeOutputs(self.ctrl_out)
            self.onChangeExtClock(self.ext_clock)
            self.onChangeIgnoreClockLoss(self.ignore_clock_loss)

        if not self.simulate:
            # connect - open - reset - configure board
            # on error: we disconnect and set self.sock=None
            #           in program_manual and transition_to_buffered we retry
            info = "'%s' init"%self.device_name
            self.sock = init_connection(info, self.con, reset=True)
            if self.sock is not None:
                send_config(info, self.sock,
                            reset       = False,
                            bus_rate    = self.bus_rate,
                            config      = self.config & CONFIG_MANUAL_MASK,
                            ctrl_in     = [0,0],
                            ctrl_out    = self.ctrl_out,
                            strb_delay  = self.strb_delay,
                            sync_wait   = self.sync_wait,
                            sync_phase  = self.sync_phase)
        else: self.sock = None
        self.first_time   = True
        self.state_manual = False # config is in manual state (True) or in running state (False)

        # prepare zprocess events for communication between primary and secondary boards
        # primary board: boards/events = list of all secondary board names/events
        # secondary board: boards/events = list containing only primary board name/event
        self.count = 0 # counts 2x with every experimental cycle
        if self.is_primary:
            self.events = [self.process_tree.event('%s_evt'%s, role='both') for s in self.boards]
            self.warnings = [False for _ in self.boards]
            self.warn = False
        else:
            self.events = [self.process_tree.event('%s_evt' % self.device_name, role='both')]
            self.warnings = []
            self.warn = False

        # reduce number of log entries in logfile (labscript-suite/logs/BLACS.log)
        self.logger.setLevel(log_level)

        print('simulate:', self.simulate)
        print("source file:", __file__)

        # go through channels and collect initialization data
        # this also loads the device class object into channel.cls
        # this is needed from program_manual for hardware initialization
        # and to call to_word for user input
        print('%i channels' % (len(self.channels)))
        init_data = []
        for connection, channel in self.channels.items():
            # note: the default channel.device_class is only the class name
            #       but we need the path + name for loading device class!
            device_class = channel.properties['device_class'].split('.')
            module_name = '.'.join(device_class[:-1])
            class_name  = device_class[-1]
            if class_name != channel.device_class:
                raise LabscriptError("%s (%s) class name '%s' != '%s'!" % (channel.name, connection, class_name, channel.device_class))
            import_or_reload(module_name)
            channel.cls = getattr(sys.modules[module_name], channel.device_class)
            if False and hasattr(channel.cls, 'test'):
                # perform self tests
                channel.cls.test()

    def program_manual(self, front_panel_values):
        # save actual front panel values
        self.front_panel_values = front_panel_values

        # 1. we first loop through all channels and generate a list of changed digital channels.
        # 2. for changed analog channels we can already generate samples since each channel has its unique address.
        data = []
        time = START_TIME
        do_samples = {}
        #save_print(self.do_list)
        #save_print('program manual final values:', self.final_values)
        #print('channels', self.channels.keys())
        #save_print('GUI   values:', front_panel_values)
        for key, value in front_panel_values.items():
            try:
                channel = self.channels[key]
            except KeyError:  # unknown device?
                save_print("unknown device '%s', value: " % (key), value)
                continue
            try:
                last = self.final_values[key]
            except KeyError:
                last = None
                self.first_time = True

            # on startup init hardware when needed
            # init_hardware might return several samples or None
            if self.first_time and hasattr(channel.cls, 'init_hardware'):
                raw_data = channel.cls.init_hardware(channel.properties)
                if raw_data is not None:
                    rack = channel.properties['rack']
                    for d in raw_data:
                        sample = [time] + [BIT_NOP_SH] * self.num_racks
                        sample[rack + 1] = d
                        data.append(sample)
                        time += TIME_STEP
                    print('init hardware %s (%s), %i data words:' % (channel.name, key, len(raw_data)), '['+('.'.join(['0x%x'%d for d in raw_data])+']'))

            if self.first_time or (key not in self.final_values) or (value != last):
                if last is not None: save_print("'%s' changed from %s to %s" % (key, str(last), str(value)))
                if channel.parent.device_class == 'AnalogChannels':
                    rack    = channel.properties['rack']
                    # TODO: units conversion? it would be good to have only one function for this!
                    sample = [time] + [BIT_NOP_SH] * self.num_racks
                    sample[rack + 1] = channel.cls.to_words(channel.properties, np.array([value]))[0]
                    #print("addr 0x%02x: %.3fV = 0x%08x" % (address, value, sample[rack+1]))
                    data.append(sample)
                    time += TIME_STEP
                elif channel.parent.device_class == 'DigitalChannels':
                    rack    = channel.properties['rack']
                    address = channel.properties['address']
                    word    = channel.cls.to_words(channel.properties, np.array([value]))[0]
                    try:
                        sample = do_samples[address]
                        if sample[rack] == BIT_NOP_SH:
                            do_samples[address][rack] = word
                        else:
                            do_samples[address][rack] = sample[rack] | word
                    except KeyError:
                        sample = [BIT_NOP_SH] * self.num_racks
                        sample[rack] = word
                        do_samples[address] = sample
                elif channel.parent.device_class == 'DDSChannels':
                    rack    = channel.properties['rack']
                    address = channel.properties['address']
                    for sub_type, v in value.items():
                        if self.first_time or (v != last[sub_type]):
                            name = channel.name + '_' + sub_type
                            sub = channel.child_list[name]
                            if (last is not None) and (sub_type in last):
                                save_print("'%s' changed from %f to %f" % (name, last[sub_type], v))
                            #print(sub.name, channel.name, channel.cls.__name__, v)
                            if sub_type == 'freq': v = v*1e6
                            raw_data = channel.cls.to_words(sub.properties, np.array([v]))
                            #print(channel.name, name, sub.properties, v, raw_data)
                            for d in raw_data:
                                sample = [time] + [BIT_NOP_SH] * self.num_racks
                                sample[rack + 1] = d
                                data.append(sample)
                                time += TIME_STEP
        # next time update only changes
        self.first_time = False

        # get digital samples
        for s in do_samples.values():
            sample = [time] + s
            data.append(sample)
            time += TIME_STEP

        # write samples to device
        if len(data) > 0:
            if self.simulate:
                save_print("simulate '%s' prg. manual (%i channels)" % (self.device_name, len(self.channels)))
                if ALWAYS_SHOW or len(data) <= MAX_SHOW:
                    show_data(np.array(data))
                else:
                    save_print('%i samples' % (len(data)))
                return front_panel_values  # ok
            else:
                if self.sock is None:
                    # try to reconnect to device
                    # this happens when an error ocurred or when no connection could be established during init
                    info = "'%s' prg. manual" % self.device_name
                    self.sock = init_connection(info, self.con, reset=True)
                    if self.sock is not None:
                        send_config(info, self.sock,
                                    reset       = False,
                                    bus_rate    = self.bus_rate,
                                    config      = self.config & CONFIG_MANUAL_MASK,
                                    ctrl_in     = [0, 0],
                                    ctrl_out    = self.ctrl_out,
                                    strb_delay  = self.strb_delay,
                                    sync_wait   = self.sync_wait,
                                    sync_phase  = self.sync_phase)
                        self.state_manual = True
                elif not self.state_manual:
                    # switch from running into manual state
                    # this disabled ext clock and ext trigger
                    self.set_reg(FPGA_REG_CTRL, self.config & CONFIG_MANUAL_MASK)
                    self.set_reg(FPGA_REG_CTRL_IN0, 0)
                    self.set_reg(FPGA_REG_CTRL_IN1, 0)
                    self.state_manual = True

                if self.sock is not None:  # device is connected
                    info = "'%s' prg. manual" % self.device_name
                    save_print("%s (%i channels)" % (info, len(data)))

                    # reset + write + configure only control register
                    result = send_data(info, self.sock, np.array(data,dtype=np.uint32), reset=True)
                    if result:
                        result = (self.set_reg(FPGA_REG_CTRL, self.config & CONFIG_MANUAL_MASK) is not None)

                    if result:
                        # start output
                        reps = 1
                        result = send_recv_data(self.sock, to_client_data32(SERVER_START, reps), SOCK_TIMEOUT, output='START')
                        if result == SERVER_ACK:
                            # wait for completion (should be immediate)
                            result = False
                            count = 0
                            while True:
                                sleep(0.1)
                                result = self.status_monitor(False)[0]
                                if result is None:
                                    print("'%s' prg. manual failed!" % self.device_name)
                                    break
                                elif count >= 10:
                                    print("'%s' prg. manual not finised after %i loops!" % (self.device_name, count))
                                    break
                                elif result == True:
                                    break
                                count += 1
                            # stop output
                            send_recv_data(self.sock, SERVER_STOP, SOCK_TIMEOUT, output='STOP')
                            if result == SERVER_ACK:
                                return front_panel_values # ok

        return False # TODO: how to indicate error? maybe return nothing?

    def transition_to_buffered(self, device_name, hdf5file, initial_values, fresh):
        """
        prepare experimental sequence.
        return on error None which calls abort_transition_to_buffered
        return on success list of final values of sequence. TODO: seems not to be used anywhere?
        """
        self.count = 0
        self.t_start[0] = get_ticks()
        if self.simulate:
            self.state_manual = False
        else:
            if self.sock is None: # try to reconnect to device
                info = "'%s' to buffered"%self.device_name
                self.sock = init_connection(info, self.con, reset=True)
                if not CONFIG_EACH_RUN:
                    result = send_config('start', self.sock,
                                         reset      = False,
                                         bus_rate   = self.bus_rate,
                                         config     = self.config,
                                         ctrl_in    = self.ctrl_in,
                                         ctrl_out   = self.ctrl_out,
                                         strb_delay = self.strb_delay,
                                         sync_wait  = self.sync_wait,
                                         sync_phase = self.sync_phase)
                    self.state_manual = False
            elif self.state_manual:
                # switch from manual into running state
                # this enables ext clock and ext trigger if needed
                self.set_reg(FPGA_REG_CTRL, self.config)
                self.set_reg(FPGA_REG_CTRL_IN0, self.ctrl_in[0])
                self.set_reg(FPGA_REG_CTRL_IN1, self.ctrl_in[1])
                self.state_manual = False
            if self.sock is None:
                return None

        self.abort = False
        with h5py.File(hdf5file,'r') as hdf5_file:
            group = hdf5_file['devices/%s'%(device_name)]
            data = group['%s_matrix'%device_name][:] # TODO: without [:] does not work?
            #print(data)
            #print(data.shape)

            self.final_values = from_string(group['%s_final' % device_name][0])
            print('final values:', self.final_values)

            if CRC_CHECK:
                all_crc = from_string(group['%s_CRC' % device_name][0])
                print('CRC:', all_crc)

            t_read = (get_ticks()-self.t_start[0])*1e3

            # use updated settings given in worker_args_ex which take precedence to worker_args.
            # however, worker_args are not overwritten, so if worker_args_ex are not anymore set, original worker_args apply.
            worker_args_ex = from_string(group['%s_worker_args_ex' % device_name][0])
            #print('updating worker_args', worker_args_ex)
            self.parse_worker_args(worker_args_ex)

            # save number of samples
            # TODO: if this is 0 for one board interprocess communication will timeout
            self.samples = len(data)

            if len(data) == 0:
                save_print("'%s' no data!" % (self.device_name))
                self.exp_time = self.exp_samples = self.last_time = 0
            else:

                # TODO: if the data has not changed it would not need to be uploaded again?
                #       the simplest would be to save a counter into hdf5 which is incremented on each new generation.
                #       additionally, in generate code one could check if data has changed to last time.

                # save last time of data
                self.last_time = data[-1][0]

                # get expected board samples and board time. these can be different.
                self.exp_samples, self.exp_time = get_board_samples(self.samples, self.last_time)

                #print('worker_args =', self.worker_args)
                save_print(self.device_name, 'is', 'primary' if self.is_primary else 'secondary')
                save_print(self.device_name, 'uses' if self.start_trg else 'does not use', 'start trigger')
                save_print(self.device_name, 'uses' if self.ext_clock else 'does not use', 'external clock')
                save_print('FPGA    control bits 0x%08x' % (self.config))
                if use_prelim_version:
                    save_print('input   control bits 0x%08x/%08x' % (self.ctrl_in[0],self.ctrl_in[1]))
                    save_print('output  control bits 0x%08x/%08x' % (self.ctrl_out[0],self.ctrl_out[1]))
                else:
                    save_print('input   control bits 0x%08x' % (self.ctrl_in,self.ctrl_in))
                    save_print('output  control bits 0x%08x' % (self.ctrl_out0,self.ctrl_out1))

                if CRC_CHECK:
                    # calculate CRC for all channels
                    # TODO: data with BIT_NOP_SH might be counted wrongly?
                    # TODO: raising LabscriptError here crashes or blocks BLACS main thread!!!
                    #       secondary worker sync_board (event) timeout does not work!!!
                    #       BLACS needs to be restarted and secondary worker process
                    #       keeps in background running! propably sometimes keeping h5 file open?
                    #       this causes strange file issues: 'file temporarily unavailable'
                    #       or BLACS says file saving but never stops?
                    # note: the result depends on the order of commands!
                    #       this fails when in experiment script commnands
                    #       are not inserted with increasing time!
                    #       this ensures that data is not mixed-up which could cause false ok.
                    for connection, crc in all_crc.items():
                        channel = self.channels[connection]
                        rack    = channel.properties['rack']
                        address = channel.properties['address']
                        ch      = channel.properties['channel']
                        if hasattr(channel.cls, 'ADDR_RNG_MASK'):
                            # DDS might have address-range which can be covered by ADDR_MASK
                            addr_mask = channel.cls.ADDR_RNG_MASK << ADDR_SHIFT
                        else:
                            addr_mask = ADDR_MASK_SH
                        mask = ((data[:,rack + 1] & addr_mask) == (address << ADDR_SHIFT))
                        raw_data = data[:,[0,rack + 1]][mask]
                        value = CRC([address])(raw_data[:, 1])
                        print('%s (%s) address 0x%02x rack %i CRC 0x%08x (%s)' % (channel.name, connection, address, rack, value, 'ok' if crc == value else 'error!'))
                        if len(raw_data) > 0:
                            print('final time %f: value %s' % (raw_data[-1,0]/self.bus_rate, str(self.final_values[connection])))
                        if ALWAYS_SHOW or len(raw_data) <= MAX_SHOW:
                            show_data(raw_data, info='%i samples:' % (len(raw_data)), bus_rate=self.bus_rate)
                        if value != crc:
                            raise LabscriptError('%s %i samples CRC 0x%08x != 0x%08x' % (channel.name, len(raw_data), value, crc))
                        # check word_to_freq
                        values = channel.cls.from_words(channel.child_list[channel.name+'_freq'].properties, data[:,0], data[:,rack+1])
                        print('freq  (MHz) =', values)
                        values = channel.cls.from_words(channel.child_list[channel.name+'_amp'].properties, data[:,0], data[:,rack+1])
                        print('amp   (dBm) =', values)
                        values = channel.cls.from_words(channel.child_list[channel.name+'_phase'].properties, data[:,0], data[:,rack+1])
                        print('phase (deg) =', values)

                if self.is_primary:
                    # primary board

                    # reset and send data
                    # returns True on success, False on error.
                    if self.simulate:
                        result = True
                        if ALWAYS_SHOW or len(data) <= MAX_SHOW:
                            show_data(np.array(data))
                    else:
                        if CONFIG_EACH_RUN:
                            # reset + configure + write
                            result = send_config('start', self.sock,
                                        reset       = True,
                                        bus_rate    = self.bus_rate,
                                        config      = self.config,
                                        ctrl_in     = self.ctrl_in,
                                        ctrl_out    = self.ctrl_out,
                                        strb_delay  = self.strb_delay,
                                        sync_wait   = self.sync_wait,
                                        sync_phase  = self.sync_phase)
                            if result:
                                result = send_data(self.device_name, self.sock, data, reset=False)
                        else:
                            # reset + write + configure only control register
                            result = send_data(self.device_name, self.sock, data, reset=True)
                            if result:
                                result = (self.set_reg(FPGA_REG_CTRL, self.config) is not None)

                    # TODO: this might be problematic with 2nd board.
                    if result != True: return None

                    t_data = (get_ticks() - self.t_start[0]) * 1e3
                    save_print('send data result =', result)
                    #save_print('events =',self.events)
                    if len(self.events) > 0:
                        # primary board: send start event to secondary boards with time and result
                        for evt in self.events:
                            evt.post(self.count, data=(get_ticks(),result))
                        save_print("'%s' post start, result=%s (%i)" % (self.device_name, str(result), self.count))
                        self.count += 1

                        # primary board: wait for secondary boards started
                        for i,evt in enumerate(self.events):
                            try:
                                t_start = get_ticks()
                                result = evt.wait(self.count, timeout=EVT_TIMEOUT)
                                t_end = get_ticks()
                                save_print("'%s' wait '%s': %s, posted %.3fms, waited %.3fms (%i)" % (self.device_name, self.boards[i], str(result[1]), (t_end - result[0]) * 1e3, (t_end - t_start) * 1e3, self.count))
                                if result[1] == False: return None # TODO: what to do with this?
                            except zTimeoutError:
                                save_print("'%s' wait '%s' started: timeout %.3fs (%i)" % (self.device_name, self.boards[i], get_ticks() - t_start, self.count))
                                return None

                    # start primary board
                    # note: FPGA_worker::start_run is called from transition_to_buffered since FPGA_tab::start_run is called only for primary pseudoclock device.
                    #sleep(0.1)
                    result = self.start_run()
                    t_start = (get_ticks() - self.t_start[0]) * 1e3
                    print('start: %s (hdf %.1fms c&d %.1fms st %.1fms tot %.1fms)' % (result, t_read, t_data-t_read, t_start-t_data, t_start))
                    if result != True: return None
                else:
                    # secondary board

                    # wait for start event, i.e. until primary board is reset
                    try:
                        t_start = get_ticks()
                        print('wait start')
                        result = self.events[0].wait(self.count, timeout=EVT_TIMEOUT)
                        t_end = get_ticks()
                        save_print("'%s' wait start: %s, posted %.3fms, waited %.3fms (%i)" % (self.device_name, str(result[1]), (t_end - result[0])*1e3, (t_end - t_start)*1e3, self.count))
                        if result[1] == False: return None
                    except zTimeoutError:
                        save_print("'%s' wait start: timeout %.3fs (%i)" % (self.device_name, get_ticks()-t_start, self.count))
                        return None
                    self.count += 1

                    # get status bits and check if external clock is present
                    if self.simulate:
                        result = to_client_status(cmd=SERVER_STATUS_RSP, board_status=STATUS_SECONDARY_READY, board_time=0, board_samples=0)
                    else:
                        result = send_recv_data(self.sock, SERVER_STATUS, SOCK_TIMEOUT, output=None, recv_bytes=get_bytes(SERVER_STATUS_RSP))
                    if result is None:
                        save_print("'%s' could not get status!" % (self.device_name))
                        return None
                    else:
                        if use_prelim_version:
                            [cmd, self.board_status, self.board_time, self.board_samples, self.board_cycles] = from_client_status(result)
                        else:
                            [cmd, self.board_status, self.board_time, self.board_samples] = from_client_status(result)
                        if (cmd != SERVER_STATUS_RSP) and (cmd != SERVER_STATUS_RSP):
                            save_print("'%s' error receive status!" % (self.device_name))
                            return None
                        else:
                            if not (self.board_status & STATUS_EXT_LOCKED):  # warning or error state
                                save_print("'%s' required external clock is missing!" % (self.device_name))
                                return None

                    # use external clock and send data
                    # returns True on success, False on error.
                    if self.simulate:
                        result = True
                        if ALWAYS_SHOW or len(data) <= MAX_SHOW:
                            show_data(np.array(data))
                    else:
                        if CONFIG_EACH_RUN:
                            # reset + configure + write
                            result = send_config('start', self.sock,
                                        reset       = True,
                                        bus_rate    = self.bus_rate,
                                        config      = self.config,
                                        ctrl_in     = self.ctrl_in,
                                        ctrl_out    = self.ctrl_out,
                                        strb_delay  = self.strb_delay,
                                        sync_wait   = self.sync_wait,
                                        sync_phase  = self.sync_phase)
                            if result:
                                result = send_data(self.device_name, self.sock, data, reset=False)
                        else:
                            # reset + write + configure only control register
                            result = send_data(self.device_name, self.sock, data, reset=True)
                            if result:
                                result = (self.set_reg(FPGA_REG_CTRL, self.config) is not None)

                    if result:
                        # secondary board: start and wait for external trigger
                        result = self.start_run()

                    # post ok for start of primary board
                    self.events[0].post(self.count, data=(get_ticks(), result))
                    save_print("'%s' post start, result=%s (%i, %.1fms)" % (self.device_name, str(result), self.count, (get_ticks() - self.t_start[0])*1e3))

                    if result != True: return None

                self.count += 1

        #return final values for all channels
        print('final values', self.final_values)
        return self.final_values

    def abort_transition_to_buffered(self):
        return self.abort_buffered()
    
    def abort_buffered(self):
        # TODO: maybe just call transition_to_manual from here?
        print('abort buffered')
        self.final_values = {}
        self.abort = True # indicates to status_monitor to return True to stop
        if self.simulate:
            return True # success
        else:
            if self.sock == None:
                save_print("abort_buffered error: '%s' not connected at %s" % (self.device_name, self.con))
                return True
            else:
                # stop board
                result = send_recv_data(self.sock, SERVER_STOP, SOCK_TIMEOUT, output='STOP')
                if result == SERVER_ACK:
                    if True:
                        # close socket after short timeout and return None
                        # this forces the board to be reprogrammed properly after abort
                        send_recv_data(self.sock, SERVER_CLOSE, 0.1, output='abort')
                        self.sock.close()
                        self.sock = None
                    else:
                        # reset board
                        result = send_recv_data(self.sock, SERVER_RESET, SOCK_TIMEOUT, output='RESET')
            if result is None:
                save_print("worker: '%s' abort timeout" % (self.device_name))
                return False  # successful aborted
            elif result == SERVER_ACK:
                save_print("worker: '%s' aborted ok" % (self.device_name))
                return True  # success
            else:
                save_print("worker: '%s' abort error '%s'" % (self.device_name, result))
                return False # error

    def transition_to_manual(self):
        start = get_ticks()
        # stop board. this is called for primary and secondary boards.
        # note: stop is reseting boards which also suspends output clock during reset.
        #       if several boards are running we first stop secondary boards and unlock them from external clock.
        #       last we stop primary board. this ensures that the secondary boards do not loose external clock during primary board reset.
        # note: this is executed in worker process where we have no access to the GUI (FPGA_Tab)
        # TODO: if status monitor detects that board is in error state it will return True and transition_to_manual will stop board
        #       and we return here False to indicate to the user that there was a problem.
        #       returning False here however requires that the board tab needs to be restarted which is not nice.
        # TODO: we check here the state and in status_monitor. it would be nice to do this in one place.
        #       maybe call status_monitor from here to get the final status?
        # TODO: unclear what to do with the final_values?
        all_ok = True
        if self.is_primary and len(self.events) > 0:
            # primary board: wait for all secondary boards to stop.
            for i,evt in enumerate(self.events):
                try:
                    t_start = get_ticks()
                    result = evt.wait(self.count, timeout=EVT_TIMEOUT)
                    t_end = get_ticks()
                    save_print("stop '%s': result=%s, posted %.3fms, waited %.3fms (%i)" % (self.boards[i], str(result[1]), (t_end - result[0]) * 1e3, (t_end - t_start) * 1e3, self.count))
                    if (result[1] is None) or (result[1] == False): all_ok = False
                    self.warnings[i] = result[2]
                except zTimeoutError:
                    save_print("stop '%s': timeout %.3fs (%i)" % (self.boards[i], get_ticks() - t_start, self.count))
                    all_ok = False # secondary board has not answered.

        # all boards: stop, which might also reset board
        #result = send_recv_data(self.sock, to_client_data32(SERVER_STOP, STOP_AT_END), SOCK_TIMEOUT, output='stop')
        if self.simulate:
            result = SERVER_ACK
        elif self.sock == None:  # this should never happen
            save_print("transition_to_manual error: '%s' not connected at %s" % (self.device_name, self.con))
            return False
        else:
            result = send_recv_data(self.sock, SERVER_STOP, SOCK_TIMEOUT, output='STOP')
        if result is None:
            # for secondary boards save result in all_ok
            # for primary board result is not changed.
            if self.is_primary: result = False
            else: all_ok = False
        elif (len(result) != SERVER_CMD_NUM_BYTES) or (result != SERVER_ACK):
            save_print("'%s' stop: unexpected result! %s\n" % (self.device_name, result))
            result = False
        else:
            result = True

            # get board status.
            self.status_monitor(False)
            aborted = '(aborted)' if self.abort else ''
            if (self.board_status == None):
                save_print("'%s' stop: could not get board status! %s\n" % (self.device_name, aborted))
                all_ok = False
            else:
                if (not (self.board_status & STATUS_END)) or (self.board_status & STATUS_ERROR & self.error_mask):
                    save_print("'%s' stop: board is not in end state! status=0x%x %s\n" % (self.device_name, self.board_status, aborted))
                    all_ok = False
                elif (self.board_samples != self.exp_samples):
                    # note: samples are appended with NOP to have multiple of 4. update Oct. 2024: not anymore needed.
                    save_print("'%s' stop: unexpected board samples %i != %i! %s\n" % (self.device_name, self.board_samples, self.exp_samples, aborted))
                    all_ok = False
                elif (self.board_time != self.exp_time):
                    save_print("'%s' stop: unexpected board time %i != %i! %s\n" % (self.device_name, self.board_time, self.exp_time, aborted))
                    all_ok = False

                if (self.board_status & STATUS_ERR_LOCK) and self.ignore_clock_loss:
                    # TODO: how to make it more visible without forcing user interaction
                    #       open dialog box which user has to click, but when already open do not open new one
                    #       but only change text counting number of occurences
                    #       for example see blacs/compile_and_restart.py
                    save_print("\n\n'%s' WARNING: clock lost during last run! %s\n\n" % (self.device_name, aborted))
                    self.warn = True
                else:
                    self.warn = False

        if self.is_primary:
            # primary board: if enabled returns False if any secondary board is in error state
            if stop_primary_on_secondary_error:
                if all_ok == False:
                    save_print("\n'%s' stop: a secondary board is in error state! stop since stop_primary_on_secondary_error=True!\n" % (self.device_name))
                    result = False
        else:
            # secondary boards: unlock from external clock before primary is reset
            if self.simulate or (not self.ext_clock):
                result = all_ok
            else:
                result = self.set_reg(FPGA_REG_CTRL, self.config & CONFIG_MANUAL_MASK)
                if result is None:
                    result = False
                else:
                    save_print("'%s' unlock: ok (%i)" % (self.device_name, self.count))
                    result = all_ok

            # send stop event to primary board with board status: True = ok, False = error
            self.events[0].post(self.count, data=(get_ticks(), result, self.warn))
            save_print("'%s' post stop, result=%s (%i)" % (self.device_name, str(result), self.count))

        self.count += 1

        # show last state and close connection before exiting board tab. afterwards is not possible anymore
        if result == False:
            self.FPGA_get_board_state()
            self.FPGA_disconnect()
            save_print("\n'%s' error!\nfor details see output above.\nplease restart board tab.\n" % (self.device_name))

        # get changed channels # disabled
        # self.changed = self.get_changed_channels()

        # return result. True = ok, False = error
        t_act = get_ticks()
        print('transition to manual result %s (%.1fms, total %.1fms)' % (str(result), (t_act - start)*1e3, (t_act - self.t_start[0])*1e3))
        return result

    def start_run(self):
        # note: FPGA_worker::start_run is called from transition_to_buffered
        #       since FPGA_tab::start_run is called only for primary pseudoclock device,
        #       but we need to start all boards.
        self.t_start[1] = get_ticks()
        self.warn = False
        if self.simulate:
            result = SERVER_ACK
        elif self.sock == None:  # should not happen
            save_print("start_run error: '%s' not connected at %s" % (self.device_name, self.con))
            result = None
        else:
            result = send_recv_data(self.sock, to_client_data32(SERVER_START, self.num_cycles), SOCK_TIMEOUT, output='START')
        if result is None:
            save_print("'%s' start %i cycles: error starting! (timeout, %i)" % (self.device_name, self.num_cycles, self.count))
        elif result == SERVER_ACK:
            if self.start_trg: save_print("'%s' start %i cycles: waiting for trigger ... (%i, %.1fms)" % (self.device_name, self.num_cycles, self.count, (get_ticks()-self.t_start[1])*1e3))
            else:              save_print("'%s' start %i cycles: running ... (%i, %.1fms)" % (self.device_name, self.num_cycles, self.count, (get_ticks()-self.t_start[1])*1e3))
            return True
        else:
            save_print("'%s' start %i cycles: error starting! (%i)" % (self.device_name, self.num_cycles, self.count))
        return False # error

    def status_monitor(self, status_end):
        """
        this is called from FPGA_Tab::status_monitor during run to update status of primary board only.
        is status_end = True then this is called from FPGA_tab::status_end.
        TODO: how to indicate error? None seems to be the same as False?
              return True = finished, False = running
              at the moment we return True on error.
              this will call transition_to_manual where we check board status and return error.
        """
        end = True
        if self.simulate:
            run_time = int((get_ticks() - self.t_start[1])*1e6)
            if run_time >= self.exp_time:
                samples = self.exp_samples
                run_time = self.exp_time
                board_status = STATUS_END
            else:
                samples = int(self.exp_samples * run_time / self.exp_time)
                board_status = STATUS_RUN
            result = to_client_status(cmd=SERVER_STATUS_RSP, board_status=board_status, board_time=run_time, board_samples=samples)
        elif self.sock == None:  # should never happen
            save_print("status_monitor error: '%s' not connected at %s" % (self.device_name, self.con))
            self.board_status = None
            result = None
        else:
            result = send_recv_data(self.sock, SERVER_STATUS_IRQ, SOCK_TIMEOUT, output=None, recv_bytes=get_bytes(SERVER_STATUS_IRQ_RSP))
        if result is None:
            self.board_status = None
        else:
            #save_print('status monitor')
            if use_prelim_version:
                [cmd, self.board_status, self.board_time, self.board_samples, self.board_cycles] = from_client_status(result)
            else:
                [cmd, self.board_status, self.board_time, self.board_samples] = from_client_status(result)
            if (cmd != SERVER_STATUS_RSP) and (cmd != SERVER_STATUS_IRQ_RSP):
                self.board_status = None
            else:
                if self.board_status & STATUS_ERROR: # warning or error state
                    if self.ignore_clock_loss and  ((self.board_status & (STATUS_RUN|STATUS_END|STATUS_ERROR)) == (STATUS_RUN|STATUS_ERR_LOCK)):
                        # clock loss but running
                        save_print('%8i, # %8i, status 0x%08x clock loss (running)!' % (self.board_time, self.board_samples, self.board_status))
                        self.warn = True
                        if not self.abort: end = False
                    elif self.ignore_clock_loss and ((self.board_status & (STATUS_RUN|STATUS_END|STATUS_ERROR)) == (STATUS_END|STATUS_ERR_LOCK)):
                        # clock loss and in end state
                        save_print('%8i, # %8i, status 0x%08x clock loss (end)!' % (self.board_time, self.board_samples, self.board_status))
                        self.warn = True
                    else: # error state
                        save_print('%8i, # %8i, status 0x%08x error!' % (
                        self.board_time, self.board_samples, self.board_status))
                elif self.board_status & STATUS_RUN:
                    if self.board_status & STATUS_WAIT: # restart state
                        save_print('%8i, # %8i, status 0x%08x restart' % (self.board_time, self.board_samples, self.board_status))
                    else: # running state
                        save_print('%8i, # %8i, status 0x%08x running' % (self.board_time, self.board_samples, self.board_status))
                    if not self.abort: end = False
                elif self.board_status & STATUS_END: # end state
                    save_print('%8i, # %8i, status 0x%08x end (%.1fms)' % (self.board_time, self.board_samples, self.board_status, (get_ticks()-self.t_start[1])*1e3))
                #elif self.board_status & STATUS_WAIT: # wait state = start trigger
                elif (self.board_status & STATUS_WAIT) or self.start_trg: # TODO: update firmware such it sets WAIT bit, then we do not need to check for self.start_trg!
                    if (self.board_time == 0) and self.start_trg: # waiting for external trigger
                        save_print('%8i, # %8i, status 0x%08x waiting start trig.' % (self.board_time, self.board_samples, self.board_status))
                    elif (self.board_time > 0) and is_enabled(STR_TRIG_STOP, self.ctrl_in, input=True): # stop state
                        if is_enabled(STR_TRIG_RESTART, self.ctrl_in, input=True):
                            save_print('%8i, # %8i, status 0x%08x waiting restart trig.' % (self.board_time, self.board_samples, self.board_status))
                        else:
                            save_print('%8i, # %8i, status 0x%08x stop trig. (abort)' % (self.board_time, self.board_samples, self.board_status))
                            self.abort = True # no restart trigger is active. TODO: disable 'Repeat'?
                    else:
                        save_print('%8i, # %8i, status 0x%08x unexpected! (abort)\n' % (self.board_time, self.board_samples, self.board_status))
                        self.abort = True
                    if not self.abort: end = False
                else: # unexpected state
                    save_print('%8i, # %8i, status 0x%08x unexpected!\n' % (self.board_time, self.board_samples, self.board_status))
        if status_end:
            #return [end, self.get_warnings() if end else [], self.changed] # disabled. see get_changed_channels.
            return [end, self.get_warnings() if end else [], {}]
        else:
            return [end, self.get_warnings() if end else []]

    def get_warnings(self):
        "return list of secondary board names where a clock lost warning should be displayed"
        #TODO: allow in some way to collect all types of messages from all workers to FPGA_tab?
        if self.is_primary:
            if self.warn:
                save_print("worker '%s': warning!" % self.device_name)
                return [self.device_name] + [sec for i,sec in enumerate(self.boards) if self.warnings[i]]
            else:
                return [sec for i, sec in enumerate(self.boards) if self.warnings[i]]
        else:
            if self.warn:
                save_print("worker '%s': warning!" % self.device_name)
            return []

    def get_changed_channels(self):
        """
        returns dictionary with changed channels.
        notes: disabled since not used at the moment and needs more work/debugging.
               the idea is to give the user a visual feedback when channels are left not default
               after experiment has been run, or when user changes manually.
               but had some issues that was not properly displayed.
               need also to transmit from secondary -> primary.
               at the moment is only transmitted from primary -> blacs_tab in status_end.
        """
        changed = {}
        for key, value in self.final_values.items():
            try:
                if self.front_panel_values[key] != value:
                    print(key, 'changed from', self.front_panel_values[key], 'to', value)
                    changed[key] = value
                    # if this is enabled will show changes between runs, otherwise changes from startup
                    # at startup we could init channels to default values.
                    #self.front_panel_values[key] = value
            except KeyError:
                print(key, 'not in front panel? (ignore)')
                print(self.front_panel_values)
        print('changed channels:', changed)
        return changed

    def shutdown(self):
        if self.sock is not None:
            # TODO: is transition_to_manual called before? to be sure we stop board.
            # stop board
            #send_recv_data(self.sock, to_client_data32(SERVER_STOP, STOP_NOW), SOCK_TIMEOUT)
            send_recv_data(self.sock, SERVER_STOP, SOCK_TIMEOUT)
            # close connection
            send_recv_data(self.sock, SERVER_CLOSE, SOCK_TIMEOUT)
            self.sock.close()
            self.sock = None
        save_print(self.device_name, 'shutdown')
        sleep(0.5)

    def FPGA_get_board_state(self):
        # get full board status
        #save_print('worker: get state')
        if self.simulate:
            save_print("simulated worker: '%s' ok" % (self.device_name))
            return True
        else:
            if self.sock == None: # try to connect
                info = "'%s' get state" % self.device_name
                self.sock = init_connection(info, self.con, reset=True)
                if self.sock is not None:
                    send_config(info, self.sock,
                                reset       = False,
                                bus_rate    = self.bus_rate,
                                config      = self.config,
                                ctrl_in     = self.ctrl_in,
                                ctrl_out    = self.ctrl_out,
                                strb_delay  = self.strb_delay,
                                sync_wait   = self.sync_wait,
                                sync_phase  = self.sync_phase)
            if self.sock == None: # not connected
                save_print("worker: '%s' not connected at %s" % (self.device_name, self.con))
            else:
                result = send_recv_data(self.sock, SERVER_STATUS_FULL, SOCK_TIMEOUT, recv_bytes=FPGA_STATUS_NUM_BYTES_8, output='GET_STATE')
                if result is None:
                    save_print("worker: could not recieve status from server (timeout)")
                else:
                    status = FPGA_status(result)
                    if status.error == FPGA_STATUS_OK:
                        status.show()
                        return True
                    elif status.error == FPGA_STATUS_ENACK:
                        # when server responds with NACK maybe the board is running? or another client connected?
                        # try to get status info during running state
                        # in this case server has closed connection, so we close old connection and try new one
                        # but in order to get old status we do not reset board.
                        save_print("worker: close and reconnect ...")
                        send_recv_data(self.sock, SERVER_CLOSE, SOCK_TIMEOUT)
                        self.sock.close()
                        self.sock = init_connection('get_board_state', self.con, reset=False)
                        if self.sock is None:
                            save_print("worker: received NACK and could not reconnect to server!")
                        else:
                            ctrl = self.get_reg(FPGA_REG_CTRL)
                            if ctrl is None:
                                save_print("worker: received NACK and could not get control bits!")
                            else:
                                result = send_recv_data(self.sock, SERVER_STATUS, SOCK_TIMEOUT, output=None, recv_bytes=get_bytes(SERVER_STATUS_RSP))
                                if result is None:
                                    save_print("worker: received NACK and could not get running status!")
                                else:
                                    if use_prelim_version:
                                        [cmd, self.board_status, self.board_time, self.board_samples, self.board_cycles] = from_client_status(result)
                                    else:
                                        [cmd, self.board_status, self.board_time, self.board_samples] = from_client_status(result)
                                    if (cmd != SERVER_STATUS_RSP) and (cmd != SERVER_STATUS_RSP):
                                        save_print("worker: received NACK and error receive status!")
                                    else:
                                        # print short status info in console
                                        save_print("board control 0x%8x (c.f. 0x%x)" % (ctrl, self.config))
                                        save_print("board status  0x%8x" % (self.board_status))
                                        save_print("board time      %8i" % (self.board_time))
                                        save_print("board samples   %8i" % (self.board_samples))
                                        save_print("board cycles    %8i" % (self.board_cycles))
                            # close connection again to force proper initialization of board
                            send_recv_data(self.sock, SERVER_CLOSE, SOCK_TIMEOUT)
                            self.sock.close()
                            self.sock = None
                    else:
                        save_print("worker: error %d unpacking status from server" % (status.error))
            # return error
            return False

    def FPGA_disconnect(self):
        # close connection
        #save_print('worker: diconnect')
        if self.sock == None: # not connected
            save_print("worker: '%s' already disconnected at %s" % (self.device_name, self.con))
            return False
        else:
            send_recv_data(self.sock, SERVER_CLOSE, SOCK_TIMEOUT)
            self.sock.close()
            self.sock = None
            save_print("worker: '%s' disconnected at %s" % (self.device_name, self.con))
            return True

    def get_reg(self, reg):
        # return register value, None on error
        if not use_prelim_version: return 0 # does not exist there
        if self.simulate:       return 0
        elif self.sock is None: return None
        result = send_recv_data(self.sock,
                                to_client_sr32(SERVER_GET_REG, reg, 0),
                                SOCK_TIMEOUT,
                                recv_bytes=STRUCT_CLIENT_SR32_NUM_BYTES,
                                output='GET_REG')
        if result is None:
            print("get register 0x%x failed!" % (reg))
        elif (len(result) == get_bytes(SERVER_NACK)) and result == SERVER_NACK:
            print("get register 0x%x returned NACK" % (reg))
        elif len(result) != STRUCT_CLIENT_SR32_NUM_BYTES:
            print("get register 0x%x returned %i bytes instead of %i" % (reg, len(result), STRUCT_CLIENT_SR32_NUM_BYTES))
        else:
            try:
                [cmd, reg2, value] = from_client_sr32(result)
                if (cmd != SERVER_GET_REG) or (reg2 != reg):
                    print("get register 0x%x unexpected command '%s' or register 0x%x" % (reg, ','.join(['%02x' % b for b in cmd]), reg2))
                else:
                    print("get register 0x%x value 0x%x (ok)" % (reg, value))
                    return value
            except Exception as e:
                print("get register 0x%x parsing error:" % (reg), e)
        return None

    def set_reg(self, reg, value):
        # write value directly to register
        # returns value if ok, otherwise None
        if not use_prelim_version: return value # does not exist there
        if self.simulate:       return value
        elif self.sock is None: return None
        result = send_recv_data(self.sock,
                                to_client_sr32(SERVER_SET_REG, reg, value),
                                SOCK_TIMEOUT,
                                recv_bytes=STRUCT_CLIENT_SR32_NUM_BYTES,
                                output=None)
        if result is None:
            print("set register 0x%x failed!" % (reg))
        elif (len(result) == get_bytes(SERVER_NACK)) and result == SERVER_NACK:
            print("set register 0x%x returned NACK" % (reg))
        elif len(result) != STRUCT_CLIENT_SR32_NUM_BYTES:
            print("set register 0x%x returned %i bytes instead of %i" % (reg, len(result), STRUCT_CLIENT_SR32_NUM_BYTES))
        else:
            try:
                [cmd, reg2, value2] = from_client_sr32(result)
                if cmd != SERVER_SET_REG:
                    print("set register 0x%x unexpected command '%s'" % (reg, ','.join(['%02x' % b for b in cmd])))
                elif reg2 != reg:
                    print("set register 0x%x != 0x%x " % (reg, reg2))
                elif value2 != value:
                    print("set register 0x%x value 0x%x != 0x%x " % (reg, value2, value))
                else:
                    print("set register 0x%x value 0x%x (ok)" % (reg, value2))
                    return value
            except Exception as e:
                print("set register 0x%x parsing error:" % (reg), e)
        return None

    def onChangeIO(self, value, input):
        "user changed I/O selection in GUI"
        if input:
            type = 'input'
            if self.set_reg(FPGA_REG_CTRL_IN0, value[0]) is None: return
            if self.set_reg(FPGA_REG_CTRL_IN1, value[1]) is None: return
            self.ctrl_in = value
            self.start_trg = is_enabled([STR_TRIG_START], value, input=True)
        else:
            type = 'output'
            if self.set_reg(FPGA_REG_CTRL_OUT0, value[0]) is None: return
            if self.set_reg(FPGA_REG_CTRL_OUT1, value[1]) is None: return
            self.ctrl_out = value
        if use_prelim_version:
            print(MSG_IO_SETTINGS % (self.device_name, type, value[0], value[1], get_io_info(value, input=input)))
        else:
            print(MSG_IO_SETTINGS % (self.device_name, type, value, get_io_info(value, input=input)))
        print(get_io_selection(value, input=input, return_NONE=False))

    def onChangeExtClock(self, state, force=False):
        self.ext_clock = state
        if self.ext_clock:
            self.config |= CTRL_EXT_CLK
            save_print((MSG_EXT_CLOCK % self.device_name) + MSG_ENABLED)
        else:
            self.config &= ~CTRL_EXT_CLK
            save_print((MSG_EXT_CLOCK % self.device_name) + MSG_DISABLED)

    def onChangeIgnoreClockLoss(self, state, force=False):
        self.ignore_clock_loss = state
        if self.ignore_clock_loss:
            self.config &= ~CTRL_ERR_LOCK_EN
            self.error_mask &= ~STATUS_ERR_LOCK
            save_print((MSG_IGNORE_CLOCK_LOSS % self.device_name) + MSG_ENABLED)
        else:
            self.config |= CTRL_ERR_LOCK_EN
            self.error_mask |= STATUS_ERR_LOCK
            save_print((MSG_IGNORE_CLOCK_LOSS % self.device_name) + MSG_DISABLED)

    def onPrint(self, output):
        print(output)

    def onForceOut(self, value):
        if not use_prelim_version: return # does not exist
        print('force output 0x%x' % value)
        self.set_reg(FPGA_REG_FORCE_OUT, value)

    def parse_worker_args(self, worker_args, init=False):
        # set experimental run parameters according to worker_args
        # worker_args = dictionary with worker arguments
        # if init = True then worker_args are from connection table and all local variables are updated.
        # if init = False then worker_args are from experiment script and local variables are not updated.
        # in both cases registers are updated according to worker_args if not already done.
        # when worker_args has a missing entry with respect to last call then register is reset to initial worker_args or default.
        # ATTENTION: worker_args in experiment script (worker_args_ex) take precedence over worker args in connection table
        #            or default values (saved as self.worker_args)!
        #            however self.worker_args is not overwritten and thus can be reverted by not setting parameters in experiment script.
        # possible parameters to be changed:
        # - config:
        #   if not None board configuration for running mode and manual mode
        # - ctrl_in and ctrl_out:
        #   if not None input and output control register
        # - strb_delay:
        #   if not None strobe 0 and strobe 1 timing.
        # - ext_clock:
        #   if True board uses external clock, otherwise internal clock
        # - ignore_clock_loss:
        #   if True secondary board ignores loss of external clock for few cycles (electrical spikes).
        #   if clock loss is permanent, the board does not generate output and gives an error at end.
        #   a message box is displayed indicating the number of clock loss but does not stop.
        # - sync_wait and sync_phase:
        #   waiting time and phase for synchronization
        # - num_cyles:
        #   number of cycles. 0=infinite, 1=default.
        # - inputs and outputs: dictionary with input and output settings.
        #   allows to overwrite individual parameters with respect to connection table or default values.
        # note: STR_SIMULATE is also an option but does not make sense to use it here.

        #print('parse worker args: act', self.worker_args, 'update', worker_args)

        # remove None from worker_args.
        # these are treated as empty entries and we avoid checking for None
        tmp = {}
        for key, value in worker_args.items():
            if value is not None: tmp[key] = value
        worker_args = tmp

        print('parse worker args (%s):' % ('init' if init else 'update'), worker_args)

        if STR_CONFIG in worker_args:
            config = worker_args[STR_CONFIG]
            if config != self.config:
                self.config = config
                self.set_reg(FPGA_REG_CTRL, self.config)
        elif STR_CONFIG in self.worker_args_ex:
            try:
                self.config = self.worker_args[STR_CONFIG]
            except KeyError:
                self.config = self.default_config
            self.set_reg(FPGA_REG_CTRL, self.config)
        if init: self.default_config = self.config

        if STR_INPUTS in worker_args:
            try:
                inputs = self.worker_args[STR_INPUTS]
                inputs.update(worker_args[STR_INPUTS])
            except KeyError:
                inputs = worker_args[STR_INPUTS]
            ctrl_in = get_ctrl_io(inputs, input=True)
            if use_prelim_version:
                if (ctrl_in[0] != self.ctrl_in[0]) or (ctrl_in[1] != self.ctrl_in[1]):
                    self.ctrl_in = ctrl_in
                    self.start_trg = is_enabled([STR_TRIG_START], self.ctrl_in, input=True)
                    self.set_reg(FPGA_REG_CTRL_IN0, self.ctrl_in[0])
                    self.set_reg(FPGA_REG_CTRL_IN1, self.ctrl_in[1])
            else:
                if ctrl_in != self.ctrl_in:
                    self.ctrl_in = ctrl_in
                    self.start_trg = is_enabled([STR_TRIG_START], self.ctrl_in, input=True)
                    self.set_reg(FPGA_REG_CTRL_IN, self.ctrl_in)
        elif STR_INPUTS in self.worker_args_ex:
            try:
                inputs = self.worker_args[STR_INPUTS]
            except KeyError:
                inputs = default_in_prim if self.is_primary else default_in_sec
            self.ctrl_in = get_ctrl_io(inputs, input=True)
            self.start_trg = is_enabled([STR_TRIG_START], self.ctrl_in, input=True)
            if use_prelim_version:
                self.set_reg(FPGA_REG_CTRL_IN0, self.ctrl_in[0])
                self.set_reg(FPGA_REG_CTRL_IN1, self.ctrl_in[1])
            else:
                self.set_reg(FPGA_REG_CTRL_IN, self.ctrl_in)

        if STR_OUTPUTS in worker_args:
            try:
                outputs = self.worker_args[STR_OUTPUTS]
                outputs.update(worker_args[STR_OUTPUTS])
            except KeyError:
                outputs = worker_args[STR_OUTPUTS]
            ctrl_out = get_ctrl_io(outputs, input=False)
            if use_prelim_version:
                if (ctrl_out[0] != self.ctrl_out[0]) or (ctrl_out[1] != self.ctrl_out[1]):
                    self.ctrl_out = ctrl_out
                    self.set_reg(FPGA_REG_CTRL_OUT0, self.ctrl_out[0])
                    self.set_reg(FPGA_REG_CTRL_OUT1, self.ctrl_out[1])
            else:
                if ctrl_oout != self.ctrl_out:
                    self.ctrl_out = ctrl_out
                    self.set_reg(FPGA_REG_CTRL_OUT, self.ctrl_out)
        elif STR_OUTPUTS in self.worker_args_ex:
            try:
                outputs = self.worker_args[STR_OUTPUTS]
            except KeyError:
                outputs = default_out_prim if self.is_primary else default_out_sec
            self.ctrl_out = get_ctrl_io(outputs, input=False)
            if use_prelim_version:
                self.set_reg(FPGA_REG_CTRL_OUT0, self.ctrl_out[0])
                self.set_reg(FPGA_REG_CTRL_OUT1, self.ctrl_out[1])
            else:
                self.set_reg(FPGA_REG_CTRL_OUT, self.ctrl_out)

        if STR_STRB_DELAY in worker_args:
            strb_delay = worker_args[STR_STRB_DELAY]
            if strb_delay != self.strb_delay:
                self.strb_delay = strb_delay
                self.set_reg(FPGA_REG_STRB_DELAY, self.strb_delay)
        elif STR_STRB_DELAY in self.worker_args_ex:
            try:
                self.strb_delay = self.worker_args[STR_STRB_DELAY]
            except KeyError:
                self.strb_delay = STRB_DELAY
            self.set_reg(FPGA_REG_STRB_DELAY, self.strb_delay)

        if STR_EXT_CLOCK in worker_args:
            ext_clock = worker_args[STR_EXT_CLOCK]
            if ext_clock != self.ext_clock:
                self.ext_clock = ext_clock
                if self.ext_clock: self.config |= CTRL_EXT_CLK
                else:              self.config &= ~CTRL_EXT_CLK
                if not self.state_manual:
                    self.set_reg(FPGA_REG_CTRL, self.config)
        elif STR_EXT_CLOCK in self.worker_args_ex:
            try:
                self.ext_clock = self.worker_args[STR_EXT_CLOCK]
            except KeyError:
                self.ext_clock = ((self.default_config & CTRL_EXT_CLK) != 0)
            if self.ext_clock: self.config |= CTRL_EXT_CLK
            else:              self.config &= ~CTRL_EXT_CLK
            if not self.state_manual:
                self.set_reg(FPGA_REG_CTRL, self.config)

        if STR_IGNORE_CLOCK_LOSS in worker_args:
            ignore_clock_loss = worker_args[STR_IGNORE_CLOCK_LOSS]
            if ignore_clock_loss != self.ignore_clock_loss:
                self.ignore_clock_loss = ignore_clock_loss
                if self.ignore_clock_loss: self.config &= CTRL_ERR_LOCK_EN
                else:                      self.config |= CTRL_ERR_LOCK_EN
                self.set_reg(FPGA_REG_CTRL, self.config)
        elif STR_IGNORE_CLOCK_LOSS in self.worker_args_ex:
            try:
                self.ignore_clock_loss = self.worker_args[STR_IGNORE_CLOCK_LOSS]
            except KeyError:
                self.ignore_clock_loss = ((self.default_config & CTRL_ERR_LOCK_EN) == 0)
            if self.ignore_clock_loss: self.config &= CTRL_ERR_LOCK_EN
            else:                      self.config |= CTRL_ERR_LOCK_EN
            self.set_reg(FPGA_REG_CTRL, self.config)

        if STR_SYNC_WAIT in worker_args:
            sync_wait = worker_args[STR_SYNC_WAIT]
            if sync_wait != self.sync_wait:
                self.sync_wait = sync_wait
                self.set_reg(FPGA_REG_SYNC_DELAY, self.sync_wait)
        elif STR_SYNC_WAIT in self.worker_args_ex:
            try:
                self.sync_wait = self.worker_args[STR_SYNC_WAIT]
            except KeyError:
                self.sync_wait = SYNC_WAIT_AUTO
            self.set_reg(FPGA_REG_SYNC_DELAY, self.sync_wait)

        if STR_SYNC_PHASE in worker_args:
            sync_phase = worker_args[STR_SYNC_PHASE]
            if sync_phase != self.sync_phase:
                self.sync_phase = sync_phase
                self.set_reg(FPGA_REG_SYNC_PHASE, self.sync_phase)
        elif STR_SYNC_PHASE in self.worker_args_ex:
            try:
                self.sync_phase = self.worker_args[STR_SYNC_PHASE]
            except KeyError:
                self.sync_phase = SYNC_PHASE_AUTO
            self.set_reg(FPGA_REG_SYNC_PHASE, self.sync_phase)

        if STR_CYCLES in worker_args:
            # this is transmitted in start_run,
            # therefore, we do not need to write into register here.
            self.num_cycles = worker_args[STR_CYCLES]
        elif STR_CYCLES in self.worker_args_ex:
            try:
                self.num_cycles = self.worker_args[STR_CYCLES]
            except KeyError:
                self.num_cycles = CONFIG_CYCLES

        if not init:
            # save updated args to know which to revert if not in file next time
            self.worker_args_ex = worker_args

        #print('parse worker args: done', self.worker_args)

        # return worker_arg with None removed
        return worker_args
