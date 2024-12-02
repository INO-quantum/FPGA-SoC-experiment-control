# internal pseudoclock device
# created April 2024 by Andi
# last change 13/6/2024 by Andi

import labscript_utils.h5_lock
import h5py
import numpy as np

from labscript import LabscriptError
from labscript_utils import import_or_reload

from user_devices.iPCdev.labscript_devices import (
    iPCdev,
    DEVICE_DEVICES, DEVICE_SEP,
    DEVICE_HARDWARE_INFO, DEVICE_INFO_PATH, DEVICE_INFO_ADDRESS, DEVICE_INFO_BOARD, DEVICE_INFO_CHANNEL, DEVICE_INFO_TYPE,
    DEVICE_TIME, DEVICE_DATA_AO, DEVICE_DATA_DO, DEVICE_DATA_DDS,
    HARDWARE_TYPE, HARDWARE_SUBTYPE, HARDWARE_ADDRTYPE,
    HARDWARE_TYPE_AO, HARDWARE_TYPE_DO, HARDWARE_TYPE_DDS,
    HARDWARE_SUBTYPE_STATIC, HARDWARE_SUBTYPE_TRIGGER
)

class iPCdev_parser(object):
    # show all devices (True) or only devices with data (False)
    SHOW_ALL = True

    def __init__(self, path, device):
        # this is called for all boards
        self.path   = path
        self.name   = device.name
        self.device = device
        if iPCdev_parser.SHOW_ALL: print("runviewer loading class '%s' device '%s' (display all channels)"       % (device.device_class, device.name))
        else:                      print("runviewer loading class '%s' device '%s' (display only used channels)" % (device.device_class, device.name))

        # below we call static method extract_channel_data in a possibly derived class of iPCdev
        # dynamically load module and get the class object
        self.derived_module = device.properties['derived_module']
        print('derived module:', self.derived_module, 'class:', device.device_class)
        device_module = import_or_reload(self.derived_module)
        self.device_class_object = getattr(device_module, device.device_class)

        # get all channels connected to clocklines of board
        # note: this does not necessarily represent the physical channels of the board
        #       if clocklines are shared channels of different boards are in this list.
        #       if clocklines are not shared then only the board physical channels are here.
        self.channels = []
        for ps_name, ps in device.child_list.items():
            for cl_name, cl in ps.child_list.items():
                for IM_name, IM in cl.child_list.items():
                    for device_name, device in IM.child_list.items():
                        #print('device:', device_name, 'class:', device.device_class)
                        self.channels.append(device)
        print('%i channels' % len(self.channels))

    def get_traces(self, add_trace, clock = None):
        # this is called for all boards
        print('get_traces', self.name)
        clocklines_and_triggers = {}
        clocklines = []

        with h5py.File(self.path, 'r') as f:
            # load data tables for analog and digital outputs
            for device in self.channels:
                hardware_info = device.properties[DEVICE_HARDWARE_INFO]
                hardware_type = hardware_info[DEVICE_INFO_TYPE]
                board         = hardware_info[DEVICE_INFO_BOARD] # this is the physical board where the channel belongs.
                address       = hardware_info[DEVICE_INFO_ADDRESS]
                group = f[hardware_info[DEVICE_INFO_PATH]]
                times = group[DEVICE_TIME][()]
                parent = device.parent
                if parent.name not in clocklines:
                    # manually insert clockline IM device when not already done. name must be true device name.
                    # times = rising edge of clock
                    print('clock %s connection %s adding %i times' % (parent.name, parent.parent_port, len(times)))
                    if False: # show last hold time
                        values = np.tile([1,0], len(times)+1)[:-1]
                        dt = (times[1:]-times[:-1])/2
                        clock = np.empty(shape=(len(times)*2,), dtype=dt.dtype)
                        clock[0]      = 0
                        clock[1:-1:2] = dt
                        clock[2::2]   = dt
                        clock[-1]     = 1e-6 # virtual hold time after last rising edge
                    else:
                        values = np.tile([1,0], len(times))
                        dt = (times[1:]-times[:-1])/2
                        clock = np.empty(shape=(len(times)*2-1,), dtype=dt.dtype)
                        clock[0]    = 0
                        clock[1::2] = dt
                        clock[2::2] = dt
                    clock = np.cumsum(clock)
                    add_trace(parent.name, (clock, values), board, parent.parent_port)
                    clocklines.append(parent.name)

                print("device %s type %s" % (device.name, hardware_type))
                if (hardware_type[HARDWARE_TYPE] == HARDWARE_TYPE_AO):
                    static = hardware_type[HARDWARE_SUBTYPE] == HARDWARE_SUBTYPE_STATIC
                    devices = [(device.name, DEVICE_DATA_AO % (device.name, address), static, False)]
                elif (hardware_type[HARDWARE_TYPE] == HARDWARE_TYPE_DO):
                    if hardware_type[HARDWARE_SUBTYPE] == HARDWARE_SUBTYPE_TRIGGER:
                        devices = [(device.name, DEVICE_DATA_DO % (board, address), False, True)]
                    else:
                        static = hardware_type[HARDWARE_SUBTYPE] == HARDWARE_SUBTYPE_STATIC
                        devices = [(device.name, DEVICE_DATA_DO % (board, address), static, False)]
                elif hardware_type[HARDWARE_TYPE] == HARDWARE_TYPE_DDS:
                    static = hardware_type[HARDWARE_SUBTYPE] == HARDWARE_SUBTYPE_STATIC
                    devices = [(channel.name, DEVICE_DATA_DDS % (device.name, address, channel.parent_port), static, False) for channel in device.child_list.values()]
                else:
                    print("warning: device %s unknown type %s (skip)" % (device.name, hardware_type))
                    continue
                for (name, dataset, static, trigger) in devices:
                    data = group[dataset][()]
                    if data is None:
                        raise LabscriptError("device %s: dataset %s not existing!" % (name, dataset))
                    elif static and (len(times) != 2) and (len(data) != 1):
                        raise LabscriptError("static device %s: %i/%i times/data but 2/1 expected!" % (name, len(times), len(data)))
                    elif not static and len(times) != len(data):
                        raise LabscriptError("device %s: %i times but %i data!" % (name, len(times), len(data)))
                    elif iPCdev_parser.SHOW_ALL or len(times) > 2:
                        channel_data = self.device_class_object.extract_channel_data(hardware_info, data)
                        # add_trace is not so clear:
                        # runviewer/__main__: add_trace(self, name, trace, parent_device_name, connection)
                        # name  = must be a true device name otherwise get NoneType object has not attribute 'device_class'
                        # trace = (time, value)
                        # parent_device_name = can be also None?
                        # connection         = can be also None?
                        if static: add_trace(name, (times, [channel_data[0]]*2), device.parent.name, device.parent_port)
                        else:      add_trace(name, (times, channel_data), device.parent.name, device.parent_port)
                        if trigger:
                            # add trigger to clocklines_and_triggers. this loads secondary boards.
                            clocklines_and_triggers[name] = (times, channel_data)

        # we return only triggers. clocklines are all read here.
        return clocklines_and_triggers
