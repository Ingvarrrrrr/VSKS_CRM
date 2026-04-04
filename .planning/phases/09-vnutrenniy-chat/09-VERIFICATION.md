---
phase: 09-vnutrenniy-chat
verified: 2026-04-03T08:00:00Z
status: gaps_found
score: 8/10 truths verified
gaps:
  - truth: "Таблицы chat_rooms, chat_participants, chat_messages, message_reads существуют в БД после рестарта контейнера"
    status: failed
    reason: "Chat models are NOT imported in backend/app/models/__init__.py. The init_db.py startup script does `import app.models` then `Base.metadata.create_all`, but since chat_room.py and chat_message.py are not in models/__init__.py, the tables are never registered in Base.metadata and are never created. Plan 09-01 Task 3 explicitly required adding these imports but it was not executed."
    artifacts:
      - path: "backend/app/models/__init__.py"
        issue: "Missing: `from .chat_room import ChatRoom, ChatParticipant` and `from .chat_message import ChatMessage, MessageRead`"
      - path: "backend/app/__init__.py"
        issue: "Missing: explicit model imports for ChatRoom, ChatParticipant, ChatMessage, MessageRead before create_all runs"
    missing:
      - "Add `from .chat_room import ChatRoom, ChatParticipant  # noqa: F401` to backend/app/models/__init__.py"
      - "Add `from .chat_message import ChatMessage, MessageRead  # noqa: F401` to backend/app/models/__init__.py"
      - "Create 09-01-SUMMARY.md and 09-02-SUMMARY.md (missing phase documentation)"
---

# Phase 09: Внутренний чат Verification Report

**Phase Goal:** Реализовать встроенный мессенджер в CRM — аналог Telegram. Личные сообщения, групповые чаты, уведомления в реальном времени. Общение только между пользователями, занесёнными в персонал системы.
**Verified:** 2026-04-03T08:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Таблицы chat_rooms/chat_participants/chat_messages/message_reads созданы в БД | ✗ FAILED | Models exist as files but NOT in models/__init__.py — create_all will not create these tables |
| 2 | ChatRoom с is_group=False создаётся для 1-on-1 чата | ✓ VERIFIED | `POST /api/chat/rooms/direct` in chat.py creates room with is_group=False (line 298-311) |
| 3 | ChatRoom с is_group=True создаётся для группового чата | ✓ VERIFIED | `POST /api/chat/rooms` in chat.py creates room with is_group=True (line 336-355) |
| 4 | Пользователь открывает /chat и видит список чатов | ✓ VERIFIED | Route `/chat` registered in router/index.ts (line 243-248); ChatView.vue has full UI with room list |
| 5 | Пользователь может отправить сообщение | ✓ VERIFIED | sendMessage() in ChatView.vue (line 535-558) calls POST /api/chat/rooms/{id}/messages via apiFetch |
| 6 | Сообщения появляются без перезагрузки (WS push) | ✓ VERIFIED | handleChatEvent in ChatView.vue (line 598-636) appends message on WS event type='message' |
| 7 | WS соединение работает и переподключается | ✓ VERIFIED | useChat.ts: ws.onclose triggers setTimeout(connect, 3000) (line 65); ping/pong keepalive every 30s |
| 8 | Badge непрочитанных в AppBar обновляется в реальном времени | ✓ VERIFIED | AppBar.vue has `watch(totalUnread, (val) => { badgeChatUnread.value = val })` and initChat() on mount |
| 9 | Изоляция по org_id — только персонал своей организации | ✓ VERIFIED | create_direct checks `target_user.org_id != current_user.org_id` (line 267); get_staff filters by org_id |
| 10 | nginx проксирует WebSocket соединения | ✓ VERIFIED | nginx.conf has `proxy_set_header Upgrade $http_upgrade`, `Connection "upgrade"`, `proxy_read_timeout 86400s` |

