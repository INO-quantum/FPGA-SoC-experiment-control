////////////////////////////////////////////////////////////////////////////////////////////////////
// dma.c, communicated with phycisal DMA device
// DMA part of dma24 Linux kernel module for Arty-Z7-20 FPGA
// created November 2018 by Andi
// compiled with g++ on Ubuntu 18.04 LTS
// tested with Petalinux 2017.4
// last change 2023/06/13 by Andi
////////////////////////////////////////////////////////////////////////////////////////////////////

#include <linux/kernel.h>			// printk, pr_err, etc.
#include <linux/delay.h>			// udelay
#include <linux/time.h>				// do_gettimeofday
#include <linux/string.h>			// memset, memcpy
#include <linux/slab.h>				// kmalloc, kfree
#include <linux/uaccess.h> 			// copy_to_user, access_ok
#include <linux/random.h>			// get_random_bytes
#include <linux/jiffies.h>			// jiffies
#include "dma.h"

////////////////////////////////////////////////////////////////////////////////////////////////////
// macros
////////////////////////////////////////////////////////////////////////////////////////////////////

// name used in all pre_err statements
#define NAME			"dma24c "		// DMA functions
#define NAME_DIO		"dio24c "		// DIO functions

// timing
#define REPETITIONS		1			    // number of repetitions of test
#define SLEEP_TIME_LONG		50			// long waiting time in microseconds
#define SLEEP_TIME_SHORT	20			// short waiting time in microseconds
#define TIMEOUT_SHORT		10000		// short timeout in us (10ms)
#define TIMEOUT_LONG		100000		// long timeout in us (100ms)
#define TIMEOUT_RESET		1000000		// FPGA reset timeout in us (1s)
#define LOOPS_SHORT         (TIMEOUT_SHORT / SLEEP_TIME_LONG)
#define LOOPS_LONG          (TIMEOUT_LONG / SLEEP_TIME_LONG)
#define LOOPS_RESET         (TIMEOUT_RESET / SLEEP_TIME_LONG)

//self_test settings
//#define TEST_BUF_SIZE			0x4000		// self_test data size in bytes (distributed on random buffer sizes)
//#define ST_NUM_UNTIL_LOOP_RX	2			// number of loops after self_test start when DMA_STATUS_LOOP_RX is set
							// this defines how many RX buffers are allocated
//#define ST_NUM_BEFORE_STOP	100			// number of loops before self_test_loops when DMA_STATUS_STOP_ALL_AT_END is set


///////////////////////////////////////////////////////////////////////////////////////////////////////////////
// globals
///////////////////////////////////////////////////////////////////////////////////////////////////////////////

// IRQ status string
//char * irq_status_string = "dma24: MM2S/S2MM irq=___/___ en=___/___\n";
// offsets into irq_status_string
#define irq_status_MM2S		21
#define irq_status_S2MM		25
#define irq_enable_MM2S		32
#define irq_enable_S2MM		36

// single-linked lists of DMA buffers and descriptors
struct mem_list mem_TX = {NULL, NULL, NULL};
struct mem_list mem_RX = {NULL, NULL, NULL};
struct dsc_list dsc_TX = {NULL, NULL, NULL};
struct dsc_list dsc_RX = {NULL, NULL, NULL};

// single-linked list of unused buffers and descriptors
struct mem_info *mem_pool = NULL;

// packet buffer counter used by prepare_TX_dsc, reset by reset_TX and start_TX
static uint32_t p_count = 0;

///////////////////////////////////////////////////////////////////////////////////////////////////////////////
// function declarations
///////////////////////////////////////////////////////////////////////////////////////////////////////////////

// show DMA status registers and dsc head, tail, last_prep
//void show_status(bool is_TX);

// start TX in scatter/getter DMA mode
int start_TX_SG(void);
// start RX in scatter/getter DMA mode
int start_RX_SG(void);

// verify completed TX descriptors 
int verify_TX(bool release);
// verify completed RX descriptors 
int verify_RX(bool release);

// shows content of DMA buffer
//void show_buf(const char *title, struct mem_info *first, bool is_TX);
// show descriptor content for debugging
void show_dsc(const char *title, struct dsc_list *list, bool is_TX);

// prepares next TX descriptors
int prepare_TX_dsc(void);
// prepares next RX descriptors
int prepare_RX_dsc(void);

// releases un-completed RX dsc's and buffers
//int release_RX(void);

// init source buffer with bit pattern
//void init_source(unsigned char *buffer, uint32_t bytes, uint32_t *count);
// verify destination buffer
//uint32_t verify(unsigned char *buffer, uint32_t bytes, uint32_t *count);

// self_test irq handler TX
int self_test_TX(int err);
// self_test irq handler RX
int self_test_RX(int err);

///////////////////////////////////////////////////////////////////////////////////////////////////////////////
// functions
///////////////////////////////////////////////////////////////////////////////////////////////////////////////

const char *bits[16] = { 
	"0000", "0001", "0010", "0011", "0100", "0101", "0110", "0111",
	"1000", "1001", "1010", "1011", "1100", "1101", "1110", "1111"
};
#define GET_BITS(num32)	bits[(num32 >> 28) & 0xF], bits[(num32 >> 24) & 0xF],\
			bits[(num32 >> 20) & 0xF], bits[(num32 >> 16) & 0xF],\
			bits[(num32 >> 12) & 0xF], bits[(num32 >>  8) & 0xF],\
			bits[(num32 >>  4) & 0xF], bits[ num32        & 0xF]
// print binary number
#define PRINT_BINARY(num32)	pr_err("0b%s%s_%s%s_%s%s_%s%s", GET_BITS(num32))

// shows all desciptors in list.
// returns 0 if ok, otherwise error code
// note:
// [head-tail]              = running      dsc's, tail=NULL or tail->buffer=NULL: nothing running
// [tail->next - last_prep] = prepared     dsc's, last_prep = NULL: nothing prepared (after start_TX/RX_SG)
// [last_prep->next - head[ = not prepared dsc's (exclusive head)
char DMA_sts_bits[7] = "esISDc"; // end/start/IRQ?/error?/error?/completed
int check_dsc(struct dsc_list *list, char *title) {
	int err = 0, i;
	char DMA_sts[7] = "xxxxxx", c[4]="xxx";
	unsigned d_count = 0, b_count = 0, running = 0, prepared = 0;
	uint32_t num, d_bytes = 0, b_bytes = 0, sts;
    bool run;
	struct dsc_info *next = list->head;
	struct SG_dsc * dsc;
    if (list->tail == NULL)              run = false;
    else if (list->tail->buffer == NULL) run = false;
    else                                 run = true;
    if (title) pr_err(NAME "%s:\n", title);
	while(next) {
		if(next->virt_addr == NULL)             { err= -1; break; }                 // must be nonzero
		c[0] = (next == list->head)      ? 'h' : (list->head      ? '.' : '!');	    // head must never NULL
		c[1] = (next == list->tail)      ? 't' : (list->tail      ? '.' : '0');
		c[2] = (next == list->last_prep) ? 'l' : (list->last_prep ? '.' : '0');
		dsc = GET_ALIGNED_DSC(next->virt_addr);
		num = dsc->control & SG_MM2S_CTRL_BYTES;
		sts = (dsc->status & SG_MM2S_STATUS_COMPLETE) ? dsc->status : dsc->control;
		sts = sts >> 26;
		for(i=0;i<6;++i,sts=sts>>1) DMA_sts[i] = (sts & 1) ? DMA_sts_bits[i] : '.';
		d_bytes += num;
		if(next->buffer) {
			pr_err(NAME "dsc %2d %s %5u %s %8p %5u %2u\n", d_count, c, num, DMA_sts, next->buffer, next->buffer->bytes, next->buffer->ref_cnt);
            if (next->buffer->ref_cnt == 0)     { err = -2; break; }                // must be at least 1
			b_bytes += next->buffer->bytes;
			++b_count;
		}
		++d_count;
        if (next == list->tail) {
            if (run) {
                if (b_count != d_count)         { err = -3; break; }                // unprepared buffers between head and tail?
                else if (d_count == 0)          { err = -4; break; }                // no running descriptors?
                running = d_count;
            }
            else {
                if (b_count != 0)               { err = -5; break; }                // TODO: not sure if this can happen or not?
                else if (next->buffer)          { err = -6; break; }                // if not running then tail->buffer must be NULL
            }
        }
        else if (next == list->last_prep) {
            prepared = d_count - running;
            if (prepared == 0)                  { err = -7; break; }                // last_prep == tail? if nothing prepared last_prep should be NULL.
        }
		next = next->next;
		if(next == list->head) break;
	}
    if (err) pr_err(NAME "check_dsc: dsc's/bytes %u/%u error %d!\n", d_count, d_bytes, err);
    else     pr_err(NAME "check_dsc: dsc's/bytes %u/%u ok\n", d_count, d_bytes);
    pr_err(NAME "           run/prep/not prep  %u/%u/%u\n", running, prepared, d_count - running - prepared);
	pr_err(NAME "           bufs/bytes %u/%u\n",      b_count, b_bytes);
	return err;
}

// check validity of descriptors in list starting at head and ending at tail (inclusive)
// head = first descriptor in list.
// tail = last descriptor in list.
// is_TX = true if descriptor is TX dsc, otherwise RX dsc.
// returns 0 if ok, otherwise error code
// start and end bits are ignored
// this is called from start_TX/RX_SG to check if prepared dsc's are valid
int check_sg_dsc(struct dsc_info *head, struct dsc_info *tail, bool is_TX) { 
	int err = 0, i = 0;
	uint32_t num, count = 0;
	struct dsc_info *act = head;
	struct SG_dsc * dsc = NULL;

	if((head == NULL) || (tail == NULL)) err = -1;
	else {
		//pr_err(NAME "check_sg_dsc: first=%p, next=%p, last=%p\n", list.first, list.next, list.last);
		while(true) {
			//pr_err(NAME "%d check_sg_dsc: this   %p\n", i, act);
			//pr_err(NAME "%d check_sg_dsc: dsc    %p\n", i, act->virt_addr);
			//pr_err(NAME "%d check_sg_dsc: next   %p\n", i, act->next);
			//pr_err(NAME "%d check_sg_dsc: buf    %p\n", i, act->buffer);
			if(act->buffer == NULL) { err = -10; break; } // buffer must not be NULL
			dsc = GET_ALIGNED_DSC(act->virt_addr); // virtual address!
			if(!dsc) { err = -11; break; }
			if((!IS_ALIGNED_DSC(dsc)) || (!IS_ALIGNED_DSC(GET_ALIGNED_PHYS_DSC(act->phys_addr)))) 
			{ err = -12; break; }
			if(dsc->address_low != GET_ALIGNED_PHYS_BUFFER(act->buffer->phys_addr)) // physical address!
			{ err = -13; break; }
			//pr_err(NAME "%d check_sg_dsc: buffer %p\n", i, dsc->address_low);
			if((dsc->address_low != GET_ALIGNED_PHYS_BUFFER(act->buffer->phys_addr)) || 
				(!IS_ALIGNED_BUFFER(dsc->address_low))) { err = -21; break; }	// wrong buffer!
			if(dsc->address_high != 0) { err = -23; break; }
			num = dsc->control & SG_MM2S_CTRL_BYTES;
			//pr_err(NAME "%d check_sg_dsc: %u bytes\n", i, num);
			/*if(dsc->control != (BUF_SIZE | 
					((i == 0) ? SG_MM2S_CTRL_START : 0) |
					(((i+1) < SG_NUM) ? 0: SG_MM2S_CTRL_END)
					)) { err = -14; break; }*/
			if(num > DMA_BUF_SIZE) { err = -31; break; }
			count += num;

			// next must never be NULL (ring-buffer)
			if(act->next == NULL) { err = -32; break; }

			// check next dsc low address
			if(dsc->next_low != GET_ALIGNED_PHYS_DSC(act->next->phys_addr)) // physical address!
			{ err = -33; break; }
			// check next dsc high address (must be always 0)
			if(dsc->next_high != 0) { err = -34; break; } 

			// check buffer reference counter
			if(is_TX && (act->buffer->ref_cnt == 0)) { err = -35; break; } // must be >0
			else if((!is_TX) && (act->buffer->ref_cnt != 1)) { err = -36; break; } // must be 1

			/*if(act == head) {
				//pr_err(NAME "%d check_sg_dsc: this is first\n", i);
				if(is_TX) { // first must have start bit set
					if((dsc->control & SG_MM2S_CTRL_START) != SG_MM2S_CTRL_START) { err = -41; break; }
				}
			}
			else {
				// normal descriptor cannot have start bit set
				if((dsc->control & SG_MM2S_CTRL_START) != 0) { err = -42; break; }
			}*/

			++i;

			if(act == tail) {
				//pr_err(NAME "%d check_sg_dsc: this is last\n", i);
				// last must have end bit set
				//if((dsc->control & SG_MM2S_CTRL_END) != SG_MM2S_CTRL_END) { err = -61; break; }
				
				// next dsc must point to first dsc
				//if(dsc->next_low != GET_ALIGNED_PHYS_DSC(first->phys_addr)) // physical address!
				// check next dsc
				// stop if last found
				break;
			}
			/*else {
				// normal descriptor cannot have end bit set
				if((dsc->control & SG_MM2S_CTRL_END) != 0) { err = -71; break; }
			}
*/
			//print_sg_dsc(act);

			act = act->next;

			if((act == head) || (act == NULL) || (i > (is_TX ? DSC_TX_NUM : DSC_RX_NUM))) { err = -99; break; } // end of ring-buffer reached without tail found!
		}
	}
	if(err) pr_err(NAME "check_sg_dsc: #%d dsc validity check error %d.\n", i, err);
	//else pr_err(NAME "check_sg_dsc: %d dsc's validity check ok (%u bytes).\n", i, count);
	return err;
}


// get new DMA buffer from memory_pool or allocates it
// returns NULL on error
// ATTENTION: must be called with user_mutex locked!
inline struct mem_info *get_mem(unsigned dbg_index) {
	struct mem_info *mem;
	if(mem_pool == NULL) {
		// allocate memory info
		mem = MALLOC_MEM_INFO;
		if(mem != NULL) {
			// allocate DMA buffer (virtual and physical address)
			MALLOC_BUFFER(mem->virt_addr, mem->phys_addr);
			if(mem->virt_addr == NULL) {
				FREE_MEM_INFO(mem);
				mem = NULL;
			}
			else ++debug_DMA_count[dbg_index];
		}
	}
	else {	// get memory info from pool
		mem = mem_pool;
		mem_pool = mem_pool->next;
		--debug_DMA_count[DBG_BUF_POOL];
		// DMA buffer must be already allocated. return NULL if this is not the case!
		if(mem->virt_addr == NULL) {
			FREE_MEM_INFO(mem);
			mem = NULL;
		}
		else ++debug_DMA_count[dbg_index];
	}
	// init memory
	if(mem) {
		mem->next = NULL;
		mem->bytes = 0L;
		mem->ref_cnt = 0;
	}
	return mem;
}

// free allocated DMA buffer and descriptors starting from 'first' until end of list.
// the list can be terminated with next == NULL or be a circular buffer next = first.
// the _no_pool version does not insert them back into pool but frees memory
// ATTENTION: must be called with user_mutex locked!
// last->next will be overwritten!
inline void free_mem(struct mem_info *first, unsigned dbg_index) { 
	unsigned count = 0;
	struct mem_info *test = first, *last = NULL;
	if (first) {
		while(true) { 	// find last entry
			if(test->ref_cnt != 0) { pr_err("\n*** "NAME "free_mem: ref_cnt != 0! ***\n\n"); return; } // error! and memory leak!
			++count;
			last = test;
			test = test->next;
			if ((test == NULL) || (test == first)) { // end of list: prepend to mem_pool
				last->next = mem_pool;
				mem_pool = first; 
				debug_DMA_count[dbg_index] -= count;
				debug_DMA_count[DBG_BUF_POOL] += count;
				break;
			}
		}
	}
}
inline void free_mem_no_pool(struct mem_info *first, unsigned dbg_index) {
	unsigned count = 0;
	struct mem_info *next = first, *tmp;
	if(first) {
		do {
			tmp = next->next;
			if(next->ref_cnt != 0) { pr_err("\n *** " NAME "free_mem (np) ref_cnt != 0! ***\n\n"); return; }
			if(next->virt_addr != NULL) FREE_BUFFER(next->virt_addr, next->phys_addr); 
			FREE_MEM_INFO(next);
			++count;
			next = tmp;
		} while ((next != NULL) && (next != first));
		debug_DMA_count[dbg_index] -= count;
	}
}

// for debugging count entries of TX, RX and testing lists
unsigned debug_DMA_count[DBG_NUM] = {0,0,0,0,0,0};
int free_dsc_no_pool(struct dsc_info *head, unsigned dbg_index) {
	int err = 0, count = 0; 
	struct dsc_info *act = head, *next;
	if(head) {
		do {
			if(act->buffer != NULL) { pr_err("\n *** " NAME "free_dsc (np) buffer != NULL! ***\n\n"); return -1; }
			next = act->next;
			if(act->virt_addr != NULL) FREE_DSC(act->virt_addr, act->phys_addr);
			FREE_DSC_INFO(act);
			++count;
			act = next;
		} while((act != NULL) && (act != head));
	}
	if(count != debug_DMA_count[dbg_index]) { pr_err("\n *** " NAME "free_dsc (np) count %u != %u! ***\n\n", count, debug_DMA_count[dbg_index]); if(!err) err = -50; }
	debug_DMA_count[dbg_index] -= count;
	return err;
}

// shows s_num samples in TX/RX buffer starting at s_start sample
void show_data(struct mem_info *mem, uint32_t s_start, uint32_t s_num) {
	uint32_t i, j = mem->bytes / DIO_BYTES_PER_SAMPLE, *p = GET_ALIGNED_BUFFER(mem->virt_addr);
	s_num += s_start;
	for (i = 0; i < s_num; ++i, --j, p += (DIO_BYTES_PER_SAMPLE/4)) {
		if(j == 0) {
			mem = mem->next;
			if(mem == NULL) return;
			if(mem->bytes == 0) continue;
			j = mem->bytes / DIO_BYTES_PER_SAMPLE;
			p = GET_ALIGNED_BUFFER(mem->virt_addr);
		}
		if(i >= s_start) {
#if DIO_BYTES_PER_SAMPLE == 8
			pr_err("%03d: %8u us %08x\n", i, *(p), *(p+1));
#elif DIO_BYTES_PER_SAMPLE == 12
			pr_err("%03d: %8u us %08x %08x\n", i, *(p), *(p+1), *(p+2));
#endif
		}
	}

}

// called by check_mem to check correct increment of time in data
// returns -1 if ok, otherwise sample index with error
int check_data(uint32_t *data, uint32_t bytes, uint32_t *t_old) {
	int i;
	bytes = (bytes / DIO_BYTES_PER_SAMPLE);
	for(i = 0; i < bytes; data += (DIO_BYTES_PER_SAMPLE/4), ++i) {
		if ((*t_old != 0xffffffff) && (*data <= *t_old)) return i;
		*t_old = *data;
	}
	return -1;
}

