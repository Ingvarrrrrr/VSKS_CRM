# Phase 9: Внутренний чат с уведомлениями — Research

**Researched:** 2026-04-03
**Domain:** Real-time chat — FastAPI WebSockets + Vue 3 Composable + PostgreSQL schema + nginx proxy
**Confidence:** HIGH

---

## Summary

Phase 9 adds a Telegram-style internal messenger to the CRM. Only staff users (those present in the `users` table with any role) can participate. The system requires real-time message delivery, unread counters in the AppBar, file attachments, and a chat list sidebar showing last message + unread count.

The project already has all foundational infrastructure needed: FastAPI async with SQLAlchemy async, JWT auth (token in localStorage), Vuetify 3 components, file uploads stored on disk at `/app/uploads` (not bytea), AppBar with existing polling badge pattern, nginx proxy for the `/api` prefix, and a `users` table with `role`, `full_name`, `org_id`, `profile_photo`, `avatar` columns. The nginx config already proxies `/n8n/` with WebSocket Upgrade headers — the same pattern applies to `/api/ws/`.

**Primary recommendation:** Use FastAPI native WebSockets (not SSE) with a server-side in-memory connection manager for broadcast. Add `?token=...` query param for WS auth since browsers cannot set Authorization headers on WebSocket connections. Store messages in PostgreSQL. Poll for unread badge count every 30s as fallback; update via WS events as primary path.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `fastapi` (WebSocket) | already installed | Real-time message push | Native FastAPI, no extra deps |
| `sqlalchemy` (async) | already installed | Chat models and queries | Already used project-wide |
| `python-jose` | already installed | JWT decode for WS auth | Already used in `app/auth/jwt.py` |
| Vue 3 `ref`/`onMounted`/`onUnmounted` | already used | WS composable lifecycle | Standard Vue 3 pattern |
| `v-virtual-scroll` (Vuetify) | Vuetify 3 | Infinite-scroll message list | Already bundled with Vuetify |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `browser native WebSocket API` | N/A | Frontend WS connection | No additional package needed |
| `v-file-input` (Vuetify) | already bundled | File attachment picker | File upload in chat input |
| `v-badge` (Vuetify) | already bundled | Unread count overlay on navbar icon | Notification badge |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| FastAPI WebSocket | SSE (Server-Sent Events) | SSE simpler for server-push-only but does not support bidirectional messaging; WS is better for chat |
| In-memory ConnectionManager | Redis pub/sub | Redis adds complexity; single-instance Docker deployment makes in-memory sufficient |
| Filesystem file storage | PostgreSQL bytea | Project already uses filesystem (`/app/uploads`) — reuse that pattern, not bytea |

**Installation:** No new packages needed. WebSocket support is built into FastAPI and Starlette.

---

## Architecture Patterns

### Recommended Project Structure
```
backend/app/
├── models/
│   ├── chat_room.py       # ChatRoom, ChatParticipant
│   └── chat_message.py    # ChatMessage, ChatFile, MessageRead
├── routers/
│   └── chat.py            # REST endpoints + WS endpoint
├── chat_manager.py        # In-memory ConnectionManager (broadcast)

frontend/src/
├── views/
│   └── ChatView.vue       # Main chat layout (sidebar + messages)
├── composables/
│   └── useChat.ts         # WS connection, send, receive, reconnect
├── components/
│   ├── ChatRoomList.vue   # Left sidebar: list of chats
│   ├── ChatMessages.vue   # Message thread with virtual scroll
│   └── ChatInput.vue      # Text input + file attachment
```

### Pattern 1: FastAPI WebSocket Connection Manager
**What:** Server-side dict mapping `user_id → WebSocket`. On message send, look up recipient IDs and push to their sockets.
**When to use:** Single Docker instance (no horizontal scaling needed).

