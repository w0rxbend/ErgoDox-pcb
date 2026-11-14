#!/usr/bin/env python3
"""Place both ErgoDox RP2040 boards. Routing is done by finish.py.

Switches plug in from the front. Sockets, diodes, LEDs and the controller sit
on the back. Only the two USB-C receptacles and the two buttons are on the
front. The left board mirrors positions, never footprints: a mirrored QFN or
socket is not a real part.
"""

from __future__ import annotations

import math

import pcbnew

from layout_pcb import (
    ROOT,
    add_line,
    add_track,
    add_via,
    add_text,
    apply_design_rules,
    ensure_net,
    iu,
    load_fp,
    load_geo,
    make_npth_fp,
    mm,
    v2,
    verify_plates,
    world,
    xform,
)

POWER = {"GND", "+3V3", "+5V", "+1V1", "LED_5V"}
GAP = 1.0  # courtyard to courtyard: room for three 0.1 mm tracks between parts

# Right-hand frame: ref -> (x, y, rotation, back side).
# USB-C mouth overhangs the top edge (y = 30.48) by 0.5 mm.
ANCHORS = {
    "J1": (137.6553, 33.63, 180, False),
    "J2": (86.4616, 33.63, 180, False),
    "SW_RST": (194.5, 41.45, 0, False),  # legacy reset position
    "SW_BOOT": (186.0, 41.45, 0, False),
    "U1": (152.0, 42.0, 0, True),
    "U3": (127.5, 40.5, 0, True),
    "U5": (97.5, 41.0, 0, True),
    "U4": (158.5, 55.0, 0, True),  # inside the LED_5V pour, beside the controller: short LED_ON
}
# Parts with no signal net of their own: sit beside this pad.
NEAR_PAD = {
    "C9": ("U1", "48"), "C8": ("U1", "50"), "C7": ("U1", "23"), "C3": ("U1", "44"),
    "C4": ("U1", "45"), "C10": ("U1", "1"), "C11": ("U1", "10"), "C12": ("U1", "22"),
    "C13": ("U1", "33"), "C14": ("U1", "42"), "C15": ("U1", "43"),
    "C5": ("U3", "1"), "C6": ("U3", "5"), "C16": ("U2", "8"),
    "D1": ("J1", "A6"), "D2": ("J2", "A6"),
}
FIRST = ["C9", "C8", "C7", "C4", "C3", "C10", "C11", "C12", "C13", "C14", "C15",
         "R10", "R11", "Y1", "C1", "C2", "R2", "U2", "C16", "D1", "D3", "D2", "D4", "C5", "C6"]
# Controller band, right-hand frame. Below Y_SPLIT the inner power layer is LED_5V.
BAND = (69.0, 33.4, 203.0, 50.6)
Y_SPLIT = 51.6
# Key cell, switch-local top view (x right, y down), parts on the back.
DIODE_AT = (-5.2, 1.85)
LED_AT = (0.0, 5.08)
DIODE_VIA_OUT = 1.3  # cathode pad centre to its via, on a diode that is not square to the grid
LED_VIA_OUT = 1.4  # pad centre to plane via, along the LED long axis
ROW_STUB_ENDS = ((5.842, -7.3), (4.2, -7.3))  # switch-local ends of the row stub, above socket pad 2
SCREW_KEEP = 4.5  # mounting hole centre to the nearest fixed via
PLANE_NETS = {"GND", "+3V3", "LED_5V"}
# Fixed copper keeps this gap. It must exceed the clearance the router is given
# (0.10 + 0.02 mm in finish.py), or the router sees violations and gives up nearby.
ROUTER_GAP = 0.19
U1_VIA_RING = 2.35
U1_ELBOW = 2.7  # inside the pin row, whose pads end 3.0 mm from the centre  # plane vias under U1 sit this far from its centre
U1_ESCAPE = 1.0  # band round the package kept free of parts, so every pin can leave
U1_MOAT = 7.0  # half-width kept free of late parts around U1, for pin escape
# Cells turned 180 degrees so a socket pad clears a mounting hole. The plate
# cutout is square, so the switch goes in turned as well.
TURNED = {"right": {"SW0:12"}, "left": set()}
# The reverse-mount LED footprint puts its pads 0.25 mm from its own cutout, and a
# track entering such a pad ends up 0.18 mm from it. Everywhere else the limit is 0.3 mm.
DRU = """(version 1)
(rule "led_cutout"
  (condition "A.Reference == 'DS*'")
  (constraint edge_clearance (min 0.18mm))
)
"""


