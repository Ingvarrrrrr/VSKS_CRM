---
phase: 07-roles-wishes-workflow
plan: 04
subsystem: api
tags: [fastapi, websocket, chat, notifications, hierarchy, consent, sqlalchemy]

# Dependency graph
requires:
  - phase: 07-02
    provides: Wishes lifecycle, employee purchase filter, task assignment with consent flow
  - phase: 09-chat
    provides: ChatRoom/ChatParticipant/ChatMessage models, chat_manager.send_to_user, WS infrastructure
provides:
  - Executor reassignment with hierarchy validation (subordinate = direct, non-subordinate = consent flow)
  - ChatRoom creation on purchase/task assignment (D-18)
  - WS system_notification events with room_id on assignment (D-16, D-17)
  - POST /api/purchases/{pid}/consent endpoint for accepting executor consent (D-15)
  - Frontend system_notification handler in useChat.ts (D-19, D-20)
affects: [chat, tasks, purchases, notifications]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "_create_*_chat_room helper: find-or-create pattern for idempotent room creation"
    - "WS notification with room_id so frontend can open/highlight the correct room"
    - "All WS calls wrapped in try/except — best-effort, never blocks main flow"

key-files:
  created: []
  modified:
    - backend/app/routers/purchases.py
    - backend/app/routers/tasks.py
    - frontend/src/composables/useChat.ts

key-decisions:
  - "_create_assignment_chat_room uses name+org_id uniqueness to avoid duplicate rooms on reassignment"
  - "org_id for ChatRoom creation falls back to current_user.org_id (Purchase has no direct org_id column)"
  - "system_notification event forwarded as new_room to listeners so ChatView can auto-refresh room list"
  - "Task chat room creation runs after db.commit() so room creation is in its own transaction — avoids partial rollback if room creation fails"
  - "accept_purchase_consent sets assigned_user_id directly on Purchase after consent_pending cleared"

patterns-established:
  - "Chat-on-assignment: create ChatRoom -> add ChatParticipants -> send system ChatMessage -> WS notify with room_id"
  - "Non-subordinate assignment: consent_pending=True on member record, no assigned_user_id change until consent"

requirements-completed: [ROLES-06]

# Metrics
duration: 5min
completed: 2026-04-05
---

# Phase 07 Plan 04: Assignment Chat Notifications + Hierarchy Validation Summary

**Executor reassignment with subordinate/non-subordinate hierarchy validation, automatic ChatRoom creation (D-18) on purchase and task assignment, and frontend WS system_notification handler**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-05T20:37:10Z
- **Completed:** 2026-04-05T20:42:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- `purchases.py` assign_purchase endpoint now checks UserHierarchy — subordinates get direct assignment, non-subordinates enter consent flow (D-14/D-15)
- `_create_assignment_chat_room` / `_create_task_chat_room` helpers create idempotent ChatRoom + 2 participants + system message, used on every assignment event (D-18)
- WS `system_notification` payloads include `room_id` so frontend can open the correct room (D-16, D-17)
- New `POST /api/purchases/{pid}/consent` endpoint to accept executor consent (D-15)
- `useChat.ts` handles `system_notification` type: plays notification sound, shows browser Notification, forwards `new_room` event to listeners for room list refresh (D-19, D-20)

## Task Commits

1. **Task 1: purchases.py hierarchy validation + ChatRoom + notifications** - `ac064b1` (feat)
2. **Task 2: tasks.py ChatRoom + notifications + useChat.ts handler** - `9cc7c56` (feat)

## Files Created/Modified

- `backend/app/routers/purchases.py` - Added UserHierarchy/ChatRoom imports, `_create_assignment_chat_room()` helper, hierarchy validation + consent flow in `assign_purchase`, new `POST /{pid}/consent` endpoint
- `backend/app/routers/tasks.py` - Added chat_manager/ChatRoom imports, `_create_task_chat_room()` helper, chat room + WS notification in `create_task` and `respond_task_consent` (accept path)
- `frontend/src/composables/useChat.ts` - Added `system_notification` WS event handler with sound, browser Notification, and `new_room` listener dispatch

## Decisions Made

- `_create_assignment_chat_room` uses `ChatRoom.name + org_id` uniqueness to find existing rooms before creating — idempotent on reassignment
- `org_id` for ChatRoom falls back to `current_user.org_id` because `Purchase` has no direct `org_id` column (it's linked via `subsidy_id -> Subsidy.org_id`)
- `system_notification` event forwarded as `new_room` to all chat listeners — ChatView receives it and can refresh/highlight the new room without polling
- Task chat room creation uses separate `await db.commit()` calls to isolate room creation failures from the main task save
- `accept_purchase_consent` endpoint sets `assigned_user_id` directly after clearing `consent_pending` — no additional hierarchy check needed (consent already given)

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- D-14 through D-20 requirements implemented: hierarchy-aware assignment, chat room creation, WS notifications with room_id, frontend notification handling
- Frontend "Мои заявки" (Viewer) and "Заявки сотрудников" (Manager) views remain unimplemented — tracked in STATE.md

---

*Phase: 07-roles-wishes-workflow*
*Completed: 2026-04-05*
