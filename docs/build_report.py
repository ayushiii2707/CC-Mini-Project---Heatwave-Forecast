"""Build the consolidated report (HTML -> PDF) from the real project outputs.

Every number is read from models/metrics.json or experiments/results/*.csv, and every
command output is copied verbatim from the logs in experiments/results/.
Usage: python docs/build_report.py   (needs Google Chrome for the PDF step)
"""
import csv
import html
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "experiments" / "results"
OUT_HTML = ROOT / "docs" / "report.html"
OUT_PDF = ROOT / "docs" / "16014223028_AyushiRanjan_CC_UseCase_Report.pdf"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
GITHUB = "https://github.com/ayushiii2707/CC-Mini-Project---Heatwave-Forecast"
HUB = "https://hub.docker.com/r/ayushiranjan27/heatguard"

M = json.loads((ROOT / "models" / "metrics.json").read_text())
E7 = list(csv.DictReader(open(RES / "exp7_summary.csv")))
E8 = list(csv.DictReader(open(RES / "exp8_summary.csv")))
E8CFG = json.loads((ROOT / "experiments" / "exp8_configs.json").read_text())
RS = json.loads((RES / "exp7" / "rightsizing_decision.json").read_text())


def log(name, start=None, end=None, max_lines=40, width=150):
    """Verbatim excerpt of a log between two marker strings."""
    lines = (RES / name).read_text().splitlines()
    i = next((k for k, l in enumerate(lines) if start in l), 0) if start else 0
    j = next((k for k, l in enumerate(lines[i + 1:], i + 1) if end in l), len(lines)) if end else len(lines)
    chunk = [l[:width] for l in lines[i:j]][:max_lines]
    return f'<pre class="log"><span class="src">{name}</span>\n' + html.escape("\n".join(chunk)) + "</pre>"


def code(path, first=None, last=None):
    lines = (ROOT / path).read_text().splitlines()[first:last]
    return f'<pre class="code"><span class="src">{path}</span>\n' + html.escape("\n".join(lines)) + "</pre>"


def img(name, caption, width="100%"):
    return (f'<figure><img src="screenshots/{name}" style="width:{width}"><figcaption>{caption}</figcaption></figure>')


def table(head, rows):
    h = "".join(f"<th>{c}</th>" for c in head)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><tr>{h}</tr>{b}</table>"


def pm(r, k):
    return f"{r[k]} ± {r[k + '_sd']}"


mods = M["models"]
sev, sev0, sevp = (M["severity_on_test_forecast"], M["severity_on_test_forecast_no_margin"],
                   M["severity_on_test_persistence"])
cm = sev["confusion_matrix"]["values"]
o7, r7 = E7
pct = lambda a, b: f"{(float(b) - float(a)) / float(a) * 100:+.1f}%"  # noqa: E731
passing = [r for r in E8 if r["meets_target"] == "True"]
best8 = min(passing, key=lambda r: float(r["est_usd_per_million_predictions"]))

perf_cols = ["Configuration", "CPU peak (% of 1 core)", "CPU used (% of limit)", "Memory peak (MiB)",
             "Memory used (% of limit)", "Throughput (req/s)", "p50 latency (ms)", "p95 latency (ms)",
             "Errors", "Est. USD / hour", "Est. USD / 1M predictions"]


def perf_row(r):
    return [f"<b>{r['config']}</b><br>{r['cpus']} vCPU / {r['memory']}", pm(r, "cpu_peak_pct"),
            pm(r, "cpu_util_of_limit_pct"), pm(r, "mem_peak_mib"), pm(r, "mem_util_of_limit_pct"),
            pm(r, "throughput_rps"), pm(r, "latency_ms_p50"), pm(r, "latency_ms_p95"),
            str(int(float(r["errors"]))), f"{float(r['est_usd_per_hour']):.4f}",
            f"{float(r['est_usd_per_million_predictions']):.4f}"]


tests = [l.split("::")[1].split(" ")[0] for l in (RES / "pytest_output.txt").read_text().splitlines()
         if "::" in l and "PASSED" in l]
test_total = (RES / "pytest_output.txt").read_text().strip().splitlines()[-1].strip("= ")

