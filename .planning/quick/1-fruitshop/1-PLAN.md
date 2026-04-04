---
phase: quick-1-fruitshop
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - /c/Users/1/AppData/Local/Temp/fruits_repo/apps/game/make_textures.cjs
  - /c/Users/1/AppData/Local/Temp/fruits_repo/apps/game/src/blocks.ts
  - /c/Users/1/AppData/Local/Temp/fruits_repo/apps/game/src/world.ts
autonomous: true
requirements: [FRUITSHOP-VISUAL-01]
must_haves:
  truths:
    - "Текстуры рендерятся в 64×64 пикселей (чётче, крупнее)"
    - "Вывески секций занимают два блока высоты (y=4 и y=5) — выглядят крупными"
    - "На задней стене (z=0) висит большая вывеска METRO на тёмно-синем фоне"
    - "node make_textures.cjs завершается без ошибок и генерирует sign_store.png"
  artifacts:
    - path: "/c/Users/1/AppData/Local/Temp/fruits_repo/apps/game/public/textures/sign_store.png"
      provides: "Текстура вывески METRO"
    - path: "/c/Users/1/AppData/Local/Temp/fruits_repo/apps/game/src/blocks.ts"
      contains: "SIGN_STORE: 30"
  key_links:
    - from: "blocks.ts SIGN_STORE=30"
      to: "blocks.ts BLOCK_TEXTURES[30]"
      via: "record entry"
    - from: "blocks.ts registerBlocks"
      to: "isSign range check"
      via: "id >= SIGN_DAIRY && id <= SIGN_STORE"
    - from: "world.ts SIGN_STORE placement"
      to: "back wall z=0"
      via: "map.set(x, y, 0, BlockType.SIGN_STORE)"
---

<objective>
Улучшить визуализацию магазина FruitShop: увеличить разрешение текстур S=32→64, сделать вывески секций двойной высоты, добавить большую вывеску METRO на заднюю стену.

Purpose: Магазин выглядит мелко и плоско — крупные текстуры и высокие вывески делают его читаемым.
Output: Обновлённые make_textures.cjs + blocks.ts + world.ts + сгенерированные PNG.
</objective>

<execution_context>
Game directory: /c/Users/1/AppData/Local/Temp/fruits_repo/apps/game/
Run textures: node make_textures.cjs  (from that directory)
</execution_context>

<context>
<!-- Key state of current files -->

make_textures.cjs (line 6): const S = 32;
- createTexture() creates PNG width=S, height=S
- Coordinate literals are hardcoded: 16 (=S/2), 24 (=S*3/4), 8 (=S/4), etc.
- drawTextCentered uses S internally via Math.floor((S - totalW) / 2) — already S-relative
- FONT has only Cyrillic glyphs (А-Я subset). No Latin letters exist yet.
- makeSectionSign() draws icon + text at y=23 (bottom area of 32px canvas)
- Light.png uses corners [[2,2],[29,2],[2,29],[29,29]] — hardcoded 29=S-3

blocks.ts:
- Last block: LIGHT: 29
- BLOCK_TEXTURES maps each id to textures/xxx.png
- registerBlocks: isSign = id >= SIGN_DAIRY && id <= SIGN_VEGET (23..28)
  → this range check MUST be extended to include SIGN_STORE=30

world.ts:
- Section signs at y=4 only (single row):
  SIGN_MEAT:  x=8..12,  z=2
  SIGN_BREAD: x=8..12,  z=8
  SIGN_DRINKS: x=24..28, z=8
  SIGN_DAIRY: x=8..14,  z=15
  SIGN_FRUIT: x=8..13,  z=22
  SIGN_VEGET: x=24..29, z=22
- Walls go up to y=5 (loop: for y=1..5)
- Back wall at z=0, full width x=0..W-1 (W=40)
</context>

<tasks>

<task type="auto">
  <name>Task 1: Увеличить S до 64 и заменить hardcoded координаты пропорциями</name>
  <files>/c/Users/1/AppData/Local/Temp/fruits_repo/apps/game/make_textures.cjs</files>
  <action>
Открыть make_textures.cjs и выполнить следующие изменения:

