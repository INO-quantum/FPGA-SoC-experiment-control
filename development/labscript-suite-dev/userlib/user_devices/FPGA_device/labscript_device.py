#####################################################################
# labscript_device for FPGA-SoC device by Andreas Trenkwalder
# works as PseudoClockDevice
# created 6/4/2021
# last change 01/07/2024 by Andi
#####################################################################

import numpy as np
from time import sleep
from time import perf_counter as get_ticks
from time import process_time as get_ticks2
import struct

from labscript import (
    PseudoclockDevice, Pseudoclock, ClockLine, IntermediateDevice,
    Output, DigitalQuantity, AnalogQuantity, DDSQuantity, Trigger,
    set_passed_properties, LabscriptError, config,
    add_time_marker,
    )
from labscript_utils.setup_logging import setup_logging
from labscript_utils import import_or_reload
from labscript_utils.unitconversions import get_unit_conversion_class

from .shared import (
    reset_all, use_prelim_version,
    PRIMARY_IP, SECONDARY_IP, DEFAULT_PORT,
    SOCK_TIMEOUT, SOCK_TIMEOUT_SHORT,
    TYPE_board, TYPE_AO, TYPE_DO, TYPE_DDS, TYPE_SP,
    PROP_UNIT, PROP_MIN, PROP_MAX, PROP_STEP, PROP_DEC,
    PROP_UNIT_V, PROP_UNIT_A, PROP_UNIT_MHZ, PROP_UNIT_DBM, PROP_UNIT_DEGREE,
    DDS_CHANNEL_FREQ, DDS_CHANNEL_AMP, DDS_CHANNEL_PHASE,
    ALWAYS_SHOW, MAX_SHOW, show_data,
    CRC_CHECK, CRC, BACK_CONVERT,
    ADD_WORKER, AO_NAME, DO_NAME, DDS_NAME, FPGA_NAME,
    MAX_FPGA_RATE, MAX_RACKS,
    DATA_BITS, ADDR_BITS, ADDR_SHIFT, ADDR_MAX, ADDR_MASK, ADDR_MASK_SH, DATA_MASK, DATA_ADDR_MASK,
    BIT_NOP, BIT_NOP_SH,
    BIT_IRQ, BIT_IRQ_SH,
    BIT_STRB, BIT_STRB_SH, BIT_STRB_MASK, BIT_STRB_GENERATE,
    BIT_STOP, BIT_STOP_SH, BIT_TRST,
    SPECIAL_BITS,
    SP_INVALID_VALUE, DO_INVALID_VALUE, DO_DEFAULT_VALUE,
)

from .in_out import (
    get_ctrl_io, get_io_selection,
    STR_BIT_NOP, STR_BIT_STRB,
    STR_TRIG_START, STR_TRIG_STOP, STR_TRIG_RESTART,
    STR_SYNC_OUT, STR_INV,
    STR_INPUT_0, STR_INPUT_1, STR_INPUT_2,
    STR_OUTPUT_0, STR_OUTPUT_1, STR_OUTPUT_2,
    STR_LED_R, STR_LED_G, STR_LED_B,
    STR_FALLING, STR_RISING,
)

if use_prelim_version == False:
    from labscript import AnalogOut
    from .in_out import (
        STR_BIT_DATA_20_23, STR_BIT_DATA_24_27, STR_BIT_DATA_28_31,
        STR_BIT_OFFSET_0, STR_BIT_OFFSET_1, STR_BIT_OFFSET_2, STR_BIT_OFFSET_3,
        STR_LEVEL_HIGH,
    )

from .DAC import AnalogOutput
from .DDS_generic import DDS_generic

import h5py, labscript_utils.h5_lock

# reduce number of log entries in logfile (labscript-suite/logs/BLACS.log)
import logging
log_level = [logging.CRITICAL, logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG, logging.NOTSET][2]

# every time after compiling connection table I get strange BrokenPipeError for any print command within FPGA_Tab!?
# sometimes crashes so badly that BLACS cannot be closed anymore and have to manually kill it! this is super annoying.
# implement a save_print command and use everywhere!
def save_print(*args):
    try:
        print(*args)
    except BrokenPipeError:
        pass

def epsilon(number):
    """
    returns smallest epsilon for which number + epsilon != number.
    note: sys.float_info.epsilon == epsilon(1.0)
    """
    e = number
    while(number + e != number):
        e /= 2
    return 2*e

# clock resolution and limit calculated from bus_rate for intermediate devices.
# bus_rate is the maximum data output rate in Hz on the bus.
# times are rounded to nearest integer multiple of clock_resolution in quantise_to_pseudoclock in labscript.py.
# time deltas dt are checked vs. dt < 1/clock_line.clock_limit in collect_change_times in labscript.py.
# we add epsilon(MAX_TIME) to clock_limit to avoid that small numberical errors cause problems.
def get_clock_resolution(bus_rate):
    return 1.0 / bus_rate
def get_clock_limit(bus_rate):
    return 1.0 / (1.0 / bus_rate - 2.0 * epsilon(MAX_TIME_SECONDS))
DEFAULT_BUS_RATE = 1e6
MAX_TIME         = (2**32)-1
MAX_TIME_SECONDS = MAX_TIME*get_clock_resolution(DEFAULT_BUS_RATE)

# smallest time step and start time in WORD units (ticks)
TIME_STEP       = 1                         # must be 1
START_TIME      = 0                         # note: FPGA board can start at time 0 since trigger delay is corrected.
TIME_ROUND_DECIMALS = 10                    # time is rounded internally by labscript to 10 decimals = 100ps
TIME_PRECISION  = 10.0**(-TIME_ROUND_DECIMALS) # time round precision in seconds
UPDATE_TIME_MS  = 500                       # update time of BLACS board status in ms

def prefix(value, unit=""):
    "returns smallest prefix G,M,k for given integer value"
    s = "%i" % (value)
    for i in range(len(s)):
        if (s[len(s) - i - 1] != '0'):
            #print([value, s, i])
            if i >= 9: return s[:-9] + "G" + unit
            if i >= 6: return s[:-6] + "M" + unit
            if i >= 3: return s[:-3] + "k" + unit
            return s + unit

# TODO: using times*self.bus_rate)+0.5 works if initial time is integer multiple of 1/self.bus_rate.
#      numpy.round() seems to be the better choice. but this needs further testing for different rates!
# delta = data[:, 0] = (np.array(times) * self.bus_rate).round(self.digits).astype(dtype=np.uint32)
def time_to_word(times, bus_rate, digits):
    return (np.array(times) * bus_rate).round(digits).astype(dtype=np.uint32)

def word_to_time(times, bus_rate):
    return np.array(times) / bus_rate

# default analog and digital output properties
# these define the capabilities of the analog outputs after unit conversion, i.e. in the base unit 'V'.
default_ao_props = {PROP_UNIT:PROP_UNIT_V, PROP_MIN:-10.0, PROP_MAX:10.0, PROP_STEP:0.1, PROP_DEC:4}
default_do_props = {'xcolor':'red'}

# DDS channel properties
default_DDS_props = {DDS_CHANNEL_FREQ  : {PROP_UNIT: PROP_UNIT_MHZ,    PROP_MIN: 0.0,    PROP_MAX: 1000.0, PROP_STEP: 1.0, PROP_DEC: 6},
                     DDS_CHANNEL_AMP   : {PROP_UNIT: PROP_UNIT_DBM,    PROP_MIN: -60.0,  PROP_MAX: 20.0,   PROP_STEP: 1.0, PROP_DEC: 3},
                     DDS_CHANNEL_PHASE : {PROP_UNIT: PROP_UNIT_DEGREE, PROP_MIN: -180.0, PROP_MAX: 180.0,  PROP_STEP: 10,  PROP_DEC: 3}
                    }

# if True then primary board returns error also when a secondary board is in error state. default = False.
stop_primary_on_secondary_error = False

# tests (use only for testing!)
TEST_TIMING_ERROR       = False             # induce timing error at half of data
TEST_PRIM               = None              # True = primary board, False = secondary board(s), None = all boards

# timeout for interprocess communication wait event
EVT_TIMEOUT     = 5000

# calculation time counter
total_time = None

if use_prelim_version:
    # primary and secondary board default input settings.
    # these settings are added to worker_args for primary and secondary boards.
    default_in_prim = {}
    default_in_sec  = {STR_TRIG_START: 'input 0 falling'}
    # primary and secondary board default output settings.
    # these settings are added to worker_args for primary and secondary boards.
    default_out_prim = {STR_OUTPUT_0   : STR_SYNC_OUT + STR_INV,
                        STR_LED_R   : 'error',
                        STR_LED_G   : 'run',
                        STR_LED_B   : 'ext clock locked'}
    default_out_sec  = {STR_LED_R   : 'error',
                        STR_LED_G   : 'run',
                        STR_LED_B   : 'ext clock locked'}
else:
    # primary and secondary board default input settings.
    # these settings are added to worker_args for primary and secondary boards.
    # TODO: at the moment these bits are hard-coded in firmware. so changing them here does not make sense.
    # do not change 'NOP bit' since it is used by driver on board to add 0 data. all data with this bit set is ignored by board.
    # 'STRB bit' and 'start trigger' can be overwritten in connection_table, in GUI or in experiment script.
    # if 'STRB bit' is set to 'None' output is always generated regardless if strobe bit toggles or not.
    # 'STRB bit' might be ignored by firmware. 'STOP bit' and 'IRQ bit' must be enabled for firmware to take into account.
    default_in_prim = {STR_BIT_NOP: (STR_BIT_DATA_28_31, STR_BIT_OFFSET_3),
                       STR_BIT_STRB: (STR_BIT_DATA_20_23, STR_BIT_OFFSET_3)}
    default_in_sec = {STR_BIT_NOP: (STR_BIT_DATA_28_31, STR_BIT_OFFSET_3),
                      STR_BIT_STRB: (STR_BIT_DATA_20_23, STR_BIT_OFFSET_3),
                      STR_TRIG_START: (STR_INPUT_0, STR_FALLING)}
    # primary and secondary board default output settings
    # these settings are added to worker_args for primary and secondary boards.
    # all settings here can be overwritten in connection_table, in GUI or in experiment script.
    default_out_prim = {'output 0':('sync out',STR_LEVEL_HIGH)}
    default_out_sec  = {}

def make_cmd(command, size):
    "return SERVER_CMD from command and size as bytes array"
    server_cmd = (size & 0x3ff) | ((command & 0x3f) << 10)
    return bytes([server_cmd & 0xff, (server_cmd >> 8) & 0xff])

def get_bytes(server_cmd):
    "returns bytes from server_cmd"
    value = int.from_bytes(server_cmd[0:2],"little")
    return value & 0x3ff

#server commands (2 bytes: [command,size of data in bytes including command])
SERVER_ACK                  = make_cmd(0x01,  2)
SERVER_NACK                 = make_cmd(0x02,  2)
SERVER_RESET                = make_cmd(0x03,  2)
SERVER_OPEN                 = make_cmd(0x20,  2)
SERVER_CLOSE                = make_cmd(0x24,  2)
if use_prelim_version:
    SERVER_CONFIG           = make_cmd(0x25, 50)
else:
    SERVER_CONFIG           = make_cmd(0x25, 42)
SERVER_WRITE                = make_cmd(0x27,  6)
SERVER_START                = make_cmd(0x28,  6)
SERVER_STOP                 = make_cmd(0x29,  2)
SERVER_STATUS               = make_cmd(0x08,  2)        # polls actual status
SERVER_STATUS_IRQ           = make_cmd(0x09, 2)         # allows to wait for update/end instead of polling
SERVER_STATUS_FULL          = make_cmd(0x07,  2)        # full status information displayed in board console
if use_prelim_version:
    SERVER_STATUS_RSP       = make_cmd(0x08, 18)        # response: SERVER_STATUS
    SERVER_STATUS_IRQ_RSP   = make_cmd(0x09, 18)        # response: SERVER_STATUS_IRQ
    SERVER_STATUS_FULL_RSP_8  = make_cmd(0x07,182)      # response: full status  8 bytes per samples
    SERVER_STATUS_FULL_RSP_12 = make_cmd(0x07,186)      # response: full status 12 bytes per samples
else:
    SERVER_STATUS_RSP       = make_cmd(0x08, 14)        # response: SERVER_STATUS
    SERVER_STATUS_IRQ_RSP   = make_cmd(0x09, 14)        # response: SERVER_STATUS_IRQ
    SERVER_STATUS_FULL_RSP_8  = make_cmd(0x07,274)      # response: full status  8 bytes per samples
    SERVER_STATUS_FULL_RSP_12 = make_cmd(0x07,278)      # response: full status 12 bytes per samples
SERVER_SET_SYNC_PHASE       = make_cmd(0x0c,  6)        # set sync phase. struct client_data32
if use_prelim_version:
    SERVER_GET_REG          = make_cmd(0x0a, 10)        # get register. struct client_sr32
    SERVER_SET_REG          = make_cmd(0x0b, 10)        # set register. struct client_sr32
    SERVER_SET_EXT_CLOCK    = make_cmd(0x0c, 6)         # set external clock, struct cliend_data32
else:
    SERVER_GET_REG = None
    SERVER_SET_REG = None
    SERVER_GET_INFO         = make_cmd(0x0d,  2)        # get info
    SERVER_GET_INFO_RSP     = make_cmd(0x0d, 10)        # response get info: struct client_data64

# number of bytes per standard server command (should be 2)
SERVER_CMD_NUM_BYTES = struct.calcsize('<2s')

#return packed bytes to configure server (SERVER_CONFIG)
if use_prelim_version:
    CONFIG_STRUCT_FORMAT = '<2s12I';
    CONFIG_NUM_BYTES = struct.calcsize(CONFIG_STRUCT_FORMAT)

    def to_config(
            cmd,            # in_out 16bit: must be SERVER_CONFIG
            clock_Hz,       # in_out 32bit: in: external clock frequency in Hz (unused if internal clock used), out: actual used clock frequency in Hz
            scan_Hz,        # in_out 32bit: in: requested scan rate in Hz, out: actual scan rate in Hz
            config,         # in_out 32bit: in: configuration bits for DIO24_IOCTL_SET_CONFIG, out: old configuration bits
            ctrl_in,        # input  32bit: in: input configuration register [0,1]
            ctrl_out,       # input  32bit: in: output configuration register [0, 1]
            reps,           # input  32bit: number of repetitions. 0=infinite, 1=default.
            trans,          # input  32bit: number of samples
            strb_delay,     # input  32bit: if not 0 strobe delay of both strobe signals
            sync_wait,      # input  32bit: if not SYNC_WAIT_AUTO, wait time in cycles after trigger sent/received
            sync_phase      # input  32bit: if not SYNC_PHASE_AUTO, {ext,det} phase.
            ):
        return struct.pack(CONFIG_STRUCT_FORMAT, cmd, int(clock_Hz), int(scan_Hz), config, ctrl_in[0], ctrl_in[1], ctrl_out[0], ctrl_out[1], reps, trans, strb_delay, sync_wait, sync_phase)
