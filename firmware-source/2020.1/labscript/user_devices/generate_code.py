def reduce_instructions(self, max_instructions=1000):
    for pseudoclock in self.child_devices:
        for clockline in pseudoclock.child_devices:
            for IM in clockline.child_devices:
                for dev in IM.child_devices:
                    if len(dev.instructions) > max_instructions:
                        num = len(dev.instructions)
                        # print(dev.instructions)
                        # extract all single integer or float values from instrutions
                        all_times = np.array(list(dev.instructions.keys()))
                        times, values = np.transpose([[key, dev.instructions[key]] for key in dev.instructions.keys() if
                                                      isinstance(dev.instructions[key], (int, float))])
                        mask = np.isin(all_times, times)
                        print('other times', all_times[~mask])
                        print('times', times)
                        # instructions might not be sorted in time.
                        # we sort in reverse order for digitize to work as we want.
                        index = np.argsort(times)[::-1]
                        times = times[index]
                        values = values[index]
                        first = times[-1]
                        next = times[-2]
                        last = times[0]

                        # delete old instructions
                        for key in times:
                            del dev.instructions[key]

                        # time given to get_value is relative to 'initial time' added with a offset
                        # this offset is calculated from 'midpoint' between the first two datapoints
                        # assuming constant sampling time but this is not the case here.
                        # so we shift time here by the possible wrong midpoint and subtract time_step/2
                        # to be sure that t is slightly larger than times to avoid numerical errors.
                        times += -first - 0.5 * (next - first) - self.time_step / 2
                        print('times', times)
                        print(len(times))

                        # print('times=',times)

                        # define a new instruction function which returns value for given time t.
                        # t can be a numpy array or a skalar.
                        # this is adapted from labscript.functions.pulse_sequence
                        # note that labscript might insert an arbitrary number of in-between points
                        # we return the last value set at or before the given time t.
                        def get_value(t):
                            print('t=', t)
                            try:
                                len(t)  # this will cause TypeError when t is not a list
                                print(len(t))
                                print(np.digitize(t, times, right=False))
                                print(t - times[np.digitize(t, times, right=False)])
                                return values[np.digitize(t, times, right=False)]
                            except TypeError:
                                print(np.digitize([t], times, right=False))
                                print(values[np.digitize([t], times, right=False)][0])
                                return values[np.digitize([t], times, right=False)][0]

                        # define new instruction calling get_value
                        dev.instructions[first] = {'function': get_value,
                                                   'description': 'get value for given time',
                                                   'initial time': first,
                                                   'end time': last,
                                                   'clock rate': self.bus_rate / 10,
                                                   'units': None,
                                                   'times': times,
                                                   'values': values}

                        print("'%s' %i instructions reduced to %i" % (dev.name, num, len(dev.instructions)))
                        print(dev.instructions.keys())


def check_times(self, pseudoclock, device):
    # compare with code in labscript.py, see pseudoclock.generate_clock()
    # device is intermediate device (DigitalChannels) or AnalogOut

    # get parent clockline and all outputs
    outputs_by_clockline = {}
    if isinstance(device, AnalogOut):
        clockline = device.parent_device.parent_device
        outputs = [device]
    elif isinstance(device, DigitalChannels):
        clockline = device.parent_device
        outputs = device.child_devices
    else:
        raise LabscriptError(
            "device %s is neither AnalogOut nor DigitalChannels but %s" % (device.name, device.__class__))
    outputs_by_clockline[clockline] = outputs

    # get all change times
    all_change_times = []
    change_times = {}
    for dev in outputs:
        all_change_times.extend(list(dev.instructions.keys()))
    change_times[clockline] = all_change_times

    if np.max(all_change_times) != pseudoclock.parent_device.stop_time:
        print('stop time =', pseudoclock.parent_device.stop_time)
        print('last time =', np.max(all_change_times))
        pseudoclock.parent_device.stop_time = np.max(all_change_times)
        print('stop time =', pseudoclock.parent_device.stop_time)

    times, clock = pseudoclock.expand_change_times(all_change_times, change_times, outputs_by_clockline)
    print(times)


