#!/usr/bin/env python3
"""Route the open connections of a board. Run inside the KiCad image.

    finish.py <side> <drc.json>

Removes every unlocked track or via named in a violation of the DRC report,
then routes each open connection with a grid search on the two outer layers,
and on In2 inside the +3V3 pour round the controller, where the pour flows
round the tracks. In2 costs more, so it carries only what the outer layers
cannot.
Each net gets the track width of its netclass in the project file. A net
whose wide track finds no way through gets a 0.1 mm track instead, and is
named in the summary.
A connection that is fenced in may push through routes of other nets that
this run laid. Pushed routes are taken out and their links go back in the
queue. Copper that was on the board before the run is never moved: pushing
it piece by piece broke more links than it made.

The open links come from the DRC report. Each route remembers the link it
makes, so a route that is taken out puts its link back in the queue.

KiCad's own connectivity is not used: after a few queries its Python objects
stop working.

Run DRC again afterwards: this script does not judge its own work.
"""

import fnmatch
import heapq
import json
import math
import re
import sys
from array import array
from collections import deque
from dataclasses import dataclass, replace
from pathlib import Path

import pcbnew

from layout_pcb import add_track, add_via

ROOT = Path(__file__).resolve().parents[1]
GRID = 0.05  # mm per cell
BLOCK = 0xFFFF  # cell closed to every net
TRACK = 0.10
VIA_RADIUS = 0.3
CLEARANCE = 0.10
EDGE_CLEARANCE = 0.3
SLACK = 0.02  # covers the grid error of sampling a shape at cell centres
VIA_COST = 40  # cells; a via is worth a 2 mm detour
# Cells; added per cell of other copper a path pushes through, times one more
# for each time that net was pushed already. About a 10 mm detour for the
# first crossing. Higher, and the search looks at the whole board first.
RIP_COST = 20
GREED = 1.5  # weight on the distance estimate; trades path length for speed
MAX_STEPS = 8_000_000  # long links across the controller band need several million
VIA_GAP = 12  # cells; two vias of one route stay 0.6 mm apart, for the 0.25 mm hole gap
MAX_RIPS = 600  # pushes in one run; after that, copper in the way stays
TRIES = 3  # times a net may find no path before it is given up
PLANE_VIA_ROOM = 1.1  # mm from a plane via to a router via; a ring of vias would cut it off the plane
PROGRESS = 25  # print a progress line every this many links laid
PASSES = 2  # a second pass routes the links the first gave up before all others
LANE = 1.2  # mm past each controller pad where only that pad's net may run
LANE_HALF = 0.19  # mm; half the 0.4 mm pin pitch, less a hair so lanes never touch
INNER_COST = 3.0  # price per cell of track on In2, against 1 on the outer layers
INNER_POWER_VIA_ROOM = 0.8  # mm from a +3V3 plane via to an In2 track, so the pour still reaches it
FRONT, BACK, INNER, VIA = 0, 1, 2, 3  # sheets; the first three are also the routing layers
SIDES = (FRONT, BACK, INNER)
LAYER = {FRONT: pcbnew.F_Cu, BACK: pcbnew.B_Cu, INNER: pcbnew.In2_Cu}


@dataclass(frozen=True)
class Net:
    """A net as the router sees it.

    reach: cell offsets round a track centre that must be open too, so a track
    wider than TRACK keeps its clearance. (0,) for a TRACK-wide net.
    """

    item: object  # KiCad's net
    code: int
    width: float  # mm
    reach: tuple


class Route:
    """Unlocked tracks and vias of one net that are taken out together.

    links: the ((x, y) mm, sides) end pairs this copper joins. Taking the
    route out leaves exactly these open.
    """

    def __init__(self, code, width, items, links):
        self.code = code
        self.width = width  # mm, of its tracks
        self.items = items
        self.links = links
        self.cells = []  # (sheet, index) this route closes to other nets
        self.inner = False  # True when the route has a track on In2


