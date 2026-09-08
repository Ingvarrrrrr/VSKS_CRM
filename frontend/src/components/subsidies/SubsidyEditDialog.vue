<template>
  <!-- ── Add Subsidy Dialog ── -->
  <v-dialog v-model="addOpen" max-width="520" :fullscreen="mobile">
    <v-card class="dialog-card">
      <v-card-title class="dialog-title">
        <v-icon icon="mdi-plus-circle-outline" color="primary" class="mr-2" />
        Добавить субсидию
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="addOpen = false" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4">
        <v-text-field v-model="form.name" label="Название *" variant="outlined" density="compact" class="mb-3" hide-details />
        <v-row>
          <v-col cols="6">
            <v-text-field v-model.number="form.year" label="Год *" variant="outlined" density="compact" type="number" hide-details />
          </v-col>
          <v-col cols="6">
            <v-text-field v-model.number="form.budget" label="Бюджет, ₽ *" variant="outlined" density="compact" type="number" hide-details />
          </v-col>
        </v-row>
        <ContractorPicker v-model="form.contractor_id" class="mt-3" />
        <v-textarea v-model="form.description" label="Описание" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />
        <v-row dense class="mt-3">
          <v-col cols="12" md="6">
            <v-text-field
              v-model="form.basis_doc_number"
              label="Номер документа-основания"
              hint="№ соглашения о субсидии (например, 831-2025-ВСКС). Используется для авто-связки банковских платежей."
              persistent-hint
              variant="outlined" density="compact"
            />
          </v-col>
          <v-col cols="12" md="6">
            <v-text-field
              v-model="form.basis_doc_date"
              label="Дата документа-основания"
              type="date"
              variant="outlined" density="compact"
            />
          </v-col>
        </v-row>
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="addOpen = false">Отмена</v-btn>
        <v-btn color="primary" :loading="saving" :disabled="!form.name || !form.budget || !form.year" @click="addSubsidy">
          Добавить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- ── Edit Subsidy Dialog ── -->
  <v-dialog v-model="editOpen" max-width="520" :fullscreen="mobile">
    <v-card class="dialog-card">
      <v-card-title class="dialog-title">
        <v-icon icon="mdi-pencil-outline" color="primary" class="mr-2" />
        Редактировать субсидию
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="editOpen = false" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4">
        <v-text-field v-model="editForm.name" label="Название *" variant="outlined" density="compact" class="mb-3" hide-details />
        <v-row>
          <v-col cols="6">
            <v-text-field v-model.number="editForm.year" label="Год *" variant="outlined" density="compact" type="number" hide-details />
          </v-col>
          <v-col cols="6">
            <v-text-field v-model.number="editForm.budget" label="Бюджет, ₽ *" variant="outlined" density="compact" type="number" hide-details />
          </v-col>
        </v-row>
        <ContractorPicker v-model="editForm.contractor_id" :initial-contractor="editInitialContractor" class="mt-3" />
        <v-textarea v-model="editForm.description" label="Описание" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />
        <v-textarea
          v-model="editForm.agreement_text"
          label="Текст соглашения о субсидии (для шаблонов)"
          variant="outlined" density="compact"
          rows="4" auto-grow
          class="mt-3"
          placeholder="Например: Финансирование договора осуществляется в рамках соглашения…"
          hint="Переменная шаблона {{subsidy_agreement_text}}"
          persistent-hint
        />
        <v-row dense class="mt-3">
          <v-col cols="12" md="6">
            <v-text-field
              v-model="editForm.basis_doc_number"
              label="Номер документа-основания"
              hint="№ соглашения о субсидии (например, 831-2025-ВСКС). Используется для авто-связки банковских платежей."
              persistent-hint
              variant="outlined" density="compact"
            />
          </v-col>
          <v-col cols="12" md="6">
            <v-text-field
              v-model="editForm.basis_doc_date"
              label="Дата документа-основания"
              type="date"
              variant="outlined" density="compact"
            />
          </v-col>
        </v-row>
        <v-divider class="mt-4 mb-3" />
        <div class="text-caption text-medium-emphasis mb-2">Реквизиты для шаблонов договоров</div>
        <v-text-field
          v-model="editForm.grantor_name"
          label="Грантодатель (для договоров)"
          hint="Напр. «Российская Федерация» или «Тверская область». Переменная {{subsidy_grantor_name}}"
          persistent-hint
          variant="outlined" density="compact"
          class="mb-3"
        />
        <v-text-field
          v-model="editForm.ministry_name"
          label="Министерство-грантодатель (для договоров)"
          hint="Напр. «МИНИСТЕРСТВОМ МОЛОДЕЖНОЙ ПОЛИТИКИ РФ» (как пишется в тексте договора). Переменная {{subsidy_ministry_name}}"
          persistent-hint
          variant="outlined" density="compact"
          class="mb-3"
        />
        <v-textarea
          v-model="editForm.extra_contract_clause_1"
          label="Доп. пункт договора 1 (зависит от субсидии)"
          hint="Например пункт о раздельном учёте расходов. Вставляется в шаблон как {{subsidy_extra_clause_1}}. Если пусто — пункт пропускается."
          persistent-hint
          rows="3"
          auto-grow
          variant="outlined"
          density="compact"
          class="mb-3"
        />
        <v-textarea
          v-model="editForm.extra_contract_clause_2"
          label="Доп. пункт договора 2 (зависит от субсидии)"
          hint="{{subsidy_extra_clause_2}}. Если пусто — пункт пропускается."
          persistent-hint
          rows="3"
          auto-grow
          variant="outlined"
          density="compact"
        />
        <!-- Настройки плана закупок (только для admin+) -->
        <template v-if="canSaveVersion">
          <v-divider class="mt-4 mb-3" />
          <div class="text-caption text-medium-emphasis mb-2">Настройки плана закупок</div>
          <v-switch
            v-model="editForm.require_planned_dates"
            label="Требовать дату потребности у позиций (для помесячного плана)"
            density="compact"
            color="primary"
            hide-details
            class="mb-2"
          />
          <v-alert
            v-if="!editForm.require_planned_dates"
            type="warning"
            density="compact"
            variant="tonal"
            class="mt-2"
          >
            Без дат плановые траты по месяцам считаться не будут
          </v-alert>
        </template>
        <v-divider class="mt-4 mb-3" />
        <v-text-field
          v-model.number="editForm.ceiling_warn_percent"
          label="Порог предупреждения о подходе к потолку субсидии, %"
          hint="Когда сумма заказанного (включая ежемесячные платежи — весь график) достигнет этого процента от потолка ФЭО, появится предупреждение в карточке субсидии, списке и на дашборде. По умолчанию 90%."
          persistent-hint
          type="number"
          min="1" max="100"
          variant="outlined" density="compact"
          class="mt-1"
        />
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="editOpen = false">Отмена</v-btn>
        <v-btn color="primary" :loading="saving" :disabled="!editForm.name || !editForm.budget || !editForm.year" @click="updateSubsidy">
          Сохранить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import { numOrNull } from '@/utils/numberFormat'
