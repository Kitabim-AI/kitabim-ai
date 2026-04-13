# VM Monitoring Guide
**VM:** kitabim-prod (us-south1-c, e2-standard-2)
**IP:** 34.174.120.98

## Quick Access

### SSH into VM
```bash
gcloud compute ssh kitabim-prod --zone=us-south1-c

# Or with direct SSH (if configured)
ssh kitabim-prod
```

---

## 📊 Real-Time Monitoring

### 1. **Check All Services Status**
```bash
ssh kitabim-prod "cd /opt/kitabim-ai && docker-compose ps"
```

**Expected output:**
```
NAME       IMAGE                          STATUS    PORTS
backend    kitabim-backend:latest         Up        8000/tcp
worker     kitabim-worker:latest          Up
redis      redis:7-alpine                 Up        6379/tcp
frontend   kitabim-frontend:latest        Up        80/tcp
nginx      nginx:1.27-alpine              Up        0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
```

---

### 2. **Monitor Resource Usage (Live)**
```bash
# Real-time stats for all containers
ssh kitabim-prod "docker stats"

# Watch specific container
ssh kitabim-prod "docker stats worker"
```

**What to look for:**
- **Worker memory:** Should stay < 1GB (limit is 1GB)
- **Backend memory:** Should stay < 1GB
- **Redis memory:** Should stay < 512MB
- **CPU %:** Spikes during OCR/embedding are normal

**Example output:**
```
CONTAINER   CPU %   MEM USAGE/LIMIT   MEM %   NET I/O       BLOCK I/O
worker      45%     650MB/1GB         65%     1.2MB/500KB   10MB/5MB
backend     12%     320MB/1GB         32%     5MB/3MB       2MB/1MB
redis       5%      180MB/512MB       35%     500KB/400KB   1MB/500KB
```

---

### 3. **Worker Pipeline Health**

#### Check Worker Logs (Last 50 lines)
```bash
ssh kitabim-prod "docker logs --tail 50 worker"
```

#### Follow Worker Logs (Real-time)
```bash
ssh kitabim-prod "docker logs -f worker"
```

**What to look for:**
- ✅ `"OCR job started"` → Jobs are being processed
- ✅ `"OCR job completed"` → Jobs finishing successfully
- ✅ `"embedding job started"` → Embedding pipeline active
- ⚠️ `"failed"` or `"error"` → Check error messages

#### Check Specific Pipeline Step
```bash
# OCR scanner activity
ssh kitabim-prod "docker logs --tail 100 worker | grep 'OCR scanner'"

# Embedding progress
ssh kitabim-prod "docker logs --tail 100 worker | grep 'embedding job'"

# Job queue status
ssh kitabim-prod "docker logs --tail 100 worker | grep 'dispatched'"
```

---

### 4. **Redis Queue Monitoring**

#### Check Job Queue Depth
```bash
# How many jobs are waiting?
ssh kitabim-prod "docker exec redis redis-cli LLEN arq:queue:default"

# Should be: 0-10 (healthy), >50 (backlog building up)
```

#### Check Active Jobs
```bash
# How many jobs are currently running?
ssh kitabim-prod "docker exec redis redis-cli KEYS 'arq:job:*' | wc -l"

# Should be: 0-4 (based on QUEUE_MAX_JOBS=2 × workers)
```

#### Check Cache Hit Rate
```bash
ssh kitabim-prod "docker exec redis redis-cli INFO stats | grep keyspace"

# Look for:
# keyspace_hits:1234
# keyspace_misses:567
# Hit rate = hits/(hits+misses) → Should be >70%
```

---

### 5. **Database Health**

#### Check Active Connections (from VM)
```bash
ssh kitabim-prod "docker exec backend psql \$DATABASE_URL -c \"SELECT count(*) as active_connections FROM pg_stat_activity WHERE state = 'active';\""

# Should be: <20 (healthy), >40 (approaching limit)
```

#### Check for Long-Running Queries
```bash
ssh kitabim-prod "docker exec backend psql \$DATABASE_URL -c \"SELECT pid, now() - query_start as duration, query FROM pg_stat_activity WHERE state = 'active' AND query NOT LIKE '%pg_stat_activity%' ORDER BY duration DESC LIMIT 5;\""
```

---

### 6. **Application Metrics**

#### Health Check Endpoint
```bash
# Backend health
curl https://kitabim.ai/api/health

# Expected: {"status": "healthy"}
```

#### Check Pipeline Processing Stats
```bash
# Via API (requires admin auth token)
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://kitabim.ai/api/stats/

# Returns pipeline statistics across all books and pages
```

---

## 🚨 Alert Thresholds

### Memory Alerts
```bash
# Check if any container is above 80% memory
ssh kitabim-prod "docker stats --no-stream --format '{{.Name}}: {{.MemPerc}}'"

# If worker >80%: Consider reducing QUEUE_MAX_JOBS or MAX_PARALLEL_PAGES
# If backend >80%: Check for memory leaks
# If redis >80%: Increase maxmemory or reduce cache TTL
```

### Disk Space Alerts
```bash
# Check VM disk usage
ssh kitabim-prod "df -h | grep -E '^/dev/'"

# Check Docker volumes
ssh kitabim-prod "docker system df"

# If >80% full:
# docker system prune -a  # Remove unused images/containers
```

### Queue Depth Alerts
```bash
# Alert if queue depth >50
QUEUE_DEPTH=$(ssh kitabim-prod "docker exec redis redis-cli LLEN arq:queue:default")
if [ "$QUEUE_DEPTH" -gt 50 ]; then
  echo "ALERT: Queue backlog detected ($QUEUE_DEPTH jobs)"
fi
```

