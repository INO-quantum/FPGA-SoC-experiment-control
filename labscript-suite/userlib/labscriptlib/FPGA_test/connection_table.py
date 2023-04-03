#!/usr/bin/python

# 2022/03/02, 23:49:28
# automatically generated labscript connection table from 'LiCr_1400G_200nK_FBcool.prg'
# command line: 'LVparser.py -p ./20220216_labview_prg -f LiCr_1400G_200nK_FBcool.prg -a ListOfActionAnalog.txt -d ListOfActionTTL.txt -l {'IR laser #3 (W)':[7.1,200.0],'Crossed Green #19 (W)':[0.1,100.0]}'

########################################################################################################################
# instructions

# copy this file connection_table.py and LiCr_1400G_200nK_FBcool.py into folder ~/labscript-suite/userlib/labscriptlib/<experiment>/.
# cd into labscript bin folder: cd /opt/pycharm-community-2021.1/bin (adapt to your version of pycharm)
# launch labscript: ./pycharm.sh
# in pycharm start BLACS and runmanager via run command on top right or/and terminal command

########################################################################################################################
# imports

import numpy as np
from labscript import start, stop, add_time_marker, AnalogOut, DigitalOut, DDS
from user_devices.FPGA_device import FPGA_board, DigitalChannels, AnalogChannels, PRIMARY_IP, SECONDARY_IP, DEFAULT_PORT
from user_devices.generic_conversion import generic_conversion

########################################################################################################################
# FPGA boards

if True:
    # primary board:
    # note: importing 'primary' from connection_table does not work with 'FPGA_device(name='primary',...)' but requres to assign primary!
    primary = FPGA_board(name='primary', ip_address="192.168.1.121", ip_port=DEFAULT_PORT, bus_rate=1e6, num_racks=1,
        worker_args={ # optional arguments. can be changed in GUI. if defined here used at startup, otherwise last settings in GUI are used.
            'inputs':{  'NOP bit' : ('data bits 28-31','offset bit 3'), 'STRB bit' : ('data bits 20-23','offset bit 3')},
            'outputs': {'output 0': ('sync out', 'low level')}, # required: start trigger for sec. board (default, keep here). other outputs can be added.
            #'ext_clock':False,  # True = use external clock
            #'ignore_clock_loss':True # True = ignore when external clock is lost. Message Box is displayed but board keeps running.
            #'trigger':{}, # no trigger (default)
            #'trigger':{'start trigger':('input 0', 'rising edge')}, # start trigger
            #'trigger':{'start trigger':('input 0', 'rising edge'),'stop trigger':('input 1', 'falling edge'),'restart trigger':('input 0', 'rising edge')}, # start+stop+restart trigger
        })

# secondary board: (enable with True)
if True:
    secondary = FPGA_board(name='secondary', ip_address="192.168.1.121", ip_port=DEFAULT_PORT, bus_rate=1e6, num_racks=1, trigger_device=primary,
        worker_args={ # optional arguments. can be changed in GUI. if defined here used at startup, otherwise last settings in GUI are used.
            'inputs':{'start trigger':('input 0', 'falling edge'),
                      'NOP bit':('data bits 20-23','offset bit 0'),
                      'STRB bit' : ('data bits 20-23','offset bit 3')}, # required: start trigger from primary board (default, keep here)
            'ext_clock': True,  # True = required: use external clock from primary board (default, keep here)
            #'ignore_clock_loss': True # True = ignore when external clock is lost. Message Box is displayed but board keeps running.
            # 'trigger':{'start trigger':('input 0', 'falling edge'),'stop trigger':('input 1', 'falling edge'),'restart trigger':('input 1', 'rising edge')}, # start+stop+restart trigger. must be input 1 or 2
            #'outputs':{'output 0': ('sync out', 'low level'),'output 0': ('lock lost', 'high level')}, example outputs can be added when needed.
        })

