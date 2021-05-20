////////////////////////////////////////////////////////////////////////////////////////////////////
// driver.h
// driver communication
// compiled with Visual Studio Express 2013 and g++
// tested with Windows 7, Ubuntu 18.04 LTS and Petalinux 2017.4
// dependency: dio24_driver.h
// created 23/06/2018 by Andi
// last change 18/05/2020
////////////////////////////////////////////////////////////////////////////////////////////////////

#ifndef DRIVER_H
#define DRIVER_H

#include <sys/ioctl.h>             // ioctl
// include "dio24_driver.h" before this file

////////////////////////////////////////////////////////////////////////////////////////////////////
// dma24 device
////////////////////////////////////////////////////////////////////////////////////////////////////

#ifdef NO_HARDWARE

#define dma24_open(x)                                   1    // 0=stdin, 1=stdout, 2=stderror
#define dma24_close(file_desc)                          {}
#define dma24_start(file_desc, p_st_pa                  0
#define dma24_stop(file_desc, flags)                    0
#define dma24_reset(file_desc)                          0
#define dma24_get_status_TX(file_desc)                  0
#define dma24_get_status_RX(file_desc)                  0

#else // with hardware

// open dma24 device
// returns device descriptor, <0 on error
#define dma24_open(x)                                   open(DMA24_DEVICE_FILE_NAME(x), O_RDWR | O_SYNC)
// close dma24 device
#define dma24_close(file_desc)                          close(file_desc)

// ioctl calls
// return 0 if ok, otherwise error
#define dma24_start(file_desc, p_st_par)                ioctl(file_desc, DMA24_IOCTL_START, p_st_par)
#define dma24_stop(file_desc, flags)                    ioctl(file_desc, DMA24_IOCTL_STOP, flags)
#define dma24_reset(file_desc)                          ioctl(file_desc, DMA24_IOCTL_RESET, NULL)
#define dma24_get_status_TX(file_desc)                  ioctl(file_desc, DMA24_IOCTL_GET_STATUS_TX, 0)
#define dma24_get_status_RX(file_desc)                  ioctl(file_desc, DMA24_IOCTL_GET_STATUS_RX, 0)
#endif // NO_HARDWARE

#define dma24_get_config(file_desc)                     ioctl(file_desc, DMA24_IOCTL_GET_CONFIG, 0)
#define dma24_set_timeout(file_desc, plong)             ioctl(file_desc, DMA24_IOCTL_SET_TIMEOUT, plong)
#define dma24_set_reps(file_desc, plong)                ioctl(file_desc, DMA24_IOCTL_SET_REPS, plong)
#define dma24_set_RX_buffer(file_desc, plong)           ioctl(file_desc, DMA24_IOCTL_SET_RX_BUFFER, plong)
#define dma24_get_load(file_desc)                       ioctl(file_desc, DMA24_IOCTL_GET_LOAD, NULL)
#define dma24_get_load_TX(file_desc)                    ioctl(file_desc, DMA24_IOCTL_GET_LOAD_TX, 0)
#define dma24_get_load_RX(file_desc)                    ioctl(file_desc, DMA24_IOCTL_GET_LOAD_RX, 0)

////////////////////////////////////////////////////////////////////////////////////////////////////
// dio24 device
// use dma24 device file_dsc returned by dma24_open()
////////////////////////////////////////////////////////////////////////////////////////////////////

#ifdef NO_HARDWARE

#define dio24_open(x)                                   1    // 0=stdin, 1=stdout, 2=stderror
#define dio24_close(file_desc)                          {}

#define dio24_start(file_desc, flags)                   0
#define dio24_stop(file_desc, flags)                    0
#define dio24_reset(file_desc, flags)                   0
#define dio24_timing_test(file_desc, flags)             0

#define dio24_get_status_FPGA(file_desc)                0
#define dio24_get_status(file_desc, p_ioctl_st)         0
#define dio24_get_status_run(file_desc, p_ioctl_st_run) 0
#define dio24_get_status_dbg(file_desc, p_ioctl_st)     0
#define dio24_get_int_clock(file_desc, plong)           0
#define dio24_get_ext_clock(file_desc, plong)           0
#define dio24_set_ext_clock(file_desc, plong)           0
#define dio24_get_mult(file_desc, plong)                0
#define dio24_set_mult(file_desc, plong)                0
#define dio24_get_config(file_desc)                     0
#define dio24_set_config(file_desc, plong)              0
#define dio24_get_extrig(file_desc, plong)              0
#define dio24_set_extrig(file_desc, plong)              0

