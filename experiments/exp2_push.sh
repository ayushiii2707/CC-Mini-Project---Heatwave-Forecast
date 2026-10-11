#!/usr/bin/env bash
# Experiment 2 (Docker Hub part): tag and push images. Requires `docker login` first.
# Usage: DOCKERHUB_USER=<your-username> bash experiments/exp2_push.sh
set -euo pipefail
: "${DOCKERHUB_USER:?set DOCKERHUB_USER (see .env.example)}"
cd "$(dirname "$0")/.."
run() { echo "\$ $*"; "$@"; echo; }

run docker info --format 'Logged in as: {{.Username}}' 2>/dev/null || true
# 1) HeatGuard image for both Apple Silicon (arm64) and Intel/AMD (amd64), pushed to Docker Hub
run docker buildx build --platform linux/arm64,linux/amd64 -t "$DOCKERHUB_USER/heatguard:1.0" -t "$DOCKERHUB_USER/heatguard:latest" --push .
run docker buildx imagetools inspect "$DOCKERHUB_USER/heatguard:1.0"
# 2) Manual task: push the nginx image to your Docker Hub
run docker tag nginx:latest "$DOCKERHUB_USER/nginx-exp2:1.0"
run docker push "$DOCKERHUB_USER/nginx-exp2:1.0"
# 3) Prove the pushed image works: remove local copy, pull from Hub and run it
docker rm -f heatguard-hub >/dev/null 2>&1 || true
run docker rmi "$DOCKERHUB_USER/heatguard:1.0" || true
run docker pull "$DOCKERHUB_USER/heatguard:1.0"
run docker run -d --name heatguard-hub -p 8001:8000 "$DOCKERHUB_USER/heatguard:1.0"
sleep 6
run curl -s localhost:8001/health
docker rm -f heatguard-hub >/dev/null
