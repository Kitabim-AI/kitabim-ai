# Status Refactor Execution Checklist

## 📋 Pre-Migration Phase

### Backup & Preparation
- [ ] Create database backup
  ```bash
  pg_dump -h localhost -U your_user kitabim > backup_pre_refactor_$(date +%Y%m%d_%H%M%S).sql
  ```
- [ ] Record current status counts
  ```bash
  psql -c "SELECT status, COUNT(*) FROM books GROUP BY status;" > pre_migration_books.txt
  psql -c "SELECT status, COUNT(*) FROM pages GROUP BY status;" > pre_migration_pages.txt
  ```
- [ ] Verify no active uploads/processing (or wait for completion)
- [ ] Stop all workers
  ```bash
  kubectl scale deployment worker --replicas=0 -n kitabim
  kubectl get pods -n kitabim | grep worker  # verify 0/0
  ```

---

## 🔄 Migration Phase

### Database Migration
- [ ] Review migration SQL: `docs/STATUS_REFACTOR_MIGRATION.sql`
- [ ] Review rollback SQL: `docs/STATUS_REFACTOR_ROLLBACK.sql`
- [ ] Run migration
  ```bash
  psql -h localhost -U your_user kitabim < docs/STATUS_REFACTOR_MIGRATION.sql
  ```
- [ ] Verify migration output (check for errors)
- [ ] Verify status counts changed correctly

### Post-Migration Verification
- [ ] Check no old statuses remain
  ```bash
  psql -c "SELECT COUNT(*) FROM books WHERE status IN ('processing', 'completed');"  # expect 0
  psql -c "SELECT COUNT(*) FROM pages WHERE status IN ('processing', 'completed');"  # expect 0
  ```
- [ ] Check new statuses exist
  ```bash
  psql -c "SELECT status, COUNT(*) FROM books GROUP BY status;"
  psql -c "SELECT status, COUNT(*) FROM pages GROUP BY status;"
  ```
- [ ] Verify column renamed
  ```bash
  psql -c "\d books" | grep ocr_done_count  # should exist
  psql -c "\d books" | grep completed_count  # should NOT exist
  ```
- [ ] Verify constraints added
  ```bash
  psql -c "SELECT conname FROM pg_constraint WHERE conrelid='books'::regclass AND conname='books_status_check';"
  psql -c "SELECT conname FROM pg_constraint WHERE conrelid='pages'::regclass AND conname='pages_status_check';"
  ```

---

## 💻 Code Changes Phase

### Backend Changes (11 files)

#### Core Models & Schemas
- [ ] **packages/backend-core/app/db/models.py**
  - [ ] Line 83: `completed_count` → `ocr_done_count`
  - [ ] Line 171: Update page status constraint values

- [ ] **packages/backend-core/app/models/schemas.py**
  - [ ] Line 75: `completed_count: int` → `ocr_done_count: int`

#### Services
- [ ] **packages/backend-core/app/services/pdf_service.py**
  - [ ] Phase 0 (L231-235): `"processing"` → `"ocr_processing"`
  - [ ] Phase 1 (L260-404): All `"completed"` → `"ocr_done"`, `"processing"` → `"ocr_processing"`
  - [ ] Phase 2 (L411-end): Add `"indexing"` and `"indexed"` statuses
  - [ ] Final status (L558-601): Update `completed_count` → `ocr_done_count` and job status logic

- [ ] **packages/backend-core/app/services/spell_check_service.py**
  - [ ] L76, L121: `"completed"` → `"ocr_done"`

- [ ] **packages/backend-core/app/services/discovery_service.py**
  - [ ] L169: `"completed"` → `"ocr_done"`

- [ ] **packages/backend-core/app/services/maintenance.py**
  - [ ] L86: Remove `"completed"` from job status check

#### API Endpoints
- [ ] **packages/backend-core/app/api/endpoints/books.py**
  - [ ] L268-L1298: All occurrences of `completed_count` → `ocr_done_count`
  - [ ] All status comparisons: `"completed"` → `"ocr_done"`, `"processing"` → `"ocr_processing"`

- [ ] **packages/backend-core/app/db/repositories/books.py**
  - [ ] L122: `completed_count` → `ocr_done_count`

#### Entry Points
- [ ] **packages/backend-core/app/main.py**
  - [ ] L81: `'completed'` → `'ocr_done'`

#### Utility Scripts
- [ ] **packages/backend-core/fix_book_statuses.py**
  - [ ] **DECISION:** Delete this file OR rewrite for new status names
  - [ ] If keeping: Update all status references

- [ ] **packages/backend-core/diagnose_books.py**
  - [ ] L65: `"processing"` → `"ocr_processing"`
  - [ ] Add reporting for new statuses

### Frontend Changes (15 files)

#### Shared Types
- [ ] **packages/shared/src/types.ts**
  - [ ] Line 5: ExtractionResult status enum - add new statuses
  - [ ] Line 24: Book status enum - add new statuses
  - [ ] Line 34: `completedCount` → `ocrDoneCount`

