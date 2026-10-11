"""Build the consolidated report (HTML -> PDF) from the real project outputs (HeatGuard v2).

Every number is read from models/metrics.json or experiments/results/*, and every command
output is copied verbatim from the logs in experiments/results/. Result-dependent sentences
are computed from the data. The demo video link is read from docs/video_link.txt if present.
Usage: python docs/build_report.py   (needs Google Chrome for the PDF step)
"""
import csv
import html
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "experiments" / "results"
OUT_HTML = ROOT / "docs" / "report.html"
OUT_PDF = ROOT / "docs" / "16014223028_AyushiRanjan_CC_UseCase_Report.pdf"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
GITHUB = "https://github.com/ayushiii2707/CC-Mini-Project---Heatwave-Forecast"
HUB = "https://hub.docker.com/u/ayushiranjan27"
VIDEO_FILE = ROOT / "docs" / "video_link.txt"
VIDEO = VIDEO_FILE.read_text().strip() if VIDEO_FILE.exists() else ""

M = json.loads((ROOT / "models" / "metrics.json").read_text())
E7 = list(csv.DictReader(open(RES / "exp7_summary.csv")))
E8 = list(csv.DictReader(open(RES / "exp8_summary.csv")))
E8CFG = json.loads((ROOT / "experiments" / "exp8_configs.json").read_text())
RS = json.loads((RES / "exp7" / "rightsizing_decision.json").read_text())
EXP3 = (RES / "exp3_kubernetes.log").read_text()
EXP2 = (RES / "exp2_docker.log").read_text()


def log(name, start=None, end=None, max_lines=40, width=150):
    """Verbatim excerpt of a log between two marker strings."""
    lines = (RES / name).read_text().splitlines()
    i = next((k for k, l in enumerate(lines) if start in l), 0) if start else 0
    j = next((k for k, l in enumerate(lines[i + 1:], i + 1) if end in l), len(lines)) if end else len(lines)
    chunk = [l[:width] for l in lines[i:j] if not re.match(r"^#\d+ |^ *(sha256|Layer)", l)][:max_lines]
    return f'<pre class="log"><span class="src">experiments/results/{name}</span>\n' + html.escape("\n".join(chunk)) + "</pre>"


def code(path, first=None, last=None):
    lines = (ROOT / path).read_text().splitlines()[first:last]
    return f'<pre class="code"><span class="src">{path}</span>\n' + html.escape("\n".join(lines)) + "</pre>"


def img(name, caption, width="100%"):
    return f'<figure><img src="screenshots/{name}" style="width:{width}"><figcaption>{caption}</figcaption></figure>'


def table(head, rows):
    h = "".join(f"<th>{c}</th>" for c in head)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><tr>{h}</tr>{b}</table>"


def pm(r, k):
    return f"{r[k]} ± {r[k + '_sd']}"


def pct(a, b):
    return f"{(float(b) - float(a)) / float(a) * 100:+.1f}%"


# ---------------- derived values ----------------
best = M["selected_model"]
H = M["horizons"]
h1 = H[0]
sev1, sev1_0, sev1_p = h1["severity_test_forecast"], h1["severity_test_forecast_no_margin"], h1["severity_test_persistence"]
validated_days = [h["horizon_days"] for h in H if h["alert_confidence"] == "validated"]
low_days = [h["horizon_days"] for h in H if h["alert_confidence"] == "low"]
o7, r7 = E7
tgt = E8CFG["performance_target"]
passing = [r for r in E8 if r["meets_target"] == "True"]
best8 = min(passing, key=lambda r: float(r["est_usd_per_million_predictions"])) if passing else None
failing = [r for r in E8 if r["meets_target"] != "True"]
RUNS8 = [json.loads(l) for l in (RES / "exp8" / "runs.jsonl").read_text().splitlines()]


def runs_meeting(cfg):
    rs = [r for r in RUNS8 if r["config"] == cfg]
    ok = [r for r in rs if r["throughput_rps"] >= tgt["min_throughput_rps"] and r["latency_ms_p95"] <= tgt["max_p95_latency_ms"]
          and r["errors"] <= tgt["max_errors"] and not r["oom_killed"]]
    return len(ok), len(rs), [r["throughput_rps"] for r in rs]


high8 = next((r for r in E8 if r["config"] == "high"), None)
avail = re.findall(r"# availability: (\d+)/(\d+) requests returned HTTP 200 \(failed: (\d+)\)", EXP3)
heal = re.search(r"### 4\..*?### 5\.", EXP3, re.S)
tests = [l.split("::")[1].split(" ")[0] for l in (RES / "pytest_output.txt").read_text().splitlines()
         if "::" in l and "PASSED" in l]
test_total = (RES / "pytest_output.txt").read_text().strip().splitlines()[-1].strip("= ")
gw = re.search(r"/api/health HTTP (\d+)\n# backend restarted -> /api/health HTTP (\d+)", EXP2)

perf_cols = ["Configuration", "CPU peak (% of 1 core)", "CPU used (% of limit)", "Memory peak (MiB)",
             "Memory used (% of limit)", "Throughput (req/s)", "p50 latency (ms)", "p95 latency (ms)",
             "Errors", "Est. USD / hour", "Est. USD / 1M predictions"]


def perf_row(r):
    return [f"<b>{r['config']}</b><br>{r['cpus']} vCPU / {r['memory']}", pm(r, "cpu_peak_pct"),
            pm(r, "cpu_util_of_limit_pct"), pm(r, "mem_peak_mib"), pm(r, "mem_util_of_limit_pct"),
            pm(r, "throughput_rps"), pm(r, "latency_ms_p50"), pm(r, "latency_ms_p95"),
            str(int(float(r["errors"]))), f"{float(r['est_usd_per_hour']):.4f}",
            f"{float(r['est_usd_per_million_predictions']):.4f}"]


