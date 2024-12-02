# sample connection table for NI_DAQmx_iPCdev internal pseudoclock device
from labscript import start, stop, add_time_marker, AnalogOut, DigitalOut, StaticDigitalOut, StaticAnalogOut
from user_devices.NI_DAQmx_iPCdev.labscript_devices import NI_PXIe_6738_iPCdev, NI_PXIe_6535_iPCdev, START_TRIGGER_EDGE_RISING, START_TRIGGER_EDGE_FALLING

# general settings
# note: give clock_terminal and rate to all boards, even if they do not have internal counters.
clock_terminal          = '/PXI1Slot3/PFI4'
clock_rate              = 10e6
start_trigger_terminal  = '/PXI1Slot3/PFI0'
start_trigger_edge      = START_TRIGGER_EDGE_RISING

# create NI boards
# name                   = arbitrary name string. must be a valid python variable name.
# MAX_name               = name of board as given in NI MAX. e.g. 'PXI1Slot2'.
# parent_device          = None for the first board, the first board name for the others.
# counter_AO             = name of counter used for analog output channels. None if no AO channels.
# counter_DO             = name of counter used for digital output channels. None if no DO channels.
# max_AO_sample_rate     = maximum allowed sample rate for analog channels in Hz.
# max_DO_sample_rate     = maximum allowed sample rate for digital channels in Hz.
# clock_terminal         = external clock terminal input or None if internal clock should be used.
# clock_rate             = external clock rate in Hz. Must be given if clock_terminal is not None.
# start_trigger_terminal = external start trigger terminal or None if should start by software.
# start_trigger_edge     = 'rising'/'falling' = external start trigger edge.
# worker_args            = dictionary with optional arguments which are passed to worker.
#                          'simulate' : True/False = if True simulate hardware, otherwise hardware must be present.
NI_PXIe_6535_iPCdev(
    name                    = 'NI_board_0',
    MAX_name                = 'PXI1Slot2',
    parent_device           = None,
    counter_AO              = None,
    counter_DO              = '/PXI1Slot3/ctr1',
    max_DO_sample_rate      = 10e6,
    clock_terminal          = clock_terminal,
    clock_rate              = clock_rate,
    start_trigger_terminal  = start_trigger_terminal,
    start_trigger_edge      = start_trigger_edge,
    worker_args             = {'simulate':True},
    )
NI_PXIe_6738_iPCdev(
    name                    = 'NI_board_1',
    MAX_name                = 'PXI1Slot3',
    parent_device           = NI_board_0,
    counter_AO              = '/PXI1Slot3/ctr0',
    counter_DO              = '/PXI1Slot3/ctr1',
    num_AO                  = 8,
    max_AO_sample_rate      = 1e6,
    max_DO_sample_rate      = 10e6,
    clock_terminal          = clock_terminal,
    clock_rate              = clock_rate,
    start_trigger_terminal  = start_trigger_terminal,
    start_trigger_edge      = start_trigger_edge,
    worker_args             = {'simulate':True},
    )
NI_PXIe_6738_iPCdev(
    name                    = 'NI_board_2',
    MAX_name                = 'PXI1Slot4',
    parent_device           = NI_board_0,
    counter_AO              = '/PXI1Slot4/ctr0',
    counter_DO              = '/PXI1Slot4/ctr1',
    num_AO                  = 8,
    max_AO_sample_rate      = 1e6,
    max_DO_sample_rate      = 10e6,
    clock_terminal          = clock_terminal,
    clock_rate              = clock_rate,
    start_trigger_terminal  = start_trigger_terminal,
    start_trigger_edge      = start_trigger_edge,
    worker_args             = {'simulate':True},
    )

# create analog and digital channels
# name          = name used to identify channel. must be a valid python variable.
# parent_device = name of NI board
# connection    = physical identifier of channel in the form of 'ao%i' or 'port%i/line%i' for analog and digital channels respectively.
# further options are possible:
# inverted      = True/False if the digital channel is inverted
# unit_conversion_class/parameters = used to define units and convert to and from volts.
# limits        = to limit analog channel range.
# default_value = if not None the value set in the last command of each experiment.
#                 normally each channel maintains the last programmed value of the experiment.
#                 for critical channels a default_value can be given which is programmed automatically
#                 at the end of each experiment cycle and when the abort button is pressed.

if False:

    # this is how you would normally assign channels with individual names which you can use in your experiment script.
    # note: the hardware needs an even number of digital and analog channels 
    DigitalOut('IR_laser_on'    , NI_board_1, 'port0/line0')
    DigitalOut('green_laser_on' , NI_board_1, 'port0/line1')
    AnalogOut('offset_current_x', NI_board_1, 'ao6')
    AnalogOut('offset_current_y', NI_board_1, 'ao7')

else:

    # this if for demonstration purpose only!
    # we automatically create all possible channels and give them default names.
    ao_count = [0, 0]
    do_count = [0, 0]
    # NI_DAQmx_iPCdev supports simultaneous static and buffered channels.
    # num_static_AO = number of static analog outputs to create for testing.
    #                 I do not know if NI boards have static AO's?
    #                 but also dynamic channels can be restricted to static,
    #                 i.e. programmed before run starts and fixed during experiment.
    # use_static_DO = True/False to enable static DO ports together with buffered ones.
    num_static_AO = 3
    use_static_DO = True
    for board in [NI_board_0, NI_board_1, NI_board_2]:
        #print(board.name)
        # digital outputs. we take only buffered ones.
        for port,value in board.ports.items():
            for channel in range(value['num_lines']):
                #name = 'digital_out_%i'%do_count
                if value['supports_buffered']:
                    name = 'digital_out_%i' % do_count[0]
                    #print(name, '%s/line%i'%(port,channel))
                    DigitalOut(name, board, '%s/line%i'%(port,channel))
                    do_count[0] += 1
                elif use_static_DO:
                    # TODO: one cannot have dynamic and static I/Os at the same time. we skip this.
                    #       but I think this is not a fundamental limit and can be fixed in NI_DAQmx device.
                    name = 'static_digital_out_%i' % do_count[1]
                    #print(name, '%s/line%i (static skipped)'%(port,channel))
                    StaticDigitalOut(name, board, '%s/line%i'%(port,channel))
                    do_count[1] += 1
        # analog outputs
        # if 8 channels are used we use only every 4th channel. this allows to go to 1MHz instead of 300kHz.
        mult = 4 if board.num_AO == 8 else 1
        for channel in range(board.num_AO):
            if ao_count[1] < num_static_AO:
                name = 'static_analog_out_%i' % ao_count[1]
                StaticAnalogOut(name=name, parent_device=board, connection='ao%i' % (channel * mult))
                ao_count[1] += 1
            else:
                name = 'analog_out_%i' % ao_count[0]
                AnalogOut(name=name, parent_device=board, connection='ao%i'%(channel*mult))
                ao_count[0] += 1
    print('%3i buffered analog  outputs'%(ao_count[0]))
    print('%3i static   analog  outputs'%(ao_count[1]))
    print('%3i buffered digital outputs'%(do_count[0]))
    print('%3i static   digital outputs'%(do_count[1]))

# the connection table must contain a dummy experimental sequence. leave it empty.
if __name__ == '__main__':
    start()
    stop(1.0)
