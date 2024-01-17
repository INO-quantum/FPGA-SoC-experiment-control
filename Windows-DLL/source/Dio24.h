////////////////////////////////////////////////////////////////////////////////////////
// function declarations for Win32/64 DLL for easy interaction with Labview and FPGA server
// created 27/11/2019 by Andi
// last change 18/05/2020 by Andi
////////////////////////////////////////////////////////////////////////////////////////

#ifndef DIO24_H
#define DIO24_H

// following defines are needed if windows.h is included
// this prevents winsock.h to be included in windows.h which defines the older version of Winsock (1)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif

//#define _CRT_SECURE_NO_WARNINGS

#include <windows.h>

// windows sockets 2
#include <winsock2.h>			// windows socket definitions in WS2_32.lib
#include <ws2tcpip.h>			// winsock 2 definitions
#include <iphlpapi.h>			// ip helper function, include windock2.h before this

// dialog box identifiers and version info
#include "resource.h"

// define VISA_DLL for Win7 VISA driver, otherwise Win XP driver!
//#define VISA_DLL

// undefine some winerror.h definitions which are used in dio24_driver.h
#ifdef ERROR_NO_DATA
#undef ERROR_NO_DATA
#endif
#ifdef ERROR_TIMEOUT
#undef ERROR_TIMEOUT
#endif
#ifdef ERROR_INPUT
#undef ERROR_INPUT
#endif

#include "dio24/Dio64_32.h"			// XP/Win7 DIO64 driver function declarations

// DLL info used as caption in MessageBox
#define DLL_INFO				"DIO64 " DLL_TYPE " " MY_VERSION

// system wide lock
#define LOCK_NAME				"33998676-2494-4C8D-9653-2CF3A90A4D84"

// recover last board handle to allow closing of boards even on serious error.
// this is for user convenience, especially during debugging, but is not perfectly save!
// if the board(s) was/were closed due to an error or user application crashed or user Aborted labview
// then in the next run opening will fail because board is still open (dialog is still open)! 
// in this case Open will not give back the board handle (but an error code) and board_out remains the user board ID.
// to resolve this situation the DLL needs to be closed (i.e. close labview completely) and restart board(s) since they are still connected.
// this is not very convenient, however, since the DLL is still running we can in principle recover the old board handle.
// but this works only when the user-provided board ID is the same as before.
// we do not allow the user to re-open the old board(s) but we can close the old board(s) when RECOVER_HDL_ON_CLOSE is defined.
// ATTENTION: a second process (app) trying to access boards could force closing the boards of another process in this way,
//            when it can guess the board ID (or by just trying all of them). so its a security question to enable this option!
//            best is to use a random number as board-ID, but on an error do not updated this number until board is closed.
//#define RECOVER_HDL_ON_CLOSE

////////////////////////////////////////////////////////////////////////////////////////
// driver definitions
////////////////////////////////////////////////////////////////////////////////////////

#include "dio24/dio24_driver.h"

#define DLL_CONFIG_RUN_64			(DIO_CTRL_IRQ_EN|DIO_CTRL_IRQ_END_EN|DIO_CTRL_IRQ_FREQ_EN)
#define DLL_CONFIG_RUN_RESTART_64	(DLL_CONFIG_RUN_64|DIO_CTRL_IRQ_RESTART_EN|DIO_CTRL_RESTART_EN)
#define DLL_CONFIG_RUN_96			(DLL_CONFIG_RUN_64|DIO_CTRL_BPS96)
#define DLL_CONFIG_RUN_RESTART_96	(DLL_CONFIG_RUN_RESTART_64|DIO_CTRL_BPS96)

