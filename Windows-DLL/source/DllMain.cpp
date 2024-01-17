////////////////////////////////////////////////////////////////////////////////////////
// DllMain.cpp
// Win32/64 DLL for easy interaction with Labview and FPGA server
// created 27/11/2019 by Andi
////////////////////////////////////////////////////////////////////////////////////////

#include "Dio24.h"				// include all headers

#include <stdio.h>				// printf
#include <commdlg.h>			// open/save file dialog
//#include <CommCtrl.h>			// common controls

#ifndef SIMPLE_SERVER_HEADER	// if defined was done by done by simple-server
// link with WS2_32.lib (needs VisualStudio)
#pragma comment(lib,"WS2_32.lib")
#endif

////////////////////////////////////////////////////////////////////////////////////////
// shared resources, protected by lock
////////////////////////////////////////////////////////////////////////////////////////

int num_proc = 0;				// number of attached processes
HANDLE lock = NULL;				// lock protects shared data. TODO: list of shared data... boards, num_proc, ...
HINSTANCE hInstModule = NULL;	// DLL instance
bool ignore_clock_loss = false;	// ignore clock loss. note: can be changed by user anytime. not protected but should not matter.

////////////////////////////////////////////////////////////////////////////////////////
// queue class
////////////////////////////////////////////////////////////////////////////////////////

HANDLE hStartup = INVALID_HANDLE_VALUE;			// signalled when thread startup and queues are valid

thread_queue::thread_queue() {
	InitializeCriticalSection(&cs);
	hSem = CreateSemaphore(NULL, 0L, 20L, NULL);
	first = NULL;
}

thread_queue::~thread_queue() {
	DeleteCriticalSection(&cs);
	CloseHandle(hSem);
	hSem = NULL;
	while (first) {
		thread_cmd *next = first->next;
		delete first;
		first = next;
	}
}

int thread_queue::debug(thread_cmd *&last) {
	int i;
	EnterCriticalSection(&cs);
	last = first;
	for (i = 0; last != NULL; ++i, last = last->next) {
		if (last->next == NULL) { ++i; break; }
	}
	LeaveCriticalSection(&cs);
	return i;
}

// add command to queue
// returns 0 if ok, otherwise error
int thread_queue::add(thread_cmd *cmd, bool priority) {
	thread_cmd *last;
	if (cmd) {
		cmd->next = NULL;
		EnterCriticalSection(&cs);
		if (priority == PRIORITY_NOW) { // insert cmd as first entry
			cmd->next = first;
			first = cmd;
		}
		else { // insert cmd as last entry
			last = first;
			if (last == NULL) first = cmd;
			else {
				while(true) {
					if (last->next == NULL) { last->next = cmd; break; }
					last = last->next;
				}
			}
		}
		LeaveCriticalSection(&cs);
		ReleaseSemaphore(hSem, 1, NULL);
		return 0;
	}
	return -1;
}

// remove first command from queue
// returns NULL on timeout
thread_cmd * thread_queue::remove(DWORD timeout) {
	thread_cmd *cmd = NULL;
	if (WaitForSingleObject(hSem, timeout) == WAIT_OBJECT_0) {
		EnterCriticalSection(&cs);
		cmd = first;
		if (cmd) first = cmd->next;
		LeaveCriticalSection(&cs);
		if (cmd) cmd->next = NULL;
	}
	return cmd;
}

// returns copy of first entry or NULL if queue is empty
// note: do not delete data if returned command contains data!
thread_cmd * thread_queue::peek(DWORD timeout) {
	thread_cmd *cmd = NULL;
	if (WaitForSingleObject(hSem, timeout) == WAIT_OBJECT_0) {
		cmd = new thread_cmd(SERVER_NONE, (void*)NULL);
		if (cmd) {
			EnterCriticalSection(&cs);
			if (first) *cmd = *first;
			LeaveCriticalSection(&cs);
			if (cmd->cmd != SERVER_NONE) cmd->next = NULL;
			else { delete cmd; cmd = NULL; }
		}
		ReleaseSemaphore(hSem, 1L, NULL);
	}
	return cmd;
}

