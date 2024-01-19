////////////////////////////////////////////////////////////////////////////////////////////////////
// driver.c
// dio24 Linux kernel module for Arty-Z7-20 FPGA
// created September 2018 by Andi
// compiled with g++ on Ubuntu 18.04 LTS
// tested with Petalinux 2017.4
// modified by Andi from Xilinx tutorial UG1165 blink.h/blink.c
////////////////////////////////////////////////////////////////////////////////////////////////////

#include <linux/kernel.h>			// printk, pr_err, etc.
#include <linux/init.h>				// module_init, module_exit
#include <linux/module.h>			// kernel version, THIS_MODULE

#include <linux/fs.h>

#include <linux/slab.h>				// kmalloc, kfree
#include <linux/io.h>
#include <linux/interrupt.h>

#include <linux/of_address.h>
#include <linux/of_device.h>
#include <linux/of_platform.h>
#include <linux/of_reserved_mem.h>

//#include <asm/uaccess.h> 			// get_user, put_user, copy_to_user (deprecated?)
#include <linux/uaccess.h> 			// copy_to_user
#include <asm/io.h>				// ioremap, iounmap
#include <asm/page.h>				// PAGE_SIZE

#include <linux/wait.h>				// wait functions
#include <linux/spinlock.h>			// spinlock used for main thread
#include <linux/mutex.h>			// mutex for user lock
#include <linux/semaphore.h>			// semaphore used for helper thread
#include <linux/kthread.h>			// kernel thread functions
#include <linux/sched.h>			// scheduler for changing scheduling scheme
#include <linux/delay.h>			// udelay, mdelay

#include "dma.h"				// DMA definitions & function declarations

#ifdef USE_DMA_API
#include <linux/dma-mapping.h>			// dma_alloc_coherent, dma_map_sg, etc.
#endif

///////////////////////////////////////////////////////////////////////////////////////////////////////////////
// module macros
///////////////////////////////////////////////////////////////////////////////////////////////////////////////

#define DEBUG					// if defined print debug info (todo: use!)

// driver info strings
#define DRIVER_INFO		"Linux kernel module for Cora-Z7-10 FPGA by Andi"
#define DRIVER_AUTHOR		"Andi"
#define DRIVER_LICENCE		"GPL"

// name used in all pr_err statements
#define NAME_DRV		"DIOdrv "	// IOCTL, read, write functions
#define NAME_DIO		"DIOio  "	// IOCTL, read, write functions
#define NAME_DMA		"DIOdma "	// IOCTL, read, write functions
#define NAMEH			"DIOhlp "	// helper thread

//#define USE_COMMAND_LINE_ARGS			// if defined use command line arguments (for testing)

#define SUCCESS 		0
#define FAILED			-1

// maximum number of IRQs
#define NUM_IRQ_MAX		2		// we need TX and RX irq's

// maximum buffer size for ioctl data
#define MAX_BUF			100

// helper tasks (bitwise allows multiple tasks)
#define HELPER_TASKS_NUM	20		// pre-allocated number of helper tasks
#define HELPER_TASK_NONE	0		// indicates end of helper tasks. dont use!
#define HELPER_TASK_IRQ_DMA	1		// handle DMA IRQ
#define HELPER_TASK_IRQ_FPGA	4		// handle FPGA IRQ
#define HELPER_TASK_TEST	8		// testing function for debugging
#define HELPER_TASK_EXIT	16		// exit thread

// increment void *
#define INC(pvoid)	(pvoid = (void*)(((char*)pvoid) + 1))

///////////////////////////////////////////////////////////////////////////////////////////////////////////////
// structure and function declarations
///////////////////////////////////////////////////////////////////////////////////////////////////////////////

// device specific data
#define TYPE_DIO24	0
#define	TYPE_DMA24	1
#define TYPE_XADC	2
struct device_info {
	int type;	// dio24/dma24/XADC
	char name[6];	// displayed device name
	int num_irq;	// number of used irq's
	void __iomem **p_base_addr; // location where to save base address
};

// local module parameters
struct dio24_local {
	int id;			// device id 0=dma, 1=dio
	int irq[NUM_IRQ_MAX];
	uint32_t mem_start; // physical memory start address
	uint32_t mem_end; // physical memory end address
	//void __iomem *base_addr; // saved in global memory
	struct device_info *data; // device specific data
};

// DIO file operation functions
int dio24_open(struct inode *inode, struct file *file);
int dio24_release(struct inode *inode, struct file *file);
ssize_t dio24_read(struct file *file, char __user * buffer, size_t length, loff_t * offset);

// DMA file operation functions
int dma24_open(struct inode *inode, struct file *file);
int dma24_release(struct inode *inode, struct file *file);
ssize_t dma24_read(struct file *file, char __user * buffer, size_t length, loff_t * offset);
ssize_t dma24_write(struct file *file, const char __user * buffer, size_t length, loff_t * offset);
long dma24_ioctl(struct file *file, unsigned int ioctl_num, unsigned long ioctl_param);
int dma24_mmap(struct file *file_p, struct vm_area_struct *vma);

// device driver functions
int dio24_probe(struct platform_device *pdev);
int dio24_remove(struct platform_device *pdev);

// helper thread functions
int create_helper_tasks(void);
void add_helper_task(int task, uint32_t status[HELPER_TASK_NUM_STATUS_IRQ], bool is_irq);
int helper_thread(void *data);

///////////////////////////////////////////////////////////////////////////////////////////////////////////////
// globals
///////////////////////////////////////////////////////////////////////////////////////////////////////////////

MODULE_DESCRIPTION(DRIVER_INFO);
MODULE_AUTHOR(DRIVER_AUTHOR);
MODULE_LICENSE(DRIVER_LICENCE);

struct mutex user_mutex;			// user (and helper) mutex ensures consistency of DMA structures (shared with dma.c)
DECLARE_WAIT_QUEUE_HEAD(dio24_queue);		// wait queue to wakeup waiting user in dio24_read()
DECLARE_WAIT_QUEUE_HEAD(dma24_queue);		// wait queue to wakeup waiting user in dma24_read()

// helper thread
struct task_struct *helper = NULL;		// helper thread
DEFINE_SPINLOCK(helper_task_lock);		// protects helper_task
struct semaphore helper_semaphore;		// blocks helper thread until IRQ or stop request
struct helper_task *helper_task_first = NULL; 	// first used entry of helper tasks ringbuffer
struct helper_task *helper_task_last = NULL;  	// last used entry of helper tasks ringbuffer
uint32_t helper_tasks = 0;			// counts actual number of used helper tasks in ringbuffer
uint32_t helper_tasks_max = 0;			// maximum number of used helper tasks in ringbuffer

int dio24_major_num = 0;			// major device number
int dma24_major_num = 0;			// major device number
int dio24_is_open = 0;				// 1 if already open
int dma24_is_open = 0;				// 1 if already open

//uint32_t irq_count_TX = 0L;			// local irq counter TX
//uint32_t irq_count_RX = 0L;			// local irq counter RX

// shared with dma.c and protected by user_mutex. content of struct FPGA_status.
struct FPGA_status status;

// read by dio24_read and updated by helper on last dio24_irq. protected by FPGA_read_lock
struct FPGA_status_run FPGA_read_data;  // status registers
uint32_t irq_FPGA = 0;                  // irq_FPGA counter
DEFINE_SPINLOCK(FPGA_read_lock);		// protects FPGA_read_data

// timeout for dio24_read in ms
uint32_t dio24_timeout = 3000;

// dma24 device
void __iomem *dma24_reg_base = NULL;			// mapped base address of registers
struct device *dio24_dev = NULL;			// device structure used for DMA API calls
const struct device_info dma24_info = {			// device data used for probing/remove
	.type = TYPE_DMA24,
	.name = "dma24",
	.num_irq = 2,
	.p_base_addr = &dma24_reg_base,
};

