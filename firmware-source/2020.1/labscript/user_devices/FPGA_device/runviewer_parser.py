#####################################################################
# runviewer_parser for FPGA-SoC device by Andreas Trenkwalder
# works as PseudoClockDevice
# created 6/4/2021
# last change 01/07/2024 by Andi
#####################################################################

import sys
import numpy as np
import h5py
from labscript import LabscriptError
from labscript_utils import import_or_reload
from labscript_devices import runviewer_parser
from labscript_utils.unitconversions import get_unit_conversion_class

from .labscript_device import (
    get_channels, word_to_time,
    BIT_NOP_SH, ADDR_MASK_SH, ADDR_SHIFT, DATA_MASK,
    START_TIME,
    get_rack, get_address, get_channel, get_channel_name,
)
from .shared import (
    TYPE_board, TYPE_AO, TYPE_DO, TYPE_SP, TYPE_DDS,
    MAX_SHOW, ALWAYS_SHOW, show_data,
    DDS_CHANNEL_FREQ, DDS_CHANNEL_AMP, DDS_CHANNEL_PHASE,
)

# runviewer options
runviewer_show_units        = True          # if True show user units in runviewer, otherwise show output in Volts
runviewer_add_start_time    = False         # if True adds time START_TIME to data if not given by user. value is last value of last instruction.
runviewer_add_stop_time     = True          # if True adds stop time to data. value is last value of last instruction.
runviewer_show_all          = True          # if True show all channels even without data

