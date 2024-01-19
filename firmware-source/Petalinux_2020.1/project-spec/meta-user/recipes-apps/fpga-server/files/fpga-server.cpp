////////////////////////////////////////////////////////////////////////////////////////////////////
// fpga-server.cpp
// 32bit Linux console application to be run on Xilinx Zynq-7020 FPGA with Petalinux
// created 2018/06/15 by Andi
// last change 2023/09/30 by Andi
// compiled with Visual Studio Express 2013 and g++
// tested with Windows 7, Ubuntu 18.04LTS, 20.04LTS and Petalinux 2017.4,2020.1
////////////////////////////////////////////////////////////////////////////////////////////////////

#include <stdio.h>              // printf for testing
#include <stdlib.h>             //_getch, system
#include <time.h>               // nanosleep
#include <string.h>             // strncmp, strncpy
#include <sys/ioctl.h>          // SIOCGIFFLAGS
#include <netinet/in.h>         // IPPROTO_IP
#include <net/if.h>             // IFF_*, ifreq
#include "fpga-server.h"        // FPGA-server class

////////////////////////////////////////////////////////////////////////////////////////////////////
// globals and static members
////////////////////////////////////////////////////////////////////////////////////////////////////

#ifdef _WINDOWS

WCHAR ServerInfo[] = L(SERVER_INFO);

#else

char ServerInfo[] = SERVER_INFO;

// used for kbhit() and getch() 
struct termios conio::old_attributes;

#endif

// shutdown text and keys
#define WAIT_TEXT_SHUT        "\nmaster: hit <ESC> or 'X' to shutdown server ...\n\n"
#define WAIT_TEXT_CONT        "\nmaster: hit <ESC> or 'X' to continue ...\n\n"
#define WAIT_KEY_1        '\x1B'
#define WAIT_KEY_2        'X'

// IP interface and mask
#define IP_INTF "eth0"
#define IP_MASK "255.255.255.0"
char ip_intf[] = IP_INTF;
char ip_mask[] = IP_MASK; 

// names used for printf
char str_master[]  = MASTER;
char str_server[]  = SERVER;
char str_client[]  = CLIENT; 

// internal server commands
SERVER_CMD ack  = SERVER_ACK;
SERVER_CMD nack = SERVER_NACK;
SERVER_CMD shtd = SERVER_SHUTDOWN;

// list of DIO64 commands
SERVER_CMD server_cmd[SERVER_CMD_NUM] = SERVER_CMD_LIST;

// data types for SendData
#define DATA_CD32           1
#define DATA_CD64           2
#define DATA_STATUS         3
#define DATA_STATUS_FULL    4

////////////////////////////////////////////////////////////////////////////////////////////////////
// forward declarations
////////////////////////////////////////////////////////////////////////////////////////////////////

// send command with command specific data and read responds of resp_num bytes
// returned data of num bytes is saved in data and must be deleted (except when NULL)
int send_cmd(char *name, FPGA_server *server, client_info *cli_server, char *&data, int &num, int resp_num);

// show U16
void show_data(unsigned char *data, int num, bool is_time_data);

// test data for device address 0x01, digital out
// data is in little-endian byte order (LSB first)!
// data sample = 32bit time (in mu, max. >1h), 16bit data, 7bit address, 1bit strobe, 8bit 0s
#define TEST_DATA_NUM_SAMPLES    69
extern uint32_t test_data[TEST_DATA_NUM_SAMPLES*2];

// sleep time in ms
// uses nanosleep defined in <time.h>
void sleep_ms(uint32_t ms);

// measure elapsed time in microseconds
// wraps over every ca. 4295s ca. 71'
uint32_t get_ticks(void);

// save 2D data of length 32bits to CSV file with given number of columns
// if file exists data is appended to existing data, otherwise new file is created
// returns 0 if ok, otherwise error code
int save_CSV(const char *name, uint32_t *data, int length, int columns) {
    int err = 0, col, cnt;
    FILE *fd = fopen(name, "a");
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
    return err;
}

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
// first call is initializing buffers cpu_sum and cpu_idle with num_cpu entries each.
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

////////////////////////////////////////////////////////////////////////////////////////////////////
// check if interface is up and set ip and mask
////////////////////////////////////////////////////////////////////////////////////////////////////

