#!/usr/bin/python

# labscript definition file for DDS from Analog Devices in the Innsbruck implementation
# these are derived classes from DDS_generic used by FPGA_device

# created 30/8/2024 by Andi
# last change 5/9/2024 by Andi

import numpy as np
from labscript import LabscriptError
from user_devices.FPGA_device.DDS_generic import DDS_generic
from user_devices.FPGA_device.shared import (
    DATA_MASK, DATA_SHIFT,ADDR_BITS, ADDR_SHIFT, ADDR_MASK,
    BACK_CONVERT,
    BIT_NOP_SH,
)

# default and invalid values
# these values might be outside limits
DDS_FREQ_DEFAULT_VALUE      = 0.0
DDS_AMP_DEFAULT_VALUE       = -60.0
DDS_PHASE_DEFAULT_VALUE     = 0.0
DDS_FREQ_INVALID_VALUE      = -1
DDS_AMP_INVALID_VALUE       = -1000
DDS_PHASE_INVALID_VALUE     = -1000

class AD9854(DDS_generic):
    description = 'DDS AD9854'

    # DDS specifics
    SYSCLK              = 300e6
    FREQ_BITS           = 48
    FREQ_MASK           = (1<<FREQ_BITS)-1
    AMP_BITS            = 12
    AMP_MASK            = (1<<AMP_BITS)-1
    PHASE_BITS          = 14
    PHASE_MASK          = (1<<PHASE_BITS)-1

    # data specifics
    REG_BITS            = 6
    REG_MASK            = (1 << REG_BITS) - 1
    REG_SHIFT           = 0
    VALUE_BITS          = 8
    VALUE_MASK          = (1 << VALUE_BITS) - 1
    VALUE_SHIFT         = 8
    
    # DDS uses address range [address ... address + (2**ADDR_RNG_BITS)-1]
    ADDR_RNG_BITS       = 2 
    ADDR_RNG_MASK       = ((1 << (ADDR_BITS-ADDR_RNG_BITS)) - 1) << ADDR_RNG_BITS

    # do not add address offset to sub-channel address
    addr_offset         = None

    # control bits (lowest two address bits)
    FSK                 = 1 << 6
    OSK                 = 1 << 7
    RESET               = 0 << 16
    WRITE               = 1 << 16
    WRITE_AND_UPDATE    = 2 << 16

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
    freq_limits         = (0, 135e6)

    # amplitude limits in dBm. limited by calibration.
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

    # data for reset. address is added automatically.
    RESET_DATA = [
        RESET                                                 , # master reset
        WRITE           |(0x10<<VALUE_SHIFT)|(0x1D<<REG_SHIFT), # Comperator power down
        WRITE           |(0x20<<VALUE_SHIFT)|(0x1C<<REG_SHIFT), # Bypass PLL
        WRITE_AND_UPDATE|(0x60<<VALUE_SHIFT)|(0x20<<REG_SHIFT), # Bypass inv sinc; OSK enable
        ]

    # registers for frequency, amplitude, phase. LSB first
    REGS_FREQ       = [0x09, 0x08, 0x07, 0x06, 0x05, 0x04]
    REGS_AMP        = [0x27, 0x26]
    REGS_PHASE      = [0x01, 0x00]

    # initial value for each register. None = all 0.
    # TODO: update for your hardware
    REGS_FREQ_INIT  = None
    REGS_AMP_INIT   = None
    REGS_PHASE_INIT = None

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
        address = cls.raw_dtype((properties['address'] & ADDR_MASK) << ADDR_SHIFT)
        return np.array(cls.RESET_DATA, dtype=cls.raw_dtype) | address

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
    def get_tuning_words(cls, properties, times, words, regs, regs_init):
        """
        filters words for device address range and
        returns times and frequency/amplitude/phase tuning words for given registers.
        properties = sub-channel properties
        times      = np.array of times (seconds or ticks).
        words      = np.array of cls.raw_dtype
        returns [times, values] as np.array of times.dtype and np.float64 of converted words.
        notes:
        - the function filters input words for device address (range)
        - the function returns fewer times and values than filtered words
        - the function tracks the registers and generates tuning words for each WRITE_AND_UPDATE
        """
        address   = cls.raw_dtype(properties['address'] & ADDR_MASK)
        addr_mask = (((words >> ADDR_SHIFT) & cls.ADDR_RNG_MASK) == address)
        #print('address 0x%x'%address)
        #print(regs)
        #print(['0x%x' % d for d in words])
        #print(addr_mask)
        w = words[addr_mask]
        if len(w) > 0:
            write  = (w & (cls.WRITE | cls.WRITE_AND_UPDATE) == cls.WRITE)
            update = (w & (cls.WRITE | cls.WRITE_AND_UPDATE) == cls.WRITE_AND_UPDATE)
            write_or_update = write | update
            values = np.zeros(shape=(len(w),), dtype=np.uint64)
            words_reg = (w >> cls.REG_SHIFT) & cls.REG_MASK
            for i,addr in enumerate(regs):
                # init register
                if regs_init is None:
                    reg = np.zeros(shape=(len(w),), dtype=np.int16)
                else:
                    reg = np.ones(shape=(len(w),), dtype=np.int16)*regs_init[i]
                # find where register is written (WRITE or WRITE_OR_UPDATE bits but not both)
                mask = (words_reg == addr) & write_or_update
                # take register values where is written
                # and fill values in between with previous values using difference and cumsum.
                changes = (w[mask] >> cls.VALUE_SHIFT) & cls.VALUE_MASK
                changes[1:] = changes[1:] - changes[:-1]
                reg[mask] = changes
                reg = np.cumsum(reg)
                #print(['0x%x'%d for d in w])
                #print(i, 'reg', addr, 'all:', np.transpose([times[addr_mask], reg]))
                # add register to values at proper offset
                values |= reg.astype(np.uint64) << np.uint64(i*cls.VALUE_BITS)
            # return times and tuning word where update bit is set
            return [times[addr_mask][update], values[update]]
        else:
            return [np.array([], dtype=times.dtype), np.array([], dtype=np.uint64)]

    @classmethod
    def freq_to_words(cls, properties, frequencies, update=True):
        """
        converts frequency in Hz to raw data words for the specific device.
        properties = sub-channel properties
        frequency  = np.array of frequencies in Hz
        returns np.array of type self.raw_dtype of one or several words.
        in a derived class define this function and to_words for your hardware.
        """
        address = cls.raw_dtype((properties['address'] & ADDR_MASK) << ADDR_SHIFT)
        freq_limits = properties['limits']
        mask = (frequencies != cls.invalid_value_freq)
        f = np.where(mask, frequencies, BIT_NOP_SH)
        f = np.clip(f, freq_limits[0], freq_limits[1])
        df = cls.SYSCLK/(1<<cls.FREQ_BITS)
        ftw = np.round(f/df).astype(np.uint64) & np.uint64(cls.FREQ_MASK)
        fb  = [(ftw >> np.uint64(i)).astype(cls.raw_dtype) & cls.VALUE_MASK for i in range(0, cls.FREQ_BITS, cls.VALUE_BITS)]
        write_last = cls.WRITE_AND_UPDATE if update else cls.WRITE
        raw_data = np.array([
                address                                                 |
                (cls.WRITE if i<(len(cls.REGS_FREQ)-1) else write_last) |
                (fb[i]<<cls.VALUE_SHIFT)                                |
                (reg<<cls.REG_SHIFT)
                for i,reg in enumerate(cls.REGS_FREQ)], dtype=cls.raw_dtype).flatten(order='F')
        if BACK_CONVERT and np.any(mask): # check back conversion
            if update: tmp = raw_data
            else: # we have to set update flag in last raw_data otherwise will not work!
                tmp = raw_data.copy()
                update_mask = (cls.ADDR_RNG_MASK << ADDR_SHIFT) | (DATA_MASK << DATA_SHIFT)
                tmp[-1] = (tmp[-1] & update_mask) | cls.WRITE_AND_UPDATE
            val = cls.words_to_freq(properties, np.arange(len(tmp)), tmp)
            errors    = np.abs(val[1] - f[mask]/1e6)
            max_error = 0.5*cls.SYSCLK/((1<<cls.FREQ_BITS)-1)
            imax      = np.argmax(errors)
            print('f = %.6f MHz: FTW = 0x%x -> %.6f MHz (%s, %.1e <= %.1e)' % (frequencies[mask][imax] / 1e6, ftw[mask][imax], val[1][imax], 'ok' if errors[imax] <= max_error else 'error', errors[imax], max_error))
            if errors[imax] > max_error:
                raise LabscriptError("%s freq_to_words: %i frequency conversions out of tolerance! max. error for %.6f MHz != %.6f MHz" % (cls.__name__, np.count_nonzero(errors > max_error), val[1][imax], f[mask][imax]/1e6))
        return raw_data

    @classmethod
    def words_to_freq(cls, properties, times, words):
        """
        converts np.array of words into frequency in MHz.
        properties = sub-channel properties
        times = numpy array of time (ticks or seconds)
        words = np.array of cls.raw_dtype
        returns [times, values] as np.array of times.dtype and np.float64 of converted words.
        notes:
        - the function filters input words for device address (range)
        - the function returns fewer times and values than words
        - the function tracks the frequency registers and generates values for each WRITE_AND_UPDATE
        TODO:
        - FSK/OSK bits are ignored here
        """
        times, values = cls.get_tuning_words(properties, times, words, cls.REGS_FREQ, cls.REGS_FREQ_INIT)
        print('FTW:', values)
        df = cls.SYSCLK/(1<<cls.FREQ_BITS)
        return [times, (values & cls.FREQ_MASK).astype(np.float64)*df/1e6]

    @classmethod
    def amp_to_words(cls, properties, amplitudes, update=True):
        """
        converts amplitude in dBm to raw data words for the specific device.
        properties = sub-channel properties
        amplitudes = np.array of amplitudes in dBm
        returns np.array of type self.raw_dtype of one or several words.
        in a derived class define this function and to_words for your hardware.
        here we use amplitude calibration to calculate amplitude tuning word.
        """
        address = cls.raw_dtype((properties['address'] & ADDR_MASK) << ADDR_SHIFT)
        amp_limits = properties['limits']
        mask = (amplitudes != cls.invalid_value_amp)
        a = np.where(mask, amplitudes, BIT_NOP_SH)
        a = np.clip(a, amp_limits[0], amp_limits[1])
        uval = 10**(a/20.0)
        atw = np.round(((uval - cls.U0)*cls.A1 + (cls.U1 - uval)*cls.A0)/(cls.U1-cls.U0)).astype(dtype=cls.raw_dtype) & cls.AMP_MASK
        ab  = [(atw>>i) & cls.VALUE_MASK for i in range(0, cls.AMP_BITS, cls.VALUE_BITS)]
        write_last = cls.WRITE_AND_UPDATE if update else cls.WRITE
        raw_data = np.array([
                address                                                    |
                (cls.WRITE if (i < (len(cls.REGS_AMP)-1)) else write_last) |
                (ab[i] << cls.VALUE_SHIFT)                                 |
                (reg   << cls.REG_SHIFT)
                for i,reg in enumerate(cls.REGS_AMP)], dtype=cls.raw_dtype).flatten(order='F')
        if BACK_CONVERT and np.any(mask): # check back conversion
            if update: tmp = raw_data
            else: # we have to set update flag in last raw_data otherwise will not work!
                tmp = raw_data.copy()
                update_mask = (cls.ADDR_RNG_MASK << ADDR_SHIFT) | (DATA_MASK << DATA_SHIFT)
                tmp[-1] = (tmp[-1] & update_mask) | cls.WRITE_AND_UPDATE
            val = cls.words_to_amp(properties, np.array(range(len(tmp))), tmp)
            errors    = np.abs(val[1] - a[mask])
            max_error = (cls.DBM_MAX - cls.DBM_MIN) / ((1 << cls.AMP_BITS) - 1)
            imax      = np.argmax(errors)
            print('a = %.6f dBm: ATW = 0x%x -> %.6f dBm (%s, %.1e <= %.1e)' % (amplitudes[mask][imax], atw[mask][imax], val[1][imax], 'ok' if errors[imax] <= max_error else 'error', errors[imax], max_error))
            if errors[imax] > max_error:
                raise LabscriptError("%s amp_to_words: %i amplitude conversions out of tolerance! max. error for %.6f dBm != %.6f dBm" % (cls.__name__, np.count_nonzero(errors > max_error), val[1][imax], a[mask][imax]))
        return raw_data

    @classmethod
    def words_to_amp(cls, properties, times, words):
        """
        converts np.array of words into amplitude in dBm.
        properties = sub-channel properties
        words = np.array of cls.raw_dtype
        returns [times, values] as np.array of times.dtype and np.float64 of converted words.
        notes:
        - the function filters input words for device address (range)
        - the function returns fewer times and values than words
        - the function tracks the amplitude registers and generates word for each WRITE_AND_UPDATE
        """
        times, values = cls.get_tuning_words(properties, times, words, cls.REGS_AMP, cls.REGS_AMP_INIT)
        #print('ATW:', values)
        values = ((values & cls.AMP_MASK).astype(np.float64)*(cls.U1-cls.U0) + cls.U0*cls.A1 - cls.U1*cls.A0)/(cls.A1-cls.A0)
        return [times, np.where(values <= 0, cls.DBM_MIN, 20.0*np.log10(values))]

    @classmethod
    def phase_to_words(cls, properties, phases, update=True):
        """
        converts phase in degree to raw data words for the specific device.
        properties = sub-channel properties
        phases     = np.array of phases in degree
        returns np.array of type self.raw_dtype of one or several words.
        in a derived class define this function and to_words for your hardware.
        """
        address = cls.raw_dtype((properties['address'] & ADDR_MASK) << ADDR_SHIFT)
        phase_limits = properties['limits']
        mask = (phases != cls.invalid_value_phase)
        p = np.where(mask, phases, BIT_NOP_SH)
        p = np.clip(p % 360.0, phase_limits[0], phase_limits[1])
        ptw = np.round((p/360.0)*((1<<cls.PHASE_BITS)-1)).astype(cls.raw_dtype) & cls.PHASE_MASK
        pb = [(ptw>>i) & cls.VALUE_MASK for i in range(0, cls.PHASE_BITS, cls.VALUE_BITS)]
        write_last = cls.WRITE_AND_UPDATE if update else cls.WRITE
        raw_data = np.array([
                address                                                      |
                (cls.WRITE if (i < (len(cls.REGS_PHASE)-1)) else write_last) |
                (pb[i] << cls.VALUE_SHIFT)                                   |
                (reg   << cls.REG_SHIFT)
                for i,reg in enumerate(cls.REGS_PHASE)], dtype=cls.raw_dtype).flatten(order='F')
        if BACK_CONVERT and np.any(mask): # check back conversion
            if update: tmp = raw_data
            else: # we have to set update flag in last raw_data otherwise will not work!
                tmp = raw_data.copy()
                update_mask = (cls.ADDR_RNG_MASK << ADDR_SHIFT) | (DATA_MASK << DATA_SHIFT)
                tmp[-1] = (tmp[-1] & update_mask) | cls.WRITE_AND_UPDATE
            val = cls.words_to_phase(properties, np.array(range(len(tmp))), tmp)
            errors    = np.abs(val[1] - p[mask])
            max_error = 360.0/((1<<cls.PHASE_BITS)-1)
            imax      = np.argmax(errors)
            print('p = %.6f °: PTW = 0x%x -> %.6f ° (%s, %.1e <= %.1e)' % (phases[mask][imax], ptw[mask][imax], val[1][imax], 'ok' if errors[imax] <= max_error else 'error', errors[imax], max_error))
            if errors[imax] > max_error:
                raise LabscriptError("%s phase_to_words: %i phase conversions out of tolerance! max. error for %.6f deg != %.6f deg" % (cls.__name__, np.count_nonzero(errors > max_error), val[1][imax], p[mask][imax]))
        return raw_data

    @classmethod
    def words_to_phase(cls, properties, times, words):
        """
        converts np.array of words into phase in degree.
        properties = sub-channel properties
        words = np.array of cls.raw_dtype
        returns [times, values] as np.array of times.dtype and np.float64 of converted words.
        notes:
        - the function filters input words for device address (range)
        - the function returns fewer times and values than words
        - the function tracks the phase registers and generates word for each WRITE_AND_UPDATE
        """
        times, values = cls.get_tuning_words(properties, times, words, cls.REGS_PHASE, cls.REGS_PHASE_INIT)
        #print('PTW:', values)
        return [times, (values & cls.PHASE_MASK).astype(np.float64)*360.0/((1<<cls.PHASE_BITS)-1)]