// define error state = any error bit is set and neither run nor end bits are set.
// the reason is that:
// electrical spikes can cause that external clock is lost for short time but board keeps running.
// in this case DIO_STATUS_ERR_LOCK is set but this is rather a warning than an error condition. 
// to keep experiment running we show a dialog box to warn user but do not stop board.
#define ERROR_STATE(status)			(((status) & DIO_STATUS_ERROR) && (((status) & (DIO_STATUS_RUN|DIO_STATUS_END)) == 0))
// define running or waiting state
#define RUN_STATE_OR_WAIT(status)	((status) & DIO_STATUS_RUN)
// define running but not waiting state
#define RUN_STATE_NO_WAIT(status)	(((status) & (DIO_STATUS_RUN|DIO_STATUS_WAIT)) == DIO_STATUS_RUN)
// define waiting state for restart trigger
#define WAIT_STATE(status)			(((status) & (DIO_STATUS_RUN|DIO_STATUS_WAIT)) == (DIO_STATUS_RUN|DIO_STATUS_WAIT))
// define end state
#define END_STATE(status)			((status) & DIO_STATUS_END)

#define CTRL_TRG_DST_MASK	((1<<CTRL_TRG_DST_BITS)-1)		// mask CTRL_TRG_DST_BITS

////////////////////////////////////////////////////////////////////////////////////////
// communication with FPGA-server
////////////////////////////////////////////////////////////////////////////////////////

#include "dio24/dio24_server.h"

////////////////////////////////////////////////////////////////////////////////////////
// structures and macros
////////////////////////////////////////////////////////////////////////////////////////

// timeouts in ms
#define LOCK_TIMEOUT		1000
#define CONNECT_TIMEOUT		2000
#define RECV_TIMEOUT		5000
#define RECV_TIMEOUT_DATA	200000		// when we send a lot of data we might wait longer for completion
#define THREAD_TIMEOUT		1000		// timeout in ms for status thread
#define CLOSE_TIMEOUT		200			// timeout in ms for closing connection if open is not received

// maximum number of boards
#define MAX_NUM_BOARDS		2

// log of lock and check ownership of lock
#ifdef _DEBUG

//#define SHOW_LOCK_INFO		// define to insert printf about lock aquire/release events

// for debugging we track number of locks/unlocks of lock. lock_count is protected by lock as well.
extern int lock_count;

// try to acquire lock for LOCK_TIMEOUT ms.
// returns 1 on error, otherwise 0
int LOCK_OPEN(HANDLE lock);

// acquire lock with 0 ms timeout.
// returns 1 on error, otherwise 0
int LOCK_ERROR(HANDLE lock);

// acquire lock, wait infinite until obtained. call from board_thread. cannot fail, but might wait forever.
void LOCK_OPEN_WAIT(HANDLE lock);

// call for every time LOCK_OPEN or LOCK_ERROR is called
// return value is 0 on error, nonzero on success.
int LOCK_RELEASE(HANDLE lock);

#else //end _DEBUG

// non-debug versions.

// try to acquire lock for LOCK_TIMEOUT ms.
// returns 1 on error, otherwise 0
#define LOCK_OPEN(lock)			((lock == NULL) ? 1 : (WaitForSingleObject(lock, LOCK_TIMEOUT) == WAIT_OBJECT_0) ? 0 : 1)
// acquire lock with 0 ms timeout.
// returns 1 on error, otherwise 0
// TODO: remove LOCK_ERROR and ERROR_LOCK_2 since should not be needed anymore!?
#define LOCK_ERROR(lock)		((lock == NULL) ? 1 : (WaitForSingleObject(lock, 0) == WAIT_OBJECT_0) ? 0 : 1)
// acquire lock, wait infinite until obtained. call from board_thread. cannot fail, but might wait forever.
#define LOCK_OPEN_WAIT(lock)	WaitForSingleObject(lock, INFINITE)
// call for every time LOCK_OPEN or LOCK_ERROR is called
// return value is 0 on error, nonzero on success
#define LOCK_RELEASE(lock)		ReleaseMutex(lock)

#endif //end not _DEBUG

// DIO64_OpenResource IP:port separator (define as string to allow string concatening of IP_PORT)
#define IP_PORT_SEPARATOR		":"

// IP address and port used with Open. board ID is added to last number of IP
#define IP_ADDRESS				"192.168.1.120"
#define IP_PORT					IP_ADDRESS IP_PORT_SEPARATOR SERVER_PORT

