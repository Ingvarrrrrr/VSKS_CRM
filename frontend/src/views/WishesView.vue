<template>
  <v-container fluid class="pa-4">
    <!-- Consent banner: pending wish participations -->
    <v-expand-transition>
      <div v-if="pendingWishConsents.length" class="mb-4">
        <div class="d-flex align-center mb-2" style="gap:8px">
          <v-icon color="orange" size="20">mdi-bell-ring</v-icon>
          <span class="font-weight-bold">Требуется ваше согласие на заявки</span>
          <v-chip color="orange" size="x-small" variant="tonal">{{ pendingWishConsents.length }}</v-chip>
        </div>
        <v-row dense>
          <v-col
            v-for="pc in pendingWishConsents"
            :key="pc.wish_id"
            cols="12"
            sm="6"
            md="4"
          >
            <v-card variant="outlined" style="border-color: rgb(251,146,60)" class="pa-3">
              <div class="font-weight-medium mb-1">{{ pc.title }}</div>
              <div class="text-caption text-medium-emphasis mb-2">
                Добавил: <b>{{ pc.added_by_name || '—' }}</b>
                <span v-if="pc.created_at"> · {{ pc.created_at.split('T')[0] }}</span>
              </div>
              <div class="d-flex" style="gap:8px">
                <v-btn
                  color="success"
                  size="small"
                  variant="tonal"
                  :loading="consentLoading === pc.wish_id + '_a'"
                  @click="respondWishConsent(pc.wish_id, true)"
                >Принять</v-btn>
                <v-btn
                  color="error"
                  size="small"
                  variant="tonal"
                  :loading="consentLoading === pc.wish_id + '_d'"
                  @click="respondWishConsent(pc.wish_id, false)"
                >Отклонить</v-btn>
              </div>
            </v-card>
          </v-col>
        </v-row>
      </div>
    </v-expand-transition>

    <!-- Header -->
    <div class="d-flex align-center mb-4 flex-wrap" style="gap:12px">
      <div>
        <h1 class="text-h5 font-weight-bold">Заявки на закупку</h1>
        <span class="text-body-2 text-medium-emphasis">
          {{ activeTab === 'my' ? 'Мои заявки' : activeTab === 'incoming' ? 'На согласование мне' : 'Заявки сотрудников' }}
        </span>
      </div>
      <v-spacer />
      <v-btn-toggle
        v-if="!mobile && activeTab === 'my'"
        v-model="viewMode"
        mandatory
        density="compact"
        variant="outlined"
        divided
        class="ml-1"
      >
        <v-btn value="table" size="small" icon="mdi-table" />
        <v-btn value="cards" size="small" icon="mdi-view-grid" />
      </v-btn-toggle>
      <RegistryExportButton
        title="Заявки на закупку"
        :get-columns="getWishExportColumns"
        :get-rows="getWishExportRows"
        :get-capture-el="() => registryArea"
        @error="(m) => ctx.showSnack(m, 'error')"
      />
      <v-btn variant="tonal" color="primary" size="small" prepend-icon="mdi-refresh" :loading="loading" @click="reloadActiveTab">
        Обновить
      </v-btn>
      <v-btn variant="tonal" size="small" prepend-icon="mdi-view-column" @click="showWishColumnPicker = true">
        Колонки
      </v-btn>
    </div>

    <!-- Tabs (visible to all authenticated users) -->
    <v-tabs v-model="activeTab" class="mb-4">
      <v-tab value="my">Мои заявки</v-tab>
      <v-tab value="incoming">На согласование мне</v-tab>
      <v-tab v-if="ctx.isManagerOrAdmin.value" value="all">Заявки сотрудников</v-tab>
    </v-tabs>

    <WishFilterPanel
      :filters="filters"
      :account-options="accountOptions"
      :org-options-filtered="orgOptionsFiltered"
      :reset-filters="resetFilters"
    />

    <!-- ── MY WISHES TAB ── -->
    <div v-if="activeTab === 'my'">
      <WishMyTab
        ref="wishMyTabRef"
        :items="myWishesFiltered"
        :headers="wishHeaders"
        :loading="loading"
        :col-filters="colFilters"
        :col-sort="colSort"
        :subsidy-name-options="wishSubsidyNameOptions"
        :effective-view="effectiveView"
        :paged-wishes="pagedWishes"
        :cards-page="cardsPage"
        :cards-total-pages="cardsTotalPages"
        :downloading-excel-id="downloadingExcelId"
        :submitting-id="submittingId"
        :deleting-id="deletingId"
        @open-edit="onOpenEdit"
        @submit="onSubmitWish"
        @delete="onDeleteWish"
        @force-status="onForceStatus"
        @convert="onConvert"
        @download-excel="onDownloadExcel"
        @update:cards-page="v => cardsPage = v"
      />
      <!-- FAB to create new wish -->
      <v-btn
        icon="mdi-plus"
        color="primary"
        size="large"
        style="position:fixed;bottom:32px;right:32px;z-index:100"
        elevation="4"
        @click="onCreate"
      />
    </div>

    <!-- ── INCOMING FOR APPROVAL TAB ── -->
    <div v-if="activeTab === 'incoming'">
      <WishIncomingTab
        :items="incomingWishesFiltered"
        :headers="wishHeaders"
        :loading="loadingIncoming"
        :col-filters="colFilters"
        :col-sort="colSort"
        :subsidy-name-options="wishSubsidyNameOptions"
        :downloading-excel-id="downloadingExcelId"
        :approving-id="approvingId"
        @open-edit="onOpenEdit"
        @kanban="onKanban"
        @approve="onApprove"
        @reject="onReject"
        @download-excel="onDownloadExcel"
      />
    </div>

    <!-- ── ALL WISHES TAB (manager/admin) ── -->
    <div v-if="ctx.isManagerOrAdmin.value && activeTab === 'all'">
      <WishAllTab
        :items="allWishesFiltered"
        :headers="wishHeadersAll"
        :loading="loadingAll"
        :col-filters="colFilters"
        :col-sort="colSort"
        :subsidy-name-options="wishSubsidyNameOptions"
        :downloading-excel-id="downloadingExcelId"
        :approving-id="approvingId"
        :all-filter="allFilter"
        :all-filters="allFilters"
        :wish-counts="wishCounts"
        :all-wishes-truncated="allWishesTruncated"
        @filter-change="onAllFilterChange"
        @open-edit="onOpenEdit"
        @kanban="onKanban"
        @approve="onApprove"
        @reject="onReject"
        @convert="onConvert"
        @download-excel="onDownloadExcel"
      />
    </div>

    <WishFormDialog
      ref="formDialogRef"
      :mobile="mobile"
      :reload-active-tab="reloadActiveTab"
      :load-wishes="loadWishes"
      :load-all-wishes="loadAllWishes"
    />

    <!-- Владелец, 2026-09-02: редактор колонок ОДИН на все три вкладки заявок
         («Мои» / «На согласование мне» / «Заявки сотрудников») — набор колонок
         у них одинаковый, раздельная настройка заставила бы настраивать
         одно и то же трижды. -->
    <ColumnConfigDialog
      v-model="showWishColumnPicker"
      :all-columns="allWishColumns"
      :state="wishColState"
      :show-width="true"
      :toggle-visible="wishToggleVisible"
      :set-position="wishSetPosition"
      :set-width="wishSetWidth"
      :reset="wishResetColumns"
    />

  </v-container>
