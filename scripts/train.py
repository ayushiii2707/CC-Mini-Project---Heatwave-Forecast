"""Train and evaluate the 7-day Tmax forecaster on real IMD data.

Direct multi-horizon forecasting: one model per horizon h = 1..7 predicts Tmax on day t+h
from the 7 days up to day t. Two model families (ridge regression, gradient boosting) are
compared with two baselines (persistence: Tmax(t+h) = Tmax(t); climatology: the normal).

Split (time-ordered by target day, no shuffling): train 2014-2022, validation 2023, test 2024.
Climatological normals are computed from the training years only. The model family and the
per-horizon alert margins are chosen on validation data only; 2024 is used once for reporting.

Usage: python scripts/train.py
Outputs: models/model.joblib, models/metrics.json
"""
from datetime import date
import json
from pathlib import Path
import sys
import time

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.cities import CITIES, COASTAL  # noqa: E402
from app.features import (FEATURE_NAMES, HORIZONS, WINDOW, build_features,  # noqa: E402
                          compute_normals, day_of_year)
from app.severity import LEVELS, classify  # noqa: E402

DATA = ROOT / "data" / "processed" / "city_tmax.csv"
MODELS = ROOT / "models"
TRAIN_YEARS, VAL_YEAR, TEST_YEAR = range(2014, 2023), 2023, 2024
ALERT_MARGINS = [round(0.25 * k, 2) for k in range(0, 25)]  # 0.0 .. 6.0 C
MIN_VALIDATED_F2 = 0.3  # below this, alerts for that horizon are flagged low-confidence
FAMILIES = {
    "ridge_regression": lambda: make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
    "gradient_boosting": lambda: HistGradientBoostingRegressor(
        max_iter=300, learning_rate=0.05, max_leaf_nodes=31, random_state=42),
}


def make_dataset(df: pd.DataFrame, normals: dict, horizon: int):
    """One row per (city, day t): features from days t-6..t, target Tmax at day t+horizon."""
    X, y, meta = [], [], []
    for city, g in df.groupby("city"):
        g = g.sort_values("date")
        dates = [date.fromisoformat(s) for s in g["date"]]
        t = g["tmax"].to_numpy()
        lat, lon = CITIES[city]
        for i in range(WINDOW - 1, len(t) - horizon):
            window, target = t[i - WINDOW + 1: i + 1], t[i + horizon]
            if np.isnan(window).any() or np.isnan(target):
                continue
            X.append(build_features(window, dates[i], lat, lon, normals[city], horizon))
            y.append(target)
            meta.append((city, dates[i + horizon]))
    return np.array(X), np.array(y), pd.DataFrame(meta, columns=["city", "target_date"])


def scores(y_true, y_pred) -> dict:
    return {"MAE": round(float(mean_absolute_error(y_true, y_pred)), 3),
            "RMSE": round(float(np.sqrt(mean_squared_error(y_true, y_pred))), 3)}


def severity_eval(meta, y_true, y_pred, normals, margin: float = 0.0, with_cm: bool = True) -> dict:
    """Compare alert level from (forecast + margin) vs alert level from the actual observed Tmax."""
    actual, predicted = [], []
    for (city, d), yt, yp in zip(meta.itertuples(index=False), y_true, y_pred):
        normal = normals[city][day_of_year(d)]
        actual.append(classify(yt, normal, city in COASTAL)["level"])
        predicted.append(classify(yp + margin, normal, city in COASTAL)["level"])
    actual_hw = np.array([a != "Normal" for a in actual])
    pred_hw = np.array([p != "Normal" for p in predicted])
    tp = int((actual_hw & pred_hw).sum())
    rec = tp / actual_hw.sum() if actual_hw.sum() else 0.0
    prec = tp / pred_hw.sum() if pred_hw.sum() else 0.0
    out = {
        "alert_margin_c": margin,
        "accuracy": round(float(np.mean(np.array(actual) == np.array(predicted))), 4),
        "heatwave_days_actual": int(actual_hw.sum()),
        "heatwave_alerts_issued": int(pred_hw.sum()),
        "heatwave_recall": round(rec, 3),
        "heatwave_precision": round(prec, 3),
        "heatwave_f2": round(5 * prec * rec / (4 * prec + rec), 3) if prec + rec else 0.0,
    }
    if with_cm:
        cm = pd.crosstab(pd.Series(actual, name="actual"), pd.Series(predicted, name="predicted"))
        out["confusion_matrix"] = {"rows=actual, cols=predicted": LEVELS,
                                   "values": cm.reindex(index=LEVELS, columns=LEVELS, fill_value=0).values.tolist()}
    return out


