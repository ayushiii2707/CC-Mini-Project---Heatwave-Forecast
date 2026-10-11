# 5-minute demonstration plan: HeatGuard v2

Ayushi Ranjan · 16014223028 · B1 · Use case KJS-CES-01 · Experiments 2, 3, 7, 8

## Before recording (about 10 minutes, not on camera)

1. Plug in the charger, turn on Do Not Disturb, start **Docker Desktop** and wait for *Engine running*.
2. Open Terminal, make the font large (Cmd +), and in every new window run first:
   ```bash
   export PATH=/Applications/Docker.app/Contents/Resources/bin:$PATH
   ```
3. Go to the project folder (if you do not have it, clone it: `git clone https://github.com/ayushiii2707/CC-Mini-Project---Heatwave-Forecast.git ~/Desktop/heatguard`):
   ```bash
   cd ~/Desktop/heatguard
   ```
4. Start the two containers (Exp 2) and check both say `healthy`:
   ```bash
   docker compose up -d --wait && docker compose ps
   ```
5. Check the Kubernetes cluster (Exp 3): you should see `heatguard-api` and `heatguard-web` pods `Running`:
   ```bash
   kubectl get pods
   ```
   If that fails (e.g. after a restart), recreate it (about 4 minutes):
   ```bash
   kind delete cluster --name heatguard; DOCKERHUB_USER=ayushiranjan27 bash experiments/exp3_kubernetes.sh > /tmp/exp3.log 2>&1; kubectl get pods
   ```
6. Open these browser tabs in order:
   1. GitHub repo → `docs/screenshots/00_architecture_diagram.png`
   2. http://localhost:8080/ (landing page via Docker Compose; scroll it once before recording so you know the flow)
   3. https://hub.docker.com/u/ayushiranjan27
   4. http://localhost:30080/dashboard?city=Jaipur&date=2024-05-24 (dashboard via Kubernetes)
   5. GitHub → `docs/screenshots/exp7_rightsizing_chart.png` and `exp8_finops_chart.png`
   6. GitHub repo home page
7. Practise once with a stopwatch.

## Recording

**Cmd + Shift + 5** → *Record Entire Screen* → *Options*: Microphone = MacBook microphone, Save to = Desktop → **Record**.
Stop with the ⏹ button in the menu bar. Trim in QuickTime (Edit → Trim) if over 5:00.
Upload to Google Drive → Share → *Anyone with the link: Viewer* → copy link, test it in a private window.
Then put the link in `docs/video_link.txt` and rebuild the report: `python docs/build_report.py` (or ask Claude to do it).

## Script

| Time | On screen | Say / do |
|---|---|---|
| 0:00–0:30 | GitHub README | "I'm Ayushi Ranjan, roll 16014223028, batch B1. My use case is KJS-CES-01, heatwave early warning. HeatGuard forecasts the next 7 days of maximum temperature for 10 Indian cities from real IMD data and turns them into IMD-style heatwave alerts. I integrated Experiments 2, 3, 7 and 8." |
| 0:30–1:10 | Architecture diagram | "Data is IMD Pune's gridded daily maximum temperature, 2014–2024. The AI part, in orange, is seven ridge-regression models, one for each forecast day, followed by IMD's rule-based heatwave criteria. The app has two services: a FastAPI backend and an nginx web frontend that proxies API calls. In blue: Docker images on Docker Hub, Kubernetes, and the right-sizing and FinOps measurements." |
| 1:10–1:35 | Landing page :8080 | Scroll slowly: "This is the landing page. Every number here comes live from the API: the highest-risk city for 27 May 2024, and every day of 2024 in Delhi from IMD data, where the deep red is the heatwave." Scroll past *How it works* and the dark *Ten cities* map, then click **Open the dashboard**. |
| 1:35–2:00 | Dashboard, Delhi 27 May 2024 | "As of 27 May 2024, Delhi gets a Heatwave alert from the next day. Each card shows the forecast with its typical error, the alert, and what IMD actually recorded: 46 °C, so the alert was right. Days 5 to 7 are marked low-confidence, because validation showed weak skill that far ahead." Scroll: chart ("observed, normal, forecast with uncertainty band, green = what happened"), map + ranking ("Jaipur is the only severe one"). Click **Chennai** on the map. In What-if, change the last value to `99.9`, click Run: "the backend rejects impossible values." |
| 2:00–2:30 | Terminal + Docker Hub tab (**Exp 2**) | `docker compose ps` → "two containers, both healthy". `curl -s localhost:8080/api/health` → "the frontend proxies to the backend". Docker Hub tab: "both images pushed for Intel and Apple chips." |
| 2:30–3:20 | Terminal + :30080 tab (**Exp 3**) | `kubectl get deploy,pods,svc` → "backend is ClusterIP, internal only; frontend is NodePort 30080." `kubectl delete pod $(kubectl get pods -l app=heatguard-api -o name \| head -1 \| cut -d/ -f2)` then `kubectl get pods` → "self-healing." `kubectl scale deployment heatguard-web --replicas=4` → "scaling." Show :30080 tab: "the label at the top right shows which backend pod answered. Rolling updates had zero failed requests, including the frontend update to version 2.1: 248 of 248." |
| 3:20–3:45 | Exp 7 chart | "With 2 CPUs the backend used only about 43% of its CPU limit and 6% of its memory. Right-sized to 1.25 CPUs and 192 MB: estimated cost down 43%, throughput and p95 latency not worse, median latency up about 22%." |
| 3:45–4:15 | Exp 8 chart | "I fixed the target before running: at least 300 requests per second and p95 under 250 ms. 0.25 CPU failed badly. 0.5 CPU is the cheapest that passes, but only on average, so it's borderline; 1 CPU gives 44% more throughput for 39% more cost per prediction. Costs are estimates from AWS's Mumbai price list." |
| 4:15–4:40 | Frontend "How reliable is it?" | "On the unseen year 2024, error grows from 0.88 °C on day 1 to 1.54 on day 7, better than both baselines. Next-day alerts caught 90% of heatwave days. 18 automated tests pass." |
| 4:40–5:00 | GitHub repo | "Everything is reproducible from the README, with all logs and measurements. Limitations: 1-degree grid cells, temperature-only inputs, emulated instance sizes. Next steps: humidity, live data and multilingual advisories. Thank you." |