</template>

<script setup lang="ts">
// WishesView.vue — оркестратор модуля «Заявки». Разбит на компоненты/композаблы
// (см. components/wishes/*.vue, composables/wishes/*.ts) без изменения поведения —
// тот же набор apiFetch-путей, текстов, условий видимости, snackbar. Остаётся
// здесь: три load* + loadWishCounts, onMounted (порядок как раньше), watch(activeTab),
// баннер согласий, хедер, useCardView. Вся форма/действия над одной заявкой —
// WishFormDialog.vue (через ref + defineExpose, единственно возможный способ
// открыть карточку строкой из таблицы — см. комментарий в этом файле).
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { apiFetch } from '@/api'
import RegistryExportButton from '@/components/RegistryExportButton.vue'
import ColumnConfigDialog from '@/components/ColumnConfigDialog.vue'
import { useCardView } from '@/composables/useCardView'
import { provideWishesContext } from '@/composables/wishes/useWishesContext'
import { useWishFilters } from '@/composables/wishes/useWishFilters'
import { useWishColumnMenu } from '@/composables/wishes/useWishColumnMenu'
import WishFilterPanel from '@/components/wishes/WishFilterPanel.vue'
import WishMyTab from '@/components/wishes/WishMyTab.vue'
import WishIncomingTab from '@/components/wishes/WishIncomingTab.vue'
import WishAllTab from '@/components/wishes/WishAllTab.vue'
import WishFormDialog from '@/components/wishes/WishFormDialog.vue'
import type { Wish, Subsidy, FeoCategory, EventItem, User, PendingWishConsent } from '@/composables/wishes/wishTypes'

