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
      docker compose build backend
      docker compose up -d backend
      ;;
    worker)
      docker compose build worker
      docker compose up -d worker
      ;;
    frontend)
      docker compose build frontend
      docker compose up -d frontend
      ;;
    *)
      echo "Unknown component: $comp"
      exit 1
      ;;
  esac

  echo "✅ $comp rebuilt and restarted"
}

if [ "$COMPONENT" = "all" ]; then
  docker compose build
  docker compose up -d
else
  rebuild_component "$COMPONENT"
fi

echo ""
echo "📊 Service status:"
docker compose ps
