# Requirement-to-test checklist (HeatGuard v2, frontend 2.1)

Statuses: Verified / Partially Verified / Not Verified / Blocked. § numbers refer to the report PDF; files are in `experiments/results/` unless a path is given.

| # | Requirement (assignment brief) | Implementation | Evidence | Status |
|---|---|---|---|---|
| 1 | Working prototype: input → processing → output | Landing page + dashboard + API: city/date (or 7 typed values) → 7-day forecast, alerts, advice, map | §8, terminal capture t06, exp2_docker.log | Verified |
| 2 | AI/ML component appropriate to use case | 7 ridge-regression models (one per forecast day) on IMD data, compared with gradient boosting and 2 baselines | §7, models/metrics.json, train_output.txt | Verified |
| 3 | Rule-based part identified | IMD heatwave criteria (app/severity.py), labelled rule-based throughout | §7.2, test_severity_rules | Verified |
| 4 | Real / public dataset documented | IMD Pune 1° gridded Tmax 2014–2024, download script with retries | §4, data/processed/city_tmax.csv | Verified |
| 5 | Labelled architecture diagram | Architecture, request flow, experiment map, Kubernetes topology, ML pipeline, Exp 7/8 method | §5, §6, §7, §9 | Verified |
| 6 | Exp 2: containerise, run, push to Docker Hub | Backend + frontend images, Compose, failure cases, multi-arch push, pull-and-run; manual nginx/hello-world/ubuntu tasks | §9.1, captures t01–t07, Docker Hub pages, exp2_docker.log | Verified |
| 7 | Exp 3: deploy, expose, pod status, scaling/recovery | kind: 2 Deployments, ClusterIP + NodePort, probes, scaling, self-healing, bad-image rollback, rolling updates with availability checks | §9.2, captures t08–t16, exp3_kubernetes.log, frontend_2.1_release.log | Verified |
| 8 | Exp 7: measure CPU/memory, right-size, compare | docker stats under a fixed load, rule-based right-sizing, 3 repeats each, limits reused in Kubernetes | §9.3, capture t17–t18, exp7/* | Verified |
| 9 | Exp 8: same workload on configs, cheapest meeting target | 3 Fargate-valid sizes, target fixed before the runs, cost per 1M predictions | §9.4, capture t18, exp8/*, exp8_configs.json | Verified |
| 10 | Exp 7 & 8 same workload, cost basis stated | Same loadtest.py, seed, 15,000 requests, 20 clients; AWS public price list saved; costs labelled estimates | pricing/aws_ecs_ap-south-1_index.json | Verified |
| 11 | Representative inputs tested | pytest + curl on real IMD windows; frontend scenarios (Delhi, Jaipur, Nagpur, Chennai, Lucknow) | §10, capture t19, pytest_output.txt | Verified |
| 12 | ≥1 invalid-input / failure scenario | unknown city 404, wrong length 422, 99.9 °C 422, bad date 422, date outside data 404, backend down 504, bad image tag, deleted pod | §10, exp2_docker.log, exp3_kubernetes.log | Verified |
| 13 | Measurements (error, latency, throughput, CPU/mem, cost) | MAE per horizon, alert recall/precision, req/s, p50/p95, docker stats, estimated USD | §7, §9.3, §9.4 | Verified |
| 14 | Clean-environment setup | v1: fresh clone + venv + tests + retraining reproduced results; v2: images deleted locally, pulled from Docker Hub and run with Compose. Full README not repeated on a second machine | exp2_docker.log §5, capture t02 | Partially Verified |
| 15 | Demonstration video (5 min) | Recorded and shared on Google Drive (public link) | link on the title page | Verified |

Notes:
- *Clean-environment setup* is Partially Verified: v1 was cloned fresh and reproduced (tests + retraining); for v2 both images were deleted locally, pulled from Docker Hub and run with Compose. The full README procedure was not repeated on a second machine.
- Demonstration video: https://drive.google.com/file/d/1zebI3uAvh0hrG1DP8EzQjp-oGLMuGmM1/view?usp=sharing
