# JLCPCB parts for one RP2040 ErgoDox half

Checked 2026-11-08. Every LCSC number below was read from a JLCPCB part page opened in this pass (`https://jlcpcb.com/partdetail/<code>`). Stock is the page payload field `overseasStockCount`. `preMinPurchaseNum` is the other quantity field on that same payload. The price ladder on each of these pages starts at quantity 1. Schema.org availability on each page was `InStock`.

JLCPCB library field `componentLibraryType`:

- `base` is recorded here as **Basic**.
- `expand` is recorded here as **Extended**.

JLCPCB help, “How to build your own parts library in JLCPCB” (page last updated 2026-09-09): basic parts can be pre-ordered and that pre-order has a minimum, and the same page says they are normally already on the feeders so a pre-order is unnecessary. The same page says in-stock extended parts have no minimum order quantity. “PCB Assembly FAQs” (same date) says an extended part adds a $3 feeder-loading fee. Those help sentences and the `preMinPurchaseNum` column are both copied as printed. They are not averaged into one order quantity.

This list is one USB controller half. The legacy sheet `ErgoDOX pcb/ErgoDOX.sch` has 38 `SW*` key symbols, 4 `SX*` thumb symbols, and a separate `SW_RST1`. That is 42 key positions on one board. Per-key rows use 42. A full keyboard is two boards only if both halves are built from this PCB. This file does not double the quantities.

The internal RP2040 regulator is used. It makes 1.1 V from 3.3 V (`Hardware design with RP2040`, chapter 2). USB VBUS is 5 V, so the board still needs the external 3.3 V LDO.

No USB differential width is given. The hardware-design chapter’s 90 Ω target and its 0.8 mm / 0.15 mm pair are for that document’s 1 mm two-layer example. Pad geometry was not measured against any manufacturer drawing.

## Chosen parts

| Role | Manufacturer and MPN | LCSC | Library | Package on the page | Stock | preMin | Qty on one half |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MCU | Raspberry Pi RP2040 | C2040 | Extended | LQFN-56 (7x7) | 87479 | 9 | 1 |
| Flash | Winbond W25Q128JVSIQ | C97521 | Basic | SOIC-8-208mil | 69173 | 4 | 1 |
| Crystal | Abracon ABM8-272-T3 | C20625731 | Extended | SMD3225-4P | 9877 | 23 | 1 |
| 3.3 V LDO | Diodes AP2112K-3.3TRG1 | C51118 | Extended | SOT-25-5 | 13410 | 63 | 1 |
| USB-C receptacle | Korean Hroparts Elec TYPE-C-31-M-12 | C165948 | Extended | SMD, 16P, right-angle female | 318246 | 49 | 1 |
| USB ESD | ST USBLC6-2SC6 | C7519 | Extended | SOT-23-6L | 23773 | 73 | 1 |
| VBUS Schottky | MDD SS14 | C2480 | Basic | SMA (DO-214AC) | 1639265 | 470 | 1 |
| LED 5 V load switch | TI TPS22917DBVT | C2680344 | Extended | SOT-23-6 | 848 | 25 | 1 |
| MX hotswap socket | HanElectricity CPG151101S11-16 | C41430893 | Extended | SMD, 14.5x5.9 mm, 2 pins | 222399 | 246 | 42 |
| Addressable LED | OPSCO SK6812 | C5378720 | Extended | SMD-4P, 5.4x5 mm | 23205 | 126 | 42 |
| Matrix diode | 1N4148W, page brand “ST(Semtech)” | C81598 | Basic | SOD-123 | 3533458 | 931 | 42 |
| BOOTSEL and RESET | XKB TS-1187A-B-A-B | C318884 | Basic | SMD-4P, 5.1x5.1 mm, SPST | 871823 | 568 | 2 |
| Crystal load, 15 pF C0G 50 V ±5% | FH 0402CG150J500NT | C1548 | Basic | 0402 | 1204691 | 5640 | 2 |
| 1 µF X5R 25 V ±10% | Samsung CL05A105KA5NQNC | C52923 | Basic | 0402 | 11533218 | 2051 | 4 |
| 100 nF X7R 16 V ±10% | Samsung CL05B104KO5NNNC | C1525 | Basic | 0402 | 34236907 | 4512 | see decoupling |
| 1 kΩ 1% 50 V | Uni-Royal 0402WGF1001TCE | C11702 | Basic | 0402 | 33742422 | 9023 | 2 |
| 5.1 kΩ 1% 50 V | Uni-Royal 0402WGF5101TCE | C25905 | Basic | 0402 | 4522521 | 6016 | 2 |
| 10 kΩ 1% 50 V, DNF | Uni-Royal 0402WGF1002TCE | C25744 | Basic | 0402 | 22757540 | 5013 | 0 fitted |
| 27 Ω 1% 50 V | Uni-Royal 0402WGF270JTCE | C25100 | Extended | 0402 | 707747 | 10000 | 2 |

