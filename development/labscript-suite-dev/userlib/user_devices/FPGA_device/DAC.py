#####################################################################
# analog output hardware specific (DAC) derived classes
# created 15/09/2024
# last change 15/09/2024 by Andi
#####################################################################

import numpy as np

from labscript import AnalogQuantity, LabscriptError
from user_devices.FPGA_device.shared import (
    DATA_MASK, DATA_SHIFT,ADDR_BITS, ADDR_SHIFT, ADDR_MASK,
    BACK_CONVERT,
    AO_INVALID_VALUE, AO_DEFAULT_VALUE,
    BIT_NOP_SH,
)

class AnalogOutput(AnalogQuantity):
    # generic analog output (implemented as DAC712)
    # use to derive other DAC's by overwriting class constants and V_to_words and words_to_V
    description = 'analog output (DAC712)'

    # default value is inserted by labscript when no user input was done
    # we want this to be an invalid value to distinguish if its inserted by user or by labscript
    # the true default value given to device is saved in device.properties.
    default_value = AO_INVALID_VALUE

    # returned data type from to_words
    raw_dtype = np.uint32

    # analog out resolution, true max and min output values and +/-5V reference values
    # see Texas Instruments, DAC712 datasheet, rev. July 2009, Table 1, p.13
    AO_BITS         = 16
    AO_RESOLUTION   = 20.0 / ((2**AO_BITS)-1)
    AO_MAX          = 10.0 - AO_RESOLUTION
    AO_MIN          = -10.0

    # test data, key = voltage, value = DAC tuning word
    test_data = {-20.0                 : 0x8000,
                 -10.0-2*AO_RESOLUTION : 0x8000,
                 -10.0-1*AO_RESOLUTION : 0x8000,
                  AO_MIN               : 0x8000,
                 -10.0                 : 0x8000,
                 -9.999695             : 0x8001,
                 -10.0+1*AO_RESOLUTION : 0x8001,
                 -10.0+2*AO_RESOLUTION : 0x8002,
                 -5.0 -2*AO_RESOLUTION : 0xbffe,
                 -5.0 -1*AO_RESOLUTION : 0xbfff,
                 -5.0                  : 0xc000,
                 -5.0 +1*AO_RESOLUTION : 0xc001,
                 -5.0 +2*AO_RESOLUTION : 0xc002,
                  0.0 -2*AO_RESOLUTION : 0xfffe,
                  0.0 -1*AO_RESOLUTION : 0xffff,
                 -305e-6               : 0xffff,
                  0.0                  : 0x0000,
                  305e-6               : 0x0001,
                  0.0 +1*AO_RESOLUTION : 0x0001,
                  0.0 +2*AO_RESOLUTION : 0x0002,
                  5.0 -2*AO_RESOLUTION : 0x3ffe,
                  5.0 -1*AO_RESOLUTION : 0x3fff,
                  5.0                  : 0x4000,
                  5.0 +1*AO_RESOLUTION : 0x4001,
                  5.0 +2*AO_RESOLUTION : 0x4002,
                 10.0 -3*AO_RESOLUTION : 0x7ffd,
                 10.0 -2*AO_RESOLUTION : 0x7ffe,
                 10.0 -1*AO_RESOLUTION : 0x7fff,
                 AO_MAX                : 0x7fff,
                  9.999695             : 0x7fff,
                 10.0                  : 0x7fff,
                 10.0 +1*AO_RESOLUTION : 0x7fff,
                 10.0 +2*AO_RESOLUTION : 0x7fff,
                 20.0                  : 0x7fff}

    def __init__(self, name, parent_device, connection, limits=None,
                 unit_conversion_class=None, unit_conversion_parameters=None,
                 default_value=None, **kwargs):
        # true device default and invalid values
        self.properties = {
            'default_value': default_value if default_value is not None else AO_DEFAULT_VALUE,
            'invalid_value': AO_INVALID_VALUE,
        }
        AnalogQuantity.__init__(self, name, parent_device, connection, limits,
                 unit_conversion_class, unit_conversion_parameters,
                 default_value, **kwargs)

    @classmethod
    def V_to_words(cls, volts):
        """
        convert np.array of voltages into low 16 bits of 32bit data words.
        see Texas Instruments, DAC712 datasheet, rev. July 2009, Table 1, p.13.
        there is no equation given and its not clear if scaling factor is 2^16 or 2^16-1,
        and the resolution of 305uV matches with both.
        however, only 2^16-1 does not give errors in test.
        """
        return (np.round((np.clip(volts, cls.AO_MIN, cls.AO_MAX) - cls.AO_MIN) * ((2**cls.AO_BITS)-1) / (cls.AO_MAX-cls.AO_MIN)).astype(cls.raw_dtype) - 0x8000) & DATA_MASK

    @classmethod
    def words_to_V(cls, words):
        """
        convert np.array 16bit data words into voltages.
        inverse function of V_to_words. see notes there.
        """
        return (np.where(words & 0x8000,
                         words.astype(np.float64) - 0x8000,
                         words.astype(np.float64) + 0x8000) * \
                (cls.AO_MAX - cls.AO_MIN) / ((2**cls.AO_BITS)-1) + cls.AO_MIN)

    # conversion function from data to raw_data word(s)
    # properies = dictionary with required content 'invalid_value' and 'address'
    # values    = numpy array of analog values to be converted to raw data words.
    # args      = additional arguments for implementation of derived classes
    # returns np.array of type cls.raw_dtype with one or several data words.
    # implementation specific:
    # - returns same number of words as values
    @classmethod
    def to_words(cls, properties, values, **args):
        #print('%s to_words' % (cls.__name__), values, type(values))
        address       = cls.raw_dtype(properties['address'] & ADDR_MASK) << ADDR_SHIFT
        invalid_value = properties['invalid_value']
        mask = (values != invalid_value)
        raw_data = np.where(mask, cls.V_to_words(np.clip(values, cls.AO_MIN, cls.AO_MAX)) | address, BIT_NOP_SH).astype(cls.raw_dtype)
        if BACK_CONVERT and np.any(mask):
            val = cls.from_words(properties, np.arange(len(raw_data)), raw_data)
            errors    = np.abs(val[1] - values[mask])
            max_error = cls.AO_RESOLUTION
            imax      = np.argmax(errors)
            #print(np.transpose([values, raw_data]))
            print('%s U = %.6f V: word = 0x%x -> %.6f V (%s, %.1e <= %.1e)' % (cls.__name__, values[mask][imax], raw_data[mask][imax], val[1][imax], 'ok' if errors[imax] <= max_error else 'error', errors[imax], max_error))
            if errors[imax] > max_error:
                raise LabscriptError("%s to_words: %i voltage conversions out of tolerance! max error for %.6f V != %.6f V" % (cls.__name__, np.count_nonzero(errors > max_error), val[1][imax], values[mask][imax]))
        return raw_data

    # conversion function from raw data word(s) to analog values
    # properies = dictionary with required content 'invalid_value' and 'address'
    # times     = numpy array of time (ticks or seconds).
    # words     = numpy array of raw data of cls.raw_dtype.
    # args      = additional arguments for implementation of derived classes
    # returns [time,value] with selected times and values for given sub-channel.
    # implementation specific:
    # - filters data for device address
    # - returns same number of values as filtered data
    @classmethod
    def from_words(cls, properties, times, words, **args):
        address = cls.raw_dtype(properties['address'] & ADDR_MASK) << ADDR_SHIFT
        mask = ((words & (BIT_NOP_SH | (ADDR_MASK << ADDR_SHIFT))) == address)
        return [times[mask], cls.words_to_V(words[mask] & DATA_MASK)]

    @classmethod
    def test(cls, test_data={}):
        """
        test words_to_V and V_to_words using cls.test_data added with input test_data.
        """
        tolerance = 5e-7
        tests = cls.test_data
        tests.update(test_data)
        volts = np.array(list(tests.keys()))
        words = np.array(list(tests.values()))

        # V_to_words
        calc = cls.V_to_words(volts)
        error = calc - words
        count = np.count_nonzero(error)
        if count > 0:
            print('[volt, word, expected, error]')
            print(np.transpose([volts, calc, words, error]))
            raise LabscriptError('%s: V_to_words %i errors!' % (cls.__name__, count))
        else:
            print('%s: V_to_words test ok. (largest error %e)' % (cls.__name__, np.max(np.abs(error))))

        # words_to_V
        calc = cls.words_to_V(words)
        error = calc - np.clip(volts, cls.AO_MIN, cls.AO_MAX)
        count = np.count_nonzero(np.abs(error) >= tolerance)
        if count > 0:
            print('[word, volt, expected, error]')
            print(np.transpose([words, calc, np.clip(volts, cls.AO_MIN, cls.AO_MAX), error]))
            raise LabscriptError('%s: words_to_V %i errors!' % (cls.__name__, count))
        else:
            print('%s: words_to_V test ok. (largest error %e)' % (cls.__name__, np.max(np.abs(error))))

        # double conversion test word -> voltage -> word.
        # we test all possible words. voltage cannot be out of range.
        words = np.arange(2**16)
        w2 = cls.V_to_words(cls.words_to_V(words))
        error = w2 - words
        count = np.count_nonzero(error)
        if count > 0:
            raise LabscriptError('%s: V_to_words(words_to_V) %i errors! largest error %e' % (cls.__name__, count, np.max(np.abs(error))))
        else:
            print('%s: V_to_words(words_to_V) test ok. (largest error %e)' % (cls.__name__, np.max(np.abs(error))))

        # double conversion test voltage -> word -> voltage
        # here we take also voltages out of range
        # we test that the found word gives minimum error when converted back to voltage
        volts = np.arange(cls.AO_MIN - 10 * cls.AO_RESOLUTION, cls.AO_MAX + 10 * cls.AO_RESOLUTION, cls.AO_RESOLUTION / 10)
        words = cls.V_to_words(volts)
        words_p = words + 1
        words_n = words - 1
        v2 = cls.words_to_V(words)
        v2_p = cls.words_to_V(words_p)
        v2_n = cls.words_to_V(words_n)
        error = np.abs(v2 - np.clip(volts, cls.AO_MIN, cls.AO_MAX)) / cls.AO_RESOLUTION
        error_p = np.abs(v2_p - np.clip(volts, cls.AO_MIN, cls.AO_MAX)) / cls.AO_RESOLUTION
        error_n = np.abs(v2_n - np.clip(volts, cls.AO_MIN, cls.AO_MAX)) / cls.AO_RESOLUTION
        if np.count_nonzero(error > 0.5) > 0:
            count = np.count_nonzero(error > 0.5)
            raise LabscriptError('%s: words_to_V(V_to_words) %i errors! largest error %.3f LSB' % (cls.__name__, count, np.max(error)))
        elif np.count_nonzero(error > error_p) > 0:
            count = np.count_nonzero(error > error_p)
            raise LabscriptError('%s: words_to_V(V_to_words) %i x error(word) > error(word+1)!' % (cls.__name__, count))
        elif np.count_nonzero(error > error_n) > 0:
            count = np.count_nonzero(error > error_n)
            raise LabscriptError('%s: words_to_V(V_to_words) %i x error(word) > error(word-1)!' % (cls.__name__, count))
        else:
            print('%s: words_to_V(V_to_words) test ok. (largest error %.3f LSB ok)' % (cls.__name__, np.max(error)))

    def constant(self, t, value, units=None):
        # check limits before giving to labscript implementation
        # for +10V its a bit nasty to type in, so we allow this and clip value to proper AO_MAX.
        # TODO: unit conversion. would be nice to calculate min/max in all units and check here.
        if units is None:
            if (value < self.AO_MIN) or (value >= (self.AO_MAX+2*self.AO_RESOLUTION)):
                raise LabscriptError("%s: time %.6f, value %.6f is out of limits [%.6f, %.6f]" % (self.name, t, value, self.AO_MIN, self.AO_MAX))
            if value > self.AO_MAX: value = self.AO_MAX
        return AnalogQuantity.constant(self, t, value, units)

