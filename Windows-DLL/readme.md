# Windows DLL

This is the Visual Studio 2019 (Community) project to generate the Windows dynamic-link-library (DLL) which directly replaces the libraries (DLL and lib) of the Viewpoint Systems driver for the dio64 I/O card:

    dio64-32.dll
    dio64-32.lib

The instructions for replacing the DLL need to be tested but as far as I remember you have to "hide" the original DLL from Labview by moving it into a different folder, not into a sub-folder, but outside of the labview project path (don't delete it but keep it - in case you need to revert the changes) and place the new DLL either at the old DLL location or into another sub-folder. Labview will notice that the DLL and path has changed and will search for it automatically. Stop the search and give the path to the new DLL. 

I have implemented the same functions as the old DLL (plus some additional ones) with the same linkage and compiled for 32bit bit Windows. This allows to use the same control program as before, but instead of communicating with the driver on the same PC, communication goes via Ethernet with the FPGA-SoC board. The IP and port number for communication with the board(s) can be set in Dio24.h. If several boards are used the IP address is automatically incremented by one.

The library (.lib) is used for statik linking and think I needed it only with Labwindows/CVI where I had to explicitly recompile the source with the new library. 

The actual configuration uses 12 bytes per sample with 4 bytes timestamp, 4 bytes data for first rack and 4 bytes data for second rack. If exists, then a second rack is driven by the secondary SoC board. Other configurations need to be manually adjusted and I should make this more user friendly.

If you do not need to keep compatibility with the old driver and application you can compile the project directly with 64bits (x64) instead of 32bits.

A simple testing program "Dlltest" is provided with the project, but it is in an undefined state and might give some error. Be warned, that you should not run this with the board connected to actual devices since it sends arbitrary data to the FPGa-SoC board! 

I have to update the DLL very soon for another experiment and at this occasion I will clean up this better.
