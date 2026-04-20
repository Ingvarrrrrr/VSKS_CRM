---
phase: 13-v3-drag-drop-n
plan: 06
type: execute
wave: 4
depends_on:
  - 03
files_modified:
  - frontend/src/views/WishesView.vue
autonomous: true
requirements:
  - D-07
must_haves:
  truths:
    - "A 'Скачать служебную записку' button is visible in the wish edit dialog header/toolbar"
    - "Clicking the button opens a dialog with an initiator autocomplete (org users list)"
    - "Confirming the dialog calls GET /api/wishes/{id}/documents/service_note?initiator_id=X and downloads the .docx"
    - "Button is visible regardless of wish status (even approved — historical record)"
  artifacts:
    - path: "frontend/src/views/WishesView.vue"
      provides: "Button + picker dialog + download handler, ported from CreateOrderView's openDocPicker pattern"
      contains: "openWishDocPicker"
  key_links:
    - from: "Скачать служебную записку button"
      to: "GET /api/wishes/{id}/documents/service_note?initiator_id=X"
      via: "apiFetch blob download + browser a[download] trigger"
      pattern: "/wishes/.*documents/service_note"
    - from: "Initiator picker"
      to: "GET /api/users/ (org users list)"
      via: "existing loadOrgUsers-equivalent — or reuse pickerInitiatorId pattern from CreateOrderView"
      pattern: "orgUsers\\|loadOrgUsers\\|users"
---

<objective>
Add "Скачать служебную записку" UI to WishesView. Implements CONTEXT D-07 (UI half; backend endpoint landed in Plan 13-03).

Purpose: Users need to print a служебка from a wish without first having to convert/approve it. The backend endpoint already accepts `initiator_id` — this plan delivers the picker UI that feeds the param.

Output: Single-file change in WishesView.vue. New button + new dialog + new download handler. No new components.
</objective>

<execution_context>
@C:/Users/1/Desktop/Cursor/VSKS_CRM/.claude/get-shit-done/workflows/execute-plan.md
@C:/Users/1/Desktop/Cursor/VSKS_CRM/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/13-v3-drag-drop-n/CONTEXT.md
@.planning/phases/13-v3-drag-drop-n/13-03-wish-service-note-endpoint-PLAN.md

<interfaces>
From backend (Plan 13-03):
```
GET /api/wishes/{wid}/documents/service_note?initiator_id=X&responsible_name=Y
→ 200 application/vnd.openxmlformats-officedocument.wordprocessingml.document
Content-Disposition: attachment; filename*=UTF-8''SZ_Wish_{wid}.docx
```

Ported from frontend/src/views/CreateOrderView.vue lines 2600-2654:
```typescript
async function openDocPicker(type: 'service_note' | ...) {
  docPickerType.value = type
  docPickerDialog.value = true
  loadingDocApprovers.value = true
  pickerResponsibleName.value = form.responsible_person || ''
  try {
    const [list] = await Promise.all([
      apiFetch<DocApprover[]>(`/subsidies/${form.subsidy_id}/approvers`),
      loadResponsiblePersonsList(),
    ])
    docApprovers.value = list
    // ... defaults ...
  } ...
}
async function confirmDocDownload() {
  ...
  if (type.startsWith('service_note')) {
    const params = initiatorId ? `?initiator_id=${initiatorId}` : ''
    await downloadDoc(type, params)
  }
}
```

And lines 2125-2212 in CreateOrderView have the docPickerDialog template — autocomplete of orgUsers for initiator, confirm button, etc. Port the minimal subset.

From frontend/src/views/WishesView.vue (line 496):
```typescript
import PurchaseItemsEditor from '@/components/PurchaseItemsEditor.vue'
// apiFetch already imported somewhere — grep to find
```

