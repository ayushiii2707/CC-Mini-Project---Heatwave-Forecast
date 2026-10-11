#!/usr/bin/env bash
# Experiment 3 (v2): deploy HeatGuard backend + frontend from Docker Hub on a local kind Kubernetes
# cluster and demonstrate pod status, service access, scaling, self-healing, a failed rollout with
# rollback, and a zero-downtime rolling update (measured).
# Usage: DOCKERHUB_USER=<your-username> bash experiments/exp3_kubernetes.sh
set -uo pipefail
: "${DOCKERHUB_USER:?set DOCKERHUB_USER (see .env.example)}"
cd "$(dirname "$0")/.."
run() { echo "\$ $*"; "$@"; echo; }
URL=http://localhost:30080

# Poll the full path (NodePort -> frontend pod -> backend Service -> backend pod) every 0.25 s
# while a command runs; report how many requests did not return HTTP 200.
availability_during() {
  local out=/tmp/heatguard-avail.txt; : > "$out"
  ( while [ ! -f /tmp/heatguard-stop ]; do curl -s -m 2 -o /dev/null -w "%{http_code}\n" "$URL/api/health" >> "$out"; sleep 0.25; done ) &
  local poller=$!
  rm -f /tmp/heatguard-stop
  "$@"
  sleep 3; touch /tmp/heatguard-stop; wait $poller; rm -f /tmp/heatguard-stop
  echo "# availability: $(grep -c '^200$' "$out")/$(wc -l < "$out" | tr -d ' ') requests returned HTTP 200 (failed: $(grep -vc '^200$' "$out"))"
}

# Right-sized backend limits from Experiment 7
CPU=$(python3 -c "import json;d=json.load(open('experiments/results/exp7/rightsizing_decision.json'));print(str(int(d['right_sized']['cpus']*1000))+'m')")
MEM=$(python3 -c "import json;d=json.load(open('experiments/results/exp7/rightsizing_decision.json'));print(d['right_sized']['memory'].replace('m','Mi'))")
echo "# backend limits from Experiment 7 right-sizing: cpu=$CPU memory=$MEM"; echo

kind get clusters 2>/dev/null | grep -q '^heatguard$' || run kind create cluster --config k8s/kind-config.yaml
run kubectl cluster-info --context kind-heatguard
run kubectl get nodes -o wide

echo "### 1. Deploy backend (ClusterIP) and frontend (NodePort) from Docker Hub"
sed -e "s|DOCKERHUB_USER|$DOCKERHUB_USER|" -e "s|API_CPU_LIMIT|$CPU|" -e "s|API_MEM_LIMIT|$MEM|" k8s/api.yaml > /tmp/heatguard-api.yaml
sed -e "s|DOCKERHUB_USER|$DOCKERHUB_USER|" k8s/web.yaml > /tmp/heatguard-web.yaml
run kubectl apply -f /tmp/heatguard-api.yaml -f /tmp/heatguard-web.yaml
run kubectl rollout status deployment/heatguard-api --timeout=300s
run kubectl rollout status deployment/heatguard-web --timeout=300s
run kubectl get deployments,pods,services -o wide
POD=$(kubectl get pods -l app=heatguard-api --field-selector=status.phase=Running -o jsonpath="{.items[0].metadata.name}")
echo "\$ kubectl describe pod $POD | grep -E 'Image:|Limits|Requests|cpu|memory|Pulled|preStop'"
kubectl describe pod "$POD" | grep -E "Image:|Limits:|Requests:|cpu:|memory:|Pulled|PreStop|sleep"; echo
echo "\$ kubectl get deployment heatguard-api -o jsonpath='{.spec.strategy}'"
kubectl get deployment heatguard-api -o jsonpath='{.spec.strategy}'; echo; echo

echo "### 2. Service access: browser -> NodePort 30080 -> frontend -> heatguard-api Service -> backend pods"
run curl -s "$URL/healthz"
echo "# backend pod answering each request (load-balanced by the heatguard-api Service):"
for i in 1 2 3 4 5 6 7 8; do curl -s "$URL/api/health"; echo; done; echo
echo "\$ curl -s -X POST $URL/api/predict   (Delhi, real IMD values 21-27 May 2024)"
V=$(curl -s "$URL/api/observed?city=Delhi&date=2024-05-27" | python3 -c 'import json,sys;print(json.load(sys.stdin)["recent_tmax"])')
curl -s -X POST "$URL/api/predict" -H 'Content-Type: application/json' \
  -d "{\"city\":\"Delhi\",\"date\":\"2024-05-27\",\"recent_tmax\":$V}" | python3 experiments/show.py predict; echo
echo "# invalid input through the cluster"
curl -s -w " HTTP %{http_code}\n" -X POST "$URL/api/predict" -H 'Content-Type: application/json' \
  -d '{"city":"Atlantis","date":"2024-05-27","recent_tmax":[40,41,42,43,44,45,46]}'; echo
echo "# the backend is not exposed outside the cluster (type ClusterIP, no NodePort):"
run kubectl get service heatguard-api -o jsonpath='{.spec.type} {.spec.ports}'
echo

echo "### 3. Horizontal scaling: frontend 2 -> 4, backend 2 -> 3"
run kubectl scale deployment heatguard-web --replicas=4
run kubectl scale deployment heatguard-api --replicas=3
run kubectl rollout status deployment/heatguard-web --timeout=120s
run kubectl rollout status deployment/heatguard-api --timeout=120s
run kubectl get pods -o wide

echo "### 4. Self-healing: delete a backend pod; the Deployment replaces it"
VICTIM=$(kubectl get pods -l app=heatguard-api -o jsonpath='{.items[0].metadata.name}')
run kubectl delete pod "$VICTIM" --wait=false
run kubectl get pods -l app=heatguard-api
sleep 15
run kubectl get pods -l app=heatguard-api
run kubectl get deployment heatguard-api

echo "### 5. Failure scenario: bad backend image -> rollout blocked, old pods keep serving -> rollback"
run kubectl set image deployment/heatguard-api api="docker.io/$DOCKERHUB_USER/heatguard:does-not-exist"
sleep 25
run kubectl get pods -l app=heatguard-api
run curl -s "$URL/api/health"
echo
run kubectl rollout undo deployment/heatguard-api
run kubectl rollout status deployment/heatguard-api --timeout=180s
run kubectl get pods -l app=heatguard-api

echo "### 6. Rolling update of the backend with continuous availability check"
echo "# strategy maxSurge=1, maxUnavailable=0 and preStop sleep 5 (v1 without preStop: 39/40 OK)"
echo "\$ kubectl rollout restart deployment/heatguard-api && kubectl rollout status deployment/heatguard-api"
availability_during bash -c "kubectl rollout restart deployment/heatguard-api >/dev/null && kubectl rollout status deployment/heatguard-api --timeout=300s"
echo
echo "\$ kubectl rollout restart deployment/heatguard-web && kubectl rollout status deployment/heatguard-web"
availability_during bash -c "kubectl rollout restart deployment/heatguard-web >/dev/null && kubectl rollout status deployment/heatguard-web --timeout=300s"
echo
run kubectl rollout history deployment/heatguard-api
run kubectl get pods -o wide

echo "### 7. Logs and events"
POD=$(kubectl get pods -l app=heatguard-api --field-selector=status.phase=Running -o jsonpath="{.items[0].metadata.name}")
run kubectl logs "$POD" --tail=5
echo "\$ kubectl get events --sort-by=.lastTimestamp | tail -20"
kubectl get events --sort-by=.lastTimestamp | tail -20
