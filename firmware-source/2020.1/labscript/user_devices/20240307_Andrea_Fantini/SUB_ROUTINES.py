########## SUB ROUTINES #######################
# by Andrea Fantini for Sr FloRydberg Group   #
# register of actions for Labscript Ruotines  #
###############################################
from labscript_utils import import_or_reload
import labscript
import_or_reload('labscriptlib.Sr.connection_table')
from labscriptlib.Sr.connection_table import *
from user_devices.mogdevice import MOGDevice
import runmanager.remote
import h5py
if True: #init of globals and times
    if True: # Time Constants
        t=0
        dt=main_board.time_step # 1 us
        usec=dt
        us=usec
        msec=1000*dt
        ms=msec
        sec=1000000*dt
        s=sec
        min=60*sec
    settings_path='F:\\Experiments\\Sr\\SrParameters.h5'
    units={}
    for globals_group  in runmanager.get_grouplist(settings_path):
        for global_name in runmanager.get_globalslist(settings_path, globals_group):
            with h5py.File(settings_path,'r') as shot_h5py: global_units =  shot_h5py["globals"][globals_group]["units"].attrs[global_name]
            if global_units=='us': #base unit for time
                g_unit=usec
            elif global_units=='ms':
                g_unit=msec
            elif global_units=='s':
                g_unit=sec
            elif global_units=='Hz':#base unit for frequency
                g_unit=1
            elif global_units=='kHz':
                e_unit=1e3
            elif global_units=='MHz':
                g_unit=1e6
            else:
                g_unit=1
            units[str(global_name)]=g_unit
    GLOBALS={}
    for i in runmanager.remote.get_globals():
        GLOBALS[str(i)]=eval(i)*units[str(i)]

def BlueMot_load(tt, load_time):
    COILS_switch.go_high(tt) # Coils
    dueD_MOT_gate.go_high(tt) # 2D MOT
    treD_MOT_gate.go_high(tt) # 3D MOT
    tt+=load_time
    return tt

def BlueMot_off(tt):
    GLOBALS['TwoD_DELAY']
    dueD_MOT_gate.go_low(tt-GLOBALS['TwoD_DELAY']) #  need advance for the 2D MOT to turn off
    treD_MOT_gate.go_low(tt) # 3D
    COILS_switch.go_low(tt) # Coils
    return tt

def BlueMot(tt, loading_time, duration_wait):
    tt=BlueMot_load(tt, loading_time)
    BlueMot_off(tt+duration_wait)
    return tt

def take_absorbImaging(tt, beam_duration):
    trigger_delay=105*usec #100 for camera activation + 5 as safety buffer
    Basler_Camera_readout=1200*msec

    ImagingBeam_gate.go_high(tt)
    tt+=Basler_Camera.expose(tt-trigger_delay,'Atoms', frametype='tiff')
    tt+=beam_duration
    ImagingBeam_gate.go_low(tt)

    tt+=Basler_Camera_readout 

    ImagingBeam_gate.go_high(tt)
    tt+=Basler_Camera.expose(tt-trigger_delay,'Probe', frametype='tiff')
    tt+=beam_duration
    ImagingBeam_gate.go_low(tt)

    tt+=Basler_Camera_readout

    Basler_Camera.expose(tt-trigger_delay,'Background', frametype='tiff')

    tt+=Basler_Camera_readout

    return tt

def do_Tweezer(tt, Tweezer_duration):
    Tweezer_gate.go_high(tt)
    tt+Tweezer_duration
    Tweezer_gate.go_low(tt)
    return tt
    
def take_fluoImagig(tt):
    ImagingBeam_gate.go_high(tt+10*usec)
    tt+=Andor_Camera.expose(tt, 'Tweezer', frametype='tiff') 
    ImagingBeam_gate.go_low(tt)
    return tt

def MogLabs_newvalue(name, channel, value, newvalue):
    
    if name == 'blue': dev = MOGDevice('192.168.1.102')
    elif name=='red': dev = MOGDevice('192.168.1.103')
    else: raise Exception('NO OTHER DEVICES than blue and red, choose one')
    if value in ['FREQ', 'POW']:   
        command=value+', '+str(channel)+', '+str(newvalue)
        dev.cmd(command)
    else: raise Exception('NO ACCEPTABLE VALUE: or FREQ or POW, choose one')
    
    
    
