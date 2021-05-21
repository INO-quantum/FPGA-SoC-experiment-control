#ifndef DIO64_H
#define DIO64_H

/* DIO64.H

   Viewpoint Systems, Inc.
   800 West Metro Parkway.
   Rochester, New York    14623
   (585) 475-9555
   viewpointusa.com

   Copyright (c) 2002
   All Rights Reserved
*/

// modified version by Andi, last modification 14/10/2020

// Andi: driver definisions used for callback and IRQ
#include "dio24_driver.h"

#define DLLEXPORT __declspec(dllexport) __stdcall

typedef unsigned short WORD;
typedef unsigned long DWORD;
typedef unsigned short USHORT;
typedef unsigned long ULONG;

#define DIO64_CLCK_INTERNAL 0
#define DIO64_CLCK_EXTERNAL 1
#define DIO64_CLCK_TRIG_0   2
#define DIO64_CLCK_OCXO			3

#define DIO64_STRT_NONE     0
#define DIO64_STRT_EXTERNAL 1
#define DIO64_STRT_TRIG_2   2
#define DIO64_STRT_PXI_STAR 3

#define DIO64_STRTTYPE_LEVEL      0
#define DIO64_STRTTYPE_EDGETOEDGE 2
#define DIO64_STRTTYPE_EDGE       4


#define DIO64_STOP_NONE					0
#define DIO64_STOP_EXTERNAL			1
#define DIO64_STOP_TRIG_3_IN		2
#define DIO64_STOP_OUTPUT_FIFO	3

#define DIO64_STOPTYPE_EDGE     0


#define DIO64_TRIG_RISING	 0
#define DIO64_TRIG_FALLING 1

#define DIO64_AI_NONE 0



#pragma pack(push, 1)
typedef struct _DIO64STAT {
	 USHORT pktsize;
   USHORT portCount;
   USHORT writePtr;
   USHORT readPtr;
   USHORT time[2];
   ULONG	fifoSize;

   USHORT fifo0;
   ULONG  ticks;
   USHORT flags;
   USHORT clkControl;
   USHORT startControl;
   USHORT stopControl;
   ULONG	AIControl;
   USHORT AICurrent;
   USHORT startTime[2];
   USHORT stopTime[2];
	 USHORT user[4];
} DIO64STAT;
#pragma pack(pop)

#define DIO64_ATTR_INPUTMODE									0		// 4=demand
#define DIO64_ATTR_OUTPUTMODE									1		// 3=packet
#define DIO64_ATTR_INPUTBUFFERSIZE						2
#define DIO64_ATTR_OUTPUTBUFFERSIZE						3
#define DIO64_ATTR_MAJORCLOCKSOURCE						4
#define DIO64_ATTR_INPUTTHRESHOLD							5			// 50%
#define DIO64_ATTR_OUTPUTTHRESHOLD						6				// 50%
#define DIO64_ATTR_INPUTTIMEOUT								7			// 100ms
#define DIO64_ATTR_RTSIGLOBALENABLE						8
#define DIO64_ATTR_RTSICLKSOURCE							9
#define DIO64_ATTR_RTSICLKTRIG7ENABLE					10
#define DIO64_ATTR_EXTERNALCLKENABLE					11
#define DIO64_ATTR_PXICLKENABLE								12
#define DIO64_ATTR_RTSISCANCLKTRIG0ENABLE			13
#define DIO64_ATTR_RTSISTARTTRIG2ENABLE				14
#define DIO64_ATTR_RTSISTOPTRIG3ENABLE				15
#define DIO64_ATTR_RTSIMODSCANCLKTRIG4ENABLE	16
#define DIO64_ATTR_PXISTARENABLE							17
#define DIO64_ATTR_PORTROUTING								18
#define DIO64_ATTR_STATICOUTPUTMASK 					19
#define DIO64_ATTR_SERIALNUMBER								20			// 41165
#define DIO64_ATTR_ARMREENABLE								21			// 0x0	
#define DIO64_ATTR_SCLKENABLE									22		// 0x0	
#define DIO64_ATTR_FPGAINFO										23		// 0x6C00051F


