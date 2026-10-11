"""HeatGuard API (backend): 7-day Tmax forecast + IMD-rule heatwave alerts.

The web frontend is a separate service (frontend/) that calls this API through its
/api/ reverse proxy. Interactive API documentation is served at /docs.

Endpoints
  GET  /            service information
  GET  /health      liveness/readiness (used by Docker HEALTHCHECK and Kubernetes probes)
  GET  /cities      supported locations (IMD grid cells)
  GET  /observed    observed IMD Tmax history for a city up to a date (+ actual next 7 days)
  GET  /outlook     7-day forecast for every city from the IMD observations up to a date
  GET  /model-info  evaluation metrics of the deployed models, per forecast horizon
  POST /predict     7-day forecast from the last 7 daily Tmax values for one city
"""
import csv
import datetime as dt
from datetime import date, timedelta
import json
import os
from pathlib import Path
import socket
import time

import joblib
import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from app.cities import CITIES, COASTAL
from app.features import WINDOW, build_features, day_of_year
from app.severity import ADVICE, LEVELS, classify

ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = Path(os.getenv("MODEL_PATH", ROOT / "models" / "model.joblib"))
METRICS_PATH = MODEL_PATH.with_name("metrics.json")
DATA_PATH = Path(os.getenv("DATA_PATH", ROOT / "data" / "processed" / "city_tmax.csv"))
VERSION = "2.0"
NOTE = "Educational prototype. Official heatwave warnings are issued by the India Meteorological Department."

app = FastAPI(title="HeatGuard API - 7-day heatwave forecast & early warning", version=VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])


def load_bundle():
    try:
        return joblib.load(MODEL_PATH)
    except FileNotFoundError:
        return None


def load_metrics():
    return json.loads(METRICS_PATH.read_text()) if METRICS_PATH.exists() else None


def load_observations():
    obs = {c: {} for c in CITIES}
    if DATA_PATH.exists():
        with open(DATA_PATH) as f:
            for row in csv.DictReader(f):
                if row["tmax"]:
                    obs[row["city"]][date.fromisoformat(row["date"])] = float(row["tmax"])
    return obs


BUNDLE = load_bundle()
METRICS = load_metrics()
OBS = load_observations()
# Typical error per horizon (validation MAE of the deployed model) shown as forecast uncertainty.
VAL_MAE = ({h["horizon_days"]: h["models"][METRICS["selected_model"]]["val"]["MAE"] for h in METRICS["horizons"]}
           if METRICS else {})


class PredictRequest(BaseModel):
    city: str = Field(examples=["Delhi"])
    date: dt.date = Field(description="'Today': the date of the newest value in recent_tmax",
                          examples=["2024-05-27"])
    recent_tmax: list[float] = Field(min_length=WINDOW, max_length=WINDOW,
                                     description="Last 7 daily max temperatures in C, oldest first",
                                     examples=[[42.2, 41.1, 40.2, 41.2, 43.5, 44.9, 45.1]])

    @field_validator("recent_tmax")
    @classmethod
    def plausible(cls, values):
        for v in values:
            if not -10.0 <= v <= 55.0:
                raise ValueError(f"temperature {v} C is outside the plausible range -10..55 C")
        return values


def require_city(city: str) -> str:
    if city not in CITIES:
        raise HTTPException(404, f"unknown city '{city}'. Supported: {', '.join(CITIES)}")
    return city


def require_model():
    if BUNDLE is None:
        raise HTTPException(503, f"model not loaded from {MODEL_PATH}")


def window_for(city: str, today: date):
    days = [today - timedelta(days=k) for k in range(WINDOW - 1, -1, -1)]
    series = OBS[city]
    if not all(d in series for d in days):
        have = sorted(series)
        span = f"{have[WINDOW - 1]} to {have[-1]}" if have else "none"
        raise HTTPException(404, f"no IMD observations for {city} for the 7 days up to {today} (available: {span})")
    return [round(series[d], 1) for d in days]