// configuration options
#define CONFIG_AUTO				// if defined use strb_delay, sync_wait and sync_phase from config.sys file
								// otherwise constants below are used (good for testing but not recommended for production).

#ifndef CONFIG_AUTO
#define ALL_STRB_DELAY_STR		"3:4:3:1"	// strobe delay string if CONFIG_AUTO not defined
#define PRIM_SYNC_DELAY			24			// sync wait in bus cycles if CONFIG_AUTO not defined
#define SEC_SYNC_PHASE_EXT		290			// external phase in degree, if CONFIG_AUTO not defined
#define SEC_SYNC_PHASE_DET		90			// detection phase in degree, if CONFIG_AUTO not defined
#endif

// full status format string
#if DIO_BYTES_PER_SAMPLE == 8
#define FMT_FULL_STATUS		"\
                TX       RX     FPGA\n\
ctrl   0x %8x        - %8x\n\
trg/ou 0x        - %8x %8x\n\
period ps %8u %8u %8u\n\
stb/ck 0x        - %8x %8x\n\
sync   0x        - %8x %8x\n\
status 0x %8x %8x %8x\n\
#/us             - %8u %8u\n\
#/us (ext)       - %8u %8u\n\
sync time        -        - %8u\n\
Temp °C          -        - %4d.%3u\n\
phase e/d        - %8u %8u\n\
err       %8d %8d %8d\n\
irq       %8u %8u %8u\n\
irq #     %8u\n\
bytes     %8u %8u %8u\n\
TX  p/a/c %8u %8u %8u\n\
RX  p/a/c %8u %8u %8u\n\
RD  m/a/d %8u %8u %8u\n\
reps/act         - %8u %8u\n\
timeout          -        - %8u\n\
last   0x %8x %8x\n\
last   us %8u\
bytes/#   %8u\n\
version   %2u.%2u - %4u/%2u/%2u\n\
info      %s\
"
#else
#define FMT_FULL_STATUS		"\
                TX       RX     FPGA\n\
ctrl   0x %8x        - %8x\n\
trg/ou 0x        - %8x %8x\n\
period ps %8u %8u %8u\n\
stb/ck 0x        - %8x %8x\n\
sync   0x        - %8x %8x\n\
status 0x %8x %8x %8x\n\
#/us             - %8u %8u\n\
#/us (ext)       - %8u %8u\n\
sync time        -        - %8u\n\
Temp °C          -        - %4d.%3u\n\
phase e/d        - %8u %8u\n\
err       %8d %8d %8d\n\
irq       %8u %8u %8u\n\
irq #     %8u\n\
bytes     %8u %8u %8u\n\
TX  p/a/c %8u %8u %8u\n\
RX  p/a/c %8u %8u %8u\n\
RD  m/a/d %8u %8u %8u\n\
reps/act         - %8u %8u\n\
timeout          -        - %8u\n\
last   0x %8x %8x %8x\n\
last   us %8u\
bytes/#   %8u\n\
version   %2u.%2u - %4u/%2u/%2u\n\
info      %s\
"
#endif

#define MSG_IGNORE_CLOCK_LOSS	L"\
Do you want to ignore external clock loss error on the secondary board?\n\n\
Attention: In this case the boards continue running even when the secondary board looses its external clock. \
But the boards might not be anymore synchronized in time!\n\n\
Once enabled, you can disable it by unchecking this option again.\
"

// error message connection to board
#define ERROR_CONNECTION_PRIM	"\
Could not connect to board %d (primary).\n\
IP address %s, port %s.\n\
Please ensure board is connected and running.\n\
Abort, Retry or Ignore?\n\
On Ignore no further connection will be attempted for this board. \
Without primary board application might not run properly.\
"
#define ERROR_CONNECTION_SEC	"\
Could not connect to board %d (secondary).\n\
IP address %s, port %s.\n\
Please ensure board is connected and running.\n\
Abort, Retry or Ignore?\n\
On Ignore no further connection will be attempted for this board.\
"