def main() -> None:
    df = pd.read_csv(DATA)
    df["year"] = df["date"].str[:4].astype(int)
    normals = {}
    for city, g in df[df["year"].isin(TRAIN_YEARS)].groupby("city"):
        normals[city] = compute_normals([date.fromisoformat(s) for s in g["date"]], g["tmax"].to_numpy())

    lag0, normal_col = FEATURE_NAMES.index("lag0"), FEATURE_NAMES.index("normal")
    per_h, fitted = {}, {name: {} for name in FAMILIES}
    for h in range(1, HORIZONS + 1):
        X, y, meta = make_dataset(df, normals, h)
        years = meta["target_date"].map(lambda d: d.year).to_numpy()
        tr, va, te = np.isin(years, list(TRAIN_YEARS)), years == VAL_YEAR, years == TEST_YEAR
        res = {"persistence_baseline": {"val": scores(y[va], X[va, lag0]), "test": scores(y[te], X[te, lag0])},
               "climatology_baseline": {"val": scores(y[va], X[va, normal_col]), "test": scores(y[te], X[te, normal_col])}}
        for name, make in FAMILIES.items():
            t0 = time.time()
            m = make().fit(X[tr], y[tr])
            fitted[name][h] = m
            res[name] = {"val": scores(y[va], m.predict(X[va])), "test": scores(y[te], m.predict(X[te])),
                         "train_seconds": round(time.time() - t0, 2)}
        per_h[h] = {"data": (X, y, meta, va, te), "models": res,
                    "samples": {"train": int(tr.sum()), "validation": int(va.sum()), "test": int(te.sum())}}
        print(f"h={h}: " + "  ".join(f"{k} val {v['val']['MAE']} test {v['test']['MAE']}" for k, v in res.items()))

    # Model family chosen by mean validation MAE over the 7 horizons (validation data only).
    mean_val = {n: float(np.mean([per_h[h]["models"][n]["val"]["MAE"] for h in per_h])) for n in FAMILIES}
    best = min(mean_val, key=mean_val.get)
    print(f"mean validation MAE: {mean_val} -> selected {best}")

    horizons_out, margins, confidence = [], {}, {}
    for h in range(1, HORIZONS + 1):
        X, y, meta, va, te = per_h[h]["data"]
        model = fitted[best][h]
        val_meta, test_meta = meta[va].reset_index(drop=True), meta[te].reset_index(drop=True)
        search = [severity_eval(val_meta, y[va], model.predict(X[va]), normals, m, with_cm=False)
                  for m in ALERT_MARGINS]
        best_search = max(search, key=lambda r: r["heatwave_f2"])
        margin = best_search["alert_margin_c"]
        margins[h] = margin
        confidence[h] = "validated" if best_search["heatwave_f2"] >= MIN_VALIDATED_F2 else "low"
        test_pred = model.predict(X[te])
        horizons_out.append({
            "horizon_days": h,
            "samples": per_h[h]["samples"],
            "models": per_h[h]["models"],
            "alert_margin_c": margin,
            "validation_f2": best_search["heatwave_f2"],
            "alert_confidence": confidence[h],
            "alert_margin_search_validation": search,
            "severity_test_forecast": severity_eval(test_meta, y[te], test_pred, normals, margin),
            "severity_test_forecast_no_margin": severity_eval(test_meta, y[te], test_pred, normals, 0.0),
            "severity_test_persistence": severity_eval(test_meta, y[te], X[te, lag0], normals),
            "test_mae_by_city": (pd.DataFrame({"city": test_meta["city"], "err": np.abs(test_pred - y[te])})
                                 .groupby("city")["err"].mean().round(3).to_dict()),
        })
        s = horizons_out[-1]["severity_test_forecast"]
        print(f"h={h}: margin {margin} C (val F2 {best_search['heatwave_f2']}, {confidence[h]}) -> test recall {s['heatwave_recall']} precision {s['heatwave_precision']}")

    metrics = {
        "data": "IMD Pune 1x1 deg gridded daily Tmax",
        "task": "direct multi-horizon forecast of daily Tmax, horizons 1-7 days",
        "split": {"train": "2014-2022", "validation": str(VAL_YEAR), "test": str(TEST_YEAR)},
        "features": FEATURE_NAMES,
        "selected_model": best,
        "min_validated_f2": MIN_VALIDATED_F2,
        "mean_validation_mae": {k: round(v, 3) for k, v in mean_val.items()},
        "horizons": horizons_out,
        "sklearn_version": sklearn.__version__,
    }
    MODELS.mkdir(exist_ok=True)
    joblib.dump({"models": {h: fitted[best][h] for h in range(1, HORIZONS + 1)}, "model_name": best,
                 "normals": normals, "alert_margins": margins, "alert_confidence": confidence, "horizons": HORIZONS,
                 "features": FEATURE_NAMES, "sklearn_version": sklearn.__version__},
                MODELS / "model.joblib")
    (MODELS / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print("saved models/model.joblib and models/metrics.json")


if __name__ == "__main__":
    main()
