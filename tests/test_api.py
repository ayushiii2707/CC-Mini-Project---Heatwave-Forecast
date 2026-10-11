"""API and AI-component tests. Run: pytest -v"""
from datetime import date

from fastapi.testclient import TestClient

from app.features import day_of_year
from app.main import app
from app.severity import classify

client = TestClient(app)
GOOD = {"city": "Delhi", "date": "2024-05-27",
        "recent_tmax": [44.1, 44.6, 45.0, 45.3, 45.6, 46.2, 46.4]}


# ---- representative inputs -------------------------------------------------
def test_health_reports_loaded_model():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok" and r.json()["horizons"] == 7


def test_cities_list():
    names = [c["city"] for c in client.get("/cities").json()]
    assert "Delhi" in names and len(names) == 10


def test_observed_returns_real_imd_window():
    r = client.get("/observed", params={"city": "Delhi", "date": "2024-05-27"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["recent_tmax"]) == 7 and body["actual_next_day_tmax"] is not None
    assert len(body["actual_next_7"]) == 7


def test_observed_history_for_charts():
    r = client.get("/observed", params={"city": "Delhi", "date": "2024-05-27", "days": 30})
    hist = r.json()["history"]
    assert len(hist) == 30 and hist[-1]["date"] == "2024-05-27" and hist[-1]["normal"] is not None


def test_predict_returns_7_consecutive_days():
    body = client.post("/predict", json=GOOD).json()
    assert [d["day"] for d in body["days"]] == [1, 2, 3, 4, 5, 6, 7]
    assert [d["date"] for d in body["days"]] == [f"2024-05-{d}" for d in range(28, 32)] + \
        ["2024-06-01", "2024-06-02", "2024-06-03"]
    assert all(35 <= d["forecast_tmax"] <= 52 for d in body["days"])
    assert {d["alert_confidence"] for d in body["days"]} <= {"validated", "low"}


def test_predict_hot_spell_raises_alert():
    body = client.post("/predict", json=GOOD).json()
    assert body["days"][0]["alert"] in ("Heatwave", "Severe heatwave")
    assert body["highest_validated_alert"] != "Normal" and body["first_alert_day"] == 1


def test_predict_winter_is_normal():
    r = client.post("/predict", json={"city": "Delhi", "date": "2024-01-10",
                                      "recent_tmax": [16, 17, 15, 16, 18, 17, 16]})
    assert r.status_code == 200 and r.json()["highest_alert"] == "Normal"


def test_forecast_close_to_actual_on_real_day():
    obs = client.get("/observed", params={"city": "Nagpur", "date": "2024-04-15"}).json()
    pred = client.post("/predict", json={"city": "Nagpur", "date": "2024-04-15",
                                         "recent_tmax": obs["recent_tmax"]}).json()
    assert abs(pred["days"][0]["forecast_tmax"] - obs["actual_next_day_tmax"]) < 5


def test_outlook_covers_all_cities_sorted_by_risk():
    body = client.get("/outlook", params={"date": "2024-05-27"}).json()
    assert len(body["cities"]) == 10
    order = ["Severe heatwave", "Heatwave", "Normal"]
    ranks = [order.index(c["highest_alert"]) for c in body["cities"]]
    assert ranks == sorted(ranks)


def test_model_info_has_7_horizons():
    h = client.get("/model-info").json()["horizons"]
    assert [x["day"] for x in h] == list(range(1, 8))
    assert all(x["test_mae"]["ridge_regression"] < x["test_mae"]["persistence_baseline"] for x in h)


# ---- invalid input / failure scenarios ------------------------------------
def test_unknown_city_404():
    r = client.post("/predict", json={**GOOD, "city": "Atlantis"})
    assert r.status_code == 404 and "unknown city" in r.json()["detail"]


def test_wrong_number_of_values_422():
    r = client.post("/predict", json={**GOOD, "recent_tmax": [40, 41, 42]})
    assert r.status_code == 422


def test_implausible_temperature_422():
    r = client.post("/predict", json={**GOOD, "recent_tmax": [40, 41, 42, 43, 44, 45, 99.9]})
    assert r.status_code == 422 and "plausible range" in r.text


def test_non_numeric_and_bad_date_422():
    assert client.post("/predict", json={**GOOD, "recent_tmax": ["hot"] * 7}).status_code == 422
    assert client.post("/predict", json={**GOOD, "date": "2024-13-45"}).status_code == 422


def test_observed_outside_data_range_404():
    r = client.get("/observed", params={"city": "Delhi", "date": "2030-05-01"})
    assert r.status_code == 404
    assert client.get("/outlook", params={"date": "2030-05-01"}).status_code == 404


def test_observed_history_too_long_422():
    r = client.get("/observed", params={"city": "Delhi", "date": "2024-05-27", "days": 500})
    assert r.status_code == 422


# ---- rule-based severity (IMD criteria) ------------------------------------
def test_severity_rules():
    assert classify(39.9, 30.0)["level"] == "Normal"            # below 40 C plains threshold
    assert classify(42.0, 37.5)["level"] == "Heatwave"          # departure 4.5
    assert classify(44.0, 37.5)["level"] == "Severe heatwave"   # departure 6.5
    assert classify(45.0, 43.0)["level"] == "Heatwave"          # absolute >= 45
    assert classify(47.0, 44.0)["level"] == "Severe heatwave"   # absolute >= 47
    assert classify(38.0, 33.0, coastal=True)["level"] == "Heatwave"  # coastal 37 C threshold
    assert classify(45.5, 43.0, coastal=True)["level"] == "Normal"    # absolute rule not for coast
    assert classify(45.0, 37.0, coastal=True)["level"] == "Heatwave"  # coast: no severe category


def test_day_of_year_aligns_leap_and_non_leap():
    assert day_of_year(date(2023, 3, 1)) == day_of_year(date(2024, 3, 1)) == 61
    assert day_of_year(date(2024, 2, 29)) == 60
