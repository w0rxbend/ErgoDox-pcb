#!/usr/bin/env python3
"""Place and route both ErgoDox RP2040 boards.

Placement is computed in the legacy right-hand frame. The left board is the
in-plane mirror from notes/geometry.md: x' = -x + 234.807846, y' = y + 2.915703,
local X negated, rotation negated. Switches stay on the front.

USB D+/D- use DESIGN.md section 13: width 0.290661 mm, edge gap 0.203200 mm.
"""

from __future__ import annotations

import array
import json
import math
import heapq
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parents[1]
GEO_PATH = ROOT / "notes" / "geometry.json"
REPORTS = ROOT / "reports"

TX = 234.807846
TY = 2.915703
Y_PLATE = 209.9818

USB_W = 0.290661
USB_GAP = 0.203200
USB_CC = USB_W + USB_GAP

CLEAR = 0.20          # DRC / netclass clearance
TRACK = 0.20
TRACK_HALF = TRACK / 2.0
# Raster routing keeps a margin so a 0.05 mm cell cannot sneak inside 0.20.
ROUTE_CLEAR = 0.26
VIA_D = 0.60
VIA_DRILL = 0.30
EDGE_COPPER = 0.30
HOLE_CLEAR = 0.20

RES = 0.05
GRID = 0.50

FP_ROOT = Path("/usr/share/kicad/footprints")
MX_PRETTY = ROOT / "third_party" / "MX_V2" / "MX_Hotswap.pretty"

POWER_PLANES = {"GND", "+5V", "+3V3", "LED_5V"}
IGNORE_TARGET = POWER_PLANES | {"+1V1"}

# Controller band on the right-hand board, between the USB edge and the key field.
BAND_Y0 = 38.4
BAND_Y1 = 58.2
BAND_X0 = 66.0
BAND_X1 = 204.0

# L3 pours. Gap between them so the zone outlines do not touch.
RECT_5V = (60.0, 30.8, 210.0, 53.5)
RECT_LED = (20.0, 55.5, 215.0, 196.0)

# Right-hand frame corridor for the 90 ohm pair between D1 and R10/R11.
# place_one refuses pads here so the coupled run stays clear. The flash
# courtyard already covers the middle; this also blocks the D1-to-U2 gap
# and parts that are allowed to overlap U2.
USB_KEEPS = (
    {"wx": 156.15, "wy": 41.40, "rot": 0.0, "sx": 3.30, "sy": 3.00, "npth": False, "round": False},
    {"wx": 160.65, "wy": 41.40, "rot": 0.0, "sx": 6.50, "sy": 1.50, "npth": False, "round": False},
)


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


def outline_points(geo):
    segs = geo["edge_cuts"]["segments"]
    pts = [tuple(segs[0]["start_mm"])]
    for seg in segs:
        pts.append(tuple(seg["end_mm"]))
    if pts[0] == pts[-1]:
        pts.pop()
    return pts


def point_in_poly(x, y, poly):
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-30) + xi):
            inside = not inside
        j = i
    return inside


def dist_to_edges(x, y, poly):
    best = 1e9
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        best = min(best, dist_point_seg(x, y, ax, ay, bx, by))
    return best


def dist_point_seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


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


# --- footprints -----------------------------------------------------------

_COURT = {}
_PAD_LOCAL = {}


def pretty_dir(nick: str) -> Path:
    if nick == "MX_Hotswap":
        return MX_PRETTY
    return FP_ROOT / f"{nick}.pretty"


def load_fp(fp_id: str):
    nick, name = fp_id.split(":")
    return pcbnew.FootprintLoad(str(pretty_dir(nick)), name)


def cache_fp(fp_id: str):
    if fp_id in _COURT:
        return
    fp = load_fp(fp_id)
    polys = fp.GetCourtyard(pcbnew.F_CrtYd)
    if polys and polys.OutlineCount():
        bb = polys.BBox()
        _COURT[fp_id] = (mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom()))
    else:
        _COURT[fp_id] = (-1.0, -1.0, 1.0, 1.0)
    pads = []
    for pad in fp.Pads():
        p = pad.GetFPRelativePosition()
        attr = int(pad.GetAttribute())
        layers = pad.GetLayerSet()
        front = bool(layers.Contains(pcbnew.F_Cu))
        back = bool(layers.Contains(pcbnew.B_Cu))
        pads.append(
            {
                "num": pad.GetNumber(),
                "x": mm(p.x),
                "y": mm(p.y),
                "sx": mm(pad.GetSizeX()),
                "sy": mm(pad.GetSizeY()),
                "drill": mm(pad.GetDrillSizeX()),
                "npth": attr == int(pcbnew.PAD_ATTRIB_NPTH),
                "smd": attr == int(pcbnew.PAD_ATTRIB_SMD),
                "round": int(pad.GetShape()) == int(pcbnew.PAD_SHAPE_CIRCLE),
                "copper": front or back,
                "front": front,
                "back": back,
            }
        )
    _PAD_LOCAL[fp_id] = pads


def court_corners(fp_id, x, y, rot):
    cache_fp(fp_id)
    x0, y0, x1, y1 = _COURT[fp_id]
    pts = []
    for lx, ly in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        pts.append(world(x, y, rot, lx, ly))
    return pts


def aabb(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def aabb_overlap(a, b, gap=0.0):
    return not (a[2] + gap < b[0] or b[2] + gap < a[0] or a[3] + gap < b[1] or b[3] + gap < a[1])


def court_polys_overlap(a_pts, b_pts, gap=0.05):
    """True when two courtyard rectangles are closer than gap. SAT, not the AABB."""

    def axes(pts):
        out = []
        for i in range(len(pts)):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % len(pts)]
            dx, dy = x2 - x1, y2 - y1
            length = math.hypot(dx, dy) or 1.0
            out.append((-dy / length, dx / length))
        return out

    def proj(pts, ax):
        vals = [p[0] * ax[0] + p[1] * ax[1] for p in pts]
        return min(vals), max(vals)

    for ax in axes(a_pts) + axes(b_pts):
        a0, a1 = proj(a_pts, ax)
        b0, b1 = proj(b_pts, ax)
        if a1 + gap <= b0 or b1 + gap <= a0:
            return False
    return True


def pad_world_list(fp_id, x, y, rot):
    cache_fp(fp_id)
    out = []
    for p in _PAD_LOCAL[fp_id]:
        wx, wy = world(x, y, rot, p["x"], p["y"])
        out.append({**p, "wx": wx, "wy": wy, "rot": rot})
    return out


# --- placement ------------------------------------------------------------

class Placed:
    def __init__(self, ref, fp_id, x, y, rot, allow=()):
        self.ref = ref
        self.fp_id = fp_id
        self.x = x
        self.y = y
        self.rot = rot
        self.allow = set(allow)
        self.court = aabb(court_corners(fp_id, x, y, rot))
        self.pads = pad_world_list(fp_id, x, y, rot)


def obb_clear(p, q, need):
    """True if copper of two pads is at least `need` mm apart (edge to edge)."""
    if p["npth"] or q["npth"]:
        return True
    # Circular pads.
    if p["round"] and q["round"]:
        r1 = max(p["sx"], p["sy"]) / 2
        r2 = max(q["sx"], q["sy"]) / 2
        return math.hypot(p["wx"] - q["wx"], p["wy"] - q["wy"]) >= r1 + r2 + need
    # Conservative: grow each AABB by need/2 and use rotated-rect SAT via sampling.
    return rect_gap(p, q) + 1e-6 >= need


def rect_gap(p, q):
    """Approximate edge gap between two rotated rectangles. Negative means overlap."""
    # Sample the boundary of p and measure distance into q's local box, and vice versa.
    gap = 1e9
    for src, dst in ((p, q), (q, p)):
        hw, hh = src["sx"] / 2, src["sy"] / 2
        for lx, ly in (
            (-hw, -hh), (0, -hh), (hw, -hh), (-hw, 0), (hw, 0), (-hw, hh), (0, hh), (hw, hh)
        ):
            wx, wy = world(src["wx"], src["wy"], src["rot"], lx, ly)
            # dst local
            a = math.radians(dst["rot"])
            c, s = math.cos(a), math.sin(a)
            dx, dy = wx - dst["wx"], wy - dst["wy"]
            # inverse of world(): lx = dx*c - dy*s? 
            # world: wx = ox + lx c + ly s ; wy = oy - lx s + ly c
            # dx = lx c + ly s ; dy = -lx s + ly c
            # lx = dx c - dy s ; ly = dx s + dy c
            llx = dx * c - dy * s
            lly = dx * s + dy * c
            dhw, dhh = dst["sx"] / 2, dst["sy"] / 2
            ox = abs(llx) - dhw
            oy = abs(lly) - dhh
            if ox <= 0 and oy <= 0:
                gap = min(gap, max(ox, oy))  # negative penetration
            else:
                ex = max(ox, 0.0)
                ey = max(oy, 0.0)
                gap = min(gap, math.hypot(ex, ey))
    return gap


def hole_ok(pad, holes, need):
    if pad["npth"]:
        return True
    r = math.hypot(pad["sx"], pad["sy"]) / 2 + need
    for hx, hy, hr in holes:
        # tighter test: rect distance to circle
        a = math.radians(pad["rot"])
        c, s = math.cos(a), math.sin(a)
        dx, dy = hx - pad["wx"], hy - pad["wy"]
        llx = dx * c - dy * s
        lly = dx * s + dy * c
        hw, hh = pad["sx"] / 2, pad["sy"] / 2
        cx = min(max(llx, -hw), hw)
        cy = min(max(lly, -hh), hh)
        if math.hypot(llx - cx, lly - cy) < hr + need:
            return False
        if r < 0:
            return False
    return True


def collect_holes(placed, mounting, stabs):
    holes = []
    for h in mounting:
        holes.append((h["x_mm"], h["y_mm"], h["drill_diameter_mm"] / 2))
    for s in stabs:
        for hole in s["holes"]:
            holes.append((hole["x_mm"], hole["y_mm"], hole["drill_diameter_mm"] / 2))
    for pl in placed:
        for p in pl.pads:
            if p["drill"] > 0:
                holes.append((p["wx"], p["wy"], p["drill"] / 2))
    return holes


_LAST_FIT = {"why": ""}


def fits(fp_id, x, y, rot, placed, holes, poly, allow_refs, copper_need=0.2):
    if not point_in_poly(x, y, poly):
        _LAST_FIT["why"] = "center"
        return False
    if dist_to_edges(x, y, poly) < 1.2:
        # still allow if every pad is inside the copper margin
        pass
    corners = court_corners(fp_id, x, y, rot)
    box = aabb(corners)
    for pl in placed:
        if pl.ref in allow_refs:
            continue
        if not aabb_overlap(box, pl.court, gap=0.0):
            continue
        other = court_corners(pl.fp_id, pl.x, pl.y, pl.rot)
        if court_polys_overlap(corners, other, gap=0.05):
            _LAST_FIT["why"] = f"court:{pl.ref}"
            return False
    pads = pad_world_list(fp_id, x, y, rot)
    for p in pads:
        if p["npth"] or not p.get("copper", True):
            continue
        # pad corners inside outline and clear of the edge
        hw, hh = p["sx"] / 2, p["sy"] / 2
        for lx, ly in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)):
            wx, wy = world(p["wx"], p["wy"], rot, lx, ly)
            if not point_in_poly(wx, wy, poly):
                _LAST_FIT["why"] = "pad-out"
                return False
            if dist_to_edges(wx, wy, poly) < EDGE_COPPER + 0.05:
                _LAST_FIT["why"] = "edge"
                return False
        if not hole_ok({**p, "rot": rot}, holes, HOLE_CLEAR + 0.02):
            _LAST_FIT["why"] = "hole"
            return False
        for pl in placed:
            if pl.ref in allow_refs:
                continue
            for q in pl.pads:
                if q["npth"] or q["drill"] and q["smd"] is False and q["sx"] <= q["drill"] + 0.01:
                    continue
                if not obb_clear(p, q, copper_need):
                    _LAST_FIT["why"] = f"cu:{pl.ref}.{q.get('num','')}"
                    return False
    _LAST_FIT["why"] = ""
    return True