// updates last queue entry of same command with new one or creates new entry if queue empty or different command.
// returns updated entry or NULL if new created.
thread_cmd * thread_queue::update(thread_cmd *cmd) {
	thread_cmd *last, *prev = NULL;
	cmd->next = NULL;
	EnterCriticalSection(&cs);
	if (first == NULL) { // empty queue: insert cmd
		first = cmd;
		last = NULL;
		ReleaseSemaphore(hSem, 1, NULL);
	}
	else {
		last = first;
		while (true) {
			if (last->next == NULL) { // last entry
				if (last->cmd == cmd->cmd) { // same command: exchange last with cmd
					if (prev == NULL) first = cmd; // one entry in queue
					else prev->next = cmd;
				}
				else { // not same command: append cmd
					last->next = cmd;
					last = NULL;
					ReleaseSemaphore(hSem, 1, NULL);
				}
				break;
			}
			prev = last;
			last = last->next;
		}
	}
	LeaveCriticalSection(&cs);
	return last;
}

////////////////////////////////////////////////////////////////////////////////////////
// modeless message dialog box
////////////////////////////////////////////////////////////////////////////////////////

HWND MB_hWnd = NULL;					// dialog box handle
unsigned MB_count = 0;					// count number of runs with errors.

// increment counter and update message dialog
void update_MB(HWND hWnd, LPARAM lParam) {
	static const char MB_format_prim[] = MB_TEXT_PRIM;
	static const char MB_format_sec[]  = MB_TEXT_SEC;
	unsigned short board_id  = (unsigned short) lParam;
	char* buffer;
	int i;
	SYSTEMTIME lt;
	GetLocalTime(&lt);
	// increment counter
	++MB_count;
	// get size of buffer and allocate buffer
	i = _scprintf((board_id == 0) ? MB_format_prim : MB_format_sec, 
            board_id, 
            MB_count, 
            lt.wYear, lt.wMonth, lt.wDay, lt.wHour, lt.wMinute, lt.wSecond, tot_runs);
	if (i > 0) {
		buffer = new char[((size_t)i) + 1];
		if (buffer) {
			// create output
			if (sprintf_s(buffer, ((size_t)i) + 1, (board_id == 0) ? MB_format_prim : MB_format_sec, 
                    board_id, 
                    MB_count, 
                    lt.wYear, lt.wMonth, lt.wDay, lt.wHour, lt.wMinute, lt.wSecond, tot_runs) == i) {
				SendDlgItemMessageA(hWnd, ID_MB_TEXT, WM_SETTEXT, (WPARAM)0, (LPARAM)buffer);
				// show message dialog
				ShowWindow(hWnd, SW_SHOW);
				SetForegroundWindow(hWnd);
			}
			delete[] buffer;
		}
	}
}

// this runs on the dlg_thread_proc thread, i.e. the same as the main dialog box
// TODO: not clear but maybe this could be run also on main DlgProc? 
//       initialization could be done after creation. initially is not visible. 
INT_PTR CALLBACK DlgMBProc(HWND hWnd, UINT message, WPARAM wParam, LPARAM lParam) {
	switch (message) {
	case WM_INITDIALOG:
		MB_count = 0;
		SendMessageA(hWnd, WM_SETTEXT, (WPARAM)0, (LPARAM)MB_CAPTION);
		ShowWindow(hWnd, SW_HIDE);
		return TRUE;
	case WM_COMMAND:
		switch (LOWORD(wParam)) {
		case ID_MB_OK:
			// reset counter and hide message dialog
			MB_count = 0;
			ShowWindow(hWnd, SW_HIDE);
			return TRUE;
		}
		break;
	}
	return FALSE; // FALSE = not handled, TRUE = handled
}

////////////////////////////////////////////////////////////////////////////////////////
// Dialog box thread procedure
////////////////////////////////////////////////////////////////////////////////////////

HWND dlg_hWnd = NULL;					// dialog box handle
HANDLE dlg_thread_hdl = NULL;			// dialog box thread
HFONT dlg_fmono = NULL;					// dialog monocpaced font
HICON dlg_icon = NULL;					// dialog icon
BOOL locked = false;					// true while dlg_thread keeps lock
char* dlg_caption = NULL;				// dialog caption