#### Hooks
- [ ] **apps/frontend/src/hooks/useBookActions.ts**
  - [ ] L232, L239, L310: `'completed'` → `'ocr_done'`

- [ ] **apps/frontend/src/hooks/useBooks.ts**
  - [ ] L24: `'processing'` → `'ocr_processing'`

#### Components
- [ ] **apps/frontend/src/components/admin/ProgressBar.tsx**
  - [ ] L9: `'completed'` → `'ocr_done'`, `completedCount` → `ocrDoneCount`

- [ ] **apps/frontend/src/components/admin/AdminView.tsx**
  - [ ] L262: `completedCount` → `ocrDoneCount`, `'completed'` → `'ocr_done'`

- [ ] **apps/frontend/src/components/admin/StatsPanel.tsx**
  - [ ] L31: Add new status styles (ocr_processing, ocr_done, indexing)
  - [ ] L54: Add new status icon cases
  - [ ] L177: Update bookStatusLabel mappings
  - [ ] L184: Update pageStatusLabel mappings
  - [ ] L320: `'completed'` → `'ocr_done'`

- [ ] **apps/frontend/src/components/admin/ActionMenu.tsx**
  - [ ] L15, L16, L18, L31: `'processing'` → `'ocr_processing'`

- [ ] **apps/frontend/src/components/reader/ReaderView.tsx**
  - [ ] L303: `'processing'` → `'ocr_processing'`

- [ ] **apps/frontend/src/App.tsx**
  - [ ] L28, L31: `'processing'` → `'ocr_processing'`

#### Tests
- [ ] **apps/frontend/src/tests/useBookActions.test.tsx**
  - [ ] L26, L156, L157: `'completed'` → `'ocr_done'`

- [ ] **apps/frontend/src/tests/ReaderView.test.tsx**
  - [ ] L18, L19, L248: `'completed'` → `'ocr_done'`

- [ ] **apps/frontend/src/tests/App.test.tsx**
  - [ ] L87: `'completed'` → `'ocr_done'`

- [ ] **apps/frontend/src/tests/AdminView.test.tsx**
  - [ ] L15, L16, L32: `'completed'` → `'ocr_done'`

- [ ] **apps/frontend/src/tests/LibraryView.test.tsx**
  - [ ] Search and replace all status references

- [ ] **apps/frontend/src/tests/BookCard.test.tsx**
  - [ ] Search and replace all status references

### i18n Changes
- [ ] **apps/frontend/src/locales/en.json**
  - [ ] `admin.stats.completed` → `admin.stats.ocrDone`: "OCR Done (not indexed)"
  - [ ] `admin.stats.bookProcessing` → `admin.stats.bookOcrProcessing`: "OCR Processing"
  - [ ] `admin.stats.pageProcessing` → `admin.stats.pageOcrProcessing`: "OCR Processing"
  - [ ] Add `admin.stats.bookIndexing`: "Indexing"
  - [ ] Add `admin.stats.pageIndexing`: "Indexing"

- [ ] **apps/frontend/src/locales/ug.json**
  - [ ] Same key changes with Uyghur translations

---

## 🧪 Testing Phase

### Code Verification
- [ ] Backend: Search for missed occurrences
  ```bash
  cd packages/backend-core
  grep -rn "status.*=.*['\"]processing['\"]" app/ --include="*.py" | grep -v "processing_step" | grep -v "#"
  grep -rn "status.*=.*['\"]completed['\"]" app/ --include="*.py" | grep -v "#"
  grep -rn "completed_count" app/ --include="*.py"
  ```

- [ ] Frontend: Search for missed occurrences
  ```bash
  cd apps/frontend
  grep -rn "status.*['\"]processing['\"]" src/ --include="*.ts" --include="*.tsx" | grep -v "//"
  grep -rn "status.*['\"]completed['\"]" src/ --include="*.ts" --include="*.tsx" | grep -v "//"
  grep -rn "completedCount" src/ --include="*.ts" --include="*.tsx"
  ```

- [ ] TypeScript compilation
  ```bash
  cd apps/frontend
  npm run type-check
  ```

### Unit Tests
- [ ] Run backend tests
  ```bash
  cd packages/backend-core
  pytest
  ```

- [ ] Run frontend tests
  ```bash
  cd apps/frontend
  npm test
  ```

---

## 🚀 Deployment Phase

### Backend Deployment
- [ ] Deploy backend
  ```bash
  ./rebuild-and-restart.sh backend
  ```
- [ ] Wait for backend pod to be ready
  ```bash
  kubectl get pods -n kitabim -w
  ```
- [ ] Check backend logs for errors
  ```bash
  kubectl logs -f deployment/backend -n kitabim
  ```

### Frontend Deployment
- [ ] Deploy frontend
  ```bash
  ./rebuild-and-restart.sh frontend
  ```
