<template>
  <!-- Владелец (2026-09-16): «вкладка ТЗ, только свёрнутая, как в закупке» —
       заголовок/скачивание остаются своими (у заявки другой эндпоинт
       скачивания и нет решений по дублям), а таблица строк ТЗ — общий
       TzRowsSection.vue (21.09, corrections-21-09.md W3): данные ИСКЛЮЧИТЕЛЬНО
       с сервера (GET /api/wishes/{id}/tz-rows), без локального пересчёта. -->
  <v-card v-if="visibleItems.length" variant="outlined" class="mb-4" style="border-color:#3B82F6">
    <v-card-title
      class="text-subtitle-1 font-weight-bold px-4 pt-3 d-flex align-center justify-space-between"
      style="cursor:pointer;user-select:none"
      @click.self="toggleCollapsed"
    >
      <span class="d-flex align-center gap-2" style="cursor:pointer" @click="toggleCollapsed">
        <v-icon icon="mdi-clipboard-text-outline" color="primary" size="20" />
        Техническое задание
        <v-icon
          :icon="collapsed ? 'mdi-chevron-down' : 'mdi-chevron-up'"
          size="18"
          color="grey"
          class="ml-1"
        />
      </span>
      <div class="d-flex align-center gap-2" @click.stop>
        <v-btn-toggle v-model="descriptionMode" mandatory density="compact" color="primary" class="mr-2">
          <v-btn value="exact" size="small" style="text-transform:none;letter-spacing:0">Точное</v-btn>
          <v-btn value="44fz" size="small" style="text-transform:none;letter-spacing:0">44-ФЗ</v-btn>
        </v-btn-toggle>
        <v-btn
          v-if="wishId"
          size="small"
          variant="tonal"
          color="primary"
          prepend-icon="mdi-file-word-outline"
          :loading="downloading"
          @click="downloadTz"
        >
          Скачать ТЗ (.docx)
        </v-btn>
        <v-chip v-else size="small" color="grey" variant="tonal">Сохраните заявку для скачивания</v-chip>
      </div>
    </v-card-title>
    <v-card-text v-show="!collapsed" class="pa-0">
      <!-- Лист-таблица ТЗ (№, фото+название, описание, кол-во, ед.) — ВСЕГДА
           по локальным позициям формы (до и после сохранения заявки), как
           было до коммита b966b1db (владелец, 26.10.2026: «почему
           переделалось в блоки?»). Правка описания мутирует те же объекты
           позиций, что держит форма заявки (props.items — ссылка на
           wishForm.value.items), автосейв формы подхватывает сам. Один
           рендер строки (WishTzItemRow внутри ячейки) — см.
           WishTzLocalTable.vue (Правило №5/№6). -->
      <div class="px-4 pt-3 pb-1">
        <WishTzLocalTable :items="visibleItems" :mode="descriptionMode" @propose="openProposeDialog" />
      </div>

      <ProposeToCatalogDialog
        v-if="proposeTarget"
        v-model="proposeDialogShow"
        :product-id="proposeTarget.product_id"
        :catalog-value="proposeTarget._description || null"
        :own-value="proposeTarget.tz_description || ''"
        field="description"
        :wish-item-id="proposeTarget.id"
      />
      <!-- Проверка повторяющихся позиций — ТОЛЬКО после сохранения (нет
           своего локального пересчёта дублей, Правило №6) — у TzRowsSection
           здесь остаётся только баннер (bannerOnly), таблицу строк рисует
           WishTzLocalTable выше, дважды список не выводим. -->
      <TzRowsSection
        v-if="wishId"
        ref="tzRowsRef"
        :wish-id="wishId"
        readonly
        banner-only
        :show-prices="false"
        :resolve-local-item="resolveLocalItem"
        :active-description="activeDescription"
      />
      <div v-else class="px-4 pb-3 text-caption text-medium-emphasis">
        Проверка повторяющихся позиций — после сохранения заявки.
      </div>
    </v-card-text>
  </v-card>

  <v-snackbar v-model="errorShow" color="error" :timeout="-1">
    {{ errorText }}
    <template #actions>
      <v-btn variant="text" @click="errorShow = false">Закрыть</v-btn>
    </template>
  </v-snackbar>
</template>

<script setup lang="ts">
// Секция «Техническое задание» для заявки — заголовок/скачивание свои
// (эндпоинт скачивания у заявки другой, решений по дублям тут нет — см.
// backend/app/routers/wish_tz.py), таблица строк — общий TzRowsSection.vue.
// Фото/описание позиции сервер не отдаёт — источник, как и раньше, локальные
// items формы (WishFormDialog передаёт wishForm.items с уже проставленным id).
import { computed, ref, watch } from 'vue'
import TzRowsSection from '@/components/purchase/TzRowsSection.vue'
import ProposeToCatalogDialog from '@/components/products/ProposeToCatalogDialog.vue'
import WishTzLocalTable from '@/components/wishes/WishTzLocalTable.vue'
import type { TzRow } from '@/composables/purchase/useTzRows'
import { effectiveTz } from '@/utils/itemTz'

