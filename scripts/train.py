"""Train and evaluate the next-day Tmax forecaster on real IMD data.

Split (time-ordered, no shuffling): train 2014-2022, validation 2023, test 2024.
Climatological normals are computed from the training years only.

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
from app.features import FEATURE_NAMES, WINDOW, build_features, compute_normals  # noqa: E402
from app.severity import LEVELS, classify  # noqa: E402

DATA = ROOT / "data" / "processed" / "city_tmax.csv"
MODELS = ROOT / "models"
TRAIN_YEARS, VAL_YEAR, TEST_YEAR = range(2014, 2023), 2023, 2024


def make_dataset(df: pd.DataFrame, normals: dict):
    """One row per (city, day t) with features from days t-6..t and target Tmax at t+1."""
    X, y, meta = [], [], []
    for city, g in df.groupby("city"):
        g = g.sort_values("date")
        dates = [date.fromisoformat(s) for s in g["date"]]
        t = g["tmax"].to_numpy()
        lat, lon = CITIES[city]
        for i in range(WINDOW - 1, len(t) - 1):
            window, target = t[i - WINDOW + 1: i + 1], t[i + 1]
            if np.isnan(window).any() or np.isnan(target):
                continue
            X.append(build_features(window, dates[i], lat, lon, normals[city]))
            y.append(target)
            meta.append((city, dates[i + 1]))
    return np.array(X), np.array(y), pd.DataFrame(meta, columns=["city", "target_date"])


def scores(y_true, y_pred) -> dict:
    return {
        "MAE": round(float(mean_absolute_error(y_true, y_pred)), 3),
        "RMSE": round(float(np.sqrt(mean_squared_error(y_true, y_pred))), 3),
    }


ALERT_MARGINS = [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0]


def severity_eval(meta, y_true, y_pred, normals, margin: float = 0.0) -> dict:
    """Compare alert level from (forecast + margin) vs alert level from the actual observed Tmax."""
    from app.features import day_of_year
    actual, predicted = [], []
    for (city, d), yt, yp in zip(meta.itertuples(index=False), y_true, y_pred):
        normal = normals[city][day_of_year(d)]
        actual.append(classify(yt, normal, city in COASTAL)["level"])
        predicted.append(classify(yp + margin, normal, city in COASTAL)["level"])
    cm = pd.crosstab(pd.Series(actual, name="actual"), pd.Series(predicted, name="predicted"))
    cm = cm.reindex(index=LEVELS, columns=LEVELS, fill_value=0)
    actual_hw = np.array([a != "Normal" for a in actual])
    pred_hw = np.array([p != "Normal" for p in predicted])
    tp = int((actual_hw & pred_hw).sum())
    rec = tp / actual_hw.sum() if actual_hw.sum() else 0.0
    prec = tp / pred_hw.sum() if pred_hw.sum() else 0.0
    return {
        "alert_margin_c": margin,
        "confusion_matrix": {"rows=actual, cols=predicted": LEVELS, "values": cm.values.tolist()},
        "accuracy": round(float(np.mean(np.array(actual) == np.array(predicted))), 4),
        "heatwave_days_actual": int(actual_hw.sum()),
        "heatwave_recall": round(tp / actual_hw.sum(), 3) if actual_hw.sum() else None,
        "heatwave_precision": round(tp / pred_hw.sum(), 3) if pred_hw.sum() else None,
        "heatwave_f2": round(5 * prec * rec / (4 * prec + rec), 3) if prec + rec else 0.0,
    }


def main() -> None:
    df = pd.read_csv(DATA)
    df["year"] = df["date"].str[:4].astype(int)
    train_df = df[df["year"].isin(TRAIN_YEARS)]
    normals = {}
    for city, g in train_df.groupby("city"):
        normals[city] = compute_normals([date.fromisoformat(s) for s in g["date"]], g["tmax"].to_numpy())

    # Build all samples once, then split by the year of the target day.
    X, y, meta = make_dataset(df, normals)
    years = meta["target_date"].map(lambda d: d.year).to_numpy()
    tr, va, te = np.isin(years, list(TRAIN_YEARS)), years == VAL_YEAR, years == TEST_YEAR
    print(f"samples: train={tr.sum()} val={va.sum()} test={te.sum()}  features={len(FEATURE_NAMES)}")

    lag0 = FEATURE_NAMES.index("lag0")
    candidates = {
        "ridge_regression": make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
        "gradient_boosting": HistGradientBoostingRegressor(
            max_iter=300, learning_rate=0.05, max_leaf_nodes=31, random_state=42),
    }
    results = {"persistence_baseline": {
        "val": scores(y[va], X[va, lag0]), "test": scores(y[te], X[te, lag0])}}
    fitted = {}
    for name, model in candidates.items():
        t0 = time.time()
        model.fit(X[tr], y[tr])
        fitted[name] = model
        results[name] = {"val": scores(y[va], model.predict(X[va])),
                         "test": scores(y[te], model.predict(X[te])),
                         "train_seconds": round(time.time() - t0, 2)}

    best = min(fitted, key=lambda n: results[n]["val"]["MAE"])  # chosen on validation only
    model = fitted[best]
    test_pred = model.predict(X[te])
    print(json.dumps(results, indent=2))
    print(f"selected model (lowest validation MAE): {best}")

    # Early-warning margin: alert on (forecast + margin). Regression under-predicts extremes,
    # so a margin is chosen on the 2023 validation year by F2 (recall weighted over precision).
    val_meta = meta[va].reset_index(drop=True)
    val_pred = model.predict(X[va])
    margin_search = [severity_eval(val_meta, y[va], val_pred, normals, m) for m in ALERT_MARGINS]
    for r in margin_search:
        r.pop("confusion_matrix")
    margin = max(margin_search, key=lambda r: r["heatwave_f2"])["alert_margin_c"]
    print(f"alert margin chosen on validation: {margin} C")

    test_meta = meta[te].reset_index(drop=True)
    per_city = (pd.DataFrame({"city": test_meta["city"], "err": np.abs(test_pred - y[te])})
                .groupby("city")["err"].mean().round(3).to_dict())
    metrics = {
        "data": "IMD Pune 1x1 deg gridded daily Tmax",
        "split": {"train": "2014-2022", "validation": str(VAL_YEAR), "test": str(TEST_YEAR)},
        "samples": {"train": int(tr.sum()), "validation": int(va.sum()), "test": int(te.sum())},
        "features": FEATURE_NAMES,
        "models": results,
        "selected_model": best,
        "test_mae_by_city": per_city,
        "alert_margin_search_validation": margin_search,
        "alert_margin_c": margin,
        "severity_on_test_forecast": severity_eval(test_meta, y[te], test_pred, normals, margin),
        "severity_on_test_forecast_no_margin": severity_eval(test_meta, y[te], test_pred, normals, 0.0),
        "severity_on_test_persistence": severity_eval(test_meta, y[te], X[te, lag0], normals),
        "sklearn_version": sklearn.__version__,
    }
    MODELS.mkdir(exist_ok=True)
    joblib.dump({"model": model, "model_name": best, "normals": normals, "alert_margin": margin,
                 "features": FEATURE_NAMES, "sklearn_version": sklearn.__version__},
                MODELS / "model.joblib")
    (MODELS / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps({k: metrics[k] for k in ("test_mae_by_city", "alert_margin_c",
                                              "severity_on_test_forecast",
                                              "severity_on_test_forecast_no_margin",
                                              "severity_on_test_persistence")}, indent=2))
    print("saved models/model.joblib and models/metrics.json")


if __name__ == "__main__":
    main()