```python
# backend/app/chat_manager.py
from fastapi import WebSocket
from typing import Dict, List

class ConnectionManager:
    def __init__(self):
        # user_id -> list of active websocket connections (multi-tab support)
        self.active: Dict[int, List[WebSocket]] = {}

    async def connect(self, user_id: int, ws: WebSocket):
        await ws.accept()
        self.active.setdefault(user_id, []).append(ws)

    def disconnect(self, user_id: int, ws: WebSocket):
        conns = self.active.get(user_id, [])
        if ws in conns:
            conns.remove(ws)
        if not conns:
            self.active.pop(user_id, None)

    async def send_to_user(self, user_id: int, data: dict):
        for ws in self.active.get(user_id, []):
            try:
                await ws.send_json(data)
            except Exception:
                pass

manager = ConnectionManager()
```

### Pattern 2: WebSocket Auth via Query Param (CRITICAL for browser WS)
**What:** Browser `new WebSocket(url)` cannot set Authorization header. Pass JWT as `?token=...` query param.
**When to use:** Always for browser-facing WebSocket endpoints.

```python
# in routers/chat.py
from fastapi import WebSocket, Query
from jose import JWTError, jwt
from app.config import settings

@router.websocket("/ws/chat")
async def chat_ws(
    ws: WebSocket,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username = payload.get("sub")
    except JWTError:
        await ws.close(code=4001)
        return
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        await ws.close(code=4001)
        return
    await manager.connect(user.id, ws)
    try:
        while True:
            data = await ws.receive_json()
            await handle_ws_message(data, user, db)
    except WebSocketDisconnect:
        manager.disconnect(user.id, ws)
```

### Pattern 3: Vue 3 WebSocket Composable
**What:** Composable manages WS lifecycle — connect on mount, reconnect on disconnect, expose reactive message list.

```typescript
// frontend/src/composables/useChat.ts
import { ref, onMounted, onUnmounted } from 'vue'

export function useChat() {
  const ws = ref<WebSocket | null>(null)
  const connected = ref(false)
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  function connect() {
    const token = localStorage.getItem('auth_token')
    if (!token) return
    // Use wss:// in production (nginx terminates TLS), ws:// in local dev
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
    ws.value = new WebSocket(`${protocol}://${location.host}/api/ws/chat?token=${token}`)

    ws.value.onopen = () => { connected.value = true }
    ws.value.onmessage = (e) => {
      const msg = JSON.parse(e.data)
      handleIncoming(msg)
    }
    ws.value.onclose = () => {
      connected.value = false
      // Reconnect after 3 seconds
      reconnectTimer = setTimeout(connect, 3000)
    }
  }

  onMounted(connect)
  onUnmounted(() => {
    ws.value?.close()
    if (reconnectTimer) clearTimeout(reconnectTimer)
  })

  return { ws, connected }
}
```

### Pattern 4: Unread Count via WS Event + Polling Fallback
**What:** AppBar receives unread count update via WS event. Polling (existing `loadBadges()` every 30s) acts as fallback.

AppBar already has `loadBadges()` polling `/api/tasks/badges` every 30s. Add chat unread to the same endpoint response OR create `/api/chat/unread-count` and call it in the same interval.

**Recommended:** Add `chat_unread: int` field to the existing `/api/tasks/badges` response to minimize AppBar changes.

### Pattern 5: Message Pagination (Infinite Scroll Upward)
**What:** Load last 50 messages on open. When user scrolls to top, fetch previous page using `before_id` cursor.
**Pattern:** Keyset pagination (cursor-based) — not offset, because messages are inserted at high rate.

```python
# GET /api/chat/rooms/{room_id}/messages?before_id=123&limit=50
@router.get("/rooms/{room_id}/messages")
async def get_messages(
    room_id: int,
    before_id: Optional[int] = None,
    limit: int = 50,
    ...
):
    q = select(ChatMessage).where(ChatMessage.room_id == room_id)
    if before_id:
        q = q.where(ChatMessage.id < before_id)
    q = q.order_by(ChatMessage.id.desc()).limit(limit)
    msgs = (await db.execute(q)).scalars().all()
    return list(reversed(msgs))  # return in chronological order
