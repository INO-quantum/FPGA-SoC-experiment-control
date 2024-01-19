////////////////////////////////////////////////////////////////////////////////////////////////////
// dio24_driver.h
// public header for dio24 kernel module
// compiled with g++ on Ubuntu 18.04 LTS
// tested with Petalinux 2017.4
// created September 2018 by Andi
// last change 2023/06/13 by Andi
////////////////////////////////////////////////////////////////////////////////////////////////////

#ifndef DIO24_DRIVER_HEADER
#define DIO24_DRIVER_HEADER

#ifdef _WIN32
#include <stdint.h>                                         // uint32_t, etc.
#endif

/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
// driver specific
/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

#define DIO24_DRIVER_NAME               "dio24"                                 // driver name
#define DIO24_DEVICE_NAME               "dio24dev"                              // DIO device name (read FPGA status and time)
#define DIO24_DEVICE_FILE_NAME(x)       "/dev/" DIO24_DEVICE_NAME #x            // device x=0,1,... file name
#define DMA24_DEVICE_NAME               "dma24dev"                              // DMA device name (write/read samples)
#define DMA24_DEVICE_FILE_NAME(x)       "/dev/" DMA24_DEVICE_NAME #x            // device x=0,1,... file name
#define DIO24_MAGIC_NUM                 0x4C464154                              // FPGA magic number LFAT = Lens/Firenze/AT
#define DMA24_MAGIC_NUM                 (DIO24_MAGIC_NUM+1)                     // DMA magic number

/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
// errors and warnings
/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

// warnings (must be >0)
#define WARN_NO_DATA            1                   // no input data
#define WARN_NOT_ENABLED        2                   // command not enabled
#define WARN_ALREADY_DONE       3                   // command already done
#define WARN_ALL_ACTIVE         4                   // cannot prepare descriptors since all active
#define WARN_OVERWRITE          5                   // prepare_RX_dsc overwrites oldest buffers
#define WARN_REALLOC            6                   // prepare_RX_dsc realloccated new buffers
#define WARN_TIMEOUT            7                   // stop_TX/RX timeout occured and reset_TX/RX called successfully
#define WARN_NOT_IDLE           8                   // stop_TX/RX was not idle but could be stopped
#define WARN_DEBUG              666                 // debug warning

// error codes given by errno if read/write returns -1
#define ERROR_NO_DATA           ENODATA             //  61: no buffers prepared for start_TX/RX
#define ERROR_DMA_INACTIVE      EWOULDBLOCK         //  11: read: DMA not running and no data available (same as EAGAIN)
#define ERROR_FPGA_INACTIVE     EBUSY               //  16: read: FPGA not running and no data available
#define ERROR_TIMEOUT           ETIMEDOUT           // 110: timeout for stop_TX/RX and reset_TX/RX
#define ERROR_ILLEGAL_STATE     EBADFD              //  77: function call not permitted at current device state
#define ERROR_INPUT             EINVAL              //  22: wrong function argument
#define ERROR_FPGA              EIO                 //   5: read: FPGA is in error state
#define ERROR_SIG_INTR          EINTR               //   4: interrupted system call
#define ERROR_BAD_ADDRESS       EFAULT              //  14: bad user address
#define ERROR_NO_MEM            ENOMEM              //  12: out of memory
#define ERROR_NO_BUF_MULT       113                 // 113: buffer size is not multiple of DMA_BUF_MULT

/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
// settings
/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

// public sample information
#ifndef DIO_BYTES_PER_SAMPLE                                // you can specify DIO_BYTES_PER_SAMPLE in your source code before including this file.
#define DIO_BYTES_PER_SAMPLE            8                   // bytes per sample, allowed values 8 (one subrack per board) or 12 (two subracks per board)
#endif
#define DIO_BIT_NOP                     31                  // data bit indicating no operation [TODO: can be set by ctrl_in but is hard-coded in driver]
//#define DIO_BIT_STOP                    30                  // data bit indicating time reset
//#define DIO_BIT_TRST                    29                  // data bit indicating time reset
//#define DIO_BIT_IRQ                     28                  // data bit generating FPGA IRQ, can be combined with DIO_BIT_NOP or not.
#define DIO_DATA_MASK                   0x00ffffff          // allowed 23+1 data+address bits w/o #SMPL = {8'h0,addr[7:0],data[15:0]} where addr[7] = strobe is ignored.
#define DIO_ADDR_MASK                   0x00ff0000          // 8 address bits, where addr[7] = strobe is ignored.
#if DIO_BYTES_PER_SAMPLE == 8
#define DIO_MAX_SAMPLES                 10                  // maximum number of allowed samples in 10^6 for 8 bytes/sample
#elif DIO_BYTES_PER_SAMPLE == 12
#define DIO_MAX_SAMPLES                 15                  // maximum number of allowed samples in 10^6 for 12 bytes/sample
#endif

