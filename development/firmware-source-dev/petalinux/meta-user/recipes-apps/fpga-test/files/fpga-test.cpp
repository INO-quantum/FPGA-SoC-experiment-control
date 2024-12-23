////////////////////////////////////////////////////////////////////////////////////////////////////
// fpga-test
// 32bit Linux console application to be run on Xilinx Zynq-7020 FPGA with Petalinux
// compiled with petalinux 2020.1 on Ubuntu 20.04 LTS
// created 2018/07/08 by Andi
// last change 2024/12/05 by Andi
////////////////////////////////////////////////////////////////////////////////////////////////////

#include <stdio.h>                  // printf, fopen
#include <stdlib.h>                 //_getch
#include <fcntl.h>                  // open
#include <unistd.h>                 // close, sleep, getopt
#include <string.h>                 // memcpy
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/mman.h>
#include <sys/time.h>               // gettimeofday
#include <time.h>                   // nanosleep
#include <stdint.h>                 // uint32_t, int32_t
#include <errno.h>                  // errno 

#include <sys/ioctl.h>              // ioctl
#include "dio24/dio24_driver.h"     // public driver definitions
//#include "dio24/driver.h"           // convenience IOCTL macros

#include "dio24-share/common.h"         // socket definitions
#include "dio24-share/dio24_server.h"   // public server definitions

//#include <libusb-1.0/libusb.h>          // libusb [TODO: include is working but linking not]
//#include <linux/usb/tmc.h>              // usbtmc specific definitions

#define NAME "fpga-test: "

// settings for test
#define TEST_BYTES          (10000*DIO_BYTES_PER_SAMPLE)    // buffer size in bytes for read()
#define TEST_TIMEOUT        1000                            // timeout in ms
#define TEST_T_LOOPS        5                               // number of timeouts before stop()
#define TEST_REPS_MAX       125                             // number of repetitions before stop()
#define TEST_ONERR_READ     false                           // after verify error continue read(), otherwise waits until FPGA and DMA finished
#define START_FLAGS         START_FPGA_DELAYED              // how to start FPGA

#define NUM_SAMPLES     0                                   // 0 = give only status
#define NUM_CYCLES      1                                   // cycles done on board without config & uploading
#define NUM_REPS        1                                   // repetitions including config & uploading
#define STRB_DELAY      0
#define SYNC_DELAY      0

// DIO_BYTES_PER_SAMPLE dependent settings
#if DIO_BYTES_PER_SAMPLE == 8
    #define CTRL_FPGA                   DIO_CONFIG_RUN_64 | DIO_CTRL_AUTO_SYNC_EN | DIO_CTRL_AUTO_SYNC_PRIM
    #define ADD_ZERO_PP(p)
    #define SHOW_DATA(p)                printf("0x %08x %08x = %8u us\n", i, *p, *(p+1), *p);
    #define SHOW_DATA_I(i,p)            printf("%6u: 0x %08x %08x = %8u us\n", i, *p, *(p+1), *p);
    #define SHOW_DATA_IC(i,p,comment)   printf("%6u: 0x %08x %08x = %8u us (%s)\n", i, *p, *(p+1), *p, comment);
    #define EXPAND96(data,num)          data
    #define EXPAND96_FREE               false
#elif DIO_BYTES_PER_SAMPLE == 12
    #define CTRL_FPGA                   DIO_CONFIG_RUN_96 | DIO_CTRL_AUTO_SYNC_EN | DIO_CTRL_AUTO_SYNC_PRIM       //DIO_CTRL_IRQ_ALL|DIO_CTRL_RESTART_EN|DIO_CTRL_BPS96
    #define ADD_ZERO_PP(p)              *p++ = 0
    #define SHOW_DATA(p)                printf("0x %08x %08x %08x = %8u us\n", i, *p, *(p+1), *(p+2), *p);
    #define SHOW_DATA_I(i,p)            printf("%6u: 0x %08x %08x %08x = %8lu us\n", i, *p, *(p+1), *(p+2), *p);
    #define SHOW_DATA_IC(i,p,comment)   printf("%6u: 0x %08x %08x %08x = %8u us (%s)\n", i, *p, *(p+1), *(p+2), *p, comment);
    #define EXPAND96(data,num)          expand64_to_96(data,num)
    #define EXPAND96_FREE               true
#endif
#define    INC32            (DIO_BYTES_PER_SAMPLE/4)    // 32bit pointer increment per sample for verify, show, etc.

#define FILE_CPU_STAT   "/proc/stat"                // file for CPU statistics
#define STAT_NUMS       10                          // number of entries per line
#define STAT_USER       0                           // 0-based index of user time
#define STAT_USER_NICE  1                           // 0-based index of user time with low priority
#define STAT_KERNEL     2                           // 0-based index of kernel time
#define STAT_IDLE       3                           // 0-based index of idle time  
#define STAT_IOWAIT     4                           // 0-based index of I/O waiting time (not reliable)  
#define STAT_IRQ        5                           // 0-based index of IRQ servicing time  
#define STAT_IRQ_SOFT   6                           // 0-based index of soft IRQ servicing time 
#define STAT_STEAL      7                           // 0-based index of stolen time (virtual environment)  
#define STAT_GUEST      8                           // 0-based index of guest time (virtual environment)  
#define STAT_GUEST_NICE 9                           // 0-based index of guest time with low priority (virtual environment)  
#define STAT_BUFFER     ((11*STAT_NUMS)+20)         // buffer for CPU statistics. I assume each number is 32bit, i.e. 10 decimal digits

// read CPU statistics from /proc/stat for num_cpu CPUs.
// saves in cpu_percent the cpu load in percent * 1000 for each CPU.
// first call is initilizing buffers cpu_sum and cpu_idle with num_cpu entries each.
// 2nd and further call gives resulting load averaged since last call.
// returns 0 if ok, otherwise error
int read_CPU_stat(unsigned long long *cpu_sum, unsigned *cpu_idle, unsigned *cpu_percent, int num_cpu) {
    static char buffer[STAT_BUFFER];
    int err = 0, i = 0, j, read;
    unsigned num, idle;
    unsigned long long sum;
    char *p;
    FILE *fd = fopen(FILE_CPU_STAT, "r");
    if (fd == NULL) { printf("open file failed\n"); err = -1; }
    else {
        while((fgets(buffer, STAT_BUFFER, fd) != NULL) && (!err)) {                 // read next line
            if (i > 0) {                                                            // skip overall cpu percent
                sum = 0;
                idle = 0;
                p = buffer;
                read = 0;
                if (sscanf(p,"cpu%u %n", &num, &read) != 1) {                       // error: entry is not cpu#
                    if (i == 1) err = -10;                                          // error only if no CPU measured
                    else {                                                          // num_cpu is wrong: set other CPUs to zero
                        for (; i <= num_cpu; ++i) {
                            *cpu_percent++ = 0;
                            *cpu_sum++ = 0;
                            *cpu_idle++ = 0;
                        }
                    }
                    break;
                }
                if ((num != (i-1)) || (read != 5)) { err = -11; break; }            // error: wrong cpu number or number not 1 character
                p += read;
                for (j = 0; j < STAT_NUMS; ++j) {                                   // read number
                    read = 0;
                    if ((sscanf(p,"%u%n", &num, &read) != 1) || (read < 1)) { err = -12; break; } // error: no number
                    if (j == STAT_IDLE) {
                        idle = num;
                        //printf("number %u = %u (idle)\n", j, num);
                    }
                    //else printf("number %u = %u\n", j, num);
                    sum += num;
                    p += read;                    
                }
                *cpu_percent++ = (sum == *cpu_sum) ? 0 : (((sum-*cpu_sum) - (idle-*cpu_idle))*100000)/(sum-*cpu_sum);
                *cpu_sum++ = sum;       // save last sum of all counters
                *cpu_idle++ = idle;     // save last idle counter
            }
            if (++i > num_cpu) break;
        }     
        fclose(fd);
    }
    return err;
}

// start taking CPU statitics with given number of CPU
unsigned *cpu_percent       = NULL;
unsigned *cpu_idle          = NULL;
unsigned long long *cpu_sum = NULL; 
int start_cpu_stat(int num_cpu) {
    int err = -1, i;

    if((num_cpu<=0) || cpu_percent || cpu_idle || cpu_sum) printf("CPU stat: already STARTed!\n");
    else {
        cpu_percent = new unsigned[num_cpu];
        cpu_idle    = new unsigned[num_cpu];
        cpu_sum     = new unsigned long long[num_cpu];

        for (i = 0; i < num_cpu; ++i) {
            cpu_percent[i] = 0; 
            cpu_idle[i] = 0;
            cpu_sum[i] = 0;
        }
        err = read_CPU_stat(cpu_sum, cpu_idle, cpu_percent, num_cpu);
        if (err) {
            printf("CPU stat: START error\n");
            delete [] cpu_percent; cpu_percent = NULL;
            delete [] cpu_idle;    cpu_idle    = NULL;
            delete [] cpu_sum;     cpu_sum     = NULL;
        }
    }
    return err;
}