// check validity of DMA buffers in list
// returns 0 if ok, otherwise error code
// notes: 
// - if test_data is true checks that time is incremental and
//   if no other error and buffer size is not multiple of DMA_BUF_MULT returns ERROR_NO_BUF_MULT
//   this way function can check for other errors and caller can decide what to do
// - mem_RX is a ring buffer while mem_TX is not! 
// - mem_RX.last is not maintained outside from prepare_RX_buffers and is not checked here.
int check_mem(struct mem_list *list, bool show, bool test_data) {
	int count = 0, err = 0, err_alt = 0, locked = 0;
	bool next_found = false;
	unsigned int bytes = 0;
	uint32_t t_old = 0xffffffff, *p;
	struct mem_info *first = list->first;
	if (show) {
        if (list->first == NULL) pr_err(NAME "check_mem: empty\n");
        else                     pr_err(NAME "check_mem: f/n/l %p/%p/%p\n", list->first, list->next, list->last);
    }
	while(first) {
		if(show) pr_err("%s%03d: %p %8u %2u\n", NAME, count, first, first->bytes, first->ref_cnt);
		// first->ref_cnt we cannot check here
		if((first->virt_addr == 0)||(first->phys_addr == 0)) { err = -101; break; } 
		if(first->bytes > DMA_BUF_SIZE) { err = -102; break; }
		if(test_data) {
			if(first->bytes == 0) { err = -103; break; } // we cannot check data when there is no data!
			if(first->bytes % DMA_BUF_MULT) err_alt = -ERROR_NO_BUF_MULT; // append_TX not yet called?
			err = check_data(GET_ALIGNED_BUFFER(first->virt_addr),first->bytes,&t_old);
			if (err >= 0) {
				p = GET_ALIGNED_BUFFER(first->virt_addr) + (err*DIO_BYTES_PER_SAMPLE/4); // buffer offset at error
				err = bytes/DIO_BYTES_PER_SAMPLE + err; // total sample offset at error
				pr_err("%s%03d: %p %8u %2u     error time! # %d t_old=%u us\n", NAME, count, first, first->bytes, first->ref_cnt, err, t_old);
				if (err > 1) {
					if(err >= 10) show_data(list->first, err - 10, 10);
					else show_data(list->first, 0, err - 1);
				}
#if DIO_BYTES_PER_SAMPLE == 8
				pr_err("%03d: %8u us %08x < error time!\n", err, *(p), *(p+1));
#elif DIO_BYTES_PER_SAMPLE == 12
				pr_err("%03d: %8u us %08x %08x < error time!\n", err, *(p), *(p+1), *(p+2));
#endif
				show_data(list->first, err + 1, (err >= 10) ? 10 : 20-err);
				err = -104; 
				break;
			}
			else err = 0;
		}
		if(first->next == NULL) { // check mem_TX.last
			if((list != &mem_TX) || (list->last != first)) { err = -105; break; }
		}
		else if (first->next == list->first) { // check mem_RX.last
			if((list != &mem_RX) /*|| (list->last != first)*/) { err = -106; break; }
		}
		if(list->next == first) { // next found
			if(next_found) { err = -107; break;} // loop?
			else next_found = true;
		}
        if (first->ref_cnt > 0) ++locked;
		bytes += first->bytes;
		first = first->next;
		++count;
		if(first == list->first) { 		// ring-buffer closed
			if (list != &mem_RX ) err = -108; 
			break; 
		}
	}
	if(list->first == NULL) {
		if(list->next != NULL) err = -109;
		if(list->last != NULL) err = -110;
	}
	if((!err) && (list->next != NULL) && (!next_found)) err = -111; // next is not in list!
	if(!err) err = err_alt;
	if(err) pr_err("%scheck_mem: locked/tot/bytes %d/%d/%u error %d!\n", NAME, locked, count, bytes, err);
	else if (show) pr_err("%scheck_mem: locked/tot/bytes %d/%d/%u ok\n", NAME, locked, count, bytes);
	return err;
}

// return FPGA status string
char *FPGA_status_str(uint32_t status) {
	static char st_run[]   = "running";
	static char st_err[]   = "error";
	static char st_end[]   = "end";
	static char st_stop[]  = "stopped";
	if (status & DIO_STATUS_RUN) return st_run;
	if (status & DIO_STATUS_END) return st_end;
	if (status & DIO_STATUS_ERROR) return st_err;
	return st_stop;
}

#define CHECK_BT_TOT(st)	((st.TX_bt_tot == st.RX_bt_tot) && (st.RX_bt_tot == (st.bt_tot*st.reps_set)))

// updates status info and if st != NULL saves to st
// if force=True resets status and forces reading of FPGA registers
// if show=True prints status on console
void update_status(struct FPGA_status *st, bool show, bool force) {
    static bool first_time = true;
    static char board_c0[] = "Cora-Z7-07S";
    static char board_c1[] = "Cora-Z7-10";
    static char board_a1[] = "Arty-Z7-10";
    static char board_a2[] = "Arty-Z7-20";
    static char board_u[]  = "unknown";
	//int i;
	int32_t mT = 0;
    uint32_t tmp;
    char *ptr;
    if (force) { // force read FPGA registers
        memset(&status, 0, sizeof(struct FPGA_status));
        // --- FPGA section ---
        // control
        status.ctrl_FPGA                    = READ_DIO_REGISTER(DIO_REG_CTRL);
        status.ctrl_in                      = READ_DIO_REGISTER(DIO_REG_CTRL_IN);
        status.ctrl_out                     = READ_DIO_REGISTER(DIO_REG_CTRL_OUT);
        status.set_samples                  = READ_DIO_REGISTER(DIO_REG_NUM_SAMPLES);
        status.clk_div                      = READ_DIO_REGISTER(DIO_REG_CLK_DIV);
        status.strb_delay                   = READ_DIO_REGISTER(DIO_REG_STRB_DELAY);
        status.sync_delay                   = READ_DIO_REGISTER(DIO_REG_SYNC_DELAY);
        status.sync_phase                   = READ_DIO_REGISTER(DIO_REG_SYNC_PHASE);
        // status register
        status.status_FPGA.status           = READ_DIO_REGISTER(DIO_REG_STATUS);
        status.status_FPGA.board_time       = READ_DIO_REGISTER(DIO_REG_BOARD_TIME);
        status.status_FPGA.board_samples    = READ_DIO_REGISTER(DIO_REG_BOARD_SAMPLES);
        status.board_time_ext               = READ_DIO_REGISTER(DIO_REG_BOARD_TIME_EXT);
        status.board_samples_ext            = READ_DIO_REGISTER(DIO_REG_BOARD_SAMPLES_EXT);
        status.sync_time                    = READ_DIO_REGISTER(DIO_REG_SYNC_TIME);
        status.status_info.version          = READ_DIO_REGISTER(DIO_REG_VERSION);
        status.status_info.info             = READ_DIO_REGISTER(DIO_REG_INFO);
        // XDC module board temperature
        status.FPGA_temp = READ_XADC_REGISTER(XADC_TEMP_ACT);
        if (first_time) { // first temperature read is always wrong. so read 2x
            first_time = false;
            status.FPGA_temp = READ_XADC_REGISTER(XADC_TEMP_ACT);
        }
    }
	if(st) memcpy(st,&status,sizeof(struct FPGA_status));
	if(show) {
		mT = GET_mT(status.FPGA_temp);
		pr_err(NAME "DMA & FPGA status:\n");
		pr_err(NAME "                    TX       RX     FPGA\n");
		pr_err(NAME "ctrl       0x %8x        - %08x\n",  status.ctrl_DMA, status.ctrl_FPGA);
		pr_err(NAME "in/out     0x        - %08x %08x\n",                   status.ctrl_in,  status.ctrl_out);
        pr_err(NAME "in/out/bus ps %8u %8u %8u\n",        status.period_in, status.period_out, status.period_bus);
        pr_err(NAME "strb/clk   0x        - %8x %8x\n",                       status.strb_delay, status.clk_div);
		pr_err(NAME "sync w/ph  0x %8x %8x\n",            status.sync_delay, status.sync_phase);
		pr_err(NAME "status     0x %8x %8x %8x (%s)\n", 	status.status_TX, status.status_RX, status.status_FPGA.status, FPGA_status_str(status.status_FPGA.status));
        pr_err(NAME "board #/t            - %8u %8d us\n",                  status.status_FPGA.board_samples, status.status_FPGA.board_time);
        pr_err(NAME "board #/t (ext)      - %8u %8d us\n",                  status.board_samples_ext, status.board_time_ext);
        //pr_err(NAME "board cyc            -        - %8d us\n",             status.board_cycles);
		pr_err(NAME "sync time            -        - %8d\n",                status.sync_time);
		pr_err(NAME "temperature          -        - %4d.%03u deg.C\n",                       mT/1000, mT % 1000);
        pr_err(NAME "phase ext/det        - %8d %8d steps\n",               status.phase_ext, status.phase_det);
		pr_err(NAME "error         %8d %8d %8d\n",        status.err_TX,    status.err_RX,    status.err_FPGA);
		pr_err(NAME "IRQ's         %8u %8u %8u\n",        status.irq_TX,    status.irq_RX,    status.irq_FPGA);
		pr_err(NAME "IRQ's mrg     %8u\n",                status.irq_num);
		pr_err(NAME "trans bytes   %8u %8u %8u (%s)\n",   status.TX_bt_tot, status.RX_bt_tot, status.bt_tot, CHECK_BT_TOT(status) ? "ok" : "error" );
		pr_err(NAME "TX p/a/c      %8u %8u %8u\n",        status.dsc_TX_p,  status.dsc_TX_a,  status.dsc_TX_c);
		pr_err(NAME "RX p/a/c      %8u %8u %8u\n",        status.dsc_RX_p,  status.dsc_RX_a,  status.dsc_RX_c);
		pr_err(NAME "rd m/a/d      %8u %8u %8u\n",       	status.RD_bt_max, status.RD_bt_act, status.RD_bt_drop);
		pr_err(NAME "reps/act      %8u %8u\n",       	status.reps_set,  status.reps_act);
		pr_err(NAME "timeout       %8u\n",  		status.timeout);
#if DIO_BYTES_PER_SAMPLE == 8
		pr_err(NAME "RX last    0x %08x %08x          (%u us)\n",	status.last_sample.data32[0], status.last_sample.data32[1], status.last_sample.data32[0]);
#elif DIO_BYTES_PER_SAMPLE == 12
		pr_err(NAME "RX last    0x %08x %08x %08x (%u us)\n",	status.last_sample.data32[0], status.last_sample.data32[1], status.last_sample.data32[2], status.last_sample.data32[0]);
#endif		
		//pr_err(NAME "bt/cyc/smpl   %8u %8u %8u (mult. of %u)\n", DIO_BYTES_PER_SAMPLE, status.set_samples, status.set_cycles, DMA_BUF_MULT/DIO_BYTES_PER_SAMPLE);
        pr_err(NAME "bt/smpl   %8u        - %8u (mult. of %u)\n", DIO_BYTES_PER_SAMPLE, status.set_samples, DMA_BUF_MULT/DIO_BYTES_PER_SAMPLE);
        tmp = status.status_info.version;       // board version {brd_vers_major[7:0],brd_vers_minor[7:0],year[6:0],month[3:0],day[4:0]}
		pr_err(NAME "version    0x        -        - %08x (%02u.%02u-%04u/%02u/%02u)\n", tmp, (tmp>>24)&0xff, (tmp>>16)&0xff, ((tmp>>9)&0x7f)+2000, (tmp>>5)&0xf, tmp&0x1f);
        tmp = status.status_info.info;
        switch (tmp & 0xff) {
            case 0xc0: ptr = board_c0; break;
            case 0xc1: ptr = board_c1; break;
            case 0xa1: ptr = board_a1; break;
            case 0xa2: ptr = board_a2; break;
            default:   ptr = board_u;
        }
		pr_err(NAME "info       0x        -        - %08x (%s)\n", tmp, ptr);
/*
		pr_err(NAME "debug_cnt     %8u\n",  		status.debug_count);
		for(i=0; i<FPGA_STATUS_NUM_DEBUG; ++i) {
			if ((i % DBG_HIST) == 0) pr_err(NAME "debug %2d   0x %8x", i, status.debug[i]);
			else if ((i % DBG_HIST) == (DBG_HIST-1)) pr_err(" %8x\n", status.debug[i]);
			else pr_err(" %8x", status.debug[i]);
		}
*/
	}
}

// set dio24 control register and return actual value
// for settable configuration values see DIO_CTRL_SETTABLE in dma24.h
// note: FPGA must be stopped!
int set_config(uint32_t *config) {
	int err = 0;
	uint32_t ctrl = status.ctrl_FPGA;
	
	if(ctrl & DIO_CTRL_RUN) {
		pr_err(NAME "set FPGA config: FPGA must be stopped! (error)\n");
		err = -1;
	}
	else {
		if((*config & (~DIO_CTRL_USER)) != 0) {
			pr_err(NAME "set FPGA config: wrong bits! %u (error)\n", *config);
			err = -2;
		}
		else {					
			if(ctrl != READ_DIO_REGISTER(DIO_REG_CTRL)) {
				pr_err(NAME "set FPGA config: CTRL %x != register %x (error)\n", ctrl, READ_DIO_REGISTER(DIO_REG_CTRL));
				err = -3;
			}
			else
			{
				// save settings
				status.ctrl_FPGA = (status.ctrl_FPGA & ~DIO_CTRL_USER) | (*config & DIO_CTRL_USER);
				WRITE_DIO_REGISTER(DIO_REG_CTRL, status.ctrl_FPGA);
				// ensure configuration is written
				wmb();
				// return new status
				*config = status.ctrl_FPGA;
				//pr_err(NAME "set_config %x, old = %x (ok)\n", status.ctrl_FPGA, ctrl);
			}
		}
	}
	return err;
}

// returns num_dsc allocated descriptors or NULL on error
// notes: 
// - start/end bits are not set since have to be set by prepare_TX/RX_dsc.
// - completion bit is also not set.
// - dsc is automatically closed as ringbuffer (last->next=first)
struct dsc_info *allocate_dsc(int num_dsc, unsigned index) {
	int i;
	uint32_t count = 0;
	struct dsc_info *first, *last = NULL, *prev = NULL;
	struct SG_dsc *dsc;

	// allocate dsc info
	first = MALLOC_DSC_INFO;
	if(first == NULL) pr_err(NAME "allocate_dsc: out of mem! (1)\n");
	else {
		// init with zeros
		memset(first, 0, sizeof(struct dsc_info));

		// allocate dsc (virtual and physical address)
		MALLOC_DSC(first->virt_addr, first->phys_addr);
		if(first->virt_addr == NULL) {
			pr_err(NAME "allocate_dsc: out of mem! (2)\n");
			FREE_DSC_INFO(first);
			first = NULL;
		}
		else {
			// for debugging count entries
			++count;

			// init first descriptor with zeros.
			prev = last = first;
			dsc = GET_ALIGNED_DSC(last->virt_addr);	// aligned virtual descriptor
			memset(dsc, 0, sizeof(struct SG_dsc));
			
			// loop over additional descriptors
			for(i = 1; i < num_dsc; ++i) {
				// allocate memory info
				last = last->next = MALLOC_DSC_INFO;
				if(last == NULL) { pr_err(NAME "allocate_dsc: out of mem! (3)\n"); break; }
				
				// init descriptor with zeros
				memset(last, 0, sizeof(struct dsc_info));

				// allocate dsc (virtual and physical address)
				MALLOC_DSC(last->virt_addr, last->phys_addr);
				if(last->virt_addr == NULL) {
					pr_err(NAME "allocate_dsc: out of mem! (4)\n");
					FREE_DSC_INFO(last);
					prev->next = last = NULL;
					break;
				}

				// for debugging count entries
				++count;

				// in previous descriptor save aligned physical address
				dsc->next_low = GET_ALIGNED_PHYS_DSC(last->phys_addr);

				// init descriptor with zeros
				dsc = GET_ALIGNED_DSC(last->virt_addr);	// aligned virtual descriptor
				// dsc->next is set in next loop
				// dsc_address_low must be DATA_WIDTH_ALIGN aligned
				// dsc_control is set to buffer size and might have start or end bit set (later).
				// dsc_status gets after successful completion transmitted buffer size and completion bit set.
				memset(dsc, 0, sizeof(struct SG_dsc));

				// save previous descriptor (only needed in error case)
				prev = last;
			} // next loop
		}
	}

	// update debug counter
	debug_DMA_count[index] += count;

	// if all ok return list, else delete list
	if(first != NULL) {
		if (last != NULL) { 
			// set last->next to first entry to close ring-buffer. same for descriptor.
			last->next = first;
			dsc->next_low = GET_ALIGNED_PHYS_DSC(first->phys_addr);
		}
		else {
			pr_err(NAME "allocate_dsc: out of mem!\n");
			free_dsc_no_pool(first, index);
			first = NULL;
		}
	}
	else pr_err(NAME "allocate_dsc: out of mem!\n");
	return first;
}


//inline void irq_enable(void) {
//	uint32_t old;
	//if(dma24_reg_base != NULL) {
	//	pr_err(NAME "irq enable: (not implemented)\n");
	//}
	/*if(dio24_reg_base != NULL) {
		old = READ_DIO_REGISTER(DIO_REG_CTRL);
		WRITE_DIO_REGISTER(DIO_REG_CTRL, old | DIO_CTRL_IRQ_FPGA); // | DIO_CTRL_IRQ_TX | DIO_CTRL_IRQ_RX);
	}*/
//}

//inline void irq_disable(void) {
//	uint32_t old;
	//if(dma24_reg_base != NULL) {
	//	pr_err(NAME "irq disable: (not implemented)\n");
	//}
	/*if(dio24_reg_base != NULL) {
		old = READ_DIO_REGISTER(DIO_REG_CTRL);
		WRITE_DIO_REGISTER(DIO_REG_CTRL, old & (~(DIO_CTRL_IRQ_FPGA | DIO_CTRL_IRQ_TX | DIO_CTRL_IRQ_RX)));
	}*/
//}

// save TX and RX and FPGA status register and acknowledge all interrups
// call within IRQ, status gets TX_status, RX_status
// notes: 
// - RESET_REGISTER_BIT does not work, have to use SET_REGISTER_BIT or WRITE_DMA_REGISTER instead!
// - this is NOT called within user_mutex since might lock out itself! locking must be done from helper_thread.
inline void irq_ack_TX(uint32_t status_irq[HELPER_TASK_NUM_STATUS_IRQ]) {
	//static TIME_DATA t_IRQ;

	// count irq's
	++status.irq_TX;

	// save time of IRQ
	// todo: save directly into status
	//GET_TIME(t_IRQ);
	//status_irq[HELPER_STATUS_SEC]=GET_SEC(t_IRQ);
	//status_irq[HELPER_STATUS_USEC]=GET_USEC(t_IRQ);

	//rmb(); // not sure if needed?
	
	// save register content
	status_irq[HELPER_STATUS_TX] = READ_DMA_REGISTER(DMA_REG_MM2S_STATUS);
	status_irq[HELPER_STATUS_RX] = 0L;

	// writing to these registers reset bits
	if(status_irq[HELPER_STATUS_TX] & MM2S_STATUS_IRQS) WRITE_DMA_REGISTER(DMA_REG_MM2S_STATUS, status_irq[HELPER_STATUS_TX]);

	// memory barrier to ensure data is written!
	// todo: not sure if needed inside irq routine? (I actually think its not needed)
	//wmb();
}
inline void irq_ack_RX(uint32_t status_irq[HELPER_TASK_NUM_STATUS_IRQ]) {
	//static TIME_DATA t_IRQ;

	// count irq's
	++status.irq_RX;

	// save time of IRQ
	// todo: save directly into status
	//GET_TIME(t_IRQ);
	//status_irq[HELPER_STATUS_SEC]=GET_SEC(t_IRQ);
	//status_irq[HELPER_STATUS_USEC]=GET_USEC(t_IRQ);

	//rmb(); // not sure if needed?
	
	// save register content
	status_irq[HELPER_STATUS_TX] = 0L;
	status_irq[HELPER_STATUS_RX] = READ_DMA_REGISTER(DMA_REG_S2MM_STATUS);

	// writing to these registers reset bits
	if(status_irq[HELPER_STATUS_RX] & S2MM_STATUS_IRQS) WRITE_DMA_REGISTER(DMA_REG_S2MM_STATUS, status_irq[HELPER_STATUS_RX]);

	// memory barrier to ensure data is written!
	// todo: not sure if needed inside irq routine? (I actually think its not needed)
	//wmb();
}
/*inline void irq_ack_FPGA(uint32_t status_irq[HELPER_TASK_NUM_STATUS]) {
	//int i = 0;
	
	// count irq's
	++status.irq_FPGA;

	// save register content
	status_irq[HELPER_STATUS_TX] = status_irq[HELPER_STATUS_RX] = 0L;
	status.status_FPGA.status = status_irq[HELPER_STATUS_FPGA] = READ_DIO_REGISTER(DIO_REG_STATUS);

	// reset corresponding irq enable bit(s) which also resets irq(s)
	WRITE_DIO_REGISTER(DIO_REG_CTRL, status.ctrl_FPGA & (~(status.status_FPGA.status & DIO_STATUS_IRQ_ALL)));

	// enable irq again if there is no error
	if (status.status_FPGA.status & DIO_STATUS_IRQ_FPGA_ERR) { 
		status.ctrl_FPGA &= (~(status.status_FPGA.status & DIO_STATUS_IRQ_ALL));
		//pr_err(NAME "irq_FPGA ctrl/status = 0x %x / %x error!\n", status.ctrl_FPGA,status.status_FPGA.status);
	}
	else { 
		WRITE_DIO_REGISTER(DIO_REG_CTRL, status.ctrl_FPGA);
		//pr_err(NAME "irq_FPGA ctrl/status = 0x %x / %x ok\n", status.ctrl_FPGA,status.status_FPGA.status);
	}
}*/

