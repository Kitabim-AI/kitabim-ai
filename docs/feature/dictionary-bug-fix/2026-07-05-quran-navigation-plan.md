# Quran Navigation and Data Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a dedicated table to store Quran verses in English, Arabic, and Uyghur, add a populating script, expose FastAPI endpoints, and integrate a high-fidelity Quran reader page into the React web app.

**Architecture:** Create a flat `quran` table in PostgreSQL. Expose read/search endpoints through FastAPI. Build a React page replicating the UX style of the `ProverbsPanel` using 114 Surah pills to select surahs and display verses in high quality.

**Tech Stack:** React 19, Vite, Tailwind CSS, FastAPI, SQLAlchemy, PostgreSQL, Python.

## Global Constraints
- monorepo structure must be kept intact.
- Docker Compose for local dev and testing.
- PostgreSQL runs as a standalone service on host machine (localhost:5432).
- All changes must be verified against current active code and verified using manual/automated tests.

---

### Task 1: Database Schema & Migration

**Files:**
- Create: `packages/backend-core/migrations/067_create_quran_table.sql`
- Create: `packages/backend-core/migrations/067_rollback_create_quran_table.sql`
- Modify: `packages/backend-core/app/db/models.py`

**Interfaces:**
- Produces: `app.db.models.Quran` SQLAlchemy class

- [ ] **Step 1: Write SQL migration file**
  Create `packages/backend-core/migrations/067_create_quran_table.sql` with:
  ```sql
  -- Migration: 067_create_quran_table.sql
  -- Description: Create quran table for storing Surahs and Ayahs
  -- Author: Omarjan
  -- Date: 2026-07-05

  BEGIN;

  CREATE TABLE IF NOT EXISTS public.quran (
      id            SERIAL PRIMARY KEY,
      surah         INTEGER NOT NULL,
      surah_name_en VARCHAR(255) NOT NULL,
      surah_name_ar VARCHAR(255) NOT NULL,
      surah_name_ug VARCHAR(255) NOT NULL,
      ayah          INTEGER NOT NULL,
      text_ar       TEXT NOT NULL,
      text_en       TEXT NOT NULL,
      text_ug       TEXT NOT NULL,
      created_at    TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
  );

  CREATE INDEX IF NOT EXISTS idx_quran_surah ON public.quran (surah);
  CREATE UNIQUE INDEX IF NOT EXISTS idx_quran_surah_ayah ON public.quran (surah, ayah);

  CREATE INDEX IF NOT EXISTS idx_quran_text_ug_trgm ON public.quran USING gin (text_ug public.gin_trgm_ops);
  CREATE INDEX IF NOT EXISTS idx_quran_text_en_trgm ON public.quran USING gin (text_en public.gin_trgm_ops);
  CREATE INDEX IF NOT EXISTS idx_quran_text_ar_trgm ON public.quran USING gin (text_ar public.gin_trgm_ops);

  COMMIT;
  ```

- [ ] **Step 2: Write SQL rollback file**
  Create `packages/backend-core/migrations/067_rollback_create_quran_table.sql` with:
  ```sql
  -- Rollback: 067_rollback_create_quran_table.sql
  -- Description: Drop quran table
  -- Author: Omarjan
  -- Date: 2026-07-05

  BEGIN;
  DROP TABLE IF EXISTS public.quran CASCADE;
  COMMIT;
  ```

- [ ] **Step 3: Run the SQL migration on local DB**
  Run: `psql -h localhost -p 5432 -U omarjan -d kitabim-ai -f packages/backend-core/migrations/067_create_quran_table.sql`
  Expected: Command runs successfully, creating the table and indexes.

- [ ] **Step 4: Update SQLAlchemy models file**
  Modify `packages/backend-core/app/db/models.py` by adding the `Quran` class.
  Add import for `String` if not already present.
  ```python
  class Quran(Base):
      """Quran model for Uyghur, English and Arabic verses (ayahs)"""

      __tablename__ = "quran"

      id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
      surah: Mapped[int] = mapped_column(Integer, nullable=False)
      surah_name_en: Mapped[str] = mapped_column(String(255), nullable=False)
      surah_name_ar: Mapped[str] = mapped_column(String(255), nullable=False)
      surah_name_ug: Mapped[str] = mapped_column(String(255), nullable=False)
      ayah: Mapped[int] = mapped_column(Integer, nullable=False)
      text_ar: Mapped[str] = mapped_column(Text, nullable=False)
      text_en: Mapped[str] = mapped_column(Text, nullable=False)
      text_ug: Mapped[str] = mapped_column(Text, nullable=False)

      created_at: Mapped[datetime] = mapped_column(
          DateTime(timezone=True),
          default=func.now(),
          server_default=func.now(),
          nullable=False,
      )
  ```

