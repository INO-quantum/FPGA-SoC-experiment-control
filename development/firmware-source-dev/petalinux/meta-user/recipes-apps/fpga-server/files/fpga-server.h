////////////////////////////////////////////////////////////////////////////////////////////////////
// fpga-server.h
// 32bit linux console application to be run on Xilinx Zynq-7020 FPGA on Petalinux
// created 15/06/2018 by Andi
// compiled with Visual Studio Express 2013 and g++
// tested with Windows 7, Ubuntu 18.04 LTS and Petalinux 2017.4
// last change 6/12/2024 by Andi
////////////////////////////////////////////////////////////////////////////////////////////////////


#ifndef FPGA_server_HEADER
#define FPGA_server_HEADER

#include "simple-server.h"                  // simple-server class
#include "dio24/dio24_driver.h"             // public driver definitions
//#include "dio24/driver.h"                   // convenience IOCTL macros
#include "dio24_server.h"                   // public server communication
#include <semaphore.h>                      // semaphore
#include <errno.h>                          // errno 

// flags used by server:
#define FLAG_NONE    0x0000                 // no flag defined
#define FLAG_SERVER    0x0001               // start as server (1) or as client connecting to server (0)
#define FLAG_SHUTDOWN    0x0002             // shutdown server when all clients disconnected
// command line option given to master:
//#define FLAG_WRITE    0x1000              // send data
//#define FLAG_READ    0x2000               // receveive data
#define FLAG_QUIT    0x4000                 // quit server
#define FLAG_TEST    0x8000                 // test

// names in printf messages
#define     MASTER          "FPGA-master: "
#define     CLIENT          "FPGA-client: "
#define     SERVER          "FPGA-server: "
#define     HELPER          "HELPER: "

#define TMP_BUF_SIZE    8

// if SAVE_DATA_FILE is defined auto-sync data is saved
#define SAVE_DATA_FILE                      "/mnt/sd/result.csv"
#define SAVE_DATA_ROWS                      500
#define SAVE_DATA_COLS                      5

// helper thread
#define HELPER_TIMEOUT_MS                   1000                        // helper thread wakep interval
#define HELPER_CMD_WRITE                    0x100                       // write command
#define HELPER_CMD_STAT_START               0x200                       // start CPU statistics
#define HELPER_CMD_STAT_STOP                0x201                       // stop CPU statistics and return result
#define HELPER_CMD_AUTO_SYNC                0x300                       // start auto-sync. returns ONDATA_ACK/NACK before started and if ACK result on queue after finished 
#define HELPER_CMD_EXIT                     0xF00                       // exit helper thread

#define UPLOAD_AND_WRITE                                                // upload data and simultaneously write to DMA memory (default)
                                                                        // for dual core CPU writes with helper thread in parallel, for single core CPU writes with main thread immediately
                                                                        // if not defined always upload and writes sequentially with single thread 
#ifdef UPLOAD_AND_WRITE
#define WAIT_HELPER_START                                               // if defined (default): wait helper finished writing data in SERVER_CMD_OUT_START, otherwise in collect_write_data
#endif

//#define TIMING_TEST                                                     // define to measure upload time
#ifdef TIMING_TEST
#define TIMING_TEST_FILE_NAME               "/mnt/sd/result.csv"
#define TIMING_TEST_PL_FREQ                 50                          // PL slow frequency in MHz used for calculating data rate
#define TIMING_TEST_NUM_COLS                8                           // number of columns in result file
#endif // TIMING_TEST

// undefine HELPER_WRITE if TIMING_TEST_NO_WRITE is defined
#ifdef TIMING_TEST_NO_WRITE
#ifdef HELPER_WRITE
#undef HELPER_WRITE
#endif
#endif

// data sent to helper thread for HELPER_CMD_WRITE command
class write_info {
public:
    FILE_HANDLE dma24_dev;                  // dma24 device file handle
    char * buffer;                          // pointer to buffer
    size_t bytes;                           // number of bytes
    size_t offset;                          // offset of write() [at the moment not used]
    size_t written;                         // written bytes or <=0 on error
    write_info() { dma24_dev=0; buffer=NULL; bytes = 0; offset=0; written=0; };
    write_info(FILE_HANDLE dma24_dev, char *buffer, size_t bytes, size_t offset) { this->dma24_dev=dma24_dev; this->buffer=buffer; this->bytes=bytes; this->offset=offset; written=0; };
    ~write_info() { if (buffer) printf("write_info: Attention! delete buffer manually!\n"); };
};

// entries in queue
class queue_entry {
    friend class queue;                     // allow queue to access next
    struct queue_entry *next;               // next entry or NULL
public:
    int cmd;                                // user-defined command
    void *data;                             // user data

    queue_entry() { cmd = -1; data = NULL; next = NULL; };
    queue_entry(int _cmd, void *_data) { cmd = _cmd; data = _data; next = NULL; };
    ~queue_entry() {};
};

