# Status Refactor Plan - Additional Findings

## 🔍 Discovered Missing Files

### 1. Type Definitions

#### [MODIFY] [packages/shared/src/types.ts](file:///Users/Omarjan/Projects/kitabim-ai/packages/shared/src/types.ts)
**Line 5:** ExtractionResult status enum
```typescript
// OLD:
status: 'pending' | 'processing' | 'completed' | 'error';

// NEW:
status: 'pending' | 'ocr_processing' | 'ocr_done' | 'indexing' | 'indexed' | 'error';
```

**Line 24:** Book status enum
```typescript
// OLD:
status: 'uploading' | 'pending' | 'processing' | 'ready' | 'error';

// NEW:
status: 'uploading' | 'pending' | 'ocr_processing' | 'ocr_done' | 'indexing' | 'ready' | 'error';
```

**Line 34:** Book.completedCount field
```typescript
// OLD:
completedCount?: number;

// NEW:
ocrDoneCount?: number;
```

---

### 2. Additional Frontend Files

#### [MODIFY] [apps/frontend/src/components/admin/ActionMenu.tsx](file:///Users/Omarjan/Projects/kitabim-ai/apps/frontend/src/components/admin/ActionMenu.tsx)
- **L15:** `book.status === 'processing'` → `'ocr_processing'`
- **L16:** `book.status === 'processing'` → `'ocr_processing'`
- **L18:** `book.status === 'processing'` → `'ocr_processing'`
- **L31:** `selectedBook.status === 'processing'` → `'ocr_processing'`

#### [MODIFY] [apps/frontend/src/components/reader/ReaderView.tsx](file:///Users/Omarjan/Projects/kitabim-ai/apps/frontend/src/components/reader/ReaderView.tsx)
- **L303:** `page.status === 'processing'` → `'ocr_processing'`
- **L303:** `page.status === 'pending'` → keep as is (pending is still valid)

#### [MODIFY] [apps/frontend/src/App.tsx](file:///Users/Omarjan/Projects/kitabim-ai/apps/frontend/src/App.tsx)
- **L28:** `r.status === 'processing'` → `'ocr_processing'`
- **L31:** `selectedBook.status === 'processing'` → `'ocr_processing'`

#### [MODIFY] [apps/frontend/src/hooks/useBooks.ts](file:///Users/Omarjan/Projects/kitabim-ai/apps/frontend/src/hooks/useBooks.ts)
- **L24:** `b.status === 'processing'` → `'ocr_processing'`

#### [MODIFY] [apps/frontend/src/tests/LibraryView.test.tsx](file:///Users/Omarjan/Projects/kitabim-ai/apps/frontend/src/tests/LibraryView.test.tsx)
Search and replace all:
- `status: 'processing'` → `'ocr_processing'`
- `status: 'completed'` → `'ocr_done'`
- `completedCount` → `ocrDoneCount`

#### [MODIFY] [apps/frontend/src/tests/BookCard.test.tsx](file:///Users/Omarjan/Projects/kitabim-ai/apps/frontend/src/tests/BookCard.test.tsx)
Search and replace all:
- `status: 'processing'` → `'ocr_processing'`
- `status: 'completed'` → `'ocr_done'`
- `completedCount` → `ocrDoneCount`

---

### 3. Additional Backend Files

#### [MODIFY] [packages/backend-core/fix_book_statuses.py](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/fix_book_statuses.py)

**This script needs complete rewrite** - it's currently migrating FROM 'ready' TO 'completed', which is the opposite direction!

**New logic:**
```python
# Line 1: Update docstring
"""Fix book statuses - migrate from old status names to new ones"""

# Line 26: Change where clause
and_(
    Book.status == "completed",  # OLD status
    Page.is_indexed == False
)

# Line 48: Update message
print(f"\nChanging status from 'completed' → 'ocr_done' for these books...")

# Line 56: Update to new status
.values(status="ocr_done", last_updated=datetime.utcnow())

# Line 62: Update success message
print(f"\n✓ Updated {result.rowcount} books to 'ocr_done' status\n")
```

OR, even better, **delete this file entirely** since the migration SQL handles this.

#### [MODIFY] [packages/backend-core/diagnose_books.py](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/diagnose_books.py)
- **L65:** `Book.status == "processing"` → `"ocr_processing"`
- **Add new sections** to show counts for 'ocr_done', 'indexing' statuses

---

## 📋 Database Constraint Analysis