- [ ] **Step 5: Run tests to verify model loading**
  Run: `pytest packages/backend-core/tests/ -v` (verify no regressions on model imports)
  Expected: All tests pass.

- [ ] **Step 6: Commit**
  ```bash
  git add packages/backend-core/migrations/067_create_quran_table.sql packages/backend-core/migrations/067_rollback_create_quran_table.sql packages/backend-core/app/db/models.py
  git commit -m "feat: create database table and model for Quran data"
  ```

---

### Task 2: Quran Data Populating Script

**Files:**
- Create: `scripts/populate_quran.py`

**Interfaces:**
- Consumes: JSON files in `/Users/Omarjan/Projects/uyghur-language/uyghur-language.github.io/quran/data/surah`
- Produces: Data in the `quran` table

- [ ] **Step 1: Write the populating script**
  Create `scripts/populate_quran.py` with:
  ```python
  import os
  import json
  import asyncio
  import sys
  import argparse
  from sqlalchemy.dialects.postgresql import insert

  # Ensure app imports resolve correctly
  sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../packages/backend-core")))

  from app.db import session as db_session
  from app.db.models import Quran
  from app.utils import circuit_breaker

  async def import_quran(data_dir: str):
      if not os.path.exists(data_dir):
          print(f"Error: Directory {data_dir} does not exist.")
          return
          
      print(f"Reading files from: {data_dir}")
      
      json_files = []
      for filename in os.listdir(data_dir):
          if filename.endswith(".json") and filename[:-5].isdigit():
              json_files.append(filename)
              
      json_files.sort(key=lambda x: int(x[:-5]))
      
      if not json_files:
          print("No numeric JSON files found in directory.")
          return

      all_ayahs = []
      for filename in json_files:
          filepath = os.path.join(data_dir, filename)
          with open(filepath, "r", encoding="utf-8") as f:
              try:
                  ayahs = json.load(f)
                  all_ayahs.extend(ayahs)
              except Exception as e:
                  print(f"Failed to parse {filename}: {e}")
                  
      print(f"Loaded {len(all_ayahs)} total ayahs to import.")
      
      print("Initializing database connection...", flush=True)
      await db_session.init_db()
      
      batch_size = 500
      try:
          async with db_session.async_session_factory() as session:
              for i in range(0, len(all_ayahs), batch_size):
                  batch = all_ayahs[i:i+batch_size]
                  
                  insert_data = [
                      {
                          "surah": entry["surah"],
                          "surah_name_en": entry["surah_name_en"],
                          "surah_name_ar": entry["surah_name_ar"],
                          "surah_name_ug": entry["surah_name_ug"],
                          "ayah": entry["ayah"],
                          "text_ar": entry["text_ar"],
                          "text_en": entry["text_en"],
                          "text_ug": entry["text_ug"],
                      }
                      for entry in batch
                  ]
                  
                  stmt = insert(Quran).values(insert_data)
                  stmt = stmt.on_conflict_do_update(
                      index_elements=["surah", "ayah"],
                      set_={
                          "surah_name_en": stmt.excluded.surah_name_en,
                          "surah_name_ar": stmt.excluded.surah_name_ar,
                          "surah_name_ug": stmt.excluded.surah_name_ug,
                          "text_ar": stmt.excluded.text_ar,
                          "text_en": stmt.excluded.text_en,
                          "text_ug": stmt.excluded.text_ug,
                      }
                  )
                  
                  await session.execute(stmt)
                  await session.commit()
                  print(f"Processed batch {i // batch_size + 1}/{(len(all_ayahs) + batch_size - 1) // batch_size}", flush=True)
                  
          print("Quran import completed successfully!", flush=True)
      except Exception as e:
          print(f"Error during import: {e}", flush=True)
      finally:
          await db_session.close_db()
          if hasattr(circuit_breaker, "_redis_client") and circuit_breaker._redis_client is not None:
              await circuit_breaker._redis_client.aclose()

  if __name__ == "__main__":
      parser = argparse.ArgumentParser(description="Import Quran JSON data to DB")
      parser.add_argument(
          "--dir", 
          type=str, 
          default="/Users/Omarjan/Projects/uyghur-language/uyghur-language.github.io/quran/data/surah",
          help="Path to the directory containing Quran JSON files"
      )
      args = parser.parse_args()
      asyncio.run(import_quran(args.dir))
  ```

