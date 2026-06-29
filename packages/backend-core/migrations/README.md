# Database Migrations

This directory contains SQL migration scripts for the Kitabim AI database.

## Migration Naming Convention

Migrations follow the pattern: `NNN_description.sql`
- `NNN` = Sequential migration number (e.g., 033)
- `description` = Brief description of the migration

## Running Migrations

### Local Development

```bash
# Run a specific migration on local database
psql -h localhost -p 5432 -U omarjan -d kitabim-ai -f packages/backend-core/migrations/033_reset_spell_check_for_new_logic.sql
```

### Production

**Option 1: Using the migration runner script (recommended)**

```bash
# From project root
./scripts/run_migration_prod.sh 033
```

This script will:
- Load production database credentials from `deploy/gcp/.env`
- Show migration preview
- Ask for confirmation
- Run the migration
- Show results

**Option 2: Manual execution**

```bash
# Copy migration to production server
gcloud compute scp packages/backend-core/migrations/033_reset_spell_check_for_new_logic.sql \
  kitabim-prod:/tmp/ --zone=us-south1-c

# SSH to production
gcloud compute ssh kitabim-prod --zone=us-south1-c

# Run migration
PGPASSWORD='<password>' psql -h 10.158.0.5 -p 5432 -U kitabim -d kitabim-ai \
  -f /tmp/033_reset_spell_check_for_new_logic.sql

# Clean up
rm /tmp/033_reset_spell_check_for_new_logic.sql
exit
```

**Option 3: Via Docker container**

```bash
# SSH to production
gcloud compute ssh kitabim-prod --zone=us-south1-c

# Run via backend container
cd /opt/kitabim
docker compose -f deploy/gcp/docker-compose.yml exec backend \
  psql postgresql://kitabim:<password>@10.158.0.5:5432/kitabim-ai \
  -f /app/packages/backend-core/migrations/033_reset_spell_check_for_new_logic.sql
```

## Recent Migrations

### 033_reset_spell_check_for_new_logic.sql
**Date:** 2025-03-16
**Purpose:** Reset spell check data to use new simplified logic

This migration:
- Truncates `page_spell_issues` table (removes all existing issues)
- Resets `spell_check_milestone` to `'idle'` for all processed pages
- Resets book-level spell check milestones

**Reason:** The spell check logic was updated to only create issues for words with OCR corrections in the dictionary, eliminating false positives from rare/valid words.

**Impact:**
- All existing spell check issues deleted
- All pages will be reprocessed
- Only genuine OCR errors will be flagged

**Rollback:** See `033_rollback_reset_spell_check_for_new_logic.sql` (note: cannot restore deleted data)

### 032_cleanup_redundant_indexes.sql
**Date:** 2025-03-15
**Purpose:** Remove redundant database indexes for performance

### 031_add_book_level_milestones.sql
**Date:** 2025-03-15
**Purpose:** Add book-level milestone tracking columns

## Rollback Migrations

Rollback migrations follow the pattern: `NNN_rollback_description.sql`

To rollback a migration:
```bash
# Local
psql -h localhost -p 5432 -U omarjan -d kitabim-ai \
  -f packages/backend-core/migrations/033_rollback_reset_spell_check_for_new_logic.sql

# Production
./scripts/run_migration_prod.sh 033_rollback
```

**Important:** Not all migrations can be rolled back. Some operations (like `TRUNCATE`) are irreversible. Always check the rollback script comments for limitations.

## Best Practices

1. **Always test locally first** before running on production
2. **Backup production database** before major migrations
3. **Use transactions** (BEGIN/COMMIT) to ensure atomicity
4. **Add comments** explaining the purpose and impact
5. **Create rollback scripts** when possible
6. **Use RAISE NOTICE** to show progress and results
7. **Check migration number** to avoid conflicts (use next sequential number)

## Creating New Migrations

1. Find the latest migration number:
   ```bash
   ls -1 packages/backend-core/migrations/ | tail -1
   ```

2. Create new migration with next number:
   ```bash
   touch packages/backend-core/migrations/034_your_description.sql
   ```

3. Add migration header:
   ```sql
   -- Migration: 034_your_description.sql
   -- Description: What this migration does
   -- Author: Your Name
   -- Date: YYYY-MM-DD

   BEGIN;

   -- Your SQL here

   COMMIT;
   ```

4. Test locally, then run on production

## Troubleshooting

**Migration fails partway through:**
- If wrapped in `BEGIN/COMMIT`, changes are automatically rolled back
- Check error message for specific issue
- Fix and re-run

**Migration already run:**
- Migrations are not tracked automatically
- Keep a log of which migrations have been applied
- Consider adding a `schema_migrations` tracking table

**Permission errors:**
- Ensure database user has necessary permissions
- Some operations (like `TRUNCATE`) require table ownership
