////////////////////////////////////////////////////////////////////////////////////////////////////
// dma.h 
// header for dma.c: DMA definitions & function declarations
// part of dio24 Linux kernel module for Digilent Cora/Arty FPGA-SoC
// created November 2018 by Andi
// compiled with petalinux 2020.1 on Ubuntu 20.04 LTS
// last change 2024/10/10 by Andi
////////////////////////////////////////////////////////////////////////////////////////////////////

#ifndef DMA_HEADER
#define DMA_HEADER

#include <linux/device.h>               // struct device
#include "dio24_driver.h"               // public driver definitions

//#define DEBUG_INFO                    // if defined creates dbg_info structure for each step

////////////////////////////////////////////////////////////////////////////////////////////////////
// exported macros
////////////////////////////////////////////////////////////////////////////////////////////////////

////////////////////////////////////////////////////////////////////////////////////////////////////
// DMA definitions
////////////////////////////////////////////////////////////////////////////////////////////////////

// define to use dma api (default) otherwise virt_to_phys and similar is used
#define USE_DMA_API

// definition of PHYS_HANDLE
#ifdef USE_DMA_API
#define PHYS_HANDLE            dma_addr_t
#else
#define PHYS_HANDLE            uint32_t
#endif

// data size and alignment (set in axi_dma IP, todo: can be read from device tree)
#define DATA_WIDTH              64              // stream data width in bits: 32-64 (default 32)
#define DATA_WIDTH_ALIGN        0x40            // alignment of data, must be power of 2, 0x20 for DATA_WIDTH=32, otherwise 0x40
#define DATA_BURST_SIZE         256             // number of maximum burst transactions, 2-256 (only powers of 2, default 16)
#define DATA_LENGTH_BITS        20              // width of buffer length register: 8-26, (default 14, 2^20 = 1MiB)

// DDR memory addresses and size
//#define BUF_SIZE        0xFF000               // size in bytes of buffer to be copied (max. 2^DATA_LENGTH_BITS-?, 1MiB-DDR_PAGE)
//#define BUF_SIZE        0x10000               // size in bytes of buffer to be copied (max. 2^DATA_LENGTH_BITS-?, 1MiB-DDR_PAGE)
//#define BUF_SIZE        0x3C                  // 15*4bytes = 60bytes
//#define DDR_SRC        0x10000000             // source address in DDR (max 64MiB)
//#define DDR_DST        0x14000000             // destination address in DDR (max 64MiB)
//#define DDR_PAGE        4096                  // one page of DDR (4kiB), todo: use PAGE_ALIGN instead!
//#define MAX_BUF_SAMPLES    512                // default DMA buffer allocation size in samples
#define MAX_BUF_SIZE            (4096*8-DATA_WIDTH_ALIGN)    // maximum usable DMA buffer size in bytes (DDR_PAGE - DATA_WIDTH_ALIGN)
//#define DMA_BUF_SIZE            (MAX_BUF_SIZE-(MAX_BUF_SIZE%DMA_BUF_MULT)) // usable bytes must be MAX_BUF_SIZE rounded down to next multiple of DMA_BUF_MULT
#define DMA_BUF_SIZE            (MAX_BUF_SIZE-(MAX_BUF_SIZE%DIO_BYTES_PER_SAMPLE))
#define DMA_BUF_SAMPLES         (DMA_BUF_SIZE/DIO_BYTES_PER_SAMPLE)
#define DSC_PACKET              25              // DMA descriptors per packet (marked by start and stop bits, #IRQs = #packets, >=1)
#define DSC_TX_NUM              100             // number of TX DMA descriptors (list dsc_TX, >=2, ensure DSC_TX_NUM/PACKET_DSC >> 1)
#define DSC_RX_NUM              100             // number of RX DMA descriptors (list dsc_RX, ensure NUM_DSC_RX/PACKET_DSC >> 1)
#define DSC_RX_ACTIVE           (DSC_RX_NUM/2)  // ideal number of active RX dsc's
#define DSC_RX_FULL             (DSC_RX_ACTIVE-2*DSC_PACKET) // maximum number of full buffers which can be stored. oldest buffers are deleted first.
#define MAX_WRITE_SIZE          128000000       // maximum total TX DMA allocation size (16M samples with 8bytes/sample)
#define MAX_READ_SIZE           0x4000000       // maximum total RX DMA allocation size (32MiB)

// scatter/getter settings
#define SG_ALIGN                0x40            // descriptors must be aligned on 16x32bit boundaries (fixed, must be power of 2)