import ContractorPicker from '@/components/ContractorPicker.vue'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import type { SubsidyRow } from '@/composables/subsidies/types'

const addOpen = defineModel<boolean>('addOpen', { default: false })
const editOpen = defineModel<boolean>('editOpen', { default: false })

const emit = defineEmits<{ (e: 'saved'): void }>()

const { mobile } = useDisplay()
const toast = useToast()
function showSnack(text: string, color: ToastType = 'success', opts?: { actionText?: string; onAction?: () => void; duration?: number }) {
  toast.addToast(text, color, opts)
}

const ctx = useSubsidyDetailCtx()

// Тот же гейт, что и в остальных местах SubsidiesView.vue (canSaveVersion) —
// вычисляется независимо здесь же, т.к. используется ещё в двух местах вне
// этого диалога (панель версий плана-графика), которые остаются в родителе.
const userRoleRaw = localStorage.getItem('user_role') || ''
const canSaveVersion = computed(() => ['superadmin', 'org_admin', 'admin', 'account_owner'].includes(userRoleRaw))

const saving = ref(false)

const form = ref({ name: '', year: new Date().getFullYear(), budget: 0, description: '', contractor_id: null as number | null, agreement_text: '' as string, basis_doc_number: '' as string, basis_doc_date: '' as string })
const editForm = ref({ id: 0, name: '', year: new Date().getFullYear(), budget: 0, description: '', contractor_id: null as number | null, agreement_text: '' as string, basis_doc_number: '' as string, basis_doc_date: '' as string, grantor_name: '' as string, ministry_name: '' as string, extra_contract_clause_1: null as string | null, extra_contract_clause_2: null as string | null, require_planned_dates: true as boolean, ceiling_warn_percent: 90 as number | null })

const contractors = ref<{ id: number; name: string; inn?: string }[]>([])
const editInitialContractor = computed(() => {
  if (!editForm.value.contractor_id) return null
  const c = contractors.value.find((x: any) => x.id === editForm.value.contractor_id)
  return c ? { id: c.id, name: c.name, inn: c.inn } : { id: editForm.value.contractor_id, name: `Контрагент #${editForm.value.contractor_id}`, inn: undefined }
})

