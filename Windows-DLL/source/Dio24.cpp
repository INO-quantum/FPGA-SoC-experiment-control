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

struct board_info *boards = NULL;	// single-linked list of boards (NULL initially)
int boards_num = 0;					// number of boards in list 'boards'
bool boards_linked = false;			// set to true when Open/OpenResource is called with baseio giving number of linked boards.
unsigned tot_runs;					// total number of experimental runs
									// all commands and data are automatically send to all linked boards.
unsigned short boards_prim = 0;		// board handle of primary board (used for linked boards)
unsigned clock_Hz = 0;				// internal clock frequency in Hz (0 initially)
char sep[] = IP_PORT_SEPARATOR;		// IP:port separator

// windows sockets 2
WSADATA	* wsa_data = NULL;			// socket data structure
int wsa_startup = -1;				// return value of WSAStartup

////////////////////////////////////////////////////////////////////////////////////////
// private functions
////////////////////////////////////////////////////////////////////////////////////////

// finds board in list of boards
// if linked boards, board = primary board handle, returns n=0 primary, n=1 first secondary, n=2, second seconday board, etc.
// if is_ID = true, then board is not board handle but user-provided board ID. be careful with this!
// returns NULL if board could not be found
// Attention: lock must be acquired before!
inline struct board_info * find_board(WORD board, int n, bool is_ID = false) {
	struct board_info *bd;
	if (is_ID) {
		for (bd = boards; bd != NULL; bd = bd->next) {
			if (bd->board == board) {
				// board found
				if (boards_linked) {
					// return n'th linked board
					if (n >= boards_num) return NULL; // invalid n
					for (int i = 0; (bd != NULL) && (i < n); ++i) {
						bd = bd->next;
					}
				}
				return bd;
			}
		}
	}
	else {
		for (bd = boards; bd != NULL; bd = bd->next) {
			if (bd->board_hdl == board) {
				// board found
				if (boards_linked) {
					// return n'th linked board
					if (n >= boards_num) return NULL; // invalid n
					for (int i = 0; (bd != NULL) && (i < n); ++i) {
						bd = bd->next;
					}
				}
				return bd;
			}
		}
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
// returns NULL if board is already in list, if list is empty, all boards used, board=-1 or internal error
// board id cannot be -1
// Attention: call LOCK() before!
inline struct board_info * get_next(WORD board) {
	struct board_info *bd, *next = NULL;
	if (board != -1) {
		for (bd = boards; bd != NULL; bd = bd->next) {
			if (bd->board == -1) { // unused board
				if (next == NULL) { // first unused board
					bd->board = board; // set board
					next = bd; // return next after checking finished
				}
			}
			else if (bd->board == board) return NULL; // error
		}
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
		if ((ip[0] >= 0) && (ip[0] < 256) &&
			(ip[1] >= 0) && (ip[1] < 256) &&
			(ip[2] >= 0) && (ip[2] < 256) &&
			(ip[3] >= 0) && ((ip[3] + board) < 256)) {
			// get size of buffer
			num = _scprintf(format, ip[0], ip[1], ip[2], ip[3] + board, port);
			if (num > 0) {
				buffer = new char[((size_t)num) + 1];
				if (buffer) {
					// create new IP
					int n = sprintf_s(buffer, ((size_t)num) + 1, format, ip[0], ip[1], ip[2], ip[3] + board, port);
					if (n != num) {
						delete[] buffer;
						buffer = NULL;
					}
					else if (offset_port) {
						*offset_port = 0;
						for (n = 1; (n < (num+1)) && (buffer[n] != '\0'); ++n) {
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

// calculates strobe delay from strobe delay string "r0:r1:r2:level"
// returns 0 on error
uint32_t get_strb_delay(const char* str[MAX_NUM_RACKS], uint32_t scan_Hz) {
	uint32_t r0, r1, r2, level = 1, delay = 0;
	int num, i;
	for (i = 0; i < MAX_NUM_RACKS; ++i) {
		if (str[i] == NULL) return 0;                                   // no strobe given
		num = sscanf_s(str[i], "%u:%u:%u:%u", &r0, &r1, &r2, &level);
		if (num >= 3) {                                                 // at least r0-r2 are given. 
			if (num == 3) level = 1;                                    // set default level if not given
			r2 = r0 + r1 + r2;
			if (level == 1) {                                           // active high
				r1 = (((r0 + r1) * BUS_CLOCK_FREQ_HZ / scan_Hz) / r2 - 1) & STRB_DELAY_MASK; // end   time in BUS_CLOCK_FREQ_HZ cycles
				r0 = ((r0 * BUS_CLOCK_FREQ_HZ / scan_Hz) / r2) & STRB_DELAY_MASK; // start time in BUS_CLOCK_FREQ_HZ cycles
			}
			else if (level == 2) {                                      // toggle bit (end = 0)
				r1 = 0;
				r0 = ((r0 * BUS_CLOCK_FREQ_HZ / scan_Hz) / r2) & STRB_DELAY_MASK; // toggle time in BUS_CLOCK_FREQ_HZ cycles
			}
			else return 0;                                              // invalid level
			delay |= (r1 << ((i * MAX_NUM_RACKS + 1) * STRB_DELAY_BITS)) | (r0 << (i * MAX_NUM_RACKS * STRB_DELAY_BITS));
		}
		else return 0;                                                  // invalid input
	}
	return delay;
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
	"GET_FPGA_STATUS_BITS", "RSP_FPGA_STATUS_BITS", "GET_DMA_STATUS_BITS", "RSP_DMA_STATUS_BITS", 
	"GET_STATUS_FULL", "RSP_STATUS_FULL", "GET_STATUS", "RSP_STATUS", "GET_STATUS_IRQ", "RSP_STATUS_IRQ",
	"AS_START", "AS_STOP", "AS_SET_PHASE", "GET_INFO", "TEST",
	"OPEN", "OPEN_RES", "MODE", "LOAD", "CLOSE",
	"IN_STATUS", "IN_START", "IN_READ", "IN_STOP", "CONFIG",
	"STATUS", "WRITE", "START", "STOP", "FORCE",
	"GET_INPUT", "GET_ATTR", "SET_ATTR"
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
// index into ctrls
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
	// acquire lock
	if (!LOCK_ERROR(lock)) {
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
		// release lock
		LOCK_RELEASE(lock);
	}
	// redraw entire dialog box
	RedrawWindow(dlg_hWnd, NULL, NULL, RDW_INVALIDATE | RDW_UPDATENOW | RDW_ALLCHILDREN);
}

// update icon according to status
// TODO: maybe load icon only once and then take handle. handle seems not to be needed to destroyed.
void dlg_update_icon(struct board_info *bd) {
	HICON hicon;
	/*if (bd->running == STATUS_ACTIVE) { // running. Andi: removed to avoid fast change of state between running and stopped
		hicon = LoadIcon(hInstModule, MAKEINTRESOURCE(IDI_OK));
		SendDlgItemMessage(dlg_hWnd, ctrls[bd->id][I_ICON], STM_SETICON, (WPARAM)hicon, (LPARAM)0);
	}
	else */
	if (bd->status & DIO_STATUS_ERROR) { // error
		if (bd->status & (DIO_STATUS_RUN | DIO_STATUS_END)) hicon = LoadIcon(NULL, IDI_WARNING); // error but running or end
		else	                                            hicon = LoadIcon(NULL, IDI_ERROR); // error and not running
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
		message = new char[((size_t)num) + 1];
		if (message) {
			n = sprintf_s(message, ((size_t)num) + 1, "%x", bd->config);
			if (n == num) {
				SendDlgItemMessageA(dlg_hWnd, ctrls[bd->id][I_CONF], WM_SETTEXT, (WPARAM)0, (LPARAM)message);
			}
			delete[] message;
		}
	}
}

// update board time and status
void dlg_update_time_status(struct board_info *bd) {
	static const char *status_str[] = { "(run|error)", "(end|error)", "(error)", "(run)", "(end)" };
	const char* dsc;
	char *message;
	int num, n;
	// FPGA status
	if (bd->status & DIO_STATUS_ERROR) dsc = (bd->status & DIO_STATUS_RUN) ? status_str[0] : 
		                                     (bd->status & DIO_STATUS_END) ? status_str[1] : status_str[2];
	else if (bd->status & DIO_STATUS_RUN) dsc = status_str[3];
	else if (bd->status & DIO_STATUS_END) dsc = status_str[4];
	else dsc = "";
	num = _scprintf("%08x %s", bd->status, dsc);
	if (num > 0) {
		message = new char[((size_t)num) + 1];
		if (message) {
			n = sprintf_s(message, ((size_t)num) + 1, "%08x %s", bd->status, dsc);
			if (n == num) {
				SendDlgItemMessageA(dlg_hWnd, ctrls[bd->id][I_STATUS], WM_SETTEXT, (WPARAM)0, (LPARAM)message);
			}
			delete[] message;
		}
	}
	// FPGA board time
	num = _scprintf("%10u", bd->time);
	if (num > 0) {
		message = new char[((size_t)num) + 1];
		if (message) {
			n = sprintf_s(message, ((size_t)num) + 1, "%10u", bd->time);
			if (n == num) {
				SendDlgItemMessageA(dlg_hWnd, ctrls[bd->id][I_TIME], WM_SETTEXT, (WPARAM)0, (LPARAM)message);
			}
			delete[] message;
		}
	}
}

// update repetition counter
void dlg_update_count(void) {
	int num, n;
	char* message;
	num = _scprintf("%u", tot_runs);
	if (num > 0) {
		message = new char[((size_t)num) + 1];
		if (message) {
			n = sprintf_s(message, ((size_t)num) + 1, "%u", tot_runs);
			if (n == num) {
				SendDlgItemMessageA(dlg_hWnd, ID_REPS, WM_SETTEXT, (WPARAM)0, (LPARAM)message);
			}
			delete[] message;
		}
	}
}

// update full status for all boards
// this can be called from main thread or from dlg_thread!
// lock must be already locked
int dlg_update_status(void) {
	int err = 0, num, n;
	struct board_info *bd;
	char *message;
	// acquire lock
	if (LOCK_ERROR(lock)) err = ERROR_LOCK;
	else {
		// ensure all boards are initialized, threads are running and queues are accessible
		if (!boards) err = ERROR_THREADS;
		else {
			// get status of all boards
			for (bd = boards, n = 0; bd != NULL; bd = bd->next) {
				if (!bd->ignore) {
					bd->send_queue->add(new thread_cmd(SERVER_GET_STATUS_FULL, (void*)NULL), PRIORITY_NORMAL);
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
							else if ((cmd->cmd != SERVER_GET_STATUS_FULL) || (cmd->data.ptr == NULL)) err = ERROR_UNEXPECTED;
							else if (((struct client_status_full *)cmd->data.ptr)->cmd != SERVER_RSP_STATUS_FULL) err = ERROR_UNEXPECTED;
							else {
								// status received
								struct FPGA_status *status = &((struct client_status_full *)cmd->data.ptr)->status;
								// convert to text
								num = _scprintf(FMT_FULL_STATUS,
									status->ctrl_DMA, status->ctrl_FPGA,
									status->ctrl_trg, status->ctrl_out,
									status->period_in, status->period_out, status->period_bus,
									status->strb_delay, status->clk_div,
									status->sync_delay, status->sync_phase,
									status->status_RX, status->status_TX, status->status_FPGA.status,
									status->set_samples, status->status_FPGA.board_time,
									status->board_samples_ext, status->board_time_ext,
									status->sync_time,
									status->FPGA_temp / 1000, status->FPGA_temp % 1000,
									status->phase_ext, status->phase_det,
									status->err_TX, status->err_RX, status->err_TX,
									status->irq_TX, status->irq_RX, status->irq_FPGA,
									status->irq_num,
									status->TX_bt_tot, status->RX_bt_tot, status->bt_tot,
									status->dsc_TX_p, status->dsc_TX_a, status->dsc_TX_c,
									status->dsc_RX_p, status->dsc_RX_a, status->dsc_RX_c, 
									status->RD_bt_max, status->RD_bt_act, status->RD_bt_drop,
									status->reps_set, status->reps_act,
									status->timeout,
#if DIO_BYTES_PER_SAMPLE == 8
									status->last_sample.data32[0], status->last_sample.data32[1],
#else
									status->last_sample.data32[0], status->last_sample.data32[1], status->last_sample.data32[2],
#endif
									status->last_sample.data32[0],
									DIO_BYTES_PER_SAMPLE,
									status->status_info.version>>24, (status->status_info.version >> 16) & 0xff, (status->status_info.version >> 9) & 0x7f, (status->status_info.version >> 5) & 0xf, status->status_info.version & 0x1f,
									((status->status_info.info & 0xff) == 0xc0) ? "Cora-Z7-07S" : ((status->status_info.info & 0xff) == 0xc1) ? "Cora-Z7-10" : ((status->status_info.info & 0xff) == 0xa1) ? "Arty-Z7-10" : ((status->status_info.info & 0xff) == 0xa2) ? "Arty-Z7-20" : "unknown"
								);
								if (num > 0) {
									message = new char[((size_t)num) + 1];
									if (message) {
										n = sprintf_s(message, ((size_t)num) + 1, FMT_FULL_STATUS,
											status->ctrl_DMA, status->ctrl_FPGA,
											status->ctrl_trg, status->ctrl_out,
											status->period_in, status->period_out, status->period_bus,
											status->strb_delay, status->clk_div,
											status->sync_delay, status->sync_phase,
											status->status_RX, status->status_TX, status->status_FPGA.status,
											status->set_samples, status->status_FPGA.board_time,
											status->board_samples_ext, status->board_time_ext,
											status->sync_time,
											status->FPGA_temp / 1000, status->FPGA_temp % 1000,
											status->phase_ext, status->phase_det,
											status->err_TX, status->err_RX, status->err_TX,
											status->irq_TX, status->irq_RX, status->irq_FPGA,
											status->irq_num,
											status->TX_bt_tot, status->RX_bt_tot, status->bt_tot,
											status->dsc_TX_p, status->dsc_TX_a, status->dsc_TX_c,
											status->dsc_RX_p, status->dsc_RX_a, status->dsc_RX_c,
											status->RD_bt_max, status->RD_bt_act, status->RD_bt_drop,
											status->reps_set, status->reps_act,
											status->timeout,
#if DIO_BYTES_PER_SAMPLE == 8
											status->last_sample.data32[0], status->last_sample.data32[1],
#else
											status->last_sample.data32[0], status->last_sample.data32[1], status->last_sample.data32[2],
#endif
											status->last_sample.data32[0],
											DIO_BYTES_PER_SAMPLE,
											status->status_info.version >> 24, (status->status_info.version >> 16) & 0xff, (status->status_info.version >> 9) & 0x7f, (status->status_info.version >> 5) & 0xf, status->status_info.version & 0x1f,
											((status->status_info.info & 0xff) == 0xc0) ? "Cora-Z7-07S" : ((status->status_info.info & 0xff) == 0xc1) ? "Cora-Z7-10" : ((status->status_info.info & 0xff) == 0xa1) ? "Arty-Z7-10" : ((status->status_info.info & 0xff) == 0xa2) ? "Arty-Z7-20" : "unknown"
											);
										if (n == num) {
											SendDlgItemMessageA(dlg_hWnd, ctrls[bd->id][I_STATUS_FULL], WM_SETTEXT, (WPARAM)0, (LPARAM)message);
										}
										delete[] message;
									}
								}
								delete cmd->data.ptr;
							}
							delete cmd;
						}
					}
				}
			}
		}
		// release lock 1x and ensure is still locked
		if (LOCK_RELEASE(lock) != 1) err = ERROR_LOCK_2;
	}
	if (err) show_error(err, "GET_STATUS_FULL"); // display error
	return err;
}


// reset all boards
// this can be called from main thread or from dlg_thread!
// lock must be already locked
int dlg_reset(void) {
	int err = 0, n;
	struct board_info *bd;
	// acquire lock
	if (LOCK_ERROR(lock)) err = ERROR_LOCK;
	else {
		// ensure all boards are initialized, threads are running and queues are accessible
		if (!boards) err = ERROR_THREADS;
		else {
			// get status of all boards
			for (bd = boards, n = 0; bd != NULL; bd = bd->next) {
				if (!bd->ignore) {
					bd->send_queue->add(new thread_cmd(SERVER_RESET, (void*)NULL), PRIORITY_NORMAL);
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
		// release lock 1x and ensure is still locked
		if (LOCK_RELEASE(lock) != 1) err = ERROR_LOCK_2;
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
	int error = 0;
	LRESULT result = 0;
	int num, n;
	char* message;
	const char *_fmt = (status == STATUS_NONE) ? __fmt[0] : __fmt[1];
	// generate format string
	if (fmt) {
		error = LB_ERR;
		_fmt = (status == STATUS_NONE) ? __fmt[2] : __fmt[3];
		num = _scprintf(_fmt, fmt);
		if (num > 0) {
			message = new char[((size_t)num) + 1];
			if (message) {
				n = sprintf_s(message, ((size_t)num) + 1, _fmt, fmt);
				if (n == num) {
					_fmt = message;
					error = 0;
				}
			}
		}
	}
	// generate string
	if (error == 0) {
		if (status == STATUS_NONE) {
			if (fmt) num = _scprintf(_fmt, cmd2str[cmd], data);
			else num = _scprintf(_fmt, cmd2str[cmd]);
		}
		else {
			if (fmt) num = _scprintf(_fmt, cmd2str[cmd], data, status2str[status]);
			else num = _scprintf(_fmt, cmd2str[cmd], status2str[status]);
		}
		if (num > 0) {
			message = new char[((size_t)num) + 1];
			if (message) {
				if (status == STATUS_NONE) {
					if (fmt) n = sprintf_s(message, ((size_t)num) + 1, _fmt, cmd2str[cmd], data);
					else n = sprintf_s(message, ((size_t)num) + 1, _fmt, cmd2str[cmd]);
				}
				else {
					if (fmt) n = sprintf_s(message, ((size_t)num) + 1, _fmt, cmd2str[cmd], data, status2str[status]);
					else n = sprintf_s(message, ((size_t)num) + 1, _fmt, cmd2str[cmd], status2str[status]);
				}
				if (n == num) {
					result = SendDlgItemMessageA(dlg_hWnd, ctrls[bd->id][I_LIST], LB_ADDSTRING, (WPARAM)0, (LPARAM)message);
				}
				delete[] message;
			}
		}
		// if list is too long delete first list entry
		if (result >= LIST_MAX) {
			SendDlgItemMessageA(dlg_hWnd, ctrls[bd->id][I_LIST], LB_DELETESTRING, (WPARAM)0, (LPARAM)0L);
			--result;
		}
		// show last item in list
		if (SendDlgItemMessage(dlg_hWnd, ctrls[bd->id][I_ASCROLL], BM_GETCHECK, (WPARAM)0, (LPARAM)0) == BST_CHECKED) {
			SendDlgItemMessageA(dlg_hWnd, ctrls[bd->id][I_LIST], LB_SETTOPINDEX, (WPARAM)result, (LPARAM)0);
		}
		// delete format string
		if (fmt) delete _fmt;
	}
	return error;
}

////////////////////////////////////////////////////////////////////////////////////////
// helper functions executed by main applicaton thread
////////////////////////////////////////////////////////////////////////////////////////

// display error in message box (dialog window is parent window)
void show_error(int error, const char *cmd) {
	int n, num = _scprintf("error %d in %s", error, cmd);
	if (num > 0) {
		char *message = new char[((size_t)num) + 1];
		if (message) {
			n = sprintf_s(message, ((size_t)num) + 1, "error %d in %s", error, cmd);
			if (n == num) {
				MessageBoxA(dlg_hWnd, message, DLL_INFO, MB_ICONEXCLAMATION | MB_OK);
			}
			delete[] message;
		}
	}
}

#define STATUS_MSG	"%d boards [%d,%d] id [%d,%d]: ignore [%d,%d], result %d"

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
		char *message = new char[((size_t)num) + 1];
		if (message) {
			n = sprintf_s(message, ((size_t)num) + 1, STATUS_MSG, i, board[0], board[1], id[0], id[1], ignore[0], ignore[1], result);
			if (n == num) {
				MessageBoxA(NULL, message, info, MB_OK);
			}
			delete[] message;
		}
	}
}

// init dialog window and windows sockets 2 if not already done
// returns 0 if ok, otherwise error.
int init_dlg(void) {
	int err = ERROR_THREADS;
	if (wsa_data == NULL) {
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
					if (dlg_thread_hdl) {
						// wait until dialog box is displayed
						WaitForSingleObject(hStartup, INFINITE);
						// ok
						err = 0;
					}
					else {
						CloseHandle(hStartup);
						hStartup = INVALID_HANDLE_VALUE;
					}
				}
			}
		}
		if (err) {
			delete wsa_data;
			wsa_data = NULL;
			wsa_startup = -1;
		}
	}
	return err;
}

// close dialog window and reset windows sockets 2
void close_dlg(void) {

	// close dialog window
	if (dlg_hWnd) {
		// send WM_DESTROY message which closes dialog box and dialog thread
		// we cannot call DestroyWindow because this must be called from same thread which created dialog box
		// dlg_hWnd is reset by thread
		// we check below that thread is closed
		SendMessage(dlg_hWnd, WM_DESTROY, 0, 0L);
	}

	// wait until dialog thread closed
	if (dlg_thread_hdl) {
		WaitForSingleObject(dlg_thread_hdl, INFINITE);
		dlg_thread_hdl = NULL;
	}

	// cleanup Windows sockets 2.0
	if (wsa_data) {
		WSACleanup();
		wsa_startup = -1;
		delete wsa_data;
		wsa_data = NULL;
	}
}

WORD get_board_handle(struct board_info *bd) {
	// calculate board handle from thread handle, thread id and user-provided board ID
	// this should be fairly random and unique across operating system.
	// note: to avoid warnings about pointer truncation we have to convert it into an integer of proper size then we can truncate.
#ifdef _WIN64
	DWORD dw = (DWORD) reinterpret_cast<uint64_t>(bd->thread_hdl);
#else
	DWORD dw = (DWORD) reinterpret_cast<uint32_t>(bd->thread_hdl);
#endif
	return ((WORD)(dw >> 16)) ^ ((WORD)dw) ^ ((WORD)bd->thread_id) ^ (bd->board);
}

// create new board and adds to list of boards
// init thread, sockets and board_info structure
// on success returns new board_info structure, otherwise NULL. call exit_thread
// use close_board to close the created board
// Attention: lock must be owned!
struct board_info* create_board(void) {
	int err = 0;
	thread_cmd *cmd;
	struct board_info *bd = NULL;

	if (boards == NULL) {
		// init dialog box. this also creates hStartup event which we use here.
		err = init_dlg();
		if (err) return NULL;
	}
	
	// create board info structure
	bd = new struct board_info;
	if (bd) {
		ZEROMEMORY(bd, sizeof(struct board_info));
		bd->board = BOARD_NONE; // mark as unused

		// insert new board into list of boards
		if (boards == NULL) {
			// first board
			boards = bd;
			boards_num = 1;
			bd->id = 0;
		}
		else if (boards->id > 0) {
			// insert board as first one
			bd->next = boards;
			bd->id = 0;
			boards = bd;
			++boards_num;
		}
		else {
			// insert board at proper place in list
			// we require that board id (= order of board tabs) is incrementing
			// so new boards are inserted with order of appearence before/after already existing boards.
			// if the boards are always openend in the same order this maintains the same order,
			// even if one or several boards have been closed and later re-opened while some boards remained open.
			// in case all boards have been closed the dialog box has been closed as well and we start anyway from zero.
#ifdef _DEBUG
			bd->id = BOARD_NONE;
#endif
			int i = 1;
			board_info* tmp = boards;
			for (; tmp->next != NULL; ++i) {
				if (i < tmp->next->id) {
					// insert board between boards tmp and tmp->next
					bd->next = tmp->next;
					bd->id = i;
					tmp->next = bd;
					break;
				}
				tmp = tmp->next;
			}
			if (i > tmp->id) {
				// insert board after last board
				tmp->next = bd;
				bd->id = i;
			}
			boards_num++;
#ifdef _DEBUG
			// ensure board was inserted
			if (bd->id == BOARD_NONE) {
				printf("\ncreate_board error: board not insered!\n\n");
				delete bd;
				return NULL;
			}
			// ensure boards are sorted with increasing id
			tmp = boards->next;
			int n = 1;
			for (i = boards->id + 1; tmp != NULL; tmp = tmp->next, ++n) {
				if (tmp->id < i) {
					printf("\ncreate_board error: boards not sorted!\n\n");
					delete bd;
					return NULL;
				}
				i = tmp->id + 1;
			}
			// ensure correct board number
			if (n != boards_num) {
				printf("\ncreate_board error: # boards %d != %d!\n\n", n, boards_num);
				delete bd;
				return NULL;
			}
#endif
		}

		// start thread: this will allocate queues and set startup event
		err = ERROR_THREADS;
		bd->thread_hdl = CreateThread(NULL, 0, board_thread, (LPVOID)bd, 0, &bd->thread_id);
		if (bd->thread_hdl) {
			// init board handle from thread handle and id. should be fairly 'random' and unique across OS.
			bd->board_hdl = get_board_handle(bd);
				
			// wait until thread sets startup event (before we cannot access queues)
			WaitForSingleObject(hStartup, INFINITE);
			// now queues are valid and we get startup run bit
			cmd = bd->recv_queue->remove(INFINITE); // this cannot timeout and must always return nonzero cmd
			if (cmd->data.u32 == 1) {
				err = 0;
			}
			// delete command. cannot be NULL.
			delete cmd;
		}

		if (err) {
			// an error occurred: delete board and remove from list of boards
			if (bd == boards) boards = bd->next;
			else {
				struct board_info *tmp = boards;
				while (tmp->next != bd) tmp = tmp->next;
				tmp->next = bd->next;
			}
			delete bd;
			bd = NULL;
			--boards_num;
		}
	}
	//report_status("init_threads",err);
	return bd;
}

// closes board and removes from list of boards
// when last board is closed resets also Windows Sockets 2
// if send_close == true sends SERVER_CMD_CLOSE to board before THREAD_EXIT, and waits for responds
// if send_close == false and bd->thread_hdl != NULL sends only THREAD_EXIT and does not wait for responds
// Attention: acquire lock before!
// note: this is called only from board_thread THREAD_EXIT command!
int close_board(struct board_info *bd) {
	int err = 0;
	struct board_info* tmp;
	if (!boards) err = ERROR_THREADS;
	else {
		// remove board from list of boards
		if (bd == boards) boards = bd->next;
		else {
			tmp = boards;
			while (tmp->next != bd) tmp = tmp->next;
			tmp->next = bd->next;
		}

		// delete board
		if (bd->IP_port) { delete[] bd->IP_port; bd->IP_port = NULL; }
		delete bd;
		--boards_num;

		// if last board close dialog box and windows sockets 2
		if (boards == NULL) {
			close_dlg();
			boards_linked = false;
		}
	}

	// return error from last communication of thread
	return err;
}

// send a command and data to board and wait for responds
// this removes all old entries from recv_queue until scmd is received
// we ignore timeout here to be sure boards have executed scmd for sure
// if flags & DO_SEND == 0 then does not send scmd but only waits for responds, 
// if flags & DO_SEND != 0 then sends scmd with given data befor waiting for responds.
// if flags & CHECK_ERROR != 0 returns 0 if all commands in queue and scmd returned STATUS_ACK or STATUS_ACTIVE
// if flags & CHECK_ERROR == 0 returns 0 if scmd returned STATUS_ACK or STATUS_ACTIVE, other errors are ignored.
// if flags & FORCE != 0 sends commands even if ignore flag is set. this is used by DIO64_Close.
// on error returns first error responds status
// Attention: acquire lock before!
#define DO_SEND			1
#define CHECK_ERROR		2
#define FORCE			4
int send_cmd_and_clean(WORD board, int n, SERVER_CMD scmd, void *data, unsigned flags) {
	int err = 0;
	struct board_info* bd;

	// get board info
	bd = find_board(board, n);
	if (bd == NULL) err = ERROR_FIND_BOARD;
	else if ((!bd->ignore) || (flags & FORCE)) {
		// send command
		if (flags & DO_SEND) {
			bd->send_queue->add(new thread_cmd(scmd, data), PRIORITY_NORMAL);
		}
		// wait for responds 
		while (true) {
			thread_cmd* cmd = bd->recv_queue->remove(THREAD_TIMEOUT);
			if (cmd) { // on timeout we get NULL, which we ignore here
				if (cmd->cmd == SERVER_CMD_OUT_STATUS) {
					// delete data only if from SERVER_CMD_OUT_STATUS
					if (cmd->data.ptr) delete cmd->data.ptr;
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
				if (flags & CHECK_ERROR) {
					// check if any command with error (but do not abort on error)
					if ((cmd->status != STATUS_ACK) && (cmd->status != STATUS_ACTIVE) && (!err)) err = cmd->status;
				}
				delete cmd;
			}	// get next command
		}
	}
	return err;
}

////////////////////////////////////////////////////////////////////////////////////////
// DIO64 public functions
////////////////////////////////////////////////////////////////////////////////////////

// connect to board with given IP:port address.
// resourceName = "IP:port" of board
// board = user selected board ID. cannot be BOARD_NONE. use same board ID in successive calls. 
// baseio if 0 or BASE_IO_DEFAULT ignored, otherwise number of linked boards with incremented IP address.
//   in this case all commands are executed automatically by all linked boards. 
//   DIO64_OpenResource with baseio non-default can be called only once except to re-open closed boards.
// define IP_PORT_SEPARATOR for definition of separator between IP and port strings
// call DIO64_Close to close board if returns >0
// returns >0 if ok, otherwise error. if >0 LOWORD returned value must be used as 'board' in all further calls. 
// returns ERROR_CONNECT_IGNORE if user selected "Ignore" upon connection error. TODO: test! will be only returned on sec. board and not prim?
extern "C"
int DLLEXPORT DIO64_OpenResource(char* resourceName, WORD board, WORD baseio) {
	int err = 0, id = 0, num = 0, num_boards, n;
	struct board_info *bd = NULL;
	thread_cmd *cmd;
	bool re_open = false;
	char* IP_port;
	int port_offset;
	WORD board_handle = BOARD_NONE;

	num_boards = ((baseio == 0) || (baseio == BASE_IO_DEFAULT)) ? 1 : baseio;

	// check input arguments. we check baseio later when we know if board was re-opened
	if ((resourceName == NULL) || (board == BOARD_NONE) ||		// illegal pointer or board number
		(num_boards < 1) || (num_boards > MAX_NUM_BOARDS) 		// number of boards outside range
		) {
		if (resourceName == NULL) err = ERROR_ARGS - 1;
		else if (board == BOARD_NONE) err = ERROR_ARGS - 2;
		else if (num_boards < 1) err = ERROR_ARGS - 2;
		else if (num_boards > MAX_NUM_BOARDS) err = ERROR_ARGS - 3;
		else err = ERROR_ARGS -4;
	}
	else {
		// acquire lock
		if (LOCK_OPEN(lock)) {
			err = ERROR_LOCK;
		}
		else {
			for (n = 0; n < num_boards; ++n) {
				// get a copy of resource name (incremented if baseio not default) and index of port string
				IP_port = get_IP(resourceName, n, &port_offset);
				
				// check if the same board IP:port was closed before
				// note: board = BOARD_NONE for closed boards until board thread terminates and removes it from boards list.
				//       board threads and all functions here must use lock to ensure consistency of boards list.
				//       since we own lock when we find closed board, we can be sure that board thread still is running!
				//       board thread will wait CLOSE_TIMEOUT ms before exiting but first it will aquire lock and check if board != BOARD_NONE. 
				//       in this case it will continue running serving the re-opened board.
				//       otherwise it will remove board from boards list, release lock and exit.
				// note: if a board cannot be connected, the error can be ignored by the user and the flag bd->ignore = true is set.
				//       these boards remain in list and thread is still active but no attempt will be made to send data to the board. 
				//       these boards can be closed and re-connected as normal boards. this is useful for testing when a board is not available.
				//       keeping the thread active makes things easier, otherwise when all boards have been closed, 
				//       the last thread has to check if ignored boards are around, or exit_all() must be called mandatory, which we want to avoid.
				bd = boards;
				while (bd) {
					if (strcmp(IP_port, bd->IP_port) == 0) {
						// board found in list of boards
						if (bd->board == BOARD_NONE) {
							// closed board was re-opened. 'board' might be different though.
							re_open = true;
							bd->board = board + n;
							if (!bd->ignore) {
								// send re-open command = reset board.
								bd->send_queue->add(new thread_cmd(SERVER_CMD_OPEN_RESOURCE, (void*)NULL), PRIORITY_NORMAL);
								// for first connection we show active command
								dlg_add(bd, SERVER_CMD_OPEN_RESOURCE, STATUS_ACTIVE, NULL, 0);
							}
						}
						else {
							// tried to re-open board which was not closed
							err = ERROR_ALREADY_OPEN;
						}
						break;
					}
					bd = bd->next;
				}

				if (err) { // on error IP_port can be deleted
					delete[] IP_port;
					IP_port = NULL;
				}
				else {
					// if board not re-openend, create board and add to list of boards
					if (bd == NULL) {
						// check if function called more than once with not default baseio
						if ((n == 0) && (boards != NULL) && ((num_boards != 1) || boards_linked)) err = ERROR_ARGS-9;
						else if ( ((boards == NULL) && (boards_num != 0)) || 
							      ((boards != NULL) && (boards_num == 0)) ) err = ERROR_UNEXPECTED; // consistency check
						else {
							// link boards if baseio gives number of boards
							boards_linked = (num_boards == 1) ? false : true;
							bd = create_board();
							if (bd == NULL) err = ERROR_THREADS;
							else {
								// save handle of first board
								if (boards_num == 1) boards_prim = bd->board_hdl;
								// save user board ID
								bd->board = board + n;
								// connect to board
								// if connection fails a message box appears asking for user action
								// if user selects "ignore" no further connection will be attempted
								// check if board ID is already used and return first unused board with set board and id
								bd->IP_port = IP_port;
								bd->port_offset = port_offset;
								bd->send_queue->add(new thread_cmd(SERVER_CMD_OPEN_RESOURCE, (void*)NULL), PRIORITY_NORMAL);
								// for first connection we show active command
								dlg_add(bd, SERVER_CMD_OPEN_RESOURCE, STATUS_ACTIVE, NULL, 0);

								// display IP address
								dlg_update();
							}
						}
					}
					else { 
						// board re-opened: check if called with same baseio
						if ( (n == 0) && ((boards_linked && (num_boards == 1)) || ((!boards_linked) && (num_boards != 1))) ) {
							err = ERROR_ARGS;
							bd = NULL;
						}
						// IP_port not needed
						delete[] IP_port;
						IP_port = NULL;
					}

					if (bd != NULL) {

						// save board handle
						if (boards_linked) {
							// linked boards: return only handle of primary board
							if (n == 0) board_handle = bd->board_hdl;
						}
						else {
							// not linked boards: return board handle of individual board
							board_handle = bd->board_hdl;
						}

						// get responds. this might take a long time on error until user decides what to do (e.g. 'Ignore')
						if (re_open) {
							// re-opening an already closed board: 
							//   board thread might be waiting for lock in THREAD_EXIT
							//   therefore, we have to release lock during waiting for responds.
							//   the board thread will find the bd->board != BOARD_NONE and abort closing,
							//   and respond to SERVER_CMD_OPEN_RESOURCE.
							// update: lock_count can only be 1. multiple locks are not anymore possible.
#ifdef _DEBUG
							if (lock_count != 1) {
								printf("\nerror lock_count %d != 1\n\n", lock_count);
							}
#endif
							LOCK_RELEASE(lock);

							cmd = bd->recv_queue->remove(INFINITE);
							
							LOCK_OPEN_WAIT(lock);
#ifdef _DEBUG
							if (lock_count != 1) {
								printf("\nerror lock_count %d != 1\n\n", lock_count);
							}
#endif
						}
						else {
							cmd = bd->recv_queue->remove(INFINITE);
						}
						dlg_add(bd, SERVER_CMD_OPEN_RESOURCE, cmd ? cmd->status : STATUS_ERECV, NULL, 0);
						if (cmd == NULL) err = ERROR_RECV_2; // note: with timeout INFINITE cannot happen!
						else {
							if ((cmd->status == STATUS_ACK) || (cmd->status == STATUS_ACTIVE)) ++num; // ok
							else {
								// connection not ok
								if (cmd->status == STATUS_IGNORE) {
									// error but user decided to ignore it. keep thread around but do not attempt to send data to board.
									bd->ignore = true;
									err = ERROR_CONNECT_IGNORE;
								}
								else {
									if (cmd->status == STATUS_ABORT) {
										// error but user decided to abort it.
										err = ERROR_CONNECT_ABORT;
									}
									else {
										// connection failed due to other reason
										//bd->board = BOARD_NONE; // indicates that board should be closed. TODO: I think this does not work with RECOVER_HDL_ON_CLOSE
										err = ERROR_CONNECT;
										//else err = cmd->status; // return unexpected status for more information on cause of error.
									}
									// exit thread and delete board as soon as lock is released
									// update: this is done in loop below
									//bd->send_queue->add(new thread_cmd(THREAD_EXIT, (void*)NULL), PRIORITY_NORMAL);
								}
							}
							delete cmd;
						}
					}
				}
				// update dialog box
				dlg_update();
				// stop on error, except when user selected 'Ignore'
				if ((err != 0) && (err != ERROR_CONNECT_IGNORE)) {
					// close all already opened boards
					for (bd = boards; bd != NULL; bd = bd->next) {
						// exit thread and delete board as soon as lock is released (no timeout)
						bd->board = BOARD_NONE; // force closing of all boards. TODO: I think RECOVER_HDL_ON_CLOSE will not work with this reset.
						bd->send_queue->add(new thread_cmd(THREAD_EXIT, (void*)NULL), PRIORITY_NORMAL);
					}
					break;
				}
			} // next board
			// release lock
			LOCK_RELEASE(lock);
		}
	}
	//report_status("OpenResource", err);

	// return <0 on error, otherwise board handle
	return (err != 0) ? err : (int) board_handle;
}

// Open connection to master board. 
// baseio if 0 or BASE_IO_DEFAULT ignored, otherwise number of linked boards with incremented IP address.
//   in this case all commands are executed automatically by all linked boards. 
//   DIO64_Open with baseio non-default can be called only once.
// function uses hard coded IP_PORT (defined in Dio24.h) with the last number in IP address added with 'board'
// this allows to change IP address with different board id's.
// for more flexibility use OpenResource where you can give directly an IP address and port
// see OpenResource for more details and return values.
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
// note: at the moment does not do much and does not send data to server
// TODO: the rbfFile argument could be used to assign device addresses to a board.
extern "C"
int DLLEXPORT DIO64_Load(WORD board, char *rbfFile, int intputHint, int outputHint) {
	int err = 0, n, boards_num_linked = (boards_linked) ? boards_num : 1;
	struct board_info *bd;
	// acquire lock
	if (LOCK_OPEN(lock)) err = ERROR_LOCK;
	else {
		if (!boards) err = ERROR_THREADS;
		else {
			// check arguments
			if ((!((intputHint == 0) || (intputHint == -1))) || (!((outputHint == 4) || (outputHint == -1)))) err = ERROR_ARGS;
			else {
				for (n = 0; n < boards_num_linked; ++n) {
					// get board info
					bd = find_board(board, n);
					if (bd == NULL) err = ERROR_FIND_BOARD;
					else if (!bd->ignore) {
						dlg_add(bd, SERVER_CMD_LOAD, STATUS_NONE, NULL, 0);
					}
				}
			}
		}
		// release lock
		LOCK_RELEASE(lock);
	}
	return err;
}

// close board
// returns 0 if board will be closed, otherwise error
// note: since the LabWindows/CVI program of Yb is opening and closing up to 2x per cycle the boards (!)
//       thread only closes the connection and exits if board is not re-connected within CLOSE_TIMEOUT ms.
extern "C"
int DLLEXPORT DIO64_Close(WORD board) {
	int err = 0, n, boards_num_linked = (boards_linked) ? boards_num : 1;
	struct board_info *bd;
#ifdef RECOVER_HDL_ON_CLOSE
	bool recover_hdl = false;
#endif
	// acquire lock
	if (LOCK_OPEN(lock)) err = ERROR_LOCK;
	else {
		if (!boards) err = ERROR_THREADS;
		else {
			for (n = 0; n < boards_num_linked; ++n) {
				// find board
				bd = find_board(board, n);
				if (bd == NULL) {
					err = ERROR_FIND_BOARD;
#ifdef RECOVER_HDL_ON_CLOSE
					// recover last board handle to allow closing of boards even on serious error.
					if (n == 0) {
						bd = find_board(board, n, true);
						if (bd) {
							board = bd->board_hdl;
							err = 0;
							recover_hdl = true;
						}
					}
#endif
				}
				if (!err) {
					// send close command with timeout, remove remaining STATUS commands and wait for STATUS_ACTIVE of SERVER_CMD_CLOSE
					err = send_cmd_and_clean(board, n, SERVER_CMD_CLOSE, (void*)CLOSE_TIMEOUT, DO_SEND | CHECK_ERROR | FORCE);
					// mark board as closed. do it after send_cmd_and_clean, otherwise find_board will not find board.
					bd->board = BOARD_NONE;
				}
				// update dialog box
				//dlg_update();
			} // next board
		}
		LOCK_RELEASE(lock);
	}
	//report_status("Close", err);
#ifdef RECOVER_HDL_ON_CLOSE
	if ((!err) && recover_hdl) err = ERROR_FIND_BOARD_2;
#endif
	return err;
}

// note: in Labview defined with "*attrID" but returns error -12 (Invalid parameter)
extern "C"
int DLLEXPORT DIO64_GetAttr(WORD board, DWORD attrID, DWORD *value) {
	return ERROR_NOT_IMPLEMENTED;
}

// note: with DIO64 driver for Win7 (beta) we had to call this function to set to interrupt mode.
//       this is not needed here anymore and any call will return ERROR_NOT_IMPLEMENTED.
extern "C"
int DLLEXPORT DIO64_SetAttr(WORD board, DWORD attrID, DWORD value) {
	return ERROR_NOT_IMPLEMENTED;
	//return 0;
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
// for primary board:
//    DIO64_Open/DIO64_OpenResource must be called before secondary boards
//    optionally you can select external clock (default 10MHz) and external trigger (not implemented)
// for secondary boards:
//    DIO64_Open/DIO64_OpenResource must be called after primary board
//    external clock is automatically selected, trigger is from sync_in and not from external trigger.
// NI LabWindows/CVI configuration board=0,ticks=0,
//                                mask={ffff,ffff,ffff,ffff}, maskLength=4,
//                                flags=0,clkControl=DIO64_CLK_INTERNAl,
//								  startType=0,startSource=DIO64_STRT_INTERNAL,
//                                stopType=0,stopSource=DIO64_STOP_NONE,
//                                AIControl=DIO64_AI_NONE,
//                                reps=ncycl*cyclsw,ntrans=(N+1)*cyclsw with cyclsw=0/1 to enable repetitions
//								  scanRate=&srate with srate = 1.0e6
// note:
//  - external triggers:
//	startSource = DIO64_STRT_NONE (0): no trigger, DIO64_STRT_EXTERNAL (1): ext_in[0], DIO64_STRT_EXTERNAL+1 (2): ext_in[1], DIO64_STRT_EXTERNAL+2 (3): ext_in[2]
//	startType = DIO64_STRTTYPE_ | DIO64_TRIG_ constants. DIO_STRTYPE_LEVEL | DIO64_TRIG_RISING = low level and DIO_STRTYPE_LEVEL | DIO64_TRIG_FALLING = high level
//              DIO64_STRTTYPE_EDGETOEDGE is special and defines that start/stop/restart trigger are all triggered on the same edge of the same signal.
//              if a secondary board is configured then the secondary board ext_in[1] (on v1.2 board labelled trg_stop) is used for the stop and restart trigger,
//              since ext_in[0] is used for the start trigger from the primary board.
//  stopSource = DIO64_STOP_NONE (0): no trigger, DIO64_STOP_EXTERNAL (1): ext_in[0], DIO64_STRT_EXTOPNAL+1 (2): ext_in[1], DIO64_STOP_EXTERNAL+2 (3): ext_in[2]
//              as soon as a stop trigger is programmed also a start trigger is programmed the same as the start trigger.
//              for secondary board stopSource is ignored and always ext_in[1] (on v1.2 board labelled trg_stop) is used.
//              if startType = DIO64_STRTTYPE_EDGETOEDGE no stop trigger is allowed since will be automatically programmed.
//  stopType = DIO64_STOPTYPE_EDGE | DIO64_TRIG_RISING = rising edge or DIO_STOPTYPE_EDGE | DIO64_TRIG_FALLING = falling edge.
//             from the DIO manual the defintion of rising/falling is opposite to this but I keep it the same as for startType.
//  the boards would accept more options but not all are implemented due to the restrictions coming from the DLL and for compatibility to the old version.
//  ATTENTION: 
//  - edge triggereing is preferred to level trigger.
//  - when using the same external trigger signal on different inputs use alternating edges, otherwise trigger signals might get lost!
//    this is not a bug but happens when small delays coming from cables and different propagation time of the inputs
//    cause that the trigger signals, although generated at the same time, are detected at different internal clock cycles
//	  and the board for example gets started in the first cycle and gets immediately stopped in the next cycle (typically 10ns later), and
//    the board seems to have never run since on the typical 1us bus clock output time scale nothing has happened.
//    one exception is the start trigger which should be usable with the same edge as another trigger on a different input,
//    when a secondary board is enabled, since then the internal auto-sync option is activated.  
//    in this case the start is delayed a few cycles (the sync_delay) which should avoid this issue. 
// note for Yb with LabWindows/CVI:
// - keep comiler switch DIO_BYTES_PER_SAMPLE = 8 (i.e. the default value).
// - call DIO64_Out_Config with maskLength=4 and mask={ffff,ffff,ffff,ffff}. 
//   this sets the config bits DIO_CTRL_BPS96 | DIO_CTRL_BPS96_BRD but the boards will not received them
//   and Out_Write will send the appropriate 8bytes/samples to each board (see next point).
// - call DIO64_Out_Write with 12bytes (96bits) per smaple for 2 boards. 
//   the board threads send only 8bytes per board, with the first 8bytes (time and data0) sent to the primary board 
//   and the first 4bytes (time) and the 9-12bytes (data1) to the secondary board. 
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
	int err = 0, n, boards_num_linked = (boards_linked) ? boards_num : 1;
	struct client_config *config;
#ifndef CONFIG_AUTO
	static const char *def_strb_delay[MAX_NUM_RACKS] = { ALL_STRB_DELAY_STR, ALL_STRB_DELAY_STR };
#endif
	int board_level = 0;	// 0 = single board, 1 = primary board, 2 = secondary board

	// input validation
	if (
		(flags != 0) || (ticks != 0) ||
		((maskLength != 0) && (maskLength != 2) && (maskLength != 4)) ||
		((clkControl != DIO64_CLCK_INTERNAL) && (clkControl != DIO64_CLCK_EXTERNAL)) ||
		//((startType != DIO64_STRTTYPE_LEVEL) && (startType != DIO64_STRTTYPE_EDGETOEDGE) && (startType != DIO64_STRTTYPE_EDGE)) ||
		//((startSource != DIO64_STRT_NONE) && (startSource != DIO64_STRT_EXTERNAL)) ||
		//((stopType != DIO64_STOPTYPE_EDGE)) ||
		//((stopSource != DIO64_STOP_NONE) && (stopSource != DIO64_STOP_EXTERNAL)) ||
		(AIControl != DIO64_AI_NONE) || (scanRate == NULL)
		) err = ERROR_ARGS;
	else if (((*scanRate) < BUS_OUT_MIN_HZ) || ((*scanRate) > BUS_OUT_MAX_HZ)) err = ERROR_ARGS;
	else {
		struct board_info *bd;
		// acquire lock
		if (LOCK_OPEN(lock)) err = ERROR_LOCK;
		else {
			if (!boards) err = ERROR_THREADS;
			else {
				for (n = 0; (n < boards_num_linked) && (!err); ++n) {
					// get board info
					bd = find_board(board, n);
					if (bd == NULL) err = ERROR_FIND_BOARD;
					else if (!bd->ignore) {
						// allocate configuration structure
						config = new struct client_config;
						if (config == NULL) err = ERROR_MEM;
						else {
							ZeroMemory(config, sizeof(struct client_config));
							// count number of ports: 2=64bits/samples, 4=96bits/samples
							// set config for correct bits/samples and set restart if reps != 0 or 1
							err = 0;
							uint32_t conf = 0, source = 0;
							if (maskLength == 0) {
								if (mask != NULL) err = ERROR_ARGS;
								else conf = 2;
							}
							else if (mask == NULL) err = ERROR_ARGS;
							else {
								for (int i = 0; i < maskLength; ++i) {
									if (mask[i] == 0xffff) ++conf;
									else if (mask[i] != 0) {
										err = ERROR_ARGS; break; // illegal mask: must be 0 or 0xffff
									}
								}
							}
#if ( DIO_BYTES_PER_SAMPLE == 8 )
							if ((conf != 2) && (conf != 4)) err = ERROR_ARGS;
#elif ( DIO_BYTES_PER_SAMPLE == 12 )
							if (conf != 4) err = ERROR_ARGS;
#else
							err = ERROR_UNEXPECTED;
#endif
							if (conf == 4) { // 12bytes/sample
								conf = ((reps == 0) || (reps == 1)) ? DLL_CONFIG_RUN_96 : DLL_CONFIG_RUN_RESTART_96;
								// TODO: at the moment the primary board gets first 8 data bytes and secondary board gets first 4 and last 4 data bytes
								//       it would be nice to allow selection by user.
							}
							else { // 8bytes/sample (default)
								conf = ((reps == 0) || (reps == 1)) ? DLL_CONFIG_RUN_64 : DLL_CONFIG_RUN_RESTART_64;
							}
							if (!err) {
								// if board is not first in list is automatically configured as secondary board
								if (bd == boards) {	// single board or primary board
									// if external clock is set set external clock bit if selected. external clock loss is always detected.
									if (clkControl == DIO64_CLCK_EXTERNAL) {
										conf |= (ignore_clock_loss) ? DIO_CTRL_EXT_CLK : DIO_CTRL_EXT_CLK | DIO_CTRL_ERR_LOCK_EN;
									}
									if (bd->next != NULL) { // set primary board bit (has no effect). DIO_CTRL_AUTO_SYNC_EN is needed for sync_delay.
										board_level = 1;
										conf |= DIO_CTRL_AUTO_SYNC_EN | DIO_CTRL_AUTO_SYNC_PRIM;
									}
								}
								else { // secondary board: enable external clock and auto sync
									board_level = 2;
									conf |= (ignore_clock_loss) ? DIO_CTRL_EXT_CLK | DIO_CTRL_AUTO_SYNC_EN : DIO_CTRL_EXT_CLK | DIO_CTRL_AUTO_SYNC_EN | DIO_CTRL_ERR_LOCK_EN;
#if ( DIO_BYTES_PER_SAMPLE == 8 )
									// for 12bytes: select send bytes 1-4 and 9-12, primary board gets bytes 1-8
									if (conf & DIO_CTRL_BPS96) conf |= DIO_CTRL_BPS96_BRD;
#endif
								}
								// set actual config
								config->cmd = SERVER_CMD_OUT_CONFIG;
								config->clock_Hz = BUS_CLOCK_FREQ_HZ;	// internal bus clock frequency in Hz
								config->scan_Hz = int(*scanRate);		// scan clock = bus output frequency in Hz
								config->config = conf;					// set configuration bits
								config->reps = (reps == 0) ? 1 : reps;	// set reps = 1 (0 = streaming mode)
								config->trans = 0;						// transitions (not used)
								// start trigger control
								if (board_level == 2) {					
									// secondary board: we use always default falling edge start trigger. 
									// TODO: - sync_out could be configured with rising edge and for some boards it might be inverted!
									config->ctrl_trg = ((CTRL_TRG_EDGE_FALLING << CTRL_TRG_SRC_BITS) | CTRL_TRG_SRC_IN0) << CTRL_TRG_DST_START;
									// if edge-to-edge trigger is enabled program 2nd input (trg_stop on v1.2 board) for stop and restart rising edge
									if ((startSource != DIO64_STRT_NONE) && (startType & DIO64_STRTTYPE_EDGETOEDGE)) {
										source = CTRL_TRG_SRC_IN1;
										if (startType == (DIO64_STRTTYPE_EDGETOEDGE | DIO64_TRIG_RISING)) { // rising edge
											config->ctrl_trg |= (((CTRL_TRG_EDGE_RISING << CTRL_TRG_SRC_BITS) | source) << CTRL_TRG_DST_STOP) |
																(((CTRL_TRG_EDGE_RISING << CTRL_TRG_SRC_BITS) | source) << CTRL_TRG_DST_RESTART);
										}
										else if (startType == (DIO64_STRTTYPE_EDGETOEDGE | DIO64_TRIG_FALLING)) { // falling edge
											config->ctrl_trg |= (((CTRL_TRG_EDGE_FALLING << CTRL_TRG_SRC_BITS) | source) << CTRL_TRG_DST_STOP) |
																(((CTRL_TRG_EDGE_FALLING << CTRL_TRG_SRC_BITS) | source) << CTRL_TRG_DST_RESTART);
										}
									}
								}
								else if (startSource != DIO64_STRT_NONE) { // external start trigger
									if      (startSource == (DIO64_STRT_EXTERNAL + 0)) source = CTRL_TRG_SRC_IN0;
									else if (startSource == (DIO64_STRT_EXTERNAL + 1)) source = CTRL_TRG_SRC_IN1;
									else if (startSource == (DIO64_STRT_EXTERNAL + 2)) source = CTRL_TRG_SRC_IN2;
									else err = ERROR_ARGS;
									if (startType == (DIO64_STRTTYPE_LEVEL | DIO64_TRIG_RISING)) { // level high
										config->ctrl_trg = ((CTRL_TRG_LEVEL_HIGH << CTRL_TRG_SRC_BITS) | source) << CTRL_TRG_DST_START;
									}
									else if (startType == (DIO64_STRTTYPE_LEVEL | DIO64_TRIG_FALLING)) { // level low
										config->ctrl_trg = ((CTRL_TRG_LEVEL_LOW << CTRL_TRG_SRC_BITS) | source) << CTRL_TRG_DST_START;
									}
									else if (startType == (DIO64_STRTTYPE_EDGE | DIO64_TRIG_RISING)) { // rising edge
										config->ctrl_trg = ((CTRL_TRG_EDGE_RISING << CTRL_TRG_SRC_BITS) | source) << CTRL_TRG_DST_START;
									}
									else if (startType == (DIO64_STRTTYPE_EDGE | DIO64_TRIG_FALLING)) { // falling edge
										config->ctrl_trg = ((CTRL_TRG_EDGE_FALLING << CTRL_TRG_SRC_BITS) | source) << CTRL_TRG_DST_START;
									}
									else if (startType == (DIO64_STRTTYPE_EDGETOEDGE | DIO64_TRIG_RISING)) { // rising edge start/stop/restart trigger
										config->ctrl_trg = (((CTRL_TRG_EDGE_RISING << CTRL_TRG_SRC_BITS) | source) << CTRL_TRG_DST_START) |
														   (((CTRL_TRG_EDGE_RISING << CTRL_TRG_SRC_BITS) | source) << CTRL_TRG_DST_STOP ) |
														   (((CTRL_TRG_EDGE_RISING << CTRL_TRG_SRC_BITS) | source) << CTRL_TRG_DST_RESTART);
									}
									else if (startType == (DIO64_STRTTYPE_EDGETOEDGE | DIO64_TRIG_FALLING)) { // falling edge start/stop/restart trigger
										config->ctrl_trg = (((CTRL_TRG_EDGE_FALLING << CTRL_TRG_SRC_BITS) | source) << CTRL_TRG_DST_START) |
														   (((CTRL_TRG_EDGE_FALLING << CTRL_TRG_SRC_BITS) | source) << CTRL_TRG_DST_STOP ) |
														   (((CTRL_TRG_EDGE_FALLING << CTRL_TRG_SRC_BITS) | source) << CTRL_TRG_DST_RESTART);
									}
								}
								else {									// no external trigger
									config->ctrl_trg = 0;
								}
								// stop trigger control. we always add restart trigger as programmed for start trigger.
								if (stopSource != DIO64_STOP_NONE) { // external stop trigger.
									if      (stopSource == (DIO64_STOP_EXTERNAL + 0)) source = CTRL_TRG_SRC_IN0;
									else if (stopSource == (DIO64_STOP_EXTERNAL + 1)) source = CTRL_TRG_SRC_IN1;
									else if (stopSource == (DIO64_STOP_EXTERNAL + 2)) source = CTRL_TRG_SRC_IN2;
									else err = ERROR_ARGS;
									if ((startType & DIO64_STRTTYPE_EDGETOEDGE) == DIO64_STRTTYPE_EDGETOEDGE) {
										// edge-to-edge and stop trigger is incompatible. you have to decide for one of the two!
										err = ERROR_ARGS;
									}
									else if (board_level == 2) {
										// secondary board ext_in[0] is used, so have to use ext_in[1] for stop and restart
										source = CTRL_TRG_SRC_IN1;
										//config->ctrl_trg = (((config->ctrl_trg >> CTRL_TRG_DST_START) & CTRL_TRG_DST_MASK) >> CTRL_TRG_SRC_BITS;
										if (stopType == (DIO64_STOPTYPE_EDGE | DIO64_TRIG_RISING)) { // rising edge
											config->ctrl_trg |= (((CTRL_TRG_EDGE_RISING << CTRL_TRG_SRC_BITS) | source) << CTRL_TRG_DST_STOP) |
												(((config->ctrl_trg >> CTRL_TRG_DST_START) & CTRL_TRG_DST_MASK) << CTRL_TRG_DST_RESTART);
										}
										else if (stopType == (DIO64_STOPTYPE_EDGE | DIO64_TRIG_FALLING)) { // falling edge
											config->ctrl_trg |= (((CTRL_TRG_EDGE_FALLING << CTRL_TRG_SRC_BITS) | source) << CTRL_TRG_DST_STOP) |
												(((config->ctrl_trg >> CTRL_TRG_DST_START) & CTRL_TRG_DST_MASK) << CTRL_TRG_DST_RESTART);
										}
									}
									else {
										// primary board: use stop trigger as programmed
										if (stopType == (DIO64_STOPTYPE_EDGE | DIO64_TRIG_RISING)) { // rising edge
											config->ctrl_trg |= (((CTRL_TRG_EDGE_RISING << CTRL_TRG_SRC_BITS) | source) << CTRL_TRG_DST_STOP) |
												                (((config->ctrl_trg >> CTRL_TRG_DST_START) & CTRL_TRG_DST_MASK) << CTRL_TRG_DST_RESTART);
										}
										else if (stopType == (DIO64_STOPTYPE_EDGE | DIO64_TRIG_FALLING)) { // falling edge
											config->ctrl_trg |= (((CTRL_TRG_EDGE_FALLING << CTRL_TRG_SRC_BITS) | source) << CTRL_TRG_DST_STOP) |
												                (((config->ctrl_trg >> CTRL_TRG_DST_START) & CTRL_TRG_DST_MASK) << CTRL_TRG_DST_RESTART);
										}
									}
								}
								// output control: we always enable sync_out
								config->ctrl_out = (((CTRL_OUT_LEVEL_LOW << CTRL_OUT_SRC_BITS) | CTRL_OUT_SRC_SYNC_OUT) << CTRL_OUT_DST_OUT0);
#ifdef CONFIG_AUTO
								config->strb_delay = STRB_DELAY_AUTO;	// use strobe delay bits from server.config file of board
								config->sync_wait  = SYNC_DELAY_AUTO;	// use sync wait time from server.config file of board
								config->sync_phase = SYNC_PHASE_AUTO;	// use sync phase from server.config file of board
#else
								config->strb_delay = get_strb_delay(def_strb_delay, config->scan_Hz); // strobe delay bits for each rack
								config->sync_wait  = (primary==1) ? PRIM_SYNC_DELAY : 0;
								config->sync_phase = (primary==1) ? 0 : (((SEC_SYNC_PHASE_EXT * PHASE_360 / 360) & SYNC_PHASE_MASK_1) << SYNC_PHASE_BITS) |
									((SEC_SYNC_PHASE_DET * PHASE_360 / 360) & SYNC_PHASE_MASK_1);
#endif
								if (!err) {
									// save numer of repetitions. TODO: check if is this thread save?
									bd->reps = reps;
									bd->act_reps = 0;
									// configure board
									bd->send_queue->add(new thread_cmd(SERVER_CMD_OUT_CONFIG, config), PRIORITY_NORMAL);
									config = NULL; // config is now owned by thread 
									//bd->dlg_pos = dlg_add_hex(i, -1, SERVER_CMD_OUT_CONFIG, STATUS_ACTIVE, conf);

									// wait for responds
									thread_cmd* cmd = bd->recv_queue->remove(INFINITE);
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
						if (!config) delete config;
					}
				} // next board
			}
			// release lock
			LOCK_RELEASE(lock);
		}
	}
	return err;
}

// get board status
// on success status contains:
//		portCount        = used port count. it is 2 or 4 as defined in port/mask given to DIO64_Out_Config.
//		time[0], time[1] = low/high 16 bits of board time. you can use also ticks to get entire 32bit board time.
//		user[0], user[1] = low/high 16 bits of board samples. in the older version of the DIO64 driver this is 'cur trans'
//      flags, clkContrl = low/high 16 bits of FPGA status bits, see DIO64_STATUS_ constants in dio24_driver.h
//		scansAvail       = 32 bit board samples
//      readPtr          = board id for which status is returned
// returns 0 on success and nonzero on error
// if board is in error state returns ERROR_BOARD
// if boards are linked and board = id of primary board (see DIO64_OpenResource) returns status of the first board which is in state:
//		error       = at least this board in error state
//      running     = at least this board running
//		wait        = at least this board in waiting state (restart trigger)
//      not started = at least this board is not started (waiting for start trigger or internal trigger)
//      end         = all boards are in end state
//   priority is from top to bottom of list. this way it is easy to evaluate if any board is running or in error state or all boards have ended.
// if board id is given not for primary board, returns status of the given board.
#define ST_LEVEL_NONE			0
#define ST_LEVEL_END			1
#define ST_LEVEL_NOT_STARTED	2
#define ST_LEVEL_WAIT			3
#define ST_LEVEL_RUN			4
#define ST_LEVEL_ERROR			5
extern "C"
int DLLEXPORT DIO64_Out_Status(WORD board, DWORD *scansAvail, DIO64STAT *status) {
	int err = 0, n, boards_num_linked = (boards_linked && (board == boards_prim)) ? boards_num : 1;
	struct board_info *bd;
	struct client_status *cs;
	unsigned char status_level = ST_LEVEL_NONE;
	bool update_status = true; // get status always of primary board. might be overwritten with other boards with higher status_level.
	if ((!scansAvail) || (!status)) err = ERROR_ARGS;
	else {
		memset(status, 0, sizeof(DIO64STAT));
		// acquire lock
		if (LOCK_OPEN(lock)) err = ERROR_LOCK;
		else {
			if (!boards) err = ERROR_THREADS;
			else {
				for (n = 0; (n < boards_num_linked) && (!err); ++n) {
					// get board info
					bd = find_board(board, n);
					if (bd == NULL) err = ERROR_FIND_BOARD;
					else if (bd->ignore) {
						// ignored board return status = 0 and no scans available
						// application has to decide what to do with these boards.
						*scansAvail = 0;
					}
					else {

						// if not running we have to ask for actual status. if it is running we get status automatically
						if (!bd->running) {
							bd->send_queue->add(new thread_cmd(SERVER_CMD_OUT_STATUS, (void*)NULL), PRIORITY_NORMAL);
							//bd->dlg_pos = dlg_add(i, -1, SERVER_CMD_OUT_STATUS, STATUS_ACTIVE);
						}

						// get status of board
						thread_cmd* cmd;
						if (bd->running) cmd = bd->recv_queue->peek(THREAD_TIMEOUT);
						else             cmd = bd->recv_queue->remove(THREAD_TIMEOUT);
						// update last status
						if (cmd == NULL) err = ERROR_RECV_2;
						else {
							if ((cmd->cmd != SERVER_CMD_OUT_STATUS) || (cmd->data.ptr == NULL)) err = ERROR_UNEXPECTED;
							else if (cmd->status != STATUS_ACK) err = ERROR_ACK;
							else {
								cs = (struct client_status*)cmd->data.ptr;
								// check state of board
								// note: this shows error only when board is not anymore running and not in end state,
								//       i.e. with 'ignore clock loss' enabled will NOT show error here.
								if ERROR_STATE(cs->status.status) {
									// board is in error state
									if (!err) {
										err = (cs->status.status & DIO_STATUS_ERR_LOCK) ? ERROR_LOCK_LOST : ERROR_BOARD;
										dlg_update_icon(bd);
									}
									if ( status_level < ST_LEVEL_ERROR ) {
										// this is the first board in error state
										status_level = ST_LEVEL_ERROR;
										update_status = true;
									}
								}
								else if RUN_STATE_NO_WAIT(cs->status.status) { 
									// board is in running state
									if ( status_level < ST_LEVEL_RUN ) {
										// this is the first board in running state
										status_level = ST_LEVEL_RUN;
										update_status = true;
									}
								}
								else if WAIT_STATE(cs->status.status) {
									// board is in waiting state
									if ( status_level < ST_LEVEL_WAIT ) {
										// this is the first board in waiting state
										status_level = ST_LEVEL_WAIT;
										update_status = true;
									}
								}
								else if (END_STATE(cs->status.status)) {
									// board is in end state
									if ( status_level < ST_LEVEL_END ) {
										// first board in end state
										// note: since this is the lowest valid level all boards must be in this state
										//       in order that function returns this state.
										status_level = ST_LEVEL_END;
										update_status = true;
									}
								}
								else {
									// board not started
									if (status_level < ST_LEVEL_NOT_STARTED) {
										// first board in not started state
										status_level = ST_LEVEL_NOT_STARTED;
										update_status = true;
									}
								}
								// copy status if primary board or for first secondary board in error/running/not end state 
								if (update_status) {
									update_status = false;
									status->pktsize		= (bd->config & DIO_CTRL_BPS96) ? 12 : 8;	// bytes per samples
									status->portCount	= (bd->config & DIO_CTRL_BPS96) ? 4 : 2;	// number of ports used
									status->time[0]		= cs->status.board_time & 0xffff;			// board time low word
									status->time[1]		= cs->status.board_time >> 16;				// board time high word
									status->ticks		= cs->status.board_time;					// board time
									status->flags		= cs->status.status & 0xffff;				// status flags low word
									status->clkControl	= cs->status.status >> 16;					// status flags high word
									status->trans		= cs->status.board_samples;					// actual board samples
									status->reps		= bd->act_reps;								// actual number of repetitions
									status->readPtr		= board + n;		   						// board id for which status is returned 
									*scansAvail			= cs->status.board_samples;					// board samples
								}
								// update board time every second or when status changed
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
				}// next board
			}
			// release lock
			LOCK_RELEASE(lock);
		}
	}
	return err;
}

// send data to board (status is ignored but must not be NULL)
// ATTENTION: bufsize is in samples
extern "C"
int DLLEXPORT DIO64_Out_Write(WORD board, WORD *buffer, DWORD bufsize, DIO64STAT *status) {
	SERVER_CMD cmd = 0;
	int err = 0, n, boards_num_linked = (boards_linked) ? boards_num : 1;
	struct board_info *bd;
	struct wr_data *data;

	// check input
	if ((!buffer) || (bufsize == 0) || (!status)) err = ERROR_ARGS;
	else {
		// acquire lock
		if (LOCK_OPEN(lock)) err = ERROR_LOCK;
		else {
			if (!boards) err = ERROR_THREADS;
			else {
				for (n = 0; (n < boards_num_linked) && (!err); ++n) {
					// get board info
					bd = find_board(board, n);
					if (bd == NULL) err = ERROR_FIND_BOARD;
					else if (!bd->ignore) {
						data = new struct wr_data;
						if (data) {
							data->buffer = (char*)buffer;
							data->samples = bufsize;
#if ( DIO_BYTES_PER_SAMPLE == 8 )
							if (bd->config & DIO_CTRL_BPS96) {
								// 12bytes/sample: send first 8bytes or send first 4 bytes and last 4bytes 
								data->flags = (bd->config & DIO_CTRL_BPS96_BRD) ? WR_DATA_FLAG_BRD_1 : WR_DATA_FLAG_BRD_0;
							}
							else {
								data->flags = WR_DATA_FLAG_ALL;
							}
#endif
							// send data to board
							bd->send_queue->add(new thread_cmd(SERVER_CMD_OUT_WRITE, data), PRIORITY_NORMAL);
							//bd->dlg_pos = dlg_add_int(i, -1, SERVER_CMD_OUT_WRITE, STATUS_ACTIVE, data->bytes, " bytes");
							// wait for responds. this might take a long time!
							// note: since buffer is in user application we must wait here until threads return it!
							//       otherwise this might become invalid and threads crash!
							thread_cmd* cmd = bd->recv_queue->remove(RECV_TIMEOUT_DATA);
							dlg_add(bd, SERVER_CMD_OUT_WRITE, cmd ? cmd->status : STATUS_TIMEOUT_2, "%u smpl", data->samples);
							if (cmd == NULL) err = ERROR_RECV_2;
							else {
								if ((cmd->status != STATUS_ACK) && (!err)) err = cmd->status;
								delete cmd;
							}
							delete data;
						}
					}
				}
			}
			// release lock
			LOCK_RELEASE(lock);
		}
	}
	return err;
}

// start board
// this empties recv_queue and checks if also previous commands are ACK'nowledged, otherwise returns error
extern "C"
int DLLEXPORT DIO64_Out_Start(WORD board) {
	int err = 0, n, boards_num_linked = (boards_linked) ? boards_num : 1;
	// acquire lock
	if (LOCK_OPEN(lock)) err = ERROR_LOCK;
	else {
		if (!boards) err = ERROR_THREADS;
		else {
			// start boards beginning from secondary and primary is last
			// this ensures the start trigger is not send before secondary boards are ready
			for (n = boards_num_linked - 1; n >= 0; --n) {
				// start board and wait for responds
				// thread sets bd->running flag while board is running and resets at end.
				struct board_info* bd = find_board(board, n);
				if (bd == NULL) err = ERROR_FIND_BOARD;
				else {
					if (bd->running) err = ERROR_FIND_BOARD_2; // board already running?
					else if (!bd->ignore) {
						// start board
						bd->send_queue->add(new thread_cmd(SERVER_CMD_OUT_START, (void*)NULL), PRIORITY_NORMAL);
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
								if (cmd->data.ptr) {
									if (cmd->cmd == SERVER_CMD_OUT_STATUS) delete cmd->data.ptr;
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
						if (err) dlg_add(bd, SERVER_CMD_OUT_START, STATUS_ERROR, "%d", err);
					}
				}
				// stop all boards if there is an error
				if (err) {
					for (; n < boards_num_linked; ++n) {
						send_cmd_and_clean(board, n, SERVER_CMD_OUT_STOP, NULL, DO_SEND);
					}
					break;
				}
			}
			// count total number of runs. dialog is updated at stop command.
			++tot_runs;
			//dlg_update_count();
		}
		// release lock
		LOCK_RELEASE(lock);
	}
	return err;
}

// stop board
// this removes all commands from recv_queue and returns error if any is not ACK'nowleded
// TODO: if cycle is running ask user to stop immediately or at end of cycle?
extern "C"
int DLLEXPORT DIO64_Out_Stop(WORD board) {
	int err = 0, n, boards_num_linked = (boards_linked) ? boards_num : 1;
	// acquire lock
	if (LOCK_OPEN(lock)) err = ERROR_LOCK;
	else {
		if (!boards) err = ERROR_THREADS;
		else {
			// stop boards starting from last board
			// this ensures that lock is not lost from secondary boards if primary does a reset
			for (n = boards_num_linked - 1; n >= 0; --n) {
				// stop board and wait for responds. 
				// this removes all (status) entries from queue until SERVER_CMD_OUT_STOP
				// we ignore timeout here to be sure boards are stopped afterwards (even if user might be asked)
				// thread automatically resets bd->running flag, so we cannot check it here. afterwards its reset for sure.
				int tmp = send_cmd_and_clean(board, n, SERVER_CMD_OUT_STOP, NULL, DO_SEND | CHECK_ERROR);
				if (tmp && !err) err = tmp; // save first error but keep loop running
				// update run counter
				struct board_info* bd = find_board(board, n);
				if (bd) {
					++bd->act_reps;
				}
			}
			// update run counter in dialog box. we count start commands since stop might be called several times.
			dlg_update_count();
		}
		// release lock
		LOCK_RELEASE(lock);
	}
	return err;
}

/*
void show_error2(uint32_t board, uint32_t status, uint64_t time, uint32_t samples) {
	int n, num = _scprintf("board %u status %x time %llx samples %x", board, status, time, samples);
	if (num > 0) {
		char* message = new char[((size_t)num) + 1];
		if (message) {
			n = sprintf_s(message, ((size_t)num) + 1, "board %u status %x time %llx samples %x", board, status, time, samples);
			if (n == num) {
				show_error(ERROR_UNEXPECTED, message);
			}
			delete[] message;
		}
	}
}
*/

// Force output to a given state
// executes 1 line of code, i.e. config-status-write-start-status-stop.
// mask is not so clear since in DIO64_Out_Config is 4xWORDs, here 1xDWORD?
// we interpret it here that each bit stands for one port, i.e. 0x03 stands for 2 ports, and 0x0f stands for 4 ports
// note: when DIO64_Out_Config has not been called will return ERROR_ARGS when 4 ports are used.
extern "C"
int DLLEXPORT DIO64_Out_ForceOutput(WORD board, WORD *buffer, DWORD mask) {
	int err = 0;
	struct board_info *bd;

	// check input
	if ((!buffer) || (mask == 0x00) || (mask > 0x0f)) err = ERROR_ARGS;
	else {
		// acquire lock
		if (LOCK_OPEN(lock)) err = ERROR_LOCK;
		else {
			if (!boards) err = ERROR_THREADS;
			else {
				// get first board for checks. we later call individual functions which are executed for all boards.
				bd = find_board(board, 0);
				if (bd == NULL) err = ERROR_FIND_BOARD;
				else if (!bd->ignore) {
					// check consistency of mask with config
					int conf = 0;
					for (int i = 0; i < 4; ++i) {
						if (mask & 1) {
							if (++conf != (i+1)) { // 1's after 0's not allowed!
								err = ERROR_ARGS;
								break;
							}
						}
						mask = mask >> 1;
					}
					if (!err) {
						if (bd->config != 0) { // check only when DIO64_Out_Config has been called before.
							if (bd->config & DIO_CTRL_BPS96) {
								if (conf != 4) err = ERROR_ARGS;
								else {}
							}
							else {
								if (conf != 2) err = ERROR_ARGS;
							}
						}
						if (!err) {
							// mask is ok
							// backup total runs counter
							unsigned int old_tot_runs = tot_runs;
							// configure board. this is needed since Stop is resetting boards.
							WORD* mask2 = new WORD[conf];
							if (mask2) {
								for (int i = 0; i < conf; ++i) {
									mask2[i] = 0xffff;
								}
								double rate = 1e6;
								// ensure boards are stopped (needed for Yb experiment)
								err = DIO64_Out_Stop(board);
								if (!err) {
									err = DIO64_Out_Config(board, 0, mask2, conf, 0,
										DIO64_CLCK_INTERNAL,
										DIO64_STRT_NONE, DIO64_STRTTYPE_LEVEL,
										DIO64_STOP_NONE, DIO64_STOPTYPE_EDGE,
										DIO64_AI_NONE, 1, 0, &rate);
									if (!err) {
										// get board status
										uint32_t st = 0;
										DWORD scans = 0;
										DIO64STAT* status = new DIO64STAT;
										if (status) {
											err = DIO64_Out_Status(board, &scans, status);
											// other than bd->status this combines status of all boards
											st = status->flags | (status->clkControl << 16);
											if ((!err) && ((st & (DIO_STATUS_RUN | DIO_STATUS_ERROR)) == 0)) {
												// write 1 data sample to boards
												WORD* buf = new WORD[(2 + (size_t)conf) * sizeof(WORD)];
												if (buf) {
													// insert time = 1us, data
													buf[0] = 1;
													buf[1] = 0;
													buf[2] = buffer[0];
													buf[3] = buffer[1];
													if (conf == 4) {
														buf[4] = buffer[2];
														buf[5] = buffer[3];
													}
													err = DIO64_Out_Write(board, buf, 1, status);
													if (!err) {
														// start boards
														err = DIO64_Out_Start(board);
														if (!err) {
															// wait until all boards are in end state or an error occurred
															do {
																err = DIO64_Out_Status(board, &scans, status);
																st = status->flags | (status->clkControl << 16);
															} while ((!err) && ((st & (DIO_STATUS_END|DIO_STATUS_ERROR)) == 0));
															if (!err) {
																if (scans != 4) { // note: driver adds 3 NOP samples
																	//show_error2((uint32_t)(status->readPtr-board), (uint32_t)st, (uint64_t)status->ticks, (uint32_t)scans);
																	err = ERROR_UNEXPECTED;
																}
																else if (((st & (DIO_STATUS_RUN|DIO_STATUS_END| DIO_STATUS_ERROR)) != DIO_STATUS_END)) err = ERROR_BOARD;
															}
															// stop boards regardless of error
															int tmp = DIO64_Out_Stop(board);
															if (!err) err = tmp;
														}
													}
													delete[] buf;
												}
											}
											delete status;
										}
									}
								}
								delete[] mask2;
							}
							// reset total runs counter to original value (Out_Stop was called 2x)
							tot_runs = old_tot_runs;
						}
					}
					// update command
					dlg_add(bd, SERVER_CMD_OUT_FORCE, err ? STATUS_ERROR : STATUS_NONE, NULL, 0);
				}
			}
			// release lock
			LOCK_RELEASE(lock);
		}
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
// additional public functions not in original DLL
////////////////////////////////////////////////////////////////////////////////////////

// exit all threads and close dialog box
// this is not anymore compulsary. but call to ensure that threads are terminated before DLL is unloaded.
// if not used insert CLOSE_TIMEOUT ms wait time before exiting application to allow threads to terminate.
// lock should have been released before exit_all() is called, i.e. all boards should have been closed with DIO64_Close.
extern "C" int DLLEXPORT exit_all(void) {
	int err = 0;
	HANDLE hdl;
	// acquire lock
	LOCK_OPEN_WAIT(lock);
#ifdef _DEBUG
	if (lock_count != 1) {
		printf("\nexit_all unexpected lock_count = %i should be 1! (continue)\n\n", lock_count);
	}
#endif
	while (boards) {
		hdl = boards->thread_hdl;
		if (hdl == NULL) { err = ERROR_THREADS_2; break; } // should not happen.
		if (boards->board != BOARD_NONE) {
			// if not already closed send thread exit command. thread will not respond!
			boards->send_queue->add(new thread_cmd(THREAD_EXIT, (void*)NULL), PRIORITY_NORMAL);
			boards->board = BOARD_NONE; // mark board as closed such that thread will close board and exit
		}
		// release lock allows thread to exit.
		// thread will delete board and boards need to be checked again!
		LOCK_RELEASE(lock);
		WaitForSingleObject(hdl, INFINITE);
		// re-aquire lock and check if remaining boards.
		LOCK_OPEN_WAIT(lock);
	}
	// finally release lock.
	LOCK_RELEASE(lock);
#ifdef _DEBUG
	if (lock_count != 0) {
		printf("\nexit_all unexpected lock_count = %i should be 0! (end)\n\n", lock_count);
	}
#endif
	return err;
}

// send test command to server of board n=0,1,2,...
extern "C" int DLLEXPORT test(WORD board, int n, void *data) {
	int err = 0;
	// acquire lock
	if (LOCK_OPEN(lock)) err = ERROR_LOCK;
	else {
		if (!boards) err = ERROR_THREADS;
		else {
			err = send_cmd_and_clean(board, n, SERVER_TEST, data, DO_SEND | CHECK_ERROR);
		}
		// release lock
		LOCK_RELEASE(lock);
	}
	return err;
}

// register callback function with given user data
// set callback = NULL to unregister
// returns 0 on success, otherwise error
// callback is executed by master thread on each status irq
// ensure callback function is thread-safe and user_data is valid until unregistered!
extern "C" int DLLEXPORT register_callback(WORD board, int n, thread_cb callback, void *user_data)
{
	int err = 0;
	struct board_info *bd;
	// acquire lock
	if (LOCK_OPEN(lock)) err = ERROR_LOCK;
	else {
		if (!boards) err = ERROR_THREADS;
		else {
			// find board
			bd = find_board(board, n);
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
		// release lock
		LOCK_RELEASE(lock);
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
// TODO: ignores new lines and just rearranges data. should I give an error when uint32_per_sample != columns?
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
