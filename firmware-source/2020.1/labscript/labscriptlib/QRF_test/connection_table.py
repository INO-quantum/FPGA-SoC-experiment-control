#!/usr/bin/python

# connection_table example for QRF module.
# this allows to test QRF module in different experiment environments with FPGA boards, generic iPCdev devices or stand-alone.
# FPGA board and iPCdev allow to add digital channels which QRF needs to trigger and to enable/disable channels.
# FPGA board is a specific hardware we use but can be simulated here,
# iPCdev is a generic virtual device which allows to easily integrate analog, digital and DDS channels.
# the QRF implementation uses a derived class of iPCdev for the specific QRF hardware.
# in e realistic experiment one would have only the FPGA board(s) or other primary devices and QRF without iPCdev.

########################################################################################################################
# imports

from labscript import start, stop, AnalogOut, DigitalOut, DDS, LabscriptError
from user_devices.Moglabs_QRF.labscript_devices import (
    QRF, QRF_DDS, MAX_NUM_CHANNELS,
    MODES_WITH_CHANNEL_TRIGGER, MODES_WITH_GLOBAL_TRIGGER, MODES_WITH_CHANNEL_ENABLE, MODES_WITH_GATE
)

########################################################################################################################
# configuration
primary = ['FPGA','iPCdev','QRF'][0]    # choose one of the options which board should be primary device
                                        # if 'QRF' is chosen neither FPGA_board nor iPCdev is generated and
                                        # all channels can use only these modes since no digital channels are available:
                                        # - mode = 'table timed' with an external start trigger on channel 1 trigger input
                                        # - mode = 'table timed software' which is ok for testing but several QRF are not synchronized.
num_FPGA   = 2                          # number of FPGA boards to be used
if primary == 'FPGA': num_FPGA = max(num_FPGA, 1)           # at least one is used in this case
else:                 num_FPGA = 0                          # no FPGA boards in other cases
num_IPCdev = 2                          # number of iPCdev to be used.
if   primary == 'iPCdev': num_IPCdev = max(num_IPCdev, 1)   # at least 1 is used in this case
elif primary == 'QRF'   : num_IPCdev = 0                    # standalone QRF with no iPCdev
QRF_address = [None,None]               # IP address or USB port of each QRF module. use None if QRF should be simulated.
num_QRF = len(QRF_address)              # number or QRF devices

# use hardware device as trigger (True) or virtual device (False)
if   primary == 'FPGA'  : hardware_trigger = True            # must be always True since FPGA board has no virtual trigger.
elif primary == 'iPCdev': hardware_trigger = [True,False][1] # choose an option
elif primary == 'QRF'   : hardware_trigger = False           # must be always False since QRF board has no digital channels.

# modes alternated by channel for demonstration
# available modes:
# 'NSB' or 'basic'               = static programming of freq/amp/phase or from front panel values if nothing in script.
#                                  RF on/off via digital gate. do not specify trigger_delay and trigger_duration.
#                                  in experiment script use enable/disable commands.
# 'NSA' or 'advanced'            = direct programming of DDS registers.
#                                  not implemented!
# 'TSB' or 'table timed'         = table mode, timed by microcontroller of QRF.
#                                  resolution 5us + clock drift if not locked to external clock.
#                                  started by external trigger attached to channel 1 trigger input
#                                  given to QRF() as DO_trg with trigger_connection = channel or DO_trg.
#                                  ATTENTION: this is a different channel than given to digital_gate of QRF_DDS!
#                                             in this case channel 1 trigger input cannot be used for channel 1,
#                                             but triggers the entire QRF device!
#                                             so use channel 1 in this mode if any channel has to be in this mode.
# 'TSB sw' or 'table timed software' = same as 'TSB' or 'table timed' but started by software trigger.
#                                  in this mode several QRF's are not synchronized!
# 'TSB_trg' or 'table triggered' = table mode, timed by external trigger given as digital_gate to QRF_DDS.
#                                  resolution 5us with relative big jitter.
if primary == 'QRF':
    modes = ['table timed','table timed software']
    DO_trg = qrf = None
else:
    modes = ['table timed', 'table timed software', 'table triggered', 'basic']

