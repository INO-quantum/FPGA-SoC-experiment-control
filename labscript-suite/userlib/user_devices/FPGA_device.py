#####################################################################
# FPGA-SoC device by Andreas Trenkwalder
# created 6/4/2021 (heavily adapted from RFBlaster.py)
# works as PseudoClockDevice
#####################################################################

from __future__ import generator_stop
import labscript.labscript
from labscript import PseudoclockDevice, Pseudoclock, ClockLine, IntermediateDevice, DDS, DigitalOut, AnalogOut, set_passed_properties, LabscriptError, config, Output
from labscript_devices import BLACS_tab, runviewer_parser
from labscript_utils.setup_logging import setup_logging
from labscript_utils import import_or_reload
from labscript_utils.unitconversions import get_unit_conversion_class
from labscript_utils.qtwidgets.toolpalette import ToolPaletteGroup
from labscript_utils.qtwidgets.digitaloutput import DigitalOutput
from labscript_utils.qtwidgets.analogoutput import AnalogOutput
import logging

# used for unit conversion inverse function
#from scipy.optimize import newton

import numpy as np
from time import sleep
from time import perf_counter as get_ticks
from time import process_time as get_ticks2
import struct
import h5py, labscript_utils.h5_lock
#import libusb
#libusb.config(LIBUSB=None)

import sys

from qtutils.qt.QtWidgets import *

# note: do not import MOGLabs_QRF here!
#       it seems Python cannot handle circular references!
#       the error occurred during compilation of connection table with BLACS.
#from user_devices.MOGLabs_QRF import MOGLabs_QRF

# reduce number of log entries in logfile (labscript-suite/logs/BLACS.log)
log_level = [logging.CRITICAL, logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG, logging.NOTSET][2]

# every time after compiling connection table I get strange BrokenPipeError for any print command within FPGA_Tab!?
# sometimes crashes so badly that BLACS cannot be closed anymore and have to manually kill it! this is super annoying.
# implement a save_print command and use everywhere!
def save_print(*args):
    try:
        print(*args)
    except BrokenPipeError:
        pass

#default connection
PRIMARY_IP   = '192.168.1.10'
SECONDARY_IP = '192.168.1.11'
DEFAULT_PORT = '49701'
SOCK_TIMEOUT = 5.0                          # timeout for send_recv_data in seconds. I see sometimes very long responds time. maybe USB-Ethernet-adapter?
SOCK_TIMEOUT_SHORT = 1.0                    # timeout for init_connection in seconds. this is shorter for fast tests withouts boards.

ADD_WORKER  = '_worker'                     # worker name = board name + ADD_WORKER
AO_NAME     = 'Analog Outputs'              # GUI button name analog outputs
DO_NAME     = 'Digital Outputs'             # GUI button name digital outputs
FPGA_NAME   = 'FPGA board'                  # GUI button name FPGA board

#global settings
MAX_FPGA_RATE   = 10e6                      # maximum bus output rate of FPGA in Hz. 30MHz contigously should be possible but not tested.
MAX_RACKS       = 2                         # 2 racks can share one clockline
MAX_SHOW        = 20                        # maximum number of samples untilrun which data is shown
ALWAYS_SHOW     = True                      # if true always shows first and last MAX_SHOW/2 data

