# Moglabs QRF 
# created 29/5/2024 by Andi
# modified from:
# https://github.com/specialforcea/labscript_suite/blob/a4ad5255207cced671990fff94647b1625aa0049/labscript_devices/MOGLabs_XRF021.py
# requires mogdevice.py, see: https://pypi.org/project/mogdevice/
# last change 5/6/2024 by Andi
import numpy as np

from labscript import (
    Device, PseudoclockDevice,
    Pseudoclock, ClockLine,
    IntermediateDevice,
    DDS, StaticDDS,
    LabscriptError,
    set_passed_properties
)

from user_devices.iPCdev.labscript_devices import (
    iPCdev, iPCdev_device,
    DEVICE_HARDWARE_INFO, DEVICE_INFO_TYPE, DEVICE_INFO_ADDRESS, DEVICE_INFO_CHANNEL,
    HARDWARE_TYPE, HARDWARE_TYPE_DDS, DEVICE_INFO_GATE, DEVICE_INFO_GATE_DEVICE, DEVICE_INFO_GATE_CONNECTION,
    HARDWARE_SUBTYPE_NONE, HARDWARE_SUBTYPE_STATIC, HARDWARE_ADDRTYPE_MULTIPLE,
    ROUND_DIGITS,
)

from user_devices.iPCdev.blacs_tabs import (
    DDS_CHANNEL_PROP_FREQ, DDS_CHANNEL_PROP_AMP, DDS_CHANNEL_PROP_PHASE,
    PROP_UNIT, PROP_MIN, PROP_MAX, PROP_STEP, PROP_DEC,
    PROP_UNIT_MHZ, PROP_UNIT_DBM, PROP_UNIT_DEGREE
)

# set number of channels
MAX_NUM_CHANNELS = 4

# min/max RF frequency in MHz
F_MIN     = 5.0
F_MAX     = 250.0
F_STEP    = 1.0
F_DEC     = 3             # changed from 6
DEFAULT_RF_FREQ = F_MIN

# min/max RF amplitudes in dBm
A_MIN      = -50.0
A_MAX      = 33.0
A_STEP     = 1.0
A_DEC     = 2

# min/max RF phase in degree
P_MIN    = 0
P_MAX    = 360
P_STEP   = 1.0
P_DEC    = 3     # TODO: find out what the phase precision is!

# timing
RESOLUTION_TABLE_MODE   = 5e-6

# default IP port
DEFAULT_PORT = 7802

# connection name
CON_SEP             = ' '
CON_CHANNEL_NAME    = 'channel'

# clockline name
CLOCKLINE_NAME  = '%s_cl'

# properties table mode and trigger each step saved into properties
DDS_CHANNEL_PROP_MODE = 'mode'

# name of actual DDS channels is user name + these names to have unique names.
# will be removed by blacs_tab since user name should be given in experiment script.
DDS_NAME_DYNAMIC    = '_dyn'
DDS_NAME_STATIC     = '_static'

# possible 'mode' selection for each channel
MODE_BASIC              = 0
MODE_ADVANCED           = 1 # this is not implemented at the moment
MODE_TABLE_TIMED        = 2 # requires start trigger on channel 1 which requires that channel 1 is in this mode as well.
MODE_TABLE_TIMED_SW     = 3
MODE_TABLE_TRIGGERED    = 4
MODES = {'NSB'    :MODE_BASIC,           'basic'                :MODE_BASIC,            'fast': MODE_BASIC,
         'NSA'    :MODE_ADVANCED,        'advanced'             :MODE_ADVANCED,
         'TSB'    :MODE_TABLE_TIMED,     'table timed'          :MODE_TABLE_TIMED,
         'TSB sw' :MODE_TABLE_TIMED_SW,  'table timed software' :MODE_TABLE_TIMED_SW,
         'TSB trg':MODE_TABLE_TRIGGERED, 'table triggered'      :MODE_TABLE_TRIGGERED,
         }