#define DIO64_ERR_ILLEGALBOARD								-8
#define DIO64_ERR_BOARDNOTOPENED							-9
#define DIO64_ERR_STATUSOVERRUNUNDERRUN				-10
#define DIO64_ERR_INVALIDPARAMETER						-12
#define DIO64_ERR_NODRIVERINTERFACE						-13
#define DIO64_ERR_OCXOOPTIONNA								-14
#define DIO64_ERR_PXIONLYSIGNALS							-15
#define DIO64_ERR_STOPTRIGSRCINVALID					-16
#define DIO64_ERR_PORTNUMBERCONFLICTS					-17
#define DIO64_ERR_MISSINGDIO64CATFILE					-18
#define DIO64_ERR_NOTENOUGHRESOURCES					-19
#define DIO64_ERR_INVALIDSIGNITUREDIO64CAT		-20
#define DIO64_ERR_REQUIREDIMAGENOTFOUND				-21
#define DIO64_ERR_ERRORPROGFPGA								-22
#define DIO64_ERR_FILENOTFOUND								-23
#define DIO64_ERR_BOARDERROR									-24
#define DIO64_ERR_FUNCTIONCALLINVALID					-25
#define DIO64_ERR_NOTENOUGHTRANS							-26

// DIO definitions
#ifdef WIN32
#define DIODLL	L"dio64_32.dll"							// name of DIO DLL
#else
#define DIODLL	L"dio64_64.dll"							// name of DIO DLL
#endif
#define DIO64_OK	0										// success code

// attribute values for Get/SetAttr (not in header but taken from Labview, ** -1 from Labview definition)
#define ATTRIB_DEFAULT						0
#define ATTRIB_LONG_VALUE					1
#define ATTRIB_POLLED						1			// **
#define ATTRIB_INTERRUPT					2			// **
#define ATTRIB_PACKET						3			// **
#define ATTRIB_DEMAND						4			// **
#define ATTRIB_LOCAL_CLOCK					6
#define ATTRIB_EXTERNAL_CLOCK				7
#define ATTRIB_RTSI_PXI_CLOCK				8
#define ATTRIB_PRECISION_CLOCK				9
#define ATTRIB_20_MHZ						10
#define ATTRIB_10_MHz						11
#define ATTRIB_PRECISION_OCXO				12
#define ATTRIB_ENABLE						13
#define ATTRIB_DISABLE						14

////////////////////////////////////////////////////////////////////////////////////////
// additional public functions added by Andi
////////////////////////////////////////////////////////////////////////////////////////

// exit all threads. call before unloading DLL!
extern "C" int DLLEXPORT exit_all(void);
typedef int(__stdcall *_exit_all)(void);

// send test command to board
extern "C" int DLLEXPORT test(WORD board, void *data);
typedef int(__stdcall* _test)(WORD board, void *data);

// register callback function with given user data
// set callback = NULL to unregister
// returns 0 on success, otherwise error
// callback is executed by status thread on each status irq
// ensure callback function is thread-safe and user_data is valid until you unregister callback!
typedef int(__stdcall *thread_cb)(DWORD time, DWORD status, void *user_data);
extern "C" int DLLEXPORT register_callback(WORD board, thread_cb callback, void *user_data);
typedef int(__stdcall *_register_callback)(WORD board, thread_cb callback, void *user_data);

// file functions
struct data_info {
	uint32_t* data;					// data buffer
	unsigned samples;				// number of samples in data = number of uint32_t / uint32_per_sample
	struct data_info* next;			// next data buffer or NULL
};

extern "C" __declspec(dllexport) struct data_info* __stdcall load_text_file(const char* filename, unsigned* samples, unsigned uint32_per_sample);
typedef struct data_info*(__stdcall *_load_text_file)(const char* filename, unsigned* samples, unsigned uint32_per_sample);

extern "C" int DLLEXPORT save_text_file(const char* filename, struct data_info* data, unsigned uint32_per_sample);
typedef int(__stdcall *_save_text_file)(const char* filename, struct data_info* data, unsigned uint32_per_sample);

////////////////////////////////////////////////////////////////////////////////////////
// Andi: public function definitions for WinXP and Visa driver
////////////////////////////////////////////////////////////////////////////////////////

// Win7/Visa driver has additional DIO64_OpenResource
extern "C" int DLLEXPORT DIO64_OpenResource(char* resourceName, WORD board, WORD baseio);

