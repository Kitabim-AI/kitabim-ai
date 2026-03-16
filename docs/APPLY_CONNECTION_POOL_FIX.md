# Fix: Database Connection Pool Exhaustion

## Problem
Production is experiencing `TimeoutError: QueuePool limit of size 15 overflow 10 reached` errors because the connection pool settings are too high for your Cloud SQL instance (50 max_connections).

## Solution Applied
Updated production connection pool settings from 15+10=25 to **5+5=10 per service**.

## Changes Made
- ✅ `deploy/gcp/.env` - Updated `DB_POOL_SIZE=5` and `DB_MAX_OVERFLOW=5`
- ✅ `deploy/gcp/.env.template` - Updated template with documentation

## How to Apply to Production

### Option 1: Rolling Restart (Zero Downtime)
```bash
# SSH into your production server
ssh your-production-server

# Navigate to deployment directory
cd /path/to/kitabim-ai/deploy/gcp

# Pull latest .env changes (or manually copy the updated .env)
# Make sure .env has:
#   DB_POOL_SIZE=5
#   DB_MAX_OVERFLOW=5

# Restart services one at a time
docker-compose restart worker
sleep 10
docker-compose restart backend
```

### Option 2: Full Restart (Brief Downtime)
```bash
# SSH into production server
ssh your-production-server
cd /path/to/kitabim-ai/deploy/gcp

# Stop all services
docker-compose down

# Start with new settings
docker-compose up -d
```

### Option 3: Using Deployment Script
If you have automated deployment scripts:
```bash
# Update .env on production server first
# Then run your normal deployment
./scripts/deploy.sh
```

## Verify the Fix

After restarting, verify the new settings are active:

```bash
# Check backend pool settings
docker exec $(docker ps -q -f name=backend) printenv | grep DB_POOL

# Check worker pool settings
docker exec $(docker ps -q -f name=worker) printenv | grep DB_POOL

# Should output:
# DB_POOL_SIZE=5
# DB_MAX_OVERFLOW=5
```

Monitor logs for the first 10 minutes:
```bash
# Watch for any pool errors (should see none)
docker-compose logs -f backend worker | grep -i "pool\|timeout"
```

## Expected Results

**Before:**
- Pool: 15 + 10 = 25 per service
- Total: 50 connections (100% of Cloud SQL limit)
- Result: Timeouts during traffic spikes

**After:**
- Pool: 5 + 5 = 10 per service
- Total: 20 connections (40% of Cloud SQL limit)
- Result: No timeouts, 60% headroom for bursts

## When to Scale Up

Only increase pool sizes if you see these errors in production logs:
```
QueuePool limit of size 5 overflow 5 reached
```

If that happens, incrementally increase:
```bash
# In deploy/gcp/.env
DB_POOL_SIZE=7
DB_MAX_OVERFLOW=8
# (7+8) * 2 services = 30 total connections
```

## Long-term: Upgrade Cloud SQL

If you consistently need more connections, upgrade your Cloud SQL instance:
- **db-f1-micro**: 25 max_connections
- **db-g1-small**: 50 max_connections
- **db-custom-1-3840**: 100 max_connections
- **db-custom-2-7680**: 250 max_connections

After upgrading to 100+ connections, you can safely use:
```bash
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=10
# (10+10) * 2 services = 40 total connections
```

## Rollback (If Needed)

If you need to rollback (you shouldn't need to):
```bash
# Edit deploy/gcp/.env
DB_POOL_SIZE=15
DB_MAX_OVERFLOW=10

# Restart
docker-compose restart backend worker
```

## Questions?

- Check logs: `docker-compose logs -f backend worker`
- Monitor connections: See main README for connection monitoring query
- Contact: Your DevOps team or create an issue
