# Requirement-to-test checklist (HeatGuard v2)

Statuses: Verified / Partially Verified / Not Verified / Blocked. Evidence files are in `experiments/results/` unless a path is given.

| # | Requirement (assignment brief) | Implementation | Evidence | Status |
|---|---|---|---|---|
| 1 | Working prototype: input → processing → output | Web frontend + API: city/date (or 7 typed values) → 7-day forecast, alerts, advice, map | exp2_docker.log, screenshots 01–04 | Verified |
| 2 | AI/ML component appropriate to use case | 7 ridge-regression models (one per forecast day) on IMD data, compared with GBM and 2 baselines | models/metrics.json, train_output.txt | Verified |
| 3 | Rule-based part identified | IMD heatwave criteria (app/severity.py), labelled rule-based | test_severity_rules | Verified |
| 4 | Real / public dataset documented | IMD Pune 1° gridded Tmax 2014–2024, download script | data/processed/city_tmax.csv | Verified |
| 5 | Labelled architecture diagram | docs/architecture.html → 00_architecture_diagram.png | Figure 1 | Verified |
| 6 | Exp 2: containerise, run, push to Docker Hub | Backend + frontend images, Compose, multi-arch push, pull-and-run check | exp2_docker.log; archive_v1/exp2_manual_tasks.log (nginx, hello-world, ubuntu) | Verified |
| 7 | Exp 3: deploy, expose, pod status, scaling/recovery | kind: 2 Deployments, ClusterIP + NodePort, scaling, self-healing, bad-image rollback, rolling update with availability check | exp3_kubernetes.log, screenshot 05 | Verified |
| 8 | Exp 7: measure CPU/memory, right-size, compare | docker stats under fixed load, rule-based right-sizing, 3 repeats each | exp7/*, rightsizing_decision.json | Verified |
| 9 | Exp 8: same workload on configs, cheapest meeting target | 3 Fargate-valid sizes, target fixed before the runs | exp8/*, exp8_configs.json, summary.md | Verified |
| 10 | Exp 7 & 8 same workload, cost basis stated | Same loadtest.py, seed, 15,000 requests, 20 clients; AWS price list saved | pricing/aws_ecs_ap-south-1_index.json | Verified |
| 11 | Representative inputs tested | pytest + curl on real IMD windows; frontend scenarios (Delhi, Jaipur, Nagpur, Chennai, Lucknow) | pytest_output.txt, exp2_docker.log | Verified |
| 12 | ≥1 invalid-input / failure scenario | unknown city 404, wrong length 422, 99.9 °C 422, bad date 422, date outside data 404, backend down, bad image tag, deleted pod | pytest_output.txt, exp2_docker.log, exp3_kubernetes.log | Verified |
| 13 | Measurements (error, latency, throughput, CPU/mem, cost) | MAE per horizon, alert recall/precision, req/s, p50/p95, docker stats, est. USD | metrics.json, summary.md | Verified |
| 14 | Clean-environment setup | v1: fresh clone + venv + tests + retrain reproduced results; v2: images pulled from Docker Hub and run with Compose. Full README not repeated on a second machine | exp2_docker.log §5 | Partially Verified |
| 15 | Demonstration video (5 min) | Plan in docs/DEMO_PLAN.md | link: to be added | Not Verified |

Notes:
- *Clean-environment setup* is Partially Verified: v1 was cloned fresh and reproduced (tests + retraining); for v2 both images were deleted locally, pulled from Docker Hub and run with Compose. The full README procedure was not repeated on a second machine.
- *Demonstration video* becomes Verified once its link is added (`docs/video_link.txt`, then `python docs/build_report.py`).
