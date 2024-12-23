////////////////////////////////////////////////////////////////////////////////////////////////////
// driver.c
// dio24 Linux kernel module for Digilent Cora/Arty FPGA-SoC
// created September 2018 by Andi
// compiled with Petalinux 2020.1 on Ubuntu 20.04 LTS
// modified by Andi from Xilinx tutorial UG1165 blink.h/blink.c
// last change 20/11/2024 by Andi
////////////////////////////////////////////////////////////////////////////////////////////////////

#include <linux/kernel.h>                   // printk, pr_err, etc.
#include <linux/init.h>                     // module_init, module_exit
#include <linux/module.h>                   // kernel version, THIS_MODULE
#include <linux/version.h>                  // LINUX_VERSION_CODE, KERNEL_VERSION macros

#include <linux/fs.h>

#include <linux/slab.h>                     // kmalloc, kfree
#include <linux/io.h>
#include <linux/interrupt.h>
#include <linux/jiffies.h>                  // jiffies

#include <linux/of_address.h>
#include <linux/of_device.h>
#include <linux/of_platform.h>
#include <linux/of_reserved_mem.h>

//#include <asm/uaccess.h>                  // get_user, put_user, copy_to_user (deprecated?)
#include <linux/uaccess.h>                  // copy_to_user
#include <asm/io.h>                         // ioremap, iounmap
#include <asm/page.h>                       // PAGE_SIZE

#include <linux/wait.h>                     // wait functions
#include <linux/spinlock.h>                 // spinlock used for main thread
#include <linux/mutex.h>                    // mutex for user lock
#include <linux/semaphore.h>                // semaphore used for helper thread
#include <linux/kthread.h>                  // kernel thread functions
#include <linux/sched.h>                    // scheduler for changing scheduling scheme
#include <linux/delay.h>                    // udelay, mdelay

#include "dma.h"                            // DMA definitions & function declarations

#ifdef USE_DMA_API
#include <linux/dma-mapping.h>              // dma_alloc_coherent, dma_map_sg, etc.
#endif

///////////////////////////////////////////////////////////////////////////////////////////////////////////////
// module macros
///////////////////////////////////////////////////////////////////////////////////////////////////////////////

#define DEBUG_INFO                          // if defined print debug info (todo: use!)

// driver info strings
#define DRIVER_INFO         "Linux kernel module for Cora-Z7-10 FPGA by Andi"
#define DRIVER_AUTHOR       "Andi"
#define DRIVER_LICENCE      "GPL"

// name used in all pr_err statements
#define NAME_DRV            "DIOdrv "       // IOCTL, read, write functions
#define NAME_DIO            "DIOio  "       // IOCTL, read, write functions
#define NAME_DMA            "DIOdma "       // IOCTL, read, write functions
#define NAMEH               "DIOhlp "       // helper thread

//#define USE_COMMAND_LINE_ARGS             // if defined use command line arguments (for testing)

#define SUCCESS             0
#define FAILED              -1

// maximum number of IRQs
#define NUM_IRQ_MAX         2               // we need TX and RX irq's

// maximum buffer size for ioctl data
#define MAX_BUF             100

// helper tasks (bitwise allows multiple tasks)
//#define HELPER_TASKS_NUM        20          // pre-allocated number of helper tasks
#define HELPER_TASK_NONE        0           // indicates end of helper tasks. dont use!
#define HELPER_TASK_IRQ_TX      1           // handle DMA TX IRQ
#define HELPER_TASK_IRQ_RX      2           // handle DMA RX IRQ
#define HELPER_TASK_IRQ_FPGA    4           // handle FPGA IRQ end or error state
#define HELPER_TASK_TEST        8           // testing function for debugging
#define HELPER_TASK_EXIT        16          // exit thread

// increment void *
#define INC(pvoid)    (pvoid = (void*)(((char*)pvoid) + 1))

///////////////////////////////////////////////////////////////////////////////////////////////////////////////
// structure and function declarations
///////////////////////////////////////////////////////////////////////////////////////////////////////////////

// local module parameters
struct dio24_local {
    int id;                                 // device id 0=dma, 1=dio
    int irq[NUM_IRQ_MAX];
    uint32_t mem_start;                     // physical memory start address
    uint32_t mem_end;                       // physical memory end address
    //void __iomem *base_addr;              // update: saved in global memory
    struct device_info *data;               // device specific data
};

// DIO file operation functions
int     dio24_open(struct inode *inode, struct file *file);
int     dio24_release(struct inode *inode, struct file *file);
ssize_t dio24_read(struct file *file, char __user * buffer, size_t length, loff_t * offset);

// DMA file operation functions
int     dma24_open(struct inode *inode, struct file *file);
int     dma24_release(struct inode *inode, struct file *file);
ssize_t dma24_read(struct file *file, char __user * buffer, size_t length, loff_t * offset);
ssize_t dma24_write(struct file *file, const char __user * buffer, size_t length, loff_t * offset);
long    dma24_ioctl(struct file *file, unsigned int ioctl_num, unsigned long ioctl_param);
int     dma24_mmap(struct file *file_p, struct vm_area_struct *vma);

// device driver functions
int     dio24_probe(struct platform_device *pdev);
int     dio24_remove(struct platform_device *pdev);

// helper thread functions
//int     create_helper_tasks(void);
//void    add_helper_task(int task, struct helper_task *task, bool is_irq);
int     helper_thread(void *data);

///////////////////////////////////////////////////////////////////////////////////////////////////////////////
// globals
///////////////////////////////////////////////////////////////////////////////////////////////////////////////

MODULE_DESCRIPTION(DRIVER_INFO);
MODULE_AUTHOR(DRIVER_AUTHOR);
MODULE_LICENSE(DRIVER_LICENCE);

struct mutex user_mutex;                    // user (and helper) mutex ensures consistency of DMA structures (shared with dma.c)
DECLARE_WAIT_QUEUE_HEAD(dio24_queue);       // wait queue to wakeup waiting user in dio24_read()
DECLARE_WAIT_QUEUE_HEAD(dma24_queue);       // wait queue to wakeup waiting user in dma24_read()

// helper thread
struct task_struct *helper = NULL;          // helper thread
DEFINE_SPINLOCK(helper_task_lock);          // protects helper_task
struct semaphore helper_semaphore;          // blocks helper thread until IRQ or stop request
struct helper_task *helper_task_first = NULL;   // first used entry of helper tasks ringbuffer
struct helper_task *helper_task_last = NULL;    // last used entry of helper tasks ringbuffer
uint32_t helper_tasks = 0;                  // counts actual number of used helper tasks in ringbuffer
uint32_t helper_tasks_max = 0;              // maximum number of used helper tasks in ringbuffer

int dio24_major_num = 0;                    // major device number
int dma24_major_num = 0;                    // major device number
int dio24_is_open = 0;                      // 1 if already open
int dma24_is_open = 0;                      // 1 if already open

// shared with dma.c and protected by user_mutex. content of struct FPGA_status.
//struct FPGA_status status;
// FPGA
uint32_t dio_ctrl;
uint32_t dio_status;
uint32_t dio_samples;
uint32_t dio_cycles;
uint32_t dio_time; 
int32_t  dio_err;
uint32_t dio_irq;
uint32_t dio_phase_ext, dio_phase_det;
uint32_t set_samples;
uint32_t set_cycles;
// DMA
uint32_t dma_ctrl;
uint32_t dma_status_TX, dma_status_RX;
uint32_t dma_reps_act;
uint8_t  dma_dsc_TX_p, dma_dsc_TX_a, dma_dsc_TX_c;
uint8_t  dma_dsc_RX_p, dma_dsc_RX_a, dma_dsc_RX_c;
int32_t  dma_err_TX, dma_err_RX;
uint32_t dma_irq_TX, dma_irq_RX;
uint32_t dma_TX_bt_tot, dma_RX_bt_tot;
uint32_t dma_RD_bt_max, dma_RD_bt_act, dma_RD_bt_drop;
uint32_t dma_timeout = 0; // timeout in ms
uint32_t dma_bt_tot;
last_sample_t dma_last_sample;

// irq status variables for helper thread protected by spinlock 
uint32_t irq_FPGA_count     = 0L;               // active irq counter FPGA
uint32_t irq_TX_count       = 0L;               // active irq counter TX
uint32_t irq_RX_count       = 0L;               // active irq counter RX
uint32_t irq_FPGA_merged    = 0L;               // merged irq counter FPGA
uint32_t irq_TX_merged      = 0L;               // merged irq counter TX
uint32_t irq_RX_merged      = 0L;               // merged irq counter RX
uint32_t irq_TX_status      = 0L;               // active irq status TX
uint32_t irq_RX_status      = 0L;               // active irq status RX

// temperature reading needs to be done twice at first time
bool first_time = true;

// read by dio24_read and updated by helper on last dio24_irq. protected by FPGA_spin_lock
//struct FPGA_status_run status_run;    // status registers // update: changed from FPGA_read_data
DEFINE_SPINLOCK(FPGA_spin_lock);            // protects status_run

// timeout for dio24_read in ms
//uint32_t dio24_timeout = IRQ_FREQ_MIN_TIMEOUT;

// dma24 device
void __iomem *dma24_reg_base = NULL;        // mapped base address of registers
struct device *dio24_dev = NULL;            // device structure used for DMA API calls
const struct device_info dma24_info = {     // device data used for probing/remove
    .type = TYPE_DMA24,
    .name = "dma24",
    .num_irq = 2,
    .pdata = NULL,
    .p_base_addr = &dma24_reg_base,
};