// stop taking CPU statitics with given number of CPU
// returns pointer to num_cpu unsigned with CPU load in % * 1000 for each CPU
// delete[] returned pointer after use
// returns NULL on error
unsigned * stop_cpu_stat(int num_cpu) {
    int err = -1, i;
    unsigned *result = NULL;
    if ((num_cpu<=0) || (!cpu_percent) || (!cpu_idle) || (!cpu_sum))  printf("CPU stat: STOP but not started!\n");
    else {                              // started and cpu_... buffers are allocated
        err = read_CPU_stat(cpu_sum, cpu_idle, cpu_percent, num_cpu);
        if (err) {
            printf("CPU stat: STOP error\n");
            delete [] cpu_percent; cpu_percent = NULL;
        }
        else { // return result
            result = cpu_percent;
            cpu_percent = NULL;
        }
        delete [] cpu_idle;    cpu_idle    = NULL;
        delete [] cpu_sum;     cpu_sum     = NULL;
    }
    return result;
}

// single-linked list of data
struct data_info {
    uint32_t *data;
    uint32_t samples;
    struct data_info *next;    // pointer to next or NULL
};

// generates linear ramp on the given analog output address from {t_start, u_start} to {t_end, u_end} with number of steps
// returns pointer to buffer with generated ramp, free after use.
uint32_t* test_analog(unsigned char address, uint32_t t_start, uint32_t t_end, int16_t u_start, int16_t u_end, uint32_t steps) {
    int err = 0;
    uint32_t t, s;
    uint32_t u;
    uint32_t *p, *buf;
    uint32_t strb = 0;
    p = buf = (uint32_t *) malloc(steps*DIO_BYTES_PER_SAMPLE);
    if(p) {
        if (u_end >= u_start ) {
            for (s = 0, t = t_start, u = u_start; s < steps; s++) {
                t = t_start + (((t_end - t_start) * s) / (steps - 1));
                u = u_start + (((u_end - u_start) * s) / (steps - 1));
                *p++ = t;
                *p++ = (u & 0xffff) | (((address & 0x7f) | (strb << 7)) << 16);
                ADD_ZERO_PP(p);
                strb ^= 1;
            }
        }
        else {
            for (s = 0, t = t_start, u = u_start; s < steps; s++) {
                t = t_start + (((t_end - t_start) * s) / (steps - 1));
                u = u_start - (((u_start - u_end) * s) / (steps - 1));
                *p++ = t;
                *p++ = (u & 0xffff) | (((address & 0x7f) | (strb << 7)) << 16);
                ADD_ZERO_PP(p);
                strb ^= 1;
            }
        }
    }
    return buf;
}

// generates TTL signal on the given address from {t_start, TTL 0} to {t_end, TTL 15} with 16 steps
// returns pointer to buffer with generated ramp, free after use.
uint32_t* test_digital(unsigned char address, uint32_t t_start, uint32_t t_end, bool ramp_up) {
    int err = 0;
    uint32_t t, s;
    uint32_t u;
    uint32_t *p, *buf;
    uint32_t strb = 1;
    p = buf = (uint32_t *) malloc(16*DIO_BYTES_PER_SAMPLE);
    if(p) {
        if (ramp_up) {
            for (s = 0, t = t_start; s < 16; s++) {
                t = t_start + (((t_end - t_start) * s) / 15);
                u = 1 << s;
                *p++ = t;
                *p++ = (u & 0xffff) | (((address & 0x7f) | (strb << 7)) << 16);
                ADD_ZERO_PP(p);
                strb ^= 1L;
            }
        }
        else {
            for (s = 0, t = t_start; s < 16; s++) {
                t = t_start + (((t_end - t_start) * s) / 15);
                u = 1 << (15-s);
                *p++ = t;
                *p++ = (u & 0xffff) | (((address & 0x7f) | (strb << 7)) << 16);
                ADD_ZERO_PP(p);
                strb ^= 1L;
            }
        }
    }
    return buf;
}

// test all output pins data 0-15 and address 0-7
// generates for each output 3 samples: only output ON followed by only output OFF followed by all outputs OFF.
// every N_WAIT outputs waiting time is doubled when all outputs are off. this makes it easier to count the outputs.
// returns pointer to buffer with data, free after use.
// samples returns the number of samples
uint32_t* test_outputs(uint32_t t_start, uint32_t t_end, uint32_t *samples) {
#define N_WAIT     4        // steps after which we insert one waiting step (must be power of 2)
#define P_WAIT     (N_WAIT-1)    // pattern for waiting time (3)
#define NN_WAIT    ((24/N_WAIT)-1)    // number of waiting steps (5)
    int err = 0;
    uint32_t s, w = 0;
    uint32_t *p, *buf;
    p = buf = (uint32_t *) malloc((24*3+1)*DIO_BYTES_PER_SAMPLE);
    if(p) {
        for (s = 0; s < 24; s++) {
            *p++ = t_start + (((t_end - t_start) * (3*s + w + 0)) / (23*3+NN_WAIT+3));
            *p++ = DIO_DATA_MASK & (1 << s); // ON: all other outputs off
            ADD_ZERO_PP(p);
            *p++ = t_start + (((t_end - t_start) * (3*s + w + 1)) / (23*3+NN_WAIT+3));
            *p++ = DIO_DATA_MASK & (~(1 << s)); // OFF: all other outputs on
            ADD_ZERO_PP(p);
            *p++ = t_start + (((t_end - t_start) * (3*s + w + 2)) / (23*3+NN_WAIT+3));
            *p++ = 0; // all outputs OFF
            ADD_ZERO_PP(p);
            if ( (s & P_WAIT) == P_WAIT ) w++; // wait one step every N_WAIT steps
        }
printf("s = %u, w = %u, t = %u, t_end = %u\n", s, w, *(p-2), t_end);
        // for testing insert another sample with all zero
        *p++ = t_end;
        *p++ = 0; // all outputs OFF
        ADD_ZERO_PP(p);
        *samples = 24*3 + 1;
printf("t = %u, dt = %u\n", *(p-6), *(p-6)-(*p-8));
printf("t = %u, dt = %u\n", *(p-4), *(p-4)-(*p-6));
printf("t = %u, dt = %u\n", *(p-2), *(p-2)-(*p-4));
    }
    return buf;
}

// generates samples starting at t_start us with t_step time. 
// data starts at d_start and increments with d_step
// returns pointer to data or NULL on error. free after use.
uint32_t* test_step(uint32_t samples, uint32_t t_start, uint32_t t_step, uint32_t d_start, uint32_t d_step) {
    uint32_t *buf, *p, s;
    p = buf = (uint32_t *) malloc(samples*DIO_BYTES_PER_SAMPLE);
    if(buf) {
        for(s = 0; s < samples; ++s, t_start += t_step, d_start += d_step) {
            *p++ = t_start;
            *p++ = DIO_DATA_MASK & d_start;
            ADD_ZERO_PP(p);
        }
    }
    return buf;
}

#define TOLD_INVALID    0xffffffff
#define TIME_MASK    0xffffffff
#define DATA_MASK    DIO_DATA_MASK        // allowed 24 data bits without special bits
inline bool chk(uint32_t i, uint32_t *p, uint32_t &t_old, bool show) {
    if (show) SHOW_DATA_I(i,p);
    /*if ((*p) & (1<<DIO_BIT_NUM)) {
        printf("%3i: num_samples = %u\n", i, (*p) & DIO_SAMPLES_MASK);
        t_old = TOLD_INVALID;
    }
    else */
    if((((*p) & TIME_MASK) <= t_old) && (t_old != TOLD_INVALID)) { 
        if (!show) {
            SHOW_DATA_IC(i-1,p-INC32,"ok");
            SHOW_DATA_IC(i,p,"error time!");
        }
        printf("\n *** error time <= old! ***\n\n");
        //return true; 
        t_old = (*p) & TIME_MASK;
    }
    else {
        t_old = (*p) & TIME_MASK;
    }
    return false;
}
// shows first max/2 and last max/2 data (or less)
// and checks if time is incrementing and data is within DIO_DATA_MASK. 
// indicates all samples where DIO_BIT_NUM is set (# samples).
// first time after DIO_BIT_NUM is set can have time < old time (auto-restart)
// init t_old with TOLD_INVALID.
// returns 0 if ok, otherwise error
// TODO: cleanup and merge
int show_data(uint32_t *p, uint32_t samples, uint32_t max, uint32_t &t_old) {
    int err = 0;
    uint32_t i;
    if(samples <= max) {
        for (i=0; i<samples; ++i, p+=INC32) {
            if (chk(i, p, t_old, true)) { err = -1; break; }
        }
    }
    else {
        max=max >> 1;
        for (i=0; i<max; ++i, p+=INC32) {
            if (chk(i, p, t_old, true)) { err = -1; break; }
        }
        if (!err) {
            max = samples - max;
            printf("...\n");
            for (; i<max; ++i, p+=INC32) {
                if (chk(i, p, t_old, false)) { err = -1; break; }
            }
            if(!err) {
                for (; i<samples; ++i, p+=INC32) {
                    if (chk(i, p, t_old, true)) { err = -1; break; }
                }
            }
        }
    }
    return err;
}
// shows samples of all data starting from total sample offset
int show_data(struct data_info *data, uint32_t offset, uint32_t samples) {
    uint32_t i = 0, j, *p;
    // find offset in data
    while(data) {
        if((i+data->samples) > offset) { 
            // offset found: show data
            p = data->data + ((offset - i)*INC32);
            i = offset;
            offset += samples;
//printf("show_data: start %u\n", i);
            for(j = 0; i < offset; ++i) {
                SHOW_DATA_I(i,p);
                if(++j < data->samples) p += INC32;
                else {
                    do {
                        data = data->next;
                        if(data == NULL) {
                            if ((i+1) < offset) {
printf("show_data: end not reached %u\n", i);
                                return -2; // could not show all data
                            }
                            else return 0;
                        }
                    } while((data->data == NULL)||(data->samples == 0));
//printf("show_data: %u new buffer %u samples @ %p\n", i, data->samples, data->data);
                    j = 0;
                    p = data->data;
                }
            }
//printf("show_data: end %u, %u samples\n", i, samples);
            // all data shown
            return 0;
        }
        i += data->samples;
        data = data->next;
//printf("show_data: %u new buffer %u samples @ %p\n", i, data->samples, data->data);
    }
    // not found
printf("show_data: %u not found!\n", offset);
    return -1;
}

