# HeatGuard: Heatwave Forecast & Early-Warning Prototype — Technical Design

**Student:** Ayushi Ranjan | **Roll No:** 16014223028 | **Batch:** B1 | **Individual submission**
**Use case:** KJS-CES-01 — Climate Intelligence for Heatwave Monitoring, Prediction and Early Warning (case 5)
**Cloud Computing experiments:** 2 (Docker & Docker Hub), 3 (Kubernetes), 7 (Right-sizing), 8 (FinOps instance comparison)

## 1. Problem statement
Heatwaves in India are increasing in frequency and intensity (case 5, §6). Authorities need timely,
region-specific warnings. This prototype forecasts next-day maximum temperature for selected Indian
locations from real IMD gridded observations and converts the forecast into a heatwave alert level.

## 2. Objectives
1. Build a working input → processing → output pipeline on real IMD data.
2. Train an ML model for next-day Tmax and measure its error against a simple baseline.
3. Classify the forecast into heatwave severity using IMD's published criteria.
4. Package, publish, deploy, measure and cost-optimise the service using Exp 2, 3, 7 and 8.

## 3. Scope (what is and is not built)
| In scope | Out of scope (stated as limitation) |
|---|---|
| IMD 1°×1° gridded daily Tmax, 2014–2024 | IoT Automated Weather Stations (hardware) |
| ~10 named grid cells (cities) | All 7 IMD regions / full spatial maps |
| Next-day Tmax regression + rule-based severity | LLM advisories (template text used instead) |
| REST API + simple web dashboard | Real cloud billing (costs are estimates) |

## 4. Data
- **Source:** IMD Pune, "High resolution 1°×1° daily gridded max temperature" binary `.GRD` files,
  downloaded from https://www.imdpune.gov.in/cmpg/Griddata/Max_1_Bin.html (form POST to `maxtemp.php`).
- **Format:** 31×31 grid (lat 7.5–37.5 N, lon 67.5–97.5 E), float32, one grid per day, 99.9 = missing.
- **Split:** train 2014–2022, validation 2023, test 2024 (time-ordered, no leakage).
- **No synthetic data is used.** No personal data is involved.

## 5. AI component (kept separate from the cloud components)
| Part | Type | Detail |
|---|---|---|
| Baseline | Persistence | "Tomorrow = today". Used only for comparison. |
| Forecaster | **ML regression** (scikit-learn gradient boosting) | Features: last 7 days of Tmax, 7-day mean, day-of-year (sin/cos), climatological normal for that cell/day, lat, lon. Target: Tmax for the next day. Metric: MAE, RMSE vs baseline. |
| Severity | **Rule-based** (labelled as such) | IMD criteria applied to forecast Tmax and departure from normal: Normal / Heatwave / Severe heatwave. Normal is computed from the 2014–2022 training years (IMD uses a 30-yr normal; documented deviation). |
| Advisory | Template text | Short advisory sentence per severity level. |

## 6. Cloud Computing components
| Exp | Role | Evidence |
|---|---|---|
| 2 Docker & Docker Hub | Containerise the FastAPI service + trained model; run locally; push `heatguard` image to Docker Hub. Also the manual's nginx pull/run. | Dockerfile, build/run/push logs, Hub page, `curl /predict` |
| 3 Kubernetes | kind cluster on Docker Desktop; Deployment (2 replicas) pulling the **Hub image**; NodePort Service; probes on `/health`; scale to 3; delete a pod → self-healing. | `kubectl` outputs, browser access, scaling and recovery logs |
| 7 Right-sizing | Same image run over-provisioned (2 CPU/2 GB) under a fixed load; `docker stats` sampled; new limits = peak + buffer; re-run, compare. Right-sized limits are reused in the Exp 3 manifest. | CSV of stats, before/after table, estimated cost saving |
| 8 FinOps comparison | **Same load script** as Exp 7 across Low/Medium/High/XL CPU-memory configs; performance target (p95 latency & zero errors); cheapest passing config chosen. | Results table, cost per 1000 predictions (estimate) |

**Cost basis (Exp 7/8):** estimates only, computed from a published per-vCPU-hour and per-GB-hour cloud
container price (source and date recorded in the report). No real charges are incurred.
Containers with CPU/memory limits on one laptop *emulate* instance sizes; this is stated in the report.

## 7. Architecture and data flow
```
IMD .GRD files ──► prepare_data.py ──► features CSV ──► train.py ──► model.joblib + metrics.json
                                                                        │
                       ┌────────────── Docker image "heatguard" (Exp 2) ┴──────────────┐
  user / dashboard ──► │ FastAPI: GET /  GET /health  GET /cities  POST /predict         │
                       │   validate input → ML forecast → IMD-rule severity → advisory   │
                       └──────────────┬──────────────────────────────────────────────────┘
                     push │ docker.io/<user>/heatguard
                          ▼
             kind Kubernetes cluster (Exp 3): Deployment ×2–3 → NodePort :30080
loadtest.py (fixed workload) ──► container with CPU/mem limits ──► docker stats → Exp 7 & Exp 8 tables
```

## 8. Technologies
Python 3.11 (container) · numpy, pandas, scikit-learn, joblib · FastAPI + uvicorn · httpx (load test) ·
pytest · Docker Desktop 29 (arm64) · Docker Hub · kind + kubectl. All free; all native on Apple M2.

## 9. Directory structure
```
app/            FastAPI service, model wrapper, severity rules, dashboard (static/index.html)
scripts/        download_imd.sh, prepare_data.py, train.py
data/raw/       IMD .GRD files (downloaded, not committed)
data/processed/ city time-series CSV derived from IMD data
models/         model.joblib, metrics.json
k8s/            kind-config.yaml, deployment.yaml, service.yaml
loadtest/       loadtest.py (shared workload for Exp 7 & 8)
experiments/    exp2..exp8 run scripts + results/ (real logs, CSVs)
tests/          pytest API + model tests (incl. invalid input)
docs/           DESIGN.md, report, demo plan, checklist, screenshots/
```

## 10. Implementation and testing sequence
1. Data: download + parse IMD, sanity-check values.
2. AI: train, evaluate vs baseline on 2024 test year.
3. API + dashboard; pytest (valid, invalid, edge cases).
4. Exp 2: Dockerfile, build, run, nginx task, push to Hub.
5. Exp 7: over-provisioned vs right-sized runs.
6. Exp 8: four configs, same workload, cost table.
7. Exp 3: kind cluster, deploy Hub image with right-sized limits, scale, recovery.
8. Report, README, checklist, demo plan, ZIP.
