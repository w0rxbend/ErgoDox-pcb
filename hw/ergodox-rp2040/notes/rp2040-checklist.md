# RP2040 minimal-design checklist

Checked against the current Raspberry Pi document, not a blog summary.

| Item | Value |
| --- | --- |
| Document | Hardware design with RP2040, chapter 2, Minimal design example |
| URL | https://datasheets.raspberrypi.com/rp2040/hardware-design-with-rp2040.pdf |
| Release | 2 |
| Build date | 20/08/2026 |
| Build version | 0444806419d7 |
| Schematic in that PDF | RPI-RP2040-MINIMAL_R3, schematic revision S1, dated 2026-07-03 |
| Layout files linked by the chapter | https://datasheets.raspberrypi.com/rp2040/Minimal-KiCAD.zip (`RPI-RP2040-MINIMAL_R3-S1`, title block 2026-07-03) |
| Pin-function names | RP2040 product brief, https://datasheets.raspberrypi.com/rp2040/rp2040-product-brief.pdf, plus the RP2040 symbol in the R3 schematic |

Pin numbers and nets below were read from that R3 schematic symbol and the matching PCB (`footprint` `RPI_COMPILED:rpi_rp2040_vias`). Where the chapter prose names a capacitor and a pin, that sentence is quoted as the requirement. Where only the layout shows which 100 nF part sits nearest a pin, it is marked as layout placement, not as a sentence in the chapter.

LCSC numbers were not on these pages. Every LCSC cell is blank. Do not fill one without opening the LCSC part page.

The example board in chapter 2 is a **two-layer, nominally 1 mm** board. Its USB track geometry is not a JLCPCB 4-layer result. See the JLCPCB section before copying any width.

## Power pins

RP2040 needs 3.3 V for I/O and 1.1 V for the core. The on-chip LDO makes 1.1 V from 3.3 V. Connect `VREG_VOUT` to the `DVDD` pins. The minimal example feeds 3.3 V from an external LDO.

Product-brief nominals, opened with the brief: `IOVDD` 1.8 V to 3.3 V, `USB_VDD` 3.3 V, `ADC_AVDD` 3.3 V, `VREG_VIN` 1.8 V to 3.3 V, `VREG_VOUT` 1.1 V (100 mA max), `DVDD` 1.1 V. This example runs `IOVDD` at 3.3 V. The crystal section says the Abracon part and its series resistor are tuned for that voltage.

| Pin | Name | R3 net | Required connection |
| --- | --- | --- | --- |
| 1 | IOVDD | +3V3 | 3.3 V |
| 10 | IOVDD | +3V3 | 3.3 V |
| 22 | IOVDD | +3V3 | 3.3 V |
| 33 | IOVDD | +3V3 | 3.3 V |
| 42 | IOVDD | +3V3 | 3.3 V |
| 49 | IOVDD | +3V3 | 3.3 V. Shares one 100 nF with pin 48 |
| 43 | ADC_AVDD | +3V3 | 3.3 V in this design |
| 44 | VREG_IN | +3V3 | 3.3 V into the on-chip regulator |
| 48 | USB_VDD | +3V3 | 3.3 V USB PHY. Shares one 100 nF with pin 49 |
| 23 | DVDD | +1V1 | Tie to `VREG_VOUT` |
| 50 | DVDD | +1V1 | Tie to `VREG_VOUT` |
| 45 | VREG_VOUT | +1V1 | On-chip 1.1 V output. Tie to both `DVDD` pins |
| 19 | TESTEN | GND | Tied to GND on the R3 schematic. The product brief only calls it the factory test pin; it does not, in the pages opened here, say to ground it. The minimal design does |
| 57 | GND | GND | Exposed ground pad. See ground pad section |

External supply in the example, not RP2040 pins:

- Micro-USB `J1` (`10103594-0001LF`) pin 1 `VBUS` is the 5 V input. Shell and GND pins go to GND. The ID pin is unconnected on the R3 PCB (`unconnected-(J1-ID-Pad4)`).
- `U1` `NCP1117ST33T3G`, fixed 3.3 V, up to 1 A. PCB pads: 1 GND, 2 and 4 `+3V3`, 3 `VBUS`.
- Chapter text: the NCP1117 datasheet requires 10 µF on the input and 10 µF on the output. Those are `C1` (VBUS to GND) and `C4` (+3V3 to GND). Both are 10 µF, 10%, 16 V, X5R, M2012 on the schematic.
- `C17` is a further 10 µF, 10%, 16 V, X5R, M2012 from +3V3 to GND on the same schematic. The chapter prose does not assign it to an RP2040 pin. On the R3 layout its centroid is far from the chip (about 22 mm from pin 1).

