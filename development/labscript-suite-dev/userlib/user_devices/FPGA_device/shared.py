#!/usr/bin/python
# shared data for FPGA_device.
# saves constants, settings and shared functions in a single file and avoids circular imports
import numpy as np

# default connection
PRIMARY_IP   = '192.168.1.130'
SECONDARY_IP = '192.168.1.131'
DEFAULT_PORT = '49701'

SOCK_TIMEOUT        = 5.0                   # timeout for send_recv_data in seconds. I see sometimes very long responds time. maybe USB-Ethernet-adapter?
SOCK_TIMEOUT_SHORT  = 1.0                   # timeout for init_connection in seconds. this is shorter for fast tests withouts boards.

ADD_WORKER  = '_worker'                     # worker name = board name + ADD_WORKER
AO_NAME     = 'Analog Outputs'              # GUI button name analog outputs
DO_NAME     = 'Digital Outputs'             # GUI button name digital outputs
DDS_NAME    = 'DDS'                         # GUI button name DDS outputs
FPGA_NAME   = 'FPGA board'                  # GUI button name FPGA board

# FPGA settings
MAX_FPGA_RATE   = 20e6                      # maximum bus output rate of FPGA in Hz (limited by strobe)
MAX_RACKS       = 2                         # 2 racks can share one clockline

# bus data structure
DATA_BITS       = 16                        # number of data bits
DATA_SHIFT      = 0                         # data offset
ADDR_BITS       = 7                         # typically 7, but also 8 is possible (if your bus supports)
ADDR_SHIFT      = DATA_BITS                 # first bit of address = number of data bits
ADDR_MASK       = ((1<<ADDR_BITS)-1)
ADDR_MAX        = ADDR_MASK                 # largest possible address
ADDR_MASK_SH    = np.uint32(ADDR_MASK<<ADDR_SHIFT) # address mask (7 or 8 bits)
DATA_MASK       = np.uint32((1<<DATA_BITS)-1) # data field mask (16 bits)
DATA_ADDR_MASK  = DATA_MASK|ADDR_MASK_SH    # combined data field + address mask (23 or 24 bits)

# display/debug settings
ALWAYS_SHOW     = False                     # if true always shows first and last MAX_SHOW/2 data
MAX_SHOW        = 20                        # maximum number of samples until which data is shown

# for debugging set True to check if back-conversion of DAC/freq/amp/phase tuning word is correct
BACK_CONVERT = True

# device types (used for ID)
TYPE_board      = 0
TYPE_SP         = 1
TYPE_DO         = 2
TYPE_AO         = 3
TYPE_DDS        = 4

# default values are inserted automatically by labscript for times before channel is used
# these values are masked below and are not sent to boards.
# to distinguish between user inserted values and auto-inserted we keep them outside valid range.
SP_INVALID_VALUE = 0 # special output device (virtual)
#AO_INVALID_VALUE = 2*default_ao_props['min']-1.0 # TODO: with unit conversion this might be a valid user-inserted value!? I think nan is not possible here. maybe use np.nan?
AO_INVALID_VALUE = np.finfo(np.float64).min
AO_DEFAULT_VALUE = 0
DO_INVALID_VALUE = 2
DO_DEFAULT_VALUE = False

# channel property names
PROP_UNIT               = 'base_unit'
PROP_MIN                = 'min'
PROP_MAX                = 'max'
PROP_STEP               = 'step'
PROP_DEC                = 'decimals'

# analog properties
PROP_UNIT_V             = 'V'
PROP_UNIT_A             = 'A'

# DDS channel property names
PROP_UNIT_MHZ       = 'MHz'
PROP_UNIT_DBM       = 'dBm'
PROP_UNIT_DEGREE    = 'deg'     # TODO: use degree symbol (unicode 0xb0) but I think on Windows does not work?

# sub-channel entry used also for final_values and addr_offset.
# must be the same as DDSQuantity.frequency/amplitude/phase.connection in labscript.py
DDS_CHANNEL_FREQ    = 'freq'
DDS_CHANNEL_AMP     = 'amp'
DDS_CHANNEL_PHASE   = 'phase'

# set this to True when you have a problem to start BLACS. resets all stored values to default.
# can happen when changing values saved to file.
# can happen when changing values saved to file.
reset_all = False

# if configure all registers each run
# for latest firmware this is not anymore needed
CONFIG_EACH_RUN = False

# if False use latest stable version from 24/1/2023 (version used in Yb-Trieste and Firenze Sr-Tweezers)
# if True use new development version from 20/12/2024 (IBK).
# TODO: at the moment only use_prelim_version = True works!
#       There were too many changes from old version but as soon as I have one day time I'll fix this.
#       if you need to work with the older firmware check my github for the 2023 version.
use_prelim_version = True