```

Frontend: when scroll position reaches top, fetch older messages and prepend, preserving scroll position.

### Anti-Patterns to Avoid
- **OAuth2PasswordBearer on WS endpoint:** Starlette WS does not support HTTP header injection from browser — use `Query(...)` token param.
- **Offset pagination for messages:** Use keyset (`before_id`) to avoid performance degradation at high message counts.
- **Storing files as bytea in DB:** Project uses filesystem (`/app/uploads`). Store chat files there too (under `/app/uploads/chat/{room_id}/`).
- **Broadcasting to all connected clients:** Only push to room participants, not all connected users.
- **Blocking WS receive loop on DB writes:** Use `asyncio` properly — all DB ops inside `while True` loop must be `await`ed with async SQLAlchemy.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| WS broadcast to room participants | Custom event bus | `ConnectionManager` dict (above) | Simple, correct for single-instance Docker |
| Read receipts query | Complex join | Single `message_reads` table + count query | Standard pattern; efficient with index on `(message_id, user_id)` |
| File mime type validation | Custom magic bytes check | Reuse `ALLOWED_MIME` set from `purchase_files.py` | Already validated, tested |
| JWT decode for WS | New auth module | `jose.jwt.decode()` from existing `app/auth/jwt.py` | DRY — already project standard |
| Unread count | COUNT(*) on every request | Indexed `MessageRead` table + pre-computed query | Avoid N+1 with single query per user |

---

## Common Pitfalls

### Pitfall 1: nginx Not Proxying WebSocket Upgrade
**What goes wrong:** WS connection silently fails with 502 or immediate disconnect.
**Why it happens:** nginx strips `Upgrade` and `Connection` headers by default for `/api` location.
**How to avoid:** Add to the `/api` location in `nginx.conf`:
```nginx
location /api {
    proxy_pass http://backend:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header Authorization $http_authorization;
    proxy_pass_header Authorization;
    # WebSocket support (required for /api/ws/chat)
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 86400s;  # keep WS alive for 24h
    proxy_send_timeout 86400s;
}
```
**Warning signs:** WS `readyState` goes to CLOSED immediately after CONNECTING.

### Pitfall 2: WebSocket Auth Token Expiry During Long Session
**What goes wrong:** Token expires while user is in chat; backend closes connection with 4001.
**Why it happens:** JWT has fixed expiry; WS connection is long-lived.
**How to avoid:** Frontend reconnect logic (already in Pattern 3 above) will re-connect with fresh token if user is still logged in. Log expiry close code distinctly to distinguish from network drops.

### Pitfall 3: Scroll Position Jump on Message Prepend
**What goes wrong:** When fetching older messages and prepending to list, viewport jumps to top.
**Why it happens:** DOM mutation shifts scroll position.
**How to avoid:** Save `scrollHeight` before prepend, restore `scrollTop = newScrollHeight - oldScrollHeight` after DOM update using `nextTick`.

### Pitfall 4: Missing `org_id` Isolation
**What goes wrong:** Users from different organizations can see each other's chats.
**Why it happens:** All users share the `users` table — chat participants must be org-scoped.
**How to avoid:** When listing staff for new chat, filter by `User.org_id == current_user.org_id`. When loading rooms, verify participant membership. Superadmin sees all.

### Pitfall 5: `asyncio.sleep` / Ping-Pong Required for Long-Lived WS
**What goes wrong:** nginx or load balancer closes idle WS connections after 60s.
**Why it happens:** Default proxy timeouts kick in on silent connections.
**How to avoid:** Add `proxy_read_timeout 86400s` in nginx (see Pitfall 1). Optionally send WS ping every 30s from frontend as belt-and-suspenders.

---

## Database Schema

```sql
-- Chat rooms (1-on-1 and group)
CREATE TABLE chat_rooms (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255),           -- NULL for 1-on-1 (derived from participants)
    is_group    BOOLEAN DEFAULT FALSE,
    created_by  INTEGER REFERENCES users(id),
    org_id      INTEGER REFERENCES organizations(id),  -- org isolation
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Room participants
CREATE TABLE chat_participants (
    id       SERIAL PRIMARY KEY,
    room_id  INTEGER REFERENCES chat_rooms(id) ON DELETE CASCADE,
    user_id  INTEGER REFERENCES users(id) ON DELETE CASCADE,
    joined_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (room_id, user_id)
);
CREATE INDEX ON chat_participants(user_id);
CREATE INDEX ON chat_participants(room_id);

