# Phase 1: Backend Stabilization - Research

**Researched:** 2026-03-15
**Domain:** Node.js Express API hardening — state machine enforcement, atomic DB transactions, CORS, input validation, address geocoding
**Confidence:** MEDIUM (codebase verified directly; external library APIs verified from package.json versions + training knowledge at HIGH confidence for stable libs; geocoding API options are MEDIUM)

---

## Summary

The fruits_repo backend is a Node.js + Express 5 + PostgreSQL app located at `/c/Users/1/AppData/Local/Temp/fruits_repo/apps/api/`. The main server is `src/server.ts`; game/wallet logic lives in `src/routes/game.ts`; order status updates live in `src/server.ts` (`PATCH /orders/:id/status`) and `src/routes/orders.ts` (`PUT /:id/status`).

**Current state of the five requirements:**

| Req | Current state | Gap |
|-----|---------------|-----|
| BACK-01 (state machine) | `PATCH /orders/:id/status` accepts any valid enum value from a whitelist but does NOT enforce transition order (`new → picking → ready → courier → delivered`). Any status can jump to any other. | Add transition table; read current status first; reject invalid jumps. |
| BACK-02 (atomic wallet) | `POST /game/orders/:id/deliver` updates wallet with `ON CONFLICT DO UPDATE` but uses the **same `pool` connection** (not a transaction). A second concurrent request can read the stale balance before the first update commits — classic read-modify-write race. | Wrap in `BEGIN … SELECT FOR UPDATE … UPDATE … COMMIT`. |
| BACK-03 (CORS) | `app.use(cors())` — **wildcard, no origin restriction**. In production this allows any origin. | Pass `{ origin: ALLOWED_ORIGIN }` from env. |
| BACK-04 (input validation) | No systematic validation library. Endpoints do ad-hoc `if (!field)` checks. Route params (`:id`) go directly into SQL as `$1` — safe from injection via parameterized queries, but no type/range checks, no `req.params.id` integer validation. | Add `express-validator` or `zod` + middleware. |
| BACK-05 (address validation Moscow) | No geocoding at all. Address is stored as freeform text. | Integrate Nominatim (OSM, free) or Yandex Geocoder; validate city=Москва + street + house exist; reject otherwise. |

**Primary recommendation:** Implement BACK-01 through BACK-04 entirely in-process (no new services). For BACK-05, use Nominatim (free, no key) as primary — Yandex Geocoder as fallback if Russian address coverage proves insufficient.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| BACK-01 | Order status transitions enforced via state machine (only valid transitions allowed) | State machine map + pre-update current-status read; enforced in `PATCH /orders/:id/status` and `PUT game/orders/:id/deliver` |
| BACK-02 | Wallet operations use atomic transactions (SELECT FOR UPDATE, no race conditions) | PostgreSQL `SELECT … FOR UPDATE` inside explicit transaction on `game_wallets`; eliminates the race in `game.ts:164-184` |
| BACK-03 | CORS configured correctly for production origin | Replace `cors()` wildcard with `cors({ origin: process.env.ALLOWED_ORIGIN })` |
| BACK-04 | API input validation on all endpoints (prevent injection) | Parameterized queries already prevent SQL injection; add `express-validator` or `zod` for type/range/presence checks |
| BACK-05 | Address validation for Moscow (geocoding, valid street/house/entrance, reject invalid) | Nominatim reverse/forward geocoding; validate city, street, house components; optionally validate entrance via Yandex |
</phase_requirements>

---

## Standard Stack

### Core (already installed — no new installs needed for BACK-01/02/03)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `express` | ^5.2.1 | HTTP framework | Already in use |
| `pg` | ^8.19.0 | PostgreSQL client; `pool.connect()` → `client.query("BEGIN")` pattern | Already in use; native `SELECT FOR UPDATE` support |
| `cors` | ^2.8.6 | CORS middleware | Already in use; just needs config |

### Supporting (need to install)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `express-validator` | ^7.x | Declarative input validation middleware for Express | BACK-04: cleaner than hand-rolled checks; integrates natively with Express 5 |
| `zod` | ^3.x | Runtime schema validation (alternative to express-validator) | If team prefers schema-first TypeScript style |
| `node-fetch` or built-in `fetch` | Node 18+ built-in | HTTP calls to external geocoding API | BACK-05; Node 18+ has global `fetch`; no install needed if runtime ≥ 18 |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `express-validator` | `zod` + custom middleware | `zod` gives better TS types; `express-validator` has more Express-idiomatic chain syntax. Both acceptable. |
| Nominatim (OSM) | Yandex Geocoder API | Nominatim is free with no key; Yandex has better Russian coverage but requires API key and has rate limits |
| Nominatim | DaData.ru | DaData has best Russian address parsing but costs money; overkill for MVP |

