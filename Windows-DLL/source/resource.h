// resource.h
// defines of dialog ID's
#ifndef RES_H
#define RES_H

#define MY_VERSION				"v2.1 by Andi"

#ifdef _WIN64
#define DLL_TYPE				"64bit WinDLL"
#else
#define DLL_TYPE				"32bit WinDLL"
#endif

// dialog caption (string concat does not work in .rc file!)
#define DIALOG_CAPTION			"FPGA board status - " DLL_TYPE " " MY_VERSION

// dialog box
#define IDD_DIALOG				100
// general
#define ID_EXIT					101
#define ID_IGNORE_CLOCK_LOSS	102
#define ID_TAB					103
// board 0
#define ID_IP_0					110
#define ID_ICON_0				111
#define ID_USE_0				112
#define ID_CONF_0				113
#define ID_STATUS_0				114
#define ID_TIME_0				115
#define ID_STATUS_FULL_0		116
#define ID_ASCROLL_0			117
#define ID_LIST_0				118
// board 1
#define ID_IP_1					120
#define ID_ICON_1				121
#define ID_USE_1				122
#define ID_CONF_1				123
#define ID_STATUS_1				124
#define ID_TIME_1				125
#define ID_STATUS_FULL_1		126
#define ID_ASCROLL_1			127
#define ID_LIST_1				128
// manual mode
#define ID_MANUAL				130
#define ID_STATUS				131
#define ID_RESET				132
#define ID_LOAD					133
#define ID_SAVE					134
#define ID_KEEP					135
#define ID_OPEN_CLOSE			136
#define ID_CONFIG				137
#define ID_SEND					138
#define ID_START_STOP			139
#define ID_REPS					140
// dlg and status icon
#define IDI_DLG					150
#define IDI_NC					151
#define IDI_OK					152
#define IDI_ERR					153

// message box
#define IDD_MB					200
#define IDI_MB_DLG				210
#define ID_MB_ICON				220
#define ID_MB_TEXT				230
#define ID_MB_OK				240
#define ID_MB_SHOW				290

#define STATUS_TEXT				"board status in manual mode"
#define TXT_IGNORE_CLOCK_LOSS	L"ignore CLK loss"

#endif

// keep one newline after this, otherwise get "unexpected end of file found"
