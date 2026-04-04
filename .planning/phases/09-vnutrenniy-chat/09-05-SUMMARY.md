---
phase: 09-vnutrenniy-chat
plan: 05
subsystem: ui
tags: [vue3, vuetify, websocket, badge, chat, sidebar]

# Dependency graph
requires:
  - phase: 09-vnutrenniy-chat-03
    provides: chat REST API + WS endpoint + chat_unread in /api/tasks/badges
  - phase: 09-vnutrenniy-chat-04
    provides: useChat.ts composable with totalUnread ref, initChat, destroyChat exports
provides:
  - AppBar sidebar nav item 'Чат' with mdi-message-outline icon (ALL_ROLES)
  - badgeChatUnread ref with dual-update: WS watch(totalUnread) + polling loadBadges every 60s
  - WS lifecycle: initChat() on mount, destroyChat() on unmount
  - _badgeInterval cleanup in onUnmounted (previously missing)
affects: [09-vnutrenniy-chat]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Badge dual-update pattern: WS push (instant) + polling fallback (60s)"
    - "Module-level reactive ref (totalUnread) shared between useChat and AppBar via watch"

key-files:
  created: []
  modified:
    - frontend/src/components/AppBar.vue

key-decisions:
  - "totalUnread ref from useChat.ts is watched in AppBar — single source of truth for WS-driven badge updates"
  - "loadBadges() polling remains as fallback even with WS to handle reconnection gaps"
  - "_badgeInterval now cleared in onUnmounted (was previously not cleaned up)"

patterns-established:
  - "Sidebar badge: <span v-if=\"item.route === '/X' && badgeX > 0\" class=\"sidebar-badge sidebar-badge--new\"> pattern"

requirements-completed: [CHAT-03, CHAT-09]

# Metrics
duration: 4min
completed: 2026-04-04
---

# Phase 09 Plan 05: Chat Badge in AppBar Summary

**AppBar sidebar gets 'Чат' nav item with real-time unread badge via WS push (watch totalUnread) + 60s polling fallback**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-04T07:16:00Z
- **Completed:** 2026-04-04T07:19:32Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- Added `import { totalUnread, initChat, destroyChat } from '@/composables/useChat'` to AppBar
- Added `const badgeChatUnread = ref(0)` and `badgeChatUnread.value = data.chat_unread || 0` in loadBadges
- Added `{ title: 'Чат', icon: 'mdi-message-outline', route: '/chat', roles: ALL_ROLES }` to sidebar menu
- Added badge span in template: `v-if="item.route === '/chat' && badgeChatUnread > 0"`
- Added `initChat()` in onMounted + `destroyChat()` in new onUnmounted block
- Added `watch(totalUnread, (val) => { badgeChatUnread.value = val })` for real-time WS updates

## Task Commits

Each task was committed atomically:

1. **Task 1: Add chat nav item, badge ref, WS integration to AppBar** - `c5a4318` (feat)

**Plan metadata:** (will be committed with SUMMARY + STATE updates)

## Files Created/Modified
- `frontend/src/components/AppBar.vue` - Chat nav item + badgeChatUnread + WS integration

## Decisions Made
- `watch(totalUnread, ...)` chosen over direct ref sharing — keeps AppBar reactive to WS events without coupling to composable internals
- `initChat()` called from AppBar (always-mounted component) rather than App.vue — AppBar is the natural persistent lifecycle owner for the WS connection
- `_badgeInterval` cleanup added to onUnmounted as Rule 2 (missing cleanup) auto-fix

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added _badgeInterval cleanup in onUnmounted**
- **Found during:** Task 1 (onMounted / onUnmounted integration)
- **Issue:** Plan specified adding `destroyChat()` in onUnmounted but the existing code had no onUnmounted at all — `_badgeInterval` was never cleared, causing a memory leak
- **Fix:** Created full onUnmounted block that clears both `_badgeInterval` and calls `destroyChat()`
- **Files modified:** frontend/src/components/AppBar.vue
- **Verification:** onUnmounted block visible in file with both clearInterval and destroyChat calls
- **Committed in:** c5a4318 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical — cleanup)
**Impact on plan:** Essential correctness fix. No scope creep.

## Issues Encountered

Plan 09-04 was found to be partially executed (useChat.ts existed but plan had no SUMMARY.md). Since useChat.ts, ChatView.vue, and the router entry all existed when checked, 09-04 was actually fully complete — only missing the SUMMARY artifact. Plan 09-05 executed cleanly against the existing 09-04 artifacts.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Chat badge is live in sidebar for all users after next Docker image rebuild
- Users will see unread count update in real-time as WS messages arrive
- After reading messages in ChatView, badge resets to 0 via server POST /read → WS unread_count event
- Remaining chat phase work: none identified beyond this plan

---
*Phase: 09-vnutrenniy-chat*
*Completed: 2026-04-04*