class DAC712(AnalogOutput):
    # DAC712 is an alias of AnalogOutput
    description = 'DAC712'

class DAC715(AnalogOutput):
    # DAC715, same as DAC712 but unipolar 0-10V, 152uV resolution.
    description = 'DAC715'

    # analog out resolution, true max and min output values and +/-5V reference values
    # see Texas Instruments, DAC715 datasheet, July 1995, Table 1, p.8
    AO_BITS         = 16
    AO_RESOLUTION   = 10/((2**AO_BITS)-1)
    AO_MAX          = 10.0 - AO_RESOLUTION
    AO_MIN          = 0.0

    # test data, key = voltage, value = DAC tuning word
    # (*) see notes at V_to_words.
    test_data = {-1.0                 : 0x8000,
                  0.0-2*AO_RESOLUTION : 0x8000,
                  0.0-1*AO_RESOLUTION : 0x8000,
                  AO_MIN              : 0x8000,
                  0.0                 : 0x8000,
                  152.6e-6            : 0x8001,     # (*)
                  0.0+1*AO_RESOLUTION : 0x8001,
                  0.0+2*AO_RESOLUTION : 0x8002,
                  2.5-2*AO_RESOLUTION : 0xbffe,
                  2.5-1*AO_RESOLUTION : 0xbfff,
                  2.5                 : 0xc000,
                  2.5+1*AO_RESOLUTION : 0xc001,
                  2.5+2*AO_RESOLUTION : 0xc002,
                  5.0-2*AO_RESOLUTION : 0xfffe,
                  5.0-1*AO_RESOLUTION : 0xffff,
                  4.999847            : 0xffff,
                  5.0                 : 0x0000,
                  5.0001526           : 0x0001, # (*)
                  5.0+1*AO_RESOLUTION : 0x0001,
                  5.0+2*AO_RESOLUTION : 0x0002,
                  7.5-2*AO_RESOLUTION : 0x3ffe,
                  7.5-1*AO_RESOLUTION : 0x3fff,
                  7.5                 : 0x4000,
                  7.5+1*AO_RESOLUTION : 0x4001,
                  7.5+2*AO_RESOLUTION : 0x4002,
                 10.0-3*AO_RESOLUTION : 0x7ffd,
                 10.0-2*AO_RESOLUTION : 0x7ffe,
                 10.0-1*AO_RESOLUTION : 0x7fff,
                 9.999847             : 0x7fff,
                 AO_MAX               : 0x7fff,
                 10.0                 : 0x7fff,
                 10.0+1*AO_RESOLUTION : 0x7fff,
                 10.0+2*AO_RESOLUTION : 0x7fff,
                 20.0                 : 0x7fff}

    @classmethod
    def V_to_words(cls, volts):
        """
        convert np.array of voltages into low 16 bits of 32bit data words.
        # see Texas Instruments, DAC715 datasheet, July 1995, Table 1, p.8.
        there is no equation given and its not clear if scaling factor is 2^16 or 2^16-1,
        and the resolution of 152uV matches with both.
        however, only 2^16-1 does not give errors in test.
        (*) had to insert more precise resolution 152.6uV in test_data to stay within tolerance 5e-7.
        """
        return (np.round((np.clip(volts, cls.AO_MIN, cls.AO_MAX) - cls.AO_MIN) * ((2**cls.AO_BITS)-1) / (cls.AO_MAX-cls.AO_MIN)).astype(cls.raw_dtype) - 0x8000) & DATA_MASK

    @classmethod
    def words_to_V(cls, words):
        "convert numpy array of 16bit data words into voltages"
        return np.where(words & 0x8000,
                        words.astype(np.float64) - 0x8000,
                        words.astype(np.float64) + 0x8000) * \
                (cls.AO_MAX - cls.AO_MIN) / ((2**cls.AO_BITS)-1) + cls.AO_MIN

