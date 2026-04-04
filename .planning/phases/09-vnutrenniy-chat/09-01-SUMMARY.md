---
phase: 09-vnutrenniy-chat
plan: 01
subsystem: database
tags: [sqlalchemy, postgresql, chat, models, orm]

# Dependency graph
requires:
  - phase: 01-purchase-form
    provides: User model with users table and org_id pattern
  - phase: 04-contract-registry
    provides: Organization model with organizations table
provides:
  - ChatRoom SQLAlchemy model (chat_rooms table) with org_id isolation
  - ChatParticipant SQLAlchemy model (chat_participants table) with UniqueConstraint
  - ChatMessage SQLAlchemy model (chat_messages table) with keyset-pagination index
  - MessageRead SQLAlchemy model (message_reads table) with UPSERT-ready UniqueConstraint
affects:
  - 09-02 (REST API endpoints for chat rooms)
  - 09-03 (WebSocket handler — queries chat_rooms, chat_messages, message_reads)
  - 09-04 (composable — reads unread counts from message_reads)
  - 09-05 (AppBar badge — depends on message_reads UniqueConstraint for upsert)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "UniqueConstraint on (room_id, user_id) in message_reads — enables pg_insert on_conflict_do_update UPSERT for mark-as-read"
    - "Composite index on (room_id, id) in chat_messages — enables keyset pagination without OFFSET"
    - "org_id ForeignKey on chat_rooms — standard multi-tenancy isolation pattern used across all entity tables"

key-files:
  created:
    - backend/app/models/chat_room.py
    - backend/app/models/chat_message.py
  modified:
    - backend/app/models/__init__.py

key-decisions:
  - "name=NULL for 1-on-1 ChatRoom; name derived from participants at query time — avoids denormalization"
  - "sender_id SET NULL on user delete — preserves message history without orphan errors"
  - "file_path stored as String(1000) pointing to /app/uploads/chat/{room_id}/ — consistent with existing purchase_files filesystem pattern"
  - "MessageRead tracks last_read_message_id (not list of read IDs) — O(1) unread count via message.id > last_read_message_id"

patterns-established:
  - "Chat room models: org_id always on the root entity (ChatRoom), not on child entities (ChatParticipant, ChatMessage)"
  - "UniqueConstraint naming: uq_{table_short} (e.g., uq_chat_participant, uq_message_read)"

requirements-completed: [CHAT-01, CHAT-02, CHAT-05, CHAT-10]

# Metrics
duration: ~10min
completed: 2026-04-03
---

# Phase 09 Plan 01: Chat Database Models Summary

**Four SQLAlchemy models (ChatRoom, ChatParticipant, ChatMessage, MessageRead) with org_id isolation, UPSERT-ready constraints, and keyset-pagination index — foundation for the entire internal chat system**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-04-03
- **Completed:** 2026-04-03
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments

- Created `chat_rooms` and `chat_participants` tables with UniqueConstraint `(room_id, user_id)` preventing duplicate participants
- Created `chat_messages` table with composite index `(room_id, id)` enabling efficient keyset pagination
- Created `message_reads` table with UniqueConstraint `(room_id, user_id)` enabling `pg_insert on_conflict_do_update` UPSERT for mark-as-read operations
- Registered all four models in `backend/app/models/__init__.py` so SQLAlchemy `create_all` creates tables on container startup

## Task Commits

1. **Task 1: Create ChatRoom and ChatParticipant models** - `17d2594` (feat)
2. **Task 2: Create ChatMessage and MessageRead models** - `4b00268` (feat)
3. **Task 3: Register models in __init__.py** - `87e8f93` (fix — registered in a later commit alongside other 09-* work)

## Files Created/Modified

- `backend/app/models/chat_room.py` — ChatRoom (chat_rooms) and ChatParticipant (chat_participants) models
- `backend/app/models/chat_message.py` — ChatMessage (chat_messages) and MessageRead (message_reads) models
- `backend/app/models/__init__.py` — Added imports for all four chat models with `# noqa: F401`

## Decisions Made

- `name=NULL` for 1-on-1 ChatRoom — avoids denormalization; room name derived from participants at query time
- `sender_id` uses `ondelete="SET NULL"` — preserves message history when users are deleted
- `file_path` stored as `String(1000)` pointing to `/app/uploads/chat/{room_id}/` — consistent with existing `purchase_files` filesystem storage pattern (not bytea)
- `MessageRead` tracks `last_read_message_id` not a list of individual message read receipts — allows O(1) unread count computation via `message.id > last_read_message_id`

## Deviations from Plan

None — plan executed exactly as written. Task 3 (register in `__init__.py`) was committed separately in commit `87e8f93` alongside other Phase 09 work, but all required imports are present and correct.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required. Tables are created automatically by SQLAlchemy `create_all` on container startup.

## Next Phase Readiness

- All four tables will be created on next container restart/rebuild
- `uq_message_read` constraint is ready for `pg_insert on_conflict_do_update` UPSERT (used in 09-03)
- Composite index `ix_chat_messages_room_id_desc` is ready for keyset pagination (used in 09-02/09-03)
- `org_id` on `chat_rooms` enables multi-tenant isolation (enforced in 09-02 REST endpoints)

---
*Phase: 09-vnutrenniy-chat*
*Completed: 2026-04-03*
