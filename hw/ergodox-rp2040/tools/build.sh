#!/usr/bin/env bash
# Generate, route and check both ErgoDox RP2040 boards.
#
#   tools/build.sh
#
# Needs Docker with kicad/kicad:10.0.7-full.
# finish.py takes one to three hours per half; the halves run in parallel.
set -euo pipefail

repo=$(cd "$(dirname "$0")/../../.." && pwd)
hw=hw/ergodox-rp2040
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

kicad() {
  docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -v "$repo":/work -v "$work":/route -w "/work/$hw" kicad/kicad:10.0.7-full "$@"
}

kicad python3 tools/build_board.py

route() {
  local side=$1
  local project=$side/ergodox-rp2040-$side
  # The open links of the placed board, for finish.py.
  kicad kicad-cli pcb drc --refill-zones --severity-error --format json \
    -o "/route/$side-open.json" "$project.kicad_pcb" >/dev/null
  # Saving the board rewrites the project file with KiCad's defaults; keep the generated one.
  cp "$repo/$hw/$project.kicad_pro" "$work/$side.kicad_pro"
  kicad python3 tools/finish.py "$side" "/route/$side-open.json" 2>&1 | grep -v "memory leak"
  cp "$work/$side.kicad_pro" "$repo/$hw/$project.kicad_pro"
}
route right & right=$!
route left & left=$!
wait "$right"
wait "$left"

mkdir -p "$repo/$hw/reports"
for side in right left; do
  project=$side/ergodox-rp2040-$side
  kicad kicad-cli sch erc --severity-error --severity-warning \
    -o "reports/$side-erc.rpt" "$project.kicad_sch"
  # Fills the zones, saves them into the board, then checks it.
  kicad kicad-cli pcb drc --refill-zones --save-board --schematic-parity \
    --severity-error --format json -o "reports/$side-drc.json" "$project.kicad_pcb"
  cp "$work/$side.kicad_pro" "$repo/$hw/$project.kicad_pro"
  python3 - "$repo/$hw/reports/$side-drc.json" "$side" <<'PY'
import json, sys
report = json.load(open(sys.argv[1]))
print(f"{sys.argv[2]}: {len(report['violations'])} DRC errors, "
      f"{len(report['unconnected_items'])} unconnected, "
      f"{len(report['schematic_parity'])} schematic mismatches")
PY
done
