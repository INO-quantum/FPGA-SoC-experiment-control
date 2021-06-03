##############################################################################################################
# import hardware_setup.py in folder labscript-suite/userlib/pythonlib
# this ensures consistent connection_table.py with all experimental scripts
##############################################################################################################
import hardware_setup

##############################################################################################################
# ATTENTION: start() and stop(1) cannot be missing! time for stop must be >0. 
##############################################################################################################
from labscript import start, stop
if __name__ == '__main__':
    start()
    stop(1)