Wish dialog structure: `<v-dialog v-model="wishDialog">` wraps `<v-card>` with toolbar at top and `<v-form>` content. Button goes in `<v-card-actions>` or toolbar.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Add service-note button + picker dialog + download handler to WishesView</name>
  <read_first>
    - frontend/src/views/WishesView.vue (full — 935 lines; identify dialog toolbar, actions slot, existing `showSnack`, `apiFetch` usage, import style)
    - frontend/src/views/CreateOrderView.vue lines 2125-2212 (docPickerDialog template — port minimal subset)
    - frontend/src/views/CreateOrderView.vue lines 2487-2600 (loadOrgUsers, openDocPicker, confirmDocDownload, downloadDoc helper)
    - .planning/phases/13-v3-drag-drop-n/CONTEXT.md (D-07)
  </read_first>
  <action>
    === Step 1: Add state + loader functions to WishesView <script setup> ===

    ```typescript
    // Service-note download (Phase 13 D-07)
    const wishDocDialog = ref(false)
    const wishDocInitiatorId = ref<number | null>(null)
    const wishDocResponsibleName = ref('')
    const wishDocLoading = ref(false)
    const orgUsersForDoc = ref<Array<{ id: number; full_name: string; username: string; role_name?: string }>>([])

    async function loadOrgUsersForDoc() {
      if (orgUsersForDoc.value.length) return
      try {
        const users = await apiFetch<any[]>('/users/')
        orgUsersForDoc.value = users.map(u => ({
          id: u.id,
          full_name: u.full_name || u.username,
          username: u.username,
          role_name: u.role,
        }))
      } catch (e) {
        orgUsersForDoc.value = []
      }
    }

    async function openWishDocPicker() {
      if (!editingWishId.value) { showSnack('Сначала сохраните заявку', 'error'); return }
      wishDocDialog.value = true
      wishDocInitiatorId.value = null
      wishDocResponsibleName.value = ''
      wishDocLoading.value = true
      try {
        await loadOrgUsersForDoc()
        // Default initiator = current user if present
        const currentUserId = (globalThis as any).__currentUserId ?? null  // or read from a store
        if (currentUserId && orgUsersForDoc.value.find(u => u.id === currentUserId)) {
          wishDocInitiatorId.value = currentUserId
        }
      } finally {
        wishDocLoading.value = false
      }
    }

    async function confirmWishDocDownload() {
      const wid = editingWishId.value
      const iid = wishDocInitiatorId.value
      const respName = wishDocResponsibleName.value
      wishDocDialog.value = false
      if (!wid) return

      const parts: string[] = []
      if (iid) parts.push(`initiator_id=${iid}`)
      if (respName) parts.push(`responsible_name=${encodeURIComponent(respName)}`)
      const qs = parts.length ? `?${parts.join('&')}` : ''

      try {
        // REVISION-1 blocker 4: use the project's canonical token key `auth_token`.
        // Confirmed via grep 2026-04-20: `frontend/src/api.ts:4` uses `localStorage.getItem('auth_token')`.
        // All other download flows (CreateOrderView downloadDoc/uploadFile, ChatView, App.vue, etc.)
        // use the same key. The old key `'token'` is NOT used anywhere in the project.
        // Prefer delegating to apiFetch if it supports blob; otherwise raw fetch with auth_token header.
        const token = localStorage.getItem('auth_token') || ''
        const resp = await fetch(`/api/wishes/${wid}/documents/service_note${qs}`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (!resp.ok) {
          const err = await resp.text()
          throw new Error(err || `HTTP ${resp.status}`)
        }
        const blob = await resp.blob()
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `SZ_Wish_${wid}.docx`
        document.body.appendChild(a)
        a.click()
        a.remove()
        URL.revokeObjectURL(url)
        showSnack('Служебная записка скачана', 'success')
      } catch (e: any) {
        showSnack(`Ошибка: ${e?.message || e}`, 'error')
      }
    }
    ```
    NOTE executor: token source is FIXED to `auth_token` (project-canonical key per `frontend/src/api.ts`). For `apiFetch` blob handling: grep the `apiFetch` definition — if it supports `responseType: 'blob'` or returns Response, prefer it over raw fetch. The Authorization header MUST use the `auth_token` localStorage key, NEVER `'token'`.

    === Step 2: Add button in wish dialog toolbar/actions ===

    Locate the wish edit `<v-dialog v-model="wishDialog">` block (around line 243 where `<v-form ref="wishFormRef">` is) — find its `<v-card>` wrapper. Add button to toolbar or actions:

    ```vue
    <v-btn v-if="editingWishId"
      color="blue" variant="tonal" prepend-icon="mdi-file-document-edit"
      @click="openWishDocPicker">
      Скачать служебную записку
    </v-btn>
    ```

    Place in the card toolbar (next to close button) OR in `<v-card-actions>` bar at the bottom next to Save. Executor chooses based on where other action buttons live in this file.

    === Step 3: Add picker dialog template (after the wishDialog block, before `</template>`) ===

    ```vue
    <v-dialog v-model="wishDocDialog" max-width="560" scrollable>
      <v-card>
        <v-card-title class="d-flex align-center">
          <v-icon class="mr-2">mdi-file-document-edit</v-icon>
          Служебная записка — выбор инициатора
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="wishDocDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text>
          <v-progress-linear v-if="wishDocLoading" indeterminate />
          <v-autocomplete v-else
            v-model="wishDocInitiatorId"
            :items="orgUsersForDoc"
            item-value="id"
            item-title="full_name"
            label="Инициатор"
            variant="outlined" density="compact" clearable
            hint="Кто подписывает служебную записку" persistent-hint />
          <v-text-field v-model="wishDocResponsibleName"
            label="Ответственный исполнитель (опционально)"
            variant="outlined" density="compact" class="mt-3"
            hint="Если отличается от инициатора" persistent-hint />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="wishDocDialog = false">Отмена</v-btn>
          <v-btn color="primary" :disabled="wishDocLoading" @click="confirmWishDocDownload">
            <v-icon start>mdi-download</v-icon>
            Скачать
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
    ```

    === Step 4: Ensure the button is ALWAYS shown for saved wishes (draft + submitted + approved) ===
    The `v-if="editingWishId"` gate ensures it only shows after first save — exactly what we want (there is no wish_id before first save, so the endpoint has no target).
  </action>
  <verify>
    <automated>cd frontend && npm run build 2>&1 | grep -iE "^error|build failed" | head -20; grep -q "openWishDocPicker" src/views/WishesView.vue && grep -q "wishDocDialog" src/views/WishesView.vue && echo "OK"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "openWishDocPicker" frontend/src/views/WishesView.vue`
    - `grep -q "confirmWishDocDownload" frontend/src/views/WishesView.vue`
    - `grep -q "Скачать служебную записку" frontend/src/views/WishesView.vue`
    - `grep -q "wishDocDialog" frontend/src/views/WishesView.vue`
    - `grep -q "/wishes/.*/documents/service_note" frontend/src/views/WishesView.vue`
    - **Blocker 4 (revision 1):** New code in WishesView.vue uses `auth_token`, not `token`:
      - `grep -n "localStorage.getItem('auth_token')" frontend/src/views/WishesView.vue` MUST match (at least in the new download handler)
      - `grep -c "localStorage.getItem('token')" frontend/src/views/WishesView.vue` MUST return 0 (no new code uses the wrong key)
    - `npm run build` green
  </acceptance_criteria>
  <done>
    Button appears in wish dialog for saved wishes, clicking opens picker, confirming downloads the .docx file with the chosen initiator.
  </done>
</task>

</tasks>

<verification>
- `npm run build` green
- Manual (dev check, optional): open a saved wish → click "Скачать служебную записку" → dialog opens with user autocomplete → select inititator → click Скачать → .docx downloads
</verification>

<success_criteria>
1. Button visible in wish edit dialog for saved (editingWishId) wishes
2. Picker dialog has initiator autocomplete and optional responsible name field
3. Confirm triggers blob download with correct filename
4. No regression to existing wish form save/submit flow
5. Build green
</success_criteria>

<output>
After completion, create `.planning/phases/13-v3-drag-drop-n/13-06-SUMMARY.md`
</output>