else:
    CONFIG_STRUCT_FORMAT = '<2s10I';
    CONFIG_NUM_BYTES = struct.calcsize(CONFIG_STRUCT_FORMAT)


    def to_config(
            cmd,            # in_out 16bit: must be SERVER_CONFIG
            clock_Hz,       # in_out 32bit: in: external clock frequency in Hz (unused if internal clock used), out: actual used clock frequency in Hz
            scan_Hz,        # in_out 32bit: in: requested scan rate in Hz, out: actual scan rate in Hz
            config,         # in_out 32bit: in: configuration bits for DIO24_IOCTL_SET_CONFIG, out: old configuration bits
            ctrl_trg,       # input  32bit: in: trigger configuration bits, see
            ctrl_out,       # input  32bit: in: output configuration bits, see
            reps,           # input  32bit: number of repetitions. 0=infinite, 1=default.
            trans,          # input  32bit: number of samples
            strb_delay,     # input  32bit: if not 0 strobe delay of both strobe signals
            sync_wait,      # input  32bit: if not SYNC_WAIT_AUTO, wait time in cycles after trigger sent/received
            sync_phase      # input  32bit: if not SYNC_PHASE_AUTO, {ext,det} phase.
            ):
        return struct.pack(CONFIG_STRUCT_FORMAT, cmd, int(clock_Hz), int(scan_Hz), config, ctrl_trg, ctrl_out, reps, trans, strb_delay, sync_wait, sync_phase)

#returns unpacked bytes from server into server configuration data (SERVER_CONFIG). for data see to_config.
def from_config(bytes):
    #save_print('unpack', bytes)
    return struct.unpack(CONFIG_STRUCT_FORMAT, bytes)

#return packed bytes with client_data32 structure
def to_client_data32(
        cmd,            # in_out 16bit: command
        data32          # in_out 32bit: data
        ):
    return struct.pack('<2sI', cmd, data32)

#returns unpacked bytes with client_sr32 structure from server [cmd, reg32, data32]
STRUCT_CLIENT_SR32_FORMAT = '<2s2I'
STRUCT_CLIENT_SR32_NUM_BYTES = struct.calcsize(STRUCT_CLIENT_SR32_FORMAT)
def from_client_sr32(bytes):
    return struct.unpack(STRUCT_CLIENT_SR32_FORMAT, bytes)
    
#return packed bytes with client_sr32 structure
def to_client_sr32(
        cmd,            # in_out 16bit: command
        reg32,          # in_out 32bit: register
        data32          # in_out 32bit: value
        ):
    return struct.pack(STRUCT_CLIENT_SR32_FORMAT, cmd, reg32, data32)

#returns unpacked bytes with client_data32 structure from server [cmd, data32]
def from_client_data32(bytes):
    return struct.unpack('<2sI', bytes)

#returns unpacked bytes with client_status structure from server:
# 16bit: command, must be SERVER_STATUS_RSP or SERVER_STATUS_IRQ_RSP
# 32bit: FPGA status register bits
# 32bit: board_time
# 32bit: board_samples
if use_prelim_version:
    # 32bit: board_cycles
    def from_client_status(bytes):
        return struct.unpack('<2s4I', bytes)

    # inverse of from_client_status
    def to_client_status(cmd, board_status, board_time, board_samples, board_cycles):
        return struct.pack('<2s4I', cmd, board_status, board_time, board_samples, board_cycles)
else:
    def from_client_status(bytes):
        return struct.unpack('<2s3I', bytes)

    # inverse of from_client_status
    def to_client_status(cmd, board_status, board_time, board_samples):
        return struct.pack('<2s3I', cmd, board_status, board_time, board_samples)

# worker arguments
STR_CONFIG              = 'config'
STR_INPUTS              = 'inputs'
STR_OUTPUTS             = 'outputs'
STR_EXT_CLOCK           = 'ext_clock'
STR_IGNORE_CLOCK_LOSS   = 'ignore_clock_loss'
STR_SYNC_WAIT           = 'sync_wait'
STR_SYNC_PHASE          = 'sync_phase'
STR_STRB_DELAY          = 'strb_delay'
STR_CYCLES              = 'num_cycles'
STR_SIMULATE            = 'simulate'
worker_args_keys = [STR_CONFIG, STR_INPUTS, STR_OUTPUTS,
                    STR_EXT_CLOCK, STR_IGNORE_CLOCK_LOSS,
                    STR_SYNC_WAIT, STR_SYNC_PHASE, STR_STRB_DELAY,
                    STR_CYCLES,
                    STR_SIMULATE]

# other
STR_ALLOW_CHANGES       = 'allow_changes'

# messages
MSG_QUESTION                = "?"
MSG_DISABLE                 = " disable"
MSG_ABORTED                 = " aborted!"
MSG_ENABLED                 = " enabled!"
MSG_DISABLED                = " disabled!"
MSG_DONE                    = " done!"
MSG_IGNORE_CLOCK_LOSS       = "board '%s' ignore clock loss"
MSG_SYNC_OUT                = "board '%s' sync out"
MSG_START_TRG               = "board '%s' start trigger"
MSG_STOP_TRG                = "board '%s' stop trigger"
MSG_RESTART_TRG             = "board '%s' restart trigger"
MSG_EXT_CLOCK               = "board '%s' external clock"
if use_prelim_version:
    MSG_IO_SETTINGS         = "board '%s' %s settings 0x[%x,%x] %s"
else:
    MSG_IO_SETTINGS         = "board '%s' %s settings 0x%x %s"
QUESTION_IGNORE_CLOCK_LOSS  = "Do you really want to ignore clock loss on board '%s'? Attention: the timing between several boards might get out of sync!"
QUESTION_SYNC_OUT           = "Do you really want to disable sync out signal of board '%s'? Attention: secondary boards will not get triggered!"
QUESTION_START_TRG          = "Do you really want to disable external trigger for board '%s'? Attention: the timing between the boards will be undefined!"
QUESTION_EXT_CLOCK          = "Do you really want to disable external clock for board '%s'? Attention: the timing between the boards will be undefined!"

# FPGA register addresses
REG_BYTES                   = 4               # multiplicator for register offsets = 4 bytes per register
if use_prelim_version:
    # control register
    FPGA_REG_CTRL               = ( 0*REG_BYTES)  # index of control register
    FPGA_REG_CTRL_IN0           = ( 4*REG_BYTES)  # index of input control register 0
    FPGA_REG_CTRL_IN1           = ( 5*REG_BYTES)  # index of input control register 1
    FPGA_REG_CTRL_OUT0          = ( 8*REG_BYTES)  # index of output control register 0
    FPGA_REG_CTRL_OUT1          = ( 9*REG_BYTES)  # index of output control register 1
    FPGA_REG_CLK_DIV            = (12*REG_BYTES)  # index of clk_div register
    FPGA_REG_STRB_DELAY         = (13*REG_BYTES)  # index of strb_delay register
    FPGA_REG_NUM_SAMPLES        = (16*REG_BYTES)  # index of number of samples register
    FPGA_REG_NUM_CYCLES         = (17*REG_BYTES)  # index of number of cycles register
    FPGA_REG_SYNC_DELAY         = (24*REG_BYTES)  # index of sync_delay register
    FPGA_REG_SYNC_PHASE         = (25*REG_BYTES)  # index of sync_phase register
    FPGA_REG_FORCE_OUT          = (30*REG_BYTES)  # index of force_out register
    # status register
    FPGA_REG_STATUS             = (32*REG_BYTES)  # index of status register
    FPGA_REG_BOARD_TIME_0       = (36*REG_BYTES)  # index of board time 0 register
    FPGA_REG_BOARD_TIME_1       = (37*REG_BYTES)  # index of board time 1 register
    FPGA_REG_SYNC_TIME          = (38*REG_BYTES)  # index of sync time register
    FPGA_REG_BOARD_SAMPLES_0    = (40*REG_BYTES)  # index of board samples 0 register
    FPGA_REG_BOARD_SAMPLES_1    = (41*REG_BYTES)  # index of board samples 1 register
    FPGA_REG_BOARD_CYCLES       = (44*REG_BYTES)  # index of board cycles register
    FPGA_REG_BUS_INFO           = (48*REG_BYTES)  # index of bus_info = {NUM_BUS_EN,NUM_STRB,BUS_ADDR_BITS,BUS_DATA_BITS}
    FPGA_REG_VERSION            = (60*REG_BYTES)  # index of version register
    FPGA_REG_INFO               = (61*REG_BYTES)  # index of info regiser
else:
    # control register
    FPGA_REG_CTRL               = ( 0*REG_BYTES)  # index of control register
    FPGA_REG_CTRL_IN0           = ( 1*REG_BYTES)  # index of input control register 0
    FPGA_REG_CTRL_IN1           = ( 2*REG_BYTES)  # index of input control register 1
    FPGA_REG_CTRL_OUT0          = ( 3*REG_BYTES)  # index of output control register 0
    FPGA_REG_CTRL_OUT1          = ( 4*REG_BYTES)  # index of output control register 1
    FPGA_REG_CLK_DIV            = ( 7*REG_BYTES)  # index of clk_div register
    FPGA_REG_STRB_DELAY         = ( 8*REG_BYTES)  # index of strb_delay register
    FPGA_REG_NUM_SAMPLES        = ( 5*REG_BYTES)  # index of number of samples register
    FPGA_REG_NUM_CYCLES         = ( 6*REG_BYTES)  # index of number of cycles register
    FPGA_REG_SYNC_DELAY         = ( 9*REG_BYTES)  # index of sync_delay register
    FPGA_REG_SYNC_PHASE         = (10*REG_BYTES)  # index of sync_phase register
    # status register
    FPGA_REG_STATUS             = (11*REG_BYTES)  # index of status register
    FPGA_REG_BOARD_TIME_0       = (12*REG_BYTES)  # index of board time 0 register
    FPGA_REG_BOARD_TIME_1       = (14*REG_BYTES)  # index of board time 1 register
    FPGA_REG_SYNC_TIME          = (17*REG_BYTES)  # index of sync time register
    FPGA_REG_BOARD_SAMPLES_0    = (13*REG_BYTES)  # index of board samples 0 register
    FPGA_REG_BOARD_SAMPLES_1    = (15*REG_BYTES)  # index of board samples 1 register
    FPGA_REG_BOARD_CYCLES       = (16*REG_BYTES)  # index of board cycles register
    FPGA_REG_VERSION            = (18*REG_BYTES)  # index of version register
    FPGA_REG_INFO               = (19*REG_BYTES)  # index of info regiser
    # not existing registers
    FPGA_REG_FORCE_OUT = None

# FPGA control register bits
CTRL_RESET                  = 1<<0           # reset enabled (not settable by user)
CTRL_READY                  = 1<<1           # server ready (not settable by user)
CTRL_RUN                    = 1<<2           # run enabled (not settable by user)
CTRL_RESTART_EN             = 1<<4           # automatic restart
CTRL_AUTO_SYNC_EN           = 1<<5           # auto-sync enabled: use to sync boards with start trigger
CTRL_AUTO_SYNC_PRIM         = 1<<6           # auto-sync primary board
CTRL_BPS96                  = 1<<8           # data format 0=64bits/sample (default), 1=96bits/sample
CTRL_BPS96_BRD              = 1<<9           # data+address selection if DIO_CTRL_BPS96=1: 0=2nd 32bit, 1=3rd 32bit (time=1st 32bit)
CTRL_EXT_CLK                = 1<<10          # 0/1=use internal/external clock
CTRL_ERR_LOCK_EN            = 1<<15          # enable error lock lost
CTRL_IRQ_EN                 = 1<<20          # FPGA all irq's enabled
CTRL_IRQ_END_EN             = 1<<21          # FPGA end irq enabled
CTRL_IRQ_RESTART_EN         = 1<<22          # FPGA restart irq enabled
CTRL_IRQ_FREQ_EN            = 1<<23          # FPGA irq with DIO_IRQ_FREQ enabled
CTRL_IRQ_DATA_EN            = 1<<24          # FPGA irq with DIO_BIT_IRQ enabled

# combined control bits
CONFIG_RUN_64               = CTRL_IRQ_EN|CTRL_IRQ_END_EN|CTRL_IRQ_FREQ_EN|CTRL_ERR_LOCK_EN
CONFIG_RUN_RESTART_64       = CONFIG_RUN_64|CTRL_IRQ_RESTART_EN|CTRL_RESTART_EN
CONFIG_RUN_96               = CONFIG_RUN_64|CTRL_BPS96
CONFIG_RUN_RESTART_96       = CONFIG_RUN_RESTART_64|CTRL_BPS96

# mask of control bits in manual mode: no auto-sync, no external clock, no restart
CONFIG_MANUAL_MASK          = CONFIG_RUN_96

# FPGA status register bits
STATUS_RESET                = 1<<0           # reset active
STATUS_READY                = 1<<1           # ready state = first data received & not end
STATUS_RUN                  = 1<<2           # running state
STATUS_END                  = 1<<3           # end state = num_samples reached
STATUS_WAIT                 = 1<<4           # wait for restart trigger
STATUS_AUTO_SYNC            = 1<<5           # auto-sync active
STATUS_AS_TIMEOUT           = 1<<6           # auto-sync timeout
STATUS_PS_ACTIVE            = 1<<7           # phase shift active
STATUS_TX_FULL              = 1<<8           # TX FIFO full
STATUS_RX_FULL              = 1<<9           # RX FIFO full
STATUS_EXT_USED             = 1<<10          # 0/1=internal/external clock is used
STATUS_EXT_LOCKED           = 1<<11          # external clock is locked
STATUS_ERR_TX               = 1<<12          # error TX timeout loading of data
STATUS_ERR_RX               = 1<<13          # error RX not ready
STATUS_ERR_TIME             = 1<<14          # error timing
STATUS_ERR_LOCK             = 1<<15          # error lock lost
STATUS_ERR_TKEEP            = 1<<16          # error tkeep signal
if use_prelim_version == False:
    STATUS_ERR_TKEEP2           = 1<<17          # error tkeep signal
    STATUS_ERR_TKEEP3           = 1<<18          # error tkeep signal
STATUS_IRQ_FPGA_ERR         = 1<<20          # FPGA error irq
STATUS_IRQ_FPGA_END         = 1<<21          # FPGA end irq
STATUS_IRQ_FPGA_RESTART     = 1<<22          # FPGA restart irq
STATUS_IRQ_FPGA_FREQ        = 1<<23          # FPGA IRQ_FREQ
STATUS_IRQ_FPGA_DATA        = 1<<24          # FPGA IRQ_DATA
STATUS_BTN_0                = 1<<30          # button 0
STATUS_BTN_1                = 1<<31          # button 1

# combined status bits
if use_prelim_version:
    STATUS_ERROR        = STATUS_ERR_TX|STATUS_ERR_RX|STATUS_ERR_TIME|STATUS_ERR_LOCK|STATUS_ERR_TKEEP
else:
    STATUS_ERROR        = STATUS_ERR_TX | STATUS_ERR_RX | STATUS_ERR_TIME | STATUS_ERR_LOCK | STATUS_ERR_TKEEP | STATUS_ERR_TKEEP2 | STATUS_ERR_TKEEP3
STATUS_SECONDARY_READY  = STATUS_READY | STATUS_AUTO_SYNC | STATUS_EXT_USED | STATUS_EXT_LOCKED

