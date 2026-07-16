# Quran Navigation and Data Storage Design Spec

This document describes the database design, data importing process, API endpoints, and frontend user interface for the Quran feature in Kitabim.AI.

## 1. Objectives

- Create a dedicated database table `quran` in PostgreSQL to store Quran verses (ayahs) in English, Arabic, and Uyghur.
- Provide a CLI python script to import/upsert local JSON files into the new `quran` table.
- Create backend API endpoints to list Surahs, fetch ayahs for a chosen Surah, and search across all verses.
- Add a new "Quran" page in the frontend navigation using the proverbs panel as a template.
- Implement the page with Surah pills for quick selection and high-fidelity rendering of verses in Arabic, Uyghur, and English.

## 2. Database Schema & Migration

### Migration File: `067_create_quran_table.sql`
A SQL migration to create the table and optimize queries using indices:

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

-- Index for searching ayahs by surah
CREATE INDEX IF NOT EXISTS idx_quran_surah ON public.quran (surah);

-- Compound unique constraint for surah & ayah to prevent duplicate verses
CREATE UNIQUE INDEX IF NOT EXISTS idx_quran_surah_ayah ON public.quran (surah, ayah);

-- GIN trigram indices for searching texts in multiple languages
CREATE INDEX IF NOT EXISTS idx_quran_text_ug_trgm ON public.quran USING gin (text_ug public.gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_quran_text_en_trgm ON public.quran USING gin (text_en public.gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_quran_text_ar_trgm ON public.quran USING gin (text_ar public.gin_trgm_ops);

COMMIT;
```

### Rollback File: `067_rollback_create_quran_table.sql`
```sql
BEGIN;
DROP TABLE IF EXISTS public.quran CASCADE;
COMMIT;
```

### SQLAlchemy Model: `app.db.models.Quran`
Add the model definition to `packages/backend-core/app/db/models.py`:

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

## 3. Data Import Script

Create the Python script at `scripts/populate_quran.py` to import local JSON surah files:

- Defaults to source directory `/Users/Omarjan/Projects/uyghur-language/uyghur-language.github.io/quran/data/surah`.
- Batch parses and upserts verses using `on_conflict_do_update`.

## 4. Backend API Router

Create `services/backend/api/endpoints/quran_router.py` containing:

- `GET /api/quran/surahs`: Return a list of all distinct 114 Surahs with names.
- `GET /api/quran/stats`: Return total ayah count in DB (or count for a single Surah).
- `GET /api/quran/search?q=...`: Substring/trigram-based verse search.
- `GET /api/quran?surah=X&skip=Y&limit=Z`: Returns verses list.

Include and map the new router in `services/backend/api/endpoints/__init__.py` and `services/backend/main.py`.

## 5. Frontend Integration

### Context Updates (`AppContext.tsx`)
Extend allowed views:
```typescript
view: 'home' | 'library' | 'admin' | 'reader' | 'global-chat' | 'join-us' | 'spell-check' | 'graph' | 'dictionary' | 'quran';
```

### Translations (`en.json`, `ug.json`)
Add `"quran"` under `"nav"`, and a new `"quran"` section to hold titles and search placeholders.

### Navigation Navbar (`Navbar.tsx`)
Add a new public navigation item using Lucide `BookOpen` icon, linking to the `quran` view.

### UI Component (`QuranView.tsx`)
Create `apps/frontend/src/components/pages/QuranView.tsx`:
- Render a search bar.
- List all 114 Surahs as buttons/pills under the search bar.
- Clicking a Surah fetches all its ayahs from `/api/quran?surah=X` and renders them sequentially in the card.
- Renders Arabic text in a larger, traditional font, followed by Uyghur and English translations, and an ayah reference badge.
- Search queries fetch matches from `/api/quran/search?q=...` and display them dynamically.