// bus clock settings
#define MHZ                             1000000             // 1MHz
#define BUS_CLOCK_FREQ_MHZ              100                 // bus clock frequency in MHz
#define BUS_CLOCK_FREQ_HZ               (BUS_CLOCK_FREQ_MHZ*MHZ) // bus clock frequency in Hz (f_bus_clk = 100MHz)
#define VCO_FREQ_MHZ                    1000                // VCO frequency in MHz
#define VCO_FREQ_HZ                     (VCO_FREQ_MHZ*MHZ)  // VCO frequency in Hz
#define BUS_OUT_FREQ_HZ                 MHZ                 // default bus output clock frequency in Hz (1MHz)
#define PHASE_360                       (56*BUS_CLOCK_FREQ_MHZ/VCO_FREQ_MHZ)                 // steps for 360 degree phase shift (56*f_VCO/f_bus_clk)
#define BUS_OUT_MAX_HZ                  (40*MHZ)            // maximum bus output rate in Hz
#define BUS_OUT_MIN_HZ                  (1*MHZ)             // minimum bus output rate in Hz

// IRQ_FPGA frequency
// TODO: maybe factor 2 wrong? 
#define IRQ_FREQ_BITS                   17                  // bits used for IRQ frequency generation. see dio24 customization parameter.
#define IRQ_FREQ                        BUS_OUT_CLOCK_FREQ_HZ/(1<<(IRQ_FREQ_BITS-1))        // IRQ_FPGA frequency in Hz
#define IRQ_FREQ_US                     (1<<(IRQ_FREQ_BITS-1))/(BUS_OUT_FREQ_HZ/1000000)    // IRQ_FPGA period in us
#define IRQ_FREQ_MIN_TIMEOUT            (1 + (2*IRQ_FREQ_US)/1000)                          // minimum timeout in ms for dio24_read

// maximum number of subracks = number of strobe outputs
#define MAX_NUM_RACKS                   2

// default strobe delay and level
// a similar string can be given in server.config file as "strobe_0" and "strobe_1" entries to overwrite default behavior for both strobe signals.
// strobe delay r0:r1:r2:level. with relative ratios with respect to r0+r1+r2=1/BUS_OUT_FREQ_HZ.
// strobe active level = 0/1/2 = active low/high/toggle. if toggle then changes state at r0. 
// TODO: at the moment active low is not implemented. only active high (1) or toggle (2)
#define STRB_DELAY_STR                  "3:4:3:1"
#define STRB_DELAY_BITS                 8                           // bits per delay for {strb_1_end,strb_1_start,strb_0_end,strb_0_start}
#define STRB_DELAY_MASK                 ((1<<STRB_DELAY_BITS)-1)    // bit mask for STRB_DELAY_BITS
#define STRB_DELAY_AUTO                 0                           // use strobe delay from server.config file

// define sample size as multiple of DMA_BUF_MULT bytes.
// if needed driver will add samples with NOP bit set.
// TODO: this was needed for 12 bytes/samples version since in_conv could not handle partially filled samples (tkeep did not accepted 0s). this should be fixed now.
//       for 8 bytes/sample one could use only 2 samples but this might be problematic for >2 input buffers of timing module. for simplicity keep 4 samples in both cases.
#define DMA_BUF_MULT            (4*DIO_BYTES_PER_SAMPLE)             // fixed 4 samples = 4*8=32bytes=2*FIFO width or 4*12=48bytes=3*FIFO width, with FIFO width = 16bytes.

/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
// IOCTL codes
/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

#define START_FPGA_DELAYED              0                                       // start FPGA when DIO_FPGA_START_BT bytes or all data transferred (default)
#define START_FPGA_NOW                  1                                       // start FPGA immediately (use for timing_test module)
#define DMA24_IOCTL_START               _IOW(DMA24_MAGIC_NUM, 0,struct st_par*) // start DMA transfer with given repetitions
#define DMA24_IOCTL_STOP                _IOW(DMA24_MAGIC_NUM, 1, uint32_t)      // stops DMA transfer
#define DMA24_IOCTL_RESET               _IO(DMA24_MAGIC_NUM, 2)                 // stop and reset DMA

// DMA settings and status, see DMA_STATUS bits, no SET function
#define DMA24_IOCTL_GET_CONFIG          _IO(DMA24_MAGIC_NUM, 10)                // get configuration (same as FPGA_status::ctrl_FPGA)
#define DMA24_IOCTL_GET_STATUS_TX       _IO(DMA24_MAGIC_NUM, 11)                // returns TX status (same as FPGA_status::status_TX)
#define DMA24_IOCTL_GET_STATUS_RX       _IO(DMA24_MAGIC_NUM, 12)                // returns RX status (same as FPGA_status::status_RX)

