#!/bin/bash
set -e

# Quick rebuild and restart for development
# Usage: ./rebuild-and-restart.sh [backend|worker|frontend|all]

COMPONENT=${1:-all}

# Auto-generate secure App ID for all/full deployments
if [ "$COMPONENT" = "all" ]; then
  NEW_APP_ID=$(openssl rand -hex 16)
  echo "🔐 Rotating App ID: $NEW_APP_ID"
  
  # Update frontend config
  sed -i.bak "s/export const APP_CLIENT_ID = '.*';/export const APP_CLIENT_ID = '$NEW_APP_ID';/" apps/frontend/src/config.ts
  rm -f apps/frontend/src/config.ts.bak
  
  # Update local .env (at repo root)
  if [ -f .env ]; then
    sed -i.bak "s/^SECURITY_APP_ID=.*/SECURITY_APP_ID=$NEW_APP_ID/" .env
    rm -f .env.bak
  fi
fi

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