// find data sample: returns offset within di, di of data and total offset in data
int find_data(struct data_info *&di, uint32_t time, uint32_t &data) {
    uint32_t i = 0, j, *p;
    // find offset in data
    while(di) {
        p = di->data;
        for(j = 0; j < di->samples; ++j, p+=INC32) {
            if( (((*p) & TIME_MASK) == time) && (((*(p+1)) & DATA_MASK) == data)) {
                //printf("%6u: 0x %08lx_%08lx (found! @ %p + %u)\n", i + j, *(p+1), *(p), p, j);
                data = i + j;
                return j;
            }
        }
        i += di->samples;
        di = di->next;
    }
    // not found
    printf("find_data: not found in %u samples!\n", i);
    return -1;
}

// for each entry in data calls show_data to print show_max samples
// and checks if data is incrementing in time
// return 0 if ok, otherwise error
// TODO: cleanup and merge
int check_data(struct data_info *data, int show_max) {
    int err = -1, i = 0;
    uint32_t t_start = TOLD_INVALID;
    uint32_t t_old = TOLD_INVALID, num = 0;
    while(data) {
        printf(NAME"(%d) check mem @ %p, %u samples, start time %u ...\n", i, data->data, data->samples, *data->data);

        err = show_data(data->data, data->samples, show_max ? show_max : data->samples, t_old);
        if(err) break;
        else printf(NAME"(%d) check mem @ %p, %u samples, start time %u ok\n", i, data->data, data->samples, *data->data);
        num += data->samples;
        if (t_start == TOLD_INVALID) {
            if (data->samples > 0) t_start = *data->data;
        }
        data = data->next;
        ++i;
    }
    if(err) printf(NAME"check_data error!\n");
    else printf(NAME"check_data %d rounds, %u samples, %u-%u=%u us ok\n", i, num, t_old, t_start, t_old - t_start);
    return err;
}


//#include <iostream>
//using namespace std;

// wait until given key is pressed
// notes:
// - you can give EOF = Ctrl-D
// - I actually wanted to flush keyboard buffer but I did not managed since all functions wait for <ENTER>.
void wait_for_key(char key) {
    //char buffer[100];
    //while(fgets(buffer, 100, stdin) != NULL ) {
    //    printf("master: input buffer = \"%s\"", buffer);
    //};
    int c;
    printf(NAME": waiting for key  = '%c' (%d)\n", key, key);
    do {
        c = fgetc(stdin);
        printf(NAME": key  = '%c' (%d)\n", c, c);
    } while ((c != EOF) && (c != (int)key) && (c != 27));
}


//#define PMAX    32767        // set value to get 12V output voltage
//#define NMAX    -32768        // set value to get -12V output voltage
#define PMAX    9000        // set value to get 12V output voltage
#define NMAX    -9001        // set value to get -12V output voltage
#define STEPS    1001        // number of steps
#define TSTEP    2        // us per step
#define A0    23        // analog out address 0
#define A1    24        // analog out address 1
#define D0    1        // digital out address 0
#define D1    2        // digital out address 1

// wait until data on device is available, maximum timeout ms
// returns >0 if data available, 0 if timeout, <0 on error
int wait_read(int device, unsigned timeout) {
    fd_set set;
    struct timeval wait;

    FD_ZERO(&set);
    FD_SET(device, &set);

    wait.tv_sec = timeout / 1000;
    wait.tv_usec = (timeout % 1000) * 1000;

    return select(device + 1, &set, NULL, NULL, &wait);
}

//#define BUFFER_LENGTH    20
//int buffer[BUFFER_LENGTH];

#define TEST_BUF_SIZE    0x2800*8        // number of 32-bit integers to be sent = number of lines*2

// sleep time in ms
// uses nanosleep defined in <time.h>
void sleep_ms(uint32_t ms) {
    static struct timespec ts;
    ts.tv_sec = ms / 1000;
    ts.tv_nsec = (ms % 1000) * 1000000;
    nanosleep(&ts, NULL);
}

// measure elapsed time in microseconds
// wraps over every ca. 4295s ca. 71'
inline uint32_t get_ticks(void) {
    static struct timespec ts2;
    clock_gettime(CLOCK_MONOTONIC, &ts2); //CLOCK_MONOTONIC or CLOCK_REALTIME
    return ts2.tv_sec*1000000 + (ts2.tv_nsec / 1000);
}

