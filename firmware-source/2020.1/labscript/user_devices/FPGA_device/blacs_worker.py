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
    SERVER_OPEN, SERVER_RESET, SERVER_CONFIG, SERVER_CLOSE, SERVER_STATUS,
    SERVER_START, SERVER_WRITE, SERVER_STATUS_RSP, SERVER_STATUS_IRQ_RSP,
    SERVER_STATUS_IRQ, SERVER_STATUS_FULL,
    CONFIG_RUN_64, CONFIG_RUN_96, CONFIG_TRANS, CONFIG_SCAN, CONFIG_CLOCK, CONFIG_CYCLES,
    CONFIG_NUM_BYTES, SYNC_WAIT_AUTO, SYNC_WAIT_PRIM, SYNC_WAIT_SINGLE, SYNC_WAIT_SEC,
    SYNC_PHASE_NONE, SYNC_PHASE_AUTO, SYNC_PHASE_SEC,
    CTRL_AUTO_SYNC_EN, CTRL_AUTO_SYNC_PRIM, CTRL_EXT_CLK,
    get_ctrl_in, get_ctrl_out, default_in_prim, default_out_prim, default_in_sec, default_out_sec,
    STR_CONFIG, STR_CONFIG_MANUAL, STR_INPUTS, STR_OUTPUTS, STR_SIMULATE, STR_CYCLES,
    STR_IGNORE_CLOCK_LOSS, STR_SYNC_PHASE, STR_SYNC_WAIT, STR_EXT_CLOCK,
    MSG_ENABLED, MSG_DISABLED, MSG_EXT_CLOCK, MSG_INPUT_SETTING, MSG_OUTPUT_SETTING,
    MSG_IGNORE_CLOCK_LOSS,
    START_TIME, BIT_NOP_SH,
    is_in_start, is_in_stop, is_trg_restart,
    from_string, get_board_samples,
    get_rack, get_address, get_channel,
    to_client_status, from_client_status, STATUS_SECONDARY_READY,
    TIME_STEP, EVT_TIMEOUT,
    STATUS_EXT_LOCKED, STATUS_RUN, STATUS_END, STATUS_WAIT, STATUS_ERROR, STATUS_ERR_LOCK,
    to_config, from_config, stop_primary_on_secondary_error,
    STRB_DELAY,
    AnalogChannels, DigitalChannels, DDSChannels,
    AnalogOutput, DigitalOutput,
    to_client_data32, get_bytes,
)
from .shared import (
    DDS_CHANNEL_FREQ, DDS_CHANNEL_AMP, DDS_CHANNEL_PHASE,
    ALWAYS_SHOW, MAX_SHOW, show_data,
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
#   if recv_bytes == 0 save_prints 'output' + number of sent bytes
#   if recv_bytes == 2 save_prints 'output' + information if ACK/NACK received
#   if recv_bytes > 2  save_prints 'output' + number of received bytes
def send_recv_data(sock, data, timeout, recv_bytes=2, output=None):
    size = None
    if (data is None) and (recv_bytes > 0):
        #wait for new data
        (rd, wr, err) = select.select([sock], [], [], timeout)
    else:
        #send data
        sock.send(data)
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
        data = sock.recv(recv_bytes)
        #save_print("received %s (%d bytes)" % (str(data), len(data)))
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

def init_connection(device_name, con, config=None, ctrl_trg=0, ctrl_out=0):
    "connect - open - reset - config. returns socket or None on error"
    sock = connect(SOCK_TIMEOUT_SHORT, con)
    if sock is None: save_print("%s: connection %s failed!" % (device_name, con))
    else:
        save_print("%s: connected at %s ok" % (device_name, con))
        # open board
        result = send_recv_data(sock, SERVER_OPEN, SOCK_TIMEOUT_SHORT, output='OPEN')
        if result == SERVER_ACK:
            # reset board
            result = send_recv_data(sock, SERVER_RESET, SOCK_TIMEOUT_SHORT, output='RESET')
            if result == SERVER_ACK:
                if config is not None:
                    # select sync_wait time if primary or secondary board
                    if config & CTRL_AUTO_SYNC_EN:
                        if config & CTRL_AUTO_SYNC_PRIM:
                            sync_wait = SYNC_WAIT_PRIM;
                        else:
                            sync_wait = SYNC_WAIT_SEC;
                    else:
                        sync_wait = SYNC_WAIT_SINGLE;
                    # send configuration. server will return new configuration (no ACK)
                    data = to_config(SERVER_CONFIG,int(CONFIG_CLOCK),int(CONFIG_SCAN),config,ctrl_trg,ctrl_out,CONFIG_CYCLES,CONFIG_TRANS,STRB_DELAY,sync_wait,SYNC_PHASE_NONE)
                    result = send_recv_data(sock, data, SOCK_TIMEOUT_SHORT, recv_bytes=len(data), output='CONFIG')
                    if (result is None):
                        save_print("%s: timeout!" % (device_name))
                    elif (len(result) == CONFIG_NUM_BYTES):
                        [cmd, clock, scan, config, ctrl_trg, ctrl_out, reps, trans, strb_delay, sync_wait, sync_phase] = from_config(result)
                        if cmd != SERVER_CONFIG: save_print('%s: config received %s instead of %s!' % (device_name, str(cmd), str(SERVER_CONFIG)))
                        else:
                            save_print("%s: ready!" % (device_name))
                            return sock
                    elif (len(result) == SERVER_CMD_NUM_BYTES):
                        if result == SERVER_NACK:
                            save_print("%s: NACK received!" % (device_name))
                        else:
                            save_print("%s: unexpected data received:" % (device_name))
                            save_print(result)
                    else:
                        save_print("%s: unexpected data received:" % (device_name))
                        save_print(result)
                else:
                    save_print("%s: ready!" % (device_name))
                    return sock
        #something went wrong. close socket after short timeout
        send_recv_data(sock, SERVER_CLOSE, 0.1, output='close')
        sock.close()
    return None

def send_data(sock, data, bus_rate, config=None, ctrl_trg=0, ctrl_out=0, reset=True, sync_wait=None, sync_phase=None, cycles=1):
    """
    send data to socket.
        sock = socket
        data = 2d numpy array of data with time and one or two data columns
        bus_rate = outbut bus rate in Hz
        config = if not None configuration bits to be sent to board
        reset = if True reset board before sending any data
    returns True if ok otherwise error
    """
    # check input
    if sock is None: return False

    # display data for debugging
    if ALWAYS_SHOW or len(data) <= MAX_SHOW:
        show_data(data)
    else:
        save_print('%i samples' % (len(data)))

    # reset board
    if reset == True:
        result = send_recv_data(sock, SERVER_RESET, SOCK_TIMEOUT, output='RESET')
        if result != SERVER_ACK: return False

    # comfigure board
    if config is not None:
        # select sync_wait time and sync_phase depending if primary or secondary board
        if config & CTRL_AUTO_SYNC_EN:
            if config & CTRL_AUTO_SYNC_PRIM:
                if sync_wait is None: sync_wait = SYNC_WAIT_PRIM
                if sync_phase is None: sync_phase = SYNC_PHASE_NONE
            else:
                if sync_wait is None: sync_wait = SYNC_WAIT_SEC
                if sync_phase is None: sync_phase = SYNC_PHASE_SEC
        else:
            if sync_wait is None: sync_wait = SYNC_WAIT_SINGLE
            if sync_phase is None: sync_phase = SYNC_PHASE_NONE
        config = to_config(SERVER_CONFIG, int(CONFIG_CLOCK), int(CONFIG_SCAN), config, ctrl_trg, ctrl_out, cycles, CONFIG_TRANS, STRB_DELAY, sync_wait, sync_phase)
        result = send_recv_data(sock, config, SOCK_TIMEOUT, recv_bytes=len(config), output='CONFIG')
        if result is None: return False
        if len(result) == CONFIG_NUM_BYTES:
            [cmd, clock, scan, config, ctrl_trg, ctrl_out, reps, trans, strb_delay, sync_wait, sync_phase] = from_config(result)
            if cmd != SERVER_CONFIG:
                save_print('config received (%s) instead of SERVER_CONFIG!' % (str(cmd)))
                return False
        elif (len(result) == SERVER_CMD_NUM_BYTES):
            if result == SERVER_NACK:
                save_print("config NACK received!")
                return False
            else:
                save_print("config unexpected data received:" % (device_name))
                save_print(result)
                return False
        else:
            save_print("config unexpected data received:" % (device_name))
            save_print(result)
            return False
    # write data to board
    num_bytes = len(data)*len(data[0])*4
    result = send_recv_data(sock, to_client_data32(SERVER_WRITE, num_bytes), SOCK_TIMEOUT, output='SEND %d bytes?'%(num_bytes))
    if result != SERVER_ACK: return False
    result = send_recv_data(sock, data.tobytes(order='C'), None, output='SEND %d bytes'%(num_bytes))
    if result != SERVER_ACK: return False
    save_print('%d bytes sent to server!' % (num_bytes))
    return True

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
        self.board_status = None
        self.board_time = 0
        self.board_samples = 0
        self.abort = False
        self.t_start = [0,0]; # start time from transition_to_manual and start_run
        self.final_values = {}
        self.front_panel_values = {}

        # default configuration
        self.config_manual = CONFIG_RUN_96 if (self.num_racks == 2) else CONFIG_RUN_64
        self.error_mask = 0xffff_ffff
        self.start_trg = False
        self.ext_clock = False
        self.ignore_clock_loss = True
        self.sync_wait  = SYNC_WAIT_AUTO
        self.sync_phase = SYNC_PHASE_AUTO
        self.num_cycles = CONFIG_CYCLES
        self.simulate   = False
        if self.is_primary:
            # primary board
            self.config = self.config_manual | CTRL_AUTO_SYNC_EN | CTRL_AUTO_SYNC_PRIM
            self.ctrl_in = get_ctrl_in(default_in_prim)
            self.ctrl_out = get_ctrl_out(default_out_prim)
            if len(self.boards) > 0:
                # secondary boards available
                save_print("init primary board '%s' with %i secondary boards" % (self.device_name, len(self.boards)))
            else:
                # single board
                save_print("init primary board '%s' without secondary boards" % (self.device_name))
        else:
            # secondary board: lock to external clock and wait for trigger
            self.ext_clock = True # external clock is always used
            self.config = self.config_manual | CTRL_AUTO_SYNC_EN | CTRL_EXT_CLK
            self.ctrl_in = get_ctrl_in(default_in_sec)
            self.ctrl_out = get_ctrl_out(default_out_sec)
            save_print("init secondary board '%s'" % (self.device_name))

        # use settings given in worker arguments
        self.parse_worker_args(self.worker_args)

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
            self.sock = init_connection("'%s' init"%self.device_name, self.con, self.config_manual)
        else: self.sock = None
        self.first_time = True

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
                if self.sock is None:  # try to reconnect to device
                    self.sock = init_connection("'%s' prg. manual" % self.device_name, self.con, self.config_manual)

                if self.sock is not None:  # device (re-)connected
                    save_print("'%s' prg. manual (%i channels)" % (self.device_name, len(data)))
                    if send_data(self.sock, np.array(data,dtype=np.uint32), self.bus_rate, self.config_manual) == True:
                        # start output
                        result = send_recv_data(self.sock, to_client_data32(SERVER_START, 1), SOCK_TIMEOUT, output='START')
                        if result == SERVER_ACK:
                            # wait for completion (should be immediate)
                            result = False
                            while result == False:
                                sleep(0.1)
                                result = self.status_monitor(False)[0]
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
        if not self.simulate:
            if self.sock is None: # try to reconnect to device
                self.sock = init_connection("'%s' to buffered"%self.device_name, self.con, self.config_manual)
            if self.sock is None:
                return None

        #if False and self.is_primary: # test uplload table
        #    MOG_test()

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
                save_print('FPGA    control bits 0x%x' % (self.config))
                save_print('input   control bits 0x%x' % (self.ctrl_in))
                save_print('output  control bits 0x%x' % (self.ctrl_out))

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

                    # reset, configure and send data
                    # returns True on success, False on error.
                    if self.simulate:
                        result = True
                        if ALWAYS_SHOW or len(data) <= MAX_SHOW:
                            show_data(np.array(data))
                    else:
                        result = send_data(self.sock, data, self.bus_rate,
                                           config=self.config,
                                           ctrl_trg=self.ctrl_in,
                                           ctrl_out=self.ctrl_out, reset=True,
                                           sync_wait=self.sync_wait, sync_phase=self.sync_phase, cycles=self.num_cycles)
                    t_data = (get_ticks() - self.t_start[0]) * 1e3
                    save_print('config result =', result)
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
                        result = send_recv_data(self.sock, SERVER_STATUS, SOCK_TIMEOUT, output=None,
                                            recv_bytes=get_bytes(SERVER_STATUS_RSP))
                    if result is None:
                        save_print("'%s' could not get status!" % (self.device_name))
                        return None
                    else:
                        [cmd, self.board_status, self.board_time, self.board_samples] = from_client_status(result)
                        if (cmd != SERVER_STATUS_RSP) and (cmd != SERVER_STATUS_RSP):
                            save_print("'%s' error receive status!" % (self.device_name))
                            return None
                        else:
                            if not (self.board_status & STATUS_EXT_LOCKED):  # warning or error state
                                save_print("'%s' required external clock is missing!" % (self.device_name))
                                return None

                    # reset, configure and send data
                    # returns True on success, False on error.
                    if self.simulate:
                        result = True
                        if ALWAYS_SHOW or len(data) <= MAX_SHOW:
                            show_data(np.array(data))
                    else:
                        result = send_data(self.sock, data, self.bus_rate, config=self.config, ctrl_trg=self.ctrl_in,
                                       ctrl_out=self.ctrl_out, reset=True,
                                       sync_wait=self.sync_wait, sync_phase=self.sync_phase, cycles=self.num_cycles)
                        save_print('config result =', result)
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
                    if False:
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
                elif (self.board_samples != self.exp_samples): # note: samples are appended with NOP to have multiple of 4
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
            # secondary boards: unlock from external clock
            data = to_config(SERVER_CONFIG, int(CONFIG_CLOCK), int(CONFIG_SCAN), self.config_manual, self.ctrl_in, self.ctrl_out, CONFIG_CYCLES, CONFIG_TRANS, STRB_DELAY, SYNC_WAIT_SINGLE, SYNC_PHASE_NONE)
            if self.simulate:
                result = data
            else:
                result = send_recv_data(self.sock, data, SOCK_TIMEOUT, recv_bytes=len(data), output='STOP unlock ext. clock')
            if result is None: result = False
            elif len(result) == CONFIG_NUM_BYTES:
                [cmd, clock, scan, config, ctrl_trg, ctrl_out, reps, trans, strb_delay, sync_wait, sync_phase] = from_config(result)
                if cmd != SERVER_CONFIG:
                    save_print("'%s' unlock: received (%s) instead of %s! (%i)" % (self.device_name, str(cmd), str(SERVER_CONFIG), self.count))
                    result = False
                else:
                    save_print("'%s' unlock: ok (%i)" % (self.device_name, self.count))
                    result = all_ok
            elif (len(result) == SERVER_CMD_NUM_BYTES):
                if result == SERVER_NACK:
                    save_print("'%s' unlock: NACK received!" % (self.device_name))
                    result = False
                else:
                    save_print("'%s' unlock: unknown data received!" % (self.device_name))
                    save_print(result)
                    result = False
            else:
                save_print("'%s' unlock: unknown data received!" % (self.device_name))
                save_print(result)
                result = False

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
                    elif (self.board_time > 0) and is_in_stop(self.ctrl_in): # stop state
                        if is_trg_restart(self.ctrl_in):
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
                self.sock = init_connection("'%s' get state"%self.device_name, self.con, self.config_manual)
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

    def onChangeInputs(self, ctrl_trg):
        self.ctrl_in = ctrl_trg
        self.start_trg = is_in_start(ctrl_trg)
        save_print(MSG_INPUT_SETTING % (self.device_name, self.ctrl_in, get_in_info(self.ctrl_in)))

    def onChangeOutputs(self, ctrl_out):
        self.ctrl_out = ctrl_out
        save_print(MSG_OUTPUT_SETTING % (self.device_name, self.ctrl_out, get_out_info(self.ctrl_out)))

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
            
    def parse_worker_args(self, worker_args):
        # set experimental run parameters according to worker_args given in connection table or/and in experiment script
        # ATTENTION: worker_args in experiment script (worker_args_ex) take precedence over worker args in connection table
        #            or default values (saved as self.worker_args)!
        #            however self.worker_args is not overwritten and thus can be reverted by not setting parameters in experiment script.
        # worker_args = dictionary with worker arguments
        # possible parameters to be changed:
        # - config and config_manual:
        #   if not None board configuration for running mode and manual mode
        # - ctrl_in and ctrl_out:
        #   if not None input and output control register
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
        print('parse worker args: act', self.worker_args, 'update', worker_args)
        if len(worker_args) > 0:
            if STR_CONFIG in worker_args and worker_args[STR_CONFIG] is not None:
                self.config = worker_args[STR_CONFIG]
            if STR_CONFIG_MANUAL in worker_args and worker_args[STR_CONFIG_MANUAL] is not None:
                self.config_manual = worker_args[STR_CONFIG_MANUAL]
            if STR_INPUTS in worker_args and worker_args[STR_INPUTS] is not None:
                if STR_INPUTS in self.worker_args and self.worker_args[STR_INPUTS] is not None:
                    inputs = self.worker_args[STR_INPUTS]
                    inputs.update(worker_args[STR_INPUTS])
                else:
                    inputs = worker_args[STR_INPUTS]
                #print('parse_worker_args', inputs)
                self.ctrl_in = get_ctrl_in(inputs)
                #print('worker_args (old)', self.worker_args[STR_INPUTS])
                #print('worker_args (hdf5)', worker_args[STR_INPUTS])
                #print('inputs', inputs)
                #print('ctrl_in 0x%x' % self.ctrl_in)
                self.start_trg = is_in_start(self.ctrl_in)
            if STR_OUTPUTS in worker_args and worker_args[STR_OUTPUTS] is not None:
                if STR_OUTPUTS in self.worker_args and self.worker_args[STR_OUTPUTS] is not None:
                    outputs = self.worker_args[STR_OUTPUTS]
                    outputs.update(worker_args[STR_OUTPUTS])
                else:
                    outputs = worker_args[STR_OUTPUTS]
                self.ctrl_out = get_ctrl_out(outputs)
            if STR_EXT_CLOCK in worker_args and worker_args[STR_EXT_CLOCK] is not None:
                self.ext_clock = worker_args[STR_EXT_CLOCK]
            if STR_IGNORE_CLOCK_LOSS in worker_args and worker_args[STR_IGNORE_CLOCK_LOSS] is not None:
                self.ignore_clock_loss = worker_args[STR_IGNORE_CLOCK_LOSS]
            if STR_SYNC_WAIT in worker_args and worker_args[STR_SYNC_WAIT] is not None:
                self.sync_wait = worker_args[STR_SYNC_WAIT]
            if STR_SYNC_PHASE in worker_args and worker_args[STR_SYNC_PHASE] is not None:
                self.sync_phase = worker_args[STR_SYNC_PHASE]
            if STR_CYCLES in worker_args and worker_args[STR_CYCLES] is not None:
                self.num_cycles = worker_args[STR_CYCLES]
            if STR_SIMULATE in worker_args and worker_args[STR_SIMULATE] is not None:
                self.simulate = worker_args[STR_SIMULATE]
        #print('parse worker args: done', self.worker_args)