# TODO: maybe merge with parse_worker_args
def check_worker_args(worker_args):
    "checks if valid worder_args are given"
    for key,value in worker_args.items():
        if key not in worker_args_keys:
            raise LabscriptError("worker_arg '%s' is not allowed!" % (key))
        if key == STR_CONFIG:
            if not isinstance(value, integer):
                raise LabscriptError("worker_arg '%s':'%s' must be an integer! but is %s" % (key, str(value), type(value)))
            if (value & CTRL_USER_MASK) != 0:
                raise LabscriptError("worker_arg '%s':0x%x is invalid!" % (key, value))
        elif key == STR_INPUTS:
            if isinstance(value, dict):
                ctrl_in = get_ctrl_io(value, input=True)
            else:
                selection = get_io_selection(value, input=True, return_NONE=False)
        elif key == STR_OUTPUTS:
            if isinstance(value, dict):
                ctrl_out = get_ctrl_io(value, input=False)
            else:
                selection = get_io_selection(value, input=False, return_NONE=False)
        elif (key == STR_EXT_CLOCK) or (key == STR_IGNORE_CLOCK_LOSS) or (key == STR_SIMULATE):
            if not isinstance(value, bool):
                raise LabscriptError("worker_arg '%s':'%s' must be True/False (bool)! but is %s" % (key, str(value), type(value)))
        elif (key == STR_SYNC_WAIT) or (key == STR_SYNC_PHASE) or (key == STR_CYCLES) or (key == STR_STRB_DELAY):
            if not isinstance(value, int):
                raise LabscriptError("worker_arg '%s':'%s' must be an integer! but is %s" % (key, str(value), type(value)))
        else:
            raise LabscriptError("error worker_arg '%s'!" % (key))

# configuration bits
CONFIG_CLOCK        = 100e6                 # 100MHz, internal FPGA rate. not used at the moment
CONFIG_SCAN         = 1e6                   # 1MHz, requested sampling rate. overwritten by FPGA_board.bus_rate
CONFIG_CYCLES       = 1                     # cycles=repetitions, 0=infite, 1=default. needs CTRL_RESTART_EN bit to enable cycling mode.
CONFIG_TRANS        = 0                     # number of samples but can be given later.

# strobe delay bits
STRB_DELAY_AUTO     = 0                     # strobe delay. 0=use from config.server file
STRB_DELAY          = STRB_DELAY_AUTO       # strobe delay. STRB_DELAY_AUTO = use from config.server file
# example strobe delays
STRB_DELAY_1MHz     = 0x451e451e            # strobe delay for 300:400:300 ns at 1MHz bus output frequency
STRB_DELAY_10MHz    = 0x08030904            # strobe 0 delay for 30:50:20 ns at 10MHz bus output frequency
                                            # strobe 1 delay for 20:50:30 ns at 10MHz bus output frequency
STRB_DELAY_20MHz    = 0x00040503            # strobe 0 delay for 20:20:10 ns at 20MHz bus output frequency
                                            # strobe 1 delay for 30ns toggle (end=0) at 20MHz bus output frequency

# primary board sync wait time
SYNC_WAIT_BITS      = 10                    # bits used for sync_wait
SYNC_WAIT_MASK      = (1<<SYNC_WAIT_BITS)-1 # bit mask for sync_wait
SYNC_WAIT_AUTO      = 0xffffffff            # sync delay in cycles. 0xffffffff = take from config.server file
SYNC_WAIT_PRIM      = 22  & SYNC_WAIT_MASK   # sync delay in cycles for primary board. SYNC_WAIT_AUTO = take from config.server file
SYNC_WAIT_SEC       = 0  & SYNC_WAIT_MASK   # sync delay in cycles for secondary boards. SYNC_WAIT_AUTO = take from config.server file
SYNC_WAIT_SINGLE    = 0  & SYNC_WAIT_MASK   # sync delay in cycles for single-board experiment. SYNC_WAIT_AUTO = take from config.server file

