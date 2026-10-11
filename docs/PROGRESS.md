# Progress log

| Stage | Status | Evidence |
|---|---|---|
| Data: IMD 2014–2024 Tmax downloaded and parsed (10 cities, 40,180 rows) | Done, verified | `data/processed/city_tmax.csv`, size/orientation checks |
| AI: Ridge forecaster, test MAE 0.883 °C vs persistence 0.940 °C | Done, verified | `models/metrics.json`, `experiments/train_output.txt` |
| AI: alert margin 1.25 °C (chosen on 2023): 2024 heatwave recall 0.896, precision 0.566 | Done, verified | `models/metrics.json` |
| API + dashboard; 13 pytest tests incl. 5 invalid-input/failure | Done, verified | `experiments/results/pytest_output.txt` |
| Exp 2 local: build, run, health check, failure cases, nginx/hello-world/ubuntu, docker commands | Done, verified | `experiments/results/exp2_*.log`, `docs/screenshots/01_*.png`, `02_*.png` |
| Exp 2 Docker Hub push (multi-arch) | **Blocked: needs student's Docker Hub login** | script ready: `experiments/exp2_push.sh` |
| Exp 7 right-sizing: 2 vCPU/2 GB → 0.75 vCPU/192 MiB; est. cost −65%/h, throughput −10.7% | Done, verified | `experiments/results/exp7/`, `summary.md`, chart |
| Exp 8 FinOps: low/medium/high; cheapest meeting pre-set target = low | Done, verified | `experiments/results/exp8/`, `summary.md`, chart |
| Exp 3 Kubernetes: kind cluster, manifests validated with local image (pre-check) | Pre-check done | final run waits for Hub image: `experiments/exp3_kubernetes.sh` |
| Report, README, checklist, demo plan, ZIP | Not started | |

## Known issues / notes
- IMD server (imdpune.gov.in) is slow; the bare domain timed out, `www.` works. Download script retries.
- Exp 7/8 workload is client-limited at ~600 req/s (single Python load generator); server CPU never saturated above 1 core.
- Exp 8 target had no throughput requirement; result reported as-is, with a labelled post-hoc sensitivity check.
- amd64 image build tested under emulation: works (`arch x86_64`).
