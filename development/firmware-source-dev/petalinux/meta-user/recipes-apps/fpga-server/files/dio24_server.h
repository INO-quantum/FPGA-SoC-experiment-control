////////////////////////////////////////////////////////////////////////////////////////////////////
// dio24_server.h
// server communication header
// compiled with petalinux 2020.1 on Ubuntu 20.04 LTS
// dependency: dio24_driver.h
// created 15/06/2018 by Andi
// last change 6/12/2024 by Andi
////////////////////////////////////////////////////////////////////////////////////////////////////

#ifndef DIO24_SERVER_HEADER
#define DIO24_SERVER_HEADER

// default configuration
#if DIO_BYTES_PER_SAMPLE == 8
    #define SERVER_CONFIG_DEFAULT_PRIM  (DIO_CONFIG_RUN_RESTART_64 | DIO_CTRL_AUTO_SYNC_EN | DIO_CTRL_AUTO_SYNC_PRIM)
    #define SERVER_CONFIG_DEFAULT_SEC   (DIO_CONFIG_RUN_RESTART_64 | DIO_CTRL_AUTO_SYNC_EN)
#elif DIO_BYTES_PER_SAMPLE == 12
    #define SERVER_CONFIG_DEFAULT_PRIM  (DIO_CONFIG_RUN_RESTART_96 | DIO_CTRL_AUTO_SYNC_EN | DIO_CTRL_AUTO_SYNC_PRIM)
    #define SERVER_CONFIG_DEFAULT_SEC   (DIO_CONFIG_RUN_RESTART_96 | DIO_CTRL_AUTO_SYNC_EN)
#endif

// default number of CPUs
#define SERVER_CPUS_DEFAULT         1

// default port on which server listens. might be overwritten by config file.
#define SERVER_PORT             "49701"

typedef uint16_t                SERVER_CMD;             // server command

#define GET_DATA_BYTES(cmd)     ((cmd) & 0x3ff)         // extract number of bytes (10bits, 0-1023) from SERVER_CMD
#define GET_CMD(cmd)            (((cmd)>>10) & 0x3f)    // extract command (6bits, 0-63) from SERVER_CMD
#define MAKE_CMD(cmd,size)      (((cmd & 0x3f)<<10)|((size) & 0x03ff))  // make command out of command and size in bytes
                                                                        // note: size must include SERVER_CMD

// data for SERVER_CMD_OUT_CONFIG sent to server and returned from server
#pragma pack(push,1)
struct client_config {
    SERVER_CMD  cmd;            // must be SERVER_CMD_OUT_CONFIG
    uint32_t    clock_Hz;       // input: external clock frequency in Hz, output: actual used clock frequency in Hz
    uint32_t    scan_Hz;        // input: requested scan rate in Hz, output: actual scan rate in Hz
    uint32_t    config;         // input: configuration bits for DIO24_IOCTL_SET_CONFIG, output: old configuration bits
    uint32_t    ctrl_in[2];     // input: input configuration register 0
    uint32_t    ctrl_out[2];    // input: output configuration register 0
    uint32_t    cycles;         // input: number of repetitions. 0=infinite, 1=default.
    uint32_t    samples;        // number of samples (not used)
    uint32_t    strb_delay;     // if not STRB_DELAY_AUTO strobe delay. 
                                // if STRB_DELAY_AUTO take from server.config file.
    uint32_t    sync_wait;      // if not SYNC_DELAY_AUTO waiting time of board after trigger send/receive. 
                                // if SYNC_DELAY_AUTO take from server.config file.
    uint32_t    sync_phase;     // if not SYNC_PHASE_AUTO phase {ext,det}. if SYNC_PHASE_AUTO take from server.config file.
};
#pragma pack(pop)

// data for SERVER_GET_STATUS sent from server to client
#pragma pack(push,1)
struct client_status {
    SERVER_CMD        cmd;              // must be SERVER_RESP_STATUS
    struct FPGA_status_run    status;   // status information
};
#pragma pack(pop)

// data for SERVER_GET_STATUS_FULL sent from server to client
#pragma pack(push,1)
struct client_status_full {
    SERVER_CMD        cmd;              // must be SERVER_RESP_STATUS_FULL
    struct FPGA_status    status;       // full status information
};
#pragma pack(pop)