def spiral(cx, cy, limit=500):
    yield cx, cy
    step = 0.9
    n = 0
    for ring in range(1, 46):
        rad = ring * step
        count = max(10, int(2 * math.pi * rad / step))
        for i in range(count):
            a = 2 * math.pi * i / count
            yield cx + rad * math.cos(a), cy + rad * math.sin(a)
            n += 1
            if n >= limit:
                return


def courtyard_pairs(placed, by_ref):
    """Overlapping courtyards. Only intentional stacks get a waiver reason."""
    decouple = {f"C{n}" for n in (3, 4, 7, 8, 9, 10, 11, 12, 13, 14, 15)}
    crystal = {"C1", "C2", "R2", "Y1"}

    def is_key(ref):
        return ref.startswith(("SW", "SX")) and ref not in ("SW_RST", "SW_BOOT")

    def reason(a, b):
        ra, rb = a.ref, b.ref
        if is_key(ra) and is_key(rb):
            return "legacy key pitch; hotswap courtyards overlap so the Litster plate still fits"
        if (ra.startswith("DS") and is_key(rb)) or (rb.startswith("DS") and is_key(ra)):
            return "per-key LED sits in the matrix pitch and overlaps a socket courtyard"
        diode = ra.startswith("D") and ra[1:].isdigit() and int(ra[1:]) >= 5
        diode = diode or (rb.startswith("D") and rb[1:].isdigit() and int(rb[1:]) >= 5)
        if diode and (is_key(ra) or is_key(rb) or ra.startswith("DS") or rb.startswith("DS")):
            return "matrix diode sits beside its socket and may overlap a key or LED courtyard"
        for left, right in ((a, b), (b, a)):
            part = by_ref.get(left.ref)
            if not part:
                continue
            legacy = (part.get("fields") or {}).get("Legacy", "")
            swref = legacy.replace(":", "_")
            stacked = left.ref.startswith("DS") or (
                left.ref.startswith("D") and left.ref[1:].isdigit() and int(left.ref[1:]) >= 5
            )
            if stacked and right.ref == swref:
                return f"{left.ref} is the per-key LED or matrix diode on {right.ref}"
        if ra in decouple and rb in decouple:
            return "decoupling cluster beside the RP2040"
        if (ra in decouple and rb == "U1") or (rb in decouple and ra == "U1"):
            return "decoupling capacitor beside its RP2040 power pin"
        if ra in crystal and rb in crystal:
            return "crystal load network beside Y1"
        if (ra in crystal and rb == "U1") or (rb in crystal and ra == "U1"):
            return "12 MHz crystal sits against the RP2040 XIN/XOUT edge"
        if (ra in decouple and rb in crystal) or (rb in decouple and ra in crystal):
            return "decoupling capacitor beside the crystal"
        if frozenset((ra, rb)) == frozenset(("C16", "U2")):
            return "flash decoupling beside U2"
        if rb in a.allow or ra in b.allow:
            return "placed against its anchor with an intentional courtyard overlap"
        return None

    pairs = []
    for i, a in enumerate(placed):
        ca = court_corners(a.fp_id, a.x, a.y, a.rot)
        for b in placed[i + 1 :]:
            if not aabb_overlap(a.court, b.court, gap=0.0):
                continue
            cb = court_corners(b.fp_id, b.x, b.y, b.rot)
            if not court_polys_overlap(ca, cb, gap=0.0):
                continue
            why = reason(a, b)
            if why is None:
                print(f"UNEXPECTED courtyard overlap {a.ref} {b.ref}", flush=True)
            pairs.append({"a": a.ref, "b": b.ref, "reason": why})
    return pairs


def compute_placement(sheet, geo):
    by_ref = {p["ref"]: p for p in sheet.parts}
    switches = {s["reference"]: s for s in geo["switches"]}
    poly = outline_points(geo)
    placed: list[Placed] = []
    pos = {}

    def add(ref, fp_id, x, y, rot, allow=()):
        pl = Placed(ref, fp_id, x, y, rot, allow)
        placed.append(pl)
        pos[ref] = (x, y, rot)
        return pl

    # Switches at legacy centers.
    for part in sheet.parts:
        legacy = part["fields"].get("Legacy")
        if not legacy or not part["ref"].startswith(("SW", "SX")):
            continue
        if part["ref"] in ("SW_RST", "SW_BOOT"):
            continue
        sw = switches[legacy]
        add(part["ref"], part["footprint"], sw["x_mm"], sw["y_mm"], sw["rotation_deg"])

    holes = collect_holes(placed, geo["mounting_holes"], geo["stabilizers"])

    # LEDs. Local +Y is opposite the hotswap socket (socket courtyard is -Y).
    # Courtyards may overlap neighboring sockets; copper clearance still applies.
    led_offsets = []
    for ly in (6.4, 5.2, 7.6, 4.0, 8.8, 2.8, 10.0, -6.4, -8.0, 0.8, -4.0):
        for lx in (0.0, 2.2, -2.2, 4.4, -4.4, 6.6, -6.6, 8.8, -8.8):
            led_offsets.append((lx, ly))
    key_refs = {pl.ref for pl in placed if pl.ref.startswith(("SW", "SX"))}
    for part in sheet.parts:
        if not part["ref"].startswith("DS"):
            continue
        legacy = part["fields"]["Legacy"]
        sw = switches[legacy]
        swref = legacy.replace(":", "_")
        chosen = None
        for extra in (0, 90, 180):
            for lx, ly in led_offsets:
                x, y = world(sw["x_mm"], sw["y_mm"], sw["rotation_deg"], lx, ly)
                rot = sw["rotation_deg"] + extra
                if fits(part["footprint"], x, y, rot, placed, holes, poly, key_refs, copper_need=0.2):
                    chosen = (x, y, rot)
                    break
            if chosen:
                break
        if not chosen:
            raise RuntimeError(f"no LED site for {part['ref']} ({legacy})")
        add(part["ref"], part["footprint"], *chosen, allow=tuple(key_refs))

    holes = collect_holes(placed, geo["mounting_holes"], geo["stabilizers"])

    # Diodes just outside the socket, on the pad-2 side, nudged until they fit.
    for part in sheet.parts:
        if not part["ref"].startswith("D") or not part["ref"][1:].isdigit():
            continue
        if int(part["ref"][1:]) < 5:
            continue
        legacy = part["fields"]["Legacy"]
        sw = switches[legacy]
        swref = legacy.replace(":", "_")
        # Pad 2 is the switch node. Search a local grid, nearest to that pad first,
        # including the inboard side when the pad faces the board edge.
        px, py = -5.842, -5.080
        chosen = None
        allow_d = set(key_refs)
        allow_d.update(pl.ref for pl in placed if pl.ref.startswith("DS"))
        cands = []
        for ix in range(-6, 7):
            for iy in range(-6, 7):
                lx, ly = ix * 1.7, iy * 1.7
                cands.append((abs(lx - px) + abs(ly - py), lx, ly))
        cands.sort()
        for _score, lx, ly in cands:
            x, y = world(sw["x_mm"], sw["y_mm"], sw["rotation_deg"], lx, ly)
            for spin in (0, 90):
                rot = sw["rotation_deg"] + spin
                if fits(part["footprint"], x, y, rot, placed, holes, poly, allow_d, copper_need=0.2):
                    chosen = (x, y, rot)
                    break
            if chosen:
                break
        if not chosen:
            print(f"diode fail {part['ref']} {legacy} last={_LAST_FIT['why']}", flush=True)
            raise RuntimeError(f"no diode site for {part['ref']} ({legacy})")
        add(part["ref"], part["footprint"], *chosen, allow=tuple(allow_d))

    # Anchors: USB-C, MCU, flash, crystal.
    anchors = {
        # Mouth toward the board edge (-Y). Y is set so the signal-pad copper
        # stays 0.30 mm inside the notch.
        "J1": ("Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", 137.6553, 36.30, 0),
        "J2": ("Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", 86.4616, 37.70, 0),
        "U1": ("Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm_ThermalVias", 171.2, 46.8, 0),
        "U2": ("Package_SO:SOIC-8_5.3x5.3mm_P1.27mm", 160.2, 40.4, 90),
        "Y1": ("Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm", 171.0, 54.5, 0),
    }
    holes = collect_holes(placed, geo["mounting_holes"], geo["stabilizers"])
    for ref, (fp, x, y, rot) in anchors.items():
        part = by_ref[ref]
        if part["footprint"] != fp:
            fp = part["footprint"]
        allow_anchor = {"U1"} if ref == "Y1" else set()
        if not fits(fp, x, y, rot, placed, holes, poly, allow_anchor, copper_need=0.2):
            print(f"anchor {ref} at {(x, y, rot)} rejected, searching", flush=True)
            found = False
            rotations = (rot,) if ref in ("J1", "J2", "U1") else (rot, rot + 90, rot + 180, rot + 270)
            for sx, sy in spiral(x, y, limit=240):
                for rtry in rotations:
                    if fits(fp, sx, sy, rtry, placed, holes, poly, allow_anchor, copper_need=0.2):
                        x, y, rot = sx, sy, rtry
                        found = True
                        break
                if found:
                    break
            if not found:
                raise RuntimeError(f"anchor {ref} does not fit")
        add(ref, fp, x, y, rot, allow=tuple(allow_anchor))
        holes = collect_holes(placed, geo["mounting_holes"], geo["stabilizers"])

    # Decoupling beside the named RP2040 pins. Courtyard may overlap U1 on purpose.
    pin_caps = {
        "C10": "1",
        "C11": "10",
        "C12": "22",
        "C7": "23",
        "C13": "33",
        "C14": "42",
        "C15": "43",
        "C3": "44",
        "C4": "45",
        "C9": "48",
        "C8": "50",
    }
    u1 = pos["U1"]
    for ref, num in pin_caps.items():
        pin = next(p for p in _PAD_LOCAL[by_ref["U1"]["footprint"]] if p["num"] == num)
        # outward from package center, dominant axis
        if abs(pin["x"]) >= abs(pin["y"]):
            ox, oy = (1.0 if pin["x"] > 0 else -1.0), 0.0
            rot0 = 0.0
        else:
            ox, oy = 0.0, (1.0 if pin["y"] > 0 else -1.0)
            rot0 = 90.0
        fp = by_ref[ref]["footprint"]
        found = False
        for dist in (1.85, 2.25, 2.7, 3.2):
            for lat in (0.0, 1.1, -1.1, 1.8, -1.8, 2.6, -2.6):
                lx = pin["x"] + ox * dist + (-oy) * lat
                ly = pin["y"] + oy * dist + ox * lat
                x, y = world(u1[0], u1[1], u1[2], lx, ly)
                rot = u1[2] + rot0
                if fits(fp, x, y, rot, placed, holes, poly, {"U1", "Y1", "U2"}, copper_need=0.2):
                    add(ref, fp, x, y, rot, allow=("U1",))
                    found = True
                    break
            if found:
                break
        if not found:
            raise RuntimeError(f"no site for decoupling {ref}")
        holes = collect_holes(placed, geo["mounting_holes"], geo["stabilizers"])

    # HOST series resistors and the ESD device, inboard of U1, aimed at J1.
    # LINK series resistors and ESD sit inboard of J2. Generic search is the fallback.
    u1x, u1y, u1rot = pos["U1"]
    if abs(u1rot) % 360 < 1:
        fixed = [
            ("R10", u1x - 6.4, u1y - 6.4, 0),
            ("R11", u1x - 6.4, u1y - 4.4, 0),
            ("D1", u1x - 18.5, u1y - 5.4, 0),
        ]
        jx, jy = pos["J2"][0], pos["J2"][1]
        fixed += [
            ("R12", jx - 6.0, jy + 9.0, 0),
            ("R13", jx - 2.5, jy + 9.0, 0),
            ("D2", jx + 4.5, jy + 9.0, 0),
        ]
        for ref, fx, fy, rot in fixed:
            part = by_ref.get(ref)
            if part is None or ref in pos:
                continue
            if fits(part["footprint"], fx, fy, rot, placed, holes, poly, set(), copper_need=0.2):
                add(ref, part["footprint"], fx, fy, rot)
                holes = collect_holes(placed, geo["mounting_holes"], geo["stabilizers"])
            else:
                print(f"fixed site rejected for {ref}", flush=True)

    # Crystal load parts beside Y1, USB series resistors beside the USB pins.
    near_anchor = {
        "C1": "Y1",
        "C2": "Y1",
        "R2": "Y1",
        "C16": "U2",
        "R10": "U1",
        "R11": "U1",
        "D1": "J1",
        "D3": "J1",
        "R4": "J1",
        "R5": "J1",
        "D2": "J2",
        "D4": "J2",
        "R12": "J2",
        "R13": "J2",
        "U3": "U1",
        "U4": "U1",
        "U5": "J2",
        "C5": "U3",
        "C6": "U3",
    }

    def target_for(part):
        pts = []
        prefer = near_anchor.get(part["ref"])
        if prefer and prefer in pos:
            pts.append(pos[prefer][:2])
        for _num, (kind, net) in part["assign"].items():
            if kind == "nc" or not net or net in IGNORE_TARGET:
                continue
            for pl in placed:
                for p in pl.pads:
                    # net is not known yet on Placed; use ref proximity only
                    pass
        if prefer and prefer in pos:
            return pos[prefer][0], pos[prefer][1]
        return 120.0, 46.0

    remaining = []
    for part in sheet.parts:
        if part["ref"] in pos:
            continue
        if not part["footprint"]:
            raise RuntimeError(f"{part['ref']} has no footprint")
        remaining.append(part)

    # Place parts whose preferred anchor exists, then the rest, each time
    # updating holes. Constrain the search to the controller band.
    def in_usb_keep(fp_id, x, y, rot):
        for p in pad_world_list(fp_id, x, y, rot):
            if p["npth"] or not p.get("copper", True):
                continue
            for keep in USB_KEEPS:
                if rect_gap(p, keep) < 0.20:
                    return True
        return False

    def place_one(part):
        fp = part["footprint"]
        cx, cy = target_for(part)
        cy = min(max(cy, BAND_Y0 + 1.0), BAND_Y1 - 1.0)
        allow = set()
        if part["ref"] in near_anchor:
            allow.add(near_anchor[part["ref"]])
        if part["ref"] in pin_caps:
            allow.add("U1")
        for sx, sy in spiral(cx, cy, limit=700):
            if not (BAND_Y0 <= sy <= BAND_Y1):
                continue
            if not (BAND_X0 <= sx <= BAND_X1):
                continue
            for rot in (0, 90, 180, 270):
                if in_usb_keep(fp, sx, sy, rot):
                    continue
                if fits(fp, sx, sy, rot, placed, holes, poly, allow, copper_need=0.2):
                    add(part["ref"], fp, sx, sy, rot, allow=tuple(allow))
                    return True
        return False

    # Multiple passes: parts next to anchors first.
    pending = list(remaining)
    pending.sort(key=lambda p: (0 if p["ref"] in near_anchor else 1, p["ref"]))
    guard = 0
    while pending and guard < 8:
        guard += 1
        nxt = []
        for part in pending:
            if place_one(part):
                holes = collect_holes(placed, geo["mounting_holes"], geo["stabilizers"])
            else:
                nxt.append(part)
        if len(nxt) == len(pending):
            break
        pending = nxt
    if pending:
        refs = [p["ref"] for p in pending]
        raise RuntimeError(f"unplaced parts: {refs}")

    # Three fab fiducials on open copper, clear of every courtyard.
    fid_fp = "Fiducial:Fiducial_1mm_Mask2mm"
    fid_seeds = ((100.0, 42.2), (168.0, 42.2), (78.0, 50.5), (186.0, 54.0), (48.0, 150.0), (175.0, 175.0))
    fid_found = []
    for seed in fid_seeds:
        if len(fid_found) >= 3:
            break
        for fx, fy in spiral(seed[0], seed[1], limit=240):
            if any(math.hypot(fx - ax, fy - ay) < 28.0 for ax, ay in fid_found):
                continue
            if fits(fid_fp, fx, fy, 0, placed, holes, poly, set(), copper_need=0.30):
                add(f"FID{len(fid_found) + 1}", fid_fp, fx, fy, 0)
                fid_found.append((fx, fy))
                break
    print(f"fiducials {fid_found}", flush=True)

    pairs = courtyard_pairs(placed, by_ref)
    print(f"placed {len(pos)} footprints, courtyard pairs {len(pairs)}", flush=True)
    return pos, pairs