const route = useRoute()
const ctx = provideWishesContext()

// Tabs
const activeTab = ref('my')

// My wishes
const myWishes = ref<Wish[]>([])
const loading = ref(false)

// All wishes (manager/admin — subordinates)
const allWishes = ref<Wish[]>([])
const loadingAll = ref(false)
const allFilter = ref('submitted')

// Incoming for approval (assigned_to = me)
const incomingWishes = ref<Wish[]>([])
const loadingIncoming = ref(false)
const allFilters = [
  { value: 'all', label: 'Все' },
  { value: 'draft', label: 'Черновики' },
  { value: 'submitted', label: 'Отправленные' },
  { value: 'approved', label: 'Одобренные' },
  { value: 'rejected', label: 'Отклонённые' },
  { value: 'converted', label: 'Конвертированные' },
]

// Счётчики по вкладкам (GET /wishes/counts) — накопительные множества статусов.
const wishCounts = ref<Record<string, number>>({})

const {
  filters,
  accountOptions,
  orgOptionsFiltered,
  buildFilterParams,
  resetFilters,
} = useWishFilters({ allOrgs: ctx.allOrgs, onChange: () => reloadActiveTab() })

const {
  allWishColumns,
  wishColState,
  wishToggleVisible,
  wishSetPosition,
  wishSetWidth,
  wishResetColumns,
  wishHeaders,
  wishHeadersAll,
  getWishExportColumns,
  getWishExportRows,
  colFilters,
  colSort,
  myWishesFiltered,
  incomingWishesFiltered,
  allWishesFiltered,
  wishSubsidyNameOptions,
  showWishColumnPicker,
} = useWishColumnMenu({ myWishes, incomingWishes, allWishes, activeTab })

async function loadWishes() {
  loading.value = true
  try {
    myWishes.value = await apiFetch<Wish[]>('/wishes/' + buildFilterParams({ mine_only: true }))
  } catch (e: any) {
    ctx.showSnack(`Ошибка загрузки заявок: ${e?.message || e?.payload?.message || 'неизвестная ошибка'}`, 'error')
  } finally {
    loading.value = false
  }
}

async function loadAllWishes() {
  loadingAll.value = true
  try {
    // Владелец, 2026-09-01: «Все» больше не значит «без статуса» — передаём status
    // ЯВНО всегда, включая 'all', которое сервер трактует как «действительно всё».
    allWishes.value = await apiFetch<Wish[]>('/wishes/' + buildFilterParams({ subordinates_only: true, status: allFilter.value }))
    loadWishCounts()
  } catch (e: any) {
    ctx.showSnack(`Ошибка загрузки заявок: ${e?.message || e?.payload?.message || 'неизвестная ошибка'}`, 'error')
  } finally {
    loadingAll.value = false
  }
}

// Счётчики вкладок — тот же scope видимости (subordinates_only), COUNT()-ом на бэке.
async function loadWishCounts() {
  try {
    wishCounts.value = await apiFetch<Record<string, number>>('/wishes/counts' + buildFilterParams({ subordinates_only: true }))
  } catch {
    // Счётчики — не критичны для работы списка, тихо оставляем прежние значения
  }
}

// Владелец, 2026-09-01: «показаны первые N из M» вместо молчаливой обрезки (limit=50 на бэке).
const allWishesTruncated = computed(() => {
  const total = wishCounts.value[allFilter.value]
  if (total === undefined) return null
  return allWishes.value.length < total ? total : null
})

async function loadIncoming() {
  loadingIncoming.value = true
  try {
    const data = await apiFetch<Wish[]>('/wishes/' + buildFilterParams({ assigned_to_me: true }))
    incomingWishes.value = data || []
  } catch (e: any) {
    ctx.showSnack(`Ошибка загрузки входящих заявок: ${e?.message || e?.payload?.message || 'неизвестная ошибка'}`, 'error')
    incomingWishes.value = []
  } finally {
    loadingIncoming.value = false
  }
}

async function reloadActiveTab() {
  if (activeTab.value === 'my') await loadWishes()
  else if (activeTab.value === 'incoming') await loadIncoming()
  else if (activeTab.value === 'all') await loadAllWishes()
}

function onAllFilterChange(v: string) {
  allFilter.value = v
  loadAllWishes()
}