**Installation (if using express-validator):**
```bash
cd /c/Users/1/AppData/Local/Temp/fruits_repo/apps/api
npm install express-validator
```

---

## Architecture Patterns

### Recommended Project Structure (additions to existing)

```
apps/api/src/
├── middleware/
│   ├── validate.ts          # express-validator error handler
│   └── corsConfig.ts        # cors({ origin }) factory
├── lib/
│   ├── stateMachine.ts      # TRANSITIONS map + validateTransition()
│   └── geocode.ts           # Nominatim wrapper + Moscow validator
├── routes/
│   ├── game.ts              # (existing) — patch deliver to use transaction
│   └── ...
└── server.ts                # (existing) — patch PATCH /orders/:id/status
```

### Pattern 1: State Machine — Transition Table

**What:** A plain JS object maps `currentStatus → Set<allowedNextStatus>`. The handler reads the current status from DB, checks the map, rejects invalid transitions with 409.

**When to use:** Any time an entity has a linear or branching workflow with enforced progression.

```typescript
// src/lib/stateMachine.ts
type OrderStatus = "new" | "picking" | "ready" | "courier" | "delivered";

const TRANSITIONS: Record<OrderStatus, OrderStatus[]> = {
  new:       ["picking"],
  picking:   ["ready"],
  ready:     ["courier"],
  courier:   ["delivered"],
  delivered: [],          // terminal
};

export function canTransition(from: OrderStatus, to: OrderStatus): boolean {
  return (TRANSITIONS[from] ?? []).includes(to);
}
```

Usage in `PATCH /orders/:id/status`:
```typescript
// 1. Read current status (within same transaction to avoid TOCTOU)
const current = await client.query(
  "SELECT status FROM orders WHERE id = $1 FOR UPDATE",
  [id]
);
if (!current.rowCount) return res.status(404).json({ error: "not_found" });

// 2. Validate transition
if (!canTransition(current.rows[0].status, newStatus)) {
  return res.status(409).json({
    error: "invalid_transition",
    from: current.rows[0].status,
    to: newStatus,
  });
}

// 3. Apply
await client.query("UPDATE orders SET status = $1 WHERE id = $2", [newStatus, id]);
await client.query("COMMIT");
```

### Pattern 2: Atomic Wallet Credit (SELECT FOR UPDATE)

**What:** Acquire a row-level lock before reading balance, update in the same transaction. Prevents two concurrent deliveries from double-crediting.

**When to use:** Any monetary/counter update that must not race.

```typescript
// In game.ts POST /orders/:id/deliver — replace pool.query with client transaction
const client = await pool.connect();
try {
  await client.query("BEGIN");

  // Lock the order row to prevent concurrent delivery claims
  const order = await client.query(
    "SELECT * FROM orders WHERE id = $1 AND status = 'ready' FOR UPDATE",
    [id]
  );
  if (!order.rowCount) {
    await client.query("ROLLBACK");
    return res.status(404).json({ error: "order_not_found_or_not_ready" });
  }

  // Mark delivered
  await client.query(
    "UPDATE orders SET status = 'delivered', delivered_at = NOW(), assigned_courier_id = $2 WHERE id = $1",
    [id, courier_id]
  );

  const reward = Math.floor(order.rows[0].total_cents / 10);

  // Atomic wallet upsert — still safe with ON CONFLICT because row is locked
  await client.query(
    `INSERT INTO game_wallets (user_id, balance_virtual, total_earned_virtual)
     VALUES ($1, $2, $2)
     ON CONFLICT (user_id) DO UPDATE
     SET balance_virtual = game_wallets.balance_virtual + EXCLUDED.balance_virtual,
         total_earned_virtual = game_wallets.total_earned_virtual + EXCLUDED.total_earned_virtual`,
    [courier_id, reward]
  );

  await client.query("COMMIT");
  res.json({ success: true, reward, order: order.rows[0] });
} catch (e) {
  await client.query("ROLLBACK");
  throw e;
} finally {
  client.release();
}
```

> **Why `SELECT … FOR UPDATE` on the order row, not the wallet row?** The wallet upsert with `ON CONFLICT DO UPDATE` is already atomic per-statement. The real race is two couriers both reading status='ready' and both claiming delivery. Locking the order row prevents both from succeeding.

### Pattern 3: CORS — Environment-driven Origin

**What:** Pass `{ origin }` to the cors middleware; read from `process.env.ALLOWED_ORIGIN`.