// dio24 device
void __iomem *dio24_reg_base = NULL;			// mapped base address of registers
const struct device_info dio24_info = {			// device data used for probing/remove
	.type = TYPE_DIO24,
	.name = "dio24",
	.num_irq = 1,
	.p_base_addr = &dio24_reg_base,
};

// XADC device
void __iomem *xadc_reg_base = NULL;
const struct device_info xadc_info = {			// device data used for probing/remove
	.type = TYPE_XADC,
	.name = "XADC",
	.num_irq = 0,
	.p_base_addr = &xadc_reg_base,
};

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
	{ .compatible = "xlnx,axi-dma-1.00.a" , .data = &dma24_info },		// dma24 (DMA part)
	{ .compatible = "xlnx,dio24-1.0"      , .data = &dio24_info },		// dio24 (FPGA part)
	{ .compatible = "xlnx,axi-xadc-1.00.a", .data = &xadc_info },		// XADC (A/D conversion for temperature)
//	{ .compatible = "xlnx,axi-dma-1.00.a", },		// axi_dma_0
//	{ .compatible = "xlnx,axi-dma-mm2s-channel", },		// dma channel MM2S
//	{ .compatible = "xlnx,axi-dma-s2mm-channel", },		// dma channel S2MM
	{ },							// last entry = NULL
};
MODULE_DEVICE_TABLE(of, dio24_of_match);
#else
# define dio24_of_match
#endif

struct platform_driver dio24_driver = {
	.driver = {
		.name = DIO24_DRIVER_NAME,
		.owner = THIS_MODULE,
		.of_match_table	= dio24_of_match,
	},
	.probe		= dio24_probe,
	.remove		= dio24_remove,
};

#ifdef USE_COMMAND_LINE_ARGS
// test receiving Kernel module command line arguments
// call as: modprobe dio24 myint=0x10 mystr="this is a test"
unsigned myint = 0xdeadbeef;
char *mystr = "default";

module_param(myint, int, S_IRUGO);
module_param(mystr, charp, S_IRUGO);

#endif	// USE_COMMAND_LINE_ARGS
/*
static const char device_status[] = DRIVER_INFO;
static const size_t status_size = sizeof(DRIVER_INFO);
*/

///////////////////////////////////////////////////////////////////////////////////////////////////////////////
// DIO24 device
///////////////////////////////////////////////////////////////////////////////////////////////////////////////

// open device
int dio24_open(struct inode *inode, struct file *file)
{
#ifdef DEBUG
	pr_err(NAME_DIO "device open <%s> (%i)\n", current->comm, current->pid);
#endif
	if (dio24_is_open++ == 0) try_module_get(THIS_MODULE);
	return SUCCESS;
}

// release device
int dio24_release(struct inode *inode, struct file *file)
{
#ifdef DEBUG
	pr_err(NAME_DIO "device release <%s> (%i)\n", current->comm, current->pid);
#endif
	if (--dio24_is_open == 0) module_put(THIS_MODULE);
	return SUCCESS;
}