def epsilon(number):
    """
    returns smallest epsilon for which number + epsilon != number.
    note: sys.float_info.epsilon = epsilon(1.0)
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
MAX_BUS_RATE     = 1e6
CLOCK_RESOLUTION = get_clock_resolution(MAX_BUS_RATE)
MAX_TIME         = (2**32)-1
MAX_TIME_SECONDS = MAX_TIME*CLOCK_RESOLUTION
CLOCK_LIMIT      = get_clock_limit(MAX_BUS_RATE)
save_print('FPGA_board: maximum bus rate %.3f MHz gives resolution %.3f ns and max time %.3f s (clock limit = bus rate + %.3f Hz)' % (MAX_BUS_RATE/1e6, CLOCK_RESOLUTION*1e9, MAX_TIME_SECONDS, CLOCK_LIMIT - MAX_BUS_RATE))

# smallest time step and start time in WORD units (ticks)
TIME_STEP       = 1                         # must be 1
START_TIME      = 0                         # note: FPGA board can start at time 0 since trigger delay is corrected.
TIME_ROUND_DECIMALS = 10                    # time is rounded internally by labscript to 10 decimals = 100ps
TIME_PRECISION  = 10.0**(-TIME_ROUND_DECIMALS) # time round precision in seconds
UPDATE_TIME_MS  = 500                       # update time of BLACS board status in ms

#bus data structure
ADDR_SHIFT      = 16                        # first bit of address 
ADDR_MASK       = 0x7f                      # address mask (7bits, strobe is ignored since generated by FPGA)
ADDR_MASK_SH    = np.array(ADDR_MASK<<ADDR_SHIFT,dtype=np.uint32)   # address mask shifted
DATA_MASK       = np.array(0xffff               ,dtype=np.uint32)   # data field mask (16bits)
DATA_ADDR_MASK  = DATA_MASK|ADDR_MASK_SH    # combined data field + address mask (23bits)
MAX_ADDRESS     = ADDR_MASK                 # largest possible address

# default special data bits
BIT_NOP             = 31                        # no operation bit (at the moment cannot be changed since is hard-coded in driver!)
BIT_STOP            = 30                        # data stop trigger bit
BIT_TRST            = 29                        # time reset bit (not implemented)
BIT_IRQ             = 28                        # data IRQ bit
BIT_STRB            = 23                        # data strobe bit
BIT_NOP_SH          = (1<<BIT_NOP)
BIT_STOP_SH         = (1<<BIT_STOP)
BIT_IRQ_SH          = (1<<BIT_IRQ)
BIT_STRB_SH         = (1<<BIT_STRB)
BIT_STRB_MASK       = np.array(~BIT_STRB_SH,dtype=np.uint32)
SPECIAL_BITS        = BIT_NOP_SH | BIT_STOP_SH |BIT_IRQ_SH | BIT_STRB_SH

# device types (used for ID)
# TODO: add DDS
TYPE_board      = 0
TYPE_DO         = 1
TYPE_AO         = 2
TYPE_SP         = 3

# if True save/retrieve worker args with str/eval from hdf5 file, otherwise with to_string/from_string.
# str/eval is 10x faster, to/from_string is more secure and more flexible to include other data.
decode_string_with_eval = False

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

# analog out resolution, true max and min output values and +/-5V reference values
# see Texas Instruments, DAC712 datasheet, rev. July 2009, Table 1, p.13
AO_BITS       = 16              # number of bits
AO_RESOLUTION = 20/(2**AO_BITS) # 0x0001 = 305uV
AO_MAX = 10.0-AO_RESOLUTION     # 0x7fff =  +9.999695V
AO_MIN = -10.0                  # 0x8000 = -10.000000V
AO_MAX_WORD    = 0x7fff         # 0x7fff =  +9.999695V
AO_MIN_WORD    = 0x8000         # 0x8000 = -10.000000V
AO_ZERO_WORD   = 0x0000         # 0x0000 =  0.000000V
AO_5V_POS_WORD = 0x4000         # 0x4000 = +5.000000V
AO_5V_NEG_WORD = 0xc000         # 0xc000 = -5.000000V

def V_to_word(volts):
    "convert voltage (scalar or np.array) into low 16 bits of 32bit data word."
    return np.array(np.round((volts-AO_MIN)*(2**AO_BITS-1)/(AO_MAX-AO_MIN))-(2**(AO_BITS-1)),dtype=np.uint32) & DATA_MASK

def word_to_V(word):
    "convert 16bit data word (scalar or np.array) into voltage"
    return np.where(word & 0x8000, np.array(word, dtype=float)-(2**(AO_BITS-1)), (2**(AO_BITS-1)) + np.array(word, dtype=float))*(AO_MAX-AO_MIN)/(2**AO_BITS-1) + AO_MIN

# default analog and digital output properties
# these define the capabilities of the analog outputs after unit conversion, i.e. in the base unit 'V'.
default_ao_props = {'base_unit':'V', 'min':-10.0, 'max':10.0,'step':0.1, 'decimals':4}
default_do_props = {'xcolor':'red'}

# default values are inserted automatically by labscript for times before channel is used
# these values are masked below and are not sent to boards.
# to distingjish between user inserted values and auto-inserted we keep them outside valid range.
SP_AUTO_VALUE = 0
AO_AUTO_VALUE = 2*default_ao_props['min']-1.0 # TODO: with unit version this might be a valid user-inserted value!? I think nan is not possible here.
DO_AUTO_VALUE = 2

# if True then primary board returns error also when a secondary board is in error state. default = False.
stop_primary_on_secondary_error = False

# runviewer options
runviewer_show_units = True                 # if True show user units in runviewer, otherwise show output in Volts
runviewer_add_start_time = False            # if True adds time START_TIME to data if not given by user. value is last value of last instruction.

# tests (use only for testing!)
TEST_TIMING_ERROR       = False             # induce timing error at half of data
TEST_PRIM               = None              # True = primary board, False = secondary board(s), None = all boards

# timeout for interprocess communication wait event
EVT_TIMEOUT     = 5000

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
SERVER_CONFIG               = make_cmd(0x25, 42)
SERVER_WRITE                = make_cmd(0x27,  6)
SERVER_START                = make_cmd(0x28,  6)
SERVER_STOP                 = make_cmd(0x29,  2)
SERVER_STATUS               = make_cmd(0x08,  2)       # polls actual status
SERVER_STATUS_RSP           = make_cmd(0x08, 14)       # response: SERVER_STATUS
SERVER_STATUS_IRQ           = make_cmd(0x09,  2)       # allows to wait for update/end instead of polling
SERVER_STATUS_IRQ_RSP       = make_cmd(0x09, 14)       # response: SERVER_STATUS_IRQ
SERVER_STATUS_FULL          = make_cmd(0x07,  2)       # full status information displayed in board console
SERVER_STATUS_FULL_RSP_8    = make_cmd(0x07,274)       # response: full status  8 bytes per samples
SERVER_STATUS_FULL_RSP_12   = make_cmd(0x07,278)       # response: full status 12 bytes per samples
SERVER_SET_SYNC_PHASE       = make_cmd(0x0c,  6)       # set sync phase. struct client_data32
SERVER_GET_INFO             = make_cmd(0x0d,  2)       # get info
SERVER_GET_INFO_RSP         = make_cmd(0x0d, 10)       # response get info: struct client_data64

# number of bytes per standard server command (should be 2)
SERVER_CMD_NUM_BYTES = struct.calcsize('<2s')

#return packed bytes to configure server (SERVER_CONFIG)
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
    return struct.pack(CONFIG_STRUCT_FORMAT, cmd, clock_Hz, scan_Hz, config, ctrl_trg, ctrl_out, reps, trans, strb_delay, sync_wait, sync_phase)

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

#returns unpacked bytes with client_data32 structure from server [cmd, data32]
def from_client_data32(bytes):
    return struct.unpack('<2sI', bytes)
    
#returns unpacked bytes with client_status structure from server:
# 16bit: command, must be SERVER_STATUS_RSP or SERVER_STATUS_IRQ_RSP
# 32bit: FPGA status register bits
# 32bit: board_time
# 32bit: board_samples
def from_client_status(bytes):
    return struct.unpack('<2s3I', bytes)

# worker arguments
STR_CONFIG              = 'config'
STR_CONFIG_MANUAL       = 'config_manual'
STR_INPUTS              = 'inputs'
STR_OUTPUTS             = 'outputs'
STR_EXT_CLOCK           = 'ext_clock'
STR_IGNORE_CLOCK_LOSS   = 'ignore_clock_loss'
STR_SYNC_WAIT           = 'sync_wait'
STR_SYNC_PHASE          = 'sync_phase'
STR_CYCLES              = 'num_cycles'

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
MSG_INPUT_SETTING           = "board '%s' input settings 0x%x %s"
MSG_OUTPUT_SETTING          = "board '%s' output settings 0x%x %s"
QUESTION_IGNORE_CLOCK_LOSS  = "Do you really want to ignore clock loss on board '%s'? Attention: the timing between several boards might get out of sync!"
QUESTION_SYNC_OUT           = "Do you really want to disable sync out signal of board '%s'? Attention: secondary boards will not get triggered!"
QUESTION_START_TRG          = "Do you really want to disable external trigger for board '%s'? Attention: the timing between the boards will be undefined!"
QUESTION_EXT_CLOCK          = "Do you really want to disable external clock for board '%s'? Attention: the timing between the boards will be undefined!"

# FPGA control register bits
CTRL_RESET                  = 1<<0           # reset enabled (not settable by user)
CTRL_READY                  = 1<<1           # server ready (not settable by user)
CTRL_RUN                    = 1<<2           # run enabled (not settable by user)
CTRL_RESTART_EN             = 1<<4           # automatic restart
CTRL_AUTO_SYNC_EN           = 1<<5           # auto-sync enabled: enable to detect start trigger with detection clock and sync_delay.
CTRL_AUTO_SYNC_PRIM         = 1<<6           # auto-sync primary board (not used at the moment)
CTRL_AUTO_SYNC_FET          = 1<<7           # auto-sync enable FET = reflect pulse
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
# TODO: have added start trigger here. need a compiler option.
CONFIG_RUN_64               = CTRL_IRQ_EN|CTRL_IRQ_END_EN|CTRL_IRQ_FREQ_EN|CTRL_ERR_LOCK_EN
CONFIG_RUN_RESTART_64       = CONFIG_RUN_64|CTRL_IRQ_RESTART_EN|CTRL_RESTART_EN
CONFIG_RUN_96               = CONFIG_RUN_64|CTRL_BPS96
CONFIG_RUN_RESTART_96       = CONFIG_RUN_RESTART_64|CTRL_BPS96

# FPGA status register bits
STATUS_RESET                = 1<<0           # reset active
STATUS_READY                = 1<<1           # ready state = first data received & not end
STATUS_RUN                  = 1<<2           # running state
STATUS_END                  = 1<<3           # end state = num_samples reached
STATUS_WAIT                 = 1<<4           # wait for restart trigger
STATUS_AUTO_SYNC            = 1<<5           # auto-sync active
STATUS_AS_TIMEOUT           = 1<<6           # auto-sync timeout
STATUS_PS_ACTIVE            = 1<<7           # phase shift active
STATUS_EXT_USED             = 1<<10          # 0/1=internal/external clock is used
STATUS_EXT_LOCKED           = 1<<11          # external clock is locked
STATUS_ERR_TX               = 1<<12          # error TX timeout loading of data
STATUS_ERR_RX               = 1<<13          # error RX not ready
STATUS_ERR_TIME             = 1<<14          # error timing
STATUS_ERR_LOCK             = 1<<15          # error lock lost
STATUS_ERR_TKEEP            = 1<<16          # error tkeep signal
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
STATUS_ERROR                = STATUS_ERR_TX|STATUS_ERR_RX|STATUS_ERR_TIME|STATUS_ERR_LOCK|STATUS_ERR_TKEEP|STATUS_ERR_TKEEP2|STATUS_ERR_TKEEP3

# trigger control register
CTRL_IN_SRC_BITS            = 3
CTRL_IN_LEVEL_BITS          = 2
CTRL_IN_DST_BITS            = (CTRL_IN_SRC_BITS + CTRL_IN_LEVEL_BITS)
CTRL_IN_SRC_MASK            = (1<<CTRL_IN_SRC_BITS)-1;
CTRL_IN_LEVEL_MASK          = (1<<CTRL_IN_LEVEL_BITS)-1;
CTRL_IN_DST_MASK            = (1<<CTRL_IN_DST_BITS)-1;

# trigger destination offsets
CTRL_IN_DST_START           = 0*CTRL_IN_DST_BITS   # start trigger
CTRL_IN_DST_STOP            = 1*CTRL_IN_DST_BITS   # stop trigger
CTRL_IN_DST_RESTART         = 2*CTRL_IN_DST_BITS   # restart trigger
CTRL_IN_DST_DATA_NOP        = 3*CTRL_IN_DST_BITS   # data NOP bit (default 31)
CTRL_IN_DST_DATA_STRB       = 4*CTRL_IN_DST_BITS   # data strobe bit (default 23)
CTRL_IN_DST_DATA_IRQ        = 5*CTRL_IN_DST_BITS   # data IRQ bit

# trigger sources
CTRL_IN_SRC_NONE            = 0                     # no trigger input
CTRL_IN_SRC_IN0             = 1                     # ext_in[0]
CTRL_IN_SRC_IN1             = 2                     # ext_in[1]
CTRL_IN_SRC_IN2             = 3                     # ext_in[2]
CTRL_IN_SRC_DATA_20         = 5                     # data bits 20-23
CTRL_IN_SRC_DATA_24         = 6                     # data bits 24-27
CTRL_IN_SRC_DATA_28         = 7                     # data bits 28-31

# trigger levels
CTRL_IN_LEVEL_LOW           = 0                     # level low
CTRL_IN_LEVEL_HIGH          = 1                     # level higth
CTRL_IN_EDGE_FALLING        = 2                     # edge falling
CTRL_IN_EDGE_RISING         = 3                     # edge rising
# data bits offset
CTRL_IN_DATA_0              = 0                     # offset bit 0
CTRL_IN_DATA_1              = 1                     # offset bit 1
CTRL_IN_DATA_2              = 2                     # offset bit 2
CTRL_IN_DATA_3              = 3                     # offset bit 3

# define trigger input list for user to select in GUI. for sources/levels give True for default selection
IN_SRC_NONE     = 'None'
in_dests        = {'start trigger'  : CTRL_IN_DST_START,
                   'stop trigger'   : CTRL_IN_DST_STOP,
                   'restart trigger': CTRL_IN_DST_RESTART,
                   'NOP bit'        : CTRL_IN_DST_DATA_NOP,
                   'IRQ bit'        : CTRL_IN_DST_DATA_IRQ,
                   'STRB bit'       : CTRL_IN_DST_DATA_STRB}
in_sources      = {IN_SRC_NONE      : CTRL_IN_SRC_NONE,
                   'input 0'        : CTRL_IN_SRC_IN0,
                   'input 1'        : CTRL_IN_SRC_IN1,
                   'input 2'        : CTRL_IN_SRC_IN2,
                   'data bits 20-23': CTRL_IN_SRC_DATA_20,
                   'data bits 24-27': CTRL_IN_SRC_DATA_24,
                   'data bits 28-31': CTRL_IN_SRC_DATA_28}
in_levels       = {'rising edge'    : CTRL_IN_EDGE_RISING,
                   'falling edge'   : CTRL_IN_EDGE_FALLING,
                   'high level'     : CTRL_IN_LEVEL_HIGH,
                   'low level'      : CTRL_IN_LEVEL_LOW,
                   'offset bit 0'   : CTRL_IN_DATA_0,
                   'offset bit 1'   : CTRL_IN_DATA_1,
                   'offset bit 2'   : CTRL_IN_DATA_2,
                   'offset bit 3'   : CTRL_IN_DATA_3}

# primary and secondary board default trigger settings
# notes:
# - these are default settings when nothing else is selected.
# - you can select 'trigger' in worker_args of board in connection_table. these take precedence over GUI selections.
# - you can select trigger also in GUI. for not defined 'trigger' selections in worker_args, last selections in GUI are restored.
default_in_prim = {'NOP bit'        : ('data bits 28-31','offset bit 3'),
                    'STRB bit'      : ('data bits 20-23','offset bit 3')}
default_in_sec  = {'NOP bit'        : ('data bits 28-31','offset bit 3'),
                   'STRB bit'       : ('data bits 20-23','offset bit 3'),
                   'start trigger'  : ('input 0', 'falling edge')}

def get_ctrl_in(trigger_selection):
    """
    returns trigger control register value from trigger_selection.
    trigger_selection = {dest:(source, level)),dest:(source, level),...}
    dest = key from in_dests. missing destinations are considered as not used.
    source = key from in_sources.
    level = key from in_levels.
    returns 32bit trigger control register value used to configure board.
    """
    register = np.array([0],dtype=np.uint32)
    for dest, value in trigger_selection.items():
        source, level = value
        register[0] |= (in_sources[source]|(in_levels[level]<<CTRL_IN_SRC_BITS))<<in_dests[dest]
    return register[0]

def get_in_selection(register, return_NONE=True):
    """
    returns dictionary with input selections.
    inverse function to get_ctrl_in.
    if return_NONE == True returns also IN_SRC_NONE, otherwise not.
    """
    selection = {}
    for dest,dest_offset in in_dests.items():
        reg_dest = (register >> dest_offset) & CTRL_IN_DST_MASK;
        for src, src_bits in in_sources.items():
            if return_NONE or (src_bits != CTRL_IN_SRC_NONE):
                if (reg_dest & CTRL_IN_SRC_MASK) == src_bits:
                    for level, level_bits in in_levels.items():
                        if ((reg_dest >> CTRL_IN_SRC_BITS) & CTRL_IN_LEVEL_MASK) == level_bits:
                            selection[dest] = (src,level)
                            break
                    break
    if get_ctrl_in(selection) != register:
        save_print('error: get_out_selection does not give consistent result with get_ctrl_in: %x != %x' %(get_ctrl_in(selection), register), selection)
        exit()
    return selection

def is_in_start(ctrl_trg):
    "returns True when start trigger is enabled in trigger control register ctrl_trg"
    return (((ctrl_trg >> CTRL_IN_DST_START) & CTRL_IN_SRC_MASK) != CTRL_IN_SRC_NONE)

def is_in_stop(ctrl_trg):
    "returns True when stop trigger is enabled in trigger control register ctrl_trg"
    return (((ctrl_trg >> CTRL_IN_DST_STOP) & CTRL_IN_SRC_MASK) != CTRL_IN_SRC_NONE)

def is_trg_restart(ctrl_trg):
    "returns True when restart trigger is enabled in trigger control register ctrl_trg"
    return (((ctrl_trg >> CTRL_IN_DST_RESTART) & CTRL_IN_SRC_MASK) != CTRL_IN_SRC_NONE)

def get_in_info(ctrl_trg):
    "returns short info string with trigger selections"
    info = []
    if is_in_start(ctrl_trg):      info += ['start']
    if is_in_stop(ctrl_trg):       info += ['stop']
    if is_trg_restart(ctrl_trg):    info += ['restart']
    if len(info) > 0: return "(" + "|".join(info) + ")"
    else:             return ""

# output control register
CTRL_OUT_SRC_BITS           = 4
CTRL_OUT_LEVEL_BITS         = 2
CTRL_OUT_DST_BITS           = CTRL_OUT_SRC_BITS + CTRL_OUT_LEVEL_BITS
CTRL_OUT_SRC_MASK           = (1<<CTRL_OUT_SRC_BITS)-1;
CTRL_OUT_LEVEL_MASK         = (1<<CTRL_OUT_LEVEL_BITS)-1;
CTRL_OUT_DST_MASK           = (1<<CTRL_OUT_DST_BITS)-1;

# output destinations offsets
CTRL_OUT_DST_OUT0           = 0*CTRL_OUT_DST_BITS   # ext_out[0]
CTRL_OUT_DST_OUT1           = 1*CTRL_OUT_DST_BITS   # ext_out[1]
CTRL_OUT_DST_OUT2           = 2*CTRL_OUT_DST_BITS   # ext_out[2]
CTRL_OUT_DST_BUS_EN0        = 3*CTRL_OUT_DST_BITS   # out_en[0]
CTRL_OUT_DST_BUS_EN1        = 4*CTRL_OUT_DST_BITS   # out_en[1]

# output sources
CTRL_OUT_SRC_NONE           = 0                 # fixed output at given level
CTRL_OUT_SRC_SYNC_OUT       = 1                 # sync_out
CTRL_OUT_SRC_SYNC_EN        = 2                 # sync_en
CTRL_OUT_SRC_SYNC_MON       = 3                 # sync_mon
CTRL_OUT_SRC_CLK_LOST       = 4                 # clock loss
CTRL_OUT_SRC_ERROR          = 5                 # error
CTRL_OUT_SRC_RUN            = 6                 # run (or wait)
CTRL_OUT_SRC_WAIT           = 7                 # wait
CTRL_OUT_SRC_READY          = 8                 # ready
CTRL_OUT_SRC_RESTART        = 9                 # restart
CTRL_OUT_SRC_TRG_START      = 10                # toggles with start trigger
CTRL_OUT_SRC_TRG_STOP       = 11                # toggles with stop trigger
CTRL_OUT_SRC_TRG_RESTART    = 12                # toggles with restart trigger

# output levels
CTRL_OUT_LEVEL_LOW          = 0                 # level active low = inverted
CTRL_OUT_LEVEL_HIGH         = 1                 # level active high = normal

# define output list for user to select in GUI. for sources/levels give True for default selection
# source=can be connected to several destinations. dest can be only connected to one source. source can be None, dest not.
OUT_SRC_NONE   = 'fixed'
out_dests   = {'output 0'        : CTRL_OUT_DST_OUT0,
                  'output 1'        : CTRL_OUT_DST_OUT1,
                  'output 2'        : CTRL_OUT_DST_OUT2,
                  'bus enable 0'    : CTRL_OUT_DST_BUS_EN0,
                  'bus enable 1'    : CTRL_OUT_DST_BUS_EN1}
out_sources = {OUT_SRC_NONE      : CTRL_OUT_SRC_NONE,
                  'sync out'        : CTRL_OUT_SRC_SYNC_OUT,
                  'sync en'         : CTRL_OUT_SRC_SYNC_EN,
                  'sync mon'        : CTRL_OUT_SRC_SYNC_MON,
                  'clock lost'      : CTRL_OUT_SRC_CLK_LOST,
                  'error'           : CTRL_OUT_SRC_ERROR,
                  'run'             : CTRL_OUT_SRC_RUN,
                  'wait'            : CTRL_OUT_SRC_WAIT,
                  'ready'           : CTRL_OUT_SRC_READY,
                  'restart'         : CTRL_OUT_SRC_RESTART,
                  'trig. start'     : CTRL_OUT_SRC_TRG_START,
                  'trig. stop'      : CTRL_OUT_SRC_TRG_STOP,
                  'trig. restart'   : CTRL_OUT_SRC_TRG_RESTART,
                  }
out_levels  = {'low level'       : CTRL_OUT_LEVEL_LOW,
                  'high level'      : CTRL_OUT_LEVEL_HIGH}

# primary and secondary board default output settings
# notes:
# - these are default settings when nothing else is selected.
# - you can select 'output' in worker_args of board in connection_table. these take precedence over GUI selections.
# - you can select outputs also in GUI. for not defined 'output' selections in worker_args, last selections in GUI are restored.
default_out_prim = {'output 0':('sync out','low level')}
default_out_sec  = {}

def get_ctrl_out(output_selection):
    """
    returns output control register value from output_selection.
    output_selection = dictionary key = output and value = (source,level) with
    output = key from out_dests. missing outputs are considered as not used.
    source = key from out_sources.
    level = key from out_levels.
    returns 32bit output control register value used to configure board.
    """
    register = np.array([0],dtype=np.uint32)
    for dest, value in output_selection.items():
        source, level = value
        register[0] |= (out_sources[source]|(out_levels[level]<<CTRL_OUT_SRC_BITS))<<out_dests[dest]
    return register[0]

def get_out_selection(register, return_NONE=True):
    """
    returns dictionary with output selections.
    inverse function to get_ctrl_out.
    if return_NONE == True returns also OUT_SRC_NONE, otherwise not.
    """
    selection = {}
    for dest,dest_offset in out_dests.items():
        reg_dest = (register >> dest_offset) & CTRL_OUT_DST_MASK;
        for src, src_bits in out_sources.items():
            if return_NONE or (src_bits != CTRL_OUT_SRC_NONE):
                if (reg_dest & CTRL_OUT_SRC_MASK) == src_bits:
                    for level, level_bits in out_levels.items():
                        if ((reg_dest >> CTRL_OUT_SRC_BITS) & CTRL_OUT_LEVEL_MASK) == level_bits:
                            selection[dest] = (src,level)
                            break
                    break
    if get_ctrl_out(selection) != register:
        save_print('error: get_out_selection does not give consistent result with get_ctrl_out: %x != %x' %(get_ctrl_out(selection), register), selection)
        exit()
    return selection

def is_sync_out(ctrl_out):
    "returns True when sync_out is enabled in output control register ctrl_out"
    for dest, dest_offset in out_dests.items():
        if (((ctrl_out >> dest_offset) & CTRL_OUT_SRC_MASK) == CTRL_OUT_SRC_SYNC_OUT): return True
    return False

def get_out_info(ctrl_out):
    "returns short info string with output selections"
    info = []
    if is_sync_out(ctrl_out):   info += ['sync out']
    if len(info) > 0: return "(" + "|".join(info) + ")"
    else:             return ""

# configuration bits
CONFIG_CLOCK        = 100e6                 # 100MHz, not used at the moment
CONFIG_SCAN         = 1e6                   # 1MHz, requested sampling rate. overwritten by FPGA_board.bus_rate
CONFIG_CYCLES       = 1                     # cycles=repetitions, 0=infite, 1=default. needs CTRL_RESTART_EN bit to enable cycling mode.
CONFIG_TRANS        = 0                     # number of samples but can be given later.

# strobe delay bits
STRB_DELAY_AUTO     = 0                     # strobe delay. 0=use from config.server file
STRB_DELAY_DEFAULT  = 0x451e451e            # default strobe delay for 300:400:300 ns at 1MHz bus output frequency
STRB_DELAY          = STRB_DELAY_AUTO       # strobe delay. STRB_DELAY_AUTO = use from config.server file

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
SEC_PHASE_EXT       = int((290*PHASE_360)//360) & SYNC_PHASE_MASK # secondary board external clock phase in steps
SEC_PHASE_DET       = int(( 90*PHASE_360)//360) & SYNC_PHASE_MASK # secondary board detection clock phase in steps
SYNC_PHASE_SEC      = (SEC_PHASE_EXT << SYNC_PHASE_BITS) | SEC_PHASE_DET # secondary board {fi_ext,fi_det} clock phase

# stop options
STOP_NOW            = 0                     # abort any output
STOP_AT_END         = 1                     # stop at end of cycle (not implemented)

# FPGA_status definition
# unpacks and save_prints full status information received from server
# unpack info contains tuples of (repetition, struct type)
FPGA_STATUS_NUM_DEBUG       = 20
FPGA_status_unpack_info_8   = [(27,'I'),(6,'B'),(2,'s'),(3,'i'),(16,'I'),(FPGA_STATUS_NUM_DEBUG,'I')] # (2,'s')
FPGA_status_unpack_info_12  = [(27,'I'),(6,'B'),(2,'s'),(3,'i'),(17,'I'),(FPGA_STATUS_NUM_DEBUG,'I')]
FPGA_STATUS_OK              = 0
FPGA_STATUS_ENOINIT         = -1
FPGA_STATUS_EINCONST        = -10
FPGA_STATUS_ENUMBYTES       = -20
FPGA_STATUS_ERSP            = -30
FPGA_STATUS_EBPS            = -40
FPGA_STATUS_ENUMI32         = -50
FPGA_STATUS_EDUMMY          = -60
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
        else:
            self.error = FPGA_STATUS_ENUMBYTES
            return
        self.cmd, *data = struct.unpack(format, bytes)
        if self.cmd != cmd:
            self.error = FPGA_STATUS_ERSP
            return
        i = 0
        self.ctrl_FPGA          = data[i]; i += 1;
        self.ctrl_in            = data[i]; i += 1;
        self.ctrl_out           = data[i]; i += 1;
        self.set_samples        = data[i]; i += 1;
        self.set_cycles         = data[i]; i += 1;
        self.clk_div            = data[i]; i += 1;
        self.strb_delay         = data[i]; i += 1;
        self.sync_delay         = data[i]; i += 1;
        self.sync_phase         = data[i]; i += 1;
        self.status             = data[i]; i += 1;
        self.board_time         = data[i]; i += 1;
        self.board_samples      = data[i]; i += 1;
        self.board_time_ext     = data[i]; i += 1;
        self.board_samples_ext  = data[i]; i += 1;
        self.board_cycles       = data[i]; i += 1;
        self.sync_time          = data[i]; i += 1;
        self.version            = data[i]; i += 1;
        self.info               = data[i]; i += 1;
        self.FPGA_temp          = data[i]; i += 1;
        self.phase_ext          = data[i]; i += 1;
        self.phase_det          = data[i]; i += 1;
        self.period_in          = data[i]; i += 1;
        self.period_out         = data[i]; i += 1;
        self.period_bus         = data[i]; i += 1;
        self.ctrl_DMA           = data[i]; i += 1;
        self.status_TX          = data[i]; i += 1;
        self.status_RX          = data[i]; i += 1;
        self.dsc_TX_p           = data[i]; i += 1;
        self.dsc_TX_a           = data[i]; i += 1;
        self.dsc_TX_c           = data[i]; i += 1;
        self.dsc_RX_p           = data[i]; i += 1;
        self.dsc_RX_a           = data[i]; i += 1;
        self.dsc_RX_c           = data[i]; i += 1;
        dummy                   = data[i]; i += 1;      # dummy 2 bytes
        self.err_TX             = data[i]; i += 1;
        self.err_RX             = data[i]; i += 1;
        self.err_FPGA           = data[i]; i += 1;
        self.irq_TX             = data[i]; i += 1;
        self.irq_RX             = data[i]; i += 1;
        self.irq_FPGA           = data[i]; i += 1;
        self.irq_num            = data[i]; i += 1;
        self.TX_bt_tot          = data[i]; i += 1;
        self.RX_bt_tot          = data[i]; i += 1;
        self.bt_tot             = data[i]; i += 1;
        self.RD_bt_max          = data[i]; i += 1;
        self.RD_bt_act          = data[i]; i += 1;
        self.RD_bt_drop         = data[i]; i += 1;
        self.reps_set           = data[i]; i += 1;
        self.reps_act           = data[i]; i += 1;
        self.timeout            = data[i]; i += 1;
        if self.bytes_per_sample == 8:  self.last_sample = data[i:i+2]; i += 2; # [time, data]
        else:                           self.last_sample = data[i:i+3]; i += 3; # [time, data rack 0, data rack 1]
        self.debug_count        = data[i]; i += 1;
        self.debug              = data[i:i+FPGA_STATUS_NUM_DEBUG]; i += FPGA_STATUS_NUM_DEBUG;
        # check number of integers
        num_int = sum([i[0] if i[1] != 's' else 1 for i in info])
        if (i != num_int): # check consistent number of uint32_t
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
        # save_print status info in console
        save_print("DMA & FPGA status:")
        save_print("                    TX       RX     FPGA")
        save_print("ctrl       0x        - %8x %08x" % (self.ctrl_DMA, self.ctrl_FPGA))
        save_print("in/out     0x        - %08x %08x" % (self.ctrl_in, self.ctrl_out))
        save_print("in/out/bus ps %8u %8u %8u" % (self.period_in, self.period_out, self.period_bus))
        save_print("strb/clk   0x        - %8x %8x" % (self.strb_delay, self.clk_div))
        save_print("sync w/ph  0x        - %8x %8x" % (self.sync_delay, self.sync_phase))
        save_print("status     0x %8x %8x %8x (%s)" % (self.status_TX, self.status_RX, self.status, self.FPGA_status_str))
        save_print("board #/t            - %8u %8d us" % (self.board_samples, self.board_time))
        save_print("board #/t (ext)      - %8u %8d us" % ( self.board_samples_ext, self.board_time_ext))
        save_print("board #/cyc          - %8d %8d" % ( self.board_cycles, self.set_cycles))
        save_print("sync time  0x        -        - %8x" % (self.sync_time))
        save_print("temperature          -        - %4d.%03u deg.C" % (self.FPGA_temp / 1000, self.FPGA_temp % 1000))
        save_print("phase ext/det        - %8d %8d steps" % (self.phase_ext, self.phase_det))
        save_print("error         %8d %8d %8d" % (self.err_TX, self.err_RX, self.err_FPGA))
        save_print("IRQ's         %8u %8u %8u" % (self.irq_TX, self.irq_RX, self.irq_FPGA))
        save_print("IRQ's mrg     %8u" % (self.irq_num))
        save_print("trans bytes   %8u %8u %8u (%s)" % (self.TX_bt_tot, self.RX_bt_tot, self.bt_tot, self.TX_RX_bytes_ok))
        save_print("TX p/a/c      %8u %8u %8u" % (self.dsc_TX_p, self.dsc_TX_a, self.dsc_TX_c))
        save_print("RX p/a/c      %8u %8u %8u" % (self.dsc_RX_p, self.dsc_RX_a, self.dsc_RX_c))
        save_print("rd m/a/d      %8u %8u %8u" % (self.RD_bt_max, self.RD_bt_act, self.RD_bt_drop))
        save_print("reps/act      %8u %8u" % (self.reps_set, self.reps_act))
        save_print("timeout       %8u" % (self.timeout))
        if self.bytes_per_sample == 8:
            save_print("RX last    0x %08x %08x        - (%u us)" % (self.last_sample[0], self.last_sample[1], self.last_sample[0]))
        elif self.bytes_per_sample == 12:
            save_print("RX last    0x %08x %08x %08x (%u us)" % (self.last_sample[0], self.last_sample[1], self.last_sample[2], self.last_sample[0]))
        save_print("byte/samples  %8u        - %8u (mult. of 4)" % (self.bytes_per_sample, self.set_samples))
        save_print("version    0x        -        - %08x (%s)" % (self.version, self.get_version()))
        save_print("info       0x        -        - %08x (%s)" % (self.info, self.get_info()))
        # debug bytes we do not display

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
    """
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
    elif isinstance(d, int):
        data += "%%i=%i;"%(d)
    elif isinstance(d, float):
        data += "%%s=%f;"%(d)
    else:
        save_print(d)
        raise LabscriptError("to_string: invalid type %s!" % (value, type(value)))
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
            save_print("%s: adding ClockLine '%s'%s" % (self.name, device.name, ' (locked)' if device.locked else ''))
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
    #check device type
    if not isinstance(device, allowed_type):
        raise LabscriptError("device '%s', type %s must be of type %s" % (device.name, str(type(device)),str(device_typpe)))
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
    if len(device_list) >= max_channels:
        raise LabscriptError("You tried to add device '%s' to '%s' but which has already %i channels." % (device.name, device.parent_device.name, max_channels))
    #check valid channel number
    if (channel<0) or (channel >= max_channels):
        raise LabscriptError("Device '%s' channel number %i must be 0..%i." % (device.name, channel, max_channels-1))
    #ensure rack/address/channel is unique
    board = device.parent_device.parent_device.parent_device.parent_device
    if not isinstance(board, FPGA_board): # sanity check
        raise LabscriptError("'%s' is expected FPGA_board but is '%s'?" % (board.name, board.__class__))
    for pseudoclock in board.child_devices:
        for clockline in pseudoclock.child_devices:
            for IM in clockline.child_devices: # intermediate devices
                #save_print('check IM',IM.name)
                # skip QRF since is not a device in a rack!
                # note: do not use isinstance since this requires to import MOGLabs_QRF which can lead to a circular reference causing import to fail!
                if isinstance(IM, (DigitalChannels, AnalogChannels)):
                    for dev in IM.child_devices: # note: device is not yet in list of childs.
                        if (dev.rack == rack) and (dev.address == address) and (dev.channel == channel):
                            raise LabscriptError("device '%s' rack/address/channel %i/%i/%i is already used by '%s'" % (device.name, rack, address, channel, dev.name))
    #return [rack,address,channel] of new device
    return [rack,address,channel]

# internal special output device
# one created for each rack
# allows to insert time with special data bits for each rack
class SpecialOut(Output):
    address = None # has no address
    channel = None # channel = rack
    type    = TYPE_SP
    default_value = SP_AUTO_VALUE
    dtype   = np.uint32

    def __init__(self, name, parent_device, connection, rack, **kwargs):
        Output.__init__(self, name, parent_device, connection, **kwargs)
        self.rack = rack

    # define conversion function from raw data to data word.
    # raw_data = numpy array generated by labscript.
    # will be called by generate_code for each DigitalOut device.
    def to_word(self, raw_data):
        "return data word for this channel"
        return np.array(np.where(raw_data == self.default_value, 0, raw_data),dtype=np.uint32)

# internal special Intermediate Device
# needed for SpecialOut devices created one per rack
class SpecialIM(IntermediateDevice):
    description = 'internal device for special data'
    allowed_children = [SpecialOut]
    shared_address = False

    def __init__(self, name, parent_device, bus_rate, clockline=None, **kwargs):
        #parent device must be FPGA_board. you should not connect it directly to clockline.
        # optional string 'clockline' allows to create an individual clockline for device for more efficient timing calculation.
        if not isinstance(parent_device, FPGA_board):
            raise LabscriptError("Device '%s' parent class is '%s' but must be '%s'!" % (self.name, parent_device.__class__, FPGA_board))
        # get clockline from FPGA_board and set as parent
        self.parent_device = parent_device.get_clockline(self, bus_rate, clockline)
        # init device with clockline as parent
        IntermediateDevice.__init__(self, name, self.parent_device, **kwargs)

    def add_device(self, device):
        if isinstance(device, SpecialOut):
            IntermediateDevice.add_device(self, device)
        else:
            raise LabscriptError("'%s' must be SpecialOut but is '%s'!" % (device.name, device.__class__))