class Grid:
    """What may pass each cell, on four sheets: tracks on each routing layer, and via centres.

    fixed: pads, locked copper and cuts. Per cell: 0 free, a net code when only
    that net is near, BLOCK otherwise.
    laid: unlocked copper. Per cell, the routes whose copper is near.
    """

    def __init__(self, board):
        box = board.GetBoardEdgesBoundingBox()
        self.x0 = pcbnew.ToMM(box.GetLeft()) - 1.0
        self.y0 = pcbnew.ToMM(box.GetTop()) - 1.0
        self.width = int((pcbnew.ToMM(box.GetWidth()) + 2.0) / GRID) + 1
        self.height = int((pcbnew.ToMM(box.GetHeight()) + 2.0) / GRID) + 1
        size = self.width * self.height
        self.fixed = [array("H", bytes(2 * size)) for _ in (*SIDES, VIA)]
        self.fixed[INNER] = array("H", [BLOCK]) * size  # opened where the +3V3 pour is
        self.laid = [{} for _ in (*SIDES, VIA)]

    def cell(self, x_mm, y_mm):
        return int((x_mm - self.x0) / GRID), int((y_mm - self.y0) / GRID)

    def centre(self, col, row):
        return self.x0 + (col + 0.5) * GRID, self.y0 + (row + 0.5) * GRID

    def cells(self, outline):
        """Indexes of the cells whose centre lies inside the outline (points in mm)."""
        pts = [((x - self.x0) / GRID, (y - self.y0) / GRID) for x, y in outline]
        edges = list(zip(pts, pts[1:] + pts[:1]))
        top = max(0, math.ceil(min(y for _, y in pts) - 0.5))
        bottom = min(self.height - 1, math.floor(max(y for _, y in pts) - 0.5))
        for row in range(top, bottom + 1):
            yc = row + 0.5
            cuts = sorted(x1 + (yc - y1) * (x2 - x1) / (y2 - y1)
                          for (x1, y1), (x2, y2) in edges if (y1 <= yc) != (y2 <= yc))
            for left, right in zip(cuts[::2], cuts[1::2]):
                first = max(0, math.ceil(left - 0.5))
                last = min(self.width - 1, math.floor(right - 0.5))
                yield from range(row * self.width + first, row * self.width + last + 1)

    def fix(self, sheet, outline, net):
        marks = self.fixed[sheet]
        for i in self.cells(outline):
            if marks[i] == 0:
                marks[i] = net
            elif marks[i] != net:
                marks[i] = BLOCK

    def lay(self, sheet, outline, route):
        marks = self.laid[sheet]
        for i in self.cells(outline):
            owners = marks.get(i, ())
            if route not in owners:
                marks[i] = owners + (route,)
                route.cells.append((sheet, i))

    def lift(self, route):
        for sheet, i in route.cells:
            owners = tuple(owner for owner in self.laid[sheet][i] if owner is not route)
            if owners:
                self.laid[sheet][i] = owners
            else:
                del self.laid[sheet][i]
        route.cells.clear()


def outlines(item, layer, grow_mm):
    """The item's shape on a layer, grown by a margin, as lists of mm points."""
    poly = pcbnew.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(poly, layer, pcbnew.FromMM(grow_mm), pcbnew.FromMM(0.005), pcbnew.ERROR_OUTSIDE)
    out = []
    for k in range(poly.OutlineCount()):
        line = poly.Outline(k)
        out.append([(pcbnew.ToMM(line.CPoint(i).x), pcbnew.ToMM(line.CPoint(i).y)) for i in range(line.PointCount())])
    return out


def circle(x, y, radius):
    return [(x + radius * math.cos(a / 16 * math.pi), y + radius * math.sin(a / 16 * math.pi)) for a in range(32)]


def stadium(a, b, radius):
    """Outline of a segment from a to b (mm) grown by radius: two half circles joined."""
    if a == b:
        return circle(*a, radius)
    heading = math.atan2(b[1] - a[1], b[0] - a[0])
    out = []
    for (x, y), turn in ((b, -math.pi / 2), (a, math.pi / 2)):
        out += [(x + radius * math.cos(heading + turn + k * math.pi / 8),
                 y + radius * math.sin(heading + turn + k * math.pi / 8)) for k in range(9)]
    return out


def mm_of(vector):
    return pcbnew.ToMM(vector.x), pcbnew.ToMM(vector.y)


def copper_keep_out(sides, a, b, half_width):
    """(sheet, outline) for a track (a to b) or via (a == b) of the given half width.

    Plain geometry: after a connectivity query, KiCad's Python shape objects stop working.
    """
    for side in sides:
        yield side, stadium(a, b, half_width + CLEARANCE + TRACK / 2 + SLACK)
    yield VIA, stadium(a, b, half_width + CLEARANCE + VIA_RADIUS + SLACK)


