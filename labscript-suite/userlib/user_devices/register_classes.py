#####################################################################
#####################################################################
from labscript_devices import register_classes
from user_devices.FPGA_device import FPGA_board

blacs_tab = 'user_devices.FPGA_device.FPGA_Tab'
runviewer_parser = 'user_devices.FPGA_device.RunviewerClass'

register_classes(
    'FPGA_board',
    BLACS_tab=blacs_tab,
    runviewer_parser=runviewer_parser,
)

register_classes(
    'AnalogChannels',
    BLACS_tab=None,
    runviewer_parser=runviewer_parser,
)

register_classes(
    'DigitalChannels',
    BLACS_tab=None,
    runviewer_parser=runviewer_parser,
)
