---
phase: 13-v3-drag-drop-n
plan: 07
type: execute
wave: 5
depends_on:
  - 01
  - 02
  - 03
  - 04
  - 05
  - 06
files_modified:
  - e2e/19-wishes-kanban.spec.ts
autonomous: true
requirements:
  - D-01
  - D-03
  - D-05
  - D-06
  - D-07
must_haves:
  truths:
    - "Full user flow works end-to-end: create wish → add items with categories → open kanban → drag card between columns → approve → verify N purchases appear"
    - "Service note download works from wish dialog (file downloads, non-empty .docx)"
    - "Category-required validation blocks product creation (backend 422, frontend disabled button)"
  artifacts:
    - path: "e2e/19-wishes-kanban.spec.ts"
      provides: "Playwright spec with 4-6 scenarios covering happy path + validation + service note + DnD"
      contains: "test('kanban distributes items across N columns'"
  key_links:
    - from: "e2e helper login"
      to: "role that can approve (superadmin or org_admin)"
      via: "e2e/helpers.ts login() with appropriate credentials"
      pattern: "login.*superadmin\\|login.*admin"
    - from: "Playwright drag simulation"
      to: "target column"
      via: "page.dragTo(sourceCard, targetColumn) — vuedraggable uses SortableJS which supports HTML5 DnD events"
      pattern: "dragTo\\|dispatchEvent.*drag"
---

<objective>
End-to-end validation of Phase 13 via Playwright. Covers the whole pipeline from CONTEXT success criteria (§success_criteria 1-6): create wish → distribute items → approve → verify purchases → download service note → enforce category required.

Purpose: Guards against regression — Phase 13 has 5 preceding plans touching backend + DB + frontend simultaneously. A single smoke spec catches integration breakage faster than unit tests alone.

Output: One new spec file `e2e/19-wishes-kanban.spec.ts` following the established pattern from `e2e/18-purchase-items-editor.spec.ts` (from Phase 15).
</objective>

<execution_context>
@C:/Users/1/Desktop/Cursor/VSKS_CRM/.claude/get-shit-done/workflows/execute-plan.md
@C:/Users/1/Desktop/Cursor/VSKS_CRM/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/13-v3-drag-drop-n/CONTEXT.md
@.planning/phases/13-v3-drag-drop-n/13-05-wish-distribution-kanban-PLAN.md

<interfaces>
Playwright helpers from e2e/helpers.ts (existing pattern, Phase 8+):
- `login(page, { role?: 'superadmin' | 'manager' | 'viewer' })` — navigates and logs in
- `waitForOverlays(page)` — closes any snack/dialog overlays
- `collectApiErrors(page)` — returns array of 4xx/5xx seen during test

Existing spec `e2e/18-purchase-items-editor.spec.ts` (Phase 15-05) shows current test patterns — executor MUST grep `e2e/18-purchase-items-editor.spec.ts` to mirror structure.

Deploy target:
- Local: `http://localhost:5173` (default Vite)
- Deploy: `BASE_URL=https://{deploy-url}` (set via env in CI)

vuedraggable DnD note: SortableJS (the underlying library) uses real HTML5 drag events. Playwright's native `dragAndDrop(sourceLocator, targetLocator)` generally works with it. If not, use:
```typescript
await page.locator(sourceSelector).dragTo(page.locator(targetSelector))
```
or manual mouse events:
```typescript
const source = page.locator('[data-testid="wish-card-{id}"]')
const target = page.locator('[data-testid="kanban-col-{key}"]')
await source.hover()
await page.mouse.down()
await target.hover()
await page.mouse.up()
```
Executor chooses based on what works with the specific vuedraggable version.