def forecast_7day(city: str, today: date, recent_tmax) -> dict:
    """Run the 7 horizon models and apply the IMD rules to each forecast day."""
    lat, lon = CITIES[city]
    normals = BUNDLE["normals"][city]
    coastal = city in COASTAL
    X = np.vstack([build_features(recent_tmax, today, lat, lon, normals, h)
                   for h in range(1, BUNDLE["horizons"] + 1)])
    days = []
    for h, model in BUNDLE["models"].items():
        tmax = float(model.predict(X[h - 1: h])[0])
        target = today + timedelta(days=h)
        normal = float(normals[day_of_year(target)])
        # Alerts use the upper-bound forecast (forecast + margin chosen on validation data),
        # because a missed heatwave is costlier than a false alarm.
        margin = float(BUNDLE["alert_margins"][h])
        sev = classify(tmax + margin, normal, coastal)
        days.append({
            "day": h,
            "date": target,
            "forecast_tmax": round(tmax, 1),
            "typical_error_c": VAL_MAE.get(h),
            "upper_forecast_tmax": round(tmax + margin, 1),
            "alert_margin_c": margin,
            "normal_tmax": round(normal, 1),
            "departure_from_normal": round(tmax - normal, 1),
            "alert": sev["level"],
            "alert_confidence": BUNDLE["alert_confidence"][h],
            "rule": sev["rule"],
        })
    peak = max(days, key=lambda d: d["forecast_tmax"])
    worst = max(LEVELS.index(d["alert"]) for d in days)
    validated_worst = max([LEVELS.index(d["alert"]) for d in days if d["alert_confidence"] == "validated"] or [0])
    return {
        "city": city, "issued_for": today, "coastal": coastal, "lat": lat, "lon": lon,
        "days": days,
        "peak": {"date": peak["date"], "forecast_tmax": peak["forecast_tmax"]},
        "highest_alert": LEVELS[worst],
        "highest_validated_alert": LEVELS[validated_worst],
        "first_alert_day": next((d["day"] for d in days if d["alert"] != "Normal"), None),
        "advisory": ADVICE[LEVELS[worst]],
        "model": BUNDLE["model_name"],
    }


@app.get("/")
def root():
    return {"service": "HeatGuard API", "version": VERSION, "docs": "/docs", "health": "/health"}


@app.get("/health")
def health():
    require_model()
    return {"status": "ok", "version": VERSION, "model": BUNDLE["model_name"],
            "horizons": BUNDLE["horizons"], "pod": socket.gethostname()}


@app.get("/cities")
def cities():
    return [{"city": c, "lat": lat, "lon": lon, "coastal": c in COASTAL}
            for c, (lat, lon) in CITIES.items()]


@app.get("/observed")
def observed(city: str, date_: date = Query(alias="date"), days: int = Query(7, ge=7, le=90)):
    """Observed IMD Tmax for the `days` days up to `date` (with normals), plus the actual next 7 days."""
    require_city(city)
    recent = window_for(city, date_)
    series = OBS[city]
    normals = BUNDLE["normals"][city] if BUNDLE else None
    hist = [date_ - timedelta(days=k) for k in range(days - 1, -1, -1)]
    nxt = [date_ + timedelta(days=k) for k in range(1, 8)]
    return {
        "city": city, "date": date_, "recent_tmax": recent,
        "history": [{"date": d, "tmax": round(series[d], 1) if d in series else None,
                     "normal": round(float(normals[day_of_year(d)]), 1) if normals is not None else None}
                    for d in hist],
        "actual_next_7": [{"date": d, "tmax": round(series[d], 1) if d in series else None} for d in nxt],
        "actual_next_day_tmax": round(series[nxt[0]], 1) if nxt[0] in series else None,
        "source": "IMD Pune 1x1 deg gridded daily Tmax",
    }


@app.get("/outlook")
def outlook(date_: date = Query(alias="date")):
    """7-day forecast for every city, driven by the real IMD observations up to `date`."""
    require_model()
    t0 = time.perf_counter()
    out = []
    for city in CITIES:
        f = forecast_7day(city, date_, window_for(city, date_))
        out.append({k: f[k] for k in ("city", "lat", "lon", "coastal", "peak", "highest_alert",
                                       "highest_validated_alert", "first_alert_day")}
                   | {"today_tmax": round(OBS[city][date_], 1),
                      "alerts": [d["alert"] for d in f["days"]],
                      "forecast_tmax": [d["forecast_tmax"] for d in f["days"]]})
    out.sort(key=lambda c: (-LEVELS.index(c["highest_alert"]), -c["peak"]["forecast_tmax"]))
    return {"date": date_, "cities": out, "inference_ms": round((time.perf_counter() - t0) * 1000, 2),
            "pod": socket.gethostname(), "note": NOTE}


@app.get("/model-info")
def model_info():
    if METRICS is None:
        raise HTTPException(404, "metrics.json not found")
    best = METRICS["selected_model"]
    return {
        "data": METRICS["data"], "task": METRICS["task"], "split": METRICS["split"],
        "selected_model": best, "mean_validation_mae": METRICS["mean_validation_mae"],
        "min_validated_f2": METRICS["min_validated_f2"],
        "horizons": [{
            "day": h["horizon_days"],
            "test_mae": {k: v["test"]["MAE"] for k, v in h["models"].items()},
            "alert_margin_c": h["alert_margin_c"],
            "alert_confidence": h["alert_confidence"],
            "alert_recall": h["severity_test_forecast"]["heatwave_recall"],
            "alert_precision": h["severity_test_forecast"]["heatwave_precision"],
            "heatwave_days_actual": h["severity_test_forecast"]["heatwave_days_actual"],
        } for h in METRICS["horizons"]],
    }


@app.post("/predict")
def predict(req: PredictRequest):
    require_model()
    require_city(req.city)
    t0 = time.perf_counter()
    f = forecast_7day(req.city, req.date, req.recent_tmax)
    return f | {"inference_ms": round((time.perf_counter() - t0) * 1000, 2),
                "pod": socket.gethostname(), "note": NOTE}
