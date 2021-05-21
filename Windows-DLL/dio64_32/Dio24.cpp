////////////////////////////////////////////////////////////////////////////////////////
// Dio24.cpp
// Win32/64 DLL for easy interaction with Labview and FPGA server
// DIO64 functions implementations declared in Dio64_Visa.h
// created 27/11/2019 by Andi
////////////////////////////////////////////////////////////////////////////////////////

#include "Dio24.h"					// include all headers

#include <stdio.h>					// sprintf
//#include <malloc.h>

////////////////////////////////////////////////////////////////////////////////////////
// private structures and macros
////////////////////////////////////////////////////////////////////////////////////////

struct board_info *boards = NULL;	// single-linked list of master boards (NULL initially)
unsigned clock_Hz = 0;				// internal clock frequency in Hz (0 initially)
char sep[] = IP_PORT_SEPARATOR;		// IP:port separator

// windows sockets 2
WSADATA	* wsa_data = NULL;			// socket data structure
int wsa_startup = -1;				// return value of WSAStartup

////////////////////////////////////////////////////////////////////////////////////////
// private functions
////////////////////////////////////////////////////////////////////////////////////////

// finds board in list of boards
// returns NULL if board could not be found
// Attention: call LOCK() before!
inline struct board_info * find_board(WORD board) {
	struct board_info *bd;
	for (bd = boards; bd != NULL; bd = bd->next) {
		if (bd->board == board) return bd;
	}
	return NULL;
}

// finds last board in list
// returns NULL if list is empty
// Attention: call LOCK() before!
inline struct board_info *find_last(void) {
	struct board_info *bd = boards;
	if (bd != NULL) {
		while (bd->next) {
			bd = bd->next;
		}
	}
	return bd;
}

// finds previous board in list of boards
// returns NULL if list is empty, board is first board, or cannot find board
// Attention: call LOCK() before!
inline struct board_info *find_prev(struct board_info *board) {
	struct board_info *bd = boards, *prev = NULL;
	while (bd) {
		if (bd == board) return prev;
		prev = bd;
		bd = bd->next;
	}
	return NULL;
}

// checks if board is unused in list and returns next unused board with board and id set.
// returns NULL if board is already in list, if list is empty, all boards used or internal error
// Attention: call LOCK() before!
inline struct board_info * get_next(WORD board) {
	struct board_info *bd, *next = NULL;
	for (bd = boards; bd != NULL; bd = bd->next) {
		if (bd->slave_id == -1) { // unused board
			if (next == NULL) { // first unused board
				bd->board = board; // set board
				next = bd; // return next after checking finished
			}
		}
		else if (bd->board == board) return NULL; // error
	}
	return next;
}

// generates new IP address from IP_port_base adding board number to last digit of IP
// returns new IP:port string or NULL on error. delete[] after use
// offset_port receives the index of IP_PORT_SEPARATOR + 1
char *get_IP(const char *IP_port_base, unsigned short board, int *offset_port) {
	const char format[] = "%d.%d.%d.%d" IP_PORT_SEPARATOR "%d";
	char *buffer = NULL;
	int ip[4];
	unsigned port;
	int num;
	// ensure is valid in case of error
	if (offset_port) *offset_port = 0;
	// parse IP address and port
	num = sscanf_s(IP_port_base, format, &ip[0], &ip[1], &ip[2], &ip[3], &port);
	if (num == 5) {
		if ((ip[0] > 0) && (ip[0] < 256) &&
			(ip[1] > 0) && (ip[1] < 256) &&
			(ip[2] > 0) && (ip[2] < 256) &&
			(ip[3] > 0) && ((ip[3] + board) < 256)) {
			// get size of buffer
			num = _scprintf(format, ip[0], ip[1], ip[2], ip[3] + board, port);
			if (num > 0) {
				buffer = new char[num + 1];
				if (buffer) {
					// create new IP
					int n = sprintf_s(buffer, num + 1, format, ip[0], ip[1], ip[2], ip[3] + board, port);
					if (n != num) {
						delete[] buffer;
						buffer = NULL;
					}
					else if (offset_port) {
						*offset_port = 0;
						for (n = 1; buffer[n] != '\0'; ++n) {
							if (buffer[n] == sep[0]) {
								*offset_port = n + 1; 
								break;
							}
						}
					}
				}
			}
		}
	}
	return buffer;
}

////////////////////////////////////////////////////////////////////////////////////////
// status and command to string conversion
////////////////////////////////////////////////////////////////////////////////////////

const enum board_status _status2str::sts[NUM_STATUS] = { STATUS_NONE, STATUS_ACTIVE, STATUS_ACK, STATUS_NACK, STATUS_IGNORE, STATUS_ERECV, STATUS_ERECV_2, STATUS_ESEND, STATUS_EACK, STATUS_EBOARD, STATUS_EMEM, STATUS_TIMEOUT_2, STATUS_ERROR };
const char * _status2str::str[NUM_STATUS] = { "NONE", "ACTIVE", "ACK", "NACK", "IGNORE", "E_RECV", "E_REC2", "E_SEND", "E_ACK", "E_BRD", "E_MEM", "E_TIME", "ERR" };

const char *_status2str::operator[](enum board_status sts) {
	static char unk[20];
	int num, n;
	// return status string according to board_status
	for (int i = 0; i < NUM_STATUS; ++i) {
		if (sts == this->sts[i]) return str[i];
	}
	// unkown board_status (can be if this is a board error code)
	num = _scprintf("unkown %d", sts);
	if (num > 0) {	
		n = sprintf_s(unk, 20, "unkown %d", sts);
		if (n == num) {
			return unk;
		}
	}
	// status string too long? (should not happen)
	return "unknown ?";
}

const SERVER_CMD _cmd2str::cmd[SERVER_CMD_NUM] = SERVER_CMD_LIST;
const char * _cmd2str::str[SERVER_CMD_NUM] = { 
	"NONE", "ACK", "NACK", "RESET", "SHUTDOWN",
	"GET_FPGA_STATUS_BITS", "RSP_FPGA_STATUS_BITS", "GET_DMA_STATUS_BITS", "RSP_DMA_STATUS_BITS", "GET_STATUS_FULL", 
	"RSP_STATUS_FULL", "GET_STATUS", "RSP_STATUS", "GET_STATUS_IRQ", "RSP_STATUS_IRQ",
	"OPEN", "OPEN_RESOURCE", "MODE", "LOAD", "CLOSE",
	"IN_STATUS", "IN_START", "IN_READ", "IN_STOP", "OUT_CONFIG",
	"OUT_STATUS", "OUT_WRITE", "OUT_START", "OUT_STOP", "OUT_FORCE",
	"OUT_GET_INPUT", "GET_ATTRIBUTE", "SET_ATTRIBUTE" 
};

const char *_cmd2str::operator[](SERVER_CMD cmd) {
	for (int i = 0; i < SERVER_CMD_NUM; ++i) {
		if (cmd == this->cmd[i]) return str[i];
	}
	// unknown command (should not happen)
	return "unkown ?";
}

class _status2str status2str;
class _cmd2str cmd2str;

////////////////////////////////////////////////////////////////////////////////////////
// dialog box status function executed by main application thread
////////////////////////////////////////////////////////////////////////////////////////

// list of control IDs per slave_id
UINT ctrls[2][9] = {
	{ ID_IP_0, ID_ICON_0, ID_USE_0, ID_CONF_0, ID_STATUS_0, ID_TIME_0, ID_STATUS_FULL_0, ID_ASCROLL_0, ID_LIST_0 },
	{ ID_IP_1, ID_ICON_1, ID_USE_1, ID_CONF_1, ID_STATUS_1, ID_TIME_1, ID_STATUS_FULL_1, ID_ASCROLL_1, ID_LIST_1 }
};
// index into ctrl
#define I_IP			0
#define I_ICON			1
#define I_USE			2
#define I_CONF			3
#define I_STATUS		4
#define I_TIME			5
#define I_STATUS_FULL	6
#define I_ASCROLL		7
#define I_LIST			8

