////////////////////////////////////////////////////////////////////////////////////////////////////
// fpga-test
// 32bit Linux console application to be run on Xilinx Zynq-7020 FPGA with Petalinux
// created 2018/07/08 by Andi
// last change 2023/9/30 by Andi
// compiled with g++ on Ubuntu 18.04 LTS, 20.04 LTS
// tested with Petalinux 2017.4, 2020.1
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

#include "dio24/dio24_driver.h"     // public driver definitions
#include "dio24/driver.h"           // convenience IOCTL macros
#include "data_xy.h"                // definition of data_xy

#include "dio24-share/common.h"         // socket definitions
#include "dio24-share/dio24_server.h"   // public server definitions

//#include <libusb-1.0/libusb.h>          // libusb [TODO: include is working but linking not]
#include <linux/usb/tmc.h>              // usbtmc specific definitions

#define NAME "dma24_test: "

// settings for test
#define TEST_OUT_FREQ_HZ    (1*MHZ)                         // bus output clock frequency in Hz
#define TEST_BYTES          (15000*DIO_BYTES_PER_SAMPLE)    // buffer size in bytes for read()
#define TEST_REPS           1                               // number of repetitions
#define TEST_TIMEOUT        1000                            // timeout in ms
#define TEST_T_LOOPS        32                              // number of timeouts before stop()
#define TEST_REPS_MAX       125                             // number of repetitions before stop()
#define TEST_ONERR_READ     false                           // after verify error continue read(), otherwise waits until FPGA and DMA finished
#define TEST_POLL           false                           // poll with dio24_get_status_FPGA(dma24_dev) or wait for FPGA IRQ by read(dio24_dev)

// DIO_BYTES_PER_SAMPLE dependent settings
#if DIO_BYTES_PER_SAMPLE == 8
    #define TEST_CONFIG            DIO_CONFIG_RUN_64 | DIO_CTRL_AUTO_SYNC_EN | DIO_CTRL_AUTO_SYNC_PRIM
    #define ADD_ZERO_PP(p)
    #define SHOW_DATA(p)            printf("0x %08lx %08lx = %8lu us\n", i, *p, *(p+1), *p);
    #define SHOW_DATA_I(i,p)        printf("%6u: 0x %08lx %08lx = %8lu us\n", i, *p, *(p+1), *p);
    #define SHOW_DATA_IC(i,p,comment)    printf("%6u: 0x %08lx %08lx = %8lu us (%s)\n", i, *p, *(p+1), *p, comment);
    #define EXPAND96(data,num)        data
    #define EXPAND96_FREE            false
#elif DIO_BYTES_PER_SAMPLE == 12
    #define TEST_CONFIG            DIO_CONFIG_RUN_96 | DIO_CTRL_AUTO_SYNC_EN | DIO_CTRL_AUTO_SYNC_PRIM       //DIO_CTRL_IRQ_ALL|DIO_CTRL_RESTART_EN|DIO_CTRL_BPS96
    #define ADD_ZERO_PP(p)            *p++ = 0
    #define SHOW_DATA(p)            printf("0x %08lx %08lx %08lx = %8lu us\n", i, *p, *(p+1), *(p+2), *p);
    #define SHOW_DATA_I(i,p)        printf("%6u: 0x %08lx %08lx %08lx = %8lu us\n", i, *p, *(p+1), *(p+2), *p);
    #define SHOW_DATA_IC(i,p,comment)    printf("%6u: 0x %08lx %08lx %08lx = %8lu us (%s)\n", i, *p, *(p+1), *(p+2), *p, comment);
    #define EXPAND96(data,num)        expand64_to_96(data,num)
    #define EXPAND96_FREE            true
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
        printf(NAME "(%d) checking %u samples ... \n", i, data->samples);
        err = show_data(data->data, data->samples, show_max ? show_max : data->samples, t_old);
        if(err) break;
        else printf(NAME "(%d) checking %u samples ok\n", i, data->samples);
        num += data->samples;
        if (t_start == TOLD_INVALID) {
            if (data->samples > 0) t_start = *data->data;
        }
        data = data->next;
        ++i;
    }
    if(err) printf(NAME "check_data error!\n");
    else printf(NAME "check_data %d rounds, %u samples, %u-%u=%u us ok\n", i, num, t_old, t_start, t_old - t_start);
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
    printf("master: waiting for key  = '%c' (%d)\n", key, key);
    do {
        c = fgetc(stdin);
        printf("master: key  = '%c' (%d)\n", c, c);
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

// send data test #4: combination of linear ramps
// data = last allocated data after which new data is added
struct data_info * test_4(struct data_info *data) {
    uint32_t time = 0, *p;
    struct data_info *next, *last = data;
    // combine linear ramps
    // note: time must be incrementing!
    for (int test = 0; test <= 7; ++test) {
        next = (struct data_info *) malloc(sizeof(struct data_info));
        if (next == NULL) break;
        next->next = NULL;
        if (last == NULL) data = next;
        else last->next = next;
        switch ( test ) {
        case 0:
            // send 1us start pulse (enable signal is also sent at same time and causes some oscillations)
            next->samples = 2;
            next->data = p = (uint32_t *)malloc(next->samples*DIO_BYTES_PER_SAMPLE);
            *p++ = time;
            *p++ = (D0 << 16) | (uint16_t)((int16_t)0xffff); // all OFF @ digital out 1
            ADD_ZERO_PP(p);
            *p++ = time+1;
            *p++ = (D0 << 16) | (uint16_t)((int16_t)0); // all OFF @ digital out 1
            ADD_ZERO_PP(p);
            //time += 100;
            break;
        case 1:
            //next->samples = 16;
            //next->data = test_digital(D0, time, time + TSTEP*(next->samples - 1), true);
            // initial state
            next->samples = 3;
            next->data = p = (uint32_t *)malloc(next->samples*DIO_BYTES_PER_SAMPLE);
            *p++ = time;
            *p++ = (A0 << 16) | (uint16_t)((int16_t)0); // 0V @ analog out 0
            ADD_ZERO_PP(p);
            *p++ = time + TSTEP;
            *p++ = (A1 << 16) | (uint16_t)((int16_t)PMAX); // max @ analog out 1
            ADD_ZERO_PP(p);
            *p++ = time + 2*TSTEP;
            *p++ = (D0 << 16) | (uint16_t)((int16_t)0xffff); // all ON @ digital out 0
            ADD_ZERO_PP(p);
            break;
/*        case 1:
            next->samples = STEPS;
            next->data = test_analog(A0, time, time + next->samples - 1, 0, PMAX, next->samples);
            break;*/
        case 2:
            next->samples = STEPS;
            next->data = test_analog(A0, time, time + TSTEP*(next->samples - 1), 0, PMAX, next->samples);
            break;
        case 3:
            next->samples = 2*STEPS-1;
            next->data = test_analog(A1, time, time + TSTEP*(next->samples - 1), PMAX, NMAX, next->samples);
            break;
        case 4:
            next->samples = 2*STEPS-1;
            next->data = test_analog(A0, time, time + TSTEP*(next->samples - 1), PMAX, NMAX, next->samples);
            break;
        case 5:
            next->samples = 2*STEPS-1;
            next->data = test_analog(A1, time, time + TSTEP*(next->samples - 1), NMAX, PMAX, next->samples);
            break;
        case 6:
            next->samples = STEPS;
            next->data = test_analog(A0, time, time + TSTEP*(next->samples - 1), NMAX, 0, next->samples);
            break;
/*        case 7:
            next->samples = STEPS;
            next->data = test_analog(A1, time, time + next->samples - 1, PMAX, 0, next->samples);
            break;*/
        case 7:
            //next->samples = 16;
            //next->data = test_digital(D1, time, time + TSTEP*(next->samples - 1), false);
            // final state
            next->samples = 3;
            next->data = p = (uint32_t *)malloc(next->samples*DIO_BYTES_PER_SAMPLE);
            *p++ = time;
            *p++ = (A0 << 16) | (uint16_t)((int16_t)0); // 0V @ analog out 0
            ADD_ZERO_PP(p);
            *p++ = time + TSTEP;
            *p++ = (A1 << 16) | (uint16_t)((int16_t)0); // 0V @ analog out 1
            ADD_ZERO_PP(p);
            *p++ = time + 2*TSTEP;
            *p++ = (D0 << 16) | (uint16_t)((int16_t) 0x0000); // all OFF @ digital out 0
            break;
        default:
            break;
        }
        time += TSTEP*next->samples;
        last = next;
    }
    return data;
}

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

#define BUFFER_LENGTH    20
int buffer[BUFFER_LENGTH];

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
int get_status(int dev, bool all) {
    int err, i;
    int32_t mT;
    memset(&status, 0, sizeof(struct FPGA_status));
    status.ctrl_FPGA = FPGA_STATUS_SHOW;    // if this is set driver will display status information
    if (all) err = dio24_get_status_dbg(dev, &status);
    else err = dio24_get_status(dev, &status);
    sleep_ms(100); // this might avoid that driver messages are printed between status.
    if(err < 0) printf(NAME "get_status failed with error %d!\n", err);
    else {
        if(err > 0) printf(NAME "get_status warning %d\n", err);
    }
}

// shows s_num samples in data info starting at s_start sample
// if data != NULL shows for comparison data in same column (must contain s_num samples)
//                 first entry index starts with i_start
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
            if(data) { printf("%04d: %8u us %08x | %03d: %8u us %08x\n", s_cnt, *(p), *(p+1), i_start+i-s_start, *data, *(data+1)); data+=2; }
            else printf("%04d: %8u us %08x\n", s_cnt, *(p), *(p+1));
#elif DIO_BYTES_PER_SAMPLE == 12
            if (data) { printf("%04d: %8u us %08x %08x | %03d: %8u us %08x %08x\n", s_cnt, *(p), *(p+1), *(p+2), i_start+i-s_start, *data, *(data+1), *(data+2)); data+=3; }
            else printf("%04d: %8u us %08x %08x\n", s_cnt, *(p), *(p+1), *(p+2));
#endif
        }
    }

}