/* irq_FPGA handler executed by helper thread with user_mutex locked
// FPGA produces irq only when in end state, on auto-restart, on error or on update
// for performance we limit output to every 5 seconds except end and error
inline void irq_hdl_FPGA(uint32_t status_irq[HELPER_TASK_NUM_STATUS]) {
	if (status.status_FPGA.status & (DIO_STATUS_ERROR|DIO_STATUS_END)) {
		if (status.status_FPGA.status & DIO_STATUS_ERROR) pr_err(NAME "%u irq_FPGA ctrl/status = 0x%x/%x (error!)\n", irq_cnt + 1, status.ctrl_FPGA, status.status_FPGA.status);
		else pr_err(NAME "%u irq_FPGA ctrl/status = 0x%x/%x (end)\n", irq_cnt + 1, status.ctrl_FPGA, status.status_FPGA.status);
		jf_old = jiffies;
		irq_cnt = 0;
	}
	else {	// auto-restart or update timer
		if((jiffies - jf_old) > (5*HZ)) {
			if (status.status_FPGA.status & DIO_STATUS_IRQ_FPGA_RESTART) pr_err(NAME "%u irq_FPGA ctrl/status = 0x%x/%x (auto-restart)\n", irq_cnt + 1, status.ctrl_FPGA, status.status_FPGA.status);
			else pr_err(NAME "%u irq_FPGA ctrl/status = 0x%x/%x (update)\n", irq_cnt + 1, status.ctrl_FPGA, status.status_FPGA.status);
			jf_old = jiffies;
			irq_cnt = 0;
		}
		else ++irq_cnt; // in next message we display # of new irqs
	}
}*/

// handle irq_TX/RX by helper thread with locked user_mutex
// status_irq is filled by irq_ack (see there)
// ATTENTION: must be called with user_mutex locked!
// updates globals status.err_TX and err_RX with last errors
// no error = 0, warnings > 0, errors < 0
// calls reset_all if error < 0
// NOTE: this is the main and busiest function of DMA part of driver!
//       if you understand it and its functions you understand most of it.
//       see also device_write, device_read and device_ioctl in driver.c
#define ST_NONE		0
#define ST_RESTARTED	1
#define ST_FINISHED	2	
inline void irq_hdl_DMA(uint32_t status_irq[HELPER_TASK_NUM_STATUS]) {
	//uint32_t status_TX, status_RX;
	int err_TX = 0, err_RX = 0;
	//TIME_DATA t_IRQ;
  	int st_TX = ST_NONE, st_RX = ST_NONE; 
	// effective samples to be done: 0 = infinite, otherwise repetitions * samples
	uint32_t bytes = status.bt_tot * status.reps_set;

	rmb(); // ensure read cache is updated such that verify finds all completed dsc's

	// read latest status and combine with status at irq
	// this ensures that we do not loose completions which occur between reading irq status and acknowlede of irq
	// but it might cause that we get irq's where nothing needs to be done (get warnings, no error).
	status.status_TX = status_irq[HELPER_STATUS_TX] | READ_DMA_REGISTER(DMA_REG_MM2S_STATUS);
	status.status_RX = status_irq[HELPER_STATUS_RX] | READ_DMA_REGISTER(DMA_REG_S2MM_STATUS);
	status.irq_num = status_irq[HELPER_STATUS_NUM_IRQ];

	// check RX/TX completion and restart as fast as possible
	if(status.status_RX & S2MM_STATUS_IRQ_COMPLETE) {

		if (++status.debug_count >= DBG_HIST) status.debug_count = 0;
		status.debug[DBG_OFF_RX_IRQ     + status.debug_count] = status.status_RX;	
		status.debug[DBG_OFF_RX_VERIFY  + status.debug_count] ^= 0xffffffff;
		status.debug[DBG_OFF_RX_START   + status.debug_count] ^= 0xffffffff;
		status.debug[DBG_OFF_RX_PREPARE + status.debug_count] ^= 0xffffffff;

		//SET_TIME(t_IRQ, status_irq[HELPER_STATUS_SEC], status_irq[HELPER_STATUS_USEC]);

		// verify_RX checks completion and sets dsc_RX.next to next not completed dsc.
		// this stops RX if status.set_RX reached
		err_RX = verify_RX(false);
		if(err_RX >= 0) {
			if ((bytes > 0L) && (status.RX_bt_tot >= bytes)) st_RX = ST_FINISHED;
			else if (!(status.ctrl_DMA & DMA_CTRL_CYCLIC_RX)) {
				// if DMA enabled:
				// start [dsc_RX.tail->next..dsc_RX.last_prepared] if dsc_RX.last_prep != NULL
				// sets active descriptors [dsc_RX.head..tail] and dsc_RX.last_prep = NULL
				err_RX = start_RX_SG();
				if(err_RX >= 0) st_RX = ST_RESTARTED;
			}
		}
	} 
	if(status.status_TX & MM2S_STATUS_IRQ_COMPLETE) {
		//SET_TIME(t_IRQ, status_irq[HELPER_STATUS_SEC], status_irq[HELPER_STATUS_USEC]);

		// verify_TX checks completion and sets dsc_TX.next to next not completed dsc.
		// stops TX if status.set_TX reached
		err_TX = verify_TX(false);

		if(err_TX >= 0) {
			if ((bytes > 0L) && (status.TX_bt_tot >= bytes)) st_TX = ST_FINISHED;
			else {
				// if DMA enabled:
				// start [dsc_TX.tail->next..dsc_TX.last_prepared] if last_prep != NULL
				// sets active descriptors [dsc_TX.head..tail] and dsc_TX.last_prep = NULL
				err_TX = start_TX_SG();
				if(err_TX >= 0)	st_TX = ST_RESTARTED;
			}
			// start FPGA when TX wrote DIO_FPGA_START_BT bytes or all data
			if ((status.ctrl_DMA & DMA_CTRL_ENABLE_FPGA) && ((status.TX_bt_tot >= DIO_FPGA_START_BT) || (st_TX == ST_FINISHED))) {
				status.ctrl_DMA &= ~DMA_CTRL_ENABLE_FPGA;
                // TODO: this might return ERROR_FPGA for small number of samples. so we ignore it at the moment but I am not sure why is this the case?
                status.err_FPGA = start_FPGA(false);
			}
		}
	}

	wmb(); // ensure start_TX/RX_SG operations are written to device

	// prepare next dsc's RX and TX if DMA enabled,
	// or stop RX/TX channel when all samples transmitted (stop_TX/RX calls verify_TX/RX(true))
	if(st_RX == ST_RESTARTED) err_RX = prepare_RX_dsc();
	else if(st_RX == ST_FINISHED) err_RX = stop_RX((status.ctrl_DMA & DMA_CTRL_ACTIVE_TX) == 0);
	if(st_TX == ST_RESTARTED) err_TX = prepare_TX_dsc();
	else if(st_TX == ST_FINISHED) err_TX = stop_TX((status.ctrl_DMA & DMA_CTRL_ACTIVE_RX) == 0);

	// check error RX channel (S2MM)
	if(status.status_RX & S2MM_STATUS_IRQ_DELAY) {
		pr_err(NAME "IRQ delay! RX control 0x%X, status 0x%x\n", READ_DMA_REGISTER(DMA_REG_S2MM_CTRL), status.status_RX);
		status.err_RX = err_RX = -50;
	}
	if(status.status_RX & S2MM_STATUS_IRQ_ERR) {
		pr_err(NAME "IRQ error! RX control 0x%08x, status 0x%08x\n", READ_DMA_REGISTER(DMA_REG_S2MM_CTRL), status.status_RX);
		pr_err(NAME "           RX current 0x%08x, tail   0x%08x\n", 
			READ_DMA_REGISTER(DMA_REG_S2MM_CURR), READ_DMA_REGISTER(DMA_REG_S2MM_TAIL));
		pr_err(NAME "IRQ error bits SG/simple %c%c%c/%c%c%c\n", 
			status.status_RX & S2MM_STATUS_ERR_SG_INT ? 'I' : '_',
			status.status_RX & S2MM_STATUS_ERR_SG_SLV ? 'S' : '_',
			status.status_RX & S2MM_STATUS_ERR_SG_DEC ? 'D' : '_',
			status.status_RX & S2MM_STATUS_ERR_INT    ? 'i' : '_',
			status.status_RX & S2MM_STATUS_ERR_SLV    ? 's' : '_',
			status.status_RX & S2MM_STATUS_ERR_DEC    ? 'd' : '_');
		status.err_RX = err_RX = -60;
	}

	// check error TX channel (MM2S)
	if(status.status_TX & MM2S_STATUS_IRQ_DELAY) {
		pr_err(NAME "IRQ delay! TX control 0x%X, status 0x%x\n", READ_DMA_REGISTER(DMA_REG_MM2S_CTRL), status.status_TX);
		status.err_TX = err_TX = -20;
	}
	if(status.status_TX & MM2S_STATUS_IRQ_ERR) {
		pr_err(NAME "IRQ error! TX control 0x%08x, status 0x%08x\n", READ_DMA_REGISTER(DMA_REG_MM2S_CTRL), status.status_TX);
		pr_err(NAME "           TX current 0x%08x, tail   0x%08x\n", 
			READ_DMA_REGISTER(DMA_REG_MM2S_CURR), READ_DMA_REGISTER(DMA_REG_MM2S_TAIL));
		pr_err(NAME "IRQ error bits SG/simple %c%c%c/%c%c%c\n", 
			status.status_TX & MM2S_STATUS_ERR_SG_INT ? 'I' : '_',
			status.status_TX & MM2S_STATUS_ERR_SG_SLV ? 'S' : '_',
			status.status_TX & MM2S_STATUS_ERR_SG_DEC ? 'D' : '_',
			status.status_TX & MM2S_STATUS_ERR_INT    ? 'i' : '_',
			status.status_TX & MM2S_STATUS_ERR_SLV    ? 's' : '_',
			status.status_TX & MM2S_STATUS_ERR_DEC    ? 'd' : '_');
		status.err_TX = err_TX = -30;
	}

	// reset DMA if an error occurred [removed since makes it difficult to debug]
	if((err_TX < 0) || (err_RX < 0)) {
		pr_err(NAME "irq_hdl: error TX = %d, RX = %d!\n", err_TX, err_RX);
		//reset_all();
	}
}

// set FPGA clock to external (true) or internal (false)
// returns 0 if ok, otherwise error
int set_ext_clk_FPGA(bool external) {
	int err = 0;
	uint32_t loops;
    //pr_err(NAME "set external clock = %d\n", (int)external);
	if(external && (!(status.status_FPGA.status & DIO_STATUS_EXT_USED))) { // switch to external clock
        // wait until clock is re-locked. max. TIMEOUT_SHORT (10ms)
        for(loops = LOOPS_SHORT; (loops > 0) && (!CLOCK_IS_LOCKED()); loops--) udelay(SLEEP_TIME_LONG);
        if (CLOCK_IS_LOCKED()) {
			// external clock is locked: try to switch to external clock
			CLOCK_SET_EXTERNAL(status.ctrl_FPGA);
			// wait until FPGA has switched to external clock
			for(loops = LOOPS_LONG; (loops > 0) && (!CLOCK_IS_EXTERNAL(status.status_FPGA.status)); loops--) udelay(SLEEP_TIME_LONG);
			if(loops == 0) {
				err = -ERROR_TIMEOUT;
				pr_err(NAME "switching to external clock failed! ctrl/status %x/%x\n", READ_DIO_REGISTER(DIO_REG_CTRL), READ_DIO_REGISTER(DIO_REG_STATUS));
			}
			else {
				status.ctrl_FPGA |= DIO_CTRL_EXT_CLK;
                if (status.ctrl_FPGA & DIO_CTRL_ERR_LOCK_EN) 
                    pr_err(NAME "ext.clock. ctrl/status %x/%x\n", READ_DIO_REGISTER(DIO_REG_CTRL), READ_DIO_REGISTER(DIO_REG_STATUS));
                else
                    pr_err(NAME "ext.clock. ctrl/status %x/%x (ignore loss!)\n", READ_DIO_REGISTER(DIO_REG_CTRL), READ_DIO_REGISTER(DIO_REG_STATUS));
			}
		}
		else {
			pr_err(NAME "external clock is not locked! ctrl/status %x/%x\n", READ_DIO_REGISTER(DIO_REG_CTRL), READ_DIO_REGISTER(DIO_REG_STATUS));
			err = -1;
		}
	}
	else if ((!external) && (status.status_FPGA.status & DIO_STATUS_EXT_USED)) { // switch to internal clock
		CLOCK_SET_INTERNAL(status.ctrl_FPGA);
		// wait until FPGA has switched to internal clock
		for(loops = LOOPS_LONG; (loops > 0) && CLOCK_IS_EXTERNAL(status.status_FPGA.status); loops--) udelay(SLEEP_TIME_LONG);
		if(loops == 0) {
			err = -ERROR_TIMEOUT;
			pr_err(NAME "switching to internal clock failed! ctrl/status %x/%x\n", READ_DIO_REGISTER(DIO_REG_CTRL), READ_DIO_REGISTER(DIO_REG_STATUS));
		}
		else {
			status.ctrl_FPGA &= ~DIO_CTRL_EXT_CLK;
			pr_err(NAME "int.clock. ctrl/status %x/%x\n", READ_DIO_REGISTER(DIO_REG_CTRL), READ_DIO_REGISTER(DIO_REG_STATUS));
		}
	}
	if (err) status.err_FPGA = err;
	return err;
}

// start FPGA
// if wait = true will wait until RUN bit is set, otherwise not.
// returns 0 if RUN bit is set, otherwise error (-ERROR_TIMEOUT if RUN bits was not set during TIMEOUT_LONG period)
// note: set all user settable control bits before calling start_FPGA!
int start_FPGA(bool wait) {
	int err = 0;
	uint32_t loops = LOOPS_LONG;
	// get actual status
	status.status_FPGA.status = READ_DIO_REGISTER(DIO_REG_STATUS);
	// check status
	if( (status.ctrl_FPGA & DIO_CTRL_RUN) != 0) err = WARN_ALREADY_DONE;
	else if ( READ_DIO_REGISTER(DIO_REG_NUM_SAMPLES) != status.set_samples ) err = -ERROR_ILLEGAL_STATE; // must have been set by IOCTL_START
	else if ( ((status.ctrl_FPGA & DIO_CTRL_EXT_CLK)?1:0) != (CLOCK_IS_EXTERNAL(status.status_FPGA.status)?1:0) ) err = -ERROR_ILLEGAL_STATE; // wrong clock selected
	else {
		// reset irq counter
		//irq_cnt = 0;
		// set multiplicator, strobe delay and external clock to defaults
//		WRITE_DIO_REGISTER(DIO_REG_BOARD_TIME_MULT, DIO_TIME_MULT);
//		WRITE_DIO_REGISTER(DIO_REG_STRB_DELAY, (DIO_STRB_DELAY << DIO_STRB_DELAY_START) | (DIO_STRB_WIDTH << DIO_STRB_WIDTH_START));
//		WRITE_DIO_REGISTER(DIO_REG_EXT_CLOCK, DIO_EXT_CLOCK_DEFAULT);

		// set FPGA running bit
		WRITE_DIO_REGISTER(DIO_REG_CTRL, status.ctrl_FPGA | DIO_CTRL_RUN);

	    // memory barrier to be sure data is written
	    wmb();

        if (wait) {
		    // wait until FPGA is running (fails when FPGA is in error mode!)
		    // if no data is available goes into idle state [so far not used], otherwise into running state
		    status.status_FPGA.status = READ_DIO_REGISTER(DIO_REG_STATUS);
		    for(; (loops > 0) && (((status.status_FPGA.status = READ_DIO_REGISTER(DIO_REG_STATUS)) & (DIO_STATUS_RUN|DIO_STATUS_READY)) != (DIO_STATUS_RUN|DIO_STATUS_READY)); --loops) {
			    udelay(SLEEP_TIME_LONG);
		    }
		    if(loops == 0) {
			    err = -ERROR_TIMEOUT;
			    pr_err(NAME "start_FPGA failed (%d loops)! ctrl/status %x/%x\n", LOOPS_LONG - loops, READ_DIO_REGISTER(DIO_REG_CTRL), READ_DIO_REGISTER(DIO_REG_STATUS));
		    }
		    else {
			    status.ctrl_FPGA |= DIO_CTRL_RUN;
			    //pr_err(NAME "start_FPGA ok (%d loops)! ctrl/st/DMA %x/%x/%x\n", 
                //    (TIMEOUT_LONG/SLEEP_TIME_LONG)-loops, READ_DIO_REGISTER(DIO_REG_CTRL), READ_DIO_REGISTER(DIO_REG_STATUS),status.ctrl_DMA);
		    }
        }
        else { // do not wait but read one time status
            status.ctrl_FPGA |= DIO_CTRL_RUN;
            status.status_FPGA.status = READ_DIO_REGISTER(DIO_REG_STATUS);
            if(!(status.status_FPGA.status & DIO_STATUS_RUN)) err = -ERROR_FPGA;
        }
	}

	status.err_FPGA = err;
	//pr_err(NAME "start_FPGA ctrl/status %x/%x result %d\n", READ_DIO_REGISTER(DIO_REG_CTRL), READ_DIO_REGISTER(DIO_REG_STATUS), err);

	return err;
}

// stop FPGA
int stop_FPGA(void) {
	int err = 0;
	uint32_t loops = LOOPS_LONG;

	if((status.ctrl_FPGA & DIO_CTRL_RUN) == 0) err = WARN_ALREADY_DONE;
	else {
		// reset FPGA running bit but keep other settings
		WRITE_DIO_REGISTER(DIO_REG_CTRL, READ_DIO_REGISTER(DIO_REG_CTRL) & ~DIO_CTRL_RUN);

		// memory barrier to be sure data is written
		wmb();
		
		// wait until FPGA is stopped (should not fail)
		for(; (loops > 0) && (((status.status_FPGA.status = READ_DIO_REGISTER(DIO_REG_STATUS)) & DIO_STATUS_RUN) != 0); --loops) udelay(SLEEP_TIME_LONG);
		if(loops == 0) {
			err = -ERROR_TIMEOUT;
			pr_err(NAME "stop_FPGA failed (%d loops)! ctrl/status %x/%x\n", LOOPS_LONG - loops, READ_DIO_REGISTER(DIO_REG_CTRL), READ_DIO_REGISTER(DIO_REG_STATUS));
		}
		else {
			status.ctrl_FPGA &= ~DIO_CTRL_RUN;
			pr_err(NAME "stop_FPGA ok (%d loops)! ctrl/status %x/%x\n", LOOPS_LONG - loops, READ_DIO_REGISTER(DIO_REG_CTRL), READ_DIO_REGISTER(DIO_REG_STATUS));
		}
	}

	status.err_FPGA = err;

	return err;
}