// update dialog box
void dlg_update(void) {
	board_info *bd;
	// update all master + slave boards
	if (!LOCK_ERROR(mutex)) {
		/* number of connected processes
		num = _scprintf("%d apps", num_proc);
		if (num > 0) {
			message = new char[num + 1];
			if (message) {
				n = sprintf_s(message, num + 1, "%d apps", num_proc);
				if (n == num) {
					SendDlgItemMessageA(dlg_hWnd, ID_NPROC, WM_SETTEXT, (WPARAM)0, (LPARAM)message);
				}
				delete[] message;
			}
		}*/
		for (bd = boards; bd != NULL; bd = bd->next) {
			if (bd->IP_port) {
				// IP:port
				SendDlgItemMessageA(dlg_hWnd, ctrls[bd->id][I_IP], WM_SETTEXT, (WPARAM)0, (LPARAM)bd->IP_port);
			}
			if (bd->ignore) { 
				// ignore flag
				HICON hicon = LoadIcon(NULL, IDI_WARNING);
				SendDlgItemMessage(dlg_hWnd, ctrls[bd->id][I_ICON], STM_SETICON, (WPARAM)hicon, (LPARAM)0);
				SendDlgItemMessage(dlg_hWnd, ctrls[bd->id][I_STATUS], WM_SETTEXT, (WPARAM)0, (LPARAM)L"not connected");
				SendDlgItemMessage(dlg_hWnd, ctrls[bd->id][I_USE], BM_SETCHECK, (WPARAM)BST_UNCHECKED, (LPARAM)0);
				SendDlgItemMessage(dlg_hWnd, ctrls[bd->id][I_USE], WM_SETTEXT, (WPARAM)0, (LPARAM)L"ignored");
				EnableWindow(GetDlgItem(dlg_hWnd, ctrls[bd->id][I_USE]), FALSE);
			}
		}
		LOCK_RELEASE(mutex);
	}
	// redraw entire dialog box
	RedrawWindow(dlg_hWnd, NULL, NULL, RDW_INVALIDATE | RDW_UPDATENOW | RDW_ALLCHILDREN);
}

// update icon according to status
// TODO: maybe load icon only once and then take handle. handle seems not to be needed to destroyed.
void dlg_update_icon(struct board_info *bd) {
	HICON hicon;
	/*if (bd->running == STATUS_ACTIVE) { // running
		hicon = LoadIcon(hInstModule, MAKEINTRESOURCE(IDI_OK));
		SendDlgItemMessage(dlg_hWnd, ctrls[bd->id][I_ICON], STM_SETICON, (WPARAM)hicon, (LPARAM)0);
	}
	else */
	if (bd->status & DIO_STATUS_ERROR) { // error
		hicon = LoadIcon(NULL, IDI_ERROR);
		SendDlgItemMessage(dlg_hWnd, ctrls[bd->id][I_ICON], STM_SETICON, (WPARAM)hicon, (LPARAM)0);
		// set also dialog icon to error
		SendMessage(dlg_hWnd, WM_SETICON, (WPARAM)ICON_BIG, (LPARAM)hicon);
		SendMessage(dlg_hWnd, WM_SETICON, (WPARAM)ICON_SMALL, (LPARAM)hicon);

	}
	else if (bd->ignore) { // ignore = not connected
		hicon = LoadIcon(NULL, IDI_WARNING);
		SendDlgItemMessage(dlg_hWnd, ctrls[bd->id][I_ICON], STM_SETICON, (WPARAM)hicon, (LPARAM)0);
	}
	else { // running or not and no error
		hicon = LoadIcon(hInstModule, MAKEINTRESOURCE(IDI_OK));
		SendDlgItemMessage(dlg_hWnd, ctrls[bd->id][I_ICON], STM_SETICON, (WPARAM)hicon, (LPARAM)0);
	}
}

// update configuration
void dlg_update_config(struct board_info *bd) {
	int num, n;
	char *message;
	num = _scprintf("%x", bd->config);
	if (num > 0) {
		message = new char[num + 1];
		if (message) {
			n = sprintf_s(message, num + 1, "%x", bd->config);
			if (n == num) {
				SendDlgItemMessageA(dlg_hWnd, ctrls[bd->id][I_CONF], WM_SETTEXT, (WPARAM)0, (LPARAM)message);
			}
			delete[] message;
		}
	}
}

// update board time and status
void dlg_update_time_status(struct board_info *bd) {
	static const char *status_str[] = { "(error)", "(run)", "(end)" };
	const char* dsc;
	char *message;
	int num, n;
	// FPGA status
	if (bd->status & DIO_STATUS_ERROR) dsc = status_str[0];
	else if (bd->status & DIO_STATUS_RUN) dsc = status_str[1];
	else if (bd->status & DIO_STATUS_END) dsc = status_str[2];
	else dsc = "";
	num = _scprintf("%x %s", bd->status, dsc);
	if (num > 0) {
		message = new char[num + 1];
		if (message) {
			n = sprintf_s(message, num + 1, "%x %s", bd->status, dsc);
			if (n == num) {
				SendDlgItemMessageA(dlg_hWnd, ctrls[bd->id][I_STATUS], WM_SETTEXT, (WPARAM)0, (LPARAM)message);
			}
			delete[] message;
		}
	}
	// FPGA board time
	num = _scprintf("%u", bd->time);
	if (num > 0) {
		message = new char[num + 1];
		if (message) {
			n = sprintf_s(message, num + 1, "%u", bd->time);
			if (n == num) {
				SendDlgItemMessageA(dlg_hWnd, ctrls[bd->id][I_TIME], WM_SETTEXT, (WPARAM)0, (LPARAM)message);
			}
			delete[] message;
		}
	}
}

// update full status for all boards
// this can be called from main thread or from dlg_thread!
// mutex must be already locked
int dlg_update_status(void) {
	int err = 0, num, n;
	struct board_info *bd;
	char *message;
	// lock mutex
	if LOCK_ERROR(mutex) err = ERROR_LOCK;
	else {
		// ensure all boards are initialized, threads are running and queues are accessible
		if (!boards) err = ERROR_THREADS;
		else {
			// get status of all boards
			for (bd = boards, n = 0; bd != NULL; bd = bd->next) {
				if (!bd->ignore) {
					bd->send_queue->add(new thread_cmd(SERVER_GET_STATUS_FULL, NULL), PRIORITY_NORMAL);
					++n;
				}
			}
			if (n == 0) err = ERROR_THREADS_2; // no boards active
			else {
				// wait for status
				for (bd = boards; bd != NULL; bd = bd->next) {
					if (!bd->ignore) {
						thread_cmd * cmd = bd->recv_queue->remove(THREAD_TIMEOUT);
						dlg_add(bd, SERVER_GET_STATUS_FULL, cmd ? cmd->status : STATUS_ERECV, NULL, 0);
						if (cmd == NULL) err = ERROR_RECV_2;
						else {
							if (cmd->status != STATUS_ACK) err = ERROR_ACK;
							else if ((cmd->cmd != SERVER_GET_STATUS_FULL) || (cmd->data == NULL)) err = ERROR_UNEXPECTED;
							else if (((struct client_status_full *)cmd->data)->cmd != SERVER_RSP_STATUS_FULL) err = ERROR_UNEXPECTED;
							else {
								// status received
								struct FPGA_status *status = &((struct client_status_full *)cmd->data)->status;
								// convert to text
								num = _scprintf(FMT_FULL_STATUS,
									status->FPGA_temp / 1000, status->FPGA_temp % 1000,
									status->ctrl_DMA, status->ctrl_FPGA,
									status->status_RX, status->status_TX, status->status_FPGA.status,
									status->set_samples, status->status_FPGA.board_time,
									status->dsc_TX_p, status->dsc_TX_a, status->dsc_TX_c,
									status->dsc_RX_p, status->dsc_RX_a, status->dsc_RX_c,
									status->err_TX, status->err_RX, status->err_TX,
									status->irq_TX, status->irq_RX, status->irq_FPGA,
									status->TX_bt_tot, status->RX_bt_tot, status->bt_tot,
									status->RD_bt_max, status->RD_bt_act, status->RD_bt_drop,
									status->reps_set, status->reps_act,
									status->last_sample.data32[0], status->last_sample.data32[1], status->last_sample.data32[2],
									status->last_sample.data32[0]
									);
								if (num > 0) {
									message = new char[num + 1];
									if (message) {
										n = sprintf_s(message, num + 1, FMT_FULL_STATUS,
											status->FPGA_temp / 1000, status->FPGA_temp % 1000,
											status->ctrl_DMA, status->ctrl_FPGA,
											status->status_RX, status->status_TX, status->status_FPGA.status,
											status->set_samples, status->status_FPGA.board_time,
											status->dsc_TX_p, status->dsc_TX_a, status->dsc_TX_c,
											status->dsc_RX_p, status->dsc_RX_a, status->dsc_RX_c,
											status->err_TX, status->err_RX, status->err_TX,
											status->irq_TX, status->irq_RX, status->irq_FPGA,
											status->TX_bt_tot, status->RX_bt_tot, status->bt_tot,
											status->RD_bt_max, status->RD_bt_act, status->RD_bt_drop,
											status->reps_set, status->reps_act,
											status->last_sample.data32[0], status->last_sample.data32[1], status->last_sample.data32[2],
											status->last_sample.data32[0]
											);
										if (n == num) {
											SendDlgItemMessageA(dlg_hWnd, ctrls[bd->id][I_STATUS_FULL], WM_SETTEXT, (WPARAM)0, (LPARAM)message);
										}
										delete[] message;
									}
								}
								delete cmd->data;
							}
							delete cmd;
						}
					}
				}
			}
		}
		// unlock mutex 1x and ensure is still locked
		if (LOCK_RELEASE(mutex) != 1) err = ERROR_LOCK_2;
	}
	if (err) show_error(err, "GET_STATUS_FULL"); // display error
	return err;
}