// ── Форма/действия над одной заявкой живут в WishFormDialog.vue (defineExpose) ──
const formDialogRef = ref<InstanceType<typeof WishFormDialog> | null>(null)
function onCreate() { formDialogRef.value?.openCreate() }
function onOpenEdit(w: Wish) { formDialogRef.value?.openEdit(w) }
function onSubmitWish(w: Wish) { formDialogRef.value?.submitWish(w) }
function onDeleteWish(w: Wish) { formDialogRef.value?.deleteWish(w) }
function onApprove(w: Wish) { formDialogRef.value?.approveWish(w) }
function onReject(w: Wish) { formDialogRef.value?.openRejectDialog(w) }
function onKanban(w: Wish) { formDialogRef.value?.openKanbanDialog(w) }
function onConvert(w: Wish) { formDialogRef.value?.openConvertDialog(w) }
function onForceStatus(w: Wish) { formDialogRef.value?.openRowForceStatus(w) }
function onDownloadExcel(w: Wish, withPhotos: boolean) { formDialogRef.value?.downloadWishExcel(w, withPhotos) }

// Индикаторы загрузки для кнопок в строках таблиц — читаются реактивно из
// WishFormDialog.vue (владеет useWishActions), см. её defineExpose.
const submittingId = computed(() => formDialogRef.value?.submittingId ?? null)
const deletingId = computed(() => formDialogRef.value?.deletingId ?? null)
const approvingId = computed(() => formDialogRef.value?.approvingId ?? null)
const downloadingExcelId = computed(() => formDialogRef.value?.downloadingExcelId ?? null)

// «Registry area» для RegistryExportButton — то же самое, что было ref="registryArea"
// в исходном шаблоне (обёртка вокруг таблицы/карточек вкладки «Мои», без FAB).
const wishMyTabRef = ref<InstanceType<typeof WishMyTab> | null>(null)
const registryArea = computed(() => (wishMyTabRef.value as any)?.$el ?? null)

// Consent banner state
const pendingWishConsents = ref<PendingWishConsent[]>([])
const consentLoading = ref<string | null>(null)
async function loadPendingWishConsents() {
  try {
    pendingWishConsents.value = await apiFetch<PendingWishConsent[]>('/wishes/members/pending-consent')
  } catch { pendingWishConsents.value = [] }
}
async function respondWishConsent(wishId: number, accept: boolean) {
  consentLoading.value = wishId + (accept ? '_a' : '_d')
  try {
    await apiFetch(`/wishes/${wishId}/members/consent?accept=${accept}`, { method: 'POST' })
    ctx.showSnack(accept ? 'Вы приняли участие в заявке' : 'Вы отклонили участие')
    await loadPendingWishConsents()
  } catch (e: any) {
    ctx.showSnack(e?.payload?.message || e?.message || 'Не удалось обработать согласие', 'error')
  } finally {
    consentLoading.value = null
  }
}

// ── Card/table view toggle (primary "my" tab only) ──
const {
  mobile,
  viewMode,
  effectiveView,
  page: cardsPage,
  totalPages: cardsTotalPages,
  paged: pagedWishes,
} = useCardView({
  storageKey: 'wishes_view_mode',
  source: () => myWishesFiltered.value,
  pageSize: 24,
})

watch(activeTab, (v) => {
  if (v === 'my') loadWishes()
  else if (v === 'incoming') loadIncoming()
  else if (v === 'all') loadAllWishes()
})

onMounted(async () => {
  await Promise.all([
    apiFetch<Subsidy[]>('/subsidies/?scope=wishes').then(r => { ctx.subsidies.value = r }).catch(() => {}),
    apiFetch<FeoCategory[]>('/feo-categories/').then(r => { ctx.allFeoCategories.value = r }).catch(() => {}),
    apiFetch<User[]>('/users/').then(r => { ctx.users.value = r }).catch(() => {}),
    apiFetch<EventItem[]>('/events/').then(r => { ctx.events.value = r || [] }).catch(() => {}),
    apiFetch<{ all: boolean; ids: number[] }>('/users/assignable-ids')
      .then(r => { ctx.assignableAll.value = !!r.all; ctx.assignableIds.value = new Set(r.ids || []) })
      .catch(() => {}),
    ctx.isSaas.value
      ? apiFetch<typeof ctx.allOrgs.value>('/organizations/').then(r => { ctx.allOrgs.value = r || [] }).catch(() => {})
      : Promise.resolve(),
  ])
  await loadWishes()
  await loadIncoming()
  if (ctx.isManagerOrAdmin.value) {
    await loadAllWishes()
  }
  loadPendingWishConsents()
  // Открыть диалог создания если ?create=1 (редирект из /create-order или кнопки «Добавить»)
  if (route.query.create === '1') {
    onCreate()
  }
  // Deep-link: ?open={wish_id} — открыть заявку напрямую (например, переход из субсидии)
  const openId = route.query.open ? Number(route.query.open) : null
  if (openId && !isNaN(openId)) {
    try {
      const wish = await apiFetch<Wish>(`/wishes/${openId}`)
      if (wish?.id) onOpenEdit(wish)
    } catch { /* невалидный id — игнорируем */ }
  }
})
</script>