## Decoupling, and which pin it sits on

Chapter rule: place decoupling close to the power pins. Ordinarily one 100 nF capacitor per power pin. Two exceptions are written down.

Written in chapter 2:

- Pins 48 and 49 share a single capacitor, `C9` (Figure 5 and Figure 6). Those pins are `USB_VDD` and `IOVDD`.
- Place 1 µF close to `VREG_IN` and 1 µF close to `VREG_OUT`. Schematic notes: `C8` close to pin 45, `C10` close to pin 44. Both are 0402 / M1005 ceramic. The chapter says small ceramic parts are expected to meet the regulator ESR limit, and points to the RP2040 datasheet for the regulator. This checklist does not copy ESR numbers from that datasheet; they were not opened in this pass.

Values printed on Figure 5 and Figure 11:

| Ref | Value | Dielectric / voltage / case | Net | Pin assignment |
| --- | --- | --- | --- | --- |
| C8 | 1 µF, 10% | X5R, 16 V, M1005 | +1V1 to GND | Chapter: close to pin 45 `VREG_VOUT`. R3 centroid is nearest pin 45 |
| C10 | 1 µF, 10% | X5R, 16 V, M1005 | +3V3 to GND | Chapter: close to pin 44 `VREG_IN`. R3 centroid is slightly nearer pin 43 than pin 44; follow the schematic note, not the centroid |
| C9 | 100 nF, 10% | X7R, 25 V, M1005 | +3V3 to GND | Chapter: the one capacitor shared by pins 48 and 49 |
| C6 | 100 nF, 10% | X7R, 25 V, M1005 | +1V1 to GND | Figure 5 groups it with the 1.1 V rail. R3 centroid nearest pin 50 `DVDD`. The chapter does not name C6's pin |
| C7 | 100 nF, 10% | X7R, 25 V, M1005 | +1V1 to GND | Same 1.1 V group. R3 centroid nearest pin 23 `DVDD`. Not named in the prose |
| C11 | 100 nF, 10% | X7R, 25 V, M1005 | +3V3 to GND | R3 centroid nearest pin 1 `IOVDD` |
| C13 | 100 nF, 10% | X7R, 25 V, M1005 | +3V3 to GND | R3 centroid nearest pin 10 `IOVDD` |
| C14 | 100 nF, 10% | X7R, 25 V, M1005 | +3V3 to GND | R3 centroid nearest pin 22 `IOVDD` |
| C12 | 100 nF, 10% | X7R, 25 V, M1005 | +3V3 to GND | R3 centroid nearest pin 33 `IOVDD` |
| C15 | 100 nF, 10% | X7R, 25 V, M1005 | +3V3 to GND | R3 centroid nearest pin 42 `IOVDD` |
| C16 | 100 nF, 10% | X7R, 25 V, M1005 | +3V3 to GND | Also nearest pin 42, then pin 43 `ADC_AVDD`, then pin 44. A unique pin for C16 is not in the chapter |
| C5 | 100 nF, 10% | X7R, 25 V, M1005 | +3V3 to GND | Flash `VCC` decoupler in Figure 7, not an RP2040 pin capacitor |

`ADC_AVDD` (pin 43) is a 3.3 V power pin, so the "100 nF per power pin" rule covers it, but no sentence and no unambiguous centroid assigns one reference designator to it alone. Do not invent that assignment.

## Crystal

| Pin | Name | Connection |
| --- | --- | --- |
| 20 | XIN | Crystal, load capacitor `C2` to GND |
| 21 | XOUT | Series resistor `R5`, then the other crystal terminal and `C3` to GND |

- Preferred source is a 12 MHz crystal between `XIN` and `XOUT`, not the internal oscillator. A CMOS clock of `IOVDD` amplitude into `XIN` is the other option the chapter allows. USB needs a real frequency reference.
- Chapter recommendation for an original RP2040 design: Abracon `ABM8-272-T3` (`X1`), the same part as on Pico. Source it from Abracon or an authorised reseller. Contact `applications@raspberrypi.com` if that is not possible.
- Table 1 in the chapter, for that part: 12.000 MHz fundamental-AT, load capacitance 10 pF, ESR maximum 50 Ω, frequency tolerance and stability ±30 ppm, shunt capacitance maximum 3.0 pF, drive level typical 10 µW and maximum 200 µW, operating −40 °C to +85 °C.
- Load capacitors `C2` and `C3` are 15 pF, C0G, 50 V, 5%, M1005, one on each side of the crystal to GND. The chapter's arithmetic: the two 15 pF parts in series are 7.5 pF, plus an assumed 3 pF of pin and track capacitance, total 10.5 pF against a 10 pF target. Keep the crystal tracks short so that parasitic term stays small.
- `R5` is 1 kΩ, 1%, 63 mW, M1005, in series so the crystal is not over-driven at 3.3 V `IOVDD`. On the R3 PCB, `R5` sits between pin 21 `XOUT` and crystal pad 3. Crystal pads 2 and 4 are GND. Crystal pad 1 is the `XIN` net.
- Any other crystal, any other series resistor, or any `IOVDD` other than 3.3 V has to be retested across temperature. The chapter says a lower `IOVDD` reduces drive and may need a smaller series resistor.

