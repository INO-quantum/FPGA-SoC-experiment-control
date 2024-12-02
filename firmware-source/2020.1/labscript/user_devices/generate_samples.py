#!/usr/bin/env python
##############################################################################################################
# generate digital and analoge samples and other test functions
##############################################################################################################

#from user_devices.FPGA_device import FPGA_board, DigitalChannels, AnalogChannels, PRIMARY_IP, SECONDARY_IP, DEFAULT_PORT, V_to_word, word_to_V

def generate_digital_samples(DigitalChannels_device, start_time, time_step = None, end_time = None, num_samples = None):
    """
    generates num_samples for the given DigitalChannels device.
    start_time = starting time
    if time_step == None calculates time_step from last_time and num_samples
    if end_time == None calculates end_time from time_step and num_samples
    if num_samples == None calculates num_samples from time_step and end_time
    returns last time
    ATTENTION: all channels of device are used! ensure no real device is attached!!!
    """
    # get channels
    channels = DigitalChannels_device.child_devices
    num = len(channels)
    # calculate parameters
    if time_step == None: time_step = (end_time - start_time)/(num_samples - 1)
    if end_time  == None: end_time = start_time + (num_samples - 1) * time_step
    if num_samples == None: num_samples = (end_time - start_time)//time_step + 1
    # switch on one channel per time_step
    t = start_time - time_step
    ramp_up = True
    cc = 0
    for i in range(num_samples):
        t += time_step
        for c,ch in enumerate(channels):
            if (c == cc): ch.go_high(t)
            else:         ch.go_low(t)
        if ramp_up:
            if cc == (num-1): ramp_up = False; cc = num - 2;
            else: cc += 1
        else:
            if cc == 0: ramp_up = True; cc = 1;
            else: cc -= 1
        if t >= end_time: break
    return t

def generate_analog_samples(AnalogOut_device, start_time, time_step = None, end_time = None, num_samples = None, Umin=-10, Umax=+10, dU=None):
    """
    generates num_samples for the given AnalogOut device.
    generates a triangular signal from Umin to Umax and back at given resolution dU
    start_time = starting time
    if time_step == None calculates time_step from last_time and num_samples
    if end_time == None calculates end_time from time_step and num_samples
    if num_samples == None calculates num_samples from time_step and end_time
    if dU == None uses the highest possible resolution = (Umax-Umin)/(2^16-1)
    returns last time
    ATTENTION: generates linear ramps (triangle signal) from -10V to +10V on the analog output at given rate!
               if a device is attached ensure device can handle this!!!
    """
    # calculate parameters
    if time_step == None: time_step = (end_time - start_time)/(num_samples - 1)
    if end_time  == None: end_time = start_time + (num_samples - 1) * time_step
    if num_samples == None: num_samples = (end_time - start_time)//time_step + 1
    if dU == None: dU = (Umax-Umin)/(2**16-1) # highest resolution for +/-10V or +/-5V
    # generate triangular signal
    t = start_time - time_step
    ramp_up = True
    U = dU # we assume we start at 0V, so the first sample must be 0 + dU
    for i in range(num_samples):
        t += time_step
        #print([t,U,int(U*(0xffff/20))])
        AnalogOut_device.constant(t,U)
        if ramp_up:
            if U >= Umax: ramp_up = False; U = Umax - dU;
            else: U += dU
        else:
            if U <= Umin: ramp_up = True; U = Umin + dU;
            else: U -= dU
        if t >= end_time: break
    return t

def generate_analog_ramp(AnalogOut_device, t_start, t_end, U_start, U_end, num_samples, t_res=None, U_res=None):
    """
    generates a linear ramp from t_start to t_end and U_start to U_end with num_samples samples.
    t_res = resolution in time. if None uses 1e-6
    U_res = resolution in voltage. if None uses 20V/(2^16-1)
    if the resolution of the ramp points is < t_res or U_res, fewer samples are returned, where time or voltage is changing.
    first and last points are always included.
    """
    if t_res is None: t_res = 1e-6
    if u_res is None: U_res = 20.0/((2**16)-1)
    dt = int((t_end-t_start)*t_res/(num_samples-1))
    if abs(dt) < 1: dt = np.sign(dt)
    dU = int((U_end-U_start)*U_res/(num_samples-1))
    if abs(dU) < 1: dU = np.sign(dU)

    t = np.arange(int(t_start*t_res), int(t_end*t_res), dt, dtype=int)
    U = np.arange(int(t_start*t_res), int(t_end*t_res), dt, dtype=int)

    print(np.transpose([t,U]))

    t = t*t_res
    U = U*U_res
    
    return t

# test voltage to word and word to voltage conversion
# we use analog_resolution=1 so we can test direclty the signed/unsigned aritmetics without scaling.
def test_word():
    # test voltage are signed integers
    voltages = [0,1,2,0x7ffe,0x7fff,-0x8000,-0x7fff,-2,-1]
    # expected words are unsigned 16-bit integers
    words    = [0,1,2,0x7ffe,0x7fff,0x8000,0x8001,0xfffe,0xffff]
    for i,V in enumerate(voltages):
        word = V_to_word(V, analog_resolution=1)
        if word != words[i]:
            raise LabscriptError('voltage %f gives word 0x%x but expected 0x%x!' % (V, word, words[i]))
        volts = word_to_V(word, analog_resolution=1)
        if volts != V:
            raise LabscriptError('word 0x%x gives voltage %f but expected %f!' % (word, volts, V))