// manual button pressed: acquire lock and enable manual mode
inline void manual_enable(void) {
	if (!locked) {
		if (LOCK_OPEN(lock)) {
			MessageBoxA(dlg_hWnd, "cannot lock boards!\nclose boards in application.", DLL_INFO, MB_ICONEXCLAMATION | MB_OK);
			SendDlgItemMessage(dlg_hWnd, ID_MANUAL, BM_SETCHECK, (WPARAM)FALSE, (LPARAM)0L);
		}
		else {
			EnableWindow(GetDlgItem(dlg_hWnd, ID_STATUS), TRUE);
			EnableWindow(GetDlgItem(dlg_hWnd, ID_RESET), TRUE);
			EnableWindow(GetDlgItem(dlg_hWnd, ID_LOAD), TRUE);
			EnableWindow(GetDlgItem(dlg_hWnd, ID_SAVE), TRUE);
			EnableWindow(GetDlgItem(dlg_hWnd, ID_IP_0), TRUE);
			EnableWindow(GetDlgItem(dlg_hWnd, ID_IP_1), TRUE);
			EnableWindow(GetDlgItem(dlg_hWnd, ID_USE_0), TRUE);
			EnableWindow(GetDlgItem(dlg_hWnd, ID_USE_1), TRUE);
			EnableWindow(GetDlgItem(dlg_hWnd, ID_CONF_0), TRUE);
			EnableWindow(GetDlgItem(dlg_hWnd, ID_CONF_1), TRUE);
			EnableWindow(GetDlgItem(dlg_hWnd, ID_KEEP), TRUE);
			EnableWindow(GetDlgItem(dlg_hWnd, ID_REPS), TRUE);
			locked = true;
		}
	}
}

// manual button released: release lock and disable manual mode
inline void manual_disable(void) {
	if (locked) {
		LOCK_RELEASE(lock);
		EnableWindow(GetDlgItem(dlg_hWnd, ID_STATUS), FALSE);
		EnableWindow(GetDlgItem(dlg_hWnd, ID_RESET), FALSE);
		EnableWindow(GetDlgItem(dlg_hWnd, ID_LOAD), FALSE);
		EnableWindow(GetDlgItem(dlg_hWnd, ID_SAVE), FALSE);
		EnableWindow(GetDlgItem(dlg_hWnd, ID_IP_0), FALSE);
		EnableWindow(GetDlgItem(dlg_hWnd, ID_IP_1), FALSE);
		EnableWindow(GetDlgItem(dlg_hWnd, ID_USE_0), FALSE);
		EnableWindow(GetDlgItem(dlg_hWnd, ID_USE_1), FALSE);
		EnableWindow(GetDlgItem(dlg_hWnd, ID_CONF_0), FALSE);
		EnableWindow(GetDlgItem(dlg_hWnd, ID_CONF_1), FALSE);
		EnableWindow(GetDlgItem(dlg_hWnd, ID_KEEP), FALSE);
		EnableWindow(GetDlgItem(dlg_hWnd, ID_REPS), FALSE);
		locked = false;
	}
}

// user data
struct data_info* data = NULL;
unsigned int samples = 0;

// last file names
char buf_load[MAX_PATH] = "";
char buf_save[MAX_PATH] = "";

void load_file_dlg(HWND hWnd) {
	OPENFILENAMEA ofn;
	ZeroMemory(&ofn, sizeof(ofn));
	ofn.lStructSize = sizeof(ofn);
	ofn.hwndOwner = hWnd;
	ofn.lpstrFile = buf_load;
	//buf_load[0] = '\0';
	ofn.nMaxFile = MAX_PATH;
	ofn.lpstrFilter = "data\0*.TXT;*.DAT;*.CSV;*.RAW\0all\0*.*\0";
	ofn.nFilterIndex = 1;
	ofn.lpstrFileTitle = NULL;
	ofn.nMaxFileTitle = 0;
	ofn.lpstrInitialDir = NULL;
	ofn.Flags = OFN_PATHMUSTEXIST | OFN_FILEMUSTEXIST;
	if (GetOpenFileNameA(&ofn) == TRUE) {
		// ok: delete old data and load new data
		while (data) {
			struct data_info* next = data->next;
			delete[] data->data;
			delete data;
			data = next;
		}
		samples = 0;
		data = load_text_file(ofn.lpstrFile, &samples, DIO_BYTES_PER_SAMPLE / sizeof(uint32_t));
	}
}