// timeout
#define DMA24_IOCTL_SET_TIMEOUT         _IOWR(DMA24_MAGIC_NUM, 20, uint32_t *)  // set timeout in ms, return old value

// RX DMA buffer size
#define DMA24_IOCTL_SET_RX_BUFFER       _IOWR(DMA24_MAGIC_NUM, 40, uint32_t *)  // set RX buffer size in bytes, returns old value.
                                                                                // must be in multiples of DIO_BYTES_PER_SAMPLE
                                                                                // call before write to increase default RX buffer size

#define DMA24_IOCTL_GET_LOAD            _IO(DMA24_MAGIC_NUM, 50)                // returns TX and RX buffer load in % completed/max.active (RX<<16) | (TX)
#define DMA24_IOCTL_GET_LOAD_TX         _IO(DMA24_MAGIC_NUM, 51)                // returns TX buffer load in % completed/max.active
#define DMA24_IOCTL_GET_LOAD_RX         _IO(DMA24_MAGIC_NUM, 52)                // returns RX buffer load in % completed/max.active

// DMA control bits (obtained from DMA24_IOCTL_GET_CONFIG and FPGA_status::ctrl_FPGA returned by DMA24_IOCTL_GET_STATUS)
#define DMA_CTRL_NONE                   0                   // nothing active, nothing enabled
#define DMA_CTRL_ACTIVE_TX              ( 1<< 0 )           // TX DMA active = running
#define DMA_CTRL_ACTIVE_RX              ( 1<< 1 )           // RX DMA active = running
#define DMA_CTRL_ENABLE_TX              ( 1<< 2 )           // TX DMA enabled = start as soon as there is data written
#define DMA_CTRL_ENABLE_RX              ( 1<< 3 )           // RX DMA enabled = start as soon as there is read request
#define DMA_CTRL_CYCLIC_TX              ( 1<< 4 )           // TX DMA in cyclic mode
#define DMA_CTRL_CYCLIC_RX              ( 1<< 5 )           // RX DMA in cyclic mode
#define DMA_CTRL_ENABLE_FPGA            ( 1<< 8 )           // start FPGA when TX FIFO is full or all TX data written

// common combinations of DMA_STATUS bits
#define DMA_CTRL_ACTIVE_ALL         (DMA_CTRL_ACTIVE_TX | DMA_CTRL_ACTIVE_RX)
#define DMA_CTRL_ENABLE_ALL         (DMA_CTRL_ENABLE_TX | DMA_CTRL_ENABLE_RX)

// convert FPGA_temperature register value into °C/1000 units (uint32_t)
#define GET_mT(reg_T)    (((reg_T>>4)*503975)/4096 - 273150)

// TODO: not implemented anymore but would be nice to have this possibility again?
// timing test: write test bits = DIO_TEST_RUN|DIO_TEST_UPDATE and return board_time_ext (uses timing module) 
// flags=DIO_TEST_RUN: (re-)start timer. flags=0: stop timer and return time. flags=DIO_TEST_RUN|DIO_TEST_UPDATE: return actual time but keep timer running.
//#define DIO24_IOCTL_TIMING_TEST         _IOW(DIO24_MAGIC_NUM, 105, uint32_t) 

// start/stop FPGA without DMA (TODO: used for timing_test module which is not existing anymore)
#define DIO24_IOCTL_START               _IOW(DIO24_MAGIC_NUM, 100, uint32_t)      // start FPGA
#define DIO24_IOCTL_STOP                _IOW(DIO24_MAGIC_NUM, 101, uint32_t)      // stop FPGA
#define DIO24_IOCTL_RESET               _IOW(DIO24_MAGIC_NUM, 102, uint32_t)      // reset FPGA

// get status information
#define DIO24_IOCTL_GET_STATUS_FPGA     _IO(DIO24_MAGIC_NUM, 110)               // returns FPGA status bits
#define DIO24_IOCTL_GET_STATUS          _IOR(DIO24_MAGIC_NUM, 111, struct FPGA_status *) // returns FPGA_status
#define DIO24_IOCTL_GET_STATUS_RUN      _IOR(DIO24_MAGIC_NUM, 112, struct FPGA_status_run *) // returns FPGA_status_run
#define DIO24_IOCTL_GET_STATUS_DBG      _IOR(DIO24_MAGIC_NUM, 113, struct FPGA_status *) // prints additional memory and debug info

