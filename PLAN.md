# ErgoDox RP2040 — paused work

Paused on 2026-11-08. Nothing in `hw/ergodox-rp2040/` is ready to order. This file is the resume point. The workflow **ergodox-rp2040-pcb** was stopped after this snapshot was written. A later session should follow the prompt below and the files on disk, not a resumed workflow. `origin` is `git@github.com:w0rxbend/ErgoDox-pcb.git`. Upstream is `https://github.com/Ergodox-io/ErgoDox`.

## Current state

Legacy files were not modified:

- `ErgoDOX pcb/` — 2016 KiCad board. One flippable half, Teensy 2.0, MCP23018, mini-USB, TRRS, 38 keys, 3 in-switch LEDs.
- `ErgoDox Acrylic Case/` — Litster acrylic plates.

New work lives in `hw/ergodox-rp2040/`. The build contract is `hw/ergodox-rp2040/DESIGN.md`. Research notes are in `hw/ergodox-rp2040/notes/`.

| Item | State |
|---|---|
| Schematics, left and right | Written. ERC 0 errors, 0 warnings (`reports/left-erc.rpt`, `reports/right-erc.rpt`) |
| Switch centers vs Litster plates | 38 cutouts, residual 0.000 mm on the last layout run |
| PCB copper, right | `right/ergodox-rp2040-right.kicad_pcb` saved. 46 router-open nets. DRC 625 errors, 276 unconnected |
| PCB copper, left | `left/ergodox-rp2040-left.kicad_pcb` saved. 45 router-open nets. DRC 778 errors, 279 unconnected |
| Zone pours | Not in the board files. Zone fill dies with signal 11 (`exit -11`). Copper files were kept on purpose |
| ZMK shield | 15 files under `firmware/zmk/`. No `BUILD.md`. Pin check against the unfinished PCB was not completed |
| Fab zips, BOM, CPL, `ORDER.md`, `README.md` | Not created |

Right DRC error mix: clearance 104, hole clearance 72, shorts 78, hole-to-hole 2, solder-mask bridge 93.

Left DRC error mix: shorts 79, clearance 106, hole clearance 69, malformed courtyard 147, hole-to-hole 2, solder-mask bridge 96.

Open nets are listed in `reports/right-unrouted.json` and `reports/left-unrouted.json`. Both halves still miss the crystal (`XTAL`, `XIN`, `XOUT`), most of the QSPI flash, USB data into the RP2040, `HOST_VBUS`, `LINK_VBUS`, the LINK UART pair, `+1V1`, and several matrix rows and columns.

KiCad is `docker run --rm --user $(id -u):$(id -g) -v "$PWD":/work -w /work kicad/kicad:10.0.7-full`. `sudo` is not available. Docker works without it.

`tools/layout_pcb.py` saves placement, routes, then saves copper **before** creating zones. `fill_saved_board()` adds zones in a child process and only replaces the board if that child exits 0. The child still segfaults, so the saved boards have tracks and no pours.

`third_party/MX_V2/` is a nested git checkout of the keyswitch library. Do not commit that `.git` directory as part of this repo without deciding how the library is vendored.

## Decisions already locked

These are in `DESIGN.md`. Do not reopen them unless a cited ZMK or RP2040 document makes one impossible.

- One RP2040 per half. Either half can be the ZMK central. Role is compile-time: flash the central image into the half that is plugged into the computer, and the peripheral image into the other half.
- HOST USB-C is the RP2040 native USB device port (CC 5.1 kΩ, 27 Ω series, ESD, no back-power into the PC).
- LINK is a second USB-C receptacle, not TRRS and not USB protocol. ZMK full-duplex UART rides a normal USB 2.0 C-to-C cable. D+ and D− are straight through, so left TX is on D+ and RX on D−, and right is swapped.
- LINK power: central presents Rp and sources 5 V only when CC shows a sink. Peripheral presents Rd and only sinks. CC and VBUS sense pins must stay inside 0–3.3 V in every state, including both halves plugged into PCs.
- One addressable LED per key, 5 V, firmware brightness cap inside the USB current budget.
- Direct diode matrix. Kailh hotswap sockets assembled by the fab. MX switches are not in the assembly BOM.
- RP2040 circuit follows Raspberry Pi's minimal design (flash, 12 MHz crystal, decoupling, BOOTSEL, RUN). Official footprint, not a hand-drawn QFN.
- 4-layer, 1.6 mm, JLCPCB stackup and 90 Ω USB geometry as written in `DESIGN.md` section 13.
- Switch centers, outline, mounting holes, and stabilizers stay on the legacy coordinates so the Litster case fits.
- Do not invent LCSC numbers. Blank the cell when `notes/parts.md` did not verify the page.
- Do not upload or pay for a JLCPCB or PCBWay order.

## Prompt to continue

Paste this to the next session:

```text
Continue the paused ErgoDox RP2040 board in /home/worxbend/Projects/Github/ErgoDox. Read PLAN.md and hw/ergodox-rp2040/DESIGN.md first. The legacy ErgoDOX pcb/ and ErgoDox Acrylic Case/ trees are read-only. Do not commit, push, or place a fabrication order unless I ask.

The schematics exist and ERC is clean (0 errors, 0 warnings). Both KiCad 10 boards exist and are not manufacturable. Right has 46 router-open nets, 625 DRC errors, and 276 unconnected pads. Left has 45 router-open nets, 778 DRC errors, and 279 unconnected pads. Zone fill SIGSEGVs (exit -11); tools/layout_pcb.py keeps the copper file when that happens. Open nets include the crystal, QSPI flash, USB into the RP2040, HOST_VBUS, LINK_VBUS, the LINK UART pair, and part of the matrix. Reports are in hw/ergodox-rp2040/reports/.

Do not run another pass of the current maze router and treat it as finished. Fix placement and routing until the crystal, flash, USB pair, power, LINK UART, LED chain, and every matrix switch are connected, with zero shorts and zero clearance errors. Keep switch centers on the legacy coordinates (last plate residual was 0.000 mm). Fill the 4-layer zones without losing the board: if KiCad zone fill still signal-11s, fix the zone geometry in a child process and keep the copper file. Courtyard overlaps that are intentional (socket, diode, LED, crystal, decoupling) may stay as exclusions in the .kicad_dru files. Connectivity, shorts, and clearance are not waivable.

After DRC reports zero errors and zero unconnected items, recheck the ZMK shield in hw/ergodox-rp2040/firmware/zmk against the schematic with tools/check_firmware_pins.py. Role stays compile-time (central image on the half plugged into the PC). Then export Gerber, drill, BOM, and CPL for JLCPCB and PCBWay under hw/ergodox-rp2040/fab/, and write hw/ergodox-rp2040/ORDER.md plus a short README. ORDER.md must say the boards have not been fabricated. KiCad CLI is the local image kicad/kicad:10.0.7-full via docker, without sudo.

Stop when ERC is 0, DRC is 0, unconnected is 0, zones are filled, the case fit is rechecked, the firmware pin check passes, and the order guide lists the real zip paths. If any of those is still failing, say so at the top of ORDER.md under "Do not order yet".
```