void save_file_dlg(HWND hWnd) {
	OPENFILENAMEA ofn;
	if (!data) MessageBox(hWnd, L"no data to save!", L"save data", MB_OK | MB_ICONINFORMATION);
	else {
		ZeroMemory(&ofn, sizeof(ofn));
		ofn.lStructSize = sizeof(ofn);
		ofn.hwndOwner = hWnd;
		ofn.lpstrFile = buf_save;
		//buffer[0] = '\0';
		ofn.nMaxFile = MAX_PATH;
		ofn.lpstrFilter = "data\0*.TXT;*.DAT;*.CSV;*.RAW\0all\0*.*\0";
		ofn.nFilterIndex = 1;
		ofn.lpstrFileTitle = NULL;
		ofn.nMaxFileTitle = 0;
		ofn.lpstrInitialDir = NULL;
		ofn.Flags = OFN_PATHMUSTEXIST | OFN_CREATEPROMPT | OFN_OVERWRITEPROMPT;
		if (GetSaveFileNameA(&ofn) == TRUE) {
			// ok: save data to file
			save_text_file(ofn.lpstrFile, data, DIO_BYTES_PER_SAMPLE / sizeof(uint32_t));
		}
	}
}

// returns dialog box caption from build date __DATE__ in a nicer form
// returns buffer with date, delete[] after use. returns NULL on error.
// TODO: there might have been an issue here with some but not all dates?
char * get_caption(void)
{
	static const char* months[] = { "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug","Sep", "Oct", "Nov", "Dec" };
	static const char build_date[] = __DATE__ " " __TIME__;
	static const char build_format[] = "%hu %hu %hu:%hu:%hu"; // format of build_date without month: "day year hour:minute:seconds"
	static const char out_format[] = "%s (%04hu/%02hu/%02hu %hu:%02hu:%02hu)"; // returned format "caption (y/m/d h:m:s)"
	char* buffer;
	unsigned short year, month, day, hour, minute, seconds;
	int i,j;

	// find month as first 3 characters
	for (i = 0; i < 12; i++) {
		for (j = 0; (j < 3) && (build_date[j] == months[i][j]); ++j);
		if (j == 3) {
			if (build_date[j] == ' ') {
				// month found
				month = i + 1;
				// get day and year
				i = sscanf_s(build_date + j + 1, build_format, &day, &year, &hour, &minute, &seconds);
				if (i == 5) {
					// get size of buffer and allocate buffer
					i = _scprintf(out_format, DIALOG_CAPTION, year, month, day, hour, minute, seconds);
					if (i > 0) {
						buffer = new char[((size_t)i) + 1];
						if (buffer) {
							// create output
							if (sprintf_s(buffer, ((size_t)i) + 1, out_format, DIALOG_CAPTION, year, month, day, hour, minute, seconds) != i) {
								delete[] buffer;
								buffer = NULL;
							}
							else {
								// return buffer. delete[] after use.
								return buffer;
							}
						}
					}
				}
			}
			break;
		}
	}
	// error
	return NULL;
}