IMPORTANT: For DnD to be testable, Plan 13-05 components should include `data-testid` attributes. If they don't, Plan 13-07 executor may need to add minimal `data-testid` attributes to WishDistributionKanban.vue / WishDistributionCard.vue — this is explicitly allowed as part of THIS plan.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Create e2e/19-wishes-kanban.spec.ts with 4+ scenarios</name>
  <read_first>
    - e2e/18-purchase-items-editor.spec.ts (pattern template — Phase 15-05 smoke spec)
    - e2e/helpers.ts (login, waitForOverlays, collectApiErrors utilities)
    - e2e/05-orders.spec.ts (example: navigating to edit views, interacting with PurchaseItemsEditor — applicable to wishes too after Phase 15)
    - frontend/src/components/WishDistributionKanban.vue (after Plan 13-05 — find selectors for cards/columns; may need to add data-testid)
    - frontend/src/views/WishesView.vue (after Plans 13-05 + 13-06 — button selectors, dialog structure)
    - .planning/phases/13-v3-drag-drop-n/CONTEXT.md (success_criteria — maps 1:1 to test scenarios)
  </read_first>
  <action>
    === Step 1: If needed, add data-testid attributes to kanban components ===
    In `frontend/src/components/WishDistributionKanban.vue`:
    - Add to the column div: `:data-testid="'kanban-col-' + col.key"`
    - Add to column header title: `:data-testid="'kanban-col-title-' + col.key"`
    - Add to approve button: `data-testid="kanban-approve-btn"`

    In `frontend/src/components/WishDistributionCard.vue`:
    - Add to card root: `:data-testid="'wish-card-' + item.id"`
    - Add to card name: `data-testid="wish-card-name"`

    In `frontend/src/views/WishesView.vue`:
    - Add to service-note button: `data-testid="wish-download-servicenote"`
    - Add to servicenote dialog confirm button: `data-testid="wish-servicenote-confirm"`

    === Step 2: Create e2e/19-wishes-kanban.spec.ts ===

    ```typescript
    import { test, expect } from '@playwright/test'
    import { login, waitForOverlays, collectApiErrors } from './helpers'

    test.describe('Phase 13 — Wishes v3 kanban', () => {
      test.beforeEach(async ({ page }) => {
        await login(page, { role: 'superadmin' })  // or whichever role can approve wishes
      })

      test('kanban renders columns grouped by product.category + «Не определено»', async ({ page }) => {
        const apiErrors = collectApiErrors(page)

        await page.goto('/wishes')
        await waitForOverlays(page)

        // Create a wish (click "+ Новая заявка" or similar)
        await page.getByRole('button', { name: /новая заявка|создать|добавить/i }).first().click()
        await waitForOverlays(page)

        // Select subsidy
        // ... (based on actual form — executor fills this in)

        // Add 3 items via PurchaseItemsEditor — pick products from different categories
        // ... (use getByText, .click() on product autocomplete entries, set quantity/price)

        // Save as draft
        await page.getByRole('button', { name: /сохранить|черновик/i }).first().click()
        await waitForOverlays(page)

        // Reopen wish → kanban should appear
        await page.getByText(/Тестовая заявка|черновик/i).first().click()

        // Assert: at least 2 columns visible (uncat + real)
        const cols = page.locator('[data-testid^="kanban-col-"]')
        await expect(cols).toHaveCount({ minimum: 2 } as any)  // use .nth/count assertions

        // «Не определено» always first
        const firstColTitle = await page.locator('[data-testid^="kanban-col-title-"]').first().textContent()
        expect(firstColTitle).toContain('Не определено')

        // No API errors
        expect(apiErrors.filter(e => e.status >= 400)).toHaveLength(0)
      })

      test('drag card from column A to column B persists', async ({ page }) => {
        // Setup: assume a wish with 2 items in different categories already exists
        // Open it
        await page.goto('/wishes')
        await page.getByText(/Тестовая/i).first().click()
        await waitForOverlays(page)

        const source = page.locator('[data-testid^="wish-card-"]').first()
        const targetCol = page.locator('[data-testid^="kanban-col-"]').nth(1).locator('.wish-kanban-col-body')

        await source.dragTo(targetCol)

        // Wait for PATCH to complete (network idle or snackbar)
        await page.waitForResponse(r => r.url().includes('/items/') && r.request().method() === 'PATCH')

        // Reload the wish dialog — card should still be in new column
        await page.reload()
        await page.getByText(/Тестовая/i).first().click()
        // W8 (revision 1): assert on a concrete fixture item name, not empty string.
        const DND_ITEM_NAME = 'Тестовая карточка 1'  // fixed constant — MUST match the item added to the wish in Scenario 1
        const newColContent = await page.locator('[data-testid^="kanban-col-"]').nth(1).textContent()
        expect(newColContent).toContain(DND_ITEM_NAME)
      })

      test('approve creates N purchases and makes wish read-only', async ({ page, request }) => {
        await page.goto('/wishes')
        await page.getByText(/Тестовая/i).first().click()
        await waitForOverlays(page)

        // Count columns before approving
        const colCount = await page.locator('[data-testid^="kanban-col-"]:not([data-empty])').count()

        // Stub window.confirm to auto-accept
        page.on('dialog', async d => await d.accept())

        // Click approve
        await page.locator('[data-testid="kanban-approve-btn"]').click()

        // Wait for success banner
        await expect(page.getByText(/Создано закупок/i)).toBeVisible({ timeout: 10000 })

        // Verify N purchases via API
        const headers = { Cookie: await page.context().cookies().then(cs => cs.map(c => `${c.name}=${c.value}`).join('; ')) }
        const resp = await request.get('/api/purchases/?status=wishes&limit=50', { headers })
        expect(resp.ok()).toBeTruthy()
        const purchases = await resp.json()
        // At least colCount purchases with the wish's title prefix should exist
        // (executor: refine based on wish title)

        // After approve: approve button should no longer be visible (readonly)
        await expect(page.locator('[data-testid="kanban-approve-btn"]')).toHaveCount(0)
      })

      test('download service note from wish dialog', async ({ page }) => {
        await page.goto('/wishes')
        await page.getByText(/Тестовая/i).first().click()
        await waitForOverlays(page)

        await page.locator('[data-testid="wish-download-servicenote"]').click()
        await waitForOverlays(page)

        // Pick initiator (autocomplete)
        await page.locator('input[label*="Инициатор"], input[aria-label*="Инициатор"]').first().click()
        await page.locator('.v-list-item-title').first().click()

        // Trigger download
        const [download] = await Promise.all([
          page.waitForEvent('download'),
          page.locator('[data-testid="wish-servicenote-confirm"]').click(),
        ])
        const path = await download.path()
        expect(path).toBeTruthy()
        // Verify it's a real .docx (non-empty, starts with PK zip magic bytes)
        const fs = await import('fs')
        const buf = fs.readFileSync(path!)
        expect(buf.length).toBeGreaterThan(1000)
        expect(buf.subarray(0, 2).toString('hex')).toBe('504b')  // ZIP/DOCX magic
      })

      test('category is required when creating product via PurchaseItemsEditor', async ({ page }) => {
        await page.goto('/wishes')
        await page.getByRole('button', { name: /новая заявка|создать/i }).first().click()
        await waitForOverlays(page)

        // Open full product dialog
        await page.getByRole('button', { name: /добавить товар|новый товар/i }).first().click()
        await waitForOverlays(page)

        // Fill name, leave category empty
        await page.locator('input[label*="Название"]').first().fill('Тест категория required')

        // Save button should be disabled
        const saveBtn = page.getByRole('button', { name: /сохранить/i }).last()
        await expect(saveBtn).toBeDisabled()

        // Fill category — save becomes enabled
        await page.locator('input[label*="Категория"]').first().fill('Электроника')
        await expect(saveBtn).toBeEnabled()
      })
    })
    ```

    Executor notes:
    - Fill in specific selectors based on actual WishesView markup after Plans 13-05 and 13-06 land
    - The `login()` helper and test org/user fixtures must match `e2e/helpers.ts` existing patterns
    - If drag simulation via `page.dragTo()` fails with vuedraggable, fall back to manual mouse events
    - For the `approve` test, cleaning up created purchases at test end is optional — they're valid test artifacts
  </action>
  <verify>
    <automated>cd "C:/Users/1/Desktop/Cursor/VSKS_CRM" && npx playwright test e2e/19-wishes-kanban.spec.ts --reporter=list</automated>
  </verify>
  <acceptance_criteria>
    - File `e2e/19-wishes-kanban.spec.ts` exists
    - `grep -cE "^  test\\(" e2e/19-wishes-kanban.spec.ts` returns at least 4
    - **W8 (revision 1):** `grep -c "toContain(''" e2e/19-wishes-kanban.spec.ts` MUST return 0 (no empty-string always-true assertions)
    - **W8 (revision 1):** `grep -qE "DND_ITEM_NAME|Тестовая карточка" e2e/19-wishes-kanban.spec.ts` MUST match (concrete fixture constant in assertion)
    - `grep -q "data-testid" frontend/src/components/WishDistributionKanban.vue` (attributes added if not present)
    - `grep -q "data-testid=\"kanban-approve-btn\"" frontend/src/components/WishDistributionKanban.vue`
    - `grep -q "data-testid=\"wish-download-servicenote\"" frontend/src/views/WishesView.vue`
    - `npx playwright test e2e/19-wishes-kanban.spec.ts` on local deploy → all scenarios green (5/5 or 4/4)
  </acceptance_criteria>
  <done>
    E2E spec covers kanban rendering, DnD persistence, approve→N purchases, service note download, category required. All scenarios green locally; ready to run against deploy.
  </done>
</task>

</tasks>

<verification>
- `npx playwright test e2e/19-wishes-kanban.spec.ts` green locally
- Optional: also run `BASE_URL=https://crm.vsks.ru npx playwright test e2e/19-wishes-kanban.spec.ts` on deploy (per CLAUDE.md Playwright rule)
- Full e2e suite still green (no regression from data-testid additions)
</verification>

<success_criteria>
1. Spec file exists with 4+ scenarios
2. Happy path: create → distribute → approve → purchases visible
3. Validation: category required blocks submission
4. Service note downloads valid .docx
5. DnD persists across reload
6. All tests pass on local deploy
</success_criteria>

<output>
After completion, create `.planning/phases/13-v3-drag-drop-n/13-07-SUMMARY.md`
</output>