// reset all boards
// this can be called from main thread or from dlg_thread!
// mutex must be already locked
int dlg_reset(void) {
	int err = 0, n;
	struct board_info *bd;
	// lock mutex
	if LOCK_ERROR(mutex) err = ERROR_LOCK;
	else {
		// ensure all boards are initialized, threads are running and queues are accessible
		if (!boards) err = ERROR_THREADS;
		else {
			// get status of all boards
			for (bd = boards, n = 0; bd != NULL; bd = bd->next) {
				if (!bd->ignore) {
					bd->send_queue->add(new thread_cmd(SERVER_RESET, NULL), PRIORITY_NORMAL);
					++n;
				}
			}
			if (n == 0) err = ERROR_THREADS_2; // no boards active
			else {
				// wait for ACK in a loop
				// sometimes it helps to send reset several times
				for (bd = boards; bd != NULL; bd = bd->next) {
					if (!bd->ignore) {
						thread_cmd *cmd;
						for (n = 0; n < 5; ++n) {
							cmd = bd->recv_queue->remove(THREAD_TIMEOUT);
							dlg_add(bd, SERVER_RESET, cmd ? cmd->status : STATUS_ERECV, NULL, 0);
							if (cmd == NULL) err = ERROR_RECV_2;
							else if ((cmd->cmd != SERVER_RESET) || (cmd->status != STATUS_ACK)) { err = ERROR_ACK; break; }
							else { err = 0; break; } // ok
						}
					}
				}
			}
		}
		// unlock mutex 1x and ensure is still locked
		if (LOCK_RELEASE(mutex) != 1) err = ERROR_LOCK_2;
	}
	if (err) show_error(err, "SERVER_RESET");
	return err;
}

// adds command & status info at end of list
// if fmt != NULL formats additional data according to format string
// returns inserted list position or LB_ERR on error
// if more than LIST_MAX items are in list first item is deleted
int dlg_add(struct board_info *bd, SERVER_CMD cmd, enum board_status status, const char *fmt, int data) {
	static const char *__fmt[4] = { "%s", "%s (%s)", "%%s %s", "%%s %s (%%s)" };
	int ret = 0;
	int num, n;
	char* message;
	const char *_fmt = (status == STATUS_NONE) ? __fmt[0] : __fmt[1];
	// generate format string
	if (fmt) {
		ret = LB_ERR;
		_fmt = (status == STATUS_NONE) ? __fmt[2] : __fmt[3];
		num = _scprintf(_fmt, fmt);
		if (num > 0) {
			message = new char[num + 1];
			if (message) {
				n = sprintf_s(message, num + 1, _fmt, fmt);
				if (n == num) {
					_fmt = message;
					ret = 0;
				}
			}
		}
	}
	// generate string
	if (ret == 0) {
		if (status == STATUS_NONE) {
			if (fmt) num = _scprintf(_fmt, cmd2str[cmd], data);
			else num = _scprintf(_fmt, cmd2str[cmd]);
		}
		else {
			if (fmt) num = _scprintf(_fmt, cmd2str[cmd], data, status2str[status]);
			else num = _scprintf(_fmt, cmd2str[cmd], status2str[status]);
		}
		if (num > 0) {
			message = new char[num + 1];
			if (message) {
				if (status == STATUS_NONE) {
					if (fmt) n = sprintf_s(message, num + 1, _fmt, cmd2str[cmd], data);
					else n = sprintf_s(message, num + 1, _fmt, cmd2str[cmd]);
				}
				else {
					if (fmt) n = sprintf_s(message, num + 1, _fmt, cmd2str[cmd], data, status2str[status]);
					else n = sprintf_s(message, num + 1, _fmt, cmd2str[cmd], status2str[status]);
				}
				if (n == num) {
					ret = SendDlgItemMessageA(dlg_hWnd, ctrls[bd->id][I_LIST], LB_ADDSTRING, (WPARAM)0, (LPARAM)message);
				}
				delete[] message;
			}
		}
		// if list is too long delete first list entry
		if (ret >= LIST_MAX) {
			SendDlgItemMessageA(dlg_hWnd, ctrls[bd->id][I_LIST], LB_DELETESTRING, (WPARAM)0, (LPARAM)0L);
			--ret;
		}
		// show last item in list
		if (SendDlgItemMessage(dlg_hWnd, ctrls[bd->id][I_ASCROLL], BM_GETCHECK, (WPARAM)0, (LPARAM)0) == BST_CHECKED) {
			SendDlgItemMessageA(dlg_hWnd, ctrls[bd->id][I_LIST], LB_SETTOPINDEX, (WPARAM)ret, (LPARAM)0);
		}
		// delete format string
		if (fmt) delete _fmt;
	}
	return ret;
}

////////////////////////////////////////////////////////////////////////////////////////
// helper functions executed by main applicaton thread
////////////////////////////////////////////////////////////////////////////////////////

// display error in message box (dialog window is parent window)
void show_error(int error, const char *cmd) {
	int n, num = _scprintf("error %d in %s", error, cmd);
	if (num > 0) {
		char *message = new char[num + 1];
		if (message) {
			n = sprintf_s(message, num + 1, "error %d in %s", error, cmd);
			if (n == num) {
				MessageBoxA(dlg_hWnd, message, DLL_INFO, MB_ICONEXCLAMATION | MB_OK);
			}
			delete[] message;
		}
	}
}

#define STATUS_MSG	"%d master boards [%d,%d] id [%d,%d]: ignore [%d,%d], result %d"

void report_status(char *info, int result) {
	int n, i = 0, id[2] = { -1, -1 }, board[2] = { -1, -1 }, ignore[2] = {0 , 0,}, num;
	board_info *bd;
	for (bd = boards, i = 0; bd != NULL; bd = bd->next, ++i) {
		board[i] = bd->board;
		id[i] = bd->id;
		ignore[i] = bd->ignore;
	}
	num = _scprintf(STATUS_MSG, i, board[0], board[1], id[0], id[1], ignore[0], ignore[1], result);
	if (num > 0) {
		char *message = new char[num + 1];
		if (message) {
			n = sprintf_s(message, num + 1, STATUS_MSG, i, board[0], board[1], id[0], id[1], ignore[0], ignore[1], result);
			if (n == num) {
				MessageBoxA(NULL, message, info, MB_OK);
			}
			delete[] message;
		}
	}
}

int exit_threads(bool send_close);	// used by init_threads

// initialize boards, threads and Windows Sockets 2
int init_threads(void) {
	int err = ERROR_THREADS, i;
	thread_cmd *cmd;
	struct board_info *bd = NULL;
	// startup windows sockets if not already done
	if ((wsa_data == NULL) && (wsa_startup == -1)) {
		wsa_data = new WSADATA;
		if (wsa_data) {
			wsa_startup = WSAStartup(MAKEWORD(2, 2), wsa_data);
			if (wsa_startup == 0) {
				// create startup event (auto-reset)
				hStartup = CreateEvent(NULL, FALSE, FALSE, NULL);
				if (hStartup) {
					// startup dialog thread
					DWORD id;
					dlg_thread_hdl = CreateThread(NULL, 0, dlg_thread_proc, (LPVOID)0, 0, &id);
					if (dlg_thread_hdl != NULL) {
						// wait until dialog box is displayed
						WaitForSingleObject(hStartup, INFINITE);
						// create boards and startup all board threads
						for (i = 0; i < NUM_BOARDS; ++i) {
							if (bd == NULL) bd = boards = new struct board_info;
							else bd = bd->next = new struct board_info;
							if (bd) {
								ZEROMEMORY(bd, sizeof(struct board_info));
								bd->id = i; // board id
								bd->slave_id = -1; // mark as unused
								// threads allocate queues and set startup event
								bd->thread_hdl = CreateThread(NULL, 0, board_thread, (LPVOID)bd, 0, &bd->thread_id);
								if (bd->thread_hdl == NULL) break;
								// wait until thread sets startup event
								WaitForSingleObject(hStartup, INFINITE);
								// now queues are valid and we get startup run bit
								cmd = bd->recv_queue->remove(INFINITE);
								if (cmd->data != (void*)1) { delete cmd; break; }
								delete cmd;
							}
						}
						if (i != NUM_BOARDS) {
							// startup error: exit already running threads
							exit_threads(false);
						}
						else { // all threads running (boards != NULL)
							err = 0;
						}
					}
				}
			}
		}
	}
	//report_status("init_threads",err);
	return err;
}

