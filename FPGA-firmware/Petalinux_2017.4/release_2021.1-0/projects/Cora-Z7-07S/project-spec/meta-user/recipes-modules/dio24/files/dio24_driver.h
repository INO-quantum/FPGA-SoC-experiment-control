////////////////////////////////////////////////////////////////////////////////////////////////////
// dio24_driver.h
// public header for dio24 kernel module
// compiled with g++ on Ubuntu 18.04 LTS
// tested with Petalinux 2017.4
// created September 2018 by Andi
// last change 27/07/2020 by Andi
////////////////////////////////////////////////////////////////////////////////////////////////////

#ifndef DIO24_DRIVER_HEADER
#define DIO24_DRIVER_HEADER

#ifdef _WIN32
#include <stdint.h>                                         // uint32_t, etc.
#endif

// public names
#define DIO24_DRIVER_NAME               "dio24"                                 // driver name
#define DIO24_DEVICE_NAME               "dio24dev"                              // DIO device name (read FPGA status and time)
#define DIO24_DEVICE_FILE_NAME(x)       "/dev/" DIO24_DEVICE_NAME #x            // device x=0,1,... file name
#define DMA24_DEVICE_NAME               "dma24dev"                              // DMA device name (write/read samples)
#define DMA24_DEVICE_FILE_NAME(x)       "/dev/" DMA24_DEVICE_NAME #x            // device x=0,1,... file name
#define DIO24_MAGIC_NUM                 0x4C464154                              // FPGA magic number LFAT = Lens/Firenze/AT

// public sample information
#define DIO_BYTES_PER_SAMPLE            12                  // 64bits=8bytes per sample or 96bits=12bytes
#define DIO_BIT_NOP                     31                  // data bit indicating NOP = no operation
#define DIO_BIT_IRQ                     30                  // data bit generating FPGA IRQ, can be combined with DIO_BIT_NOP or not.
#define DIO_BIT_NUM                     29                  // data bit indicating number of samples (#SMPL) = number of samples (first 32bit)
#define DIO_DATA_MASK                   0x00ffffff          // allowed 23+1 data+address bits w/o #SMPL = {8'h0,addr[7:0],data[15:0]} where addr[7] = strobe is ignored.
#define DIO_ADDR_MASK                   0x00ff0000          // 8 address bits, where addr[7] = strobe is ignored.
#define DIO_SAMPLES_MASK                0x0000ffff          // num samples bits when DIO_NUM_SAMPLE_BIT is set. TODO: is this correct?
#define DIO_IRQ_FREQ                    16                  // FPGA irq is generated with this frequency in Hz (is power of 2)
#define PHASE_360                       1120                // steps for 360 degree phase shift
#if DIO_BYTES_PER_SAMPLE == 8
#define DIO_MAX_SAMPLES                 10                  // maximum number of allowed samples in 10^6 for 8 bytes/sample
#elif DIO_BYTES_PER_SAMPLE == 12
#define DIO_MAX_SAMPLES                 15                  // maximum number of allowed samples in 10^6 for 12 bytes/sample
#endif

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

// IOCTL codes
#define DMA24_MAGIC_NUM                 (DIO24_MAGIC_NUM+1)                     // DMA magic number

// start, stop, reset DMA
struct st_par {                                                                 // parameters for DMA24_IOCTL_START
    uint32_t repetitions;
    uint32_t flags;
};
#define START_FPGA_DELAYED              0                                       // start FPGA when DIO_FPGA_START_BT bytes or all data transferred (default)
#define START_FPGA_NOW                  1                                       // start FPGA immediately (use for timing_test module)
#define DMA24_IOCTL_START               _IOW(DMA24_MAGIC_NUM, 0, struct st_par *) // start DMA transfer with given repetitions
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

