# ErgoDox RP2040 build contract

This file is the contract for the two KiCad 10 projects under `hw/ergodox-rp2040/`. It does not generate those projects, order boards, or upload anything to a fab. Normative coordinates are `notes/geometry.json`. Normative legacy nets are `ErgoDOX pcb/ErgoDOX.net`. Part numbers below are filled only when `notes/parts.md` recorded an LCSC page or when this pass opened the page. Empty LCSC cells are unverified. Do not invent a number to fill one.

The legacy tree `ErgoDOX pcb/` and `ErgoDox Acrylic Case/` is read-only.

## 1. What is already decided

Each half is its own RP2040 board. A standard USB 2.0 C-to-C cable between the two LINK receptacles carries full-duplex UART, not USB. ZMK has no stable USB split transport. See section 3.

The right-hand project copies the legacy PCB geometry. That geometry matches the Litster Standard Right plate. The left-hand project is the in-plane mirror that matches the Standard Left plate. Switches plug in from the front. Hotswap sockets, diodes, LEDs and the controller are on the back. Only the two USB-C receptacles and the two buttons are on the front. The left board mirrors part positions, never footprints: a mirrored QFN or socket is not a real part, so each side is placed and routed on its own. This is not the legacy reversible single PCB.

One Python script generates both projects. The only intentional differences are:

- LINK D+ / D− swap (section 8)
- board-id strap (section 9)
- silkscreen `LEFT` or `RIGHT`, plus `LINK` and `NOT A PC PORT` on the LINK receptacle

Everything else, including the matrix, the power tree, and the GPIO numbers, is the same circuit.

## 2. Block diagram

Words, one half:

- HOST USB-C is a USB full-speed device port on the RP2040 USB PHY. CC1 and CC2 each have their own 5.1 kΩ to GND. The RP2040 never presents Rp on HOST. VBUS enters the board 5 V rail through a Schottky, so the board cannot back-power the PC.
- LINK USB-C is not a PC port. Its D+ and D− are UART TX and RX, with series resistors and an ESD diode. Its CC pins switch between Rd (sink) and Rp (source). Its VBUS is either sunk onto the 5 V rail through a second Schottky, or sourced from the 5 V rail through a high-side load switch.
- The half that sees HOST VBUS is the power source on LINK. The other half is the power sink. That power role is hardware and runtime. The ZMK central/peripheral role is not. See section 3.
- +5 V feeds the AP2112K-3.3 LDO and the LED 5 V load switch. The LDO feeds every RP2040 3.3 V pin and the flash. The on-chip regulator makes 1.1 V for the core.
- 38 MX hotswap positions, the keys of the Litster Standard plate, form a diode matrix on GPIO. No I/O expander. The 4 legacy alternate thumb positions are dropped: their sockets overlap the main thumb sockets and cannot be assembled. One reverse-mount SK6812MINI-E per key shines up through a board cutout under the switch. One chain, data from one GPIO, power from the switched 5 V rail.
- BOOTSEL is a button on QSPI CS through 1 kΩ. RESET is a button on RUN.

## 3. ZMK role versus power role

