#!/usr/bin/env bash
# Release a new frontend version: push to Docker Hub (arm64 + amd64) and roll it out on the kind
# cluster with a continuous availability check (Experiments 2 and 3 workflow, frontend only).
# Usage: DOCKERHUB_USER=<user> VERSION=2.1 bash experiments/release_frontend.sh
set -uo pipefail
: "${DOCKERHUB_USER:?set DOCKERHUB_USER}"; : "${VERSION:?set VERSION}"
cd "$(dirname "$0")/.."
run() { echo "\$ $*"; "$@"; echo; }
IMG=$DOCKERHUB_USER/heatguard-web:$VERSION
URL=http://localhost:30080

echo "### 1. Build and push $IMG (linux/arm64 + linux/amd64)"
run docker buildx build --platform linux/arm64,linux/amd64 -t "$IMG" -t "$DOCKERHUB_USER/heatguard-web:latest" --push --quiet ./frontend
echo "\$ docker buildx imagetools inspect $IMG | grep Platform"; docker buildx imagetools inspect "$IMG" | grep "Platform:" | grep -v unknown; echo

echo "### 2. Rolling update on Kubernetes with availability check (every 0.25 s through NodePort 30080)"
run kubectl get deployment heatguard-web -o wide
: > /tmp/hg-avail.txt; rm -f /tmp/hg-stop
( while [ ! -f /tmp/hg-stop ]; do curl -s -m 2 -o /dev/null -w "%{http_code}\n" "$URL/" >> /tmp/hg-avail.txt; curl -s -m 2 -o /dev/null -w "%{http_code}\n" "$URL/api/health" >> /tmp/hg-avail.txt; sleep 0.25; done ) &
P=$!
run kubectl set image deployment/heatguard-web web="docker.io/$IMG"
run kubectl rollout status deployment/heatguard-web --timeout=300s
sleep 3; touch /tmp/hg-stop; wait $P; rm -f /tmp/hg-stop
echo "# availability: $(grep -c '^200$' /tmp/hg-avail.txt)/$(wc -l < /tmp/hg-avail.txt | tr -d ' ') requests (landing page + /api/health) returned HTTP 200 (failed: $(grep -vc '^200$' /tmp/hg-avail.txt))"; echo
run kubectl get deployment heatguard-web -o wide
run kubectl get pods -l app=heatguard-web
run kubectl rollout history deployment/heatguard-web

echo "### 3. New pages served by the cluster"
for p in / /dashboard /api/health /api/docs; do curl -s -o /dev/null -w "HTTP %{http_code}  %{content_type}  $p\n" "$URL$p"; done
echo "\$ curl -s $URL/ | grep -o '<title>.*</title>'"; curl -s "$URL/" | grep -o '<title>.*</title>'