/* parameters for DMA24_IOCTL_START [not used anymore, implement later again]
#define DMA_START_TX            1                    // start transmission of data from beginning and stop when bytes transferred
#define DMA_START_RX            2                    // start receiving of data from beginning and stop when bytes transferred
#define DMA_RESUME_TX            (4 | DMA_START_TX)            // resume transmission of data from current position and stop when bytes transferred
#define DMA_RESUME_RX            (8 | DMA_START_RX)            // resume receiving of data from current position and stop when bytes transferred
//#define DMA_START_TX_STOP_AT_END    (16 | DMA_START_TX)            // stop TX at end of TX data buffer
//#define DMA_START_RX_STOP_AT_END    (32 | DMA_START_RX)            // stop RX at end of TX data buffer
#define DMA_START_TX_AND_LOOP        (16 | DMA_START_TX)            // start TX from beginning and loop until DMA24_IOCTL_STOP
#define DMA_START_RX_AND_LOOP        (32 | DMA_START_RX)            // start RX from beginning and loop until DMA24_IOCTL_STOP
#define DMA_RESUME_TX_AND_LOOP        (16 | DMA_RESUME_TX)            // resume TX from current and loop until DMA24_IOCTL_STOP
#define DMA_RESUME_RX_AND_LOOP        (32 | DMA_RESUME_RX)            // resume RX from current and loop until DMA24_IOCTL_STOP
#define DMA_START_MASK            (DMA_START_TX_STOP_AT_END | DMA_START_RX_STOP_AT_END) // allowed bits

// parameters for DMA24_IOCTL_STOP
#define DMA_PAUSE_TX            1                    // pause transmission of data (resumable)
#define DMA_PAUSE_RX            2                    // pause receiving of data (resumable)
#define DMA_STOP_TX            (4 | DMA_PAUSE_TX)            // stop transmission of data and reset to beginning
#define DMA_STOP_RX            (8 | DMA_PAUSE_RX)            // stop receiving of data and reset to beginning
#define DMA_STOP_TX_AT_END        (16 | DMA_STOP_TX)            // stop TX at end of TX data buffer
#define DMA_STOP_RX_AT_END        (32 | DMA_STOP_RX)            // stop RX at end of TX data buffer
#define DMA_STOP_MASK            (DMA_STOP_TX_AT_END | DMA_STOP_RX_AT_END) // allowed bits
*/


// dma24 mmap interface
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

// data for DIO24_IOCTL_GET_STATUS (37*4=148bytes)
// ATTENTION: FPGA registers are read at once so order is important!
//#define FPGA_STATUS_REGS                4
#define FPGA_STATUS_NUM_DEBUG           20
// used for debugging
#define DBG_HIST                        5
#define DBG_OFF_RX_IRQ                  0
#define DBG_OFF_RX_VERIFY               5
#define DBG_OFF_RX_START                10
#define DBG_OFF_RX_PREPARE              15
struct FPGA_status {
    // FPGA section: maintained by hardware, FPGA_STATUS_REGS registers
    // control
    uint32_t ctrl_FPGA;                                     // FPGA control register
    uint32_t ctrl_test;                                     // timing test settings
    uint32_t set_samples;                                   // number of samples
    uint32_t sync_delay;                                    // sync delay settings
    uint32_t sync_phase;                                    // sync phase {ext,det} settings
    // status register
    struct FPGA_status_run status_FPGA;
    uint32_t board_time_ext;                                // FPGA extra board time register
    uint32_t board_samples_ext;                             // FPGA extra board samples register
    uint32_t sync_time;                                     // auto-sync measured round trip time
    uint32_t FPGA_temp;                                     // FPGA temperature in °C
    // FPGA section: maintained by driver, any order
    uint32_t phase_ext, phase_det;                          // external and detector absolute phase in steps
    // DMA section: maintained by driver, any order
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
    // used for debugging
    uint32_t debug_count;
    uint32_t debug[FPGA_STATUS_NUM_DEBUG];
};

// convert FPGA_temperature register value into °C/1000 units (uint32_t)
#define GET_mT(reg_T)    (((reg_T>>4)*503975)/4096 - 273150)

