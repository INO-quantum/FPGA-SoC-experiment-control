////////////////////////////////////////////////////////////////////////////////////////////////////
// FPGA-test
// 32bit Linux console application to be run on Xilinx Zynq-7020 FPGA with Petalinux
// created 08/07/2018 by Andi
// compiled with g++ on Ubuntu 18.04 LTS
// tested with Petalinux 2017.4
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
#define TEST_BYTES          15000*DIO_BYTES_PER_SAMPLE      // buffer size in bytes for read()
#define TEST_REPS           1                               // number of repetitions
#define TEST_TIMEOUT        1000                            // timeout in ms
#define TEST_T_LOOPS        125                             // number of timeouts before stop()
#define TEST_REPS_MAX       125                             // number of repetitions before stop()
#define TEST_ONERR_READ     false                           // after verify error continue read(), otherwise waits until FPGA and DMA finished
#define TEST_POLL           false                           // poll with dio24_get_status_FPGA(dma24_dev) or wait for FPGA IRQ by read(dio24_dev)

// DIO_BYTES_PER_SAMPLE dependent settings
#if DIO_BYTES_PER_SAMPLE == 8
    #define TEST_CONFIG            DIO_CONFIG_RUN_64
    #define ADD_ZERO_PP(p)
    #define SHOW_DATA(p)            printf("0x %08lx %08lx = %8lu us\n", i, *p, *(p+1), *p);
    #define SHOW_DATA_I(i,p)        printf("%6u: 0x %08lx %08lx = %8lu us\n", i, *p, *(p+1), *p);
    #define SHOW_DATA_IC(i,p,comment)    printf("%6u: 0x %08lx %08lx = %8lu us (%s)\n", i, *p, *(p+1), *p, comment);
    #define EXPAND96(data,num)        data
    #define EXPAND96_FREE            false