#define MB_CAPTION	DIALOG_CAPTION ": Warning!"
#define MB_TEXT_PRIM    "primary board (id %u):\nexternal clock lost in %u runs!\nlast time %04hu/%02hu/%02hu %02hu:%02hu:%02hu, run = %u"
#define MB_TEXT_SEC		"secondary board (id %u):\nexternal clock lost in %u runs!\nlast time %04hu/%02hu/%02hu %02hu:%02hu:%02hu, run = %u"

// common error codes
#define		ERROR_ARGS				-10		// illegal input argument
#define		ERROR_LOCK				-20		// could not obtain lock
#define		ERROR_LOCK_2			-21		// could not obtain lock
#define		ERROR_THREADS			-30		// threads not running
#define		ERROR_THREADS_2			-31 	// threads error
#define		ERROR_FIND_BOARD		-40		// could not find board, board ID in use or too many boards opened
#define		ERROR_FIND_BOARD_2		-41		// unexpected error with boards list
#define		ERROR_MEM				-50		// could not allocate memory
#define		ERROR_CONF				-60		// DIO64_Out_Config not called or called twice
#define		ERROR_NOT_IMPLEMENTED	-70		// function not implemented
#define		ERROR_SEND				-80		// error sending data
#define		ERROR_RECV				-90		// error receiving data = typically timeout
#define		ERROR_RECV_2			-95		// error receiving data = typically timeout
#define		ERROR_ACK				-100	// no ACK received
#define		ERROR_UNEXPECTED		-110	// unexpected responds from server received or other unexpected error
#define		ERROR_TIMEOUT_2			-120	// timeout. ERROR_TIMEOUT already defined in winerror.h but positive.
#define		ERROR_CONNECT			-130	// could not connect. most likely board is still open and server returned NACK.
#define		ERROR_CONNECT_ABORT		-131	// could not connect and user selected "Abort"
#define		ERROR_CONNECT_IGNORE	-132	// could not connect and user selected "Ignore"
#define		ERROR_IP				-140	// illegal IP address
#define		ERROR_BOARD				-150	// board is in error state
#define		ERROR_ALREADY_OPEN		-151	// tried to re-open an already open board
#define		ERROR_LOCK_LOST			-160	// external lock lost

/*
first run config ok, start_TX_sg gives error -22
then something crashes in labview or in DLL
in server get receive failed but when I try to OPEN get NACK. so it does not close the client. 2nd attempt to open works.
but then get error about lock when it tries to configure

with test vi get open error -130 without asking user and without attempting to connect. in dialog box says NACK.

*/

////////////////////////////////////////////////////////////////////////////////////////
// shared resources, protected by lock (NULL on error)
////////////////////////////////////////////////////////////////////////////////////////

// defined in DllMain.cpp
extern HINSTANCE hInstModule;		// DLL instance
extern HANDLE lock;					// mutex protects shared data (NULL initially)
extern int num_proc;				// number of attached processes
extern bool ignore_clock_loss;		// ignore clock loss
extern unsigned tot_runs;			// total number of experimental runs

// defined in Dio24.cpp
extern struct board_info *boards;	// single-linked list of master boards (NULL initially)
extern unsigned clock_Hz;			// internal clock frequency in Hz (0 initially)

////////////////////////////////////////////////////////////////////////////////////////
// dialog thread
////////////////////////////////////////////////////////////////////////////////////////

// defined in DllMain.cpp
extern DWORD WINAPI dlg_thread_proc(LPVOID lpParam);		// dialog box thread procedure
extern HANDLE dlg_thread_hdl;								// dialog box thread
extern HWND dlg_hWnd;										// dialog box handle

#define LIST_MAX	256						// maximum number of items per list. last are deleted