class DAC7744(AnalogOutput):
    # Texas Instruments DAC7744
    description = 'DAC7744'

    # Texas Instruments DAC7744, +/-10V, 305uV resolution
    # tuning word 0x0 = -10V, 0x8000 = 0.0V, 0xffff = 10-AO_RESOLUTION
    AO_BITS         = 16
    AO_RESOLUTION   = 20/(2**AO_BITS)
    AO_MAX          = 10.0 - AO_RESOLUTION
    AO_MIN          = -10.0

    # test data, key = voltage, value = DAC tuning word
    # calculated from equ. 1 in datasheet
    test_data = {20.0                   : 0xffff,
                 10.0                   : 0xffff,
                 AO_MAX                 : 0xffff,
                 9.999695               : 0xffff,
                 10.0-1*AO_RESOLUTION   : 0xffff,
                 10.0-2*AO_RESOLUTION   : 0xfffe,
                  5.0+2*AO_RESOLUTION   : 0xc002,
                  5.0+1*AO_RESOLUTION   : 0xc001,
                  5.0                   : 0xc000,
                  5.0-1*AO_RESOLUTION   : 0xbfff,
                  5.0-2*AO_RESOLUTION   : 0xbffe,
                  0.0+2*AO_RESOLUTION   : 0x8002,
                  0.0+1*AO_RESOLUTION   : 0x8001,
                  0.0                   : 0x8000,
                  0.0-1*AO_RESOLUTION   : 0x7fff,
                  0.0-2*AO_RESOLUTION   : 0x7ffe,
                 -5.0+2*AO_RESOLUTION   : 0x4002,
                 -5.0+1*AO_RESOLUTION   : 0x4001,
                 -5.0                   : 0x4000,
                 -5.0-1*AO_RESOLUTION   : 0x3fff,
                 -5.0-2*AO_RESOLUTION   : 0x3ffe,
                -10.0+2*AO_RESOLUTION   : 0x0002,
                -10.0+1*AO_RESOLUTION   : 0x0001,
                 -9.999695              : 0x0001,
                  AO_MIN                : 0x0000,
                -10.0                   : 0x0000,
                -10.0-1*AO_RESOLUTION   : 0x0000,
                -10.0-2*AO_RESOLUTION   : 0x0000,
                -20.0                   : 0x0000,
                 }

    @classmethod
    def V_to_words(cls, volts):
        "convert voltages (scalar or np.array) into low 16 bits of 32bit data words."
        return np.round((np.clip(volts, cls.AO_MIN, cls.AO_MAX) - cls.AO_MIN) * (2**cls.AO_BITS)/20.0).astype(cls.raw_dtype) & DATA_MASK

    @classmethod
    def words_to_V(cls, words):
        "convert 16bit data words (scalar or np.array) into voltages"
        return np.array(words, dtype=np.float64) * 20.0/(2**cls.AO_BITS) + cls.AO_MIN


