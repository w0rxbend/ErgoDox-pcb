# Third-party notices

## MX_V2

- Upstream: https://github.com/ai03-2725/MX_V2
- Commit: `0b379eebbeb66c7fd6e82e400b47958ad695614e`
- Commit date: 2024-08-15 12:42:02 +0900
- License: MIT, in `MX_V2/LICENSE` (Copyright (c) 2017 ai03)
- Vendored path: `third_party/MX_V2`
- Used footprint: `MX_Hotswap:MX-Hotswap-1U` (pads `1` and `2`, plus non-plated mounting holes). This is the published Kailh MX hotswap socket land pattern. It was not redrawn for this repo.

`Switch_Misc.pretty` in the same commit only has 2-pin indicator LED footprints (`MX-LED` and Alps variants). Those are not an SK6812. The addressable LED footprint assigned on the schematic is the KiCad 10.0.7 library footprint `LED_SMD:LED_SK6812_PLCC4_5.0x5.0mm_P3.2mm`, also not drawn for this repo. The OPSCO SK6812 body on the JLCPCB page recorded in `notes/parts.md` is 5.4 × 5 mm. Pad match of the 5.0 × 5.0 mm KiCad footprint to that body was not re-measured.

The MX_V2 readme at this commit says a fresh hotswap layout should flip the socket footprint so the socket and pads are on the bottom. That is a layout step, not a schematic connection.
