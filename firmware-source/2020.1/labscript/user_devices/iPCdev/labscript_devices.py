# internal pseudoclock device
# created April 2024 by Andi
# last change 14/6/2024 by Andi

# TODO: when needed implement split_connection, combine_channel_data, extract_channel_data and generate_code for your device.

from labscript import (
    IntermediateDevice,
    AnalogOut, StaticAnalogOut,
    DigitalOut, StaticDigitalOut, Trigger,
    DDS, StaticDDS,
    LabscriptError,
    Pseudoclock,
    ClockLine,
    PseudoclockDevice,
    set_passed_properties,
    config,
)

import numpy as np
from time import perf_counter as get_ticks

# reduce number of log entries in logfile (labscript-suite/logs/BLACS.log)
import logging
log_level = [logging.CRITICAL, logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG, logging.NOTSET][2]

# for testing
#from user_devices.h5_file_parser import read_file, read_group

# connection strings
CON_SEP                 = '/'
CON_PS                  = 'ps'
CON_CL                  = 'cl'

# clockline name returned by split_connection for board name + type + address
NAME_CLOCKLINE          = '%s_%s_%s'
NAME_AO                 = 'ao'
NAME_DO                 = 'do'
NAME_STATIC_AO          = 'ao_static'
NAME_STATIC_DO          = 'do_static'
NAME_DDS                = 'dds'
NAME_VIRTUAL            = 'virtual'
# pseudoclock, clockline and device name format strings for given clockline name
# NAME_DEV is displayed in runviwer_parser to user for the clockline. others are not visible to user.
NAME_PS                 = '%s_ps'
NAME_CL                 = '%s_cl'
NAME_DEV                = '%s_clock'

# virtual IM device. we use same connection format as digital channels.
VIRTUAL_ADDR            = '0'
VIRTUAL_CON             = VIRTUAL_ADDR + CON_SEP + '%i'

# hardware type to discriminate general device types.
# using isinstance or device.device_class is too specific especially for derived types.
# this way generate_code and device_tabs can also handle derived types.
# implementation as string of 3 letters:
# major   type = first  letter: analog/digital/dds outputs
# sub     type = second letter: static, trigger, virtual, etc.
# address tupe = third  letter: how address and dats is combined
# intermediated devices must have the same major type but can have mixed sub-types
HARDWARE_TYPE               = 0
HARDWARE_TYPE_AO            = 'a'       # analog output
HARDWARE_TYPE_DO            = 'd'       # digital output
HARDWARE_TYPE_DDS           = 'f'       # DDS output
HARDWARE_TYPE_PS            = 'p'       # pseudoclock
HARDWARE_SUBTYPE            = 1
HARDWARE_SUBTYPE_NONE       = '-'
HARDWARE_SUBTYPE_STATIC     = 's'       # static
HARDWARE_SUBTYPE_TRIGGER    = 't'       # trigger device
HARDWARE_SUBTYPE_VIRTUAL    = 'v'       # virtual
HARDWARE_ADDRTYPE           = 2
HARDWARE_ADDRTYPE_NONE      = '-'
HARDWARE_ADDRTYPE_SINGLE    = 'a'       # analog  like: one address per channel: single data
HARDWARE_ADDRTYPE_MERGED    = 'd'       # digital like: shared address for several channels: merged into single data
HARDWARE_ADDRTYPE_MULTIPLE  = 'f'       # DDS     like: shared address for several channels: list of data per channel

# hd5 file name format for each IM device
# TODO: allow address to be string, like IP address. for DDS already done.
DEVICE_SEP              = '/'
DEVICE_DEVICES          = 'devices'
DEVICE_TIME             = 'time'
DEVICE_DATA_AO          = 'data_ao_%s_%x'       # name + address
DEVICE_DATA_DO          = 'data_do_%s_%x'       # board name + address
DEVICE_DATA_DDS         = 'data_dds_%s_%s_%s'   # name + address + sub-channel name

# hardware info entry in connection table property
DEVICE_HARDWARE_INFO            = 'hardware_info'
DEVICE_INFO_PATH                = 'path'
DEVICE_INFO_ADDRESS             = 'address'
DEVICE_INFO_CHANNEL             = 'channel'
DEVICE_INFO_TYPE                = 'hardware_type'
DEVICE_INFO_BOARD               = 'parent_device'
DEVICE_INFO_GATE                = 'gate'
DEVICE_INFO_GATE_DEVICE         = 'device'
DEVICE_INFO_GATE_CONNECTION     = 'connection'

# margin for numberical uncertainties
TIME_EPSILON            = 1e-12

# number of digits labscript.add_instructions and other functions rounds times
ROUND_DIGITS = 10

class _iPCdev(Pseudoclock):
    def add_device(self, device):
        if isinstance(device, ClockLine):
            # only allow one child
            if self.child_devices:
                raise LabscriptError('The pseudoclock %s only supports 1 clockline, which is automatically created. Please use the clockline located at %s.clockline'%(self.parent_device.name, self.parent_device.name))
            Pseudoclock.add_device(self, device)
        else:
            raise LabscriptError('You have connected %s to %s (the pseudoclock of %s), but %s only supports children that are ClockLines. Please connect your device to %s.clockline instead.'%(device.name, self.name, self.parent_device.name, self.name, self.parent_device.name))

