# Navbar Spacing Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce padding and flex gap spacing in the frontend navigation bar so all items (9 links, search, upload, and profile) fit cleanly on a single row on desktop screens without overlapping or wrapping.

**Architecture:** Update Tailwind CSS class names inside the `Navbar` component to decrease padding and margins responsively.

**Tech Stack:** React, TypeScript, Tailwind CSS.

## Global Constraints
- Do not introduce breaking changes to existing navigation states/actions.
- Align design adjustments to the desktop breakpoint `xl` (>= 1280px) and `2xl` (>= 1536px).

---

### Task 1: Update Navbar Layout and Button Spacing

**Files:**
- Modify: `apps/frontend/src/components/layout/Navbar.tsx`

**Interfaces:**
- Consumes: None
- Produces: Updated styles for the Navigation Bar component

- [ ] **Step 1: Apply spacing changes to Navbar.tsx**

  In [Navbar.tsx](../../../apps/frontend/src/components/layout/Navbar.tsx), perform the following contiguous edits:

  - Update line 37:
    ```diff
    -      <nav className="fixed top-0 left-0 right-0 px-4 sm:px-6 md:px-10 lg:px-12 py-1.5 sm:py-2 flex items-center justify-between z-[100] transition-all duration-300" dir="rtl">
    +      <nav className="fixed top-0 left-0 right-0 px-4 sm:px-6 md:px-8 lg:px-8 xl:px-10 py-1.5 sm:py-2 flex items-center justify-between z-[100] transition-all duration-300" dir="rtl">
    ```

  - Update line 46:
    ```diff
    -        <div className="relative flex items-center gap-3 sm:gap-4 md:gap-3 lg:gap-8">
    +        <div className="relative flex items-center gap-3 sm:gap-4 md:gap-3 lg:gap-4 xl:gap-5">
    ```

  - Update line 58:
    ```diff
    -            <span dir="ltr" className="flex items-center font-semibold text-[#1a1a1a] text-[24px] mt-[12px] md:text-[32px] md:mt-[16px] tracking-tight">
    +            <span dir="ltr" className="flex items-center font-semibold text-[#1a1a1a] text-[24px] mt-[12px] md:text-[28px] md:mt-[14px] lg:text-[30px] lg:mt-[15px] xl:text-[32px] xl:mt-[16px] tracking-tight">
    ```

  - Update line 126:
    ```diff
    -        <div className="relative flex items-center gap-2 md:gap-2 lg:gap-4">
    +        <div className="relative flex items-center gap-2 lg:gap-3">
    ```

  - Update line 142 (Add Book button):
    ```diff
    -                className="group relative px-[0.7rem] md:px-5 lg:px-6 h-9 md:h-11 rounded-xl md:rounded-2xl font-normal flex items-center justify-center gap-2 transition-all duration-300 text-white shadow-[0_8px_20px_rgba(3,105,161,0.2)] hover:shadow-[0_12px_28px_rgba(3,105,161,0.3)] hover:-translate-y-0.5 active:translate-y-0 overflow-hidden text-sm lg:text-base"
    +                className="group relative px-[0.7rem] md:px-4 lg:px-4 xl:px-5 h-9 md:h-11 rounded-xl md:rounded-2xl font-normal flex items-center justify-center gap-2 transition-all duration-300 text-white shadow-[0_8px_20px_rgba(3,105,161,0.2)] hover:shadow-[0_12px_28px_rgba(3,105,161,0.3)] hover:-translate-y-0.5 active:translate-y-0 overflow-hidden text-sm lg:text-base"
    ```

  - Update line 274 (NavButton component padding):
    ```diff
    -    className={`relative px-3 md:px-3 lg:px-4 xl:px-6 h-[36px] md:h-[42px] rounded-xl text-sm lg:text-base font-normal flex items-center gap-2 transition-all duration-300 group ${active
    +    className={`relative px-2.5 lg:px-3 xl:px-3 2xl:px-4 h-[36px] md:h-[42px] rounded-xl text-sm lg:text-base font-normal flex items-center gap-2 transition-all duration-300 group ${active
    ```

- [ ] **Step 2: Rebuild and redeploy containers**

  Run in root:
  `./deploy/local/rebuild-and-restart.sh frontend`

- [ ] **Step 3: Run existing unit tests**

  Run inside `apps/frontend`:
  `npx vitest run src/tests/components/layout/Navbar.test.tsx`

  Verify that the tests that passed previously (Navbar renders correctly and handles file upload trigger) still pass.

- [ ] **Step 4: Commit changes**

  Run:
  `git add apps/frontend/src/components/layout/Navbar.tsx`
  `git commit -m "style: optimize navbar horizontal spacing and padding for xl layout"`
