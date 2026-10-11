"""Experiment 7, step 4: derive right-sized limits from the over-provisioned runs.

Rule (from the Exp 7 manual: "slightly above peak usage, with a safety buffer"):
  CPU    = highest observed peak (cores) x 1.25, rounded UP to a 0.25-vCPU step
  Memory = highest observed peak (MiB)   x 1.50, rounded UP to a 64 MiB step
Usage: python experiments/rightsize.py
"""
import json
import math
from pathlib import Path

RUNS = Path(__file__).resolve().parent / "results" / "exp7" / "runs.jsonl"
CPU_BUFFER, MEM_BUFFER = 1.25, 1.50

runs = [json.loads(line) for line in RUNS.read_text().splitlines()]
over = [r for r in runs if r["config"] == "over-provisioned" and r["status"] == "OK"]
peak_cpu_cores = max(r["cpu_peak_pct"] for r in over) / 100
peak_mem_mib = max(r["mem_peak_mib"] for r in over)

cpus = math.ceil(peak_cpu_cores * CPU_BUFFER / 0.25) * 0.25
mem_mib = math.ceil(peak_mem_mib * MEM_BUFFER / 64) * 64
decision = {
    "allocated": {"cpus": over[0]["cpus"], "memory": over[0]["memory"]},
    "observed_peak": {"cpu_cores": round(peak_cpu_cores, 3), "memory_mib": peak_mem_mib},
    "buffer": {"cpu": CPU_BUFFER, "memory": MEM_BUFFER},
    "right_sized": {"cpus": cpus, "memory": f"{mem_mib}m"},
}
(RUNS.parent / "rightsizing_decision.json").write_text(json.dumps(decision, indent=2))
print(json.dumps(decision, indent=2))