**1. Изменить S:**
```js
const S = 64; // texture resolution (64×64)
```

**2. Заменить все абсолютные координаты пропорциями от S.**

Правило замены (S=32 → S=64, масштаб ×2):
- Каждый hardcoded пиксельный литерал X заменить на `Math.round(X * S / 32)` ИЛИ, если значение простое, на выражение через S:
  - `16` → `Math.round(S/2)`
  - `8`  → `Math.round(S/4)`
  - `24` → `Math.round(S*3/4)`
  - `4`  → `Math.round(S/8)`
  - `2`  → `Math.round(S/16)`
  - `1`  → `Math.round(S/32)` (или просто оставить `1` где это padding/border — на усмотрение)
  - `29` (= S-3) → `S-3`
  - `28` (= S-4) → `S-4`
  - Прочие числа X → `Math.round(X * S / 32)`

**ВАЖНО:** Функции-помощники `createTexture`, `px`, `fill`, `circle`, `ellipse`, `hline`, `vline`, `dnoise`, `fillNoise` уже используют S или просто итерируют — их НЕ трогать кроме случаев где есть конкретные числа.

**Функции которые НУЖНО обновить** (в них есть hardcoded координаты):
- `floor.png` creator: `i <= 31` → `i <= S-1`; `i += 15` → `i += Math.round(S/2)-1`
- `ceiling.png`: `i += 16` → `i += Math.round(S/2)`; `cx = qx*16+8` → `cx = qx*Math.round(S/2)+Math.round(S/4)`; radius `2` → `Math.round(S/16)`
- `shelf_frame.png`: bolt holes `[8,16,24]` → `[Math.round(S/4), Math.round(S/2), Math.round(S*3/4)]`; center highlight `14,15,16` → `Math.round(S/2)-2, Math.round(S/2)-1, Math.round(S/2)`; edge `px(png, S-1, ...)` уже ОК
- `shelf_plank.png`: `y+=4` → `y += Math.round(S/8)`; `x+=4` → `x += Math.round(S/8)`; top highlight `3` → `Math.round(S/10)` (или просто 6)
- `glass.png`: inner border `2` → `Math.round(S/16)`, `S-3` → `S-3`; highlight band `4..20` → `Math.round(S/8)..Math.round(S*5/8)`; bottom-right tint `S/2` → `S/2`
- `light.png`: tubes `fill(png, 2, 10, S-4, 2, ...)` и `fill(png, 2, 20, S-4, 2, ...)` → y=10→`Math.round(S*10/32)`, y=20→`Math.round(S*20/32)`; glow lines y=9,12,19,22 → пропорционально; corners `[[2,2],[29,2],[2,29],[29,29]]` → `[[2,2],[S-3,2],[2,S-3],[S-3,S-3]]`
- `conveyor.png`: `12..20` center wear → `Math.round(S*12/32)..Math.round(S*20/32)`; chevron coords → пропорционально
- `checkout.png`: `i += 8` → `i += Math.round(S/4)`; button coords `6,12` → `Math.round(S*6/32), Math.round(S*12/32)`
- `floor_tile_white.png`: `grout = [0,1,15,16,S-2,S-1]` → `[0, 1, Math.round(S/2)-1, Math.round(S/2), S-2, S-1]`; tile highlight `bx = qx*16+2` → `qx*Math.round(S/2)+2`
- `wall_white.png`: `y+=8` → `y += Math.round(S/4)`
- `checkout_sign.png`: checkmark fill positions → масштабировать; `drawTextCentered(png, 'КАССА', 20, ...)` → y=20 → `Math.round(S*20/32)`
- `makeSectionSign`: text y=`23` → `Math.round(S*23/32)`; icon draws внутри каждого sign: все координаты масштабировать ×2 (т.е. `* S/32`)
- Все `drawTextCentered(png, text, y, ...)` вызовы где y=hardcoded → `Math.round(y_old * S / 32)`
- Все product textures (product_red, product_orange и т.д.): координаты circle/fill/ellipse → масштабировать `* S/32`