def expand_times_and_values(self, device, shared_times, expand_values):
    """
    expand times and values from device instructions.
    if shared_times is not None uses these times, otherwise uses times from instructions. requires expand_values = True.
    if expand_values = True returns values, otherwise values = [].
    returns [times, values]
    """
    times = []
    values = []
    for key, value in device.instructions.items():
        if isinstance(value, (int, float)):  # single value. units conversion is already applied
            times.extend([key])
            if expand_values:
                values.extend([value])
        elif isinstance(value, dict):  # function
            # TODO: check what labscript exactly does
            t_start = round(value['initial time'], 10)
            t_end = round(value['end time'], 10)
            samples = int((t_end - t_start) * value['clock rate'])
            if (t_start + samples / value['clock rate']) < t_end:
                # we move slightly t_start towards larger times to have correct sampling rate.
                # this ignores that times should be integer multiple of dt.
                t_start = t_end - samples / value['clock rate']
            t = key + np.linspace(t_start, t_end, samples)
            times.extend(t)
            if expand_values:
                v = value['function'](t)
                if value['units'] is not None:
                    v = device.apply_calibration(v, value['units'])
                values.extend(v)
        elif isinstance(value, (list, np.ndarray)):  # allow direct input of data[0] = time, data[1] = value
            times.extend(value[0])
            if expand_values:
                values.extend(value[1])
        else:  # unknown type?
            print(value)
            raise LabscriptError("unknown instruction! at time %f" % (key))

    # check smallest time and insert t0 if is not there.
    # this ensures that digitize returns always valid indices even if the first instruction of device is at later time.
    t_min = np.min(times)
    if t_min < self.t0:
        raise LabscriptError("time %f < %f!" % (t_min, self.t0))
    elif t_min > self.t0:
        times.extend([self.t0])
        values.extend([device.default_value])

    # ensure there are unique times. TODO: maybe more efficient after sorting by looking on difference not zero?
    if len(times) != len(np.unique(times)):
        print(times)
        raise LabscriptError("times are not unique!")

    if expand_values and (len(times) != len(values)):
        print(times)
        print(values)
        raise LabscriptError("times (%i) and values (%i) are inconsistent!" % (len(times), len(values)))

    if shared_times is None:
        if expand_values:
            # sort times
            index = np.argsort(times)
            times = np.array(times)[index]
            values = np.array(values)[index]
        else:
            # we sort times later
            times = np.array(times)
    else:
        # shared_times given
        if len(times) == 1:
            # single time bin: return single value for all shared_times
            values = np.ones(shape=(len(shared_times),), dtype=device.dtype) * values[0]
            times = shared_times
        else:
            # map times to shared_times 'ts' using times[i] <= ts < times[i+1]
            index = np.argsort(times)[::-1]
            times = np.array(times)[index]
            values = np.array(values)[index]
            index = np.digitize(shared_times + self.time_step / 2, times, right=False)
            if np.count_nonzero((shared_times < times[-1]) | (shared_times > times[0])) > 0:
                # shared_time must be >= smallest time otherwise digitize gives index = len(times)
                # if shared_time >= largest time digitize gives index = 0
                t = shared_times[(shared_times < times[-1]) | (shared_times > (times[0] + self.time_step / 2))]
                print('times outside range [%f,%f]:' % (times[-1], times[0]), t)
                raise LabscriptError("shared time must be in range %f <= t <= %f!" % (times[-1], times[0]))
            if True:  # check mapping
                # print('times  =', times)
                ## print('values =',values)
                # print('t      =', shared_times)
                # print('index  =', index)
                # print('isin   =', np.isin(shared_times, times))
                for i, t in enumerate(shared_times):
                    if ((index[i] + 1 < len(times)) and (times[index[i]] <= t < times[index[i] + 1])):
                        raise LabscriptError(
                            "error time: %f <= %f < %f is not fulfilled!" % (times[index[i]], t, times[index[i] + 1]))
                    elif (index[i] == len(times)) and not (times[0] <= t):
                        raise LabscriptError("error time: %f <= %f is not fulfilled!" % (times[index[i]], t))
            values = values[index]
            times = shared_times
    return [times, values]