// dio24 device
void __iomem *dio24_reg_base = NULL;        // mapped base address of registers
const struct device_info dio24_info = {     // device data used for probing/remove
    .type = TYPE_DIO24,
    .name = "dio24",
    .num_irq = 1,
    .pdata = NULL,
    .p_base_addr = &dio24_reg_base,
};

// XADC device
void __iomem *xadc_reg_base = NULL;
const struct device_info xadc_info = {      // device data used for probing/remove
    .type = TYPE_XADC,
    .name = "XADC",
    .num_irq = 0,
    .pdata = NULL,
    .p_base_addr = &xadc_reg_base,
};

// clock wizard
//uint32_t clk_wiz_num = 0;                 // number of clock wizards
struct clk_wiz_data *clk_wiz_pdata[CLK_WIZ_NUM] = {NULL,NULL}; // global array of pointers to clock wizard data
const struct device_info clk_wiz_info = {   // device data used for probing/remove
    .type = TYPE_CLK_W,
    .name = "Clk_W",
    .num_irq = 0,
    .pdata = NULL,                          // pointer to individual struct clk_wiz_data
    .p_base_addr = NULL,                    // not used by clock wizard
};

// find clock wizard and channel number matching channel name
struct clk_wiz_data *find_clock(char *channel, uint32_t *num) {
    struct clk_wiz_data *wiz = NULL;
    int i, ch, k;
    for (i = 0; i < CLK_WIZ_NUM; ++i) {
        if (clk_wiz_pdata[i]) {
            wiz = clk_wiz_pdata[i];
            if (wiz->channel) {
                for (ch = 0; ch < wiz->num; ++ch) {
                    for (k = 0; (wiz->channel[ch].name[k] == channel[k]); ++k) {
                        if (channel[k] == '\0') { // found
                            *num = ch;
                            return wiz;
                        }
                    }
                }
            }
        }
    }
    // not found
    return NULL;
}


// file operations for dma24 char device (NULL for unused functions)
struct file_operations dma24_fops = {
    .owner = THIS_MODULE,       
    .read = dma24_read,
    .write = dma24_write,
    .unlocked_ioctl = dma24_ioctl,
    .open = dma24_open,
    .release = dma24_release, 
    .mmap = dma24_mmap,
};

// file operations for dio24 char device (NULL for unused functions)
struct file_operations dio24_fops = {
    .owner = THIS_MODULE,       
    .read = dio24_read,
    .write = NULL,
    .unlocked_ioctl = NULL,
    .open = dio24_open,
    .release = dio24_release, 
};

#ifdef CONFIG_OF
// must match device tree compatible entry (see pl.dtsi)
struct of_device_id dio24_of_match[] = {
    { .compatible = "xlnx,axi-dma-1.00.a" , .data = &dma24_info   },    // dma24 (DMA part)
    { .compatible = "xlnx,dio24-1.0"      , .data = &dio24_info   },    // dio24 (FPGA part)
    { .compatible = "xlnx,axi-xadc-1.00.a", .data = &xadc_info    },    // XADC (A/D conversion for temperature)
    { .compatible = "xlnx,clocking-wizard", .data = &clk_wiz_info },    // clocking wizard
//    { .compatible = "xlnx,axi-dma-1.00.a", },                         // axi_dma_0
//    { .compatible = "xlnx,axi-dma-mm2s-channel", },                   // dma channel MM2S
//    { .compatible = "xlnx,axi-dma-s2mm-channel", },                   // dma channel S2MM
    { },                                                                // last entry must be NULL
};
MODULE_DEVICE_TABLE(of, dio24_of_match);
#else
# define dio24_of_match
#endif

struct platform_driver dio24_driver = {
    .driver = {
        .name = DIO24_DRIVER_NAME,
        .owner = THIS_MODULE,
        .of_match_table    = dio24_of_match,
    },
    .probe        = dio24_probe,
    .remove        = dio24_remove,
};

#ifdef USE_COMMAND_LINE_ARGS
// test receiving Kernel module command line arguments
// call as: modprobe dio24 myint=0x10 mystr="this is a test"
unsigned myint = 0xdeadbeef;
char *mystr = "default";

module_param(myint, int, S_IRUGO);
module_param(mystr, charp, S_IRUGO);

#endif    // USE_COMMAND_LINE_ARGS
/*
static const char device_status[] = DRIVER_INFO;
static const size_t status_size = sizeof(DRIVER_INFO);
*/

///////////////////////////////////////////////////////////////////////////////////////////////////////////////
// DIO24 device
// this is only used to read status information/and wait for IRQs
///////////////////////////////////////////////////////////////////////////////////////////////////////////////

// open device
int dio24_open(struct inode *inode, struct file *file)
{
    if ((!dma24_reg_base) || (!dio24_reg_base) || (!xadc_reg_base)) return -EIO; // error device
#ifdef DEBUG_INFO
    pr_err(NAME_DIO "device open <%s> (%i)\n", current->comm, current->pid);
#endif
    if (dio24_is_open++ == 0) try_module_get(THIS_MODULE);
    // set server ready bit: this resets all LEDs indicating that board is ready after startup
    // reset device
    //reset_all();
    // get actual control register and set ready bit
    dio_ctrl = READ_DIO_REGISTER(DIO_REG_CTRL);
    dio_ctrl |= DIO_CTRL_READY;
    WRITE_DIO_REGISTER(DIO_REG_CTRL, dio_ctrl);
    return SUCCESS;
}

// release device
int dio24_release(struct inode *inode, struct file *file)
{
#ifdef DEBUG_INFO
    pr_err(NAME_DIO "device release <%s> (%i)\n", current->comm, current->pid);
#endif
    // reset device
    //reset_all();
    // reset server ready bit: not done anymore to indicate board ready after startup
    //dio_ctrl &= (~DIO_CTRL_READY);
    //WRITE_DIO_REGISTER(DIO_REG_CTRL, dio_ctrl);
    if (--dio24_is_open == 0) module_put(THIS_MODULE);
    return SUCCESS;
}

// read from device = wait for FPGA irq
// buffer must be pointer to struct FPGA_status_run and length = sizeof(struct FPGA_status_run)
// waits for next FPGA irq and returns sizeof(struct FPGA_status_run) if ok
// on error or if timeout returns -1 and errno gives information about cause of error
// timeout is fixed to IRQ_FREQ_MIN_TIMEOUT
// note: DIO24_IOCTL_GET_STATUS_RUN gets the same information, but here we wait for FPGA IRQ (instead of polling)
// TODO:
// - this might timeout on error or when board is stopping to run right when called.
// - allow to set timeout?
// - function can be called by any number of users but this was never tested.
// - if not running reads register status and board time directly as IOCTL calls.
ssize_t dio24_read(struct file *file, char __user * buffer, size_t length, loff_t * offset)
{
    ssize_t result = 0;
    unsigned long flags = 0;
    struct FPGA_status_run status_act;

    if((buffer == NULL) || (length != sizeof(struct FPGA_status_run))) result = -EINVAL; // bad arguments
    else {
#if LINUX_VERSION_CODE < KERNEL_VERSION(5,0,0)
        if (!access_ok(VERIFY_WRITE, buffer, length)) result = -EFAULT; // bad address
#else
        if (!access_ok(buffer, length)) result = -EFAULT; // bad address
#endif
        else { 
            //
            //update 12/10/2024: read dio_status outside spinlock.
            // read actual status within spinlock
            spin_lock_irqsave(&FPGA_spin_lock, flags);
            status_act.status        = dio_status;
            status_act.board_time    = dio_time;
            //status_old.board_samples = dio_samples;
            //status_old.board_cycles  = dio_cycles;
            spin_unlock_irqrestore(&FPGA_spin_lock, flags);
            //if ( !(status_old.status & (DIO_STATUS_RUN|DIO_STATUS_WAIT)) ) { 
            //
            if ( !(dio_status & (DIO_STATUS_RUN|DIO_STATUS_WAIT)) ) { 
                // not running: read registers within user mutex 
                //              user mutex protects from other users
                if(mutex_lock_interruptible(&user_mutex)) result = -EINTR; // interrupted system call
                else {
                    status_act.status        = READ_DIO_REGISTER(DIO_REG_STATUS);
                    status_act.board_time    = READ_DIO_REGISTER(DIO_REG_BOARD_TIME);
                    status_act.board_samples = READ_DIO_REGISTER(DIO_REG_BOARD_SAMPLES);
                    status_act.board_cycles  = READ_DIO_REGISTER(DIO_REG_BOARD_CYCLES);
                    mutex_unlock(&user_mutex);
                    //pr_err("dio24_read: not running. last time %u us\n", status_act.board_time);
                    result = 0;
                }
            }
            else {  
                // running: wait for FPGA_irq. returns >=1 if ok, 0 on timeout, -ERESTARTSYS on signal
                // notes: 
                // - here we test of time or status changes 
                // - this does not need spinlock
                // - if the board stops right after we heave read dio_status is running,
                //   then we should still see status change here even if wakeup call is missed. 
                //   maybe setting a nonzero timeout could be still a good idea.
                result = wait_event_interruptible_timeout(dio24_queue, 
                            (dio_time   != status_act.board_time) || 
                            (dio_status != status_act.status    ),
                            (uint32_t)((dma_timeout*HZ)/1000));
                if(result == -ERESTARTSYS) result = -EINTR;    
                else if( (result     == 0                    ) && 
                         (dio_time   == status_act.board_time) && 
                         (dio_status == status_act.status    ) ) {
                    result = -ETIMEDOUT;  // no error and no changes: timeout
                    //pr_err("dio24_read: running timeout! status 0x%x\n", status_act.status);
                }
                else {    
                    // no timeout: copy last FPGA status and time to user
                    //             spinlock ensures consistency of all values.
                    spin_lock_irqsave(&FPGA_spin_lock, flags);
                    status_act.status        = dio_status;
                    status_act.board_time    = dio_time;
                    status_act.board_samples = dio_samples;
                    status_act.board_cycles  = dio_cycles;
                    spin_unlock_irqrestore(&FPGA_spin_lock, flags);
                    result = 0;
                }
            }
            if (result == 0) {
                // copy data to user buffer
                result = __copy_to_user(buffer,&status_act,sizeof(struct FPGA_status_run));
                // check result
                if (result != 0) result = -EIO; // error copying (unexpected)
                else result = sizeof(struct FPGA_status_run); // ok: return number of copied bytes
            }
        }
    }
    return result;
}

