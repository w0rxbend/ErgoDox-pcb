#!/usr/bin/env bash
# Generate, route and check both ErgoDox RP2040 boards.
#
#   tools/build.sh /path/to/freerouting-2.5.0.jar
#
# Needs Docker with kicad/kicad:10.0.7-full, and Java 21+ for Freerouting.
# Routing takes up to 30 minutes per half; the halves run in parallel.
set -euo pipefail

jar=${1:?usage: build.sh /path/to/freerouting.jar}
[[ -f $jar ]] || { echo "no such file: $jar" >&2; exit 1; }

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
  kicad python3 tools/route.py export "$side" "/route/$side.dsn"
  # No fanout stage: it puts a via on every SMD pin and chokes the RP2040.
  # place.py already ties the power pads to the planes.
  java -jar "$jar" -de "$work/$side.dsn" -do "$work/$side.ses" \
    --router.autorouter.max_passes=120 --router.fanout.enabled=false \
    --gui.enabled=false >"$work/$side-router.log" 2>&1
  kicad python3 tools/route.py import "$side" "/route/$side.ses"
}
route right &
route left &
wait

mkdir -p "$repo/$hw/reports"
for side in right left; do
  project=$side/ergodox-rp2040-$side
  kicad kicad-cli sch erc --severity-error --severity-warning \
    -o "reports/$side-erc.rpt" "$project.kicad_sch"
  # Fills the zones, saves them into the board, then checks it.
  kicad kicad-cli pcb drc --refill-zones --save-board --schematic-parity \
    --severity-error --format json -o "reports/$side-drc.json" "$project.kicad_pcb"
  python3 - "$repo/$hw/reports/$side-drc.json" "$side" <<'PY'
import json, sys
report = json.load(open(sys.argv[1]))
print(f"{sys.argv[2]}: {len(report['violations'])} DRC errors, "
      f"{len(report['unconnected_items'])} unconnected, "
      f"{len(report['schematic_parity'])} schematic mismatches")
PY
done