// DMA registers (offset to mapped register memory region, see PG021_axi_dma.pdf)
#define DMA_REG_MM2S_CTRL       0x00            // offset MM2S control
#define DMA_REG_MM2S_STATUS     0x04            // offset MM2S status
#define DMA_REG_MM2S_CURR       0x08            // offset MM2S current SG descriptor lower bits
#define DMA_REG_MM2S_CURR_MSB   0x0C            // offset MM2S current SG descriptor upper bits
#define DMA_REG_MM2S_TAIL       0x10            // offset MM2S tail SG descriptor lower bits
#define DMA_REG_MM2S_TAIL_MSB   0x14            // offset MM2S tail SG descriptor upper bits
#define DMA_REG_MM2S_SRC        0x18            // offset MM2S simple DMA source address lower bits
#define DMA_REG_MM2S_SRC_MSB    0x1C            // offset MM2S simple DMA source address upper bits
#define DMA_REG_MM2S_LEN        0x28            // offset MM2S simple DMA length in bytes
#define DMA_REG_S2MM_CTRL       0x30            // offset S2MM control
#define DMA_REG_S2MM_STATUS     0x34            // offset S2MM status
#define DMA_REG_S2MM_CURR       0x38            // offset S2MM current SG descriptor lower bits
#define DMA_REG_S2MM_CURR_MSB   0x3C            // offset S2MM current SG descriptor upper bits
#define DMA_REG_S2MM_TAIL       0x40            // offset S2MM tail SG descriptor lower bits
#define DMA_REG_S2MM_TAIL_MSB   0x44            // offset S2MM tail SG descriptor upper bits
#define DMA_REG_S2MM_DST        0x48            // offset S2MM simple DMA destination address lower bits
#define DMA_REG_S2MM_DST_MSB    0x4C            // offset S2MM simple DMA destination address upper bits
#define DMA_REG_S2MM_LEN        0x58            // offset S2MM simple DMA length in bytes

// DMA control register bits
#define MM2S_CTRL_RUN           0x1
#define MM2S_CTRL_RSVD_1        0x2             // always 1
#define MM2S_CTRL_RESET         0x4
#define MM2S_CTRL_KEYHOLE       0x8
#define MM2S_CTRL_CYCLIC        0x10
#define MM2S_CTRL_RSVD_5        0x20            // always 0
#define MM2S_CTRL_RSVD_6        0x40            // always 0
#define MM2S_CTRL_RSVD_7        0x80            // always 0
#define MM2S_CTRL_RSVD_8        0x100           // always 0
#define MM2S_CTRL_RSVD_9        0x200           // always 0
#define MM2S_CTRL_RSVD_10       0x400           // always 0
#define MM2S_CTRL_RSVD_11       0x800           // always 0
#define MM2S_CTRL_IRQ_COMPLETE  0x1000
#define MM2S_CTRL_IRQ_DELAY     0x2000
#define MM2S_CTRL_IRQ_ERR       0x4000
#define MM2S_CTRL_RSVD_15       0x8000          // always 0
#define MM2S_CTRL_MASK          0x8ffe          // mask for TX_IS_OK: all without run and IRQ settings
#define MM2S_CTRL_EXPECT_RST    0x10002         // expected bits set for TX_IS_RESET
#define MM2S_CTRL_EXPECT_OK     0x2             // expected bits set for TX_IS_OK
#define MM2S_CTRL_IRQ_MASK      0x7000          // mask IRQ settings

#define S2MM_CTRL_RUN           0x1
#define S2MM_CTRL_RSVD_1        0x2             // always 1
#define S2MM_CTRL_RESET         0x4
#define S2MM_CTRL_KEYHOLE       0x8
#define S2MM_CTRL_CYCLIC        0x10
#define S2MM_CTRL_RSVD_5        0x20            // always 0
#define S2MM_CTRL_RSVD_6        0x40            // always 0
#define S2MM_CTRL_RSVD_7        0x80            // always 0
#define S2MM_CTRL_RSVD_8        0x100           // always 0
#define S2MM_CTRL_RSVD_9        0x200           // always 0
#define S2MM_CTRL_RSVD_10       0x400           // always 0
#define S2MM_CTRL_RSVD_11       0x800           // always 0
#define S2MM_CTRL_IRQ_COMPLETE  0x1000
#define S2MM_CTRL_IRQ_DELAY     0x2000
#define S2MM_CTRL_IRQ_ERR       0x4000
#define S2MM_CTRL_RSVD_15       0x8000          // always 0
#define S2MM_CTRL_MASK          0x8ffe          // mask for RX_IS_OK: all without run and IRQ settings
#define S2MM_CTRL_EXPECT_RST    0x10002         // expected bits set for RX_IS_RESET
#define S2MM_CTRL_EXPECT_OK     0x2             // expected bits set for RX_IS_OK
#define S2MM_CTRL_IRQ_MASK      0x7000          // mask IRQ settings

// DMA status register bits
#define MM2S_STATUS_HALTED      0x01
#define MM2S_STATUS_IDLE        0x02
#define MM2S_STATUS_RSVD_2      0x04            // always 0
#define MM2S_STATUS_SG          0x08
#define MM2S_STATUS_ERR_INT     0x10
#define MM2S_STATUS_ERR_SLV     0x20
#define MM2S_STATUS_ERR_DEC     0x40
#define MM2S_STATUS_RSVD_7      0x80            // always 0
#define MM2S_STATUS_ERR_SG_INT  0x100
#define MM2S_STATUS_ERR_SG_SLV  0x200
#define MM2S_STATUS_ERR_SG_DEC  0x400
#define MM2S_STATUS_RSVD_11     0x800           // always 0
#define MM2S_STATUS_IRQ_COMPLETE 0x1000
#define MM2S_STATUS_IRQ_DELAY   0x2000
#define MM2S_STATUS_IRQ_ERR     0x4000
#define MM2S_STATUS_RSVD_15     0x8000          // always 0
#define MM2S_STATUS_MASK        0xeff4          // mask for TX_IS_OK: all without halted, idle, SG, completed IRQ
#define MM2S_STATUS_EXPECT_RST  0x10009         // expected bits set for TX_IS_RESET
#define MM2S_STATUS_EXPECT_OK   0x0             // expected bits set for TX_IS_OK
#define MM2S_STATUS_IRQS        (MM2S_STATUS_IRQ_COMPLETE | MM2S_STATUS_IRQ_DELAY | MM2S_STATUS_IRQ_ERR) // IRQ bits

