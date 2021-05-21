# FPGA buffer card

FPGA-buffer card serves to buffer and level shift from the FPGA 3.3V to the 5V TTL level of the bus. For this purpose we use the 74HCT541 octal buffer, which is supplied with 5V from the rack but accepts the 3.3V input from the FPGA. The FPGA is also supplied from the rack via the buffer card with 5V.

The buffer card also has the input and output clock buffers needed for locking with an external clock and to synchronize several boards with one board providing the clock to the other boards. The External clock can be in the frequency range of 10MHz- 300MHz. Depending on the choice of input components the input signal can be sine-wave max +10dBm/2Vpp @ 50 Ohm centered around zero (left values in schematics page 4) or can be an LVPECL signal (right values) with differential 0.8Vpp. The output buffer gives a LVPECL signal. Note that if you measure the output without the proper load it will stay at a DC offset voltage without oscillations.

At the moment the firmware needs to be adjusted manually for the frequency input and is set to 10MHz input for the Cora-Z7-10 and 50MHz for the Cora-Z7-07S. Output is always 50MHz, but can be adjusted also in the firmware. The reason was that the Cora-Z7-10 was used as the primary board which the 07S was used as the secondary board in the paper. But I should make this software configurable - or at least configurable via the SD card server.config file. 

At present there are two versions available with version v1.2 fully tested and functional. 

Version v1.3 is in production and needs to be tested. It features additional buffers which permit to drive two racks from a single FPGA-SoC board. One of the two racks is connected either on the backplane connector (J14) or on a 50 pole ribbon cable (via J13), and the second rack is connected with another 50-pole ribbon cable (via J15). It provides independent strobe signals for the two racks which enables to update one or the other rack (or both) and to correct for electronic delays between the racks. This is not yet implemented in the firmware.

Each folder containes the schematics and Gerber and drill files. Additional bill of materials with lists of components and a "shopping list" with the codes from RS can be found in the BOM folder. The boards are simple double layer with components only one one side. Version v1.2 has some optional components on the back side but which do not need to be populated.