INT_PTR CALLBACK DlgProc(HWND hWnd, UINT message, WPARAM wParam, LPARAM lParam) {
	switch (message) {
	case WM_INITDIALOG: 
		// set initial state of dialog box (hWndDialog is not yet defined)
		ignore_clock_loss = FALSE;
		dlg_caption = get_caption();
		SendMessageA(hWnd, WM_SETTEXT, (WPARAM)0, (LPARAM)(dlg_caption ? dlg_caption : DIALOG_CAPTION));
		SendDlgItemMessage(hWnd, ID_USE_0, BM_SETCHECK, (WPARAM)BST_CHECKED, (LPARAM)0);
		SendDlgItemMessage(hWnd, ID_USE_1, BM_SETCHECK, (WPARAM)BST_CHECKED, (LPARAM)0);
		SendDlgItemMessage(hWnd, ID_ASCROLL_0, BM_SETCHECK, (WPARAM)BST_CHECKED, (LPARAM)0);
		SendDlgItemMessage(hWnd, ID_ASCROLL_1, BM_SETCHECK, (WPARAM)BST_CHECKED, (LPARAM)0);
		SendDlgItemMessageA(hWnd, ID_IP_0, WM_SETTEXT, (WPARAM)0, (LPARAM)"not connected");
		SendDlgItemMessageA(hWnd, ID_IP_1, WM_SETTEXT, (WPARAM)0, (LPARAM)"not connected");
		SendDlgItemMessageA(hWnd, ID_CONF_0, WM_SETTEXT, (WPARAM)0, (LPARAM)"none");
		SendDlgItemMessageA(hWnd, ID_CONF_1, WM_SETTEXT, (WPARAM)0, (LPARAM)"none");
		SendDlgItemMessageA(hWnd, ID_REPS, WM_SETTEXT, (WPARAM)0, (LPARAM)"0");
		// set status full font to monospaced (destroy font after use)
		dlg_fmono = CreateFont(8, 0, 0, 0, FW_LIGHT, FALSE, FALSE, FALSE, ANSI_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, DEFAULT_QUALITY, DEFAULT_PITCH | FF_MODERN, TEXT("Courier New"));
		SendDlgItemMessage(hWnd, ID_STATUS_FULL_0, WM_SETFONT, (WPARAM)dlg_fmono, (LPARAM)0);
		SendDlgItemMessage(hWnd, ID_STATUS_FULL_1, WM_SETFONT, (WPARAM)dlg_fmono, (LPARAM)0);
		// set dialog icon (icon does not need to be destroyed)
		dlg_icon = LoadIcon(hInstModule, MAKEINTRESOURCE(IDI_DLG));
		SendMessage(hWnd, WM_SETICON, (WPARAM)ICON_BIG, (LPARAM)dlg_icon);
		SendMessage(hWnd, WM_SETICON, (WPARAM)ICON_SMALL, (LPARAM)dlg_icon);
		return TRUE;
	case WM_SYSCOMMAND:
		switch (wParam) {
		case SC_CLOSE:
			manual_disable();			// release lock if was locked
			DestroyWindow(dlg_hWnd);	// close dialog box
			return TRUE;
		}
		break;
	case WM_COMMAND:
		switch (LOWORD(wParam)) {
		case ID_MB_SHOW:
			// increment counter and display message box until user presses ok
			update_MB(MB_hWnd, lParam);
			break;
		case ID_IGNORE_CLOCK_LOSS: 
			if (HIWORD(wParam) == BN_CLICKED) {
				int res = MessageBoxW(hWnd, MSG_IGNORE_CLOCK_LOSS, L"Ignore External Clock Loss", MB_YESNOCANCEL | MB_ICONQUESTION);
				switch (res) {
				case IDYES:
					ignore_clock_loss = true;
					CheckDlgButton(hWnd, ID_IGNORE_CLOCK_LOSS, TRUE);
					//SendDlgItemMessage(hWnd, ID_IGNORE_CLOCK_LOSS, BM_SETSTATE, (WPARAM)TRUE, (LPARAM)0L);
					//SendDlgItemMessage(hWnd, ID_IGNORE_CLOCK_LOSS, WM_SETTEXT, (WPARAM)0, (LPARAM)TXT_MONITOR_CLOCK_LOSS);
					break;
				case IDNO:
					ignore_clock_loss = false;
					CheckDlgButton(hWnd, ID_IGNORE_CLOCK_LOSS, FALSE);
					//SendDlgItemMessage(hWnd, ID_IGNORE_CLOCK_LOSS, BM_SETSTATE, (WPARAM)FALSE, (LPARAM)0);
					//SendDlgItemMessage(hWnd, ID_IGNORE_CLOCK_LOSS, WM_SETTEXT, (WPARAM)0, (LPARAM)TXT_IGNORE_CLOCK_LOSS);
					break;
				}
			}
			return TRUE;
		case ID_MANUAL:
			if (SendDlgItemMessage(hWnd, ID_MANUAL, BM_GETCHECK, (WPARAM)0, (LPARAM)0L) == BST_CHECKED) manual_enable();
			else manual_disable();
			return TRUE;
		case ID_STATUS:
			dlg_update_status();
			return TRUE;
		case ID_RESET:
			dlg_reset();
			return TRUE;
		case ID_LOAD:
			load_file_dlg(hWnd); // open file dialog box and call load_file function
			return TRUE;
		case ID_SAVE:
			save_file_dlg(hWnd); // save file dialog box and call save_file function
			return TRUE;
		case ID_EXIT:
			//MessageBox(hWnd, L"exit", L"test", MB_OK);
			DestroyWindow(dlg_hWnd);
			return TRUE;
		}
		break;
	case WM_DESTROY:
		// delete data
		while (data) {
			struct data_info* next = data->next;
			delete[] data->data;
			delete data;
			data = next;
		}
		if (dlg_caption) {
			delete[] dlg_caption;
			dlg_caption = NULL;
		}
		PostQuitMessage(0);
		return TRUE;
	}
	return FALSE; // FALSE = not handled, TRUE = handled; https://learn.microsoft.com/en-us/windows/win32/api/winuser/nc-winuser-dlgproc
}

