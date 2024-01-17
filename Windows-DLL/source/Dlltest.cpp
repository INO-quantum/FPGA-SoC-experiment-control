////////////////////////////////////////////////////////////////////////////////////////
// Dlltest.cpp
// Win32/64 test of DLL
// created 27/11/2019 by Andi
// command line arguments: 
// '-c' followed by 'IP:port' of board. add for each board.
// '-f' followed by path + file with user data
// '-r' followed by number of repetitions
// '-s' followed by the number of samples
// '-v' vary number of samples down to 4 in powers of 2
// '-t' send test command at end
// examples:
// Dlltest -c 192.168.1.120:49701 -c 192.168.1.121:49701 -s 1000000 -r 50
// Dlltest -f C:/Andi/programming/dio64_32/test_data.txt -r 0
////////////////////////////////////////////////////////////////////////////////////////

// for single board: set LINKED_BOARDS = 0 and check command line uses only one -c option.

#include "Dio24.h"					// header
#include <stdio.h>					// printf
#include <conio.h>					// getch

#define MAX_SHOW		20			// maximum number of samples to display for show_data

// define number of linked boards: 0=none or >=2
// for linked boards all functions called for primary board are automatically called for secondary boards.
#define LINKED_BOARDS	0
#if (LINKED_BOARDS != 0)
#define BASE_IO		LINKED_BOARDS	// default 0x180 or 0x00, otherwise number of linked boards.
#else
#define BASE_IO		BASE_IO_DEFAULT	// default 0x180 or 0x00, otherwise number of linked boards.
#endif

#define NAME		"DLL test: "
#define BOARD_ID	0			// user selected board ID, has to remain the same. distinguishes different boards.
#define CYCLES		1			// number of cyles. 0 = infinite, 1 = normal, >1 number of cycles
#define MS			1000
#define SEC			1000000
#define VOLT(x)		((32767*(x))/10)
#define LOOPS		1			// number of repetitions with opening/closing device with changing number of samples using NEXT_SAMPLES
#define REPS_1		1			// number of repetitions with opening/closing device with same number of samples
#define REPS_2		1			// number of repetitions without opening/closing device		
#define SAMPLES		500000		// number of samples
#define NEXT_SAMPLES(s)	(s>>1)	// recalculates samples in each loop

// define to test sending 12bytes/sample with DLL and sending 8bytes/sample to primary and secondary boards (Yb LabWindows/CVI)
// ignored when BYTES_PER_SAMPLE != 8
#define GET_12_SEND_8

#ifdef GET_12_SEND_8
#if ( DIO_BYTES_PER_SAMPLE == 8 )
#define CREATE_DATA_BYTES_PER_SAMPLE	12
#else
#define CREATE_DATA_BYTES_PER_SAMPLE	DIO_BYTES_PER_SAMPLE
#endif
#else
#define CREATE_DATA_BYTES_PER_SAMPLE	DIO_BYTES_PER_SAMPLE
#endif

// if defined start each run with external trigger on primary board. 
// 0 = level low, 1 = level high, 2 = falling edge, 3 = risign edge (preferred)
// 4 = edge-to-edge rising, 5 = edge-to-edge falling. 
// options 4 and 5 are incompatible with STOP_TRIGGER.
//#define START_TRIGGER	4

// if defined enable stop trigger on primary and secondary boards. 2 = falling edge, 3 = rising edge.
// STOP_TRIGGER with START_TRIGGER defined as edge-to-edge (option 4 or 5) is not allowed since this automatically enables STOP/RESTART_TRIGGERS.
// restart trigger with same config as START_TRIGGER is automatically enabled for each board by DLL when STOP_TRIGGER is defined.
// in DIO64 manual v.1.04: the rising/falling edge definition is inverted with respect to start trigger. we ignore this and keep same definition!
//                         the definitions for the different drivers might be also different/inconsistent.
// TODO: for secondary board this requires that START_TRIGGER is configured with falling edge (option 2) since sync_out is at falling edge.
//       for board versions > 1.2 a different restart trigger channel could be given releasing this constraint.
//#define STOP_TRIGGER	2

#ifdef START_TRIGGER
#if ( START_TRIGGER == 0 ) // level low
#define START_SOURCE	DIO64_STRT_EXTERNAL
#define START_TYPE		DIO64_STRTTYPE_LEVEL | DIO64_TRIG_FALLING
#elif ( START_TRIGGER == 1 ) // level high
#define START_SOURCE	DIO64_STRT_EXTERNAL
#define START_TYPE		DIO64_STRTTYPE_LEVEL | DIO64_TRIG_RISING
#elif ( START_TRIGGER == 2 ) // falling edge
#define START_SOURCE	DIO64_STRT_EXTERNAL
#define START_TYPE		DIO64_STRTTYPE_EDGE | DIO64_TRIG_FALLING
#elif ( START_TRIGGER == 3 ) // rising edge
#define START_SOURCE	DIO64_STRT_EXTERNAL
#define START_TYPE		DIO64_STRTTYPE_EDGE | DIO64_TRIG_RISING
#elif ( START_TRIGGER == 4 ) // edge-to-edge rising (do not define STOP_TRIGGER)
#define START_SOURCE	DIO64_STRT_EXTERNAL
#define START_TYPE		DIO64_STRTTYPE_EDGETOEDGE | DIO64_TRIG_RISING
#elif ( START_TRIGGER == 5 ) // edge-to-edge falling (do not define STOP_TRIGGER)
#define START_SOURCE	DIO64_STRT_EXTERNAL
#define START_TYPE		DIO64_STRTTYPE_EDGETOEDGE | DIO64_TRIG_FALLING
#endif
#else
#define START_SOURCE	DIO64_STRT_NONE
#define START_TYPE		DIO64_STRTTYPE_EDGE
#endif