// expands data with 64bit/sample to 96bits/sample
// returns pointer to expanded data. free after use.
uint32_t * expand64_to_96(uint32_t *data, uint32_t samples) {
    uint32_t i, *data96, *p;
    p = data96 = (uint32_t*)malloc(samples*12);
    if(data96) {
        for(i = 0; i < samples; ++i) {
            *p++ = *data++;                // time
            *p++ = DIO_DATA_MASK & (*data++);    // data board 0
            *p++ = DIO_DATA_MASK & 0;        // data board 1
        }
    }
    return data96;
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

// get device status and display by driver
static struct FPGA_status status;
static struct FPGA_status_run st_run;
int get_status(int dev) {
    int err, i;
    int32_t mT;
    memset(&status, 0, sizeof(struct FPGA_status));
    status.ctrl_FPGA = FPGA_STATUS_SHOW;    // if this is set driver will display status information
    //if (all) err = dio24_get_status_dbg(dev, &status);
    //err = dio24_get_status(dev, &status);
    err = ioctl(dev, DIO24_IOCTL_GET_STATUS, &status);
    sleep_ms(100); // this might avoid that driver messages are printed between status.
    if(err != 0) printf(NAME "get_status failed with error %d (%d)!\n", errno, err);
    return err;
}

// shows s_num samples in data info starting at s_start sample
// if data != NULL shows for comparison data in same column (must contain s_num samples)
//                 displayed data index starts with i_start
// wraps around data info to show s_num samples
void show_data2(struct data_info *info, uint32_t *data, uint32_t s_num, uint32_t s_start, uint32_t i_start) {
    struct data_info *mem = info;
    uint32_t i, j = mem->samples, *p = mem->data, s_cnt = 0;
    s_num += s_start;
printf(NAME "show_data: %u samples %u start\n", s_num, s_start);sleep_ms(200);
    for (i = 0; i < s_num; ++i, ++s_cnt, --j, p += (DIO_BYTES_PER_SAMPLE/4)) {
        if(j == 0) {
            do {
                mem = mem->next;
                if(mem == NULL) { mem = info; s_cnt = 0; }
            } while ((mem->samples == 0) || (mem->data == NULL));
            j = mem->samples;
            p = mem->data;
        }
        if(i >= s_start) {
#if DIO_BYTES_PER_SAMPLE == 8
            if(data) { 
                printf("%04d: %8u us %08x | %03d: %8u us %08x\n", s_cnt, *(p), *(p+1), i_start+i-s_start, *data, *(data+1)); 
                data += 2; 
            }
            else {
                printf("%04d: %8u us %08x\n", s_cnt, *(p), *(p+1));
            }
#elif DIO_BYTES_PER_SAMPLE == 12
            if (data) { 
                printf("%04d: %8u us %08x %08x | %03d: %8u us %08x %08x\n", s_cnt, *(p), *(p+1), *(p+2), i_start+i-s_start, *data, *(data+1), *(data+2)); 
                data += 3; 
            }
            else {
                printf("%04d: %8u us %08x %08x\n", s_cnt, *(p), *(p+1), *(p+2));
            }
#endif
        }
    }

}

// verify RX data of samples length within TX data info starting at sample s_offset.
// returns 0 on success, <0 on error.
// on success updates s_offset to next sample index
#define SHOW_SAMPLES    10    // shows data +/- samples around last good sample
int verify_data2(struct data_info *info, uint32_t *data, uint32_t samples, uint32_t *s_offset) {
    struct data_info *mem = info;
    uint32_t i = 0, j, *p, *d = data, s_cnt;
    uint32_t t_start = *data;
    bool restart = true;
    
    //printf(NAME "verify_data: %u samples starting at %u\n", samples, *s_offset);
    
    // skip forward to offset
    while(mem) {
        if ((i + mem->samples) > *s_offset) {
            p = mem->data + (*s_offset - i)*(DIO_BYTES_PER_SAMPLE/4);
            i = *s_offset;
            j = mem->samples;
            break;
        }
        i += mem->samples;
        mem = mem->next;
    }
    if (mem == NULL) {
        printf(NAME "verify_data: offset %u too large! buffer contains %u samples\n", *s_offset, i);
        return -2;
    }
    //printf(NAME "mem @ %p, %u samples, first time %u\n", mem->data, mem->samples, *d);
        
    for (s_cnt = 0; ; ++i, --j, p += (DIO_BYTES_PER_SAMPLE/4)) {
        if (j == 0) {
            // next buffer
            //printf(NAME "mem @ 0x%p, %u samples, next time %u\n", mem->data, mem->samples, *d);
            do {
                mem = mem->next;
                if(mem == NULL) {
                    // time not found!
                    printf(NAME "verify_data: sample # %u = %u us not found! %u/%u samples\n", i, *d, i - *s_offset, samples);
                    return -10;
                }
            } while ((mem->samples == 0) || (mem->data == NULL)); // skip zero samples data
            j = mem->samples;
            p = mem->data;
        }
        if (*p == *d) { // matching time
#if DIO_BYTES_PER_SAMPLE == 8
            if(*(p+1) != *(d+1)) return -20; // error data
            d += 2; 
#elif DIO_BYTES_PER_SAMPLE == 12
            if(*(p+1) != *(d+1)) return -21; // error data 1
            if(*(p+2) != *(d+2)) return -22; // error data 2
            d += 3; 
#endif
            ++s_cnt;        // count good samples
            if (s_cnt >= samples) {
                ++i;
                break;
            }
        }
        else if (s_cnt != 0) {
            // data must contain contiguous samples!
            printf(NAME "verify_data: sample # %u time %u != %u! %u/%u samples\n", i, *d, *p, s_cnt, samples);
            return -31;            
        }
    }

    //if ((i - *s_offset) != samples) printf(NAME "verify_data: %u samples ok, %u dropped\n", samples, i - *s_offset - samples);
    *s_offset = i;
    return 0;
}

// command line parameters
typedef struct test_params {
    uint32_t clk_div;
    uint32_t ctrl;
    uint32_t ctrl_in [2];
    uint32_t ctrl_out[2];
    uint32_t samples;
    uint32_t cycles;
    uint32_t reps;
    uint32_t strb_delay;
    uint32_t sync_delay;
    uint32_t poll_ms;
    uint32_t start_flags;
    char *   filename;
    bool     verify;
    bool     ext_clk;
} TP;

// test mmap
int test_mmap(void) {
    int err = -1, i;
    int dma24_dev;
    struct dma24_interface * p_intf;
    struct data_info *data;
    uint32_t *p, *q;
    // open device
    //dma24_dev = dma24_open(0);
    dma24_dev = open(DMA24_DEVICE_FILE_NAME(0), O_RDWR | O_SYNC);
    if (dma24_dev <= 0) printf(NAME "error %d opening dma24 device!\n", dma24_dev); 
    else {
        // mmap kernel memory as dma24_interface structure
        p_intf = (struct dma24_interface *) mmap(NULL, sizeof(struct dma24_interface), PROT_READ | PROT_WRITE, MAP_SHARED, dma24_dev, 0);
        if(p_intf == MAP_FAILED) printf(NAME "error mmap!\n"); 
        else {
            // generate data
            data->samples = MMAP_SIZE / DIO_BYTES_PER_SAMPLE;
            data->data = test_step(data->samples, 0, 1, 0x030201, 0x010101);
            // write data to kernel memory
            p = data->data;
            q = (uint32_t *) p_intf->buffer;
            for (i = 0; i < data->samples; ++i) {
#if DIO_BYTES_PER_SAMPLES == 8
                *q++ = *p++;
                *q++ = *p++;
#elif DIO_BYTES_PER_SAMPLES == 12
                *q++ = *p++;
                *q++ = *p++;
                *q++ = *p++;
#endif
            }
            // give data back to kernel via ioctl (not write)
            //dma24_write(dma24_dev,p_intf);
            // unmap kernel memory
            munmap(p_intf, sizeof(struct dma24_interface));
        }
        // close device
        //dma24_close(dma24_dev);
        close(dma24_dev);
    }
    return err;
}

// save 2D data of length 32bits to CSV file with given number of columns
// if file exists data is appended to existing data, otherwise new file is created
// returns 0 if ok, otherwise error code
int save_CSV(const char *name, uint32_t *data, int length, int columns) {
    int err = 0, col, cnt;
    FILE *fd;
    if (data && (length > 0)) {
        fd = fopen(name, "a");
        if (fd == NULL) err = -1;
        else {
            for(cnt = 0, col = 1; cnt < length; ++cnt, ++col, ++data) {
                if (col == columns ) {
                    if (fprintf(fd,"%d\n", *data) <= 0) { err = -2; break; }
                    col = 0;
                }
                else {
                    if (fprintf(fd,"%d,", *data) <= 0) { err = -3; break; }
                }
            }
            if (!err) {
                if (fprintf(fd,"\n") <= 0) err = -4;
            }
            fclose(fd);
        }
    }
    return err;
}

// perform write and read of all data
// verifies correctness of RX data
// caller must free data
// if cleaning = true then verify waits until TX data is received
int write_read_test(struct data_info *data, TP *params) {
    int err = -1;
    int dma24_dev, dio24_dev;
    uint32_t *buffer, samples = 0, load, s_max = 1, s_act = 0, s_more = 0, cnt, d_cnt, t_old, t_act, s_drop = 0;
    uint32_t value;
    struct data_info *first, *next;
    struct st_par stp;
    struct set_reg32 sr32;
    bool status_show = false;

    // open dma24_dev
    //dma24_dev = dma24_open(0);
    dma24_dev = open(DMA24_DEVICE_FILE_NAME(0), O_RDWR | O_SYNC);
    if(dma24_dev <= 0) printf(NAME "error %d opening dma24 device!\n", dma24_dev); 
    else {
        // open dio24_dev device
        //dio24_dev = dio24_open(0);
        dio24_dev = open(DIO24_DEVICE_FILE_NAME(0), O_RDONLY | O_SYNC);
        if (dio24_dev <= 0) printf(NAME "error %d opening dio24 device!\n", dio24_dev); 
        else {
            memset(&status, 0, sizeof(struct FPGA_status));
            //sleep_ms(10);
            if( data == NULL ) printf(NAME "data NULL or samples 0!?\n");
            else {
                buffer = (uint32_t *)malloc(TEST_BYTES);
                if( buffer == NULL ) printf(NAME "allocation of %d bytes failed!\n", TEST_BYTES);
                else {
                    // reset dma24_dev which also cleans buffers
                    //err = dma24_reset(dma24_dev);
                    err = ioctl(dma24_dev, DMA24_IOCTL_RESET, NULL);
                    if(err < 0) printf(NAME "reset error %d (0x%X)\n", err, err);
                    else {
                        printf(NAME "reset ok.\n");
                        // set timeout
                        value = TEST_TIMEOUT;
                        //err = dma24_set_timeout(dma24_dev, &value);
                        err = ioctl(dma24_dev, DMA24_IOCTL_SET_TIMEOUT, &value);
                        if(err) printf(NAME "set timeout %u error %d (0x%X)\n", value, err, err);
                        else {
                            printf(NAME "set timeout %u ok\n", value);
                            // set config
                            if (params->cycles != 1) {
                                params->ctrl |= DIO_CTRL_RESTART_EN;
                                printf(NAME "%u cycles set config 0x%x with restart flag\n", params->cycles, params->ctrl);
                            }
                            //dio24_set_config(dma24_dev, params->ctrl, sr32, err);
                            sr32.reg  = DIO_REG_CTRL;
                            sr32.data = params->ctrl;
                            err = ioctl(dma24_dev, DIO24_IOCTL_SET_REG, &sr32);
                            if(err != 0) printf(NAME "set_config 0x%x failed with error %d (%d)!\n", params->ctrl, errno, err);
                            else {
                                printf(NAME "set_config 0x%x ok\n", params->ctrl);
                                // set clock divider
                                //dio24_set_div(dma24_dev, params->clk_div, sr32, err);
                                sr32.reg  = DIO_REG_CLK_DIV;
                                sr32.data = params->clk_div;
                                err = ioctl(dma24_dev, DIO24_IOCTL_SET_REG, &sr32);
                                if(err) printf(NAME "set_div %u failed with error %d!\n", params->clk_div, err);
                                else {
                                    printf(NAME "set_div %d ok\n", params->clk_div);
                                    // set control_in/out to 0
                                    //dio24_set_ctrl_in0(dma24_dev, params->ctrl_in[0], sr32, err);
                                    sr32.reg  = DIO_REG_CTRL_IN0;
                                    sr32.data = params->ctrl_in[0];
                                    err = ioctl(dma24_dev, DIO24_IOCTL_SET_REG, &sr32);
                                    if(err != 0) printf(NAME "set_ctrl_in0 = 0x%x failed with error %d (%d)!\n", params->ctrl_in[0], errno, err);
                                    else {
                                        printf(NAME "set_ctrl_in0 = 0x%x ok\n", params->ctrl_in[0]);
                                        //dio24_set_ctrl_in1(dma24_dev, params->ctrl_in[1], sr32, err);
                                        sr32.reg  = DIO_REG_CTRL_IN1;
                                        sr32.data = params->ctrl_in[1];
                                        err = ioctl(dma24_dev, DIO24_IOCTL_SET_REG, &sr32);
                                        if(err != 0) printf(NAME "set_ctrl_in1 = 0x%x failed with error %d (%d)!\n", params->ctrl_in[1], errno, err);
                                        else {
                                            printf(NAME "set_ctrl_in1 = 0x%x ok\n", params->ctrl_in[1]);
                                            //dio24_set_ctrl_out0(dma24_dev, params->ctrl_out[0], sr32, err);
                                            sr32.reg  = DIO_REG_CTRL_OUT0;
                                            sr32.data = params->ctrl_out[0];
                                            err = ioctl(dma24_dev, DIO24_IOCTL_SET_REG, &sr32);
                                            if(err != 0) printf(NAME "set_ctrl_out0 = 0x%x failed with error %d (%d)!\n", params->ctrl_out[0], errno, err);
                                            else {
                                                printf(NAME "set_ctrl_out0 = 0x%x ok\n", params->ctrl_out[0]);
                                                //dio24_set_ctrl_out1(dma24_dev, params->ctrl_out[1], sr32, err);
                                                sr32.reg  = DIO_REG_CTRL_OUT1;
                                                sr32.data = params->ctrl_out[1];
                                                err = ioctl(dma24_dev, DIO24_IOCTL_SET_REG, &sr32);
                                                if(err != 0) printf(NAME "set_ctrl_out1 = 0x%x failed with error %d (%d)!\n", params->ctrl_out[1], errno, err);
                                                else {
                                                    printf(NAME "set_ctrl_out1 = 0x%x ok\n", params->ctrl_out[1]);
                                                    // set strobe delay
                                                    //dio24_set_strb_delay(dma24_dev, params->strb_delay, sr32, err);
                                                    sr32.reg  = DIO_REG_STRB_DELAY;
                                                    sr32.data = params->strb_delay;
                                                    err = ioctl(dma24_dev, DIO24_IOCTL_SET_REG, &sr32);
                                                    if(err != 0) printf(NAME "set_strb_delay %u failed with error %d!\n", params->strb_delay, err);
                                                    else {
                                                        printf(NAME "set_strb_delay 0x%x ok\n", params->strb_delay);
                                                        // set sync delay
                                                        //dio24_set_sync_delay(dma24_dev, params->sync_delay, sr32, err);
                                                        sr32.reg  = DIO_REG_SYNC_DELAY;
                                                        sr32.data = params->sync_delay;
                                                        err = ioctl(dma24_dev, DIO24_IOCTL_SET_REG, &sr32);
                                                        if(err != 0) printf(NAME "set_sync_delay %d error %d\n",  params->sync_delay, err);
                                                        else { 
                                                            printf(NAME "set_sync_delay %d ok\n",  params->sync_delay);
                                                            // prepare RX + TX buffers
                                                            samples = 0;
                                                            err = 0;
                                                            next = data;
                                                            while (next != NULL) {
                                                                if((next->data != NULL) && (next->samples != 0)) {
                                                                    err = write(dma24_dev, next->data, next->samples * DIO_BYTES_PER_SAMPLE);
                                                                    if (err < 0) break;
                                                                    else if (err != (next->samples*DIO_BYTES_PER_SAMPLE)) {
                                                                        err/=DIO_BYTES_PER_SAMPLE;
                                                                        printf(NAME "warning: written %d/%d samples (ignore)\n", err, next->samples);
                                                                        sleep_ms(10);
                                                                        //err = -1;
                                                                        //break;
                                                                        samples += err;
                                                                    }
                                                                    else samples += next->samples;
                                                                }
                                                                next = next->next;
                                                            }
                                                            if(err < 0) printf(NAME "prepare TX+RX %d samples error %d (%d)\n", samples, errno, err);
                                                            else {
                                                                printf(NAME "prepare TX+RX %d samples ok\n", samples);sleep_ms(10);
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                                if (err >= 0) {
                                    // start transmission
                                    stp.cycles = params->cycles;
                                    stp.flags  = params->start_flags;
                                    //err = dma24_start(dma24_dev, &stp);
                                    err = ioctl(dma24_dev, DMA24_IOCTL_START,&stp);
                                    if(err < 0) printf(NAME "start error %d\n", err);
                                    else {
                                        printf(NAME "start ok (%d)\n", err);
                                        sleep_ms(10);
                                        // read and verify data until returns 0 (or error)
                                        err = 0;
                                        first = next = data;
                                        s_max = (params->cycles * samples) ? params->cycles * samples : TEST_REPS_MAX * samples;
                                        s_act = s_drop = cnt = d_cnt = 0;
                                        t_old = get_ticks();
                                        for(; (s_act < s_max) && (!err);) {
                                            //load = dma24_get_load(dma24_dev);
                                            if (params->poll_ms != 0) {
                                                // poll status
                                                sleep_ms(params->poll_ms);
                                                //err = dio24_get_status_run(dma24_dev, &st_run);
                                                err = ioctl(dma24_dev, DIO24_IOCTL_GET_STATUS_RUN, &st_run);
                                                if (err) {
                                                    printf(NAME "FPGA poll status error %d (%d)!\n", errno, err);
                                                }
                                                else {
                                                    printf(NAME "FPGA poll status 0x%8x %8u us (%s)\n", st_run.status, st_run.board_time, FPGA_status_str(st_run.status)); 
                                                    if (st_run.status & (DIO_STATUS_RUN|DIO_STATUS_WAIT)) continue;
                                                    else break;
                                                }
                                            }
                                            else if (params->verify) {
                                                // read from dma24 device = read data on RX channel
                                                err = read(dma24_dev, buffer, TEST_BYTES);
                                                if (err == 0) {
                                                    // timeout: continue when running or wait.
                                                    // either at end or when few data over long time.
                                                    //err = dio24_get_status_run(dma24_dev, &st_run);
                                                    err = ioctl(dma24_dev, DIO24_IOCTL_GET_STATUS_RUN, &st_run);
                                                    printf(NAME "READ timeout (ok). status 0x%8x %8u us (%s)\n", st_run.status, st_run.board_time, FPGA_status_str(st_run.status)); 
                                                    if (st_run.status & (DIO_STATUS_RUN|DIO_STATUS_WAIT)) continue;
                                                    else break;
                                                }
                                                else if ((err == -1) && (errno == ERROR_DMA_INACTIVE)) {
                                                    // DMA has stopped: happens only at end.
                                                    //err = dio24_get_status_run(dma24_dev, &st_run);
                                                    err = ioctl(dma24_dev, DIO24_IOCTL_GET_STATUS_RUN, &st_run);
                                                    if ( (!err) && ((st_run.status & DIO_STATUS_END) == DIO_STATUS_END) ) {
                                                        printf(NAME "READ DMA stopped (ok). status 0x%8x %8u us (%s)\n", st_run.status, st_run.board_time, FPGA_status_str(st_run.status)); 
                                                    }
                                                    else {
                                                        printf(NAME "READ DMA stopped (error). status 0x%8x %8u us (%s), error %d (%d)\n", st_run.status, st_run.board_time, FPGA_status_str(st_run.status), err, errno); 
                                                        err = -ERROR_DMA_INACTIVE;
                                                    }
                                                    break;
                                                }
                                                else if (err < 0) {
                                                    printf("\n" NAME "***   read error %d (%d)!   *** \n\n", err, errno);
                                                    break; 
                                                }
                                                else {
                                                    s_more += err / DIO_BYTES_PER_SAMPLE; // samples since last output
                                                    ++cnt;                                // loops since last output
                                                    t_act = get_ticks();
                                                    if((t_act - t_old) > 200000) {
                                                        //if (dio24_get_status_run(dma24_dev, &st_run) != 0) { // error
                                                        if (ioctl(dma24_dev, DIO24_IOCTL_GET_STATUS_RUN, &st_run)) {
                                                            st_run.status = st_run.board_time = 0xffffffff;
                                                        }
                                                        printf(NAME "read # %d %8u us %u/%u/%u #/last/loops status 0x%x (%s)\n", 
                                                            st_run.board_samples, st_run.board_time,
                                                            s_more,   err / DIO_BYTES_PER_SAMPLE, cnt, 
                                                            st_run.status, FPGA_status_str(st_run.status)
                                                            );
                                                        t_old = t_act;
                                                        s_more = cnt = 0;
                                                    }
                                                    
                                                    // verify data:
                                                    // s_act  = actual samples index
                                                    // s_drop = dropped samples
                                                    //if (do_verify) err = verify_data(first, next, d_cnt, s_act, s_drop, buffer, err, samples);
                                                    uint32_t s_buf = err/DIO_BYTES_PER_SAMPLE, s_old = s_act;
                                                    if (err % DIO_BYTES_PER_SAMPLE) {
                                                        printf(NAME "verify_data: %u bytes is not integer multipe of %u bytes/samples!\n", err, DIO_BYTES_PER_SAMPLE);
                                                        err = -15;
                                                        break;
                                                    }
                                                    err = verify_data2(first, buffer, s_buf, &s_act);
                                                    if (err) {
                                                        printf("\n" NAME "***   verify error %d!   *** \n\n", err); 
                                                        break;
                                                    }
                                                    else { 
                                                        // verify might have skiped samples since searches for matching time
                                                        s_drop += s_act - s_old - s_buf; 
                                                    }
                                                }
                                            }
                                            else {
                                                // read from dio24 device = wait for FPGA IRQ
                                                sleep_ms(10);
                                                err = read(dio24_dev, &st_run, sizeof(struct FPGA_status_run));
                                                if (err == 0) printf(NAME "FPGA read status timeout!\n");
                                                if (err < 0) {
                                                    if ((errno == ETIMEDOUT)||(errno == -ETIMEDOUT)) { // timeout 
                                                        ++cnt;
                                                        printf(NAME "%u/%u samples timeout %d/%d\n", s_act, s_max, cnt, TEST_T_LOOPS);
                                                        err = 0;
                                                        if (cnt >= TEST_T_LOOPS) break;
                                                        continue;
                                                    }
                                                    else {
                                                        printf(NAME "FPGA read error %d (%d)!\n", errno, err);
                                                    }
                                                }
                                                else if (err != sizeof(struct FPGA_status_run)) printf(NAME "FPGA read %d/%d bytes?\n", err, sizeof(struct FPGA_status_run));
                                                else {
                                                    err = 0;
                                                    printf(NAME "FPGA status 0x%8x %8u us (%s)\n", st_run.status, st_run.board_time, FPGA_status_str(st_run.status)); 
                                                    if (st_run.status & (DIO_STATUS_RUN|DIO_STATUS_WAIT)) continue;
                                                    else break;
                                                }
                                            }
                                        } // next loop
                                        
                                        // print status before sending stop command
                                        sleep_ms(10);
                                        get_status(dma24_dev);
                                        status_show = true;

                                        //printf(NAME "wait 5s ...\n");
                                        //sleep(5);

                                        //if(dma24_stop(dma24_dev, 0L) <0 ) printf(NAME "stop error!\n");
                                        if(ioctl(dma24_dev, DMA24_IOCTL_STOP, 0L) < 0) printf(NAME "stop error!\n");
                                        else {
                                            sleep_ms(10);
                                            printf(NAME "stop ok\n");
                                        }
                                        sleep_ms(10);
                                    }
                                }
                            }
                        }
                    }
                    free(buffer);
                }
            }

            // show status also on error
            sleep_ms(100);
            if (!status_show) {
                get_status(dma24_dev);            
                sleep_ms(10);
            }
            
            // print result for different conditions
            if (params->verify) { 
                // read & verify and no verification error
                if( ( (err == EWOULDBLOCK) || (err == 0)                 ) &&
                    ( s_act == s_max                                     ) &&
                    ( s_drop == (status.RD_bt_drop/DIO_BYTES_PER_SAMPLE) ) && 
                    ( status.TX_bt_tot == status.RX_bt_tot               ) && 
                    ( status.TX_bt_tot == s_max*DIO_BYTES_PER_SAMPLE     ) 
                  ) {
                    // all verified samples ok, maybe dropped samples but samples TX == RX == verified + dropped
                    printf("\n" NAME "***   %u/%u samples verify ok! %u dropped (%d)  ***\n\n", s_act-s_drop, s_max, status.RD_bt_drop/DIO_BYTES_PER_SAMPLE, err);
                }
                else {
                    if(!err) err = -4; // most likely wrong numbers of samples
                    printf("\n" NAME "***   %u/%u samples verified, %u (%u) dropped, error %d!   *** \n\n", s_act-s_drop, s_max, s_drop, status.RD_bt_drop/DIO_BYTES_PER_SAMPLE, err);
                }
            } 
            else { // no verification
                if( (status.TX_bt_tot == status.RX_bt_tot) && 
                        (status.TX_bt_tot == samples*DIO_BYTES_PER_SAMPLE) && 
                        ((status.RD_bt_drop + status.RD_bt_act)/DIO_BYTES_PER_SAMPLE == samples) && 
                        (err == 0) 
                      ) {
                    printf("\n" NAME "***   %u/%u samples ok! %u dropped (%d)  ***\n\n", s_max, samples, status.RD_bt_drop/DIO_BYTES_PER_SAMPLE, err);
                }
                else {
                    if(!err) err = -5; // wrong number of samples
                    printf("\n" NAME "***   %u/%u/%u samples, %u dropped, error %d!   *** \n\n", status.TX_bt_tot/DIO_BYTES_PER_SAMPLE, status.RX_bt_tot/DIO_BYTES_PER_SAMPLE, s_max, status.RD_bt_drop/DIO_BYTES_PER_SAMPLE, err);
                }
            }

            // close dio24 device
            sleep_ms(20);
            //dio24_close(dio24_dev);
            close(dio24_dev);
        }
        // close dma24 device
        //dma24_close(dma24_dev);
        close(dma24_dev);
    }

    return err;
}

// calculates strobe delay from strobe delay string "r0:r1:r2:level"
// returns 0 on error
uint32_t get_strb_delay(char *str[MAX_NUM_RACKS], uint32_t scan_Hz) {
    uint32_t r0, r1, r2, level = 1, delay = 0;
    int num, i;
    for (i = 0; i < MAX_NUM_RACKS; ++i) {
        if (str[i] == NULL) return 0;                                   // no strobe given
        num = sscanf(str[i], "%u:%u:%u:%u", &r0, &r1, &r2, &level);
        if (num >= 3) {                                                 // at least r0-r2 are given. 
            if (num == 3) level = 1;                                    // set default level if not given
            r2 = r0 + r1 + r2;
            if (level == 1) {                                           // active high
                r1 = (((r0 + r1) * BUS_CLOCK_FREQ_HZ / scan_Hz) / r2 - 1) & STRB_DELAY_MASK; // end   time in BUS_CLOCK_FREQ_HZ cycles
                r0 = (( r0       * BUS_CLOCK_FREQ_HZ / scan_Hz) / r2)     & STRB_DELAY_MASK; // start time in BUS_CLOCK_FREQ_HZ cycles
            }
            else if (level == 2) {                                      // toggle bit (end = 0)
                r1 = 0;
                r0 = (( r0       * BUS_CLOCK_FREQ_HZ / scan_Hz) / r2)     & STRB_DELAY_MASK; // toggle time in BUS_CLOCK_FREQ_HZ cycles
            }
            else return 0;                                              // invalid level
            delay |= (r1 << ((i*MAX_NUM_RACKS+1)*STRB_DELAY_BITS)) | (r0 << (i*MAX_NUM_RACKS*STRB_DELAY_BITS));
        }
        else return 0;                                                  // invalid input
    }
    return delay;
}

// CSV filename and number of columns to arrange data
#define FILE_NAME       "/mnt/sd/result.csv"
#define FILE_COLS       12

// reads list of integers from string at given byte offset
// str     = string of bytes bytes in the form "#,#,#,".
//           allowed separators are single ',' or '\t' and multiple '\r', '\n' 
//           blank space ' ' is ignored.
//           if # starts with "0x" integer is interpreted as hexadecimal
// bytes   = number of bytes in str.
//           if bytes = 0 str must be terminated with "\0" and no termination can be given, i.e. term = "".
//           returns number of read bytes
// list    = array of maximum entries 32bit unsigned integer which are filled by function
// entries = maximum number of entries in list.
//           returns number of read entries 
// next    = index of first character of next uncompleted entry
// start   = string with possible starting characters, e.g. "([{", empty if no starting character needed. 
// sep     = string with possible separator characters, e.g. ",\t ", can be empty if only one entry needed.
// term    = string with possible terminating characters, e.g. ")]}", empty if no ending character needed.
// ignore  = string with possible ignored characters, e.g. " _", empty if no character should be ignored.
// returns 0 if ok otherwise error
int read_list(char *str, unsigned *bytes, uint32_t *list, unsigned *entries, unsigned *next, const char *start, const char *sep, const char *term, const char *ignore) {
    uint32_t value = 0;
    uint32_t basis = 10;
    int i = 0, j = 0, k, first = 0, error = 0;
    unsigned bt = (*bytes == 0) ? 0xffffffff : *bytes;
    if (bt < 1) error = -1;
    else {
        // check starting character
        // TODO: ignored character is allowed before starting character
        if (start[0] != '\0') {
            // error if no starting character
            error = -2;
            for (k = 0; start[k] != '0'; ++k) {
                if (*str == start[k]) { // ok
                    i = first = 1; // set first character of number
                    ++str;
                    error = 0;
                    break;
                }
            }
        }
    }
    if (!error) {
        for (; (!error) && (i < bt) && (j < *entries); ++i, ++str) {
            switch (*str) {
                case '0':
                case '1':
                case '2':
                case '3':
                case '4':
                case '5':
                case '6':
                case '7':
                case '8':
                case '9':
                    value = value*basis + uint32_t((*str)-'0');
                    break;
                case 'a':
                case 'b':
                case 'c':
                case 'd':
                case 'e':
                case 'f':
                    if (basis != 16) error = -3; // illegal character or wrong basis
                    else value = value*basis + uint32_t((*str)-'a') + 10;
                    break;
                case 'A':
                case 'B':
                case 'C':
                case 'D':
                case 'E':
                case 'F':
                    if (basis != 16) error = -3; // illedal character or wrong basis
                    else value = value*basis + uint32_t((*str)-'A') + 10;
                    break;
                case 'x': // hex basis?
                    if (i == (first + 1)) { // number must start with "0x"
                        if (*(str-1) == '0') basis = 16;
                        else error = -4; // illegal character
                    }
                    else error = -5; // illegal character
                    break;
                case '\0': 
                    // 0-termination only allowed when bytes == 0 and empty term == ""
                    // this is like termination with '\0'
                    if ((*bytes == 0) && (term[0] == '\0')) {
                        list[j++] = value;
                        first = i + 1; // first character of next entry
                        error = 1;
                    }
                    else error = -6;
                    break;
                default:
                    // other character
                    for (k = 0; ignore[k] != '\0'; ++k) {
                        if (*str == ignore[k]) { // ignored character
                            if (first == i) ++first; // shift first character of next entry
                            break;
                        }
                    }
                    if (ignore[k] == '\0') {
                        for (k = 0; sep[k] != '\0'; ++k) {
                            if (*str == sep[k]) { // separation character: next entry
                                if (i == first) error = -7; // empty entry not allowed
                                else {
                                    //printf("sep %u %u %c\n", i, j, sep[k]);
                                    list[j++] = value;
                                    first = i + 1; // first character of next entry
                                    basis = 10;
                                    value = 0;
                                }
                                break;
                            }
                        }
                        if (sep[k] == '\0') {
                            for (k = 0; term[k] != '\0'; ++k) {
                                if (*str == term[k]) { // termination character: return
                                    if (i == first) error = -8; // empty entry not allowed
                                    else {
                                        list[j++] = value;
                                        first = i + 1; // first character of next entry
                                        error = 1;
                                    }
                                    break;
                                }
                            }
                            if (term[k] == '\0') { // illegal character
                                printf("illegal character at index %u '%c'\n", i, *str);
                                error = -9;
                            }
                        }
                    }
            }
        }
        if (error == 1) {
            // termination character or '\0'
            // return number of bytes including termination or '\0'
            error = 0;
        }
        else if (error) {
            // error: bytes = index of bad character = read good character
            // note: for-loop increments i before checking error
            --i;
        }
        else if (term[0] != '\0') {
            // termination required but missing
            error = -10;
        }
        else {
            // no termination required: bytes or entries reached
        }
    }

    // return number of bytes, read entries, first next character and error code
    *bytes   = i;
    *entries = j;
    *next    = first;
    return error;
}

// reads samples data
// definition of sample data
// give list of decimal or hex (with '0x') 32bit integers separated with comma or new line
// first integer = time in units of 1/bus output rate
// second integer = 16bit data + 7 or 8 bits of address and optional STRB, STOP, NOP bits
// comments can be inserted with "//" at beginning of line or after data but not within data
// new lines can be inserted instead of comma. empty lines are ok.
// TODO:
// comments in this function are handled not conforming to C-style!
// this is for simplicity and due to lack of time to fix it.
// - a single '/' in empty lines is recognized as comment. we do not enforce second '/'.
// - in lines with 2 valid entries two "//" are required: the first is used as termination and the second to skip rest (as empty line).
// - "/*" would work in empty lines but will skip entire line and does not look for closing "*/"
#define BUFFER_CHARS            256
#define ALLOC_SAMPLES           1024
int read_file(char *filename, struct data_info *&data) {
    int err = 0;
    unsigned buf_bytes = 0, buf_index = 0, bytes, entries = 0, next_index, tot_bytes = 0, tot_buf = 0, tot_samples = 0;
    char *buffer;
    struct data_info *next;
    int fd;
    bool eof = false, skip = false;
    fd = open(filename, O_RDONLY);
    if (fd == -1) err = -errno;
    else {
        buffer = (char*) malloc(BUFFER_CHARS+1);
        if (buffer == NULL) err = -11;
        else {
            buffer[BUFFER_CHARS] = '\0';
            data = (struct data_info *) malloc(sizeof(struct data_info));
            if (data == NULL) err = -12;
            else { 
                next = data;
                next->next    = NULL;
                next->samples = 0;
                next->data    = (uint32_t*) malloc(DIO_BYTES_PER_SAMPLE*ALLOC_SAMPLES);
                if (next->data == NULL) err = -13;
                else {
                    while(!err) {
                        if ( (buf_index >= buf_bytes) && (!eof) ) {
                            // read data from file until end of file (EOF)
                            err = read(fd, buffer + buf_bytes, BUFFER_CHARS - buf_bytes);
                            if (err <= 0) { // EOF
                                eof = true;
                                if (buf_bytes > 0) err = -21;
                                break;
                            }
                            else buf_bytes += err;
                            if (skip) {
                                // comment at end of buffer, skip until first newline
                                char *p = buffer;
                                for(buf_index = 0; buf_index < buf_bytes; ++buf_index, ++p) {
                                    if (*p == '\n') {
                                        skip = false;
                                        break;
                                    }
                                }
                                tot_bytes += buf_index;
                                if (skip) {
                                    // read next buffer
                                    continue;
                                }
                            }
                            else buf_index = 0;
                            buffer[buf_bytes] = '\0'; // for printing
                            //printf("read buffer %u bytes:\n%s\n", buf_bytes, buffer);
                            
                        }
                        
                        // read one sample = 2 entries from buffer
                        bytes      = buf_bytes - buf_index;     // remaining bytes in buffer
                        entries    = DIO_BYTES_PER_SAMPLE/4;    // 1 sample = 2 entries to be inserted into next->data
                        next_index = 0;                         // index of next unread sample
                        err = read_list(buffer + buf_index, &bytes, next->data + next->samples*DIO_BYTES_PER_SAMPLE/4, 
                                        &entries, &next_index, "", ",", "\n/", " \t\r");
                        
                        //printf("reading %u bytes at offset %u: bytes %u, entries %u, next %u, error %d\n%s\n", 
                        //        buf_bytes - buf_index, buf_index, bytes, entries, next_index, err, buffer + buf_index);
                        
                        // check error
                        if (err) {
                            if (err == -10) { 
                                // unterminated: buffer not long enough
                                // copy remaining bytes to beginning of buffer
                                char *p = buffer + buf_index, *q = buffer;
                                for(unsigned i = buf_index; i < buf_bytes; ++i, ++p, ++q) *q = *p;
                                buf_bytes -= buf_index; // read new data from file after this 
                                buf_index = buf_bytes;
                                err = 0;
                                continue;
                            }
                            else if ((err == -8) && (bytes == next_index) && (entries == 0)) {
                                unsigned i = buf_index + bytes;
                                char *p = buffer + i;
                                if (*p == '/') {
                                    // skip empty line with comment until end of line or end of buffer
                                    for(++i; i < buf_bytes; ++i, ++p) {
                                        if (*p == '\n') {
                                            buffer[i-1] = '\0';
                                            //printf("skip empty comment at index %u - %u '%s'\n", buf_index + bytes, i, buffer + buf_index + bytes);
                                            break;
                                        }
                                    }
                                    if (i == buf_bytes) {
                                        buf_bytes = 0;
                                        skip = true; // end of buffer
                                    }
                                    next_index = i - buf_index;
                                }
                                else {
                                    // skip empty line
                                    //printf("skip empty line at index %u\n", bytes);
                                    ++next_index;
                                }
                                tot_bytes += next_index;
                                buf_index += next_index;
                                if (buf_index >= buf_bytes) buf_bytes = 0; // load next buffer
                                err = 0;
                                continue;
                            }
                        }
                        else if (entries != 2) err = - 14; // should not happen 
                                                
                        if (!err) {
                            // update entries counter and reallocate sample buffer if needed
                            tot_bytes += next_index;
                            buf_index += next_index;
                            if (buf_index >= buf_bytes) buf_bytes = 0; // load next buffer
                            ++next->samples;                      
                            
                            //show_data2(data, NULL, next->samples, 0, 0);
                            
                            if (next->samples == ALLOC_SAMPLES) {
                                // buffer full
                                ++tot_buf;
                                tot_samples += next->samples;
                                next->next = (struct data_info *) malloc(sizeof(struct data_info));
                                if (next->next == NULL) err = -15;
                                else {
                                    next = next->next;
                                    next->next    = NULL;
                                    next->samples = 0;
                                    next->data    = (uint32_t*) malloc(DIO_BYTES_PER_SAMPLE*ALLOC_SAMPLES);
                                    if (next->data == NULL) err = -16;
                                }
                            }
                        }
                    } // read next data into buffer. stop if EOF.
                    
                    ++tot_buf;
                    tot_samples += next->samples;
                    printf("total %u bytes, %u samples and %u buffer read\n", tot_bytes, tot_samples, tot_buf);
                    next = data;
                    while(next) {
                        show_data2(next, NULL, next->samples, 0, 0);
                        next = next->next;
                    }
                }
            }
            free(buffer);
        }
        close(fd);
    }
    if (err) {
        while(data) {
            struct data_info *next = data->next;
            free(data->data);
            free(data);
            data = next;
        }
    }
    return err;
}

// main program
int main(int argc, char *argv[])
{
    static char strb_default[] = STRB_DELAY_STR;
    char *strb_str[MAX_NUM_RACKS] = {strb_default,strb_default};
    int err = 0, opt, dma24_dev, rep;
    unsigned bytes, entries, next;
    int send_data = 0, num_cpu = 2;
    char *cmd;
    TP params = {
        .clk_div        = CLK_DIV_DEFAULT,
        .ctrl           = CTRL_FPGA,
        .ctrl_in        = CTRL_IN_DEFAULT,
        .ctrl_out       = CTRL_OUT_DEFAULT,
        .samples        = NUM_SAMPLES,
        .cycles         = NUM_CYCLES,
        .reps           = NUM_REPS,
        .strb_delay     = STRB_DELAY,
        .sync_delay     = SYNC_DELAY,
        .poll_ms        = 0,
        .start_flags    = START_FLAGS,
        .filename       = NULL,
        .verify         = false,
        .ext_clk        = false,
    };
    struct st_par stp;
    bool reset = false;
#ifdef _DEBUG
    printf("\n*** %s ... (with _DEBUG flag) ***\n\n, argv[0]");
#else
    printf("\n*** %s ... ***\n\n", argv[0]);
#endif

    while ((opt = getopt(argc, argv, ":d:xn:c:r:vp:s:i:o:w:b:f:R")) != -1) {
        switch (opt) {
            case 'd': 
                if ((atol(optarg) < CLK_DIV_MIN) || (atol(optarg) > CLK_DIV_MAX)) {
                    printf(NAME "clock divider = %d out of range [%u, %u]\n", params.clk_div, CLK_DIV_MIN, CLK_DIV_MAX); 
                    err = -10;
                }
                else {
                    params.clk_div = atol(optarg); 
                    printf(NAME "clock divider       = %d\n", params.clk_div); 
                }
                break;
            case 'x': params.ext_clk     = true        ; printf(NAME "use external clock\n")                           ; break;
            case 'n': params.samples     = atol(optarg); printf(NAME "samples             = %d\n", params.samples)     ; break;
            case 'c': params.cycles      = atol(optarg); printf(NAME "cycles (w/o upload) = %d\n", params.cycles)      ; break;
            case 'r': params.reps        = atol(optarg); printf(NAME "reps (with upload)  = %d\n", params.reps)        ; break;
            case 'p': params.poll_ms     = atol(optarg); printf(NAME "poll every %u ms\n"        , params.poll_ms)     ; break;
            case 's': params.start_flags = atol(optarg); printf(NAME "start flags %u ms\n"       , params.start_flags) ; break;
            case 'v': params.verify      = true        ; printf(NAME "read & verify\n")                                ; break;
            case 'f': params.filename    = optarg      ; printf(NAME "read samples file   = '%s'\n", params.filename)  ; break;
            case 'w': params.sync_delay  = atol(optarg); printf(NAME "sync_delay          = %d\n"  , params.sync_delay); break;
            case 'b': // strb_delay
                bytes   = 0;
                entries = 1;
                next    = 0;
                err = read_list(optarg, &bytes, &params.strb_delay, &entries, &next, "", "", "", "");
                if (err == 0) {
                    if (entries != 1) err = -11;
                    else {
                        printf(NAME "strb_delay        = 0x%x\n", params.strb_delay); 
                    }
                }
                break;
            case 'i': // ctrl_in list [#,#]
                bytes   = 0;
                entries = 2;
                next    = 0;
                err = read_list(optarg, &bytes, params.ctrl_in, &entries, &next, "[", ",", "]", "");
                if ((err == 0) && (entries == 2)) printf(NAME "ctrl_in             = [0x%x,0x%x]\n", params.ctrl_in[0], params.ctrl_in[1]); 
                else                              printf(NAME "error %d reading ctrl_in '%s'\n", err, optarg);
                break;
            case 'o': // ctrl_out list [#,#]
                bytes   = 0;
                entries = 2;
                next    = 0;
                err = read_list(optarg, &bytes, params.ctrl_out, &entries, &next, "[", ",", "]", "");
                if ((err == 0) && (entries == 2)) printf(NAME "ctrl_out            = [0x%x,0x%x]\n", params.ctrl_out[0], params.ctrl_out[1]); 
                else                              printf(NAME "error %d reading ctrl_out '%s'\n", err, optarg);
                break;
            case 'R': reset = true;                      printf(NAME "reset board\n")                                ; break;
            case '?':                                    printf(NAME "illegal option!\n"); err = -3                  ; break;
            case ':':                                    printf(NAME "give a value!\n")  ; err = -3                  ; break;
            default:                                     printf(NAME "invalid option!\n"); err = -3                  ; break;
        }
        if(err) break;
    }
    
    if (err) {
        printf("%s: error %d (%d)\n\n", argv[0], err, errno);
        printf("%s options:\n", argv[0]);
        printf("-d #      set # = clock divider (%u..%u)     default %u\n", CLK_DIV_MIN, CLK_DIV_MAX, params.clk_div);
        printf("-x        use external clock                 default internal\n");
        printf("-n #      set # = number samples             default %u\n", NUM_SAMPLES);
        printf("-c #      set # = number cycles (w/o upload) default %u\n", NUM_CYCLES);
        printf("-r #      set # = number reps. (with upload) default %u\n", NUM_REPS);
        printf("-p #      poll status every # ms             default wait irq w/o read\n");
        printf("-s #      set # = start params               default %d\n", START_FLAGS);
        printf("-v        read and verify data               default wait irq w/o read\n");
        printf("-i [#,#]  set # = ctrl_in0/1                 default [0x%x,0x%x]\n", params.ctrl_in[0], params.ctrl_in[1]);
        printf("-o [#,#]  set # = ctrl_out0/1                default [0x%x,0x%x]\n", params.ctrl_out[0], params.ctrl_out[1]);
        printf("-b #      set # = strb_delay                 default 0x%x\n", STRB_DELAY);
        printf("-w #      set # = waiting time in 10ns steps default %d\n", SYNC_DELAY);
        printf("-f <name> set <sample file name>             default none\n");
        printf("-R        reset if not specified -n or -f\n");
    }
    else {
        // no error
        if (params.strb_delay == 0) { 
            // calculate strobe delay from string
            params.strb_delay = get_strb_delay(strb_str, BUS_CLOCK_FREQ_MHZ*MHZ/params.clk_div);
            if (params.strb_delay == 0) {
                printf(NAME "error strobe delay\n");
                err = -10;
            }
            else {
                printf(NAME "strobe delay 0x%08x\n", params.strb_delay);
            }
        }
    }    

    if(!err) {
        sleep_ms(10);
        if ((params.samples > 0) || (params.filename != NULL)) {
            for (rep = 0; (rep < params.reps) && (!err); ++rep) {
                printf("\n" NAME "***   repetition %u/%u  ***\n\n", rep + 1, params.reps);
                struct data_info *data = NULL, *next, *last = NULL;
                if (params.filename != NULL) {
                    // read samples from file
                    err = read_file(params.filename, data);
                }
                else {
                    // generate samples
                    data = (struct data_info *) malloc(sizeof(struct data_info));
                    if (data) {
                        data->next = NULL;
                        data->samples = params.samples;
                        data->data = test_step(data->samples, 0, 1, 0x030201, 0x010101);
                    }
                }
                if (data) {
                    err = check_data(data, 10);
                    sleep_ms(100);
                    if (!err) {
                        err = write_read_test(data, &params);
                    }
                    while(data) {
                        next = data->next;
                        free(data->data);
                        free(data);
                        data = next;
                    }
                }
            } // next repetition
        }
        else {
            // read dma24_dev status & lock/unlock from external clock
            printf(NAME "read status ...\n");
            //dma24_dev = dma24_open(0);
            dma24_dev = open(DMA24_DEVICE_FILE_NAME(0), O_RDWR | O_SYNC);
            if(dma24_dev <= 0) {
                err = -1;
                printf(NAME "open error\n");
            }
            else {
                err = get_status(dma24_dev);
                sleep_ms(20);
                if(err) {
                    printf(NAME "get_status error = %d (%d)\n", errno, err);
                    // try get_status_run
                    memset(&st_run, 0, sizeof(struct FPGA_status_run));
                    //err = dio24_get_status_run(dma24_dev, &st_run);
                    err = ioctl(dma24_dev, DIO24_IOCTL_GET_STATUS_RUN, &st_run);
                    sleep_ms(100); // this might avoid that driver messages are printed between status.
                    if(err != 0) printf(NAME "get_status_run failed with error %d (%d)!\n", errno, err);
                    else {
                        //printf(NAME "FPGA ctrl     0x%8x\n", dio24_get_config(dma24_dev));
                        struct set_reg32 sr32 = { .reg = DIO_REG_CTRL, .data = 0 };
                        err = ioctl(dma24_dev, DIO24_IOCTL_GET_REG, &sr32);
                        if (err) printf(NAME "get config failed with error %d (%d)\n", errno, err);  
                        else {
                            printf(NAME "FPGA ctrl     0x%8x\n", sr32.data);
                            printf(NAME "FPGA status   0x%8x %8u us (%s)\n", st_run.status, st_run.board_time, FPGA_status_str(st_run.status)); 
                            //printf(NAME "DMA ctrl      0x%8x\n", dma24_get_config(dma24_dev)); 
                            //printf(NAME "DMA status TX 0x%8x\n", dma24_get_status_TX(dma24_dev)); 
                            //printf(NAME "DMA status RX 0x%8x\n", dma24_get_status_RX(dma24_dev)); 
                            printf(NAME "DMA ctrl      0x%8x\n", ioctl(dma24_dev, DMA24_IOCTL_GET_CONFIG, 0)); 
                            printf(NAME "DMA status TX 0x%8x\n", ioctl(dma24_dev, DMA24_IOCTL_GET_STATUS_TX, 0)); 
                            printf(NAME "DMA status RX 0x%8x\n", ioctl(dma24_dev, DMA24_IOCTL_GET_STATUS_RX, 0)); 
                        }
                    }
                }
                else printf(NAME "get_status (ok)\n");
                sleep_ms(20);
                
                if (reset) {
                    // reset dma24_dev which also cleans buffers
                    //err = dma24_reset(dma24_dev);
                    err = ioctl(dma24_dev, DMA24_IOCTL_RESET, NULL);
                    if(err < 0) printf(NAME "reset error %d (0x%X)\n", err, err);
                    else {
                        printf(NAME "reset ok.\n");
                    }
                }
                //dma24_close(dma24_dev);
                close(dma24_dev);
            }
        }
    }

    return err;
}