```typescript
// server.ts
import cors from "cors";

const ALLOWED_ORIGIN = process.env.ALLOWED_ORIGIN || "http://localhost:3000";

app.use(cors({
  origin: ALLOWED_ORIGIN,
  methods: ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
  allowedHeaders: ["Content-Type", "Authorization"],
  credentials: true,
}));
```

Set in `.env`:
```
ALLOWED_ORIGIN=https://yourdomain.com
```

For multiple origins (e.g., prod + staging):
```typescript
const ORIGINS = (process.env.ALLOWED_ORIGINS || "").split(",").filter(Boolean);
app.use(cors({ origin: (origin, cb) => {
  if (!origin || ORIGINS.includes(origin)) cb(null, true);
  else cb(new Error("Not allowed by CORS"));
}}));
```

### Pattern 4: Input Validation with express-validator

**What:** Declare validation chains on routes; use `validationResult()` in a shared middleware.

```typescript
// middleware/validate.ts
import { validationResult } from "express-validator";
import { Request, Response, NextFunction } from "express";

export const validate = (req: Request, res: Response, next: NextFunction) => {
  const errors = validationResult(req);
  if (!errors.isEmpty()) {
    return res.status(422).json({ errors: errors.array() });
  }
  next();
};
```

```typescript
// In route file
import { param, body } from "express-validator";
import { validate } from "../middleware/validate.js";

router.patch(
  "/orders/:id/status",
  param("id").isUUID().withMessage("id must be a valid UUID"),
  body("status").isIn(["picking", "ready", "courier", "delivered"]).withMessage("invalid status"),
  validate,
  async (req, res) => { /* handler */ }
);
```

### Pattern 5: Address Validation via Nominatim

**What:** Call `https://nominatim.openstreetmap.org/search` with structured query; verify `city` component is Москва; verify `road` (street) and `house_number` are present in the response.

**When to use:** BACK-05. No API key required; rate limit = 1 req/sec (must throttle in bulk scenarios).

```typescript
// src/lib/geocode.ts
const NOMINATIM = "https://nominatim.openstreetmap.org/search";

interface NominatimResult {
  address: {
    city?: string;
    town?: string;
    road?: string;
    house_number?: string;
    country_code?: string;
  };
  lat: string;
  lon: string;
}

export async function validateMoscowAddress(
  street: string,
  house: string,
  entrance?: string
): Promise<{ valid: boolean; lat?: number; lon?: number; reason?: string }> {
  const url = new URL(NOMINATIM);
  url.searchParams.set("street", `${house} ${street}`);
  url.searchParams.set("city", "Москва");
  url.searchParams.set("country", "Russia");
  url.searchParams.set("format", "jsonv2");
  url.searchParams.set("addressdetails", "1");
  url.searchParams.set("limit", "1");

  const resp = await fetch(url.toString(), {
    headers: { "User-Agent": "FruitsDeliveryApp/1.0" }, // Required by Nominatim ToS
  });
  if (!resp.ok) throw new Error(`Nominatim error ${resp.status}`);
  const data: NominatimResult[] = await resp.json();

  if (!data.length) return { valid: false, reason: "address_not_found" };

  const addr = data[0].address;
  const city = addr.city || addr.town || "";
  if (!city.toLowerCase().includes("москва")) {
    return { valid: false, reason: "not_moscow" };
  }
  if (!addr.road) return { valid: false, reason: "street_not_found" };
  if (!addr.house_number) return { valid: false, reason: "house_not_found" };

  // Entrance (подъезд) cannot be validated via geocoding — it's building metadata
  // Accept if street+house validate; log entrance for manual review
  return {
    valid: true,
    lat: parseFloat(data[0].lat),
    lon: parseFloat(data[0].lon),
  };
}
```

**Nominatim ToS requirements (HIGH confidence):**
- `User-Agent` header identifying your app — mandatory.
- Max 1 request/second from a single IP.
- No bulk geocoding (use caching if same address appears multiple times).

### Anti-Patterns to Avoid