#define S2MM_STATUS_HALTED      0x01
#define S2MM_STATUS_IDLE        0x02
#define S2MM_STATUS_RSVD_2      0x04            // always 0
#define S2MM_STATUS_SG          0x08
#define S2MM_STATUS_ERR_INT     0x10
#define S2MM_STATUS_ERR_SLV     0x20
#define S2MM_STATUS_ERR_DEC     0x40
#define S2MM_STATUS_RSVD_7      0x80            // always 0
#define S2MM_STATUS_ERR_SG_INT  0x100
#define S2MM_STATUS_ERR_SG_SLV  0x200
#define S2MM_STATUS_ERR_SG_DEC  0x400
#define S2MM_STATUS_RSVD_11     0x800           // always 0
#define S2MM_STATUS_IRQ_COMPLETE 0x1000
#define S2MM_STATUS_IRQ_DELAY   0x2000
#define S2MM_STATUS_IRQ_ERR     0x4000
#define S2MM_STATUS_RSVD_15     0x8000          // always 0
#define S2MM_STATUS_MASK        0xeff4          // mask for RX_IS_OK: all without halted, idle, SG, completed IRQ
#define S2MM_STATUS_EXPECT_RST  0x10009         // expected bits set for RX_IS_RESET
#define S2MM_STATUS_EXPECT_OK   0x0             // expected bits set for RX_IS_OK
#define S2MM_STATUS_IRQS        (S2MM_STATUS_IRQ_COMPLETE | S2MM_STATUS_IRQ_DELAY | S2MM_STATUS_IRQ_ERR) // IRQ bits

// scatter/getter descriptor control register
#define SG_MM2S_CTRL_BYTES      0x03FFFFFF      // mask for transferred bytes
#define SG_MM2S_CTRL_END        0x04000000      // end of frame
#define SG_MM2S_CTRL_START      0x08000000      // start of frame
#define SG_S2MM_CTRL_BYTES      0x03FFFFFF      // mask for transferred bytes
#define SG_S2MM_CTRL_END        0x04000000      // end of frame (dont use)
#define SG_S2MM_CTRL_START      0x08000000      // start of frame (dont use)

// scatter/getter descriptor status register
#define SG_MM2S_STATUS_BYTES    0x03FFFFFF      // mask for transferred bytes
#define SG_MM2S_STATUS_ERR_INT  0x10000000      // internal error
#define SG_MM2S_STATUS_ERR_SLV  0x20000000      // slave error
#define SG_MM2S_STATUS_ERR_DEC  0x40000000      // decoder error
#define SG_MM2S_STATUS_COMPLETE 0x80000000      // completed
#define SG_MM2S_STATUS_MASK     (SG_MM2S_CTRL_BYTES) // expected status bits copied from control register
#define SG_S2MM_STATUS_BYTES    0x03FFFFFF      // mask for transferred bytes
#define SG_S2MM_STATUS_END      0x04000000      // end of frame
#define SG_S2MM_STATUS_START    0x08000000      // start of frame
#define SG_S2MM_STATUS_ERR_INT  0x10000000      // internal error
#define SG_S2MM_STATUS_ERR_SLV  0x20000000      // slave error
#define SG_S2MM_STATUS_ERR_DEC  0x40000000      // decoder error
#define SG_S2MM_STATUS_COMPLETE 0x80000000      // completed
// expected status bits copied from dsc control to dsc status
// todo: the end flag might be different from control if the PL sends less/more bytes than expected by prepare_RX
//       at the moment we assume this is not the case and the number of dsc is as expected.
#define SG_S2MM_STATUS_MASK    (SG_S2MM_CTRL_BYTES | SG_S2MM_STATUS_START | SG_S2MM_STATUS_END)

// pointer arithmetics
#define GET_ADDR(base, offset)              ((void*)(((char*)base) + (offset)))
#define GET_DMA_ADDR(offset)                GET_ADDR(dma24_reg_base, offset)
#define GET_DIO_ADDR(offset)                GET_ADDR(dio24_reg_base, offset)
#define GET_XADC_ADDR(offset)               GET_ADDR(xadc_reg_base , offset)

// write / read register
#define WRITE_DMA_REGISTER(offset, value)   iowrite32(value,GET_DMA_ADDR(offset))
#define READ_DMA_REGISTER(offset)           ioread32(GET_DMA_ADDR(offset))
#define WRITE_DIO_REGISTER(offset, value)   iowrite32(value,GET_DIO_ADDR(offset))
#define READ_DIO_REGISTER(offset)           ioread32(GET_DIO_ADDR(offset))
#define READ_DIO_REGS(buffer,count)         ioread32_rep(dio24_reg_base,buffer,count);
#define READ_XADC_REGISTER(offset)          ioread32(GET_XADC_ADDR(offset))

// set and reset register bits
#define SET_REGISTER_BIT(offset, bits)      WRITE_DMA_REGISTER(offset, READ_DMA_REGISTER(offset) | bits)
#define RESET_REGISTER_BIT(offset, bits)    WRITE_DMA_REGISTER(offset, READ_DMA_REGISTER(offset) & (~bits))

// check if cyclic = 1
#define TX_IS_CYCLIC(control)               (((control) & MM2S_CTRL_CYCLIC) == MM2S_CTRL_CYCLIC)
#define RX_IS_CYCLIC(control)               (((control) & S2MM_CTRL_CYCLIC) == S2MM_CTRL_CYCLIC)

