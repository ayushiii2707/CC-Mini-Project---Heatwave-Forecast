"""Pretty-print HeatGuard API responses in experiment logs.
Usage: curl ... | python3 experiments/show.py predict|outlook"""
import json
import sys

d = json.load(sys.stdin)
if sys.argv[1] == "predict":
    print(f"highest alert: {d['highest_alert']} | validated: {d['highest_validated_alert']} | "
          f"first alert day: {d['first_alert_day']} | served by {d['pod']} in {d['inference_ms']} ms")
    for x in d["days"]:
        print(f"  day {x['day']} {x['date']}  {x['forecast_tmax']:5.1f} C (+/-{x['typical_error_c']})"
              f"  alert basis {x['upper_forecast_tmax']:5.1f} C  {x['alert']:<16} {x['alert_confidence']}")
else:
    for c in d["cities"]:
        print(f"  {c['city']:<12} today {c['today_tmax']:5.1f} C  peak {c['peak']['forecast_tmax']:5.1f} C  {c['highest_alert']}")
    print(f"  ({len(d['cities'])} cities, {d['inference_ms']} ms, served by {d['pod']})")