// WinXP and Win7/Visa driver functions
extern "C" int DLLEXPORT DIO64_Open(WORD board, WORD baseio);
extern "C" int DLLEXPORT DIO64_Mode(WORD board, WORD mode);
extern "C" int DLLEXPORT DIO64_Load(WORD board, char *rbfFile, int intputHint, int outputHint);
extern "C" int DLLEXPORT DIO64_Close(WORD board);

extern "C" int DLLEXPORT DIO64_In_Start(WORD board,
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
															double *scanRate );

extern "C" int DLLEXPORT DIO64_In_Status(WORD board, DWORD *scansAvail, DIO64STAT *status);
extern "C" int DLLEXPORT DIO64_In_Read(WORD board, WORD *buffer, DWORD scansToRead, DIO64STAT *status);

extern "C" int DLLEXPORT DIO64_In_Stop(WORD board);

extern "C" int DLLEXPORT DIO64_Out_ForceOutput(WORD board, WORD *buffer, DWORD mask);
extern "C" int DLLEXPORT DIO64_Out_GetInput(WORD board, WORD *buffer);
extern "C" int DLLEXPORT DIO64_Out_Config(WORD board,
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

													);
extern "C" int DLLEXPORT DIO64_Out_Start(WORD board);

extern "C" int DLLEXPORT DIO64_Out_Status(
														WORD board,
														DWORD *scansAvail,
														DIO64STAT *status);

extern "C" int DLLEXPORT DIO64_Out_Write(WORD board, WORD *buffer, DWORD bufsize, DIO64STAT *status);
extern "C" int DLLEXPORT DIO64_Out_Stop(WORD board);

extern "C" int DLLEXPORT DIO64_SetAttr(WORD board, DWORD attrID, DWORD value);
//int DLLEXPORT DIO64_GetAttr(WORD board, DWORD *attrID, DWORD *value); // this is wrong in original header!
extern "C" int DLLEXPORT DIO64_GetAttr(WORD board, DWORD attrID, DWORD *value);

////////////////////////////////////////////////////////////////////////////////////////
// Andi: typedefs for convenience to manually use LoadLibrary and GetProcAddress
////////////////////////////////////////////////////////////////////////////////////////

typedef int(__stdcall *_DIO64_OpenResource)(char* resourceName, WORD board, WORD baseio);
typedef int(__stdcall *_DIO64_Open)(WORD board, WORD baseio);
typedef int(__stdcall *_DIO64_Load)(WORD board, char *rbfFile, int intputHint, int outputHint);
typedef int(__stdcall *_DIO64_Close)(WORD board);
typedef int(__stdcall *_DIO64_GetAttr)(WORD board, DWORD attrID, DWORD *value);					// below and in Labview "*attrID" defined but returns error -12 (Invalid parameter)
typedef int(__stdcall *_DIO64_SetAttr)(WORD board, DWORD attrID, DWORD value);
typedef int(__stdcall *_DIO64_Out_Config)(WORD board, DWORD ticks, WORD *mask, WORD maskLength, WORD flags, WORD clkControl, WORD startType, WORD startSource, WORD stopType, WORD stopSource, DWORD AIControl, DWORD reps, WORD ntrans, double *scanRate);
typedef int(__stdcall *_DIO64_Out_Status)(WORD board, DWORD *scansAvail, DIO64STAT *status);
typedef int(__stdcall *_DIO64_Out_Write)(WORD board, WORD *buffer, DWORD bufsize, DIO64STAT *status);
typedef int(__stdcall *_DIO64_Out_Start)(WORD board);
typedef int(__stdcall *_DIO64_Out_Stop)(WORD board);
typedef int(__stdcall *_DIO64_Out_ForceOutput)(WORD board, WORD *buffer, DWORD mask);
typedef int(__stdcall *_DIO64_Out_GetInput)(WORD board, WORD *buffer);
typedef int(__stdcall *_DIO64_In_Start)(WORD board, DWORD ticks, WORD *mask, WORD maskLength, WORD flags, WORD clkControl, WORD startType, WORD startSource, WORD stopType, WORD stopSource, DWORD AIControl, double *scanRate);
typedef int(__stdcall *_DIO64_In_Stop)(WORD board);
typedef int(__stdcall *_DIO64_In_Status)(WORD board, DWORD *scansAvail, DIO64STAT *status);
typedef int(__stdcall *_DIO64_In_Read)(WORD board, WORD *buffer, DWORD scansToRead, DIO64STAT *status);

#endif
