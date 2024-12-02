#####################################################################
#                                                                   #
# /NI_DAQmx/blacs_tab.py                                            #
#                                                                   #
# Copyright 2018, Monash University, JQI, Christopher Billington    #
#                                                                   #
# This file is part of the module labscript_devices, in the         #
# labscript suite (see http://labscriptsuite.org), and is           #
# licensed under the Simplified BSD License. See the license.txt    #
# file in the root of the project for the full license.             #
#                                                                   #
#####################################################################

# Jan-May 2024, modified by Andi to generate pseudoclock with NIDAQmx counter.
# last change 14/6/2024 by Andi

import labscript_utils.h5_lock
import h5py
from labscript import LabscriptError

from labscript_devices.NI_DAQmx.utils import split_conn_AO, split_conn_DO
import warnings

from user_devices.iPCdev.blacs_tabs import iPCdev_tab

from PyQt5.QtWidgets import QPushButton

worker_path = 'user_devices.NI_DAQmx_iPCdev.blacs_workers.NI_DAQmx_OutputWorker'

# status monitor update time
UPDATE_TIME_MS = 250

class NI_DAQmx_tab(iPCdev_tab):
    def initialise_GUI(self):
        # set update time how often status_monitor is called
        self.set_update_time_ms(UPDATE_TIME_MS)
        # call super class
        super(NI_DAQmx_tab, self).initialise_GUI()

    def init_tab_and_worker(self):

        # get min and max voltage range
        AO_base_units = 'V'
        if self.device.properties['num_AO'] > 0:
            # note: 'AO_range' from connection_table or from labscript_devices.models CAPABILITIES
            AO_base_min, AO_base_max = self.device.properties['AO_range']
        else:
            AO_base_min, AO_base_max = None, None
        AO_base_step = 0.1
        AO_base_decimals = 3
        self.worker_args.update({
            'Vmin': AO_base_min,
            'Vmax': AO_base_max,
        })

        # create worker
        # note: updated from parent class
        print('create worker', worker_path)
        self.create_worker(
            name        = self.primary_worker,
            WorkerClass = worker_path,
            workerargs  = self.worker_args,
        )

        # Set the capabilities of this device
        self.supports_remote_value_check(False)
        self.supports_smart_programming(True)
