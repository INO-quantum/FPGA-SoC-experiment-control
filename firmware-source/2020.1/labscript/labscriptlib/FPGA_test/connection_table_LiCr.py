#!/usr/bin/env python
##############################################################################################################
# connection_table.py
# import global hardware_setup.py file from lbascript-suite/userlib/pythonlib directory
# importing connection_table.py into individual experimental sequence file does not work!?
# but importing hardware_setup.py from connection_table.py works.
# this is much more convenient than to have connection_table defined in EVERY experimental sequence and
# moreover one needs to change only a single file!
##############################################################################################################

# 2022/01/06, 17:59:47
# automatically generated labscript experimental sequence from '0field_check.prg'
# command line: 'LVparser.py -p ./LiCr -f 0field_check.prg -a ListOfActionAnalog.txt -d ListOfActionTTL.txt -o 0field_check.py'

# imports
import numpy as np
from labscript import start, stop, add_time_marker, LabscriptError, AnalogOut, DigitalOut, UnitConversion
from user_devices.FPGA_device import FPGA_board, DigitalChannels, AnalogChannels, PRIMARY_IP, SECONDARY_IP, DEFAULT_PORT #, generic_conversion
#from labscriptlib.FPGA_test.generic_conversion import generic_conversion
from labscript import generic_conversion

#FPGA boards
board0 = FPGA_board(name='board0', ip_address=PRIMARY_IP, ip_port=DEFAULT_PORT, bus_rate=1.000000, num_racks=1)