// internal and external clock periods
// *FPGA must be stopped!
// to set bus output clock period first set clock divider (DIO24_IOCTL_SET_DIV)
// the returned period is always as close as possible to the requested period. 
#define DIO24_IOCTL_GET_BUS_PERIOD      _IO(DIO24_MAGIC_NUM, 120)               // get bus output period in ps
#define DIO24_IOCTL_SET_BUS_PERIOD      _IOWR(DIO24_MAGIC_NUM, 121, uint32_t *) // set bus output period in ps, returns new period in ps
#define DIO24_IOCTL_GET_IN_PERIOD       _IO(DIO24_MAGIC_NUM, 122)               // get external input clock period in ps
#define DIO24_IOCTL_SET_IN_PERIOD       _IOWR(DIO24_MAGIC_NUM, 123, uint32_t *) // set external input clock period in ps, returns new period in ps
#define DIO24_IOCTL_GET_OUT_PERIOD      _IO(DIO24_MAGIC_NUM, 124)               // get external output clock period in ps
#define DIO24_IOCTL_SET_OUT_PERIOD      _IOWR(DIO24_MAGIC_NUM, 125, uint32_t *) // set external output clock period in ps, returns new period in ps

// get/set clock divider used by timing module. use DIO24_IOCTL_SET_BUS_PERIOD to set bus period directly.
#define DIO24_IOCTL_GET_DIV             _IO(DIO24_MAGIC_NUM, 130)               // get divider
#define DIO24_IOCTL_SET_DIV             _IOWR(DIO24_MAGIC_NUM, 131, uint32_t *) // set divider, return new divider*

// strobe delay
#define DIO24_IOCTL_GET_STRB_DELAY      _IO(DIO24_MAGIC_NUM, 136)               // get strobe delay
#define DIO24_IOCTL_SET_STRB_DELAY      _IOWR(DIO24_MAGIC_NUM, 137, uint32_t *) // set strobe delay, return new delay*

// FPGA control bits, see DIO_CTRL_ bits
#define DIO24_IOCTL_GET_CONFIG          _IO(DIO24_MAGIC_NUM, 140)               // get configuration
#define DIO24_IOCTL_SET_CONFIG          _IOWR(DIO24_MAGIC_NUM, 141, uint32_t *) // set configuration and return new configuration*

// trigger control bits settings, see CTRL_IN_ defines
#define DIO24_IOCTL_GET_CTRL_IN         _IO(DIO24_MAGIC_NUM, 142)               // get input control bits
#define DIO24_IOCTL_SET_CTRL_IN         _IOW(DIO24_MAGIC_NUM, 143, uint32_t)    // set input control bits

// ouput control bits settings, see CTRL_OUT_ defines
#define DIO24_IOCTL_GET_CTRL_OUT        _IO(DIO24_MAGIC_NUM, 145)               // get output control bits
#define DIO24_IOCTL_SET_CTRL_OUT        _IOW(DIO24_MAGIC_NUM, 145, uint32_t)    // set output control bits

// set/get sync delay
#define DIO24_IOCTL_GET_SYNC_DELAY      _IO(DIO24_MAGIC_NUM, 150)               // get sync delay
#define DIO24_IOCTL_SET_SYNC_DELAY      _IOW(DIO24_MAGIC_NUM, 151, uint32_t)    // set sync delay

// set/get sync phase
#define DIO24_IOCTL_GET_SYNC_PHASE      _IO(DIO24_MAGIC_NUM, 152)               // get sync phase
#define DIO24_IOCTL_SET_SYNC_PHASE      _IOW(DIO24_MAGIC_NUM, 153, uint32_t)    // set sync phase

// external trigger settings, see DIO_CTRL_TRG_ bits of control register (TODO: remove)
//#define DIO24_IOCTL_GET_EXTRIG          _IOR(DIO24_MAGIC_NUM, 152, uint32_t *)  // get trigger configuration
//#define DIO24_IOCTL_SET_EXTRIG          _IOWR(DIO24_MAGIC_NUM, 153, uint32_t *) // set trigger configuration and return new configuration*

// get sync time
#define DIO24_IOCTL_GET_SYNC_TIME       _IO(DIO24_MAGIC_NUM, 160)               // get sync time

// get version and info
#define DIO24_IOCTL_GET_INFO            _IOR(DIO24_MAGIC_NUM, 170, struct FPGA_info *)  // get version and info


/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
// structures
/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

// start, stop, reset DMA
struct st_par {                                                                 // parameters for DMA24_IOCTL_START
    uint32_t repetitions;
    uint32_t flags;
};

// dma24 mmap interface [not fully implemented]
#define MMAP_SIZE                   (1 * 1024 * 1024)       // 1MiB
struct dma24_interface {
    unsigned char buffer[MMAP_SIZE];
    enum status { DIO_NO_ERROR = 0, DIO_BUSY = 1, DIO_TIMEOUT = 2, DIO_ERROR = 3 } status;
    unsigned int length;
};