---

## 📈 Performance Monitoring (After Optimizations)

### Compare Before/After Pipeline Speed

#### Method 1: Check Logs for Processing Time
```bash
# Find OCR job completion times
ssh kitabim-prod "docker logs worker | grep 'OCR job completed' | tail -10"

# Expected format:
# {"timestamp": "...", "message": "OCR job completed", "book_id": "abc123", "page_count": 300}
```

#### Method 2: Database Query for Pipeline Stats
```bash
# Average time from upload to ready (last 10 books)
ssh kitabim-prod "docker exec backend psql \$DATABASE_URL -c \"
  SELECT
    title,
    EXTRACT(EPOCH FROM (last_updated - upload_date))/60 as minutes_to_ready,
    total_pages,
    status
  FROM books
  WHERE status = 'ready'
    AND upload_date > NOW() - INTERVAL '7 days'
  ORDER BY upload_date DESC
  LIMIT 10;
\""
```

### Expected Results After Optimization
- **Before:** 300-page book = ~38 minutes
- **After:** 300-page book = ~15 minutes
- **Target:** 50-60% reduction in processing time

---

## 🔧 Common Monitoring Commands (Cheat Sheet)

```bash
# Save this as ~/monitor-kitabim.sh

#!/bin/bash
VM="kitabim-prod"
ZONE="us-south1-c"

echo "=== Container Status ==="
gcloud compute ssh $VM --zone=$ZONE --command "docker-compose -f /opt/kitabim-ai/docker-compose.yml ps"

echo -e "\n=== Resource Usage ==="
gcloud compute ssh $VM --zone=$ZONE --command "docker stats --no-stream"

echo -e "\n=== Job Queue Depth ==="
gcloud compute ssh $VM --zone=$ZONE --command "docker exec redis redis-cli LLEN arq:queue:default"

echo -e "\n=== Recent Worker Activity (last 20 lines) ==="
gcloud compute ssh $VM --zone=$ZONE --command "docker logs --tail 20 worker"

echo -e "\n=== Disk Usage ==="
gcloud compute ssh $VM --zone=$ZONE --command "df -h | grep -E '^/dev/'"

echo -e "\n=== Backend Health ==="
curl -s https://kitabim.ai/api/health | jq .
```

**Usage:**
```bash
chmod +x ~/monitor-kitabim.sh
./monitor-kitabim.sh
```

---

## 🔍 Troubleshooting Common Issues

### Worker Not Processing Books
```bash
# 1. Check if worker is running
ssh kitabim-prod "docker ps | grep worker"

# 2. Check worker logs for errors
ssh kitabim-prod "docker logs --tail 100 worker | grep -i error"

# 3. Restart worker if needed
ssh kitabim-prod "cd /opt/kitabim-ai && docker-compose restart worker"
```

### High Memory Usage
```bash
# 1. Identify the culprit
ssh kitabim-prod "docker stats --no-stream | sort -k7 -h"

# 2. Check worker job count
ssh kitabim-prod "docker exec redis redis-cli KEYS 'arq:job:*' | wc -l"

# 3. Reduce QUEUE_MAX_JOBS if needed
ssh kitabim-prod "nano /opt/kitabim-ai/.env"
# Change: QUEUE_MAX_JOBS=2  (or even 1)
ssh kitabim-prod "cd /opt/kitabim-ai && docker-compose restart worker"
```

### Jobs Stuck in Queue
```bash
# 1. Check queue depth
ssh kitabim-prod "docker exec redis redis-cli LLEN arq:queue:default"

# 2. Check if jobs are failing
ssh kitabim-prod "docker logs --tail 50 worker | grep -i failed"

# 3. Check for stale jobs (in-progress for >2 hours)
ssh kitabim-prod "docker exec backend psql \$DATABASE_URL -c \"
  SELECT book_id, page_number, ocr_milestone, last_updated
  FROM pages
  WHERE ocr_milestone = 'in_progress'
    AND last_updated < NOW() - INTERVAL '2 hours';
\""
```

---

## 📱 Setting Up Alerts (Optional)

### GCP Cloud Monitoring

1. **Create Alert Policy:**
   ```bash
   # VM CPU >80%
   gcloud alpha monitoring policies create \
     --notification-channels=CHANNEL_ID \
     --display-name="Kitabim VM High CPU" \
     --condition-threshold-value=80 \
     --condition-threshold-duration=300s
   ```

2. **Email Notifications:**
   - Go to: https://console.cloud.google.com/monitoring
   - Create notification channel (your email)
   - Attach to alert policies

---

## 🎯 Daily Monitoring Routine

### Morning Check (2 minutes)
```bash
# Quick health check
curl https://kitabim.ai/api/health
ssh kitabim-prod "docker stats --no-stream"
ssh kitabim-prod "docker exec redis redis-cli LLEN arq:queue:default"
```

### Weekly Deep Dive (10 minutes)
```bash
# Full monitoring script
./monitor-kitabim.sh

# Check logs for patterns
ssh kitabim-prod "docker logs --since 7d worker | grep -c 'OCR job completed'"

# Database health
ssh kitabim-prod "docker exec backend psql \$DATABASE_URL -c \"
  SELECT
    status,
    COUNT(*) as count
  FROM books
  GROUP BY status;
\""
```

---

*Created: 2026-03-14*
*VM: kitabim-prod (34.174.120.98)*