- **Setting status without reading current:** `UPDATE orders SET status=$2 WHERE id=$1` without first checking current status allows any transition.
- **Wallet update without transaction:** Using bare `pool.query()` for wallet credits means two concurrent requests can both read the same balance and both add to it — yielding double credit.
- **`cors()` with no options in production:** Allows any origin. Always supply `{ origin }`.
- **Integer IDs validated as-is:** If IDs are UUIDs (as in this codebase), validate with `isUUID()` before querying; if numeric, `isInt()`. Prevents unnecessary DB round-trips on malformed input.
- **Entrance validation via geocoding:** Nominatim does not carry entrance/подъезд data. Do NOT attempt to validate entrance number via geocoding — it will always fail. Accept entrance as unvalidatable at this layer.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Input validation chains | Custom `if (!field || typeof field !== 'string')` per route | `express-validator` | Edge cases: whitespace-only strings, type coercion, nested body, query vs param handling |
| SQL injection prevention | Manual escaping | Parameterized queries (`$1`, `$2`) — already in use | Parameterized queries are the correct solution; already implemented |
| CORS headers | Manual `res.setHeader('Access-Control-Allow-Origin', ...)` | `cors` package — already installed | Handles preflight OPTIONS, vary headers, credentials correctly |
| Geocoding HTTP client | Custom fetch wrapper | Node 18+ built-in `fetch` | Already available; no install needed |

**Key insight:** The race condition is the most dangerous issue. A custom "check then update" pattern without `SELECT FOR UPDATE` is always wrong under concurrent load — always use the database's row-locking primitives.

---

## Common Pitfalls

### Pitfall 1: TOCTOU Race in Order Delivery
**What goes wrong:** Two couriers simultaneously `GET /game/orders/available` → both see order as `ready` → both call `POST /game/orders/:id/deliver` → both succeed → wallet gets double credit, order_count wrong.
**Why it happens:** Current code: `UPDATE orders SET status = 'delivered' WHERE id = $1 AND status = 'ready'` runs without locking. The `WHERE status = 'ready'` filter is a check-and-set, but if two requests are in-flight simultaneously, both can pass the check before either commits.
**How to avoid:** `SELECT … FOR UPDATE` on the order row inside a transaction before the UPDATE.
**Warning signs:** `rowCount` on the UPDATE returning 0 for one of two concurrent requests (correct outcome once fixed), or wallet balance being higher than expected.

### Pitfall 2: State Machine Not Applied to ALL Status Endpoints
**What goes wrong:** Fixing `PATCH /orders/:id/status` in server.ts but forgetting `PUT /:id/status` in `src/routes/orders.ts` and `POST /game/orders/:id/deliver` in game.ts.
**Why it happens:** Status is updated in at least 3 separate places in this codebase.
**How to avoid:** Centralize `canTransition()` in `src/lib/stateMachine.ts`; grep all files for `SET status` and audit each one.
**Warning signs:** Tests pass for one endpoint but manual testing of another shows bypassed transitions.

### Pitfall 3: CORS Wildcard Surviving Deployment
**What goes wrong:** `cors()` with no options works fine in development but exposes API to cross-site request forgery in production.
**Why it happens:** `cors()` defaults to `{ origin: '*' }`.
**How to avoid:** Always specify `origin` even in dev (`http://localhost:3000`); read from env so prod uses the real domain automatically.
**Warning signs:** Browser DevTools → Network → Response headers show `Access-Control-Allow-Origin: *`.

### Pitfall 4: Nominatim Rate Limit (429)
**What goes wrong:** If address validation is called during order creation and users submit rapidly, Nominatim returns 429.
**Why it happens:** 1 req/sec limit per IP.
**How to avoid:** Cache geocode results (in-memory Map or Redis) keyed by normalized address string; exponential backoff on 429; or validate address asynchronously after order creation (degraded mode).
**Warning signs:** Geocoding calls returning 429 in logs during load testing.

### Pitfall 5: express-validator Not Catching `req.params.id` Type Errors
**What goes wrong:** SQL receives a non-UUID/non-integer `:id` and throws a DB error instead of returning 422.
**Why it happens:** Express params are always strings; without validation they go straight to `$1` in parameterized query.
**How to avoid:** `param("id").isUUID()` (or `.isInt()`) as first validator on all `:id` routes.

---

## Code Examples

### Current Race Condition Location (game.ts lines 164-184)

```typescript
// CURRENT (BROKEN — no transaction, no row lock)
router.post("/orders/:id/deliver", async (req, res) => {
  const order = await pool.query(            // <-- uses pool, not client
    `UPDATE orders SET status = 'delivered', ... WHERE id = $1 AND status = 'ready' RETURNING *`,
    [id, courier_id]
  );
  if (!order.rowCount) return res.status(404)...;

  const reward = Math.floor(order.rows[0].total_cents / 10);
  await pool.query(                          // <-- separate statement, not same tx
    `INSERT INTO game_wallets ... ON CONFLICT DO UPDATE SET balance_virtual = game_wallets.balance_virtual + $2`,
    [courier_id, reward]
  );
  // If two requests run concurrently: both can claim the same order,
  // because the UPDATE + wallet credit are not atomic.
});
```

### Current Status Endpoint (server.ts — no transition enforcement)