# --- board construction ---------------------------------------------------

def mirror_fp(fp):
    for pad in fp.Pads():
        p = pad.GetFPRelativePosition()
        pad.SetFPRelativePosition(pcbnew.VECTOR2I(-p.x, p.y))
        try:
            pad.SetOrientation(pcbnew.EDA_ANGLE(-pad.GetOrientation().AsDegrees(), pcbnew.DEGREES_T))
        except Exception:
            pass
    for item in list(fp.GraphicalItems()):
        cls = item.GetClass()
        if cls == "PCB_SHAPE":
            mirror_shape(item)
        elif cls in ("PCB_TEXT", "PCB_FIELD"):
            try:
                pos = item.GetPosition()
                item.SetPosition(pcbnew.VECTOR2I(-pos.x, pos.y))
                if hasattr(item, "SetMirrored"):
                    item.SetMirrored(False)
            except Exception:
                pass
    for item in (fp.Reference(), fp.Value()):
        try:
            pos = item.GetPosition()
            item.SetPosition(pcbnew.VECTOR2I(-pos.x, pos.y))
            item.SetMirrored(False)
        except Exception:
            pass


def mirror_shape(sh):
    k = int(sh.GetShape())

    def neg(pt):
        return pcbnew.VECTOR2I(-pt.x, pt.y)

    try:
        if k == int(pcbnew.SHAPE_T_SEGMENT) or k == int(pcbnew.SHAPE_T_RECT):
            sh.SetStart(neg(sh.GetStart()))
            sh.SetEnd(neg(sh.GetEnd()))
        elif k == int(pcbnew.SHAPE_T_CIRCLE):
            sh.SetCenter(neg(sh.GetCenter()))
        elif k == int(pcbnew.SHAPE_T_ARC):
            sh.SetCenter(neg(sh.GetCenter()))
            sh.SetStart(neg(sh.GetStart()))
            sh.SetEnd(neg(sh.GetEnd()))
            if hasattr(sh, "GetArcMid") and hasattr(sh, "SetArcGeometry"):
                mid = neg(sh.GetArcMid())
                sh.SetArcGeometry(sh.GetStart(), mid, sh.GetEnd())
        elif k == int(pcbnew.SHAPE_T_POLY):
            poly = sh.GetPolyShape()
            for oi in range(poly.OutlineCount()):
                outline = poly.Outline(oi)
                for pi in range(outline.PointCount()):
                    pt = outline.CPoint(pi)
                    outline.SetPoint(pi, pcbnew.VECTOR2I(-pt.x, pt.y))
        elif k == int(pcbnew.SHAPE_T_BEZIER):
            sh.SetStart(neg(sh.GetStart()))
            sh.SetEnd(neg(sh.GetEnd()))
    except Exception as exc:
        print("mirror shape", k, exc, flush=True)


