# Progress log

| Stage | Status | Evidence |
|---|---|---|
| Data: IMD 2014–2024 Tmax downloaded (2017 needed 3 attempts) and parsed (10 cities, 40,180 rows) | Verified | `data/processed/city_tmax.csv` |
| AI: Ridge forecaster, test MAE 0.883 °C vs persistence 0.940 °C | Verified | `models/metrics.json`, `experiments/train_output.txt` |
| AI: alert margin 1.25 °C (chosen on 2023): 2024 heatwave recall 0.896, precision 0.566 | Verified | `models/metrics.json` |
| IMD coastal rule corrected after checking IMD definitions (v1.1); forecast errors unchanged | Verified | `app/severity.py`, `exp2_push_v1.1.log` |
| API + dashboard; 13 pytest tests incl. invalid-input/failure | Verified | `experiments/results/pytest_output.txt` |
| Exp 2: build, run, failures, nginx/hello-world/ubuntu, multi-arch push 1.0 and 1.1, pull-and-run | Verified | `exp2_*.log`, screenshot 04 |
| Exp 3: kind, Hub image, service, load balancing, scale, self-healing, bad-image rollback, rolling update | Verified | `exp3_kubernetes.log`, screenshots 03, 05 |
| Exp 7: 2 vCPU/2 GB → 0.75 vCPU/192 MiB; est. cost/hour −65.2%, throughput −10.7% | Verified | `exp7/`, `summary.md` |
| Exp 8: low/medium/high; cheapest meeting pre-set target = low | Verified | `exp8/`, `summary.md` |
| Report PDF, README, checklist, demo plan, source ZIP, GitHub push | Done | `docs/` |
| Demonstration video | Not done: to be recorded by student | `docs/DEMO_PLAN.md` |

## Known issues
- IMD server is slow; bare domain times out, `www.` works.
- Exp 7/8 throughput limited by the single Python load generator (~600 req/s).
- Exp 8 target had no throughput requirement; post-hoc sensitivity reported separately.
- One failed health check (1/40) during the Exp 3 rolling update; preStop hook not implemented.
