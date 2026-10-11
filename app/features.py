"""Feature construction shared by training (scripts/train.py) and serving (app/main.py).

Input for one forecast: the last 7 observed daily Tmax values for a city
(oldest first, newest = "today") and today's date. One model per horizon
h = 1..7 predicts Tmax for day today + h (direct multi-horizon forecasting);
the features differ between horizons only in the target day's season and normal.
"""
from datetime import date, timedelta

import numpy as np

WINDOW = 7
HORIZONS = 7
FEATURE_NAMES = (
    [f"lag{k}" for k in range(WINDOW)]  # lag0 = today, lag6 = six days ago
    + ["mean7", "doy_sin", "doy_cos", "normal", "lat", "lon"]
)


def day_of_year(d: date) -> int:
    """1..366, with 29 Feb kept as 60 and later days of non-leap years shifted, so a
    calendar day maps to the same index in every year."""
    doy = d.timetuple().tm_yday
    is_leap = d.year % 4 == 0 and (d.year % 100 != 0 or d.year % 400 == 0)
    if not is_leap and doy >= 60:
        doy += 1
    return doy


def build_features(recent_tmax, today: date, lat: float, lon: float, normals,
                   horizon: int = 1) -> np.ndarray:
    """Return one feature row for the forecast of day `today + horizon`.
    `normals` is a length-367 array indexed by day_of_year."""
    recent = np.asarray(recent_tmax, dtype=float)
    if recent.shape != (WINDOW,):
        raise ValueError(f"expected {WINDOW} recent values, got {recent.shape}")
    target = today + timedelta(days=horizon)
    doy = day_of_year(target)
    angle = 2 * np.pi * doy / 366.0
    lags = recent[::-1]  # newest first
    return np.concatenate(
        [lags, [recent.mean(), np.sin(angle), np.cos(angle), normals[doy], lat, lon]]
    )


def compute_normals(dates, values, smooth_days: int = 15) -> np.ndarray:
    """Daily climatological normal Tmax (index 1..366) using a circular moving average."""
    sums = np.zeros(367)
    counts = np.zeros(367)
    for d, v in zip(dates, values):
        if not np.isnan(v):
            k = day_of_year(d)
            sums[k] += v
            counts[k] += 1
    raw = np.divide(sums[1:], counts[1:], out=np.full(366, np.nan), where=counts[1:] > 0)
    # fill any empty day (e.g. 29 Feb with few samples) from neighbours, then smooth circularly
    idx = np.arange(366)
    good = ~np.isnan(raw)
    raw = np.interp(idx, idx[good], raw[good], period=366)
    half = smooth_days // 2
    padded = np.concatenate([raw[-half:], raw, raw[:half]])
    smooth = np.convolve(padded, np.ones(smooth_days) / smooth_days, mode="valid")
    return np.concatenate([[np.nan], smooth])  # index 0 unused