///////////////////////////////////////////////////////////////////////////////////////////////////////////////
// DMA24 device
///////////////////////////////////////////////////////////////////////////////////////////////////////////////

// open device
// TODO: allow several users (although not needed)
int dma24_open(struct inode *inode, struct file *file)
{
    if (dma24_is_open) return -EBUSY;        // allow only single client
    if ((!dma24_reg_base) || (!dio24_reg_base) || (!xadc_reg_base)) return -EIO; // error device
#ifdef DEBUG_INFO
    pr_err(NAME_DMA "device open <%s> (%i)\n", current->comm, current->pid);
#endif
    dma24_is_open++;
    try_module_get(THIS_MODULE);
    return SUCCESS;
}

// release device
int dma24_release(struct inode *inode, struct file *file)
{
#ifdef DEBUG_INFO
    pr_err(NAME_DMA "device release <%s> (%i)\n", current->comm, current->pid);
#endif
    dma24_is_open--;
    module_put(THIS_MODULE);
    return SUCCESS;
}

// read RX data from device (at the moment this is TX data looped back through PL)
// TODO: at the moment this is used only for testing purpose since no data is read from hardware. 
//       RX channeld could be disabled completely and maybe one can get more bandwidth for TX channel?
// file = file handle
// buffer = user buffer of at least length bytes. can be NULL when length = 0.
// length = user buffer size in bytes (not samples!). 
//          if 0 returns number of available bytes without copying data. 
//          if > 0 returns max. length bytes if data available. returns < length bytes if less available
//          if no data available and in running state blocks until data available or timeout (returns 0)
//          if no data available and not in running state returns 0
// offset = is ignored
// returns number of bytes copied if length > 0 (but can be < length or 0)
// returns number of bytes available if length = 0 (can be 0 if none available).
// returns < 0 on error. in application you get -1, check errno to get error number (>0)
// notes: 
// - call with length > 0 to wait until data is available while in running state (or after finished and not yet read called).
// - ensure RX is enabled and started, otherwise no data will be available.
ssize_t dma24_read(struct file *file, char __user * buffer, size_t length, loff_t * offset)
{
    ssize_t result = 0;

    // lock other users
    if(mutex_lock_interruptible(&user_mutex)) result = -EINTR; // interrupted system call
    else {
        if(length == 0) {
            // return number of available bytes
            result = dma_RD_bt_act;
        }
        else {    // length > 0
            // check user buffer
            if(buffer == NULL) result = -EFAULT;
#if LINUX_VERSION_CODE < KERNEL_VERSION(5,0,0)
            else if (!access_ok(VERIFY_WRITE, buffer, length)) result = -EFAULT; // bad address
#else
            else if (!access_ok(buffer, length)) result = -EFAULT; // bad address
#endif
            else { // user buffer ok
                result = dma_RD_bt_act; // number of available bytes
                if ( result == 0 ) { // no data available
                    if      ( (dma_ctrl & DMA_CTRL_ACTIVE_ALL) == 0)       result = -ERROR_DMA_INACTIVE;  // -11: DMA is not running
                    else if ( (dio_status & DIO_STATUS_ERROR) != 0)        result = -ERROR_FPGA;          //  -5: FPGA is in error state
                    else if ( ( (dio_status & (DIO_STATUS_RUN|DIO_STATUS_WAIT|DIO_STATUS_END)) == 0) &&   // -16: FPGA is not running and not in end
                              ( (dma_ctrl & DMA_CTRL_ENABLE_FPGA) == 0 ) ) result = -ERROR_FPGA_INACTIVE; //      and will not be started automatically
                    else {
                        // no data available and active transmission: wait until data available
                        //pr_err(NAME_DMA "read: pid %i (%s) bytes %i, wait for data...\n", current->pid, current->comm, length);
                        //pr_err(NAME_DMA "read: wait (%d ms) ...\n", dma_timeout); 
                                    
                        // unlock other user while waiting. this ensures helper is not blocked.
                        mutex_unlock(&user_mutex);
                                    
                        // wait until data available or timeout or FPGA end or FPGA error
                        // helper thread is waking up thread after RX irq handled
                        // wait_event_interruptible_timeout returns >=1 if ok, 0 on timeout, -ERESTARTSYS on signal
                        // wait_event_interruptible returns 0 if ok, -ERESTARTSYS on signal
                        if ( dma_timeout > 0 ) {
                            result = wait_event_interruptible_timeout(dma24_queue, 
                                DIO_WAKEUP(dma_RD_bt_act, dio_status), 
                                (uint32_t)((dma_timeout*HZ)/1000));
                            //pr_err(NAME_DMA "read: wait (%d ms) returned %d, bytes %d, status 0x%x, wakeup %d\n", dma_timeout, result, dma_RD_bt_act, dio_status, (int)DIO_WAKEUP(dma_RD_bt_act, dio_status));
                        }
                        else {
                            result = wait_event_interruptible(dma24_queue, 
                                DIO_WAKEUP(dma_RD_bt_act, dio_status));
                        }
                        if(result == -ERESTARTSYS) result = -EINTR;        
                        else {
                            // lock again other users and read number of available bytes
                            if(mutex_lock_interruptible(&user_mutex)) result = -EINTR;
                            else {
                                result = dma_RD_bt_act;
                                //pr_err(NAME_DMA "read: %i bytes\n", result);
                            }
                        }
                    }
                }
                if( result > 0 ) {
                    // copy available data into buffer
                    // returns number of copied bytes or <0 on error
                    result = copy_RX(buffer, length);
                }
            }
        }
        //pr_err(NAME_DMA "read result %d %x\n", result, dma_RD_bt_act); 

        // allow other users again if 2nd lock did not failed
        if (result != -EINTR) mutex_unlock(&user_mutex);
    }
    return result;
}

// writes user data to device
// allocates and copies data into TX and RX DMA buffers for transfer to PL.
// returns 0 if ok, >0 on warning, <0 on error
// notes: 
// - if length is not multiple of BYTES_PER_SAMPLE writes next lower multiple of bytes.
// - RX buffer size can be increased with DMA_IOCTL_SET_RX_BUFFER (call before write).
ssize_t dma24_write(struct file *file, const char __user * buffer, size_t length, loff_t * offset)
{
    ssize_t result = -EINVAL, RX_buf_size;

    //pr_err(NAME_DMA "pid %i (%s) write %u bytes\n", current->pid, current->comm, length);

    // check user buffer
    if((offset == NULL) || (buffer == NULL)) result = -EINVAL; // bad argument
#if LINUX_VERSION_CODE < KERNEL_VERSION(5,0,0)
    else if (!access_ok(VERIFY_READ, buffer, length)) result = -EFAULT; // bad address
#else
    else if (!access_ok(buffer, length)) result = -EFAULT; // bad address
#endif
    else {
        // lock other user
        if(mutex_lock_interruptible(&user_mutex)) result = -EINTR; // interrupted system call
        else {
            // check maximum number of bytes
            if ((set_samples * DIO_BYTES_PER_SAMPLE + length) > MAX_WRITE_SIZE) result = -ENOMEM;    // all memory used
            else {
                // reduce length to multiple of DIO_BYTES_PER_SAMPLE
                length -= length % DIO_BYTES_PER_SAMPLE;
                if (length == 0) result = -EINVAL;                // too few or 0 bytes given?
                else {
                    // copy data from user into DMA buffers
                    // this increments set_samples
                    result = prepare_TX_buffers(buffer, length);
                    if(result >= 0) {
                        // ensure we have DSC_RX_NUM RX buffers
                        RX_buf_size = prepare_RX_buffers(DMA_BUF_SIZE*DSC_RX_NUM, false);
                        if(RX_buf_size <= 0) result = (RX_buf_size ? RX_buf_size : -EFAULT);
                    }
                }
            }
            // allow other users again
            mutex_unlock(&user_mutex);
        }
    }

    return result;
}

int dma24_mmap(struct file *file_p, struct vm_area_struct *vma)
{
    /*struct dma_proxy_channel *pchannel_p = (struct dma_proxy_channel *)file_p->private_data;

    return dma_mmap_coherent(pchannel_p->dma_device_p, vma,
                       pchannel_p->interface_p, pchannel_p->interface_phys_addr,
                       vma->vm_end - vma->vm_start);
    */
    return -1;
}

