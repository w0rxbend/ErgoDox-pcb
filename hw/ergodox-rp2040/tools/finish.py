#!/usr/bin/env python3
"""Route the open connections of a board. Run inside the KiCad image.

    finish.py <side> <drc.json>

Reads a KiCad DRC report of the board. Removes every unlocked track or via
named in a violation, then routes each unconnected pair with a grid
search on the two outer layers. A pair that is fenced in may push through
routes laid earlier in the same run: those are taken out and routed again.
Copper that was on the board before the run is never moved.

Run DRC again afterwards: this script does not judge its own work.
"""

import heapq
import json
import math
import re
import sys
from array import array
from pathlib import Path

import pcbnew

from layout_pcb import add_track, add_via

ROOT = Path(__file__).resolve().parents[1]
GRID = 0.05  # mm per cell
BLOCK = 0xFFFF  # cell closed to every net
TRACK = 0.15
VIA_RADIUS = 0.3
CLEARANCE = 0.15
EDGE_CLEARANCE = 0.3
SLACK = 0.02  # covers the grid error of sampling a shape at cell centres
VIA_COST = 40  # cells; a via is worth a 2 mm detour
RIP_COST = 4  # cells; added per cell of an earlier route that a path pushes through.
# Kept low: the search looks at everything cheaper than the push before it pushes.
GREED = 1.5  # weight on the distance estimate; trades path length for speed
MAX_STEPS = 6_000_000
TRIES = 2  # a pair that finds no path goes to the back of the queue this often
MAX_RIPS = 600  # routes taken out in one run before pushing through is switched off
ROOM = 3000  # cells; an end that reaches fewer than this is fenced in
FRONT, BACK, VIA = 0, 1, 2  # sheets; FRONT and BACK are also the two sides
LAYER = {FRONT: pcbnew.F_Cu, BACK: pcbnew.B_Cu}
NAME = {"F.Cu": FRONT, "B.Cu": BACK}


class Grid:
    """What may pass each cell, on three sheets: front tracks, back tracks, via centres.

    fixed: copper and cuts that were on the board before the run. Per cell:
    0 free, a net code when only that net is near, BLOCK otherwise.
    laid: routes of this run. Per cell, the pairs whose copper is near.
    """

    def __init__(self, board):
        box = board.GetBoardEdgesBoundingBox()
        self.x0 = pcbnew.ToMM(box.GetLeft()) - 1.0
        self.y0 = pcbnew.ToMM(box.GetTop()) - 1.0
        self.width = int((pcbnew.ToMM(box.GetWidth()) + 2.0) / GRID) + 1
        self.height = int((pcbnew.ToMM(box.GetHeight()) + 2.0) / GRID) + 1
        size = self.width * self.height
        self.fixed = [array("H", bytes(2 * size)) for _ in (FRONT, BACK, VIA)]
        self.laid = [{} for _ in (FRONT, BACK, VIA)]

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

    def lay(self, sheet, outline, pair):
        marks = self.laid[sheet]
        for i in self.cells(outline):
            owners = marks.get(i, ())
            if pair not in owners:
                marks[i] = owners + (pair,)
                pair.cells.append((sheet, i))

    def lift(self, pair):
        for sheet, i in pair.cells:
            owners = tuple(owner for owner in self.laid[sheet][i] if owner is not pair)
            if owners:
                self.laid[sheet][i] = owners
            else:
                del self.laid[sheet][i]
        pair.cells.clear()


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


def keep_out(item, sides):
    """(sheet, outline) for the cells a track or via of another net may not enter."""
    for side in sides:
        for outline in outlines(item, LAYER[side], CLEARANCE + TRACK / 2 + SLACK):
            yield side, outline
        for outline in outlines(item, LAYER[side], CLEARANCE + VIA_RADIUS + SLACK):
            yield VIA, outline


def fix_cut(grid, outline_for):
    """Close cells near a board edge or hole. outline_for(margin) gives the shapes."""
    for sheet, reach in ((FRONT, TRACK / 2), (BACK, TRACK / 2), (VIA, VIA_RADIUS)):
        for outline in outline_for(EDGE_CLEARANCE + reach + SLACK):
            grid.fix(sheet, outline, BLOCK)