type EditorItem = any

const props = defineProps<{
  items: EditorItem[]
  wishId?: number | null
}>()

const tzRowsRef = ref<InstanceType<typeof TzRowsSection> | null>(null)

// Карточка видна, пока в заявке есть именованные позиции — даже до первого
// сохранения (wishId ещё нет). Таблица строк внутри — только после сохранения
// (см. шаблон), она читает исключительно сервер.
const visibleItems = computed(() => (props.items || []).filter((it) => (it.item_name || '').trim()))

// Ключ 'wish_tz_collapsed', формула дефолта — как было до b966b1db (владелец,
// 26.10.2026: «раскрытие без клика не нужно») — свёрнут, если в localStorage
// не лежит явное '0'. Раскрывается только явным кликом по заголовку.
const COLLAPSE_KEY = 'wish_tz_collapsed'
const MODE_KEY = 'wish_tz_description_mode'

const collapsed = ref(localStorage.getItem(COLLAPSE_KEY) !== '0') // свёрнута по умолчанию
function toggleCollapsed() {
  collapsed.value = !collapsed.value
  try { localStorage.setItem(COLLAPSE_KEY, collapsed.value ? '1' : '0') } catch { /* noop */ }
}

const descriptionMode = ref<'exact' | '44fz'>(
  (localStorage.getItem(MODE_KEY) as 'exact' | '44fz') || 'exact'
)
function _persistMode(v: 'exact' | '44fz') {
  try { localStorage.setItem(MODE_KEY, v) } catch { /* noop */ }
}
// v-btn-toggle mutates descriptionMode directly via v-model; persist on change.
watch(descriptionMode, _persistMode)

// Позиции заявки меняются в форме без её перезагрузки (add/remove/edit) —
// перечитываем строки ТЗ с сервера, чтобы баннер дублей не отставал.
// wishForm.items меняется часто (каждый keystroke) — берём только длину как
// триггер, id/имена новых позиций появляются на сервере после автосейва формы,
// частый чистый watch(items, deep) гонял бы tz-rows на каждый ввод буквы.
watch(() => props.items?.length, () => { tzRowsRef.value?.refresh() })

// «Предложить в каталог» (Этап В, п.4) — один диалог на секцию, цель —
// текущая позиция (ProposeToCatalogDialog сам шлёт POST .../description-proposals
// и показывает тост по итогу — ПРАВИЛО №6, второй отправки здесь нет).
const proposeDialogShow = ref(false)
const proposeTarget = ref<EditorItem | null>(null)
function openProposeDialog(item: EditorItem) {
  proposeTarget.value = item
  proposeDialogShow.value = true
}

function resolveLocalItem(row: TzRow): EditorItem | undefined {
  const list = props.items || []
  if (row.item_id != null) {
    const byId = list.find((it) => it.id === row.item_id)
    if (byId) return byId
  }
  return list.find((it) => (it.item_name || '').trim() && (it.item_name || '').trim() === row.item_name?.trim())
}

function activeDescription(item: EditorItem): string {
  // Своё ТЗ позиции (tz_description) важнее каталожного — ОДНА формула
  // (effectiveTz, ПРАВИЛО №6), план item-tz-description.md, Этап Б. Для
  // позиций без каталожной привязки своё ТЗ всё равно может быть (импорт из
  // файла) — проверяем его раньше подсказки «появится после привязки».
  const d = effectiveTz(item, descriptionMode.value)
  if (d) return d
  if (!item.product_id) return 'описание появится после привязки к каталогу'
  return 'нет описания'
}

const downloading = ref(false)
const errorShow = ref(false)
const errorText = ref('')

async function downloadTz() {
  if (!props.wishId) return
  downloading.value = true
  try {
    const res = await fetch(
      `/api/wishes/${props.wishId}/documents/tech_spec?tz_override_mode=${descriptionMode.value}`,
      { headers: {} }
    )
    if (!res.ok) {
      const err = await res.json().catch(() => null)
      throw new Error(err?.detail || err?.message || `Ошибка ${res.status}`)
    }
    const blob = await res.blob()
    const disposition = res.headers.get('Content-Disposition') || ''
    let filename = 'ТЗ.docx'
    const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i)
    if (utf8Match?.[1]) {
      try { filename = decodeURIComponent(utf8Match[1]) } catch { /* keep default */ }
    }
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch (e: any) {
    errorText.value = e?.message || 'Ошибка генерации документа'
    errorShow.value = true
  } finally {
    downloading.value = false
  }
}
</script>
