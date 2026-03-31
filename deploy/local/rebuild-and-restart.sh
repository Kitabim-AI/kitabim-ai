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

  # Start postgres first so migrations can run against it
  docker compose up -d postgres
  echo "⏳ Waiting for postgres to be ready..."
  until docker compose exec -T postgres pg_isready -U kitabim -d kitabim-ai > /dev/null 2>&1; do
    sleep 1
  done
  echo "✅ Postgres ready"

  # Apply all migrations (IF NOT EXISTS guards make these idempotent)
  echo "🗄️  Applying migrations..."
  for f in packages/backend-core/migrations/*.sql; do
    echo "  → $(basename "$f")"
    docker compose exec -T postgres psql -U kitabim -d kitabim-ai < "$f"
  done

  docker compose up -d
else
  rebuild_component "$COMPONENT"
fi

echo ""
echo "📊 Service status:"
docker compose ps