// FPGA status registers returned by DIO24_IOCTL_GET_STATUS_RUN and by reading dio24 device
// struct FPGA_status contains this also 
struct FPGA_status_run {
    uint32_t status;                                        // FPGA status register
    uint32_t board_time;                                    // FPGA board time register
    uint32_t board_samples;                                 // FPGA board samples register
};

// FPGA version and info registers returned by DIO24_IOCTL_GET_INFO
struct FPGA_info {
    uint32_t version;                                       // board version {brd_vers_major[7:0],brd_vers_minor[7:0],year[6:0],month[3:0],day[4:0], e.g. v1.2, 2023/01/10 = 23«9+1«5+10 = 0x0102_2e2a}
    uint32_t info;                                          // board info (board[15:0]: 0xc0/c1=Cora-Z7-07S/10, 0xa1/a2=Arty-Z7-10/20)
};

// data for DIO24_IOCTL_GET_STATUS
// ATTENTION: FPGA registers are read at once so order is important!
#define FPGA_STATUS_NUM_DEBUG           20
// used for debugging
#define DBG_HIST                        5
#define DBG_OFF_RX_IRQ                  0
#define DBG_OFF_RX_VERIFY               5
#define DBG_OFF_RX_START                10
#define DBG_OFF_RX_PREPARE              15
#define FPGA_STATUS_SHOW                1
#define FPGA_STATUS_SHOW_NOT            0
struct FPGA_status {
    // --- FPGA section ---
    // control
    uint32_t ctrl_FPGA;                                     // FPGA control register
    uint32_t ctrl_in;                                       // input control register
    uint32_t ctrl_out;                                      // output control register
    uint32_t set_samples;                                   // number of samples
    //uint32_t set_cycles;                                    // number of cycles (requires CTRL_RESTART_EN bit enabled, 1=default, 0=infinite)
    uint32_t clk_div;                                       // bus clock (bits 0-7) and trigger window (bits 15-8) divider.
    uint32_t strb_delay;                                    // strobe delay {strb_end_1,strb_start_1,strb_end_0,strb_start_0} each 8 bits
    uint32_t sync_delay;                                    // sync delay settings
    uint32_t sync_phase;                                    // sync phase {ext,det} settings
    // status register
    struct FPGA_status_run status_FPGA;
    uint32_t board_time_ext;                                // FPGA extra board time register
    uint32_t board_samples_ext;                             // FPGA extra board samples register
    //uint32_t board_cycles;                                  // FPGA board cycles
    uint32_t sync_time;                                     // auto-sync measured round trip time
    struct FPGA_info status_info;                           // FPGA version & info
    // XDC module board temperature
    uint32_t FPGA_temp;                                     // FPGA temperature in °C
    // actual phases and periods (no registers)
    uint32_t phase_ext, phase_det;                          // external and detector absolute phase in steps
    uint32_t period_in, period_out, period_bus;             // clock period of external in/out and bus in ns
    // --- DMA section ---
    uint32_t ctrl_DMA;                                      // DMA control bits
    uint32_t status_TX, status_RX;                          // TX and RX status bits
    uint8_t dsc_TX_p, dsc_TX_a, dsc_TX_c;                   // number of prepared/active/completed TX descriptors
    uint8_t dsc_RX_p, dsc_RX_a, dsc_RX_c;                   // number of prepared/active/completed RX descriptors
    int32_t err_TX, err_RX, err_FPGA;                       // last error code for TX, RX and FPGA channels, 0=ok, otherwise error
    uint32_t irq_TX, irq_RX, irq_FPGA;                      // number of IRQs for TX, RX, FPGA channels
    uint32_t irq_num;                                       // number of merged irqs at last irq_hdl_DMA
    uint32_t TX_bt_tot, RX_bt_tot, bt_tot;                  // total transmitted number of bytes for TX and RX channels
    uint32_t RD_bt_max, RD_bt_act, RD_bt_drop;              // maximum, available and droppted bytes for reading
    uint32_t reps_set, reps_act;                            // number of repetitions, 0=infinite, 1=default
    uint32_t timeout;                                       // timeout in ms for read. 0=inifinite=default
    union {
        uint32_t data32[DIO_BYTES_PER_SAMPLE/4];
        uint8_t data8[DIO_BYTES_PER_SAMPLE];
    } last_sample;
    // --- debugging section ---
    uint32_t debug_count;
    uint32_t debug[FPGA_STATUS_NUM_DEBUG];
};


/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
// registers
/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