// start/stop FPGA without DMA. use for timing_test module only!
#define DIO24_IOCTL_START               _IOW(DIO24_MAGIC_NUM, 100, uint32_t)      // start FPGA
#define DIO24_IOCTL_STOP                _IOW(DIO24_MAGIC_NUM, 101, uint32_t)      // stop FPGA
#define DIO24_IOCTL_RESET               _IOW(DIO24_MAGIC_NUM, 102, uint32_t)      // reset FPGA

// timing test: write test bits = DIO_TEST_RUN|DIO_TEST_UPDATE and return board_time_ext (uses timing module) 
// flags=DIO_TEST_RUN: (re-)start timer. flags=0: stop timer and return time. flags=DIO_TEST_RUN|DIO_TEST_UPDATE: return actual time but keep timer running.
#define DIO24_IOCTL_TIMING_TEST         _IOW(DIO24_MAGIC_NUM, 105, uint32_t) 

// get status information
#define DIO24_IOCTL_GET_STATUS_FPGA     _IO(DIO24_MAGIC_NUM, 110)               // returns FPGA status bits
#define DIO24_IOCTL_GET_STATUS          _IOR(DIO24_MAGIC_NUM, 111, struct FPGA_status *) // returns FPGA_status
#define DIO24_IOCTL_GET_STATUS_RUN      _IOR(DIO24_MAGIC_NUM, 112, struct FPGA_status_run *) // returns FPGA_status_run
#define DIO24_IOCTL_GET_STATUS_DBG      _IOR(DIO24_MAGIC_NUM, 113, struct FPGA_status *) // prints additional memory and debug info

// internal and external clock
// *FPGA must be stopped!
#define DIO24_IOCTL_GET_INT_CLOCK       _IOR(DIO24_MAGIC_NUM, 120, uint32_t *)  // get internal clock frequency in Hz
#define DIO24_IOCTL_GET_EXT_CLOCK       _IOR(DIO24_MAGIC_NUM, 121, uint32_t *)  // get external clock frequency in Hz
#define DIO24_IOCTL_SET_EXT_CLOCK       _IOWR(DIO24_MAGIC_NUM, 122, uint32_t *) // set external clock frequency in Hz, returns new clock frequency in Hz*

// multiplicator
#define DIO24_IOCTL_GET_MULT            _IOR(DIO24_MAGIC_NUM, 130, uint32_t *)  // get multiplicator
#define DIO24_IOCTL_SET_MULT            _IOWR(DIO24_MAGIC_NUM, 131, uint32_t *) // set multiplicator, return new multiplicator*

// FPGA settings, see DIO_CTRL_ bits
#define DIO24_IOCTL_GET_CONFIG          _IO(DIO24_MAGIC_NUM, 140)               // get configuration
#define DIO24_IOCTL_SET_CONFIG          _IOWR(DIO24_MAGIC_NUM, 141, uint32_t *) // set configuration and return new configuration*

// test bits settings, see DIO_TEST_ bits
#define DIO24_IOCTL_GET_TEST            _IO(DIO24_MAGIC_NUM, 142)               // get test bits
#define DIO24_IOCTL_SET_TEST            _IOW(DIO24_MAGIC_NUM, 143, uint32_t)    // set test bits

// set/get sync delay
#define DIO24_IOCTL_GET_SYNC_DELAY      _IO(DIO24_MAGIC_NUM, 150)               // get sync delay
#define DIO24_IOCTL_SET_SYNC_DELAY      _IOW(DIO24_MAGIC_NUM, 151, uint32_t)    // set sync delay

// set/get sync phase
#define DIO24_IOCTL_GET_SYNC_PHASE      _IO(DIO24_MAGIC_NUM, 152)               // get sync phase
#define DIO24_IOCTL_SET_SYNC_PHASE      _IOW(DIO24_MAGIC_NUM, 153, uint32_t)    // set sync phase

// external trigger settings, see DIO_CTRL_TRG_ bits of control register
#define DIO24_IOCTL_GET_EXTRIG          _IOR(DIO24_MAGIC_NUM, 152, uint32_t *)  // get trigger configuration
#define DIO24_IOCTL_SET_EXTRIG          _IOWR(DIO24_MAGIC_NUM, 153, uint32_t *) // set trigger configuration and return new configuration*

