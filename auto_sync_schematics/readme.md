# auto-sync cable driver

This is the schematics of the auto-synchronization electronics used for the paper.

The left part is the driver to generate the pulse and detect the reflected pulse in the cable. This is used by the primary board. 

The right part detects the pulse and includes the FET to reflect the pulse. This is used by the secondary board.

This was the first design to test the auto-sync scheme, which is not optimized in any way. It is matched with 50 Ohm on the driver and detector side. The pulse is reflected on a high impedance produced by the BJT (Q5). 

In the paper we propose an improofed setup which allows to synchronize several boards and not only two:
- the 50 Ohm terminations is at both ends of the cable, independent of the driver and detector. 
- the detector is connected with high impedance to the cable, so the same pulse can propagate to all secondary boards.
- a FET or BJT is used to induce a short-cirquit at the secondary board. this reflects an inverted pulse which needs a different detector on the primary board, than on the secondary board, but should make it easier to measure short cables where the generated and reflected pulse would otherwise overlap.