def apply_design_rules(board):
    board.SetCopperLayerCount(4)
    ds = board.GetDesignSettings()
    ds.SetBoardThickness(iu(1.6))
    pairs = {
        "m_MinClearance": CLEAR,
        "m_TrackMinWidth": 0.16,
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


class Raster:
    """owner: -1 empty, -2 wall, 1..9999 net copper, 10000+net that net's halo."""

    def __init__(self, poly):
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        self.x0 = min(xs) - 1.0
        self.y0 = min(ys) - 1.0
        self.w = int((max(xs) - self.x0 + 2.0) / RES) + 2
        self.h = int((max(ys) - self.y0 + 2.0) / RES) + 2
        n = self.w * self.h
        self.owner = [array.array("i", [-1]) * n, array.array("i", [-1]) * n]
        self.poly = poly
        self._mask_board()

    def _idx(self, x, y):
        ix = int((x - self.x0) / RES)
        iy = int((y - self.y0) / RES)
        if ix < 0 or iy < 0 or ix >= self.w or iy >= self.h:
            return None
        return iy * self.w + ix

    def _mark(self, layer, idx, net_id, kind):
        cur = self.owner[layer][idx]
        if kind == "wall":
            self.owner[layer][idx] = -2
            return
        if cur == -2:
            return
        halo = 10000 + net_id
        if kind == "copper":
            if cur in (-1, net_id, halo):
                self.owner[layer][idx] = net_id
            else:
                self.owner[layer][idx] = -2
            return
        if cur == -1:
            self.owner[layer][idx] = halo
        elif cur == net_id or cur == halo:
            return
        else:
            self.owner[layer][idx] = -2

    def passable(self, x, y, layer, net_id):
        i = self._idx(x, y)
        if i is None:
            return False
        o = self.owner[layer][i]
        if o == -1:
            return True
        if net_id and (o == net_id or o == 10000 + net_id):
            return True
        return False

    def _mask_board(self):
        # Scanline fill, then wall a capsule along every outline edge.
        margin = EDGE_COPPER + TRACK_HALF + 0.04
        inside = bytearray(self.w * self.h)
        n = len(self.poly)
        for iy in range(self.h):
            y = self.y0 + (iy + 0.5) * RES
            xs = []
            for i in range(n):
                x1, y1 = self.poly[i]
                x2, y2 = self.poly[(i + 1) % n]
                if (y1 > y) == (y2 > y):
                    continue
                xs.append(x1 + (y - y1) / (y2 - y1) * (x2 - x1))
            xs.sort()
            row = iy * self.w
            for k in range(0, len(xs) - 1, 2):
                ix0 = max(0, int((xs[k] - self.x0) / RES))
                ix1 = min(self.w - 1, int((xs[k + 1] - self.x0) / RES))
                for ix in range(ix0, ix1 + 1):
                    inside[row + ix] = 1
        for i, flag in enumerate(inside):
            if not flag:
                self.owner[0][i] = -2
                self.owner[1][i] = -2
        for i in range(n):
            self.paint_seg(self.poly[i], self.poly[(i + 1) % n], margin, (0, 1), -2)

    def paint_circle(self, x, y, radius, layers, net_id=-2, kind="wall"):
        if radius <= 0:
            return
        r2 = radius * radius
        ix0 = int((x - radius - self.x0) / RES)
        iy0 = int((y - radius - self.y0) / RES)
        ix1 = int((x + radius - self.x0) / RES) + 1
        iy1 = int((y + radius - self.y0) / RES) + 1
        use = "wall" if net_id == -2 else kind
        for iy in range(max(0, iy0), min(self.h, iy1)):
            py = self.y0 + (iy + 0.5) * RES
            row = iy * self.w
            for ix in range(max(0, ix0), min(self.w, ix1)):
                px = self.x0 + (ix + 0.5) * RES
                if (px - x) ** 2 + (py - y) ** 2 <= r2:
                    for layer in layers:
                        self._mark(layer, row + ix, net_id, use)

    def paint_pad(self, pad, layers, margin, net_id, kind):
        grow = margin
        if pad["round"] or (abs(pad["sx"] - pad["sy"]) < 0.01 and pad.get("drill", 0) > 0):
            self.paint_circle(
                pad["wx"], pad["wy"], max(pad["sx"], pad["sy"]) / 2 + grow, layers, net_id, kind
            )
            return
        hw = pad["sx"] / 2 + grow
        hh = pad["sy"] / 2 + grow
        a = math.radians(pad["rot"])
        c, s = abs(math.cos(a)), abs(math.sin(a))
        bw = hw * c + hh * s
        bh = hw * s + hh * c
        ix0 = int((pad["wx"] - bw - self.x0) / RES)
        iy0 = int((pad["wy"] - bh - self.y0) / RES)
        ix1 = int((pad["wx"] + bw - self.x0) / RES) + 1
        iy1 = int((pad["wy"] + bh - self.y0) / RES) + 1
        ca, sa = math.cos(a), math.sin(a)
        use = "wall" if net_id == -2 else kind
        for iy in range(max(0, iy0), min(self.h, iy1)):
            py = self.y0 + (iy + 0.5) * RES
            row = iy * self.w
            for ix in range(max(0, ix0), min(self.w, ix1)):
                px = self.x0 + (ix + 0.5) * RES
                dx, dy = px - pad["wx"], py - pad["wy"]
                llx = dx * ca - dy * sa
                lly = dx * sa + dy * ca
                if abs(llx) <= hw and abs(lly) <= hh:
                    for layer in layers:
                        self._mark(layer, row + ix, net_id, use)

    def paint_seg(self, a, b, radius, layers, net_id=-2, kind="wall"):
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        steps = max(1, int(length / (RES * 0.8)))
        for i in range(steps + 1):
            t = i / steps
            self.paint_circle(
                a[0] + (b[0] - a[0]) * t,
                a[1] + (b[1] - a[1]) * t,
                radius,
                layers,
                net_id,
                kind,
            )


def pad_layers(pad):
    if pad.get("npth") or not pad.get("copper", True):
        return ()
    if pad["drill"] > 0 and not pad["smd"]:
        return (0, 1)
    front = pad.get("front", True)
    back = pad.get("back", False)
    if front and back:
        return (0, 1)
    if back and not front:
        return (1,)
    return (0,)


class GridRouter:
    def __init__(self, raster: Raster):
        self.r = raster
        self.ox = math.floor(raster.x0 / GRID) * GRID
        self.oy = math.floor(raster.y0 / GRID) * GRID
        self.nx = int((raster.w * RES) / GRID) + 4
        self.ny = int((raster.h * RES) / GRID) + 4
        self.vias = []
        self.keepout = []  # (x, y, radius) circles where a via would cut the USB reference plane

    def snap(self, x, y):
        ix = int(round((x - self.ox) / GRID))
        iy = int(round((y - self.oy) / GRID))
        ix = max(0, min(self.nx - 1, ix))
        iy = max(0, min(self.ny - 1, iy))
        return ix, iy, self.ox + ix * GRID, self.oy + iy * GRID

    def free(self, x, y, layer, width, net_id):
        extra = max(0.0, width / 2 - TRACK_HALF)
        if extra < 0.02:
            return self.r.passable(x, y, layer, net_id)
        steps = int(extra / RES) + 1
        for iy in range(-steps, steps + 1):
            for ix in range(-steps, steps + 1):
                if ix * ix + iy * iy > steps * steps:
                    continue
                if not self.r.passable(x + ix * RES, y + iy * RES, layer, net_id):
                    return False
        return True

    def via_ok(self, x, y, net_id):
        # Pad halos already include ~0.36 mm. The via center only has to sit
        # just outside that halo; exact pad geometry is checked separately.
        rad = 0.18
        steps = int(rad / RES) + 1
        for layer in (0, 1):
            for iy in range(-steps, steps + 1):
                for ix in range(-steps, steps + 1):
                    if (ix * ix + iy * iy) * RES * RES > rad * rad:
                        continue
                    if not self.r.passable(x + ix * RES, y + iy * RES, layer, net_id):
                        return False
        for vx, vy in self.vias:
            if math.hypot(x - vx, y - vy) < 0.82:
                return False
        for kx, ky, kr in self.keepout:
            if math.hypot(x - kx, y - ky) < kr:
                return False
        return True

    def route(self, starts, goals, width, net_id, limit=160000):
        """Orthogonal A* on both layers. starts/goals are (x, y, layer or None).

        Points are snapped onto the routing grid. Callers must dogleg from the
        real pad to that exact grid point. `sv` spaces vias by at least 1.0 mm.
        """
        start_nodes = []
        for x, y, layer in starts:
            for lay in ((0, 1) if layer is None else (layer,)):
                ix, iy, gx, gy = self.snap(x, y)
                if self.free(gx, gy, lay, width, net_id):
                    start_nodes.append((lay, ix, iy))
        goal_set = set()
        goal_pts = []
        for x, y, layer in goals:
            for lay in ((0, 1) if layer is None else (layer,)):
                ix, iy, gx, gy = self.snap(x, y)
                if self.free(gx, gy, lay, width, net_id):
                    goal_set.add((lay, ix, iy))
                    goal_pts.append((gx, gy))
        if not start_nodes or not goal_set:
            return None

        def heur(ix, iy):
            best = 1e9
            x = self.ox + ix * GRID
            y = self.oy + iy * GRID
            for gx, gy in goal_pts:
                best = min(best, abs(x - gx) + abs(y - gy))
            return best

        counter = 0
        heap = []
        dist = {}
        prev = {}
        for lay, ix, iy in start_nodes:
            key = (lay, ix, iy, 2)
            dist[key] = 0.0
            heapq.heappush(heap, (heur(ix, iy), counter, key))
            counter += 1
        seen = 0
        while heap:
            _f, _c, key = heapq.heappop(heap)
            lay, ix, iy, sv = key
            if dist.get(key, 1e18) < _f - heur(ix, iy) - 1e-6:
                continue
            if (lay, ix, iy) in goal_set:
                return self._rebuild(key, prev)
            base = dist[key]
            seen += 1
            if seen > limit:
                return None
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = ix + dx, iy + dy
                if nx < 0 or ny < 0 or nx >= self.nx or ny >= self.ny:
                    continue
                wx = self.ox + nx * GRID
                wy = self.oy + ny * GRID
                if not self.free(wx, wy, lay, width, net_id):
                    continue
                if not self._seg_free(self.ox + ix * GRID, self.oy + iy * GRID, wx, wy, lay, width, net_id):
                    continue
                nsv = sv + 1 if sv < 2 else 2
                nkey = (lay, nx, ny, nsv)
                nd = base + GRID
                if nd + 1e-9 < dist.get(nkey, 1e18):
                    dist[nkey] = nd
                    prev[nkey] = key
                    heapq.heappush(heap, (nd + heur(nx, ny), counter, nkey))
                    counter += 1
            if sv >= 2 and self.via_ok(self.ox + ix * GRID, self.oy + iy * GRID, net_id):
                olay = 1 - lay
                cx = self.ox + ix * GRID
                cy = self.oy + iy * GRID
                if self.free(cx, cy, olay, width, net_id):
                    nkey = (olay, ix, iy, 0)
                    nd = base + 2.5
                    if nd + 1e-9 < dist.get(nkey, 1e18):
                        dist[nkey] = nd
                        prev[nkey] = key
                        heapq.heappush(heap, (nd + heur(ix, iy), counter, nkey))
                        counter += 1
        return None

    def _seg_free(self, x1, y1, x2, y2, layer, width, net_id):
        steps = max(1, int(math.hypot(x2 - x1, y2 - y1) / RES))
        for i in range(steps + 1):
            t = i / steps
            if not self.free(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, layer, width, net_id):
                return False
        return True

    def _rebuild(self, key, prev):
        nodes = [key]
        while key in prev:
            key = prev[key]
            nodes.append(key)
        nodes.reverse()
        pts = []
        for lay, ix, iy, _sv in nodes:
            pt = (lay, self.ox + ix * GRID, self.oy + iy * GRID)
            if pts and pts[-1] == pt:
                continue
            pts.append(pt)
        return pts

    def commit(self, pts, width, net_id=0):
        """Unused by the maze. Kept so a partial path can still be painted."""
        return []


def layer_id(index):
    return pcbnew.F_Cu if index == 0 else pcbnew.B_Cu


def emit_route(board, net, pts, width):
    items = []
    for (l1, x1, y1), (l2, x2, y2) in zip(pts, pts[1:]):
        if l1 != l2:
            items.append(add_via(board, net, x2, y2))
        else:
            items.append(add_track(board, net, layer_id(l1), (x1, y1), (x2, y2), width))
    return items


def exact_hit(x, y, width, pads, holes, poly, ignore):
    """True if a track center at (x, y) would violate clearance."""
    need = width / 2 + CLEAR
    if not point_in_poly(x, y, poly) or dist_to_edges(x, y, poly) < EDGE_COPPER + width / 2:
        return True
    for hx, hy, hr in holes:
        if math.hypot(x - hx, y - hy) < hr + HOLE_CLEAR + width / 2:
            return True
    for p in pads:
        if id(p) in ignore or p["npth"]:
            continue
        if p["drill"] and not p["smd"] and p["sx"] <= p["drill"] + 0.02 and p.get("net_is_plane"):
            continue
        a = math.radians(p["rot"])
        ca, sa = math.cos(a), math.sin(a)
        dx, dy = x - p["wx"], y - p["wy"]
        llx = dx * ca - dy * sa
        lly = dx * sa + dy * sa if False else dx * sa + dy * ca
        hw, hh = p["sx"] / 2, p["sy"] / 2
        ox = abs(llx) - hw
        oy = abs(lly) - hh
        if ox <= 0 and oy <= 0:
            gap = max(ox, oy)
        else:
            gap = math.hypot(max(ox, 0.0), max(oy, 0.0))
        if gap < need - 1e-4:
            return True
    return False


def segment_exact_ok(a, b, width, pads, holes, poly, ignore):
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    steps = max(1, int(length / 0.1))
    for i in range(steps + 1):
        t = i / steps
        x = a[0] + (b[0] - a[0]) * t
        y = a[1] + (b[1] - a[1]) * t
        # allow the portion sitting on the ignored pads
        if exact_hit(x, y, width, pads, holes, poly, ignore):
            return False
    return True


# --- high level layout ----------------------------------------------------

def layout_board(sheet, side: str, project: str):
    geo = load_geo()
    if side == "right":
        verify_plates(geo)
    print(f"layout {side}", flush=True)
    placement, court_pairs = compute_placement(sheet, geo)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"{side}-courtyard-pairs.json").write_text(
        json.dumps(court_pairs, indent=2), encoding="utf-8"
    )
    poly = outline_points(geo)
    board = pcbnew.BOARD()
    apply_design_rules(board)
    net_cache = {}

    # Edge.Cuts
    segs = geo["edge_cuts"]["segments"]
    for seg in segs:
        a = xform(*seg["start_mm"], side)
        b = xform(*seg["end_mm"], side)
        add_line(board, pcbnew.Edge_Cuts, a, b, seg["width_mm"])

    # Footprints from the schematic.
    fp_by_ref = {}
    pad_records = []  # dicts used by the router, in this board's frame
    for part in sheet.parts:
        ref = part["ref"]
        x, y, rot = placement[ref]
        x, y = xform(x, y, side)
        if side == "left":
            rot = -rot
        fp = load_fp(part["footprint"])
        if side == "left":
            mirror_fp(fp)
        fp.SetPosition(v2(x, y))
        fp.SetOrientation(pcbnew.EDA_ANGLE(rot, pcbnew.DEGREES_T))
        fp.SetReference(ref)
        fp.SetValue(part["value"])
        try:
            fp.SetPath(pcbnew.KIID_PATH("/" + part["uuid"]))
        except Exception as exc:
            print("SetPath", ref, exc, flush=True)
        fp.SetSheetfile(f"{project}.kicad_sch")
        try:
            fp.SetSheetname("Root")
        except Exception:
            pass
        # nets
        for pad in fp.Pads():
            num = pad.GetNumber()
            assign = part["assign"].get(num)
            if not assign or assign[0] == "nc":
                continue
            net = ensure_net(board, net_cache, assign[1])
            pad.SetNet(net)
        # readable refs
        try:
            ref_t = fp.Reference()
            ref_t.SetTextSize(v2(0.8, 0.8))
            ref_t.SetTextThickness(iu(0.12))
            ref_t.SetVisible(True)
            val_t = fp.Value()
            val_t.SetVisible(False)
        except Exception:
            pass
        board.Add(fp)
        fp_by_ref[ref] = fp
        for pad in fp.Pads():
            posp = pad.GetPosition()
            assign = part["assign"].get(pad.GetNumber())
            net_name = None if not assign or assign[0] == "nc" else assign[1]
            attr = int(pad.GetAttribute())
            layers = pad.GetLayerSet()
            front = bool(layers.Contains(pcbnew.F_Cu))
            back = bool(layers.Contains(pcbnew.B_Cu))
            rec = {
                "ref": ref,
                "num": pad.GetNumber(),
                "net": net_name,
                "wx": mm(posp.x),
                "wy": mm(posp.y),
                "sx": mm(pad.GetSizeX()),
                "sy": mm(pad.GetSizeY()),
                "rot": pad.GetOrientation().AsDegrees(),
                "drill": mm(pad.GetDrillSizeX()),
                "npth": attr == int(pcbnew.PAD_ATTRIB_NPTH),
                "smd": attr == int(pcbnew.PAD_ATTRIB_SMD),
                "round": int(pad.GetShape()) == int(pcbnew.PAD_SHAPE_CIRCLE),
                "copper": front or back,
                "front": front,
                "back": back,
                "fp_x": x,
                "fp_y": y,
            }
            pad_records.append(rec)

    # Mounting holes and stabilizers. Not schematic symbols.
    for i, hole in enumerate(geo["mounting_holes"], start=1):
        hx, hy = xform(hole["x_mm"], hole["y_mm"], side)
        make_npth_fp(board, f"H{i}", hx, hy, 0, [(0, 0, hole["drill_diameter_mm"])])
    for stab in geo["stabilizers"]:
        sx, sy = xform(stab["x_mm"], stab["y_mm"], side)
        rot = -stab["rotation_deg"] if side == "left" else stab["rotation_deg"]
        holes = []
        for hole in stab["holes"]:
            lx = -hole["local_x_mm"] if side == "left" else hole["local_x_mm"]
            holes.append((lx, hole["local_y_mm"], hole["drill_diameter_mm"]))
        make_npth_fp(board, stab["reference"], sx, sy, rot, holes)

    # Fiducials were sited in the right-hand frame. Mirror with the board.
    fid_right = [placement[f"FID{i}"][:2] for i in range(1, 4) if f"FID{i}" in placement]
    for i, (fx, fy) in enumerate(fid_right, start=1):
        fx, fy = xform(fx, fy, side)
        fid = load_fp("Fiducial:Fiducial_1mm_Mask2mm")
        fid.SetPosition(v2(fx, fy))
        fid.SetReference(f"FID{i}")
        fid.SetValue("FID")
        try:
            fid.Reference().SetVisible(False)
            fid.Value().SetVisible(False)
        except Exception:
            pass
        board.Add(fid)
        posp = None
        for pad in fid.Pads():
            posp = (mm(pad.GetPosition().x), mm(pad.GetPosition().y))
            pad_records.append(
                {
                    "ref": f"FID{i}",
                    "num": pad.GetNumber(),
                    "net": None,
                    "wx": posp[0],
                    "wy": posp[1],
                    "sx": mm(pad.GetSizeX()),
                    "sy": mm(pad.GetSizeY()),
                    "rot": 0.0,
                    "drill": 0.0,
                    "npth": False,
                    "smd": True,
                    "round": True,
                    "copper": True,
                    "front": True,
                    "back": False,
                    "fp_x": fx,
                    "fp_y": fy,
                }
            )

    add_silkscreen(board, side, poly)

    pcb_path = ROOT / side / f"{project}.kicad_pcb"
    print(f"saving placement {pcb_path}", flush=True)
    pcbnew.SaveBoard(str(pcb_path), board)
    print("placement saved", flush=True)
    if os.environ.get("LAYOUT_PHASE") == "place":
        return pcb_path

    # Route, then save the copper before any zone is created. SaveBoard
    # SIGSEGVs once zones exist, and that crash was discarding the board.
    failed = route_all(board, side, pad_records, poly, net_cache, geo)
    print(f"saving copper {pcb_path}", flush=True)
    pcbnew.SaveBoard(str(pcb_path), board)
    print(f"wrote {pcb_path} unrouted={len(failed)}", flush=True)
    fill_saved_board(pcb_path, side)
    return pcb_path