After recording: `kubectl scale deployment heatguard-web --replicas=2`.

## Which output proves which experiment

| Experiment | Proof on screen |
|---|---|
| 2 Docker & Docker Hub | `docker ps` (2 healthy containers); `/api/health` through the frontend; Docker Hub page with heatguard + heatguard-web |
| 3 Kubernetes | `kubectl get deploy,pods,svc`; pod replaced after delete; scaling; pod name in the :30080 status pill |
| 7 Right-sizing | Exp 7 chart + report table (CPU/memory % of limit before vs after, cost) |
| 8 FinOps | Exp 8 chart with both target lines; medium highlighted |
| AI component | 7-day cards vs actual IMD values; reliability panel (MAE per day, alert recall) |

## Likely viva questions

**AI component**
1. *How do you forecast 7 days?* Direct multi-horizon forecasting: seven separate ridge-regression models, model *h* predicts day *t+h* from the last 7 days, season, the climatological normal and location.
2. *Why ridge regression?* It had the lowest mean validation error across the 7 days (1.516 °C vs 1.531 for gradient boosting), is fast and explainable.
3. *How good is it?* Test MAE 0.88 °C on day 1 rising to 1.54 °C on day 7, better than persistence (0.94 → 2.16) and climatology (1.58) at every day.
4. *Why does accuracy fall with lead time?* Weather becomes less predictable further ahead; using only temperature history, by day 7 the model is close to "the usual temperature for that date".
5. *What is the alert margin?* Regression under-predicts extremes, so alerts use forecast + a margin chosen per day on 2023 data (1.25 °C for day 1, larger for later days). A missed heatwave is worse than a false alarm.
6. *What does low-confidence mean?* For days 5–7 the best validation F2 score was below 0.3, so the app shows those alerts as an outlook, not a validated warning.
7. *Is the severity AI?* No, it is IMD's rule set (40 °C plains / 37 °C coast threshold, departure 4.5–6.4 °C heatwave, > 6.4 severe, ≥ 45/47 °C absolute for plains).
8. *Leakage?* Time-ordered split (train 2014–22, validate 2023, test 2024); normals from training years only; 2024 used once.

**Application**
9. *Why separate frontend and backend?* Each can be scaled, updated and secured independently; the backend stays internal and the frontend is a cheap static nginx container.
10. *How does the frontend reach the backend?* nginx proxies `/api/` to `API_URL`: `http://api:8000` in Compose, `http://heatguard-api:8000` (Kubernetes DNS) in the cluster.
11. *Why does the map work offline?* It uses a bundled Natural Earth outline (India point-of-view boundaries) instead of an online tile server; fonts and chart libraries are bundled too.
11b. *What changed in frontend 2.1?* A new animated landing page and a redesigned dashboard. Only the frontend image changed (2.0 → 2.1); it was rolled out on Kubernetes with 248/248 requests succeeding. The backend and all measurements are unchanged.

**Cloud / experiments**
12. *Image vs container?* An image is the read-only template; a container is a running instance.
13. *What does Docker Compose add?* It starts both containers on a shared network, waits until the backend is healthy, and gives the frontend the backend's name.
14. *Why multi-arch images?* My Mac is ARM; most PCs and servers are x86. buildx built both under one tag.
15. *What happened when the backend was stopped?* The frontend stayed up and API calls returned HTTP 504 until the backend restarted.
16. *Deployment vs Service; ClusterIP vs NodePort?* A Deployment keeps N pods running; a Service gives them a stable name and load-balances. ClusterIP is internal only; NodePort exposes a port on the node.
17. *How did you get zero downtime?* `maxUnavailable: 0` keeps all old pods until a new one is ready, and a 5 s `preStop` delay lets the Service stop sending traffic before a pod exits. v1 without preStop had 1 failure in 40; v2 had 0 in 89 and 0 in 114.
18. *How were the right-sized values chosen?* Peak under load (0.868 cores, 118 MiB) × buffers (1.25 CPU, 1.5 memory), rounded up: 1.25 vCPU, 192 MiB; used as the Kubernetes limits.
19. *Did performance degrade?* Throughput and p95 did not; median latency rose about 22%. Cost fell about 43% (estimate).
20. *Why did 2 CPUs not help?* One Uvicorn process uses at most about one core.
21. *Why is 0.5 vCPU "borderline"?* It passed the 300 req/s target on average (302.7) but one of three runs was 295.5.
22. *Why was 0.25 vCPU the most expensive per prediction?* It was cheapest per hour but served only ~63 req/s, so cost per prediction was highest. Its health check also timed out under load.
23. *Are costs real?* No, estimates from AWS Fargate ARM Mumbai prices; no cloud account was used.

**Limitations**
24. 1° grid cells, temperature-only inputs, simplified heatwave declaration rule, historical replay rather than live data, emulated instance sizes, estimated costs.
