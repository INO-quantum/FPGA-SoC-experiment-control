////////////////////////////////////////////////////////////////////////////////////////////////////
// FPGA.h
// FPGA definitions and settings for Xilinx Zynq-7020 FPGA on Petalinux
// created 15/06/2018 by Andi
// compiled with Visual Studio Express 2013 and g++
// tested with Windows 7, Ubuntu 18.04 LTS and Petalinux 2017.4
////////////////////////////////////////////////////////////////////////////////////////////////////

// on Linux
// compile with: [] = optional
//   g++ FPGA-server.cpp simple-server.cpp [FPGA-test-client.cpp] -o FPGA-server -pthread
// run with:
//   ./FPGA-server

// on Petalinux
// source Petalinux:
//   source /opt/pkg/petalinux/settings.sh
// create project:
//   cd into folder with bsp
//   petalinux-create -t project -s Petalinux-Arty-Z7-20-2017.4-1.bsp
// configure project:
//   petalinux-config
//   petalinux-config -c kernel
//   petalinux-config -c u-boot
//   petalinus-config -c rootfs
// create new application:
//   petalinux-create -t apps [--template c++] -n FPGA-server [--enable]	// use '-' instead of '_'!
//   petalinux-config -c rootfs		-> enable app if not --enable
// create new module:
//   petalinux-create -t modules -n dio-24 [--enable]				// use lowercase only!
//   petalinux-config -c rootfs		-> enable module if not --enable
//   petalinux-config -c kernel	& exit	-> this might be needed for 1st module?
// compile entire project: 
//   petalinux-build
// create BOOT.bIN to boot from SD:
//   petalinux-package --boot --force --fsbl images/linux/zynq_fsbl.elf --fpga images/linux/design_1_wrapper.bit --u-boot
//   copy image.ub and BOOT.BIN on SD card and boot board with jumper set for SD card
// compile app and re-package existing image.ub
//   petalinux-build -c FPGA-server
//   petalinux-build -x package
// change device tree / hardware has changed
//   in Vivado (Windows) export to hardware, include bitstream and copy into project folder
//   petalinux-build -x distclean		// sometimes this was needed to solve building errors
//   petalinux-config --get-hw-description=./
//   petalinux-build


#ifndef FPGA_HEADER
#define FPGA_HEADER

#include <dma24/driver.h>		// driver communication
#include <dma24/dma24.h>		// driver definitions

typedef uint16_t			U16;			// standard data U16 sent to FPGA-server
typedef uint16_t			SERVER_CMD;		// server command
#define BYTES_PER_SAMPLE		8			// bytes per scan line (8)
#define U16_PER_SAMPLE			(BYTES_PER_SAMPLE/sizeof(U16)) // number of U16 per sample (4)

#define GET_DATA_BYTES(cmd)		((cmd) >> 8)		// extract number of bytes per command
#define GET_CMD(cmd,size)		((((size)<<8) & 0xff00)|((cmd) & 0x00ff)) // make command out of comand and bytes

// data for SERVER_CMD_OUT_CONFIG sent to server and returned from server
#pragma pack(push,1)
struct client_config {
	SERVER_CMD	cmd;		// must be SERVER_CMD_OUT_CONFIG
	uint32_t	clock_Hz;	// input: external clock frequency in Hz (unused if internal clock used), output: actual used clock frequency in Hz
	uint32_t	scan_Hz;	// input: requested scan rate in Hz, output: actual scan rate in Hz
	uint32_t	config;		// input: configuration bits for DIO24_IOCTL_SET_CONFIG, output: old configuration bits
	uint32_t	extrig;		// configuration bits for DIO24_IOCTL_SET_EXTRIG
//	uint32_t 	repetitions;	// number of cycles to repeat
//	uint32_t	transitions;	// number of transitions = samples
};
#pragma pack(pop)

