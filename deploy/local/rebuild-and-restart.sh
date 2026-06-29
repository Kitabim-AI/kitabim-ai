#!/bin/bash
set -e

# Quick rebuild and restart for development
# Usage: ./rebuild-and-restart.sh [backend|worker|frontend|all]

COMPONENT=${1:-all}

# Auto-generate secure App ID for all/full deployments
if [ "$COMPONENT" = "all" ]; then
  NEW_APP_ID=$(openssl rand -hex 16)
  echo "🔐 Rotating App ID: $NEW_APP_ID"
  
  # Update local .env — SECURITY_APP_ID is used by both backend and frontend build
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

  # Verify local postgres is reachable
  echo "⏳ Waiting for local postgres to be ready..."
  until pg_isready -h 127.0.0.1 -p 5432 -U kitabim -d kitabim-ai > /dev/null 2>&1; do
    sleep 1
  done
  echo "✅ Postgres ready"

  # Apply all migrations (IF NOT EXISTS guards make these idempotent)
  echo "🗄️  Applying migrations..."
  for f in packages/backend-core/migrations/*.sql; do
    if [[ "$f" == *"rollback"* ]]; then
      continue
    fi
    echo "  → $(basename "$f")"
    psql "postgresql://kitabim:kitabim@127.0.0.1:5432/kitabim-ai" < "$f"
  done

  docker compose up -d
else
  rebuild_component "$COMPONENT"
fi

echo ""
echo "📊 Service status:"
docker compose ps
