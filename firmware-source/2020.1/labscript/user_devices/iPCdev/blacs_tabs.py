# internal pseudoclock device
# created April 2024 by Andi
# last change 13/5/2024 by Andi

import labscript_utils.h5_lock
import h5py
import numpy as np
from labscript import LabscriptError, config
from labscript_utils.qtwidgets.toolpalette import ToolPaletteGroup
from labscript_utils.qtwidgets.digitaloutput import DigitalOutput
from labscript_utils.qtwidgets.analogoutput import AnalogOutput
from labscript_utils.qtwidgets.ddsoutput import DDSOutput
from blacs.device_base_class import DeviceTab
from blacs.tab_base_classes import (
    define_state,
    MODE_MANUAL, MODE_TRANSITION_TO_BUFFERED, MODE_TRANSITION_TO_MANUAL, MODE_BUFFERED
)

import logging
from labscript_utils import import_or_reload
from os.path import split

# for testing
#from user_devices.h5_file_parser import read_group

# path to labscript device and worker
# TODO: in derived class implement init_tab_and_worker with the correct path
#       and load derived class iPCdev
from .labscript_devices import (
    iPCdev, log_level,
    DEVICE_HARDWARE_INFO, DEVICE_INFO_BOARD, DEVICE_INFO_ADDRESS, DEVICE_INFO_CHANNEL, DEVICE_INFO_TYPE,
    HARDWARE_TYPE_AO, HARDWARE_TYPE_DO, HARDWARE_TYPE_DDS, HARDWARE_SUBTYPE_STATIC, HARDWARE_SUBTYPE_TRIGGER,
    HARDWARE_TYPE, HARDWARE_SUBTYPE, DEVICE_INFO_GATE, DEVICE_INFO_GATE_DEVICE, DEVICE_INFO_GATE_CONNECTION,
)
worker_path = 'user_devices.iPCdev.blacs_workers.iPCdev_worker'

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
PROP_UNIT_MHZ           = 'MHz'
PROP_UNIT_DBM           = 'dBm'
PROP_UNIT_DEGREE        = 'deg'     # TODO: use degree symbol (unicode 0x00f0) but I think on Windows does not work?
DDS_CHANNEL_PROP_FREQ   = 'freq'    # must be the same as DDSQuantity.frequency.connection in labscript.py
DDS_CHANNEL_PROP_AMP    = 'amp'     # must be the same as DDSQuantity.amplitude.connection in labscript.py
DDS_CHANNEL_PROP_PHASE  = 'phase'   # must be the same as DDSQuantity.phase.connection in labscript.py

# default channel properties
# TODO: give for each channel
default_AO_props = {PROP_UNIT: PROP_UNIT_V, PROP_MIN: -10.0, PROP_MAX: 10.0, PROP_STEP: 0.1, PROP_DEC: 4}
default_DO_props = {}
default_DDS_props = {DDS_CHANNEL_PROP_FREQ  : {PROP_UNIT: PROP_UNIT_MHZ,    PROP_MIN: 0.0,    PROP_MAX: 1000.0, PROP_STEP: 1.0, PROP_DEC: 6},
                     DDS_CHANNEL_PROP_AMP   : {PROP_UNIT: PROP_UNIT_DBM,    PROP_MIN: -30.0,  PROP_MAX: 20.0,   PROP_STEP: 1.0, PROP_DEC: 3},
                     DDS_CHANNEL_PROP_PHASE : {PROP_UNIT: PROP_UNIT_DEGREE, PROP_MIN: -180.0, PROP_MAX: 180.0,  PROP_STEP: 10,  PROP_DEC: 3}
                    }

# button name in GUI
AO_NAME         = 'analog outputs'
AO_NAME_STATIC  = 'analog outputs (static)'
DO_NAME         = 'digital outputs: '
DO_NAME_STATIC  = 'digital outputs (static): '
DDS_NAME        = 'DDS channels'

# update time of BLACS board status in ms
UPDATE_TIME_MS = 250