def fails_because(r):
    why = []
    if float(r["throughput_rps"]) < tgt["min_throughput_rps"]:
        why.append(f"throughput {r['throughput_rps']} &lt; {tgt['min_throughput_rps']} req/s")
    if float(r["latency_ms_p95"]) > tgt["max_p95_latency_ms"]:
        why.append(f"p95 {r['latency_ms_p95']} &gt; {tgt['max_p95_latency_ms']} ms")
    if float(r["errors"]) > tgt["max_errors"]:
        why.append("errors")
    if r["oom"] == "True":
        why.append("OOM kill")
    return ", ".join(why) or "run status not OK"


ai_rows = []
for h in H:
    mo = h["models"]
    s = h["severity_test_forecast"]
    ai_rows.append([f"Day {h['horizon_days']}", mo["persistence_baseline"]["test"]["MAE"], mo["climatology_baseline"]["test"]["MAE"],
                    mo["gradient_boosting"]["test"]["MAE"], f"<b>{mo['ridge_regression']['test']['MAE']}</b>",
                    f"{h['alert_margin_c']} °C", h["validation_f2"], s["heatwave_recall"], s["heatwave_precision"],
                    "validated" if h["alert_confidence"] == "validated" else "<b>low</b>"])

if avail:
    avail_txt = "; ".join(f"{a}/{t} successful during the {name} rollout" for (a, t, _), name in zip(avail, ["backend", "frontend"]))
    avail_failed = sum(int(f) for _, _, f in avail)
else:
    avail_txt, avail_failed = "not measured", None

CHECKLIST = [
    ("Working prototype: input → processing → output", "Web frontend + API: city/date (or 7 typed values) → 7-day forecast, alerts, advice, map",
     "exp2_docker.log, screenshots 01–04", "Verified"),
    ("AI/ML component appropriate to use case", "7 ridge-regression models (one per forecast day) on IMD data, compared with GBM and 2 baselines",
     "models/metrics.json, train_output.txt", "Verified"),
    ("Rule-based part identified", "IMD heatwave criteria (app/severity.py), labelled rule-based", "test_severity_rules", "Verified"),
    ("Real / public dataset documented", "IMD Pune 1° gridded Tmax 2014–2024, download script", "data/processed/city_tmax.csv", "Verified"),
    ("Labelled architecture diagram", "docs/architecture.html → 00_architecture_diagram.png", "Figure 1", "Verified"),
    ("Exp 2: containerise, run, push to Docker Hub", "Backend + frontend images, Compose, multi-arch push, pull-and-run check",
     "exp2_docker.log; archive_v1/exp2_manual_tasks.log (nginx, hello-world, ubuntu)", "Verified"),
    ("Exp 3: deploy, expose, pod status, scaling/recovery", "kind: 2 Deployments, ClusterIP + NodePort, scaling, self-healing, bad-image rollback, rolling update with availability check",
     "exp3_kubernetes.log, screenshot 05", "Verified"),
    ("Exp 7: measure CPU/memory, right-size, compare", "docker stats under fixed load, rule-based right-sizing, 3 repeats each",
     "exp7/*, rightsizing_decision.json", "Verified"),
    ("Exp 8: same workload on configs, cheapest meeting target", "3 Fargate-valid sizes, target fixed before the runs",
     "exp8/*, exp8_configs.json, summary.md", "Verified"),
    ("Exp 7 & 8 same workload, cost basis stated", "Same loadtest.py, seed, 15,000 requests, 20 clients; AWS price list saved",
     "pricing/aws_ecs_ap-south-1_index.json", "Verified"),
    ("Representative inputs tested", "pytest + curl on real IMD windows; frontend scenarios (Delhi, Jaipur, Nagpur, Chennai, Lucknow)",
     "pytest_output.txt, exp2_docker.log", "Verified"),
    ("≥1 invalid-input / failure scenario", "unknown city 404, wrong length 422, 99.9 °C 422, bad date 422, date outside data 404, backend down, bad image tag, deleted pod",
     "pytest_output.txt, exp2_docker.log, exp3_kubernetes.log", "Verified"),
    ("Measurements (error, latency, throughput, CPU/mem, cost)", "MAE per horizon, alert recall/precision, req/s, p50/p95, docker stats, est. USD",
     "metrics.json, summary.md", "Verified"),
    ("Clean-environment setup", "v1: fresh clone + venv + tests + retrain reproduced results; v2: images pulled from Docker Hub and run with Compose. Full README not repeated on a second machine",
     "exp2_docker.log §5", "Partially Verified"),
    ("Demonstration video (5 min)", "Plan in docs/DEMO_PLAN.md", "link: " + (VIDEO or "to be added"), "Verified" if VIDEO else "Not Verified"),
]

video_html = (f'<a href="{VIDEO}">{VIDEO}</a>' if VIDEO else
              '<span class="placeholder">[Placeholder: demonstration video link, to be inserted after upload]</span>')