Opened this pass: [ZMK split keyboards](https://zmk.dev/docs/features/split-keyboards) and [split configuration](https://zmk.dev/docs/config/split), development docs.

ZMK names two transports, Bluetooth and full-duplex wired UART. Only one can be active. Bluetooth is the tested one. RP2040 has no BLE radio (product brief, opened this pass: 2 UARTs, 1 USB 1.1 PHY, no radio). Full-duplex UART is in the tree and is described as a recent addition for early adopters. The same page says half-duplex is future work and is not finished. There is no USB-protocol split on that page, and `notes/zmk.md` records that `app/src/split/` has only `bluetooth/` and `wired/`. Do not design LINK as USB device-to-device.

Wired split on RP2040 is interrupt mode. The configuration page lists RP2040 under interrupt-driven UART, not async/DMA. Use the hardware PL011 `uart0`. Do not point `zmk,wired-split` at a PIO UART. Do not set `half-duplex`.

Role is compile-time:

- `CONFIG_ZMK_SPLIT=y` on both images.
- `CONFIG_ZMK_SPLIT_ROLE_CENTRAL=y` on the central image only. The Kconfig default is `n` (peripheral).
- The build produces two images. Flash the central image into the half whose HOST plug is in the computer. Flash the peripheral image into the other half.
- `zmk,wired-split` has no role property and no VBUS property. A GPIO on HOST VBUS cannot change which image is running.
- The docs' "Runtime Switching" section switches Bluetooth versus wired UART. It is highly experimental, has no reference design, and is not a central/peripheral handover. Do not use it.

Power role is the opposite. It follows HOST VBUS at runtime and must not be wired to the ZMK Kconfig. A board-id strap can tell left from right. It also cannot change the ZMK role.

If the images are flashed onto the wrong halves, LINK power can still be safe and the keyboard will not work as one ZMK device. The operator fixes that by flashing, not by a runtime detect pin.

Devicetree shape, pins from section 9, not from the ZMK example (that example uses GP0, which this board uses for UART):

```dts
/ {
    wired_split {
        compatible = "zmk,wired-split";
        device = <&uart0>;
    };
};
```

Both images use the same UART node. ZMK does not document a baud. Do not copy 115200 from a console node and call it a split requirement. Both halves must be set to the same speed. Pick it when the firmware is written and record it there.

Underglow is `CONFIG_ZMK_RGB_UNDERGLOW=y` with `chain-length = <38>` on each half, not 76. The ZMK lighting page says per-key LEDs of the WS2812 family, including SK6812, use underglow. Drive the chain with the PIO SPI pattern on that page, on GPIO2, not on the example's GPIO0.

## 4. Power tree

```text
HOST VBUS ----|>|---- +5V ----+---- AP2112K-3.3 EN=VIN ---- +3V3 ---- RP2040 IOVDD,
             SS14             |                                 |     USB_VDD, ADC_AVDD,
                              |                                 |     VREG_VIN, flash VCC
                              |                                 +---- RP2040 VREG_OUT 1.1 V
                              |                                       tied to both DVDD
                              |
                              +---- TPS22917 (LED) ---- LED_5V ---- 38x SK6812MINI-E
                              |
                              +---- TPS22917 (LINK source) ---- LINK VBUS
                              |
LINK VBUS ----|>|-------------+
             SS14 (sink only)
```

- HOST Schottky: anode at the HOST VBUS pads, cathode at +5V. The PC is never back-powered.
- LINK sink Schottky: anode at the LINK VBUS pads, cathode at +5V. +5V cannot flow backward onto the cable through this diode.
- LINK source switch: VIN at +5V, VOUT at LINK VBUS. This is the only path that drives the cable. It is off unless section 5 says on.
- The two Schottkys OR HOST and LINK into +5V. A half with only LINK power (the peripheral) boots from that rail. A half with only HOST power (the central) boots from HOST.
- LED switch and LINK switch are the same part, TI TPS22917DBVT, LCSC C2680344, two pieces. Active high. SOT-23-6 pins from `notes/parts.md`: 1 VIN, 2 GND, 3 ON, 4 CT, 5 QOD, 6 VOUT. Leave CT open. Leave QOD open. Do not leave ON floating. 10 kΩ from ON to GND on each switch.
- AP2112K-3.3TRG1, LCSC C51118. SOT-25 pins from `notes/parts.md`: 1 VIN, 2 GND, 3 EN, 5 VOUT. Tie EN to VIN. 1 µF X5R on VIN and on VOUT. Do not copy the NCP1117 10 µF values from the Raspberry Pi minimal example. Those belong to the NCP1117, which this board does not use.
- On-chip regulator: VREG_VIN (pin 44) from +3V3, VREG_VOUT (pin 45) tied to DVDD pins 23 and 50. Product brief, opened this pass: VREG_VOUT is 1.1 V, 100 mA max. 1 µF close to pin 44 and 1 µF close to pin 45.
- IOVDD pins 1, 10, 22, 33, 42, and 49, USB_VDD pin 48, and ADC_AVDD pin 43 are +3V3. TESTEN pin 19 is GND. GND pad is pin 57.

SS14 forward drop on the JLCPCB page, as copied in `notes/parts.md`, is 550 mV at 1 A. The drop at the budget current was not read from a curve. LED VDD is therefore not a stiff 5.0 V. Do not raise the brightness cap to spend that unknown drop.

## 5. LINK CC and VBUS

A USB 2.0 C-to-C cable connects VBUS to VBUS, GND to GND, D+ to D+, and D− to D−. Release 1.0 Table 3-11, and the same wiring in the Microchip USB-C cable table opened via search this pass: plug A5 (CC) is one wire to the other plug's A5; A6 (Dp) goes to A6; A7 (Dn) goes to A7. The note on that table says plug B5 (VCONN) is for electronically marked cables. A plain USB 2.0 cable does not have to present Ra. Full-featured and e-marked cables do present Ra, about 800 Ω to 1.2 kΩ, on the unused CC pin. Detection must work for both.

Rp and Rd, from the Type-C tables quoted on the pages opened this pass (Chiptron USB-C pinout, the DigiKey Type-C current note, and the Release 1.1 redline extract):

| Advertisement | Rp to 5 V | Rp to 3.3 V | Current source |
| --- | --- | --- | --- |
| Default USB | 56 kΩ ±20% | 36 kΩ ±20% | 80 µA ±20% |
| 1.5 A | 22 kΩ ±5% | 12 kΩ ±5% | 180 µA ±8% |
| 3.0 A | 10 kΩ ±5% | 4.7 kΩ ±5% | 330 µA ±8% |

This LINK source advertises Default USB only. Rp is 36 kΩ ±20% to +3V3, one resistor per CC pin. Do not pull Rp up to 5 V. Do not advertise 1.5 A or 3 A. The host port is not a 3 A supply, and the peripheral would be allowed to draw the advertisement. Rd is 5.1 kΩ ±1% to GND, one resistor per CC pin. Never tie CC1 to CC2.

Source-side windows below are the Default USB numbers in the Release 1.1 redline extract opened this pass (that extract's Table 4-21). They were not re-read from USB Type-C Release 2.4. Confirm them against the current USB-IF source-side table before the thresholds are frozen. `notes/parts.md` does record Release 2.4 Table 4-28 for the sink resistor: 5.1 kΩ ±10% to GND, maximum voltage on that pin 2.04 V.

| Window | Release 1.1 extract, Default USB, source side |
| --- | --- |
| vRa | 0.00 V to 0.15 V, threshold 0.20 V |
| vRd | 0.25 V to 1.50 V, threshold 1.60 V |
| vOPEN | above 1.65 V |

With 36 kΩ to 3.3 V and the far-end resistor, ignoring sense-divider load:

- Far Rd 5.1 kΩ: V = 3.3 × 5.1 / 41.1 = 0.409 V, inside vRd.
- Ra 1.0 kΩ: V = 3.3 × 1.0 / 37 = 0.089 V, inside vRa. At 1.2 kΩ, V = 0.106 V, still inside vRa.
- Open: V = 3.3 V, vOPEN.

The sense divider adds load. It must leave an open pin, pulled up only by 36 kΩ, above 1.65 V. A divider whose resistance to GND is not much larger than 36 kΩ will make an open pin look like a sink. That is a forbidden false source.

### 5.1 Circuit on each CC pin

CC1 and CC2 are separate copies of this circuit.

- Rd path, present with no local power. 5.1 kΩ from CC to a depletion-mode P-channel JFET, source of the JFET at GND, gate at `LINK_RP_EN`. Vgs = 0 keeps the JFET on, which is the unpowered and the peripheral state. `LINK_RP_EN` high turns the JFET off and removes Rd. Part: onsemi MMBFJ177LT1G, LCSC C106763, SOT-23 pad 1 drain, 2 source, 3 gate. Its on-resistance (300 Ω on the LCSC page) adds to the 5.1 kΩ Rd. The datasheet Vgs(off) was not re-read against 3.3 V this pass. An enhancement MOSFET here is wrong: it is off when unpowered, the central never sees Rd, and LINK VBUS never turns on.
- Rp path. 36 kΩ from +3V3 to an N-channel MOSFET, other side of the MOSFET at CC, gate at `LINK_RP_EN`. On only while sourcing. Part: 2N7002, LCSC C8545, basic, SOT-23 pad 1 gate, 2 source, 3 drain.
- `LINK_RP_EN` has 10 kΩ to GND. It is driven high only when the HOST VBUS divider says HOST is present. Unpowered and peripheral stay at Rd, with Rp off.
- Sense. CC does not touch a GPIO or an ADC pin directly. A high-value divider brings each CC to ADC1 and ADC2. The divider load to GND must keep vOPEN above 1.65 V, and 5.5 V on CC must still be at or below 3.0 V on the ADC pin. Resistor LCSC cells stay blank until those parts are opened.
- The same rule for VBUS. HOST VBUS and LINK VBUS reach ADC0 and ADC3 only through dividers. 5.5 V at the connector maps to 3.0 V or less on the pin. A compliant USB-C source is 5 V until a PD contract. This board does not speak PD and does not accept a 9/15/20 V contract. The divider is for vSafe5V (5.5 V max), not for a 20 V mis-plug. That 20 V case is outside this contract.

`LINK_SRC_EN` is the firmware request for the source switch. The switch ON pin is low whenever HOST VBUS is absent, even if that GPIO is high. Implement that as a gate that shorts ON to GND when the HOST divider is low, in series with the 10 kΩ pulldown already required. The peripheral cannot source.

### 5.2 State table

`RP_EN` is `LINK_RP_EN`. The source switch is the LINK TPS22917.

| State | HOST VBUS | RP_EN | Rd | Rp | What CC shows | Source switch | Who feeds +5V |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Peripheral, central alive, plain cable | absent | low | on | off | central's Rp against our Rd | off | LINK, through the sink Schottky |
| Peripheral, e-marked cable | absent | low | on | off | same, other CC has Ra in the cable | off | LINK |
| Central, peripheral attached, plain cable | present | high | off | on | one pin vRd (0.41 V), the other vOPEN | on | HOST |
| Central, peripheral attached, e-marked cable | present | high | off | on | one pin vRd, the other vRa | on | HOST |
| Central, nothing on LINK, or cable with the far end open | present | high | off | on | both vOPEN, or one vRa and one vOPEN, and no vRd | off | HOST |
| Both halves plugged into PCs, LINK cable between them | present on both | high on both | off | off Rp on both | through-wire sits near 3.3 V (vOPEN); the other pin is vOPEN or vRa; no vRd | off on both | each half from its own HOST |
| LINK plugged into a PC while this half is a source | present | high | off | on | far side is also a source, so no vRd; CC can be pulled above 3.3 V by the PC's Rp | off | HOST. ADC stays inside the divider limit |
| Neither cable powered | absent | low (no 3.3 V) | on, passive | off | n/a | off | unpowered |

Enable the source switch only when HOST VBUS is present and one CC pin is inside vRd and the other is inside vRa or vOPEN. Any other combination, including both pins vOPEN and the two-source case, leaves the switch off. Never enable because the other side is also a source.

Both-PCs is electrically safe and is not a valid ZMK configuration. ZMK still has only one central image. Do not try to make both halves central.

## 6. HOST USB

Receptacle is the same part as LINK: Korean Hroparts Elec TYPE-C-31-M-12, LCSC C165948, extended. This pass opened the JLCPCB page: 16 pins, USB 2.0, 20 V, 5 A listed on the page. Footprint, from the KiCad 10.0.7 image this pass: `Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12`. Pads in that file are A1, A4, A5, A6, A7, A8, A9, A12, B1, B4, B5, B6, B7, B8, B9, B12, and four shell pads SH. There are no SuperSpeed pads. Pad geometry was not checked against the HRO drawing.

| Pads | HOST net |
| --- | --- |
| A4, A9, B4, B9 | HOST_VBUS, then the SS14 anode |
| A1, A12, B1, B12, SH | GND |
| A5 | CC1, own 5.1 kΩ to GND, nothing else |
| B5 | CC2, own 5.1 kΩ to GND, nothing else |
| A6 tied to B6 | USB_DP |
| A7 tied to B7 | USB_DM |
| A8, B8 | no connect |

Tie A6 to B6 and A7 to B7 next to the receptacle. The maximum stub length was not re-read from the USB-IF PDF this pass. Keep the stub short.

USB_DP goes through 27 Ω, 1%, to RP2040 pin 47 `USB_DP`. USB_DM goes through 27 Ω, 1%, to pin 46 `USB_DM`. Those resistors sit next to the RP2040, which is what Hardware design with RP2040 requires. Part is Uni-Royal 0402WGF270JTCE, LCSC C25100, from `notes/parts.md`. No extra pull-up or pull-down on the pair. The PHY has them.

ESD is ST USBLC6-2SC6, LCSC C7519, one part on HOST D+ / D−, placed at the receptacle. KiCad has `Package_TO_SOT_SMD:SOT-23-6`. `notes/parts.md` says the pads were not checked against the ST drawing. Do not copy a remembered pinout. Open the ST datasheet when the symbol is drawn. The page recorded in `notes/parts.md` lists 2 channels, 5.25 V stand-off, 3.5 pF, SOT-23-6L.

The product brief calls the PHY a USB 1.1 controller with full-speed device and host. The connector is wired as USB 2.0 full speed (12 Mbit/s), which is that PHY. This board is not high speed and does not use a high-speed eye diagram as an excuse to change the 90 Ω target. The target stays 90 Ω because that is what chapter 2 of Hardware design with RP2040 sets for this pair. The geometry is section 13, and it is not the chapter's 1 mm two-layer example.

## 7. Crystal load capacitors

Part: Abracon ABM8-272-T3, LCSC C20625731. Chapter 2 of Hardware design with RP2040 and the Abracon drawing, as recorded in `notes/parts.md` and `notes/rp2040-checklist.md`: 12.000 MHz fundamental, load capacitance CL = 10 pF, shunt C0 = 3.0 pF max (this is not the PCB stray term), ESR 50 Ω max, drive 10 µW typical and 200 µW max.

The chapter's formula, same source:

- Two equal capacitors, one on each crystal pin to GND, are in series, so each must be `2 × (CL − Cstray)` for the series pair to equal `CL − Cstray`.
- The chapter assumes Cstray = 3 pF for the pins and the tracks. This board uses that assumption. It is not a measurement of this layout.
- Ideal equal value: `2 × (10 − 3) = 14` pF.
- Fitted value: 15 pF, C0G, 50 V, ±5%, FH 0402CG150J500NT, LCSC C1548, one on XIN and one on XOUT. Series combination 7.5 pF, plus 3 pF, total 10.5 pF against the 10 pF target. The chapter calls 15 pF close enough. Keep the crystal tracks short so the 3 pF assumption stays valid.

1 kΩ, 1%, LCSC C11702, in series from pin 21 `XOUT` toward the crystal, at 3.3 V IOVDD, for this crystal's 50 Ω maximum ESR. The other C11702 is the BOOTSEL series resistor. Do not change the crystal, the series resistor, or IOVDD without the retest the chapter describes.

KiCad footprint `Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm` is in the 10.0.7 image. Its description cites a different crystal drawing. Pads were not compared with the Abracon drawing. On the Raspberry Pi R3 layout, as recorded in the checklist, crystal pads 2 and 4 are GND, pad 1 is XIN, and the series resistor sits between XOUT and pad 3. Confirm that against the Abracon drawing before the footprint is trusted.

## 8. Full-duplex UART on LINK

ZMK full duplex crosses TX to RX. A straight-through C-to-C cable does not cross D+ and D− (section 5). The boards do the cross:

| Half | GPIO2 is not involved | D+ (A6 and B6) | D− (A7 and B7) |
| --- | --- | --- | --- |
| Left |  | UART0 TX, GPIO0, package pin 2 | UART0 RX, GPIO1, package pin 3 |
| Right |  | UART0 RX, GPIO1, package pin 3 | UART0 TX, GPIO0, package pin 2 |

Left TX lands on right RX, and left RX lands on right TX, with the cable plugged either way up, because A6 is tied to B6 and A7 is tied to B7 on both receptacles.

UART0 on GPIO0 / GPIO1 is a legal pair. `notes/zmk.md` records the Zephyr RP2040 pinmux header: UART0 TX/RX on P0/P1, P12/P13, P16/P17, or P28/P29. P28/P29 are ADC pins on this board, so they are not the UART. RX needs `input-enable` in pinctrl. No sleep pinctrl on this UART.

On each UART net, from the RP2040 out to the receptacle: GPIO, then 27 Ω (C25100, same verified part, used here as a series resistor and not as a USB-impedance requirement), then the wire, with USBLC6-2SC6 at the receptacle. A second C7519 is the LINK ESD part. RP2040 GPIO is not a 5 V pin. The product brief limits IOVDD to a nominal 3.3 V. Absolute maximum was not re-opened. The series resistor and the ESD diode are mandatory. Confirm the USBLC6 clamp actually protects a 3.3 V pin before release; do not claim the GPIO is 5 V tolerant.

Silkscreen on this receptacle, both halves: `LINK` and `NOT A PC PORT`.

## 9. GPIO map

Package pins are from the RP2040 product brief pinout, opened this pass (published August 2022). No GPIO is used twice. Pins that are not GPIO are listed so they are not quietly reused.

| GPIO | Package pin | Function | Direction |
| --- | --- | --- | --- |
| GPIO0 | 2 | LINK UART0 TX | out |
| GPIO1 | 3 | LINK UART0 RX | in |
| GPIO2 | 4 | SK6812 data, PIO | out |
| GPIO3 | 5 | LED 5 V switch ON | out, pulldown on the pin's net |
| GPIO4 | 6 | LINK source-switch request | out, hardware-gated by HOST VBUS |
| GPIO5 | 7 | LINK_RP_EN | out, pulldown, high = source |
| GPIO6 | 8 | ROW0 | in, pull-up |
| GPIO7 | 9 | ROW1 | in, pull-up |
| GPIO8 | 11 | ROW2 | in, pull-up |
| GPIO9 | 12 | ROW3 | in, pull-up |
| GPIO10 | 13 | ROW4 | in, pull-up |
| GPIO11 | 14 | ROW5 | in, pull-up |
| GPIO12 | 15 | COL0 | out |
| GPIO13 | 16 | COL1 | out |
| GPIO14 | 17 | COL4 | out |
| GPIO15 | 18 | COL5 | out |
| GPIO16 | 27 | COL6 | out |
| GPIO17 | 28 | COL10 | out |
| GPIO18 | 29 | COL11 | out |
| GPIO19 | 30 | Board id | in |
| GPIO20 | 31 | unused | pull-down, no connect |
| GPIO21 | 32 | unused | pull-down, no connect |
| GPIO22 | 34 | unused | pull-down, no connect |
| GPIO23 | 35 | unused | pull-down, no connect |
| GPIO24 | 36 | unused | pull-down, no connect |
| GPIO25 | 37 | unused | pull-down, no connect |
| GPIO26 / ADC0 | 38 | HOST VBUS sense, after divider | analog in |
| GPIO27 / ADC1 | 39 | LINK CC1 sense, after divider | analog in |
| GPIO28 / ADC2 | 40 | LINK CC2 sense, after divider | analog in |
| GPIO29 / ADC3 | 41 | LINK VBUS sense, after divider | analog in |

Board id: GPIO19 has 10 kΩ to GND on the left project and 10 kΩ to +3V3 on the right project. The firmware may read it to tell the halves apart. It must not use it to pick the ZMK role.

Not GPIO, and not available for the matrix:

| Package pin | Name | Connection |
| --- | --- | --- |
| 19 | TESTEN | GND |
| 20 | XIN | crystal |
| 21 | XOUT | 1 kΩ, then crystal |
| 24 | SWCLK | optional test pad only |
| 25 | SWDIO | optional test pad only |
| 26 | RUN | RESET button to GND |
| 43 | ADC_AVDD | +3V3 |
| 44 | VREG_VIN | +3V3 |
| 45 | VREG_VOUT | 1.1 V to both DVDD |
| 46 | USB_DM | HOST D− |
| 47 | USB_DP | HOST D+ |
| 51 | QSPI_SD3 | flash |
| 52 | QSPI_SCLK | flash |
| 53 | QSPI_SD0 | flash |
| 54 | QSPI_SD2 | flash |
| 55 | QSPI_SD1 | flash |
| 56 | QSPI_SS | flash CS, BOOTSEL |
| 57 | GND pad | ground vias, section 12 |

Column names stay the legacy names. They are not renumbered to COL0–COL6. COL2, COL3, COL7, COL8, and COL9 do not exist in the legacy netlist.

Scan: columns are outputs, idle high, one column driven low at a time. Rows are inputs with pull-ups. A pressed key reads low. That matches the legacy diode: symbol pin 4 is the cathode and it sits on the column net (`ErgoDOX.net` library section and the column nets).

## 10. Matrix

Legacy electrical positions, from `ErgoDOX pcb/ErgoDOX.net`. Each socket gets its own 1N4148W, cathode toward the column named here. The four alternate thumbs keep the nets they had. They are not new rows.

| Reference | Row | Column | Notes |
| --- | --- | --- | --- |
| SW0:7 | ROW0 | COL6 | plate key |
| SW0:8 | ROW0 | COL5 | plate key |
| SW0:9 | ROW0 | COL4 | plate key |
| SW0:10 | ROW0 | COL10 | plate key, stabilizer S2 |
| SW0:11 | ROW0 | COL11 | plate key, stabilizer S1 |
| SW0:12 | ROW0 | COL1 | plate key |
| SW1:9 | ROW1 | COL4 | plate key |
| SW1:10 | ROW1 | COL10 | plate key |
| SW1:11 | ROW1 | COL11 | plate key |
| SW1:12 | ROW1 | COL1 | plate key |
| SW1:13 | ROW1 | COL0 | plate key |
| SW2:7 | ROW2 | COL6 | plate key |
| SW2:8 | ROW2 | COL5 | plate key |
| SW2:9 | ROW2 | COL4 | plate key |
| SW2:10 | ROW2 | COL10 | plate key |
| SW2:11 | ROW2 | COL11 | plate key |
| SW2:12 | ROW2 | COL1 | plate key |
| SW2:13 | ROW2 | COL0 | plate key |
| SW3:8 | ROW3 | COL5 | plate key |
| SW3:9 | ROW3 | COL4 | plate key |
| SW3:10 | ROW3 | COL10 | plate key |
| SW3:11 | ROW3 | COL11 | plate key |
| SW3:12 | ROW3 | COL1 | plate key |
| SW3:13 | ROW3 | COL0 | plate key |
| SW4:7 | ROW4 | COL6 | plate key |
| SW4:8 | ROW4 | COL5 | plate key |
| SW4:9 | ROW4 | COL4 | plate key |
| SW4:10 | ROW4 | COL10 | plate key |
| SW4:11 | ROW4 | COL11 | plate key |
| SW4:12 | ROW4 | COL1 | plate key |
| SW4:13 | ROW4 | COL0 | plate key |
| SW5:7 | ROW5 | COL6 | plate key |
| SW5:8 | ROW5 | COL5 | plate key |
| SW5:9 | ROW5 | COL4 | plate key |
| SW5:10 | ROW5 | COL10 | plate key |
| SW5:11 | ROW5 | COL11 | plate key |
| SW5:12 | ROW5 | COL1 | plate key |
| SW5:13 | ROW5 | COL0 | plate key |

Empty crossings, do not add a switch: ROW0/COL0, ROW3/COL6.

38 `SW*` references are the plate keys, and 38 MX sockets are placed.

Diode: 1N4148W, LCSC C81598, SOD-123, qty 38. KiCad `Diode_SMD:D_SOD-123`.

Hotswap socket: HanElectricity CPG151101S11-16, LCSC C41430893, qty 38, from `notes/parts.md`. That page's manufacturer is not Kailh. A Kailh-branded LCSC page was not opened. The KiCad 10.0.7 image has `Button_Switch_Keyboard` Cherry MX footprints and no footprint whose name matches Hotswap, Kailh, or CPG1511. The Cherry MX 1.00u PCB footprint is a through-hole switch (pads 1 and 2 only), not a socket, and it has no LED pads. Do not substitute it for the socket. Do not draw a socket from memory. Vendor a published hotswap footprint and check its pads against the C41430893 drawing before release. MX switch bodies are not in the assembly BOM. The socket is.

Switch center and rotation come from `notes/geometry.json`. SW0:12 on the right board is turned 180° so its socket pad clears a mounting hole; the plate cutout is square, so the switch goes in turned too. The socket footprint's origin is that center.

## 11. LED chain

One OPSCO SK6812MINI-E, LCSC C5149201, extended, per key. Qty 38. Power from `LED_5V` only, never from +3V3. Data from GPIO2, one chain, no branch.

The LED is reverse-mounted on the back and shines up through a cutout under the switch. Footprint: KiCad `LED_SMD:LED_SK6812MINI-E_3.2x2.8mm_P1.5mm_ReverseMount`, whose description cites the C5149201 datasheet. The footprint carries its own `Edge.Cuts` cutout. It sits at switch-local (0, +5.08) mm, the MX LED window. Its pads are 0.25 mm from that cutout by design, so `.kicad_dru` lowers the edge clearance to 0.2 mm for `DS*` only.

The JLCPCB page lists 3.7 V to 5.5 V supply and 800 kbit/s. The SK6812MINI-E VIH row was not read this pass. The older note for the 5050 SK6812 was VIH minimum `0.65 × VDD` (3.25 V at 5.0 V) against RP2040 VOH minimum 2.62 V. Assume the same margin problem until the MINI-E datasheet is read. No level shifter is fitted. It stays a blocker in section 17.

Chain order is the PCB order and the firmware index. Index 1 is the first LED, fed from GPIO2. The chain snakes by legacy row, and within a row by KiCad X, reversing every other row. Coordinates below are the right-hand board, Y down, from `notes/geometry.json`.

| Index | Reference | x mm | y mm | rotation deg |
| --- | --- | --- | --- | --- |
| 1 | SW0:7 | 34.69894 | 143.26870 | 25 |
| 2 | SW0:9 | 42.74820 | 160.53308 | 25 |
| 3 | SW0:12 | 50.80000 | 177.80000 | 25 |
| 4 | SW0:8 | 51.96332 | 135.21944 | 25 |
| 5 | SW0:11 | 64.03848 | 161.11728 | 115 |
| 6 | 6 | SW0:10 | 81.30286 | 153.06548 | 115 |
| 8 | 7 | SW1:13 | 186.69000 | 143.20266 | 0 |
| 8 | SW1:12 | 167.64000 | 143.20266 | 0 |
| 9 | SW1:11 | 148.59000 | 140.02766 | 0 |
| 10 | SW1:10 | 129.54000 | 138.43000 | 0 |
| 11 | SW1:9 | 110.49000 | 140.02766 | 0 |
| 14 | 15 | 12 | SW2:7 | 72.39000 | 117.48516 | 90 |
| 13 | SW2:8 | 91.44000 | 122.24766 | 0 |
| 14 | SW2:9 | 110.49000 | 120.97766 | 0 |
| 15 | SW2:10 | 129.54000 | 119.38000 | 0 |
| 16 | SW2:11 | 148.59000 | 120.97766 | 0 |
| 17 | SW2:12 | 167.64000 | 124.15266 | 0 |
| 18 | SW2:13 | 191.45250 | 124.15266 | 0 |
| 19 | SW3:13 | 191.45250 | 105.10266 | 0 |
| 20 | SW3:12 | 167.64000 | 105.10266 | 0 |
| 21 | SW3:11 | 148.59000 | 101.92766 | 0 |
| 22 | SW3:10 | 129.54000 | 100.33000 | 0 |
| 23 | SW3:9 | 110.49000 | 101.92766 | 0 |
| 24 | SW3:8 | 91.44000 | 103.19766 | 0 |
| 25 | SW4:7 | 72.39000 | 88.91016 | 90 |
| 26 | SW4:8 | 91.44000 | 84.14766 | 0 |
| 27 | SW4:9 | 110.49000 | 82.87766 | 0 |
| 28 | SW4:10 | 129.54000 | 81.28000 | 0 |
| 29 | SW4:11 | 148.59000 | 82.87766 | 0 |
| 30 | SW4:12 | 167.64000 | 86.05266 | 0 |
| 31 | SW4:13 | 191.45250 | 86.05266 | 0 |
| 32 | SW5:13 | 191.45250 | 67.00520 | 0 |
| 33 | SW5:12 | 167.64000 | 67.00520 | 0 |
| 34 | SW5:11 | 148.59000 | 63.82766 | 0 |
| 35 | SW5:10 | 129.54000 | 62.23000 | 0 |
| 36 | SW5:9 | 110.49000 | 63.82766 | 0 |
| 37 | SW5:8 | 91.44000 | 65.10020 | 0 |
| 38 | SW5:7 | 72.39000 | 65.10020 | 0 |

The left project uses the mirrored coordinates and the same index order. `color-mapping` in the ZMK example is green, red, blue. Zephyr's usual WS2812 pixel is GRB. The OPSCO PDF's channel order was not re-read this pass. Confirm GRB against the C5378720 PDF before the first light-up. Do not assume an RGBW channel.

Firmware cap is section 14. The LED load switch stays off until the USB device is configured, and it stays off when the pattern is dark.

## 12. RP2040 minimal circuit

Follow Hardware design with RP2040, chapter 2, release 2, build date 20/08/2026, schematic RPI-RP2040-MINIMAL revision S1 dated 2026-07-03. The local extract is `notes/rp2040-checklist.md`. The example board in that chapter is two-layer and nominally 1 mm. Do not copy its USB geometry. Do copy the connectivity below.

Flash: Winbond W25Q128JVSIQ, LCSC C97521, 128 Mbit. KiCad `Package_SO:SOIC-8_5.3x6.2mm_P1.27mm` (description says 208 mil). Pads were not checked against the Winbond drawing.

| RP2040 pin | Flash pin |
| --- | --- |
| 56 QSPI_SS | 1 CS |
| 52 QSPI_SCLK | 6 CLK |
| 53 QSPI_SD0 | 5 DI / IO0 |
| 55 QSPI_SD1 | 2 DO / IO1 |
| 54 QSPI_SD2 | 3 WP / IO2 |
| 51 QSPI_SD3 | 7 HOLD / IO3 |
| +3V3 | 8 VCC, 100 nF to GND |
| GND | 4 GND |

QSPI tracks short and direct. 10 kΩ from QSPI_SS to +3V3 is on the schematic and is do-not-fit for this Winbond part (LCSC C25744). BOOTSEL: 1 kΩ from QSPI_SS to a button to GND. RESET: button from RUN (pin 26) to GND. The product brief says reset when RUN is low and run when RUN is high. The minimal schematic fits no external RUN pull-up. The checklist did not copy a pull-up resistance onto RUN.

Decoupling, C1525, 100 nF, the R3 set:

| Role | Net | Placement |
| --- | --- | --- |
| Flash VCC | +3V3 | at the flash |
| DVDD | +1V1 | one near pin 50, one near pin 23 |
| USB_VDD and IOVDD | +3V3 | one capacitor shared by pins 48 and 49 |
| IOVDD | +3V3 | one each near pins 1, 10, 22, 33, 42 |
| the R3 capacitor the chapter does not assign to a single pin | +3V3 | the checklist says a unique pin for this part is not in the chapter prose; place it on +3V3 next to pin 43 `ADC_AVDD`, because that power pin otherwise has no capacitor. This placement is a choice of this contract, not a sentence in chapter 2 |

That is 10 pieces of C1525. 1 µF C52923, four pieces: VREG_IN, VREG_OUT, AP2112 input, AP2112 output.

Ground pad. Chapter 2 does not state a via count. The published R3-S1 footprint `rpi_rp2040_vias`, measured in `notes/rp2040-checklist.md`, is the pattern this board uses: one 3.2 mm × 3.2 mm SMD pad, nine vias, copper 0.6 mm, drill 0.25 mm, centers at the nine combinations of x and y in {−1.1 mm, 0, +1.1 mm} relative to the package center. The only RP2040 footprint inside `kicad/kicad:10.0.7-full` is the tiny_tapeout demo `RP2040-QFN-56.kicad_mod`. Do not use that demo land pattern as the production pad. Use the R3-S1 via footprint, or a footprint checked against the datasheet package drawing. The datasheet package section was not opened this pass. The product brief physical page gives the body as 7 mm × 7 mm nominal and does not give the via rule.

L2 is solid ground under the whole QFN and under the whole HOST USB pair. No split in that ground, no track crossing the pair on L2.

## 13. Stackup and USB geometry

Finished board 1.6 mm, 4 layers. The legacy KiCad file says 1.6002 mm. The new boards are 1.6 mm, which is the JLCPCB thickness this stackup is built on. The case check is the outline, the holes, and the switch centers, not that 0.0002 mm.

Order stackup: **JLC04161H-7628**. Recorded in `notes/rp2040-checklist.md` from the JLCPCB impedance page with 1.6 mm, outer copper 1 oz, inner copper 0.5 oz checked. This pass opened the JLCPCB calculator guide (last updated 2026-09-16) and not the stackup table itself. The guide says the calculator computes the width. It does not print a 90 Ω USB result. It does print 1 oz external copper as 1.6 mil, 0.5 oz internal as 0.6 mil, and, in the prose, 15.2 μm for 0.5 oz internal on 4- to 8-layer boards. It also prints the soldermask figures below. The dielectric thicknesses are from the notes file, not re-measured here.

| Layer | Material | Thickness in the notes |
| --- | --- | --- |
| Top | Copper | 0.035 mm |
| Prepreg | 7628 × 1 | 0.21040 mm |
| Inner L2 | Copper | 0.0152 mm |
| Core | Core | 1.065 mm |
| Inner L3 | Copper | 0.0152 mm |
| Prepreg | 7628 × 1 | 0.21040 mm |
| Bottom | Copper | 0.035 mm |

Dielectric constants recorded on that same notes table: prepreg 7628 = 4.4, core = 4.6. Soldermask, also recorded there and repeated by the calculator guide: coating above substrate 1.2 mil, coating above the trace 0.6 mil, coating between traces 1.2 mil, dielectric constant 3.8. 4- to 8-layer material in the guide is Nan Ya Plastics NP-155F. Do not mix in 3313, 1080, or 2116 thicknesses.

Layer use:

- L1, top: signals, including the USB pair and the UART pair. Components on both sides are allowed.
- L2: solid GND. Reference for the USB pair. Unbroken under the pair and under the RP2040.
- L3: +5V, +3V3, and +1V1 pours. No USB pair on this layer.
- L4, bottom: signals and components.

### 90 Ω pair

JLCPCB Impedance Calculator, <https://jlcpcb.com/pcb-impedance-calculator>, inverse solution for picture `DiffEdgeCoupledCoatedMicrostrip1B` ("Differential Pair (Non coplanar)"), template `JLC04161H-7628` (id `30726297697b4c18a0946278a48fb7d8`). Outer microstrip to L2 uses only the 7628 prepreg: H = 0.2104 mm, which the calculator shows as H1 = 8.2835 mil. Live copper-trace config for 1 oz outer, preferred base-copper 0.5 oz row: T1 = 1.6 mil, etch compensation 0.5 mil (W2 = W1 − 0.5 mil). Live coverlay for that row: C1 = 1.0 mil, C2 = 0.6 mil, C3 = 1.0 mil, CEr = 3.8. The public guide's 1.2 mil mask figures are not what those config endpoints return.

The picture's Er1 stays 4.3. The calculator does not copy the stackup prepreg dielectric constant 4.4 into Er1. Inverse solve of W2 with the picture-default spacing held at S1 = 8.0 mil, Zo = 90 Ω, ZoTol = 0.5:

| Quantity | Calculator | Board |
| --- | --- | --- |
| Finished base width W1 | 11.443359 mil | **0.290661 mm** |
| Etched top width W2 | 10.943359 mil | fab compensation, not a second track width |
| Edge gap S1 | 8.000 mil | **0.203200 mm** |
| Reported Z at Er1 = 4.3 | 90.2938 Ω | use this geometry |

The same S1 with Er1 set to the stackup value 4.4 returned the same W1 and W2 and reported 89.5253 Ω. Both results are inside the 0.5 Ω tolerance the UI sends. Route W1 and S1. Do not copy 0.8 mm / 0.15 mm from Hardware design with RP2040 (that pair is the chapter's 1 mm two-layer example). Do not copy a third-party stackup model.

Route the pair side by side, matched, over the solid L2 ground for the whole length, including under the ESD diode. No acute corners. The 27 Ω resistors stay at the RP2040, not at the receptacle. Center-to-center spacing is 0.290661 + 0.203200 = 0.493861 mm.

## 14. Power budget

The cap is 500 mA from the HOST port after the device is configured. That is the Default USB current this board is allowed to plan on: the Type-C pages opened this pass describe Default USB Power as following the USB device rules, and the DigiKey note says that otherwise the sink may draw up to 500 mA. The USB 2.0 specification clause was not re-opened. Do not plan on 1.5 A or 3 A. LEDs stay off until the host has configured the device. The unconfigured unit-load number was not re-read from the USB 2.0 PDF.

When one HOST plug feeds the keyboard, that 500 mA covers both halves. The peripheral's LEDs and MCU ride on LINK VBUS, which comes out of the central's +5V.

Figures from the OPSCO table in `notes/parts.md`, at the stated test points:

- static, outputs off: 0.6 mA typical at VDD = 4.5 V. No maximum was copied.
- per color, VDD = 5.0 V, VDS = 1.0 V: 10 / 12 / 14.5 mA min / typical / max.

The numbers below were worked for 84 of the 5050 SK6812. The boards now carry 76 SK6812MINI-E (38 per half), and the MINI-E current table was not read. The 10% cap is kept as is; 76 LEDs draw less than 84 at the same per-LED current.

84 LEDs (42 per half):

- static, both halves, typical: 84 × 0.6 = 50.4 mA
- full white, typical: 84 × 3 × 12 = 3024 mA
- full white, max column: 84 × 3 × 14.5 = 3654 mA

Non-LED allowance: **80 mA** for both RP2040s, both flashes, both LDOs, and the CC bias. This is a design allowance, not a sum of datasheet currents. RP2040 active current and AP2112 quiescent current were not opened this pass. VREG_VOUT's 100 mA max is the 1.1 V core rail, not this 5 V number.

Remaining for PWM light: 500 − 80 − 50.4 = 369.6 mA.

Cap against the 14.5 mA column so the max drive still fits:

- fraction = 369.6 / 3654 = 0.1012
- firmware maximum = **10% of full-scale white**, both halves together
- if the ZMK brightness control is 0–255 and linear in channel current, the ceiling is `floor(0.1012 × 255) = 25`

Check: 0.1012 × 3654 = 370 mA of LED PWM, plus 50.4 mA static, plus 80 mA allowance = 500 mA. At the 12 mA typical column the same 10% cap is about 306 mA of PWM, and the total is about 436 mA.

The LED switch may be turned off when the pattern is dark, which removes the 50.4 mA. Do not spend that saving by raising the 10% cap unless this section is revised with measured currents.

The central image always uses the both-halves cap. It cannot see a runtime role, and a single HOST port is the supply whenever LINK is powering the other half. Two PCs, one per HOST, is a lower load per port. The cap stays at 10% anyway.

## 15. Parts on one half

LCSC values are from `notes/parts.md` unless the source column says this pass re-opened the page. Qty is one half, not a full keyboard. "Blank" means do not invent a number.

| Ref | Part | LCSC | Qty | Source |
| --- | --- | --- | --- | --- |
| U1 | Raspberry Pi RP2040, LQFN-56 | C2040 | 1 | notes/parts.md, extended |
| U2 | Winbond W25Q128JVSIQ | C97521 | 1 | notes/parts.md, basic |
| U3 | Diodes AP2112K-3.3TRG1 | C51118 | 1 | notes/parts.md, extended |
| U4, U5 | TI TPS22917DBVT, LED switch and LINK source switch | C2680344 | 2 | notes/parts.md, extended |
| J1, J2 | Korean Hroparts Elec TYPE-C-31-M-12 | C165948 | 2 | re-opened this pass, extended; notes/parts.md had the same code |
| D1 | ST USBLC6-2SC6, HOST D+/D− | C7519 | 1 | notes/parts.md, extended |
| D2 | ST USBLC6-2SC6, LINK TX/RX | C7519 | 1 | same part |
| D3, D4 | MDD SS14, HOST VBUS and LINK sink | C2480 | 2 | notes/parts.md, basic. Page Vf 550 mV at 1 A |
| D5–D42 | 1N4148W, matrix | C81598 | 38 | notes/parts.md, basic |
| DS1–DS38 | OPSCO SK6812MINI-E, reverse mount | C5149201 | 38 | LCSC and JLCPCB pages, extended |
| SW sockets | HanElectricity CPG151101S11-16 | C41430893 | 38 | notes/parts.md. Not a verified Kailh MPN |
| MX switches | not assembled |  | 0 | |
| SW_BOOT, SW_RST | XKB TS-1187A-B-A-B | C318884 | 2 | notes/parts.md, basic |
| Y1 | Abracon ABM8-272-T3, 12 MHz | C20625731 | 1 | notes/parts.md, extended |
| C_L1, C_L2 | 15 pF C0G 50 V, FH 0402CG150J500NT | C1548 | 2 | notes/parts.md, basic |
| C_1U | Samsung CL05A105KA5NQNC, 1 µF | C52923 | 4 | notes/parts.md, basic |
| C_100N | Samsung CL05B104KO5NNNC, 100 nF | C1525 | 10 | notes/parts.md part, qty from section 12 |
| R_1K | Uni-Royal 0402WGF1001TCE | C11702 | 2 | BOOTSEL and crystal damper |
| R_5K1 | Uni-Royal 0402WGF5101TCE | C25905 | 4 | HOST CC1, HOST CC2, LINK CC1, LINK CC2 |
| R_10K | Uni-Royal 0402WGF1002TCE | C25744 | 4 fitted, 1 DNF | fitted: two switch ON pulldowns, LINK_RP_EN pulldown, board-id. DNF: QSPI_SS pull-up |
| R_27 | Uni-Royal 0402WGF270JTCE | C25100 | 4 | HOST D+, HOST D−, LINK TX, LINK RX. Extended |
| R_RP | 36 kΩ ±20%, Rp to +3V3, one per LINK CC |  | 2 | value from the Type-C table. LCSC not opened |
| Q1, Q3 | onsemi MMBFJ177LT1G, Rd disconnect, one per LINK CC | C106763 | 2 | LCSC page |
| Q2, Q4 | 2N7002, Rp connect, one per LINK CC | C8545 | 2 | JLCPCB page, basic |
| Q5, Q6 | 2N7002, hold LINK source ON low unless HOST VBUS is present | C8545 | 2 | same part |
| R_DIV | CC and VBUS dividers, values per section 5 |  |  | unverified |

No level shifter is in this list. See section 11 and section 17.

Footprints that are in the KiCad 10.0.7 image and are the ones to prefer, after a pad check against the datasheet: `Package_SO:SOIC-8_5.3x6.2mm_P1.27mm`, `Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm`, `Package_TO_SOT_SMD:SOT-23-5`, `Package_TO_SOT_SMD:SOT-23-6`, `Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A`, `Diode_SMD:D_SOD-123`, `Diode_SMD:D_SMA`, `Capacitor_SMD:C_0402_1005Metric`, `Resistor_SMD:R_0402_1005Metric`, `Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12`. AP2112 is SOT-25; confirm SOT-23-5 against the Diodes drawing before using it. TPS22917 is SOT-23-6; same rule.

## 16. Geometry and the case

Right project, KiCad Y down, copies `notes/geometry.json` with residual 0:

- 38 classic switch centers and rotations
- `Edge.Cuts`, the 25 legacy segments minus the 4.5 mm × 1.27 mm TRRS notch at x 84.21–88.71 mm, which is filled so the LINK receptacle has board under its mouth, bounding box x 23.08098–205.9178 mm, y 30.48–189.35192 mm
- eight mounting holes, drill 6.3754 mm, non-plated, the `H99` coordinates in the JSON
- stabilizer S1 origin at SW0:11, (64.03848, 161.11728) mm, rotation 115°, footprint name `STAB_PCB940`, value `STAB200`
- stabilizer S2 origin at SW0:10, (81.30286, 153.06548) mm, rotation 295°
- copy the legacy stabilizer pad geometry out of the legacy footprint. Do not edit that file, and do not redraw the holes from memory

The legacy outline is not the acrylic outline. `notes/geometry.md` records a PCB edge vertex up to 14.165266 mm from the right plate outline. Do not stretch `Edge.Cuts` to the acrylic. The plate check is the switch cutouts, not the plate perimeter.

Left project: in-plane mirror, switches still on the front, so the centers land on the Standard Left plate. `notes/geometry.md`, Y-up millimetres, right plate already equal to the KiCad right-hand board by `x_plate = x_kicad` and `y_plate = -y_kicad + 209.9818`:

- `x_left = -x_right + 234.807846`
- `y_left = y_right - 2.915703`

Mirror rotations with that same reflection. Do not flip the board over. A 180° rotation of the right-hand KiCad numbers also meets the left plate after the translation the notes give, (234.807846, 207.066097) mm in Y-down, but that is only because Y-down is already a flip. The physical left plate is the mirror. Use the mirror, then check residual 0 against `ErgoDox Acrylic Case/ErgoDOX Acrylic Case - Designed by Litster/Standard/Left/ErgoDOX Case Layer 3 Plate - Left.dxf` and the matching Right DXF. Both DXFs are millimetres (`$INSUNITS` 4).

HOST and LINK sit on the top edge, on the front, in the region the legacy USB mini and the 3.5 mm jack occupied: legacy J1 at (137.6426, 30.48) mm rotation 270°, legacy J2 at (86.3092, 30.48) mm rotation 270°. Exact USB-C origins are a layout choice inside that edge. They must not move a switch center, a mounting hole, a stabilizer, or `Edge.Cuts`. Silkscreen `RIGHT` on the right project and `LEFT` on the left, on the front.

## 17. Acceptance checks

All of these are required before the boards are called done. This document does not claim any of them have been run.

1. ERC: zero errors on both projects.
2. DRC: zero errors on both projects, including schematic parity.
3. Right-hand switch centers and rotations match `notes/geometry.json` with residual 0. Left-hand centers match the Standard Left plate with residual 0 under the section 16 mirror.
4. Mounting holes, stabilizer origins, and `Edge.Cuts` match the same sources.
5. Case DXF check against the Litster Standard Left and Standard Right layer-3 plates, not the wrist-rest plates.
6. No LCSC cell is filled with a number that was not on a page or in `notes/parts.md`. Blank cells stay blank.
7. GPIO map: no pin used twice. UART is not a matrix pin and not the LED pin. ADC pins are only the four sense nets.
8. HOST has Rd on both CC pins, 27 Ω at the RP2040, ESD, and a series diode from VBUS onto +5V. No Rp on HOST.
9. LINK silkscreen says `LINK` and `NOT A PC PORT`. TX and RX are crossed as in section 8. Source switch cannot turn on when the other side is a source, and cannot turn on when HOST VBUS is absent.
10. No CC or VBUS net touches a GPIO without a divider that stays inside 0 V to 3.3 V, including both HOST plugs in PCs.
11. USB D+/D− width and spacing are the JLCPCB calculator result for JLC04161H-7628 at 90 Ω, written down next to the fab note. They are not 0.8 mm / 0.15 mm.
12. LED chain order matches section 11, `chain-length` 38, brightness cap at or below the section 14 number.
13. One script generated both projects, and a diff of the non-mirror, non-strap, non-UART-swap nets is empty.

### Blockers the layout does not get to ignore

- 90 Ω geometry is the calculator row in section 13 (W1 0.290661 mm, gap 0.203200 mm). Er1 in that solve is the picture default 4.3; the stackup prepreg is 4.4 and the same widths report 89.5253 Ω.
- SK6812 VIH minimum 3.25 V at VDD = 5.0 V versus RP2040 VOH minimum 2.62 V at IOVDD = 3.3 V. No level shifter is fitted. Direct drive is not guaranteed.
- Hotswap LCSC C41430893 is not a Kailh manufacturer page, and KiCad 10.0.7 has no Kailh or CPG1511 footprint. The socket land pattern is unverified.
- Rp 36 kΩ and the 100 kΩ / 200 kΩ sense-divider resistors have no LCSC number.
- Source-side CC windows are from a Release 1.1 extract, not re-checked against Release 2.4.
- ZMK role cannot follow HOST VBUS. The product sentence "the half that sees VBUS is central" is met by flashing the central image into that half, not by a runtime detect.

## 18. Sources opened for this contract

- `notes/geometry.md`, `notes/geometry.json`, `notes/parts.md`, `notes/rp2040-checklist.md`, `notes/zmk.md`
- `ErgoDOX pcb/ErgoDOX.net` matrix nets
- RP2040 product brief, August 2022, <https://pip-assets.raspberrypi.com/categories/814-rp2040/documents/RP-008372-DS-1-rp2040-product-brief.pdf>
- ZMK development docs, split feature and split configuration, opened this pass
- JLCPCB calculator guide, last updated 2026-09-16, <https://jlcpcb.com/help/article/user-guide-to-the-jlcpcb-impedance-calculator>
- JLCPCB part page for C165948, opened this pass
- KiCad 10.0.7-full image: the footprints named in sections 6, 10, 11, and 15
- USB Type-C cable wiring and Rp/Rd tables, from the Release 1.0 and Release 1.1 extracts and the secondary pinout pages cited in sections 5 and 8. Release 2.4 was not re-opened this pass; `notes/parts.md` is the record for its Table 4-28.
