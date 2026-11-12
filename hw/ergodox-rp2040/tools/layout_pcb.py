#!/usr/bin/env python3
"""Shared pcbnew helpers for place.py: units, the left-hand mirror, footprint
loading, board primitives and the case-plate check."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parents[1]
GEO_PATH = ROOT / "notes" / "geometry.json"
TX = 234.807846
TY = 2.915703
Y_PLATE = 209.9818
CLEAR = 0.15  # same as the Default netclass in the .kicad_pro
TRACK = 0.20
VIA_D = 0.60
VIA_DRILL = 0.30
EDGE_COPPER = 0.30
HOLE_CLEAR = 0.20
FP_ROOT = Path("/usr/share/kicad/footprints")
MX_PRETTY = ROOT / "third_party" / "MX_V2" / "MX_Hotswap.pretty"


def iu(mm: float) -> int:
    return int(pcbnew.FromMM(float(mm)))


def mm(v) -> float:
    return float(pcbnew.ToMM(v))


def v2(x: float, y: float):
    return pcbnew.VECTOR2I(iu(x), iu(y))


def xform(x: float, y: float, side: str):
    if side == "left":
        return (-x + TX, y + TY)
    return (x, y)


def world(ox, oy, rot_deg, lx, ly):
    a = math.radians(rot_deg)
    c, s = math.cos(a), math.sin(a)
    return (ox + lx * c + ly * s, oy - lx * s + ly * c)


def load_geo():
    return json.loads(GEO_PATH.read_text(encoding="utf-8"))


def dxf_centers(path: Path):
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    i = 0
    centers = []
    n = len(lines)
    while i + 1 < n:
        code = lines[i].strip()
        val = lines[i + 1].strip()
        if code == "0" and val == "LWPOLYLINE":
            i += 2
            verts = []
            closed = False
            pending_x = None
            while i + 1 < n:
                c = lines[i].strip()
                v = lines[i + 1].strip()
                if c == "0":
                    break
                if c == "70":
                    try:
                        closed = bool(int(float(v)) & 1)
                    except ValueError:
                        pass
                elif c == "10":
                    pending_x = float(v)
                elif c == "20" and pending_x is not None:
                    verts.append((pending_x, float(v)))
                    pending_x = None
                i += 2
            if closed and len(verts) >= 12:
                cx = sum(p[0] for p in verts) / len(verts)
                cy = sum(p[1] for p in verts) / len(verts)
                # Switch cutouts are about 14 mm across. The plate outline is much larger.
                span = max(p[0] for p in verts) - min(p[0] for p in verts)
                if 8.0 < span < 20.0:
                    centers.append((cx, cy))
            continue
        i += 2
    return centers


def verify_plates(geo):
    right_dxf = (
        ROOT.parents[1]
        / "ErgoDox Acrylic Case"
        / "ErgoDOX Acrylic Case - Designed by Litster"
        / "Standard"
        / "Right"
        / "ErgoDOX Case Layer 3 Plate - Right.dxf"
    )
    left_dxf = (
        ROOT.parents[1]
        / "ErgoDox Acrylic Case"
        / "ErgoDOX Acrylic Case - Designed by Litster"
        / "Standard"
        / "Left"
        / "ErgoDOX Case Layer 3 Plate - Left.dxf"
    )
    switches = [s for s in geo["switches"] if s["reference"].startswith("SW")]
    right_c = dxf_centers(right_dxf)
    left_c = dxf_centers(left_dxf)
    print(f"plate cutouts right={len(right_c)} left={len(left_c)} switches={len(switches)}", flush=True)

    def nearest(pts, x, y):
        return min(math.hypot(x - px, y - py) for px, py in pts)

    right_err = 0.0
    left_err = 0.0
    for s in switches:
        x, y = s["x_mm"], s["y_mm"]
        pr = (x, -y + Y_PLATE)
        right_err = max(right_err, nearest(right_c, *pr))
        pl = (-x + TX, (-y + Y_PLATE) - TY)
        left_err = max(left_err, nearest(left_c, *pl))
    print(f"plate residual right={right_err:.6f} mm left={left_err:.6f} mm", flush=True)
    if right_err > 0.05 or left_err > 0.05:
        raise RuntimeError(f"plate residual right={right_err} left={left_err}")


def pretty_dir(nick: str) -> Path:
    if nick == "MX_Hotswap":
        return MX_PRETTY
    return FP_ROOT / f"{nick}.pretty"


def load_fp(fp_id: str):
    nick, name = fp_id.split(":")
    return pcbnew.FootprintLoad(str(pretty_dir(nick)), name)


def apply_design_rules(board):
    board.SetCopperLayerCount(4)
    ds = board.GetDesignSettings()
    ds.SetBoardThickness(iu(1.6))
    pairs = {
        "m_MinClearance": CLEAR,
        "m_TrackMinWidth": 0.15,
        "m_ViasMinSize": VIA_D,
        "m_ViasMinDrill": VIA_DRILL,
        "m_MinThroughDrill": 0.2,
        "m_HoleClearance": HOLE_CLEAR,
        "m_HoleToHoleMin": 0.25,
        "m_CopperEdgeClearance": EDGE_COPPER,
        "m_SilkClearance": 0.0,
        "m_TextMinWidth": 0.08,
        "m_MinHoleToHole": 0.25,
    }
    for name, val in pairs.items():
        if hasattr(ds, name):
            setattr(ds, name, iu(val))
    try:
        default = ds.m_NetSettings.GetDefaultNetclass()
        default.SetClearance(iu(CLEAR))
        default.SetTrackWidth(iu(TRACK))
        default.SetViaDiameter(iu(VIA_D))
        default.SetViaDrill(iu(VIA_DRILL))
        if hasattr(default, "SetDiffPairWidth"):
            default.SetDiffPairWidth(0)
            default.SetDiffPairGap(0)
    except Exception as exc:
        print("netclass setup", exc, flush=True)


def ensure_net(board, cache, name):
    if name in cache:
        return cache[name]
    existing = board.FindNet(name)
    if existing is not None and existing.GetNetCode() > 0 and existing.GetNetname() == name:
        cache[name] = existing
        return existing
    item = pcbnew.NETINFO_ITEM(board, name, board.GetNetCount() + 1)
    board.Add(item)
    cache[name] = item
    return item


def add_track(board, net, layer, a, b, width):
    if math.hypot(a[0] - b[0], a[1] - b[1]) < 0.02:
        return None
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(v2(*a))
    t.SetEnd(v2(*b))
    t.SetWidth(iu(width))
    t.SetLayer(layer)
    t.SetNet(net)
    board.Add(t)
    return t


def add_via(board, net, x, y):
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(v2(x, y))
    via.SetWidth(iu(VIA_D))
    via.SetDrill(iu(VIA_DRILL))
    via.SetNet(net)
    via.SetViaType(pcbnew.VIATYPE_THROUGH)
    board.Add(via)
    return via


def add_line(board, layer, a, b, width):
    sh = pcbnew.PCB_SHAPE(board)
    sh.SetShape(pcbnew.SHAPE_T_SEGMENT)
    sh.SetLayer(layer)
    sh.SetWidth(iu(width))
    sh.SetStart(v2(*a))
    sh.SetEnd(v2(*b))
    board.Add(sh)
    return sh


def make_npth_fp(board, ref, x, y, rot, holes):
    """holes: list of (local_x, local_y, drill) in the footprint frame before rotation."""
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference(ref)
    fp.SetValue("NPTH")
    # Specctra needs a name, and a distinct one per hole pattern, or the router loses the keepouts.
    fp.SetFPID(pcbnew.LIB_ID("", f"NPTH_{ref}"))
    for i, (lx, ly, drill) in enumerate(holes, start=1):
        pad = pcbnew.PAD(fp)
        pad.SetNumber("")
        pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        d = iu(drill)
        pad.SetSize(pcbnew.VECTOR2I(d, d))
        pad.SetDrillSize(pcbnew.VECTOR2I(d, d))
        pad.SetFPRelativePosition(v2(lx, ly))
        try:
            pad.SetLayerSet(pad.UnplatedHoleMask())
        except Exception:
            pad.SetLayerSet(pcbnew.LSET.AllCuMask())
        fp.Add(pad)
    fp.SetPosition(v2(x, y))
    fp.SetOrientation(pcbnew.EDA_ANGLE(rot, pcbnew.DEGREES_T))
    board.Add(fp)
    try:
        fp.Reference().SetVisible(False)
        fp.Value().SetVisible(False)
    except Exception:
        pass
    return fp


def add_text(board, text, x, y, layer=None, size=1.2):
    item = pcbnew.PCB_TEXT(board)
    item.SetText(text)
    item.SetLayer(layer or pcbnew.F_SilkS)
    item.SetPosition(v2(x, y))
    item.SetTextSize(v2(size, size))
    item.SetTextThickness(iu(max(0.12, size * 0.15)))
    try:
        item.SetMirrored(False)
    except Exception:
        pass
    board.Add(item)
    return item