#ifdef STOP_TRIGGER
#if ( STOP_TRIGGER == 2 ) // falling edge
#define STOP_SOURCE		DIO64_STOP_EXTERNAL
#define STOP_TYPE		DIO64_STOPTYPE_EDGE | DIO64_TRIG_FALLING
#elif ( STOP_TRIGGER == 3 ) // rising edge
#define STOP_SOURCE		DIO64_STOP_EXTERNAL
#define STOP_TYPE		DIO64_STOPTYPE_EDGE | DIO64_TRIG_RISING
#endif
#else
#define STOP_SOURCE		DIO64_STOP_NONE
#define STOP_TYPE		DIO64_STOPTYPE_EDGE
#endif

////////////////////////////////////////////////////////////////////////////////////////
// test data
////////////////////////////////////////////////////////////////////////////////////////

// test data for device address ADDR
// data is in little-endian byte order (LSB first)!
// data sample = 32bit time (in mu, max. >1h), 16bit data, 7bit address, 1bit strobe, 8bit 0s
//#define GET_TIME(ms)			(((ms)*1000) & 0xffff),((((ms)*1000) >> 16) & 0xffff)
//#define GET_MU(us)				((us) & 0xffff),(((us) >> 16) & 0xffff)

/* digital out
#define ADDR					0x01
#define TEST_DATA_NUM_SAMPLES	19
WORD test_data[TEST_DATA_NUM_SAMPLES * 4] = {
	 GET_TIME(100) , 0xffff, ADDR,
	 GET_TIME(200) , 0x0001, ADDR,
	 GET_TIME(300) , 0x0002, ADDR,
	 GET_TIME(400) , 0x0004, ADDR,
	 GET_TIME(500) , 0x0008, ADDR,
	 GET_TIME(600) , 0x0010, ADDR,
	 GET_TIME(700) , 0x0020, ADDR,
	 GET_TIME(800) , 0x0040, ADDR,
	 GET_TIME(900) , 0x0080, ADDR,
	 GET_TIME(1000), 0x0100, ADDR,
	 GET_TIME(1100), 0x0200, ADDR,
	 GET_TIME(1200), 0x0400, ADDR,
	 GET_TIME(1300), 0x0800, ADDR,
	 GET_TIME(1400), 0x1000, ADDR,
	 GET_TIME(1500), 0x2000, ADDR,
	 GET_TIME(1600), 0x4000, ADDR,
	 GET_TIME(1700), 0x8000, ADDR,
	 GET_TIME(1800), 0xffff, ADDR,
	 GET_TIME(1900), 0x0000, ADDR
};*/

/* shutter tests
#define SHIFT 100	// shift timer 0 (100) vs. timer 1 (0) since have slightly different frequencies
// trigger on falling edge ch0
#define ADDR					0x01
#define TEST_DATA_NUM_SAMPLES	4
WORD test_data1[TEST_DATA_NUM_SAMPLES * 4] = {
	GET_MU(0), 0x00ff, ADDR,
	GET_MU(16000 + SHIFT), 0xff00, ADDR,	// trg 0, pulse start -0.5ms before falling edge with overlap
	GET_MU(31000 + 2*SHIFT), 0x00ff, ADDR,
	GET_MU(48000 + 3*SHIFT), 0xff00, ADDR		// trg 1, pulse end -0.5ms before falling edge without overlap
	//GET_MU(47500+3*SHIFT), 0xff00, ADDR		// trg 1, pulse end right at falling edge with overlap
	//GET_MU(46400+3*SHIFT), 0xff00, ADDR		// trg 1, pulse start right before falling edge with overlap
	//GET_MU(46300+3*SHIFT), 0xff00, ADDR		// trg 1, pulse start right after falling edge no overlap (=no pulse)
};
// shutter test
// trigger on rising edge ch15
#define ADDR					0x01
#define TEST_DATA_NUM_SAMPLES	4
WORD test_data[TEST_DATA_NUM_SAMPLES * 4] = {
	GET_MU(0), 0x00ff, ADDR,
	GET_MU(15700 + SHIFT), 0xff00, ADDR,	// trg 0, pulse start -0.5ms before rising edge with overlap
	GET_MU(31000 + 2*SHIFT), 0x00ff, ADDR,
	//GET_MU(47700+3*SHIFT), 0xff00, ADDR		// trg 1, pulse end -0.5ms before rising edge without overlap
	//GET_MU(47000+3*SHIFT), 0xff00, ADDR		// trg 1, pulse end right at rising edge with overlap
	//GET_MU(46400 + 3*SHIFT), 0xff00, ADDR		// trg 1, pulse start right before rising edge with overlap
	GET_MU(46300+3*SHIFT), 0xff00, ADDR		// trg 1, pulse start right after rising edge no overlap (=no pulse)
};*/