def fill_saved_board(pcb_path: Path, side: str):
    """Add and fill zones in a child process. The copper file stays if it dies."""
    dest = pcb_path.with_suffix(".zones.kicad_pcb")
    script = (
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, str(Path(sys.argv[1]).resolve().parents[1] / 'tools'))\n"
        "import pcbnew\n"
        "from layout_pcb import add_zones, load_geo, outline_points, xform\n"
        "src, side, dest = sys.argv[1], sys.argv[2], sys.argv[3]\n"
        "board = pcbnew.LoadBoard(src)\n"
        "poly = [xform(x, y, side) for x, y in outline_points(load_geo())]\n"
        "add_zones(board, side, {}, poly)\n"
        "pcbnew.SaveBoard(dest, board)\n"
        "print('zones saved', dest, flush=True)\n"
        "filler = pcbnew.ZONE_FILLER(board)\n"
        "filler.Fill(board.Zones())\n"
        "pcbnew.SaveBoard(dest, board)\n"
        "print('zones filled', dest, flush=True)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script, str(pcb_path), side, str(dest)],
        check=False,
    )
    print(f"zone fill exit {proc.returncode} {dest}", flush=True)
    if proc.returncode == 0 and dest.exists():
        dest.replace(pcb_path)
        print(f"zones merged into {pcb_path}", flush=True)
        return True
    print(f"zone pass failed; copper board kept at {pcb_path}", flush=True)
    return False


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


def add_silkscreen(board, side, poly_right):
    # Text is authored in the right-hand frame, then moved. Glyphs stay upright.
    hand = "LEFT" if side == "left" else "RIGHT"
    labels = [
        ("ErgoDox RP2040", 128.0, 147.6, 1.4),
        (hand, 128.0, 150.0, 1.6),
        ("HOST", 137.66, 42.6, 1.2),
        ("LINK", 86.46, 43.4, 1.2),
        ("NOT A PC PORT", 86.46, 45.6, 1.0),
        ("POLARITY K TO COLUMN", 150.0, 146.0, 1.0),
        ("LED DIN AT MARK", 168.0, 146.0, 1.0),
    ]
    for text, x, y, size in labels:
        x, y = xform(x, y, side)
        add_text(board, text, x, y, size=size)
    # Board-origin cross, inside the outline near the minimum-X vertex.
    ox, oy = xform(28.0, 146.0, side)
    arm = 1.4
    add_line(board, pcbnew.F_SilkS, (ox - arm, oy), (ox + arm, oy), 0.15)
    add_line(board, pcbnew.F_SilkS, (ox, oy - arm), (ox, oy + arm), 0.15)
    add_text(board, "ORIGIN", ox + 3.2, oy, size=0.9)
    try:
        board.GetDesignSettings().SetAuxOrigin(v2(ox, oy))
    except Exception as exc:
        print("aux origin", exc, flush=True)
    # Fab note. Not silkscreen.
    note = (
        "JLC04161H-7628 1.6 mm 4-layer. "
        "USB D+/D- width 0.290661 mm, gap 0.203200 mm, Er1 4.3 coated microstrip to L2."
    )
    nx, ny = xform(120.0, 44.0, side)
    add_text(board, note, nx, ny, layer=pcbnew.Cmts_User, size=0.8)
    title = board.GetTitleBlock()
    title.SetTitle(f"ErgoDox RP2040 {hand}")
    title.SetComment(1, "LINK is UART, not a PC port")
    title.SetComment(2, "USB pair 0.290661/0.203200 mm on JLC04161H-7628")


def group_pads(records):
    nets = {}
    for rec in records:
        if not rec["net"]:
            continue
        nets.setdefault(rec["net"], []).append(rec)
    return nets


def outward_end(pad, distance):
    dx, dy = pad["wx"] - pad["fp_x"], pad["wy"] - pad["fp_y"]
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        dx, dy = 0.0, 1.0
    if abs(dx) >= abs(dy):
        direction = (1.0 if dx > 0 else -1.0, 0.0)
    else:
        direction = (0.0, 1.0 if dy > 0 else -1.0)
    return (pad["wx"] + direction[0] * distance, pad["wy"] + direction[1] * distance), direction


