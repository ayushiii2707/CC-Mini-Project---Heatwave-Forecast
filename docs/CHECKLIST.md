# Requirement-to-test checklist

Statuses: Verified / Partially Verified / Not Verified / Blocked. Evidence files are in `experiments/results/` unless a path is given.

| # | Requirement (assignment brief) | Implementation | Evidence | Status |
|---|---|---|---|---|
| 1 | Working prototype: input → processing → output | Dashboard + POST /predict (city, date, 7 Tmax → forecast, alert, advice) | exp2_run.log, screenshots 01–03, 05 | Verified |
| 2 | AI/ML component appropriate to use case | Ridge regression next-day Tmax on IMD data; compared with GBM and persistence | metrics.json, train_output.txt | Verified |
| 3 | Rule-based part identified | IMD heatwave criteria (app/severity.py), labelled rule-based | test_severity_rules | Verified |
| 4 | Real / public dataset documented | IMD Pune 1° gridded Tmax 2014–2024, download script | data/processed/city_tmax.csv | Verified |
| 5 | Labelled architecture diagram | docs/architecture.html → 00_architecture_diagram.png | Figure 1 | Verified |
| 6 | Exp 2: containerise, run, push to Docker Hub | Dockerfile, multi-arch push, pull-and-run check, nginx push | exp2_build/run/push logs, Docker Hub API + screenshot 04 | Verified |
| 7 | Exp 3: deploy, expose, pod status, scaling/recovery | kind cluster, Deployment + NodePort, scale 2→3, pod delete, bad image rollback, rolling update | exp3_kubernetes.log, screenshots 03, 05 | Verified |
| 8 | Exp 7: measure CPU/memory, right-size, compare | docker stats under fixed load, rule-based right-sizing, 3 repeats | exp7/*.csv, runs.jsonl, rightsizing_decision.json | Verified |
| 9 | Exp 8: same workload on configs, cheapest meeting target | 3 Fargate-valid sizes, target fixed beforehand | exp8/*, exp8_configs.json, summary.md | Verified |
| 10 | Exp 7 & 8 same workload, cost basis stated | Same loadtest.py, seed, 15000 requests, 20 clients; AWS price list saved | pricing/aws_ecs_ap-south-1_index.json | Verified |
| 11 | Representative inputs tested | pytest + curl on real IMD windows (Delhi, Jaipur, Nagpur, Chennai) | pytest_output.txt | Verified |
| 12 | ≥1 invalid-input / failure scenario | unknown city 404, 3 values 422, 99.9 °C 422, bad date 422, bad image tag in K8s | pytest_output.txt, exp2_run.log, exp3_kubernetes.log | Verified |
| 13 | Measurements (error, latency, throughput, CPU/mem, cost) | MAE/RMSE, recall/precision, req/s, p50/p95, docker stats, est. USD | metrics.json, summary.md | Verified |
| 14 | Clean-environment setup | Fresh git clone + new venv: pip install, 13/13 tests pass, retraining reproduces MAE 0.883 and margin 1.25; published image pulled and run after deleting local tag. Docker/K8s steps not repeated from scratch | exp2_push.log (pull + health); clean-clone check | Partially Verified |
| 15 | Demonstration video (5 min) | Plan in docs/DEMO_PLAN.md | to be recorded by student | Not Verified |

Notes:
- *Clean-environment setup* is Partially Verified: the GitHub repository was cloned into an empty folder with a new virtual environment; `pip install -r requirements-dev.txt`, `pytest` (13/13 passed) and `python scripts/train.py` (same MAE 0.883 °C and margin 1.25 °C) worked. The published image was pulled from Docker Hub and run. The Docker build and Kubernetes steps were not repeated from scratch on a second machine.
- *Demonstration video* is Not Verified until the student records it (plan: `docs/DEMO_PLAN.md`).