def sides_of(item):
    return [side for side in (FRONT, BACK) if item.IsOnLayer(LAYER[side])]


def load_obstacles(board):
    grid = Grid(board)
    edge_shapes = [g for g in board.GetDrawings() if g.GetLayer() == pcbnew.Edge_Cuts]
    copper = list(board.GetTracks())
    for fp in board.GetFootprints():
        edge_shapes += [g for g in fp.GraphicalItems() if g.GetLayer() == pcbnew.Edge_Cuts]
        for pad in fp.Pads():
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                at = pad.GetPosition()
                radius = pcbnew.ToMM(max(pad.GetDrillSizeX(), pad.GetDrillSizeY())) / 2
                fix_cut(grid, lambda grow, at=at, radius=radius: [
                    circle(pcbnew.ToMM(at.x), pcbnew.ToMM(at.y), radius + grow)])
            else:
                copper.append(pad)
    for shape in edge_shapes:
        fix_cut(grid, lambda grow, shape=shape: outlines(shape, pcbnew.Edge_Cuts, grow))
    for item in copper:
        for sheet, outline in keep_out(item, sides_of(item)):
            grid.fix(sheet, outline, item.GetNetCode() or BLOCK)
    return grid


class Pair:
    """Two ends that a DRC report lists as unconnected, and the route between them."""

    def __init__(self, board, items):
        (name, self.a_mm, self.a_sides), (_, self.b_mm, self.b_sides) = (end_of(item) for item in items)
        self.net = board.FindNet(name)
        self.code = self.net.GetNetCode()
        self.length = math.dist(self.a_mm, self.b_mm)
        self.at_controller = any("of U1 " in item["description"] for item in items)
        self.items = []  # tracks and vias of the route
        self.cells = []  # (sheet, index) this route closes to other nets
        self.rips = 0  # times this route was taken out
        self.tries = 0  # times no path was found

    def ends(self, grid):
        return (*grid.cell(*self.a_mm), self.a_sides), (*grid.cell(*self.b_mm), self.b_sides)


def end_of(item):
    """(net name, position in mm, sides) of one end named in a DRC report."""
    text = item["description"]
    name = re.search(r"\[(.*?)\]", text).group(1)
    sides = (FRONT, BACK) if text.startswith("Via") else tuple(s for label, s in NAME.items() if label in text)
    return name, (item["pos"]["x"], item["pos"]["y"]), sides


def toll(grid, sheet, i, net, push):
    """Price of entering a cell: 0 when free, None when closed.

    With push, a cell held by earlier routes of other nets is open at a price.
    """
    if grid.fixed[sheet][i] not in (0, net):
        return None
    price = 0
    for owner in grid.laid[sheet].get(i, ()):
        if owner.code != net:
            if not push:
                return None
            price += RIP_COST * (1 + owner.rips)
    return price


def moves(grid, net, side, i, push):
    """Cells one move away from (side, i), with the price of each move."""
    width = grid.width
    for step, length in ((1, 1.0), (-1, 1.0), (width, 1.0), (-width, 1.0),
                         (width + 1, 1.4142), (width - 1, 1.4142), (-width + 1, 1.4142), (-width - 1, 1.4142)):
        price = toll(grid, side, i + step, net, push)
        if price is None:
            continue
        if length > 1.0:  # a diagonal may not cut the corner of a closed cell
            across = step - (width if step > 1 else -width)
            corner_a = toll(grid, side, i + across, net, push)
            corner_b = toll(grid, side, i + step - across, net, push)
            if corner_a is None or corner_b is None:
                continue
            price += corner_a + corner_b
        yield side, i + step, length + price
    drill = toll(grid, VIA, i, 0, push)  # a via may not sit beside copper of its own net either
    landing = toll(grid, 1 - side, i, net, push)
    if drill is not None and landing is not None:
        yield 1 - side, i, VIA_COST + drill + landing