def put(fp, x, y, rot, back):
    fp.SetPosition(v2(x, y))
    if back and not fp.IsFlipped():
        fp.Flip(v2(x, y), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    # KiCad mirrors a back footprint top-to-bottom; +180 makes it a left-right mirror.
    fp.SetOrientationDegrees(rot + 180 if back else rot)


def box(fp):
    """Courtyard box in mm; pads when the footprint has no courtyard."""
    fp.BuildCourtyardCaches()
    poly = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd)
    bb = poly.BBox() if poly.OutlineCount() else fp.GetBoundingBox(False)
    return (mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom()))


def hit(a, b, gap):
    return a[0] < b[2] + gap and b[0] < a[2] + gap and a[1] < b[3] + gap and b[1] < a[3] + gap


def side_rect(rect, side):
    (x0, y0), (x1, y1) = xform(rect[0], rect[1], side), xform(rect[2], rect[3], side)
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def spiral(cx, cy, step=0.25, reach=26.0):
    yield cx, cy
    for ring in range(1, int(reach / step)):
        r = ring * step
        for i in range(-ring, ring):
            t = i * step
            yield cx + t, cy - r
            yield cx + r, cy + t
            yield cx - t, cy + r
            yield cx - r, cy - t


class Placer:
    def __init__(self, board, sheet, side, project):
        self.board, self.side, self.project = board, side, project
        self.parts = {p["ref"]: p for p in sheet.parts}
        self.nets = {}
        self.fps = {}
        self.occ = {True: [], False: []}  # back?, list of boxes
        self.both = []  # drills and holes block both sides
        self.pads_on = {}  # net -> [(x, y)] of placed pads
        self.band = side_rect(BAND, side)

    def net_of(self, part, num):
        got = part["assign"].get(num)
        return None if not got or got[0] == "nc" else got[1]

    def make(self, ref):
        part = self.parts[ref]
        fp = load_fp(part["footprint"])
        fp.SetReference(ref)
        fp.SetValue(part["value"])
        fp.SetPath(pcbnew.KIID_PATH("/" + part["uuid"]))
        fp.SetSheetfile(f"{self.project}.kicad_sch")
        fp.SetSheetname("Root")
        for pad in fp.Pads():
            net = self.net_of(part, pad.GetNumber())
            if net:
                pad.SetNet(ensure_net(self.board, self.nets, net))
        fp.Value().SetVisible(False)
        fp.Reference().SetTextSize(v2(0.7, 0.7))
        fp.Reference().SetTextThickness(iu(0.1))
        self.board.Add(fp)  # Flip needs the board
        return fp

    def commit(self, ref, fp, back, keep=None):
        self.fps[ref] = fp
        self.occ[back].append(keep or box(fp))
        part = self.parts[ref]
        for pad in fp.Pads():
            p = pad.GetPosition()
            if pad.GetDrillSizeX():
                r = mm(max(pad.GetSizeX(), pad.GetSizeY())) / 2
                self.both.append((mm(p.x) - r, mm(p.y) - r, mm(p.x) + r, mm(p.y) + r))
            net = self.net_of(part, pad.GetNumber())
            if net:
                self.pads_on.setdefault(net, []).append((mm(p.x), mm(p.y)))

    def fixed(self, ref, x, y, rot, back, keep=None):
        fp = self.make(ref)
        put(fp, x, y, rot, back)
        self.commit(ref, fp, back, keep)

    def targets(self, ref):
        """[(pad number, [points it wants to be near])] from already placed parts."""
        part = self.parts[ref]
        if ref in NEAR_PAD:
            aref, anum = NEAR_PAD[ref]
            if aref not in self.fps:
                return []
            spot = next(p.GetPosition() for p in self.fps[aref].Pads() if p.GetNumber() == anum)
            mine = next(n for n in part["assign"] if self.net_of(part, n) == self.net_of(self.parts[aref], anum))
            return [(mine, [(mm(spot.x), mm(spot.y))])]
        out = []
        for num in part["assign"]:
            net = self.net_of(part, num)
            if net and net not in POWER and net in self.pads_on:
                out.append((num, self.pads_on[net]))
        # The net with the fewest pads is the most local one; it decides the site.
        out.sort(key=lambda t: len(t[1]))
        return out

    def auto(self, ref):
        want = self.targets(ref)
        if not want:
            return False
        fp = self.make(ref)
        shapes = []  # per rotation: courtyard box and pad offsets, relative to the origin
        for rot in (0, 90, 180, 270):
            put(fp, 0, 0, rot, True)
            pads = {p.GetNumber(): (mm(p.GetPosition().x), mm(p.GetPosition().y)) for p in fp.Pads()}
            shapes.append((rot, box(fp), pads))
        cx, cy = want[0][1][0]
        best = None
        found = 0
        for x, y in spiral(cx, cy):
            for rot, b, pads in shapes:
                me = (b[0] + x, b[1] + y, b[2] + x, b[3] + y)
                if me[0] < self.band[0] or me[1] < self.band[1] or me[2] > self.band[2] or me[3] > self.band[3]:
                    continue
                if any(hit(me, o, GAP) for o in self.occ[True]) or any(hit(me, o, 0.3) for o in self.both):
                    continue
                cost = 0.0
                for num, pts in want:
                    px, py = pads[num][0] + x, pads[num][1] + y
                    cost += min(math.hypot(px - qx, py - qy) for qx, qy in pts)
                found += 1
                if best is None or cost < best[0]:
                    best = (cost, x, y, rot)
            if found >= 60:
                break
        if best is None:
            raise RuntimeError(f"no site for {ref} on {self.side}")
        put(fp, best[1], best[2], best[3], True)
        self.commit(ref, fp, True)
        return True


