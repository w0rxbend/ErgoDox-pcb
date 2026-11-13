#!/usr/bin/env python3
"""Specctra hand-off for Freerouting. Run inside the KiCad image.

    route.py export <side> <file.dsn>
    route.py import <side> <file.ses>

Zones are filled afterwards by `kicad-cli pcb drc --refill-zones --save-board`.
"""

import math
import sys
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parents[1]
# The router gets a little extra clearance so its rounding never lands under the DRC limit.
ROUTER_EXTRA_MM = 0.03
MIN_TRACK = pcbnew.FromMM(0.10)


def led_cutout_keepout(board, led):
    """Router-only keepout over an LED cutout, so tracks stay 0.2 mm from its edge.

    The cutout is 3.4 x 3.0 mm. The router holds its own clearance from this box.
    Not saved to the board file.
    """
    half_x, half_y = pcbnew.FromMM(1.75), pcbnew.FromMM(1.55)
    centre = led.GetPosition()
    angle = led.GetOrientation().AsRadians()
    cos, sin = math.cos(angle), math.sin(angle)
    corners = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        x, y = sx * half_x, sy * half_y
        # KiCad turns counter-clockwise on a Y-down sheet.
        corners.append(pcbnew.VECTOR2I(int(centre.x + x * cos + y * sin), int(centre.y - x * sin + y * cos)))
    zone = board.AddArea(None, 0, pcbnew.F_Cu, corners[0], pcbnew.ZONE_BORDER_DISPLAY_STYLE_NO_HATCH)
    for point in corners[1:]:
        zone.AppendCorner(point, -1)
    zone.SetIsRuleArea(True)
    zone.SetLayerSet(pcbnew.LSET.AllCuMask())
    zone.SetDoNotAllowTracks(True)
    zone.SetDoNotAllowVias(True)
    zone.SetDoNotAllowPads(False)
    zone.SetDoNotAllowZoneFills(False)
    zone.SetDoNotAllowFootprints(False)


def main(action, side, other):
    pcb = ROOT / side / f"ergodox-rp2040-{side}.kicad_pcb"
    board = pcbnew.LoadBoard(str(pcb))
    if action == "export":
        for track in list(board.GetTracks()):
            if not track.IsLocked():
                board.Remove(track)
        for fp in board.GetFootprints():
            if fp.GetReference().startswith("DS"):
                led_cutout_keepout(board, fp)
        settings = board.GetDesignSettings().m_NetSettings
        classes = [settings.GetDefaultNetclass()] + list(settings.GetNetclasses().values())
        for netclass in classes:
            netclass.SetClearance(netclass.GetClearance() + pcbnew.FromMM(ROUTER_EXTRA_MM))
        if not pcbnew.ExportSpecctraDSN(board, other):
            raise SystemExit("DSN export failed")
    elif action == "import":
        if not pcbnew.ImportSpecctraSES(board, other):
            raise SystemExit("SES import failed")
        # The router may neck a stub below the board minimum of 0.10 mm.
        for track in board.GetTracks():
            if track.GetClass() == "PCB_TRACK" and track.GetWidth() < MIN_TRACK:
                track.SetWidth(MIN_TRACK)
        pcbnew.SaveBoard(str(pcb), board)
        print(f"{side}: {len(board.GetTracks())} tracks and vias", flush=True)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
