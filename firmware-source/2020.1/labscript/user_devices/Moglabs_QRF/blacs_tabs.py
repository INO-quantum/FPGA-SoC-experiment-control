# Moglabs QRF 
# created 29/5/2024 by Andi
# modified from:
# https://github.com/specialforcea/labscript_suite/blob/a4ad5255207cced671990fff94647b1625aa0049/labscript_devices/MOGLabs_XRF021.py
# requires mogdevice.py, see: https://pypi.org/project/mogdevice/
# last change 30/5/2024 by Andi

from blacs.tab_base_classes import MODE_MANUAL
from PyQt5.QtWidgets import QWidget, QGridLayout, QCheckBox, QLabel
from labscript_utils.qtwidgets.toolpalette import ToolPaletteGroup

from user_devices.iPCdev.labscript_devices import (
    DEVICE_INFO_GATE, DEVICE_INFO_GATE_DEVICE, DEVICE_INFO_GATE_CONNECTION
)

from user_devices.iPCdev.blacs_tabs import (
    iPCdev_tab, DDS_NAME, DEVICE_HARDWARE_INFO, DEVICE_INFO_CHANNEL,
)

from .labscript_devices import (
    MAX_NUM_CHANNELS, DDS_CHANNEL_PROP_MODE, DDS_NAME_DYNAMIC, DDS_NAME_STATIC,
)

worker_path = 'user_devices.Moglabs_QRF.blacs_workers.QRF_worker'

# status monitor update time
UPDATE_TIME_MS = 250

# power check boxes for each DDS
class power_check_boxes(QWidget):
    labels = ['signal', 'amplifier', 'both']  # labels for check boxes

    def __init__(self, parent, name, channel, signal=False, amplifier=False, align_horizontal=False):
        super(power_check_boxes, self).__init__(parent._ui)

        # init class
        self.parent    = parent                 # parent (DeviceTab instance)
        self.name      = name                   # channel name in connection table (string)
        self.channel   = channel                # channel number (integer)
        self.signal    = signal                 # initial state of signal check box (bool)
        self.amplifier = amplifier              # initial state of amplifier check box (bool)
        self.both      = signal and amplifier   # initial state of both check box (bool)

        # create layout
        grid = QGridLayout(self)
        self.setLayout(grid)

        # create check boxes
        states  = [signal, amplifier, signal and amplifier]
        connect = [self.onSignal, self.onAmp, self.onBoth]
        self.cb = []
        for i,name in enumerate(self.labels):
            cb = QCheckBox(name)
            cb.setChecked(states[i])
            cb.clicked.connect(connect[i])
            self.cb.append(cb)
            if align_horizontal: grid.addWidget(cb, 0, i)
            else:                grid.addWidget(cb, i, 0)

    def onSignal(self, state):
        # 'signal' clicked: manually insert event into parent event queue. see tab_base_classes.py @define_state(MODE_MANUAL, True)
        self.parent.event_queue.put(allowed_states=MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=False,
                                    data=[self._onSignal, [[self.channel, state], {}]])

    def onAmp(self, state, both=False):
        # 'amplifier' clicked: manually insert event into parent event queue. see tab_base_classes.py @define_state(MODE_MANUAL, True)
        self.parent.event_queue.put(allowed_states=MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=False,
                                    data=[self._onAmp, [[self.channel, state], {}]])

    def onBoth(self, state):
        # 'both' clicked: manually insert event into parent event queue. see tab_base_classes.py @define_state(MODE_MANUAL, True)
        self.parent.event_queue.put(allowed_states=MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=False,
                                    data=[self._onBoth, [[self.channel, state], {}]])

    def _onSignal(self, parent, channel, state):
        # executed by QT main thread (tab_base_classes.py Tab::mainloop). must be generator (with yield).
        info = "'%s' %s signal" % (self.name, 'enable' if state else 'disable')
        result = yield (self.parent.queue_work(self.parent.primary_worker, 'onSignal', channel, state))
        if (result is not None) and result:
            self.signal = state
            print(info)
            self.cb[0].setChecked(self.signal)
            self.set_both()
        else:
            print(info + ' failed!')
            self.cb[0].setChecked(self.signal)

    def _onAmp(self, parent, channel, state):
        # executed by QT main thread (tab_base_classes.py Tab::mainloop). must be generator (with yield).
        info = "'%s' %s amplifier" % (self.name, 'enable' if state else 'disable')
        result = yield (self.parent.queue_work(self.parent.primary_worker, 'onAmp', channel, state))
        if (result is not None) and result:
            self.amplifier = state
            print(info)
            self.cb[1].setChecked(self.amplifier)
            self.set_both()
        else:
            print(info + ' failed!')
            self.cb[1].setChecked(self.amplifier)

    def _onBoth(self, parent, channel, state):
        # executed by QT main thread (tab_base_classes.py Tab::mainloop). must be generator (with yield).
        info = "'%s' %s signal & amplifier" % (self.name, 'enable' if state else 'disable')
        result = yield (self.parent.queue_work(self.parent.primary_worker, 'onBoth', channel, state))
        if (result is not None) and result:
            self.signal    = state
            self.amplifier = state
            print(info)
            self.cb[0].setChecked(self.signal)
            self.cb[1].setChecked(self.amplifier)
            self.set_both()
        else:
            print(info + ' failed!')
            self.cb[2].setChecked(self.both)

    def set_both(self):
        # returns new checked state of 'both' checkbox
        # changes state only when signal and amplifier are both on or both off
        # this allows to click on 'both' to perform the last selection for both.
        if self.both:
            self.both = self.signal or self.amplifier
        else:
            self.both = self.signal and self.amplifier
        self.cb[2].setChecked(self.both)

    def get_save_data(self, data):
        "save current settings to data dictionary"
        state = (4 if self.both else 0)|(2 if self.amplifier else 0)|(1 if self.signal else 0)
        #print('get_save_data state =',state)
        data[self.name] = state

    def restore_save_data(self, data):
        "restore saved settings from data dictionary"
        if self.name in data:
            state = data[self.name]
            #print('restore_save_data state =', state)
            signal = (state & 1) == 1
            amp    = (state & 2) == 2
            both   = (state & 4) == 4
            if (signal == amp) and ((self.signal != signal) or (self.amplifier != amp)):
                self.onBoth(signal)
            else:
                if self.signal != signal: self.onSignal(signal)
                if self.amplifier != amp: self.onAmp(amp)
                self.both = both
                self.cb[2].setChecked(both)

