#!/bin/bash
# Deploy Kitabim AI to GCE production VM
# Usage (from repo root): ./deploy/gcp/scripts/deploy.sh [IMAGE_TAG]
# Example: ./deploy/gcp/scripts/deploy.sh abc1234
# If no tag given, uses current git short SHA
set -euo pipefail

# Ensure gcloud is on PATH (handles non-interactive shells on Mac)
for _gcloud_dir in \
    "$HOME/google-cloud-sdk/bin" \
    "/usr/local/google-cloud-sdk/bin" \
    "/opt/homebrew/bin" \
    "/usr/local/bin"; do
    if [ -x "$_gcloud_dir/gcloud" ]; then
        export PATH="$_gcloud_dir:$PATH"
        break
    fi
done

# ─── Config ───────────────────────────────────────────────────────────────
GCP_PROJECT_ID="${GCP_PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="us-south1"
REGISTRY="${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/kitabim"
IMAGE_TAG="${1:-$(git rev-parse --short HEAD)}"
VM_INSTANCE="kitabim-prod"
VM_ZONE="us-south1-c"
APP_DIR="/opt/kitabim"
COMPOSE_FILE="${APP_DIR}/deploy/gcp/docker-compose.yml"

echo "==> Deploying Kitabim AI"
echo "    Project:   $GCP_PROJECT_ID"
echo "    Registry:  $REGISTRY"
echo "    Image tag: $IMAGE_TAG"
echo "    VM:        $VM_INSTANCE ($VM_ZONE)"
echo ""

# ─── Build images ─────────────────────────────────────────────────────────
echo "==> [1/3] Building Docker images"
export DOCKER_BUILDKIT=1

docker build -f Dockerfile.backend \
    --platform linux/amd64 \
    -t "${REGISTRY}/kitabim-backend:${IMAGE_TAG}" \
    -t "${REGISTRY}/kitabim-backend:latest" \
    --progress=plain .

docker build -f Dockerfile.worker \
    --platform linux/amd64 \
    -t "${REGISTRY}/kitabim-worker:${IMAGE_TAG}" \
    -t "${REGISTRY}/kitabim-worker:latest" \
    --progress=plain .

docker build -f apps/frontend/Dockerfile \
    --platform linux/amd64 \
    -t "${REGISTRY}/kitabim-frontend:${IMAGE_TAG}" \
    -t "${REGISTRY}/kitabim-frontend:latest" \
    --progress=plain .

# ─── Push to Artifact Registry ────────────────────────────────────────────
echo "==> [2/3] Pushing images to Artifact Registry"
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

docker push "${REGISTRY}/kitabim-backend:${IMAGE_TAG}"
docker push "${REGISTRY}/kitabim-backend:latest"
docker push "${REGISTRY}/kitabim-worker:${IMAGE_TAG}"
docker push "${REGISTRY}/kitabim-worker:latest"
docker push "${REGISTRY}/kitabim-frontend:${IMAGE_TAG}"
docker push "${REGISTRY}/kitabim-frontend:latest"

# ─── Deploy to VM ─────────────────────────────────────────────────────────
echo "==> [3/3] Deploying to VM: $VM_INSTANCE"
gcloud compute ssh "$VM_INSTANCE" --zone="$VM_ZONE" --command="
    set -e

    cd ${APP_DIR}
    echo '--> Pulling latest code'
    git pull --ff-only origin main

    echo '--> Pulling new Docker images'
    REGISTRY=${REGISTRY} IMAGE_TAG=${IMAGE_TAG} \
        docker compose -f ${COMPOSE_FILE} pull backend worker frontend

    echo '--> Restarting services'
    REGISTRY=${REGISTRY} IMAGE_TAG=${IMAGE_TAG} \
        docker compose -f ${COMPOSE_FILE} up -d --no-deps backend worker frontend nginx

    echo '--> Waiting for backend health check'
    sleep 8
    for i in \$(seq 1 10); do
        if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
            echo 'Backend: healthy'
            break
        fi
        echo \"  attempt \$i/10...\"
        sleep 3
    done

    echo '--> Service status'
    REGISTRY=${REGISTRY} IMAGE_TAG=${IMAGE_TAG} \
        docker compose -f ${COMPOSE_FILE} ps

    echo \"Deploy complete: ${IMAGE_TAG}\"
"

echo ""
echo "============================================"
echo " Deployed: $IMAGE_TAG"
echo " https://kitabim.ai/health"
echo "============================================"
