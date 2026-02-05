#!/bin/bash
timestamp=$(date +%Y%m%d_%H%M%S)
backup_dir="data/backups/backup_$timestamp"

# Create parent directory if it doesn't exist
mkdir -p "data/backups"

echo "Starting backup of kitabim_ai_db..."
echo "Destination: $backup_dir"

mongodump --uri="mongodb://localhost:27017" --db="kitabim_ai_db" --out="$backup_dir"

if [ $? -eq 0 ]; then
    echo "Backup completed successfully."
else
    echo "Backup failed!"
    exit 1
fi
