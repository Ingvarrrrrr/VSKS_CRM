<template>
  <!-- Владелец (2026-09-16): «вкладка ТЗ, только свёрнутая, как в закупке» —
       тот же вид, что и секция «Техническое задание» в CreateOrderView.vue
       (2.5, свёрнута по умолчанию), но самодостаточный компонент: свои
       collapsed/description-mode в localStorage, своя ошибка скачивания.
       Перенос секции закупки на этот же компонент — отдельный шаг, см. отчёт. -->
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
      <v-table density="comfortable" class="wish-tz-table">
        <thead>
          <tr>
            <th style="width:36px;text-align:center">№</th>
            <th style="width:72px;text-align:center">Фото</th>
            <th>Наименование и описание</th>
            <th style="width:70px;text-align:center">Кол-во</th>
            <th style="width:56px;text-align:center">Ед.</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(item, i) in visibleItems" :key="item._uid ?? i" style="vertical-align:middle">
            <td class="text-center text-medium-emphasis">{{ i + 1 }}</td>
            <td class="text-center py-2">
              <v-avatar v-if="item._photo_url" size="56" rounded="sm" style="overflow:hidden">
                <img :src="item._photo_url" style="width:56px;height:56px;object-fit:cover;display:block" />
              </v-avatar>
              <v-icon v-else size="40" color="grey-lighten-2">mdi-image-off-outline</v-icon>
            </td>
            <td class="py-2">
              <div class="font-weight-medium" style="font-size:13px">{{ item.item_name }}</div>
              <div class="text-caption text-medium-emphasis mt-1" style="white-space:pre-line;max-width:420px">
                {{ activeDescription(item) }}
              </div>
            </td>
            <td class="text-center">{{ item.quantity ?? '—' }}</td>
            <td class="text-center">{{ item.unit || '—' }}</td>
          </tr>
        </tbody>
      </v-table>
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
// Секция «Техническое задание» для заявки — свёрнутая копия одноимённой секции
// закупки (CreateOrderView.vue:802+), но самостоятельный компонент: не тянет
// сюда логику CreateOrderView, читает только items/wishId. Скачивание — новый
// эндпоинт GET /api/wishes/{id}/documents/tech_spec (wish_documents.py),
// который переиспользует ТОТ ЖЕ построитель контекста ТЗ, что и закупка
// (services/documents/contexts.py::_build_items_list_from_purchase_items).
import { ref, computed, watch } from 'vue'

type EditorItem = any

const props = defineProps<{
  items: EditorItem[]
  wishId?: number | null
}>()

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

const visibleItems = computed(() => (props.items || []).filter((it) => (it.item_name || '').trim()))

function activeDescription(item: EditorItem): string {
  if (!item.product_id) return 'описание появится после привязки к каталогу'
  const d = descriptionMode.value === '44fz'
    ? (item._description_44fz || item._description)
    : item._description
  return d || 'нет описания'
}

const downloading = ref(false)
const errorShow = ref(false)
const errorText = ref('')

async function downloadTz() {
  if (!props.wishId) return
  downloading.value = true
  try {
    const token = localStorage.getItem('auth_token')
    const res = await fetch(
      `/api/wishes/${props.wishId}/documents/tech_spec?tz_override_mode=${descriptionMode.value}`,
      { headers: { Authorization: `Bearer ${token}` } }
    )
    if (!res.ok) {
      const err = await res.json().catch(() => null)
      throw new Error(err?.detail || err?.message || `Ошибка ${res.status}`)
    }
    const blob = await res.blob()
    const disposition = res.headers.get('Content-Disposition') || ''
    let filename = 'ТЗ.docx'
    const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i)
    if (utf8Match) {
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

<style scoped>
.wish-tz-table :deep(th) {
  font-size: 12px;
  color: rgba(0, 0, 0, 0.6);
  background: rgba(59, 130, 246, 0.04);
}
</style>