def track_keep_out(item):
    if item.GetClass() == "PCB_VIA":
        centre = mm_of(item.GetPosition())
        return copper_keep_out(SIDES, centre, centre, pcbnew.ToMM(item.GetWidth(pcbnew.F_Cu)) / 2)
    return copper_keep_out(sides_of(item), mm_of(item.GetStart()), mm_of(item.GetEnd()),
                           pcbnew.ToMM(item.GetWidth()) / 2)


def sides_of(item):
    return [side for side in SIDES if item.IsOnLayer(LAYER[side])]


def pad_keep_out(item):
    """(sheet, outline) for the cells a track or via of another net may not enter."""
    for side in sides_of(item):
        for outline in outlines(item, LAYER[side], CLEARANCE + TRACK / 2 + SLACK):
            yield side, outline
        for outline in outlines(item, LAYER[side], CLEARANCE + VIA_RADIUS + SLACK):
            yield VIA, outline


def fix_cut(grid, outline_for):
    """Close cells near a board edge or hole. outline_for(margin) gives the shapes."""
    for sheet, reach in ((FRONT, TRACK / 2), (BACK, TRACK / 2), (INNER, TRACK / 2), (VIA, VIA_RADIUS)):
        for outline in outline_for(EDGE_CLEARANCE + reach + SLACK):
            grid.fix(sheet, outline, BLOCK)


def reserve_controller(grid, board):
    """Keep the way out of every controller pin open, and keep vias from under it.

    Routes of other nets used to cross right in front of a pin and wall it in.
    A router via under the package cut the +3V3 plane round the power vias there.
    """
    controller = board.FindFootprintByReference("U1")
    planes = {zone.GetNetCode() for zone in board.Zones()}
    centre = mm_of(controller.GetPosition())
    pads = [pad for pad in controller.Pads() if pad.GetNumber() != "57"]  # 57: the centre pad
    edges = []
    for pad in pads:
        box = pad.GetBoundingBox()
        edges.append((pcbnew.ToMM(box.GetLeft()), pcbnew.ToMM(box.GetTop()),
                      pcbnew.ToMM(box.GetRight()), pcbnew.ToMM(box.GetBottom())))
    left, top = min(e[0] for e in edges), min(e[1] for e in edges)
    right, bottom = max(e[2] for e in edges), max(e[3] for e in edges)
    for i in grid.cells([(left, top), (right, top), (right, bottom), (left, bottom)]):
        grid.fixed[VIA][i] = BLOCK
        grid.fixed[INNER][i] = BLOCK  # the pour under the package feeds its power vias
    for pad, (x0, y0, x1, y1) in zip(pads, edges):
        code = pad.GetNetCode()
        if not code or code in planes:
            continue
        (px, py) = mm_of(pad.GetPosition())
        if abs(px - centre[0]) > abs(py - centre[1]):  # left or right row: the lane runs in x
            near, far = (x1, x1 + LANE) if px > centre[0] else (x0 - LANE, x0)
            lane = [(near, py - LANE_HALF), (far, py - LANE_HALF), (far, py + LANE_HALF), (near, py + LANE_HALF)]
        else:
            near, far = (y1, y1 + LANE) if py > centre[1] else (y0 - LANE, y0)
            lane = [(px - LANE_HALF, near), (px + LANE_HALF, near), (px + LANE_HALF, far), (px - LANE_HALF, far)]
        for i in grid.cells(lane):
            for side in sides_of(pad):
                if grid.fixed[side][i] == 0:
                    grid.fixed[side][i] = code
            grid.fixed[VIA][i] = BLOCK


def open_inner(grid, board):
    """Open In2 for tracks where the +3V3 pour covers it."""
    for zone in board.Zones():
        if zone.GetNetname() != "+3V3" or not zone.IsOnLayer(pcbnew.In2_Cu):
            continue
        outline = zone.Outline().Outline(0)
        points = [mm_of(outline.CPoint(k)) for k in range(outline.PointCount())]
        for i in grid.cells(points):
            grid.fixed[INNER][i] = 0
        return zone.GetNetCode()
    raise SystemExit("no +3V3 zone on In2")