`assemblyMode` on these pages is `smtWeld`. The SK6812 rendered page also says Assembly Type “SMT Assembly”, PCBA Type “Standard Only”, Assembly Difficulty “High”, MSL 5.

## Power path

VBUS goes through SS14 into the board 5 V rail. The JLCPCB page lists SS14 as 40 V, 1 A, forward voltage 550 mV at 1 A. That 5 V rail feeds AP2112K-3.3TRG1. The 5 V LED rail is switched by TPS22917DBVT.

AP2112-3.3 table in Diodes DS39724 Rev. 2-2: output 3.3 V, 600 mA minimum, dropout 250 mV typical and 400 mV maximum at 600 mA, enable high 1.5 V minimum. SOT25 pin table: pin 1 VIN, pin 2 GND, pin 3 EN, pin 5 VOUT. Tie EN to VIN. The datasheet uses 1.0 µF ceramic on the input and on the output, and Note 4 prefers X5R or X7R when that 1.0 µF ceramic is used. Two of C52923 do that. The NCP1117 10 µF values in the RP2040 minimal example belong to the NCP1117, not to this LDO.

TPS22917 (the DBV part without the L suffix) is active high. SLVSDW8 text: VIN 1 V to 5.5 V, continuous current 2 A, RON 80 mΩ typical at 5 V, ON high-level 1 V minimum to 5.5 V. SOT-23-6 top view: pin 1 VIN, pin 2 GND, pin 3 ON, pin 4 CT, pin 5 QOD, pin 6 VOUT. Do not leave ON floating. Leave CT open for the fastest slew named in the datasheet, or add a capacitor from CT to VIN later from a value in that datasheet. Leave QOD open to disable the discharge path. A 3.3 V GPIO meets the 1 V ON threshold. Typical curves in the datasheet use a 1 µF load; that capacitor is not added here as a separate required line.

## RP2040, flash, buttons

Use the on-chip 1.1 V LDO. Connect VREG_OUT to both DVDD pins. The hardware-design chapter places 1 µF close to VREG_IN and 1 µF close to VREG_OUT. Those are the other two C52923 parts.

Decoupling: the same chapter says ordinarily one 100 nF per power pin, with USB_VDD and the adjacent IOVDD (pins 48 and 49) sharing one capacitor. Use C1525 for each of those positions. The exact reference-designator count is the minimal-design example; it was not re-counted from the PDF figures in this pass. See `notes/rp2040-checklist.md`.

Flash is the Winbond part named on the minimal schematic, 128 Mbit (16 MB), SOIC-8 208 mil, page range 2.7 V to 3.6 V. KiCad 10.0.7 has `Package_SO:SOIC-8_5.3x6.2mm_P1.27mm`, whose description says “208 mils width”. Pads were not measured against the Winbond drawing.

QSPI_SS for this Winbond part: the chapter marks the external 10 kΩ pull-up DNF, because the RP2040 pin already comes up with a pull-up after the brief power-on window. C25744 is on the list only as that unfitted resistor. BOOTSEL is the chapter’s 1 kΩ from QSPI_SS to a switch to GND, then a reset. One C11702 is that series resistor. The other C11702 is the crystal damper.

RUN is RP2040 pin 26, type Digital In (FT), power domain IOVDD. The pin table’s reset state is Pull-Up. The datasheet text says the chip is held in reset while RUN is low and runs when RUN is high, and that an unused RUN must be tied high. The ohm value of that reset-state pull-up was not in the pin row. The 50 kΩ to 80 kΩ RPU row is in the digital-IO characteristics table, not in the RUN pin row, so it is not copied onto RUN. RESET is TS-1187A-B-A-B from RUN to GND. BOOTSEL is the other switch, on the far side of the 1 kΩ.