// data for SERVER_GET_STATUS sent from server to client
#pragma pack(push,1)
struct client_status {
	SERVER_CMD	cmd;		// must be SERVER_STATUS
	struct FPGA_status status;	// status
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
#define SERVER_NONE			GET_CMD(0x00,0)				// no command
#define SERVER_ACK			GET_CMD(0xf0,sizeof(SERVER_CMD))	// responds acknowledgement
#define SERVER_NACK			GET_CMD(0xf1,sizeof(SERVER_CMD))	// responds not acknowledgement
#define SERVER_GET_STATUS_BITS		GET_CMD(0xf2,sizeof(SERVER_CMD))	// get status bits
#define SERVER_RSP_STATUS_BITS		GET_CMD(0xf2,sizeof(client_data32))	// respond status bits = data
#define SERVER_GET_STATUS		GET_CMD(0xf3,sizeof(SERVER_CMD))	// get full status
#define SERVER_RSP_STATUS		GET_CMD(0xf3,sizeof(client_status)) 	// respond full status (data = client_status)
#define SERVER_RESET			GET_CMD(0xf4,sizeof(SERVER_CMD))	// reset
#define SERVER_SHUTDOWN			GET_CMD(0xff,sizeof(SERVER_CMD))	// shutdown command (only accepted from local client)

// DIO64 server commands (*not implemented, **only DLL)
// first byte = command
// second byte = number of following bytes in data structure
// note: we use little endian = LSB first
#define SERVER_CMD_NUM_DIO64		18					// number of DIO64 commands
#define SERVER_CMD_OPEN			GET_CMD(0x10,sizeof(SERVER_CMD)) 	// open board (XP driver), board in = IPv4 address string, board out = 16bit handle
#define SERVER_CMD_OPEN_RESOURCE	GET_CMD(0x11,sizeof(SERVER_CMD))	// open resource (VISA driver) board in = IPv4 address string, board out = 16bit handle
#define SERVER_CMD_MODE			GET_CMD(0x12,sizeof(SERVER_CMD))	// undocumented (*)
#define SERVER_CMD_LOAD			GET_CMD(0x13,sizeof(SERVER_CMD))	// load FPGA board code (**)
#define SERVER_CMD_CLOSE		GET_CMD(0x14,sizeof(SERVER_CMD))	// close board
#define SERVER_CMD_IN_STATUS		GET_CMD(0x20,sizeof(SERVER_CMD))	// get input status (*)
#define SERVER_CMD_IN_START		GET_CMD(0x21,sizeof(SERVER_CMD))	// input start (*)
#define SERVER_CMD_IN_READ		GET_CMD(0x22,sizeof(SERVER_CMD))	// read data (*)
#define SERVER_CMD_IN_STOP		GET_CMD(0x23,sizeof(SERVER_CMD))	// input stop (*)
#define SERVER_CMD_OUT_CONFIG		GET_CMD(0x30,sizeof(client_config)) 	// configure outputs (data = client_config)
#define SERVER_CMD_OUT_STATUS		GET_CMD(0x31,sizeof(SERVER_CMD))	// get ouput status (**)
#define SERVER_CMD_OUT_WRITE		GET_CMD(0x32,sizeof(client_data32)) 	// write data (data = number of bytes)
#define SERVER_CMD_OUT_START		GET_CMD(0x33,sizeof(SERVER_CMD))	// output start (*)
#define SERVER_CMD_OUT_STOP		GET_CMD(0x34,sizeof(SERVER_CMD))	// output stop (*)
#define SERVER_CMD_OUT_FORCE		GET_CMD(0x35,sizeof(SERVER_CMD))	// force output (*)
#define SERVER_CMD_OUT_GET_INPUT	GET_CMD(0x36,sizeof(SERVER_CMD))	// get input data (*)
#define SERVER_CMD_GET_ATTRIBUTE	GET_CMD(0x40,sizeof(SERVER_CMD))	// get attribute (**)
#define SERVER_CMD_SET_ATTRIBUTE	GET_CMD(0x41,sizeof(SERVER_CMD))	// set attribute (**)

// list of all SERVER_CMD_NUM DIO64 server commands
#define SERVER_CMD_NUM		(SERVER_CMD_NUM_DIO64 + 8) 	// total number of commands
#define SERVER_CMD_LIST		{SERVER_ACK,SERVER_NACK,SERVER_RESET,SERVER_SHUTDOWN,\
				 SERVER_GET_STATUS_BITS,SERVER_RSP_STATUS_BITS,SERVER_GET_STATUS,SERVER_RSP_STATUS,\
				 SERVER_CMD_OPEN,SERVER_CMD_OPEN_RESOURCE,SERVER_CMD_MODE,SERVER_CMD_LOAD,SERVER_CMD_CLOSE,\
				 SERVER_CMD_IN_STATUS,SERVER_CMD_IN_START,SERVER_CMD_IN_READ,SERVER_CMD_IN_STOP,SERVER_CMD_OUT_CONFIG,\
				 SERVER_CMD_OUT_STATUS,SERVER_CMD_OUT_WRITE,SERVER_CMD_OUT_START,SERVER_CMD_OUT_STOP,SERVER_CMD_OUT_FORCE,\
				 SERVER_CMD_OUT_GET_INPUT,SERVER_CMD_GET_ATTRIBUTE,SERVER_CMD_SET_ATTRIBUTE}


#endif		// FPGA_HEADER