# collections of mode values and mode strings
# global trigger required on GLOBAL_TRIGGER_CHANNEL
MODE_VALUES_WITH_GLOBAL_TRIGGER  = [MODE_TABLE_TIMED]
MODES_WITH_GLOBAL_TRIGGER        = list([name for name, mode in MODES.items() if mode in MODE_VALUES_WITH_GLOBAL_TRIGGER])
# channel trigger required
MODE_VALUES_WITH_CHANNEL_TRIGGER = [MODE_TABLE_TRIGGERED]
MODES_WITH_CHANNEL_TRIGGER       = list([name for name, mode in MODES.items() if mode in MODE_VALUES_WITH_CHANNEL_TRIGGER])
# channel enable required
MODE_VALUES_WITH_CHANNEL_ENABLE  = [MODE_BASIC]
MODES_WITH_CHANNEL_ENABLE        = list([name for name, mode in MODES.items() if mode in MODE_VALUES_WITH_CHANNEL_ENABLE])
# modes with GATE required = either channel trigger or enable
MODE_VALUES_WITH_GATE            = [MODE_BASIC, MODE_TABLE_TRIGGERED]
MODES_WITH_GATE                  = list([name for name, mode in MODES.items() if mode in MODE_VALUES_WITH_GATE])
# modes with static DDS
MODE_VALUES_STATIC               = [MODE_BASIC]
MODES_STATIC                     = list([name for name, mode in MODES.items() if mode in MODE_VALUES_STATIC])
# modes with dynamic DDS
MODE_VALUES_DYNAMIC              = [MODE_ADVANCED, MODE_TABLE_TIMED, MODE_TABLE_TIMED_SW, MODE_TABLE_TRIGGERED]
MODES_DYNAMIC                    = list([name for name, mode in MODES.items() if mode in MODE_VALUES_DYNAMIC])

# channel trigger input for global trigger.
GLOBAL_TRIGGER_CHANNEL = 1

