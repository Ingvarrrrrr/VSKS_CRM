---
phase: 09-vnutrenniy-chat
plan: "04"
subsystem: frontend-chat
tags: [chat, websocket, vue3, vuetify, composable]
dependency_graph:
  requires: [09-01, 09-02, 09-03]
  provides: [chat-frontend, chat-route, ws-composable]
  affects: [router, app-navigation]
tech_stack:
  added: []
  patterns: [module-level-refs, onChatEvent-callbacks, telegram-layout, keyset-pagination]
key_files:
  created:
    - frontend/src/composables/useChat.ts
    - frontend/src/views/ChatView.vue
  modified:
    - frontend/src/router/index.ts
decisions:
  - "Module-level refs (totalUnread, wsConnected) allow global badge display in AppBar without prop drilling"
  - "onChatEvent registry pattern: ChatView registers/unregisters on mount/unmount — clean separation from WS lifecycle"
  - "WS ping every 30s to prevent proxy idle timeout; pong silently ignored"
  - "Employee role allowed /chat — chat is universal communication, not admin-only"
metrics:
  duration: "3 minutes"
  completed: "2026-04-04"
  tasks_completed: 3
  tasks_total: 3
  files_created: 2
  files_modified: 1
---

# Phase 09 Plan 04: Chat Frontend Summary

**One-liner:** Vue 3 chat frontend with WebSocket composable (reconnect/ping/global unread) and Telegram-style ChatView (sidebar + message bubbles + file uploads + mobile layout).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create useChat.ts composable | 9847386 | frontend/src/composables/useChat.ts |
| 2 | Create ChatView.vue | 7b0cfe6 | frontend/src/views/ChatView.vue |
| 3 | Add /chat route to Vue Router | 7e88dee | frontend/src/router/index.ts |

## What Was Built

### useChat.ts Composable (`9847386`)
- `totalUnread` and `wsConnected` as module-level Vue refs (shared globally across components)
- `onChatEvent(cb)` — register callback to receive WS events; returns unregister function
- Auto-reconnect with 3s delay on close (except code 4001 = auth error)
- Ping every 30s via `setInterval` to keep connection alive through proxies
- `initChat()` / `destroyChat()` for App.vue lifecycle-free usage
- `useChat()` composable variant with `onMounted`/`onUnmounted` lifecycle binding

### ChatView.vue (`7b0cfe6`)
- **Sidebar** (320px, `v-navigation-drawer`): room list with avatar, name, last message preview, unread badge (`v-badge`)
- **Message area**: bubbles — self (primary/right), other (surface-variant/left); sender name shown in group chats
- **File attachments**: `v-chip` with `mdi-paperclip`, `href` downloads via `/api/chat/rooms/{id}/files/{msg_id}`
- **Input area**: text field + file attach button (`<input type="file">`) + send button
- **WS integration**: `handleChatEvent` handles `message`, `unread_count`, `read` events; rooms sorted by last message
- **Mark-as-read**: called on `selectRoom` and on incoming message if chat is open
- **Keyset pagination**: `onScroll` detects `scrollTop < 50` → loads older messages with `?before_id=`
- **New chat dialog**: staff search, multi-select, direct vs group creation logic
- **Mobile**: `showSidebar` computed — either sidebar or messages visible (not both) using `useDisplay().smAndUp`
- **WS status indicator**: `mdi-wifi` / `mdi-wifi-off` in toolbar from `wsConnected` ref

### Router update (`7e88dee`)
- Added `/chat` route: lazy-loaded `ChatView.vue`, `meta: { requiresAuth: true }`
- Added `/chat` to employee allowed paths in `beforeEach` guard

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Access] Employee role blocked from /chat**
- **Found during:** Task 3 — reading router `beforeEach` guard
- **Issue:** Employee role guard would redirect to `/my-tasks` when navigating to `/chat` — blocking all employees from using chat
- **Fix:** Added `|| path === '/chat'` to the allowed paths list for employee role
- **Files modified:** `frontend/src/router/index.ts`
- **Commit:** 7e88dee

## Self-Check: PASSED

| Item | Status |
|------|--------|
| frontend/src/composables/useChat.ts | FOUND |
| frontend/src/views/ChatView.vue | FOUND |
| frontend/src/router/index.ts | FOUND |
| Commit 9847386 (useChat.ts) | FOUND |
| Commit 7b0cfe6 (ChatView.vue) | FOUND |
| Commit 7e88dee (router) | FOUND |
