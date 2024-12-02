#!/usr/bin/python

########################################################################################################################
# imports

import numpy as np
from labscript import start, stop, add_time_marker, LabscriptError, Trigger, DDSQuantity
from user_devices.FPGA_device.labscript_device import (
    FPGA_board, DigitalChannels, AnalogChannels, DDSChannels,
    AnalogOutput, DigitalOutput,
    PRIMARY_IP, SECONDARY_IP, DEFAULT_PORT,
)
from user_devices.FPGA_device.generic_conversion import generic_conversion
from user_devices.FPGA_device.DDS_generic import DDS_generic
from user_devices.FPGA_device.DAC import DAC712, DAC715, DAC7744
from user_devices.FPGA_device.shared import ADDR_SHIFT

from labscript_utils import import_or_reload
import_or_reload('labscriptlib.FPGA_test.connection_table')

from labscriptlib.FPGA_test.connection_table import primary, secondary

########################################################################################################################
# experimental sequence

if True:
    # load channels from globals.
    # in a typical experiment you give a proper name of your channel in connection_table. so this is not needed.
    ao = []
    do = []
    dds  = []
    for name, channel in globals()['__builtins__'].items():
        if isinstance(channel, AnalogOutput):
            ao.append(channel)
        elif isinstance(channel, Trigger): # skip trigger which is a DigitalOut
            pass
        elif isinstance(channel, DigitalOutput):
            do.append(channel)
        elif isinstance(channel, DDS_generic):
            dds.append(channel)
    print('%i analog  out' % (len(ao)))
    print('%i digital out' % (len(do)))
    print('%i DDS' % (len(dds)))

