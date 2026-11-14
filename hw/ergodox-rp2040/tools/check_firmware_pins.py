#!/usr/bin/env python3
"""Fail if a ZMK overlay GPIO is missing from the schematic or used twice.

The allow-list is the RP2040 symbol pins named GPIO<n> on both halves.
A pin is dropped when its transformed connection point has a no_connect.
Left and right allow-sets must match. Rotation other than 0 is an error.

One image is a shield overlay, the quote-includes it follows, and
boards/rpi_pico_rp2040_zmk.overlay once. Angle-bracket includes are skipped.
PIO pinmux plus mosi-gpios on the same pin count as one led-data use.
The LED driver's clock and MISO pins carry no signal, so they may be
unconnected on the board; they must still not clash with another use.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMATICS = (
    ROOT / "left" / "ergodox-rp2040-left.kicad_sch",
    ROOT / "right" / "ergodox-rp2040-right.kicad_sch",
)
SHIELD = ROOT / "firmware" / "zmk" / "boards" / "shields" / "ergodox_rp2040"
BOARD_OVERLAY = SHIELD / "boards" / "rpi_pico_rp2040_zmk.overlay"
Y_SIGN = -1
TOL = 0.02
LIB_ID = "MCU_RaspberryPi:RP2040"
UNWIRED_OK = {"clk-gpios", "miso-gpios"}  # the LED SPI driver's unused lines


def tokenize(text: str):
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c == "(":
            yield "("
            i += 1
            continue
        if c == ")":
            yield ")"
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
            yield "".join(buf)
            continue
        j = i
        while j < n and not text[j].isspace() and text[j] not in "()":
            j += 1
        yield text[i:j]
        i = j


def parse(text: str):
    tokens = iter(tokenize(text))

    def read():
        tok = next(tokens)
        if tok == "(":
            node = []
            while True:
                nxt = read()
                if nxt is None:
                    break
                node.append(nxt)
            return node
        if tok == ")":
            return None
        return tok

    root = read()
    try:
        next(tokens)
    except StopIteration:
        return root
    raise RuntimeError("trailing tokens after schematic root")


def head(node):
    if isinstance(node, list) and node and not isinstance(node[0], list):
        return node[0]
    return None


def child(node, name):
    for item in node[1:]:
        if isinstance(item, list) and item and item[0] == name:
            return item
    return None


def walk(node, fn):
    if isinstance(node, list):
        fn(node)
        for item in node:
            walk(item, fn)


def gpio_number(name: str):
    match = re.fullmatch(r"GPIO(\d+)(?:/ADC\d)?", name)  # 26-29 are named GPIOn/ADCm
    if not match:
        return None
    return int(match.group(1))


def pin_record(pin_node):
    at = child(pin_node, "at")
    name = child(pin_node, "name")
    if not at or not name or len(at) < 3:
        return None
    label = name[1]
    if not isinstance(label, str):
        return None
    return float(at[1]), float(at[2]), label


def unit_style(symbol_name: str):
    parts = symbol_name.rsplit("_", 2)
    if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
        return int(parts[1]), int(parts[2])
    return None


def allowed_gpios(path: Path) -> set[int]:
    root = parse(path.read_text(encoding="utf-8"))
    symbol_pins = {}

    def collect_symbol(node):
        if head(node) != "symbol" or len(node) < 2 or not isinstance(node[1], str):
            return
        parsed = unit_style(node[1])
        if parsed != (1, 1):
            return
        if "RP2040" not in node[1]:
            return
        for item in node[1:]:
            if head(item) != "pin":
                continue
            rec = pin_record(item)
            if rec is None:
                continue
            number = gpio_number(rec[2])
            if number is None:
                continue
            symbol_pins[number] = (rec[0], rec[1])

    walk(root, collect_symbol)
    if not symbol_pins:
        raise RuntimeError(f"{path} has no RP2040 GPIO pins")

    instances = []

    def collect_instance(node):
        if head(node) != "symbol":
            return
        lib = child(node, "lib_id")
        if not lib or lib[1] != LIB_ID:
            return
        at = child(node, "at")
        unit = child(node, "unit")
        if not at or len(at) < 4:
            raise RuntimeError(f"{path} RP2040 instance has no rotation")
        rotation = float(at[3])
        if rotation != 0:
            raise RuntimeError(f"{path} RP2040 rotation is {rotation}, not 0")
        if unit and unit[1] not in ("1", 1):
            return
        instances.append((float(at[1]), float(at[2])))

    walk(root, collect_instance)
    if len(instances) != 1:
        raise RuntimeError(f"{path} has {len(instances)} RP2040 instances")
    origin_x, origin_y = instances[0]

    crosses = []

    def collect_nc(node):
        if head(node) != "no_connect":
            return
        at = child(node, "at")
        if at and len(at) >= 3:
            crosses.append((float(at[1]), float(at[2])))

    walk(root, collect_nc)

    def is_nc(x, y):
        return any(abs(x - cx) <= TOL and abs(y - cy) <= TOL for cx, cy in crosses)

    allowed = set()
    for number, (px, py) in symbol_pins.items():
        world_x = origin_x + px
        world_y = origin_y + Y_SIGN * py
        if not is_nc(world_x, world_y):
            allowed.add(number)
    return allowed


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//.*?$", "", text, flags=re.M)
    return text


def quote_includes(text: str, source: Path):
    found = []
    for match in re.finditer(r'^\s*#include\s+"([^"]+)"', text, flags=re.M):
        found.append((source.parent / match.group(1)).resolve())
    return found


def extract_uses(text: str):
    uses = []
    # Phandle arrays are <&gpio0 11 ...> , <&gpio0 10 ...> ; so read through
    # the semicolon. Pinmux names such as UART0_TX_P0 contain underscores.
    for match in re.finditer(r"([A-Za-z0-9_,-]+)\s*=\s*([^;]*);", text, flags=re.S):
        prop = match.group(1)
        body = match.group(2)
        if prop == "pinmux":
            for macro in re.findall(r"\b([A-Za-z][A-Za-z0-9_]*_P\d+)\b", body):
                pin = int(re.search(r"_P(\d+)$", macro).group(1))
                tag = "pio-pinmux" if macro.startswith("PIO") else macro
                uses.append((pin, tag))
            continue
        for pin in re.findall(r"&gpio\d+\s+(\d+)", body):
            uses.append((int(pin), prop))
        if prop == "gpios" and "&gpio" not in body:
            window = text[max(0, match.start() - 80) : match.start()]
            bare = re.match(r"\s*<\s*(\d+)\b", body)
            if bare and "gpio-hog" in window:
                uses.append((int(bare.group(1)), "gpio-hog"))
    return uses


def load_image(overlay: Path):
    seen = set()
    uses = []
    files = []

    def load(path: Path):
        path = path.resolve()
        if path in seen:
            return
        if not path.is_file():
            raise RuntimeError(f"missing include {path}")
        seen.add(path)
        files.append(path)
        raw = strip_comments(path.read_text(encoding="utf-8"))
        for inc in quote_includes(raw, path):
            load(inc)
        body = re.sub(r'^\s*#include\s+"[^"]+"', "", raw, flags=re.M)
        uses.extend(extract_uses(body))

    load(overlay)
    if BOARD_OVERLAY.resolve() not in seen:
        load(BOARD_OVERLAY)
    return uses, files


def normalize(uses):
    grouped = {}
    for pin, tag in uses:
        grouped.setdefault(pin, []).append(tag)
    errors = []
    result = {}
    for pin, tags in sorted(grouped.items()):
        counts = Counter(tags)
        if counts["pio-pinmux"] and counts["mosi-gpios"]:
            if counts["pio-pinmux"] > 1 or counts["mosi-gpios"] > 1:
                errors.append(f"GPIO{pin} led-data is listed more than once")
            counts["pio-pinmux"] -= 1
            counts["mosi-gpios"] -= 1
            if counts["pio-pinmux"] == 0:
                del counts["pio-pinmux"]
            if counts["mosi-gpios"] == 0:
                del counts["mosi-gpios"]
            counts["led-data"] += 1
        for tag, count in counts.items():
            if count > 1:
                errors.append(f"GPIO{pin} {tag} is used {count} times")
        live = {tag: count for tag, count in counts.items() if count}
        if len(live) > 1:
            errors.append(f"GPIO{pin} is used as {sorted(live)}")
        elif len(live) == 1:
            result[pin] = next(iter(live))
    return result, errors


def check_image(uses, allowed: set[int]):
    mapped, errors = normalize(uses)
    for pin, tag in sorted(mapped.items()):
        if pin not in allowed and tag not in UNWIRED_OK:
            errors.append(f"GPIO{pin} is not a connected RP2040 GPIO on the schematic")
    return mapped, errors


def self_test(allowed: set[int]):
    duplicate, errors = check_image([(12, "col-gpios"), (12, "col-gpios")], allowed)
    if not errors:
        raise RuntimeError("duplicate GPIO check did not fail")
    conflict, errors = check_image([(2, "pio-pinmux"), (2, "mosi-gpios"), (2, "row-gpios")], allowed)
    if not errors:
        raise RuntimeError("mixed-function GPIO check did not fail")
    led, errors = check_image([(2, "pio-pinmux"), (2, "mosi-gpios")], allowed)
    if errors or led.get(2) != "led-data":
        raise RuntimeError(f"led-data collapse failed: {led} {errors}")
    missing, errors = check_image([(31, "row-gpios")], allowed)
    if not any("not a connected" in item for item in errors):
        raise RuntimeError("off-schematic GPIO check did not fail")
    del duplicate, conflict, missing


def main() -> int:
    sets = []
    for path in SCHEMATICS:
        allowed = allowed_gpios(path)
        print(f"{path.name}: {len(allowed)} GPIOs {sorted(allowed)}")
        sets.append(allowed)
    if sets[0] != sets[1]:
        print("left and right GPIO allow-lists differ", file=sys.stderr)
        print("left only", sorted(sets[0] - sets[1]), file=sys.stderr)
        print("right only", sorted(sets[1] - sets[0]), file=sys.stderr)
        return 1
    allowed = sets[0]
    self_test(allowed)

    overlays = sorted(SHIELD.glob("ergodox_rp2040_*.overlay"))
    if len(overlays) != 4:
        print(f"expected 4 shield overlays, found {len(overlays)}", file=sys.stderr)
        return 1
    failed = False
    for overlay in overlays:
        uses, files = load_image(overlay)
        mapped, errors = check_image(uses, allowed)
        print(f"{overlay.name}: {len(mapped)} pins from {len(files)} files")
        for pin, tag in sorted(mapped.items()):
            print(f"  GPIO{pin}: {tag}")
        if errors:
            failed = True
            for error in errors:
                print(f"  ERROR {error}", file=sys.stderr)
    if failed:
        return 1
    print("pin check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
