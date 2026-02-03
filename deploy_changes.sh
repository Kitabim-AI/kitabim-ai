#!/bin/bash
set -e

echo "Building Backend..."
docker build -t kitabim-backend:local -f services/backend/Dockerfile .

echo "Building Worker..."
docker build -t kitabim-worker:local -f services/worker/Dockerfile .

echo "Building Frontend..."
docker build -t kitabim-frontend:local -f apps/frontend/Dockerfile .

# UyghurOCR was likely not changed, but let's build it to be safe if requested, or skip to save time. 
# The user modified backend logic and frontend. OCR service itself (code) wasn't changed in this session.
# But "Reverting OCR Pipeline" summary mentions layout_processor.py? 
# Ah, that was a PREVIOUS session "Reverting OCR Pipeline" (Step 920).
# In THIS session, I modified backend-core (used by backend and worker) and frontend.
# So backend, worker, frontend are the targets.

echo "Restarting deployments..."
kubectl -n kitabim rollout restart deployment/backend deployment/worker deployment/frontend

echo "Waiting for rollout..."
kubectl -n kitabim rollout status deployment/backend
kubectl -n kitabim rollout status deployment/worker
kubectl -n kitabim rollout status deployment/frontend

echo "Deployment complete."