// terminates all threads and Windows Sockets 2
// if send_close == true sends SERVER_CMD_CLOSE to boards before THREAD_EXIT, and waits for responds
// if send_close == false sends only THREAD_EXIT and does not wait for responds
// note: boards = NULL afterwards!
// TODO: at the moment we close all threads which is not ok if there are several master boards!
//       then we must check if all boards are closed and only then call this or do a per-board init/exit of threads.
int exit_threads(bool send_close) {
	int err = 0;
	struct board_info *bd;
	if (boards) {
		if (send_close) {
			// send close command to connected boards
			for (bd = boards; bd != NULL; bd = bd->next) {
				if (!bd->ignore) bd->send_queue->add(new thread_cmd(SERVER_CMD_CLOSE, (void*)0), PRIORITY_NORMAL);
			}
			// wait for ACK
			for (bd = boards; bd != NULL; bd = bd->next) {
				if (!bd->ignore) {
					thread_cmd * cmd = bd->recv_queue->remove(THREAD_TIMEOUT);
					if (cmd == NULL) err = ERROR_RECV_2;
					else {
						if (cmd->status != STATUS_ACK) err = ERROR_ACK;
						delete cmd;
					}
				}
			}
		}
		// send WM_DESTROY message which closes dialog box and dialog thread
		// we cannot call DestroyWindow because this must be called from same thread which created dialog box
		// dlg_hWnd is reset by thread
		// we check below that thread is closed
		if (dlg_hWnd) SendMessage(dlg_hWnd, WM_DESTROY, 0, 0L);
		// exit all running threads (no ACK expected), queues are deleted by threads!
		for (bd = boards; bd != NULL; bd = bd->next) {
			if (bd->thread_hdl) bd->send_queue->add(new thread_cmd(THREAD_EXIT, NULL), PRIORITY_NORMAL);
		}
		// delete threads and boards
		for (bd = boards; bd != NULL; bd = bd->next) {
			if (bd->IP_port) { delete[] bd->IP_port; bd->IP_port = NULL; }
			if (bd->thread_hdl) {
				WaitForSingleObject(bd->thread_hdl, INFINITE);
				bd->thread_hdl = NULL;
				bd->thread_id = 0;
			}
			struct board_info *next = bd->next;
			delete bd;
			bd = next;
		}
		// all boards deleted
		boards = NULL;
		// wait until dialog thread closed
		if (dlg_thread_hdl) {
			WaitForSingleObject(dlg_thread_hdl, INFINITE);
			dlg_thread_hdl = NULL;
		}
		// cleanup Windows sockets 2.0
		WSACleanup();
		wsa_startup = -1;
		if (wsa_data) { delete wsa_data; wsa_data = NULL; }
	}
	return err;
}

// send scmd command and data to master and slave boards and wait for responds
// this removes all old entries from recv_queue until scmd is received
// we ignore timeout here to be sure boards have executed scmd for sure
// if flags & DO_SEND == 0 then does not send scmd but only waits for responds, 
// if flags & DO_SEND != 0 then sends scmd with given data befor waiting for responds.
// if flags & CHECK_ERROR != 0 returns 0 if all commands in queue and scmd returned STATUS_ACK or STATUS_ACTIVE
// if flags & CHECK_ERROR == 0 returns 0 if scmd returned STATUS_ACK or STATUS_ACTIVE, other errors are ignored.
// on error returns first error responds status
#define DO_SEND			1
#define CHECK_ERROR		2
int send_cmd_and_clean(WORD board, SERVER_CMD scmd, void *data, unsigned flags) {
	int err = 0;
	struct board_info* bd;
	if (flags & DO_SEND) {
		// send command
		for (int i = 0; i <= NUM_SLAVE; ++i) {
			// get board info
			bd = find_board(board + i);
			if (bd == NULL) { err = ERROR_FIND_BOARD; break; }
			else if (!bd->ignore) {
				bd->send_queue->add(new thread_cmd(scmd, data), PRIORITY_NORMAL);
				//bd->dlg_pos = dlg_add(i, -1, scmd, STATUS_ACTIVE);
			}
		}
	}
	// wait for responds 
	for (int i = 0; i <= NUM_SLAVE; ++i) {
		// get board info
		bd = find_board(board + i);
		if (bd == NULL) { err = ERROR_FIND_BOARD; break; }
		else if (!bd->ignore) {
			while (true) {
				thread_cmd* cmd = bd->recv_queue->remove(THREAD_TIMEOUT);
				if (cmd) { // we ignore timeout
					if (cmd->cmd == SERVER_CMD_OUT_STATUS) {
						// delete data only if from SERVER_CMD_OUT_STATUS
						if (cmd->data) delete cmd->data;
						else if (!err) err = ERROR_UNEXPECTED; // data must not be NULL
					}
					// stop if scmd command
					else if (cmd->cmd == scmd) {
						// check status. note: earlier errors have priority if CHECK_ERROR is enabled
						if ((cmd->status != STATUS_ACK) && (cmd->status != STATUS_ACTIVE) && (!err)) err = cmd->status;
						dlg_add(bd, scmd, cmd->status, NULL, 0);
						dlg_update_icon(bd);
						delete cmd;
						break;
					}
					//else if (!err) err = ERROR_UNEXPECTED; // unexpected command [ignore for the moment]
					if(flags & CHECK_ERROR) {
						// check if any command with error (but do not abort on error)
						if ((cmd->status != STATUS_ACK) && (cmd->status != STATUS_ACTIVE) && (!err)) err = cmd->status;
					}
					// get next command
					delete cmd;
				}
			}
		}
	}
	return err;
}

////////////////////////////////////////////////////////////////////////////////////////
// DIO64 public functions
////////////////////////////////////////////////////////////////////////////////////////

// connect to master board. slave boards are automatically initialized.
// resourceName = "IP:port" of master board, slave IP are incremented per board
// board = user selected board ID
// baseio = must be 0, otherwise ignored
// define IP_PORT_SEPARATOR for definition of separator between IP and port strings
// use same board in successive calls. 
// call DIO64_Close to close master and slave boards.
// returns 0 if ok, otherwise error. 
// returns ERROR_CONNECT_IGNORE if user selected "Ignore" upon connection error [not done otherwise Yb program does not continue]
// note: do not call this function with IP:port of slave boards since they are opened automatically.
extern "C"
int DLLEXPORT DIO64_OpenResource(char* resourceName, WORD board, WORD baseio) {
	int err = 0, id = 0, num = 0;
	struct board_info *bd;
	thread_cmd *cmd;
	bool first_time = false;

	// check input arguments
	if ((resourceName == NULL) || (baseio != 0)) err = ERROR_INPUT;
	else {
		// lock mutex
		if LOCK_OPEN(mutex) err = ERROR_LOCK;
		else {
			// ensure all boards are initialized, threads are running and queues are accessible
			if (boards) {
				// threads already running:
				// we try opening and reset boards if not ignored
				// boards might have been disconnected by previous close command after timeout.
				// thread will return STATUS_ACK if board was closed, otherwise STATUS_ACTIVE if was already open.
				// note: all previous commands from queue are removed and their status ignored. ensures empty queue and clean start.
				err = send_cmd_and_clean(board, SERVER_CMD_OPEN, NULL, DO_SEND);
			}
			else {
				// first time: startup boards and threads and wait until queues are accessible
				first_time = true;
				err = init_threads();
				if (!err) {
					// connect to master and slave boards
					// for each failed connection a message box appears asking for user action
					// if user selects "ignore" no further connection will be attempted
					for (int i = 0; i <= NUM_SLAVE; ++i) {
						// check if board ID is already used and return first unused board with set board and id
						bd = get_next(board + i);
						if (bd == NULL) { err = ERROR_FIND_BOARD; break; }
						else {
							bd->IP_port = get_IP(resourceName, i, &bd->port);
							bd->slave_id = i;
							bd->send_queue->add(new thread_cmd(SERVER_CMD_OPEN_RESOURCE, NULL), PRIORITY_NORMAL);
							// for first connection we show active command
							dlg_add(bd, SERVER_CMD_OPEN_RESOURCE, STATUS_ACTIVE, NULL, 0);
						}
					}

					// display IP addresses
					dlg_update();

					// wait for responds of all boards
					if (!err) {
						for (int i = 0; i <= NUM_SLAVE; ++i) {
							// get board info
							bd = find_board(board + i);
							if (bd == NULL) { err = ERROR_FIND_BOARD; break; }
							else if (!bd->ignore) {
								// get responds
								cmd = bd->recv_queue->remove(INFINITE); // CONNECT_TIMEOUT);
								dlg_add(bd, first_time ? SERVER_CMD_OPEN_RESOURCE : SERVER_CMD_OPEN, cmd ? cmd->status : STATUS_ERECV, NULL, 0);
								if (cmd == NULL) err = ERROR_RECV_2;
								else {
									if ((cmd->status == STATUS_ACK) || (cmd->status == STATUS_ACTIVE)) ++num; // ok
									else {
#ifdef _DEBUG
										// connection not ok: in debug mode when ignored for master & slave we continue without error!
										if (cmd->status == STATUS_IGNORE)
#else
										// connection not ok: for master return error, for slave do not return error if ignored by user
										if (i == SLAVE_ID_MASTER) err = ERROR_CONNECT;
										else if (cmd->status == STATUS_IGNORE)
#endif
										{
											// close board thread and set ignore flag (no responds needed)
											// queues and handle are invalid after this!
											bd->send_queue->add(new thread_cmd(THREAD_EXIT, NULL), PRIORITY_NORMAL);
											bd->ignore = true;
											bd->thread_hdl = NULL;
											//err = ERROR_CONNECT_IGNORE; [do not return error to avoid problems with LWCVI]
										}
										else err = cmd->status;
									}
									delete cmd;
								}
							}
						}
					}
				}
#ifndef _DEBUG
				// check if threads are left
				if ((num == 0) && (!err)) err = ERROR_THREADS_2;
#endif
			}
			// on error exit all threads and delete boards
			if (err) exit_threads(false);
			// update dialog box
			dlg_update();
			// note: mutex is kept until Dio64_Close
		}
	}
	//report_status("OpenResource", err);
	return err;
}

