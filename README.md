# HeatGuard: Heatwave Forecast & Early Warning (Cloud Computing Mini Project)

**Ayushi Ranjan · Roll No. 16014223028 · Batch B1 · KJSSE, Somaiya Vidyavihar University**

Somaiya AI use case **KJS-CES-01: Climate Intelligence for Heatwave Monitoring, Prediction and Early Warning**,
integrated with Cloud Computing **Experiments 2, 3, 7 and 8**.

HeatGuard takes the last 7 days of observed maximum temperature for an Indian city, forecasts
tomorrow's maximum temperature with a machine-learning model trained on **real IMD gridded data**,
and turns the forecast into an IMD-criteria heatwave alert with advice. It is packaged as a Docker
image on Docker Hub, deployed on Kubernetes, and right-sized and cost-compared with measurements.

> Educational prototype. Official heatwave warnings are issued by the India Meteorological Department.

| | |
|---|---|
| Docker Hub image | [`ayushiranjan27/heatguard:1.1`](https://hub.docker.com/r/ayushiranjan27/heatguard) (linux/arm64 + linux/amd64). Exp 7/8 measured `1.0`; `1.1` only corrects the coastal heatwave rule. |
| Data | IMD Pune 1°×1° daily gridded max temperature, 2014–2024 ([source](https://www.imdpune.gov.in/cmpg/Griddata/Max_1_Bin.html)) |
| AI | Ridge regression next-day Tmax forecaster (ML) + IMD heatwave rules (rule-based) |
| Experiments | 2 Docker & Docker Hub · 3 Kubernetes · 7 Right-sizing · 8 FinOps instance comparison |

## Architecture

```
IMD .GRD files ─► scripts/prepare_data.py ─► city_tmax.csv ─► scripts/train.py ─► model.joblib + metrics.json
                                                                                     │
                    ┌──────────── Docker image ayushiranjan27/heatguard (Exp 2) ─────┴───────────┐
 browser / curl ──► │ FastAPI  GET /  /health  /cities  /observed  /model-info   POST /predict    │
                    │ validate input → ML forecast → +1.25 °C alert margin → IMD rules → advisory │
                    └───────────────┬──────────────────────────────────────────────────────────────┘
                                    │ docker pull from Docker Hub
            kind Kubernetes cluster (Exp 3): Deployment ×2→3 pods, NodePort Service :30080
                                    │ limits 750m CPU / 192Mi = right-sized values from Exp 7
 loadtest/loadtest.py (fixed workload) ─► docker run --cpus/--memory ─► docker stats ─► Exp 7 & Exp 8 tables
```

## Results at a glance (all measured, see `experiments/results/`)

| Item | Result |
|---|---|
| Next-day Tmax error, unseen 2024 | **MAE 0.883 °C** (ridge) vs 0.940 °C persistence baseline |
| Heatwave alerts, 2024 (48 actual heatwave city-days) | recall **0.896**, precision 0.566 (persistence: 0.688 / 0.647) |
| Tests | 13/13 pytest passed (incl. 5 invalid-input/failure cases) |
| Exp 7 right-sizing | 2 vCPU/2 GB → 0.75 vCPU/192 MiB: est. cost/hour **−65.2%**, throughput −10.7%, p95 +10.9%, 0 errors |
| Exp 8 FinOps | cheapest config meeting p95 ≤ 150 ms & 0 errors: **0.25 vCPU / 0.5 GB** (USD 0.0064 per 1M predictions, estimate) |
| Exp 3 Kubernetes | Hub image pulled, 2→3 replicas, deleted pod recreated in ~16 s, bad image blocked and rolled back while old pods kept serving, rolling update 1.0→1.1 (39/40 health checks OK during rollout) |

Costs are **estimates**, not charges: AWS Fargate Linux/ARM, Mumbai (ap-south-1), USD 0.02383 per vCPU-hour +
USD 0.00261 per GB-hour, from the AWS public price list published 2026-09-11 (saved in `experiments/pricing/`).

## Prerequisites

- macOS (tested on Apple M2, 8 GB) or Linux/Windows with Docker
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (tested: engine 29.7.2) and a free Docker Hub account
- Python 3.13 (tested 3.13.5)
- [kind](https://kind.sigs.k8s.io/) and kubectl (macOS: `brew install kind`; kubectl ships with Docker Desktop)

## Quick start: run the published image

```bash
docker run -d --name heatguard -p 8000:8000 ayushiranjan27/heatguard:1.1
```
Open http://localhost:8000 (example with a forecast already run:
http://localhost:8000/?city=Delhi&date=2024-05-27&auto=1).

## Full reproduction

```bash
# 1. Python environment
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# 2. Data (IMD server is slow; the script retries). Raw files are not in the repo.
bash scripts/download_imd.sh 2014 2024
python scripts/prepare_data.py          # -> data/processed/city_tmax.csv

# 3. Train + evaluate (train 2014-22, validate 2023, test 2024)
python scripts/train.py                 # -> models/model.joblib, models/metrics.json

# 4. Tests (valid inputs + invalid-input/failure scenarios)
pytest -v

# 5. Run locally without Docker
uvicorn app.main:app --port 8000
```

### Experiment 2: Docker & Docker Hub
```bash
docker build -t heatguard:1.0 .
docker run -d --name heatguard -p 8000:8000 heatguard:1.0
curl localhost:8000/health
docker login
DOCKERHUB_USER=<your-user> bash experiments/exp2_push.sh   # multi-arch push, nginx push, pull-and-run check
```

### Experiment 7: right-sizing (needs heatguard:1.0 built locally)
```bash
python experiments/run_config.py --exp exp7 --name over-provisioned --cpus 2 --memory 2g --requests 15000
python experiments/rightsize.py          # peak x buffer -> right-sized limits
python experiments/run_config.py --exp exp7 --name right-sized --cpus 0.75 --memory 192m --requests 15000
```

### Experiment 8: FinOps instance comparison (configs + target in experiments/exp8_configs.json)
```bash
python experiments/run_config.py --exp exp8 --name low    --cpus 0.25 --memory 512m --requests 15000
python experiments/run_config.py --exp exp8 --name medium --cpus 0.5  --memory 1g   --requests 15000
python experiments/run_config.py --exp exp8 --name high   --cpus 1    --memory 2g   --requests 15000
python experiments/summarize.py          # tables -> experiments/results/summary.md, charts -> docs/screenshots/
```

### Experiment 3: Kubernetes
```bash
kind create cluster --config k8s/kind-config.yaml
DOCKERHUB_USER=<your-user> bash experiments/exp3_kubernetes.sh
# open http://localhost:30080
kind delete cluster --name heatguard     # clean up
```

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Dashboard |
| GET | `/health` | Liveness/readiness (Kubernetes probes), returns pod name |
| GET | `/cities` | Supported cities (IMD grid cells) |
| GET | `/observed?city=Delhi&date=2024-05-27` | Last 7 real IMD values + actual next-day value |
| GET | `/model-info` | Evaluation metrics of the deployed model |
| POST | `/predict` | `{"city","date","recent_tmax":[7 values]}` → forecast, alert, advisory |

Errors: unknown city → 404; wrong number of values, values outside −10..55 °C, bad date → 422; model missing → 503.

## Repository layout

```
app/            FastAPI service, features, IMD severity rules, dashboard
scripts/        download_imd.sh, prepare_data.py, train.py
data/processed/ city_tmax.csv (derived from IMD data; raw .GRD files not committed)
models/         model.joblib, metrics.json
k8s/            kind-config.yaml, deployment.yaml, service.yaml
loadtest/       loadtest.py (shared Exp 7/8 workload)
experiments/    run_config.py, rightsize.py, summarize.py, exp2_push.sh, exp3_kubernetes.sh,
                exp8_configs.json, pricing/, results/ (raw logs, docker stats CSVs, summaries)
tests/          pytest suite
docs/           design, report, checklist, demo plan, screenshots
```

## Limitations

1° grid cells (≈100 km), not weather stations; one-day forecast only; heatwave rules applied per cell per
day (IMD needs ≥2 stations for 2 consecutive days); normals from 2014–2022 rather than a 30-year normal;
the alert margin was tuned on a validation year containing only 14 heatwave city-days; Exp 7/8 emulate
instance sizes with Docker limits on one laptop and the load generator limits throughput to ~600 req/s;
costs are estimates. No personal data is processed.

## Acknowledgement of AI assistance

This project was developed with assistance from Claude (Anthropic), used as a coding and documentation
assistant. All code was executed, and all results, logs and screenshots in this repository come from
real runs on the author's machine.

## Deliverables

| Deliverable | Location |
|---|---|
| Consolidated report (PDF) | `docs/16014223028_AyushiRanjan_CC_UseCase_Report.pdf` (rebuild: `python docs/build_report.py`) |
| Requirement-to-test checklist | `docs/CHECKLIST.md` |
| 5-minute demo plan + viva questions | `docs/DEMO_PLAN.md` |
| Design | `docs/DESIGN.md` |
| Screenshots and charts | `docs/screenshots/` |
| Raw logs and measurements | `experiments/results/` |