// handle IOCTL requests
long dma24_ioctl(struct file *file, unsigned int ioctl_num, unsigned long ioctl_param)
{
    //static uint32_t status_test[HELPER_TASK_NUM_STATUS_IRQ];
    static struct st_par stp;
    //static struct FPGA_status_run st_run;
    static uint32_t st_count = 0;
    uint32_t ldata, ldata2;
    //uint32_t t_start;
    struct set_reg32 sr32;
    //int32_t mT;
    long result = 0;
    unsigned long flags = 0;
    //struct dsc_info *info, *tmp;
    struct FPGA_status *status;
    struct FPGA_status_run *status_run;

    //pr_err(NAME_DMA "ioctl: %s (%i) IOCTL 0x%08X\n", current->comm, current->pid, ioctl_num);

    // TODO: for stopping user thread is always blocked (in user_mutex?), inserting task for helper was working.
    if(ioctl_num == DMA24_IOCTL_STOP) {
        // set test
        //add_helper_task(HELPER_TASK_TEST, status_test, false);
        up(&helper_semaphore);    
        //pr_err(NAME_DMA "ioctl: %s (%i) IOCTL 0x%08X set task ok.\n", current->comm, current->pid, ioctl_num);
        //return 0;    
    }

    // lock other users
    if(mutex_lock_interruptible(&user_mutex)) result = -EINTR;
    else {
        switch (ioctl_num) 
        {
            /////////////////////////////////////////////////////////////////////////////
            // DMA
            /////////////////////////////////////////////////////////////////////////////            

            case DMA24_IOCTL_RESET:
                result = reset_all();
                break;    
            case DMA24_IOCTL_START:
                // start DMA data transmission and FPGA output as soon as data availabel or start trigger
                // this is the main starting point
                // this assumes that FPGA control registers are programmed and DMA is prepared
                //pr_err(NAME_DMA "START\n");
                //t_start = jiffies;
                if ( ( (dma_ctrl   & (DMA_CTRL_ACTIVE_ALL|DMA_CTRL_ENABLE_ALL)) ) || // DMA already running
                     ( (dio_ctrl   & (DIO_CTRL_READY | DIO_CTRL_RUN)) !=  DIO_CTRL_READY ) || // FPGA already running
                     ( (dio_status & (DIO_STATUS_RUN|DIO_STATUS_WAIT         )) ) || // FPGA already running
                     ( mem_TX.first == NULL                                     ) || // no RX buffer allocated
                     ( mem_RX.first == NULL                                     ) || // no TX buffer allocated
                     ( dma_bt_tot == 0                                          ) || // buffer empty
                     ( dma_bt_tot % DIO_BYTES_PER_SAMPLE                        )    // invalid number of bytes
                   ) result = -ERROR_ILLEGAL_STATE;
                else if (copy_from_user(&stp, (struct st_par *)ioctl_param, sizeof(struct st_par)) != 0) 
                    result = -EFAULT;   // bad user address
                else if ((stp.cycles != 1) && (dio_ctrl & DIO_CTRL_RESTART_EN))
                    result = -EINVAL;   // cycles selected but not enabled! TODO: is this needed?
                else {
                    // append NOP samples to last buffer if needed. 
                    // update 10/10/2024: any number of samples is allowed. 
                    // append_TX, DMA_BUF_MULT and NOP not needed anymore.
                    // calculates set_samples and updates dma_bt_tot
                    //result = append_TX();
                    //if (result == 0) {
                    // write # samples and cycles before starting TX
                    // TODO: ensure that DMA is prepared for multiple cycles!?
                    set_samples  = (uint32_t)(dma_bt_tot / DIO_BYTES_PER_SAMPLE);
                    set_cycles   = stp.cycles;
                    dma_reps_act = 0L;
                    WRITE_DIO_REGISTER(DIO_REG_NUM_CYCLES , stp.cycles);
                    WRITE_DIO_REGISTER(DIO_REG_NUM_SAMPLES, set_samples);
                    //pr_err(NAME_DMA "%d samples, %d cycles\n", set_samples, stp.cycles);
                    // write memory barrier ensures that at this point all data is written
                    // and compiler does not rearrange order of events.
                    // additionally, we read back the register to be sure its written
                    wmb();
                    while (READ_DIO_REGISTER(DIO_REG_NUM_SAMPLES) != set_samples);
                    // lock to internal/external clock
                    // TODO: see DIO24_IOCTL_SET_EXT_CLOCK
                    result = set_ext_clk_FPGA((dio_ctrl & DIO_CTRL_EXT_CLK) ? true : false);
                    if (result == 0) {
                        // reset all memories of the status registers
                        spin_lock_irqsave(&FPGA_spin_lock, flags);
                        dio_status  = 0;
                        dio_time    = 0;
                        dio_irq     = 0;
                        dio_samples = 0;
                        dio_cycles  = 0;
                        spin_unlock_irqrestore(&FPGA_spin_lock, flags);
                        // start DMA TX and RX channels
                        result = start_RX();
                        if (result >= 0) {
                            result = start_TX();
                            if(result >= 0) {
                                ++st_count;
                                if ((stp.flags & START_FPGA_MASK_WHEN) == START_FPGA_DELAYED) {
                                    // start FPGA when TX FIFO bytes or all data transferred
                                    dma_ctrl |= DMA_CTRL_ENABLE_FPGA;
                                    // set status to run to indicate that we are running
                                    dio_status = DIO_STATUS_RUN;
                                }                                
                                else { 
                                    // start FPGA now with given flags
                                    // on success this sets DIO_STATUS_RUN bit in dio_status to indicate we are running.
#ifdef PERF_START_IRQ_UP            // with PERF_START_IRQ_UP flag we cannot wait for run bit. TODO: not tested anymore
                                    result = start_FPGA((dio_ctrl & PERF_START_IRQ_UP) ? START_FPGA_NOW : stp.flags);
#else
                                    result = start_FPGA(stp.flags);
#endif
                                }
                            }
                        }
                    }
                }
                if (result < 0) {
                    pr_err(NAME_DMA "START error %ld\n", result);
                    // on error we stop and cleanup all buffers. this might cover debug info but is the savest way.
                    //reset_all();
                }
                //t_start = jiffies - t_start;
                // ATTENTION: DO NO output between start and end irq otherwise irq's for >1MHz output are not handled!
                //pr_err(NAME_DMA "START result %ld (%u/%u, %u ms, res %u ms)\n", result, t_start, HZ, (t_start*1000)/HZ, 1000/HZ );
                break;    
            case DMA24_IOCTL_STOP:
                result = stop_FPGA();
                stop_TX(true);
                stop_RX(true);
                //result = reset_all();
                break;
            case DMA24_IOCTL_SET_TIMEOUT:
                result = get_user(ldata, (uint32_t*) ioctl_param);
                if(!result) {
                    result = put_user(dma_timeout, (uint32_t*) ioctl_param); // return last timeout in ms
                    dma_timeout = ldata;
                }
                break;
            case DMA24_IOCTL_SET_RX_BUFFER:
                result = get_user(ldata, (uint32_t*) ioctl_param);
                if(!result) {
                    result = put_user(dma_RD_bt_max, (uint32_t*) ioctl_param);
                    dma_RD_bt_max = ldata;
                    result = prepare_RX_buffers(ldata, true);
                }
                break;
            case DMA24_IOCTL_GET_LOAD:
                result = (((dma_dsc_RX_c*100)/(DSC_RX_NUM-1))<<16) | ((dma_dsc_TX_c*100)/(DSC_RX_NUM-1));
                break;
            case DMA24_IOCTL_GET_LOAD_TX:
                result = (dma_dsc_TX_c*100)/(DSC_TX_NUM-1);
                break;
            case DMA24_IOCTL_GET_LOAD_RX:
                result = (dma_dsc_RX_c*100)/(DSC_RX_NUM-1);
                break;
            case DMA24_IOCTL_GET_STATUS_TX: 
                // read DMA status TX bits directly
                // TODO: returning values works only when >0! 
                result = dma_status_TX = READ_DMA_REGISTER(DMA_REG_MM2S_STATUS);
                break;
            case DMA24_IOCTL_GET_STATUS_RX: 
                // read DMA status RX bits directly
                // TODO: returning values works only when >0! 
                result = dma_status_RX = READ_DMA_REGISTER(DMA_REG_S2MM_STATUS);
                break;
            case DMA24_IOCTL_GET_CONFIG: 
                // return DMA control bits (these are not the ones in register)
                // TODO: returning values works only when >0! 
                result = dma_ctrl;
                break;    
                
            /////////////////////////////////////////////////////////////////////////////
            // FPGA
            /////////////////////////////////////////////////////////////////////////////            

            case DIO24_IOCTL_GET_REG:  
                // read from register
                // ioctrl_param = struct set_reg32*
                // set_reg32->reg  = address offset: must be integer multiple of REG_BYTES and within DIO_REG_NUM register space
                // set_reg32->data = returns register value
                //pr_err(NAME_DMA "GET_REG\n");
                if (copy_from_user(&sr32, (struct set_reg32*) ioctl_param, sizeof(struct set_reg32)) != 0) { 
                    result = -EFAULT; // bad address
                }
                else {
                    if ( ( sr32.reg > ((DIO_REG_NUM-1)*REG_BYTES) ) || ( sr32.reg & (REG_BYTES-1) ) ) {
                        result = -EINVAL;
                    }
                    else {
                        sr32.data = READ_DIO_REGISTER(sr32.reg);
                        if (copy_to_user((struct set_reg32*) ioctl_param, &sr32, sizeof(struct set_reg32)) != 0) {
                            result = -EFAULT; // bad address                        
                        }
                    }
                }
                break;
            case DIO24_IOCTL_SET_REG:  
                // write to register
                // ioctrl_param = struct set_reg32*
                // set_reg32->reg  = address offset: must be integer multiple of REG_BYTES and within DIO_REG_NUM register space
                // set_reg32->data = value to be written
                // note: this is allowed only when not in running state!
                // ATTENTION: only control register is checked for valid input!
                if (dio_status & (DIO_STATUS_RUN|DIO_STATUS_WAIT)) result = -ERROR_ILLEGAL_STATE;
                else {
                    if (copy_from_user(&sr32, (struct set_reg32*) ioctl_param, sizeof(struct set_reg32)) != 0) 
                        result = -EFAULT; // bad address
                    else {
                        if ( ( sr32.reg > ((DIO_REG_NUM-1)*REG_BYTES) ) || ( sr32.reg & (REG_BYTES-1) ) ) result = -EINVAL;
                        else {                
                            if (sr32.reg == DIO_REG_CTRL) {
                                // control register:
                                // check allowed bits, set ready bit and memorize register content
                                if ((sr32.data & DIO_CTRL_USER) != sr32.data) result = -EINVAL;
                                else {
                                    sr32.data |= DIO_CTRL_READY;
                                    dio_ctrl = sr32.data;
                                    WRITE_DIO_REGISTER(sr32.reg, sr32.data);
                                    result = 0;
                                }
                            }
                            else {
                                WRITE_DIO_REGISTER(sr32.reg, sr32.data);
                                result = 0;
                            }
                        }
                    }
                }
                break;
            case DIO24_IOCTL_GET_STATUS:
                //case DIO24_IOCTL_GET_STATUS_DBG:
                // ioctrl_param == pointer to FPGA_status: display status, otherwise not
                // note: while running this function should not be called to be sure irq can be handled.
                //       call DIO24_IOCTL_GET_STATUS_RUN instead! or dio24_read
                if (dio_status & (DIO_STATUS_RUN|DIO_STATUS_WAIT)) result = -ERROR_ILLEGAL_STATE;
                else {
                    result = get_user(ldata2, (uint32_t*) ioctl_param);
                    if(!result) {
                        // get full status
                        status = kmalloc(sizeof(struct FPGA_status), GFP_KERNEL);
                        if (status == NULL) result = -ENOMEM;
                        else {
                            memset(status, 0, sizeof(struct FPGA_status));
                            // --- FPGA section ---
                            // control register
                            status->ctrl_FPGA               = READ_DIO_REGISTER(DIO_REG_CTRL);
                            status->ctrl_in0                = READ_DIO_REGISTER(DIO_REG_CTRL_IN0);
                            status->ctrl_in1                = READ_DIO_REGISTER(DIO_REG_CTRL_IN1);
                            status->ctrl_out0               = READ_DIO_REGISTER(DIO_REG_CTRL_OUT0);
                            status->ctrl_out1               = READ_DIO_REGISTER(DIO_REG_CTRL_OUT1);
                            status->set_samples             = READ_DIO_REGISTER(DIO_REG_NUM_SAMPLES);
                            status->set_cycles              = READ_DIO_REGISTER(DIO_REG_NUM_CYCLES);
                            status->clk_div                 = READ_DIO_REGISTER(DIO_REG_CLK_DIV);
                            status->strb_delay              = READ_DIO_REGISTER(DIO_REG_STRB_DELAY);
                            status->sync_delay              = READ_DIO_REGISTER(DIO_REG_SYNC_DELAY);
                            status->sync_phase              = READ_DIO_REGISTER(DIO_REG_SYNC_PHASE);
                            status->force_out               = READ_DIO_REGISTER(DIO_REG_FORCE_OUT);
                            // status register
                            status->status_FPGA             = READ_DIO_REGISTER(DIO_REG_STATUS);
                            status->board_time              = READ_DIO_REGISTER(DIO_REG_BOARD_TIME);
                            status->board_samples           = READ_DIO_REGISTER(DIO_REG_BOARD_SAMPLES);
                            status->board_time_ext          = READ_DIO_REGISTER(DIO_REG_BOARD_TIME_EXT);
                            status->board_samples_ext       = READ_DIO_REGISTER(DIO_REG_BOARD_SAMPLES_EXT);
                            status->sync_time               = READ_DIO_REGISTER(DIO_REG_SYNC_TIME);
                            status->version                 = READ_DIO_REGISTER(DIO_REG_VERSION);
                            status->info                    = READ_DIO_REGISTER(DIO_REG_INFO);
                            // XDC module board temperature
                            status->FPGA_temp               = READ_XADC_REGISTER(XADC_TEMP_ACT);
                            if (first_time) { // first temperature read is always wrong. so read 2x
                                first_time = false;
                                status->FPGA_temp           = READ_XADC_REGISTER(XADC_TEMP_ACT);
                            }
                            
                            status->phase_ext               = dio_phase_ext;
                            status->phase_det               = dio_phase_det;
                            status->err_FPGA                = dio_err;
                            status->irq_FPGA                = dio_irq;
                            
                            // --- FPGA section ---
                            status->ctrl_DMA                = dma_ctrl;
                            status->status_TX               = dma_status_TX;
                            status->status_RX               = dma_status_RX;
                            status->dsc_TX_p                = dma_dsc_TX_p;
                            status->dsc_TX_a                = dma_dsc_TX_a;
                            status->dsc_TX_c                = dma_dsc_TX_c;
                            status->dsc_RX_p                = dma_dsc_RX_p;
                            status->dsc_RX_a                = dma_dsc_RX_a;
                            status->dsc_RX_c                = dma_dsc_RX_c;
                            status->err_TX                  = dma_err_TX;
                            status->err_RX                  = dma_err_RX;
                            status->irq_TX                  = dma_irq_TX;
                            status->irq_RX                  = dma_irq_RX;
                            status->TX_bt_tot               = dma_TX_bt_tot;
                            status->RX_bt_tot               = dma_RX_bt_tot;
                            status->bt_tot                  = dma_bt_tot;
                            status->RD_bt_max               = dma_RD_bt_max;
                            status->RD_bt_act               = dma_RD_bt_act;
                            status->RD_bt_drop              = dma_RD_bt_drop;
                            status->reps_act                = dma_reps_act;
                            status->timeout                 = dma_timeout;
                            status->last_sample.data32[0]   = dma_last_sample.data32[0];
                            status->last_sample.data32[1]   = dma_last_sample.data32[1];
                            if (DIO_BYTES_PER_SAMPLE == 12) {
                                status->last_sample.data32[2] = dma_last_sample.data32[2];
                            }

                            // print status
                            if (ldata2 == FPGA_STATUS_SHOW) show_status(status); 
                            
                            // copy status into user buffer
                            if(copy_to_user((struct FPGA_status *)ioctl_param, status, sizeof(struct FPGA_status)) != 0) 
                                result = -EFAULT; // bad address

                            kfree(status);
                            status = NULL;
                        }
                    }
                }
                break;
            case DIO24_IOCTL_GET_STATUS_RUN: 
                // NOTE: while FPGA is running registers are maintained by dio24_irq 
                //       until at end or error and helper thread updates status.
                //       if not running we directly read status register and board time.
                status_run = kmalloc(sizeof(struct FPGA_status_run), GFP_KERNEL);
                if (status_run == NULL) result = -ENOMEM;
                else {
                    //memset(status_run, 0, sizeof(struct FPGA_status_run));
                    if (dio_status & (DIO_STATUS_RUN|DIO_STATUS_WAIT)) {
                        spin_lock_irqsave(&FPGA_spin_lock, flags);
                        status_run->status          = dio_status;
                        status_run->board_time      = dio_time;
                        status_run->board_samples   = dio_samples;
                        status_run->board_cycles    = dio_cycles;
                        spin_unlock_irqrestore(&FPGA_spin_lock, flags);
                    }
                    else {
                        status_run->status          = READ_DIO_REGISTER(DIO_REG_STATUS);
                        status_run->board_time      = READ_DIO_REGISTER(DIO_REG_BOARD_TIME);
                        status_run->board_samples   = READ_DIO_REGISTER(DIO_REG_BOARD_SAMPLES);
                        status_run->board_cycles    = READ_DIO_REGISTER(DIO_REG_BOARD_CYCLES);
                    }
                    if(copy_to_user((struct FPGA_status_run *)ioctl_param, status_run, sizeof(struct FPGA_status_run)) != 0) result = -EFAULT; // bad address
                    kfree(status_run);
                    status_run = NULL;
                }
                break;
            case DIO24_IOCTL_SET_EXT_CLOCK: 
                // set absolute {ext,det} phase: return relative {ext,det} phase
                // update 20/11/2024: do not return relative phase since when this is negative will be treated as error!
                // TODO: keep track of absolute phase in hardware and use DIO24_IOCTL_SET_REG.
                //       this should be easy since need anyway a counter for this. in this case just do not reset counter.
                //       I think this was a fast fix since I did not considered this in first implementation in firmware.
                // TODO: this function should be merged with SERVER_SET_EXT_CLOCK and entirely be done in driver!
                //       see also set_ext_clk_FPGA!
                //       this function should locks to the external clock and then does the phase shift.
                //       uses client_data64 with data0 = nonzero to use external clock and 0 to unlock.
                // external phase
                ldata = ((ioctl_param>>SYNC_PHASE_BITS) & SYNC_PHASE_MASK_1) % PHASE_360;
                ldata = (ldata >= dio_phase_ext) ? ldata-dio_phase_ext : (ldata+PHASE_360)-dio_phase_ext;
                dio_phase_ext = (dio_phase_ext + ldata) % PHASE_360;
                // detector phase
                ioctl_param = (ioctl_param & SYNC_PHASE_MASK_1) % PHASE_360;
                ioctl_param = (ioctl_param >= dio_phase_det) ? ioctl_param-dio_phase_det : (ioctl_param+PHASE_360)-status->phase_det;
                dio_phase_det = (dio_phase_det + ioctl_param) % PHASE_360;
                // set relative phase
                ldata = (ldata << SYNC_PHASE_BITS) | ioctl_param;
                WRITE_DIO_REGISTER(DIO_REG_SYNC_PHASE, ldata);
                //pr_err("SET_SYNC_PHASE 0x%x\n", dio_sync_phase);
                //result = ldata;
                break;
            default:
                result = -EINVAL;
        }

        // unlock other users
        mutex_unlock(&user_mutex);
    }

    //pr_err(NAME_DMA "ioctl: %s (%i) IOCTL 0x%08X err = %d/%d\n", current->comm, current->pid, ioctl_num, err_TX, err_RX);

    // note on return value of IOCTL:
    // when result < 0 user gets -1 as result and errno = |result|
    // i.e. direct returning of positive values is ok but not if value might be negative!

    return result;
}