class iPCdev_device(IntermediateDevice):
    allowed_children = [DigitalOut, StaticDigitalOut, AnalogOut, StaticAnalogOut, DDS, StaticDDS, Trigger]

    description = 'iPCdev intermediate device'

    def __init__(self, name, parent_device, board_name, clockline_name):
        IntermediateDevice.__init__(self, name, parent_device)
        # save parent board name (parent_device is the clockine, not the board)
        self.board_name = board_name
        # set connection to clockline_name of split_connection and get_device.
        # this might be used by blacs_tabs or worker.
        self.connection = clockline_name
        # hardware type identifies the type of connected hardware. we allow only one type per IM device.
        self.hardware_type = None

    def add_device(self, device):
        # get hardware type
        if isinstance(device, Trigger):
            #print(self.name, 'add_device trigger', device.name)
            hardware_type = HARDWARE_TYPE_DO + HARDWARE_SUBTYPE_TRIGGER + HARDWARE_ADDRTYPE_MERGED
            # Trigger is automcatically created by labscript for secondary board(s)
            # we have to do the same as in iPCdev.add_device
            # TODO: use one function to do the same here and there?
            # 1. get clockline and hardware names. this uses always IPCdev implementation
            clockline_name, device.hardware_info = iPCdev.split_connection(self, device)
            # 2. save original parent_device name into hardware_info in case clockline is not of the same device.
            #    blacs_tabs uses this to display board devices only.
            device.hardware_info.update({DEVICE_INFO_BOARD:self.board_name})
            # 3. find or create intermediate device: not needed since this has already clockline/parent device.
            # 4. save device hardware information into connection table
            device.set_property(DEVICE_HARDWARE_INFO, device.hardware_info, location='connection_table_properties')
            # 5. add channel to intermediate device. done below.
        elif isinstance(device, (AnalogOut)):
            hardware_type = HARDWARE_TYPE_AO + HARDWARE_SUBTYPE_NONE + HARDWARE_ADDRTYPE_SINGLE
        elif isinstance(device, (StaticAnalogOut)):
            hardware_type = HARDWARE_TYPE_AO + HARDWARE_SUBTYPE_STATIC + HARDWARE_ADDRTYPE_SINGLE
        elif isinstance(device, (DigitalOut)):
            hardware_type = HARDWARE_TYPE_DO + HARDWARE_SUBTYPE_NONE + HARDWARE_ADDRTYPE_MERGED
        elif isinstance(device, (StaticDigitalOut)):
            hardware_type = HARDWARE_TYPE_DO + HARDWARE_SUBTYPE_STATIC + HARDWARE_ADDRTYPE_MERGED
        elif isinstance(device, DDS):
            hardware_type = HARDWARE_TYPE_DDS + HARDWARE_SUBTYPE_NONE + HARDWARE_ADDRTYPE_MULTIPLE
        elif isinstance(device, StaticDDS):
            hardware_type = HARDWARE_TYPE_DDS + HARDWARE_SUBTYPE_STATIC + HARDWARE_ADDRTYPE_MULTIPLE
        else:
            raise LabscriptError("device %s type %s added to device %s which is not allowed!" % (device.name, type(device), self.name))

        # check and set hardware type, sub-type and address type of IM device
        # type and address-type of all devices on the same IM device must be the same,
        # but we allow different sub-types, e.g. static and dynamic AO/DO channels or trigger and DO channels.
        if self.hardware_type is None:
            self.hardware_type = hardware_type
            # save hardware type and board into connection table.
            # this allows blacs_tab and worker to determine the board and type of clockline.
            hardware_info = {DEVICE_INFO_TYPE: self.hardware_type, DEVICE_INFO_BOARD: self.board_name}
            self.set_property(DEVICE_HARDWARE_INFO, hardware_info, location='connection_table_properties')
        else:
            if (self.hardware_type[HARDWARE_TYPE    ] != hardware_type[HARDWARE_TYPE    ]) or \
               (self.hardware_type[HARDWARE_ADDRTYPE] != hardware_type[HARDWARE_ADDRTYPE]):
                raise LabscriptError("device %s type %s added to intermediate device %s but already a different type %s existing!\nadd only same type to intermediate devices." % (device.name, hardware_type, self.name, self.hardware_type))
            # if a trigger device is added mark in the subtype trigger so we can easier find secondary boards in generate_code.
            if hardware_type[HARDWARE_SUBTYPE] == HARDWARE_SUBTYPE_TRIGGER:
                self.hardware_type = hardware_type

        # check if device was added directly (should not happen)
        if not hasattr(device, 'hardware_info'):
            board = self.parent_device.parent_device.parent_device
            raise LabscriptError("device %s type %s added directly to intermediate device %s!\nadd %s only to %s!" % (device.name, hardware_type, self.name, device.name, board.name))

        # add channel to intermediate device
        IntermediateDevice.add_device(self, device)