// verify RX data of bytes length within TX data info of total samples size.
// wraps around when it cannot find time and is at end of data info.
// returns number of found samples. <0 on error.
#define SHOW_SAMPLES    10    // shows data +/- samples around last good sample
int verify_data2(struct data_info *info, uint32_t *data, uint32_t bytes, uint32_t samples) {
    struct data_info *mem = info;
    uint32_t i, j = mem->samples, *p = mem->data, *d = data, s_cnt = 0, s_ok = -1;
    bool restart = true;
//printf(NAME "verify_data: %u bytes\n", bytes);sleep_ms(200);
    bytes /= DIO_BYTES_PER_SAMPLE;
    for (i = 0; i < bytes; --j, ++s_cnt, p += (DIO_BYTES_PER_SAMPLE/4)) {
        if(j == 0) {
            do {
                mem = mem->next;
                if(mem == NULL) {
                    if(restart) { // restart max. 1x without finding data
                        printf(NAME "verify_data: restart\n");sleep_ms(200);
                        mem = info; restart = false; s_cnt = 0; 
                    }
                    else {    // not all data found!
                        if (s_ok != -1) { // show data centered around last good sample @ s_ok and data[i-1]=d-1 (in samples)
                            printf(NAME "verify_data: %u us not found! last good # %u, %u/%u samples\n", *d, s_ok, i, bytes);sleep_ms(200);
                        }
                        else {    // show data with first samples
                            printf(NAME "verify_data: %u us not found! last good # <none!>, %u/%u samples\n", *d, i, bytes);sleep_ms(200);
                            s_ok = 0; i=1; d++; // as if first sample would be last good
                        }
                        uint32_t s_start, i_start, i_end;
                        i_start = (i >= (1+SHOW_SAMPLES)) ? i - 1 - SHOW_SAMPLES : 0; // RX start index
                        i_end = i_start + 2*SHOW_SAMPLES+1; // RX end index (exclusive)
                        if(i_end > bytes) { // RX end reached
                            i_end = bytes;
                            i_start = (i_end >= 2*SHOW_SAMPLES+1) ? i_end - 2*SHOW_SAMPLES+1 : 0; // adapt RX start
                        }
                        s_start = i - i_start - 1; 
                        s_start = (s_ok >= s_start) ? s_ok - s_start : samples + s_ok - s_start; // TX start
                        if (data + i*(DIO_BYTES_PER_SAMPLE/4) != d) { printf(NAME "error! %p != %p\n", data + i*(DIO_BYTES_PER_SAMPLE/4), d); return -2; }
                        printf(NAME "verify_data: TX %u RX %u samples %u\n", s_start, i_start, i_end - i_start);sleep_ms(200);
                        show_data2(info, data+i_start*(DIO_BYTES_PER_SAMPLE/4), i_end-i_start, s_start, i_start);
                        return -1;
                    }
                }
            } while ((mem->samples == 0) || (mem->data == NULL)); // skip zero samples data
            j = mem->samples;
            p = mem->data;
        }
        if(*p == *d) { // matching time
#if DIO_BYTES_PER_SAMPLE == 8
            if(*(p+1) != *(d+1)) return -2; // error data
#elif DIO_BYTES_PER_SAMPLE == 12
            if(*(p+2) != *(d+2)) return -2; // error data 1
            //if(*(p+3) != *(d+3)) return -3; // error data 2
#endif
            ++i; d += (DIO_BYTES_PER_SAMPLE/4); s_ok = s_cnt; restart = true; // data found
        }
    }
//printf(NAME "verify_data: %d/%u bytes\n", i, bytes);sleep_ms(200);
    return i;
}

