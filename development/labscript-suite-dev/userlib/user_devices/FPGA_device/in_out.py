#####################################################################
# in_out.py
# part of labscript_device for FPGA-SoC device by Andreas Trenkwalder
# created 18/11/2024 by Andi
# last change 18/11/2024 by Andi
#####################################################################

import numpy as np
from labscript import LabscriptError
from .shared import use_prelim_version

if use_prelim_version:
    # input control register
    CTRL_IN_SRC_BITS = 6
    CTRL_IN_SRC_MASK = (1 << CTRL_IN_SRC_BITS) - 1;

    # bit mask for all possible sources
    CTRL_IN_SRC_ALL  = (1<<64)-1
    # bit mask for possible sources for start and restart trigger
    # only first NUM_SRC_TRG_START sources are allowed.
    NUM_SRC_TRG_START = 13
    CTRL_IN_SRC_START = (1<<NUM_SRC_TRG_START)-1
    # bit mask for possible sources for stop trigger (all)
    CTRL_IN_SRC_STOP  = CTRL_IN_SRC_ALL
    # bit mask for data sources
    CTRL_IN_SRC_NONE  = 0
    CTRL_IN_SRC_DATA  = (((1<<32)-1) << 32) | (1 << CTRL_IN_SRC_NONE);

    # input sources
    # dict with key = source names, value = bit number
    IN_SRC_NONE = IN_SRC_DEFAULT = 'None'
    STR_INPUT_0         = 'input 0'
    STR_INPUT_1         = 'input 1'
    STR_INPUT_2         = 'input 2'
    STR_INV             = ' inverted'
    STR_RISING          = ' rising'
    STR_FALLING         = ' falling'
    in_sources = {IN_SRC_NONE               : CTRL_IN_SRC_NONE,
                  STR_INPUT_0               : 1,
                  STR_INPUT_0 + STR_INV     : 2,
                  STR_INPUT_0 + STR_RISING  : 3,
                  STR_INPUT_0 + STR_FALLING : 4,
                  STR_INPUT_1               : 5,
                  STR_INPUT_1 + STR_INV     : 6,
                  STR_INPUT_1 + STR_RISING  : 7,
                  STR_INPUT_1 + STR_FALLING : 8,
                  STR_INPUT_2               : 9,
                  STR_INPUT_2 + STR_INV     : 10,
                  STR_INPUT_2 + STR_RISING  : 11,
                  STR_INPUT_2 + STR_FALLING : 12,
                  #'logic A AND'             : 13,
                  #'logic A OR'              : 14,
                  #'logic A XOR'             : 15,
                  #'logic A NAND'            : 16,
                  #'logic A NOR'             : 17,
                  #'logic A XNOR'            : 18,
                  #'logic B AND'             : 19,
                  #'logic B OR'              : 20,
                  #'logic B XOR'             : 21,
                  #'logic B NAND'            : 22,
                  #'logic B NOR'             : 23,
                  #'logic B XNOR'            : 24,
                  'data bit 0'              : 32,
                  'data bit 1'              : 33,
                  'data bit 2'              : 34,
                  'data bit 3'              : 35,
                  'data bit 4'              : 36,
                  'data bit 5'              : 37,
                  'data bit 6'              : 38,
                  'data bit 7'              : 39,
                  'data bit 8'              : 40,
                  'data bit 9'              : 41,
                  'data bit 10'             : 42,
                  'data bit 11'             : 43,
                  'data bit 12'             : 44,
                  'data bit 13'             : 45,
                  'data bit 14'             : 46,
                  'data bit 15'             : 47,
                  'data bit 16'             : 48,
                  'data bit 17'             : 49,
                  'data bit 18'             : 50,
                  'data bit 19'             : 51,
                  'data bit 20'             : 52,
                  'data bit 21'             : 53,
                  'data bit 22'             : 54,
                  'data bit 23'             : 55,
                  'data bit 24'             : 56,
                  'data bit 25'             : 57,
                  'data bit 26'             : 58,
                  'data bit 27'             : 59,
                  'data bit 28'             : 60,
                  'data bit 29'             : 61,
                  'data bit 30'             : 62,
                  'data bit 31'             : 63,
                  }

    # input destinations
    # dict with key = destination, value = (register, offset, bit mask of sources)
    STR_TRIG_START      = 'trigger start'
    STR_TRIG_STOP       = 'trigger stop'
    STR_TRIG_RESTART    = 'trigger restart'
    STR_BIT_NOP         = 'bit NOP'
    STR_BIT_IRQ         = 'bit IRQ'
    STR_BIT_STRB        = 'bit STRB'
    #STR_LOGIC_A0        = 'logic A input 0'
    #STR_LOGIC_A1        = 'logic A input 1'
    #STR_LOGIC_B0        = 'logic B input 0'
    #STR_LOGIC_B1        = 'logic B input 1'
    # (register, offset, mask)
    in_dests = {STR_TRIG_START      : (0, 0, CTRL_IN_SRC_START),
                STR_TRIG_STOP       : (0, 1, CTRL_IN_SRC_STOP),
                STR_TRIG_RESTART    : (0, 2, CTRL_IN_SRC_START),
                #STR_LOGIC_A0        : (0, 3, CTRL_IN_SRC_ALL),
                #STR_LOGIC_A1        : (0, 4, CTRL_IN_SRC_ALL),
                STR_BIT_NOP         : (1, 0, CTRL_IN_SRC_DATA),
                STR_BIT_IRQ         : (1, 1, CTRL_IN_SRC_DATA),
                STR_BIT_STRB        : (1, 2, CTRL_IN_SRC_DATA),
                #STR_LOGIC_B0        : (1, 3, CTRL_IN_SRC_ALL),
                #STR_LOGIC_B1        : (1, 4, CTRL_IN_SRC_ALL),
                }

    # output control register
    CTRL_OUT_SRC_BITS = 6
    CTRL_OUT_SRC_MASK = (1 << CTRL_OUT_SRC_BITS) - 1;

    # output sources
    # dict with key = source names, value = bit numbe
    CTRL_OUT_SRC_ALL    = (2**54)-1
    CTRL_OUT_SRC_BUS_EN = 0x3
    STR_LOW      = OUT_SRC_DEFAULT = 'low'
    STR_HIGH     = 'high'
    STR_SYNC_OUT = 'sync out'
    out_sources = {
                  STR_LOW                       : 0,
                  STR_HIGH                      : 1,
                  STR_SYNC_OUT                  : 2,
                  STR_SYNC_OUT + STR_INV        : 3,
                  'sync enable'                 : 4,
                  'sync enable' + STR_INV       : 5,
                  'sync monitor'                : 6,
                  'sync monitor' + STR_INV      : 7,
                  'ext clock locked'            : 8,
                  'ext clock locked' + STR_INV  : 9,
                  'ext clock enabled'           : 10,
                  'ext clock enabled' + STR_INV : 11,
                  'ext clock lost'              : 12,
                  'ext clock lost' + STR_INV    : 13,
                  'error'                       : 14,
                  'error' + STR_INV             : 15,
                  'ready'                       : 16,
                  'ready' + STR_INV             : 17,
                  'run'                         : 18,
                  'run' + STR_INV               : 19,
                  'wait'                        : 20,
                  'wait' + STR_INV              : 21,
                  'end'                         : 22,
                  'end' + STR_INV               : 23,
                  'restart'                     : 24,
                  'restart' + STR_INV           : 25,
                  STR_TRIG_START                : 26,
                  STR_TRIG_START + STR_INV      : 27,
                  STR_TRIG_STOP                 : 28,
                  STR_TRIG_STOP + STR_INV       : 29,
                  STR_TRIG_RESTART              : 30,
                  STR_TRIG_RESTART + STR_INV    : 31,
                  'strobe 0'                    : 32,
                  'strobe 0' + STR_INV          : 33,
                  'strobe 0 contiguous'         : 34,
                  'strobe 0 contiguous'+STR_INV : 35,
                  'strobe 1'                    : 36,
                  'strobe 1' + STR_INV          : 37,
                  'strobe 1 contiguous'         : 38,
                  'strobe 1 contiguous'+STR_INV : 39,
                  'IRQ TX'                      : 40,
                  'IRQ TX' + STR_INV            : 41,
                  'IRQ RX'                      : 42,
                  'IRQ RX' + STR_INV            : 43,
                  'IRQ FPGA'                    : 44,
                  'IRQ FPGA' + STR_INV          : 45,
                  'TX FIFO full'                : 46,
                  'TX FIFO full' + STR_INV      : 47,
                  'TX FIFO empty'               : 48,
                  'TX FIFO empty' + STR_INV     : 49,
                  'RX FIFO full'                : 50,
                  'RX FIFO full' + STR_INV      : 51,
                  'RX FIFO empty'               : 52,
                  'RX FIFO empty' + STR_INV     : 53,
                  }

    # output destinations
    # dict with key = destination, value = (register, offset, bit mask of sources)
    STR_OUTPUT_0    = 'output 0'
    STR_OUTPUT_1    = 'output 1'
    STR_OUTPUT_2    = 'output 2'
    STR_BUS_EN_0    = 'bus enable 0'
    STR_BUS_EN_1    = 'bus enable 1'
    STR_LED_R       = 'LED red'
    STR_LED_G       = 'LED green'
    STR_LED_B       = 'LED blue'
    # (register, offset, mask)
    out_dests = {STR_OUTPUT_0   : (0, 0, CTRL_OUT_SRC_ALL),
                 STR_OUTPUT_1   : (0, 1, CTRL_OUT_SRC_ALL),
                 STR_OUTPUT_2   : (0, 2, CTRL_OUT_SRC_ALL),
                 STR_BUS_EN_0   : (0, 3, CTRL_OUT_SRC_BUS_EN),
                 STR_BUS_EN_1   : (0, 4, CTRL_OUT_SRC_BUS_EN),
                 STR_LED_R      : (1, 0, CTRL_OUT_SRC_ALL),
                 STR_LED_G      : (1, 1, CTRL_OUT_SRC_ALL),
                 STR_LED_B      : (1, 2, CTRL_OUT_SRC_ALL),
                }

    def get_ctrl_io(user_selection, input, check=True):
        """
        returns input/output control register [0,1] values from user_selection dict.
        user_selection = dict with {dest: source} given as strings
        input = if True input selection, otherwise output selection.
        returns array of 2x 32bit trigger control register value used to configure board.
        on error returns None
        """
        if input:
            type     = 'input'
            dests    = in_dests
            sources  = in_sources
            bits     = CTRL_IN_SRC_BITS
            bit_mask = CTRL_IN_SRC_MASK
        else:
            type     = 'output'
            dests    = out_dests
            sources  = out_sources
            bits     = CTRL_OUT_SRC_BITS
            bit_mask = CTRL_OUT_SRC_MASK
        #print('get_ctrl_io', user_selection, input)
        register = np.array([0,0], dtype=np.uint32)
        for dest, source in user_selection.items():
            try:
                (reg, offset, mask) = dests[dest]
                bit = sources[source]
                if (1<<bit) & mask == 0:
                    print('mask error', bit, mask, bit & mask)
                    raise KeyError
                #print(dest, source, bit, sources[source], offset)
                register[reg] |= (bit << (offset*bits))
            except KeyError:
                raise LabscriptError("get_ctrl_io: %s source '%s' cannot be selected for destination '%s'" % (type, source, dest))
                return None
        if check: # consistency check
            sel = get_io_selection(register, input, return_NONE=False, check=False)
            for key,value in sel.items():
                if (key not in user_selection) or (user_selection[key] != value):
                    if key in user_selection:
                        print(type, '(source) =', user_selection[key])
                    else:
                        # skip default values
                        if input:
                            if value == IN_SRC_DEFAULT: continue
                        else:
                            if value == OUT_SRC_DEFAULT: continue
                        print(type, "key '%s' not existing" % (key))
                    print('output (source) =', value)
                    print('user selection:\n', user_selection, '\n-> register = 0x [%x,%x]' % (register[0], register[1]))
                    print('register = 0x [%x,%x]' % (register[0], register[1]), '\n-> selection:\n', sel)
                    raise LabscriptError("error: get_ctrl_io does not give consistent result with get_io_selection for key '%s'!" %(key))
        #sel = get_in_selection(register[0],return_NONE=False, check=False)
        #print('get_ctrl_in')
        #print(input_selection)
        #print(sel)
        #raise LabscriptError('test')
        return register

    def get_io_selection(register, input, return_NONE=False, check=True):
        """
        returns dictionary with input/output selections.
        inverse function to get_ctrl_inout.
        register    = array of 2 register values
        input       = if True input selection, otherwise output selection
        return_NONE = if True returns also IN_SRC_NONE, otherwise not.
        check = consistency check
        """
        if input:
            type     = 'input'
            dests    = in_dests
            sources  = in_sources
            disabled = CTRL_IN_SRC_NONE
            bits     = CTRL_IN_SRC_BITS
            src_mask = CTRL_IN_SRC_MASK
        else:
            type     = 'output'
            dests    = out_dests
            sources  = out_sources
            disabled = -1               # outputs cannot be disabled. default is fixed low.
            bits     = CTRL_OUT_SRC_BITS
            src_mask = CTRL_OUT_SRC_MASK
        selection = {}
        #print('get_inout_selection', register, input)
        for dest, (reg, offset, mask) in dests.items():
            source = (register[reg] >> (offset*bits)) & src_mask;
            if source == disabled:
                if return_NONE: selection[dest] = IN_SRC_NONE
                continue
            #print([dest, reg, offset, mask, source])
            for src, value in sources.items():
                if source == value:
                    if ((1 << value) & mask) == 0: # source is not enabled in mask
                        raise LabscriptError("destination '%s' source '%s' (0x%x) is not allowed!" % (dest, src, source))
                    else:
                        #print("source '%s' (0x%x)" % (src, bit))
                        selection[dest] = src
                        break
        if check: # consistency check
            reg = get_ctrl_io(selection, input, check=False);
            if (reg[0] != register[0]) or (reg[1] != register[1]):
                raise LabscriptError('get_io_selection does not give consistent result with get_ctrl_io: [%x,%x] != [%x,%x]' %(reg[0], reg[1], register[0], register[1]), selection)
        return selection

    def is_enabled(destinations, register, input, sources=None):
        """
        returns True when any of destinations is enabled in input/output control register.
        destinations = list of destination or source strings.
        register     = array of 2 register values.
        input        = if True input selection, otherwise output selection.
        source       = if None: returns True for any enabled destination.
                       if not None: list of specific sources. returns True only when these are enabled.
        """
        if input:
            type     = 'input'
            dests    = in_dests
            s_all    = in_sources
            shift    = CTRL_IN_SRC_BITS
            bit_mask = CTRL_IN_SRC_MASK
        else:
            type     = 'output'
            dests    = out_dests
            s_all    = out_sources
            shift    = CTRL_OUT_SRC_BITS
            bit_mask = CTRL_OUT_SRC_MASK
        for destination in destinations:
            (reg, offset, mask) = dests[destination]
            s_value = ((register[reg] >> (offset*shift)) & bit_mask)
            if sources is None:
                if s_value != 0: return True
            else:
                for s in sources:
                    if not s in s_all: raise LabscriptError("is_enabled source '%s' is not a valid %s source!" % (s, type))
                    if s_value == s: return True
        return False