// check if scatter/getter = 1
#define TX_IS_SG(status)                    (((status) & MM2S_STATUS_SG) == MM2S_STATUS_SG)
#define RX_IS_SG(status)                    (((status) & S2MM_STATUS_SG) == S2MM_STATUS_SG)

// check if idle = 1 (must be also running!)
#define TX_IS_IDLE(status)                  (((status) & MM2S_STATUS_IDLE) == MM2S_STATUS_IDLE)
#define RX_IS_IDLE(status)                  (((status) & S2MM_STATUS_IDLE) == S2MM_STATUS_IDLE)

// check if running: run/stop = 1, halted = 0
#define TX_IS_RUNNING(control, status)      ((((control) & MM2S_CTRL_RUN) == MM2S_CTRL_RUN) && (((status) & MM2S_STATUS_HALTED) == 0))
#define RX_IS_RUNNING(control, status)      ((((control) & S2MM_CTRL_RUN) == S2MM_CTRL_RUN) && (((status) & S2MM_STATUS_HALTED) == 0))

// check if in reset state (includes SG and CYCLIC bits)
#define TX_IS_RESET(control, status)        (((control) == MM2S_CTRL_EXPECT_RST) && ((status)  == MM2S_STATUS_EXPECT_RST))
#define RX_IS_RESET(control, status)        (((control) == S2MM_CTRL_EXPECT_RST) && ((status)  == S2MM_STATUS_EXPECT_RST))

// check if no error bits, IRQs and reserved bits are set
#define TX_IS_OK(control, status)           ((((control) & MM2S_CTRL_MASK   ) ==  MM2S_CTRL_EXPECT_OK) && \
                                             (((status)  & MM2S_STATUS_MASK ) ==  MM2S_STATUS_EXPECT_OK))
#define RX_IS_OK(control, status)           ((((control) & S2MM_CTRL_MASK   ) ==  S2MM_CTRL_EXPECT_OK) && \
                                             (((status)  & S2MM_STATUS_MASK ) ==  S2MM_STATUS_EXPECT_OK))
// settings for IRQs
#define TX_IRQ_SETTINGS                     (MM2S_CTRL_IRQ_COMPLETE | MM2S_CTRL_IRQ_ERR)
#define RX_IRQ_SETTINGS                     (S2MM_CTRL_IRQ_COMPLETE | S2MM_CTRL_IRQ_ERR)

// allocation of kernel memory and macros returning aligned addresses
// note on alignement:
// - descriptors must be SG_ALIGN aligned
// - buffers must be DATA_WIDTH_ALIGN aligned
// - the kernel.h ALIGN macro returns the next higher address aligned on given boundary (power of 2)
// - using __GFP_HIGHMEM does not change anything

// allocate buffer in normal kernel memory
#define MALLOC_USER_BUFFER(size)    kmalloc(size, GFP_KERNEL)
#define MALLOC_RECV_BUFFER(size)    kzalloc(size, GFP_KERNEL)        // zeros memory
#define FREE_USER_BUFFER(addr)      kfree(addr)
// allocate mem_info
#define MALLOC_MEM_INFO             kmalloc(sizeof(struct mem_info), GFP_KERNEL)
#define FREE_MEM_INFO(addr)         kfree(addr)
// allocate dsc_info
#define MALLOC_DSC_INFO             kmalloc(sizeof(struct dsc_info), GFP_KERNEL)
#define FREE_DSC_INFO(addr)         kfree(addr)

#ifdef USE_DMA_API

#include <linux/dma-mapping.h>      // dma_alloc_coherent, dma_map_sg, etc.

#define PHYS_HANDLE                 dma_addr_t

#define MALLOC_BUFFER(addr, handle) addr = dma_alloc_coherent(dio24_dev, DMA_BUF_SIZE+DATA_WIDTH_ALIGN-1, &handle, GFP_KERNEL)
#define FREE_BUFFER(addr, handle)   dma_free_coherent(dio24_dev, DMA_BUF_SIZE+DATA_WIDTH_ALIGN-1, addr, handle)

// TODO: use dma_pool here for small memory (<page)
#define MALLOC_DSC(addr, handle)    addr = dma_alloc_coherent(dio24_dev, sizeof(struct SG_dsc)+SG_ALIGN-1, &handle, GFP_KERNEL)
#define FREE_DSC(addr, handle)      dma_free_coherent(dio24_dev, sizeof(struct SG_dsc)+SG_ALIGN-1, addr, handle)

#else

#include <asm/io.h>                 // ioremap, iounmap, virt_to_phys, phys_to_virt (replaced by dma api)

#define PHYS_HANDLE                 uint32_t

#define MALLOC_BUFFER(addr,handle)  {addr = kmalloc(BUF_SIZE+DATA_WIDTH_ALIGN-1, GFP_KERNEL); handle = virt_to_phys(addr);}
#define FREE_BUFFER(addr,handle)    kfree(addr)

#define MALLOC_DSC(addr,handle)     {addr = kmalloc(sizeof(struct SG_dsc)+SG_ALIGN-1, GFP_KERNEL); handle = virt_to_phys(addr);}
#define FREE_DSC(addr,handle)       kfree(addr)

#endif