### Books Table
**Current:** No CHECK constraint on `books.status` (found in models.py)
**Action Required:** Add a CHECK constraint in the migration

```sql
-- Add after column rename
ALTER TABLE books ADD CONSTRAINT books_status_check
  CHECK (status IN ('uploading', 'pending', 'ocr_processing', 'ocr_done', 'indexing', 'ready', 'error'));
```

### Pages Table
**Current:** Has CHECK constraint (will be modified per original plan)
**Action:** Already covered in original plan (line 54-57)

---

## 🔄 Complete Rollback Script

```sql
-- STATUS_REFACTOR_ROLLBACK.sql
-- Run this ONLY if you need to rollback the migration
-- WARNING: This should be run BEFORE deploying new code

-- Rollback status values in data
UPDATE books SET status = 'processing' WHERE status = 'ocr_processing';
UPDATE books SET status = 'completed' WHERE status = 'ocr_done';
UPDATE books SET status = 'processing' WHERE status = 'indexing';

UPDATE pages SET status = 'processing' WHERE status = 'ocr_processing';
UPDATE pages SET status = 'completed' WHERE status = 'ocr_done';
UPDATE pages SET status = 'processing' WHERE status = 'indexing';
UPDATE pages SET status = 'completed' WHERE status = 'indexed';

-- Rollback denormalized cache column
ALTER TABLE books RENAME COLUMN ocr_done_count TO completed_count;

-- Rollback page status check constraint
ALTER TABLE pages DROP CONSTRAINT pages_status_check;
ALTER TABLE pages ADD CONSTRAINT pages_status_check
  CHECK (status IN ('pending', 'processing', 'completed', 'error'));

-- Rollback book status check constraint (if added)
ALTER TABLE books DROP CONSTRAINT IF EXISTS books_status_check;
```

---

## ✅ Enhanced Verification Plan

### Pre-Migration Checks
```bash
# Count current status distribution
psql -c "SELECT status, COUNT(*) FROM books GROUP BY status;"
psql -c "SELECT status, COUNT(*) FROM pages GROUP BY status;"

# Backup database
pg_dump -h localhost -U your_user kitabim > backup_pre_refactor_$(date +%Y%m%d_%H%M%S).sql
```

### Post-Migration Automated Checks
```bash
# Verify NO old status values remain
psql -c "SELECT COUNT(*) FROM books WHERE status IN ('processing', 'completed');" # expect 0
psql -c "SELECT COUNT(*) FROM pages WHERE status IN ('processing', 'completed');" # expect 0

# Verify new status values exist
psql -c "SELECT status, COUNT(*) FROM books GROUP BY status;"
psql -c "SELECT status, COUNT(*) FROM pages GROUP BY status;"

# Verify column rename worked
psql -c "SELECT column_name FROM information_schema.columns WHERE table_name='books' AND column_name='ocr_done_count';" # expect 1 row
psql -c "SELECT column_name FROM information_schema.columns WHERE table_name='books' AND column_name='completed_count';" # expect 0 rows

# Verify constraints
psql -c "SELECT conname, consrc FROM pg_constraint WHERE conrelid = 'pages'::regclass AND conname = 'pages_status_check';"
psql -c "SELECT conname, consrc FROM pg_constraint WHERE conrelid = 'books'::regclass AND conname = 'books_status_check';"
```

### Post-Deployment Code Verification
```bash
# Backend: Search for any remaining old status strings (should find ZERO)
cd packages/backend-core
grep -r "status.*=.*['\"]processing['\"]" app/ --include="*.py" | grep -v "# " | grep -v "processing_step"
grep -r "status.*=.*['\"]completed['\"]" app/ --include="*.py" | grep -v "# "
grep -r "completed_count" app/ --include="*.py"

# Frontend: Search for any remaining old status strings (should find ZERO)
cd apps/frontend
grep -r "status.*['\"]processing['\"]" src/ --include="*.ts" --include="*.tsx" | grep -v "//"
grep -r "status.*['\"]completed['\"]" src/ --include="*.ts" --include="*.tsx" | grep -v "//"
grep -r "completedCount" src/ --include="*.ts" --include="*.tsx"

# Shared types: Verify type definitions
grep "status:" packages/shared/src/types.ts
```

### Manual Testing Checklist
- [ ] Upload a new PDF book
- [ ] Watch it progress: `pending` → `ocr_processing` → `ocr_done` → `indexing` → `ready`
- [ ] Verify Stats page shows:
  - "OCR Processing" count (books in ocr_processing)
  - "OCR Done (not indexed)" count (books in ocr_done)
  - "Indexing" count (books in indexing)
  - "Ready" count (books fully indexed)
