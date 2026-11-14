#!/usr/bin/env bash
# Write the JLCPCB files for both boards under hw/ergodox-rp2040/fab/<side>/:
# a Gerber and drill zip, the BOM and the placement (CPL) file.
#
#   tools/export_fab.sh
#
# Needs Docker with kicad/kicad:10.0.7-full. Run tools/build.sh first.
# This only writes files. It does not upload or order anything.
set -euo pipefail

repo=$(cd "$(dirname "$0")/../../.." && pwd)
hw=hw/ergodox-rp2040
layers=F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts

kicad() {
  docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -v "$repo":/work -w "/work/$hw" kicad/kicad:10.0.7-full "$@"
}

for side in right left; do
  project=$side/ergodox-rp2040-$side
  out=fab/$side
  rm -rf "${repo:?}/$hw/$out"
  mkdir -p "$repo/$hw/$out/gerber"
  kicad kicad-cli pcb export gerbers --layers "$layers" --subtract-soldermask \
    -o "$out/gerber" "$project.kicad_pcb"
  kicad kicad-cli pcb export drill --excellon-separate-th -o "$out/gerber" "$project.kicad_pcb"
  kicad kicad-cli sch export bom --exclude-dnp \
    --fields 'Value,Reference,Footprint,LCSC' --labels 'Comment,Designator,Footprint,LCSC' \
    --group-by 'Value,Footprint,LCSC' --ref-range-delimiter '' \
    -o "$out/ergodox-rp2040-$side-bom.csv" "$project.kicad_sch"
  kicad kicad-cli pcb export pos --format csv --units mm --side both \
    -o "$out/pos.csv" "$project.kicad_pcb"
  python3 - "$repo/$hw/$out" "$side" <<'PY'
"""Zip the Gerbers and turn KiCad's position file into JLCPCB's CPL columns."""
import csv, shutil, sys, zipfile
from pathlib import Path

out, side = Path(sys.argv[1]), sys.argv[2]
with zipfile.ZipFile(out / f"ergodox-rp2040-{side}-gerber.zip", "w", zipfile.ZIP_DEFLATED) as bundle:
    for path in sorted((out / "gerber").iterdir()):
        bundle.write(path, path.name)
with open(out / "pos.csv", newline="") as source, \
        open(out / f"ergodox-rp2040-{side}-cpl.csv", "w", newline="") as target:
    writer = csv.writer(target)
    writer.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
    for row in csv.DictReader(source):
        layer = {"top": "Top", "bottom": "Bottom"}[row["Side"]]
        writer.writerow([row["Ref"], f"{row['PosX']}mm", f"{row['PosY']}mm", layer, row["Rot"]])
(out / "pos.csv").unlink()
shutil.rmtree(out / "gerber")
PY
  echo "$side: $(ls "$repo/$hw/$out")"
done