// FPGA register indices
// control
#define REG_CTRL                0   // index of control register 
#define REG_CTRL_IN             1   // index of trigger control register
#define REG_CTRL_OUT            2   // index of trigger control register
#define REG_NUM_SAMPLES         3   // index of number of samples register
//#define REG_NUM_CYCLES          4   // index of number of cycles register
#define REG_CLK_DIV             4   // index of clk_div register
#define REG_STRB_DELAY          5   // index of strb_delay register
#define REG_SYNC_DELAY          6   // index of sync_delay register      
#define REG_SYNC_PHASE          7   // index of sync_phase register
// status registers
#define REG_STATUS              8   // index of status register
#define REG_BOARD_TIME          9   // index of board time register
#define REG_BOARD_SAMPLES       10  // index of board samples register
#define REG_BOARD_TIME_EXT      11  // index of 2nd board time register
#define REG_BOARD_SAMPLES_EXT   12  // index of 2nd board samples register
//#define REG_BOARD_CYCLES        14  // index of board cycles register
#define REG_SYNC_TIME           13  // index of sync time register
#define REG_VERSION             14  // index of version register
#define REG_INFO                15  // index of info regiser
// temperature register in XDC module uses different address mapping
//#define REG_TEMP                0

// FPGA control bits 
// obtained from DIO24_IOCTL_GET_CONFIG and from fpga_status entry returned by DMA24_IOCTL_GET_STATUS
// most bits can be set by DIO24_IOCTL_SET_CONFIG
#define DIO_CTRL_NONE                   0x0000              // initial state

#define DIO_CTRL_RESET                  ( 1<< 0 )           // reset enabled (not user settable)
#define DIO_CTRL_READY                  ( 1<< 1 )           // server ready (not user settable)
#define DIO_CTRL_RUN                    ( 1<< 2 )           // run enabled (not user settable)
#define DIO_CTRL_RESTART_EN             ( 1<< 4 )           // restart at end of cycle until cycles reached
#define DIO_CTRL_AUTO_SYNC_EN           ( 1<< 5 )           // auto-sync enable bit = if 1'b1 detect start trigger @ clk_det and wait sync_delay, otherwise detect @ clk_bus and no wait.
#define DIO_CTRL_AUTO_SYNC_PRIM         ( 1<< 6 )           // auto-sync primary board. unused at the moment.
#define DIO_CTRL_BPS96                  ( 1<< 8 )           // data format 0=64bits/sample (default), 1=96bits/sample 
#define DIO_CTRL_BPS96_BRD              ( 1<< 9 )           // data+address selection if DIO_CTRL_BPS96=1: 0=2nd 32bit, 1=3rd 32bit (time=1st 32bit)
#define DIO_CTRL_EXT_CLK                ( 1<< 10 )          // 0/1=use internal/external clock
#define DIO_CTRL_ERR_LOCK_EN            ( 1<< 15 )          // enable error lock lost
#define DIO_CTRL_IRQ_EN                 ( 1<< 20 )          // FPGA all irq's enabled
#define DIO_CTRL_IRQ_END_EN             ( 1<< 21 )          // FPGA end irq enabled
#define DIO_CTRL_IRQ_RESTART_EN         ( 1<< 22 )          // FPGA restart irq enabled
#define DIO_CTRL_IRQ_FREQ_EN            ( 1<< 23 )          // FPGA irq with DIO_IRQ_FREQ enabled
#define DIO_CTRL_IRQ_DATA_EN            ( 1<< 24 )          // FPGA irq with DIO_BIT_IRQ enabled

#define DIO_CTRL_IRQ_ALL                (DIO_CTRL_IRQ_EN|DIO_CTRL_IRQ_END_EN|DIO_CTRL_RESTART_EN|DIO_CTRL_IRQ_FREQ_EN|DIO_CTRL_IRQ_DATA_EN)
#define DIO_CTRL_USED                   0x01F087F7          // used bits of control register
#define DIO_CTRL_USER                   0x01F087F0          // allowed user bits for DIO24_IOCTL_SET_CONFIG

// trigger control register
#define CTRL_IN_SRC_BITS                3
#define CTRL_IN_LEVEL_BITS              2
#define CTRL_IN_DST_BITS                (CTRL_IN_SRC_BITS + CTRL_IN_LEVEL_BITS)

// trigger destination offsets
#define CTRL_IN_DST_START               (0*CTRL_IN_DST_BITS)   // start trigger (= sync_in with DIO_CTRL_AUTO_SYNC_EN)
#define CTRL_IN_DST_STOP                (1*CTRL_IN_DST_BITS)   // stop trigger
#define CTRL_IN_DST_RESTART             (2*CTRL_IN_DST_BITS)   // restart trigger
#define CTRL_IN_DST_NOP                 (3*CTRL_IN_DST_BITS)   // NOP bit
#define CTRL_IN_DST_STRB                (4*CTRL_IN_DST_BITS)   // STRB bit
#define CTRL_IN_DST_IRQ                 (5*CTRL_IN_DST_BITS)   // IRQ bit
 
