#####################################################################
# blacs_tab for FPGA-SoC device by Andreas Trenkwalder
# works as PseudoClockDevice
# created 6/4/2021
# last change 30/6/2024 by Andi
#####################################################################

from qtutils.qt.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

from labscript_utils.qtwidgets.toolpalette import ToolPaletteGroup
from labscript_utils.qtwidgets.digitaloutput import DigitalOutput
from labscript_utils.qtwidgets.analogoutput import AnalogOutput

from labscript_devices import BLACS_tab
from blacs.tab_base_classes import Worker, define_state, MODE_MANUAL, MODE_TRANSITION_TO_BUFFERED, MODE_TRANSITION_TO_MANUAL, MODE_BUFFERED
from blacs.device_base_class import DeviceTab

import logging
from .labscript_device import (
    log_level, get_channels,
    AO_NAME, DO_NAME, DDS_NAME, FPGA_NAME, ADD_WORKER,
    STR_ALLOW_CHANGES, STR_EXT_CLOCK, STR_IGNORE_CLOCK_LOSS, STR_INPUTS, STR_OUTPUTS,
    MSG_DISABLE, MSG_ABORTED, MSG_ENABLED, MSG_QUESTION,
    UPDATE_TIME_MS,
    save_print, in_dests, in_sources, in_levels, out_dests, out_sources, out_levels,
    get_ctrl_in, get_ctrl_out, reset_all,
)
from .shared import (
    DDS_CHANNEL_FREQ, DDS_CHANNEL_AMP, DDS_CHANNEL_PHASE,
    PROP_MIN, PROP_MAX,
)

# path to worker (must be in same folder)
#worker_path = '.blacs_worker.FPGA_worker' # python sucks! why this does not work?
worker_path = 'user_devices.FPGA_device.blacs_worker.FPGA_worker'

# simple dialog box for warning user!
# remains open until user clicks ok but does not prevent labscript from running.
class warn_user_dialog(QDialog):
    def __init__(self, parent, title, text):
        QDialog.__init__(self, parent)

        self.setAttribute(Qt.WA_DeleteOnClose, True)  # make sure the dialog is deleted when the window is closed
        self.setWindowTitle(title)
        self.resize(500, 200)

        # update must be called at least one time to display dialog
        self.text = text
        self.first_time = True
        self.count = 0

        # layout
        layout = QVBoxLayout()
        self.setLayout(layout)

        # top row = icon + text
        top = QHBoxLayout()
        layout.addLayout(top, stretch=0)

        # icon
        #self.Bicon = QPushButton('button with icon')
        #self.Bicon.setIcon(self.style().standardIcon(getattr(QStyle.StandardPixmap, 'SP_MessageBoxWarning')))
        self.icon = QLabel()
        icon = self.style().standardIcon(getattr(QStyle.StandardPixmap, 'SP_MessageBoxWarning'))
        self.icon.setPixmap(icon.pixmap(QSize(64,64)))
        #self.icon.setStyleSheet("QLabel {background-color: red;}")
        top.addWidget(self.icon, alignment=Qt.AlignCenter, stretch=0)

        # text
        self.label = QLabel()
        if '%i' in self.text: self.label.setText(self.text % self.count)
        else:                 self.label.setText(self.text)
        self.label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.label.setStyleSheet("QLabel {background-color: red;}")
        top.addWidget(self.label, stretch=1)

        # bottom row = button in middle
        bottom = QHBoxLayout()
        layout.addLayout(bottom, stretch=1)

        # ok button
        self.button = QPushButton('ok', self)
        self.button.setMinimumHeight(50)
        #self.button.setFixedHeight(50)
        self.button.clicked.connect(self.ok_clicked)
        self.button.setStyleSheet('QPushButton {color: red; border:1px solid #ff0000; border-radius: 3px;}')
        bottom.addStretch(stretch=1)
        bottom.addWidget(self.button, stretch=2)
        bottom.addStretch(stretch=1)

        #self.show() # show only after first update

    def update(self, count=None, text=None, title=None):
        "update text. show dialog if called the first time"
        if text is not None: self.text = text
        if count is not None: self.count = count
        else:                 self.count += 1
        if '%i' in self.text:
            save_print(self.text % self.count)
            self.label.setText(self.text % self.count)
        else:
            self.label.setText(self.text)
        if title is not None: self.setWindowTitle(title)
        if self.first_time:
            self.first_time = False
            self.show()
        else:
            self.setHidden(False)

    def ok_clicked(self):
        save_print('warn_user_dialog: ok (reset count)')
        self.count = 0
        self.setHidden(True)

    def closeEvent(self, event):
        save_print('warn_user_dialog: closed')
        event.accept()

