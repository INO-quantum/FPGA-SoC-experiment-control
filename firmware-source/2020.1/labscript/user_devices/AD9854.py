#!/usr/bin/python

# labscript definition file for DDS AD9854
# creates the data required for Innbruck implementation

# created 30/8/2024 by Andi
# last change 2/9/2024 by Andi

import numpy as np

from user_devices.FPGA_device.labscript_device import (
    DDS_generic,
    DDS_FREQ_INVALID_VALUE, DDS_AMP_INVALID_VALUE, DDS_PHASE_INVALID_VALUE,
    DDS_CHANNEL_FREQ, DDS_CHANNEL_AMP, DDS_CHANNEL_PHASE,
)

# system clock frequency in Hz
SYSCLK              = 300e6     # TODO: to be checked!

# address bits
ADDR_BITS           = 6
ADDR_MASK           = (1<<ADDR_BITS)-1
ADDR_SHIFT          = 18

# frequency word bits
FREQ_BITS           = 48
FREQ_MASK           = (1<<FREQ_BITS)-1

# amplitude word bits
AMP_BITS            = 12
AMP_MASK            = (1<<AMP_BITS)-1

# phase word bits
PHASE_BITS          = 14
PHASE_MASK          = (1<<PHASE_BITS)-1

# DDS register
REG_BITS            = 6
REG_MASK            = (1<<REG_BITS)-1
REG_SHIFT           = 0

# DDS register value
VALUE_BITS          = 8
VALUE_MASK          = (1<<VALUE_BITS)-1
VALUE_SHIFT         = 8

# control bits
FSK                 = 1 << 6
OSK                 = 1 << 7
RESET               = 0 << 16
WRITE               = 1 << 16
WRITE_AND_UPDATE    = 2 << 16

# amplitude limits
DB_MIN              = -30
DB_MAX              = 0

# TODO: this needs to be done!
# amplitude calibration
# this assumes output voltage is linear with amplitude tuning word.
amin                = 1
amax                = (1<<AMP_BITS)-1
dBm_min             = -30               # measured power in dBm at amplitude word = amin
dBm_max             = 0                 # measured power in dBm at amplitude word = amax
umin                = 10**(dBm_min/20)
umax                = 10**(dBm_max/20)

