////////////////////////////////////////////////////////////////////////////////////////////////////
// dio24_server.h
// server communication header
// compiled with Visual Studio Express 2013 and g++
// tested with Windows 7, Ubuntu 18.04 LTS and Petalinux 2017.4
// dependency: dio24_driver.h
// created 15/06/2018 by Andi
// last change 31/05/2020 by Andi
////////////////////////////////////////////////////////////////////////////////////////////////////

#ifndef DIO24_SERVER_HEADER
#define DIO24_SERVER_HEADER

// default port on which server listens. might be overwritten by config file.
#define SERVER_PORT		"49701"

typedef uint16_t			SERVER_CMD;		// server command

#define GET_DATA_BYTES(cmd)		((cmd) >> 8)		// extract number of bytes per command
#define GET_CMD(cmd,size)		((((size)<<8) & 0xff00)|((cmd) & 0x00ff)) // make command out of comand and bytes

// data for SERVER_CMD_OUT_CONFIG sent to server and returned from server
#pragma pack(push,1)
struct client_config {
	SERVER_CMD	cmd;		// must be SERVER_CMD_OUT_CONFIG
	uint32_t	clock_Hz;	// input: external clock frequency in Hz (unused if internal clock used), output: actual used clock frequency in Hz
	uint32_t	scan_Hz;	// input: requested scan rate in Hz, output: actual scan rate in Hz
	uint32_t	config;		// input: configuration bits for DIO24_IOCTL_SET_CONFIG, output: old configuration bits
	uint32_t	extrig;		// configuration bits for DIO24_IOCTL_SET_EXTRIG (not yet implemented)
	uint32_t 	reps;		// input: number of repetitions. 0=infinite, 1=default.
	uint32_t	trans;		// number of samples
};
#pragma pack(pop)

// data for SERVER_GET_STATUS sent from server to client
#pragma pack(push,1)
struct client_status {
	SERVER_CMD		cmd;		// must be SERVER_RESP_STATUS
	struct FPGA_status_run	status;		// status information
};
#pragma pack(pop)

// data for SERVER_GET_STATUS_FULL sent from server to client
#pragma pack(push,1)
struct client_status_full {
	SERVER_CMD		cmd;		// must be SERVER_RESP_STATUS_FULL
	struct FPGA_status	status;		// full status information
};
#pragma pack(pop)

// used by server commands expecting 32bit data
#pragma pack(push,1)
struct client_data32 {
	SERVER_CMD	cmd;		// server command
	uint32_t	data;		// 32bit data
};
#pragma pack(pop)

// internal server commands between DLL or master and server
#define SERVER_CMD_NUM_INT		15					// internal server commands
#define SERVER_NONE		        GET_CMD(0x00,0)				// no command
#define SERVER_ACK		        GET_CMD(0xf0,sizeof(SERVER_CMD))	// responds acknowledgement
#define SERVER_NACK		        GET_CMD(0xf1,sizeof(SERVER_CMD))	// responds not acknowledgement
#define SERVER_RESET		        GET_CMD(0xf2,sizeof(SERVER_CMD))	// reset
#define SERVER_SHUTDOWN		        GET_CMD(0xf3,sizeof(SERVER_CMD))	// shutdown command (only accepted from local client)
#define SERVER_GET_FPGA_STATUS_BITS	GET_CMD(0xf4,sizeof(SERVER_CMD))	// get FPGA status bits
#define SERVER_RSP_FPGA_STATUS_BITS	GET_CMD(0xf4,sizeof(client_data32))	// responce FPGA status bits = data
#define SERVER_GET_DMA_STATUS_BITS	GET_CMD(0xf5,sizeof(SERVER_CMD))	// get DMA status bits
#define SERVER_RSP_DMA_STATUS_BITS	GET_CMD(0xf5,sizeof(client_data32))	// responce DMA status bits = data
#define SERVER_GET_STATUS_FULL	        GET_CMD(0xf6,sizeof(SERVER_CMD))	// get full status
#define SERVER_RSP_STATUS_FULL		GET_CMD(0xf6,sizeof(client_status_full))// responce full status (data = client_status_full)
#define SERVER_GET_STATUS	        GET_CMD(0xf7,sizeof(SERVER_CMD))	// get run status
#define SERVER_RSP_STATUS	        GET_CMD(0xf7,sizeof(client_status)) 	// responce run status (data = client_status)
#define SERVER_GET_STATUS_IRQ	        GET_CMD(0xf8,sizeof(SERVER_CMD))	// get run status, waits for FPGA irq
#define SERVER_RSP_STATUS_IRQ	        GET_CMD(0xf8,sizeof(client_status)) 	// responce run status after FPGA irq (data = client_status)
#define SERVER_TEST		        GET_CMD(0xf9,sizeof(client_data32))	// test command

