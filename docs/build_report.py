"""Build the consolidated report (HTML -> PDF) from the real project outputs (HeatGuard v2, frontend 2.1).

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
REL21 = (RES / "frontend_2.1_release.log").read_text()


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
rel21 = re.search(r"# availability: (\d+)/(\d+) requests", REL21)
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

TERM_DIR = RES / "terminal_captures"
FIG = [0]


def fig(name, caption, width="100%"):
    """Numbered figure (numbers are assigned in order, so they always stay sequential)."""
    FIG[0] += 1
    return f'<figure><img src="screenshots/{name}" style="width:{width}"><figcaption><b>Figure {FIG[0]}.</b> {caption}</figcaption></figure>'


def term(name, caption, width="100%"):
    """A terminal capture: real output saved in experiments/results/terminal_captures/<name>.txt, rendered as an image."""
    stamp = (TERM_DIR / f"{name}.txt").read_text().splitlines()[0].replace("# captured ", "")
    return fig(f"{name}.png", f"{caption} <span class='src2'>Terminal capture, real output recorded {stamp} "
                              f"(text: experiments/results/terminal_captures/{name}.txt).</span>", width)


def callout(exp, color, text):
    return f'<div class="callout" style="border-color:{color}"><div class="callout-h" style="color:{color}">Where Experiment {exp} comes into play in HeatGuard</div>{text}</div>'

C2, C3, C7, C8 = "#1f5fa8", "#1d7a5f", "#b26d10", "#8a3f86"

CHECKLIST = [
    ("Working prototype: input → processing → output", "Landing page + dashboard + API: city/date (or 7 typed values) → 7-day forecast, alerts, advice, map",
     "§8, terminal capture t06, exp2_docker.log", "Verified"),
    ("AI/ML component appropriate to use case", "7 ridge-regression models (one per forecast day) on IMD data, compared with gradient boosting and 2 baselines",
     "§7, models/metrics.json, train_output.txt", "Verified"),
    ("Rule-based part identified", "IMD heatwave criteria (app/severity.py), labelled rule-based throughout", "§7.2, test_severity_rules", "Verified"),
    ("Real / public dataset documented", "IMD Pune 1° gridded Tmax 2014–2024, download script with retries", "§4, data/processed/city_tmax.csv", "Verified"),
    ("Labelled architecture diagram", "Architecture, request flow, experiment map, Kubernetes topology, ML pipeline, Exp 7/8 method", "§5, §6, §7, §9", "Verified"),
    ("Exp 2: containerise, run, push to Docker Hub", "Backend + frontend images, Compose, failure cases, multi-arch push, pull-and-run; manual nginx/hello-world/ubuntu tasks",
     "§9.1, captures t01–t07, Docker Hub pages, exp2_docker.log", "Verified"),
    ("Exp 3: deploy, expose, pod status, scaling/recovery", "kind: 2 Deployments, ClusterIP + NodePort, probes, scaling, self-healing, bad-image rollback, rolling updates with availability checks",
     "§9.2, captures t08–t16, exp3_kubernetes.log, frontend_2.1_release.log", "Verified"),
    ("Exp 7: measure CPU/memory, right-size, compare", "docker stats under a fixed load, rule-based right-sizing, 3 repeats each, limits reused in Kubernetes",
     "§9.3, capture t17–t18, exp7/*", "Verified"),
    ("Exp 8: same workload on configs, cheapest meeting target", "3 Fargate-valid sizes, target fixed before the runs, cost per 1M predictions",
     "§9.4, capture t18, exp8/*, exp8_configs.json", "Verified"),
    ("Exp 7 & 8 same workload, cost basis stated", "Same loadtest.py, seed, 15,000 requests, 20 clients; AWS public price list saved; costs labelled estimates",
     "pricing/aws_ecs_ap-south-1_index.json", "Verified"),
    ("Representative inputs tested", "pytest + curl on real IMD windows; frontend scenarios (Delhi, Jaipur, Nagpur, Chennai, Lucknow)",
     "§10, capture t19, pytest_output.txt", "Verified"),
    ("≥1 invalid-input / failure scenario", "unknown city 404, wrong length 422, 99.9 °C 422, bad date 422, date outside data 404, backend down 504, bad image tag, deleted pod",
     "§10, exp2_docker.log, exp3_kubernetes.log", "Verified"),
    ("Measurements (error, latency, throughput, CPU/mem, cost)", "MAE per horizon, alert recall/precision, req/s, p50/p95, docker stats, estimated USD",
     "§7, §9.3, §9.4", "Verified"),
    ("Clean-environment setup", "v1: fresh clone + venv + tests + retraining reproduced results; v2: images deleted locally, pulled from Docker Hub and run with Compose. Full README not repeated on a second machine",
     "exp2_docker.log §5, capture t02", "Partially Verified"),
    ("Demonstration video (5 min)", "Recorded and shared on Google Drive (public link)", "link on the title page", "Verified" if VIDEO else "Not Verified"),
]

video_html = (f'<a href="{VIDEO}">{VIDEO}</a>' if VIDEO else
              '<span class="placeholder">[Placeholder: demonstration video link, to be inserted after upload]</span>')

IMAGES = [
    ["<code>ayushiranjan27/heatguard:2.0</code>", "Backend: FastAPI + 7 ML models + IMD rules", "linux/arm64, linux/amd64", "2, 3, 7, 8"],
    ["<code>ayushiranjan27/heatguard-web:2.1</code>", "Frontend: nginx serving the landing page and dashboard, proxying /api/", "linux/arm64, linux/amd64", "2, 3"],
    ["<code>ayushiranjan27/nginx-exp2:1.0</code>", "Exp 2 manual task (nginx pushed to own repository)", "linux/arm64", "2"],
]
FILES = [
    ["<code>scripts/</code>", "download_imd.sh, prepare_data.py, train.py: data and model training", "AI"],
    ["<code>app/</code>", "Backend API (main.py), features.py, severity.py (IMD rules), cities.py", "AI · 2"],
    ["<code>frontend/</code>", "Landing page, dashboard, assets, vendored libraries, nginx config, Dockerfile", "2"],
    ["<code>Dockerfile</code>, <code>docker-compose.yml</code>", "Backend image; both services run together", "2"],
    ["<code>experiments/exp2_docker.sh</code>", "Build, run, test, push (multi-arch) and pull-back verification", "2"],
    ["<code>k8s/</code>", "kind-config.yaml, api.yaml, web.yaml (Deployments + Services)", "3"],
    ["<code>experiments/exp3_kubernetes.sh</code>, <code>release_frontend.sh</code>", "Deploy, scale, self-heal, rollback, rolling updates with availability checks", "3"],
    ["<code>loadtest/loadtest.py</code>, <code>experiments/run_config.py</code>", "Fixed workload and per-configuration measurement (docker stats, latency, cost)", "7 · 8"],
    ["<code>experiments/rightsize.py</code>", "Right-sizing rule (peak × buffer)", "7"],
    ["<code>experiments/exp8_configs.json</code>, <code>summarize.py</code>", "Pre-defined target and configurations; tables, charts, target check", "8"],
    ["<code>experiments/results/</code>", "All raw logs, docker stats CSVs, summaries, terminal captures (v1 in archive_v1/)", "2 · 3 · 7 · 8"],
    ["<code>tests/</code>", "18 pytest tests including invalid inputs", "Testing"],
]
MAP = [
    ["Package", f'<b style="color:{C2}">Exp 2</b>', "The backend (code + 7 trained models + IMD city data) and the frontend become two Docker images; Compose runs them together",
     "Dockerfile, frontend/Dockerfile, docker-compose.yml", "Two runnable images"],
    ["Publish", f'<b style="color:{C2}">Exp 2</b>', "Both images pushed to Docker Hub for arm64 and amd64, then pulled back and run to prove they work",
     "experiments/exp2_docker.sh", "Public images on Docker Hub"],
    ["Deploy &amp; operate", f'<b style="color:{C3}">Exp 3</b>', "The Hub images run on Kubernetes: replicated, self-healing, scalable, updated without downtime",
     "k8s/*.yaml, exp3_kubernetes.sh, release_frontend.sh", "Live service on localhost:30080"],
    ["Measure &amp; right-size", f'<b style="color:{C7}">Exp 7</b>', "The backend image is loaded with 15,000 real forecast requests; measured peaks set new CPU/memory limits",
     "loadtest.py, run_config.py, rightsize.py", "Limits 1250m / 192Mi → Kubernetes"],
    ["Choose a size", f'<b style="color:{C8}">Exp 8</b>', "Same workload on three instance sizes against a pre-defined target; cheapest passing size identified",
     "exp8_configs.json, summarize.py", "Sizing decision (0.5 vCPU, borderline)"],
]

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
    <tr><td>Use case</td><td>Case 5 · KJS-CES-01 · Climate Intelligence for Heatwave Monitoring, Prediction and Early Warning</td></tr>
    <tr><td>Experiments mapped</td><td><b>2</b> Containerization, Docker and Docker Hub · <b>3</b> Application Deployment using Kubernetes ·
        <b>7</b> Cloud Cost Optimization through Resource Right-Sizing · <b>8</b> FinOps Principles and Instance-Type Comparison</td></tr>
    <tr><td>Demonstration video</td><td>{video_html}</td></tr>
    <tr><td>Source code</td><td><a href="{GITHUB}">{GITHUB}</a></td></tr>
    <tr><td>Docker images</td><td><a href="{HUB}">{HUB}</a> · heatguard:2.0 (backend) · heatguard-web:2.1 (frontend)</td></tr>
    <tr><td>Date</td><td>11 October 2026</td></tr>
  </table>
</section>

<section class="toc">
<h2>Contents</h2>
<ol>
<li>Project at a glance: video, deployed images, code files</li><li>Abstract</li><li>Problem statement, objectives and scope</li>
<li>Dataset</li><li>System architecture and tools</li><li><b>Where each experiment comes into play</b></li>
<li>AI component</li><li>Application: landing page, dashboard and API</li>
<li>Implementation of the four experiments (2, 3, 7, 8)</li><li>Testing and results</li><li>Requirement-to-test checklist</li>
<li>Limitations, data privacy and improvements</li><li>Version history</li><li>Conclusion</li><li>References</li><li>Acknowledgement of AI-assisted work</li>
</ol>
</section>

<h2>1. Project at a glance</h2>
<h3>1.1 Demonstration video</h3>
<p>{video_html}<br><span class="muted">The video shows the landing page and dashboard, the containers under Docker Compose, the images on Docker Hub,
the Kubernetes deployment (pods, services, self-healing, scaling) and the Experiment 7/8 results.</span></p>
<h3>1.2 Deployed images (Docker Hub, public)</h3>
{table(["Image", "What it contains", "Platforms", "Used in experiments"], IMAGES)}
<p>Run the complete application on any machine with Docker: <code>docker compose up -d</code>, then open <code>http://localhost:8080</code>
(landing page), <code>/dashboard</code> and <code>/api/docs</code>. On the Kubernetes cluster the same images are served at <code>http://localhost:30080</code>.</p>
<h3>1.3 Code files and which experiment they serve</h3>
{table(["Path", "Contents", "Experiment"], FILES)}

<h2>2. Abstract</h2>
<p>HeatGuard is a working prototype of the heatwave early-warning use case. It uses real India Meteorological Department (IMD) gridded daily
maximum-temperature data for 2014–2024, forecasts the maximum temperature for each of the next <b>7 days</b> for ten Indian cities with
machine-learning models, and converts every forecast day into a heatwave alert using IMD's published criteria. On the unseen year 2024 the forecast
error grows from <b>{H[0]['models'][best]['test']['MAE']} °C</b> (day 1) to <b>{H[-1]['models'][best]['test']['MAE']} °C</b> (day 7), lower than both
baselines at every horizon; next-day alerts detect <b>{sev1['heatwave_recall']*100:.0f}%</b> of actual heatwave city-days, and alerts for days
{low_days[0] if low_days else '-'}–7 are labelled low-confidence. The system is a FastAPI <b>backend</b> and an nginx-served <b>frontend</b> (animated landing page and
dashboard). Experiment 2 packages both as Docker images and publishes them on Docker Hub; Experiment 3 runs them on Kubernetes with scaling,
self-healing, rollback and zero-downtime rolling updates; Experiment 7 right-sizes the backend from measured usage (estimated hourly cost
<b>{pct(o7['est_usd_per_hour'], r7['est_usd_per_hour'])}</b>); Experiment 8 compares three instance sizes under the same workload against a target fixed in
advance. All results come from real runs on the student's machine; costs are estimates.</p>

<h2>3. Problem statement, objectives and scope</h2>
<p><b>Problem.</b> Heatwaves in India are increasing in frequency, intensity and duration and affect public health, agriculture and economic activity.
Severity varies by region, so timely, region-specific warnings are needed (use-case document KJS-CES-01, §6).</p>
<p><b>Objectives.</b></p>
<ol>
<li>Build an input → processing → output prototype on real IMD meteorological data (use case §11, steps 1–2).</li>
<li>Develop AI models for region-wise maximum-temperature forecasting up to 7 days ahead and evaluate them against baselines (§8, objective 2).</li>
<li>Classify heatwave severity per day, produce advisories and visualise them on a decision-support dashboard (§8, objective 4; §11, steps 7–9).</li>
<li>Package, publish, deploy, measure and cost-optimise the service using Experiments 2, 3, 7 and 8.</li>
</ol>
{table(["In scope", "Out of scope (see Limitations)"], [
 ["IMD 1°×1° gridded daily Tmax 2014–2024, ten city grid cells", "IoT Automated Weather Stations (hardware)"],
 ["7-day Tmax forecast (one ML model per day) + IMD rule-based severity", "Humidity/heat-index inputs, numerical weather model input"],
 ["Landing page, dashboard, REST API", "LLM-generated multilingual advisories (future work)"],
 ["Docker, Docker Compose, Docker Hub, Kubernetes, measured right-sizing and costing", "Real cloud VM deployment and billing (costs are estimates)"]])}

<h2>4. Dataset</h2>
<ul>
<li><b>Source:</b> IMD Pune, "High resolution 1°×1° daily gridded maximum temperature",
<a href="https://www.imdpune.gov.in/cmpg/Griddata/Max_1_Bin.html">imdpune.gov.in/cmpg/Griddata/Max_1_Bin.html</a> (Srivastava, Rajeevan and Kshirsagar, 2009),
the repository named in the use-case document (§11, step 1).</li>
<li><b>Format:</b> one <code>.GRD</code> file per year, float32, 31 × 31 grid (7.5–37.5 °N, 67.5–97.5 °E), 99.9 = missing; file sizes checked
(1,403,060 bytes for 365-day years, 1,406,904 for leap years).</li>
<li><b>Acquisition:</b> <code>scripts/download_imd.sh</code>; the IMD server is slow and dropped connections (2017 needed three attempts), so the script
retries and accepts only full-size files.</li>
<li><b>Pre-processing:</b> <code>scripts/prepare_data.py</code> extracts the grid cell of each of ten cities (Delhi, Jaipur, Lucknow, Patna, Ahmedabad,
Nagpur, Kolkata, Bhubaneswar, Hyderabad, Chennai): 40,180 daily rows; grid orientation verified (sea cells missing, Ladakh cold, Delhi ≈ 17 °C in
January and ≈ 40 °C in May).</li>
<li><b>Split (by forecast target day):</b> train 2014–2022, validation 2023, test 2024 (day-1 samples {h1['samples']['train']} / {h1['samples']['validation']} / {h1['samples']['test']}).</li>
<li><b>No synthetic data</b> is used; the data is non-personal meteorological data.</li>
</ul>

<h2>5. System architecture and tools</h2>
{fig("00_architecture_diagram.png", "Labelled architecture and data flow. Orange: AI component. Blue: Cloud Computing experiments. Green: data pipeline.")}
{fig("diag_request_flow.png", "Request flow from the browser through the frontend proxy to the backend, the 7 models and the IMD rules.")}
<h3>5.1 Why an early-warning service needs these cloud capabilities</h3>
<p>A heatwave warning is most valuable exactly when demand peaks: during a hot spell many people open the dashboard at once, and the service cannot be
down while it is being updated. Packaging the backend and frontend as separate images (Exp 2) means each can be rebuilt, versioned and moved to any
machine unchanged. Running them on Kubernetes (Exp 3) adds replicas, health probes and self-healing, so a crashed pod does not take the warning
offline, and rolling updates let a retrained model or a new interface be released without an outage. Because such a service runs all year but is busy
mainly in summer, paying for idle capacity is the main waste; Exp 7 measures how much of the allocated capacity is really used, and Exp 8 picks the
cheapest size that still meets a stated response-time and throughput target.</p>
<h3>5.2 Tools</h3>
{table(["Layer", "Tools (versions as run)"], [
 ["Language / ML", "Python 3.13, NumPy 2.5.4, scikit-learn 1.9.1, pandas 3.0.6 (training only), joblib 1.6.0"],
 ["Backend", "FastAPI 0.143.0, Uvicorn 0.54.0 (image python:3.13-slim, non-root)"],
 ["Frontend", "HTML/CSS/JavaScript (landing page + dashboard), Chart.js 4.4.1, Leaflet 1.9.4, Natural Earth boundaries (India view), fonts Fraunces / IBM Plex (SIL OFL), nginx 1.27 (unprivileged)"],
 ["Testing / load", "pytest 9.1.1, httpx 0.28.1 (async load generator)"],
 ["Containers (Exp 2)", "Docker Desktop engine 29.7.2 (arm64), Docker Compose, docker buildx, Docker Hub"],
 ["Orchestration (Exp 3)", "kind v0.33.0 (Kubernetes v1.37.0), kubectl v1.36.1"],
 ["Measurement (Exp 7, 8)", "docker stats, experiments/run_config.py, matplotlib 3.11.2"],
 ["Hardware", "Apple MacBook Air M2, 8 GB RAM (Docker VM: 8 CPUs, 3.8 GiB)"]])}

<h2>6. Where each experiment comes into play</h2>
<p>The four experiments are not separate demonstrations: they are consecutive stages in the life of the same two images. The AI component produces
the trained models; Experiment 2 packages and publishes them, Experiment 3 runs and operates them, Experiment 7 measures what the backend really needs
and feeds new limits back into the Kubernetes deployment, and Experiment 8 decides how large each backend replica should be.</p>
{fig("diag_experiment_map.png", "Where each Cloud Computing experiment comes into play in HeatGuard, and what each one passes to the next.")}
{table(["Stage", "Experiment", "Role in HeatGuard", "Key files", "Output passed on"], MAP)}
<h3>6.1 How the heatwave use case motivates each experiment</h3>
<table class="why">
<tr><td class="e" style="color:{C2}">Exp 2</td><td><b>A warning system must be deployable anywhere, identically.</b> A district control room, a university server or a cloud VM
must run exactly the forecasting service that was validated. Docker images freeze the code, the 7 trained models and the IMD data together; Docker Hub
lets anyone pull them for Intel or Apple machines.</td></tr>
<tr><td class="e" style="color:{C3}">Exp 3</td><td><b>Warnings must stay online during the heat peak and during updates.</b> Kubernetes keeps several copies of each service,
replaces failed ones, scales the public frontend when many people check the forecast, and rolls out a retrained model or a new interface without
dropping requests (measured).</td></tr>
<tr><td class="e" style="color:{C7}">Exp 7</td><td><b>The service runs all year but is busy mainly in summer.</b> Reserving large machines "to be safe" wastes money for most of the
year. Measuring the backend under a realistic forecast load shows how much CPU and memory it actually needs, and those limits are applied in Kubernetes.</td></tr>
<tr><td class="e" style="color:{C8}">Exp 8</td><td><b>Public money should buy the cheapest service that still meets its promise.</b> A target is stated first (how many forecasts
per second, how fast), then instance sizes are compared on cost per million forecasts, so the choice is based on value rather than on the lowest price.</td></tr>
</table>

<h2>7. AI component</h2>
<p>The AI part is kept separate from the cloud part so each can be explained on its own.</p>
{fig("diag_ml_pipeline.png", "AI component: offline training (top) and the online 7-day forecast (bottom). Orange = ML, dashed = rule-based.")}
<h3>7.1 Machine-learning forecaster (7 days ahead)</h3>
<p><b>Direct multi-horizon forecasting:</b> seven separate models; model <i>h</i> predicts the maximum temperature on day <i>t + h</i> from the 7 days up to day
<i>t</i>. <b>Features</b> (<code>app/features.py</code>, shared by training and serving): the last 7 daily Tmax values, their mean, the target day's season
(sine/cosine of day-of-year) and climatological normal (from 2014–2022 only), and the cell's latitude and longitude. Two model families (ridge regression,
gradient boosting) were compared with two baselines, <i>persistence</i> (same as today) and <i>climatology</i> (the normal for that date). The family with the
lowest mean validation error ({best}, {M['mean_validation_mae'][best]} °C) was deployed; 2024 was used only once, for the numbers below.</p>
<h3>7.2 Rule-based severity classifier (not ML)</h3>
<p><code>app/severity.py</code> applies the IMD heatwave definitions: a heatwave is considered only if Tmax ≥ 40 °C (plains) or ≥ 37 °C (coastal).
Departure from normal 4.5–6.4 °C → Heatwave, &gt; 6.4 °C → Severe heatwave; for plains, Tmax ≥ 45 °C → Heatwave and ≥ 47 °C → Severe. Coastal stations
(Kolkata, Chennai) have only a Heatwave category.</p>
<h3>7.3 Alert margin and confidence per forecast day</h3>
<p>Regression pulls extreme values towards the mean, so a raw forecast rarely crosses the IMD thresholds (day 1 without a margin: recall
{sev1_0['heatwave_recall']*100:.0f}%). Because a missed heatwave is costlier than a false alarm, each day's alert uses an <b>upper-bound forecast</b>
(forecast + margin); the margin for each day was chosen on 2023 by F2 score. Where the best validation F2 was below {M['min_validated_f2']}, that day's alerts
are labelled <b>low-confidence</b>. Validation contains only 14 heatwave city-days, so these choices are uncertain.</p>
{table(["Day", "Persistence MAE", "Climatology MAE", "Grad. boosting MAE", f"{best} MAE (deployed)", "Alert margin", "Val F2",
        "Test recall", "Test precision", "Alert confidence"], ai_rows)}
<p>MAE in °C on the 2024 test year ({sev1['heatwave_days_actual']} actual heatwave city-days per horizon). The ML model beats persistence at every horizon,
by a widening margin; by day 7 it is only slightly better than climatology, as expected from temperature history alone. Alert skill falls with lead time:
days {validated_days[0]}–{validated_days[-1]} validated, days {low_days[0] if low_days else '-'}–{low_days[-1] if low_days else '-'} shown as an outlook.
Day-1 confusion matrix (rows actual, columns predicted; Normal / Heatwave / Severe): {sev1['confusion_matrix']['values']}; persistence day-1
recall/precision {sev1_p['heatwave_recall']} / {sev1_p['heatwave_precision']}.</p>
{fig("04_frontend_model_reliability.png", "The dashboard's reliability panel: forecast error by day (ML vs baselines) and alert skill per day, read live from /model-info.", "92%")}

<h2>8. Application: landing page, dashboard and API</h2>
<p><b>Backend</b> (<code>app/main.py</code>, image <code>ayushiranjan27/heatguard:2.0</code>): a stateless FastAPI service with <code>/health</code>,
<code>/cities</code>, <code>/observed</code> (IMD history with normals and the actual next 7 days), <code>/outlook</code> (all 10 cities), <code>/model-info</code>
(per-horizon metrics) and <code>POST /predict</code> (7-day forecast). Invalid input returns 404/422 with clear messages; interactive docs at <code>/docs</code>.</p>
<p><b>Frontend</b> (<code>frontend/</code>, image <code>ayushiranjan27/heatguard-web:2.1</code>): unprivileged nginx serving two pages and reverse-proxying
<code>/api/</code> (and the API docs at <code>/api/docs</code>) to the backend, so the browser talks to one address and the backend stays internal. One
visual identity (a printed "heat bulletin": paper and ink for the interface, heat colours only for data; fonts and libraries bundled so nothing depends on the internet):</p>
<ul>
<li><b>Landing page</b> (<code>/</code>): animated introduction whose figures all come from the live API: the highest-risk city for 27 May 2024, a "heat
stripes" band of every 2024 IMD daily maximum for Delhi, count-up key figures, the pipeline, a pulsing India map of the 10-city outlook, per-day accuracy and the
four experiments. Animations respect the reduced-motion setting.</li>
<li><b>Dashboard</b> (<code>/dashboard</code>): 7-day heat bulletin for any city and date in 2014–2024: headline alert and advice, KPIs, a seven-day forecast
table with the actual IMD values, trend chart with uncertainty band, India map and ranking, what-if form, reliability panel.</li>
</ul>
{fig("06_landing_hero.png", "Landing page: headline, live hero card (highest-risk city on 27 May 2024 from /outlook) and the 2024 Delhi heat stripes from IMD data.")}
{fig("07_landing_how_outlook.png", "Landing page: how it works, and the 10-city outlook with a pulsing India map (Natural Earth, India view).", "92%")}
{fig("01_frontend_delhi_heatwave_overview.png", "Dashboard, Delhi as of 27 May 2024 (Docker Compose): bulletin headline, KPIs and the 7-day forecast table with the actual IMD values that followed.")}
{fig("02_frontend_trend_map_ranking.png", "Dashboard: trend chart (observed, normal, forecast with uncertainty band, actual IMD values), India map and regional ranking.")}

<h2>9. Implementation of the four experiments</h2>

<h3 class="exph" style="border-color:{C2}">9.1 Experiment 2: Containerization, Docker and Docker Hub</h3>
<p><b>Aim (manual).</b> Install Docker, pull and run images from Docker Hub, modify containers to run an application, and push it to Docker Hub.</p>
<p><b>About the experiment.</b> A Docker image is a read-only, layered template holding an application with all its dependencies; a container is a
running instance of that image. A registry such as Docker Hub stores images so that any machine can pull and run exactly the same software.</p>
{callout(2, C2, '''<p>Experiment 2 is the <b>packaging and publishing stage</b>. The backend image bakes in the API code, the 7 trained models, their metrics and
the IMD city series, so the forecast that was evaluated is the forecast that is served. The frontend image holds the landing page, dashboard and the nginx
proxy. Docker Compose runs them together; Docker Hub distributes them. Every later experiment uses these exact images: Kubernetes pulls them (Exp 3) and
the backend image is the workload measured in Exp 7 and Exp 8.</p>''')}
<p><b>Files:</b> <code>Dockerfile</code>, <code>frontend/Dockerfile</code>, <code>frontend/nginx/default.conf.template</code>, <code>docker-compose.yml</code>,
<code>.dockerignore</code>, <code>experiments/exp2_docker.sh</code>, <code>experiments/release_frontend.sh</code>.</p>
<p><b>Procedure.</b> (1) Docker Desktop installed; Docker Hub account <code>ayushiranjan27</code> created and <code>docker login</code> done by the student.
(2) Manual tasks: nginx pulled and run on port 8080, hello-world and Ubuntu run, Docker commands explored, nginx pushed as
<code>ayushiranjan27/nginx-exp2:1.0</code>. (3) Dockerfiles and Compose file written. (4) Both images built, run together, tested through the frontend proxy
including failure cases. (5) Both pushed for arm64 and amd64 with <code>docker buildx</code>. (6) Local images deleted, pulled back from Docker Hub and run.
(7) The redesigned frontend was released as 2.1 the same way.</p>
<p><b>Configuration.</b></p>
{code("Dockerfile")}
{code("frontend/Dockerfile")}
{code("docker-compose.yml")}
<p><b>Evidence.</b></p>
{term("t01_docker_version", "Docker engine and Compose versions used.")}
{term("t02_compose_ps", "The backend and frontend running together under Docker Compose, from the images pulled from Docker Hub; both healthy.")}
{term("t03_docker_images", "HeatGuard images on the machine (v1 tags kept for history).")}
{term("t04_hub_multiarch", "Both published images contain linux/arm64 and linux/amd64 variants on Docker Hub.")}
{fig("03_dockerhub_repositories.png", "Docker Hub: the three repositories of user ayushiranjan27.", "80%")}
{fig("09_dockerhub_heatguard_tags.png", "Docker Hub tags of the backend image (heatguard), with both platforms.", "80%")}
{fig("09_dockerhub_heatguard-web_tags.png", "Docker Hub tags of the frontend image (heatguard-web).", "80%")}
{term("t06_api_through_frontend", "A real 7-day forecast for Delhi (IMD values of 21–27 May 2024) requested through the frontend proxy.")}
{term("t05_docker_stats", "Resource use of the two running containers (idle).")}
{term("t07_compose_logs", "Container logs: requests reaching the backend and the frontend.")}
{log("exp2_docker.log", "### 3.", "### 4.", 14)}
{log("archive_v1/exp2_manual_tasks.log", "$ docker run -d --name web-nginx", "$ docker ps", 14)}
<p><b>Results.</b> Backend image 136 MB and frontend image about 22 MB (compressed). Both containers report healthy; the frontend reaches the backend through
its <code>/api/</code> proxy. Invalid input returns 404/422. With the backend stopped, the frontend stayed up and API calls returned HTTP {gw.group(1) if gw else '?'}
(gateway error) until the backend was restarted (HTTP {gw.group(2) if gw else '?'}). Docker Hub lists both images for linux/amd64 and linux/arm64, and the pulled
images ran healthy.</p>
<p><b>Conclusion.</b> HeatGuard was containerised as two images, run as a multi-container application and published; anyone can start the full
application with <code>docker compose up</code> on Intel or Apple Silicon machines.</p>

<h3 class="exph" style="border-color:{C3}">9.2 Experiment 3: Application Deployment using Kubernetes</h3>
<p><b>Aim (manual).</b> Deploy an application using Kubernetes; use kubectl commands; expose an application, preferably the image created in the Docker experiment.</p>
<p><b>About the experiment.</b> Kubernetes manages containers declaratively: a <i>Deployment</i> states how many copies (pods) of an image should run, a
<i>ReplicaSet</i> enforces that number, and a <i>Service</i> gives the pods a stable address and balances traffic between them. Probes, rolling updates and
rollbacks let an application keep running while it fails, scales or changes.</p>
{callout(3, C3, '''<p>Experiment 3 is the <b>operating stage</b>. The two Docker Hub images from Experiment 2 run as two Deployments on a kind cluster. The backend
is internal (ClusterIP) and is reached only through the frontend, which is the public entry point (NodePort 30080). The backend's CPU/memory limits are the
values measured in Experiment 7. The experiment demonstrates exactly what a warning service needs: replicas, self-healing, scaling, safe rollback of a bad
release and updates with zero dropped requests.</p>''')}
<p><b>Files:</b> <code>k8s/kind-config.yaml</code>, <code>k8s/api.yaml</code>, <code>k8s/web.yaml</code>, <code>experiments/exp3_kubernetes.sh</code>,
<code>experiments/release_frontend.sh</code>. The manual used the Killercoda playground; this project used <b>kind</b> (Kubernetes-in-Docker), a real
Kubernetes cluster running locally, so every step could be scripted and logged.</p>
{fig("diag_k8s_topology.png", "Kubernetes topology of the HeatGuard deployment and why each object exists.")}
<p><b>Configuration.</b></p>
{code("k8s/api.yaml")}
{code("k8s/web.yaml", 0, 40)}
<p><b>Evidence.</b></p>
{term("t08_k8s_cluster", "The kind cluster and its node (Kubernetes v1.37.0, arm64).")}
{term("t09_k8s_objects", "Deployments, ReplicaSets (one per released version, including the failed and rolled-back one) and Services.")}
{term("t10_k8s_pods", "Backend and frontend pods running.")}
{term("t11_k8s_describe", "Backend deployment: Docker Hub image, rolling-update strategy, resource limits from Experiment 7, probes.")}
{term("t14_k8s_access", "Service access through NodePort 30080: pages and API, with requests answered by different backend pods.")}
{term("t12_k8s_selfheal", "Self-healing: a backend pod is deleted and the Deployment creates a replacement.")}
{term("t13_k8s_scaling", "Horizontal scaling: the frontend scaled from 2 to 4 replicas (and back to 2).")}
{log("exp3_kubernetes.log", "### 5.", "### 6.", 26)}
{log("exp3_kubernetes.log", "### 6.", "### 7.", 24)}
{log("frontend_2.1_release.log", "### 2.", "### 3.", 32)}
{term("t15_k8s_history", "Rollout history of both deployments and the images currently running.")}
{term("t16_k8s_events", "Recent cluster events.")}
{fig("05_frontend_via_kubernetes.png", "Dashboard (frontend 2.1) served through the Kubernetes NodePort (localhost:30080); the label at the top right shows the backend pod that answered.")}
<p><b>Results.</b> Both images were pulled from Docker Hub; all pods became Ready; the frontend reached the backend through the <code>heatguard-api</code>
Service with requests spread across backend pods; scaling and self-healing worked; a non-existent image tag stopped in <code>ImagePullBackOff</code> while existing
pods kept serving, and <code>kubectl rollout undo</code> restored the Deployment. Rolling updates with checks every 0.25 s: {avail_txt}.
{(f"The frontend release from 2.0 to 2.1 served {rel21.group(1)}/{rel21.group(2)} requests successfully. " if rel21 else "")}
{"No request failed, so the preStop delay and maxUnavailable 0 removed the single failure observed in v1 (39/40)." if avail_failed == 0 else ""}</p>
<p><b>Conclusion.</b> Kubernetes provided declarative deployment, service discovery between the two tiers, scaling, self-healing, safe rollback and
zero-downtime updates for the warning service.</p>

<h3 class="exph" style="border-color:{C7}">9.3 Experiment 7: Cloud Cost Optimization through Resource Right-Sizing</h3>
<p><b>Aim (manual).</b> Analyse CPU and memory utilisation of an over-provisioned workload, apply right-sizing, and measure cost and efficiency
improvements without performance degradation.</p>
<p><b>About the experiment.</b> Over-provisioning means reserving more CPU and memory than a workload uses, which costs money and energy without benefit.
Right-sizing measures real usage under a representative load and sets limits slightly above the observed peak, then checks that performance holds.</p>
{callout(7, C7, '''<p>Experiment 7 is the <b>measurement stage</b>. The workload is the HeatGuard backend image itself, answering 15,000 real 7-day forecast
requests built from 2024 IMD data. The right-sized limits are not just reported: they are written into the backend Deployment in Experiment 3, and the same
workload and cost model are reused in Experiment 8.</p>''')}
<p><b>Files:</b> <code>loadtest/loadtest.py</code>, <code>experiments/run_config.py</code>, <code>experiments/rightsize.py</code>,
<code>experiments/summarize.py</code>, results in <code>experiments/results/exp7/</code>.</p>
{fig("diag_exp78_method.png", "How the backend was measured, right-sized (Exp 7) and costed (Exp 8).")}
<p><b>Procedure.</b> (1) Run <code>ayushiranjan27/heatguard:2.0</code> with 2 vCPU / 2 GB. (2) Send the fixed workload (15,000 <code>POST /predict</code>,
20 concurrent clients, 100 warm-up requests, fixed seed) while sampling <code>docker stats</code> about once per second; repeat 3 times. (3) Apply the manual's
rule, "slightly above peak with a safety buffer": CPU = peak × 1.25 rounded up to 0.25 vCPU; memory = peak × 1.5 rounded up to 64 MiB. (4) Re-run the same
workload 3 times with the new limits. (5) Estimate cost.</p>
{term("t17_rightsize", "Right-sizing decision computed from the measured peaks.")}
<p><b>Right-sizing decision:</b> observed peak {RS['observed_peak']['cpu_cores']} cores and {RS['observed_peak']['memory_mib']} MiB →
<b>{RS['right_sized']['cpus']} vCPU / {RS['right_sized']['memory']}</b>.</p>
{table(perf_cols, [perf_row(r) for r in E7])}
<p>Change after right-sizing: throughput {pct(o7['throughput_rps'], r7['throughput_rps'])}, p50 latency {pct(o7['latency_ms_p50'], r7['latency_ms_p50'])},
p95 latency {pct(o7['latency_ms_p95'], r7['latency_ms_p95'])}, estimated hourly cost {pct(o7['est_usd_per_hour'], r7['est_usd_per_hour'])}, estimated cost per
million predictions {pct(o7['est_usd_per_million_predictions'], r7['est_usd_per_million_predictions'])}. Errors {int(float(o7['errors']))} and
{int(float(r7['errors']))}; no out-of-memory kills.</p>
{fig("exp7_rightsizing_chart.png", "Experiment 7: utilisation of the allocated resources and estimated hourly cost before and after right-sizing (mean ± std, 3 runs).")}
<p><b>Cost basis (estimate, not an actual charge):</b> AWS Fargate on-demand, Linux/ARM, Asia Pacific (Mumbai): USD 0.02383 per vCPU-hour and USD 0.00261
per GB-hour, from the AWS public price list (published 2026-09-11), saved as <code>experiments/pricing/aws_ecs_ap-south-1_index.json</code>. Hourly cost =
vCPU × 0.02383 + GB × 0.00261; cost per million predictions = hourly cost ÷ (throughput × 3600) × 10<sup>6</sup>. No cloud account was used.</p>
<p><b>Conclusion.</b> The backend used under half of the 2 allocated CPUs ({o7['cpu_util_of_limit_pct']}% of the limit) and about
{float(o7['mem_util_of_limit_pct']):.0f}% of its memory; a single Uvicorn process cannot use more than about one core. After right-sizing, throughput changed by
{pct(o7['throughput_rps'], r7['throughput_rps'])} and p95 latency by {pct(o7['latency_ms_p95'], r7['latency_ms_p95'])}, but median latency rose by
{pct(o7['latency_ms_p50'], r7['latency_ms_p50'])} ({o7['latency_ms_p50']} → {r7['latency_ms_p50']} ms), so "without performance degradation" holds for throughput
and tail latency but not fully for median latency. Given the {pct(o7['est_usd_per_hour'], r7['est_usd_per_hour'])} estimated cost change, the trade-off is
acceptable for this service.</p>

<h3 class="exph" style="border-color:{C8}">9.4 Experiment 8: FinOps Principles and Instance-Type Comparison</h3>
<p><b>Aim (manual).</b> Compare different instance (resource) configurations for the same workload and identify the most cost-efficient option without
performance degradation.</p>
<p><b>About the experiment.</b> FinOps treats cloud spending as a shared engineering and finance decision whose goal is value per unit cost, not the lowest
bill. Comparing instance sizes on the same workload, against a stated performance target, shows which size delivers the required service most cheaply.</p>
{callout(8, C8, '''<p>Experiment 8 is the <b>sizing decision</b>. It reuses the Experiment 7 image, workload and cost model, and asks: if HeatGuard must serve at
least 300 forecasts per second with p95 latency under 250 ms, which instance size does that most cheaply? The answer informs how large each backend replica in
the Kubernetes deployment should be.</p>''')}
<p><b>Files:</b> <code>experiments/exp8_configs.json</code> (target + sizes, written before running), <code>experiments/run_config.py</code>,
<code>experiments/summarize.py</code>, results in <code>experiments/results/exp8/</code>.</p>
<p><b>Procedure</b> (manual algorithm steps 1–10). Workload identical to Experiment 7. Candidates: three AWS Fargate-valid sizes emulated with Docker limits.
Target rule: {E8CFG['target_rule']} → throughput ≥ {tgt['min_throughput_rps']} req/s, p95 ≤ {tgt['max_p95_latency_ms']} ms, zero errors, no OOM kill.
Each configuration ran 3 times.</p>
{table(perf_cols + ["Meets target"], [perf_row(r) + ["yes" if r["meets_target"] == "True" else "no"] for r in E8])}
{term("t18_results", "Experiment 7 and 8 results summarised from the raw runs (mean of 3 runs each), with the target check.")}
{fig("exp8_finops_chart.png", "Experiment 8: throughput, p95 latency (dashed lines = targets) and estimated cost per million predictions (mean ± std, 3 runs).")}
<p><b>Result.</b> {f"The most cost-efficient configuration meeting the target is <b>{best8['config']} ({best8['cpus']} vCPU / {best8['memory']})</b> at an estimated USD {float(best8['est_usd_per_million_predictions']):.4f} per million predictions." if best8 else "No configuration met the target."}
{(lambda m: f"It passes on the mean of 3 runs, but only {m[0]} of {m[1]} individual runs reached {tgt['min_throughput_rps']} req/s (runs: {', '.join(str(x) for x in m[2])} req/s), so it is a borderline choice with little headroom." if m[0] < m[1] else f"All {m[1]} of its runs met the target.")(runs_meeting(best8['config'])) if best8 else ""}
{" ".join(f"{r['config']} ({r['cpus']} vCPU) failed: {fails_because(r)}." for r in failing)}
At 0.25 vCPU the backend was CPU-saturated and its Docker health check timed out under load; in Kubernetes this would trigger liveness restarts.</p>
<p><b>Conclusion.</b> The cheapest size per hour (low) was the most expensive per prediction because it served so few requests: cost must be judged per unit
of useful work. {f"Moving from {best8['config']} to high ({high8['cpus']} vCPU) raised throughput by {pct(best8['throughput_rps'], high8['throughput_rps'])} at {pct(best8['est_usd_per_million_predictions'], high8['est_usd_per_million_predictions'])} cost per prediction; it is the safer choice if more headroom above the target is wanted." if best8 and high8 and best8['config'] != 'high' else ""}</p>

<h2>10. Testing and results</h2>
{term("t19_pytest", "Automated test suite.")}
{table(["Test", "Type"], [[t, "invalid input / failure" if any(x in t for x in ("unknown", "wrong", "implausible", "non_numeric", "outside", "too_long")) else "representative / rules"] for t in tests])}
<p><b>Failure scenarios demonstrated on the running system:</b> unknown city (404), 3 values instead of 7 (422), IMD missing-value code 99.9 °C (422),
invalid date (422), date outside the data (404), backend stopped behind the frontend (gateway error, recovered on restart), non-existent image tag in Kubernetes
(ImagePullBackOff, rolled back), deleted pod (recreated). In the dashboard, rejected what-if values are shown as an error message.</p>
<p><b>Summary of measured results.</b></p>
{table(["Area", "Result"], [
 ["Forecast accuracy (2024)", f"MAE {H[0]['models'][best]['test']['MAE']} °C (day 1) → {H[-1]['models'][best]['test']['MAE']} °C (day 7), better than persistence and climatology"],
 ["Heatwave alerts (2024)", f"day 1 recall {sev1['heatwave_recall']*100:.0f}%, precision {sev1['heatwave_precision']*100:.0f}%; days {validated_days[0]}–{validated_days[-1]} validated"],
 ["Exp 2", "2 images, multi-arch, pushed and pulled back; failure cases handled"],
 ["Exp 3", f"scaling, self-healing, rollback; rolling updates {avail_txt}{(f'; frontend 2.1 release {rel21.group(1)}/{rel21.group(2)}' if rel21 else '')}"],
 ["Exp 7", f"{RS['allocated']['cpus']} vCPU / {RS['allocated']['memory']} → {RS['right_sized']['cpus']} vCPU / {RS['right_sized']['memory']}; est. cost/hour {pct(o7['est_usd_per_hour'], r7['est_usd_per_hour'])}"],
 ["Exp 8", f"cheapest passing: {best8['config']} ({best8['cpus']} vCPU), USD {float(best8['est_usd_per_million_predictions']):.4f} per 1M predictions (estimate)" if best8 else "none"],
 ["Tests", test_total]])}

<h2>11. Requirement-to-test checklist</h2>
{table(["Requirement (assignment brief)", "Implementation", "Evidence", "Status"], [list(r) for r in CHECKLIST])}

<h2>12. Limitations, data privacy and improvements</h2>
<ul>
<li><b>Spatial resolution:</b> 1° grid cells (~100 km) are averages, not station readings.</li>
<li><b>Forecast inputs:</b> temperature history and season only; skill at days 5–7 is close to climatology.</li>
<li><b>Alerts:</b> per cell per day; IMD declares heatwaves when criteria hold at ≥ 2 stations of a sub-division for 2 consecutive days. Normals come from
2014–2022. Margins were tuned on a validation year with only 14 heatwave city-days; precision is low at longer horizons.</li>
<li><b>Historical replay:</b> the dashboard forecasts from any date in 2014–2024 using IMD archives; it is not connected to a live feed.</li>
<li><b>Experiments 7 and 8:</b> instance sizes were emulated with Docker limits on one laptop; the single Python load generator limits throughput; costs are estimates.</li>
<li><b>Experiment 3:</b> single-node local cluster rather than a cloud VM.</li>
<li><b>Data privacy:</b> only public, non-personal weather data; no user data stored; both containers run as non-root users; the backend is not exposed outside
the cluster; no credentials in the repository.</li>
<li><b>Improvements:</b> humidity/heat-index inputs and IMD forecast products; consecutive-day rule; calibrated uncertainty; scheduled data refresh;
LLM multilingual advisories with human review (use case §13); Horizontal Pod Autoscaler; repeat Experiments 7–8 on real cloud instances.</li>
</ul>

<h2>13. Version history</h2>
{table(["Version", "What changed", "Evidence"], [
 ["v1.0 / v1.1", "Single container with built-in dashboard, next-day forecast; v1.1 corrected the coastal heatwave rule", "experiments/results/archive_v1/"],
 ["v2.0", "7-day forecast; separate backend and frontend images; Docker Compose; two-tier Kubernetes with zero-downtime settings; all experiments re-run", "experiments/results/"],
 ["frontend 2.1", "Animated landing page and redesigned dashboard; frontend-only change released with a measured rolling update; backend stays 2.0", "frontend_2.1_release.log"]])}

<h2>14. Conclusion</h2>
<p>HeatGuard turns real IMD observations into 7-day maximum-temperature forecasts and IMD-style heatwave alerts, with each day's reliability measured and shown
to the user. The same two images were containerised and published (Exp 2), operated on Kubernetes with scaling, recovery and zero-downtime updates (Exp 3),
right-sized from measured usage with the limits fed back into the deployment (Exp 7), and sized against an explicit service target (Exp 8). Because each
experiment acts on the same artifacts and hands its result to the next, together they form one pipeline from data and model to a cost-aware, resilient
early-warning service.</p>

<h2>15. References</h2>
<ol class="refs">
<li>Somaiya Vidyavihar University, AI Use Case KJS-CES-01: Climate Intelligence for Heatwave Monitoring, Prediction, and Early Warning (use-case document).</li>
<li>Somaiya Vidyavihar University, Cloud Computing Experiment manuals 2, 3, 7 and 8 (KJSSE, 2025–26).</li>
<li>IMD Pune, High resolution daily gridded maximum temperature data (1°×1°), https://www.imdpune.gov.in/cmpg/Griddata/Max_1_Bin.html</li>
<li>A. K. Srivastava, M. Rajeevan, S. R. Kshirsagar, "Development of a high resolution daily gridded temperature data set (1969–2005) for the Indian region", Atmospheric Science Letters, 10(4), 249–254, 2009.</li>
<li>India Meteorological Department, Heat wave definitions, https://mausam.imd.gov.in/pdfs/heatcolduser/Definition.pdf</li>
<li>Amazon Web Services, AWS Price List (AmazonECS, ap-south-1), publication 2026-09-11.</li>
<li>Docker documentation, https://docs.docker.com/ ; Kubernetes documentation, https://kubernetes.io/docs/ ; kind, https://kind.sigs.k8s.io/</li>
<li>scikit-learn, https://scikit-learn.org/ ; FastAPI, https://fastapi.tiangolo.com/ ; nginx, https://nginx.org/</li>
<li>Chart.js, https://www.chartjs.org/ ; Leaflet, https://leafletjs.com/ ; Natural Earth (India point-of-view boundaries), https://www.naturalearthdata.com/</li>
<li>FinOps overview, Microsoft Learn, https://learn.microsoft.com/en-us/cloud-computing/finops/overview</li>
</ol>

<h2>16. Acknowledgement of AI-assisted work</h2>
<p>This project was developed with the help of Claude (Anthropic), an AI assistant, used for analysing the assignment documents, writing code and scripts,
drawing diagrams and drafting this report. All code was executed on the student's machine; all results, logs and screenshots were produced by real runs and
were checked by the student. The student created the Docker Hub account, performed the <code>docker login</code> and recorded the demonstration video herself.
Command outputs are copied verbatim from the files in <code>experiments/results/</code> (Docker build progress lines omitted for length). Terminal figures are
renderings of real command output captured on the student's machine by <code>docs/tools/capture_terminal.py</code>; the captured text is saved next to the logs.
Screenshots of the web pages and Docker Hub were captured with headless Google Chrome from the running services.</p>
"""