def route_all(board, side, records, poly_right, net_cache, geo):
    # Outline in this board's frame.
    poly = [xform(x, y, side) for x, y in poly_right]
    nets = group_pads(records)
    holes = []
    for rec in records:
        if rec["drill"] > 0:
            holes.append((rec["wx"], rec["wy"], rec["drill"] / 2))
    for hole in geo["mounting_holes"]:
        hx, hy = xform(hole["x_mm"], hole["y_mm"], side)
        holes.append((hx, hy, hole["drill_diameter_mm"] / 2))
    for stab in geo["stabilizers"]:
        sx, sy = stab["x_mm"], stab["y_mm"]
        rot = stab["rotation_deg"]
        for hole in stab["holes"]:
            lx = hole["local_x_mm"]
            ly = hole["local_y_mm"]
            if side == "left":
                lx = -lx
                rot_use = -rot
                ox, oy = xform(sx, sy, side)
                wx, wy = world(ox, oy, rot_use, lx, ly)
            else:
                wx, wy = world(sx, sy, rot, lx, ly)
            holes.append((wx, wy, hole["drill_diameter_mm"] / 2))

    raster = Raster(poly)
    margin = ROUTE_CLEAR + TRACK_HALF
    net_ids = {}

    def nid(name):
        if name not in net_ids:
            net_ids[name] = len(net_ids) + 1
        return net_ids[name]

    copper_pads = []
    for rec in records:
        if rec["npth"] or not rec.get("copper", True) or not rec.get("net"):
            continue
        layers = pad_layers(rec)
        if not layers:
            continue
        copper_pads.append((rec, layers))
    for rec, layers in copper_pads:
        raster.paint_pad(rec, layers, 0.0, nid(rec["net"]), "copper")
    for rec, layers in copper_pads:
        raster.paint_pad(rec, layers, margin, nid(rec["net"]), "halo")
    for hx, hy, hr in holes:
        raster.paint_circle(hx, hy, hr + HOLE_CLEAR + 0.05, (0, 1), -2, "wall")

    router = GridRouter(raster)
    drawn = []

    def draw_seg(net_name, a, b, width, layer_index):
        if math.hypot(a[0] - b[0], a[1] - b[1]) < 0.02:
            return
        net = ensure_net(board, net_cache, net_name)
        add_track(board, net, layer_id(layer_index), a, b, width)
        # Halo first, then the copper centerline so this net can still tee off it.
        halo_r = width / 2 + CLEAR + 0.04
        raster.paint_seg(a, b, halo_r, (layer_index,), nid(net_name), "halo")
        raster.paint_seg(a, b, width / 2, (layer_index,), nid(net_name), "copper")
        drawn.append((net_name, a, b, width, layer_index))

    def draw_via_at(net_name, x, y):
        for vx, vy in router.vias:
            if math.hypot(vx - x, vy - y) < 0.05:
                return
        net = ensure_net(board, net_cache, net_name)
        add_via(board, net, x, y)
        raster.paint_circle(x, y, VIA_D / 2 + CLEAR + 0.04, (0, 1), nid(net_name), "halo")
        raster.paint_circle(x, y, VIA_D / 2, (0, 1), nid(net_name), "copper")
        router.vias.append((x, y))

    # Power vias. GND -> L2, +5V -> L3 top band, LED_5V -> L3 key field, +3V3 -> B.Cu band.
    # The zones are added after routing. Vias must land inside those rectangles.
    z5 = xform_rect(RECT_5V, side)
    zled = xform_rect(RECT_LED, side)
    z3 = z5

    def in_rect(pt, rect, inset=0.6):
        x, y = pt
        return rect[0] + inset <= x <= rect[2] - inset and rect[1] + inset <= y <= rect[3] - inset

    zone_for = {"GND": None, "+5V": z5, "LED_5V": zled, "+3V3": z3}

    def seg_seg_dist(a, b, c, d):
        def cross(p, q, r):
            return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

        def on_seg(p, q, r):
            return (
                min(p[0], q[0]) - 1e-6 <= r[0] <= max(p[0], q[0]) + 1e-6
                and min(p[1], q[1]) - 1e-6 <= r[1] <= max(p[1], q[1]) + 1e-6
            )

        d1, d2 = cross(c, d, a), cross(c, d, b)
        d3, d4 = cross(a, b, c), cross(a, b, d)
        if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
            return 0.0
        if abs(d1) < 1e-9 and on_seg(c, d, a):
            return 0.0
        if abs(d2) < 1e-9 and on_seg(c, d, b):
            return 0.0
        if abs(d3) < 1e-9 and on_seg(a, b, c):
            return 0.0
        if abs(d4) < 1e-9 and on_seg(a, b, d):
            return 0.0

        def cand(p, q, r):
            dx, dy = q[0] - p[0], q[1] - p[1]
            L2 = dx * dx + dy * dy
            if L2 < 1e-12:
                return math.hypot(r[0] - p[0], r[1] - p[1])
            t = max(0.0, min(1.0, ((r[0] - p[0]) * dx + (r[1] - p[1]) * dy) / L2))
            return math.hypot(r[0] - (p[0] + t * dx), r[1] - (p[1] + t * dy))

        return min(cand(a, b, c), cand(a, b, d), cand(c, d, a), cand(c, d, b))

    def hits_drawn(a, b, width, net_name, layer):
        for dnet, c, d, dw, dlayer in drawn:
            if dnet == net_name or dlayer != layer:
                continue
            if seg_seg_dist(a, b, c, d) < (width + dw) / 2 + CLEAR - 1e-4:
                return True
        return False

    def hits_via(a, b, width, net_name):
        limit = VIA_D / 2 + width / 2 + CLEAR - 1e-4
        for vx, vy in router.vias:
            if seg_seg_dist(a, b, (vx, vy), (vx, vy)) < limit:
                # A same-net via is still a hole the track may end on, not cross.
                return True
        return False

    def via_clear(ex, ey, pad, width):
        # The via must clear every pad, including this net's own copper.
        if exact_hit(ex, ey, VIA_D, records, holes, poly, set()):
            return False
        if not router.via_ok(ex, ey, nid(pad["net"])):
            return False
        if hits_drawn((ex, ey), (ex, ey), VIA_D, pad["net"], 0) or hits_drawn((ex, ey), (ex, ey), VIA_D, pad["net"], 1):
            return False
        return True

    def connect_via(pad, net_name, ex, ey, width):
        a = (pad["wx"], pad["wy"])
        b = (ex, ey)
        ignore = {id(p) for p in nets.get(net_name, [])}
        options = []
        if abs(a[0] - b[0]) < 0.02 or abs(a[1] - b[1]) < 0.02:
            options.append([a, b])
        for mid in ((b[0], a[1]), (a[0], b[1])):
            if math.hypot(mid[0] - a[0], mid[1] - a[1]) < 0.02 or math.hypot(mid[0] - b[0], mid[1] - b[1]) < 0.02:
                continue
            options.append([a, mid, b])
        for opt in options:
            ok = True
            for s, e in zip(opt, opt[1:]):
                if (
                    not segment_exact_ok(s, e, width, records, holes, poly, ignore)
                    or hits_drawn(s, e, width, net_name, 0)
                    or hits_via(s, e, width, net_name)
                ):
                    ok = False
                    break
            if not ok:
                continue
            for s, e in zip(opt, opt[1:]):
                draw_seg(net_name, s, e, width, 0)
            draw_via_at(net_name, *b)
            return True
        return False

    # USB pair first so its ground keepout exists before power vias land.
    usb_done = route_usb(
        board, side, nets, records, holes, poly, draw_seg, hits_drawn, hits_via, router, nid
    )

    for net_name in ("GND", "+5V", "+3V3", "LED_5V"):
        width = 0.80 if net_name in ("+5V", "LED_5V") else 0.40
        zone = zone_for[net_name]
        for pad in nets.get(net_name, []):
            if pad["npth"] or not pad.get("copper", True):
                continue
            if pad["drill"] > 0 and not pad["smd"]:
                continue
            if pad["ref"] == "U1" and pad["num"] == "57":
                continue
            dists = (1.15, 1.5, 1.9, 2.4, 3.0, 3.8)
            if zone is not None and not in_rect((pad["wx"], pad["wy"]), zone, inset=0.0):
                dists = dists + (6.0, 10.0, 16.0, 24.0, 34.0)
            placed_via = False
            for use_w in (width, 0.40, 0.25):
                for dist in dists:
                    steps = 16
                    for i in range(steps):
                        ang = 2 * math.pi * i / steps
                        ex = pad["wx"] + dist * math.cos(ang)
                        ey = pad["wy"] + dist * math.sin(ang)
                        if zone is not None and not in_rect((ex, ey), zone, inset=0.9):
                            continue
                        if not via_clear(ex, ey, pad, use_w):
                            continue
                        if connect_via(pad, net_name, ex, ey, use_w):
                            placed_via = True
                            break
                    if placed_via:
                        break
                if placed_via:
                    break
            if not placed_via:
                print(f"no power via for {pad['ref']}.{pad['num']} {net_name}", flush=True)

    # Matrix before the LED chain so rows and columns keep the front layer.
    def net_rank(name, span):
        if name.startswith(("ROW", "COL", "SWNODE")):
            return (0, span)
        if name.startswith("LED"):
            return (2, span)
        return (1, span)

    signal_names = []
    for name, pads in nets.items():
        if name in POWER_PLANES or name in usb_done:
            continue
        if len(pads) < 2:
            continue
        xs = [p["wx"] for p in pads]
        ys = [p["wy"] for p in pads]
        span = (max(xs) - min(xs)) + (max(ys) - min(ys))
        signal_names.append((net_rank(name, span), name))
    signal_names.sort()
    print(f"{side} routing {len(signal_names)} nets", flush=True)

    failed = []
    for n_i, (_rank, name) in enumerate(signal_names):
        if n_i % 15 == 0:
            print(f"{side} net {n_i}/{len(signal_names)} {name}", flush=True)
        width = TRACK
        if name in ("HOST_VBUS", "LINK_VBUS"):
            width = 0.60
        elif name == "+1V1":
            width = TRACK
        ok = route_signal(
            board,
            name,
            nets[name],
            width,
            router,
            net_cache,
            records,
            holes,
            poly,
            draw_seg,
            hits_drawn,
            hits_via,
            draw_via_at,
            nid,
        )
        if not ok:
            failed.append(name)
            print(f"UNROUTED {name} pads={len(nets[name])}", flush=True)
    if failed:
        print(f"{side} retry {len(failed)}", flush=True)
        still = []
        for name in failed:
            width = 0.60 if name in ("HOST_VBUS", "LINK_VBUS") else TRACK
            ok = route_signal(
                board, name, nets[name], width, router, net_cache, records, holes, poly,
                draw_seg, hits_drawn, hits_via, draw_via_at, nid, limit=400000,
            )
            if not ok:
                still.append(name)
                print(f"UNROUTED {name} pads={len(nets[name])}", flush=True)
        failed = still
        print(f"{side} unrouted {len(failed)}: {failed}", flush=True)

    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"{side}-unrouted.json").write_text(
        json.dumps({"unrouted": failed}, indent=2) + "\n", encoding="utf-8"
    )
    return failed


def xform_rect(rect, side):
    x0, y0, x1, y1 = rect
    pts = [xform(x0, y0, side), xform(x1, y0, side), xform(x1, y1, side), xform(x0, y1, side)]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def add_zones(board, side, net_cache, poly):
    gnd = ensure_net(board, net_cache, "GND")
    v5 = ensure_net(board, net_cache, "+5V")
    v3 = ensure_net(board, net_cache, "+3V3")
    led = ensure_net(board, net_cache, "LED_5V")
    add_poly_zone(board, gnd, pcbnew.In1_Cu, poly, 1)
    add_rect_zone(board, v5, pcbnew.In2_Cu, xform_rect(RECT_5V, side), 1)
    add_rect_zone(board, led, pcbnew.In2_Cu, xform_rect(RECT_LED, side), 1)
    add_rect_zone(board, v3, pcbnew.B_Cu, xform_rect(RECT_5V, side), 1)


def _zone_common(zone, net):
    zone.SetNet(net)
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    zone.SetMinThickness(iu(0.20))
    zone.SetLocalClearance(iu(0.20))
    zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    zone.SetAssignedPriority(1)
    try:
        zone.SetFillMode(pcbnew.ZONE_FILL_MODE_POLYGONS)
    except Exception:
        pass
    zone.SetIsFilled(False)
    if hasattr(zone, "SetNeedRefill"):
        zone.SetNeedRefill(True)


def add_poly_zone(board, net, layer, points, priority):
    zone = pcbnew.ZONE(board)
    zone.SetLayer(layer)
    _zone_common(zone, net)
    poly = pcbnew.SHAPE_POLY_SET()
    poly.NewOutline()
    for x, y in points:
        poly.Append(iu(x), iu(y))
    zone.SetOutline(poly)
    board.Add(zone)
    return zone


def add_rect_zone(board, net, layer, rect, priority):
    x0, y0, x1, y1 = rect
    return add_poly_zone(board, net, layer, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], priority)


def _clean_pts(pts):
    out = []
    for p in pts:
        if out and abs(p[0] - out[-1][0]) < 0.02 and abs(p[1] - out[-1][1]) < 0.02:
            continue
        if len(out) >= 2:
            a, b = out[-2], out[-1]
            ab = (b[0] - a[0], b[1] - a[1])
            bp = (p[0] - b[0], p[1] - b[1])
            cross = ab[0] * bp[1] - ab[1] * bp[0]
            dot = ab[0] * bp[0] + ab[1] * bp[1]
            if abs(cross) < 1e-3 and dot > 0:
                out[-1] = p
                continue
        out.append(p)
    return out


def _angles_ok(pts):
    """Orthogonal, straight, or a reversal. Reject an acute corner."""
    for i in range(1, len(pts) - 1):
        ax = pts[i][0] - pts[i - 1][0]
        ay = pts[i][1] - pts[i - 1][1]
        bx = pts[i + 1][0] - pts[i][0]
        by = pts[i + 1][1] - pts[i][1]
        la = math.hypot(ax, ay)
        lb = math.hypot(bx, by)
        if la < 0.02 or lb < 0.02:
            continue
        dot = (ax * bx + ay * by) / (la * lb)
        if 0.15 < dot < 0.985:
            return False
    return True


def _orth_options(a, b):
    options = []
    if abs(a[0] - b[0]) < 0.02 or abs(a[1] - b[1]) < 0.02:
        options.append([a, b])
    for mid in ((b[0], a[1]), (a[0], b[1])):
        if math.hypot(mid[0] - a[0], mid[1] - a[1]) < 0.05 or math.hypot(mid[0] - b[0], mid[1] - b[1]) < 0.05:
            continue
        options.append([a, mid, b])
    return options


