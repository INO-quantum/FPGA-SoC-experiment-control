# FPGA buffer card

The FPGA-buffer card serves to buffer and level shift from the FPGA 3.3V to the 5V TTL level of the bus. For this purpose the 74HCT541 octal buffer is used, which is supplied with 5V from the rack but accepts the 3.3V input from the FPGA. The Cora-Z7 FPGA board is also supplied from the rack via the buffer card with 5V using a short cable with 2.1mm jack connected to the terminal block on the buffer card.

The buffer card also has the input and output clock buffers needed for locking with an external clock and to synchronize several boards with one board providing the clock to the other boards. 

The first PCB version was v1.2 and features basic buffer capabilities for the bus and clock.

Version v1.3 features additional buffers which permit to drive two nearby sub-racks from a single FPGA-SoC board. One of the two sub-racks is connected to the backplane connector, and the second sub-rack is connected with a 50-pole ribbon cable (via the daughter-connectors) to the buffer card of the first rack. This provides independent strobe signals for the two sub-racks which enables to update one or the other rack (or both) and to correct for electronic delays between the sub-racks. The timing can be configured in the server.config file.

>[!IMPORTANT]
>The buffer cards need to be configured such that one card can drive the other card and that two independent strobe signals are sent to the proper sub-rack. On the driven card the first buffers need to be set to tri-state. See schematics or ask me for assistance.

The newest version v1.4 uses a differential clock signal from the clock buffer into the FPGA board and allows to place additional small resistors in series to the signals towards the sub-rack. This should reduce the sensitivity to electrical discharges which sometimes cause that the clock unlocks and gives an error in the software.

Each folder contains the schematics and production files including Gerber and drill files and bill of materials. An additional "shopping list" is provided with the codes from RS or Mouser. The boards are simple double layer with most components placed on one side. 

>[!IMPORTANT]
>The buffer card must be configured for the clock input signal which can be either **sine wave** with +10dBm/2Vpp @ 50Ohm around zero or a **LVPECL** signal with 0.8Vpp at ca. 1.3V offset. Please consult the schematics for the details. The clock output is always a 10MHz LVPECL signal. Note that if you try to measure the output clock without the proper load it will stay at the DC offset voltage without oscillations.

At the moment the clock input and output frequencies are set to fixed 10MHz in the firmware. This is the lowest frequency the PLLs of the FPGA board can accept. If you need higher clock frequencies please ask for an updated firmware version.