// reset FPGA
int reset_FPGA(void) {
	int err = 0;
	uint32_t loops[2] = {LOOPS_LONG,LOOPS_RESET};

	// use internal clock
	// force by setting status.ctrl_FPGA to external clock
	//status.ctrl_FPGA |= DIO_CTRL_EXT_CLK;
	//set_ext_clk_FPGA(false);

	// set DATA_NUM to 0
    // TODO: is this needed?
	WRITE_DIO_REGISTER(DIO_REG_NUM_SAMPLES, 0);
	// set multiplicator, strobe delay and external clock to defaults
	//WRITE_DIO_REGISTER(DIO_REG_BOARD_TIME_MULT, DIO_TIME_MULT);
	//WRITE_DIO_REGISTER(DIO_REG_STRB_DELAY, (DIO_STRB_DELAY << DIO_STRB_DELAY_START) | (DIO_STRB_WIDTH << DIO_STRB_WIDTH_START));
	//WRITE_DIO_REGISTER(DIO_REG_EXT_CLOCK, DIO_EXT_CLOCK_DEFAULT);

	// reset all FPGA control bits and set FPGA reset and (server ready) bit
	// note: reset bit is cleared automatically!
	WRITE_DIO_REGISTER(DIO_REG_CTRL, DIO_CTRL_RESET|DIO_CTRL_READY);

	// memory barrier to be sure data is written
	wmb();

	// wait for reset bit set in status register. we might miss this bit but 100ms timeout is not too long. maybe reduce timeout, but seems not to happen (often).
	for(; (loops[0] > 0) && ((DIO_STATUS_RESET & (status.status_FPGA.status = READ_DIO_REGISTER(DIO_REG_STATUS))) != DIO_STATUS_RESET); --loops[0]) udelay(SLEEP_TIME_LONG); 

	// wait until FPGA is reset. this should never fail. timeout is 1s.
	for(; (loops[1] > 0) && (((status.status_FPGA.status = READ_DIO_REGISTER(DIO_REG_STATUS)) & DIO_STATUS_RESET_MASK) != DIO_STATUS_RESET_EXP); --loops[1]) udelay(SLEEP_TIME_LONG);
	if((loops[0] == 0) || (loops[1] == 0)) { // timeout
		pr_err(NAME "reset_FPGA: reset timeout! (%u/%u loops) ctrl/sts = %x/%x (error)\n", LOOPS_LONG - loops[0], LOOPS_RESET - loops[1], READ_DIO_REGISTER(DIO_REG_CTRL), status.status_FPGA.status);
		if (loops[1] == 0) err = -ERROR_TIMEOUT; // only second timeout is serious
	}
	else {
		pr_err(NAME "reset_FPGA: (%u/%u loops) ctrl/sts = %x/%x (ok)\n", LOOPS_LONG - loops[0], LOOPS_RESET - loops[1], READ_DIO_REGISTER(DIO_REG_CTRL), status.status_FPGA.status);
		status.ctrl_FPGA = DIO_CTRL_NONE;
	}

	status.err_FPGA = err;

	return err;
}

// reset TX channel.
// returns 0 if ok, >0 if warning, <0 error
// ATTENTION: this resets also RX channel!
// call verify_TX and release_TX if you want to use data
int reset_TX(void) {
	int err = 0;
	uint32_t loops = LOOPS_LONG;

	//print_status(NAME "reset_TX");
	pr_err(NAME "reset TX (and RX) channel ...\n");

	// reset TX channel
	SET_REGISTER_BIT(DMA_REG_MM2S_CTRL, MM2S_CTRL_RESET);

	// memory barrier to be sure data is written
	wmb();

	// wait until DMA is reset
	for(; (loops > 0) && (!TX_IS_RESET(READ_DMA_REGISTER(DMA_REG_MM2S_CTRL),READ_DMA_REGISTER(DMA_REG_MM2S_STATUS))); --loops) udelay(SLEEP_TIME_LONG);
	if(loops == 0) {
		pr_err(NAME "reset_TX: timeout! (error)\n");
		err = -ERROR_TIMEOUT;
	}
	else {
		//pr_err(NAME "reset_TX: succeeded! (ok)\n");
		// reset status
		status.ctrl_DMA &= ~(DMA_CTRL_ENABLE_TX | DMA_CTRL_ACTIVE_TX);
		
		// reset packet buffer count (next starts with start bit)
		p_count = 0;
	}

	//print_status(NULL);
	status.err_TX = err;

	return err;
}

// reset RX channel
// returns 0 if ok, >0 if warning, <0 error
// ATTENTION: this resets also TX channel!
// call verify_RX and release_RX if you want to use data
int reset_RX(void) {
	int err = 0;
	uint32_t loops = LOOPS_LONG;

	//print_status(NAME "reset_RX");
	pr_err(NAME "reset RX (and TX) channel ...\n");

	// reset RX channel
	SET_REGISTER_BIT(DMA_REG_S2MM_CTRL, S2MM_CTRL_RESET);

	// memory barrier to be sure data is written
	wmb();

	for(; (loops > 0) && (!RX_IS_RESET(READ_DMA_REGISTER(DMA_REG_S2MM_CTRL),READ_DMA_REGISTER(DMA_REG_S2MM_STATUS))); --loops) udelay(SLEEP_TIME_LONG);
	if(loops == 0) {
		pr_err(NAME "reset_RX: timeout! (error)\n");
		err = -ERROR_TIMEOUT;
	}
	else {
		//pr_err(NAME "reset_RX: succeeded! (ok)\n");
		// reset status
		status.ctrl_DMA &= ~(DMA_CTRL_ENABLE_RX | DMA_CTRL_ACTIVE_RX);
	}

	//print_status(NULL);
	status.err_RX = err;

	return err;
}

void check_TX(void) {
	struct dsc_info *dsc = dsc_TX.tail;
	uint32_t curr = READ_DMA_REGISTER(DMA_REG_MM2S_CURR);
	uint32_t tail = READ_DMA_REGISTER(DMA_REG_MM2S_TAIL);
	int i = 0;
	pr_err(NAME "stop_TX: tail 0x%08x != curr 0x%08x, status 0x%x\n", tail, curr, READ_DMA_REGISTER(DMA_REG_MM2S_STATUS));
	pr_err(NAME "dsc:     virt     phys   m_virt\n");
	pr_err(NAME "%3d: %p %08x %p\n", i, dsc, tail, dsc->buffer);
	while(dsc && (tail != curr)) {
		++i;
		dsc = dsc->next;
		if(dsc == NULL) break;
		tail = GET_ALIGNED_PHYS_DSC(dsc->phys_addr);
		pr_err(NAME "%3d: %p %08x %p\n", i, dsc, tail, dsc->buffer);
	}
}

// stops all pending TX DMA transactions
// this might fail when DMA is not idle! resetting DMA is working however, but resets both channels!
// if reset_on_error == true waits maximum TIMEOUT_LONG until idle state, otherwise calls reset_TX!
// returns 0 if ok, >0 if warning, <0 error
// calls verify_TX if DMA_CTRL_ACTIVE_TX and release_TX if DMA_CTRL_STOP_TX_AT_END
// TODO: reset_on_error caused that verify_TX gives error if finds completed dscs (same for RX).
int stop_TX(bool reset_on_error) {
	int err = 0;
	uint32_t loops;

	if((status.ctrl_DMA & DMA_CTRL_ENABLE_TX) == 0) err = WARN_ALREADY_DONE;
	else {
		if ((READ_DMA_REGISTER(DMA_REG_MM2S_STATUS) & MM2S_STATUS_IDLE) == 0) {
			//pr_err(NAME "stop_TX not idle ...\n");
			if(reset_on_error) {
				// wait until idle, otherwise reset
				loops = LOOPS_LONG;
				for (; (loops > 0) && ((READ_DMA_REGISTER(DMA_REG_MM2S_STATUS) & MM2S_STATUS_IDLE) == 0); --loops) udelay(SLEEP_TIME_LONG);
				if (loops == 0) { // timeout
					pr_err(NAME "stop_TX not idle: reset TX (and RX)!\n");
					err = reset_TX();
					if(!err) err = WARN_TIMEOUT;
					status.ctrl_DMA |= DMA_CTRL_ENABLE_TX; // otherwise verify_TX error -24 when finds completed dscs
				}
			}
			else {
				pr_err(NAME "stop_TX not idle (might fail)\n");
				err = WARN_NOT_IDLE;
			}
		}

		// reset run bit and wait for the halted bit to go high
		RESET_REGISTER_BIT(DMA_REG_MM2S_CTRL, MM2S_CTRL_RUN);
		loops = LOOPS_LONG;
		for (; (loops > 0) && ((READ_DMA_REGISTER(DMA_REG_MM2S_STATUS) & MM2S_STATUS_HALTED) == 0); --loops) udelay(SLEEP_TIME_LONG);
		if (loops == 0) { // timeout
			if (err) pr_err(NAME "stop_TX: timeout/not idle! (error)\n");
			else pr_err(NAME "stop_TX: timeout! (error)\n");
			err = -ERROR_TIMEOUT;
		}

		if(err >= 0) {
			// disable TX
			status.ctrl_DMA &= ~DMA_CTRL_ENABLE_TX;

			// check if there were completed dsc's and release all of them
			err = verify_TX(true);
            if (err < 0) pr_err("%s *** stop_TX: verify_TX error %d! ***\n\n", NAME, err);
			if(status.ctrl_DMA & DMA_CTRL_ACTIVE_TX) err = -2; // verify_TX(true) must clear this bit!
		}
	}
	if (err) status.err_TX = err;

	return err;
}

// stop all pending RX DMA transactions
// this might fail when DMA is not idle! resetting DMA is working however, but resets both channels!
// if reset_on_error == true waits maximum TIMEOUT_LONG until idle state, otherwise calls reset_RX!
// returns 0 if ok, >0 if warning, <0 error
// TODO: reset_on_error caused that verify_RX gives error if finds completed dscs.
int stop_RX(bool reset_on_error) {
	int err = 0;
	uint32_t loops;

	if((status.ctrl_DMA & DMA_CTRL_ENABLE_RX) == 0) err = WARN_ALREADY_DONE;
	else {
		if ((READ_DMA_REGISTER(DMA_REG_S2MM_STATUS) & S2MM_STATUS_IDLE) == 0) {
			//pr_err(NAME "stop_RX not idle ...\n");
			if(reset_on_error) {
				// wait until idle, otherwise reset
				loops = LOOPS_LONG;
				for (; (loops > 0) && ((READ_DMA_REGISTER(DMA_REG_S2MM_STATUS) & S2MM_STATUS_IDLE) == 0); --loops) udelay(SLEEP_TIME_LONG);
				if(loops == 0) { // timeout
					pr_err(NAME "stop_RX not idle: reset RX (and TX)!\n");
					err = reset_RX();
					if(!err) err = WARN_TIMEOUT;
					status.ctrl_DMA |= DMA_CTRL_ENABLE_RX; // otherwise verify_RX error when finds completed dscs
				}
			}
			else {
				pr_err(NAME "stop_RX not idle (might fail)\n");
				err = WARN_NOT_IDLE;
			}
		}

		// reset run bit and wait for the halted bit to go high
		RESET_REGISTER_BIT(DMA_REG_S2MM_CTRL, S2MM_CTRL_RUN);
		loops = LOOPS_LONG;
		for (; (loops > 0) && ((READ_DMA_REGISTER(DMA_REG_S2MM_STATUS) & S2MM_STATUS_HALTED) == 0); --loops) udelay(SLEEP_TIME_LONG);
		if(loops == 0) { // timeout
			if(err) pr_err(NAME "stop_RX: timeout/not idle! (error)\n");
			else pr_err(NAME "stop_RX: timeout! (error)\n");
			err = -ERROR_TIMEOUT;
		}

		if(err >= 0) {
			// disable RX
			status.ctrl_DMA &= ~DMA_CTRL_ENABLE_RX;

			// check if there were completed dsc's and release all of them
			err = verify_RX(true);
            if (err < 0) pr_err("\n%s *** stop_RX: verify_RX error %d! ***\n\n", NAME, err);
			if(status.ctrl_DMA & DMA_CTRL_ACTIVE_RX) err = -2; // verify_RX must clear this bit!
		}
	}
	if (err) status.err_RX = err;

	return err;
}

// start TX in scatter/getter DMA mode
// returns 0 if ok, >0 if warning, <0 error
// ATTENTION: must be called with user_mutex locked!
// notes: 
// - starts descriptors [dsc_TX.head..last_prep] (inclusive).
// - after return dsc_TX.tail = dsc_TX.last_prep and dsc_TX.last_prep = NULL.
// - sets DMA_CTRL_ACTIVE_TX bit in status.ctrl_DMA
// - call verify_TX before to update dsc_TX.head to first not-completed dsc.
// - if dsc_TX.last_prep == NULL no descriptors are ready and returns without error
// - if status.ctrl_DMA & DMA_CTRL_ACTIVE_TX == 0 then no descriptors are running
int start_TX_SG(void) {
	int err = 0;
	uint32_t loops, control, tmp;
	struct SG_dsc *dsc;

	// check if TX DMA is enabled
	if((status.ctrl_DMA & DMA_CTRL_ENABLE_TX) == 0) {
		// reset descriptors (tail = last = NULL)
		//status.ctrl_DMA &= ~DMA_CTRL_ACTIVE_TX;
		//dsc_TX.tail = dsc_TX.last_prep = NULL;
		err = WARN_NOT_ENABLED;
	}
	else {
		//pr_err(NAME "start_TX_SG [%p,%p,%p]\n", dsc_TX.head, dsc_TX.tail, dsc_TX.last_prep);
		//pr_err(NAME "start_TX_SG\n");
		// check if descriptors are ready
		if(dsc_TX.last_prep == NULL) { 
			// no descriptors ready: set dma status to incactive
			//pr_err(NAME "start_TX_SG: no prepared descriptors (ok)\n");
			//status.ctrl_DMA &= ~DMA_CTRL_ACTIVE_TX;
			err = WARN_NO_DATA;
		}
		else {
			// set last_prep->next to NULL. this avoids DMA going byound tail.
			//dsc = GET_ALIGNED_DSC(dsc_TX.last_prep->virt_addr);
			//dsc->next_low = 0;

			// check validity of descriptors
			if(dsc_TX.head == NULL) err = -1;
			else {
				//err = check_sg_dsc(dsc_TX.head, dsc_TX.last_prep, true);
				//if(!err) {
				{
					// read TX control and status registers
					control = READ_DMA_REGISTER(DMA_REG_MM2S_CTRL);
					tmp = READ_DMA_REGISTER(DMA_REG_MM2S_STATUS);

					// check scatter/getter bit
					if(!TX_IS_SG(tmp)) err = -1;
					// check cyclic bit
					else if(TX_IS_CYCLIC(control)) err = -2;
					// check error bits, IRQs and reserved bits
					else if(!TX_IS_OK(control, tmp)) { // restart from error
						err = -3;
						/*WRITE_DMA_REGISTER(DMA_REG_MM2S_CTRL, );
						// wait until halted bit is reset
						loops = LOOPS_LONG;
						for(; (loops > 0) && (READ_DMA_REGISTER(DMA_REG_MM2S_STATUS) & MM2S_STATUS_HALTED); --loops) udelay(SLEEP_TIME_LONG);

						// clear irq by writing to it
						WRITE_DMA_REGISTER(DMA_REG_MM2S_STATUS, tmp & TX_IRQ_SETTINGS);

						// set current dsc which is NULL
						tmp = GET_ALIGNED_PHYS_DSC(dsc_TX.tail->next->phys_addr);
						WRITE_DMA_REGISTER(DMA_REG_MM2S_CURR,tmp);
						WRITE_DMA_REGISTER(DMA_REG_MM2S_CURR_MSB,0);

						// set run bit, enable interrupts on completion and error, disable interrupt on delay
						WRITE_DMA_REGISTER(DMA_REG_MM2S_CTRL, (control & (~MM2S_CTRL_IRQ_MASK)) | MM2S_CTRL_RUN | TX_IRQ_SETTINGS);

						// memory barrier to be sure data is written
						wmb();

						// wait until halted bit is reset
						loops = LOOPS_LONG;
						for(; (loops > 0) && (READ_DMA_REGISTER(DMA_REG_MM2S_STATUS) & MM2S_STATUS_HALTED); --loops) udelay(SLEEP_TIME_LONG);
						if(loops == 0) err = -31;
						dsc = GET_ALIGNED_DSC(dsc_TX.tail->virt_addr); // this is virt_addr
						*/
					}
					// check if is already running
					else if(TX_IS_RUNNING(control, tmp)) {
						// already running:
						// DMA status must be active
						// IRQs must be enabled and tail descriptor must be dsc_TX->tail
						// TODO:
						// - idle bit might be set if there are no more descriptors.
						// - current might be not be equal tail descriptor but can be ahead!? but then does not restart!?
						// - to avoid this I set tail dsc->next = NULL [causes IRQ_ERR with ERR_SG_SLV, curr = NULL, cannot restart]
						if(TX_IS_IDLE(tmp)) {
							tmp = READ_DMA_REGISTER(DMA_REG_MM2S_TAIL); 
							if ((tmp != READ_DMA_REGISTER(DMA_REG_MM2S_CURR)))
								pr_err(NAME "start_TX_SG: IDLE! curr 0x%08x != tail 0x%08x\n", READ_DMA_REGISTER(DMA_REG_MM2S_CURR), tmp);
							//else pr_err(NAME "start_TX_SG: IDLE! curr == tail 0x%08x \n", tmp);
						}
						else tmp = READ_DMA_REGISTER(DMA_REG_MM2S_TAIL); // this is phys_addr
						dsc = GET_ALIGNED_DSC(dsc_TX.tail->virt_addr); // this is virt_addr
						//if((status.ctrl_DMA & DMA_CTRL_ACTIVE_TX) == 0) err = -12;
						if((control & MM2S_CTRL_IRQ_MASK) != TX_IRQ_SETTINGS) err = -13;
						else if (dsc_TX.tail == NULL) err = -14; // here tail cannot be NULL!
						else if (tmp != GET_ALIGNED_PHYS_DSC(dsc_TX.tail->phys_addr)) err = -15;
						else if (dsc == NULL) err = -16;
						//else if (dsc->next_low != 0) err = -17; // must be 0
						else if (dsc_TX.tail->next == NULL) err = -18; // must be first prepared dsc
						else {
							// set valid first prepared dsc. this allows DMA to go byound tail.
							// not done here but right before writing of tail dsc!
							//tmp = GET_ALIGNED_PHYS_DSC(dsc_TX.tail->next->phys_addr);
							//pr_err(NAME "start_TX_SG: re-start\n");
						}
					}
					else if(status.ctrl_DMA & DMA_CTRL_ACTIVE_TX) err = -21; // must be inactive
					else if(dsc_TX.tail != NULL) err = -22; // must be NULL
					else {	// not running:
						//pr_err(NAME "start_TX_SG: starting ...\n");
						// write current descriptor register with starting descriptor
						WRITE_DMA_REGISTER(DMA_REG_MM2S_CURR,GET_ALIGNED_PHYS_DSC(dsc_TX.head->phys_addr));
						WRITE_DMA_REGISTER(DMA_REG_MM2S_CURR_MSB,0);

						// set run bit, enable interrupts on completion and error, disable interrupt on delay
						WRITE_DMA_REGISTER(DMA_REG_MM2S_CTRL, (control & (~MM2S_CTRL_IRQ_MASK)) | MM2S_CTRL_RUN | TX_IRQ_SETTINGS);

						// memory barrier to be sure data is written
						wmb();

						// wait until halted bit is reset
						loops = LOOPS_LONG;
						for(; (loops > 0) && (READ_DMA_REGISTER(DMA_REG_MM2S_STATUS) & MM2S_STATUS_HALTED); --loops) udelay(SLEEP_TIME_LONG);
						if(loops == 0) err = -31;
						dsc = NULL;
					}
					
					// running or not: writing tail descriptor will (re-)start DMA
					if(!err) {

						// all descriptors up to last will be sent after next 2 instructions
						// update descriptors and reset last_prep=NULL
						// head was updated by verify_TX
						dsc_TX.tail = dsc_TX.last_prep;
						dsc_TX.last_prep = NULL;

						// update status
						status.ctrl_DMA |= DMA_CTRL_ACTIVE_TX;

						/*if(dsc) {
							// set valid first prepared dsc. this allows DMA to go byound tail.
							// TODO: if between here and writing tail dsc the DMA arrives at tail
							//       it might go byound and restarting does not work!
							//       I do not know how to fix this, but probability is very low.
							//       - one solution for not too many data is to use cycling mode.
							dsc->next_low = tmp;
						}*/

						// write tail descriptor
						// this causes DMA transfer to start
						WRITE_DMA_REGISTER(DMA_REG_MM2S_TAIL,GET_ALIGNED_PHYS_DSC(dsc_TX.tail->phys_addr));
						WRITE_DMA_REGISTER(DMA_REG_MM2S_TAIL_MSB,0);

						// true time starts somewhere between WRITE_DMA_REGISTER above and end of barrier below
						//GET_TIME(t_TX_start);

						// memory barrier to be sure data is written
						wmb();				

						//do not output anything here, otherwise disturbs time measurement
					}
				}
			}
		}
	}

	if (err) status.err_TX = err;

	if(err < 0) pr_err(NAME "start_TX_SG error %d ctrl/status = 0x %x/%x\n", err, READ_DMA_REGISTER(DMA_REG_MM2S_CTRL), READ_DMA_REGISTER(DMA_REG_MM2S_STATUS));
	else if(err==0) {
		status.dsc_TX_a += status.dsc_TX_p;
		status.dsc_TX_p = 0;
		//pr_err(NAME "start_TX_SG %p - %p active %u (ok)\n", dsc_TX.head->buffer, dsc_TX.tail->buffer, status.dsc_TX_a);
	}

	return err;
}