# generate list of trigger_connection for each secondary device
# and gate trigger channels for each QRF channel we need
# this gives the number of required trigger channels
trigger_connection = [] # trigger_connection for each QRF device
gate               = [] # gate for each channel of QRF device
count_trg = 0
for i in range(num_FPGA + num_IPCdev + num_QRF):
    if i == 0:
        # skip primary device whatever it is
        trigger_connection.append(None)
    elif (primary == 'FPGA' and (i < num_FPGA)) or (primary != 'FPGA' and (i <= num_FPGA)):
        # skip secondary FPGA boards since they do not need a trigger channel
        trigger_connection.append(None)
    else:
        # trigger for each secondary device
        if hardware_trigger:  # hardware trigger
            trigger_connection.append(('%i' % count_trg) if primary == 'FPGA' else ('0x0/0x%x' % count_trg))
            count_trg += 1
        else:  # virtual trigger
            trigger_connection.append(None)
    if i >= num_FPGA + num_IPCdev:
        # trigger connection for each QRF channel
        for j in range(MAX_NUM_CHANNELS):
            mode = modes[j % len(modes)]
            if mode in MODES_WITH_GATE:
                # gate required. the connection must be given differently for different primary devices
                gate.append(('%i'%count_trg) if primary=='FPGA' else ('0x0/0x%x'%count_trg))
                count_trg += 1
            else:
                # no gate used, possibly start trigger instead
                gate.append(None)
num_trg = count_trg
tmp = [len([c for c in trigger_connection if c is not None]), len([g for g in gate if g is not None])]
if hardware_trigger: # primary is either 'FPGA' or 'iPCdev'
    expected = num_IPCdev + num_QRF if primary == 'FPGA' else num_IPCdev + num_QRF - 1
else: # primary is either 'iPCdev' or 'QRF'. virtual trigger is used.
    expected = 0
if expected != tmp[0]:
    raise LabscriptError("number of device trigger channels %i expected but got %i" % (expected, tmp[0]))
if tmp[0] + tmp[1] != num_trg:
    raise LabscriptError("number of total trigger channels %i expected but got %i" % (tmp[0] + tmp[1], num_trg))
print('\ncreating %i FPGA boards, %i iPCdev boards, %i QRF modules, primary = %s' % (num_FPGA, num_IPCdev, num_QRF, primary))
print('required trigger channels: %i (%i secondary boards, %i gates), hardware_trigger = %s\n' % (num_trg, tmp[0], tmp[1], str(hardware_trigger)))

########################################################################################################################
# FPGA board
# provides trigger channels (has no DDS)
if num_FPGA > 0:
    from user_devices.FPGA_device import FPGA_board, DigitalChannels, AnalogChannels

    def create_FPGA(board_id, parent_device, num_trg, count_do, count_ao, simulate):
        # create board
        if parent_device is None:
            board = FPGA_board(name='FPGA_%i'%board_id, ip_address='192.168.1.10', bus_rate=1.0e6,
                               worker_args={'inputs': {'start trigger': ('input 0', 'low level')},
                                            'outputs': {'output 0': ('sync out', 'low level')},
                                            'simulate': simulate  # simulate device. set to False if you have real device.
                                           },
                              )

            # we need some trigger channels
            # additional digital out channels are free to use in the experiment and can be initialized here
            DO_trg = DigitalChannels(name='DO_trg', parent_device=board, connection='0x00', rack=0, max_channels=16)
            for i in range(num_trg, 16):
                DigitalOut(name='digital_out_%i' % count_do, parent_device=DO_trg, connection=i)
                count_do += 1
        else:
            board = FPGA_board(name='FPGA_%i'%board_id, ip_address='192.168.1.11', bus_rate=1.0,
                               trigger_device = parent_device,
                               worker_args={'inputs': {'start trigger': ('input 0', 'low level')},
                                            'simulate': simulate # simulate device. set to False if you have real device.
                                           },
                              )
            DO_trg = None

            # additional digital out channels
            do_im = DigitalChannels(name='DO_%i'%board_id, parent_device=board, connection='0x0', rack=0, max_channels=16)
            for i in range(16):
                DigitalOut(name='digital_out_%i' % count_do, parent_device=do_im, connection=i)
                count_do += 1

        # additional analog out channels
        ao_im = AnalogChannels(name='AO_%i'%board_id, parent_device=board, rack=0, max_channels=2)
        for i in range(2):
            AnalogOut(name='analog_out_%i'%count_ao, parent_device=ao_im, connection='0x%x'%(i+1))
            count_ao += 1

        return board, DO_trg, count_do, count_ao

########################################################################################################################
# iPCdev
# provides trigger channels and classic DDS. needs digital outputs to trigger.
# if all boards are iPCdev we can set sync_boards = True, otherwise not.

