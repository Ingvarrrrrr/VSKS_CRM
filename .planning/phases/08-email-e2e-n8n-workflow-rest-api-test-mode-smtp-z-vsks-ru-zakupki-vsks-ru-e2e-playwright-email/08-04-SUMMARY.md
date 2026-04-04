---
phase: "08"
plan: "04"
subsystem: e2e-tests
tags: [playwright, e2e, publications, smtp, fabrikant, roseltorg]
dependency_graph:
  requires: [08-01, 08-02, 08-03]
  provides: [e2e-publication-tests]
  affects: [ci-pipeline]
tech_stack:
  added: []
  patterns: [mock-callback-via-patch, 409-fallback-to-get-list]
key_files:
  created:
    - e2e/12-publications.spec.ts
  modified: []
key_decisions:
  - Handle 409 gracefully by fetching existing publication rather than failing
  - Use /orders/{id}/edit route (not /create-order/{id}) for order detail page
  - Use trailing slash /api/purchases/ to avoid 307 redirect dropping Authorization header
metrics:
  duration: "~15 min"
  completed: "2026-03-20"
  tasks_completed: 1
  files_created: 1
---

# Phase 08 Plan 04: E2E Publication Tests Summary

**One-liner:** 4 Playwright tests covering Fabrikant mock callback, Roseltorg error display, procedure_type API validation, and SMTP endpoint — all 4 passing against remote server.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create e2e/12-publications.spec.ts with 4 tests | 398c390 | e2e/12-publications.spec.ts |

## What Was Built

4 E2E Playwright tests in `e2e/12-publications.spec.ts`:

1. **Фабрикант test mode** — Creates publication, sends mock PATCH callback with `status=published`, verifies chip "Опубликовано" visible in UI on `/orders/{id}/edit`
2. **Росэлторг no-token error** — Creates publication, mock callback with `status=error` and descriptive error_text, verifies error text visible in UI table
3. **Росэлторг procedure_type validation** — POST with `procedure_type` field returns 200 or 409 (not 422), confirming no schema validation error
4. **SMTP test endpoint** — POST to `/api/settings/smtp/test` returns non-500 (200 or 400 with message)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] POST publication returns 409 when publication already exists**
- **Found during:** Task 1 execution
- **Issue:** Remote server already had publications for the test purchase+platform, causing 409 on POST
- **Fix:** Added fallback — when 409 received, GET existing publications list and find the matching one by platform
- **Files modified:** e2e/12-publications.spec.ts
- **Commit:** 398c390

**2. [Rule 1 - Bug] Wrong route URL in UI assertions**
- **Found during:** Task 1 execution
- **Issue:** Plan used `/create-order/${purchaseId}` but router uses `/orders/:id/edit`
- **Fix:** Changed page.goto to `/orders/${purchaseId}/edit`
- **Files modified:** e2e/12-publications.spec.ts
- **Commit:** 398c390

**3. [Rule 1 - Bug] 307 redirect drops Authorization header in beforeAll**
- **Found during:** Task 1 execution (beforeAll GET /api/purchases?limit=5 returned 401)
- **Issue:** nginx redirects `/api/purchases` → `/api/purchases/` (trailing slash), Authorization header dropped on redirect
- **Fix:** Use `/api/purchases/?limit=5` (with trailing slash) directly
- **Files modified:** e2e/12-publications.spec.ts
- **Commit:** 398c390

## Verification Results

```
BASE_URL=http://85.239.53.155 npx playwright test e2e/12-publications.spec.ts --reporter=line
4 passed (1.5m)
```

All 4 tests pass against remote server at http://85.239.53.155.

## Self-Check: PASSED

- File exists: e2e/12-publications.spec.ts ✓
- Commit exists: 398c390 ✓
- All 4 tests pass ✓