// used by server commands expecting 32bit data
#pragma pack(push,1)
struct client_data32 {
    SERVER_CMD    cmd;          // server command
    uint32_t    data;           // 32bit data
};
#pragma pack(pop)

// used by server commands expecting 64bit data
#pragma pack(push,1)
struct client_data64 {
    SERVER_CMD    cmd;          // server command
    uint32_t    data_0;         // 32bit data
    uint32_t    data_1;         // 32bit data
};
#pragma pack(pop)

// set/get register command
#pragma pack(push,1)
struct client_sr32 {
    SERVER_CMD          cmd;    // server command
    struct set_reg32    sr32;   // set register 32 structure
};
#pragma pack(pop)

// internal server commands between DLL or boards
#define SERVER_CMD_NUM_INT          19                                      // number internal server commands
#define SERVER_NONE                 MAKE_CMD(0x00,0)                        // no command
#define SERVER_ACK                  MAKE_CMD(0x01,sizeof(SERVER_CMD))       // responds acknowledgement
#define SERVER_NACK                 MAKE_CMD(0x02,sizeof(SERVER_CMD))       // responds not acknowledgement
#define SERVER_RESET                MAKE_CMD(0x03,sizeof(SERVER_CMD))       // reset
#define SERVER_SHUTDOWN             MAKE_CMD(0x04,sizeof(SERVER_CMD))       // shutdown command (only accepted from local client)
#define SERVER_GET_FPGA_STATUS_BITS MAKE_CMD(0x05,sizeof(SERVER_CMD))       // get FPGA status bits
#define SERVER_RSP_FPGA_STATUS_BITS MAKE_CMD(0x05,sizeof(client_data32))    // responce FPGA status bits = data
#define SERVER_GET_DMA_STATUS_BITS  MAKE_CMD(0x06,sizeof(SERVER_CMD))       // get DMA status bits
#define SERVER_RSP_DMA_STATUS_BITS  MAKE_CMD(0x06,sizeof(client_data32))    // responce DMA status bits = data
#define SERVER_GET_STATUS_FULL      MAKE_CMD(0x07,sizeof(SERVER_CMD))       // get full status
#define SERVER_RSP_STATUS_FULL      MAKE_CMD(0x07,sizeof(client_status_full))// responce full status (data = client_status_full)
#define SERVER_GET_STATUS           MAKE_CMD(0x08,sizeof(SERVER_CMD))       // get run status
#define SERVER_RSP_STATUS           MAKE_CMD(0x08,sizeof(client_status))    // responce run status (data = client_status)
#define SERVER_GET_STATUS_IRQ       MAKE_CMD(0x09,sizeof(SERVER_CMD))       // get run status, waits for FPGA irq
#define SERVER_RSP_STATUS_IRQ       MAKE_CMD(0x09,sizeof(client_status))    // responce run status after FPGA irq (data = client_status)
#define SERVER_GET_REG              MAKE_CMD(0x0a,sizeof(client_sr32))      // read register = reg, result = data
#define SERVER_SET_REG              MAKE_CMD(0x0b,sizeof(client_sr32))      // write register = reg, value = data
#define SERVER_SET_EXT_CLOCK        MAKE_CMD(0x0c,sizeof(client_data64))    // switch to/from external clock
                                                                            // data0 = if nonzero switch to external clock if possible
                                                                            // data1 = sync phase {ext,det} 
#define SERVER_TEST                 MAKE_CMD(0x0f,sizeof(client_data32))    // test command

// DIO64 server commands (*not implemented, **only sent to DLL, not sent to server)
// first byte = command
// second byte = number of following bytes in data structure
// note: we use little endian = LSB first
#define SERVER_CMD_NUM_DIO64        18                                      // number of DIO64 commands
#define SERVER_CMD_OPEN             MAKE_CMD(0x20,sizeof(SERVER_CMD))       // open board (XP driver), board = user board ID
#define SERVER_CMD_OPEN_RESOURCE    MAKE_CMD(0x21,sizeof(SERVER_CMD))       // open resource (VISA driver),
                                                                            // board = user board ID, resourceName = IP:port