class FPGA_buttons(QWidget):
    def __init__(self, name, parent, update=[], worker_args={}):
        """
        creates button widgets and clock selection check boxes for FPGA board
        name   = unique name used to save and restore data
        parent = DeviceTab class
        update = list of widgets with update(allow_changes) function called when allow_changes is clicked
        worker_args = optional worker arguments given for board in connection_table with startup selections:
            'ext_clock':         if True external clock should be used
            'ignore_clock_loss': if True loss of external clock should be ignored
        notes:
        - calls parent.get_state when state button pressed
        - calls parent.conn when disconnect button pressed
        - calls parent.abort when abort button pressed
        - calls worker onChangeExtClock when external clock check box has been changed
        - calls worker onChangeIgnoreClockLoss when ignore clock loss check box has been changed
        """
        super(FPGA_buttons, self).__init__(parent._ui)

        self.parent       = parent
        self.store_allow_changes = name + '_' + STR_ALLOW_CHANGES
        self.store_clock  = name + '_' + STR_EXT_CLOCK
        self.store_ignore = name + '_' + STR_IGNORE_CLOCK_LOSS
        self.update       = update
        self.worker_args  = worker_args

        self.dialog_enable = True

        self.allow_changes = False
        self.ext_clock = False
        self.ignore_clock_loss = False
        if STR_EXT_CLOCK in worker_args:
            self.ext_clock  = worker_args[STR_EXT_CLOCK]
        if STR_IGNORE_CLOCK_LOSS in worker_args:
            self.ignore_clock_loss  = worker_args[STR_IGNORE_CLOCK_LOSS]

        self.grid = QGridLayout(self)
        self.setLayout(self.grid)

        # device state button
        bt_state = QPushButton('get state')
        bt_state.setStyleSheet('QPushButton {border:1px solid #8f8f91; border-radius: 3px;}')
        self.grid.addWidget(bt_state,0,0)
        bt_state.clicked.connect(parent.get_state)

        # connect / disconnect button
        bt_conn = QPushButton('disconnect')
        bt_conn.setStyleSheet('QPushButton {border:1px solid #8f8f91; border-radius: 3px;}')
        self.grid.addWidget(bt_conn,0,1)
        bt_conn.clicked.connect(parent.conn)
        #TODO: get actual connection status and connect or disconnect with this button!

        # abort button
        bt_abort = QPushButton('abort!')
        bt_abort.setStyleSheet('QPushButton {color: red; border:1px solid #ff0000; border-radius: 3px;}')
        self.grid.addWidget(bt_abort,0,2)
        bt_abort.clicked.connect(parent.abort)

        # enable/disable changes checkbox
        self.cb_allow_changes = QCheckBox('allow changes (caution!)')
        self.cb_allow_changes.setChecked(self.allow_changes)
        self.cb_allow_changes.clicked.connect(self.onAllowChanges)
        self.grid.addWidget(self.cb_allow_changes,1,0)
        self.grid.addWidget(QLabel('changes here are temporary and are restored after tab restarts.\nfor permanent changes use connection table.'),2,0)

        # external clock
        self.cb_ext_clock = QCheckBox('external clock')
        self.cb_ext_clock.setChecked(self.ext_clock)
        #self.cb_ext_clock.setStyleSheet("color: black")
        self.cb_ext_clock.setEnabled(self.allow_changes)
        self.cb_ext_clock.clicked.connect(self.onChangeExtClock)
        self.grid.addWidget(self.cb_ext_clock,3,0)

        # ignore clock loss
        self.cb_ignore_clock_loss = QCheckBox('ignore clock loss')
        self.cb_ignore_clock_loss.setChecked(self.ignore_clock_loss)
        self.cb_ignore_clock_loss.setStyleSheet("color: red")
        self.cb_ignore_clock_loss.setEnabled(self.allow_changes)
        self.cb_ignore_clock_loss.clicked.connect(self.onChangeIgnoreClockLoss)
        self.grid.addWidget(self.cb_ignore_clock_loss, 3, 1)

        #self.grid.addSpacing(30)

    def onAllowChanges(self, state):
        self.allow_changes = self.cb_allow_changes.isChecked()
        self.cb_ext_clock.setEnabled(self.allow_changes)
        self.cb_ignore_clock_loss.setEnabled(self.allow_changes)
        for widget in self.update:
            widget.update(self.allow_changes)

    def onChangeExtClock(self, state):
        self.ext_clock = self.cb_ext_clock.isChecked()
        caption = (MSG_EXT_CLOCK % self.parent.device_name)
        if (not self.ext_clock) and (not self.parent.is_primary):
            if self.dialog_enable:
                # for secondary board disabling of external clock is not recommended
                qm = QMessageBox()
                ret = qm.question(self.parent._ui,
                                  caption + MSG_DISABLE + MSG_QUESTION,
                                  QUESTION_EXT_CLOCK % self.parent.device_name,
                                  qm.Yes | qm.No)
                if ret == qm.No:
                    self.ext_clock = True
                    self.cb_ext_clock.setChecked(True)
                    save_print(caption + MSG_DISABLE + MSG_ABORTED)
                    return
        if self.ext_clock: save_print(caption + MSG_ENABLED)
        else:              save_print(caption + MSG_DISABLED)
        # manually insert event into parent event queue as is done by tab_base_classes.py @define_state(MODE_MANUAL, True)
        # data = [function,[args,kwargs]] with function must be a generator, i.e. has to call yield.
        # see blacs/tab_base_classes.py for define_state and mainloop.
        self.parent.event_queue.put(allowed_states=MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=False, data=[self._onChangeExtClock, [[self.ext_clock],{}]])

    def _onChangeExtClock(self, parent, value):
        # executed by QT main thread (tab_base_classes.py Tab::mainloop). must be generator (with yield).
        yield (self.parent.queue_work(self.parent.primary_worker, 'onChangeExtClock', value))

    def onChangeIgnoreClockLoss(self, state):
        self.ignore_clock_loss = self.cb_ignore_clock_loss.isChecked()
        caption = MSG_IGNORE_CLOCK_LOSS % self.parent.device_name
        if self.ignore_clock_loss:
            if self.dialog_enable:
                qm = QMessageBox()
                ret = qm.question(self.parent._ui,
                                  caption + MSG_QUESTION,
                                  QUESTION_IGNORE_CLOCK_LOSS % self.parent.device_name,
                                  qm.Yes | qm.No)
                if ret == qm.No:
                    self.ignore_clock_loss = False
                    self.cb_ignore_clock_loss.setChecked(False)
                    save_print(caption + MSG_ABORTED)
                    return
        if self.ignore_clock_loss: save_print(caption + MSG_ENABLED)
        else:                      save_print(caption + MSG_DISABLED)
        # manually insert event into parent event queue as is done by tab_base_classes.py @define_state(MODE_MANUAL, True)
        # data = [function,[args,kwargs]] with function must be a generator, i.e. has to call yield.
        # see blacs/tab_base_classes.py for define_state and mainloop.
        self.parent.event_queue.put(allowed_states=MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=False, data=[self._onChangeIgnoreClockLoss, [[self.ignore_clock_loss], {}]])

    def _onChangeIgnoreClockLoss(self, parent, value):
        # executed by QT main thread (tab_base_classes.py Tab::mainloop). must be generator (with yield).
        yield (self.parent.queue_work(self.parent.primary_worker, 'onChangeIgnoreClockLoss', value))

    def add_update(self, widget):
        "add widget or list of widgets to be updated"
        if isinstance(widget, list):
            self.update += widget
        else:
            self.update.append(widget)

    #def get_save_data(self, data):
    #    "save current settings to data dictionary"
    #    data[self.store_allow_changes] = False # self.allow_changes. we always reset
    #    data[self.store_clock]  = self.ext_clock
    #    data[self.store_ignore] = self.ignore_clock_loss

    #def restore_save_data(self, data):
    #    "restore saved settings from data dictionary"
    #    if reset_all: return
    #    self.dialog_enable = False # temporarily disable dialog
    #    if (self.store_allow_changes in data):
    #        self.allow_changes = False #data[self.store_allow_changes]
    #        self.cb_ext_clock.setEnabled(self.allow_changes)
    #        self.cb_ignore_clock_loss.setEnabled(self.allow_changes)
    #        #self.onAllowChanges(None) # this makes problems when restarting tab without restarting blacs
    #    if (self.store_clock in data) and (STR_EXT_CLOCK not in self.worker_args):
    #        self.ext_clock = data[self.store_clock]
    #        self.cb_ext_clock.setChecked(self.ext_clock)
    #    if (self.store_ignore in data) and (STR_IGNORE_CLOCK_LOSS not in self.worker_args):
    #        self.ignore_clock_loss = data[self.store_ignore]
    #        self.cb_ignore_clock_loss.setChecked(self.ignore_clock_loss)
    #    self.dialog_enable = True # enable dialog

