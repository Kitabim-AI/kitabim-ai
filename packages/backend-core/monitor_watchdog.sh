#!/bin/bash
# Monitor worker logs with focus on watchdog activity

echo "=============================================================================="
echo "🔍 MONITORING WORKER - WATCHING FOR WATCHDOG BEHAVIOR"
echo "=============================================================================="
echo ""
echo "What to watch for:"
echo "  1️⃣  STARTUP (t=0):     Watchdog enqueues ~30 books"
echo "  2️⃣  CYCLE 2 (t=15min): Watchdog SKIPS books (proves fix works!)"
echo ""
echo "Press Ctrl+C to stop monitoring"
echo "=============================================================================="
echo ""

# Start worker and filter logs for watchdog activity
arq app.worker.WorkerSettings 2>&1 | grep -E "(Watchdog|Rescuing|Skipping|📊|⏸️|🚑|✅|⚠️)" --line-buffered --color=always
