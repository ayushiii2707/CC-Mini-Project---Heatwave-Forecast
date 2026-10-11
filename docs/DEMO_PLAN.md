# 5-minute demonstration plan: HeatGuard

Ayushi Ranjan · 16014223028 · B1 · Use case KJS-CES-01 · Experiments 2, 3, 7, 8

## Before recording (about 5 minutes, not on camera)

1. Start Docker Desktop and wait until it says *Engine running*.
2. In Terminal, from the project folder:
   ```bash
   export PATH=/Applications/Docker.app/Contents/Resources/bin:$PATH
   kind get clusters                      # should print: heatguard
   kubectl get pods                       # 3 pods Running (if the cluster is gone, see step 3)
   docker rm -f heatguard 2>/dev/null; docker run -d --name heatguard -p 8000:8000 ayushiranjan27/heatguard:1.1
   ```
3. If the cluster is missing: `kind create cluster --config k8s/kind-config.yaml`, then
   `DOCKERHUB_USER=ayushiranjan27 bash experiments/exp3_kubernetes.sh` (about 3 minutes).
4. Open these browser tabs in order:
   - `docs/screenshots/00_architecture_diagram.png`
   - http://localhost:8000/?city=Delhi&date=2024-05-27&auto=1
   - https://hub.docker.com/r/ayushiranjan27/heatguard/tags
   - http://localhost:30080/?city=Jaipur&date=2024-05-25&auto=1
   - `docs/screenshots/exp7_rightsizing_chart.png`, `docs/screenshots/exp8_finops_chart.png`
   - the GitHub repository
5. Make the Terminal font large (Cmd +) and clear the screen.

## Script

| Time | On screen | Say |
|---|---|---|
| 0:00–0:30 | Report title page or GitHub README | "I'm Ayushi Ranjan, roll 16014223028, batch B1. My use case is KJS-CES-01, heatwave monitoring and early warning. Heatwaves in India are getting more frequent, so we need region-specific warnings. HeatGuard forecasts tomorrow's maximum temperature from real IMD data and issues IMD-style heatwave alerts. I integrated Experiments 2, 3, 7 and 8." |
| 0:30–1:15 | Architecture diagram | "The data is IMD Pune's 1-degree gridded daily maximum temperature, 2014 to 2024, for ten cities. The AI part, shown in orange, is a ridge regression model that uses the last 7 days to predict tomorrow; it is then checked against IMD's heatwave rules, which are rule-based, not ML. The blue parts are the cloud experiments: Docker image on Docker Hub, Kubernetes deployment, and right-sizing and FinOps measurements on the same image." |
| 1:15–1:50 | Dashboard on :8000 (Delhi 27 May 2024) | Click *Load IMD observations*, then *Forecast tomorrow*. "These are real IMD values for Delhi. The model forecasts 44.1 °C for 28 May 2024; the alert uses forecast plus a 1.25 degree safety margin, so it says Heatwave. The actual IMD value was 46.0, so the alert was correct." Change one value to 99.9 and click Forecast: "Invalid sensor values are rejected with a clear error." |
| 1:50–2:20 | Terminal + Docker Hub tab (**Exp 2**) | Run `docker ps` and `curl -s localhost:8000/health`. "This is the container from my Dockerfile." Show the Docker Hub tab: "I pushed it to Docker Hub for both amd64 and arm64, so it runs on any laptop." |
| 2:20–3:10 | Terminal (**Exp 3**) | Run `kubectl get deploy,pods,svc -o wide`. "Kubernetes pulled the image from Docker Hub. The Service exposes it on NodePort 30080." Run `kubectl delete pod <one pod name>` then `kubectl get pods`: "Kubernetes immediately creates a replacement: self-healing." Run `kubectl scale deployment heatguard --replicas=4` then `kubectl get pods`. Show the :30080 tab: "The 'served by' row shows which pod answered." |
| 3:10–3:30 | Exp 7 chart | "For Experiment 7 I loaded the API with 15,000 real forecast requests. With 2 CPUs and 2 GB it used only 28% of the CPU and 5% of the memory. I right-sized to 0.75 CPU and 192 MB: estimated cost per hour fell 65% while throughput dropped about 11%, with zero errors." |
| 3:30–4:00 | Exp 8 chart | "For Experiment 8 the same workload ran on three Fargate-sized configs. I set the target before running: p95 latency under 150 ms and no errors. All three passed, so the cheapest, 0.25 vCPU, wins at about half the cost per prediction. But it halves throughput, so if we also required 500 requests per second, the 0.5 vCPU size would be the choice. Costs are estimates from AWS's Mumbai price list." |
| 4:00–4:30 | Report §4.3 table or `/model-info` on dashboard | "On the unseen 2024 test year the model's error is 0.88 °C versus 0.94 for the simple baseline. Without the margin it caught only 29% of heatwave days; with the margin, chosen on 2023 data, it catches 90%, at the cost of more false alarms. All 13 automated tests pass, including invalid inputs." |
| 4:30–5:00 | GitHub repository | "Everything is reproducible from the README in this repository, and all logs and measurements are included. Limitations: 1-degree grid cells, a one-day horizon, and cost estimates from a laptop rather than real cloud instances. Next steps would be humidity inputs, multi-day forecasts and LLM-generated multilingual advisories. Thank you." |