class FPGA_IO(QWidget):
    def __init__(self, parent, name = "", dests={}, sources={}, levels={}, showHeader=True, is_input=True, worker_args={}):
        """
        creates input and output selectors of FPGA board
        name = unique name of widget. used to store and restore settings.
        parent = DeviceTab class.
        dests  = list of destination strings
        sources = list of source strings
        levels = list of levels strings
        showHeader = if True header is shown, otherwise not
        is_input = if True sources are inputs and dests are possible trigger settings and
                   get_ctrl_in() is used to calculate trigger control register value and OnChangeInputs is called in worker,
                   if False sources are internal FPGA signals and dests are outputs and
                   get_ctrl_out() is used to calculate output control register value and OnChangeOutputs is called in worker.
        worker_args = optional worker arguments given for board in connection_table with startup selections:
        notes:
        - calls worker onChangeInputs/Outputs functions when user changes selection!
        """
        super(FPGA_IO, self).__init__(parent._ui)

        self.name        = name
        self.parent      = parent
        self.dests       = dests
        self.sources     = [] # list of source combobox
        self.levels      = [] # list of levels combobox
        self.is_input    = is_input
        self.init        = {}
        if self.is_input and (STR_INPUTS in worker_args):
            self.init = worker_args[STR_INPUTS]
        if (not self.is_input) and (STR_OUTPUTS in worker_args):
            self.init = worker_args[STR_OUTPUTS]

        self.change_enable = True
        self.dialog_enable = True

        self.grid = QGridLayout(self)
        self.setLayout(self.grid)

        self.value = 0;

        if showHeader:
            self.grid.addWidget(QLabel('destination'), 0, 0)
            self.grid.addWidget(QLabel('source'), 0, 1)
            self.grid.addWidget(QLabel('level'), 0, 2)
            row = 1
        else:
            row = 0

        for name,value in dests.items():
            src_bits, lvl_bits = value[1:3]
            if src_bits == 0 or lvl_bits == 0: continue # nothing enabled
            self.grid.addWidget(QLabel(name), row, 0)
            src = QComboBox()
            src.setEnabled(False)
            for source, src_bit in sources.items():
                if src_bits & (1<<src_bit):
                    src.addItem(source)
            self.grid.addWidget(src, row, 1)
            self.sources.append(src)
            lvl = QComboBox()
            lvl.setEnabled(False)
            for level, lvl_bit in levels.items():
                if lvl_bits & (1<<lvl_bit):
                    lvl.addItem(level, lvl_bits) # TODO: here was i instead of lvl_bits?
            self.grid.addWidget(lvl, row, 2)
            self.levels.append(lvl)
            src.currentIndexChanged.connect(self.changed)
            lvl.currentIndexChanged.connect(self.changed)
            row += 1

        # indicator/edit of actual settings in hex
        self.grid.addWidget(QLabel('value 0x'), row, 0)
        self.hex_value = QLineEdit('None')
        self.hex_value.setEnabled(False)
        self.hex_value.returnPressed.connect(self.value_changed)
        self.grid.addWidget(self.hex_value, row, 1)

        # init combo boxes (all must have been created). this calls 'changed' for each option.
        self.init_items(self.init, first_time=True)

        #self.grid.addSpacing(30)

    def init_items(self, init, first_time=False):
        # initialize combo boxes. if first_time = False take only options which are NOT in self.init.
        # this allows to give starting selections in worker_args,
        # or if no worker_args given, restore last settings in GUI (using restore_save_data).
        if len(init) > 0:
            self.change_enable = False # changed() will be called for each changed item. this avoids calling worker each time
            i = 0
            for name, value in self.dests.items():
                src_bits, lvl_bits = value[1:3]
                if src_bits == 0 or lvl_bits == 0: continue  # nothing enabled
                if name in init:
                    if first_time or (name not in self.init):
                        src = self.sources[i] # source combobox
                        index = src.findText(init[name][0])
                        if (index >= 0): src.setCurrentIndex(index)
                        else:            save_print("error init %s: '%s' is not in sources" % (self.name, init[name][0]))
                        lvl = self.levels[i] # level combobox
                        index = lvl.findText(init[name][1])
                        if (index >= 0): lvl.setCurrentIndex(index)
                        else:
                            save_print("error init %s: '%s' is not in levels" % (self.name, init[name][1]))
                            print(init)
                i += 1
            self.change_enable = True
            if first_time:
                # init hex value
                self.value = get_ctrl_in(init) if self.is_input else get_ctrl_out(init)
                self.hex_value.setText('%x'%self.value)
            else:
                # update of worker when all changes are done
                self.dialog_enable = False # disable dialog box
                self.changed(0)
                self.dialog_enable = True

    def value_changed(self):
        # user changed hex value and pressed return
        try:
            self.value = int(self.hex_value.text(), 16)
        except ValueError:
            print('%s is not a hexadecimal number! reverting to last valid number' % (self.hex_value.text()))
            self.hex_value.setText('%x' % self.value)
            return
        if self.is_input:
            selection = get_in_selection(self.value)
            print('new input config 0x%x' % self.value, selection)
        else:
            selection = get_out_selection(self.value)
            print('new output config 0x%x'%self.value, selection)
        self.init_items(selection, True)

    def changed(self, index):
        # user changed any combo box. for simplicity we go through all of them and recalculate control register value.
        #item = self.sender()
        #name = item.currentText()
        #i = item.itemData(index)
        if not self.change_enable: return # do nothing while init_items is active
        selection = {}
        i = 0
        for name, value in self.dests.items():
            src_bits, lvl_bits = value[1:3]
            if src_bits == 0 or lvl_bits == 0: continue  # nothing enabled
            source = self.sources[i].currentText()
            if (source != IN_SRC_NONE):
                selection[name] = (source, self.levels[i].currentText())
            i += 1
        if self.is_input:
            #print('changed', selection)
            value         = get_ctrl_in(selection)
            prim_sync_out = False
            sec_trg_in    = (not self.parent.is_primary) and (not is_in_start(value))
        else:
            value         = get_ctrl_out(selection)
            prim_sync_out = self.parent.is_primary and (not is_sync_out(value))
            sec_trg_in    = False
        if prim_sync_out or sec_trg_in:
            if prim_sync_out:
                caption = MSG_SYNC_OUT % self.parent.device_name
                message = QUESTION_SYNC_OUT % self.parent.device_name
            else:
                caption = MSG_START_TRG % self.parent.device_name
                message = QUESTION_START_TRG % self.parent.device_name
            if self.dialog_enable:
                # disabling of sync out on primary board and external trigger on secondary board is not recommended
                qm = QMessageBox()
                ret = qm.question(self.parent._ui, caption + MSG_DISABLE + MSG_QUESTION, message, qm.Yes | qm.No)
                if ret == qm.No:
                    save_print(caption + MSG_DISABLE + MSG_ABORTED)
                    # revert to previous selection
                    selection = get_in_selection(self.value) if self.is_input else get_out_selection(self.value)
                    self.init_items(selection, first_time=True)
                    return
            save_print(caption + MSG_DISABLED)
        self.value = value
        self.hex_value.setText('%x'%self.value)
        if self.is_input: save_print(MSG_INPUT_SETTING  % (self.parent.device_name, self.value, get_in_info(self.value)))
        else:             save_print(MSG_OUTPUT_SETTING % (self.parent.device_name, self.value, get_out_info(self.value)))
        # manually insert event into parent event queue as is done by tab_base_classes.py @define_state(MODE_MANUAL, True)
        # data = [function,[args,kwargs]] with function must be a generator, i.e. has to call yield.
        # see blacs/tab_base_classes.py for define_state and mainloop.
        self.parent.event_queue.put(allowed_states=MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=False, data=[self._changed, [[self.value],{}]])

    def _changed(self, parent, value):
        # executed by QT main thread (tab_base_classes.py Tab::mainloop). must be generator (with yield).
        yield (self.parent.queue_work(self.parent.primary_worker, 'onChangeInputs' if self.is_input else 'onChangeOutputs', value))

    def update(self, allow_changes):
        "if allow_changes enable changes otherwise not (grayed out)"
        for src in self.sources:
            src.setEnabled(allow_changes)
        for lvl in self.levels:
            lvl.setEnabled(allow_changes)
        self.hex_value.setEnabled(allow_changes)

    #def get_save_data(self, data):
    #    "save current settings to data dictionary"
    #    data[self.name] = int(self.value)

    #def restore_save_data(self, data):
    #    "restore saved settings from data dictionary"
    #    if reset_all: return
    #    if self.name in data:
    #        init = get_in_selection(data[self.name]) if self.is_input else get_out_selection(data[self.name])
    #        #print(init)
    #        #save_print('FPGA_IO restore_save_data old:', self.init)
    #        self.init_items(init)
    #        #save_print('FPGA_IO restore_save_data new:', self.init)