#else // with hardware

// open dma24 device
// returns device descriptor, <0 on error
#define dio24_open(x)                                   open(DIO24_DEVICE_FILE_NAME(x), O_RDONLY | O_SYNC)
// close dma24 device
#define dio24_close(file_desc)                          close(file_desc)

// start/stop FPGA without DMA. use for timing_test module only! 
#define dio24_start(file_desc, flags)                   ioctl(file_desc, DIO24_IOCTL_START, flags)      // flags = 1: wait until run bit set, otherwise not
#define dio24_stop(file_desc, flags)                    ioctl(file_desc, DIO24_IOCTL_STOP, flags)
#define dio24_reset(file_desc, flags)                   ioctl(file_desc, DIO24_IOCTL_RESET, flags)      // only resets FPGA without DMA

// timing test: write test bits = DIO_TEST_RUN|DIO_TEST_UPDATE and return board_time_ext (uses timing module) 
// flags=DIO_TEST_RUN: (re-)start timer. flags=0: stop timer and return time. flags=DIO_TEST_RUN|DIO_TEST_UPDATE: return actual time but keep timer running.
#define dio24_timing_test(file_desc, flags)             ioctl(file_desc, DIO24_IOCTL_TIMING_TEST, flags)

// ioctl calls
// return 0 if ok, otherwise error
#define dio24_get_status_FPGA(file_desc)                ioctl(file_desc, DIO24_IOCTL_GET_STATUS_FPGA, 0)
#define dio24_get_status(file_desc, p_ioctl_st)         ioctl(file_desc, DIO24_IOCTL_GET_STATUS, p_ioctl_st)
#define dio24_get_status_run(file_desc, p_ioctl_st_run) ioctl(file_desc, DIO24_IOCTL_GET_STATUS_RUN, p_ioctl_st_run)
#define dio24_get_status_dbg(file_desc, p_ioctl_st)     ioctl(file_desc, DIO24_IOCTL_GET_STATUS_DBG, p_ioctl_st)

#define dio24_get_int_clock(file_desc, plong)           ioctl(file_desc, DIO24_IOCTL_GET_INT_CLOCK, plong)
#define dio24_get_ext_clock(file_desc, plong)           ioctl(file_desc, DIO24_IOCTL_GET_EXT_CLOCK, plong)
#define dio24_set_ext_clock(file_desc, plong)           ioctl(file_desc, DIO24_IOCTL_SET_EXT_CLOCK, plong)

#define dio24_get_mult(file_desc, plong)                ioctl(file_desc, DIO24_IOCTL_GET_MULT, plong)
#define dio24_set_mult(file_desc, plong)                ioctl(file_desc, DIO24_IOCTL_SET_MULT, plong)

#define dio24_get_config(file_desc)                     ioctl(file_desc, DIO24_IOCTL_GET_CONFIG, 0)
#define dio24_set_config(file_desc, plong)              ioctl(file_desc, DIO24_IOCTL_SET_CONFIG, plong)

#define dio24_get_test(file_desc)                       ioctl(file_desc, DIO24_IOCTL_GET_TEST, 0)           // return test bits
#define dio24_set_test(file_desc, long)                 ioctl(file_desc, DIO24_IOCTL_SET_TEST, long)        // set and return new test bits

#define dio24_get_sync_delay(file_desc)                 ioctl(file_desc, DIO24_IOCTL_GET_SYNC_DELAY, 0)     // return sync_delay
#define dio24_set_sync_delay(file_desc, long)           ioctl(file_desc, DIO24_IOCTL_SET_SYNC_DELAY, long)  // set and return new sync_delay
#define dio24_get_sync_phase(file_desc)                 ioctl(file_desc, DIO24_IOCTL_GET_SYNC_PHASE, 0)     // return sync_phase
#define dio24_set_sync_phase(file_desc, long)           ioctl(file_desc, DIO24_IOCTL_SET_SYNC_PHASE, long)  // set and return new sync_phase
#define dio24_get_sync_time(file_desc)                  ioctl(file_desc, DIO24_IOCTL_GET_SYNC_TIME, 0)      // return sync_time

#define dio24_get_extrig(file_desc, plong)              ioctl(file_desc, DIO24_IOCTL_GET_EXTRIG, plong)
#define dio24_set_extrig(file_desc, plong)              ioctl(file_desc, DIO24_IOCTL_SET_EXTRIG, plong)

#endif // NO_HARDWARE

#endif // DRIVER_H