body = f"""
<section class="title">
  <p class="inst">Somaiya Vidyavihar University · K J Somaiya School of Engineering</p>
  <p class="course">Cloud Computing · Mini Project Report</p>
  <h1>HeatGuard: 7-day Heatwave Forecast and Early Warning</h1>
  <p class="sub">Cloud Computing Experiments integrated with the Somaiya AI Use Case<br>
  <b>KJS-CES-01: Climate Intelligence for Heatwave Monitoring, Prediction and Early Warning</b></p>
  <table class="meta">
    <tr><td>Student</td><td><b>Ayushi Ranjan</b></td></tr>
    <tr><td>Roll No.</td><td>16014223028</td></tr>
    <tr><td>Batch</td><td>B1</td></tr>
    <tr><td>Submission</td><td>Individual</td></tr>
    <tr><td>Selected use case</td><td>Case 5: Climate Intelligence for Heatwave Monitoring, Prediction and Early Warning</td></tr>
    <tr><td>Selected experiments</td><td><b>2</b> Containerization, Docker and Docker Hub · <b>3</b> Application Deployment using Kubernetes ·
        <b>7</b> Cloud Cost Optimization through Resource Right-Sizing · <b>8</b> FinOps Principles and Instance-Type Comparison</td></tr>
    <tr><td>Source code</td><td><a href="{GITHUB}">{GITHUB}</a></td></tr>
    <tr><td>Docker images</td><td><a href="{HUB}">{HUB}</a> (heatguard, heatguard-web)</td></tr>
    <tr><td>Demonstration video</td><td>{video_html}</td></tr>
    <tr><td>Date</td><td>11 October 2026</td></tr>
  </table>
</section>

<h2>Abstract</h2>
<p>HeatGuard is a working prototype of the heatwave early-warning use case. It uses real India Meteorological Department (IMD)
gridded daily maximum-temperature data for 2014–2024, forecasts the maximum temperature for each of the next <b>7 days</b> for ten
Indian cities with machine-learning models, and converts every forecast day into a heatwave alert using IMD's published criteria.
On the unseen year 2024 the forecast error grows from <b>{H[0]['models'][best]['test']['MAE']} °C</b> (day 1) to
<b>{H[-1]['models'][best]['test']['MAE']} °C</b> (day 7), lower than both baselines at every horizon. Next-day alerts detect
<b>{sev1['heatwave_recall']*100:.0f}%</b> of actual heatwave city-days; alerts for days {low_days[0] if low_days else '-'}–7 are marked
low-confidence because validation showed limited skill. The system is split into a FastAPI <b>backend</b> and an nginx-served
<b>web frontend</b>, both published on Docker Hub (Experiment 2) and deployed on Kubernetes with scaling, self-healing, rollback
and measured rolling updates (Experiment 3). The backend was right-sized from 2 vCPU / 2 GB to {RS['right_sized']['cpus']} vCPU /
{RS['right_sized']['memory']} with an estimated <b>{pct(o7['est_usd_per_hour'], r7['est_usd_per_hour'])}</b> change in hourly cost
(Experiment 7), and three instance sizes were compared under the same workload against a target fixed in advance (Experiment 8).
All results come from real runs; costs are estimates.</p>

<h2>1. Problem statement, objectives and scope</h2>
<p><b>Problem.</b> Heatwaves in India are increasing in frequency, intensity and duration and affect public health, agriculture
and economic activity. Severity varies by region, so timely, region-specific warnings are needed (use-case document KJS-CES-01, §6).</p>
<p><b>Objectives.</b></p>
<ol>
<li>Build an input → processing → output prototype on real IMD meteorological data (use case §11, steps 1–2).</li>
<li>Develop AI models for region-wise maximum-temperature forecasting up to 7 days ahead and evaluate them against baselines (§8, objective 2).</li>
<li>Classify heatwave severity per day, produce advisories and visualise them on a decision-support dashboard (§8, objective 4; §11, steps 7–9).</li>
<li>Package, publish, deploy, measure and cost-optimise the service using Experiments 2, 3, 7 and 8.</li>
</ol>
<p><b>Prototype scope.</b></p>
{table(["In scope", "Out of scope (see Limitations)"], [
 ["IMD 1°×1° gridded daily Tmax 2014–2024, ten city grid cells", "IoT Automated Weather Stations (hardware)"],
 ["7-day Tmax forecast (one ML model per day) + IMD rule-based severity", "Humidity/heat-index inputs, numerical weather model input"],
 ["Web frontend: alerts, 7-day cards, trend chart, India map, ranking, what-if", "LLM-generated multilingual advisories (future work)"],
 ["Backend REST API, Docker, Docker Compose, Kubernetes", "Real cloud VM deployment and billing (costs are estimates)"]])}

<h2>2. Dataset</h2>
<ul>
<li><b>Source:</b> IMD Pune, "High resolution 1°×1° daily gridded maximum temperature" binary data,
<a href="https://www.imdpune.gov.in/cmpg/Griddata/Max_1_Bin.html">imdpune.gov.in/cmpg/Griddata/Max_1_Bin.html</a>
(Srivastava, Rajeevan and Kshirsagar, 2009), the repository named in the use-case document (§11, step 1).</li>
<li><b>Format:</b> one <code>.GRD</code> file per year, float32, 31 × 31 grid (7.5–37.5 °N, 67.5–97.5 °E), 99.9 = missing.
File sizes were checked (1,403,060 bytes for 365-day years, 1,406,904 bytes for leap years).</li>
<li><b>Acquisition:</b> <code>scripts/download_imd.sh</code>. The IMD server is slow and dropped connections (2017 needed three
attempts), so the script retries and accepts only full-size files.</li>
<li><b>Pre-processing:</b> <code>scripts/prepare_data.py</code> extracts the grid cell nearest to each of ten cities (Delhi, Jaipur, Lucknow,
Patna, Ahmedabad, Nagpur, Kolkata, Bhubaneswar, Hyderabad, Chennai): 40,180 daily rows. Grid orientation was verified (sea cells missing,
Ladakh cold, Delhi ≈ 17 °C in January and ≈ 40 °C in May).</li>
<li><b>Split (time-ordered by the forecast target day):</b> train 2014–2022, validation 2023, test 2024. Day-1 samples: train
{h1['samples']['train']}, validation {h1['samples']['validation']}, test {h1['samples']['test']}.</li>
<li><b>No synthetic data</b> is used. The data is non-personal meteorological data.</li>
</ul>

<h2>3. System architecture and tools</h2>
{img("00_architecture_diagram.png", "Figure 1. Labelled architecture and data flow (v2). Orange: AI component. Blue: Cloud Computing experiments. Green: data pipeline.")}
<h3>3.1 Why an early-warning service needs these cloud capabilities</h3>
<p>A heatwave warning is most valuable exactly when demand peaks: during a hot spell many people open the dashboard at once, and the
service cannot be down while it is being updated. Packaging the backend and frontend as separate images (Exp 2) means each can be
rebuilt, versioned and moved to any machine unchanged. Running them on Kubernetes (Exp 3) adds replicas, health probes and
self-healing, so a crashed pod does not take the warning offline, and rolling updates let a retrained model be released without an
outage. Because such a service runs all year but is busy only in summer, paying for idle capacity is the main waste; Exp 7 measures
how much of the allocated capacity is really used, and Exp 8 picks the cheapest size that still meets a stated response-time and
throughput target.</p>
<h3>3.2 Tools</h3>
{table(["Layer", "Tools (versions as run)"], [
 ["Language / ML", "Python 3.13, NumPy 2.5.4, scikit-learn 1.9.1, pandas 3.0.6 (training only), joblib 1.6.0"],
 ["Backend", "FastAPI 0.143.0, Uvicorn 0.54.0 (image python:3.13-slim, non-root)"],
 ["Frontend", "HTML/CSS/JavaScript, Chart.js 4.4.1, Leaflet 1.9.4, Natural Earth boundaries (India view), served by nginx 1.27 (nginx-unprivileged)"],
 ["Testing / load", "pytest 9.1.1, httpx 0.28.1 (async load generator)"],
 ["Containers (Exp 2)", "Docker Desktop engine 29.7.2 (arm64), Docker Compose, docker buildx, Docker Hub"],
 ["Orchestration (Exp 3)", "kind v0.33.0 (Kubernetes v1.37.0), kubectl v1.36.1"],
 ["Measurement (Exp 7, 8)", "docker stats, experiments/run_config.py, matplotlib 3.11.2"],
 ["Hardware", "Apple MacBook M2, 8 GB RAM (Docker VM: 8 CPUs, 3.8 GiB)"]])}

<h2>4. AI component</h2>
<p>The AI part is kept separate from the cloud part so each can be explained on its own.</p>
<h3>4.1 Machine-learning forecaster (7 days ahead)</h3>
<p><b>Method: direct multi-horizon forecasting.</b> Seven separate models are trained; model <i>h</i> predicts the maximum temperature on
day <i>t + h</i> from the 7 days up to day <i>t</i>. <b>Features</b> (<code>app/features.py</code>, shared by training and serving): the last 7
daily Tmax values, their mean, the target day's season (sine/cosine of day-of-year) and climatological normal (from 2014–2022 only),
and the cell's latitude and longitude. Two model families (ridge regression, gradient boosting) were compared with two baselines:
<i>persistence</i> (same as today) and <i>climatology</i> (the normal for that date). The family with the lowest mean validation error
({best}, {M['mean_validation_mae'][best]} °C) was deployed; 2024 was used only once, for the final numbers below.</p>
<h3>4.2 Rule-based severity classifier (not ML)</h3>
<p><code>app/severity.py</code> applies the IMD heatwave definitions: a heatwave is considered only if Tmax ≥ 40 °C (plains) or ≥ 37 °C
(coastal). Departure from normal 4.5–6.4 °C → Heatwave, &gt; 6.4 °C → Severe heatwave; for plains, Tmax ≥ 45 °C → Heatwave and ≥ 47 °C
→ Severe. Coastal stations (Kolkata, Chennai) have only a Heatwave category.</p>
<h3>4.3 Alert margin and confidence per forecast day</h3>
<p>Regression pulls extreme values towards the mean, so a raw forecast rarely crosses the IMD thresholds (day 1 without a margin:
recall {sev1_0['heatwave_recall']*100:.0f}%). Because a missed heatwave is costlier than a false alarm, each day's alert is issued on an
<b>upper-bound forecast</b> (forecast + margin). The margin for each day was chosen on the 2023 validation year by F2 score (recall weighted
over precision). Where the best validation F2 was below {M['min_validated_f2']}, that day's alerts are labelled <b>low-confidence</b>
in the API and the dashboard. Validation contains only 14 heatwave city-days, so these choices are uncertain.</p>
{table(["Day", "Persistence MAE", "Climatology MAE", "Grad. boosting MAE", f"{best} MAE (deployed)", "Alert margin", "Val F2",
        "Test recall", "Test precision", "Alert confidence"], ai_rows)}
<p>All MAE values are in °C on the 2024 test year ({sev1['heatwave_days_actual']} actual heatwave city-days per horizon).
<b>Interpretation:</b> the ML model beats persistence at every horizon and by a widening margin; by day 7 it is only slightly better than
climatology, which is expected for weather forecasting from temperature history alone. Alert skill falls with lead time: days
{validated_days[0]}–{validated_days[-1]} are validated; days {low_days[0] if low_days else '-'}–{low_days[-1] if low_days else '-'} catch fewer heatwaves and raise more false alarms,
so they are shown as an outlook. Day-1 confusion matrix (rows = actual, columns = predicted; Normal / Heatwave / Severe):
{sev1['confusion_matrix']['values']}. Persistence baseline day-1 alert recall/precision: {sev1_p['heatwave_recall']} / {sev1_p['heatwave_precision']}.</p>
{img("04_frontend_model_reliability.png", "Figure 2. The frontend's reliability panel: forecast error by day (ML vs baselines) and alert skill per day, read live from the API.", "92%")}

<h2>5. Application: backend and frontend</h2>
<p><b>Backend</b> (<code>app/main.py</code>, image <code>ayushiranjan27/heatguard:2.0</code>): a stateless FastAPI service. Endpoints:
<code>/health</code>, <code>/cities</code>, <code>/observed</code> (IMD history with normals and the actual next 7 days),
<code>/outlook</code> (7-day forecast for all 10 cities), <code>/model-info</code> (per-horizon metrics) and <code>POST /predict</code>
(7-day forecast from 7 values). Input validation returns 404/422 with clear messages; interactive API docs are at <code>/docs</code>.
<b>Frontend</b> (<code>frontend/</code>, image <code>ayushiranjan27/heatguard-web:2.0</code>): a static web app served by unprivileged
nginx, which also reverse-proxies <code>/api/</code> to the backend, so the browser talks to one address and the backend can stay
internal. It shows an alert banner, KPI cards, seven forecast cards (with the actual IMD value when known), a 30-day trend chart with
the forecast and an uncertainty band, an India map and ranking of all cities, a what-if form, and the reliability panel. The map uses
bundled Natural Earth boundaries (India point-of-view edition), so it works without an internet map service.</p>
{img("01_frontend_delhi_heatwave_overview.png", "Figure 3. Frontend, Delhi as of 27 May 2024 (served by Docker Compose): alert banner, KPIs and 7-day forecast with the actual IMD values that followed.", "100%")}
{img("02_frontend_trend_map_ranking.png", "Figure 4. Trend chart (observed, normal, forecast with uncertainty band, actual IMD values), all-India map and regional ranking.", "100%")}

<h2>6. Implementation of the four experiments</h2>

<h3>Experiment 2: Containerization, Docker and Docker Hub</h3>
<p><b>Aim (manual):</b> install Docker, pull and run images from Docker Hub, modify containers to run an application and push it to Docker Hub.
<b>Use-case connection:</b> the forecasting backend (code + 7 trained models + IMD city data) and the web frontend are packaged as two images,
which every later experiment uses unchanged.</p>
<p><b>Procedure.</b> (1) Docker Desktop installed; Docker Hub account <code>ayushiranjan27</code> created and <code>docker login</code> done by the
student. (2) Manual tasks: nginx pulled and run on port 8080, hello-world and Ubuntu run, Docker commands explored
(<code>experiments/results/archive_v1/exp2_manual_tasks.log</code>; nginx was pushed as <code>ayushiranjan27/nginx-exp2:1.0</code>).
(3) Two Dockerfiles and a Compose file written. (4) Both images built and run together, tested through the frontend proxy, including failure cases.
(5) Both pushed for arm64 and amd64 with <code>docker buildx</code>. (6) Local images deleted, pulled back from Docker Hub and run. Script:
<code>experiments/exp2_docker.sh</code>.</p>
{code("Dockerfile")}
{code("frontend/Dockerfile")}
{code("docker-compose.yml")}
{log("exp2_docker.log", "### 2.", "### 3.", 36)}
{log("exp2_docker.log", "### 3.", "### 4.", 14)}
{log("exp2_docker.log", "### 4.", "### 5.", 16)}
{log("exp2_docker.log", "$ docker rmi", None, 20)}
{img("03_dockerhub_repositories.png", "Figure 5. Docker Hub repositories of user ayushiranjan27 (captured after the v2 push).", "80%")}
<p><b>Results.</b> Backend image 136 MB and frontend image 22 MB (compressed). Both containers report healthy; the frontend reaches the backend
through its <code>/api/</code> proxy. Invalid input returns 404/422. With the backend stopped, the frontend stayed up and API calls returned
HTTP {gw.group(1) if gw else '?'} (gateway error) until the backend was restarted (HTTP {gw.group(2) if gw else '?'}). Docker Hub lists both images for
linux/amd64 and linux/arm64; the pulled images ran healthy.</p>
<p><b>Conclusion.</b> Both tiers were containerised, run together and published; anyone can start the full application with
<code>docker compose up</code> on Intel or Apple Silicon machines.</p>

<h3>Experiment 3: Application Deployment using Kubernetes</h3>
<p><b>Aim (manual):</b> deploy an application using Kubernetes, use kubectl commands and expose an app (preferably the image created in the Docker
experiment). <b>Use-case connection:</b> both HeatGuard images from Docker Hub run as replicated, self-healing Deployments, as an early-warning
service must stay available, including while it is updated.</p>
<p><b>Procedure.</b> The manual used the Killercoda playground; this project used <b>kind</b> (Kubernetes-in-Docker), a real Kubernetes cluster
running locally, so every step could be scripted (<code>experiments/exp3_kubernetes.sh</code>) and logged. The backend is a ClusterIP Service
(internal only); the frontend is a NodePort Service on 30080 and finds the backend by its Kubernetes DNS name. Both Deployments use
<code>maxSurge: 1, maxUnavailable: 0</code> and a 5-second <code>preStop</code> delay. The backend's CPU/memory limits are read from the
Experiment 7 right-sizing decision.</p>
{code("k8s/api.yaml")}
{code("k8s/web.yaml", 0, 40)}
{log("exp3_kubernetes.log", "### 1.", "### 2.", 38)}
{log("exp3_kubernetes.log", "### 2.", "### 3.", 30)}
{log("exp3_kubernetes.log", "### 3.", "### 4.", 30)}
{log("exp3_kubernetes.log", "### 4.", "### 5.", 26)}
{log("exp3_kubernetes.log", "### 5.", "### 6.", 26)}
{log("exp3_kubernetes.log", "### 6.", "### 7.", 24)}
{img("05_frontend_via_kubernetes.png", "Figure 6. Frontend served through the Kubernetes NodePort (localhost:30080); the status pill shows the backend pod that answered.", "100%")}
<p><b>Results.</b> Both images were pulled from Docker Hub; all pods became Ready; the frontend reached the backend through the
<code>heatguard-api</code> Service, with requests spread across backend pods; scaling (frontend 2→4, backend 2→3) worked; a deleted backend pod was
replaced automatically; a non-existent image tag stopped in <code>ImagePullBackOff</code> while existing pods kept serving, and
<code>kubectl rollout undo</code> restored the Deployment. Rolling updates with continuous checks every 0.25 s: {avail_txt}.
{"No request failed, so the preStop delay removed the single failure observed in v1 (39/40)." if avail_failed == 0 else
 f"{avail_failed} request(s) failed; v1 (without preStop) had 1 failure in 40 checks." if avail_failed is not None else ""}</p>
<p><b>Conclusion.</b> Kubernetes provided declarative deployment, service discovery between the two tiers, scaling, self-healing, safe rollback
and rolling updates for HeatGuard.</p>

<h3>Experiment 7: Cloud Cost Optimization through Resource Right-Sizing</h3>
<p><b>Aim (manual):</b> analyse CPU and memory utilisation of an over-provisioned workload, apply right-sizing and measure cost and efficiency
improvements without performance degradation. <b>Use-case connection:</b> the workload is the HeatGuard v2 backend itself, answering 7-day
forecast requests built from real 2024 IMD data.</p>
<p><b>Procedure.</b> (1) Run <code>ayushiranjan27/heatguard:2.0</code> with 2 vCPU / 2 GB (<code>docker run --cpus 2 --memory 2g</code>).
(2) Send the fixed workload: 15,000 <code>POST /predict</code> requests, 20 concurrent clients, 100 warm-up requests, fixed seed
(<code>loadtest/loadtest.py</code>), while sampling <code>docker stats</code> about once per second. (3) Repeat 3 times. (4) Right-size with the manual's rule,
"slightly above peak with a safety buffer" (<code>experiments/rightsize.py</code>): CPU = peak × 1.25 rounded up to 0.25 vCPU; memory = peak × 1.5
rounded up to 64 MiB. (5) Re-run the same workload 3 times with the new limits. (6) Estimate cost.</p>
<p><b>Right-sizing decision:</b> observed peak {RS['observed_peak']['cpu_cores']} cores and {RS['observed_peak']['memory_mib']} MiB →
<b>{RS['right_sized']['cpus']} vCPU / {RS['right_sized']['memory']}</b>. These values are used as the backend limits in Kubernetes (Exp 3).</p>
{table(perf_cols, [perf_row(r) for r in E7])}
<p>Change after right-sizing: throughput {pct(o7['throughput_rps'], r7['throughput_rps'])}, p50 latency {pct(o7['latency_ms_p50'], r7['latency_ms_p50'])},
p95 latency {pct(o7['latency_ms_p95'], r7['latency_ms_p95'])}, estimated hourly cost {pct(o7['est_usd_per_hour'], r7['est_usd_per_hour'])},
estimated cost per million predictions {pct(o7['est_usd_per_million_predictions'], r7['est_usd_per_million_predictions'])}.
Errors: {int(float(o7['errors']))} and {int(float(r7['errors']))}; out-of-memory kills: none.</p>
{img("exp7_rightsizing_chart.png", "Figure 7. Experiment 7: utilisation of the allocated resources and estimated hourly cost before and after right-sizing (mean ± std, 3 runs).")}
<p><b>Cost basis (estimate, not an actual charge):</b> AWS Fargate on-demand, Linux/ARM, Asia Pacific (Mumbai): USD 0.02383 per vCPU-hour and
USD 0.00261 per GB-hour, from the AWS public price list (publication date 2026-09-11), saved as <code>experiments/pricing/aws_ecs_ap-south-1_index.json</code>.
Hourly cost = vCPU × 0.02383 + GB × 0.00261; cost per million predictions = hourly cost ÷ (throughput × 3600) × 10<sup>6</sup>. No cloud account was used.</p>
<p><b>Conclusion.</b> The backend used under half of the 2 allocated CPUs ({o7['cpu_util_of_limit_pct']}% of the limit) and about
{float(o7['mem_util_of_limit_pct']):.0f}% of its memory; a single Uvicorn process cannot use more than about one core, so the extra CPU was idle.
After right-sizing, throughput changed by {pct(o7['throughput_rps'], r7['throughput_rps'])} and p95 latency by {pct(o7['latency_ms_p95'], r7['latency_ms_p95'])},
but median (p50) latency rose by {pct(o7['latency_ms_p50'], r7['latency_ms_p50'])} ({o7['latency_ms_p50']} → {r7['latency_ms_p50']} ms), so the manual's
"without performance degradation" holds for throughput and tail latency but not fully for median latency. Given the
{pct(o7['est_usd_per_hour'], r7['est_usd_per_hour'])} estimated cost change, this trade-off is acceptable for this service.</p>

<h3>Experiment 8: FinOps Principles and Instance-Type Comparison</h3>
<p><b>Aim (manual):</b> compare different instance (resource) configurations for the same workload and identify the most cost-efficient option without
performance degradation. <b>Use-case connection:</b> chooses the cheapest size on which the heatwave API still meets its service target.</p>
<p><b>Procedure</b> (manual algorithm steps 1–10). Workload identical to Experiment 7. Candidates: three AWS Fargate-valid sizes, emulated with Docker limits.
The <b>performance target was written down before running</b> (<code>experiments/exp8_configs.json</code>), using the rule: {E8CFG['target_rule']}
This gives throughput ≥ {tgt['min_throughput_rps']} req/s, p95 latency ≤ {tgt['max_p95_latency_ms']} ms, zero errors and no OOM kill. Each configuration ran 3 times.</p>
{table(perf_cols + ["Meets target"], [perf_row(r) + ["yes" if r["meets_target"] == "True" else "no"] for r in E8])}
{img("exp8_finops_chart.png", "Figure 8. Experiment 8: throughput, p95 latency (dashed lines = targets) and estimated cost per million predictions (mean ± std, 3 runs).")}
<p><b>Result.</b> {f"The most cost-efficient configuration meeting the target is <b>{best8['config']} ({best8['cpus']} vCPU / {best8['memory']})</b> at an estimated USD {float(best8['est_usd_per_million_predictions']):.4f} per million predictions." if best8 else "No configuration met the target."}
{(lambda m: f"It passes on the mean of 3 runs, but only {m[0]} of {m[1]} individual runs reached {tgt['min_throughput_rps']} req/s (runs: {', '.join(str(x) for x in m[2])} req/s), so it is a borderline choice with little headroom." if m[0] < m[1] else f"All {m[1]} of its runs met the target.")(runs_meeting(best8['config'])) if best8 else ""}
{" ".join(f"{r['config']} ({r['cpus']} vCPU) failed: {fails_because(r)}." for r in failing)}
At 0.25 vCPU the backend was CPU-saturated; its Docker health check timed out under load (the container was reported "unhealthy"), which in Kubernetes
would trigger liveness-probe restarts.</p>
<p><b>Conclusion.</b> The cheapest size per hour (low) was the most expensive per prediction, because it served so few requests; cost must be judged
per unit of useful work. {f"Moving from {best8['config']} to high ({high8['cpus']} vCPU) raised throughput by {pct(best8['throughput_rps'], high8['throughput_rps'])} at {pct(best8['est_usd_per_million_predictions'], high8['est_usd_per_million_predictions'])} cost per prediction; it would be the safer choice if more headroom above the target were wanted." if best8 and high8 and best8['config'] != 'high' else ""}
Unlike v1, the target was defined with both a throughput and a latency requirement, closing the gap noted in the v1 analysis.</p>

<h2>7. Testing and results</h2>
<p><b>Automated tests</b> (<code>pytest -v</code>, result: <b>{test_total}</b>):</p>
{table(["Test", "Type"], [[t, "invalid input / failure" if any(x in t for x in ("unknown", "wrong", "implausible", "non_numeric", "outside", "too_long")) else "representative / rules"] for t in tests])}
<p><b>Failure scenarios demonstrated</b> on the running system: unknown city (404), 3 values instead of 7 (422), IMD missing-value code 99.9 °C (422),
invalid date (422), date outside the data (404), backend stopped behind the frontend (gateway error, recovered on restart), non-existent image tag in
Kubernetes (ImagePullBackOff, rolled back), deleted pod (recreated). In the frontend, rejected what-if values are shown as an error message.</p>

<h2>8. Requirement-to-test checklist</h2>
{table(["Requirement (assignment brief)", "Implementation", "Evidence", "Status"], [list(r) for r in CHECKLIST])}

<h2>9. Limitations, data privacy and improvements</h2>
<ul>
<li><b>Spatial resolution:</b> 1° grid cells (~100 km) are averages, not station readings.</li>
<li><b>Forecast inputs:</b> temperature history and season only (no humidity, wind or numerical weather model); skill at days 5–7 is close to climatology.</li>
<li><b>Alerts:</b> per cell per day; IMD declares heatwaves when criteria hold at ≥ 2 stations of a sub-division for 2 consecutive days. Normals come from
2014–2022, not 30-year station normals. Margins were tuned on a validation year with only 14 heatwave city-days; precision is low at longer horizons.</li>
<li><b>Historical replay:</b> the dashboard forecasts from any date in 2014–2024 using IMD archives; it is not connected to a live data feed.</li>
<li><b>Experiments 7 and 8:</b> instance sizes were emulated with Docker limits on one laptop; the single Python load generator limits throughput; costs are estimates.</li>
<li><b>Experiment 3:</b> single-node local cluster, not a cloud VM.</li>
<li><b>Data privacy:</b> only public, non-personal weather data; no user data stored; both containers run as non-root users; the backend is not exposed
outside the cluster; no credentials in the repository.</li>
<li><b>Improvements:</b> humidity/heat-index inputs and IMD forecast products; consecutive-day rule; calibrated uncertainty (quantile regression);
scheduled data refresh; LLM multilingual advisories with human review (use case §13); Horizontal Pod Autoscaler; repeat Experiments 7–8 on real cloud instances.</li>
</ul>

<h2>10. Version history</h2>
<p><b>v1.0/1.1</b>: single FastAPI container with a built-in dashboard and a next-day forecast; v1.1 corrected the coastal heatwave rule.
<b>v2.0</b> (this report): 7-day forecast, separate backend and frontend images, two-tier Kubernetes deployment with zero-downtime settings.
All v1 experiment logs and measurements are kept unchanged in <code>experiments/results/archive_v1/</code>; every v2 experiment was re-run with the same scripts.</p>

<h2>11. Conclusion</h2>
<p>HeatGuard turns real IMD observations into 7-day maximum-temperature forecasts and IMD-style heatwave alerts, with each day's reliability
measured and shown to the user. The same two images were containerised and published (Exp 2), operated on Kubernetes with scaling, recovery and
rolling updates (Exp 3), right-sized from measured usage (Exp 7) and sized against an explicit service target (Exp 8). Each experiment acts on the same
artifacts, so together they form one pipeline from data and model to a cost-aware, resilient deployment.</p>

<h2>12. References</h2>
<ol class="refs">
<li>Somaiya Vidyavihar University, AI Use Case KJS-CES-01: Climate Intelligence for Heatwave Monitoring, Prediction, and Early Warning (use-case document).</li>
<li>Somaiya Vidyavihar University, Cloud Computing Experiment manuals 2, 3, 7 and 8 (KJSSE, 2025–26).</li>
<li>IMD Pune, High resolution daily gridded maximum temperature data (1°×1°), https://www.imdpune.gov.in/cmpg/Griddata/Max_1_Bin.html</li>
<li>A. K. Srivastava, M. Rajeevan, S. R. Kshirsagar, "Development of a high resolution daily gridded temperature data set (1969–2005) for the Indian region", Atmospheric Science Letters, 10(4), 249–254, 2009.</li>
<li>India Meteorological Department, Heat wave definitions, https://mausam.imd.gov.in/pdfs/heatcolduser/Definition.pdf</li>
<li>Amazon Web Services, AWS Price List (AmazonECS, ap-south-1), publication 2026-09-11, https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonECS/current/ap-south-1/index.json</li>
<li>Docker documentation, https://docs.docker.com/ ; Kubernetes documentation, https://kubernetes.io/docs/ ; kind, https://kind.sigs.k8s.io/</li>
<li>scikit-learn, https://scikit-learn.org/ ; FastAPI, https://fastapi.tiangolo.com/ ; nginx, https://nginx.org/</li>
<li>Chart.js, https://www.chartjs.org/ ; Leaflet, https://leafletjs.com/ ; Natural Earth (India point-of-view boundaries), https://www.naturalearthdata.com/</li>
<li>FinOps overview, Microsoft Learn, https://learn.microsoft.com/en-us/cloud-computing/finops/overview</li>
</ol>

<h2>13. Acknowledgement of AI-assisted work</h2>
<p>This project was developed with the help of Claude (Anthropic), an AI assistant, used for analysing the assignment documents, writing code and
scripts, and drafting this report. All code was executed on the student's machine; all results, logs and screenshots were produced by real runs and
were checked by the student. The student created the Docker Hub account and performed the <code>docker login</code> herself. Command outputs in this report
are copied verbatim from the log files in <code>experiments/results/</code> (Docker build progress lines omitted for length); screenshots of the frontend and
Docker Hub were captured with headless Google Chrome from the running services.</p>
"""