def load(board):
    """The grid of what is on the board: pads, tracks, vias, holes and the edge."""
    grid = Grid(board)
    power = open_inner(grid, board)
    edge_shapes = [g for g in board.GetDrawings() if g.GetLayer() == pcbnew.Edge_Cuts]
    fixed = []
    for fp in board.GetFootprints():
        edge_shapes += [g for g in fp.GraphicalItems() if g.GetLayer() == pcbnew.Edge_Cuts]
        for pad in fp.Pads():
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                at = pad.GetPosition()
                radius = pcbnew.ToMM(max(pad.GetDrillSizeX(), pad.GetDrillSizeY())) / 2
                fix_cut(grid, lambda grow, at=at, radius=radius: [
                    circle(pcbnew.ToMM(at.x), pcbnew.ToMM(at.y), radius + grow)])
            else:
                fixed.append(pad)
    for shape in edge_shapes:
        fix_cut(grid, lambda grow, shape=shape: outlines(shape, pcbnew.Edge_Cuts, grow))
    for item in fixed:
        for sheet, outline in pad_keep_out(item):
            grid.fix(sheet, outline, item.GetNetCode() or BLOCK)
    for track in board.GetTracks():
        for sheet, outline in track_keep_out(track):
            grid.fix(sheet, outline, track.GetNetCode() or BLOCK)
    planes = {zone.GetNetCode() for zone in board.Zones()}
    for track in board.GetTracks():
        if track.GetClass() == "PCB_VIA" and track.GetNetCode() in planes:
            centre = mm_of(track.GetPosition())
            grid.fix(VIA, circle(*centre, PLANE_VIA_ROOM), BLOCK)
            if track.GetNetCode() == power:
                grid.fix(INNER, circle(*centre, INNER_POWER_VIA_ROOM), BLOCK)
    reserve_controller(grid, board)
    return grid


def reach_of(grid, width):
    """Offsets of the cells a track of this width needs open round its centre.

    The fixed cells already keep TRACK / 2 off; the rest of the half width is
    checked here, plus half a cell diagonal for sampling at cell centres.
    """
    if width <= TRACK:
        return (0,)
    radius = ((width - TRACK) / 2 + GRID / math.sqrt(2)) / GRID
    span = int(radius)
    return tuple(dy * grid.width + dx for dy in range(-span, span + 1) for dx in range(-span, span + 1)
                 if dx * dx + dy * dy <= radius * radius)


def toll(grid, sheet, i, net, push, pushed):
    """Price of entering a cell: 0 when free, None when closed.

    With push, a cell held by unlocked copper of other nets is open at a price.
    """
    if grid.fixed[sheet][i] not in (0, net):
        return None
    price = 0
    for owner in grid.laid[sheet].get(i, ()):
        if owner.code != net:
            if not push:
                return None
            price += RIP_COST * (1 + pushed.get(owner.code, 0))
    return price


def toll_around(grid, sheet, i, net, push, pushed):
    """toll for a track centre of this net at cell i: every cell in its reach must be open."""
    if len(net.reach) == 1:
        return toll(grid, sheet, i, net.code, push, pushed)
    price = 0
    for offset in net.reach:
        part = toll(grid, sheet, i + offset, net.code, push, pushed)
        if part is None:
            return None
        price += part
    return price


def moves(grid, net, side, i, push, pushed):
    """Cells one move away from (side, i), with the price of each move."""
    width = grid.width
    for step, length in ((1, 1.0), (-1, 1.0), (width, 1.0), (-width, 1.0),
                         (width + 1, 1.4142), (width - 1, 1.4142), (-width + 1, 1.4142), (-width - 1, 1.4142)):
        price = toll_around(grid, side, i + step, net, push, pushed)
        if price is None:
            continue
        if length > 1.0:  # a diagonal may not cut the corner of a closed cell
            across = step - (width if step > 1 else -width)
            corner_a = toll(grid, side, i + across, net.code, push, pushed)
            corner_b = toll(grid, side, i + step - across, net.code, push, pushed)
            if corner_a is None or corner_b is None:
                continue
            price += corner_a + corner_b
        yield side, i + step, length * (INNER_COST if side == INNER else 1.0) + price
    drill = toll(grid, VIA, i, 0, push, pushed)  # a via may not sit beside copper of its own net either
    if drill is None:
        return
    for other in SIDES:
        landing = toll_around(grid, other, i, net, push, pushed) if other != side else None
        if landing is not None:
            yield other, i, VIA_COST + drill + landing


