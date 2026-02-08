#!/bin/bash
set -e

echo "Building Backend..."
docker build -t kitabim-backend:local -f services/backend/Dockerfile .

echo "Building Worker..."
docker build -t kitabim-worker:local -f services/worker/Dockerfile .

echo "Building Frontend..."
docker build -t kitabim-frontend:local -f apps/frontend/Dockerfile .

# Build the main services
# Backend, worker, and frontend are rebuilt on change.

echo "Restarting deployments..."
kubectl -n kitabim rollout restart deployment/backend deployment/worker deployment/frontend

echo "Waiting for rollout..."
kubectl -n kitabim rollout status deployment/backend
kubectl -n kitabim rollout status deployment/worker
kubectl -n kitabim rollout status deployment/frontend

echo "Deployment complete."