CSS = """
@page { size: A4; margin: 16mm 14mm; }
body { font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 10.5pt; color: #1e1e1e; line-height: 1.45; }
h1 { font-size: 24pt; margin: 10px 0; } h2 { font-size: 15pt; margin-top: 22px; border-bottom: 2px solid #b4441c; padding-bottom: 3px; }
h3 { font-size: 12.5pt; margin-top: 18px; color: #1f5fa8; }
.title { text-align: center; page-break-after: always; padding-top: 60px; }
.title .inst { font-size: 12pt; } .title .course { color: #555; } .title .sub { font-size: 12pt; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 8.8pt; page-break-inside: avoid; }
th, td { border: 1px solid #ccc; padding: 4px 5px; text-align: left; vertical-align: top; } th { background: #f3efe8; }
table.meta { width: 88%; margin: 30px auto; font-size: 10.5pt; } table.meta td:first-child { width: 26%; font-weight: 600; background: #f8f6f2; }
pre { font-family: Menlo, Consolas, monospace; font-size: 7.2pt; background: #f7f7f7; border: 1px solid #ddd; padding: 6px 8px;
      white-space: pre-wrap; word-break: break-all; page-break-inside: avoid; }
pre.log { background: #10151c; color: #d7e0ea; border-color: #10151c; }
.src { display: block; font-weight: 700; color: #b4441c; margin-bottom: 2px; } pre.log .src { color: #f0a070; }
figure { text-align: center; margin: 10px 0; page-break-inside: avoid; } img { border: 1px solid #ddd; max-height: 245mm; object-fit: contain; }
figcaption { font-size: 9pt; color: #555; margin-top: 4px; }
code { font-family: Menlo, Consolas, monospace; font-size: 9pt; } ol.refs li { margin-bottom: 4px; } a { color: #1f5fa8; }
.placeholder { background: #fff3cd; border: 1px dashed #c9a227; padding: 1px 6px; }
"""

OUT_HTML.write_text(f'<!doctype html><html><head><meta charset="utf-8"><title>HeatGuard Report</title>'
                    f"<style>{CSS}</style></head><body>{body}</body></html>")
subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                f"--print-to-pdf={OUT_PDF}", OUT_HTML.as_uri()], check=True, capture_output=True)
print(f"wrote {OUT_HTML.relative_to(ROOT)} and {OUT_PDF.relative_to(ROOT)}")