# second independent primary board for 50Hz compensation: (enable with True)
# trigger device must be given for all other boards than primary, is_primary forces config as primary board.
if False:
    from user_devices.FPGA_device import CONFIG_RUN_64, CTRL_RESTART_EN

    board_comp = FPGA_board(name='board_comp', ip_address="192.168.1.121", ip_port=DEFAULT_PORT, bus_rate=1e6, num_racks=1,
        trigger_device=primary,
        #clockline="board_comp_clockline",
        worker_args={
            'inputs':{  #'start trigger'  : ('input 0', 'rising edge'),
                        #'stop trigger'   : ('data bits 28-31','offset bit 2'),
                        #'restart trigger': ('input 1','rising edge'),
                        'NOP bit'        : ('data bits 28-31','offset bit 3'),
                        'STRB bit'       : ('data bits 20-23','offset bit 3')},
            'ext_clock': False,
            # configuration bits in manual and running mode.
            # the easiest is to import the default config CONFIG_RUN_64 and add additional config.
            'config_manual': CONFIG_RUN_64,
            'config': CONFIG_RUN_64|CTRL_RESTART_EN, # restart is needed for cycling mode
            # set wait time and sync_phase to 0. if not given uses values from server.config file on SD card.
            'sync_wait': 0x0, 'sync_phase': 0x0,
            # cycling mode number of cycles: 0=infinite, 1=default. better give in experiment script.
            #'num_cycles': 1
        })
    #primary = board_comp

    # 50Hz compensation
    AnalogChannels(name='AO_comp', parent_device=board_comp, rack=0, max_channels=2)
    AnalogOut     (name='compensation', parent_device=AO_comp, connection='0x14')

    # TTL output for testing
    DigitalChannels(name='DO_comp', parent_device=board_comp, connection='0x01', rack=0, max_channels=16)
    for i in range(16):
        DigitalOut(name='comp_TTL_%i'%(i), parent_device=DO_comp, connection=i)

# for testing define some devices with alternative board, which is secondary when exists, otherwise board0
try:
    board_alt = secondary
except NameError:
    board_alt = primary

########################################################################################################################
if True:
    # MOGLABS Quad RF synthesizer. give primary board as parent_device
    from user_devices.MOGLabs_QRF import MOGLabs_QRF, QRF_DDS

    # we need one or several DigitalChannels intermediate device(s) for triggering given to QRF_DDS digital_gate as 'device' keyword.
    # note: do not create the channel(s) here since QRF_DDS creates each channel automatically with the 'connection' keyword as channel number.
    # this ensures the user does not set the channel by mistake.
    # parent must be the same board as for QRF.
    # the enable/disable commands are working. maybe this can be employed for triggering of individual channels?
    DigitalChannels(name='DO_QRF', parent_device=primary, connection='0x27', rack=0, max_channels=16)

    # define temporarily for testing another intependent digital channel for Trigger of QRF. 
    # this should give a single trigger command for a single channel or for all channels I do not know, 
    # but so far even if I call QRF_0.trigger does not do anything?
    DigitalChannels(name='DO_QRF_1', parent_device=primary, connection='0x28', rack=0, max_channels=16, clockline=('QRF',True))
    DigitalOut(name='QRF_trigger_0', parent_device=DO_QRF_1, connection=15)

    # parent must be primary or secondary board. address and port is passed to MOGDevice.__init__
    MOGLabs_QRF(name='QRF_0', parent_device=QRF_trigger_0, addr='192.168.1.190', port=7802)

    # note: connection must be given as 'channel %i' i=0-3, and there must be 4 channels.
    # give digital_gate with 'device' = DigitalChannels with a free channel number given as 'connection'. do not create any channels manually.
    # these channels are used with the test_DDS_#.enable/disable commands and this works.
    # TODO: if user does not provide the correct channel name or fewer channels then get an error when starting BLACS. this should be gixed.
    #       also the channel names are not displayed in BLACS (I had to fix this also for the FPGA boards, look there how to do it)
    QRF_DDS(name='test_DDS_0', parent_device=QRF_0, connection='channel 0', table_mode=False, digital_gate={'device':DO_QRF, 'connection': 0})
    QRF_DDS(name='test_DDS_1', parent_device=QRF_0, connection='channel 1', table_mode=True, trigger_each_step=False, digital_gate={'device':DO_QRF, 'connection': 1})
    QRF_DDS(name='test_DDS_2', parent_device=QRF_0, connection='channel 2', table_mode=True, trigger_each_step=True, digital_gate={'device':DO_QRF, 'connection': 2})
    QRF_DDS(name='test_DDS_3', parent_device=QRF_0, connection='channel 3', table_mode=True, trigger_each_step=True, digital_gate={'device':DO_QRF, 'connection': 3})

########################################################################################################################
# analog outputs

AnalogChannels(name='AO0', parent_device=primary, rack=0, max_channels=2)
AnalogOut     (name='IR_AOM_no2_percent', parent_device=AO0, connection='0x2', unit_conversion_class=generic_conversion, 
               unit_conversion_parameters={'unit':'percent', 'equation':'(-0.02063+3.62077*np.tan(0.01724-0.19288*np.sqrt(x/100)+1.39915*x/100))', 'min':0.0, 'max':100.0})
AnalogOut     (name='IR_laser_no3_W', parent_device=AO0, connection='0x3', unit_conversion_class=generic_conversion, 
               unit_conversion_parameters={'unit':'W', 'equation':'np.sign(x-7.0)*(1.04532+np.sqrt(abs(-0.04508+(0.04255*x-0.07844)**2)))', 'min':7.1, 'max':200.0})

