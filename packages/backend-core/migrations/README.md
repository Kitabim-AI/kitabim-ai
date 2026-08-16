# Database Migrations

This directory contains SQL migration scripts for the Kitabim AI database.

## Migration Naming Convention

Migrations follow the pattern: `NNN_description.sql`
- `NNN` = Sequential migration number (e.g., 089)
- `description` = Brief description of the migration

Note: migrations `002`-`033` no longer exist as individual files. They were
squashed into `001_initial_baseline.sql` (a `pg_dump` schema snapshot) on
2026-03-20. The next migration after the baseline is `034`, so numbering
jumps from `001` straight to `034`.

## Running Migrations

### Local Development

```bash
# Run a specific migration on local database
psql -h localhost -p 5432 -U omarjan -d kitabim-ai -f packages/backend-core/migrations/089_remove_dead_system_configs.sql
```

### Production

**Option 1: Using the migration runner script (recommended)**

```bash
# From project root
./scripts/run_migration_prod.sh 089
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
gcloud compute scp packages/backend-core/migrations/089_remove_dead_system_configs.sql \
  kitabim-prod:/tmp/ --zone=us-south1-c

# SSH to production
gcloud compute ssh kitabim-prod --zone=us-south1-c

# Run migration
PGPASSWORD='<password>' psql -h <CLOUD_SQL_PRIVATE_IP> -p 5432 -U kitabim -d kitabim-ai \
  -f /tmp/089_remove_dead_system_configs.sql

# Clean up
rm /tmp/089_remove_dead_system_configs.sql
exit
```

**Option 3: Via Docker container**

```bash
# SSH to production
gcloud compute ssh kitabim-prod --zone=us-south1-c

# Run via backend container
cd /opt/kitabim
docker compose -f deploy/gcp/docker-compose.yml exec backend \
  psql postgresql://kitabim:<password>@<CLOUD_SQL_PRIVATE_IP>:5432/kitabim-ai \
  -f /app/packages/backend-core/migrations/089_remove_dead_system_configs.sql
```

## Recent Migrations

This section is illustrative, not exhaustive — see the directory listing for
the full, current set of migrations.

### 089_remove_dead_system_configs.sql
**Date:** 2026-08-16
**Purpose:** Remove dead `system_configs` rows left over from superseded features

**Rollback:** See `089_rollback_remove_dead_system_configs.sql`

### 088_seed_entity_semantic_matching_config.sql
**Date:** 2026-08-15
**Purpose:** Seed config keys for entity semantic matching (default off)

**Rollback:** See `088_rollback_seed_entity_semantic_matching_config.sql`

### 086_add_aliases_to_history_dictionary.sql
**Date:** 2026-08-09
**Purpose:** Add an `aliases` column to `history_dictionary` for alternate term names

**Rollback:** See `086_rollback_add_aliases_to_history_dictionary.sql`

## Rollback Migrations

Rollback migrations follow the pattern: `NNN_rollback_description.sql`

To rollback a migration:
```bash
# Local
psql -h localhost -p 5432 -U omarjan -d kitabim-ai \
  -f packages/backend-core/migrations/089_rollback_remove_dead_system_configs.sql

# Production
./scripts/run_migration_prod.sh 089_rollback
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

1. Find the latest migration number (note: `ls | tail -1` alone will
   incorrectly return this `README.md` since it sorts after numeric
   filenames — restrict the glob to `*.sql`):
   ```bash
   ls -1 packages/backend-core/migrations/*.sql | tail -1
   ```

2. Create new migration with next number:
   ```bash
   touch packages/backend-core/migrations/090_your_description.sql
   ```

3. Add migration header:
   ```sql
   -- Migration: 090_your_description.sql
   -- Description: What this migration does
   -- Author: Your Name
   -- Date: YYYY-MM-DD

   BEGIN;

   -- Your SQL here

   COMMIT;
   ```

4. If this migration adds/changes a table, follow the repo-wide workflow
   order: migration file first, ORM model second, repository third,
   endpoint last (see project `CLAUDE.md`).

5. Test locally, then run on production

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