async function startEdit(s: SubsidyRow) {
  if (s.contractor_id && !contractors.value.find(c => c.id === s.contractor_id)) {
    try { const f = await apiFetch<any>(`/contractors/${s.contractor_id}`); contractors.value.push(f) } catch {}
  }
  // /dashboard/charts не отдаёт agreement_text / basis_doc_*, тянем полную карточку
  // через /api/subsidies/{id} — иначе при save поля перезатрутся в NULL.
  let full: any = s
  try { full = await apiFetch<any>(`/subsidies/${s.id}`) } catch { full = s }
  editForm.value = {
    id: full.id,
    name: full.name,
    year: full.year,
    budget: full.budget,
    description: full.description || '',
    contractor_id: full.contractor_id ?? null,
    agreement_text: full.agreement_text || '',
    basis_doc_number: full.basis_doc_number || '',
    basis_doc_date: full.basis_doc_date || '',
    grantor_name: full.grantor_name || '',
    ministry_name: full.ministry_name || '',
    extra_contract_clause_1: full.extra_contract_clause_1 ?? null,
    extra_contract_clause_2: full.extra_contract_clause_2 ?? null,
    require_planned_dates: full.require_planned_dates ?? true,
    ceiling_warn_percent: full.ceiling_warn_percent ?? 90,
  }
  editOpen.value = true
}

async function addSubsidy() {
  saving.value = true
  try {
    const res = await apiFetch<any>('/subsidies/', {
      method: 'POST',
      body: JSON.stringify({ name: form.value.name, year: form.value.year, budget: form.value.budget, description: form.value.description || null, contractor_id: form.value.contractor_id, agreement_text: form.value.agreement_text || null, basis_doc_number: form.value.basis_doc_number || null, basis_doc_date: form.value.basis_doc_date || null })
    })
    ctx.allSubsidies.value.push({ ...res, planned: 0, paid: 0, contracted: 0, plan_schedule: 0, ordered: 0, work: 0, contracts: 0, delivered: 0, delivered_unpaid: 0 })
    addOpen.value = false
    form.value = { name: '', year: new Date().getFullYear(), budget: 0, description: '', contractor_id: null, agreement_text: '', basis_doc_number: '', basis_doc_date: '' }
    showSnack('Субсидия добавлена')
    emit('saved')
  } catch (e: any) {
    showSnack(e?.detail || e?.payload?.message || 'Ошибка добавления', 'error')
  } finally {
    saving.value = false
  }
}

async function updateSubsidy() {
  saving.value = true
  try {
    await apiFetch<any>(`/subsidies/${editForm.value.id}`, {
      method: 'PUT',
      body: JSON.stringify({ name: editForm.value.name, year: editForm.value.year, budget: editForm.value.budget, description: editForm.value.description || null, contractor_id: editForm.value.contractor_id, agreement_text: editForm.value.agreement_text || null, basis_doc_number: editForm.value.basis_doc_number || null, basis_doc_date: editForm.value.basis_doc_date || null, grantor_name: editForm.value.grantor_name || null, ministry_name: editForm.value.ministry_name || null, extra_contract_clause_1: editForm.value.extra_contract_clause_1 || null, extra_contract_clause_2: editForm.value.extra_contract_clause_2 || null, require_planned_dates: editForm.value.require_planned_dates, ceiling_warn_percent: numOrNull(editForm.value.ceiling_warn_percent) })
    })
    // После save перезагружаем весь список с backend — гарантированно свежие
    // данные (включая поля которые backend мог трансформировать). Spread-merge
    // ответа PUT мог давать stale поля если SW кэшировал предыдущий GET.
    await ctx.loadAll()
    editOpen.value = false
    showSnack('Субсидия обновлена')
    emit('saved')
  } catch (e: any) {
    console.error('updateSubsidy failed:', e)
    showSnack(e?.detail || e?.payload?.message || 'Ошибка сохранения', 'error')
  } finally {
    saving.value = false
  }
}

defineExpose({ startEdit })
</script>

<style scoped>
/* .dialog-card/.dialog-title — было в <style scoped> SubsidiesView.vue, пока
   диалог был её частью; вынесено вместе с диалогом (волна 5c) — иначе scoped CSS
   другого файла эти классы не достаёт (проверено на ContractorEditDialog.vue —
   тот же паттерн: каждый диалог держит эти два правила у себя). */
.dialog-card {}
.dialog-title {
  display: flex; align-items: center;
  font-size: 16px !important; font-weight: 600 !important;
  padding: 16px 20px !important;
}
</style>