class AD9854(DDS_generic):
    # description
    description = 'DDS AD9854'

    # minimum time between commands in seconds
    min_time_step = 1e-6

    # data word type
    dtype = np.uint32

    # frequency limits in Hz
    freq_limits = (0,135e6)

    # amplitude limits in dBm
    amp_limits = (DB_MIN, DB_MAX)

    def __init__(self, name, parent_device, connection, **kwargs):
        "check input and create DDS object"
        try:
            self.address = int(connection, 0)
        except ValueError:
            raise LabscriptError("%s '%s' address %s is invalid! give address as decimal or hexadecimal (with '0x') number." % (self.description, name, connection))
        if self.address % 4 != 0:
            raise LabscriptError("%s '%s' address %s (%i) must be integer multiple of 4!" % (self.description, name, self.connection, self.address))
        DDS_generic.__init__(self, name, parent_device, connection, **kwargs)

        self.frequency.default_value = DDS_FREQ_INVALID_VALUE
        self.amplitude.default_value = DDS_AMP_INVALID_VALUE
        self.phase.default_value     = DDS_PHASE_INVALID_VALUE
        self.frequency.final_time    = self.frequency.final_value = None
        self.amplitude.final_time    = self.amplitude.final_value = None
        self.phase.final_time        = self.phase.final_value = None

    @staticmethod
    def init_hardware(properties):
        """
        init DDS.
        called once from worker on startup.
        properties contain channel properties. we need only address.
        return None or numpy array of np.uint32 to be put on the bus for initialization.
        """
        # we just need to reset the DDS
        return AD9854.reset_hardware(properties)

    @staticmethod
    def reset_hardware(properties):
        """
        reset DDS.
        properties contain channel properties. we need only address.
        return None or numpy array of np.uint32 to be put on the bus for initialization.
        """
        address = (properties['address'] & ADDR_MASK) << ADDR_SHIFT
        return np.array([
                address|RESET                                                 ,     # master reset
                address|WRITE           |(0x10<<VALUE_SHIFT)|(0x1D<<REG_SHIFT),     # Comperator power down
                address|WRITE           |(0x20<<VALUE_SHIFT)|(0x1C<<REG_SHIFT),     # Bypass PLL
                address|WRITE_AND_UPDATE|(0x60<<VALUE_SHIFT)|(0x20<<REG_SHIFT)      # Bypass inv sinc; OSK enable
                ], dtype=AD9854.dtype)

    @staticmethod
    def shutdown_hardware(properties):
        """
        shutdown DDS.
        called once from worker on shutdown.
        properties contain channel properties. we need only address.
        return None or numpy array of np.uint32 to be put on the bus for initialization.
        """
        # nothing to be done or should we reset DDS but then its off?
        return None

    @staticmethod
    def to_words(properties, value, update=True):
        sub_channel = properties['channel']
        if sub_channel == DDS_CHANNEL_FREQ:
            return AD9854.freq_to_words(properties, value, update)
        elif sub_channel == DDS_CHANNEL_AMP:
            return AD9854.amp_to_words(properties, value, update)
        elif sub_channel == DDS_CHANNEL_PHASE:
            return AD9854.phase_to_words(properties, value, update)
        else:
            raise LabscriptError("sub channel %i does not exist!" % (sub_channel))

    @staticmethod
    def freq_to_words(properties, frequency, update=True):
        """
        converts frequency in Hz to data words to be put on bus.
        properties contain channel properties. we need only address.
        if update = True updates output, otherwise not (i.e. want to write more data)
        return None or numpy array of np.uint32 to be put on the bus for initialization.
        """
        address = (properties['address'] & ADDR_MASK) << ADDR_SHIFT
        f = np.round((np.clip(frequency, AD9854.freq_limits[0], AD9854.freq_limits[1])*(1<<FREQ_BITS))/SYSCLK).astype(AD9854.dtype) & FREQ_MASK
        f = [(f>>i) & VALUE_MASK for i in range(0, FREQ_BITS, VALUE_BITS)]
        write_last = WRITE_AND_UPDATE if update else WRITE
        return np.array([
                address|WRITE     |(f[5]<<VALUE_SHIFT)|(0x04<<REG_SHIFT),
                address|WRITE     |(f[4]<<VALUE_SHIFT)|(0x05<<REG_SHIFT),
                address|WRITE     |(f[3]<<VALUE_SHIFT)|(0x06<<REG_SHIFT),
                address|WRITE     |(f[2]<<VALUE_SHIFT)|(0x07<<REG_SHIFT),
                address|WRITE     |(f[1]<<VALUE_SHIFT)|(0x08<<REG_SHIFT),
                address|write_last|(f[0]<<VALUE_SHIFT)|(0x09<<REG_SHIFT)
                ], dtype=AD9854.dtype)

    @staticmethod
    def amp_to_words(properties, amplitude, update=True):
        """
        converts amplitude in dBm to data words to be put on bus.
        properties contain channel properties. we need only address.
        if update = True updates output, otherwise not (i.e. want to write more data)
        return None or numpy array of np.uint32 to be put on the bus for initialization.
        this uses amplitude calibration assuming output voltage is linear with tuning word.
        """
        address = (properties['address'] & ADDR_MASK) << ADDR_SHIFT
        uval = 10**(np.clip(amplitude, AD9854.amp_limits[0], AD9854.amp_limits[1])/20)
        a = round(((uval - umin)*amax + (umax - uval)*amin)/(umax-umin)) & FREQ_MASK
        a = [(a>>i) & VALUE_MASK for i in range(0, AMP_BITS, VALUE_BITS)]
        write_last = WRITE_AND_UPDATE if update else WRITE
        return np.array([
                address|WRITE     |(a[1]<<VALUE_SHIFT)|(0x26<<REG_SHIFT),
                address|write_last|(a[0]<<VALUE_SHIFT)|(0x27<<REG_SHIFT)
                ], dtype=AD9854.dtype)

    @staticmethod
    def phase_to_words(properties, phase, update=True):
        """
        converts phase in degree to data words to be put on bus.
        properties contain channel properties. we need only address.
        if update = True updates output, otherwise not (i.e. want to write more data)
        return None or numpy array of np.uint32 to be put on the bus for initialization.
        """
        address = (properties['address'] & ADDR_MASK) << ADDR_SHIFT
        phase = phase % 360.0
        phase = round((phase/360.0)*((1<<PHASE_BITS)-1)) & PHASE_MASK
        p = [(phase>>i) & VALUE_MASK for i in range(0, PHASE_BITS, VALUE_BITS)]
        write_last = WRITE_AND_UPDATE if update else WRITE
        return np.array([
                address|WRITE     |(p[1]<<VALUE_SHIFT)|(0x00<<REG_SHIFT),
                address|write_last|(p[0]<<VALUE_SHIFT)|(0x01<<REG_SHIFT)
                ], dtype=AD9854.dtype)

    def setfreq(self, t, value, update=True):
        "set frequency in Hz at given time in seconds"
        # clip frequency to limits
        if   value < self.freq_limits[0]: value = self.freq_limits[0]
        elif value > self.freq_limits[1]: value = self.freq_limits[1]
        # save raw data into individual instructions
        raw_data = self.freq_to_words(self.properties, value, update)
        for data in raw_data:
            self.frequency.add_instruction(t, data)
            t += self.min_time_step
        # save final time and value
        if self.frequency.final_time is None or t > self.frequency.final_time:
            self.frequency.final_time  = t
            self.frequency.final_value = value

    def setamp(self, t, value, update=True):
        "set amplitude  in dBm at given time in seconds"
        # clip amplitude to limits
        if   value < self.amp_limits[0]: value = self.amp_limits[0]
        elif value > self.amp_limits[1]: value = self.amp_limits[1]
        # save raw data into individual instructions
        raw_data = self.amp_to_words(self.properties, value, update)
        for data in raw_data:
            self.amplitude.add_instruction(t, data)
            t += self.min_time_step
        # save final time and value
        if self.amplitude.final_time is None or t > self.amplitude.final_time:
            self.amplitude.final_time  = t
            self.amplitude.final_value = value

    def setphase(self, t, value, update=True):
        "set phase in degree at given time in seconds"
        # map phase into range 0-360°
        value = value % 360.0
        # save raw data into individual instructions
        raw_data = self.phase_to_words(self.properties, value, update)
        for data in raw_data:
            self.phase.add_instruction(t, data)
            t += self.min_time_step
        # save final time and value
        if self.phase.final_time is None or t > self.phase.final_time:
            self.phase.final_time  = t
            self.phase.final_value = value