AnalogChannels(name='AO1', parent_device=primary, rack=0, max_channels=2)
AnalogOut     (name='Cr_AOM_MOT_60to127MHz_no4_MHz', parent_device=AO1, connection='0x4', unit_conversion_class=generic_conversion, 
               unit_conversion_parameters={'unit':'MHz', 'equation':'(x-65.5)/17.1', 'min':0.0, 'max':236.50000000000003})
AnalogOut     (name='Cr_AOM_TC_70to115MHz_no5_MHz', parent_device=AO1, connection='0x5', unit_conversion_class=generic_conversion, 
               unit_conversion_parameters={'unit':'MHz', 'equation':'(x-64.8)/8.65', 'min':0.0, 'max':151.3})

AnalogChannels(name='AO2', parent_device=primary, rack=0, max_channels=2)
AnalogOut     (name='Green_AOM_no6_W', parent_device=AO2, connection='0x6', unit_conversion_class=generic_conversion, 
               unit_conversion_parameters={'unit':'W', 'equation':'(0.396102*x**0.958663-0.0333004)', 'min':0.0, 'max':29.117949927869077})
AnalogOut     (name='Li_cool_int_no7_percent', parent_device=AO2, connection='0x7', unit_conversion_class=generic_conversion, 
               unit_conversion_parameters={'unit':'percent', 'equation':'(0.72168*np.tan(0.011379*((x+7.1646)))-3.2231-np.exp(-0.35968*x)*0.28516)', 'min':0.0, 'max':100.0})