# secondary boards external and detection clock phase bits
PHASE_360           = 560                   # phase steps for 360 degree at 100MHz clock
SYNC_PHASE_BITS     = 12                    # number of bits per phase
SYNC_PHASE_MASK     = (1<<SYNC_PHASE_BITS)-1 # phase mask
SYNC_PHASE_AUTO     = 0xffffffff            # use phase from server.config file
SYNC_PHASE_NONE     = 0                     # 0 phase
SEC_PHASE_EXT       = int((0*PHASE_360)//360) & SYNC_PHASE_MASK # secondary board external clock phase in steps
SEC_PHASE_DET       = int((0*PHASE_360)//360) & SYNC_PHASE_MASK # secondary board detection clock phase in steps
SYNC_PHASE_SEC      = (SEC_PHASE_EXT << SYNC_PHASE_BITS) | SEC_PHASE_DET # secondary board {fi_ext,fi_det} clock phase

# stop options
STOP_NOW            = 0                     # abort any output
STOP_AT_END         = 1                     # stop at end of cycle (not implemented)

# FPGA_status definition
# unpacks and save_prints full status information received from server
# unpack info contains tuples of (repetition, struct type)
if use_prelim_version:
    FPGA_status_unpack_info_8   = [(27,'I'),(6,'B'),(2,'s'),(3,'i'),(13,'I')]
    FPGA_status_unpack_info_12  = [(27,'I'),(6,'B'),(2,'s'),(3,'i'),(14,'I')]
else:
    FPGA_STATUS_NUM_DEBUG = 20
    FPGA_status_unpack_info_8   = [(25,'I'),(6,'B'),(2,'s'),(3,'i'),(16,'I'),(FPGA_STATUS_NUM_DEBUG,'I')] # (2,'s')
    FPGA_status_unpack_info_12  = [(25,'I'),(6,'B'),(2,'s'),(3,'i'),(17,'I'),(FPGA_STATUS_NUM_DEBUG,'I')]

FPGA_STATUS_OK              = 0
FPGA_STATUS_ENOINIT         = -1
FPGA_STATUS_EINCONST        = -10
FPGA_STATUS_ENUMBYTES       = -20
FPGA_STATUS_ERSP            = -30
FPGA_STATUS_EBPS            = -40
FPGA_STATUS_ENUMI32         = -50
FPGA_STATUS_EDUMMY          = -60
FPGA_STATUS_ENACK           = -70
FPGA_status_format_8 = FPGA_status_format_12 = '<2s'
for i in FPGA_status_unpack_info_8 : FPGA_status_format_8  += '%i%s' % i[0:2]
for i in FPGA_status_unpack_info_12: FPGA_status_format_12 += '%i%s' % i[0:2]
FPGA_STATUS_NUM_BYTES_8     = struct.calcsize(FPGA_status_format_8)
FPGA_STATUS_NUM_BYTES_12    = struct.calcsize(FPGA_status_format_12)
class FPGA_status:
    error = FPGA_STATUS_ENOINIT        # error code. FPGA_STATUS_OK = ok

    def __init__(self, bytes):
        # extract FPGA_status from bytes sent from server
        # note: assigning result of struct.unpack to a single variable saves everything as bytes and not int!?
        if (get_bytes(SERVER_STATUS_FULL_RSP_8) != FPGA_STATUS_NUM_BYTES_8) or (get_bytes(SERVER_STATUS_FULL_RSP_12) != FPGA_STATUS_NUM_BYTES_12):
            save_print('FPGA_status inconsistency: %i != %i or %i != %i' % (get_bytes(SERVER_STATUS_FULL_RSP_8),FPGA_STATUS_NUM_BYTES_8,get_bytes(SERVER_STATUS_FULL_RSP_12),FPGA_STATUS_NUM_BYTES_12))
            self.error = FPGA_STATUS_EINCONST
            return
        if len(bytes) == FPGA_STATUS_NUM_BYTES_8:
            self.bytes_per_sample = 8
            cmd = SERVER_STATUS_FULL_RSP_8
            info = FPGA_status_unpack_info_8
            format = FPGA_status_format_8
        elif len(bytes) == FPGA_STATUS_NUM_BYTES_12:
            self.bytes_per_sample = 12
            cmd = SERVER_STATUS_FULL_RSP_12
            info = FPGA_status_unpack_info_12
            format = FPGA_status_format_12
        elif (len(bytes) == SERVER_CMD_NUM_BYTES) and (bytes == SERVER_NACK):
            save_print('FPGA_status recieved NACK!')
            self.error = FPGA_STATUS_ENACK
            return
        else:
            save_print('FPGA_status recieved %i bytes but must be either %i or %i' % (len(bytes), FPGA_STATUS_NUM_BYTES_8, FPGA_STATUS_NUM_BYTES_12))
            self.error = FPGA_STATUS_ENUMBYTES
            return
        self.cmd, *data = struct.unpack(format, bytes)
        if self.cmd != cmd:
            self.error = FPGA_STATUS_ERSP
            return
        i = 0
        self.ctrl_FPGA          = data[i]; i += 1;
        if use_prelim_version:
            self.ctrl_in0       = data[i]; i += 1;
            self.ctrl_in1       = data[i]; i += 1;
            self.ctrl_out0      = data[i]; i += 1;
            self.ctrl_out1      = data[i]; i += 1;
            self.set_samples    = data[i]; i += 1;
            self.set_cycles     = data[i]; i += 1;
            self.clk_div        = data[i]; i += 1;
            self.strb_delay     = data[i]; i += 1;
            self.sync_delay     = data[i]; i += 1;
            self.sync_phase     = data[i]; i += 1;
            self.force_out      = data[i]; i += 1;
        else:
            self.ctrl_in        = data[i]; i += 1;
            self.ctrl_out       = data[i]; i += 1;
            self.set_samples    = data[i]; i += 1;
            self.clk_div        = data[i]; i += 1;
            self.strb_delay     = data[i]; i += 1;
            self.sync_delay     = data[i]; i += 1;
            self.sync_phase     = data[i]; i += 1;
            self.force_out      = data[i]; i += 1;
        self.status             = data[i]; i += 1;
        self.board_time         = data[i]; i += 1;
        self.board_samples      = data[i]; i += 1;
        self.board_time_ext     = data[i]; i += 1;
        self.board_samples_ext  = data[i]; i += 1;
        if use_prelim_version:
            self.board_cycles   = data[i]; i += 1;
        self.sync_time          = data[i]; i += 1;
        self.version            = data[i]; i += 1;
        self.info               = data[i]; i += 1; # 21
        self.FPGA_temp          = data[i]; i += 1;
        self.phase_ext          = data[i]; i += 1;
        self.phase_det          = data[i]; i += 1;
        if use_prelim_version == False:
            self.period_in      = data[i]; i += 1;
            self.period_out     = data[i]; i += 1;
            self.period_bus     = data[i]; i += 1;
        self.ctrl_DMA           = data[i]; i += 1;
        self.status_TX          = data[i]; i += 1;
        self.status_RX          = data[i]; i += 1; # 27
        self.dsc_TX_p           = data[i]; i += 1;
        self.dsc_TX_a           = data[i]; i += 1;
        self.dsc_TX_c           = data[i]; i += 1;
        self.dsc_RX_p           = data[i]; i += 1;
        self.dsc_RX_a           = data[i]; i += 1;
        self.dsc_RX_c           = data[i]; i += 1;
        dummy                   = data[i]; i += 1; # dummy gives 2 bytes at once
        self.err_TX             = data[i]; i += 1;
        self.err_RX             = data[i]; i += 1;
        self.err_FPGA           = data[i]; i += 1;
        self.irq_TX             = data[i]; i += 1;
        self.irq_RX             = data[i]; i += 1;
        self.irq_FPGA           = data[i]; i += 1;
        if not use_prelim_version:
            self.irq_num            = data[i]; i += 1;
        self.TX_bt_tot          = data[i]; i += 1;
        self.RX_bt_tot          = data[i]; i += 1;
        self.bt_tot             = data[i]; i += 1;
        self.RD_bt_max          = data[i]; i += 1;
        self.RD_bt_act          = data[i]; i += 1;
        self.RD_bt_drop         = data[i]; i += 1;
        if use_prelim_version == False:
            self.reps_set       = data[i]; i += 1;
        self.reps_act           = data[i]; i += 1;
        self.timeout            = data[i]; i += 1;
        if self.bytes_per_sample == 8:
            self.last_sample = data[i:i+2]; # [time, data]
            print('last sample', self.last_sample, len(data), i)
            i += 2;
        else:
            self.last_sample = data[i:i+3]; i += 3; # [time, data rack 0, data rack 1]
        if use_prelim_version == False:
            self.debug_count    = data[i]; i += 1;
            self.debug          = data[i:i+FPGA_STATUS_NUM_DEBUG]; i += FPGA_STATUS_NUM_DEBUG;
        # check number of integers
        # dummy returns 2 bytes instead of 1
        if use_prelim_version:
            num_int = sum([ii[0] if ii[1] != 's' else 1 for ii in info])
        else:
            num_int = sum([ii[0] if ii[1] != 's' else 1 for ii in info])
        if (i != num_int): # check consistent number of uint32_t
            print("%i != %i" % (i, num_int))
            print(self.set_samples, self.set_cycles, self.clk_div, self.version, self.info)
            self.error = FPGA_STATUS_ENUMI32
            return
        # check bytes per sample
        bytes_per_sample = 8 if ((self.ctrl_FPGA & CTRL_BPS96) == 0) else 12
        if (self.bytes_per_sample != bytes_per_sample): # check consistent bytes per sample
            self.error = FPGA_STATUS_EBPS
            return
        # check dummy
        if dummy != b'\x00\x00':
            save_print('2 dummy bytes should be 0 but is',dummy)
            self.error = FPGA_STATUS_EDUMMY
            return
        # status string
        if   self.status & STATUS_RUN:   self.FPGA_status_str = "running"
        elif self.status & STATUS_ERROR: self.FPGA_status_str = "error"
        elif self.status & STATUS_END:   self.FPGA_status_str = "end"
        else:                            self.FPGA_status_str = "stopped"
        # check correct number of TX and RX bytes
        self.TX_RX_bytes_ok = "ok" if (self.TX_bt_tot == self.RX_bt_tot) and (self.TX_bt_tot == self.bt_tot) else "error"
        # board temperature
        self.FPGA_temp = (((self.FPGA_temp >> 4) * 503975) / 4096 - 273150)
        if (self.FPGA_temp < 10): self.FPGA_temp = 0    # TODO: first sample is always wrong?
        # no error:
        self.error = FPGA_STATUS_OK

    def show(self):
        # print status info in console
        save_print(     "FPGA/DMA status:")
        save_print(     "ctrl/state   0x        - %08x %08x (%s)"% (self.ctrl_FPGA, self.status, self.FPGA_status_str))
        if use_prelim_version:
            save_print( "ctrl in  0/1 0x        - %08x %08x"    % (self.ctrl_in0, self.ctrl_in1))
            save_print( "ctrl out 0/1 0x        - %08x %08x"    % (self.ctrl_out0, self.ctrl_out1))
        else:
            save_print( "in/out       0x        - %08x %08x"    % (self.ctrl_in, self.ctrl_out))
            save_print( "in/out/bus ps   %8u %8u %8u"           % (self.period_in, self.period_out, self.period_bus))
        save_print(     "strb/clk     0x        - %8x %8x"      % (self.strb_delay, self.clk_div))
        save_print(     "sync w/ph/t  0x %8x %8x %8x"           % (self.sync_delay, self.sync_phase, self.sync_time))
        save_print(     "brd time   0/1         - %8u %8u us"   % (self.board_time, self.board_time_ext))
        save_print(     "brd smpl s/0/1  %8u %8u %8u"           % (self.set_samples, self.board_samples, self.board_samples_ext))
        if use_prelim_version:
            save_print( "cyc set/DMA/brd %8u %8u %8u"           % ( self.set_cycles, self.reps_act, self.board_cycles))
        else:
            save_print("reps/act         %8u %8u"               % (self.reps_set, self.reps_act))
        save_print(     "phase ext/det          - %8d %8d steps"% (self.phase_ext, self.phase_det))
        save_print(     "force out    0x        -        - %8x" % (self.force_out))
        save_print(     "temperature            -        - %4d.%03u deg.C" % (self.FPGA_temp / 1000, self.FPGA_temp % 1000))
        #save_print(     "DMA status:")
        #save_print(     "                    TX       RX     FPGA")
        save_print(     "DMA TX/RX/ctrl 0x %6x %8x %8x"         % (self.status_TX, self.status_RX, self.ctrl_DMA))
        save_print(     "err TX/RX/FPGA  %8d %8d %8d"           % (self.err_TX, self.err_RX, self.err_FPGA))
        save_print(     "dsc TX p/a/c    %8u %8u %8u"           % (self.dsc_TX_p, self.dsc_TX_a, self.dsc_TX_c))
        save_print(     "dsc RX p/a/c    %8u %8u %8u"           % (self.dsc_RX_p, self.dsc_RX_a, self.dsc_RX_c))
        save_print(     "trans TX/RX/tot %8u %8u %8u bytes (%s)"% (self.TX_bt_tot, self.RX_bt_tot, self.bt_tot, self.TX_RX_bytes_ok))
        save_print(     "rd max/act/drop %8u %8u %8u bytes"     % (self.RD_bt_max, self.RD_bt_act, self.RD_bt_drop))
        save_print(     "IRQs TX/RX/FPGA %8u %8u %8u"           % (self.irq_TX, self.irq_RX, self.irq_FPGA))
        if not use_prelim_version:
            save_print( "IRQs merged            -        - %8u" % (self.irq_num))
        save_print(     "timeout                -        - %8u ms"   % (self.timeout))
        if self.bytes_per_sample == 8:
            save_print( "RX last      0x %08x %08x        - (%u us)" % (self.last_sample[0], self.last_sample[1], self.last_sample[0]))
        elif self.bytes_per_sample == 12:
            save_print( "RX last      0x %08x %08x %08x (%u us)"     % (self.last_sample[0], self.last_sample[1], self.last_sample[2], self.last_sample[0]))
        if use_prelim_version:
            save_print( "bytes/sample           -        - %8u" % (self.bytes_per_sample))
        save_print(     "version      0x        -        - %08x (%s)"% (self.version, self.get_version()))
        save_print(     "info         0x        -        - %08x (%s)"% (self.info, self.get_info()))

    def get_version(self):
        major = (self.version >> 24) & 0xff
        minor = (self.version >> 16) & 0xff
        year  = 2000 + ((self.version >> 9)  & 0x7f)
        month = (self.version >> 5) & 0x0f
        day   = (self.version     ) & 0x1f
        return 'v%02i.%02i-%04i/%02i/%02i' % (major, minor, year, month, day)

    def get_info(self):
        board = self.info & 0xff
        if   board == 0xc0: return 'Cora-Z7-07S'
        elif board == 0xc1: return 'Cora-Z7-10'
        elif board == 0xa1: return 'Arty-Z7-10'
        elif board == 0xa2: return 'Arty-Z7-20'
        else: return ''

    def get_status_run(self):
        "prints short status info - this can be called also during running state"
        pass # not yet implmeneted


def get_board_samples(samples, last_time):
    """
    returns the expected board [samples, time] from sent number of samples and last time.
    the board is appending NOP samples in order to have always multiple of 4 samples.
    this changes the board_samples and the board_time.
    note: the reason is that the FIFO buffer have a fixed data width of 2^7 = 128bits = 16 bytes.
          for  8 bytes/sample this gives 2 experiment samples/FIFO sample
          for 12 bytes/sample this gives 4 experiment samples/3 FIFO samples
          the experimental samples are extracted from the FIFO samples by the onboard hardware,
          where a mask for invalid bytes could be set. but the driver would need to set this mask.
          if the total number of samples is a multiple of 2 or 4 samples, there will be never invalid bytes.
          so, for simplicity, the driver is always generating multiple of 4 samples where added samples have the NOP bit set,
          and the hardware is disregarding data whith the NOP bit set. the time has to be still incrementing for this data.
    update Oct. 2024: the limit of 4 samples is now not anymore required! board_samples = programmed samples
          the board_time is one tick incremented vs. last time
    """
    if use_prelim_version:
        return [samples, last_time+1]
    else:
        if (samples % 4) == 0: add = 0
        else:                  add = 4 - (samples % 4)
        return [samples + add, last_time + add]

def to_string(d, level=0):
    """
    creates string from a python object to be used to save as dataset for hdf5 file.
    allowed objects are dict, list, string, integer, float.
    inverse function of dict_from_string(d).
    the recursive call makes the function very simple but maybe not very efficient.
    """
    data = ""
    if isinstance(d, dict):
        data += "%%D%i#%i["%(level, len(d)*2)
        for key, value in d.items():
            data += "%s%s"%(to_string(key,level+1),to_string(value,level+1))
        data += "]%i;"%level
    elif isinstance(d, list):
        data += "%%L%i#%i["%(level, len(d))
        for di in d:
            data += "%s" % (to_string(di, level+1))
        data += "]%i;" % (level)
    elif isinstance(d, tuple):
        data += "%%T%i#%i[" % (level, len(d))
        for di in d:
            data += "%s" % (to_string(di, level + 1))
        data += "]%i;" % (level)
    elif isinstance(d, str):
        data += "%%s=%s;"%(d)
    elif isinstance(d, (int,np.uint32,np.uint64,np.int32,np.int64)):
        data += "%%i=%i;"%(d)
    elif isinstance(d, (float,np.float32,np.float64)):
        data += "%%f=%f;"%(d)
    elif d is None: # note: isinstance does not work with type(None) = NoneType!?
        data += "%NN;"
    else:
        save_print(d)
        raise LabscriptError('to_string:',d,'has unknown data type', type(d))
        exit()
    return data

def findall(s, sub):
    "generator to find indices of all non-overlapping sub in s"
    i = s.find(sub)
    while i != -1:
        yield i
        i = s.find(sub, i + len(sub))

def list_from_string(data, level):
    "helper function for from_string. returns list of python objects from data string"
    #print('list level', level, 'data =', data)
    num = 3 + data[3:].find("#")
    next  = [i for i in findall(data, ";")]
    start = [i for i in findall(data, "[")]
    end   = [i for i in findall(data, "]")]
    if (num < 0) or (len(next) == 0) or (len(start)==0) or (len(start) != len(end)) or (end[-1] > len(data)-3):
        print([num,len(next),len(start),len(end),end[-1],len(data)])
        raise LabscriptError("from_string: '%s' invalid! (L0)" % (data))
    if (int(data[2:num]) != (level-1)) or (int(data[end[-1]+1:end[-1]+num-1]) != (level-1)):
        raise LabscriptError("from_string: '%s' invalid! (L1)" % (data))
    num = int(data[num+1:start[0]]) # number of items in list
    # get indices of entries on on actual level
    assign = np.array([0 for _ in next] + [1 for _ in start] + [-1 for _ in end])
    index = np.array([i for i in next] + [i for i in start] + [i for i in end])
    sort = np.argsort(index)
    assign = assign[sort]
    index = index[sort]
    cumsum = np.cumsum(assign)
    mask = (cumsum == 1) & (assign == 0)
    index = index[mask]
    if (len(index) != num):
        raise LabscriptError("from_string: '%s' invalid! (L2)" % (data))
    start = start[0] + 1
    d = [None for _ in range(num)]
    for j,i in enumerate(index):
        d[j] = from_string(data[start:i+1], level)
        start = i + 1
    #print('list level', level, 'result =', d)
    return d

def from_string(data, level=0):
    """
    inverse function of to_string. returns reconstructed object. for details see there.
    """
    d = None

    #print('level', level, 'data = ', data)

    if isinstance(data, bytes):
        data = data.decode('utf-8')

    # data must contain single object starting wtih "%" and ending with ";"
    if (len(data) <= 3) or (data[0] != "%") or (data[-1] != ";"):
        print(data)
        print(data[0])
        print(data[-1])
        raise LabscriptError("from_string: '%s' invalid! (0)" % (data))

    if data[1] == "D": # dictionary
        d = {}
        l = list_from_string(data, level+1)
        if len(l) & 1 == 1:
            raise LabscriptError("from_string: '%s' invalid! (1)" % (data))
        for i in range(0,len(l),2):
            d[l[i]] = l[i+1]
        return d
    elif data[1] == "T": # tuple
        return tuple(list_from_string(data, level+1))
    elif data[1] == "L": # list
        return list_from_string(data, level+1)
    elif (data[1] == "s") and (data[2] == "="): # string
        return data[3:-1]
    elif (data[1] == "i") and (data[2] == "="): # integer
        return int(data[3:-1])
    elif (data[1] == "f") and (data[2] == "="): # float
        return float(data[3:-1])
    elif (data[1] == "N") and (data[2]=='N') and (len(data) == 4):  # None
        return None
    else: # unknown
        raise LabscriptError("from_string: '%s' invalid! (2)" % (data))

# PseudoClock
# accepts only ClockLine as childs
class FPGA_PseudoClock(Pseudoclock):
    # TODO: TriggerableDevice needs to be defined here otherwise get an error in start() which calls labscript.py trigger() line 949.
    #       the name of the dictionary is however __trigger but somehow it needs the '_TriggerableDevice' before? very obscure.
    #       To fix this I think one needs to declare a digital output as the "trigger", but I do not know how.
    #       For secondary boards, I do not need a TTL output for triggering since the primary board triggers it internally.
    #       However, for the Moglabs QRF device one would need a trigger TTL associated in some way?
    _TriggerableDevice__triggers = []

    def add_device(self, device):
        if isinstance(device, ClockLine):
            save_print("%s: adding ClockLine '%s'" % (self.name, device.name))
            parent = device.parent_device.name
            Pseudoclock.add_device(self, device)
        else:
            raise LabscriptError('%s allows only ClockLine child but you have connected %s (class %s).'%(self.name, device.name, device.__class__))

def parse_num(num):
    "parse string into integer number. string can be prefixed with '0x' for hex number"
    #TODO: which exceptions can int() raise?
    if isinstance(num, str):
        if len(num) > 2:
            if (num[0]=='0') and (num[1]=='x'): # hex number
                return int(num[2:],16)
            else: return int(num)
        else: return int(num)
    else:
        return num # assume is already a number

def time_to_str(time):
    #convert time (float) in seconds into easily readable string
    if time < 1e-12: return '0s'
    elif time < 1e-6: return ('%.3fns' % (time*1e9))
    elif time < 1e-3: return ('%.3fus' % (time*1e6))
    elif time < 1.0: return ('%.6fms' % (time*1e3))
    else: return ('%.6fs' % time)

#basic checking when adding new devices to one of the IntermediateDevice below
#returns decimal numbers [rack,address,channel] of device or raises LabscriptError on error
def check_device(device, allowed_type, max_channels, device_list, shared_address):
    #check device type. this includes also derived types.
    if not isinstance(device, allowed_type):
        raise LabscriptError("device '%s', type %s must be of type %s" % (device.name, str(type(device)), str(allowed_type)))
    # rack is always given by parent device
    rack = device.parent_device.rack
    #get address or channel
    if shared_address: # get rack & address from parent. channel defines data bits.
        address = device.parent_device.address
        channel = parse_num(device.connection)
    else: # each channel has its own rack/address. channel not needed (maybe in GUI).
        address = parse_num(device.connection)
        channel = len(device_list)
    #check valid rack number
    if (rack < 0) or (rack >= MAX_RACKS):
        save_print([rack,MAX_RACKS, rack < 0, rack >= MAX_RACKS])
        LabscriptError("For device '%s' rack number %i given but only 0..%i allowed!"%(device.name, rack, MAX_RACKS-1))
    #check maximum number of channels
    if max_channels is not None and len(device_list) >= max_channels:
        raise LabscriptError("You tried to add device '%s' to '%s' but which has already %i channels." % (device.name, device.parent_device.name, max_channels))
    #check valid channel number
    if (channel<0) or ((max_channels is not None) and (channel >= max_channels)):
        raise LabscriptError("Device '%s' channel number %i must be 0..%i." % (device.name, channel, max_channels-1))
    #ensure rack/address/channel is unique
    board = device.parent_device.parent_device.parent_device.parent_device
    if not isinstance(board, FPGA_board): # sanity check
        raise LabscriptError("'%s' is expected FPGA_board but is '%s'?" % (board.name, board.__class__))
    if hasattr(device, 'ADDR_RNG_MASK'):
        mask = device.ADDR_RNG_MASK
    else:
        mask = ADDR_MASK
    for pseudoclock in board.child_devices:
        for clockline in pseudoclock.child_devices:
            for IM in clockline.child_devices: # intermediate devices
                #save_print('check IM',IM.name)
                # skip QRF since is not a device in a rack!
                # note: do not use isinstance since this requires to import MOGLabs_QRF which can lead to a circular reference causing import to fail!
                if isinstance(IM, (DigitalChannels, AnalogChannels, DDSChannels)):
                    for dev in IM.child_devices: # note: device is not yet in list of childs.
                        _rack    = dev.properties['rack']
                        _address = dev.properties['address']
                        if hasattr(dev, 'ADDR_RNG_MASK'):
                            _mask = dev.ADDR_RNG_MASK
                        else:
                            _mask = ADDR_MASK
                        if IM == device.parent_device:
                            # same IM device must have same rack and different channel number
                            _channel = dev.properties['channel']
                            if (_channel == channel) or (_rack != rack):
                                raise LabscriptError("device '%s' rack %i, address 0x%x, channel %i is already used by '%s', channel %i" % (device.name, rack, address, channel, dev.name, _channel))
                        elif (rack == _rack) and ( ((address & _mask) == _address) or ((_address & mask) == address) ):
                            # different IM device must have different address or different rack
                            raise LabscriptError("device '%s' rack %i, address 0x%x (mask 0x%x) is already used by '%s' (0x%x, mask 0x%x)" % (device.name, rack, address, mask, dev.name, _address, _mask))
    #return [rack,address,channel] of new device
    return [rack, address, channel]

# internal special output device
# one created for each rack
# allows to insert time with special data bits for each rack
class SpecialOut(Output):
    address = None # has no address
    channel = None # channel = rack
    type    = TYPE_SP
    default_value = SP_INVALID_VALUE
    dtype   = np.uint32

    def __init__(self, name, parent_device, connection, rack, **kwargs):
        Output.__init__(self, name, parent_device, connection, **kwargs)
        # save device hardware properties into device and  hd5 file
        self.properties = {
            'rack'         : rack,
            'channel'      : 0,
            'default_value': 0,
            'invalid_value': SP_INVALID_VALUE,
        }
        for key, value in self.properties.items():
            self.set_property(key, value, 'connection_table_properties')

# internal special Intermediate Device
# needed for SpecialOut devices created one per rack
# TODO: maybe can be replaced with markers?
class SpecialIM(IntermediateDevice):
    description = 'internal device for special data'
    allowed_children = [SpecialOut]
    shared_address = False

    # returned data type from to_words
    raw_dtype = np.uint32

    def __init__(self, name, parent_device, bus_rate, **kwargs):
        #parent device must be FPGA_board. you should not connect it directly to clockline.
        if not isinstance(parent_device, FPGA_board):
            raise LabscriptError("Device '%s' parent class is '%s' but must be '%s'!" % (self.name, parent_device.__class__, FPGA_board))
        # get clockline from FPGA_board and set as parent
        self.name = name  # in case get_clockline gives an error
        self.parent_device = parent_device.get_clockline(self, bus_rate)
        # init device with clockline as parent
        IntermediateDevice.__init__(self, name, self.parent_device, **kwargs)

    def add_device(self, device):
        if isinstance(device, SpecialOut):
            IntermediateDevice.add_device(self, device)
        else:
            raise LabscriptError("'%s' must be SpecialOut but is '%s'!" % (device.name, device.__class__))

        device.to_words  = self.to_words
        device.raw_dtype = self.raw_dtype

    # define conversion function from raw data to data word.
    # properies = dictionary with required content 'invalid_value'
    @staticmethod
    def to_words(properties, data):
        invalid_value = properties['invalid_value']
        return np.array(np.where(data == invalid_value, 0, data), dtype=SpecialIM.raw_dtype)

class DigitalOutput(DigitalQuantity):
    description = 'digital output'

    # default value is inserted by labscript when no user input was done
    # we want this to be an invalid value to distinguish if its inserted by user or by labscript
    # the true default value given to device is saved in device.properties.
    default_value = DO_INVALID_VALUE

    # returned data type from to_words
    raw_dtype = np.uint32

    def __init__(self, name, parent_device, connection, inverted=DO_DEFAULT_VALUE, **kwargs):
        # true device default and invalid values
        self.properties = {
            'default_value': 1 if inverted else 0,
            'invalid_value': DO_INVALID_VALUE,
        }
        DigitalQuantity.__init__(self, name, parent_device, connection, inverted, **kwargs)

    # conversion function from data to raw_data word(s)
    # properies = dictionary with required content 'invalid_value', 'address', 'channel'
    @staticmethod
    def to_words(properties, data):
        address       = properties['address']
        ch            = properties['channel']
        invalid_value = properties['invalid_value']
        return np.array(np.where(data == invalid_value, BIT_NOP_SH,
                                 (data * (1 << ch)) | (address << ADDR_SHIFT)),
                        dtype=DigitalOutput.raw_dtype)

# IntermediateDevice with digital output channels
# channel numbers must be unique. all channels have the parent address (called 'connect' for consistency)
class DigitalChannels(IntermediateDevice):
    description = 'digital output device with several channels'
    allowed_children = [DigitalOutput]
    shared_address = True

    # output type
    type = TYPE_DO

    #clock_limit = CLOCK_LIMIT
    #num_racks = 0 # set to maximum allowed number of racks given by FPGA_board

    def __init__(self, name, parent_device, connection, rack, max_channels, bus_rate=DEFAULT_BUS_RATE, **kwargs):
        #parent device must be FPGA_board. you should not connect it directly to clockline.
        if not isinstance(parent_device, FPGA_board):
            raise LabscriptError("Device '%s' parent class is '%s' but must be '%s'!" % (name, parent_device.__class__, FPGA_board))
        # get clockline from FPGA_board and set as parent
        self.name = name # in case get_clockline gives an error
        self.parent_device = parent_device.get_clockline(self, bus_rate)
        # init device with clockline as parent
        IntermediateDevice.__init__(self, name, self.parent_device, **kwargs)

        # set clock limit and resolution
        self.clock_limit      = get_clock_limit(bus_rate)
        self.clock_resolution = get_clock_resolution(bus_rate)
        #print(name, "clock limit", self.clock_limit, "resolution", self.clock_resolution)

        self.num_racks = parent_device.num_racks
        self.max_channels = max_channels
        self.rack = rack

        # digital channels share the same address. therefore, channels on the same intermediate device can change simultaneously.
        self.address = parse_num(connection)
        if (self.rack < 0) or (self.rack >= self.num_racks):
            raise LabscriptError("For device '%s' rack number %i given but parent device '%s' has only %i racks!" % (self.name, self.rack, parent_device.name, self.num_racks))
        if (self.address < 0) or (self.address > ADDR_MAX):
            raise LabscriptError("For device '%s' address %x given but only 0..%x allowed!" % (self.name, self.address, ADDR_MAX))
        #save address bits
        # manually add device to clockline
        #self.parent_device.add_device(self)

    def add_device(self, device):
        #save_print('FPGA_Intermediatedevice: add device', device.name)
        #check if valid device, channel and if channel is already used
        rack, address, channel = check_device(device, DigitalQuantity, self.max_channels, self.child_devices, self.shared_address)
        # save default device hardware properties into device and hd5 file
        # when device has already properties they are kept
        properties = {
            'rack'          : rack,
            'address'       : address,
            'channel'       : channel,
            'device_class'  : str(type(device)).split("'")[1],
        }
        if hasattr(device, 'properties'):
            properties.update(device.properties)
        device.properties = properties

        for key, value in device.properties.items():
            device.set_property(key, value, 'connection_table_properties')

        # check that device implements everything needed
        if not hasattr(device, 'to_words') or \
            not hasattr(device, 'raw_dtype') or \
            not hasattr(device, 'default_value'):
            raise LabscriptError("'%s' type '%s' must implement 'to_words', 'raw_dtype', 'default_value'" % (device.name, str(type(device))))
        elif 'default_value' not in device.properties or \
             'invalid_value' not in device.properties:
            raise LabscriptError("'%s' type '%s' properties must implement 'default_value', 'invalid_value'" % (device.name, str(type(device))))

        # connect to parent device
        IntermediateDevice.add_device(self, device)

# IntermediateDevice with analog output channels
# channels have individual addresses (saved in 'connect').
class AnalogChannels(IntermediateDevice):
    description = 'analog output device with several channels'
    if use_prelim_version:
        allowed_children = [AnalogOutput]
    else:
        allowed_children = [AnalogOut]
    shared_address = False

    # output type
    type = TYPE_AO

    #clock_limit = CLOCK_LIMIT
    #num_racks = 0 # set to maximum allowed number of racks given by FPGA_board

    def __init__(self, name, parent_device, rack, max_channels, bus_rate=DEFAULT_BUS_RATE, **kwargs):
        # parent device must be FPGA_board. you should not connect it directly to clockline.
        if not isinstance(parent_device, FPGA_board):
            raise LabscriptError("Device '%s' parent class is '%s' but must be '%s'!" % (self.name, parent_device.__class__, FPGA_board))
        # get clockline from FPGA_board and set as parent_device
        self.name = name # in case get_clockline gives an error
        self.parent_device = parent_device.get_clockline(self, bus_rate)
        # init device with clockline as parent
        IntermediateDevice.__init__(self, name, self.parent_device, **kwargs)

        # set clock limit and resolution
        self.clock_limit      = get_clock_limit(bus_rate)
        self.clock_resolution = get_clock_resolution(bus_rate)

        self.num_racks = parent_device.num_racks
        self.rack = rack
        self.max_channels = max_channels
        if rack >= self.num_racks:
            raise LabscriptError("Device '%s' specified rack number %i is larger than allowed %i!" % (self.name, rack, self.num_racks-1))
        # manually add device to clockline
        #self.parent_device.add_device(self)

    def add_device(self, device):
        #save_print("AnalogChannels: add device '%s' type '%s'" % (device.name, str(type(device))))
        #check if valid device and channel and if channel is already used
        #create container class and check if valid device, channel and if channel is already used
        #each channel has its own address.
        rack, address, channel = check_device(device, AnalogQuantity, self.max_channels, self.child_devices, False)

        # save default device hardware properties into device and hd5 file
        # when device has already properties they are kept
        properties = {
            'rack'          : rack,
            'address'       : address,
            'channel'       : channel,
            'device_class'  : str(type(device)).split("'")[1],
        }
        if hasattr(device, 'properties'):
            properties.update(device.properties)
        device.properties = properties
        for key, value in device.properties.items():
            device.set_property(key, value, 'connection_table_properties')

        if use_prelim_version:
            # check that device implements everything needed
            if not hasattr(device, 'to_words') or \
                not hasattr(device, 'raw_dtype') or \
                not hasattr(device, 'default_value'):
                raise LabscriptError("'%s' type '%s' must implement 'to_words', 'raw_dtyoe', 'default_value'" % (device.name, str(type(device))))
            elif 'default_value' not in device.properties or \
                 'invalid_value' not in device.properties:
                raise LabscriptError("'%s' type '%s' properties must implement 'default_value', 'invalid_value'" % (device.name, str(type(device))))

        # connect to parent device
        IntermediateDevice.add_device(self, device)

# IntermediateDevice with DDS output channels
# address of each channel must be integer multiple of 4
# since each channel uses 3 consecutive addresses for frequency, amplitude and phase.
class DDSChannels(IntermediateDevice):
    description = 'DDS output device with several channels'
    allowed_children = [DDSQuantity]
    shared_address = False

    # output type
    type = TYPE_DDS

    #clock_limit = CLOCK_LIMIT
    #num_racks = 0 # set to maximum allowed number of racks given by FPGA_board

    def __init__(self, name, parent_device, rack, max_channels, bus_rate=DEFAULT_BUS_RATE, **kwargs):
        # parent device must be FPGA_board. you should not connect it directly to clockline.
        if not isinstance(parent_device, FPGA_board):
            raise LabscriptError("Device '%s' parent class is '%s' but must be '%s'!" % (self.name, parent_device.__class__, FPGA_board))
        # get clockline from FPGA_board and set as parent_device
        self.name = name  # in case get_clockline gives an error
        self.parent_device = parent_device.get_clockline(self, bus_rate)
        # init device with clockline as parent
        IntermediateDevice.__init__(self, name, self.parent_device, **kwargs)

        # set clock limit and resolution
        self.clock_limit      = get_clock_limit(bus_rate)
        self.clock_resolution = get_clock_resolution(bus_rate)

        self.num_racks = parent_device.num_racks
        self.rack = rack
        self.max_channels = max_channels
        if rack >= self.num_racks:
            raise LabscriptError("Device '%s' specified rack number %i is larger than allowed %i!" % (self.name, rack, self.num_racks-1))
        # manually add device to clockline
        #self.parent_device.add_device(self)

    def add_device(self, device):
        #save_print("DDSChannels: add device '%s' type '%s'" % (device.name, str(type(device)).split("'")[1]))
        #check if valid device and channel and if channel is already used
        #create container class and check if valid device, channel and if channel is already used
        #each channel has its own address.
        rack, address, channel = check_device(device, DDSQuantity, self.max_channels, self.child_devices, False)

        # save default device hardware properties into device and hd5 file
        # when device has already properties they are kept
        properties = {
            'rack'          : rack,
            'address'       : address,
            'channel'       : channel,
            'device_class'  : str(type(device)).split("'")[1],
        }
        if hasattr(device, 'properties'):
            properties.update(device.properties)
        device.properties = properties
        for key, value in device.properties.items():
            device.set_property(key, value, 'connection_table_properties')

        # check that device implements everything needed
        if not hasattr(device, 'to_words') or \
            not hasattr(device, 'setfreq') or \
            not hasattr(device, 'setamp') or \
            not hasattr(device, 'setphase'):
            raise LabscriptError("'%s' type '%s' must implement 'to_words', 'setfreq', 'setamp', 'setphase'" % (device.name, str(type(device))))

        # connect to parent device
        IntermediateDevice.add_device(self, device)

# PseudoclockDevice
class FPGA_board(PseudoclockDevice):
    description = 'FPGA board device class v1.0'
    allowed_children = [FPGA_PseudoClock]

    # the delay is corrected by the board on the ns level if needed, so we can set this to 0.
    trigger_delay = 0
    #wait_delay = 2e-6 # unclear what this is?
    trigger_edge_type = 'rising'

    PCLOCK_FORMAT           = '%s_pc%i_%s'      # device name + index + bus_rate
    CLOCKLINE_FORMAT        = '%s_cl%i'         # pseudo clock name + index
    CLOCKLINE_FORMAT_NAME   = '%s_cl%i_%s'      # pseudo clock name + index
    CON_FORMAT              = '%s_con'          # pseudo clock or clockline name
    CLOCK_FORMAT_SEP        = "_"               # format separator for when clockline is given as name

    # call with name, IP address string and port string, output bus rate in Hz and num_racks (1=8 bytes/sample, 2=12 bytes/sample)
    # for all secondary boards give trigger_device=primary board.
    @set_passed_properties()
    def __init__(self, name, ip_address, ip_port=DEFAULT_PORT, bus_rate=DEFAULT_BUS_RATE, num_racks=1, trigger_device=None, worker_args={}):
        if trigger_device is not None:
            trigger_connection = 'trigger' # we have to give a connection with name 'trigger' otherwise get error.
        else:
            trigger_connection = None

        # init PseudclockDevice class with proper trigger settings
        PseudoclockDevice.__init__(self, name, trigger_device=trigger_device, trigger_connection=trigger_connection)

        # check if primary board and manually add secondary device to primary board child list.
        # all other than first board need a trigger_device to be given (not sure what to do with it).
        self.trigger_device = trigger_device
        if trigger_device is None:
            self.is_primary = True
            self.primary_board = None
            inputs = default_in_prim
            outputs = default_out_prim
        else:
            if isinstance(trigger_device, FPGA_board):
                self.primary_board = trigger_device
                self.primary_board.add_device(self)
                self.is_primary = False
            else:
                # external trigger device like PulseBlaster
                # boards are independent but need to wait for start trigger
                self.is_primary = True
                self.primary_board = None
            inputs = default_in_sec
            outputs = default_out_sec

        # worker args passed to Worker init
        # werge default worker args with worker args from connection_table. connection_table takes precedence.
        # inputs and outputs are dictionaries themselves, so need to be merged separately
        # note: we must set triogger_edge_type before call to super class
        check_worker_args(worker_args)
        self.worker_args = worker_args
        if STR_INPUTS in worker_args:
            inputs.update(worker_args[STR_INPUTS])
            self.worker_args[STR_INPUTS] = inputs
            if STR_TRIG_START in inputs:
                if STR_RISING    in inputs[STR_TRIG_START]: self.trigger_edge_type = STR_RISING
                elif STR_FALLING in inputs[STR_TRIG_START]: self.trigger_edge_type = STR_FALLING
                else:                                            self.trigger_edge_type = None
                print('start trigger type', self.trigger_edge_type)
        elif len(inputs) > 0:
            self.worker_args[STR_INPUTS] = inputs
        if STR_OUTPUTS in worker_args:
            outputs.update(worker_args[STR_OUTPUTS])
            self.worker_args[STR_OUTPUTS] = outputs
        elif len(outputs) > 0:
            self.worker_args[STR_OUTPUTS] = outputs

        # init PseudclockDevice class with proper trigger settings
        #PseudoclockDevice.__init__(self, name, trigger_device=trigger_device, trigger_connection=trigger_connection)

        self.ip_address = ip_address.replace(":",".") # must be a string of the form '192.168.1.1' or '192:168:1:1'
        self.ip_port = str(ip_port) # the ip_port could be given as integer, but we request string
        self.BLACS_connection = '%s:%s'%(self.ip_address,self.ip_port)
        self.bus_rate = bus_rate # maximum bus output rate of board
        self.time_step = TIME_STEP/self.bus_rate    # smallest allowed rate
        self.start_time = self.time_step*START_TIME # initial time cannot be smaller than this. TODO: check in data!
        self.num_racks = num_racks
        self.digits = int(np.ceil(np.log10(self.bus_rate))) # for 9e5 get 6, for 1e6 get 6, for 1.1e6 get 7

        # check allowed bytes per sample
        if (num_racks > 2): raise LabscriptError("%s: you have given %i racks but maximum 2 are allowed! use several boards instead." %(self.name, bytes_per_sample))
        elif (num_racks < 1): raise LabscriptError("%s: you have given %i racks but minimum 1 is allowed!" %(self.name, bytes_per_sample))
        if bus_rate > MAX_FPGA_RATE: raise LabscriptError("%s: maximum bus rate is %.3f MHz. You specified %.3f MHz!" %(self.name,self.MAX_FPGA_RATE/1e6,self.bus_rate/1e6))
        self.clock_limit      = get_clock_limit(bus_rate)
        self.clock_resolution = get_clock_resolution(bus_rate)

        #save bus rate in Hz and number of racks into hdf5 file
        self.set_property('bus_rate', self.bus_rate, 'connection_table_properties')
        self.set_property('num_racks', self.num_racks, 'connection_table_properties')

        # create num_racks SpecialOut devices to store special data bits per rack
        # we need one SpecialIM device for this.
        # note: the special data bits are not sent to devices, so we can set maximum bus rate but this might have unintended side-effects?
        self.special_IM   = SpecialIM(name='%s_special_IM'%self.name, parent_device=self, bus_rate=self.bus_rate)
        self.special_data = [SpecialOut(name='%s_special_data_%i'%(self.name,i),
                                        parent_device=self.special_IM,
                                        connection='%s_special_data_%i_con'%(self.name,i),
                                        rack=i) for i in range(self.num_racks)]

        # list of secondary boards.
        # note: QRF board is not in list of childs, so we have to keep a separate list
        self.secondary_boards = []

        # additional worker args from experiment script (filled in generate_code and parsed in transition_to_buffered)
        self.worker_args_ex = {}

        # save worker arguments into hdf5 file
        print('%s init: worker_args =' % self.name, self.worker_args)
        self.set_property('worker_args', self.worker_args, location='connection_table_properties')

    def add_device(self, device):
        if isinstance(device, Pseudoclock):
            save_print("%s: adding PseudoClock '%s'" % (self.name, device.name))
            PseudoclockDevice.add_device(self, device)
        elif isinstance(device, Trigger):
            save_print("%s: adding Trigger '%s' parent '%s'" % (self.name, device.name, device.parent_device.name))
            # TODO: for each secondary board the primary board gets a Trigger device but I dont know what to do with it?
            pass
        elif isinstance(device, PseudoclockDevice):
            save_print("%s: adding secondary board '%s'" % (self.name, device.name))
            # I call this manually from __init___ for each secondary board added with trigger_device = primary board.
            self.secondary_boards.append(device)
        elif isinstance(device, labscript.labscript.DDS):
            # DDS
            save_print("%s: adding %s '%s' (not implemented)" % (self.name, device.__class__, device.name))
        else:
            raise LabscriptError("%s: adding %s '%s' is not allowed!" % (self.name, device.__class__, device.name))

    def get_clockline(self, device, bus_rate):
        """
        creates pseudoclock and clockline with given maximum bus_rate in Hz.
        updated: now creates for all intermediate devices a separate clockline.
                 this should improve performance of generate_code since does not need to interpolate which we do not want.
        returns clockline with given maximum bus_rate.
        call from __init__ of all intermediate devices to get parent_device.
        """
        # note about pseudoclocks and clocklines (as far as I understand):
        # the hirarchial connection is from parent -> child:
        #       PseudoclockDevice (FPGA_board) -> pseudoclock (FPGA_PseudoClock) -> clockline -> intermediate device -> channels
        # different clocklines on the SAME pseudoclock are interfering!
        # i.e. the smallest bus_rate on any clockline is limiting the entire pseudoclock!
        # therefore, to allow different bus_rates of different intermediate devices I generate different pseudeclocks!
        # the purpose of having different clocklines seems to be for devices with the SAME bus_rate but changing at different times?
        # tests with two clocklines are unclear: I get randomly LabscriptError labscript.py line 907 following if dt < (2 * clock_line.minimum_clock_high_time)
        # see notes from 12/2/2023. looks like a bug but discussion here says not: https://groups.google.com/g/labscriptsuite/c/QdW6gUGNwQ0/m/AJTUufvbAAAJ
        # to be sure I create now different pseudoclocks and I allow different clocklines for the future.

        # device must be IntermediateDevice or FPGA_board
        if not isinstance(device, (IntermediateDevice, FPGA_board)):
            raise LabscriptError("device '%s' class '%s' must be 'IntermediateDevice'!" % (device.name, device.__class__))

        # check minimum and maximum bus rate
        if bus_rate <= 1000.0:
            raise LabscriptError("you tried to add to '%s' a clockline for device '%s' with bus_rate %.3f Hz which seems low? Please give frequency in Hz, not in MHz. Max. possible is %.3f MHz." % (self.name, device.name, bus_rate, MAX_FPGA_RATE/1e6))
        if bus_rate > MAX_FPGA_RATE:
            raise LabscriptError("you tried to add to '%s' a clockline for device '%s' with bus_rate %.3f MHz > max. allowed %.3f MHz" % (self.name, device.name, bus_rate/1e6, MAX_FPGA_RATE/1e6))

        # create new pseudoclock with given rate
        line_index = 0
        index = 0
        for child in self.child_devices:
            if isinstance(child, Pseudoclock):
                index += 1
        # find smallest digit of bus_rate
        name = self.PCLOCK_FORMAT % (self.name, index, prefix(bus_rate, "Hz"))
        connection = self.CON_FORMAT % (name)
        pseudoclock = FPGA_PseudoClock(name=name, pseudoclock_device=self, connection=connection)
        pseudoclock.bus_rate = bus_rate
        # set clock limit and resolution
        pseudoclock.clock_limit = get_clock_limit(bus_rate)
        pseudoclock.clock_resolution = get_clock_resolution(bus_rate)

        # create new clockline with given name or default name from line_index = number of clocklines - 1
        clockline_name = self.CLOCKLINE_FORMAT % (pseudoclock.name, line_index)
        connection = self.CON_FORMAT % (clockline_name)
        _clockline = ClockLine(name=clockline_name, pseudoclock=pseudoclock, connection=connection, call_parents_add_device=False)
        pseudoclock.add_device(_clockline)

        # return new clockline
        return _clockline

    @staticmethod
    def get_table_mode_channels(pseudoclock_device):
        """
        returns list with channels with table_mode = True and trigger_each_step = True.
        recursively searches for channels including in triggered child devices
        """
        table_mode_channels = []
        for pseudoclock in pseudoclock_device.child_devices:
            for clockline in pseudoclock.child_devices:
                for IM in clockline.child_devices:
                    # TODO: at the moment table_mode is defined for intermediate device. maybe define per channel?
                    if hasattr(IM, 'table_mode') and IM.table_mode and \
                       hasattr(IM, 'trigger_each_step') and IM.trigger_each_step:
                        table_mode_channels += IM.child_devices
                    else:
                        # we must search all digital channels if they are triggering any
                        # pseudoclock device like Moglabs_QRF
                        for dev in IM.child_devices:
                            for psd in dev.child_devices:
                                table_mode_channels += FPGA_board.get_table_mode_channels(psd)
        return table_mode_channels

    def generate_code(self, hdf5_file):
        global total_time
        
        if total_time is None:
            total_time = get_ticks()
            save_print("\n'%s' generating code (start) ...\n" % (self.name))
        else:
            save_print("'%s' generating code (0) %.3fms ..." % (self.name, (get_ticks() - total_time) * 1e3))

        # insert instructions for table_mode devices like QRF DDS
        # notes:
        # - applies to devices with device.table_mode = True and device.trigger_each_step = True.
        # - these devices must have a device.gate digital output associated given as 'digital_gate' in __init__.
        #   additional required properties: trigger_delay and trigger_duration.
        # - for each instruction at time t we add two gate instructions:
        #   device.gate.go_high(t-device.trigger_delay)
        #   device.gate.go_low(t-device.trigger_delay+device.trigger_duration)
        # - if the user has manually inserted instructions for device.gate we give an error here.
        # - this allows to program the frequency, amplitude, phase of the DDS for arbitrary times without the user
        #   requiring to activate the gate for each step.
        # - this needs to be called before PseudoclockDevice.generate_code, otherwise new instructions are not taken.
        # TODO: not fully tested. work in progress.
        #       latest update: not anymore needed since I found a better way. see QRF project.
        if False:
            table_mode_channels = FPGA_board.get_table_mode_channels(self)
            if len(table_mode_channels) > 0:
                print('%i table mode channels found:' % len(table_mode_channels))
                for dev in table_mode_channels:
                    if (not hasattr(dev, 'gate')) or (not hasattr(dev.parent_device, 'trigger_delay')) or (not hasattr(dev.parent_device, 'trigger_duration')):
                        raise LabscriptError("%s error: no 'gate' defined or parent has not 'trigger_delay' or no 'trigger_duration'!" % (dev.name))
                    if len(dev.gate.instructions) > 2:
                        raise LabscriptError("%s error: in table mode do not call enable/disable or gate.go_low/go_high but program directly frequency/amplitude/phase!" % (dev.name))
                    # get times
                    trigger_delay    = dev.parent_device.trigger_delay
                    trigger_duration = dev.parent_device.trigger_duration
                    times = []
                    if isinstance(dev, DDSQuantity):
                        # DDS has frequency, amplitude and phase. we need the times.
                        for child in dev.child_devices:
                            for key in child.instructions.keys():
                                if isinstance(key, dict):
                                    # TODO: at the moment ramps are not working here! maybe call expand_timeseries?
                                    raise LabscriptError("%s error: at the moment no ramps are allowed for this device! use individual commands." % (dev.name))
                            times += list(child.instructions.keys())
                    else:
                        for key in child.instructions.keys():
                            if isinstance(key, dict):
                                # TODO: at the moment ramps are not working here! maybe call expand_timeseries?
                                raise LabscriptError("%s error: at the moment no ramps are allowed for this device! use individual commands." % (dev.name))
                        times += list(child.instructions.keys())
                    # get unique times and sort with increasing time.
                    times = np.unique(times)
                    if len(times) > 0:
                        # activate gate for each time
                        # TODO: use functions.pulse_sequence
                        trigger_delay = 0
                        for t in times:
                            if (t - trigger_delay) < 0:
                                raise LabscriptError("%s error: time %f with trigger_delay %f gives negative time %f!" % (dev.name, t, trigger_delay, t - trigger_delay))
                            dev.gate.go_high(t - trigger_delay)
                            dev.gate.go_low(t - trigger_delay + trigger_duration)
                        print('%s: %i gate instructions added' % (dev.name, len(times)))
                        print(times)
                        print(dev.gate.instructions)

        save_print("'%s' generating code (1) %.3fms ..." % (self.name, (get_ticks() - total_time) * 1e3))

        # save special instructions since Pseudoclock.generate_code might delete them
        special_instructions = {}
        for pseudoclock in self.child_devices:
            for clockline in pseudoclock.child_devices:
                for IM in clockline.child_devices:
                    if isinstance(IM, SpecialIM):
                        for dev in IM.child_devices:
                            if len(dev.instructions) > 0:
                                special_instructions[dev] = dev.instructions

        # TODO:
        # - maybe this call is not needed? we can do everything below directly from dev.instructions
        #   only the error checking would be nice.
        # - alternative: use separate clockline for each IM device then no interpolation is done.
        #   this is not needed for FPGA board, causes more work and memory and time.
        # - check why many digital pulses take so long to compile?
        #   I think its in this call and not in my code. maybe with separate clock lines its already better?
        PseudoclockDevice.generate_code(self, hdf5_file)

        save_print("'%s' generating code (2) %.3fms ..." % (self.name, (get_ticks() - total_time) * 1e3))

        t_start = get_ticks()
        # experimental:
        # merge all times of all pseudoclocks and clocklines
        # times and channel.raw_output will have different lengths!
        times = np.unique(np.concatenate([pseudoclock.times[clockline] for pseudoclock in self.child_devices for clockline in pseudoclock.child_devices]))
        exp_time = times[-1]

        save_print("'%s' total %i times:\n"%(self.name,len(times)),times)
        # allocate data matrix row x column = samples x (time + data for each rack)
        data = np.zeros(shape=(len(times), self.num_racks + 1), dtype=np.uint32)
        # allocate mask where data changes from one sample to next
        changes = np.zeros(shape=(len(times), self.num_racks), dtype=np.bool_)
        # allocate mask where several devices with different address change at the same time.
        # note that several TTL outputs with the same address (on the same IM device) are allowed to change simultaneously.
        conflicts = np.zeros(shape=(len(times), self.num_racks), dtype=np.bool_)

        # insert time word
        data[:, 0] = time_to_word(times, self.bus_rate, self.digits)

        # go through all channels and collect data
        special_STRB = False
        final_values = {} # final state of each used channel
        crc = {} # dict of CRC for each channel
        for pseudoclock in self.child_devices:
            #print('ps_clock %s:'%pseudoclock.name)
            for clockline in pseudoclock.child_devices:

                t = pseudoclock.times[clockline]
                #print("'%s' %i times:\n"%(clockline.name, len(t)), t)

                # get indices of t within times
                # note: working with mask might be faster but I have troubles with double-indexing on left-hand side of assignments.
                #       this does not work: changes[mask][chg] = True assigns to a COPY of changes[mask] which is then thrown away!
                #       this however works: changes[mask] = chg. to use this with data: m2=mask.copy(); m2[mask]=chg; data[m2] = d[chg];
                #       I think this is a misconception of Python.
                #       why would one want to make a copy of anything on the left-hand-side of an assignment?
                indices = np.argwhere(np.isin(times, t)).ravel()

                if len(indices) != len(t): # sanity check
                    raise LabscriptError('generate_code: not all times of pseudoclock found? (should not happen)')

                for IM in clockline.child_devices:
                    #print('IM device %s:'%IM.name)

                    # skip special devices (will be treated after all other below)
                    if isinstance(IM, SpecialIM):
                        continue

                    if IM.shared_address: # shared address like digital out

                        # collect data for all channels of IM device
                        d   = np.zeros(shape=(len(t),), dtype=np.uint32)
                        chg = np.zeros(shape=(len(t),), dtype=np.bool_)

                        for dev in IM.child_devices:
                            #print('device %s: %i times' % (dev.name, len(dev.raw_output)))
                            #if np.count_nonzero(dev.raw_output == dev.default_value) != len(t):
                            #print('%s instr:'%dev.name, dev.instructions)
                            #print('%s raw data:' % dev.name, dev.raw_output)

                            if len(dev.raw_output) != len(t):  # sanity check.
                                print('device %s: %i times' % (dev.name, len(dev.raw_output)))
                                print(dev.raw_output)
                                print(dev.times)
                                raise LabscriptError('generate_code: raw output (%i) not consistent with times (%i)? (should not happen)' % (len(dev.raw_output), len(t)))

                            # convert raw data into data word and accumulate with other channels
                            d |= dev.to_words(dev.properties, dev.raw_output)

                            if use_prelim_version:
                                default_value = dev.properties['default_value']
                            else:
                                default_value = dev.default_value

                            # mark changes
                            chg[0]  |= (dev.raw_output[0] != dev.default_value)
                            chg[1:] |= ((d[1:] - d[:-1]) != 0)

                            # save last state. worker needs channel name and not device name (dev.name).
                            # if last value is dev.default_value (i.e. invalid value) then channel was not used and we return channel default_value.
                            rack          = dev.properties['rack']
                            address       = dev.properties['address']
                            channel       = dev.properties['channel']
                            #ID = get_ID(IM.type,rack,address,channel)
                            final_value = default_value if dev.raw_output[-1] == default_value else dev.raw_output[-1]
                            final_values[get_channel_name(IM.type, rack, address, channel)] = final_value

                        # check conflicts with devices of different address
                        i = indices[chg]
                        conflicts[i,IM.rack] |= changes[i,IM.rack]
                        changes[i,IM.rack] = True

                        # save data where output changed
                        # we have to mask NOP bit from unused channels
                        data[i,IM.rack+1] = d[chg] & DATA_ADDR_MASK
                    else:
                        # no shared address (like analog out and DDS):
                        # collect data for each individual device
                        for dev in IM.child_devices:
                            #if np.count_nonzero(dev.raw_output == dev.default_value) != len(t):
                            #    # print('%s instr:'%dev.name, dev.instructions)
                            #    print('%s raw data:' % dev.name, dev.raw_output)

                            # get list of sub-channels and final value of device
                            # worker needs channel name (connection) and not device name (sub.name).
                            # if last value is sub.default_value (i.e. invalid value),
                            # then channel was not used and we return true channel default_value.
                            if len(dev.child_devices) > 0 and not isinstance(dev, Trigger):
                                # device with sub-channels like DDS:
                                # raw_output is not user input but already processed data.
                                # to_words is a dummy and returning the raw data.
                                # this allows that one user input creates several data words,
                                # 2 drawbacks:
                                # - ramps are not possible since have to work on user data
                                #   and not on processed data.
                                # - device must collect final_values for all sub-channels
                                # note: Trigger has sub-channel(s) = secondary board(s) which we do not want here.
                                devList = dev.child_devices
                                rack          = dev.properties['rack']
                                address       = dev.properties['address']
                                channel       = dev.properties['channel']
                                #ID = get_ID(IM.type,rack,address,channel)
                                final_values[get_channel_name(IM.type, rack, address, channel)] = dev.final_values
                            else:
                                # single channel:
                                # raw_output is directly the user input or generated from ramps.
                                # to_words is processing data into hardware specific raw data.
                                # this requires that each user input creates only one data word.
                                devList = [dev]
                                rack          = dev.properties['rack']
                                address       = dev.properties['address']
                                channel       = dev.properties['channel']
                                if use_prelim_version:
                                    default_value = dev.properties['default_value']
                                else:
                                    default_value = dev.default_value
                                #ID = get_ID(IM.type,rack,address,channel)
                                if dev.raw_output[-1] == default_value:
                                    final_values[get_channel_name(IM.type, rack, address, channel)] = default_value
                                else:
                                    final_values[get_channel_name(IM.type, rack, address, channel)] = dev.raw_output[-1]

                            # collect data for each (sub-)channel.
                            # use only changing data.
                            # change in data is used also to detect time conflicts.
                            for sub in devList:
                                # convert raw data into data word
                                d = sub.to_words(sub.properties, sub.raw_output)
                                # print('%s data:' % sub.name, d)

                                if len(d) != len(t):  # sanity check.
                                    raise LabscriptError('generate_code: %s raw output length %i not consistent with %i times? (should not happen)' % (sub.name, len(d), len(times)))

                                # mark changes
                                chg = np.empty(shape=(len(t),), dtype=np.bool_)
                                chg[0]  = (sub.raw_output[0] != sub.default_value)
                                chg[1:] = ((d[1:] - d[:-1]) != 0)
                                i = indices[chg]

                                # detect conflicts with other devices
                                conflicts[i, rack] |= changes[i, rack]
                                changes[i, rack] = True

                                # save data where output changes
                                data[i, rack+1] = d[chg]

                            if len(dev.child_devices) > 0 and not isinstance(dev, Trigger):
                                rack          = dev.properties['rack']
                                address       = dev.properties['address']
                                channel       = dev.properties['channel']
                                #ID = get_ID(IM.type,rack,address,channel)
                                name = get_channel_name(IM.type, rack, address, channel)
                                #print(dev.name, name, "final values =", dev.final_values)
                                if CRC_CHECK:
                                    #print(dev.name, name, 'CRC =', str(dev.crc))
                                    crc[name] = dev.crc.value()

        if len(special_instructions) > 0:
            # collect special data bits
            # these bits are combined with existing data and cannot cause conflicts
            for dev, instructions in special_instructions.items():
                IM          = dev.parent_device
                clockline   = IM.parent_device
                pseudoclock = clockline.parent_device
                t = pseudoclock.times[clockline]
                indices = np.argwhere(np.isin(times, t)).ravel()

                #if np.count_nonzero(dev.raw_output == dev.default_value) != len(t):
                #    print('%s instr:'%dev.name, instructions)
                #    print('%s raw data:' % dev.name, dev.raw_output)

                if len(dev.raw_output) != len(t):  # sanity check.
                    raise LabscriptError('generate_code: raw output not consistent with times? (should not happen)')

                # convert raw data into data word
                #print(dev.name, type(dev), dev.properties)
                d = dev.to_words(dev.properties, dev.raw_output)
                #print('%s data:' % dev.name, d)

                # check if strobe bit is set somewhere
                if np.count_nonzero(d & BIT_STRB_SH) > 0:
                    if not BIT_STRB_GENERATE:
                        raise LabscriptError("Strobe bit is not generated but in your script 'SKIP' with do_not_toggle_STRB=True is called which uses this bit! Either enable generation of strobe bit (BIT_GENERATE=True) or call 'SKIP' with do_not_toggle_STRB=False to use NOP bit instead of Strobe bit.")
                    special_STRB = True

                # take all non-default values
                if use_prelim_version:
                    default_value = dev.properties['default_value']
                else:
                    default_value = dev.default_value
                mask = (d != default_value)
                if t[-1] not in instructions:
                    # remove last entry when was automatically inserted by labscript, i.e. when its not in instructions
                    mask[-1] = False
                i = indices[mask]

                # combine ALL non-default special data bits with existing data
                # add NOP bit where special bits are without data action
                rack = dev.properties['rack']
                data[i, rack+1] |= np.where(changes[i, rack], d[mask], d[mask] | BIT_NOP_SH)

                # mark all non-default special entries as changed data
                changes[i, rack] |= True

        if False:
            # show all data for debugging
            if ALWAYS_SHOW or (len(data) <= MAX_SHOW):
                show_data(data, info='\ndata (all):', bus_rate=self.bus_rate)
            #save_print('changes:\n', np.transpose(changes))
            #save_print('conflicts:\n', np.transpose(conflicts))

        if np.count_nonzero(conflicts) != 0:
            # time conflicts detected
            conflicts_t  = {}
            conflicts_ch = {}
            for rack in range(self.num_racks):
                conflicts_t[rack] = times[conflicts[:,rack]]
            # go through all channels and collect conflicting channel information
            for pseudoclock in self.child_devices:
                for clockline in pseudoclock.child_devices:
                    t = pseudoclock.times[clockline]
                    indices = np.argwhere(np.isin(times, t)).ravel()
                    for IM in clockline.child_devices:
                        for dev in IM.child_devices:
                            rack    = dev.properties['rack']
                            channel = dev.properties['channel']
                            if len(dev.child_devices) > 0 and not isinstance(dev, Trigger):
                                print('dds channel conflict!')
                                devList = dev.child_devices
                            else:
                                devList = [dev]
                            for sub in devList:
                                d = sub.to_words(sub.properties, sub.raw_output)
                                chg = np.empty(shape=(len(t),), dtype=np.bool_)
                                chg[0] = (sub.raw_output[0] != sub.default_value)
                                chg[1:] = ((d[1:] - d[:-1]) != 0)
                                mask = np.isin(t[chg], conflicts_t[rack])
                                if np.count_nonzero(mask) > 0:
                                    address       = sub.properties['address']
                                    info = (IM.type,  # channel type
                                            rack,  # rack number
                                            address,  # address
                                            indices[chg][mask],  # sample index
                                            t[chg][mask],  # time in seconds
                                            sub.default_value, # invalid value
                                            list(np.concatenate(([sub.default_value], sub.raw_output[chg][:-1]))[mask]), # old value
                                            sub.raw_output[chg][mask])  # new value
                                    if sub.name in conflicts_ch:
                                        old = conflicts_ch[sub.name]
                                        conflicts_ch[sub.name] = (old[i] if i < 3 else old[i] + info[i] for i in range(len(old)))
                                    else:
                                        conflicts_ch[sub.name] = info

            for rack in range(self.num_racks):
                if len(conflicts_t) > 0:
                    indices = np.argsort(conflicts_t[rack])
                    save_print('\n%i time conflicts on %i channels detected:\n' % (len(conflicts_t[rack]), len(conflicts_ch)))
                    save_print('%25s %4s %4s %12s %12s %12s %12s' % ('channel_name','rack','addr','sample','time (s)','old value','new value'))
                    for t in conflicts_t[rack]:
                        for ch, info in conflicts_ch.items():
                            for i in range(len(info[3])):
                                if info[4][i] == t:
                                    if info[0] == TYPE_DO: # digital out
                                        s2 = "0x%02x" % (info[2])
                                        s5 = '-' if info[6][i] == info[5] else ("low" if info[6][i]==0 else "high")
                                        s6 = '-' if info[7][i] == info[5] else ("low" if info[7][i]==0 else "high")
                                        s5 = "low" if info[6][i]==0 else "high"
                                        s6 = "low" if info[7][i]==0 else "high"
                                        s7 = ''
                                    elif info[0] == TYPE_AO: # analog out
                                        s2 = "0x%02x" % (info[2])
                                        s5 = '-' if info[6][i] == info[5] else "%12.6f" % info[6][i]
                                        s6 = '-' if info[7][i] == info[5] else "%12.6f" % info[7][i]
                                        s7 = ''
                                    elif info[0] == TYPE_DDS:
                                        # dds channel
                                        # TODO: we give here the raw_data but from instructions we could recover the user input value.
                                        s2 = "0x%02x" % (info[2])
                                        s5 = '-' if info[6][i] == info[5] else "0x%08x" % int(info[6][i])
                                        s6 = '-' if info[7][i] == info[5] else "0x%08x" % int(info[7][i])
                                        s7 = ''
                                    elif info[0] == TYPE_SP:
                                        # special data
                                        # note: since address = None will never cause conflict but might appear with other conflicts when at same time
                                        s2 = '-'
                                        s5 = '-' if info[6][i] == SP_INVALID_VALUE else "0x%8x" % info[6][i]
                                        s6 = '-' if info[7][i] == SP_INVALID_VALUE else "0x%8x" % info[7][i]
                                        s7 = ' ignore'
                                    save_print('%25s %4i %4s %12i %12.6f %12s %12s%s'%(ch, info[1], s2, info[3][i], info[4][i], s5, s6, s7))
                        save_print()
            save_print()
            raise LabscriptError('%i time conflicts detected! (abort compilation)' % (np.count_nonzero(conflicts)))

        # detect samples where anything changes on any rack
        chg = np.any(changes, axis=1)

        # update: we keep first sample under any conditions (marked with NOP if nothing happens)
        # where special data STRB bit is set we do not toggle strobe bit in data.
        # however, the board always executes first instruction regardless of first strobe bit.
        # therefore we give an error below and in SKIP() when for first sample STRB bit is set.
        # here we retain first sample such that at least one sample is before any sample with STRB bit.
        # if first sample does not contain data it will be marked with NOP bit below.
        #if special_STRB: chg[0] = True
        chg[0] = True

        # we always keep the last sample (marked with NOP if nothing happens)
        chg[-1] = True

        # remove samples without changes on any rack
        data = data[chg]
        changes = changes[chg]

        # add NOP for racks without changes
        for rack in range(self.num_racks):
            data[:,rack+1][~changes[:,rack]] = BIT_NOP_SH

        # insert toggle strobe into data
        if BIT_STRB_GENERATE:
            if special_STRB:
                # we do not want to toggle all data
                for rack in range(self.num_racks):
                    mask = np.array(data[:,rack+1] & BIT_STRB_SH == 0, dtype=np.uint32)
                    if mask[0] == 0:
                        # first sample has strobe bit set which does not work (see notes above).
                        if data[0,0] == 0: raise LabscriptError("you have called 'SKIP' with do_not_toggle_STRB=True for time = 0 which does not work! use 'SKIP' with do_not_toggle_STRB=False.")
                    #print(mask)
                    #print(np.cumsum(mask) & 1)
                    if False: # use XOR
                        strb = (np.cumsum(mask) & 1) * BIT_STRB_SH
                        data[:,rack+1] ^= np.concatenate((np.array([0],dtype=np.uint32),strb[:-1]))
                    else: # use OR and mask (TODO: check what is faster)
                        strb = (np.cumsum(mask) & 1) * BIT_STRB_SH
                        data[:,rack+1] = (data[:,rack+1] & BIT_STRB_MASK) | strb
            else:
                # toggle strobe for all data
                if len(data) & 1 == 1: strb = np.tile(np.array([0,BIT_STRB_SH],dtype=np.uint32),reps=(len(data)+1)//2)[:-1]
                else:                  strb = np.tile(np.array([0,BIT_STRB_SH],dtype=np.uint32),reps=len(data)//2)
                for rack in range(self.num_racks):
                    data[:,rack+1] |= strb

        # save matrix for each board to file
        # TODO: had to add device name also to devices otherwise get error. however now we create board#_devices/board#.
        save_print('generate_code create group', self.name)
        group = hdf5_file['devices'].create_group(self.name)
        group.create_dataset('%s_matrix' % self.name, compression=config.compression, data=data)

        # save final states
        save_print('final values:', final_values)
        d = to_string(final_values)
        group.create_dataset('%s_final' % self.name, shape=(1,), dtype='S%i' % (len(d)), data=d.encode('ascii', 'ignore'))

        # save CRC if enabled
        if CRC_CHECK:
            save_print('CRC:', crc)
            d = to_string(crc)
            group.create_dataset('%s_CRC' % self.name, shape=(1,), dtype='S%i' % (len(d)), data=d.encode('ascii', 'ignore'))

        # save extra worker arguments into hdf5. we must convert everything into a string and convert it back in worker.
        d = to_string(self.worker_args_ex)
        group.create_dataset('%s_worker_args_ex' % self.name, shape=(1,), dtype='S%i' % (len(d)), data=d.encode('ascii', 'ignore'))

        # TODO: add another group with all used channels. this can be used by runviewer to avoid displaying unused channels.
        #      channels should be already saved somehow in hdf5? so maybe one can add this info for each channel there?

        if self.stop_time != exp_time:
            raise LabscriptError('%s stop time %.3e != experiment time %.3e!' % (self.stop_time, exp_time))

        # save stop_time and if master pseudoclock = primary board into hdf5
        # for master_pseudoclock t0 = 0
        self.set_property('is_master_pseudoclock', self.is_master_pseudoclock, location='device_properties')
        self.set_property('stop_time', self.stop_time, location='device_properties')

        save_print("'%s' generating code (3) %.3fms ..." % (self.name, (get_ticks() - total_time) * 1e3))

        # save if primary board and list of secondary boards names, or name of primary board.
        # the names identify the worker processes used for interprocess communication.
        if self.is_primary:
            self.set_property('is_primary', True, location='connection_table_properties', overwrite=False)
            self.set_property('boards', [s.name for s in self.secondary_boards],
                              location='connection_table_properties', overwrite=False)
        else:
            self.set_property('is_primary', False, location='connection_table_properties', overwrite=False)
            self.set_property('boards', [self.primary_board.name], location='connection_table_properties', overwrite=False)

        t_end = get_ticks()
        t_new = (t_end - t_start) * 1e3
        if ALWAYS_SHOW or (len(data) <= MAX_SHOW):
            show_data(data, info='data: (%.3fms)' % (t_new), bus_rate=self.bus_rate)

        save_print("'%s' generating code (4) %.3fms ..." % (self.name, (get_ticks() - total_time) * 1e3))

        # TODO: generate_code is not called for secondary boards? so have to call it manually.
        #       for iPCdev needed to comment generate_code in intermediate_device, then was working.
        #       here does not help?!
        for secondary in self.secondary_boards:
            save_print('%s call generate code for %s' % (self.name, secondary.name))
            secondary.generate_code(hdf5_file)

        # experiment duration
        if   exp_time >= 1.0:  tmp = '%.3f s'  % (exp_time)
        elif exp_time > 1e-3:  tmp = '%.3f ms' % (exp_time * 1e3)
        elif exp_time > 1e-6:  tmp = '%.3f us' % (exp_time * 1e6)
        else:                  tmp = '%.1f ns' % (exp_time * 1e9)
        save_print("'%s' generating code (5) %.3fms done. experiment duration %s." % (self.name, (get_ticks() - total_time) * 1e3, tmp))

    def SKIP(self, time, rack=0, do_not_toggle_STRB=False):
        "set NOP bit or do not toggle strobe bit at given time = time is waited but no output generated"
        if do_not_toggle_STRB:
            if not BIT_STRB_GENERATE:
                raise LabscriptError("Strobe bit is not generated but in your script 'SKIP' with do_not_toggle_STRB=True is called which uses this bit! Either enable generation of strobe bit (BIT_GENERATE=True) or call 'SKIP' with do_not_toggle_STRB=False to use NOP bit instead of Strobe bit.")
            if time == 0: raise LabscriptError("SKIP: you have specified do_not_toggle_STRB for time = 0 which is not allowed! use NOP bit instead.")
            bit = BIT_STRB_SH
        else:
            bit = BIT_NOP_SH
        print('insert SKIP bit at time %f, rack %i'%(time, rack))
        if time in self.special_data[rack].instructions:
            self.special_data[rack].instructions[time] |= bit
        else:
            self.special_data[rack].add_instruction(time,bit)

    def WAIT(self, time, label='WAIT', rack=0):
        "set stop bit at given time = top board and wait for restart trigger"
        bit = BIT_STOP_SH
        print("%s: insert WAIT bit at time %f, rack %i, label '%s'"%(self.name, time, rack, label))
        if time in self.special_data[rack].instructions:
            # action at same time
            # action is executed at the given time. actions after this time are delayed by wait.
            self.special_data[rack].instructions[time] |= bit
        else:
            # no action at this time.
            # but an action might be added later at same time.
            self.special_data[rack].add_instruction(time, bit)
        add_time_marker(t=time, label=label, color=None, verbose=False)

    def IRQ(self, time, rack=0):
        "set data IRQ bit at given time = generates an IRQ at given time. might be used to trigger events without polling."
        bit = BIT_IRQ_SH
        print('%s: insert IRQ bit at time %f, rack %i'%(self.name, time, rack))
        if time in self.special_data[rack].instructions:
            self.special_data[rack].instructions[time] |= bit
        else:
            self.special_data[rack].add_instruction(time,bit)

    def set_start_trigger(self, source, level):
        if STR_INPUTS in self.worker_args_ex: inputs = self.worker_args_ex[STR_INPUTS]
        else:                                 inputs = {}
        inputs[STR_TRIG_START] = (source, level)
        self.worker_args_ex[STR_INPUTS] = inputs

    def set_restart_trigger(self, source, level):
        if STR_INPUTS in self.worker_args_ex: inputs = self.worker_args_ex[STR_INPUTS]
        else:                                 inputs = {}
        inputs[STR_TRIG_RESTART] = (source, level)
        self.worker_args_ex[STR_INPUTS] = inputs

    def set_stop_trigger(self, source, level):
        if STR_INPUTS in self.worker_args_ex: inputs = self.worker_args_ex[STR_INPUTS]
        else:                                 inputs = {}
        inputs[STR_TRIG_STOP] = (source, level)
        self.worker_args_ex[STR_INPUTS] = inputs

    def set_ctrl_in(self, ctrl_in):
        """
        set input control register. this can be either a dictionary as given for connection table or the register value directly.
        this overwrites what might be given in connection table.
        """
        if STR_INPUTS in self.worker_args_ex: inputs = self.worker_args_ex[STR_INPUTS]
        else:                                 inputs = {}
        if not isinstance(ctrl_in, dict):
            ctrl_in = get_io_selection(ctrl_in, input=True, return_NONE=False)
        for key, value in ctrl_in.items():
            inputs[key] = value
        self.worker_args_ex[STR_INPUTS] = inputs

    def set_ctrl_out(self, ctrl_out):
        """
        set out control register. this can be either a dictionary as given for connection table or the register value directly.
        this overwrites what might be given in connection table.
        """
        if STR_OUTPUTS in self.worker_args_ex: outputs = self.worker_args_ex[STR_OUTPUTS]
        else:                                  outputs = {}
        if not isinstance(ctrl_out, dict):
            ctrl_out = get_io_selection(ctrl_out, input=False, return_NONE=False)
        for key, value in ctrl_out.items():
            outputs[key] = value
        self.worker_args_ex[STR_OUTPUTS] = outputs

    def set_ext_clock(self, enable, ignore_clock_loss=False):
        """
        enable or disable external clock.
        when enabled ensure that when experiment is started the external clock is available and stable.
        if not, starting of the experiment will give an error.
        for secondary boards an external clock is mandatory. this can be a shared clock for all boards,
        or a clock provided from the primary board.
        use this option for fast tests. for permanent settings use connection table.
        if ignore_clock_loss = True: then short clock loss is tolerated without error.
                                     clock loss over more than few clock cycles can cause
                                     that PLL takes a long time to relock or it might not relock at all.
                                     in this case a reset is necessary.
                                     ATTENTION: this option might cause that boards might get out of synchronization!
        """
        self.worker_args_ex[STR_EXT_CLOCK]         = enable
        self.worker_args_ex[STR_IGNORE_CLOCK_LOSS] = ignore_clock_loss

    def set_sync_params(self, wait=None, phase_ext=None, phase_det=None):
        """
        set sync_phase or/and sync_wait.
        wait = delay in units of 10ns. 0 for secondary board. ca. 10 for primary board. use to coarse adjust delay between boards.
        phase_ext = external clock phase in degrees. 0 on primary board. on secondary board use to fine-adjust delay between boards.
        phase_det = detection clock phase in degrees. does not change timing, but when you see random jumps of +/-10ns add or subtract ca. 90 degrees.
        this function overwrites what might be given in connection table or/and on the SD card.
        """
        if wait is not None:
            self.worker_args_ex[STR_SYNC_WAIT] = wait
        if (phase_ext is not None) or (phase_det is not None):
            ext = ((int)(phase_ext*PHASE_360/360)) & SYNC_PHASE_MASK if phase_ext is not None else 0
            det = ((int)(phase_det*PHASE_360/360)) & SYNC_PHASE_MASK if phase_det is not None else 0
            self.worker_args_ex[STR_SYNC_PHASE] = (ext<<SYNC_PHASE_BITS) | det

    def set_strb_delay(self, strb_delay):
        """
        set strobe 0 and strobe 1 timings
        bits  0-3  = strobe 0 start time when strobe goes high in units of 10ns
        bits  4-7  = strobe 0 end time when strobe goes low in units of 10ns. when 0 toggles.
        bits  8-11 = strobe 1 start time when strobe goes high in units of 10ns
        bits 12-15 = strobe 1 end time when strobe goes low in units of 10ns. when 0 toggles.
        """
        self.worker_args_ex[STR_STRB_DELAY] = strb_delay

    def set_cycles(self, cycles, restart):
        """
        set number of cycles. and restart bit in configuration.
        this overwrites what might be given in connection table.
        """
        if STR_CONFIG in self.worker_args_ex: config = self.worker_args_ex[STR_CONFIG]
        else:                                 config = CONFIG_RUN_64 if self.num_racks == 1 else CONFIG_RUN_96
        if restart: self.worker_args_ex[STR_CONFIG] = config | CTRL_RESTART_EN
        else:       self.worker_args_ex[STR_CONFIG] = config ^ CTRL_RESTART_EN
        self.worker_args_ex[STR_CYCLES] = cycles

    # ID bits definition. sum must be 32.
ID_channel_bits  = 8
ID_address_bits  = 8
ID_rack_bits     = 8
ID_type_bits     = 8
# derived bit masks
ID_channel_mask  = (1 << ID_channel_bits) - 1
ID_address_mask  = (1 << ID_address_bits) - 1
ID_rack_mask     = (1 << ID_rack_bits) - 1
ID_type_mask     = (1 << ID_type_bits) - 1
# derived number of bits to shift
ID_channel_shift = 0
ID_address_shift = ID_channel_bits
ID_rack_shift    = ID_channel_bits + ID_address_bits
ID_type_shift    = ID_channel_bits + ID_address_bits + ID_rack_bits

def get_ID(type, rack, address, channel):
    # calculate unique ID (integer) for given channel
    # type = device type: TYPE_AO, TYPE_DO, TYPE_DDS
    # rack = rack number: 0,1
    # address = device address. this can be the address of the IntermediateDevice (for digital out) or of the channel itself (analog device)
    # channel = channel number: 0,1,..
    return ((type & ID_type_mask) << ID_type_shift) | \
           ((rack & ID_rack_mask) << ID_rack_shift) | \
           ((address & ID_address_mask) << ID_address_shift) | \
           ((channel & ID_channel_mask) << ID_channel_shift)

def get_type(ID):
    # get device type from ID
    return (ID >> ID_type_shift) & ID_type_mask

def get_rack(ID):
    # get rack number from ID
    return (ID >> ID_rack_shift) & ID_rack_mask

def get_address(ID):
    # get address from ID
    return (ID >> ID_address_shift) & ID_address_mask

def get_channel(ID):
    # get channel from ID
    return (ID >> ID_channel_shift) & ID_channel_mask

def unpack_ID(ID):
    # inverse of get ID (see there)
    return [get_type(ID),get_rack(ID),get_address(ID),get_channel(ID)]

def get_channel_name(type, rack, address, channel):
    # get channel name as unique string containing type, rack, address channel
    #type, rack, address, channel = unpack_ID(ID)
    if   type == TYPE_AO : return "a0_%x.%02x_%i" % (rack, address, channel)
    elif type == TYPE_DO : return "do_%x.%02x_%i" % (rack, address, channel)
    elif type == TYPE_DDS: return "dds_%x.%02x_%i" % (rack, address, channel)
    else: return "??_%x.%02x_%i" % (rack, address, channel)

# finds all channels of given IM device
# IM = intermediate device (Analog/Digital/DDSChannels) connection object
# returns dictionary with:
#   key = channel name as given to AnaolgChannel, DigitalChannel
#   value = list of [ID, properties, child connection object, name, unit conversion class]
def get_channels(IM):
    #get all digital and analog outputs from intermediate device
    child_list = {}
    if IM.device_class == 'AnalogChannels':
        #num_AO = IM.properties['num_AO'] # AnalogChannels
        #save_print("'%s' with %i analog outputs:" % (IM.name, len(IM.child_list)))
        for child_name, child in IM.child_list.items():
            #rack, address, channel = child.properties['address'].split('/')
            rack    = int(child.properties['rack'])
            address = int(child.properties['address'])
            channel = int(child.properties['channel'])
            ID = get_ID(type=TYPE_AO,rack=rack,address=address,channel=channel)
            ch_name = get_channel_name(TYPE_AO, rack, address, channel)
            #save_print("  '%s' %i/0x%0x/%i" % (child.name, rack, address, channel))
            #note: it seems that these properties are intended only for 'base_unit' and not for derived units calculated by unit conversion class
            #      if min/max are given in unit conversion class we use calculated voltage limits.
            # TODO: we give here the number of digits in Volts, which is correct, but the number of digits in 'unit' is wrong.
            #       it seems to go in the opposite direction. e.g. with decimals=4 and from_base multiplies by 10,
            #       decimals are increased to 5 instead of decreased to 3. looks like a bug in labscript or can this be set somehow?
            props = default_ao_props.copy() # Attention: enforce copying otherwise we change default_ao_props!
            if child.unit_conversion_class is not None:
                # import class. importing/reloading is not working well in python and you might experience problems here.
                unit_conversion_class = get_unit_conversion_class(child.unit_conversion_class)
                unit = child.unit_conversion_params['unit']
                V_min, V_max, min, max = unit_conversion_class.get_limits(child.unit_conversion_params) # use class to get voltage limits
                props['min'] = V_min
                props['max'] = V_max
                note = ''
            else:
                unit_conversion_class = None
                unit = 'V'
                V_min = min = props['min']
                V_max = max = props['max']
                note = '(default)'
            save_print("%-10s %-35s: min %10.4f %-3s = %10.4f V, max %10.4f %-3s = %10.4f V %s" % (ch_name, child.name, min, unit, V_min, max, unit, V_max, note))
            child_list[child_name] = [ID,props,child,ch_name,unit_conversion_class]
    elif IM.device_class == 'DigitalChannels':
        #num_DO = IM.properties['num_DO'] # DigitalChannels
        #save_print("'%s' with %i digital outputs:" % (IM.name, len(IM.child_list)))
        for child_name, child in IM.child_list.items():
            #rack, address, channel = child.properties['address'].split('/')
            rack    = int(child.properties['rack'])
            address = int(child.properties['address'])
            channel = int(child.properties['channel'])
            #save_print("  '%s' %i/0x%0x/%i" % (child.name, rack, address, channel))
            props = default_do_props
            ID = get_ID(type=TYPE_DO, rack=rack, address=address, channel=channel)
            ch_name = get_channel_name(TYPE_DO, rack, address, channel)
            child_list[child_name] = [ID,props,child,ch_name,None]
    elif IM.device_class == 'DDSChannels':
        for dds_name, dds in IM.child_list.items():
            rack    = int(dds.properties['rack'])
            address = int(dds.properties['address'])
            channel = int(dds.properties['channel'])
            props = default_DDS_props
            ID = get_ID(type=TYPE_DDS, rack=rack, address=address, channel=channel)
            ch_name = get_channel_name(TYPE_DDS, rack, address, channel)
            child_list[dds_name] = [ID, props, dds, ch_name, None]
            if False:
                for child_name, child in dds.child_list.items():
                    #rack, address, channel = dds.properties['address'].split('/')
                    rack    = int(child.properties['rack'])
                    address = int(child.properties['address'])
                    channel = int(child.properties['channel'])
                    props = default_DDS_props
                    print("get_channel '%s' properties:" % (dds_name), dds.properties)
                    props.update(dds.properties) # TODO: save device.properties from connection table definition
                    ID = get_ID(type=TYPE_DDS, rack=rack, address=address, channel=channel)
                    ch_name = get_channel_name(TYPE_DDS, rack, address, channel)
                    child_list[child_name] = [ID,props,child,ch_name,None]
    else:
        raise LabscriptError("get_channels: device '%s' class '%s' unknown!" % (IM.name, IM.device_class))
    return child_list