@runviewer_parser
class FPGA_parser(object):
    
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
                    #self.ao_list = get_channels(device)
                    #print('%i channels:'%len(self.ao_list), list(self.ao_list.keys()))
                    self.channels = {}
                    for name, channel in device.child_list.items():
                        device_class = channel.properties['device_class'].split('.')
                        module_name = '.'.join(device_class[:-1])
                        class_name = device_class[-1]
                        if class_name != channel.device_class:
                            raise LabscriptError("%s (%s) class name '%s' != '%s'!" % (channel.name, name, class_name, channel.device_class))
                        import_or_reload(module_name)
                        channel.cls = getattr(sys.modules[module_name], channel.device_class)
                        self.channels[name] = channel
                elif device.device_class == 'DigitalChannels':
                    self.type = TYPE_DO
                    print("runviewer loading '%s' (digital outputs)" % (device.name))
                    self.do_list = get_channels(device)
                    print('%i channels:'%len(self.do_list), list(self.do_list.keys()))
                elif device.device_class == 'DDSChannels':
                    self.type = TYPE_DDS
                    print("runviewer loading '%s' (DDS)" % (device.name))
                    #self.dds_list = get_channels(device)
                    #print('%i channels:' % len(self.dds_list), list(self.dds_list.keys()))
                    self.channels = {}
                    for name, dds in device.child_list.items():
                        device_class = dds.properties['device_class'].split('.')
                        module_name = '.'.join(device_class[:-1])
                        class_name = device_class[-1]
                        if class_name != dds.device_class:
                            raise LabscriptError("%s (%s) class name '%s' != '%s'!" % (dds.name, name, class_name, dds.device_class))
                        import_or_reload(module_name)
                        dds.cls = getattr(sys.modules[module_name], dds.device_class)
                        self.channels[name] = dds
                else: # unknown device
                    print("runviewer loading '%s' (ignore)" % (device.name))
        except Exception as e:
            # we have to catch exceptions here since they are not displayed which makes debugging very difficult
            print("exception '%s'" % (str(e)))
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
                    #for name, ll in self.ao_list.items():
                    for name, ch in self.channels.items():
                        #[ID,props,child,ch_name,unit_conversion_class] = ll
                        # we have access to unit conversion class and parameters
                        #ch = self.device.child_list[name]
                        if ch.unit_conversion_class is not None:
                            # import class. importing/reloading is not working well in python and you might experience problems here!
                            unit_conversion_class = get_unit_conversion_class(ch.unit_conversion_class)
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
                        #rack = get_rack(ID)
                        #addr = get_address(ID)
                        rack    = ch.properties['rack']
                        addr    = ch.properties['address']
                        channel = ch.properties['channel']
                        ch_name = get_channel_name(self.type, rack, addr, channel)
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
                            time, value = ch.cls.from_words(ch.properties, time, d[:, rack + 1])
                            if to_unit is not None:
                                value = to_unit(value)
                            if runviewer_add_stop_time and (time[-1] != (data[-1,0]/self.bus_rate)):
                                # extend trace to last time
                                time = np.concatenate([time,[data[-1,0]/self.bus_rate]])
                                value = np.concatenate([value, [value[-1]]])
                            #print("ao '%s' 0x%x:" % (name,ID))
                            #print('time = ',time)
                            # we add trace for all channels, even if not used
                            add_trace(name, (time, value), self, ch_name)
                            #traces[name] = (time, value) # TODO: should be not needed? call only for clocklines and triggers
                            print("analog out '%s' (%s) %i samples %.3f - %.3fV" % (name, ch_name, len(value), np.min(value), np.max(value)))
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
                    # get rack, address and mask from first channel. this is the same for all channels
                    [ID, props, child, ch_name, unit_conversion_class] = list(self.do_list.values())[0]
                    rack = get_rack(ID)
                    addr = get_address(ID)
                    mask = (((data[:,rack+1] & (BIT_NOP_SH|ADDR_MASK_SH))>>ADDR_SHIFT) == addr)
                    #for i,di in enumerate(data):
                    #    print("%8u %08x %s" % (di[0], di[1], mask[i]))
                    d = data[mask]
                    print("'%s' add trace (digital out) %i/%i samples" % (self.name, len(d), len(data)))
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
                            if runviewer_add_stop_time and (time[-1] != (data[-1,0]/self.bus_rate)):
                                # extend trace to last time
                                time = np.concatenate([time,[data[-1,0]/self.bus_rate]])
                                value = np.concatenate([value, [value[-1]]])
                            #print("do '%s' 0x%x:" % (name,ID))
                            #print('time = ',time)
                            #print('data = ',value)
                            # we add trace for all channels, even if channel might not be used
                            # add_trace(name, (time, value), parent, conn)
                            add_trace(name, (time, value), self, ch_name)
                            #traces[name] = (time, value) # TODO: should be not needed? call only for clocklines and triggers
                            print("digital out '%s' (%s) %i samples" % (name, ch_name, len(value)))
                            if len(value) <= 2:
                                print(np.transpose([time,value]))
                    else: # address is not used
                        if runviewer_show_all:
                            time = np.array([data[0, 0], data[-1, 0]]) / self.bus_rate
                            value = np.array([0, 0])
                            for name, ll in self.do_list.items():
                                [ID, props, child, ch_name, unit_conversion_class] = ll
                                #print("'%s' (%s, addr 0x%x) not used" % (name, ch_name, addr))
                                add_trace(name, (time, value), self, ch_name)
                elif self.type == TYPE_DDS:  # DDS
                    print("'%s' add trace (DDS) %i samples" % (self.name, len(data)))
                    for dds_name, dds in self.channels.items():
                        rack    = dds.properties['rack']
                        address = dds.properties['address']
                        channel = dds.properties['channel']
                        ch_name = get_channel_name(TYPE_DDS, rack, address, channel)
                        for name, sub in dds.child_list.items():
                            addr        = sub.properties['address']
                            sub_channel = sub.properties['sub-channel']
                            if dds.cls.addr_offset is not None:
                                # individual address of each of sub-channel
                                if address + dds.cls.addr_offset[sub_channel] != addr:
                                    raise LabscriptError("DDS '%s' (%s) address 0x%x != 0x%x + 0x%x" % (name, ch_name, addr, address, dds.cls.addr_offset[sub_channel]))
                                addr_mask = ADDR_MASK_SH
                            elif hasattr(dds.cls, 'ADDR_RNG_MASK'):
                                # address range of sub-channel
                                addr_mask = dds.cls.ADDR_RNG_MASK << ADDR_SHIFT
                            else:
                                # addresses of sub-channel = dds address
                                addr_mask = ADDR_MASK_SH
                            mask = (((data[:, rack + 1] & (BIT_NOP_SH | addr_mask)) >> ADDR_SHIFT) == addr)
                            d = data[mask]
                            if len(d) > 0: # data available
                                #print('time, value, mask:\n', np.transpose([data[:,0], data[:, rack + 1], mask.astype(np.uint8)]))
                                if runviewer_add_start_time and (d[0,0] > START_TIME):
                                    # add last state of channel as initial state
                                    d = np.concatenate([[np.concatenate([[START_TIME],d[-1,1:]])],d])
                                #show_data(d, info="DDS '%s' (%s, addr 0x%02x) raw data" % (name, ch_name, addr), bus_rate=self.bus_rate)
                                # convert raw data into time and user value
                                # time and value might be fewer than raw data!
                                time, value = dds.cls.from_words(sub.properties, d[:,0]/self.bus_rate, d[:, rack + 1])
                                if len(value) == 0:
                                    # from_words returned no data although data with device address available.
                                    # maybe wrong address or addr_mask or a bug in from_words?
                                    if ALWAYS_SHOW or len(value) <= MAX_SHOW:
                                        show_data(data, info="DDS '%s' (%s, addr 0x%02x) raw data"%(name, ch_name, addr), bus_rate=self.bus_rate)
                                    raise LabscriptError("DDS '%s' (%s, addr 0x%02x) %i/%i samples! from_words returned 0 samples" % (name, ch_name, addr, len(value), len(d)))
                                else:
                                    if runviewer_add_stop_time and (time[-1] != (data[-1,0]/self.bus_rate)):
                                        # extend trace to last time
                                        time = np.concatenate([time,[data[-1,0]/self.bus_rate]])
                                        value = np.concatenate([value, [value[-1]]])
                                    # we add trace for all channels, even if not used
                                    add_trace(name, (time, value), self, ch_name)
                                    print("DDS '%s' (%s, addr 0x%02x) %i/%i samples" % (name, ch_name, addr, len(value), len(data)))
                                    if ALWAYS_SHOW or len(value) <= MAX_SHOW:
                                        print(np.transpose([time,value]))
                            else: # address is not used
                                print("DDS '%s' (%s, addr 0x%02x) no data" % (name, ch_name, addr))
                                if runviewer_show_all:
                                    time = np.array([data[0, 0], data[-1, 0]]) / self.bus_rate
                                    # give device default values.
                                    # note: this might be out of sub.properties['limits']
                                    #       but this way we indicate it was not programmed.
                                    if   sub_channel == DDS_CHANNEL_FREQ : default = dds.cls.default_value_freq
                                    elif sub_channel == DDS_CHANNEL_AMP  : default = dds.cls.default_value_amp
                                    elif sub_channel == DDS_CHANNEL_PHASE: default = dds.cls.default_value_phase
                                    else: raise LabscriptError('%s sub-channel %s unknown!?' % (sub.name, sub_channel))
                                    value = np.array([default, default])
                                    add_trace(name, (time, value), self, ch_name)
                else:
                    print("'%s' add trace (unknown?) %i samples" % (self.name, len(data)))

        except Exception as e:
            # we have to catch exceptions here since they are not displayed which makes debugging very difficult
            print("exception '%s'" % (str(e)))
            raise e

        return traces