#define GET_ALIGNED_BUFFER(addr)        ((uint32_t*)ALIGN((uint32_t)addr,DATA_WIDTH_ALIGN))
#define GET_ALIGNED_PHYS_BUFFER(phys)   (uint32_t)GET_ALIGNED_BUFFER(phys)
#define GET_ALIGNED_DSC(addr)           (struct SG_dsc *)ALIGN((uint32_t)addr,SG_ALIGN)
#define GET_ALIGNED_PHYS_DSC(phys)      (uint32_t)GET_ALIGNED_DSC(phys)
#define IS_ALIGNED_BUFFER(addr)         ((((uint32_t)(addr)) & (DATA_WIDTH_ALIGN-1)) == 0)
#define IS_ALIGNED_DSC(addr)            ((((uint32_t)(addr)) & (SG_ALIGN-1)) == 0)

// get time
//#define GET_TIME(act)            (((float)act)/HZ)
//#define GET_S(act)            (act)
// get time difference in ms
//#define GET_MS(start, end)        ((int32_t)(end)-(int32_t)(start))*1000/HZ
#define TIME_DATA                   struct timeval
#define SET_TIME(t,sec,usec)        { t.tv_sec=sec; t.tv_usec=usec; }
#define GET_SEC(t)                  t.tv_sec
#define GET_USEC(t)                 t.tv_usec
#define GET_TIME(t)                 do_gettimeofday(&t)
#define GET_ACT_US(t)               (((long long)t.tv_usec) + ((long long)t.tv_sec)*1000000)
#define GET_US(start,stop)          (GET_ACT_US(stop)-GET_ACT_US(start))

////////////////////////////////////////////////////////////////////////////////////////////////////
// FPGA definitions
////////////////////////////////////////////////////////////////////////////////////////////////////

// FPGA TX and RX FIFO size in samples
#define DIO_TX_FIFO_SIZE            8192
#define DIO_RX_FIFO_SIZE            8192

// the first TX irq is issued with DIO_FPGA_START_DSC descriptors which is as close as possible to TX FIFO samples
// this allows with START_FPGA_DELAYED to start the FPGA with nearly full TX FIFO
#define _DIO_FPGA_START_DSC         (DIO_TX_FIFO_SIZE - DIO_TX_FIFO_SIZE%DMA_BUF_SAMPLES)/DMA_BUF_SAMPLES
#if DSC_PACKET < _DIO_FPGA_START_DSC
    // DSC_PACKET has fewer samples than in TX FIFO:
    // round to nearest multiple of DSC_PACKET
    #define DIO_FPGA_START_DSC      (_DIO_FPGA_START_DSC - _DIO_FPGA_START_DSC%DSC_PACKET)
#else
    // DSC_PACKET has more samples than in TX FIFO: 
    // the first irq is issued at fewer samples and only all next are issued with DSC_PACKET.
    #define DIO_FPGA_START_DSC      _DIO_FPGA_START_DSC
#endif

// wakeup reading user thread when data available or FPGA end or FPGA error
//#define DIO_STATUS_WAKEUP_MASK      (DIO_STATUS_ERROR|DIO_STATUS_END|DIO_STATUS_RUN|DIO_STATUS_READY)
//#define DIO_STATUS_WAKEUP_NEQ       (DIO_STATUS_RUN|DIO_STATUS_READY)
//#define DIO_WAKEUP(bt, st)          ((bt > 0) || ((st & DIO_STATUS_WAKEUP_MASK) != DIO_STATUS_WAKEUP_NEQ))
#define DIO_WAKEUP(bytes, status)     ( (bytes > 0) || ((status & (DIO_STATUS_RUN|DIO_STATUS_WAIT)) == 0) )

// clock periods in ps TODO: update
#define INIT_EXT_IN_PERIOD_PS       100000      // initial external input  = 10MHz (defined by clock wizard 0)
#define BUS_CLOCK_PERIOD_PS         10000       // initial bus clock = 100MHz (defined by clock wizard 2)
#define INIT_EXT_OUT_PERIOD_PS      100000      // initial external output = 10MHz (defined by clock wizard 2)

// limits in MHz for MMCM (see xapp888 samples files)
#define MMCM_F_VCO_MIN              600.0
#define MMCM_F_VCO_MAX              1200.0
#define MMCM_F_PFD_MIN              10.0
#define MMCM_F_PFD_MAX              450.0
#define MMCM_F_IN_MIN               10.0
#define MMCM_F_IN_MAX               800.0
#define MMCM_F_OUT_MIN              (600.0/128)
#define MMCM_F_OUT_MAX              800.0
#define MMCM_MUL_MIN_FRAC           1.0
#define MMCM_MUL_MAX_FRAC           255.875
#define MMCM_MUL_STEP_FRAC          0.125
#define MMCM_DIV_MIN_FRAC           1.0
#define MMCM_DIV_MAX_FRAC           255.875
#define MMCM_DIV_STEP_FRAC          0.125
#define MMCM_MUL_MIN                2
#define MMCM_MUL_MAX                64
#define MMCM_MUL_STEP               1
#define MMCM_DIV_MIN                1
#define MMCM_DIV_MAX                106
#define MMCM_DIV_STEP               1
#define MMCM_OUT_DIV_MIN            1
#define MMCM_OUT_DIV_MAX            128
#define MMCM_OUT_DIV_STEP           1