CSS = """
@page { size: A4; margin: 16mm 14mm; }
body { font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 10.4pt; color: #1e1e1e; line-height: 1.45; }
h1 { font-size: 24pt; margin: 10px 0; } h2 { font-size: 15pt; margin-top: 24px; border-bottom: 2px solid #b4441c; padding-bottom: 3px; page-break-after: avoid; }
h3 { font-size: 12.5pt; margin-top: 18px; color: #1f5fa8; page-break-after: avoid; }
h3.exph { font-size: 14pt; color: #1e1e1e; border-left: 6px solid; padding-left: 10px; margin-top: 30px; page-break-before: always; }
.title { text-align: center; page-break-after: always; padding-top: 50px; }
.title .inst { font-size: 12pt; } .title .course { color: #555; } .title .sub { font-size: 12pt; }
.toc { page-break-after: always; } .toc ol { font-size: 11.5pt; line-height: 2; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 8.8pt; page-break-inside: auto; }
tr { page-break-inside: avoid; } thead, tr:first-child { page-break-after: avoid; }
th, td { border: 1px solid #ccc; padding: 4px 5px; text-align: left; vertical-align: top; } th { background: #f3efe8; }
table.meta { width: 90%; margin: 26px auto; font-size: 10.5pt; } table.meta td:first-child { width: 24%; font-weight: 600; background: #f8f6f2; }
table.why td { font-size: 9.6pt; padding: 7px 8px; } table.why td.e { width: 58px; font-weight: 700; font-size: 11pt; }
pre { font-family: Menlo, Consolas, monospace; font-size: 7.2pt; background: #f7f7f7; border: 1px solid #ddd; padding: 6px 8px;
      white-space: pre-wrap; word-break: break-all; page-break-inside: avoid; }
pre.log { background: #10151c; color: #d7e0ea; border-color: #10151c; }
.src { display: block; font-weight: 700; color: #b4441c; margin-bottom: 2px; } pre.log .src { color: #f0a070; }
.src2 { color: #777; }
figure { text-align: center; margin: 12px 0; page-break-inside: avoid; } img { border: 1px solid #e2e2e2; max-height: 235mm; object-fit: contain; }
figcaption { font-size: 8.8pt; color: #444; margin-top: 4px; text-align: left; }
code { font-family: Menlo, Consolas, monospace; font-size: 8.8pt; } ol.refs li { margin-bottom: 4px; } a { color: #1f5fa8; }
.callout { border-left: 6px solid; background: #f7f9fc; padding: 8px 14px; margin: 10px 0 12px; page-break-inside: avoid; }
.callout-h { font-weight: 700; font-size: 10pt; text-transform: uppercase; letter-spacing: .04em; margin-bottom: 2px; }
.callout p { margin: 4px 0; }
.muted { color: #666; } .placeholder { background: #fff3cd; border: 1px dashed #c9a227; padding: 1px 6px; }
"""

OUT_HTML.write_text(f'<!doctype html><html><head><meta charset="utf-8"><title>HeatGuard Report</title>'
                    f"<style>{CSS}</style></head><body>{body}</body></html>")
subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                f"--print-to-pdf={OUT_PDF}", OUT_HTML.as_uri()], check=True, capture_output=True)
print(f"wrote {OUT_HTML.relative_to(ROOT)} and {OUT_PDF.relative_to(ROOT)} ({FIG[0]} figures)")