## Flash

External QSPI flash is required. The example is Winbond `W25Q128JVSIQ` (`U2`), 128 Mbit / 16 MB, which the chapter calls the largest size RP2040 supports. A smaller 25-series part is allowed if it supports the boot commands in section 2.6. QSPI tracks must be short and direct.

| RP2040 pin | Name | Flash pin on the R3 PCB |
| --- | --- | --- |
| 56 | QSPI_SS | 1, chip select |
| 52 | QSPI_SCLK | 6, CLK |
| 53 | QSPI_SD0 | 5, DI / IO0 |
| 55 | QSPI_SD1 | 2, DO / IO1 |
| 54 | QSPI_SD2 | 3, WP / IO2 |
| 51 | QSPI_SD3 | 7, HOLD / IO3 |
| — | +3V3 | 8, VCC, with `C5` 100 nF to GND |
| — | GND | 4, GND |

`QSPI_SS` has two resistors, both placed close to the flash:

- `R2`, 10 kΩ, 1%, 63 mW, M1005, from `QSPI_SS` to 3.3 V. Marked DNF. The R3 schematic has `dnp yes` on `R2`. The chapter says this Winbond part did not need the external pull-up, because `QSPI_SS` already defaults to a pull-up, but the pull-up covers the brief period at power-up when that pin is not guaranteed. Fit 10 kΩ if a different flash needs the chip select held at its own 3.3 V during power-up.
- `R1`, 1 kΩ, 1%, 63 mW, M1005, from `QSPI_SS` to header `J2` pin 1 (`USB_BOOT`). `J2` pin 2 is GND. The 1 kΩ lets RP2040 overdrive the pull-down once boot continues. Do not short `QSPI_SS` to GND with no resistor.

## USB and the 27 ohm resistors

| Pin | Name | Connection |
| --- | --- | --- |
| 47 | USB_DP | `R3` 27 Ω, then connector D+ (`J1` pin 3, net `/USB_D+`) |
| 46 | USB_DM | `R4` 27 Ω, then connector D− (`J1` pin 2, net `/USB_D-`) |

- `R3` and `R4` are 27 Ω, 1%, 63 mW, M1005. The chapter says to place them close to the chip so the USB impedance spec is met.
- No extra pull-up or pull-down on `USB_DP` / `USB_DM`. Speed and host/device resistors are inside the I/O.
- Target differential characteristic impedance is 90 Ω.
- Chapter geometry, **only for this 1 mm two-layer example**: 0.8 mm wide tracks on `USB_DP` and `USB_DM`, 0.15 mm gap, over a solid uninterrupted ground for the whole length. The example puts almost all of the bottom copper on ground. The chapter says a board thicker than 1 mm changes the impedance, and that re-engineering the pair may be physically impossible. It does not give a width for 1.6 mm or for four layers. Do not reuse 0.8 mm / 0.15 mm on the JLCPCB stackup below.

## RUN

| Pin | Name | Connection |
| --- | --- | --- |
| 26 | RUN | Header `J4` only. No resistor on this net in the R3 schematic |

The chapter uses a toggle of `RUN` as the example of resetting after `QSPI_SS` has been pulled down, so the chip restarts in BOOTSEL instead of running flash. The product brief says: reset when driven low, run when driven high. The minimal schematic does not fit an external pull-up.

## BOOTSEL

There is no BOOTSEL button on this RP2040 minimal design. BOOTSEL is the `QSPI_SS` strap:

1. Jumper `J2` (`USB_BOOT`) so `R1` pulls `QSPI_SS` to GND.
2. Reset by toggling `RUN`.
3. RP2040 enters BOOTSEL and presents USB mass storage.

`R1` must stay in series. See the flash section.

## Ground pad and via guidance