- [ ] **Step 2: Run the script to import data**
  Run: `python scripts/populate_quran.py`
  Expected: Prints progress of processing batches and "Quran import completed successfully!" with 6236 ayahs loaded.

- [ ] **Step 3: Commit**
  ```bash
  git add scripts/populate_quran.py
  git commit -m "feat: add quran database population script"
  ```

---

### Task 3: Backend API Router

**Files:**
- Create: `services/backend/api/endpoints/quran_router.py`
- Create: `services/backend/tests/api/endpoints/quran_router_test.py`
- Modify: `services/backend/api/endpoints/__init__.py`
- Modify: `services/backend/main.py`

**Interfaces:**
- Consumes: `app.db.models.Quran` SQLAlchemy class
- Produces: JSON API endpoints: `/api/quran/surahs`, `/api/quran/stats`, `/api/quran/search`, and `/api/quran`

- [ ] **Step 1: Write the router code**
  Create `services/backend/api/endpoints/quran_router.py` containing the schema and FastAPI get routes for listing, stats, searching, and filtering Quran verses. (Code detailed in spec, uses `Quran` DB model).

- [ ] **Step 2: Export router in api/endpoints/__init__.py**
  Add `quran_router` to imports and `__all__` list in `services/backend/api/endpoints/__init__.py`.

- [ ] **Step 3: Include router in backend/main.py**
  Add import:
  ```python
  from services.backend.api.endpoints import quran_router
  ```
  Add app inclusion:
  ```python
  app.include_router(quran_router.router, prefix="/api", tags=["quran"])
  ```

- [ ] **Step 4: Create units tests for router**
  Create `services/backend/tests/api/endpoints/quran_router_test.py` with mock-based unit tests matching the pattern in `books_router_test.py`:
  ```python
  import sys
  from pathlib import Path
  import pytest
  from unittest.mock import AsyncMock, MagicMock, patch

  BACKEND_DIR = str(Path(__file__).resolve().parents[3])
  BACKEND_CORE_DIR = str(
      Path(__file__).resolve().parents[5] / "packages" / "backend-core"
  )

  def setup_paths():
      for m in list(sys.modules.keys()):
          if m == "api" or m.startswith("api."):
              del sys.modules[m]
      for p in [BACKEND_CORE_DIR, BACKEND_DIR]:
          if p in sys.path:
              sys.path.remove(p)
          sys.path.insert(0, p)

  @pytest.mark.asyncio
  async def test_list_surahs():
      setup_paths()
      from api.endpoints.quran_router import list_surahs
      
      mock_session = AsyncMock()
      
      # Mock the database execute output
      mock_res = MagicMock()
      mock_res.all.return_value = [
          (1, "Al-Fatihah", "الفاتحة", "ئالفاتىھە"),
          (2, "Al-Baqarah", "البقرة", "ئالباقارە")
      ]
      mock_session.execute.return_value = mock_res
      
      result = await list_surahs(session=mock_session)
      
      assert len(result) == 2
      assert result[0].surah == 1
      assert result[0].surah_name_ug == "ئالفاتىھە"
      assert result[1].surah_name_en == "Al-Baqarah"
  ```

- [ ] **Step 5: Run tests**
  Run: `pytest services/backend/tests/api/endpoints/quran_router_test.py -v`
  Expected: PASS

- [ ] **Step 6: Commit**
  ```bash
  git add services/backend/api/endpoints/quran_router.py services/backend/tests/api/endpoints/quran_router_test.py services/backend/api/endpoints/__init__.py services/backend/main.py
  git commit -m "feat: implement and unit-test backend API router for Quran"
  ```

---

### Task 4: Frontend App Setup & Navigation