// Open connection to master board. baseio must be 0 but is not used.
// function uses hard coded IP_PORT (defined in Dio24.h) with the last number in IP address incremented by board
// this allows to change IP address with different board id's.
// for more flexibility use OpenResource where you can give directly an IP address and port
// note: do not call this function with board id matching IP:port of slave boards!
//       slave boards have automatically incremented IP address of their master board IP
//       for example, if your first master board = 0 and it has one slave board its board number would be 1,
//       and the next master board could be 2 or anything higher.
extern "C"
int DLLEXPORT DIO64_Open(WORD board, WORD baseio) {
	int err = 0;
	char *buffer = get_IP(IP_PORT, board, NULL);
	if (buffer == NULL) err = ERROR_IP;
	else {
		err = DIO64_OpenResource(buffer, board, baseio);
		delete[] buffer;
	}
	return err;
}

// load is not used, rbfFile = NULL, intputHint = 0 or -1, outputHint = 4 or -1
// returns 0 if arguments are ok, otherwise error
// note: does not send data to server
extern "C"
int DLLEXPORT DIO64_Load(WORD board, char *rbfFile, int intputHint, int outputHint) {
	int err = 0;
	struct board_info *bd;
	// ensure mutex is locked
	if (LOCK_ERROR(mutex)) err = ERROR_LOCK;
	else {
		if (!boards) err = ERROR_THREADS;
		else {
			// check arguments
			if ((!((intputHint == 0) || (intputHint == -1))) || (!((outputHint == 4) || (outputHint == -1)))) err = ERROR_INPUT;
			else {
				for (int i = 0; i <= NUM_SLAVE; ++i) {
					// get board info
					bd = find_board(board + i);
					if (bd == NULL) { err = ERROR_FIND_BOARD; break; }
					else if (!bd->ignore) {
						dlg_add(bd, SERVER_CMD_LOAD, STATUS_NONE, NULL, 0);
					}
				}
			}
		}
		// unlock mutex 1x and ensure is still locked
		if (LOCK_RELEASE(mutex) != 1) err = ERROR_LOCK_2;
	}
	return err;
}

// close master and slave boards
// returns 0 if boards will be closed, otherwise error
// note: since the LabWindows/CVI program of Yb is opening and closing up to 2x per cycle the boards (!)
//       thread closes the connection to server only if no other command is sent within CLOSE_TIMEOUT ms.
//       in all cases threads remain running and boards are still valid.
//       user application has to call exit_all() to close boards and terminate threads.
extern "C"
int DLLEXPORT DIO64_Close(WORD board) {
	int err = 0;
	//struct board_info *bd;
	// ensure mutex is locked
	if (LOCK_ERROR(mutex)) err = ERROR_LOCK;
	else {
		if (!boards) err = ERROR_THREADS;
		else {
			/* close master and slave boards
			// we also close threads since this is the savest way. in DllMain we cannot do this!
			//err = exit_threads(true);
			// find board
			bd = find_board(board);
			if (bd == NULL) err = ERROR_FIND_BOARD;
			else {
				// remove master board from list of boards
				if (boards == bd) boards = bd->next;
				else {
					// find board before (should never fail!)
					struct board_info *prev = find_prev(bd);
					if (prev) prev->next = bd->next;
				}
				delete bd;
			}
			// update dialog box
			dlg_update();
			*/
			// send close command, remove remaining STATUS commands and wait for STATUS_ACTIVE of SERVER_CMD_CLOSE
			err = send_cmd_and_clean(board, SERVER_CMD_CLOSE, (void*)CLOSE_TIMEOUT, DO_SEND | CHECK_ERROR);
		}
		// unlock mutex 2x to finally release it
		if (LOCK_RELEASE(mutex) != 1) err = ERROR_LOCK_2;
		LOCK_RELEASE(mutex);
	}
	//report_status("Close", err);
	return err;
}

// note: in Labview defined with "*attrID" but returns error -12 (Invalid parameter)
extern "C"
int DLLEXPORT DIO64_GetAttr(WORD board, DWORD attrID, DWORD *value) {
	return ERROR_NOT_IMPLEMENTED;
}

extern "C"
int DLLEXPORT DIO64_SetAttr(WORD board, DWORD attrID, DWORD value) {
	return ERROR_NOT_IMPLEMENTED;
}

// set output configuration
// see also DIO64-Manual-Ver-1-04.pdf for details
// board = board ID given to DIO64_OpenResource
// ticks = divider
// mask = array of WORDS with bit masks for each port, use ports a+b or all ports
// maskLength = number of WORDS in mask, use 2 or 4
// flags = 0 (unused)
// clkControl = 0 (internal clock), 1 (external clock), 2-3 not used
// startType = 0 (level-high), 1 (level-low), 2 (transition-rising), 3 (transition-falling), 4 (edge-rising), 5 (edge-falling)
// startSource = 0 (none), 1 (external), 2-3 not used
// stopType = 0 (edge-rising), 1 (edge-falling)
// stopSource = 0 (none), 1 (external), 2 not used, 3 (end of data)
// AIControl = DAQ clock modulo = 0
// reps = number of repetitions
// ntrans = number of transitions (not used)
// scanRate = input: scan rate in Hz, output: actual scan rate in Hz
// NI LabWindows/CVI configuration board=0,ticks=0,
//                                mask={ffff,ffff,ffff,ffff}, maskLength=4,
//                                flags=0,clkControl=DIO64_CLK_INTERNAl,
//								  startType=0,startSource=DIO64_STRT_INTERNAL,
//                                stopType=0,stopSource=DIO64_STOP_NONE,
//                                AIControl=DIO64_AI_NONE,
//                                reps=ncycl*cyclsw,ntrans=(N+1)*cyclsw with cyclsw=0/1 to enable repetitions
//								  scanRate=&srate with srate = 1.0e6
extern "C"
int DLLEXPORT DIO64_Out_Config(	WORD board, 
								DWORD ticks, 
								WORD *mask, 
								WORD maskLength, 
								WORD flags, 
								WORD clkControl, 
								WORD startType, 
								WORD startSource, 
								WORD stopType, 
								WORD stopSource, 
								DWORD AIControl, 
								DWORD reps, 
								WORD ntrans, 
								double *scanRate
								) {
	int err = 0;
	struct client_config *config;

	// input validation
	if ( 
		(flags != 0) || (ticks != 0) || 
		((maskLength != 2) && (maskLength != 4)) ||
		((clkControl != DIO64_CLCK_INTERNAL) && (clkControl != DIO64_CLCK_EXTERNAL)) ||
		((startType != DIO64_STRTTYPE_LEVEL) && (startType != DIO64_STRTTYPE_EDGETOEDGE) && (startType != DIO64_STRTTYPE_EDGE)) ||
		((startSource != DIO64_STRT_NONE) && (startSource != DIO64_STRT_EXTERNAL)) ||
		((stopType != DIO64_STOPTYPE_EDGE)) ||
		((stopSource != DIO64_STOP_NONE) && (stopSource != DIO64_STOP_EXTERNAL)) ||
		(AIControl != DIO64_AI_NONE)
		) err = ERROR_INPUT;
	else {
		struct board_info *bd;
		// ensure mutex is locked
		if (LOCK_ERROR(mutex)) err = ERROR_LOCK;
		else {
			if (!boards) err = ERROR_THREADS;
			else {
				// allocate configuration structure
				config = new struct client_config;
				if (config == NULL) err = ERROR_MEM;
				else {
					// count number of ports: 2=64bits/samples, 4=96bits/samples
					// set config for correct bits/samples and set restart if reps != 0 or 1
					err = 0;
					int conf = 0;
					for (int i = 0; i < maskLength; ++i) {
						if (mask[i] == 0xffff) ++conf;
						else if (mask[i] != 0) {
							err = ERROR_INPUT; break; // illegal mask: must be 0 or 0xffff
						}
					}
					if (conf == 4) { // 96bits/samples
						conf = ((reps == 0) || (reps == 1)) ? DLL_CONFIG_RUN_96 : DLL_CONFIG_RUN_RESTART_96;
						// for 96bits: select board 1 if requested (otherwise use board 0)
						//if (bd->is_board2) config |= DIO_CTRL_BPS96_BRD;
					}
					else { // 64bits/samples
						conf = ((reps == 0) || (reps == 1)) ? DLL_CONFIG_RUN_64 : DLL_CONFIG_RUN_RESTART_64;
					}
					if (!err) {
						// set external clock bit if selected
						if (clkControl == DIO64_CLCK_EXTERNAL) conf |= DIO_CTRL_EXT_CLK;
						// set external trigger if bit selected
						if (startSource == DIO64_CLCK_EXTERNAL) conf |= DIO_CTRL_TRG_START_EN;
						// set actual config
						config->cmd = SERVER_CMD_OUT_CONFIG;
						config->clock_Hz = 100000000;
						config->scan_Hz = 1000000;
						config->config = conf;
						config->reps = (reps == 0) ? 1 : reps; // set reps = 1 (0 = streaming mode)
						config->extrig = 0; // for trigger config flags are used

						// configure master and slave boards
						// note: we create a copy of config for each thread, so we can delete config!
						for (int i = 0; i <= NUM_SLAVE; ++i) {
							// get board info
							bd = find_board(board + i);
							if (bd == NULL) { err = ERROR_FIND_BOARD; break; }
							else if (!bd->ignore) {
								bd->send_queue->add(new thread_cmd(SERVER_CMD_OUT_CONFIG, new client_config(*config)), PRIORITY_NORMAL);
								//bd->dlg_pos = dlg_add_hex(i, -1, SERVER_CMD_OUT_CONFIG, STATUS_ACTIVE, conf);
							}
						}
						// wait for responds
						for (int i = 0; i <= NUM_SLAVE; ++i) {
							// get board info
							bd = find_board(board + i);
							if (bd == NULL) { err = ERROR_FIND_BOARD; break; }
							else if (!bd->ignore) {
								thread_cmd * cmd = bd->recv_queue->remove(INFINITE);
								dlg_add(bd, SERVER_CMD_OUT_CONFIG, cmd ? cmd->status : STATUS_ERECV, "0x%x", conf);
								if (cmd == NULL) err = ERROR_RECV_2; // should not happen
								else {
									if ((cmd->status != STATUS_ACK) && (!err)) err = cmd->status;
									else {
										// success: save actual config
										bd->config = conf;
										dlg_update_config(bd);
									}
									delete cmd;
								}
							}
						}
					}
					delete config;
				}
			}
			// unlock mutex 1x and ensure is still locked
			if (LOCK_RELEASE(mutex) != 1) err = ERROR_LOCK_2;
		}
	}
	return err;
}

