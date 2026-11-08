# DRC courtyard waivers

Each line is a KiCad custom rule in the matching project `.kicad_dru`:
`severity exclusion` on `courtyard_clearance`.
The exclusion covers courtyard overlap of parts stacked on purpose
(hotswap sockets at the legacy pitch, a per-key LED or diode on its switch,
the crystal against the RP2040, and decoupling beside the QFN).
Clearance, shorts, unconnected items, and track angles are not waived.

| Side | A | B | Reason |
| --- | --- | --- | --- |
| left | SW0_7 | D5 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW0_8 | D8 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW0_9 | D6 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW0_10 | DS8 | per-key LED sits in the matrix pitch and overlaps a socket courtyard |
| left | SW0_10 | D11 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW0_11 | DS6 | per-key LED sits in the matrix pitch and overlaps a socket courtyard |
| left | SW0_11 | DS15 | per-key LED sits in the matrix pitch and overlaps a socket courtyard |
| left | SW0_11 | D9 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW0_12 | D7 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW1_9 | D17 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW1_10 | D16 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW1_11 | D15 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW1_12 | D14 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW1_13 | D13 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW2_7 | D20 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW2_8 | D21 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW2_9 | D22 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW2_10 | D23 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW2_11 | D24 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW2_12 | D25 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW2_13 | D26 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW3_8 | D32 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW3_9 | D31 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW3_10 | D30 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW3_11 | D29 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW3_12 | D28 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW3_13 | D27 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW4_7 | D33 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW4_8 | D34 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW4_9 | D35 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW4_10 | D36 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW4_11 | D37 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW4_12 | D38 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW4_13 | D39 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW5_7 | D46 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW5_8 | D45 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW5_9 | D44 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW5_10 | D43 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW5_11 | D42 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW5_12 | D41 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SW5_13 | D40 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SX0_10 | D12 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SX0_11 | D10 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SX1_7 | DS14 | per-key LED sits in the matrix pitch and overlaps a socket courtyard |
| left | SX1_7 | D19 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | SX1_8 | DS14 | per-key LED sits in the matrix pitch and overlaps a socket courtyard |
| left | SX1_8 | D18 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | DS6 | D9 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | DS8 | D11 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | DS14 | D18 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| left | J1 | D3 | placed against its anchor with an intentional courtyard overlap |
| left | J2 | D4 | placed against its anchor with an intentional courtyard overlap |
| left | J2 | U5 | placed against its anchor with an intentional courtyard overlap |
| left | U1 | U3 | placed against its anchor with an intentional courtyard overlap |
| left | U1 | U4 | placed against its anchor with an intentional courtyard overlap |
| left | U2 | C16 | flash decoupling beside U2 |
| left | Y1 | C12 | decoupling capacitor beside the crystal |
| left | Y1 | C7 | decoupling capacitor beside the crystal |
| left | Y1 | C1 | crystal load network beside Y1 |
| left | Y1 | C2 | crystal load network beside Y1 |
| left | Y1 | R2 | crystal load network beside Y1 |
| right | SW0_7 | D5 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW0_8 | D8 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW0_9 | D6 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW0_10 | DS8 | per-key LED sits in the matrix pitch and overlaps a socket courtyard |
| right | SW0_10 | D11 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW0_11 | DS6 | per-key LED sits in the matrix pitch and overlaps a socket courtyard |
| right | SW0_11 | DS15 | per-key LED sits in the matrix pitch and overlaps a socket courtyard |
| right | SW0_11 | D9 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW0_12 | D7 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW1_9 | D17 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW1_10 | D16 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW1_11 | D15 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW1_12 | D14 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW1_13 | D13 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW2_7 | D20 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW2_8 | D21 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW2_9 | D22 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW2_10 | D23 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW2_11 | D24 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW2_12 | D25 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW2_13 | D26 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW3_8 | D32 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW3_9 | D31 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW3_10 | D30 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW3_11 | D29 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW3_12 | D28 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW3_13 | D27 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW4_7 | D33 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW4_8 | D34 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW4_9 | D35 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW4_10 | D36 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW4_11 | D37 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW4_12 | D38 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW4_13 | D39 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW5_7 | D46 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW5_8 | D45 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW5_9 | D44 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW5_10 | D43 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW5_11 | D42 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW5_12 | D41 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SW5_13 | D40 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SX0_10 | D12 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SX0_11 | D10 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SX1_7 | DS14 | per-key LED sits in the matrix pitch and overlaps a socket courtyard |
| right | SX1_7 | D19 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | SX1_8 | DS14 | per-key LED sits in the matrix pitch and overlaps a socket courtyard |
| right | SX1_8 | D18 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | DS6 | D9 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | DS8 | D11 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | DS14 | D18 | matrix diode sits beside its socket and may overlap a key or LED courtyard |
| right | J1 | D3 | placed against its anchor with an intentional courtyard overlap |
| right | J2 | D4 | placed against its anchor with an intentional courtyard overlap |
| right | J2 | U5 | placed against its anchor with an intentional courtyard overlap |
| right | U1 | U3 | placed against its anchor with an intentional courtyard overlap |
| right | U1 | U4 | placed against its anchor with an intentional courtyard overlap |
| right | U2 | C16 | flash decoupling beside U2 |
| right | Y1 | C12 | decoupling capacitor beside the crystal |
| right | Y1 | C7 | decoupling capacitor beside the crystal |
| right | Y1 | C1 | crystal load network beside Y1 |
| right | Y1 | C2 | crystal load network beside Y1 |
| right | Y1 | R2 | crystal load network beside Y1 |