// get sync time
#define DIO24_IOCTL_GET_SYNC_TIME       _IO(DIO24_MAGIC_NUM, 160)               // get sync time

// FPGA control bits 
// obtained from DIO24_IOCTL_GET_CONFIG and from fpga_status entry returned by DMA24_IOCTL_GET_STATUS
// most bits can be set by DIO24_IOCTL_SET_CONFIG
#define DIO_CTRL_NONE                   0x0000              // initial state

#define DIO_CTRL_RESET                  ( 1<< 0 )           // reset enabled (not user settable)
#define DIO_CTRL_READY                  ( 1<< 1 )           // server ready (not user settable)
#define DIO_CTRL_RUN                    ( 1<< 2 )           // run enabled (not user settable)
#define DIO_CTRL_RESTART_EN             ( 1<< 4 )           // automatic restart (for timing_test: wait for data)
#define DIO_CTRL_AUTO_SYNC_EN           ( 1<< 5 )           // auto-sync enabled
#define DIO_CTRL_AUTO_SYNC_PRIM         ( 1<< 6 )           // auto-sync primary board = generate pulse & start timer , if false wait for pulse
#define DIO_CTRL_AUTO_SYNC_FET          ( 1<< 7 )           // auto-sync enable FET = reflect pulse
#define DIO_CTRL_BPS96                  ( 1<< 8 )           // data format 0=64bits/sample (default), 1=96bits/sample 
#define DIO_CTRL_BPS96_BRD              ( 1<< 9 )           // data+address selection if DIO_CTRL_BPS96=1: 0=2nd 32bit, 1=3rd 32bit (time=1st 32bit)
#define DIO_CTRL_EXT_CLK                ( 1<< 10 )          // 0/1=use internal/external clock
#define DIO_CTRL_IRQ_EN                 ( 1<< 20 )          // FPGA all irq's enabled
#define DIO_CTRL_IRQ_END_EN             ( 1<< 21 )          // FPGA end irq enabled
#define DIO_CTRL_IRQ_RESTART_EN         ( 1<< 22 )          // FPGA restart irq enabled
#define DIO_CTRL_IRQ_FREQ_EN            ( 1<< 23 )          // FPGA irq with DIO_IRQ_FREQ enabled
#define DIO_CTRL_IRQ_DATA_EN            ( 1<< 24 )          // FPGA irq with DIO_BIT_IRQ enabled
#define DIO_CTRL_TRG_START_EN           ( 1<< 28 )          // enable start trigger
#define DIO_CTRL_TRG_STOP_EN            ( 1<< 29 )          // enable stop trigger

#define DIO_CTRL_IRQ_ALL                (DIO_CTRL_IRQ_EN|DIO_CTRL_IRQ_END_EN|DIO_CTRL_RESTART_EN|DIO_CTRL_IRQ_FREQ_EN|DIO_CTRL_IRQ_DATA_EN)
#define DIO_CTRL_USED                   0x31F007F7          // used bits of control register
#define DIO_CTRL_USER                   0x31F007F0          // allowed user bits for DIO24_IOCTL_SET_CONFIG
#define DIO_TRG_BITS                    0x30000000          // allowed bits for DIO24_IOCTL_SET_EXTRIG

// bits used for normal run with 64 or 96 bits/sample
#define DIO_CONFIG_RUN_64               (DIO_CTRL_IRQ_EN|DIO_CTRL_IRQ_END_EN|DIO_CTRL_IRQ_FREQ_EN)
#define DIO_CONFIG_RUN_RESTART_64       (DIO_CONFIG_RUN_64|DIO_CTRL_IRQ_RESTART_EN|DIO_CTRL_RESTART_EN)
#define DIO_CONFIG_RUN_96               (DIO_CONFIG_RUN_64|DIO_CTRL_BPS96)
#define DIO_CONFIG_RUN_RESTART_96       (DIO_CONFIG_RUN_RESTART_64|DIO_CTRL_BPS96)