// get board status
// returns nonzero if master or slave boards are in error mode
// returns status only of master board.
extern "C"
int DLLEXPORT DIO64_Out_Status(WORD board, DWORD *scansAvail, DIO64STAT *status) {
	int err = 0;
	struct board_info *bd;
	struct client_status *cs;
	if ((!scansAvail) || (!status)) err = ERROR_INPUT;
	else {
		memset(status, 0, sizeof(DIO64STAT));
		// ensure mutex is locked
		if (LOCK_ERROR(mutex)) err = ERROR_LOCK;
		else {
			if (!boards) err = ERROR_THREADS;
			else {
				// if not running we have to ask for actual status otherwise we get status automatically
				for (int i = 0; i <= NUM_SLAVE; ++i) {
					// get board info
					bd = find_board(board + i);
					if (bd == NULL) { err = ERROR_FIND_BOARD; break; }
					else if ((!bd->ignore) && (!bd->running)) {
						bd->send_queue->add(new thread_cmd(SERVER_CMD_OUT_STATUS, NULL), PRIORITY_NORMAL);
						//bd->dlg_pos = dlg_add(i, -1, SERVER_CMD_OUT_STATUS, STATUS_ACTIVE);
					}
				}
				// get status of master and slave boards
				for (int i = 0; i <= NUM_SLAVE; ++i) {
					// get board info
					bd = find_board(board + i);
					if (bd == NULL) { err = ERROR_FIND_BOARD_2; break; }
					else if (!bd->ignore) {
						thread_cmd * cmd;
						if (bd->running) cmd = bd->recv_queue->peek(THREAD_TIMEOUT);
						else cmd = bd->recv_queue->remove(THREAD_TIMEOUT);
						// update last status
						if (cmd == NULL) err = ERROR_RECV_2;
						else {
							if ((cmd->cmd != SERVER_CMD_OUT_STATUS) || (cmd->data == NULL)) err = ERROR_UNEXPECTED;
							else if (cmd->status != STATUS_ACK) err = ERROR_ACK;
							else {
								cs = (struct client_status *)cmd->data;
								// master & slave: check error state
								if ((cs->status.status & DIO_STATUS_ERROR) && (!err)) {
									err = ERROR_BOARD;
									dlg_update_icon(bd);
								}
								if (i == 0) { // master: copy status
									status->ticks = cs->status.board_time;
									status->time[0] = cs->status.board_time & 0xffff;
									status->time[1] = cs->status.board_time >> 16;
									status->AIControl = cs->status.status;
								}
								// master & slave: update board time every second or when status changed
								// list and icon are updated only if status changed
								if ((bd->time == 0) || (bd->status != cs->status.status) || ((cs->status.board_time - bd->time) >= 1000000)) {
									if (bd->status != cs->status.status) {
										dlg_add(bd, SERVER_CMD_OUT_STATUS, cmd->status, "0x%x", cs->status.status);
										dlg_update_icon(bd);
									}
									bd->time = cs->status.board_time;
									bd->status = cs->status.status;
									dlg_update_time_status(bd);
								}
							}
							// delete data only if not running 
							//TODO: this can crash since bd->running is changed by other thread! so we do it always in OutStart/Stop.
							//if ((!bd->running) && (cmd->data)) delete cmd->data;
							delete cmd;
						}
					}
				}
			}
			// unlock mutex 1x and ensure is still locked
			if (LOCK_RELEASE(mutex) != 1) err = ERROR_LOCK_2;
		}
	}
	return err;
}

// send data to boards (status is ignored but must not be NULL)
// note: bufsize is in samples
extern "C"
int DLLEXPORT DIO64_Out_Write(WORD board, WORD *buffer, DWORD bufsize, DIO64STAT *status) {
	SERVER_CMD cmd = 0;
	int err = 0;
	struct board_info *bd;
	struct wr_data *data;

	// check input
	if ((!buffer) || (bufsize == 0) || (!status)) err = ERROR_INPUT;
	else {
		// ensure mutex is locked
		if (LOCK_ERROR(mutex)) err = ERROR_LOCK;
		else {
			if (!boards) err = ERROR_THREADS;
			else {
				data = new struct wr_data;
				if (data) {
					// send data to master and slave boards
					data->buffer = (char *)buffer;
					data->bytes = bufsize * DIO_BYTES_PER_SAMPLE;
					for (int i = 0; i <= NUM_SLAVE; ++i) {
						// get board info
						bd = find_board(board + i);
						if (bd == NULL) { err = ERROR_FIND_BOARD; break; }
						else if (!bd->ignore) {
							bd->send_queue->add(new thread_cmd(SERVER_CMD_OUT_WRITE, data), PRIORITY_NORMAL);
							//bd->dlg_pos = dlg_add_int(i, -1, SERVER_CMD_OUT_WRITE, STATUS_ACTIVE, data->bytes, " bytes");
						}
					}
					// wait for responds
					// todo: since buffer is in LWCVI we must wait here until threads return it!
					//       otherwise this might become invalid and threads crash!
					//       we could test and check if / when buffer is becoming invalid?  
					//       I guess only after cycle finished?
					for (int i = 0; i <= NUM_SLAVE; ++i) {
						// get board info
						bd = find_board(board + i);
						if (bd == NULL) { err = ERROR_FIND_BOARD; break; }
						else if (!bd->ignore) {
							thread_cmd * cmd = bd->recv_queue->remove(RECV_TIMEOUT_DATA);
							dlg_add(bd, SERVER_CMD_OUT_WRITE, cmd ? cmd->status : STATUS_TIMEOUT_2, "%u bytes", data->bytes);
							if (cmd == NULL) err = ERROR_RECV_2;
							else {
								if ((cmd->status != STATUS_ACK) && (!err)) err = cmd->status;
								delete cmd;
							}
						}
					}
					delete data; // delete only if all threads responded!
				}
			}
			// unlock mutex 1x and ensure is still locked
			if (LOCK_RELEASE(mutex) != 1) err = ERROR_LOCK_2;
		}
	}
	return err;
}

