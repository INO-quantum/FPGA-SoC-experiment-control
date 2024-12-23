#!/usr/bin/python

# labscript definition file for generic DDS used by FPGA_device
# you can use a derived class for your specific hardware

# created 30/8/2024 by Andi
# last change 5/9/2024 by Andi

import numpy as np

from labscript import ( DDSQuantity, LabscriptError )
from .shared import (
    PROP_UNIT, PROP_MIN, PROP_MAX, PROP_STEP, PROP_DEC,
    PROP_UNIT_MHZ, PROP_UNIT_DBM, PROP_UNIT_DEGREE,
    DDS_CHANNEL_FREQ, DDS_CHANNEL_AMP, DDS_CHANNEL_PHASE,
    CRC_CHECK, CRC, show_data, BACK_CONVERT,
    DATA_BITS, DATA_MASK, DATA_SHIFT, ADDR_BITS, ADDR_MASK, ADDR_SHIFT, ADDR_MAX,
    BIT_NOP_SH,
)

# DDS address offsets
DDS_FREQ_ADDR_OFFSET        = 0
DDS_AMP_ADDR_OFFSET         = 1
DDS_PHASE_ADDR_OFFSET       = 2

# default and invalid values in Hz, dBm, degree
# these values do not need to be within limits of device.
# device limits are used only when programming device.
DDS_FREQ_DEFAULT_VALUE      = 0.0
DDS_AMP_DEFAULT_VALUE       = -60.0
DDS_PHASE_DEFAULT_VALUE     = 0.0
DDS_FREQ_INVALID_VALUE      = -1
DDS_AMP_INVALID_VALUE       = -1000
DDS_PHASE_INVALID_VALUE     = -1000

