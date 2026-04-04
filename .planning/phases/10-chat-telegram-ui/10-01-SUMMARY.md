---
phase: 10-chat-telegram-ui
plan: 01
subsystem: e2e
tags: [e2e, chat, websocket, playwright, test-scaffold]
dependency_graph:
  requires: []
  provides: [e2e/13-chat-ui.spec.ts]
  affects: [e2e/]
tech_stack:
  added: []
  patterns: [graceful-skip-pattern, playwright-test-scaffold]
key_files:
  created:
    - e2e/13-chat-ui.spec.ts
  modified: []
decisions:
  - "chromium imported for future two-context cross-user delivery test (not yet used)"
  - "CHAT-UI-01 two-browser cross-user test omitted — requires two live accounts with known credentials"
  - "All tests use test.skip() for missing data conditions — no hard failures on empty rooms/messages"
metrics:
  duration: "2m"
  completed: "2026-04-04"
  tasks: 1
  files: 1
---

# Phase 10 Plan 01: E2E Test Scaffold for Chat Telegram-style UI Summary

**One-liner:** Playwright E2E scaffold with 8 tests covering real-time delivery (CHAT-UI-01), sticky header (CHAT-UI-02), dual-mode search (CHAT-UI-03), and Telegram polish (CHAT-UI-04) — all skip gracefully without chat data.

## What Was Built

Created `e2e/13-chat-ui.spec.ts` with 8 tests:

| Test | Requirement | Behavior |
|------|-------------|----------|
| chat header stays visible after scrolling | CHAT-UI-02 | toolbar.boundingBox().y < 200 after scroll |
| search field visible in sidebar | CHAT-UI-03 | `.chat-sidebar input[placeholder*="Поиск"]` is visible |
| search filters room list when no room selected | CHAT-UI-03 | room count decreases with nonsense query |
| search placeholder changes when room is selected | CHAT-UI-03 | placeholder switches "по чатам" → "в чате" |
| message bubbles have correct CSS classes | CHAT-UI-04 | `.bubble-self` / `.bubble-other` with position:relative |
| date separators present | CHAT-UI-04 | `.date-separator` DOM check |
| WebSocket connection indicator visible | CHAT-UI-01 | `.v-toolbar .v-icon[class*="mdi-wifi"]` visible |
| message sent appears without page reload | CHAT-UI-01 | message count increases + `.bubble-self` contains text |

## Verification

```
npx playwright test e2e/13-chat-ui.spec.ts --list
Total: 8 tests in 1 file
```

All 4 requirement IDs (CHAT-UI-01 through CHAT-UI-04) have dedicated test blocks. File parses without TypeScript/Playwright errors.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. This is a test scaffold — no UI components or stubs introduced.

## Commits

| Hash | Description |
|------|-------------|
| 3a5c5f6 | test(10-01): add E2E scaffold for Phase 10 chat UI — 8 tests covering CHAT-UI-01..04 |

## Self-Check: PASSED

- `e2e/13-chat-ui.spec.ts` exists: FOUND
- Commit 3a5c5f6 exists: FOUND
- 8 tests listed (requirement: 7+): PASSED
- All 4 CHAT-UI requirements covered: PASSED
