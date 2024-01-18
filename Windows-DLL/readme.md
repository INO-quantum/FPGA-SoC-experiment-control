# Windows DLL

This is the Visual Studio 2019 (Community) project to generate the Windows dynamic-link-library (DLL) which directly replaces the libraries (DLL and lib) of the Viewpoint Systems driver for the dio64 I/O card. A simple command-line test probram (Dlltest.exe) is also provided to fast test the functionality.

    dio64-32.dll
    dio64-32.lib
    Dlltest.exe

To replace the DLL you have to "hide" the original DLL from Labview by moving it into a different folder but which cannot be a sub-folder of the labview project since Labview will find it again. Do not delete it but keep it in a separate folder outside of the projct - in case you need to revert the changes. Place the new DLL either at the old DLL location or into another sub-folder. Labview will notice that the DLL and path has changed and will search for it automatically. Stop the search and give the path to the new DLL. On newer computers the old DLL is located in one of the folders "C:/Windows/System32" or "C:/Windows/SysWOW64" and the library might be in "C:/Program Files (x86)/ViewpointSystems/DIO64/Visual C/".

I have implemented the same functions as the old DLL (plus some additional ones) with the same calling convention and compiled if for [32bit Windows](/Windows-DLL/Windows-DLL-x86) and [64bit Windows](/Windows-DLL/Windows-DLL-x64). This allows to use the same control program as before, but instead of communicating with the driver on the same PC, communication goes via Ethernet with the FPGA-SoC board. Since the old DLL was only available for 32bit Windows your Labview/Labwindows/CVI version must have been also 32bit but after the upgrade to the new control system you can consider upgrading also your control computer and Windows. Since no driver is needed anymore there are no constraints anymore on your control computer hardware, software and operating system. You might even consider of using [labscript-suite](/labscript-suite) as an alternative control platform for which I have provided the necessary python files. Nevertheless, I provide here the Windows DLL such that the transition can be done smooth and hopefully without many problems.

The library (.lib) is used for static linking and is needed only with Labwindows/CVI. You need to manually recompile the source with the new library selected. 

After the DLL is replaced you will need to make a few changes on the old Labview program - and similar on Labwindows/CVI:

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