def add_zone(board, net, layer, pts):
    # AddArea keeps ownership in the board. A Python-built ZONE crashes SaveBoard.
    zone = board.AddArea(None, net.GetNetCode(), layer, v2(*pts[0]), pcbnew.ZONE_BORDER_DISPLAY_STYLE_DIAGONAL_EDGE)
    for pt in pts[1:]:
        zone.AppendCorner(v2(*pt), -1)
    zone.SetNet(net)
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    zone.SetMinThickness(iu(0.2))
    zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)


def snapped(a, b):
    """Point b moved so that a-b runs at a multiple of 45 degrees, same length.

    The router does not pick up a fixed stub that lies at any other angle,
    which is every stub in the thumb cluster.
    """
    angle = round(math.atan2(b[1] - a[1], b[0] - a[0]) / (math.pi / 4)) * (math.pi / 4)
    length = math.dist(a, b)
    return (a[0] + length * math.cos(angle), a[1] + length * math.sin(angle))


def led_vias(board, led, rot):
    """A via beside each LED pad: supply pads reach the planes, and the router
    gets a round target for the data pads, which it cannot reach on a rotated LED."""
    centre = led.GetPosition()
    ux, uy = world(0, 0, rot, 1, 0)  # LED long axis
    for pad in led.Pads():
        if not pad.GetNetname():
            continue  # the last LED has no data output
        px, py = mm(pad.GetPosition().x), mm(pad.GetPosition().y)
        out = 1 if (px - mm(centre.x)) * ux + (py - mm(centre.y)) * uy > 0 else -1
        vx, vy = snapped((px, py), (px + out * LED_VIA_OUT * ux, py + out * LED_VIA_OUT * uy))
        for item in (add_track(board, pad.GetNet(), pcbnew.B_Cu, (px, py), (vx, vy), 0.4),
                     add_via(board, pad.GetNet(), vx, vy)):
            item.SetLocked(True)  # locked copper is exported as fixed, so the router keeps it


def chain_turn(placer, ref, rot, led_at):
    """0 or 180: the turn that points this LED's data output at the next LED.

    The router fails on a link that has to run round its own LED, so every LED
    faces down the chain. The cutout is symmetric, so either way fits.
    """
    index = int(ref[2:])
    part = placer.parts[ref]
    out_net, in_net = f"LED_{index}", f"LED_{index - 1}"
    ahead, behind = led_at.get(f"DS{index + 1}"), led_at.get(f"DS{index - 1}")
    probe = load_fp(part["footprint"])
    placer.board.Add(probe)  # Flip needs the board
    put(probe, *led_at[ref], rot, True)
    cost = 0.0  # positive when the pads face the wrong way
    for pad in probe.Pads():
        net = placer.net_of(part, pad.GetNumber())
        target = ahead if net == out_net else behind if net == in_net else None
        if target:
            here = (mm(pad.GetPosition().x), mm(pad.GetPosition().y))
            mirrored = (2 * led_at[ref][0] - here[0], 2 * led_at[ref][1] - here[1])
            cost += math.dist(here, target) - math.dist(mirrored, target)
    placer.board.Remove(probe)
    return 180 if cost > 0 else 0