Restore after recording: `kubectl scale deployment heatguard --replicas=3`.

## Which output proves which experiment

| Experiment | Proof on screen |
|---|---|
| 2 Docker & Docker Hub | `docker ps` shows heatguard healthy; Docker Hub tags page with amd64/arm64 |
| 3 Kubernetes | `kubectl get pods` Running; pod replaced after delete; scaling; "Served by" pod name in dashboard via :30080 |
| 7 Right-sizing | Exp 7 chart + `experiments/results/summary.md` table (CPU/memory % of limit before vs after, cost) |
| 8 FinOps | Exp 8 chart with target line; cheapest passing config highlighted |
| AI component | Dashboard forecast vs actual; metrics table (MAE, recall, precision) |

## Likely viva questions

**AI component**

1. *Why ridge regression and not a deep model?* We compared it with gradient boosting and a persistence baseline. Ridge had the lowest validation error (0.888 °C) and is fast and explainable. With ~33,000 training rows and 13 features, a deep model is unlikely to help much.
2. *What are the features?* The last 7 daily maximum temperatures, their mean, the day of year as sine/cosine (seasonality), the climatological normal for that day, and latitude/longitude.
3. *How did you avoid data leakage?* Time-ordered split: train 2014–2022, validate 2023, test 2024. Normals were computed from training years only. The model and the margin were chosen on 2023; 2024 was used once, at the end.
4. *Why add a 1.25 °C margin?* Regression pulls extreme values towards the average, so without it the model caught only 29% of heatwave days. Missing a heatwave is worse than a false alarm, so alerts use forecast + margin. The margin was picked on 2023 using the F2 score, which weights recall more than precision.
5. *Is the severity classification AI?* No. It is rule-based, using IMD's definitions (departure from normal of 4.5–6.4 °C, or ≥ 45 °C, etc.). The ML part is the temperature forecast.
6. *What does MAE 0.88 °C mean?* On average the forecast is 0.88 °C away from the real IMD value for the next day.
7. *Why is precision only 0.57?* The margin trades false alarms for fewer missed heatwaves; about 4 in 10 alerts were not real heatwaves.

**Cloud / experiments**

8. *Image vs container?* An image is the read-only template (code, model, dependencies). A container is a running instance of it.
9. *Why multi-arch?* My Mac is ARM (M2); most lab PCs and cloud servers are x86. buildx built both, so the same tag works everywhere.
10. *What is kind and why not Killercoda?* kind runs a real Kubernetes cluster inside Docker containers. It let me script and log every step locally and pull my own Docker Hub image; Killercoda sessions expire.
11. *Deployment vs Service?* The Deployment keeps the desired number of pods running (scaling, self-healing, rolling updates). The Service gives a stable address and load-balances across the pods; NodePort exposes it outside the cluster.
12. *What are readiness and liveness probes?* Kubernetes calls /health. Readiness decides whether a pod receives traffic; liveness restarts a pod that stops responding.
13. *How did you choose the right-sized values?* Measured peak usage under load (0.566 cores, 105.5 MiB), multiplied by safety buffers (1.25 for CPU, 1.5 for memory) and rounded up: 0.75 vCPU and 192 MiB.
14. *Did performance degrade after right-sizing?* Slightly: throughput −10.7% and p95 latency +10.9%, with zero errors. I report that honestly; the cost saving (−65%) outweighs it for this service.
15. *Are the costs real?* No. They are estimates using AWS Fargate's published Mumbai ARM prices (USD 0.02383 per vCPU-hour, 0.00261 per GB-hour). No cloud account was used.
16. *Why did 2 CPUs not help?* Uvicorn runs one Python process, which uses at most about one core; the extra CPU sits idle. That is exactly the over-provisioning right-sizing detects.
17. *What is FinOps?* A practice that gets engineering and finance to choose resources by value per cost, for example the cheapest configuration that still meets the performance target.
18. *Why did Low win in Exp 8 despite lower throughput?* The target fixed beforehand was latency and errors only. Low met it at the lowest cost per prediction. If throughput mattered, Medium would win; the target must be defined carefully.
19. *How are Exp 7 and 8 comparable?* Same image, same load script, same 15,000 requests, 20 clients, same random seed, 3 repeats each, same machine.

**Architecture / limitations**

20. *What happens with bad input?* Unknown city → 404; wrong number of values, values outside −10..55 °C or a bad date → 422; the service keeps running.
21. *Main limitations?* 1° grid cells rather than stations, one-day horizon, temperature-only inputs, simplified heatwave declaration rule, emulated instance sizes, estimated costs.
22. *Data privacy?* Only public, non-personal weather data; no user data stored; container runs as non-root; no credentials in the repository.
23. *What would you add next?* Humidity/heat index, multi-day forecasts, IMD's consecutive-day rule, LLM multilingual advisories with human review, a Horizontal Pod Autoscaler, and repeating Exp 7–8 on real cloud instances.
