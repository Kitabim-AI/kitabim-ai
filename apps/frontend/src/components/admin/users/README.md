# User Management Admin Component (`admin/users`)

## Overview
Provides the administrative user management interface for viewing, searching, filtering, and modifying user roles (`admin`, `editor`, `reader`) and account active statuses.

## Interface
- `[index.ts:UserManagementPanel]` — Re-exports named component `UserManagementPanel` from `./UserManagementPanel`.
- `[UserManagementPanel.tsx:UserManagementPanel]` — Named and default exported React functional component rendering the admin user management table with search, role/status filtering, infinite scroll pagination, and inline role/status editing.

## Invariants
- `[UserManagementPanel.tsx:UserManagementPanel]` — Requires admin privileges (`useIsAdmin()`); if `!isAdmin`, `loadUsers` exits early and the component renders an access-required notice instead of the user table.
- `[UserManagementPanel.tsx:UserRow]` — Users cannot edit their own record: `isOwnRecord` (`currentUser?.id === user.id`) disables the edit button.
- `[UserManagementPanel.tsx:UserRowProps]` — Editable roles are constrained to `'admin' | 'editor' | 'reader'` and status to `boolean` (`isActive`).
- `[UserManagementPanel.tsx:loadUsers]` — Pagination uses fixed `pageSize = 20`, deduplicates appended users by `u.id`, and sets `hasMore` only when `data.users.length === pageSize` and loaded count is less than `data.total`.

## Side Effects
- `[UserManagementPanel.tsx:loadUsers]` — Calls `UserService.listUsers(nextPage, pageSize, roleFilter, statusFilter, debouncedSearch)` to fetch paginated user records over HTTP.
- `[UserManagementPanel.tsx:handleSave]` — Calls `UserService.changeUserRole(userId, editData.role)` and/or `UserService.changeUserStatus(userId, editData.isActive)` when modified.
- `[UserManagementPanel.tsx:useEffect]` — Registers and cleans up `document` `'mousedown'` event listener to close role/status filter dropdowns on outside click.
- `[UserManagementPanel.tsx:useEffect]` — Instantiates and disconnects an `IntersectionObserver` on `loaderRef` (`rootMargin: '1200px'`, `threshold: 0.1`) to trigger infinite scrolling (`loadUsers(false)`).
- `[UserManagementPanel.tsx:useEffect]` — Auto-focuses `inputRef` after a 50ms timeout on mount and debounces `searchQuery` into `debouncedSearch` with a 500ms timeout.

## Verification
- Run: `npm test`