class QRF_tab(iPCdev_tab):
    def initialise_GUI(self):
        # set update time how often status_monitor is called
        self.set_update_time_ms(UPDATE_TIME_MS)
        # call super class
        super(QRF_tab, self).initialise_GUI()

        # add check boxes to enable signal/power/both:
        place_below = False # True = below DDS frame, False = right of DDS frame
        layout = self.get_tab_layout()
        index = layout.count()
        self.power_cb = [None for _ in range(MAX_NUM_CHANNELS)]
        for i in range(index):
            widget = layout.itemAt(i).widget()
            if widget is not None:
                children = widget.findChildren(ToolPaletteGroup)
                for child in children:
                    if DDS_NAME in child._widget_groups:
                        index, toolpalette, button = child._widget_groups[DDS_NAME]
                        for j,dds in enumerate(toolpalette._widget_list):
                            if j >= MAX_NUM_CHANNELS:
                                print('error: maximum channels %i specified but %i existing!?' % (MAX_NUM_CHANNELS, len(toolpalette._widget_list)))
                                exit()
                            layout = dds._layout
                            connection = dds._hardware_name # connection = 'channel %i'
                            device = self.channels[connection]
                            hardware_info = device.properties[DEVICE_HARDWARE_INFO]
                            channel_index = hardware_info[DEVICE_INFO_CHANNEL]
                            cb = power_check_boxes(parent=self, name=device.name, channel=channel_index, align_horizontal=place_below)
                            if place_below: layout.addWidget(cb)
                            else:           layout.addWidget(cb,1,1)
                            self.power_cb[j] = cb

                            # add mode indicator after connection and channel name
                            # if there is a gate we insert mode before gate
                            mode = device.properties[DDS_CHANNEL_PROP_MODE]
                            label = dds._label.text().split('\n') # [connection, user given name + 'dyn'/'static']
                            if   label[1].endswith(DDS_NAME_DYNAMIC):
                                label[1] = label[1][:-len(DDS_NAME_DYNAMIC)]
                                static = False
                            elif label[1].endswith(DDS_NAME_STATIC ):
                                label[1] = label[1][:-len(DDS_NAME_STATIC)]
                                static = True
                            else:
                                raise LabscriptError("unexpected DDS name '%s'" % label[1])
                            label.insert(2,mode)
                            label = '\n'.join(label)
                            dds._label.setText(label)


        # Set the capabilities of this device
        self.supports_remote_value_check(False)
        self.supports_smart_programming(True)

    def init_tab_and_worker(self):
        # create worker using worker_path
        # note: updated from parent class
        #print('create worker', worker_path)
        self.create_worker(
            name        = self.primary_worker,
            WorkerClass = worker_path,
            workerargs  = self.worker_args,
        )
