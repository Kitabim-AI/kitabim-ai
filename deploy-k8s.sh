#!/bin/bash
set -e

echo "🏗️  Building and deploying to Kubernetes..."

# Build images with BuildKit caching
./build-k8s.sh

# Deploy to Kubernetes
echo ""
echo "🚀 Deploying to Kubernetes..."
kubectl apply -f k8s/local/

echo ""
echo "⏳ Waiting for rollout to complete..."
kubectl rollout status deployment/backend -n kitabim --timeout=5m
kubectl rollout status deployment/worker -n kitabim --timeout=5m
kubectl rollout status deployment/frontend -n kitabim --timeout=5m

echo ""
echo "✅ Deployment complete!"
echo ""
echo "Service endpoints:"
kubectl get services -n kitabim
