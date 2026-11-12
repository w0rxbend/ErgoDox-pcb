#!/usr/bin/env python3
"""Generate the left and right ErgoDox RP2040 KiCad 10 schematics.

One circuit. The only intentional differences are the LINK D+/D- UART swap
and the GPIO19 board-id strap (left pulldown, right pullup).
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYMBOL_DIR = Path("/usr/share/kicad/symbols")
DEMO_PRO = Path("/usr/share/kicad/demos/tiny_tapeout/tinytapeout-demo.kicad_pro")

# File Y is up. KiCad's placed symbol mirrors local +Y, so a local pin
# (px, py) lands at (sx + px, sy - py) for rotation 0. Verified by ERC.
Y_SIGN = -1
STUB = 5.08
GRID = 1.27

# LCSC codes copied from notes/parts.md and DESIGN.md, which cite the
# JLCPCB part pages. Values with no code in those files stay blank.
LCSC = {
    "RP2040": "C2040",
    "W25Q128JVSIQ": "C97521",
    "AP2112K-3.3TRG1": "C51118",
    "TPS22917DBVT": "C2680344",
    "TYPE-C-31-M-12": "C165948",
    "USBLC6-2SC6": "C7519",
    "SS14": "C2480",
    "1N4148W": "C81598",
    "SK6812MINI-E": "C5149201",
    "CPG151101S11-16": "C41430893",
    "TS-1187A-B-A-B": "C318884",
    "ABM8-272-T3": "C20625731",
    "15pF": "C1548",
    "1uF": "C52923",
    "100nF": "C1525",
    "1k": "C11702",
    "5.1k": "C25905",
    "10k": "C25744",
    "27": "C25100",
    "2N7002": "C8545",
    "MMBFJ177LT1G": "C106763",
}

# Legacy matrix. Cathode of each per-socket diode is the column.
# Chain index is the SK6812 order in DESIGN.md section 11.
KEYS = [
    ("SW0:7", "ROW0", "COL6", 1),
    ("SW0:8", "ROW0", "COL5", 4),
    ("SW0:9", "ROW0", "COL4", 2),
    ("SW0:10", "ROW0", "COL10", 6),
    ("SW0:11", "ROW0", "COL11", 5),
    ("SW0:12", "ROW0", "COL1", 3),
    ("SW1:9", "ROW1", "COL4", 11),
    ("SW1:10", "ROW1", "COL10", 10),
    ("SW1:11", "ROW1", "COL11", 9),
    ("SW1:12", "ROW1", "COL1", 8),
    ("SW1:13", "ROW1", "COL0", 7),
    ("SW2:7", "ROW2", "COL6", 12),
    ("SW2:8", "ROW2", "COL5", 13),
    ("SW2:9", "ROW2", "COL4", 14),
    ("SW2:10", "ROW2", "COL10", 15),
    ("SW2:11", "ROW2", "COL11", 16),
    ("SW2:12", "ROW2", "COL1", 17),
    ("SW2:13", "ROW2", "COL0", 18),
    ("SW3:8", "ROW3", "COL5", 24),
    ("SW3:9", "ROW3", "COL4", 23),
    ("SW3:10", "ROW3", "COL10", 22),
    ("SW3:11", "ROW3", "COL11", 21),
    ("SW3:12", "ROW3", "COL1", 20),
    ("SW3:13", "ROW3", "COL0", 19),
    ("SW4:7", "ROW4", "COL6", 25),
    ("SW4:8", "ROW4", "COL5", 26),
    ("SW4:9", "ROW4", "COL4", 27),
    ("SW4:10", "ROW4", "COL10", 28),
    ("SW4:11", "ROW4", "COL11", 29),
    ("SW4:12", "ROW4", "COL1", 30),
    ("SW4:13", "ROW4", "COL0", 31),
    ("SW5:7", "ROW5", "COL6", 38),
    ("SW5:8", "ROW5", "COL5", 37),
    ("SW5:9", "ROW5", "COL4", 36),
    ("SW5:10", "ROW5", "COL10", 35),
    ("SW5:11", "ROW5", "COL11", 34),
    ("SW5:12", "ROW5", "COL1", 33),
    ("SW5:13", "ROW5", "COL0", 32),
]

ROWS = {
    "ROW0": "8",
    "ROW1": "9",
    "ROW2": "11",
    "ROW3": "12",
    "ROW4": "13",
    "ROW5": "14",
}
COLS = {
    "COL0": "15",
    "COL1": "16",
    "COL4": "17",
    "COL5": "18",
    "COL6": "27",
    "COL10": "28",
    "COL11": "29",
}


def fmt(n: float) -> str:
    v = round(float(n), 4)
    if abs(v) < 5e-5:
        v = 0.0
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def esc(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace('"', '\\"')


def uid() -> str:
    return str(uuid.uuid4())


def parse_sexpr(text: str):
    tokens = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c in "()":
            tokens.append(c)
            i += 1
            continue
        if c == '"':
            i += 1
            buf = []
            while i < n:
                if text[i] == "\\":
                    buf.append(text[i + 1])
                    i += 2
                    continue
                if text[i] == '"':
                    i += 1
                    break
                buf.append(text[i])
                i += 1
            tokens.append('"' + "".join(buf).replace("\\", "\\\\").replace('"', '\\"') + '"')
            continue
        j = i
        while i < n and not text[i].isspace() and text[i] not in "()":
            i += 1
        tokens.append(text[j:i])

    def rec(idx):
        if tokens[idx] != "(":
            return tokens[idx], idx + 1
        idx += 1
        items = []
        while tokens[idx] != ")":
            item, idx = rec(idx)
            items.append(item)
        return items, idx + 1

    tree, _ = rec(0)
    return tree


def unquote(atom) -> str:
    if not isinstance(atom, str):
        return ""
    if len(atom) >= 2 and atom[0] == '"' and atom[-1] == '"':
        return atom[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return atom


def dump(node, indent=0) -> str:
    if isinstance(node, str):
        return node
    pad = "\t" * indent
    if all(isinstance(c, str) for c in node):
        return pad + "(" + " ".join(node) + ")"
    lines = [pad + "(" + (node[0] if node and isinstance(node[0], str) else "")]
    start = 1 if node and isinstance(node[0], str) else 0
    if start == 0:
        lines = [pad + "("]
    for child in node[start:]:
        lines.append(dump(child, indent + 1))
    lines.append(pad + ")")
    return "\n".join(lines)


class Lib:
    def __init__(self):
        self.files = {}
        self.symbols = {}  # (lib, name) -> tree with lib-id name

    def load_file(self, filename: str):
        if filename in self.files:
            return self.files[filename]
        path = SYMBOL_DIR / filename
        tree = parse_sexpr(path.read_text(encoding="utf-8", errors="replace"))
        tops = {}
        for child in tree[1:]:
            if isinstance(child, list) and child and child[0] == "symbol":
                tops[unquote(child[1])] = child
        self.files[filename] = tops
        return tops

    def _flatten(self, tops, name, seen):
        if name in seen:
            raise RuntimeError(f"extends cycle at {name}")
        seen.add(name)
        if name not in tops:
            raise KeyError(name)
        node = tops[name]
        extends = None
        for child in node[1:]:
            if isinstance(child, list) and child and child[0] == "extends":
                extends = unquote(child[1])
        if not extends:
            return node
        parent = self._flatten(tops, extends, seen)
        import copy

        child = copy.deepcopy(node)
        child[:] = [c for c in child if not (isinstance(c, list) and c and c[0] == "extends")]
        child_has_unit = any(
            isinstance(c, list) and c and c[0] == "symbol" for c in child[1:]
        )
        if not child_has_unit:
            for c in parent[1:]:
                if isinstance(c, list) and c and c[0] == "symbol":
                    unit = copy.deepcopy(c)
                    old = unquote(unit[1])
                    if old == extends or old.startswith(extends + "_"):
                        unit[1] = '"' + name + old[len(extends) :] + '"'
                    child.append(unit)
        have = {c[0] for c in child[1:] if isinstance(c, list) and c}
        for key in ("pin_names", "pin_numbers"):
            if key not in have:
                for c in parent[1:]:
                    if isinstance(c, list) and c and c[0] == key:
                        child.append(copy.deepcopy(c))
        # Derived symbols keep parent fields they do not override. 1N4148W
        # inherits Sim.Device and Sim.Pins from 1N4001; without them KiCad
        # reports lib_symbol_mismatch.
        def prop_name(node):
            if isinstance(node, list) and node and node[0] == "property" and len(node) > 1:
                return unquote(node[1])
            return None

        have_props = {prop_name(c) for c in child[1:]}
        for c in parent[1:]:
            name = prop_name(c)
            if name and name not in have_props:
                child.append(copy.deepcopy(c))
                have_props.add(name)
        return child

    def symbol(self, filename: str, name: str, nick: str):
        key = (nick, name)
        if key in self.symbols:
            return self.symbols[key]
        tops = self.load_file(filename)
        flat = self._flatten(tops, name, set())
        import copy

        node = copy.deepcopy(flat)
        node[1] = f'"{nick}:{name}"'
        self.symbols[key] = node
        return node


def symbol_pins(node):
    """Return unit-1 pins: number, name, etype, x, y, angle."""
    short = unquote(node[1]).split(":")[-1]
    pins = []
    units = set()

    def walk(item, unit_name):
        if not isinstance(item, list) or not item:
            return
        if item[0] == "symbol" and len(item) > 1 and isinstance(item[1], str):
            unit_name = unquote(item[1])
            parts = unit_name.rsplit("_", 2)
            if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
                units.add(int(parts[1]))
        if item[0] == "pin":
            etype = item[1] if len(item) > 1 else "?"
            number = name = ""
            x = y = angle = 0.0
            for c in item:
                if isinstance(c, list) and c:
                    if c[0] == "number":
                        number = unquote(c[1])
                    elif c[0] == "name":
                        name = unquote(c[1])
                    elif c[0] == "at":
                        x = float(c[1])
                        y = float(c[2])
                        angle = float(c[3]) if len(c) > 3 else 0.0
            # Style 2 is the De Morgan alternate. Some power symbols, including
            # PWR_FLAG, put the pin on unit 0 style 0 (PWR_FLAG_0_0).
            keep = True
            style = 1
            unit = 1
            if unit_name:
                parts = unit_name.rsplit("_", 2)
                if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
                    unit = int(parts[1])
                    style = int(parts[2])
                    if unit not in (0, 1) or style not in (0, 1):
                        keep = False
            if keep and number:
                pins.append(
                    {
                        "number": number,
                        "name": name,
                        "etype": etype,
                        "x": x,
                        "y": y,
                        "angle": angle,
                        "unit": unit,
                        "style": style,
                    }
                )
        for c in item:
            if isinstance(c, list):
                walk(c, unit_name)

    walk(node, short)
    # Prefer the normal body (style 1, unit 1) when the same number is drawn twice.
    best = {}
    for pin in pins:
        prev = best.get(pin["number"])
        rank = (pin["style"] == 1, pin["unit"] == 1)
        if prev is None or rank > prev[0]:
            best[pin["number"]] = (rank, pin)
    pins = [item[1] for _, item in sorted(best.items(), key=lambda kv: kv[0])]
    extra = {u for u in units if u > 1}
    return pins, extra


def default_footprint(node) -> str:
    for c in node[1:]:
        if isinstance(c, list) and c and c[0] == "property" and unquote(c[1]) == "Footprint":
            return unquote(c[2])
    return ""


class Sheet:
    def __init__(self, side: str, lib: Lib):
        self.side = side
        self.lib = lib
        self.parts = []
        self.power_uses = []  # (net, abs_x, abs_y) placed later from pin coords
        self.labels = []  # (name, x, y, angle)
        self.wires = []
        self.ncs = []
        self.texts = []
        self.flags = []  # nets that need a PWR_FLAG
        self.net_types = {}
        self._pwr_i = 0
        self._flg_i = 0
        self.sym_nodes = {}

    def use(self, filename, name, nick):
        node = self.lib.symbol(filename, name, nick)
        self.sym_nodes[f"{nick}:{name}"] = node
        return node

    def add_part(
        self,
        lib_id,
        ref,
        value,
        footprint="",
        datasheet="",
        dnp=False,
        fields=None,
        pins=None,
    ):
        node = self.sym_nodes[lib_id]
        pin_list, extra_units = symbol_pins(node)
        if extra_units:
            raise RuntimeError(f"{lib_id} has extra units {extra_units}")
        part = {
            "lib_id": lib_id,
            "ref": ref,
            "value": value,
            "footprint": footprint,
            "datasheet": datasheet or "~",
            "dnp": dnp,
            "fields": fields or {},
            "pins": pin_list,
            "assign": {},  # number -> ("power", net) | ("label", net) | ("nc",)
        }
        if pins:
            part["assign"] = pins
        self.parts.append(part)
        return part

    def note_type(self, net, etype):
        if net is None:
            return
        self.net_types.setdefault(net, set()).add(etype)

    def assign(self, part, number, kind, net=None):
        number = str(number)
        hits = [p for p in part["pins"] if p["number"] == number]
        if not hits:
            raise KeyError(f"{part['ref']} has no pin {number}: {part['pins']}")
        if number in part["assign"]:
            raise RuntimeError(f"{part['ref']} pin {number} assigned twice")
        part["assign"][number] = (kind, net)
        if kind != "nc":
            self.note_type(net, hits[0]["etype"])

    def assign_name(self, part, name, kind, net=None):
        hits = [p for p in part["pins"] if p["name"] == name]
        if len(hits) != 1:
            shown = [(p["number"], p["name"], p["etype"]) for p in part["pins"]]
            raise KeyError(f"{part['ref']} name {name!r} matched {hits} in {shown}")
        self.assign(part, hits[0]["number"], kind, net)

    def require_all_assigned(self):
        for part in self.parts:
            for pin in part["pins"]:
                if pin["number"] not in part["assign"]:
                    shown = [(p["number"], p["name"], p["etype"]) for p in part["pins"]]
                    raise RuntimeError(f"{part['ref']} pin {pin['number']} ({pin['name']}) open; pins={shown}")


def abs_point(sx, sy, px, py):
    return sx + px, sy + Y_SIGN * py


def world_dir(angle):
    a = int(round(angle)) % 360
    table = {0: (1.0, 0.0), 90: (0.0, 1.0), 180: (-1.0, 0.0), 270: (0.0, -1.0)}
    if a not in table:
        raise RuntimeError(f"pin angle {angle}")
    dx, dy = table[a]
    return dx, Y_SIGN * dy


def on_segment(ax, ay, bx, by, px, py, tol=0.02):
    dx, dy = bx - ax, by - ay
    length = (dx * dx + dy * dy) ** 0.5
    if length < 1e-9:
        return abs(px - ax) < tol and abs(py - ay) < tol
    t = ((px - ax) * dx + (py - ay) * dy) / (length * length)
    if t <= 0.02 or t >= 0.98:
        return False
    cx, cy = ax + t * dx, ay + t * dy
    return abs(px - cx) < tol and abs(py - cy) < tol


def choose_stub(x, y, angle, others):
    """Wire stub from a pin.

    KiCad stores the pin angle as the direction from the connection point
    toward the body. The first try is the opposite direction so the stub
    leaves the symbol instead of shorting pins inside it.
    """
    dx, dy = world_dir(angle)
    for sign in (-1.0, 1.0):
        for length in (STUB, 2.54, 1.27):
            ex, ey = x + sign * dx * length, y + sign * dy * length
            if any(on_segment(x, y, ex, ey, ox, oy) for ox, oy in others):
                continue
            if any(abs(ex - ox) < 0.02 and abs(ey - oy) < 0.02 for ox, oy in others):
                continue
            return ex, ey
    raise RuntimeError(f"no stub from {(x, y)}")


def place_parts(sheet: Sheet):
    cursor_x = 40.0
    cursor_y = 30.0
    row_h = 0.0
    max_x = 1500.0
    pad = STUB + 3.81
    for part in sheet.parts:
        xs, ys = [], []
        for pin in part["pins"]:
            wx, wy = pin["x"], Y_SIGN * pin["y"]
            xs.append(wx)
            ys.append(wy)
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        width = (maxx - minx) + 2 * pad
        height = (maxy - miny) + 2 * pad
        if cursor_x + width > max_x:
            cursor_x = 40.0
            cursor_y += row_h + 8.0
            row_h = 0.0
        sx = cursor_x - minx + pad
        sy = cursor_y - miny + pad
        # Keep the symbol origin on the 1.27 mm grid.
        sx = round(sx / GRID) * GRID
        sy = round(sy / GRID) * GRID
        part["x"] = sx
        part["y"] = sy
        cursor_x += width + 6.0
        row_h = max(row_h, height)
        for pin in part["pins"]:
            pin["ax"], pin["ay"] = abs_point(sx, sy, pin["x"], pin["y"])


def emit_connections(sheet: Sheet):
    for part in sheet.parts:
        points = [(p["ax"], p["ay"]) for p in part["pins"]]
        occupied = list(points)
        # Stacked pins (USB-C VBUS, D+, D-) share one coordinate. One stub
        # keeps a single label from landing on several identical wires.
        label_groups = {}
        for pin in part["pins"]:
            kind, net = part["assign"][pin["number"]]
            if kind == "nc":
                sheet.ncs.append((pin["ax"], pin["ay"]))
                continue
            if kind == "power":
                sheet.power_uses.append((net, pin["ax"], pin["ay"]))
                continue
            if kind != "label":
                raise RuntimeError(kind)
            label_groups.setdefault((pin["ax"], pin["ay"]), []).append((pin, net))
        for (ax, ay), items in label_groups.items():
            nets = {net for _pin, net in items}
            if len(nets) != 1:
                ref = part["ref"]
                raise RuntimeError(f"{ref} stacked pins at {(ax, ay)} have nets {nets}")
            pin = items[0][0]
            net = items[0][1]
            others = [pt for pt in occupied if pt != (ax, ay)]
            ex, ey = choose_stub(ax, ay, pin["angle"], others)
            occupied.append((ex, ey))
            sheet.wires.append((ax, ay, ex, ey))
            sheet.labels.append((net, ex, ey, 0))


def add_power_flags(sheet: Sheet):
    """One PWR_FLAG on every net that has a power-input and no power-output."""
    # 1.27 mm connection grid. 31*1.27 = 39.37, 1338*1.27 = 1699.26.
    y = 39.37
    x = 1699.26
    for net, types in sorted(sheet.net_types.items()):
        if "power_in" in types and "power_out" not in types:
            sheet.flags.append((net, x, y))
            y += 12.7


def effects(hide=False) -> str:
    hide_s = "\n\t\t\t\t(hide yes)" if hide else ""
    return (
        "\t\t\t(effects\n"
        "\t\t\t\t(font\n"
        "\t\t\t\t\t(size 1.27 1.27)\n"
        "\t\t\t\t)"
        f"{hide_s}\n"
        "\t\t\t)"
    )


def property_block(name, value, x, y, hide=False) -> str:
    return (
        f'\t\t(property "{esc(name)}" "{esc(value)}"\n'
        f"\t\t\t(at {fmt(x)} {fmt(y)} 0)\n"
        f"{effects(hide)}\n"
        "\t\t)"
    )


def write_schematic(sheet: Sheet, project: str, path: Path, root_uuid: str):
    lib_text = "\n".join(dump(node, 2) for node in sheet.sym_nodes.values())
    chunks = []
    for part in sheet.parts:
        x, y = part["x"], part["y"]
        pin_blocks = []
        seen = set()
        for pin in part["pins"]:
            if pin["number"] in seen:
                continue
            seen.add(pin["number"])
            pin_blocks.append(
                f'\t\t(pin "{esc(pin["number"])}"\n\t\t\t(uuid "{uid()}")\n\t\t)'
            )
        fields = [
            property_block("Reference", part["ref"], x, y + 2.54, hide=part["ref"].startswith("#")),
            property_block("Value", part["value"], x, y - 2.54),
            property_block("Footprint", part["footprint"], x, y, hide=True),
            property_block("Datasheet", part["datasheet"], x, y, hide=True),
        ]
        for key, val in part["fields"].items():
            if val is None or val == "":
                continue
            fields.append(property_block(key, val, x, y, hide=True))
        dnp = "yes" if part["dnp"] else "no"
        part["uuid"] = part.get("uuid") or uid()
        chunks.append(
            "\t(symbol\n"
            f'\t\t(lib_id "{esc(part["lib_id"])}")\n'
            f"\t\t(at {fmt(x)} {fmt(y)} 0)\n"
            "\t\t(unit 1)\n"
            "\t\t(exclude_from_sim no)\n"
            f"\t\t(in_bom {'no' if part['ref'].startswith('#') else 'yes'})\n"
            f"\t\t(on_board {'no' if part['ref'].startswith('#') else 'yes'})\n"
            f"\t\t(dnp {dnp})\n"
            f'\t\t(uuid "{part["uuid"]}")\n'
            + "\n".join(fields)
            + "\n"
            + "\n".join(pin_blocks)
            + "\n"
            + "\t\t(instances\n"
            + f'\t\t\t(project "{esc(project)}"\n'
            + '\t\t\t\t(path "/"\n'
            + f'\t\t\t\t\t(reference "{esc(part["ref"])}")\n'
            + "\t\t\t\t\t(unit 1)\n"
            + "\t\t\t\t)\n"
            + "\t\t\t)\n"
            + "\t\t)\n"
            + "\t)"
        )

    def power_symbol(lib_id, ref, value, x, y, in_bom="no"):
        node = sheet.sym_nodes[lib_id]
        pins, _ = symbol_pins(node)
        if len(pins) != 1:
            raise RuntimeError(f"{lib_id} pin count {len(pins)}")
        px, py = pins[0]["x"], pins[0]["y"]
        # abs = (sx + px, sy + Y_SIGN*py) == (x, y)
        sx = x - px
        sy = y - Y_SIGN * py
        pin = pins[0]
        return (
            "\t(symbol\n"
            f'\t\t(lib_id "{esc(lib_id)}")\n'
            f"\t\t(at {fmt(sx)} {fmt(sy)} 0)\n"
            "\t\t(unit 1)\n"
            "\t\t(exclude_from_sim no)\n"
            f"\t\t(in_bom {in_bom})\n"
            "\t\t(on_board no)\n"
            "\t\t(dnp no)\n"
            f'\t\t(uuid "{uid()}")\n'
            + property_block("Reference", ref, sx, sy + 3.81, hide=True)
            + "\n"
            + property_block("Value", value, sx, sy - 3.81, hide=False)
            + "\n"
            + property_block("Footprint", "", sx, sy, hide=True)
            + "\n"
            + property_block("Datasheet", "", sx, sy, hide=True)
            + "\n"
            + f'\t\t(pin "{esc(pin["number"])}"\n\t\t\t(uuid "{uid()}")\n\t\t)\n'
            + "\t\t(instances\n"
            + f'\t\t\t(project "{esc(project)}"\n'
            + '\t\t\t\t(path "/"\n'
            + f'\t\t\t\t\t(reference "{esc(ref)}")\n'
            + "\t\t\t\t\t(unit 1)\n"
            + "\t\t\t\t)\n"
            + "\t\t\t)\n"
            + "\t\t)\n"
            + "\t)"
        ), (sx, sy)

    power_chunks = []
    pwr_n = 0
    for net, x, y in sheet.power_uses:
        pwr_n += 1
        ref = f"#PWR{pwr_n:04d}"
        lib_id = f"power:{net}"
        text, _ = power_symbol(lib_id, ref, net, x, y)
        power_chunks.append(text)

    flag_chunks = []
    flag_wires = []
    flg_n = 0
    for net, x, y in sheet.flags:
        flg_n += 1
        # Wire from a net connection point to the flag.
        if net in ("+3V3", "+5V", "+1V1", "GND"):
            pwr_n += 1
            ref = f"#PWR{pwr_n:04d}"
            text, _ = power_symbol(f"power:{net}", ref, net, x, y)
            power_chunks.append(text)
            anchor = (x, y)
        else:
            sheet.labels.append((net, x, y, 0))
            anchor = (x, y)
        fx, fy = x + 10.16, y
        flg_ref = f"#FLG{flg_n:04d}"
        text, _ = power_symbol("power:PWR_FLAG", flg_ref, "PWR_FLAG", fx, fy)
        flag_chunks.append(text)
        flag_wires.append((anchor[0], anchor[1], fx, fy))

    wire_chunks = []
    for x1, y1, x2, y2 in list(sheet.wires) + flag_wires:
        wire_chunks.append(
            "\t(wire\n"
            "\t\t(pts\n"
            f"\t\t\t(xy {fmt(x1)} {fmt(y1)}) (xy {fmt(x2)} {fmt(y2)})\n"
            "\t\t)\n"
            "\t\t(stroke\n"
            "\t\t\t(width 0)\n"
            "\t\t\t(type default)\n"
            "\t\t)\n"
            f'\t\t(uuid "{uid()}")\n'
            "\t)"
        )
    label_chunks = []
    for name, x, y, angle in sheet.labels:
        label_chunks.append(
            f'\t(label "{esc(name)}"\n'
            f"\t\t(at {fmt(x)} {fmt(y)} {angle})\n"
            "\t\t(effects\n"
            "\t\t\t(font\n"
            "\t\t\t\t(size 1.27 1.27)\n"
            "\t\t\t\t)\n"
            "\t\t)\n"
            f'\t\t(uuid "{uid()}")\n'
            "\t)"
        )
    nc_chunks = []
    for x, y in sheet.ncs:
        nc_chunks.append(f'\t(no_connect\n\t\t(at {fmt(x)} {fmt(y)})\n\t\t(uuid "{uid()}")\n\t)')
    text_chunks = []
    for text, x, y in sheet.texts:
        text_chunks.append(
            f'\t(text "{esc(text)}"\n'
            f"\t\t(at {fmt(x)} {fmt(y)} 0)\n"
            "\t\t(effects\n"
            "\t\t\t(font\n"
            "\t\t\t\t(size 1.27 1.27)\n"
            "\t\t\t\t)\n"
            "\t\t)\n"
            f'\t\t(uuid "{uid()}")\n'
            "\t)"
        )
    title = f"ErgoDox RP2040 {sheet.side}"
    body = f"""(kicad_sch
	(version 20250114)
	(generator "build_board.py")
	(generator_version "10.0.7")
	(uuid "{root_uuid}")
	(paper "A0")
	(title_block
		(title "{title}")
		(date "2026-11-08")
		(rev "0.1")
		(comment 1 "Generated by hw/ergodox-rp2040/tools/build_board.py")
		(comment 2 "LINK is a UART cable, not a PC port")
		(comment 3 "Only left/right differences: LINK UART swap and GPIO19 strap")
	)
	(lib_symbols
{lib_text}
	)
{chr(10).join(chunks)}
{chr(10).join(power_chunks)}
{chr(10).join(flag_chunks)}
{chr(10).join(wire_chunks)}
{chr(10).join(label_chunks)}
{chr(10).join(nc_chunks)}
{chr(10).join(text_chunks)}
	(sheet_instances
		(path "/"
			(page "1")
		)
	)
	(embedded_fonts no)
)
"""
    path.write_text(body, encoding="utf-8")


def two_pin(sheet, lib_id, ref, value, footprint, pin_a, pin_b, lcsc_key=None, dnp=False, fields=None):
    extra = dict(fields or {})
    if lcsc_key and LCSC.get(lcsc_key):
        extra["LCSC"] = LCSC[lcsc_key]
    part = sheet.add_part(lib_id, ref, value, footprint=footprint, dnp=dnp, fields=extra)
    for pin, spec in (("1", pin_a), ("2", pin_b)):
        kind, net = spec
        sheet.assign(part, pin, kind, net)
    return part


def r_part(sheet, ref, value, a, b, dnp=False, note=""):
    fields = {}
    if note:
        fields["Note"] = note
    return two_pin(
        sheet,
        "Device:R",
        ref,
        value,
        "Resistor_SMD:R_0402_1005Metric",
        a,
        b,
        lcsc_key=value if value in LCSC else None,
        dnp=dnp,
        fields=fields,
    )


def c_part(sheet, ref, value, a, b, note=""):
    fields = {"Note": note} if note else {}
    return two_pin(
        sheet,
        "Device:C",
        ref,
        value,
        "Capacitor_SMD:C_0402_1005Metric",
        a,
        b,
        lcsc_key=value if value in LCSC else None,
        fields=fields,
    )


def labeled(net):
    return ("label", net)


def powered(net):
    return ("power", net)


def nc():
    return ("nc", None)


def build(side: str, lib: Lib) -> Sheet:
    if side not in ("left", "right"):
        raise ValueError(side)
    sheet = Sheet(side, lib)
    sheet.use("Device.kicad_sym", "R", "Device")
    sheet.use("Device.kicad_sym", "C", "Device")
    sheet.use("Transistor_FET.kicad_sym", "2N7002", "Transistor_FET")
    sheet.use("Device.kicad_sym", "Q_PJFET_DSG", "Device")
    sheet.use("Device.kicad_sym", "Crystal_GND24", "Device")
    sheet.use("Switch.kicad_sym", "SW_Push", "Switch")
    sheet.use("Diode.kicad_sym", "1N4148W", "Diode")
    sheet.use("Diode.kicad_sym", "SS14", "Diode")
    sheet.use("LED.kicad_sym", "SK6812MINI", "LED")
    sheet.use("Connector.kicad_sym", "USB_C_Receptacle_USB2.0_16P", "Connector")
    sheet.use("MCU_RaspberryPi.kicad_sym", "RP2040", "MCU_RaspberryPi")
    sheet.use("Memory_Flash.kicad_sym", "W25Q128JVS", "Memory_Flash")
    sheet.use("Regulator_Linear.kicad_sym", "AP2112K-3.3", "Regulator_Linear")
    sheet.use("Power_Management.kicad_sym", "TPS22917DBV", "Power_Management")
    sheet.use("Power_Protection.kicad_sym", "USBLC6-2SC6", "Power_Protection")
    for name in ("GND", "+3V3", "+5V", "+1V1", "PWR_FLAG"):
        sheet.use("power.kicad_sym", name, "power")

    # --- MCU ---
    mcu = sheet.add_part(
        "MCU_RaspberryPi:RP2040",
        "U1",
        "RP2040",
        footprint="Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm_ThermalVias",
        datasheet="https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf",
        fields={"LCSC": LCSC["RP2040"], "MPN": "RP2040"},
    )
    power_pins_3v3 = {"1", "43", "44", "48"}
    # Passive IOVDD pins are still the 3.3 V rail. Pin 49 shares a capacitor with USB_VDD.
    passive_3v3 = {"10", "22", "33", "42", "49"}
    for num in power_pins_3v3 | passive_3v3:
        sheet.assign(mcu, num, "power", "+3V3")
    for num in ("23", "50"):
        sheet.assign(mcu, num, "power", "+1V1")
    sheet.assign(mcu, "45", "power", "+1V1")  # VREG_VOUT power_out
    sheet.assign(mcu, "57", "power", "GND")
    sheet.assign(mcu, "19", "power", "GND")  # TESTEN
    gpio_nets = {
        "2": "GPIO0",
        "3": "GPIO1",
        "4": "LED_DIN",
        "5": "LED_ON",
        "6": "LINK_SRC_REQ",
        "7": "LINK_RP_EN",
        "8": "ROW0",
        "9": "ROW1",
        "11": "ROW2",
        "12": "ROW3",
        "13": "ROW4",
        "14": "ROW5",
        "15": "COL0",
        "16": "COL1",
        "17": "COL4",
        "18": "COL5",
        "27": "COL6",
        "28": "COL10",
        "29": "COL11",
        "30": "BOARD_ID",
        "38": "HOST_VBUS_SENSE",
        "39": "CC1_SENSE",
        "40": "CC2_SENSE",
        "41": "LINK_VBUS_SENSE",
    }
    for num, net in gpio_nets.items():
        sheet.assign(mcu, num, "label", net)
    sheet.assign(mcu, "20", "label", "XIN")
    sheet.assign(mcu, "21", "label", "XOUT")
    # Unused GPIO20-25: no pad, no resistor. Firmware turns on the internal pulldown.
    for num in ("31", "32", "34", "35", "36", "37"):
        sheet.assign(mcu, num, "nc", None)
    sheet.assign(mcu, "24", "nc", None)  # SWCLK, test pad not fitted
    sheet.assign(mcu, "25", "nc", None)  # SWDIO
    sheet.assign(mcu, "26", "label", "RUN")
    sheet.assign(mcu, "46", "label", "USB_DM_MCU")
    sheet.assign(mcu, "47", "label", "USB_DP_MCU")
    for num, net in {
        "51": "QSPI_SD3",
        "52": "QSPI_SCLK",
        "53": "QSPI_SD0",
        "54": "QSPI_SD2",
        "55": "QSPI_SD1",
        "56": "QSPI_SS",
    }.items():
        sheet.assign(mcu, num, "label", net)

    # --- Flash ---
    flash = sheet.add_part(
        "Memory_Flash:W25Q128JVS",
        "U2",
        "W25Q128JVSIQ",
        footprint="Package_SO:SOIC-8_5.3x5.3mm_P1.27mm",
        datasheet="https://www.winbond.com/resource-files/w25q128jv%20revg%2004082019%20plus.pdf",
        fields={
            "LCSC": LCSC["W25Q128JVSIQ"],
            "MPN": "W25Q128JVSIQ",
            "Note": "KiCad symbol footprint is SOIC-8 5.3x5.3 mm, 208 mil JEITA. DESIGN.md also names SOIC-8_5.3x6.2mm; pads were not measured against the Winbond drawing.",
        },
    )
    flash_map = flash_pin_map(flash)
    for num, kind, net in flash_map:
        sheet.assign(flash, num, kind, net)

    # --- LDO ---
    ldo = sheet.add_part(
        "Regulator_Linear:AP2112K-3.3",
        "U3",
        "AP2112K-3.3TRG1",
        footprint="Package_TO_SOT_SMD:SOT-23-5",
        datasheet="https://www.diodes.com/assets/Datasheets/AP2112.pdf",
        fields={"LCSC": LCSC["AP2112K-3.3TRG1"], "MPN": "AP2112K-3.3TRG1"},
    )
    assign_ldo(sheet, ldo)

    def load_switch(ref, on_net, vout_net):
        part = sheet.add_part(
            "Power_Management:TPS22917DBV",
            ref,
            "TPS22917DBVT",
            footprint="Package_TO_SOT_SMD:SOT-23-6",
            datasheet="https://www.ti.com/lit/ds/symlink/tps22917.pdf",
            fields={"LCSC": LCSC["TPS22917DBVT"], "MPN": "TPS22917DBVT", "Note": "CT open, QOD open, active high"},
        )
        by_name = {p["name"]: p for p in part["pins"]}
        need = {"VIN", "GND", "ON", "CT", "QOD", "VOUT"}
        if set(by_name) != need:
            raise RuntimeError(f"TPS22917 pins {list(by_name)}")
        sheet.assign(part, by_name["VIN"]["number"], "power", "+5V")
        sheet.assign(part, by_name["GND"]["number"], "power", "GND")
        sheet.assign(part, by_name["ON"]["number"], "label", on_net)
        sheet.assign(part, by_name["CT"]["number"], "nc", None)
        sheet.assign(part, by_name["QOD"]["number"], "nc", None)
        sheet.assign(part, by_name["VOUT"]["number"], "label", vout_net)
        return part

    load_switch("U4", "LED_ON", "LED_5V")
    load_switch("U5", "LINK_SRC_ON", "LINK_VBUS")

    # --- USB-C ---
    def usb_c(ref, role):
        part = sheet.add_part(
            "Connector:USB_C_Receptacle_USB2.0_16P",
            ref,
            "TYPE-C-31-M-12",
            footprint="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
            datasheet="http://www.krhro.com/uploads/soft/180320/1-1P320120243.pdf",
            fields={
                "LCSC": LCSC["TYPE-C-31-M-12"],
                "MPN": "TYPE-C-31-M-12",
                "Role": role,
            },
        )
        return part

    host = usb_c("J1", "HOST USB device")
    link = usb_c("J2", "LINK not a PC port")
    wire_usb(sheet, host, vbus="HOST_VBUS", dp="USB_DP_CONN", dm="USB_DM_CONN", cc1="HOST_CC1", cc2="HOST_CC2")
    # Swap is which UART net lands on D+ / D-.
    if side == "left":
        tx_conn, rx_conn = "LINK_DP", "LINK_DM"
    else:
        tx_conn, rx_conn = "LINK_DM", "LINK_DP"
    wire_usb(sheet, link, vbus="LINK_VBUS", dp="LINK_DP", dm="LINK_DM", cc1="LINK_CC1", cc2="LINK_CC2")

    def esd(ref, conn_p, dev_p, conn_m, dev_m, vbus_kind, vbus_net, note):
        part = sheet.add_part(
            "Power_Protection:USBLC6-2SC6",
            ref,
            "USBLC6-2SC6",
            footprint="Package_TO_SOT_SMD:SOT-23-6",
            datasheet="https://www.st.com/resource/en/datasheet/usblc6-2.pdf",
            fields={"LCSC": LCSC["USBLC6-2SC6"], "MPN": "USBLC6-2SC6", "Note": note},
        )
        by_num = {p["number"]: p for p in part["pins"]}
        expect = {
            "1": "I/O1",
            "2": "GND",
            "3": "I/O2",
            "4": "I/O2",
            "5": "VBUS",
            "6": "I/O1",
        }
        got = {n: by_num[n]["name"].replace("~", "").replace("{", "").replace("}", "") for n in expect}
        # Accept the ST names even if the symbol decorates them.
        for num, needle in (("1", "IO1"), ("6", "IO1"), ("3", "IO2"), ("4", "IO2"), ("2", "GND"), ("5", "VBUS")):
            compact = "".join(ch for ch in by_num[num]["name"].upper() if ch.isalnum())
            if needle not in compact and not (needle == "IO1" and "IO1" in compact):
                raise RuntimeError(f"USBLC6 pin {num} is {by_num[num]['name']}, expected {needle}. All={[(p['number'], p['name'], p['etype']) for p in part['pins']]}")
        sheet.assign(part, "1", "label", conn_p)
        sheet.assign(part, "6", "label", dev_p)
        sheet.assign(part, "3", "label", conn_m)
        sheet.assign(part, "4", "label", dev_m)
        sheet.assign(part, "2", "power", "GND")
        sheet.assign(part, "5", vbus_kind, vbus_net)

    esd(
        "D1",
        "USB_DP_CONN",
        "USB_DP",
        "USB_DM_CONN",
        "USB_DM",
        "label",
        "HOST_VBUS",
        "HOST D+/D- at the receptacle. ST pin 1/6 are one channel, pin 3/4 the other.",
    )
    esd(
        "D2",
        tx_conn if side == "left" else rx_conn,
        "LINK_TX" if side == "left" else "LINK_RX",
        rx_conn if side == "left" else tx_conn,
        "LINK_RX" if side == "left" else "LINK_TX",
        "power",
        "+3V3",
        "LINK UART ESD. VBUS pin of the array is the upper clamp rail and is tied to +3V3, not 5 V. Clamp voltage above 3.3 V was not verified against the RP2040 absolute maximum.",
    )
    # The assignment above for D2 tries to be clever and is easy to get wrong.
    # Rebuild D2 explicitly: channel 1 is TX, channel 2 is RX.
    # Undo by not using the computed args. The function already assigned.
    # Verify the nets that were requested:
    # left: conn pin1 = LINK_DP = tx_conn, pin6 = LINK_TX, pin3 = LINK_DM, pin4 = LINK_RX
    # right: tx_conn is LINK_DM, but the call used `tx_conn if left else rx_conn` for pin 1.
    # right: pin1 = rx_conn = LINK_DP, pin6 = LINK_RX, pin3 = tx_conn = LINK_DM, pin4 = LINK_TX.
    # That is the required swap. Good.

    # Schottky OR into +5V. Anode at the connector, cathode at +5V.
    def schottky(ref, anode_net):
        part = sheet.add_part(
            "Diode:SS14",
            ref,
            "SS14",
            footprint="Diode_SMD:D_SMA",
            fields={"LCSC": LCSC["SS14"], "MPN": "SS14", "Note": "Anode toward the connector so +5V cannot back-power it"},
        )
        assign_diode(sheet, part, anode=("label", anode_net), cathode=("power", "+5V"))

    schottky("D3", "HOST_VBUS")
    schottky("D4", "LINK_VBUS")

    # Series 27 ohm next to the RP2040.
    r_part(sheet, "R10", "27", labeled("USB_DP"), labeled("USB_DP_MCU"), note="HOST D+ series, at the RP2040")
    r_part(sheet, "R11", "27", labeled("USB_DM"), labeled("USB_DM_MCU"), note="HOST D- series, at the RP2040")
    r_part(sheet, "R12", "27", labeled("GPIO0"), labeled("LINK_TX"), note="LINK TX series")
    r_part(sheet, "R13", "27", labeled("GPIO1"), labeled("LINK_RX"), note="LINK RX series")

    # HOST CC sink only.
    r_part(sheet, "R4", "5.1k", labeled("HOST_CC1"), powered("GND"), note="HOST CC1 Rd")
    r_part(sheet, "R5", "5.1k", labeled("HOST_CC2"), powered("GND"), note="HOST CC2 Rd")

    # LINK CC, one copy per pin.
    def link_cc(idx, cc_net, sense_net, rd_ref, rp_ref, jfet_ref, nmos_ref, div_top, div_bot):
        r_part(sheet, rd_ref, "5.1k", labeled(cc_net), labeled(f"{cc_net}_RD"), note="LINK Rd")
        jfet = sheet.add_part(
            "Device:Q_PJFET_DSG",
            jfet_ref,
            "MMBFJ177LT1G",
            footprint="Package_TO_SOT_SMD:SOT-23",
            fields={
                "LCSC": LCSC["MMBFJ177LT1G"],
                "MPN": "MMBFJ177LT1G",
                "Note": "Depletion P-channel JFET. On at Vgs=0, off at Vgs=+3.3 V. SOT-23 pad 1 D, 2 S, 3 G.",
            },
        )
        sheet.assign_name(jfet, "G", "label", "LINK_RP_EN")
        sheet.assign_name(jfet, "S", "power", "GND")
        sheet.assign_name(jfet, "D", "label", f"{cc_net}_RD")
        r_part(
            sheet,
            rp_ref,
            "36k",
            powered("+3V3"),
            labeled(f"{cc_net}_RP"),
            note="Rp to +3.3 V, Default USB, +/-20%. LCSC unverified.",
        )
        nmos = sheet.add_part(
            "Transistor_FET:2N7002",
            nmos_ref,
            "2N7002",
            footprint="Package_TO_SOT_SMD:SOT-23",
            fields={"LCSC": LCSC["2N7002"], "MPN": "2N7002", "Note": "N-channel MOSFET, on at Vgs=3.3 V."},
        )
        sheet.assign_name(nmos, "G", "label", "LINK_RP_EN")
        sheet.assign_name(nmos, "D", "label", f"{cc_net}_RP")
        sheet.assign_name(nmos, "S", "label", cc_net)
        # 200k / 100k. Open-pin load is 300k. 3.3*300/336 = 2.95 V (> 1.65 V).
        # 5.5 V on CC -> 5.5*100/300 = 1.83 V on the ADC (<= 3.0 V).
        r_part(sheet, div_top, "200k", labeled(cc_net), labeled(sense_net), note="CC sense top. LCSC unverified.")
        r_part(sheet, div_bot, "100k", labeled(sense_net), powered("GND"), note="CC sense bottom. LCSC unverified.")

    link_cc(1, "LINK_CC1", "CC1_SENSE", "R6", "R8", "Q1", "Q2", "R20", "R21")
    link_cc(2, "LINK_CC2", "CC2_SENSE", "R7", "R9", "Q3", "Q4", "R22", "R23")

    r_part(sheet, "R16", "10k", labeled("LINK_RP_EN"), powered("GND"), note="LINK_RP_EN pulldown")

    # Source-switch gate. ON is shorted to GND unless HOST VBUS is present.
    r_part(sheet, "R18", "1k", labeled("LINK_SRC_REQ"), labeled("LINK_SRC_ON"), note="GPIO series so the clamp MOSFET can win")
    r_part(sheet, "R15", "10k", labeled("LINK_SRC_ON"), powered("GND"), note="LINK source ON pulldown")
    q_gate = sheet.add_part(
        "Transistor_FET:2N7002",
        "Q5",
        "2N7002",
        footprint="Package_TO_SOT_SMD:SOT-23",
        fields={"LCSC": LCSC["2N7002"], "MPN": "2N7002", "Note": "Shorts LINK source ON to GND when its gate is high."},
    )
    sheet.assign_name(q_gate, "G", "label", "LINK_GATE")
    sheet.assign_name(q_gate, "D", "label", "LINK_SRC_ON")
    sheet.assign_name(q_gate, "S", "power", "GND")
    r_part(sheet, "R19", "10k", powered("+3V3"), labeled("LINK_GATE"), note="Default-on pull-up for the ON clamp. LCSC is the verified 10k.")
    q_host = sheet.add_part(
        "Transistor_FET:2N7002",
        "Q6",
        "2N7002",
        footprint="Package_TO_SOT_SMD:SOT-23",
        fields={"LCSC": LCSC["2N7002"], "MPN": "2N7002", "Note": "Pulls the ON-clamp gate down when HOST VBUS sense is high."},
    )
    sheet.assign_name(q_host, "G", "label", "HOST_VBUS_SENSE")
    sheet.assign_name(q_host, "D", "label", "LINK_GATE")
    sheet.assign_name(q_host, "S", "power", "GND")

    r_part(sheet, "R14", "10k", labeled("LED_ON"), powered("GND"), note="LED switch ON pulldown")

    # VBUS dividers. 100k/100k maps 5.5 V to 2.75 V.
    r_part(sheet, "R24", "100k", labeled("HOST_VBUS"), labeled("HOST_VBUS_SENSE"), note="HOST VBUS divider top. LCSC unverified.")
    r_part(sheet, "R25", "100k", labeled("HOST_VBUS_SENSE"), powered("GND"), note="HOST VBUS divider bottom. LCSC unverified.")
    r_part(sheet, "R26", "100k", labeled("LINK_VBUS"), labeled("LINK_VBUS_SENSE"), note="LINK VBUS divider top. LCSC unverified.")
    r_part(sheet, "R27", "100k", labeled("LINK_VBUS_SENSE"), powered("GND"), note="LINK VBUS divider bottom. LCSC unverified.")

    if side == "left":
        r_part(sheet, "R17", "10k", labeled("BOARD_ID"), powered("GND"), note="Left board id. GPIO19 reads low.")
    else:
        r_part(sheet, "R17", "10k", labeled("BOARD_ID"), powered("+3V3"), note="Right board id. GPIO19 reads high.")

    # Crystal.
    y1 = sheet.add_part(
        "Device:Crystal_GND24",
        "Y1",
        "ABM8-272-T3",
        footprint="Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm",
        datasheet="https://abracon.com/Resonators/ABM8.pdf",
        fields={"LCSC": LCSC["ABM8-272-T3"], "MPN": "ABM8-272-T3", "Note": "12 MHz, CL 10 pF. Pads 2 and 4 GND."},
    )
    sheet.assign(y1, "1", "label", "XIN")
    sheet.assign(y1, "2", "power", "GND")
    sheet.assign(y1, "3", "label", "XTAL")
    sheet.assign(y1, "4", "power", "GND")
    c_part(sheet, "C1", "15pF", labeled("XIN"), powered("GND"), note="Crystal load, XIN. Chapter value 15 pF.")
    c_part(sheet, "C2", "15pF", labeled("XTAL"), powered("GND"), note="Crystal load, XOUT side of the crystal.")
    r_part(sheet, "R2", "1k", labeled("XOUT"), labeled("XTAL"), note="Crystal damper from XOUT")

    # Buttons.
    two_pin(
        sheet,
        "Switch:SW_Push",
        "SW_RST",
        "TS-1187A-B-A-B",
        "Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A",
        labeled("RUN"),
        powered("GND"),
        lcsc_key="TS-1187A-B-A-B",
        fields={"Note": "RESET. RUN to GND. Internal pull-up, no external RUN resistor."},
    )
    two_pin(
        sheet,
        "Switch:SW_Push",
        "SW_BOOT",
        "TS-1187A-B-A-B",
        "Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A",
        labeled("BOOT"),
        powered("GND"),
        lcsc_key="TS-1187A-B-A-B",
        fields={"Note": "BOOTSEL. Through 1k from QSPI_SS."},
    )
    r_part(sheet, "R1", "1k", labeled("QSPI_SS"), labeled("BOOT"), note="BOOTSEL series")
    r_part(
        sheet,
        "R3",
        "10k",
        labeled("QSPI_SS"),
        powered("+3V3"),
        dnp=True,
        note="DNF. Winbond flash does not need the external CS pull-up.",
    )

    # Decoupling. Placement notes are layout, the nets are the rails.
    caps_100 = [
        ("C7", "+1V1", "near DVDD pin 23"),
        ("C8", "+1V1", "near DVDD pin 50"),
        ("C9", "+3V3", "shared USB_VDD pin 48 and IOVDD pin 49"),
        ("C10", "+3V3", "near IOVDD pin 1"),
        ("C11", "+3V3", "near IOVDD pin 10"),
        ("C12", "+3V3", "near IOVDD pin 22"),
        ("C13", "+3V3", "near IOVDD pin 33"),
        ("C14", "+3V3", "near IOVDD pin 42"),
        ("C15", "+3V3", "near ADC_AVDD pin 43"),
        ("C16", "+3V3", "flash VCC"),
    ]
    for ref, rail, note in caps_100:
        c_part(sheet, ref, "100nF", powered(rail), powered("GND"), note=note)
    c_part(sheet, "C3", "1uF", powered("+3V3"), powered("GND"), note="close to VREG_VIN pin 44")
    c_part(sheet, "C4", "1uF", powered("+1V1"), powered("GND"), note="close to VREG_VOUT pin 45")
    c_part(sheet, "C5", "1uF", powered("+5V"), powered("GND"), note="AP2112 input")
    c_part(sheet, "C6", "1uF", powered("+3V3"), powered("GND"), note="AP2112 output")

    # Matrix and LEDs.
    by_chain = sorted(KEYS, key=lambda row: row[3])
    if [row[3] for row in by_chain] != list(range(1, len(KEYS) + 1)):
        raise RuntimeError("chain index is not 1..N")
    for legacy, row, col, index in KEYS:
        ref = legacy.replace(":", "_")
        sw = sheet.add_part(
            "Switch:SW_Push",
            ref,
            "CPG151101S11-16",
            footprint="MX_Hotswap:MX-Hotswap-1U",
            fields={
                "LCSC": LCSC["CPG151101S11-16"],
                "MPN": "CPG151101S11-16",
                "Legacy": legacy,
                "Note": "Hotswap socket only. MX switch body is not assembled.",
            },
        )
        # Socket pad 1 is the one beside the diode on the board.
        sheet.assign(sw, "1", "label", f"SWNODE_{legacy}")
        sheet.assign(sw, "2", "label", row)
        dref = f"D{4 + index}"
        diode = sheet.add_part(
            "Diode:1N4148W",
            dref,
            "1N4148W",
            footprint="Diode_SMD:D_SOD-123",
            fields={"LCSC": LCSC["1N4148W"], "MPN": "1N4148W", "Legacy": legacy, "Note": "Cathode toward the column"},
        )
        assign_diode(sheet, diode, anode=("label", f"SWNODE_{legacy}"), cathode=("label", col))

    for n, (legacy, _row, _col, index) in enumerate(by_chain):
        din = "LED_DIN" if n == 0 else f"LED_{n}"
        dout = None if n == len(by_chain) - 1 else f"LED_{n + 1}"
        led = sheet.add_part(
            "LED:SK6812MINI",
            f"DS{index}",
            "SK6812MINI-E",
            footprint="LED_SMD:LED_SK6812MINI-E_3.2x2.8mm_P1.5mm_ReverseMount",
            fields={
                "LCSC": LCSC["SK6812MINI-E"],
                "MPN": "SK6812MINI-E",
                "Legacy": legacy,
                "Chain": str(index),
                "Note": "Reverse mount on the back, shines up through the board cutout under the switch.",
            },
        )
        by_name = {p["name"]: p["number"] for p in led["pins"]}
        for need in ("VSS", "DIN", "VDD", "DOUT"):
            if need not in by_name:
                raise RuntimeError(f"SK6812 pins {led['pins']}")
        sheet.assign(led, by_name["VDD"], "label", "LED_5V")
        sheet.assign(led, by_name["VSS"], "power", "GND")
        sheet.assign(led, by_name["DIN"], "label", din)
        if dout is None:
            sheet.assign(led, by_name["DOUT"], "nc", None)
        else:
            sheet.assign(led, by_name["DOUT"], "label", dout)

    swap = "D+ = LINK_TX, D- = LINK_RX" if side == "left" else "D+ = LINK_RX, D- = LINK_TX"
    strap = "GPIO19 10k to GND" if side == "left" else "GPIO19 10k to +3V3"
    notes = [
        f"{side.upper()} half. Silkscreen this board {side.upper()}.",
        "LINK receptacle silkscreen: LINK and NOT A PC PORT. It is not a USB device port.",
        f"UART swap on this half: {swap}. GPIO0 is UART0 TX. GPIO1 is UART0 RX.",
        f"Board id: {strap}. Firmware may read it. It does not select the ZMK role.",
        "ZMK role is compile-time. Flash the central image into the half whose HOST plug is in the computer.",
        "HOST CC pins are Rd 5.1k only. No Rp on HOST. VBUS enters +5V through SS14.",
        "LINK Rp is 36k to +3.3V, one per CC pin, only while LINK_RP_EN is high.",
        "CC divider 200k/100k keeps a 36k open pin at 2.95 V and 5.5 V at 1.83 V on the ADC.",
        "VBUS divider 100k/100k maps 5.5 V to 2.75 V. Divider LCSC codes are blank.",
        "36k, 100k and 200k resistors have no verified LCSC code.",
        "USB_DP and USB_DM are the HOST pair between the ESD device side and the 27 ohm resistors.",
        "USB D+/D- on the board is 0.290661 mm wide with 0.203200 mm edge gap (DESIGN.md section 13).",
        "No level shifter on the SK6812 data pin. Direct 3.3 V drive is not guaranteed.",
        "Firmware LED cap is 10 percent of full-scale white, both halves together.",
    ]
    for i, line in enumerate(notes):
        sheet.texts.append((line, 40.0, 12.0 + i * 3.5))

    sheet.require_all_assigned()
    place_parts(sheet)
    emit_connections(sheet)
    add_power_flags(sheet)
    return sheet


def flash_pin_map(part):
    """Map the Winbond SOIC-8 symbol onto the RP2040 QSPI nets."""
    out = []
    for pin in part["pins"]:
        compact = "".join(ch for ch in pin["name"].upper() if ch.isalnum())
        num = pin["number"]
        if "VCC" in compact or compact in ("VDD", "VDDQ"):
            out.append((num, "power", "+3V3"))
        elif compact == "GND" or compact == "VSS":
            out.append((num, "power", "GND"))
        elif "CS" in compact or compact.endswith("SS"):
            out.append((num, "label", "QSPI_SS"))
        elif "CLK" in compact or "SCK" in compact:
            out.append((num, "label", "QSPI_SCLK"))
        elif "IO0" in compact or compact in ("DI", "SI"):
            out.append((num, "label", "QSPI_SD0"))
        elif "IO1" in compact or compact in ("DO", "SO"):
            out.append((num, "label", "QSPI_SD1"))
        elif "IO2" in compact or "WP" in compact:
            out.append((num, "label", "QSPI_SD2"))
        elif "IO3" in compact or "HOLD" in compact:
            out.append((num, "label", "QSPI_SD3"))
        else:
            shown = [(p["number"], p["name"], p["etype"]) for p in part["pins"]]
            raise RuntimeError(f"unmapped flash pin {num} {pin['name']} in {shown}")
    if len(out) != len(part["pins"]):
        raise RuntimeError("flash map length")
    return out


def assign_ldo(sheet, part):
    for pin in part["pins"]:
        compact = "".join(ch for ch in pin["name"].upper() if ch.isalnum())
        num = pin["number"]
        if compact in ("VIN", "IN", "VI"):
            sheet.assign(part, num, "power", "+5V")
        elif compact in ("GND", "VSS"):
            sheet.assign(part, num, "power", "GND")
        elif "EN" in compact or compact in ("CE", "CHIPEN"):
            sheet.assign(part, num, "power", "+5V")
        elif compact in ("VOUT", "OUT", "VO"):
            sheet.assign(part, num, "power", "+3V3")
        elif "NC" in compact or compact in ("EP", "PAD", "TAB"):
            sheet.assign(part, num, "nc", None)
        else:
            shown = [(p["number"], p["name"], p["etype"]) for p in part["pins"]]
            raise RuntimeError(f"unmapped LDO pin {num} {pin['name']} in {shown}")


def assign_diode(sheet, part, anode, cathode):
    by_name = {p["name"].upper(): p for p in part["pins"]}
    # KiCad diode: K cathode, A anode. Some symbols use pin names K/A.
    if "K" in by_name and "A" in by_name:
        k, a = by_name["K"], by_name["A"]
    else:
        shown = [(p["number"], p["name"], p["etype"]) for p in part["pins"]]
        raise RuntimeError(f"diode pins {shown}")
    sheet.assign(part, a["number"], anode[0], anode[1])
    sheet.assign(part, k["number"], cathode[0], cathode[1])


def wire_usb(sheet, part, vbus, dp, dm, cc1, cc2):
    by_num = {p["number"]: p for p in part["pins"]}
    need = ["A1", "A4", "A5", "A6", "A7", "A8", "A9", "A12", "B1", "B4", "B5", "B6", "B7", "B8", "B9", "B12", "SH"]
    missing = [n for n in need if n not in by_num]
    if missing:
        raise RuntimeError(f"USB-C missing {missing} have {list(by_num)}")
    gnd = ("A1", "A12", "B1", "B12", "SH")
    vbus_pins = ("A4", "A9", "B4", "B9")
    for num in gnd:
        sheet.assign(part, num, "power", "GND")
    for num in vbus_pins:
        sheet.assign(part, num, "label", vbus)
    sheet.assign(part, "A5", "label", cc1)
    sheet.assign(part, "B5", "label", cc2)
    sheet.assign(part, "A6", "label", dp)
    sheet.assign(part, "B6", "label", dp)
    sheet.assign(part, "A7", "label", dm)
    sheet.assign(part, "B7", "label", dm)
    sheet.assign(part, "A8", "nc", None)
    sheet.assign(part, "B8", "nc", None)


def write_project(side: str, sch_name: str, root_uuid: str):
    proj_dir = ROOT / side
    proj_dir.mkdir(parents=True, exist_ok=True)
    pro_path = proj_dir / f"{sch_name}.kicad_pro"
    data = json.loads(DEMO_PRO.read_text(encoding="utf-8"))
    data["meta"]["filename"] = pro_path.name
    data["sheets"] = [[root_uuid, sch_name]]
    data["text_variables"] = {}
    if "boards" in data:
        data["boards"] = []
    # One netclass. Demo patterns would force USB onto a 0.23 mm pair that is
    # not the JLC04161H-7628 result in DESIGN.md section 13.
    def netclass(name, width, priority):
        return {
            "bus_width": 12,
            "clearance": 0.15,
            "diff_pair_gap": 0.2032,
            "diff_pair_via_gap": 0.25,
            "diff_pair_width": 0.2907,
            "line_style": 0,
            "microvia_diameter": 0.3,
            "microvia_drill": 0.1,
            "name": name,
            "pcb_color": "rgba(0, 0, 0, 0.000)",
            "priority": priority,
            "schematic_color": "rgba(0, 0, 0, 0.000)",
            "track_width": width,
            "via_diameter": 0.6,
            "via_drill": 0.3,
            "wire_width": 6,
        }

    # USB width is the JLC04161H-7628 90 ohm result in DESIGN.md section 13.
    data["net_settings"]["classes"] = [
        netclass("Default", 0.2, 2147483647),
        netclass("Power", 0.4, 0),
        netclass("USB", 0.2907, 1),
    ]
    data["net_settings"]["netclass_patterns"] = [
        {"netclass": "Power", "pattern": pat}
        for pat in ("+5V", "LED_5V", "HOST_VBUS", "LINK_VBUS")
    ] + [{"netclass": "USB", "pattern": "USB_D*"}]
    data["net_settings"]["netclass_assignments"] = None
    rules = data["board"]["design_settings"]["rules"]
    rules["min_clearance"] = 0.15
    rules["min_track_width"] = 0.15
    data["board"]["design_settings"]["defaults"]["zones"]["min_clearance"] = 0.2
    data["board"]["design_settings"]["diff_pair_dimensions"] = [
        {"gap": 0.0, "via_gap": 0.0, "width": 0.0}
    ]
    pro_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    fp = f"""(fp_lib_table
  (version 7)
  (lib (name "MX_Hotswap")(type "KiCad")(uri "${{KIPRJMOD}}/../third_party/MX_V2/MX_Hotswap.pretty")(options "")(descr "ai03 MX_V2 commit 0b379eebbeb66c7fd6e82e400b47958ad695614e"))
  (lib (name "Switch_Misc")(type "KiCad")(uri "${{KIPRJMOD}}/../third_party/MX_V2/Switch_Misc.pretty")(options "")(descr "ai03 MX_V2 indicator LEDs, not used for SK6812"))
)
"""
    (proj_dir / "fp-lib-table").write_text(fp, encoding="utf-8")


def check_required_nets(path: Path, side: str):
    text = path.read_text(encoding="utf-8")
    for net in ("USB_DP", "USB_DM", "LINK_TX", "LINK_RX"):
        if f'(label "{net}"' not in text:
            raise RuntimeError(f"{side} missing label {net}")
    if side == "left":
        # Both labels exist on both boards. The swap is which connector label
        # shares a stub with which UART label only through the ESD, so both
        # names are present. Confirm the strap note.
        if "GPIO19 10k to GND" not in text:
            raise RuntimeError("left strap text missing")
    else:
        if "GPIO19 10k to +3V3" not in text:
            raise RuntimeError("right strap text missing")


def main():
    if not SYMBOL_DIR.is_dir():
        raise SystemExit(f"KiCad symbols not found at {SYMBOL_DIR}. Run this inside the KiCad 10.0.7 image.")
    from place import build_pcb

    lib = Lib()
    sheets = {}
    projects = {}
    for side in ("left", "right"):
        print(f"building {side}", flush=True)
        sheet = build(side, lib)
        project = f"ergodox-rp2040-{side}"
        root_uuid = str(uuid.uuid4())
        proj_dir = ROOT / side
        proj_dir.mkdir(parents=True, exist_ok=True)
        sch_path = proj_dir / f"{project}.kicad_sch"
        write_schematic(sheet, project, sch_path, root_uuid)
        write_project(side, project, root_uuid)
        check_required_nets(sch_path, side)
        print(f"wrote {sch_path} parts={len(sheet.parts)} flags={len(sheet.flags)}", flush=True)
        sheets[side] = sheet
        projects[side] = project
    for side in ("right", "left"):
        build_pcb(sheets[side], side, projects[side])


if __name__ == "__main__":
    main()