def _seg_distance(a, b, c, d):
    def cross(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    def on_seg(p, q, r):
        return (
            min(p[0], q[0]) - 1e-6 <= r[0] <= max(p[0], q[0]) + 1e-6
            and min(p[1], q[1]) - 1e-6 <= r[1] <= max(p[1], q[1]) + 1e-6
        )

    d1, d2 = cross(c, d, a), cross(c, d, b)
    d3, d4 = cross(a, b, c), cross(a, b, d)
    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return 0.0
    for val, pt, s, e in ((d1, a, c, d), (d2, b, c, d), (d3, c, a, b), (d4, d, a, b)):
        if abs(val) < 1e-9 and on_seg(s, e, pt):
            return 0.0

    def cand(p, q, r):
        dx, dy = q[0] - p[0], q[1] - p[1]
        length = dx * dx + dy * dy
        if length < 1e-12:
            return math.hypot(r[0] - p[0], r[1] - p[1])
        t = max(0.0, min(1.0, ((r[0] - p[0]) * dx + (r[1] - p[1]) * dy) / length))
        return math.hypot(r[0] - (p[0] + t * dx), r[1] - (p[1] + t * dy))

    return min(cand(a, b, c), cand(a, b, d), cand(c, d, a), cand(c, d, b))


def _path_clear(pts, width, layer, net_name, records, holes, poly, ignore, hits_drawn, hits_via):
    pts = _clean_pts(pts)
    if len(pts) < 2:
        return True
    if not _angles_ok(pts):
        return False
    for s, e in zip(pts, pts[1:]):
        if abs(s[0] - e[0]) > 0.02 and abs(s[1] - e[1]) > 0.02:
            return False
        if math.hypot(e[0] - s[0], e[1] - s[1]) < 0.02:
            continue
        if not segment_exact_ok(s, e, width, records, holes, poly, ignore):
            return False
        if hits_drawn(s, e, width, net_name, layer) or hits_via(s, e, width, net_name):
            return False
    return True


def _mutual(polys, slack=0.002):
    for i, (p1, w1, n1) in enumerate(polys):
        for p2, w2, n2 in polys[i + 1 :]:
            if n1 == n2:
                continue
            need = (w1 + w2) / 2 + CLEAR - slack
            for a, b in zip(p1, p1[1:]):
                for c, d in zip(p2, p2[1:]):
                    if _seg_distance(a, b, c, d) < need:
                        return False
    return True


def route_signal(
    board, name, pads, width, router, net_cache, records, holes, poly,
    draw_seg, hits_drawn, hits_via, draw_via_at, nid, limit=160000,
):
    terminals = []
    for pad in pads:
        if pad["npth"] or not pad.get("copper", True):
            continue
        if any(abs(pad["wx"] - t["wx"]) < 0.05 and abs(pad["wy"] - t["wy"]) < 0.05 for t in terminals):
            continue
        terminals.append(pad)
    if len(terminals) < 2:
        return True
    net_id = nid(name)
    ignore = {id(p) for p in terminals}

    def draw_pts(pts, layer):
        for s, e in zip(pts, pts[1:]):
            draw_seg(name, s, e, width, layer)

    def draw_route(pts):
        for (l1, x1, y1), (l2, x2, y2) in zip(pts, pts[1:]):
            if l1 != l2:
                draw_via_at(name, x2, y2)
            else:
                draw_seg(name, (x1, y1), (x2, y2), width, l1)

    def try_direct(p, q):
        for layer in (0, 1):
            if layer not in pad_layers(p) or layer not in pad_layers(q):
                continue
            for opt in _orth_options((p["wx"], p["wy"]), (q["wx"], q["wy"])):
                if _path_clear(opt, width, layer, name, records, holes, poly, ignore, hits_drawn, hits_via):
                    draw_pts(_clean_pts(opt), layer)
                    return True
        return False

    def find_escape(pad, layer):
        ix, iy, _gx, _gy = router.snap(pad["wx"], pad["wy"])
        vx = pad["wx"] - pad["fp_x"]
        vy = pad["wy"] - pad["fp_y"]
        dirs = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        dirs.sort(key=lambda d: -(d[0] * vx + d[1] * vy))
        home = 0 if pad.get("front", True) else 1
        for dist in list(range(1, 12)) + [14, 18, 24]:
            for sx, sy in dirs:
                x = router.ox + (ix + sx * dist) * GRID
                y = router.oy + (iy + sy * dist) * GRID
                if layer in pad_layers(pad):
                    if not router.free(x, y, layer, width, net_id):
                        continue
                    for opt in _orth_options((pad["wx"], pad["wy"]), (x, y)):
                        if _path_clear(opt, width, layer, name, records, holes, poly, ignore, hits_drawn, hits_via):
                            return (x, y, _clean_pts(opt), layer, None)
                else:
                    if not router.free(x, y, layer, width, net_id):
                        continue
                    if not router.via_ok(x, y, net_id):
                        continue
                    if exact_hit(x, y, VIA_D, records, holes, poly, set()):
                        continue
                    for opt in _orth_options((pad["wx"], pad["wy"]), (x, y)):
                        if _path_clear(opt, width, home, name, records, holes, poly, ignore, hits_drawn, hits_via):
                            return (x, y, _clean_pts(opt), home, (x, y))
        return None

    def draw_escape(esc):
        _x, _y, poly_pts, layer, via = esc
        draw_pts(poly_pts, layer)
        if via is not None:
            draw_via_at(name, via[0], via[1])

    def try_astar(pad, prev):
        for layer in (0, 1):
            ea = find_escape(pad, layer)
            eb = find_escape(prev, layer)
            if not ea or not eb:
                continue
            pts = router.route([(ea[0], ea[1], layer)], [(eb[0], eb[1], layer)], width, net_id, limit=limit)
            if not pts:
                continue
            draw_escape(ea)
            draw_escape(eb)
            draw_route(pts)
            return True
        return False

    order = [terminals[0]]
    rest = terminals[1:]
    while rest:
        cur = order[-1]
        nxt = min(rest, key=lambda p: abs(p["wx"] - cur["wx"]) + abs(p["wy"] - cur["wy"]))
        rest.remove(nxt)
        order.append(nxt)

    linked = [order[0]]
    for pad in order[1:]:
        cands = sorted(linked, key=lambda p: abs(p["wx"] - pad["wx"]) + abs(p["wy"] - pad["wy"]))
        ok = False
        for prev in cands[:4]:
            if try_direct(pad, prev):
                ok = True
                break
        if not ok:
            for prev in cands[:3]:
                if try_astar(pad, prev):
                    ok = True
                    break
        if not ok:
            return False
        linked.append(pad)
    return True


def route_usb(board, side, nets, records, holes, poly, draw_seg, hits_drawn, hits_via, router, nid):
    """90 ohm HOST pair plus receptacle D+/D- ties. Returns nets the maze must not redo."""
    done = set()

    def copper_pads(net):
        return [
            p for p in nets.get(net, [])
            if p.get("copper") and not p.get("npth")
        ]

    def draw_pts(net, pts, width, layer):
        for s, e in zip(_clean_pts(pts), _clean_pts(pts)[1:]):
            draw_seg(net, s, e, width, layer)

    def ignore_of(net):
        return {id(p) for p in copper_pads(net)}

    def install_pair():
        r_dp = [p for p in copper_pads("USB_DP") if p["ref"].startswith("R")]
        r_dm = [p for p in copper_pads("USB_DM") if p["ref"].startswith("R")]
        e_dp = [p for p in copper_pads("USB_DP") if p["ref"].startswith("D")]
        e_dm = [p for p in copper_pads("USB_DM") if p["ref"].startswith("D")]
        if not (r_dp and r_dm and e_dp and e_dm):
            print("USB pair pads missing", flush=True)
            return False
        rp, rm = r_dp[0], r_dm[0]
        ep, em = e_dp[0], e_dm[0]
        print(
            f"USB pads R {rp['wx']:.2f},{rp['wy']:.2f} {rm['wx']:.2f},{rm['wy']:.2f} "
            f"D {ep['wx']:.2f},{ep['wy']:.2f} {em['wx']:.2f},{em['wy']:.2f}",
            flush=True,
        )
        half = USB_CC / 2
        # Coupled run along X. Escape the ESD pads sideways first: pin 5 of the
        # SOT-23-6 sits between USB_DP and USB_DM, so a vertical drop on the pad
        # column would short it. 90 degree corners only.
        best = None
        rx = 1.0 if (rp["wx"] + rm["wx"]) > (ep["wx"] + em["wx"]) else -1.0

        def consider(dp_poly, dm_poly, dp_line):
            nonlocal best
            if best is not None:
                return
            dp_poly, dm_poly = _clean_pts(dp_poly), _clean_pts(dm_poly)
            if not _angles_ok(dp_poly) or not _angles_ok(dm_poly):
                return
            if not _path_clear(dp_poly, USB_W, 0, "USB_DP", records, holes, poly, ignore_of("USB_DP"), hits_drawn, hits_via):
                return
            if not _path_clear(dm_poly, USB_W, 0, "USB_DM", records, holes, poly, ignore_of("USB_DM"), hits_drawn, hits_via):
                return
            if not _mutual([(dp_poly, USB_W, "USB_DP"), (dm_poly, USB_W, "USB_DM")]):
                return
            best = (dp_poly, dm_poly, dp_line)

        def jog_x(pad, other, lane_y):
            lo, hi = sorted((pad["wy"], lane_y))
            crosses = lo + 0.05 < other["wy"] < hi - 0.05 and abs(pad["wx"] - other["wx"]) < 0.8
            if crosses:
                return pad["wx"] - rx * 0.90
            return pad["wx"]

        def poly_for(res, esd, other_res, lane_y, esc_x):
            jx = jog_x(res, other_res, lane_y)
            return [
                (esd["wx"], esd["wy"]),
                (esc_x, esd["wy"]),
                (esc_x, lane_y),
                (jx, lane_y),
                (jx, res["wy"]),
                (res["wx"], res["wy"]),
            ]

        centers = []
        for base in (
            (rp["wy"] + rm["wy"]) / 2,
            (ep["wy"] + em["wy"]) / 2,
            (rp["wy"] + rm["wy"] + ep["wy"] + em["wy"]) / 4,
        ):
            for shift in (0.0, 0.25, -0.25, 0.50, -0.50):
                centers.append(base + shift)
        esd_x = (ep["wx"] + em["wx"]) / 2
        for hi_is_dp in (True, False):
            for center in centers:
                hi, lo = center + half, center - half
                dp_lane, dm_lane = (hi, lo) if hi_is_dp else (lo, hi)
                for esc in (1.15, 1.45, 1.80, 2.20, 2.70, 3.30):
                    esc_x = esd_x + rx * esc
                    dp_poly = poly_for(rp, ep, rm, dp_lane, esc_x)
                    dm_poly = poly_for(rm, em, rp, dm_lane, esc_x)
                    consider(dp_poly, dm_poly, [(esc_x, dp_lane), (jog_x(rp, rm, dp_lane), dp_lane)])
                    if best is not None:
                        break
                if best is not None:
                    break
            if best is not None:
                break
        if not best:
            print("USB 90 ohm pair not placed", flush=True)
            return False
        dp_poly, dm_poly, dp_line = best
        draw_pts("USB_DP", dp_poly, USB_W, 0)
        draw_pts("USB_DM", dm_poly, USB_W, 0)
        # Keep later vias out of the reference plane under the pair.
        a, b = dp_line[0], dp_line[1]
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        steps = max(1, int(length / 0.8))
        for i in range(steps + 1):
            t = i / steps
            router.keepout.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, 0.90))
        done.update(("USB_DP", "USB_DM"))
        print(f"USB pair {side} {a} -> {b}", flush=True)
        return True

    def install_ties(jref, net_a, net_b, esd_ref):
        ja = sorted([p for p in copper_pads(net_a) if p["ref"] == jref], key=lambda p: (p["wx"], p["wy"]))
        jb = sorted([p for p in copper_pads(net_b) if p["ref"] == jref], key=lambda p: (p["wx"], p["wy"]))
        ea = [p for p in copper_pads(net_a) if p["ref"] == esd_ref]
        eb = [p for p in copper_pads(net_b) if p["ref"] == esd_ref]
        if len(ja) < 2 or len(jb) < 2 or not ea or not eb:
            print(f"tie pads missing {jref} {net_a}/{net_b}", flush=True)
            return
        # Opposite sides of the pad row. Same-side U's cross because A6/B6 and A7/B7 interleave.
        plans = []
        for reach_a, reach_b in ((0.95, 1.20), (1.05, 1.30), (1.20, 1.45), (0.85, 1.05), (1.35, 1.55)):
            for sign in (1.0, -1.0):
                plans.append((reach_a, sign, reach_b, -sign))
        # Back-layer horizontals, both inboard, at two different reaches.
        back_plans = [(1.45, 2.35), (1.55, 2.6), (1.7, 2.9)]

        def front_u(pair, reach, sign):
            y = pair[0]["wy"] + sign * reach
            pts = [
                (pair[0]["wx"], pair[0]["wy"]),
                (pair[0]["wx"], y),
                (pair[1]["wx"], y),
                (pair[1]["wx"], pair[1]["wy"]),
            ]
            return _clean_pts(pts)

        def dog_options(esd, target):
            a = (esd["wx"], esd["wy"])
            b = (target["wx"], target["wy"]) if not isinstance(target, tuple) else target
            # target may be a pad dict
            if isinstance(target, dict):
                b = (target["wx"], target["wy"])
            opts = _orth_options(a, b)
            span = abs(a[0] - b[0]) + abs(a[1] - b[1])
            if span < 1.0:
                return opts
            for lift in (2.2, 3.4, -2.0):
                y = a[1] + lift
                opts.append(_clean_pts([a, (a[0], y), (b[0], y), b]))
            return opts

        chosen = None
        fallback = None
        for ra, sa, rb, sb in plans:
            ua = front_u(ja, ra, sa)
            ub = front_u(jb, rb, sb)
            if not _path_clear(ua, TRACK, 0, net_a, records, holes, poly, ignore_of(net_a), hits_drawn, hits_via):
                continue
            if not _path_clear(ub, TRACK, 0, net_b, records, holes, poly, ignore_of(net_b), hits_drawn, hits_via):
                continue
            if not _mutual([(ua, TRACK, net_a), (ub, TRACK, net_b)]):
                continue
            if fallback is None:
                fallback = ("front", ua, ub, [])
            dogs = []
            ok = True
            for net, pair, esd in ((net_a, ja, ea[0]), (net_b, jb, eb[0])):
                target = min(pair, key=lambda p: abs(p["wx"] - esd["wx"]) + abs(p["wy"] - esd["wy"]))
                hit = None
                for opt in dog_options(esd, target):
                    if _path_clear(opt, TRACK, 0, net, records, holes, poly, ignore_of(net), hits_drawn, hits_via):
                        hit = _clean_pts(opt)
                        break
                if hit is None:
                    ok = False
                    break
                dogs.append((net, hit))
            if not ok:
                continue
            bundle = [(ua, TRACK, net_a), (ub, TRACK, net_b)] + [(d, TRACK, n) for n, d in dogs]
            if not _mutual(bundle):
                continue
            chosen = ("front", ua, ub, dogs)
            break
        if chosen is None:
            for ra, rb in back_plans:
                vias_a = [(p["wx"], p["wy"] + ra) for p in ja]
                vias_b = [(p["wx"], p["wy"] + rb) for p in jb]
                if any(not router.via_ok(x, y, nid(net_a)) or exact_hit(x, y, VIA_D, records, holes, poly, set()) for x, y in vias_a):
                    continue
                if any(not router.via_ok(x, y, nid(net_b)) or exact_hit(x, y, VIA_D, records, holes, poly, set()) for x, y in vias_b):
                    continue
                stubs_a = [
                    _clean_pts([(p["wx"], p["wy"]), v])
                    for p, v in zip(ja, vias_a)
                ]
                stubs_b = [
                    _clean_pts([(p["wx"], p["wy"]), v])
                    for p, v in zip(jb, vias_b)
                ]
                back_a = _clean_pts([vias_a[0], vias_a[1]])
                back_b = _clean_pts([vias_b[0], vias_b[1]])
                ok = _path_clear(back_a, TRACK, 1, net_a, records, holes, poly, ignore_of(net_a), hits_drawn, hits_via)
                ok = ok and _path_clear(back_b, TRACK, 1, net_b, records, holes, poly, ignore_of(net_b), hits_drawn, hits_via)
                for stub in stubs_a:
                    ok = ok and _path_clear(stub, TRACK, 0, net_a, records, holes, poly, ignore_of(net_a), hits_drawn, hits_via)
                for stub in stubs_b:
                    ok = ok and _path_clear(stub, TRACK, 0, net_b, records, holes, poly, ignore_of(net_b), hits_drawn, hits_via)
                if not ok:
                    continue
                # Dogleg on the front from the ESD pad to the nearer via.
                dogs = []
                for net, vias, esd in ((net_a, vias_a, ea[0]), (net_b, vias_b, eb[0])):
                    target = min(vias, key=lambda v: abs(v[0] - esd["wx"]) + abs(v[1] - esd["wy"]))
                    hit = None
                    for opt in _orth_options((esd["wx"], esd["wy"]), target):
                        if _path_clear(opt, TRACK, 0, net, records, holes, poly, ignore_of(net), hits_drawn, hits_via):
                            hit = _clean_pts(opt)
                            break
                    if hit is None:
                        ok = False
                        break
                    dogs.append((net, hit))
                if not ok:
                    continue
                bundle = (
                    [(back_a, TRACK, net_a), (back_b, TRACK, net_b)]
                    + [(s, TRACK, net_a) for s in stubs_a]
                    + [(s, TRACK, net_b) for s in stubs_b]
                    + [(d, TRACK, n) for n, d in dogs]
                )
                if not _mutual(bundle):
                    continue
                chosen = ("back", stubs_a, stubs_b, back_a, back_b, vias_a, vias_b, dogs)
                break
        if chosen is None:
            chosen = fallback
        if chosen is None:
            print(f"tie failed {jref} {net_a}/{net_b}", flush=True)
            return
        if chosen[0] == "front":
            _tag, ua, ub, dogs = chosen
            draw_pts(net_a, ua, TRACK, 0)
            draw_pts(net_b, ub, TRACK, 0)
            for net, dog in dogs:
                draw_pts(net, dog, TRACK, 0)
        else:
            _tag, stubs_a, stubs_b, back_a, back_b, vias_a, vias_b, dogs = chosen
            for stub in stubs_a:
                draw_pts(net_a, stub, TRACK, 0)
            for stub in stubs_b:
                draw_pts(net_b, stub, TRACK, 0)
            for x, y in vias_a:
                draw_via_at_usb(net_a, x, y)
            for x, y in vias_b:
                draw_via_at_usb(net_b, x, y)
            draw_pts(net_a, back_a, TRACK, 1)
            draw_pts(net_b, back_b, TRACK, 1)
            for net, dog in dogs:
                draw_pts(net, dog, TRACK, 0)
        # A pad-only tie still leaves the ESD device for the maze.
        if chosen[0] == "front":
            linked = bool(chosen[3])
        else:
            linked = bool(chosen[7])
        if linked:
            done.update((net_a, net_b))
        print(f"tie {jref} {net_a}/{net_b} via {chosen[0]} {'full' if linked else 'pads'}", flush=True)

    def draw_via_at_usb(net_name, x, y):
        # Local wrapper: route_usb does not close over draw_via_at. Use the board directly.
        for vx, vy in router.vias:
            if math.hypot(vx - x, vy - y) < 0.05:
                return
        net = board.FindNet(net_name)
        if net is None or net.GetNetCode() <= 0:
            print(f"missing net {net_name}", flush=True)
            return
        add_via(board, net, x, y)
        router.vias.append((x, y))
        router.r.paint_circle(x, y, VIA_D / 2 + CLEAR + 0.04, (0, 1), nid(net_name), "halo")
        router.r.paint_circle(x, y, VIA_D / 2, (0, 1), nid(net_name), "copper")

    # Pair first so the ties route around the 90 ohm geometry.
    install_pair()
    install_ties("J1", "USB_DP_CONN", "USB_DM_CONN", "D1")
    install_ties("J2", "LINK_DP", "LINK_DM", "D2")

    def stub(net):
        pads = copper_pads(net)
        if len(pads) < 2:
            return
        ignore = ignore_of(net)
        # One orthogonal run, front only, between the MCU pin and the resistor.
        a = next((p for p in pads if p["ref"] == "U1"), None)
        b = next((p for p in pads if p["ref"].startswith("R")), None)
        if a is None or b is None:
            return
        for opt in _orth_options((a["wx"], a["wy"]), (b["wx"], b["wy"])):
            if _path_clear(opt, TRACK, 0, net, records, holes, poly, ignore, hits_drawn, hits_via):
                draw_pts(net, opt, TRACK, 0)
                done.add(net)
                return

    stub("USB_DP_MCU")
    stub("USB_DM_MCU")
    return done