-- Messages
CREATE TABLE chat_messages (
    id          SERIAL PRIMARY KEY,
    room_id     INTEGER REFERENCES chat_rooms(id) ON DELETE CASCADE,
    sender_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    content     TEXT,                   -- NULL if file-only message
    file_path   VARCHAR(1000),          -- NULL if text-only
    file_name   VARCHAR(255),
    file_mime   VARCHAR(100),
    file_size   INTEGER,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ON chat_messages(room_id, id DESC);  -- keyset pagination

-- Read receipts (who has seen up to which message)
CREATE TABLE message_reads (
    id         SERIAL PRIMARY KEY,
    room_id    INTEGER REFERENCES chat_rooms(id) ON DELETE CASCADE,
    user_id    INTEGER REFERENCES users(id) ON DELETE CASCADE,
    last_read_message_id INTEGER REFERENCES chat_messages(id) ON DELETE SET NULL,
    UNIQUE (room_id, user_id)
);
CREATE INDEX ON message_reads(user_id);
```

**Unread count query (efficient):**
```sql
-- Count rooms with unread messages for a user
SELECT COUNT(*) FROM chat_participants cp
JOIN chat_messages cm ON cm.room_id = cp.room_id
LEFT JOIN message_reads mr ON mr.room_id = cp.room_id AND mr.user_id = cp.user_id
WHERE cp.user_id = :user_id
  AND (mr.last_read_message_id IS NULL OR cm.id > mr.last_read_message_id)
  AND cm.sender_id != :user_id;
```

---

## Code Examples

Verified patterns from project codebase:

### AppBar Badge Integration (existing pattern)
```typescript
// frontend/src/components/AppBar.vue (lines 379-387)
// Existing pattern - add chat_unread to this response
async function loadBadges() {
  try {
    const data = await apiFetch<any>('/tasks/badges')
    badgeNewTasks.value = data.new_tasks || 0
    badgeTaskChanges.value = data.task_changes || 0
    // NEW: add this
    badgeChatUnread.value = data.chat_unread || 0
  } catch {}
}
```

Add to sidebar nav items:
```typescript
{ title: 'Чат', icon: 'mdi-message-outline', route: '/chat', roles: ALL_ROLES },
```

Badge in sidebar (same pattern as tasks badge, lines 237-244 in AppBar.vue):
```html
<span v-if="item.route === '/chat' && badgeChatUnread > 0"
  class="sidebar-badge sidebar-badge--new">{{ badgeChatUnread }}</span>
```

### File Upload in Chat (reuse purchase_files pattern)
```python
# Store under /app/uploads/chat/{room_id}/
import os, hashlib, uuid
from fastapi import UploadFile

CHAT_UPLOAD_DIR = "/app/uploads/chat"

async def save_chat_file(room_id: int, file: UploadFile) -> dict:
    contents = await file.read()
    if len(contents) > 50 * 1024 * 1024:
        raise HTTPException(400, "Файл превышает 50 МБ")
    dest_dir = os.path.join(CHAT_UPLOAD_DIR, str(room_id))
    os.makedirs(dest_dir, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}_{file.filename}"
    dest_path = os.path.join(dest_dir, safe_name)
    with open(dest_path, "wb") as f:
        f.write(contents)
    return {"path": dest_path, "name": file.filename,
            "mime": file.content_type, "size": len(contents)}
```

### WS Message Envelope Format
```json
{
  "type": "message",
  "room_id": 42,
  "message": {
    "id": 1001,
    "sender_id": 7,
    "sender_name": "Иван Петров",
    "content": "Привет!",
    "file_name": null,
    "created_at": "2026-04-03T10:00:00Z"
  }
}

{
  "type": "read",
  "room_id": 42,
  "user_id": 7,
  "last_read_message_id": 1001
}

{
  "type": "unread_count",
  "total_unread": 3
}
```

---

## nginx Configuration Required

The `/api` location block in `nginx/nginx.conf` must be updated to support WebSocket:

```nginx
location /api {
    set $backend_upstream http://backend:8000;
    proxy_pass $backend_upstream;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header Authorization $http_authorization;
    proxy_pass_header Authorization;
    # WebSocket support — required for /api/ws/chat
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 86400s;
    proxy_send_timeout 86400s;
}
```

The `/n8n/` location already has the Upgrade headers — this confirms the pattern works in this nginx setup.

---

## Chat UI Layout

```
┌─────────────────────────────────────────────────────┐
│  AppBar (existing — add chat badge to sidebar)      │
├──────────────┬──────────────────────────────────────┤
│              │  [Contact Name / Group Name]    [···] │
│  Chat List   ├──────────────────────────────────────┤
│  ──────────  │                                       │
│  [User A] 3  │  [message bubble]  10:00              │
│  [Group B]   │      [message bubble]         10:01   │
│  [User C] 1  │  [message bubble]  10:02              │
│              │                                       │
│  [+ New chat]│                                       │
│              ├──────────────────────────────────────┤
│              │  📎  [Type a message...]    [Send]    │
└──────────────┴──────────────────────────────────────┘
```

**Vuetify components to use:**
- `v-navigation-drawer` (left, permanent on desktop) — chat room list
- `v-virtual-scroll` — message list (handles large history efficiently)
- `v-text-field` with `append-inner-icon` — message input
- `v-badge` on sidebar icon — unread count
- `v-list-item` with `v-avatar` — chat list items

**Responsive:** On mobile (< `md` breakpoint), show only chat list OR messages pane (not both). Toggle via route param or local state.

---

## REST API Endpoints Required

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/chat/rooms` | List user's chat rooms (with last message + unread) |
| POST | `/api/chat/rooms` | Create group chat |
| POST | `/api/chat/rooms/direct` | Get-or-create 1-on-1 room with `target_user_id` |
| GET | `/api/chat/rooms/{id}/messages` | Paginated messages (`?before_id=&limit=50`) |
| POST | `/api/chat/rooms/{id}/messages` | Send message (text or with file attachment) |
| POST | `/api/chat/rooms/{id}/read` | Mark room as read (update `message_reads`) |
| GET | `/api/chat/staff` | List staff users available for chat (org-scoped) |
| GET | `/api/tasks/badges` | EXTEND: add `chat_unread` field |
| WS | `/api/ws/chat?token=...` | Real-time connection |
| GET | `/api/chat/rooms/{id}/files/{msg_id}` | Download chat file attachment |

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| SSE for server push | WebSocket bidirectional | WS allows client-to-server messages without separate HTTP call |
| Polling for chat | WebSocket push | Real-time; eliminates polling overhead |
| Redis for pub/sub in single-instance | In-memory dict | Simpler; sufficient for single Docker container |
| Offset pagination | Keyset (cursor) pagination | No performance cliff at large message counts |

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CHAT-01 | Личные сообщения (1-on-1 чат) | `chat_rooms` + `chat_participants` schema; POST /rooms/direct endpoint; WS delivers message to target user_id |
| CHAT-02 | Групповые чаты (несколько участников) | Same schema with `is_group=true`; `name` column; POST /rooms with participants list |
| CHAT-03 | Уведомления в реальном времени (badge в navbar) | WS `unread_count` event; fallback polling via existing `loadBadges()` in AppBar; `chat_unread` field added to `/api/tasks/badges` |
| CHAT-04 | Список чатов с последним сообщением + счётчик непрочитанных | GET /rooms returns last_message + unread_count computed from `message_reads` table |
| CHAT-05 | Только персонал системы (staff users) | GET /chat/staff filters by `User.org_id`; WS auth validates JWT; participants checked at room level |
| CHAT-06 | Отправка сообщений через WebSocket | WS endpoint at `/api/ws/chat?token=...`; nginx Upgrade headers; ConnectionManager broadcast |
| CHAT-07 | Медиафайлы — изображения и документы | POST /rooms/{id}/messages with multipart form; file saved to `/app/uploads/chat/{room_id}/`; same ALLOWED_MIME as purchase_files |
| CHAT-08 | Просмотр/скачивание вложений | GET /chat/rooms/{id}/files/{msg_id} — FileResponse, same pattern as purchase download |
| CHAT-09 | Бейдж непрочитанных в AppBar | `v-badge` on chat sidebar item; `badgeChatUnread` ref; updated by WS event + polling |
| CHAT-10 | Отметка сообщений прочитанными при открытии чата | POST /rooms/{id}/read updates `message_reads`; sends WS `read` event to room participants; badge decrements |
</phase_requirements>

---

## Open Questions

1. **Multi-tab WS connections**
   - What we know: `ConnectionManager` stores a list per user_id, so multiple tabs work.
   - What's unclear: If one tab reads messages, other tabs' local unread count should also decrement — handled by pushing `unread_count` WS event to all connections of the same user.
   - Recommendation: Send `unread_count` update to all connections of `user_id` on read.

2. **Message delivery guarantee**
   - What we know: WS is unreliable (connection drops).
   - What's unclear: Should offline messages be queued?
   - Recommendation: Messages are always written to DB first, then pushed via WS. On reconnect, frontend calls `GET /rooms` and `GET /rooms/{id}/messages` to catch up. No explicit queue needed.

3. **Group chat member management**
   - What we know: Schema has `chat_participants` table.
   - What's unclear: Can members be added/removed after creation?
   - Recommendation: POST `/api/chat/rooms/{id}/participants` and DELETE same — implement in MVP as basic add-only; removal is out of scope.

---

## Sources

### Primary (HIGH confidence)
- Project codebase: `backend/app/auth/jwt.py` — JWT decode pattern confirmed, `get_current_user` uses `OAuth2PasswordBearer` which cannot be used on WS endpoints
- Project codebase: `nginx/nginx.conf` — `/n8n/` location confirms Upgrade header pattern works in this nginx setup
- Project codebase: `backend/app/routers/purchase_files.py` — file storage pattern (filesystem at `/app/uploads`, not bytea)
- Project codebase: `frontend/src/components/AppBar.vue` lines 372–387 — existing badge polling pattern (`loadBadges()`)
- FastAPI official docs: WebSocket endpoint pattern with Query param auth — confirmed in FastAPI WebSocket docs (fastapi.tiangolo.com/advanced/websockets)

### Secondary (MEDIUM confidence)
- nginx official docs: `proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade"` — standard WS proxy pattern; confirmed by `/n8n/` location already in use
- Vuetify 3 docs: `v-virtual-scroll` for long lists — standard component for message rendering

### Tertiary (LOW confidence)
- Keyset pagination performance claims at large scale — standard industry knowledge, not benchmarked against this specific PostgreSQL setup

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already present in project; no new dependencies
- Architecture: HIGH — WebSocket + ConnectionManager is the FastAPI canonical pattern; nginx WS proxy confirmed by existing `/n8n/` config
- Database schema: HIGH — derived from chat domain requirements + existing project conventions (org_id isolation, integer PKs)
- Pitfalls: HIGH — nginx timeout pitfall verified from existing nginx.conf; WS auth via Query param is documented FastAPI limitation
- UI patterns: MEDIUM — Vuetify component choices are standard but UI details (exact layout) require implementation iteration

**Research date:** 2026-04-03
**Valid until:** 2026-07-01 (FastAPI WebSocket API is stable; nginx WS config is static)