#analog outputs
AnalogChannels(name='AO0', parent_device=board0, rack=0, max_channels = 2)
AnalogOut     (name='IR_AOM_no2_percent', parent_device=AO0, connection='0x2', unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit':'%', 'equation':'(-0.02063+3.62077*np.tan(0.01724-0.19288*np.sqrt(x/100)+1.39915*x/100))', 'min':0.0, 'max':100.0})
AnalogOut     (name='IR_laser_no3_W', parent_device=AO0, connection='0x3', unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit':'W', 'equation':'np.sign(x-7.0)*(1.04532+np.sqrt(abs(-0.04508+(0.04255*x-0.07844)**2)))', 'min':8.0, 'max':212.35339050208577})
AnalogChannels(name='AO1', parent_device=board0, rack=0, max_channels = 2)
AnalogOut     (name='Cr_AOM_MOT_60to127MHz_no4_MHz', parent_device=AO1, connection='0x4', unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit':'MHz', 'equation':'(x-65.5)/17.1', 'min':0.0, 'max':236.50000000000003})
AnalogOut     (name='Cr_AOM_TC_70to115MHz_no5_MHz', parent_device=AO1, connection='0x5', unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit':'MHz', 'equation':'(x-64.8)/8.65', 'min':0.0, 'max':151.3})
AnalogChannels(name='AO2', parent_device=board0, rack=0, max_channels = 2)
AnalogOut     (name='Green_AOM_no6_W', parent_device=AO2, connection='0x6', unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit':'W', 'equation':'(-0.017+2.39297+3.69834*np.tan(-0.57803+0.02901*np.sqrt(x/100)+0.73451*x/100+0.93362*(x/100)**3))', 'min':0.0, 'max':100.00106433807996})
AnalogOut     (name='Li_cool_int_no7_percent', parent_device=AO2, connection='0x7', unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit':'%', 'equation':'(0.72168*np.tan(0.011379*((x+7.1646)))-3.2231-np.exp(-0.35968*x)*0.28516)', 'min':0.0, 'max':100.0})
AnalogChannels(name='AO3', parent_device=board0, rack=0, max_channels = 2)
AnalogOut     (name='MOT_current_0to100A_no8_A', parent_device=AO3, connection='0x8', unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit':'A', 'equation':'(x-0.39562)/246.3221*10.000000', 'min':-245.92648000000003, 'max':246.71771999999999})
AnalogOut     (name='dont_use_no9_V', parent_device=AO3, connection='0x9')
AnalogChannels(name='AO4', parent_device=board0, rack=0, max_channels = 2)
AnalogOut     (name='Li_cooling_no10_MHz', parent_device=AO4, connection='0xa', unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit':'MHz', 'equation':'(x-80.237)/15.224', 'min':0.0, 'max':232.477})
AnalogOut     (name='Li_repumper_no11_MHz', parent_device=AO4, connection='0xb', unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit':'MHz', 'equation':'(x-129.395)/33.752', 'min':0.0, 'max':466.9150000000001})
AnalogChannels(name='AO5', parent_device=board0, rack=0, max_channels = 2)
AnalogOut     (name='Li_ZS_AOM_74to140MHz_no12_MHz', parent_device=AO5, connection='0xc', unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit':'MHz', 'equation':'(x-70.52)/86.7*10.000000', 'min':0.0, 'max':157.22})
AnalogOut     (name='Li_rep_int_no13_percent', parent_device=AO5, connection='0xd', unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit':'%', 'equation':'-2.314*np.log(1-x*0.986/100)*32767/10/3276.700000', 'min':0.0, 'max':100.0})
AnalogChannels(name='AO6', parent_device=board0, rack=0, max_channels = 2)
AnalogOut     (name='FB_current_0to200A_no14_A', parent_device=AO6, connection='0xe', unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit':'A', 'equation':'x*5/200', 'min':-400.0, 'max':400.0})
AnalogOut     (name='dont_use_no15_V', parent_device=AO6, connection='0xf')
AnalogChannels(name='AO7', parent_device=board0, rack=0, max_channels = 2)
AnalogOut     (name='Cr_AOM_MOT_int_no16_percent', parent_device=AO7, connection='0x10', unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit':'%', 'equation':'(-7.98923+0.26451*np.sqrt(x)+2.0896E-6*x**3-2.00775E-4*x**2)', 'min':0.0, 'max':100.0})
AnalogOut     (name='Cr_AOM_R1_int_no17_percent', parent_device=AO7, connection='0x11', unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit':'%', 'equation':'(-1.97067*np.log((105.585441-x)/110.718))', 'min':0.0, 'max':100.0})
AnalogChannels(name='AO8', parent_device=board0, rack=0, max_channels = 2)
AnalogOut     (name='Crossed_AOM_no18_percent', parent_device=AO8, connection='0x12', unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit':'%', 'equation':'(3.65118+0.52383*np.tan(1.34955-3.3005*np.sqrt(x/100)+0.53289*x/100))', 'min':0.1, 'max':100.0})
AnalogOut     (name='Crossed_Green_no19_percent', parent_device=AO8, connection='0x13', unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit':'%', 'equation':'x', 'min':0.0, 'max':100.0})
AnalogChannels(name='AO9', parent_device=board0, rack=0, max_channels = 2)
AnalogOut     (name='Analog_no20_V', parent_device=AO9, connection='0x14')
AnalogOut     (name='Analog_no21_V', parent_device=AO9, connection='0x15')
AnalogChannels(name='AO10', parent_device=board0, rack=0, max_channels = 2)
AnalogOut     (name='Analog_no22_V', parent_device=AO10, connection='0x16')
AnalogOut     (name='Li_AOM_abs_img_70to110MHz_no23_MHz', parent_device=AO10, connection='0x17', unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit':'MHz', 'equation':'(x-85.150)/16.629', 'min':0.0, 'max':251.44000000000003})
AnalogChannels(name='AO11', parent_device=board0, rack=0, max_channels = 2)
AnalogOut     (name='Analog_no24_V', parent_device=AO11, connection='0x18')
AnalogOut     (name='Analog_no25_V', parent_device=AO11, connection='0x19')
AnalogChannels(name='AO12', parent_device=board0, rack=0, max_channels = 2)
AnalogOut     (name='Cr_AOM_spectr_60to137MHz_no26_MHz', parent_device=AO12, connection='0x1a', unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit':'MHz', 'equation':'(x-90.608)/16.647', 'min':0.0, 'max':257.078})
AnalogOut     (name='Cr_AOM_ZS_48to94MHz_no27_MHz', parent_device=AO12, connection='0x1b', unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit':'MHz', 'equation':'(x-80.30)/10.85', 'min':0.0, 'max':188.8})
AnalogChannels(name='AO13', parent_device=board0, rack=0, max_channels = 2)
AnalogOut     (name='Analog_no28_V', parent_device=AO13, connection='0x1c')
AnalogOut     (name='Analog_no29_V', parent_device=AO13, connection='0x1d')
AnalogChannels(name='AO14', parent_device=board0, rack=0, max_channels = 2)
AnalogOut     (name='Analog_no30_V', parent_device=AO14, connection='0x1e')
AnalogOut     (name='Analog_no31_V', parent_device=AO14, connection='0x1f', unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit':'V', 'equation':'(x-0.01348)/195.1084*10.000000', 'min':-195.09492, 'max':195.12187999999998})
AnalogChannels(name='AO15', parent_device=board0, rack=0, max_channels = 2)
AnalogOut     (name='DDS_no32_index', parent_device=AO15, connection='0x20', unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit':'index', 'equation':'x', 'min':0.0, 'max':1024})

#digital outputs
DigitalChannels(name='DO0', parent_device=board0, connection='0x0', rack=0, max_channels = 16)
DigitalOut     (name='MOT_IGBT_no0per1_on', parent_device=DO0, connection=0)
DigitalOut     (name='FB_Helmholtz_no0per2_on', parent_device=DO0, connection=1)
DigitalOut     (name='MOT_Helmholtz_no0per3_on', parent_device=DO0, connection=2)
DigitalOut     (name='Cr_ZS_current_no0per4_on', parent_device=DO0, connection=3)
DigitalOut     (name='Cr_MOT_AOM_no0per5_on', parent_device=DO0, connection=4)
DigitalOut     (name='Cr_TC_AOM_no0per6_on', parent_device=DO0, connection=5)
DigitalOut     (name='Cr_ZS_AOM_no0per7_on', parent_device=DO0, connection=6)
DigitalOut     (name='Cr_mf_pump_no0per8_on', parent_device=DO0, connection=7)
DigitalOut     (name='Li_ZS_current_no0per9_on', parent_device=DO0, connection=8)
DigitalOut     (name='Cr_Andor_trigger_no0per10_on', parent_device=DO0, connection=9)
DigitalOut     (name='Li_D2_no0per11_on', parent_device=DO0, connection=10)
DigitalOut     (name='Li_D1_no0per12_on', parent_device=DO0, connection=11)
DigitalOut     (name='Li_MOT_shutter_no0per13_on', parent_device=DO0, connection=12)
DigitalOut     (name='img_shutter_no0per14_on', parent_device=DO0, connection=13)
DigitalOut     (name='Blue_shutter_no0per15_on', parent_device=DO0, connection=14)
DigitalOut     (name='FB_IGBT_no0per16_on', parent_device=DO0, connection=15)
DigitalChannels(name='DO1', parent_device=board0, connection='0x1', rack=0, max_channels = 16)
DigitalOut     (name='Stingray_no1per1_on', parent_device=DO1, connection=0)
DigitalOut     (name='Li_ZS_AOM_no1per2_on', parent_device=DO1, connection=1)
DigitalOut     (name='CrRepumpers_AOMshutter_no1per3_on', parent_device=DO1, connection=2)
DigitalOut     (name='Li_oven_shutter_no1per4_on', parent_device=DO1, connection=3)
DigitalOut     (name='Li_Cooler_no1per5_on', parent_device=DO1, connection=4)
DigitalOut     (name='Cr_R1_no1per6_on', parent_device=DO1, connection=5)
DigitalOut     (name='Cr_R2_no1per7_on', parent_device=DO1, connection=6)
DigitalOut     (name='Cr_img_shutter_no1per8_on', parent_device=DO1, connection=7)
DigitalOut     (name='Li_img_AOM_no1per9_on', parent_device=DO1, connection=8)
DigitalOut     (name='Li_Rep_no1per10_on', parent_device=DO1, connection=9)
DigitalOut     (name='Current_Green_no1per11_on', parent_device=DO1, connection=10)
DigitalOut     (name='Li_img_HF_AOM_no1per12_on', parent_device=DO1, connection=11)
DigitalOut     (name='CrRepumpers_Servoshutter_no1per13_on', parent_device=DO1, connection=12)
DigitalOut     (name='Green_AOM_TTL_no1per14_on', parent_device=DO1, connection=13)
DigitalOut     (name='IR_AOM_TTL_no1per15_on', parent_device=DO1, connection=14)
DigitalOut     (name='Osci_trigger_no1per16_on', parent_device=DO1, connection=15)
DigitalChannels(name='DO2', parent_device=board0, connection='0x40', rack=0, max_channels = 16)
DigitalOut     (name='Crossed_AOM_no3per1_on', parent_device=DO2, connection=0)
DigitalOut     (name='test_no3per2_on', parent_device=DO2, connection=1)
DigitalOut     (name='test_no3per3_on', parent_device=DO2, connection=2)
DigitalOut     (name='test_no3per4_on', parent_device=DO2, connection=3)
DigitalOut     (name='test_no3per5_on', parent_device=DO2, connection=4)
DigitalOut     (name='test_no3per6_on', parent_device=DO2, connection=5)
DigitalOut     (name='test_no3per7_on', parent_device=DO2, connection=6)
DigitalOut     (name='test_no3per8_on', parent_device=DO2, connection=7)
DigitalOut     (name='test_no3per9_on', parent_device=DO2, connection=8)
DigitalOut     (name='test_no3per10_on', parent_device=DO2, connection=9)
DigitalOut     (name='test_no3per11_on', parent_device=DO2, connection=10)
DigitalOut     (name='test_no3per12_on', parent_device=DO2, connection=11)
DigitalOut     (name='test_no3per13_on', parent_device=DO2, connection=12)
DigitalOut     (name='test_no3per14_on', parent_device=DO2, connection=13)
DigitalOut     (name='test_no3per15_on', parent_device=DO2, connection=14)
DigitalOut     (name='test_no3per16_on', parent_device=DO2, connection=15)

from labscript import start, stop
if __name__ == '__main__':
    start()
    stop(1)