// start RX in scatter/getter DMA mode
// returns 0 if ok, >0 if warning, <0 error
// ATTENTION: must be called with user_mutex locked!
// notes: 
// - starts descriptors [dsc_RX.head..last_prep] (inclusive).
// - after return dsc_RX.tail = dsc_RX.last_prep and dsc_RX.last_prep = NULL.
// - sets DMA_CTRL_ACTIVE_RX bit in status.ctrl_DMA
// - call verify_RX before to update dsc_RX.head to first not-completed dsc.
// - if dsc_RX.last_prep == NULL no descriptors are ready and returns without error
// - if status.ctrl_DMA & DMA_CTRL_ACTIVE_RX == 0 then no descriptors are running
// - if status.ctrl_DMA & DMA_CTRL_CYCLIC_RX bit is set then cyclic bit is set if not running. if running will not do anything.
//   in this case all RX dsc's must be prepared/active with dsc_RX.last_prep->next == dsc_RX.head.
int start_RX_SG(void) {
	int err = 0;
	uint32_t loops, control, st, tail;
	// check if RX DMA is enabled
	if((status.ctrl_DMA & DMA_CTRL_ENABLE_RX) == 0) {
		// reset descriptors (tail = last = NULL)
		//dsc_RX.tail = dsc_RX.last_prep = NULL;
		//status.ctrl_DMA &= ~DMA_CTRL_ACTIVE_RX;
		err = WARN_NOT_ENABLED;
	}
	//else if(num_old > 0L) err = WARN_ALL_ACTIVE; // test: do not restart if there are active dsc's (get prepare_RX_dsc error -31 when this is commented out!?)
	else {
		//pr_err(NAME "start_RX_SG [%p,%p,%p]\n", dsc_RX.head, dsc_RX.tail, dsc_RX.last_prep);
		//pr_err(NAME "start_RX_SG\n");

		// check if descriptors are ready
		if(dsc_RX.last_prep == NULL) { 
			// no descriptors ready: set dma status to incactive (done by verify)
			//pr_err(NAME "start_RX_SG: no prepared descriptors (ok)\n");
			//status.ctrl_DMA &= ~DMA_CTRL_ACTIVE_RX;
			err = WARN_NO_DATA;
		}
		else {
			// check validity of descriptors
			if(dsc_RX.head == NULL) err = -1;
			else {
				err = check_sg_dsc(dsc_RX.head, dsc_RX.last_prep, false);

				// in cyclic mode all descriptors must have been prepared
				if ((!err) && (status.ctrl_DMA & DMA_CTRL_CYCLIC_RX)) {
					if (dsc_RX.last_prep->next != dsc_RX.head) err = -2;
				}

				if(!err) {
					// read RX control and status registers
					control = READ_DMA_REGISTER(DMA_REG_S2MM_CTRL);
					st = READ_DMA_REGISTER(DMA_REG_S2MM_STATUS);

					// check scatter/getter bit
					if(!RX_IS_SG(st)) err = -3;
					// check error bits, IRQs and reserved bits
					else if(!RX_IS_OK(control, st)) err = -4;
					// check if is already running
					else if(RX_IS_RUNNING(control, st)) {
						// already running:
						// DMA status must be active (no, verify changes it to inactive if all dsc completed)
						// IRQs must be enabled and tail descriptor must be dsc_RX->tail
						// idle bit might be set if there are no more descriptors
						// current might be not be equal tail descriptor but can be ahead
						//if((status.ctrl_DMA & DMA_CTRL_ACTIVE_RX) == 0) err = -12;
						tail = READ_DMA_REGISTER(DMA_REG_S2MM_TAIL);
						if((control & S2MM_CTRL_IRQ_MASK) != RX_IRQ_SETTINGS) err = -13;
						else if(dsc_RX.tail == NULL) err = -14; // here tail cannot be NULL!
						else if(tail != GET_ALIGNED_PHYS_DSC(dsc_RX.tail->phys_addr)) err = -15;
						// if cyclic bit is set we should not come here (no prepared dscs and should not be called when running)
						else if(RX_IS_CYCLIC(control)) err = -16;
						else {
						//	pr_err(NAME "start_RX_SG: re-start\n");
							//err = check_stall();
						}
					}
					else if(status.ctrl_DMA & DMA_CTRL_ACTIVE_RX) err = -21;
					else {	// not running:
						//pr_err(NAME "start_RX_SG: starting ...\n");
						// write current descriptor register with starting descriptor
						WRITE_DMA_REGISTER(DMA_REG_S2MM_CURR,GET_ALIGNED_PHYS_DSC(dsc_RX.head->phys_addr));
						WRITE_DMA_REGISTER(DMA_REG_S2MM_CURR_MSB,0);

						// set run bit and cyclic bit if enabled, enable interrupts on completion and error, disable interrupt on delay
						//if (status.ctrl_DMA & DMA_CTRL_CYCLIC_RX) WRITE_DMA_REGISTER(DMA_REG_S2MM_CTRL, control | S2MM_CTRL_RUN | S2MM_CTRL_CYCLIC);
						//else WRITE_DMA_REGISTER(DMA_REG_S2MM_CTRL, control | S2MM_CTRL_RUN);
						if (status.ctrl_DMA & DMA_CTRL_CYCLIC_RX) 
							WRITE_DMA_REGISTER(DMA_REG_S2MM_CTRL, (control & (~S2MM_CTRL_IRQ_MASK)) | S2MM_CTRL_RUN | RX_IRQ_SETTINGS |  S2MM_CTRL_CYCLIC);
						else 
							WRITE_DMA_REGISTER(DMA_REG_S2MM_CTRL, (control & (~S2MM_CTRL_IRQ_MASK)) | S2MM_CTRL_RUN | RX_IRQ_SETTINGS);

						// memory barrier to be sure data is written
						wmb();

						// wait until halted bit is reset
						loops = LOOPS_LONG;
						for(; (loops > 0) && (READ_DMA_REGISTER(DMA_REG_S2MM_STATUS) & S2MM_STATUS_HALTED); --loops) udelay(SLEEP_TIME_LONG);
						if(loops == 0) {
							//pr_err(NAME "start_RX_SG: timeout! (error)\n");
							err = -ERROR_TIMEOUT;
						}
						/*else {
							// enable interrupts on completion and error, disable interrupt on delay
							WRITE_DMA_REGISTER(DMA_REG_S2MM_CTRL, (control & (~S2MM_CTRL_IRQ_MASK)) | S2MM_CTRL_RUN | RX_IRQ_SETTINGS);
						}*/
					}
					
					// running or not: writing tail descriptor will (re-)start DMA
					if(err >= 0) {
						// all descriptors up to last will be sent after next 2 instructions
						// update tail descriptor and reset last_prep=NULL
						// head was updated by verify_RX
						dsc_RX.tail = dsc_RX.last_prep;
						dsc_RX.last_prep = NULL;

						status.ctrl_DMA |= DMA_CTRL_ACTIVE_RX;

						// write tail descriptor
						// this causes DMA transfer to start
						WRITE_DMA_REGISTER(DMA_REG_S2MM_TAIL,GET_ALIGNED_PHYS_DSC(dsc_RX.tail->phys_addr));
						WRITE_DMA_REGISTER(DMA_REG_S2MM_TAIL_MSB,0);

						// true time starts somewhere between WRITE_DMA_REGISTER above and end of barrier below
						//GET_TIME(t_RX_start);
						
						// memory barrier to be sure data is written (done in irq_hdl)
						//wmb();				

						/* for debugging:
						// wait until idle bit is reset
						for(ms = TIMEOUT, us = 0; (ms > 0) && ((READ_DMA_REGISTER(DMA_REG_S2MM_STATUS) & S2MM_STATUS_IDLE) != 0); us+=SLEEP_TIME_LONG) {
							if(us >= 1000) {
								us -= 1000;
								ms--;
								//if(ms % 1000 == 0) pr_err(NAME "%2ds: waiting for RX halted bit to deassert ...\n", ms / 1000);
							}
							udelay(SLEEP_TIME_LONG);
						}
						if(ms <= 0) {
							//pr_err(NAME "start_RX_SG: timeout! (error)\n");
							err = -ERROR_TIMEOUT;
						}*/

						//do not output anything here, otherwise disturbs time measurement
					}
				}
			}
		}
	}			
	//if(err >= 0) {
	//	if(num_curr != 0xFFFFFFFF) err = (err << 8) | num_curr;
	//}

	status.err_RX = err;

	status.debug[DBG_OFF_RX_START+status.debug_count] = ((status.dsc_RX_a+status.dsc_RX_p) << 8) | status.dsc_RX_p;

	if(err < 0) pr_err(NAME "start_RX_SG error %d\n", err);
	else if(err == 0) {
		//pr_err(NAME "start_RX_SG %d started (%d)\n", status.dsc_RX_p, err);
		status.dsc_RX_a += status.dsc_RX_p;
		status.dsc_RX_p = 0;
	}

	return err;
}

// copy available RX data into user buffer
// if buffer=NULL does not copy but liberates RX buffers
// decrements status.RD_bt_act by the number of copied bytes
// starts copying from mem_RX.first until mem_RX.next or uncompleted buffer or length reached
// updates mem_RX.first to point to first not read RX buffer
// returns number of copied bytes or <0 on error
// ATTENTION: must be called with user_mutex locked!
// note: driver must verify user buffer with access_ok!
ssize_t copy_RX(char __user * buffer, size_t length) {
	size_t bytes;
	ssize_t result;
	struct mem_info *mem = mem_RX.first;

//pr_err(NAME "read copy %u: act/set = %u/%u, RXbt = %u/%u (1)\n", length, status.RD_bt_tot, status.bt_tot, status.RD_bt_act, status.RD_bt_max); 

	if (mem_RX.next == NULL) result = status.RD_bt_act ? -ERROR_NO_DATA : WARN_NO_DATA; // no prepared buffers
	else {
		bytes = result = (length <= status.RD_bt_act) ? length : status.RD_bt_act; // number of bytes to copy
		while(bytes > 0) {
			// stop if wrong address, buffer empty or buffer in use
			if((mem->virt_addr == NULL) || (mem->bytes == 0) || (mem->ref_cnt != 0)) break;
			if(mem->bytes > bytes) break; // copy only entire buffers
			if ( buffer == NULL ) {
				//pr_err(NAME "copy_RX: free %u bytes\n", mem->bytes);
				status.RD_bt_drop += mem->bytes;
			}
			else {
				//pr_err(NAME "copy_RX: %u bytes\n", mem->bytes);
				if(__copy_to_user(buffer, GET_ALIGNED_BUFFER(mem->virt_addr), mem->bytes) != 0) {
					pr_err(NAME "copy_RX: %u bytes error!\n", mem->bytes);
					result = -EFAULT; // -14 = bad address
					break;
				}
				buffer += mem->bytes;	// next byte in user buffer
			}

			bytes -= mem->bytes;	// remaining bytes

			// reset buffer bytes
			mem->bytes = 0;

			// next buffer
			mem = mem->next;
			// stop if first unprepared buffer reached (all buffers copied)
			if(mem == mem_RX.next) break;
		}
	}

	if ( result > 0 ) { 
		// only entire buffers were copied. correct for the difference
		result -= bytes;
		// reset byte counter
		status.RD_bt_act -= result;
		// update first buffer with next data
		mem_RX.first = mem;
	}
	else status.err_RX = result;

	//if (buffer) pr_err(NAME "copy_RX: %d/%u rest %u\n", result, length, status.RD_bt_act);
	//else pr_err(NAME "copy_RX: freed %d/%u rest %u\n", result, length, status.RD_bt_act);  

	// return number of copied bytes
	return result;
}

// verify completed TX descriptors 
// increments status.TX_bt_tot completed bytes and sets dsc_TX.head to first not-completed dsc.
// if release == true releases all not completed dsc's until dsc_TX.last_prep.
// resets DMA_CTRL_ACTIVE_TX bit in status.ctrl_DMA if no dsc's are active
// returns 0 if ok, >0 if warning, <0 error
// ATTENTION: must be called with user_mutex locked!
// notes:
// - starts verification from first until tail (inclusive).
// - stops at the first non-completed dsc or at dsc_RX.tail (!release) or dsc_RX.last_prep (if not NULL and release).
// - first and tail can be the same descriptor.
// - release sets buffer bytes to 0L and removes association of buffer with dsc's.
// - start and end bits are ignored.
int verify_TX(bool release) {
	int err = 0, num = 0;
	uint32_t a_bytes = 0;
	struct dsc_info *next;
	struct SG_dsc *dsc = NULL;
	bool active = status.ctrl_DMA & DMA_CTRL_ACTIVE_TX;

	//if(release) pr_err(NAME "verify_TX release, active = %d\n", active);

	next = dsc_TX.head; // first dsc, cannot be NULL
	//last = (release && dsc_TX.last_prep) ? dsc_TX.last_prep : dsc_TX.tail; // last running or last prepared dsc
	//if((next == NULL) || (dsc_TX.tail == NULL)) err = -1;
	if(next == NULL) err = -1;
	else if((dsc_TX.tail == NULL) || (!(active || (release && (dsc_TX.last_prep != NULL))))) err = WARN_NO_DATA; // nothing todo!
	else {
		while(true) {
			// get descriptor
			dsc = GET_ALIGNED_DSC(next->virt_addr);	// aligned virtual descriptor
			if(dsc == NULL) { err = -10; break; } // ensure dsc is not NULL
			if(next->buffer == NULL) { err = -11; break; } // ensure buffer is not NULL
		
			if(next->buffer->ref_cnt == 0) { err = -12; break; } // wrong buffer reference count!

			if(active) { // running dsc
				if( (next == dsc_TX.tail) && (dsc_TX.last_prep == NULL) && (mem_TX.next != NULL) &&
				    (mem_TX.next != (next->buffer->next ? next->buffer->next : mem_TX.first) ) ) { 
					pr_err(NAME "verify_TX e-13 %p %p %p %p (%d)\n", next, next->buffer, next->buffer->next, mem_TX.next, release);	
					check_dsc(&dsc_TX, "verify TX (run error)");
					check_mem(&mem_TX, true, true);
					err = -13; break; // wrong next buffer?
				}
				if(dsc->status & SG_MM2S_STATUS_COMPLETE) { 
					// count number of completed dsc
					++num;
					// descriptor is completed
					if((dsc->status & SG_MM2S_STATUS_BYTES) != (dsc->control & SG_MM2S_CTRL_BYTES)) { err = -14; break; }
					else {
						// descriptor ok: count number of sent bytes/samples
						a_bytes += (dsc->status & SG_MM2S_STATUS_BYTES);	
					}
				}
				else {
					// running but not completed: set head to first not completed descriptor
					dsc_TX.head = next;
					//if(release) mem_TX.next = next->buffer; // save first not completed buffer
					if(!release) break; // stop loop if should not release					
				}
			}
			else { // not running dsc
				if((next == dsc_TX.last_prep) && (mem_TX.next != NULL) &&
					(mem_TX.next != (next->buffer->next ? next->buffer->next : mem_TX.first) ) ) { 
					pr_err(NAME "verify_TX e-23 %p %p %p %p (%d)\n", next, next->buffer, next->buffer->next, mem_TX.next, release);	
					check_dsc(&dsc_TX, "verify_TX (stopped error)");
					check_mem(&mem_TX, true, true);
					err = -23; break; // wrong next buffer?
				}
				if(dsc->status & SG_MM2S_STATUS_COMPLETE) { // not running dsc completed?
					// TODO: this should never happen but it occurs! I am sure this is a BUG in DMA module!!!
					//       DMA is reading dsc's in advance and IGNORES tail dsc and reads byound!
					//       this can be seen on curr dsc pointer which I have seen 1 or 2 (maybe even more) dsc's AFTER tail dsc.
					//       if this happens preparing new dsc's DOES NOT start DMA again and I get error_in in FPGA.
					//       - to avoid this I try to have sufficient number of running dsc's but if driver starts dropping (TX or RX) irqs its bad.
					//       + one could give NULL as the next dsc after tail. but when we write back good dsc it might happen right then!
					//         unless we wait by purpose that dsc is idle before restarting it again - but how to wait or is always idle when tail reached?
					//         one could do it in a stop-and-go fashion. preparing all dscs, run and wait always until last and only irq. then restart again.
					//         would need some testing since relies on FIFOs to be large enough.
					//         - should check official driver - although this is really a mess...
					//         maybe adding some valid dscs after tail but with 0 bytes might be the trick?
					//       + for reps > 1 if all TX buffers can be kept in memory one could use DMA cycling mode which does not need much driver intervention.
                                        // addendum: on RX the same error (-33) is caused by stop_RX calling reset_RX since channel is not idle (tail not reached)
					//           so it might be a side-effect of reset which supposedly releases last dsc? which might not be a bug.
					//           changed error code from -24 to +24 to indicate warning and do not overwrite other error 
					if(!err) err = 24; 
					//break; break causes memory leak and we get ENOMEM if happens several time. releasing buffer should fix it.
				}
			}

			// reduce buffer reference count
			--next->buffer->ref_cnt;
			// invalidate buffer
			next->buffer = NULL;

			// invalidate descriptor
			dsc->address_low = 0L;
			dsc->status = dsc->control = 0L;

			if(next == dsc_TX.tail) {
				if(next->next == NULL) { err = -15; break; } // ring-buffer cannot be NULL
				// all descriptors completed: set head to tail->next and reset active flag
				// for running and not completed dsc's we end up here only if release = true
				// and we can assume that verify_TX(true) was called by stop_TX
				//pr_err(NAME "verify_TX reset active flag. release = %d, active = %d\n", release, active);
				dsc_TX.head = next->next;
				status.ctrl_DMA &= ~DMA_CTRL_ACTIVE_TX;
				if(release && (dsc_TX.last_prep != NULL)) active = false; // release prepared=incative descriptors
				else break;
			}
			else if(next == dsc_TX.last_prep) { 
				// all prepared dsc's released: set tail = last_prep and last_prep = NULL
				if(next->next == NULL) { err = -25; break; } // ring-buffer cannot be NULL
				else if(next->next->buffer != NULL) { err = -26; break; } // used buffer in next dsc?
				else {
					//dsc_TX.tail = dsc_TX.last_prep; // tail != NULL avoids that for another irq verify returns -1
					dsc_TX.tail = NULL; // all dsc's released
					dsc_TX.last_prep = NULL;
					//mem_TX.next = mem_TX.first; // reset with ioctl
				}
				break;
			}
			
			next = next->next;

			if((num > DSC_TX_NUM) || (next == NULL) /*|| (a_bytes % DIO_BYTES_PER_SAMPLE)*/) { err = -20; break; } // wrong tail or not full sample sent
		} // next loop
		if((err >= 0) && (num == 0)) err = WARN_NO_DATA;	// nothing done?
	}

	// update global byte counter and stop TX if sufficient bytes transmitted
	// this calls verify_TX(true) again if DMA_CTRL_ACTIVE_TX
	status.TX_bt_tot += a_bytes;
	status.err_TX = err;

	if(err < 0) pr_err(NAME "verify_TX dsc %3d: error %d\n", num, err);	
	else if(err == 0) {
		status.dsc_TX_c = num;
		status.dsc_TX_a -= num;
		//pr_err(NAME "verify_TX dsc %3d: %u bytes act %u (%p) ok\n", num, a_bytes, status.dsc_TX_a, dsc_TX.head->buffer);
	}


	return err;
}