# default special data bits
BIT_NOP             = 31                        # no operation bit. TODO: this can be configured by software and might be None!
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

# if True save CRC for all channels into hd5 and check in worker
# notes:
# - data with BIT_NOP_SH might be counted wrong?
# - the result depends on the order of instructions!
#   therefore, when this is enabled instructions must be inserted with increasing time,
#   otherwise worker will raise the error that CRC is not the same!
CRC_CHECK = False

# CRC-32
# https://en.wikipedia.org/wiki/Cyclic_redundancy_check#CRC-32_algorithm
# reversed, shift-right
# same implementation as zlib.crc32 (verified with CRC.test below)
poly = 0xedb88320
def CRC32_generate_table():
    table = np.empty(shape=(256,), dtype=np.uint32)
    for i in range(256):
        d   = np.uint32(i)
        crc = np.uint32(0)
        for bit in range(8):
            if (d ^ crc) & 1:
                crc = (crc >> 1) ^ poly
            else:
                crc >>= 1
            d >>= 1
        table[i] = crc
    return table

def CRC32_8(data8, table, crc = np.uint32(0xffffffff)):
    # data must be bytes or np.uint8
    for d in data8:
        crc = table[(crc ^ (d & 0xff)) & 0xff] ^ (crc >> 8)
    return crc

def CRC32_32(data32, table, crc = np.uint32(0xffffffff)):
    # data must be np.array of uint32.
    # we assume MSB first (little endian).
    for d in data32:
        for i in range(0, 32, 8):
            crc = table[(crc ^ ((d>>(24-i)) & 0xff)) & 0xff] ^ (crc >> 8)
    return crc

class CRC:
    def __init__(self, data=None):
        self._table = CRC32_generate_table()
        self._crc = 0xffffffff
        if data is not None:
            self._crc = CRC32_32(np.array(data, dtype=np.uint32), self._table, self._crc)

    def __str__(self):
        return ('0x%08x' % self._crc)

    def value(self):
        return self._crc

    def __call__(self, data):
        self._crc = CRC32_32(data, self._table, self._crc)
        return self._crc

    def test(self):
        # verify code with zlib.crc32
        import zlib
        from labscript import LabscriptError
        tests = [b'hello-world',b'1234',b'this is a test',b'\x00\x01\x02\x03\x04\x05\x06\x07']
        for t in tests:
            if len(t) % 4 != 0:
                t += b'\x00'*(4-len(t)%4)
            z = zlib.crc32(t)
            crc8 = crc32 = 0xffffffff
            crc8 = CRC32_8(t, self._table, crc8) ^ 0xffffffff
            num = int(len(t)//4)
            t32 = np.empty(shape=(num,), dtype=np.uint32)
            for i in range(num): # this assumes MSB first
                t32[i] = (t[i*4] << 24) | (t[i*4+1] << 16) | (t[i*4+2] << 8) | t[i*4+3]
                #print(i, '0x%08x' % t32[i])
            crc32 = CRC32_32(t32, self._table, crc32) ^ 0xffffffff
            if crc8 == z and crc32 == z:
                print("zlib CRC %s = 0x%08x (ok)" % (t, z))
            else:
                raise LabscriptError("zlib CRC %s = 0x%08x != 0x%08x != 0x%08x (error)" % (t, crc8, crc32, z))

def show_data(data, info=None, bus_rate=None):
    if info is not None: print(info)
    if len(data) > MAX_SHOW:
        index = [[0, int(MAX_SHOW / 2)], [len(data) - int(MAX_SHOW / 2), len(data)]]
    else:
        index = [[0, len(data)]]
    if data.shape[1] >= 3:
        print('   sample      time   strobe_0   strobe_1')
    else:
        print('   sample      time       data')
    for i_rng in index:
        if data.shape[1] >= 3:
            for i in range(i_rng[0], i_rng[1]):
                print('%9i %9u 0x%08x 0x%08x' % (i, data[i, 0], data[i, 1], data[i, 2]))
        else:
            for i in range(i_rng[0], i_rng[1]):
                print('%9i %9u 0x%08x' % (i, data[i, 0], data[i, 1]))
    if len(data) > 1:
        if bus_rate is None:
            times = data[:, 0]
            min_step = np.min(times[1:] - times[0:-1])
            print('%i samples, smallest time step %.3e ticks' % (len(data), min_step))
            print('first time %f, second time %e, last time %f\n' % (times[0], times[1], times[-1]))
        else:
            times = data[:, 0]/bus_rate
            min_step = np.min(times[1:] - times[0:-1])
            print('%i samples, smallest time step %.3e seconds (%.6f MHz)' % (len(data), min_step, (1e-6 / min_step)))
            print('first time %f, second time %e, last time %f\n' % (times[0], times[1], times[-1]))
    else:
        print('%i samples\n' % (len(data)))