///////////////////////////////////////////////////////////////////////////////////////////////////////////////
// IRQ handler
///////////////////////////////////////////////////////////////////////////////////////////////////////////////

// IRQ handler for FPGA, TX and RX irq's, lp = pointer to dio24_local structure (not used)
// note: we cannot lock here since might lock out itself
//       therefore, we just acknowledge irq to hardware and wakeup helper_thread
//       helper_thread will within lock: check & update the driver status, cleanup memory 
//       and wakeup eventual waiting clients in read
// TODO:
// - remove inline functions in DMA irqs 
// - do we need the status_irq lists at all? we could save everything in global variables [already done for dio24_irq]
irqreturn_t dio24_irq(int irq, void *lp)
{
    // save registers
    // note: this is executed in irq context, so we do not need the irqsave/irqrestore versions
    spin_lock(&FPGA_spin_lock);
    dio_status  = READ_DIO_REGISTER(DIO_REG_STATUS);
    dio_time    = READ_DIO_REGISTER(DIO_REG_BOARD_TIME);
    dio_samples = READ_DIO_REGISTER(DIO_REG_BOARD_SAMPLES);
    dio_cycles  = READ_DIO_REGISTER(DIO_REG_BOARD_CYCLES);
    ++dio_irq;
    spin_unlock(&FPGA_spin_lock);

    // reset irq enable bit which also resets irq(s)
    WRITE_DIO_REGISTER(DIO_REG_CTRL, dio_ctrl & (~DIO_CTRL_IRQ_EN));

    // enable irq again if there is no error
    // TODO: this could be done automatically by PL. maybe with a separate reset irq bit such that enable bit is not touched above.
    if (!(dio_status & DIO_STATUS_ERROR)) WRITE_DIO_REGISTER(DIO_REG_CTRL, dio_ctrl);

    // on error or end wakeup helper thread
    if (!(dio_status & (DIO_STATUS_RUN|DIO_STATUS_WAIT))) {
        spin_lock(&helper_task_lock); 
        ++irq_FPGA_count;
        spin_unlock(&helper_task_lock);
        up(&helper_semaphore);
    }

    // wakup waiting thread in dio24_read
    // TODO: is this the right function from irq context?
    wake_up_interruptible(&dio24_queue);

    // irq was handled
    return IRQ_HANDLED;
}