// verify completed RX descriptors, count status.RX_bt_tot and update buffer bytes
// increments status.RX_bt_tot/a_bytes completed bytes and sets dsc_RX.head to first non-completed dsc.
// if release == true releases all not completed dsc's until dsc_RX.last_prep.
// resets DMA_CTRL_ACTIVE_RX bit in status.ctrl_DMA if no dsc's are active
// returns 0 if ok, >0 if warning, <0 error
// ATTENTION: must be called with user_mutex locked!
// notes:
// - starts verification from dsc_RX.head
// - stops at the first non-completed dsc or at dsc_RX.tail (!release) or dsc_RX.last_prep (if not NULL and release).
// - dsc_RX.head and tail can be the same descriptor.
// - if release sets buffer bytes to 0L and removes association of buffer with dsc's.
// - start and stop bits are set by DMA in status register
int verify_RX(bool release) {
	int err = 0, num = 0;
	uint32_t a_bytes = 0, offset;
	uint8_t *p;
	struct dsc_info *next;
	struct SG_dsc *dsc = NULL;
	struct mem_info * mem = NULL, *last_c = NULL;
	bool cyclic = (status.ctrl_DMA & DMA_CTRL_CYCLIC_RX) ? true : false;

	//pr_err(NAME "verify_RX: [%p,%p,%p] ...\n", dsc_RX.head, dsc_RX.tail, dsc_RX.last_prep);
	//pr_err(NAME "verify_RX\n");
	//show_dsc("verify_RX", &dsc_RX, false);
	//test(4L, false);	

	next = dsc_RX.head; // first dsc, cannot be NULL
	if(next == NULL) err = -1;
	else if((dsc_RX.tail == NULL) || !(status.ctrl_DMA & DMA_CTRL_ACTIVE_RX)) err = release ? 0 : WARN_NO_DATA; // nothing todo! (DMA_CTRL_ACTIVE_RX is reset below)
	else {
		while(true) {
			// get descriptor
			dsc = GET_ALIGNED_DSC(next->virt_addr);	// aligned virtual descriptor
			if(dsc == NULL) { err = -10; break; } // ensure dsc is not NULL
			
			mem = next->buffer;
			if(mem == NULL) { err = -11; break; } // ensure buffer is not NULL
					
			if(mem->ref_cnt != 1) { err = -12; break; } // wrong buffer reference count

			if(dsc->status & SG_S2MM_STATUS_COMPLETE) { 
				// descriptor is completed
				if((dsc->status & SG_S2MM_STATUS_BYTES) > (dsc->control & SG_S2MM_CTRL_BYTES)) { 
					pr_err(NAME "verify_RX dsc %2d/%p: %4u>%4u/%4u bts>max/tot (error)\n", 
						num, dsc, 
						(dsc->status & SG_S2MM_STATUS_BYTES), (dsc->control & SG_S2MM_CTRL_BYTES), 
						a_bytes);
					err = -14; 
					break; 
				}
				else {
					// descriptor ok: count and update number of received bytes
					a_bytes += (dsc->status & SG_S2MM_STATUS_BYTES);	
					status.RD_bt_act += (dsc->status & SG_S2MM_STATUS_BYTES);
					mem->bytes = dsc->status & SG_S2MM_STATUS_BYTES;
					// count number of completed dsc
					++num;
					// save last completed buffer
					last_c = mem;
					//pr_err(NAME "verify_RX %d dsc, %u bytes (1)\n", num, a_bytes);
				}
			}
			else {
				// running but not completed: set head to first not completed descriptor
				dsc_RX.head = next;
				if (cyclic) mem_RX.next = mem; // in cyclic mode save next not completed buffer
				break;
			}

			if (cyclic) { 
				// cyclic mode: reset dsc and if buffer full drop oldest unread buffer(s)
				dsc->status = 0L;
				while(status.RD_bt_act > (DSC_RX_FULL*DMA_BUF_SIZE)) { // drop oldest unread buffer(s)
					status.RD_bt_act -= mem_RX.first->bytes;
					status.RD_bt_drop += mem_RX.first->bytes;
					mem_RX.first->bytes = 0;
					mem_RX.first = mem_RX.first->next;
				}
			}
			else {
				// reset buffer reference count
				mem->ref_cnt = 0;
				// invalidate buffer
				next->buffer = NULL;

				// invalidate descriptor
				dsc->address_low = 0L;
				dsc->status = dsc->control = 0L;

				if(next == dsc_RX.tail) {
					if( (dsc_RX.last_prep == NULL) && (mem->next != mem_RX.next)) { err = -13; break; } // wrong next buffer?
					// all descriptors completed: set head to tail->next and reset active flag
					//TODO: I think next statement is not true!? but it indicates that DMA went idle which might be a problem
					// for running and not completed dsc's we end up here only if release = true
					// and we can assume that verify_RX(true) was called by stop_RX
					if(next->next == NULL) err = -15; // ring-buffer cannot be NULL
					else dsc_RX.head = next->next;
					status.ctrl_DMA &= ~DMA_CTRL_ACTIVE_RX;
					break;
				}
				else if(next == dsc_RX.last_prep) { err = -16; /*break;*/ } // last_prep completed? (TODO & ENOMEM fix: see Verify_TX error -24)
			}
			
			next = next->next;

			if((num > DSC_RX_NUM) || (next == NULL) /*|| (a_bytes % DIO_BYTES_PER_SAMPLE)*/) { err = -20; break; } // wrong tail or not full sample received
		} // next loop
		if((!err) && (num == 0) && (!release)) err = WARN_NO_DATA; // nothing done
	}
	
	if(release && (!err)) { // release all buffers dsc_RX.head .. dsc_RX.last_prep
		if (status.ctrl_DMA & DMA_CTRL_ACTIVE_RX) err = -30; // RX DMA must be inactive
		else if (dsc_RX.head == NULL) err = -31; // cannot be NULL
		else {
			next = dsc_RX.head; // first not compleded dsc
			while(true) {
				dsc = GET_ALIGNED_DSC(next->virt_addr);	// aligned virtual descriptor
				if(dsc == NULL) { err = -32; break; } // ensure dsc is not NULL
				if(dsc->status & SG_S2MM_STATUS_COMPLETE) { // dsc completed when DMA not running? 
					// note:
					// we get this when stop_RX has called reset_RX since RX was not in idle state (i.e. tail not reached)
					// verify_RX(release=true) is called only from stop_RX after is stopped for sure
					// so we can ignore this error, otherwise we get a huge memory leak (ENOMEM).
					// the completed dsc might contain valid data, but we ignore this here.
					// we change here error code from -33 to +33 as a warning and do not overwrite old errors.
					if(!err) err = 33; 
				}
				//else mem_RX.next = next->buffer; // save first not completed buffer [not needed]

				mem = next->buffer;
				if(mem == NULL) break; //{ err = -34; break; } // ensure buffer is not NULL?

				// reset buffer reference count
				mem->ref_cnt = 0;
				// invalidate buffer
				next->buffer = NULL;

				// invalidate descriptor
				dsc->address_low = 0L;
				dsc->status = dsc->control = 0L;
				
				// check if is last prepared buffer
				if(next == dsc_RX.last_prep) {
					if (mem->next != mem_RX.next) err = -35; // wrong next buffer?
					if(next->next == NULL) { err = -36; break; } // ring-buffer cannot be NULL
					else if(next->next->buffer != NULL) { err = -37; break; } // used buffer in next dsc?
					else {
						//dsc_RX.tail = dsc_RX.last_prep; // tail != NULL avoids that for another irq verify returns -1
						dsc_RX.tail = NULL; // if tail=last_prep get error -32 in prepare_TX_dsc
						dsc_RX.last_prep = NULL;
						//mem_RX.next = mem_RX.first; // reset with ioctl
					}
					break;
				}
				next = next->next;
			}
		}
	}
	
	// update transmitted byte counter
	status.RX_bt_tot += a_bytes;

	if (last_c) {	// save last completed sample
		offset = (status.RX_bt_tot % DIO_BYTES_PER_SAMPLE) + DIO_BYTES_PER_SAMPLE;
		if(last_c->bytes >= offset) {
			p = ((char*)GET_ALIGNED_BUFFER(last_c->virt_addr)) + (last_c->bytes-offset);
			for (offset = 0; offset < DIO_BYTES_PER_SAMPLE; ++offset) status.last_sample.data8[offset] = *p++;
		}
	}

	if (err != 0) status.err_RX = err;

	if(err < 0) pr_err(NAME "verify_RX dsc %3d: error %d\n", num, err);
	else {	
		status.dsc_RX_c = num;
		status.dsc_RX_a -= num;
		//pr_err(NAME "verify_RX dsc %3d: %u bytes act %u ok\n", num, a_bytes, status.RX_bt_tot);
	}

	if (!release) {
		status.debug[DBG_OFF_RX_VERIFY+status.debug_count] = (num << 16) | a_bytes;
	}

	return err;
}


// prepares next TX descriptors
// returns 0 if ok, >0 if warning, <0 error
// ATTENTION: must be called with user_mutex locked!
// notes:
// - this is typically called from irq_hdl AFTER next DMA is started
//   but it can be also called from start_TX to prepare first DMA. 
//   do not call from IOCTL or write frunctions directly.
// - function prepares maximum half of DSC_TX_NUM. this allows start_TX to faster call start_TX_SG
//   and then again prepare_TX_dsc to prepare second half.
// - [head..tail] (inclusive) = active descriptors (must not be touched)
//   [tail->next..[head (exclusive) = not-active descriptors (update here)
//   if head == tail->next then no active descriptors. 
//   last_prep must be NULL initially, will be set to last prepared descriptor
// - [mem_TX.first..[mem_TX.next (exclusive) = active or already prepared buffers
//   [mem_TX.next..mem_TX.last] (inclusive) = next buffers to prepare
//   mem_TX.next will be set to next buffer to prepare after function returns. NULL when all prepared.
// - DSC_PACKET (can be 1) descriptors are grouped together as one packet with 
//   first descriptors with start bit set and last descriptor end bit set.
//   each packet generates one TX IRQ when completed. The packet size does not matter.
int prepare_TX_dsc(void) {
	int err = 0, num = 0;
	struct mem_info *mem = NULL;
	struct dsc_info *first, *next, *last;
	struct SG_dsc *dsc = NULL;
	// TX DMA must be enabled
	if((status.ctrl_DMA & DMA_CTRL_ENABLE_TX) == 0) err = WARN_NOT_ENABLED; 
	else {
		//pr_err(NAME "prepare_TX\n");
		//pr_err(NAME "prepare_TX: dsc [%p,%p,%p]\n", dsc_TX.head, dsc_TX.tail, dsc_TX.last_prep);
		//pr_err(NAME "prepare_TX: mem [%p,%p,%p]\n", mem_TX.first, mem_TX.next, mem_TX.last);

		// allocate descriptors for the first time
		// note: this sets dsc_TX.tail->next = dsc_TX.head (and dsc_TX.last_prep = NULL)
		if(dsc_TX.head == NULL) {
			dsc_TX.head = allocate_dsc(DSC_TX_NUM, DBG_TX_DSC);	// we check for NULL later
			dsc_TX.tail = dsc_TX.last_prep = NULL; 	// this indicates no dsc is running
		}

		// get first active and inactive descriptors, last_prep must be NULL
		// note:
		// it happens that tail->next == head, then all dsc's are active and we cannot prepare anything.
		// this should never be the case but could be explained that more dsc's are verified than for which IRQ was generated
		// then another IRQ is coming but verify_RX does not find any dsc to verify.
		// and following start_TX_SG will start all available dsc's.
		// and the following prepare_TX_dsc will find tail->next = head.
		first = dsc_TX.head; 	// first active (don't touch! unless head == tail->next)
		next = dsc_TX.tail; 	// last active, NULL if stopped
		last = dsc_TX.last_prep; // last prepared, must be NULL
		if(first == NULL) err = -ERROR_NO_MEM; // allocation failed above?
		else if(last != NULL) err = WARN_ALREADY_DONE; // there are prepared dsc's
		else {
			if(status.ctrl_DMA & DMA_CTRL_ACTIVE_TX) { // dsc's are running: start with tail->next
				if(next == NULL) err = -12; // when dsc's are active tail must not be NULL
				else {
					next = next->next; // start with next inactive dsc
					if(next == NULL) err = -13; // in ring-buffer cannot be NULL
					else if(next == first) {
						err = WARN_ALL_ACTIVE; // all dsc are active: do not prepare anything
						//pr_err(NAME "prepare_TX_dsc: %d (%d) all active!\n", num, err);
					}
				}
			}
			else { // no running dsc's
				next = first; // start with first dsc
			}
			if(!err) {
				// get first unprepared buffer
				// if NULL then at end of buffer:
		 		// - restart DMA from beginning if repetitions are active and not completed
				// - otherwise return with last == NULL
				mem = mem_TX.next;
				if(mem == NULL) {
					if((status.reps_set == 0) || (status.reps_act < status.reps_set)) {
						++status.reps_act;
						mem = mem_TX.first;
					}
				}
				if(!mem) { 
					//pr_err(NAME "prepare_TX: no buffers (ok)\n");
					err = WARN_NO_DATA;
				}
				else {
					// loop over each descriptor:
					// - if buffer available set address and size and reset status
					// - stop if no more buffers available or half of dsc filled
			  		// - last contains last descriptor with new buffer
					// - if next == first then no active DMA is running
					do {
						// get descriptor
						dsc = GET_ALIGNED_DSC(next->virt_addr);	// aligned virtual descriptor

						// check if descriptor is used
						if((next->buffer != NULL) || (dsc->address_low != 0L)) { err = -21; break; }

						// save buffer and increment reference count
						next->buffer = mem;
						++mem->ref_cnt;
						
						// set descriptor
						// dsc_address_low must be DATA_WIDTH_ALIGN aligned
						// dsc control is set to buffer size and might have start or end bit set.
						// dsc status is reset and receives transferred bytes and completion bit
						dsc->address_low = GET_ALIGNED_PHYS_BUFFER(mem->phys_addr);		
						dsc->control = mem->bytes;
						dsc->status = 0;

						// packet buffer counter
						if(++p_count == 1) { // set start bit
							dsc->control |= SG_MM2S_CTRL_START;
						}
						else if (p_count >= DSC_PACKET) { // set end bit
							p_count = 0;
							dsc->control |= SG_MM2S_CTRL_END;
						}

						// save last descriptor which contains new buffer
						last = next;

						// next buffer. restart from beginning if repetitions are active and not completed.
						mem = mem->next;
						if ( mem == NULL ) {
							status.reps_act++;
							if((status.reps_set == 0) || (status.reps_act < status.reps_set)) mem = mem_TX.first;
						}

						// next descriptor
						next = next->next;
						// last->next can never point to tail!
						if(next == dsc_TX.tail) { err = -23; break; }

						// count number of prepared dscs
						++num;
					} while ((mem != NULL) && (next != first) && (num < (DSC_TX_NUM >> 1))); // next loop
					
					if(err >= 0) {
						// set stop bit of last descriptor
						// note: doing this only for mem == NULL ensures that PACKET_DSC is maintained over several calls of prepare_TX_dsc
						//       even if less dsc's were completed (e.g. for last TX buffer).
						if (mem == NULL) {
							dsc->control |= SG_MM2S_CTRL_END;
							p_count = 0; // reset packet buffer count (next starts with start bit)
						}

						// set last prepared descriptor (will become tail after start_TX_SG)
						dsc_TX.last_prep = last;

						// set next buffer to prepare the next time. NULL if all are prepared.
						mem_TX.next = mem;
					}
					//show_dsc("prepare_TX_dsc status", &dsc_TX, true);	
				}
			}
		}
	}

	status.err_TX = err;
	status.dsc_TX_p += num;

	if(err < 0) pr_err(NAME "prepare_TX_dsc: %d (%d) error!\n", num, err);
	//else pr_err(NAME "prepare_TX_dsc: %d ok (%d)\n", num, err);

	//check_dsc(&dsc_TX, true);

	return err;
}

