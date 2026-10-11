"""Convert IMD 1x1 degree gridded Tmax binary files into a per-city daily CSV.

IMD .GRD format (from the IMD download page): float32, 31 x 31 grid per day,
latitude 7.5N..37.5N and longitude 67.5E..97.5E in 1 degree steps,
longitude varying fastest; 99.9 marks missing (sea / outside India).

Usage: python scripts/prepare_data.py
Output: data/processed/city_tmax.csv  (date, city, lat, lon, tmax)
"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.cities import CITIES  # noqa: E402

RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed" / "city_tmax.csv"
N = 31
LAT0, LON0 = 7.5, 67.5
MISSING = 99.9


def read_grd(path: Path) -> np.ndarray:
    """Return array of shape (days, lat, lon) with NaN for missing cells."""
    raw = np.fromfile(path, dtype="<f4")
    if raw.size % (N * N) != 0:
        raise ValueError(f"{path.name}: size {raw.size} is not a multiple of 31x31")
    grid = raw.reshape(-1, N, N).astype("float64")
    grid[grid >= MISSING - 0.01] = np.nan
    return grid


def main() -> None:
    files = sorted(RAW.glob("Maxtemp_MaxT_*.GRD"))
    if not files:
        sys.exit("No .GRD files in data/raw. Run: bash scripts/download_imd.sh 2014 2024")

    rows = []
    for f in files:
        year = int(f.stem.split("_")[-1])
        grid = read_grd(f)
        dates = pd.date_range(f"{year}-01-01", periods=grid.shape[0], freq="D")
        if dates[-1].year != year:
            sys.exit(f"{f.name}: {grid.shape[0]} days does not fit year {year}")
        for city, (lat, lon) in CITIES.items():
            i, j = round(lat - LAT0), round(lon - LON0)
            for d, t in zip(dates, grid[:, i, j]):
                rows.append((d.date().isoformat(), city, lat, lon, t))
        print(f"{f.name}: {grid.shape[0]} days")

    df = pd.DataFrame(rows, columns=["date", "city", "lat", "lon", "tmax"])
    missing = df["tmax"].isna().groupby(df["city"]).mean()
    bad = missing[missing > 0.05]
    if not bad.empty:
        sys.exit(f"Cities with >5% missing values (check grid cell): {bad.to_dict()}")
    # Fill rare single-day gaps by linear interpolation within each city.
    df["tmax"] = df.groupby("city")["tmax"].transform(lambda s: s.interpolate(limit=3))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"Wrote {len(df)} rows for {df['city'].nunique()} cities "
          f"({df['date'].min()} to {df['date'].max()}) -> {OUT.relative_to(ROOT)}")
    print(df.groupby("city")["tmax"].agg(["min", "mean", "max"]).round(1).to_string())


if __name__ == "__main__":
    main()
