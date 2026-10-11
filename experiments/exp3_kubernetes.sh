#!/usr/bin/env bash
# Experiment 3: deploy the Docker Hub image on a local kind Kubernetes cluster and demonstrate
# pod status, service access, load balancing, scaling, self-healing and a failed rollout + rollback.
# Usage: DOCKERHUB_USER=<your-username> bash experiments/exp3_kubernetes.sh
set -uo pipefail
: "${DOCKERHUB_USER:?set DOCKERHUB_USER (see .env.example)}"
cd "$(dirname "$0")/.."
run() { echo "\$ $*"; "$@"; echo; }
URL=http://localhost:30080

kind get clusters | grep -q '^heatguard$' || run kind create cluster --config k8s/kind-config.yaml
run kubectl cluster-info --context kind-heatguard
run kubectl get nodes -o wide

echo "### 1. Deploy (image pulled from Docker Hub) and expose"
sed "s|DOCKERHUB_USER|$DOCKERHUB_USER|" k8s/deployment.yaml > /tmp/heatguard-deployment.yaml
run kubectl apply -f /tmp/heatguard-deployment.yaml
run kubectl apply -f k8s/service.yaml
run kubectl rollout status deployment/heatguard --timeout=300s
run kubectl get deployment heatguard
run kubectl get pods -o wide
run kubectl get service heatguard
POD=$(kubectl get pods -l app=heatguard --field-selector=status.phase=Running -o jsonpath="{.items[0].metadata.name}")
echo "\$ kubectl describe pod $POD | grep -E 'Image:|Pulled|Limits|cpu|memory'"
kubectl describe pod "$POD" | grep -E "Image:|Pulled|Limits:|Requests:|cpu:|memory:"; echo

echo "### 2. Service access + load balancing across pods"
for i in 1 2 3 4 5 6; do curl -s "$URL/health"; echo; done; echo
echo "\$ curl -X POST $URL/predict (Delhi, real IMD values for 21-27 May 2024)"
V=$(curl -s "$URL/observed?city=Delhi&date=2024-05-27" | python3 -c 'import json,sys;print(json.load(sys.stdin)["recent_tmax"])')
curl -s -X POST "$URL/predict" -H 'Content-Type: application/json' \
  -d "{\"city\":\"Delhi\",\"date\":\"2024-05-27\",\"recent_tmax\":$V}"; echo; echo
echo "# invalid input through the Service"
curl -s -w " HTTP %{http_code}" -X POST "$URL/predict" -H 'Content-Type: application/json' \
  -d '{"city":"Atlantis","date":"2024-05-27","recent_tmax":[40,41,42,43,44,45,46]}'; echo; echo

echo "### 3. Scaling 2 -> 3 replicas"
run kubectl scale deployment heatguard --replicas=3
run kubectl rollout status deployment/heatguard --timeout=120s
run kubectl get pods -o wide

echo "### 4. Self-healing: delete a pod, the Deployment recreates it"
VICTIM=$(kubectl get pods -l app=heatguard -o jsonpath='{.items[0].metadata.name}')
run kubectl delete pod "$VICTIM" --wait=false
run kubectl get pods
sleep 15
run kubectl get pods
run kubectl get deployment heatguard
for i in 1 2 3; do curl -s "$URL/health"; echo; done; echo

echo "### 5. Failure scenario: bad image tag -> rollout blocked, old pods keep serving -> rollback"
run kubectl set image deployment/heatguard heatguard="docker.io/$DOCKERHUB_USER/heatguard:does-not-exist"
sleep 25
run kubectl get pods
run curl -s "$URL/health"
echo
run kubectl rollout undo deployment/heatguard
run kubectl rollout status deployment/heatguard --timeout=180s
run kubectl rollout history deployment/heatguard
run kubectl get pods -o wide

echo "### 6. Logs and events"
POD=$(kubectl get pods -l app=heatguard --field-selector=status.phase=Running -o jsonpath="{.items[0].metadata.name}")
run kubectl logs "$POD" --tail=5
echo "\$ kubectl get events --sort-by=.lastTimestamp | tail -25"
kubectl get events --sort-by=.lastTimestamp | tail -25