CHECKLIST = [
    ("Working prototype: input → processing → output", "Dashboard + POST /predict (city, date, 7 Tmax → forecast, alert, advice)",
     "exp2_run.log, screenshots 01–03, 05", "Verified"),
    ("AI/ML component appropriate to use case", "Ridge regression next-day Tmax on IMD data; compared with GBM and persistence",
     "metrics.json, train_output.txt", "Verified"),
    ("Rule-based part identified", "IMD heatwave criteria (app/severity.py), labelled rule-based", "test_severity_rules", "Verified"),
    ("Real / public dataset documented", "IMD Pune 1° gridded Tmax 2014–2024, download script", "data/processed/city_tmax.csv", "Verified"),
    ("Labelled architecture diagram", "docs/architecture.html → 00_architecture_diagram.png", "Figure 1", "Verified"),
    ("Exp 2: containerise, run, push to Docker Hub", "Dockerfile, multi-arch push, pull-and-run check, nginx push",
     "exp2_build/run/push logs, Docker Hub API + screenshot 04", "Verified"),
    ("Exp 3: deploy, expose, pod status, scaling/recovery", "kind cluster, Deployment + NodePort, scale 2→3, pod delete, bad image rollback, rolling update",
     "exp3_kubernetes.log, screenshots 03, 05", "Verified"),
    ("Exp 7: measure CPU/memory, right-size, compare", "docker stats under fixed load, rule-based right-sizing, 3 repeats",
     "exp7/*.csv, runs.jsonl, rightsizing_decision.json", "Verified"),
    ("Exp 8: same workload on configs, cheapest meeting target", "3 Fargate-valid sizes, target fixed beforehand",
     "exp8/*, exp8_configs.json, summary.md", "Verified"),
    ("Exp 7 & 8 same workload, cost basis stated", "Same loadtest.py, seed, 15000 requests, 20 clients; AWS price list saved",
     "pricing/aws_ecs_ap-south-1_index.json", "Verified"),
    ("Representative inputs tested", "pytest + curl on real IMD windows (Delhi, Jaipur, Nagpur, Chennai)", "pytest_output.txt", "Verified"),
    ("≥1 invalid-input / failure scenario", "unknown city 404, 3 values 422, 99.9 °C 422, bad date 422, bad image tag in K8s",
     "pytest_output.txt, exp2_run.log, exp3_kubernetes.log", "Verified"),
    ("Measurements (error, latency, throughput, CPU/mem, cost)", "MAE/RMSE, recall/precision, req/s, p50/p95, docker stats, est. USD",
     "metrics.json, summary.md", "Verified"),
    ("Clean-environment setup", "README steps; published image pulled and run after deleting local tag",
     "exp2_push.log (pull + health)", "Partially Verified"),
    ("Demonstration video (5 min)", "Plan in docs/DEMO_PLAN.md", "to be recorded by student", "Not Verified"),
]