// read from device = wait for FPGA irq
// buffer must be pointer to struct FPGA_status_run and length = sizeof(struct FPGA_status_run)
// waits for next FPGA irq and returns sizeof(struct FPGA_status_run) if ok
// on error or if timeout returns -1 and errno gives information about cause of error
// timeout is fixed to 1000ms
// note: DIO24_IOCTL_GET_STATUS_RUN gets the same information, but we do not wait for FPGA IRQ (polling)
// TODO:
// - allow to set timeout
// - function can be called by any number of users. this is not tested.
// - if not running reads register status and board time directly as IOCTL calls.
ssize_t dio24_read(struct file *file, char __user * buffer, size_t length, loff_t * offset)
{
	ssize_t result = 0;
	unsigned long flags = 0;
	struct FPGA_status_run status_FPGA;

	if((buffer == NULL) || (length != sizeof(struct FPGA_status_run))) result = -EINVAL; // bad arguments
	else {
		if (!access_ok(VERIFY_WRITE, buffer, length)) result = -EFAULT; // bad address
		else { 
			// read actual status within spinlock
			spin_lock_irqsave(&FPGA_read_lock, flags);
			status_FPGA = FPGA_read_data;
			spin_unlock_irqrestore(&FPGA_read_lock, flags);
			if ( !(status_FPGA.status & DIO_STATUS_RUN) ) { // not running: read registers within user mutex
				if(mutex_lock_interruptible(&user_mutex)) result = -EINTR; // interrupted system call
				else {
					status_FPGA.status = READ_DIO_REGISTER(DIO_REG_STATUS);
					status_FPGA.board_time = READ_DIO_REGISTER(DIO_REG_TIME);
                    status_FPGA.board_samples = READ_DIO_REGISTER(DIO_REG_SAMPLES);
					mutex_unlock(&user_mutex);
					pr_err("dio24_read: not running. last time %u us\n", status_FPGA.board_time);
					result = 0;
				}
			}
			else {  // running: wait for FPGA_irq. returns >=1 if ok, 0 on timeout, -ERESTARTSYS on signal
				// notes: 
				// - test of time changed is not done within spinlock but for changes its ok!
				// - if between testing if status_FPGA.status is running and here the irq_FPGA with end state occurred,
				//   we might miss irq and get timeout. however, in test we will see that time changed and proceed as without timeout.
				//   since this can happen (though less likely) set timeout not too long (1s or maybe even 2x1/IRQ_FREQ).
				result = wait_event_interruptible_timeout(dio24_queue, FPGA_read_data.board_time != status_FPGA.board_time, (dio24_timeout*HZ)/1000);
				if(result == -ERESTARTSYS) result = -EINTR;	
				else if((result == 0) && (FPGA_read_data.board_time == status_FPGA.board_time)) result = -ETIMEDOUT;  // timeout
				else {	// no timeout: copy last FPGA status and time to user
					spin_lock_irqsave(&FPGA_read_lock, flags);
					status_FPGA = FPGA_read_data;
					spin_unlock_irqrestore(&FPGA_read_lock, flags);
					result = 0;
				}
			}
			if (result == 0) {
			    // copy data to user buffer
			    result = __copy_to_user(buffer,&status_FPGA,sizeof(struct FPGA_status_run));
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
	if (dma24_is_open) return -EBUSY;		// allow only single client
#ifdef DEBUG
	pr_err(NAME_DMA "device open <%s> (%i)\n", current->comm, current->pid);
#endif
	dma24_is_open++;
	try_module_get(THIS_MODULE);
	// set server ready bit
	status.ctrl_FPGA |= DIO_CTRL_READY;
	WRITE_DIO_REGISTER(DIO_REG_CTRL, status.ctrl_FPGA);
	return SUCCESS;
}

// release device
int dma24_release(struct inode *inode, struct file *file)
{
#ifdef DEBUG
	pr_err(NAME_DMA "device release <%s> (%i)\n", current->comm, current->pid);
#endif
	dma24_is_open--;
	module_put(THIS_MODULE);
	// reset server ready bit
	status.ctrl_FPGA &= (~DIO_CTRL_READY);
	WRITE_DIO_REGISTER(DIO_REG_CTRL, status.ctrl_FPGA);
	return SUCCESS;
}

// read from device
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
			result = status.RD_bt_act;
		}
		else {	// length > 0
			// check user buffer
			if(buffer == NULL) result = -EFAULT;
			else if (!access_ok(VERIFY_WRITE, buffer, length)) result = -EFAULT; // bad address
			else { // user buffer ok
				result =  status.RD_bt_act; // number of available bytes
				if ( result == 0 ) { // no data available
					if ( (status.ctrl_DMA & DMA_CTRL_ACTIVE_ALL) == 0) result = -ERROR_DMA_INACTIVE;             // -11: DMA is not running
					else if ( (status.status_FPGA.status & DIO_STATUS_ERROR) != 0) result = -ERROR_FPGA;                //  -5: FPGA is in error state
					else if ( ( (status.status_FPGA.status & (DIO_STATUS_RUN|DIO_STATUS_END)) == 0) &&                  // -16: FPGA is not running and not in end
                              ( (status.ctrl_DMA & DMA_CTRL_ENABLE_FPGA) == 0 ) ) result = -ERROR_FPGA_INACTIVE; //      and will not be started automatically
				        else {
						// no data available and active transmission: wait until data available
						//pr_err(NAME_DMA "read: pid %i (%s) bytes %i, wait for data...\n", current->pid, current->comm, length);
						//pr_err(NAME_DMA "read: wait (%d ms) ...\n", status.timeout); 
									
						// unlock other user while waiting
						mutex_unlock(&user_mutex);
									
						// wait until data available or timeout or FPGA end or FPGA error
						// helper thread is waking up thread after irq handled
						// wait_event_interruptible_timeout returns >=1 if ok, 0 on timeout, -ERESTARTSYS on signal
						// wait_event_interruptible returns 0 if ok, -ERESTARTSYS on signal
						if ( status.timeout > 0 ) result = wait_event_interruptible_timeout(dma24_queue, DIO_WAKEUP(status), (status.timeout*HZ)/1000);
						else result = wait_event_interruptible(dma24_queue, DIO_WAKEUP(status));
						if(result == -ERESTARTSYS) result = -EINTR;		
						else {
							// lock again other users and read number of available bytes
							if(mutex_lock_interruptible(&user_mutex)) result = -EINTR;
							else {
								result = status.RD_bt_act;
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
		//pr_err(NAME_DMA "read result %d %x\n", result, status.RD_bt_act); 

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
	ssize_t result = -EINVAL, RX_buf_size, max_length;

	//pr_err(NAME_DMA "pid %i (%s) write %u bytes\n", current->pid, current->comm, length);

	// check user buffer
	if((offset == NULL) || (buffer == NULL)) result = -EINVAL; // bad argument
	else if (!access_ok(VERIFY_READ, buffer, length)) result = -EFAULT; // bad address
	else {
		// lock other user
		if(mutex_lock_interruptible(&user_mutex)) result = -EINTR; // interrupted system call
		else {
			// check maximum number of bytes
			max_length = status.set_samples * DIO_BYTES_PER_SAMPLE;
			if (max_length > MAX_WRITE_SIZE) result = -ENOMEM;	// all memory used
			else {
				// reduce length to maximum possible multiple of DMA_BUF_MULT
				max_length = (MAX_WRITE_SIZE - max_length) - ((MAX_WRITE_SIZE - max_length) % DMA_BUF_MULT);
				if (max_length == 0) result = -ENOMEM;		// all memory used up to a few bytes
				else {
					if (length > max_length) length = max_length;
					// copy data from user into DMA buffers
					// this increments status.set_samples
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
	static uint32_t status_test[HELPER_TASK_NUM_STATUS_IRQ];
    static struct st_par stp;
	//static struct FPGA_status_run st_run;
	static uint32_t st_count = 0;
	uint32_t ldata;
	int32_t mT;
	long result = 0;
	unsigned long flags = 0;
	struct dsc_info *info, *tmp;

	//pr_err(NAME_DMA "ioctl: %s (%i) IOCTL 0x%08X\n", current->comm, current->pid, ioctl_num);

	// TODO: for stopping user thread is always blocked (in user_mutex?), inserting task for helper was working.
	if(ioctl_num == DMA24_IOCTL_STOP) {
		// set test
		add_helper_task(HELPER_TASK_TEST, status_test, false);
		up(&helper_semaphore);	
		//pr_err(NAME_DMA "ioctl: %s (%i) IOCTL 0x%08X set task ok.\n", current->comm, current->pid, ioctl_num);
		//return 0;	
	}

	// lock other users
	if(mutex_lock_interruptible(&user_mutex)) result = -EINTR;
	else {
		switch (ioctl_num) 
		{
			case DMA24_IOCTL_RESET:
				result = reset_all();
				break;	
			case DIO24_IOCTL_SET_CONFIG: // set FPGA control bits and return new values
				result = get_user(ldata, (uint32_t*) ioctl_param);
				if(!result) {				
					result = set_config(&ldata);
					if(!result) {
						result = put_user(ldata, (uint32_t*) ioctl_param);
					}
				}
				break;	
			case DIO24_IOCTL_GET_CONFIG: // read FPGA control bits directly
				result = status.ctrl_FPGA = READ_DIO_REGISTER(DIO_REG_CTRL);
				break;	
			case DIO24_IOCTL_SET_TEST: // set test bits: returns new test bits
                pr_err("SET_TEST 0x%x\n", (unsigned) ioctl_param);
				WRITE_DIO_REGISTER(DIO_REG_TEST, ioctl_param);
                result = status.ctrl_test = ioctl_param;
				break;	
			case DIO24_IOCTL_GET_TEST: // read test bits
				result = status.ctrl_test = READ_DIO_REGISTER(DIO_REG_TEST);
				break;	
			case DIO24_IOCTL_SET_SYNC_DELAY: // set sync delay: return new delay
				WRITE_DIO_REGISTER(DIO_REG_SYNC_DELAY, ioctl_param);
                result = status.sync_delay = ioctl_param;
				break;	
			case DIO24_IOCTL_GET_SYNC_DELAY: // read sync delay
				result = status.sync_delay = READ_DIO_REGISTER(DIO_REG_SYNC_DELAY);
				break;	
			case DIO24_IOCTL_SET_SYNC_PHASE: // set absolute {ext,det} phase: return relative {ext,det} phase
                // external phase
                ldata = ((ioctl_param>>SYNC_PHASE_BITS) & SYNC_PHASE_MASK_1) % PHASE_360;
                ldata = (ldata >= status.phase_ext) ? ldata-status.phase_ext : (ldata+PHASE_360)-status.phase_ext;
                status.phase_ext = (status.phase_ext + ldata) % PHASE_360;
                // detector phase
                ioctl_param = (ioctl_param & SYNC_PHASE_MASK_1) % PHASE_360;
                ioctl_param = (ioctl_param >= status.phase_det) ? ioctl_param-status.phase_det : (ioctl_param+PHASE_360)-status.phase_det;
                status.phase_det = (status.phase_det + ioctl_param) % PHASE_360;
                // set relative phase
                result = status.sync_phase = (ldata << SYNC_PHASE_BITS) | ioctl_param;
				WRITE_DIO_REGISTER(DIO_REG_SYNC_PHASE, status.sync_phase);
                //pr_err("SET_SYNC_PHASE 0x%x\n", ioctl_param );
				break;	
			case DIO24_IOCTL_GET_SYNC_PHASE: // read {ext,det} absolute phase
				result = (status.phase_ext << SYNC_PHASE_BITS) | status.phase_det;
				break;	
            case DIO24_IOCTL_GET_SYNC_TIME: // get sync time
                result = READ_DIO_REGISTER(DIO_REG_SYNC_TIME);
                //pr_err("sync time %d\n", result);
                break;
			case DMA24_IOCTL_START:
				if ( ( (status.ctrl_DMA & (DMA_CTRL_ACTIVE_ALL|DMA_CTRL_ENABLE_ALL)) != 0) || // already running
				     ( mem_TX.first == NULL ) || ( mem_RX.first == NULL ) || ( status.bt_tot == 0 ) // no TX or RX buffer allocated
				   ) result = -ERROR_ILLEGAL_STATE;
				else if ( status.bt_tot % DIO_BYTES_PER_SAMPLE ) result = -EINVAL; // total number of bytes must be multiple of samples size
                else if (copy_from_user(&stp, (struct st_par *)ioctl_param, sizeof(struct st_par)) != 0) result = -EFAULT; // bad address
				else {
					// append NOP samples to last buffer if needed
					// calculates status.set_samples and updates status.bt_tot
					result = append_TX();
					if (!result) {
						// write # samples before starting TX
						WRITE_DIO_REGISTER(DIO_REG_DATA_NUM, status.set_samples);
						wmb();					
						while (READ_DIO_REGISTER(DIO_REG_DATA_NUM) != status.set_samples); // read back to be sure its written
						// set internal/external clock
						result = set_ext_clk_FPGA((status.ctrl_FPGA & DIO_CTRL_EXT_CLK) ? true : false);
						if (result == 0) {
							// reset repetitions
							status.reps_set = stp.repetitions;
							status.reps_act = 0L;
							// set FPGA status to RUN (no other bits) and all others to 0 to indicate that will be started but no irq_FPGA yet
							spin_lock_irqsave(&FPGA_read_lock, flags);
							FPGA_read_data.status = DIO_STATUS_RUN;
							FPGA_read_data.board_time = 0;
                            FPGA_read_data.board_samples = 0;
                            //irq_ctrl = DIO_STATUS_RUN;
                            irq_FPGA = 0;
							spin_unlock_irqrestore(&FPGA_read_lock, flags);
							// start DMA TX and RX channels
							result = start_RX();
							if (result >= 0) {
								result = start_TX();
								if(result >= 0) {
									++st_count;
									if (stp.flags & START_FPGA_NOW) // start FPGA 
#ifdef PERF_START_IRQ_UP                // with PERF_START_IRQ_UP flag we cannot wait for run bit
                                        result = start_FPGA((status.ctrl_FPGA & PERF_START_IRQ_UP) ? false : true);
#else
                                        result = start_FPGA(true); // wait for run bit to be set before returning. TODO: is this needed?
#endif
                                    else status.ctrl_DMA |= DMA_CTRL_ENABLE_FPGA; // start FPGA when DIO_FPGA_START_BT TX bytes or all data transferred
								}
							}
						}
					}
				}
				break;	
			case DMA24_IOCTL_STOP:
				result = stop_FPGA();
				stop_TX(true);
				stop_RX(true);
                //result = reset_all();
				break;
            case DIO24_IOCTL_START: // start FPGA without DMA (use with timing_test module)
				// set FPGA status to RUN (no other bits) and all others to 0 to indicate that will be started but no irq_FPGA yet
				spin_lock_irqsave(&FPGA_read_lock, flags);
				FPGA_read_data.status = DIO_STATUS_RUN;
				FPGA_read_data.board_time = 0;
                FPGA_read_data.board_samples = 0;
                //irq_ctrl = DIO_STATUS_RUN;
                irq_FPGA = 0;
				spin_unlock_irqrestore(&FPGA_read_lock, flags);
                result = start_FPGA(ioctl_param != 0);
                break;
            case DIO24_IOCTL_STOP: // stop FPGA without DMA (use with timing_test module)
                result = stop_FPGA();
                break;
            case DIO24_IOCTL_RESET: // reset FPGA without DMA (use with timing_test module)
                result = reset_FPGA();
                break;
            case DIO24_IOCTL_TIMING_TEST: // set test bits and return board_time_ext
                WRITE_DIO_REGISTER(DIO_REG_TEST, ioctl_param & DIO_TEST_MASK);
                switch (ioctl_param & (DIO_TEST_RUN|DIO_TEST_UPDATE)) { 
                    case 0: // reset run bit: return board_time_ext
                        result = READ_DIO_REGISTER(DIO_REG_TIME_EXT);
                        break;
                    case DIO_TEST_RUN|DIO_TEST_UPDATE: // update & run bits: return board_time_ext and reset update bit
                        result = READ_DIO_REGISTER(DIO_REG_TIME_EXT);
                        WRITE_DIO_REGISTER(DIO_REG_TEST, DIO_TEST_RUN);
                        break;
                    default: // nothing to return
                        result = 0;
                }
                // timing test measure number of cycles @ f_PL=50MHz: no action = 16, write = 33, read = 37, write & read = 54-65
                //WRITE_DIO_REGISTER(DIO_REG_CTRL, status.ctrl_FPGA | DIO_CTRL_RUN);
                //WRITE_DIO_REGISTER(DIO_REG_DATA_NUM, 8192);
                //result = READ_DIO_REGISTER(DIO_REG_STATUS);
                //WRITE_DIO_REGISTER(DIO_REG_CTRL, status.ctrl_FPGA & (~DIO_CTRL_RUN));
                break;
			case DMA24_IOCTL_SET_TIMEOUT:
				result = get_user(ldata, (uint32_t*) ioctl_param);
				if(!result) {
					result = put_user(status.timeout, (uint32_t*) ioctl_param);
					status.timeout = ldata;
				}
				break;
			case DMA24_IOCTL_SET_RX_BUFFER:
				result = get_user(ldata, (uint32_t*) ioctl_param);
				if(!result) {
					result = put_user(status.RD_bt_max, (uint32_t*) ioctl_param);
					status.RD_bt_max = ldata;
					result = prepare_RX_buffers(ldata, true);
				}
				break;
			case DIO24_IOCTL_GET_STATUS:
			case DIO24_IOCTL_GET_STATUS_DBG:
				// update status
				// Attention: update_status will overwrite control register content of status when not yet written to FPGA!
				//            status.control is save since SET_CONFIG writes directly to FPGA
				//	      status.set_samples would be overwritten if get_status is called between write() and start()
				//            we still return 'actual' value but save control registers here temporarily
				ldata = status.set_samples; // at the moment this is the only control register in danger.
				//update_status(NULL,false);
				// update FPGA status registers
				// NOTE: while FPGA is running registers are maintained by dio24_irq until at end or error helper thread updates status.
				//       if not running we directly read status register and board time.
				if (status.status_FPGA.status & DIO_STATUS_RUN) {
					spin_lock_irqsave(&FPGA_read_lock, flags);
					status.status_FPGA = FPGA_read_data;
					spin_unlock_irqrestore(&FPGA_read_lock, flags);
				}
				else {
					status.status_FPGA.status = READ_DIO_REGISTER(DIO_REG_STATUS);
					status.status_FPGA.board_time = READ_DIO_REGISTER(DIO_REG_TIME);
                    status.status_FPGA.board_samples = READ_DIO_REGISTER(DIO_REG_SAMPLES);
				}
                // get actual sync time, extra time and sample registers
				status.sync_time = READ_DIO_REGISTER(DIO_REG_SYNC_TIME);
				status.board_time_ext = READ_DIO_REGISTER(DIO_REG_TIME_EXT);
                status.board_samples_ext = READ_DIO_REGISTER(DIO_REG_SAMPLES_EXT);
				// get actual temperature
				status.FPGA_temp = READ_XADC_REGISTER(XADC_TEMP_ACT);
				// copy status into user buffer
				if(copy_to_user((struct FPGA_status *)ioctl_param, &status, sizeof(struct FPGA_status)) != 0) result = -EFAULT; // bad address
				status.set_samples = ldata;
				if (ioctl_num == DIO24_IOCTL_GET_STATUS_DBG) { // print memory and dsc info on console
					pr_err(NAME_DMA "TX dsc:\n");
					check_dsc(&dsc_TX, true);
					pr_err(NAME_DMA "TX buffer:\n");
					check_mem(&mem_TX, true, true);
					pr_err(NAME_DMA "RX dsc:\n");
					check_dsc(&dsc_RX, true);
					pr_err(NAME_DMA "RX buffer:\n");
					check_mem(&mem_RX, true, false);
					ldata = READ_XADC_REGISTER(XADC_TEMP_ACT); mT = GET_mT(ldata);
					pr_err(NAME_DMA "T act     = %4d.%03u deg.C (%u)\n", mT/1000, (mT >= 0) ? mT%1000 : (-mT)%1000, ldata);
					ldata = READ_XADC_REGISTER(XADC_TEMP_MIN); mT = GET_mT(ldata);
					pr_err(NAME_DMA "T min     = %4d.%03u deg.C (%u)\n", mT/1000, (mT >= 0) ? mT%1000 : (-mT)%1000, ldata);
					ldata = READ_XADC_REGISTER(XADC_TEMP_MAX); mT = GET_mT(ldata);
					pr_err(NAME_DMA "T max     = %4d.%03u deg.C (%u)\n", mT/1000, (mT >= 0) ? mT%1000 : (-mT)%1000, ldata);
					ldata = READ_XADC_REGISTER(XADC_TEMP_ALARM_LOWER); mT = GET_mT(ldata);
					pr_err(NAME_DMA "T alarm_l = %4d.%03u deg.C (%u)\n", mT/1000, (mT >= 0) ? mT%1000 : (-mT)%1000, ldata);
					ldata = READ_XADC_REGISTER(XADC_TEMP_ALARM_UPPER); mT = GET_mT(ldata);
					pr_err(NAME_DMA "T alarm_u = %4d.%03u deg.C (%u)\n\n", mT/1000, (mT >= 0) ? mT%1000 : (-mT)%1000, ldata);

					pr_err(NAME_DMA "%u loops done\n", st_count);
					pr_err(NAME_DMA "dbg cnt = %u/%u/%u/%u/%u/%u\n", 
						debug_DMA_count[DBG_TX_DSC], debug_DMA_count[DBG_RX_DSC], 
						debug_DMA_count[DBG_TX_BUF], debug_DMA_count[DBG_RX_BUF],
						debug_DMA_count[DBG_BUF_POOL],debug_DMA_count[DBG_TEST]);

					// DSC allocation test
					info = tmp = allocate_dsc(1, DBG_TEST);
					ldata = 0;
					while(tmp) {
						++ldata;
						tmp = tmp->next = allocate_dsc(1, DBG_TEST);
					} 
					pr_err(NAME_DMA "%u dscs * %u/%u bytes = %u/%u bytes allocated\n", ldata, sizeof(struct dsc_info), sizeof(struct SG_dsc)+SG_ALIGN-1, ldata*sizeof(struct dsc_info),ldata*(sizeof(struct SG_dsc)+SG_ALIGN-1));
					result = free_dsc_no_pool(info, DBG_TEST);
					if(result != 0) pr_err(NAME_DMA "%u dscs allocated error %ld\n", ldata, result);
					else pr_err(NAME_DMA "%u dscs allocated ok\n", ldata);
				}
				break;
			case DIO24_IOCTL_GET_STATUS_RUN: 
				// NOTE: while FPGA is running registers are maintained by dio24_irq until at end or error helper thread updates status.
				//       if not running we directly read status register and board time.
				if (status.status_FPGA.status & DIO_STATUS_RUN) {
					spin_lock_irqsave(&FPGA_read_lock, flags);
					status.status_FPGA = FPGA_read_data;
					spin_unlock_irqrestore(&FPGA_read_lock, flags);
				}
				else {
					status.status_FPGA.status = READ_DIO_REGISTER(DIO_REG_STATUS);
					status.status_FPGA.board_time = READ_DIO_REGISTER(DIO_REG_TIME);
					status.status_FPGA.board_samples = READ_DIO_REGISTER(DIO_REG_SAMPLES);
				}
				if(copy_to_user((struct FPGA_status_run *)ioctl_param, &status.status_FPGA.status, sizeof(struct FPGA_status_run)) != 0) result = -EFAULT; // bad address
				break;
			case DMA24_IOCTL_GET_LOAD:
				result = (((status.dsc_RX_c*100)/(DSC_RX_NUM-1))<<16) | ((status.dsc_TX_c*100)/(DSC_RX_NUM-1));
				break;
			case DMA24_IOCTL_GET_LOAD_TX:
				result = (status.dsc_TX_c*100)/(DSC_TX_NUM-1);
				break;
			case DMA24_IOCTL_GET_LOAD_RX:
				result = (status.dsc_RX_c*100)/(DSC_RX_NUM-1);
				break;
			case DMA24_IOCTL_GET_STATUS_TX: // read DMA status TX bits directly
				result = status.status_TX = READ_DMA_REGISTER(DMA_REG_MM2S_STATUS);
				break;
			case DMA24_IOCTL_GET_STATUS_RX: // read DMA status RX bits directly
				result = status.status_RX = READ_DMA_REGISTER(DMA_REG_S2MM_STATUS);
				break;
			case DIO24_IOCTL_GET_STATUS_FPGA: // read FPGA status bits directly
				result = status.status_FPGA.status = READ_DIO_REGISTER(DIO_REG_STATUS);
				break;
			case DMA24_IOCTL_GET_CONFIG: // return DMA control bits (these are not the ones in register)
				result = status.ctrl_DMA;
				break;	
/*
			case DIO24_IOCTL_GET_INT_CLOCK:
				ldata = status.clock_int;
				err_RX = put_user(ldata, (uint32_t*) ioctl_param);
				if(err_RX != 0)	pr_err(NAME_DMA "get int clock: write error!\n");
				else pr_err(NAME_DMA "get int clock ok: %x!\n", ldata);
				break;	
			case DIO24_IOCTL_GET_EXT_CLOCK:
				ldata = status.clock_ext;
				err_RX = put_user(ldata, (uint32_t*) ioctl_param);
				if(err_RX != 0)	pr_err(NAME_DMA "get ext clock: write error!\n");
				else pr_err(NAME_DMA "get ext clock ok: %x!\n", ldata);
				break;	
			case DIO24_IOCTL_SET_EXT_CLOCK:
				err_TX = get_user(ldata, (uint32_t*) ioctl_param);
				if(err_TX != 0) pr_err(NAME_DMA "set ext clock: read error!\n");
				else {		
					WRITE_DIO_REGISTER(DIO_REG_EXT_CLOCK, ldata);
					ldata = status.clock_ext = READ_DIO_REGISTER(DIO_REG_EXT_CLOCK);
					err_TX = put_user(ldata, (uint32_t*) ioctl_param);
					if(err_TX != 0) pr_err(NAME_DMA "set ext clock: write error!\n");
					else {
						pr_err(NAME_DMA "set ext clock: ok\n");
					}
				}
				break;	
			case DIO24_IOCTL_GET_MULT:
				ldata = status.time_mult;
				err_RX = put_user(ldata, (uint32_t*) ioctl_param);
				if(err_RX != 0)	pr_err(NAME_DMA "get multiplicator: write error!\n");
				else pr_err(NAME_DMA "get multiplicator ok: %x!\n", ldata);
				break;	
			case DIO24_IOCTL_SET_MULT:
				err_TX = get_user(ldata, (uint32_t*) ioctl_param);
				if(err_TX != 0) pr_err(NAME_DMA "set multiplicator: read error!\n");
				else {		
					WRITE_DIO_REGISTER(DIO_REG_TIME_MULT, ldata);
					ldata = status.time_mult = READ_DIO_REGISTER(DIO_REG_TIME_MULT);
					err_TX = put_user(ldata, (uint32_t*) ioctl_param);
					if(err_TX != 0) pr_err(NAME_DMA "set multiplicator: write error!\n");
					else {
						pr_err(NAME_DMA "set multiplicator: ok\n");
					}
				}
				break;	
			case DIO24_IOCTL_GET_EXTRIG:
				ldata = status.FPGA_ctrl & DIO_TRG_BITS;
				err_RX = put_user(ldata, (uint32_t*) ioctl_param);
				if(err_RX != 0)	pr_err(NAME_DMA "get trigger config: write error!\n");
				else pr_err(NAME_DMA "get trigger config: %x!\n", ldata);
				break;	
			case DIO24_IOCTL_SET_EXTRIG:
				err_TX = get_user(ldata, (uint32_t*) ioctl_param);
				if(err_TX != 0) pr_err(NAME_DMA "set trigger config: read error!\n");
				else {		
					WRITE_DIO_REGISTER(DIO_REG_TIME_MULT, (ldata & DIO_TRG_BITS) | (status.FPGA_ctrl & (~DIO_TRG_BITS)));
					ldata = status.FPGA_ctrl = READ_DIO_REGISTER(DIO_REG_TIME_MULT);
					err_TX = put_user(ldata & DIO_TRG_BITS, (uint32_t*) ioctl_param);
					if(err_TX != 0) pr_err(NAME_DMA "set trigger config: write error!\n");
					else {
						pr_err(NAME_DMA "set trigger config: ok\n");
					}
				}
				break;	*/
			default:
				result = -EINVAL;
		}

		// unlock other users
		mutex_unlock(&user_mutex);
	}

	//pr_err(NAME_DMA "ioctl: %s (%i) IOCTL 0x%08X err = %d/%d\n", current->comm, current->pid, ioctl_num, err_TX, err_RX);

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
	static uint32_t status_irq_FPGA[HELPER_TASK_NUM_STATUS_IRQ]; // TODO: not used anymore but required for add_helper_task
	uint32_t ctrl, status, time, samples;
    //bool ctrl_disable_irq = false;

	// save registers
	status  = READ_DIO_REGISTER(DIO_REG_STATUS);
	time    = READ_DIO_REGISTER(DIO_REG_TIME);
    samples = READ_DIO_REGISTER(DIO_REG_SAMPLES);
	ctrl    = READ_DIO_REGISTER(DIO_REG_CTRL);

	// reset irq enable bit which also resets irq(s)
	WRITE_DIO_REGISTER(DIO_REG_CTRL, ctrl & (~DIO_CTRL_IRQ_EN));

	// enable irq again if there is no error
	if (!(status & DIO_STATUS_IRQ_FPGA_ERR)) WRITE_DIO_REGISTER(DIO_REG_CTRL, ctrl);

	// save status and time within spinlock
	// note: this is executed in irq context, so we do not need the irqsave/irqrestore versions
	spin_lock(&FPGA_read_lock);
	FPGA_read_data.status        = status;
	FPGA_read_data.board_time    = time;
    FPGA_read_data.board_samples = samples;
    //irq_ctrl = ctrl;
    //irq_ctrl_update = ctrl_update;
    ++irq_FPGA;
	spin_unlock(&FPGA_read_lock);

	if (!(status & DIO_STATUS_RUN)) {
		// if run bit not set wakeup helper which updates global status within user mutex
		// we update FPGA_read_data and control registers and irq count
        // this is needed to detect end state or error in dio24_read(). DIO24_IOCTL_GET_STATUS_RUN reads directly FPGA_read_data.
		//pr_err("FPGA irq %u %u %u %u us\n", ctrl, irq_count_FPGA, status, time);
		//status_irq_FPGA[HELPER_STATUS_TX] = ctrl;
		//status_irq_FPGA[HELPER_STATUS_RX] = irq_count_FPGA;
		add_helper_task(HELPER_TASK_IRQ_FPGA, status_irq_FPGA, true);
		//irq_count_FPGA = 0;
	}

	// wakup waiting thread in dio24_read
	// TODO: is this the right function from irq context?
	wake_up_interruptible(&dio24_queue);

	// irq was handled
	return IRQ_HANDLED;
}
irqreturn_t dma24_irq_TX(int irq, void *lp)
{
	static uint32_t status_irq_TX[HELPER_TASK_NUM_STATUS_IRQ];
	
	// get status registers and acknowledge IRQ in hardware
	irq_ack_TX(status_irq_TX);

	// save helper task in ringbuffer
	// lock ensures helper is not reading task at the same time
	// when ring buffer is full we overwrite oldest entry (helper_task_first)
	add_helper_task(HELPER_TASK_IRQ_DMA, status_irq_TX, true);

	// irq was handled
	return IRQ_HANDLED;
}
irqreturn_t dma24_irq_RX(int irq, void *lp)
{
	static uint32_t status_irq_RX[HELPER_TASK_NUM_STATUS_IRQ];

	// get status registers and acknowledge IRQ in hardware
	irq_ack_RX(status_irq_RX);

	// save helper task in ringbuffer
	// lock ensures helper is not reading task at the same time
	// when ring buffer is full we overwrite oldest entry (helper_task_first)
	add_helper_task(HELPER_TASK_IRQ_DMA, status_irq_RX, true);

	// irq was handled
	return IRQ_HANDLED;
}

///////////////////////////////////////////////////////////////////////////////////////////////////////////////
// helper thread
///////////////////////////////////////////////////////////////////////////////////////////////////////////////

// create HELPER_TASKS_NUM helper tasks in ringbuffer
// returns 0 if ok, otherwise error
inline int create_helper_tasks(void) {
	int err = 0, i;
	struct helper_task *next;
	helper_task_first = helper_task_last = NULL;
	for(i=0; i<HELPER_TASKS_NUM; ++i) {
		next = (struct helper_task *) kmalloc(sizeof(struct helper_task), GFP_KERNEL);
		if(next == NULL) { err = -1; break; }
		memset(next,0,sizeof(struct helper_task));
		if(helper_task_first == NULL) helper_task_first = helper_task_last = next;
		else helper_task_last = helper_task_last->next = next;
	}
	if(!err) {
		helper_task_last->next = helper_task_first; // close ringbuffer
	}
	helper_task_last = NULL;
	helper_tasks = helper_tasks_max = 0;
	return err;
}

// append helper task to ringbuffer, if task==HELPER_TASK_IRQ executed in irq context
// notes:
// - if task = HELPER_TASK_IRQ is the same as last task ORs status together, takes latest time and saves in last
//   since these are by far the most common tasks this reduces task usage significantly
// - usage of ringbuffer avoids allocation during irq routine! but oldest entries might be overwritten!
//   additionally, this requires copying of tasks and status entries.
// TODO: maybe use static variables protected by spinlock instead of 'status'. merging is now quite rare but can be counted there.
inline void add_helper_task(int task, uint32_t status[HELPER_TASK_NUM_STATUS_IRQ], bool is_irq) {
	unsigned long flags = 0L;
	int i;

	if(is_irq) spin_lock(&helper_task_lock); // called from irq context: irq's are already disabled
	else spin_lock_irqsave(&helper_task_lock, flags); // called from normal context: must disable irq's otherwise could deadlock itself
	if(helper_task_last == NULL) { // zero entries
		if(++helper_tasks > helper_tasks_max) helper_tasks_max = helper_tasks;	
		helper_task_last = helper_task_first;
		helper_task_last->task = task;
		for(i=0; i<HELPER_TASK_NUM_STATUS_IRQ; ++i) helper_task_last->status[i]=status[i];
		helper_task_last->status[HELPER_STATUS_NUM_IRQ] = 1L;
	}
	else { // nonzero entries
		if((task & HELPER_TASK_IRQ_DMA) && (helper_task_last->task & HELPER_TASK_IRQ_DMA)) {	// merge HELPER_TASK_IRQ_DMA
			helper_task_last->status[HELPER_STATUS_TX] |= status[HELPER_STATUS_TX];		// OR with old TX status
			helper_task_last->status[HELPER_STATUS_RX] |= status[HELPER_STATUS_RX];		// OR with old RX status
			//helper_task_last->status[HELPER_STATUS_FPGA] |= status[HELPER_STATUS_FPGA];	// OR with old FPGA status
			//helper_task_last->status[HELPER_STATUS_SEC] = status[HELPER_STATUS_SEC];	// take new seconds
			//helper_task_last->status[HELPER_STATUS_USEC] = status[HELPER_STATUS_USEC];	// take new micro-seconds
			helper_task_last->status[HELPER_STATUS_NUM_IRQ]++;				// number of irq's merged
			helper_task_last->task |= task;							// OR tasks
		}
		else {
			// different tasks
			if(++helper_tasks > helper_tasks_max) helper_tasks_max = helper_tasks;
			if(helper_task_last->next == helper_task_first) helper_task_first = helper_task_first->next; // overwrite oldest!
			helper_task_last = helper_task_last->next;
			helper_task_last->task = task;
			for(i=0; i<HELPER_TASK_NUM_STATUS_IRQ; ++i) helper_task_last->status[i]=status[i];
			helper_task_last->status[HELPER_STATUS_NUM_IRQ] = 1L;
		}
	}
	if(is_irq) spin_unlock(&helper_task_lock);
	else spin_unlock_irqrestore(&helper_task_lock, flags);

	// wakeup helper thread
	// note: only spin_locks and semaphore up() are allowed in atomic (irq) context!
	//pr_err(NAME_DRV "wake up helper...\n");
	up(&helper_semaphore);
}

// copy helper task from ringbuffer, executed by helper thread
// returns HELPER_TASK_NONE if empty
// todo: this is executed by helper thread which could just exchange struct helper_task's to avoid copying
//       for dio24_irq executing add_helper_task this cannot be done since he might need to insert more than 2 structures
inline void copy_helper_task(struct helper_task *task) {
	unsigned long flags = 0L;
	int i;
	spin_lock_irqsave(&helper_task_lock, flags);
	if(helper_task_last == NULL) {
		task->task = HELPER_TASK_NONE;
	}
	else {
		task->task = helper_task_first->task;
		for(i=0; i<HELPER_TASK_NUM_STATUS; ++i) task->status[i] = helper_task_first->status[i];
		if(helper_task_first == helper_task_last) helper_task_last = NULL;
		helper_task_first = helper_task_first->next;
		--helper_tasks;
	}
	spin_unlock_irqrestore(&helper_task_lock, flags);
}

/* show all helper tasks in ringbuffer
inline void show_helper_tasks(void) {
	static char tasks[7][5] = {"NONE","IRQd","IRQf","TEST","EXIT","????"};
	uint32_t i = 0;
	unsigned long flags = 0L;
	char *tsk;
	struct helper_task *next;
	
	spin_lock_irqsave(&helper_task_lock, flags);
	next = helper_task_first;
	if(next) {
		pr_err(NAME_DRV "helper tasks:\n[sec.mu    ] ## task (i) irq stat__TX stat__RX bts\n");
		do {
			switch(next->task) {
				case HELPER_TASK_NONE: tsk = tasks[0]; break;
				case HELPER_TASK_IRQ_DMA: tsk = tasks[1]; break;
				case HELPER_TASK_IRQ_FPGA: tsk = tasks[2]; break;
				case HELPER_TASK_TEST: tsk = tasks[3]; break;
				case HELPER_TASK_EXIT: tsk = tasks[4]; break;
				default:               tsk = tasks[5];
			}
			pr_err("%2u %s (%d) %3u %8x %8x %c\n", 
			//pr_err("[%3lu.%06lu] %2lu %s (%d) %3lu %8lx %8lx %s\n", 
				//next->status[HELPER_STATUS_SEC] % 1000, 
				//next->status[HELPER_STATUS_USEC], 
				i, tsk, next->task, 
				next->status[HELPER_STATUS_NUM_IRQ],
				next->status[HELPER_STATUS_TX], 
				next->status[HELPER_STATUS_RX],
				next == helper_task_last ? 'l': next == helper_task_first ? 'f' : ' ');
			next = next->next;
			++i;
		} while(next != helper_task_first);
	}
	spin_unlock_irqrestore(&helper_task_lock, flags);
	pr_err(NAME_DRV "act/tot/max tasks %u/%u/%u, IRQs TX/RX %u/%u\n", helper_tasks, i, helper_tasks_max, irq_count_TX, irq_count_RX);
}*/

// delete all helper tasks
inline void delete_helper_tasks(void) {
	int i;
	for(i=0; i<HELPER_TASKS_NUM; ++i) {
		helper_task_last = helper_task_first->next;
		kfree(helper_task_first);
		helper_task_first = helper_task_last;
	}
	helper_task_first = helper_task_last = NULL;
}

/* add helper task to ringbuffer
#define ADD_HELPER_TASK(t, status, i, flags) { \
	spin_lock_irqsave(&helper_task_lock, flags); \
	if((helper_task_first != HELPER_TASK_NONE) && (helper_task_first == helper_task_next)) helper_task_first = helper_task_first->next; \
	helper_task_next->task = t; \
	for(i=0; i<HELPER_TASK_NUM_STATUS; ++i) helper_task_next->status[i]=status[i];\
	helper_task_next = helper_task_next->next; \
	spin_unlock_irqrestore(&helper_task_lock, helper_task_lock_flags); \
}

// copy helper task from ringbuffer
#define COPY_HELPER_TASK(_task, flags) { \
	spin_lock_irqsave(&helper_task_lock, flags); \
	_task = *helper_task_first; \
	helper_task_first->task = HELPER_TASK_NONE; \
	helper_task_first = helper_task_first-> next; \
	spin_unlock_irqrestore(&helper_task_lock, flags); \
}*/

// helper thread
int helper_thread(void *data) {
	int err = 0;
	unsigned long flags = 0L;
	struct helper_task task;
	//struct task_struct *tsk;
	//void kthread_bind(struct task_struct *thread, int cpu); // todo: bind helper on 2nd CPU?
	//struct sched_param param = { .sched_priority = 0 };
	
	//pr_err(NAMEH "pid %i (%s) started\n", current->pid, current->comm);

	// lower thread priority for testing
	//sched_setscheduler(current, SCHED_NORMAL, &param);
	//set_user_nice();

    pr_err(NAMEH "pid %i (%s) waiting for IRQ ...\n", current->pid, current->comm);
	while (!err) {
		// wait for next IRQ
		if(down_interruptible(&helper_semaphore)) {
			pr_err(NAMEH "pid %i (%s) signal received!\n", current->pid, current->comm);
			break;
		}
		// get next task within spinlock
		copy_helper_task(&task);
		switch(task.task) {
			case HELPER_TASK_NONE:				// no task (might happen)
				break;
			case HELPER_TASK_IRQ_DMA: 
				// process IRQ result
				//pr_err(NAMEH "pid %i (%s) handle IRQ\n", current->pid, current->comm);

				// lock out other users, this ensures consistency of DMA but might block!
				if(mutex_lock_interruptible(&user_mutex)) {
					pr_err(NAMEH "pid %i (%s) signal received!\n", current->pid, current->comm);
					err = -EINTR;
					break;
				}

				// irq_handler
				if(task.task & HELPER_TASK_IRQ_DMA) irq_hdl_DMA (task.status);
				
				//pr_err(NAMEH "wakeup 'read', IRQs=%u/%u, error=%d/%d status=%x\n", status.irq_TX, status.irq_RX, status.err_TX, status.err_RX, status.DMA_ctrl);

				// allow other users again
				mutex_unlock(&user_mutex);

				// wakeup reading process(es)
				wake_up_interruptible(&dma24_queue);
				break;
			case HELPER_TASK_IRQ_FPGA: // called after FPGA is stopped (end or error) from DMA24_IOCTL_STOP and dio24_irq
				// lock out other users, this ensures consistency of DMA but might block!
				if(mutex_lock_interruptible(&user_mutex)) {
					pr_err(NAMEH "pid %i (%s) signal received!\n", current->pid, current->comm);
					err = -EINTR;
					break;
				}
				// update status with FPGA registers and irq counter (note: task.status is not used)
				spin_lock_irqsave(&FPGA_read_lock, flags);
				status.status_FPGA = FPGA_read_data;
                if(FPGA_read_data.status & DIO_STATUS_IRQ_FPGA_ERR) {
                    status.ctrl_FPGA &= (~DIO_CTRL_IRQ_EN); // dio24_irq handler disables irq's on error
                }
                status.irq_FPGA = irq_FPGA;
				spin_unlock_irqrestore(&FPGA_read_lock, flags);
				//status.ctrl_FPGA = task.status[HELPER_STATUS_TX];
				//status.irq_FPGA += task.status[HELPER_STATUS_RX];
				pr_err("\n" NAMEH "FPGA irq 0x%x %u us # %u\n\n", status.status_FPGA.status, status.status_FPGA.board_time, status.status_FPGA.board_samples);
				// allow other users again
				mutex_unlock(&user_mutex);
				break;
			case HELPER_TASK_EXIT:
		 		pr_err(NAMEH "pid %i (%s) exit request received\n", current->pid, current->comm);
				err = 99;
				break;
			case HELPER_TASK_TEST:
		 		//pr_err(NAMEH "pid %i (%s) stop!\n", current->pid, current->comm);
				/* lock out other users, this ensures consistency of DMA but might block!
				if(mutex_lock_interruptible(&user_mutex)) {
					pr_err(NAMEH "pid %i (%s) signal received!\n", current->pid, current->comm);
					err = -EINTR;
					break;
				}
				else {
					//status.DMA_ctrl |= DMA_CTRL_STOP_ALL_AT_END;
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
		delete_helper_tasks();
	}
	pr_err(NAMEH "pid %i (%s) ended (error %d)\n", current->pid, current->comm, err);
	return err;
}
///////////////////////////////////////////////////////////////////////////////////////////////////////////////
// driver/module functions
///////////////////////////////////////////////////////////////////////////////////////////////////////////////

// called after device initialization
inline void device_init(int type) {
	if(type == TYPE_DMA24) {
		// reset status
		memset(&status, 0, sizeof(struct FPGA_status));
		// set default reps
		status.reps_set = 1;
		// update FPGA status if dio24 was probed before
		status.status_FPGA = FPGA_read_data;
		// get actual dio24 status
		update_status(NULL, false);
	}
	else if (type == TYPE_DIO24) {
		// read DIO control registers
		FPGA_read_data.status = READ_DIO_REGISTER(DIO_REG_STATUS);
		FPGA_read_data.board_time = READ_DIO_REGISTER(DIO_REG_TIME);
        FPGA_read_data.board_samples = READ_DIO_REGISTER(DIO_REG_SAMPLES);
		// save into status if dma24 was probed before
		status.status_FPGA = FPGA_read_data;
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
        int rc = 0, i;
	struct resource *r_irq; /* Interrupt resources */
	struct resource *r_mem; /* IO mem resources */
	struct device *dev = &pdev->dev;
	struct dio24_local *lp = NULL;
	const struct of_device_id *match = of_match_device(dio24_of_match, dev);

	// probing dma or dio device?
	//pr_err(NAME_DRV "pid %i (%s) device probing ...\n", current->pid, current->comm);

	if(!match) return -ENODEV; // not our device

	// allocate private memory
	lp = (struct dio24_local *) kmalloc(sizeof(struct dio24_local), GFP_KERNEL);
	if (!lp) {
		dev_err(dev, "private memory allocation failed!\n");
		return -ENOMEM;
	}
	dev_set_drvdata(dev, lp);
	lp->data = (struct device_info *) match->data;

	if(*lp->data->p_base_addr != NULL) {
		dev_err(dev, "device %s already probed!\n", lp->data->name);
		rc = -EBUSY;
		goto error1;
	}
	dev_info(dev, "probing %s device...\n", lp->data->name);
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

//pr_err(NAME_DRV "get %d irqs %s device...\n", lp->data->num_irq, lp->data->name);
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
		dev_info(dev,"(%s) at 0x%08X mapped to 0x%08X, irq=%d/%d\n", lp->data->name,
			(unsigned int __force)lp->mem_start, (unsigned int __force)*lp->data->p_base_addr,
			lp->irq[0], lp->irq[1]);
	}
	else if (lp->data->type == TYPE_DIO24){
		// application level init device
		dev_info(dev,"(%s) at 0x%08X mapped to 0x%08X, irq=%d\n", lp->data->name,
			(unsigned int __force)lp->mem_start, (unsigned int __force)*lp->data->p_base_addr,
			lp->irq[0]);
		//pr_err(NAME_DRV "pid %i (%s) device probed ok!\n", current->pid, current->comm);
	}
	else {
		dev_info(dev,"(%s) at 0x%08X mapped to 0x%08X, irq=<none>\n", lp->data->name,
			(unsigned int __force)lp->mem_start, (unsigned int __force)*lp->data->p_base_addr);
	}
	device_init(lp->data->type);

	return 0;
error4:
	// free allocated IRQ's
	for(i = 0; i < lp->data->num_irq; ++i) {
		free_irq(lp->irq[i], lp);
	}
	// unmap physical device addresses
	iounmap(*lp->data->p_base_addr);
	*lp->data->p_base_addr = NULL;

error2:
	// release memory region
	release_mem_region(lp->mem_start, lp->mem_end - lp->mem_start + 1);
error1:
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

	if(lp) {
		if(lp->data) {
			// application level device removal
			device_remove(lp->data->type);

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
	result = register_chrdev(0,				// major device number (0..255, 0=auto)
				DIO24_DEVICE_NAME,		// device name
				&dio24_fops			// ptr to file operations structure
				);
	if (result < 0) {
		pr_err(NAME_DRV "failed registering %s character device\n", DIO24_DEVICE_NAME);
	}
	else {
		// save major device number
		dio24_major_num = result;

		// register dma24 char device
		result = register_chrdev(0,				// major device number (0..255, 0=auto)
					DMA24_DEVICE_NAME,		// device name
					&dma24_fops			// ptr to file operations structure
					);
		if (result < 0) {
			pr_err(NAME_DRV "failed registering %s character device\n", DMA24_DEVICE_NAME);
			unregister_chrdev(dio24_major_num, DIO24_DEVICE_NAME);
		}
		else {
			// save major device number
			dma24_major_num = result;
			
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
				// create user mutex
				mutex_init(&user_mutex);
				// create binary semaphore for helper
				sema_init(&helper_semaphore, 0);
				// init spin locks
				spin_lock_init(&helper_task_lock);
				spin_lock_init(&FPGA_read_lock);
				// create ringbuffer of helper tasks
				result = create_helper_tasks();
				if(result) pr_err(NAME_DRV "allocation of helper task ringbuffer failed!\n");
				else {
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
				}
			}
			else {
				pr_err(NAME_DRV "driver %s register error %d\n", DIO24_DRIVER_NAME, result);
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
	uint32_t status[HELPER_TASK_NUM_STATUS];
	// tell helper to stop
	if(helper) {
		add_helper_task(HELPER_TASK_EXIT, status, false);
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