class AD9858(AD9854):
    description         = 'DDS AD9858'

    # DDS specifics
    SYSCLK              = 1000e6
    FREQ_BITS           = 32
    FREQ_MASK           = (1 << FREQ_BITS) - 1
    AMP_BITS            = 7
    AMP_MASK            = (1 << AMP_BITS) - 1
    PHASE_BITS          = 14
    PHASE_MASK          = (1 << PHASE_BITS) - 1

    # data specifics
    REG_BITS            = 6
    REG_MASK            = (1 << REG_BITS) - 1
    REG_SHIFT           = 0
    VALUE_BITS          = 8
    VALUE_MASK          = (1 << VALUE_BITS) - 1
    VALUE_SHIFT         = 8

    # DDS uses address range [address ... address + (2**ADDR_RNG_BITS)-1]
    ADDR_RNG_BITS       = 2 
    ADDR_RNG_MASK       = ((1 << (ADDR_BITS-ADDR_RNG_BITS)) - 1) << ADDR_RNG_BITS

    # do not add address offset to sub-channel address
    addr_offset         = None

    # control bits (lowest two address bits)
    PS0                 = 1 << 6
    PS1                 = 1 << 7
    RESET               = 0 << 16
    WRITE               = 1 << 16
    WRITE_AND_UPDATE    = 2 << 16
    AMPLITUDE           = 3 << 16

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
    freq_limits         = (0, 400e6)

    # amplitude limits in dBm. limited by calibration.
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

    # data for reset. address is added automatically.
    RESET_DATA = [
        RESET                                                         , # master reset
        WRITE_AND_UPDATE | (0x58 << VALUE_SHIFT) | (0x00 << REG_SHIFT), # 2 GHz divider disable; Mixer power down; Phase detect power down
        ]

    # registers for frequency, and phase. LSB first
    REGS_FREQ       = [0x0a, 0x0b, 0x0c, 0x0d]
    REGS_PHASE      = [0x0e, 0x0f]

    # initial value for each register. None = all 0.
    # TODO: update for your hardware
    REGS_FREQ_INIT  = None
    REGS_PHASE_INIT = None

    @classmethod
    def amp_to_words(cls, properties, amplitudes):
        """
        converts amplitude in dBm to raw data words for the specific device.
        properties = sub-channel properties
        amplitudes = np.array of amplitudes in dBm
        returns np.array of type self.raw_dtype of one or several words.
        in a derived class define this function and to_words for your hardware.
        here we use amplitude calibration to calculate amplitude tuning word.
        note: this has no update flag since is directly written to attenuator.
        TODO: assumed amplitude value is shifted by VALUE_SHIFT?
        """
        address = cls.raw_dtype((properties['address'] & ADDR_MASK) << ADDR_SHIFT)
        amp_limits = properties['limits']
        mask = (amplitudes != cls.invalid_value_amp)
        a = np.where(mask, amplitudes, BIT_NOP_SH)
        a = np.clip(a, amp_limits[0], amp_limits[1])
        uval = 10**(a/20)
        atw = np.round(((uval - cls.U0) * cls.A1 + (cls.U1 - uval) * cls.A0) / (cls.U1 - cls.U0)).astype(dtype=cls.raw_dtype) & cls.AMP_MASK
        raw_data = np.array([
            address | cls.AMPLITUDE | (atw << cls.VALUE_SHIFT)
        ], dtype=cls.raw_dtype).flatten(order='F')
        if BACK_CONVERT and np.any(mask): # check back conversion
            val = cls.words_to_amp(properties, np.array(range(len(raw_data))), raw_data)
            errors    = np.abs(val[1] - a[mask])
            max_error = (cls.DBM_MAX - cls.DBM_MIN) / ((1 << cls.AMP_BITS) - 1)
            imax      = np.argmax(errors)
            print('a = %.6f MHz: ATW = 0x%x -> %.6f MHz (%s, %.1e <= %.1e)' % (amplitudes[mask][imax], atw[mask][imax], val[1][imax], 'ok' if errors[imax] <= max_error else 'error', errors[imax], max_error))
            if errors[imax] > max_error:
                raise LabscriptError("%s amp_to_words: %i amplitude conversions out of tolerance! max. error for %.6f dBm != %.6f dBm" % (cls.__name__, np.count_nonzero(errors > max_error), val[1][imax], a[mask][imax]))
        return raw_data

    @classmethod
    def words_to_amp(cls, properties, times, words):
        """
        converts np.array of words into amplitude in dBm.
        properties = sub-channel properties
        words = np.array of cls.raw_dtype
        returns [times, values] as np.array of times.dtype and np.float64 of converted words.
        notes:
        - the function filters input words for device address (range)
        - the function returns ALL times and values where AMPLITUDE is set
        TODO: assumed amplitude value is shifted by VALUE_SHIFT?
        """
        amplitude = ((words & cls.AMPLITUDE) == cls.AMPLITUDE)
        values = (words[amplitude] >> cls.VALUE_SHIFT) & cls.AMP_MASK
        values = (values.astype(np.float64)*(cls.U1-cls.U0) + cls.U0*cls.A1 - cls.U1*cls.A0)/(cls.A1-cls.A0)
        return [times[amplitude], np.where(values <= 0, cls.DBM_MIN, 20.0*np.log10(values))]