- [ ] Wait for frontend pod to be ready
- [ ] Check frontend loads in browser
- [ ] Check browser console for errors

### Worker Deployment
- [ ] Restart workers
  ```bash
  kubectl scale deployment worker --replicas=1 -n kitabim
  ```
- [ ] Check worker logs
  ```bash
  kubectl logs -f deployment/worker -n kitabim
  ```

---

## ✅ Post-Deployment Verification

### Automated Checks
- [ ] API health check
  ```bash
  curl http://localhost:30800/health
  ```

- [ ] Database status verification
  ```bash
  psql -c "SELECT status, COUNT(*) FROM books GROUP BY status;"
  psql -c "SELECT status, COUNT(*) FROM pages GROUP BY status;"
  ```

### Manual Testing
- [ ] **Upload Flow**
  - [ ] Upload a new PDF book
  - [ ] Verify status starts as `pending`
  - [ ] Watch it change to `ocr_processing`
  - [ ] Verify it becomes `ocr_done` after OCR completes
  - [ ] Verify it becomes `indexing` when embedding starts
  - [ ] Verify it becomes `ready` when fully indexed

- [ ] **Stats Page**
  - [ ] Open Admin → Stats tab
  - [ ] Verify "OCR Processing" shows count correctly
  - [ ] Verify "OCR Done (not indexed)" shows books in ocr_done status
  - [ ] Verify "Indexing" shows count correctly
  - [ ] Verify "Ready" shows fully indexed books

- [ ] **Admin View**
  - [ ] Progress bars calculate correctly
  - [ ] Page counts display correctly
  - [ ] Book actions work (Retry, Reindex, Delete)
  - [ ] Action menu shows correct options based on status

- [ ] **Job Status**
  - [ ] Find a book that finished as `ocr_done` (not fully indexed)
  - [ ] Verify its job shows as `succeeded` (not `failed`)
  - [ ] Check job note says "OCR complete, indexing incomplete"

- [ ] **Error Handling**
  - [ ] Test retry on failed pages
  - [ ] Verify error status still works correctly

- [ ] **Translations**
  - [ ] Switch language to Uyghur
  - [ ] Verify all new status labels show correctly
  - [ ] Switch back to English

---

## 📊 Monitoring Phase (24 hours)

### Continuous Monitoring
- [ ] Monitor backend logs
  ```bash
  kubectl logs -f deployment/backend -n kitabim | grep -i "error\|warning"
  ```

- [ ] Monitor worker logs
  ```bash
  kubectl logs -f deployment/worker -n kitabim | grep -i "error\|warning"
  ```

- [ ] Monitor database for anomalies
  ```bash
  # Run every 4 hours
  psql -c "SELECT status, COUNT(*) FROM books GROUP BY status;"
  ```

### Health Checks (run every 4 hours)
- [ ] Hour 0: Initial deployment ✅
- [ ] Hour 4: First checkpoint
  - [ ] Check error logs
  - [ ] Verify status distribution
  - [ ] Test upload flow

- [ ] Hour 8: Second checkpoint
  - [ ] Check error logs
  - [ ] Verify no regressions

- [ ] Hour 12: Third checkpoint
  - [ ] Check error logs
  - [ ] Verify system stable

- [ ] Hour 24: Final checkpoint
  - [ ] Full manual test suite
  - [ ] Performance check
  - [ ] Declare success ✅

---

## 🔴 Rollback Procedure (If Needed)

### When to Rollback
- Database migration fails
- Critical bugs discovered in first 4 hours
- Data corruption detected
- System instability

### Rollback Steps
1. [ ] Stop workers
   ```bash
   kubectl scale deployment worker --replicas=0 -n kitabim
   ```

2. [ ] Rollback deployments
   ```bash
   # Revert to previous code (git revert or restore from backup)
   git revert HEAD
   ./rebuild-and-restart.sh backend
   ./rebuild-and-restart.sh frontend
   ```

3. [ ] Rollback database
   ```bash
   psql -h localhost -U your_user kitabim < docs/STATUS_REFACTOR_ROLLBACK.sql
   ```

4. [ ] Verify rollback
   ```bash
   psql -c "SELECT status, COUNT(*) FROM books GROUP BY status;"
   ```

5. [ ] Restart workers
   ```bash
   kubectl scale deployment worker --replicas=1 -n kitabim
   ```

6. [ ] Post-mortem
   - [ ] Document what went wrong
   - [ ] Identify root cause
   - [ ] Fix issues before retry

---

## 📝 Sign-off

- [ ] All code changes complete
- [ ] All tests passing
- [ ] Migration successful
- [ ] Deployment successful
- [ ] Manual testing complete
- [ ] 24-hour monitoring complete
- [ ] No critical issues found

**Migration completed by:** ________________

**Date:** ________________

**Notes:**
_________________________________________________________________
_________________________________________________________________
_________________________________________________________________
