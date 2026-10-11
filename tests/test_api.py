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
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_cities_list():
    names = [c["city"] for c in client.get("/cities").json()]
    assert "Delhi" in names and len(names) == 10


def test_observed_returns_real_imd_window():
    r = client.get("/observed", params={"city": "Delhi", "date": "2024-05-27"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["recent_tmax"]) == 7 and body["actual_next_day_tmax"] is not None


def test_predict_hot_spell_raises_alert():
    r = client.post("/predict", json=GOOD)
    assert r.status_code == 200
    body = r.json()
    assert body["forecast_date"] == "2024-05-28"
    assert 35 <= body["forecast_tmax"] <= 52
    assert body["alert"] in ("Heatwave", "Severe heatwave")


def test_predict_winter_is_normal():
    r = client.post("/predict", json={"city": "Delhi", "date": "2024-01-10",
                                      "recent_tmax": [16, 17, 15, 16, 18, 17, 16]})
    assert r.status_code == 200 and r.json()["alert"] == "Normal"


def test_forecast_close_to_actual_on_real_day():
    obs = client.get("/observed", params={"city": "Nagpur", "date": "2024-04-15"}).json()
    pred = client.post("/predict", json={"city": "Nagpur", "date": "2024-04-15",
                                         "recent_tmax": obs["recent_tmax"]}).json()
    assert abs(pred["forecast_tmax"] - obs["actual_next_day_tmax"]) < 5


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


# ---- rule-based severity (IMD criteria) ------------------------------------
def test_severity_rules():
    assert classify(39.9, 30.0)["level"] == "Normal"            # below 40 C plains threshold
    assert classify(42.0, 37.5)["level"] == "Heatwave"          # departure 4.5
    assert classify(44.0, 37.5)["level"] == "Severe heatwave"   # departure 6.5
    assert classify(45.0, 43.0)["level"] == "Heatwave"          # absolute >= 45
    assert classify(47.0, 44.0)["level"] == "Severe heatwave"   # absolute >= 47
    assert classify(38.0, 33.0, coastal=True)["level"] == "Heatwave"  # coastal 37 C threshold
    assert classify(45.5, 43.0, coastal=True)["level"] == "Normal"    # absolute rule not for coast


def test_day_of_year_aligns_leap_and_non_leap():
    assert day_of_year(date(2023, 3, 1)) == day_of_year(date(2024, 3, 1)) == 61
    assert day_of_year(date(2024, 2, 29)) == 60