// test bits in timing module
#define DIO_TEST_RUN                    ( 1<< 0 )           // test_timer run bit. on falling edge: board_time_ext = test_timer.
#define DIO_TEST_UPDATE                 ( 1<< 1 )           // test_timer update bit. on rising edge board_samples_ext = test_timer.
#define DIO_TEST_MASK                   ( DIO_TEST_RUN | DIO_TEST_UPDATE ) // allowed test bits

/* performance test and auto-sync control bits in timing-test module
#define DIO_TEST_TX                     ( 1<< 0 )           // TX enable
#define DIO_TEST_RX                     ( 1<< 1 )           // RX enable
#define DIO_TEST_START_0                ( 1<< 4 )           // start source
#define DIO_TEST_START_1                ( 1<< 5 )           // 0 = run rising edge, 1 = first data, 2 = IRQ rising edge, 3 = IRQ falling edge
#define DIO_TEST_START_2                ( 1<< 6 )           // 4 = trg_start rising edge, 5 = trg_start falling edge, 6 = trg_stop rising edge, 7 = trg_stop falling edge
#define DIO_TEST_UPD_0                  ( 1<< 8 )           // update board time source
#define DIO_TEST_UPD_1                  ( 1<< 9 )           // 0 = run falling edge, 1 = TX/RX data, 2 = IRQ rising edge, 3 = IRQ falling edge
#define DIO_TEST_UPD_2                  ( 1<< 10 )          // 4 = trg_start rising edge, 5 = trg_start falling edge, 6 = trg_stop rising edge, 7 = trg_stop falling edge
#define DIO_TEST_IRQ_0                  ( 1<< 12 )          // IRQ source
#define DIO_TEST_IRQ_1                  ( 1<< 13 )          // 2'b00 = none, 2'b01 = irq_TX, 2'b10 = irq_RX, 2'b11 = irq FPGA toggle bit

// timing test module settings for performance tests
// start source
#define PERF_START_RUN_UP               0
#define PERF_START_DATA                 DIO_TEST_START_0
#define PERF_START_IRQ_UP               DIO_TEST_START_1
#define PERF_START_IRQ_DN               (DIO_TEST_START_0|DIO_TEST_START_1)
#define PERF_START_TRG_START_UP         DIO_TEST_START_2
#define PERF_START_TRG_START_DN         (DIO_TEST_START_0|DIO_TEST_START_2)
#define PERF_START_TRG_STOP_UP          (DIO_TEST_START_1|DIO_TEST_START_2)
#define PERF_START_TRG_STOP_DN          (DIO_TEST_START_0|DIO_TEST_START_1|DIO_TEST_START_2)
// board time update source 
#define PERF_UPD_RUN_DN                 0
#define PERF_UPD_DATA                   DIO_TEST_UPD_0
#define PERF_UPD_IRQ_UP                 DIO_TEST_UPD_1
#define PERF_UPD_IRQ_DN                 (DIO_TEST_UPD_0|DIO_TEST_UPD_1)
#define PERF_UPD_TRG_START_UP           DIO_TEST_UPD_2
#define PERF_UPD_TRG_START_DN           (DIO_TEST_UPD_0|DIO_TEST_UPD_2)
#define PERF_UPD_TRG_STOP_UP            (DIO_TEST_UPD_1|DIO_TEST_UPD_2)
#define PERF_UPD_TRG_STOP_DN            (DIO_TEST_UPD_0|DIO_TEST_UPD_1|DIO_TEST_UPD_2)
// IRQ source
#define PERF_SIRQ_NONE                  0
#define PERF_SIRQ_TX                    DIO_TEST_IRQ_0
#define PERF_SIRQ_RX                    DIO_TEST_IRQ_1
#define PERF_SIRQ_FPGA_TGL              (DIO_TEST_IRQ_0|DIO_TEST_IRQ_1)
// shortcuts
#define PERF_USED_IRQS                  (DIO_CTRL_IRQ_EN|DIO_CTRL_IRQ_END_EN|DIO_CTRL_IRQ_FREQ_EN)
// test settings
#define PERF_TIME           (PERF_START_RUN_UP|PERF_UPD_RUN_DN|DIO_CTRL_IRQ_EN|DIO_CTRL_IRQ_END_EN) // start-stop timer used with dio24_start/stop. FPGA IRQ disabled
#define PERF_TIME_PEAK      (PERF_START_RUN_UP|PERF_UPD_RUN_DN|PERF_USED_IRQS) // with FPGA_IRQs to measure min/avg/max values
#define PERF_TX             (DIO_TEST_TX|PERF_START_DATA|PERF_UPD_DATA|PERF_USED_IRQS)
#define PERF_TX_PLUS        (DIO_TEST_TX|DIO_TEST_RX|PERF_START_DATA|PERF_UPD_DATA|PERF_USED_IRQS) // TX while RX running
#define PERF_TX_PLUS_IRQ    (DIO_TEST_TX|DIO_TEST_RX|PERF_START_DATA|PERF_UPD_IRQ_UP|PERF_SIRQ_TX|PERF_USED_IRQS) // TX while RX running, update on TX IRQ
#define PERF_RX             (DIO_TEST_RX|PERF_START_RUN_UP|PERF_UPD_IRQ_UP|PERF_SIRQ_RX|PERF_USED_IRQS)
#define PERF_RX_WRITE       (DIO_TEST_RX|PERF_START_RUN_UP|PERF_UPD_DATA|PERF_USED_IRQS) // RX time when data is written = see nicely backpressure
#define PERF_RX_PLUS        (DIO_TEST_TX|DIO_TEST_RX|PERF_START_DATA|PERF_UPD_IRQ_UP|PERF_SIRQ_RX|PERF_USED_IRQS) // [1,2] = PERF_RX and [3,4] = PERF_TX
#define PERF_IRQ_TX         (DIO_TEST_TX|PERF_START_IRQ_UP|PERF_UPD_IRQ_DN|PERF_SIRQ_TX|DIO_CTRL_IRQ_EN|DIO_CTRL_IRQ_END_EN)
#define PERF_IRQ_RX         (DIO_TEST_RX|PERF_START_IRQ_UP|PERF_UPD_IRQ_DN|PERF_SIRQ_RX|PERF_USED_IRQS)
#define PERF_IRQ_RX_TX      (DIO_TEST_TX|DIO_TEST_RX|PERF_START_IRQ_UP|PERF_UPD_IRQ_DN|PERF_SIRQ_RX|DIO_IRQ_EN|DIO_IRQ_END_EN)
#define PERF_IRQ_TX_RX      (DIO_TEST_TX|DIO_TEST_RX|PERF_START_IRQ_UP|PERF_UPD_IRQ_DN|PERF_SIRQ_TX|DIO_IRQ_EN|DIO_IRQ_END_EN)
#define PERF_IRQ_FPGA       (DIO_TEST_TX|DIO_TEST_RX|PERF_START_DATA|PERF_UPD_IRQ_UP|PERF_SIRQ_FPGA_TGL|PERF_USED_IRQS)
*/