// limits in MHz for PLL (see xapp888 samples files)
#define PLL_F_VCO_MIN               800.0
#define PLL_F_VCO_MAX               1600.0
#define PLL_F_PFD_MIN               19.0
#define PLL_F_PFD_MAX               450.0
#define PLL_F_IN_MIN                19.0
#define PLL_F_IN_MAX                800.0
#define PLL_F_OUT_MIN               (800.0/128)
#define PLL_F_OUT_MAX               800.0
#define PLL_MUL_MIN                 2
#define PLL_MUL_MAX                 64
#define PLL_MUL_STEP                1
#define PLL_DIV_MIN                 1
#define PLL_DIV_MAX                 56
#define PLL_DIV_STEP                1
#define PLL_OUT_DIV_MIN             1
#define PLL_OUT_DIV_MAX             128
#define PLL_OUT_DIV_STEP            1

// number of clock wizards with AXI Light channels
#define CLK_WIZ_NUM                 2

// clock wizard channel names
#define CLOCK_EXT_IN                "clk_out1"
#define CLOCK_EXT_OUT               "clk_out"
#define CLOCK_BUS_OUT               "clk_bus"
#define CLOCK_STRB_0                "clk_strb0"
#define CLOCK_STRB_1                "clk_strb1"

// PLL types
#define CLK_WIZ_NONE                0
#define CLK_WIZ_PLL                 1
#define CLK_WIZ_MMCM                2

////////////////////////////////////////////////////////////////////////////////////////////////////
// structures
////////////////////////////////////////////////////////////////////////////////////////////////////

// scatter-getter descriptor 
// must be aligned on SG_ALIGN boundaries in physical memory
struct SG_dsc {
    uint32_t next_low;
    uint32_t next_high;
    uint32_t address_low;
    uint32_t address_high;
    uint32_t reserved_0;
    uint32_t reserved_1;
    uint32_t control;
    uint32_t status;
    // note: APP0..4 are used only when control/status streams are enabled
    uint32_t app0;
    uint32_t app1;
    uint32_t app2;
    uint32_t app3;
    uint32_t app4;
};

// clock wizard channel information
// at the moment contains only pointer to names but maybe need later more info (frequency settings?)
struct clk_wiz_channel {
    char * name;                        // channel is identified by name. do not free!
};

struct clk_wiz_data {                   // pdata of clock wizard
    void __iomem *base_addr;            // address register base
    int index;                          // clock wizard index
    uint32_t PLL_type;                  // CLK_WIZ_PLL or CLK_WIZ_MMCM (read from device tree)
    uint32_t in_ps;                     // input period in ps (read from device tree)
    uint32_t VCO_ps;                    // actual VCO period in ps (0 if not set)
    int32_t num;                        // number of channels in array
    struct clk_wiz_channel *channel;    // array of num channels
};

// device specific data
#define TYPE_DIO24	    0       // timing module
#define	TYPE_DMA24	    1       // DMA module
#define TYPE_XADC	    2       // XADC
#define TYPE_CLK_W  	3       // clock wizard
struct device_info {
	int type;	    // dio24/dma24/XADC/CWZ
	char name[6];	// displayed device name
	int num_irq;	// number of used irq's
    void *pdata;    // additional data (pointer to array of channels of clock wizard device)
	void __iomem **p_base_addr; // location where to save base address
};

// structure to save helper tasks and register content for IRQ
#define HELPER_STATUS_TX            0                // DMA_REG_MM2S_STATUS register at IRQ
#define HELPER_STATUS_RX            1                // DMA_REG_S2MM_STATUS register at IRQ
//#define HELPER_STATUS_FPGA        2                // FPGA status register at IRQ
//#define HELPER_STATUS_SEC         2                // seconds at IRQ
//#define HELPER_STATUS_USEC        3                // us at IRQ
#define HELPER_STATUS_NUM_IRQ       2                // number of merged IRQ's per helper_task
#define HELPER_TASK_NUM_STATUS_IRQ  HELPER_STATUS_NUM_IRQ        // number of entries in status for irq_ack
#define HELPER_TASK_NUM_STATUS      (HELPER_STATUS_NUM_IRQ+1)    // number of entries in status for irq_hdl
struct helper_task {
    int task;                       // task: see HELPER_TASK_ definitions
    uint32_t status[HELPER_TASK_NUM_STATUS];    // status registers and counter of IRQ
    struct helper_task *next;       // pointer to next task or NULL
};

struct dsc_info;                    // used by mem_info

// single linked list of DMA buffers
// DMA buffers = user data copied into buffers of DMA_BUF_SIZE bytes
struct mem_info {
    void *virt_addr;                // virtual address of unaligned DMA buffer
    PHYS_HANDLE phys_addr;          // physical handle of unaligned DMA buffer
    uint32_t bytes;                 // number of transmitted bytes in buffer, 0 initially, allocated DMA_BUF_SIZE
    struct mem_info *next;          // next entry in list or NULL
    unsigned ref_cnt;               // counts number of dsc's using buffer (0=none, 1=one, can be >1 when reps>0 and few samples)
};
struct mem_list {
    struct mem_info *first;         // first buffer in list
    struct mem_info *last;          // last buffer in list (last->next = NULL)
    struct mem_info *next;          // next not sent buffer in list, NULL if all sent.
};

