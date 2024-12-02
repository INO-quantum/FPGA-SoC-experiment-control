#####################################################################
#                                                                   #
# /NI_DAQmx/models/labscript_devices.py                             #
#                                                                   #
# Copyright 2018, Monash University, JQI, Christopher Billington    #
#                                                                   #
# This file is part of the module labscript_devices, in the         #
# labscript suite (see http://labscriptsuite.org), and is           #
# licensed under the Simplified BSD License. See the license.txt    #
# file in the root of the project for the full license.             #
#                                                                   #
#####################################################################

__version__ = '1.1.0'

# Jan-May 2024, modified by Andi to generate pseudoclock with NIDAQmx counter.
# last change 14/6/2024 by Andi

from labscript import (
    IntermediateDevice,
    AnalogOut,
    DigitalOut,
    StaticAnalogOut,
    StaticDigitalOut,
    AnalogIn,
    bitfield,
    config,
    compiler,
    LabscriptError,
    set_passed_properties,
    Pseudoclock,
    ClockLine,
    PseudoclockDevice,
)

from labscript_utils import dedent
import numpy as np
import warnings
from time import perf_counter as get_ticks

from user_devices.iPCdev.labscript_devices import (
    iPCdev, iPCdev_device,
    HARDWARE_TYPE, HARDWARE_TYPE_AO, HARDWARE_TYPE_DO, HARDWARE_TYPE_DDS,
    HARDWARE_SUBTYPE, HARDWARE_SUBTYPE_NONE, HARDWARE_SUBTYPE_STATIC, HARDWARE_SUBTYPE_TRIGGER,
    HARDWARE_ADDRTYPE, HARDWARE_ADDRTYPE_SINGLE, HARDWARE_ADDRTYPE_MERGED,
    DEVICE_HARDWARE_INFO, DEVICE_INFO_TYPE, DEVICE_INFO_ADDRESS, DEVICE_INFO_CHANNEL,
)

_ints = {8: np.uint8, 16: np.uint16, 32: np.uint32, 64: np.uint64}

def _smallest_int_type(n):
    """Return the smallest unsigned integer type sufficient to contain n bits"""
    return _ints[min(size for size in _ints.keys() if size >= n)]

# indices of counter_AO and counter_DO in internal self.counters list
INDEX_NUM = 2
INDEX_AO = 0
INDEX_DO = 1

# connection format
CON_SEP         = '/'
CON_DO_PORT     = 'port'
CON_DO_LINE     = 'line'
CON_AO          = 'ao'

# counter name constructed from MAX_name
# note: counters must start with '/' otherwise NI-DAQmx gives an error. MAX_name does not need this.
#       we take care of this. user can give counter and MAX_name with or without initial '/'.
COUNTER_NAME    = CON_SEP + '%s' + CON_SEP + 'ctr%i'

# static clockline name returned by split_connection. this is not a counter.
STATIC_NAME_AO  = '%s_ao_%s'
STATIC_NAME_DO  = '%s_do_%s'

# start trigger edge names
START_TRIGGER_EDGE_RISING   = 'rising'
START_TRIGGER_EDGE_FALLING  = 'falling'

# internal clock rate in Hz of DAQmx cards
# overwrite with internal_clock_rate in connection table
DAQMX_INTERNAL_CLOCKRATE    = 100e6

