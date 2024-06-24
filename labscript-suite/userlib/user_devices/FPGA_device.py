#####################################################################
# FPGA-SoC device by Andreas Trenkwalder
# works as PseudoClockDevice
# created 6/4/2021
# last change 24/6/2024 by Andi
#####################################################################

from __future__ import generator_stop
import labscript.labscript
from labscript import PseudoclockDevice, Pseudoclock, ClockLine, IntermediateDevice, DDS, DigitalOut, AnalogOut, set_passed_properties, LabscriptError, config, Output, DDSQuantity
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
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

from blacs.tab_base_classes import Worker, define_state, MODE_MANUAL, MODE_TRANSITION_TO_BUFFERED, MODE_TRANSITION_TO_MANUAL, MODE_BUFFERED
from blacs.device_base_class import DeviceTab

# note: do not import MOGLabs_QRF here!
#       it seems Python cannot handle circular references!
#       the error occurred during compilation of connection table with BLACS.
#from user_devices.MOGLabs_QRF import MOGLabs_QRF

# reduce number of log entries in logfile (labscript-suite/logs/BLACS.log)
log_level = [logging.CRITICAL, logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG, logging.NOTSET][2]

# set this to True when you have a problem to start BLACS. resets all stored values to default.
# can happen when changing values saved to file.
reset_all = False

# use latest stable version from 24/1/2023 (version used in Yb-Trieste and Firenze Sr-Tweezers)
old_version = True

# every time after compiling connection table I get strange BrokenPipeError for any print command within FPGA_Tab!?
# sometimes crashes so badly that BLACS cannot be closed anymore and have to manually kill it! this is super annoying.
# implement a save_print command and use everywhere!
def save_print(*args):
    try:
        print(*args)
    except BrokenPipeError:
        pass

#default connection
PRIMARY_IP   = '192.168.1.130'
SECONDARY_IP = '192.168.1.131'
DEFAULT_PORT = '49701'
SOCK_TIMEOUT = 5.0                          # timeout for send_recv_data in seconds. I see sometimes very long responds time. maybe USB-Ethernet-adapter?
SOCK_TIMEOUT_SHORT = 1.0                    # timeout for init_connection in seconds. this is shorter for fast tests withouts boards.

ADD_WORKER  = '_worker'                     # worker name = board name + ADD_WORKER
AO_NAME     = 'Analog Outputs'              # GUI button name analog outputs
DO_NAME     = 'Digital Outputs'             # GUI button name digital outputs
FPGA_NAME   = 'FPGA board'                  # GUI button name FPGA board

#global settings
MAX_FPGA_RATE   = 10e6                      # maximum bus output rate of FPGA in Hz. theoretical limit 30MHz - not tested.
MAX_RACKS       = 2                         # 2 racks can share one clockline
MAX_SHOW        = 20                        # maximum number of samples until which data is shown
ALWAYS_SHOW     = True                      # if true always shows first and last MAX_SHOW/2 data

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
MAX_BUS_RATE     = 1e6
CLOCK_RESOLUTION = get_clock_resolution(MAX_BUS_RATE)
MAX_TIME         = (2**32)-1
MAX_TIME_SECONDS = MAX_TIME*CLOCK_RESOLUTION
CLOCK_LIMIT      = get_clock_limit(MAX_BUS_RATE)
#save_print('FPGA_board: maximum bus rate %.3f MHz gives resolution %.3f ns and max time %.3f s (clock limit = bus rate + %.3f Hz)' % (MAX_BUS_RATE/1e6, CLOCK_RESOLUTION*1e9, MAX_TIME_SECONDS, CLOCK_LIMIT - MAX_BUS_RATE))

# smallest time step and start time in WORD units (ticks)
TIME_STEP       = 1                         # must be 1
START_TIME      = 0                         # note: FPGA board can start at time 0 since trigger delay is corrected.
TIME_ROUND_DECIMALS = 10                    # time is rounded internally by labscript to 10 decimals = 100ps
TIME_PRECISION  = 10.0**(-TIME_ROUND_DECIMALS) # time round precision in seconds
UPDATE_TIME_MS  = 500                       # update time of BLACS board status in ms

#bus data structure
DATA_BITS       = 16
ADDR_BITS       = 7                         # typically 7, but also 8 is possible (if your bus supports)
ADDR_SHIFT      = DATA_BITS                 # first bit of address = number of data bits
MAX_ADDRESS     = ((2**ADDR_BITS)-1)        # largest possible address
ADDR_MASK_SH    = np.array(MAX_ADDRESS<<ADDR_SHIFT,dtype=np.uint32) # address mask (7 or 8 bits)
DATA_MASK       = np.array((2**DATA_BITS)-1, dtype=np.uint32) # data field mask (16 bits)
DATA_ADDR_MASK  = DATA_MASK|ADDR_MASK_SH    # combined data field + address mask (23 or 24 bits)

# default special data bits
# TODO: defined by firmware.
BIT_NOP             = 31                        # no operation bit (at the moment cannot be changed since is hard-coded in driver!)
BIT_TRST            = 30                        # time reset bit (not implemented)
BIT_IRQ             = 29                        # data IRQ bit
BIT_STOP            = 28                        # data stop trigger bit
BIT_STRB            = DATA_BITS+ADDR_BITS       # data strobe bit (typically 23 but could be also 24)
BIT_STRB_GENERATE   = False                     # if True: generate BIT_STRB toggle bit, otherwise not
BIT_NOP_SH          = (1 << BIT_NOP)
BIT_STOP_SH         = (1 << BIT_STOP)
BIT_IRQ_SH          = (1 << BIT_IRQ)
BIT_STRB_SH         = (1 << BIT_STRB)
BIT_STRB_MASK       = ~np.array(BIT_STRB_SH, dtype=np.uint32)
SPECIAL_BITS        = BIT_NOP_SH | BIT_STOP_SH |BIT_IRQ_SH | BIT_STRB_SH

# device types (used for ID)
# TODO: add DDS
TYPE_board      = 0
TYPE_DO         = 1
TYPE_AO         = 2
TYPE_SP         = 3

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
    return np.array(np.round((np.clip(volts,AO_MIN,AO_MAX)-AO_MIN)*(2**AO_BITS-1)/(AO_MAX-AO_MIN))-(2**(AO_BITS-1)),dtype=np.uint32) & DATA_MASK

def word_to_V(word):
    "convert 16bit data word (scalar or np.array) into voltage"
    return np.where(word & 0x8000, np.array(word, dtype=float)-(2**(AO_BITS-1)), (2**(AO_BITS-1)) + np.array(word, dtype=float))*(AO_MAX-AO_MIN)/(2**AO_BITS-1) + AO_MIN

# default analog and digital output properties
# these define the capabilities of the analog outputs after unit conversion, i.e. in the base unit 'V'.
default_ao_props = {'base_unit':'V', 'min':-10.0, 'max':10.0,'step':0.1, 'decimals':4}
default_do_props = {'xcolor':'red'}

# default values are inserted automatically by labscript for times before channel is used
# these values are masked below and are not sent to boards.
# to distinguish between user inserted values and auto-inserted we keep them outside valid range.
SP_INVALID_VALUE = 0 # special output device (virtual)
#AO_INVALID_VALUE = 2*default_ao_props['min']-1.0 # TODO: with unit conversion this might be a valid user-inserted value!? I think nan is not possible here. maybe use np.nan?
AO_INVALID_VALUE = np.finfo(np.float64).min # inserted automatically by labscript
DO_INVALID_VALUE = 2 # inserted automatically by labscript

# if True then primary board returns error also when a secondary board is in error state. default = False.
stop_primary_on_secondary_error = False

# runviewer options
runviewer_show_units    = True              # if True show user units in runviewer, otherwise show output in Volts
runviewer_add_start_time= False             # if True adds time START_TIME to data if not given by user. value is last value of last instruction.
runviewer_show_all      = True              # if True show all channels even without data

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
if old_version:
    SERVER_STATUS_FULL_RSP_8  = make_cmd(0x07,266)       # response: full status  8 bytes per samples
    SERVER_STATUS_FULL_RSP_12 = make_cmd(0x07,270)       # response: full status 12 bytes per samples
else:
    SERVER_STATUS_FULL_RSP_8  = make_cmd(0x07,274)       # response: full status  8 bytes per samples
    SERVER_STATUS_FULL_RSP_12 = make_cmd(0x07,278)       # response: full status 12 bytes per samples
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

