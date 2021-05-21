////////////////////////////////////////////////////////////////////////////////////////
// Dlltest.cpp
// Win32/64 test of DLL
// created 27/11/2019 by Andi
////////////////////////////////////////////////////////////////////////////////////////

#include "Dio24.h"					// header
#include <stdio.h>					// printf
#include <conio.h>					// getch

////////////////////////////////////////////////////////////////////////////////////////
// test data
////////////////////////////////////////////////////////////////////////////////////////

// test data for device address ADDR
// data is in little-endian byte order (LSB first)!
// data sample = 32bit time (in mu, max. >1h), 16bit data, 7bit address, 1bit strobe, 8bit 0s
#define GET_TIME(ms)			(((ms)*1000) & 0xffff),((((ms)*1000) >> 16) & 0xffff)
#define GET_MU(us)				((us) & 0xffff),(((us) >> 16) & 0xffff)

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

// shutter tests
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
};


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

// generates samples starting at t_start us with t_step time. 
// data starts at d_start and increments with d_step
// notes: 
// - good for creating big data for board tests but do not use with devices in rack since data is random!
// - usage: pdata = test_step(1024*100/*100ks*/, 0/*start 0us*/, 1/*step 1us*/, 0x030201/*data start pattern*/, 0x010101/*data increment*/);
uint32_t* test_step(uint32_t samples, uint32_t t_start, uint32_t t_step, uint32_t d_start, uint32_t d_step) {
	uint32_t *buf, *p, s;
	p = buf = new uint32_t[samples*DIO_BYTES_PER_SAMPLE/sizeof(uint32_t)];
	for (s = 0; s < samples; ++s, t_start += t_step, d_start += d_step) {
		*p++ = t_start;
#if DIO_BYTES_PER_SAMPLE == 8
		*p++ = DIO_DATA_MASK & d_start;
#elif DIO_BYTES_PER_SAMPLE == 12
		*p++ = DIO_DATA_MASK & d_start;
		*p++ = DIO_DATA_MASK & d_start;
#endif
	}
	return buf;
}