**Добавить латинские буквы в FONT** (нужны для "METRO"):
```js
'M': [1,0,1, 1,1,1, 1,1,0, 1,0,1, 1,0,1],  // М уже есть как 'М'
'E': [1,1,1, 1,0,0, 1,1,0, 1,0,0, 1,1,1],
'T': [1,1,1, 0,1,0, 0,1,0, 0,1,0, 0,1,0],  // Т уже есть как 'Т'
'R': [1,1,0, 1,0,1, 1,1,0, 1,1,0, 1,0,1],
'O': [0,1,0, 1,0,1, 1,0,1, 1,0,1, 0,1,0],  // О уже есть как 'О'
```
Добавить их в объект FONT рядом с кириллическими (они не конфликтуют, разные ключи).

**Добавить генерацию sign_store.png** в конце файла, после sign_veget:
```js
// sign_store.png — store entrance sign: METRO
createTexture('sign_store.png', (png) => {
  // Dark navy background
  fill(png, 0, 0, S, S, 10, 20, 80);
  // Border
  for (let i = 0; i < S; i++) {
    px(png, 0, i, 5, 10, 50);   px(png, S-1, i, 5, 10, 50);
    px(png, i, 0, 5, 10, 50);   px(png, i, S-1, 5, 10, 50);
  }
  // Yellow stripe at bottom third
  fill(png, 1, Math.round(S*2/3), S-2, Math.round(S/6), 240, 180, 0);
  // White "METRO" text centered vertically in upper 2/3
  drawTextCentered(png, 'METRO', Math.round(S/4), 255, 255, 255);
  // Thin white line above yellow stripe
  for (let x = 1; x < S-1; x++) px(png, x, Math.round(S*2/3)-1, 200, 200, 200);
});
```
  </action>
  <verify>
    <automated>cd /c/Users/1/AppData/Local/Temp/fruits_repo/apps/game && node make_textures.cjs 2>&1 | tail -5</automated>
  </verify>
  <done>
    - `node make_textures.cjs` завершается без ошибок
    - В выводе есть строки sign_store.png и все остальные текстуры
    - public/textures/sign_store.png существует и имеет размер > 200 bytes
    - Размер других PNG примерно в 4 раза больше прежнего (64×64 vs 32×32)
  </done>
</task>

<task type="auto">
  <name>Task 2: blocks.ts — добавить SIGN_STORE + расширить isSign диапазон</name>
  <files>/c/Users/1/AppData/Local/Temp/fruits_repo/apps/game/src/blocks.ts</files>
  <action>
**В объекте BlockType** добавить после `LIGHT: 29`:
```typescript
  SIGN_STORE: 30,      // Store entrance sign: METRO
```

**В BLOCK_TEXTURES** добавить после `[BlockType.LIGHT]` entry:
```typescript
  [BlockType.SIGN_STORE]:    'textures/sign_store.png',
```

**В registerBlocks** найти строку:
```typescript
const isSign = id >= BlockType.SIGN_DAIRY && id <= BlockType.SIGN_VEGET
```
Заменить на:
```typescript
const isSign = id >= BlockType.SIGN_DAIRY && id <= BlockType.SIGN_STORE
```
Это делает SIGN_STORE non-solid (walk-through), как и остальные знаки.
  </action>
  <verify>
    <automated>cd /c/Users/1/AppData/Local/Temp/fruits_repo/apps/game && grep -n "SIGN_STORE" src/blocks.ts</automated>
  </verify>
  <done>
    - SIGN_STORE: 30 присутствует в BlockType
    - BLOCK_TEXTURES содержит запись для id 30 → textures/sign_store.png
    - isSign диапазон включает id=30
  </done>
</task>

<task type="auto">
  <name>Task 3: world.ts — двойная высота секционных знаков + вывеска METRO на задней стене</name>
  <files>/c/Users/1/AppData\Local\Temp\fruits_repo\apps\game\src\world.ts</files>
  <action>
**1. Двойная высота для всех 6 секционных знаков** — добавить y=5 в дополнение к y=4, также расширить по X где возможно.

Найти и заменить каждый блок размещения знаков:

