# Auth Component (`auth`)

## Overview
Provides user authentication controls and OAuth provider buttons (Google, Facebook, Twitter/X), alongside an interactive profile menu showing user role badges, bookmarks navigation, and session termination.

## Interface
- `[index.ts:AuthButton]` — Primary authentication button and dropdown trigger.
- `[index.ts:LoginButton]` — Standalone Google OAuth sign-in button.
- `[index.ts:UserMenu]` — User profile avatar, role badge, bookmarks navigation, and logout trigger menu.
- `[AuthButton.tsx:LoginButton]` — Google OAuth trigger button component.
- `[AuthButton.tsx:FacebookLoginButton]` — Facebook OAuth trigger button component.
- `[AuthButton.tsx:TwitterLoginButton]` — Twitter/X OAuth trigger button component.
- `[AuthButton.tsx:OAuthButtonGroup]` — Multi-provider OAuth login dropdown.
- `[AuthButton.tsx:UserMenu]` — Dropdown menu for authenticated users displaying user info, role badges, bookmarks link, and logout option.
- `[AuthButton.tsx:AuthButton]` — Main header authentication component dynamically rendering loading pulse, `UserMenu`, or `OAuthButtonGroup`.

## Invariants
- `[AuthButton.tsx:AuthButton]` — Checks `isAuthenticated` and `isLoading` from `useAuth()`, rendering a pulsing skeleton indicator during auth resolution.
- `[AuthButton.tsx:UserMenu]` — Returns `null` if user is unauthenticated; maps roles (`admin`, `editor`, `reader`) to corresponding badge styles and labels.

## Side Effects
- `[AuthButton.tsx:LoginButton]` — Calls `loginWithGoogle()`.
- `[AuthButton.tsx:FacebookLoginButton]` — Calls `loginWithFacebook()`.
- `[AuthButton.tsx:TwitterLoginButton]` — Calls `loginWithTwitter()`.
- `[AuthButton.tsx:UserMenu]` — Calls `logout()`, dispatches optional `onLogout?.()`, and invokes `setView('library')` and `setActiveTab('bookmarks')`.
- `[AuthButton.tsx:OAuthButtonGroup]` / `[AuthButton.tsx:UserMenu]` — Attaches and removes `document.addEventListener('mousedown')` click-outside listeners.

## Verification
- Run: `npm test`
