# internal pseudoclock device
# created April 2024 by Andi
# last change 27/5/2024 by Andi

from labscript_devices import register_classes

blacs_path     = 'user_devices.iPCdev.blacs_tabs.iPCdev_tab'
runviewer_path = 'user_devices.iPCdev.runviewer_parsers.iPCdev_parser'

register_classes(
    labscript_device_name='iPCdev',
    BLACS_tab=blacs_path,
    runviewer_parser=runviewer_path,
)

register_classes(
    labscript_device_name='iPCdev_device',
    BLACS_tab=blacs_path,
    runviewer_parser=runviewer_path,
)

