#!/bin/bash
set -e

BUILD_UI=false
if [[ "$1" == "--ui" ]]; then
  BUILD_UI=true
fi

echo "Building Backend..."
docker build -t kitabim-backend:local -f services/backend/Dockerfile .

echo "Building Worker..."
docker build -t kitabim-worker:local -f services/worker/Dockerfile .

if [ "$BUILD_UI" = true ]; then
  echo "Building Frontend..."
  docker build -t kitabim-frontend:local -f apps/frontend/Dockerfile .
else
  echo "Skipping Frontend build (use --ui flag to include it)."
fi

echo "Restarting deployments..."
kubectl -n kitabim rollout restart deployment/backend deployment/worker
if [ "$BUILD_UI" = true ]; then
  kubectl -n kitabim rollout restart deployment/frontend
fi

echo "Waiting for rollout..."
kubectl -n kitabim rollout status deployment/backend
kubectl -n kitabim rollout status deployment/worker
if [ "$BUILD_UI" = true ]; then
  kubectl -n kitabim rollout status deployment/frontend
fi

echo "Deployment complete."