SIGN_MEAT (z=2):
```typescript
// Было:
for (let x = 8; x <= 12; x++) map.set(x, 4, 2, BlockType.SIGN_MEAT)
// Стало:
for (let x = 7; x <= 13; x++) {
  map.set(x, 4, 2, BlockType.SIGN_MEAT)
  map.set(x, 5, 2, BlockType.SIGN_MEAT)
}
```

SIGN_BREAD (z=8):
```typescript
// Было:
for (let x = 8; x <= 12; x++) map.set(x, 4, 8, BlockType.SIGN_BREAD)
// Стало:
for (let x = 7; x <= 13; x++) {
  map.set(x, 4, 8, BlockType.SIGN_BREAD)
  map.set(x, 5, 8, BlockType.SIGN_BREAD)
}
```

SIGN_DRINKS (z=8):
```typescript
// Было:
for (let x = 24; x <= 28; x++) map.set(x, 4, 8, BlockType.SIGN_DRINKS)
// Стало:
for (let x = 23; x <= 29; x++) {
  map.set(x, 4, 8, BlockType.SIGN_DRINKS)
  map.set(x, 5, 8, BlockType.SIGN_DRINKS)
}
```

SIGN_DAIRY (z=15):
```typescript
// Было:
for (let x = 8; x <= 14; x++) map.set(x, 4, 15, BlockType.SIGN_DAIRY)
// Стало:
for (let x = 7; x <= 15; x++) {
  map.set(x, 4, 15, BlockType.SIGN_DAIRY)
  map.set(x, 5, 15, BlockType.SIGN_DAIRY)
}
```

SIGN_FRUIT (z=22):
```typescript
// Было:
for (let x = 8; x <= 13; x++) map.set(x, 4, 22, BlockType.SIGN_FRUIT)
// Стало:
for (let x = 7; x <= 14; x++) {
  map.set(x, 4, 22, BlockType.SIGN_FRUIT)
  map.set(x, 5, 22, BlockType.SIGN_FRUIT)
}
```

SIGN_VEGET (z=22):
```typescript
// Было:
for (let x = 24; x <= 29; x++) map.set(x, 4, 22, BlockType.SIGN_VEGET)
// Стало:
for (let x = 23; x <= 30; x++) {
  map.set(x, 4, 22, BlockType.SIGN_VEGET)
  map.set(x, 5, 22, BlockType.SIGN_VEGET)
}
```

**2. Разместить SIGN_STORE на задней стене (z=0)** — добавить ПОСЛЕ секции стен (после блока `// ============ WALLS ============`), но ДО секций с полками:

```typescript
  // ============ STORE SIGN (back wall, z=0) ============
  // Large METRO sign: x=14..25, y=2..4
  for (let x = 14; x <= 25; x++) {
    for (let y = 2; y <= 4; y++) {
      map.set(x, y, 0, BlockType.SIGN_STORE)
    }
  }
```

Знак перекрывает WALL_WHITE на этих позициях — это ожидаемо, вывеска висит на стене.
  </action>
  <verify>
    <automated>cd /c/Users/1/AppData/Local/Temp/fruits_repo/apps/game && grep -n "SIGN_STORE\|y, 5, " src/world.ts | head -20</automated>
  </verify>
  <done>
    - Каждый из 6 знаков имеет два цикла map.set: y=4 и y=5
    - SIGN_STORE размещён на z=0, x=14..25, y=2..4
    - TypeScript компилируется без ошибок (import BlockType подтягивает новое поле)
  </done>
</task>

</tasks>

<verification>
После всех трёх задач выполнить:
```bash
cd /c/Users/1/AppData/Local/Temp/fruits_repo/apps/game
node make_textures.cjs
ls -la public/textures/sign_store.png
# Ожидается: файл существует, размер ~2-4KB
```
</verification>

<success_criteria>
- S=64 в make_textures.cjs
- node make_textures.cjs запускается без ошибок
- sign_store.png сгенерирован
- blocks.ts: SIGN_STORE=30, в BLOCK_TEXTURES, isSign диапазон включает 30
- world.ts: все 6 знаков секций двойной высоты (y=4 И y=5), вывеска METRO на z=0
</success_criteria>

<output>
После завершения создать `.planning/quick/1-fruitshop/1-SUMMARY.md` с кратким описанием изменений.
</output>
