---
phase: 09-vnutrenniy-chat
plan: "03"
subsystem: chat-backend
tags: [chat, websocket, rest-api, fastapi, postgresql]
dependency_graph:
  requires: [09-01, 09-02]
  provides: [chat-rest-api, chat-ws-endpoint, badges-chat-unread]
  affects: [tasks-badges, frontend-chat]
tech_stack:
  added: []
  patterns: [keyset-pagination, multipart-upload, ws-jwt-auth, pg-upsert-on-conflict]
key_files:
  created:
    - backend/app/routers/chat.py
  modified:
    - backend/app/__init__.py
    - backend/app/routers/tasks.py
decisions:
  - ws_router uses separate APIRouter without prefix so WS path is /api/ws/chat as frontend expects
  - chat_unread in badges wrapped in try/except to avoid breaking badges if chat tables not yet migrated
  - pg_insert with on_conflict_do_update used for UPSERT on message_reads (constraint name uq_message_read)
metrics:
  duration: "2 minutes"
  completed: "2026-04-03"
  tasks_completed: 2
  files_modified: 3
---

# Phase 09 Plan 03: Chat REST + WebSocket API Summary

**One-liner:** Full chat REST API with WS push using FastAPI, PostgreSQL keyset pagination, and multipart file upload under /api/chat prefix.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create chat.py REST + WebSocket endpoints | bee828f | backend/app/routers/chat.py (created) |
| 2 | Register routers + extend /tasks/badges | f8773c4 | backend/app/__init__.py, backend/app/routers/tasks.py |

## What Was Built

### Task 1 — `backend/app/routers/chat.py`

Created full chat router with two APIRouter instances:

- `router = APIRouter(prefix="/api/chat")` — 8 REST endpoints
- `ws_router = APIRouter()` — 1 WS endpoint at `/api/ws/chat`

**REST Endpoints:**
1. `GET /api/chat/rooms` — list user rooms with last_message + unread_count, sorted by recency
2. `POST /api/chat/rooms/direct` — get-or-create 1-on-1 room (org_id isolation enforced)
3. `POST /api/chat/rooms` — create group chat (all participant_ids validated for same org)
4. `GET /api/chat/rooms/{room_id}/messages` — keyset pagination via `?before_id=`
5. `POST /api/chat/rooms/{room_id}/messages` — multipart form: text + file upload to `/app/uploads/chat/{room_id}/`
6. `POST /api/chat/rooms/{room_id}/read` — UPSERT message_reads + WS push to all participants
7. `GET /api/chat/staff` — staff list filtered by org_id (excludes self)
8. `GET /api/chat/rooms/{room_id}/files/{msg_id}` — FileResponse download

**WS Endpoint:**
- `/api/ws/chat?token=...` — JWT auth via query param; sends initial unread_count on connect; read-only drain loop (all actions via REST)

**Helper functions:**
- `_get_room_unread(room_id, user_id, db)` — per-room unread via LEFT JOIN
- `_get_participant_ids(room_id, db)` — list of room participant user_ids
- `_compute_unread_total(user_id, db)` — total unread across all rooms
- `_check_room_participant(room_id, user_id, db)` — 403 guard
- `_build_room_out(room, user_id, db)` — enriches room with last_message + unread + participants
- `_message_to_dict(msg, sender_name)` — converts ChatMessage to dict for WS push

### Task 2 — Router registration + badges extension

**`backend/app/__init__.py`:**
- `from .routers import chat as chat_router`
- `app.include_router(chat_router.router)` — REST at `/api/chat/...`
- `app.include_router(chat_router.ws_router)` — WS at `/api/ws/chat`

**`backend/app/routers/tasks.py` — `get_badges`:**
- Added `chat_unread` count using `COUNT(DISTINCT CP.room_id)` query with LEFT JOIN on MessageRead
- Wrapped in `try/except` for graceful degradation before DB migration
- Added `"chat_unread": chat_unread` to response dict

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- FOUND: backend/app/routers/chat.py
- FOUND: commit bee828f (Task 1)
- FOUND: commit f8773c4 (Task 2)
- Verification 1: `grep -c "@router\."` → 9 decorators (≥8 required)
- Verification 2: `grep "ws_router|chat_router"` → both found in __init__.py
- Verification 3: `grep "chat_unread"` → found in tasks.py get_badges and return dict
- Verification 4: `grep "from app.chat_manager import manager"` → present in chat.py
- Verification 5: `grep "FileResponse"` → present in chat.py download_file endpoint
