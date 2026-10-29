# Third-party licenses

## brickGame.ts

Game logic (paddle/ball physics, brick layout, collision, level progression) is based on
[lefrasso/Arkanoid](https://github.com/lefrasso/Arkanoid), licensed under the MIT License.
Rendering, UI text, HUD, and asset/sound/theme code were not ported — only the core game-loop
mechanics. Attribution is also kept inline at the top of `brickGame.ts`.

```
MIT License

Copyright (c) 2025 Arkanoid Game Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

Note: "Arkanoid" is a trademark of Taito Corporation. The in-app UI name for this game is
«Кирпичики» — the upstream project name is never shown in the product UI, only in this
attribution file and the source code comment.

## tankGame.ts

Based on [kyuuzou/battle-city](https://github.com/kyuuzou/battle-city), licensed under the MIT
License. That repository is a thin Unity/C# prototype whose only implemented mechanics are: a
level loaded from a text grid where each character maps 1:1 to a tile (`LevelLoader.cs`), a
projectile that moves at constant speed in a straight line and disappears on its first collision
(`Projectile.cs`), and an object that is destroyed on first hit (`Destructible.cs`). Those three
pieces of logic are what's ported. The repo has no enemy AI, no base-defense objective, no lives,
and no level/wave counter — `TankOnRails.cs`/`TankReallistic.cs` are free-physics (Rigidbody)
manual-control scripts, not grid-aligned AI. Grid-aligned 4-direction movement, enemy AI, the
defendable base, lives, and wave/level progression in `tankGame.ts` are original design, built on
top of the ported grid/projectile/destructible mechanics. Attribution is also kept inline at the
top of `tankGame.ts`.

```
MIT License

Copyright (c) 2023 Nelson Rodrigues

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

Note: "Battle City" is a trademark of Namco (Bandai Namco). No original stage layouts, textures,
sounds, or models from any holder of that trademark are used — the 5 stage maps in `tankGame.ts`
are original brick-wall patterns (e.g. letter/word shapes «АКТ», «НДС», «ИТОГО»). The in-app UI
name for this game is «Танчики» — no upstream project/trademark name is shown in the product UI,
only in this attribution file and the source code comment.
