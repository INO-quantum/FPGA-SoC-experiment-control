# labscript-suite development version

This folder contains the next version of the labscript-suite python driver.

The `userlib/user_devices` folder contains `FPGA_device` which is the driver. Ensure to keep `use_prelim_version = True` since at the moment this version can be used only with the actual [development version](https://github.com/INO-quantum/FPGA-SoC-experiment-control/tree/main/development/firmware-dev)

The `userlib/labscriptlib/FPGA_test` folder contains a sample `connection_table.py` file and experiment script `FPGA_test.py` with examples how to use this driver.