class AD9915(AD9854):
    description         = 'DDS AD9915'

    # DDS specifics
    SYSCLK              = 2500e6
    FREQ_BITS           = 32
    FREQ_MASK           = (1 << FREQ_BITS) - 1
    AMP_BITS            = 12
    AMP_MASK            = (1 << AMP_BITS) - 1
    PHASE_BITS          = 16
    PHASE_MASK          = (1 << PHASE_BITS) - 1

    # data specifics
    REG_BITS            = 8
    REG_MASK            = (1 << REG_BITS) - 1
    REG_SHIFT           = 0
    VALUE_BITS          = 8
    VALUE_MASK          = (1 << VALUE_BITS) - 1
    VALUE_SHIFT         = 8

    # DDS uses address range [address ... address + (2**ADDR_RNG_BITS)-1]
    ADDR_RNG_BITS       = 2 
    ADDR_RNG_MASK       = ((1 << (ADDR_BITS-ADDR_RNG_BITS)) - 1) << ADDR_RNG_BITS

    # do not add address offset to sub-channel address
    addr_offset         = None

    # control bits (lowest two address bits)
    RESET               = 0 << 16
    WRITE               = 1 << 16
    WRITE_AND_UPDATE    = 2 << 16

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
    freq_limits         = (0, 1000e6)

    # amplitude limits in dBm. limited by calibration.
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

    # data for reset. address is added automatically.
    RESET_DATA = [
        RESET                                                         , # master reset
        WRITE            | (0x01 << VALUE_SHIFT) | (0x01 << REG_SHIFT), # OSK enable
        WRITE_AND_UPDATE | (0x80 << VALUE_SHIFT) | (0x02 << REG_SHIFT), # profile mode enable
        ]

    # registers for frequency, amplitude and phase. LSB first
    REGS_FREQ  = [0x2c, 0x2d, 0x2e, 0x2f]
    REGS_AMP   = [0x32, 0x23]
    REGS_PHASE = [0x30, 0x31]

    # initial value for each register. None = all 0.
    # TODO: update for your hardware
    REGS_FREQ_INIT  = None
    REGS_AMP_INIT   = None
    REGS_PHASE_INIT = None