#elif DIO_BYTES_PER_SAMPLE == 12
    #define TEST_CONFIG            DIO_CTRL_IRQ_ALL|DIO_CTRL_RESTART_EN|DIO_CTRL_BPS96
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
    if ((*p) & (1<<DIO_BIT_NUM)) {
        printf("%3i: num_samples = %u\n", i, (*p) & DIO_SAMPLES_MASK);
        t_old = TOLD_INVALID;
    }
    else if((((*p) & TIME_MASK) <= t_old) && (t_old != TOLD_INVALID)) { 
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

#define CHECK_BT_TOT(st)    ((st.TX_bt_tot == st.RX_bt_tot) && (st.RX_bt_tot == (st.bt_tot*st.reps_set)))

// display device status
static struct FPGA_status status;
int get_status(int dev, bool all) {
    int err, i;
    int32_t mT;
    memset(&status, 0, sizeof(struct FPGA_status));
    if (all) err = dio24_get_status_dbg(dev, &status);
    else err = dio24_get_status(dev, &status);
    sleep_ms(100); // this might avoid that driver messages are printed between status.
    if(err < 0) printf(NAME "get_status failed with error %d!\n", err);
    else {
        if(err > 0) printf(NAME "get_status warning %d\n", err);
        mT = GET_mT(status.FPGA_temp);
        printf(NAME "DMA & FPGA status:\n");
        printf(NAME "                  TX       RX     FPGA\n");
        printf(NAME "ctrl       0x %8x        - %8x\n",    status.ctrl_DMA,                        status.ctrl_FPGA);
        printf(NAME "del/ph/tst 0x %8x %8x %8x\n",    status.sync_delay, status.sync_phase, status.ctrl_test);
        printf(NAME "status     0x %8x %8x %8x (%s)\n", status.status_TX, status.status_RX, status.status_FPGA.status, FPGA_status_str(status.status_FPGA.status));
        printf(NAME "board #/t            - %8u %8d us\n",                  status.status_FPGA.board_samples, status.status_FPGA.board_time);
        printf(NAME "board #/t (ext)      - %8u %8d us\n",                  status.board_samples_ext, status.board_time_ext);
		printf(NAME "sync time 0x         -        - %8x\n",                status.sync_time);
        printf(NAME "temperature          -        - %4d.%03u deg.C\n",                        mT/1000, mT % 1000);
        printf(NAME "phase ext/det        - %8d %8d steps\n",               status.phase_ext, status.phase_det);
        printf(NAME "error         %8d %8d %8d\n",         status.err_TX,    status.err_RX,    status.err_FPGA);
        printf(NAME "IRQ's         %8u %8u %8u\n",         status.irq_TX,    status.irq_RX,    status.irq_FPGA);
        printf(NAME "IRQ's mrg     %8u\n",                 status.irq_num);
        printf(NAME "trans bytes   %8u %8u %8u (%s)\n",    status.TX_bt_tot, status.RX_bt_tot, status.bt_tot, CHECK_BT_TOT(status) ? "ok" : "error" );
        printf(NAME "TX p/a/c      %8u %8u %8u\n",         status.dsc_TX_p,  status.dsc_TX_a,  status.dsc_TX_c);
        printf(NAME "RX p/a/c      %8u %8u %8u\n",         status.dsc_RX_p,  status.dsc_RX_a,  status.dsc_RX_c);
        printf(NAME "rd m/a/d      %8u %8u %8u\n",         status.RD_bt_max, status.RD_bt_act, status.RD_bt_drop);
        printf(NAME "reps/act      %8u %8u\n",                status.reps_set,   status.reps_act);
        printf(NAME "timeout       %8u\n",                   status.timeout);
#if DIO_BYTES_PER_SAMPLE == 8
        printf(NAME "RX last    0x %08x %08x          (%u us)\n",    status.last_sample.data32[0], status.last_sample.data32[1], status.last_sample.data32[0]);
#elif DIO_BYTES_PER_SAMPLE == 12
        printf(NAME "RX last    0x %08x %08x %08x (%u us)\n",    status.last_sample.data32[0], status.last_sample.data32[1], status.last_sample.data32[2], status.last_sample.data32[0]);
#endif        
        printf(NAME "byte/sample   %8u        - %8u\n", DIO_BYTES_PER_SAMPLE, status.set_samples);
        printf(NAME "debug_cnt     %8u\n",           status.debug_count);
        for(i=0; i<FPGA_STATUS_NUM_DEBUG; ++i) {
            if ((i % DBG_HIST) == 0) printf(NAME "debug %2d   0x %8x", i, status.debug[i]);
            else if ((i % DBG_HIST) == (DBG_HIST-1)) printf(" %8x\n", status.debug[i]);
            else printf(" %8x", status.debug[i]);
        }
    }
    sleep_ms(100); // this might avoid that driver messages are printed between status.
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
    uint32_t reps;                    // repetitions, 1=default, 0=infinite
    uint32_t timeout;                // timeout in ms, 0=no timeout=default
    uint32_t RX_s_buf;                // RX buffer size in samples
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
    uint32_t *buffer, samples = 0, load, s_max = 1, s_act = 0, s_more = 0, t_cnt, d_cnt, t_old, t_act, s_drop = 0;
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
                            printf(NAME "set_config %x, old = %x ok\n", params->config, samples);

                            // set RX buffer size
                            if (params->RX_s_buf > 0) {
                                samples = params->RX_s_buf*DIO_BYTES_PER_SAMPLE;
                                err = dma24_set_RX_buffer(dma24_dev, &samples);
                                if(err < 0) printf(NAME "set RX buffer %d samples error %d\n", params->RX_s_buf, err);
                                else printf(NAME "set RX buffer %u samples ok (old %u)\n", params->RX_s_buf, samples);
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
                                        // read and verify data until returns 0 (or error)
                                        err = 0;
                                        first = next = data;
                                        s_max = (params->reps * samples) ? params->reps * samples : TEST_REPS_MAX * samples;
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
                free(buffer);
            }
        }

        // print result for different conditions
        if (do_verify) { // read & verify and no verification error
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
                    (status.TX_bt_tot == s_max*DIO_BYTES_PER_SAMPLE) && 
                    ((status.RD_bt_drop + status.RD_bt_act)/DIO_BYTES_PER_SAMPLE == s_max) && 
                    (err == 0) 
                  ) {
                printf("\n" NAME "***   %u samples ok! %u dropped (%d)  ***\n\n", s_max, status.RD_bt_drop/DIO_BYTES_PER_SAMPLE, err);
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

// connects to given IP_address and port
// returns socket if ok or INVALID_SOCKET on error
// note: if IP_address = NULL connects to INADDR_ANY = "localhost"
SOCKET _connect(const char *IP_address, const char *port) {
    SOCKET c = INVALID_SOCKET;
    struct addrinfo *result = NULL, *ptr = NULL;
    struct addrinfo ai;
    // init address information structure
    ZEROMEMORY(&ai, sizeof(ai));
    ai.ai_family = AF_INET;                        // use IPv4 or IPv6 adress family
    ai.ai_socktype = SOCK_STREAM;                // streaming socket
    ai.ai_protocol = IPPROTO_TCP;                // TCP protocol

    // Resolve the server address and port
    if (getaddrinfo(IP_address, port, &ai, &result) == 0)
    {
        // attempt to connect to the first address returned by the call to getaddrinfo
        ptr = result;

        // Create a SOCKET for connecting to server
        SOCKET c;
        if ((c = socket(ptr->ai_family, ptr->ai_socktype, ptr->ai_protocol)) != INVALID_SOCKET)
        {
            // connect to server
            if (::connect(c, ptr->ai_addr, (int)ptr->ai_addrlen) != SOCKET_ERROR) 
            {
                // free adress info structure returned by getaddrinfo
                freeaddrinfo(result);
                return c;
            }
            // error connecting to server
            CLOSESOCKET(c);
            c = INVALID_SOCKET;
        }
        // free adress info structure returned by getaddrinfo
        freeaddrinfo(result);
    }
    return c;
}


// send data and receive ACK/NACK or SERVER_AUTO_SYNC_START
// returns RECV_ACK/RECV_NACK if ACK/NACK received, otherwise error code
#define RECV_ACK    0
#define RECV_NACK   -SERVER_NACK
int send_recv(SOCKET sock, char *data, int bytes) {
    int err = 0;
    SERVER_CMD cmd;
    if ((data != NULL) && (bytes > 0)) {
        err = send(sock, data, bytes, 0);
        if (err != bytes) { 
            printf(NAME "send error %d\n", err); 
            err = -100;
        }
        else err = 0;
    }
    if(!err) {
        // recieve ACK (TODO: use timeout!)
        err = recv(sock, &cmd, sizeof(SERVER_CMD), 0);
        if ((cmd == SERVER_NACK) && (err == sizeof(SERVER_CMD))) { 
            printf(NAME "received NACK (%x)\n", cmd); 
            err = RECV_NACK;
        }
        else if ((cmd == SERVER_ACK) && (err == sizeof(SERVER_CMD))) {
            err = RECV_ACK;
        }
        else {
            printf(NAME "received cmd %x bytes %u instead of ACK (%x/%u)\n", cmd, err, (int)SERVER_ACK, sizeof(SERVER_CMD)); 
            err = -103; 
        }
    }
    return err;
}

// receive board status bits
// returns status bits if ok, otherwise -1
uint32_t recv_status(SOCKET sock) {
    uint32_t result = -1;
    int err;
    struct client_data32 cd;
    cd.cmd = SERVER_GET_FPGA_STATUS_BITS;
    cd.data = -1;
    err = send(sock, (char*)&cd.cmd, sizeof(SERVER_CMD), 0);
    if (err != sizeof(SERVER_CMD)) {
        printf(NAME "send error %d\n", err); 
    }
    else {
        // recieve data (TODO: use timeout!)
        err = recv(sock, (char*)&cd, sizeof(struct client_data32), 0);
        if(err != sizeof(struct client_data32)) { 
            printf(NAME "recv error %d\n", err); 
        }
        else if (cd.cmd == SERVER_NACK) { 
            printf(NAME "received NACK (%x) instead of SERVER_RSP_FPGA_STATUS_BITS (%x)\n", cd.cmd, SERVER_RSP_FPGA_STATUS_BITS); 
        }
        else if (cd.cmd != SERVER_RSP_FPGA_STATUS_BITS) { 
            printf(NAME "received %x instead of SERVER_RSP_FPGA_STATUS_BITS (%x)\n", cd.cmd, SERVER_RSP_FPGA_STATUS_BITS); 
        }
        else {
            result = cd.data;
        }
    }
    return result;
}

// start/stop auto-sync on secondary board with given delay and phase = {ext,det} in steps
// if FET=true then pulse is reflected, otherwise not
// returns last sync_time in delay
int auto_sync_secondary(SOCKET sock, uint32_t *delay, int phase, bool start, bool reset, bool reflect) {
    int err = 0;
    struct client_data64 cd64;

    if (reset) { // reset secondary device
        cd64.cmd = SERVER_RESET;
        err = send_recv(sock, (char*)&cd64.cmd, sizeof(SERVER_CMD));
    }
    if (!err) {
        //printf(NAME "auto-sync secondary START/STOP\n");
        cd64.data_0 = reflect ? ((*delay) & SYNC_DELAY_MASK) | SYNC_DELAY_WITH_FET : ((*delay) & SYNC_DELAY_MASK);
        cd64.data_1 = phase & SYNC_PHASE_MASK_2; 
        if (start) { // start auto-sync with given delay & phase
            cd64.cmd = SERVER_AUTO_SYNC_START;
            err = send_recv(sock, (char*)&cd64, sizeof(client_data64));
            if (err != RECV_ACK) { 
                printf(NAME "no ACK received from secondary board! (%d)\n", err); 
                err = -100;
            }
            else err = 0;
        }
        else { // stop auto-sync with given delay & phase and get sync_time
            cd64.cmd = SERVER_AUTO_SYNC_STOP;
            err = send(sock, (char*)&cd64, sizeof(client_data64), 0);
            if (err != sizeof(client_data64)) { 
                printf(NAME "send error %d\n", err); 
                err = -200;
            }
            else {
                // recieve SERVER_AUTO_SYNC_STOP with data_0 = sync_time
                err = recv(sock, (char*)&cd64, sizeof(struct client_data64), 0);
                if ((cd64.cmd == SERVER_AUTO_SYNC_STOP) && (err == sizeof(struct client_data64))) { 
                    //printf(NAME "received sync_time = 0x%08x\n", data.data); 
                    *delay = cd64.data_0;
                    err = 0;
                }
                else {
                    printf(NAME "received cmd %x / bytes %u instead of %x/%u\n", cd64.cmd, err, (int)SERVER_AUTO_SYNC_STOP, sizeof(struct client_data64)); 
                    err = -203; 
                }
            }
        }
    
        /*printf(NAME "auto-sync secondary (%s) trg in/out/phase %u/%u/%d\n", start ? "start" : "stop", 
            (unsigned)(data.data & TRG_MAX_IN_DELAY), 
            (unsigned)(data.data>>TRG_DELAY_IN_BITS) & TRG_MAX_OUT_DELAY, 
            (int)(data.data>>(TRG_DELAY_IN_BITS+TRG_DELAY_OUT_BITS)) );
        sleep_ms(10);*/
    }
    return err;
}

// configure FPGA for auto-sync with given sync delay and phase
// note: keep this function consistent with FPGA-server!
int as_config(int dev, uint32_t delay, uint32_t phase, bool reset) {
    int err = 0;
    uint32_t config = AUTO_SYNC_PRIM_CONF;
    // reset board
    if (reset) err = dma24_reset(dev);
    if (err) printf(NAME "error %d reset\n", err);
    else {
        /* set output trigger delay & phase
        printf(NAME "set trigger delay in/out/phase %u/%u/%u\n", 
            (unsigned)(delay & TRG_MAX_IN_DELAY), 
            (unsigned)(delay>>TRG_DELAY_IN_BITS) & TRG_MAX_OUT_DELAY, 
            (int)(delay>>(TRG_DELAY_IN_BITS+TRG_DELAY_OUT_BITS))  );
        */
        // set sync delay
        err = dio24_set_sync_delay(dev, delay);
        if(err != delay) { printf(NAME "error %d set sync delay %u\n", err, delay); err = -120; } 
        else {
            // set sync phase. this immediately starts phase shift. returns difference to old phase.
            dio24_set_sync_phase(dev, phase);
            // check if absolute phase is correct
            err = dio24_get_sync_phase(dev);
            if( ((err >> SYNC_PHASE_BITS)  != (((phase >> SYNC_PHASE_BITS) & SYNC_PHASE_MASK_1) % PHASE_360)) ||
                ((err & SYNC_PHASE_MASK_1) != ((phase & SYNC_PHASE_MASK_1) % PHASE_360))                         
            ) { printf(NAME "error %d set sync phase %d\n", err, phase); err = -121; } 
            else {
                err = 0;
                // wait until phase shift is done (waits one time, then should be fine)
                while(dio24_get_status_FPGA(dev) & DIO_STATUS_PS_ACTIVE) { if(++err >=10) break; sleep_ms(10); }
                if (err >= 10) { printf(NAME "waited %d loops for phase shift\n", err); err = -122; }
                else {
                    // configure FPGA 
                    // for primary board: sets DIO_CTRL_AUTO_SYNC_EN|DIO_CTRL_AUTO_SYNC_PRIM bits generating immediately the pulse
                    // for secondary board: sets DIO_CTRL_AUTO_SYNC_EN bits without generating pulse
                    err = dio24_set_config(dev, &config);
                    if (err) printf(NAME "error %d set config 0x%x\n", err, config);
                    else {
                        err = 0;
                    }
                }
            }
        }
    }
    return err;
}

#define AS_SEC          "192.168.1.12"      // if defined connect to secondary board at given IP

#define PHASE_360       1120                // 360 degree = (1/50MHz)/(1/(56*1000MHz)); 1GHz/56 = 17.857ps/step, 20ns/17.857ps = 1120 steps
#define PHASE_STEPS     10                  // number of phase steps in given range
#define PHASE_REPS      5                   // max. number of repetitions with same phase for statistics
#define ERROR_MAX       5                   // max. number of errors before stops
#define AS_COLS         5                   // entries per measurement in result file
#define FIND_T0         0                   // search jump in t0_PS
#define FIND_T1         1                   // search jump in t1_PS
#define FIND_POSITIVE   0                   // search for positive jump in time
#define FIND_NEGATIVE   2                   // search for negative jump in time
#define FIND_DELTA      4                   // search jump in t0_PS-t0 or t1_PS-1
#ifdef AS_SEC
#define FIND_REMOTE     8                   // search on remote/secondary board (sock != INVALID_SOCKED)
#endif
#define FIND_NONE       16                  // single pulse with given primary & secondary phase = *start and primary delay = *end
#define FIND_RUN        32                  // combine with FIND_NONE: single pulse with given primary delay = *end and secondary phase = *start
#define FIND_FINE       64                  // restart search on error, otherwise abort and return with error immediately
// recursively find jumps in sync_time until 2*phase error <= PHASE_GOAL
// start and end give the range of phase where search is intiated in units of PHASE_360
// returns 0 if found, otherwise error code
// use start and end to retrieve result phase = (end+start)/2 and error = (end-start)/2
// result time is saved in tL and tH
// if start == end measures one time without search and returns tH
// if data !=0 points to data_length uint32_t where phase and sync_time is saved, data is incremented and data_length decremented
// if sock != INVALID_SOCKET then performs measurement in parallel on remote board. if FIND_REMOTE uses remote sync_time to find jump, otherwise local.
// ph_ext = secondary external phase kept constant during measurement
// notes:
// - phases are all absolute, driver takes care of relative phase shifts to actual phase 
// - does NOT reset device to keep secondary board locked and changes phase incrementally. 
// - this is a copy of same function in FPGA-test and it would be good to keep them identical!
int find_jump(int dma24_dev, SOCKET sock, int ph_ext, int *start, int *end, uint8_t *tL, uint8_t *tH, uint32_t *&data, int *data_length, unsigned flags) {
    int err = 0, count, reps = 0, phase, ph, step, dcnt = 0, err_count = 0, rst_count = 0;
    uint32_t config, t_sync = 0, t_sync_2 = 0;
    uint8_t time;
    struct FPGA_status_run st;
    bool search_positive = true; // true = search new end (positive phase steps), false = search new start (negative phase steps)
    bool note = true;
    char fm  = (flags & FIND_NEGATIVE) ? '-' : '+';    
    char f1  = (flags & FIND_T1) ? '1' : '0'; 
    char fd  = (flags & FIND_DELTA) ? 'd' : '.'; 

    *tL = *tH = 0;
    ph_ext &= SYNC_PHASE_MASK_1;
    (*start) &= SYNC_PHASE_MASK_1;
    if (flags & FIND_NONE) {
        (*end) &= SYNC_DELAY_MASK;
        printf(NAME "find_jump prim. delay %u sec. phase ext/det %d/%d steps\n", *end, ph_ext, *start);
        phase = *start; // prim & sec phase
    }
    else {
        (*end) &= SYNC_PHASE_MASK_1;
        if (*end < *start) { step = *start; *start = *end; *end = step; } // end must be larger start
        *end = *start + ((*end - *start) % PHASE_360); // ensure end is within 360 degree above start
        phase = *start;
        step = (*end - *start)/PHASE_STEPS;
        if(step == 0) step = 1;
        printf(NAME "find_jump phase start %d stop %d ext %d\n", *start, *end, ph_ext);
    }
    while(true) {
        // reset, phase shift & configure primary device which starts immediately the auto-sync pulse
        //sleep_ms(20);printf(NAME "find jump: phase %d start/end/step %u/%u/%u, time/0/1 %u/%u/%u\n",phase,*start,*end,step,time,*tL,*tH);sleep_ms(20);
        ph = phase % PHASE_360;
        while (ph < 0) ph += PHASE_360;
#ifdef AS_SEC
        if (sock != INVALID_SOCKET) { // remote secondary board
            // reset, lock to primary clock and start auto-sync on secondary board with delay = 0 and phase
            t_sync_2 = 0;
            err = auto_sync_secondary(sock, 
                                        &t_sync_2,              // input: delay = 0, output: last sync_time if stop
                                        (ph_ext << SYNC_PHASE_BITS) | ((flags & FIND_NONE) ? (*start) : ph), // {ext,det} absolute phase in steps
                                        true,                   // start=true, stop=false
                                        true,                   // reset
                                        (flags & FIND_REMOTE) == 0 // remote board = FET off (no reflection), otherwise FET on (reflect)
                                    );
            if (err) { printf(NAME "start secondary error %d\n", err); break; }
        }
#endif
        // generate pulse on local board and measure time
        if (flags & FIND_NONE) err = as_config(dma24_dev, ((*end) & SYNC_DELAY_MASK), (flags & FIND_RUN) ? 0 : *start, false); // set delay and phase
        else err = as_config(dma24_dev, 0, ph, false); // set phase, delay = 0
        if (err) { printf(NAME "auto-sync configure error %d\n", err); break; }
        // wait until auto-sync is finished
        for(count = 0; count < 25; ++count) {
            memset(&st, 0, sizeof(struct FPGA_status_run));
            err = dio24_get_status_run(dma24_dev, &st);
            if (err) { printf(NAME "get status error %d\n", err); break; }
            //printf(NAME "time %d status 0x%x\n", st.board_time, st.status);
            if ((st.status & DIO_STATUS_AUTO_SYNC) == 0) break; 
            sleep_ms(20);
        }
        if ((st.status & DIO_STATUS_AUTO_SYNC) != 0) { // auto-sync does not end: should not happen since there is a timeout
            printf(NAME "timeout after %dms!\n", count*20);
            err = -201;
            break;
        } 
        if ((st.status & DIO_STATUS_AS_TIMEOUT) != 0) { // happens for short cables where there is a single pulse
            if (flags & FIND_REMOTE) { 
                if (note) { 
                    printf(NAME "note: REM auto-sync timeout on local board (1x note)\n"); sleep_ms(20); 
                    note=false;
                } 
            }
            else {
                printf(NAME "auto-sync timeout! status 0x%x (short cable?)\n", st.status);sleep_ms(20);
                err = -202;
                break;
            }
        } 
        // reset auto-sync bit
        config = AUTO_SYNC_PRIM_CONF & (~DIO_CTRL_AUTO_SYNC_EN);
        err = dio24_set_config(dma24_dev, &config);
        if (err) { printf(NAME "auto-sync error stop %d!\n", err); break; }
        // get sync_time t0 or t1 from local board
        t_sync = dio24_get_sync_time(dma24_dev);

#ifdef AS_SEC
        if (sock != INVALID_SOCKET) { // remote secondary board
            // obtain resulting sync_time (set same phase and delay = 0)
            t_sync_2 = 0;
            err = auto_sync_secondary(sock, 
                                        &t_sync_2,              // input: delay = 0, output: last sync_time if stop
                                        (flags & FIND_NONE) ? (*start) : ph, // absolute phase in steps
                                        false,                  // start=true, stop=false
                                        false,                  // reset
                                        (flags & FIND_REMOTE) == 0 // remote board = FET off (no reflection), otherwise FET on (reflect)
                                    );
            if (err) { printf(NAME "stop secondary error %d\n", err); break; }
        }
#endif

        // save local sync_time if data not NULL or full
        if(data && (*data_length >= AS_COLS)) {
            *data++ = phase;
            *data++ = t_sync & 0xff;
            *data++ = (t_sync >> 8) & 0xff;
            *data++ = (t_sync >> 16) & 0xff;
            *data++ = (t_sync >> 24) & 0xff;
            *data_length = *data_length - AS_COLS;
        }

        // take local/remote sync_time
        if (flags & FIND_REMOTE) t_sync = t_sync_2;
        // take local/remote time difference or PS times
        if (flags & FIND_DELTA) time = (flags & FIND_T1) ? (10 + (t_sync >> 24) - ((t_sync >> 8) & 0xff)) : (10 + ((t_sync >> 16) & 0xff) - (t_sync & 0xff));
        else                    time = (flags & FIND_T1) ?  (t_sync >> 24)                           : ( (t_sync >> 16) & 0xff );

        if (flags & FIND_REMOTE) printf(NAME "REM %c%c%c ext %4d det %4d time %08x %3d\n", fd, f1, fm, ph_ext, phase, t_sync, time);
        else printf(NAME "LOC %c%c%c ext %4d det %4d time %08x %3d\n", fd, f1, fm, ph_ext, phase, t_sync, time);

        // search jump in t1
        if (search_positive) { // increase phase
            if (*tL == 0) { // first time: save first t1
                if (flags & FIND_NONE) { // do no search jump, just output pulse
                    if (flags & FIND_DELTA) {
                        *tL = (((t_sync >> 16) & 0xff) - (t_sync & 0xff));
                        *tH = ((t_sync >> 24) - ((t_sync >> 8) & 0xff));
                    }
                    else {
                        *tL = ((t_sync >> 16) & 0xff);
                        *tH = ((t_sync >> 24) & 0xff);
                    }
                    break;
                }
                *tL = time;
            }
            if ( time == *tL ) { // same time: next phase
                reps = 0; // reset statistics 
                phase += step;
                if (phase >= (*start + PHASE_360)) { // reduce step size if wrapping around
                    phase -= PHASE_360;
                    step/=2;
                    if (step == 0) step = 1;
                }
            }
            else { // time changed: do statistics with same phase
                if (*tH == 0) { // first jump
                    if (flags & FIND_NEGATIVE) {
                        if (time < *tL) *tH = time; // jump negative
                        else { // wrong jump direction: reset tL and continue
                            *tL = time;
                            reps = 0;
                            phase += step;
                            continue;
                        }
                    }
                    else {
                        if (time > *tL) *tH = time; // jump positive
                        else { // wrong jump direction: reset tL and continue
                            *tL = time;
                            reps = 0;
                            phase += step;
                            continue;
                        }
                    }
                }
                if (time == *tH) {
                    if (++reps >= PHASE_REPS) { // 100% tH detected: save end and reverse direction
                        step /= 2;
                        if (step == 0) step = 1;
                        *end = phase;
                        phase -= step;
                        reps = 0;
                        search_positive = false;
                    }
                }
                else { // jump to 3rd time!
                    if (flags & FIND_FINE) {
                        if (++err_count > ERROR_MAX) {
                            if (++rst_count >= 8) { err=-11; break; } // cannot recover
                            else { // re-start with phase - 45*rst_count degree. maybe first jump was an outlier?
                                printf(NAME, "3rd time encountered, retry %d/%d...\n", rst_count, 8);
                                phase -= PHASE_360/8*rst_count;
                                if (phase < 0) phase += PHASE_360;
                                *tL = *tH = 0;
                                *start = 0; *end = PHASE_360; step = (*end - *start)/PHASE_STEPS;
                                err_count = 0;      
                            }
                        }
                    }
                    else { // abort immediately
                        err=-11; 
                        break;
                    }
                }
            }
        }
        else { // decrease phase
            if ( time == *tH ) { // same time: next phase
                reps = 0; // reset statistics 
                phase -= step;
                if (phase <= (*end - PHASE_360)) { // reduce step size if wrapping around
                    phase += PHASE_360;
                    step/=2;
                    if (step == 0) step = 1;
                } 
            }
            else { // time changed: do statistics with same phase
                if (time == *tL) {
                    if (++reps >= PHASE_REPS) { // 100% tL detected: save start and search in narrower range if not goal reached
                        int tmp = (*end - phase)/PHASE_STEPS;
                        if ((tmp == 0) || (tmp >= step)) break; // search is finished for primary and secondary boards
                        step = tmp;
                        *start = phase;
                        phase += step;
                        reps = 0;
                        search_positive = true;
                    }
                }
                else { // jump to 3rd time?
                    if (flags & FIND_FINE) {
                        if (++err_count > ERROR_MAX) {
                            if (++rst_count >= 8) { err=-21; break; } // cannot recover
                            else { // re-start with phase - 45*rst_count degree. maybe first jump was an outlier?
                                printf(NAME, "3rd time encountered, retry %d/%d...\n", rst_count, 8);
                                phase += PHASE_360/8*rst_count;
                                if (phase > PHASE_360) phase -= PHASE_360;
                                *tL = *tH = 0;
                                *start = 0; *end = PHASE_360; step = (*end - *start)/PHASE_STEPS;
                                err_count = 0;
                                search_positive = true;      
                            }
                        }
                    }
                    else { // abort immediately
                        err=-21; 
                        break;
                    }
                }
            }
        }
    } // next loop

    // return tL < tH
    if (*tL > *tH) { uint8_t tmp = *tH; *tH = *tL; *tL = tmp; }

    return err;
}

#define RESULT_NAME      "/mnt/sd/result.csv"
#define STEPS_NAME       "/mnt/sd/steps.csv"

#define LOOPS_COARSE    5               // coarse adjustment loops
#define LOOPS_FINE      (3*28)          // maximum number of fine adjustment loops
#define LOOPS_RUN       25              // number of RUN loops
#define PHASE_360       1120            // 360 degree = (1/50MHz)/(1/(56*1000MHz)); 1GHz/56 = 17.857ps/step, 20ns/17.857ps = 1120 steps
#define PHASE_STEP      (PHASE_360/28)  // phase increment per step

#define LOOPS_TOTAL     (LOOPS_COARSE+LOOPS_FINE+LOOPS_RUN)
#define DATA_MAX        500             // maximum number of lines to save on csv

#define MODE_COARSE     0               // determine of coarse delay
#define MODE_FINE       1               // determine phase shift
#define MODE_RUN        2               // delay and phase determined

#define CYCLE_TIME_NS       20                                  // cycle time in ns
#define CYCLE_TIME_PS       (CYCLE_TIME_NS*1000)                // cycle time in ps
#define PHASE_PLUS_DEG      25                                  // phase of positive jump in degree
#define PHASE_PLUS          ((PHASE_PLUS_DEG*PHASE_360)/360)    // phase of positive jump in steps
#define PHASE_PLUS_PS       ((PHASE_PLUS_DEG*CYCLE_TIME_PS)/360)// phase of positive jump in ps
#define PHASE_DET           ((70*PHASE_360)/360)                // phase offset of detection clock in steps
#define PHASE_P_CRNG        ((20*PHASE_360)/360)                // phase in steps if fi_p is within this to threshold add_1 add/subtract PHASE_EXT_ADD to fi_ext
#define PHASE_EXT_ADD       ((30*PHASE_360)/360)                // phase in steps added/subtracted to fi_ext if fi_p is within critical range PHASE_P_CRIT
#define PHASE_MARGIN        ((90*PHASE_360)/360)                // phase margin in steps
#define PRIM_RT_OFFSET_PS   205000                              // primary board const offset in ps from fit RT time vs. cable length 
#define SEC_PH_OFFSET_PS    -2000                               // secondary board const offset in ps from fit time vs. cable length 
#define SEC_PH_OFFSET       ((SEC_PH_OFFSET_PS*PHASE_360)/CYCLE_TIME_PS) // secondary board const offset in steps
#define PHASE_CORR          ((20*PHASE_360)/360)                // phase correction in steps added to have zero error (positive shifts primary board later i.e. reduces error)
#define WAIT_ADD            3                                   // additional cycles to add for wait time
#define PULSE_SPEED         5.3                                 // propagation speed for estimation of cable length

// test flags for find_jumps to be executed for MODE_FINE
#define NUM_TEST                8                               // number of tests to be done
int test[NUM_TEST] = {  FIND_T0|FIND_NEGATIVE,                       
                        FIND_T1|FIND_NEGATIVE|FIND_FINE,                                // primary board phase measurement
                        FIND_T0|FIND_NEGATIVE|FIND_DELTA|FIND_REMOTE|FIND_FINE,         // secondary board phase measurement
                        FIND_T1|FIND_NEGATIVE|FIND_DELTA|FIND_REMOTE,
                        FIND_T0|FIND_POSITIVE,
                        FIND_T1|FIND_POSITIVE,
                        FIND_T0|FIND_POSITIVE|FIND_DELTA|FIND_REMOTE,
                        FIND_T1|FIND_POSITIVE|FIND_DELTA|FIND_REMOTE
};
// choose index into test which is used for average of primary and secondary boards
#define USE_TEST_PRIM_T0    0
#define USE_TEST_PRIM_T1    1
#define USE_TEST_SEC_T0     2
#define USE_TEST_SEC_T1     3
// resulting phase limits, tL, tH
int ph_start[NUM_TEST];
int ph_end[NUM_TEST];
uint8_t tL[NUM_TEST];   
uint8_t tH[NUM_TEST];

// map angle in steps to 0 .. PHASE_360
// note: in C % gives the remainder with the sign of y.
#define MAP_360(y)          ((((y) < 0) ? (PHASE_360 + ((y) % PHASE_360)) : ((y) % PHASE_360)))
// returns the average of the two phases (can be negative)
#define AVG_PHASE(x,y)      ((x)+angle_diff(x,y)/2)

// calculates the difference in angles in steps
// returns the smallest difference in angles y-x
// the sign is positive when x rotated into y is counter-clockwise
int angle_diff(int x, int y) {
    int d;
    x = MAP_360(x);
    y = MAP_360(y);
    d = y-x;
    if (abs(d) <= abs(PHASE_360-abs(d))) return d;
    else return -d/abs(d)*(PHASE_360-abs(d));
}

// tests angle_diff for known cases (not exhaustive)
int angle_diff_test(void) {
    int x, y, d;
    x=10;y=20;d=10;
    if (angle_diff(x,y)!=d) goto ad_error;
    x=20;y=10;d=-10;
    if (angle_diff(x,y)!=d) goto ad_error;
    x=1000;y=10;d=130;
    if (angle_diff(x,y)!=d) goto ad_error;
    x=10;y=1000;d=-130;
    if (angle_diff(x,y)!=d) goto ad_error;
    x=10;y=570;d=560;
    if (angle_diff(x,y)!=d) goto ad_error;
    x=570;y=10;d=-560; // TODO: this gives negative result but here its a matter of definition
    if (angle_diff(x,y)!=d) goto ad_error;
    x=800;y=800;d=0;
    if (angle_diff(x,y)!=d) goto ad_error;
    return 0;
ad_error:
    printf(NAME "angle_diff %d - %d = %d but %d expected!\n",y,x,angle_diff(x,y),d);
    return -1;
}

// performs auto-sync of trg_delay for the given boards IP addresses
// command line must be "FPGA-test -y IP0 IP1 IP2 etc."
// changed to "FPGA-test -y phase0 [reps] [step]" if only phase0 searchs jumps, if reps repeats reps times with same phase, if reps + step adds steps for each repetition
// for testing instead of IP0 give phase in degree during coarse tuning
// returns 0 if ok otherwise error
// FPGA-test -y ext = auto-sync, ext = secondary external clock phase in steps. constant during measurement.
// FPGA-test -y phase reps = repeat reps x with given phase in steps (1120 = 360 degree @ 50MHz)
// FPGA-test -y start stop step = scan phase from start to stop with given step width. all units in steps.
// FPGA-test -y delay ext det reps = repeat reps times with primary delay in cycles, secondary ext phase in steps and secondary detection phase in steps
int auto_sync(int argc, char *argv[]) {
    int err = 0, i, j, k, tmp, tot, ph_det = 0, ph_ext = 0, ph_step = 0, mode, max_loops = LOOPS_COARSE, boards, d_len, fi_p_crit;
    int dma24_dev;
    float cable_length = 0.0f;
    uint32_t config, delay_max = 0, delay = 0, status, count, *data;
    uint32_t *brd_delay = NULL;         // delay per board
    uint32_t *brd_phase = NULL;         // phase per board
    SOCKET sock = INVALID_SOCKET;
    bool add_1 = false;
    fi_p_crit = MAP_360(PHASE_360 - PHASE_MARGIN - PHASE_CORR - PHASE_DET);
#ifdef AS_SEC
    const char *IP = AS_SEC;
    SERVER_CMD cmd;
#endif
    //struct FPGA_status_run st;
    if (argc < 3) err = -1; // no parameter given
    else if ((argv[1][0]!='-') || (argv[1][1]!='y') || (argv[1][2]!='\0')) { printf(NAME "error wrong argument \"%s\"!\n", argv[1]); err = -2; } // only option "-y" allowed 
    else {
        dma24_dev = dma24_open(0); // open primary device
        if(dma24_dev <= 0) { printf(NAME "error open device\n"); err = -10; }
        else {
            //boards = argc - 2;
            boards = 1;
            d_len = AS_COLS*DATA_MAX;
            brd_delay = data = new uint32_t[d_len];
            //brd_phase = new uint32_t[LOOPS_TOTAL];

            // init delay and phases
            for (i = 0; i < LOOPS_TOTAL; ) { 
                for (j = 0; j < AS_COLS; ++j) brd_delay[i++] = 0; 
            }

            // go through secondary boards and measure individual trigger delay
            for (i = 0; (i < boards) && (!err); ++i) {
                delay = 0;
                switch (argc) {
                    case 3: // auto-sync
                        ph_ext = MAP_360(atol(argv[2])) & SYNC_PHASE_MASK_1; // secondary external clock phase in steps
                        ph_det = 0;
                        max_loops = LOOPS_COARSE;
                        mode = MODE_COARSE;
                        break;
                    case 4: // repeat
                        ph_ext = 0;
                        ph_det = MAP_360(atol(argv[2])) & SYNC_PHASE_MASK_1;// phase in steps.
                        max_loops = atol(argv[3]);                      // number of repetitions
                        mode = MODE_COARSE;
                        break;
                    case 5: // scan phase
                        ph_ext = 0;
                        ph_det = MAP_360(atol(argv[2])) & SYNC_PHASE_MASK_1;      // initial phase in steps
                        max_loops = MAP_360(atol(argv[3])) & SYNC_PHASE_MASK_1;  // final phase in steps
                        ph_step = atol(argv[4]) & SYNC_PHASE_MASK_1;    // step width
                        if (ph_step == 0) ph_step = 1; 
                        max_loops = (max_loops - ph_det)/ph_step + 1 + (((max_loops - ph_det)%ph_step == 0) ? 0 : 1);
                        mode = MODE_COARSE;
                        break;
                    case 6: // manual auto-sync
                        delay = atol(argv[2]) & SYNC_DELAY_MASK;        // primary waiting time in cycles
                        ph_ext = MAP_360(atol(argv[3])) & SYNC_PHASE_MASK_1;     // secondary external clock phase in steps
                        ph_det = MAP_360(atol(argv[4])) & SYNC_PHASE_MASK_1;      // secondary det phase in steps
                        max_loops = atol(argv[5]);                      // repetitions
                        mode = MODE_RUN;
                        break;
                    default:
                        ph_det = ph_ext = 0;
                        max_loops = MODE_COARSE;
                        mode = MODE_COARSE;
                }
                tot = 0;
                printf(NAME "initial phase ext/det = %d/%d, loops = %d\n", ph_ext, ph_det, max_loops);
#ifdef AS_SEC
                //IP = argv[i+2];
                printf(NAME "auto-sync board %d IP \"%s\"\n", i, IP); sleep_ms(10);

                // connect to secondary board
                sock = _connect(IP, SERVER_PORT);
                if(sock == INVALID_SOCKET) { printf(NAME "connection to IP \"%s\" failed!\n", IP); err = -100; break; }

                // open secondary device
                cmd = SERVER_CMD_OPEN;
                err = send_recv(sock, (char*)&cmd, sizeof(SERVER_CMD));
                if (err != RECV_ACK) { printf(NAME "error %d open scondary board\n", err); CLOSESOCKET(sock); sock = INVALID_SOCKET; break; }
#endif

                // repeat measurement for max_loops loops
                for (j = 0; (j < max_loops) && (!err); ++j) {
                    add_1 = false;
                    if (j==0) { // reset primary board to go back to 0 phase (note: this resets external clock for about 7us!)
                        err = dma24_reset(dma24_dev);
                        if (err) { printf(NAME "reset primary board error %d\n", err); break; }
                        sleep_ms(10); // keep this to ensure external clock is stable!
                    }
                    switch (mode) {
                        case MODE_COARSE:
                            // get coarse round trip time
                            err = find_jump(dma24_dev, sock, ph_ext, &ph_det, (int*)&delay, &tL[0], &tH[0], data, &d_len, FIND_NONE);
                            sleep_ms(20); printf(NAME "%3d COARSE phase %d RT time %u/%u status 0x%x, error %d\n", j, ph_det, (unsigned)tL[0], (unsigned)tH[0], status, err); sleep_ms(20);
                            //delay_old = brd_delay[i] = st.board_time;               // save tentative coarse delay. correct within +/-1
                            if((j+1) == max_loops) {
                                printf(NAME "save %d measurements to file %s\n", DATA_MAX-d_len/AS_COLS, STEPS_NAME);
                                save_CSV(STEPS_NAME, brd_delay, AS_COLS*DATA_MAX-d_len, AS_COLS);
                                d_len = AS_COLS*DATA_MAX;
                                data = brd_delay;
                                if (argc == 3) {
                                    mode = MODE_FINE;
                                    max_loops = LOOPS_FINE;
                                    j = -1;
                                }
                            }
                            else ph_det += ph_step;
                            break;
                        case MODE_FINE:
                            for (k = 0; k < NUM_TEST; ++k) {
                                ph_start[k] = 0; ph_end[k] = PHASE_360 - 1;
                                err = find_jump(dma24_dev, sock, ph_ext, &ph_start[k], &ph_end[k], &tL[k], &tH[k], data, &d_len, test[k]);
                                sleep_ms(20); 
                                printf(NAME "%d/%d FINE phase %d(%d) time %u/%u error %d\n", j, k, (ph_end[k] + ph_start[k])/2*360/PHASE_360, (ph_end[k] - ph_start[k])/2*360/PHASE_360, (unsigned)tL[k], (unsigned)tH[k], err); 
                                sleep_ms(20);
                                if (!(test[k] & FIND_REMOTE)) { // save only local measurements
                                    printf(NAME "save %d measurements to file %s\n", DATA_MAX-d_len/AS_COLS, STEPS_NAME);
                                    save_CSV(STEPS_NAME, brd_delay, AS_COLS*DATA_MAX-d_len, AS_COLS);
                                }
                                d_len = AS_COLS*DATA_MAX;
                                data = brd_delay;
                                if (err && (test[k] & FIND_FINE)) break; // stop on error, but only for important measurements, others are just for documentation.
                                else err = 0;
                            }
                            if(!err) {
                                // summary
                                sleep_ms(20); 
                                printf("summary result:\n");
                                for (k = 0; k < NUM_TEST; ++k) {
                                    printf(NAME "%d RT time %3u/%3u ns phase %3d/%3d degree\n", k, tL[k], tH[k], ph_start[k]*360/PHASE_360, ph_end[k]*360/PHASE_360);
                                    if(data && (d_len >= AS_COLS)) { 
                                        *data++ = k;
                                        *data++ = tL[k]; // lower time in cycles
                                        *data++ = tH[k]; // upper time in cycles
                                        *data++ = ph_start[k]; // start phase in steps
                                        *data++ = ph_end[k]; // end phase in steps
                                        d_len -= AS_COLS;
                                    }
                                }
                                // primary average phase t1 in ps
                                k = AVG_PHASE(ph_end[USE_TEST_PRIM_T1],ph_start[USE_TEST_PRIM_T1]);
                                k = MAP_360(k); // map to positive side [0..360[
                                k = (k*CYCLE_TIME_PS)/PHASE_360;
                                // one-way cable propagation time in ps. 
                                // we use primary t1 and secondary t0 since they have the same fitted speed.
                                // RT time is increased by one cycle when phase below positive jump.
                                delay = ((tH[USE_TEST_PRIM_T1]*CYCLE_TIME_PS + k - PRIM_RT_OFFSET_PS) + ((k < PHASE_PLUS_PS) ? CYCLE_TIME_PS : 0)) / 2;
                                //printf(NAME "cable propagation time %u cycles + %u ps (%u ps)\n", delay/CYCLE_TIME_PS, delay % CYCLE_TIME_PS, delay);
                                // fi_p = primary pulse phase at secondary board (including generation & detection time)
                                k = (((delay + PRIM_RT_OFFSET_PS) % CYCLE_TIME_PS)*PHASE_360)/CYCLE_TIME_PS;
                                // fi_s = secondary board pulse t0 phase steps with respect to external clock (ext.phase=0)
                                // we use primary t1 and secondary t0 since they have the same fitted speed.
                                // note: on secondary board no correction for smaller positive phase jump is needed
                                j = AVG_PHASE(ph_start[USE_TEST_SEC_T0],ph_end[USE_TEST_SEC_T0]) - SEC_PH_OFFSET;
                                j = MAP_360(j); // map to positive side [0..360[
                                printf(NAME "primary/secondary phase %d/%d steps\n", k, j);
                                // fi_ext = external clock phase with PHASE_CORRection applied
                                tmp = j - k - PHASE_CORR;
                                tmp = MAP_360(tmp); // map to positive side [0..360[
                                // fi_det = detector phase relative to global clock in steps
                                // note: we map to positive side but do not limit to 360 degrees, so we can check below for additional cycle!
                                ph_det = k + PHASE_CORR + PHASE_DET; 
                                if (ph_det < 0) ph_det += PHASE_360;
                                // ensure detector phase is outside [-PHASE_MARGIN,+PHASE_MARGIN] of bus clock
                                if (ph_det < PHASE_MARGIN) ph_det = PHASE_MARGIN;
                                else if ((ph_det + PHASE_MARGIN) > PHASE_360) {
                                    add_1 = true;           // add one cycle
                                    ph_det -= PHASE_360;
                                    if (ph_det < PHASE_MARGIN) ph_det = PHASE_MARGIN;
                                    printf(NAME "note: add 1 cycle!\n");
                                }
                                // if fi_p is close to critical value we are very sensitive to noise and drifts. 
                                // in this case add/subtract security phase to fi_ext which increases error but ensures we are on save side
                                if (k >= fi_p_crit) {
                                    if ((k - fi_p_crit) < PHASE_P_CRNG) { // above but near threshold
                                        tmp -= PHASE_EXT_ADD;
                                        printf(NAME "note: subtract %d steps to fi_ext gives %d!\n", PHASE_EXT_ADD, tmp);
                                    }
                                }
                                else if ((fi_p_crit - k) < PHASE_P_CRNG) { // below but near threshold
                                    tmp += PHASE_EXT_ADD;
                                    printf(NAME "note: add %d steps to fi_ext gives %d!\n", PHASE_EXT_ADD, tmp);
                                }
                                if(data && (d_len >= AS_COLS)) { // last line = summary of secondary board 
                                    *data++ = NUM_TEST;
                                    *data++ = delay;        // cable propagation time in ps
                                    *data++ = j;            // secondary phase in steps
                                    *data++ = tmp;          // external clock phase in steps
                                    *data++ = ph_det;       // detector clock phase in steps
                                    d_len -= AS_COLS;
                                }
                                ph_ext = MAP_360(ph_ext + tmp); // secondary external phase
                                cable_length = ((float)delay) / (1000.0f*PULSE_SPEED);
                                printf(NAME "propagation time %d ns, estimated cable length %.3f m\n", delay/1000, cable_length);
                                // waiting time in cycles
                                delay = ((delay + PRIM_RT_OFFSET_PS) / CYCLE_TIME_PS) + WAIT_ADD + (add_1 ? 1 : 0);
                                if (delay_max < delay) delay_max = delay;
                                // summary result
                                printf(NAME "waiting time %u cycles, secondary phase ext/det %d/%d steps\n", delay, k, j);
                                // save summary
                                printf(NAME "save %d results to file %s\n", DATA_MAX-d_len/AS_COLS, RESULT_NAME);
                                save_CSV(RESULT_NAME, brd_delay, AS_COLS*DATA_MAX-d_len, AS_COLS);
                                d_len = AS_COLS*DATA_MAX;
                                data = brd_delay;
                                // auto-sync is finished
                                sleep_ms(1000);
                                mode = MODE_RUN;
                                max_loops = LOOPS_RUN;
                                j = -1;
                            }
                            break;
                        case MODE_RUN:                                              // run until all LOOPS done
                            err = find_jump(dma24_dev, sock, ph_ext, &ph_det, (int*)&delay, &tL[0], &tH[0], data, &d_len, FIND_NONE|FIND_RUN);
                            sleep_ms(20); 
                            printf(NAME "%3d/%d RUN prim delay %d, sec. phase %d/%d\n", j, max_loops, delay, ph_ext & SYNC_PHASE_MASK_1, ph_det & SYNC_PHASE_MASK_1);
                            sleep_ms(20);
                            break;
                    }

                } // next loop

#ifdef AS_SEC
                // close secondary device
                cmd = SERVER_CMD_CLOSE;
                send_recv(sock, (char*)&cmd, sizeof(SERVER_CMD));

                // close socket
                CLOSESOCKET(sock); 
                sock = INVALID_SOCKET;
#endif

                sleep_ms(100);
            } // next secondary board
 
            delete[] brd_delay;
            brd_delay = NULL;

            //delete[] brd_phase;
            //brd_phase = NULL;

            dma24_close(dma24_dev);
        }
    }
    if (err) {
        printf(NAME "auto-sync error %d\n\n", err);
    }
    else {
        printf(NAME "auto-sync estimated cable length %.3f m ok\n\n", cable_length);
    }
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

// CSV filename and number of columns to arrange data
#define FILE_NAME       "/mnt/sd/result.csv"
#define FILE_COLS       12

// main program
int main(int argc, char *argv[])
{
    int err = 0, opt, dma24_dev, o;
    int ext_clk = 0;
    int send_data = 0, num_cpu = 2;
    char *cmd;
    TP params = {
        .config = TEST_CONFIG,
        .reps = TEST_REPS,
        .timeout = TEST_TIMEOUT,
        .RX_s_buf = 0,
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

    angle_diff_test();

    while ((opt = getopt(argc, argv, ":y:r:t:x:b:vae:z:m:n:su:")) != -1) {
        o = opt;
        switch (opt) {
            case 'y': printf(NAME "auto-sync\n"); break; // auto-sync with given secondary board IP addresses
            case 'x': send_data = atol(optarg); break; // send test data #
            case 'r': params.reps = atol(optarg); params.config |= DIO_CTRL_IRQ_RESTART_EN|DIO_CTRL_RESTART_EN; printf(NAME "repetitions = %d\n",params.reps); break; // set repetitions
            case 't': params.timeout = atol(optarg); printf(NAME "timeout = %d\n",params.timeout); break; // set timeout
            case 'b': params.RX_s_buf = atol(optarg); printf(NAME "RX buf samples = %d\n",params.RX_s_buf); break; // set RX buffer size
            case 'u': printf(NAME "USB test\n"); cmd = optarg; break; // USB test
            case 'v': params.verify = true; printf(NAME "read & verify\n"); break; // read and verify
            case 'a': params.all = true; printf(NAME "show all\n"); break; // show all debug info
            case 'e': ext_clk = atoi(optarg); printf(NAME "lock to external clock = %d\n", ext_clk); break; // lock to external clock if != 0
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
        else if (o == 'y') err = auto_sync(argc, argv); // auto-sync of trg_delay
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
                if(ext_clk) {
                    uint32_t config = DIO_CTRL_EXT_CLK;
                    err = dio24_set_config(dma24_dev, &config);
                    sleep_ms(20);
                    if(err < 0) printf(NAME "set_config failed with error %d!\n", err);
                    else {
                        printf(NAME "set_config %x, old = %x ok\n", DIO_CTRL_EXT_CLK, config);
                    }
                }
                err = get_status(dma24_dev, params.all);
                sleep_ms(20);
                if((status.ctrl_FPGA & DIO_CTRL_EXT_CLK) && (!ext_clk)) {
                    uint32_t config = 0;
                    err = dio24_set_config(dma24_dev, &config);
                    sleep_ms(20);
                    if(err < 0) printf(NAME "set_config failed with error %d!\n", err);
                    else {
                        printf(NAME "set_config %x, old = %x ok\n", 0, config);
                    }
                }
                dma24_close(dma24_dev);
                sleep_ms(20);
                if(err) printf(NAME "get_status error = %d\n", err);
                else printf(NAME "get_status (ok)\n");
            }
        }
    }

    return err;
}


