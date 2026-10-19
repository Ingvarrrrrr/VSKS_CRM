<template>
  <!-- Одна тонкая строка «Мероприятия · Журнал загрузок ФЭО» (владелец,
       19.10.2026): «Мероприятия» (большой блок с пустой иконкой-заглушкой) и
       «Журнал загрузок ФЭО» раньше занимали много места и были видны всегда
       под деревом ФЭО — владелец попросил свернуть их в одну строку,
       раскрывающуюся по клику на каждую половину отдельно. Оба свёрнуты по
       умолчанию, открытость каждого — в localStorage (per-браузер, тот же
       try/catch-паттерн, что уже был в FeoImportRunsPanel.vue).

       SubsidyEventsPanel.vue смонтирован ВСЕГДА (не только когда раскрыт) —
       его собственный `expanded` проп прячет только содержимое, а
       загрузка/счётчик (reload/count) работают в фоне, чтобы N в кнопке было
       видно и при свёрнутом разделе. FeoImportRunsPanel.vue, наоборот, грузит
       журнал только при раскрытии — как и раньше. -->
  <div class="subsidy-bottom-sections mt-3">
    <div class="subsidy-bottom-row">
      <button type="button" class="subsidy-bottom-toggle" @click="toggleEvents">
        <v-icon :icon="eventsOpen ? 'mdi-chevron-down' : 'mdi-chevron-right'" size="16" class="mr-1" />
        <v-icon icon="mdi-calendar-outline" size="16" class="mr-1" />
        Мероприятия
        <span class="subsidy-bottom-count">({{ eventsCount }})</span>
      </button>
      <span v-if="isAdminLevel" class="subsidy-bottom-sep">·</span>
      <button v-if="isAdminLevel" type="button" class="subsidy-bottom-toggle" @click="toggleJournal">
        <v-icon :icon="journalOpen ? 'mdi-chevron-down' : 'mdi-chevron-right'" size="16" class="mr-1" />
        <v-icon icon="mdi-file-upload-outline" size="16" class="mr-1" />
        Журнал загрузок ФЭО
      </button>
    </div>

    <div v-if="eventsOpen" class="subsidy-bottom-content">
      <SubsidyEventsPanel ref="eventsPanelRefLocal" :subsidy-id="subsidyId" :expanded="true" />
    </div>
    <!-- SubsidyEventsPanel смонтирован и когда свёрнут — не оборачиваем v-if
         снаружи, иначе count/reload в фоне не работали бы (см. докстринг выше). -->
    <SubsidyEventsPanel v-else ref="eventsPanelRefLocal" :subsidy-id="subsidyId" :expanded="false" />

    <div v-if="journalOpen && isAdminLevel" class="subsidy-bottom-content">
      <FeoImportRunsPanel :subsidy-id="subsidyId" :panel-open="true" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ADMIN_ROLES } from '@/constants/roles'
import SubsidyEventsPanel from '@/components/subsidies/SubsidyEventsPanel.vue'
import FeoImportRunsPanel from '@/components/subsidies/FeoImportRunsPanel.vue'

const props = defineProps<{ subsidyId: number | null }>()

const userRoleRaw = localStorage.getItem('user_role') || ''
const isAdminLevel = ADMIN_ROLES.includes(userRoleRaw as typeof ADMIN_ROLES[number])

const EVENTS_OPEN_KEY = 'subsidy_bottom_sections_events_open'
const JOURNAL_OPEN_KEY = 'subsidy_bottom_sections_journal_open'

function readOpen(key: string): boolean {
  try {
    return localStorage.getItem(key) === '1'
  } catch {
    return false
  }
}
function writeOpen(key: string, v: boolean) {
  try {
    localStorage.setItem(key, v ? '1' : '0')
  } catch { /* приватный режим/квота — не критично, открытость просто не запомнится */ }
}

const eventsOpen = ref(readOpen(EVENTS_OPEN_KEY))
const journalOpen = ref(readOpen(JOURNAL_OPEN_KEY))

function toggleEvents() {
  eventsOpen.value = !eventsOpen.value
  writeOpen(EVENTS_OPEN_KEY, eventsOpen.value)
}
function toggleJournal() {
  journalOpen.value = !journalOpen.value
  writeOpen(JOURNAL_OPEN_KEY, journalOpen.value)
}

// Template ref на SubsidyEventsPanel — доступен в обеих ветках v-if/v-else
// (один и тот же имя ref'а на обоих тегах), родитель (SubsidiesView.vue)
// зовёт eventsPanelRef.value?.reload(subsidyId) — пробрасываем reload через
// defineExpose, чтобы вызов доходил независимо от того, раскрыт раздел или
// нет (Правило №6 — второй способ перезагрузки не заводим).
const eventsPanelRefLocal = ref<InstanceType<typeof SubsidyEventsPanel> | null>(null)
const eventsCount = computed(() => eventsPanelRefLocal.value?.count ?? 0)

function reload(subsidyId: number) {
  return eventsPanelRefLocal.value?.reload(subsidyId)
}

defineExpose({ reload })

// При смене субсидии состояние разделов (открыт/свёрнут) НЕ сбрасываем —
// это предпочтение пользователя per-браузер, не per-субсидия.
watch(() => props.subsidyId, () => { /* намеренно пусто */ })
</script>

<style scoped>
.subsidy-bottom-row {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 34px;
  padding: 0 4px;
  border-top: 1px solid var(--crm-border);
}
.subsidy-bottom-toggle {
  display: inline-flex;
  align-items: center;
  background: none;
  border: none;
  padding: 4px 6px;
  font-size: 12px;
  font-weight: 500;
  color: var(--crm-text-muted);
  cursor: pointer;
  border-radius: 6px;
}
.subsidy-bottom-toggle:hover {
  background: var(--crm-table-header);
  color: var(--crm-text);
}
.subsidy-bottom-count {
  margin-left: 4px;
  color: var(--crm-text-faint);
}
.subsidy-bottom-sep {
  color: var(--crm-border-strong);
}
.subsidy-bottom-content {
  padding: 8px 4px 4px;
}
</style>