// parameters of write_read_test
typedef struct test_params {
    uint32_t config;                // configuration sent to DIO24_IOCTL_GET_CONFIG before the test
    uint32_t reps;                  // repetitions, 1=default, 0=infinite
    uint32_t timeout;               // timeout in ms, 0=no timeout=default
    uint32_t RX_s_buf;              // RX buffer size in samples
    uint32_t strb_delay;            // strobe delay
    uint32_t sync_wait;             // wait time
    bool verify;                    // 1=read and verify RX samples, 0=do not read & verify RX samples
    bool all;
} TP;

// test mmap
int test_mmap(void) {
    int err = -1, i;
    int dma24_dev;
    struct dma24_interface * p_intf;
    struct data_info *data;
    uint32_t *p, *q;
    // open device
    dma24_dev = dma24_open(0);
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
        dma24_close(dma24_dev);
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
int write_read_test(int dma24_dev, struct data_info *data, TP *params) {
    int err = -1;
    int dio24_dev;
    uint32_t *buffer, samples = 0, load, s_max = 1, s_act = 0, s_more = 0, t_cnt, d_cnt, t_old, t_act, s_drop = 0, exp_samples = 0;
    struct data_info *first, *next;
    struct FPGA_status_run st_run;
    struct st_par stp;
    bool do_verify = params->verify;
    bool do_read = params->verify;

    // open dio24_dev device
    dio24_dev = dio24_open(0);
    if (dio24_dev <= 0) printf(NAME "error %d opening dio24 device!\n", dio24_dev); 
    else {
        memset(&status, 0, sizeof(struct FPGA_status));
        sleep_ms(500);
        if( data == NULL ) printf(NAME "data NULL or samples 0!?\n");
        else {
            buffer = (uint32_t *)malloc(TEST_BYTES);
            if( buffer == NULL ) printf(NAME "allocation of %d bytes failed!\n", TEST_BYTES);
            else {
                // reset dma24_dev which also cleans buffers
                err = dma24_reset(dma24_dev);
                if(err < 0) printf(NAME "reset error %d (0x%X)\n", err, err);
                else {
                    printf(NAME "reset ok.\n");
    //sleep_ms(100);
    //show_data(data, 5000, 20);
    //sleep_ms(100);
                    // set timeout (use samples temporarily)
                    samples = params->timeout;
                    err = dma24_set_timeout(dma24_dev, &samples);
                    if(err) printf(NAME "set timeout error %d (0x%X)\n", err, err);
                    else {
                        printf(NAME "set timeout new/old %d/%d ok\n", params->timeout, samples);
                        // set config (use samples temporarily)
                        samples = params->config;
                        err = dio24_set_config(dma24_dev, &samples);
                        if(err < 0) printf(NAME "set_config failed with error %d!\n", err);
                        else {
                            printf(NAME "set_config 0x%x ok\n", samples);
                            if (true) { // set clock divider for timing module
                                samples = (BUS_CLOCK_FREQ_HZ/TEST_OUT_FREQ_HZ);
                                err = dio24_set_div(dma24_dev, &samples);
                                if(err < 0) printf(NAME "set_div failed with error %d!\n", err);
                                else printf(NAME "set_div 0x%x ok\n", samples);
                            }
                            if (err >=0 ) {
                                // set strobe delay
                                samples = params->strb_delay;
                                err = dio24_set_strb_delay(dma24_dev, &samples);
                                if(err < 0) printf(NAME "set_strb_delay %u failed with error %d!\n", err, params->strb_delay);
                                else {
                                    printf(NAME "set_strb_delay 0x%x ok\n", samples);
                                    // set RX buffer size
                                    if (params->RX_s_buf > 0) {
                                        samples = params->RX_s_buf*DIO_BYTES_PER_SAMPLE;
                                        err = dma24_set_RX_buffer(dma24_dev, &samples);
                                        if(err < 0) printf(NAME "set RX buffer %d samples error %d\n", params->RX_s_buf, err);
                                        else printf(NAME "set RX buffer %u samples ok (old %u)\n", params->RX_s_buf, samples);
                                    }

                                    // set sync delay when AUTO_SYNC enabled and primary board, otherwise set it to 0
                                    if (err == 0) {
                                        samples = (params->config & (DIO_CTRL_AUTO_SYNC_EN|DIO_CTRL_AUTO_SYNC_PRIM) == (DIO_CTRL_AUTO_SYNC_EN|DIO_CTRL_AUTO_SYNC_PRIM)) ? params->sync_wait : 0;
                                        err = dio24_set_sync_delay(dma24_dev, samples);
                                        if(err < 0) printf(NAME "set_sync_delay %d error %d\n", samples, err);
                                        else if(err != samples) printf(NAME "set_sync_delay %d error actual delay %d\n", samples, err);
                                        else { printf(NAME "set_sync_delay %d ok\n", err); err = 0; }
                                    }

                                    if (err >= 0) {
                                        // prepare RX + TX buffers
                                        samples = 0;
                                        err = 0;
                                        next = data;
                                        while (next != NULL) {
                                            if((next->data != NULL) && (next->samples != 0)) {
                                                err = write(dma24_dev, next->data, next->samples*DIO_BYTES_PER_SAMPLE);
                                                if (err < 0) break;
                                                else if (err != (next->samples*DIO_BYTES_PER_SAMPLE)) {
                                                    err/=DIO_BYTES_PER_SAMPLE;
                                                    printf(NAME "warning: written %d/%d samples (ignore)\n", err, next->samples);sleep_ms(100);
                                                    //err = -1;
                                                    //break;
                                                    samples += err;
                                                }
                                                else samples += next->samples;
                                            }
                                            next = next->next;
                                        }
                                        if(err < 0) printf(NAME "prepare TX+RX %d samples error %d\n", samples, err);
                                        else {
                                            printf(NAME "prepare TX+RX %d samples ok\n", samples);sleep_ms(200);

                                            // start transmission
                                            stp.repetitions = params->reps;
                                            stp.flags = START_FPGA_DELAYED;
                                            err = dma24_start(dma24_dev, &stp);
                                            if(err < 0) printf(NAME "start error %d\n", err);
                                            else {
                                                sleep_ms(100);
                                                printf(NAME "start ok (%d)\n", err);
                                                // round samples to next multiple of 4
                                                exp_samples = samples + ((samples % 4) ? 4 - (samples % 4) : 0);
                                                // read and verify data until returns 0 (or error)
                                                err = 0;
                                                first = next = data;
                                                s_max = (params->reps * samples) ? params->reps * exp_samples : TEST_REPS_MAX * exp_samples;
                                                s_act = s_drop = t_cnt = d_cnt = 0;
                                                t_old = get_ticks();
                                                for(; (s_act < s_max) && (!err) && (t_cnt < TEST_T_LOOPS); ) {
                                                    load = dma24_get_load(dma24_dev);
                                                    if (do_read) err = read(dma24_dev, buffer, TEST_BYTES);
                                                    else {
                                                        ++t_cnt;
                                                        sleep_ms(1000);
                                                        // continue if FPGA run bit is set
                                                        if ( TEST_POLL ) { // directly read FPGA registers without waiting for FPGA IRQ (polling)
                                                            status.status_FPGA.status = dio24_get_status_FPGA(dma24_dev);
                                                            printf(NAME "FPGA status 0x%8x %8u us (%s)\n", status.status_FPGA.status, status.last_sample.data32[0], FPGA_status_str(status.status_FPGA.status)); 
                                                            if (status.status_FPGA.status & DIO_STATUS_RUN) continue; 
                                                            else break;
                                                            err = 0;
                                                        }
                                                        else {  // read from dio24 device = wait for FPGA IRQ
                                                            err = read(dio24_dev, &st_run, sizeof(struct FPGA_status_run));
                                                            if (err == 0) printf(NAME "FPGA read status timeout!\n");
                                                            if (err < 0) printf(NAME "FPGA read error %d (%d)!\n", errno, err);
                                                            else if (err != sizeof(struct FPGA_status_run)) printf(NAME "FPGA read %d/%d bytes?\n", err, sizeof(struct FPGA_status_run));
                                                            else {
                                                                err = 0;
                                                                printf(NAME "FPGA status 0x%8x %8u us (%s)\n", st_run.status, st_run.board_time, FPGA_status_str(st_run.status)); 
                                                                if (st_run.status & DIO_STATUS_RUN) continue;
                                                                else break;
                                                            }
                                                        }
                                                    }
                                                    if(err < 0) {
                                                        err = errno;
                                                        printf(NAME "read error %d\n", err); // error -16
                                                    }
                                                    else if (err > 0) {
                                                        t_act = get_ticks();
                                                        if((t_act - t_old) > 1000000) {
                                                            if (dio24_get_status_run(dma24_dev, &st_run) != 0) { // error
                                                                st_run.status = st_run.board_time = 0xffffffff;
                                                            }
                                                            printf(NAME "read %d smpl %8u us (%x, %d, %d/%d\%)\n", 
                                                                s_more + (err / DIO_BYTES_PER_SAMPLE), 
                                                                st_run.board_time, st_run.status,
                                                                err / DIO_BYTES_PER_SAMPLE, 
                                                                load & 0xff, (load>>16) & 0xff);
                                                            t_old = t_act;
                                                            s_more = 0;
                                                        }
                                                        else s_more += err / DIO_BYTES_PER_SAMPLE;
                                                        // verify data: next, d_cnt and s_act are updated
                                                        //if (do_verify) err = verify_data(first, next, d_cnt, s_act, s_drop, buffer, err, samples);
                                                        if (do_verify) {
                                                            uint32_t s_buf = err/DIO_BYTES_PER_SAMPLE;
                                                            err = verify_data2(first, buffer, err, samples);
                                                            if(err == 0) err = -1;
                                                            else if(err > 0) {
                                                                s_act += err;
                                                                s_drop += (err - s_buf);
                                                                err = 0;
                                                            }
                                                        }
                                                        else err = 0;
                                                        if (err > 0) { printf(NAME "warning %d\n", err); err = 0; }
                                                        else if (err < 0) { 
                                                            printf("\n" NAME "***   write_read_test error %d!   *** \n\n", err); 
                                                            err = 0; 
                                                            do_verify = false;
                                                            do_read = params->verify ? TEST_ONERR_READ : false; 
                                                        }
                                                        t_cnt = 0;
                                                    }
                                                    else { // read returned 0 = timeout 
                                                        ++t_cnt;
                                                        printf(NAME "%u/%u samples timeout %d/%d\n", s_act, s_max, t_cnt, TEST_T_LOOPS);
                                                    }
                                                    //sleep_ms(10);
                                                    //get_status(dma24_dev,false);
                                                }
                                                sleep_ms(100);
                                                get_status(dma24_dev, params->all);

                                                //printf(NAME "wait 5s ...\n");
                                                //sleep(5);

                                                if(dma24_stop(dma24_dev, 0L) <0 ) printf(NAME "stop error!\n");
                                                else {
                                                    sleep_ms(100);
                                                    printf(NAME "stop ok\n");
                                                }
                                                sleep_ms(100);
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                free(buffer);
            }
        }

        // print result for different conditions
        if (do_verify) { 
            // read & verify and no verification error
            if( ((s_act-s_drop+(status.RD_bt_drop/DIO_BYTES_PER_SAMPLE)) == s_max) && 
                    (status.TX_bt_tot == status.RX_bt_tot) && 
                    (status.TX_bt_tot == s_max*DIO_BYTES_PER_SAMPLE) && 
                    ((err == EWOULDBLOCK) || (err == 0)) 
                  ) {
                // all verified samples ok, maybe dropped samples but samples TX == RX == verified + dropped
                printf("\n" NAME "***   %u/%u samples ok! %u dropped (%d)  ***\n\n", s_act-s_drop, s_max, status.RD_bt_drop/DIO_BYTES_PER_SAMPLE, err);
                // ignore possible reading error EWOULDBLOCK (11) which can happen at end when samples were dropped
                err = 0;
            }
            else {
                if(!err) err = -4; // wrong numbers of samples
                printf("\n" NAME "***   %u/%u samples, %u dropped, error %d!   *** \n\n", s_act-s_drop, s_max, status.RD_bt_drop/DIO_BYTES_PER_SAMPLE, err);
            }
        } 
        else if (params->verify) { // verification error
            if (!err) err = -4;
            printf("\n" NAME "***   %u/%u samples, %u dropped, verify error %d!   *** \n\n", s_act-s_drop, s_max, status.RD_bt_drop/DIO_BYTES_PER_SAMPLE, err);
        }
        else { // no verification
            if( (status.TX_bt_tot == status.RX_bt_tot) && 
                    (status.TX_bt_tot == exp_samples*DIO_BYTES_PER_SAMPLE) && 
                    ((status.RD_bt_drop + status.RD_bt_act)/DIO_BYTES_PER_SAMPLE == exp_samples) && 
                    (err == 0) 
                  ) {
                printf("\n" NAME "***   %u (%u/%u) samples ok! %u dropped (%d)  ***\n\n", s_max, samples, exp_samples, status.RD_bt_drop/DIO_BYTES_PER_SAMPLE, err);
            }
            else {
                if(!err) err = -5; // wrong number of samples
                printf("\n" NAME "***   %u/%u/%u samples, %u dropped, error %d!   *** \n\n", status.TX_bt_tot/DIO_BYTES_PER_SAMPLE, status.RX_bt_tot/DIO_BYTES_PER_SAMPLE, s_max, status.RD_bt_drop/DIO_BYTES_PER_SAMPLE, err);
            }
        }
        sleep_ms(100);

        // close dio24 device
        dio24_close(dio24_dev);
    }
//show_data(data, 0, samples);
//sleep_ms(100);

    return err;
}

#define BUF_SIZE    256
#define NO_READ     0
#define DO_READ     1
#define READ_CHAR   '?'   

// send cmd and read if requested
// returns 0 if ok, otherwise error
// cmd is automatically terminated with '\n'
// possible commands: "*IDN?", "VOLTage:OFFSet 1.0"
// if read == NO_READ (0) does not read
// if read == DO_READ (1) always reads
// if read == any other character reads if agrees with last character of command. typically '?'  
int usb_test(char *cmd, char read_char) {
    int err = 0, dev, num;
    unsigned char buffer[BUF_SIZE];
    
    dev = open("/dev/usbtmc0", O_RDWR);
    if(dev <= 0) printf("open device failed with error %d\n", errno); 
    else {
        for(num=0; cmd[num]!='\0'; ++num);
        cmd[num]='\n';
        err = write(dev, cmd, num+1);
        cmd[num]='\0';
        if(err != num) printf("write %d bytes error %d/%d:\n%s\n", num, err, errno, cmd);
        else {
            printf("write %d bytes ok:\n%s\n", num, cmd);
            if ((read_char == DO_READ) || ((read_char != NO_READ) && (read_char == cmd[num-1]))) {
                err = read(dev, &buffer, BUF_SIZE);
                if (err <= 0) printf("read error %d/%d\n", err, errno);
                else {
                    buffer[err] = '\0';
                    printf("read %d bytes ok:\n%s", err, buffer);
                    sleep_ms(20);
                    err = 0;
                }
            }
            else err = 0;
        }
        close(dev);
    }

    if (err) printf("USB test error %d\n", err);
    else printf("USB test ok\n");

    return err;
}

// DMA memory write test
int test_DMA_write(int samples) {
    int err = 0;
    // open device
    printf(NAME "open device ...\n"); sleep_ms(20);
    int dev = dma24_open(0);
    if(dev <= 0) { err = -1; printf(NAME "open device error\n"); sleep_ms(20); }
    else {
        printf(NAME "open device ok\n"); sleep_ms(20);
        // reset device
        printf(NAME "reset device ...\n"); sleep_ms(20);
        err = dma24_reset(dev);
        if (err) { printf(NAME "reset error %d\n", err); sleep_ms(20); }
        else {
            printf(NAME "reset device ok\n"); sleep_ms(20);
            // configure device
            printf(NAME "configure device ...\n"); sleep_ms(20);
            uint32_t config = TEST_CONFIG;
            err = dio24_set_config(dev, &config);
            if(err < 0) { printf(NAME "configure device error %d\n", err); sleep_ms(20); }
            else {
                printf(NAME "configure device %x, old = %x ok\n", TEST_CONFIG, config);
                // generate samples in memory
                printf(NAME "generate %u samples ...\n", samples); sleep_ms(20);
                uint32_t *data = test_step(samples, 0, 1, 0x030201, 0x010101);
                if (data == NULL) { printf(NAME "generate %u samples error!\n", samples); sleep_ms(20); }
                else {
                    printf(NAME "generate %u samples ok\n", samples); sleep_ms(20);
                    // empty CPU cache
                    int i,j;
                    int size = 1; // size in MB. set much larger than L1+L2 cache (L1=32kB instr. 32kB data per CPU, L2=512kB).
                    char *tmp = (char*) malloc(size*0x100000);
                    printf(NAME "empty cache (write %dMB) ...\n", size); sleep_ms(20);
                    for (i=0; i<0x100000; ++i) {
                        for (j=0; j<size; ++j) {
                            tmp[j] = i*j;
                        }
                    } 
                    printf(NAME "empty cache (write %dMB) ok\n", size); sleep_ms(20);
                    // write to memory
                    printf(NAME "write %u samples ...\n", samples); sleep_ms(20);
                    err = write(dev, data, samples*DIO_BYTES_PER_SAMPLE);
                    if (err < 0) { 
                        if (errno == ENOMEM) printf(NAME "write %u samples error %d (ENOMEM)\n", samples, errno);
                        else printf(NAME "write %u samples error %d/%d\n", samples, err, errno); 
                        sleep_ms(20); 
                    }
                    else if (err != (samples*DIO_BYTES_PER_SAMPLE)) { printf(NAME "write %u bytes but %d written!\n", samples*DIO_BYTES_PER_SAMPLE, err); sleep_ms(20); }
                    else {
                        printf(NAME "write %u samples ok [test succeeded!]\n", samples); sleep_ms(20);
                    }
                    // free data
                    free(tmp);
                    free(data);
                }
            }
        }
        printf(NAME "close device ...\n"); sleep_ms(20);
        dma24_close(dev);
        printf(NAME "close device ok\n"); sleep_ms(20);
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

// main program
int main(int argc, char *argv[])
{
    static char strb_default[] = STRB_DELAY_STR;
    char *strb_str[MAX_NUM_RACKS] = {strb_default,strb_default};
    int err = 0, opt, dma24_dev, o;
    int send_data = 0, num_cpu = 2;
    char *cmd;
    TP params = {
        .config = TEST_CONFIG, // | DIO_CTRL_AUTO_SYNC_EN | DIO_CTRL_AUTO_SYNC_PRIM, // added for testing
        .reps = TEST_REPS,
        .timeout = TEST_TIMEOUT,
        .RX_s_buf = 0,
        .strb_delay = 0,
        .sync_wait = 0,
        .verify = false,
        .all = false
    };
    struct st_par stp;
    bool variate = false;   // if true vary number of samples
#ifdef _DEBUG
    printf("\n*** %s ... (with _DEBUG flag) ***\n\n, argv[0]");
#else
    printf("\n*** %s ... ***\n\n", argv[0]);
#endif

    while ((opt = getopt(argc, argv, ":r:t:x:b:va:z:m:n:su:")) != -1) {
        o = opt;
        switch (opt) {
            case 'x': send_data = atol(optarg); break; // send test data #
            case 'r': params.reps = atol(optarg); params.config |= DIO_CTRL_IRQ_RESTART_EN|DIO_CTRL_RESTART_EN; printf(NAME "repetitions = %d\n",params.reps); break; // set repetitions
            case 't': params.timeout = atol(optarg); printf(NAME "timeout = %d\n",params.timeout); break; // set timeout
            case 'b': params.RX_s_buf = atol(optarg); printf(NAME "RX buf samples = %d\n",params.RX_s_buf); break; // set RX buffer size
            case 'u': printf(NAME "USB test\n"); cmd = optarg; break; // USB test
            case 'v': params.verify = true; printf(NAME "read & verify\n"); break; // read and verify
            case 'a': params.all = true; printf(NAME "show all\n"); break; // show all debug info
            case 'z': send_data = atol(optarg); printf(NAME "DMA timing test (requires timing_test module!)\n"); break; // note: must be last option
            case 'm': send_data = atol(optarg); printf(NAME "DMA timing test write to memory (requires timing_test module!)\n"); break; // note: must be last option
            case 'n': num_cpu = atol(optarg); printf(NAME "DMA timing test number of cpu = %i\n", num_cpu); break; 
            case 's': printf(NAME "DMA timing test: vary samples\n"); variate = true; break; 
            case '?': printf(NAME "unknown option\n"); err=-1; break;
            case ':': printf(NAME "give a value!\n"); err=-2; break;
            default:
                printf("%s invalid option '%c'!\n", argv[0], opt);
                err=-3;
        }
        if(err) break;
    }

    if (!err) { 
        // calculate default strobe delay
        params.strb_delay = get_strb_delay(strb_str, BUS_OUT_FREQ_HZ);
        if (params.strb_delay == 0) {
            printf(NAME "error strobe delay\n");
            err = -10;
        }
        else {
            printf(NAME "strobe delay 0x%08x\n", params.strb_delay);
        }
    }

    if(!err) {
        sleep_ms(100);
        if(o == 'x') { 
            // open dma24_dev
            dma24_dev = dma24_open(0);
            if(dma24_dev <= 0) { 
                err = -1; 
                printf(NAME "open error\n"); 
            }
            else
            {
                struct data_info *data = NULL, *next, *last = NULL;
                bool free_buffer;
                data = (struct data_info *) malloc(sizeof(struct data_info));
                if (data) {
                    data->data = NULL;
                    data->samples = 0;
                    data->next = NULL;
                    switch (send_data) {
                    case 1:
                        data->samples = TEST_DATA_NUM_SAMPLES;
                        data->data = EXPAND96(test_data,data->samples);
                        free_buffer = EXPAND96_FREE;
                        break;
                    case 2:
                        data->samples = TEST_DATA_NUM_SAMPLES_2;
                        data->data = EXPAND96(test_data_2,data->samples);
                        free_buffer = EXPAND96_FREE;
                        break;
                    case 3:
                        data->data = test_outputs(100000, 172000, &data->samples);
                        free_buffer = true;
                        break;
                    case 4:
                        data = test_4(data);
                        free_buffer = true;
                        break;
                    case 5:
                        data->samples = LENS_NUM;
                        data->data = EXPAND96((uint32_t*) LENS_data,data->samples);
                        free_buffer = EXPAND96_FREE;
                        break;
                    case 6:
                        data->samples = LICR_NUM;
                        data->data = EXPAND96((uint32_t*) LiCr_data,data->samples);
                        free_buffer = EXPAND96_FREE;
                        break;
                    case 7:
                        data->samples = 500; // tiny samples < buffer but fast is difficult with repetitions
                        data->data = test_step(data->samples, 0, 1, 0x030201, 0x010101);
                        free_buffer = true;
                        break;
                    case 8:
                        data->samples = 512*20 + 12; // small 10k samples
                        data->data = test_step(data->samples, 0, 1, 0x030201, 0x010101);
                        free_buffer = true;
                        break;
                    case 9:
                        data->samples = 512*200 + 12; // 100k samples
                        data->data = test_step(data->samples, 0, 1, 0x030201, 0x010101);
                        free_buffer = true;
                        break;
                    case 10:
                        data->samples = 512*2000 + 12; // big 1M samples! = 12MiB @ 12bytes/sample
                        data->data = test_step(data->samples, 0, 1, 0x030201, 0x010101);
                        free_buffer = true;
                        break;
                    case 11:
                        data->samples = 512*10000 + 12; // huge 5M samples! = 60MiB @ 12bytes/sample
                        data->data = test_step(data->samples, 0, 1, 0x030201, 0x010101);
                        free_buffer = true;
                        break;
                    default:
                        data->samples = TEST_DATA_NUM_SAMPLES;
                        data->data = EXPAND96(test_data,data->samples);
                        free_buffer = EXPAND96_FREE;
                        break;
                    }
                    err = check_data(data, 10);
                    if (!err) {
                        sleep_ms(100);
                        err = write_read_test(dma24_dev, data, &params);
                    }
                    while(data) {
                        next = data->next;
                        if (free_buffer) free(data->data);
                        free(data);
                        data = next;
                    }
                }
                if (err) wait_for_key('e');
                //get_status(dma24_dev, params.all);
                dma24_close(dma24_dev);
            }
        }
        else if (o == 'u') err = usb_test(cmd, READ_CHAR); // USB test
        else if (o == 'm') err = test_DMA_write(send_data); // write to DMA test 
        /*else if ((o == 'z') || (o == 'm')) {            // timing test (requires timing_test module!)
            dma24_dev = dma24_open(0);
            if(dma24_dev <= 0) err = -1;
            else {
                uint32_t config, *result, *p_result, *buffer;
                uint32_t old, count = 0;        
                unsigned *cpu_percent = NULL;        
                struct FPGA_status_run st;
                bool started = false;
                int dio24_dev = dio24_open(0);
                if (dio24_dev <= 0) err = -2;
                else {
                    struct data_info *data = (struct data_info *) malloc(sizeof(struct data_info));
                    if (!data) err = -10;
                    else {
                        unsigned smpl, r, pwr = 2, length, s_end;
                        if (variate) { // reduce number of samples down to 4
                            s_end = 4;
                            // use next lower power of 2 for number of samples
                            for (smpl = send_data, pwr = 0; smpl > 0; smpl = smpl>>1, ++pwr);
                            send_data = 1 << (pwr-1);
                            length = params.reps*(pwr-2)*FILE_COLS; // numer of uint32_t in result
                        }
                        else {
                            s_end = send_data;
                            r = 1;
                            length = params.reps*FILE_COLS;
                        }
                        result = p_result = (uint32_t*) malloc(sizeof(uint32_t)*length);
                        if (!result) err = -11;
                        else {
                            buffer = (uint32_t *)malloc(TEST_BYTES);
                            if( buffer == NULL ) err = -12;
                            else {
                                printf(NAME "DMA TX timing test (start %d samples, %d reps, %d vars)\n", send_data, params.reps, pwr-2);
                                sleep_ms(50);
                                for (smpl = send_data; (smpl >= s_end) && (err >= 0); smpl = smpl>>1) { // reduce number of samples down to 4
                                    for (r = 0; (r < params.reps) && (err >= 0); ++r) { // repeat measurements with same number of samples for statistics
                                        config = (o == 'm') ? PERF_TIME : PERF_RX; // PERF_ test
                                        data->samples = smpl; // # samples
                                        data->next = NULL;
                                        data->data = test_step(data->samples, 0, 1, 0x030201, 0x010101);
                                        if (data->data == NULL) { err = -12; break; }
                                        else {
                                            err = dma24_reset(dma24_dev);
                                            if(!err) {
                                                err = dio24_set_config(dma24_dev, &config);
                                                if (!err) {
                                                    if (true) { // true = write data to DMA memory and for option 'm' measure writing time [default]
                                                        if (o == 'm') { // start timer
                                                            start_cpu_stat(num_cpu);
                                                            dio24_start(dma24_dev, 1);
                                                        }
                                                        //sleep_ms(50);
                                                        //for(int k=0; k<10; ++k) {
                                                        //    if (dio24_get_status_run(dma24_dev, &st)) printf(NAME "time %u irqs %u status %x (error!)\n", st.board_time, st.board_samples, st.status);
                                                        //    else printf(NAME "time %u irqs %u status %x\n", st.board_time, st.board_samples, st.status);
                                                        //    sleep_ms(50);
                                                        //}
                                                        err = write(dma24_dev, data->data, data->samples*DIO_BYTES_PER_SAMPLE);
                                                        if (o == 'm') { // stop timer
                                                            dio24_stop(dma24_dev, 0);
                                                            cpu_percent = stop_cpu_stat(num_cpu);
                                                        }
                                                    }
                                                    else { // false = measure writing time directly in driver [normally not done]
                                                        err = data->samples*DIO_BYTES_PER_SAMPLE;
                                                        dio24_timing_test(dma24_dev, 0);
                                                    }
                                                    if (err > 0) {
                                                        if(err != (data->samples*DIO_BYTES_PER_SAMPLE)) err = -20;
                                                        else if (o == 'm') { // measure DMA memory writing time (no data transmission)
                                                            get_status(dma24_dev, false);
                                                            printf("\n" NAME "%10u us: # %8u, 0x %8x (test result)\n\n", status.status_FPGA.board_time, status.status_FPGA.board_samples, status.status_FPGA.status);
                                                            sleep_ms(50);

                                                            // save result
                                                            *p_result++ = data->samples;    // set samples
                                                            *p_result++ = status.status_FPGA.board_samples; // transmitted samples = 0
                                                            *p_result++ = status.status_FPGA.board_time;    // measured time
                                                            for(count = 6; count < FILE_COLS; ++count) *p_result++ = 0; // add zeros
                                                            for (int ct = 0; ct < 2; ++ct) {                // 2x CPU load in % * 1000
                                                                if ((cpu_percent) && (ct < num_cpu)) {
                                                                    printf("CPU %i: %3u.%03u%%\n", ct, cpu_percent[ct] / 1000, cpu_percent[ct] % 1000);
                                                                    *p_result++ = cpu_percent[ct];
                                                                }
                                                                else *p_result++ = 0;
                                                            }
                                                            if (cpu_percent) {
                                                                sleep_ms(50);
                                                                delete[] cpu_percent; cpu_percent = NULL;
                                                            }
                                                            *p_result++ = (uint32_t)err;    // error if != 0
                                                        }
                                                        else { // timing test other than memory writing
                                                            stp.repetitions = 1;
                                                            stp.flags = START_FPGA_NOW; // START_FPGA_DELAYED/START_FPGA_NOW
                                                            start_cpu_stat(num_cpu);
                                                            err = dma24_start(dma24_dev, &stp);
                                                            if ((!err) || (config & PERF_START_IRQ_UP)) { // ignore start error when PERF_START_IRQ_UP is selected
                                                                count = 0;
                                                                while (true) { // TX & RX: wait until board_samples == data->samples
                                                                    memset(&st, 0, sizeof(struct FPGA_status_run));
                                                                    err = dio24_get_status_run(dma24_dev, &st);
                                                                    if (err) {
                                                                        printf(NAME "%10u us: # %8u, 0x %8x (err 0x%x)\n", st.board_time, st.board_samples, st.status, err);
                                                                        break;
                                                                    }
                                                                    if((st.status & DIO_STATUS_ERROR)) { 
                                                                        printf(NAME "%10u us: # %8u, 0x %8x (error)\n", st.board_time, st.board_samples, st.status); 
                                                                        err = -100;
                                                                        break; 
                                                                    }
                                                                    if((st.status & DIO_STATUS_END)) { 
                                                                        printf(NAME "%10u us: # %8u, 0x %8x (end)\n", st.board_time, st.board_samples, st.status); 
                                                                        break; 
                                                                    }
                                                                    if(st.board_samples >= data->samples) { 
                                                                        printf(NAME "%10u us: # %8u, 0x %8x (# ok)\n", st.board_time, st.board_samples, st.status); 
                                                                        break; 
                                                                    }
                                                                    if(st.status & DIO_STATUS_RUN) {
                                                                        started = true;
                                                                        printf(NAME "%10u us: # %8u, 0x %8x (run)\n", st.board_time, st.board_samples, st.status);
                                                                    }
                                                                    else if (started && ((config & PERF_START_IRQ_UP) == 0)) { // for PERF_IRQ_... this can happen
                                                                        printf(NAME "%10u us: # %8u, 0x %8x (stop?)\n", st.board_time, st.board_samples, st.status);
                                                                        err = -101;
                                                                        break;
                                                                    }
                                                                    else {
                                                                        printf(NAME "%10u us: # %8u, 0x %8x (starting...)\n", st.board_time, st.board_samples, st.status);
                                                                    }
                                                                    if (old == st.board_samples) {
                                                                        if(++count >= 10) {
                                                                            if (config & DIO_TEST_TX) { err = -102; printf(NAME "no change for %u loops - stop with error %d!\n", count, err); }
                                                                            else printf(NAME "no change for %u loops - stop (TX disabled: ok)!\n", count);
                                                                            break;
                                                                        }
                                                                    }
                                                                    else count = 0;
                                                                    old = st.board_samples;
                                                                    sleep_ms(200);
                                                                }
                                                                if((err>=0) && (config & DIO_TEST_RX)) { // RX: wait until data->samples received
                                                                    for(count = 0; count < (data->samples*DIO_BYTES_PER_SAMPLE); count += err) {
                                                                        err = read(dma24_dev, buffer, TEST_BYTES);
                                                                        if(err > 0) {
                                                                            printf(NAME "%8u: %8d bytes read\n", count, err);
                                                                        }
                                                                        else {
                                                                            printf(NAME "%8u: read error %d (%d)\n", count, errno, err);
                                                                            break;
                                                                        }
                                                                    }
                                                                    if (err > 0) { 
                                                                        printf(NAME "%8u bytes total (ok)\n", count, err); 
                                                                        err = 0; 
                                                                    }
                                                                    else printf(NAME "%8u bytes total, err = %d\n", count, err);
                                                                }
                                                                sleep_ms(50);
                                                                dma24_stop(dma24_dev, 0L);
                                                                cpu_percent = stop_cpu_stat(num_cpu);
                                                                sleep_ms(50);
                                                                if(false) {
                                                                    memset(&st, 0, sizeof(struct FPGA_status_run));
                                                                    dio24_get_status_run(dma24_dev, &st);
                                                                    printf("\n" NAME "%10u us: # %8u, 0x %8x (test result)\n", st.board_time, st.board_samples, st.status);
                                                                    sleep_ms(50);
                                                                }
                                                                else {
                                                                    get_status(dma24_dev, false);
                                                                    printf("\n" NAME "%10u us: # %8u, 0x %8x (test result)\n", status.status_FPGA.board_time, status.status_FPGA.board_samples, status.status_FPGA.status);
                                                                    sleep_ms(50);
                                                                }
                                                                // save result
                                                                *p_result++ = data->samples;    // set samples
                                                                *p_result++ = st.board_samples; // transmitted samples
                                                                *p_result++ = st.board_time;    // measured time
                                                                *p_result++ = status.RX_bt_tot/DIO_BYTES_PER_SAMPLE;    // RX: transmitted samples
                                                                *p_result++ = status.last_sample.data32[0];             // RX: last sample time
                                                                *p_result++ = status.last_sample.data32[1];             // RX: last sample data
                                                                *p_result++ = status.irq_TX;    // TX IRQ counter 
                                                                *p_result++ = status.irq_RX;    // RX IRQ counter
                                                                *p_result++ = status.irq_FPGA;  // FPGA IRQ counter
                                                                for (int ct = 0; ct < 2; ++ct) { // 2x CPU load in % * 1000
                                                                    if ((cpu_percent) && (ct < num_cpu)) {
                                                                        printf("CPU %i: %3u.%03u%%\n", ct, cpu_percent[ct] / 1000, cpu_percent[ct] % 1000);
                                                                        *p_result++ = cpu_percent[ct];
                                                                    }
                                                                    else *p_result++ = 0;
                                                                }
                                                                if (cpu_percent) {
                                                                    printf("\n");
                                                                    sleep_ms(50);
                                                                    delete[] cpu_percent; cpu_percent = NULL;
                                                                }
                                                                *p_result++ = (uint32_t)err;    // error if != 0
                                                                //get_status(dma24_dev, false);
                                                                //if(!err) printf("\n" NAME "%10uus: samples %8u, status %8x (ok)\n", st.board_time, st.board_samples, st.status);
                                                                //else printf("\n" NAME "%10uus: samples %8u, status %8x (error)\n", st.board_time, st.board_samples, st.status);

                                                                // ignore errors:
                                                                err = 0;
                                                            }    
                                                        }
                                                    }
                                                }                                        
                                            }
                                            free(data->data);
                                        }
                                    }
                                }
                                free(buffer);
                            }
                            printf(NAME "append %u lines to %s\n", length/FILE_COLS, FILE_NAME);
                            err = save_CSV(FILE_NAME, result, length, FILE_COLS);
                            free(result);
                        }
                        free(data);
                    }
                    dio24_close(dio24_dev);
                }
                dma24_close(dma24_dev);
            }
            if(err) printf(NAME "test error = %d\n", err);
            else printf(NAME "test (ok)\n");
        }*/
        else {
            // read dma24_dev status & lock/unlock from external clock
            dma24_dev = dma24_open(0);
            if(dma24_dev <= 0) {
                err = -1;
                printf(NAME "open error\n");
            }
            else {
                err = get_status(dma24_dev, params.all);
                sleep_ms(20);
                dma24_close(dma24_dev);
                sleep_ms(20);
                if(err) printf(NAME "get_status error = %d\n", err);
                else printf(NAME "get_status (ok)\n");
            }
        }
    }

    return err;
}