# DDS channel with mode option and external digital_gate for triggering.
# default = basic (fast) mode with StaticDDS and enable/disable RF functions.
# this is a generic labscript device and acts as container class for DDS and StaticDDS.
class QRF_DDS(Device):
    def __init__(self,
                 name,
                 parent_device,
                 connection,
                 mode                       = None,
                 trigger_delay              = None,
                 trigger_duration           = None,
                 digital_gate               = {},
                 freq_limits                = None,
                 freq_conv_class            = None,
                 freq_conv_params           = {},
                 amp_limits                 = None,
                 amp_conv_class             = None,
                 amp_conv_params            = {},
                 phase_limits               = None,
                 phase_conv_class           = None,
                 phase_conv_params          = {}
                 ):

        # call super class which will insert device name into globals
        # we manually call QRF.add_device later.
        super(QRF_DDS, self).__init__(name, parent_device, connection, call_parents_add_device=False)

        # allow digital_gate to be None instead of empty dict
        if digital_gate is None: digital_gate = {}

        # mode selection
        modes = [k for k, m in MODES.items() if m != MODE_ADVANCED]
        if mode is None:
            self.mode_value = MODE_BASIC
            self.mode_name  = [name for name, mode in MODES.items() if mode == self.mode_value][0]
        elif (not isinstance(mode, str)) or (mode not in MODES):
            raise LabscriptError("channel '%s' mode '%s' invalid! use one of these modes: %s" % (name, mode, str(modes)))
        else:
            self.mode_name = mode
            self.mode_value = MODES[mode]
            if self.mode_value == MODE_ADVANCED:
                raise LabscriptError("channel '%s' mode '%s' not implemented! use one of the other modes: %s" % (name, mode, str(modes)))
            if mode in MODES_WITH_GATE:
                if (DEVICE_INFO_GATE_DEVICE not in digital_gate or DEVICE_INFO_GATE_CONNECTION not in digital_gate):
                    raise LabscriptError("channel '%s' mode '%s' requires to give digital_gate with '%s' and '%s' entries!" % (name, mode, DEVICE_INFO_GATE_DEVICE, DEVICE_INFO_GATE_CONNECTION))
            elif len(digital_gate) != 0:
                raise LabscriptError("channel '%s' mode '%s' does not need digital_gate!\nset it to empty dictionary or remove from channel definition." % (name, mode))
            if mode in MODES_WITH_CHANNEL_TRIGGER:
                if (trigger_duration is None or trigger_delay is None):
                    raise LabscriptError("channel '%s' mode '%s' requires trigger_duration and trigger_delay to be specified!" % (name, mode))
            elif (trigger_duration is not None or trigger_delay is not None):
                raise LabscriptError("channel '%s' mode '%s' does not need trigger_duration or trigger_delay!\ndset them to None or removed from channel definition." % (name, mode))
            # note: we check MODES_WITH_GLOBAL_TRIGGER in split_connection

        if self.mode_value == MODE_BASIC:
            # init static DDS
            # note: this calls QRF.add_device (call_parents_add_device does not work!)
            self.dds = StaticDDS(name + DDS_NAME_STATIC, parent_device, connection, digital_gate.copy(),
                                 freq_limits, freq_conv_class, freq_conv_params,
                                 amp_limits, amp_conv_class, amp_conv_params,
                                 phase_limits, phase_conv_class, phase_conv_params,
                                 )
        else:
            # init dynamic dds class
            # note: this calls QRF.add_device
            self.dds = DDS(name + DDS_NAME_DYNAMIC, parent_device, connection, digital_gate.copy(),
                           freq_limits, freq_conv_class, freq_conv_params,
                           amp_limits, amp_conv_class, amp_conv_params,
                           phase_limits, phase_conv_class, phase_conv_params,
                           )

        # device capabilities
        props_freq  = {PROP_UNIT: PROP_UNIT_MHZ,    PROP_MIN: F_MIN, PROP_MAX: F_MAX, PROP_STEP: F_STEP, PROP_DEC: F_DEC}
        props_amp   = {PROP_UNIT: PROP_UNIT_DBM,    PROP_MIN: A_MIN, PROP_MAX: A_MAX, PROP_STEP: A_STEP, PROP_DEC: A_DEC}
        props_phase = {PROP_UNIT: PROP_UNIT_DEGREE, PROP_MIN: P_MIN, PROP_MAX: P_MAX, PROP_STEP: P_STEP, PROP_DEC: P_DEC}

        if freq_limits is not None:
            if freq_limits[0] is not None:
                props_freq.update({PROP_MIN: freq_limits[0]})
            if freq_limits[1] is not None:
                props_freq.update({PROP_MAX: freq_limits[0]})

        if amp_limits is not None:
            if amp_limits[0] is not None:
                props_amp.update({PROP_MIN: amp_limits[0]})
            if amp_limits[1] is not None:
                props_amp.update({PROP_MAX: amp_limits[1]})

        if phase_limits is not None:
            if phase_limits[0] is not None:
                props_phase.update({PROP_MIN: amp_limits[0]})
            if phase_limits[1] is not None:
                props_phase.update({PROP_MAX: amp_limits[1]})

        # save capabilities into device.properties
        # these will be used by iPCdev/blacs_tabs to set DDS properly in GUI
        self.dds.set_property(DDS_CHANNEL_PROP_FREQ , props_freq , location='connection_table_properties')
        self.dds.set_property(DDS_CHANNEL_PROP_AMP  , props_amp  , location='connection_table_properties')
        self.dds.set_property(DDS_CHANNEL_PROP_PHASE, props_phase, location='connection_table_properties')

        # save mode into device.properties
        self.dds.set_property(DDS_CHANNEL_PROP_MODE, self.mode_name, location='connection_table_properties')

        # save mode, trigger_delay and trigger_duration into DDS channel.
        # mode is needed in QRF.add_device. TODO: can this be removed?
        # trigger_delay/duration is needed for iPCdev.prepare_generate_code if digital_gate is given.
        self.dds.mode_name        = self.mode_name
        if False: # disabled since prepare_generate_code is not needed anymore
            self.dds.trigger_delay    = trigger_delay
            self.dds.trigger_duration = trigger_duration
        else: # insert gate commands in check_mode
            self.trigger_delay    = trigger_delay
            self.trigger_duration = trigger_duration

        # manually call QRF.add_device to check consistent channel modes.
        parent_device.add_device(self)

    def check_mode(self, allowed_modes, name, call_requires_time=None, time=None):
        """
        checks if the function 'name' call is allowed in the allowed modes.
        if call_requires_time is None: function is not existing in the actual mode.
        if call_requires_time = True/False: function needs/does not need time to be given but is not allowed in the current mode.
        when function call is allowed time is given and mode requires gate commands inserts the gate command
        """
        # check mode
        if self.mode_value not in allowed_modes:
            if call_requires_time is None:
                raise LabscriptError("device '%s' in mode '%s' has no function '%s'!" % (self.name, self.mode_name, name))
            elif call_requires_time:
                raise LabscriptError("device '%s' in mode '%s' requires call to '%s' without time!" % (self.name, self.mode_name, name))
            else:
                raise LabscriptError("device '%s' in mode '%s' requires call to '%s' with time!" % (self.name, self.mode_name, name))
        if call_requires_time and time is not None and self.mode_value in MODE_VALUES_WITH_CHANNEL_TRIGGER:
            #print(self.name, 'insert gate', time, self.dds.gate.instructions)
            t_start = np.round(time - self.trigger_delay, ROUND_DIGITS)
            t_end   = np.round(t_start + self.trigger_duration, ROUND_DIGITS)
            if t_start in self.dds.gate.instructions: # existing instruction
                value = self.dds.gate.instructions[t_start]
                if not isinstance(value, int) or value != 1:
                    raise LabscriptError("device '%s' in mode '%s' function '%s' at time %f collides with existing gate instruction at time %f (required gate.go_high): %s!\nplease choose a different time and check consistency with trigger delay %f and trigger duration %f" % (self.name, self.mode_name, name, time, t_start, str(value), self.trigger_delay, self.trigger_duration))
            elif t_end in self.dds.gate.instructions:  # existing instruction
                value = self.dds.gate.instructions[t_end]
                if not isinstance(value, int) or value != 0:
                    raise LabscriptError("device '%s' in mode '%s' function '%s' at time %f collides with existing gate instruction at time %f (required gate.to_low): %s!\nplease choose a different time and check consistency with trigger delay %f and trigger duration %f" % (self.name, self.mode_name, name, time, t_end, str(value), self.trigger_delay, self.trigger_duration))
            else:
                # insert gate command in channel trigger mode
                self.dds.enable (t_start)
                self.dds.disable(t_start + self.trigger_duration)

    def setamp(self, arg1, arg2=None, units=None):
        if units is not None: # 3 parameters passed: time, value, units
            self.check_mode(allowed_modes=MODE_VALUES_DYNAMIC, name='setamp', call_requires_time=True, time=arg1)
            self.dds.setamp(t=arg1, value=arg2, units=units)
        elif arg2 is not None:
            if isinstance(arg2, str): # 2 parameters passed: value, units
                self.check_mode(allowed_modes=MODE_VALUES_STATIC, name='setamp', call_requires_time=False)
                self.dds.setamp(value=arg1, units=arg2)
            else: # 2 parameters passed: time, value
                self.check_mode(allowed_modes=MODE_VALUES_DYNAMIC, name='setamp', call_requires_time=True, time=arg1)
                self.dds.setamp(t=arg1, value=arg2)
        else: # 1 parameter passed: value
            self.check_mode(allowed_modes=MODE_VALUES_STATIC, name='setamp', call_requires_time=False)
            self.dds.setamp(value=arg1)

    def setfreq(self, arg1, arg2=None, units=None):
        if units is not None: # 3 parameters passed: time, value, units
            self.check_mode(allowed_modes=MODE_VALUES_DYNAMIC, name='setfreq', call_requires_time=True, time=arg1)
            self.dds.setfreq(t=arg1, value=arg2, units=units)
        elif arg2 is not None:
            if isinstance(arg2, str): # 2 parameters passed: value, units
                self.check_mode(allowed_modes=MODE_VALUES_STATIC, name='setfreq', call_requires_time=False)
                self.dds.setfreq(value=arg1, units=arg2)
            else: # 2 parameters passed: time, value
                self.check_mode(allowed_modes=MODE_VALUES_DYNAMIC, name='setfreq', call_requires_time=True, time=arg1)
                self.dds.setfreq(t=arg1, value=arg2)
        else: # 1 parameter passed: value
            self.check_mode(allowed_modes=MODE_VALUES_STATIC, name='setfreq', call_requires_time=False)
            self.dds.setfreq(value=arg1)

    def setphase(self, arg1, arg2=None, units=None):
        if units is not None: # 3 parameters passed: time, value, units
            self.check_mode(allowed_modes=MODE_VALUES_DYNAMIC, name='setphase', call_requires_time=True, time=arg1)
            self.dds.setphase(t=arg1, value=arg2, units=units)
        elif arg2 is not None:
            if isinstance(arg2, str): # 2 parameters passed: value, units
                self.check_mode(allowed_modes=MODE_VALUES_STATIC, name='setphase', call_requires_time=False)
                self.dds.setphase(value=arg1, units=arg2)
            else: # 2 parameters passed: time, value
                self.check_mode(allowed_modes=MODE_VALUES_DYNAMIC, name='setphase', call_requires_time=True, time=arg1)
                self.dds.setphase(t=arg1, value=arg2)
        else: # 1 parameter passed: value
            self.check_mode(allowed_modes=MODE_VALUES_STATIC, name='setphase', call_requires_time=False)
            self.dds.setphase(value=arg1)

    def enable(self, t):
        self.check_mode(allowed_modes=MODE_VALUES_STATIC, name='enable')
        self.dds.enable(t)

    def disable(self, t):
        self.check_mode(allowed_modes=MODE_VALUES_STATIC, name='disable')
        self.dds.disable(t)

    # TODO: at the moment not supported
    #def pulse(self, t, duration, amplitude, frequency, phase=None, amplitude_units = None, frequency_units = None, phase_units = None, print_summary=False):
    #    self.check_mode(allowed_modes=MODE_VALUES_DYNAMIC, name='pulse')
    #    self.dds.pulse(t, duration, amplitude, frequency, phase, amplitude_units, frequency_units, phase_units, print_summary)