// trigger sources
#define CTRL_IN_SRC_NONE                0                       // no trigger input
#define CTRL_IN_SRC_IN0                 1                       // ext_in[0]
#define CTRL_IN_SRC_IN1                 2                       // ext_in[1]
#define CTRL_IN_SRC_IN2                 3                       // ext_in[2]
#define CTRL_IN_SRC_DATA_20             5                       // data bit 20-23
#define CTRL_IN_SRC_DATA_24             6                       // data bit 24-27
#define CTRL_IN_SRC_DATA_28             7                       // data bit 28-31

// trigger levels
#define CTRL_TRG_LEVEL_LOW              0                       // level low
#define CTRL_TRG_LEVEL_HIGH             1                       // level higth
#define CTRL_TRG_EDGE_FALLING           2                       // edge falling
#define CTRL_TRG_EDGE_RISING            3                       // edge rising
// data bit offsets
#define CTRL_IN_DATA_0                  0                       // offset bit 0
#define CTRL_IN_DATA_1                  1                       // offset bit 1
#define CTRL_IN_DATA_2                  2                       // offset bit 2
#define CTRL_IN_DATA_3                  3                       // offset bit 3

// output control register
#define CTRL_OUT_SRC_BITS               4
#define CTRL_OUT_LEVEL_BITS             2
#define CTRL_OUT_DST_BITS               (CTRL_OUT_SRC_BITS + CTRL_OUT_LEVEL_BITS)

// output destination offsets
#define CTRL_OUT_DST_OUT0               (0*CTRL_OUT_DST_BITS)   // ext_out[0]
#define CTRL_OUT_DST_OUT1               (1*CTRL_OUT_DST_BITS)   // ext_out[1]
#define CTRL_OUT_DST_OUT2               (2*CTRL_OUT_DST_BITS)   // ext_out[2]
#define CTRL_OUT_DST_BUS_EN_0           (3*CTRL_OUT_DST_BITS)   // bus_en[0]
#define CTRL_OUT_DST_BUS_EN_1           (4*CTRL_OUT_DST_BITS)   // bus_en[1]

// output sources
#define CTRL_OUT_SRC_NONE               0                   // fixed output with given level
#define CTRL_OUT_SRC_SYNC_OUT           1                   // sync_out
#define CTRL_OUT_SRC_SYNC_EN            2                   // sync_en (as_active)
#define CTRL_OUT_SRC_SYNC_MON           3                   // sync_mon (for debugging)
#define CTRL_OUT_SRC_CLK_LOST           4                   // clock loss
#define CTRL_OUT_SRC_ERROR              5                   // error
#define CTRL_OUT_SRC_RUN                6                   // run (or wait)
#define CTRL_OUT_SRC_WAIT               7                   // wait
#define CTRL_OUT_SRC_READY              8                   // ready
#define CTRL_OUT_SRC_RESTART            9                   // restart
#define CTRL_OUT_TRG_START              10                  // start trigger toggle bit
#define CTRL_OUT_TRG_STOP               11                  // stop trigger toggle bit
#define CTRL_OUT_TRG_RESTART            12                  // restart trigger toggle bit

// output levels
#define CTRL_OUT_LEVEL_LOW              0                   // level active low = inverted
#define CTRL_OUT_LEVEL_HIGH             1                   // level active high = normal

// bits used for normal run with 64 or 96 bits/sample
#define DIO_CONFIG_RUN_64               (DIO_CTRL_IRQ_EN|DIO_CTRL_IRQ_END_EN|DIO_CTRL_IRQ_FREQ_EN|DIO_CTRL_ERR_LOCK_EN)
#define DIO_CONFIG_RUN_RESTART_64       (DIO_CONFIG_RUN_64|DIO_CTRL_IRQ_RESTART_EN|DIO_CTRL_RESTART_EN)
#define DIO_CONFIG_RUN_96               (DIO_CONFIG_RUN_64|DIO_CTRL_BPS96)
#define DIO_CONFIG_RUN_RESTART_96       (DIO_CONFIG_RUN_RESTART_64|DIO_CTRL_BPS96)

// auto-sync
#define AUTO_SYNC_SINGLE_BOARD          (DIO_CTRL_IRQ_EN|DIO_CTRL_IRQ_END_EN|DIO_CTRL_IRQ_FREQ_EN|DIO_CTRL_IRQ_DATA_EN)
#define AUTO_SYNC_PRIM_CONF             (DIO_CTRL_AUTO_SYNC_EN|DIO_CTRL_AUTO_SYNC_PRIM|DIO_CTRL_IRQ_EN|DIO_CTRL_IRQ_END_EN|DIO_CTRL_IRQ_FREQ_EN|DIO_CTRL_IRQ_DATA_EN)
#define AUTO_SYNC_SEC_CONF              (DIO_CTRL_AUTO_SYNC_EN|DIO_CTRL_EXT_CLK|DIO_CTRL_IRQ_EN|DIO_CTRL_IRQ_END_EN|DIO_CTRL_IRQ_FREQ_EN|DIO_CTRL_IRQ_DATA_EN)