// auto-sync
#define AUTO_SYNC_PRIM_CONF             (DIO_CTRL_AUTO_SYNC_EN|DIO_CTRL_AUTO_SYNC_PRIM|DIO_CTRL_IRQ_EN|DIO_CTRL_IRQ_END_EN|DIO_CTRL_IRQ_FREQ_EN|DIO_CTRL_IRQ_DATA_EN|DIO_CTRL_TRG_START_EN|DIO_CTRL_TRG_STOP_EN)
#define AUTO_SYNC_SEC_CONF              (DIO_CTRL_AUTO_SYNC_EN|DIO_CTRL_EXT_CLK|DIO_CTRL_IRQ_EN|DIO_CTRL_IRQ_END_EN|DIO_CTRL_IRQ_FREQ_EN|DIO_CTRL_IRQ_DATA_EN|DIO_CTRL_TRG_START_EN)
#define AUTO_SYNC_SEC_CONF_FET          (DIO_CTRL_AUTO_SYNC_EN|DIO_CTRL_AUTO_SYNC_FET|DIO_CTRL_EXT_CLK|DIO_CTRL_IRQ_EN|DIO_CTRL_IRQ_END_EN|DIO_CTRL_IRQ_FREQ_EN|DIO_CTRL_IRQ_DATA_EN|DIO_CTRL_TRG_START_EN)

