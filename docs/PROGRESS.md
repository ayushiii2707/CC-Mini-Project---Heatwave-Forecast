# Progress log

| Stage | Status | Evidence |
|---|---|---|
| Data: IMD 2014–2024 Tmax (2017 needed 3 attempts), 10 cities, 40,180 rows | Verified | `data/processed/city_tmax.csv` |
| v1: next-day forecast, single container, Exp 2/3/7/8 | Verified, archived | `experiments/results/archive_v1/` |
| v2 AI: 7 ridge models; test MAE 0.88 (day 1) → 1.54 °C (day 7); days 1–4 validated alerts | Verified | `models/metrics.json`, `experiments/results/train_output.txt` |
| v2 backend API + frontend (nginx), Docker Compose; 18/18 tests | Verified | `pytest_output.txt`, screenshots 01–04 |
| Exp 2 v2: build, compose, failure cases, multi-arch push, pull-and-run | Verified | `exp2_docker.log` |
| Exp 7 v2: 2 vCPU/2 GB → 1.25 vCPU/192 MiB, est. cost −42.7% | Verified | `exp7/`, `summary.md` |
| Exp 8 v2: target fixed beforehand; medium cheapest passing (borderline) | Verified | `exp8/`, `summary.md` |
| Exp 3 v2: two tiers, scaling, self-healing, rollback, rolling updates 89/89 + 114/114 | Verified | `exp3_kubernetes.log`, screenshot 05 |
| Frontend 2.1: animated landing page + redesigned dashboard; pushed and rolled out (248/248 OK) | Verified | `frontend_2.1_release.log`, screenshots 01–08 |
| Report PDF, README, checklist, demo plan, ZIP, GitHub push | Done | `docs/` |
| Demonstration video | To be recorded by student; link goes in `docs/video_link.txt` | `docs/DEMO_PLAN.md` |

## Known issues
- IMD server is slow; bare domain times out, `www.` works.
- Online map tile servers were unreachable on this network; the map uses a bundled Natural Earth outline (India view).
- Exp 7: median latency +21.8% after right-sizing (throughput and p95 not worse).
- Exp 8: medium passes on the mean; 1 of 3 runs at 295.5 req/s (< 300).
- At 0.25 vCPU the backend's health check times out under load.