/* DDS index
#define ADDR					0x01
#define TEST_DATA_NUM_SAMPLES	40
//#define PATTERN(x)				((x)|0x4400)		// AD9958: x=index into LUT, bits 10,14 = set output immediately
#define PATTERN(x)				((x)|0x4200)			// AD9854: x=index into LUT, bits 9,14 = set output immediately
WORD test_data[TEST_DATA_NUM_SAMPLES * 4] = {
	GET_TIME( 250), PATTERN(0), ADDR,
	GET_TIME( 500), PATTERN(1), ADDR,
	GET_TIME( 750), PATTERN(2), ADDR,
	GET_TIME(1000), PATTERN(3), ADDR,
	GET_TIME(1250), PATTERN(4), ADDR,
	GET_TIME(1500), PATTERN(5), ADDR,
	GET_TIME(1750), PATTERN(6), ADDR,
	GET_TIME(2000), PATTERN(7), ADDR,
	GET_TIME(2250), PATTERN(8), ADDR,
	GET_TIME(2500), PATTERN(9), ADDR,
	GET_TIME(2750), PATTERN(10), ADDR,
	GET_TIME(3000), PATTERN(11), ADDR,
	GET_TIME(3250), PATTERN(12), ADDR,
	GET_TIME(3500), PATTERN(13), ADDR,
	GET_TIME(3750), PATTERN(14), ADDR,
	GET_TIME(4000), PATTERN(15), ADDR,
	GET_TIME(4250), PATTERN(16), ADDR,
	GET_TIME(4500), PATTERN(17), ADDR,
	GET_TIME(4750), PATTERN(18), ADDR,
	GET_TIME(5000), PATTERN(19), ADDR,
	GET_TIME(5250), PATTERN(20), ADDR,
	GET_TIME(5500), PATTERN(21), ADDR,
	GET_TIME(5750), PATTERN(22), ADDR,
	GET_TIME(6000), PATTERN(23), ADDR,
	GET_TIME(6250), PATTERN(24), ADDR,
	GET_TIME(6500), PATTERN(25), ADDR,
	GET_TIME(6750), PATTERN(26), ADDR,
	GET_TIME(7000), PATTERN(27), ADDR,
	GET_TIME(7250), PATTERN(28), ADDR,
	GET_TIME(7500), PATTERN(29), ADDR,
	GET_TIME(7750), PATTERN(30), ADDR,
	GET_TIME(8000), PATTERN(31), ADDR,
	GET_TIME(8250), PATTERN(32), ADDR,
	GET_TIME(8500), PATTERN(33), ADDR,
	GET_TIME(8750), PATTERN(34), ADDR,
	GET_TIME(9000), PATTERN(35), ADDR,
	GET_TIME(9250), PATTERN(36), ADDR,
	GET_TIME(9500), PATTERN(37), ADDR,
	GET_TIME(9750), PATTERN(38), ADDR,
	GET_TIME(10000), PATTERN(39), ADDR
};*/

////////////////////////////////////////////////////////////////////////////////////////
// generates test data linear ramps
////////////////////////////////////////////////////////////////////////////////////////

//typedef short			int16_t;		// signed WORD
//typedef unsigned short	uint16_t;		// WORD
//typedef unsigned long	uint32_t;		// DWORD
//typedef unsigned char	uint8_t;		// BYTE

#define STRB_TOGGLE_BIT			(1<<23)
#define DIO_DATA_MASK_NO_TGL	(DIO_DATA_MASK ^ STRB_TOGGLE_BIT)

// generates samples starting at t_start us with t_step time. 
// data starts at d_start and increments with d_step
// notes: 
// - good for creating big data for board tests but do not use with devices in rack since data is random!
// - usage: pdata = test_step(1024*100/*100ks*/, 0/*start 0us*/, 1/*step 1us*/, 0x030201/*data start pattern*/, 0x010101/*data increment*/);
uint32_t* test_step(uint32_t samples, uint32_t t_start, uint32_t t_step, uint32_t d_start, uint32_t d_step, int bytes_per_sample) {
	uint32_t *buf, *p, s, tgl = 0;
	p = buf = new uint32_t[((size_t)samples) * bytes_per_sample / sizeof(uint32_t)];
	if (bytes_per_sample == 8) {
		for (s = 0; s < samples; ++s, t_start += t_step) {
			*p++ = t_start;
			*p++ = (DIO_DATA_MASK_NO_TGL & d_start) | tgl;
			d_start += d_step;
			tgl ^= STRB_TOGGLE_BIT;
		}
	}
	else if (bytes_per_sample == 12) {
		for (s = 0; s < samples; ++s, t_start += t_step) {
			*p++ = t_start;
			*p++ = (DIO_DATA_MASK_NO_TGL & d_start) | tgl;
			d_start += d_step;
			tgl ^= STRB_TOGGLE_BIT;
			*p++ = (DIO_DATA_MASK_NO_TGL & d_start) | tgl;
			d_start += d_step;
		}
	}
	return buf;
}

// linear analog ramp on address for {time in mu, voltage} = {t_start,u_start} to {t_end,u_end} in steps
// returns pointer to data, delete[] after use!
uint16_t *analog_ramp(uint8_t address, uint32_t t_start, uint32_t t_end, int16_t u_start, int16_t u_end, int steps) {
	uint32_t time;
	uint16_t *data = new uint16_t[((size_t)steps)*4];
	uint16_t *p;
	if (data) {
		p = data;
		for (int i = 0; i < steps; i++) {
			time = t_start + ((t_end - t_start)*i) / (steps-1);
			*p++ = time & 0xffff;
			*p++ = (time >> 16) & 0xffff;
			*p++ = (uint16_t)(u_start + ((u_end - u_start)*i) / (steps - 1));
			*p++ = (uint16_t) address;
		}
	}
	return data;
}