// auto-sync delay and phase register bits
#define SYNC_DELAY_BITS                 10
#define SYNC_PHASE_BITS                 12
//#define SYNC_MAX_DELAY                  ((1<<SYNC_DELAY_BITS)-1)
//#define SYNC_MAX_PHASE                  ((1<<(SYNC_PHASE_BITS))-1)       // +31
#define SYNC_DELAY_MASK                 ((1<<SYNC_DELAY_BITS)-1)
#define SYNC_DELAY_WITH_FET             (1<<31)                         // use FET bit in delay sent to server = reflect pulse
#define SYNC_PHASE_MASK_1               ((1<<SYNC_PHASE_BITS)-1)
#define SYNC_PHASE_MASK_2               ((1<<(2*SYNC_PHASE_BITS))-1)

// dio24 status register
#define DIO_STATUS_NONE                 0x0000              // initial state
//
#define DIO_STATUS_RESET                ( 1<< 0 )           // reset active
#define DIO_STATUS_READY                ( 1<< 1 )           // ready state = first data received & not end
#define DIO_STATUS_RUN                  ( 1<< 2 )           // running state
#define DIO_STATUS_END                  ( 1<< 3 )           // end state = num_samples reached
// 
#define DIO_STATUS_RESTART              ( 1<< 4 )           // restart toggle bit
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
#define DIO_STATUS_ERR_TKEEP            ( 1<<16 )           // error tkeep signal
#define DIO_STATUS_ERR_TKEEP2           ( 1<<17 )           // error tkeep signal
#define DIO_STATUS_ERR_TKEEP3           ( 1<<18 )           // error tkeep signal
//
#define DIO_STATUS_IRQ_FPGA_ERR         ( 1<<20 )           // FPGA error irq
#define DIO_STATUS_IRQ_FPGA_END         ( 1<<21 )           // FPGA end irq
#define DIO_STATUS_IRQ_FPGA_RESTART     ( 1<<22 )           // FPGA restart irq
#define DIO_STATUS_IRQ_FPGA_FREQ        ( 1<<23 )           // FPGA IRQ_FREQ
#define DIO_STATUS_IRQ_FPGA_DATA        ( 1<<24 )           // FPGA IRQ_DATA
//
#define DIO_STATUS_TRG_START            ( 1<<28 )           // start external trigger active
#define DIO_STATUS_TRG_STOP             ( 1<<29 )           // stop external trigger active
//
#define DIO_STATUS_BTN_0                ( 1<<30 )           // button 0
#define DIO_STATUS_BTN_1                ( 1<<31 )           // button 1

#define DIO_STATUS_IRQ_ALL    (DIO_STATUS_IRQ_FPGA_ERR|DIO_STATUS_IRQ_FPGA_END|DIO_STATUS_IRQ_FPGA_RESTART|DIO_STATUS_IRQ_FPGA_FREQ|DIO_STATUS_IRQ_FPGA_DATA)

#define DIO_STATUS_RESET_MASK           (~(DIO_STATUS_RESTART|DIO_STATUS_EXT_LOCKED|DIO_STATUS_TRG_START|DIO_STATUS_TRG_STOP|DIO_STATUS_BTN_0|DIO_STATUS_BTN_1)) // mask for reset
#define DIO_STATUS_RESET_EXP            0                   // expected status bits after reset with mask applied
#define DIO_STATUS_ERROR    ( DIO_STATUS_ERR_TIME | DIO_STATUS_ERR_TX | DIO_STATUS_ERR_RX | DIO_STATUS_ERR_TKEEP|DIO_STATUS_ERR_TKEEP2|DIO_STATUS_ERR_TKEEP3 ) // one of the error bits set

#endif  // DIO24_DRIVER_HEADER