// start boards
// this empties recv_queue and checks if also previous commands are ACK'nowledged, otherwise returns error
extern "C"
int DLLEXPORT DIO64_Out_Start(WORD board) {
	int err = 0;
	// ensure mutex is locked
	if (LOCK_ERROR(mutex)) err = ERROR_LOCK;
	else {
		if (!boards) err = ERROR_THREADS;
		else {
			// start all boards and wait for responds beginning with slave boards
			// last board to start is master, which ensures slaves are ready for start trigger of master.
			// slaves boards return ACK when in running state but before triggering.
			// thread sets bd->running flag while board is running and resets at end.
			for (int i = NUM_SLAVE; i >= 0; --i) {
				struct board_info *bd = find_board(board + i);
				if (bd == NULL) { err = ERROR_FIND_BOARD; break; }
				else {
					if (bd->running) { err = ERROR_FIND_BOARD_2; break; } // board already running?
					else if (!bd->ignore) {
						// start board
						bd->send_queue->add(new thread_cmd(SERVER_CMD_OUT_START, NULL), PRIORITY_NORMAL);
						// reset time and status
						bd->status = 0x0;
						bd->time = 0;
						//bd->dlg_pos = dlg_add(i, -1, SERVER_CMD_OUT_START, STATUS_ACTIVE);
						// wait for responds and ensure recv_queue is empty
						// here we increase timeout to 10xTHREAD_TIMEOUT to be sure start is executed
						for (int i = 0; i < 10; ) {
							thread_cmd* cmd = bd->recv_queue->remove(THREAD_TIMEOUT);
							if (cmd == NULL) { ++i; err = ERROR_TIMEOUT_2; } // timeout
							else { // no timeout:
								if (err == ERROR_TIMEOUT_2) err = 0; // timeout reset
								// check if any command with error (but do not abort on error)
								if ((cmd->status != STATUS_ACK) && (!err)) err = cmd->status;
								// delete data if from SERVER_CMD_OUT_STATUS
								if (cmd->data) {
									if (cmd->cmd == SERVER_CMD_OUT_STATUS) delete cmd->data;
									else if (!err) err = ERROR_UNEXPECTED;
								}
								// stop if start command
								if (cmd->cmd == SERVER_CMD_OUT_START) {
									dlg_add(bd, SERVER_CMD_OUT_START, cmd->status, NULL, 0);
									dlg_update_icon(bd);
									delete cmd;
									break;
								}
								// get next command
								delete cmd;
							}
						}
					}
					if(err) dlg_add(bd, SERVER_CMD_OUT_START, STATUS_ERROR, "%d", err);
				}
			}
			// stop all boards if there is any error
			if (err) send_cmd_and_clean(board, SERVER_CMD_OUT_STOP, NULL, DO_SEND);
		}
		// unlock mutex 1x and ensure is still locked
		if (LOCK_RELEASE(mutex) != 1) err = ERROR_LOCK_2;
	}
	return err;
}

// stop board(s)
// this removes all commands from recv_queue and returns error if any is not ACK'nowleded
// TODO: if cycle is running asks user to stop immediately or at end of cycle
extern "C"
int DLLEXPORT DIO64_Out_Stop(WORD board) {
	int err = 0;
	// ensure mutex is locked
	if (LOCK_ERROR(mutex)) err = ERROR_LOCK;
	else {
		if (!boards) err = ERROR_THREADS;
		else {
			// stop master and slave boards and wait for responds. 
			// this removes all (status) entries from queue until SERVER_CMD_OUT_STOP
			// we ignore timeout here to be sure boards are stopped afterwards (even if user might be asked)
			// thread automatically resets bd->running flag, so we cannot check it here. afterwards its reset for sure.
			err = send_cmd_and_clean(board, SERVER_CMD_OUT_STOP, NULL, DO_SEND | CHECK_ERROR);
		}
		// unlock mutex 1x and ensure is still locked
		if (LOCK_RELEASE(mutex) == 0) err = ERROR_LOCK_2;
	}
	return err;
}

// Force output to a given state
// TODO: not implemented
extern "C"
int DLLEXPORT DIO64_Out_ForceOutput(WORD board, WORD *buffer, DWORD mask) {
	int err = 0;
	struct board_info *bd;
	// ensure mutex is locked
	if (LOCK_ERROR(mutex)) err = ERROR_LOCK;
	else {
		if (!boards) err = ERROR_THREADS;
		else {
			for (int i = 0; i <= NUM_SLAVE; ++i) {
				bd = find_board(board + i);
				if (bd == NULL) { err = ERROR_FIND_BOARD; break; }
				else if (!bd->ignore) {
					dlg_add(bd, SERVER_CMD_OUT_FORCE, STATUS_NONE, NULL, 0);
				}
			}
		}
		// unlock mutex 1x and ensure is still locked
		if (LOCK_RELEASE(mutex) != 1) err = ERROR_LOCK_2;
	}
	return err;
}

extern "C"
int DLLEXPORT DIO64_Out_GetInput(WORD board, WORD *buffer) {
	return ERROR_NOT_IMPLEMENTED;
}

extern "C"
int DLLEXPORT DIO64_In_Start(WORD board, DWORD ticks, WORD *mask, WORD maskLength, WORD flags, WORD clkControl, WORD startType, WORD startSource, WORD stopType, WORD stopSource, DWORD AIControl, double *scanRate) {
	return ERROR_NOT_IMPLEMENTED;
}

extern "C"
int DLLEXPORT DIO64_In_Stop(WORD board) {
	return ERROR_NOT_IMPLEMENTED;
}

extern "C"
int DLLEXPORT DIO64_In_Status(WORD board, DWORD *scansAvail, DIO64STAT *status) {
	return ERROR_NOT_IMPLEMENTED;
}

extern "C"
int DLLEXPORT DIO64_In_Read(WORD board, WORD *buffer, DWORD scansToRead, DIO64STAT *status) {
	return ERROR_NOT_IMPLEMENTED;
}

////////////////////////////////////////////////////////////////////////////////////////
// additional public functions
////////////////////////////////////////////////////////////////////////////////////////

// close threads and boards
extern "C" int DLLEXPORT exit_all(void) {
	int err = 0;
	// ensure mutex is locked
	if (LOCK_ERROR(mutex)) err = ERROR_LOCK;
	else {
		err = exit_threads(false);
		// unlock mutex until it is fully released
		while (LOCK_RELEASE(mutex) > 0);
	}
	return err;
}

// send test command to server
extern "C" int DLLEXPORT test(WORD board, void *data) {
	int err = 0;
	// ensure mutex is locked
	if (LOCK_ERROR(mutex)) err = ERROR_LOCK;
	else {
		if (!boards) err = ERROR_THREADS;
		else {
			err = send_cmd_and_clean(board, SERVER_TEST, data, DO_SEND | CHECK_ERROR);
		}
		// unlock mutex until it is fully released
		while (LOCK_RELEASE(mutex) > 0);
	}
	return err;
}

// register callback function with given user data
// set callback = NULL to unregister
// returns 0 on success, otherwise error
// callback is executed by master thread on each status irq
// ensure callback function is thread-safe and user_data is valid until unregistered!
extern "C" int DLLEXPORT register_callback(WORD board, thread_cb callback, void *user_data)
{
	int err = 0;
	struct board_info *bd;
	// ensure mutex is locked
	if (LOCK_ERROR(mutex)) err = ERROR_LOCK;
	else {
		if (!boards) err = ERROR_THREADS;
		else {
			// find board
			bd = find_board(board);
			if (bd == NULL) err = ERROR_FIND_BOARD;
			else if (bd->ignore) err = ERROR_UNEXPECTED; // master is ignored!
			else {
				// register callback with master thread
				struct cb_data * cb = new struct cb_data;
				if (cb == NULL)  err = ERROR_MEM;
				else {
					cb->callback = callback;
					cb->user_data = user_data;
					err = bd->send_queue->add(new thread_cmd(THREAD_CMD_CB, cb), PRIORITY_NORMAL);
					cb = NULL; // cb is deleted by thread
					// wait for responds
					thread_cmd *cmd = bd->recv_queue->remove(THREAD_TIMEOUT);
					if (cmd == NULL) err = ERROR_RECV_2;
					else {
						if ((cmd->status == STATUS_ACK) || (cmd->status == STATUS_ACTIVE)) err = 0; // success
						else err = ERROR_ACK;
						delete cmd;
					}
				}
			}
		}
		// unlock mutex 1x and ensure is still locked
		if (LOCK_RELEASE(mutex) != 1) err = ERROR_LOCK_2;
	}
	return err;
}