////////////////////////////////////////////////////////////////////////////////////////
// board threads
// each board has its own thread, board 0 = master, other boards = slave
// threads try to connect to its board on SERVER_CMD_OPEN(_RESOURCE) command
// board IP address is incremented for each board
// thread for slave is closed if:
//   - SERVER_CMD_OUT_CONFIG requests only one board used 
//   - or if user selects "ignore" on board which could not be connected
// board time is always that of master board, callback is executed by master thread.
// status is the common status of all boards:
//   - running if at least one board is running
//   - end if all boards are ended
//   - error if at least one board is in error state
// thread commands = server commands (plus THREAD_CMD_xxx)
////////////////////////////////////////////////////////////////////////////////////////

extern DWORD WINAPI board_thread(LPVOID lpParam);	// board thread function

extern int close_board(struct board_info* bd);

//#define NUM_MASTER			1		// number of master boards for which Open/OpenResource can be called. must be > 0.
//#define NUM_SLAVE			1		// number of slave boards per master. they do not appear in boards list. can be 0.
//#define NUM_BOARDS			(NUM_MASTER * (1+NUM_SLAVE))	// total number of master + slave boards

//#define SLAVE_ID_MASTER		0		// master thread id in con_data->slave_id

// IP:port separator
extern char sep[];

// mem and socket
#define ZEROMEMORY(address, size)	memset(address, 0, size)
#define CLOSESOCKET(socket)			closesocket(socket)

// board status and errors returned by thread_ functions
#define NUM_STATUS		13
enum board_status { 
	STATUS_NONE = 0,
	STATUS_ACTIVE = 1,
	STATUS_ACK = 2,
	STATUS_NACK = 3,
	STATUS_IGNORE = 4,
	STATUS_ABORT = 5,
	STATUS_ERECV = ERROR_RECV,		// returned by threads
	STATUS_ERECV_2 = ERROR_RECV_2,	// returned by user thread (Dio64 functions) 
	STATUS_ESEND = ERROR_SEND,
	STATUS_EACK = ERROR_ACK,
	STATUS_EBOARD = ERROR_BOARD,
	STATUS_EMEM = ERROR_MEM,
	STATUS_TIMEOUT_2 = ERROR_TIMEOUT_2, // STATUS_TIMEOUT already defined
	STATUS_ERROR = -99				// general error displayed in dialog box with error code (use format string in dlg_add)	
};

class thread_queue;					// used by thread_cmd, defined below.

union cmd_data {
	void* ptr;
	uint32_t u32;
};

class thread_cmd {					// queue entry
	friend thread_queue;			// allow queue to access next
private:
	thread_cmd *next;				// next command, NULL if no more commands
public:
	SERVER_CMD cmd;					// server or thread command
	union cmd_data data;			// command dependent data
	board_status status;			// status field

	thread_cmd(SERVER_CMD cmd, void *data)    { this->cmd = cmd; this->data.ptr = data; status = STATUS_NONE; next = NULL; };
	thread_cmd(SERVER_CMD cmd, uint32_t data) { this->cmd = cmd; this->data.u32 = data; status = STATUS_NONE; next = NULL; };
	~thread_cmd() {};
};

#define PRIORITY_NORMAL		false	// insert entry at end of queue
#define PRIORITY_NOW		true	// insert entry at beginning of queue

class thread_queue {
private:
	CRITICAL_SECTION cs;			// critical section protects queue
	HANDLE hSem;					// semaphore allows to wait for elemnts in queue
	class thread_cmd *first;		// first queue entry
public:
	// constructor and destructor
	thread_queue();
	~thread_queue();

	// add and remove command to/from queue
	int add(thread_cmd *cmd, bool priority);	// returns 0 on success, otherwise error
	thread_cmd * remove(DWORD timeout);			// returns removed entry or NULL if queue is empty
	thread_cmd * peek(DWORD timeout);			// returns copy of first entry or NULL if queue is empty
	int debug(thread_cmd *&last);

	// updates last queue entry of same command with new one or creates new entry if queue empty or different command.
	thread_cmd * update(thread_cmd *cmd);		// returns updated entry or NULL if new created.
};

// status to string conversion
class _status2str {
private:
	static const enum board_status sts[NUM_STATUS];
	static const char* str[NUM_STATUS];
public:
	const char *operator[](enum board_status sts);
};