irqreturn_t dma24_irq_TX(int irq, void *lp)
{   
    uint32_t status; 
    // get status registers and acknowledge IRQ in hardware
    //irq_ack_TX(status_irq_TX);
	++dma_irq_TX;
	
	// save register content
	status = READ_DMA_REGISTER(DMA_REG_MM2S_STATUS);

	// writing to these registers reset bits
	// TODO: this bit should be always set here?
	if(status & MM2S_STATUS_IRQS) WRITE_DMA_REGISTER(DMA_REG_MM2S_STATUS, status);

    // update status for helper
    spin_lock(&helper_task_lock); 
    ++irq_TX_count;
    irq_TX_status = status;
    spin_unlock(&helper_task_lock);

    // wakeup helper
    up(&helper_semaphore);

    // irq was handled
    return IRQ_HANDLED;
}

irqreturn_t dma24_irq_RX(int irq, void *lp)
{
    uint32_t status;
    // get status registers and acknowledge IRQ in hardware
    //irq_ack_RX(status_irq_RX);
	// count irq's, this is global, other threads only read this
	++dma_irq_RX;

	// save register content
	status = READ_DMA_REGISTER(DMA_REG_S2MM_STATUS);

	// writing to these registers reset bits
	// TODO: this bit should be always set here?
	if(status & S2MM_STATUS_IRQS) WRITE_DMA_REGISTER(DMA_REG_S2MM_STATUS, status);

    // update status for helper
    spin_lock(&helper_task_lock); 
    ++irq_RX_count;
    irq_RX_status = status;
    spin_unlock(&helper_task_lock);
    
    // wakeup helper
    up(&helper_semaphore);

    // irq was handled
    return IRQ_HANDLED;
}

///////////////////////////////////////////////////////////////////////////////////////////////////////////////
// helper thread
// handles long-lasting DMA tasks outside of irq context.
// FPGA irq's are handled directly, only the last is sent to helper.
///////////////////////////////////////////////////////////////////////////////////////////////////////////////

// helper thread
unsigned char helper_running = 1;
int helper_thread(void *data) {
    int err = 0;
    //struct helper_task task;
    unsigned long flags = 0L;
    unsigned char task = HELPER_TASK_NONE;
    unsigned count_none = 0;
    
    pr_err(NAMEH "pid %i (%s) waiting for IRQ ...\n", current->pid, current->comm);
    while (helper_running && (!err)) {
        
        // wait for next IRQ
        if(down_interruptible(&helper_semaphore)) {
            pr_err(NAMEH "pid %i (%s) signal received!\n", current->pid, current->comm);
            break;
        }
        
        // copy status from irq context to global context
        // TX has priority over RX which has priority over FPGA
        // note: we reset dma_status_TX/RX here in order to keep the last status for show_status.
        //       one of them might be 0 depending on which was last.
        spin_lock_irqsave(&helper_task_lock, flags);
        if (irq_TX_count > 0) {
            task = HELPER_TASK_IRQ_TX;
            irq_TX_merged += irq_TX_count - 1;
            irq_TX_count = 0;
            dma_status_TX = irq_TX_status;
        }
        else if (irq_RX_count > 0) {
            task = HELPER_TASK_IRQ_RX;
            irq_RX_merged += irq_RX_count - 1;
            irq_RX_count = 0;
            dma_status_RX = irq_RX_status;
        }
        else if (irq_FPGA_count > 0) {
            task = HELPER_TASK_IRQ_FPGA;
            irq_FPGA_merged += irq_FPGA_count - 1;
            irq_FPGA_count = 0;
            // we do not transmit status to worker.
        }
        else {
            // TODO: can this happen?
            task = HELPER_TASK_NONE;
        }
        spin_unlock_irqrestore(&helper_task_lock, flags);
        
        // handle task
        switch(task) {
            case HELPER_TASK_NONE:                // no task?
                //pr_err(NAMEH "pid %i (%s) NONE recieved?\n", current->pid, current->comm);
                ++count_none;
                break;
            case HELPER_TASK_IRQ_TX: 
                // process IRQ result
                //pr_err(NAMEH "pid %i (%s) handle IRQ\n", current->pid, current->comm);

                // lock out other users, this ensures consistency of DMA but might block!
                if(mutex_lock_interruptible(&user_mutex)) {
                    pr_err(NAMEH "pid %i (%s) signal received!\n", current->pid, current->comm);
                    err = -EINTR;
                    break;
                }

                // irq_handler
                irq_hdl_TX();
                
                // allow other users again
                mutex_unlock(&user_mutex);
                break;
            case HELPER_TASK_IRQ_RX: 
                // process IRQ result
                //pr_err(NAMEH "pid %i (%s) handle IRQ\n", current->pid, current->comm);

                // lock out other users, this ensures consistency of DMA but might block!
                if(mutex_lock_interruptible(&user_mutex)) {
                    pr_err(NAMEH "pid %i (%s) signal received!\n", current->pid, current->comm);
                    err = -EINTR;
                    break;
                }

                // irq_handler
                irq_hdl_RX();
                
                // allow other users again
                mutex_unlock(&user_mutex);

                //pr_err(NAMEH "wakeup 'read', IRQs=%u/%u, error=%d/%d status=%x\n", dma_irq_TX, dma_irq_RX, dma_err_TX, dma_err_RX, dma_ctrl);

                // wakeup reading process(es)
                wake_up_interruptible(&dma24_queue);
                break;
            case HELPER_TASK_IRQ_FPGA: 
                // FPGA is stopped at end or error
                // this is not critical anymore, we just use it to print end irq with state.
                // lock out other users, this ensures consistency of DMA but might block!
                if(mutex_lock_interruptible(&user_mutex)) {
                    pr_err(NAMEH "pid %i (%s) signal received!\n", current->pid, current->comm);
                    err = -EINTR;
                    break;
                }
                pr_err("\n" NAMEH "FPGA irq 0x%x %u us # %u (%x)\n\n", dio_status, dio_time, dio_samples, dio_ctrl);
                pr_err(NAMEH "count_none = %d\n", count_none);
                mutex_unlock(&user_mutex);
                break;
            case HELPER_TASK_EXIT:
                 pr_err(NAMEH "pid %i (%s) exit request received\n", current->pid, current->comm);
                err = 99;
                break;
            case HELPER_TASK_TEST:
                 pr_err(NAMEH "pid %i (%s) test!\n", current->pid, current->comm);
                /* lock out other users, this ensures consistency of DMA but might block!
                if(mutex_lock_interruptible(&user_mutex)) {
                    pr_err(NAMEH "pid %i (%s) signal received!\n", current->pid, current->comm);
                    err = -EINTR;
                    break;
                }
                else {
                    //dma_ctrl |= DMA_CTRL_STOP_ALL_AT_END;
                    //st_stop = true;
                    mutex_unlock(&user_mutex);
                }*/
                //err = buffer_test();
                break;                    
            default:
                // unknown task?
                err = 3;
        }
        // introduce some small delay for testing
        //udelay(1);
        //sched_yield();
    }
    if(err == 99) {
        err = 0;
        // free ringbuffer of helper tasks
        //delete_helper_tasks();
    }
    pr_err(NAMEH "pid %i (%s) ended (error %d)\n", current->pid, current->comm, err);
    pr_err(NAMEH "count_none = %d\n", count_none);
    return err;
}
///////////////////////////////////////////////////////////////////////////////////////////////////////////////
// driver/module functions
///////////////////////////////////////////////////////////////////////////////////////////////////////////////