// check and prepares next RX descriptors
// returns 0 if ok, >0 if warning, <0 error
// ATTENTION: must be called with user_mutex locked!
// notes: 
// notes:
// - this is typically called from irq_hdl AFTER next DMA is started
//   but it can be also called from start_TX to prepare first DMA. 
//   do not call from IOCTL or write frunctions directly.
// - function always tries to prepare DSC_RX_NUM/2 dsc's, which ensures that DSC_RX_NUM dsc's
//   are prepared. start_RX can faster call start_RX_SG since only half of the dsc's are prepared,
//   and in successive calls all DSC_RX_NUM's will be used since not all dsc's will be filled per IRQ/packet.
// - [dsc_RX.head..tail] (inclusive) = active descriptors (must not be touched)
//   [dsc_RX.tail->next..[head (exclusive) = not-active descriptors (update here)
//   if dsc_RX.head == dsc_RX.tail->next then no active descriptors. 
//   dsc_RX.last_prep must be NULL initially, will be set to last prepared descriptor
// - [mem_RX.first..[mem_RX.next (exclusive) = active or already prepared buffers
//   [mem_RX.next..mem_RX.last] (inclusive) = next buffers to prepare
//   mem_RX.next will be set to next buffer to prepare after function returns. NULL when all prepared.
// - DSC_PACKET (can be 1) descriptors are grouped together as one packet with 
//   first descriptors with start bit set and last descriptor end bit set.
//   each packet generates one RX IRQ when completed. The packet size does not matter.
// - the RX function does not set start and stop bits for packets. these are set by the DMA hardware.
// TODO:
// - if mem_RX.next == NULL then all RX buffers are completed or prepared.
//   function will start to use oldest completed buffers if there are available - like in a ring-buffer.
//   this will OVERWRITE not read data!
// - at the moment we do not allow reallocation after DMA is running!
int prepare_RX_dsc(void) {
	int err = 0, num = 0, drop = 0;
	struct dsc_info *first, *next, *last;
	struct SG_dsc *dsc = NULL;
	struct mem_info *mem = mem_RX.next ? mem_RX.next : mem_RX.first;

	// RX DMA must be enabled and buffers prepared
	if((status.ctrl_DMA & DMA_CTRL_ENABLE_RX) == 0) err = WARN_NOT_ENABLED; 
	else if(mem == NULL) err = -ERROR_NO_DATA;
	else if (status.dsc_RX_a >= (DSC_RX_ACTIVE+DSC_PACKET)) err = WARN_ALL_ACTIVE;	// there are enough active dsc's
	else {

		// allocate descriptors for the first time
		if(dsc_RX.head == NULL) {
			dsc_RX.head = allocate_dsc(DSC_RX_NUM, DBG_RX_DSC);	// we check for NULL later
			dsc_RX.tail = dsc_RX.last_prep = NULL; 	// this indicates no dsc is running
		}

		// get first active and inactive descriptors, last_prep must be NULL
		// note:
		// it happens that tail->next == head, then all dsc's are active and we cannot prepare anything.
		// this should never be the case but could be explained that more dsc's are verified than for which IRQ was generated
		// then another IRQ is coming but verify_RX does not find any dsc to verify.
		// and following start_RX_SG will start all available dsc's.
		// and the following prepare_RX_dsc will find tail->next = head.
		first = dsc_RX.head; 	// first active (don't touch! unless head == tail->next)
		next = dsc_RX.tail; // last active, NULL if stopped
		last = dsc_RX.last_prep; // last prepared, must be NULL
		if(first == NULL) err = -ERROR_NO_MEM; // allocation failed above?
		else if(last != NULL) err = WARN_ALREADY_DONE;	// there are prepared dsc's
		else {
			if(status.ctrl_DMA & DMA_CTRL_ACTIVE_RX) { // dsc's are running
				if(next == NULL) err = -12; // when dsc's are active tail must not be NULL
				else {
					next = next->next; // start with next inactive dsc
					if(next == NULL) err = -13; // in ring-buffer cannot be NULL
					else if(next == first) err = WARN_ALL_ACTIVE; // all dsc are active: do not prepare anything
				}
			}
			else { // no running dsc's
				//dsc_RX.tail = NULL; // avoid error -32
				next = first; // start with first dsc
			}
			if(!err) {
				// get first unprepared buffer (NULL initially)
				//mem = mem_RX.next ? mem_RX.next : mem_RX.first;
				// set start bit of first unprepared descriptor
				//dsc = GET_ALIGNED_DSC(next->virt_addr);	// aligned virtual descriptor
				//dsc->control |= SG_S2MM_CTRL_START;

				// loop over each descriptor:
				// - set buffer address and size and reset status
				// - stop if half of descriptors prepared or if active descriptors (head) reached
		  		// - last contains last descriptor with new buffer
				do {
					// drop oldest completed un-read buffer if needed
					if (mem == mem_RX.first) { // all buffers prepared
						if (status.RD_bt_act > 0) { // status.RD_bt_act == 0: first time with nothing to drop
							//pr_err(NAME "prepare_RX_dsc: drop 1 buffer %d %p %p\n", status.RD_bt_act, mem_RX.first, mem_RX.next);
							err = copy_RX(NULL, DMA_BUF_SIZE); // returns number of copied bytes
							if(err <= 0) { err = -20; break; }
							else err = 0;
							++drop;
						}
					}

					// get descriptor
					dsc = GET_ALIGNED_DSC(next->virt_addr);	// aligned virtual descriptor
					
					// check if descriptor is used
					if((next->buffer != NULL) || (dsc->address_low != 0L)) { 
						pr_err(NAME "info/dsc %p/%p buf/addr %p/%08x\n", next, dsc, next->buffer, dsc->address_low);
						err = -21; 
						break; 
					}

					if(mem == NULL) { err = -23; break; } // cannot be NULL in ring-buffer
					else if (mem->ref_cnt > 0) { err = -24; break; } // buffer already used!?
	
					// save buffer and increment reference count
					next->buffer = mem;
					++mem->ref_cnt;

					// set max. buffer length to allocated size or 0L?
					//mem->bytes = DMA_BUF_SIZE;

					// set descriptor
					// dsc_address_low must be DATA_WIDTH_ALIGN aligned
					// dsc control is set to buffer size.
					// dsc status is reset and receives transferred bytes and completion bit
					// and should receive start or end bit set by dma.
					dsc->address_low = GET_ALIGNED_PHYS_BUFFER(mem->phys_addr);		
					dsc->control = DMA_BUF_SIZE;
					dsc->status = 0;
					// save last descriptor which contains new buffer
					last = next;

					// next buffer and descriptor
					mem = mem->next;
					next = next->next;

					// last_prep->next can never point to tail! (except after first allocation of dsc's)
					// but last_prep->next can point to head!
					if(next == dsc_RX.tail) { err = -32; break; }

					// if not in cyclic mode stop if DSC_RX_NUM/2 dsc's active
					// TODO: in cyclic mode stops if next == first, i.e. all dsc's. better would be when all RX buffers used.
					if ((++num >= (DSC_RX_ACTIVE+DSC_PACKET-status.dsc_RX_a)) && !(status.ctrl_DMA & DMA_CTRL_CYCLIC_RX)) break;
				} while (next != first); //&& ( mem != mem_RX.first )); // next loop
			
				if(err >= 0) {
					// set last prepared descriptor (will become tail after start_RX_SG)
					dsc_RX.last_prep = last;

					// set next buffer to prepare the next time.
					mem_RX.next = mem;
				}
				//show_dsc("prepare_RX_dsc status", &dsc_RX, false);	
			}
		}
	}		
	status.err_RX = err;
	status.dsc_RX_p += num;

	if(err < 0) pr_err(NAME "prepare_RX_dsc: %d dsc (%d) error!\n", num, err);
	//else pr_err(NAME "prepare_RX_dsc: %d d/a/c %u/%u/%u (%d)\n", num, drop, status.dsc_RX_a, status.dsc_RX_c, err);

	status.debug[DBG_OFF_RX_PREPARE+status.debug_count] = (drop << 24) | (num << 16) | (status.dsc_RX_a << 8) | status.dsc_RX_c;

	return err;
}

// start DMA TX transfer
// data buffers must have been prepared with prepare_TX_buffers
// returns 0 if ok, >0 if warning, <0 error
// ATTENTION: must be called with user_mutex locked!
// notes: 
// - this is called from IOCTL and irq_hdl
// - reset mem_RT.next to proper starting buffer!
int start_TX(void) {
	int err = 0;

	//pr_err(NAME "start_TX\n");

	if(status.ctrl_DMA & DMA_CTRL_ACTIVE_TX) err = WARN_ALREADY_DONE;	// DMA is already running!
	else if(mem_TX.next == NULL) err = -ERROR_NO_DATA; // no buffers prepared
	else {
		// ensure buffers are multiple of DMA_BUF_SIZE and time is incremental
		err = check_mem(&mem_TX, false, false); // TODO: temporarily timing check disabled!
		if(!err) {
			// reset sample counter
			status.TX_bt_tot = 0;
			// reset packet buffer count (next starts with start bit)
			p_count = 0;
			// enable TX
			status.ctrl_DMA |= DMA_CTRL_ENABLE_TX;
			// prepare descriptors
			// we start preparing at actual dsc_TX.next pointer
			//pr_err(NAME "start_TX: prepare_TX_dsc\n");
			// returns dsc_TX.last_prep == NULL when no descriptors are ready
			err = prepare_TX_dsc();
			if((err >= 0) && (dsc_TX.last_prep != NULL)) {
				//pr_err(NAME "start_TX: start_TX_SG\n");
                
//check_dsc(&dsc_TX, "start_TX (before start)");
//check_mem(&mem_TX, true, false);

				// start DMA on TX channel. dsc_TX.last = NULL afterwards
				err = start_TX_SG();
				if(err >= 0) {
					// ok: we wait until completion IRQ
					// prepare new descriptors if buffers available
					err = prepare_TX_dsc();

				}
			}
		}
	}
	if (err < 0) pr_err(NAME "start_TX error %d!\n", err);
	//else pr_err(NAME "start_TX ok (%d)\n", err);
	status.err_TX = err;

//check_dsc(&dsc_TX, "start_TX (after start)");
//check_mem(&mem_TX, true, false);

	return err;
}

// start DMA RX transfer
// data buffers must have been prepared with prepare_TX_buffers
// returns 0 if ok, >0 if warning, <0 error
// ATTENTION: must be called with user_mutex locked!
// notes: 
// - this is called from IOCTL and irq_hdl
// - reset mem_RX.next to proper receiving buffer!
int start_RX(void) {
	int err = 0;

	//pr_err(NAME "start_RX\n");

	if(status.ctrl_DMA & DMA_CTRL_ACTIVE_RX) err = WARN_ALREADY_DONE; // DMA is already running!
	else if(mem_RX.first == NULL) err = -ERROR_NO_DATA; // no buffers prepared
	else {
		// reset bytes counter
		status.RX_bt_tot = status.RD_bt_act = 0;
		// enable RX
		status.ctrl_DMA |= DMA_CTRL_ENABLE_RX;
		// prepare descriptors
		// returns dsc_RX.last_prep == NULL when no descriptors are ready
		err = prepare_RX_dsc();
		if((err >= 0) && (dsc_RX.last_prep != NULL)) {

//check_dsc(&dsc_RX, "start_RX (before start)");
//check_mem(&mem_RX, true, false);

			// start DMA on RX channel
			err = start_RX_SG();
			if(err >= 0) {
				// ok: we wait until completion IRQ
				// prepare new descriptors if buffers available
				//err = prepare_RX_dsc();

			}
		}
	}
	if (err < 0) pr_err(NAME "start_RX error %d!\n", err);
	//else pr_err(NAME "start_RX ok (%d)\n", err);
	status.err_RX = err;

//check_dsc(&dsc_RX, "start_RX (after start)");
//check_mem(&mem_RX, true, false);

	return err;
}

// append NOP samples to last buffer if needed
// last buffer size must be multiple of DIO_BYTES_PER_SAMPLE but does not need to be multiple of DMA_BUF_MULT
// on success last buffer size is also multiple of DMA_BUF_MULT with NOP samples appended.
// updates status.bt_tot and sets always status.set_samples
// returns 0 if ok, otherwise error
long append_TX(void) {
	long i, result = status.bt_tot % DMA_BUF_MULT;
	uint32_t *p_copy, t_old;
	struct mem_info *last = NULL;
	if (result != 0) { // add result bytes to have total number of bytes multiple of DMA_BUF_MULT (which is multiple of DIO_BYTES_PER_SAMPLE)
		result = DMA_BUF_MULT - result;
		// get last TX buffer (cannot be NULL)
		last = mem_TX.last;
		if (last == NULL) result = -1;
		else if (last->virt_addr == NULL) result = -2;
		else if ((last->bytes == 0) || (last->bytes % DIO_BYTES_PER_SAMPLE)) result = -3;
		else {
			// get last time (size needs to be multiple of DIO_BYTES_PER_SAMPLE and cannot be 0)
			p_copy = GET_ALIGNED_BUFFER(last->virt_addr);
			t_old = p_copy[((last->bytes/DIO_BYTES_PER_SAMPLE)-1)*(DIO_BYTES_PER_SAMPLE/4)];
			
			// check if has sufficient size to add result bytes
			if (result > (DMA_BUF_SIZE - last->bytes)) { // no space: allocate new buffer
				if(last->bytes % DMA_BUF_MULT) result = -EWOULDBLOCK; // previous buffer length invalid! (should not happen)
				else {
					last = last->next = get_mem(DBG_TX_BUF);
					if (last == NULL) result = -ENOMEM;
					else p_copy = GET_ALIGNED_BUFFER(last->virt_addr);
				}
			}
			if (result > 0) { // append result bytes to previous or new buffer
				p_copy += (last->bytes/4);
				for(i = 0; i < result; i += DIO_BYTES_PER_SAMPLE) {
					*p_copy++ = ++t_old;
#if DIO_BYTES_PER_SAMPLE == 8
					*p_copy++ = (1<<DIO_BIT_NOP);
#elif DIO_BYTES_PER_SAMPLE == 12
					*p_copy++ = (1<<DIO_BIT_NOP);
					*p_copy++ = (1<<DIO_BIT_NOP);
#endif
				}
				//pr_err(NAME "append_TX %ld samples @ %lu us\n", result/DIO_BYTES_PER_SAMPLE, t_old - result/DIO_BYTES_PER_SAMPLE);
				// update buffer and total bytes
				last->bytes += result;
				status.bt_tot += result;
				result = 0;
			}
		}
	}
	// always update total number of samples
	if (result == 0) status.set_samples = status.bt_tot / DIO_BYTES_PER_SAMPLE;
	return result;
}

// copies user buffer of length bytes into list mem_TX of TX DMA buffers
// updates status.bt_tot by length bytes
// returns number of written bytes if ok, <=0 on error
// ATTENTION: must be called with user_mutex locked!
// notes
// - allows arbitrary input length. appends and fills last buffer and adds and fills new buffers.
//   last buffer is filled with remaining bytes without sappending NOPs (done by DMA24_IOCTL_START).
// - assumes that data in buffer is sorted in time and that each consecutive buffer is also consecutive in time.
// - user buffer must have been checked with access_ok!
// TODO: 
// - this copies user buffer. maybe we can do it without copying?
//   there will be IOCTL commands to get kernel buffers for user to write and to submit back.
//   but then we cannot combine user buffers for better efficiency! maybe ensure size is maximum!
ssize_t prepare_TX_buffers(const char __user *buffer, size_t length) {
	ssize_t bytes = length, b_copy = 0, b_size = DMA_BUF_SIZE;
	struct mem_info *first = NULL, *last = NULL;
	char *p_copy = NULL;
	bool append = false;

	if ((length == 0) || (buffer == NULL) /*|| (length % DIO_BYTES_PER_SAMPLE)*/) bytes = -EINVAL;
	else {
//pr_err(NAME "prep_TX_buf bytes %u # %u\n", length, status.bt_tot);udelay(1000);
		// append list if is not empty
		if(mem_TX.last) {
			first = mem_TX.first;
			last = mem_TX.last;
			// if previous buffer has at least a single byte space we add to this buffer
			// this is necessary to ensure buffer is filled with multiple of DMA_BUF_MULT bytes
			if ( (mem_TX.last->bytes + 1) <= DMA_BUF_SIZE ) {
				append = true;
				b_size = DMA_BUF_SIZE - last->bytes;
			}
		}
		// in each loop we copy maximum DMA_BUF_SIZE byte into DMA buffer
		// we ensure that copied bytes is multiple of DMA_BUF_MULT
		for(; bytes > 0; buffer += b_copy, bytes -= b_copy) {
			// get bytes to copy and round down to multiple of DMA_BUF_MULT
			b_copy = (bytes >= b_size) ? b_size : bytes;
			if (append) { // append to last buffer (only first time)
				append = false;
				b_size = DMA_BUF_SIZE;
				p_copy = ((char*)GET_ALIGNED_BUFFER(last->virt_addr)) + last->bytes;
				//pr_err(NAME "prep_TX_buf %u/%u bytes (append)\n", b_copy, last->bytes + b_copy);
				last->bytes += b_copy;
			}
			else {	// allocate new buffer
				if(last) last = last->next = get_mem(DBG_TX_BUF);
				else last = first = get_mem(DBG_TX_BUF);	// first entry in list
				if(last == NULL) { bytes = -ERROR_NO_MEM; break; } // out of memory
				p_copy = (char*)GET_ALIGNED_BUFFER(last->virt_addr);
				last->bytes = b_copy;
				//pr_err(NAME "prep_TX_buf %u bytes\n", b_copy);
			}
			// copy user data into TX buffer
			if(__copy_from_user(p_copy, buffer, b_copy) != 0) { bytes = -EFAULT; break; }
		} // next loop

		// update mem_TX list or free on error
		if(bytes < 0) {
			if(mem_TX.first == NULL) free_mem_no_pool(first, DBG_TX_BUF);
			else free_mem_no_pool(mem_TX.first, DBG_TX_BUF);
			mem_TX.first = mem_TX.last = mem_TX.next = NULL;
		}
		else {
			b_copy = length - bytes; // true number of copied bytes
			if(mem_TX.first == NULL) {
				// first buffers, no DMA is running
				mem_TX.first = mem_TX.next = first;
				mem_TX.last = last;
				// update total number of TX bytes
				status.bt_tot = b_copy;
			}
			else {
				// append new buffers to already existing buffers
				//mem_TX.last->next = first; (already done)
				mem_TX.last = last;
				// new buffers will be processed after previous are finished
				// mem_TX.next is NULL when DMA has already been started on all old buffers
				if(mem_TX.next == NULL) mem_TX.next = first;
				// update total number of TX bytes
				status.bt_tot += b_copy;
			}
		}
	}
	
	// check validity of buffers (for debugging)
	if (bytes >= 0)	bytes = check_mem(&mem_TX, false, false);
	if (bytes < 0) {
		pr_err(NAME "prep_TX_buf error %d\n", bytes);
		status.err_TX = bytes;
	}
	else {
		//pr_err(NAME "prep_TX_buf bytes %u/%u tot %u\n", b_copy, length, status.bt_tot);udelay(1000);
		bytes = b_copy;
	}

	return bytes;
}

// prepares list mem_RX of RX DMA buffers to have at least total length bytes available
// if shrink=true then a larger existing buffer is reduced in size, otherwise not.
// returns number of total bytes in RX buffers if ok, <=0 on error
// ATTENTION: must be called with user_mutex locked!
// notes: 
// - length must be multiple of 8 otherwise returns error!
// - shrink=True option can only be called when DMA is not running, otherwise returns error.
// TODO: 
// - at the moment we allow to call this ONLY when DMA is not running. 
//   otherwise its not clear where to insert new buffers when all existing buffers were used (ref_cnt >0)
// - for simplicity I also use mem_RX.last to save pointer where to insert next buffer
//   everywhere else its not updated anymore!
// - mem_RX is used as ring-buffer while mem_TX is not. this is a bit inconsistent.
ssize_t prepare_RX_buffers(size_t length, bool shrink) {
	ssize_t bytes = status.RD_bt_max;
	struct mem_info *first = NULL, *last = NULL;
//pr_err(NAME "prep_RX_buf bytes %u # %u\n", length, status.bt_tot);udelay(1000);
	if ( (length == 0) /*|| (length % DIO_BYTES_PER_SAMPLE)*/ ) bytes = -ERROR_INPUT;
	else if ( length > MAX_READ_SIZE ) bytes = -ENOMEM; // size too large
	else if ( status.ctrl_DMA & DMA_CTRL_ACTIVE_RX ) bytes = -ERROR_ILLEGAL_STATE; // TODO: DMA running!
	else if ( bytes < length ) {		// increase size of buffer
		first = get_mem(DBG_RX_BUF);	// allocate first buffer
		if(first == NULL) bytes = -ERROR_NO_MEM;
		else {
			last = first;
			last->bytes = 0; // changed: from MAX_BUFSIZE or remaining bytes to 0. same below

			// init first buffer with zeros
			memset(GET_ALIGNED_BUFFER(last->virt_addr), 0, DMA_BUF_SIZE);

			bytes += DMA_BUF_SIZE;
//if(bytes >= length) pr_err(NAME "prep_RX_buf %u bytes\n", bytes);
			// create additional buffers of max. DMA_BUF_SIZE bytes until length bytes reached
			while(bytes < length) {
//pr_err(NAME "prep_RX_buf %u bytes\n", bytes);
				last = last->next = get_mem(DBG_RX_BUF);	// allocate next buffer
				if(last == NULL) { bytes = -ERROR_NO_MEM; break; }
				last->bytes = 0;

				// init next buffer with zeros
				memset(GET_ALIGNED_BUFFER(last->virt_addr), 0, DMA_BUF_SIZE);

				bytes += DMA_BUF_SIZE;
			} // next loop
		}

		// if allocation of all buffers was ok, add to list of buffers, otherwise free already allocated buffers
		if(bytes <= 0) free_mem_no_pool(first, DBG_RX_BUF);
		else {
			if(mem_RX.first == NULL) {
				// first buffers, no DMA is running
				mem_RX.first = first;
				mem_RX.last = last;
				mem_RX.next = NULL;
			}
			else {
				// add new buffers to already existing buffers at first not used buffer
				// if all buffers are used we have aproblem!
				mem_RX.last->next = first;
				mem_RX.last = last;
				// new buffers will be processed after previous are finished
				// mem_RX.next is first when DMA has already been started on all old buffers
				if(mem_RX.next == mem_RX.first) mem_RX.next = first;
			}
			mem_RX.last->next = mem_RX.first;	// close ring-buffer
			status.RD_bt_max = bytes;		// update total number of RX samples
		}
	}
	else if ( shrink && (bytes > length)) { // shrink buffer to given length (rounded up to next DMA_BUF_SIZE)
		if ( status.ctrl_DMA & DMA_CTRL_ACTIVE_RX ) bytes = -ERROR_ILLEGAL_STATE; // DMA running!
		else if(first == NULL) bytes = -31; // cannot be NULL
		else {
			// decrement length for each existing buffer until <= MAX_BUFSIZE
			// we set next buffer to first in list to be sure it is valid
			// actual bytes in buffer is reset and we count available bytes.
			mem_RX.next = last = mem_RX.first;
			bytes = 0;
			status.RD_bt_act = 0;
			do {
				bytes += DMA_BUF_SIZE;
				if ( bytes >= length ) break;
				last = last->next;
			} while (last != mem_RX.first);
			status.RD_bt_max = bytes;		// update total number of RX samples

			// remove remaining buffers starting at first->next until mem_RX.last
			if (last != mem_RX.first) {
				free_mem_no_pool(last->next, DBG_RX_BUF);
				last->next = mem_RX.first;	// close ring-buffer
				mem_RX.last = last;
			}
		}
	}
	
	// check validity of all buffers (for debugging)
	if(bytes > 0) {
		if(check_mem(&mem_RX, false, false) < 0) bytes = -33;
	}
	if(bytes <= 0) {
		pr_err(NAME "prep_RX_buf error %d\n", bytes);
		status.err_RX = bytes;
	}
	else {
		//pr_err(NAME "prep_RX_buf bytes %u # %u\n", bytes, bytes/DIO_BYTES_PER_SAMPLE);udelay(1000);
	}

	return bytes;
}

