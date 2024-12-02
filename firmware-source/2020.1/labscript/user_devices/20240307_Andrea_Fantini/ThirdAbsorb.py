from labscript import start, stop #                                                 |
from labscript_utils import import_or_reload #                                      |
import_or_reload('labscriptlib.Sr.SUB_ROUTINES') #                                  |
from labscriptlib.Sr.SUB_ROUTINES import * #                                        |
#________________________ GENERIC LIBRARIES ________________________________________#


start()
t+=dt
if GLOBALS['CALIBRATION']: G_Imaging_Frq=GLOBALS['CAL_Imaging_Frq']/1e6
else:G_Imaging_Frq=GLOBALS['Imaging_Frq']/1e6
print(G_Imaging_Frq)
ImagingBeam.DDS.setfreq(t, G_Imaging_Frq)
ImagingBeam.DDS.frequency.add_instruction(t, G_Imaging_Frq)
# MogLabs_newvalue('blue', 4, 'FREQ',G_Imaging_Frq)

for i in range(0,GLOBALS['n_loop']):

    t=BlueMot(t, GLOBALS['loadTime_BlueMOT'], GLOBALS['MOT_duration'])

    t+=GLOBALS['TOF'] # wait for time of fligh

    t=take_absorbImaging(t, GLOBALS['AbsImgPulse_duration'])

stop(t+1*sec)