// digital ramp on address for {time in mu, output} = {t_start,u_start} to {t_end,u_start<<u_step*(steps-1))} in steps
// returns pointer to data, delete[] after use!
// u_start, u_step, steps alows different pattern: 
// 0x0001, 1,16		= TTL 0 - 15 is high, one after the next for each step
// 0x8000,-1,16		= TTL 15 - 0 is high, one after the next for each step
// 0x0003, 1,15		= TTL 0&1,1&2,2&3 - 13&14,14&15 is high, one after the next for each step
// 0x0005, 2,7		= TTL 0&2,2&4,4&6 - 12&14 is high, one after the next for each step
uint16_t *digital_ramp(uint8_t address, uint32_t t_start, uint32_t t_end, uint16_t u_start, int16_t u_step, int steps) {
	uint32_t time;
	uint16_t *data = new uint16_t[((size_t)steps) * 4];
	uint16_t *p;
	if (data) {
		p = data;
		for (int i = 0; i < steps; i++) {
			time = t_start + ((t_end - t_start)*i) / (steps - 1);
			*p++ = time & 0xffff;
			*p++ = (time >> 16) & 0xffff;
			*p++ = u_start;
			*p++ = (uint16_t)address;
			if (u_step > 0) u_start <<= u_step;
			else u_start >>= (-u_step);
		}
	}
	return data;
}

// shutter test on address from t_start to t_end in ms in steps
// returns pointer to data, delete[] after use!
uint16_t *shutter_test(uint8_t address, uint32_t t_start, uint32_t t_end, int steps) {
	uint32_t t_off = 12500 / steps; // microseconds each pulse is delayed more
	uint32_t time = t_start, t_step = (t_end - t_start) / (steps - 1) - t_off * steps;
	uint16_t *data = new uint16_t[((size_t)steps) * 4];
	uint16_t *p;
	uint16_t u = 0xf0f0;
	if (data) {
		p = data;
		for (int i = 0; i < steps; i++, u = ~u, t_step += t_off) {
			time += t_step;
			*p++ = time & 0xffff;
			*p++ = (time >> 16) & 0xffff;
			*p++ = u;
			*p++ = (uint16_t)address;
		}
	}
	return data;
}

uint16_t *set_value(uint8_t address, uint32_t time, int16_t u) {
	uint16_t *p, *data = new uint16_t[4];
	if (data) {
		p = data;
		*p++ = time & 0xffff;
		*p++ = (time >> 16) & 0xffff;
		*p++ = (uint16_t)u;
		*p++ = (uint16_t)address;
	}
	return data;
}

// show data. maximum MAX_SHOW samples.
void show_data(uint16_t *data, int samples, int bytes_per_sample) {
	uint32_t i, n, num, time, start[2], end[2], k = bytes_per_sample / sizeof(uint16_t);
	uint16_t* d;
	if (samples > MAX_SHOW) {
		num		 = 2;
		start[0] = 0;
		end[0]   = MAX_SHOW / 2;
		start[1] = samples - MAX_SHOW / 2;
		end[1]   = samples;
	}
	else {
		num		 = 1;
		start[0] = 0;
		end[0]   = samples;
	}
	for (n = 0; n < num; ++n) {
		d = data + ((size_t)start[(size_t)n]) * (size_t)k;
		for (i = start[n]; i < end[n]; ++i, d += k) {
			time = d[0];
			time |= d[1] << 16;
			if (bytes_per_sample == 8)
				printf("%6i %04x_%04x %04x_%04x (%uus)\n", i, d[1], d[0], d[3], d[2], time);
			else if (bytes_per_sample == 12)
				printf("%6i %04x_%04x %04x_%04x %04x_%04x (%uus)\n", i, d[1], d[0], d[3], d[2], d[5], d[4], time);
		}
	}
}

uint32_t show_status(int board, DIO64STAT *status, uint32_t scansAvail) {
	static char st_non[] = "not started";
	static char st_run[] = "run";
	static char st_end[] = "end";
	static char st_err[] = "error";
	static char st_err_run[] = "run|error";
	static char st_err_end[] = "end|error";
	char* st_ptr;
	uint32_t status_FPGA = status->flags | (status->clkControl << 16);
	if (status_FPGA & DIO_STATUS_ERROR)    st_ptr = (status_FPGA & DIO_STATUS_RUN) ? st_err_run : (status_FPGA & DIO_STATUS_END) ? st_err_end : st_err;
	else if (status_FPGA & DIO_STATUS_END) st_ptr = st_end;
	else if (status_FPGA & DIO_STATUS_RUN) st_ptr = st_run;
	else st_ptr = st_non;
	if (status->ticks >= 1000000) {
		printf("%i: FPGA time %8u us, # %8u, status 0x%8x (%us, %s)\n", board, status->ticks, scansAvail, status_FPGA, status->ticks / 1000000, st_ptr);
	}
	else {
		printf("%i: FPGA time %8u us, # %8u, status 0x%8x (%s)\n", board, status->ticks, scansAvail, status_FPGA, st_ptr);
	}
	return status_FPGA;
}

////////////////////////////////////////////////////////////////////////////////////////
// application entry
////////////////////////////////////////////////////////////////////////////////////////