```typescript
// CURRENT (BROKEN — no transition check)
app.patch("/orders/:id/status", async (req, res) => {
  const { status } = req.body ?? {};
  const allowed = ["new", "picking", "ready", "courier", "delivered", "cancelled"];
  if (!allowed.includes(status)) {
    return res.status(400).json({ error: "invalid_status" });
  }
  // Goes straight to UPDATE — no check on CURRENT status
  const result = await pool.query(
    "UPDATE orders SET status = $2 WHERE id = $1 RETURNING id, status",
    [id, status]
  );
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `pg` callbacks | `pg` async/await with Pool | pg v7+ | Already in use in codebase |
| Manual CORS headers | `cors` npm package | ~2015 | Already in use; just needs config |
| Hand-rolled validation | `express-validator` v7 / `zod` | Stable for years | Need to add |
| External geocoding services (Google) | Nominatim (OSM, free) | Free alternative matures | Use for Russia; Yandex as fallback |

**Deprecated/outdated:**
- `express` v4 patterns (callback-style middleware): Express 5 is already installed (`^5.2.1`). Express 5 changes error handling (async errors propagate automatically without `try/catch next(e)`). The current codebase uses explicit try/catch which still works in v5 — no breaking change.

---

## Open Questions

1. **Are order IDs UUIDs or integers?**
   - What we know: In `migration.sql` orders uses `SERIAL PRIMARY KEY` (integer). In `game.ts` route params are used directly. In `server.ts` orders use `id` from INSERT RETURNING which returns integer. However, some code uses `crypto.randomUUID()` for other purposes.
   - What's unclear: Whether the `orders.id` column is actually UUID or SERIAL in the live DB (migration.sql shows SERIAL but SPEC.md mentions a different production DB structure).
   - Recommendation: Query `information_schema.columns` or `\d orders` to confirm column type before writing validators.

2. **What is the production ALLOWED_ORIGIN?**
   - What we know: `PUBLIC_APP_URL` env var exists; `http://localhost:PORT` is the default.
   - What's unclear: Whether there is a deployed frontend domain yet.
   - Recommendation: Set `ALLOWED_ORIGIN=http://localhost:3000` for dev; document that prod must set this env var.

3. **Is entrance (подъезд) validation actually required by the client?**
   - What we know: BACK-05 mentions "valid street/house/entrance, reject invalid addresses." Entrance numbers cannot be validated via free geocoding APIs.
   - What's unclear: Whether the client literally requires entrance validation or just street+house.
   - Recommendation: Validate street + house via Nominatim; accept entrance as a format check only (numeric, 1-99); document limitation.

4. **Node.js runtime version on deployment?**
   - What we know: `package.json` doesn't specify engines. `@types/node@^25.x` suggests Node 22+ in dev.
   - What's unclear: Production runtime. Built-in `fetch` requires Node 18+.
   - Recommendation: Verify production Node version before relying on global `fetch`; fallback is `node-fetch` v3 (ESM) or v2 (CJS).

---

## Sources

### Primary (HIGH confidence)
- Direct codebase read: `/c/Users/1/AppData/Local/Temp/fruits_repo/apps/api/src/server.ts` — CORS, status endpoint
- Direct codebase read: `/c/Users/1/AppData/Local/Temp/fruits_repo/apps/api/src/routes/game.ts` — race condition, wallet logic
- Direct codebase read: `/c/Users/1/AppData/Local/Temp/fruits_repo/apps/api/package.json` — installed dependencies and versions
- PostgreSQL `SELECT FOR UPDATE` docs — standard locking primitive, stable feature
- `cors` npm package README — `{ origin }` option documented

### Secondary (MEDIUM confidence)
- Nominatim API: `https://nominatim.openstreetmap.org/` — free geocoding, usage policy states 1 req/sec and User-Agent requirement
- express-validator v7 documentation — validation chain API

### Tertiary (LOW confidence)
- Yandex Geocoder as fallback — requires API key, Russian coverage known to be better than OSM in dense urban areas; not verified in this session

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — read directly from package.json; Express 5, pg 8, cors all confirmed installed
- Architecture (patterns 1-4): HIGH — PostgreSQL locking primitives are stable; Express middleware patterns are established
- Architecture (pattern 5 Nominatim): MEDIUM — API shape verified from known documentation; rate limits from official ToS
- Pitfalls: HIGH — race condition visible directly in source code; CORS wildcard verified in source
- Open questions: accurately flagged as LOW confidence

**Research date:** 2026-03-15
**Valid until:** 2026-04-15 (stable dependencies; geocoding API shape may change sooner)
