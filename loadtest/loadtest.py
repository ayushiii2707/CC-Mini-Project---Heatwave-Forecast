"""Fixed forecast workload for Experiments 7 and 8 (identical in every run).

Sends N POST /predict requests built from real IMD 7-day windows (2024 test
year, fixed random seed) with a fixed number of concurrent clients, then
reports throughput, latency percentiles and errors as JSON.

Usage: python loadtest/loadtest.py --url http://localhost:8000 --requests 3000 --concurrency 20
"""
import argparse
import asyncio
import csv
from datetime import date, timedelta
import json
from pathlib import Path
import random
import statistics
import time

import httpx

DATA = Path(__file__).resolve().parent.parent / "data" / "processed" / "city_tmax.csv"


def build_payloads(n: int, seed: int = 7):
    series = {}
    with open(DATA) as f:
        for row in csv.DictReader(f):
            if row["date"].startswith("2024") and row["tmax"]:
                series.setdefault(row["city"], {})[date.fromisoformat(row["date"])] = float(row["tmax"])
    rng = random.Random(seed)
    cities = sorted(series)
    payloads = []
    while len(payloads) < n:
        city = rng.choice(cities)
        today = date(2024, 1, 7) + timedelta(days=rng.randrange(0, 358))
        days = [today - timedelta(days=k) for k in range(6, -1, -1)]
        if all(d in series[city] for d in days):
            payloads.append({"city": city, "date": today.isoformat(),
                             "recent_tmax": [series[city][d] for d in days]})
    return payloads


async def run(url: str, payloads, concurrency: int, timeout: float):
    queue = asyncio.Queue()
    for p in payloads:
        queue.put_nowait(p)
    latencies, errors = [], []

    async def worker(client):
        while True:
            try:
                p = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            t0 = time.perf_counter()
            try:
                r = await client.post(f"{url}/predict", json=p)
                if r.status_code == 200:
                    latencies.append((time.perf_counter() - t0) * 1000)
                else:
                    errors.append(f"HTTP {r.status_code}")
            except httpx.HTTPError as e:
                errors.append(type(e).__name__)

    limits = httpx.Limits(max_connections=concurrency)
    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        start = time.perf_counter()
        await asyncio.gather(*(worker(client) for _ in range(concurrency)))
        duration = time.perf_counter() - start
    return latencies, errors, duration


def pct(values, q):
    if not values:
        return None
    s = sorted(values)
    return round(s[min(len(s) - 1, int(round(q / 100 * (len(s) - 1))))], 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--requests", type=int, default=3000)
    ap.add_argument("--concurrency", type=int, default=20)
    ap.add_argument("--warmup", type=int, default=100)
    ap.add_argument("--timeout", type=float, default=10.0)
    args = ap.parse_args()

    payloads = build_payloads(args.requests + args.warmup)
    asyncio.run(run(args.url, payloads[:args.warmup], args.concurrency, args.timeout))
    lat, err, dur = asyncio.run(run(args.url, payloads[args.warmup:], args.concurrency, args.timeout))
    print(json.dumps({
        "requests": args.requests, "concurrency": args.concurrency,
        "ok": len(lat), "errors": len(err), "error_types": sorted(set(err)),
        "duration_s": round(dur, 3), "throughput_rps": round(len(lat) / dur, 1),
        "latency_ms_mean": round(statistics.mean(lat), 2) if lat else None,
        "latency_ms_p50": pct(lat, 50), "latency_ms_p95": pct(lat, 95), "latency_ms_p99": pct(lat, 99),
    }))


if __name__ == "__main__":
    main()