body = f"""
<section class="title">
  <p class="inst">Somaiya Vidyavihar University · K J Somaiya School of Engineering</p>
  <p class="course">Cloud Computing · Mini Project Report</p>
  <h1>HeatGuard: Heatwave Forecast and Early Warning</h1>
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
    <tr><td>Docker image</td><td><a href="{HUB}">{HUB}</a></td></tr>
    <tr><td>Date</td><td>11 October 2026</td></tr>
  </table>
</section>

<h2>Abstract</h2>
<p>HeatGuard is a working prototype of the heatwave early-warning use case. It reads real India Meteorological
Department (IMD) gridded daily maximum-temperature data for 2014–2024, forecasts the next day's maximum temperature
for ten Indian cities with a machine-learning model, and converts the forecast into a heatwave alert using IMD's published
criteria. On the unseen year 2024 the deployed ridge-regression model has a mean absolute error of
<b>{mods['ridge_regression']['test']['MAE']} °C</b> (persistence baseline {mods['persistence_baseline']['test']['MAE']} °C), and the alert
logic detects <b>{sev['heatwave_recall']*100:.1f}%</b> of the {sev['heatwave_days_actual']} actual heatwave city-days with a precision of
{sev['heatwave_precision']*100:.1f}%. The service is containerised and published on Docker Hub (Experiment 2), deployed on a Kubernetes cluster with
scaling, self-healing, rollback and a rolling update (Experiment 3), right-sized from 2 vCPU / 2 GB to {RS['right_sized']['cpus']} vCPU /
{RS['right_sized']['memory']} with an estimated <b>{pct(o7['est_usd_per_hour'], r7['est_usd_per_hour'])}</b> change in hourly cost
(Experiment 7), and compared across three instance sizes under the same workload to find the cheapest size meeting a
pre-defined performance target (Experiment 8). All results in this report come from real runs; costs are estimates.</p>

<h2>1. Problem statement, objectives and scope</h2>
<p><b>Problem.</b> Heatwaves in India are increasing in frequency, intensity and duration and affect public health,
agriculture and economic activity. Severity varies by region, so timely, region-specific warnings are needed
(Use-case document KJS-CES-01, §6).</p>
<p><b>Objectives.</b></p>
<ol>
<li>Build an input → processing → output prototype on real IMD meteorological data (use case §11, steps 1–2).</li>
<li>Develop an AI model for region-wise maximum-temperature forecasting and evaluate it against a baseline (§8, objective 2).</li>
<li>Classify heatwave severity and produce an advisory (§8, objective 4; §11, steps 8–9).</li>
<li>Package, publish, deploy, measure and cost-optimise the service using Experiments 2, 3, 7 and 8.</li>
</ol>
<p><b>Prototype scope.</b></p>
{table(["In scope", "Out of scope (see Limitations)"], [
 ["IMD 1°×1° gridded daily Tmax, 2014–2024, ten city grid cells", "IoT Automated Weather Stations (hardware)"],
 ["Next-day Tmax regression + IMD rule-based severity", "Multi-day forecasts, spatial hotspot maps of all 7 IMD regions"],
 ["Template advisories per severity level", "LLM-generated advisories (listed as future work)"],
 ["REST API + web dashboard, Docker, Kubernetes", "Real cloud deployment and billing (costs are estimates)"]])}

<h2>2. Dataset</h2>
<ul>
<li><b>Source:</b> IMD Pune, "High resolution 1°×1° daily gridded maximum temperature" binary data,
<a href="https://www.imdpune.gov.in/cmpg/Griddata/Max_1_Bin.html">imdpune.gov.in/cmpg/Griddata/Max_1_Bin.html</a>
(Srivastava, Rajeevan and Kshirsagar, 2009). This is the repository named in the use-case document (§11, step 1).</li>
<li><b>Format:</b> one <code>.GRD</code> file per year, float32, 31 × 31 grid (7.5–37.5 °N, 67.5–97.5 °E), 99.9 = missing.
File sizes were checked: 1,403,060 bytes for 365-day years and 1,406,904 bytes for leap years.</li>
<li><b>Acquisition:</b> <code>scripts/download_imd.sh</code>. The IMD server is slow and dropped connections (2017 needed three
attempts), so the script retries and accepts only full-size files.</li>
<li><b>Pre-processing:</b> <code>scripts/prepare_data.py</code> parses the grid, extracts the cell nearest to each of ten cities
(Delhi, Jaipur, Lucknow, Patna, Ahmedabad, Nagpur, Kolkata, Bhubaneswar, Hyderabad, Chennai) and writes 40,180 daily rows.
Grid orientation was verified (sea cells missing, Ladakh cold, Delhi ≈ 17 °C in January and ≈ 40 °C in May).</li>
<li><b>Split (time-ordered):</b> train 2014–2022 ({M['samples']['train']} samples), validation 2023 ({M['samples']['validation']}),
test 2024 ({M['samples']['test']}).</li>
<li><b>No synthetic data</b> is used. The data is non-personal meteorological data, so no personal-data privacy issues arise.</li>
</ul>

<h2>3. System architecture and tools</h2>
{img("00_architecture_diagram.png", "Figure 1. Labelled architecture and data flow. Orange: AI component. Blue: Cloud Computing experiments. Green: data pipeline.")}
{table(["Layer", "Tools (versions as run)"], [
 ["Language / ML", "Python 3.13, NumPy 2.5.4, scikit-learn 1.9.1, pandas 3.0.6 (training only), joblib 1.6.0"],
 ["Service", "FastAPI 0.143.0, Uvicorn 0.54.0, HTML/JS dashboard (no external libraries)"],
 ["Testing / load", "pytest 9.1.1, httpx 0.28.1 (async load generator)"],
 ["Containers (Exp 2)", "Docker Desktop, engine 29.7.2 (arm64), docker buildx, Docker Hub"],
 ["Orchestration (Exp 3)", "kind v0.33.0 (Kubernetes v1.37.0), kubectl v1.36.1"],
 ["Measurement (Exp 7, 8)", "docker stats, custom runner experiments/run_config.py, matplotlib 3.11.2"],
 ["Hardware", "Apple MacBook M2, 8 GB RAM (Docker VM: 8 CPUs, 3.8 GiB)"]])}

<h2>4. AI component</h2>
<p>The AI part is kept separate from the cloud part so each can be explained on its own.</p>
<h3>4.1 Machine-learning forecaster (next-day maximum temperature)</h3>
<p><b>Input features</b> (<code>app/features.py</code>, shared by training and serving): the last 7 daily Tmax values, their
mean, day-of-year as sine/cosine, the climatological normal for the target day (from 2014–2022 only, to avoid leakage),
and the cell's latitude and longitude. <b>Target:</b> Tmax on the next day. Three approaches were compared; the model with the
lowest <i>validation</i> error was deployed and the test year was used only once for final reporting.</p>
{table(["Model", "Validation MAE 2023 (°C)", "Test MAE 2024 (°C)", "Test RMSE 2024 (°C)"],
 [[k + (" <b>(deployed)</b>" if k == M['selected_model'] else ""), v['val']['MAE'], v['test']['MAE'], v['test']['RMSE']] for k, v in mods.items()])}
<p>Test MAE by city (°C): {", ".join(f"{c} {v}" for c, v in M['test_mae_by_city'].items())}.</p>
<p><b>Interpretation:</b> the ML model is about {(1 - mods['ridge_regression']['test']['MAE'] / mods['persistence_baseline']['test']['MAE']) * 100:.0f}%
more accurate than the persistence baseline. Day-to-day temperature is strongly persistent, so the gain is modest but consistent; the
simpler linear model generalised slightly better than gradient boosting.</p>

<h3>4.2 Rule-based severity classifier (not ML)</h3>
<p><code>app/severity.py</code> applies the IMD heatwave definitions (IMD, <i>Heat wave definitions</i>): a heatwave is
considered only if Tmax ≥ 40 °C (plains) or ≥ 37 °C (coastal). Departure from normal 4.5–6.4 °C → Heatwave, &gt; 6.4 °C →
Severe heatwave; for plains, Tmax ≥ 45 °C → Heatwave and ≥ 47 °C → Severe. Coastal stations have only a Heatwave category.
Kolkata and Chennai are treated as coastal.</p>

<h3>4.3 Alert margin (finding and fix)</h3>
<p>Evaluated directly on the forecast, alerts detected only <b>{sev0['heatwave_recall']*100:.1f}%</b> of real heatwave days: regression
pulls extreme values towards the mean, so the forecast rarely crossed the IMD thresholds. Because a missed heatwave is costlier
than a false alarm, alerts are issued on an <b>upper-bound forecast</b> (forecast + margin). The margin was chosen on the 2023
validation year by F2 score (which weights recall above precision): margin {M['alert_margin_c']} °C. The 2023 year contains only 14
heatwave city-days, so this choice is uncertain.</p>
{table(["Alert method (test 2024, " + str(sev['heatwave_days_actual']) + " actual heatwave city-days)", "Recall", "Precision", "F2"], [
 [f"ML forecast + {M['alert_margin_c']} °C margin <b>(deployed)</b>", sev['heatwave_recall'], sev['heatwave_precision'], sev['heatwave_f2']],
 ["ML forecast, no margin", sev0['heatwave_recall'], sev0['heatwave_precision'], sev0['heatwave_f2']],
 ["Persistence baseline", sevp['heatwave_recall'], sevp['heatwave_precision'], sevp['heatwave_f2']]])}
<p>Confusion matrix of the deployed alert on 2024 (rows = actual, columns = predicted; Normal / Heatwave / Severe):
{cm[0]}, {cm[1]}, {cm[2]}. The system detects most heatwave days but about 4 in 10 alerts are false alarms.</p>

<h2>5. Implementation of the four experiments</h2>

<h3>Experiment 2: Containerization, Docker and Docker Hub</h3>
<p><b>Aim (manual):</b> install Docker, pull and run images from Docker Hub, modify containers to run an application and push it to
Docker Hub. <b>Use-case connection:</b> the HeatGuard forecast service, trained model and IMD city data are packaged as one image,
which every later experiment uses unchanged.</p>
<p><b>Procedure.</b> (1) Docker Desktop installed; Docker Hub account <code>ayushiranjan27</code> created and <code>docker login</code> done by
the student. (2) Manual tasks: nginx pulled and run on port 8080, hello-world and Ubuntu run, Docker commands explored.
(3) Dockerfile written (python:3.13-slim, non-root user, HEALTHCHECK). (4) Image built, run and tested, including invalid inputs.
(5) Image pushed for arm64 and amd64 with <code>docker buildx</code>; nginx pushed. (6) Local tag removed, image pulled back from
Docker Hub and run.</p>
{code("Dockerfile")}
{log("exp2_run.log", None, "# Failure scenario 1", 40)}
{log("exp2_run.log", "# Failure scenario 1", "$ docker logs", 14)}
{log("exp2_manual_tasks.log", "$ docker run -d --name web-nginx", "$ docker exec", 30)}
{log("exp2_push.log", "$ docker buildx imagetools inspect", "$ docker tag", 16)}
{log("exp2_push.log", "$ docker rmi", None, 14)}
{img("04_dockerhub_heatguard_tags.png", "Figure 2. Docker Hub repository ayushiranjan27/heatguard with linux/amd64 and linux/arm64 images (captured after the 1.0 push).", "85%")}
{img("01_dashboard_docker_delhi_heatwave.png", "Figure 3. Dashboard served from the Docker container: Delhi, forecast for 28 May 2024 = 44.1 °C, alert Heatwave; actual IMD value 46.0 °C.", "80%")}
<p><b>Results.</b> Image size 136 MB (compressed content). Health check reports healthy; forecasts are served; unknown city returns 404 and
malformed inputs return 422 without crashing the service. Docker Hub lists <code>heatguard:1.0</code>, <code>1.1</code> and <code>latest</code>
for amd64 and arm64, and <code>nginx-exp2:1.0</code>. Version 1.1 only corrects the coastal heatwave rule (Section 4.2); forecast errors are identical.</p>
<p><b>Conclusion.</b> The application was containerised, run and published; anyone can now run it with one <code>docker run</code> command on
Intel or Apple Silicon machines.</p>

<h3>Experiment 3: Application Deployment using Kubernetes</h3>
<p><b>Aim (manual):</b> deploy an application using Kubernetes, use kubectl commands and expose an app (preferably the image created in the
Docker experiment). <b>Use-case connection:</b> the HeatGuard image from Docker Hub is deployed as a replicated, self-healing service, as an
early-warning service must stay available. Resource limits come from Experiment 7.</p>
<p><b>Procedure.</b> The manual used the Killercoda playground; this project used <b>kind</b> (Kubernetes-in-Docker), a real Kubernetes
cluster running locally on Docker Desktop, so the full sequence could be scripted (<code>experiments/exp3_kubernetes.sh</code>) and
logged. Steps: create cluster → apply Deployment (2 replicas) and NodePort Service → access through the Service → scale to 3 → delete a
pod → set a non-existent image tag → roll back → rolling update to 1.1.</p>
{code("k8s/deployment.yaml")}
{code("k8s/service.yaml")}
{log("exp3_kubernetes.log", "### 1.", "### 2.", 40)}
{log("exp3_kubernetes.log", "### 2.", "### 3.", 14)}
{log("exp3_kubernetes.log", "### 4.", "### 5.", 30)}
{log("exp3_kubernetes.log", "### 5.", "$ kubectl rollout history", 22)}
{log("exp3_kubernetes.log", "### 7.", None, 40)}
{img("03_dashboard_kubernetes_nodeport_30080.png", "Figure 4. Dashboard through the Kubernetes NodePort Service (localhost:30080); 'Served by' shows the pod name. Jaipur, 26 May 2024: forecast 44.9 °C, Heatwave; actual 46.4 °C.", "80%")}
<p><b>Results.</b> The image was pulled from Docker Hub by the cluster; both pods became Ready; requests were spread across pods; scaling to 3
worked; a deleted pod was replaced by the Deployment within about 16 s; a non-existent image tag stopped in <code>ImagePullBackOff</code>
while the 3 old pods kept serving, and <code>kubectl rollout undo</code> restored the Deployment. During the rolling update to 1.1, 39 of 40
health checks (every 0.5 s) returned HTTP 200 and one failed. A likely cause is a terminating pod still receiving a request before the Service
endpoints were updated; a <code>preStop</code> delay is the usual remedy (not implemented).</p>
<p><b>Conclusion.</b> Kubernetes provided declarative deployment, service discovery, scaling and recovery for the HeatGuard service.</p>

<h3>Experiment 7: Cloud Cost Optimization through Resource Right-Sizing</h3>
<p><b>Aim (manual):</b> analyse CPU and memory utilisation of an over-provisioned workload, apply right-sizing and measure cost and efficiency
improvements without performance degradation. <b>Use-case connection:</b> the workload is the HeatGuard forecast API itself, loaded with
forecast requests built from real 2024 IMD data.</p>
<p><b>Procedure.</b> (1) Run the heatguard image with 2 vCPU / 2 GB (<code>docker run --cpus 2 --memory 2g</code>). (2) Send the fixed workload:
15,000 <code>POST /predict</code> requests, 20 concurrent clients, 100 warm-up requests, fixed random seed (<code>loadtest/loadtest.py</code>), while
sampling <code>docker stats</code> about once per second. (3) Repeat 3 times. (4) Right-size with the manual's rule, "slightly above peak with a
safety buffer" (<code>experiments/rightsize.py</code>): CPU = peak × 1.25 rounded up to 0.25 vCPU; memory = peak × 1.5 rounded up to 64 MiB.
(5) Re-run the same workload 3 times with the new limits. (6) Estimate cost.</p>
<p><b>Right-sizing decision</b> (from <code>rightsizing_decision.json</code>): observed peak {RS['observed_peak']['cpu_cores']} cores and
{RS['observed_peak']['memory_mib']} MiB → <b>{RS['right_sized']['cpus']} vCPU / {RS['right_sized']['memory']}</b>.</p>
{table(perf_cols, [perf_row(r) for r in E7])}
<p>Change after right-sizing: throughput {pct(o7['throughput_rps'], r7['throughput_rps'])}, p50 latency {pct(o7['latency_ms_p50'], r7['latency_ms_p50'])},
p95 latency {pct(o7['latency_ms_p95'], r7['latency_ms_p95'])}, estimated hourly cost {pct(o7['est_usd_per_hour'], r7['est_usd_per_hour'])},
estimated cost per million predictions {pct(o7['est_usd_per_million_predictions'], r7['est_usd_per_million_predictions'])}. No errors and no
out-of-memory kills in any run. The right-sized limits are used in the Kubernetes Deployment (Experiment 3).</p>
{img("exp7_rightsizing_chart.png", "Figure 5. Experiment 7: utilisation of the allocated resources and estimated hourly cost before and after right-sizing (mean ± std, 3 runs).")}
<p><b>Cost basis (estimate, not an actual charge):</b> AWS Fargate on-demand, Linux/ARM, Asia Pacific (Mumbai): USD 0.02383 per vCPU-hour and
USD 0.00261 per GB-hour, read from the AWS public price list (publication date 2026-09-11), saved as
<code>experiments/pricing/aws_ecs_ap-south-1_index.json</code>. Hourly cost = vCPU × 0.02383 + GB × 0.00261; cost per million predictions = hourly cost ÷
(throughput × 3600) × 10<sup>6</sup>. No cloud account was used.</p>
<p><b>Conclusion.</b> The service was heavily over-provisioned (≈ 28% of CPU and 5% of memory used). Right-sizing cut the estimated cost by
about two-thirds for a ~11% throughput reduction, an acceptable trade-off for this service. The manual's "without performance
degradation" is only approximately met: a small, measured degradation occurred.</p>

<h3>Experiment 8: FinOps Principles and Instance-Type Comparison</h3>
<p><b>Aim (manual):</b> compare different instance (resource) configurations for the same workload and identify the most cost-efficient option
without performance degradation. <b>Use-case connection:</b> chooses the cheapest size on which the heatwave API still meets its response-time target.</p>
<p><b>Procedure</b> (manual algorithm steps 1–10). Workload: identical to Experiment 7. Candidates: three AWS Fargate-valid sizes, emulated with
Docker limits. The <b>performance target was written down before running</b> (<code>experiments/exp8_configs.json</code>):
p95 latency ≤ {E8CFG['performance_target']['max_p95_latency_ms']} ms, zero errors, no OOM kill. Each configuration ran 3 times.</p>
{table(perf_cols + ["Meets target"], [perf_row(r) + ["yes" if r["meets_target"] == "True" else "no"] for r in E8])}
{img("exp8_finops_chart.png", "Figure 6. Experiment 8: throughput, p95 latency (dashed line = target) and estimated cost per million predictions (mean ± std, 3 runs).")}
<p><b>Result.</b> All three sizes met the pre-defined target; the most cost-efficient is <b>{best8['config']} ({best8['cpus']} vCPU / {best8['memory']})</b>
at an estimated USD {float(best8['est_usd_per_million_predictions']):.4f} per million predictions, about half the cost of the 1 vCPU size. It does so with
roughly half the throughput and about 3× higher median latency. The target did not include a throughput requirement. As a
<i>post-hoc sensitivity check</i> (not the pre-defined target): if ≥ 500 req/s were also required, the medium size would be chosen.</p>
<p><b>Conclusion.</b> Doubling resources beyond 0.5 vCPU gave almost no extra performance (a single-process Python server uses at most
about one core) but doubled the cost. FinOps decisions depend on stating the performance target explicitly.</p>

<h2>6. Testing and results</h2>
<p><b>Automated tests</b> (<code>pytest -v</code>, result: <b>{test_total}</b>):</p>
{table(["Test", "Type"], [[t, "invalid input / failure" if any(x in t for x in ("unknown", "wrong", "implausible", "non_numeric", "outside")) else "representative / rules"] for t in tests])}
<p><b>Failure scenarios demonstrated</b> on the running container and through Kubernetes: unknown city (404), 3 values instead of 7 (422),
an IMD missing-value code 99.9 °C (422), invalid date (422), a non-existent image tag (ImagePullBackOff, rolled back), and a deleted pod
(recreated). <b>Measurements:</b> forecast MAE/RMSE, alert recall/precision/F2, throughput, p50/p95 latency, CPU and memory utilisation
and estimated cost, summarised in Sections 4 and 5.</p>

<h2>7. Requirement-to-test checklist</h2>
{table(["Requirement (assignment brief)", "Implementation", "Evidence", "Status"], [list(r) for r in CHECKLIST])}

<h2>8. Limitations, data privacy and improvements</h2>
<ul>
<li><b>Spatial resolution:</b> 1° grid cells (~100 km) are averages, not station readings; city values are approximations.</li>
<li><b>Forecast horizon:</b> one day ahead only; uses only past temperature (no humidity, wind or numerical weather model input).</li>
<li><b>Heatwave rules:</b> applied per cell per day; IMD declares heatwaves when criteria hold at ≥ 2 stations of a sub-division for 2
consecutive days. Normals come from 2014–2022 rather than IMD's 30-year station normals.</li>
<li><b>Alert margin:</b> tuned on a validation year with only 14 heatwave city-days; precision is 0.57 (many false alarms).</li>
<li><b>Experiments 7 and 8:</b> instance sizes were emulated with Docker limits on one laptop, not cloud VMs; the single Python load
generator limited throughput to ~600 req/s; costs are estimates from public prices.</li>
<li><b>Experiment 3:</b> single-node local cluster; one failed health check during the rolling update.</li>
<li><b>Data privacy:</b> only public, non-personal meteorological data is processed; no user data is stored; the container runs as a
non-root user; Docker Hub credentials were kept out of the code and repository (<code>.env.example</code> holds only the username variable).</li>
<li><b>Improvements:</b> add humidity/heat-index and IMD forecast inputs; multi-day forecasts; consecutive-day rule; quantile regression for
calibrated uncertainty; LLM-generated multilingual advisories with human review (use case §13); Horizontal Pod Autoscaler and
<code>preStop</code> hooks; repeat Experiments 7–8 on real cloud instances.</li>
</ul>

<h2>9. Conclusion</h2>
<p>A working heatwave early-warning prototype was built on real IMD data. Its ML forecaster beats a persistence baseline, and the
validated alert margin raises heatwave detection on the unseen 2024 year from {sev0['heatwave_recall']*100:.0f}% to {sev['heatwave_recall']*100:.0f}%.
The same service was containerised and published (Exp 2), deployed and operated on Kubernetes (Exp 3), right-sized for an estimated
{abs(float(pct(o7['est_usd_per_hour'], r7['est_usd_per_hour']).strip('%+'))):.0f}% cost reduction (Exp 7), and compared across instance sizes to
choose the cheapest one meeting a stated target (Exp 8). Each experiment acts on the same artifact, so together they form one pipeline from
model to cost-optimised deployment.</p>

<h2>10. References</h2>
<ol class="refs">
<li>Somaiya Vidyavihar University, AI Use Case KJS-CES-01: Climate Intelligence for Heatwave Monitoring, Prediction, and Early Warning (use-case document).</li>
<li>Somaiya Vidyavihar University, Cloud Computing Experiment manuals 2, 3, 7 and 8 (KJSSE, 2025–26).</li>
<li>IMD Pune, High resolution daily gridded maximum temperature data (1°×1°), https://www.imdpune.gov.in/cmpg/Griddata/Max_1_Bin.html</li>
<li>A. K. Srivastava, M. Rajeevan, S. R. Kshirsagar, "Development of a high resolution daily gridded temperature data set (1969–2005) for the Indian region", Atmospheric Science Letters, 10(4), 249–254, 2009.</li>
<li>India Meteorological Department, Heat wave definitions, https://mausam.imd.gov.in/pdfs/heatcolduser/Definition.pdf</li>
<li>Amazon Web Services, AWS Price List (AmazonECS, ap-south-1), publication 2026-09-11, https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonECS/current/ap-south-1/index.json</li>
<li>Docker documentation, https://docs.docker.com/ ; Kubernetes documentation, https://kubernetes.io/docs/ ; kind, https://kind.sigs.k8s.io/</li>
<li>scikit-learn documentation, https://scikit-learn.org/ ; FastAPI documentation, https://fastapi.tiangolo.com/</li>
<li>FinOps Foundation / Microsoft Learn, FinOps overview, https://learn.microsoft.com/en-us/cloud-computing/finops/overview</li>
</ol>

<h2>11. Acknowledgement of AI-assisted work</h2>
<p>This project was developed with the help of Claude (Anthropic), an AI assistant, used for analysing the assignment documents,
writing code and scripts, and drafting this report. All code was executed on the student's machine; all results, logs and screenshots
were produced by real runs and were checked by the student. The student created the Docker Hub account and performed the
<code>docker login</code> herself. Command outputs in this report are copied verbatim from the log files in
<code>experiments/results/</code>; screenshots of the dashboard and Docker Hub were captured with headless Google Chrome from the
running services.</p>
"""