// simple queue class
class queue {
private:
    sem_t sem;                              // wait & counting
    pthread_mutex_t mutex;                  // protection
    queue_entry *first, *last;              // pointer to first and last queue entries, NULL if empty
public:
    queue();                                // constructor
    ~queue();                               // destructor

    void put(queue_entry *entry);           // append entry (can be several) to queue
    queue_entry *get(int max, unsigned timeout_ms); // remove maximum max entries from queue (<0 for all, 0 = peek first entry without removing)
};

// FPGA_server class inherited from simple_server virtual basic class
class FPGA_server : public simple_server {
private:
    unsigned flags;                         // flags given to constructor
    char * name;                            // name of server
    const char *server_IP;                  // server IP
    const char *server_port;                // server port
    uint32_t t_old;                         // time measurments with get_ticks() in us
    SERVER_CMD active_cmd;                  // active command (used for collecting more data)
    uint32_t b_set;                         // total number of bytes to receive from client
    uint32_t b_act;                         // actual number of bytes written bytes to device
    uint32_t b_part;                        // partial written bytes in last recv buffer (0 if all written)
    int num_cpu;                            // number of CPUs (1 or 2)
    bool primary;                           // primary board
    THREAD_HANDLE helper_handle;		    // helper thread handle
    bool helper_running;                    // indicates helper is running
    int helper_count;                       // number of buffers submitted to helper
    queue *send_queue;                      // send queue to helper thread
    queue *recv_queue;                      // receive queue from helper thread
    int act_phase;                          // actual phase of clock_slow_PS in steps
    int i_tot;                              // total number of transmitted buffers
    uint32_t clk_div;                       // clock divider
    uint32_t ctrl_in[2];                    // input configuration
    uint32_t ctrl_out[2];                   // output configuration
    uint32_t strb_delay;                    // strobe delay
    uint32_t sync_wait;                     // wait time before output of data
    uint32_t sync_phase;                    // synchronization phase
#ifdef SAVE_DATA_FILE
    uint32_t *save_data;                    // pointer to save data in result file
    int save_data_length;                   // number of uint32_t in save_data
#endif
#ifdef TIMING_TEST
    //struct FPGA_status status;              // board status
    uint32_t b_first;                       // first buffer size
    uint32_t t_RT;                          // round trip time
    uint32_t t_upload;                      // uploading time
#endif

    FILE_HANDLE dio24_dev;                  // dio24 device file handle
    FILE_HANDLE dma24_dev;                  // dma24 device file handle

    // private functions
    static THREAD_ENTRY(helper_thread, class FPGA_server *server); // helper thread entry point
    int helper_start(void);                 // start helper thread if num_cpu > 1
    int helper_shutdown(unsigned long timeout); // shutdown of helper thread within given timeout in ms
    int collect_write_data(client_info *c, char *last_buffer, int last_bytes, int tot_bytes, int &result); // SERVER_CMD_OUT_WRITE collect data
    int wait_helper_write(void);            // wait until helper finished writing

public:
    // constructor and destructor
    FPGA_server(unsigned flags, const char *IP, const char *port, 
                uint32_t clk_div, uint32_t ctrl_in[2], uint32_t ctrl_out[2], 
                uint32_t strb_delay, uint32_t sync_wait, uint32_t sync_phase,
                int num_cpu, bool primary);
    ~FPGA_server();

    // FPGA server implementation
    virtual void onStartup(void);           // server startup
    virtual bool onConnect(client_info *c); // client has connected to server. return true to accept client
    virtual void onTimeout(void);           // called every timeout ms. use for timing
    virtual void onSendFinished(client_info *c, void *data, int num, int sent, unsigned allow_delete, int error); // sending of large data finished
    virtual void onDisconnect(client_info *c); // client disconnected
    virtual void onShutdown(int error);     // server shutdown with error code (0=ok)
    // received tot_bytes > 0 bytes of data from client/server. return one of the ONDATA_ values.
    virtual int onData(client_info *c, char *last_buffer, int last_bytes, int tot_bytes);
};

// main thread
#define MASTER_ERROR        0x0A00          // error codes of master thread start with this

// FPGA server
#define SERVER_INFO         "FPGA server v1.0 by Andi"
#define SERVER_GLOBAL_IP    "localhost"     // global server IP address. this must be a resolvable IP like "localhost" or "192.168.0.10"
#define SERVER_LOCAL_IP     INADDR_ANY      // local server IP address. normally INADDR_ANY = NULL. different only when several network cards.
#define SERVER_MAX_CLIENTS  3               // maximum number of clients the server accepts, maximum SOMAXCONN
#define SERVER_TIMEOUT      2000            // server timeout in ms
#define SERVER_PHASE_RETRY  10              // number of retries for phase shift


// common error codes used by onData
#define ONDATA_NONE                0        // no error
#define ONDATA_ACK                 1        // return ACK
#define ONDATA_NACK                2        // return NACK
#define ONDATA_CMD                 4        // valid command received: enter switch-case

#endif // FPGA_server_HEADER
