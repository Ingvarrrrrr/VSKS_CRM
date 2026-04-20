---
phase: 13-v3-drag-drop-n
plan: 04
type: execute
wave: 1
depends_on: []
files_modified:
  - frontend/src/components/AdvancedProductSelector.vue
  - frontend/src/components/PurchaseItemsEditor.vue
autonomous: true
requirements:
  - D-03
must_haves:
  truths:
    - "In AdvancedProductSelector full-product dialog, save is disabled until category is non-empty"
    - "In PurchaseItemsEditor full-product dialog (line ~402), category field is marked required with validation rule"
    - "Submitting without category shows a visible validation error near the category field"
  artifacts:
    - path: "frontend/src/components/AdvancedProductSelector.vue"
      provides: "Required category field in full-product creation dialog with reactive disabled submit"
      contains: ":rules=\"[v => !!v || 'Категория обязательна'"
    - path: "frontend/src/components/PurchaseItemsEditor.vue"
      provides: "Same required rule on line 402 v-combobox category field"
      contains: ":rules=\"[v => !!v || 'Категория обязательна'"
  key_links:
    - from: "Save button in full-product dialog"
      to: "fullProductForm.category value"
      via: ":disabled computed on !fullProductForm.category"
      pattern: ":disabled=.*!fullProductForm.category"
---

<objective>
Frontend half of CONTEXT D-03. Make `category` required in both product-creation dialogs (AdvancedProductSelector and PurchaseItemsEditor) so the UI matches the NOT NULL DB constraint landed in Plan 13-01. No architectural changes — pure validation + disabled-submit wiring.

Purpose: Without this, users hitting the form before 13-01's migration lands will see 422 errors from the backend. With this, they get inline Vuetify validation — better UX.

Output:
- `<v-combobox v-model="fullProductForm.category" :rules="[v => !!v || 'Категория обязательна']" required>` in both files
- Save/submit button gated by `!fullProductForm.category` check
- No other behavior change
</objective>

<execution_context>
@C:/Users/1/Desktop/Cursor/VSKS_CRM/.claude/get-shit-done/workflows/execute-plan.md
@C:/Users/1/Desktop/Cursor/VSKS_CRM/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/13-v3-drag-drop-n/CONTEXT.md

<interfaces>
From frontend/src/components/AdvancedProductSelector.vue:
- Full product create dialog (scan around line 480 `onProductAdded`, dialog template earlier in file)
- `newProduct.category` binding — currently Optional string

From frontend/src/components/PurchaseItemsEditor.vue line 402:
```vue
<v-combobox v-model="fullProductForm.category"
  :items="fullProductCategoryOptions"
  label="Категория" variant="outlined" density="compact" clearable
  hint="Выберите или введите новую" persistent-hint />
```
Must become:
```vue
<v-combobox v-model="fullProductForm.category"
  :items="fullProductCategoryOptions"
  label="Категория *"
  :rules="[v => (!!v && String(v).trim().length > 0) || 'Категория обязательна']"
  required
  variant="outlined" density="compact"
  hint="Выберите или введите новую (обязательное поле)" persistent-hint />
```

`fullProductForm` structure confirmed at line 1033, 1091, 1119 (category: ''  / category: fullProductForm.category || null).

