# FPGA-SoC experiment control system

## Project structure

Below an outline of the project structure. See readme files in the individual folders for more specific information.

```
├── firmware-release        firmware to be saved on the SD card
├── firmware-source         firmware source for Vivado and Petalinux
│   ├── 2017.4              initial version
│   └── 2020.1              newest version
├── Windows-DLL             Windows DLL and source files
│   ├── images
│   ├── source              source files
│   │   ├── dio24           header files
│   │   └── dio64_32        Visual studio project folder
│   ├── Windows-DLL-x64     compiled 64bit Windows DLL
│   └── Windows-DLL-x86     compiled 32bit Windows DLL
├── labscript-suite         labscript-suite implementation
│   └── userlib
│       ├── labscriptlib
│       │   └── FPGA_test   connection table and example script
│       └── user_devices    user device
├── buffer-card             schematics and production files of buffer card 
│   ├── v1.2                board version v1.2
│   ├── v1.3                board version v1.3
│   └── v1.4                board version v1.4
└── paper                   publication
    ├── data                data used for publication
    └── schematics          cable driver schematics
```

<!--
| folder                         | description                          | toolchain            | language            |
|--------------------------------|--------------------------------------|----------------------|---------------------|
| firmware-release               | firmware to be saved on SD card      | -                    | - 
| FPGA-firmware/Vivado_2017.4    | hardware (logic) implementation      | Xilinx Vivado 2017.4 | Verilog             |
| FPGA-firmware/Petalinux_2017.4 | software (driver, server)            | petalinux 2017.4     | C/C++, shell script |
| FPGA-buffer-card               | electronic schematics of buffer card | KiCad 5.1            | -                   |
| labscript-suite                | labscript device                     | labscript-suite      | Python 3            |
| Windows-DLL                    | Windows dynamic link library         | Visual Studio 2019   | C++                 |
| paper                          | publication about FPGA-Soc           | -                    | -                   |
| paper/data                     | data and analysis used in paper      | -                    | Python 3            |
| paper/schematics               | electronic scheme used for auto-sync | KiCad 5.1            | -                   |
-->

## Project Overview

This project contains everything to run and generate your own FPGA-SoC experimental control system designed for cold or ultracold atoms experiments. But any other use is welcome!

Here a figure [taken from the paper](/paper) with an overview of the system:

<img src="paper/setup.png" width="600"/>

(a) Each of the FPGA-SoC boards (red) is inserted inside of a 19" sub-rack at possibly remote locations from each other and are connected via Ethernet (orange) to a control computer. The timing is provided by an external clock (green) and a trigger line (blue) which is driven by one of the boards (the primary board) and connects to all of the other (secondary) boards. (b) Image of the FPGA-SoC board mounted on top of the buffer card used to connect the FPGA-SoC with the sub-rack. (c) Image of the FPGA-SoC board.

