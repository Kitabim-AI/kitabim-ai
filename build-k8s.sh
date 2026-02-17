#!/bin/bash
set -e

# Build optimized images for Kubernetes with BuildKit
export DOCKER_BUILDKIT=1

echo "🚀 Building optimized Docker images for Kubernetes..."

# Build backend
echo "📦 Building backend..."
docker build -f Dockerfile.backend -t kitabim-backend:local --progress=plain .

# Build worker
echo "📦 Building worker..."
docker build -f Dockerfile.worker -t kitabim-worker:local --progress=plain .

# Build frontend
echo "📦 Building frontend..."
docker build -f apps/frontend/Dockerfile -t kitabim-frontend:local --progress=plain .

echo "✅ All images built successfully!"
echo ""
echo "Image sizes:"
docker images | grep "kitabim.*local"
echo ""
echo "To deploy to Kubernetes, run:"
echo "  kubectl apply -f k8s/local/"