Save button for full-product dialog — executor MUST locate by grep for "Сохранить" or "createFullProduct" or dialog close action near `fullProductForm`.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Make category required in PurchaseItemsEditor full-product dialog</name>
  <read_first>
    - frontend/src/components/PurchaseItemsEditor.vue lines 395-420 (v-combobox category binding)
    - frontend/src/components/PurchaseItemsEditor.vue (find "fullProductForm" save/submit button — grep for "saveFullProduct" or "createFullProduct" or "Сохранить товар" to identify)
    - frontend/src/components/PurchaseItemsEditor.vue line 1119 (the API payload construction — confirm `category: fullProductForm.category || null` should NOT fall back to null anymore)
    - .planning/phases/13-v3-drag-drop-n/CONTEXT.md (D-03)
  </read_first>
  <action>
    Step 1: Replace line 401-406 (the `v-combobox` for category):
    ```vue
    <v-col cols="12" md="4">
      <v-combobox v-model="fullProductForm.category"
        :items="fullProductCategoryOptions"
        label="Категория *"
        :rules="[v => (!!v && String(v).trim().length > 0) || 'Категория обязательна']"
        required
        variant="outlined" density="compact"
        hint="Выберите или введите новую (обязательное поле)" persistent-hint />
    </v-col>
    ```

    Step 2: Find the save button for this dialog (grep `fullProductForm` + `@click` in template portion, typically "Сохранить товар" or similar). Add `:disabled` binding:
    ```vue
    <v-btn color="primary"
      :disabled="!fullProductForm.category || !String(fullProductForm.category).trim() || (other existing conditions)"
      @click="saveFullProduct">Сохранить</v-btn>
    ```
    The exact existing button text/handler depends on the file. Executor MUST preserve existing `:disabled` conditions by combining with `||`.

    Step 3: Update line 1119 payload construction — remove `|| null` fallback since category is now required:
    Before: `category: fullProductForm.category || null,`
    After:  `category: (fullProductForm.category || '').trim(),`
  </action>
  <verify>
    <automated>cd frontend && npm run build 2>&1 | tee /tmp/fe_build.log | grep -iE "error|fail" | grep -v "info" | head -20; test ! -s <(grep -iE "^(error|build failed)" /tmp/fe_build.log) && echo "BUILD OK"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "'Категория обязательна'" frontend/src/components/PurchaseItemsEditor.vue`
    - `grep -q "label=\"Категория \\*\"" frontend/src/components/PurchaseItemsEditor.vue`
    - `grep -q ":disabled=\"!fullProductForm.category" frontend/src/components/PurchaseItemsEditor.vue` (or equivalent — executor chooses)
    - `npm run build` completes without errors in frontend/
    - No new TypeScript errors (`npm run build` includes vue-tsc)
  </acceptance_criteria>
  <done>
    Category field in PurchaseItemsEditor full-product dialog shows required star, validates, and save is disabled without value. Build green.
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: Make category required in AdvancedProductSelector create-product dialog</name>
  <read_first>
    - frontend/src/components/AdvancedProductSelector.vue (full file — find the create-product dialog template; may be around line 50-300 based on 537 total lines)
    - frontend/src/components/AdvancedProductSelector.vue line 481-502 (onProductAdded handler — shows category in payload)
    - frontend/src/components/PurchaseItemsEditor.vue after Task 1 changes (use as reference for exact rule expression)
  </read_first>
  <action>
    Step 1: Locate the product-creation dialog/form inside AdvancedProductSelector.vue. The `newProduct` reactive object (referenced at line 487 `category: newProduct.category`) has a corresponding form. Find the `v-combobox` or `v-text-field` bound to `newProduct.category`.

    Step 2: Add the same required rule:
    ```vue
    <v-combobox v-model="newProduct.category"
      :items="<existing categories list>"
      label="Категория *"
      :rules="[v => (!!v && String(v).trim().length > 0) || 'Категория обязательна']"
      required
      variant="outlined" density="compact" />
    ```
    Preserve all existing props (items, hints, etc.).

    Step 3: Locate submit/save button for this dialog and add disabled check:
    ```vue
    :disabled="!newProduct.name || !newProduct.category || !String(newProduct.category).trim()"
    ```

    Step 4: If there is a `<v-form ref="productFormRef">` wrapper, ensure the save handler calls `await productFormRef.value?.validate()` and bails on `valid === false` — Vuetify pattern identical to `wishFormRef` in WishesView.vue line 792.
  </action>
  <verify>
    <automated>cd frontend && npm run build 2>&1 | tee /tmp/fe_build2.log | grep -iE "^error" | head -20; test ! -s <(grep -iE "^(error|build failed)" /tmp/fe_build2.log) && echo "BUILD OK"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "'Категория обязательна'" frontend/src/components/AdvancedProductSelector.vue`
    - `grep -q "label=\"Категория \\*\"" frontend/src/components/AdvancedProductSelector.vue`
    - `grep -qE ":disabled=.*newProduct.category" frontend/src/components/AdvancedProductSelector.vue`
    - `npm run build` (frontend) → exit 0
  </acceptance_criteria>
  <done>
    Category field required in both places; users cannot submit without it; build green.
  </done>
</task>

</tasks>

<verification>
- `npm run build` in frontend/ exits 0
- Manual smoke (developer verification, optional): open WishesView, click "+ Товар" inside PurchaseItemsEditor full dialog, try to save without category → button disabled
- No TypeScript errors
</verification>

<success_criteria>
1. Category is visibly marked required (star in label) in both dialogs
2. Save button disabled until category has value
3. Vuetify validation rule fires on form validate()
4. `npm run build` green (no TS errors)
5. No other behavior change in either component
</success_criteria>

<output>
After completion, create `.planning/phases/13-v3-drag-drop-n/13-04-SUMMARY.md`
</output>