KiCad 10.0.7 has `Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A`. Its description points at `http://www.helloxkb.com/public/images/pdf/TS-1187A-X-X-X.pdf`. The JLCPCB page for C318884 lists actuator 1.5 mm, 1.6 N, 100,000 cycles, 12 V, 50 mA, SPST, vertical, without bracket. Pads were not compared.

The only RP2040 footprint file found in `kicad/kicad:10.0.7-full` is the demo `RP2040-QFN-56.kicad_mod` under tiny_tapeout. It is not a checked production land pattern.

## Crystal load capacitors

Abracon drawing 456603, revision IR, date of issue 16 Nov 2023, the PDF attached to C20625731. Electrical table, typical column unless noted:

- Center frequency 12.000 MHz, fundamental-AT.
- Load capacitance CL 10 pF.
- Shunt capacitance C0 3.0 pF maximum. This is not the PCB stray term.
- ESR 50 Ω maximum.
- Drive level 10 µW typical, 200 µW maximum.
- Tolerance and stability ±30 ppm, operating −40 °C to +85 °C.
- Package named on the drawing: 3.2 × 2.5 × 0.8 mm, 4 pins.

That Abracon PDF has no load-capacitor formula. The formula used below is the one in `Hardware design with RP2040` for this same crystal:

- Two equal capacitors, one on each side of the crystal to ground, appear in series: `(C2*C3)/(C2+C3) = C/2`.
- Stray capacitance of the tracks and the RP2040 XIN/XOUT pins is in parallel with that series pair.
- The chapter assumes that stray term is 3 pF. This note uses that same assumption. It is not a measurement of this layout.
- Chapter arithmetic with 15 pF parts: series combination 7.5 pF, plus 3 pF, total 10.5 pF, against the 10 pF target.

Ideal equal value for exactly 10 pF with a 3 pF stray term is `2*(10−3) = 14` pF. The fitted parts are the basic 15 pF C0G capacitors C1548, which is the value the chapter uses and calls close enough. Keep the crystal tracks short so the 3 pF assumption stays valid.

The chapter also fits 1 kΩ in series with the crystal at 3.3 V IOVDD for a crystal whose ESR maximum is 50 Ω. That is the second C11702, from XOUT toward the crystal. Any other crystal, series resistor, or IOVDD requires the retest the chapter describes.

KiCad 10.0.7 has `Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm`. Its description cites a different crystal drawing. Pads were not compared with the Abracon drawing.

## USB-C

TYPE-C-31-M-12 is the 16-contact right-angle receptacle on C165948. The page lists 20 V and 5 A. KiCad 10.0.7 footprint `Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12` describes a USB 2.0 and PD receptacle and links `http://www.krhro.com/uploads/soft/180320/1-1P320120243.pdf`. Pads were not copied from that file into this note.

USB Type-C Cable and Connector Specification Release 2.4, October 2024, Table 4-28, Sink CC termination:

- ±10% resistor to GND, nominal 5.1 kΩ, can detect power capability, maximum voltage on the pin 2.04 V.
- ±20% resistor to GND, nominal 5.1 kΩ, cannot detect power capability.

Use two separate C25905 resistors, one from CC1 to GND and one from CC2 to GND. 1% is inside the ±10% row. Do not join CC1 and CC2 onto one resistor.

USB_DP and USB_DM each get 27 Ω in series, placed close to the RP2040, which is what the hardware-design chapter specifies (1%, in that chapter). C25100 is extended. A second 27 Ω 0402 page, Yageo RC0402JR-0727RL C137890, is also extended (±5%, stock 26584 on that payload). No basic 27 Ω 0402 page was opened. C25100 is the one fitted because it is ±1%.

USBLC6-2SC6 page: 2 channels, reverse stand-off 5.25 V, junction capacitance 3.5 pF, SOT-23-6L. KiCad has `Package_TO_SOT_SMD:SOT-23-6` and `SOT-23-5`. Pads were not checked.

## Addressable LED

Selected LED: OPSCO SK6812, C5378720, extended, Standard Only, assembly difficulty High, MSL 5. Supply on the JLCPCB page and in the attached datasheet is 3.7 V to 5.5 V, so the LED rail stays on the switched 5 V, not on 3.3 V.