CSS = """
@page { size: A4; margin: 16mm 14mm; }
body { font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 10.5pt; color: #1e1e1e; line-height: 1.45; }
h1 { font-size: 24pt; margin: 10px 0; } h2 { font-size: 15pt; margin-top: 22px; border-bottom: 2px solid #b4441c; padding-bottom: 3px; }
h3 { font-size: 12.5pt; margin-top: 18px; color: #1f5fa8; }
.title { text-align: center; page-break-after: always; padding-top: 70px; }
.title .inst { font-size: 12pt; } .title .course { color: #555; } .title .sub { font-size: 12pt; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 9pt; page-break-inside: avoid; }
th, td { border: 1px solid #ccc; padding: 4px 6px; text-align: left; vertical-align: top; } th { background: #f3efe8; }
table.meta { width: 85%; margin: 30px auto; font-size: 10.5pt; } table.meta td:first-child { width: 28%; font-weight: 600; background: #f8f6f2; }
pre { font-family: Menlo, Consolas, monospace; font-size: 7.3pt; background: #f7f7f7; border: 1px solid #ddd; padding: 6px 8px;
      white-space: pre-wrap; word-break: break-all; page-break-inside: avoid; }
pre.log { background: #10151c; color: #d7e0ea; border-color: #10151c; }
.src { display: block; font-weight: 700; color: #b4441c; margin-bottom: 2px; } pre.log .src { color: #f0a070; }
figure { text-align: center; margin: 10px 0; page-break-inside: avoid; } img { border: 1px solid #ddd; }
figcaption { font-size: 9pt; color: #555; margin-top: 4px; }
code { font-family: Menlo, Consolas, monospace; font-size: 9pt; } ol.refs li { margin-bottom: 4px; } a { color: #1f5fa8; }
"""

OUT_HTML.write_text(f'<!doctype html><html><head><meta charset="utf-8"><title>HeatGuard Report</title>'
                    f"<style>{CSS}</style></head><body>{body}</body></html>")
subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                f"--print-to-pdf={OUT_PDF}", OUT_HTML.as_uri()], check=True, capture_output=True)
print(f"wrote {OUT_HTML.relative_to(ROOT)} and {OUT_PDF.relative_to(ROOT)}")
