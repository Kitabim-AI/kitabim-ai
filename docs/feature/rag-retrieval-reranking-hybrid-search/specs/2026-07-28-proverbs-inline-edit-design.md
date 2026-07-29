# Proverbs Inline Editing Design Spec

## Executive Summary
Admins and Editors will be able to inline-edit proverbs in the Dictionary Proverbs tab (`ProverbsPanel.tsx`) to fix OCR spelling mistakes. Following the Book Management page UI style, inline controls (Edit icon button, inline text/volume/page input controls, Save & Cancel buttons) allow fast corrections without page popups or entry deletion/creation capabilities.

---

## User Roles & Permissions
- **Permitted Roles**: `ADMIN`, `EDITOR` (checked via `useIsEditor()` hook in React, and `require_editor` dependency in FastAPI backend).
- **Guest / Reader Users**: View-only mode remains unchanged; edit buttons are hidden, and unauthorized backend PUT calls return `403 Forbidden`.

---

## Proposed System Architecture & Design

### 1. Backend (`services/backend/api/endpoints/proverbs_router.py`)
- **New Endpoint**: `PUT /api/proverbs/{proverb_id}`
  - **Auth**: `current_user: User = Depends(require_editor)`
  - **Request Body Schema**:
    ```python
    class ProverbUpdate(BaseModel):
        text: Optional[str] = None
        volume: Optional[int] = None
        page_number: Optional[int] = None
    ```
  - **Action**:
    1. Fetch proverb by `id` from PostgreSQL database. Return `404` if not found.
    2. Update provided non-null fields (`text`, `volume`, `page_number`).
    3. Commit session and refresh object.
    4. Invalidate Redis proverb cache entries (`proverb:*` and `proverbs:*`) so front-end/RAG/random proverb views fetch fresh corrected data.
    5. Return updated `ProverbEntryOut`.

---

### 2. Frontend (`apps/frontend/src/components/admin/dictionary/ProverbsPanel.tsx`)
- **Role Detection**:
  - `const isEditor = useIsEditor();`
- **State Additions**:
  - `editingId: number | null` — tracks ID of proverb currently being inline-edited.
  - `editForm: { text: string; volume: string | number; page_number: string | number } | null` — holds transient form state.
  - `isSaving: boolean` — tracks saving request in progress.

- **UI & Layout (Matching Book Management `AdminView.tsx` Style)**:
  - **Read State**:
    - If `isEditor` is true, display an **Edit** button (`Edit2` icon) styled matching Book Management:
      `p-2 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] hover:bg-[#0369a1] dark:hover:bg-[#38bdf8] hover:text-white dark:hover:text-slate-950 rounded-xl transition-all`
  - **Editing State** (`entry.id === editingId`):
    - `text`: `<textarea>` or `<input type="text">` styled with `uyghur-text text-[16px] md:text-xl border-2 border-[#0369a1] dark:border-[#38bdf8] rounded-xl bg-white dark:bg-slate-950 text-slate-800 dark:text-slate-100 p-2.5 w-full outline-none`.
    - `volume` & `page_number`: optional numeric inputs styled consistently.
    - **Action Controls**:
      - **Save Button**: `<Save size={18} />` (`p-2.5 bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 rounded-xl...`)
      - **Cancel Button**: `<X size={20} />` (`p-2 bg-slate-100 dark:bg-slate-800 text-slate-400...`)
  - **Save Logic**:
    - Trigger `authFetch(`/api/proverbs/${editingId}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(editForm) })`.
    - Update `allEntries` / `suggestions` state directly upon successful response.
    - Reset `editingId` to `null`.

---

## Verification Plan
1. **Automated Tests**:
   - Add backend test for `PUT /api/proverbs/{id}` endpoint verifying:
     - 401 for unauthenticated requests.
     - 403 for `READER` role users.
     - 200 and DB update for `ADMIN` / `EDITOR` role users.
     - Redis cache invalidation call on update.
2. **Manual Verification**:
   - Log in as Editor/Admin user.
   - Navigate to Dictionary → Proverbs Tab.
   - Click inline Edit button on a proverb entry.
   - Modify spelling mistakes and save.
   - Verify text updates inline without full page reload.