# GUI adaptations
GUI_ADJUST          = True          # if True activate appearance options below
GUI_ADJUST_DO       = True          # if True change DO font, color and size for better readability
GUI_AO_CLOSE        = False         # if True close AO's on startup
GUI_DO_CLOSE        = False         # if True close DO's on startup
GUI_DDS_CLOSE       = False         # if True close DDS's on startup
# other GUI options independent of GUI_ADJUST
GUI_SHOW_TRIGGER    = False         # if True show trigger devices which are normally hidden.
# show digital gate in tabs_blacs
GUI_DDS_SHOW_GATE   = True         # TODO: not tested, just copied from QRF

# worker name given for each board name
STR_WORKER          = "%s_worker"

class iPCdev_tab(DeviceTab):

    def set_update_time_ms(self, update_time_ms):
        self._update_time_ms = update_time_ms

    def initialise_GUI(self):
        # reduce number of log entries in logfile (labscript-suite/logs/BLACS.log)
        # TODO: maybe there is a global setting for this but could not find?
        self.logger.setLevel(log_level)
        logger = ['BLACS.AnalysisSubmission.mainloop', 'BLACS.queue_manager.thread','BLACS','BLACS.ConnectionTable','BLACS.QueueManager','BLACS.FrontPanelSettings']
        for l in logger:
            log = logging.getLogger(l)
            log.setLevel(log_level)

        connection_table = self.settings['connection_table']
        self.device = connection_table.find_by_name(self.device_name)

        print('%s initialize_GUI' % (self.device_name))

        # option if clocklines are shared between boards (True) or are for each board individually (False, default)
        # if False (default) displays and saves in self.channels all channels belonging to the clocklines of this board.
        #       self.clocklines = [] since all clocklines can be obtained from channels.
        # if True displays and saves in self.channels only channels belonging to this board.
        #       self.clocklines contains the names of all clocklines of the board.
        #       this is needed since channels of other boards might use board clockline but no channels of the board.
        #       for this all boards and clocklines of the system have to be searched.
        #       implementation:
        #       the parent_device given in the connection_table is saved in device.hardware_info[DEVICE_INFO_BOARD].
        #       the clocklines can be given either as part of the connection (usually first entry before '/') or
        #       are given as arguments to __init__ for the specific derived class. see for example NI_DAQmx_iPCdev.
        # note: this affects self.channels and self.clocklines given to worker!
        self.shared_clocklines = self.device.properties['shared_clocklines']

        if not hasattr(self,'_update_time_ms'):
            # update time in ms status_monitor is called
            # call self.set_update_time_ms() from derived class initialize_GUI. can be also called after super.
            self._update_time_ms = UPDATE_TIME_MS

        if False:
            # at the moment not needed
            # below we call static method split_connection in a possibly derived class of iPCdev
            # dynamically load module and get the class object
            self.derived_module = self.device.properties['derived_module']
            print("%s: derived module '%s', class '%s'" % (self.device_name, self.derived_module, self.device.device_class))
            device_module = import_or_reload(self.derived_module)
            device_class_object = getattr(device_module, self.device.device_class)

        if self.shared_clocklines:
            # in order to find all channels we have to search all boards and not only this one.
            primary = self.device
            while primary.parent is not None:
                primary = primary.parent
            if primary.name == self.device_name:
                print('%s: is the primary device (share clocklines)' % (self.device_name))
            else:
                print('%s: primary device is %s (share clocklines)' % (self.device_name, primary.name))
            boards = [primary]
        else:
            boards = [self.device]

        # get all channels of board
        # we need here several dictionaries:
        # - ao/do/dds_props : list of dictionaries for each address containing key = connection, value = device properties
        # - channels        : key = connection, value = channel device object.
        #                     this is used by get_child_from_connection_table and we give this also to worker.
        # - clocklines      : list of clockline intermediate devices given to worker.
        #                     used only when shared_clocklines = True
        # note: connections = pseudo clock -> clockline -> intermediate device -> channel
        # TODO: analog/digital properties should be defined by channel and not from default_AO/DO_props
        ao_prop         = {}
        do_prop         = {}
        dds_prop        = {}
        self.channels   = {}
        self.clocklines = []
        while len(boards) > 0:
            board = boards.pop(0)
            this_board = (board.name == self.device_name)
            #if self.shared_clocklines: print(self.device_name, 'searching for channels of:', board.name)
            for pseudoclock in board.child_list.values():
                for clockline in pseudoclock.child_list.values():
                    for IM_name, IM in clockline.child_list.items():
                        if self.shared_clocklines and this_board:
                            # save all clocklines belonging to this board.
                            # check IM.properties[DEVICE_HARDWARE_INFO] for board and type.
                            self.clocklines.append(IM)
                        for channel_name, channel in IM.child_list.items():
                            #print(channel_name, channel.device_class, child.properties)
                            hardware_info = channel.properties[DEVICE_HARDWARE_INFO]
                            type = hardware_info[DEVICE_INFO_TYPE][HARDWARE_TYPE]
                            subtype = hardware_info[DEVICE_INFO_TYPE][HARDWARE_SUBTYPE]
                            if subtype == HARDWARE_SUBTYPE_TRIGGER:
                                if self.shared_clocklines:
                                    if len(channel.child_list) != 1:
                                        raise LabscriptError("%s trigger %s has %i boards attached but should be 1! this is a bug." % (self.device_name, channel.name, len(channel.child_list)))
                                    # save next board into list of boards
                                    next_board = next(iter(channel.child_list.values()))
                                    #print('trigger', channel_name, 'next board:', next_board.name)
                                    boards.append(next_board)
                                    # skip devices not belonging to this board
                                    if hardware_info[DEVICE_INFO_BOARD] != self.device_name: continue
                                if GUI_SHOW_TRIGGER: # normally we do not show trigger which is a virtual device.
                                    props = default_DO_props.copy()
                                    props.update(channel.properties)
                                    do_prop[0][channel.parent_port] = props
                            else:
                                if self.shared_clocklines and \
                                   hardware_info[DEVICE_INFO_BOARD] != self.device_name:
                                    # skip devices not belonging to this board
                                    #print(self.device_name, 'skipping', channel_name, 'belonging to', channel.hardware_info[DEVICE_INFO_BOARD])
                                    continue
                                if type == HARDWARE_TYPE_AO:
                                    props = default_AO_props.copy()
                                    props.update(channel.properties)
                                    ao_prop[channel.parent_port] = props
                                elif type == HARDWARE_TYPE_DO:
                                    props = default_DO_props.copy()
                                    props.update(channel.properties)
                                    do_prop[channel.parent_port] = props
                                elif type == HARDWARE_TYPE_DDS:
                                    #print('DDS', channel.name, 'connection', channel.parent_port, 'properties', channel.properties)
                                    props = default_DDS_props
                                    props.update(channel.properties)
                                    dds_prop[channel.parent_port] = props
                                else:
                                    raise LabscriptError('channel %s class %s not implemented!' % (channel.name, channel.device_class))
                            # save hardware info into channel
                            # TODO: not really needed, this way information is twice!?
                            #channel.hardware_info = hardware_info
                            # save channel for each connection = parent_port
                            self.channels[channel.parent_port] = channel

        # create all channels
        if len(ao_prop)  > 0: self.create_analog_outputs(ao_prop)
        if len(do_prop)  > 0: self.create_digital_outputs(do_prop)
        if len(dds_prop) > 0: self.create_dds_outputs(dds_prop)

        # create lists of widgets
        # we separate widgets of buffered/static channels and for DO for different ports
        # widgets = dict with key = connection, value = property
        # names = list of button names to use in GUI
        dds_w, ao_w, do_w = self.auto_create_widgets()
        ao_widgets  = []
        ao_names    = []
        do_widgets  = []
        do_names    = []
        dds_widgets = []
        dds_names   = []
        for connection, prop in ao_w.items():
            child = self.channels[connection]
            name = AO_NAME if child.device_class == 'AnalogOut' else AO_NAME_STATIC
            if name in ao_names:
                index = ao_names.index(name)
                ao_widgets[index][connection] = prop
            else:
                ao_names.append(name)
                ao_widgets.append({connection:prop})
        for connection, prop in do_w.items():
            child = self.channels[connection]
            if child.device_class == 'DigitalOut':
                name = DO_NAME + child.parent_port.split('/')[0]
            else:
                name = DO_NAME_STATIC + child.parent_port.split('/')[0]
            if name in do_names:
                index = do_names.index(name)
                do_widgets[index][connection] = prop
            else:
                do_names.append(name)
                do_widgets.append({connection:prop})
        for connection, prop in dds_w.items():
            child = self.channels[connection]
            name = DDS_NAME # + child.parent_port.split('/')[0]
            if name in dds_names:
                index = dds_names.index(name)
                dds_widgets[index][connection] = prop
            else:
                dds_names.append(name)
                dds_widgets.append({connection:prop})

        # create widgets and place on GUI
        #dds_widgets, ao_widgets, do_widgets = self.auto_create_widgets()
        for w in ao_widgets:
            for name, prop in w.items():
                # if there is a unit conversion class select unit, decimals* and step size*. Volts can be still selected manually.
                # TODO: (*) these settings are not permanent: changed when user selects Volts and then goes back to 'unit'.
                child = self.channels[name]
                if child.unit_conversion_class is not None:

                    # create conversion class object
                    class_path = child.unit_conversion_class.split('.')
                    #module = importlib.import_module('.'.join(class_path[:-1])) # this works as well
                    module = import_or_reload('.'.join(class_path[:-1]))
                    cls = getattr(module, class_path[-1])
                    conversion = cls(child.unit_conversion_params)

                    # select unit
                    try:
                        #unit = child.unit_conversion_params['unit']
                        unit = conversion.derived_units[0]
                        base_unit = conversion.base_unit
                        # replace % symbol since in unit conversion class have to define %_to_base and %_from_base functions which would be invalid names
                        # TODO: how to display still '%' instead?
                        if unit == '%': unit = 'percent'
                        prop.set_selected_unit(unit)
                    except KeyError:
                        unit = None
                        base_unit = None
                    # print("analog out '%s' selected unit '%s'" % (name, prop.selected_unit))

                    # select number of decimals.
                    try:
                        decimals = child.unit_conversion_params['decimals']
                        prop.set_num_decimals(decimals)
                    except KeyError:
                        pass
                    # set step size.
                    try:
                        step = child.unit_conversion_params['step']
                        prop.set_step_size(step)
                    except KeyError:
                        pass

                    if (unit is not None) and (base_unit is not None):
                        to_base = getattr(conversion, unit + '_to_base')
                        # minimum value in given unit
                        try:
                            val_min = child.unit_conversion_params['min']
                            V_min = to_base(val_min)
                        except KeyError:
                            val_min = np.NAN
                            V_min = default_AO_props['min']

                        # maximum value in given unit
                        try:
                            val_max = child.unit_conversion_params['max']
                            V_max = to_base(val_max)
                        except KeyError:
                            val_max = np.NAN
                            V_max = default_AO_props['min']

                        print('%s set limits [%.3f, %.3f] %s = [%.3f, %.3f] %s' % (child.name, val_min, val_max, unit, V_min, V_max, base_unit))
                        prop.set_limits(V_min, V_max)

        # sorting of devices under each button
        # returns one interger used to sort widgets
        def sort(channel):
            # get connection string
            connection = self.channels[channel].parent_port
            # get all digits including hex numbers
            digits = [c for c in connection if (c>='0' and c<='9') or (c>='a' and c<='f') or (c>='A' and c<='F')]
            # interpret digits as hex number
            num = int(''.join(digits), 16)
            return num

        # place the widgets. we sort by name which puts buffered before static and with increasing port for DO
        # TODO: on the device tab which is displayed initially the channels are not arranged properly.
        for i,name in sorted(enumerate(ao_names), key=lambda x:x[1]):
            self.auto_place_widgets((name, ao_widgets[i], sort))
        for i,name in sorted(enumerate(do_names), key=lambda x:x[1]):
            self.auto_place_widgets((name, do_widgets[i], sort))
        for i,name in sorted(enumerate(dds_names), key=lambda x:x[1]):
            self.auto_place_widgets((name, dds_widgets[i], sort))

        if GUI_ADJUST:
            # customize GUI appearance
            # + closes enabled widget group buttons
            # + change color and font size of digital outputs since is hardly readable
            layout = self.get_tab_layout()
            index = layout.count()
            for i in range(index):
                widget = layout.itemAt(i).widget()
                if widget is not None:
                    # find ToolPaletteGroup which is the container class
                    children = widget.findChildren(ToolPaletteGroup)
                    for child in children:
                        if GUI_AO_CLOSE and (AO_NAME in child._widget_groups):
                            child.hide_palette(AO_NAME)
                        if GUI_DO_CLOSE and (DO_NAME in child._widget_groups):
                            child.hide_palette(DO_NAME)
                        if GUI_DDS_CLOSE and (DDS_NAME in child._widget_groups):
                            child.hide_palette(DDS_NAME)
                    if GUI_ADJUST_DO:
                        # change digital output text color since text is hardly readable
                        DO = widget.findChildren(DigitalOutput)
                        for do in DO:
                            do.setToolTip(do.text())
                            #do.setStyleSheet('QPushButton {color: white; font-size: 14pt;}')
                            do.setStyleSheet('QPushButton {color: white;}')
                            #do.setFixedWidth(100)
                            #do.setMinimumWidth(100)
                    if GUI_DDS_SHOW_GATE:
                        dds_list = widget.findChildren(DDSOutput)
                        for dds in dds_list:
                            connection = dds._hardware_name # connection = 'channel %i'
                            device = self.channels[connection]
                            hardware_info = device.properties[DEVICE_HARDWARE_INFO]
                            try:
                                gate = hardware_info[DEVICE_INFO_GATE]
                            except KeyError:
                                continue
                            label = dds._label.text().split('\n')  # [connection, user given name]
                            label.append("%s: %s" % (gate[DEVICE_INFO_GATE_DEVICE], gate[DEVICE_INFO_GATE_CONNECTION]))
                            label = '\n'.join(label)
                            dds._label.setText(label)
                #AO = widget.findChildren(AnalogOutput)
                    #for ao in AO:
                    #    #ao.setFixedWidth(100)
                    #    ao.setMinimumWidth(100)
                    #widget.update()
                    #def SizeHint():
                    #    return QSize(100,20)
                    #widget.SizeHint = SizeHint
                    #print(widget.geometry())

        #print(self.device_name, "update")
        #self._ui.splitter.setSizes([1, 1, 1])
        #self._ui.update()

        # perform further initalization and create worker in derived class
        # note: properties contains 'worker_args' and 'shared_clocklines'. del does not work?
        self.worker_args = {'is_primary'        : self.device.properties['is_primary'],
                            'boards'            : self.device.properties['boards'],
                            'channels'          : self.channels,
                            'properties'        : self.device.properties,
                            'device_class'      : self.device.device_class}
        if self.shared_clocklines:
            self.worker_args.update({'clocklines': self.clocklines})
        self.primary_worker = STR_WORKER % (self.device_name)
        self.init_tab_and_worker()

        # TODO: the tab which is displayed last before closing is displayed first after rstart
        #       but the layout is messed up and changes to normal when restarting worker or resize GUI.
        #       so far nothing has worked.
        #layout = self.get_tab_layout()
        #layout.update()
        #self._ui.update()
        #self._ui.showMaximized()
        #self._ui.resize(1000, 800)

    def init_tab_and_worker(self):
        # create worker
        # TODO: define in derived class with proper worker_path and updated worker_args when needed.
        self.create_worker(
            name        = self.primary_worker,
            WorkerClass = worker_path,
            workerargs  = self.worker_args,
        )

        # Set the capabilities of this device
        self.supports_remote_value_check(False)
        self.supports_smart_programming(True)

    def get_child_from_connection_table(self, parent_device_name, port):
        # this is called from create_analog/digital/dds_outputs to get the name of the channel.
        # if not defined, the default implementation assumes that iPCdev is the parent device of all channels.
        # but in our case the parents of the channels are the iPCdev_device intermediate devices.
        # port = user given 'connection' in connection_table
        # returns the output channel device (connection object)
        #         blacs is displaying device.name = user-given 'name' in connection_table.
        if parent_device_name == self.device_name:
            # iPCdev device name given: return channel with the given connection
            return self.channels[port]
        else:
            # DDS device name given: find DDS device and return sub-channel
            for channel in self.channels.values():
                if channel.name == parent_device_name:
                    for child in channel.child_list.values():
                        if child.parent_port == port:
                            return child
                    break
            raise LabscriptError("iPCdev.get_child_from_connection_table error: %s could not find connection '%s' in childs of device '%s' (supposed DDS)" % (self.device_name, port, parent_device_name))

    def restart(self, value):
        # restart button pressed
        # - we need to notify worker such that it can release resources before restarting!
        # - we cannot use self.connect_restart_receiver(self.restart) since self.event_queue.put
        #   exectues function only after this function returns but then the tab is already closed.
        # - so we have to delay the closing until the worker 'restart' function returns.
        # - this function replaces Tab.restart in tab_base_classes which we call later
        # 1. insert _restart function into event queue. this is executed only after restarts returns.
        print(self.device_name, 'restart ...')
        self.event_queue.put(allowed_states=MODE_MANUAL | MODE_BUFFERED | MODE_TRANSITION_TO_BUFFERED | MODE_TRANSITION_TO_MANUAL,
                                    queue_state_indefinitely=True,
                                    delete_stale_states=False,
                                    data=[self._restart, [[],{}]])

    def _restart(self, parent):
        # 2. yield restart function in primary worker and wait for result
        result = yield(self.queue_work(self.primary_worker, 'restart'))
        # 3. if worker returns True we call Tab.restart in tab_base_classes which restarts tab.
        print(self.device_name, 'restart result', result)
        if result:
            super(iPCdev_tab, self).restart()

    @define_state(MODE_BUFFERED, True)
    def start_run(self, notify_queue):
        #print(self.device_name, 'start run')
        # note: this is called only for primary pseudoclock device! and not for other boards!
        #       therefore, the worker must call FPGA_worker::start_run() directly from transition_to_buffered.
        # update status during run every self._update_time_ms
        self.statemachine_timeout_add(self._update_time_ms, self.status_monitor, notify_queue)
        # check of end state in MODE_MANUAL after run finished
        # this way we can collect information of all boards since transition_to_manual is called for all of them.
        # here one could indicate in the GUI about device status.
        # from worker we have no access to GUI and most likely cannot call back to DeviceTab?
        self.event_queue.put(MODE_MANUAL, True, False, [self.status_end, ((),{})], priority=0)

    #@define_state(MODE_BUFFERED, True)
    @define_state(MODE_MANUAL | MODE_BUFFERED | MODE_TRANSITION_TO_BUFFERED | MODE_TRANSITION_TO_MANUAL, True)
    def status_monitor(self, notify_queue):
        # TODO: I have not found a way to call this for all boards.
        #       using name of workers of other boards gives an error.
        #       however status_end gives a way to check status of all boards after run finished.
        result = yield (self.queue_work(self.primary_worker, 'status_monitor', False))
        #print(self.device_name, 'status monitor result', result)
        if result: # end or error
            # indicate that experiment cycle is finished.
            # this causes transition_to_manual called on all workers.
            notify_queue.put('done')
            # do not call status_monitor anymore
            self.statemachine_timeout_remove(self.status_monitor)

    @define_state(MODE_MANUAL, True)
    def status_end(self,test=None):
        # check final state after experimental cycle is finished.
        # this calls status_monitor in worker with status_end=True
        # this is called as soon as transition_to_manual has been exectued by all boards.
        # return dict with key = board name (self.device_name), value = error code. 0 = ok.
        # optionally return empty dict when transition_to_manual is called with abort=True.
        # TODO: save result into h5 file either here or in primary worker.
        board_status = yield(self.queue_work(self.primary_worker, 'status_monitor', True))
        if False:
            print(self.device_name, 'status end result', board_status)

    def get_save_data(self):
        "return all GUI settings to be retrieved after BLACS restarts"
        data = {}
        #print("%s: get_save_data:" %  self.device_name, data)
        return data

    def restore_save_data(self, data):
        """
        get GUI settings. settings in worker_args have precedence.
        unfortunately is called AFTER initialize_GUI, so we have to init stuff several times.
        data might be empty.
        """
        #print("%s: restore_save_data:" % self.device_name, data)
        pass