<style>
/* Владелец, 2026-08-13: «остановка заявки/закупки» — крупный алерт в красной
   рамке на всю ширину строки/карточки, а не мелкий чип. НЕ scoped (правило
   проекта — общий CSS-класс на несколько отдельных SFC: WishMyTab/WishIncomingTab/
   WishAllTab/WishFormDialog.vue после разбиения WishesView.vue на компоненты;
   scoped-стиль в одном из них не достал бы элементы в других). */
.wish-stopped-banner {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  column-gap: 10px;
  row-gap: 2px;
  width: 100%;
  border: 2px solid #d32f2f;
  background: #fdecea;
  color: #b71c1c;
  border-radius: 6px;
  padding: 6px 10px;
  margin-bottom: 6px;
}
.wish-stopped-banner__title {
  font-weight: 800;
  font-size: 0.92rem;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}
.wish-stopped-banner__meta {
  font-size: 0.78rem;
  font-weight: 500;
  opacity: 0.9;
}
.wish-stopped-banner--large {
  padding: 12px 16px;
}
.wish-stopped-banner--large .wish-stopped-banner__title {
  font-size: 1.15rem;
}
.wish-stopped-banner--large .wish-stopped-banner__meta {
  font-size: 0.85rem;
}

/* Мобильный фикс (владелец, 2026-09-04, «прокручиваемых вбок таблиц быть не должно»):
   растягивает v-btn-toggle на всю ширину контейнера и переносит текст кнопок на
   вторую строку вместо обрезки за правым краем экрана (используется в
   WishFormDialog.vue). НЕ scoped по той же причине, что и .wish-stopped-banner выше. */
.mobile-toggle-wrap {
  width: 100%;
}
.mobile-toggle-wrap :deep(.v-btn) {
  flex: 1 1 0;
  height: auto !important;
  min-height: 36px;
  padding-top: 6px;
  padding-bottom: 6px;
}
.mobile-toggle-wrap :deep(.v-btn__content) {
  white-space: normal;
  text-align: center;
  line-height: 1.2;
}

/* T3: pulse highlight for items/fields missing needed_date (WishFormDialog.vue) */
@keyframes wish-date-pulse {
  0%   { box-shadow: 0 0 0 0 rgba(211, 47, 47, 0.6); outline: 2px solid rgba(211, 47, 47, 0.8); }
  40%  { box-shadow: 0 0 0 8px rgba(211, 47, 47, 0); outline: 2px solid rgba(211, 47, 47, 0.4); }
  60%  { box-shadow: 0 0 0 0 rgba(211, 47, 47, 0); outline: 2px solid rgba(211, 47, 47, 0.8); }
  100% { box-shadow: 0 0 0 0 rgba(211, 47, 47, 0); outline: 2px solid transparent; }
}
.wish-date-missing-pulse {
  animation: wish-date-pulse 1s ease-out 3;
  border-radius: 4px;
}
/* Кнопка «заблокирована» гейтом категории ФЭО (владелец, 2026-08-11) — визуально
   приглушена, но не :disabled. */
.wish-btn-blocked {
  opacity: 0.55;
  filter: grayscale(0.35);
}

/* Владелец (2026-09-04): окно «Распределение позиций по закупкам» — шире,
   компактнее, с изменяемым мышью размером (см. WishKanbanDialog.vue).
   content-class на v-dialog применяется к .v-overlay__content, который Vuetify
   телепортирует в <body> — эти правила намеренно НЕ scoped. */
.wish-kanban-dialog-content {
  width: 95vw;
  max-width: 1800px;
  height: 88vh;
  max-height: 92vh;
  min-width: 760px;
  min-height: 420px;
  resize: both;
  overflow: hidden;
}
.v-overlay--fullscreen .wish-kanban-dialog-content {
  width: 100% !important;
  height: 100% !important;
  max-width: 100% !important;
  max-height: 100% !important;
  min-width: 0 !important;
  min-height: 0 !important;
  resize: none !important;
}
.wish-kanban-dialog-card {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.wish-kanban-dialog-cardtext {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  display: flex;
}
.wish-kanban-dialog-cardtext > * {
  min-height: 0;
  width: 100%;
}
</style>
