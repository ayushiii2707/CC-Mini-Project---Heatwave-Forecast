#!/usr/bin/env bash
# Experiment 2 (v2): containerise the backend API and the web frontend, run them together with
# Docker Compose, test them, push both images to Docker Hub (arm64 + amd64) and verify by pulling.
# Requires `docker login`.   Usage: DOCKERHUB_USER=<user> bash experiments/exp2_docker.sh
set -uo pipefail
: "${DOCKERHUB_USER:?set DOCKERHUB_USER (see .env.example)}"
cd "$(dirname "$0")/.."
run() { echo "\$ $*"; "$@"; echo; }
API=$DOCKERHUB_USER/heatguard:2.0
WEB=$DOCKERHUB_USER/heatguard-web:2.0

echo "### 1. Build both images"
run docker version --format 'Client {{.Client.Version}} / Server {{.Server.Version}} ({{.Server.Os}}/{{.Server.Arch}})'
run docker build -q -t "$API" .
run docker build -q -t "$WEB" ./frontend
run docker images --filter "reference=$DOCKERHUB_USER/heatguard*"

echo "### 2. Run backend + frontend together (docker-compose.yml)"
docker compose down >/dev/null 2>&1
run docker compose up -d --wait
run docker compose ps
run curl -s localhost:8000/health
run curl -s localhost:8080/healthz
echo "\$ curl -s localhost:8080/api/health          # frontend -> nginx proxy -> backend"
curl -s localhost:8080/api/health; echo; echo
echo "\$ curl -s -X POST localhost:8080/api/predict (Delhi, real IMD values 21-27 May 2024)"
V=$(curl -s "localhost:8080/api/observed?city=Delhi&date=2024-05-27" | python3 -c 'import json,sys;print(json.load(sys.stdin)["recent_tmax"])')
curl -s -X POST localhost:8080/api/predict -H 'Content-Type: application/json' \
  -d "{\"city\":\"Delhi\",\"date\":\"2024-05-27\",\"recent_tmax\":$V}" | python3 experiments/show.py predict
echo
echo "\$ curl -s 'localhost:8080/api/outlook?date=2024-05-27'   (all 10 cities)"
curl -s "localhost:8080/api/outlook?date=2024-05-27" | python3 experiments/show.py outlook
echo
echo "### 3. Failure scenarios (through the frontend proxy)"
echo "# unknown city";            curl -s -w " HTTP %{http_code}\n" -X POST localhost:8080/api/predict -H 'Content-Type: application/json' -d '{"city":"Atlantis","date":"2024-05-27","recent_tmax":[40,41,42,43,44,45,46]}'
echo "# 99.9 = IMD missing code"; curl -s -w " HTTP %{http_code}\n" -X POST localhost:8080/api/predict -H 'Content-Type: application/json' -d '{"city":"Delhi","date":"2024-05-27","recent_tmax":[40,41,42,43,44,45,99.9]}'
echo "# date outside the data";   curl -s -w " HTTP %{http_code}\n" "localhost:8080/api/outlook?date=2030-05-01"
echo "# backend stopped -> frontend stays up, API calls fail with a gateway error"
docker compose stop api >/dev/null 2>&1
curl -s -o /dev/null -w "  /healthz HTTP %{http_code}   /api/health HTTP " localhost:8080/healthz; curl -s -o /dev/null -w "%{http_code}\n" localhost:8080/api/health
docker compose start api >/dev/null 2>&1; sleep 5
curl -s -o /dev/null -w "# backend restarted -> /api/health HTTP %{http_code}\n\n" localhost:8080/api/health

echo "### 4. Push both images to Docker Hub for linux/arm64 and linux/amd64"
run docker buildx build --platform linux/arm64,linux/amd64 -t "$API" -t "$DOCKERHUB_USER/heatguard:latest" --push --quiet .
run docker buildx build --platform linux/arm64,linux/amd64 -t "$WEB" -t "$DOCKERHUB_USER/heatguard-web:latest" --push --quiet ./frontend
for img in "$API" "$WEB"; do
  echo "\$ docker buildx imagetools inspect $img | grep Platform"; docker buildx imagetools inspect "$img" | grep "Platform:" | grep -v unknown; echo
done

echo "### 5. Verify: delete local images, pull from Docker Hub, run with Compose"
docker compose down >/dev/null 2>&1
run docker rmi "$API" "$WEB"
run docker compose pull
run docker compose up -d --wait --no-build
run docker compose ps
run curl -s localhost:8080/api/health