class DDS_generic(DDSQuantity):
    description = 'generic DDS'

    # returned data type from to_words
    raw_dtype           = np.uint32

    # DDS specifics
    SYSCLK              = 1000e6
    FREQ_BITS           = 48
    FREQ_MASK           = (1<<FREQ_BITS)-1
    AMP_BITS            = 14
    AMP_MASK            = (1<<AMP_BITS)-1
    PHASE_BITS          = 12
    PHASE_MASK          = (1<<PHASE_BITS)-1

    # DDS uses address range [address ... address + (2**ADDR_RNG_BITS)-1]
    ADDR_RNG_BITS       = 2
    ADDR_RNG_MASK       = ((1<<(ADDR_BITS-ADDR_RNG_BITS))-1)<<ADDR_RNG_BITS

    # reset data
    # we assume there is a reset bit above data + address bits
    RESET               = 1<<(DATA_BITS+ADDR_BITS)

    # amplitude calibration
    # at amplitude tuning word A0,A1 measured output power is DBM0,DBM1 in dBm.
    # this assumes output voltage is linear with amplitude tuning word.
    A0                  = 1
    A1                  = AMP_MASK
    DBM0                = -30
    DBM1                = 0
    U0                  = 10**(DBM0 / 20)
    U1                  = 10**(DBM1 / 20)
    DBM_MIN             = 20.0*np.log10((       0*(U1-U0) + U0*A1 - U1*A0)/(A1 - A0))
    DBM_MAX             = 20.0*np.log10((AMP_MASK*(U1-U0) + U0*A1 - U1*A0)/(A1 - A0))

    # frequency limits in Hz
    freq_limits         = (0, 500e6)

    # amplitude limits in dBm, limited by calibration.
    amp_limits          = (DBM_MIN, DBM_MAX)

    # phase limits in degree
    phase_limits        = (0, 360)

    # sub-channel default value is inserted by labscript when no user input was done
    # we set this in add_device to invalid value to distinguish if its inserted by user or by labscript
    # the true default value is saved in sub-channel properties.
    default_value_freq  = DDS_FREQ_DEFAULT_VALUE
    default_value_amp   = DDS_AMP_DEFAULT_VALUE
    default_value_phase = DDS_PHASE_DEFAULT_VALUE
    invalid_value_freq  = DDS_FREQ_INVALID_VALUE
    invalid_value_amp   = DDS_AMP_INVALID_VALUE
    invalid_value_phase = DDS_PHASE_INVALID_VALUE

    # optional address offset added for each sub-channel if not None
    addr_offset = {DDS_CHANNEL_FREQ : DDS_FREQ_ADDR_OFFSET ,
                   DDS_CHANNEL_AMP  : DDS_AMP_ADDR_OFFSET  ,
                   DDS_CHANNEL_PHASE: DDS_PHASE_ADDR_OFFSET}

    def __init__(self, name, parent_device, connection, digital_gate={},
                 freq_limits=None, freq_conv_class=None, freq_conv_params={},
                 amp_limits=None, amp_conv_class=None, amp_conv_params={},
                 phase_limits=None, phase_conv_class=None, phase_conv_params = {},
                 call_parents_add_device=True, **kwargs):

        # init DDS. call_parents_add_device is ignored.
        DDSQuantity.__init__(self, name, parent_device, connection, digital_gate,
                freq_limits=None, freq_conv_class=freq_conv_class, freq_conv_params=freq_conv_params,
                amp_limits=None, amp_conv_class=amp_conv_class, amp_conv_params=amp_conv_params,
                phase_limits=None, phase_conv_class=phase_conv_class, phase_conv_params=phase_conv_params,
                call_parents_add_device=True, **kwargs)

        # check valid address
        address = self.properties['address']
        if address & ADDR_MASK != address:
            raise LabscriptError("%s '%s' address 0x%02x (%i) outside range 0..0x%02x (%i)!" % (self.description, name, address, address, ADDR_MAX, ADDR_MAX))
        if address & self.ADDR_RNG_MASK != address:
            raise LabscriptError("%s '%s' address 0x%02x (%i) invalid! masked address 0x%02x must be the same! (mask 0x%02x)" % (self.description, name, address, address, address & self.ADDR_RNG_MASK, self.ADDR_RNG_MASK))

        # unit conversion is not done here.

        # set limits when given
        # we do not give limits to labscript since this conflicts with default_value.
        # therefore, we enforce limits in setfreq/amp/phase functions.
        # TODO: would be more efficient when labscripb could take care of this.
        if freq_limits is not None:
            if freq_limits[0] < self.freq_limits[0] or freq_limits[1] > self.freq_limits[1]:
                raise LabscriptError("%s frequency limits [%s,%s] must be in range [%s,%s]" % (self.name, str(freq_limits[0]), str(freq_limits[1]), str(self.freq_limits[0]), str(self.freq_limits[1])))
            self.freq_limits  = freq_limits
        if amp_limits is not None:
            if amp_limits[0] < self.amp_limits[0] or amp_limits[1] > self.amp_limits[1]:
                raise LabscriptError("%s amplitude limits [%s,%s] must be in range [%s,%s]" % (self.name, str(amp_limits[0]), str(amp_limits[1]), str(self.amp_limits[0]), str(self.amp_limits[1])))
            self.amp_limits   = amp_limits
        if phase_limits is not None:
            if phase_limits[0] < self.phase_limits[0] or phase_limits[1] > self.phase_limits[1]:
                raise LabscriptError("%s phase limits [%s,%s] must be in range [%s,%s]" % (self.name, str(phase_limits[0]), str(phase_limits[1]), str(self.phase_limits[0]), str(self.phase_limits[1])))
            self.phase_limits = phase_limits

        # self.default value is automatically inserted by labscript when no user provided values.
        # device-specific limits are saved into properties.
        # dummy conversion function _to_word is called for each sub-channel from generate_code.
        # final_time is used to find final value of each sub-channel.
        # frequency
        self.frequency.default_value = self.invalid_value_freq
        self.frequency.properties    = {'address'    : address if self.addr_offset is None else address + self.addr_offset[DDS_CHANNEL_FREQ],
                                        'sub-channel': DDS_CHANNEL_FREQ,
                                        'limits'     : self.freq_limits,
                                        'blacs_props': {PROP_UNIT: PROP_UNIT_MHZ,
                                                        PROP_MIN:  self.freq_limits[0]/1e6,
                                                        PROP_MAX:  self.freq_limits[1]/1e6,
                                                        PROP_STEP: 1.0,
                                                        PROP_DEC : 6 }
                                       }
        self.frequency.to_words      = self._to_words
        self.frequency.final_time    = None
        # amplitude
        self.amplitude.default_value = self.invalid_value_amp
        self.amplitude.properties    = {'address'    : address if self.addr_offset is None else address + self.addr_offset[DDS_CHANNEL_AMP],
                                        'sub-channel': DDS_CHANNEL_AMP,
                                        'limits'     : self.amp_limits,
                                        'blacs_props': {PROP_UNIT: PROP_UNIT_DBM,
                                                        PROP_MIN:  self.amp_limits[0],
                                                        PROP_MAX:  self.amp_limits[1],
                                                        PROP_STEP: 1.0,
                                                        PROP_DEC : 3 }
                                       }
        self.amplitude.to_words      = self._to_words
        self.amplitude.final_time    = None
        # phase
        self.phase.default_value     = self.invalid_value_phase
        self.phase.properties        = {'address'    : address if self.addr_offset is None else address + self.addr_offset[DDS_CHANNEL_PHASE],
                                        'sub-channel': DDS_CHANNEL_PHASE,
                                        'limits'     : self.phase_limits,
                                        'blacs_props': {PROP_UNIT: PROP_UNIT_DEGREE,
                                                        PROP_MIN:  self.phase_limits[0],
                                                        PROP_MAX:  self.phase_limits[1],
                                                        PROP_STEP: 1.0,
                                                        PROP_DEC : 3 }
                                       }
        self.phase.to_words          = self._to_words
        self.phase.final_time        = None

        # we have to save final values for all sub-channels in MHz, dBm, degree
        self.final_values = {DDS_CHANNEL_FREQ : DDS_FREQ_DEFAULT_VALUE/1e6,
                             DDS_CHANNEL_AMP  : DDS_AMP_DEFAULT_VALUE,
                             DDS_CHANNEL_PHASE: DDS_PHASE_DEFAULT_VALUE}

        # save all properties into h5 file
        # this way worker and runviewer have access to it.
        for sub in [self.frequency, self.amplitude, self.phase]:
            for key, value in sub.properties.items():
                sub.set_property(key, value, 'connection_table_properties')

        if CRC_CHECK:
            # init CRC for testing
            self.crc = CRC([address])
            # verify CRC is consistent with zlib.crc32
            #CRC().test()

    @classmethod
    def init_hardware(cls, properties):
        """
        init DDS.
        called once from worker on startup.
        properties contain DDS properties.
        return None or numpy array of np.uint32 to be put on the bus for initialization.
        """
        # we just need to reset the DDS
        return cls.reset_hardware(properties)

    @classmethod
    def reset_hardware(cls, properties):
        """
        reset DDS.
        properties contain DDS properties.
        return None or numpy array of np.uint32 to be put on the bus for initialization.
        """
        address = np.array((properties['address'] & ADDR_MASK) << ADDR_SHIFT, dtype=cls.raw_dtype)
        data = np.array([address|cls.RESET], dtype=cls.raw_dtype)
        return data

    @classmethod
    def shutdown_hardware(cls, properties):
        """
        shutdown DDS.
        called once from worker on shutdown.
        properties contain DDS properties.
        return None or numpy array of np.uint32 to be put on the bus for initialization.
        """
        # nothing to be done or should we reset DDS but then its off?
        return None

    @classmethod
    def freq_to_words(cls, properties, frequencies, **args):
        """
        converts frequencies in Hz to raw data words for the specific device.
        properties  = sub-channel properties
        frequencies = numpy array of frequencies in Hz
        returns numpy array of type self.raw_dtype of one or several words.
        in a derived class define this function for your hardware.
        """
        address = cls.raw_dtype((properties['address'] & ADDR_MASK) << ADDR_SHIFT)
        freq_limits = properties['limits']
        df = cls.SYSCLK/(1<<cls.FREQ_BITS)
        mask = (frequencies != cls.invalid_value_freq)
        f = np.where(mask, frequencies, BIT_NOP_SH)
        f = np.clip(f, freq_limits[0], freq_limits[1])
        ftw = np.round(f/df).astype(np.uint64) & np.uint64(cls.FREQ_MASK)
        raw_data = np.array([address | (((ftw >> np.uint64(i)).astype(cls.raw_dtype) & DATA_MASK) << DATA_SHIFT) for i in range(0, cls.FREQ_BITS, DATA_BITS)], dtype=cls.raw_dtype).flatten(order='F')
        if BACK_CONVERT and np.any(mask): # check back conversion
            val = cls.words_to_freq(properties, np.array(range(len(raw_data))), raw_data)
            errors = np.abs(val[1] - f[mask]/1e6)
            max_error = 0.5*cls.SYSCLK/((1<<cls.FREQ_BITS)-1)
            imax = np.argmax(errors)
            #print('%s f = %.6f MHz: FTW = 0x%x -> %.6f MHz' % (cls.__name__, frequency[mask][imax]/1e6, ftw[mask][imax], val[1][imax]))
            if errors[imax] > max_error:
                raise LabscriptError("%s freq_to_words: %i frequencies out of tolerance! max. error for %.6f MHz != %.6f MHz" % (cls.__name__, np.count_nonzero(errors > max_error), val[1][imax], f[mask][imax]/1e6))
        return raw_data

    @classmethod
    def words_to_freq(cls, properties, times, words, **args):
        """
        converts np.array of words into frequency in Hz.
        properties = sub-channel properties
        times      = np.array of times (ticks or seconds)
        words      = np.array of cls.raw_dtype
        returns [times, values] as np.array of times.dtype and np.float64 of converted words.
        the returned number of times, values might be different than the number of input times, words.
        in a derived class define this function for your hardware.
        implementation specific:
        - selects only words with device sub-channel address.
        - selected words length must be integer multiple of 3 = FREQ_BITS/DATA_BITS otherwise raises error
        - assumes that words are properly aligned, i.e. first 3 words correspond to first frequency.
        - returns every 3rd selected time starting with first and corresponding frequency
        """
        address = cls.raw_dtype(properties['address'] & ADDR_MASK)
        mask = (((words >> ADDR_SHIFT) & ADDR_MASK) == address)
        w = words[mask]
        if len(w) % 3 != 0:
            show_data(np.array([times, words]))
            raise LabscriptError("words_to_freq requires integer multiple of 3 words but %i obtained!" % (len(w)))
        values = ((np.uint64(w[0::3] & DATA_MASK)               ) |
                  (np.uint64(w[1::3] & DATA_MASK)<< DATA_BITS   ) |
                  (np.uint64(w[2::3] & DATA_MASK)<<(DATA_BITS*2)) ) & cls.FREQ_MASK
        #print('FTW = ', ['%x'%v for v in values])
        df = cls.SYSCLK/(1<<cls.FREQ_BITS)
        values = (df*values)/1e6
        return [times[mask][::3], values]

    @classmethod
    def amp_to_words(cls, properties, amplitudes, **args):
        """
        converts amplitudes in dBm to raw data words for the specific device.
        properties = sub-channel properties
        amplitude  = numpy array of amplitudes in dBm
        returns np.array of type self.raw_dtype of one or several words.
        in a derived class define this function for your hardware.
        here we use amplitude calibration to calculate amplitude tuning word.
        """
        address = cls.raw_dtype((properties['address'] & ADDR_MASK) << ADDR_SHIFT)
        amp_limits = properties['limits']
        mask = (amplitudes != cls.invalid_value_amp)
        a = np.where(mask, amplitudes, BIT_NOP_SH)
        a = np.clip(a, amp_limits[0], amp_limits[1])
        uval = 10**(a/20.0)
        atw = np.round(((uval - cls.U0)*cls.A1 + (cls.U1 - uval)*cls.A0)/(cls.U1-cls.U0)).astype(dtype=cls.raw_dtype) & cls.AMP_MASK
        raw_data = np.array([address | (((atw >> i) & DATA_MASK) << DATA_SHIFT) for i in range(0, cls.AMP_BITS, DATA_BITS)], dtype=cls.raw_dtype).flatten(order='F')
        if BACK_CONVERT and np.any(mask): # check back conversion
            val = cls.words_to_amp(properties, np.arange(len(raw_data)), raw_data)
            errors    = np.abs(val[1] - a[mask])
            max_error = (cls.DBM_MAX-cls.DBM_MIN)/((1<<cls.AMP_BITS)-1)
            imax      = np.argmax(errors)
            #print('%s a = %.6f dBm: ATW = 0x%x -> %.6f dBm' % (cls.__name__, amplitude[mask][imax], atw[mask][imax], val[1][imax]))
            if errors[imax] > max_error:
                raise LabscriptError("%s amp_to_words: %i amplitudes out of tolerance! max. error for %.6f dBm != %.6f dBm" % (cls.__name__, np.count_nonzero(errors > max_error), val[1][imax], a[mask][imax]))
        return raw_data

    @classmethod
    def words_to_amp(cls, properties, times, words, **args):
        """
        converts np.array of words into amplitude in dBm.
        properties = sub-channel properties
        times      = np.array of times (ticks or seconds)
        words      = np.array of cls.raw_dtype
        returns [times, values] as np.array of times.dtype and np.float64 of converted words.
        the returned number of times, values might be different than the number of input times, words.
        in a derived class define this function for your hardware.
        implementation specific:
        - selects only words with device sub-channel address.
        - returns times and converted amplitude from selected words.
        """
        address = cls.raw_dtype(properties['address'] & ADDR_MASK)
        mask = (((words >> ADDR_SHIFT) & ADDR_MASK) == address)
        w = words[mask]
        values = ((w & DATA_MASK).astype(np.float64)*(cls.U1-cls.U0) + cls.U0*cls.A1 - cls.U1*cls.A0)/(cls.A1-cls.A0)
        return [times[mask], np.where(values <= 0, cls.DBM_MIN, 20.0*np.log10(values))]

    @classmethod
    def phase_to_words(cls, properties, phases, **args):
        """
        converts phase in degree to raw data words for the specific device.
        properties = sub-channel properties
        phasez     = numpy array of phases in degree
        returns np.array of type self.raw_dtype of one or several words.
        in a derived class define this function for your hardware.
        """
        address = cls.raw_dtype((properties['address'] & ADDR_MASK) << ADDR_SHIFT)
        phase_limits = properties['limits']
        mask = (phases != cls.invalid_value_phase)
        p = np.where(mask, phases, BIT_NOP_SH)
        p = np.clip(p % 360.0, phase_limits[0], phase_limits[1])
        ptw = np.round((p/360.0)*((1<<cls.PHASE_BITS)-1)).astype(cls.raw_dtype) & cls.PHASE_MASK
        raw_data = np.array([address | (((ptw>>i) & DATA_MASK) << DATA_SHIFT) for i in range(0, cls.PHASE_BITS, DATA_BITS)], dtype=cls.raw_dtype).flatten(order='F')
        if BACK_CONVERT and np.any(mask): # check back conversion
            val = cls.words_to_phase(properties, np.array(range(len(raw_data))), raw_data)
            errors    = np.abs(val[1] - p[mask])
            max_error = 360.0/((1<<cls.PHASE_BITS)-1)
            imax      = np.argmax(errors)
            #print('%s p = %.6f deg: PTW = 0x%x -> %.6f deg' % (cls.__name__, phase[mask][imax], ptw[mask][imax], val[1][imax]))
            if errors[imax] > max_error:
                raise LabscriptError("%s phase_to_words: %i phases out of tolerance! max. error for %.6f deg != %.6f deg" % (cls.__name__, np.count_nonzero(errors > max_error), val[1][imax], p[mask][imax]))
        return raw_data

    @classmethod
    def words_to_phase(cls, properties, times, words, **args):
        """
        converts np.array of words into phase in degree.
        properties = sub-channel properties
        times      = np.array of times (ticks or seconds)
        words      = np.array of cls.raw_dtype
        returns [times, values] as np.array of times.dtype and np.float64 of converted words.
        the returned number of times, values might be different than the number of input times, words.
        in a derived class define this function for your hardware.
        implementation specific:
        - selects only words with device sub-channel address.
        - returns times and converted phase from selected words.
        """
        address = cls.raw_dtype(properties['address'] & ADDR_MASK)
        mask = (((words >> ADDR_SHIFT) & ADDR_MASK) == address)
        w = words[mask]
        values = (w & DATA_MASK).astype(np.float64)*360.0/((1<<cls.PHASE_BITS)-1)
        return [times[mask], values]

    # dummy conversion function to be called on each sub-channel from generate_code.
    # properties is not used.
    # raw_data is returned without modification since conversion is already done.
    @classmethod
    def _to_words(cls, properties, raw_data, **args):
        return raw_data

    # conversion function to be called with each sub-channel properties from worker class.
    # converts frequency, amplitude or phase into data words to be used in program_manual.
    # properties = sub-channel properties
    # values     = numpy array of values to be converted depeding on sub-channel type.
    # args       = additional arguments for implementation of derived classes
    # returns numpy array of type cls.raw_dtype with one or several data words.
    @classmethod
    def to_words(cls, properties, values, **args):
        sub = properties['sub-channel']
        if   sub == DDS_CHANNEL_FREQ : return cls.freq_to_words (properties, values, **args)
        elif sub == DDS_CHANNEL_AMP  : return cls.amp_to_words  (properties, values, **args)
        elif sub == DDS_CHANNEL_PHASE: return cls.phase_to_words(properties, values, **args)
        else: raise LabscriptError("to_words: sub-channel %i invalid!" % (sub))

    # converts words into frequency, amplitude or phase.
    # is called by runviewer-parser.
    # properties = sub-channel properties for which values should be returned.
    # times      = numpy array of time (ticks or seconds).
    # words      = numpy array of raw data of cls.raw_dtype.
    # args       = additional arguments for implementation of derived classes
    # returns [time,value] with selected times and values for given sub-channel.
    @classmethod
    def from_words(cls, properties, times, words, **args):
        # select data device address
        sub = properties['sub-channel']
        if   sub == DDS_CHANNEL_FREQ : return cls.words_to_freq (properties, times, words, **args)
        elif sub == DDS_CHANNEL_AMP  : return cls.words_to_amp  (properties, times, words, **args)
        elif sub == DDS_CHANNEL_PHASE: return cls.words_to_phase(properties, times, words, **args)
        else: raise LabscriptError("from_words: sub-channel %i invalid!" % (sub))

    def setfreq(self, t, value, **args):
        "set frequency in Hz at given time in seconds"
        # check limits
        if value < self.freq_limits[0] or value > self.freq_limits[1]:
            raise LabscriptError("%s t=%e: frequency %e is out of range %e - %e!" % (self.name, t, value, self.freq_limits[0], self.freq_limits[1]))
        # save raw data into individual instructions
        raw_data = self.freq_to_words(self.frequency.properties, np.array([value]), **args)
        #print(self.name, 't', t, 'f', value, '['+(','.join(['0x%x'%d for d in raw_data])+']'))
        if CRC_CHECK:
            self.crc(raw_data)
            #print(self.name, 'freq CRC =', str(self.crc))
        t_next = t
        for data in raw_data:
            self.frequency.add_instruction(t_next, data)
            t_next += 1.0/self.frequency.clock_limit
        # save final time and frequency in MHz
        # note: this uses the user-given time and not the actual last used time
        if self.frequency.final_time is None or t > self.frequency.final_time:
            self.frequency.final_time = t
            self.final_values[DDS_CHANNEL_FREQ] = value/1e6
        # return duration in seconds
        return (t_next - 1.0/self.frequency.clock_limit - t)

    def setamp(self, t, value, **args):
        "set amplitude  in dBm at given time in seconds"
        # check limits
        if value < self.amp_limits[0] or value > self.amp_limits[1]:
            raise LabscriptError("%s t=%e: amplitude %e is out of range %e - %e!" % (self.name, t, value, self.amp_limits[0], self.amp_limits[1]))
        # save raw data into individual instructions
        raw_data = self.amp_to_words(self.amplitude.properties, np.array([value]), **args)
        #print(self.name, 't', t, 'a', value, '['+(','.join(['0x%x'%d for d in raw_data])+']'))
        if CRC_CHECK:
            self.crc(raw_data)
            #print(self.name, 'amp CRC =', str(self.crc))
        t_next = t
        for data in raw_data:
            self.amplitude.add_instruction(t_next, data)
            t_next += 1.0/self.amplitude.clock_limit
        # save final time and amplitude in dBm
        # note: this uses the user-given time and not the actual last used time
        if self.amplitude.final_time is None or t > self.amplitude.final_time:
            self.amplitude.final_time = t
            self.final_values[DDS_CHANNEL_AMP] = value
        # return duration in seconds
        return (t_next - 1.0/self.amplitude.clock_limit - t)

    def setphase(self, t, value, **args):
        "set phase in degree at given time in seconds"
        # check limits
        if value < self.phase_limits[0] or value > self.phase_limits[1]:
            raise LabscriptError("%s t=%e: phase %e is out of range %e - %e!" % (self.name, t, value, self.phase_limits[0], self.phase_limits[1]))
        # save raw data into individual instructions
        raw_data = self.phase_to_words(self.phase.properties, np.array([value]), **args)
        #print(self.name, 't', t, 'p', value, '['+(','.join(['0x%x'%d for d in raw_data])+']'))
        if CRC_CHECK:
            self.crc(raw_data)
            #print(self.name, 'phase CRC =', str(self.crc))
        t_next = t
        for data in raw_data:
            self.phase.add_instruction(t_next, data)
            t_next += 1.0/self.phase.clock_limit
        # save final time and phase in degree
        # - this uses the user-given time and not the actual last used time
        # - for Analog Devices DDS this does not use the update flag
        #   which might lead to inconsistencies.
        # - runviewer can take true update time and update flag into account.
        if self.phase.final_time is None or t > self.phase.final_time:
            self.phase.final_time = t
            self.final_values[DDS_CHANNEL_PHASE] = value
        # return duration in seconds
        return (t_next - 1.0/self.phase.clock_limit - t)