def search(grid, net, start, goal, push, pushed):
    """Cheapest path of (side, col, row) cells from start to goal, or None.

    start and goal are (col, row, sides). Moves: 8 directions on a layer, or a via.
    """
    width = grid.width
    gx, gy, goal_sides = goal
    goals = {(side, gy * width + gx) for side in goal_sides}

    def estimate(i):
        dx, dy = abs(i % width - gx), abs(i // width - gy)
        return GREED * (max(dx, dy) + 0.4142 * min(dx, dy))

    first = start[1] * width + start[0]
    best = {(side, first): 0.0 for side in start[2]}
    came = {}
    heap = [(estimate(first), 0.0, side, first) for side in start[2]]
    heapq.heapify(heap)
    for _ in range(MAX_STEPS):
        if not heap:
            return None
        _, cost, side, i = heapq.heappop(heap)
        if (side, i) in goals:
            path = [(side, i)]
            while path[-1] in came:
                path.append(came[path[-1]])
            return [(s, j % width, j // width) for s, j in reversed(path)]
        if cost > best[(side, i)]:
            continue
        for key_side, j, price in moves(grid, net, side, i, push, pushed):
            if key_side != side and via_behind(came, (side, i)):
                continue
            key = (key_side, j)
            if cost + price < best.get(key, math.inf):
                best[key] = cost + price
                came[key] = (side, i)
                heapq.heappush(heap, (cost + price + estimate(j), cost + price, key_side, j))
    return None


def via_behind(came, here):
    """True when the path into here changed layer within the last VIA_GAP cells."""
    for _ in range(VIA_GAP):
        before = came.get(here)
        if before is None:
            return False
        if before[0] != here[0]:
            return True
        here = before
    return False


def in_the_way(grid, net, path):
    """Routes that a pushed path runs through: other nets, and any copper beside a new via."""
    width = grid.width
    found = []
    for (side_a, col_a, row_a), (side_b, col_b, row_b) in zip(path, path[1:]):
        entered = row_b * width + col_b
        spots = [(side_b, entered + offset) for offset in net.reach]
        if side_a != side_b:
            spots.append((VIA, row_a * width + col_a))
        else:  # both corner cells of a diagonal move
            spots += [(side_b, row_a * width + col_b), (side_b, row_b * width + col_a)]
        for sheet, i in spots:
            for owner in grid.laid[sheet].get(i, ()):
                if owner not in found and (owner.code != net.code or sheet == VIA):
                    found.append(owner)
    return found


def corners(path):
    """Drop the cells in the middle of a straight run."""
    kept = [path[0]]
    for before, here, after in zip(path, path[1:], path[2:]):
        straight = (here[1] - before[1], here[2] - before[2]) == (after[1] - here[1], after[2] - here[2])
        if here[0] != before[0] or here[0] != after[0] or not straight:
            kept.append(here)
    kept.append(path[-1])
    return kept


def lay(board, grid, net, path, link):
    """Add the path to the board as one route for the link, and close its cells to other nets."""
    route = Route(net.code, net.width, [], [link])
    (start_mm, _), (goal_mm, _) = link
    points = [(side, grid.centre(col, row)) for side, col, row in corners(path)]
    points = [(points[0][0], start_mm)] + points + [(points[-1][0], goal_mm)]
    for (side_a, a), (side_b, b) in zip(points, points[1:]):
        if side_a != side_b:
            item, shape = add_via(board, net.item, *a), copper_keep_out(SIDES, a, a, VIA_RADIUS)
        else:
            item = add_track(board, net.item, LAYER[side_a], a, b, net.width)
            shape = copper_keep_out((side_a,), a, b, net.width / 2)
            route.inner = route.inner or side_a == INNER
        if item:
            route.items.append(item)
            for sheet, outline in shape:
                grid.lay(sheet, outline, route)
    return route


def save(board, path, routes):
    """Save the board. In2 must be a mixed layer once it carries tracks.

    Asks the routes, not the board: by now KiCad's Python objects may have stopped working.
    """
    if any(route.inner for route in routes):
        board.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_MIXED)
    pcbnew.SaveBoard(str(path), board)


def lift(board, grid, route):
    for item in route.items:
        board.Remove(item)
    grid.lift(route)


def find_path(grid, net, link, pushed):
    """(net, path) for the link: at the net's width, else at TRACK. (net, None) when fenced in."""
    (a_mm, a_sides), (b_mm, b_sides) = link
    start, goal = (*grid.cell(*a_mm), a_sides), (*grid.cell(*b_mm), b_sides)
    push = sum(pushed.values()) < MAX_RIPS
    path = search(grid, net, start, goal, push, pushed)
    if path is None and net.width > TRACK:
        net = replace(net, width=TRACK, reach=(0,))
        path = search(grid, net, start, goal, push, pushed)
    return net, path


def route_all(board, grid, links, nets):
    """Route every link, round the queue, putting back the links of pushed routes.

    links: (net code, link) in order. nets: net code to Net. Returns the links
    given up, the number of pushes, and the routes now on the board.
    """
    queue = deque(links)
    failures, pushed = {}, {}
    given_up, alive = [], set()
    laid = 0
    while queue:
        code, link = queue.popleft()
        net, path = find_path(grid, nets[code], link, pushed)
        if path is None:
            (a_mm, _), (b_mm, _) = link
            key = (code, a_mm, b_mm)
            failures[key] = failures.get(key, 0) + 1
            (given_up if failures[key] >= TRIES else queue).append((code, link))
            continue
        for other in in_the_way(grid, net, path):
            lift(board, grid, other)
            alive.discard(other)
            pushed[other.code] = pushed.get(other.code, 0) + 1
            queue.extend((other.code, other_link) for other_link in other.links)
        alive.add(lay(board, grid, net, path, link))
        laid += 1
        if laid % PROGRESS == 0:
            print(f"  {laid} laid, {len(queue)} queued, {sum(pushed.values())} pushes, "
                  f"{len(given_up)} given up", flush=True)
    return given_up, sum(pushed.values()), alive


def class_widths(project_path):
    """Function from net name to the track width (mm) of its netclass in the project file."""
    settings = json.loads(project_path.read_text())["net_settings"]
    width = {netclass["name"]: netclass["track_width"] for netclass in settings["classes"]}
    patterns = [(rule["pattern"], width[rule["netclass"]]) for rule in settings["netclass_patterns"]]
    return lambda name: next((w for pattern, w in patterns if fnmatch.fnmatchcase(name, pattern)), width["Default"])


def end_of(item):
    """(net name, ((x, y) mm, sides)) of one end named in a DRC report."""
    text = item["description"]
    name = re.search(r"\[(.*?)\]", text).group(1)
    sides = SIDES if text.startswith("Via") else tuple(
        side for label, side in (("F.Cu", FRONT), ("B.Cu", BACK), ("In2.Cu", INNER)) if label in text)
    return name, ((item["pos"]["x"], item["pos"]["y"]), sides)


def main(side, report_path):
    path = ROOT / side / f"ergodox-rp2040-{side}.kicad_pcb"
    board = pcbnew.LoadBoard(str(path))
    report = json.loads(Path(report_path).read_text())
    width_of = class_widths(path.with_suffix(".kicad_pro"))  # read before SaveBoard rewrites it
    items = {pad.GetNetname(): pad.GetNet() for pad in board.GetPads()}
    codes = {name: item.GetNetCode() for name, item in items.items()}

    # Copper named in a violation is taken out; DRC reports the links it leaves open next time.
    faulty = {item["uuid"] for violation in report["violations"] for item in violation["items"]}
    bad = [track for track in board.GetTracks() if track.m_Uuid.AsString() in faulty and not track.IsLocked()]
    for track in bad:
        board.Remove(track)
    grid = load(board)
    links = []
    for entry in report["unconnected_items"]:
        (name, a), (_, b) = (end_of(item) for item in entry["items"])
        links.append((codes[name], (a, b)))
    nets = {codes[name]: Net(item, codes[name], width_of(name), reach_of(grid, width_of(name)))
            for name, item in items.items()}
    # Wide nets first, as they need the most room; then controller pins and
    # the shortest links, which have the fewest ways out.
    controller = {pad.GetNetCode() for pad in board.FindFootprintByReference("U1").Pads()}
    links.sort(key=lambda entry: (-nets[entry[0]].width, entry[0] not in controller,
                                  math.dist(entry[1][0][0], entry[1][1][0])))
    best = None
    for attempt in range(PASSES):
        given_up, pushes, alive = route_all(board, grid, links, nets)
        print(f"{side}: pass {attempt + 1}, {len(given_up)} of {len(links)} links open", flush=True)
        if best is None or len(given_up) < len(best[0]):
            narrow = {route.code for route in alive if route.width < nets[route.code].width}
            best = (given_up, pushes, narrow)
            save(board, path, alive)
        if not given_up:
            break
        for route in alive:  # start again from the board as loaded, hard links first
            lift(board, grid, route)
        links = given_up + [entry for entry in links if entry not in given_up]
    given_up, pushes, narrow = best
    names = {code: name for name, code in codes.items()}
    print(f"{side}: took out {len(bad)} faulty items, {len(links)} links to route, "
          f"{pushes} pushes, given up {len(given_up)}: {sorted({names[c] for c, _ in given_up})}, "
          f"at {TRACK} mm instead of the class width: {sorted(names[c] for c in narrow)}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