**Files:**
- Modify: `apps/frontend/src/context/AppContext.tsx`
- Modify: `apps/frontend/src/App.tsx`
- Modify: `apps/frontend/src/components/layout/Navbar.tsx`
- Modify: `apps/frontend/src/locales/en.json`
- Modify: `apps/frontend/src/locales/ug.json`

**Interfaces:**
- Exposes: Navigation option to switch to `quran` view, routing `/quran`, and new localization keys.

- [ ] **Step 1: Extend AppContext view state**
  In `apps/frontend/src/context/AppContext.tsx`:
  - Add `'quran'` to allowed `view` values inside `AppContextType` (lines 9-12).
  - Add `'quran'` to states inside `parsePath` (resolve `/quran` to view `'quran'`).
  - Add `quran` view to path configuration in `getPathFromView`.

- [ ] **Step 2: Render QuranView in App.tsx**
  In `apps/frontend/src/App.tsx`:
  - Import `QuranView`:
    ```typescript
    import QuranView from './components/pages/QuranView';
    ```
  - Render the component inside the `<Shell>` container:
    ```typescript
    {view === 'quran' && <QuranView />}
    ```

- [ ] **Step 3: Update Navbar.tsx navigation list**
  In `apps/frontend/src/components/layout/Navbar.tsx`:
  - Add Quran navigation button right below `dictionary`:
    ```tsx
    <NavButton
      active={view === 'quran'}
      onClick={() => { setSearchQuery(''); setView('quran'); }}
      icon={<BookOpen size={20} strokeWidth={2.5} />}
      label={t('nav.quran')}
    />
    ```
  - Repeat the navigation entry inside the Mobile Nav list (around line 217).

- [ ] **Step 4: Update translation locales**
  - Add `"quran": "Quran"` in `en.json` under `"nav"`.
  - Add `"quran": "قۇرئان"` in `ug.json` under `"nav"`.
  - Add `"quran"` objects in both translation files to define titles/placeholders:
    - **en.json**:
      ```json
      "quran": {
        "title": "Holy Quran",
        "searchPlaceholder": "Search Quran...",
        "ayahNotFound": "No verses found.",
        "totalVerses": "{count} Verses",
        "ayahSuffix": "-ayah"
      }
      ```
    - **ug.json**:
      ```json
      "quran": {
        "title": "قۇرئان كەرىم",
        "searchPlaceholder": "قۇرئاندىن ئىزدەش...",
        "ayahNotFound": "ئايەت تېپىلمىدى.",
        "totalVerses": "{count} ئايەت",
        "ayahSuffix": "-ئايەت"
      }
      ```

- [ ] **Step 5: Commit**
  ```bash
  git add apps/frontend/src/context/AppContext.tsx apps/frontend/src/App.tsx apps/frontend/src/components/layout/Navbar.tsx apps/frontend/src/locales/en.json apps/frontend/src/locales/ug.json
  git commit -m "feat: configure navigation routing and translations for Quran page"
  ```

---

### Task 5: Quran UI Page Component

**Files:**
- Create: `apps/frontend/src/components/pages/QuranView.tsx`

**Interfaces:**
- Consumes: `/api/quran/surahs`, `/api/quran`, `/api/quran/search` API endpoints
- Exposes: Fully functioning, beautiful Quran reader page

- [ ] **Step 1: Write QuranView.tsx**
  Create `apps/frontend/src/components/pages/QuranView.tsx`.
  The file should fetch Surahs and display them as pills, fetch ayahs for the selected Surah, display Arabic text in a gorgeous, large Arabic font, and show translation cards under the search box.
  Make sure to replicate the UI styles (like `.glass-panel`, `.uyghur-text`) and classes from `ProverbsPanel.tsx`.
  Include infinite-scroll loading for verses if needed, but since a surah has at most 286 verses, we can load them all in a single query with limit=300 for a smooth reading experience.

- [ ] **Step 2: Verify compilation**
  Run local build or dev checking to ensure Vite builds typescript files successfully without errors.
  Command: `npm run build` or inspect using local development server.

- [ ] **Step 3: Commit**
  ```bash
  git add apps/frontend/src/components/pages/QuranView.tsx
  git commit -m "feat: implement high-fidelity Quran page component"
  ```