def fixed_track(board, net, a, b, width):
    track = add_track(board, net, pcbnew.B_Cu, a, b, width)
    if track:
        track.SetLocked(True)


def cell_tracks(board, socket, diode, cx, cy, rot, holes):
    """Fixed copper inside a key cell. The router cannot reach a rotated socket pad."""
    pads = {p.GetNumber(): p for p in socket.Pads() if p.GetNumber()}
    at = lambda pad: (mm(pad.GetPosition().x), mm(pad.GetPosition().y))
    anode = next(p for p in diode.Pads() if p.GetNumber() == "2")
    fixed_track(board, pads["1"].GetNet(), at(pads["1"]), at(anode), 0.25)
    # Row pad: a stub to open board above the socket, for the router to pick up.
    # First end that stays out of the screw-head area of every mounting hole.
    end = next(e for e in (snapped(at(pads["2"]), world(cx, cy, rot, *local)) for local in ROW_STUB_ENDS)
               if all(math.hypot(e[0] - hx, e[1] - hy) > SCREW_KEEP for hx, hy in holes))
    fixed_track(board, pads["2"].GetNet(), at(pads["2"]), end, 0.25)
    add_via(board, pads["2"].GetNet(), *end).SetLocked(True)
    if rot % 90:  # same for the column pad of a turned diode: a via past its end
        cathode = next(p for p in diode.Pads() if p.GetNumber() == "1")
        (ax, ay), (kx, ky) = at(anode), at(cathode)
        reach = DIODE_VIA_OUT / math.dist((ax, ay), (kx, ky))
        end = snapped((kx, ky), (kx + (kx - ax) * reach, ky + (ky - ay) * reach))
        fixed_track(board, cathode.GetNet(), (kx, ky), end, 0.25)
        add_via(board, cathode.GetNet(), *end).SetLocked(True)


def pad_box(pad, grow=0.0):
    bb = pad.GetBoundingBox()
    return (mm(bb.GetLeft()) - grow, mm(bb.GetTop()) - grow, mm(bb.GetRight()) + grow, mm(bb.GetBottom()) + grow)


