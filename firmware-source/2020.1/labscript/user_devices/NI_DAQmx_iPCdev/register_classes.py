#####################################################################
#                                                                   #
# /NI_DAQmx/register_classes.py                                     #
#                                                                   #
# Copyright 2018, Monash University, JQI, Christopher Billington    #
#                                                                   #
# This file is part of the module labscript_devices, in the         #
# labscript suite (see http://labscriptsuite.org), and is           #
# licensed under the Simplified BSD License. See the license.txt    #
# file in the root of the project for the full license.             #
#                                                                   #
#####################################################################
from labscript_devices import register_classes

# Jan-May 2024, modified by Andi to generate pseudoclock with NIDAQmx counter.

blacs_path  = 'user_devices.NI_DAQmx_iPCdev.blacs_tabs.NI_DAQmx_tab'
viewer_path = 'user_devices.NI_DAQmx_iPCdev.runviewer_parsers.NI_DAQmx_parser'

# The base class:
register_classes(
    labscript_device_name='NI_DAQmx_iPCdev',
    BLACS_tab=blacs_path,
    runviewer_parser=viewer_path,
)

register_classes(
    labscript_device_name='NI_PXIe_6738_iPCdev',
    BLACS_tab=blacs_path,
    runviewer_parser=viewer_path,
)

register_classes(
    labscript_device_name='NI_PXIe_6535_iPCdev',
    BLACS_tab=blacs_path,
    runviewer_parser=viewer_path,
)