DWORD WINAPI dlg_thread_proc(LPVOID lpParam) {
	DWORD err = 0;
	MSG msg;
	int ret;

	// create modeless dialog boxes for main frame and hidden message box
	dlg_hWnd = CreateDialog(hInstModule, MAKEINTRESOURCE(IDD_DIALOG), NULL, DlgProc);
	MB_hWnd  = CreateDialog(hInstModule, MAKEINTRESOURCE(IDD_MB), NULL, DlgMBProc);
	// signal startup finished even on error
	SetEvent(hStartup);
	if (dlg_hWnd && MB_hWnd) {
		// message loop until DestroyWindow(dlg_hWnd) is called by thread or WM_DESTROY is sent by other thread
		while ((ret = GetMessage(&msg, NULL, 0, 0)) != 0) {
			if (ret == -1) break; // error
			else {
				if ((!IsDialogMessage(dlg_hWnd, &msg)) &&
				    (!IsDialogMessage(MB_hWnd, &msg)) ) {
					TranslateMessage(&msg);
					DispatchMessage(&msg);
				}
			}
		}
		DestroyWindow(MB_hWnd);
		DestroyWindow(dlg_hWnd);
		dlg_hWnd = NULL;
		MB_hWnd = NULL;
	}
	else err = -1;

	if (dlg_fmono) { DeleteObject(dlg_fmono); dlg_fmono = NULL; }
	// note: dlg_icon does not need to be destroyed

	return err;
}

////////////////////////////////////////////////////////////////////////////////////////
// DLL entry point
////////////////////////////////////////////////////////////////////////////////////////

//INITCOMMONCONTROLSEX icex;

BOOL APIENTRY DllMain(HINSTANCE hModule, DWORD ul_reason_for_call, LPVOID lpReserved)
{
	BOOL ret = FALSE;
	switch (ul_reason_for_call)	{
	case DLL_PROCESS_ATTACH:
		// first attached process creates system-wide lock which protects shared data
		// other processes optain the same handle
		lock = CreateMutexA(NULL, FALSE, LOCK_NAME);
		if (lock) {
			hInstModule = hModule;
			if (num_proc == 0) {
				//DWORD id;
				//CreateThread(NULL, 0, dialog_thread, 0, 0, &id);
			}
			//icex.dwSize = sizeof(INITCOMMONCONTROLSEX);
			//icex.dwICC = ICC_TAB_CLASSES;
			//if (InitCommonControlsEx(&icex)) {
				++num_proc;
				ret = TRUE;
			//}
		}
#ifdef _DEBUG
		wprintf(L"process attached (%hu), count %d, result %d (1=ok)\n", GetCurrentThreadId(), num_proc, ret);
#endif
		break;
	case DLL_THREAD_ATTACH:
#ifdef _DEBUG
		wprintf(L"thread attached (%hu, ok)\n", GetCurrentThreadId());
#endif
		ret = TRUE;
		break;
	case DLL_THREAD_DETACH:
#ifdef _DEBUG
		wprintf(L"thread detached (%hu, ok)\n", GetCurrentThreadId());
#endif
		ret = TRUE;
		break;
	case DLL_PROCESS_DETACH:
		--num_proc;
		/*if ((num_proc == 0) && (dlg_hWnd != NULL)) {
			SendMessage(dlg_hWnd, WM_DESTROY, 0, 0L); // this seems to crash sometimes!?
		}*/
		// close lock. if this is the last process the lock is destroyed
		if (lock) {
			CloseHandle(lock);
			lock = NULL;
			ret = TRUE;
		}
#ifdef _DEBUG
		wprintf(L"process detached (%hu), count %d, result %d (1=ok)\n", GetCurrentThreadId(), num_proc, ret);
#endif
		break;
	}
	
	// return TRUE on success, otherwise FALSE and DLL will be unloaded
	return ret;
}