def plane_vias(board):
    """Give every SMD pad on a plane net a via. The router does not connect planes."""
    pads = [pad for fp in board.GetFootprints() for pad in fp.Pads()]
    vias = [(mm(t.GetPosition().x), mm(t.GetPosition().y), t.GetNetname())
            for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    u1 = board.FindFootprintByReference("U1").GetPosition()
    u1x, u1y = mm(u1.x), mm(u1.y)

    def clear(x, y, half, net, own, copper_gap=ROUTER_GAP):
        me = (x - half, y - half, x + half, y + half)
        for pad in pads:
            if pad.GetNetname() == net and not pad.GetDrillSizeX():
                if half < 0.3:
                    continue  # a stub may cross copper of its own net
                gap = ROUTER_GAP  # the router wants a via clear of every SMD pad, same net or not
            else:
                gap = 0.25 if pad.GetDrillSizeX() else copper_gap
            if hit(me, pad_box(pad), gap):
                return False
        return True

    def stub_clear(a, b, net):
        steps = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) / 0.1))
        return all(clear(a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps, 0.1, net, None)
                   for i in range(steps + 1))

    def candidates(pad, px, py):
        fp = pad.GetParentFootprint()
        if fp.GetReference() == "U1":  # under the package, between the pin row and the centre pad
            dx, dy = px - u1x, py - u1y
            # Corner pins slide toward the middle of their row. The stub first runs
            # straight in past the pin row, then turns, so it clears the next pin.
            for slide in (0.0, 0.1, 0.2, 0.3):
                if abs(dx) > abs(dy):
                    yield (u1x + math.copysign(U1_VIA_RING, dx), py - math.copysign(slide, dy),
                           (u1x + math.copysign(U1_ELBOW, dx), py))
                else:
                    yield (px - math.copysign(slide, dx), u1y + math.copysign(U1_VIA_RING, dy),
                           (px, u1y + math.copysign(U1_ELBOW, dy)))
            return
        cx, cy = mm(fp.GetPosition().x), mm(fp.GetPosition().y)
        away = math.atan2(py - cy, px - cx)
        for dist in (0.7, 0.9, 1.1, 1.4, 1.8, 2.3, 3.0):
            for turn in (0, 45, -45, 90, -90, 135, -135, 180):
                angle = round(math.degrees(away) / 45) * 45 + turn
                yield px + dist * math.cos(math.radians(angle)), py + dist * math.sin(math.radians(angle)), None

    missed = []
    for pad in pads:
        net = pad.GetNetname()
        ref = pad.GetParentFootprint().GetReference()
        centre_pad = ref == "U1" and pad.GetNumber() == "57"  # has its own thermal vias
        if net not in PLANE_NETS or pad.GetDrillSizeX() or ref.startswith("DS") or centre_pad:
            continue
        px, py = mm(pad.GetPosition().x), mm(pad.GetPosition().y)
        def path_clear(path):
            return all(stub_clear(a, b, net) for a, b in zip(path, path[1:]))

        path, new_via = None, False
        elbow = next(candidates(pad, px, py))[2]  # same first leg as a new via would use
        for vx, vy, vnet in vias:  # share a via that is already beside the pad
            route = [(px, py)] + ([elbow] if elbow else []) + [(vx, vy)]
            if vnet == net and math.hypot(vx - px, vy - py) < 1.3 and path_clear(route):
                path = route
                break
        if path is None:
            for vx, vy, elbow in candidates(pad, px, py):
                route = [(px, py)] + ([elbow] if elbow else []) + [(vx, vy)]
                near = [math.hypot(vx - ox, vy - oy) for ox, oy, _ in vias]
                if all(d >= 0.9 for d in near) and clear(vx, vy, 0.3, net, pad) and path_clear(route):
                    path, new_via = route, True
                    break
        if path is None:
            missed.append(f"{ref}.{pad.GetNumber()}")
            continue
        layer = pcbnew.B_Cu if pad.IsOnLayer(pcbnew.B_Cu) else pcbnew.F_Cu
        for a, b in zip(path, path[1:]):
            track = add_track(board, pad.GetNet(), layer, a, b, 0.2)
            if track:
                track.SetLocked(True)
        if new_via:
            add_via(board, pad.GetNet(), *path[-1]).SetLocked(True)
            vias.append((*path[-1], net))
    if missed:
        print(f"no plane via for {missed}", flush=True)