- Pin 57 is the single external GND pad. The product brief describes GND as the connection bonded to a number of internal ground pads on the die. It does not give a via count.
- Chapter 2 prose does not state a via count, drill, or grid. It does require a solid ground under the USB pair, many grounds on the I/O headers (outer row of `J3` and `J4`), and a low-impedance ground return. The four-layer discussion in chapter 3 is about the Pico VGA board, not a via pattern under RP2040.
- The footprint actually shipped in the chapter's R3-S1 layout is `rpi_rp2040_vias`. Measured from that PCB file, not from a written rule:
  - one SMD pad, 3.2 mm × 3.2 mm, net GND
  - nine thru-hole vias, also pad 57, net GND
  - each via: copper size 0.6 mm × 0.6 mm, drill 0.25 mm
  - via centres at the nine combinations of x, y in {−1.1 mm, 0, +1.1 mm} relative to the package centre
- Treat that grid as what the published minimal layout does. It is not a sentence in chapter 2. If a datasheet package drawing gives a different via rule, open that page before treating the footprint as the requirement. This pass did not open the RP2040 datasheet package section.

## JLCPCB 4-layer stackup

Opened https://jlcpcb.com/impedance (controlled-impedance stackup page). The checked controls on that page were **1.6 mm**, **outer copper 1 oz**, **inner copper 0.5 oz**.

Also opened https://jlcpcb.com/help/article/multi-layer-pcb-standard-laminated-structures (last updated 2026-09-09). That article does not print the layer table; it says to use the JLCPCB Impedance Calculator with the selected laminate. It does give finished copper as 1.6 mil for 1 oz outer and 0.6 mil for 0.5 oz inner, and it repeats the soldermask figures below. The impedance page lists outer copper as 0.035 mm. Both numbers are recorded as printed. They were not converted or averaged.

Dielectric constants on the impedance page:

| Material | Dielectric constant |
| --- | --- |
| Prepreg 7628 | 4.4 |
| Prepreg 3313 | 4.1 |
| Prepreg 1080 | 3.91 |
| Prepreg 2116 | 4.16 |
| Core | 4.6 |

Soldermask on that page: coating above substrate C1 = 1.2 mil, coating above trace C2 = 0.6 mil, coating between traces C3 = 1.2 mil, coating dielectric constant = 3.8.

For the checked 1.6 mm / 1 oz / 0.5 oz selection, **1) No requirement** and **2) JLC04161H-7628** are the same thicknesses:

| Layer | Material | Thickness |
| --- | --- | --- |
| Top | Copper | 0.035 mm |
| Prepreg | 7628 × 1 | 0.21040 mm |
| Inner L2 | Copper | 0.0152 mm |
| Core | Core | 1.065 mm |
| Inner L3 | Copper | 0.0152 mm |
| Note on the core row | — | 1.1 mm H/HOZ with copper |
| Prepreg | 7628 × 1 | 0.21040 mm |
| Bottom | Copper | 0.035 mm |

The named stackup to call out on the order is **JLC04161H-7628**. Other named 4-layer builds (3313, 1080, 2116, and the A/B/C variants) are on the same page and have different dielectric thicknesses. Do not mix those thicknesses into this stackup.

### 90 ohm USB pair

The impedance page does not give a trace width or a spacing for a 90 Ω USB pair. The 0.15 mm and 0.2 mm figures on that page are core thicknesses or the minimum-via capability (minimum via 0.2 mm), not a USB pair. The word "90" does not appear in the stackup body as an impedance result.

The layout must use the **JLCPCB Impedance Calculator**, https://jlcpcb.com/pcb-impedance-calculator, with JLC04161H-7628 (or the identical "No requirement" row if that is what is ordered), 1.6 mm, 1 oz outer, 0.5 oz inner, differential 90 Ω. No width is filled in here.

The chapter's 0.8 mm / 0.15 mm pair is for the 1 mm two-layer example only. It is not the JLCPCB number.

## Parts named by the chapter

| Ref | What the document calls it | LCSC |
| --- | --- | --- |
| U3 | RP2040 | |
| U1 | NCP1117ST33T3G | |
| U2 | W25Q128JVSIQ | |
| X1 | Abracon ABM8-272-T3, 12 MHz | |
| J1 | 10103594-0001LF Micro-USB | |
| R3, R4 | 27 Ω | |
| R1, R5 | 1 kΩ | |
| R2 | 10 kΩ, do not fit for this Winbond flash | |
| C2, C3 | 15 pF C0G | |
| C8, C10 | 1 µF | |
| C5, C6, C7, C9, C11–C16 | 100 nF | |
| C1, C4, C17 | 10 µF | |