AnalogChannels(name='AO3', parent_device=primary, rack=0, max_channels=2)
AnalogOut     (name='MOT_current_0to100A_no8_A', parent_device=AO3, connection='0x78', unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit':'A', 'equation':'(x-0.39562)/246.3221*10.000000', 'min':-245.92648000000003, 'max':246.71772})
AnalogOut     (name='dont_use_no9_V', parent_device=AO3, connection='0x79')

AnalogChannels(name='AO4', parent_device=primary, rack=0, max_channels=2)
AnalogOut     (name='Li_cooling_no10_MHz', parent_device=AO4, connection='0xa', unit_conversion_class=generic_conversion, 
               unit_conversion_parameters={'unit':'MHz', 'equation':'(x-80.237)/15.224', 'min':0.0, 'max':232.477})
AnalogOut     (name='Li_repumper_no11_MHz', parent_device=AO4, connection='0xb', unit_conversion_class=generic_conversion, 
               unit_conversion_parameters={'unit':'MHz', 'equation':'(x-129.395)/33.752', 'min':0.0, 'max':466.9150000000001})

AnalogChannels(name='AO5', parent_device=primary, rack=0, max_channels=2)
AnalogOut     (name='Li_ZS_AOM_74to140MHz_no12_MHz', parent_device=AO5, connection='0xc', unit_conversion_class=generic_conversion, 
               unit_conversion_parameters={'unit':'MHz', 'equation':'(x-70.52)/86.7*10.000000', 'min':0.0, 'max':157.22})
AnalogOut     (name='Li_rep_int_no13_percent', parent_device=AO5, connection='0xd', unit_conversion_class=generic_conversion, 
               unit_conversion_parameters={'unit':'percent', 'equation':'-2.314*np.log(1-x*0.986/100)', 'min':0.0, 'max':100.0})

AnalogChannels(name='AO6', parent_device=primary, rack=0, max_channels=2)
AnalogOut     (name='FB_current_0to200A_no14_A', parent_device=AO6, connection='0xe', unit_conversion_class=generic_conversion, 
               unit_conversion_parameters={'unit':'A', 'equation':'x*5/200', 'min':-400.0, 'max':400.0})
AnalogOut     (name='dont_use_no15_V', parent_device=AO6, connection='0xf')

AnalogChannels(name='AO7', parent_device=primary, rack=0, max_channels=2)
AnalogOut     (name='Cr_AOM_MOT_int_no16_percent', parent_device=AO7, connection='0x10', unit_conversion_class=generic_conversion, 
               unit_conversion_parameters={'unit':'percent', 'equation':'(-7.98923+0.26451*np.sqrt(x)+2.0896E-6*x**3-2.00775E-4*x**2)', 'min':0.0, 'max':100.0})
AnalogOut     (name='Cr_AOM_R1_int_no17_percent', parent_device=AO7, connection='0x11', unit_conversion_class=generic_conversion, 
               unit_conversion_parameters={'unit':'percent', 'equation':'(-1.97067*np.log((105.585441-x)/110.718))', 'min':0.0, 'max':100.0})

AnalogChannels(name='AO8', parent_device=primary, rack=0, max_channels=2)
AnalogOut     (name='Crossed_AOM_no18_percent', parent_device=AO8, connection='0x12', unit_conversion_class=generic_conversion, 
               unit_conversion_parameters={'unit':'percent', 'equation':'(2.27475+0.68981*np.tan(1.36604-1.0119*np.sqrt(x/100)+1.18276*x/100-2.80819*(x/100)**3))', 'min':0.0, 'max':100.0})
AnalogOut     (name='Crossed_Green_no19_W', parent_device=AO8, connection='0x13', unit_conversion_class=generic_conversion, 
               unit_conversion_parameters={'unit':'W', 'equation':'(2.36907+1.02646*np.tan(-1.10156+0.28301*np.sqrt(x)-0.00296*x))', 'min':0.1, 'max':100.0})

AnalogChannels(name='AO9', parent_device=primary, rack=0, max_channels=2)
AnalogOut     (name='CompCoil_z_no20_A', parent_device=AO9, connection='0x74', unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit':'A', 'equation':'x', 'min':-10.0, 'max':10.0})
AnalogOut     (name='Li_img_HF_145to238_no21_MHz', parent_device=AO9, connection='0x75', unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit':'MHz', 'equation':'(x-142.31036)/31.31786', 'min':0.0, 'max':455.48896})

AnalogChannels(name='AO10', parent_device=primary, rack=0, max_channels=2)
AnalogOut     (name='Analog_no22_V', parent_device=AO10, connection='0x16')
AnalogOut     (name='Li_AOM_abs_img_70to110MHz_no23_MHz', parent_device=AO10, connection='0x17', unit_conversion_class=generic_conversion, 
               unit_conversion_parameters={'unit':'MHz', 'equation':'(x-85.150)/16.629', 'min':0.0, 'max':251.44000000000003})

AnalogChannels(name='AO11', parent_device=primary, rack=0, max_channels=2)
AnalogOut     (name='Analog_no24_V', parent_device=AO11, connection='0x18')
AnalogOut     (name='Analog_no25_V', parent_device=AO11, connection='0x19')

AnalogChannels(name='AO12', parent_device=primary, rack=0, max_channels=2)
AnalogOut     (name='Cr_AOM_spectr_60to137MHz_no26_MHz', parent_device=AO12, connection='0x1a', unit_conversion_class=generic_conversion, 
               unit_conversion_parameters={'unit':'MHz', 'equation':'(x-90.608)/16.647', 'min':0.0, 'max':257.078})
AnalogOut     (name='Cr_AOM_ZS_48to94MHz_no27_MHz', parent_device=AO12, connection='0x1b', unit_conversion_class=generic_conversion, 
               unit_conversion_parameters={'unit':'MHz', 'equation':'(x-80.30)/10.85', 'min':0.0, 'max':188.8})

AnalogChannels(name='AO14', parent_device=primary, rack=0, max_channels=2)
AnalogOut     (name='Analog_no30_V', parent_device=AO14, connection='0x1e')
AnalogOut     (name='Analog_no31_V', parent_device=AO14, connection='0x1f', unit_conversion_class=generic_conversion, 
               unit_conversion_parameters={'unit':'V', 'equation':'(x-0.01348)/195.1084*10.000000', 'min':-195.09492, 'max':195.12187999999998})

AnalogChannels(name='AO15', parent_device=primary, rack=0, max_channels=2)
AnalogOut     (name='DDS_no32_index', parent_device=AO15, connection='0x20', unit_conversion_class=generic_conversion, 
               unit_conversion_parameters={'unit':'index', 'equation':'x/3276.700000', 'min':0.0, 'max':1024})

########################################################################################################################
# digital outputs

DigitalChannels(name='DO0', parent_device=primary, connection='0x0', rack=0, max_channels=16,clockline=("fast",True))
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

DigitalChannels(name='DO1', parent_device=primary, connection='0x71', rack=0, max_channels=16)
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
DigitalOut     (name='Current_Green_no1per11_off', parent_device=DO1, connection=10)
DigitalOut     (name='Li_img_HF_AOM_no1per12_on', parent_device=DO1, connection=11)
DigitalOut     (name='CrRepumpers_Servoshutter_no1per13_on', parent_device=DO1, connection=12)
DigitalOut     (name='Green_AOM_TTL_no1per14_on', parent_device=DO1, connection=13)
DigitalOut     (name='IR_AOM_TTL_no1per15_on', parent_device=DO1, connection=14)
DigitalOut     (name='Osci_trigger_no1per16_on', parent_device=DO1, connection=15)

DigitalChannels(name='DO2', parent_device=primary, connection='0x40', rack=0, max_channels=16)
DigitalOut     (name='Osci_trigger', parent_device=DO2, connection=12)
DigitalOut     (name='Stop_trigger', parent_device=DO2, connection=14)


########################################################################################################################
# experimental sequence

if __name__ == '__main__':

    t = primary.start_time #note: t is not used here
    dt = primary.time_step

    # start sequence
    start()

    # stop sequence
    stop(1.0 + dt)


