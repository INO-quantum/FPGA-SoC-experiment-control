# Moglabs QRF 
# created 29/5/2024 by Andi
# modified from:
# https://github.com/specialforcea/labscript_suite/blob/a4ad5255207cced671990fff94647b1625aa0049/labscript_devices/MOGLabs_XRF021.py
# requires mogdevice.py, see: https://pypi.org/project/mogdevice/
# last change 29/5/2024 by Andi

from labscript_devices import register_classes

blacs_path  = 'user_devices.Moglabs_QRF.blacs_tabs.QRF_tab'
viewer_path = 'user_devices.iPCdev.runviewer_parsers.iPCdev_parser'

register_classes(
    labscript_device_name='QRF',
    BLACS_tab=blacs_path,
    runviewer_parser=viewer_path,
)