// single linked list of descriptors (ring-buffer)
// descriptors = information where DMA buffers are located in memory.
//               there are NUM_DSC descriptors per RX and TX channels.
//               descriptors are used for active DMA or its preparation. 
struct dsc_info {
    void *virt_addr;                // virtual address of unaligned descriptor
    PHYS_HANDLE phys_addr;          // physical handle of unaligned descritor
    struct mem_info *buffer;        // pointer to DMA buffer, NULL when not used.
    struct dsc_info *next;          // next entry in list, last points to first.
};
struct dsc_list {
    struct dsc_info *head;          // first descriptor in list, cannot be NULL
    struct dsc_info *tail;          // last started descriptor in list, tail->next == head when none started
    struct dsc_info *last_prep;     // last prepared descriptor in list, NULL if none prepared
};

////////////////////////////////////////////////////////////////////////////////////////////////////
// XADC register offset
////////////////////////////////////////////////////////////////////////////////////////////////////

#define XADC_TEMP_ACT               0x200
#define XADC_TEMP_MAX               0x280
#define XADC_TEMP_MIN               0x290
#define XADC_TEMP_ALARM_UPPER       0x340
#define XADC_TEMP_ALARM_LOWER       0x350

////////////////////////////////////////////////////////////////////////////////////////////////////
// Clock wizard register offset
////////////////////////////////////////////////////////////////////////////////////////////////////

#define CLK_WIZ_REG_RESET           0x000
#define CLK_WIZ_REG_STATUS          0x004
#define CLK_WIZ_REG_STATUS_ERR      0x008
#define CLK_WIZ_REG_STATUS_IRQ      0x00C
#define CLK_WIZ_REG_IRQ_EN          0x010
#define CLK_WIZ_REG_FB_MUL_DIV      0x200
#define CLK_WIZ_REG_FB_PHASE        0x204
#define CLK_WIZ_REG_OUT_0_DIV       0x208
#define CLK_WIZ_REG_OUT_0_PHASE     0x20C
#define CLK_WIZ_REG_OUT_0_DUTY      0x210
#define CLK_WIZ_REG_OUT_1_DIV       0x210
#define CLK_WIZ_REG_OUT_1_PHASE     0x210
#define CLK_WIZ_REG_OUT_1_DUTY      0x21C
#define CLK_WIZ_REG_OUT_2_DIV       0x220
#define CLK_WIZ_REG_OUT_2_PHASE     0x224
#define CLK_WIZ_REG_OUT_2_DUTY      0x228
#define CLK_WIZ_REG_OUT_3_DIV       0x22C
#define CLK_WIZ_REG_OUT_3_PHASE     0x230
#define CLK_WIZ_REG_OUT_3_DUTY      0x234
#define CLK_WIZ_REG_OUT_4_DIV       0x238
#define CLK_WIZ_REG_OUT_4_PHASE     0x23C
#define CLK_WIZ_REG_OUT_4_DUTY      0x240
#define CLK_WIZ_REG_OUT_5_DIV       0x244
#define CLK_WIZ_REG_OUT_5_PHASE     0x248
#define CLK_WIZ_REG_OUT_5_DUTY      0x24C
#define CLK_WIZ_REG_OUT_6_DIV       0x250
#define CLK_WIZ_REG_OUT_6_PHASE     0x254
#define CLK_WIZ_REG_OUT_6_DUTY      0x258
#define CLK_WIZ_REG_LOAD_SEN        0x25C

////////////////////////////////////////////////////////////////////////////////////////////////////
// shared variables (see driver.c)
////////////////////////////////////////////////////////////////////////////////////////////////////

extern struct mutex user_mutex;     // user (and helper) mutex ensures consistency of DMA/FPGA structures
//extern struct FPGA_status status;   // actual DMA and FPGA status
extern uint32_t dio_ctrl;
extern uint32_t dio_status;
extern uint32_t dio_time;
extern uint32_t dio_samples;
extern uint32_t dio_cycles;
extern uint32_t dio_irq;
extern uint32_t set_samples;
extern uint32_t set_cycles;
extern int32_t  dio_err;
extern uint32_t dma_ctrl;
extern uint32_t dma_reps_act;
extern uint32_t dma_status_TX, dma_status_RX;
extern uint8_t  dma_dsc_TX_p, dma_dsc_TX_a, dma_dsc_TX_c;
extern uint8_t  dma_dsc_RX_p, dma_dsc_RX_a, dma_dsc_RX_c;
extern int32_t  dma_err_TX, dma_err_RX;
extern uint32_t dma_irq_TX, dma_irq_RX;
extern uint32_t dma_TX_bt_tot, dma_RX_bt_tot;
extern uint32_t dma_RD_bt_max, dma_RD_bt_act, dma_RD_bt_drop;
extern uint32_t dma_timeout;
extern uint32_t dma_bt_tot;

// additional variables for show_status but not in FPGA_status
// irq helper counters should be 0, otherwise merging of irq's happened
extern uint32_t irq_FPGA_merged;            // active irq counter FPGA
extern uint32_t irq_TX_merged;              // active irq counter TX
extern uint32_t irq_RX_merged;              // active irq counter RX

typedef union {
        uint32_t data32[DIO_BYTES_PER_SAMPLE/4];
        uint8_t data8[DIO_BYTES_PER_SAMPLE];
} last_sample_t;
extern last_sample_t dma_last_sample;


// single-linked lists of DMA buffers and descriptors
extern struct mem_list mem_TX;
extern struct mem_list mem_RX;
extern struct dsc_list dsc_TX;
extern struct dsc_list dsc_RX;

// this is set to 1L by DMA24_IOCTL_STOP to stop self_test
// todo: is there a better way?
//extern bool st_stop;

