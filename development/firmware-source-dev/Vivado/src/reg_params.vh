// reg_params.vh
// register map for dio24.v module
// created 3/12/2024 by Andi
// last change 3/12/2024 by Andi

    // register indices
    parameter integer REG_CTRL              = 0;    // index of control register 
    parameter integer REG_CTRL_IN0          = 4;    // index of input control register 0
    parameter integer REG_CTRL_IN1          = 5;    // index of input control register 1
    parameter integer REG_CTRL_OUT0         = 8;    // index of output control register 0
    parameter integer REG_CTRL_OUT1         = 9;    // index of output control register 1
    parameter integer REG_CLK_DIV           = 12;   // index of clk_div register
    parameter integer REG_STRB_DELAY        = 13;   // index of strb_delay register
    parameter integer REG_NUM_SAMPLES       = 16;   // index of num_samples register
    parameter integer REG_NUM_CYCLES        = 17;   // index of num_cycles register
    parameter integer REG_SYNC_DELAY        = 24;   // index of sync_delay register      
    parameter integer REG_SYNC_PHASE        = 25;   // index of sync_phase register
    parameter integer REG_FORCE_OUT         = 30;   // index of force_out register
    
    parameter integer REG_STATUS            = 32;   // index of status register
    parameter integer REG_BOARD_TIME_0      = 36;   // index of board time 0 register
    parameter integer REG_BOARD_TIME_1      = 37;   // index of board time 1 register
    parameter integer REG_SYNC_TIME         = 38;   // index of sync time register
    parameter integer REG_BOARD_SAMPLES_0   = 40;   // index of board samples 0 register
    parameter integer REG_BOARD_SAMPLES_1   = 41;   // index of board samples 1 register
    parameter integer REG_BOARD_CYCLES      = 44;   // index of board cycles register
    parameter integer REG_BUS_INFO          = 48;   // index of bus_info register
    parameter integer REG_VERSION           = 60;   // index of version register
    parameter integer REG_INFO              = 61;   // index of info regiser
    
    // number of control and status registers 
    parameter integer NUM_CTRL              = 32;   // number of control registers (must match AXI slave)
    
    // number of bytes per register
    parameter integer REG_NUM_BYTES         = 4;

    // control register bits
    parameter integer CTRL_RESET            = 0;       // manual reset (active high), auto-reset after 1 cycle
    parameter integer CTRL_READY            = 1;       // ready bit set by device open/close to indicate server startup
    parameter integer CTRL_RUN              = 2;       // run bit
    // 3 = end bit in status
    parameter integer CTRL_RESTART_EN       = 4;       // restart enable bit
    parameter integer CTRL_AUTO_SYNC_EN     = 5;       // auto-sync enable bit. if set detect start trigger @ clk_det and wait sync_delay, otherwise detect @ clk_bus and no wait.
    parameter integer CTRL_AUTO_SYNC_PRIM   = 6;       // auto-sync primary board.
    // 7 = phase shift active
    parameter integer CTRL_BPS96            = 8;       // if 1 data format = 96bits per samples
    parameter integer CTRL_BPS96_BRD_1      = 9;       // if CTRL_BPS96: 0 = board 0, 1=board 1 i.e. use DATA_START_0/1
    parameter integer CTRL_CLK_EXT          = 10;      // 0 = internal clock, 1 = external clock
    // 11 = external clock locked
    // 12-18 = error bits in status
    parameter integer CTRL_ERR_LOCK_EN      = 15;      // if set enable error on external lock lost, otherwise continue with internal clock. IRQ_ERR will be still generated.
    // 19 = free 
    parameter integer CTRL_IRQ_EN           = 20;      // 1 = enable all irq output
    parameter integer CTRL_IRQ_END_EN       = 21;      // 1 = enable irq output when in end state
    parameter integer CTRL_IRQ_RESTART_EN   = 22;      // 1 = enable irq output for each restart
    parameter integer CTRL_IRQ_FREQ_EN      = 23;      // 1 = enable irq with IRQ_FREQ frequency
    parameter integer CTRL_IRQ_DATA_EN      = 24;      // 1 = enable irq with BIT_IRQ
    // 27-29 = free
    // 30-31 = buttons in status
    
    // combined control bits
    parameter integer CTRL_ERR_ALL  = (1<<CTRL_ERR_LOCK_EN);
    parameter integer CTRL_IRQ_ALL  = (1<<CTRL_IRQ_EN) | (1<<CTRL_IRQ_END_EN) | (1<<CTRL_IRQ_RESTART_EN) | (1<<CTRL_IRQ_FREQ_EN) | (1<<CTRL_IRQ_DATA_EN); 
    
    // status register bits
    // general
    parameter integer STATUS_RESET          =  0;   // 1 = reset is active
    parameter integer STATUS_READY          =  1;   // 1 = ready = first data received and not finished
    parameter integer STATUS_RUN            =  2;   // 1 = running (or waiting)
    parameter integer STATUS_END            =  3;   // 1 = finished = num_samples generated without error
    parameter integer STATUS_WAIT           =  4;   // 1 = waiting for restart trigger
    // phase shift
    parameter integer STATUS_AUTO_SYNC      =  5;   // 1 = auto sync active
    parameter integer STATUS_AS_TIMEOUT     =  6;   // 1 = auto sync timeout
    parameter integer STATUS_PS_ACTIVE      =  7;   // 1 = phase shift active
    // TX/RX FIFO full
    parameter integer STATUS_TX_FULL        =  8;   // 1 = TX FIFO full
    parameter integer STATUS_RX_FULL        =  9;   // 1 = RX FIFO full
    // clock
    parameter integer STATUS_CLK_EXT        = 10;   // actual selected clock: 0 = internal clock, 1 = external clock
    parameter integer STATUS_CLK_EXT_LOCKED = 11;   // external clock locked
    // error
    parameter integer STATUS_ERR_IN         = 12;   // input error
    parameter integer STATUS_ERR_OUT        = 13;   // output error
    parameter integer STATUS_ERR_TIME       = 14;   // time error
    parameter integer STATUS_ERR_LOCK       = 15;   // external lock lost
    parameter integer STATUS_ERR_TKEEP      = 16;   // in_keep signal error
    // irq
    parameter integer STATUS_IRQ_ERROR      = 20;   // irq error active
    parameter integer STATUS_IRQ_END        = 21;   // irq end active
    parameter integer STATUS_IRQ_RESTART    = 22;   // irq restart active
    parameter integer STATUS_IRQ_FREQ       = 23;   // irq from IRQ_FREQ or IRQ_DATA
    parameter integer STATUS_IRQ_DATA       = 24;   // irq from IRQ_FREQ or IRQ_DATA
    // trigger state
    parameter integer STATUS_TRG_START      = 28;   // start trigger input
    parameter integer STATUS_TRG_STOP       = 29;   // stop trigger input
    // buttons state
    parameter integer STATUS_BTN_0          = 30;   // button 0
    parameter integer STATUS_BTN_1          = 31;   // button 1

    // combined status bits
    parameter integer STATUS_ERR_ALL        = (1<<STATUS_ERR_IN) | (1<<STATUS_ERR_OUT) | (1<<STATUS_ERR_TIME) | (1<<STATUS_ERR_LOCK) | (1<<STATUS_ERR_TKEEP);
    parameter integer STATUS_IRQ_ALL        = (1<<STATUS_IRQ_ERROR) | (1<<STATUS_IRQ_END) | (1<<STATUS_IRQ_RESTART) | (1<<STATUS_IRQ_FREQ) | (1<<STATUS_IRQ_DATA);