// load data from file
// file must contain ASCII text with 32bit unsigned integers saved as decimal or hexadecimal numbers. 
// numbers must be separated by one or several of these characters: ' ', ',', '\t', '\n', '\r'.
// all hex numbers must be preceded by "0x".
// comments can be indicated by "//", '#', ';' and are ignored until end of line '\n' or '\r'
// or can be inline or multiline within "/**/". 
// comments cannot be within numbers or terminate numbers (put separator before comment after number). 
// characters for visually grouping of numbers '.', '_' are ignored but only within numbers.
// returns single-linked list of data_info structures, NULL on error
// returned data contains samples*word_per_samples 32bit numbers, 0 on error
// file must contain integer multiple of uint32_per_samples 32bit numbers,
// and each returned data buffer contains integer multiple of uint32_per_sample 32bit numbers.
// i.e. set words_per_sample = DIO_BYTES_PER_SAMPLE / sizeof(uint32_t).
#define BLEN		1024	// allocated number of samples per buffer
#define RD_SEP		0		// skip separators
#define RD_SKIP		1		// skip within /**/
#define RD_SKIPEND	2		// skip until end of line
#define RD_DEC		3		// read decimal number
#define RD_HEX		4		// read hex number
#define RD_ZERO		5		// zero read
#define RD_SLASH	6		// slash read
#define RD_STAR		7		// star read
extern "C" __declspec(dllexport) struct data_info* __stdcall load_text_file(const char* filename, unsigned* samples, unsigned uint32_per_sample) {
	uint32_t number = 0, * p;
	DWORD rd;
	char* buffer, t;
	unsigned bc, wc, blen = BLEN - (BLEN % uint32_per_sample);
	struct data_info* data = NULL, * next = NULL;
	int mode = RD_SEP;
	// reset samples
	*samples = 0;
	// open file
	HANDLE hFile = CreateFileA(
		filename,				// filename
		GENERIC_READ,			// read only
		FILE_SHARE_READ,		// allow reading access for other applications
		NULL,					// no security attributes
		OPEN_EXISTING,			// file must exist
		FILE_ATTRIBUTE_NORMAL,	// no special attributes
		NULL					// no template used
	);
	if (hFile != INVALID_HANDLE_VALUE) {
		// allocate small buffer for reading from file
		buffer = new char[BLEN];
		// allocate first data
		data = next = (struct data_info*) new struct data_info;
		next->next = NULL;
		next->data = p = new uint32_t[blen];
		next->samples = wc = 0;
		// read text until end of file
		while ((ReadFile(hFile, buffer, BLEN, &rd, NULL) == TRUE) && (rd > 0)) {
			// interpret text
			for (bc = 0; bc < rd; ++bc) {
				t = buffer[bc];
				switch (t) {
				case '/':
					if (mode == RD_SEP) mode = RD_SLASH; // "//" or "/*"
					else if (mode == RD_SLASH) mode = RD_SKIPEND; // "//"
					else if (mode == RD_STAR) mode = RD_SEP; // "*/"
					else if ((mode != RD_SKIP) && (mode != RD_SKIPEND)) goto error; // comment or error
					break;
				case '*':
					if (mode == RD_SLASH) mode = RD_SKIP; // "/*"
					else if (mode == RD_SKIP) mode = RD_STAR; // possible "*/"
					else if (mode != RD_SKIPEND) goto error; // comment or error
					break;
				case '#':
				case ';':
					if (mode == RD_SEP) mode = RD_SKIPEND; // skip comment until new line
					else if ((mode != RD_SKIP) && (mode != RD_SKIPEND)) goto error; // comment or error
					break;
				case '\n':
				case '\r':
					if (mode == RD_SKIPEND) { mode = RD_SEP; break; } // end skip end of line
					else if ((mode == RD_SEP) || (mode == RD_SKIP)) break; // separator or multiline comment
					// otherwise: separator
				case ' ':
				case ',':
					if ((mode == RD_DEC) || (mode == RD_HEX) || (mode == RD_ZERO)) { // separator
						// save number
						*p++ = number;
						number = 0;
						if (++wc >= blen) { // allocate new data
							next->samples = wc / uint32_per_sample;
							*samples += next->samples;
							next = next->next = new struct data_info;
							next->next = NULL;
							next->data = p = new uint32_t[BLEN];
							next->samples = wc = 0;
						};
						mode = RD_SEP;
					}
					else if ((mode != RD_SEP) && (mode != RD_SKIP) && (mode != RD_SKIPEND)) goto error; // separator, comment or error
					break;
				case 'x':
					if (mode == RD_ZERO) mode = RD_HEX; // "0x" = hex number 
					else if ((mode != RD_SKIP) && (mode != RD_SKIPEND)) goto error; // comment or error
					break;
				case '0':
					if (mode == RD_SEP) mode = RD_ZERO;	// "0" or "0x"
					else if (mode == RD_DEC) number *= 10;
					else if (mode == RD_HEX) number *= 16;
					else if ((mode != RD_ZERO) && (mode != RD_SKIP) && (mode != RD_SKIPEND)) goto error; // "00", comment or error
					break;
				case '1':
				case '2':
				case '3':
				case '4':
				case '5':
				case '6':
				case '7':
				case '8':
				case '9':
					if ((mode == RD_SEP) || (mode == RD_ZERO)) { mode = RD_DEC; number = t - '0'; }
					else if (mode == RD_DEC) number = number * 10 + (t - '0');
					else if (mode == RD_HEX) number = number * 16 + (t - '0');
					else if ((mode != RD_SKIP) && (mode != RD_SKIPEND)) goto error; // comment or error
					break;
				case 'a':
				case 'b':
				case 'c':
				case 'd':
				case 'e':
				case 'f':
					if (mode == RD_HEX) number = number * 16 + (t - 'a' + 10);
					else if ((mode != RD_SKIP) && (mode != RD_SKIPEND)) goto error; // comment or error
					break;
				case 'A':
				case 'B':
				case 'C':
				case 'D':
				case 'E':
				case 'F':
					if (mode == RD_HEX) number = number * 16 + (t - 'A' + 10);
					else if ((mode != RD_SKIP) && (mode != RD_SKIPEND)) goto error; // comment or error
					break;
				case '.':
				case '_':
					if ((mode != RD_ZERO) && (mode != RD_DEC) && (mode != RD_HEX) &&
						(mode != RD_SKIP) && (mode != RD_SKIPEND)) goto error; // number, comment or error
					break;
				default:
					if ((mode != RD_SKIP) && (mode != RD_SKIPEND)) goto error; // comment or error
				}
			}
		}
		// update number of samples
		next->samples = wc / uint32_per_sample;
		*samples += next->samples;
		goto ok;
	error:
		// delete all data
		while (data) {
			struct data_info* next = data->next;
			delete[] data->data;
			delete data;
			data = next;
		}
	ok:
		delete[] buffer;
		CloseHandle(hFile);
	}
	// return data or NULL on error
	return data;
}

// save data to ASCII file which can be loaded by load_text_file
// for file format and allowed characters see load_file
extern "C" int DLLEXPORT save_text_file(const char* filename, struct data_info* data, unsigned uint32_per_sample) {
	int err = 0;
	unsigned int i, col, bcnt;
	char* buffer, * b;
	uint32_t* p;
	DWORD written;
	HANDLE hFile = CreateFileA(
		filename,				// filename
		GENERIC_WRITE,			// write only
		0,						// no sharing for other applications
		NULL,					// no security attributes
		OPEN_ALWAYS,			// create or overwrite ol file
		FILE_ATTRIBUTE_NORMAL,	// no special attributes
		NULL					// no template used
	);
	if (hFile == INVALID_HANDLE_VALUE) err = -1;
	else {
		// allocate small buffer for writing to file
		bcnt = BLEN;
		buffer = b = new char[bcnt];
		while (data) {
			col = 1;
			for (i = 0, p = data->data; i < data->samples; ) {
				// write data into buffer.
				// bcnt = number of remaining bytes in buffer including \0
				// err = number of written characters without \0 or -1 on error (buffer full)
				if (col == 1)                     err = sprintf_s(b, bcnt, "%10d, ", *p); // save time as decimal number
				else if (col < uint32_per_sample) err = sprintf_s(b, bcnt, "0x%08x, ", *p); // save data as hex number
				else                              err = sprintf_s(b, bcnt, "0x%x\r\n", *p); // save last data as hex number
				if (err > 0) { // all ok 
					b += err;
					bcnt -= err;
					++i;
					++p;
					if (col == uint32_per_sample) col = 1;
					else ++col;
				}
				else {
					// buffer full: write data to file
					if (WriteFile(hFile, buffer, BLEN - bcnt, &written, NULL) == FALSE) { err = -3; break; }
					else if (written != BLEN - bcnt) { err = -4; break; }
					// reset buffer and repeat previous sprintf
					b = buffer;
					bcnt = BLEN;
				}
			}
			// next data or NULL
			data = data->next;
		}
		// delete buffer and close file
		delete[] buffer;
		CloseHandle(hFile);
	}
	return err;
}
