from labscript import start, stop, add_time_marker, AnalogOut, StaticAnalogOut, DigitalOut, StaticDigitalOut, DDS, StaticDDS
from user_devices.iPCdev.labscript_devices import iPCdev
from user_devices.generic_conversion import generic_conversion

# options
simulate    = True       # simulate device. not needed but with some hardware missing needed.
sync_boards = True       # synchronize boards. not needed but some hardware might need.

boards = []
iPCdev(
    name                    = 'device_0',
    worker_args             = {'simulate': simulate, 'sync_boards': sync_boards},
    )
boards.append(device_0)

if True:
    iPCdev(
        name                    = 'device_1',
        parent_device           = device_0,
        worker_args             = {'simulate': simulate, 'sync_boards': sync_boards},
        )
    boards.append(device_1)

if True:
    iPCdev(
        name                    = 'device_2',
        parent_device           = device_0,
        worker_args             = {'simulate': simulate, 'sync_boards': sync_boards},
        )
    boards.append(device_2)

# create analog and digital channels
# give user-friendly names. but must be valid python variable names.
# for connection give: "address/channel" for digital channels and "address" for analog channels,
#                      address and channel can be decimal or hex with 0x prefix
#                      digital channels can share same address.
#                      analogue channels must use unique address.
#                      for each unique address a separate clockline is created.

# counts buffered and static devices
do_count  = [0,0]
ao_count  = [0,0]
dds_count = [0,0]

# go though all boards
for parent in boards:
    addr = 0

    # digital outputs
    for channel in range(16):
        DigitalOut(name = 'digital_out_%i'%do_count[0], parent_device = parent, connection = '0x%x/0x%x'%(addr, channel))
        do_count[0] += 1
    addr += 1

    for channel in range(16):
        DigitalOut(name = 'digital_out_%i'%do_count[0], parent_device = parent, connection = '0x%x/0x%x'%(addr, channel))
        do_count[0] += 1
    addr += 1

    # static digital output
    for channel in range(4):
        StaticDigitalOut(name = 'static_digital_out_%i'%do_count[1], parent_device = parent, connection = '0x%x/0x%x'%(addr, channel))
        do_count[1] += 1
    addr += 1

    # analog outputs
    for channel in range(8):
        AnalogOut (name = 'analog_out_%i'%ao_count[0], parent_device = parent, connection = '0x%x'%(addr))
        ao_count[0] += 1
        addr += 1

    # analog out with unit conversion
    AnalogOut (name = 'analog_out_%i'%ao_count[0], parent_device = parent, connection = '0x%x'%(addr),
               unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit': 'A', 'equation': 'x/10.0', 'min': -0.01, 'max': 100.0}
               )
    ao_count[0] += 1
    addr += 1

    # static analog output
    StaticAnalogOut(name='static_analog_out_%i' % ao_count[1], parent_device=parent, connection='0x%x' % (addr))
    ao_count[1] += 1
    addr += 1

    # static analog out with unit conversion
    StaticAnalogOut(name = 'static_analog_out_%i'%ao_count[1], parent_device = parent, connection = '0x%x'%(addr),
               unit_conversion_class=generic_conversion,
               unit_conversion_parameters={'unit': 'A', 'equation': 'x/10.0', 'min': -0.01, 'max': 100.0}
               )
    ao_count[1] += 1
    addr += 1

    # DDS. TODO: get an error about unit conversion
    for channel in range(2):
        DDS(name = 'dds_%i'%dds_count[0], parent_device = parent, connection = '0x%x'%(addr),
            #freq_conv_class=generic_conversion,
            #freq_conv_params={'unit': 'MHz', 'equation': 'x', 'min': 0.0, 'max': 1000.0}
            )
        dds_count[0] += 1
        addr += 1

    # static DDS.
    for channel in range(2):
        StaticDDS(name = 'dds_static_%i'%dds_count[1], parent_device = parent, connection = '0x%x'%(addr),
            #freq_conv_class=generic_conversion,
            #freq_conv_params={'unit': 'MHz', 'equation': 'x', 'min': 0.0, 'max': 1000.0}
            )
        dds_count[1] += 1
        addr += 1

# the connection table must contain a dummy experimental sequence. leave it empty.
if __name__ == '__main__':
    start()
    stop(1.0)
    