// main application start
int main(int argc, char* argv[])
{
	int	err = 0;					// error if nonzero
	int loop = 0, samples = SAMPLES, reps_1, reps_2, vary = 1;
	DIO64STAT* status[MAX_NUM_BOARDS] = { NULL };
	bool test_cmd = false, wait_dlg = true, no_primary = false;
	bool run[MAX_NUM_BOARDS];
	int l, tmp;
#if DIO_BYTES_PER_SAMPLE == 8
	#ifdef GET_12_SEND_8
		// this mask defines that Out_Write recieves 12 bytes/sample and DLL sends 8 bytes/sample to each board
		// primary board gets first 8 bytes and secondary first 4 bytes and last 4 bytes.
		WORD mask[4] = { 0xffff, 0xffff, 0xffff, 0xffff }; // port a+b+c+d = Yb
	#else
		WORD mask[4] = { 0xffff, 0xffff, 0x0000, 0x0000 }; // port a+b = K39,LiCr
	#endif
#else
	WORD mask[4] = { 0xffff, 0xffff, 0xffff, 0xffff }; // port a+b+c+d = Yb
#endif
	double scanRate = 1000000; // scan rate in Hz
	int i, user_reps = REPS_1, user_samples = SAMPLES;
	char* user_file = NULL;
	char* board_IP[MAX_NUM_BOARDS] = {NULL};	// IP:port address for each board. MAX_NUM_BOARDS can be given. if none given use default with DIO64_Open.
	WORD board_hdl[MAX_NUM_BOARDS] = {0};		// board handles returned by Open/OpenResource
	int num_boards = 0;			// count number of given boards. if none given use default = 1.
	int num_boards_loop = 0;	// number of boards to loop over. depends if boards are linked or not.
	struct data_info* user_data = NULL;
	ULONG old_time[MAX_NUM_BOARDS];
	bool use_OpenResource = false;	// true when option -c is used

	printf(NAME "test program by Andi for Windows DLL:\n");
	printf(DLL_INFO "\n\n");

	// parse command line arguments.
	if (argc > 1) {
		for (i = 1; (i < argc) && (!err); ++i) {
			if ((argv[i][0] == '-') && (argv[i][1] != '\0') && (argv[i][2] == '\0')) {
				switch (argv[i][1]) {
				case 'c':
					use_OpenResource = true;
					if (++i >= argc) {
						printf(NAME "no IP:port given for option \"%s\"\n", argv[i - 1]);
						err = 3;
					}
					else if (num_boards >= MAX_NUM_BOARDS) {
						printf(NAME "exceeded maximum number of boards %i option \"%s\"\n", MAX_NUM_BOARDS, argv[i - 1]);
						err = 3;
					}
					else { // give board IP:port
						board_IP[num_boards] = argv[i];
						printf(NAME "board %i '%s'\n", num_boards, argv[i]);
						++num_boards;
					}
					break;
				case 'f':
					if (++i >= argc) {
						printf(NAME "no filename given for option \"%s\"\n", argv[i - 1]);
						err = 3;
					}
					else { // load file
						user_file = argv[i];
						printf(NAME "loading data from file \"%s\"\n", user_file);
					}
					break;
				case 'r':
					if (++i >= argc) {
						printf(NAME "no number given for option \"%s\"\n", argv[i - 1]);
						err = 40;
					}
					else { // parse number
						err = sscanf_s(argv[i], "%u", &user_reps);
						if (err != 1) {
							printf(NAME "error reading number \"%s\"\n", argv[i]);
							err = 41;
							user_reps = REPS_1;
						}
						else {
							err = 0;
							if (user_reps != 0)	printf(NAME "%d repetitions\n", user_reps);
							else                printf(NAME "loop until key pressed\n");
						}
					}
					break;
				case 's':
					if (++i >= argc) {
						printf(NAME "no number given for option \"%s\"\n", argv[i - 1]);
						err = 50;
					}
					else { // parse number
						err = sscanf_s(argv[i], "%u", &user_samples);
						if (err != 1) {
							printf(NAME "error reading number \"%s\"\n", argv[i]);
							err = 51;
							user_samples = SAMPLES;
						}
						else {
							err = 0;
							printf(NAME "%d samples\n", user_samples);
						}
					}
					break;
                case 'v':
					printf(NAME "vary number of samples.\n");
                    vary = 2;
					break;
				case 't':
					printf(NAME "test.\n");
					test_cmd = true;
					break;
				default:
					printf(NAME "illegal command line argument: \"%s\"\n", argv[i]);
					err = 2;
				}
			}
			else err = 1;
		}
	}
	else {
		if (user_reps == 0) {
			printf(NAME "execute test sequence of %d samples until key pressed\n", user_samples);
		}
		else {
			printf(NAME "execute test sequence of %d samples for %d repetitions\n", user_samples, user_reps);
		}
		printf(NAME "ATTENTION: ensure no devices are connceted since this sends random data to board\n");
		printf(NAME "do you want to continue <y/n> ?\n");
		char c = 'N';
		if (scanf_s("%c", &c, 1) != 1) err = -10;
		else if ((c != 'Y') && (c != 'y')) {
			printf(NAME "aborted\n");
			err = -11;
		}
	}

	if (err) {
		printf(NAME "command line arguments:\n");
		printf(NAME "'-c <IP:port>'  = connect to board at IP:port (max. %i boards)\n", MAX_NUM_BOARDS);
		printf(NAME "'-f <filename>' = load data from text file\n");
		printf(NAME "'-r <#>'        = repeat # times (0=until key pressed)\n");
		printf(NAME "'-s <#>'        = use # samples\n");
		printf(NAME "'-v             = vary # samples down to 4 in powers of 2\n");
	}
	else {
		// ensure there is at least one board. if none is defined as arguments then one default is assumed
		if (num_boards == 0) num_boards = 1;

		// load library
		HMODULE module = LoadLibrary(DIODLL);
		if (module == NULL)
		{
			printf(NAME "loading of DLL failed!\n");
			err = 10;
		}
		else
		{
			// get function pointers
			_exit_all				exit_all			= (_exit_all)				GetProcAddress(module, "exit_all");
			_test					test				= (_test)					GetProcAddress(module, "test");
			_register_callback		register_callback	= (_register_callback)		GetProcAddress(module, "register_callback");
			_load_text_file			load_text_file		= (_load_text_file)			GetProcAddress(module, "load_text_file");
			_save_text_file			save_text_file		= (_save_text_file)			GetProcAddress(module, "save_text_file");
			_DIO64_OpenResource		DIO64_OpenResource	= (_DIO64_OpenResource)		GetProcAddress(module, "DIO64_OpenResource");
			_DIO64_Open				DIO64_Open			= (_DIO64_Open)				GetProcAddress(module, "DIO64_Open");
			_DIO64_Load				DIO64_Load			= (_DIO64_Load)				GetProcAddress(module, "DIO64_Load");
			_DIO64_Close			DIO64_Close			= (_DIO64_Close)			GetProcAddress(module, "DIO64_Close");
			_DIO64_Out_Config		DIO64_Out_Config	= (_DIO64_Out_Config)		GetProcAddress(module, "DIO64_Out_Config");
			_DIO64_Out_Status		DIO64_Out_Status	= (_DIO64_Out_Status)		GetProcAddress(module, "DIO64_Out_Status");
			_DIO64_Out_Write		DIO64_Out_Write		= (_DIO64_Out_Write)		GetProcAddress(module, "DIO64_Out_Write");
			_DIO64_Out_Start		DIO64_Out_Start		= (_DIO64_Out_Start)		GetProcAddress(module, "DIO64_Out_Start");
			_DIO64_Out_Stop			DIO64_Out_Stop		= (_DIO64_Out_Stop)			GetProcAddress(module, "DIO64_Out_Stop");
			_DIO64_Out_ForceOutput	DIO64_Out_Force		= (_DIO64_Out_ForceOutput)	GetProcAddress(module, "DIO64_Out_ForceOutput");

			if ((!exit_all) || (!register_callback) || (!load_text_file) || (!save_text_file) ||
				(!DIO64_OpenResource) || (!DIO64_Load) || (!DIO64_Close) || (!DIO64_Out_Config) || (!DIO64_Out_Status) ||
				(!DIO64_Out_Write) || (!DIO64_Out_Start) || (!DIO64_Out_Stop) || (!DIO64_Out_Force)) {
				printf("DLL test could not load all function pointers!\n");
				err = 20;
			}
			else {
				if (user_file != NULL) {
					// load file if specified
#if ( DIO_BYTES_PER_SAMPLE == 8 ) 
#ifdef GET_12_SEND_8
					// expect 3 columns per sample
					user_data = load_text_file(user_file, (unsigned int*)&samples, 12 / sizeof(uint32_t));
#else
					// expect 2 columns per sample
					user_data = load_text_file(user_file, (unsigned int*)&samples, DIO_BYTES_PER_SAMPLE / sizeof(uint32_t));
#endif
#else
					// expect 2 columns per sample
					user_data = load_text_file(user_file, (unsigned int*)&samples, DIO_BYTES_PER_SAMPLE / sizeof(uint32_t));
#endif
					if ((user_data == NULL) || (samples == 0)) {
						printf(NAME "could not load file \"%s\"\n", user_file);
						samples = 0;
						user_data = NULL;
						err = 21;
					}
					else {
						printf(NAME "%d samples loaded ok\n", samples);
					}
				}
				else {
                    if (vary > 1) {
                        // use next lower power of 2 for number of samples
                        for (vary = 0; user_samples > 0; user_samples = user_samples>>1, ++vary);
                        user_samples = 1 << (vary-1);
                        vary = vary-2; // stop at 4
                    }
					samples = user_samples;
				}
				if (!err) {
					// define number of boards to loop over. depends if boards are linked or not
#if ( LINKED_BOARDS == 0 )
					// no linked boards: loop over all boards
					num_boards_loop = num_boards;
#else
					// linked boards: no loop. call for primary board only.
					num_boards_loop = 1;
#endif

					for (loop = 0; (loop < vary) && (!err); ++loop, samples = NEXT_SAMPLES(samples)) {
						if (samples < 4) break;

						for (reps_1 = 0; (!err); ++reps_1) {
							if (user_reps > 0) {
								if (reps_1 < user_reps) {
									printf("\n" NAME "loop %d/%d rep %d/%d samples %d/%d\n", loop, vary, reps_1, user_reps, samples, user_samples);
								}
								else {
									printf("\n" NAME "loop %d/%d rep %d/%d samples %d/%d (finished)\n", loop, vary, reps_1, user_reps, samples, user_samples);
									break;
								}
							}
							else {
								if (_kbhit()) {
									printf("\n" NAME "loop %d/%d rep %d samples %d/%d (finished)\n", loop, vary, reps_1, samples, user_samples);
									break;
								}
								else {
									printf("\n" NAME "loop %d/%d rep %d samples %d/%d\n", loop, vary, reps_1, samples, user_samples);
								}
							}
							if (loop > 0) Sleep(100);
							if (use_OpenResource) {
								// open boards at given IP:port and increment BOARD_ID
								// if connection fails and user selects 'Abort' application stops.
								// if he select 'Ignore' for a board application opens all other boards,
								// however, if the ignored board is the primary one, the secondary boards cannot be triggered.
								// they are then programmed as independent primary boards without external clock and without ext sync!
								for (i = 0; i < num_boards_loop; ++i) {
									err = DIO64_OpenResource(board_IP[i], BOARD_ID + i, BASE_IO);
									if (err > 0) {
										board_hdl[i] = (WORD)err;
										err = 0;
										printf(NAME "%i: OpenResource ok (handle 0x%04x)\n", i, board_hdl[i]);
									}
									else if (err == ERROR_CONNECT_IGNORE) {
										if (i == 0) {
											no_primary = true; // primary board ignored
											printf("\n" NAME "%i: OpenResource warning %d: primary board ignored!\nSecondary boards will be programmed without external clock and cannot be hardware trittered!", i, err);
										}
										else printf("\n" NAME "%i: OpenResource warning %d: secondary ignored!\n", i, err);
										printf("continue with any key!");
										_getch();
										printf("\n\n");
										loop = LOOPS; // execute only a single loop
									}
									else {
										printf(NAME "%i: OpenResource error %d\n", i, err);
										num_boards = i; // this ensures to close already openened boards but not more.
										break;
									}
								}
							}
							else {
								// open single board or linked boards with default IP
								err = DIO64_Open(BOARD_ID, BASE_IO);
								if (err > 0) {
									board_hdl[0] = (WORD) err;
									err = 0;
									printf(NAME "OpenResource ok (handle 0x%04x)\n", board_hdl[0]);
								}
								else if (err == ERROR_CONNECT_IGNORE) {
									printf("\n" NAME "OpenResource warning %d: board ignored!\n", err);
									printf("continue with any key!");
									_getch();
									printf("\n\n");
									loop = LOOPS; // execute only a single loop
								}
								else printf(NAME "OpenResource error %d\n", err);
							}
							if (err && (err != ERROR_CONNECT_IGNORE)) goto test_error;
							err = 0;
							// does not do anything, should not fail
							for (i = 0; (i < num_boards_loop) && (!err); ++i) {
								err = DIO64_Load(board_hdl[i], NULL, 0, 4);
							}
							if (err) {
								printf(NAME "Load returned %d\n", err);
								goto test_error;
							}
							else printf(NAME "Load ok\n");

							// configure boards
							// first board = primary, all other boards = secondary
							for (i = 0; (i < num_boards_loop) && (!err); ++i) {
								if ((i == 0) || no_primary) { // primary board
									err = DIO64_Out_Config(board_hdl[i], 0, mask, 4, 0, DIO64_CLCK_INTERNAL,
										START_TYPE, START_SOURCE, STOP_TYPE, STOP_SOURCE,
										DIO64_AI_NONE, CYCLES, 0, &scanRate);
								}
								else { // secondary board: enable external clock and sync_in trigger (auto-sync)
									err = DIO64_Out_Config(board_hdl[i], 0, mask, 4, 0, DIO64_CLCK_EXTERNAL,
										DIO64_STRTTYPE_EDGE | DIO64_TRIG_FALLING, DIO64_STRT_EXTERNAL, STOP_TYPE, STOP_SOURCE,
										DIO64_AI_NONE, CYCLES, 0, &scanRate);
								}
							}
							if (err) {
								if (err < 0) { printf(NAME "Out_Config returned %d\n", err); goto test_error; }
								else printf(NAME "Out_Config returned %d (continue)\n", err);
							}
							else printf(NAME "Out_config ok\n");

							for (i = 0; i < num_boards_loop; ++i) {
								status[i] = new DIO64STAT;
								if (status[i] == NULL) {
									err = -10;
									break;
								}
							}
							if (err) {
								printf(NAME "error allocation status structure!\n");
								goto test_error;
							}
							else {
								DWORD scansAvail[MAX_NUM_BOARDS];
								uint32_t status_FPGA[MAX_NUM_BOARDS];
								for (reps_2 = 0; (reps_2 < REPS_2) && (!err); ++reps_2) {

									// get board status
									for (i = 0; i < num_boards_loop; ++i) {
										status[i]->flags = 0;
										scansAvail[i] = 0;
										err = DIO64_Out_Status(board_hdl[i], &scansAvail[i], status[i]);
										status_FPGA[i] = show_status(i, status[i], scansAvail[i]);

										if (err) {
											printf(NAME "board %i get status error %d!\n", i, err);
										}
										else {
											if (status_FPGA[i] & DIO_STATUS_ERROR) {
												err = -1; // status error
												printf(NAME "board %i status 0x%x (error!)\n", i, status_FPGA[i]);
											}
											else if (status_FPGA[i] & DIO_STATUS_RUN) {
												err = -2; // board should not be running!
												printf(NAME "board %i status 0x%x (run!?)\n", i, status_FPGA[i]);
											}
											else {
												printf(NAME "board %i status 0x%x (ok)\n", i, status_FPGA[i]);
											}
										}
									}

									if (!err) {
										// write data to FPGA
										// TODO: generate data only at beginning! if samples are varied they only decrease.
										if (user_file != NULL) {
											struct data_info* data = user_data;
											while (data) {
												show_data((uint16_t*)data->data, data->samples, CREATE_DATA_BYTES_PER_SAMPLE);
												for (i = 0; (i < num_boards_loop) && (!err); ++i) {
													err = DIO64_Out_Write(board_hdl[i], (WORD*)data->data, data->samples, status[i]);
												}
												if (err) {
													printf(NAME "error 0x%x writing %d data to board!\n", err, data->samples);
													break;
												}
												data = data->next;
											}
										}
										else {
											uint16_t* data = (uint16_t*)test_step(
												(uint32_t)samples * 3 / 2, // samples
												0, // start time in us
												1, // step time in us
												0x030201, // data start pattern
												0x010101, // data increment
												CREATE_DATA_BYTES_PER_SAMPLE // bytes per sample of created data
												);
											if (data) {
												if ((loop == 0) && (reps_1 == 0) && (reps_2 == 0)) {
													show_data(data, samples, CREATE_DATA_BYTES_PER_SAMPLE);
												}
												for (i = 0; (i < num_boards_loop) && (!err); ++i) {
													err = DIO64_Out_Write(board_hdl[i], data, (uint32_t)samples, status[i]);
												}
												delete[] data;
											}
											else goto test_error;
										}

										// start boards, beginning from secondary ones. last is primary board.
										for (i = num_boards_loop - 1; (i >= 0) && (!err); --i) {
											run[i] = false;
											old_time[i] = (ULONG)-1;
											err = DIO64_Out_Start(board_hdl[i]);
										}
										if (err) {
											printf(NAME "error %d start FPGA!\n", err);
											goto test_error;
										}

										// get primary board status until RUN bit is reset
										// if a secondary board is in error state stops.
										bool running = true;
										l = 0;
										while (running) {
											running = false; // will be set to true if any board is not finished
											for (i = 0; i < num_boards_loop; ++i) {
												status[i]->flags = 0;
												scansAvail[i] = 0;
												err = DIO64_Out_Status(board_hdl[i], &scansAvail[i], status[i]);
												status_FPGA[i] = show_status(i, status[i], scansAvail[i]);

												if (err) { // stop on error of any board
													running = false;
													break;
												}

												if (status_FPGA[i] & (DIO_STATUS_ERROR | DIO_STATUS_END)) continue; // error or end
												else {
													if (run[i]) {
														if (!(status_FPGA[i] & DIO_STATUS_RUN)) continue; // error or end
														else { // board is running
															running = true;
															if (status[i]->ticks == old_time[i]) ++l;
															else { // ticks have changed
																old_time[i] = status[i]->ticks;
															}
														}
													}
													else if (status_FPGA[i] & DIO_STATUS_RUN) {
														run[i] = true;
														running = true;
													}
													else { // wait for run bit
														++l;
														running = true;
													}
												}
											}
											if (l > (25 * num_boards_loop)) { // stop when nothing happens
												printf(NAME "%i: abort after %d loops without changes!\n", i, l);
												break;
											}
											Sleep(1000);
										}
										//if (err == ERROR_BOARD) err = 0; // not a real error

										// get status of all boards after finished but before stop
										for (i = 0; (i < num_boards_loop) && (!err); ++i) {
											status[i]->flags = 0;
											scansAvail[i] = 0;
											err = DIO64_Out_Status(board_hdl[i], &scansAvail[i], status[i]);
											status_FPGA[i] = show_status(i, status[i], scansAvail[i]);
										}

										if (err) goto test_error;

										//Sleep(5000);
										// stop boards starting from secondary ones
										// TODO: unlock secondary ones before stopping primary board.
										for (i = num_boards_loop - 1; (i >= 0) && (!err); --i) {
											err = DIO64_Out_Stop(board_hdl[i]);
										}
										if (err) {
											printf(NAME "error %d stop FPGA!\n", err);
											goto test_error;
										}
									}
								} // next rep_2
							}
test_error:
							// delete status structure
							for (i = 0; i < num_boards_loop; ++i) {
								if (status[i] != NULL) { delete status[i]; status[i] = NULL; }
							}
							// close all boards even if there was an error
							for (i = 0; i < num_boards_loop; ++i) {
								if (tmp = DIO64_Close(board_hdl[i])) printf(NAME "Close board %i returned error %d!\n", i, tmp);
								//if (tmp = DIO64_Close(0)) printf(NAME "Close board %i returned error %d!\n", i, tmp);
								else printf(NAME "Close board %i ok\n", i);
								if (tmp && (!err)) err = tmp;
							}
						} // next rep_1
					} // next loop
				} // no error
			
				// send test command first board.
				if (test_cmd && (num_boards > 0)) {
					if (board_IP[0]) err = DIO64_OpenResource(board_IP[0], BOARD_ID, BASE_IO);
					else             err = DIO64_Open(BOARD_ID, BASE_IO);
					if (err > 0) {
						board_hdl[0] = (WORD)err;
						err = test(board_hdl[0], 0, NULL);
						if (err) printf(NAME "board %d test() returned error!\n", 0);
						else printf(NAME "board %d test() ok\n", 0);
						DIO64_Close(BOARD_ID);
					}
				}

				if (err) printf("\n" NAME "terminated with error %d!\n", err);
				else printf("\n" NAME "finished ok\n");

				/* open primary board again and wait until user presses a key. 
				// we do this only to keep dialog box open.
				if (wait_dlg && (num_boards > 0)) {
					//Sleep(1000);
					if (board_IP[0]) err = DIO64_OpenResource(board_IP[0], BOARD_ID, BASE_IO);
					else             err = DIO64_Open(BOARD_ID, BASE_IO);
					if (err > 0) {
						board_hdl[0] = (WORD)err;
						err = 0;
						printf("\ncontinue with any key to close dialog.\n");
						_getch();
						printf("\n");
						DIO64_Close(board_hdl[0]);
					}
					else {
						printf("error %d re-opening board 0!\n", err);
					}
				}*/

				/* exit all threads and close dialog box
				// this is not anymore compulsary. but call to ensure that threads are terminated before DLL is unloaded.
				// if not used insert CLOSE_TIMEOUT ms wait time before exiting application to allow threads to terminate.
				//Sleep(1000); // after this no thread should be running and dialog box should be closed
				tmp = exit_all();
				if (tmp) { // we should never get here an error, otherwise threads are not properly cleaned up!
					printf("\n" NAME "exit_all returned error %d!\n", tmp);
					printf("\n\ncontinue with any key to close dialog.\n");
					_getch();
					printf("\n");
				}*/
			} // DLL functions valid

			//DIO64_Close(0);

			// free library
			Sleep(250); // ensure all threads are closed (>200ms)
			FreeLibrary(module);
		}

		//if (err) printf("\n" NAME "terminated with error %d!", err);
		//else printf("\n" NAME "finished ok");
	}
	// wait for user pressed any key, before finishing (not anymore needed on VS 2019/Win10)
	//printf("\n\ncontinue with any key!");
	//_getch();
	//printf("\n");

    return err;
}