The heart of the exerpimental control system is the [Cora-Z7 board from Digilent](https://digilent.com/shop/cora-z7-zynq-7000-single-core-for-arm-fpga-soc-development/). There are two versions: the Cora-Z7-10 has a dual core CPU, but is out of production, the Cora-Z7-07S has a single-core CPU, is slightly cheaper and is in production. The only measurable difference between the two boards is that the uploading rate of the single-core CPU board is about 80% smaller than that of the dual-core CPU. This difference is only significant for very large number of samples [see paper](/paper). You need to use the right [firmare for your board](/firmware-release).

This is a low-cost FPGA-SoC development board. The SoC (system-on-a-chip) consists of a CPU (ARM Cortex A9) and a FPGA (field-programmable gate array) on the same chip. The CPU allows to run a simple Linux operating system (Petalinux) on the CPU which makes it easy to run custom code and use Linux system services to access external hardware (Ethernet, DDR memory, USB keyboard/mouse, SD card, etc.). The FPGA allows to implement custom hardware (logic, PLLs, serializer, etc.) to perform a specific task which otherwise might be very difficult to implement, like testing a new interface, time-critical applications or highly parallelized tasks. Image analysis or neural networks are two examples. The tight connection between the CPU and FPGA allows to control the hardware by software and to efficiently transfer data between the two parts. 

An alternative board using an Intel/Altera FPGA-SoC could be the DE10-Nano Kit from Terasinc. It is more powerful but also more expensive than the Cora. However, I have not tested this device:
https://www.terasic.com.tw/cgi-bin/page/archive.pl?Language=English&CategoryNo=167&No=1046

The implementation of the FPGA-SoC for "experimental control" was born out of the need to replace the old `DIO64` card (from Viewpoint Systems) which is used in many of our experiments but is not anymore sold and supported by the manufacturer. It uses old Hardware (PCI slot) and the old driver constraints the operating systems (Windows XP/7/8). This card was preferrably programmed with NI Labview and Labwindows/CVI user application programms which create a table of time and instructions (32bit time and 32 or 64bit data) which is sent to the driver. The card performs the task of outputting the data at the programmed time (typically in units of us) on a 50-way ribbon cable of 2-3m length. This cable is connected to a 19" rack which hosts our custom hardware in one or two sub-racks. After buffering and electrical isolation (in a custom buffer card) the data are available on a bus at the backplane of each sub-rack. Several plug-in modules of different type and size can be inserted into the sub-rack and connect to this bus. Typical devices are digital and analog outpus and DDS (direct digital synthesizers, i.e. RF generators). Some experiments might use also input devices, but not in our design. Each device has an address decoder and 7 bits of the data are reserved for the address of the device. 16 data bits are reserved for device specific data. One bit called "Strobe" is used as a pseudo-clock, which is simply a clock which pulses only when something on the bus should be updated. This signal is originally recovered from a bit generated by the software and sent with the data by the `DIO64 card`. This bit must change state for every instruction and in the buffer card a simple electronic cirquit generates the pulses out of this signal. The pulses must be shorter than the update rate of the bus (essentially, it has twice the frequency than the bus) and must be delayed in time with the bus update. This way delays between different bits on the bus (known as skew) and noise is cancelled.

The FPGA-SoC replaces the DIO64 card but also improves the old system in several ways:
  
1. nothing needs to be installed on the control computer:
  * hardware requirements are low - just Ethernet is needed which every computer has
  * no driver is needed:
    * no restrictions on the operating system
    * no restriction on the used software
  * the computer is free to do other things during the execution of the sequence since there is no busy driver running in the background
  
2. the data is uploaded via Gigabit Ethernet:
  * even for long sequences the uploading time is small (2.3s for 10M samples)
  * electrical isolation is ensured by the Ethernet specification (via magnetic decoupling)
  * much longer cables are possible which allows even remote control over the network

3. 10M samples can be stored directly on the FPGA-SoC board:
  * this size (128MiB) is more than sufficient for our experiments
  * repetitions of the same experiment can be done directly by the board without uploading the data again
  * in a future extension: only parts of the data could be updated in memory
  
4. contiguous bus output (and input) rates of up to 40MHz should be possible:
  * we usually use 1MHz output rate (limited by our plug-in modules) but tests showed no problem running the board with 10MHz output rate. higher rates were not tested so-far.
  * the data from the memory into the FPGA part is transmitted via direct memory access (DMA) which gives the limitation of contiguous data output rate. the [measured DMA rate in the paper](/paper) agrees perfectly with the specification of 350MBit/s.
  * theoretical limit is 29.2MHz for 64bit data and 43.8MHz for 32bit data (8 or 12 bytes per samples are used)
  * not used, but reading data could be done simultaneously without affecting the writing channel
  * using more of the unused DMA ports and giving priority to the write channel might increase the rates even more
  
5. the internal write and read FIFOs hold 8192 samples which allows short bursts of output/input at higher rates:
  * for short time and ensuring the FIFOs are not getting empty/full output/input can be done at higher rates
  * this is so-far not tested
    
6. the FPGA-SoC allows to customize for your application. New ideas, new features, and new devices can be implementd. here is a list what could be done or is partially already done or tested:
  * several boards are synchronized by using a common clock signal provided externally or from one board and one board provides a trigger signal to the other boards in order to start the experiment run. This is the default configuration and works well. Using an oscilloscope one can measure the delay between the boards and the delay can be adjusted by software to order of 1ns. In the [paper](/paper) we present an automatic synchronization protodocl where the delay between the boards can be automatically measured and corrected. This is however not implemented since it requires hardware to generate a sufficient strong pulse on the trigger line which the current buffer card does not provide.
  * you could run additional software on the CPU. for example some python analysis/feedback program, which changes the state of the experiment depending on measured values. note however, this cannot be "very" fast (the CPU runs at 650MHz). Very fast things could be done on the hardware, but also this is limited to 100-200MHz, but things can be done in parallel (on many bits).
  * the board features an USB port which can be configured as device (passive, like a flash drive) or host (active, like your computer). Many modern laboratory equipments allow to be remote controlled via USB (using the USBTMC protocol) or older devices use the GPIB port for which USB-to-GPIB adapters exist. You could directly control such a device from the FPGA-SoC using a simple application running on the CPU or with data which you send via Ethernet. I have tested triggering a function generator in this way but connected via the USB port of the control computer and using the software programmable interrupt (DATA_IRQ) could achieve a relative low jitter.
  * one could implement ramps directly on the board and update only parts of the sequence

7. limiations of the current design:
  * the current bus hardware layout with the "strobe" signal instead of a real clock limits the output rate
  * the internal 100MHz bus clock of the board limits the output rate to 50MHz. a bus clock of 200MHz might be possible at the cost of higher latency and more resources used. individual I/O ports I have tested to run with 1GHz using parallel-to-serial and serial-to-parallel decoders (SERDES) on the chip but I think its not possible to use this on many port.


