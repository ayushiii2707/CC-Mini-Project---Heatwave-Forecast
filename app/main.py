"""HeatGuard API: next-day Tmax forecast + IMD-rule heatwave alert.

Endpoints
  GET  /            dashboard (static HTML)
  GET  /health      liveness/readiness (used by Kubernetes probes)
  GET  /cities      supported locations
  GET  /observed    last 7 observed IMD Tmax values for a city/date (+ actual next day)
  GET  /model-info  evaluation metrics of the deployed model
  POST /predict     forecast for tomorrow from 7 recent Tmax values
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
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from app.cities import CITIES, COASTAL
from app.features import WINDOW, build_features, day_of_year
from app.severity import classify

ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = Path(os.getenv("MODEL_PATH", ROOT / "models" / "model.joblib"))
METRICS_PATH = MODEL_PATH.with_name("metrics.json")
DATA_PATH = Path(os.getenv("DATA_PATH", ROOT / "data" / "processed" / "city_tmax.csv"))

app = FastAPI(title="HeatGuard - Heatwave Forecast & Early Warning", version="1.0")


def load_bundle():
    try:
        return joblib.load(MODEL_PATH)
    except FileNotFoundError:
        return None


def load_observations():
    obs = {c: {} for c in CITIES}
    if DATA_PATH.exists():
        with open(DATA_PATH) as f:
            for row in csv.DictReader(f):
                if row["tmax"]:
                    obs[row["city"]][date.fromisoformat(row["date"])] = float(row["tmax"])
    return obs


BUNDLE = load_bundle()
OBS = load_observations()


class PredictRequest(BaseModel):
    city: str = Field(examples=["Delhi"])
    date: dt.date = Field(description="'Today': the date of the newest value in recent_tmax",
                       examples=["2024-05-27"])
    recent_tmax: list[float] = Field(min_length=WINDOW, max_length=WINDOW,
                                     description="Last 7 daily max temperatures in C, oldest first",
                                     examples=[[44.1, 44.6, 45.0, 45.3, 45.6, 46.2, 46.4]])

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


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/health")
def health():
    if BUNDLE is None:
        raise HTTPException(503, f"model not loaded from {MODEL_PATH}")
    return {"status": "ok", "model": BUNDLE["model_name"], "pod": socket.gethostname()}


@app.get("/cities")
def cities():
    return [{"city": c, "lat": lat, "lon": lon, "coastal": c in COASTAL}
            for c, (lat, lon) in CITIES.items()]


@app.get("/observed")
def observed(city: str, date_: date = Query(alias="date")):
    require_city(city)
    days = [date_ - timedelta(days=k) for k in range(WINDOW - 1, -1, -1)]
    series = OBS[city]
    if not all(d in series for d in days):
        have = sorted(series)
        span = f"{have[WINDOW - 1]} to {have[-1]}" if have else "none"
        raise HTTPException(404, f"no IMD observations for {city} 7 days up to {date_} (available: {span})")
    nxt = date_ + timedelta(days=1)
    return {"city": city, "date": date_, "recent_tmax": [round(series[d], 1) for d in days],
            "actual_next_day_tmax": round(series[nxt], 1) if nxt in series else None, "source": "IMD 1x1 deg gridded Tmax"}


@app.get("/model-info")
def model_info():
    if not METRICS_PATH.exists():
        raise HTTPException(404, "metrics.json not found")
    m = json.loads(METRICS_PATH.read_text())
    return {k: m[k] for k in ("data", "split", "selected_model", "models", "alert_margin_c",
                             "severity_on_test_forecast", "severity_on_test_forecast_no_margin",
                             "severity_on_test_persistence")}


@app.post("/predict")
def predict(req: PredictRequest):
    if BUNDLE is None:
        raise HTTPException(503, "model not loaded")
    require_city(req.city)
    t0 = time.perf_counter()
    lat, lon = CITIES[req.city]
    normals = BUNDLE["normals"][req.city]
    x = build_features(req.recent_tmax, req.date, lat, lon, normals)
    forecast = float(BUNDLE["model"].predict(x.reshape(1, -1))[0])
    target = req.date + timedelta(days=1)
    normal = float(normals[day_of_year(target)])
    # Alert uses the upper-bound forecast (forecast + margin chosen on validation data),
    # because a missed heatwave is costlier than a false alarm.
    margin = float(BUNDLE.get("alert_margin", 0.0))
    upper = forecast + margin
    sev = classify(upper, normal, req.city in COASTAL)
    return {
        "city": req.city,
        "forecast_date": target,
        "forecast_tmax": round(forecast, 1),
        "upper_forecast_tmax": round(upper, 1),
        "alert_margin_c": margin,
        "normal_tmax": round(normal, 1),
        "alert": sev["level"],
        "departure_from_normal": sev["departure_from_normal"],
        "rule": sev["rule"],
        "advisory": sev["advisory"],
        "model": BUNDLE["model_name"],
        "inference_ms": round((time.perf_counter() - t0) * 1000, 2),
        "pod": socket.gethostname(),
        "note": "Educational prototype. Official warnings: India Meteorological Department.",
    }