The PDF LCSC serves for product code C5378720 is titled SK6812-012, file number SK6812-012, revision B/1, OPSCO, sending date 2025-08-11. Section 9, IC electrical parameters at TA = 25 °C, with the test-condition column on the threshold row reading `+VDD=5.0V`:

- VIH minimum = `0.65*VDD`.
- At that stated 5.0 V test point, VIH minimum = 0.65 × 5.0 = **3.25 V**.
- VIL maximum = `0.3*VDD`.
- Output drive current 10 / 12 / 14.5 mA (min / typ / max) at VDD = 5.0 V and VDS = 1.0 V.
- Static current 0.6 mA typical at VDD = 4.5 V with the outputs off.
- Working voltage range in the same table: 3.7 V to 5.5 V, typical 5.0 V.

3.25 V is not above 3.3 V, so no level shifter is added.

At the top of the datasheet range, 0.65 × 5.5 V = 3.575 V, which is above 3.3 V. The decision uses the 5.0 V test condition printed on the VIH row.

RP2040 datasheet Table 625, digital IO at IOVDD = 3.3 V: output high VOH minimum is 2.62 V. That minimum is below the LED’s 3.25 V VIH minimum, so a direct GPIO connection is not guaranteed by those two limits. A shifter was still left off the BOM because the LED threshold at the datasheet’s 5.0 V test point is not above 3.3 V.

Per color, the typical drive column is 12 mA. Forty-two keys at that typical current on all three colors are 42 × 3 × 12 mA = 1.512 A, plus 42 × 0.6 mA typical static current. That sum fits under the 2 A switch rating and is above the 500 mA USB default. Firmware has to limit the LED pattern. The ±10% row of Table 4-28 is what lets the sink read the source’s advertised current; this note does not pick a current above default.

Parts that were opened and not selected:

- Worldsemi WS2812B-V5/W, C2874885, extended. Payload stock 4, `preMinPurchaseNum` 94. Too few pieces for 42 keys.
- Worldsemi WS2812B-V6, C52917433, extended, Standard Only, difficulty High, MSL 5. Payload stock 104502. The datasheet URL on that page returned HTTP 403, so its VIH was not read and the part is not selected.
- OPSCO SK6812-B, C5380881. Its LCSC PDF (SK6812-B-012) lists VIH minimum `0.7*VDD` at `+VDD=5.0V`, which is 3.5 V and is above 3.3 V. Not selected, so no shifter was verified.

## Hotswap socket and matrix diode

C41430893 is in stock and marked for SMT assembly. The manufacturer field on the page is HanElectricity. The MPN is CPG151101S11-16. The page lists 12 V, 2 pins, 3000 gf, 5000 cycles, package SMD 14.5 × 5.9 mm, category “Mechanical Keyboard Shaft”. A Kailh-manufacturer listing was not opened in this pass, so none is recorded. KiCad 10.0.7-full has no footprint filename matching Hotswap, Kailh, or CPG1511 under `/usr/share/kicad/footprints`.

1N4148W C81598 is basic, SOD-123, 75 V, 150 mA, reverse recovery 4 ns, forward 1 V at 50 mA. KiCad has `Diode_SMD:D_SOD-123` and `Diode_SMD:D_SMA`. One diode per key position.

## Sources opened for the numbers above

- JLCPCB part pages for every LCSC cell in the table, plus C137890, C2874885, C52917433, and C5380881.
- JLCPCB help: PCB Assembly FAQs, and How to build your own parts library.
- Raspberry Pi, Hardware design with RP2040, local text extract of the PDF.
- Raspberry Pi RP2040 datasheet, pin 26 and Table 625.
- Abracon ABM8-272-T3 drawing 456603.
- Diodes AP2112 DS39724 Rev. 2-2.
- TI TPS22917, including the pin table and the ON VIH row.
- OPSCO SK6812-012 Rev. B/1, the PDF LCSC attaches to C5378720, and the SK6812-B-012 PDF for the part that was rejected.
- USB Type-C Cable and Connector Specification Release 2.4, Table 4-28, via the Infineon community copy of that specification.
- KiCad 10.0.7-full image, footprint filenames listed above.
- Legacy schematic `ErgoDOX pcb/ErgoDOX.sch`, reference-designator count only.