else:
    # input control register
    CTRL_IN_SRC_BITS = 3
    CTRL_IN_LEVEL_BITS = 2
    CTRL_IN_DST_BITS = (CTRL_IN_SRC_BITS + CTRL_IN_LEVEL_BITS)
    CTRL_IN_SRC_MASK = (1 << CTRL_IN_SRC_BITS) - 1;
    CTRL_IN_LEVEL_MASK = (1 << CTRL_IN_LEVEL_BITS) - 1;
    CTRL_IN_DST_MASK = (1 << CTRL_IN_DST_BITS) - 1;

    # input destination offsets
    CTRL_IN_DST_START = 0 * CTRL_IN_DST_BITS  # start trigger
    CTRL_IN_DST_STOP = 1 * CTRL_IN_DST_BITS  # stop trigger
    CTRL_IN_DST_RESTART = 2 * CTRL_IN_DST_BITS  # restart trigger
    # TODO: firmware uses parameters given at compile time.
    #       these tell the software which bits to generate but no cross-checking is done.
    #       either read from firmare directly or allow to modify firmware values (NOP is difficult).
    #       BIT_IRQ is also missing here but no space left.
    CTRL_IN_DST_DATA_NOP = 3 * CTRL_IN_DST_BITS  # data NOP bit (must be 31)
    CTRL_IN_DST_DATA_STRB = 4 * CTRL_IN_DST_BITS  # data strobe bit (default 23)
    CTRL_IN_DST_DATA_STOP = 5 * CTRL_IN_DST_BITS  # data STOP bit (default 28)

    # input sources
    CTRL_IN_SRC_NONE = 0  # no trigger input
    CTRL_IN_SRC_IN0 = 1  # ext_in[0]
    CTRL_IN_SRC_IN1 = 2  # ext_in[1]
    CTRL_IN_SRC_IN2 = 3  # ext_in[2]
    CTRL_IN_SRC_DATA_20 = 4  # data bits 20-23
    CTRL_IN_SRC_DATA_24 = 5  # data bits 24-27
    CTRL_IN_SRC_DATA_28 = 6  # data bits 28-31 # TODO: firmware uses only this!
    CTRL_IN_SRC_DATA_START = CTRL_IN_SRC_DATA_20  # first data bit source
    CTRL_IN_SRC_IN_ALL = (1 << CTRL_IN_SRC_NONE) | (1 << CTRL_IN_SRC_IN0) | (1 << CTRL_IN_SRC_IN1) | (
                1 << CTRL_IN_SRC_IN2)
    CTRL_IN_SRC_DATA_ALL = (1 << CTRL_IN_SRC_NONE) | (1 << CTRL_IN_SRC_DATA_20) | (1 << CTRL_IN_SRC_DATA_24) | (
                1 << CTRL_IN_SRC_DATA_28)
    CTRL_IN_SRC_ALL = CTRL_IN_SRC_IN_ALL | CTRL_IN_SRC_DATA_ALL

    # input levels
    CTRL_IN_LEVEL_LOW = 0  # level low
    CTRL_IN_LEVEL_HIGH = 1  # level higth
    CTRL_IN_EDGE_FALLING = 2  # edge falling
    CTRL_IN_EDGE_RISING = 3  # edge rising
    # data bits offset. in register are same bits as input levels.
    # to distinguish the names we add CTRL_IN_DATA_OFFSET which in register is masked out with CTRL_IN_LEVEL_MASK
    CTRL_IN_DATA_OFFSET = (1 << CTRL_IN_LEVEL_BITS)
    CTRL_IN_DATA_0 = 0 | CTRL_IN_DATA_OFFSET  # offset bit 0
    CTRL_IN_DATA_1 = 1 | CTRL_IN_DATA_OFFSET  # offset bit 1
    CTRL_IN_DATA_2 = 2 | CTRL_IN_DATA_OFFSET  # offset bit 2
    CTRL_IN_DATA_3 = 3 | CTRL_IN_DATA_OFFSET  # offset bit 3
    CTRL_IN_LVL_IN_ALL = (1 << CTRL_IN_LEVEL_LOW) | (1 << CTRL_IN_LEVEL_HIGH) | (1 << CTRL_IN_EDGE_FALLING) | (
                1 << CTRL_IN_EDGE_RISING)
    CTRL_IN_LVL_DATA_ALL = (1 << CTRL_IN_DATA_0) | (1 << CTRL_IN_DATA_1) | (1 << CTRL_IN_DATA_2) | (1 << CTRL_IN_DATA_3)
    CTRL_IN_LVL_ALL = CTRL_IN_LVL_IN_ALL | CTRL_IN_LVL_DATA_ALL

    # define inputs list for user to select in GUI. for sources/levels give True for default selection
    # source=can be connected to several destinations. dest can be only connected to one source. source can be None, dest not.
    # for in_dests values give (start offset, source_enable_bits, level_enable_bits)
    # with enable bits = 1 for each enabled source or level option (use 1<<option).
    # if nothing enabled destination is not displayed, if only one enabled destination is grayed.
    IN_SRC_NONE = 'None'
    STR_TRIG_START = 'start trigger'
    STR_TRIG_STOP = 'stop trigger'
    STR_TRIG_RESTART = 'restart trigger'
    STR_BIT_NOP = 'NOP bit'
    STR_BIT_STRB = 'STRB bit'
    STR_BIT_STOP = 'STOP bit'
    STR_INPUT_0 = 'input 0'
    STR_INPUT_1 = 'input 1'
    STR_INPUT_2 = 'input 2'
    STR_BIT_DATA_20_23 = 'data bits 20-23'
    STR_BIT_DATA_24_27 = 'data bits 24-27'
    STR_BIT_DATA_28_31 = 'data bits 28-31'
    STR_RISING = 'rising edge'
    STR_FALLING = 'falling edge'
    STR_LEVEL_HIGH = 'high level'
    STR_LEVEL_LOW = 'low level'
    STR_BIT_OFFSET_0 = 'offset bit 0'
    STR_BIT_OFFSET_1 = 'offset bit 1'
    STR_BIT_OFFSET_2 = 'offset bit 2'
    STR_BIT_OFFSET_3 = 'offset bit 3'
    # imported but not needed
    STR_INV = None
    STR_OUTPUT_0 = None
    STR_OUTPUT_1 = None
    STR_OUTPUT_2 = None
    STR_LED_R = None
    STR_LED_G = None
    STR_LED_B = None
    in_dests = {STR_TRIG_START: (CTRL_IN_DST_START, CTRL_IN_SRC_IN_ALL, CTRL_IN_LVL_IN_ALL),
                STR_TRIG_STOP: (CTRL_IN_DST_STOP, CTRL_IN_SRC_ALL, CTRL_IN_LVL_ALL),
                STR_TRIG_RESTART: (CTRL_IN_DST_RESTART, CTRL_IN_SRC_IN_ALL, CTRL_IN_LVL_IN_ALL),
                STR_BIT_NOP: (CTRL_IN_DST_DATA_NOP, 1 << CTRL_IN_SRC_DATA_28, 1 << CTRL_IN_DATA_3),
                STR_BIT_STRB: (CTRL_IN_DST_DATA_STRB, CTRL_IN_SRC_DATA_ALL, CTRL_IN_LVL_DATA_ALL),
                STR_BIT_STOP: (CTRL_IN_DST_DATA_STOP, CTRL_IN_SRC_DATA_ALL, CTRL_IN_LVL_DATA_ALL)}
    in_sources = {IN_SRC_NONE: CTRL_IN_SRC_NONE,
                  STR_INPUT_0: CTRL_IN_SRC_IN0,
                  STR_INPUT_1: CTRL_IN_SRC_IN1,
                  STR_INPUT_2: CTRL_IN_SRC_IN2,
                  STR_BIT_DATA_20_23: CTRL_IN_SRC_DATA_20,
                  STR_BIT_DATA_24_27: CTRL_IN_SRC_DATA_24,
                  STR_BIT_DATA_28_31: CTRL_IN_SRC_DATA_28}
    in_levels = {STR_RISING     : CTRL_IN_EDGE_RISING,
                 STR_FALLING    : CTRL_IN_EDGE_FALLING,
                 STR_LEVEL_HIGH : CTRL_IN_LEVEL_HIGH,
                 STR_LEVEL_LOW  : CTRL_IN_LEVEL_LOW,
                 STR_BIT_OFFSET_0: CTRL_IN_DATA_0,
                 STR_BIT_OFFSET_1: CTRL_IN_DATA_1,
                 STR_BIT_OFFSET_2: CTRL_IN_DATA_2,
                 STR_BIT_OFFSET_3: CTRL_IN_DATA_3}

    def get_ctrl_in(input_selection,check=True):
        """
        returns input control register value from input_selection.
        input_selection = {dest:(source, level)),dest:(source, level),...}
        dest = key from in_dests. missing destinations are considered as not used.
        source = key from in_sources.
        level = key from in_levels.
        returns 32bit trigger control register value used to configure board.
        """
        register = np.array([0],dtype=np.uint32)
        for dest, value in input_selection.items():
            source, level = value
            register[0] |= (in_sources[source]|((in_levels[level] & CTRL_IN_LEVEL_MASK)<<CTRL_IN_SRC_BITS))<<in_dests[dest][0]
        if check: # consistency check
            sel = get_in_selection(register[0],return_NONE=False, check=False)
            for key,value in sel.items():
                if (key not in input_selection) or (input_selection[key][0] != value[0]) or (input_selection[key][1] != value[1]):
                    if key in input_selection:
                        save_print('input (source, level) =', input_selection[key])
                    else:
                        save_print('input key %s not existing' % (key))
                    save_print('output (source, level) =', value)
                    print('input selection:\n', input_selection, '\n-> value = 0x%x' % (register[0]))
                    print('value = 0x%x' % register[0], '\n-> input selection:\n', sel)
                    raise LabscriptError("error: get_ctrl_in does not give consistent result with get_in_selection for key '%s'!" %(key))
        #sel = get_in_selection(register[0],return_NONE=False, check=False)
        #print('get_ctrl_in')
        #print(input_selection)
        #print(sel)
        #raise LabscriptError('test')
        return register[0]

    def get_in_selection(register, return_NONE=True, check=True):
        """
        returns dictionary with input selections.
        inverse function to get_ctrl_in.
        if return_NONE == True returns also IN_SRC_NONE, otherwise not.
        """
        selection = {}
        for dest, dest_offset in in_dests.items():
            offset, source_enable_bits, level_enable_bits = dest_offset
            reg_dest = (register >> offset) & CTRL_IN_DST_MASK;
            if reg_dest == 0: continue
            reg_src = reg_dest & CTRL_IN_SRC_MASK
            reg_lvl = (reg_dest >> CTRL_IN_SRC_BITS) & CTRL_IN_LEVEL_MASK
            #print(dest, 'dest bits:', reg_dest, 'source bits', reg_src ,'level bits', reg_lvl)
            for src, src_bits in in_sources.items():
                if (source_enable_bits & (1 << src_bits)) != 0: # source enabled
                    if return_NONE or (src_bits != CTRL_IN_SRC_NONE):
                        if reg_src == src_bits:
                            #print('source %s (0x%x)' % (src, src_bits))
                            for level, level_bits in in_levels.items():
                                if (level_enable_bits & (1 << level_bits)) != 0:  # level enabled
                                    if src_bits >= CTRL_IN_SRC_DATA_START and (level_bits & CTRL_IN_DATA_OFFSET) == 0: continue
                                    if reg_lvl == (level_bits & CTRL_IN_LEVEL_MASK):
                                        #print('level %s (0x%x)' % (level, level_bits))
                                        selection[dest] = (src,level)
                                        break
                            if dest not in selection:
                                raise LabscriptError("could not find level for %s! register 0x%x" % (dest, register))
                            break
        if check and (get_ctrl_in(selection) != register): # consistency check
            raise LabscriptError('error: get_in_selection does not give consistent result with get_ctrl_in: %x != %x' %(get_ctrl_in(selection), register), selection)
        return selection

    def is_in_start(ctrl_trg):
        "returns True when start trigger is enabled in trigger control register ctrl_trg"
        return (((ctrl_trg >> CTRL_IN_DST_START) & CTRL_IN_SRC_MASK) != CTRL_IN_SRC_NONE)

    def is_in_stop(ctrl_trg):
        "returns True when stop trigger is enabled in trigger control register ctrl_trg"
        return (((ctrl_trg >> CTRL_IN_DST_STOP) & CTRL_IN_SRC_MASK) != CTRL_IN_SRC_NONE)

    def is_in_restart(ctrl_trg):
        "returns True when restart trigger is enabled in trigger control register ctrl_trg"
        return (((ctrl_trg >> CTRL_IN_DST_RESTART) & CTRL_IN_SRC_MASK) != CTRL_IN_SRC_NONE)

    def get_in_info(ctrl_trg):
        "returns short info string with trigger selections"
        info = []
        if is_in_start(ctrl_trg)    : info += ['start']
        if is_in_stop(ctrl_trg)     : info += ['stop']
        if is_in_restart(ctrl_trg)  : info += ['restart']
        if len(info) > 0: return "(" + "|".join(info) + ")"
        else:             return ""

    # output control register
    CTRL_OUT_SRC_BITS           = 4
    CTRL_OUT_LEVEL_BITS         = 2
    CTRL_OUT_DST_BITS           = CTRL_OUT_SRC_BITS + CTRL_OUT_LEVEL_BITS
    CTRL_OUT_SRC_MASK           = (1<<CTRL_OUT_SRC_BITS)-1;
    CTRL_OUT_LEVEL_MASK         = (1<<CTRL_OUT_LEVEL_BITS)-1;
    CTRL_OUT_DST_MASK           = (1<<CTRL_OUT_DST_BITS)-1;

    # output destinations offsets
    CTRL_OUT_DST_OUT0           = 0*CTRL_OUT_DST_BITS   # ext_out[0]
    CTRL_OUT_DST_OUT1           = 1*CTRL_OUT_DST_BITS   # ext_out[1]
    CTRL_OUT_DST_OUT2           = 2*CTRL_OUT_DST_BITS   # ext_out[2]
    CTRL_OUT_DST_BUS_EN0        = 3*CTRL_OUT_DST_BITS   # out_en[0]
    CTRL_OUT_DST_BUS_EN1        = 4*CTRL_OUT_DST_BITS   # out_en[1]

    # output sources
    CTRL_OUT_SRC_NONE           = 0                 # fixed output at given level
    CTRL_OUT_SRC_SYNC_OUT       = 1                 # sync_out
    CTRL_OUT_SRC_SYNC_EN        = 2                 # sync_en
    CTRL_OUT_SRC_SYNC_MON       = 3                 # sync_mon
    CTRL_OUT_SRC_CLK_LOST       = 4                 # clock loss
    CTRL_OUT_SRC_ERROR          = 5                 # error
    CTRL_OUT_SRC_RUN            = 6                 # run (or wait)
    CTRL_OUT_SRC_WAIT           = 7                 # wait (high only when run bit reset)
    CTRL_OUT_SRC_READY          = 8                 # ready
    CTRL_OUT_SRC_RESTART        = 9                 # restart toggle bit in cycling mode
    CTRL_OUT_SRC_TRG_START      = 10                # toggles with start trigger
    CTRL_OUT_SRC_TRG_STOP       = 11                # toggles with stop trigger
    CTRL_OUT_SRC_TRG_RESTART    = 12                # toggles with restart trigger
    CTRL_OUT_SRC_ALL            = (1<<CTRL_OUT_SRC_NONE)|(1<<CTRL_OUT_SRC_SYNC_OUT)|(1<<CTRL_OUT_SRC_SYNC_EN)|(1<<CTRL_OUT_SRC_SYNC_MON)|\
                                  (1<<CTRL_OUT_SRC_CLK_LOST)|(1<<CTRL_OUT_SRC_ERROR)|\
                                  (1<<CTRL_OUT_SRC_RUN)|(1<<CTRL_OUT_SRC_WAIT)|(1<<CTRL_OUT_SRC_READY)|(1<<CTRL_OUT_SRC_RESTART)|\
                                  (1<<CTRL_OUT_SRC_TRG_START)|(1<<CTRL_OUT_SRC_TRG_STOP)|(1<<CTRL_OUT_SRC_TRG_RESTART)

    # output levels
    CTRL_OUT_LEVEL_LOW          = 0                 # level active low = inverted
    CTRL_OUT_LEVEL_HIGH         = 1                 # level active high = normal
    CTRL_OUT_LVL_ALL            = (1<<CTRL_OUT_LEVEL_LOW)|(1<<CTRL_OUT_LEVEL_HIGH)

    # define output list for user to select in GUI. for sources/levels give True for default selection
    # source=can be connected to several destinations. dest can be only connected to one source. source can be None, dest not.
    # for out_dests values give (start offset, source_enable_bits, level_enable_bits)
    # with enable bits = 1 for each enabled source or level option (use 1<<option).
    # if nothing enabled destination is not displayed, if only one enabled destination is grayed.
    # TODO: define string constants as for inputs...
    OUT_SRC_NONE   = 'fixed'
    STR_SYNC_OUT   = 'sync out'
    out_dests   = {   'output 0'        : (CTRL_OUT_DST_OUT0, CTRL_OUT_SRC_ALL, CTRL_OUT_LVL_ALL),
                      'output 1'        : (CTRL_OUT_DST_OUT1, CTRL_OUT_SRC_ALL, CTRL_OUT_LVL_ALL),
                      'output 2'        : (CTRL_OUT_DST_OUT2, CTRL_OUT_SRC_ALL, CTRL_OUT_LVL_ALL),
                      'bus enable 0'    : (CTRL_OUT_DST_BUS_EN0, CTRL_OUT_SRC_ALL, CTRL_OUT_LVL_ALL),
                      'bus enable 1'    : (CTRL_OUT_DST_BUS_EN1, CTRL_OUT_SRC_ALL, CTRL_OUT_LVL_ALL)}
    out_sources = {   OUT_SRC_NONE      : CTRL_OUT_SRC_NONE,
                      STR_SYNC_OUT      : CTRL_OUT_SRC_SYNC_OUT,
                      'sync en'         : CTRL_OUT_SRC_SYNC_EN,
                      'sync mon'        : CTRL_OUT_SRC_SYNC_MON,
                      'clock lost'      : CTRL_OUT_SRC_CLK_LOST,
                      'error'           : CTRL_OUT_SRC_ERROR,
                      'run'             : CTRL_OUT_SRC_RUN,
                      'wait'            : CTRL_OUT_SRC_WAIT,
                      'ready'           : CTRL_OUT_SRC_READY,
                      'restart'         : CTRL_OUT_SRC_RESTART,
                      'trig. start'     : CTRL_OUT_SRC_TRG_START,
                      'trig. stop'      : CTRL_OUT_SRC_TRG_STOP,
                      'trig. restart'   : CTRL_OUT_SRC_TRG_RESTART,
                      }
    out_levels  = {   STR_LEVEL_LOW     : CTRL_OUT_LEVEL_LOW,
                      STR_LEVEL_HIGH    : CTRL_OUT_LEVEL_HIGH}

    def get_ctrl_out(output_selection):
        """
        returns output control register value from output_selection.
        output_selection = dictionary key = output and value = (source,level) with
        output = key from out_dests. missing outputs are considered as not used.
        source = key from out_sources.
        level = key from out_levels.
        returns 32bit output control register value used to configure board.
        """
        register = np.array([0],dtype=np.uint32)
        for dest, value in output_selection.items():
            source, level = value
            register[0] |= (out_sources[source]|(out_levels[level]<<CTRL_OUT_SRC_BITS))<<out_dests[dest][0]
        return register[0]

    def get_out_selection(register, return_NONE=True):
        """
        returns dictionary with output selections.
        inverse function to get_ctrl_out.
        if return_NONE == True returns also OUT_SRC_NONE, otherwise not.
        """
        selection = {}
        for dest, dest_offset in out_dests.items():
            reg_dest = (register >> dest_offset[0]) & CTRL_OUT_DST_MASK;
            for src, src_bits in out_sources.items():
                if return_NONE or (src_bits != CTRL_OUT_SRC_NONE):
                    if (reg_dest & CTRL_OUT_SRC_MASK) == src_bits:
                        for level, level_bits in out_levels.items():
                            if ((reg_dest >> CTRL_OUT_SRC_BITS) & CTRL_OUT_LEVEL_MASK) == level_bits:
                                selection[dest] = (src,level)
                                break
                        break
        if get_ctrl_out(selection) != register: # consistency check
            save_print('error: get_out_selection does not give consistent result with get_ctrl_out: %x != %x' %(get_ctrl_out(selection), register), selection)
            exit()
        return selection

    def is_sync_out(ctrl_out):
        "returns True when sync_out is enabled in output control register ctrl_out"
        for dest, dest_offset in out_dests.items():
            if (((ctrl_out >> dest_offset[0]) & CTRL_OUT_SRC_MASK) == CTRL_OUT_SRC_SYNC_OUT): return True
        return False

    def get_out_info(ctrl_out):
        "returns short info string with output selections"
        info = []
        if is_sync_out(ctrl_out):   info += ['sync out']
        if len(info) > 0: return "(" + "|".join(info) + ")"
        else:             return ""

    # alias of newer functions
    def get_ctrl_io(selection, input, check=True):
        if input: return get_ctrl_in(selection, check=check)
        else:     return get_ctrl_out(selection, check=check)
    def get_io_selection(register, input, return_NONE=True, check=True):
        if input: return get_in_selection(register, return_NONE=return_None, check=check)
        else:     return get_out_selection(register, return_NONE=True, check=True)
    def is_enabled(destinations, register, input, sources=None):
        en = False
        for destination in destinations:
            if sources is None:
                if   input and (destination == STR_TRIG_START  )  : en |= is_in_start  (register)
                elif input and (destination == STR_TRIG_STOP   )  : en |= is_in_stop   (register)
                elif input and (destination == STR_TRIG_RESTART)  : en |= is_in_restart(register)
                else:
                    raise LabScriptError("is_enabled '%s' with input=%s not implemented!" % (destination, str(input)))
            else:
                if input: raise LabscriptError("is_enabled with sources can be used only on outputs!")
                for s in sources:
                    if not s in out_sources: raise LabscriptError("is_enabled source '%s' is not a valid output source!" % (s))
                    if (s == STR_SYNC_OUT) or (s == STR_SYNC_OUT + STR_INV): en |= is_sync_out(register)
                    else: raise LabScriptError("is_enabled source=%s not implemented!" % (s))
        return en

def get_io_info(register, input):
    "returns short info string with input/output selections"
    info = []
    if input:
        if is_enabled([STR_TRIG_START  ], register, input=True): info += ['start']
        if is_enabled([STR_TRIG_STOP   ], register, input=True): info += ['stop']
        if is_enabled([STR_TRIG_RESTART], register, input=True): info += ['restart']
        if is_enabled([STR_BIT_NOP     ], register, input=True): info += ['NOP']
        if is_enabled([STR_BIT_IRQ     ], register, input=True): info += ['IRQ']
        if is_enabled([STR_BIT_STRB    ], register, input=True): info += ['STRB']
    else:
        if is_enabled(list(out_dests.keys()), register, input=False, sources=[STR_SYNC_OUT, STR_SYNC_OUT + STR_INV]): info += ['sync out']
        if is_enabled([STR_OUTPUT_0], register, input=False): info += ['out 0']
        if is_enabled([STR_OUTPUT_1], register, input=False): info += ['out 1']
        if is_enabled([STR_OUTPUT_2], register, input=False): info += ['out 2']
    if len(info) > 0:
        return "(" + "|".join(info) + ")"
    else:
        return ""