// stop and reset FPGA/DMA transfer to clean state
// returns 0 if in reset state, otherwise error
// ATTENTION: must be called with user_mutex locked!
// call this when an error occurred to bring FPGA and DMA back to initial state!
int reset_all(void) {
	pr_err(NAME "reset_all\n");

    //check_dsc(&dsc_TX, "reset_all TX (before stop)");
	//check_mem(&mem_TX, true, false);
    //check_dsc(&dsc_RX, "reset_all RX (before stop)");
	//check_mem(&mem_RX, true, false);

    // ensure FPGA is stopped if was running before.
	stop_FPGA();

	// stop any running DMA transfer. if a channel is not in idle state we reset channel, otherwise we would get a timeout.
    // reset of one channel will also reset other, but we have to call both functions to ensure that verify_TX/RX is called to cleanup buffers and dsc's!
    // TODO: it is not clear under which conditions channels are in idle state? RX is always not idle?
	stop_TX(true);
	stop_RX(true);

    //check_dsc(&dsc_TX, "reset_all TX (before reset)");
	//check_mem(&mem_TX, true, false);
    //check_dsc(&dsc_RX, "reset_all RX (before reset)");
	//check_mem(&mem_RX, true, false);

	// reset FPGA (should not fail)
	status.err_FPGA = reset_FPGA();

	// reset TX and RX channel
	status.err_TX = reset_TX();
	status.err_RX = reset_RX();

    //check_dsc(&dsc_TX, "reset_all TX (after reset)");
	//check_mem(&mem_TX, true, false);
    //check_dsc(&dsc_RX, "reset_all RX (after reset)");
	//check_mem(&mem_RX, true, false);

	//pr_err(" *** " NAME "reset_all: bufs %u/%u/%u ***\n", debug_DMA_count[DBG_TX_BUF], debug_DMA_count[DBG_RX_BUF], debug_DMA_count[DBG_BUF_POOL]);
	//pr_err(" *** " NAME "reset_all: dscs %u/%u/%u ***\n", debug_DMA_count[DBG_TX_DSC], debug_DMA_count[DBG_RX_DSC], debug_DMA_count[DBG_TEST]);

	// free DMA buffers by inserting them back into pool
	// note: free_mem_no_pool takes >10 seconds if many buffers were allocated!
	//free_mem_no_pool(mem_TX.first, DBG_TX_BUF);
    //pr_err("free mem TX\n");
	free_mem(mem_TX.first, DBG_TX_BUF);
	mem_TX.first = mem_TX.last = mem_TX.next = NULL;
	//free_mem_no_pool(mem_RX.first, DBG_RX_BUF);
    //pr_err("free mem RX\n");
	free_mem(mem_RX.first, DBG_RX_BUF);
	mem_RX.first = mem_RX.last = mem_RX.next = NULL;
	if ((debug_DMA_count[DBG_TX_BUF] != 0) || (debug_DMA_count[DBG_RX_BUF] != 0)) 
		pr_err(" *** " NAME "reset_all: bufs %u/%u/%u (error) ***\n", debug_DMA_count[DBG_TX_BUF], debug_DMA_count[DBG_RX_BUF], debug_DMA_count[DBG_BUF_POOL]);
	//else 	
	//	pr_err(" *** " NAME "reset_all: bufs %u/%u/%u (ok) ***\n", debug_DMA_count[DBG_TX_BUF], debug_DMA_count[DBG_RX_BUF], debug_DMA_count[DBG_BUF_POOL]);

	// free descriptors (for descriptors there is no pool)
	free_dsc_no_pool(dsc_TX.head,DBG_TX_DSC);
	dsc_TX.head = dsc_TX.tail = dsc_TX.last_prep = NULL;
	free_dsc_no_pool(dsc_RX.head,DBG_RX_DSC);
	dsc_RX.head = dsc_RX.tail = dsc_RX.last_prep = NULL;
	if ((debug_DMA_count[DBG_TX_DSC] != 0) || (debug_DMA_count[DBG_RX_DSC] != 0)) 
		pr_err(" *** " NAME "reset_all: dscs %u/%u/%u (error) ***\n", debug_DMA_count[DBG_TX_DSC], debug_DMA_count[DBG_RX_DSC], debug_DMA_count[DBG_TEST]);
	//else 
	//	pr_err(" *** " NAME "reset_all: dscs %u/%u/%u (ok) ***\n", debug_DMA_count[DBG_TX_DSC], debug_DMA_count[DBG_RX_DSC], debug_DMA_count[DBG_TEST]);

	// free pool of DMA buffers (used now by RX + TX buffers)
	//free_mem_no_pool(mem_pool, DBG_BUF_POOL);
	//mem_pool = NULL;

	if (status.err_TX || status.err_RX || status.err_FPGA) pr_err(NAME "reset_all: error %d/%d\n", status.err_TX, status.err_RX);
	//else pr_err(NAME "reset_all: ok\n");

	// reset all values to 0 (mainly DMA section) and update FPGA section of status info since registers are not software reset.
	update_status(NULL, false, true);
    //status.set_cycles = 1;
	status.reps_set = 1;

	// free debug info
	//FREE_DEBUG();
	
    // returns always 0 since these values are reset in update_status with force = true
	return (status.err_TX | status.err_RX | status.err_FPGA);
}

// {MMCM,PLL} limits in ps
const int32_t PS_VCO_MIN  [2] = {1000000/MMCM_F_VCO_MAX,1000000/PLL_F_VCO_MAX};
const int32_t PS_VCO_MAX  [2] = {1000000/MMCM_F_VCO_MIN,1000000/PLL_F_VCO_MIN};
const int32_t PS_OUT_MIN  [2] = {1000000/MMCM_F_OUT_MAX,1000000/PLL_F_OUT_MAX};
const int32_t PS_OUT_MAX  [2] = {1000000/MMCM_F_OUT_MIN,1000000/PLL_F_OUT_MIN};
const int32_t PS_IN_MIN   [2] = {1000000/MMCM_F_IN_MAX ,1000000/PLL_F_IN_MAX};
const int32_t PS_IN_MAX   [2] = {1000000/MMCM_F_IN_MIN ,1000000/PLL_F_IN_MIN};
const int32_t PS_PFD_MIN  [2] = {1000000/MMCM_F_PFD_MAX,1000000/PLL_F_PFD_MAX};
const int32_t PS_PFD_MAX  [2] = {1000000/MMCM_F_PFD_MIN,1000000/PLL_F_PFD_MIN};
const int32_t MUL_MIN     [2] = {MMCM_MUL_MIN          ,PLL_MUL_MIN};
const int32_t MUL_MAX     [2] = {MMCM_MUL_MAX          ,PLL_MUL_MAX};
const int32_t MUL_STEP    [2] = {MMCM_MUL_STEP         ,PLL_MUL_STEP};
const int32_t DIV_MIN     [2] = {MMCM_DIV_MIN          ,PLL_DIV_MIN};
const int32_t DIV_MAX     [2] = {MMCM_DIV_MAX          ,PLL_DIV_MAX};
const int32_t DIV_STEP    [2] = {MMCM_DIV_STEP         ,PLL_DIV_STEP};
const int32_t OUT_DIV_MIN [2] = {MMCM_OUT_DIV_MIN      ,PLL_OUT_DIV_MIN};
const int32_t OUT_DIV_MAX [2] = {MMCM_OUT_DIV_MAX      ,PLL_OUT_DIV_MAX};
const int32_t OUT_DIV_STEP[2] = {MMCM_OUT_DIV_STEP     ,PLL_OUT_DIV_STEP};

// set the clock period in ps of the channel with the given name
// returns 0 on success and out_ps is set to actual period in ps.
// returns nonzero on error
// notes:
// - for simplicity, fractional division is not used now. this is anyway not possible together with fine phase shift or for PLL.
// - when MMCM/PLL is locked initially or when SET_CLOCK_WAIT_LOCK is specified (requires SET_CLOCK_OUT_LOAD) then waits for lock re-established.
// TODO: it is not clear if can load only when is locked?
// TODO: check calculation from xapp888, maybe in freq domain using fractions
int set_clock(char *channel, uint32_t *out_ps, unsigned flags) {
    int type;
    uint32_t index;
    uint32_t mul, div, in_div, VCO, div_out;
    uint32_t mul_min, div_min, div_out_min;
    int32_t d, d_min = 0x7fffffff;
    uint32_t status = 0x0;
    
    // find clock wizard and channel index
    struct clk_wiz_data *wiz = find_clock(channel, &index);
    if (wiz == NULL) return -1;
    else if ((wiz->PLL_type != CLK_WIZ_PLL) && (wiz->PLL_type != CLK_WIZ_MMCM)) return -2;
    else if (wiz->base_addr == NULL) return -3;
    else {
        // get PLL type
        type = (wiz->PLL_type == CLK_WIZ_MMCM) ? 0 : 1;
        // check if is locked
        status = ioread32(GET_ADDR(wiz->base_addr, CLK_WIZ_REG_STATUS));
        if ( (flags & SET_CLOCK_RESET) || (((status & CLK_WIZ_LOCKED) != CLK_WIZ_LOCKED) && (flags & SET_CLOCK_RESET_IF_NOT_LOCKED)) ) {
            // reset before programming
            iowrite32(CLK_WIZ_RESET, GET_ADDR(wiz->base_addr, CLK_WIZ_REG_RESET)); 
            udelay(SLEEP_TIME_LONG);
            status = ioread32(GET_ADDR(wiz->base_addr, CLK_WIZ_REG_STATUS));
            pr_err(NAME "channel '%s' (%i) wizard %d address 0x%p status 0x%x (reset)\n", channel, index, wiz->index, wiz->base_addr, status);
        }
        else {
            pr_err(NAME "channel '%s' (%i) wizard %d address 0x%p status 0x%x\n", channel, index, wiz->index, wiz->base_addr, status);
        }

        if ((*out_ps < PS_OUT_MIN[type]) || (*out_ps > PS_OUT_MAX[type])) return -10;
        if (flags & SET_CLOCK_VCO) {
            // calculate VCO multiplier and divider and output divider
            if ((wiz->in_ps < PS_IN_MIN[type]) || (wiz->in_ps > PS_IN_MAX[type])) return -11;
            for (div = DIV_MIN[type]; div <= DIV_MAX[type]; div += DIV_STEP[type]) {
                in_div = wiz->in_ps * div;
                if ((in_div >= PS_VCO_MIN[type]) && (in_div >= PS_PFD_MIN[type]) && (in_div <= PS_PFD_MAX[type])) { // divided input within allowed range and within range of VCO.
                    for (mul = MUL_MIN[type]; mul <= MUL_MAX[type]; mul += MUL_STEP[type]) {
                        VCO = in_div / mul;
                        if (VCO < PS_VCO_MIN[type]) break; // outside VCO range: increase div 
                        if (VCO <= PS_VCO_MAX[type]) { // within VCO range
                            for (div_out = OUT_DIV_MIN[type]; div_out <= OUT_DIV_MAX[type]; div_out += OUT_DIV_STEP[type]) {
                                d = (VCO * div_out) - *out_ps;
                                if (d == 0) { // found
                                    d_min = d; 
                                    mul_min = mul;
                                    div_min = div;
                                    div_out_min = div_out;
                                    goto VCO_found;
                                }
                                else if (d < 0) d = -d; // take absolute value (d is signed)
                                if (d < d_min) { // save smallest difference for smallest mul and div values
                                    d_min = d; 
                                    mul_min = mul;
                                    div_min = div;
                                    div_out_min = div_out;
                                }
                            }
                        }
                    }
                }
            }
VCO_found:  // set VCO configuration with smallest deviation
            wiz->VCO_ps = (wiz->in_ps * div_min) / mul_min;
            if ((wiz->VCO_ps < PS_VCO_MIN[type]) || (wiz->VCO_ps > PS_VCO_MAX[type])) return -5; // VCO outside range?
            if (((wiz->in_ps/div_min) < PS_PFD_MIN[type]) || ((wiz->in_ps/div_min) > PS_PFD_MAX[type])) return -6; // divided input frequency outside range?
            pr_err(NAME "set clock: VCO = %u * %u / %u = %u ps\n", wiz->in_ps, div_min, mul_min, wiz->VCO_ps);
            iowrite32(((mul_min & 0xff)<<8) | (div_min & 0xff), GET_ADDR(wiz->base_addr, CLK_WIZ_REG_FB_MUL_DIV));
        }
        else {
            // only calculate output divider
            if (wiz->VCO_ps == 0) { // read registers and calculate VCO period
                mul = ioread32(GET_ADDR(wiz->base_addr, CLK_WIZ_REG_FB_MUL_DIV));
                if (mul & 0xffff0000) return -10; // fraction given
                div = mul & 0xff;
                mul = (mul >> 8) & 0xff;
                wiz->VCO_ps = (wiz->in_ps * div) / mul;
                pr_err(NAME "act clock: VCO = %u * %u / %u = %u ps\n", wiz->in_ps, div_min, mul_min, wiz->VCO_ps);
            }
            else {
                pr_err(NAME "act clock: VCO = %u ps\n", wiz->VCO_ps);
            }

            // check if VCO period is within range
            VCO = wiz->VCO_ps;
            if ((VCO < PS_VCO_MIN[type]) || (VCO > PS_VCO_MAX[type])) return -20;

            // calculate div_out for given VCO frequency
            for (div_out = OUT_DIV_MIN[type]; div_out <= OUT_DIV_MAX[type]; div_out += OUT_DIV_STEP[type]) {
                d = (VCO * div_out) - *out_ps;
                if (d == 0) { // found
                    d_min = d; 
                    div_out_min = div_out;
                    break;
                }
                else if (d < 0) d = -d;
                if (d < d_min) { // smallest difference
                    d_min = d; 
                    div_out_min = div_out;
                }
            }
        }

        // set output divider for given channel
        *out_ps = wiz->VCO_ps * div_out_min;
        if ((*out_ps < PS_OUT_MIN[type]) || (*out_ps > PS_OUT_MAX[type])) return -30; // outside range?
        switch(index) {
            case 0:
                iowrite32(div_out_min & 0xff, GET_ADDR(wiz->base_addr, CLK_WIZ_REG_OUT_0_DIV));
                break;
            case 1:
                iowrite32(div_out_min & 0xff, GET_ADDR(wiz->base_addr, CLK_WIZ_REG_OUT_1_DIV));
                break;
            case 2:
                iowrite32(div_out_min & 0xff, GET_ADDR(wiz->base_addr, CLK_WIZ_REG_OUT_2_DIV));
                break;
            case 3:
                iowrite32(div_out_min & 0xff, GET_ADDR(wiz->base_addr, CLK_WIZ_REG_OUT_3_DIV));
                break;
            case 4:
                iowrite32(div_out_min & 0xff, GET_ADDR(wiz->base_addr, CLK_WIZ_REG_OUT_4_DIV));
                break;
            case 5:
                iowrite32(div_out_min & 0xff, GET_ADDR(wiz->base_addr, CLK_WIZ_REG_OUT_5_DIV));
                break;
            case 6:
                iowrite32(div_out_min & 0xff, GET_ADDR(wiz->base_addr, CLK_WIZ_REG_OUT_6_DIV));
                break;
            default:
                return -31; // illegal channel index
        }
        pr_err(NAME "set clock: out = %u * %u = %u ps\n", wiz->VCO_ps, div_out_min, *out_ps);

        if (flags & SET_CLOCK_OUT_LOAD) {
            udelay(SLEEP_TIME_SHORT);
            // load settings into PLL/MMCM
            // TODO: according to manual has to be locked before?
            index = ioread32(GET_ADDR(wiz->base_addr, CLK_WIZ_REG_STATUS));
            if (index == 0x1) {
                pr_err(NAME "set clock: status 0x%x (locked, ok)\n", index);
            }
            else {
                pr_err(NAME "set clock: status 0x%x must be 0x1!\n", index);
                return -40;
            }
            // TODO: according to manual have to set 0x7, then 0x2, then 0x3? why? its then said that backward compatibility is given? so is an option? but again why?
            if (false) {
                iowrite32(0x7, GET_ADDR(wiz->base_addr, CLK_WIZ_REG_LOAD_SEN)); udelay(SLEEP_TIME_SHORT);
                iowrite32(0x2, GET_ADDR(wiz->base_addr, CLK_WIZ_REG_LOAD_SEN)); udelay(SLEEP_TIME_SHORT);
            }
            iowrite32(0x3, GET_ADDR(wiz->base_addr, CLK_WIZ_REG_LOAD_SEN)); udelay(SLEEP_TIME_LONG);
        }

        // wait for lock if was locked before, or if waiting flag is set
        if ((status & CLK_WIZ_LOCKED) | (flags & SET_CLOCK_WAIT_LOCK)) {
            udelay(SLEEP_TIME_LONG);
            d = 1000*SLEEP_TIME_SHORT;
            while(((ioread32(GET_ADDR(wiz->base_addr, CLK_WIZ_REG_STATUS)) & CLK_WIZ_LOCKED) != CLK_WIZ_LOCKED) && (d > 0)) {
                --d;
                udelay(SLEEP_TIME_SHORT);
            }
            if (d == 0) pr_err(NAME "set clock: timeout! status 0x%x (should be 0x1)\n", ioread32(GET_ADDR(wiz->base_addr, CLK_WIZ_REG_STATUS)));
            else        pr_err(NAME "set clock: locked ok!\n");
        }

        // activate new settings
    }
    return 0;
}

