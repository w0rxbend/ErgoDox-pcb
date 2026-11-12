# ErgoDox RP2040

An ErgoDox split keyboard PCB rebuilt around an RP2040 in each half, with ZMK firmware, USB-C on every port and one RGB LED per key. It keeps the original ErgoDox switch positions, so it fits the Litster acrylic case.

**Status: in development. The boards are not finished and have never been fabricated. Do not order them yet.** See [PLAN.md](PLAN.md) for what is open.

Project page: <https://w0rxbend.github.io/ErgoDox-pcb/>

## What it is

| | Original ErgoDox (2016) | ErgoDox RP2040 |
| --- | --- | --- |
| Controller | Teensy 2.0 plus MCP23018 expander | One RP2040 per half |
| Firmware | QMK and others | ZMK, wired split |
| Computer port | Mini-USB | USB-C |
| Link between halves | TRRS, I2C | USB-C cable carrying UART |
| Master half | Fixed (the Teensy side) | Either half |
| Switches | Soldered | Hotswap sockets |
| Lighting | 3 indicator LEDs | One SK6812MINI-E per key |
| Board | One reversible 2-layer PCB | Separate left and right 4-layer PCBs |
| Keys | 38 per half | 38 per half |

### Either half can be the master

Both halves carry the same circuit. ZMK fixes the role at build time, so there are four firmware images: left or right, central or peripheral. Flash the central image into the half you plug into the computer and the peripheral image into the other half. To swap sides, reflash both halves over USB.

The link port is a USB-C receptacle, but it carries UART and 5 V, not USB. It is marked `LINK` and `NOT A PC PORT` on the board.

## Repository layout

| Path | Contents |
| --- | --- |
| `hw/ergodox-rp2040/DESIGN.md` | The design contract: circuit, pin map, parts, acceptance checks |
| `hw/ergodox-rp2040/left`, `right` | Generated KiCad 10 projects |
| `hw/ergodox-rp2040/tools` | Python scripts that generate the schematics and boards |
| `hw/ergodox-rp2040/firmware/zmk` | ZMK shield, as a Zephyr module |
| `hw/ergodox-rp2040/notes` | Geometry taken from the legacy board, part research, ZMK notes |
| `hw/ergodox-rp2040/third_party/MX_V2` | ai03 keyswitch footprint library |
| `docs` | Source of the project page |
| `ErgoDOX pcb` | The original 2016 KiCad board. Kept unchanged for reference |
| `ErgoDox Acrylic Case` | Litster acrylic case drawings. Kept unchanged |

## Rebuild the boards

The KiCad files are generated. Do not edit them by hand; change the scripts and run them again.

You need Docker and the `kicad/kicad:10.0.7-full` image. Routing also needs [Freerouting](https://github.com/freerouting/freerouting) 2.5.0 and Java 21 or later.

From the repository root:

```sh
hw/ergodox-rp2040/tools/build.sh /path/to/freerouting-2.5.0.jar
```

The script runs these steps for both halves:

1. `build_board.py` writes the schematics and places every part.
2. `route.py export` writes a Specctra file for the router.
3. Freerouting routes the board. This takes about 15 minutes per half.
4. `route.py import` reads the routes back.
5. `kicad-cli pcb drc` fills the zones and writes the reports to `hw/ergodox-rp2040/reports`.

Check the firmware pin map against the schematics with:

```sh
python3 hw/ergodox-rp2040/tools/check_firmware_pins.py
```

## Firmware

The ZMK shield is in `hw/ergodox-rp2040/firmware/zmk`. Add that directory to your ZMK build as an extra module and build these shields for the `rpi_pico` board:

- `ergodox_rp2040_left_central`
- `ergodox_rp2040_left_peripheral`
- `ergodox_rp2040_right_central`
- `ergodox_rp2040_right_peripheral`

The firmware has not been built or run on hardware yet. LED brightness is capped at 10% so both halves stay within 500 mA from one USB port.

## Known limits

- ZMK's wired split is new and has no runtime role switch. The role follows the flashed image.
- The RP2040 drives the LED data line at 3.3 V with no level shifter. This is outside the LED's guaranteed input level at 5 V.
- The USB-C openings have not been test fitted in the Litster case.
- Some resistor values have no verified JLCPCB part number yet. `DESIGN.md` lists them.

## Credits

Based on the open [ErgoDox](https://github.com/Ergodox-io/ErgoDox) PCB and the acrylic case designed by Litster. Keyswitch footprints are from ai03's MX_V2 library. Routing is done with Freerouting.
