"""Run the fixed HeatGuard workload against one CPU/memory configuration (Exp 7 & 8).

For each repeat: start the heatguard image with `docker run --cpus --memory`,
wait for /health, sample `docker stats` while loadtest/loadtest.py runs,
then record performance, utilisation, OOM status and the estimated cost.

Usage:
  python experiments/run_config.py --exp exp7 --name over-provisioned --cpus 2 --memory 2g
"""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
DOCKER = "/Applications/Docker.app/Contents/Resources/bin/docker"

# Cost basis: AWS Fargate on-demand, Linux/ARM, Asia Pacific (Mumbai) ap-south-1,
# from the AWS public price list (experiments/pricing/aws_ecs_ap-south-1_index.json,
# publicationDate 2026-09-11). These are ESTIMATES; no cloud charges were incurred.
USD_PER_VCPU_HOUR = 0.02383
USD_PER_GB_HOUR = 0.00261


def docker(*args, check=True):
    return subprocess.run([DOCKER, *args], capture_output=True, text=True, check=check).stdout.strip()


def to_mib(s: str) -> float:
    s = s.strip()
    for unit, f in (("GiB", 1024), ("MiB", 1), ("KiB", 1 / 1024), ("GB", 1000 / 1.048576),
                    ("MB", 1 / 1.048576), ("kB", 1 / 1048.576), ("B", 1 / 1048576)):
        if s.endswith(unit):
            return float(s[: -len(unit)]) * f
    return float(s)


def mem_gb(spec: str) -> float:
    spec = spec.lower()
    return float(spec[:-1]) / 1024 if spec.endswith("m") else float(spec.rstrip("g"))


def wait_healthy(port: int, timeout: float = 60) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(f"http://localhost:{port}/health", timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def sampler(container: str, out: list, stop: threading.Event):
    while not stop.is_set():
        line = docker("stats", "--no-stream", "--format", "{{json .}}", container, check=False)
        if line:
            s = json.loads(line)
            out.append({"t": round(time.time(), 2),
                        "cpu_pct": float(s["CPUPerc"].rstrip("%")),
                        "mem_mib": round(to_mib(s["MemUsage"].split("/")[0]), 1),
                        "mem_limit_mib": round(to_mib(s["MemUsage"].split("/")[1]), 1)})


def one_run(args, run: int, outdir: Path) -> dict:
    name = f"hg-{args.exp}-{args.name}"
    docker("rm", "-f", name, check=False)
    docker("run", "-d", "--name", name, "--cpus", str(args.cpus), "--memory", args.memory,
           "--memory-swap", args.memory, "-p", f"{args.port}:8000", args.image)
    result = {"exp": args.exp, "config": args.name, "run": run, "cpus": args.cpus, "memory": args.memory}
    if not wait_healthy(args.port):
        state = json.loads(docker("inspect", "--format", "{{json .State}}", name))
        result.update({"status": "FAILED_TO_START", "oom_killed": state.get("OOMKilled"),
                       "exit_code": state.get("ExitCode"),
                       "logs": docker("logs", "--tail", "5", name, check=False)})
        docker("rm", "-f", name, check=False)
        return result

    idle = json.loads(docker("stats", "--no-stream", "--format", "{{json .}}", name))
    samples, stop = [], threading.Event()
    th = threading.Thread(target=sampler, args=(name, samples, stop), daemon=True)
    th.start()
    lt = subprocess.run([sys.executable, str(ROOT / "loadtest" / "loadtest.py"),
                         "--url", f"http://localhost:{args.port}", "--requests", str(args.requests),
                         "--concurrency", str(args.concurrency)], capture_output=True, text=True)
    stop.set()
    th.join()
    state = json.loads(docker("inspect", "--format", "{{json .State}}", name))
    docker("rm", "-f", name, check=False)

    with open(outdir / f"{args.name}_run{run}_docker_stats.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["t", "cpu_pct", "mem_mib", "mem_limit_mib"])
        w.writeheader()
        w.writerows(samples)

    load = json.loads(lt.stdout) if lt.returncode == 0 else {"error": lt.stderr[-500:]}
    cpu = [s["cpu_pct"] for s in samples] or [0]
    mem = [s["mem_mib"] for s in samples] or [0]
    hourly = args.cpus * USD_PER_VCPU_HOUR + mem_gb(args.memory) * USD_PER_GB_HOUR
    rps = load.get("throughput_rps") or 0
    result.update({
        "status": "OK" if state.get("Running") and not state.get("OOMKilled") and not load.get("errors") else "DEGRADED",
        "oom_killed": state.get("OOMKilled"),
        "idle_mem_mib": round(to_mib(idle["MemUsage"].split("/")[0]), 1),
        "stats_samples": len(samples),
        "cpu_avg_pct": round(sum(cpu) / len(cpu), 1), "cpu_peak_pct": round(max(cpu), 1),
        "mem_peak_mib": round(max(mem), 1),
        "cpu_util_of_limit_pct": round(max(cpu) / (args.cpus * 100) * 100, 1),
        "mem_util_of_limit_pct": round(max(mem) / (mem_gb(args.memory) * 1024) * 100, 1),
        **{k: load.get(k) for k in ("ok", "errors", "error_types", "duration_s", "throughput_rps",
                                    "latency_ms_mean", "latency_ms_p50", "latency_ms_p95", "latency_ms_p99")},
        "est_usd_per_hour": round(hourly, 6),
        "est_usd_per_million_predictions": round(hourly / (rps * 3600) * 1e6, 4) if rps else None,
    })
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--cpus", type=float, required=True)
    ap.add_argument("--memory", required=True, help="e.g. 2g or 512m")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--requests", type=int, default=3000)
    ap.add_argument("--concurrency", type=int, default=20)
    ap.add_argument("--port", type=int, default=8100)
    ap.add_argument("--image", default="heatguard:1.0")
    args = ap.parse_args()

    outdir = ROOT / "experiments" / "results" / args.exp
    outdir.mkdir(parents=True, exist_ok=True)
    with open(outdir / "runs.jsonl", "a") as f:
        for run in range(1, args.repeats + 1):
            r = one_run(args, run, outdir)
            f.write(json.dumps(r) + "\n")
            print(json.dumps(r))


if __name__ == "__main__":
    main()