// called after device initialization
inline void device_init(int type) {
    //uint32_t test;
    /*if(type == TYPE_DMA24) {
        // reset status and get actual registers
        update_status(NULL, false, true);
        //dma_timeout = 0; // timeout in ms. 0 = no timeout
        dma_reps_set = 1;
        // update FPGA status if dio24 was probed before
        dio_status = status_run;
    }
    else if (type == TYPE_DIO24) {
        // read DIO control registers
        status_run.status = READ_DIO_REGISTER(DIO_REG_STATUS);
        status_run.board_time = READ_DIO_REGISTER(DIO_REG_BOARD_TIME);
        status_run.board_samples = READ_DIO_REGISTER(DIO_REG_BOARD_SAMPLES);
        // save into status if dma24 was probed before
        dio_status = status_run;
    }*/
    //else if (type == TYPE_CLK_W) {
    //}
    // after all devices are initialized we can read FPGA status and actual temperature
    if ((dma24_reg_base != NULL) && (dio24_reg_base != NULL) && (xadc_reg_base != NULL)) {
        // reset status and get actual registers
        //pr_err(NAME_DRV "reading reg ...\n");
        dio_ctrl    = READ_DIO_REGISTER(DIO_REG_CTRL);
        dio_status  = READ_DIO_REGISTER(DIO_REG_STATUS);
        dio_samples = READ_DIO_REGISTER(DIO_REG_BOARD_SAMPLES);
        dio_cycles  = READ_DIO_REGISTER(DIO_REG_BOARD_CYCLES);

        //test = READ_DIO_REGISTER(DIO_REG_CTRL);
        //pr_err(NAME_DRV "update status ...\n");
        //update_status(NULL, false, true);
        //pr_err(NAME_DRV "update status ok\n");
        //dma_timeout = 0; // timeout in ms. 0 = no timeout
        //set_cycles = 1;
        //dma_reps_set = 1;
    }
}

// called before device removal
inline void device_remove(int type) {
    if(type == TYPE_DMA24) {
        // disable FPGA irq
        //if(!is_dma24) irq_disable(); else
        // stop and reset
        reset_all();
    }
}

// device probe = device start
int dio24_probe(struct platform_device *pdev)
{
    int rc = -1, i, index = -1;
    struct resource *r_irq; /* Interrupt resources */
    struct resource *r_mem; /* IO mem resources */
    struct device *dev = &pdev->dev;
    struct device_node *node = pdev->dev.of_node;
    struct dio24_local *lp = NULL;
    const struct of_device_id *match = of_match_device(dio24_of_match, dev);
    struct clk_wiz_data *cwd = NULL;

    if(!match) return -ENODEV; // not our device

#ifdef DEBUG_INFO
    // probing dma or dio device?
    pr_err(NAME_DRV "pid %i (%s) device probing ... (matched)\n", current->pid, current->comm);
#endif

    // allocate private memory
    lp = kmalloc(sizeof(struct dio24_local), GFP_KERNEL);
    if (!lp) {
        dev_err(dev, "private memory allocation failed!\n");
        return -ENOMEM;
    }
    dev_set_drvdata(dev, lp);
    lp->data = (struct device_info *) match->data;

    if (lp->data->type == TYPE_CLK_W) {
        // get index of wizard
        rc = of_property_read_u32(node, "index", &index);
        if (rc < 0) {
            dev_err(dev, "error %d get index!\n", rc);
            goto error1;
        }
        else if ((index <0) || (index >= CLK_WIZ_NUM)) {
            dev_err(dev, "index %d outside range 0..%d!\n", index, CLK_WIZ_NUM-1);
            goto error1;
        }
        //lp->data->p_base_addr = &clk_wiz_reg_base[clk_wiz_num++];

        // get number of channels
        rc = of_property_count_strings(node, "clock-output-names");
        if (rc <= 0) {
            dev_err(dev, "error or no channels found (%d)!\n", rc);
            goto error1;
        }
        // allocate channel info and array of channels
        cwd = kmalloc(sizeof(struct clk_wiz_data), GFP_KERNEL);
        if (!cwd) {
            dev_err(dev, "channel info allocation failed!\n");
            goto error1;
        }
        clk_wiz_pdata[index] = cwd;             // save global pointer
        lp->data->pdata = cwd;                  // save pointer also in device data
        lp->data->p_base_addr = &cwd->base_addr;// location where to save base address later
        cwd->index = index;                     // index in ck_wiz_pdata
        cwd->VCO_ps = 0;                        // 0 = read from registers
        cwd->num = rc;                          // number of channels
        cwd->channel = kmalloc(rc*sizeof(struct clk_wiz_channel), GFP_KERNEL);
        if (!cwd->channel) {
            dev_err(dev, "channel array allocation failed!\n");
            goto error1;
        }

        // enumerate channels
        for (i = 0; i < cwd->num; ++i) {
            // get channel name TODO: is copying needed?
            rc = of_property_read_string_index(node, "clock-output-names", i, (const char**) &cwd->channel[i].name);
            if (rc < 0) {
                dev_err(dev, "read channel string error %d!\n", rc);
                goto error1;
            }
            else {
                dev_err(dev, "channel %d '%s'\n", i, cwd->channel[i].name);
            }
        }

        // get PLL type and input period in ns (default values on error)
        // these values must be inserted manually into system-user.dtsi according to the design.
        cwd->PLL_type = CLK_WIZ_NONE;
        cwd->in_ps = 0;
        of_property_read_u32(node, "PLL_type", &cwd->PLL_type);
        of_property_read_u32(node, "period_in_ps", &cwd->in_ps);
        //of_property_read_u32(node, "period_VCO_ps", &cwd->VCO_ps);
        dev_err(dev, "PLL_type %d, in %u ps (ok)\n", cwd->PLL_type, cwd->in_ps);
    }

    if(*lp->data->p_base_addr != NULL) {
        dev_err(dev, "device %s already probed!\n", lp->data->name);
        rc = -EBUSY;
        goto error1;
    }

    //dev_info(dev, "probing %s device ...\n", lp->data->name);
    //pr_err(NAME_DRV "probing %s device...\n", lp->data->name);

#ifdef USE_DMA_API
    if(lp->data->type == TYPE_DMA24) {
        // for reserving memory see https://xilinx-wiki.atlassian.net/wiki/spaces/A/pages/18841683/Linux+Reserved+Memory
        /* Initialize reserved memory resources */
        /*rc = of_reserved_mem_device_init(dev);
        if(rc) {
            dev_err(dev, "Could not get reserved memory\n");
            goto error1;
        }*/
        /* Allocate memory */
        //dma_set_coherent_mask(dev, 0xFFFFFFFF);
        //lp->vaddr = dma_alloc_coherent(dev, ALLOC_SIZE, &lp->paddr, GFP_KERNEL);
        //dev_info(dev, "Allocated coherent memory, vaddr: 0x%0llX, paddr: 0x%0llX\n", (u64)lp->vaddr, lp->paddr);

        // about DMA api see https://www.kernel.org/doc/Documentation/DMA-API-HOWTO.txt
        // dma_set_mask_and_coherent() is the same as calling dma_set_mask() and dma_set_coherent_mask()
        // set 32bit address mask and coherent caching for device (returns 0 if ok)
        if(dma_set_mask_and_coherent(dev, DMA_BIT_MASK(32))) {
            dev_err(dev, "setup of DMA address mask and coherent caching failed!\n");
            rc = -EBUSY;
            goto error1;
        }
    }
#endif
    // get register memory region from device tree
    r_mem = platform_get_resource(pdev, IORESOURCE_MEM, 0);
    if (!r_mem) {
        dev_err(dev, "invalid memory region!\n");
        rc = -ENODEV;
        goto error1;
    }
    
    lp->mem_start = r_mem->start;
    lp->mem_end = r_mem->end;
    // lock register memory region
    if (!request_mem_region(lp->mem_start,
                lp->mem_end - lp->mem_start + 1,
                DIO24_DRIVER_NAME)) {
        dev_err(dev, "locking of memory region at %p failed!\n",(void *)lp->mem_start);
        rc = -EBUSY;
        goto error1;
    }

    // map device registers (force no caching)
    *lp->data->p_base_addr = ioremap_nocache(lp->mem_start, lp->mem_end - lp->mem_start + 1);
    if(*lp->data->p_base_addr == NULL) {
        dev_err(dev, "mapping of memory region failed\n");
        rc = -EIO;
        goto error2;
    }

#ifdef DEBUG_INFO
    pr_err(NAME_DRV "get %d irqs %s device...\n", lp->data->num_irq, lp->data->name);
#endif
    // get TX and RX irq's
    for(i = 0; i < lp->data->num_irq; ++i) { 
        // get irq
        r_irq = platform_get_resource(pdev, IORESOURCE_IRQ, i);
        if (!r_irq) {
            lp->data->num_irq = i; // call free_irq on already allocated irq's
            dev_err(dev, "IRQ %i not found!\n", i);
            goto error4;
        }
        lp->irq[i] = r_irq->start;
        
        switch(lp->data->type) {
            case TYPE_DIO24:
                rc = request_irq(lp->irq[i], &dio24_irq, 0, DIO24_DRIVER_NAME, lp);
                break;
            case TYPE_DMA24:
                // TODO: actually we do not know which irq is TX and which is RX channel!?
                rc = request_irq(lp->irq[i], (i==0) ? &dma24_irq_TX : &dma24_irq_RX, 0, DIO24_DRIVER_NAME, lp);
                break;
            default:
                // unknown device?
                dev_err(dev, "unknown device %d requests %d irqs?\n", lp->data->type, lp->data->num_irq);
                goto error4;
        }
        if (rc) {
            lp->data->num_irq = i; // call free_irq on already allocated irq's
            dev_err(dev, "allocation of IRQ %d failed!\n", lp->irq[i]);
            goto error4;
        }
    }
    //pr_err(NAME_DRV "ok %s device...\n", lp->data->name);
    // all succeeded
    if(lp->data->type == TYPE_DMA24) {
        // save device for dma api calls
        dio24_dev = dev;
        dev_info(dev,"@ 0x%08X mapped 0x%08X, irq=%d/%d\n", //lp->data->name,
            (unsigned int __force)lp->mem_start, (unsigned int __force)*lp->data->p_base_addr,
            lp->irq[0], lp->irq[1]);
    }
    else if (lp->data->type == TYPE_DIO24){
        // application level init device
        dev_info(dev,"@ 0x%08X mapped 0x%08X, irq=%d\n", //lp->data->name,
            (unsigned int __force)lp->mem_start, (unsigned int __force)*lp->data->p_base_addr,
            lp->irq[0]);
        //pr_err(NAME_DRV "pid %i (%s) device probed ok!\n", current->pid, current->comm);
    }
    else if (lp->data->type == TYPE_XADC) { // xadc device
        dev_info(dev,"@ 0x%08X mapped 0x%08X, irq=<none>\n", //lp->data->name,
            (unsigned int __force)lp->mem_start, (unsigned int __force)*lp->data->p_base_addr);
    }
    else {
        pr_err(NAME_DRV "pid %i (%s) unknown device probing!?\n", current->pid, current->comm);
        goto error4;
    }

    device_init(lp->data->type);

#ifdef DEBUG_INFO
    pr_err(NAME_DRV "ok %s device probing\n", lp->data->name);
#endif

    return 0;
error4:
    pr_err(NAME_DRV "device probing (error 4)\n");
    // free allocated IRQ's
    for(i = 0; i < lp->data->num_irq; ++i) {
        free_irq(lp->irq[i], lp);
    }
    // unmap physical device addresses
    iounmap(*lp->data->p_base_addr);
    *lp->data->p_base_addr = NULL;

error2:
    pr_err(NAME_DRV "device probing (error 2)\n");
    // release memory region
    release_mem_region(lp->mem_start, lp->mem_end - lp->mem_start + 1);
error1:    
    pr_err(NAME_DRV "device probing (error 1)\n");
    if (lp->data->type == TYPE_CLK_W) { // free clock wizard channels
        cwd = (struct clk_wiz_data*)lp->data->pdata;
        if (cwd) {
            clk_wiz_pdata[cwd->index] = NULL; // reset global pointer
            if (cwd->channel) {
                kfree(cwd->channel);
                cwd->channel = NULL;
            }
            cwd->num = 0;
            kfree(cwd);
            lp->data->pdata = NULL;
        }
    }
    // free private memory
    dev_set_drvdata(dev, NULL);
    kfree(lp);

    return rc;
}