// auto-sync delay register bits
#define SYNC_DELAY_BITS                 10
//#define SYNC_MAX_DELAY                  ((1<<SYNC_DELAY_BITS)-1)
#define SYNC_DELAY_MASK                 ((1<<SYNC_DELAY_BITS)-1)
#define SYNC_DELAY_WITH_FET             (1<<31)                         // use FET bit in delay sent to server = reflect pulse
#define SYNC_DELAY_AUTO                 0xffffffff                      // use the delay from server.config file

// auto-sync phase register bits
#define SYNC_PHASE_BITS                 12
//#define SYNC_MAX_PHASE                  ((1<<(SYNC_PHASE_BITS))-1)       // +31
#define SYNC_PHASE_MASK_1               ((1<<SYNC_PHASE_BITS)-1)
#define SYNC_PHASE_MASK_2               ((1<<(2*SYNC_PHASE_BITS))-1)
#define SYNC_PHASE_AUTO                 0xffffffff                      // use phase from server.config file

// dio24 status register
#define DIO_STATUS_NONE                 0x0000              // initial state
//
#define DIO_STATUS_RESET                ( 1<< 0 )           // reset active
#define DIO_STATUS_READY                ( 1<< 1 )           // ready state = first data received & not end
#define DIO_STATUS_RUN                  ( 1<< 2 )           // running state
#define DIO_STATUS_END                  ( 1<< 3 )           // end state = num_samples reached
// 
#define DIO_STATUS_WAIT                 ( 1<< 4 )           // wait for restart trigger
#define DIO_STATUS_AUTO_SYNC            ( 1<< 5 )           // auto-sync active
#define DIO_STATUS_AS_TIMEOUT           ( 1<< 6 )           // auto-sync timeout
#define DIO_STATUS_PS_ACTIVE            ( 1<< 7 )           // phase shift active
//
#define DIO_STATUS_EXT_USED             ( 1<<10 )           // 0/1=internal/external clock is used
#define DIO_STATUS_EXT_LOCKED           ( 1<<11 )           // external clock is locked
//
#define DIO_STATUS_ERR_TX               ( 1<<12 )           // error TX timeout loading of data
#define DIO_STATUS_ERR_RX               ( 1<<13 )           // error RX not ready
#define DIO_STATUS_ERR_TIME             ( 1<<14 )           // error timing
#define DIO_STATUS_ERR_LOCK             ( 1<<15 )           // error lock lost
#define DIO_STATUS_ERR_TKEEP            ( 1<<16 )           // error tkeep signal (for debugging)
#define DIO_STATUS_ERR_TKEEP2           ( 1<<17 )           // error tkeep signal (for debugging)
#define DIO_STATUS_ERR_TKEEP3           ( 1<<18 )           // error tkeep signal (for debugging)
//
#define DIO_STATUS_IRQ_FPGA_ERR         ( 1<<20 )           // FPGA error irq
#define DIO_STATUS_IRQ_FPGA_END         ( 1<<21 )           // FPGA end irq
#define DIO_STATUS_IRQ_FPGA_RESTART     ( 1<<22 )           // FPGA restart irq
#define DIO_STATUS_IRQ_FPGA_FREQ        ( 1<<23 )           // FPGA IRQ_FREQ
#define DIO_STATUS_IRQ_FPGA_DATA        ( 1<<24 )           // FPGA IRQ_DATA
//
#define DIO_STATUS_BTN_0                ( 1<<30 )           // button 0
#define DIO_STATUS_BTN_1                ( 1<<31 )           // button 1

#define DIO_STATUS_IRQ_ALL    (DIO_STATUS_IRQ_FPGA_ERR|DIO_STATUS_IRQ_FPGA_END|DIO_STATUS_IRQ_FPGA_RESTART|DIO_STATUS_IRQ_FPGA_FREQ|DIO_STATUS_IRQ_FPGA_DATA)

#define DIO_STATUS_RESET_MASK           (~(DIO_STATUS_EXT_LOCKED|DIO_STATUS_BTN_0|DIO_STATUS_BTN_1)) // mask for reset
#define DIO_STATUS_RESET_EXP            0x0000                  // expected status bits after reset with mask applied
#define DIO_STATUS_ERROR    (DIO_STATUS_ERR_TX|DIO_STATUS_ERR_RX|DIO_STATUS_ERR_TIME|DIO_STATUS_ERR_LOCK|DIO_STATUS_ERR_TKEEP|DIO_STATUS_ERR_TKEEP2|DIO_STATUS_ERR_TKEEP3) // error bits

#endif  // DIO24_DRIVER_HEADER