class QRF(iPCdev):

    # table timed trigger delay and duration
    trigger_delay            = 1e-6
    trigger_minimum_duration = 1e-6

    @set_passed_properties(
        property_names={'connection_table_properties': ['addr', 'port']}
    )
    def __init__(self, name, parent_device, trigger_connection=None, addr=None, port=DEFAULT_PORT, worker_args=None):
        if addr is None:  BLACS_connection = 'QRF module - simulated'
        else:             BLACS_connection = 'QRF module %s:%s' % (str(addr), str(port))

        # init parent iPCdev device
        super(QRF, self).__init__(
            name                = name,
            parent_device       = parent_device,
            trigger_connection  = trigger_connection,
            AO_rate             = 1e6,
            DO_rate             = None,
            worker_args         = worker_args,
            BLACS_connection    = BLACS_connection,
        )

        self.addr = addr
        self.port = port

    def add_device(self, device):
        """
        custom implementation of iPCdev.add_device.
        device = Pseudoclock, DDS, StaticDDS or QRF_DDS.
                 QRF_DDS is a container class for device.dds which is static or dynamic dds.
        """
        # check device is PseudoClock or QRF_DDS
        if isinstance (device, (Pseudoclock)):
            # Pseudocklock of intermediate device created by iPCdev.get_device
            #print('add_device:', device.name)
            return super(QRF, self).add_device(device)
        if isinstance(device, (DDS, StaticDDS)):
            # DDS created by QRF_DDS class
            #print('add_device:', device.name)
            return super(QRF, self).add_device(device)
        elif isinstance(device, QRF_DDS):
            #print('add_device:', device.name)
            # QRF_DDS class: check that channels have consistent modes
            if device.mode_name in MODES_WITH_GLOBAL_TRIGGER:
                # timed table modes require external start trigger on GLOBAL_TRIGGER_CHANNEL
                # this requires that channel 1 is in this mode as well - maybe could be still used in a mode without trigger.
                # check if this is not channel 1 that channel 1 must exist and must be in the same mode!
                channel = device.dds
                channel_index = channel.hardware_info[DEVICE_INFO_ADDRESS]
                if channel_index != GLOBAL_TRIGGER_CHANNEL:
                    found = False
                    for ps in self.child_devices:
                        for cl in ps.child_devices:
                            for im in cl.child_devices:
                                for ch in im.child_devices:
                                    if ch.hardware_info[DEVICE_INFO_CHANNEL] == GLOBAL_TRIGGER_CHANNEL:
                                        if ch.mode_name not in MODES_WITH_GLOBAL_TRIGGER:
                                            raise LabscriptError(
                                                "device '%s', channel %i mode '%s' requires that '%s', channel %i is in the same mode but is in mode '%s'!\nIf any channel is in mode '%s' the start trigger must be connected on channel %i trigger input and this input cannot be used anymore for channel %i.\nTherefore, use channel %i if this mode is required." % (
                                                    device.name, channel_index, device.mode_name, ch.name,
                                                    GLOBAL_TRIGGER_CHANNEL, ch.mode_name, device.mode_name,
                                                    GLOBAL_TRIGGER_CHANNEL, GLOBAL_TRIGGER_CHANNEL,
                                                    GLOBAL_TRIGGER_CHANNEL))
                                        found = True
                                        break
                                if found: break
                            if found: break
                        if found: break
                    if not found:
                        raise LabscriptError(
                            "device '%s' channel %i mode '%s' requires that channel %i is in the same mode but is not defined!\nPlease initialize channel %i in mode '%s' even if it is not used and attach the start trigger on channel %i trigger input." % (
                                device.name, channel_index, channel.mode_name, GLOBAL_TRIGGER_CHANNEL,
                                GLOBAL_TRIGGER_CHANNEL, channel.mode_name, GLOBAL_TRIGGER_CHANNEL))
        else:
            raise LabscriptError("device '%s', type '%s' added to '%s' but only QRF_DDS are allowed!" % (device.name, type(device), self.name))

    def split_connection(self, channel):
        """
        custom implementation from iPCdev class. for details see there.
        channel = DDS or STATIC_DDS.
        returns (clockline name, hardware_info) for given channel connection object
        implementation details:
        connection = "channel %i" % (channel) with channel = 1..MAX_NUm_CHANNELS
        """
        clockline_name = None
        hardware_info  = {}
        connection = channel.connection
        split = connection.split(CON_SEP)
        if not isinstance(channel, (DDS, StaticDDS)):
            raise LabscriptError('device %s (class %s) cannot be connected with %s! Only QRF_DDS are allowed!' % (channel.name, device.__class__, self.name))
        else:
            if isinstance(channel, StaticDDS):
                hardware_info[DEVICE_INFO_TYPE] = HARDWARE_TYPE_DDS + HARDWARE_SUBTYPE_STATIC + HARDWARE_ADDRTYPE_MULTIPLE
            else:
                hardware_info[DEVICE_INFO_TYPE] = HARDWARE_TYPE_DDS + HARDWARE_SUBTYPE_NONE + HARDWARE_ADDRTYPE_MULTIPLE
            if channel.gate is not None:
                hardware_info[DEVICE_INFO_GATE] = {DEVICE_INFO_GATE_DEVICE: channel.gate.name, DEVICE_INFO_GATE_CONNECTION: channel.gate.connection}
            if len(split) == 2 and split[0].startswith(CON_CHANNEL_NAME):
                clockline_name                     = CLOCKLINE_NAME % channel.name
                hardware_info[DEVICE_INFO_ADDRESS] = str(channel.parent_device.addr) # str() since address mignt be None
                try:
                    channel_index = hardware_info[DEVICE_INFO_CHANNEL] = int(split[1])
                except ValueError:
                    clockline_name = None
            if clockline_name is None:
                raise LabscriptError("DDS '%s' connection '%s' invalid!\ngive 'channel %%i'%%channel." % (channel.name, connection))
            # check channel index and existing channels
            if (channel_index < 1) or (channel_index > MAX_NUM_CHANNELS):
                raise ValueError("DDS '%s' channel %i must be in range 1 .. %i!" % (channel.name, channel_index, MAX_NUM_CHANNELS))
            else:
                used = [c.hardware_info[DEVICE_INFO_CHANNEL] for c in self.child_devices if c.hardware_info[DEVICE_INFO_TYPE][HARDWARE_TYPE] == HARDWARE_TYPE_DDS]
                available = [i for i in range(1, MAX_NUM_CHANNELS+1) if i not in used]
                if channel_index in used:
                    if len(available) == 0:
                        raise ValueError("DDS '%s' channel %i cannot be added to '%s'! all possible 1..%i channels already defined." % (channel.name, channel_index, self.name, MAX_NUM_CHANNELS))
                    else:
                        raise ValueError("DDS '%s' channel %i already used for '%s'! free channel numbers: %s" % (channel.name, channel_index, self.name, str(available)))

        #print(self.name, 'split_connection (QRF):', channel.name, 'clockline', clockline_name, 'hw info', hardware_info)

        return clockline_name, hardware_info