def get_raw_data(self, do_check_times=True):
    "replaces PseudoclockDevice.generate_code"
    # TODO: unfinished. would need to manually expand ramps, which would be not difficult.
    #       this function could already collect data, changes, conflicts.
    #       maybe still first collect all times from instructions including function times so we can allocate data.
    #       different devices on the same clocklines do not need to be combined,
    #       i.e. no intermediate values need to be calculated for any device.
    #       clock limits, i.e. smallest deltas can be checked per device.
    # - this function should give the same result as expand_change_times + expand_timeseries called for each device with independend address.
    #   the same effect would be to give each analog output and each digital intermediate device a single pseudoclock.
    self.all_times = []
    for pseudoclock in self.child_devices:
        for clockline in pseudoclock.child_devices:
            # note: clockline does not get times. these are stored per device
            for IM in clockline.child_devices:
                if IM.shared_address:
                    shared_times = [self.expand_times_and_values(dev, shared_times=None, expand_values=False)[0] for dev
                                    in IM.child_devices if len(dev.instructions) > 0]
                    IM.times = shared_times = np.unique([t for l in shared_times for t in l])
                else:
                    shared_times = None
                for dev in IM.child_devices:
                    if len(dev.instructions) > 0:
                        dev.times, dev.raw_output = self.expand_times_and_values(dev, shared_times=shared_times,
                                                                                 expand_values=True)
                        self.all_times.extend(dev.times)
                        # TODO: check toggle rate of device. call do_checks?

                        if do_check_times and not IM.shared_address and isinstance(dev, AnalogOut):
                            self.check_times(pseudoclock, dev)
                    else:
                        if IM.shared_address:
                            dev.times = shared_times
                            dev.raw_output = np.ones(shape=(len(shared_times),), dtype=dev.dtype) * dev.default_value
                        else:
                            dev.times = dev.raw_output = np.array([])
                if do_check_times and IM.shared_address:
                    self.check_times(pseudoclock, IM)

        self.all_times = np.unique(self.all_times)
        #print(self.all_times)
        # from here proceed generating data matrix, collect changes and check conflicts as below in generate_code

    def generate_code(self, hdf5_file):
        global total_time

        save_print("\n'%s' generating code ...\n" % (self.name))
        if self.name == 'primary':
            total_time = get_ticks()

        # Generate clock and save raw instructions to the hdf5 file:
        # - generate_code_with_labscript = True:
        #   uses original code from labscript.py
        #   this is a bottleneck and scales bad with number of instructions!
        #   merges all times for each clockline and generated raw data for all times
        #   performs many advanced checks
        # - generate_code_with_labscript = False: [experimental stage]
        #   much simpler code just expands functions and performs basic tests
        #   merges only times for intermediate devices with shared address (DigitalOut)
        #   much faster but is not fully tested!
        #   returns different number of samples than generate_code_with_labscript = True.
        generate_code_with_labscript = True  # True = old slow code, False = new optimized code for FPGA_board
        if generate_code_with_labscript:
            # first attempt to merge multiple instructions into fewer ones.
            # partially working but not finished. labscript assums ramps/functions with constant time steps which is not what I would need.
            # self.reduce_instructions(max_instructions=100)
            PseudoclockDevice.generate_code(self, hdf5_file)
        else:
            self.get_raw_data()
        print('total_time %.3fms' % ((get_ticks() - total_time) * 1e3))

        t_start = get_ticks()
        # experimental:
        # merge all times of all pseudoclocks and clocklines
        # times and channel.raw_data will have different lengths!
        if generate_code_with_labscript:
            times = np.unique(np.concatenate([pseudoclock.times[clockline] for pseudoclock in self.child_devices for clockline in pseudoclock.child_devices]))
        else:
            times = self.all_times

        #save_print("'%s' total %i times:\n"%(self.name,len(times)),times)
        # allocate data matrix row x column = samples x (time + data for each rack)
        data = np.zeros(shape=(len(times), self.num_racks + 1), dtype=np.uint32)
        # allocate mask where data changes from one sample to next
        changes = np.zeros(shape=(len(times), self.num_racks), dtype=np.bool_)
        # allocate mask where several devices with different address change at the same time.
        # note that several TTL outputs with the same address (on the same IM device) are allowed to change simultaneously.
        conflicts = np.zeros(shape=(len(times), self.num_racks), dtype=np.bool_)

        # insert time word
        data[:, 0] = time_to_word(times, self.bus_rate, self.digits)

        # go through all channels and collect data
        special = False
        special_STRB = False
        for pseudoclock in self.child_devices:
            #print('%s:'%pseudoclock.name)
            for clockline in pseudoclock.child_devices:

                t = pseudoclock.times[clockline]
                #print("'%s' %i times:\n"%(clockline.name, len(t)), t)

                # get indices of t within times
                # note: working with mask might be faster but I have troubles with double-indexing on left-hand side of assignments.
                #       this does not work: changes[mask][chg] = True assigns to a COPY of changes[mask] which is then thrown away!
                #       this however works: changes[mask] = chg. to use this with data: m2=mask.copy(); m2[mask]=chg; data[m2] = d[chg];
                #       I think this is a misconception of Python.
                #       why would one want to make a copy of anything on the left-hand-side of an assignment?
                indices = np.argwhere(np.isin(times, t)).ravel()

                if len(indices) != len(t): # sanity check
                    raise LabscriptError('generate_code: no all times of pseudoclock found? (should not happen)')

                for IM in clockline.child_devices:
                    #print('%s:'%IM.name)

                    # skip special devices (will be treated after all other below)
                    if isinstance(IM, SpecialIM):
                        special = True
                        continue

                    if IM.shared_address:

                        if not generate_code_with_labscript:
                            t = IM.times
                            if len(t) == 0: continue
                            indices = np.argwhere(np.isin(times, t)).ravel()

                        # collect data for all channels of IM device
                        d   = np.zeros(shape=(len(t),), dtype=np.uint32)
                        chg = np.zeros(shape=(len(t),), dtype=np.bool_)

                        for dev in IM.child_devices:
                            #if np.count_nonzero(dev.raw_output == dev.default_value) != len(t):
                            #    #print('%s instr:'%dev.name, dev.instructions)
                            #    print('%s raw data:' % dev.name, dev.raw_output)

                            if len(dev.raw_output) != len(t):  # sanity check.
                                raise LabscriptError('generate_code: raw output (%i) not consistent with times (%i)? (should not happen)' % (len(dev.raw_output), len(t)))

                            # convert raw data into data word and accumulate with other channels
                            d |= dev.to_word(dev.raw_output)

                            # mark changes
                            chg[0]  |= (dev.raw_output[0] != dev.default_value)
                            chg[1:] |= ((d[1:] - d[:-1]) != 0)

                        # check conflicts with devices of different address
                        i = indices[chg]
                        conflicts[i,dev.rack] |= changes[i,dev.rack]
                        changes[i,dev.rack] = True

                        # save data where output changed
                        # we have to mask NOP bit from unused channels
                        data[i,dev.rack+1] = d[chg] & DATA_ADDR_MASK
                    else:
                        # no shared address: collect data for each individual device
                        for dev in IM.child_devices:
                            #if np.count_nonzero(dev.raw_output == dev.default_value) != len(t):
                            #    # print('%s instr:'%dev.name, dev.instructions)
                            #    print('%s raw data:' % dev.name, dev.raw_output)

                            if not generate_code_with_labscript:
                                t = dev.times
                                if len(t) == 0: continue
                                indices = np.argwhere(np.isin(times, t)).ravel()

                            if len(dev.raw_output) != len(t):  # sanity check.
                                raise LabscriptError('generate_code: raw output not consistent with times? (should not happen)')

                            # convert raw data into data word
                            d = dev.to_word(dev.raw_output)
                            #print('%s data:' % dev.name, d)

                            # mark changes
                            chg = np.empty(shape=(len(t),), dtype=np.bool_)
                            chg[0]  = (dev.raw_output[0] != dev.default_value)
                            chg[1:] = ((d[1:] - d[:-1]) != 0)
                            i = indices[chg]

                            # detect conflicts with other devices
                            conflicts[i, dev.rack] |= changes[i, dev.rack]
                            changes[i,dev.rack] = True

                            # save data where output changes
                            data[i,dev.rack+1] = d[chg]

        if special:
            # collect special data bits
            # these bits are combined with existing data and cannot cause conflicts
            for pseudoclock in self.child_devices:
                for clockline in pseudoclock.child_devices:
                    if generate_code_with_labscript:
                        t = pseudoclock.times[clockline]
                        indices = np.argwhere(np.isin(times, t)).ravel()
                        if len(t) == 0: continue
                    for IM in clockline.child_devices:
                        if isinstance(IM, SpecialIM):
                            for dev in IM.child_devices:
                                #if np.count_nonzero(dev.raw_output == dev.default_value) != len(t):
                                #    print('%s instr:'%dev.name, dev.instructions)
                                #    print('%s raw data:' % dev.name, dev.raw_output)

                                if not generate_code_with_labscript:
                                    t = dev.times
                                    if len(t) == 0: continue
                                    indices = np.argwhere(np.isin(times, t)).ravel()

                                if len(dev.raw_output) != len(t):  # sanity check.
                                    raise LabscriptError('generate_code: raw output not consistent with times? (should not happen)')

                                # convert raw data into data word
                                d = dev.to_word(dev.raw_output)
                                #print('%s data:' % dev.name, d)

                                # check if strobe bit is set somewhere
                                if np.count_nonzero(d & BIT_STRB_SH) > 0:
                                    special_STRB = True

                                # take all non-default values
                                mask = (d != dev.default_value)
                                if t[-1] not in dev.instructions:
                                    # remove last entry when was automatically inserted by labscript, i.e. when its not in instructions
                                    mask[-1] = False
                                i = indices[mask]

                                # mark all non-default special entries as changed data
                                changes[i, dev.rack] |= True

                                # combine ALL non-default special data bits with existing data
                                data[i,dev.rack+1] |= d[mask]

        if False:
            # show all data for debugging
            self.show_data(data, '\ndata (all):')
            #save_print('changes:\n', np.transpose(changes))
            #save_print('conflicts:\n', np.transpose(conflicts))

        if np.count_nonzero(conflicts) != 0:
            # time conflicts detected
            conflicts_t  = {}
            conflicts_ch = {}
            for rack in range(self.num_racks):
                conflicts_t[rack] = times[conflicts[:,rack]]
            # go through all channels and collect conflicting channel information
            for pseudoclock in self.child_devices:
                for clockline in pseudoclock.child_devices:
                    if generate_code_with_labscript:
                        t = pseudoclock.times[clockline]
                        indices = np.argwhere(np.isin(times, t)).ravel()
                    for IM in clockline.child_devices:
                        for dev in IM.child_devices:
                            if not generate_code_with_labscript:
                                t = dev.times
                                indices = np.argwhere(np.isin(times, t)).ravel()
                            d = dev.to_word(dev.raw_output)
                            chg = np.empty(shape=(len(t),), dtype=np.bool_)
                            chg[0] = (dev.raw_output[0] != dev.default_value)
                            chg[1:] = ((d[1:] - d[:-1]) != 0)
                            mask = np.isin(t[chg], conflicts_t[dev.rack])
                            if np.count_nonzero(mask) > 0:
                                info = (dev.type,  # channel type
                                        dev.rack,  # rack number
                                        dev.address,  # address
                                        indices[chg][mask],  # sample index
                                        t[chg][mask],  # time in seconds
                                        list(np.concatenate(([dev.default_value], dev.raw_output[chg][:-1]))[mask]), # old value
                                        dev.raw_output[chg][mask])  # new value
                                if dev.name in conflicts_ch:
                                    old = conflicts_ch[dev.name]
                                    conflicts_ch[dev.name] = (old[i] if i < 3 else old[i] + info[i] for i in range(len(old)))
                                else:
                                    conflicts_ch[dev.name] = info

            for rack in range(self.num_racks):
                if len(conflicts_t) > 0:
                    indices = np.argsort(conflicts_t[rack])
                    save_print('\n%i time conflicts on %i channels detected:\n' % (len(conflicts_t[rack]), len(conflicts_ch)))
                    save_print('%35s %4s %4s %12s %12s %12s %12s' % ('channel name','rack','addr','sample','time (s)','old value','new value'))
                    for t in conflicts_t[rack]:
                        for ch, info in conflicts_ch.items():
                            for i in range(len(info[3])):
                                if info[4][i] == t:
                                    if info[0] == TYPE_DO: # digital out
                                        s2 = "0x%02x" % (info[2])
                                        s5 = '-' if info[5][i] == DO_AUTO_VALUE else ("low" if info[5][i]==0 else "high")
                                        s6 = '-' if info[6][i] == DO_AUTO_VALUE else ("low" if info[6][i]==0 else "high")
                                        s7 = ''
                                    elif info[0] == TYPE_AO: # analog out
                                        s2 = "0x%02x" % (info[2])
                                        s5 = '-' if info[5][i] == AO_AUTO_VALUE else "%12.6f" % info[5][i]
                                        s6 = '-' if info[6][i] == AO_AUTO_VALUE else "%12.6f" % info[6][i]
                                        s7 = ''
                                    elif info[0] == TYPE_SP:
                                        # special data
                                        # note: since address = None will never cause conflict but can appear with other conflicts when at same time
                                        s2 = '-'
                                        s5 = '-' if info[5][i] == SP_AUTO_VALUE else "0x%8x" % info[5][i]
                                        s6 = '-' if info[6][i] == SP_AUTO_VALUE else "0x%8x" % info[6][i]
                                        s7 = ' ignore'
                                    save_print('%35s %4i %4s %12i %12.6f %12s %12s%s'%(ch, info[1], s2, info[3][i], info[4][i], s5, s6, s7))
                        save_print()
            save_print()
            raise LabscriptError('%i time conflicts detected! (abort compilation)' % (np.count_nonzero(conflicts)))

        # detect samples where anything changes on any rack
        chg = np.any(changes, axis=1)

        # updated: we keep first sample under any conditions (marked with NOP if nothing happens)
        # where special data STRB bit is set we do not toggle strobe bit in data.
        # however, the board always executes first instruction regardless of first strobe bit.
        # therefore we give an error below and in SKIP() when for first sample STRB bit is set.
        # here we retain first sample such that at least one sample is before any sample with STRB bit.
        # if first sample does not contain data it will be marked with NOP bit below.
        #if special_STRB: chg[0] = True
        chg[0] = True

        # we always keep the last sample (marked with NOP if nothing happens)
        chg[-1] = True

        # remove samples without changes on any rack
        data = data[chg]
        changes = changes[chg]

        # add NOP for racks without changes
        for rack in range(self.num_racks):
            data[:,rack+1][~changes[:,rack]] = BIT_NOP_SH

        # insert toggle strobe into data
        if special_STRB:
            # we do not want to toggle all data
            for rack in range(self.num_racks):
                mask = np.array(data[:,rack+1] & BIT_STRB_SH == 0, dtype=np.uint32)
                if mask[0] == 0:
                    # first sample has strobe bit set which does not work (see notes above).
                    if data[0,0] == 0: raise LabscriptError("you have specified do_not_toggle_STRB for time = 0 which does not work! use NOP bit instead.")
                #print(mask)
                #print(np.cumsum(mask) & 1)
                if False: # use XOR
                    strb = (np.cumsum(mask) & 1) * BIT_STRB_SH
                    data[:,rack+1] ^= np.concatenate((np.array([0],dtype=np.uint32),strb[:-1]))
                else: # use OR and mask (TODO: check what is faster)
                    strb = (np.cumsum(mask) & 1) * BIT_STRB_SH
                    data[:,rack+1] = (data[:,rack+1] & BIT_STRB_MASK) | strb
        else:
            # toggle strobe for all data
            if len(data) & 1 == 1: strb = np.tile(np.array([0,BIT_STRB_SH],dtype=np.uint32),reps=(len(data)+1)//2)[:-1]
            else:                  strb = np.tile(np.array([0,BIT_STRB_SH],dtype=np.uint32),reps=len(data)//2)
            for rack in range(self.num_racks):
                data[:,rack+1] |= strb

        # save matrix for each board to file
        # TODO: had to add device name also to devices otherwise get error. however now we create board#_devices/board#.
        group = hdf5_file['devices'].create_group(self.name)
        group.create_dataset('%s_matrix' % self.name, compression=config.compression, data=data)

        # save extra worker arguments into hdf5. we must convert everything into a string and convert it back in worker.
        save_print('saving worker args ex:\n', self.worker_args_ex)
        if decode_string_with_eval:
            d = str(self.worker_args_ex)
        else:
            d = to_string(self.worker_args_ex)
        group.create_dataset('%s_worker_args_ex' % self.name, shape=(1,), dtype='S%i' % (len(d)), data=d.encode('ascii', 'ignore'))

        # TODO: add another group with all used channels. this can be used by runviewer to avoid displaying unused channels.
        #      channels should be already saved somehow in hdf5? so maybe one can add this info for each channel there?

        # save stop_time and if master pseudoclock = primary board into hdf5
        # for master_pseudoclock t0 = 0
        self.set_property('is_master_pseudoclock', self.is_master_pseudoclock, location='device_properties')
        self.set_property('stop_time', self.stop_time, location='device_properties')

        save_print("'%s' generating code done" % (self.name))

        # save if primary board and list of secondary boards names, or name of primary board.
        # the names identify the worker processes used for interprocess communication.
        if self.is_primary:
            self.set_property('is_primary', True, location='connection_table_properties', overwrite=False)
            self.set_property('boards', [s.name for s in self.secondary_boards],
                              location='connection_table_properties', overwrite=False)
        else:
            self.set_property('is_primary', False, location='connection_table_properties', overwrite=False)
            self.set_property('boards', [self.primary_board.name], location='connection_table_properties',
                              overwrite=False)

        t_end = get_ticks()
        t_new = (t_end - t_start) * 1e3
        self.show_data(data, 'data: (%.3fms)' % (t_new))
        print('total_time %.3fms' % ((get_ticks() - total_time) * 1e3))

        for secondary in self.secondary_boards:
            #save_print('%s call generate code for %s' % (self.name, secondary.name))
            secondary.generate_code(hdf5_file)

