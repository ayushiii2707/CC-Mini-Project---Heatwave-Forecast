"""Compact console view of the Exp 7 / Exp 8 summaries (used for terminal captures)."""
import csv
from pathlib import Path

RES = Path(__file__).resolve().parents[2] / "experiments" / "results"
cols = [("config", "config", 17), ("cpus", "vCPU", 5), ("memory", "mem", 5), ("cpu_peak_pct", "cpu peak%", 9),
        ("cpu_util_of_limit_pct", "%limit", 7), ("mem_peak_mib", "mem MiB", 8), ("throughput_rps", "req/s", 7),
        ("latency_ms_p50", "p50 ms", 7), ("latency_ms_p95", "p95 ms", 7), ("errors", "err", 4),
        ("est_usd_per_hour", "USD/h", 7), ("est_usd_per_million_predictions", "USD/1M", 7)]
for name in ("exp7", "exp8"):
    rows = list(csv.DictReader(open(RES / f"{name}_summary.csv")))
    print(f"== {name} (mean of {rows[0]['repeats']} runs, 15000 requests each) ==")
    print(" ".join(h.rjust(w) if i else h.ljust(w) for i, (_, h, w) in enumerate(cols))
          + ("  target" if name == "exp8" else ""))
    for r in rows:
        line = " ".join((str(r[k]).rjust(w) if i else str(r[k]).ljust(w)) for i, (k, _, w) in enumerate(cols))
        print(line + (("  " + ("PASS" if r["meets_target"] == "True" else "FAIL")) if name == "exp8" else ""))
    print()
