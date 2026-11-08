# Legacy ErgoDox geometry

Extracted from `ErgoDOX pcb/ErgoDOX.kicad_pcb` (KiCad pcb version 20160815, pcbnew (2016-12-22 revision d365dc5)-makepkg). The JSON coordinates are millimetres in that file: X to the right, Y downward. Footprint rotation is the `(at x y rot)` angle in degrees. A pad's board position is the module origin plus the KiCad 4.0.7 `RotatePoint` mapping `x' = x cos θ + y sin θ`, `y' = -x sin θ + y cos θ`.

Board thickness is **1.6002 mm** (`general.thickness`).

## Switches

**38 classic keys** on this half, references `SW*`. That is the Litster plate count. The PCB also places **42 MX footprints**: 34 `MX_FLIP_DIODE`, 4 `MX_FLIP_XX`, and 4 `MX_FLIP`.

The four `MX_FLIP` parts are `SX0:10`, `SX0:11`, `SX1:7`, and `SX1:8`. Each is 9.524–9.527 mm from a stabilized thumb switch (`SW0:10` with stabilizer `S2`, or `SW0:11` with `S1`), on opposite sides of that switch. The nearest Litster cutout is 9.524–9.527 mm away, so these four are not on the Standard plates. `SW_RST1` is a tactile reset and is not a key. Switch centers in the JSON are the footprint origins; those 38 origins are what land on the cutouts.

## Outline, holes, connectors

`Edge.Cuts` is a closed loop of 25 straight segments, width 0.381 mm. Bounding box x 23.08098–205.9178 mm, y 30.48–189.35192 mm, perimeter 620.424945 mm. Every `gr_line` stores angle 90. The endpoints chain, and `ErgoDOX-Edge.Cuts.gm1` is G01 only with Y negated, so the angle is not an arc sweep.

Eight mounting holes, reference `H99`, footprint `ErgoDOXmech`, non-plated drill 6.3754 mm. Non-plated holes in the file: 139 (2 connector, 3 ic_footprint, 8 mounting, 8 stabilizer, 118 switch).

Stabilizers `S1` and `S2` are `STAB_PCB940`, value `STAB200`. `S1` shares its origin with `SW0:11` (rotation 115 deg). `S2` shares its origin with `SW0:10` (rotation 295 deg).

USB is `J1`, footprint `USBMINImod`, schematic value `USB`, at (137.6426, 30.48) mm, rotation 270 deg. The 4-pin 3.5 mm jack is `J2`, footprint `4pin35mmAudio`, schematic value `3.5mm`, at (86.3092, 30.48) mm, rotation 270 deg. The file never says TRRS; a 4-pin 3.5 mm jack is that connector. Front silkscreen says RIGHT HAND; back silkscreen says LEFT HAND.

## Litster Standard plates

Both Layer 3 DXFs set `$INSUNITS` to 4, which AutoCAD defines as millimetres. The right file's `$ACADVER` is AC1021; the left file's is AC1014. Each plate has 38 switch cutouts (closed 20-vertex polylines, area about 206.54049–206.565013 mm²). Cutout center is the vertex mean.

Compared in Y-up millimetres (DXF native, KiCad Y negated the same way as the Edge.Cuts gerber), the legacy board **matches the right plate**, not a mirrored copy:

- `x_plate = x_kicad`
- `y_plate = -y_kicad + 209.9818`
- rotation 0, no reflection, maximum residual 0 mm

The left cutouts are the X-mirror of the right cutouts (`x_left = -x_right + 234.807846`, `y_left = y_right - 2.915703`, maximum residual 0 mm). Native KiCad Y-down numbers also meet the left plate after a 180° rotation and translation (234.807846, 207.066097) mm, residual 0 mm. That proper rotation exists only because Y-down is already a flip; in the DXF Y-up frame the left plate is the mirror.

The plate outlines are separate, larger polylines (left 34 vertices, right 50). Under the switch transform, a PCB edge vertex is up to 14.165266 mm from the right outline and 14.165266 mm from the left outline. A right-outline vertex is up to 19.7238 mm from the PCB edge. The acrylic outline is not the PCB `Edge.Cuts`. Each plate also has four closed 4-vertex polylines of area about 46.1 mm². Stabilizer holes are 0.761534–2.032407 mm from the nearest right-plate quad edge; 4 of 8 holes fall inside a quad. The left plate draws all 8 mounting holes as circles of radius 1.524 mm. The right plate draws only 2 circles of that radius, and both land on `H99` holes. Circles of radius 1.5 mm (7 per plate) do not land on the mounting holes.
