"""Run Docker/Kubernetes/experiment commands live and save their REAL output as
(1) text in experiments/results/terminal_captures/ and (2) a terminal-window image in docs/screenshots/.
The images are renderings of the captured text (nothing is typed in by hand).
Usage: python docs/tools/capture_terminal.py
"""
from datetime import datetime
import html
from pathlib import Path
import subprocess
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.image as mi  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TXT = ROOT / "experiments" / "results" / "terminal_captures"
IMG = ROOT / "docs" / "screenshots"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
ENV_PATH = "/Applications/Docker.app/Contents/Resources/bin:/opt/homebrew/bin:/usr/bin:/bin"
PY = ".venv/bin/python"  # relative to ROOT (the project path contains spaces)

API_POD = "$(kubectl get pods -l app=heatguard-api -o jsonpath='{.items[0].metadata.name}')"
CAPTURES = [
    ("t01_docker_version", "Exp 2 · Docker engine", ["docker version --format 'Client {{.Client.Version}} | Server {{.Server.Version}} ({{.Server.Os}}/{{.Server.Arch}})'", "docker compose version"]),
    ("t02_compose_ps", "Exp 2 · backend + frontend running with Docker Compose", ["docker compose ps"]),
    ("t03_docker_images", "Exp 2 · HeatGuard images", ["docker images --filter 'reference=ayushiranjan27/*'"]),
    ("t04_hub_multiarch", "Exp 2 · images on Docker Hub (multi-arch)", [
        "docker buildx imagetools inspect ayushiranjan27/heatguard:2.0 | grep -E 'Name:|Platform:' | grep -v unknown",
        "docker buildx imagetools inspect ayushiranjan27/heatguard-web:2.1 | grep -E 'Name:|Platform:' | grep -v unknown"]),
    ("t05_docker_stats", "Exp 2 · container resource use (idle)", ["docker stats --no-stream heatguard-api-1 heatguard-web-1"]),
    ("t06_api_through_frontend", "Exp 2 · forecast through the frontend proxy", [
        "curl -s localhost:8080/api/health",
        "V=$(curl -s 'localhost:8080/api/observed?city=Delhi&date=2024-05-27' | python3 -c 'import json,sys;print(json.load(sys.stdin)[\"recent_tmax\"])'); "
        "curl -s -X POST localhost:8080/api/predict -H 'Content-Type: application/json' -d \"{\\\"city\\\":\\\"Delhi\\\",\\\"date\\\":\\\"2024-05-27\\\",\\\"recent_tmax\\\":$V}\" | python3 experiments/show.py predict"]),
    ("t07_compose_logs", "Exp 2 · container logs", ["docker compose logs --tail 4 api", "docker compose logs --tail 4 web"]),
    ("t08_k8s_cluster", "Exp 3 · Kubernetes cluster (kind)", ["kind get clusters", "kubectl cluster-info", "kubectl get nodes -o wide"]),
    ("t09_k8s_objects", "Exp 3 · deployments, replica sets and services", ["kubectl get deployments,replicasets,services -o wide"]),
    ("t10_k8s_pods", "Exp 3 · pods", ["kubectl get pods -o wide"]),
    ("t11_k8s_describe", "Exp 3 · backend deployment: image, strategy, limits from Exp 7, probes", [
        "kubectl describe deployment heatguard-api | grep -E 'Replicas:|StrategyType|RollingUpdateStrategy|Image:|Limits|Requests|cpu:|memory:|Liveness|Readiness|PreStop|sleep'"]),
    ("t12_k8s_selfheal", "Exp 3 · self-healing: a deleted backend pod is replaced", [
        f"kubectl delete pod {API_POD} --wait=false", "kubectl get pods -l app=heatguard-api", "sleep 12", "kubectl get pods -l app=heatguard-api"]),
    ("t13_k8s_scaling", "Exp 3 · horizontal scaling of the frontend 2 -> 4 -> 2", [
        "kubectl scale deployment heatguard-web --replicas=4", "kubectl rollout status deployment/heatguard-web --timeout=120s",
        "kubectl get pods -l app=heatguard-web", "kubectl scale deployment heatguard-web --replicas=2"]),
    ("t14_k8s_access", "Exp 3 · service access through NodePort 30080", [
        "for p in / /dashboard /api/health /api/docs; do curl -s -o /dev/null -w \"HTTP %{http_code}  $p\\n\" localhost:30080$p; done",
        "for i in 1 2 3 4; do curl -s localhost:30080/api/health; echo; done"]),
    ("t15_k8s_history", "Exp 3 · rollout history and current images", [
        "kubectl rollout history deployment/heatguard-api", "kubectl rollout history deployment/heatguard-web",
        "kubectl get deployments -o custom-columns=NAME:.metadata.name,READY:.status.readyReplicas,IMAGE:.spec.template.spec.containers[0].image"]),
    ("t16_k8s_events", "Exp 3 · recent cluster events", ["kubectl get events --sort-by=.lastTimestamp | tail -12"]),
    ("t17_rightsize", "Exp 7 · right-sizing decision from measured peaks", [f"{PY} experiments/rightsize.py"]),
    ("t18_results", "Exp 7 & 8 · measured results (same workload)", [f"{PY} docs/tools/print_results.py"]),
    ("t19_pytest", "Testing · automated tests", [f"{PY} -m pytest -q -p no:warnings"]),
]

PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: "Plex Mono"; src: url("{font}") format("woff2"); }}
body {{ margin: 0; background: #ffffff; padding: 18px; }}
.win {{ width: 1180px; background: #14161b; border-radius: 10px; box-shadow: 0 10px 30px rgba(0,0,0,.25); overflow: hidden; }}
.bar {{ height: 30px; background: #2a2d34; display: flex; align-items: center; padding: 0 12px; gap: 8px; font: 12px -apple-system, sans-serif; color: #b9bec8; }}
.dot {{ width: 12px; height: 12px; border-radius: 50%; }} .t {{ margin-left: 14px; }}
pre {{ margin: 0; padding: 14px 18px 18px; font: 12.5px/1.5 "Plex Mono", Menlo, monospace; color: #d9dee7; white-space: pre-wrap; word-break: break-all; }}
.p {{ color: #7fd1a5; }} .c {{ color: #ffd479; }} .m {{ color: #7d8594; }}
</style></head><body><div class="win"><div class="bar"><span class="dot" style="background:#ff5f57"></span><span class="dot" style="background:#febc2e"></span>
<span class="dot" style="background:#28c840"></span><span class="t">ayushiranjan@MacBook-Air — heatguard — {title}</span></div><pre>{body}</pre></div></body></html>"""


def run(cmd):
    p = subprocess.run(["bash", "-c", cmd], cwd=ROOT, capture_output=True, text=True,
                       env={"PATH": ENV_PATH, "HOME": str(Path.home()), "TERM": "dumb", "COLUMNS": "150"})
    return (p.stdout + p.stderr).rstrip("\n")


def render(name, title, transcript):
    body = []
    for kind, text in transcript:
        if kind == "cmd":
            body.append(f'<span class="p">ayushiranjan@MacBook-Air heatguard %</span> <span class="c">{html.escape(text)}</span>')
        elif kind == "meta":
            body.append(f'<span class="m">{html.escape(text)}</span>')
        else:
            body.append(html.escape(text))
    page = TXT / f"{name}.html"
    page.write_text(PAGE.format(font=(ROOT / "frontend/public/assets/fonts/plexmono-400.woff2").as_uri(), title=html.escape(title), body="\n".join(body)))
    png = IMG / f"{name}.png"
    lines = sum(max(1, len(t) // 145 + 1) for _, t in transcript for t in t.split("\n"))
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size=1220,{min(4000, 120 + lines * 19)}",
                    f"--screenshot={png}", page.as_uri()], capture_output=True)
    page.unlink()
    a = mi.imread(png)
    rows = np.where((a[:, :, :3] < 0.98).any(axis=(1, 2)))[0]
    cols = np.where((a[:, :, :3] < 0.98).any(axis=(0, 2)))[0]
    mi.imsave(png, a[max(0, rows[0] - 8): rows[-1] + 10, max(0, cols[0] - 8): cols[-1] + 10])


def main():
    TXT.mkdir(parents=True, exist_ok=True)
    only = set(sys.argv[1:])
    for name, title, cmds in CAPTURES:
        if only and name not in only:
            continue
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        transcript = [("meta", f"# captured {stamp}")]
        for c in cmds:
            transcript.append(("cmd", c))
            out = run(c)
            if out:
                transcript.append(("out", out))
        (TXT / f"{name}.txt").write_text("\n".join(("$ " + t if k == "cmd" else t) for k, t in transcript) + "\n")
        render(name, title, transcript)
        print("captured", name)


if __name__ == "__main__":
    main()