# IntermediateDevice with digital output channels
# channel numbers must be unique. all channels have the parent address (called 'connect' for consistency)
class DigitalChannels(IntermediateDevice):
    description = 'digital output device with several channels'
    allowed_children = [DigitalOut]
    shared_address = True
    #clock_limit = CLOCK_LIMIT
    #num_racks = 0 # set to maximum allowed number of racks given by FPGA_board

    def __init__(self, name, parent_device, connection, rack, max_channels, bus_rate=MAX_BUS_RATE, clockline=None, **kwargs):
        #parent device must be FPGA_board. you should not connect it directly to clockline.
        # optional string 'clockline' allows to create an individual clockline for device for more efficient timing calculation.
        if not isinstance(parent_device, FPGA_board):
            raise LabscriptError("Device '%s' parent class is '%s' but must be '%s'!" % (self.name, parent_device.__class__, FPGA_board))
        # get clockline from FPGA_board and set as parent
        self.parent_device = parent_device.get_clockline(self, bus_rate, clockline)
        # init device with clockline as parent
        IntermediateDevice.__init__(self, name, self.parent_device, **kwargs)

        # set clock limit and resolution
        self.clock_limit      = get_clock_limit(bus_rate)
        self.clock_resolution = get_clock_resolution(bus_rate)

        self.num_racks = parent_device.num_racks
        self.max_channels = max_channels
        self.rack = rack

        # digital channels share the same address. therefore, channels on the same intermediate device can change simultaneously.
        self.address = parse_num(connection)
        if (self.rack < 0) or (self.rack >= self.num_racks):
            raise LabscriptError("For device '%s' rack number %i given but parent device '%s' has only %i racks!" % (self.name, self.rack, parent_device.name, self.num_racks))
        if (self.address < 0) or (self.address > MAX_ADDRESS):
            raise LabscriptError("For device '%s' address %x given but only 0..%x allowed!" % (self.name, self.address, MAX_ADDRESS))
        #save address bits
        # manually add device to clockline
        #self.parent_device.add_device(self)

        # define conversion function from raw data to data word.
        # raw_data = numpy array generated by labscript.
        # will be called by generate_code for each DigitalOut device.
        def _to_word(self, raw_data):
            "return data word for this channel"
            return np.array(np.where(raw_data == self.default_value, BIT_NOP_SH, (raw_data*self.ch_bits) | self.addr_bits),dtype=np.uint32)
        DigitalOut.to_word = _to_word

    def add_device(self, device):
        #save_print('FPGA_Intermediatedevice: add device', device.name)
        #check if valid device, channel and if channel is already used
        #we use shared address from parent (DigitalChannels)
        device.rack, device.address, device.channel = check_device(device, DigitalOut, self.max_channels, self.child_devices, self.shared_address)
        device.type = TYPE_DO
        device.default_value = DO_AUTO_VALUE
        #data save data and address bits for this channel
        device.ch_bits   = np.array((1<<device.channel) | (self.address << ADDR_SHIFT), dtype=np.uint32)
        device.addr_bits = np.array((self.address << ADDR_SHIFT), dtype=np.uint32)
        # set default value when unused
        IntermediateDevice.add_device(self, device)
        #save device rack/address/channel into hdf5 file
        device.set_property('address', '%i/%i/%i'%(device.rack,device.address,device.channel), 'connection_table_properties')

    def get_data(self, times, conflicts, data=None, changes=None, rack=None, channels=None):
        """
        combine data bits of digital channels.
        times     = numpy list of times where any channel changes for given board.
        conflicts = if channels is None: 2D list for each rack and time, otherwise: 1D list for given rack and time.
                       list contains: input boolean of conflicts. output True where two or more channels changes simultaneously.
        data      = 2D list for each rack and time: input data for all times (0 initially). output updated data with channel bits.
        changes   = 2D list for each rack and time: input boolean for all times (False initially). output True where any channel changes.
        rack      = if not None: rack number for which conflicting channels should be added to channels
        channels  = if not None: dict with key = conflict time, value = list of conflicting channels for each conflict of given rack
            conflict_time = time where conflict occurs. this must be an entry of times[conflicts]
            conflict_channels = list of [channel name, initial state, final state] for all channels in rack, where time conflict is detected.
            initial and final states are float or integer,
            initial state can be None if the conflict occurs at the first instruction of the channel.
            a conflicting channel is changing state at the same time as another channel of another device.
        note: digital channels with same address (i.e. with same parent DigitalChannels) can change simultaneously.
        """
        d = np.zeros(len(times),dtype=np.uint32)
        chg = np.zeros(len(times),dtype=np.bool_)
        if channels is not None: zeros = np.zeros(len(times),dtype=np.uint32)
        #combine all channels into data.
        #note: labscript gives a warning when a channel state is changed at the same time twice or more. the last state is retained.
        #dev.raw_output gives state 0 or 1 for each entry in times
        for dev in self.child_devices:
            if (channels is None) or (dev.parent_device.rack == rack):
                #save_print('combine DO',dev.name)
                # first user-defined instruction (auto-inserted time=dev.t0, value=DO_AUTO_VALUE is ignored)
                user_times = [key for key,value in dev.instructions.items() if isinstance(value,dict) or (key != dev.t0) or (value != DO_AUTO_VALUE)]
                if channels is not None:
                    # get changing channels for all conflicts (called only when conflicts detected)
                    # here we detect individual changing channels
                    d = np.where(dev.raw_output != DO_AUTO_VALUE, dev.raw_output, zeros)
                    chg = np.concatenate([[False], (np.array(d[1:] - d[0:-1]) != 0)])
                    if len(user_times) > 0:
                        chg |= (np.abs(times - round(min(user_times), TIME_ROUND_DECIMALS)) < TIME_PRECISION)
                    index = np.arange(len(times))[conflicts & chg]
                    for i in index:
                        conflict_time = times[i]
                        conflict_channel = [dev.name, None if (i == 0) or (d[i - 1] == DO_AUTO_VALUE) else d[i - 1], d[i]]
                        if conflict_time in channels:
                            channels[conflict_time].append(conflict_channel)
                        else:
                            channels[conflict_time] = [conflict_channel]
                else:
                    # here we combine data and detect changes for all channels together
                    #d[dev.raw_output == 1] |= dev.ch_bits
                    d |= np.where(dev.raw_output == 1, dev.ch_bits, dev.addr_bits)
                    if len(user_times) > 0:
                        #save_print("'%s' first user time %.6f" % (dev.name, round(min(user_times), TIME_ROUND_DECIMALS)))
                        chg |= (np.abs(times - round(min(user_times), TIME_ROUND_DECIMALS)) < TIME_PRECISION)
                    #else: save_print("'%s' no user instruction" % (dev.name))
        if channels is None:
            # detect changes in state = True. first user-defined instructions are ALWAYS executed.
            chg |= np.concatenate([[False], (np.array(d[1:] - d[0:-1]) != 0)])
            if any(chg):
                # detect conflicts with other devices
                conflicts[:,dev.parent_device.rack][chg] |= changes[:, dev.parent_device.rack][chg]
                # combine data
                data[:,dev.parent_device.rack+1][chg] |= (d[chg] & DATA_ADDR_MASK)
                # update changes
                changes[:,dev.parent_device.rack][chg] = True

# IntermediateDevice with analog output channels
# channels have individual addresses (saved in 'connect').
class AnalogChannels(IntermediateDevice):
    description = 'analog output device with several channels'
    allowed_children = [AnalogOut]
    shared_address = False
    #clock_limit = CLOCK_LIMIT
    #num_racks = 0 # set to maximum allowed number of racks given by FPGA_board

    def __init__(self, name, parent_device, rack, max_channels, bus_rate=MAX_BUS_RATE, clockline=None, **kwargs):
        # parent device must be FPGA_board. you should not connect it directly to clockline.
        # optional string 'clockline' allows to create an individual clockline for device for more efficient timing calculation.
        if not isinstance(parent_device, FPGA_board):
            raise LabscriptError("Device '%s' parent class is '%s' but must be '%s'!" % (self.name, parent_device.__class__, FPGA_board))
        # get clockline from FPGA_board and set as parent_device
        self.parent_device = parent_device.get_clockline(self, bus_rate, clockline)
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

        # define conversion function from raw data to data word. will be called by generate_code for each AnalogOut device.
        def _to_word(self, raw_data):
            "return data word for this channel"
            return np.array(np.where(raw_data == self.default_value, BIT_NOP_SH, V_to_word(raw_data) | self.addr_bits),dtype=np.uint32)
        AnalogOut.to_word = _to_word

    def add_device(self, device):
        #save_print("AnalogChannels: add device '%s' type '%s'" % (device.name, str(type(device))))
        #check if valid device and channel and if channel is already used
        #create container class and check if valid device, channel and if channel is already used
        #each channel has its own address.
        device.rack, device.address, device.channel = check_device(device, AnalogOut, self.max_channels, self.child_devices, False)
        device.type = TYPE_AO
        device.default_value = AO_AUTO_VALUE
        #device.id = get_ID(type=device.type, rack=device.rack, address=device.address, channel=device.channel)
        device.addr_bits = np.array(device.address<<ADDR_SHIFT,dtype=np.uint32)
        IntermediateDevice.add_device(self, device)
        device.set_property('address', '%i/%i/%i'%(device.rack,device.address,device.channel), 'connection_table_properties')
        # note: this is called with device = labscript.labscript.AnalogOut via parent class constructors of Output and Device classes.
        #       unfortunately, it is called BEFORE unit_conversion_class and unit_conversion_parameters are assigned!
        #       therefore, we cannot check here (i.e. during compilation of connection table)
        #       if unit_conversion is valid and calculate V_min and V_max for later usage!
        #       instead we have to do this inside get_channels which is called every time when new data is generated (runmanager).

    def get_data(self, times, conflicts, data=None, changes=None, rack=None, channels=None):
        """
        combine data bits of analog channels.
        times     = numpy list of times where any channel changes for given board.
        conflicts = if channels is None: 2D list for each rack and time, otherwise: 1D list for given rack and time.
                       list contains: input boolean of conflicts. output True where two or more channels changes simultaneously.
        data      = 2D list for each rack and time: input data for all times (0 initially). output updated data with channel bits.
        changes   = 2D list for each rack and time: input boolean for all times (False initially). output True where any channel changes.
        rack      = if not None: rack number for which conflicting channels should be added to channels
        channels  = if not None: dict with key = conflict time, value = list of conflicting channels for each conflict of given rack
            conflict_time = time where conflict occurs. this must be an entry of times[conflicts]
            conflict_channels = list of [channel name, initial state, final state] for all channels in rack, where time conflict is detected.
            initial and final states are float or integer,
            initial state can be None if the conflict occurs at the first instruction of the channel.
            a conflicting channel is changing state at the same time as another channel of another device.
        """
        for dev in self.child_devices:
            if (channels is not None) and (dev.parent_device.rack != rack): continue # skip wrong rack
            #note: dev.raw_output has same length as times and is already in volts and unit_conversion has been applied and limits checked.
            d = np.array(V_to_word(dev.raw_output), np.uint16)
            chg = np.concatenate([[False], ((d[1:] - d[0:-1]) != 0)])
            # detect changes in state = True. in next lines first user-defined instruction is detected and ALWAYS executed.
            # note: labscript gives a warning when a channel state is changed at the same time twice or more. the last state is retained.
            # first user-defined instruction (auto-inserted time=dev.t0, value=AO_AUTO_VALUE is ignored)
            user_times = [key for key,value in dev.instructions.items() if isinstance(value,dict) or (key != dev.t0) or (value != AO_AUTO_VALUE)]
            if len(user_times) > 0:
                #print('%s user times:' % dev.name, user_times)
                #if channels is None: save_print("'%s' first user time %.6f" % (dev.name, round(min(user_times), TIME_ROUND_DECIMALS)))
                chg |= (np.abs(times - round(min(user_times), TIME_ROUND_DECIMALS)) < TIME_PRECISION)

            #else: save_print("'%s' no user instruction" % (self.name))
            #save_print('combine AO',dev.name)
            if channels is not None:
                # get changing channels for all conflicts (called only when conflicts detected)
                index = np.arange(len(times))[conflicts & chg]
                for i in index:
                    conflict_time = times[i]
                    #TODO: unit conversion?
                    conflict_channel = [dev.name, None if (i == 0) or (dev.raw_output[i - 1] == AO_AUTO_VALUE) else dev.raw_output[i - 1], dev.raw_output[i]]
                    if conflict_time in channels:
                        channels[conflict_time].append(conflict_channel)
                    else:
                        channels[conflict_time] = [conflict_channel]
            else:
                # detect conflicts with other channels and devices
                conflicts[:,dev.parent_device.rack] |= (changes[:,dev.parent_device.rack] & chg)
                # combine data
                data[:,dev.parent_device.rack+1] = data[:,dev.parent_device.rack+1] | ((d|dev.addr_bits) & (chg*DATA_ADDR_MASK))
                # update changes
                changes[:,dev.parent_device.rack] |= chg

total_time = None