if __name__ == '__main__':

    #t = primary.start_time
    #dt = primary.time_step
    t = 0
    dt = 1e-6

    # start sequence
    start()

    if False:
        # these are some examples of options which can be set for each experiment.
        # this is convenient for debugging but permanent settings should be done in connection table worker_args.

        # set start, data stop and restart trigger
        # this is an example for a re-triggerable line-trigger at the start and during experiment
        # you can also use another input as start trigger and set in first data bit 30 (see WAIT command below).
        # this way you can wait for MOT loaded and start with next line trigger.
        primary.set_start_trigger('input 2', 'falling edge')          # start experiment with rising edge at input 2 (= input 1 on boared v1.3)
        primary.set_stop_trigger('data bits 28-31','offset bit 0')   # stop experiment when data bit 28 (see FPGA_device BIT_STOP) is set.
        primary.set_restart_trigger('input 2', 'rising edge')        # restart experiment with next rising edge on input 2.

    if False:

        # this sets stop bit 30 in data at the given time.
        # digital or analog channels can be still programmed at the same time.
        primary.WAIT(t)

        # for debugging its nice to have a signal when board is running or waiting
        # 'run' = high while running and restart trigger, low while waiting for start trigger
        # 'wait' = high while waiting for start or restart trigger
        # note: depending on board version output buffer is inverting
        primary.set_ctrl_out({'output 1': ('wait', 'low level')})

        # set synchronization primary wait time and secondary phase
        # for primary board use wait time >0 in units of 10ns and phase = 0
        # for secondary board use wait time = 0 and phase_ext can be used to fine-tune on the ns level.
        # phase_det is normally 0 but if you see random jumps of +/-10ns you can adjust this.
        # units of phase = 0..560 in steps of 1 = 0..360° in steps of 360/560°. 360° = 10ns.
        primary.set_sync_params(wait = 0, phase_ext = 0, phase_det = 0)

        # this sets the NOP bit at the given time
        # if a sample is at this time then the sample is sent to the board but not executed.
        # if no sample is at this time an empty sample is sent but not executed.
        # this is for demonstration only. probably you will never need this.
        #primary.SKIP(time = 10*dt)

    # define some experiment parameters
    # they might be defined from runviewer globals, otherwise value is assigned
    try:
        inverted
    except NameError:
        inverted = False                  # invert signals
    try:
        do_ramp
    except NameError:
        do_ramp = False                 # perform triangular ramp on all analog channels
    try:
        ramp_rate
    except NameError:
        ramp_rate = 100e3               # sample rate in Hz
    try:
        wait_between_digital
    except NameError:
        wait_between_digital = False    # wait for switching each digital channel
    try:
        experiment_time
    except NameError:
        experiment_time = 1.0         # experiment time in seconds

    # switch all digital outputs on/off
    # we change this with address and invert flag to have not all boards the same pattern
    # this can be done all together or one by one
    if True:
        i = 1 if inverted else 0
        for doi in do:
            if (doi.properties['address'] ^ i) & 1:
                doi.go_high(t)
            else:
                doi.go_low(t)
            if wait_between_digital:
                t += dt
            i += 1

    t += dt
    #test_camera.expose(t, 'test_image_1', trigger_duration=0.1)
    #pb0_trg.trigger(t,duration=0.1)

    # switch all analog outputs to constant values
    # this has to be done one-by-one
    if True:
        j = 1 if inverted else 0
        for i,aoi in enumerate(ao):
            if ((aoi.properties['address'] & 1) ^ j) or isinstance(aoi, DAC715):
                aoi.constant(t, 1 + (i % 9))
            else:
                #print(aoi.name, t, -1 - (i % 9))
                aoi.constant(t, -1 - (i % 9))
            t += dt

    if True:
        # DAC test.
        # writes test_data for each DAC. manually check the resulting word in data sent to board.
        # - we must exclude data outside limits since otherwise get out of limit error (as expected).
        # - only data where channel changes are written, i.e. same words after each other are removed.
        dt_step = 1e-3
        channel = ao2
        for V,word in channel.test_data.items():
            if V < channel.AO_MIN or V > channel.AO_MAX: continue
            print("%s (%s): time = %.6f, V = %.6f, expected word = 0x%08x" % (channel.name, type(channel).__name__, t, V, np.uint32(word | (channel.properties['address'] << ADDR_SHIFT))))
            channel.constant(t,V)
            t += dt_step

    if True:
        # DDS test
        # notes for analog device DDS:
        # - most functions produce more than one sample on the bus
        #   the samples are written with bus_rate given to DDSChannels in connection table
        # - most functions have an 'update' flag:
        #   this allows to first set all registers before updating output,
        #   which avoids spurious spikes while writing to registers.
        # - here we update the DDS with 1MHz bus rate.
        #   when the DDS update rate is slower set dt_dds to the time the DDS needs to update.
        #   in this case, or if there would be a faster device on the bus,
        #   then this faster device might be programmed in the mean time on the bus,
        #   which I assume should be no problem.
        dt_dds = 1e-6
        t += dt_dds
        # DDS AD9854
        t += dds_0.setfreq (t, 10e6, update=False) + dt_dds
        #t += dds_0.setfreq(t, 80e6, update=False) + dt_dds
        #t += dds_0.setfreq(t, 100e6, update=False) + dt_dds
        #t += dds_0.setfreq(t, 136e6, update=False) + dt_dds
        if False:
            # test in-between command:
            # ok when slot is free, i.e. dt_dds > 1e-6
            # when slot is occupied gives expected error in runviewer about time collission.
            do0.go_low(t - dt_dds/2)
        t += dds_0.setamp  (t,  -10, update=False) + dt_dds
        t += dds_0.setphase(t,  100, update=True ) + dt_dds
        # DDS AD9858
        t += dds_1.setfreq (t, 200e6, update=False) + dt_dds
        t += dds_1.setamp  (t,   -20              ) + dt_dds    # this has no update flag!
        t += dds_1.setphase(t,   200, update=True ) + dt_dds
        # DDS AD9915
        t += dds_2.setfreq (t, 100e6, update=False) + dt_dds
        t += dds_2.setamp  (t,    -1, update=False) + dt_dds
        t += dds_2.setphase(t,    25, update=True ) + dt_dds

        # generic DDS
        t += dds_5.setfreq (t, 55e6) + dt_dds
        t += dds_5.setamp  (t,   -5) + dt_dds
        t += dds_5.setphase(t,   45) + dt_dds

        if True:
            dds = dds_0
            for i in range(5):
                dds.setfreq(t, 70e6+i*1e6, update=True)
                t += 0.1

        if False:
            dds_0.setfreq(t, 70e6)
            t += 0.1
            dds_5.setfreq(t, 71e6)
            t += 0.1
        else:
            #t -= 0.15
            dds_0.setfreq(t, 80e6)
            t += 0.1
            dds_5.setfreq(t, 50e6)
            t += 0.1

        ao3.constant(0.5, 10.0)

    if do_ramp:
        # do a triangular ramp on one analog channel
        channel = ao4
        t += dt
        duration = experiment_time - t - 2*dt - 2/ramp_rate
        t += channel.ramp(t=t, initial=  0, final= 10, duration=duration/4, samplerate=ramp_rate) + 1/ramp_rate
        t += channel.ramp(t=t, initial= 10, final=-10, duration=duration/2, samplerate=ramp_rate) + 1/ramp_rate
        t += channel.ramp(t=t, initial=-10, final=  0, duration=duration/4, samplerate=ramp_rate) + dt

    if False:
        # switch all analog outputs to constant values
        # this has to be done one-by-one
        if True:
            t = experiment_time/4
            for i,aoi in enumerate(ao):
                aoi.constant(t,(i+1)*0.1)
                t += dt

        # switch all analog outputs to constant values
        # this has to be done one-by-one
        if True:
            t = experiment_time/2
            for i,aoi in enumerate(ao):
                if isinstance(aoi, DAC715):
                    aoi.constant(t, (i + 1) * (5.0) / len(ao))
                else:
                    aoi.constant(t,(i+1)*(-5.0)/len(ao))
                t += dt

    # switch all analog outputs to constant values
    # this has to be done one-by-one
    if True:
        t = experiment_time - (len(ao))*dt - ((len(do)+1)*dt if wait_between_digital else dt)
        if True:
            # delay primary until next restart trigger
            # secondary is not affected by this
            primary.WAIT(t)
        j = 1 if inverted else 0
        for i,aoi in enumerate(ao):
            if ((aoi.properties['address'] & 1) ^ j) and not isinstance(aoi, DAC715):
                aoi.constant(t, -1 - (i % 9))
            else:
                aoi.constant(t, 1 + (i % 9))
            t += dt

    # switch all digital outputs off/on
    # we change this with address and invert flag to have not all boards the same pattern
    # this can be done all together or one by one
    if True:
        t = experiment_time - ((len(do)+1)*dt if wait_between_digital else dt)
        i = 0 if inverted else 1
        for doi in do:
            if (doi.properties['address'] ^ i) & 1:
                doi.go_high(t)
            else:
                doi.go_low(t)
            if wait_between_digital:
                t += dt
            i += 1

    # stop sequence
    t = experiment_time
    print('experiment duration %.3fs' % (t))
    stop(t)