// DIO64 server commands (*not implemented, **only DLL)
// first byte = command
// second byte = number of following bytes in data structure
// note: we use little endian = LSB first
#define SERVER_CMD_NUM_DIO64		18					// number of DIO64 commands
#define SERVER_CMD_OPEN			GET_CMD(0x10,sizeof(SERVER_CMD)) 	// open board (XP driver), board = user board ID
#define SERVER_CMD_OPEN_RESOURCE	GET_CMD(0x11,sizeof(SERVER_CMD))	// open resource (VISA driver) board = user board ID, resourceName = IP:port
#define SERVER_CMD_MODE			GET_CMD(0x12,sizeof(SERVER_CMD))	// undocumented (*)
#define SERVER_CMD_LOAD			GET_CMD(0x13,sizeof(SERVER_CMD))	// load FPGA board code (**)
#define SERVER_CMD_CLOSE		GET_CMD(0x14,sizeof(SERVER_CMD))	// close board
#define SERVER_CMD_IN_STATUS		GET_CMD(0x20,sizeof(SERVER_CMD))	// get input status (*)
#define SERVER_CMD_IN_START		GET_CMD(0x21,sizeof(SERVER_CMD))	// input start (*)
#define SERVER_CMD_IN_READ		GET_CMD(0x22,sizeof(SERVER_CMD))	// read data (*)
#define SERVER_CMD_IN_STOP		GET_CMD(0x23,sizeof(SERVER_CMD))	// input stop (*)
#define SERVER_CMD_OUT_CONFIG		GET_CMD(0x30,sizeof(client_config)) 	// configure outputs (data = client_config)
#define SERVER_CMD_OUT_STATUS		GET_CMD(0x31,sizeof(SERVER_CMD))	// get output status (**)
#define SERVER_CMD_OUT_WRITE		GET_CMD(0x32,sizeof(client_data32)) 	// write data (data = number of bytes)
#define SERVER_CMD_OUT_START		GET_CMD(0x33,sizeof(client_data32))	// output start (data = repetitions, 0=infinite, 1=default)
#define SERVER_CMD_OUT_STOP		GET_CMD(0x34,sizeof(SERVER_CMD))	// output stop (stop at end)
#define SERVER_CMD_OUT_FORCE		GET_CMD(0x35,sizeof(SERVER_CMD))	// force output (*)
#define SERVER_CMD_OUT_GET_INPUT	GET_CMD(0x36,sizeof(SERVER_CMD))	// get input data (*)
#define SERVER_CMD_GET_ATTRIBUTE	GET_CMD(0x40,sizeof(SERVER_CMD))	// get attribute (**)
#define SERVER_CMD_SET_ATTRIBUTE	GET_CMD(0x41,sizeof(SERVER_CMD))	// set attribute (**)

// list of all SERVER_CMD_NUM DIO64 server commands
#define SERVER_CMD_NUM		(SERVER_CMD_NUM_DIO64 + SERVER_CMD_NUM_INT) 	// total number of commands
#define SERVER_CMD_LIST		{SERVER_NONE,SERVER_ACK,SERVER_NACK,SERVER_RESET,SERVER_SHUTDOWN,\
				 SERVER_GET_FPGA_STATUS_BITS,SERVER_RSP_FPGA_STATUS_BITS,SERVER_GET_DMA_STATUS_BITS,SERVER_RSP_DMA_STATUS_BITS,\
                 		 SERVER_GET_STATUS_FULL,SERVER_RSP_STATUS_FULL,SERVER_GET_STATUS,SERVER_RSP_STATUS,SERVER_GET_STATUS_IRQ,SERVER_RSP_STATUS_IRQ,\
				 SERVER_CMD_OPEN,SERVER_CMD_OPEN_RESOURCE,SERVER_CMD_MODE,SERVER_CMD_LOAD,SERVER_CMD_CLOSE,\
				 SERVER_CMD_IN_STATUS,SERVER_CMD_IN_START,SERVER_CMD_IN_READ,SERVER_CMD_IN_STOP,SERVER_CMD_OUT_CONFIG,\
				 SERVER_CMD_OUT_STATUS,SERVER_CMD_OUT_WRITE,SERVER_CMD_OUT_START,SERVER_CMD_OUT_STOP,SERVER_CMD_OUT_FORCE,\
				 SERVER_CMD_OUT_GET_INPUT,SERVER_CMD_GET_ATTRIBUTE,SERVER_CMD_SET_ATTRIBUTE}


#endif		// DIO24_SERVER_HEADER