def run_reports():
    REPORTS.mkdir(parents=True, exist_ok=True)
    waiver_lines = [
        "# DRC courtyard waivers",
        "",
        "Each line is a KiCad custom rule in the matching project `.kicad_dru`:",
        "`severity exclusion` on `courtyard_clearance`.",
        "The exclusion covers courtyard overlap of parts stacked on purpose",
        "(hotswap sockets at the legacy pitch, a per-key LED or diode on its switch,",
        "the crystal against the RP2040, and decoupling beside the QFN).",
        "Clearance, shorts, unconnected items, and track angles are not waived.",
        "",
        "| Side | A | B | Reason |",
        "| --- | --- | --- | --- |",
    ]
    for side in ("left", "right"):
        project = f"ergodox-rp2040-{side}"
        pair_path = REPORTS / f"{side}-courtyard-pairs.json"
        pairs = json.loads(pair_path.read_text(encoding="utf-8")) if pair_path.exists() else []
        rules = ["(version 1)"]
        n = 0
        for pair in pairs:
            why = pair.get("reason")
            if not why:
                print(f"UNWAIVED overlap {side} {pair['a']} {pair['b']}", flush=True)
                continue
            n += 1
            a, b = pair["a"], pair["b"]
            cond = (
                f"(A.Reference == '{a}' && B.Reference == '{b}') || "
                f"(A.Reference == '{b}' && B.Reference == '{a}')"
            )
            rules.append(
                f'(rule "court_{n}"\n'
                f"  (severity exclusion)\n"
                f"  (constraint courtyard_clearance)\n"
                f'  (condition "{cond}")\n'
                f")"
            )
            waiver_lines.append(f"| {side} | {a} | {b} | {why} |")
        dru = ROOT / side / f"{project}.kicad_dru"
        dru.write_text("\n".join(rules) + "\n", encoding="utf-8")
        print(f"wrote {dru} rules={n}", flush=True)
    (REPORTS / "drc-waivers.md").write_text("\n".join(waiver_lines) + "\n", encoding="utf-8")

    drc_errors = 0
    erc_errors = 0
    for side in ("left", "right"):
        project = f"ergodox-rp2040-{side}"
        pcb = ROOT / side / f"{project}.kicad_pcb"
        sch = ROOT / side / f"{project}.kicad_sch"
        drc_json = REPORTS / f"{side}-drc.json"
        drc_txt = REPORTS / f"{side}-drc.rpt"
        erc_txt = REPORTS / f"{side}-erc.rpt"
        subprocess.run(
            ["kicad-cli", "sch", "erc", "--severity-error", "--severity-warning", "-o", str(erc_txt), str(sch)],
            check=False,
        )
        text = erc_txt.read_text(encoding="utf-8", errors="replace") if erc_txt.exists() else ""
        for line in text.splitlines():
            if "ERC messages" in line and "Errors" in line:
                parts = line.replace("*", " ").split()
                if "Errors" in parts:
                    erc_errors += int(parts[parts.index("Errors") + 1])
        subprocess.run(
            [
                "kicad-cli", "pcb", "drc",
                "--schematic-parity",
                "--severity-error",
                "--refill-zones",
                "--format", "json",
                "-o", str(drc_json),
                str(pcb),
            ],
            check=False,
        )
        subprocess.run(
            [
                "kicad-cli", "pcb", "drc",
                "--schematic-parity",
                "--severity-error",
                "--severity-warning",
                "--format", "report",
                "-o", str(drc_txt),
                str(pcb),
            ],
            check=False,
        )
        n = 0
        detail = ""
        if drc_json.exists():
            data = json.loads(drc_json.read_text(encoding="utf-8"))
            types = {}
            for v in data.get("violations") or []:
                if v.get("excluded"):
                    continue
                if str(v.get("severity", "error")).lower() != "error":
                    continue
                n += 1
                kind = v.get("type") or "?"
                types[kind] = types.get(kind, 0) + 1
            unc = data.get("unconnected_items") or []
            n += len(unc)
            sp = data.get("schematic_parity")
            items = sp if isinstance(sp, list) else (sp or {}).get("violations") or []
            sp_n = 0
            for item in items:
                if isinstance(item, dict) and str(item.get("severity", "error")).lower() == "error" and not item.get("excluded"):
                    sp_n += 1
            n += sp_n
            detail = f" types={types} unconnected={len(unc)} parity={sp_n}"
        drc_errors += n
        print(f"{side} drc errors={n}{detail}", flush=True)
    summary = REPORTS / "drc-summary.txt"
    summary.write_text(f"drc_errors={drc_errors}\nerc_errors={erc_errors}\n", encoding="utf-8")
    print(f"reports drc_errors={drc_errors} erc_errors={erc_errors}", flush=True)