// device remove
int dio24_remove(struct platform_device *pdev)
{
    int i;
    struct device *dev = &pdev->dev;
    struct dio24_local *lp = dev_get_drvdata(dev);
    struct clk_wiz_data *cwd;

    if(lp) {
        if(lp->data) {
            // application level device removal
            device_remove(lp->data->type);

            // free clock wizard channels
            if (lp->data->type == TYPE_CLK_W) {
                cwd = (struct clk_wiz_data*)lp->data->pdata;
                if (cwd) {
                    /* find and reset global pointer and counter
                    for (i = 0; i < clk_wiz_num; ++i) {
                        if(clk_wiz_pdata[i] == cwd) {
                            clk_wiz_pdata[i] = NULL;
                            --clk_wiz_num;
                            break;
                        }
                    }*/
                    clk_wiz_pdata[cwd->index] = NULL;
                    if (cwd->channel) {
                        kfree(cwd->channel);
                        cwd->channel = NULL;
                    }
                    cwd->num = 0;
                    kfree(cwd);
                    lp->data->pdata = NULL;
                }
            }

            // free irq's
            for(i = 0; i < lp->data->num_irq; ++i) {
                free_irq(lp->irq[i], lp);
            }

            // unmap physical device addresses
            iounmap(*lp->data->p_base_addr);
            *lp->data->p_base_addr = NULL;
        }

        // unlock device memory
        release_mem_region(lp->mem_start, lp->mem_end - lp->mem_start + 1);

        // free private device memory
        kfree(lp);
        dev_set_drvdata(dev, NULL);
    }
    return 0;
}

// module entry
int __init dio24_init(void) {
        int result = 0;
    pr_err(NAME_DRV "%s\n", DRIVER_INFO);
#ifdef USE_COMMAND_LINE_ARGS
    pr_err(NAME_DRV "parameters were (0x%08x) and \"%s\"\n", myint,mystr);
#endif // USE_COMMAND_LINE_ARGS

    // register character device, returns major device number, <0 on error
    // note: character devices are unbuffered, block devices are buffered
    result = register_chrdev(0,                // major device number (0..255, 0=auto)
                DIO24_DEVICE_NAME,        // device name
                &dio24_fops            // ptr to file operations structure
                );
    if (result < 0) {
        pr_err(NAME_DRV "registering %s char device failed!\n", DIO24_DEVICE_NAME);
    }
    else {
        // save major device number
        dio24_major_num = result;
#ifdef DEBUG_INFO
        pr_err(NAME_DRV "registering %s char device (%d) ok\n", DIO24_DEVICE_NAME, dio24_major_num);
#endif
        // register dma24 char device
        result = register_chrdev(0,                // major device number (0..255, 0=auto)
                    DMA24_DEVICE_NAME,        // device name
                    &dma24_fops            // ptr to file operations structure
                    );
        if (result < 0) {
            pr_err(NAME_DRV "registering %s char device failed!\n", DMA24_DEVICE_NAME);
            unregister_chrdev(dio24_major_num, DIO24_DEVICE_NAME);
        }
        else {
            // save major device number
            dma24_major_num = result;
#ifdef DEBUG_INFO
            pr_err(NAME_DRV "registering %s char device (%d) ok\n", DMA24_DEVICE_NAME, dma24_major_num);
#endif            
            // note: we do not open XADC, so we do not need to register it as a device.
            //       if one wants to read voltages continuously would be useful however.

            // register device driver, returns 0 if ok
            result =  platform_driver_register(&dio24_driver);
            
            //pr_err(NAME_DRV "registers mapped to 0x%x  \n", (unsigned int)dma24_reg_base);
            //pr_err(NAME_DRV "registration success, major device number = %d.\n", major_num);
            //pr_err(NAME_DRV "If you want to talk to the device driver,\n");
            //pr_err(NAME_DRV "create a device file by following command:\n");
            //pr_err(NAME_DRV "mknod %s c %d 0\n", DIO_DEVICE_NAME, major_num);
            //pr_err(NAME_DRV "registering driver result %d\n", rc);
            if(result == 0) {
#ifdef DEBUG_INFO
                pr_err(NAME_DRV "registering driver %s ok\n", DIO24_DRIVER_NAME);
#endif            
                // create user mutex
                mutex_init(&user_mutex);
                // create binary semaphore for helper
                sema_init(&helper_semaphore, 0);
                // init spin locks
                spin_lock_init(&helper_task_lock);
                spin_lock_init(&FPGA_spin_lock);
                // create ringbuffer of helper tasks
                //result = create_helper_tasks();
                //if(result) pr_err(NAME_DRV "allocation of helper task ringbuffer failed!\n");
                //else {
                    // create and start helper thread
                    helper = kthread_run(helper_thread, NULL, "dio24helper");
                    if(helper == ERR_PTR(-ENOMEM)) {
                        pr_err(NAME_DRV "could not create helper thread!\n");
                        result = -ENOMEM;
                    }
                    else {
                        pr_err(NAME_DRV "char-device %s (%d) registered ok\n", DIO24_DEVICE_NAME, dio24_major_num);
                        pr_err(NAME_DRV "char-device %s (%d) registered ok\n", DMA24_DEVICE_NAME, dma24_major_num);
                    }
                //}
            }
            else {
                pr_err(NAME_DRV "registering driver %s error %d\n", DIO24_DRIVER_NAME, result);
                unregister_chrdev(dio24_major_num, DIO24_DEVICE_NAME);
                unregister_chrdev(dma24_major_num, DMA24_DEVICE_NAME);
            }
        }
    }
    return result;
}

// module exit
void __exit dio24_exit(void)
{
    //uint32_t status[HELPER_TASK_NUM_STATUS];
    // tell helper to stop
    if(helper) {
        //add_helper_task(HELPER_TASK_EXIT, status, false);
        helper_running = 0;
        up(&helper_semaphore);
        //kthread_stop(helper);
        helper = NULL;
    }
    // un-init spin locks not needed?
    // unregister driver
    platform_driver_unregister(&dio24_driver);
    // unregister char devices
        unregister_chrdev(dio24_major_num, DIO24_DEVICE_NAME);
        unregister_chrdev(dma24_major_num, DMA24_DEVICE_NAME);
    pr_err(NAME_DRV "exit\n");
}

// define module entry and exit
module_init(dio24_init);
module_exit(dio24_exit);