// dma24 device registers
extern void __iomem *dma24_reg_base;
extern struct device *dio24_dev;        // device structure

// dio24 device registers
extern void __iomem *dio24_reg_base;

// XADC device registers
extern void __iomem *xadc_reg_base;

// debug counter in dma.c
#define DBG_TX_DSC                  0
#define DBG_RX_DSC                  1
#define DBG_TX_BUF                  2
#define DBG_RX_BUF                  3
#define DBG_BUF_POOL                4
#define DBG_TEST                    5
#define DBG_NUM                     (DBG_TEST+1)
extern unsigned debug_DMA_count[DBG_NUM];

////////////////////////////////////////////////////////////////////////////////////////////////////
// exported functions
// all return 0 on success, otherwise error code
////////////////////////////////////////////////////////////////////////////////////////////////////

// device init and removal
//void device_init(bool is_dma24);
//void device_remove(bool is_dma24);

// IRQ functions
//void irq_enable(void); // enable irq's (called by init)
//void irq_disable(void); // disable irq's (called by remove)
//void irq_ack_TX(uint32_t status_irq[HELPER_TASK_NUM_STATUS_IRQ]);    // call from TX IRQ, for status see HELPER_STATUS defines
//void irq_ack_RX(uint32_t status_irq[HELPER_TASK_NUM_STATUS_IRQ]);    // call from RX IRQ, for status see HELPER_STATUS defines
//void irq_ack_FPGA(uint32_t status_irq[HELPER_TASK_NUM_STATUS_IRQ]);    // call from FPGA IRQ, for status see HELPER_STATUS defines
// executed by helper thread:
//void irq_hdl_DMA(uint32_t status_irq[HELPER_TASK_NUM_STATUS]);    // do not call from IRQ routine but from helper thread
//void irq_hdl_DMA(void);    // do not call from IRQ routine but from helper thread
//void irq_hdl_FPGA(uint32_t status_irq[HELPER_TASK_NUM_STATUS]);    // do not call from IRQ routine but from helper thread
void irq_hdl_TX(void);    // do not call from IRQ routine but from helper thread
void irq_hdl_RX(void);    // do not call from IRQ routine but from helper thread

// restarts repetitions if transmission finished and repetitions enabled
//int restart_reps(void);

// status info
// int read_status(void);
// update actual status info
void show_status(struct FPGA_status *status);

// set dio24 control register and return new value
int set_config(uint32_t *config);

// set FPGA clock to external (true) or internal (false)
int set_ext_clk_FPGA(bool external);

// copy available RX data into user buffer
// returns number of copied bytes or <0 on error
ssize_t copy_RX(char __user * buffer, size_t length);

// start/stop/reset FPGA
int start_FPGA(uint32_t flags);
int stop_FPGA(void);
int reset_FPGA(void);

// start/stop DMA transfer
int start_TX(void);                 // start transmission
int start_RX(void);                 // start receiving
int stop_TX(bool reset_on_error);   // stops transmission
int stop_RX(bool reset_on_error);   // stops receiving
//int stop_all(void);

// reset
int reset_TX(void);                 // reset TX channel (affects also RX)
int reset_RX(void);                 // reset RX channel (affects also TX)
int reset_all(void);                // reset DMA to initial state. call on error!

// append NOP samples to last buffer if needed
long append_TX(void);

// copies user buffer of length bytes into list mem_TX of TX DMA buffers
// if buffer == NULL called from self_test and buffers are initialized with test pattern
// returns 0 if ok, otherwise error code
// ATTENTION: must be called with user_mutex locked!
ssize_t prepare_TX_buffers(const char __user *buffer, size_t length);

// prepares list mem_RX of RX DMA buffers to have at least total length bytes available
// if shrink=true then a larger existing buffer is reduced in size, otherwise not
// returns 0 if ok, >0 if warning, <0 error
// ATTENTION: must be called with user_mutex locked!
ssize_t prepare_RX_buffers(size_t length, bool shrink);

// free allocated TX/RX buffer and descriptors starting from 'first'
//void free_mem(struct mem_info *first, struct mem_info *last);

// checks and prints descriptor and memory information
int check_dsc(struct dsc_list *list, char *title);
int check_mem(struct mem_list *list, bool show, bool test_data);

// allocate and free dscs
struct dsc_info *allocate_dsc(int num_dsc, unsigned index);
int free_dsc_no_pool(struct dsc_info *head, unsigned index);

// set the clock period in ps of the channel with the given name
// returns 0 on success and out_ps is set to actual period in ps.
// returns nonzero on error
#define SET_CLOCK_VCO                   1       // configure VCO (use with SET_CLOCK_OUT or SET_CLOCK_OUT_PART)
#define SET_CLOCK_OUT_LOAD              2       // configure output divider and load into MMCM/PLL
#define SET_CLOCK_OUT_PART              0       // configure output divider but do not load into MMCM/PLL
#define SET_CLOCK_WAIT_LOCK             4       // wait until lock is established
#define SET_CLOCK_RESET                 8       // reset before programming
#define SET_CLOCK_RESET_IF_NOT_LOCKED   16      // reset before programming if not locked
#define CLK_WIZ_LOCKED                  0x1     // locked status
#define CLK_WIZ_RESET                   0xA     // software reset
int set_clock(char *channel, uint32_t *out_ps, unsigned flags);

// find clock wizard and channel number
struct clk_wiz_data *find_clock(char *channel, uint32_t *num);


#endif                              // DMA_HEADER
