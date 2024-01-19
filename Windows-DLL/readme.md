# Windows DLL

In order do allow a fast and easily revertible transition from the old Viewpoint Systems `DIO64` card to the new FPGA-SoC control system, I provide here a Windows dynamic-link-library (DLL) with the same functions as the library of the original Viewpoint Systems driver. By just replacing the old DLL with the new one, any software used to control the old system will be able to control the new FPGA-Soc system with only minor changes. Reverting back to the original control system can be done by switching back to the original DLL. 

> [!TIP]
> For a fresh install of your control system, the old driver does not need to be installed. Just place the 64bit DLL into "C:/Windows/System32". 

Here you find the compiled DLL for [32bit Windows](/Windows-DLL/Windows-DLL-x86) and [64bit Windows](/Windows-DLL/Windows-DLL-x64). Since the old DLL was only available for 32bit Windows your old Labview/Labwindows/CVI version must have been also 32bit. I provide 3 files, the dynamic link library (.dll), the static link library (.lib), which is needed by LabWindows/CVI and a command-line executable (.exe) which allows you to test the DLL:

    dio64-32.dll
    dio64-32.lib
    Dlltest.exe

> [!ATTENTION]
> DLLtest.exe can send and execute random data on the board(s)! Do not connect real devices on the board while using this software! Use `DLLtest.exe -h` to get help on how to use this tool.

> [!TIP]
> Since the new control system does not need a driver, there are no constraints anymore on your control computer hardware, software and operating system! You can upgrade your computer to 64bit Windows, Linux or MAC (not tested). You might also consider of using the open and Python-based control platform [labscript-suite](/labscript-suite) for which I provide the necessary Python files.

In the [source](/Windows-DLL/source) folder you find the source files for the DLL and the Visual Studio 2019 project to generate the DLL.

To replace the DLL you have to "hide" the original DLL from Labview by moving it into a different folder outside of the labview project, otherwise Labview will find it again. Do not delete it, so you can revert the changes if needed. When you start your Labview VI it will start searching for the old DLL, stop it and give the path to the new DLL. The old DLL is either located in one of your Labview constrol system folders or, when properly installed, in one of the Windows folders "C:/Windows/System32" or "C:/Windows/SysWOW64".

The library (.lib) is used for static linking and is needed only with Labwindows/CVI. It might be located in "C:/Program Files (x86)/ViewpointSystems/DIO64/Visual C/". You have to manually select the new library and recompile the project. 

After the DLL is replaced you will need to make a few changes on the old Labview program. Similar changes need to be done on Labwindows/CVI.

1. first check that all `DIO64_` function VI's ('Virtual Instrument's) use the new DLL by double-clicking, open Block Diagram, and double-clicking on the "Call Library Function Node", where you should find in the "Function" tab the path to the DLL. 

2. depending on how antique your old driver is the `DIO64_Open` or `DIO64_OpenResource` function is used to open the device. Use `DIO64_OpenResource` since it allows to select the IP address of the board as the `resouceName`. See Figure how to implement this properly. I have placed this into a case structure which allows to faster switch between using the old function call and the new.

![Figure OpenResource](/Windows-DLL/images/OpenResource.png)

Give a string for example as `192.168.1.140:49701` with the number before the colon ':' indicating the IP address and that after the colon the port, which by default is set to `49701`. Set `board` = 0 and `baseio` = number of boards, i.e. 1 for single board and 2 for primary and secondary board. The default IP address depends on the board version:

| board version  | default IP address |
| :---: | :---: |
| v1.2 | 192.168.1.120 |
| v1.3 | 192.168.1.130 |
| v1.4 | 192.168.1.140 |

The returned error cluster of `DIO64_OpenResource` needs to be unbundled and when `code` > 0 then there is no error but `code` converted to `U16` is the **board identifier** which needs to be given to all following `DIO64_` functions as `board in`. This ensures that the board can be accessed only from one application at a time. See the figure how to unbundle and to get the board identifier. The error cluster needs then to be reset to the ok state as shown.

3. The other `DIO64_` functions do not need to be modified. Just ensure that the same board identifier is given to all of them and ensure that `DIO64_Close` is called before your VI exits. Otherwise, when you try to start the next time your VI you will not be able to open the board and you will get an error. The software is programmed in such a way that at the second attempt you should be able to open it again. However, ensure to close the board all the time, even if there is an error. Do not use the Labview `Exit` function or the red abort button but always stop your run loop within your VI and properly close the board.

> [!TIP]
> Do not open and close the board during each loop. This was done with the old DIO card to fix some issues but is not needed for the new FPGA board and just takes unnecessary time on your computer.

> [!IMPORTANT]
> Ensure all DIO64_ functions are using the returned board identifier from `DIO64_OpenResource` and call always `DIO64_Close` before exiting your VI even on error!