#define SERVER_CMD_MODE             MAKE_CMD(0x22,sizeof(SERVER_CMD))       // undocumented (*)
#define SERVER_CMD_LOAD             MAKE_CMD(0x23,sizeof(SERVER_CMD))       // load FPGA board code (**)
#define SERVER_CMD_CLOSE            MAKE_CMD(0x24,sizeof(SERVER_CMD))       // close board
#define SERVER_CMD_OUT_CONFIG       MAKE_CMD(0x25,sizeof(client_config))    // configure outputs (data = client_config)
#define SERVER_CMD_OUT_STATUS       MAKE_CMD(0x26,sizeof(SERVER_CMD))       // get output status (**)
#define SERVER_CMD_OUT_WRITE        MAKE_CMD(0x27,sizeof(client_data32))    // write data (data = number of bytes)
#define SERVER_CMD_OUT_START        MAKE_CMD(0x28,sizeof(client_data32))    // output start (data = repetitions, 0=infinite, 1=default)
#define SERVER_CMD_OUT_STOP         MAKE_CMD(0x29,sizeof(SERVER_CMD))       // output stop
#define SERVER_CMD_OUT_FORCE        MAKE_CMD(0x2a,sizeof(SERVER_CMD))       // force output (*)
#define SERVER_CMD_OUT_GET_INPUT    MAKE_CMD(0x2b,sizeof(SERVER_CMD))       // get input data (*)
#define SERVER_CMD_GET_ATTRIBUTE    MAKE_CMD(0x30,sizeof(SERVER_CMD))       // get attribute (**)
#define SERVER_CMD_SET_ATTRIBUTE    MAKE_CMD(0x31,sizeof(SERVER_CMD))       // set attribute (**)
#define SERVER_CMD_IN_STATUS        MAKE_CMD(0x3a,sizeof(SERVER_CMD))       // get input status (*)
#define SERVER_CMD_IN_START         MAKE_CMD(0x3b,sizeof(SERVER_CMD))       // input start (*)
#define SERVER_CMD_IN_READ          MAKE_CMD(0x3c,sizeof(SERVER_CMD))       // read data (*)
#define SERVER_CMD_IN_STOP          MAKE_CMD(0x3d,sizeof(SERVER_CMD))       // input stop (*)

// list of all SERVER_CMD_NUM DIO64 server commands
#define SERVER_CMD_NUM              (SERVER_CMD_NUM_DIO64 + SERVER_CMD_NUM_INT)   // total number of commands
#define SERVER_CMD_LIST     {SERVER_NONE,SERVER_ACK,SERVER_NACK,SERVER_RESET,SERVER_SHUTDOWN,\
                             SERVER_GET_FPGA_STATUS_BITS,SERVER_RSP_FPGA_STATUS_BITS,\
                             SERVER_GET_DMA_STATUS_BITS,SERVER_RSP_DMA_STATUS_BITS,\
                             SERVER_GET_STATUS_FULL,SERVER_RSP_STATUS_FULL,SERVER_GET_STATUS,SERVER_RSP_STATUS,\
                             SERVER_GET_STATUS_IRQ,SERVER_RSP_STATUS_IRQ,\
                             SERVER_GET_REG,SERVER_SET_REG,\
                             SERVER_SET_EXT_CLOCK,SERVER_TEST,\
                             SERVER_CMD_OPEN,SERVER_CMD_OPEN_RESOURCE,SERVER_CMD_MODE,SERVER_CMD_LOAD,SERVER_CMD_CLOSE,\
                             SERVER_CMD_IN_STATUS,SERVER_CMD_IN_START,SERVER_CMD_IN_READ,SERVER_CMD_IN_STOP,\
                             SERVER_CMD_OUT_CONFIG,\
                             SERVER_CMD_OUT_STATUS,SERVER_CMD_OUT_WRITE,\
                             SERVER_CMD_OUT_START,SERVER_CMD_OUT_STOP,SERVER_CMD_OUT_FORCE,\
                             SERVER_CMD_OUT_GET_INPUT,SERVER_CMD_GET_ATTRIBUTE,SERVER_CMD_SET_ATTRIBUTE}


#endif        // DIO24_SERVER_HEADER