**Score: 9/10 truths verified (1 failed)**

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/app/models/chat_room.py` | ChatRoom, ChatParticipant models | ✓ VERIFIED | 36 lines; ChatRoom with org_id, ChatParticipant with UniqueConstraint |
| `backend/app/models/chat_message.py` | ChatMessage, MessageRead models | ✓ VERIFIED | 39 lines; MessageRead with UniqueConstraint uq_message_read |
| `backend/app/chat_manager.py` | ConnectionManager singleton | ✓ VERIFIED | 56 lines; multi-tab support, send_to_users, graceful offline handling |
| `backend/app/routers/chat.py` | REST + WS endpoints | ✓ VERIFIED | 638 lines; 8 REST endpoints + 1 WS endpoint; all major operations present |
| `backend/app/__init__.py` | Routers registered | ✓ VERIFIED | Lines 313-314: chat_router.router and ws_router both included |
| `frontend/src/views/ChatView.vue` | Full chat UI | ✓ VERIFIED | 755 lines; room list, message area, input, file attachment, new chat dialog |
| `frontend/src/composables/useChat.ts` | WS composable | ✓ VERIFIED | 102 lines; totalUnread, wsConnected, onChatEvent, initChat, destroyChat exported |
| `frontend/src/components/AppBar.vue` | Chat nav item + badge | ✓ VERIFIED | badgeChatUnread ref, mdi-message-outline nav item, watch(totalUnread), initChat() on mount |
| `frontend/src/router/index.ts` | /chat route | ✓ VERIFIED | Lines 243-248: path '/chat', ChatView lazy-loaded, meta.requiresAuth: true |
| `nginx/nginx.conf` | WebSocket proxy headers | ✓ VERIFIED | Upgrade, Connection, proxy_read_timeout 86400s all present |
| `backend/app/models/__init__.py` | Chat model imports | ✗ MISSING | No chat model imports — tables will not be auto-created |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `backend/app/__init__.py` | `routers/chat.py` | `from .routers import chat as chat_router` | ✓ WIRED | Lines 23, 313-314: both routers included |
| `backend/app/routers/chat.py` | `app/chat_manager.py` | `from app.chat_manager import manager` | ✓ WIRED | Line 23; manager.send_to_users called on send_message (line 463) |
| `backend/app/routers/chat.py` | `ChatRoom`, `ChatMessage` | DB queries via sqlalchemy | ✓ WIRED | All 8 endpoints use DB with real queries, no static returns |
| `frontend/src/views/ChatView.vue` | `/api/chat/rooms` | `apiFetch('/chat/rooms')` | ✓ WIRED | loadRooms() at line 494-500; response assigned to rooms.value |
| `frontend/src/views/ChatView.vue` | `useChat.ts` | `import { wsConnected, onChatEvent }` | ✓ WIRED | Line 342; onChatEvent registered in onMounted (line 707) |
| `frontend/src/components/AppBar.vue` | `useChat.ts` | `import { totalUnread, initChat, destroyChat }` | ✓ WIRED | Line 340; watch(totalUnread) at line 758-759; initChat() called in onMounted |
| `backend/app/models/__init__.py` | `chat_room.py`, `chat_message.py` | imports for create_all | ✗ NOT_WIRED | Chat models absent from __init__.py — Base.metadata won't include chat tables |
| `init_db.py` | chat tables | `import app.models` + `create_all` | ✗ BROKEN | init_db.py imports app.models which doesn't include chat models; tables not created |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|---------|
| CHAT-01 | 09-01, 09-03, 09-04 | Личные сообщения между пользователями | ✓ SATISFIED | Direct room creation + message API + ChatView UI all present |
| CHAT-02 | 09-01, 09-03, 09-04 | Групповые чаты | ✓ SATISFIED | POST /api/chat/rooms creates group; ChatView handles is_group display |
| CHAT-03 | 09-05 | Уведомления (badge) в реальном времени | ✓ SATISFIED | AppBar.vue: watch(totalUnread) + WS unread_count event |
| CHAT-04 | 09-03, 09-04 | История сообщений с пагинацией | ✓ SATISFIED | GET /rooms/{id}/messages with ?before_id= keyset pagination; ChatView onScroll triggers loadMessages(beforeId) |
| CHAT-05 | 09-01, 09-03 | Файловые вложения | ✓ SATISFIED | ChatMessage has file_path/file_name/file_mime/file_size; POST /messages accepts UploadFile; GET /files/{msg_id} downloads |
| CHAT-06 | 09-02, 09-04 | WebSocket real-time | ✓ SATISFIED | ConnectionManager + WS endpoint + useChat.ts reconnection logic |
| CHAT-07 | 09-03, 09-04 | Только персонал системы | ✓ SATISFIED | GET /chat/staff filters by org_id; direct room validates target org_id |
| CHAT-08 | 09-03, 09-04 | Чтение/непрочитанные | ✓ SATISFIED | POST /rooms/{id}/read UPSERT + unread_count in room list; WS unread_count push |
| CHAT-09 | 09-05 | Badge в навигации | ✓ SATISFIED | AppBar.vue: mdi-message-outline nav item + sidebar-badge span with badgeChatUnread |
| CHAT-10 | 09-01, 09-03, 09-04 | Изоляция по организации | ✓ SATISFIED | org_id in ChatRoom; org isolation enforced in create_direct, create_group, get_staff |

---

## Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `backend/app/models/__init__.py` | Chat model imports missing (Task 3 from Plan 09-01 not executed) | BLOCKER | Chat tables `chat_rooms`, `chat_participants`, `chat_messages`, `message_reads` will NOT be created on container startup — entire chat feature is non-functional in a fresh deployment |
| Plan 09-01 | No SUMMARY.md created | Warning | Missing documentation for Plans 01 and 02 |
| Plan 09-02 | No SUMMARY.md created | Warning | Missing documentation for Plan 02 |

---

## Human Verification Required

### 1. WebSocket real-time delivery end-to-end

**Test:** Open two browser windows logged in as two different users. User A sends a message to User B. Without refreshing, check if User B's chat updates.
**Expected:** Message appears in User B's chat window within 1-2 seconds without any page refresh.
**Why human:** Cannot verify live WS message delivery programmatically without a running environment.

### 2. Badge reset after reading

**Test:** Send a message from User A to User B. Log in as User B, check that the badge in the sidebar shows > 0. Click on the chat, read the message. Verify badge resets to 0.
**Expected:** Badge disappears after messages are read (after POST /rooms/{id}/read fires).
**Why human:** Requires live browser interaction with WS events in flight.

### 3. File attachment upload and download

**Test:** In a chat room, click the paperclip, attach a PDF or image file. Send. Verify the file chip appears. Click the chip to download.
**Expected:** File uploads successfully, chip shows filename, clicking downloads the file.
**Why human:** File I/O in a running Docker container with mounted volumes.

---

## Gaps Summary

**One critical blocker identified:** Plan 09-01 Task 3 was not executed.

The task required adding two import lines to `backend/app/models/__init__.py`:
```python
from .chat_room import ChatRoom, ChatParticipant   # noqa: F401
from .chat_message import ChatMessage, MessageRead  # noqa: F401
```

Without these imports, `Base.metadata` (used by both `init_db.py create_all` and alembic migrations) does not know about the chat tables. On a fresh container start or migration run, the four chat tables (`chat_rooms`, `chat_participants`, `chat_messages`, `message_reads`) are never created. All 10 chat API endpoints will throw database errors (relation does not exist) at runtime.

Note: On the existing production database the tables may already exist if they were created during development by some other means (e.g., the router importing models causes them to register at uvicorn startup time, AFTER init_db.py has already run). However, a fresh deployment or database reset will fail.

The fix is a 2-line addition to `backend/app/models/__init__.py`.

All other artifacts are substantive and properly wired. The frontend (ChatView.vue, useChat.ts, AppBar integration) and backend (chat.py router, chat_manager.py, nginx config) are fully implemented and correctly connected.

---

_Verified: 2026-04-03T08:00:00Z_
_Verifier: Claude (gsd-verifier)_
