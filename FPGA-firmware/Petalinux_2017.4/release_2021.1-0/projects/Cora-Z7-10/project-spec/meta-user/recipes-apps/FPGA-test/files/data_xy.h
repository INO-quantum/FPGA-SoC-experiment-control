// declaration of sample data

#ifndef DATA_XY_H
#define DATA_XY_H

#include <stdint.h>			// uint32_t, int32_t

#define BYTES_PER_SAMPLE	8

// test data for device address 0x01, digital out
// data is in little-endian byte order (LSB first)!
// data sample = 32bit time (in mu, max. >1h), 16bit data, 7bit address, 1bit strobe, 8bit 0s
#define TEST_DATA_NUM_SAMPLES		19
extern uint32_t test_data[TEST_DATA_NUM_SAMPLES*2];

// test data for device address 0x01, digital out
// data is in little-endian byte order (LSB first)!
// data sample = 32bit time (in mu, max. >1h), 16bit data, 7bit address, 1bit strobe, 8bit 0s
#define TEST_DATA_NUM_SAMPLES_2		11*3*2
extern uint32_t test_data_2[TEST_DATA_NUM_SAMPLES_2*2];

// max time = 5.860362s
#define LENS_NUM			5890
extern uint16_t LENS_data[LENS_NUM*4];

// max time = 5.864362s
#define LICR_NUM			5898
extern uint16_t LiCr_data[LICR_NUM*4];


#endif // DATA_XY_H
