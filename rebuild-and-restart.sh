#!/bin/bash
set -e

# Quick rebuild and restart for development
# Usage: ./rebuild-and-restart.sh [backend|worker|frontend|all]

COMPONENT=${1:-all}

rebuild_component() {
  local comp=$1
  echo "🔨 Rebuilding $comp..."

  case $comp in
    backend)
      docker build -f Dockerfile.backend -t kitabim-backend:local -q .
      kubectl rollout restart deployment/backend -n kitabim
      ;;
    worker)
      docker build -f Dockerfile.worker -t kitabim-worker:local -q .
      kubectl rollout restart deployment/worker -n kitabim
      ;;
    frontend)
      docker build -f apps/frontend/Dockerfile -t kitabim-frontend:local -q .
      kubectl rollout restart deployment/frontend -n kitabim
      ;;
    *)
      echo "Unknown component: $comp"
      exit 1
      ;;
  esac

  echo "✅ $comp rebuilt and restarted"
}

export DOCKER_BUILDKIT=1

if [ "$COMPONENT" = "all" ]; then
  rebuild_component backend
  rebuild_component worker
  rebuild_component frontend
else
  rebuild_component "$COMPONENT"
fi

echo ""
echo "📊 Deployment status:"
kubectl get pods -n kitabim
