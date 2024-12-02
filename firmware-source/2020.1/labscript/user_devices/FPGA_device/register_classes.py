#####################################################################
# register_classes for FPGA-SoC device by Andreas Trenkwalder
# works as PseudoClockDevice
# created April 2024 by Andi
# last change 01/07/2024 by Andi
#####################################################################

from labscript_devices import register_classes

blacs_path     = 'user_devices.FPGA_device.blacs_tab.FPGA_tab'
runviewer_path = 'user_devices.FPGA_device.runviewer_parser.FPGA_parser'

register_classes(
    'FPGA_board',
    BLACS_tab=blacs_path,
    runviewer_parser=runviewer_path,
)

register_classes(
    'AnalogChannels',
    BLACS_tab=blacs_path,
    runviewer_parser=runviewer_path,
)

register_classes(
    'DigitalChannels',
    BLACS_tab=blacs_path,
    runviewer_parser=runviewer_path,
)

register_classes(
    'DDSChannels',
    BLACS_tab=blacs_path,
    runviewer_parser=runviewer_path,
)

register_classes(
    'SpecialIM',
    BLACS_tab=blacs_path,
    runviewer_parser=runviewer_path,
)