- [ ] Verify Admin view progress bars calculate correctly
- [ ] Verify a book finishing as `ocr_done` shows job status as `succeeded` (not `failed`)
- [ ] Verify page-level status transitions work correctly
- [ ] Test retry functionality on failed pages
- [ ] Test reindex functionality on ready books
- [ ] Test spell-check on ocr_done pages

---

## 📦 Deployment Sequence

1. **Backup Database**
   ```bash
   pg_dump -h localhost -U your_user kitabim > backup_pre_refactor_$(date +%Y%m%d_%H%M%S).sql
   ```

2. **Stop All Workers** (prevent race conditions)
   ```bash
   kubectl scale deployment worker --replicas=0 -n kitabim
   ```

3. **Run Migration SQL**
   ```bash
   psql -h localhost -U your_user kitabim < migration.sql
   ```

4. **Verify Migration**
   ```bash
   # Run all post-migration automated checks above
   ```

5. **Deploy Backend**
   ```bash
   ./rebuild-and-restart.sh backend
   ```

6. **Deploy Frontend**
   ```bash
   ./rebuild-and-restart.sh frontend
   ```

7. **Restart Workers**
   ```bash
   kubectl scale deployment worker --replicas=1 -n kitabim
   ```

8. **Monitor Logs** (watch for 24h)
   ```bash
   kubectl logs -f deployment/backend -n kitabim
   kubectl logs -f deployment/worker -n kitabim
   ```

---

## 🎯 Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Column rename breaks existing queries | **HIGH** | Grep entire codebase for `completed_count`, comprehensive testing |
| Race condition during migration | **MEDIUM** | Stop workers before migration, use transactions |
| Type errors in frontend | **MEDIUM** | Update shared types first, TypeScript will catch errors |
| Missed status checks in code | **MEDIUM** | Comprehensive grep search, code review |
| Job status logic breaks | **LOW** | Covered in original plan, well-tested section |
| Migration rollback needed | **LOW** | Have rollback script ready, database backup |

---

## 📝 Summary of ALL Files Requiring Changes

### Backend Python (11 files)
1. ✅ models.py
2. ✅ schemas.py
3. ✅ pdf_service.py
4. ✅ books.py (endpoint)
5. ✅ books.py (repository)
6. ✅ spell_check_service.py
7. ✅ discovery_service.py
8. ✅ main.py
9. ✅ maintenance.py
10. ⚠️  **fix_book_statuses.py** (MISSING - needs rewrite or deletion)
11. ⚠️  **diagnose_books.py** (MISSING - needs update)

### Frontend TypeScript (13 files)
1. ✅ useBookActions.ts
2. ✅ ProgressBar.tsx
3. ✅ AdminView.tsx
4. ✅ StatsPanel.tsx
5. ✅ useBookActions.test.tsx
6. ✅ ReaderView.test.tsx
7. ✅ App.test.tsx
8. ✅ AdminView.test.tsx
9. ⚠️  **types.ts** (MISSING - shared types)
10. ⚠️  **ActionMenu.tsx** (MISSING)
11. ⚠️  **ReaderView.tsx** (MISSING)
12. ⚠️  **App.tsx** (MISSING)
13. ⚠️  **useBooks.ts** (MISSING)
14. ⚠️  **LibraryView.test.tsx** (MISSING)
15. ⚠️  **BookCard.test.tsx** (MISSING)

### i18n (2 files)
1. ✅ en.json
2. ✅ ug.json

### Database (1 migration)
1. ✅ migration.sql
2. ⚠️  **books_status_check constraint** (MISSING in original plan)

**Total Files:** 27 files need changes (original plan had 17, found 10 more)

---

## 🚀 Recommendation

The original plan is **85% complete**. Before execution:

1. ✅ Update the plan to include the 10 missing files listed above
2. ✅ Add the `books_status_check` constraint to migration.sql
3. ✅ Decide whether to delete or rewrite `fix_book_statuses.py`
4. ✅ Create the rollback script
5. ✅ Run pre-migration verification
6. ✅ Execute deployment sequence
7. ✅ Run post-migration verification
8. ✅ Manual testing

**Estimated Time:**
- Code changes: 2-3 hours
- Testing: 1-2 hours
- Migration + deployment: 30-45 minutes
- Monitoring: 24 hours

**Total:** ~4-6 hours of active work + 24h monitoring period