// linear analog ramp on address for {time in mu, voltage} = {t_start,u_start} to {t_end,u_end} in steps
// returns pointer to data, delete[] after use!
uint16_t *analog_ramp(uint8_t address, uint32_t t_start, uint32_t t_end, int16_t u_start, int16_t u_end, int steps) {
	uint32_t time;
	uint16_t *data = new uint16_t[steps*4];
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
	uint16_t *data = new uint16_t[steps * 4];
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
	uint16_t *data = new uint16_t[steps * 4];
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

void show_data(uint16_t *data, int steps) {
	uint32_t time;
	for (int i = 0; i < steps; ++i, data += DIO_BYTES_PER_SAMPLE/sizeof(uint16_t)) {
		time = data[0];
		time |= data[1] << 16;
#if DIO_BYTES_PER_SAMPLE == 8
		printf("%3d %04x_%04x %04x_%04x (%uus)\n", i, data[0], data[1], data[2], data[3], time);
#elif DIO_BYTES_PER_SAMPLE == 12
		printf("%3d %04x_%04x %04x_%04x %04x_%04x (%uus)\n", i, data[0], data[1], data[2], data[3], data[4], data[5], time);
#endif
	}
}

uint32_t show_status(DIO64STAT *status) {
	uint32_t status_FPGA = status->AIControl, time = status->time[0] | (status->time[1] << 16);
	if (status_FPGA & DIO_STATUS_ERROR) {
		printf("FPGA status = 0x%08x (error)\n", status_FPGA);
	}
	else if (status_FPGA & DIO_STATUS_END) {
		printf("FPGA status = 0x%08x (end)\n", status_FPGA);
	}
	else if (status_FPGA & DIO_STATUS_RUN) {
		printf("FPGA status = 0x%08x (run)\n", status_FPGA);
	}
	else {
		printf("FPGA status = 0x%08x (not running)\n", status_FPGA);
	}
	if (time > 1000000) printf("FPGA time   = %u us (%us)\n", time, time/1000000);
	else printf("FPGA time   = %u us\n", time);
	return status_FPGA;
}

////////////////////////////////////////////////////////////////////////////////////////
// application entry
////////////////////////////////////////////////////////////////////////////////////////

#define NAME		"DLL test: "
#define BOARD_ID	0			// user selected board ID, has to remain the same. distinguishes different boards.
#define CYCLES		1			// number of cyles. 0 = infinite, 1 = normal, >1 number of cycles
#define TEST		3			// 0=test_data, 1=analog+digital ramps, 2=shutter test, 3=1us ramp big data
#define MS			1000
#define SEC			1000000
#define VOLT(x)		((32767*(x))/10)
#define LOOPS		1			// number of repetitions with opening/closing device with changing number of samples using NEXT_SAMPLES
#define REPS_1		1			// number of repetitions with opening/closing device with same number of samples
#define REPS_2		1			// number of repetitions without opening/closing device		
#define SAMPLES		500000		// number of samples
#define NEXT_SAMPLES(s)	(s>>1)	// recalculates samples in each loop

// main application start
// command arguments: 
// '-f' followed by path + file with user data
// '-r' followed by number of repetitions
// '-s' followed by the number of samples
// '-v' vary number of samples down to 4 in powers of 2
// '-t' send test command at end
int main(int argc, char* argv[])
{
	int	err = 0;					// error if nonzero
	int loop = 0, samples = SAMPLES, reps_1, reps_2, vary = 1;
	DIO64STAT* status = NULL;
	bool run = false, test_cmd = false;
	int l = 0;
	//WORD mask[4] = { 0xffff, 0xffff, 0x0000, 0x0000 }; // port a+b
	WORD mask[4] = { 0xffff, 0xffff, 0xffff, 0xffff }; // port a+b+c+d = Yb
	double scanRate = 1000000; // scan rate in Hz
	int i, user_reps = REPS_1, user_samples = SAMPLES;
	char* user_file = NULL;
	struct data_info* user_data = NULL;
	ULONG old_time = 0;

	printf(NAME "test program by Andi for Windows DLL:\n");
	printf(DLL_INFO "\n\n");

	// parse command line arguments
	if (argc > 1) {
		for (i = 1; (i < argc) && (!err); ++i) {
			if ((argv[i][0] == '-') && (argv[i][1] != '\0') && (argv[i][2] == '\0')) {
				switch (argv[i][1]) {
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
							printf(NAME "%d repetitions\n", user_reps);
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
		printf(NAME "execute test sequence of %d samples for %d repetitions\n", user_samples, user_reps);
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
		printf(NAME "'-f <filename>' = load data from text file\n");
		printf(NAME "'-r <#>'        = repeat the sequence # times\n");
		printf(NAME "'-s <#>'        = use test with given # samples\n");
		printf(NAME "'-v             = vary # samples down to 4 in powers of 2\n");
	}
	else {
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
			_exit_all				exit_all = (_exit_all)GetProcAddress(module, "exit_all");
			_test					test = (_test)GetProcAddress(module, "test");
			_register_callback		register_callback = (_register_callback)GetProcAddress(module, "register_callback");
			_load_text_file			load_text_file = (_load_text_file)GetProcAddress(module, "load_text_file");
			_save_text_file			save_text_file = (_save_text_file)GetProcAddress(module, "save_text_file");
			_DIO64_OpenResource		DIO64_OpenResource = (_DIO64_OpenResource)GetProcAddress(module, "DIO64_OpenResource");
			_DIO64_Open				DIO64_Open = (_DIO64_Open)GetProcAddress(module, "DIO64_Open");
			_DIO64_Load				DIO64_Load = (_DIO64_Load)GetProcAddress(module, "DIO64_Load");
			_DIO64_Close			DIO64_Close = (_DIO64_Close)GetProcAddress(module, "DIO64_Close");
			_DIO64_Out_Config		DIO64_Out_Config = (_DIO64_Out_Config)GetProcAddress(module, "DIO64_Out_Config");
			_DIO64_Out_Status		DIO64_Out_Status = (_DIO64_Out_Status)GetProcAddress(module, "DIO64_Out_Status");
			_DIO64_Out_Write		DIO64_Out_Write = (_DIO64_Out_Write)GetProcAddress(module, "DIO64_Out_Write");
			_DIO64_Out_Start		DIO64_Out_Start = (_DIO64_Out_Start)GetProcAddress(module, "DIO64_Out_Start");
			_DIO64_Out_Stop			DIO64_Out_Stop = (_DIO64_Out_Stop)GetProcAddress(module, "DIO64_Out_Stop");
			_DIO64_Out_ForceOutput	DIO64_Out_Force = (_DIO64_Out_ForceOutput)GetProcAddress(module, "DIO64_Out_ForceOutput");

			if ((!exit_all) || (!register_callback) || (!load_text_file) || (!save_text_file) ||
				(!DIO64_OpenResource) || (!DIO64_Load) || (!DIO64_Close) || (!DIO64_Out_Config) || (!DIO64_Out_Status) ||
				(!DIO64_Out_Write) || (!DIO64_Out_Start) || (!DIO64_Out_Stop) || (!DIO64_Out_Force)) {
				printf("DLL test could not load all function pointers!\n");
				err = 20;
			}
			else {
				if (user_file != NULL) {
					// load file if specified
					user_data = load_text_file(user_file, (unsigned int*)&samples, DIO_BYTES_PER_SAMPLE / sizeof(uint32_t));
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
					for (loop = 0; (loop < vary) && (!err); ++loop, samples = NEXT_SAMPLES(samples)) {
						if (samples < 4) break;
						for (reps_1 = 0; (reps_1 < user_reps) && (!err); ++reps_1) {
							printf(NAME "loop %d/%d rep %d/%d samples %d/%d\n", loop, vary, reps_1, user_reps, samples, user_samples);
							if (loop > 0) Sleep(100);
							// open board at given IP:port and give BOARD_ID
							// err = DIO64_OpenResource(IP_PORT, BOARD_ID, 0);
							err = DIO64_Open(BOARD_ID, 0);
							if (err && ((err != ERROR_CONNECT) && (err != ERROR_CONNECT_IGNORE))) { printf(NAME "OpenResource returned %d\n", err); break; }
							else {
								if (err) {
									printf(NAME "OpenResource ok (warning %d)\n", err);
									printf("continue with any key!");
									_getch();
									printf("\n");
									loop = LOOPS;
								}
								else printf(NAME "OpenResource ok\n");

								// does not do anything, should not fail
								err = DIO64_Load(BOARD_ID, NULL, 0, 4);
								if (err) {
									printf(NAME "Load returned %d\n", err);
									goto test_error;
								}
								else printf(NAME "Load ok\n");

								// configure board
								// for fast testing set 
								err = DIO64_Out_Config(BOARD_ID, 0, mask, 4, 0, DIO64_CLCK_INTERNAL,
									DIO64_STRTTYPE_EDGE, DIO64_STRT_NONE, DIO64_STOPTYPE_EDGE, DIO64_STOP_NONE,
									DIO64_AI_NONE, CYCLES, 0, &scanRate);
								if (err) {
									if (err < 0) { printf(NAME "Out_Config returned %d\n", err); goto test_error; }
									else printf(NAME "Out_Config returned %d (continue)\n", err);
								}
								else printf(NAME "Out_config ok\n");

								status = new DIO64STAT;
								if (status == NULL) {
									printf(NAME "error allocation status structure!\n");
									goto test_error;
								}
								else {
									for (reps_2 = 0; (reps_2 < REPS_2) && (!err); ++reps_2) {
										// write data to FPGA
										// todo: should call OutStatus before!
#if TEST == 0
										err = DIO64_Out_Write(BOARD_ID, test_data, TEST_DATA_NUM_SAMPLES, status);
#elif TEST == 1
										Attention: not all functions adapted for 12bytes / sample!
											uint16_t * data;
										uint32_t steps;
										for (int i = 0; ; ++i) {
											switch (i) {
											case 0:
												steps = 16;
												data = digital_ramp(1, 0000 * MS, 499 * MS, 0x0001, 1, steps);
												break;
											case 1:
												steps = 63;
												data = analog_ramp(23, 1000 * MS, 1124 * MS, VOLT(0), VOLT(5), steps);
												break;
											case 2:
												steps = 63;
												data = analog_ramp(23, 1125 * MS, 1374 * MS, VOLT(5), VOLT(-5), steps);
												break;
											case 3:
												steps = 63;
												data = analog_ramp(23, 1375 * MS, 1499 * MS, VOLT(-5), VOLT(0), steps);
												break;
											case 4:
												steps = 16;
												data = digital_ramp(1, 1500 * MS, 1999 * MS, 0x8000, -1, steps);
												break;
											default:		// stop when all cases are done
												steps = 0;
												data = NULL;
												break;
											}
											if (steps > 0) {
												if (data) {
													show_data(data, steps);
													err = DIO64_Out_Write(BOARD_ID, data, steps, status);
													delete[] data;
													if (err) {
														printf(NAME "error %d sending %d steps of data!\n", err, steps);
														goto test_error;
													}
												}
												else {
													printf(NAME "error %d generating %d steps of data!\n", err, steps);
													goto test_error;
												}
											}
											else break;
										}
#elif TEST == 2
										Attention: not adapted for 12bytes / sample
											uint32_t steps = 25;
										uint16_t* data = shutter_test(0x01, 0, (steps + 1) * SEC, steps);
										if (data) {
											err = DIO64_Out_Write(BOARD_ID, data, steps, status);
											delete[] data;
										}
#elif TEST == 3
										if (user_file != NULL) {
											struct data_info* data = user_data;
											while (data) {
												show_data((uint16_t*)data->data, data->samples);
												err = DIO64_Out_Write(BOARD_ID, (WORD*)data->data, data->samples, status);
												if (err) {
													printf(NAME "error 0x%x writing %d data to board!\n", err, data->samples);
													break;
												}
												data = data->next;
											}
										}
										else {
											uint16_t* data = (uint16_t*)test_step(
												(uint32_t)samples/*samples*/,
												0/*start 0us*/,
												1/*step 1us*/,
												0x030201/*data start pattern*/,
												0x010101/*data increment*/);
											if (data) {
												err = DIO64_Out_Write(BOARD_ID, data, (uint32_t)samples, status);
												delete[] data;
											}
										}
#endif
										// start FPGA
										err = DIO64_Out_Start(BOARD_ID);
										if (err) {
											printf(NAME "error %d start FPGA!\n", err);
											goto test_error;
										}

										// get FPGA status until RUN bit is reset
										DWORD scansAvail;
										uint32_t status_FPGA;
										l = 0;
										while (true) {
											status->flags = 0;
											scansAvail = 0;
											err = DIO64_Out_Status(BOARD_ID, &scansAvail, status);
											status_FPGA = show_status(status);
											if (err) break; // stop on error
											else if (run) {
												if (!(status_FPGA & DIO_STATUS_RUN)) break; // run finished (error or end)
											}
											else { // wait for run bit set, stop if end or error
												if (status_FPGA & DIO_STATUS_RUN) run = true;
												else if (status_FPGA & (DIO_STATUS_ERROR | DIO_STATUS_END)) break;
											}
											if (!run) ++l;
											else if (status->ticks == old_time) ++l;
											else { old_time = status->ticks; l = 0; }
											if (l > 25) {
												printf(NAME "abort after %d loops without changes!\n", l);
												break;
											}
											Sleep(1000);
										}

										if (err) {
											printf(NAME "error %d get status (bits)!\n", err);
											goto test_error;
										}
										else {
											// get complete status after finished but before stop
											status->flags = 0;
											scansAvail = 0;
											err = DIO64_Out_Status(BOARD_ID, &scansAvail, status);
											status_FPGA = show_status(status);
										}

										//Sleep(5000);
										// stop FPGA
										err = DIO64_Out_Stop(BOARD_ID);
										if (err) {
											printf(NAME "error %d stop FPGA!\n", err);
											goto test_error;
										}
									} // next rep_2
								test_error:
									// delete status structure
									if (status != NULL) { delete status; status = NULL; }
								}
								// close board
								if (DIO64_Close(BOARD_ID)) printf(NAME "Close returned an error!\n");
								else printf(NAME "Close ok\n");
							}
						} // next rep_1
					} // next loop
				} //
			}

			if (test_cmd) {
				err = DIO64_Open(BOARD_ID, 0);
				if (!err) {
					if (test(BOARD_ID, NULL)) printf(NAME "test() returned error!\n");
					else printf(NAME "test() ok\n");
					DIO64_Close(BOARD_ID);
				}
			}

			if (err) printf("\n" NAME "terminated with error %d!", err);
			else printf("\n" NAME "finished ok");

			// wait for user pressed any key, before closing dialog box
			printf("\n\ncontinue with any key!");
			_getch();
			printf("\n");

			// exit all threads and close dialog box
			if(exit_all != NULL) exit_all();

			// free library
			FreeLibrary(module);
		}

		//if (err) printf("\n" NAME "terminated with error %d!", err);
		//else printf("\n" NAME "finished ok");
	}
	// wait for user pressed any key, before finishing
	//printf("\n\ncontinue with any key!");
	//_getch();
	//printf("\n");

    return err;
}