class NI_DAQmx_iPCdev(iPCdev):

    # use shared clockline between boards
    iPCdev.shared_clocklines = True

    @set_passed_properties(
        property_names={
            "connection_table_properties": [
                "MAX_name",
                "counter_AO",
                "counter_DO",
                "clock_terminal",
                "clock_rate",
                "clock_mirror_terminal",
                "internal_clock_rate",
                "start_trigger_terminal",
                "start_trigger_edge",
                "connected_terminals",
                "num_CI",
                "num_AO",
                "supports_buffered_AO",
                "static_AO",
                "max_AO_sample_rate",
                "AO_range",
                "ports",
                "supports_buffered_DO",
                "static_DO",
                "max_DO_sample_rate",
                "num_AI",
                "acquisition_rate",
                "AI_range",
                "AI_range_Diff",
                "AI_start_delay",
                "AI_start_delay_ticks",
                "AI_term",
                "AI_term_cfg",
                "AI_chans",
                "max_AI_multi_chan_rate",
                "max_AI_single_chan_rate",
                "min_semiperiod_measurement",
                "supports_semiperiod_measurement",
                "supports_simultaneous_AI_sampling",
                "wait_monitor_minimum_pulse_width",
                "wait_monitor_supports_wait_completed_events",
            ],
            "device_properties": ["acquisition_rate","start_delay_ticks"],
        }
    )
    def __init__(self,
                 name,
                 MAX_name,
                 counter_AO,
                 counter_DO,
                 parent_device = None,
                 worker_args={},
                 BLACS_connection='NI-DAQmx internal pseudoclock device v1.0 by Andi',
                 # external terminals (clock and trigger)
                 clock_terminal=None,
                 clock_rate=1e6,
                 clock_mirror_terminal=None,
                 internal_clock_rate=DAQMX_INTERNAL_CLOCKRATE,
                 start_trigger_terminal=None,
                 start_trigger_edge='rising',
                 connected_terminals=None,
                 # counter (half used as output, input not possible)
                 num_CI=0,
                 # analog out
                 num_AO=0,
                 supports_buffered_AO=False,
                 static_AO=None,
                 max_AO_sample_rate=None,
                 AO_range=None,
                 # digital out
                 ports=None,
                 supports_buffered_DO=False,
                 static_DO=None,
                 max_DO_sample_rate=None,
                 # analog in (not implemented)
                 num_AI=0,
                 acquisition_rate=None,
                 AI_range=None,
                 AI_range_Diff=None,
                 AI_start_delay=0,
                 AI_start_delay_ticks=None,
                 AI_term='RSE',
                 AI_term_cfg=None,
                 AI_chans=None,
                 max_AI_multi_chan_rate=None,
                 max_AI_single_chan_rate=None,
                 min_semiperiod_measurement=None,
                 supports_semiperiod_measurement=False,
                 supports_simultaneous_AI_sampling=False,
                 # wait monitor (not implemented)
                 wait_monitor_minimum_pulse_width=None,
                 wait_monitor_supports_wait_completed_events=None,
                 **kwargs):

        """Generic class for NI_DAQmx devices.

        Generally over-ridden by device-specific subclasses that contain
        the introspected default values.

        Args:
            name (str): name to assign to the created labscript device
            parent_device (clockline): Parent clockline device that will
                clock the outputs of this device
            clock_terminal (str): What input on the DAQ is used for the clockline
            MAX_name (str): NI-MAX device name
            static_AO (int, optional): Number of static analog output channels.
            static_DO (int, optional): Number of static digital output channels.
            clock_mirror_terminal (str, optional): Channel string of digital output
                that mirrors the input clock. Useful for daisy-chaning DAQs on the same
                clockline.
            acquisiton_rate (float, optional): Default sample rate of inputs.
            AI_range (iterable, optional): A `[Vmin, Vmax]` pair that sets the analog
                input voltage range for all analog inputs.
            AI_range_Diff (iterable, optional): A `[Vmin, Vmax]` pair that sets the analog
                input voltage range for all analog inputs when using Differential termination.
            AI_start_delay (float, optional): Time in seconds between start of an
                analog input task starting and the first sample.
            AI_start_delay_ticks (int, optional): Time in sample clock periods between
                start of an analog input task starting and the first sample. To use
                this method, `AI_start_delay` must be set to `None`. This is necessary
                for DAQs that employ delta ADCs.
            AI_term (str, optional): Configures the analog input termination for all
                analog inputs. Must be supported by the device. Supported options are
                `'RSE'`, `'NRSE'` `'Diff'`, and '`PseudoDiff'`.
            AI_term_cfg (dict, optional): Dictionary of analog input channels and their
                supported terminations. Best to use `get_capabilities.py` to introspect
                these.
            AO_range (iterable, optional): A `[Vmin, Vmax]` pair that sets the analog
                output voltage range for all analog outputs.
            max_AI_multi_chan_rate (float, optional): Max supported analog input
                sampling rate when using multiple channels.
            max_AI_single_chan_rate (float, optional): Max supported analog input
                sampling rate when only using a single channel.
            max_AO_sample_rate (float, optional): Max supported analog output
                sample rate.
            max_DO_sample_rate (float, optional): Max supported digital output
                sample rate.
            min_sermiperiod_measurement (float, optional): Minimum measurable time
                for a semiperiod measurement.
            num_AI (int, optional): Number of analog inputs channels.
            num_AO (int, optional): Number of analog output channels.
            num_CI (int, optional): Number of counter input channels.
            ports (dict, optional): Dictionarly of DIO ports, which number of lines
                and whether port supports buffered output.
            supports_buffered_AO (bool, optional): True if analog outputs support
                buffered output
            supports_buffered_DO (bool, optional): True if digital outputs support
                buffered output
            supports_semiperiod_measurement (bool, optional): True if device supports
                semi-period measurements

        """
        # init parent iPCdev device
        super(NI_DAQmx_iPCdev, self).__init__(
            name = name,
            parent_device = parent_device,
            AO_rate = max_AO_sample_rate,
            DO_rate = max_DO_sample_rate,
            worker_args = worker_args,
            BLACS_connection = BLACS_connection,
        )

        # set MAX name. None can be used only for simulation.
        self.MAX_name = MAX_name if MAX_name is not None else name

        # for digital out we have 8 bits per port, so we can reduce the data width of combine_channel_data.
        # alternatively, we could overload this static function.
        if self.primary is None: iPCdev.DO_type = np.uint8

        # the counters define the clocklines which we need.
        # they can be shared between devices. see add_device.
        # we ensure they start with '/' otherwise NI-DAQmx gives and error.
        if (counter_AO is None) and (counter_DO is None):
            raise LabscriptError("'%s' class '%s' needs at least one counter!"%(s, type(self)))
        self.counter_AO = counter_AO if (counter_AO is None or counter_AO.startswith(CON_SEP)) else CON_SEP + counter_AO
        self.counter_DO = counter_DO if (counter_DO is None or counter_DO.startswith(CON_SEP)) else CON_SEP + counter_DO

        # create counter = clocklines of actual board independent of self.counter_AO/DO
        # only half of the counters can be used since always 2 and 2 are linked.
        # note: self.counters_DO/AO might be belonging to another board and might not yet be created!
        #       they are returned as clockline_name by split_connection for each added channel.
        #       the clockline_name here must match, otherwise an error is generated.
        self.num_CI = num_CI
        for i in range(self.num_CI//2):
            clockline_name = COUNTER_NAME % (MAX_name.replace(CON_SEP,''), i)
            device = super(NI_DAQmx_iPCdev, self).get_device(clockline_name, True)
            print('%s creating counter %s' % (self.name, clockline_name))

        # Default static output setting based on whether the device supports buffered
        # output:
        self.static_AO = static_AO
        self.static_DO = static_DO
        if static_AO is None:
            static_AO = not supports_buffered_AO
        if static_DO is None:
            static_DO = not supports_buffered_DO

        if acquisition_rate is not None and num_AI == 0:
            msg = "Cannot set set acquisition rate on device with no analog inputs"
            raise ValueError(msg)
        # Acquisition rate cannot be larger than the single channel rate:
        if acquisition_rate is not None and acquisition_rate > max_AI_single_chan_rate:
            msg = """acquisition_rate %f is larger than the maximum single-channel rate
                %f for this device"""
            raise ValueError(dedent(msg) % (acquisition_rate, max_AI_single_chan_rate))

        self.acquisition_rate = acquisition_rate
        self.AO_range = AO_range
        self.max_AI_multi_chan_rate = max_AI_multi_chan_rate
        self.max_AI_single_chan_rate = max_AI_single_chan_rate
        self.max_AO_sample_rate = max_AO_sample_rate
        self.max_DO_sample_rate = max_DO_sample_rate
        self.min_semiperiod_measurement = min_semiperiod_measurement
        self.num_AI = num_AI
        # special handling for AI termination configurations
        self.AI_term = AI_term
        if num_AI > 0:
            if AI_term_cfg == None:
                # assume legacy configuration if none provided
                AI_term_cfg = {f'ai{i:d}': ['RSE'] for i in range(num_AI)}
                # warn user to update their local model specs
                msg = """Model specifications for {} needs to be updated.
                    Please run the `get_capabilites.py` and `generate_subclasses.py`
                    scripts or define the `AI_Term_Cfg` kwarg for your device.
                    """
                warnings.warn(dedent(msg.format(self.description)), FutureWarning)
            self.AI_chans = [key for key,val in AI_term_cfg.items() if self.AI_term in val]
            if not len(self.AI_chans):
                msg = """AI termination {0} not supported for {1}."""
                raise LabscriptError(dedent(msg.format(AI_term,self.description)))
            if AI_term == 'Diff':
                self.AI_range = AI_range_Diff
            if AI_start_delay is None:
                if AI_start_delay_ticks is not None:
                    # Tell blacs_worker to use AI_start_delay_ticks to define delay
                    self.start_delay_ticks = True
                else:
                    raise LabscriptError("You have specified `AI_start_delay = None` but have not provided `AI_start_delay_ticks`.")
            else:
                # Tells blacs_worker to use AI_start_delay to define delay
                self.start_delay_ticks = False
        else:
            # no analog inputs
            self.AI_chans = []
            self.start_delay_ticks = None
        self.num_AO = num_AO
        self.ports = ports if ports is not None else {}
        self.supports_buffered_AO = supports_buffered_AO
        self.supports_buffered_DO = supports_buffered_DO
        self.supports_semiperiod_measurement = supports_semiperiod_measurement
        self.supports_simultaneous_AI_sampling = supports_simultaneous_AI_sampling

        if self.supports_buffered_DO and self.supports_buffered_AO:
            self.clock_limit = min(self.max_DO_sample_rate, self.max_AO_sample_rate)
        elif self.supports_buffered_DO:
            self.clock_limit = self.max_DO_sample_rate
        elif self.supports_buffered_AO:
            self.clock_limit = self.max_AO_sample_rate
        else:
            self.clock_limit = None
            if not (static_AO and static_DO):
                msg = """Device does not support buffered output, please instantiate
                it with static_AO=True and static_DO=True"""
                raise LabscriptError(dedent(msg))

        self.wait_monitor_minimum_pulse_width = self.min_semiperiod_measurement

        #if clock_terminal is None and not (static_AO and static_DO):
         #   msg = """Clock terminal must be specified unless static_AO and static_DO are
          #      both True"""
           # raise LabscriptError(dedent(msg))

        self.BLACS_connection = self.MAX_name

        # Cannot be set with set_passed_properties because of name mangling with the
        # initial double underscore:
        self.set_property('__version__', __version__, 'connection_table_properties')

        if self.primary is None:
            iPCdev.DO_type = np.uint8

    ###############################################################
    # derived class implementation                                #
    ###############################################################

    def split_connection(self, channel):
        """
        custom implementation from iPCdev class. for details see there.
        implementation details:
        for analog  out connection = "ao%i" % (address)
        for digital out connection = "port%i/line%i" % (address, channel)
        """
        clockline_name = None
        hardware_info  = {}
        connection = channel.connection
        if connection[0] == CON_SEP: connection = connection[1:] # remove initial '/' if given
        split = connection.split(CON_SEP)
        if isinstance(channel, (AnalogOut, StaticAnalogOut)): # ao%i
            static = isinstance(channel, StaticAnalogOut)
            hardware_info[DEVICE_INFO_TYPE] = HARDWARE_TYPE_AO + (HARDWARE_SUBTYPE_STATIC if static else HARDWARE_SUBTYPE_NONE) + HARDWARE_ADDRTYPE_SINGLE
            if self.counter_AO is None:
                raise LabscriptError("AO device '%s' connection '%s' but no counter given!\ngive a valid couner_AO for board '%s'." % (channel.name, connection, self.name))
            try:
                if len(split) == 1 and split[0].startswith(CON_AO):
                    clockline_name                     = (STATIC_NAME_AO % (channel.name, split[0])) if static else self.counter_AO
                    hardware_info[DEVICE_INFO_ADDRESS] = int(split[0][len(CON_AO):])
                    hardware_info[DEVICE_INFO_CHANNEL] = None
            except ValueError:
                clockline_name = None
            if clockline_name is None:
                raise LabscriptError("AO device '%s' connection '%s' invalid!\ngive 'ao%%i'%%address with address as decimal or hex (with prefix 0x) integer." % (channel.name, connection))
            # checks
            if (self.num_AO == 0) or ((self.num_AO != 32) and (self.num_AO != 8)) or \
               ((self.num_AO == 32) and (hardware_info[DEVICE_INFO_ADDRESS] >= self.num_AO)) or \
               ((self.num_AO == 8)  and (hardware_info[DEVICE_INFO_ADDRESS] >= self.num_AO*4)):
                raise ValueError("Cannot add output with connection string '%s' to device with num_AO=%d" % (connection, self.num_AO))
        elif isinstance(channel, (DigitalOut, StaticDigitalOut)):
            static = isinstance(channel, StaticDigitalOut)
            hardware_info[DEVICE_INFO_TYPE] = HARDWARE_TYPE_DO + (HARDWARE_SUBTYPE_STATIC if static else HARDWARE_SUBTYPE_NONE) + HARDWARE_ADDRTYPE_MERGED
            if self.counter_DO is None:
                raise LabscriptError("DO device '%s' connection '%s' but no counter given!\ngive a valid couner_DO for board '%s'." % (channel.name, connection, self.name))
            try:
                if len(split) == 2 and split[0].startswith(CON_DO_PORT) and split[1].startswith(CON_DO_LINE):
                    clockline_name                            = (STATIC_NAME_DO % (self.name, split[0])) if static else self.counter_DO
                    port = hardware_info[DEVICE_INFO_ADDRESS] = int(split[0][len(CON_DO_PORT):])
                    line = hardware_info[DEVICE_INFO_CHANNEL] = int(split[1][len(CON_DO_LINE):])
            except ValueError:
                clockline_name = None
            if clockline_name is None:
                raise LabscriptError("DO device '%s' connection '%s' invalid!\ngive 'port%i/line%i'%(port,line) with port and line as decimal or hex (with prefix 0x) integer." % (name, connection))
            # checks
            port_str = 'port%d' % port
            if port_str not in self.ports:
                raise ValueError("Parent device has no such DO port '%s'" % port_str)
            nlines = self.ports[port_str]['num_lines']
            if line >= nlines:
                raise ValueError("Cannot add output with connection string '%s' to port '%s' with only %d lines" % (connection, port_str, nlines))
            #using a buffered output as static should still work
            #if static and self.ports[port_str]['supports_buffered']:
            #    raise ValueError("Cannot add StaticDigitalOut port '%s', which supports buffered output" % port_str)
            if not static and not self.ports[port_str]['supports_buffered']:
                raise ValueError("Cannot add DigitalOut port '%s', which does not support buffered output" % port_str)
        else:
            raise LabscriptError('You have connected %s (class %s) to %s, but does not support children with that class.'%(channel.name, device.__class__, self.name))

        return clockline_name, hardware_info

    def add_device(self, device):
        """
        add given device to board.
        this only calls the super class implementation but with allow_create_new=False
        this ensures that no clockline is created in addition to counters.
        exception: static channels.
        """

        #notes:
        # - AnalogIn is not implemented
        # - we removed all static_AO/DO checks since we allow mixed static and dynamic channels.
        #   but I do not know if the NI devices allow this however.

        # call iPCdev implementation which calls self.split_connection here
        # this should not create a new clockline = counter device since they should already exist.
        if isinstance(device, (AnalogOut, DigitalOut)):
            allow_create_new = False
        elif isinstance(device, (Pseudoclock, StaticAnalogOut, StaticDigitalOut)):
            allow_create_new = True
        else:
            raise LabscriptError("%s device %s type %s cannot be added!" % (self.name, device.name, type(device).__name__))
        #print(self.name, 'add_device', device.name)
        super(NI_DAQmx_iPCdev, self).add_device(device, allow_create_new=allow_create_new)

# create NI devices from existing labscript_devices.NI_DAQmx models
import labscript_devices.NI_DAQmx.models as models
import sys

def create_class(class_name, caps):
    "create device specific inherited class"
    def __init__(self, *args, **kwargs):
        combined_kwargs = caps.copy()
        combined_kwargs.update(kwargs)
        NI_DAQmx_iPCdev.__init__(self, *args, **combined_kwargs)
    return type(class_name, (NI_DAQmx_iPCdev,), {'__init__':__init__})

# go through all models and create class inside this package
for model_name in models.capabilities:
    caps=models.capabilities[model_name]
    cls = create_class('NI_' + model_name.replace('-','_') + '_iPCdev', caps)
    setattr(sys.modules[cls.__module__], cls.__name__, cls)
    del cls