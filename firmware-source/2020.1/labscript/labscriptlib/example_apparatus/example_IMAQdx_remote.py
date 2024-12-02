from labscript import start, stop, add_time_marker, Trigger, RemoteBLACS
from labscript_devices.DummyPseudoclock.labscript_devices import DummyPseudoclock
from labscript_devices.DummyIntermediateDevice import DummyIntermediateDevice
from labscript_devices.IMAQdxCamera.labscript_devices import IMAQdxCamera

# Use a virtual ('dummy') device for the psuedoclock
DummyPseudoclock(name='pseudoclock')

# An output of this DummyPseudoclock is its 'clockline' attribute, which we use
# to trigger children devices
DummyIntermediateDevice(name='intermediate_device', parent_device=pseudoclock.clockline)

# Instantiate a labscript.Trigger instance used to trigger the camera exposure
# This will be specified as the camera's parent device later
Trigger(
    name='camera_trigger', parent_device=intermediate_device, connection='port0/line0'
)

# On the host specified below, start the RemoteBLACS server by running the following:
# $ python - m labscript_utils.remote
RemoteBLACS(name='test_remote', host='localhost')

# We then initiate an IMAQdxCamera using this RemoteBLACS instance
# using mock=True to bypass any attempts to commmunicate with an
# actual camera, and generate fake data at the end of the shot
IMAQdxCamera(
    name='camera',
    parent_device=camera_trigger,
    connection='trigger',
    serial_number=0xDEADBEEF,
    worker=test_remote,
    mock=True,
)

# Begin issuing labscript primitives
# A timing variable t is used for convenience
# start() elicits the commencement of the shot
t = 0
add_time_marker(t, "Start", verbose=True)
start()

t += 1
add_time_marker(t, "Exposure: 'before' image", verbose=True)
camera.expose(t, name='comparison', frametype='before', trigger_duration=0.2)

t += 0.5
add_time_marker(t, "Exposure: 'after' image", verbose=True)
camera.expose(t, name='comparison', frametype='after', trigger_duration=0.2)

t += 0.5
stop(t)