# inverse of from_client_status
def to_client_status(cmd, board_status, board_time, board_samples):
    return struct.pack('<2s3I', cmd, board_status, board_time, board_samples)

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
STR_SIMULATE            = 'simulate'
worker_args_keys = [STR_CONFIG, STR_CONFIG_MANUAL, STR_INPUTS, STR_OUTPUTS,
                    STR_EXT_CLOCK, STR_IGNORE_CLOCK_LOSS,
                    STR_SYNC_WAIT, STR_SYNC_PHASE, STR_CYCLES,
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
STATUS_SECONDARY_READY      = STATUS_READY | STATUS_AUTO_SYNC | STATUS_EXT_USED | STATUS_EXT_LOCKED

# input control register
CTRL_IN_SRC_BITS            = 3
CTRL_IN_LEVEL_BITS          = 2
CTRL_IN_DST_BITS            = (CTRL_IN_SRC_BITS + CTRL_IN_LEVEL_BITS)
CTRL_IN_SRC_MASK            = (1<<CTRL_IN_SRC_BITS)-1;
CTRL_IN_LEVEL_MASK          = (1<<CTRL_IN_LEVEL_BITS)-1;
CTRL_IN_DST_MASK            = (1<<CTRL_IN_DST_BITS)-1;

# input destination offsets
CTRL_IN_DST_START           = 0*CTRL_IN_DST_BITS   # start trigger
CTRL_IN_DST_STOP            = 1*CTRL_IN_DST_BITS   # stop trigger
CTRL_IN_DST_RESTART         = 2*CTRL_IN_DST_BITS   # restart trigger
# TODO: firmware uses parameters given at compile time.
#       these tell the software which bits to generate but no cross-checking is done.
#       either read from firmare directly or allow to modify firmware values (NOP is difficult).
#       BIT_IRQ is also missing here but no space left.
CTRL_IN_DST_DATA_NOP        = 3*CTRL_IN_DST_BITS   # data NOP bit (must be 31)
CTRL_IN_DST_DATA_STRB       = 4*CTRL_IN_DST_BITS   # data strobe bit (default 23)
CTRL_IN_DST_DATA_STOP       = 5*CTRL_IN_DST_BITS   # data STOP bit (default 28)

# input sources
CTRL_IN_SRC_NONE            = 0                     # no trigger input
CTRL_IN_SRC_IN0             = 1                     # ext_in[0]
CTRL_IN_SRC_IN1             = 2                     # ext_in[1]
CTRL_IN_SRC_IN2             = 3                     # ext_in[2]
CTRL_IN_SRC_DATA_20         = 5                     # data bits 20-23
CTRL_IN_SRC_DATA_24         = 6                     # data bits 24-27
CTRL_IN_SRC_DATA_28         = 4                     # data bits 28-31 # TODO: firmware uses only this!
CTRL_IN_SRC_DATA_START      = CTRL_IN_SRC_DATA_20   # first data bit source
CTRL_IN_SRC_IN_ALL          = (1<<CTRL_IN_SRC_NONE)|(1<<CTRL_IN_SRC_IN0)|(1<<CTRL_IN_SRC_IN1)|(1<<CTRL_IN_SRC_IN2)
CTRL_IN_SRC_DATA_ALL        = (1<<CTRL_IN_SRC_NONE)|(1<<CTRL_IN_SRC_DATA_20)|(1<<CTRL_IN_SRC_DATA_24)|(1<<CTRL_IN_SRC_DATA_28)
CTRL_IN_SRC_ALL             = CTRL_IN_SRC_IN_ALL | CTRL_IN_SRC_DATA_ALL

# input levels
CTRL_IN_LEVEL_LOW           = 0                     # level low
CTRL_IN_LEVEL_HIGH          = 1                     # level higth
CTRL_IN_EDGE_FALLING        = 2                     # edge falling
CTRL_IN_EDGE_RISING         = 3                     # edge rising
# data bits offset. in register are same bits as input levels.
# to distinguish the names we add CTRL_IN_DATA_OFFSET which in register is masked out with CTRL_IN_LEVEL_MASK
CTRL_IN_DATA_OFFSET         = (1<<CTRL_IN_LEVEL_BITS)
CTRL_IN_DATA_0              = 0|CTRL_IN_DATA_OFFSET # offset bit 0
CTRL_IN_DATA_1              = 1|CTRL_IN_DATA_OFFSET # offset bit 1
CTRL_IN_DATA_2              = 2|CTRL_IN_DATA_OFFSET # offset bit 2
CTRL_IN_DATA_3              = 3|CTRL_IN_DATA_OFFSET # offset bit 3
CTRL_IN_LVL_IN_ALL          = (1<<CTRL_IN_LEVEL_LOW)|(1<<CTRL_IN_LEVEL_HIGH)|(1<<CTRL_IN_EDGE_FALLING)|(1<<CTRL_IN_EDGE_RISING)
CTRL_IN_LVL_DATA_ALL        = (1<<CTRL_IN_DATA_0)|(1<<CTRL_IN_DATA_1)|(1<<CTRL_IN_DATA_2)|(1<<CTRL_IN_DATA_3)
CTRL_IN_LVL_ALL             = CTRL_IN_LVL_IN_ALL | CTRL_IN_LVL_DATA_ALL

# define inputs list for user to select in GUI. for sources/levels give True for default selection
# source=can be connected to several destinations. dest can be only connected to one source. source can be None, dest not.
# for in_dests values give (start offset, source_enable_bits, level_enable_bits)
# with enable bits = 1 for each enabled source or level option (use 1<<option).
# if nothing enabled destination is not displayed, if only one enabled destination is grayed.
IN_SRC_NONE         = 'None'
STR_TRIG_START      = 'start trigger'
STR_TRIG_STOP       = 'stop trigger'
STR_TRIG_RESTART    = 'restart trigger'
STR_BIT_NOP         = 'NOP bit'
STR_BIT_STRB        = 'STRB bit'
STR_BIT_STOP        = 'STOP bit'
STR_IN_0            = 'input 0'
STR_IN_1            = 'input 1'
STR_IN_2            = 'input 2'
STR_BIT_DATA_20_23  = 'data bits 20-23'
STR_BIT_DATA_24_27  = 'data bits 24-27'
STR_BIT_DATA_28_31  = 'data bits 28-31'
STR_EDGE_RISING     = 'rising edge'
STR_EDGE_FALLING    = 'falling edge'
STR_LEVEL_HIGH      = 'high level'
STR_LEVEL_LOW       = 'low level'
STR_BIT_OFFSET_0    = 'offset bit 0'
STR_BIT_OFFSET_1    = 'offset bit 1'
STR_BIT_OFFSET_2    = 'offset bit 2'
STR_BIT_OFFSET_3    = 'offset bit 3'
in_dests        = {STR_TRIG_START       : (CTRL_IN_DST_START, CTRL_IN_SRC_IN_ALL, CTRL_IN_LVL_IN_ALL),
                   STR_TRIG_STOP        : (CTRL_IN_DST_STOP, CTRL_IN_SRC_ALL, CTRL_IN_LVL_ALL),
                   STR_TRIG_RESTART     : (CTRL_IN_DST_RESTART, CTRL_IN_SRC_IN_ALL, CTRL_IN_LVL_IN_ALL),
                   STR_BIT_NOP          : (CTRL_IN_DST_DATA_NOP, 1<<CTRL_IN_SRC_DATA_28, 1<<CTRL_IN_DATA_3),
                   STR_BIT_STRB         : (CTRL_IN_DST_DATA_STRB, CTRL_IN_SRC_DATA_ALL, CTRL_IN_LVL_DATA_ALL),
                   STR_BIT_STOP         : (CTRL_IN_DST_DATA_STOP, CTRL_IN_SRC_DATA_ALL, CTRL_IN_LVL_DATA_ALL)}
in_sources      = {IN_SRC_NONE          : CTRL_IN_SRC_NONE,
                   STR_IN_0             : CTRL_IN_SRC_IN0,
                   STR_IN_1             : CTRL_IN_SRC_IN1,
                   STR_IN_2             : CTRL_IN_SRC_IN2,
                   STR_BIT_DATA_20_23   : CTRL_IN_SRC_DATA_20,
                   STR_BIT_DATA_24_27   : CTRL_IN_SRC_DATA_24,
                   STR_BIT_DATA_28_31   : CTRL_IN_SRC_DATA_28}
in_levels       = {STR_EDGE_RISING      : CTRL_IN_EDGE_RISING,
                   STR_EDGE_FALLING     : CTRL_IN_EDGE_FALLING,
                   STR_LEVEL_HIGH       : CTRL_IN_LEVEL_HIGH,
                   STR_LEVEL_LOW        : CTRL_IN_LEVEL_LOW,
                   STR_BIT_OFFSET_0     : CTRL_IN_DATA_0,
                   STR_BIT_OFFSET_1     : CTRL_IN_DATA_1,
                   STR_BIT_OFFSET_2     : CTRL_IN_DATA_2,
                   STR_BIT_OFFSET_3     : CTRL_IN_DATA_3}

# primary and secondary board default input settings.
# these settings are added to worker_args for primary and secondary boards.
# TODO: at the moment these bits are hard-coded in firmware. so changing them here does not make sense.
# do not change 'NOP bit' since it is used by driver on board to add 0 data. all data with this bit set is ignored by board.
# 'STRB bit' and 'start trigger' can be overwritten in connection_table, in GUI or in experiment script.
# if 'STRB bit' is set to 'None' output is always generated regardless if strobe bit toggles or not.
# 'STRB bit' might be ignored by firmware. 'STOP bit' and 'IRQ bit' must be enabled for firmware to take into account.
default_in_prim = {STR_BIT_NOP      : (STR_BIT_DATA_28_31, STR_BIT_OFFSET_3),
                   STR_BIT_STRB     : (STR_BIT_DATA_20_23, STR_BIT_OFFSET_3)}
default_in_sec  = {STR_BIT_NOP      : (STR_BIT_DATA_28_31, STR_BIT_OFFSET_3),
                   STR_BIT_STRB     : (STR_BIT_DATA_20_23, STR_BIT_OFFSET_3),
                   STR_TRIG_START   : (STR_IN_0, STR_EDGE_FALLING)}

def get_ctrl_in(input_selection,check=True):
    """
    returns input control register value from input_selection.
    input_selection = {dest:(source, level)),dest:(source, level),...}
    dest = key from in_dests. missing destinations are considered as not used.
    source = key from in_sources.
    level = key from in_levels.
    returns 32bit trigger control register value used to configure board.
    """
    register = np.array([0],dtype=np.uint32)
    for dest, value in input_selection.items():
        source, level = value
        register[0] |= (in_sources[source]|((in_levels[level] & CTRL_IN_LEVEL_MASK)<<CTRL_IN_SRC_BITS))<<in_dests[dest][0]
    if check: # consistency check
        sel = get_in_selection(register[0],return_NONE=False, check=False)
        for key,value in sel.items():
            if (key not in input_selection) or (input_selection[key][0] != value[0]) or (input_selection[key][1] != value[1]):
                if key in input_selection:
                    save_print('input (source, level) =', input_selection[key])
                else:
                    save_print('input key %s not existing' % (key))
                save_print('output (source, level) =', value)
                print('input selection:\n', input_selection, '\n-> value = 0x%x' % (register[0]))
                print('value = 0x%x' % register[0], '\n-> input selection:\n', sel)
                raise LabscriptError("error: get_ctrl_in does not give consistent result with get_in_selection for key '%s'!" %(key))
    #sel = get_in_selection(register[0],return_NONE=False, check=False)
    #print('get_ctrl_in')
    #print(input_selection)
    #print(sel)
    #raise LabscriptError('test')
    return register[0]

def get_in_selection(register, return_NONE=True, check=True):
    """
    returns dictionary with input selections.
    inverse function to get_ctrl_in.
    if return_NONE == True returns also IN_SRC_NONE, otherwise not.
    """
    selection = {}
    for dest, dest_offset in in_dests.items():
        offset, source_enable_bits, level_enable_bits = dest_offset
        reg_dest = (register >> offset) & CTRL_IN_DST_MASK;
        for src, src_bits in in_sources.items():
            if (source_enable_bits & (1 << src_bits)) != 0: # source enabled
                if return_NONE or (src_bits != CTRL_IN_SRC_NONE):
                    if (reg_dest & CTRL_IN_SRC_MASK) == src_bits:
                        for level, level_bits in in_levels.items():
                            if (level_enable_bits & (1 << level_bits)) != 0:  # level enabled
                                if src_bits >= CTRL_IN_SRC_DATA_START and (level_bits & CTRL_IN_DATA_OFFSET) == 0: continue
                                if ((reg_dest >> CTRL_IN_SRC_BITS) & CTRL_IN_LEVEL_MASK) == (level_bits & CTRL_IN_LEVEL_MASK):
                                    selection[dest] = (src,level)
                                    break
                        if dest not in selection:
                            raise LabscriptError("could not find level for %s! register 0x%x" % (dest, register))
                        break
    if check and (get_ctrl_in(selection) != register): # consistency check
        raise LabscriptError('error: get_in_selection does not give consistent result with get_ctrl_in: %x != %x' %(get_ctrl_in(selection), register), selection)
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
    if is_in_start(ctrl_trg):    info += ['start']
    if is_in_stop(ctrl_trg):     info += ['stop']
    if is_trg_restart(ctrl_trg): info += ['restart']
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
CTRL_OUT_SRC_WAIT           = 7                 # wait (high only when run bit reset)
CTRL_OUT_SRC_READY          = 8                 # ready
CTRL_OUT_SRC_RESTART        = 9                 # restart toggle bit in cycling mode
CTRL_OUT_SRC_TRG_START      = 10                # toggles with start trigger
CTRL_OUT_SRC_TRG_STOP       = 11                # toggles with stop trigger
CTRL_OUT_SRC_TRG_RESTART    = 12                # toggles with restart trigger
CTRL_OUT_SRC_ALL            = (1<<CTRL_OUT_SRC_NONE)|(1<<CTRL_OUT_SRC_SYNC_OUT)|(1<<CTRL_OUT_SRC_SYNC_EN)|(1<<CTRL_OUT_SRC_SYNC_MON)|\
                              (1<<CTRL_OUT_SRC_CLK_LOST)|(1<<CTRL_OUT_SRC_ERROR)|\
                              (1<<CTRL_OUT_SRC_RUN)|(1<<CTRL_OUT_SRC_WAIT)|(1<<CTRL_OUT_SRC_READY)|(1<<CTRL_OUT_SRC_RESTART)|\
                              (1<<CTRL_OUT_SRC_TRG_START)|(1<<CTRL_OUT_SRC_TRG_STOP)|(1<<CTRL_OUT_SRC_TRG_RESTART)

# output levels
CTRL_OUT_LEVEL_LOW          = 0                 # level active low = inverted
CTRL_OUT_LEVEL_HIGH         = 1                 # level active high = normal
CTRL_OUT_LVL_ALL            = (1<<CTRL_OUT_LEVEL_LOW)|(1<<CTRL_OUT_LEVEL_HIGH)

# define output list for user to select in GUI. for sources/levels give True for default selection
# source=can be connected to several destinations. dest can be only connected to one source. source can be None, dest not.
# for out_dests values give (start offset, source_enable_bits, level_enable_bits)
# with enable bits = 1 for each enabled source or level option (use 1<<option).
# if nothing enabled destination is not displayed, if only one enabled destination is grayed.
# TODO: define string constants as for inputs...
OUT_SRC_NONE   = 'fixed'
out_dests   = {   'output 0'        : (CTRL_OUT_DST_OUT0, CTRL_OUT_SRC_ALL, CTRL_OUT_LVL_ALL),
                  'output 1'        : (CTRL_OUT_DST_OUT1, CTRL_OUT_SRC_ALL, CTRL_OUT_LVL_ALL),
                  'output 2'        : (CTRL_OUT_DST_OUT2, CTRL_OUT_SRC_ALL, CTRL_OUT_LVL_ALL),
                  'bus enable 0'    : (CTRL_OUT_DST_BUS_EN0, CTRL_OUT_SRC_ALL, CTRL_OUT_LVL_ALL),
                  'bus enable 1'    : (CTRL_OUT_DST_BUS_EN1, CTRL_OUT_SRC_ALL, CTRL_OUT_LVL_ALL)}
out_sources = {   OUT_SRC_NONE      : CTRL_OUT_SRC_NONE,
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
out_levels  = {   STR_LEVEL_LOW     : CTRL_OUT_LEVEL_LOW,
                  STR_LEVEL_HIGH    : CTRL_OUT_LEVEL_HIGH}

# primary and secondary board default output settings
# these settings are added to worker_args for primary and secondary boards.
# all settings here can be overwritten in connection_table, in GUI or in experiment script.
default_out_prim = {'output 0':('sync out',STR_LEVEL_HIGH)}
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
        register[0] |= (out_sources[source]|(out_levels[level]<<CTRL_OUT_SRC_BITS))<<out_dests[dest][0]
    return register[0]

def get_out_selection(register, return_NONE=True):
    """
    returns dictionary with output selections.
    inverse function to get_ctrl_out.
    if return_NONE == True returns also OUT_SRC_NONE, otherwise not.
    """
    selection = {}
    for dest, dest_offset in out_dests.items():
        reg_dest = (register >> dest_offset[0]) & CTRL_OUT_DST_MASK;
        for src, src_bits in out_sources.items():
            if return_NONE or (src_bits != CTRL_OUT_SRC_NONE):
                if (reg_dest & CTRL_OUT_SRC_MASK) == src_bits:
                    for level, level_bits in out_levels.items():
                        if ((reg_dest >> CTRL_OUT_SRC_BITS) & CTRL_OUT_LEVEL_MASK) == level_bits:
                            selection[dest] = (src,level)
                            break
                    break
    if get_ctrl_out(selection) != register: # consistency check
        save_print('error: get_out_selection does not give consistent result with get_ctrl_out: %x != %x' %(get_ctrl_out(selection), register), selection)
        exit()
    return selection

def is_sync_out(ctrl_out):
    "returns True when sync_out is enabled in output control register ctrl_out"
    for dest, dest_offset in out_dests.items():
        if (((ctrl_out >> dest_offset[0]) & CTRL_OUT_SRC_MASK) == CTRL_OUT_SRC_SYNC_OUT): return True
    return False

def get_out_info(ctrl_out):
    "returns short info string with output selections"
    info = []
    if is_sync_out(ctrl_out):   info += ['sync out']
    if len(info) > 0: return "(" + "|".join(info) + ")"
    else:             return ""

# TODO: maybe merge with parse_worker_args
def check_worker_args(worker_args):
    "checks if valid worder_args are given"
    for key,value in worker_args.items():
        if key not in worker_args_keys:
            raise LabscriptError("worker_arg '%s' is not allowed!" % (key))
        if (key == STR_CONFIG) or (key == STR_CONFIG_MANUAL):
            if not isinstance(value, integer):
                raise LabscriptError("worker_arg '%s':'%s' must be an integer! but is %s" % (key, str(value), type(value)))
            if (value & CTRL_USER_MASK) != 0:
                raise LabscriptError("worker_arg '%s':0x%x is invalid!" % (key, value))
        elif key == STR_INPUTS:
            if isinstance(value, dict):
                ctrl_in = get_ctrl_in(value)
            else:
                selection = get_in_selection(value, return_NONE=False)
        elif key == STR_OUTPUTS:
            if isinstance(value, dict):
                ctrl_out = get_ctrl_out(value)
            else:
                selection = get_out_selection(value, return_NONE=False)
        elif (key == STR_EXT_CLOCK) or (key == STR_IGNORE_CLOCK_LOSS) or (key == STR_SIMULATE):
            if not isinstance(value, bool):
                raise LabscriptError("worker_arg '%s':'%s' must be True/False (bool)! but is %s" % (key, str(value), type(value)))
        elif (key == STR_SYNC_WAIT) or (key == STR_SYNC_PHASE) or (key == STR_CYCLES):
            if not isinstance(value, integer):
                raise LabscriptError("worker_arg '%s':'%s' must be an integer! but is %s" % (key, str(value), type(value)))
        else:
            raise LabscriptError("error worker_arg '%s'!" % (key))

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
if old_version:
    FPGA_status_unpack_info_8   = [(25,'I'),(6,'B'),(2,'s'),(3,'i'),(16,'I'),(FPGA_STATUS_NUM_DEBUG,'I')] # (2,'s')
    FPGA_status_unpack_info_12  = [(25,'I'),(6,'B'),(2,'s'),(3,'i'),(17,'I'),(FPGA_STATUS_NUM_DEBUG,'I')]
else:
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
            save_print('FPGA_status recieved %i bytes but must be either %i or %i' % (len(bytes), FPGA_STATUS_NUM_BYTES_8, FPGA_STATUS_NUM_BYTES_12))
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
        if not old_version:
            self.set_cycles     = data[i]; i += 1;
        self.clk_div            = data[i]; i += 1;
        self.strb_delay         = data[i]; i += 1;
        self.sync_delay         = data[i]; i += 1;
        self.sync_phase         = data[i]; i += 1;
        self.status             = data[i]; i += 1;
        self.board_time         = data[i]; i += 1;
        self.board_samples      = data[i]; i += 1;
        self.board_time_ext     = data[i]; i += 1;
        self.board_samples_ext  = data[i]; i += 1;
        if not old_version:
            self.board_cycles   = data[i]; i += 1;
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
        if not old_version:
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
    #check device type
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
    default_value = SP_INVALID_VALUE
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
# TODO: maybe can be replaced with markers?
class SpecialIM(IntermediateDevice):
    description = 'internal device for special data'
    allowed_children = [SpecialOut]
    shared_address = False

    def __init__(self, name, parent_device, bus_rate, **kwargs):
        #parent device must be FPGA_board. you should not connect it directly to clockline.
        if not isinstance(parent_device, FPGA_board):
            raise LabscriptError("Device '%s' parent class is '%s' but must be '%s'!" % (self.name, parent_device.__class__, FPGA_board))
        # get clockline from FPGA_board and set as parent
        self.parent_device = parent_device.get_clockline(self, bus_rate)
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

    def __init__(self, name, parent_device, connection, rack, max_channels, bus_rate=MAX_BUS_RATE, **kwargs):
        #parent device must be FPGA_board. you should not connect it directly to clockline.
        if not isinstance(parent_device, FPGA_board):
            raise LabscriptError("Device '%s' parent class is '%s' but must be '%s'!" % (name, parent_device.__class__, FPGA_board))
        # get clockline from FPGA_board and set as parent
        self.parent_device = parent_device.get_clockline(self, bus_rate)
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
        device.user_default_value = device.default_value # default_value given in connection_table
        device.default_value = DO_INVALID_VALUE # automatically inserted value by labscript
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
                # first user-defined instruction (auto-inserted time=dev.t0, value=DO_INVALID_VALUE is ignored)
                user_times = [key for key,value in dev.instructions.items() if isinstance(value,dict) or (key != dev.t0) or (value != dev.default_value)]
                if channels is not None:
                    # get changing channels for all conflicts (called only when conflicts detected)
                    # here we detect individual changing channels
                    d = np.where(dev.raw_output != dev.default_value, dev.raw_output, zeros)
                    chg = np.concatenate([[False], (np.array(d[1:] - d[0:-1]) != 0)])
                    if len(user_times) > 0:
                        chg |= (np.abs(times - round(min(user_times), TIME_ROUND_DECIMALS)) < TIME_PRECISION)
                    index = np.arange(len(times))[conflicts & chg]
                    for i in index:
                        conflict_time = times[i]
                        conflict_channel = [dev.name, None if (i == 0) or (d[i - 1] == dev.default_value) else d[i - 1], d[i]]
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

    def __init__(self, name, parent_device, rack, max_channels, bus_rate=MAX_BUS_RATE, **kwargs):
        # parent device must be FPGA_board. you should not connect it directly to clockline.
        if not isinstance(parent_device, FPGA_board):
            raise LabscriptError("Device '%s' parent class is '%s' but must be '%s'!" % (self.name, parent_device.__class__, FPGA_board))
        # get clockline from FPGA_board and set as parent_device
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
        device.user_default_value = device.default_value # default_value given in connection_table
        device.default_value = AO_INVALID_VALUE # automatically inserted value by labscript
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
            # first user-defined instruction (auto-inserted time=dev.t0, value=AO_INVALID_VALUE is ignored)
            user_times = [key for key,value in dev.instructions.items() if isinstance(value,dict) or (key != dev.t0) or (value != AO_INVALID_VALUE)]
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
                    conflict_channel = [dev.name, None if (i == 0) or (dev.raw_output[i - 1] == AO_INVALID_VALUE) else dev.raw_output[i - 1], dev.raw_output[i]]
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
    trigger_edge_type = 'rising'

    PCLOCK_FORMAT           = '%s_pc%i_%s'      # device name + index + bus_rate
    CLOCKLINE_FORMAT        = '%s_cl%i'         # pseudo clock name + index
    CLOCKLINE_FORMAT_NAME   = '%s_cl%i_%s'      # pseudo clock name + index
    CON_FORMAT              = '%s_con'          # pseudo clock or clockline name
    CLOCK_FORMAT_SEP        = "_"               # format separator for when clockline is given as name

    # call with name, IP address string and port string, output bus rate in Hz and num_racks (1=8 bytes/sample, 2=12 bytes/sample)
    # for all secondary boards give trigger_device=primary board.
    @set_passed_properties()
    def __init__(self, name, ip_address, ip_port=DEFAULT_PORT, bus_rate=MAX_BUS_RATE, num_racks=1, trigger_device=None, worker_args={}):
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
                self.trigger_edge_type = 'rising' if inputs[STR_TRIG_START][1] == STR_EDGE_RISING else 'falling'
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
        self.clock_limit = CLOCK_LIMIT
        self.clock_resolution = CLOCK_RESOLUTION

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
        elif isinstance(device, labscript.labscript.Trigger):
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
        # times and channel.raw_data will have different lengths!
        times = np.unique(np.concatenate([pseudoclock.times[clockline] for pseudoclock in self.child_devices for clockline in pseudoclock.child_devices]))
        exp_time = times[-1]

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
        final_values = {} # final state of each used channel
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
                        special = True
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
                            d |= dev.to_word(dev.raw_output)

                            # mark changes
                            chg[0]  |= (dev.raw_output[0] != dev.default_value)
                            chg[1:] |= ((d[1:] - d[:-1]) != 0)

                            # save last state. worker needs channel name and not device name (dev.name).
                            # if last value is dev.default_value then channel was not changed and we return user_default_value.
                            ID = get_ID(dev.type,dev.rack,dev.address,dev.channel)
                            if dev.raw_output[-1] == dev.default_value: final_values[get_channel_name(ID)] = dev.user_default_value
                            else:                                       final_values[get_channel_name(ID)] = dev.raw_output[-1]

                        # check conflicts with devices of different address
                        i = indices[chg]
                        conflicts[i,IM.rack] |= changes[i,IM.rack]
                        changes[i,IM.rack] = True

                        # save data where output changed
                        # we have to mask NOP bit from unused channels
                        data[i,IM.rack+1] = d[chg] & DATA_ADDR_MASK
                    else:
                        # no shared address (like analog out): collect data for each individual device
                        for dev in IM.child_devices:
                            #if np.count_nonzero(dev.raw_output == dev.default_value) != len(t):
                            #    # print('%s instr:'%dev.name, dev.instructions)
                            #    print('%s raw data:' % dev.name, dev.raw_output)

                            if len(dev.raw_output) != len(t):  # sanity check.
                                raise LabscriptError('generate_code: raw output not consistent with times? (should not happen)')

                            # convert raw data into data word
                            d = dev.to_word(dev.raw_output)
                            #print('%s data:' % dev.name, d)

                            # save last state. worker needs channel name and not device name (dev.name).
                            # if last value is dev.default_value then channel was not changed and we return user_default_value.
                            ID = get_ID(dev.type,dev.rack,dev.address,dev.channel)
                            if dev.raw_output[-1] == dev.default_value: final_values[get_channel_name(ID)] = dev.user_default_value
                            else:                                       final_values[get_channel_name(ID)] = dev.raw_output[-1]

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
                    t = pseudoclock.times[clockline]
                    indices = np.argwhere(np.isin(times, t)).ravel()
                    if len(t) == 0: continue

                    for IM in clockline.child_devices:
                        if isinstance(IM, SpecialIM):
                            for dev in IM.child_devices:
                                #if np.count_nonzero(dev.raw_output == dev.default_value) != len(t):
                                #    print('%s instr:'%dev.name, dev.instructions)
                                #    print('%s raw data:' % dev.name, dev.raw_output)

                                if len(dev.raw_output) != len(t):  # sanity check.
                                    raise LabscriptError('generate_code: raw output not consistent with times? (should not happen)')

                                # convert raw data into data word
                                d = dev.to_word(dev.raw_output)
                                #print('%s data:' % dev.name, d)

                                # check if strobe bit is set somewhere
                                if np.count_nonzero(d & BIT_STRB_SH) > 0:
                                    if not BIT_STRB_GENERATE:
                                        raise LabscriptError("Strobe bit is not generated but in your script 'SKIP' with do_not_toggle_STRB=True is called which uses this bit! Either enable generation of strobe bit (BIT_GENERATE=True) or call 'SKIP' with do_not_toggle_STRB=False to use NOP bit instead of Strobe bit.")
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
                    t = pseudoclock.times[clockline]
                    indices = np.argwhere(np.isin(times, t)).ravel()
                    for IM in clockline.child_devices:
                        for dev in IM.child_devices:
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
                                        s5 = '-' if info[5][i] == DO_INVALID_VALUE else ("low" if info[5][i]==0 else "high")
                                        s6 = '-' if info[6][i] == DO_INVALID_VALUE else ("low" if info[6][i]==0 else "high")
                                        s5 = "low" if info[5][i]==0 else "high"
                                        s6 = "low" if info[6][i]==0 else "high"
                                        s7 = ''
                                    elif info[0] == TYPE_AO: # analog out
                                        s2 = "0x%02x" % (info[2])
                                        s5 = '-' if info[5][i] == AO_INVALID_VALUE else "%12.6f" % info[5][i]
                                        s6 = '-' if info[6][i] == AO_INVALID_VALUE else "%12.6f" % info[6][i]
                                        s7 = ''
                                    elif info[0] == TYPE_SP:
                                        # special data
                                        # note: since address = None will never cause conflict but can appear with other conflicts when at same time
                                        s2 = '-'
                                        s5 = '-' if info[5][i] == SP_INVALID_VALUE else "0x%8x" % info[5][i]
                                        s6 = '-' if info[6][i] == SP_INVALID_VALUE else "0x%8x" % info[6][i]
                                        s7 = ' ignore'
                                    save_print('%35s %4i %4s %12i %12.6f %12s %12s%s'%(ch, info[1], s2, info[3][i], info[4][i], s5, s6, s7))
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
        self.show_data(data, 'data: (%.3fms)' % (t_new))

        save_print("'%s' generating code (4) %.3fms ..." % (self.name, (get_ticks() - total_time) * 1e3))

        # TODO: generate_code is not called for secondary boards? so have to call it manually.
        #       for iPCdev needed to comment generate_code in intermediate_device, then was working. here not?!
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
            ext = ((int)(phase_ext*PHASE_360/360)) & SYNC_PHASE_MASK if phase_ext is not None else SEC_PHASE_EXT
            det = ((int)(phase_det*PHASE_360/360)) & SYNC_PHASE_MASK if phase_det is not None else SEC_PHASE_DET
            self.worker_args_ex[STR_SYNC_PHASE] = (ext<<SYNC_PHASE_BITS) | det

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
        try:
            # called for each board and intermediate device
            self.path = path
            self.name = device.name
            self.device = device
            self.board = self.device
            self.type = None
            if device.device_class == 'FPGA_board': # pseudoclock device
                self.type = TYPE_board
                print("\nrunviewer loading '%s' (FPGA_board)" % (device.name))
                self.bus_rate = device.properties['bus_rate']
            else: # intermediate device
                # find parent board
                self.board = self.device.parent.parent.parent
                if self.board.device_class != 'FPGA_board':
                    raise LabscriptError("parent board is class '%s' instead of 'FPGA_board'?" % (self.board.device_class))
                # get bus rate
                self.bus_rate = self.board.properties['bus_rate']
                #print("top device '%s', bus rate %.3e Hz" %(self.board.name,self.bus_rate))
                if device.device_class == 'AnalogChannels':
                    self.type = TYPE_AO
                    print("runviewer loading '%s' (analog outputs)" % (device.name))
                    self.ao_list = get_channels(device, True)
                    print('%i channels:'%len(self.ao_list), list(self.ao_list.keys()))
                elif device.device_class == 'DigitalChannels':
                    self.type = TYPE_DO
                    print("runviewer loading '%s' (digital outputs)" % (device.name))
                    self.do_list = get_channels(device, False)
                    print('%i channels:'%len(self.do_list), list(self.do_list.keys()))
                else: # unknown device
                    print("runviewer loading '%s' (ignore)" % (device.name))
        except Exception as e:
            # we have to catch exceptions here since they are not displayed which makes debugging very difficult
            print("exception '%s'" % (e))
            raise e

    def get_traces(self, add_trace, clock=None):
        try:
            # called for each board and intermediate device
            data = []
            traces = {}
            with h5py.File(self.path, 'r') as f:
                # get data sent to board
                group = f['devices/%s' % (self.board.name)]
                data = group['%s_matrix'%self.board.name][:]
            if len(data) == 0:
                print("'%s' add trace (type %d) no data!" % (self.name, self.type))
            else:
                #print('matrix\n',data)
                if self.type == TYPE_board: # main board
                    print("'%s' add trace (board) %i samples" % (self.name, len(data)))
                    time = word_to_time(data[:,0], self.bus_rate)
                    for pseudoclock in self.device.child_list.values():
                        if pseudoclock.device_class == 'FPGA_PseudoClock':
                            for clockline in pseudoclock.child_list.values():
                                if clockline.device_class == 'ClockLine':
                                    # add clockline to traces:
                                    # this creates RunviewerClass for clockline and calls get_traces for all of its intermediate channels
                                    # the (time,value) is given as 'clock' to get_traces
                                    # we also call add_trace such that trace of clockline can be inspected by user
                                    print('adding Clockline %s' % (clockline.name))
                                    value = [(i & 1) for i in range(len(time))]
                                    add_trace(clockline.name, (time, value), None, None)
                                    traces[clockline.name] = (time, value)
                        elif pseudoclock.device_class == 'Trigger':
                            # add trigger device to traces:
                            # this creates RunviewerClass for secondary board and calls get_traces for all of its intermediate channels
                            # the (time,value) is given as 'clock' to get_traces
                            print('adding Trigger %s' % (pseudoclock.name))
                            traces[pseudoclock.name] = (time, value)
                elif self.type == TYPE_AO: # analog outputs (intermediate device)
                    print("'%s' add trace (analog out) %i samples" % (self.name, len(data)))
                    # for all channels extract from data all entries with channel device address & rack
                    #TODO use self.device.child_list[i].unit_conversion_class/params
                    for name, ll in self.ao_list.items():
                        [ID,props,child,ch_name,unit_conversion_class] = ll
                        # we have access to unit conversion class and parameters
                        ch = self.device.child_list[name]
                        if unit_conversion_class is not None:
                            unit = ch.unit_conversion_params['unit']
                            print("'%s' unit conversion class: '%s', unit '%s'" % (name, ch.unit_conversion_class, unit))
                            #for k,v in ch.unit_conversion_params.items():
                            #    print('%s : %s' % (k, v))
                            if runviewer_show_units: # plot in given units
                                txt = 'unit_conversion_class(calibration_parameters=%s)' % (ch.unit_conversion_params)
                                unit_conversion = eval(compile(txt, 'conv', 'eval'))
                                to_unit = getattr(unit_conversion, unit+'_from_base')
                            #print(to_unit)
                            else: # plot in volts
                                to_unit = None
                        else:
                            #print("'%s' no unit conversion." % (name))
                            to_unit = None
                        rack = get_rack(ID)
                        addr = get_address(ID)
                        mask = (((data[:, rack + 1] & (BIT_NOP_SH | ADDR_MASK_SH)) >> ADDR_SHIFT) == addr)
                        d = data[mask]
                        if len(d) > 0: # data available
                            #print('time:\n', d[:,0]/self.bus_rate)
                            #print('value:\n', data[:, rack + 1])
                            #print('mask:\n', mask.astype(np.uint8))
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
                            #print("ao '%s' 0x%x:" % (name,ID))
                            #print('time = ',time)
                            # we add trace for all channels, even if not used
                            add_trace(name, (time, value), self, ch_name)
                            #traces[name] = (time, value) # TODO: should be not needed? call only for clocklines and triggers
                            print("analog out '%s' (%s, addr 0x%x) %i samples %.3f - %.3fV" % (name, ch_name, addr, len(value), np.min(value), np.max(value)))
                            if len(value) <= 20:
                                print(np.transpose([time,value]))
                        else: # address is not used
                            print("'%s' (%s, addr 0x%x) not used" % (name, ch_name, addr))
                            if runviewer_show_all:
                                time = np.array([data[0, 0], data[-1, 0]]) / self.bus_rate
                                value = np.array([0.0, 0.0])
                                add_trace(name, (time, value), self, ch_name)
                            #for i,dd in enumerate(data):
                            #    print('%3i %10d %08x' % (i, dd[0], dd[rack+1]))
                            #print('time:\n', d[:,0]/self.bus_rate)
                            #print('value:\n', data[:, rack + 1])
                            #print('mask:\n', mask.astype(np.uint8))
                elif self.type == TYPE_DO: # digital outputs (intermediate device)
                    print("'%s' add trace (digital out) %i samples" % (self.name, len(data)))
                    # get rack, address and mask from first channel. this is the same for all channels
                    [ID, props, child, ch_name, unit_conversion_class] = list(self.do_list.values())[0]
                    rack = get_rack(ID)
                    addr = get_address(ID)
                    mask = (((data[:,rack+1] & (BIT_NOP_SH|ADDR_MASK_SH))>>ADDR_SHIFT) == addr)
                    #for i,di in enumerate(d):
                    #    print("%8u %08x %s" % (di[0], di[1], mask[i]))
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
                            #print("do '%s' 0x%x:" % (name,ID))
                            #print('time = ',time)
                            #print('data = ',value)
                            # we add trace for all channels, even if channel might not be used
                            # add_trace(name, (time, value), parent, conn)
                            add_trace(name, (time, value), self, ch_name)
                            #traces[name] = (time, value) # TODO: should be not needed? call only for clocklines and triggers
                            print("digital out '%s' (%s, addr 0x%x, ch %i) %i samples" % (name, ch_name, addr, channel, len(value)))
                            if len(value) <= 2:
                                print(np.transpose([time,value]))
                        else: # address is not used
                            print("'%s' (%s, addr 0x%x) not used" % (name, ch_name, addr))
                            if runviewer_show_all:
                                time = np.array([data[0, 0], data[-1, 0]]) / self.bus_rate
                                value = np.array([0, 0])
                                add_trace(name, (time, value), self, ch_name)
                else: # DDS not implemented
                    print("'%s' add trace (unknown?) %i samples" % (self.name, len(data)))

        except Exception as e:
            # we have to catch exceptions here since they are not displayed which makes debugging very difficult
            print("exception '%s'" % (e))
            raise e

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
    def __init__(self, name, parent, update=[], worker_args={}):
        """
        creates button widgets and clock selection check boxes for FPGA board
        name   = unique name used to save and restore data
        parent = DeviceTab class
        update = list of widgets with update(allow_changes) function called when allow_changes is clicked
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
        self.store_allow_changes = name + '_' + STR_ALLOW_CHANGES
        self.store_clock  = name + '_' + STR_EXT_CLOCK
        self.store_ignore = name + '_' + STR_IGNORE_CLOCK_LOSS
        self.update       = update
        self.worker_args  = worker_args

        self.dialog_enable = True

        self.allow_changes = False
        self.ext_clock = False
        self.ignore_clock_loss = False
        if STR_EXT_CLOCK in worker_args:
            self.ext_clock  = worker_args[STR_EXT_CLOCK]
        if STR_IGNORE_CLOCK_LOSS in worker_args:
            self.ignore_clock_loss  = worker_args[STR_IGNORE_CLOCK_LOSS]

        self.grid = QGridLayout(self)
        self.setLayout(self.grid)

        # device state button
        bt_state = QPushButton('get state')
        bt_state.setStyleSheet('QPushButton {border:1px solid #8f8f91; border-radius: 3px;}')
        self.grid.addWidget(bt_state,0,0)
        bt_state.clicked.connect(parent.get_state)

        # connect / disconnect button
        bt_conn = QPushButton('disconnect')
        bt_conn.setStyleSheet('QPushButton {border:1px solid #8f8f91; border-radius: 3px;}')
        self.grid.addWidget(bt_conn,0,1)
        bt_conn.clicked.connect(parent.conn)
        #TODO: get actual connection status and connect or disconnect with this button!

        # abort button
        bt_abort = QPushButton('abort!')
        bt_abort.setStyleSheet('QPushButton {color: red; border:1px solid #ff0000; border-radius: 3px;}')
        self.grid.addWidget(bt_abort,0,2)
        bt_abort.clicked.connect(parent.abort)

        # enable/disable changes checkbox
        self.cb_allow_changes = QCheckBox('allow changes (caution!)')
        self.cb_allow_changes.setChecked(self.allow_changes)
        self.cb_allow_changes.clicked.connect(self.onAllowChanges)
        self.grid.addWidget(self.cb_allow_changes,1,0)

        # external clock
        self.cb_ext_clock = QCheckBox('external clock')
        self.cb_ext_clock.setChecked(self.ext_clock)
        #self.cb_ext_clock.setStyleSheet("color: black")
        self.cb_ext_clock.setEnabled(self.allow_changes)
        self.cb_ext_clock.clicked.connect(self.onChangeExtClock)
        self.grid.addWidget(self.cb_ext_clock,2,0)

        # ignore clock loss
        self.cb_ignore_clock_loss = QCheckBox('ignore clock loss')
        self.cb_ignore_clock_loss.setChecked(self.ignore_clock_loss)
        self.cb_ignore_clock_loss.setStyleSheet("color: red")
        self.cb_ignore_clock_loss.setEnabled(self.allow_changes)
        self.cb_ignore_clock_loss.clicked.connect(self.onChangeIgnoreClockLoss)
        self.grid.addWidget(self.cb_ignore_clock_loss, 2, 1)

    def onAllowChanges(self, state):
        self.allow_changes = self.cb_allow_changes.isChecked()
        self.cb_ext_clock.setEnabled(self.allow_changes)
        self.cb_ignore_clock_loss.setEnabled(self.allow_changes)
        for widget in self.update:
            widget.update(self.allow_changes)

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

    def add_update(self, widget):
        "add widget or list of widgets to be updated"
        if isinstance(widget, list):
            self.update += widget
        else:
            self.update.append(widget)

    def get_save_data(self, data):
        "save current settings to data dictionary"
        data[self.store_allow_changes] = False # self.allow_changes. we always reset
        data[self.store_clock]  = self.ext_clock
        data[self.store_ignore] = self.ignore_clock_loss

    def restore_save_data(self, data):
        "restore saved settings from data dictionary"
        if reset_all: return
        self.dialog_enable = False # temporarily disable dialog
        if (self.store_allow_changes in data):
            self.allow_changes = False #data[self.store_allow_changes]
            self.cb_ext_clock.setEnabled(self.allow_changes)
            self.cb_ignore_clock_loss.setEnabled(self.allow_changes)
            #self.onAllowChanges(None) # this makes problems when restarting tab without restarting blacs
        if (self.store_clock in data) and (STR_EXT_CLOCK not in self.worker_args):
            self.ext_clock = data[self.store_clock]
            self.cb_ext_clock.setChecked(self.ext_clock)
        if (self.store_ignore in data) and (STR_IGNORE_CLOCK_LOSS not in self.worker_args):
            self.ignore_clock_loss = data[self.store_ignore]
            self.cb_ignore_clock_loss.setChecked(self.ignore_clock_loss)
        self.dialog_enable = True # enable dialog

class FPGA_IO(QWidget):
    def __init__(self, parent, name = "", dests={}, sources={}, levels={}, showHeader=True, is_input=True, worker_args={}):
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
        self.sources     = [] # list of source combobox
        self.levels      = [] # list of levels combobox
        self.is_input    = is_input
        self.init        = {}
        if self.is_input and (STR_INPUTS in worker_args):
            self.init = worker_args[STR_INPUTS]
        if (not self.is_input) and (STR_OUTPUTS in worker_args):
            self.init = worker_args[STR_OUTPUTS]

        self.change_enable = True
        self.dialog_enable = True

        self.grid = QGridLayout(self)
        self.setLayout(self.grid)

        self.value = 0;

        if showHeader:
            self.grid.addWidget(QLabel('destination'), 0, 0)
            self.grid.addWidget(QLabel('source'), 0, 1)
            self.grid.addWidget(QLabel('level'), 0, 2)
            row = 1
        else:
            row = 0

        for name,value in dests.items():
            src_bits, lvl_bits = value[1:3]
            if src_bits == 0 or lvl_bits == 0: continue # nothing enabled
            self.grid.addWidget(QLabel(name), row, 0)
            src = QComboBox()
            src.setEnabled(False)
            for source, src_bit in sources.items():
                if src_bits & (1<<src_bit):
                    src.addItem(source)
            self.grid.addWidget(src, row, 1)
            self.sources.append(src)
            lvl = QComboBox()
            lvl.setEnabled(False)
            for level, lvl_bit in levels.items():
                if lvl_bits & (1<<lvl_bit):
                    lvl.addItem(level, i)
            self.grid.addWidget(lvl, row, 2)
            self.levels.append(lvl)
            src.currentIndexChanged.connect(self.changed)
            lvl.currentIndexChanged.connect(self.changed)
            row += 1

        # init combo boxes (all must have been created). this calls 'changed' for each option.
        self.init_items(self.init, first_time=True)

        # indicator/edit of actual settings in hex
        self.grid.addWidget(QLabel('value 0x'), row, 0)
        self.hex_value = QLineEdit('None')
        self.hex_value.setEnabled(False)
        self.hex_value.returnPressed.connect(self.value_changed)
        self.grid.addWidget(self.hex_value, row, 1)

    def init_items(self, init, first_time=False):
        # initialize combo boxes. if first_time = False take only options which are NOT in self.init.
        # this allows to give starting selections in worker_args,
        # or if no worker_args given, restore last settings in GUI (using restore_save_data).
        if len(init) > 0:
            self.change_enable = False # changed() will be called for each changed item. this avoids calling worker each time
            i = 0
            for name, value in self.dests.items():
                src_bits, lvl_bits = value[1:3]
                if src_bits == 0 or lvl_bits == 0: continue  # nothing enabled
                if name in init:
                    if first_time or (name not in self.init):
                        src = self.sources[i] # source combobox
                        index = src.findText(init[name][0])
                        if (index >= 0): src.setCurrentIndex(index)
                        else:            save_print("error init %s: '%s' is not in sources" % (self.name, init[name][0]))
                        lvl = self.levels[i] # level combobox
                        index = lvl.findText(init[name][1])
                        if (index >= 0): lvl.setCurrentIndex(index)
                        else:
                            save_print("error init %s: '%s' is not in levels" % (self.name, init[name][1]))
                            print(init)
                i += 1
            self.change_enable = True
            if not first_time:
                # update of worker when all changes are done
                self.dialog_enable = False # disable dialog box
                self.changed(0)
                self.dialog_enable = True

    def value_changed(self):
        # user changed hex value and pressed return
        try:
            self.value = int(self.hex_value.text(), 16)
        except ValueError:
            print('%s is not a hexadecimal number! reverting to last valid number' % (self.hex_value.text()))
            self.hex_value.setText('%x' % self.value)
            return
        if self.is_input:
            selection = get_in_selection(self.value)
            print('new input config 0x%x' % self.value, selection)
        else:
            selection = get_out_selection(self.value)
            print('new output config 0x%x'%self.value, selection)
        self.init_items(selection, True)

    def changed(self, index):
        # user changed any combo box. for simplicity we go through all of them and recalculate control register value.
        #item = self.sender()
        #name = item.currentText()
        #i = item.itemData(index)
        if not self.change_enable: return # do nothing while init_items is active
        selection = {}
        i = 0
        for name, value in self.dests.items():
            src_bits, lvl_bits = value[1:3]
            if src_bits == 0 or lvl_bits == 0: continue  # nothing enabled
            source = self.sources[i].currentText()
            if (source != IN_SRC_NONE):
                selection[name] = (source, self.levels[i].currentText())
            i += 1
        if self.is_input:
            print('changed', selection)
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
        self.hex_value.setText('%x'%self.value)
        if self.is_input: save_print(MSG_INPUT_SETTING  % (self.parent.device_name, self.value, get_in_info(self.value)))
        else:             save_print(MSG_OUTPUT_SETTING % (self.parent.device_name, self.value, get_out_info(self.value)))
        # manually insert event into parent event queue as is done by tab_base_classes.py @define_state(MODE_MANUAL, True)
        # data = [function,[args,kwargs]] with function must be a generator, i.e. has to call yield.
        # see blacs/tab_base_classes.py for define_state and mainloop.
        self.parent.event_queue.put(allowed_states=MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=False, data=[self._changed, [[self.value],{}]])

    def _changed(self, parent, value):
        # executed by QT main thread (tab_base_classes.py Tab::mainloop). must be generator (with yield).
        yield (self.parent.queue_work(self.parent.primary_worker, 'onChangeInputs' if self.is_input else 'onChangeOutputs', value))

    def update(self, allow_changes):
        "if allow_changes enable changes otherwise not (grayed out)"
        for src in self.sources:
            src.setEnabled(allow_changes)
        for lvl in self.levels:
            lvl.setEnabled(allow_changes)
        self.hex_value.setEnabled(allow_changes)

    def get_save_data(self, data):
        "save current settings to data dictionary"
        data[self.name] = int(self.value)

    def restore_save_data(self, data):
        "restore saved settings from data dictionary"
        if reset_all: return
        if self.name in data:
            init = get_in_selection(data[self.name]) if self.is_input else get_out_selection(data[self.name])
            #print(init)
            #save_print('FPGA_IO restore_save_data old:', self.init)
            self.init_items(init)
            #save_print('FPGA_IO restore_save_data new:', self.init)

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

        save_print('FPGA_Tab initialise_GUI:', self.device_name)

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

        save_print("'%s': %i racks, %.3fMHz bus rate" % (self.device_name, self.num_racks, self.bus_rate / 1e6))
        save_print(device.properties)
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
        # key = channel name (like AO0.00.0) as given to AnaolgChannel, DigitalChannel
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

        #for key,child in self.all_childs.items():
        #    print('channel',key,'name',child.name)

        # Create the output objects
        save_print('create %i analog  outputs' % (len(ao_list)))
        #save_print('ao_list', ao_list)
        #save_print('ao_prop',ao_prop)
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
        #self.secondary_worker = self.device_name + ADD_WORKER
        #save_print('create worker',self.primary_worker,'args',self.worker_args)
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

        if True:
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
        self.buttons = FPGA_buttons(parent=self, name=self.device_name, update=[], worker_args=self.worker_args)
        toolpalette.insertWidget(0, self.buttons)

        # create list of input selectors
        self.inputs = FPGA_IO(
                    name        = self.device_name+'_inputs',
                    parent      = self,
                    is_input    = True,
                    dests       = in_dests,
                    sources     = in_sources,
                    levels      = in_levels,
                    worker_args = self.worker_args
        )
        toolpalette.insertWidget(1, self.inputs)
        self.buttons.add_update(self.inputs)

        # create list of output selectors
        self.outputs = FPGA_IO(
                    name        = self.device_name+'_outputs',
                    parent      = self,
                    is_input    = False,
                    dests       = out_dests,
                    sources     = out_sources,
                    levels      = out_levels,
                    worker_args = self.worker_args,
                    showHeader  = False
        )
        toolpalette.insertWidget(2, self.outputs)
        self.buttons.add_update(self.outputs)

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
        save_print('FPGA (prim): get_state', result)
        if False and self.is_primary:
            result = yield (self.queue_work("secondary"+ADD_WORKER, 'FPGA_get_board_state'))
            save_print('FPGA (sec): get_state', result)

    @define_state(MODE_MANUAL, True)
    def conn(self, state):
        result = yield(self.queue_work(self.primary_worker, 'FPGA_disconnect'))
        save_print('FPGA: dicsonnect', result)

    @define_state(MODE_BUFFERED, True)
    def start_run(self, notify_queue):
        #save_print('start run (FPGA_tab)')
        # note: this is called only for primary pseudoclock device! and not for other boards!
        #       therefore, the worker must call FPGA_worker::start_run directly from transition_to_buffered.
        #success = yield (self.queue_work(self.primary_worker, 'start_run'))
        #if success:
        if True:
            # update status during run every UPDATE_TIME_MS
            self.statemachine_timeout_add(UPDATE_TIME_MS, self.status_monitor, notify_queue)
            # check of end state in MODE_MANUAL after run finished
            # this way we can update dialog box in GUI after transition_to_manual
            # from worker we have no access to GUI and most likely cannot call back to FPGA_Tab?
            self.event_queue.put(MODE_MANUAL, True, False, [self.status_end, ((),{})], priority=0)
        else:
            raise RuntimeError('Failed to start run')
    
    #@define_state(MODE_BUFFERED, True)
    @define_state(MODE_MANUAL | MODE_BUFFERED | MODE_TRANSITION_TO_BUFFERED | MODE_TRANSITION_TO_MANUAL, True)
    def status_monitor(self, notify_queue):
        # note: I could not find a way to call this for all boards!
        #save_print('status monitor (FPGA_tab)')
        result = yield(self.queue_work(self.primary_worker, 'status_monitor', False))
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
        result, warnings, changed = yield(self.queue_work(self.primary_worker, 'status_monitor', True))
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

        # update changed channels
        changed = {}
        if len(changed) > 0:
            for channel, value in changed.items():
                print(channel, 'changed to', value)
            if False: # TODO: disabled since there is some bug!
                count = len(changed)
                layout = self.get_tab_layout()
                index = layout.count()
                for i in range(index):
                    widget = layout.itemAt(i).widget()
                    if widget is not None:
                        if count == 0: break
                        DO = widget.findChildren(DigitalOutput)
                        for do in DO:
                            if do._DO._hardware_name in changed.keys():
                                do.setStyleSheet('QPushButton {color: black; background-color: red; font-size: 14pt;}')
                                do.clicked.connect(lambda: self.reset_do(do))
                                if --count == 0: break
                        if count == 0: break
                        AO = widget.findChildren(AnalogOutput)
                        for ao in AO:
                            if ao._AO._hardware_name in changed.keys():
                                ao._label.setStyleSheet('QLabel {color: red;}')
                                print([ao._label.text(),ao._AO._hardware_name])
                                ao._spin_widget.valueChanged.connect(lambda:self.reset_ao(ao))
                                if --count == 0: break
                    if count == 0: break

    def reset_do(self, do):
        do.setStyleSheet('QPushButton {color: white; background-color: lightgreen; font-size: 14pt;}')
        #do.clicked.disconnect() this always fails!?

    def reset_ao(self, ao):
        ao._label.setStyleSheet('QLabel { color: black; }')
        #ao._spin_widget.valueChanged.disconnect() this always fails!?
        print('reset_ao', ao._label.text())

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
        if reset_all: return
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

    def program_manual(self, front_panel_values):
        # save actual front panel values
        # TODO: last values are saved in do_list, ao_list and self.front_pane_values and last values of sequence are saved in final_values.
        self.front_panel_values = front_panel_values

        # 1. we first loop through all channels and generate a list of changed digital channels.
        # 2. for changed analog channels we can already generate samples since each channel has its unique address.
        data = []
        time = START_TIME
        sample = [time] + [BIT_NOP_SH]*self.num_racks
        do_IDs = []
        #save_print(self.do_list)
        save_print('program manual final values:', self.final_values)
        #save_print('GUI   values:', front_panel_values)
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
                        # TODO: units conversion? it would be good to have only one function for this!
                        sample[rack+1] = (address<<ADDR_SHIFT)|((int((value*0x7fff) + 0.5)//10) & 0xffff)
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
            if self.simulate:
                save_print("simulate '%s' prg. manual (%i channels)" % (self.device_name, len(data)))
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

                if self.is_primary:
                    # primary board

                    # reset, configure and send data
                    # returns True on success, False on error.
                    if self.simulate:
                        result = True
                    else:
                        result = send_data(self.sock, data, self.bus_rate, config=self.config, ctrl_trg=self.ctrl_in,
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
        return self.final_values

    def abort_transition_to_buffered(self):
        return self.abort_buffered()
    
    def abort_buffered(self):
        # TODO: maybe just call transition_to_manual from here?
        print('abort buffered')
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

        # check if final value of a channel has changed
        self.get_changed_channels()

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
            return [end, self.get_warnings() if end else [], self.get_changed_channels()]
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
        "returns dictionary with changed channels"
        changed = {}
        for key, value in self.final_values.items():
            try:
                if self.front_panel_values[key] != value:
                    print(key, 'changed from', self.front_panel_values[key], 'to', value)
                    changed[key] = value
            except KeyError:
                print(key, 'not in front panel? (ignore)')
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
        sleep(1.0)

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


# testing functions

def test_word():
    "test word_to_value and value_to_word. see Texas Instruments, DAC712 datasheet, July 2009, Table 1, page 13"
    LSB = AO_RESOLUTION # 305uV
    tolerance = 1e-12   # numerical tolerance for word_to_V conversion (we would need only LSB/2)
    tests = {AO_MAX*2     : AO_MAX_WORD,
             AO_MAX+2*LSB : AO_MAX_WORD,
             AO_MAX+1*LSB : AO_MAX_WORD,
             AO_MAX-0*LSB : AO_MAX_WORD,
             AO_MAX-1*LSB : AO_MAX_WORD-1,
             AO_MAX-2*LSB : AO_MAX_WORD-2,
             5.0          : AO_5V_POS_WORD,
             2*LSB        : 2,
             1*LSB        : 1,
             0*LSB        : AO_ZERO_WORD,
             -1*LSB       : 0xffff,
             -2*LSB       : 0xfffe,
             -5.0         : AO_5V_NEG_WORD,
             AO_MIN+2*LSB : AO_MIN_WORD+2,
             AO_MIN+1*LSB : AO_MIN_WORD+1,
             AO_MIN+0*LSB : AO_MIN_WORD,
             AO_MIN-1*LSB : AO_MIN_WORD,
             AO_MIN-2*LSB : AO_MIN_WORD,
             AO_MIN*2     : AO_MIN_WORD}
    volts = np.array(list(tests.keys()))
    words = np.array(list(tests.values()))
    #out_of_range = (volts < AO_MIN) | (volts > AO_MAX)

    #print(V_to_word(volts))
    #print(word_to_V(words))

    # convert directly volts to words. this is what V_to_word does.
    num = 2**16
    ymax = 10.0-(20/num)
    ymin = -10.0
    calc_f  = (np.clip(volts,AO_MIN,AO_MAX)-ymin)*(num-1)/(ymax-ymin)
    calc_i  = np.array(np.round(calc_f)-0x8000,dtype=np.uint16)
    #calc_i = np.array(np.round((volts-AO_MIN)*(2**AO_BITS-1)/(AO_MAX-AO_MIN))-(2**(AO_BITS-1)),dtype=np.uint16)
    error   = calc_i-words
    count = np.count_nonzero(error)
    if count > 0:
        save_print('direct conversion test %i errors! [volt, word, expected, error]' % (count))
        save_print(np.transpose([volts, calc_f, calc_i, words, error]))
        exit()
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
    for volt,word in tests.items():
        calc = V_to_word(volt)
        error = calc - word
        if error != 0:
            save_print('V_to_word scalar error %e V -> %i, expected %i, error %i!' % (volt, calc, word, error))
            exit()
    save_print('V_to_word scalar test ok. (largest error %e)' % (np.max(np.abs(error))))

    # word_to_V vector test
    calc = word_to_V(words)
    error = calc - np.clip(volts, AO_MIN, AO_MAX)
    count = np.count_nonzero(np.abs(error) >= tolerance)
    if count > 0:
        save_print('word_to_V vector %i errors! [word, volt, expected, error]' % (count))
        save_print(np.transpose([words,calc,np.clip(volts,AO_MIN,AO_MAX),error]))
        exit()
    else:
        save_print('word_to_V vector test ok. (largest error %e)' % (np.max(np.abs(error))))

    # word_to_V scalar test
    for volt,word in tests.items():
        calc = word_to_V(word)
        error = calc - np.clip(volt,AO_MIN,AO_MAX)
        if np.abs(error) >= tolerance:
            save_print('word_to_V scalar error %i -> %e, expected %e, error %e!' % (word, calc, volt, error))
            exit()
    save_print('word_to_V scalar test ok. (largest error %e)' % (np.max(np.abs(error))))

    # double conversion test word -> voltage -> word.
    # we test all possible words. voltage cannot be out of range.
    words = np.arange(2**16)
    w2 = V_to_word(word_to_V(words))
    error = w2 - words
    count = np.count_nonzero(error)
    if count > 0:
        save_print('V_to_word(word_to_V) %i errors! largest error %e' % (count, np.max(np.abs(error))))
        exit()
    else:
        save_print('V_to_word(word_to_V) test ok. (largest error %e)' % (np.max(np.abs(error))))

    # double conversion test voltage -> word -> voltage
    # here we take also voltages out of range
    # we test that the found word gives minimum error when converted back to voltage
    volts   = np.arange(AO_MIN-10*LSB, AO_MAX+10*LSB, LSB/10)
    words   = V_to_word(volts)
    words_p = words + 1
    words_n = words - 1
    v2      = word_to_V(words)
    v2_p    = word_to_V(words_p)
    v2_n    = word_to_V(words_n)
    error   = np.abs(v2   - np.clip(volts, AO_MIN, AO_MAX))/LSB
    error_p = np.abs(v2_p - np.clip(volts, AO_MIN, AO_MAX))/LSB
    error_n = np.abs(v2_n - np.clip(volts, AO_MIN, AO_MAX))/LSB
    if np.count_nonzero(error > 0.5) > 0:
        count = np.count_nonzero(error > 0.5)
        save_print('word_to_V(V_to_word) %i errors! largest error %.3f LSB' % (count, np.max(error)))
        exit()
    elif np.count_nonzero(error > error_p) > 0:
        count = np.count_nonzero(error > error_p)
        save_print('word_to_V(V_to_word) %i x error(word) > error(word+1)!' % (count))
        exit()
    elif np.count_nonzero(error > error_n) > 0:
        count = np.count_nonzero(error > error_n)
        save_print('word_to_V(V_to_word) %i x error(word) > error(word-1)!' % (count))
        exit()
    else:
        save_print('word_to_V(V_to_word) test ok. (largest error %.3f LSB ok)' % (np.max(error)))


if __name__ == '__main__':
    # test word_to_V and V_to_word
    test_word()

    # TODO: add unit conversion test