def fenced_in(grid, net, end):
    """True when fewer than ROOM cells can be reached from this end."""
    col, row, sides = end
    seen = {(side, row * grid.width + col) for side in sides}
    todo = list(seen)
    while todo and len(seen) < ROOM:
        side, i = todo.pop()
        for key in ((s, j) for s, j, _ in moves(grid, net, side, i, False)):
            if key not in seen:
                seen.add(key)
                todo.append(key)
    return len(seen) < ROOM


def search(grid, net, start, goal, push=False):
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
        for key_side, j, price in moves(grid, net, side, i, push):
            key = (key_side, j)
            if cost + price < best.get(key, math.inf):
                best[key] = cost + price
                came[key] = (side, i)
                heapq.heappush(heap, (cost + price + estimate(j), cost + price, key_side, j))
    return None


def in_the_way(grid, net, path):
    """Earlier routes of other nets that a pushed path runs through."""
    width = grid.width
    found = []
    for (side_a, col_a, row_a), (side_b, col_b, row_b) in zip(path, path[1:]):
        if side_a != side_b:
            spots = [(VIA, row_a * width + col_a), (side_b, row_b * width + col_b)]
        else:  # the cell entered, and both corner cells of a diagonal move
            spots = [(side_b, row_b * width + col_b), (side_b, row_a * width + col_b), (side_b, row_b * width + col_a)]
        for sheet, i in spots:
            for owner in grid.laid[sheet].get(i, ()):
                if owner not in found and (owner.code != net or sheet == VIA):
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


def lay(board, grid, pair, path):
    """Add the path to the board as tracks and vias, and close its cells."""
    points = [(side, grid.centre(col, row)) for side, col, row in corners(path)]
    points = [(points[0][0], pair.a_mm)] + points + [(points[-1][0], pair.b_mm)]
    for (side_a, a), (side_b, b) in zip(points, points[1:]):
        if side_a != side_b:
            item, sides = add_via(board, pair.net, *a), (FRONT, BACK)
        else:
            item, sides = add_track(board, pair.net, LAYER[side_a], a, b, TRACK), (side_a,)
        if item:
            pair.items.append(item)
            for sheet, outline in keep_out(item, sides):
                grid.lay(sheet, outline, pair)


def lift(board, grid, pair):
    for item in pair.items:
        board.Remove(item)
    pair.items.clear()
    grid.lift(pair)
    pair.rips += 1


def route_all(board, grid, pairs):
    """Route every pair. Returns the pairs left open and the number of rip-ups."""
    queue = list(pairs)
    failed = []
    rips = 0
    while queue:
        pair = queue.pop(0)
        start, goal = pair.ends(grid)
        open_ends = not fenced_in(grid, pair.code, start) and not fenced_in(grid, pair.code, goal)
        path = search(grid, pair.code, start, goal) if open_ends else None
        if path is None and rips < MAX_RIPS:
            path = search(grid, pair.code, start, goal, push=True)
            for other in in_the_way(grid, pair.code, path or []):
                lift(board, grid, other)
                queue.append(other)
                rips += 1
        if path is not None:
            lay(board, grid, pair, path)
            continue
        pair.tries += 1
        (queue if pair.tries < TRIES else failed).append(pair)
    return failed, rips


def main(side, report_path):
    path = ROOT / side / f"ergodox-rp2040-{side}.kicad_pcb"
    board = pcbnew.LoadBoard(str(path))
    report = json.loads(Path(report_path).read_text())

    faulty = {item["uuid"] for violation in report["violations"] for item in violation["items"]}
    removed = [track for track in board.GetTracks()
               if track.m_Uuid.AsString() in faulty and not track.IsLocked()]
    for track in removed:
        board.Remove(track)

    pairs = [Pair(board, entry["items"]) for entry in report["unconnected_items"]]
    # Controller pins first, then shortest first: those have the fewest ways out.
    pairs.sort(key=lambda pair: (not pair.at_controller, pair.length))
    failed, rips = route_all(board, load_obstacles(board), pairs)
    pcbnew.SaveBoard(str(path), board)
    names = sorted(pair.net.GetNetname() for pair in failed)
    print(f"{side}: removed {len(removed)} faulty items, routed {len(pairs) - len(names)} "
          f"of {len(pairs)} with {rips} rip-ups, open {names}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