// SERVER_CMD to string conversion
class _cmd2str {
private:
	static const SERVER_CMD cmd[SERVER_CMD_NUM];
	static const char* str[SERVER_CMD_NUM];
public:
	const char *operator[](SERVER_CMD cmd);
};

// data for SERVER_CMD_WRITE
#define WR_DATA_FLAG_ALL	0		// 8 or 12bytes/sample: send all data to board
#define WR_DATA_FLAG_BRD_0	1		// 12bytes/sample: send first 8bytes, skip 4 bytes
#define WR_DATA_FLAG_BRD_1	2		// 12bytes/sample: send first 4bytes, skip 4 bytes, send next 4bites
#define WR_DATA_BUFFER_SMPL	1024	// size of intermediate data buffer in samples
struct wr_data {
	char *buffer;
	int samples;
	unsigned char flags;			// see WR_DATA_FLAGS
};

// list of boards for which DIO64_Open/OpenResource was called, and closed by DIO64_Close.
// note: the thread will not immediately close board but keeps it inactive for CLOSE_TIMEOUT ms. 
//       during this time board = BOARD_NONE and the same board can be re-opened fast.
#define BOARD_NONE					((WORD)-1)
struct board_info {
	WORD board;						// user provided board ID (BOARD_NONE = unused/closed)
	WORD board_hdl;					// board handle returned by Open/OpenResource (must be used in all other calls).
	int id;							// 0-based board tab ID = board counter.
	struct board_info *next;		// next board or NULL
	// thread handle and id
	HANDLE thread_hdl;				// thread handle (NULL if thread closed)
	DWORD thread_id;				// thread id
	// sending and receiving queues per board (owned by threads)
	// valid after threads created. invalid after THREAD_EXIT command.
	thread_queue *send_queue;
	thread_queue *recv_queue;
	// board data
	char *IP_port;					// IP:port address
	int port_offset;				// offset to port in IP_port
	// dialog box info
	//int list_items;					// number of items in list box
	uint32_t config;				// board configuration
	uint32_t time;					// last board time
	uint32_t status;				// last board status
	unsigned reps;					// number of repetitions given to DIO_Out_Config
	unsigned act_reps;				// actual number of repetitions
	// status flags
	bool ignore;					// true if board is ignored, i.e. not connected but user selected to ignore
	bool running;					// true if running (for Out_Status)
};

// callback function, thread command and queue data entry
// callback function executed only by BOARD_0_MASTER thread
// returns 0 if ok, otherwise callback function is unregistered
struct cb_data {					// callback function and user data for THREAD_CMD_CB, NULL for unregister
	thread_cb callback;
	void *user_data;
};
#define THREAD_CMD_CB	MAKE_CMD(0xA0,sizeof(struct cb_data))		// register callback funcion

// start and exit thread command
#define THREAD_START	MAKE_CMD(0xA1, 0)			// returned by thread on startup. data = 1 if ok, otherwise error.
#define THREAD_EXIT		MAKE_CMD(0xA2, 0)			// send to thread to exit immediately. data = NULL.

// threads
extern HANDLE hStartup;								// signalled when thread startup and queues are valid

// thread helper functions
board_status thread_connect(SOCKET &sock, char *IP_port, int port_offset, int id);
board_status thread_close(SOCKET &sock);
board_status thread_reset(SOCKET sock);
board_status thread_config(SOCKET sock, client_config *config);
board_status thread_status(SOCKET sock, struct client_status *st);
board_status thread_write(SOCKET sock, struct wr_data *data);
board_status thread_start(SOCKET sock, int reps);
board_status thread_stop(SOCKET sock);
board_status thread_test(SOCKET sock, void *data);

// display error in dialog box
void show_error(int error, const char *cmd);
	
// dialog box functions
void dlg_update(void);
int dlg_add(struct board_info *bd, SERVER_CMD cmd, enum board_status status, const char *fmt, int data); // adds command & status info at end of list
// dialog box manual functions
int dlg_update_status(void);		// update full status for all boards
int dlg_reset(void);				// reset all boards

#endif DIO24_H
