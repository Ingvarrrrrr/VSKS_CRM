---
plan: 13-06-wish-service-note-button
phase: 13-v3-drag-drop-n
status: complete
completed: 2026-04-20
---

# SUMMARY — 13-06 Wish Service Note Button

## What was built
- "Скачать служебную записку" / "Служебная записка" buttons added to wish cards in `frontend/src/views/WishesView.vue`:
  - Visible on submitted wishes (next to Распределить / Быстрое одобрение / Отклонить).
  - Also visible on draft / approved / converted wishes via compact "Скачать служебную записку" text button.
  - Hidden on rejected wishes.
- `downloadServiceNote(wish)` function uses `fetch('/api/wishes/{id}/documents/service_note')` with `Authorization: Bearer ${localStorage.auth_token}` (project-canonical key per `frontend/src/api.ts:4`, NOT `'token'`). Streams blob → triggers download as `service_note_wish_${id}.docx`.
- Per-wish loading state via `downloadingServiceNoteId` ref.

## Key commit
Bundled into the same 13-05 integration commit (single-file WishesView edit with kanban + service-note — keeps atomic scope).

## Coverage
- D-07 frontend half — ✓ (backend is 13-03)

## Notes
- Uses direct `fetch` not `apiFetch` because blob response handling differs; auth token pulled from `localStorage.getItem('auth_token')` matching project convention. No hardcoded `'token'` key.
