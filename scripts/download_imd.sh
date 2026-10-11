#!/usr/bin/env bash
# Download IMD Pune 1x1 degree daily gridded MAXIMUM temperature (.GRD binary) for the given years.
# Source page: https://www.imdpune.gov.in/cmpg/Griddata/Max_1_Bin.html (form posts "maxtemp=<year>").
# The IMD server is slow and sometimes times out, so each year is retried.
# Usage: bash scripts/download_imd.sh 2014 2024
set -u
START=${1:-2014}
END=${2:-2024}
OUT="$(dirname "$0")/../data/raw"
mkdir -p "$OUT"

for year in $(seq "$START" "$END"); do
  file="$OUT/Maxtemp_MaxT_${year}.GRD"
  if [ -f "$file" ] && [ "$(wc -c < "$file")" -ge 1403060 ]; then
    echo "$year: already downloaded"; continue
  fi
  for attempt in 1 2 3 4; do
    curl -sS -m 150 -X POST -d "maxtemp=${year}" -o "$file" \
      https://www.imdpune.gov.in/cmpg/Griddata/maxtemp.php
    size=$(wc -c < "$file" 2>/dev/null || echo 0)
    # 31 x 31 grid x 4 bytes x 365 (or 366) days
    if [ "$size" -eq 1403060 ] || [ "$size" -eq 1406904 ]; then
      echo "$year: OK ($size bytes)"; break
    fi
    echo "$year: attempt $attempt failed (size=$size), retrying..."; sleep 3
  done
done