class iPCdev(PseudoclockDevice):

    description              = 'internal pseudoclock device'
    clock_limit              = 100e6 # large enough such that the limit comes from the devices
    clock_resolution         = 1e-9
    trigger_delay            = 0.0
    trigger_minimum_duration = 0.0
    wait_delay               = 0
    allowed_children         = [_iPCdev]
    max_instructions         = None

    # default data types for combine_channel_data
    AO_dtype            = np.float64
    DO_type             = np.uint32
    DDS_dtype           = np.float64

    # if True share clocklines between boards. if needed overwrite in derived class.
    shared_clocklines       = False

    def __init__(self,
                 name,
                 parent_device      = None,
                 trigger_connection = None,
                 AO_rate            = 1e6,
                 DO_rate            = 1e6,
                 worker_args        = {},
                 BLACS_connection   = 'internal pseudoclock device v1.0 by Andi',
                 ):

        self.name               = name
        self.parent_device      = parent_device         # None for primary device, otherwise give primary IPDdev or intermediate device.
        self.trigger_connection = trigger_connection    # None or connection if parent_device is intermediate device
        self.AO_rate            = AO_rate               # default maximum analog output rate in Hz
        self.DO_rate            = DO_rate               # default maximum digital output rate in Hz
        self.BLACS_connection   = BLACS_connection      # displayed in tab. not sure if used for something else?

        # find primary pseudoclock from parent_device
        # if this device is primary pseudoclock self.primary = None
        self.primary = parent_device
        while parent_device is not None:
            self.primary = parent_device
            parent_device = self.primary.parent_device

        # init device class
        if self.primary is None:
            print("iPCdev init primary '%s'" % (name))
            PseudoclockDevice.__init__(self, name, None, None)

            # for first IPCdev (= primary device) create virtual trigger IM device.
            # this is required to 'trigger' other (= secondary) IPCdev when the experiment starts.
            # since our boards (like FPGA_device) usually have their own trigger mechanism this is not a real hardware.
            # other boards (like PulseBlaster) might require real hardware to trigger.
            # another way is to trigger all boards from an external trigger (like a line trigger).
            self.virtual_device = self.get_device(NAME_CLOCKLINE % (self.name, NAME_VIRTUAL, VIRTUAL_ADDR), True)
        else:
            # secondary devices need a trigger_device which can be either:
            # - virtual trigger digital channel from the primary device:
            #   primary board must be iPCdev, and trigger_connection must be None
            # - IntermediateDevice with trigger_connection = channel used for triggering:
            #   parent_device must be IntermediateDevice and trigger_connection is not None
            if isinstance(self.primary, iPCdev) and trigger_connection is None:
                trigger_device = self.primary.virtual_device
                # count secondary boards connected on virtual device to find its virtual connection
                index = 0
                for child in trigger_device.child_devices:
                    if isinstance(child, Trigger):
                        index += 1
                trigger_connection = (VIRTUAL_CON % index)
            elif isinstance(self.parent_device, IntermediateDevice) and trigger_connection is not None:
                trigger_device = self.parent_device
                index = None
            else:
                raise LabscriptError("iPCdev '%s': parent '%s', type '%s', primary '%s', type %s, trigger_connection %s incompatiple!\nfor virtual trigger ensure primary type is 'iPCdev' (or derived class) and trigger_connection = None,\nfor hardware trigger give parent = IntermediateDevice (or derived class) and trigger_connection != None." % (name, self.parent_device.name, type(self.parent_device).__name__, self.primary.name, type(self.primary).__name__, str(trigger_connection)))
            print("iPCdev init secondary%s '%s': primary '%s', trigger device '%s', trigger connection '%s'"% ('' if index is None else ' (#%i)'%index, name, self.primary.name, trigger_device.name, str(trigger_connection)))
            PseudoclockDevice.__init__(self, name, trigger_device=trigger_device, trigger_connection=trigger_connection)

        # save worker_args into connection_table
        self.set_property('worker_args', worker_args , location='connection_table_properties')

        # save module path. this allows to load runviewer_parser to load module and device class.
        self.set_property('derived_module', self.__module__, location='connection_table_properties')

        # save shared_clocklines into connection_table
        self.set_property('shared_clocklines', iPCdev.shared_clocklines , location='connection_table_properties')

    def add_device(self, device, allow_create_new=True):
        if isinstance(device, Pseudoclock):
            # pseudoclock connected
            #print('adding pseudoclock', device.name)
            PseudoclockDevice.add_device(self, device)
            device.hardware_info = {DEVICE_INFO_TYPE:HARDWARE_TYPE_PS + HARDWARE_SUBTYPE_NONE + HARDWARE_ADDRTYPE_NONE}
        else:
            # output channel connected: connect to proper IM device
            # 1. get clockline and hardware names. this might be overwritten in derived class
            # raises LabscriptError when connection is invalid
            clockline_name, device.hardware_info = self.split_connection(device)
            #print('adding output channel', device.name, 'clockline', clockline_name)
            # 2. save original parent_device name into hardware_info in case clockline is not of the same device
            #    blacs_tabs uses this to get board devices only for diaplaying and to give to worker
            device.hardware_info.update({DEVICE_INFO_BOARD:self.name})
            #print(self.name, 'split_connection (iPCdev):', device.name, 'clockline', clockline_name, 'hw info', device.hardware_info, 'shared clocklines', iPCdev.shared_clocklines)
            # 3. find or create intermediate device
            device.parent_device = self.get_device(clockline_name, allow_create_new=allow_create_new)
            if device.parent_device is None:
                if allow_create_new:
                    raise LabscriptError("%s error adding '%s', type '%s': clockline '%s' could not be created!" % (self.name, device.name, type(device).__name__, clockline_name))
                else:
                    raise LabscriptError("%s error adding '%s', type '%s': could not find clockline '%s'!" % (self.name, device.name, type(device).__name__, clockline_name))
            #print('add_device IM device', device.parent_device.name)
            # 4. save device hardware information into connection table
            device.set_property(DEVICE_HARDWARE_INFO, device.hardware_info, location='connection_table_properties')
            # 5. add channel to intermediate device
            device.parent_device.add_device(device)

    def get_device(self, clockline_name, allow_create_new):
        """
        returns intermediate (IM) device for given clockline_name.
        either creates new pseudoclock + clockline + IM device or returns existing IM device.
        searchs IM device names in primary device list.
        if allow_create_new = False the device must exist, otherwise returns None.
        if allow_create_new = True creates and returns new device if does not exists.
        notes:
        in default implementation the name is related to iPCdev device, so the IM device belongs to this board.
        however, get_device can be called from a derived class with arbitrary name independent of iPCdev device.
        this way IM device can be 'shared' between boards.
        depending on the implemenation of blacs_tabs the channels can be displayed with the board
        with which they are created or with the board having created the IM device.
        see NI_DAQmx implementation where this can be configured.
        """
        # check address and channel
        if clockline_name is None: return None

        # create name from device name and address
        _clockline_name = clockline_name.replace(CON_SEP,'_').replace(':','').replace('=','')
        name_ps  = NAME_PS  % (_clockline_name)
        name_cl  = NAME_CL  % (_clockline_name)
        name_dev = NAME_DEV % (_clockline_name)

        # search IM device with matching pseudoclock name
        # if shared_clocklines we have to search all boards starting from primary,
        # otherwise we search only clocklines of this board.
        # ATTENTION: do not assign devices = self.child_devices and pop out elements below!
        devices = []
        if iPCdev.shared_clocklines:
            if self.primary is None: devices += self.child_devices
            else:                    devices += self.primary.child_devices
        else:
            devices += self.child_devices
        #print('searching board:', self.name if self.primary is None else self.primary.name)
        while len(devices) > 0:
            ps = devices.pop(0)
            for cl in ps.child_devices:
                for im in cl.child_devices:
                    if im.name == name_dev:
                        # found: return IM device
                        #print('IM device found: %s' % (im.name))
                        return im
                    if iPCdev.shared_clocklines:
                        for child in im.child_devices:
                            if isinstance(child, Trigger):
                                if len(child.child_devices) != 1:
                                    raise LabscriptError("%s trigger %s has %i boards attached but should be 1! this is a bug." % (self.name, child.name, len(child.child_devices)))
                                board = next(iter(child.child_devices))
                                #print('searching board:', board.name)
                                devices += board.child_devices

        #print('IM device not found for', name_dev)

        # return None if not existing and we should not create a new one.
        if not allow_create_new: return None

        # not found: create new pseudoclock, clockline and intermediate device
        ps = _iPCdev(
            name                = name_ps,
            pseudoclock_device  = self,
            connection          = CON_PS,
        )
        cl = ClockLine(
            name                = name_cl,
            pseudoclock         = ps,
            connection          = CON_CL,
        )
        im = iPCdev_device(
            name                = name_dev,
            parent_device       = cl,
            board_name          = self.name,
            clockline_name      = clockline_name,
        )
        # return new IM device
        return im

    ###############################################################
    # following functions might be overwritten in a derived class #
    ###############################################################

    def split_connection(self, channel):
        """
        TODO: overwrite in derived class if you need your own implementation.
              this is usually required to match channel.connection format to the one required by the hardware.
        returns [clockline_name, hardware_info] for given output channel.
        hardware_info is saved into channel. and is given as channel.properties[HARDWARE_INFO], to device_tab and runviewer_parser.
        channel = channel like AnalogOut, DigitalOut, DDS etc. given to add_device.
        raises LabscriptError on error.
        implementation details here (most likely changed in derived class):
        - channel.connection = "clockline/address/channel" given as string/integer/integer
          where address and channel can be prefixed with '0x' to indicate hex integer.
        - clockline can be omitted. then returns clockline_name = address string.
        - uses isinstance to determine type of device.
        - AnalogOutput: needs address only
        - DigitalOutput: needs address/channel
        - DDS: needs address only
        - returned clockline_name = clockline part or address if no clockline given
        - returned hardware_info = dict containing DEVICE_INFO_.. entries
          minimum required:
          hardware_type = HARDWARE_TYPE_ string of device
          address = channel address integer
          channel = channel number for digital output or None for analog output
        """
        clockline_name = None
        hardware_info  = {}
        connection = channel.connection
        if connection[0] == CON_SEP: connection = connection[1:] # remove initial '/'
        split = connection.split(CON_SEP)
        if isinstance(channel, Trigger):
            # Trigger device: connection = VIRTUAL_CON (same format as for digital channels)
            # note: for Trigger device isinstance (channel, DigitalOut) gives True - so we have to check this first.
            hardware_info[DEVICE_INFO_TYPE] = HARDWARE_TYPE_DO + HARDWARE_SUBTYPE_TRIGGER + HARDWARE_ADDRTYPE_MERGED
            try:
                if len(split) == 2: # address/channel
                    clockline_name                     = split[0]
                    hardware_info[DEVICE_INFO_ADDRESS] = int(split[0], 0)
                    hardware_info[DEVICE_INFO_CHANNEL] = int(split[1], 0)
            except ValueError:
                clockline_name = None
            if clockline_name is None:
                raise LabscriptError("trigger device '%s' connection '%s' (board '%s') invalid!\ngive '[clockline/]address/channel' as decimal or hex (with prefix 0x) integer." % (channel.name, channel.connection, self.name))
        elif isinstance(channel, (AnalogOut, StaticAnalogOut)):
            static = isinstance(channel, StaticAnalogOut)
            hardware_info[DEVICE_INFO_TYPE] = HARDWARE_TYPE_AO + (HARDWARE_SUBTYPE_STATIC if static else HARDWARE_SUBTYPE_NONE) + HARDWARE_ADDRTYPE_SINGLE
            try:
                if len(split) == 1: # address only
                    clockline_name                     = NAME_CLOCKLINE % (self.name, NAME_AO, split[0])
                    hardware_info[DEVICE_INFO_ADDRESS] = int(split[0], 0)
                    hardware_info[DEVICE_INFO_CHANNEL] = None
                elif len(split) == 2: # clockline/address
                    clockline_name                     = NAME_CLOCKLINE % (self.name, NAME_AO, split[0])
                    hardware_info[DEVICE_INFO_ADDRESS] = int(split[1], 0)
                    hardware_info[DEVICE_INFO_CHANNEL] = None
            except ValueError:
                clockline_name = None
            if clockline_name is None:
                raise LabscriptError("AO device '%s' connection '%s' (board '%s') invalid!\ngive '[clockline/]address' as decimal or hex (with prefix 0x) integer." % (channel.name, channel.connection, board_name))
        elif isinstance(channel, (DigitalOut, StaticDigitalOut)):
            static = isinstance(channel, StaticDigitalOut)
            hardware_info[DEVICE_INFO_TYPE] = HARDWARE_TYPE_DO + (HARDWARE_SUBTYPE_STATIC if static else HARDWARE_SUBTYPE_NONE) + HARDWARE_ADDRTYPE_MERGED
            try:
                if len(split) == 2: # address/channel
                    clockline_name                     = NAME_CLOCKLINE % (self.name, NAME_DO, split[0])
                    hardware_info[DEVICE_INFO_ADDRESS] = int(split[0], 0)
                    hardware_info[DEVICE_INFO_CHANNEL] = int(split[1], 0)
                elif len(split) == 3: # clockline/address/channel
                    clockline_name                     = NAME_CLOCKLINE % (self.name, NAME_DO, split[0])
                    hardware_info[DEVICE_INFO_ADDRESS] = int(split[1], 0)
                    hardware_info[DEVICE_INFO_CHANNEL] = int(split[2], 0)
            except ValueError:
                clockline_name = None
            if clockline_name is None:
                raise LabscriptError("DO device '%s' connection '%s' (board '%s') invalid!\ngive '[clockline/]address/channel' as decimal or hex (with prefix 0x) integer." % (channel.name, channel.connection, self.name))
        elif isinstance(channel, (DDS, StaticDDS)):
            static = isinstance(channel, StaticDDS)
            hardware_info[DEVICE_INFO_TYPE] = HARDWARE_TYPE_DDS + (HARDWARE_SUBTYPE_STATIC if static else HARDWARE_SUBTYPE_NONE) + HARDWARE_ADDRTYPE_MULTIPLE
            try:
                if channel.gate is not None:
                    hardware_info[DEVICE_INFO_GATE] = {DEVICE_INFO_GATE_DEVICE: channel.gate.name, DEVICE_INFO_GATE_CONNECTION: channel.gate.connection}
            except AttributeError:
                # StaticDDS have gate not defined when digital_gate is not defined.
                # DDSQuantity defines it None.
                #channel.gate = None
                pass
            try:
                if len(split) == 1:  # address
                    clockline_name                     = NAME_CLOCKLINE % (self.name, NAME_DDS, split[0])
                    hardware_info[DEVICE_INFO_ADDRESS] = int(split[0], 0)
                    hardware_info[DEVICE_INFO_CHANNEL] = None
                elif len(split) == 2:  # clockline/address
                    clockline_name                     = NAME_CLOCKLINE % (self.name, NAME_DDS, split[0])
                    hardware_info[DEVICE_INFO_ADDRESS] = int(split[1], 0)
                    hardware_info[DEVICE_INFO_CHANNEL] = None
            except ValueError:
                clockline_name = None
            if clockline_name is None:
                raise LabscriptError("DDS device '%s' connection '%s' (board '%s') invalid!\ngive '[clockline/]address/channel' as decimal or hex (with prefix 0x) integer." % (channel.name, channel.connection, self.name))
        else:
            raise LabscriptError('You have connected %s (class %s) to %s, but does not support children with that class.'%(channel.name, channel.__class__, self.name))

        # note: hardware_info[DEVICE_INFO_PATH] is set later in generate_code.
        #       when split_connection is called channel.parent_device is the iPCdev board.
        #       the proper parent intermediate device is generated only after this returns.

        return clockline_name, hardware_info

    @staticmethod
    def combine_channel_data(hardware_info, channel_data, combined_channel_data):
        """
        TODO: overwrite in derived class if you need your own implementation.
        returns channel_data added to combined_channel_data for the given channel.
        hardware_info         = arbitrary device information to determine how data should be combined
        channel_data          = numpy array of raw data of channel. cannot be None.
        combined_channel_data = numpy array of combined data of all channels with same address.
                                can be None or np.empty for first device to be combined.
                                if not None returns the same data type,
                                otherwise uses default data types.: AO_dtype or DO_dtype.
        extract_channel_data is the inverse function of this function.
        on error returns None
        implementation-details:
        - channel_info = dict with DEVICE_INFO_.. entries
        - address must be integer address of channel
        - if addr_type == HARDWARE_ADDRTYPE_SINGLE: analog output
          channel is None (but not checked)
          combined_channel_data must be empty or None since each analog output data is saved individually.
          returns channel_data
        - if addr_type == HARDWARE_ADDRTYPE_MERGED: digital output
          channel must be an integer and gives the number of bits shifted left
          returns combined_channel_data | (channel_data << channel)
        - addr_type = HARDWARE_ADDRTYPE_MULTIPLE is not implemented and returns None
        """
        address   = hardware_info[DEVICE_INFO_ADDRESS]
        channel   = hardware_info[DEVICE_INFO_CHANNEL]
        addr_type = hardware_info[DEVICE_INFO_TYPE][HARDWARE_ADDRTYPE]
        data = None
        if address is not None:
            if (addr_type == HARDWARE_ADDRTYPE_SINGLE) or (addr_type == HARDWARE_ADDRTYPE_MULTIPLE):
                # analog: only one channel per address is allowed, i.e. give None or np.empty() as combined_channel_data
                # note: for DDS this is called for each channel which is analog output.
                if combined_channel_data is None:
                    data = channel_data.astype(iPCdev.AO_dtype)
                elif (len(combined_channel_data) == 0):
                    data = channel_data.astype(combined_channel_data.dtype)
            elif addr_type == HARDWARE_ADDRTYPE_MERGED:
                # digital out: several channels per address combine data bits
                #              allow to give None or np.empty() for the first device
                if channel is not None and channel >= 0:
                    if combined_channel_data is None:
                        data = ((channel_data.astype(iPCdev.DO_type) & 1) << channel)
                    elif (len(combined_channel_data) == 0):
                        data = ((channel_data.astype(combined_channel_data.dtype) & 1) << channel)
                    else:
                        data = combined_channel_data | ((channel_data.astype(combined_channel_data.dtype) & 1) << channel)
            else:
                raise LabscriptError("combine_channel_data hardware tupe '%s' not implemented!" % (hardware_info[DEVICE_INFO_TYPE]))

        # return combined data or None on error
        return data

    @staticmethod
    def extract_channel_data(hardware_info, combined_channel_data):
        """
        TODO: overwrite in derived class if you need your own implementation.
        returns channel data from combined_channel_data for the given device.
        returns None on error.
        inverse function to combine_channel_aata. for description see there.
        """
        address   = hardware_info[DEVICE_INFO_ADDRESS]
        channel   = hardware_info[DEVICE_INFO_CHANNEL]
        addr_type = hardware_info[DEVICE_INFO_TYPE][HARDWARE_ADDRTYPE]
        channel_data = None
        if (addr_type == HARDWARE_ADDRTYPE_SINGLE) or (addr_type == HARDWARE_ADDRTYPE_MULTIPLE):
            channel_data = combined_channel_data
        elif addr_type == HARDWARE_ADDRTYPE_MERGED:
            if channel is not None and channel >= 0:
                channel_data = ((combined_channel_data >> channel) & 1).astype(bool)
        else:
            raise LabscriptError("extract_channel_data hardware tupe '%s' not implemented!" % (hardware_info[DEVICE_INFO_TYPE]))
        # return extracted channel data or None on error
        return channel_data

    @staticmethod
    def get_trigger_times(dev, device_info):
        """
        returns unsorted list of trigger times from dev.instructions.
        checks that instructions contains only integer or float values.
        removes dev.default_value at time=dev.t0 which is automatically inserted by labscript.
        note: for many instructions this is very inefficient!
        """
        times = []
        for t, instruction in dev.instructions.items():
            if not isinstance(instruction, (int, float, np.float64, np.float32)):
                raise LabscriptError(device_info, "instruction at time %f is of type %s but only integer or real are allowed!" % (t, type(instruction)))
            elif t != dev.t0 or instruction != dev.default_value:
                times.append(t)
        return times

    def prepare_generate_code(self, hdf5_file):
        """
        TODO: overwrite in derived class when needed.
        called from generate_code before any other function is called.
        implementation details:
        - we search for Trigger device (_trigger):
          we given an error if user programs this manually.
        - we search for devices with self.gate, trigger_delay and trigger_duration defined and connected to a digital output channel,
          these are devices which are running in 'table mode' and need an external trigger to advance to the next state in the table.
          we give an error if user programs the digital channel manually using the 'enable' or go_low/go_high commands.
          when a value of the device is programmed we add a gate command here to trigger the device at the given time.
          if you want to use the 'enable' command then just do not define trigger_delay and trigger_duration for this channel.
        - unfortunately, labscript already has inserted time=0 instructions when this function is called, so we have to deal with this.
        """
        for pseudoclock in self.child_devices:
            for clockline in pseudoclock.child_devices:
                for IM in clockline.child_devices:
                    for dev in IM.child_devices:
                        if isinstance(dev, Trigger):
                            if False and hasattr(dev, 'instructions') and len(dev.instructions) != 0:
                                first_time = next(iter(dev.instructions))
                                print(dev.instructions)
                                raise LabscriptError("Trigger device '%s', connection '%s' cannot be programmed directly but has an instruction at time %f!" % (dev.name, dev.connection, first_time))
                        elif hasattr(dev, 'gate') and dev.gate is not None:
                            device_info = "device '%s', connection '%s' with gate '%s' on digital out '%s', connection '%s' in 'table mode'" % (dev.name, dev.connection, dev.gate.name, dev.gate.parent_device.name, dev.gate.connection)
                            if not hasattr(dev, 'trigger_delay') or dev.trigger_delay is None or \
                               not hasattr(dev, 'trigger_duration') or dev.trigger_duration is None:
                                print(device_info, "warning: skipped without trigger_delay or trigger_duration")
                            else:
                                # collect instructions. using dir we get unique instructions - but possible not ordered.
                                # note: normally only DDS devices have dev.gate = None or DigitalOut.
                                #       other devices do not have gate but we allow here to enable 'table mode' for any device.
                                times = []
                                if len(dev.gate.instructions) != 0:
                                    # gate must not have direct instructions! labscript inserts time 0 default value though.
                                    # note: gate is a digital out which should have empty instructions defined.
                                    first_time  = np.min(list(dev.gate.instructions.keys()))
                                    first_value = dev.gate.instructions[first_time]
                                    if (len(dev.gate.instructions) > 1) or (first_value != dev.gate.default_value):
                                        print(dev.gate.instructions)
                                        raise LabscriptError("%s cannot be programmed directly but has %i instructions starting at time %f!\nif you want to use 'enable' and 'disable' remove 'trigger_delay' and 'trigger_duration' from connection_table for this channel!" %
                                                             device_info, (len(dev.gate.instructions), first_time))
                                if hasattr(dev, 'instructions') and len(dev.instructions) != 0:
                                    # note: device is intermediate device which has normally no instructions.
                                    times = iPCdev.get_trigger_times(dev, device_info)
                                elif len(dev.child_devices) > 0:
                                    # no instructions: check if device has sub-devices (like DDS) with instructions
                                    for sub in dev.child_devices:
                                        if hasattr(sub, 'instructions') and len(sub.instructions) != 0:
                                            times += iPCdev.get_trigger_times(sub, device_info)
                                if len(times) > 0:
                                    # this gives sorted list and ignores same times
                                    times = np.unique(times)
                                    # check that time difference between instructions is > trigger_duration + trigger_delay
                                    trigger_delay    = dev.trigger_delay
                                    trigger_duration = dev.trigger_duration
                                    # manually check times
                                    # labscript will check negative times
                                    deltas = times[1:]-times[:-1]
                                    mask = (deltas < (trigger_duration + trigger_delay - TIME_EPSILON))
                                    if np.any(mask):
                                        first = np.argmax(mask)
                                        raise LabscriptError("%s instructions at time %f and %f (delta %f) are closer than trigger duration + delay %f + %f = %f!" % (
                                                device_info, times[first], times[first+1],
                                                deltas[first], trigger_duration, trigger_delay,
                                                trigger_duration + trigger_delay))
                                    print(device_info, "adding %i trigger times" % (len(times)))
                                    print(dev.name, dev.gate.name)
                                    print(times)
                                    for t in times:
                                        #dev.gate.go_high(t - trigger_delay) # this will give an error for negative times.
                                        #dev.gate.go_low (t - trigger_delay + trigger_duration)
                                        dev.enable (t - trigger_delay) # this will give an error for negative times.
                                        dev.disable(t - trigger_delay + trigger_duration)

    def generate_code(self, hdf5_file):
        """
        TODO: overwrite in derived class if needed.
        save all times and data of all channels into hd5 file.
        this is called automatically also for secondary PseudoClockDevices.
        """
        print("%s generate_code ..." % self.name)
        t_start = get_ticks()

        # prepare generate code in derived class
        # here you can search, modify and insert new device.instructions before labscript generates clocks, times and raw_data.
        #self.prepare_generate_code(hdf5_file)

        PseudoclockDevice.generate_code(self, hdf5_file)
        group = hdf5_file[DEVICE_DEVICES].create_group(self.name)

        secondary = []
        exp_time = 0.0
        for pseudoclock in self.child_devices:
            for clockline in pseudoclock.child_devices: # there should be only one
                times = pseudoclock.times[clockline]
                #print('generate_code %s times:' % clockline.name, times)
                if times[-1] > exp_time: exp_time = times[-1]
                for IM in clockline.child_devices:
                    # create IM device sub-group and save time
                    g_IM = group.create_group(IM.name)
                    g_IM.create_dataset(DEVICE_TIME, compression=config.compression, data=times)
                    # device path
                    path = DEVICE_DEVICES + DEVICE_SEP + self.name + DEVICE_SEP + IM.name
                    if IM.hardware_type is None:
                        # IM device created but has no channels? should not happen except for virtual trigger without sec. boards.
                        print('warning: skip device %s without channels.' % (IM.name))
                    else:
                        addr_type = IM.hardware_type[HARDWARE_ADDRTYPE]
                        if addr_type == HARDWARE_ADDRTYPE_SINGLE:
                            # save data for each individual channel
                            for dev in IM.child_devices:
                                #print('AO', dev.name, 'address', dev.hardware_info[DEVICE_INFO_ADDRESS])
                                #if True and hasattr(dev, 'times') and len(dev.times) > 1:  # check times
                                #    t = np.array(dev.times)
                                #    dt = t[1:] - t[:-1]
                                #    if np.min(dt) <= 0:
                                #        raise LabscriptError(dev.name, "time not increasing!")
                                data = type(self).combine_channel_data(dev.hardware_info, dev.raw_output, None)
                                dataset = DEVICE_DATA_AO % (dev.name, dev.hardware_info[DEVICE_INFO_ADDRESS])
                                g_IM.create_dataset(dataset, compression=config.compression, data=data)
                                # save device path into device properties
                                dev.hardware_info[DEVICE_INFO_PATH] = path
                        elif addr_type == HARDWARE_ADDRTYPE_MERGED:
                            # save data for digital channels and triggers for same board and address
                            # we could save each dataset for each device individually,
                            # but typically digital channels are grouped and share the same address = port number
                            # we assume that for each board the address is unique, but different boards might use the same addresses.
                            # therefore, we save dataset for each board and address.
                            # as long as the clocklines are not shared between boards, there will be anyway just one board in the list.
                            boards = list(set([dev.hardware_info[DEVICE_INFO_BOARD] for dev in IM.child_devices]))
                            if (self.primary is None) and (IM.hardware_type[HARDWARE_SUBTYPE] == HARDWARE_SUBTYPE_TRIGGER):
                                # add secondary board names from trigger child devices.
                                # this requires that first channel created is trigger device otherwise subtypse is not trigger.
                                # since trigger is created immediately with primary device this should be fine.
                                # however, other digital channels not being trigger can be added by user.
                                # therefore, we have to check subtype for each channel.
                                #print(self.name, "trigger IM found", IM.name)
                                for trg in IM.child_devices:
                                    hardware_info = trg.hardware_info
                                    if hardware_info[DEVICE_INFO_TYPE][HARDWARE_SUBTYPE] == HARDWARE_SUBTYPE_TRIGGER:
                                        #print(self.name, "sec board found", trg.name)
                                        secondary.append(next(iter(trg.child_devices)).name)
                            for board in boards:
                                # for all channels of the same board and address combine all bits into one data word
                                addresses = list(set([dev.hardware_info[DEVICE_INFO_ADDRESS] for dev in IM.child_devices if dev.hardware_info[DEVICE_INFO_BOARD] == board]))
                                for address in addresses:
                                    data = None
                                    for dev in IM.child_devices:
                                        if (dev.hardware_info[DEVICE_INFO_BOARD] == board) and (dev.hardware_info[DEVICE_INFO_ADDRESS] == address):
                                            data = type(self).combine_channel_data(dev.hardware_info, dev.raw_output, data)
                                            #print('DO', dev.name, 'address', dev.hardware_info[DEVICE_INFO_ADDRESS], 'channel', dev.hardware_info[DEVICE_INFO_ADDRESS],'data', dev.raw_output, 'combined', data)
                                            #if dev.name == 'digital_out_0' or dev.name == 'digital_out_9' or dev.name == 'digital_out_10' or dev.name == 'digital_out_11':
                                            #if True and hasattr(dev, 'times') and len(dev.times) > 1: # check times
                                            #    t = np.array(dev.times)
                                            #    dt = t[1:]-t[:-1]
                                            #    if np.min(dt) <= 0:
                                            #        raise LabscriptError(dev.name, "time not increasing!")
                                            #if True and (dev.name == 'digital_out_4' or dev.name == 'digital_out_8')\
                                            #        and len(times) <= 150:
                                            #    print(dev.name, len(times))
                                            #    print(np.transpose([times,dev.raw_output]))
                                            # save device path into device properties
                                            dev.hardware_info[DEVICE_INFO_PATH] = path
                                    #print(board, 'DO address', address, 'data:', data)
                                    dataset = DEVICE_DATA_DO % (board, address)
                                    g_IM.create_dataset(dataset, compression=config.compression, data=data)
                        elif addr_type == HARDWARE_ADDRTYPE_MULTIPLE:
                            # save data for sub-channels like for DDS:
                            for dev in IM.child_devices:
                                #print('DDS', dev.name, 'address', dev.hardware_info[DEVICE_INFO_ADDRESS])
                                for subdev in dev.child_devices:
                                    # print('DDS', subdev.name, dev.hardware_info, subdev.raw_output)
                                    data = type(self).combine_channel_data(dev.hardware_info, subdev.raw_output, None)
                                    dataset = DEVICE_DATA_DDS % (dev.name, str(dev.hardware_info[DEVICE_INFO_ADDRESS]), subdev.connection)
                                    g_IM.create_dataset(dataset, compression=config.compression, data=data)
                                # save device path into device properties
                                dev.hardware_info[DEVICE_INFO_PATH] = path
                        else:
                            print('warning: skip device %s hardware type %s' % (IM.name, IM.hardware_type))

        # this needs to be save into properties otherwise get an error
        if self.stop_time != exp_time:
            raise LabscriptError('%s stop time %.3e != experiment time %.3e!' % (self.stop_time, exp_time))
        self.set_property('stop_time', self.stop_time, location='device_properties')

        # note: when generate_code is not existing in intermediate device,
        #       then generate_code of secondary boards is called, otherwise not!
        #       for FPGA_board this is still not working, so seems other factors to matter as well?
        #for sec in self.secondary:
        #    print('%s call generate code for %s' % (self.name, sec.name))
        #    sec.generate_code(hdf5_file)

        # save if primary board and list of secondary boards names, or name of primary board.
        # the names identify the worker processes used for interprocess communication.
        if self.primary is None:
            print(self.name, '(primary) secondary boards:', secondary)
            self.set_property('is_primary', True, location='connection_table_properties', overwrite=False)
            self.set_property('boards', secondary, location='connection_table_properties', overwrite=False)
        else:
            print(self.name, '(secondary) primary board:', self.primary.name)
            self.set_property('is_primary', False, location='connection_table_properties', overwrite=False)
            self.set_property('boards', [self.primary.name], location='connection_table_properties', overwrite=False)

        # experiment duration
        if   exp_time >= 1.0:  tmp = '%.3f s'  % (exp_time)
        elif exp_time > 1e-3:  tmp = '%.3f ms' % (exp_time * 1e3)
        elif exp_time > 1e-6:  tmp = '%.3f us' % (exp_time * 1e6)
        else:                  tmp = '%.1f ns' % (exp_time * 1e9)
        print("%s generate_code done (%.3f ms). experiment duration %s" % (self.name, (get_ticks() - t_start) * 1000, tmp))

        if False:
            # Andi test: release all resources
            print(self.name, 'releasing resources ...')
            for pseudoclock in self.child_devices:
                del pseudoclock.times
                del pseudoclock.clock
                for clockline in pseudoclock.child_devices:
                    for IM in clockline.child_devices:
                        for dev in IM.child_devices:
                            if hasattr(dev, 'times'):
                                del dev.times
                                del dev.raw_output
                            if hasattr(dev, 'instructions'):
                                del dev.instructions
                            if not isinstance(dev, Trigger):
                                for subdev in dev.child_devices:
                                    if hasattr(subdev, 'times'):
                                        del subdev.times
                                        del subdev.raw_output
                                    if hasattr(dev, 'instructions'):
                                        del dev.instructions
