import labscript_utils.h5_lock
import h5py
import numpy as np

# Jan-May 2024, modified by Andi to generate pseudoclock with NIDAQmx counter.
# this is just a wrapper to iPCdev_parser. you can also directly register iPCdev_parser in register_classes.py

from user_devices.iPCdev.runviewer_parsers import iPCdev_parser

class NI_DAQmx_parser(iPCdev_parser):
    def __init__(self, path, device):
        super(NI_DAQmx_parser, self).__init__(path, device)