@BLACS_tab
class FPGA_tab(DeviceTab):
    def initialise_GUI(self):
        # reduce number of log entries in logfile (labscript-suite/logs/BLACS.log)
        # TODO: maybe there is a global setting for this but could not find?
        self.logger.setLevel(log_level)
        logger = ['BLACS.AnalysisSubmission.mainloop', 'BLACS.queue_manager.thread','BLACS','BLACS.ConnectionTable','BLACS.QueueManager','BLACS.FrontPanelSettings']
        for l in logger:
            log = logging.getLogger(l)
            log.setLevel(log_level)

        save_print('FPGA_Tab initialise_GUI:', self.device_name)

        device = self.settings['connection_table'].find_by_name(self.device_name)
        self.con = device.BLACS_connection
        self.num_racks = device.properties['num_racks']
        self.bus_rate = device.properties['bus_rate']
        self.worker_args = device.properties['worker_args']
        try:
            self.is_primary = device.properties['is_primary']
            self.boards = device.properties['boards']
        except KeyError:
            # sometimes labscript goes into a strange loop and gives KeyError here although key should exist in hdf5:
            # runmanager says that cannot submit job since connection table is not a subset of experiment and thus does not update the hdf5.
            # but BLACS complains about KeyError in hdf5 file - which runmanager does not update.
            # seems that hdf5 is somtimes broken or corrupted? maybe just deleting the hdf5 might help?
            # it happended the last time when I added Moglabs QRF device which gave an error during compilation of connection table.
            # so I removed it from connection table and BLACS compiled it ok but when tried to create new hdf5 with runmanager had then this strange error.
            # I try to break the loop here such that BLACS starts without errors and runmanager can update the hdf5 file.
            save_print("strange error occurred (again). try submitting hdf5 with runmanager and/or recompile connection table.")
            self.is_primary = True
            self.boards = []

        save_print("'%s': %i racks, %.3fMHz bus rate" % (self.device_name, self.num_racks, self.bus_rate / 1e6))
        save_print(device.properties)
        if self.is_primary:
            save_print("'%s' primary board with %i secondary boards connected:" % (self.device_name, len(self.boards)))
            for sec in self.boards:
                save_print("'%s' (secondary)" % sec)
        else:
            if len(self.boards) != 1: raise LabscriptError("secondary board '%s' must have one entry in boards, not %i!" % (self.device_name, len(self.boards)))
            save_print('secondary board')
        save_print("'%s' init devices" % (self.device_name))

        # get all channels of board
        # note: connections = pseudo clock -> clockline -> intermediate device -> channel
        #ao_list = {}
        #do_list = {}
        #dds_list = {}
        ao_prop = {}
        do_prop = {}
        dds_prop = {}
        self.channels = {}
        all_IDs = {}
        for pseudoclock in device.child_list.values():
            if pseudoclock.device_class=="FPGA_PseudoClock":
                for clockline in pseudoclock.child_list.values():
                    if clockline.device_class == 'ClockLine':
                        for IM_name, IM in clockline.child_list.items():
                            if IM.device_class == 'AnalogChannels':
                                child_list = get_channels(IM)
                                for [ID, props, child, key, unit_conversion_class] in child_list.values():
                                    all_IDs[key] = ID
                                    ao_prop[key] = props
                                    self.channels[key] = child
                            elif IM.device_class == 'DigitalChannels':
                                child_list = get_channels(IM)
                                for [ID, props, child, key, unit_conversion_class] in child_list.values():
                                    all_IDs[key] = ID
                                    do_prop[key] = props
                                    self.channels[key] = child
                            elif IM.device_class == 'DDSChannels':
                                child_list = get_channels(IM)
                                for [ID, _, child, key, unit_conversion_class] in child_list.values():
                                    props = {}
                                    for name, sub in child.child_list.items():
                                        sub_prop = sub.properties['sub-channel']
                                        props[sub_prop] = sub.properties['blacs_props']
                                    all_IDs[key] = ID
                                    dds_prop[key] = props
                                    self.channels[key] = child
                                    print(child.name, props)
                            else:
                                save_print("'%s' unknown device '%s' (ignore)" % (IM_name, IM.device_class))

        if False:
            # get ananlog and digital output properties.
            # key = channel name (like AO0.00.0) as given to AnaolgChannel, DigitalChannel
            # all_childs is used by get_child_from_connection_table to find child connection object for channel name
            # all_IDs is used to get ID from channel name for sorting function
            # TODO: generate these lists above in one loop
            ao_prop = {}
            for name, ll in ao_list.items():
                [ID, props, child, key, unit_conversion_class] = ll
                ao_prop[key] = props
                self.channels[key] = child
                all_IDs[key] = ID

            #get digital output properties (which are empty at the moment)
            do_prop = {}
            for name, ll in do_list.items():
                [ID, props, child, key, unit_conversion_class] = ll
                do_prop[key] = props
                self.channels[key] = child
                all_IDs[key] = ID

            dds_prop = {}
            for name, ll in dds_list.items():
                [ID, props, child, key, unit_conversion_class] = ll
                dds_prop[key] = props
                self.channels[key] = child
                all_IDs[key] = ID

        print(self.channels)
        for key, child in self.channels.items():
            print('channel',key,'name',child.name)

        # Create the output objects
        save_print('create %i analog  outputs' % (len(ao_prop)))
        save_print('create %i digital outputs' % (len(do_prop)))
        save_print('create %i DDS     outputs' % (len(dds_prop)))

        if len(ao_prop ) > 0: self.create_analog_outputs(ao_prop)
        if len(do_prop ) > 0: self.create_digital_outputs(do_prop)
        if len(dds_prop) > 0: self.create_dds_outputs(dds_prop)

        #returns integer ID = unique identifier of channel (type|rack|address|channel)
        def sort(channel):
            return all_IDs[channel]

        # create widgets and place on GUI
        dds_widgets, ao_widgets, do_widgets = self.auto_create_widgets()
        for name, prop in ao_widgets.items():
            # if there is a unit conversion class select unit, decimals* and step size*. Volts can be still selected manually.
            # TODO: (*) these settings are not permanent: changed when user selects Volts and then goes back to 'unit'.
            child = self.channels[name]
            if child.unit_conversion_class is not None:
                # select unit
                try:
                    unit = child.unit_conversion_params['unit']
                    # replace % symbol since in unit conversion class have to define %_to_base and %_from_base functions which would be invalid names
                    # TODO: how to display still '%' instead?
                    if unit == '%': unit = 'percent'
                    prop.set_selected_unit(unit)
                except KeyError:
                    pass
                # save_print("analog out '%s' selected unit '%s'" % (name, prop.selected_unit))
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
                # the limits we have already set via voltage limits. this is permanent.
                #prop.set_limits(lower, upper)

        self.auto_place_widgets((AO_NAME, ao_widgets, sort),
                                (DO_NAME, do_widgets, sort),
                                (DDS_NAME, dds_widgets, sort))

        if False:
            # change ananlog output list to contain only IDs and last value
            # key = channel name as given to AnaolgChannel, DigitalChannel
            ao_list2 = {}
            for name, ll in ao_list.items():
                [ID, props, child, key, unit_conversion_class] = ll
                ao_list2[key] = [ID, 0]
            # change digital output list to contain only IDs and last value
            do_list2 = {}
            for name, ll in do_list.items():
                [ID, props, child, key, unit_conversion_class] = ll
                do_list2[key] = [ID, 0]
            # change DDS output list to contain only IDs and last value
            dds_list2 = {}
            for name, ll in dds_list.items():
                [ID, props, child, key, unit_conversion_class] = ll
                dds_list2[key] = [ID, {'freq':0, 'amp':0, 'phase':0}]

        # create the worker process
        # each board gets his own name, so we can refer to it
        self.primary_worker = self.device_name + ADD_WORKER
        #self.secondary_worker = self.device_name + ADD_WORKER
        #save_print('create worker',self.primary_worker,'args',self.worker_args)
        pm = self.create_worker(self.primary_worker, worker_path, {
            'con'           : self.con,         # string 'IP:port'
            #'do_list'       : do_list2,         # list of digital outputs
            #'ao_list'       : ao_list2,         # list of analog outputs
            #'dds_list'      : dds_list2,        # list of dds channels
            'channels'      : self.channels,    # list of all channels, key = connection, value = connection object
            'num_racks'     : self.num_racks,   # number of racks
            'bus_rate'      : self.bus_rate,    # integer rate in Hz
            'is_primary'    : self.is_primary,  # bool primary = True, secondary = False
            'boards'        : self.boards,      # for primary: names of secondary boards, for secondary: name of primary board
            'worker_args'   : self.worker_args, # additional worker arguments
        })

        # Set the capabilities of this device
        # TODO: should check what these make. maybe is useful for something?
        self.supports_remote_value_check(False)
        self.supports_smart_programming(False)

        # add 'FPGA board' settings at bottom
        layout = self.get_tab_layout()
        widget = QWidget()
        toolpalettegroup = ToolPaletteGroup(widget)
        toolpalette = toolpalettegroup.append_new_palette(FPGA_NAME)
        layout.insertWidget(1,widget)

        if True:
            # customize digital and analog outputs GUI appearance
            # + close all widget group buttons
            # + change color of digital outputs since is hardly readable
            index = layout.count()
            for i in range(index):
                widget = layout.itemAt(i).widget()
                if widget is not None:
                    # find ToolPaletteGroup with is the container class which allows to hide/unhide all outputs
                    children = widget.findChildren(ToolPaletteGroup)
                    for child in children:
                        #if isinstance(child,ToolPaletteGroup):
                        if AO_NAME in child._widget_groups:
                            child.hide_palette(AO_NAME)
                        if DO_NAME in child._widget_groups:
                            child.hide_palette(DO_NAME)
                        if DDS_NAME in child._widget_groups:
                            child.hide_palette(DDS_NAME)
                        if FPGA_NAME in child._widget_groups:
                            child.hide_palette(FPGA_NAME)
                    # change digital output text color since text is hardly readable
                    DO = widget.findChildren(DigitalOutput)
                    for do in DO:
                        #save_print('set color of digital output', do.text())
                        do.setToolTip(do.text())
                        #do.setText('changed!\n')
                        do.setStyleSheet('QPushButton {color: white; font-size: 14pt;}')
                        #do.setStyleSheet('QPushButton {color: white; background-color: darkgreen; font-size: 14pt;} QPushButton::pressed {color: black; background-color: lightgreen; font-size: 14pt;}')
                        #do.setStyleSheet('QPushButton {color: white; font-size: 14pt;} QPushButton::pressed {color: black; font-size: 14pt;}')

        # optional worker arguments
        #save_print("'%s' worker args:" % self.device_name, self.worker_args)

        # create buttons and clock check boxes
        self.buttons = FPGA_buttons(parent=self, name=self.device_name, update=[], worker_args=self.worker_args)
        toolpalette.insertWidget(0, self.buttons)
        #toolpalette.addSpacing(30)

        # create list of input selectors
        self.inputs = FPGA_IO(
                    name        = self.device_name+'_inputs',
                    parent      = self,
                    is_input    = True,
                    dests       = in_dests,
                    sources     = in_sources,
                    levels      = in_levels,
                    worker_args = self.worker_args
        )
        toolpalette.insertWidget(1, self.inputs)
        #toolpalette.addSpacing(30)
        self.buttons.add_update(self.inputs)

        # create list of output selectors
        self.outputs = FPGA_IO(
                    name        = self.device_name+'_outputs',
                    parent      = self,
                    is_input    = False,
                    dests       = out_dests,
                    sources     = out_sources,
                    levels      = out_levels,
                    worker_args = self.worker_args,
                    showHeader  = False
        )
        toolpalette.insertWidget(2, self.outputs)
        #toolpalette.addStretch()
        self.buttons.add_update(self.outputs)

        # warning dialog. count '%i' is maintained by warning_user_dialog
        self.warning_text = "'%s': external clock lost on last %%i runs!" % self.device_name
        self.warning = warn_user_dialog(parent=self._ui, text=self.warning_text, title="'%s' warning!" % self.device_name)
        #self.warning.update("'%s' test" % self.device_name)

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

    @define_state(MODE_BUFFERED, True)
    def abort(self, state):
        result = yield (self.queue_work(self.primary_worker, 'abort_buffered'))
        save_print('FPGA: abort', result)

    @define_state(MODE_MANUAL,True)
    def get_state(self, state):
        result = yield(self.queue_work(self.primary_worker, 'FPGA_get_board_state'))
        save_print('FPGA (prim): get_state', result)
        if False and self.is_primary:
            result = yield (self.queue_work("secondary"+ADD_WORKER, 'FPGA_get_board_state'))
            save_print('FPGA (sec): get_state', result)

    @define_state(MODE_MANUAL, True)
    def conn(self, state):
        result = yield(self.queue_work(self.primary_worker, 'FPGA_disconnect'))
        save_print('FPGA: dicsonnect', result)

    @define_state(MODE_BUFFERED, True)
    def start_run(self, notify_queue):
        #save_print('start run (FPGA_tab)')
        # note: this is called only for primary pseudoclock device! and not for other boards!
        #       therefore, the worker must call FPGA_worker::start_run directly from transition_to_buffered.
        #success = yield (self.queue_work(self.primary_worker, 'start_run'))
        #if success:
        if True:
            # update status during run every UPDATE_TIME_MS
            self.statemachine_timeout_add(UPDATE_TIME_MS, self.status_monitor, notify_queue)
            # check of end state in MODE_MANUAL after run finished
            # this way we can update dialog box in GUI after transition_to_manual
            # from worker we have no access to GUI and most likely cannot call back to FPGA_Tab?
            self.event_queue.put(MODE_MANUAL, True, False, [self.status_end, ((),{})], priority=0)
        else:
            raise RuntimeError('Failed to start run')
    
    #@define_state(MODE_BUFFERED, True)
    @define_state(MODE_MANUAL | MODE_BUFFERED | MODE_TRANSITION_TO_BUFFERED | MODE_TRANSITION_TO_MANUAL, True)
    def status_monitor(self, notify_queue):
        # note: I could not find a way to call this for all boards!
        #save_print('status monitor (FPGA_tab)')
        result = yield(self.queue_work(self.primary_worker, 'status_monitor', False))
        if result[0]: # end or error
            # indicate that experiment cycle is finished.
            # this causes transition_to_manual called on all workers.
            notify_queue.put('done')
            # do not call status_monitor anymore
            self.statemachine_timeout_remove(self.status_monitor)

    @define_state(MODE_MANUAL, True)
    def status_end(self,test=None):
        # check final state after experimental cycle is finished.
        # this is called as soon as transition_to_manual is finished and before the next transition_to_buffered.
        # at this time all boards are stopped and we can get final status of all boards.
        # TODO: get status of all boards, not only warnings and display in dialog box on any error/warning
        result, warnings, changed = yield(self.queue_work(self.primary_worker, 'status_monitor', True))
        if len(warnings) > 0:
            save_print('FPGA_tab: %i warnings' % (len(warnings)))
            if len(warnings) == 1:
                text = "external clock lost %i times of "
            else:
                text = "external clock lost %%i times for %i boards: " % (len(warnings))
            for i, sec in enumerate(warnings):
                if i == 0:
                    text += sec
                else:
                    text += ', ' + sec
            self.warning.update(text=text)

        # update changed channels
        #changed = {}
        if False and len(changed) > 0:
            # TODO: disabled since there is some bug!
            #       additonally, this is transmitted at the moment only for primary board!
            #       would need to transmit changed channels from sec -> prim -> here
            for channel, value in changed.items():
                print(channel, 'changed to', value)
                count = len(changed)
                layout = self.get_tab_layout()
                index = layout.count()
                for i in range(index):
                    widget = layout.itemAt(i).widget()
                    if widget is not None:
                        if count == 0: break
                        DO = widget.findChildren(DigitalOutput)
                        for do in DO:
                            if do._DO._hardware_name in changed.keys():
                                do.setStyleSheet('QPushButton {color: black; background-color: red; font-size: 14pt;}')
                                do.clicked.connect(lambda: self.reset_do(do))
                                if --count == 0: break
                        if count == 0: break
                        AO = widget.findChildren(AnalogOutput)
                        for ao in AO:
                            if ao._AO._hardware_name in changed.keys():
                                ao._label.setStyleSheet('QLabel {color: red;}')
                                print([ao._label.text(),ao._AO._hardware_name])
                                ao._spin_widget.valueChanged.connect(lambda:self.reset_ao(ao))
                                if --count == 0: break
                    if count == 0: break

    def reset_do(self, do):
        do.setStyleSheet('QPushButton {color: white; background-color: lightgreen; font-size: 14pt;}')
        #do.clicked.disconnect() this always fails!?

    def reset_ao(self, ao):
        ao._label.setStyleSheet('QLabel { color: black; }')
        #ao._spin_widget.valueChanged.disconnect() this always fails!?
        print('reset_ao', ao._label.text())

    def get_save_data(self):
        "return all GUI settings to be retrieved after BLACS restarts"
        data = {}
        #self.inputs.get_save_data(data)
        #self.outputs.get_save_data(data)
        #self.buttons.get_save_data(data)
        #save_print("'%s' get_save_data:" %  self.device_name, data)
        return data

    def restore_save_data(self, data):
        """
        get GUI settings. settings in worker_args have precedence.
        unfortunately is called AFTER initialize_GUI, so we have to init stuff several times.
        data might be empty.
        """
        if reset_all: return
        #save_print("'%s' restore_save_data:" % self.device_name, data)
        #self.inputs.restore_save_data(data)
        #self.outputs.restore_save_data(data)
        #self.buttons.restore_save_data(data)