int set_IP(char *interface, char *ip_address, char *ip_mask) {
    int state = -1;
    struct ifreq ifr;
    struct sockaddr_in* addr = (struct sockaddr_in*)&ifr.ifr_addr;;
    char old_ip[INET_ADDRSTRLEN];
    int flags;
    int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (sock < 0) {
        printf("create socket failed. Errno = %d\n", errno);
    }
    else {
        strncpy(ifr.ifr_name, interface, IFNAMSIZ);
        state = ioctl(sock, SIOCGIFFLAGS, &ifr);
        if ( state < 0 ) {
            printf("get flags (1) failed. Errno = %d\n", errno);
        }
        else {
            flags = ifr.ifr_flags;
                                            
            if ((flags & IFF_UP) == 0) { //|| (!(flags & IFF_RUNNING)) ) {
                // network not configured yet after boot
                // in this case SIOCGIFADDR fails with errno 99 (EADDRNOTAVAIL)
                printf("actual flags 0x%x (need 0x%x)\n",flags, IFF_UP); // | IFF_RUNNING); 
                state = -2;
            }
            else {
                // interface is ready
            
                // get actual IP address
                state = ioctl(sock, SIOCGIFADDR, &ifr);
                if ( state < 0 ) {
                    printf("get IP (1) failed. Errno = %d\n", errno);
                }
                else {
                    inet_ntop(AF_INET, &addr->sin_addr, old_ip, INET_ADDRSTRLEN);
                    printf("actual flags 0x%x (ok), IP '%s'\n", flags, old_ip); 

                    // set IP address
                    inet_pton(AF_INET, ip_address, &addr->sin_addr);
                    ifr.ifr_addr.sa_family = AF_INET;
                    state = ioctl(sock, SIOCSIFADDR, &ifr);
                    if ( state < 0 ) {
                        printf("set address failed. Errno = %d\n", errno);
                    }
                    else {
                        // set net mask
                        inet_pton(AF_INET, ip_mask, &addr->sin_addr);
                        state = ioctl(sock, SIOCSIFNETMASK, &ifr);
                        if ( state < 0 ) {
                            printf("set mask failed. Errno = %d\n", errno);
                        }
                        else {
                            // read actual flags
                            state = ioctl(sock, SIOCGIFFLAGS, &ifr);
                            if ( state < 0 ) {
                                printf("get flags (2) failed. Errno = %d\n", errno);
                            }
                            else {
                                flags = ifr.ifr_flags;
                                        
                                if ((flags & IFF_UP) == 0) { //|| (!(flags & IFF_RUNNING)) ) {
                                    // this should not happen!?
                                    printf("actual flags 0x%x (need 0x%x)\n",flags, IFF_UP); // | IFF_RUNNING); 
                                    state = -3;
                                }
                                else {
                                    // most examples set this manually but IFF_UP should be set already. 
                                    // and RUNNING = cable connected, should be set only by driver. maybe this allows it to set?
                                    //ifr.ifr_flags |= (IFF_UP | IFF_RUNNING);
                                    //state = ioctl(sock, SIOCSIFFLAGS, &ifr);
                                    
                                    // get actual IP address
                                    state = ioctl(sock, SIOCGIFADDR, &ifr);
                                    if ( state < 0 ) {
                                        printf("get IP (2) failed. Errno = %d\n", errno);
                                    }
                                    else {
                                        inet_ntop(AF_INET, &addr->sin_addr, old_ip, INET_ADDRSTRLEN);
                                        printf("new    flags 0x%x (ok), IP '%s'\n", flags, old_ip); 
                                        //deprecated to return IP string inet_ntoa(addr->sin_addr)
                                    
                                        //state = 0;
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        close(sock);
    }
    return state;
}

////////////////////////////////////////////////////////////////////////////////////////////////////
// queue class
////////////////////////////////////////////////////////////////////////////////////////////////////

// default constructor
queue::queue() {
    sem_init(&sem, 0, 0); // share between threads, 0 initial count
    pthread_mutex_init(&mutex, NULL);
    first = last = NULL;
}

// destructor
queue::~queue() {
    pthread_mutex_lock(&mutex);
    if (first != NULL) {
        printf("queue: deleting non-empty queue! danger of memory leakage!\n");
        while(first) {
            queue_entry *next = first->next; 
            delete first;
            first = next;
        }
    }
    last = NULL;
    sem_destroy(&sem);
    pthread_mutex_destroy(&mutex);
}

// append entry (can be several) to queue
// Attention: ensure entry->next == NULL for last entry.
void queue::put(queue_entry *entry) {
    pthread_mutex_lock(&mutex);
    if (last == NULL) first = last = entry;
    else last = last->next = entry;
    while(last->next) {     // for several entries: increment semaphore for each of them and find last
        sem_post(&sem);
        last = last->next;
    }
    pthread_mutex_unlock(&mutex);
    sem_post(&sem);
}

// remove maximum max entries from queue (<0 for all, 0 = peek first entry without removing)
// if max = 0: does not wait but returns pointer to first entry without locking mutex or removing enrty. use only to check if queue is empty!
//             if this is NULL queue was at that moment empty, if its not NULL queue was not empty at that moment. 
//             Attention: do not use the returned pointer, since its not reliable if serveral threads can remove entries!
//             call get() with max!=0 to return the entry - this call will not wait unless another thread has already removed the entry.
// timeout_ms = maximum time the thread will wait in ms until the function returns with NULL
// TODO: what happens with timeout_ms = 0?
struct queue_entry *queue::get(int max, unsigned timeout_ms) {
    struct queue_entry *tmp = NULL;                 // returns NULL on timeout or error
    struct timespec ts;
    int s;
    if (max == 0) tmp = first;                      // peek first entry without locking or removing from queue! 
    else {
        if (clock_gettime(CLOCK_REALTIME, &ts) != -1) {
            ts.tv_sec += timeout_ms/1000;
            ts.tv_nsec += (timeout_ms % 1000)*1000000;
            s = sem_timedwait(&sem, &ts);
            if (s == 0) {                           // success (on timeout s=-1 and errno == ETIMEDOUT)
                pthread_mutex_lock(&mutex);
                tmp = first;
                if (max > 0) {                      // try to remove max entries
                    struct queue_entry *l = tmp;
                    while(l->next && (--max > 0)) l = l->next;
                    first = l->next;
                    if (first == NULL) last = NULL; // all removed
                    else l->next = NULL;
                }
                else { // remove all entries
                    first = last = NULL;
                }
                pthread_mutex_unlock(&mutex);
            }
        }
    }
    return tmp;
}

////////////////////////////////////////////////////////////////////////////////////////////////////
// helper thread
////////////////////////////////////////////////////////////////////////////////////////////////////

// configure FPGA for auto-sync with given sync delay and phase
// note: keep this function consistent with FPGA-server!
int as_config(int dev, uint32_t delay, int phase, bool reset) {
    int err = 0;
    return err;
}

#define PHASE_STEPS     10                  // number of phase steps in given range
#define PHASE_REPS      5                   // max. number of repetitions with same phase for statistics
#define AS_COLS         SAVE_DATA_COLS      // entries per measurement in result file (must be 5!)
#define FIND_T0         0                   // search jump in t0_PS
#define FIND_T1         1                   // search jump in t1_PS
#define FIND_POSITIVE   0                   // search for positive jump in time
#define FIND_NEGATIVE   2                   // search for negative jump in time
#define FIND_DELTA      4                   // search jump in t0_PS-t0 or t1_PS-1
#ifdef AS_SEC
#define FIND_REMOTE     8                   // search on remote/secondary board (sock != INVALID_SOCKED)
#endif
// NOTE: this is a copy of same function in FPGA-test and it would be good to keep them identical!
// recursively find jumps in sync_time until 2*phase error <= PHASE_GOAL
// start and end give the range of phase where search is intiated in units of PHASE_360
// returns 0 if found, otherwise error code
// use start and end to retrieve result phase = (end+start)/2 and error = (end-start)/2
// result time is saved in time0 and time1
// if start == end measures one time without search and returns time0
// if data !=0 points to data_length uint32_t where phase and sync_time is saved, data is incremented and data_length decremented
// Attention: assumes initial phase = *act_phase and returns last set phase in *act_phase
//            does NOT reset device to keep secondary board locked and changes phase incrementally. 
// note: keep this function consistent with FPGA-test!
int find_jump(int dma24_dev, SOCKET sock, int *act_phase, int *start, int *end, uint8_t *tL, uint8_t *tH, uint32_t *&data, int *data_length, unsigned flags) {
    int err = 0;
    return err;
}

#ifdef SAVE_DATA_FILE
    #define DATA_PTR    server->save_data
    #define DATA_PLN    &server->save_data_length
#else
    #define DATA_PTR    NULL
    #define DATA_PLEN   NULL
#endif

// helper thread entry
// get pointer to FPGA_server class. main thread must ensure queues are valid until helper is closed
// returns error code 0 if ok, otherwise error
THREAD_ENTRY(FPGA_server::helper_thread, class FPGA_server *server)
{
    int err = 0, i;
    class queue* send_queue = NULL;
    class queue* recv_queue = NULL;
    unsigned *cpu_percent = NULL;
    unsigned *cpu_idle = NULL;
    unsigned long long *cpu_sum = NULL;
    bool started = false;

    if(server == NULL) {
        printf(HELPER "error NULL given!\n");
        err = -1;
    }
    else {
        send_queue = server->send_queue;
        recv_queue = server->recv_queue;
        //sleep_ms(20);
        printf(HELPER "running ...\n");

        struct queue_entry *active = NULL, *next;
        while(server->helper_running) {
            // if no active command: wait for new command from queue
            // if command active: check fast if new command on queue, otherwise continue with active command
            next = send_queue->get(1, HELPER_TIMEOUT_MS);   // wait for new command, maximum HELPER_TIMEOUT_MS ms
            if (next) {                                     // new command
                if (active) {
                    delete active;                          // delete active command
                    active = next;                          // retrieve one new command
                }
                else active = next;
            }
            if (active) {
                switch(active->cmd) {
                    case HELPER_CMD_WRITE:                  // write command
                        if ( active->data ) {
                            write_info *wi = (write_info*)active->data;
                            // write data and return number of written bytes, <=0 on error
                            //printf("helper %i: buffer %p bytes %u ...\n", wi->offset, wi->buffer, wi->bytes); //sleep_ms(10);
                            wi->written = write(wi->dma24_dev, wi->buffer, wi->bytes);
                            if (wi->written != wi->bytes) { printf("helper %i: buffer %p bytes %d partial %d\n", wi->offset, wi->buffer, wi->bytes, wi->written); sleep_ms(10); }
                            //else { 
                            //    printf("helper %i: buffer %p bytes %u ok\n", wi->offset, wi->buffer, wi->bytes); //sleep_ms(10); 
                            //}
                            recv_queue->put(active);
                            //delete [] wi->buffer;
                            //wi->buffer = NULL;
                            //delete wi;
                            //active->data = NULL;
                            //delete active;
                            active = NULL;                  // active is sent back to main thread
                        }
                        break;
                    case HELPER_CMD_STAT_START:             // start collecting CPU statistics
                        if (active->data == NULL) err = -10;
                        else {
                            printf(HELPER "START\n");
                            cpu_percent = new unsigned[server->num_cpu];
                            cpu_idle    = new unsigned[server->num_cpu];
                            cpu_sum     = new unsigned long long[server->num_cpu];

                            for (i = 0; i < server->num_cpu; ++i) {
                                cpu_percent[i] = 0; 
                                cpu_idle[i] = 0;
                                cpu_sum[i] = 0;
                            }
                            err = read_CPU_stat(cpu_sum, cpu_idle, cpu_percent, server->num_cpu);
                            if (err) {
                                printf(HELPER "START error (ignore)\n");
                                delete [] cpu_percent; cpu_percent = NULL;
                                delete [] cpu_idle;    cpu_idle    = NULL;
                                delete [] cpu_sum;     cpu_sum     = NULL;
                            }
                            else {
                                started = true;             // ok
                            }
                            delete active;
                            active = NULL;
                        }
                        break;
                    case HELPER_CMD_STAT_STOP:              // stop CPU statistics and return data
                        if (!started) {
                            printf(HELPER "STOP error not started (ignore)\n");
                        }
                        else {                              // started and cpu_... buffers are allocated
                            printf(HELPER "STOP\n");
                            err = read_CPU_stat(cpu_sum, cpu_idle, cpu_percent, server->num_cpu);
                            printf(HELPER "STOP (2)\n");
                            if (err) {
                                printf(HELPER "STOP error (ignore)\n");
                                delete[] cpu_percent; cpu_percent = NULL;
                            }
                            else {
                                for (i = 0; i < server->num_cpu; ++i) printf("CPU %i: %3u.%03u%%\n", i, cpu_percent[i] / 1000, cpu_percent[i] % 1000);
                                //sleep_ms(50);
                            }
                        }
                        // even on error return result to avoid long timeout on error
                        active->data = cpu_percent;     // return result (NULL on error)
                        recv_queue->put(active);        // return result
                        cpu_percent = NULL;             // server has to delete
                        if (cpu_idle) { delete [] cpu_idle; cpu_idle = NULL; }
                        if (cpu_sum ) { delete [] cpu_sum;  cpu_sum  = NULL; }
                        active = NULL;                  // server has to delete
                        started = false;
                        break;
                    case HELPER_CMD_AUTO_SYNC:
                        if (server->dma24_dev == FILE_INVALID) { // error: device is not open. return NACK
                            active->data = (void*)ONDATA_NACK;
                            recv_queue->put(active);
                            active = NULL;
                        }
                        else { // ok: return ACK
                            active->data = (void*)ONDATA_ACK;
                            recv_queue->put(active);
                            active = NULL;
                            // find jumps in time 
                            int ph_start = 0, ph_end = PHASE_360;
                            uint8_t t0 = 0, t1 = 0;
                            err = find_jump(server->dma24_dev, INVALID_SOCKET, &server->act_phase, &ph_start, &ph_end, &t0, &t1, DATA_PTR, DATA_PLN, FIND_T0|FIND_POSITIVE|FIND_DELTA);
                            if(err) { recv_queue->put(new queue_entry(HELPER_CMD_AUTO_SYNC,NULL)); break; }
                            err = find_jump(server->dma24_dev, INVALID_SOCKET, &server->act_phase, &ph_start, &ph_end, &t0, &t1, DATA_PTR, DATA_PLN, FIND_T0|FIND_NEGATIVE|FIND_DELTA);
                            if(err) { recv_queue->put(new queue_entry(HELPER_CMD_AUTO_SYNC,NULL)); break; }
                            err = find_jump(server->dma24_dev, INVALID_SOCKET, &server->act_phase, &ph_start, &ph_end, &t0, &t1, DATA_PTR, DATA_PLN, FIND_T1|FIND_POSITIVE|FIND_DELTA);
                            if(err) { recv_queue->put(new queue_entry(HELPER_CMD_AUTO_SYNC,NULL)); break; }
                            err = find_jump(server->dma24_dev, INVALID_SOCKET, &server->act_phase, &ph_start, &ph_end, &t0, &t1, DATA_PTR, DATA_PLN, FIND_T1|FIND_NEGATIVE|FIND_DELTA);
                            if(err) { recv_queue->put(new queue_entry(HELPER_CMD_AUTO_SYNC,NULL)); break; }
                            else { // success: TODO: return delta time
                                recv_queue->put(new queue_entry(HELPER_CMD_AUTO_SYNC,(void*)0x1));
                            }
                        }
                        break;
                    case HELPER_CMD_EXIT:
                        printf(HELPER "EXIT\n");
                        server->helper_running = false;
                        break;
                    default:                            // THREAD_EXIT or unknown command
                        printf(HELPER "unknown command %d?\n", active->cmd);
                        server->helper_running = false;
                        break;
                }
            }
        }                                               // next loop until helper_running = false

        if (active) delete active;
        if (cpu_sum) delete [] cpu_sum;
        if (cpu_idle) delete [] cpu_idle;
        if (cpu_percent) delete [] cpu_percent;
    }

    printf(HELPER "exit with error code %d\n", err);
    //sleep_ms(10);
    pthread_exit((void*)(long long)err);
}

// start helper thread if num_cpu > 1
int FPGA_server::helper_start(void)
{
    int err = 0;
    if (num_cpu > 1) {                                  // start helper thread if more than one CPU available.
        send_queue = new queue();
        recv_queue = new queue();
        helper_running = true;                          // anticipate running flag, otherwise thread will terminate immediately
    #ifdef _WINDOWS
        unsigned long id = 0;
        helper_handle = CreateThread( NULL,             // security attributes
                    0,                                  // stack size,0=default
                    (LPTHREAD_START_ROUTINE)helper_thread,// thread starting address
                    (LPVOID)this,                       // parameters = pointer to FPGA_server
                    0,                                  // creation flags
                    &id                                 // thread ID (unused)
                    );
        if (thread == INVALID_THREAD) {                 // error
    #else
        err = pthread_create(&helper_handle,            // thread id (used as handle)
                    NULL,                               // flags
                    (void*(*)(void*))helper_thread,     // thread starting address
                    (void *)this                        // parameters = pointer to FPGA_server
                    );
        if (err != 0) {                                 // error
            helper_handle = INVALID_THREAD; 
    #endif
            err =-1;                                    // error
            delete send_queue; send_queue = NULL;
            delete recv_queue; recv_queue = NULL;
            helper_running = false;
        }
    }
    return err;
}

// shutdown of helper thread within given timeout in ms
// if time is 0 does not wait until thread is shutdown and does not delete queues! call again with timeout >0.
int FPGA_server::helper_shutdown(unsigned long timeout) {
    int err = 0;
    if (helper_running) {
        // start shutdown of helper thread
        send_queue->put(new queue_entry(HELPER_CMD_EXIT, NULL));
        // for nonzero timeout wait until thread is terminated (regardless of error)
        if (timeout != 0) {
            // reset running flag to increase chance of thread shutdown
            // we cannot do this with 0 timeout, otherwise in second call with timeout >0 would not do anything
            helper_running = false;
#ifdef _WINDOWS
            unsigned long result = WaitForSingleObject(helper_handle, timeout);
            if (result == WAIT_TIMEOUT) {
                // thread still running after timeout ms: kill thread.
                err = -1;
                TerminateThread(helper_handle, err);
            }
            else {
                // thread terminated: get exit code
                unsigned long exitCode = 0;
                GetExitCodeThread(helper_handle, &exitCode);
                err = (int)exitCode;
            }
#else
            void *exitCode;
            struct timespec ts;
            if (clock_gettime(CLOCK_REALTIME, &ts) == -1) err = -1;
            else {
                ts.tv_sec += timeout/1000;
                err = pthread_timedjoin_np(helper_handle, &exitCode, &ts);
                if(err == 0) {
                    // all ok, return exit code of thread
                    err = (long)exitCode;    // (long) avoids an error message
                }
                else if(err == ETIMEDOUT) {
                    // timeout
                    // TODO: on Windows version we kill thread at this point?
                    printf("thread_shutdown: timeout!\n");
                }
                else {
                    printf("thread_shutdown: error %d (0x%X)\n", err, err);
                    err = -2;
                }
            }
#endif
            // now we are sure thread is terminated: delete queues
            helper_handle = INVALID_THREAD; 
            delete send_queue; send_queue = NULL;
            delete recv_queue; recv_queue = NULL;
        }
    }
    return err;
}


////////////////////////////////////////////////////////////////////////////////////////////////////
// FPGA server class inherited from simple_server virtual basic class
////////////////////////////////////////////////////////////////////////////////////////////////////

// constructor and destructor
FPGA_server::FPGA_server(unsigned flags, const char *IP, const char *port, int num_cpu, uint32_t strb_delay, uint32_t sync_wait, uint32_t sync_phase) {
    this->flags = flags;
    this->name = (flags & FLAG_SERVER) ? str_server : str_client;
    this->server_IP = IP;
    this->server_port = port;
    this->num_cpu = num_cpu;
    this->strb_delay = strb_delay;
    this->sync_wait = sync_wait; 
    this->sync_phase = sync_phase;
    active_cmd = SERVER_NONE;
    b_set = b_act = b_part = 0;
    dio24_dev = FILE_INVALID;
    dma24_dev = FILE_INVALID;
    helper_handle = INVALID_THREAD;
    helper_running = false;
    helper_count = i_tot = 0;
    send_queue = recv_queue = NULL;
    act_phase = 0;
#ifdef SAVE_DATA_FILE
    save_data_length = 0;
    save_data = NULL;
#endif
#ifdef TIMING_TEST
    //memset(&status, 0, sizeof(struct FPGA_status));
    b_first = t_RT = t_upload = 0;
#endif
}

FPGA_server::~FPGA_server() {
    if(dio24_dev != FILE_INVALID) {
        FILE_CLOSE(dio24_dev);
        dio24_dev = FILE_INVALID;
    }
    if(dma24_dev != FILE_INVALID) {
        FILE_CLOSE(dma24_dev);
        dma24_dev = FILE_INVALID;
    }
#ifdef SAVE_DATA_FILE
    if (save_data && (save_data_length > 0)) {
        delete [] save_data;
        save_data = NULL;
        save_data_length = 0;
    }
#endif
}

// FPGA server specific server/client events
// notes: 
// - if flags & FLAG_SERVER is server, otherwise is client
// - all exectued by server/client thread
// - on error call shutdown() to quit server

// server startup
void FPGA_server::onStartup(void) {
    int err;
    if(flags & FLAG_SERVER) {
        // server: listen on given IP_address:port for max_clients
        // if this fails most likely server is already running!
        err = listen(server_IP, server_port, SERVER_MAX_CLIENTS);
        if (err) {
            printf("%sstartup error 0x%04X (server already running?)\n", name, err);
            shutdown(err);
        }
        else
        {
            // start helper thread if more than one CPU available
            err = helper_start();
            if (err) printf("%shelper thread startup failed with error %d\n", name, err);
            else {
                client_info *c = clients.get_first();
                while(c) {
                    if(c->is_server()) printf("%slistening at %s:%s\n", name, c->get_IP_address(), c->get_port_str());
                    c = clients.get_next(c);
                }
                // open & close board briefly. 
                // driver reset LEDs of board to indicate that board & server is ready
                dma24_dev = dma24_open(0);
                if(FILE_OPEN_ERROR(dma24_dev)) {
                    err = -10;
                    printf("%sSTART OPEN NACK: dma24_dev open failed!\n", name);
                }
                else {
                    dio24_dev = dio24_open(0);
                    if(FILE_OPEN_ERROR(dio24_dev)) {
                        printf("%sSTART OPEN NACK: dio24_dev open failed!\n", name);
                        err = -11;
                    }
                    else {
                        dio24_close(dio24_dev);
                        dio24_dev = FILE_INVALID;
                        printf("%sstartup ok.\n", name);
                        err = 0;
                    }
                    dma24_close(dma24_dev);
                    dma24_dev = FILE_INVALID;
                }
            }
        }
    }
    else {
        // client: connect to server
        err = connect(server_IP, server_port);
        if(err) printf("%scould not connect to %s:%s (error %d)\n", name, server_IP, server_port, err);
        else {
            client_info *c = clients.get_first();
            while (c) {
                if(c->is_client()) {
                    printf("%sconnection to %s:%s ok (port %hu)\n", name, 
                        c->get_IP_address(), 
                        c->get_port_str(), 
                        c->get_local_port(false));
                }
                c = clients.get_next(c);
            }
        }
    }
}

// client has connected to server. return true to accept client.
bool FPGA_server::onConnect(client_info *c) {
    if(c->is_local()) printf("%s%s:%s connected (local)\n", name, c->get_IP_address(), c->get_port_str());
    else printf("%s%s:%s connected\n", name, c->get_IP_address(), c->get_port_str());
    return true;    // accept all clients
}

// called every timeout ms. use for timing/cleanup/background tasks
void FPGA_server::onTimeout(void) {
    //if(!(flags & FLAG_SERVER)) printf("%stimeout\n", name);
}

// calculates a*b/c with 32bit registers
// see Ancient Egyptian multiplication
// most efficient if a < b
// return also r = remainder if needed
uint32_t muldiv(uint32_t a, uint32_t b, uint32_t c) {
    uint32_t q = 0, r = 0, qn = b / c, rn = b%c;
    while (a) {
        if (a & 1) {
            q+=qn;
            r+=rn;
            if(r >= c) {
                ++q;
                r-=c;
            }
        }
        a >>= 1;
        qn <<= 1;
        rn <<= 1;
        if (rn >= c) {
            ++qn;
            rn-=c;
        }
    }
    return q;
}

// return data rate in kByte/s = [0 .. 100000]
#define GET_RATE(time,bytes)    ((time)==0) ? 0 : muldiv(TIMING_TEST_PL_FREQ*1000,bytes,time)

// wait until helper finished writing.
// call only if helper_running == True
// returns ONDATA_ACK if all ok, otherwise error
// TODO: at the moment deletes buffers but it could give them back to server. 
//       be careful, if called from collect_write_data we might already return last buffer! 
inline int FPGA_server::wait_helper_write(void) {
    int err = ONDATA_ACK;
    class queue_entry *q_entry;
    //printf("write: helper %d/%d buffer remaining at helper\n", helper_count, i_tot); //sleep_ms(20);
    while(helper_count > 0) {                                           // buffers remaining
        //printf("write: helper wait %d remaining\n", helper_count); //sleep_ms(20);
        q_entry = recv_queue->get(1, 2*HELPER_TIMEOUT_MS);
        //printf("write: wait %p\n", q_entry); //sleep_ms(20);
        // check error: timeout or wrong data (should not happen!)
        if (q_entry == NULL) { err = -201; break; }                     // timeout
        else {
            if ((q_entry->data == NULL) || (q_entry->cmd != HELPER_CMD_WRITE)) { err = -202; break; }
            else {
                class write_info *wi = (class write_info*)q_entry->data;
                if (wi->written != wi->bytes) {                         // we do not allow partial writes!
                    delete [] wi->buffer;
                    wi->buffer = NULL;
                    delete wi;
                    err = -203;
                    break;
                }
                else {                                                  // ok
                    --helper_count;
                    delete [] wi->buffer;
                    wi->buffer = NULL;
                    delete wi;
                }
            }
            delete q_entry;
        }
    }
    //printf("write: helper %d/%d buffer remaining, result %d\n", helper_count, i_tot, err); //sleep_ms(20);
    return err;
}

// save received data in memory and write to DMA afterwards
inline int FPGA_server::collect_write_data(client_info *c, char *last_buffer, int last_bytes, int tot_bytes, int &result) {
    int err = 0;
    int bytes = this->b_act + tot_bytes;                                            // total received bytes
#ifdef TIMING_TEST
    if (this->i_tot == 0) {                                                         // first samples
        this->t_RT = dio24_timing_test(dma24_dev, DIO_TEST_RUN|DIO_TEST_UPDATE);    // save round-trip time
        this->b_first = tot_bytes;                                                  // save first number of samples
    }
#endif

    if ((tot_bytes <= (RECV_BUFLEN/2)) && (bytes < this->b_set)) {
        result = ONDATA_COLLECT_LAST;                                               // fill more data into buffer. too small buffers would reduce DMA writing speed!
    }
    else {
#ifdef UPLOAD_AND_WRITE                                                             // upload data and simultaneously write to DMA memory (default)
        // a) if helper is running submit samples to helper thread (2.1s/10M* samples)
        // b) otherwise write to DMA during uploading (2.6s/10M* samples. slightly faster than writing after uploading 2.7s/10M* samples.)
        // *these are older numbers. now uploading with helper is 2.3-2.4s. only small changes were done in the meantime.
        //  difference with waiting here or in SERVER_CMD_OUT_START is very small since only about 10 buffers remaining with helper.
        class recv_data *next = c->recv.get_first();
        this->b_act = bytes;
        if ( helper_running ) {
            class queue_entry *q_entry;
            // note: we return ONDATA_IN_USE_ALL and server will delete c->recv but not delete buffers used here.
            result = ONDATA_IN_USE_ALL;                                                // if no buffer is returned from helper: all buffers are used by helper
            while(next) {
                // get last result if available (do not wait)
                if (recv_queue->get(0, 0) != NULL) {                                // result available
                    q_entry = recv_queue->get(1, 0);
                    // check error: timeout or wrong data (should not happen!)
                    if (q_entry == NULL) { err = -101; break; }
                    else if ((q_entry->data == NULL) || (q_entry->cmd != HELPER_CMD_WRITE)) { err = -102; break; }
                    else {
                        class write_info *wi = (class write_info*)q_entry->data;
                        if (wi->written != wi->bytes) {                             // we do not allow partial writes!
                            delete [] wi->buffer;
                            wi->buffer = NULL;
                            delete wi;
                            err = -103;
                            break;
                        }
                        else {                                                      // ok: reuse old queue entry
                            /*if (c->recv.is_last(next)) {                            // last buffer: give old buffer back to server [removed since seems slightly slower?]
                                wi->bytes = next->get_bytes();
                                wi->buffer = next->exchange(wi->buffer, 0);         // exchange buffers, 0 used bytes.
                            }
                            else*/ 
                            {                                                       // not last buffer: for simplicity delete old buffer
                                delete [] wi->buffer;                               // delete old buffer. 
                                wi->bytes = next->get_bytes();
                                wi->buffer = next->get_data();                      // get data (server calls get_reset_data)
                            }
                            wi->written = 0;
                            wi->offset = i_tot;
                        }
                    }
                }
                else { // create new entry
                    ++helper_count;                                                 // count remaining buffers at helper
                    q_entry = new queue_entry(HELPER_CMD_WRITE, new write_info(dma24_dev, next->get_data(), next->get_bytes(), i_tot));
                }
                // submit new buffer to helper
                //printf("%i: entry %p buffer %p bytes %u ...\n", i_tot, q_entry, next->get_data(), next->get_bytes()); //sleep_ms(20);
                send_queue->put(q_entry);
                next = c->recv.get_next(next);                                      // next entry
                ++i_tot;                                                            // count total number of buffers
            }
        }
        else { // helper not running: write data immediately to DMA
            result = ONDATA_REUSE_ALL;                                              // server can reuse list of buffers
            int b_req, b_written;
            while(next) {                                                           // repeat until all data written
                b_req = next->get_bytes();
                b_written = write(dma24_dev, next->get_data(), b_req);
                if ( b_written != b_req ) {
                    if (b_written >= 0) {    // partial data: should not happen!?
                        printf("%sOUT_WRITE partial bytes %d < %d, rest %d\n", name, b_written, b_req, b_req - b_written);
                    }
                    else {    // error
                        if (errno == ENOMEM) printf("%sOUT_WRITE error ENOMEM %d bytes\n", name, b_req);
                        else printf("%sOUT_WRITE error %p, %d bytes %d/%d\n", name, next->get_data(), next->get_bytes(), b_written, errno);
                    }
                    err = -666;
                    break;
                }
                next = c->recv.get_next(next);                                      // next entry
                this->i_tot++;                                                      // count buffers
            }
        }

#else   // upload, save list to rcv_buf and write to DMA memory after uploading (for testing)
        static single_linked_list<recv_data> rcv_buf;                               // temporary single-linked list
        rcv_buf.merge(&c->recv);                                                    // note: c->recv is empty after merging!
        this->i_tot++;
        this->b_act = bytes;
        result = ONDATA_IN_USE_ALL;
#endif // UPLOAD_AND_WRITE

        if ( bytes >= this->b_set ) {                                               // all data received
#ifdef TIMING_TEST
            this->t_upload = dio24_timing_test(dma24_dev, DIO_TEST_RUN|DIO_TEST_UPDATE); // save uploading time
#else       // don't print during timing test!
            printf("%sOUT_WRITE %d samples (%d buffers) uploaded ok\n", name, this->b_act/DIO_BYTES_PER_SAMPLE, this->i_tot); //sleep_ms(10);
#endif

#ifdef UPLOAD_AND_WRITE  
#ifndef WAIT_HELPER_START                                                           // wait until helper finished writing (normally done in SERVER_CMD_OUT_START)
            if ( helper_running ) {
                int tmp = wait_helper_write();
                if (tmp != ONDATA_ACK) err = tmp;                                   // error
            }
#endif
#else
            // c) test write to DMA after uploading (2.7s)
            class recv_data *next = rcv_buf.get_first();
            int b_req, b_written;
            while(next) {                                                           // repeat until all data written
                b_req = next->get_bytes();
                b_written = write(dma24_dev, next->get_data(), b_req);
                if ( b_written != b_req ) {
                    if (b_written >= 0) {    // partial data: should not happen!?
                        printf("%sOUT_WRITE partial bytes %d < %d, rest %d\n", name, b_written, b_req, b_req - b_written);
                    }
                    else {    // error
                        if (errno == ENOMEM) printf("%sOUT_WRITE error ENOMEM %d bytes\n", name, b_req);
                        else printf("%sOUT_WRITE error %p, %d bytes %d/%d\n", name, next->get_data(), next->get_bytes(), b_written, errno);
                    }
                    err = -666;
                    break;
                }
                else { // all data written: count bytes and try writing next buffer
                    next = rcv_buf.get_next(next);
                }
            }
#endif // UPLOAD_AND_WRITE
            if (err >= 0) {
#ifdef TIMING_TEST
                static uint32_t res[TIMING_TEST_NUM_COLS];
                uint32_t t_tot = dio24_timing_test(dma24_dev, 0);                       // stop timer and save total time
                uint32_t rate_tot, rate_upload;                                         // data rate in kB/s
                unsigned *cpu_percent = NULL;
                cpu_percent = stop_cpu_stat(num_cpu);                                   // stop CPU statistics and get result
                this->t_old = get_ticks() - this->t_old;                                // save ticks
                if (i_tot == 1) { // only one buffer needed: uploading time = round-trip-time / 2
                    rate_upload = GET_RATE(t_RT/2,b_set);
                    rate_tot    = GET_RATE(t_tot - t_RT/2,b_set);
                }
                else { // several buffers needed: uploading time = upload time - round-trip-time / 2
                    rate_upload = GET_RATE(t_upload-(t_RT/2),b_set);
                    rate_tot    = GET_RATE(t_tot   -(t_RT/2),b_set);
                }
                uint32_t tu_RT     = t_RT    /TIMING_TEST_PL_FREQ;
                uint32_t tu_upload = t_upload/TIMING_TEST_PL_FREQ;
                uint32_t tu_tot    = t_tot   /TIMING_TEST_PL_FREQ;
                res[0] = b_set/DIO_BYTES_PER_SAMPLE;                                 // total number of samples
                res[1] = b_first;                                                    // first bytes
                res[2] = t_RT;                                                       // RT time in cycles
                res[3] = t_upload;                                                   // upload time in cycles
                res[4] = t_tot;                                                      // total time in cycles
                res[5] = t_old;                                                      // total ticks in us
                res[6] = cpu_percent ? cpu_percent[0] : 0;                           // first CPU percent * 1000 (if no error)
                res[7] = (cpu_percent && (num_cpu > 1)) ? cpu_percent[1] : 0;        // second CPU percent * 1000 (if exists and no error)
                printf("%sOUT_WRITE %d (%d) samples uploaded & written ok\n", name, this->b_set/DIO_BYTES_PER_SAMPLE, this->b_first/DIO_BYTES_PER_SAMPLE);
                if (helper_running) printf("%sOUT_WRITE %d total buffers, %d remaining at helper\n", name, i_tot, helper_count);
                else printf("%sOUT_WRITE %d total buffers (no helper)\n", name, i_tot);
                printf("%sOUT_WRITE times (us)   %u / %u / %u (%d)\n", name, tu_RT, tu_upload, tu_tot, t_old); // time in us + ticks
                printf("%sOUT_WRITE rates (MB/s) %u.%03u / %u.%03u\n", name, rate_upload/1000, rate_upload%1000, rate_tot/1000, rate_tot%1000);
                printf("%sOUT_WRITE CPU   (%%)    %u.%03u / %u.%03u\nappend result to %s\n\n", name, res[6]/1000, res[6]%1000, res[7]/1000, res[7]%1000, TIMING_TEST_FILE_NAME);
                save_CSV(TIMING_TEST_FILE_NAME, res, TIMING_TEST_NUM_COLS, TIMING_TEST_NUM_COLS);
                //sleep_ms(100);
                if (cpu_percent) delete[] cpu_percent;
#else           // don't print during timing test!
                if (!helper_running) {
                    printf("%sOUT_WRITE %d samples saved to DMA ok\n", name, this->b_act/DIO_BYTES_PER_SAMPLE); //sleep_ms(10);
                }
#endif // TIMING_TEST

#ifdef UPLOAD_AND_WRITE
                err = ONDATA_ACK;
#else
                // return all buffers to server. rcv_buf is empty afterwards.
                c->recv.merge(&rcv_buf);
                c->recv_add_bytes(this->b_act - tot_bytes); // update total number of received bytes. TODO: this should be done by server
                if (err > 0) err = ONDATA_ACK;
#endif
                this->active_cmd = SERVER_NONE;
                this->b_act = this->b_set = this->b_part = 0;
                this->i_tot = 0;
#ifdef TIMING_TEST
                this->b_first = 0; this->t_RT = 0; this->t_upload = 0;
#endif
            }
        }
    }

    if (err < 0) { 
        // note: the error case is very tricky since buffers might be in use by helper or not!
        //       therefore, we OR (|) ONDATA_CLOSE_CLIENT to ensure buffers are treated properly before client is closed.
        result |= ONDATA_CLOSE_CLIENT;
        printf("%sOUT_WRITE %d/%d samples error %d\n", name, this->b_act, this->b_set, err); //sleep_ms(10); 
    }
    return err;
}

// received tot_bytes > 0 bytes of data from client/server. return one of the ONDATA_ values.
// last_buffer and last_bytes are the last entries of the receive list - obtained with c->recv.get_last().
// if tot_bytes == last_bytes then the receive list contains only one entry, otherwise contains more entries.
// first entry of list can be obtained with first = c->recv.get_first(),
// successive entries can be obtained with c->recv.get_next(first).
int FPGA_server::onData(client_info *c, char *last_buffer, int last_bytes, int tot_bytes) {
    int result = ONDATA_REUSE_ALL; // in most cases allow to reuse all buffers
    int err = ONDATA_NONE; // internal error codes if >0 generates NACK, ACK, if <0 error and client will be disconnected.
    SERVER_CMD cmd;
    uint32_t t_start;
    //uint32_t ldata;
    //if (active_cmd != SERVER_CMD_OUT_WRITE) {
    //    if(c->is_local()) printf("%s%d bytes received from %s:%s (local)\n", name, tot_bytes, c->get_IP_address(), c->get_port_str());
    //    else printf("%s%d bytes received from %s:%s\n", name, tot_bytes, c->get_IP_address(), c->get_port_str());
    //}

    // check if more data is needed
    if(active_cmd == SERVER_NONE) { // not collecting data
        if(tot_bytes < sizeof(SERVER_CMD)) { // first byte received = command
            printf("%spartial command (single byte)\n", name);
            // find required number of bytes from list of commands
            // note: unlikely to happen unless client sends data byte by byte!
            // todo: for same first byte of server command this might find wrong command!
            cmd = (SERVER_CMD)*(unsigned char*)last_buffer;
            result = ONDATA_CLOSE_CLIENT; // error if command not found: closes client
            for(int i = 0; i < SERVER_CMD_NUM; ++i) {
                if(cmd == (server_cmd[i] & 0xff)) {
                    active_cmd = server_cmd[i];
                    result = ONDATA_COLLECT_LAST; // want more data
                    break;
                }
            }
        }
        else { // complete command including number of bytes received
            cmd = *(SERVER_CMD*)last_buffer;
            if(tot_bytes < GET_DATA_BYTES(cmd)) { // start collecting data
                printf("%spartial command (missing data)\n", name);
                active_cmd = cmd;
                result = ONDATA_COLLECT_LAST; // want more data
            }
            else { // act on command
                err = ONDATA_CMD;
                //printf("%scommand (%d bytes/%d) received\n", name, tot_bytes, GET_DATA_BYTES(cmd));
            }
        }
    }
    else if (active_cmd == SERVER_CMD_OUT_WRITE) { // receive samples
        // for testing print small data
        if (((this->b_set/DIO_BYTES_PER_SAMPLE) <= 100) && (this->b_act == 0)) {
            show_data((unsigned char*)last_buffer, last_bytes, true);
        }
        // give samples to helper or write directly
        err = collect_write_data(c, last_buffer, last_bytes, tot_bytes, result);
    }
    else { // collecting data
        if(tot_bytes < GET_DATA_BYTES(cmd)) { // continue collecting data
            printf("%spartial command (need more data)\n", name);
            result = ONDATA_COLLECT_LAST;
        }
        else {    // finished collecting data
            printf("%spartial command (completed)\n", name);
            cmd = active_cmd;
            active_cmd = SERVER_NONE;
            err = ONDATA_CMD;
        }
    }
    if(err == ONDATA_CMD) { // act on command
        err = 0;
        switch(cmd) {
            case SERVER_SHUTDOWN:
                if (c->is_local()) {
                    printf("%sshutdown command received\n", name);
                    if(flags & FLAG_SERVER) {
                        // server: notify all clients of shutdown: so they can disconnect.
                        c = clients.get_first();
                        while(c) {
                            if(c->is_client()) {
                                last_bytes = sizeof(SERVER_CMD);
                                err = SendData(c, &shtd, &last_bytes, DATA_STATIC);
                                if(err) {
                                    if (err == SERVER_SEND_PENDING) { // onSendFinished called when finished (will not delete data)
                                        printf("%sSHUTDOWN notify %s:%s postboned\n", name, c->get_IP_address(), c->get_port_str());
                                    }
                                    else {
                                        result = ONDATA_CLOSE_CLIENT; // error: sending of NACK will most likely also fail. just close client.
                                        printf("%sSHUTDOWN notify %s:%s error %d.\n", name, c->get_IP_address(), c->get_port_str(), err);
                                    }
                                }
                                else {
                                    printf("%sSHUTDOWN notify %s:%s ok\n", name, c->get_IP_address(), c->get_port_str());
                                }
                            };
                            c = clients.get_next(c);
                        }
                        // we shutdown only after all clients have disconnected
                        flags |= FLAG_SHUTDOWN;
                    }
                    else {
                        // disconnect from all clients and shutdown without error
                        shutdown(0x00);
                    }
                }
                else {  // we do not accept shutdown from non-local client: disconnect misbehaving client
                    printf("%sdisconnect %s:%s\n", name, c->get_IP_address(), c->get_port_str());
                    result = ONDATA_CLOSE_CLIENT;
                }
                break;
            case SERVER_RESET:
                if(dma24_dev == FILE_INVALID) {
                    printf("%sRESET NACK: device not open!\n", name);
                    err = ONDATA_NACK;
                }
                else {
                    if (dma24_reset(dma24_dev)) {
                        printf("%sRESET NACK\n", name);
                        err = ONDATA_NACK;
                    }
                    else {
                        printf("%sRESET ACK\n", name);
                        err = ONDATA_ACK;
                        act_phase = 0; // reset phase
                    }
                }
                break;
            case SERVER_CMD_OPEN:                       // connect (XP driver)
            case SERVER_CMD_OPEN_RESOURCE:              // connect (Win7/8 Visa driver, custom software)
                if((dma24_dev != FILE_INVALID) || (dio24_dev != FILE_INVALID)) {
                    printf("%sOPEN NACK: already open!\n", name);
                    err = ONDATA_NACK;
                }
                else {
                    dma24_dev = dma24_open(0);
                    if(FILE_OPEN_ERROR(dma24_dev)) {
                        err = ONDATA_NACK;
                        printf("%sOPEN NACK: dma24_dev open failed!\n", name);
                    }
                    else {
                        dio24_dev = dio24_open(0);
                        if(FILE_OPEN_ERROR(dio24_dev)) {
                            printf("%sOPEN NACK: dio24_dev open failed!\n", name);
                            err = ONDATA_NACK;
                            dma24_close(dma24_dev);
                            dma24_dev = FILE_INVALID;
                        }
                        else {
                            printf("%sOPEN ACK\n", name);
                            err = ONDATA_ACK;
                        }
                    }
                }
                break;
            case SERVER_CMD_CLOSE:                // disconnect
                printf("%sCLOSE\n", name);
                result = ONDATA_CLOSE_CLIENT;
                if((dma24_dev == FILE_INVALID) || (dio24_dev == FILE_INVALID)) err = ONDATA_NACK;
                else err = ONDATA_ACK;
                if (dma24_dev != FILE_INVALID) dma24_close(dma24_dev);
                if (dio24_dev != FILE_INVALID) dio24_close(dio24_dev);
                dma24_dev = dio24_dev = FILE_INVALID;
                break;
            case SERVER_GET_FPGA_STATUS_BITS:
                printf("%sGET_FPGA_STATUS_BITS\n", name);
                if(dma24_dev == FILE_INVALID) err = ONDATA_NACK;
                else {
                    struct client_data32 *cd = new struct client_data32;
                    if(cd == NULL) err = ONDATA_NACK;
                    else {
                        cd->cmd = SERVER_RSP_FPGA_STATUS_BITS;
                        cd->data = dio24_get_status_FPGA(dma24_dev);
                        last_bytes = sizeof(struct client_data32);
                        //printf("%ssend FPGA status bits 0x%X, %d bytes\n", name, cd->data, last_bytes);
                        err = SendData(c, (char*)cd, &last_bytes, DATA_CD32);
                        if (err == SERVER_SEND_PENDING) { // onSendFinished called when finished (will delete data)
                            printf("%sGET_FPGA_STATUS_BITS send %u bytes postboned (ok)\n", name, sizeof(struct client_data32));
                        }
                        else if (err) {
                            result = ONDATA_CLOSE_CLIENT; // error: sending of NACK will most likely also fail. just close client.
                            printf("%sGET_FPGA_STATUS_BITS send %u bytes error %d\n", name, sizeof(struct client_data32), err);
                            delete cd;
                        }
                        else {
                            delete cd;
                        }
                    }
                }
                break;
            case SERVER_GET_DMA_STATUS_BITS:
                printf("%sGET_DMA_STATUS_BITS\n", name);
                if(dma24_dev == FILE_INVALID) err = ONDATA_NACK;
                else {
                    struct client_data32 *cd = new struct client_data32;
                    if(cd == NULL) err = ONDATA_NACK;
                    else {
                        cd->cmd = SERVER_RSP_DMA_STATUS_BITS;
                        cd->data = dma24_get_config(dma24_dev);
                        last_bytes = sizeof(struct client_data32);
                        printf("%ssend DMA status bits 0x%X, %d bytes\n", name, cd->data, last_bytes);
                        err = SendData(c, (char*)cd, &last_bytes, DATA_CD32);
                        if (err == SERVER_SEND_PENDING) { // onSendFinished called when finished (will delete data)
                            printf("%sGET_DMA_STATUS_BITS send %u bytes postboned (ok)\n", name, sizeof(struct client_data32));
                        }
                        else if (err) {
                            result = ONDATA_CLOSE_CLIENT; // error: sending of NACK will most likely also fail. just close client.
                            printf("%sGET_DMA_STATUS_BITS send %u bytes error %d\n", name, sizeof(struct client_data32), err);
                            delete cd;
                        }
                        else {
                            delete cd;
                        }
                    }
                }
                break;
            case SERVER_GET_STATUS_IRQ:
                //printf("%sGET_STATUS_IRQ\n", name);
                if(dio24_dev == FILE_INVALID) err = ONDATA_NACK;
                else {
                    struct client_status *status = new struct client_status;
                    if(status == NULL) err = ONDATA_NACK;
                    else { 
                        status->cmd = SERVER_RSP_STATUS_IRQ;
                        status->status.status = 0;
                        status->status.board_time = 0; 
                        status->status.board_samples = 0;
#ifdef TIMING_TEST      // timing test status
                        err = dio24_get_status_run(dma24_dev, &status->status);
                        if(err) {
                            printf("%sGET_STATUS error %d\n", name, err);
                            err = ONDATA_NACK;
                            delete status;
                        }                        
                        else {
                            // set board time to maximum such that application stops
                            status->status.board_time = 0xffffffff;
#else
                        // wait until next FPGA irq by reading dio24_dev
                        // updates with guaranteed rate but blocks until irq or timeout
                        // under rare conditions this might timeout: in this case we poll actual status
                        // TODO: timeout seems to happen when FPGA is in error state? [maybe fixed?]
                        err = read(dio24_dev, &status->status, sizeof(struct FPGA_status_run));
                        if(err == sizeof(struct FPGA_status_run)) err = 0;
                        else { // timeout: try to read status directly
                            status->cmd = SERVER_RSP_STATUS;
                            // read FPGA status bits directly. this also forces to update status bits of driver.
                            status->status.status = dio24_get_status_FPGA(dma24_dev);
                            // read board samples and board time (and again status bits)
                            err = dio24_get_status_run(dma24_dev, &status->status);
                        }
                        if(err) {
                            if (status->cmd == SERVER_RSP_STATUS_IRQ) printf("%sGET_STATUS_IRQ error %d\n", name, err);
                            else                                      printf("%sGET_STATUS (IRQ) error %d\n", name, err);
                            err = ONDATA_NACK;
                            delete status;
                        }
                        else {
#endif
                            if (status->cmd == SERVER_RSP_STATUS) printf("%sGET_STATUS_IRQ timeout (ok)\n", name);
                            last_bytes = sizeof(struct client_status);
                            //printf("%ssend status %d bytes\n", name, last_bytes);
                            err = SendData(c, status, &last_bytes, DATA_STATUS);
                            if (err == SERVER_SEND_PENDING) { // onSendFinished called when finished (will delete status)
                                printf("%sGET_STATUS_IRQ send %u bytes postboned (ok)\n", name, sizeof(struct client_status));
                            }
                            else if (err) {
                                result = ONDATA_CLOSE_CLIENT; // error: sending of NACK will most likely also fail. just close client.
                                printf("%sGET_STATUS_IRQ send %u bytes error %d\n", name, sizeof(struct client_status), err);
                                delete status;
                            }
                            else {
                                uint32_t t_act = get_ticks();
                                if((t_act - t_old) > 1000000) {
                                    t_old = t_act;
                                    printf("%sGET_STATUS_IRQ 0x%8x %u us # %u\n", name, status->status.status, status->status.board_time, status->status.board_samples);
                                }
                                delete status;
                            }
                        }
                    }
                }
                break;
            case SERVER_GET_STATUS: 
                //printf("%sGET_STATUS\n", name);
                if(dio24_dev == FILE_INVALID) err = ONDATA_NACK;
                else {
                    struct client_status *status = new struct client_status;
                    if(status == NULL) err = ONDATA_NACK;
                    else { 
                        status->cmd = SERVER_RSP_STATUS;
                        // reading status register directly without waiting (might not update for a long time)
                        err = dio24_get_status_run(dma24_dev, &status->status);
                        if(err) {
                            printf("%sGET_STATUS error %d\n", name, err);
                            err = ONDATA_NACK;
                            delete status;
                        }
                        else {
                            last_bytes = sizeof(struct client_status);
                            //printf("%ssend status %d bytes\n", name, last_bytes);
                            err = SendData(c, status, &last_bytes, DATA_STATUS);
                            if (err == SERVER_SEND_PENDING) { // onSendFinished called when finished (will delete status)
                                printf("%sGET_STATUS send %u bytes postboned (ok)\n", name, sizeof(struct client_status));
                            }
                            else if (err) {
                                result = ONDATA_CLOSE_CLIENT; // error: sending of NACK will most likely also fail. just close client.
                                printf("%sGET_STATUS send %u bytes error %d\n", name, sizeof(struct client_status), err);
                                delete status;
                            }
                            else {
                                uint32_t t_act = get_ticks();
                                if((t_act - t_old) > 1000000) {
                                    t_old = t_act;
                                    printf("%sGET_STATUS 0x%8x %u us # %u\n", name, status->status.status, status->status.board_time, status->status.board_samples);
                                }
                                delete status;
                            }
                        }
                    }
                }
                break;
            case SERVER_GET_STATUS_FULL: 
                //printf("%sGET_STATUS_FULL\n", name);
                if(dio24_dev == FILE_INVALID) err = ONDATA_NACK;
                else {
                    struct client_status_full *status = new struct client_status_full;
                    if(status == NULL) err = ONDATA_NACK;
                    else { 
                        status->cmd = SERVER_RSP_STATUS_FULL;
                        err = dio24_get_status(dma24_dev, &status->status);
                        if(err) {
                            printf("%sGET_STATUS_FULL error %d\n", name, err);
                            err = ONDATA_NACK;
                            delete status;
                        }
                        else {
                            last_bytes = sizeof(struct client_status_full);
                            //printf("%ssend status %d bytes\n", name, last_bytes);
                            err = SendData(c, status, &last_bytes, DATA_STATUS_FULL);
                            if (err == SERVER_SEND_PENDING) { // onSendFinished called when finished (will delete status)
                                printf("%sGET_STATUS_FULL send %u bytes postboned (ok)\n", name, sizeof(struct client_status_full));
                            }
                            else if (err) {
                                result = ONDATA_CLOSE_CLIENT; // error: sending of NACK will most likely also fail. just close client.
                                printf("%sGET_STATUS_FULL send %u bytes error %d\n", name, sizeof(struct client_status_full), err);
                                delete status;
                            }
                            else {
                                uint32_t t_act = get_ticks();
                                if((t_act - t_old) > 1000000) {
                                    t_old = t_act;
                                    printf("%sGET_STATUS_FULL send %d/%d bytes ok\n", name, last_bytes, sizeof(struct client_status_full));
                                }
                                delete status;
                            }
                        }
                    }
                }
                break;
            case SERVER_GET_INFO:
                if(dma24_dev == FILE_INVALID) err = ONDATA_NACK;
                else {
                    struct client_data64 *cd64 = new struct client_data64;
                    if (cd64 == NULL) err = ONDATA_NACK;
                    else {
                        cd64->cmd = SERVER_GET_INFO;
                        err = dio24_get_info(dma24_dev, &cd64->data_0);
                        if (err) {
                            printf("%sGET_INFO error %d\n", name, err);
                            err = ONDATA_NACK;
                            delete cd64;
                        }
                        else {
                            last_bytes = sizeof(struct client_data64);
                            err = SendData(c, cd64, &last_bytes, DATA_CD64);
                            if (err == SERVER_SEND_PENDING) { // onSendFinished called when finished (will delete status)
                                printf("%sGET_INFO send %u bytes postboned (ok)\n", name, sizeof(struct client_data64));
                            }
                            else if (err) {
                                result = ONDATA_CLOSE_CLIENT; // error: sending of NACK will most likely also fail. just close client.
                                printf("%sGET_INFO send %u bytes error %d\n", name, sizeof(struct client_data64), err);
                                delete cd64;
                            }
                            else {
                                delete cd64;
                            }
                        }
                    }
                }
                break;
            case SERVER_CMD_OUT_CONFIG:
                t_start = get_ticks();
                printf("%sOUT_CONFIG\n", name);
                if(dma24_dev == FILE_INVALID) err = ONDATA_NACK;
                else {
                    // we re-use buffer for result
                    struct client_config *config = (struct client_config *)last_buffer;
                    // validate input
                    if((config->scan_Hz == 0) || ((config->config & DIO_CTRL_EXT_CLK) && (config->clock_Hz == 0))) err = ONDATA_NACK;
                    else {
                        // set clock divider
                        uint32_t value = (config->clock_Hz/config->scan_Hz);
                        err = dio24_set_div(dma24_dev, &value);
                        if(err) {
                            printf("%sset_div %u failed with error %d!\n", name, value, err);
                            err = ONDATA_NACK;
                        }
                        else {
                            printf("%sset_div %u ok\n", name, value);

                            // set strobe delay either from config or from server.config file
                            value = (config->strb_delay == STRB_DELAY_AUTO) ? strb_delay : config->strb_delay;
                            err = dio24_set_strb_delay(dma24_dev, &value);
                            if(err) {
                                printf("%sset strobe delay 0x%x failed with error %d!\n", name, value, err);
                                err = ONDATA_NACK;
                            }
                            else {
                                printf("%sset strobe delay 0x%x ok\n", name, value);

                                // set board waiting time either from config or from server.config file
                                value = (config->sync_wait == SYNC_DELAY_AUTO) ? sync_wait : config->sync_wait;
                                err = dio24_set_sync_delay(dma24_dev, value);
                                if(err != value) { 
                                    printf("%sset sync wait time %u failed with error %d!\n", name, value, err);
                                    err = ONDATA_NACK;
                                }
                                else {
                                    printf("%sset wait time %u ok\n", name, value);

                                    // set sync phase either from config or from server.config file
                                    // if phase is nonzero and there is no external clock this will fail!
                                    value = ((config->sync_phase == SYNC_PHASE_AUTO) ? sync_phase : config->sync_phase) & SYNC_PHASE_MASK_2;

                                    err = dio24_get_status_FPGA(dma24_dev);
                                    if ((value != 0) && ((err & DIO_STATUS_EXT_LOCKED) == 0)) {
                                        printf("%sset phase ext/det %u/%u no external clock! (status 0x%x)\n", name, 
                                            (unsigned)((value >> SYNC_PHASE_BITS) & SYNC_PHASE_MASK_1),
                                            (unsigned)(value & SYNC_PHASE_MASK_1),
                                            (unsigned)err);
                                        err = ONDATA_NACK;
                                    }
                                    else {
                                        dio24_set_sync_phase(dma24_dev, value);
                                        // wait until phase shift is done
                                        // TODO: wait for PS_ACTIVE bit and then until reset (see e.g. reset_FPGA).
                                        err = 0;
                                        while(dio24_get_status_FPGA(dma24_dev) & DIO_STATUS_PS_ACTIVE) { 
                                            if(++err >= SERVER_PHASE_RETRY) break; 
                                            sleep_ms(1); 
                                        }
                                        if (err >= SERVER_PHASE_RETRY) { 
                                            printf("%sset phase ext/det %u/%u error! waited %d loops (no clock?), status 0x%x\n", name, 
                                                (unsigned)((value >> SYNC_PHASE_BITS) & SYNC_PHASE_MASK_1),
                                                (unsigned)(value & SYNC_PHASE_MASK_1),
                                                err,
                                                dio24_get_status_FPGA(dma24_dev));
                                            err = ONDATA_NACK;
                                        }
                                        else {
                                            //printf("%snote: waited %i loop(s) for phase shift (ok)\n", name, err);
                                            printf("%sset phase ext/det %u/%u (%d loops) ok\n", name, 
                                                (unsigned)((value >> SYNC_PHASE_BITS) & SYNC_PHASE_MASK_1),
                                                (unsigned)(value & SYNC_PHASE_MASK_1),
                                                err);

                                            // set configuration bits, return new config bits
                                            // TODO: maybe set all 3 control registers with one command? or even all control registers here?
                                            //printf("%sOUT_CONFIG set config %x\n", name, config->config); //sleep_ms(100);
                                            err = dio24_set_config(dma24_dev, &config->config);
                                            printf("%sOUT_CONFIG actual config %x (%d)\n", name, config->config, err); //sleep_ms(20);
                                            if(!err) {
                                                // set input control register
                                                err = dio24_set_ctrl_in(dma24_dev, config->ctrl_in);
                                                if(err != config->ctrl_in) {
                                                    printf("%sset trg ctrl 0x%x != 0x%x\n", name, config->ctrl_in, err); //sleep_ms(10);
                                                    err = ONDATA_NACK;
                                                }
                                                else {
                                                    //printf("%sset in ctrl 0x%x ok\n", name, config->ctrl_in); //sleep_ms(10);
                                                    // set output control register
                                                    err = dio24_set_ctrl_out(dma24_dev, config->ctrl_out);
                                                    if(err != config->ctrl_out) {
                                                        printf("%sset out ctrl 0x%x != 0x%x\n", name, config->ctrl_out, err); //sleep_ms(10);
                                                        err = ONDATA_NACK;
                                                    }
                                                    else {
                                                        printf("%sset in/out ctrl 0x%x/0x%x (ok)\n", name, config->ctrl_in, config->ctrl_out); //sleep_ms(10);
                                                        // return actual values in last buffer
                                                        //printf("%ssend actual config\n", name);
                                                        //config->clock_Hz = clock_Hz;
                                                        //config->scan_Hz = clock_Hz / mult;
                                                        err = SendData(c, last_buffer, &last_bytes, DATA_CHAR_ARRAY);
                                                        if (err == SERVER_SEND_PENDING) { // onSendFinished called when finished (will delete buffer)
                                                            result = ONDATA_IN_USE_LAST;
                                                            printf("%sOUT_CONFIG send %u bytes postboned (ok, %uus)\n", name, sizeof(struct client_config), get_ticks()-t_start);
                                                        }
                                                        else if (err) {
                                                            result = ONDATA_CLOSE_CLIENT; // error: sending of NACK will most likely also fail. just close client.
                                                            printf("%sOUT_CONFIG send %u bytes error %d\n", name, sizeof(struct client_config), err);
                                                        }
                                                        else {
                                                            printf("%sOUT_CONFIG send %u bytes ok (%uus)\n", name, sizeof(struct client_config), get_ticks()-t_start);
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                break;
            case SERVER_CMD_OUT_WRITE: 
                // write data: after server sends ACK client is sending specified number of bytes
                // client might not wait for ACK, but start sending immediately.
                // after all data received server sends second ACK.
                // note: total number of bytes must be multiple of DIO_BYTES_PER_SAMPLE (but might arrive in packages of other size!)
                //printf("%sOUT_WRITE\n", name);
                if((dma24_dev == FILE_INVALID)||(dio24_dev == FILE_INVALID)) err = ONDATA_NACK;
                else {
                    struct client_data32 *cd = (struct client_data32 *)last_buffer;
                    if((cd->data % DIO_BYTES_PER_SAMPLE) != 0) {
                        printf("%sOUT_WRITE %u bytes is not multiple of %u! (error)\n", name, cd->data, DIO_BYTES_PER_SAMPLE); //sleep_ms(20);
                        err = ONDATA_NACK;
                    }
                    else if((cd->data / DIO_BYTES_PER_SAMPLE) > (DIO_MAX_SAMPLES*1024*1024)) {
                        printf("%sOUT_WRITE %u samples are larger than maximum allowed %dM! (error)\n", name, cd->data / DIO_BYTES_PER_SAMPLE, DIO_MAX_SAMPLES); //sleep_ms(20);
                        err = ONDATA_NACK;
                    }
                    else {
                        // set active command and number of remaining bytes
                        active_cmd = cmd;
                        this->b_set = cd->data;
                        this->b_act = this->b_part = 0;
                        this->i_tot = 0;
                        this->helper_count = 0;
                        t_old = get_ticks();                                                // actual ticks in us
#ifdef TIMING_TEST      // start timing test
                        b_first = t_RT = t_upload = 0;
                        //memset(&status, 0, sizeof(struct FPGA_status));
                        start_cpu_stat(num_cpu);                                            // start CPU statistics
                        dio24_timing_test(dma24_dev, DIO_TEST_RUN);                         // start timer
#else
                        printf("%sOUT_WRITE ACK %u bytes\n", name, cd->data);
#endif
                        err = ONDATA_ACK;
                    }
                }
                break;
            case SERVER_CMD_OUT_START:
                t_start = get_ticks();
                printf("%sOUT_START\n", name);
                if(dma24_dev == FILE_INVALID) {
                    printf("%sOUT_START error: not open!\n", name); //sleep_ms(10);
                    err = ONDATA_NACK;
                }
                else {
#ifdef WAIT_HELPER_START                                                                    // wait until helper finished writing data to reserved DMA memory
                    if ( helper_running ) {
                        err = wait_helper_write();
                        if (err != ONDATA_ACK) {
                            printf("%sOUT_START wait for helper error %d\n", name, err); //sleep_ms(100);
                            err = ONDATA_NACK;
                        }
                        else { 
                            printf("%sOUT_START wait for helper ok (%d)\n", name, err); //sleep_ms(100); 
                        }
                    }
                    else err = ONDATA_ACK;
                    if (err == ONDATA_ACK)
#endif
                    {
                        struct client_data32 *cd = (struct client_data32 *)last_buffer;
                        struct st_par stp;
                        stp.repetitions = cd->data;
                        stp.flags = START_FPGA_DELAYED;
                        err = dma24_start(dma24_dev, &stp);
                        if(err < 0) {
                            printf("%sOUT_START reps = %d error %d\n", name, cd->data, err); //sleep_ms(100);
                            err = ONDATA_NACK;
                        }
                        else {
                            printf("%sOUT_START reps = %d ok (%uus)\n", name, cd->data, get_ticks()-t_start); //sleep_ms(100);
                            err = ONDATA_ACK;
                            t_old = get_ticks();
                        }
                    }
                }
                break;
            case SERVER_CMD_OUT_STOP:
                printf("%sOUT_STOP\n", name);
                if(dma24_dev == FILE_INVALID) err = ONDATA_NACK;
                else {
                    err = dma24_stop(dma24_dev, 0);
                    if(err < 0) {
                        printf("%sOUT_STOP error %d!\n", name, err);
                        err = ONDATA_NACK;
                    }
                    else {
                        err = ONDATA_ACK;
                    }
                }
                break;
            case SERVER_TEST:
                printf("%sSERVER_TEST", name);
                //err = system("/usr/bin/FPGA-exit"); // requires <stdlib.h>
                //printf("%sSERVER_TEST (unmounting SD returned %d)", name, err);
                // we shutdown after all clients have disconnected
                //flags |= FLAG_SHUTDOWN;
                err = ONDATA_ACK;
                break;
            case SERVER_SET_SYNC_PHASE:
                if(dma24_dev == FILE_INVALID) err = ONDATA_NACK;
                else {
                    struct client_data32 *cd = (struct client_data32 *)last_buffer;
                    // set phase shift. this starts phase shift if not the same as before. returns difference to old phase.
                    dio24_set_sync_phase(dma24_dev, cd->data & SYNC_PHASE_MASK_2);
                    // wait until phase shift is done
                    err = 0;
                    while(dio24_get_status_FPGA(dma24_dev) & DIO_STATUS_PS_ACTIVE) { 
                        if(++err >= SERVER_PHASE_RETRY) break; 
                        sleep_ms(1); 
                    }
                    if (err >= SERVER_PHASE_RETRY) { 
                        printf("%serror: waited %d loops for phase shift (error)\n", name, err); 
                        err = ONDATA_NACK; 
                    }
                    else {
                        //printf("%snote: waited %i loop(s) for phase shift (ok)\n", name, err);
                        printf("%sset phase ext/det %u/%u (%d loops) ok\n", name, 
                            (unsigned)((cd->data >> SYNC_PHASE_BITS) & SYNC_PHASE_MASK_1),
                            (unsigned)(cd->data & SYNC_PHASE_MASK_1),
                            err);
                        err = ONDATA_ACK;
                    }
                }
                break;
            case SERVER_AUTO_SYNC_START:
            case SERVER_AUTO_SYNC_STOP:
                //printf("%sAUTO_SYNC\n", name);
                if(dma24_dev == FILE_INVALID) err = ONDATA_NACK;
                else {
                    uint32_t t_sync;
                    struct client_data64 *cd64 = (struct client_data64 *)last_buffer;
                    //printf("%sstatus 0x%x\n", name, dio24_get_status_FPGA(dma24_dev));       
                    printf("%sset sync delay %u phase ext/det/FET %u/%u/%u\n", name, 
                        (unsigned)(cd64->data_0 & SYNC_DELAY_MASK), 
                        (unsigned)((cd64->data_1 >> SYNC_PHASE_BITS) & SYNC_PHASE_MASK_1),
                        (unsigned)(cd64->data_1 & SYNC_PHASE_MASK_1),
                        (unsigned)(cd64->data_0>>31)
                    );
                    //sleep_ms(10);
                    // set trigger delay & phase shift
                    err = dio24_set_sync_delay(dma24_dev, cd64->data_0 & SYNC_DELAY_MASK);
                    if(err != (cd64->data_0 & SYNC_DELAY_MASK)) err = ONDATA_NACK;
                    else {
                        // set phase shift. this starts phase shift if not the same as before. returns difference to old phase.
                        dio24_set_sync_phase(dma24_dev, cd64->data_1 & SYNC_PHASE_MASK_2);
                        // check absolute phase
                        //err = dio24_get_sync_phase(dma24_dev);
                        //if( ((err >> SYNC_PHASE_BITS)  != (((cd64->data_1 >> SYNC_PHASE_BITS) & SYNC_PHASE_MASK_1) % PHASE_360)) ||
                        //    ((err & SYNC_PHASE_MASK_1) != ((cd64->data_1 & SYNC_PHASE_MASK_1) % PHASE_360))                         ) err = ONDATA_NACK;
                        //else 
                        {
                            err = 0;
                            // wait until phase shift is done
                            while(dio24_get_status_FPGA(dma24_dev) & DIO_STATUS_PS_ACTIVE) { 
                                if(++err >=SERVER_PHASE_RETRY) break; 
                                sleep_ms(1); 
                            }
                            if (err == 1) { 
                                printf("%snote: waited 1 loop for phase shift (ok)\n", name); 
                                //sleep_ms(10); 
                            }
                            if (err > 1) { 
                                printf("%serror: waited %d loops for phase shift\n", name, err); 
                                err = ONDATA_NACK; 
                            }
                            else {
                                //printf("%sstatus 0x%x\n", name, dio24_get_status_FPGA(dma24_dev)); //sleep_ms(10);
                                if (cmd == SERVER_AUTO_SYNC_START) {
                                    // configure secondary FPGA which sets DIO_CTRL_AUTO_SYNC_EN bit which measures one pulse without generating it
                                    t_sync = AUTO_SYNC_SEC_CONF;
                                    err = dio24_set_config(dma24_dev, &t_sync);
                                    if (err) err = ONDATA_NACK;
                                    else {
                                        //printf("%sstatus 0x%x\n", name, dio24_get_status_FPGA(dma24_dev)); //sleep_ms(10);
#ifdef SAVE_DATA_FILE
                                        if (save_data == NULL) {
                                            save_data_length = 0;
                                            save_data = new uint32_t[SAVE_DATA_ROWS*SAVE_DATA_COLS];
                                        }
                                        if (save_data_length <= ((SAVE_DATA_ROWS-1)*SAVE_DATA_COLS)) { // save detector phase
                                            save_data[save_data_length++] = (cd64->data_1 & SYNC_PHASE_MASK_1);
                                        }
#endif
                                        act_phase = (int)(cd64->data_1 & SYNC_PHASE_MASK_1);
                                        printf("%sAUTO-SYNC (START) phase %u status 0x%08x ACK\n", name, act_phase, dio24_get_status_FPGA(dma24_dev)); //sleep_ms(10);
                                        err = ONDATA_ACK; // return ACK
                                    }
                                }
                                else { // SERVER_AUTO_SYNC_STOP
                                    // get sync_time
                                    t_sync = dio24_get_sync_time(dma24_dev);
#ifdef SAVE_DATA_FILE               // save data if not NULL
                                    if (save_data && (save_data_length <= ((SAVE_DATA_ROWS-1)*SAVE_DATA_COLS+1))) {
                                        save_data[save_data_length++] = t_sync & 0xff;
                                        save_data[save_data_length++] = (t_sync >> 8) & 0xff;
                                        save_data[save_data_length++] = (t_sync >> 16) & 0xff;
                                        save_data[save_data_length++] = (t_sync >> 24) & 0xff;
                                        err = save_CSV(SAVE_DATA_FILE, save_data, save_data_length, SAVE_DATA_COLS);
                                        save_data_length = 0;
                                    }
#endif
                                    printf("%sAUTO-SYNC (STOP) phase %u status 0x%08x time 0x%08x ACK\n", name, act_phase, dio24_get_status_FPGA(dma24_dev), dio24_get_sync_time(dma24_dev));
                                    //sleep_ms(10);
                                    act_phase = (int)(cd64->data_1 & SYNC_PHASE_MASK_1);
                                    // send back sync_time
                                    cd64->data_0 = t_sync;
                                    cd64->data_1 = 0;
                                    err = SendData(c, last_buffer, &last_bytes, DATA_CHAR_ARRAY);
                                    if (err) {
                                        if (err == SERVER_SEND_PENDING) { // onSendFinished called when finished (will delete buffer)
                                            result = ONDATA_IN_USE_LAST;
                                            printf("%sAS_STOP send %u bytes postboned (ok)\n", name, sizeof(struct client_data64));
                                        }
                                        else {
                                            result = ONDATA_CLOSE_CLIENT; // error: sending of NACK will most likely also fail. just close client.
                                            printf("%sAS_STOP send %u bytes error %d\n", name, sizeof(struct client_data64), err);
                                        }
                                    }
                                    else {
                                        err = ONDATA_NONE; // no ACK is needed. we already returned same command.
                                    }
                                }
                            }
                        }
                    }
                }                
                break;
            case SERVER_CMD_IN_START:
            case SERVER_CMD_IN_STATUS:
            case SERVER_CMD_IN_READ:
            case SERVER_CMD_IN_STOP:
            case SERVER_CMD_OUT_FORCE:
            case SERVER_CMD_OUT_GET_INPUT:
                // not implemented: respond NACK
                printf("%sNOT YET IMPLEMENTED!\n", name);
                err = ONDATA_NACK;
                break;
            // these commands are implemented only in DLL and should not be sent to server: close client after NACK
            case SERVER_CMD_LOAD:
            case SERVER_CMD_OUT_STATUS:
            case SERVER_CMD_GET_ATTRIBUTE:
            case SERVER_CMD_SET_ATTRIBUTE:
                printf("%sNOT IMPLEMENTED!\n", name);
                err = ONDATA_NACK;
                result = ONDATA_CLOSE_CLIENT;
                break;
            default:
                // unknown command: close client without reply
                printf("%sUNKNOWN (0x%x)!\n", name, cmd);
                result = ONDATA_CLOSE_CLIENT;
        }
    }
    if(err == ONDATA_ACK) { // send ACK
        //printf("%sACK\n", name);
        last_bytes = sizeof(SERVER_CMD);
        err = SendData(c, &ack, &last_bytes, ABORT_PARTIAL_DATA);
        if (err) {
            result |= ONDATA_CLOSE_CLIENT; // error: close client but keep other return flags
            printf("%sACK send %u bytes error %d\n", name, sizeof(SERVER_CMD), err);
        }
    }
    else if(err == ONDATA_NACK) { 
        // error = send NACK
        printf("%sNACK (0x%d)\n", name, err);
        last_bytes = sizeof(SERVER_CMD);
        SendData(c, &nack, &last_bytes, ABORT_PARTIAL_DATA);
        if (err) {
            result |= ONDATA_CLOSE_CLIENT; // error: close client but keep other return flags.
            printf("%sNACK send %u bytes error %d\n", name, sizeof(SERVER_CMD), err);
        }
        // TODO: at the moment we always disconnect client after sending NACK. maybe is not needed?
        // note: the error case is very tricky since buffers might be in use by helper or not!
        //       therefore, we OR (|) ONDATA_CLOSE_CLIENT to ensure buffers are treated properly before client is closed.
        result |= ONDATA_CLOSE_CLIENT;
    }
    // on serious error always close client and dma24/dio24_dev
    if ((err < 0) || (result & ONDATA_CLOSE_CLIENT)) {
        printf("%sclose dio24/dma24_dev (OnData CLOSE_CLIENT 0x%x)\n", name, err); //sleep_ms(10);
        if (this->dio24_dev != FILE_INVALID) dio24_close(this->dio24_dev);
        if (this->dma24_dev != FILE_INVALID) dma24_close(this->dma24_dev);
        this->dio24_dev = this->dma24_dev = FILE_INVALID;
        // note: the error case is very tricky since buffers might be in use by helper or not!
        //       therefore, we OR (|) ONDATA_CLOSE_CLIENT to ensure buffers are treated properly before client is closed.
        result |= ONDATA_CLOSE_CLIENT;
    }
    //printf("%sOnData return 0x%x\n", name, result); //sleep_ms(10);
    return result;
}

// sending of large data finished
// data_info is user-provided data info given to SendData. use this to cast data before calling delete!
void FPGA_server::onSendFinished(client_info *c, void *data, int num, int sent, unsigned data_info, int error) {
    if (error) printf("%ssending of %d/%d bytes finished with error 0x%x\n", name, sent, num, error);
    else       printf("%ssending of %d/%d bytes finished ok\n", name, sent, num);
    if      ((data_info == DATA_CD32)        && (num == sizeof(struct client_data32)))      delete((struct client_data32*)data);
    else if ((data_info == DATA_CD64)        && (num == sizeof(struct client_data64)))      delete((struct client_data64*)data);
    else if ((data_info == DATA_STATUS)      && (num == sizeof(struct client_status)))      delete((struct client_status*)data);
    else if ((data_info == DATA_STATUS_FULL) && (num == sizeof(struct client_status_full))) delete((struct client_status_full*)data);
    else if (data_info == DATA_CHAR_ARRAY) delete [] ((char*)data);
}

// client/server disconnected from server/client
void FPGA_server::onDisconnect(client_info *c) {
    if (c->is_local()) {
        printf("%s%s:%s disconnected (local)\n", name, c->get_IP_address(), c->get_port_str());
    }
    else {
        printf("%s %s:%s disconnected\n", name, c->get_IP_address(), c->get_port_str());
    }
    if(flags & FLAG_SHUTDOWN) {
        // count number of remaining clients
        int num = 0;
        client_info *ci = clients.get_first();
        while(ci) {
            if((ci != c) && ci->is_client()) ++num;
            ci = clients.get_next(ci);
        }
        if(num == 0) {
            printf("%sshutdown after last connection disconnected\n", name);
            shutdown(0x00);
        } 
        else {
            printf("%swaiting for last connection to disconnect (%d remaining)\n", name, num);
        }
    }
    // close dma24_dev
    // TODO: maybe we should distinguish between master and client disconnecting?
    if (this->dio24_dev != FILE_INVALID) dio24_close(this->dio24_dev);
    if (this->dma24_dev != FILE_INVALID) dma24_close(this->dma24_dev);
    this->dio24_dev = this->dma24_dev = FILE_INVALID;
    printf("%sclosed dio24/dma24_dev (onDisconnect)\n", name);
}

// client/server shutdown with error code (0=ok)
void FPGA_server::onShutdown(int error) {
    if (error) printf("%sshutdown with error 0x%04X\n", name, error);
    else printf("%sshutdown ok!\n", name);

    // TODO: delete all application specific resources here!

    // shutdown helper thread if is running
    helper_shutdown(2*HELPER_TIMEOUT_MS);

    // delete data
    if (save_data && (save_data_length > 0)) {
        delete [] save_data;
        save_data = NULL;
        save_data_length = 0;
    }

    // close dma24_dev
    if (this->dio24_dev != FILE_INVALID) dio24_close(this->dio24_dev);
    if (this->dma24_dev != FILE_INVALID) dma24_close(this->dma24_dev);
    this->dio24_dev = this->dma24_dev = FILE_INVALID;
    printf("%sclose dio24/dma24_dev (onShutdown)\n", name);
}

////////////////////////////////////////////////////////////////////////////////////////////////////
// function implementation
////////////////////////////////////////////////////////////////////////////////////////////////////

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

int test0(char *name, FPGA_server *server, client_info *cli_server, struct client_config *c_config) {
    static struct client_data32 c_data;
    int err = 0, num, expect_num;
    char *data;
    SERVER_CMD cmd, expect_cmd;

    printf("%stest 0: single experimental sequence ...\n", name);

    int i=0;
    while(true) {
        switch (i) {
            case 0:    // open dma24_dev
                cmd = SERVER_CMD_OPEN; 
                num = sizeof(SERVER_CMD);
                data = (char*) &cmd;
                expect_cmd = SERVER_ACK;
                expect_num = sizeof(SERVER_CMD);
                printf("%stest command 'OPEN' (0x%x)\n", name, cmd);
                break;
            case 1: // reset dma24_dev
                cmd = SERVER_RESET;
                num = sizeof(SERVER_CMD);
                data = (char*) &cmd;
                expect_cmd = SERVER_ACK;
                expect_num = sizeof(SERVER_CMD);
                printf("%stest command 'RESET' (0x%x)\n", name, cmd);
                break;
            case 2: // config dma24_dev
                cmd = SERVER_CMD_OUT_CONFIG;
                num = sizeof(struct client_config);
                data = (char*) c_config;
                expect_cmd = SERVER_NONE;
                expect_num = sizeof(client_config);
                printf("%stest command 'OUT_CONFIG' (0x%x)\n", name, cmd);
                break;
            case 3: // get status bits
                cmd = SERVER_GET_FPGA_STATUS_BITS;
                num = sizeof(SERVER_CMD);
                data = (char*) &cmd;
                expect_cmd = SERVER_RSP_FPGA_STATUS_BITS;
                expect_num = sizeof(client_data32);
                printf("%stest command 'GET_FPGA_STATUS_BITS' (0x%x)\n", name, cmd);
                break;
            case 4:    // start writing of data, expect ACK if ready
                cmd = SERVER_CMD_OUT_WRITE;
                num = sizeof(struct client_data32);
                c_data.cmd = cmd;
                c_data.data = TEST_DATA_NUM_SAMPLES*DIO_BYTES_PER_SAMPLE;
                data =(char*) &c_data;
                expect_cmd = SERVER_ACK;
                expect_num = sizeof(SERVER_CMD);
                printf("%stest command 'OUT_WRITE' (0x%x) ...\n", name, cmd);
                break;
            case 5: // write odd number of data. expect nothing
                //cmd = SERVER_CMD_OUT_WRITE; // same command active
                num = TEST_DATA_NUM_SAMPLES*DIO_BYTES_PER_SAMPLE/2-1;
                data = (char*)test_data;
                expect_cmd = SERVER_NONE;
                expect_num = 0;
                printf("%stest command 'OUT_WRITE' (0x%x) send first %d bytes \n", name, cmd, num);
                break;
            case 6: // write second data. expect ACK after all data received.
                //cmd = SERVER_CMD_OUT_WRITE; // same command active
                num = TEST_DATA_NUM_SAMPLES*DIO_BYTES_PER_SAMPLE/2+1;
                data = ((char*)test_data) + TEST_DATA_NUM_SAMPLES*DIO_BYTES_PER_SAMPLE/2-1;
                expect_cmd = SERVER_ACK;
                expect_num = sizeof(SERVER_CMD);
                printf("%stest command 'OUT_WRITE' (0x%x) send last %d bytes \n", name, cmd, num);
                break;
            case 7: // start run
                cmd = SERVER_CMD_OUT_START;
                num = sizeof(struct client_data32);
                c_data.cmd = cmd;
                c_data.data = c_config->reps;
                data = (char*) &c_data;
                expect_cmd = SERVER_ACK;
                expect_num = sizeof(SERVER_CMD);
                printf("%stest command 'OUT_START' (0x%x)\n", name, cmd);
                break;
            case 8:    // get status bits in a loop until run finished (or error)
                cmd = SERVER_GET_FPGA_STATUS_BITS;
                num = sizeof(SERVER_CMD);
                data =(char*) &cmd;
                expect_cmd = SERVER_RSP_FPGA_STATUS_BITS;
                expect_num = sizeof(client_data32);
                printf("%stest command 'GET_FPGA_STATUS_BITS' (0x%x)\n", name, cmd);
                break;
            case 9:    // stop run (should be already stopped)
                cmd = SERVER_CMD_OUT_STOP; 
                num = sizeof(SERVER_CMD);
                data =(char*) &cmd;
                expect_cmd = SERVER_ACK;
                expect_num = sizeof(SERVER_CMD);
                printf("%stest command 'OUT_STOP' (0x%x)\n", name, cmd);
                break;
            case 10: // get full status
                cmd = SERVER_GET_STATUS;
                num = sizeof(SERVER_CMD);
                data = (char*) &cmd;
                expect_cmd = SERVER_RSP_STATUS;
                expect_num = sizeof(client_status);
                printf("%stest command 'GET_STATUS' (0x%x)\n", name, cmd);
                break;
            default: // close dma24_dev
                cmd = SERVER_CMD_CLOSE;  
                num = sizeof(SERVER_CMD);
                data =(char*) &cmd;
                expect_cmd = SERVER_ACK;
                expect_num = sizeof(SERVER_CMD);
                printf("%stest command 'OUT_CLOSE' (0x%x)\n", name, cmd);
                break;
        }
        // send command with command specific data and read responds of resp_num bytes
        // returned data of num bytes is saved in data and must be deleted (except when NULL)
        err = send_cmd(name, server, cli_server, data, num, expect_num);
        if((!err) && ((data == NULL) || (num != expect_num))) err = -10; // unexpected bytes
        if((!err) && ((expect_cmd != SERVER_NONE) && ((*(SERVER_CMD*)data) != expect_cmd))) err = -11; // unexpected command
        if(err) { // test failed: close and exit
            if(data == NULL) {
                printf("%stest command (0x%x) failed! error code %d\n\treceived/expected command NULL/0x%x\n\treceived/expected bytes %d/%d\n", 
                    name, cmd, err, expect_cmd, num, expect_num);
            }
            else {
                printf("%stest command (0x%x) failed! error code %d\n\treceived/expected command 0x%x/0x%x\n\treceived/expected bytes %d/%d\n", 
                    name, cmd, err, *(SERVER_CMD*)data, expect_cmd, num, expect_num);
                delete[] data;
                data = NULL;
            }
            if(cmd == SERVER_CMD_CLOSE) break;
            else i = 999; // default = SERVER_CMD_CLOSE
        }
        else { // test ok
            printf("%stest command (0x%x) ok\n", name, cmd);
            if(cmd == SERVER_GET_FPGA_STATUS_BITS) { // wait until not running anymore
                struct client_data32 *cd = (client_data32 *)data;
                //printf("%scmd = 0x%x, status = 0x%x\n", name, cd->cmd, cd->data); 
                if ( cd->data & DIO_STATUS_ERROR ) {
                    printf("%sstatus = 0x%x error! (stop)\n", name, cd->data); 
                    i = 10; // get status & close
                }
                else if ( cd->data & DIO_STATUS_RUN ) {
                    printf("%sstatus = 0x%x running ...\n", name, cd->data);
                    //sleep_ms(1000);
                    //++i; // stop
                }
                else {
                    printf("%sstatus = 0x%x stopped (ok)\n", name, cd->data);
                    ++i; // next test
                }
                delete[] data;
                data = NULL;
            }
            else {
                delete[] data;
                data = NULL;
                if(cmd == SERVER_CMD_CLOSE) { // last test
                    break;
                }
                else { // next test
                    ++i;
                }
            }
        }
    }
    if (err) printf("%s*** test 0 error! (%d) ***\n", name, err);
    else printf("%s*** test 0 ok! ***\n", name);
    return err;
}

// test data for device addresses 1-3, 2xdigital out 1x analog out
// data is in little-endian byte order (LSB first)!
// data sample = 32bit time (in mu, max. >1h), 16bit data, 7bit address, 1bit strobe, 8bit 0s
uint32_t test_data[TEST_DATA_NUM_SAMPLES*2] = {
      00000, 0x00010001,
      20000, 0x00020001,
      40000, 0x00030000,
      60000, 0x00010002,
      80000, 0x00020002,
     100000, 0x00030000 + 3277,// 1V
     120000, 0x00010004,
     140000, 0x00020004,
     160000, 0x00030000 + 3277*2,// 2V
     180000, 0x00010008,
     200000, 0x00020008,
     220000, 0x00030000 + 3277*3,// 3V
     240000, 0x00010010,
     260000, 0x00020010,
     280000, 0x00030000 + 3277*4,// 4V
     300000, 0x00010020,
     320000, 0x00020020,
     340000, 0x00030000 + 3277*5,// 5V
     360000, 0x00010040,
     380000, 0x00020040,
     400000, 0x00030000 + 3277*6,// 6V
     420000, 0x00010080,
     440000, 0x00020080,
     460000, 0x00030000 + 3277*7,// 7V
     480000, 0x00010100,
     500000, 0x00020100,
     520000, 0x00030000 + 3277*8,// 8V
     540000, 0x00010200,
     560000, 0x00020200,
     580000, 0x00030000 + 3277*9,// 9V
     600000, 0x00010200,
     620000, 0x00020200,
     640000, 0x00030000 + 32767,// +10V
     660000, 0x00010200,
     680000, 0x00020200,
     700000, 0x00030000 + 32768,// -10V
     720000, 0x00010400,
     740000, 0x00020400,
     760000, 0x00030000 + 3277*11,// -9V
     780000, 0x00010800,
     800000, 0x00020800,
     820000, 0x00030000 + 3277*12,// -8V
     840000, 0x00011000,
     860000, 0x00021000,
     880000, 0x00030000 + 3277*13,// -7V
     900000, 0x00012000,
     920000, 0x00022000,
     940000, 0x00030000 + 3277*14,// -6V
     960000, 0x00014000,
     980000, 0x00024000,
     1000000, 0x00030000 + 3277*15,// -5V
     1020000, 0x00018000,
     1040000, 0x00028000,
     1060000, 0x00030000 + 3277*16,// -4V
     1080000, 0x0001ffff,
     1100000, 0x0002ffff,
     1120000, 0x00030000 + 3277*17,// -3V
     1140000, 0x0001ff00,
     1160000, 0x000200ff,
     1180000, 0x00030000 + 3277*18,// -2V
     1200000, 0x000100ff,
     1220000, 0x0002ff00,
     1240000, 0x00030000 + 3277*19,// -1V
     1260000, 0x0001ffff,
     1280000, 0x0002ffff,
     1300000, 0x00030000,// 0V
     1320000, 0x00010000,
     1340000, 0x00020000,
     1360000, 0x00030000 // 0V
};


////////////////////////////////////////////////////////////////////////////////////////////////////
// main application
////////////////////////////////////////////////////////////////////////////////////////////////////

// show data
// if is_data is displayed as data_time, otherwise as chars
void show_data(unsigned char *data, int num, bool is_time_data) {
    if(is_time_data) {
        int samples = num / DIO_BYTES_PER_SAMPLE;
        uint32_t *p = (uint32_t*)data;
        int row;
        if(num % DIO_BYTES_PER_SAMPLE) printf("show_data warning: %u bytes in excess not shown!\n", num % DIO_BYTES_PER_SAMPLE);
#if DIO_BYTES_PER_SAMPLE == 12
        for (row = 0; row < samples; ++row, p+=3) {
            printf("%6d: 0x %08X %08X %08X = %10d us\n", row, *p, *(p+1), *(p+2), *p);
        }
#elif DIO_BYTES_PER_SAMPLE == 8
        for (row = 0; row < samples; ++row, p+=2) {
            printf("%6d: 0x %08X %08X = %10d us\n", row, *p, *(p+1), *p);
        }
#endif
        printf("%d samples (%d bytes)\n", samples, num);
    }
    else {
        int row, col, i = 0;
        for (row = 0; i < num; ++row) {
            printf("%3d: ", i);
            for (col = 0; (col < DIO_BYTES_PER_SAMPLE) && (i < num); ++col, ++i, ++data) {
                printf("%02x ", *data);
            }
            printf("\n");
        }
    }
}

// respond ok
//num = data_status_size;
//int err = SendData(c, data_status, &num);
//if (err) Shutdown(err);

// send command with command specific data and read responds of resp_num bytes
// returned data of num bytes is saved in data and must be deleted (except when NULL)
int send_cmd(char *name, FPGA_server *server, client_info *cli_server, char *&data, int &num, int resp_num) {
    int err, ret;
    // allocate responds data
    char *resp = new char[resp_num+1];
    if(resp == NULL) {
        printf("%serror allocation!\n", name);
        data = NULL;
        num = 0;
        err = -2;
    }
    else {
        // send command and data
        err = server->thread_send(cli_server, data, num, 1000);
        // return allocated data, num gets number of received bytes
        data = resp;
        num = 0;
        if(err) printf("%ssend error %d!\n", name, err);
        else {                
            // read responds from server until resp_num bytes or timeout (5s)
            do {
                err = server->thread_wait_recv(cli_server->get_socket(),5000);
                if(err != 0) {
                    if (err == SERVER_WAIT_TIMEOUT) {
                        if(resp_num == 0) { // expected no responds!
                            printf("%swait responds TIMEOUT expected (ok)!\n", name);
                            err = 0;
                        }
                        else printf("%swait responds error %d (TIMEOUT)\n", name, err);
                    }
                    else printf("%swait responds error %d\n", name, err);
                    break;
                }
                else {
                    ret = server->thread_recv(cli_server, resp, resp_num+1); // adds '\0' to data
                    if(ret <= 0) {
                        err = ret;
                        printf("%sreceive error %d\n", name, err);
                        break;
                    }
                    else {
                        num += ret; // update received bytes
                    }
                }
            } while((!err) && (num < resp_num));
            
            // display standard responds
            if((!err) && (num > 0)) {
                if(num == sizeof(SERVER_CMD)) {
                    SERVER_CMD cmd = *(SERVER_CMD*)data;
                    switch(cmd) {
                        case SERVER_ACK:  printf("%sreceived: ACK\n", name); break;
                        case SERVER_NACK: printf("%sreceived: NACK\n", name); break;
                        case SERVER_SHUTDOWN: printf("%sreceived: SHUTDOWN\n", name); break;
                        default: printf("%sreceived unknown command: 0x%lX\n", name, (unsigned long)cmd); err = -3; // should not happen!
                    }
                }
                else { 
                    printf("%sreceived %d bytes:\n", name, num); 
                    show_data((unsigned char*)data, num, false);
                }
            }
        }
    }
    return err;
}

// wait for data from server & for keyboard input (kbhit)
// if proper key pressed send shutdown command to server
// exit loop when server sends anything or on error.
int master_loop(char *name, FPGA_server *server, client_info *cli_server) {
    int err = 0;
    char c, *resp = new char[64];
    if(resp == NULL) {
        printf("%sallocation error!\n", name);
        err = -1;
    }
    else {
        printf(WAIT_TEXT_SHUT);
        CONIO_INIT();
        do {
            // wait for data from server or timeout
            err = server->thread_wait_recv(cli_server->get_socket(), 1000);
            if(err == 0) {
                // data available
                err = server->thread_recv(cli_server, resp, 64);
                if(err <= 0) printf("%sreceive error %d\n", name, err);
                else if(err == sizeof(SERVER_CMD)) {
                    switch(*(SERVER_CMD*)resp) {
                        case SERVER_ACK:  printf("%sreceived: ACK\n", name); err = 0; break;
                        case SERVER_NACK: printf("%sreceived: NACK\n", name); err = 0; break;
                        case SERVER_SHUTDOWN: printf("%sreceived: SHUTDOWN\n", name); err = 0; break;
                        default: printf("%sreceived unknown command: 0x%02X\n", name, *(SERVER_CMD*)resp); err = -3;
                    }
                }
                else { printf("%sreceived %d bytes: \"%s\"\n", name, err, resp); err = 0; }
                err = 0; // in all cases return and disconnect and shutdown server
            }
            // check if keyboard hit
            if(CONIO_KBHIT()) {
                c = CONIO_GETCH();
                if((c == WAIT_KEY_1)||(c == WAIT_KEY_2)) {
                    printf("%sshutdown key '%c' (%d) pressed\n", name, c, (int)c);
                    // send shutdown command to server
                    printf("%ssending shutdown ...\n", name);
                    SERVER_CMD cmd = SERVER_SHUTDOWN;
                    char *data =(char*)&cmd;
                    int num = sizeof(SERVER_CMD);
                    err = send_cmd(name, server, cli_server, data, num, sizeof(SERVER_CMD));
                    if(data) delete[] data;
                    break;
                }
                else {
                    // on Arty I receive here always c = 0
                    // this is because server was started without console attached
                    if(c > 0) printf("%skey '%c' (%d) pressed (continue)\n", name, c, (int)c);
                }
            }
        } while(err == SERVER_WAIT_TIMEOUT);
        CONIO_RESET();
        delete [] resp;
    }
    return err;
}

#if DIO_BYTES_PER_SAMPLE == 8
    #define    SVR_CONFIG    DIO_CONFIG_RUN_RESTART_64
#elif DIO_BYTES_PER_SAMPLE == 12
    #define SVR_CONFIG    DIO_CONFIG_RUN_RESTART_96
#endif

// calculates strobe delay from strobe delay string "r0:r1:r2:level"
// returns 0 on error
uint32_t get_strb_delay(char *str[MAX_NUM_RACKS], uint32_t scan_Hz) {
    uint32_t r0, r1, r2, level = 1, delay = 0, clk_ratio = BUS_CLOCK_FREQ_HZ / scan_Hz;
    int num, i;
    for (i = 0; i < MAX_NUM_RACKS; ++i) {
        if(str[i] == NULL) return 0;                                    // no strobe given
        //printf("strobe delay %s at bus clock %.3f MHz, scan frequency %.3f MHz\n", str[i], ((float)BUS_CLOCK_FREQ_HZ)/1e6, ((float)scan_Hz)/1e6);
        num = sscanf(str[i], "%u:%u:%u:%u", &r0, &r1, &r2, &level);
        //printf("r0:r1:r2:level = %u:%u:%u:%u\n", r0, r1, r2, level);
        if (num >= 3) {                                                 // at least r0-r2 are given. 
            if (num == 3) level = 1;                                    // set default level if not given
            r2 = r0 + r1 + r2;
            if (level == 1) {                                           // active high
                r1 = (((r0 + r1) * clk_ratio) / r2 - 1) & STRB_DELAY_MASK; // end   time in BUS_CLOCK_FREQ_HZ cycles
                r0 = (( r0       * clk_ratio) / r2)     & STRB_DELAY_MASK; // start time in BUS_CLOCK_FREQ_HZ cycles
            }
            else if (level == 2) {                                      // toggle bit (end = 0)
                r1 = 0;
                r0 = (( r0       * clk_ratio) / r2)     & STRB_DELAY_MASK; // toggle time in BUS_CLOCK_FREQ_HZ cycles
            }
            else return 0;                                              // invalid level
            //printf("r0':r1' = %u:%u, sum = %u\n", r0, r1, r2);
            delay |= (r1 << ((i*MAX_NUM_RACKS+1)*STRB_DELAY_BITS)) | (r0 << (i*MAX_NUM_RACKS*STRB_DELAY_BITS));
            //printf("strobe delay 0x%x\n", delay);
        }
        else return 0;                                                  // invalid input
    }
    return delay;
}

// application starting point
int main(int argc, char **argv)
{
    char server_port[] = SERVER_PORT;
    struct client_config c_config {
        .cmd = SERVER_CMD_OUT_CONFIG,
        .clock_Hz = BUS_CLOCK_FREQ_HZ,
        .scan_Hz = BUS_OUT_FREQ_HZ,
        .config = SVR_CONFIG,
        .ctrl_in = 0,
        .ctrl_out = 0,
        .reps = 1,
        .trans = 0
    };
    int err = 0;                                // error code returned 0=ok, otherwise nonzero
    int opt, i, num, num_cpu = 2;               // options, counter, number of cpu
    unsigned flags = 0;                         // flags
    unsigned long test = 0L;
    char *name = str_master;
    char *address = NULL, *ip_address = NULL;
    char *port = server_port;
    char *wfile = NULL, *rfile = NULL;         // write/read file names
    FPGA_server *server = NULL;
    client_info *cli_server = NULL;
    static char strb_default[] = STRB_DELAY_STR;
    char *strb_str[MAX_NUM_RACKS] = {NULL};
    uint32_t strb_delay, sync_phase = 0, sync_wait = 0;
    int strb_cnt = 0;
    bool prim = false;

#ifdef _WINDOWS
    // set console title (just nice)
    SetConsoleTitle(ServerInfo);
    wprintf(L"%s\n", ServerInfo);
    // Initialize Winsock (i.e. start and init WS2_32.dll)
    WSADATA            wsaData;                // socket data structure
    if ((err = WSAStartup(MAKEWORD(2, 2), &wsaData)) != 0) // version 2.2
    {
        printf("%s WSAStartup failed with error %d\n", name, err);
        err = MASTER_ERROR + 0x1;
    }
    else
    {
#else 

    //ungetc('x', stdin);    

    // set console title (does not work)
    //printf("\033]0;%s\007",ServerInfo);
    printf("%s\n", ServerInfo);

#ifdef _DEBUG
    printf("note: used with _DEBUG\n");
#endif
#ifdef NO_HARDWARE
    printf("ATTENTION: hardware not used!\n");
#endif

    while ((opt = getopt(argc, argv, ":sqI:P:b:p:c:w:f:")) != -1) {
        switch (opt) {
            case 's': flags |= FLAG_SERVER; break; // start
            case 'q': flags |= FLAG_QUIT; break; // quit
            case 'I': ip_address = optarg; break; // IP address
            case 'P': if (optarg[0] != '.') port = optarg; break; // optional server port
            case 'b': if (optarg[0] != '.') { if (strb_cnt < MAX_NUM_RACKS) strb_str[strb_cnt++] = optarg; else err = -2; } break; // optional strobe delay string
            case 'p': if (optarg[0] != '.') { if (atoi(optarg) == 1) prim = true; else if (atoi(optarg) == 2) prim = false; else err = -2; } break; // optional primary or secondary board 
            case 'c': if (optarg[0] != '.') { num_cpu = atoi(optarg); if ((num_cpu <= 0)||(num_cpu > 2)) err = -2; } break; // optional number of CPUs
            case 'w': if (optarg[0] != '.') { sync_wait = atoi(optarg); if (sync_wait < 0) err = -2; } break; // optional wait time
            case 'f': if (optarg[0] != '.') { if(sscanf(optarg, "0x%x", &sync_phase) != 1) err = -7; } break; // optional sync phase
            //case 'a': address = optarg; break; // remote server address
            //case 'w': flags |= FLAG_WRITE; wfile = optarg; break; // write file
            //case 'r': flags |= FLAG_READ; rfile = optarg; break; // read file
            //case 'r': c_config.reps = atol(optarg); break; // repetitions
            //case 't': flags |= FLAG_TEST; test = atol(optarg); break; // test #
            //case 'n': num_cpu = atoi(optarg); break; // number of CPU
            case '?': printf("%sunknown option\n", name); err = -2; break;
            case ':': printf("%sgive a value!\n", name); err = -2; break;
            default: err = -3;
        }
        if(err) break;
    }
    if(err > 0) err = 0;
    else if(!err) {
        if (
            ((flags & FLAG_SERVER) && (flags & ~FLAG_SERVER)) ||
            ((flags & FLAG_QUIT) && (flags & ~FLAG_QUIT)) ||
            //((flags & (FLAG_WRITE | FLAG_READ)) && (flags & ~(FLAG_WRITE | FLAG_READ))) ||
            ((flags & FLAG_TEST) && (flags & ~FLAG_TEST))
        ) {
            printf("%sinvalid combination of options!\n", name);
            err = -4;
        }
        else if(flags == 0) {
            printf("%sgive either option s or q!\n", name);
            err = -5;
        }
    }
    if (err) {

        printf("choose option:\n");
        printf("%s [-s] [-q] [-p #] [-b <strb>] [-P <1/2>] [-c <1/2>] [-w #] [-f #]\n", argv[0]);
        printf("-s        : start server\n");
        printf("-q        : quit server (localhost only)\n");
        printf("-I <IP>   : server IP address\n");
        printf("-P #      : server port #\n");
        printf("-b <strb> : strobe delay r0:r1:r2:level (give 2x for both strobes)\n");
        printf("-p <1/2>  : primary (1) or secondary (2) board\n");
        printf("-c <1/2>  : number of CPUs must be 1 or 2 (default)\n");
        printf("-w #      : waiting time before data generation\n");
        printf("-f 0x#    : sync phase {ext,det} (hex number)\n");
//        printf("    -a # = remote server IP address #\n");
//        printf("    -w file = write file\n");
//        printf("    -r file = read file\n");
//        printf("    -r # = repetitions #\n");
//        printf("    -t # = run test number #\n");
    }

    if(!err)
    {
#endif
        printf("%snumber CPU %i\n", name, num_cpu);
        printf("%ssync wait time %i\n", name, sync_wait);
        printf("%ssync phase 0x%x\n", name, sync_phase);

        // calculate strobe delay
        for(i = 0; i < MAX_NUM_RACKS; ++i) {
            if(strb_str[i] == NULL) strb_str[i] = strb_default;
        }
        strb_delay = get_strb_delay(strb_str, c_config.scan_Hz);
        if (strb_delay == 0) {
            printf("%serror strobe delay\n", name);
        }
        else {
 
            printf("%sstrobe delay 0x%08x\n", name, strb_delay);

            if (flags & FLAG_SERVER) {
                // if IP address is given wait until interface is ready and set IP address and mask
                if (ip_address) {
                    while(set_IP(ip_intf, ip_address, ip_mask) != 0) {
                        printf("%s '%s' not ready ...\n", name, IP_INTF);
                        sleep_ms(500);
                    }
                    printf("%s'%s' ready and IP '%s' set ok.\n", name, IP_INTF, ip_address);
                }
            
                // start server process
                printf("%sstart server ...\n", name);
                /* 
                // fork works but it has an "aestetic" issue:
                 // - it duplicates console and it looks like thread is blocked to user although its not blocked
                // - a more intuitive approach is to open 2 console: one for server and one for client
                pid_t pid = fork();
                if(pid == 0) { // this is child process! which will be the server master thread (daemon)
                    name = str_smaster;
                    printf("%sserver process pid %d startup ok\n", name, getpid());
                    flags |= FLAG_SERVER;
                }
                else if(pid > 0) { // this is the master
                    printf("%sserver process pid %d created ok\n", name, pid);
                }
                else { // this is the master
                    printf("%sserver process creation error %d\n", name, errno);            
                    err = -1;
                }*/
            }
            else if(flags & FLAG_QUIT) {
                printf("%sconnect and quit server ...\n", name);
            }
            else if(flags & FLAG_TEST) {
                if(address) printf("%sconnect and run test # %lu @ %s ...\n", name, test, address);
                else printf("%sconnect and run test # %lu ...\n", name, test);
            }

            // create server/client instance with specified flags
            // flags & FLAG_SERVER = creates server. if not set creates client.
            server = new FPGA_server(flags, (flags & FLAG_SERVER) ? SERVER_LOCAL_IP : (address ? address : SERVER_GLOBAL_IP), port, num_cpu, strb_delay, sync_wait, sync_phase);
            if (server == NULL) {
                printf("%sinit failed\n", name);
                err = MASTER_ERROR + 0x10;
            }
            else {
                // start (server/client) thread
                // note: for client we could call server->connect and server->recv directly and send/receive data.
                err = server->thread_start(SERVER_TIMEOUT);
                if (err) printf("%sthread start error 0x%04X\n", name, err);
                else {
                    if (flags & FLAG_SERVER) {
                        // server thread is running. wait until startup is finished
                        // returns 0 if startup successful, otherwise error code
                        printf("%sserver is starting ...\n", name);
                        err = server->thread_wait_startup(1000);
                        if(err) {
                            // todo: check type of error (0x0C11)
                            printf("%sserver start error 0x%04X (already running?)\n", name, err);
                        }
                        else {
                            printf("%sserver start succeeded\n", name);
                        }
                    }
                    if(!err) {
                        // connect to running server
                        cli_server = server->thread_connect((address ? address : SERVER_GLOBAL_IP), port);
                        if(cli_server == NULL) {
                            err = MASTER_ERROR + 0x20; // error connection
                            printf("%sconnection to %s:%s error %d\n", name, address ? address : SERVER_GLOBAL_IP, port, err);
                        }
                        else {
                            // connection established: server is running!
                            printf("%sconnection to %s:%s ok (port %hu)\n", name, 
                                cli_server->get_IP_address(), 
                                cli_server->get_port_str(), 
                                cli_server->get_local_port(false));

                            if (flags & FLAG_SERVER) {
                                // wait until key pressed or server shutdown
                                err = master_loop(name, server, cli_server);
                            }
                            else if (flags & FLAG_QUIT) {
                                // quit server by sending shutdown command
                                SERVER_CMD cmd = SERVER_SHUTDOWN;
                                char *data =(char*)&cmd;
                                int resp_num = sizeof(SERVER_CMD);
                                err = send_cmd(name, server, cli_server, data, resp_num, sizeof(SERVER_CMD));
                                if(data) delete[] data;
                            }
                            else if (flags & FLAG_TEST) {
                                // run tests
                                switch(test) {
                                    case 0:
                                        err = test0(name, server, cli_server, &c_config);
                                        break;
                                    default:
                                    printf("%stest %lu not implemented\n", name, test);
                                }
                            }

                            // disconnect from server
                            err = server->thread_disconnect(cli_server);
                            if(err) {
                                printf("%sdisconnect error 0x%04X\n", name, err);
                            }
                            else {
                                printf("%sdisconnect ok\n", name);
                            }

                            // delete client info
                            delete cli_server;
                            cli_server = NULL;
                        }
                    }
                    // wait until server/client terminates
                    err = server->thread_shutdown(SERVER_TIMEOUT<<1);
                    if(err) printf("%sshutdown error %d\n", name, err);
                    else printf("%sshutdown ok!\n", name);
                }
                // delete server
                delete(server);
                server = NULL;
            }
        }   

//sleep(10);     
#ifdef _WINDOWS
        // clean up windows sockets (i.e. delete resources and terminate WS2_32.dll)
        printf("%sunload dll\n", name);
        WSACleanup();
#endif
    }

    if(err) printf("%sterminated with error %d\n", name, err);
    else printf("%sterminated with success\n", name);

#ifdef _WINDOWS
    // wait for user presses any key
    printf("\ncontinue with any key!");
    _getch();
#endif
    printf("\n");

    return err;
}