def build_pcb(sheet, side, project):
    geo = load_geo()
    if side == "right":
        verify_plates(geo)
    board = pcbnew.BOARD()
    apply_design_rules(board)
    placer = Placer(board, sheet, side, project)
    mirror = -1 if side == "left" else 1

    # Outline. The legacy TRRS notch (y = 31.75) is filled so the LINK
    # receptacle has board under its whole mouth.
    outline = []
    for seg in geo["edge_cuts"]["segments"]:
        a, b = seg["start_mm"], seg["end_mm"]
        if a[1] == 31.75 or b[1] == 31.75:
            continue
        outline.append((a, b))
    outline.append(([88.7095, 30.48], [84.2137, 30.48]))
    for a, b in outline:
        add_line(board, pcbnew.Edge_Cuts, xform(*a, side), xform(*b, side), 0.1)

    screw_holes = []
    for i, hole in enumerate(geo["mounting_holes"], start=1):
        hx, hy = xform(hole["x_mm"], hole["y_mm"], side)
        screw_holes.append((hx, hy))
        make_npth_fp(board, f"H{i}", hx, hy, 0, [(0, 0, hole["drill_diameter_mm"])])
        placer.both.append((hx - SCREW_KEEP, hy - SCREW_KEEP, hx + SCREW_KEEP, hy + SCREW_KEEP))
    for stab in geo["stabilizers"]:
        sx, sy = xform(stab["x_mm"], stab["y_mm"], side)
        holes = [(mirror * h["local_x_mm"], h["local_y_mm"], h["drill_diameter_mm"]) for h in stab["holes"]]
        make_npth_fp(board, stab["reference"], sx, sy, mirror * stab["rotation_deg"], holes)

    # Key cells.
    switches = {s["reference"]: s for s in geo["switches"]}
    by_legacy = {}
    for part in sheet.parts:
        legacy = part["fields"].get("Legacy")
        if legacy:
            by_legacy.setdefault(legacy, {})[part["ref"][:2]] = part["ref"]

    def cell_frame(legacy):
        sw = switches[legacy]
        rot = mirror * sw["rotation_deg"] + (180 if legacy in TURNED[side] else 0)
        return (*xform(sw["x_mm"], sw["y_mm"], side), rot)

    led_at = {refs["DS"]: world(*cell_frame(legacy), *LED_AT) for legacy, refs in by_legacy.items()}
    for legacy, refs in by_legacy.items():
        cx, cy, rot = cell_frame(legacy)
        cell = (cx - 7.6, cy - 7.6, cx + 7.6, cy + 7.6)
        placer.fixed(refs["SW"], cx, cy, rot, True, keep=cell)
        dref = next(r for k, r in refs.items() if k[0] == "D" and k != "DS")
        placer.fixed(dref, *world(cx, cy, rot, *DIODE_AT), rot, True, keep=cell)
        led_rot = rot + chain_turn(placer, refs["DS"], rot, led_at)
        placer.fixed(refs["DS"], *led_at[refs["DS"]], led_rot, True, keep=cell)
        led_vias(board, placer.fps[refs["DS"]], led_rot)
        cell_tracks(board, placer.fps[refs["SW"]], placer.fps[dref], cx, cy, rot, screw_holes)

    for ref, (x, y, rot, back) in ANCHORS.items():
        placer.fixed(ref, *xform(x, y, side), mirror * rot, back)
    b = box(placer.fps["U1"])
    placer.occ[True].append((b[0] - U1_ESCAPE, b[1] - U1_ESCAPE, b[2] + U1_ESCAPE, b[3] + U1_ESCAPE))
    for ref in ("J1", "J2"):  # keep the back clear under the pad row for fan-out vias
        b = box(placer.fps[ref])
        placer.both.append((b[0], b[1], b[2], b[3] + 2.0))

    def place_all(todo):
        while todo:
            ref = next((r for r in todo if placer.auto(r)), None)
            if ref is None:
                raise RuntimeError(f"nothing to anchor {todo} to on {side}")
            todo.remove(ref)

    first = [r for r in FIRST if r in placer.parts]
    place_all(list(first))
    ux, uy = mm(placer.fps["U1"].GetPosition().x), mm(placer.fps["U1"].GetPosition().y)
    placer.occ[True].append((ux - U1_MOAT, uy - U1_MOAT, ux + U1_MOAT, uy + U1_MOAT))
    place_all([r for r in placer.parts if r not in placer.fps])
    plane_vias(board)

    # Inner layers: L2 solid GND, L3 +3V3 under the controller and LED_5V under the keys.
    xs = [xform(*a, side)[0] for a, _ in outline]
    ys = [xform(*a, side)[1] for a, _ in outline]
    x0, x1, y0, y1 = min(xs) - 1, max(xs) + 1, min(ys) - 1, max(ys) + 1
    ysplit = xform(0, Y_SPLIT, side)[1]
    net = lambda name: ensure_net(board, placer.nets, name)
    add_zone(board, net("GND"), pcbnew.In1_Cu, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
    add_zone(board, net("+3V3"), pcbnew.In2_Cu, [(x0, y0), (x1, y0), (x1, ysplit - 0.3), (x0, ysplit - 0.3)])
    add_zone(board, net("LED_5V"), pcbnew.In2_Cu, [(x0, ysplit + 0.3), (x1, ysplit + 0.3), (x1, y1), (x0, y1)])
    board.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)
    board.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_MIXED)  # finish.py runs a few tracks in the +3V3 pour

    hand = side.upper()
    for text, x, y, size in (
        (f"ErgoDox RP2040 {hand}", 128.0, 148.5, 1.4),
        ("HOST", 137.66, 40.0, 1.2),
        ("LINK", 86.46, 40.0, 1.2),
        ("NOT A PC PORT", 86.46, 42.0, 1.0),
        ("RST", 194.5, 45.6, 1.0),
        ("BOOT", 186.0, 45.6, 1.0),
    ):
        add_text(board, text, *xform(x, y, side), size=size)
    board.GetTitleBlock().SetTitle(f"ErgoDox RP2040 {hand}")

    path = ROOT / side / f"{project}.kicad_pcb"
    path.with_suffix(".kicad_dru").write_text(DRU, encoding="utf-8")
    pcbnew.SaveBoard(str(path), board)
    print(f"placed {side}: {len(placer.fps)} footprints -> {path}", flush=True)
    return path