# PseudoclockDevice
class FPGA_board(PseudoclockDevice):
    description = 'FPGA board device class v1.0'
    allowed_children = [FPGA_PseudoClock]

    # the delay is corrected by the board on the ns level if needed, so we can set this to 0.
    trigger_delay = 0
    #wait_delay = 2e-6 # unclear what this is?

    PCLOCK_FORMAT           = '%s_pc%i_%s'      # device name + index + bus_rate
    CLOCKLINE_FORMAT        = '%s_cl%i'         # pseudo clock name + index
    CLOCKLINE_FORMAT_NAME   = '%s_cl%i_%s'      # pseudo clock name + index
    CON_FORMAT              = '%s_con'          # pseudo clock or clockline name
    CLOCK_FORMAT_SEP        = "_"               # format separator for when clockline is given as name

    # call with name, IP address string and port string, output bus rate in MHz and num_racks (1=8 bytes/sample, 2=12 bytes/sample)
    # for all secondary boards give trigger_device=primary board.
    @set_passed_properties()
    def __init__(self, name, ip_address, ip_port, bus_rate=MAX_BUS_RATE, num_racks=1, trigger_device=None, worker_args=None):
        if trigger_device is not None: trigger_connection = 'trig_con' # we have to give a connection. name seems irrelevant.
        else:                          trigger_connection = None
        PseudoclockDevice.__init__(self, name, trigger_device=trigger_device, trigger_connection=trigger_connection)
        self.ip_address = ip_address.replace(":",".") # must be a string of the form '192.168.1.1' or '192:168:1:1'
        self.ip_port = str(ip_port) # the ip_port could be given as integer, but we request string
        self.BLACS_connection = '%s:%s'%(self.ip_address,self.ip_port)
        self.bus_rate = bus_rate # maximum bus output rate of board
        self.time_step = TIME_STEP/self.bus_rate    # smallest allowed rate
        self.start_time = self.time_step*START_TIME # initial time cannot be smaller than this. TODO: check in data!
        self.num_racks = num_racks
        self.digits = int(np.ceil(np.log10(self.bus_rate))) # for 9e5 get 6, for 1e6 get 6, for 1.1e6 get 7
        self.worker_args = worker_args
        self.worker_args_ex = {} # modifying worker_args makes troubles, so we save extra worker_args_ex separately in hdf5 file
        # check allowed bytes per sample
        if (num_racks > 2): raise LabscriptError("%s: you have given %i racks but maximum 2 are allowed! use several boards instead." %(self.name, bytes_per_sample))
        elif (num_racks < 1): raise LabscriptError("%s: you have given %i racks but minimum 1 is allowed!" %(self.name, bytes_per_sample))
        if bus_rate > MAX_FPGA_RATE: raise LabscriptError("%s: maximum bus rate is %.3f MHz. You specified %.3f MHz!" %(self.name,self.MAX_FPGA_RATE/1e6,self.bus_rate/1e6))
        self.clock_limit = CLOCK_LIMIT
        self.clock_resolution = CLOCK_RESOLUTION

        #save bus rate in Hz and number of racks into hdf5 file
        self.set_property('bus_rate', self.bus_rate, 'connection_table_properties')
        self.set_property('num_racks', self.num_racks, 'connection_table_properties')

        # save worker arguments into hdf5 file
        self.set_property('worker_args', self.worker_args, location='connection_table_properties')

        # create num_racks SpecialOut devices to store special data bits per rack
        # we need one SpecialIM device and one special (and locked=exclusive) clockline for this.
        # note: the special data bits are not sent to devices, so we can set maximum bus rate but this might have unintended side-effects?
        self.special_IM   = SpecialIM(name='%s_special_IM'%self.name, parent_device=self, bus_rate=self.bus_rate, clockline=("special",True))
        self.special_data = [SpecialOut(name='%s_special_data_%i'%(self.name,i),
                                        parent_device=self.special_IM,
                                        connection='%s_special_data_%i_con'%(self.name,i),
                                        rack=i) for i in range(self.num_racks)]

        # list of secondary boards.
        # note: QRF board is not in list of childs, so we have to keep a separate list
        self.secondary_boards = []

        # check if primary board and manually add secondary device to primary board child list.
        # all other than first board need a trigger_device to be given (not sure what to do with it).
        self.trigger_device = trigger_device
        if trigger_device is None:
            self.is_primary = True
            self.primary_board = None
        else:
            self.is_primary = False
            self.primary_board = trigger_device
            self.primary_board.add_device(self)

    def add_device(self, device):
        if isinstance(device, Pseudoclock):
            save_print("%s: adding PseudoClock '%s'" % (self.name, device.name))
            PseudoclockDevice.add_device(self, device)
        elif isinstance(device, labscript.labscript.Trigger):
            save_print("%s: adding Trigger '%s'" % (self.name, device.name))
            # for each secondary board the primary board gets a Trigger device but I dont know what to do with it?
            pass
        elif isinstance(device, PseudoclockDevice):
            save_print("%s: adding secondary board '%s'" % (self.name, device.name))
            # I call this manually from __init___ for each secondary board added with self = primary board.
            self.secondary_boards.append(device)
        elif isinstance(device, labscript.labscript.DDS):
            # DDS
            save_print("%s: adding %s '%s' (not implemented)" % (self.name, device.__class__, device.name))
        else:
            raise LabscriptError("%s: adding %s '%s' is not allowed!" % (self.name, device.__class__, device.name))

    def get_clockline(self, device, bus_rate, clockline=None):
        """
        finds or creates appropriate pseudoclock and clockline with given maximum bus_rate in Hz.
        clockline can be given as clockline=None, clockline=name or clockline=(name,locked)
        if name is not None searches the first clockline which ends with this name, if not found or name is None creates new.
        if locked = True then the new clockline is reserved for the given device and cannot be shared with another device even if name given.
        returns clockline with given maximum bus_rate.
        call from __init__ of all intermediate devices to get parent_device.
        """
        # note about pseudoclocks and clocklines (as far as I understand):
        # the hirarchial connection is from parent - >child:
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

        if clockline is None:
            locked = False
        elif isinstance (clockline, (tuple,list)):
            clockline, locked = clockline
        else:
            locked = False

        # check bus rate is not larger MAX_BUS_RATE [disabled. TODO: device will be limited but should still work?]
        #if bus_rate > self.bus_rate:
        #    raise LabscriptError("device '%s' bus rate %.3f MHz > maximum possible %.3f MHz!" % (device.name, bus_rate/1e6, self.bus_rate/1e6))
        # find a peseudoclocck with the same bus rate
        # if clockline is given needs to have also same name, otherwise create a new clockline with this name.
        pseudoclock = None
        _clockline = None
        line_index = None
        for pc in self.child_devices:
            if not isinstance(pc, Pseudoclock): # sanity check
                raise LabscriptError("get_clockline: '%s' is not Pseudoclock but '%s'!" % (pc.name, type(pc)))
            if pc.bus_rate == bus_rate:
                pseudoclock = pc # we always take first pseudoclock with same rate
                if not locked:
                    # new clockline is not locked: search for matching clockline if name given
                    if clockline is None: # take first clockline which is not locked
                        for index, cl in enumerate(pc.child_devices):
                            if not cl.locked:
                                _clockline = cl
                                line_index = index
                                break
                    else:
                        # take first existing not locked clockline ending with given name
                        num = len(clockline.split(self.CLOCK_FORMAT_SEP))
                        for index,cl in enumerate(pc.child_devices):
                            if not cl.locked and (self.CLOCK_FORMAT_SEP.join(cl.name.split(self.CLOCK_FORMAT_SEP)[-num:]) == clockline):
                                _clockline  = cl
                                line_index = index
                                break
                    if (_clockline is not None) and (not isinstance(_clockline, ClockLine)):
                        # sanity check
                        raise LabscriptError("get_clockline: '%s' is not ClockLine but '%s'!" % (_clockline.name, type(_clockline)))
                if line_index is None:
                    line_index = len(pseudoclock.child_devices)
                break
        if pseudoclock is None:
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
        if _clockline is None:
            # create new clockline with given name or default name from line_index = number of clocklines - 1
            if clockline is None:
                clockline_name = self.CLOCKLINE_FORMAT % (pseudoclock.name, line_index)
            else:
                clockline_name = self.CLOCKLINE_FORMAT_NAME % (pseudoclock.name, line_index, clockline)
            connection = self.CON_FORMAT % (clockline_name)
            _clockline = ClockLine(name=clockline_name, pseudoclock=pseudoclock, connection=connection, call_parents_add_device=False)
            _clockline.locked = locked
            pseudoclock.add_device(_clockline)
        # return new clockline
        return _clockline

    def show_data(self, data, info=None):
        if ALWAYS_SHOW or (len(data) <= MAX_SHOW):
            if info is not None: save_print(info)
            if len(data) > MAX_SHOW:
                index = [[0, int(MAX_SHOW / 2)], [len(data) - int(MAX_SHOW / 2), len(data)]]
            else:
                index = [[0, len(data)]]
            if self.num_racks == 2:
                save_print('   sample      time      rack0      rack1')
            else:
                save_print('   sample      time       data')
            for i_rng in index:
                if self.num_racks == 2:
                    for i in range(i_rng[0], i_rng[1]):
                        save_print('%9i %9u 0x%08x 0x%08x' % (i, data[i, 0], data[i, 1], data[i, 2]))
                else:
                    for i in range(i_rng[0], i_rng[1]):
                        save_print('%9i %9u 0x%08x' % (i, data[i, 0], data[i, 1]))
            save_print()

    def reduce_instructions(self, max_instructions=1000):
        for pseudoclock in self.child_devices:
            for clockline in pseudoclock.child_devices:
                for IM in clockline.child_devices:
                    for dev in IM.child_devices:
                        if len(dev.instructions) > max_instructions:
                            num = len(dev.instructions)
                            #print(dev.instructions)
                            # extract all single integer or float values from instrutions
                            all_times = np.array(list(dev.instructions.keys()))
                            times,values = np.transpose([[key,dev.instructions[key]] for key in dev.instructions.keys() if isinstance(dev.instructions[key], (int,float))])
                            mask = np.isin(all_times, times)
                            print('other times', all_times[~mask])
                            print('times',times)
                            # instructions might not be sorted in time.
                            # we sort in reverse order for digitize to work as we want.
                            index = np.argsort(times)[::-1]
                            times  = times[index]
                            values = values[index]
                            first = times[-1]
                            next  = times[-2]
                            last = times[0]

                            # delete old instructions
                            for key in times:
                                del dev.instructions[key]

                            # time given to get_value is relative to 'initial time' added with a offset
                            # this offset is calculated from 'midpoint' between the first two datapoints
                            # assuming constant sampling time but this is not the case here.
                            # so we shift time here by the possible wrong midpoint and subtract time_step/2
                            # to be sure that t is slightly larger than times to avoid numerical errors.
                            times += -first - 0.5*(next - first) - self.time_step/2
                            print('times', times)
                            print(len(times))

                            #print('times=',times)

                            # define a new instruction function which returns value for given time t.
                            # t can be a numpy array or a skalar.
                            # this is adapted from labscript.functions.pulse_sequence
                            # note that labscript might insert an arbitrary number of in-between points
                            # we return the last value set at or before the given time t.
                            def get_value(t):
                                print('t=', t)
                                try:
                                    len(t) # this will cause TypeError when t is not a list
                                    print(len(t))
                                    print(np.digitize(t, times, right=False))
                                    print(t-times[np.digitize(t, times, right=False)])
                                    return values[np.digitize(t, times, right=False)]
                                except TypeError:
                                    print(np.digitize([t], times, right=False))
                                    print(values[np.digitize([t], times, right=False)][0])
                                    return values[np.digitize([t], times, right=False)][0]

                            # define new instruction calling get_value
                            dev.instructions[first] = {'function': get_value,
                                                          'description': 'get value for given time',
                                                          'initial time': first,
                                                          'end time': last,
                                                          'clock rate': self.bus_rate/10,
                                                          'units': None,
                                                          'times': times,
                                                          'values': values}

                            print("'%s' %i instructions reduced to %i" % (dev.name, num, len(dev.instructions)))
                            print(dev.instructions.keys())

    def check_times(self, pseudoclock, device):
        # compare with code in labscript.py, see pseudoclock.generate_clock()
        # device is intermediate device (DigitalChannels) or AnalogOut

        # get parent clockline and all outputs
        outputs_by_clockline = {}
        if isinstance(device, AnalogOut):
            clockline = device.parent_device.parent_device
            outputs = [device]
        elif isinstance(device, DigitalChannels):
            clockline = device.parent_device
            outputs = device.child_devices
        else:
            raise LabscriptError("device %s is neither AnalogOut nor DigitalChannels but %s" % (device.name, device.__class__))
        outputs_by_clockline[clockline] = outputs

        # get all change times
        all_change_times = []
        change_times = {}
        for dev in outputs:
            all_change_times.extend(list(dev.instructions.keys()))
        change_times[clockline] = all_change_times

        if np.max(all_change_times) != pseudoclock.parent_device.stop_time:
            print('stop time =', pseudoclock.parent_device.stop_time)
            print('last time =', np.max(all_change_times))
            pseudoclock.parent_device.stop_time = np.max(all_change_times)
            print('stop time =', pseudoclock.parent_device.stop_time)

        times, clock = pseudoclock.expand_change_times(all_change_times, change_times, outputs_by_clockline)
        print(times)

    def expand_times_and_values(self, device, shared_times, expand_values):
        """
        expand times and values from device instructions.
        if shared_times is not None uses these times, otherwise uses times from instructions. requires expand_values = True.
        if expand_values = True returns values, otherwise values = [].
        returns [times, values]
        """
        times = []
        values = []
        for key, value in device.instructions.items():
            if isinstance(value, (int, float)):  # single value. units conversion is already applied
                times.extend([key])
                if expand_values:
                    values.extend([value])
            elif isinstance(value, dict):  # function
                # TODO: check what labscript exactly does
                t_start = round(value['initial time'], 10)
                t_end = round(value['end time'], 10)
                samples = int((t_end - t_start) * value['clock rate'])
                if (t_start + samples / value['clock rate']) < t_end:
                    # we move slightly t_start towards larger times to have correct sampling rate.
                    # this ignores that times should be integer multiple of dt.
                    t_start = t_end - samples / value['clock rate']
                t = key + np.linspace(t_start, t_end, samples)
                times.extend(t)
                if expand_values:
                    v = value['function'](t)
                    if value['units'] is not None:
                        v = device.apply_calibration(v, value['units'])
                    values.extend(v)
            elif isinstance(value, (list, np.ndarray)):  # allow direct input of data[0] = time, data[1] = value
                times.extend(value[0])
                if expand_values:
                    values.extend(value[1])
            else:  # unknown type?
                print(value)
                raise LabscriptError("unknown instruction! at time %f" % (key))

        # check smallest time and insert t0 if is not there.
        # this ensures that digitize returns always valid indices even if the first instruction of device is at later time.
        t_min = np.min(times)
        if t_min < self.t0: raise LabscriptError("time %f < %f!" % (t_min, self.t0))
        elif t_min > self.t0:
            times.extend([self.t0])
            values.extend([device.default_value])

        # ensure there are unique times. TODO: maybe more efficient after sorting by looking on difference not zero?
        if len(times) != len(np.unique(times)):
            print(times)
            raise LabscriptError("times are not unique!")

        if expand_values and (len(times) != len(values)):
            print(times)
            print(values)
            raise LabscriptError("times (%i) and values (%i) are inconsistent!" % (len(times), len(values)))

        if shared_times is None:
            if expand_values:
                # sort times
                index = np.argsort(times)
                times = np.array(times)[index]
                values = np.array(values)[index]
            else:
                # we sort times later
                times = np.array(times)
        else:
            # shared_times given
            if len(times) == 1:
                # single time bin: return single value for all shared_times
                values = np.ones(shape=(len(shared_times),), dtype=device.dtype) * values[0]
                times = shared_times
            else:
                # map times to shared_times 'ts' using times[i] <= ts < times[i+1]
                index = np.argsort(times)[::-1]
                times = np.array(times)[index]
                values = np.array(values)[index]
                index = np.digitize(shared_times + self.time_step/2, times, right=False)
                if np.count_nonzero((shared_times < times[-1]) | (shared_times > times[0])) > 0:
                    # shared_time must be >= smallest time otherwise digitize gives index = len(times)
                    # if shared_time >= largest time digitize gives index = 0
                    t = shared_times[(shared_times < times[-1]) | (shared_times > (times[0] + self.time_step/2))]
                    print('times outside range [%f,%f]:'%(times[-1],times[0]), t)
                    raise LabscriptError("shared time must be in range %f <= t <= %f!" % (times[-1], times[0]))
                if True: # check mapping
                    #print('times  =', times)
                    ## print('values =',values)
                    #print('t      =', shared_times)
                    #print('index  =', index)
                    #print('isin   =', np.isin(shared_times, times))
                    for i,t in enumerate(shared_times):
                        if ((index[i]+1 < len(times)) and (times[index[i]] <= t < times[index[i]+1])):
                            raise LabscriptError("error time: %f <= %f < %f is not fulfilled!" % (times[index[i]], t, times[index[i]+1]))
                        elif (index[i] == len(times)) and not (times[0] <= t):
                            raise LabscriptError("error time: %f <= %f is not fulfilled!" % (times[index[i]], t))
                values = values[index]
                times  = shared_times
        return [times,values]

    def get_raw_data(self, do_check_times=True):
        "replaces PseudoclockDevice.generate_code"
        # TODO: unfinished. would need to manually expand ramps, which would be not difficult.
        #       this function could already collect data, changes, conflicts.
        #       maybe still first collect all times from instructions including function times so we can allocate data.
        #       different devices on the same clocklines do not need to be combined,
        #       i.e. no intermediate values need to be calculated for any device.
        #       clock limits, i.e. smallest deltas can be checked per device.
        # - this function should give the same result as expand_change_times + expand_timeseries called for each device with independend address.
        #   the same effect would be to give each analog output and each digital intermediate device a single pseudoclock.
        self.all_times = []
        for pseudoclock in self.child_devices:
            for clockline in pseudoclock.child_devices:
                # note: clockline does not get times. these are stored per device
                for IM in clockline.child_devices:
                    if IM.shared_address:
                        shared_times = [self.expand_times_and_values(dev, shared_times=None, expand_values=False)[0] for dev in IM.child_devices if len(dev.instructions) > 0]
                        IM.times = shared_times = np.unique([t for l in shared_times for t in l])
                    else:
                        shared_times = None
                    for dev in IM.child_devices:
                        if len(dev.instructions) > 0:
                            dev.times, dev.raw_output = self.expand_times_and_values(dev, shared_times=shared_times, expand_values=True)
                            self.all_times.extend(dev.times)
                            # TODO: check toggle rate of device. call do_checks?

                            if do_check_times and not IM.shared_address and isinstance(dev, AnalogOut):
                                self.check_times(pseudoclock, dev)
                        else:
                            if IM.shared_address:
                                dev.times = shared_times
                                dev.raw_output = np.ones(shape=(len(shared_times),),dtype=dev.dtype)*dev.default_value
                            else:
                                dev.times = dev.raw_output = np.array([])
                    if do_check_times and IM.shared_address:
                        self.check_times(pseudoclock, IM)

        self.all_times = np.unique(self.all_times)
        #print(self.all_times)
        # from here proceed generating data matrix, collect changes and check conflicts as below in generate_code

    def generate_code(self, hdf5_file):
        global total_time
        
        save_print("\n'%s' generating code ...\n" % (self.name))
        if self.name == 'primary':
            total_time = get_ticks()

        # Generate clock and save raw instructions to the hdf5 file:
        # - generate_code_with_labscript = True:
        #   uses original code from labscript.py
        #   this is a bottleneck and scales bad with number of instructions!
        #   merges all times for each clockline and generated raw data for all times
        #   performs many advanced checks
        # - generate_code_with_labscript = False: [experimental stage]
        #   much simpler code just expands functions and performs basic tests
        #   merges only times for intermediate devices with shared address (DigitalOut)
        #   much faster but is not fully tested!
        #   returns different number of samples than generate_code_with_labscript = True.
        generate_code_with_labscript = True # True = old slow code, False = new optimized code for FPGA_board
        if generate_code_with_labscript:
            # first attempt to merge multiple instructions into fewer ones.
            # partially working but not finished. labscript assums ramps/functions with constant time steps which is not what I would need.
            # self.reduce_instructions(max_instructions=100)
            PseudoclockDevice.generate_code(self, hdf5_file)
        else:
            self.get_raw_data()
        print('total_time %.3fms' % ((get_ticks() - total_time) * 1e3))

        #return

        if True:
            t_start = get_ticks()
            # experimental:
            # merge all times of all pseudoclocks and clocklines
            # times and channel.raw_data will have different lengths!
            if generate_code_with_labscript:
                times = np.unique(np.concatenate([pseudoclock.times[clockline] for pseudoclock in self.child_devices for clockline in pseudoclock.child_devices]))
            else:
                times = self.all_times
            #save_print("'%s' total %i times:\n"%(self.name,len(times)),times)
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
            special = False
            special_STRB = False
            for pseudoclock in self.child_devices:
                #print('%s:'%pseudoclock.name)
                for clockline in pseudoclock.child_devices:

                    if generate_code_with_labscript:
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
                            raise LabscriptError('generate_code: no all times of pseudoclock found? (should not happen)')

                    #zeros = np.zeros(shape=(len(t),), dtype=np.uint32)
                    for IM in clockline.child_devices:
                        #print('%s:'%IM.name)

                        # skip special devices (will be treated after all other below)
                        if isinstance(IM, SpecialIM):
                            special = True
                            continue
                        # skip MOGLabs QRF since is not part of rack.
                        # note: do not use isinstance since this requires to import MOGLabs_QRF which can lead to a circular reference causing import to fail!
                        elif type(IM).__name__ == 'MOGLabs_QRF':
                            continue

                        if IM.shared_address:

                            if not generate_code_with_labscript:
                                t = IM.times
                                if len(t) == 0: continue
                                indices = np.argwhere(np.isin(times, t)).ravel()

                            # collect data for all channels of IM device
                            d   = np.zeros(shape=(len(t),), dtype=np.uint32)
                            chg = np.zeros(shape=(len(t),), dtype=np.bool_)

                            for dev in IM.child_devices:
                                #if np.count_nonzero(dev.raw_output == dev.default_value) != len(t):
                                #    #print('%s instr:'%dev.name, dev.instructions)
                                #    print('%s raw data:' % dev.name, dev.raw_output)

                                if dev.name == 'QRF_trigger_0':
                                    print('\n', dev.name)
                                    print(t)
                                    print(dev.raw_output,'\n')

                                if len(dev.raw_output) != len(t):  # sanity check.
                                    raise LabscriptError('generate_code: raw output (%i) not consistent with times (%i)? (should not happen)' % (len(dev.raw_output), len(t)))

                                # convert raw data into data word and accumulate with other channels
                                d |= dev.to_word(dev.raw_output)

                                # mark changes
                                chg[0]  |= (dev.raw_output[0] != dev.default_value)
                                chg[1:] |= ((d[1:] - d[:-1]) != 0)

                            # check conflicts with devices of different address
                            i = indices[chg]
                            conflicts[i,dev.rack] |= changes[i,dev.rack]
                            changes[i,dev.rack] = True

                            # save data where output changed
                            # we have to mask NOP bit from unused channels
                            data[i,dev.rack+1] = d[chg] & DATA_ADDR_MASK
                        else:
                            # no shared address: collect data for each individual device
                            for dev in IM.child_devices:
                                #if np.count_nonzero(dev.raw_output == dev.default_value) != len(t):
                                #    # print('%s instr:'%dev.name, dev.instructions)
                                #    print('%s raw data:' % dev.name, dev.raw_output)

                                if not generate_code_with_labscript:
                                    t = dev.times
                                    if len(t) == 0: continue
                                    indices = np.argwhere(np.isin(times, t)).ravel()

                                if len(dev.raw_output) != len(t):  # sanity check.
                                    raise LabscriptError('generate_code: raw output not consistent with times? (should not happen)')

                                # convert raw data into data word
                                d = dev.to_word(dev.raw_output)
                                #print('%s data:' % dev.name, d)

                                # mark changes
                                chg = np.empty(shape=(len(t),), dtype=np.bool_)
                                chg[0]  = (dev.raw_output[0] != dev.default_value)
                                chg[1:] = ((d[1:] - d[:-1]) != 0)
                                i = indices[chg]

                                # detect conflicts with other devices
                                conflicts[i, dev.rack] |= changes[i, dev.rack]
                                changes[i,dev.rack] = True

                                # save data where output changes
                                data[i,dev.rack+1] = d[chg]

            if special:
                # collect special data bits
                # these bits are combined with existing data and cannot cause conflicts
                for pseudoclock in self.child_devices:
                    for clockline in pseudoclock.child_devices:
                        if generate_code_with_labscript:
                            t = pseudoclock.times[clockline]
                            indices = np.argwhere(np.isin(times, t)).ravel()
                            if len(t) == 0: continue
                        for IM in clockline.child_devices:
                            if isinstance(IM, SpecialIM):
                                for dev in IM.child_devices:
                                    #if np.count_nonzero(dev.raw_output == dev.default_value) != len(t):
                                    #    print('%s instr:'%dev.name, dev.instructions)
                                    #    print('%s raw data:' % dev.name, dev.raw_output)

                                    if not generate_code_with_labscript:
                                        t = dev.times
                                        if len(t) == 0: continue
                                        indices = np.argwhere(np.isin(times, t)).ravel()

                                    if len(dev.raw_output) != len(t):  # sanity check.
                                        raise LabscriptError('generate_code: raw output not consistent with times? (should not happen)')

                                    # convert raw data into data word
                                    d = dev.to_word(dev.raw_output)
                                    #print('%s data:' % dev.name, d)

                                    # check if strobe bit is set somewhere
                                    if np.count_nonzero(d & BIT_STRB_SH) > 0:
                                        special_STRB = True

                                    # take all non-default values
                                    mask = (d != dev.default_value)
                                    if t[-1] not in dev.instructions:
                                        # remove last entry when was automatically inserted by labscript, i.e. when its not in instructions
                                        mask[-1] = False
                                    i = indices[mask]

                                    # mark all non-default special entries as changed data
                                    changes[i, dev.rack] |= True

                                    # combine ALL non-default special data bits with existing data
                                    data[i,dev.rack+1] |= d[mask]

            if False:
                # show all data for debugging
                self.show_data(data, '\ndata (all):')
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
                        if generate_code_with_labscript:
                            t = pseudoclock.times[clockline]
                            indices = np.argwhere(np.isin(times, t)).ravel()
                        for IM in clockline.child_devices:
                            for dev in IM.child_devices:
                                if not generate_code_with_labscript:
                                    t = dev.times
                                    indices = np.argwhere(np.isin(times, t)).ravel()
                                d = dev.to_word(dev.raw_output)
                                chg = np.empty(shape=(len(t),), dtype=np.bool_)
                                chg[0] = (dev.raw_output[0] != dev.default_value)
                                chg[1:] = ((d[1:] - d[:-1]) != 0)
                                mask = np.isin(t[chg], conflicts_t[dev.rack])
                                if np.count_nonzero(mask) > 0:
                                    info = (dev.type,  # channel type
                                            dev.rack,  # rack number
                                            dev.address,  # address
                                            indices[chg][mask],  # sample index
                                            t[chg][mask],  # time in seconds
                                            list(np.concatenate(([dev.default_value], dev.raw_output[chg][:-1]))[mask]), # old value
                                            dev.raw_output[chg][mask])  # new value
                                    if dev.name in conflicts_ch:
                                        old = conflicts_ch[dev.name]
                                        conflicts_ch[dev.name] = (old[i] if i < 3 else old[i] + info[i] for i in range(len(old)))
                                    else:
                                        conflicts_ch[dev.name] = info

                for rack in range(self.num_racks):
                    if len(conflicts_t) > 0:
                        indices = np.argsort(conflicts_t[rack])
                        save_print('\n%i time conflicts on %i channels detected:\n' % (len(conflicts_t[rack]), len(conflicts_ch)))
                        save_print('%35s %4s %4s %12s %12s %12s %12s' % ('channel name','rack','addr','sample','time (s)','old value','new value'))
                        for t in conflicts_t[rack]:
                            for ch, info in conflicts_ch.items():
                                for i in range(len(info[3])):
                                    if info[4][i] == t:
                                        if info[0] == TYPE_DO: # digital out
                                            s2 = "0x%02x" % (info[2])
                                            s5 = '-' if info[5][i] == DO_AUTO_VALUE else ("low" if info[5][i]==0 else "high")
                                            s6 = '-' if info[6][i] == DO_AUTO_VALUE else ("low" if info[6][i]==0 else "high")
                                            s7 = ''
                                        elif info[0] == TYPE_AO: # analog out
                                            s2 = "0x%02x" % (info[2])
                                            s5 = '-' if info[5][i] == AO_AUTO_VALUE else "%12.6f" % info[5][i]
                                            s6 = '-' if info[6][i] == AO_AUTO_VALUE else "%12.6f" % info[6][i]
                                            s7 = ''
                                        elif info[0] == TYPE_SP:
                                            # special data
                                            # note: since address = None will never cause conflict but can appear with other conflicts when at same time
                                            s2 = '-'
                                            s5 = '-' if info[5][i] == SP_AUTO_VALUE else "0x%8x" % info[5][i]
                                            s6 = '-' if info[6][i] == SP_AUTO_VALUE else "0x%8x" % info[6][i]
                                            s7 = ' ignore'
                                        save_print('%35s %4i %4s %12i %12.6f %12s %12s%s'%(ch, info[1], s2, info[3][i], info[4][i], s5, s6, s7))
                            save_print()
                save_print()
                raise LabscriptError('%i time conflicts detected! (abort compilation)' % (np.count_nonzero(conflicts)))

            # detect samples where anything changes on any rack
            chg = np.any(changes, axis=1)

            # where special data STRB bit is set we do not toggle strobe bit in data.
            # however, the board always executes first instruction regardless of first strobe bit.
            # therefore we give an error below and in SKIP() when for first sample STRB bit is set.
            # here we retain first sample such that at least one sample is before any sample with STRB bit.
            # if first sample does not contain data it will be marked with NOP bit below.
            if special_STRB: chg[0] = True

            # remove samples without changes on any rack
            data = data[chg]
            changes = changes[chg]

            # add NOP for racks without changes
            for rack in range(self.num_racks):
                data[:,rack+1][~changes[:,rack]] = BIT_NOP_SH

            # insert toggle strobe into data
            if special_STRB:
                # we do not want to toggle all data
                for rack in range(self.num_racks):
                    mask = np.array(data[:,rack+1] & BIT_STRB_SH == 0, dtype=np.uint32)
                    if mask[0] == 0:
                        # first sample has strobe bit set which does not work (see notes above).
                        if data[0,0] == 0: raise LabscriptError("you have specified do_not_toggle_STRB for time = 0 which does not work! use NOP bit instead.")
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

            t_end = get_ticks()
            t_new = (t_end-t_start)*1e3
            self.show_data(data, 'data: (%.3fms)' % (t_new))
            print('total_time %.3fms' % ((get_ticks() - total_time) * 1e3))

            data_test = data

            for secondary in self.secondary_boards:
                #save_print('%s call generate code for %s' % (self.name, secondary.name))
                secondary.generate_code(hdf5_file)

            return

        # monitor calculation time
        t_start = get_ticks()
        print('total_time %.3fms' % ((get_ticks() - total_time) * 1e3))

        # old code. works only with single pseudoclocks and clocklines!
        for pseudoclock in self.child_devices:
            for clockline in pseudoclock.child_devices:
                if isinstance(clockline.child_devices[0],SpecialIM): continue
                #get list of times in seconds
                #TODO: difference with self._pseudoclock.clock?
                #save_print(self._pseudoclock.clock)
                # note: even if start time is > 0 there is always an entry at time = 0 = self.t0 for each Output device.
                #       however, this entry might be removed below if nothing happens at time = 0
                times = np.array(pseudoclock.times[clockline])
                save_print("'%s' '%s' %i times:" % (pseudoclock.name, clockline.name, len(times)), times)
                # check overflow
                if (np.max(times)*self.bus_rate) > MAX_TIME:
                    raise LabscriptError('maximum time %.3f s is larger allowed maximum time %.3f s for bus sampling rate %.3f MHz' % (np.max(times), MAX_TIME/self.bus_rate, self.bus_rate/1e6))
                # allocate data and list of changes
                # data = contains 2-3 columns with time, data0, optional data1
                #        number of rows = number of different times
                # changes = True when data0/1 has changed, otherwise False.
                # conflits = True when several devices on the same rack change at the same time
                data      = np.zeros(shape=(len(times), self.num_racks+1), dtype=np.uint32) # this includes time and data for each rack
                changes   = np.zeros(shape=(len(times), self.num_racks),   dtype=np.bool_)
                conflicts = np.zeros(shape=(len(times), self.num_racks),   dtype=np.bool_)

                #get timestamps
                delta = data[:, 0] = time_to_word(times, self.bus_rate, self.digits)
                # check non-monotone increase in time, i.e. 0 or negative time difference.
                delta = delta[1:]-delta[0:-1]
                min_step = np.min(delta)
                if np.min(delta) < 1:
                    save_print(times)
                    save_print(delta)
                    error = delta < 1
                    delta = (times[1:]-times[0:-1])[error]
                    error = np.concatenate([[False],error])
                    times = times[error]
                    raise LabscriptError('data contains time steps smaller than %.3fns (rate %.3f MHz) at %d time (s) and delta (ns):\n%s\n%s' %
                                         (1e9/self.bus_rate, self.bus_rate/1e6, len(times), str(times), str(delta*1e9)))

                #combine data for all Intermediate devices of ClockLine
                #and check time conflicts = changes of devices with different address cannot be at the same time
                for IM in clockline.child_devices:
                    if isinstance(IM, (AnalogChannels, DigitalChannels)): # TODO: add DDS/Moglabs
                        IM.get_data(times=times, data=data, changes=changes, conflicts=conflicts)
                if np.any(conflicts):
                    # at least one time conflict detected: show all changing channels at first time conflict for each rack
                    text = ''
                    for rack in range(self.num_racks):
                        cc = conflicts[:,rack]
                        if any(cc):
                            # get first conflict for rack
                            index = np.arange(len(times))[cc]
                            num = len(index)
                            first_time = times[index[0]]
                            cc = np.zeros(shape=(len(times),),dtype=np.bool_)
                            cc[index[0]] = True
                            # we call get_data for all channels again to get all channels for conflicts per rack
                            channels = {}
                            for IM in clockline.child_devices:
                                if isinstance(IM, (AnalogChannels, DigitalChannels)):  # TODO: add DDS/Moglabs
                                    IM.get_data(times=times, conflicts=cc, rack=rack, channels=channels)
                            #save_print(channels)
                            if (len(channels) != 1) or (first_time not in channels):
                                raise LabscriptError('unexpected time in channels!')
                            if num == 1:
                                text = "\n\n'%s' time conflict at time %.6f seconds with %i channels on rack %i:\n\n" % (self.name, first_time, len(channels[first_time]), rack)
                            else:
                                save_print(times)
                                text = "\n\n'%s' %i time conflicts detected!\nfirst is at time %.6f seconds with %i channels on rack %i:\n\n" % (self.name, len(index), first_time, len(channels[first_time]), rack)
                            ch_len = 0
                            for n in channels[first_time]:
                                if len(n[0])>ch_len: ch_len = len(n[0])
                            for n in channels[first_time]:
                                # TODO: unit conversion?
                                if n[1] is None: text += ('%%-%is : None -> %%f\n' % (ch_len) % (n[0], n[2]))
                                else:            text += ('%%-%is : %%f -> %%f\n' % (ch_len) % (n[0], n[1], n[2]))
                    raise LabscriptError(text)

                # set NOP bit for data without action. this keeps timing but does not generate a strobe signal.
                # TODO: maybe it would be more efficient to save changes directly in data with BIT_NOP and remove changes?
                for rack in range(self.num_racks):
                    data[:,rack+1] = data[:,rack+1] | (BIT_NOP_SH*np.invert(changes[:,rack]))

                # remove data where nothing happens in all racks except last sample
                # this happens for example with slow ramps with small varyation where in many samples nothing changes
                # last sample is needed to ensure that primary board waits for secondary board to finish. maybe also runviewer needs it?
                chg = changes[:, 0]
                for r in range(1,self.num_racks):
                    chg = chg | changes[:,r]
                chg[-1] = True # we keep always last
                data = data[chg]

                # test inserting toggle strobe. TODO: not optimized at all!
                # TODO: do this when strobe bit enabled. use programmed strobe bit.
                if True:
                    for rack in range(self.num_racks):
                        toggle = (np.arange(len(data[:,rack+1])) & 0x1) << BIT_STRB;
                        data[:,rack+1] = data[:,rack+1] | toggle

                if False:
                    # insert special data bits at given rack and time
                    # TODO: STROBE needs special treatement already in loop above!
                    sort = False
                    print(self.special)
                    for t,bits in self.special.items():
                        t = time_to_word([t], self.bus_rate, self.digits)[0]
                        mask = (data[:,0] == t)
                        print(mask)
                        count = np.count_nonzero(mask)
                        if count == 0:
                            # time not in list: append time with bit and NOP set. sort below.
                            sort = True
                            data = np.concatenate((data,np.array([[t]+[b | BIT_NOP_SH for b in bits]],dtype=np.uint32)))
                            print('time %i not in list'%t, data[-1])
                            print(bits)
                        elif count != 1: # sanity check
                            raise LabscriptError("%i occurrences of %f in times!?" % (count, t))
                        else:
                            # time in list
                            act = data[mask][0]
                            print(act)
                            print(bits)
                            print(np.array([t] + [act[i+1] | b for i,b in enumerate(bits)],dtype=np.uint32))
                            data[mask] = np.array([t] + [act[i+1] | b for i,b in enumerate(bits)],dtype=np.uint32)
                            print('time %i in list'%t, data[mask])
                    if sort:
                        indices = np.argsort(data[:,0])
                        data  = data[indices]
                    print(data.dtype)
                    print(data.shape)

                if data[0,0] < self.start_time:
                    raise LabscriptError('\n\nfirst time cannot be < %s.start_time = %.3e seconds!\n' % (self.name, self.start_time))

                t_end = get_ticks()
                t_old = (t_end - t_start) * 1e3
                self.show_data(data, 'data [old]: (%.3fms)' % (t_old))
                print('total_time %.3fms' % ((get_ticks() - total_time)*1e3))

                # compare with new data
                t_start = get_ticks()
                self.show_data(data_test, 'data [new]')
                mask_old = np.isin(data[:,0],data_test[:,0])
                mask_new = np.isin(data_test[:,0],data[:,0])
                differences = np.zeros(shape=(np.count_nonzero(mask_old), self.num_racks), dtype=np.bool_)
                for rack in range(self.num_racks):
                    differences[:,rack] = (data[:,rack+1][mask_old] != data_test[:,rack+1][mask_new])
                differences = np.any(differences, axis=1)
                if np.count_nonzero(~mask_old) > 0:
                    self.show_data(data[~mask_old], 'missing in new:')
                if np.count_nonzero(~mask_new) > 0:
                    self.show_data(data_test[~mask_new], 'missing in old:')
                if np.count_nonzero(differences) > 0:
                    self.show_data(data[mask_old][differences], 'old data differences:')
                    self.show_data(data_test[mask_new][differences], 'new data differences:')
                t_end = get_ticks()
                print('%.3fms' % ((t_end-t_start)*1e3))
                print('total_time %.3fms' % ((get_ticks() - total_time)*1e3))

                save_print('%i samples, smallest time step %d x %.3f us' % (len(data), min_step, 1e6/self.bus_rate))
                if len(data) >= 2:
                    save_print('first time %s, second time %s, last time %s' % (time_to_str(data[0,0]/self.bus_rate),time_to_str(data[1,0]/self.bus_rate),time_to_str(data[-1,0]/self.bus_rate)))

                if TEST_TIMING_ERROR and (len(data) > 1) and ((TEST_PRIM == None) or (TEST_PRIM == self.is_primary)):
                    # add same time in middle of data which should cause time error of board.
                    i = int(len(data)//2)
                    save_print("'%s': inserting time %.3f instead of %.3f at sample %i!\nshould cause timing error of board!" % (self.name, data[i+1,0], data[i,0], i))
                    data[i,0] = data[i+1,0]

                # TODO: here we must break for several pseudoclocks/clocklines otherwise we get an error in hdf5 file
                if pseudoclock != self.child_devices[0]: break
                if clockline != pseudoclock.child_devices[0]: break

                # save matrix for each board to file
                # TODO: had to add device name also to devices otherwise get error. however now we create board#_devices/board#.
                group = hdf5_file['devices'].create_group(self.name)
                group.create_dataset('%s_matrix'%self.name, compression=config.compression, data=data)

                # save extra worker arguments into hdf5. we must convert everything into a string and convert it back in worker.
                save_print('saving worker args ex:\n', self.worker_args_ex)
                if decode_string_with_eval:
                    d = str(self.worker_args_ex)
                else:
                    d = to_string(self.worker_args_ex)
                group.create_dataset('%s_worker_args_ex' % self.name, shape=(1,), dtype='S%i'%(len(d)), data=d.encode('ascii','ignore'))

                #TODO: add another group with all used channels. this can be used by runviewer to avoid displaying unused channels.
                #      channels should be already saved somehow in hdf5? so maybe one can add this info for each channel there?

                # save stop_time and if master pseudoclock = primary board into hdf5
                # for master_pseudoclock t0 = 0
                self.set_property('is_master_pseudoclock', self.is_master_pseudoclock, location='device_properties')
                self.set_property('stop_time', self.stop_time, location='device_properties')

                save_print("'%s' generating code done" % (self.name))

                # labscript calls generate_code only for primary board.
                # manually call it for all secondary boards
                for secondary in self.secondary_boards:
                    save_print('%s call generate code for %s' % (self.name, secondary.name))
                    secondary.generate_code(hdf5_file)

                # save if primary board and list of secondary boards names, or name of primary board.
                # the names identify the worker processes used for interprocess communication.
                if self.is_primary:
                    self.set_property('is_primary', True, location='connection_table_properties', overwrite=False)
                    self.set_property('boards', [s.name for s in self.secondary_boards], location='connection_table_properties', overwrite=False)
                else:
                    self.set_property('is_primary', False, location='connection_table_properties', overwrite=False)
                    self.set_property('boards', [self.primary_board.name], location='connection_table_properties', overwrite=False)

        print('total_time %.3fms' % ((get_ticks() - total_time)*1e3))
        print('t_new = %.3fms' % t_new)
        print('t_old = %.3fms' % t_old)


    def SKIP(self, time, rack=0, do_not_toggle_STRB=False):
        "set NOP bit or do not toggle strobe bit at given time = time is waited but no output generated"
        if do_not_toggle_STRB:
            if time == 0: raise LabscriptError("SKIP: you have specified do_not_toggle_STRB for time = 0 which is not allowed! use NOP bit instead.")
            bit = BIT_STRB_SH
        else:
            bit = BIT_NOP_SH
        print('insert SKIP bit at time %f, rack %i'%(time, rack))
        if time in self.special_data[rack].instructions:
            self.special_data[rack].instructions[time] |= bit
        else:
            self.special_data[rack].add_instruction(time,bit)

    def WAIT(self, time, rack=0):
        "set stop bit at given time = top board and wait for restart trigger"
        bit = BIT_STOP_SH
        print('insert WAIT bit at time %f, rack %i'%(time, rack))
        if time in self.special_data[rack].instructions:
            self.special_data[rack].instructions[time] |= bit
        else:
            self.special_data[rack].add_instruction(time,bit)

    def IRQ(self, time, rack=0):
        "set data IRQ bit at given time = generates an IRQ at given time. might be used to trigger events without polling."
        bit = BIT_IRQ_SH
        print('insert IRQ bit at time %f, rack %i'%(time, rack))
        if time in self.special_data[rack].instructions:
            self.special_data[rack].instructions[time] |= bit
        else:
            self.special_data[rack].add_instruction(time,bit)

    def set_start_trigger(self, source, level):
        if STR_INPUTS in self.worker_args_ex: inputs = self.worker_args_ex[STR_INPUTS]
        else:                                 inputs = {}
        inputs['start trigger'] = (source, level)
        self.worker_args_ex[STR_INPUTS] = inputs

    def set_restart_trigger(self, source, level):
        if STR_INPUTS in self.worker_args_ex: inputs = self.worker_args_ex[STR_INPUTS]
        else:                                 inputs = {}
        inputs['restart trigger'] = (source, level)
        self.worker_args_ex[STR_INPUTS] = inputs

    def set_stop_trigger(self, source, level):
        if STR_INPUTS in self.worker_args_ex: inputs = self.worker_args_ex[STR_INPUTS]
        else:                                 inputs = {}
        inputs['stop trigger'] = (source, level)
        self.worker_args_ex[STR_INPUTS] = inputs

    def set_ctrl_in(self, ctrl_in):
        """
        set input control register. this can be either a dictionary as given for connection table or the register value directly.
        this overwrites what might be given in connection table.
        """
        if STR_INPUTS in self.worker_args_ex: inputs = self.worker_args_ex[STR_INPUTS]
        else:                                 inputs = {}
        if not isinstance(ctrl_in, dict):
            ctrl_in = get_in_selection(ctrl_in, return_NONE=False)
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
            ctrl_out = get_out_selection(ctrl_out, return_NONE=False)
        for key, value in ctrl_out.items():
            outputs[key] = value
        self.worker_args_ex[STR_OUTPUTS] = outputs

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

    def set_sync_params(self, wait=None, phase=None):
        "set sync_phase or sync_wait. this overwrites what might be given in connection table."
        if wait is not None: self.worker_args_ex[STR_SYNC_WAIT] = wait
        if phase is not None: self.worker_args_ex[STR_SYNC_PHASE] = phase

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
    # type = device type: TYPE_AO or TYPE_DO
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

def get_channel_name(ID):
    # get channel name as unique string containing type, rack, address channel
    type, rack, address, channel = unpack_ID(ID)
    if type == TYPE_AO: return "AO%x.%02x.%x" % (rack, address, channel)
    elif type == TYPE_DO: return "DO%x.%02x.%x" % (rack, address, channel)
    else: return "?%x.%x.%x" % (rack, address, channel)

# finds all channels of board
# device = intermediate device (AnalogChannels or DigitalChannels) connection object
# if is_analog device is AnalogChannels, otherwise DigitalChannels connection object
# returns dictionary with key = channel name as given to AnaolgChannel, DigitalChannel
# value = list of [ID, properties, child connection object, name, unit conversion class]
def get_channels(device, is_analog):
    #get all digital and analog outputs from intermediate device
    child_list = {}
    if is_analog:
        #num_AO = device.properties['num_AO'] # AnalogChannels
        #save_print("'%s' with %i analog outputs:" % (device.name, len(device.child_list)))
        for child_name, child in device.child_list.items():
            rack, address, channel = child.properties['address'].split('/')
            rack = int(rack)
            address = int(address)
            channel = int(channel)
            ID = get_ID(type=TYPE_AO,rack=rack,address=address,channel=channel)
            ch_name = get_channel_name(ID)
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
    else:
        #num_DO = device.properties['num_DO'] # DigitalChannels
        #save_print("'%s' with %i digital outputs:" % (device.name, len(device.child_list)))
        for child_name, child in device.child_list.items():
            rack, address, channel = child.properties['address'].split('/')
            rack = int(rack)
            address = int(address)
            channel = int(channel)
            #save_print("  '%s' %i/0x%0x/%i" % (child.name, rack, address, channel))
            props = default_do_props
            ID = get_ID(type=TYPE_DO, rack=rack, address=address, channel=channel)
            ch_name = ch_name = get_channel_name(ID)
            child_list[child_name] = [ID,props,child,ch_name,None]
    return child_list

@runviewer_parser
class RunviewerClass(object):
    
    def __init__(self, path, device):
        # called for each board and intermediate device
        self.path = path
        self.name = device.name
        self.device = device
        self.top = self.device
        self.type = None
        save_print("runviewer loading '%s'" % (device.name))
        if device.device_class == 'FPGA_board': # pseudoclock device
            self.type = TYPE_board
            # save_print(clockline.name)
            self.bus_rate = device.properties['bus_rate']
        else: # intermediate device
            # find top device = board0
            while self.top.parent is not None:
                self.top = self.top.parent
            # get bus rate
            self.bus_rate = self.top.properties['bus_rate']
            save_print("top device '%s', bus rate %.3e Hz" %(self.top.name,self.bus_rate))
            if device.device_class == 'AnalogChannels':
                self.type = TYPE_AO
                save_print("runviewer loading '%s:%s' (analog outputs)" % (self.top.name, device.name))
                self.ao_list = get_channels(device, True)
            elif device.device_class == 'DigitalChannels':
                self.type = TYPE_DO
                save_print("runviewer loading '%s:%s' (digital outputs)" % (self.top.name, device.name))
                self.do_list = get_channels(device, False)
            else: # unknown device
                save_print("runviewer loading '%s:%s' (ignore)" % (self.top.name, device.name))

    def get_traces(self, add_trace, clock=None):
        # called for each board and intermediate device
        data = []
        traces = {}
        with h5py.File(self.path, 'r') as f: #get data sent to board
            group = f['devices/%s' % (self.top.name)]
            data = group['%s_matrix'%self.top.name][:]
        if len(data) == 0:
            save_print("'%s:%s' add trace (type %d) no data!" % (self.top.name, self.name, self.type))
        else:
            #save_print('matrix\n',data)
            if self.type == TYPE_board: # main board
                save_print("'%s' add trace (board) %i samples" % (self.name, len(data)))
                time = word_to_time(data[:,0], self.bus_rate)
                for pseudoclock in self.device.child_list.values():
                    if pseudoclock.device_class == 'FPGA_PseudoClock':
                        for clockline in pseudoclock.child_list.values():
                            if clockline.device_class == 'ClockLine':
                                value = [(i & 1) for i in range(len(time))]
                                add_trace(clockline.name, (time, value), None, None)
                                traces[clockline.name] = (time, value)
            elif self.type == TYPE_AO: # analog outputs (intermediate device)
                save_print("'%s:%s' add trace (analog out) %i samples" % (self.top.name, self.name, len(data)))
                # for all channels extract from data all entries with channel device address & rack
                #TODO use self.device.child_list[i].unit_conversion_class/params
                try:
                    for name, ll in self.ao_list.items():
                        [ID,props,child,ch_name,unit_conversion_class] = ll
                        # we have access to unit conversion class and parameters
                        ch = self.device.child_list[name]
                        if unit_conversion_class is not None:
                            unit = ch.unit_conversion_params['unit']
                            save_print("'%s' unit conversion class: '%s', unit '%s'" % (name, ch.unit_conversion_class, unit))
                            #for k,v in ch.unit_conversion_params.items():
                            #    save_print('%s : %s' % (k, v))
                            if runviewer_show_units: # plot in given units
                                txt = 'unit_conversion_class(calibration_parameters=%s)' % (ch.unit_conversion_params)
                                unit_conversion = eval(compile(txt, 'conv', 'eval'))
                                to_unit = getattr(unit_conversion, unit+'_from_base')
                            #save_print(to_unit)
                            else: # plot in volts
                                to_unit = None
                        else:
                            #save_print("'%s' no unit conversion." % (name))
                            to_unit = None
                        rack = get_rack(ID)
                        addr = get_address(ID)
                        mask = (((data[:, rack + 1] & (BIT_NOP_SH | ADDR_MASK_SH)) >> ADDR_SHIFT) == addr)
                        d = data[mask]
                        if len(d) > 0: # data available
                            if runviewer_add_start_time and (d[0,0] > START_TIME):
                                # add last state of channel as initial state
                                d = np.concatenate([[np.concatenate([[START_TIME],d[-1,1:]])],d])
                            time = d[:,0]/self.bus_rate
                            #value = ((d[:,rack + 1] & DATA_MASK)/0x7fff)*10.0 # TODO: convertion into volts or any other unit
                            #value = word_to_V(d[:,rack + 1] & DATA_MASK)  # TODO: convertion into volts or any other unit
                            if to_unit is None:
                                value = word_to_V(d[:, rack + 1] & DATA_MASK)
                            else:
                                value = to_unit(word_to_V(d[:, rack + 1] & DATA_MASK))
                            if time[-1] != (data[-1,0]/self.bus_rate): # extend trace to last time
                                time = np.concatenate([time,[data[-1,0]/self.bus_rate]])
                                value = np.concatenate([value, [value[-1]]])
                            #save_print("ao '%s' 0x%x:" % (name,ID))
                            #save_print('time = ',time)
                            # we add trace for all channels, even if not used
                            add_trace(name, (time, value), self, ch_name)
                            traces[name] = (time, value)
                            save_print("'%s' (%s) %i samples" % (name, ch_name, len(value)))
                            if len(value) <= 2:
                                save_print(np.transpose([time,value]))
                        #else: # address is not used
                        #   save_print("'%s' (%s) not used" % (name, ch_name))
                        #    time = np.array([data[0, 0], data[-1, 0]]) / self.bus_rate
                        #    value = np.array([0.0, 0.0])
                except Exception as e:
                    save_print("exception '%s'" % (e))
                    raise e
            elif self.type == TYPE_DO: # digital outputs (intermediate device)
                save_print("'%s:%s' add trace (digital out) %i samples" % (self.top.name, self.name, len(data)))
                # get rack, address and mask from first channel. this is the same for all channels
                [ID, props, child, ch_name, unit_conversion_class] = list(self.do_list.values())[0]
                rack = get_rack(ID)
                addr = get_address(ID)
                mask = (((data[:,rack+1] & (BIT_NOP_SH|ADDR_MASK_SH))>>ADDR_SHIFT) == addr)
                #for i,di in enumerate(d):
                #    save_print("%8u %08x %s" % (di[0], di[1], mask[i]))
                d = data[mask]
                if len(d) > 0:  # address is used - find where channel changes
                    # for all channels find where channels change.
                    # note: first value is always set. last time is always added with last value.
                    #       this causes for unused channels to have still 2 entries (with 0) in list.
                    #       however, this happens only if on the same intermediate device channels are used.
                    # TODO: save into hdf5 first user value or number of user values per channel (or both).
                    #       with this information one could prevent unused channels to be displayed.
                    #       get_channels cannot return this information since gives only static channel properties.
                    if runviewer_add_start_time and (d[0, 0] > START_TIME):
                        # add last state of channel as initial state
                        d = np.concatenate([[np.concatenate([[START_TIME], d[-1, 1:]])], d])
                    for name, ll in self.do_list.items():
                        #[ID, props, parent, conn, last] = ll
                        [ID, props, child, ch_name, unit_conversion_class] = ll
                        channel = get_channel(ID)
                        bit = (d[:,rack+1] >> channel) & 1
                        chg = np.concatenate([[True],((bit[1:]-bit[0:-1]) != 0)])
                        time = d[:,0][chg]/self.bus_rate
                        value = bit[chg]
                        if time[-1] != (data[-1,0]/self.bus_rate): # extend trace to last time
                            time = np.concatenate([time,[data[-1,0]/self.bus_rate]])
                            value = np.concatenate([value, [value[-1]]])
                        #save_print("do '%s' 0x%x:" % (name,ID))
                        #save_print('time = ',time)
                        #save_print('data = ',value)
                        # we add trace for all channels, even if not used
                        # add_trace(name, (time, value), parent, conn)
                        add_trace(name, (time, value), self, ch_name)
                        traces[name] = (time, value)
                        save_print("'%s' (%s) %i samples" % (name, ch_name, len(value)))
                        if len(value) <= 2:
                            save_print(np.transpose([time,value]))
                    #else: # address is not used
                    #    save_print("'%s' (%s) not used" % (name, ch_name))
                    #    time = np.array([data[0, 0], data[-1, 0]]) / self.bus_rate
                    #    value = np.array([0, 0])
            else: # DDS not implemented
                save_print("'%s:%s' add trace (unknown?) %i samples" % (self.top_name, self.name, len(data)))
        #TODO: not sure what to return here?
        return traces


# vendor and product id and serial number
USB_VID     = 0xA5A5        # Prevedelli
#USB_PID    = 0x9958        # AD9958
#USB_PID    = 0x9854	    # Poli: AD9854
USB_PID     = 0x0001		# Poli: AD9854 broken firmware?
USB_SERIAL	= 3             # serial number

# init USB devices (still testing)
def FindUSBDevice():
    pass

from blacs.tab_base_classes import Worker, define_state, MODE_MANUAL, MODE_TRANSITION_TO_BUFFERED, MODE_TRANSITION_TO_MANUAL, MODE_BUFFERED
from blacs.device_base_class import DeviceTab

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
    if len(data) <= MAX_SHOW:
        times = data[:,0]/bus_rate
        if len(data) > 1: min_step = np.min(times[1:]-times[0:-1])
        else:             min_step = 0
        if len(data[0]) == 3:
            save_print('     time:      rack0      rack1')
            for d in data: save_print('%9u: 0x%08x 0x%08x' % (d[0], d[1], d[2]))
        else:
            save_print('     time:       data')
            for d in data: save_print('%9u: 0x%08x' % (d[0], d[1]))
        save_print('%i samples, smallest time step %.3es, rate %.3f MHz (send_data)' % (len(data), min_step, bus_rate*1e-6))
        if len(data) > 1: save_print('first time %fs, second time %es, last time %fs' % (times[0],times[1],times[-1]))
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
        # set sync phase only for secondary board
        #if sync_phase != SYNC_PHASE_NONE:
        #    result = send_recv_data(sock, to_client_data32(SERVER_SET_SYNC_PHASE, sync_phase), SOCK_TIMEOUT,
        #                            output='set sync phase 0x%x' % (sync_phase))
        #    if result != SERVER_ACK:
        #        save_print('set sync phase 0x%x failed!' % (sync_phase))
        #        return False
        # send configuration. server will return new configuration (no ACK)
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

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

# simple dialog box for warning user!
# remains open until user clicks ok but does not prevent labscript from running.
class warn_user_dialog(QDialog):
    def __init__(self, parent, title, text):
        QDialog.__init__(self, parent)

        self.setAttribute(Qt.WA_DeleteOnClose, True)  # make sure the dialog is deleted when the window is closed
        self.setWindowTitle(title)
        self.resize(500, 200)

        # update must be called at least one time to display dialog
        self.text = text
        self.first_time = True
        self.count = 0

        # layout
        layout = QVBoxLayout()
        self.setLayout(layout)

        # top row = icon + text
        top = QHBoxLayout()
        layout.addLayout(top, stretch=0)

        # icon
        #self.Bicon = QPushButton('button with icon')
        #self.Bicon.setIcon(self.style().standardIcon(getattr(QStyle.StandardPixmap, 'SP_MessageBoxWarning')))
        self.icon = QLabel()
        icon = self.style().standardIcon(getattr(QStyle.StandardPixmap, 'SP_MessageBoxWarning'))
        self.icon.setPixmap(icon.pixmap(QSize(64,64)))
        #self.icon.setStyleSheet("QLabel {background-color: red;}")
        top.addWidget(self.icon, alignment=Qt.AlignCenter, stretch=0)

        # text
        self.label = QLabel()
        if '%i' in self.text: self.label.setText(self.text % self.count)
        else:                 self.label.setText(self.text)
        self.label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.label.setStyleSheet("QLabel {background-color: red;}")
        top.addWidget(self.label, stretch=1)

        # bottom row = button in middle
        bottom = QHBoxLayout()
        layout.addLayout(bottom, stretch=1)

        # ok button
        self.button = QPushButton('ok', self)
        self.button.setMinimumHeight(50)
        #self.button.setFixedHeight(50)
        self.button.clicked.connect(self.ok_clicked)
        self.button.setStyleSheet('QPushButton {color: red; border:1px solid #ff0000; border-radius: 3px;}')
        bottom.addStretch(stretch=1)
        bottom.addWidget(self.button, stretch=2)
        bottom.addStretch(stretch=1)

        #self.show() # show only after first update

    def update(self, count=None, text=None, title=None):
        "update text. show dialog if called the first time"
        if text is not None: self.text = text
        if count is not None: self.count = count
        else:                 self.count += 1
        if '%i' in self.text:
            save_print(self.text % self.count)
            self.label.setText(self.text % self.count)
        else:
            self.label.setText(self.text)
        if title is not None: self.setWindowTitle(title)
        if self.first_time:
            self.first_time = False
            self.show()
        else:
            self.setHidden(False)

    def ok_clicked(self):
        save_print('warn_user_dialog: ok (reset count)')
        self.count = 0
        self.setHidden(True)

    def closeEvent(self, event):
        save_print('warn_user_dialog: closed')
        event.accept()

class FPGA_buttons(QWidget):
    def __init__(self, name, parent, worker_args={}):
        """
        creates button widgets and clock selection check boxes for FPGA board
        name   = unique name used to save and restore data
        parent = DeviceTab class
        worker_args = optional worker arguments given for board in connection_table with startup selections:
            'ext_clock':         if True external clock should be used
            'ignore_clock_loss': if True loss of external clock should be ignored
        notes:
        - calls parent.get_state when state button pressed
        - calls parent.conn when disconnect button pressed
        - calls parent.abort when abort button pressed
        - calls worker onChangeExtClock when external clock check box has been changed
        - calls worker onChangeIgnoreClockLoss when ignore clock loss check box has been changed
        """
        super(FPGA_buttons, self).__init__(parent._ui)

        self.parent       = parent
        self.store_clock  = name + '_' + STR_EXT_CLOCK
        self.store_ignore = name + '_' + STR_IGNORE_CLOCK_LOSS
        self.worker_args  = worker_args

        self.dialog_enable = True

        self.ext_clock = False
        self.ignore_clock_loss = False
        if STR_EXT_CLOCK in worker_args:
            self.ext_clock  = worker_args[STR_EXT_CLOCK]
        if STR_IGNORE_CLOCK_LOSS in worker_args:
            self.ignore_clock_loss  = worker_args[STR_IGNORE_CLOCK_LOSS]

        grid = QGridLayout(self)
        self.setLayout(grid)

        # device state button
        bt_state = QPushButton('get state')
        bt_state.setStyleSheet('QPushButton {border:1px solid #8f8f91; border-radius: 3px;}')
        grid.addWidget(bt_state,0,0)
        bt_state.clicked.connect(parent.get_state)

        # connect / disconnect button
        bt_conn = QPushButton('disconnect')
        bt_conn.setStyleSheet('QPushButton {border:1px solid #8f8f91; border-radius: 3px;}')
        grid.addWidget(bt_conn,0,1)
        bt_conn.clicked.connect(parent.conn)
        #TODO: get actual connection status and connect or disconnect with this button!

        # abort button
        bt_abort = QPushButton('abort!')
        bt_abort.setStyleSheet('QPushButton {color: red; border:1px solid #ff0000; border-radius: 3px;}')
        grid.addWidget(bt_abort,0,2)
        bt_abort.clicked.connect(parent.abort)

        # external clock
        self.cb_ext_clock = QCheckBox('external clock')
        self.cb_ext_clock.setChecked(self.ext_clock)
        #self.cb_ext_clock.setStyleSheet("color: black")
        #self.cb_ext_clock.setEnabled(False)
        self.cb_ext_clock.clicked.connect(self.onChangeExtClock)
        grid.addWidget(self.cb_ext_clock,1,0)

        # ignore clock loss
        self.cb_ignore_clock_loss = QCheckBox('ignore clock loss')
        self.cb_ignore_clock_loss.setChecked(self.ignore_clock_loss)
        self.cb_ignore_clock_loss.setStyleSheet("color: red")
        #self.cb_ignore_clock_loss.setEnabled(False)
        self.cb_ignore_clock_loss.clicked.connect(self.onChangeIgnoreClockLoss)
        grid.addWidget(self.cb_ignore_clock_loss, 1, 1)

    def onChangeExtClock(self, state):
        self.ext_clock = self.cb_ext_clock.isChecked()
        caption = (MSG_EXT_CLOCK % self.parent.device_name)
        if (not self.ext_clock) and (not self.parent.is_primary):
            if self.dialog_enable:
                # for secondary board disabling of external clock is not recommended
                qm = QMessageBox()
                ret = qm.question(self.parent._ui,
                                  caption + MSG_DISABLE + MSG_QUESTION,
                                  QUESTION_EXT_CLOCK % self.parent.device_name,
                                  qm.Yes | qm.No)
                if ret == qm.No:
                    self.ext_clock = True
                    self.cb_ext_clock.setChecked(True)
                    save_print(caption + MSG_DISABLE + MSG_ABORTED)
                    return
        if self.ext_clock: save_print(caption + MSG_ENABLED)
        else:              save_print(caption + MSG_DISABLED)
        # manually insert event into parent event queue as is done by tab_base_classes.py @define_state(MODE_MANUAL, True)
        # data = [function,[args,kwargs]] with function must be a generator, i.e. has to call yield.
        # see blacs/tab_base_classes.py for define_state and mainloop.
        self.parent.event_queue.put(allowed_states=MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=False, data=[self._onChangeExtClock, [[self.ext_clock],{}]])

    def _onChangeExtClock(self, parent, value):
        # executed by QT main thread (tab_base_classes.py Tab::mainloop). must be generator (with yield).
        yield (self.parent.queue_work(self.parent.primary_worker, 'onChangeExtClock', value))

    def onChangeIgnoreClockLoss(self, state):
        self.ignore_clock_loss = self.cb_ignore_clock_loss.isChecked()
        caption = MSG_IGNORE_CLOCK_LOSS % self.parent.device_name
        if self.ignore_clock_loss:
            if self.dialog_enable:
                qm = QMessageBox()
                ret = qm.question(self.parent._ui,
                                  caption + MSG_QUESTION,
                                  QUESTION_IGNORE_CLOCK_LOSS % self.parent.device_name,
                                  qm.Yes | qm.No)
                if ret == qm.No:
                    self.ignore_clock_loss = False
                    self.cb_ignore_clock_loss.setChecked(False)
                    save_print(caption + MSG_ABORTED)
                    return
        if self.ignore_clock_loss: save_print(caption + MSG_ENABLED)
        else:                      save_print(caption + MSG_DISABLED)
        # manually insert event into parent event queue as is done by tab_base_classes.py @define_state(MODE_MANUAL, True)
        # data = [function,[args,kwargs]] with function must be a generator, i.e. has to call yield.
        # see blacs/tab_base_classes.py for define_state and mainloop.
        self.parent.event_queue.put(allowed_states=MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=False, data=[self._onChangeIgnoreClockLoss, [[self.ignore_clock_loss], {}]])

    def _onChangeIgnoreClockLoss(self, parent, value):
        # executed by QT main thread (tab_base_classes.py Tab::mainloop). must be generator (with yield).
        yield (self.parent.queue_work(self.parent.primary_worker, 'onChangeIgnoreClockLoss', value))

    def get_save_data(self, data):
        "save current settings to data dictionary"
        data[self.store_clock]  = self.ext_clock
        data[self.store_ignore] = self.ignore_clock_loss

    def restore_save_data(self, data):
        "restore saved settings from data dictionary"
        self.dialog_enable = False # temporarily disable dialog
        if (self.store_clock in data) and (STR_EXT_CLOCK not in self.worker_args):
            self.ext_clock = data[self.store_clock]
            self.cb_ext_clock.setChecked(self.ext_clock)
        if (self.store_ignore in data) and (STR_IGNORE_CLOCK_LOSS not in self.worker_args):
            self.ignore_clock_loss = data[self.store_ignore]
            self.cb_ignore_clock_loss.setChecked(self.ignore_clock_loss)
        self.dialog_enable = True # enable dialog

class FPGA_IO(QWidget):
    def __init__(self, parent, name = "", dests=[], sources=[], levels=[], showHeader=True, is_input=True, worker_args={}):
        """
        creates input and output selectors of FPGA board
        name = unique name of widget. used to store and restore settings.
        parent = DeviceTab class.
        dests  = list of destination strings
        sources = list of source strings
        levels = list of levels strings
        showHeader = if True header is shown, otherwise not
        is_input = if True sources are inputs and dests are possible trigger settings and
                   get_ctrl_in() is used to calculate trigger control register value and OnChangeInputs is called in worker,
                   if False sources are internal FPGA signals and dests are outputs and
                   get_ctrl_out() is used to calculate output control register value and OnChangeOutputs is called in worker.
        worker_args = optional worker arguments given for board in connection_table with startup selections:
        notes:
        - calls worker onChangeInputs/Outputs functions when user changes selection!
        """
        super(FPGA_IO, self).__init__(parent._ui)

        self.name        = name
        self.parent      = parent
        self.dests       = dests
        self.sources     = []
        self.levels      = []
        self.is_input    = is_input
        self.init        = {}
        if self.is_input and (STR_INPUTS in worker_args):
            self.init = worker_args[STR_INPUTS]
        if (not self.is_input) and (STR_OUTPUTS in worker_args):
            self.init = worker_args[STR_OUTPUTS]

        self.change_enable = True
        self.dialog_enable = True

        grid = QGridLayout(self)
        self.setLayout(grid)

        self.value = 0;

        if showHeader:
            grid.addWidget(QLabel('destination'), 0, 0)
            grid.addWidget(QLabel('source'), 0, 1)
            grid.addWidget(QLabel('level'), 0, 2)
            row = 1
        else:
            row = 0
        for i,name in enumerate(dests):
            grid.addWidget(QLabel(name), row + i, 0)
            src = QComboBox()
            for source in sources:
                src.addItem(source)
            grid.addWidget(src, row + i, 1)
            self.sources.append(src)
            lvl = QComboBox()
            for level in levels:
                lvl.addItem(level, i)
            grid.addWidget(lvl, row + i, 2)
            self.levels.append(lvl)
            src.currentIndexChanged.connect(self.changed)
            lvl.currentIndexChanged.connect(self.changed)
        # init combo boxes (all must have been created). this calls 'changed' for each option.
        self.init_items(self.init, first_time=True)

    def init_items(self, init, first_time=False):
        # initialize combo boxes. if first_time = False take only options which are NOT in self.init.
        # this allows to give starting selections in worker_args,
        # or if no worker_args given, restore last settings in GUI (using restore_save_data).
        if len(init) > 0:
            self.change_enable = False # changed() will be called for each changed item. this avoids calling worker each time
            for i, name in enumerate(self.dests):
                if name in init:
                    if first_time or (name not in self.init):
                        src = self.sources[i]
                        index = src.findText(init[name][0])
                        if (index >= 0): src.setCurrentIndex(index)
                        else:            save_print("error init %s: '%s' is not in sources" % (self.name, name[0]))
                        lvl = self.levels[i]
                        index = lvl.findText(init[name][1])
                        if (index >= 0): lvl.setCurrentIndex(index)
                        else:            save_print("error init %s: '%s' is not in levels" % (self.name, name[1]))
            self.change_enable = True
            if not first_time:
                # update of worker when all changes are done
                self.dialog_enable = False # disable dialog box
                self.changed(0)
                self.dialog_enable = True

    def changed(self, index):
        # user changed any combo box. for simplicity we go through all of them and recalculate control register value.
        #item = self.sender()
        #name = item.currentText()
        #i = item.itemData(index)
        if not self.change_enable: return # do nothing while init_items is active
        selection = {}
        for i,name in enumerate(self.dests):
            source = self.sources[i].currentText()
            if (source != IN_SRC_NONE):
                selection[name] = (source, self.levels[i].currentText())
        if self.is_input:
            value         = get_ctrl_in(selection)
            prim_sync_out = False
            sec_trg_in    = (not self.parent.is_primary) and (not is_in_start(value))
        else:
            value         = get_ctrl_out(selection)
            prim_sync_out = self.parent.is_primary and (not is_sync_out(value))
            sec_trg_in    = False
        if prim_sync_out or sec_trg_in:
            if prim_sync_out:
                caption = MSG_SYNC_OUT % self.parent.device_name
                message = QUESTION_SYNC_OUT % self.parent.device_name
            else:
                caption = MSG_START_TRG % self.parent.device_name
                message = QUESTION_START_TRG % self.parent.device_name
            if self.dialog_enable:
                # disabling of sync out on primary board and external trigger on secondary board is not recommended
                qm = QMessageBox()
                ret = qm.question(self.parent._ui, caption + MSG_DISABLE + MSG_QUESTION, message, qm.Yes | qm.No)
                if ret == qm.No:
                    save_print(caption + MSG_DISABLE + MSG_ABORTED)
                    # revert to previous selection
                    selection = get_in_selection(self.value) if self.is_input else get_out_selection(self.value)
                    self.init_items(selection, first_time=True)
                    return
            save_print(caption + MSG_DISABLED)
        self.value = value
        if self.is_input: save_print(MSG_INPUT_SETTING  % (self.parent.device_name, self.value, get_in_info(self.value)))
        else:             save_print(MSG_OUTPUT_SETTING % (self.parent.device_name, self.value, get_out_info(self.value)))
        # manually insert event into parent event queue as is done by tab_base_classes.py @define_state(MODE_MANUAL, True)
        # data = [function,[args,kwargs]] with function must be a generator, i.e. has to call yield.
        # see blacs/tab_base_classes.py for define_state and mainloop.
        self.parent.event_queue.put(allowed_states=MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=False, data=[self._changed, [[self.value],{}]])

    def _changed(self, parent, value):
        # executed by QT main thread (tab_base_classes.py Tab::mainloop). must be generator (with yield).
        yield (self.parent.queue_work(self.parent.primary_worker, 'onChangeInputs' if self.is_input else 'onChangeOutputs', value))

    def get_save_data(self, data):
        "save current settings to data dictionary"
        data[self.name] = self.value

    def restore_save_data(self, data):
        "restore saved settings from data dictionary"
        if self.name in data:
            init = get_in_selection(data[self.name]) if self.is_input else get_out_selection(data[self.name])
            self.init_items(init)

@BLACS_tab
class FPGA_Tab(DeviceTab):
    def initialise_GUI(self):
        # reduce number of log entries in logfile (labscript-suite/logs/BLACS.log)
        # TODO: maybe there is a global setting for this but could not find?
        self.logger.setLevel(log_level)
        logger = ['BLACS.AnalysisSubmission.mainloop', 'BLACS.queue_manager.thread','BLACS','BLACS.ConnectionTable','BLACS.QueueManager','BLACS.FrontPanelSettings']
        for l in logger:
            log = logging.getLogger(l)
            log.setLevel(log_level)

        device = self.settings['connection_table'].find_by_name(self.device_name)
        self.con = device.BLACS_connection
        self.num_racks = device.properties['num_racks']
        self.bus_rate = device.properties['bus_rate']
        self.worker_args = device.properties['worker_args']
        try:
            self.is_primary = device.properties['is_primary']
            self.boards = device.properties['boards']
        except KeyError:
            # sometimes labscript goes into a strange loop and gives KeyError here although key should exist in hdf5:
            # runmanager says that cannot submit job since connection table is not a subset of experiment and thus does not update the hdf5.
            # but BLACS complains about KeyError in hdf5 file - which runmanager does not update.
            # seems that hdf5 is somtimes broken or corrupted? maybe just deleting the hdf5 might help?
            # it happended the last time when I added Moglabs QRF device which gave an error during compilation of connection table.
            # so I removed it from connection table and BLACS compiled it ok but when tried to create new hdf5 with runmanager had then this strange error.
            # I try to break the loop here such that BLACS starts without errors and runmanager can update the hdf5 file.
            save_print("strange error occurred (again). try submitting hdf5 with runmanager and/or recompile connection table.")
            self.is_primary = True
            self.boards = []
        save_print(device.properties)

        save_print("'%s': %i racks, %.3fMHz bus rate" % (self.device_name, self.num_racks, self.bus_rate / 1e6))
        if self.is_primary:
            save_print("'%s' primary board with %i secondary boards connected:" % (self.device_name, len(self.boards)))
            for sec in self.boards:
                save_print("'%s' (secondary)" % sec)
        else:
            if len(self.boards) != 1: raise LabscriptError("secondary board '%s' must have one entry in boards, not %i!" % (self.device_name, len(self.boards)))
            save_print('secondary board')
        save_print("'%s' init devices" % (self.device_name))

        # get all channels of board
        # note: connections = pseudo clock -> clockline -> intermediate device -> channel
        ao_list = {}
        do_list = {}
        for pseudoclock in device.child_list.values():
            if pseudoclock.device_class=="FPGA_PseudoClock":
                for clockline in pseudoclock.child_list.values():
                    if clockline.device_class == 'ClockLine':
                        for IM_name, IM in clockline.child_list.items():
                            if IM.device_class == 'AnalogChannels':
                                ao_list.update(get_channels(IM, True))
                            elif IM.device_class == 'DigitalChannels':
                                do_list.update(get_channels(IM, False))
                            elif IM.device_class == 'MOGLabs_XRF021':
                                save_print("'%s' MOGlabs DDS (ignore)" % IM_name)
                            else: # DDS not implemented yet
                                save_print("'%s' unknown device (ignore)" % IM_name)

        # get ananlog and digital output properties.
        # key = channel name as given to AnaolgChannel, DigitalChannel
        # all_childs is used by get_child_from_connection_table to find child connection object for channel name
        # all_IDs is used to get ID from channel name for sorting function
        ao_prop = {}
        self.all_childs = {}
        all_IDs = {}
        for name, ll in ao_list.items():
            [ID, props, child, key, unit_conversion_class] = ll
            ao_prop[key] = props
            self.all_childs[key] = child
            all_IDs[key] = ID
        #get digital output properties (which are empty at the moment)
        do_prop = {}
        for name, ll in do_list.items():
            [ID, props, child, key, unit_conversion_class] = ll
            do_prop[key] = props
            self.all_childs[key] = child
            all_IDs[key] = ID

        # Create the output objects
        save_print('create %i analog  outputs' % (len(ao_list)))
        #save_print(ao_prop)
        save_print('create %i digital outputs' % (len(do_list)))
        #save_print(do_prop)

        self.create_analog_outputs(ao_prop)
        self.create_digital_outputs(do_prop)

        #returns integer ID = unique identifier of channel (type|rack|address|channel)
        def sort(channel):
            return all_IDs[channel]

        # create widgets and place on GUI
        dds_widget, ao_widgets, do_widgets = self.auto_create_widgets()
        for name, prop in ao_widgets.items():
            # if there is a unit conversion class select unit, decimals* and step size*. Volts can be still selected manually.
            # TODO: (*) these settings are not permanent: changed when user selects Volts and then goes back to 'unit'.
            child = self.all_childs[name]
            if child.unit_conversion_class is not None:
                # select unit
                try:
                    unit = child.unit_conversion_params['unit']
                    # replace % symbol since in unit conversion class have to define %_to_base and %_from_base functions which would be invalid names
                    # TODO: how to display still '%' instead?
                    if unit == '%': unit = 'percent'
                    prop.set_selected_unit(unit)
                except KeyError:
                    pass
                # save_print("analog out '%s' selected unit '%s'" % (name, prop.selected_unit))
                # select number of decimals.
                try:
                    decimals = child.unit_conversion_params['decimals']
                    prop.set_num_decimals(decimals)
                except KeyError:
                    pass
                # set step size.
                try:
                    step = child.unit_conversion_params['step']
                    prop.set_step_size(step)
                except KeyError:
                    pass
                # the limits we have already set via voltage limits. this is permanent.
                #prop.set_limits(lower, upper)

        self.auto_place_widgets((AO_NAME, ao_widgets, sort), (DO_NAME, do_widgets, sort))

        # change ananlog output list to contain only IDs and last value
        # key = channel name as given to AnaolgChannel, DigitalChannel
        ao_list2 = {}
        for name, ll in ao_list.items():
            [ID, props, child, key, unit_conversion_class] = ll
            ao_list2[key] = [ID, 0]
        # change digital output list to contain only IDs and last value
        do_list2 = {}
        for name, ll in do_list.items():
            [ID, props, child, key, unit_conversion_class] = ll
            do_list2[key] = [ID, 0]

        # create the worker process
        # each board gets his own name, so we can refer to it
        self.primary_worker = self.device_name + ADD_WORKER
        self.secondary_worker = self.device_name + ADD_WORKER
        pm = self.create_worker(self.primary_worker, FPGA_Worker, {
            'con'           : self.con,         # string 'IP:port'
            'do_list'       : do_list2,         # list of digital outputs
            'ao_list'       : ao_list2,         # list of analog outputs
            'num_racks'     : self.num_racks,   # number of racks
            'bus_rate'      : self.bus_rate,    # integer rate in Hz
            'is_primary'    : self.is_primary,  # bool primary = True, secondary = False
            'boards'        : self.boards,      # for primary: names of secondary boards, for secondary: name of primary board
            'worker_args'   : self.worker_args, # additional worker arguments
        })

        # Set the capabilities of this device
        # TODO: should check what these make. maybe is useful for something?
        self.supports_remote_value_check(False)
        self.supports_smart_programming(False)

        # add 'FPGA board' settings at bottom
        layout = self.get_tab_layout()
        widget = QWidget()
        toolpalettegroup = ToolPaletteGroup(widget)
        toolpalette = toolpalettegroup.append_new_palette(FPGA_NAME)
        layout.insertWidget(1,widget)

        # customize digital and analog outputs GUI appearance
        # + close all widget group buttons
        # + change color of digital outputs since is hardly readable
        index = layout.count()
        for i in range(index):
            widget = layout.itemAt(i).widget()
            if widget is not None:
                # find ToolPaletteGroup with is the container class which allows to hide/unhide all outputs
                children = widget.findChildren(ToolPaletteGroup)
                for child in children:
                    #if isinstance(child,ToolPaletteGroup):
                    if AO_NAME in child._widget_groups:
                        child.hide_palette(AO_NAME)
                    if DO_NAME in child._widget_groups:
                        child.hide_palette(DO_NAME)
                    if FPGA_NAME in child._widget_groups:
                        child.hide_palette(FPGA_NAME)
                # change digital output text color since text is hardly readable
                DO = widget.findChildren(DigitalOutput)
                for do in DO:
                    #save_print('set color of digital output', do.text())
                    do.setToolTip(do.text())
                    #do.setText('changed!\n')
                    do.setStyleSheet('QPushButton {color: white; font-size: 14pt;}')
                    #do.setStyleSheet('QPushButton {color: white; background-color: darkgreen; font-size: 14pt;} QPushButton::pressed {color: black; background-color: lightgreen; font-size: 14pt;}')
                    #do.setStyleSheet('QPushButton {color: white; font-size: 14pt;} QPushButton::pressed {color: black; font-size: 14pt;}')

        # optional worker arguments
        #save_print("'%s' worker args:" % self.device_name, self.worker_args)

        # create buttons and clock check boxes
        self.buttons = FPGA_buttons(parent=self, name=self.device_name, worker_args=self.worker_args)
        toolpalette.insertWidget(0, self.buttons)

        # create list of input selectors
        self.inputs = FPGA_IO(
                    name        = self.device_name+'_in',
                    parent      = self,
                    is_input    = True,
                    dests       = in_dests.keys(),
                    sources     = in_sources.keys(),
                    levels      = in_levels.keys(),
                    worker_args = self.worker_args
        )
        toolpalette.insertWidget(1, self.inputs)

        # create list of output selectors
        self.outputs = FPGA_IO(
                    name        = self.device_name+'_out',
                    parent      = self,
                    is_input    = False,
                    dests       = out_dests.keys(),
                    sources     = out_sources.keys(),
                    levels      = out_levels.keys(),
                    worker_args = self.worker_args,
                    showHeader  = False
        )
        toolpalette.insertWidget(2, self.outputs)

        # warning dialog. count '%i' is maintained by warning_user_dialog
        self.warning_text = "'%s': external clock lost on last %%i runs!" % self.device_name
        self.warning = warn_user_dialog(parent=self._ui, text=self.warning_text, title="'%s' warning!" % self.device_name)
        #self.warning.update("'%s' test" % self.device_name)

    def get_child_from_connection_table(self, parent_device_name, port):
        # this is called from create_analog_outputs or create_digital_outputs to get the name of the channel.
        # if not defined, the default implementation assumes that self (FPGA board) is the parent device of all channels.
        # but in our case the parents of the channels are the intermediate devices.
        # port = channel name displayed by blacs (hardware name)
        # we return the connection object (device) of the corresponding channel. blacs is displaying device.name.
        return self.all_childs[port]

    @define_state(MODE_BUFFERED, True)
    def abort(self, state):
        result = yield (self.queue_work(self.primary_worker, 'abort_buffered'))
        save_print('FPGA: abort', result)

    @define_state(MODE_MANUAL,True)
    def get_state(self, state):
        result = yield(self.queue_work(self.primary_worker, 'FPGA_get_board_state'))
        save_print('FPGA: get_state', result)

    @define_state(MODE_MANUAL, True)
    def conn(self, state):
        result = yield(self.queue_work(self.primary_worker, 'FPGA_disconnect'))
        save_print('FPGA: dicsonnect', result)

    @define_state(MODE_BUFFERED, True)
    def start_run(self, notify_queue):
        # TODO: start all boards here. worker can use events to synchronize among them.
        success = yield (self.queue_work(self.primary_worker, 'start_run'))
        if success:
            # update status during run every UPDATE_TIME_MS
            self.statemachine_timeout_add(UPDATE_TIME_MS, self.status_monitor, notify_queue)
            # check of end state in MODE_MANUAL after run finished
            # this way we can update dialog box in GUI after transition_to_manual
            # from worker we have no access to GUI and most likely cannot call back to FPGA_Tab?
            self.event_queue.put(MODE_MANUAL, True, False, [self.status_end, ((),{})], priority=0)
        else:
            raise RuntimeError('Failed to start run')
    
    @define_state(MODE_BUFFERED, True)
    def status_monitor(self, notify_queue):
        result = yield(self.queue_work(self.primary_worker, 'status_monitor'))
        if result[0]: # end or error
            # indicate that experiment cycle is finished.
            # this causes transition_to_manual called on all workers.
            notify_queue.put('done')
            # do not call status_monitor anymore
            self.statemachine_timeout_remove(self.status_monitor)

    @define_state(MODE_MANUAL, True)
    def status_end(self,test=None):
        # check final state after experimental cycle is finished.
        # this is called as soon as transition_to_manual is finished and before the next transition_to_buffered.
        # at this time all boards are stopped and we can get final status of all boards.
        # TODO: get status of all boards, not only warnings and display in dialog box on any error/warning
        result = yield(self.queue_work(self.primary_worker, 'status_monitor'))
        warnings = result[1]
        if len(warnings) > 0:
            save_print('FPGA_tab: %i warnings' % (len(warnings)))
            if len(warnings) == 1:
                text = "external clock lost %i times of "
            else:
                text = "external clock lost %%i times for %i boards: " % (len(warnings))
            for i, sec in enumerate(warnings):
                if i == 0:
                    text += sec
                else:
                    text += ', ' + sec
            self.warning.update(text=text)

    def get_save_data(self):
        "return all GUI settings to be retrieved after BLACS restarts"
        data = {}
        self.inputs.get_save_data(data)
        self.outputs.get_save_data(data)
        self.buttons.get_save_data(data)
        #save_print("'%s' get_save_data:" %  self.device_name, data)
        return data

    def restore_save_data(self, data):
        """
        get GUI settings. settings in worker_args have precedence.
        unfortunately is called AFTER initialize_GUI, so we have to init stuff several times.
        data might be empty.
        """
        #save_print("'%s' restore_save_data:" % self.device_name, data)
        self.inputs.restore_save_data(data)
        self.outputs.restore_save_data(data)
        self.buttons.restore_save_data(data)

#BLACS worker thread
class FPGA_Worker(Worker):
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

        # test libusb
        #FindUSBDevice()

        # last board status. None on error
        self.board_status = None
        self.board_time = 0
        self.board_samples = 0
        self.abort = False

        # default configuration
        self.config_manual = CONFIG_RUN_96 if (self.num_racks == 2) else CONFIG_RUN_64
        self.error_mask = 0xffff_ffff
        self.start_trg = False
        self.ext_clock = False
        self.ignore_clock_loss = True
        self.sync_wait  = SYNC_WAIT_AUTO
        self.sync_phase = SYNC_PHASE_AUTO
        self.num_cycles = CONFIG_CYCLES
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
        self.parse_worker_args(self.worker_args, update=False)

        if False: # save_print selected options
            self.onChangeInputs(self.ctrl_in)
            self.onChangeOutputs(self.ctrl_out)
            self.onChangeExtClock(self.ext_clock)
            self.onChangeIgnoreClockLoss(self.ignore_clock_loss)

        # connect - open - reset - configure board
        # on error: we disconnect and set self.sock=None
        #           in program_manual and transition_to_buffered we retry
        self.sock = init_connection("'%s' init"%self.device_name, self.con, self.config_manual)
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

    def program_manual(self, front_panel_values):
        if self.sock == None: # try to reconnect to device
            self.sock = init_connection("'%s' prg. manual"%self.device_name, self.con, self.config_manual)

        if False and (not self.first_time):
            # test: send event between boards BEFORE the other side waits for it
            wait = not self.is_primary
            for loop in range(10):
                if wait:
                    sleep(5.0) # sleep here to allow posting board to send event before we wait
                    for i, evt in enumerate(self.events):
                        ticks = get_ticks()
                        try:
                            result = evt.wait(self.count, timeout=5.0)
                            t_end = get_ticks()
                            save_print("%i '%s' wait '%s': %s, posted %.3fms waited %.3fms (%i)" % (loop, self.device_name, self.boards[i], result[1], (t_end - result[0])*1e3, (t_end - ticks)*1e3, self.count))
                        except zTimeoutError:
                            save_print("%i '%s' wait '%s': timeout %.3fs (%i)" % (loop, self.device_name, self.boards[i], get_ticks()-ticks, self.count))
                            return None
                else: # post as fast as possible
                    #sleep(1.0)
                    for i,evt in enumerate(self.events):
                        evt.post(self.count, data=(get_ticks(), 't_%i'%(self.count/2)))
                    save_print("%i: '%s' posted %i events" % (loop, self.device_name, len(self.events)))
                # change role
                wait = not wait
                self.count += 1
            save_print("'%s' %i loops done!" % (self.device_name, loop+1))
            #self.first_time = False

        if self.sock is not None: # device (re-)connected
        #if True:
            save_print("'%s' prg. manual" % (self.device_name))
            # 1. we first loop through all channels and generate a list of changed digital channels.
            # 2. for changed analog channels we can already generate samples since each channel has its unique address.
            data = []
            time = START_TIME
            sample = [time] + [BIT_NOP_SH]*self.num_racks
            do_IDs = []
            #save_print(self.do_list)
            for key, value in front_panel_values.items():
                try:
                    [ID, last] = self.do_list[key] # DigitalChannels
                    if self.first_time or (value != last):
                        if value != last: save_print("'%s' changed from %i to %i" % (key, last, value))
                        do_IDs = do_IDs + [ID] # save changed ID
                        self.do_list[key] = [ID, value] # save new state
                except KeyError:
                    try:
                        [ID, last] = self.ao_list[key] # AnalogChannels
                        if self.first_time or (value != last):
                            if value != last: save_print("'%s' changed from %f to %f" % (key, last, value))
                            rack = get_rack(ID)
                            address = get_address(ID)
                            sample[rack+1] = (address<<ADDR_SHIFT)|((int((value*0x7fff) + 0.5)//10) & 0xffff) # TODO: units conversion?
                            data.append(sample)
                            time += TIME_STEP
                            sample = [time] + [BIT_NOP_SH]*self.num_racks
                            self.ao_list[key] = [ID, value]
                    except KeyError: # unknown device?
                        save_print("unknown device '%s', value %f" % (key, value))
            # 3. for changed digital channels we have to collect all channel bits (changed or not) with the same rack & address
            if len(do_IDs) > 0:
                do_IDs = np.unique(do_IDs) # numpy array of unique changed IDs
                done = [False]*len(do_IDs) # True for IDs which are already taken saved into a sample
                #save_print(do_IDs)
                for i,ID in enumerate(do_IDs):
                    if not done[i]:
                        rack = get_rack(ID)
                        address = get_address(ID)
                        sample[rack+1] = (address<<ADDR_SHIFT)
                        for key in self.do_list: # get all bits from all channels with same rack & address
                            _ID, last = self.do_list[key]
                            if (get_rack(_ID) == rack) and (get_address(_ID) == address): # same rack and address, i.e. same DigitalChannels parent
                                channel = get_channel(_ID)
                                sample[rack+1] = sample[rack+1] | ((last & 1) << channel) # add bit
                                # mark _ID as already added to sample. this includes _ID == ID case.
                                # IndexError if _ID is not in list of changed channels
                                try:
                                    done[np.arange(len(do_IDs))[do_IDs == _ID][0]] = True
                                except IndexError:
                                    pass
                                #save_print('ID 0x%x/0x%x done (value %d)' % (_ID, ID, last))
                        data.append(sample) # save sample
                        time += TIME_STEP
                        sample = [time] + [BIT_NOP_SH]*self.num_racks
            # next time update only changes
            self.first_time = False
            # write samples to device
            if len(data) > 0:
                if send_data(self.sock, np.array(data,dtype=np.uint32), self.bus_rate, self.config_manual) == True:
                    # start output
                    result = send_recv_data(self.sock, to_client_data32(SERVER_START, 1), SOCK_TIMEOUT, output='START')
                    if result == SERVER_ACK:
                        # wait for completion (should be immediate)
                        result = False
                        while result == False:
                            sleep(0.1)
                            result = self.status_monitor()[0]
                        # stop output
                        send_recv_data(self.sock, SERVER_STOP, SOCK_TIMEOUT, output='STOP')
                        if result == SERVER_ACK:
                            return front_panel_values # ok

        return False # TODO: how to indicate error?

    def transition_to_buffered(self, device_name, hdf5file, initial_values, fresh):
        """
        prepare experimental sequence.
        return None on error which calls abort_transition_to_buffered
        return list of final values (still needs to be done. not sure what to put there?)
        """
        if self.sock == None: # try to reconnect to device
            self.sock = init_connection("'%s' to buffered"%self.device_name, self.con, self.config_manual)
        if self.sock is None:
            return None

        #if False and self.is_primary: # test uplload table
            MOG_test()

        self.abort = False
        with h5py.File(hdf5file,'r') as hdf5_file:
            group = hdf5_file['devices/%s'%(device_name)]
            data = group['%s_matrix'%device_name][:] # TODO: is the copy here needed?
            print(data)
            print(data.shape)

            # use updated settings given in worker_args_ex
            if decode_string_with_eval:
                worker_args_ex = eval(group['%s_worker_args_ex'%device_name][0])
            else:
                worker_args_ex = from_string(group['%s_worker_args_ex' % device_name][0])
            print('updating worker_args',worker_args_ex)
            self.parse_worker_args(worker_args_ex, update=False)

            # save number of samples
            # TODO: if this is 0 for one board interprocess communication will timeout
            self.samples = len(data)

            if len(data) == 0:
                save_print("'%s' no data!" % (self.device_name))
            else:

                # TODO: if the data has not changed it would not need to be uploaded again?
                #       the simplest would be to save a counter into hdf5 which is incremented on each new generation.
                #       additionally, in generate code one could check if data has changed to last time.

                # save last time of data
                self.last_time = data[-1][0]

                # note: 'start_run' is called only for primary board! so we have to start secondary board already here.
                #       in order to not loose the external clock of secondary boards we have to reset primary board also here
                #       and secondary boards can start only after primary board has been reset.

                if not self.is_primary:
                    # secondary board: wait for start event, i.e. until primary board is reset
                    try:
                        t_start = get_ticks()
                        result = self.events[0].wait(self.count, timeout=EVT_TIMEOUT)
                        t_end = get_ticks()
                        save_print("'%s' wait start: %s, posted %.3fms, waited %.3fms (%i)" % (self.device_name, str(result[1]), (t_end - result[0])*1e3, (t_end - t_start)*1e3, self.count))
                        if result[1] == False: return None
                    except zTimeoutError:
                        save_print("'%s' wait start: timeout %.3fs (%i)" % (self.device_name, get_ticks()-t_start, self.count))
                        return None

                # all boards: reset, configure and send data
                # returns True on success, False on error.
                save_print('FPGA    control 0x%x' % (self.config))
                save_print('trigger control 0x%x' % (self.ctrl_in))
                save_print('output  control 0x%x' % (self.ctrl_out))
                result = send_data(self.sock, data, self.bus_rate, config=self.config, ctrl_trg=self.ctrl_in, ctrl_out=self.ctrl_out, reset=True,
                                   sync_wait=self.sync_wait, sync_phase=self.sync_phase, cycles=self.num_cycles)
                save_print('result =',result)

                if self.is_primary:
                    #save_print('events =',self.events)
                    if len(self.events) > 0:
                        # primary board: send start event to secondary boards with time and result
                        for evt in self.events:
                            evt.post(self.count, data=(get_ticks(),result))
                        save_print("'%s' post start, result=%s (%i)" % (self.device_name, str(result), self.count))

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
                else:
                    # secondary board: start and wait for external trigger
                    result = self.start_run()

                    # post ok for start of primary board
                    self.events[0].post(self.count, data=(get_ticks(), result))
                    save_print("'%s' post start, result=%s (%i)" % (self.device_name, str(result), self.count))

                    if result != True: return None

                self.count += 2

        #TODO: return final values
        return {}

    def abort_transition_to_buffered(self):
        return self.abort_buffered()
    
    def abort_buffered(self):
        self.abort = True # indicates to status_monitor to return True to stop
        if self.sock == None:
            save_print("worker: '%s' not connected at %s" % (self.device_name, self.con))
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
        if self.sock == None: # this should never happen
            save_print("'%s' not connected at %s" % (self.device_name, self.con))
            return False

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
        result = send_recv_data(self.sock, SERVER_STOP, SOCK_TIMEOUT, output='STOP')
        if result is None:
            # for secondary boards save result in all_ok
            # for primary board result is not changed.
            if self.is_primary: result = False
            else: all_ok = False
        else:
            # get expected board samples and board time
            exp_samples, exp_time = get_board_samples(self.samples, self.last_time)

            # get board status.
            self.status_monitor()
            aborted = '(aborted)' if self.abort else ''
            if (self.board_status == None):
                save_print("'%s' stop: could not get board status! %s\n" % (self.device_name, aborted))
                all_ok = False
            else:
                if (not (self.board_status & STATUS_END)) or (self.board_status & STATUS_ERROR & self.error_mask):
                    save_print("'%s' stop: board is not in end state! status=0x%x %s\n" % (self.device_name, self.board_status, aborted))
                    all_ok = False
                elif (self.board_samples != exp_samples): # note: samples are appended with NOP to have multiple of 4
                    save_print("'%s' stop: unexpected board samples %i != %i! %s\n" % (self.device_name, self.board_samples, exp_samples, aborted))
                    all_ok = False
                elif (self.board_time != exp_time):
                    save_print("'%s' stop: unexpected board time %i != %i! %s\n" % (self.device_name, self.board_time, exp_time, aborted))
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

        # return result. True = ok, False = error
        return result

    def start_run(self):
        if self.sock == None: # should not happen
            save_print("'%s' not connected at %s" % (self.device_name, self.con))
        else:
            self.warn = False
            result = send_recv_data(self.sock, to_client_data32(SERVER_START, self.num_cycles), SOCK_TIMEOUT, output='START')
            if result is None:
                save_print("'%s' start %i cycles: error starting! (timeout, %i)" % (self.device_name, self.num_cycles, self.count))
            elif result == SERVER_ACK:
                if self.start_trg: save_print("'%s' start %i cycles: running ... (%i)" % (self.device_name, self.num_cycles, self.count))
                else:              save_print("'%s' start %i cycles: waiting for trigger ... (%i)" % (self.device_name, self.num_cycles, self.count))
                return True
            else:
                save_print("'%s' start %i cycles: error starting! (%i)" % (self.device_name, self.num_cycles, self.count))
        return False # error

    def status_monitor(self):
        "this is called from FPGA_Tab::status_monitor during run to update status of primary board only"
        if self.sock == None: # should never happen
            save_print("'%s' not connected at %s" % (self.device_name, self.con))
            self.board_status = None
        else:
            result = send_recv_data(self.sock, SERVER_STATUS_IRQ, SOCK_TIMEOUT, output=None, recv_bytes=get_bytes(SERVER_STATUS_IRQ_RSP))
            if result is None:
                self.board_status = None
            else:
                [cmd, self.board_status, self.board_time, self.board_samples] = from_client_status(result)
                if (cmd != SERVER_STATUS_RSP) and (cmd != SERVER_STATUS_IRQ_RSP):
                    self.board_status = None
                else:
                    if self.board_status & STATUS_ERROR: # warning or error state
                        if self.ignore_clock_loss and  ((self.board_status & (STATUS_RUN|STATUS_END|STATUS_ERROR)) == (STATUS_RUN|STATUS_ERR_LOCK)):
                            # clock loss but running
                            save_print('t %8i, # %8i, status 0x%08x clock loss (running)!' % (self.board_time, self.board_samples, self.board_status))
                            self.warn = True
                            if self.abort: return [True, self.get_warnings()]
                            else:          return [False]
                        elif self.ignore_clock_loss and ((self.board_status & (STATUS_RUN|STATUS_END|STATUS_ERROR)) == (STATUS_END|STATUS_ERR_LOCK)):
                            # clock loss and in end state
                            save_print('t %8i, # %8i, status 0x%08x clock loss (end)!' % (self.board_time, self.board_samples, self.board_status))
                            self.warn = True
                            return [True, self.get_warnings()]
                        else: # error state
                            save_print('t %8i, # %8i, status 0x%08x error!' % (
                            self.board_time, self.board_samples, self.board_status))
                            return [True, self.get_warnings()]
                    elif self.board_status & STATUS_RUN:
                        if self.board_status & STATUS_WAIT: # restart state
                            save_print('t %8i, # %8i, status 0x%08x restart' % (self.board_time, self.board_samples, self.board_status))
                        else: # running state
                            save_print('t %8i, # %8i, status 0x%08x running' % (self.board_time, self.board_samples, self.board_status))
                        if self.abort: return [True, self.get_warnings()]
                        else:          return [False]
                    elif self.board_status & STATUS_END: # end state
                        save_print('t %8i, # %8i, status 0x%08x end' % (self.board_time, self.board_samples, self.board_status))
                        return [True, self.get_warnings()]
                    elif self.board_status & STATUS_WAIT: # wait state = start trigger
                        if (self.board_time == 0) and is_in_start(self.ctrl_in): # waiting for external trigger
                            save_print('t %8i, # %8i, status 0x%08x waiting start trig.' % (self.board_time, self.board_samples, self.board_status))
                        elif (self.board_time > 0) and is_in_stop(self.ctrl_in): # stop state
                            if is_trg_restart(self.ctrl_in):
                                save_print('t %8i, # %8i, status 0x%08x waiting restart trig.' % (self.board_time, self.board_samples, self.board_status))
                            else:
                                save_print('t %8i, # %8i, status 0x%08x stop trig. (abort)' % (self.board_time, self.board_samples, self.board_status))
                                self.abort = True # no restart trigger is active. TODO: disable 'Repeat'?
                        else:
                            save_print('t %8i, # %8i, status 0x%08x unexpected! (abort)\n' % (self.board_time, self.board_samples, self.board_status))
                            self.abort = True
                        if self.abort: return [True, self.get_warnings()]
                        else:          return [False]
                    else: # unexpected state
                        save_print('t %8i, # %8i, status 0x%08x unexpected!\n' % (self.board_time, self.board_samples, self.board_status))
                        return [True, self.get_warnings()]
        # TODO: how to indicate error? None seems to be the same as False?
        #       return True = finished, False = running
        #       at the moment we return True on error.
        #       this will call transition_to_manual where we check board status and return error.
        return [True, self.get_warnings()]

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
        save_print('worker shutdown')

    def FPGA_get_board_state(self):
        # get board state
        #save_print('worker: get state')
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
            
    def parse_worker_args(self, worker_args, update):
        # worker_args = dictionary with worker arguments passed to board in experimental sequence to overwrite default or connection table arguments.
        # update = if True actual worker args are udpated, otherwise not
        # ATTENTION: these parameters overwrite default or connection table settings!
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
        # - num_cuyles:
        #   number of cycles. 0=infinite, 1=default.
        
        # we first update all parameters in worker_args
        if worker_args is not None:
            if STR_CONFIG in worker_args and worker_args[STR_CONFIG] is not None:
                self.config = worker_args[STR_CONFIG]
            if STR_CONFIG_MANUAL in worker_args and worker_args[STR_CONFIG_MANUAL] is not None:
                self.config_manual = worker_args[STR_CONFIG_MANUAL]
            if STR_INPUTS in worker_args and worker_args[STR_INPUTS] is not None:
                self.ctrl_in = get_ctrl_in(worker_args[STR_INPUTS])
                start_trg = is_in_start(self.ctrl_in)
            if STR_OUTPUTS in worker_args and worker_args[STR_OUTPUTS] is not None:
                self.ctrl_out = get_ctrl_out(worker_args[STR_OUTPUTS])
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
                
        if update:
            # replace new worker_args ('worker_args_ex' set in experimental sequence) in self.worker_args (set in connection table).
            # this overwrites the settings in connection table.
            for key, value in worker_args.items():
                if key in self.worker_args:
                    if isinstance(value, dict):  # value is a dictionary: insert/replace all extra items
                        act = self.worker_args[key]
                        for key2, value2 in value.items():
                            act[key2] = value2
                        value = act
                    save_print("%s exchange worker arg '%s' " % (self.device_name, key), self.worker_args[key], "with", value)
                else:
                    save_print("%s new worker arg '%s' " % (self.device_name, key), value)
                self.worker_args[key] = value


# testing functions

def test_word():
    "test word_to_value and value_to_word. see Texas Instruments, DAC712 datasheet, July 2009, Table 1, page 13"
    LSB = AO_RESOLUTION # 305uV
    tolerance = 1e-12   # numerical tolerance for word_to_V conversion (we would need only LSB/2)
    tests = {0x7fff:10-LSB, 0x4000:5.0, 1:LSB, 0:0, 0xffff:-LSB, 0xc000:-5.0, 0x8000:-10.0}
    words = np.array(list(tests.keys()))
    volts = np.array(list(tests.values()))

    # convert directly volts to words. this is what V_to_word does.
    num = 2**16
    ymax = 10.0-(20/num)
    ymin = -10.0
    calc_f  = (volts-ymin)*(num-1)/(ymax-ymin)
    calc_i  = np.array(np.round(calc_f)-0x8000,dtype=np.uint16)
    #calc_i = np.array(np.round((volts-AO_MIN)*(2**AO_BITS-1)/(AO_MAX-AO_MIN))-(2**(AO_BITS-1)),dtype=np.uint16)
    error   = calc_i-words
    count = np.count_nonzero(error)
    if count > 0:
        save_print('direct conversion test %i errors! [volt, word, expected, error]' % (count))
        save_print(np.transpose([volts, calc_f, calc_i, words, error]))
        #exit()
    else:
        save_print('direct conversion test ok. (largest error %e)' % (np.max(np.abs(error))))

    # V_to_word vector test
    calc = V_to_word(volts)
    error = calc - words
    count = np.count_nonzero(error)
    if count > 0:
        save_print('V_to_word %i errors! [volt, word, expected, error]' % (count))
        save_print(np.transpose([volts,calc,words,error]))
        exit()
    else:
        save_print('V_to_word vector test ok. (largest error %e)' % (np.max(np.abs(error))))

    # V_to_word scalar test
    for word,volt in tests.items():
        calc = V_to_word(volt)
        error = calc - word
        if error != 0:
            save_print('V_to_word scalar error %e V -> %i, expected %i, error %i!' % (volt, calc, word, error))
            exit()
    save_print('V_to_word scalar test ok. (largest error %e)' % (np.max(np.abs(error))))

    # word_to_V vector test
    calc = word_to_V(words)
    error = calc - volts
    count = np.count_nonzero(np.abs(error) >= tolerance)
    if count > 0:
        save_print('word_to_V vector %i errors! [word, volt, expected, error]' % (count))
        save_print(np.transpose([words,calc,volts,error]))
        exit()
    else:
        save_print('word_to_V vector test ok. (largest error %e)' % (np.max(np.abs(error))))

    # word_to_V scalar test
    for word,volt in tests.items():
        calc = word_to_V(word)
        error = calc - volt
        if np.abs(error) >= tolerance:
            save_print('word_to_V scalar error %i -> %e, expected %e, error %e!' % (word, calc, volt, error))
            exit()
    save_print('word_to_V scalar test ok. (largest error %e)' % (np.max(np.abs(error))))

    # double conversion test. here we test all possible numbers.
    words = np.arange(2**16)
    volts = word_to_V(words)
    w2 = V_to_word(volts)
    v2 = word_to_V(w2)
    error = w2 - words
    count = np.count_nonzero(error)
    if count > 0:
        save_print('V_to_word(word_to_V) %i errors! largest error %e' % (count, np.max(np.abs(error))))
        exit()
    else:
        save_print('V_to_word(word_to_V) test ok. (largest error %e)' % (np.max(np.abs(error))))
    error = v2 - volts
    count = np.count_nonzero(np.abs(error) >= tolerance)
    if count > 0:
        save_print('word_to_V(V_to_word) %i errors! largest error %e' % (count, np.max(np.abs(error))))
        exit()
    else:
        save_print('word_to_V(V_to_word) test ok. (largest error %e)' % (np.max(np.abs(error))))

if __name__ == '__main__':
    # test word_to_V and V_to_word
    test_word()

    # TODO: add unit conversion test