if num_IPCdev > 0:
    from user_devices.iPCdev.labscript_devices import iPCdev

    def create_iPCdev(board_id, parent_device, num_trg, count_do, count_ao, count_dds, trigger_connection):
        # create board
        if parent_device is None:
            board = iPCdev(name                 = 'iPCdev_%i'%board_id,
                           parent_device        = None,
                           trigger_connection   = None,
                           worker_args          = {'sync_boards': primary != 'FPGA'},
                          )
            # for triggering we need some digital channels
            # additional digital out channels are free to use in the experiment and can be initialized here
            for j in range(num_trg, 16):
                do = DigitalOut(name='digital_out_%i' % count_do, parent_device=board, connection='0x0/0x%x' % (j))
                count_do += 1
            # we need the intermediate device for the trigger channels which is the parent of any digital out channel here
            DO_trg = do.parent_device
        else:
            board = iPCdev(name                 = 'iPCdev_%i'%board_id,
                           parent_device        = parent_device,
                           trigger_connection   = trigger_connection,
                           worker_args          = {'sync_boards': primary != 'FPGA'},
                          )
            DO_trg = None

            # additional digital out channels
            for i in range(16):
                DigitalOut(name='digital_out_%i' % count_do, parent_device=board, connection='0x0/0x%x' % (i))
                count_do += 1

        # additional analog out channels
        for i in range(2):
            AnalogOut(name='analog_out_%i'%count_ao, parent_device=board, connection='0x1/0x%x'%(i))
            count_ao += 1

        # aadditional classic DDS
        for i in range(2):
            DDS(name='classic_DDS_%i'%count_dds, parent_device=board, connection='0x2/0x%i'%i)
            count_dds += 1

        return board, DO_trg, count_do, count_ao, count_dds

########################################################################################################################
# QRF DDS

def create_QRF(board_id, parent_device, num_trg, count_qrf, trigger_connection, gates):

    board = QRF(name                  = 'QRF_%i' % board_id,
                parent_device         = parent_device,                # intermediate device or iPCdev or None
                addr                  = None,                         # IP address, or None for simulation
                trigger_connection    = trigger_connection,           # channel of intermediate device
                worker_args = {'sync_boards': primary != 'FPGA'},     # synchronize boards when possible.
                                                                      # this is for demonstration but not really needed.
               )
    # create channels
    for j in range(MAX_NUM_CHANNELS):
        mode = modes[j % len(modes)]
        if mode in MODES_WITH_CHANNEL_TRIGGER: # trigger_delay/duration required
            trigger_delay = 5e-6
            trigger_duration = 5e-6
        else:
            trigger_delay = None
            trigger_duration = None
        QRF_DDS(name                = 'test_DDS_%i' % count_qrf,
                parent_device       = board,
                connection          = 'channel %i' % (j+1), # must be in the form 'channel %i' with i=1..4
                mode                = mode,
                digital_gate        = None if gates is None else gates[j],
                trigger_delay       = trigger_delay,
                trigger_duration    = trigger_duration,
                )
        count_qrf += 1

    return board, count_qrf

########################################################################################################################
# generate boards and channels

# generate primary board
count_boards = 0
count_do     = 0
count_ao     = 0
count_dds    = 0
count_qrf    = 0
if primary == 'FPGA':
    prim, DO_trg, count_do, count_ao = create_FPGA(count_boards, None, num_trg, count_do, count_ao, simulate=True)
elif primary == 'iPCdev':
    prim, DO_trg, count_do, count_ao, count_dds = create_iPCdev(count_boards, None, num_trg, count_do, count_ao, count_dds, None)
elif primary == 'QRF':
    prim, count_qrf = create_QRF(count_boards, None, num_trg, count_qrf, None, None)
count_boards += 1

# generate secondary FPGA boards
# parent device is primary board
for i in range(num_FPGA):
    if i == 0 and primary == 'FPGA': continue
    _, _, count_do, count_ao = create_FPGA(i, prim, 0, count_do, count_ao, simulate=True)
    count_boards += 1

# generate secondary iPCdev boards
# parent device is either an iPCdev with virtual trigger connection or intermediate device with hardware trigger
for i in range(num_IPCdev):
    if i == 0 and primary == 'iPCdev': continue
    if hardware_trigger:
        parent_device       = DO_trg
        _trigger_connection = trigger_connection[count_boards]
    else:
        parent_device       = prim
        _trigger_connection = None
    _, _, count_do, count_ao, count_dds = create_iPCdev(i, parent_device, 0, count_do, count_ao, count_dds, _trigger_connection)
    count_boards += 1

# generate secondary QRF boards
# parent device is either an iPCdev with virtual trigger connection or intermediate device with hardware trigger
for i in range(num_QRF):
    if i == 0 and primary == 'QRF': continue
    if hardware_trigger:
        parent_device       = DO_trg
        _trigger_connection = trigger_connection[count_boards]
    else:
        parent_device       = prim
        _trigger_connection = None
    gates = [None if g is None else {'device': DO_trg if primary == 'FPGA' else prim, 'connection': g} for g in gate[i*MAX_NUM_CHANNELS:(i+1)*MAX_NUM_CHANNELS]]
    _, count_qrf = create_QRF(i, parent_device, 0, count_qrf, _trigger_connection, gates)
    count_boards += 1

########################################################################################################################
# experimental sequence

if __name__ == '__main__':

    # start sequence
    start()

    # stop sequence
    stop(1.0)


