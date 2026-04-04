---
phase: quick-1-fruitshop
plan: "01"
subsystem: game-visuals
tags: [textures, game, fruitshop, visuals]
key-files:
  modified:
    - /c/Users/1/AppData/Local/Temp/fruits_repo/apps/game/make_textures.cjs
    - /c/Users/1/AppData/Local/Temp/fruits_repo/apps/game/src/blocks.ts
    - /c/Users/1/AppData/Local/Temp/fruits_repo/apps/game/src/world.ts
  created:
    - /c/Users/1/AppData/Local/Temp/fruits_repo/apps/game/public/textures/sign_store.png
decisions:
  - "All texture coordinates scaled proportionally by sc=S/32 factor, not hardcoded"
  - "Latin M/E/T/R/O added as separate FONT entries (Cyrillic keys are different Unicode codepoints)"
metrics:
  duration: ~15min
  completed: "2026-03-27"
  tasks_completed: 3
  tasks_total: 3
  files_modified: 3
  files_created: 1
---

# Quick Task 1: FruitShop — Texture Upgrade + METRO Sign Summary

**One-liner:** 64x64 texture resolution upgrade with proportional coordinate scaling, METRO store entrance sign, and double-height section signs.

## What Was Done

### Task 1: Texture Resolution S=32 -> S=64 (make_textures.cjs)
- Changed `const S = 64`
- Replaced all hardcoded pixel coordinates with proportional expressions (`Math.round(X * S / 32)` or `S/N` fractions)
- Updated: floor grid, ceiling tile pattern, shelf_frame bolt holes, shelf_plank wire grid, glass inner border, light.png tube positions + corner brackets, conveyor wear band + chevron, checkout grooves + buttons, floor_tile_white grout lines, wall_white seam lines, checkout_sign checkmark + text y
- `makeSectionSign`: text y scaled from `23` to `Math.round(S*23/32)`
- All 6 section sign icons: coordinates scaled by `sc = S/32`
- All 8 product textures: coordinates scaled by `sc = S/32`
- Added Latin glyphs M, E, T, R, O to FONT object (separate from Cyrillic 'М','Т','О')
- Added `sign_store.png` generator: dark navy bg, yellow bottom stripe, white "METRO" text

### Task 2: blocks.ts — SIGN_STORE=30
- Added `SIGN_STORE: 30` to BlockType enum
- Added `[BlockType.SIGN_STORE]: 'textures/sign_store.png'` to BLOCK_TEXTURES
- Extended `isSign` range from `<= SIGN_VEGET` to `<= SIGN_STORE` (non-solid walk-through blocks)

### Task 3: world.ts — Double Height Signs + METRO Back Wall
- All 6 section signs now placed at both y=4 AND y=5 (double height)
- Signs widened by 1-2 blocks: MEAT 7..13, BREAD 7..13, DRINKS 23..29, DAIRY 7..15, FRUIT 7..14, VEGET 23..30
- SIGN_STORE placed on back wall: z=0, x=14..25, y=2..4 (large 12-wide x 3-tall METRO sign)

## Verification

- `node make_textures.cjs` completes without errors: "All 30 textures generated at 64x64!"
- `public/textures/sign_store.png` exists: 445 bytes
- All 3 success criteria satisfied

## Deviations from Plan

None - plan executed exactly as written.

## Commits

| Task | Commit  | Description |
|------|---------|-------------|
| 1    | 103972d | feat(quick-1-01): upgrade texture resolution S=32→64, add METRO sign |
| 2    | 560b310 | feat(quick-1-01): add SIGN_STORE=30 to blocks.ts, extend isSign range |
| 3    | 199a137 | feat(quick-1-01): double-height section signs + METRO sign on back wall |

## Self-Check: PASSED

- [x] `/c/Users/1/AppData/Local/Temp/fruits_repo/apps/game/public/textures/sign_store.png` — exists (445 bytes)
- [x] `make_textures.cjs` S=64 confirmed
- [x] blocks.ts SIGN_STORE:30 at lines 35, 70, 85
- [x] world.ts y=5 signs confirmed at lines 121, 133, 137, 153, 163, 167
- [x] Commits 103972d, 560b310, 199a137 in gameclaw branch
